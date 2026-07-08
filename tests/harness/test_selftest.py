"""v2.972.0 — Admin Center demo self-test runner ("The Proving Ground").

The self-test lives on the Admin Center (port 8015, its own auth) — not the
8013 harness target — so this file has two layers, mirroring
``test_admin_center.py``:

  * Pure unit tests (host-side, no container) for the report model helpers:
    the roll-up tally recompute, node-status derivation, combatant
    construction, and the JSON-safety of ``run_status``.
  * One live end-to-end test (skips unless the admin-center is reachable AND
    admin tools + demo mode are on): trigger a run, poll to completion, and
    assert every demo campaign ran with a non-empty, error-free report.
"""
import json
import os
from pathlib import Path

import httpx
import pytest

from app.admin_center import selftest


# ── Pure unit tests (always run) ─────────────────────────────────────────────

def test_status_from_tally_precedence():
    assert selftest._status_from_tally({"passed": 0, "failed": 0, "error": 0, "skipped": 0, "total": 0}) == "pending"
    assert selftest._status_from_tally({"passed": 3, "failed": 0, "error": 0, "skipped": 0, "total": 3}) == "pass"
    assert selftest._status_from_tally({"passed": 2, "failed": 1, "error": 0, "skipped": 0, "total": 3}) == "fail"
    # error dominates fail
    assert selftest._status_from_tally({"passed": 1, "failed": 1, "error": 1, "skipped": 0, "total": 3}) == "error"


def test_recompute_rolls_up_nested_tree_and_totals():
    report = {
        "totals": selftest._empty_tally(),
        "campaigns": [{
            "campaign_id": 1, "name": "C1", "gm": "g", "map": "",
            "status": "running", "tally": {},
            "setup_checks": [
                selftest._check("reachability", "d", "e", "a", "pass"),
                selftest._check("movement", "d", "e", "a", "fail"),
            ],
            "rounds": [{
                "round": 1, "status": "running", "tally": {},
                "actors": [{
                    "actor": "Pip", "kind": "pc", "status": "running", "tally": {},
                    "checks": [selftest._check("pc_attack", "d", "e", "a", "error")],
                }],
            }],
            "teardown_checks": [selftest._check("restore", "d", "e", "a", "pass")],
        }],
    }
    selftest._recompute(report)
    camp = report["campaigns"][0]
    # 2 setup + 1 actor + 1 teardown = 4 checks
    assert camp["tally"] == {"passed": 2, "failed": 1, "error": 1, "skipped": 0, "total": 4}
    # error present anywhere in the campaign → campaign status error
    assert camp["status"] == "error"
    # actor + round roll-ups
    actor = camp["rounds"][0]["actors"][0]
    assert actor["tally"]["error"] == 1 and actor["status"] == "error"
    assert camp["rounds"][0]["tally"]["total"] == 1
    # report totals mirror the single campaign
    assert report["totals"] == camp["tally"]


def test_combatants_shape():
    heroes = [{"id": 10, "character_id": 5, "label": "Pip", "team": "hero"}]
    villains = [{"id": 20, "token_template_id": 7, "label": "Goblin", "team": "villain"}]
    combs = selftest._combatants(heroes, villains)
    assert len(combs) == 2
    h, v = combs
    assert h["char_id"] == 5 and "token_template_id" not in h  # PC: char_id, no template
    assert v["char_id"] is None and v["token_template_id"] == 7 and v["source_token_id"] == 20
    # deterministic descending initiative, heroes first
    assert h["initiative"] > v["initiative"]
    for c in combs:
        assert set(c["economy"]) == {"action", "bonus", "reaction", "movement"}


def test_run_status_is_json_safe_and_drops_private_keys():
    # Simulate a thread handle parked on the status (as start_run does).
    selftest._STATUS["_thread"] = object()
    try:
        s = selftest.run_status()
        assert "_thread" not in s
        json.dumps(s)  # must not raise
        assert set(s) >= {"state", "pct", "current", "report"}
    finally:
        selftest._STATUS.pop("_thread", None)


# ── Live end-to-end (skips unless reachable + enabled + demo) ─────────────────

ADMIN_BASE_URL = os.getenv("ADMIN_CENTER_BASE_URL", "http://localhost:8015")


def _env_file_value(key: str, default: str = "") -> str:
    val = default
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            s = line.strip()
            if s.startswith(f"{key}=") and not s.startswith("#"):
                val = s.split("=", 1)[1].strip() or val
    return os.getenv(key, val)


_AUTH = httpx.BasicAuth(
    _env_file_value("ADMIN_CENTER_USER", "admin"),
    _env_file_value("ADMIN_CENTER_PASS", "changeme"),
)


def _selftest_live() -> bool:
    """Reachable AND admin-tools enabled AND demo mode — else the run route is
    gated off (404 / redirect) and there's nothing to exercise."""
    try:
        r = httpx.get(f"{ADMIN_BASE_URL}/selftest/run-status", auth=_AUTH, timeout=3.0)
    except httpx.HTTPError:
        return False
    if r.status_code != 200:
        return False
    return r.json().get("state") != "disabled"


_LIVE = pytest.mark.skipif(
    not _selftest_live(),
    reason="admin-center /selftest not reachable/enabled (needs :8015 + ADMIN_CENTER_ADMIN_TOOLS + DEMO_MODE)",
)


@_LIVE
def test_selftest_run_to_completion_reports_all_campaigns():
    import time
    with httpx.Client(base_url=ADMIN_BASE_URL, auth=_AUTH, timeout=30.0) as c:
        # Start a run (tolerate an already-running one — just poll it).
        rr = c.post("/selftest/run")
        assert rr.status_code == 200, rr.text
        deadline = time.monotonic() + 90
        state, report = "running", None
        while time.monotonic() < deadline:
            s = c.get("/selftest/run-status").json()
            state, report = s.get("state"), s.get("report")
            if state in ("done", "error"):
                break
            time.sleep(1.0)
        assert state == "done", f"run did not finish: state={state}"
        assert report and report["campaigns"], "no campaigns in report"
        # Every campaign produced setup + teardown checks, and the roll-up totals
        # are internally consistent (no orphaned checks).
        totals = report["totals"]
        assert totals["total"] > 0
        summed = {"passed": 0, "failed": 0, "error": 0, "skipped": 0, "total": 0}
        setup_cats = set()
        for camp in report["campaigns"]:
            assert camp["setup_checks"], f"{camp['name']} ran no setup checks"
            for ch in camp["setup_checks"]:
                setup_cats.add(ch["category"])
            for k in summed:
                summed[k] += camp["tally"][k]
        assert summed == totals
        # Negative-path gate checks (driven as a non-GM player) ran.
        assert "gate" in setup_cats, f"no gate checks in setup: {setup_cats}"
        # A healthy stack should have no runner-level errors.
        assert totals["error"] == 0, f"self-test surfaced errors: {totals}"

        # Combat rounds (Phase 2): at least one campaign ran rounds with PC + NPC
        # actor nodes carrying attack + turn-advance checks.
        cats = set()
        kinds = set()
        rounds_seen = 0
        for camp in report["campaigns"]:
            for rnd in camp.get("rounds", []):
                rounds_seen += 1
                for actor in rnd.get("actors", []):
                    kinds.add(actor.get("kind"))
                    for ch in actor.get("checks", []):
                        cats.add(ch["category"])
        assert rounds_seen > 0, "no combat rounds were simulated"
        assert {"pc", "npc"} <= kinds, f"missing actor kinds: {kinds}"
        # PC attack + NPC attack + turn advance + a spell cast (casters cast a
        # leveled spell or fall back to a cantrip; non-casters record a skip).
        assert {"pc_attack", "npc_attack", "turn_advance", "spell_cast"} <= cats, \
            f"missing combat checks: {cats}"
