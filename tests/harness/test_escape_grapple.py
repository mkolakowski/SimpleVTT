"""v2.99.114 — /escape_grapple endpoint tests.

Closes the v2.99.112-.113 Grapple loop: target uses an action +
STR (Athletics) or DEX (Acrobatics) check contested by the
grappler's STR (Athletics) check to break free.

Mirror of /use_grapple: optional `escapee_check_total` +
`grappler_check_total` body fields trigger auto-resolved contested
check; otherwise legacy "auto" path removes the buff
unconditionally. Action economy fires regardless of outcome.

Tests:
  - happy path (escapee_check > grappler_check) → buff removed
  - target_won → grappled buff still on Tavik
  - tie → still grappled (RAW: contesting party wins ties)
  - legacy mode (no totals) → buff removed unconditionally
  - 409 not_grappled when caller doesn't have the buff
  - 400 bad_check_totals when totals are non-numeric
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", speed_walk=30, buffs=None):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "speed_walk": speed_walk,
        "buffs": buffs or [],
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
async def tavik_grappled_by_krieger(gm_client, roster):
    """Set up: Krieger grapples Tavik via /use_grapple; now Tavik
    has the grappled buff. Yields (krieger, tavik, kr_tok, tv_tok).
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]
    kr_tok = f"tok_esc_kr_{krieger['id']}"
    tv_tok = f"tok_esc_tv_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
        _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
    ])
    grapple_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_grapple",
        json={
            "character_id": krieger["id"],
            "target_combatant_id": tv_tok,
            "override": True,
        },
    )
    assert grapple_resp.status_code == 200, grapple_resp.text
    yield krieger, tavik, kr_tok, tv_tok


async def _get_buff_keys(gm_client, char_id):
    buffs_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return {(b or {}).get("key") for b in buffs_resp.json().get("buffs") or []}


async def test_escapee_wins_removes_grappled_buff(
    gm_client, tavik_grappled_by_krieger,
):
    """Tavik rolls 18, Krieger rolls 12 → escapee_wins → grappled
    buff removed.
    """
    _, tavik, _, _ = tavik_grappled_by_krieger
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/escape_grapple",
        json={
            "character_id": tavik["id"],
            "escapee_check_total": 18,
            "grappler_check_total": 12,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outcome"] == "escaped", data
    assert data["removed"] is True
    # Buff gone.
    keys = await _get_buff_keys(gm_client, tavik["id"])
    assert "grappled" not in keys, keys


async def test_grappler_wins_buff_stays(
    gm_client, tavik_grappled_by_krieger,
):
    """Tavik rolls 8, Krieger rolls 17 → still_grappled, buff
    stays.
    """
    _, tavik, _, _ = tavik_grappled_by_krieger
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/escape_grapple",
        json={
            "character_id": tavik["id"],
            "escapee_check_total": 8,
            "grappler_check_total": 17,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outcome"] == "still_grappled", data
    assert data["removed"] is False
    keys = await _get_buff_keys(gm_client, tavik["id"])
    assert "grappled" in keys, keys


async def test_tie_grappler_wins_by_raw(
    gm_client, tavik_grappled_by_krieger,
):
    """Tied at 15 → grappler holds (RAW: contesting party wins
    ties). Outcome="tie", buff stays.
    """
    _, tavik, _, _ = tavik_grappled_by_krieger
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/escape_grapple",
        json={
            "character_id": tavik["id"],
            "escapee_check_total": 15,
            "grappler_check_total": 15,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outcome"] == "tie", data
    assert data["removed"] is False


async def test_legacy_mode_always_escapes(
    gm_client, tavik_grappled_by_krieger,
):
    """No check totals → legacy "auto" path, buff removed
    unconditionally.
    """
    _, tavik, _, _ = tavik_grappled_by_krieger
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/escape_grapple",
        json={
            "character_id": tavik["id"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["outcome"] == "auto", data
    assert data["removed"] is True
    keys = await _get_buff_keys(gm_client, tavik["id"])
    assert "grappled" not in keys, keys


async def test_not_grappled_returns_409(gm_client, roster):
    """If the caller isn't grappled → 409 not_grappled.
    Use Pip who's not in a grapple.
    """
    pip = roster["Pip Quickfingers"]
    # Seed Pip into battle but not grappled.
    pip_tok = f"tok_esc_ng_pip_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(pip_tok, pip["id"], name=pip["name"], speed_walk=30),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/escape_grapple",
        json={"character_id": pip["id"], "override": True},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data["error"] == "not_grappled"


async def test_bad_check_totals_return_400(
    gm_client, tavik_grappled_by_krieger,
):
    """Non-integer totals → 400 bad_check_totals."""
    _, tavik, _, _ = tavik_grappled_by_krieger
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/escape_grapple",
        json={
            "character_id": tavik["id"],
            "escapee_check_total": "not a number",
            "grappler_check_total": "also not",
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text
    data = resp.json()
    assert data["error"] == "bad_check_totals"
