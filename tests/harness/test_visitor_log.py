"""Unit tests for ``app.visitor_log`` — the opt-in per-request
``visitor.request`` audit event (TODO.md P2 follow-up to the
v2.424.0–v2.477.0 security/audit arc).

Pure in-process (no httpx, no running container) even though they
live under ``tests/harness/`` — same pattern as ``test_audit_log.py``.
They assert on the two-gate interlock + the emitted line shape so the
fail2ban filter that consumes ``visitor.request`` stays in sync with
what the middleware actually writes.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

from app import visitor_log


def _fake_request(*, ip: str = "10.0.0.5", ua: str = "Mozilla/5.0 (pytest)", xff: str | None = None):
    """Minimal stand-in for fastapi.Request — mirrors the helper in
    ``test_audit_log.py``. Only ``client.host`` + ``headers`` are read."""
    headers = {"user-agent": ua}
    if xff is not None:
        headers["x-forwarded-for"] = xff
    return SimpleNamespace(client=SimpleNamespace(host=ip), headers=headers)


def _capture(caplog, fn):
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="simplevtt.audit"):
        fn()
    return [r.getMessage() for r in caplog.records if r.name == "simplevtt.audit"]


# ---- gate predicate -------------------------------------------------

def test_disabled_by_default(monkeypatch):
    """No env set → gate closed (default OFF)."""
    monkeypatch.delenv("VISITOR_REQUEST_LOG_ENABLED", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    assert visitor_log.visitor_request_log_enabled() is False


def test_flag_on_but_no_trusted_hop_stays_closed(monkeypatch):
    """The flag alone isn't enough — without TRUSTED_PROXY_HOPS>=1 the
    only IP we could record is the proxy's, so the interlock keeps the
    gate closed."""
    monkeypatch.setenv("VISITOR_REQUEST_LOG_ENABLED", "true")
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "0")
    assert visitor_log.visitor_request_log_enabled() is False


def test_trusted_hop_but_flag_off_stays_closed(monkeypatch):
    """A trusted hop without the explicit opt-in stays closed."""
    monkeypatch.delenv("VISITOR_REQUEST_LOG_ENABLED", raising=False)
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    assert visitor_log.visitor_request_log_enabled() is False


def test_both_gates_open(monkeypatch):
    monkeypatch.setenv("VISITOR_REQUEST_LOG_ENABLED", "true")
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    assert visitor_log.visitor_request_log_enabled() is True


def test_flag_accepts_truthy_synonyms(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    for raw in ("1", "true", "TRUE", "Yes", "on"):
        monkeypatch.setenv("VISITOR_REQUEST_LOG_ENABLED", raw)
        assert visitor_log.visitor_request_log_enabled() is True, raw
    for raw in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("VISITOR_REQUEST_LOG_ENABLED", raw)
        assert visitor_log.visitor_request_log_enabled() is False, raw


# ---- emission -------------------------------------------------------

def test_emit_noop_when_disabled(caplog, monkeypatch):
    """Gate closed → emit_visitor_request writes nothing."""
    monkeypatch.delenv("VISITOR_REQUEST_LOG_ENABLED", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    req = _fake_request()
    lines = _capture(caplog, lambda: visitor_log.emit_visitor_request(
        req, method="GET", path="/foo", status=200, ms=12,
    ))
    assert lines == []


def test_emit_canonical_line_when_enabled(caplog, monkeypatch):
    """Gate open → a single canonical ``visitor.request`` line with the
    method / path / status / ms fields the operator + fail2ban read."""
    monkeypatch.setenv("VISITOR_REQUEST_LOG_ENABLED", "true")
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    # XFF "client, proxy" with 1 trusted hop → real client is the left
    # entry (203.0.113.7), confirming we reuse the shared IP extractor.
    req = _fake_request(ip="10.0.0.5", xff="203.0.113.7, 10.0.0.99")
    lines = _capture(caplog, lambda: visitor_log.emit_visitor_request(
        req, method="GET", path="/campaign/7", status=200, ms=42,
    ))
    assert len(lines) == 1
    line = lines[0]
    assert line.startswith("visitor.request ")
    # IP comes from the trusted XFF entry, identical to every other
    # audit event for this client — fail2ban consistency.
    assert "ip=203.0.113.7" in line
    assert 'ua="Mozilla/5.0 (pytest)"' in line
    assert "method=GET" in line
    assert "path=/campaign/7" in line
    assert "status=200" in line
    assert "ms=42" in line


def test_emit_quotes_path_with_query_chars(caplog, monkeypatch):
    """A path that isn't a bare token (query string, spaces) gets
    quoted so the canonical-line parser doesn't split on it."""
    monkeypatch.setenv("VISITOR_REQUEST_LOG_ENABLED", "true")
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    req = _fake_request()
    lines = _capture(caplog, lambda: visitor_log.emit_visitor_request(
        req, method="GET", path="/search?q=a b", status=404, ms=3,
    ))
    assert len(lines) == 1
    assert 'path="/search?q=a b"' in lines[0]
    assert "status=404" in lines[0]
