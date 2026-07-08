"""Admin-Center demo self-test runner.

Drives a live smoke test of the whole VTT game loop against each demo
campaign — token movement across the map + (Phase 2) a few combat rounds —
and records a nested, human-readable report the ``/selftest`` page renders.

Why this exists: the harness suite (``tests/harness/``) covers this ground
but only runs offline via ``scripts/run_harness.sh``; the Admin Center's
``/tests`` page merely *displays* the JSON those runs drop on disk. This
module gives an operator a one-click "does the whole game loop still work?"
button whose report streams in live.

How it works: exactly like the harness — it talks to the *main app* over
HTTP + WebSocket (the admin-center process is a separate container; the app
is reachable at ``SELFTEST_APP_URL``, default ``http://app:8013``). It logs
in as each campaign's demo GM (driving as GM bypasses the action-economy +
turn gates), snapshots token positions + battle state, runs its checks, then
restores the snapshot in a ``finally`` so repeated runs are non-destructive
on the live demo. ``httpx`` + ``websockets`` are production deps, so both are
available in this image.

The run happens on a background thread; ``run_status()`` exposes the growing
report (rebuilt as a JSON snapshot after every check) so the page can poll
and render the tree filling in mid-run.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import threading
import time
from datetime import datetime, timezone

import httpx
import websockets

log = logging.getLogger("simplevtt.admin_center.selftest")

# The main app's base URL, reachable from the admin-center container. In
# docker compose the app service is named ``app``; the localhost fallback
# keeps the runner usable outside docker (dev). APP_BASE_URL defaults to
# localhost which points at the admin-center container itself, so it is only
# a last resort here.
_APP_URL = os.getenv(
    "SELFTEST_APP_URL",
    os.getenv("APP_BASE_URL", "http://localhost:8013"),
).rstrip("/")

# All demo accounts share this password (see app/demo_seed.py DEMO_PASSWORD).
_DEMO_PASSWORD = "demopass"

# Grid reference: 70 px per 5 ft cell (Map.grid_size_px default). Used only to
# annotate the *expected* movement distance; the pass/fail check is grid-rule
# agnostic (asserts the token relocated + a broadcast with distance > 0).
_PX_PER_CELL = 70.0
_FT_PER_CELL = 5.0

_WS_TIMEOUT = float(os.getenv("SELFTEST_WS_TIMEOUT", "3.0"))

# ── Run state (single background run at a time) ──────────────────────────────
_LOCK = threading.Lock()
_STATUS: dict = {
    "state": "idle",      # idle | running | done | error
    "pct": 0,
    "current": "",
    "started": 0.0,
    "finished": 0.0,
    "report": None,
}


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Report model helpers ─────────────────────────────────────────────────────

def _check(category: str, description: str, expected: str,
           actual: str, status: str, detail: str = "") -> dict:
    """One leaf assertion. ``status`` ∈ pass | fail | error | skip."""
    return {
        "category": category,
        "description": description,
        "expected": expected,
        "actual": actual,
        "status": status,
        "detail": detail,
    }


def _empty_tally() -> dict:
    return {"passed": 0, "failed": 0, "error": 0, "skipped": 0, "total": 0}


def _tally_checks(checks: list, into: dict) -> None:
    for c in checks:
        into["total"] += 1
        s = c.get("status")
        if s == "pass":
            into["passed"] += 1
        elif s == "fail":
            into["failed"] += 1
        elif s == "error":
            into["error"] += 1
        elif s == "skip":
            into["skipped"] += 1


def _status_from_tally(t: dict) -> str:
    """Roll a tally up to a node status. Empty → pending (nothing run yet)."""
    if t["total"] == 0:
        return "pending"
    if t["error"]:
        return "error"
    if t["failed"]:
        return "fail"
    return "pass"


def _recompute(report: dict) -> None:
    """Recompute every node's tally + status and the report totals, bottom-up,
    so a partially-filled tree is always internally consistent for rendering."""
    totals = _empty_tally()
    for camp in report.get("campaigns", []):
        camp_t = _empty_tally()
        _tally_checks(camp.get("setup_checks", []), camp_t)
        for rnd in camp.get("rounds", []):
            rnd_t = _empty_tally()
            for actor in rnd.get("actors", []):
                a_t = _empty_tally()
                _tally_checks(actor.get("checks", []), a_t)
                actor["tally"] = a_t
                actor["status"] = _status_from_tally(a_t)
                for k in rnd_t:
                    rnd_t[k] += a_t[k]
            rnd["tally"] = rnd_t
            rnd["status"] = _status_from_tally(rnd_t)
            for k in camp_t:
                camp_t[k] += rnd_t[k]
        _tally_checks(camp.get("teardown_checks", []), camp_t)
        camp["tally"] = camp_t
        camp["status"] = _status_from_tally(camp_t)
        for k in totals:
            totals[k] += camp_t[k]
    report["totals"] = totals


def _publish(report: dict) -> None:
    """Snapshot the (mutable) report into _STATUS as an immutable JSON copy so a
    concurrently-polling request never observes a half-mutated dict."""
    _recompute(report)
    _STATUS["report"] = json.loads(json.dumps(report))


def run_status() -> dict:
    """The current run status + latest report snapshot (polled by the page).
    Drops private keys (e.g. the Thread handle) so the result is JSON-safe."""
    return {k: v for k, v in _STATUS.items() if not k.startswith("_")}


# ── Demo campaign discovery ──────────────────────────────────────────────────

def _demo_campaigns() -> list:
    """The demo campaigns (flagship + leveled showcase), each with its GM email,
    ordered as they seed. Empty when not a demo DB."""
    from ..database import SessionLocal
    from ..models import Campaign, User
    from ..demo_seed import DEMO_CAMPAIGN_NAME
    from .. import demo_campaigns as dc

    names = [DEMO_CAMPAIGN_NAME, *dc.campaign_names()]
    order = {n: i for i, n in enumerate(names)}
    db = SessionLocal()
    try:
        rows = db.query(Campaign).filter(Campaign.name.in_(names)).all()
        out = []
        for c in rows:
            gm = db.query(User).filter(User.id == c.gm_user_id).first()
            out.append({
                "id": c.id,
                "name": c.name,
                "gm_email": gm.email if gm else None,
                "archived": bool(c.is_archived),
            })
        out.sort(key=lambda r: order.get(r["name"], 999))
        return out
    finally:
        db.close()


# ── Minimal WS collector (local copy of the harness helper) ──────────────────

class _WSCollector:
    """Buffer a campaign's WS broadcasts so a check can wait for the one its
    HTTP action should have fired. ``mark()`` resets the cursor right before an
    action so only post-action broadcasts are considered."""

    def __init__(self, ws):
        self.ws = ws
        self.messages: list = []
        self._task = None
        self._closed = False
        self._cursor = 0

    async def start(self):
        self._task = asyncio.create_task(self._recv_loop())
        await asyncio.sleep(0.3)  # drain hub priming (battle_update, presence)
        self.mark()
        return self

    async def stop(self):
        self._closed = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _recv_loop(self):
        try:
            while not self._closed:
                raw = await self.ws.recv()
                try:
                    self.messages.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
        except (websockets.ConnectionClosed, asyncio.CancelledError):
            pass
        except Exception as e:  # noqa: BLE001
            log.debug("selftest WS recv error: %s", e)

    def mark(self):
        self._cursor = len(self.messages)

    def _since(self, msg_type=None):
        sl = self.messages[self._cursor:]
        return sl if msg_type is None else [m for m in sl if m.get("type") == msg_type]

    async def wait_for(self, msg_type: str, timeout: float = _WS_TIMEOUT):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            hits = self._since(msg_type)
            if hits:
                return hits[0]
            await asyncio.sleep(0.02)
        return None


async def _open_ws(client: httpx.AsyncClient, campaign_id: int):
    cookie_header = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
    ws_base = _APP_URL.replace("https://", "wss://").replace("http://", "ws://")
    return await websockets.connect(
        f"{ws_base}/ws/campaign/{campaign_id}",
        extra_headers={"Cookie": cookie_header},
    )


# ── Combatant construction ───────────────────────────────────────────────────

def _combatants(heroes: list, villains: list) -> list:
    """Build a deterministic initiative order (heroes first, descending) from
    the seeded tokens. Nominal HP so an auto-applied hit is observable as a
    drop regardless of the real sheet max."""
    combs = []
    init = 20
    for t in heroes:
        combs.append({
            "id": f"tok_stH_{t['id']}",
            "char_id": t.get("character_id"),
            "name": t.get("label") or "Hero",
            "initiative": init, "hp_current": 50, "hp_max": 50,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        })
        init -= 1
    for t in villains:
        combs.append({
            "id": f"tok_stV_{t['id']}",
            "char_id": None,
            "token_template_id": t.get("token_template_id"),
            "source_token_id": t["id"],
            "name": t.get("label") or "Villain",
            "initiative": init, "hp_current": 40, "hp_max": 40,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        })
        init -= 1
    return combs


# ── Per-campaign run ─────────────────────────────────────────────────────────

async def _run_campaign(camp: dict, node: dict, report: dict) -> None:
    cid = camp["id"]
    gm_email = camp["gm_email"]
    setup = node["setup_checks"]
    teardown = node["teardown_checks"]

    if not gm_email:
        setup.append(_check(
            "reachability", "Resolve the campaign GM account",
            "a demo GM email is on file", "no GM user found", "error"))
        _publish(report)
        return

    client = None
    ws = None
    collector = None
    moved: list = []          # (token_id, orig_x, orig_y) to restore
    battle_snapshot = None    # prior battle state to restore

    try:
        # --- login as the campaign GM ---
        client = httpx.AsyncClient(base_url=_APP_URL, follow_redirects=True, timeout=20.0)
        r = await client.post("/login", data={"email": gm_email, "password": _DEMO_PASSWORD})
        if r.status_code not in (200, 303):
            setup.append(_check(
                "reachability", f"Log in as GM {gm_email}",
                "HTTP 200/303", f"HTTP {r.status_code}", "error"))
            _publish(report)
            return
        setup.append(_check(
            "reachability", f"Log in as GM {gm_email}",
            "HTTP 200/303 (session cookie set)", f"HTTP {r.status_code}", "pass"))
        _publish(report)

        # --- open the realtime WS ---
        try:
            ws = await _open_ws(client, cid)
            collector = await _WSCollector(ws).start()
        except Exception as e:  # noqa: BLE001
            setup.append(_check(
                "reachability", "Open the campaign WebSocket",
                "connection established", f"failed: {e}", "error"))

        # --- reachability: roster + tokens ---
        heroes, villains = [], []
        try:
            rr = await client.get(f"/api/campaign/{cid}/roster")
            tr = await client.get(f"/api/campaign/{cid}/tokens")
            roster = rr.json().get("characters", []) if rr.status_code == 200 else []
            tokens = tr.json().get("tokens", []) if tr.status_code == 200 else []
            heroes = [t for t in tokens if t.get("team") == "hero" and t.get("character_id")]
            villains = [t for t in tokens if t.get("team") == "villain"]
            node["map"] = f"{len(tokens)} tokens"
            ok = rr.status_code == 200 and tr.status_code == 200 and heroes and villains
            setup.append(_check(
                "reachability", "Fetch roster + map tokens",
                "HTTP 200, ≥1 hero and ≥1 villain token on the active map",
                f"roster={rr.status_code} ({len(roster)} chars), "
                f"tokens={tr.status_code} ({len(heroes)} hero / {len(villains)} villain)",
                "pass" if ok else "fail"))
        except Exception as e:  # noqa: BLE001
            setup.append(_check(
                "reachability", "Fetch roster + map tokens",
                "HTTP 200 with tokens", f"exception: {e}", "error"))
        _publish(report)

        # --- movement across the map ---
        if heroes:
            tok = heroes[0]
            tid = tok["id"]
            ox, oy = float(tok.get("x") or 0), float(tok.get("y") or 0)
            # Move ~2 cells along x, staying in-bounds by heading away from 0.
            delta = 2 * _PX_PER_CELL
            tx = ox - delta if ox > 300 else ox + delta
            ty = oy
            exp_ft = round(math.hypot(tx - ox, ty - oy) / _PX_PER_CELL * _FT_PER_CELL, 1)
            try:
                if collector:
                    collector.mark()
                mr = await client.post(
                    f"/api/campaign/{cid}/token/{tid}/move", json={"x": tx, "y": ty})
                moved.append((tid, ox, oy))
                bcast = await collector.wait_for("token_move") if collector else None
                # Confirm the DB position changed.
                tr2 = await client.get(f"/api/campaign/{cid}/tokens")
                now = next((t for t in tr2.json().get("tokens", []) if t["id"] == tid), None)
                relocated = now is not None and abs(float(now["x"]) - tx) < 1 and abs(float(now["y"]) - ty) < 1
                dist = (bcast or {}).get("data", {}).get("distance_ft")
                ok = mr.status_code == 200 and relocated and bcast is not None and (dist or 0) > 0
                actual = (
                    f"HTTP {mr.status_code}; token at ({now['x']:.0f},{now['y']:.0f}); "
                    f"token_move broadcast {'seen' if bcast else 'MISSING'}, distance_ft={dist}")
                setup.append(_check(
                    "movement",
                    f"Move {tok.get('label') or 'a hero'} across the map",
                    f"HTTP 200, token relocates to ({tx:.0f},{ty:.0f}) (~{exp_ft} ft "
                    f"gridless), a token_move broadcast fires with distance_ft > 0",
                    actual, "pass" if ok else "fail",
                    f"from ({ox:.0f},{oy:.0f})"))
            except Exception as e:  # noqa: BLE001
                setup.append(_check(
                    "movement", "Move a hero token across the map",
                    "HTTP 200 + token_move broadcast", f"exception: {e}", "error"))
        else:
            setup.append(_check(
                "movement", "Move a hero token across the map",
                "a hero token to move", "no hero token found", "skip"))
        _publish(report)

        # --- start initiative (snapshot the prior battle first, to restore) ---
        if heroes and villains:
            try:
                gb = await client.get(f"/api/campaign/{cid}/battle")
                battle_snapshot = gb.json().get("battle") if gb.status_code == 200 else None
                combs = _combatants(heroes, villains)
                if collector:
                    collector.mark()
                pr = await client.put(
                    f"/api/campaign/{cid}/battle",
                    json={"combatants": combs, "turn_index": 0, "round": 1, "active": True})
                bcast = await collector.wait_for("battle_update") if collector else None
                gb2 = await client.get(f"/api/campaign/{cid}/battle")
                state = gb2.json().get("battle") if gb2.status_code == 200 else None
                active = bool(state and state.get("active"))
                ok = pr.status_code == 200 and pr.json().get("ok") and active and bcast is not None
                setup.append(_check(
                    "initiative", "Start initiative (PUT battle)",
                    "HTTP 200 {ok:true}, battle_update broadcast, battle now active "
                    f"with {len(combs)} combatants",
                    f"HTTP {pr.status_code} {pr.json()}, active={active}, "
                    f"battle_update {'seen' if bcast else 'MISSING'}",
                    "pass" if ok else "fail"))
                # stash combatants for Phase 2 combat on the node
                node["_combatants"] = combs
            except Exception as e:  # noqa: BLE001
                setup.append(_check(
                    "initiative", "Start initiative (PUT battle)",
                    "HTTP 200 + battle_update", f"exception: {e}", "error"))
        else:
            setup.append(_check(
                "initiative", "Start initiative (PUT battle)",
                "heroes and villains to seed combat",
                "insufficient tokens", "skip"))
        _publish(report)

    finally:
        # --- teardown: restore token positions + battle state ---
        if client is not None:
            try:
                for tid, ox, oy in moved:
                    await client.post(
                        f"/api/campaign/{cid}/token/{tid}/move", json={"x": ox, "y": oy})
                if battle_snapshot is not None:
                    await client.put(f"/api/campaign/{cid}/battle", json=battle_snapshot)
                else:
                    await client.put(
                        f"/api/campaign/{cid}/battle",
                        json={"combatants": [], "turn_index": 0, "round": 1, "active": False})
                teardown.append(_check(
                    "restore", "Restore token positions + battle state",
                    "tokens moved back and battle reset to its prepped state",
                    f"{len(moved)} token(s) restored; battle "
                    f"{'snapshot' if battle_snapshot is not None else 'cleared'}",
                    "pass"))
            except Exception as e:  # noqa: BLE001
                teardown.append(_check(
                    "restore", "Restore token positions + battle state",
                    "clean restore", f"exception: {e}", "error"))
            _publish(report)
        if collector is not None:
            await collector.stop()
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass
        if client is not None:
            await client.aclose()


async def _run_all() -> None:
    started = time.time()
    report = {
        "started_at": _iso(),
        "finished_at": None,
        "duration_s": 0.0,
        "app_url": _APP_URL,
        "state": "running",
        "totals": _empty_tally(),
        "campaigns": [],
    }
    _STATUS.update(state="running", pct=0, current="starting", started=started, finished=0.0)
    _publish(report)

    campaigns = _demo_campaigns()
    if not campaigns:
        _STATUS.update(state="error", current="no demo campaigns found")
        report["state"] = "error"
        _publish(report)
        return

    n = len(campaigns)
    for i, camp in enumerate(campaigns):
        _STATUS["current"] = camp["name"]
        node = {
            "campaign_id": camp["id"], "name": camp["name"], "gm": camp["gm_email"],
            "map": "", "status": "running", "tally": _empty_tally(),
            "setup_checks": [], "rounds": [], "teardown_checks": [],
        }
        report["campaigns"].append(node)
        _publish(report)
        try:
            await _run_campaign(camp, node, report)
        except Exception as e:  # noqa: BLE001
            node["setup_checks"].append(_check(
                "reachability", "Run campaign self-test",
                "campaign completes", f"unhandled exception: {e}", "error"))
        _STATUS["pct"] = int((i + 1) / n * 100)
        _publish(report)

    report["state"] = "done"
    report["finished_at"] = _iso()
    report["duration_s"] = round(time.time() - started, 1)
    _STATUS.update(state="done", pct=100, current="complete", finished=time.time())
    _publish(report)


def _worker() -> None:
    try:
        asyncio.run(_run_all())
    except Exception as e:  # noqa: BLE001
        log.exception("self-test run crashed")
        _STATUS.update(state="error", current=f"crashed: {e}")
    finally:
        with _LOCK:
            _STATUS["_thread"] = None


def start_run() -> bool:
    """Kick off a background run. Returns False if one is already in flight."""
    with _LOCK:
        if _STATUS.get("state") == "running":
            return False
        t = threading.Thread(target=_worker, name="selftest-runner", daemon=True)
        _STATUS["_thread"] = t
        _STATUS.update(state="running", pct=0, current="starting", report=None)
    t.start()
    return True
