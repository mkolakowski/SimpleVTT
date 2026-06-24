"""Operator backup-settings surface for the Admin Center.

Phase 8 of the backup/export-import arc
(``docs/plans/backup-export-overhaul.md``). The automated-backup schedule +
retention used to be env-only (``BACKUP_CRON`` / ``KEEP_DAILY`` /
``KEEP_WEEKLY`` baked into the sidecar at compose time). This module lets an
operator edit them at runtime: the Admin Center writes
``${BACKUP_DIR}/backup-settings.json`` on the shared ``backup_data`` volume,
and the sidecar's watch-loop (``scripts/entrypoint-backup.sh``) regenerates
its crontab when the file changes; ``scripts/backup.sh`` reads the retention
from it on each run.

Dependency-light (stdlib only) so the read/write/validate logic is
unit-testable host-side without the web stack — the same pattern as
``app/export_limit.py``.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

SETTINGS_FORMAT = "simplevtt-backup-settings"
SETTINGS_VERSION = 1

# Defaults mirror the docker-compose env defaults so a fresh instance (no
# settings file yet) reports the same schedule the sidecar boots with.
_DEFAULT_CRON = "0 3 * * *"
_DEFAULT_KEEP_DAILY = 7
_DEFAULT_KEEP_WEEKLY = 4

# Retention is clamped to sane bounds so a fat-fingered value can't wedge the
# sidecar's `find -mtime` pruning (0 would delete everything; huge values
# never prune).
_KEEP_MIN = 1
_KEEP_MAX = 365


def backups_dir() -> Path:
    return Path(os.environ.get("BACKUP_DIR", "/backups"))


def _settings_path() -> Path:
    return backups_dir() / "backup-settings.json"


def demo_mode_active() -> bool:
    """True when automated backups are disabled because the instance is a
    demo (the sidecar skips them; the page renders read-only)."""
    return os.environ.get("DEMO_MODE", "").strip().lower() in ("1", "true", "yes", "on")


def validate_cron(expr: str) -> bool:
    """A crontab line is exactly five whitespace-separated fields. We don't
    fully parse the fields (crond does) — just guard the shape so a blank /
    malformed value can't be written into the crontab."""
    parts = (expr or "").split()
    return len(parts) == 5 and all(parts)


def _clamp_keep(value, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(_KEEP_MIN, min(_KEEP_MAX, n))


def read_settings() -> dict:
    """Current backup settings: the on-disk file if present, else the env
    defaults. Always returns the full shape the page renders."""
    path = _settings_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {
                    "cron": data.get("cron") or _DEFAULT_CRON,
                    "keep_daily": _clamp_keep(data.get("keep_daily"), _DEFAULT_KEEP_DAILY),
                    "keep_weekly": _clamp_keep(data.get("keep_weekly"), _DEFAULT_KEEP_WEEKLY),
                    "updated_at": data.get("updated_at"),
                    "updated_by": data.get("updated_by"),
                    "source": "file",
                }
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "cron": os.environ.get("BACKUP_CRON", _DEFAULT_CRON),
        "keep_daily": _clamp_keep(os.environ.get("KEEP_DAILY"), _DEFAULT_KEEP_DAILY),
        "keep_weekly": _clamp_keep(os.environ.get("KEEP_WEEKLY"), _DEFAULT_KEEP_WEEKLY),
        "updated_at": None,
        "updated_by": None,
        "source": "env",
    }


def write_settings(
    *,
    cron: str,
    keep_daily,
    keep_weekly,
    updated_by: str,
    now_iso: str,
) -> dict:
    """Validate + atomically persist the settings file. Raises ``ValueError``
    on a malformed cron expression (the route maps that to a 400-style
    redirect). Returns the written dict."""
    cron = (cron or "").strip()
    if not validate_cron(cron):
        raise ValueError("Cron expression must be five fields (min hour dom mon dow).")
    payload = {
        "format": SETTINGS_FORMAT,
        "version": SETTINGS_VERSION,
        "cron": cron,
        "keep_daily": _clamp_keep(keep_daily, _DEFAULT_KEEP_DAILY),
        "keep_weekly": _clamp_keep(keep_weekly, _DEFAULT_KEEP_WEEKLY),
        "updated_at": now_iso,
        "updated_by": updated_by or "admin",
    }
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic
    return payload


def trigger_run() -> None:
    """Drop the run-now trigger file the sidecar watch-loop picks up."""
    d = backups_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / ".run-now").write_text("", encoding="utf-8")


def _stat_artifact(p: Path) -> dict:
    st = p.stat()
    return {"name": p.name, "size": st.st_size, "mtime": st.st_mtime}


_ARTIFACT_SUFFIXES = (".sql.gz", ".homebrew.tar.gz", ".uploads.tar.gz")


def artifact_path(bucket: str, name: str) -> Optional[Path]:
    """Resolve a backup artifact to its on-disk path, or ``None`` if it isn't a
    real backup file under ``daily/``/``weekly/``. Traversal-proof: the bucket
    is allowlisted, the name must be a bare filename (no separators / ``..``)
    ending in a known backup suffix, and the resolved path must still sit
    directly inside the bucket dir."""
    if bucket not in ("daily", "weekly"):
        return None
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    if not name.endswith(_ARTIFACT_SUFFIXES):
        return None
    bucket_dir = (backups_dir() / bucket).resolve()
    candidate = (bucket_dir / name).resolve()
    if candidate.parent != bucket_dir or not candidate.is_file():
        return None
    return candidate


def list_artifacts() -> dict:
    """List the individual backup artifacts under daily/ + weekly/, newest
    first. (Used internally; the page lists grouped *backups* — see
    ``list_backups``.)"""
    out: dict[str, list] = {"daily": [], "weekly": []}
    for bucket in ("daily", "weekly"):
        d = backups_dir() / bucket
        if not d.is_dir():
            continue
        items = [
            _stat_artifact(p)
            for p in d.iterdir()
            if p.is_file() and p.name.endswith(_ARTIFACT_SUFFIXES)
        ]
        items.sort(key=lambda a: a["mtime"], reverse=True)
        out[bucket] = items
    return out


# A backup run's timestamp, e.g. ``20260624T030000Z`` — the stamp shared by the
# run's ``simplevtt-<ts>.sql.gz`` + ``simplevtt-<ts>.homebrew.tar.gz`` pair.
_TS_RE = re.compile(r"\A[A-Za-z0-9]+\Z")


def _ts_of(name: str) -> Optional[str]:
    """Extract the run timestamp from an artifact filename, or None."""
    if not name.startswith("simplevtt-"):
        return None
    base = name[len("simplevtt-"):]
    for suf in _ARTIFACT_SUFFIXES:
        if base.endswith(suf):
            return base[: -len(suf)] or None
    return None


def list_backups() -> dict:
    """Group artifacts into *backups* keyed by run timestamp (the SQL dump +
    homebrew tarball produced together), newest first. Each entry carries its
    file names, total size, and newest mtime so the page can offer one
    download-as-zip per backup."""
    out: dict[str, list] = {"daily": [], "weekly": []}
    for bucket, items in list_artifacts().items():
        groups: dict[str, dict] = {}
        for a in items:
            ts = _ts_of(a["name"])
            if ts is None:
                continue
            g = groups.setdefault(ts, {"ts": ts, "files": [], "size": 0, "mtime": 0.0})
            g["files"].append(a["name"])
            g["size"] += a["size"]
            g["mtime"] = max(g["mtime"], a["mtime"])
        ordered = sorted(groups.values(), key=lambda g: g["mtime"], reverse=True)
        for g in ordered:
            g["tag"] = _tag_for(bucket, g["ts"])
        out[bucket] = ordered
    return out


# ── Restore (v2.627.0) — Admin Center → sidecar coordination ──────────────────
# The Admin Center can't restore directly (the app image has no psql + the
# homebrew/uploads volumes are the sidecar's to unpack), so a restore is
# requested by dropping a JSON trigger the sidecar watch-loop processes.

def _restore_request_path() -> Path:
    return backups_dir() / ".restore-request"


def _restore_result_path() -> Path:
    return backups_dir() / ".restore-result"


def restore_pending() -> bool:
    """True while a restore request is queued / in flight (the sidecar removes
    the trigger when it starts processing)."""
    return _restore_request_path().is_file()


def request_restore(bucket: str, ts: str, *, requested_by: str, now_iso: str) -> bool:
    """Queue a restore of the ``(bucket, ts)`` backup by writing the trigger
    file the sidecar picks up. Returns False if the backup doesn't exist or a
    restore is already pending. The sidecar takes a tagged safety backup before
    overwriting anything."""
    if not backup_files_for(bucket, ts):
        return False
    if restore_pending():
        return False
    payload = {
        "bucket": bucket,
        "ts": ts,
        "requested_by": requested_by or "admin",
        "requested_at": now_iso,
    }
    path = _restore_request_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".request.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)
    return True


def last_restore_result() -> Optional[dict]:
    """The most recent restore outcome the sidecar reported, or None."""
    p = _restore_result_path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _tag_for(bucket: str, ts: str) -> Optional[str]:
    """The optional note written alongside a backup run (e.g. a pre-restore
    safety backup), or None. Stored as a sibling ``simplevtt-<ts>.tag`` file."""
    if bucket not in ("daily", "weekly") or not _TS_RE.match(ts or ""):
        return None
    p = backups_dir() / bucket / f"simplevtt-{ts}.tag"
    if p.is_file():
        try:
            return p.read_text(encoding="utf-8").strip()[:300] or None
        except OSError:
            return None
    return None


def backup_files_for(bucket: str, ts: str) -> list:
    """The on-disk paths for a backup run's artifacts (SQL dump + homebrew
    tarball, whichever exist), validated through ``artifact_path``. Empty list
    on a bad bucket / timestamp / missing run — traversal-proof (``ts`` is
    alnum-only and each filename is re-validated)."""
    if not ts or not _TS_RE.match(ts):
        return []
    paths = []
    for suf in _ARTIFACT_SUFFIXES:
        p = artifact_path(bucket, f"simplevtt-{ts}{suf}")
        if p is not None:
            paths.append(p)
    return paths
