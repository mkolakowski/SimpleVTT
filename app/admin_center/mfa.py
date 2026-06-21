"""TOTP multi-factor auth + env recovery code for the admin center.

Per ``docs/plans/admin-center-mfa.md``. Opt-in, env-gated, and
**default-off** — with MFA disabled this module is inert and the login
stays password-only.

Dependency-free: TOTP (RFC 6238) is implemented with stdlib
``hmac``/``hashlib``/``struct``/``base64`` so there's no new package to
add. Pure + clock-injectable so the verify + recovery logic are
unit-testable without env or wall-time.

Three env vars (all default off/blank):

  * ``ADMIN_CENTER_MFA_ENABLED``  — master switch.
  * ``ADMIN_CENTER_TOTP_SECRET``  — base32 shared secret.
  * ``ADMIN_CENTER_RECOVERY_CODE`` — single recovery code. **Blank ⇒
    nothing is ever accepted** (the headline safety property).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
from urllib.parse import quote, urlencode

_TRUTHY = ("1", "true", "yes", "on")


# ---- config (read at call time so a restart picks up env changes) ----

def mfa_enabled() -> bool:
    return os.environ.get("ADMIN_CENTER_MFA_ENABLED", "").strip().lower() in _TRUTHY


def _totp_secret() -> str:
    return os.environ.get("ADMIN_CENTER_TOTP_SECRET", "").strip()


def totp_configured() -> bool:
    """True iff a usable (non-blank, base32-decodable) secret is set."""
    secret = _totp_secret()
    if not secret:
        return False
    try:
        _b32decode(secret)
        return True
    except Exception:  # noqa: BLE001 — malformed secret = not configured
        return False


def mfa_misconfigured() -> bool:
    """MFA is on but no usable TOTP secret — the login must fail closed
    (never silently downgrade to password-only)."""
    return mfa_enabled() and not totp_configured()


def _recovery_code() -> str:
    return os.environ.get("ADMIN_CENTER_RECOVERY_CODE", "").strip()


# ---- TOTP (RFC 6238) -------------------------------------------------

def _b32decode(secret: str) -> bytes:
    # Authenticators show the secret without padding + case-insensitive.
    pad = "=" * ((8 - len(secret) % 8) % 8)
    return base64.b32decode(secret.upper() + pad, casefold=True)


def _hotp(secret: str, counter: int, *, digits: int = 6) -> str:
    key = _b32decode(secret)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10 ** digits)).zfill(digits)


def verify_totp(
    code: str,
    *,
    now: float,
    secret: "str | None" = None,
    step: int = 30,
    digits: int = 6,
    valid_window: int = 1,
) -> bool:
    """Verify a TOTP ``code`` for the given ``now`` (unix seconds).

    Accepts the current step ±``valid_window`` to tolerate clock skew.
    Constant-time compare per candidate. Returns False on a blank code,
    a missing/blank secret, or a malformed secret.
    """
    code = (code or "").strip()
    secret = _totp_secret() if secret is None else (secret or "").strip()
    if not code or not secret or not code.isdigit():
        return False
    try:
        counter = int(now // step)
        for w in range(-valid_window, valid_window + 1):
            candidate = _hotp(secret, counter + w, digits=digits)
            if hmac.compare_digest(candidate, code):
                return True
    except Exception:  # noqa: BLE001 — bad secret etc. → reject
        return False
    return False


# ---- recovery code (the §4 safety property) --------------------------

# One-shot consume flag. In-process (best-effort, matches the rest of
# the admin center); a restart re-arms it — pair with rotating the env
# value after a recovery login.
_recovery_state = {"used": False}


def recovery_code_accepts(submitted: str, *, configured: "str | None" = None) -> bool:
    """True iff ``submitted`` matches the configured recovery code.

    **A blank/whitespace configured code accepts nothing** — even a
    blank submission is rejected before any compare, closing the
    empty==empty bypass. Constant-time compare. Returns False once the
    code has been consumed this process (one-shot)."""
    cfg = (_recovery_code() if configured is None else configured or "").strip()
    if not cfg:
        return False
    if _recovery_state["used"]:
        return False
    return secrets.compare_digest((submitted or "").strip(), cfg)


def mark_recovery_used() -> None:
    _recovery_state["used"] = True


def recovery_used() -> bool:
    return _recovery_state["used"]


def reset_recovery_state() -> None:
    """Re-arm the one-shot (used by tests; in production a restart does
    this)."""
    _recovery_state["used"] = False


# ---- provisioning ----------------------------------------------------

def provisioning_uri(*, account: str = "admin", issuer: str = "SimpleVTT Admin") -> str:
    """``otpauth://`` URI for adding the secret to an authenticator app
    (pasteable / QR-encodable). Empty string when no secret is set."""
    secret = _totp_secret()
    if not secret:
        return ""
    label = quote(f"{issuer}:{account}")
    params = urlencode({
        "secret": secret,
        "issuer": issuer,
        "algorithm": "SHA1",
        "digits": 6,
        "period": 30,
    })
    return f"otpauth://totp/{label}?{params}"
