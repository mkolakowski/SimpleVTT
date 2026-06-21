"""Remove Cloudflare edge bans (IP Access Rules) for an IP.

When the admin-center "Unban" button fires, it should clear the IP
everywhere it might be banned — the local fail2ban jails (via the
control spool) AND the Cloudflare edge, if bans were pushed there (the
fail2ban ``cloudflare-bouncer`` action or the in-app "Ban IP at edge"
button). This module is the Cloudflare side.

It wraps the existing async client in ``app/integrations/cloudflare.py``
— no new HTTP code — and is dependency-light (httpx, no FastAPI) so it
can be unit-tested in-process with the cloudflare functions
monkeypatched.

Gating: uses ``integration_enabled()`` (the API client is configured),
NOT the GM-facing ban-button gate — unbanning is always safe to offer
when the client can talk to Cloudflare, even if the ban *button* is
hidden.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..integrations import cloudflare

log = logging.getLogger("simplevtt.admin_center")

# Rule modes that represent a *ban* we'd want to lift (not a whitelist).
_BAN_MODES = {"block", "challenge", "js_challenge", "managed_challenge"}


async def unban_ip(ip: str) -> Optional[int]:
    """Remove Cloudflare ban rules targeting ``ip``.

    Returns the number of rules removed, or ``None`` when the Cloudflare
    client isn't configured (so the caller can omit any edge-related UI).
    Never raises — a Cloudflare hiccup must not break the local unban.
    """
    if not cloudflare.integration_enabled():
        return None
    try:
        rules = await cloudflare.list_ip_access_rules(ip=ip)
    except cloudflare.CloudflareError as e:  # noqa: BLE001 — degrade gracefully
        log.warning("cloudflare unban: list failed for ip=%s: %s", ip, e)
        return None

    removed = 0
    for rule in rules:
        rule_id = rule.get("id")
        cfg = rule.get("configuration") or {}
        # Only delete block/challenge rules that target exactly this IP.
        if (
            rule_id
            and cfg.get("value") == ip
            and rule.get("mode") in _BAN_MODES
        ):
            try:
                await cloudflare.remove_ip_access_rule(rule_id)
                removed += 1
            except cloudflare.CloudflareError as e:  # noqa: BLE001
                log.warning(
                    "cloudflare unban: delete rule %s for ip=%s failed: %s",
                    rule_id, ip, e,
                )
    if removed:
        log.info("cloudflare unban: removed %d edge rule(s) for ip=%s", removed, ip)
    return removed
