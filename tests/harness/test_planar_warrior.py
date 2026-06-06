"""v2.99.382 — Horizon Walker Ranger: Planar Warrior (G Ranger conclave CLOSE, Lv 3+, XGE).

Phase G Ranger conclave subclass batch ship #7 — Horizon Walker
opens and CLOSES the Ranger conclave batch.
RAW XGE p.42: as a bonus action, mark a creature within 30 ft; the
next weapon hit this turn deals all its damage as force, plus an
extra 1d8 force (2d8 at Lv 11).

v2.99.400 — Phase 2.4 of docs/plans/on-hit-riders.md: when a
``target_combatant_id`` is supplied, the feature installs a
`planar-warrior` rider buff that auto-applies through the /attack
pipeline — `weapon_hit_bonus_dice: "{1|2}d8"` + force type (the extra
force damage) and the new `weapon_hit_convert_type: "force"` key
(re-types the whole hit's damage to force), gated
`weapon_hit_once_per_turn` and 1-round so it fires exactly once this
turn (RAW). Without a target it stays announce-only.

Rowan Quickbow (Ranger, PATCHed to Horizon Walker Lv 5) is the demo
fixture (1d8 below Lv 11). His Longbow (attack_index 0) is piercing,
so the conversion to force is observable.

Tests:
  - Lv 5 happy: +1d8 force in [1,8], range 30, converts to force.
  - Wrong subclass (default Hunter) → 409.
  - Wrong class (Caelan paladin) → 409.
  - v2.99.400: with a target, installs the rider buff + the /attack
    converts the Longbow's piercing damage to force and lands +1d8.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", ac=None):
    c = {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": 50, "hp_max": 50,
        "buffs": [], "speed_walk": 30,
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0},
    }
    if ac is not None:
        c["ac"] = ac
    return c


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _pw_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "planar-warrior"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def rowan_horizon(gm_client, roster):
    """PATCH Rowan to Horizon Walker; restore to Hunter on teardown."""
    rowan = roster["Rowan Quickbow"]
    await _patch_sheet(
        gm_client, rowan["id"],
        {"subclass": "Horizon Walker"},
        class_slug="ranger",
    )
    try:
        yield rowan
    finally:
        await _patch_sheet(
            gm_client, rowan["id"],
            {"subclass": "Hunter"},
            class_slug="ranger",
        )


async def test_use_pw_happy_lv5(
    gm_client, gm_ws, rowan_horizon,
):
    """Lv 5 Horizon Walker → +1d8 force in [1,8], range 30."""
    rowan = rowan_horizon
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_planar_warrior",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "planar-warrior"
    assert data["force_damage_dice"] == "1d8"
    assert 1 <= data["force_damage"] <= 8
    assert data["range_ft"] == 30
    assert data["converts_to_force"] is True
    assert data["ranger_level"] == 5
    await asyncio.sleep(0.3)
    feats = _pw_broadcasts(gm_ws, rowan["id"])
    assert feats
    assert feats[-1]["data"]["force_damage"] == data["force_damage"]


async def test_use_pw_wrong_subclass(
    gm_client, roster,
):
    """Default Rowan (Hunter) → 409."""
    rowan = roster["Rowan Quickbow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_planar_warrior",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_pw_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_planar_warrior",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_pw_installs_rider_and_converts(
    gm_client, gm_ws, rowan_horizon,
):
    """v2.99.400 — Phase 2.4: with a target, Planar Warrior installs the
    rider buff (force conversion + extra 1d8 force) and a /attack vs the
    marked target re-types the Longbow's piercing damage to force and
    lands the +1d8 force uplift.

    AC 1 on the dummy guarantees the hit, so the once-per-turn rider
    fires deterministically (not stripped on a miss).
    """
    rowan = rowan_horizon
    rowan_cid = f"tok_pw_rowan_{rowan['id']}"
    dummy_cid = "tok_pw_dummy"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
            _mkc(dummy_cid, None, name="Dummy", ac=1),
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_planar_warrior",
        json={"character_id": rowan["id"],
              "target_combatant_id": dummy_cid, "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["buff_installed"] is True
    assert data["target_combatant_id"] == dummy_cid

    bu = await gm_ws.wait_for("buff_update")
    pw = next((b for b in bu["data"]["buffs"]
               if b.get("key") == "planar-warrior"), None)
    assert pw is not None, bu["data"]["buffs"]
    eff = pw.get("effects") or {}
    assert eff.get("weapon_hit_convert_type") == "force"
    assert eff.get("weapon_hit_bonus_dice") == "1d8"  # Lv 5 → 1d8
    assert eff.get("weapon_hit_bonus_damage_type") == "force"
    assert eff.get("weapon_hit_bonus_target_combatant_id") == dummy_cid
    assert eff.get("weapon_hit_once_per_turn") is True
    assert eff.get("weapon_hit_flag") == "planar_warrior"

    # Attack the marked target with the (piercing) Longbow. The
    # conversion + once-per-turn rider only fire on a confirmed hit, and
    # misses neither convert nor burn the rider — so retry until a swing
    # connects (Rowan is +7 vs the dummy's default AC 10). The buff is
    # 1-round, so it survives every same-turn swing until the first hit.
    hit_ad = None
    for _ in range(12):
        a = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": rowan["id"], "attack_index": 0,
                  "target_combatant_id": dummy_cid, "override": True},
        )
        assert a.status_code == 200, a.text
        ad = a.json()
        if ad["hit"]:
            hit_ad = ad
            break
    assert hit_ad is not None, "expected at least one hit in 12 swings"

    # The whole hit's damage is re-typed from piercing to force.
    assert hit_ad["damage_type"] == "force", hit_ad
    # ...and the extra +1d8 force rider lands as a force uplift.
    ups = [u for u in (hit_ad.get("auto_uplifts") or [])
           if u.get("source") == "planar-warrior"]
    assert len(ups) == 1, hit_ad.get("auto_uplifts")
    assert ups[0]["expression"] == "1d8"
    assert ups[0]["damage_type"] == "force"
    assert 1 <= ups[0]["total"] <= 8
