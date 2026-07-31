"""Authentication: local password + Google SSO + session helpers."""
from __future__ import annotations

from typing import Optional

from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, HTTPException, Request, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_db
from .models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth client is registered lazily once we have settings.
oauth = OAuth()


def register_oauth(settings: Settings) -> None:
    if settings.google_sso.enabled and settings.google_sso.client_id:
        oauth.register(
            name="google",
            client_id=settings.google_sso.client_id,
            client_secret=settings.google_sso.client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: Optional[str]) -> bool:
    if not hashed:
        return False
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def authenticate_local(db: Session, email: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or user.is_disabled:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_or_create_google_user(
    db: Session,
    settings: Settings,
    *,
    google_sub: str,
    email: str,
    name: str,
) -> User:
    email = email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            email=email,
            display_name=name or email.split("@")[0],
            google_sub=google_sub,
            is_admin=settings.is_admin_email(email),
        )
        db.add(user)
    else:
        if not user.google_sub:
            user.google_sub = google_sub
        # Keep admin status in sync with config
        user.is_admin = user.is_admin or settings.is_admin_email(email)
    db.commit()
    db.refresh(user)
    return user


def login_user(request: Request, user: User, db: Optional[Session] = None) -> None:
    request.session["user_id"] = user.id
    # v2.606.0 — stamp the last successful login. Best-effort: when a db
    # session is passed, record now() on the user and commit. All login
    # paths (password, SSO, demo magic-link) pass it; a None db (legacy
    # caller) just skips the stamp rather than failing the login.
    if db is not None:
        from datetime import datetime as _dt
        try:
            user.last_login_at = _dt.utcnow()
            db.commit()
        except Exception:
            db.rollback()


def logout_user(request: Request) -> None:
    request.session.clear()


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> Optional[User]:
    uid = request.session.get("user_id")
    if not uid:
        return None
    user = db.query(User).filter(User.id == uid).first()
    if user and user.is_disabled:
        return None
    return user


def require_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login required",
            headers={"Location": "/login"},
        )
    return user


def require_admin(
    request: Request, db: Session = Depends(get_db)
) -> User:
    user = require_user(request, db)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def require_gm(
    request: Request, db: Session = Depends(get_db)
) -> User:
    """App-wide GM gate (v2.584.0): the user must hold the GM role or be an
    admin (admins implicitly may create + run campaigns). Players are
    refused with 403. Distinct from per-campaign GM checks. See
    docs/plans/app-wide-roles-and-storage.md."""
    user = require_user(request, db)
    if not (user.is_gm or user.is_admin):
        raise HTTPException(status_code=403, detail="GM access required")
    return user


def uploads_disabled_in_demo(settings: Optional[Settings] = None) -> bool:
    """True when this instance is a locked-down public demo — ``DEMO_MODE``
    and ``DEMO_DISABLE_UPLOADS`` both on (the latter defaults true). Pure
    predicate, so it's unit-testable without a request/DB. See
    ``require_uploads_enabled`` and docs/plans/demo-mode.md."""
    settings = settings or get_settings()
    return bool(settings.demo_mode and settings.demo_disable_uploads)


def require_uploads_enabled() -> None:
    """FastAPI dependency guarding user file-upload endpoints on a public
    demo (v2.1034.0). When ``DEMO_MODE`` and ``DEMO_DISABLE_UPLOADS`` are both
    on, refuse the upload with 403 so demo visitors can't fill the shared
    uploads volume with arbitrary files. No effect on a normal deploy
    (``DEMO_MODE=false``): the demo reseeds hourly and its seed already ships
    the showcase media, so uploads are pure abuse surface there."""
    if uploads_disabled_in_demo():
        raise HTTPException(status_code=403, detail="Uploads are disabled on this demo instance")


def safe_next_path(raw: Optional[str]) -> str:
    """v2.785.0 — scrub a post-login redirect target to a same-origin path
    (no scheme, no protocol-relative ``//``). Falls back to ``/``. Shared by
    the login form, the 401 bounce, and the magic-link / SSO callbacks so
    every login method can return the user to where they were."""
    if not raw or not isinstance(raw, str):
        return "/"
    c = raw.strip()
    # v2.1036.1 — browsers normalize backslashes to forward slashes, so
    # "/\evil.com" resolves to protocol-relative "//evil.com" (open redirect).
    # Normalize "\" → "/" (catches the decoded form) and reject the still-
    # encoded form + control/whitespace chars that smuggle past URL parsers.
    if "%5c" in c.lower() or any(ch in c for ch in ("\t", "\n", "\r", "\x00")):
        return "/"
    c = c.replace("\\", "/")
    if not c.startswith("/") or c.startswith("//"):
        return "/"
    parts = c.split("/", 2)
    if len(parts) > 1 and ":" in parts[1]:
        return "/"
    return c


def pop_login_next(request: Request) -> str:
    """v2.785.0 — consume the session-stashed post-login destination (set on
    the 401 bounce / GET ``/login``), returning a safe same-origin path and
    clearing it. Used by login paths that don't carry ``next`` themselves
    (demo magic-link, Google SSO)."""
    try:
        raw = request.session.pop("login_next", None)
    except (AttributeError, AssertionError):
        raw = None
    return safe_next_path(raw)
