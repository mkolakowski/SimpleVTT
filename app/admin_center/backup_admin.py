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

# v2.998.0 — offsite (cloud) upload settings. ``copy`` accumulates (remote only
# ever gains files — safest default); ``sync`` mirrors local retention. The
# remote path is "<bucket-or-folder>/<prefix>" under the rclone remote.
_OFFSITE_MODES = ("copy", "sync")
_DEFAULT_OFFSITE_MODE = "copy"
_DEFAULT_OFFSITE_PATH = "simplevtt-backups"
_OFFSITE_PROVIDERS = ("s3", "drive", "dropbox", "onedrive")
_OFFSITE_PATH_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._/-]{0,199}\Z")


def backups_dir() -> Path:
    return Path(os.environ.get("BACKUP_DIR", "/backups"))


def _settings_path() -> Path:
    return backups_dir() / "backup-settings.json"


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def backups_force_enabled() -> bool:
    """Testing override: re-enable backups on a demo instance. Default off."""
    return _env_truthy("DEMO_BACKUPS_ENABLED")


def demo_mode_active() -> bool:
    """True when automated backups are *disabled because* this is a demo
    instance — i.e. ``DEMO_MODE`` is on and the ``DEMO_BACKUPS_ENABLED`` testing
    override is off. The page renders the backups surface read-only and the
    settings / run / restore actions are refused when this is true."""
    return _env_truthy("DEMO_MODE") and not backups_force_enabled()


def demo_override_active() -> bool:
    """True when this is a demo instance with backups force-enabled for testing
    (``DEMO_MODE`` *and* ``DEMO_BACKUPS_ENABLED``). The backups surface is fully
    live (schedule / run-now / download / restore), but the page surfaces a
    note so the operator knows it's a demo — which reseeds hourly, so a restored
    or edited state won't survive the next reset."""
    return _env_truthy("DEMO_MODE") and backups_force_enabled()


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


def _norm_offsite_mode(value) -> str:
    v = str(value or "").strip().lower()
    return v if v in _OFFSITE_MODES else _DEFAULT_OFFSITE_MODE


def _norm_offsite_path(value) -> str:
    """Sanitize the remote path ("bucket/prefix"): trimmed, slash-normalized,
    restricted charset, no traversal. Falls back to the default."""
    v = str(value or "").strip().strip("/")
    if not v or ".." in v or not _OFFSITE_PATH_RE.match(v):
        return _DEFAULT_OFFSITE_PATH
    return v


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
                    # v2.998.0 — offsite upload settings ride the same file.
                    "offsite_enabled": bool(data.get("offsite_enabled")),
                    "offsite_mode": _norm_offsite_mode(data.get("offsite_mode")),
                    "offsite_path": _norm_offsite_path(data.get("offsite_path")),
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
        "offsite_enabled": False,
        "offsite_mode": _DEFAULT_OFFSITE_MODE,
        "offsite_path": _DEFAULT_OFFSITE_PATH,
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
    offsite_enabled=None,
    offsite_mode=None,
    offsite_path=None,
) -> dict:
    """Validate + atomically persist the settings file. Raises ``ValueError``
    on a malformed cron expression (the route maps that to a 400-style
    redirect). Returns the written dict.

    v2.998.0 — the ``offsite_*`` kwargs default to ``None`` = *preserve the
    current on-disk value* (so the schedule form's save can't silently clobber
    the offsite settings, and vice versa)."""
    cron = (cron or "").strip()
    if not validate_cron(cron):
        raise ValueError("Cron expression must be five fields (min hour dom mon dow).")
    current = read_settings()
    payload = {
        "format": SETTINGS_FORMAT,
        "version": SETTINGS_VERSION,
        "cron": cron,
        "keep_daily": _clamp_keep(keep_daily, _DEFAULT_KEEP_DAILY),
        "keep_weekly": _clamp_keep(keep_weekly, _DEFAULT_KEEP_WEEKLY),
        "offsite_enabled": bool(current["offsite_enabled"] if offsite_enabled is None
                                else offsite_enabled),
        "offsite_mode": _norm_offsite_mode(current["offsite_mode"] if offsite_mode is None
                                           else offsite_mode),
        "offsite_path": _norm_offsite_path(current["offsite_path"] if offsite_path is None
                                           else offsite_path),
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


def run_status() -> dict:
    """The sidecar's coarse progress for the current/last backup run — drives
    the "Back up now" progress toast. Shape: ``{state, stage, pct, started, ts}``
    (``state`` ∈ running / done); ``{"state": "idle"}`` when no status file."""
    p = backups_dir() / ".run-status"
    if not p.is_file():
        return {"state": "idle"}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"state": "idle"}
    except (OSError, json.JSONDecodeError):
        return {"state": "idle"}


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


# A backup run's stem — the name shared by its ``.sql.gz`` /
# ``.homebrew.tar.gz`` / ``.uploads.tar.gz`` trio. v2.631.1 names are
# ``YYYY-MM-DD_HHmmss[_tag]`` (e.g. ``2026-06-24_210306_manual``); older names
# were ``simplevtt-<ts>``. Both use only ``[A-Za-z0-9_-]`` (no ``/`` or ``.``),
# so the stem stays traversal-safe as a download / restore identifier.
_TS_RE = re.compile(r"\A[A-Za-z0-9_-]+\Z")


def _ts_of(name: str) -> Optional[str]:
    """Extract the run stem (the filename minus its artifact suffix) from an
    artifact filename, or None. Handles both the v2.631.0 stem and the older
    ``simplevtt-<ts>`` names (the leading ``simplevtt-`` just stays part of the
    stem for old files)."""
    for suf in _ARTIFACT_SUFFIXES:
        if name.endswith(suf):
            return name[: -len(suf)] or None
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


def delete_backup(bucket: str, ts: str) -> int:
    """Delete a backup run's artifacts (the three tarballs/dump + its ``.tag``)
    for ``(bucket, ts)``. Returns the number of files removed. Traversal-safe:
    the artifact paths come through ``backup_files_for`` (allowlisted bucket +
    ``_TS_RE`` stem + must-exist), and the ``.tag`` sibling is name-validated."""
    removed = 0
    for p in backup_files_for(bucket, ts):
        try:
            p.unlink()
            removed += 1
        except OSError:
            pass
    if bucket in ("daily", "weekly") and _TS_RE.match(ts or ""):
        tag = backups_dir() / bucket / f"{ts}.tag"
        try:
            if tag.is_file():
                tag.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def _tag_for(bucket: str, ts: str) -> Optional[str]:
    """The optional note written alongside a backup run (e.g. a pre-restore
    safety backup), or None. Stored as a sibling ``simplevtt-<ts>.tag`` file."""
    if bucket not in ("daily", "weekly") or not _TS_RE.match(ts or ""):
        return None
    p = backups_dir() / bucket / f"{ts}.tag"
    if p.is_file():
        try:
            return p.read_text(encoding="utf-8").strip()[:300] or None
        except OSError:
            return None
    return None


# ── Offsite (cloud) uploads (v2.998.0) ───────────────────────────────────────
# The Admin Center writes an rclone config (one remote named ``offsite``) +
# a secrets-free metadata sidecar on the shared volume; the backup sidecar
# (which has rclone baked in via Dockerfile.backup) pushes after each run and
# honors the .offsite-test / .offsite-push trigger files. Secrets live ONLY in
# rclone.conf (0600) — never in the metadata, summaries, or any JSON response.

def _offsite_conf_path() -> Path:
    return backups_dir() / "rclone.conf"


def _offsite_meta_path() -> Path:
    return backups_dir() / ".offsite-config.json"


def _clean_line(value, *, max_len: int = 500) -> str:
    """Single-line, trimmed config value. Newlines are stripped (rclone.conf is
    line-oriented — embedded newlines would allow section injection)."""
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()[:max_len]


def _norm_oauth_token(raw: str) -> str:
    """Validate + normalize a pasted ``rclone authorize`` token to compact
    single-line JSON (the shape rclone.conf expects). Raises ValueError."""
    try:
        tok = json.loads(raw or "")
    except (TypeError, json.JSONDecodeError):
        raise ValueError(
            "Token must be the JSON blob printed by `rclone authorize` "
            '(looks like {"access_token":"...","expiry":"..."}).')
    if not isinstance(tok, dict) or not tok:
        raise ValueError("Token must be a non-empty JSON object.")
    return json.dumps(tok, separators=(",", ":"))


def write_offsite_config(provider: str, fields: dict, *, updated_by: str, now_iso: str) -> None:
    """Generate ``rclone.conf`` (remote name ``offsite``) for the given
    provider + a secrets-free metadata sidecar. Raises ``ValueError`` on an
    unknown provider or missing required fields. Atomic write, chmod 0600."""
    provider = (provider or "").strip().lower()
    if provider not in _OFFSITE_PROVIDERS:
        raise ValueError(f"Unknown provider {provider!r} (expected one of {_OFFSITE_PROVIDERS}).")
    f = {k: _clean_line(v, max_len=4000 if k == "token" else 500)
         for k, v in (fields or {}).items()}
    lines = ["# managed by the SimpleVTT Admin Center — do not edit by hand",
             "[offsite]"]
    if provider == "s3":
        if not f.get("access_key_id") or not f.get("secret_access_key"):
            raise ValueError("S3 needs an access key id and a secret access key.")
        lines += ["type = s3",
                  # An explicit endpoint means an S3-compatible service
                  # (MinIO / R2 / B2 / Wasabi …) → provider Other.
                  f"provider = {'Other' if f.get('endpoint') else 'AWS'}",
                  f"access_key_id = {f['access_key_id']}",
                  f"secret_access_key = {f['secret_access_key']}"]
        if f.get("region"):
            lines.append(f"region = {f['region']}")
        if f.get("endpoint"):
            lines.append(f"endpoint = {f['endpoint']}")
    else:
        token = _norm_oauth_token(fields.get("token") if fields else "")
        lines += [f"type = {provider}", f"token = {token}"]
        if f.get("client_id"):
            lines.append(f"client_id = {f['client_id']}")
        if f.get("client_secret"):
            lines.append(f"client_secret = {f['client_secret']}")
        if provider == "onedrive":
            if f.get("drive_id"):
                lines.append(f"drive_id = {f['drive_id']}")
            drive_type = f.get("drive_type") or "personal"
            lines.append(f"drive_type = {drive_type}")
    conf = "\n".join(lines) + "\n"
    path = _offsite_conf_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".conf.tmp")
    tmp.write_text(conf, encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)  # atomic
    meta = {"provider": provider, "updated_at": now_iso, "updated_by": updated_by or "admin"}
    mtmp = _offsite_meta_path().with_suffix(".json.tmp")
    mtmp.write_text(json.dumps(meta), encoding="utf-8")
    os.chmod(mtmp, 0o600)
    mtmp.replace(_offsite_meta_path())


def offsite_config_summary() -> dict:
    """Secrets-free view of the offsite config for the page: whether a remote
    is configured + which provider + when. NEVER includes credential values."""
    configured = _offsite_conf_path().is_file()
    out = {"configured": configured, "provider": None,
           "updated_at": None, "updated_by": None}
    if configured and _offsite_meta_path().is_file():
        try:
            meta = json.loads(_offsite_meta_path().read_text(encoding="utf-8"))
            if isinstance(meta, dict):
                out["provider"] = meta.get("provider")
                out["updated_at"] = meta.get("updated_at")
                out["updated_by"] = meta.get("updated_by")
        except (OSError, json.JSONDecodeError):
            pass
    return out


def delete_offsite_config() -> bool:
    """Remove the rclone config + metadata (+ stale result files, best-effort —
    they may be root-owned in the sticky volume root). True if a config was
    actually removed."""
    removed = False
    for p in (_offsite_conf_path(), _offsite_meta_path(),
              backups_dir() / ".offsite-test-result", backups_dir() / ".offsite-status"):
        try:
            if p.is_file():
                if p == _offsite_conf_path():
                    removed = True
                p.unlink()
        except OSError:
            pass
    return removed


def _read_json_file(p: Path) -> Optional[dict]:
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def offsite_status() -> Optional[dict]:
    """The sidecar's last upload outcome: {ok, at, mode, path, error?, ts?}."""
    return _read_json_file(backups_dir() / ".offsite-status")


def offsite_test_result() -> Optional[dict]:
    """The sidecar's last connectivity-probe outcome: {ok, at, path, error?}."""
    return _read_json_file(backups_dir() / ".offsite-test-result")


def trigger_offsite_list() -> None:
    """Drop the remote-listing trigger; the sidecar writes .offsite-listing."""
    d = backups_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / ".offsite-list").write_text("", encoding="utf-8")


def offsite_listing() -> Optional[dict]:
    """The sidecar's last remote listing: {ok, at, path, daily:[…], weekly:[…]}
    (rclone lsjson entries: Name/Size/ModTime), or None."""
    return _read_json_file(backups_dir() / ".offsite-listing")


def remote_backups() -> Optional[dict]:
    """The remote listing grouped into backup runs (same shape as
    ``list_backups``: per-bucket [{ts, files, size, mtime}]) so the page can
    render one row per run with a pull button. None when no listing yet;
    ``{"ok": False, …}`` passthrough when the last listing failed."""
    listing = offsite_listing()
    if listing is None:
        return None
    if not listing.get("ok"):
        return {"ok": False, "at": listing.get("at"), "error": listing.get("error")}
    out: dict = {"ok": True, "at": listing.get("at"), "daily": [], "weekly": []}
    for bucket in ("daily", "weekly"):
        groups: dict[str, dict] = {}
        for entry in listing.get(bucket) or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("Name") or "")
            ts = _ts_of(name)
            if ts is None:
                continue
            g = groups.setdefault(ts, {"ts": ts, "files": [], "size": 0, "mtime": ""})
            g["files"].append(name)
            g["size"] += int(entry.get("Size") or 0)
            g["mtime"] = max(g["mtime"], str(entry.get("ModTime") or ""))
        out[bucket] = sorted(groups.values(), key=lambda g: g["mtime"], reverse=True)
    return out


def request_offsite_pull(bucket: str, ts: str) -> bool:
    """Queue a pull of one remote backup run into the LOCAL bucket dir (where
    the normal restore flow takes over). Traversal-proof: bucket allowlisted +
    ``_TS_RE`` stem, and the sidecar re-validates both. False on bad input."""
    if bucket not in ("daily", "weekly") or not ts or not _TS_RE.match(ts):
        return False
    d = backups_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / ".offsite-pull.tmp"
    tmp.write_text(json.dumps({"bucket": bucket, "ts": ts}), encoding="utf-8")
    tmp.replace(d / ".offsite-pull")
    return True


def offsite_pull_result() -> Optional[dict]:
    """The sidecar's last pull outcome: {ok, at, bucket?, ts, files?|error}."""
    return _read_json_file(backups_dir() / ".offsite-pull-result")


def trigger_offsite_test() -> None:
    """Drop the connectivity-test trigger the sidecar watch-loop picks up."""
    d = backups_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / ".offsite-test").write_text("", encoding="utf-8")


def trigger_offsite_push() -> None:
    """Drop the upload-now trigger (pushes existing artefacts, no new backup)."""
    d = backups_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / ".offsite-push").write_text("", encoding="utf-8")


def backup_files_for(bucket: str, ts: str) -> list:
    """The on-disk paths for a backup run's artifacts (SQL dump + homebrew
    tarball, whichever exist), validated through ``artifact_path``. Empty list
    on a bad bucket / timestamp / missing run — traversal-proof (``ts`` is
    alnum-only and each filename is re-validated)."""
    if not ts or not _TS_RE.match(ts):
        return []
    paths = []
    for suf in _ARTIFACT_SUFFIXES:
        p = artifact_path(bucket, f"{ts}{suf}")
        if p is not None:
            paths.append(p)
    return paths
