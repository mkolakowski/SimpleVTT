"""Harness tests for the v2.427.0 Cloudflare edge-banning
integration — Phase 1 of ``docs/plans/cloudflare-edge-banning.md``.

Two test families, mirroring the v2.425.0 demo-magic-link pattern:

1. **In-process unit tests** on the predicate +
   ``_read_config`` helper. The async HTTP methods themselves are
   exercised end-to-end against the wiremock service (Phase 1B
   compose-override smoke test) — Phase 1's in-process tests don't
   need to mock httpx because the wiremock is the source of truth.

2. **Integration tests** against the running dev container with
   the gates off (default). All three endpoints return 503 when
   the feature isn't configured + enabled, so the harness asserts
   the gate-off shape — protects against a regression that
   exposes the endpoints without configuration.

Happy-path testing (admin clicks "Ban at edge" → SimpleVTT calls
wiremock → audit row written → list returns the row) is exercised
manually by booting the ``dev`` profile (``docker compose --profile
dev up cloudflare-mock``) + flipping the env vars. A permanent
end-to-end regression test lives with the test-compose override
filed for Phase 2.
"""
from __future__ import annotations

import httpx
import pytest

from app.integrations import cloudflare as cf

from .helpers import BASE_URL, login_client


# ─── Unit tests on the predicate + config helpers ─────────────────────


def test_integration_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ZONE_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_BASE_URL", raising=False)
    assert cf.integration_enabled() is False
    assert cf._read_config() is None


def test_integration_requires_both_token_and_zone(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token-only")
    monkeypatch.delenv("CLOUDFLARE_ZONE_ID", raising=False)
    assert cf.integration_enabled() is False, "token without zone shouldn't enable"

    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", "zone-only")
    assert cf.integration_enabled() is False, "zone without token shouldn't enable"

    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "real-token")
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", "real-zone")
    assert cf.integration_enabled() is True, "both set should enable the client"


def test_integration_uses_custom_base_url(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "real-token")
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", "real-zone")
    monkeypatch.setenv("CLOUDFLARE_API_BASE_URL", "http://cloudflare-mock:8080/client/v4/")
    cfg = cf._read_config()
    assert cfg is not None
    # Trailing slash stripped — URL composition is base + "/zones/..."
    assert cfg.api_base_url == "http://cloudflare-mock:8080/client/v4"


def test_integration_defaults_to_public_api(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "real-token")
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", "real-zone")
    monkeypatch.delenv("CLOUDFLARE_API_BASE_URL", raising=False)
    cfg = cf._read_config()
    assert cfg is not None
    assert cfg.api_base_url == "https://api.cloudflare.com/client/v4"


def test_banning_requires_both_client_and_ui_gate(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "real-token")
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", "real-zone")

    # Client configured + UI gate OFF → banning disabled.
    monkeypatch.delenv("SIMPLEVTT_CLOUDFLARE_BANNING_ENABLED", raising=False)
    assert cf.cloudflare_banning_enabled() is False, "UI gate off → no banning UI"

    # Client configured + UI gate ON → banning enabled.
    monkeypatch.setenv("SIMPLEVTT_CLOUDFLARE_BANNING_ENABLED", "true")
    assert cf.cloudflare_banning_enabled() is True, "both set → banning UI live"

    # Client NOT configured + UI gate ON → still disabled.
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    assert cf.cloudflare_banning_enabled() is False, "client missing → UI hidden"


def test_banning_gate_accepts_truthy_variants(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "real-token")
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", "real-zone")
    for truthy in ("1", "true", "TRUE", "yes", "YES", "on", "ON"):
        monkeypatch.setenv("SIMPLEVTT_CLOUDFLARE_BANNING_ENABLED", truthy)
        assert cf.cloudflare_banning_enabled() is True, f"{truthy!r} should enable"
    for falsy in ("0", "false", "FALSE", "no", "off", "", "garbage"):
        monkeypatch.setenv("SIMPLEVTT_CLOUDFLARE_BANNING_ENABLED", falsy)
        assert cf.cloudflare_banning_enabled() is False, f"{falsy!r} should not enable"


# ─── Integration tests against the running container ──────────────────


async def _admin_client():
    return await login_client("demo-gm@example.com", "demopass")


async def test_ban_ip_returns_503_when_gate_off():
    """Default dev container: client env vars unset → gate off → 503
    even for an admin. Defense in depth on top of the UI hiding the
    affordance.
    """
    client = await _admin_client()
    try:
        resp = await client.post(
            "/admin/cloudflare/ban_ip",
            json={"ip": "198.51.100.10", "notes": "harness probe"},
            follow_redirects=False,
        )
    finally:
        await client.aclose()
    assert resp.status_code == 503
    body = resp.json()
    assert body.get("detail") == "cloudflare_banning_not_configured"


async def test_unban_ip_returns_503_when_gate_off():
    client = await _admin_client()
    try:
        resp = await client.post(
            "/admin/cloudflare/unban_ip",
            json={"rule_id": "abc123"},
            follow_redirects=False,
        )
    finally:
        await client.aclose()
    assert resp.status_code == 503


async def test_edge_bans_list_returns_503_when_gate_off():
    client = await _admin_client()
    try:
        resp = await client.get("/admin/cloudflare/edge_bans", follow_redirects=False)
    finally:
        await client.aclose()
    assert resp.status_code == 503


async def test_ban_ip_returns_403_for_non_admin():
    """Non-admin auth still gets rejected even before the gate
    check. require_admin fires first by design (same pattern as
    demo-magic-link mint endpoint) so the standard `/login`
    redirect still works for users exploring the UI.
    """
    client = await login_client("demo-alice@example.com", "demopass")
    try:
        resp = await client.post(
            "/admin/cloudflare/ban_ip",
            json={"ip": "198.51.100.10"},
            follow_redirects=False,
        )
    finally:
        await client.aclose()
    assert resp.status_code == 403


async def test_ban_ip_returns_401_for_anonymous():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0, follow_redirects=False) as client:
        resp = await client.post(
            "/admin/cloudflare/ban_ip",
            json={"ip": "198.51.100.10"},
        )
    assert resp.status_code == 401
