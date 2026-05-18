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
from collections import defaultdict
from typing import Callable, Dict, Optional, Set

from fastapi import WebSocket

log = logging.getLogger(__name__)


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
        self._lock = asyncio.Lock()
        self._battle: Dict[int, dict] = {}

    def get_battle(self, campaign_id: int) -> dict | None:
        return self._battle.get(campaign_id)

    def set_battle(self, campaign_id: int, state: dict) -> None:
        self._battle[campaign_id] = state

    def get_presence(self, campaign_id: int) -> list[dict]:
        """Return the deduped list of users currently connected to this
        campaign's WS hub. Each entry: ``{user_id, display_name, color,
        is_gm}``. Order isn't guaranteed; the client sorts at render
        time for stability.
        """
        seen: dict[int, dict] = {}
        for ws in self._channels.get(campaign_id, ()):
            ident = self._identities.get(ws)
            if not ident:
                continue
            uid = ident.get("user_id")
            if uid is None or uid in seen:
                continue
            seen[uid] = {
                "user_id": uid,
                "display_name": ident.get("display_name") or "Player",
                "color": ident.get("color"),
                "is_gm": bool(ident.get("is_gm")),
            }
        return list(seen.values())

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
                "data": {"users": self.get_presence(campaign_id)},
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

    async def _broadcast_presence(self, campaign_id: int) -> None:
        """Send the current presence roster to every connected client
        for this campaign. Called from connect/disconnect; safe to call
        even when the campaign has zero connections (early-returns
        inside broadcast since there are no recipients)."""
        await self.broadcast(campaign_id, {
            "type": "presence_update",
            "data": {"users": self.get_presence(campaign_id)},
        })


hub = CampaignHub()
