"""Per-campaign WebSocket hub.

Each campaign has a set of connected clients. Any message accepted by the
HTTP API (token move, dice roll, chat) is broadcast to that campaign's
clients.

Clients receive JSON messages of shape: {"type": "...", "data": {...}}.

v2.9.1: the hub also tracks per-connection identity (user_id +
display_name + color + is_gm) so a ``presence_update`` broadcast can
render the connected-players bubbles in the lower-left of the map.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Callable, Dict, Optional, Set

from fastapi import WebSocket

log = logging.getLogger(__name__)

# v2.1044.0 — presence idle threshold. A connection counts as idle once
# it has gone this long with no inbound WS traffic (the client pings on
# real user interaction, throttled — see ``_pingActivity`` in
# tabletop.js). Deliberately generous: a player reading a rules popover
# or watching someone else's turn is still "here", so this is tuned to
# flag genuinely-away seats, not brief pauses.
PRESENCE_IDLE_AFTER_SECONDS = 300


class CampaignHub:
    def __init__(self) -> None:
        self._channels: Dict[int, Set[WebSocket]] = defaultdict(set)
        # v2.9.1: per-connection identity. Keyed on the WebSocket
        # object so disconnect can look up the user info without a
        # second arg, and so multiple tabs from the same user each
        # show their own bubble (we dedupe by user_id at presence-
        # broadcast time so the lower-left only shows one pill per
        # human, even if they have three tabs open).
        self._identities: Dict[WebSocket, dict] = {}
        # v2.1044.0 — per-connection last-activity stamp (monotonic
        # seconds), fed by ``mark_active`` on every inbound WS frame.
        # Kept in its own map rather than inside ``_identities`` so the
        # identity dicts handed to ``recipient_filter`` stay the stable
        # {user_id, display_name, color, is_gm} shape callers expect.
        self._last_active: Dict[WebSocket, float] = {}
        self._lock = asyncio.Lock()
        self._battle: Dict[int, dict] = {}
        # v2.101.0 — campaigns whose battle has been hydrated from the
        # `battles` DB table at least once this process. A campaign with
        # NO persisted battle is still marked here after the first miss
        # so `get_battle` doesn't re-query the DB on every battle read
        # (it runs on every token move / OA check / turn advance).
        self._db_hydrated: Set[int] = set()

    def get_battle(self, campaign_id: int) -> dict | None:
        """Return the campaign's battle state, lazily rehydrating from
        the `battles` table on the first cache miss per process.

        The in-memory `_battle` map is the hot read path. After an app
        restart or the demo reseed it's empty, so the first read for a
        campaign falls through to the persisted row (the authoritative
        store) and repopulates the cache. Subsequent reads stay in
        memory. A campaign with no persisted battle is marked hydrated
        so we don't hammer the DB on every battle read.
        """
        state = self._battle.get(campaign_id)
        if state is not None:
            return state
        if campaign_id not in self._db_hydrated:
            self._db_hydrated.add(campaign_id)
            loaded = self._load_battle_from_db(campaign_id)
            if loaded is not None:
                self._battle[campaign_id] = loaded
                return loaded
        return self._battle.get(campaign_id)

    def evict_battle(self, campaign_id: int) -> None:
        """Drop the in-memory battle cache for a campaign so the next
        ``get_battle`` re-reads the authoritative DB row (or finds none).

        The demo *scheduler* reseed wipes + recreates a campaign's tokens
        WITHOUT a process restart, so the persisted ``battles`` row is
        cascade-deleted with the old campaign but this RAM cache survives
        — and would keep serving the previous cycle's combatants, whose
        ``source_token_id``s point at deleted tokens and whose economy
        still shows spent reactions. That stale state silently breaks
        opportunity-attack detection (watcher reaction reads as spent) and
        the client Dash gate (active-combatant match fails on the dangling
        token id). Evicting here forces a clean rehydrate.
        """
        self._battle.pop(campaign_id, None)
        self._db_hydrated.discard(campaign_id)

    def set_battle(self, campaign_id: int, state: dict) -> None:
        """Update the in-memory cache and write through to the DB.

        The cache is updated first (it's what every server-side battle
        read consults), then the state is persisted to the `battles`
        table so it survives a restart. A DB write failure is logged but
        never raised — the in-memory hub stays correct for the live
        process even if persistence hiccups.
        """
        self._battle[campaign_id] = state
        self._db_hydrated.add(campaign_id)
        self._persist_battle_to_db(campaign_id, state)

    @staticmethod
    def _load_battle_from_db(campaign_id: int) -> dict | None:
        """Read the persisted battle state for a campaign, or None."""
        try:
            from .database import SessionLocal
            from .models import Battle
            with SessionLocal() as db:
                row = db.get(Battle, campaign_id)
                if row is not None and isinstance(row.state, dict):
                    return row.state
        except Exception as e:  # noqa: BLE001
            log.warning(
                "battle DB load failed for campaign %s: %s", campaign_id, e,
            )
        return None

    @staticmethod
    def _persist_battle_to_db(campaign_id: int, state: dict) -> None:
        """Upsert the campaign's battle state into the `battles` table."""
        try:
            from .database import SessionLocal
            from .models import Battle
            with SessionLocal() as db:
                row = db.get(Battle, campaign_id)
                if row is None:
                    db.add(Battle(campaign_id=campaign_id, state=state))
                else:
                    row.state = state
                db.commit()
        except Exception as e:  # noqa: BLE001
            log.warning(
                "battle DB persist failed for campaign %s: %s",
                campaign_id, e,
            )

    def get_presence(self, campaign_id: int) -> list[dict]:
        """Return the deduped list of users currently connected to this
        campaign's WS hub. Each entry: ``{user_id, display_name, color,
        is_gm, idle, idle_seconds}``. Order isn't guaranteed; the client
        sorts at render time for stability.

        v2.1044.0 — ``idle_seconds`` is the age of the user's most recent
        activity *at broadcast time*, and ``idle`` is that age measured
        against ``PRESENCE_IDLE_AFTER_SECONDS``. The client keeps ticking
        the age forward locally between broadcasts (see ``_renderPresence``),
        so a seat goes amber on its own without the server having to run a
        sweeper task or push a fresh roster on a timer.

        Ages are sent as a *relative* duration rather than an absolute
        timestamp so a client whose clock is skewed against the server
        still renders the right thing.
        """
        now = time.monotonic()
        seen: dict[int, dict] = {}
        for ws in self._channels.get(campaign_id, ()):
            ident = self._identities.get(ws)
            if not ident:
                continue
            uid = ident.get("user_id")
            if uid is None:
                continue
            # A user is only as idle as their MOST recently active tab,
            # so fold extra connections into the existing entry instead
            # of skipping them (pre-v2.1044.0 this just `continue`d on a
            # duplicate uid, which was fine when there was nothing
            # per-connection to merge).
            idle_seconds = max(0.0, now - self._last_active.get(ws, now))
            prev = seen.get(uid)
            if prev is not None:
                if idle_seconds < prev["idle_seconds"]:
                    prev["idle_seconds"] = round(idle_seconds, 1)
                    prev["idle"] = idle_seconds >= PRESENCE_IDLE_AFTER_SECONDS
                continue
            seen[uid] = {
                "user_id": uid,
                "display_name": ident.get("display_name") or "Player",
                "color": ident.get("color"),
                "is_gm": bool(ident.get("is_gm")),
                "idle": idle_seconds >= PRESENCE_IDLE_AFTER_SECONDS,
                "idle_seconds": round(idle_seconds, 1),
            }
        return list(seen.values())

    async def mark_active(self, campaign_id: int, ws: WebSocket) -> None:
        """v2.1044.0 — record inbound client traffic as user activity.

        Called from the WS receive loop for every frame the client sends.
        The client only pings on genuine interaction (pointer/key/wheel),
        throttled well below the idle threshold, so this stays cheap.

        Re-broadcasts the roster only when this connection was *already*
        past the idle threshold — i.e. on the amber→green transition, so
        the rest of the table sees someone come back. Steady-state pings
        from an active seat cost one dict write and no broadcast.
        """
        now = time.monotonic()
        async with self._lock:
            prev = self._last_active.get(ws)
            was_idle = (
                prev is not None
                and (now - prev) >= PRESENCE_IDLE_AFTER_SECONDS
            )
            self._last_active[ws] = now
        if was_idle:
            await self._broadcast_presence(campaign_id)

    def is_user_present(self, campaign_id: int, user_id: int) -> bool:
        """v2.99.59 — single-user presence probe.

        Returns True when at least one open WebSocket in this
        campaign's channel is identified as ``user_id``. Used by the
        reaction-prompt router so popups for an offline player's PC
        fall back to the GM instead of vanishing into the void.

        Multi-tab is honored — any open tab for the user makes them
        "present" — so an OA prompt fires even if the player is on
        their character sheet in a second tab and not on the
        tabletop tab.
        """
        if user_id is None:
            return False
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            return False
        for ws in self._channels.get(campaign_id, ()):
            ident = self._identities.get(ws)
            if not ident:
                continue
            if ident.get("user_id") == uid:
                return True
        return False

    async def connect(
        self,
        campaign_id: int,
        ws: WebSocket,
        identity: Optional[dict] = None,
    ) -> None:
        await ws.accept()
        async with self._lock:
            self._channels[campaign_id].add(ws)
            if identity is not None:
                self._identities[ws] = dict(identity)
            # v2.1044.0 — a fresh connection is active by definition.
            self._last_active[ws] = time.monotonic()
        # Send current battle state to the newly connected client
        state = self._battle.get(campaign_id)
        if state:
            try:
                await ws.send_text(json.dumps({"type": "battle_update", "data": state}))
            except Exception:
                pass
        # Send the current presence roster to the new client
        # (private — every existing client already has it).
        try:
            await ws.send_text(json.dumps({
                "type": "presence_update",
                "data": {
                    "users": self.get_presence(campaign_id),
                    "idle_after_seconds": PRESENCE_IDLE_AFTER_SECONDS,
                },
            }, default=str))
        except Exception:
            pass
        # And broadcast the (possibly grown) roster to everyone else so
        # bubbles light up for the existing players. ``_broadcast_presence``
        # is a small wrapper around broadcast() that builds the payload
        # from get_presence; doing it inside the hub keeps the call sites
        # in tabletop_routes thin.
        await self._broadcast_presence(campaign_id)

    async def disconnect(self, campaign_id: int, ws: WebSocket) -> None:
        async with self._lock:
            self._channels[campaign_id].discard(ws)
            if not self._channels[campaign_id]:
                del self._channels[campaign_id]
            self._identities.pop(ws, None)
            self._last_active.pop(ws, None)
        await self._broadcast_presence(campaign_id)

    async def broadcast(
        self,
        campaign_id: int,
        message: dict,
        *,
        recipient_filter: Optional[Callable[[dict], bool]] = None,
    ) -> None:
        """Send ``message`` to every connected client on the campaign.

        v2.12.4: ``recipient_filter`` lets the caller restrict which
        clients receive the message. The filter is called with each
        connection's identity dict (``{user_id, display_name, color,
        is_gm}``) — return True to send, False to skip. None (default)
        means broadcast to everyone (the v2.9.0 behaviour).

        Used by ``/roll`` to keep ``gm_only`` rolls off non-GM clients
        and ``gm_and_roller`` rolls off everyone except the GM(s) and
        the rolling user. Server-side filtering is defense-in-depth on
        top of the existing client-side filter in ``roll_toast.js`` —
        a determined player watching the WS in devtools would
        otherwise read the raw data even when the toast was filtered.
        """
        text = json.dumps(message, default=str)
        # Snapshot to avoid mutation during iteration
        async with self._lock:
            recipients = list(self._channels.get(campaign_id, ()))
            # Capture identities alongside the WS so the filter has
            # what it needs without re-locking per send.
            identities = {ws: self._identities.get(ws, {}) for ws in recipients}
        dead = []
        for ws in recipients:
            if recipient_filter is not None:
                ident = identities.get(ws) or {}
                try:
                    if not recipient_filter(ident):
                        continue
                except Exception as e:  # noqa: BLE001
                    # A buggy filter shouldn't kill the broadcast for
                    # everyone — log + skip the problematic recipient.
                    log.warning("recipient_filter raised: %s", e)
                    continue
            try:
                await ws.send_text(text)
            except Exception as e:
                log.warning("ws send failed: %s", e)
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._channels.get(campaign_id, set()).discard(ws)
                    self._identities.pop(ws, None)
                    self._last_active.pop(ws, None)

    async def _broadcast_presence(self, campaign_id: int) -> None:
        """Send the current presence roster to every connected client
        for this campaign. Called from connect/disconnect; safe to call
        even when the campaign has zero connections (early-returns
        inside broadcast since there are no recipients)."""
        await self.broadcast(campaign_id, {
            "type": "presence_update",
            "data": {
                "users": self.get_presence(campaign_id),
                "idle_after_seconds": PRESENCE_IDLE_AFTER_SECONDS,
            },
        })


hub = CampaignHub()
