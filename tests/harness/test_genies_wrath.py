"""v2.99.355 — The Genie Warlock: Genie's Wrath (G Warlock batch CLOSE, Lv 1+, TCE).

Phase G Warlock patron subclass batch ship #7 — The Genie opens
and CLOSES the Warlock patron batch (7/7).
RAW TCE p.71: once per turn on a hit, deal extra damage = your
proficiency bonus. The type depends on your genie kind:
bludgeoning (dao), thunder (djinni), fire (efreeti), cold (marid).

v1 announce-only — the once-per-turn limit + on-hit damage
application are GM-tracked. The +PB damage + type are computed
server-side. No action cost.

Magnus Hexbinder (Warlock, PATCHed to The Genie Lv 5) is the demo
fixture.

Tests:
  - Lv 5 happy (default djinni → thunder): bonus_damage = PB.
  - Lv 5 happy (efreeti → fire): damage_type echoes "fire".
  - Wrong subclass (default The Fiend) → 409.
  - Invalid genie_kind → 400.
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


def _gw_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "genies-wrath"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def magnus_genie(gm_client, roster):
    """PATCH Magnus to The Genie; restore to The Fiend."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(
        gm_client, magnus["id"],
        {"subclass": "The Genie"},
        class_slug="warlock",
    )
    try:
        yield magnus
    finally:
        await _patch_sheet(
            gm_client, magnus["id"],
            {"subclass": "The Fiend"},
            class_slug="warlock",
        )


async def test_use_gw_happy_default(
    gm_client, gm_ws, magnus_genie,
):
    """Lv 5 Genie, default kind → thunder (djinni), +PB damage."""
    magnus = magnus_genie
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_genies_wrath",
        json={"character_id": magnus["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "genies-wrath"
    assert data["genie_kind"] == "djinni"
    assert data["damage_type"] == "thunder"
    assert data["bonus_damage"] >= 2  # proficiency bonus (>=2)
    assert data["warlock_level"] == 5
    await asyncio.sleep(0.3)
    feats = _gw_broadcasts(gm_ws, magnus["id"])
    assert feats
    assert feats[-1]["data"]["damage_type"] == "thunder"


async def test_use_gw_happy_efreeti(
    gm_client, magnus_genie,
):
    """efreeti → fire."""
    magnus = magnus_genie
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_genies_wrath",
        json={"character_id": magnus["id"], "genie_kind": "efreeti"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["genie_kind"] == "efreeti"
    assert data["damage_type"] == "fire"


def _mkc(cid, char_id, name="C"):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": 40, "hp_max": 40, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def test_gw_installs_rider_and_lands(
    gm_client, gm_ws, magnus_genie,
):
    """v2.99.450 — Phase 2 retrofit: Genie's Wrath installs a non-target,
    once-per-turn flat rider (+PB of the genie's element), and the bonus
    lands on the first /attack hit through the uplift pipeline.
    """
    magnus = magnus_genie
    magnus_cid = f"tok_gw_magnus_{magnus['id']}"
    dummy_cid = "tok_gw_dummy"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _mkc(magnus_cid, magnus["id"], name=magnus["name"]),
            _mkc(dummy_cid, None, name="Dummy"),
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_genies_wrath",
        json={"character_id": magnus["id"]},  # default djinni → thunder
    )
    assert r.status_code == 200, r.text
    rd = r.json()
    assert rd["rider_installed"] is True
    pb = rd["bonus_damage"]

    bu = await gm_ws.wait_for("buff_update")
    gw = next((b for b in bu["data"]["buffs"]
               if b.get("key") == "genies-wrath"), None)
    assert gw is not None, bu["data"]["buffs"]
    eff = gw.get("effects") or {}
    assert eff.get("weapon_hit_bonus_flat") == pb
    assert eff.get("weapon_hit_bonus_damage_type") == "thunder"
    assert eff.get("weapon_hit_once_per_turn") is True
    assert eff.get("weapon_hit_flag") == "genies_wrath"
    assert "weapon_hit_bonus_target_combatant_id" not in eff

    # First weapon hit this turn auto-adds +PB thunder.
    hit_ad = None
    for _ in range(12):
        a = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": magnus["id"], "attack_index": 0,
                  "target_combatant_id": dummy_cid, "override": True},
        )
        assert a.status_code == 200, a.text
        ad = a.json()
        if ad["hit"]:
            hit_ad = ad
            break
    assert hit_ad is not None, "expected at least one hit in 12 swings"
    ups = [u for u in (hit_ad.get("auto_uplifts") or [])
           if u.get("source") == "genies-wrath"]
    assert len(ups) == 1, hit_ad.get("auto_uplifts")
    assert ups[0]["damage_type"] == "thunder"
    assert ups[0]["total"] == pb


async def test_use_gw_wrong_subclass(
    gm_client, roster,
):
    """Default Magnus (The Fiend) → 409."""
    magnus = roster["Magnus Hexbinder"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_genies_wrath",
        json={"character_id": magnus["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_gw_invalid_kind(
    gm_client, magnus_genie,
):
    """Invalid genie_kind → 400."""
    magnus = magnus_genie
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_genies_wrath",
        json={"character_id": magnus["id"], "genie_kind": "pixie"},
    )
    assert r.status_code == 400, r.text
