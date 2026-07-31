"""Tests for the request-body size limit (v2.1037.0).

Unit tests on `app.main._request_body_too_large` (the pure predicate the
`_request_body_limit_mw` middleware calls). A live "spoof an oversized
Content-Length" integration test was intentionally omitted: sending a declared
length that doesn't match the transferred body stalls the HTTP client, and the
predicate + middleware wiring are trivial enough that the unit tests are the
reliable coverage.
"""
from __future__ import annotations

from app.main import _request_body_too_large


def test_predicate_allows_under_limit():
    assert _request_body_too_large("100", 512) is False


def test_predicate_rejects_over_limit():
    assert _request_body_too_large("513", 512) is True


def test_predicate_allows_missing_or_unparseable_header():
    assert _request_body_too_large(None, 512) is False
    assert _request_body_too_large("not-a-number", 512) is False


def test_predicate_disabled_when_limit_zero_or_negative():
    assert _request_body_too_large("999999999", 0) is False
    assert _request_body_too_large("999999999", -1) is False


def test_limit_resolves_from_env_or_512_mib_default():
    """The middleware's cap equals MAX_REQUEST_BODY_BYTES when set, else the
    512 MiB default (generous — bulk/video uploads pass; multi-GB floods are
    rejected)."""
    import os

    from app.main import _MAX_REQUEST_BODY_BYTES
    expected = int(os.getenv("MAX_REQUEST_BODY_BYTES") or 512 * 1024 * 1024)
    assert _MAX_REQUEST_BODY_BYTES == expected
