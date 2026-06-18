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
)
from ..config import get_settings
from ..database import get_db
from ..models import User
from ..templates import templates

router = APIRouter()
log = logging.getLogger(__name__)


def _safe_next_path(raw: Optional[str]) -> str:
    """v2.3.28: scrub a ``?next=`` query param so we only bounce the
    user back to a same-origin path. Rejects absolute URLs (no scheme,
    no double-slash prefix) and protocol-relative URLs to prevent an
    open redirect. Falls back to ``/`` on anything suspicious or empty.
    """
    if not raw:
        return "/"
    candidate = raw.strip()
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
):
    settings = get_settings()
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "settings": settings,
            "error": error,
            "google_enabled": settings.google_sso.enabled and bool(settings.google_sso.client_id),
            # v2.3.28: round-trip the safe-validated ``next`` so the form
            # carries it through to the POST handler.
            "next_path": _safe_next_path(next),
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
    login_user(request, user)
    audit("auth.login_ok", request=request, user_id=user.id)
    return RedirectResponse(_safe_next_path(next), status_code=303)


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
    login_user(request, user)
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
    login_user(request, user)
    return RedirectResponse("/", status_code=303)
