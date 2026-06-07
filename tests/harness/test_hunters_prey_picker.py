"""v2.99.223 — Hunter's Prey picker + Giant Killer + Horde Breaker.

Phase E.3 of the v2.99.193 phased completion plan. RAW PHB
p.93: at Hunter Ranger Lv 3, pick one of:
  - Colossus Slayer (already shipped v2.60.0 via the attack
    auto-uplift framework)
  - Giant Killer: reaction to attack a Large+ creature within
    5 ft after it hits / misses you.
  - Horde Breaker: once per turn, extra attack with the same
    weapon against a different creature within 5 ft.

v1 ships:
  - /select_hunters_prey picker endpoint.
  - /use_giant_killer announce endpoint (marks reaction chip).
  - /use_horde_breaker announce endpoint (no chip — RAW part of
    Attack action).

Rowan Quickbow (Ranger Hunter Lv 7) is the demo fixture.

Tests:
  - Select picker: 200 + persists.
  - Picker bad option: 400.
  - Giant Killer happy: 200 + broadcast.
  - Giant Killer wrong pick: 409.
  - Horde Breaker happy: 200 + broadcast.
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


def _hp_pick_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "hunters-prey-pick"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _gk_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "giant-killer"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _hb_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "horde-breaker"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def rowan_clean_pick(gm_client, roster):
    """Reset Rowan's hunters_prey to "" in teardown."""
    rowan = roster["Rowan Quickbow"]
    yield rowan
    await _patch_sheet(gm_client, rowan["id"], {"hunters_prey": ""})


async def test_select_hunters_prey_happy_path(
    gm_client, gm_ws, rowan_clean_pick,
):
    """Rowan picks giant-killer."""
    rowan = rowan_clean_pick
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_hunters_prey",
        json={
            "character_id": rowan["id"],
            "option": "giant-killer",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["option"] == "giant-killer"
    await asyncio.sleep(0.3)
    feats = _hp_pick_broadcasts(gm_ws, rowan["id"])
    assert feats


async def test_select_hunters_prey_bad_option(
    gm_client, roster,
):
    """Bad option → 400."""
    rowan = roster["Rowan Quickbow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_hunters_prey",
        json={
            "character_id": rowan["id"],
            "option": "improved-critical",
        },
    )
    assert r.status_code == 400, r.text


async def test_use_giant_killer_happy_path(
    gm_client, gm_ws, rowan_clean_pick,
):
    """Rowan with giant-killer pick → /use_giant_killer → 200."""
    rowan = rowan_clean_pick
    await _patch_sheet(
        gm_client, rowan["id"], {"hunters_prey": "giant-killer"},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_giant_killer",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "giant-killer"
    await asyncio.sleep(0.3)
    feats = _gk_broadcasts(gm_ws, rowan["id"])
    assert feats


async def test_use_giant_killer_wrong_pick(
    gm_client, rowan_clean_pick,
):
    """Rowan with horde-breaker pick → /use_giant_killer → 409."""
    rowan = rowan_clean_pick
    await _patch_sheet(
        gm_client, rowan["id"], {"hunters_prey": "horde-breaker"},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_giant_killer",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_hunters_prey"
    assert data.get("expected") == "giant-killer"


async def test_use_horde_breaker_happy_path(
    gm_client, gm_ws, rowan_clean_pick,
):
    """Rowan with horde-breaker pick + target_name → 200 + broadcast."""
    rowan = rowan_clean_pick
    await _patch_sheet(
        gm_client, rowan["id"], {"hunters_prey": "horde-breaker"},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_horde_breaker",
        json={
            "character_id": rowan["id"],
            "target_name": "Goblin #2",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "horde-breaker"
    assert data["target_name"] == "Goblin #2"
    await asyncio.sleep(0.3)
    feats = _hb_broadcasts(gm_ws, rowan["id"])
    assert feats
    feat_data = feats[-1].get("data") or {}
    assert "Goblin #2" in (feat_data.get("feature_name") or "")


def _mkc(cid, char_id, name="C", hp=30):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": hp, "hp_max": hp, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def test_horde_breaker_resolves_second_attack(
    gm_client, rowan_clean_pick,
):
    """v2.99.451 — Phase 2 extra-attack retrofit: with a
    target_combatant_id, Horde Breaker resolves the bonus Longbow attack
    server-side (roll vs AC, apply damage on a hit). Loop re-seeding the
    battle (which clears the once-per-turn flag) until a swing connects.
    """
    rowan = rowan_clean_pick
    await _patch_sheet(gm_client, rowan["id"], {"hunters_prey": "horde-breaker"})
    rowan_cid = f"tok_hb_rowan_{rowan['id']}"
    dummy_cid = "tok_hb_dummy"

    hit_data = None
    for _ in range(12):
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [
                _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
                _mkc(dummy_cid, None, name="Dummy"),
            ], "turn_index": 0, "round": 1, "active": True},
        )
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_horde_breaker",
            json={"character_id": rowan["id"], "attack_index": 0,
                  "target_combatant_id": dummy_cid},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["attacked"] is True
        assert data["target_ac"] > 0
        if data["hit"]:
            assert data["damage_type"] == "piercing"
            assert data["damage_rolled"] > 0  # 1d8+4
            assert data["damage_applied"] > 0
            hit_data = data
            break
    assert hit_data is not None, "no hit in 12 Horde Breaker swings"


async def test_horde_breaker_once_per_turn(
    gm_client, rowan_clean_pick,
):
    """The second Horde Breaker attack in the same turn → 409
    already_used (the once-per-turn economy flag)."""
    rowan = rowan_clean_pick
    await _patch_sheet(gm_client, rowan["id"], {"hunters_prey": "horde-breaker"})
    rowan_cid = f"tok_hb2_rowan_{rowan['id']}"
    dummy_cid = "tok_hb2_dummy"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
            _mkc(dummy_cid, None, name="Dummy"),
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_horde_breaker",
        json={"character_id": rowan["id"], "attack_index": 0,
              "target_combatant_id": dummy_cid},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["attacked"] is True
    # Second use this turn → blocked.
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_horde_breaker",
        json={"character_id": rowan["id"], "attack_index": 0,
              "target_combatant_id": dummy_cid},
    )
    assert r2.status_code == 409, r2.text
    assert r2.json()["error"] == "already_used"


async def test_horde_breaker_target_not_in_battle_404(
    gm_client, rowan_clean_pick,
):
    """A target_combatant_id not in battle → 404."""
    rowan = rowan_clean_pick
    await _patch_sheet(gm_client, rowan["id"], {"hunters_prey": "horde-breaker"})
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_horde_breaker",
        json={"character_id": rowan["id"], "attack_index": 0,
              "target_combatant_id": "nope_not_in_battle"},
    )
    assert r.status_code == 404, r.text
