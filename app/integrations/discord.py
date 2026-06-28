"""Discord channel-webhook notifications (best-effort, opt-in).

v2.724.0. Posts short messages to a Discord channel webhook for in-app
events (currently: a new suggestion / issue report). Reuses the SAME webhook
the fail2ban ``discord-notify`` action uses (``FAIL2BAN_DISCORD_WEBHOOK_URL``)
so one channel receives both ban alerts and feedback pings — set it once in
``.env``.

Design (mirrors the cloudflare integration + the fail2ban action):
  - No webhook URL configured → every call is a graceful **no-op** (returns
    False). The feature is off until an operator opts in.
  - Network failures NEVER raise — a slow/unreachable webhook must not block
    or fail the user action that triggered the notification.
  - The webhook URL is an operator secret (their own Discord server); it
    lives in ``.env`` / compose env, never in the repo, and there is no
    in-repo mock (consistent with the fail2ban-side action + cloudflare
    bouncer, which call the real APIs too).
"""
from __future__ import annotations

import logging
import os

import httpx

_log = logging.getLogger("simplevtt.discord")

# Discord rejects content over 2000 chars; keep a margin.
_MAX_CONTENT = 1900


def discord_webhook_url() -> str:
    """The configured webhook URL, or "" when unset. Prefers a generic
    ``DISCORD_WEBHOOK_URL`` if an operator sets one, falling back to the
    fail2ban webhook so "the same webhook as fail2ban" works out of the box."""
    return (
        os.getenv("DISCORD_WEBHOOK_URL")
        or os.getenv("FAIL2BAN_DISCORD_WEBHOOK_URL")
        or ""
    ).strip()


def _username() -> str:
    return (os.getenv("FAIL2BAN_DISCORD_USERNAME") or "SimpleVTT").strip()


def discord_notifications_enabled() -> bool:
    return bool(discord_webhook_url())


async def post_discord(content: str) -> bool:
    """Best-effort POST of ``content`` to the Discord channel webhook.

    Returns True on a 2xx, False when no webhook is configured or the post
    fails. Never raises.
    """
    url = discord_webhook_url()
    if not url:
        return False
    payload = {"content": (content or "")[:_MAX_CONTENT], "username": _username()}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
        if resp.status_code >= 300:
            _log.warning("discord webhook returned %s", resp.status_code)
            return False
        return True
    except Exception:
        _log.warning("discord webhook post failed", exc_info=True)
        return False
