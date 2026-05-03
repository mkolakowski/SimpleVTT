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


def login_user(request: Request, user: User) -> None:
    request.session["user_id"] = user.id


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
