"""Demo magic-link login endpoints — Phase 1 of
``docs/plans/demo-magic-link.md``.

URL-based passwordless login for the public demo instance. An
operator mints a `?token=<...>` link from the Admin Center (port
8015, ``/tools``; the in-app `/admin` mint was retired in v2.581.0);
the link works exactly once, expires in 15 minutes, and only
resolves a seeded demo account (never a real user). Hard-gated by two deploy-time
env vars — `DEMO_MODE=true` AND `SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED=true`
— so a production deploy never accepts these tokens regardless of
payload.

Token shape: an ``itsdangerous.URLSafeTimedSerializer`` blob
holding ``{sub, jti, inst}``. The serializer embeds the signing
timestamp and signs the whole thing with HMAC-SHA256 over the
app's ``SECRET_KEY``. Verification fails closed on bad signature
/ expired timestamp / wrong instance / replayed jti / unknown sub.

Single-use enforcement: every successful verify writes the ``jti``
to the ``demo_magic_links`` table (PK = jti). A duplicate insert
is the replay-detection signal — see ``_consume_jti()``.

Logging follows the canonical audit-log contract in
``app/audit_log.py`` so the demo_magic_link.* events ride the same
fail2ban / CrowdSec filters as the auth.* family.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit_log import audit
from ..auth import login_user, pop_login_next
from ..database import get_db
from ..demo_magic_link import magic_link_enabled, verify_token
from ..demo_seed import DEMO_EMAILS
from ..models import DemoMagicLink, User

router = APIRouter()
log = logging.getLogger(__name__)


def _consume_jti(db: Session, *, jti: str, sub: str) -> bool:
    """Single-use enforcement. Atomic INSERT into the
    ``demo_magic_links`` table; a unique-constraint violation means
    the jti was already consumed (replay attempt) — returns False so
    the caller can log + 401. Returns True on first consumption.
    """
    row = DemoMagicLink(jti=jti, sub=sub)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    return True


# ─── Routes ───────────────────────────────────────────────────────────


# v2.581.0 — the in-app magic-link MINT (`POST /admin/demo/mint-magic-link`)
# was RETIRED and re-homed in the Admin Center (port 8015, /tools → demo
# magic-link), per docs/plans/admin-center-consolidation.md Phase 4. The
# Center's mint reuses ``app.demo_magic_link.mint_token`` (same SECRET_KEY,
# so tokens it mints verify here), double-gated by DEMO_MODE +
# ADMIN_CENTER_ADMIN_TOOLS. The PUBLIC redemption endpoint below
# (``/demo-login``) stays — it's the link target, not an admin surface.


@router.get("/demo-login")
def demo_login(
    request: Request,
    token: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Public verify-and-login. Token comes from the URL query.

    On success: consumes the jti, mints the auth session cookie,
    302 to ``/``. On failure: a deliberately-vague 401 with no
    detail so an enumerating attacker can't distinguish replay from
    bad-sig.
    """
    if not magic_link_enabled():
        # Gate off — the route literally shouldn't be reachable, but
        # belt-and-suspenders: refuse with 404. No audit emit; if the
        # gate is off, we don't want to fill the log with noise from
        # crawlers / robots scanning for the path.
        raise HTTPException(status_code=404, detail="Not found")
    if not token:
        audit(
            "demo_magic_link.verify_rejected",
            level=logging.WARNING,
            request=request,
            reason="missing_token",
        )
        raise HTTPException(status_code=401, detail="invalid_token")
    result = verify_token(token)
    if not result.ok:
        audit(
            "demo_magic_link.verify_rejected",
            level=logging.WARNING,
            request=request,
            reason=result.reason,
        )
        raise HTTPException(status_code=401, detail="invalid_token")
    if result.sub not in DEMO_EMAILS:
        audit(
            "demo_magic_link.verify_rejected",
            level=logging.WARNING,
            request=request,
            reason="unknown_sub",
            jti=result.jti,
        )
        raise HTTPException(status_code=401, detail="invalid_token")
    user = db.query(User).filter(User.email == result.sub).first()
    if user is None or user.is_disabled:
        audit(
            "demo_magic_link.verify_rejected",
            level=logging.WARNING,
            request=request,
            reason="user_missing",
            jti=result.jti,
            sub=result.sub,
        )
        raise HTTPException(status_code=401, detail="invalid_token")
    if not _consume_jti(db, jti=result.jti, sub=result.sub):
        audit(
            "demo_magic_link.verify_rejected",
            level=logging.WARNING,
            request=request,
            reason="replay",
            jti=result.jti,
        )
        raise HTTPException(status_code=401, detail="invalid_token")
    login_user(request, user, db)
    audit(
        "demo_magic_link.verify_ok",
        request=request,
        sub=result.sub,
        jti=result.jti,
        user_id=user.id,
    )
    # v2.785.0 — return to where the session expired (stashed on the 401
    # bounce / GET /login), else home.
    return RedirectResponse(pop_login_next(request), status_code=303)
