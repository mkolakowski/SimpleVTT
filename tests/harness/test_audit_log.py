"""Unit tests for ``app.audit_log`` — the canonical structured
emission helper from
``docs/plans/fail2ban-crowdsec-integration.md``.

These tests are pure in-process (no httpx, no running container)
even though they live under ``tests/harness/``. They assert on the
emitted log-line shape so the fail2ban / CrowdSec filters stay in
sync with what the app actually writes.
"""
from __future__ import annotations

import logging
import os
import re
from types import SimpleNamespace

import pytest

from app import audit_log


# Parser regex from the plan doc. Both fail2ban filters and the
# (future) CrowdSec parser pipeline read this exact shape.
_AUDIT_LINE_RE = re.compile(
    r"^(?P<event>[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)\s+(?P<kvs>.*)$"
)


def _fake_request(*, ip: str = "1.2.3.4", ua: str = "Mozilla/5.0 (pytest)", xff: str | None = None):
    """Build a minimal stand-in for fastapi.Request that ``audit_log``'s
    helpers can read. Only the ``client.host`` + ``headers`` lookups
    are exercised."""
    headers = {"user-agent": ua}
    if xff is not None:
        headers["x-forwarded-for"] = xff
    return SimpleNamespace(
        client=SimpleNamespace(host=ip),
        headers=headers,
    )


def _capture(caplog, fn):
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="simplevtt.audit"):
        fn()
    return [r.getMessage() for r in caplog.records if r.name == "simplevtt.audit"]


def test_emits_canonical_line_with_required_keys(caplog):
    req = _fake_request()
    lines = _capture(caplog, lambda: audit_log.audit(
        "auth.login_failed", level=logging.WARNING, request=req, username="alice@example.com"
    ))
    assert len(lines) == 1
    line = lines[0]
    m = _AUDIT_LINE_RE.match(line)
    assert m, f"line did not match parser regex: {line!r}"
    assert m.group("event") == "auth.login_failed"
    # ip + ua + username are all present and in order.
    assert "ip=1.2.3.4" in line
    # UA contains whitespace → must be double-quoted.
    assert 'ua="Mozilla/5.0 (pytest)"' in line
    assert "username=alice@example.com" in line


def test_login_ok_at_info_level(caplog):
    req = _fake_request()
    lines = _capture(caplog, lambda: audit_log.audit(
        "auth.login_ok", request=req, user_id=42
    ))
    assert len(lines) == 1
    assert lines[0].startswith("auth.login_ok ")
    assert "user_id=42" in lines[0]


def test_x_forwarded_for_ignored_by_default(caplog, monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    req = _fake_request(ip="10.0.0.5", xff="203.0.113.7, 10.0.0.99")
    lines = _capture(caplog, lambda: audit_log.audit(
        "auth.login_failed", request=req, username="x"
    ))
    # Default trusts 0 hops — XFF is ignored entirely; client IP wins.
    assert "ip=10.0.0.5" in lines[0]
    assert "203.0.113.7" not in lines[0]


def test_x_forwarded_for_trusted_when_hops_set(caplog, monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    req = _fake_request(ip="10.0.0.5", xff="203.0.113.7, 10.0.0.99")
    lines = _capture(caplog, lambda: audit_log.audit(
        "auth.login_failed", request=req, username="x"
    ))
    # With 1 trusted hop, the rightmost entry (10.0.0.99) is the trusted
    # proxy and the *previous* entry (203.0.113.7) is the real client.
    assert "ip=203.0.113.7" in lines[0]


def test_x_forwarded_for_multi_hop(caplog, monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
    req = _fake_request(ip="10.0.0.5", xff="198.51.100.10, 10.0.0.99, 10.0.0.5")
    lines = _capture(caplog, lambda: audit_log.audit(
        "auth.login_failed", request=req, username="x"
    ))
    # XFF = "client, proxy1, proxy2" — with 2 trusted hops the trusted
    # entries are the last 2 (10.0.0.99 + 10.0.0.5) and the real client
    # is what the closest-trusted-proxy saw, which is parts[-(hops+1)]
    # = parts[0] = 198.51.100.10.
    assert "ip=198.51.100.10" in lines[0]


def test_x_forwarded_for_hops_exceeds_chain(caplog, monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "10")
    req = _fake_request(ip="10.0.0.5", xff="198.51.100.10, 10.0.0.99")
    lines = _capture(caplog, lambda: audit_log.audit(
        "auth.login_failed", request=req, username="x"
    ))
    # More trusted hops than entries in the chain — clamps to the
    # leftmost (the original client). This protects against a
    # mis-configured TRUSTED_PROXY_HOPS reading off the front of the
    # array.
    assert "ip=198.51.100.10" in lines[0]


def test_unknown_ip_when_no_request(caplog, monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    lines = _capture(caplog, lambda: audit_log.audit(
        "auth.login_failed", username="bg-task"
    ))
    assert "ip=unknown" in lines[0]
    assert 'ua=""' in lines[0]


def test_value_quoting_handles_whitespace_and_quotes(caplog):
    req = _fake_request(ua='Mozilla/5.0 "weird"')
    lines = _capture(caplog, lambda: audit_log.audit(
        "auth.login_failed", request=req, username="alice@example.com",
        notes="this has spaces and a \" quote"
    ))
    # UA contains whitespace + a literal quote — must be quoted +
    # escaped.
    assert 'ua="Mozilla/5.0 \\"weird\\""' in lines[0]
    # notes value also gets quoted because of whitespace.
    assert 'notes="this has spaces and a \\" quote"' in lines[0]
    # username is bare-token-safe.
    assert "username=alice@example.com" in lines[0]


def test_explicit_ip_kv_overrides_request(caplog):
    req = _fake_request(ip="1.2.3.4")
    lines = _capture(caplog, lambda: audit_log.audit(
        "auth.login_failed", request=req, ip="9.9.9.9", username="x"
    ))
    assert "ip=9.9.9.9" in lines[0]
    assert "ip=1.2.3.4" not in lines[0]


def test_bool_and_int_render_as_bare_tokens(caplog):
    req = _fake_request()
    lines = _capture(caplog, lambda: audit_log.audit(
        "auth.login_ok", request=req, user_id=42, is_admin=True, is_demo=False
    ))
    assert "user_id=42" in lines[0]
    assert "is_admin=true" in lines[0]
    assert "is_demo=false" in lines[0]


def test_invalid_trusted_proxy_hops_falls_back_to_zero(caplog, monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "not-a-number")
    req = _fake_request(ip="10.0.0.5", xff="203.0.113.7")
    lines = _capture(caplog, lambda: audit_log.audit(
        "auth.login_failed", request=req, username="x"
    ))
    # Falls back to 0 trusted hops — XFF ignored, client IP wins.
    assert "ip=10.0.0.5" in lines[0]


def test_negative_trusted_proxy_hops_falls_back_to_zero(caplog, monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "-3")
    req = _fake_request(ip="10.0.0.5", xff="203.0.113.7")
    lines = _capture(caplog, lambda: audit_log.audit(
        "auth.login_failed", request=req, username="x"
    ))
    # Negative hops clamp to 0.
    assert "ip=10.0.0.5" in lines[0]
