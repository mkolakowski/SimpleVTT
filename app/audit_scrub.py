"""GDPR Article 17 audit-log pseudonymization for deleted users.

When an admin deletes a user the ``users`` row + cascaded game data
are removed, but the canonical audit log (``app/audit_log.py`` ->
``AUDIT_LOG_PATH``) retains lines *about* that user for the Section
2.3 retention window — permitted under Article 17(3)(b)/(e). A
privacy-conscious operator may still want to **pseudonymize** the
deleted user's identifiers in the log while keeping the
security-relevant structure intact ("a banned IP was logged" stays;
``actor_id=42``/``target=user@example.com`` become a stable opaque
token).

This module owns that rewrite. Design constraints (from the filed
TODO + the v2.474.0 non-root hardening):

- **Never delete a line.** The audit trail's integrity matters for
  fail2ban / CrowdSec and for the operator's own incident review;
  we rewrite identifiers in place, line-for-line.
- **Preserve ``ip=`` / ``ua=`` / the event tag.** Those are exactly
  the fields the log-based banning engines consume. Only
  user-identifying keys + the email value are touched.
- **Stable opaque token.** The same user always maps to the same
  ``<deleted-…>`` token so cross-line correlation ("this principal
  did X then Y") survives the scrub while the real identity does
  not. The token is a one-way HMAC of the user id — not reversible
  to the id.
- **Runs as ``appuser``.** The rewrite is plain file I/O against the
  ``audit_logs`` volume the app already owns; it coordinates with the
  live ``RotatingFileHandler`` so post-scrub emits land in the
  rewritten file rather than the old (now-unlinked) inode.
- **Idempotent.** Re-running finds nothing left to change (the email
  is gone and the id keys now carry the token), so it reports
  ``lines_rewritten=0``.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable, Optional

# Keys whose value is a user id (vs. an IP, a slug, a count). Only
# these are rewritten when their value equals the target id, so
# ``ip=`` / ``ua=`` / numeric counts are never mangled.
_ID_KEYS = ("actor_id", "user_id", "uid", "target_user_id", "caster_user_id")

# RotatingFileHandler is configured with backupCount=5 in app/main.py.
_ROTATION_BACKUPS = 5


def _scrub_salt() -> str:
    """Salt for the pseudonym HMAC. Read at call time so an env
    override is honored in tests. Defaults to a fixed constant — the
    property we need is one-way *opacity* of the id, not secrecy of
    the salt, so a stable default keeps tokens reproducible across
    restarts even when the operator never sets the var.
    """
    return (os.environ.get("AUDIT_SCRUB_SALT", "").strip()
            or "simplevtt-audit-scrub")


def pseudonym(user_id: int) -> str:
    """Stable opaque token for a user. ``user_id`` -> ``<deleted-xxxx>``.

    Deterministic (same id -> same token) and one-way (HMAC-SHA256
    truncated to 12 hex chars, salted). The angle brackets make the
    token distinct from any real value the log carries, which is what
    keeps the rewrite idempotent.
    """
    digest = hmac.new(
        _scrub_salt().encode("utf-8"),
        f"user:{int(user_id)}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:12]
    return f"<deleted-{digest}>"


def default_audit_paths() -> list[str]:
    """The active audit-log file + its rotated backups. Empty when
    ``AUDIT_LOG_PATH`` is unset (stdout-only deploy — nothing to
    scrub on disk).
    """
    base = os.environ.get(
        "AUDIT_LOG_PATH", "/var/log/simplevtt/audit.log",
    ).strip()
    if not base:
        return []
    return [base] + [f"{base}.{i}" for i in range(1, _ROTATION_BACKUPS + 1)]


def _rewrite_line(line: str, user_id: int, email: str, token: str) -> str:
    """Rewrite a single audit line: id-bearing keys carrying the
    target id, and any occurrence of the email value, become ``token``.
    Everything else (event tag, ip, ua, other keys) is untouched.
    """
    out = line
    uid = re.escape(str(int(user_id)))
    # key=<uid>  ->  key=<token>  for the id-bearing keys only. The
    # trailing \b prevents user_id=5 from matching inside user_id=50.
    out = re.sub(
        r"\b(" + "|".join(_ID_KEYS) + r")=" + uid + r"\b",
        lambda m: f"{m.group(1)}={token}",
        out,
    )
    # The email value, bare or inside quotes. Emails are distinctive
    # enough to replace by literal match; the token's <> chars never
    # appear in an email, so a second pass is a no-op.
    if email:
        out = out.replace(email, token)
    return out


def _audit_file_handlers() -> list[RotatingFileHandler]:
    logger = logging.getLogger("simplevtt.audit")
    return [h for h in logger.handlers
            if isinstance(h, RotatingFileHandler)]


def _detach_handler_streams(handlers: Iterable[RotatingFileHandler]) -> None:
    """Flush + close each handler's open fd and set ``stream=None`` so
    the next ``emit()`` reopens against the rewritten file. Done under
    the handler lock by the caller so no emit interleaves with the
    rewrite.
    """
    for h in handlers:
        try:
            if h.stream is not None:
                h.stream.flush()
                h.stream.close()
            h.stream = None
        except Exception:  # noqa: BLE001 — best-effort; never fail the scrub
            pass


def _rewrite_files(
    paths: Iterable[str], user_id: int, email: str, token: str,
) -> dict:
    files_scanned = 0
    lines_rewritten = 0
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            continue
        files_scanned += 1
        changed = False
        new_lines: list[str] = []
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                new = _rewrite_line(line, user_id, email, token)
                if new != line:
                    lines_rewritten += 1
                    changed = True
                new_lines.append(new)
        if changed:
            # Atomic replace so a crash mid-write can't truncate the
            # audit trail: write a sibling temp then rename over.
            tmp = path.with_name(path.name + ".scrub-tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                fh.writelines(new_lines)
            os.replace(tmp, path)
    return {"files_scanned": files_scanned, "lines_rewritten": lines_rewritten}


def scrub_user_from_audit_log(
    *,
    user_id: int,
    email: str,
    paths: Optional[Iterable[str]] = None,
    reset_handlers: bool = True,
) -> dict:
    """Pseudonymize ``user_id`` + ``email`` across the audit log.

    Args:
        user_id: the (usually already-deleted) user's numeric id.
        email: the user's email — the second identifier carried in
            audit lines (``target=``). Pass the value captured before
            the delete.
        paths: override the file set (tests). Defaults to
            :func:`default_audit_paths`.
        reset_handlers: when True (default) close + reopen the live
            ``RotatingFileHandler`` around the rewrite so subsequent
            emits append to the new file. Pass False in unit tests
            where no live handler is attached.

    Returns a summary dict: ``files_scanned``, ``lines_rewritten``,
    ``pseudonym`` (the stable token applied). Idempotent —
    ``lines_rewritten`` is 0 on a second run.
    """
    token = pseudonym(user_id)
    target_paths = list(paths) if paths is not None else default_audit_paths()
    handlers = _audit_file_handlers() if reset_handlers else []
    # Hold every handler's lock across the rewrite. emit() acquires the
    # same lock, so any concurrent audit() blocks until we're done and
    # then reopens the rewritten file — no line is written to the stale
    # inode, none is clobbered by our os.replace.
    for h in handlers:
        h.acquire()
    try:
        _detach_handler_streams(handlers)
        summary = _rewrite_files(target_paths, user_id, email, token)
    finally:
        for h in reversed(handlers):
            h.release()
    summary["pseudonym"] = token
    return summary
