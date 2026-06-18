"""Demo magic-link login endpoints — Phase 1 of
``docs/plans/demo-magic-link.md``.

URL-based passwordless login for the public demo instance. A GM
admin mints a `?token=<...>` link from `/admin`; the link works
exactly once, expires in 15 minutes, and only resolves a seeded
demo account (never a real user). Hard-gated by two deploy-time
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

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit_log import audit
from ..auth import login_user, require_admin
from ..config import get_settings
from ..database import get_db
from ..demo_magic_link import (
    TOKEN_MAX_AGE_SECONDS,
    magic_link_enabled,
    mint_token,
    verify_token,
)
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


@router.post("/admin/demo/mint-magic-link")
def admin_mint_magic_link(
    request: Request,
    sub: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Mint a magic link for a seeded demo account. Admin-only +
    double-env-var-gated. Returns ``{ok, url, expires_in_seconds}``.

    Refuses 404 (not 403) when the feature is off so the admin UI's
    button can detect "feature not deployed" vs. "feature deployed
    but I'm not admin" cleanly.
    """
    if not magic_link_enabled():
        raise HTTPException(status_code=404, detail="Not found")
    sub_norm = sub.strip().lower()
    if sub_norm not in DEMO_EMAILS:
        # Don't audit-emit this — it's an admin-side typo, not a
        # banning-relevant event.
        raise HTTPException(status_code=400, detail="unknown_sub")
    token = mint_token(sub_norm)
    base_url = get_settings().app.base_url.rstrip("/")
    url = f"{base_url}/demo-login?token={token}"
    audit(
        "demo_magic_link.mint_ok",
        request=request,
        sub=sub_norm,
        admin_id=user.id,
    )
    return {
        "ok": True,
        "url": url,
        "expires_in_seconds": TOKEN_MAX_AGE_SECONDS,
    }


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
    login_user(request, user)
    audit(
        "demo_magic_link.verify_ok",
        request=request,
        sub=result.sub,
        jti=result.jti,
        user_id=user.id,
    )
    return RedirectResponse("/", status_code=303)
