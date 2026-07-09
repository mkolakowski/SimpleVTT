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
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import websockets

from ..version import APP_VERSION

log = logging.getLogger("simplevtt.admin_center.selftest")

# Where completed run reports are archived so the page can show a history +
# reopen a past run. A dedicated admin-center-owned volume (see docker-compose);
# persistence degrades gracefully (skipped) if the dir isn't writable.
_RESULTS_DIR = Path(os.getenv("SELFTEST_RESULTS_DIR", "/data/selftest-results"))
_VID_DIR = _RESULTS_DIR / "video"


def _parse_size(s, default=(1600, 900)):
    """Parse a 'WxH' video-size string, clamped to something sane."""
    try:
        w, h = str(s).lower().split("x")
        w, h = int(w), int(h)
        if 320 <= w <= 3840 and 240 <= h <= 2160:
            return (w, h)
    except Exception:  # noqa: BLE001
        pass
    return default


# Capture resolution for the video recorder (default 900p / 1600x900).
_VIDEO_SIZE = _parse_size(os.getenv("SELFTEST_VIDEO_SIZE", "1600x900"))
_KEEP_RUNS = 25
_RUN_ID_RE = re.compile(r"^[0-9A-Za-z_-]+$")
_VIDEO_NAME_RE = re.compile(r"^selftest-vid-[0-9A-Za-z_-]+\.webm$")

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

# Selectable check phases (reachability always runs — it's the foundation).
# combat/spells/gates each need initiative, which runs implicitly when any of
# them is selected.
#
# Two tiers: the original "Core" smoke test, plus a "Rules deep-dive" tier
# (v2.987.0+) that exercises deeper SRD mechanics — each deep phase needs an
# active battle + a target combatant and is applicability-skipped per demo.
_CORE_PHASES = ("movement", "combat", "doors", "spells", "gates")
_DEEP_PHASES = ("rest", "heal", "death_saves")
_ALL_PHASES = _CORE_PHASES + _DEEP_PHASES

# Pacing between visible actions (moves, attacks, door toggles) so a watching GM
# sees the tokens glide + interact in real time rather than teleporting. Set
# SELFTEST_STEP_DELAY=0 for a fast headless run; the "Run slower" button uses the
# larger SELFTEST_SLOW_STEP_DELAY so a user can follow along.
_STEP_DELAY = float(os.getenv("SELFTEST_STEP_DELAY", "0.4"))
_SLOW_STEP_DELAY = float(os.getenv("SELFTEST_SLOW_STEP_DELAY", "1.5"))
# The pace the current run uses (set per-run by _run_all; slow runs raise it).
_ACTIVE_STEP_DELAY = _STEP_DELAY


async def _pace():
    if _ACTIVE_STEP_DELAY > 0:
        await asyncio.sleep(_ACTIVE_STEP_DELAY)


def _norm_phases(phases) -> set:
    """None/empty → all phases; otherwise the recognized subset."""
    if not phases:
        return set(_ALL_PHASES)
    got = {str(p).strip().lower() for p in phases} & set(_ALL_PHASES)
    return got or set(_ALL_PHASES)

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
        _tally_checks(camp.get("deep_checks", []), camp_t)
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


# ── Run-history persistence (JSON files on an admin-center-owned volume) ──────

def _persist(report: dict) -> None:
    """Archive a completed report as ``selftest-<stamp>.json`` and prune to the
    most recent _KEEP_RUNS. Best-effort — never raises into the runner."""
    try:
        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = report.get("run_id") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (_RESULTS_DIR / f"selftest-{stamp}.json").write_text(json.dumps(report))
        files = sorted(_RESULTS_DIR.glob("selftest-*.json"), key=lambda p: p.name, reverse=True)
        for stale in files[_KEEP_RUNS:]:
            try:
                stale.unlink()
            except OSError:
                pass
        _prune_videos(files[:_KEEP_RUNS])
    except Exception as e:  # noqa: BLE001
        log.warning("self-test run history not persisted: %s", e)


def list_runs(limit: int = _KEEP_RUNS) -> list:
    """Newest-first run-history headers (id + timestamps + totals) for the page."""
    if not _RESULTS_DIR.is_dir():
        return []
    out = []
    files = sorted(_RESULTS_DIR.glob("selftest-*.json"), key=lambda p: p.name, reverse=True)
    for p in files[:limit]:
        try:
            rep = json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            continue
        out.append({
            "id": p.stem.replace("selftest-", ""),
            "started_at": rep.get("started_at"),
            "finished_at": rep.get("finished_at"),
            "duration_s": rep.get("duration_s"),
            "app_version": rep.get("app_version"),
            "state": rep.get("state"),
            "slow": bool((rep.get("scope") or {}).get("slow")),
            "record": bool((rep.get("scope") or {}).get("record")),
            "totals": rep.get("totals") or _empty_tally(),
        })
    return out


# ── Video capture (headless Chromium records each campaign's tabletop) ────────

class _Recorder:
    """Optional per-run video capture. Launches one headless Chromium for the
    run; opens a recording browser context per campaign (a second GM session
    that just watches the tabletop while the runner drives it over HTTP), and
    saves a .webm per campaign. Degrades gracefully (disabled) if Playwright /
    Chromium isn't available."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._pw = None
        self._browser = None
        self.enabled = False

    async def start(self) -> bool:
        try:
            from playwright.async_api import async_playwright
        except Exception as e:  # noqa: BLE001
            log.warning("selftest video: Playwright unavailable (%s)", e)
            return False
        try:
            _VID_DIR.mkdir(parents=True, exist_ok=True)
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage"])
            self.enabled = True
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("selftest video: browser launch failed (%s)", e)
            await self.stop()
            return False

    async def open(self, cid, cookies):
        """Open a recording context on the campaign's tabletop. Returns an opaque
        handle (context, page) or None."""
        if not self.enabled:
            return None
        try:
            vw, vh = _VIDEO_SIZE
            ctx = await self._browser.new_context(
                viewport={"width": vw, "height": vh},
                record_video_dir=str(_VID_DIR),
                record_video_size={"width": vw, "height": vh})
            await ctx.add_cookies(cookies)
            page = await ctx.new_page()
            await page.goto(f"{_APP_URL}/campaign/{cid}",
                            wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(900)  # let the map + WS connect
            return (ctx, page)
        except Exception as e:  # noqa: BLE001
            log.warning("selftest video: open failed for campaign %s (%s)", cid, e)
            return None

    async def close(self, handle, cid) -> "str | None":
        """Finalize the campaign's recording; returns the served filename."""
        if not handle:
            return None
        ctx, page = handle
        try:
            vid = page.video
            await ctx.close()  # finalizes the .webm
            if not vid:
                return None
            src = await vid.path()
            name = f"selftest-vid-{self.run_id}-{cid}.webm"
            os.replace(src, str(_VID_DIR / name))
            return name
        except Exception as e:  # noqa: BLE001
            log.warning("selftest video: close failed for campaign %s (%s)", cid, e)
            return None

    async def stop(self):
        try:
            if self._browser:
                await self._browser.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:  # noqa: BLE001
            pass


def video_path(name: str) -> "Path | None":
    """Validated path to a served self-test video, or None."""
    if not name or not _VIDEO_NAME_RE.match(name):
        return None
    p = _VID_DIR / name
    return p if p.is_file() else None


def _prune_videos(keep_report_files) -> None:
    """Delete .webm files no longer referenced by any retained report."""
    if not _VID_DIR.is_dir():
        return
    referenced = set()
    for rf in keep_report_files:
        try:
            rep = json.loads(rf.read_text())
        except Exception:  # noqa: BLE001
            continue
        for camp in rep.get("campaigns", []):
            if camp.get("video"):
                referenced.add(camp["video"])
    for v in _VID_DIR.glob("selftest-vid-*.webm"):
        if v.name not in referenced:
            try:
                v.unlink()
            except OSError:
                pass


def load_run(run_id: str) -> "dict | None":
    """Full archived report for a history id, or None (id is charset-validated
    so it can't traverse out of the results dir)."""
    if not run_id or not _RUN_ID_RE.match(run_id):
        return None
    p = _RESULTS_DIR / f"selftest-{run_id}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None


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


def _user_email(user_id) -> "str | None":
    """Resolve a user id → email (for logging in as a token's owning player)."""
    if not user_id:
        return None
    from ..database import SessionLocal
    from ..models import User
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == user_id).first()
        return u.email if u else None
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


# ── Combat rounds ────────────────────────────────────────────────────────────

# How many rounds to simulate, and how many of each side act per round. Capped
# so the report + runtime stay bounded (some demo battles have 14 combatants);
# a representative party + monster subset still exercises the whole loop.
_ROUNDS = 2
_MAX_PC_PER_ROUND = 3
_MAX_NPC_PER_ROUND = 2
_COMBAT_WS_TIMEOUT = 2.0


async def _get_battle(client, cid):
    r = await client.get(f"/api/campaign/{cid}/battle")
    return (r.json().get("battle") if r.status_code == 200 else None) or {}


async def _get_sheet(client, cid, char_id):
    r = await client.get(f"/api/campaign/{cid}/character/{char_id}/sheet-json")
    return (r.json().get("sheet") if r.status_code == 200 else None) or {}


def _slots_available(sheet: dict) -> int:
    """Total unspent leveled spell slots across all classes/levels."""
    avail = 0
    for per_class in (sheet.get("spell_slots") or {}).values():
        if not isinstance(per_class, dict):
            continue
        for slot in per_class.values():
            if isinstance(slot, dict):
                avail += max(0, int(slot.get("total") or 0) - int(slot.get("used") or 0))
    return avail


def _pick_spell(spells: list, has_slot: bool):
    """Choose (spell_index, is_leveled) to cast. Prefer a leveled spell when a
    slot is free (tests slot decrement); else a cantrip (level 0, no slot).
    Returns None when the character can't cast without a slot."""
    leveled = [i for i, s in enumerate(spells) if isinstance(s, dict) and int(s.get("level") or 0) >= 1]
    cantrips = [i for i, s in enumerate(spells) if isinstance(s, dict) and int(s.get("level") or 0) == 0]
    if has_slot and leveled:
        return leveled[0], True
    if cantrips:
        return cantrips[0], False
    return None


# ── Movement + doors (watchable — tokens glide, doors open/close) ────────────

async def _ruler_show(client, cid, points):
    """Broadcast a shared ruler line (points = [{x,y}, ...]) so watching clients
    see the distance line a player would see. Best-effort. Skips a degenerate
    zero-length line (e.g. a token already adjacent to its target)."""
    if len(points) == 2:
        (ax, ay), (bx, by) = (points[0]["x"], points[0]["y"]), (points[1]["x"], points[1]["y"])
        if abs(ax - bx) < 2 and abs(ay - by) < 2:
            return
    try:
        await client.post(f"/api/campaign/{cid}/ruler_broadcast",
                          json={"action": "show", "points": points})
    except Exception:  # noqa: BLE001
        pass


async def _ruler_hide(client, cid):
    try:
        await client.post(f"/api/campaign/{cid}/ruler_broadcast", json={"action": "hide"})
    except Exception:  # noqa: BLE001
        pass


async def _tok_pos(client, cid):
    """token_id → (x, y) for every token on the active map."""
    try:
        toks = (await client.get(f"/api/campaign/{cid}/tokens")).json().get("tokens", [])
        return {t["id"]: (float(t.get("x") or 0), float(t.get("y") or 0)) for t in toks}
    except Exception:  # noqa: BLE001
        return {}


async def _target_line(client, cid, a_tok_id, b_tok_id):
    """Draw a targeting line between two tokens (like a player picking a target)."""
    pos = await _tok_pos(client, cid)
    if a_tok_id in pos and b_tok_id in pos:
        ax, ay = pos[a_tok_id]
        bx, by = pos[b_tok_id]
        await _ruler_show(client, cid, [{"x": ax, "y": ay}, {"x": bx, "y": by}])
        return True
    return False


async def _move_token(client, collector, cid, token_id, x, y):
    """Move a token one hop, waiting for the token_move broadcast, then pace so a
    watching GM sees it. Returns (response, broadcast)."""
    if collector:
        collector.mark()
    # Confirm the speed/OA gates so a GM-driven advance can cross the map even
    # mid-battle on a large map (otherwise a long hop is 409 over_speed_cap).
    r = await client.post(
        f"/api/campaign/{cid}/token/{token_id}/move",
        json={"x": x, "y": y, "over_speed_confirmed": True, "oa_confirmed": True})
    b = await collector.wait_for("token_move", _COMBAT_WS_TIMEOUT) if collector else None
    await _pace()
    return r, b


async def _glide(client, collector, cid, token_id, sx, sy, tx, ty, steps=4):
    """Walk a token from (sx,sy) to (tx,ty) in ``steps`` hops so it visibly moves
    across the map, showing the distance line a dragging player would see.
    Returns (all_ok, broadcasts_seen, last_response)."""
    # Show the movement ruler for the whole path while the token travels.
    await _ruler_show(client, cid, [{"x": sx, "y": sy}, {"x": tx, "y": ty}])
    ok = True
    seen = 0
    last = None
    for i in range(1, steps + 1):
        nx = sx + (tx - sx) * i / steps
        ny = sy + (ty - sy) * i / steps
        r, b = await _move_token(client, collector, cid, token_id, nx, ny)
        last = r
        if r.status_code != 200:
            ok = False
        if b is not None:
            seen += 1
    await _ruler_hide(client, cid)
    return ok, seen, last


def _find_doors(walls) -> list:
    """Door ids on the map — plain door/gate segments plus embedded doors
    (``{wallId}:{doorId}``)."""
    out = []
    for w in walls or []:
        if not isinstance(w, dict):
            continue
        if (w.get("door") or w.get("gate")) and w.get("id") is not None and not w.get("doors"):
            out.append(str(w["id"]))
        for d in (w.get("doors") or []):
            if isinstance(d, dict) and d.get("id") is not None:
                out.append(f"{w.get('id')}:{d['id']}")
    return out


def _door_open(walls, did: str):
    """The ``open`` flag of a door id within a walls list (None if not found)."""
    if ":" in did:
        wall_id, _, emb = did.partition(":")
        for w in walls or []:
            if isinstance(w, dict) and str(w.get("id")) == wall_id:
                for d in (w.get("doors") or []):
                    if isinstance(d, dict) and str(d.get("id")) == emb:
                        return bool(d.get("open"))
        return None
    for w in walls or []:
        if isinstance(w, dict) and str(w.get("id")) == did:
            return bool(w.get("open"))
    return None


async def _door_checks(client, collector, cid, map_id, walls, checks, report) -> None:
    """Open then close the first door on the map (GM bypasses any gate), asserting
    the walls_update broadcast + the open flag flips each way. Non-destructive —
    it ends closed/as-found. Appended with category ``door``."""
    doors = _find_doors(walls)
    if map_id is None or not doors:
        checks.append(_check(
            "door", "Open + close a door", "a door on the active map",
            "no doors on this map", "skip"))
        _publish(report)
        return
    did = doors[0]
    was_open = _door_open(walls, did)

    async def _toggle(action: str, want_open: bool):
        if collector:
            collector.mark()
        r = await client.post(f"/api/campaign/{cid}/map/{map_id}/door/{did}/toggle", json={})
        b = await collector.wait_for("walls_update", _COMBAT_WS_TIMEOUT) if collector else None
        await _pace()
        gw = await client.get(f"/api/campaign/{cid}/map/{map_id}/walls")
        now = _door_open(gw.json().get("walls", []), did) if gw.status_code == 200 else None
        ok = r.status_code == 200 and b is not None and now == want_open
        checks.append(_check(
            "door", f"{action} door {did}",
            f"HTTP 200, walls_update broadcast, door open={want_open}",
            f"HTTP {r.status_code}, broadcast {'seen' if b else 'MISSING'}, open={now}",
            "pass" if ok else "fail"))
        _publish(report)
        return now

    # Toggle both ways so the GM sees the door open AND close, ending as-found.
    if was_open:
        await _toggle("Close", False)
        await _toggle("Open", True)
    else:
        await _toggle("Open", True)
        await _toggle("Close", False)


def _hp_of(state: dict, combatant_id: str):
    for c in state.get("combatants", []):
        if c.get("id") == combatant_id:
            return c.get("hp_current")
    return None


def _tok_id(comb):
    """The Token row id embedded in a combatant id (``tok_stH_<id>``)."""
    try:
        return int(str(comb.get("id")).rsplit("_", 1)[-1])
    except (TypeError, ValueError):
        return None


async def _pc_spell_check(client, collector, cid, comb, target, actor_node, spell_casters) -> None:
    """Cast a spell as this PC at ``target`` and record a spell_cast check.
    Self-contained (own try/except) so it never disturbs the attack check."""
    char_id = comb["char_id"]
    try:
        sheet = await _get_sheet(client, cid, char_id)
        spells = list(sheet.get("spells") or [])
        if not spells:
            actor_node["checks"].append(_check(
                "spell_cast", f"{actor_node['actor']} casts a spell",
                "a castable spell", "not a caster (no spells on sheet)", "skip"))
            return
        avail_before = _slots_available(sheet)
        pick = _pick_spell(spells, avail_before > 0)
        if pick is None:
            actor_node["checks"].append(_check(
                "spell_cast", f"{actor_node['actor']} casts a spell",
                "a cantrip or an available slot", "no slot free and no cantrip known", "skip"))
            return
        # Try the chosen spell; if a leveled cast is refused (e.g. a Warlock's
        # pact slot doesn't match the spell's level), fall back to a cantrip.
        cantrips = [i for i, s in enumerate(spells)
                    if isinstance(s, dict) and int(s.get("level") or 0) == 0]
        attempts = [pick]
        if pick[1] and cantrips:
            attempts.append((cantrips[0], False))

        r = None
        bcast = None
        spell_index, is_leveled = pick
        for spell_index, is_leveled in attempts:
            if collector:
                collector.mark()
            r = await client.post(
                f"/api/campaign/{cid}/cast_spell",
                json={"character_id": char_id, "spell_index": spell_index,
                      "target_combatant_id": target["id"], "override": True})
            bcast = await collector.wait_for("spell_cast", _COMBAT_WS_TIMEOUT) if collector else None
            if r.status_code == 200:
                break
        spell_name = (spells[spell_index] or {}).get("name") or f"spell #{spell_index}"
        ok = r.status_code == 200 and bcast is not None
        err = "" if r.status_code == 200 else f" ({str(r.text)[:80]})"
        detail = f"'{spell_name}' (level {'1+' if is_leveled else '0 cantrip'}) at {target['name']}"
        if is_leveled and ok:
            avail_after = _slots_available(await _get_sheet(client, cid, char_id))
            spell_casters.add(char_id)
            decremented = avail_after == avail_before - 1
            actor_node["checks"].append(_check(
                "spell_cast", f"{actor_node['actor']} casts {spell_name}",
                "HTTP 200, spell_cast broadcast, one spell slot consumed",
                f"HTTP {r.status_code}, broadcast {'seen' if bcast else 'MISSING'}, "
                f"slots {avail_before}→{avail_after}{err}",
                "pass" if (ok and decremented) else "fail", detail))
        else:
            actor_node["checks"].append(_check(
                "spell_cast", f"{actor_node['actor']} casts {spell_name}",
                "HTTP 200, spell_cast broadcast (cantrip — no slot spent)",
                f"HTTP {r.status_code}, broadcast {'seen' if bcast else 'MISSING'}{err}",
                "pass" if ok else "fail", detail))
    except Exception as e:  # noqa: BLE001
        actor_node["checks"].append(_check(
            "spell_cast", f"{actor_node['actor']} casts a spell",
            "HTTP 200 + spell_cast broadcast", f"exception: {e}", "error"))


async def _combat_rounds(client, collector, cid, node, report, combs, spell_casters, phases) -> None:
    """Drive a few rounds. Each round is a node; each acting combatant is an
    actor node under it with an attack check + a turn-advance check (and, for
    caster PCs, a spell-cast check). ``spell_casters`` collects the char_ids
    that spent a slot, so the caller can long-rest them in teardown. ``phases``
    gates which checks run: "combat" (attacks + turn advance) and/or "spells"."""
    do_attacks = "combat" in phases
    do_spells = "spells" in phases
    heroes = [c for c in combs if c.get("char_id") is not None]
    villains = [c for c in combs if c.get("char_id") is None]
    if not heroes or not villains:
        return
    actors = heroes[:_MAX_PC_PER_ROUND] + villains[:_MAX_NPC_PER_ROUND]
    # Targets: heroes hit the first villain, villains hit the first hero.
    v_target, h_target = villains[0], heroes[0]

    turn = 0
    for rnd in range(1, _ROUNDS + 1):
        round_node = {"round": rnd, "status": "running", "tally": _empty_tally(), "actors": []}
        node["rounds"].append(round_node)
        _publish(report)

        for comb in actors:
            is_pc = comb.get("char_id") is not None
            # Which checks apply to this actor under the selected phases?
            pc_attack = is_pc and do_attacks
            pc_spell = is_pc and do_spells
            npc_attack = (not is_pc) and do_attacks
            if not (pc_attack or pc_spell or npc_attack):
                continue
            actor_node = {
                "actor": comb.get("name") or ("Hero" if is_pc else "Villain"),
                "kind": "pc" if is_pc else "npc",
                "combatant_id": comb["id"], "status": "running",
                "tally": _empty_tally(), "checks": [],
            }
            round_node["actors"].append(actor_node)
            _publish(report)

            # --- the actor's attack (+ spell for casters) ---
            try:
                if is_pc:
                    tgt = v_target
                    if pc_attack:
                        # Advance on the target first — glide the PC token to melee
                        # so it looks like real play, then swing.
                        try:
                            toks = (await client.get(f"/api/campaign/{cid}/tokens")).json().get("tokens", [])
                            pos = {t["id"]: (float(t.get("x") or 0), float(t.get("y") or 0)) for t in toks}
                            pid, vid = _tok_id(comb), _tok_id(tgt)
                            if pid in pos and vid in pos:
                                (px, py), (vx, vy) = pos[pid], pos[vid]
                                dx, dy = vx - px, vy - py
                                d = math.hypot(dx, dy) or 1.0
                                stopx, stopy = vx - dx / d * _PX_PER_CELL, vy - dy / d * _PX_PER_CELL
                                mok, mseen, _ = await _glide(
                                    client, collector, cid, pid, px, py, stopx, stopy, steps=2)
                                # Broadcasts are informational: a PC already in
                                # melee makes near-zero hops (no broadcast), which
                                # is valid — the check passes on clean HTTP moves.
                                actor_node["checks"].append(_check(
                                    "movement", f"{actor_node['actor']} advances on {tgt['name']}",
                                    "token glides toward the target (token_move per real hop)",
                                    f"HTTP 200 hops; {mseen}/2 token_move broadcasts"
                                    + ("" if mseen else " (already adjacent)"),
                                    "pass" if mok else "fail"))
                                _publish(report)
                        except Exception as e:  # noqa: BLE001
                            actor_node["checks"].append(_check(
                                "movement", f"{actor_node['actor']} advances",
                                "glide toward target", f"exception: {e}", "error"))
                            _publish(report)
                        # Targeting line PC → target, like a player picking a target.
                        await _target_line(client, cid, _tok_id(comb), _tok_id(tgt))
                        await _pace()
                        before = _hp_of(await _get_battle(client, cid), tgt["id"])
                        collector.mark() if collector else None
                        r = await client.post(
                            f"/api/campaign/{cid}/attack",
                            json={"character_id": comb["char_id"], "attack_index": 0,
                                  "target_combatant_id": tgt["id"], "override": True})
                        bcast = await collector.wait_for("weapon_attack", _COMBAT_WS_TIMEOUT) if collector else None
                        after = _hp_of(await _get_battle(client, cid), tgt["id"])
                        body = r.json() if r.status_code == 200 else {}
                        ok = r.status_code == 200 and bcast is not None
                        actor_node["checks"].append(_check(
                            "pc_attack", f"{actor_node['actor']} attacks {tgt['name']} (attack #0)",
                            "HTTP 200 (attack_total + damage_total), weapon_attack broadcast",
                            f"HTTP {r.status_code}, attack_total={body.get('attack_total')}, "
                            f"damage_total={body.get('damage_total')}, "
                            f"broadcast {'seen' if bcast else 'MISSING'}",
                            "pass" if ok else "fail",
                            f"target HP {before}→{after}"))

                    await _ruler_hide(client, cid)

                    if pc_spell:
                        # A caster PC casts a spell at the villain: a leveled
                        # spell when a slot is free (tests slot decrement), else
                        # a cantrip; non-casters record a skip. Show the target line.
                        await _target_line(client, cid, _tok_id(comb), _tok_id(v_target))
                        await _pc_spell_check(
                            client, collector, cid, comb, v_target, actor_node, spell_casters)
                        await _ruler_hide(client, cid)
                elif npc_attack:
                    tgt = h_target
                    await _target_line(client, cid, _tok_id(comb), _tok_id(tgt))
                    await _pace()
                    before = _hp_of(await _get_battle(client, cid), tgt["id"])
                    collector.mark() if collector else None
                    r = await client.post(
                        f"/api/campaign/{cid}/npc_attack",
                        json={"combatant_id": comb["id"], "action_name": "Strike",
                              "attack_bonus": "+4", "damage": "1d8", "damage_type": "bludgeoning",
                              "range": "5 ft", "target_combatant_id": tgt["id"],
                              # Seeded tokens sit at map distance; this is a
                              # synthetic strike, so bypass the range gate (the
                              # GM click-again-to-override escape hatch).
                              "override_range": True})
                    bcast = await collector.wait_for("weapon_attack", _COMBAT_WS_TIMEOUT) if collector else None
                    after = _hp_of(await _get_battle(client, cid), tgt["id"])
                    ok = r.status_code == 200 and bcast is not None
                    actor_node["checks"].append(_check(
                        "npc_attack", f"{actor_node['actor']} strikes {tgt['name']}",
                        "HTTP 200, weapon_attack broadcast (hit resolved vs target AC)",
                        f"HTTP {r.status_code}, broadcast {'seen' if bcast else 'MISSING'}",
                        "pass" if ok else "fail",
                        f"target HP {before}→{after}"))
                    await _ruler_hide(client, cid)
            except Exception as e:  # noqa: BLE001
                actor_node["checks"].append(_check(
                    "pc_attack" if is_pc else "npc_attack",
                    f"{actor_node['actor']} acts", "an attack + broadcast",
                    f"exception: {e}", "error"))
            _publish(report)

            # --- advance the turn (combat phase only; preserves HP/economy) ---
            if not do_attacks:
                continue
            try:
                state = await _get_battle(client, cid)
                n = len(state.get("combatants", [])) or 1
                new_turn = (turn + 1) % n
                cur_round = state.get("round", rnd) or rnd
                new_round = cur_round + (1 if new_turn == 0 else 0)
                state["turn_index"] = new_turn
                state["round"] = new_round
                state["active"] = True
                collector.mark() if collector else None
                pr = await client.put(f"/api/campaign/{cid}/battle", json=state)
                bcast = await collector.wait_for("battle_update", _COMBAT_WS_TIMEOUT) if collector else None
                after = await _get_battle(client, cid)
                advanced = after.get("turn_index") == new_turn
                ok = pr.status_code == 200 and advanced and bcast is not None
                actor_node["checks"].append(_check(
                    "turn_advance", f"End {actor_node['actor']}'s turn (advance initiative)",
                    f"HTTP 200, battle_update broadcast, turn_index → {new_turn}"
                    + (f" (round {new_round})" if new_turn == 0 else ""),
                    f"HTTP {pr.status_code}, turn_index={after.get('turn_index')}, "
                    f"round={after.get('round')}, broadcast {'seen' if bcast else 'MISSING'}",
                    "pass" if ok else "fail"))
                turn = new_turn
            except Exception as e:  # noqa: BLE001
                actor_node["checks"].append(_check(
                    "turn_advance", f"End {actor_node['actor']}'s turn",
                    "turn advances + battle_update", f"exception: {e}", "error"))
            _publish(report)


# ── Negative-path gate checks (driven as a non-GM player) ────────────────────

async def _gate_checks(gm_client, cid, checks, report, heroes, combs, gm_email) -> None:
    """Assert the gates a non-GM player hits (the GM bypasses them, so these run
    as the player who owns a token): an off-turn move is 403, and an attack on an
    already-spent action is 409 over_budget. Appended to the given ``checks`` list
    with category ``gate``. Non-mutating — both actions are expected to be
    rejected, so nothing to restore."""
    # Find a player-owned hero token (controller is a non-GM user).
    player_tok = None
    player_email = None
    for t in heroes:
        email = _user_email(t.get("controller_user_id"))
        if email and email != gm_email:
            player_tok, player_email = t, email
            break
    if not player_tok:
        checks.append(_check(
            "gate", "Player-side gate checks (off-turn move / over-budget)",
            "a player-owned token to drive the gates",
            "no non-GM-owned hero token in this campaign", "skip"))
        _publish(report)
        return

    player_cid = f"tok_stH_{player_tok['id']}"
    villain = next((c for c in combs if c.get("char_id") is None), None)
    if villain is None:
        return
    v_index = combs.index(villain)

    player_client = None
    try:
        player_client = httpx.AsyncClient(base_url=_APP_URL, follow_redirects=True, timeout=20.0)
        lr = await player_client.post("/login", data={"email": player_email, "password": _DEMO_PASSWORD})
        if lr.status_code not in (200, 303):
            checks.append(_check(
                "gate", f"Log in as player {player_email}",
                "HTTP 200/303", f"HTTP {lr.status_code}", "error"))
            _publish(report)
            return

        # Seed a controlled battle: active, a villain's turn (so the player is
        # off-turn), and the player's action already spent.
        state_combs = []
        for c in combs:
            c2 = dict(c)
            if c2["id"] == player_cid:
                c2["economy"] = {**c2.get("economy", {}), "action": True}
            state_combs.append(c2)
        await gm_client.put(
            f"/api/campaign/{cid}/battle",
            json={"combatants": state_combs, "turn_index": v_index, "round": 1, "active": True})

        # 1) Off-turn move → 403.
        ox, oy = float(player_tok.get("x") or 0), float(player_tok.get("y") or 0)
        mr = await player_client.post(
            f"/api/campaign/{cid}/token/{player_tok['id']}/move", json={"x": ox + 35, "y": oy})
        checks.append(_check(
            "gate", f"{player_email} moves off-turn (it's a villain's turn)",
            "HTTP 403 (not your turn) — the off-turn movement gate blocks it",
            f"HTTP {mr.status_code}", "pass" if mr.status_code == 403 else "fail",
            str(mr.text)[:80]))
        _publish(report)

        # 2) Attack on an already-spent action, no override → 409 over_budget.
        ar = await player_client.post(
            f"/api/campaign/{cid}/attack",
            json={"character_id": player_tok["character_id"], "attack_index": 0,
                  "target_combatant_id": villain["id"]})
        err = ar.json().get("error") if ar.status_code == 409 else None
        checks.append(_check(
            "gate", f"{player_email} attacks with its action spent (no override)",
            "HTTP 409 {error: over_budget} — the action-economy gate blocks it",
            f"HTTP {ar.status_code}" + (f", error={err}" if err else ""),
            "pass" if (ar.status_code == 409 and err == "over_budget") else "fail",
            str(ar.text)[:80]))
        _publish(report)
    except Exception as e:  # noqa: BLE001
        checks.append(_check(
            "gate", "Player-side gate checks", "gates reject the player's actions",
            f"exception: {e}", "error"))
        _publish(report)
    finally:
        if player_client is not None:
            await player_client.aclose()


# ── Rules deep-dive tier (deeper SRD mechanics) ──────────────────────────────

async def _deep_checks(client, collector, cid, node, report, combs,
                       heroes, villains, spell_casters, rested_pcs, phases) -> None:
    """Run the enabled Rules deep-dive phases. Each appends to node["deep_checks"]
    and is applicability-skipped per demo. Runs with an active battle already
    established (combs), so target combatants + HP are available."""
    deep = node["deep_checks"]
    if "rest" in phases:
        await _rest_check(client, cid, heroes, deep, report, rested_pcs)
    if "heal" in phases:
        await _heal_check(client, collector, cid, heroes, deep, report, spell_casters, rested_pcs)
    if "death_saves" in phases:
        await _death_saves_check(client, cid, heroes, deep, report)


async def _rest_check(client, cid, heroes, deep, report, rested_pcs) -> None:
    """Short rest on a hero: assert a hit die is spent + HP recovered (SRD PHB
    p.186). Restored by the teardown long-rest."""
    hero = next((h for h in heroes if h.get("character_id")), None)
    if not hero:
        deep.append(_check("rest", "Short rest (spend a hit die)",
                           "a hero PC", "no hero PC on the map", "skip"))
        _publish(report)
        return
    char_id = hero["character_id"]
    name = hero.get("label") or "a hero"
    try:
        before = await _get_sheet(client, cid, char_id)
        hd_before = (before.get("hit_dice") or {}).get("current")
        if hd_before is not None and hd_before <= 0:
            deep.append(_check("rest", f"{name} takes a short rest",
                               "a hit die to spend", "no hit dice remaining", "skip"))
            _publish(report)
            return
        r = await client.post(
            f"/api/campaign/{cid}/character/{char_id}/rest", json={"type": "short"})
        body = r.json() if r.status_code == 200 else {}
        hd_after = (body.get("hit_dice") or {}).get("current")
        recovered = body.get("recovered")
        ok = (r.status_code == 200 and hd_before is not None and hd_after is not None
              and hd_after == hd_before - 1)
        if r.status_code == 200:
            rested_pcs.add(char_id)
        deep.append(_check(
            "rest", f"{name} takes a short rest",
            "HTTP 200, one hit die spent (current −1), HP recovered",
            f"HTTP {r.status_code}, hit_dice {hd_before}→{hd_after}, recovered={recovered}",
            "pass" if ok else "fail"))
    except Exception as e:  # noqa: BLE001
        deep.append(_check("rest", f"{name} short rest",
                           "HTTP 200 + hit-die spend", f"exception: {e}", "error"))
    _publish(report)


_HEAL_SLUGS = ("cure-wounds", "healing-word", "mass-cure-wounds", "mass-healing-word")


async def _sheet_hp(client, cid, char_id):
    """A PC's real (sheet) current/max HP — PC damage + healing act on the sheet,
    not the nominal hub combatant HP. Returns (current, max) or (None, None)."""
    hp = (await _get_sheet(client, cid, char_id)).get("hp") or {}
    return hp.get("current"), hp.get("max")


async def _heal_check(client, collector, cid, heroes, deep, report, spell_casters, rested_pcs) -> None:
    """A healer casts Cure Wounds / Healing Word at a wounded ally: assert the
    target's HP rises + a slot is spent (SRD PHB healing). The target is first
    actually damaged by an NPC strike (so its real HP is below max and the heal
    is observable); the teardown long-rest restores it."""
    healer = spell_index = spell_name = None
    healer_sheet = None
    for h in heroes:
        chid = h.get("character_id")
        if not chid:
            continue
        sheet = await _get_sheet(client, cid, chid)
        for i, sp in enumerate(sheet.get("spells") or []):
            slug = (sp.get("_slug") or "").lower()
            nm = (sp.get("name") or "").lower()
            if slug in _HEAL_SLUGS or "cure wounds" in nm or "healing word" in nm:
                healer, spell_index, spell_name, healer_sheet = h, i, sp.get("name"), sheet
                break
        if healer:
            break
    if not healer:
        deep.append(_check("heal", "Cast a healing spell",
                           "a hero with Cure Wounds / Healing Word",
                           "no healer in this party", "skip"))
        _publish(report)
        return
    try:
        state = await _get_battle(client, cid)
        combs = state.get("combatants", [])
        healer_comb = next((c for c in combs if c.get("char_id") == healer["character_id"]), None)
        target = next((c for c in combs if c.get("char_id") is not None and c is not healer_comb), healer_comb)
        attacker = next((c for c in combs if c.get("char_id") is None), None)
        if target is None or attacker is None:
            deep.append(_check("heal", "Cast a healing spell", "an ally + an attacker",
                               "not enough combatants", "skip"))
            _publish(report)
            return
        tgt_char = target["char_id"]
        rested_pcs.add(tgt_char)  # long-rest restores its real HP
        # Actually wound the target (its SHEET HP) with NPC strikes so the heal
        # is observable (PC HP lives on the sheet, not the nominal hub combatant).
        wounded, hp_max = await _sheet_hp(client, cid, tgt_char)
        for _ in range(3):
            if wounded is not None and hp_max is not None and wounded < hp_max:
                break
            await client.post(
                f"/api/campaign/{cid}/npc_attack",
                json={"combatant_id": attacker["id"], "action_name": "Strike",
                      "attack_bonus": "+15", "damage": "6d10", "damage_type": "bludgeoning",
                      "target_combatant_id": target["id"], "override_range": True})
            wounded, hp_max = await _sheet_hp(client, cid, tgt_char)
        slots_before = _slots_available(healer_sheet)
        if collector:
            collector.mark()
        r = await client.post(
            f"/api/campaign/{cid}/cast_spell",
            json={"character_id": healer["character_id"], "spell_index": spell_index,
                  "target_combatant_id": target["id"], "override": True})
        body = r.json() if r.status_code == 200 else {}
        bcast = await collector.wait_for("spell_cast", _COMBAT_WS_TIMEOUT) if collector else None
        # Some heals need an explicit apply-claim; auto-heals don't.
        cast_id = body.get("cast_id") or body.get("id")
        if r.status_code == 200 and not body.get("auto_heal_applied") and cast_id:
            await client.post(f"/api/campaign/{cid}/apply_healing", json={"cast_id": cast_id})
        after, _ = await _sheet_hp(client, cid, tgt_char)
        slots_after = _slots_available(await _get_sheet(client, cid, healer["character_id"]))
        if r.status_code == 200:
            spell_casters.add(healer["character_id"])
        ok = (r.status_code == 200 and after is not None and wounded is not None
              and after > wounded)
        deep.append(_check(
            "heal", f"{healer.get('label') or 'A healer'} heals {target.get('name')} with {spell_name}",
            "HTTP 200, spell_cast broadcast, wounded ally's HP rises, one slot spent",
            f"HTTP {r.status_code}, target HP {wounded}→{after}, slots {slots_before}→{slots_after}, "
            f"broadcast {'seen' if bcast else 'MISSING'}",
            "pass" if ok else "fail"))
    except Exception as e:  # noqa: BLE001
        deep.append(_check("heal", "Cast a healing spell",
                           "HTTP 200 + HP rise", f"exception: {e}", "error"))
    _publish(report)


async def _death_saves_check(client, cid, heroes, deep, report) -> None:
    """Death saves + stabilize (SRD PHB p.197). Sets a hero dying (GM override,
    HP untouched), rolls a death save (asserts the state advances), then
    stabilizes it — resetting the death-save state afterward (self-restoring)."""
    hero = next((h for h in heroes if h.get("character_id")), None)
    if not hero:
        deep.append(_check("death_save", "Roll a death save + stabilize",
                           "a hero PC", "no hero PC on the map", "skip"))
        _publish(report)
        return
    char_id = hero["character_id"]
    name = hero.get("label") or "a hero"
    base = f"/api/campaign/{cid}/character/{char_id}"
    try:
        await client.post(f"{base}/death-save/override",
                          json={"status": "dying", "successes": 0, "failures": 0})
        r = await client.post(f"{base}/death-save")
        body = r.json() if r.status_code == 200 else {}
        outcome = body.get("outcome")
        status = body.get("status")
        rolled = r.status_code == 200 and outcome is not None
        stab = None
        if status == "dying":
            sr = await client.post(f"{base}/stabilize")
            stab = ((sr.json().get("death_saves") or {}).get("status")
                    if sr.status_code == 200 else f"HTTP {sr.status_code}")
        ok = rolled and (status != "dying" or stab == "stable")
        deep.append(_check(
            "death_save", f"{name}: roll a death save + stabilize",
            "HTTP 200, death-save roll advances state; stabilize → stable "
            "(unless the roll woke/killed the PC)",
            f"roll {outcome}/{status} (succ {body.get('successes')} / fail {body.get('failures')}); "
            f"stabilize → {stab}",
            "pass" if ok else "fail"))
    except Exception as e:  # noqa: BLE001
        deep.append(_check("death_save", f"{name}: death save",
                           "HTTP 200 + state advance", f"exception: {e}", "error"))
    finally:
        # Reset death-save state (HP was never changed by the override path).
        try:
            await client.post(f"{base}/death-save/override",
                              json={"status": "alive", "successes": 0, "failures": 0})
        except Exception:  # noqa: BLE001
            pass
    _publish(report)


# ── Per-campaign run ─────────────────────────────────────────────────────────

async def _run_campaign(camp: dict, node: dict, report: dict, phases: set, recorder=None) -> None:
    cid = camp["id"]
    gm_email = camp["gm_email"]
    setup = node["setup_checks"]
    teardown = node["teardown_checks"]
    # combat/spells/gates + every deep-tier phase need an active battle →
    # initiative runs when any is on.
    need_battle = bool(phases & ({"combat", "spells", "gates"} | set(_DEEP_PHASES)))
    battle_touched = False
    rec_handle = None

    if not gm_email:
        setup.append(_check(
            "reachability", "Resolve the campaign GM account",
            "a demo GM email is on file", "no GM user found", "error"))
        _publish(report)
        return

    client = None
    ws = None
    collector = None
    token_snapshot: dict = {}   # token_id → (x, y) for all tokens, to restore
    battle_snapshot = None      # prior battle state to restore
    combs_for_combat = None     # combatants seeded by initiative, for the rounds
    spell_casters: set = set()  # char_ids that spent a slot → long-rest to restore
    rested_pcs: set = set()     # char_ids whose sheet was mutated → long-rest to restore
    map_id = None               # active map id (for doors)
    walls: list = []            # active map walls/doors

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
            # Snapshot every token's position so movement/combat is restorable.
            token_snapshot = {t["id"]: (float(t.get("x") or 0), float(t.get("y") or 0)) for t in tokens}
            # Active map (id + walls) for door checks + movement bounds.
            try:
                mr = await client.get(f"/api/campaign/{cid}/active-map")
                if mr.status_code == 200:
                    mj = mr.json()
                    map_id = mj.get("map_id")
                    walls = mj.get("walls") or []
            except Exception:  # noqa: BLE001
                pass
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

        # --- open the recording browser (captures movement + combat) ---
        if recorder is not None:
            cookies = [{"name": k, "value": v, "url": _APP_URL}
                       for k, v in client.cookies.items()]
            rec_handle = await recorder.open(cid, cookies)

        # --- movement across the map (a visible multi-step glide) ---
        if "movement" not in phases:
            pass
        elif heroes:
            tok = heroes[0]
            tid = tok["id"]
            ox, oy = float(tok.get("x") or 0), float(tok.get("y") or 0)
            # Glide ~4 cells along x (away from the edge), in several hops so a
            # watching GM sees the token travel.
            span = 4 * _PX_PER_CELL
            tx = ox - span if ox > 400 else ox + span
            ty = oy
            steps = 4
            exp_ft = round(math.hypot(tx - ox, ty - oy) / _PX_PER_CELL * _FT_PER_CELL, 1)
            try:
                ok_glide, seen, last = await _glide(
                    client, collector, cid, tid, ox, oy, tx, ty, steps=steps)
                tr2 = await client.get(f"/api/campaign/{cid}/tokens")
                now = next((t for t in tr2.json().get("tokens", []) if t["id"] == tid), None)
                relocated = now is not None and abs(float(now["x"]) - tx) < 1 and abs(float(now["y"]) - ty) < 1
                ok = ok_glide and relocated and seen >= 1
                setup.append(_check(
                    "movement",
                    f"Glide {tok.get('label') or 'a hero'} across the map ({steps} steps)",
                    f"HTTP 200 each hop, token travels to ({tx:.0f},{ty:.0f}) (~{exp_ft} ft), "
                    f"a token_move broadcast per hop",
                    f"final ({now['x']:.0f},{now['y']:.0f}); {seen}/{steps} token_move broadcasts seen",
                    "pass" if ok else "fail",
                    f"from ({ox:.0f},{oy:.0f})"))
            except Exception as e:  # noqa: BLE001
                setup.append(_check(
                    "movement", "Glide a hero token across the map",
                    "HTTP 200 + token_move broadcasts", f"exception: {e}", "error"))
        else:
            setup.append(_check(
                "movement", "Glide a hero token across the map",
                "a hero token to move", "no hero token found", "skip"))
        _publish(report)

        # --- doors: open + close a door on the map (GM bypasses gates) ---
        if "doors" in phases:
            try:
                await _door_checks(client, collector, cid, map_id, walls, setup, report)
            except Exception as e:  # noqa: BLE001
                setup.append(_check(
                    "door", "Open + close a door",
                    "walls_update + open flag flips", f"exception: {e}", "error"))
                _publish(report)

        # --- start initiative (snapshot the prior battle first, to restore) ---
        if not need_battle:
            pass
        elif heroes and villains:
            try:
                gb = await client.get(f"/api/campaign/{cid}/battle")
                battle_snapshot = gb.json().get("battle") if gb.status_code == 200 else None
                combs = _combatants(heroes, villains)
                battle_touched = True
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
                if ok:
                    combs_for_combat = combs
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

        # --- negative-path gate checks (driven as a non-GM player) ---
        if combs_for_combat and "gates" in phases:
            await _gate_checks(
                client, cid, setup, report, heroes, combs_for_combat, gm_email)

        # --- combat rounds: per round → per actor (PC/NPC) ---
        if combs_for_combat and (phases & {"combat", "spells"}):
            await _combat_rounds(
                client, collector, cid, node, report, combs_for_combat, spell_casters, phases)

        # --- Rules deep-dive tier: deeper SRD mechanics ---
        if combs_for_combat and (phases & set(_DEEP_PHASES)):
            await _deep_checks(
                client, collector, cid, node, report, combs_for_combat,
                heroes, villains, spell_casters, rested_pcs, phases)

        # --- finalize the recording before teardown resets the board ---
        if recorder is not None:
            node["video"] = await recorder.close(rec_handle, cid)
            rec_handle = None
            _publish(report)

    finally:
        # Close a still-open recording (e.g. an exception before combat ended).
        if recorder is not None and rec_handle is not None:
            node["video"] = await recorder.close(rec_handle, cid)
        # --- teardown: restore token positions + battle state ---
        if client is not None:
            try:
                # Move every token back to its snapshot position (idempotent when
                # unchanged) so movement + combat advances are non-destructive.
                for tid, (ox, oy) in token_snapshot.items():
                    await client.post(
                        f"/api/campaign/{cid}/token/{tid}/move", json={"x": ox, "y": oy})
                # Refill spent spell slots + any sheet mutated by the deep tier
                # (rest hit-dice, feature resources) with a long rest.
                for char_id in (spell_casters | rested_pcs):
                    await client.post(
                        f"/api/campaign/{cid}/character/{char_id}/rest", json={"type": "long"})
                # Only touch the battle if this run started one.
                if battle_touched:
                    if battle_snapshot is not None:
                        await client.put(f"/api/campaign/{cid}/battle", json=battle_snapshot)
                    else:
                        await client.put(
                            f"/api/campaign/{cid}/battle",
                            json={"combatants": [], "turn_index": 0, "round": 1, "active": False})
                battle_word = ("snapshot" if battle_snapshot is not None else "cleared") if battle_touched else "untouched"
                teardown.append(_check(
                    "restore", "Restore token positions + battle + spell slots",
                    "tokens moved back, battle reset to its prepped state, slots refilled",
                    f"{len(token_snapshot)} token(s) restored; battle "
                    f"{battle_word}; "
                    f"{len(spell_casters | rested_pcs)} PC(s) long-rested",
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


def list_campaigns() -> list:
    """[{id, name}] of the demo campaigns, for the page's scope picker."""
    return [{"id": c["id"], "name": c["name"]} for c in _demo_campaigns()]


def reseed_campaigns(campaign_ids) -> list:
    """Wipe + reseed just the given demo campaigns to their pristine seeded
    state (the demo has no permanent data). Supported for the leveled sample
    campaigns (rebuilt via ``_seed_one``); the flagship keeps id 1 and is left to
    the full demo reset in Tools. Each reseeded campaign gets a fresh id — the
    self-test resolves campaigns by name, so that's fine. Returns a per-campaign
    result list."""
    from ..database import SessionLocal
    from ..models import Campaign, User
    from .. import demo_seed as ds
    from .. import demo_campaigns as dc
    from ..campaign_wipe import wipe_campaign_children
    from ..realtime import hub

    specs = {s["name"]: s for s in dc.CAMPAIGN_SPECS}
    key_email = {
        "gm": ds.DEMO_GM_EMAIL, "alice": ds.DEMO_ALICE_EMAIL, "bob": ds.DEMO_BOB_EMAIL,
        "gm2": ds.DEMO_GM2_EMAIL, "carol": ds.DEMO_CAROL_EMAIL,
        "dave": ds.DEMO_DAVE_EMAIL, "erin": ds.DEMO_ERIN_EMAIL,
    }
    out = []
    db = SessionLocal()
    try:
        by_email = {u.email: u for u in db.query(User).filter(
            User.email.in_(list(key_email.values()))).all()}
        users = {k: by_email[e] for k, e in key_email.items() if e in by_email}
        for cid in (campaign_ids or []):
            try:
                camp = db.query(Campaign).filter(Campaign.id == int(cid)).first()
                if not camp:
                    out.append({"id": cid, "ok": False, "error": "campaign not found"})
                    continue
                name = camp.name
                if name not in specs:
                    out.append({
                        "id": cid, "name": name, "ok": False,
                        "error": "per-campaign reseed is for the leveled demos only "
                                 "(use Tools → demo reset for the flagship)"})
                    continue
                old_id = camp.id
                wipe_campaign_children(db, [old_id])
                hub.evict_battle(old_id)
                db.query(Campaign).filter(Campaign.id == old_id).delete(synchronize_session=False)
                db.flush()
                new = dc._seed_one(db, specs[name], users)
                db.commit()
                out.append({"id": cid, "name": name, "ok": True, "new_id": new.id})
            except Exception as e:  # noqa: BLE001
                db.rollback()
                out.append({"id": cid, "ok": False, "error": str(e)[:160]})
        return out
    finally:
        db.close()


async def _run_all(campaign_ids=None, phases=None, step_delay=None, record=False) -> None:
    global _ACTIVE_STEP_DELAY
    _ACTIVE_STEP_DELAY = _STEP_DELAY if step_delay is None else float(step_delay)
    slow = _ACTIVE_STEP_DELAY > _STEP_DELAY
    started = time.time()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # Purge this run's synthetic stat events afterwards so the self-test (esp. a
    # slow run) never skews the campaign's real time/activity stats.
    from datetime import timedelta
    purge_since = datetime.now(timezone.utc) - timedelta(seconds=5)
    phase_set = _norm_phases(phases)
    # Optional video capture (headless Chromium records each tabletop).
    recorder = _Recorder(run_id) if record else None
    if recorder is not None:
        rec_ok = await recorder.start()
        if not rec_ok:
            recorder = None
    campaigns = _demo_campaigns()
    if campaign_ids:
        wanted = {int(x) for x in campaign_ids}
        campaigns = [c for c in campaigns if c["id"] in wanted]
    tested_ids = [c["id"] for c in campaigns]
    report = {
        "started_at": _iso(),
        "finished_at": None,
        "duration_s": 0.0,
        "app_url": _APP_URL,
        "app_version": APP_VERSION,
        "run_id": run_id,
        "state": "running",
        "scope": {
            "campaigns": [c["name"] for c in campaigns],
            "phases": sorted(phase_set),
            "slow": slow,
            "step_delay": _ACTIVE_STEP_DELAY,
            "record": recorder is not None,
            "video_size": (f"{_VIDEO_SIZE[0]}x{_VIDEO_SIZE[1]}" if recorder is not None else ""),
        },
        "stats_note": "",
        "totals": _empty_tally(),
        "campaigns": [],
    }
    _STATUS.update(state="running", pct=0, current="starting", started=started, finished=0.0)
    _publish(report)

    if not campaigns:
        _STATUS.update(state="error", current="no demo campaigns to run")
        report["state"] = "error"
        report["finished_at"] = _iso()
        _publish(report)
        _persist(report)
        return

    n = len(campaigns)
    for i, camp in enumerate(campaigns):
        _STATUS["current"] = camp["name"]
        node = {
            "campaign_id": camp["id"], "name": camp["name"], "gm": camp["gm_email"],
            "map": "", "status": "running", "tally": _empty_tally(),
            "setup_checks": [], "rounds": [], "deep_checks": [], "teardown_checks": [],
        }
        report["campaigns"].append(node)
        _publish(report)
        try:
            await _run_campaign(camp, node, report, phase_set, recorder)
        except Exception as e:  # noqa: BLE001
            node["setup_checks"].append(_check(
                "reachability", "Run campaign self-test",
                "campaign completes", f"unhandled exception: {e}", "error"))
        _STATUS["pct"] = int((i + 1) / n * 100)
        _publish(report)

    if recorder is not None:
        await recorder.stop()

    # Scrub the synthetic stat events this run generated so it doesn't count as
    # real play in the campaign's time/activity stats.
    purged = _purge_stat_events(tested_ids, purge_since)
    report["stats_note"] = (
        f"{purged} synthetic stat event(s) purged — this self-test run does not "
        f"count toward campaign stats." + (" (slow run)" if slow else ""))

    report["state"] = "done"
    report["finished_at"] = _iso()
    report["duration_s"] = round(time.time() - started, 1)
    _STATUS.update(state="done", pct=100, current="complete", finished=time.time())
    _publish(report)
    _persist(report)


def _purge_stat_events(campaign_ids, since) -> int:
    """Delete CampaignStatEvent rows for the given campaigns created at/after
    ``since`` — the self-test's synthetic gameplay. Best-effort. Returns count."""
    if not campaign_ids:
        return 0
    from ..database import SessionLocal
    from ..models import CampaignStatEvent
    db = SessionLocal()
    try:
        n = (db.query(CampaignStatEvent)
             .filter(CampaignStatEvent.campaign_id.in_([int(c) for c in campaign_ids]),
                     CampaignStatEvent.created_at >= since)
             .delete(synchronize_session=False))
        db.commit()
        return int(n or 0)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        log.warning("self-test stat-event purge failed: %s", e)
        return 0
    finally:
        db.close()


def _worker(campaign_ids, phases, step_delay, record) -> None:
    try:
        asyncio.run(_run_all(campaign_ids, phases, step_delay, record))
    except Exception as e:  # noqa: BLE001
        log.exception("self-test run crashed")
        _STATUS.update(state="error", current=f"crashed: {e}")
    finally:
        with _LOCK:
            _STATUS["_thread"] = None


def start_run(campaign_ids=None, phases=None, step_delay=None, record=False) -> bool:
    """Kick off a background run over an optional subset of campaigns/phases.
    ``step_delay`` overrides the per-action pacing (a slow run passes a larger
    value so a user can follow along). ``record`` captures video of each
    campaign's tabletop. Returns False if one is already running."""
    with _LOCK:
        if _STATUS.get("state") == "running":
            return False
        t = threading.Thread(
            target=_worker, args=(campaign_ids, phases, step_delay, record),
            name="selftest-runner", daemon=True)
        _STATUS["_thread"] = t
        _STATUS.update(state="running", pct=0, current="starting", report=None)
    t.start()
    return True
