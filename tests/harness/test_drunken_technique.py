"""v2.99.360 — Way of the Drunken Master Monk: Drunken Technique (G Monk batch #6, Lv 3+, XGE).

Phase G Monk Ways subclass batch ship #6 — Way of the Drunken
Master opens.
RAW XGE p.33: whenever you use Flurry of Blows, you gain the
benefit of the Disengage action and your walking speed increases
by 10 ft until the end of the current turn.

v2.158.18 installed the rider buff (disengage flag + speed flag).
v2.158.37 (Phase 2 finisher) wires the +10 ft speed half: the buff
now carries the engine-generic `effects.speed_bonus_ft: 10`, which
`effective_speed_walk` folds into the `/token/move` speed cap. The
disengage half was already consumed by the OA-prompting flow.

Kael Brightleaf (Monk, PATCHed to Way of the Drunken Master Lv 7)
is the demo fixture.

Tests:
  - Lv 7 happy: disengage True, speed_bonus_ft 10, broadcast fires.
  - State contract: buff carries disengage + both speed keys.
  - Phase 2 read site: the buff raises the move-cap 30 → 40 ft.
  - Wrong subclass (default Way of the Open Hand) → 409.
  - Wrong class (Caelan paladin) → 409.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _dt_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "drunken-technique"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def kael_drunken(gm_client, roster):
    """PATCH Kael to Way of the Drunken Master; restore to Open Hand."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(
        gm_client, kael["id"],
        {"subclass": "Way of the Drunken Master"},
        class_slug="monk",
    )
    try:
        yield kael
    finally:
        await _patch_sheet(
            gm_client, kael["id"],
            {"subclass": "Way of the Open Hand"},
            class_slug="monk",
        )


def _pc(cid, c, *, hp_max=40):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_kael_in_battle(gm_client, kael):
    """v2.158.18 — `_install_buff` requires an active battle.
    Seed a minimal one with Kael."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_dt_kael_{kael['id']}", kael)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def test_use_dt_happy_lv7(
    gm_client, gm_ws, kael_drunken,
):
    """Lv 7 Drunken Master → disengage True, +10 ft speed,
    buff_installed True."""
    kael = kael_drunken
    await _seed_kael_in_battle(gm_client, kael)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_drunken_technique",
        json={"character_id": kael["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "drunken-technique"
    assert data["disengage"] is True
    assert data["speed_bonus_ft"] == 10
    assert data["monk_level"] == 7
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _dt_broadcasts(gm_ws, kael["id"])
    assert feats
    assert feats[-1]["data"]["speed_bonus_ft"] == 10


async def test_dt_buff_payload_carries_disengage_and_speed_flags(
    gm_client, gm_ws, kael_drunken,
):
    """v2.158.18 — state contract (Phase 9): the installed
    `drunken-technique-active` buff carries `effects.disengage:
    True` (reuses the engine flag from Step of the Wind), plus
    the two Drunken-Technique-specific flags
    (`speed_bonus_ft: 10`, `rider_of: "flurry-of-blows"`).
    Duration 1 round (until end of turn per RAW)."""
    kael = kael_drunken
    await _seed_kael_in_battle(gm_client, kael)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_drunken_technique",
        json={"character_id": kael["id"]},
    )
    assert r.status_code == 200, r.text
    bu = await gm_ws.wait_for("buff_update")
    kael_buffs = bu["data"]["buffs"]
    dt_buff = next(
        (b for b in kael_buffs if b.get("key") == "drunken-technique-active"),
        None,
    )
    assert dt_buff is not None, (
        f"drunken-technique-active buff missing; got keys="
        f"{[b.get('key') for b in kael_buffs]}"
    )
    effects = dt_buff.get("effects") or {}
    assert effects.get("disengage") is True
    # v2.158.37 — Phase 2: the engine-generic speed key the move-cap
    # reader actually consumes, alongside the descriptive key.
    assert effects.get("speed_bonus_ft") == 10
    assert effects.get("drunken_technique_speed_bonus_ft") == 10
    assert effects.get("drunken_technique_rider_of") == "flurry-of-blows"
    # 1-turn buff (until end of turn per RAW), not concentration.
    assert dt_buff.get("concentration") in (False, None)
    assert int(dt_buff.get("duration_rounds") or 0) == 1


async def _tokens_by_char(client):
    resp = await client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    assert resp.status_code == 200, resp.text
    return {
        t["character_id"]: t
        for t in resp.json()["tokens"]
        if t.get("character_id")
    }


def _mkc_move(cid, char_id, name, source_token_id, *, buffs=None):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "source_token_id": source_token_id,
        "initiative": 10, "hp_current": 50, "hp_max": 50,
        "speed_walk": 30, "buffs": buffs or [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def test_dt_speed_bonus_raises_move_cap(gm_client, roster):
    """v2.158.37 — Phase 2 read site. A combatant carrying the
    `drunken-technique-active` buff (`effects.speed_bonus_ft: 10`)
    has its `/token/move` speed cap raised 30 → 40, so a 35 ft move
    that 409s for an unbuffed control returns 200. This exercises the
    engine path (`effective_speed_walk` → `effective_speed_bonus_ft`)
    that previously ignored the inert `drunken_technique_speed_bonus_ft`
    key."""
    pip = roster["Pip Quickfingers"]
    tokens = await _tokens_by_char(gm_client)
    assert pip["id"] in tokens, "no Pip token on the demo map"
    tok = tokens[pip["id"]]
    # Park the token at a known origin.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
        json={"x": 350.0, "y": 350.0, "over_speed_confirmed": True,
              "oa_confirmed": True},
    )
    try:
        # Control: no buff → 35 ft move (840,350) exceeds the 30 ft cap.
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [
                _mkc_move(f"tok_dt_cap_{pip['id']}", pip["id"], pip["name"],
                          tok["id"]),
            ], "turn_index": 0, "round": 1, "active": True},
        )
        ctrl = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
            json={"x": 840.0, "y": 350.0},
        )
        assert ctrl.status_code == 409, ctrl.text
        assert ctrl.json().get("cap_ft") == 30
        # With the Drunken Technique buff → cap 40, same move passes.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
            json={"x": 350.0, "y": 350.0, "over_speed_confirmed": True,
                  "oa_confirmed": True},
        )
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [
                _mkc_move(
                    f"tok_dt_cap_{pip['id']}", pip["id"], pip["name"],
                    tok["id"],
                    buffs=[{
                        "key": "drunken-technique-active",
                        "name": "🍶 Drunken Technique",
                        "effects": {"disengage": True, "speed_bonus_ft": 10},
                        "duration_rounds": 1,
                    }],
                ),
            ], "turn_index": 0, "round": 1, "active": True},
        )
        buffed = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
            json={"x": 840.0, "y": 350.0},
        )
        assert buffed.status_code == 200, (
            f"v2.158.37: Drunken Technique speed_bonus_ft should raise the "
            f"cap to 40 so a 35 ft move passes; got {buffed.status_code} "
            f"{buffed.text}"
        )
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0,
                  "round": 1, "active": False},
        )


async def test_use_dt_wrong_subclass(
    gm_client, roster,
):
    """Default Kael (Way of the Open Hand) → 409."""
    kael = roster["Kael Brightleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_drunken_technique",
        json={"character_id": kael["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_dt_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_drunken_technique",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
