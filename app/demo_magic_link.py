"""Pure-logic helpers for demo magic-link login (Phase 1 of
``docs/plans/demo-magic-link.md``).

Lives here as a sibling of ``app/audit_log.py`` rather than inside
the route module so the unit tests can import the helpers without
pulling in fastapi. The route module itself
(``app.routes.demo_magic_link_routes``) imports from here.

Two responsibilities:

1. **Token mint/verify** via itsdangerous's URLSafeTimedSerializer
   over the app's SECRET_KEY. HMAC-SHA256, 15-minute TTL, payload
   carries ``{sub, jti, inst}``.

2. **Gate predicate** — both ``DEMO_MODE`` and
   ``SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED`` must be truthy for the
   feature to be on. Either alone is a no-op.
"""
from __future__ import annotations

import hashlib
import os
import secrets

from itsdangerous import (
    BadSignature,
    SignatureExpired,
    URLSafeTimedSerializer,
)

from .config import get_settings


_TOKEN_SALT = "simplevtt-demo-magic-link-v1"
_TOKEN_MAX_AGE_SECONDS = 15 * 60
_TOKEN_INST_TAG = "demo"


def magic_link_enabled() -> bool:
    """Public predicate: are BOTH gates open?

    Both ``DEMO_MODE=true`` and ``SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED=true``
    must be set at deploy time. Either alone is a no-op. Re-evaluated
    at call time (no module-level cache) so tests can flip the env
    vars without restarting the process.
    """
    settings = get_settings()
    if not settings.demo_mode:
        return False
    raw = os.environ.get("SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _serializer() -> URLSafeTimedSerializer:
    """Build the timed serializer from the runtime SECRET_KEY. Built
    fresh on each mint/verify so a hot-rotated key works without a
    process restart."""
    settings = get_settings()
    return URLSafeTimedSerializer(
        secret_key=settings.app.secret_key,
        salt=_TOKEN_SALT,
        signer_kwargs={"digest_method": hashlib.sha256},
    )


def mint_token(sub: str) -> str:
    """Mint a single-use token for the given demo-account email. The
    caller is responsible for verifying the sub is in the demo
    allowlist before minting."""
    jti = secrets.token_urlsafe(16)
    payload = {"sub": sub, "jti": jti, "inst": _TOKEN_INST_TAG}
    return _serializer().dumps(payload)


class VerifyResult:
    __slots__ = ("ok", "sub", "jti", "reason")

    def __init__(self, ok: bool, sub: str = "", jti: str = "", reason: str = ""):
        self.ok = ok
        self.sub = sub
        self.jti = jti
        self.reason = reason


def verify_token(token: str) -> VerifyResult:
    """Decode + check the signature and TTL. Does NOT check the
    consumed-jti table — that's the caller's responsibility so a
    verify-only path can inspect a token without consuming it.

    Reason vocabulary on failure: ``signature`` / ``expired`` /
    ``payload`` — the route layer maps each to the matching
    audit-log event.
    """
    if not token or "." not in token:
        return VerifyResult(False, reason="signature")
    try:
        payload = _serializer().loads(token, max_age=_TOKEN_MAX_AGE_SECONDS)
    except SignatureExpired:
        return VerifyResult(False, reason="expired")
    except BadSignature:
        return VerifyResult(False, reason="signature")
    if not isinstance(payload, dict):
        return VerifyResult(False, reason="payload")
    sub = payload.get("sub") or ""
    jti = payload.get("jti") or ""
    inst = payload.get("inst") or ""
    if inst != _TOKEN_INST_TAG:
        return VerifyResult(False, reason="payload")
    if not sub or not jti:
        return VerifyResult(False, reason="payload")
    return VerifyResult(True, sub=sub, jti=jti)


# Token max-age expressed in seconds — re-exported so callers (the
# admin-mint endpoint, the audit log) can surface "expires in N
# minutes" without re-deriving the constant.
TOKEN_MAX_AGE_SECONDS = _TOKEN_MAX_AGE_SECONDS
