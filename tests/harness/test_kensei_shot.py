"""v2.99.357 — Way of the Kensei Monk: Kensei's Shot (G Monk Ways batch #2, Lv 3+, XGE).

Phase G Monk Ways subclass batch ship #2 — Way of the Kensei
opens.
RAW XGE p.34: bonus action — ranged kensei weapon attacks this
turn deal an extra 1d4 damage of the weapon's type, until the end
of the turn. No ki.

v1 announce-only — the actual on-hit damage application is
GM-tracked. The 1d4 is rolled server-side. Bonus chip.

Kael Brightleaf (Monk, PATCHed to Way of the Kensei Lv 7) is the
demo fixture.

Tests:
  - Lv 7 happy: bonus_damage in [1,4], 1d4 dice, broadcast fires.
  - Wrong subclass (default Way of the Open Hand) → 409.
  - Wrong class (Caelan paladin) → 409.
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


def _ks_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "kensei-shot"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def kael_kensei(gm_client, roster):
    """PATCH Kael to Way of the Kensei; restore to Way of the Open Hand."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(
        gm_client, kael["id"],
        {"subclass": "Way of the Kensei"},
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


async def test_use_ks_happy_lv7(
    gm_client, gm_ws, kael_kensei,
):
    """Lv 7 Way of the Kensei → +1d4 bonus damage in [1,4]."""
    kael = kael_kensei
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_kensei_shot",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "kensei-shot"
    assert data["damage_dice"] == "1d4"
    assert 1 <= data["bonus_damage"] <= 4
    assert data["monk_level"] == 7
    await asyncio.sleep(0.3)
    feats = _ks_broadcasts(gm_ws, kael["id"])
    assert feats
    assert feats[-1]["data"]["bonus_damage"] == data["bonus_damage"]


async def test_use_ks_wrong_subclass(
    gm_client, roster,
):
    """Default Kael (Way of the Open Hand) → 409."""
    kael = roster["Kael Brightleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_kensei_shot",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ks_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_kensei_shot",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_ks_installs_rider_and_lands(
    gm_client, gm_ws, kael_kensei,
):
    """v2.99.403 — Kensei's Shot installs a this-turn, non-target rider
    (+1d4 of the weapon's type), and the bonus lands on a /attack.

    The rider is NOT once-per-turn, so it isn't stripped on a miss — the
    auto_uplift assertion is deterministic (no retry loop needed). The
    uplift inherits the weapon's damage type (no stored type key).
    """
    kael = kael_kensei
    kael_cid = f"tok_ks_kael_{kael['id']}"
    dummy_cid = "tok_ks_dummy"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _mkc(kael_cid, kael["id"], name=kael["name"]),
            _mkc(dummy_cid, None, name="Dummy"),
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_kensei_shot",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["buff_installed"] is True

    bu = await gm_ws.wait_for("buff_update")
    ks = next((b for b in bu["data"]["buffs"]
               if b.get("key") == "kensei-shot"), None)
    assert ks is not None, bu["data"]["buffs"]
    eff = ks.get("effects") or {}
    assert eff.get("weapon_hit_bonus_dice") == "1d4"
    # Not once-per-turn, non-target: no flag, no stored target key.
    assert "weapon_hit_once_per_turn" not in eff
    assert "weapon_hit_bonus_target_combatant_id" not in eff
    # No stored damage type → the uplift inherits the weapon's type.
    assert "weapon_hit_bonus_damage_type" not in eff

    # Attack the dummy with Kael's (bludgeoning) Unarmed Strike. The rider
    # isn't once-per-turn, so its +1d4 uplift rides every swing — assert
    # it deterministically (it inherits the weapon's bludgeoning type).
    a = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": kael["id"], "attack_index": 0,
              "target_combatant_id": dummy_cid, "override": True},
    )
    assert a.status_code == 200, a.text
    ups = [u for u in (a.json().get("auto_uplifts") or [])
           if u.get("source") == "kensei-shot"]
    assert len(ups) == 1, a.json().get("auto_uplifts")
    assert ups[0]["expression"] == "1d4"
    assert ups[0]["damage_type"] == "bludgeoning"  # weapon's type
    assert 1 <= ups[0]["total"] <= 4
