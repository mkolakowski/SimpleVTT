"""Harness tests for ``app.routes.demo_magic_link_routes`` — Phase 1
of ``docs/plans/demo-magic-link.md``.

Two test families:

1. **In-process unit tests** on the HMAC mint/verify helpers
   (``mint_token`` / ``verify_token``). These exercise the
   substrate directly without hitting the running container — the
   single-use enforcement is harder to test that way (it needs a
   DB session), so it's covered by the integration tests below.

2. **Integration tests** against the running container. The dev
   container boots with ``DEMO_MODE=false`` and
   ``SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED=false`` so the only
   integration-level behavior we can assert without a second
   container is the gate-off path: both endpoints return 404.

   The happy-path end-to-end test (mint via admin + verify via
   public URL + replay 401) is filed for the demo-instance test
   environment that doesn't exist today. Phase 2 may add a
   docker-compose override for it.
"""
from __future__ import annotations

import os

import httpx
import pytest

from app import demo_magic_link as mlr

from .helpers import BASE_URL


_DEMO_SUB = "demo-gm@example.com"


# ─── Unit tests on the mint/verify helpers ────────────────────────────


def test_mint_then_verify_roundtrip():
    token = mlr.mint_token(_DEMO_SUB)
    assert "." in token  # itsdangerous compact: <payload>.<sig>
    result = mlr.verify_token(token)
    assert result.ok
    assert result.sub == _DEMO_SUB
    assert result.jti
    # jti is 16 random bytes urlsafe-base64 — 22 chars (no padding).
    assert len(result.jti) == 22


def test_verify_rejects_tampered_payload():
    token = mlr.mint_token(_DEMO_SUB)
    # Flip a character in the payload segment — the signature is now
    # for a different payload, so loads() raises BadSignature.
    head, sep, tail = token.partition(".")
    # Flip the first character; it's base64url so this stays valid b64
    # but the underlying payload changes.
    tampered_head = ("a" if head[0] != "a" else "b") + head[1:]
    tampered = tampered_head + sep + tail
    result = mlr.verify_token(tampered)
    assert not result.ok
    assert result.reason == "signature"


def test_verify_rejects_tampered_signature():
    token = mlr.mint_token(_DEMO_SUB)
    head, sep, tail = token.partition(".")
    tampered_tail = ("a" if tail[0] != "a" else "b") + tail[1:]
    tampered = head + sep + tampered_tail
    result = mlr.verify_token(tampered)
    assert not result.ok
    assert result.reason == "signature"


def test_verify_rejects_empty_token():
    result = mlr.verify_token("")
    assert not result.ok
    assert result.reason == "signature"


def test_verify_rejects_token_without_dot():
    # A token with no separator can't be a real itsdangerous blob.
    result = mlr.verify_token("not-a-real-token")
    assert not result.ok
    assert result.reason == "signature"


def test_verify_rejects_garbage_token():
    # Bytes that look valid-ish but won't decode/verify.
    result = mlr.verify_token("aaaa.bbbb.cccc")
    assert not result.ok
    assert result.reason == "signature"


def test_jti_is_unique_per_mint():
    # Successive mints produce different jtis even for the same sub.
    seen = set()
    for _ in range(20):
        token = mlr.mint_token(_DEMO_SUB)
        result = mlr.verify_token(token)
        assert result.ok
        assert result.jti not in seen, "jti collision — secrets.token_urlsafe broken?"
        seen.add(result.jti)


def test_gate_off_by_default(monkeypatch):
    # In a normal CI environment neither env var is set.
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED", raising=False)
    # Bypass the lru_cache on get_settings so the env-var delete is honored.
    from app.config import get_settings
    get_settings.cache_clear()
    assert mlr.magic_link_enabled() is False


def test_gate_requires_both_env_vars(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.delenv("SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED", raising=False)
    get_settings.cache_clear()
    assert mlr.magic_link_enabled() is False, "DEMO_MODE alone shouldn't open the gate"

    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setenv("SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED", "true")
    get_settings.cache_clear()
    assert mlr.magic_link_enabled() is False, "MAGIC_LINK var alone shouldn't open the gate"

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED", "true")
    get_settings.cache_clear()
    assert mlr.magic_link_enabled() is True, "both gates set should open the feature"


def test_gate_accepts_truthy_variants(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    for truthy in ("1", "true", "TRUE", "yes", "YES", "on", "ON"):
        monkeypatch.setenv("SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED", truthy)
        assert mlr.magic_link_enabled() is True, f"variant {truthy!r} should open the gate"
    for falsy in ("0", "false", "FALSE", "no", "off", "", "random"):
        monkeypatch.setenv("SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED", falsy)
        assert mlr.magic_link_enabled() is False, f"variant {falsy!r} should not open the gate"


# ─── Integration tests against the running container ──────────────────
#
# Dev container default: DEMO_MODE=false, SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED
# unset → both endpoints 404. These tests assert the gate-off
# behavior so a regression that accidentally re-opens the gate fails
# loudly.


async def test_demo_login_endpoint_404_when_gate_off():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0, follow_redirects=False) as client:
        resp = await client.get("/demo-login?token=anything")
    if resp.status_code == 401:
        pytest.skip(
            "gate is OPEN on the running container — skipping gate-off "
            "404 assertion. The happy-path tests above cover the gate-on shape."
        )
    # Gate off → 404. The /login.html bouncer in main.py shouldn't
    # intercept because the request is a raw GET, not a guarded API.
    assert resp.status_code == 404


# v2.581.0 — the in-app mint route (`POST /admin/demo/mint-magic-link`) was
# retired (moved to the Admin Center, Phase 4 of
# docs/plans/admin-center-consolidation.md). That it's gone is asserted by
# test_admin_routes_retired.py; the Center's mint is covered by
# test_admin_center.py::test_tools_mint_magic_link. The happy-path below now
# mints container-side via the Center (same SECRET_KEY → tokens verify at the
# app's /demo-login), which also exercises the real cross-service contract.

ADMIN_CENTER_BASE_URL = os.getenv("ADMIN_CENTER_BASE_URL", "http://localhost:8015")


def _env_file_value(key: str, default: str = "") -> str:
    """Read a value from the repo-root .env (the file docker-compose reads),
    falling back to a shell env var then the default."""
    from pathlib import Path
    val = default
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            s = line.strip()
            if s.startswith(f"{key}=") and not s.startswith("#"):
                val = s.split("=", 1)[1].strip() or val
    return os.getenv(key, val)


async def _center_mint(sub: str) -> "str | None":
    """Mint a demo magic link via the Admin Center (container-side, same
    SECRET_KEY as the app). Returns the token, or None to skip — Center
    unreachable / admin-tools off / magic-link off / login or mint refused.
    """
    from urllib.parse import parse_qs, unquote, urlparse

    user = _env_file_value("ADMIN_CENTER_USER", "admin")
    pw = _env_file_value("ADMIN_CENTER_PASS", "changeme")
    secret = _env_file_value("ADMIN_CENTER_TOTP_SECRET", "")
    try:
        async with httpx.AsyncClient(
            base_url=ADMIN_CENTER_BASE_URL, timeout=8.0, follow_redirects=False
        ) as c:
            r = await c.post("/login", data={"username": user, "password": pw, "next": "/tools"})
            if "/login/mfa" in r.headers.get("location", "") and secret:
                import time as _t

                from app.admin_center import mfa as _mfa
                await c.post("/login/mfa", data={"code": _mfa._hotp(secret, int(_t.time() // 30))})
            m = await c.post("/tools/demo/mint-magic-link", data={"sub": sub})
    except httpx.HTTPError:
        return None
    if m.status_code != 303:
        return None
    minted = parse_qs(urlparse(m.headers.get("location", "")).query).get("minted", [""])[0]
    url = unquote(minted)
    if "token=" not in url:
        return None
    return url.split("token=", 1)[1]


async def _magic_link_gate_open() -> bool:
    """Probe whether the running container has both magic-link
    gates open. Used by the happy-path tests below to auto-skip
    when the override compose isn't up.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0, follow_redirects=False) as client:
        resp = await client.get("/demo-login?token=garbage-token")
    # Gate ON  → 401 (we get past the gate, fail signature verify)
    # Gate OFF → 404 (route refuses to register effectively)
    return resp.status_code == 401


async def test_happy_path_when_gate_open():
    """End-to-end mint (via the Admin Center) → verify → replay against the
    app's public /demo-login. Only runs when the app's magic-link gate is
    open AND the Admin Center can mint (admin-tools on + reachable);
    otherwise skips. This exercises the real cross-service contract: the
    Center mints with the shared SECRET_KEY, the app redeems.

    Verifies:
      1. The Center mints a one-time URL whose token reaches /demo-login.
      2. First redemption → 303 to / with the demo user's session cookie.
      3. A second attempt with the same token → 401 (replay rejected).
    """
    if not await _magic_link_gate_open():
        pytest.skip(
            "demo magic-link gate closed on the app container — set "
            "DEMO_MODE=true + SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED=true to run."
        )
    # 1. Mint container-side via the Admin Center (same SECRET_KEY as the app).
    token = await _center_mint("demo-alice@example.com")
    if not token:
        pytest.skip(
            "could not mint via the Admin Center (unreachable / admin-tools "
            "off / magic-link off) — skipping the cross-service happy path."
        )

    # 2. First verify (success → 303 redirect + auth cookie).
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0, follow_redirects=False) as anon:
        resp = await anon.get(f"/demo-login?token={token}")
    assert resp.status_code == 303, (
        f"first verify should 303-redirect on success; got {resp.status_code} {resp.text[:200]}"
    )
    assert resp.headers.get("location") == "/"
    cookies = resp.headers.get("set-cookie") or ""
    assert "session=" in cookies, "first verify should set the session cookie"

    # 3. Second verify with the SAME token → 401 (replay rejected).
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0, follow_redirects=False) as anon:
        resp2 = await anon.get(f"/demo-login?token={token}")
    assert resp2.status_code == 401, (
        f"second verify should 401 on replay; got {resp2.status_code} {resp2.text[:200]}"
    )
