"""Unified file-based content resolver.

Replaces ``app/local_features.py`` (which only knew about class_features /
subclass_features / races) and absorbs spell / item / feat / monster /
background / condition resolution into the same two-tier chain.

Resolution priority
-------------------
For each ``(slug, system, type)`` lookup the resolver checks:

1. **Homebrew tier** — files under ``HOMEBREW_ROOT/<system>/<scope>/<type>/``
   where ``<scope>`` is ``campaign-<id>`` for campaign-scoped requests, falling
   back to ``global``. Source label ``"local-homebrew"``.
2. **Shipped SRD tier** — files under ``SHIPPED_ROOT/<system>/<type>/``.
   Source label ``"local-srd"``.

Open5e — both the mega-file mirror and the live API — is a tier-3 fallback
consulted only when both tiers above miss. Those callers stay on the
existing ``open5e_local`` and live-fetch code paths in ``tabletop_routes``.

Path safety
-----------
``_safe_slug`` and ``_safe_scope`` reject anything that could escape the
tier root (``/``, ``\\``, ``..``). They mirror ``local_features._safe_slug``.

Caching
-------
Reads are cached by ``(path, mtime)`` so directory walks don't re-stat every
JSON every request. The cache is invalidated automatically when a file is
rewritten (mtime changes) so admin edits show up on the next read without an
explicit eviction.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import threading
from typing import Optional

from pydantic import BaseModel, ValidationError

from .content_schemas import TYPE_REGISTRY

log = logging.getLogger(__name__)

# ── Path roots ───────────────────────────────────────────────────────────────
SHIPPED_ROOT = pathlib.Path(__file__).parent / "data" / "local"
HOMEBREW_ROOT = pathlib.Path(
    os.getenv("HOMEBREW_DATA_DIR", str(pathlib.Path(__file__).parent / "data" / "homebrew"))
)

_lock = threading.Lock()
_cache: dict[pathlib.Path, tuple[float, dict]] = {}


# ── Safety helpers ───────────────────────────────────────────────────────────
def _safe_slug(s: str) -> str:
    """Reject anything that could escape the data directory (path traversal,
    nested paths, hidden files). Returns the lowercased slug or ``""`` on
    rejection."""
    s = (s or "").strip().lower()
    if not s or "/" in s or "\\" in s or ".." in s or s.startswith("."):
        return ""
    return s


def _safe_scope(s: str) -> str:
    """Accept ``"global"`` or ``"campaign-<digits>"``. Anything else (including
    user-supplied campaign ids with non-numeric junk) is rejected."""
    s = (s or "").strip().lower()
    if s == "global":
        return "global"
    if s.startswith("campaign-") and s[9:].isdigit():
        return s
    return ""


def _safe_type(t: str) -> str:
    """Accept only the registered content type names."""
    t = (t or "").strip().lower()
    return t if t in TYPE_REGISTRY else ""


def _safe_system(s: str) -> str:
    """Accept any non-empty alphanumeric system identifier."""
    s = (s or "").strip().lower()
    if not s or not all(c.isalnum() or c in "-_" for c in s):
        return ""
    return s


# ── Format helpers (moved from the deleted local_features.py) ────────────────
def _ordinal_suffix(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    if 10 <= (n % 100) <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def features_to_markdown(features: list) -> str:
    """Flatten a structured feature list into the markdown blob the existing
    sheet consumes. Each entry becomes a ``### {name}`` section with an
    optional ``*Nth-level feature*`` subtitle. Used by the v52 migration when
    exporting ``CustomClass.features`` (a JSON list) to the shipped
    ``ClassFeature.features`` (a markdown string)."""
    parts: list[str] = []
    for f in features or []:
        if not isinstance(f, dict):
            continue
        name = (f.get("name") or "").strip()
        if not name:
            continue
        lvl = f.get("level")
        lvl_line = f"*{lvl}{_ordinal_suffix(lvl)}-level feature*\n\n" if lvl else ""
        desc = (f.get("desc") or "").strip()
        parts.append(f"### {name}\n{lvl_line}{desc}".strip())
    return "\n\n".join(parts)


# ── Disk I/O ─────────────────────────────────────────────────────────────────
def _load_and_validate(path: pathlib.Path, model: type[BaseModel]) -> Optional[dict]:
    """Return the cached or freshly-loaded record at ``path``, validated by
    ``model``. Returns ``None`` if the file is missing, malformed, or fails
    validation (each failure mode logs a single warning)."""
    if not path.exists():
        return None
    try:
        mtime = path.stat().st_mtime
    except OSError as e:
        log.warning("local_content: stat failed for %s: %s", path, e)
        return None
    with _lock:
        cached = _cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("local_content: failed to read %s: %s", path, e)
        return None
    try:
        record = model.model_validate(raw).model_dump(by_alias=True)
    except ValidationError as e:
        log.warning("local_content: %s failed schema validation: %s", path, e)
        return None
    with _lock:
        _cache[path] = (mtime, record)
    return record


def _label_for_record(rec: dict, *, tier: str) -> str:
    """Return the ``source`` label echoed back to the frontend.

    ``tier="homebrew"`` always returns ``"local-homebrew"``. ``tier="shipped"``
    inspects the record's ``source`` field: SRD content gets ``"local-srd"``;
    anything marked ``"custom"`` (a homebrew file someone dropped into the
    shipped dir) gets ``"local-custom"``.
    """
    if tier == "homebrew":
        return "local-homebrew"
    return "local-custom" if (rec.get("source") or "srd").lower() == "custom" else "local-srd"


# ── Path builders ────────────────────────────────────────────────────────────
def _homebrew_dir(*, system: str, scope: str, type: str) -> pathlib.Path:
    return HOMEBREW_ROOT / system / scope / type


def _shipped_dir(*, system: str, type: str) -> pathlib.Path:
    return SHIPPED_ROOT / system / type


def _candidate_scopes(campaign_id: Optional[int]) -> list[str]:
    """Build the scope-priority list for a lookup. Campaign-scoped homebrew
    beats global homebrew."""
    scopes: list[str] = []
    if campaign_id is not None:
        scopes.append(f"campaign-{int(campaign_id)}")
    scopes.append("global")
    return scopes


# ── Public API ───────────────────────────────────────────────────────────────
def resolve(
    slug: str,
    *,
    system: str = "dnd5e",
    type: str,
    campaign_id: Optional[int] = None,
) -> Optional[tuple[dict, str]]:
    """Look up one record by slug across both tiers.

    Returns ``(record, source_label)`` on hit, ``None`` on miss. Source labels
    follow the convention from the docstring header.
    """
    sys = _safe_system(system)
    typ = _safe_type(type)
    sl = _safe_slug(slug)
    if not (sys and typ and sl):
        return None
    model = TYPE_REGISTRY[typ]

    # 1. Homebrew tier — scope priority: campaign-N then global.
    for scope in _candidate_scopes(campaign_id):
        path = _homebrew_dir(system=sys, scope=scope, type=typ) / f"{sl}.json"
        rec = _load_and_validate(path, model)
        if rec is not None:
            return rec, _label_for_record(rec, tier="homebrew")

    # 2. Shipped SRD tier.
    path = _shipped_dir(system=sys, type=typ) / f"{sl}.json"
    rec = _load_and_validate(path, model)
    if rec is not None:
        return rec, _label_for_record(rec, tier="shipped")

    return None


def search(
    q: str = "",
    *,
    system: str = "dnd5e",
    type: str,
    campaign_id: Optional[int] = None,
    limit: int = 100,
) -> tuple[list[dict], int]:
    """List all records across both tiers, filtered by an optional substring
    match against ``name``. Homebrew records override shipped records with the
    same slug; campaign-scoped homebrew overrides global homebrew.

    Returns ``(records, total_before_limit)``. Each record has a synthetic
    ``_source`` key set to the resolver label so the caller can surface
    provenance without re-resolving.
    """
    sys = _safe_system(system)
    typ = _safe_type(type)
    if not (sys and typ):
        return [], 0
    model = TYPE_REGISTRY[typ]

    seen: dict[str, dict] = {}

    def _ingest(dir_: pathlib.Path, tier: str):
        if not dir_.is_dir():
            return
        for p in dir_.iterdir():
            if not p.name.endswith(".json"):
                continue
            slug = p.stem
            if slug in seen:
                continue  # higher tier already won
            rec = _load_and_validate(p, model)
            if rec is None:
                continue
            rec = {**rec, "_source": _label_for_record(rec, tier=tier)}
            seen[slug] = rec

    # Walk homebrew tiers first (campaign before global) so they take
    # precedence in the `seen` map.
    for scope in _candidate_scopes(campaign_id):
        _ingest(_homebrew_dir(system=sys, scope=scope, type=typ), "homebrew")
    _ingest(_shipped_dir(system=sys, type=typ), "shipped")

    records = list(seen.values())
    if q:
        needle = q.lower()
        records = [r for r in records if needle in (r.get("name") or "").lower()]
    total = len(records)
    records.sort(key=lambda r: (r.get("name") or r.get("slug") or "").lower())
    return records[:max(1, int(limit))], total


def write_homebrew(
    record: dict,
    *,
    system: str = "dnd5e",
    type: str,
    scope: str = "global",
) -> pathlib.Path:
    """Validate the record against its Pydantic model and atomically write it
    to the homebrew volume.

    Raises ``ValueError`` on invalid system / type / scope / slug, or on
    Pydantic validation failure (the caller surfaces this as HTTP 400).
    Returns the final on-disk path.
    """
    sys = _safe_system(system)
    typ = _safe_type(type)
    scp = _safe_scope(scope)
    if not (sys and typ and scp):
        raise ValueError(f"invalid system/type/scope: {system!r}/{type!r}/{scope!r}")

    slug = _safe_slug(record.get("slug", ""))
    if not slug:
        raise ValueError(f"invalid or missing slug: {record.get('slug')!r}")

    model = TYPE_REGISTRY[typ]
    validated = model.model_validate(record).model_dump(by_alias=True)

    dir_ = _homebrew_dir(system=sys, scope=scp, type=typ)
    dir_.mkdir(parents=True, exist_ok=True)
    final = dir_ / f"{slug}.json"
    tmp = dir_ / f".{slug}.json.tmp"
    tmp.write_text(json.dumps(validated, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, final)

    # Invalidate cache entry so the next read sees the new content.
    with _lock:
        _cache.pop(final, None)
    return final


def delete_homebrew(
    slug: str,
    *,
    system: str = "dnd5e",
    type: str,
    scope: str = "global",
) -> bool:
    """Remove a homebrew file. Returns ``True`` if a file was deleted,
    ``False`` if no such file existed. Raises ``ValueError`` on invalid
    system/type/scope/slug."""
    sys = _safe_system(system)
    typ = _safe_type(type)
    scp = _safe_scope(scope)
    sl = _safe_slug(slug)
    if not (sys and typ and scp and sl):
        raise ValueError(f"invalid system/type/scope/slug: {system!r}/{type!r}/{scope!r}/{slug!r}")
    final = _homebrew_dir(system=sys, scope=scp, type=typ) / f"{sl}.json"
    if not final.exists():
        return False
    final.unlink()
    with _lock:
        _cache.pop(final, None)
    return True
