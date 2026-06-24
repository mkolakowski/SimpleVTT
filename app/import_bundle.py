"""Reader-side primitives for ``simplevtt-export`` archives.

Phase 6 of the backup/export-import arc
(``docs/plans/backup-export-overhaul.md``). The mirror of
``app/export_bundle.py``: open an uploaded archive, validate its envelope,
read the JSON tree, and extract bundled media to **fresh** uuids under
``uploads/`` (so a re-import never collides with or overwrites existing
files, and a crafted archive can't path-traverse — the on-disk name is
always server-generated). ``rewrite_urls`` then threads the
``old_url → new_url`` map through the data so re-created rows point at the
freshly-written media.

FastAPI-free (only the stdlib + ``export_bundle`` constants) so the parsing
+ media handling is unit-testable host-side.
"""
from __future__ import annotations

import io
import json
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any, Optional

from .export_bundle import EXPORT_FORMAT, EXPORT_VERSION

_STATIC_ROOT = Path(__file__).resolve().parent / "static"
_UPLOADS_ROOT = _STATIC_ROOT / "uploads"
_UPLOADS_URL_PREFIX = "/static/uploads/"

_SAFE_EXT = re.compile(r"\.[a-z0-9]{1,8}\Z")
_SAFE_BUCKET = re.compile(r"[^a-z0-9_]")


class BundleError(ValueError):
    """Malformed / unsupported archive — the route maps this to HTTP 400."""


def open_archive(raw: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as e:
        raise BundleError("Not a valid zip archive.") from e


def read_manifest(zf: zipfile.ZipFile, *, expected_level: Optional[str] = None) -> dict:
    """Parse + validate ``manifest.json``: right format, not-from-the-future
    version, and (optionally) the expected ``level``."""
    try:
        manifest = json.loads(zf.read("manifest.json"))
    except KeyError as e:
        raise BundleError("Archive has no manifest.json.") from e
    except json.JSONDecodeError as e:
        raise BundleError("manifest.json is not valid JSON.") from e
    if not isinstance(manifest, dict) or manifest.get("format") != EXPORT_FORMAT:
        raise BundleError(f"Not a {EXPORT_FORMAT} archive.")
    if int(manifest.get("version") or 0) > EXPORT_VERSION:
        raise BundleError(
            f"Archive version {manifest.get('version')} is newer than this "
            f"server supports ({EXPORT_VERSION}). Upgrade first."
        )
    if expected_level and manifest.get("level") != expected_level:
        raise BundleError(
            f"Expected a {expected_level} archive, got {manifest.get('level')!r}."
        )
    return manifest


def read_json(zf: zipfile.ZipFile, archive_path: str) -> Any:
    try:
        return json.loads(zf.read(archive_path))
    except KeyError as e:
        raise BundleError(f"Archive is missing {archive_path}.") from e
    except json.JSONDecodeError as e:
        raise BundleError(f"{archive_path} is not valid JSON.") from e


def _new_url_to_abs(new_url: str, root: Path) -> Path:
    return root / new_url[len(_UPLOADS_URL_PREFIX):]


def extract_media(
    zf: zipfile.ZipFile,
    manifest: dict,
    *,
    uploads_root: Optional[Path] = None,
) -> dict[str, str]:
    """Extract every entry named in the manifest's ``media_manifest`` to a
    fresh uuid filename under ``uploads/<bucket>/`` and return the
    ``{original_url: new_url}`` map.

    Fresh server-generated names mean (a) no collision with existing files,
    (b) no overwrite of unrelated media, and (c) no path-traversal from a
    crafted archive — the archive's own filenames are never used on disk.
    """
    root = uploads_root or _UPLOADS_ROOT
    url_map: dict[str, str] = {}
    for entry in (manifest.get("media_manifest") or []):
        if not isinstance(entry, dict):
            continue
        arc = entry.get("archive_path") or ""
        orig = entry.get("original_url") or ""
        if not arc.startswith("media/") or not orig:
            continue
        parts = arc.split("/")
        if len(parts) < 3:
            continue
        bucket = _SAFE_BUCKET.sub("", parts[1].lower()) or "misc"
        ext = Path(parts[-1]).suffix.lower()
        if not _SAFE_EXT.match(ext):
            ext = ""
        try:
            blob = zf.read(arc)
        except KeyError:
            continue
        dest_dir = root / bucket
        dest_dir.mkdir(parents=True, exist_ok=True)
        new_name = f"{uuid.uuid4().hex}{ext}"
        (dest_dir / new_name).write_bytes(blob)
        url_map[orig] = f"{_UPLOADS_URL_PREFIX}{bucket}/{new_name}"
    return url_map


def rewrite_urls(obj: Any, url_map: dict[str, str]) -> Any:
    """Deep-copy ``obj`` replacing any string equal to an ``original_url`` key
    with its ``new_url``. Leaves everything else untouched."""
    if not url_map:
        return obj
    if isinstance(obj, str):
        return url_map.get(obj, obj)
    if isinstance(obj, dict):
        return {k: rewrite_urls(v, url_map) for k, v in obj.items()}
    if isinstance(obj, list):
        return [rewrite_urls(v, url_map) for v in obj]
    return obj


def cleanup_extracted(url_map: dict[str, str], *, uploads_root: Optional[Path] = None) -> None:
    """Best-effort unlink of media written by ``extract_media`` — call when the
    DB transaction that would reference them rolls back, so a failed import
    doesn't leave orphaned files."""
    root = uploads_root or _UPLOADS_ROOT
    for new_url in url_map.values():
        try:
            _new_url_to_abs(new_url, root).unlink(missing_ok=True)
        except OSError:
            pass
