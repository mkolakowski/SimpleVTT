"""v2.99.112 — /use_grapple endpoint tests.

Sixth speed-engine consumer (after Lance of Lethargy, Slow, Web,
Hold Person, Hold Monster). New `_make_grappled_buff` factory
mirrors v2.99.106's Restrained pattern but with the canonical
Grappled raw_effects (no attack-roll modifiers, ends if grappler
incapacitated). Buff key is `"grappled"`.

v1 ships the mechanical install + audit broadcast; the contested
STR (Athletics) check is the GM's responsibility today.

Tests:
  - happy path: Krieger grapples Tavik → grappled buff installs
    on Tavik with speed_reduction_ft = base + key="grappled"
  - missing target → 404 (with target_not_found error)
  - missing character_id → 400
  - WS audit broadcast carries `source: grapple-action`
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", speed_walk=30):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "speed_walk": speed_walk,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def test_grapple_installs_grappled_buff(gm_client, gm_ws, roster):
    """Krieger (Barbarian) grapples Tavik. The grappled buff installs
    on Tavik with speed_reduction_ft = 30 (Tavik's base speed_walk)
    and key="grappled".
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]
    kr_tok = f"tok_grap_kr_{krieger['id']}"
    tv_tok = f"tok_grap_tv_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
        _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
    ])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_grapple",
        json={
            "character_id": krieger["id"],
            "target_combatant_id": tv_tok,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["grappler_character_id"] == krieger["id"]
    assert data["target_combatant_id"] == tv_tok
    assert data["base_speed_walk"] == 30
    assert data["speed_reduction_ft"] == 30
    assert data["installed"] is True
    assert data["duration_rounds"] == 10
    # Verify the buff is on Tavik.
    buffs_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/buffs",
    )
    buffs = buffs_resp.json().get("buffs") or []
    grappled = next((b for b in buffs if b.get("key") == "grappled"), None)
    assert grappled is not None, f"no grappled buff; got {buffs}"
    assert grappled.get("source") == "grapple-action"
    assert grappled["effects"]["speed_reduction_ft"] == 30


async def test_grapple_missing_target_returns_404(gm_client, roster):
    """Bogus target_combatant_id → 404 target_not_found."""
    krieger = roster["Krieger Stonefist"]
    # Seed battle with just Krieger so the target lookup fails.
    kr_tok = f"tok_grap_404_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_grapple",
        json={
            "character_id": krieger["id"],
            "target_combatant_id": "bogus_tok_id",
            "override": True,
        },
    )
    assert resp.status_code == 404, resp.text
    data = resp.json()
    assert data["error"] == "target_not_found"


async def test_grapple_missing_character_id_returns_400(gm_client, roster):
    """Missing character_id → 400."""
    tavik = roster["Brother Tavik Stonebrow"]
    tv_tok = f"tok_grap_400_tv_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_grapple",
        json={"target_combatant_id": tv_tok},
    )
    assert resp.status_code == 400, resp.text


async def test_grapple_broadcasts_feature_used_audit(
    gm_client, gm_ws, roster,
):
    """The grapple broadcasts a feature_used with source=
    grapple-action carrying target_combatant_id + target_name.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]
    kr_tok = f"tok_grap_audit_kr_{krieger['id']}"
    tv_tok = f"tok_grap_audit_tv_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
        _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
    ])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_grapple",
        json={
            "character_id": krieger["id"],
            "target_combatant_id": tv_tok,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # Find the feature_used broadcast.
    msg = await gm_ws.wait_for("feature_used")
    bd = msg["data"]
    assert bd["source"] == "grapple-action"
    assert bd["character_id"] == krieger["id"]
    assert bd["target_combatant_id"] == tv_tok
    assert bd["target_name"] == tavik["name"]
    assert bd["speed_reduction_ft"] == 30
