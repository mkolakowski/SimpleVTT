"""Per-campaign WebSocket hub.

Each campaign has a set of connected clients. Any message accepted by the
HTTP API (token move, dice roll, chat) is broadcast to that campaign's
clients.

Clients receive JSON messages of shape: {"type": "...", "data": {...}}.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Dict, Set

from fastapi import WebSocket

log = logging.getLogger(__name__)


class CampaignHub:
    def __init__(self) -> None:
        self._channels: Dict[int, Set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._battle: Dict[int, dict] = {}

    def get_battle(self, campaign_id: int) -> dict | None:
        return self._battle.get(campaign_id)

    def set_battle(self, campaign_id: int, state: dict) -> None:
        self._battle[campaign_id] = state

    async def connect(self, campaign_id: int, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._channels[campaign_id].add(ws)
        # Send current battle state to the newly connected client
        state = self._battle.get(campaign_id)
        if state:
            try:
                await ws.send_text(json.dumps({"type": "battle_update", "data": state}))
            except Exception:
                pass

    async def disconnect(self, campaign_id: int, ws: WebSocket) -> None:
        async with self._lock:
            self._channels[campaign_id].discard(ws)
            if not self._channels[campaign_id]:
                del self._channels[campaign_id]

    async def broadcast(self, campaign_id: int, message: dict) -> None:
        text = json.dumps(message, default=str)
        # Snapshot to avoid mutation during iteration
        async with self._lock:
            recipients = list(self._channels.get(campaign_id, ()))
        dead = []
        for ws in recipients:
            try:
                await ws.send_text(text)
            except Exception as e:
                log.warning("ws send failed: %s", e)
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._channels.get(campaign_id, set()).discard(ws)


hub = CampaignHub()
