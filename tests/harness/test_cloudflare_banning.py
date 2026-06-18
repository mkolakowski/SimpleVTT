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


# ─── In-process HTTP unit tests via httpx.AsyncClient monkeypatch ─────
#
# v2.428.0 — closes the v2.427.0 wiremock-deferred regression test by
# exercising the real httpx call paths in-process. monkeypatches
# httpx.AsyncClient with a tiny fake that captures the request and
# returns canned responses. Covers what the wiremock-driven smoke
# test would have covered:
#
#   - add_ip_access_rule sends the right URL + Bearer header + body
#     shape, and parses the rule_id out of a success response.
#   - remove_ip_access_rule treats 404 as idempotent-success (the
#     rule was already gone — e.g. an operator removed it via the
#     Cloudflare dashboard).
#   - list_ip_access_rules returns the result array.
#   - CloudflareApiError fires on non-200 responses.
#   - CloudflareApiError fires on success=false responses.
#   - CloudflareDisabledError fires when env vars are unset, with no
#     HTTP call attempted.


class _FakeResp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        if isinstance(self._body, dict):
            return self._body
        import json
        return json.loads(self._body)

    @property
    def text(self):
        if isinstance(self._body, dict):
            import json
            return json.dumps(self._body)
        return self._body


class _FakeClient:
    """Captures the request and returns canned responses."""
    captured: list = []
    responses: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, *, headers=None, json=None, **kw):
        _FakeClient.captured.append({"method": "POST", "url": url, "headers": headers, "body": json})
        return _FakeClient.responses.get("POST", _FakeResp(200, {"success": True, "result": {"id": "captured-rule-id"}}))

    async def delete(self, url, *, headers=None, **kw):
        _FakeClient.captured.append({"method": "DELETE", "url": url, "headers": headers})
        return _FakeClient.responses.get("DELETE", _FakeResp(200, {"success": True, "result": {"id": "removed"}}))

    async def get(self, url, *, headers=None, params=None, **kw):
        _FakeClient.captured.append({"method": "GET", "url": url, "headers": headers, "params": params})
        return _FakeClient.responses.get("GET", _FakeResp(200, {
            "success": True,
            "result": [{"id": "rule-1", "configuration": {"value": "1.2.3.4"}, "mode": "block"}],
        }))


@pytest.fixture
def fake_cf_client(monkeypatch):
    """Wires the FakeClient into httpx + sets the env vars the client
    code reads at call time. Clears the captured/responses state at
    setup so tests don't bleed into each other.
    """
    import httpx as _httpx
    monkeypatch.setattr(_httpx, "AsyncClient", _FakeClient)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-token-xyz")
    monkeypatch.setenv("CLOUDFLARE_ZONE_ID", "test-zone-abc")
    monkeypatch.setenv("CLOUDFLARE_API_BASE_URL", "https://api.test.example/v4")
    _FakeClient.captured = []
    _FakeClient.responses = {}
    yield _FakeClient


async def test_add_ip_access_rule_sends_correct_request(fake_cf_client):
    rule_id = await cf.add_ip_access_rule("198.51.100.10", notes="test ban")
    assert rule_id == "captured-rule-id"
    assert len(fake_cf_client.captured) == 1
    req = fake_cf_client.captured[0]
    assert req["method"] == "POST"
    assert req["url"] == "https://api.test.example/v4/zones/test-zone-abc/firewall/access_rules/rules"
    assert req["headers"]["Authorization"] == "Bearer test-token-xyz"
    assert req["headers"]["Content-Type"] == "application/json"
    body = req["body"]
    assert body["mode"] == "block"
    assert body["configuration"]["target"] == "ip"
    assert body["configuration"]["value"] == "198.51.100.10"
    assert body["notes"] == "test ban"


async def test_add_ip_access_rule_raises_on_non_200(fake_cf_client):
    fake_cf_client.responses["POST"] = _FakeResp(500, {"success": False, "errors": ["internal"]})
    with pytest.raises(cf.CloudflareApiError) as exc:
        await cf.add_ip_access_rule("198.51.100.10")
    assert exc.value.status_code == 500


async def test_add_ip_access_rule_raises_on_success_false(fake_cf_client):
    fake_cf_client.responses["POST"] = _FakeResp(200, {"success": False, "errors": [{"code": 6003, "message": "Invalid token"}]})
    with pytest.raises(cf.CloudflareApiError):
        await cf.add_ip_access_rule("198.51.100.10")


async def test_add_ip_access_rule_raises_disabled_when_env_unset(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ZONE_ID", raising=False)
    with pytest.raises(cf.CloudflareDisabledError):
        await cf.add_ip_access_rule("198.51.100.10")


async def test_remove_ip_access_rule_sends_delete(fake_cf_client):
    await cf.remove_ip_access_rule("rule-xyz")
    req = fake_cf_client.captured[0]
    assert req["method"] == "DELETE"
    assert req["url"].endswith("/rules/rule-xyz")


async def test_remove_ip_access_rule_treats_404_as_success(fake_cf_client):
    """Idempotent delete: a 404 from Cloudflare means the rule was
    already gone (operator removed it via dashboard, etc.). Should
    not raise."""
    fake_cf_client.responses["DELETE"] = _FakeResp(404, {"success": False, "errors": ["not found"]})
    # Should not raise.
    await cf.remove_ip_access_rule("already-gone")


async def test_list_ip_access_rules_returns_array(fake_cf_client):
    rules = await cf.list_ip_access_rules()
    assert isinstance(rules, list)
    assert len(rules) == 1
    assert rules[0]["id"] == "rule-1"
    # Verify the GET request shape.
    req = fake_cf_client.captured[0]
    assert req["method"] == "GET"
    assert req["params"] == {"per_page": 100}


async def test_list_ip_access_rules_with_ip_filter(fake_cf_client):
    await cf.list_ip_access_rules(ip="203.0.113.7")
    req = fake_cf_client.captured[0]
    assert req["params"]["configuration.value"] == "203.0.113.7"


async def test_notes_truncated_at_1024_chars(fake_cf_client):
    long_notes = "a" * 2000
    await cf.add_ip_access_rule("198.51.100.10", notes=long_notes)
    body = fake_cf_client.captured[0]["body"]
    assert len(body["notes"]) == 1024
