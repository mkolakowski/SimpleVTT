"""HTTP basic-auth gate for the admin center.

Independent of the main app's session login — the admin center is a
separate ASGI app on its own port, protected by a dedicated
``ADMIN_CENTER_USER`` / ``ADMIN_CENTER_PASS`` credential pair. Creds
are read from the environment at request time (never cached) so an
operator can rotate them with a container restart.

Security posture:
  * Constant-time comparison (``secrets.compare_digest``) on both the
    username and password so the gate doesn't leak which half was
    wrong via timing.
  * The default password ``changeme`` makes the dashboard usable out
    of the box, but ``is_default_password()`` lets the UI render a
    loud "change me" banner so it never silently ships to production
    on the default.
"""
from __future__ import annotations

import base64
import binascii
import os
import secrets
from typing import Optional

_DEFAULT_USER = "admin"
_DEFAULT_PASS = "changeme"


def configured_user() -> str:
    return os.environ.get("ADMIN_CENTER_USER", _DEFAULT_USER).strip() or _DEFAULT_USER


def configured_pass() -> str:
    # Note: an explicitly-empty ADMIN_CENTER_PASS falls back to the
    # default rather than disabling auth — an unauthenticated admin
    # center is never the intended state.
    return os.environ.get("ADMIN_CENTER_PASS", _DEFAULT_PASS) or _DEFAULT_PASS


def is_default_password() -> bool:
    """True when the password is still the shipped default — the UI
    uses this to nag the operator to set ADMIN_CENTER_PASS."""
    return configured_pass() == _DEFAULT_PASS


def check_credentials(username: str, password: str) -> bool:
    """Constant-time check of a supplied user/pass against the config."""
    user_ok = secrets.compare_digest(username, configured_user())
    pass_ok = secrets.compare_digest(password, configured_pass())
    return user_ok and pass_ok


def parse_basic_auth_header(header: Optional[str]) -> Optional[tuple[str, str]]:
    """Decode an ``Authorization: Basic <b64>`` header into
    ``(username, password)``, or ``None`` if absent / malformed."""
    if not header:
        return None
    parts = header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "basic":
        return None
    try:
        decoded = base64.b64decode(parts[1].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if ":" not in decoded:
        return None
    user, password = decoded.split(":", 1)
    return user, password


def header_authorizes(header: Optional[str]) -> bool:
    """True iff the given Authorization header carries valid creds."""
    creds = parse_basic_auth_header(header)
    if creds is None:
        return False
    return check_credentials(creds[0], creds[1])
