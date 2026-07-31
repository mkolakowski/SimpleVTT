"""Login, logout, register, and Google OAuth routes."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .. import auth as auth_mod
from ..audit_log import audit
from ..auth import (
    authenticate_local,
    get_or_create_google_user,
    hash_password,
    login_user,
    logout_user,
    oauth,
    pop_login_next,
)
from ..config import get_settings
from ..database import get_db
from ..models import Campaign, CampaignMembership, User
from ..templates import templates

router = APIRouter()
log = logging.getLogger(__name__)


def _demo_login_roster(db: Session) -> list[dict]:
    """v2.884.0 — the full demo cast for the login screen. For each seeded
    demo account (all share ``demopass``) return its display name, email, GM
    flag, and the campaigns it belongs to (as primary GM via
    ``Campaign.gm_user_id`` or as a player/co-GM via ``CampaignMembership``),
    so the login page can list everyone and reveal who plays where. Ordered
    to match the seed's ``DEMO_EMAILS`` (GMs interleaved with their players).
    """
    from ..demo_seed import DEMO_EMAILS  # local import: demo_seed is heavy

    users = db.query(User).filter(User.email.in_(DEMO_EMAILS)).all()
    by_email = {u.email: u for u in users}
    uids = [u.id for u in users]
    if not uids:
        return []
    camps = db.query(Campaign).all()
    camp_by_id = {c.id: c for c in camps}
    owned_by_uid: dict[int, list] = {}
    for c in camps:
        owned_by_uid.setdefault(c.gm_user_id, []).append(c)
    mem_by_uid: dict[int, list] = {}
    for m in (
        db.query(CampaignMembership)
        .filter(CampaignMembership.user_id.in_(uids))
        .all()
    ):
        mem_by_uid.setdefault(m.user_id, []).append(m)

    roster: list[dict] = []
    for email in DEMO_EMAILS:
        u = by_email.get(email)
        if not u:
            continue
        campaigns: list[dict] = []
        seen: set[int] = set()
        for c in owned_by_uid.get(u.id, []):
            campaigns.append(
                {"name": c.name, "role": "GM", "archived": bool(c.is_archived)}
            )
            seen.add(c.id)
        for m in mem_by_uid.get(u.id, []):
            c = camp_by_id.get(m.campaign_id)
            if not c or c.id in seen:
                continue
            campaigns.append(
                {
                    "name": c.name,
                    "role": "Co-GM" if m.is_gm else "Player",
                    "archived": bool(c.is_archived),
                }
            )
            seen.add(c.id)
        campaigns.sort(key=lambda x: x["name"])
        roster.append(
            {
                "email": u.email,
                "display_name": u.display_name,
                "is_gm": bool(u.is_gm),
                "campaigns": campaigns,
            }
        )
    return roster


def _safe_next_path(raw: Optional[str]) -> str:
    """v2.3.28: scrub a ``?next=`` query param so we only bounce the
    user back to a same-origin path. Rejects absolute URLs (no scheme,
    no double-slash prefix) and protocol-relative URLs to prevent an
    open redirect. Falls back to ``/`` on anything suspicious or empty.
    """
    if not raw:
        return "/"
    candidate = raw.strip()
    # v2.1036.1 — reject backslash-based open redirects: browsers normalize
    # "\" → "/", so "/\evil.com" becomes protocol-relative "//evil.com".
    # Block the decoded + encoded backslash and control/whitespace smuggling.
    if "%5c" in candidate.lower() or any(ch in candidate for ch in ("\t", "\n", "\r", "\x00")):
        return "/"
    candidate = candidate.replace("\\", "/")
    # Reject absolute URLs and protocol-relative URLs.
    if not candidate.startswith("/") or candidate.startswith("//"):
        return "/"
    # Reject anything that smuggles in a scheme via the path.
    if ":" in candidate.split("/", 2)[1]:
        return "/"
    return candidate


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    error: Optional[str] = None,
    next: Optional[str] = None,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    safe_next = _safe_next_path(next)
    # v2.785.0 — also stash in the session so passwordless paths (demo
    # magic-link, Google SSO) can return to the same destination.
    if safe_next and safe_next != "/":
        try:
            request.session["login_next"] = safe_next
        except (AttributeError, AssertionError):
            pass
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "settings": settings,
            "error": error,
            "google_enabled": settings.google_sso.enabled and bool(settings.google_sso.client_id),
            # v2.3.28: round-trip the safe-validated ``next`` so the form
            # carries it through to the POST handler.
            "next_path": safe_next,
            # v2.884.0 — the full demo cast + their campaigns for the login
            # box (only queried under demo mode; empty list otherwise).
            "demo_users": _demo_login_roster(db) if settings.demo_mode else [],
        },
    )


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    user = authenticate_local(db, email, password)
    if not user:
        audit(
            "auth.login_failed",
            level=logging.WARNING,
            request=request,
            username=email.lower().strip(),
        )
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "settings": get_settings(),
                "error": "Invalid email or password",
                "google_enabled": get_settings().google_sso.enabled,
                "next_path": _safe_next_path(next),
            },
            status_code=401,
        )
    # Refresh admin status from config every login
    settings = get_settings()
    if settings.is_admin_email(user.email) and not user.is_admin:
        user.is_admin = True
        db.commit()
    login_user(request, user, db)
    audit("auth.login_ok", request=request, user_id=user.id)
    # Prefer the form ``next``; fall back to the session-stashed one. Clear it.
    dest = _safe_next_path(next)
    try:
        stashed = request.session.pop("login_next", None)
    except (AttributeError, AssertionError):
        stashed = None
    if dest == "/" and stashed:
        dest = _safe_next_path(stashed)
    return RedirectResponse(dest, status_code=303)


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, error: Optional[str] = None):
    settings = get_settings()
    if not settings.app.allow_local_registration:
        raise HTTPException(404, "Registration disabled")
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "settings": settings, "error": error},
    )


@router.post("/register")
def register_submit(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.app.allow_local_registration:
        raise HTTPException(404, "Registration disabled")
    email_norm = email.lower().strip()
    if len(password) < 8:
        audit(
            "auth.signup_failed",
            level=logging.WARNING,
            request=request,
            reason="password_too_short",
            username=email_norm,
        )
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "settings": settings, "error": "Password must be at least 8 characters."},
            status_code=400,
        )
    existing = db.query(User).filter(User.email == email_norm).first()
    if existing:
        audit(
            "auth.signup_failed",
            level=logging.WARNING,
            request=request,
            reason="email_taken",
            username=email_norm,
        )
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "settings": settings, "error": "Email already registered."},
            status_code=400,
        )
    user = User(
        email=email_norm,
        display_name=display_name.strip() or email_norm.split("@")[0],
        password_hash=hash_password(password),
        is_admin=settings.is_admin_email(email_norm),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    login_user(request, user, db)
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/login", status_code=303)


# ---------- Google SSO ----------

@router.get("/auth/google/login")
async def google_login(request: Request):
    settings = get_settings()
    if not (settings.google_sso.enabled and settings.google_sso.client_id):
        raise HTTPException(404, "Google SSO disabled")
    redirect_uri = settings.app.base_url.rstrip("/") + "/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    if not (settings.google_sso.enabled and settings.google_sso.client_id):
        raise HTTPException(404, "Google SSO disabled")
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        log.warning("Google OAuth error: %s", e)
        return RedirectResponse("/login?error=google_failed", status_code=303)
    userinfo = token.get("userinfo") or {}
    if not userinfo:
        return RedirectResponse("/login?error=google_no_userinfo", status_code=303)
    email = userinfo.get("email")
    sub = userinfo.get("sub")
    name = userinfo.get("name") or ""
    if not email or not sub:
        return RedirectResponse("/login?error=google_missing_fields", status_code=303)
    user = get_or_create_google_user(db, settings, google_sub=sub, email=email, name=name)
    if user.is_disabled:
        return RedirectResponse("/login?error=disabled", status_code=303)
    login_user(request, user, db)
    # v2.785.0 — return to where the session expired (stashed on the 401
    # bounce / GET /login), else home.
    return RedirectResponse(pop_login_next(request), status_code=303)
