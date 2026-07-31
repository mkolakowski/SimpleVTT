"""In-process unit tests for post-login redirect scrubbing (v2.1036.1).

`app.auth.safe_next_path` (and the mirror `_safe_next_path` in
`app.routes.auth_routes`) must reject open-redirect targets — including the
backslash-normalization bypass (`/\\evil.com` → browser reads `//evil.com`).
"""
from __future__ import annotations

import pytest

from app.auth import safe_next_path
from app.routes.auth_routes import _safe_next_path

_IMPLS = (safe_next_path, _safe_next_path)


@pytest.mark.parametrize("fn", _IMPLS)
@pytest.mark.parametrize("evil", [
    "//evil.com",
    "/\\evil.com",         # backslash → normalizes to //evil.com
    "\\\\evil.com",        # double backslash
    "/\\/evil.com",
    "https://evil.com",
    "/%5cevil.com",        # url-encoded backslash
    "/%5Cevil.com",
    "javascript:alert(1)",
    "/foo\r\nSet-Cookie: x=1",   # CRLF header-injection smuggling
    "/foo\tbar",
])
def test_open_redirect_targets_rejected(fn, evil):
    """Every hostile target collapses to the safe root path."""
    assert fn(evil) == "/"


@pytest.mark.parametrize("fn", _IMPLS)
@pytest.mark.parametrize("good", [
    "/",
    "/campaign/1",
    "/campaign/1/tabletop",
    "/wiki/readme",
])
def test_legitimate_same_origin_paths_preserved(fn, good):
    assert fn(good) == good


@pytest.mark.parametrize("fn", _IMPLS)
def test_empty_and_none_fall_back_to_root(fn):
    assert fn("") == "/"
    assert fn(None) == "/"
