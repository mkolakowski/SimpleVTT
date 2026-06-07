"""v2.99.216 — Foe Slayer (Ranger Lv 20).

Phase F.3 cont'd of the v2.99.193 phased completion plan. RAW
PHB p.92: "Once on each of your turns, you can add your Wisdom
modifier to the attack roll or the damage roll of an attack you
make against one of your favored enemies."

v1 ships announce-style. `/use_foe_slayer` validates Ranger Lv
20+ + computes the PC's WIS mod + broadcasts feature_used with
the mode (attack / damage) + bonus. The GM applies the bonus
manually. Per-turn tracking is filed; future commit would
extend /attack with a `foe_slayer_mode` body param that adds
the WIS mod automatically.

Tests:
  - Happy attack: Rowan Lv 20 → /use_foe_slayer mode=attack →
    broadcast with mode="attack" + wis_mod value.
  - Happy damage: mode=damage variant.
  - Gate: Rowan Lv 7 → 409 level_too_low.
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


def _fs_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "foe-slayer"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def rowan_lv20(gm_client, roster):
    """PATCH Rowan to Lv 20. Restore Lv 7 in teardown."""
    rowan = roster["Rowan Quickbow"]
    await _patch_sheet(
        gm_client, rowan["id"], {"level": 20},
        class_slug="ranger",
    )
    yield rowan
    await _patch_sheet(
        gm_client, rowan["id"], {"level": 7},
        class_slug="ranger",
    )


async def test_use_foe_slayer_attack_mode(
    gm_client, gm_ws, rowan_lv20,
):
    """Rowan Lv 20 → /use_foe_slayer attack mode → broadcast."""
    rowan = rowan_lv20
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_foe_slayer",
        json={
            "character_id": rowan["id"],
            "mode": "attack",
            "target": "Goblin Captain",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "attack"
    assert isinstance(data["wis_mod"], int)
    await asyncio.sleep(0.3)
    feats = _fs_broadcasts(gm_ws, rowan["id"])
    assert feats, (
        f"v2.99.216: expected feature_used(source=foe-slayer); "
        f"buffered={gm_ws.buffered()}"
    )
    feat_data = feats[-1].get("data") or {}
    assert feat_data.get("mode") == "attack"
    assert "attack roll" in (feat_data.get("feature_name") or "")
    assert "Goblin Captain" in (feat_data.get("feature_name") or "")


async def test_use_foe_slayer_damage_mode(
    gm_client, gm_ws, rowan_lv20,
):
    """Mode damage variant."""
    rowan = rowan_lv20
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_foe_slayer",
        json={
            "character_id": rowan["id"],
            "mode": "damage",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "damage"
    await asyncio.sleep(0.3)
    feats = _fs_broadcasts(gm_ws, rowan["id"])
    assert feats
    feat_data = feats[-1].get("data") or {}
    assert feat_data.get("mode") == "damage"
    assert "damage roll" in (feat_data.get("feature_name") or "")


async def test_use_foe_slayer_level_gate(
    gm_client, roster,
):
    """Control: Rowan at Lv 7 → 409 level_too_low."""
    rowan = roster["Rowan Quickbow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_foe_slayer",
        json={"character_id": rowan["id"], "mode": "attack"},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "level_too_low"
    assert data.get("required") == 20


def _mkc(cid, char_id, name="C"):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": 40, "hp_max": 40, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def test_foe_slayer_damage_installs_rider_and_lands(
    gm_client, gm_ws, rowan_lv20,
):
    """v2.99.460 — Foe Slayer mode=damage installs a non-target,
    once-per-turn flat rider (+WIS mod); the bonus lands on the first
    /attack hit."""
    rowan = rowan_lv20
    r_cid = f"tok_fs_r_{rowan['id']}"
    dummy_cid = "tok_fs_dummy"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _mkc(r_cid, rowan["id"], name=rowan["name"]),
            _mkc(dummy_cid, None, name="Dummy"),
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_foe_slayer",
        json={"character_id": rowan["id"], "mode": "damage"},
    )
    assert r.status_code == 200, r.text
    rd = r.json()
    assert rd["rider_installed"] is True
    wis = rd["wis_mod"]
    assert wis > 0

    bu = await gm_ws.wait_for("buff_update")
    fs = next((b for b in bu["data"]["buffs"]
               if b.get("key") == "foe-slayer"), None)
    assert fs is not None, bu["data"]["buffs"]
    eff = fs.get("effects") or {}
    assert eff.get("weapon_hit_bonus_flat") == wis
    assert eff.get("weapon_hit_once_per_turn") is True
    assert eff.get("weapon_hit_flag") == "foe_slayer"

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
    ups = [u for u in (hit_ad.get("auto_uplifts") or [])
           if u.get("source") == "foe-slayer"]
    assert len(ups) == 1, hit_ad.get("auto_uplifts")
    assert ups[0]["total"] == wis
