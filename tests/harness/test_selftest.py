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


def test_load_run_rejects_bad_ids(tmp_path, monkeypatch):
    # Path-traversal / junk ids never resolve, and a clean id round-trips.
    monkeypatch.setattr(selftest, "_RESULTS_DIR", tmp_path)
    assert selftest.load_run("../../etc/passwd") is None
    assert selftest.load_run("nope/../x") is None
    assert selftest.load_run("") is None
    assert selftest.load_run("does-not-exist") is None
    (tmp_path / "selftest-20260101T000000Z.json").write_text('{"totals": {"total": 3}}')
    got = selftest.load_run("20260101T000000Z")
    assert got and got["totals"]["total"] == 3


def test_video_path_validation(tmp_path, monkeypatch):
    # Only well-formed selftest-vid-*.webm names that exist resolve; traversal
    # and junk are refused.
    monkeypatch.setattr(selftest, "_VID_DIR", tmp_path)
    assert selftest.video_path("../secret.webm") is None
    assert selftest.video_path("evil.webm") is None            # wrong prefix
    assert selftest.video_path("selftest-vid-x.mp4") is None    # wrong ext
    assert selftest.video_path("selftest-vid-x.webm") is None   # not a file yet
    (tmp_path / "selftest-vid-run1-2.webm").write_bytes(b"webm")
    got = selftest.video_path("selftest-vid-run1-2.webm")
    assert got is not None and got.name == "selftest-vid-run1-2.webm"


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
        deadline = time.monotonic() + 240  # watchable pacing makes a full run longer
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
        # Door open/close ran (pass where a door exists, skip otherwise).
        assert "door" in setup_cats, f"no door checks in setup: {setup_cats}"

        # Run history: the completed run was archived and is reopenable, and the
        # id guard rejects traversal.
        hist = c.get("/selftest/history").json().get("runs", [])
        assert hist, "run history is empty after a completed run"
        newest = hist[0]["id"]
        reopened = c.get(f"/selftest/history/{newest}")
        assert reopened.status_code == 200
        assert reopened.json().get("campaigns"), "reopened run has no campaigns"
        assert c.get("/selftest/history/..%2f..%2fetc").status_code == 404
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


@_LIVE
def test_selftest_movement_only_subset():
    """A phase subset (movement only) runs just that phase: no combat rounds, and
    setup checks limited to reachability + movement. Scope is recorded."""
    import time
    with httpx.Client(base_url=ADMIN_BASE_URL, auth=_AUTH, timeout=30.0) as c:
        assert c.post("/selftest/run", json={"phases": ["movement"]}).status_code == 200
        deadline = time.monotonic() + 60
        state, report = "running", None
        while time.monotonic() < deadline:
            s = c.get("/selftest/run-status").json()
            state, report = s.get("state"), s.get("report")
            if state in ("done", "error"):
                break
            time.sleep(1.0)
        assert state == "done", f"subset run did not finish: {state}"
        assert report["scope"]["phases"] == ["movement"]
        assert report["scope"]["slow"] is False
        assert report.get("stats_note") is not None  # purge note always set
        for camp in report["campaigns"]:
            assert not camp["rounds"], f"{camp['name']} ran combat despite movement-only"
            cats = {ch["category"] for ch in camp["setup_checks"]}
            assert cats <= {"reachability", "movement"}, f"unexpected setup checks: {cats}"


@_LIVE
def test_selftest_slow_flag_and_stats_note():
    """A slow run is flagged in scope (slow + a larger step_delay) and every run
    records a stats-purge note so it doesn't skew campaign time stats. Uses the
    gates phase so the run stays quick even in slow mode."""
    import time
    with httpx.Client(base_url=ADMIN_BASE_URL, auth=_AUTH, timeout=30.0) as c:
        assert c.post("/selftest/run", json={"phases": ["gates"], "slow": True}).status_code == 200
        deadline = time.monotonic() + 120
        state, report = "running", None
        while time.monotonic() < deadline:
            s = c.get("/selftest/run-status").json()
            state, report = s.get("state"), s.get("report")
            if state in ("done", "error"):
                break
            time.sleep(1.0)
        assert state == "done", f"slow run did not finish: {state}"
        assert report["scope"]["slow"] is True
        assert report["scope"]["step_delay"] >= 1.0
        assert report.get("stats_note"), "no stats-purge note recorded"


@_LIVE
def test_selftest_reseed_flagship_skipped_and_validation():
    """Reseed endpoint: the flagship (id 1) is refused per-campaign (non-
    destructive — nothing is wiped), and an empty request is a 400."""
    with httpx.Client(base_url=ADMIN_BASE_URL, auth=_AUTH, timeout=30.0) as c:
        r = c.post("/selftest/reseed", json={"campaigns": [1]})
        assert r.status_code == 200, r.text
        res = r.json().get("results")
        assert res and res[0]["ok"] is False and "leveled" in res[0]["error"]
        assert c.post("/selftest/reseed", json={}).status_code == 400


@_LIVE
def test_selftest_video_capture():
    """A recorded run flags scope.record and, when the headless browser is
    available, produces a per-campaign .webm that serves (playback) and is
    traversal-guarded. Skips the video assertion if recording is unavailable."""
    import time

    def _wait(c, deadline_s):
        deadline = time.monotonic() + deadline_s
        state, report = "running", None
        while time.monotonic() < deadline:
            s = c.get("/selftest/run-status").json()
            state, report = s.get("state"), s.get("report")
            if state in ("done", "error"):
                break
            time.sleep(1.0)
        return state, report

    with httpx.Client(base_url=ADMIN_BASE_URL, auth=_AUTH, timeout=30.0) as c:
        # Discover a leveled campaign id (flagship is id 1).
        c.post("/selftest/run", json={"phases": ["movement"]})
        st, rep = _wait(c, 90)
        assert st == "done"
        cid = next(x["campaign_id"] for x in rep["campaigns"] if x["campaign_id"] != 1)
        # Recorded movement run on that one campaign.
        assert c.post("/selftest/run", json={
            "campaigns": [cid], "phases": ["movement"], "record": True}).status_code == 200
        st, rep = _wait(c, 150)
        assert st == "done"
        assert rep["scope"]["record"] is True
        vids = [x.get("video") for x in rep["campaigns"] if x.get("video")]
        if not vids:
            import pytest as _pt
            _pt.skip("no video produced (headless browser unavailable on this stack)")
        v = vids[0]
        r = c.get(f"/selftest/video/{v}")
        assert r.status_code == 200 and "webm" in r.headers.get("content-type", "")
        assert int(r.headers.get("content-length", "0")) > 0
        assert c.get("/selftest/video/..%2f..%2fpasswd").status_code == 404


@_LIVE
def test_selftest_deep_phases():
    """The Rules deep-dive tier runs its phases as a separate deep_checks group
    (not combat rounds) and restores cleanly. Covers the implemented phases;
    extend the phases list + assertions as more land."""
    import time
    with httpx.Client(base_url=ADMIN_BASE_URL, auth=_AUTH, timeout=30.0) as c:
        # Pick a leveled campaign with a healer (L3 Goblin Warrens has a Cleric).
        c.post("/selftest/run", json={"phases": ["movement"]})
        deadline = time.monotonic() + 90
        rep = None
        while time.monotonic() < deadline:
            s = c.get("/selftest/run-status").json()
            if s.get("state") in ("done", "error"):
                rep = s.get("report")
                break
            time.sleep(1.0)
        cid = next(x["campaign_id"] for x in rep["campaigns"] if x["campaign_id"] != 1)
        assert c.post("/selftest/run", json={
            "campaigns": [cid], "phases": ["rest", "heal", "death_saves", "concentration", "reactions", "saves", "features", "undo"]}).status_code == 200
        deadline = time.monotonic() + 120
        state, rep = "running", None
        while time.monotonic() < deadline:
            s = c.get("/selftest/run-status").json()
            state, rep = s.get("state"), s.get("report")
            if state in ("done", "error"):
                break
            time.sleep(1.0)
        assert state == "done"
        camp = rep["campaigns"][0]
        assert not camp["rounds"], "deep-only should not run combat rounds"
        cats = {ch["category"] for ch in camp["deep_checks"]}
        assert {"rest", "heal", "death_save", "concentration", "reaction", "save", "feature", "undo"} <= cats, f"missing deep checks: {cats}"
        # No runner errors (individual checks may skip where inapplicable).
        assert rep["totals"]["error"] == 0


@_LIVE
def test_selftest_doors_subset():
    """A doors-only subset opens/closes doors: every campaign records a door
    check (pass where a door exists, skip otherwise) and no combat runs."""
    import time
    with httpx.Client(base_url=ADMIN_BASE_URL, auth=_AUTH, timeout=30.0) as c:
        assert c.post("/selftest/run", json={"phases": ["doors"]}).status_code == 200
        deadline = time.monotonic() + 120
        state, report = "running", None
        while time.monotonic() < deadline:
            s = c.get("/selftest/run-status").json()
            state, report = s.get("state"), s.get("report")
            if state in ("done", "error"):
                break
            time.sleep(1.0)
        assert state == "done", f"doors subset did not finish: {state}"
        assert report["scope"]["phases"] == ["doors"]
        for camp in report["campaigns"]:
            assert not camp["rounds"], f"{camp['name']} ran combat despite doors-only"
            cats = {ch["category"] for ch in camp["setup_checks"]}
            assert "door" in cats, f"{camp['name']} ran no door check: {cats}"
