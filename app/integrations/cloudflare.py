"""Outbound Cloudflare API client — Phase 1 of
``docs/plans/cloudflare-edge-banning.md``.

Thin async wrapper around the IP Access Rules subset of Cloudflare's
v4 API. Stateless: reads the API token + zone id + base URL from
environment at call time so a hot-rotated token works without
restart, and so tests can flip the env vars via monkeypatch.

The three operations:

- ``add_ip_access_rule(ip, mode='block', notes='')`` — creates a
  rule against the configured zone. Returns the Cloudflare-side
  rule id.
- ``remove_ip_access_rule(rule_id)`` — idempotent delete; 404 is
  treated as success.
- ``list_ip_access_rules()`` — paginated list of active rules.

Three exception types:

- ``CloudflareDisabledError`` — the integration env vars aren't
  configured. Callers can catch this to gracefully skip rather
  than error a user-facing flow.
- ``CloudflareApiError`` — Cloudflare returned a non-2xx response
  or a success=False JSON body.
- ``CloudflareConnectionError`` — couldn't reach the API at all
  (network timeout, DNS, etc.).

Per the [Third-party APIs must be Docker Compose services](../../CLAUDE.md)
rule, the development docker-compose ships a wiremock service
under the ``dev`` profile that serves canned responses for these
three endpoints so the integration is testable without real
Cloudflare quota.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx


log = logging.getLogger(__name__)


# Default to the public Cloudflare API. The wiremock dev service
# overrides via ``CLOUDFLARE_API_BASE_URL=http://cloudflare-mock:8080/client/v4``.
_DEFAULT_API_BASE = "https://api.cloudflare.com/client/v4"


class CloudflareError(Exception):
    """Base for all client-emitted errors."""


class CloudflareDisabledError(CloudflareError):
    """Integration not configured. Raised before any HTTP call."""


class CloudflareApiError(CloudflareError):
    """Cloudflare returned a non-success response. Carries the HTTP
    status + truncated body so callers can build a useful audit
    log entry without leaking long API responses to logs."""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body[:500]  # truncate for log safety
        super().__init__(f"Cloudflare API returned {status_code}: {self.body}")


class CloudflareConnectionError(CloudflareError):
    """Couldn't reach the API at all (DNS / timeout / refused)."""


class _Config:
    __slots__ = ("api_token", "zone_id", "api_base_url")

    def __init__(self, api_token: str, zone_id: str, api_base_url: str):
        self.api_token = api_token
        self.zone_id = zone_id
        self.api_base_url = api_base_url.rstrip("/")


def _read_config() -> Optional[_Config]:
    """Read env at call time. Returns None when the integration
    isn't configured (any required field missing). Callers map
    None → ``CloudflareDisabledError`` so the explicit name shows
    up in logs.
    """
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    zone_id = os.environ.get("CLOUDFLARE_ZONE_ID", "").strip()
    if not api_token or not zone_id:
        return None
    base_url = os.environ.get("CLOUDFLARE_API_BASE_URL", "").strip() or _DEFAULT_API_BASE
    return _Config(api_token, zone_id, base_url)


def integration_enabled() -> bool:
    """Public predicate: is the Cloudflare CLIENT configured?

    Separate from the GM-facing feature gate (see
    ``cloudflare_banning_enabled``). An operator running the
    CrowdSec → Cloudflare bouncer path may want the client
    configured even when the in-app banning UI is disabled — this
    predicate is for the client; the UI gate is checked elsewhere.
    """
    return _read_config() is not None


def cloudflare_banning_enabled() -> bool:
    """Both the integration client AND the GM-facing button must be
    explicitly on for the admin UI to show the ban controls.
    Default closed — fresh deploys never expose the affordance.
    """
    if not integration_enabled():
        return False
    raw = os.environ.get("SIMPLEVTT_CLOUDFLARE_BANNING_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def cloudflare_cache_purge_enabled() -> bool:
    """v2.531.0 — gate for the deploy-time cache purge (see
    ``purge_cache``). Both the integration client AND an explicit
    ``SIMPLEVTT_CLOUDFLARE_CACHE_PURGE_ENABLED`` flag must be on. Default
    closed — fresh deploys never call the Cloudflare API on boot.
    """
    if not integration_enabled():
        return False
    raw = os.environ.get(
        "SIMPLEVTT_CLOUDFLARE_CACHE_PURGE_ENABLED", "",
    ).strip().lower()
    return raw in ("1", "true", "yes", "on")


# ─── HTTP operations ──────────────────────────────────────────────────


async def add_ip_access_rule(
    ip: str,
    *,
    mode: str = "block",
    notes: str = "",
) -> str:
    """Create an IP Access Rule against the configured zone. Returns
    the Cloudflare-side rule id (opaque string).

    Args:
        ip: dotted-quad IPv4 or v6 address. We don't validate the
            shape — let Cloudflare reject malformed inputs.
        mode: ``"block"`` (default 403 at edge), ``"challenge"``
            (Cloudflare CAPTCHA), or ``"whitelist"``. Anything else
            Cloudflare 400s.
        notes: free-form operator note attached to the rule for
            future review. Kept short — Cloudflare caps at 1024.
    """
    cfg = _read_config()
    if cfg is None:
        raise CloudflareDisabledError(
            "Cloudflare integration not configured "
            "(CLOUDFLARE_API_TOKEN + CLOUDFLARE_ZONE_ID required)"
        )
    payload = {
        "mode": mode,
        "configuration": {"target": "ip", "value": ip},
        "notes": (notes or "")[:1024],
    }
    url = f"{cfg.api_base_url}/zones/{cfg.zone_id}/firewall/access_rules/rules"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {cfg.api_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
        raise CloudflareConnectionError(str(e)) from e
    if resp.status_code != 200:
        raise CloudflareApiError(resp.status_code, resp.text)
    body = resp.json()
    if not body.get("success"):
        raise CloudflareApiError(resp.status_code, resp.text)
    result = body.get("result") or {}
    rule_id = result.get("id") or ""
    if not rule_id:
        raise CloudflareApiError(resp.status_code, "missing rule id in response")
    return rule_id


async def remove_ip_access_rule(rule_id: str) -> None:
    """Idempotent delete of a Cloudflare rule. A 404 from Cloudflare
    is logged + treated as success (the rule was already removed,
    possibly by an operator working in the Cloudflare dashboard).
    """
    cfg = _read_config()
    if cfg is None:
        raise CloudflareDisabledError(
            "Cloudflare integration not configured"
        )
    url = f"{cfg.api_base_url}/zones/{cfg.zone_id}/firewall/access_rules/rules/{rule_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                url,
                headers={"Authorization": f"Bearer {cfg.api_token}"},
            )
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
        raise CloudflareConnectionError(str(e)) from e
    if resp.status_code == 404:
        log.info("Cloudflare rule %s already gone — treating as success", rule_id)
        return
    if resp.status_code != 200:
        raise CloudflareApiError(resp.status_code, resp.text)


async def list_ip_access_rules(*, ip: Optional[str] = None) -> list[dict]:
    """List active IP Access Rules on the configured zone, optionally
    filtered to one IP. Returns the raw rule dicts from Cloudflare —
    the route layer projects the fields it needs.
    """
    cfg = _read_config()
    if cfg is None:
        raise CloudflareDisabledError(
            "Cloudflare integration not configured"
        )
    url = f"{cfg.api_base_url}/zones/{cfg.zone_id}/firewall/access_rules/rules"
    params: dict = {"per_page": 100}
    if ip:
        params["configuration.value"] = ip
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {cfg.api_token}"},
                params=params,
            )
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
        raise CloudflareConnectionError(str(e)) from e
    if resp.status_code != 200:
        raise CloudflareApiError(resp.status_code, resp.text)
    body = resp.json()
    if not body.get("success"):
        raise CloudflareApiError(resp.status_code, resp.text)
    result = body.get("result") or []
    return result if isinstance(result, list) else []


async def purge_cache(*, files: Optional[list[str]] = None) -> None:
    """v2.531.0 — purge the configured zone's Cloudflare cache. With no
    ``files`` (the default), purges EVERYTHING — the deploy-time
    cache-bust so a freshly-shipped ``APP_VERSION``'s HTML/JS isn't
    served stale from the edge after a restart. Pass ``files`` (a list
    of absolute URLs) to purge only those.

    POSTs ``{"purge_everything": true}`` (or ``{"files": [...]}``) to
    ``/zones/{zone}/purge_cache``. Raises ``CloudflareDisabledError``
    when unconfigured, ``CloudflareApiError`` on a non-success response,
    or ``CloudflareConnectionError`` on a network failure — the startup
    caller swallows these so a purge failure never blocks boot.
    """
    cfg = _read_config()
    if cfg is None:
        raise CloudflareDisabledError(
            "Cloudflare integration not configured "
            "(CLOUDFLARE_API_TOKEN + CLOUDFLARE_ZONE_ID required)"
        )
    payload: dict = {"files": list(files)} if files else {"purge_everything": True}
    url = f"{cfg.api_base_url}/zones/{cfg.zone_id}/purge_cache"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {cfg.api_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
        raise CloudflareConnectionError(str(e)) from e
    if resp.status_code != 200:
        raise CloudflareApiError(resp.status_code, resp.text)
    body = resp.json()
    if not body.get("success"):
        raise CloudflareApiError(resp.status_code, resp.text)
