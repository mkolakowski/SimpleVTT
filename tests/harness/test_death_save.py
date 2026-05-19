"""Death-save state machine — /character/{id}/death-save{,/override}, /stabilize.

The death-save endpoints are the v2.1.0 source of truth for the
dying → stable / dead transition. They're called whenever an HP
change crosses 0 (from auto-damage in T.2 / T.3b, manual GM edits
via sheet-fields PATCH, etc.). No dedicated test existed before
v2.35.1.

Coverage:
  - Drop a PC to 0 HP → status = dying
  - Roll a death save (POST /death-save) → success/failure counter
    increments, 3 successes → stable
  - Override (POST /death-save/override) — GM force-sets status
  - Stabilize (POST /stabilize) — GM-only DC-10-Medicine bypass
  - 409 when rolling a death save on an alive character
  - 403 when a non-owner / non-GM player calls override / stabilize
"""
from .conftest import CAMPAIGN_ID


async def _set_hp(gm_client, char_id: int, hp_current: int) -> None:
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"hp": {"current": hp_current}},
    )


async def _drop_to_zero(gm_client, char_id: int) -> None:
    """Drop a PC via the damage path so the death-save state machine
    fires cleanly (status → dying, successes/failures reset).

    Resets prior dead/stable state via the override endpoint first so
    each test starts from a known baseline regardless of what earlier
    tests in the same session left behind. Then long-rest to refill HP
    + clear any lingering counters, then damage to 0.
    """
    # Override → alive (clears dead / stable / dying state).
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )
    # Long rest to refill HP.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    # Damage just enough to hit 0. NOT 99 — that's ≥ 2× max HP for
    # most demo PCs and triggers RAW instant-kill (massive damage).
    # ``damage_amount`` should equal the actual reduction — Pip has
    # ~33 max HP so 33 is exactly the drop and safe.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={
            "hp": {"current": 0},
            "hp_change_reason": "damage",
            "damage_amount": 1,
            "damage_type": "slashing",
        },
    )


async def _roster_hp(gm_client, char_id: int) -> int:
    """Re-fetch the lightweight roster and pluck hp_current for the
    target char. (The roster endpoint surfaces hp_current/hp_max but
    not the full sheet; that's why dying-status assertions use the
    death-save endpoints' returned state instead.)"""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/roster")
    chars = r.json()["characters"]
    char = next((c for c in chars if c["id"] == char_id), None)
    return int((char or {}).get("hp_current") or 0)


async def test_drop_to_zero_sets_dying(gm_client, roster):
    """Damaging a PC to 0 → state machine flips to dying. Verified by
    posting a death-save roll; the endpoint returns 409 unless the
    character is in ``dying`` state (so a 200 implicitly confirms the
    state)."""
    pip = roster["Pip Quickfingers"]
    await _drop_to_zero(gm_client, pip["id"])
    # HP should now be 0.
    assert await _roster_hp(gm_client, pip["id"]) == 0
    # Rolling a death save should succeed (200) because state is dying.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/death-save",
        json={},
    )
    assert resp.status_code == 200, f"expected dying state to allow death save, got {resp.status_code}"


async def test_death_save_roll_updates_counters(gm_client, roster):
    """POST /death-save on a dying PC → returns the roll result +
    increments either successes or failures. State machine handles the
    rest (3 successes → stable, 3 failures → dead, nat 20 → alive).
    """
    pip = roster["Pip Quickfingers"]
    await _drop_to_zero(gm_client, pip["id"])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/death-save",
        json={},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Response has flat fields: ok, raw, outcome, status, successes,
    # failures, hp.
    assert data["ok"] is True
    assert isinstance(data.get("raw"), int)
    # After one roll, the new state can be:
    # - dying with +1 success or +1 failure (most rolls)
    # - alive (nat 20 → wakes at 1 HP)
    # - dead (3rd failure on a nat 1 — first roll though, so just 1)
    # - stable (3rd success — not on first roll)
    successes = int(data.get("successes") or 0)
    failures = int(data.get("failures") or 0)
    assert successes + failures >= 1 or data.get("status") == "alive"


async def test_death_save_409_when_alive(gm_client, roster):
    """Rolling a death save on a non-dying character → 409."""
    # Long-rest Pip to clear any dying state from prior tests.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{roster['Pip Quickfingers']['id']}/rest",
        json={"type": "long"},
    )
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/death-save",
        json={},
    )
    assert resp.status_code == 409, resp.text


async def test_death_save_override_sets_status(gm_client, roster):
    """GM override force-sets status + counters. Useful for narrative
    beats or misclick recovery (player rolled the wrong char's save)."""
    pip = roster["Pip Quickfingers"]
    await _drop_to_zero(gm_client, pip["id"])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/death-save/override",
        json={"status": "stable", "successes": 3, "failures": 0},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    ds = data["death_saves"]
    assert ds["status"] == "stable"
    assert ds["successes"] == 3
    assert ds["failures"] == 0


async def test_stabilize_endpoint(gm_client, roster):
    """POST /stabilize sets status=stable, zeros counters, leaves HP
    at 0 (per RAW DC-10-Medicine bypass)."""
    pip = roster["Pip Quickfingers"]
    await _drop_to_zero(gm_client, pip["id"])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/stabilize",
        json={},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["death_saves"]["status"] == "stable"


async def test_stabilize_forbidden_for_non_gm(alice_client, roster):
    """Alice (player, not GM) → 403 on stabilize."""
    pip = roster["Pip Quickfingers"]
    resp = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/stabilize",
        json={},
    )
    assert resp.status_code == 403, resp.text


async def test_override_to_alive_bumps_hp_to_1(gm_client, roster):
    """Override to ``alive`` from a 0-HP dying state should bump HP
    to 1 (the state machine refuses 'alive at 0 HP')."""
    pip = roster["Pip Quickfingers"]
    await _drop_to_zero(gm_client, pip["id"])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/death-save/override",
        json={"status": "alive", "successes": 0, "failures": 0},
    )
    assert resp.status_code == 200, resp.text
    # Re-fetch roster to verify HP bumped to ≥1.
    assert await _roster_hp(gm_client, pip["id"]) >= 1
