"""v2.99.365 — Path of the Zealot Barbarian: Divine Fury (G Barbarian batch #2, Lv 3+, XGE).

Phase G Barbarian Paths subclass batch ship #2 — Path of the
Zealot opens.
RAW XGE p.11: while raging, the first creature you hit each turn
with a weapon attack takes extra damage = 1d6 + half your
barbarian level, of a chosen type (necrotic or radiant).

v1 announce-only — the on-hit application + first-hit-per-turn
limit are GM-tracked. The bonus damage is rolled server-side. No
action cost.

Krieger Stonefist (Barbarian, PATCHed to Path of the Zealot Lv 7)
is the demo fixture (half level = 3).

Tests:
  - Lv 7 happy (default radiant): bonus = 1d6 + 3, type radiant.
  - Lv 7 happy (necrotic): damage_type echoes "necrotic".
  - Wrong subclass (default Berserker) → 409.
  - Invalid damage_type → 400.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X"):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": 60, "hp_max": 60,
        "buffs": [], "speed_walk": 30,
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0},
    }


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _df_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "divine-fury"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def krieger_zealot(gm_client, roster):
    """PATCH Krieger to Path of the Zealot; restore to Berserker."""
    krieger = roster["Krieger Stonefist"]
    await _patch_sheet(
        gm_client, krieger["id"],
        {"subclass": "Path of the Zealot"},
        class_slug="barbarian",
    )
    try:
        yield krieger
    finally:
        await _patch_sheet(
            gm_client, krieger["id"],
            {"subclass": "Path of the Berserker"},
            class_slug="barbarian",
        )


async def test_use_df_happy_radiant(
    gm_client, gm_ws, krieger_zealot,
):
    """Lv 7 Zealot, default → radiant, bonus = 1d6 + 3 in [4,9]."""
    krieger = krieger_zealot
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_fury",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "divine-fury"
    assert data["damage_type"] == "radiant"
    assert data["half_level"] == 3
    assert 1 <= data["die_roll"] <= 6
    assert data["bonus_damage"] == data["die_roll"] + 3
    assert data["barbarian_level"] == 7
    await asyncio.sleep(0.3)
    feats = _df_broadcasts(gm_ws, krieger["id"])
    assert feats
    assert feats[-1]["data"]["bonus_damage"] == data["bonus_damage"]


async def test_use_df_happy_necrotic(
    gm_client, krieger_zealot,
):
    """damage_type=necrotic echoes through."""
    krieger = krieger_zealot
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_fury",
        json={"character_id": krieger["id"], "damage_type": "necrotic"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["damage_type"] == "necrotic"


async def test_use_df_wrong_subclass(
    gm_client, roster,
):
    """Default Krieger (Berserker) → 409."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_fury",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_df_invalid_type(
    gm_client, krieger_zealot,
):
    """Invalid damage_type → 400."""
    krieger = krieger_zealot
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_fury",
        json={"character_id": krieger["id"], "damage_type": "fire"},
    )
    assert r.status_code == 400, r.text


async def test_df_installs_rider_and_lands(
    gm_client, gm_ws, krieger_zealot,
):
    """v2.99.402 — Divine Fury installs a non-target, once-per-turn rider
    (1d6 + half-level), and the bonus lands on the first /attack hit.

    Non-target (no stored target key) + once-per-turn: stripped on a
    miss, so retry until a swing connects (Krieger's Greataxe is +7).
    """
    krieger = krieger_zealot
    krieger_cid = f"tok_df_krieger_{krieger['id']}"
    dummy_cid = "tok_df_dummy"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _mkc(krieger_cid, krieger["id"], name=krieger["name"]),
            _mkc(dummy_cid, None, name="Dummy"),
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_divine_fury",
        json={"character_id": krieger["id"], "damage_type": "necrotic"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["buff_installed"] is True

    bu = await gm_ws.wait_for("buff_update")
    df = next((b for b in bu["data"]["buffs"]
               if b.get("key") == "divine-fury"), None)
    assert df is not None, bu["data"]["buffs"]
    eff = df.get("effects") or {}
    assert eff.get("weapon_hit_bonus_dice") == "1d6"
    assert eff.get("weapon_hit_bonus_flat") == 3  # half of Lv 7
    assert eff.get("weapon_hit_bonus_damage_type") == "necrotic"
    assert eff.get("weapon_hit_once_per_turn") is True
    assert eff.get("weapon_hit_flag") == "divine_fury"
    # Non-target rider: no stored target key.
    assert "weapon_hit_bonus_target_combatant_id" not in eff

    # First weapon hit this turn auto-adds +1d6+3 necrotic.
    hit_ad = None
    for _ in range(12):
        a = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": krieger["id"], "attack_index": 0,
                  "target_combatant_id": dummy_cid, "override": True},
        )
        assert a.status_code == 200, a.text
        ad = a.json()
        if ad["hit"]:
            hit_ad = ad
            break
    assert hit_ad is not None, "expected at least one hit in 12 swings"
    ups = [u for u in (hit_ad.get("auto_uplifts") or [])
           if u.get("source") == "divine-fury"]
    assert len(ups) == 1, hit_ad.get("auto_uplifts")
    assert ups[0]["expression"] == "1d6+3"
    assert ups[0]["damage_type"] == "necrotic"
    assert 4 <= ups[0]["total"] <= 9  # 1d6 (1-6) + 3
