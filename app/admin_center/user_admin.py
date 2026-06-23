"""User-administration service functions for the Admin Center.

Phase 2 of ``docs/plans/admin-center-consolidation.md`` moves the
site-admin **user CRUD** out of the main app's in-app ``/admin`` portal
and into the standalone Center. The in-app routes (``admin_routes.py``)
are FastAPI handlers wired to ``Depends(require_admin)`` + ``Depends(get_db)``
— not reusable as plain functions — so the actual DB logic is re-homed
here as small, dependency-light service functions the Center's gated
routes call. They are intentionally free of FastAPI / auth concerns: the
caller (``main.py``) owns the ``ADMIN_CENTER_ADMIN_TOOLS`` gate, the MFA
gate on destructive ops, and the operator-audit emission.

Each function takes an open ``Session`` and commits inline (mirroring the
in-app handlers). Validation failures raise ``UserAdminError`` with a
human-readable message the route turns into a redirect banner.
"""
from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session

from ..auth import hash_password
from ..config import get_settings
from ..models import User


class UserAdminError(Exception):
    """A validation/precondition failure the route surfaces to the operator."""


def list_users(db: Session) -> List[User]:
    """All users, id-ordered (the same ordering the in-app portal uses)."""
    return db.query(User).order_by(User.id).all()


def get_user(db: Session, user_id: int) -> User:
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise UserAdminError(f"No user with id {user_id}")
    return u


def create_user(db: Session, *, email: str, display_name: str, password: str) -> User:
    """Create a user. Mirrors ``admin_routes.admin_create_user`` —
    lowercases/strips the email, rejects duplicates, derives is_admin from
    the operator's configured admin-email list. Non-destructive (additive)
    so it doesn't sit behind the MFA gate."""
    email_n = (email or "").lower().strip()
    if not email_n:
        raise UserAdminError("Email is required")
    if len(password or "") < 8:
        raise UserAdminError("Password too short (min 8 chars)")
    if db.query(User).filter(User.email == email_n).first():
        raise UserAdminError("Email already in use")
    settings = get_settings()
    u = User(
        email=email_n,
        display_name=(display_name or "").strip() or email_n.split("@")[0],
        password_hash=hash_password(password),
        is_admin=settings.is_admin_email(email_n),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def set_user_disabled(db: Session, user_id: int) -> tuple[User, bool]:
    """Toggle a user's disabled flag. Returns (user, new_disabled_state)."""
    u = get_user(db, user_id)
    u.is_disabled = not u.is_disabled
    db.commit()
    return u, u.is_disabled


def reset_password(db: Session, user_id: int, *, new_password: str) -> User:
    """Set a new password hash. The plaintext is never logged or returned."""
    u = get_user(db, user_id)
    if len(new_password or "") < 8:
        raise UserAdminError("Password too short (min 8 chars)")
    u.password_hash = hash_password(new_password)
    db.commit()
    return u


def set_role(db: Session, user_id: int, *, role: str, value: bool) -> User:
    """Grant/revoke an app-wide role on a user (v2.587.0). ``role`` is
    ``"gm"`` (``User.is_gm``) or ``"admin"`` (``User.is_admin``). Returns the
    updated user. See docs/plans/app-wide-roles-and-storage.md."""
    u = get_user(db, user_id)
    if role == "gm":
        u.is_gm = bool(value)
    elif role == "admin":
        u.is_admin = bool(value)
    else:
        raise UserAdminError(f"Unknown role: {role!r} (expected 'gm' or 'admin')")
    db.commit()
    return u


def delete_user(db: Session, user_id: int) -> str:
    """Delete a user. Returns the email captured BEFORE the delete so the
    caller can audit a human-readable target after the row is gone."""
    u = get_user(db, user_id)
    target_email = u.email
    db.delete(u)
    db.commit()
    return target_email
