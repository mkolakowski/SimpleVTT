"""v2.99.113 — /use_grapple auto-resolved contested check tests.

v2.99.112 shipped /use_grapple that always installed the grappled
buff (legacy v1 path: GM resolves the check externally + invokes
the endpoint when the grapple lands).

v2.99.113 adds optional `attacker_check_total` + `target_check_total`
body fields. When BOTH are supplied, the server compares them and
only installs the buff on grappler-win. RAW: grappler must strictly
beat the target — ties go to the target.

Tests:
  - grappler_won (attacker > target) → buff installs, outcome reported
  - target_won (attacker < target) → no buff, outcome reported
  - tie (attacker == target) → no buff (RAW strict), outcome "tie"
  - legacy mode (no totals) → buff installs, outcome "auto"
  - one total supplied + the other missing → legacy mode (both
    must be present to trigger auto-resolution)
  - bad totals (non-int) → 400 bad_check_totals
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


@pytest_asyncio.fixture
async def krieger_grapples_tavik(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]
    kr_tok = f"tok_grap_cc_kr_{krieger['id']}"
    tv_tok = f"tok_grap_cc_tv_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
        _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
    ])
    yield krieger, tavik, kr_tok, tv_tok


async def test_grappler_wins_installs_buff(gm_client, krieger_grapples_tavik):
    """attacker_check_total > target_check_total → grappler_won,
    buff installs.
    """
    krieger, tavik, _, tv_tok = krieger_grapples_tavik
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_grapple",
        json={
            "character_id": krieger["id"],
            "target_combatant_id": tv_tok,
            "attacker_check_total": 18,
            "target_check_total": 12,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outcome"] == "grappler_won", data
    assert data["installed"] is True
    assert data["attacker_check_total"] == 18
    assert data["target_check_total"] == 12


async def test_target_wins_no_buff(gm_client, krieger_grapples_tavik):
    """attacker_check_total < target_check_total → target_won,
    no buff.
    """
    krieger, tavik, _, tv_tok = krieger_grapples_tavik
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_grapple",
        json={
            "character_id": krieger["id"],
            "target_combatant_id": tv_tok,
            "attacker_check_total": 8,
            "target_check_total": 17,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outcome"] == "target_won", data
    assert data["installed"] is False
    # Confirm Tavik has no grappled buff.
    buffs_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/buffs",
    )
    buff_keys = {(b or {}).get("key") for b in buffs_resp.json().get("buffs") or []}
    assert "grappled" not in buff_keys, buff_keys


async def test_tie_target_wins(gm_client, krieger_grapples_tavik):
    """RAW: tie goes to target. outcome="tie", no buff."""
    krieger, tavik, _, tv_tok = krieger_grapples_tavik
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_grapple",
        json={
            "character_id": krieger["id"],
            "target_combatant_id": tv_tok,
            "attacker_check_total": 15,
            "target_check_total": 15,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outcome"] == "tie", data
    assert data["installed"] is False


async def test_legacy_mode_installs_unconditionally(
    gm_client, krieger_grapples_tavik,
):
    """No check totals → legacy v2.99.112 path, outcome="auto",
    buff always installs.
    """
    krieger, tavik, _, tv_tok = krieger_grapples_tavik
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
    assert data["outcome"] == "auto", data
    assert data["installed"] is True


async def test_one_total_only_falls_through_to_legacy(
    gm_client, krieger_grapples_tavik,
):
    """attacker total supplied but target missing → legacy mode."""
    krieger, tavik, _, tv_tok = krieger_grapples_tavik
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_grapple",
        json={
            "character_id": krieger["id"],
            "target_combatant_id": tv_tok,
            "attacker_check_total": 20,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outcome"] == "auto", data
    assert data["installed"] is True


async def test_bad_totals_return_400(gm_client, krieger_grapples_tavik):
    """Non-int totals → 400 bad_check_totals."""
    krieger, tavik, _, tv_tok = krieger_grapples_tavik
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_grapple",
        json={
            "character_id": krieger["id"],
            "target_combatant_id": tv_tok,
            "attacker_check_total": "not a number",
            "target_check_total": "also not",
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text
    data = resp.json()
    assert data["error"] == "bad_check_totals"
