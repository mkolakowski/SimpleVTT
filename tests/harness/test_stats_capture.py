"""v2.650.0 — per-campaign statistics capture, Phase 1 (Hook A).

The stats event log (`campaign_stat_events`) is written best-effort from
the damage funnel `_apply_damage_to_combatant`. This commit ships the
schema + the damage hook; the read API + page land in later phases, so
this test verifies the capture by querying the DB directly (the
`docker compose exec db psql` precedent from `test_ws_disabled_user.py`)
rather than through an endpoint that doesn't exist yet.

Coverage:
  - A PC's weapon hit against an NPC inserts a `damage_dealt` stat row
    for that PC (baseline-delta so prior tests' rows don't matter).
  - The attack endpoint still succeeds (no regression from the hook).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import httpx
import pytest

from .conftest import CAMPAIGN_ID

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PG_USER = "simplevtt"
_PG_DB = "simplevtt"


def _app_up() -> bool:
    try:
        return httpx.get(
            "http://localhost:8013/healthz", timeout=3.0
        ).status_code == 200
    except httpx.HTTPError:
        return False


def _psql(sql: str) -> str | None:
    try:
        r = subprocess.run(
            ["docker", "compose", "exec", "-T", "db",
             "psql", "-U", _PG_USER, "-d", _PG_DB, "-tA", "-c", sql],
            cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()


_SKIP = pytest.mark.skipif(not _app_up(), reason="app not reachable on :8013")


def _damage_dealt_count(actor_char_id: int) -> int | None:
    out = _psql(
        f"SELECT count(*) FROM campaign_stat_events "
        f"WHERE campaign_id={CAMPAIGN_ID} AND actor_char_id={actor_char_id} "
        f"AND event_type='damage_dealt' AND amount > 0"
    )
    if out is None:
        return None
    try:
        return int(out)
    except ValueError:
        return None


@_SKIP
async def test_pc_hit_on_npc_logs_damage_dealt(gm_client, roster):
    garrik = roster["Garrik Ironside"]
    # Require the DB query path (the read API doesn't exist yet).
    base = _damage_dealt_count(garrik["id"])
    if base is None:
        pytest.skip("db not reachable via docker compose exec (non-demo stack)")

    npc_cid = "tok_stat_dummy"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_stat_g_{garrik['id']}", "char_id": garrik["id"],
             "name": garrik["name"], "initiative": 12,
             "hp_current": 85, "hp_max": 85, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": npc_cid, "char_id": None, "name": "Training Dummy",
             "initiative": 1, "hp_current": 200, "hp_max": 200, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )

    # Land at least one hit so damage is applied (auto-apply is on in the
    # demo campaign).
    hit = False
    for _ in range(20):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": garrik["id"],
                "attack_index": 0,
                "target_combatant_id": npc_cid,
                "override": True,
                "override_range": True,
            },
        )
        assert r.status_code == 200, r.text  # no regression from the hook
        if r.json().get("hit") and (r.json().get("damage_applied") or 0) > 0:
            hit = True
            break
    assert hit, "Garrik never landed a damaging hit on the dummy in 20 swings"

    after = _damage_dealt_count(garrik["id"])
    assert after is not None
    assert after > base, (
        f"expected a new damage_dealt stat row for Garrik; "
        f"baseline={base} after={after}"
    )
