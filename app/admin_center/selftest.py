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


def _hp_of(state: dict, combatant_id: str):
    for c in state.get("combatants", []):
        if c.get("id") == combatant_id:
            return c.get("hp_current")
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


async def _combat_rounds(client, collector, cid, node, report, combs, spell_casters) -> None:
    """Drive a few rounds. Each round is a node; each acting combatant is an
    actor node under it with an attack check + a turn-advance check (and, for
    caster PCs, a spell-cast check). ``spell_casters`` collects the char_ids
    that spent a slot, so the caller can long-rest them in teardown."""
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
            actor_node = {
                "actor": comb.get("name") or ("Hero" if is_pc else "Villain"),
                "kind": "pc" if is_pc else "npc",
                "combatant_id": comb["id"], "status": "running",
                "tally": _empty_tally(), "checks": [],
            }
            round_node["actors"].append(actor_node)
            _publish(report)

            # --- the actor's attack ---
            try:
                if is_pc:
                    tgt = v_target
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

                    # A caster PC also casts a spell at the villain. Prefer a
                    # leveled spell when a slot is free (tests slot decrement),
                    # else a cantrip; non-casters record a skip.
                    await _pc_spell_check(
                        client, collector, cid, comb, v_target, actor_node, spell_casters)
                else:
                    tgt = h_target
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
            except Exception as e:  # noqa: BLE001
                actor_node["checks"].append(_check(
                    "pc_attack" if is_pc else "npc_attack",
                    f"{actor_node['actor']} acts", "an attack + broadcast",
                    f"exception: {e}", "error"))
            _publish(report)

            # --- advance the turn (preserving mutated HP/economy) ---
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
    combs_for_combat = None   # combatants seeded by initiative, for the rounds
    spell_casters: set = set()  # char_ids that spent a slot → long-rest to restore

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

        # --- combat rounds: per round → per actor (PC/NPC) ---
        if combs_for_combat:
            await _combat_rounds(
                client, collector, cid, node, report, combs_for_combat, spell_casters)

    finally:
        # --- teardown: restore token positions + battle state ---
        if client is not None:
            try:
                for tid, ox, oy in moved:
                    await client.post(
                        f"/api/campaign/{cid}/token/{tid}/move", json={"x": ox, "y": oy})
                # Refill spent spell slots so leveled casts are non-destructive.
                for char_id in spell_casters:
                    await client.post(
                        f"/api/campaign/{cid}/character/{char_id}/rest", json={"type": "long"})
                if battle_snapshot is not None:
                    await client.put(f"/api/campaign/{cid}/battle", json=battle_snapshot)
                else:
                    await client.put(
                        f"/api/campaign/{cid}/battle",
                        json={"combatants": [], "turn_index": 0, "round": 1, "active": False})
                teardown.append(_check(
                    "restore", "Restore token positions + battle + spell slots",
                    "tokens moved back, battle reset to its prepped state, slots refilled",
                    f"{len(moved)} token(s) restored; battle "
                    f"{'snapshot' if battle_snapshot is not None else 'cleared'}; "
                    f"{len(spell_casters)} caster(s) long-rested",
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
