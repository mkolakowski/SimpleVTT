"""Reusable primitives for building ``simplevtt-export`` zip archives.

Phase 2 of the backup/export-import arc
(``docs/plans/backup-export-overhaul.md``). This module carries the
*mechanics* every export level (PC sheet / campaign / homebrew item)
shares, kept deliberately generic so the per-level data-tree assembly
(landing in Phase 4 alongside the campaign-export endpoint) just feeds
plain dicts + a media list into ``write_bundle_zip``:

  - ``row_to_dict`` — JSON-safe projection of any ORM row via SQLAlchemy
    column inspection, so we don't hand-maintain a column list per model.
  - ``find_media_urls`` — recursively scan serialized data for the
    ``/static/uploads/...`` references that must be bundled.
  - ``archive_path_for`` / ``abs_path_for_url`` — map an uploads URL to its
    in-zip path and its on-disk source.
  - ``build_manifest`` — the envelope (mirrors the ``simplevtt-homebrew``
    convention: a ``format`` + ``version`` root).
  - ``write_bundle_zip`` — stream a manifest + ``data/*.json`` tree +
    bundled ``media/`` binaries into a zip at a staging path.

FastAPI-free; only depends on SQLAlchemy (already a hard dependency) so
the primitives are unit-testable host-side without the web stack.
"""
from __future__ import annotations

import enum
import io
import json
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional

EXPORT_FORMAT = "simplevtt-export"
EXPORT_VERSION = 1

# Uploaded media lives under ``app/static/uploads/<bucket>/<file>`` and is
# referenced by stored URLs that always start with this prefix.
_STATIC_ROOT = Path(__file__).resolve().parent / "static"
_UPLOADS_URL_PREFIX = "/static/uploads/"


def _json_safe(value: Any) -> Any:
    """Coerce a column value into something ``json.dumps`` accepts.

    Datetimes/dates → ISO-8601; enums → their value; everything else is
    passed through (JSON columns are already dict/list/scalar)."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    return value


def row_to_dict(obj: Any) -> dict[str, Any]:
    """JSON-safe ``{column: value}`` for an ORM row, via mapper inspection.

    Generic so a new column on any model is exported automatically (no
    per-model projection to keep in sync). Only mapped *columns* are
    included — relationships are walked explicitly by the per-level
    assembly so the archive layout stays deterministic."""
    from sqlalchemy import inspect as sa_inspect  # lazy: keep the module importable without SQLAlchemy

    mapper = sa_inspect(obj).mapper
    return {attr.key: _json_safe(getattr(obj, attr.key)) for attr in mapper.column_attrs}


def find_media_urls(data: Any) -> list[str]:
    """Recursively collect every distinct ``/static/uploads/...`` URL in a
    serialized structure (dict / list / scalar), preserving first-seen
    order. These are the binaries a self-contained archive must bundle."""
    seen: dict[str, None] = {}

    def _walk(node: Any) -> None:
        if isinstance(node, str):
            if node.startswith(_UPLOADS_URL_PREFIX):
                seen.setdefault(node, None)
        elif isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                _walk(v)

    _walk(data)
    return list(seen)


def archive_path_for(url: str) -> str:
    """In-zip path for an uploads URL: ``/static/uploads/maps/x.png`` →
    ``media/maps/x.png``. Non-uploads URLs are returned unchanged under
    ``media/`` so nothing is silently dropped."""
    rel = url[len(_UPLOADS_URL_PREFIX):] if url.startswith(_UPLOADS_URL_PREFIX) else url.lstrip("/")
    return f"media/{rel}"


def abs_path_for_url(url: str, *, static_root: Optional[Path] = None) -> Optional[Path]:
    """On-disk source path for an uploads URL, or ``None`` if the URL isn't
    an uploads reference. Does not check existence — the caller decides how
    to handle a missing file (skip + log vs. fail)."""
    if not url.startswith(_UPLOADS_URL_PREFIX):
        return None
    root = static_root or _STATIC_ROOT
    return root / url[len("/static/"):]


def build_manifest(
    level: str,
    *,
    app_version: str,
    schema_version: int,
    exported_at: str,
    source_campaign_id: Optional[int] = None,
    source_campaign_name: Optional[str] = None,
    counts: Optional[dict[str, int]] = None,
    media_manifest: Optional[list[dict[str, str]]] = None,
) -> dict[str, Any]:
    """The archive envelope. ``level`` ∈ {campaign, character,
    homebrew-item}. ``exported_at`` is supplied by the caller (the
    module stays clock-free so it's deterministic under test)."""
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "level": level,
        "app_version": app_version,
        "schema_version": schema_version,
        "exported_at": exported_at,
        "source_campaign_id": source_campaign_id,
        "source_campaign_name": source_campaign_name,
        "counts": counts or {},
        "media_manifest": media_manifest or [],
    }


def _write_into(
    zf: zipfile.ZipFile,
    manifest: dict[str, Any],
    data_files: dict[str, Any],
    media_files: Iterable[tuple[str, Path]],
) -> None:
    """Shared core: write the manifest + data + media into an open ZipFile.
    A media source that doesn't exist on disk is skipped (so a stale URL
    never aborts the whole export)."""
    zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    for arc_path, payload in data_files.items():
        zf.writestr(arc_path, json.dumps(payload, indent=2, sort_keys=True))
    for arc_path, src in media_files:
        if src and Path(src).is_file():
            zf.write(src, arc_path)


def write_bundle_zip(
    zip_path: Path,
    *,
    manifest: dict[str, Any],
    data_files: dict[str, Any],
    media_files: Iterable[tuple[str, Path]],
) -> Path:
    """Write a ``simplevtt-export`` zip to ``zip_path`` and return it.

    ``data_files`` maps an in-zip path (e.g. ``data/campaign.json``) to a
    JSON-serializable object. ``media_files`` is an iterable of
    ``(archive_path, source_abs_path)``.
    """
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        _write_into(zf, manifest, data_files, media_files)
    return zip_path


def bundle_to_bytes(
    *,
    manifest: dict[str, Any],
    data_files: dict[str, Any],
    media_files: Iterable[tuple[str, Path]],
) -> bytes:
    """Build a ``simplevtt-export`` zip in memory and return its bytes. For
    small archives (e.g. a single character) that don't warrant the
    background-job + staging-file lifecycle the campaign export uses."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        _write_into(zf, manifest, data_files, media_files)
    return buf.getvalue()
