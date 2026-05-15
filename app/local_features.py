"""
Local-first overrides for class / subclass feature data.

Resolution flow
---------------
A provider chain is consulted in priority order before any Open5e call.
Currently only the filesystem provider is wired; a future DB-backed
provider for per-campaign / per-user custom subclasses will be added as
a single entry to ``_CLASS_PROVIDERS`` / ``_SUBCLASS_PROVIDERS``.

Scopes
------
Every override record may carry an optional ``scope`` (default
``"global"``) and ``owner`` (default ``null``).  Resolver callers may
pass a list of scopes in priority order; providers filter records to
those whose ``scope`` matches one of the entries.  No caller threads a
non-global scope yet — future endpoints will pass e.g.
``scopes=["campaign:42", "user:7", "global"]`` to surface campaign- or
user-specific homebrew before falling back to the shipped SRD content.

Source labels
-------------
Resolver functions return ``(record, source)`` where ``source`` is one of:

  - ``"local-srd"``     filesystem record whose ``"source"`` field is
                        absent or ``"srd"`` (the SRD-equivalent content
                        this project ships).
  - ``"local-custom"``  filesystem record marked ``"source": "custom"``
                        (homebrew added by an operator dropping a file).
  - ``"local-db"``      reserved for the future DB-backed provider.

The proxy endpoints echo this string back in the response payload so the
frontend can render an authoring affordance only on custom content.

File layout
-----------
Content is namespaced by game system from disk on outward so a future
second system (PF2e, CoC, …) can ship alongside D&D 5e without renames:

``app/data/local/<system>/class_features/<slug>.json``
``app/data/local/<system>/subclass_features/<class_slug>__<sub_slug>.json``
``app/data/local/<system>/races/<slug>.json``

Only ``dnd5e`` ships today; the constants below pin to that subtree.
When a second system arrives the loader will accept a ``system`` arg
and resolve paths against ``_DATA_DIR / system / …``.
"""
from __future__ import annotations

import json
import pathlib
import threading
import time
from typing import Callable, Optional

_DATA_DIR = pathlib.Path(__file__).parent / "data" / "local"
_SYSTEM_DIR = _DATA_DIR / "dnd5e"
_CLASS_DIR = _SYSTEM_DIR / "class_features"
_SUBCLASS_DIR = _SYSTEM_DIR / "subclass_features"
_RACE_DIR = _SYSTEM_DIR / "races"

_lock = threading.Lock()
_misses: dict[str, dict] = {}


def _safe_slug(s: str) -> str:
    """Reject anything that could escape the data directory."""
    s = (s or "").strip().lower()
    if not s or "/" in s or "\\" in s or ".." in s:
        return ""
    return s


def _load_json(path: pathlib.Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _scope_of(rec: dict) -> str:
    return (rec.get("scope") or "global").lower()


def _label_for_fs_record(rec: dict) -> str:
    src = (rec.get("source") or "srd").lower()
    return "local-custom" if src == "custom" else "local-srd"


# ── Provider chain ────────────────────────────────────────────────────────────
#
# Each provider returns ``(record, source_label)`` on hit, ``None`` on miss.
# Providers are responsible for their own scope filtering and source labelling
# so the same chain can host filesystem files, DB rows, in-memory test
# fixtures, etc., each with their own conventions.

ClassProvider = Callable[..., Optional[tuple[dict, str]]]
SubclassProvider = Callable[..., Optional[tuple[dict, str]]]


def _fs_class_provider(slug: str, *, scopes: list[str], db=None) -> tuple[dict, str] | None:
    # ``db`` accepted but ignored — filesystem provider needs no DB session.
    s = _safe_slug(slug)
    if not s:
        return None
    rec = _load_json(_CLASS_DIR / f"{s}.json")
    if not rec or _scope_of(rec) not in scopes:
        return None
    return rec, _label_for_fs_record(rec)


def _features_to_markdown(features: list) -> str:
    """Flatten a structured feature list into the markdown blob shape the
    existing frontend already consumes from the class-detail endpoint.
    Mirrors the heading style Open5e uses (### per feature)."""
    parts = []
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


def _ordinal_suffix(n) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    if 10 <= (n % 100) <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


# _db_class_provider removed in v2.0.0. Homebrew classes now live in
# per-slug JSON files; ``app/local_content.py`` is the source of truth.


def _fs_subclass_provider(class_slug: str, sub_slug: str, *, scopes: list[str], db=None) -> tuple[dict, str] | None:
    # ``db`` accepted but ignored — filesystem provider needs no DB session.
    sub = _safe_slug(sub_slug)
    if not sub:
        return None
    cls = _safe_slug(class_slug)
    # Prefer the class-prefixed file (disambiguates same-named subclasses
    # across classes), then fall back to the bare-slug file.
    candidates: list[pathlib.Path] = []
    if cls:
        candidates.append(_SUBCLASS_DIR / f"{cls}__{sub}.json")
    candidates.append(_SUBCLASS_DIR / f"{sub}.json")
    for path in candidates:
        rec = _load_json(path)
        if rec and _scope_of(rec) in scopes:
            return rec, _label_for_fs_record(rec)
    return None


# _db_subclass_provider removed in v2.0.0. See note above _db_class_provider.


# _db_race_provider removed in v2.0.0. See note above _db_class_provider.


def _fs_race_provider(slug: str, *, scopes: list[str], db=None) -> tuple[dict, str] | None:
    """Shipped FS races under ``app/data/local/dnd5e/races/<slug>.json``.

    Files mirror the shape ``_db_race_provider`` returns so the
    ``/api/open5e/race-detail`` adapter handles both uniformly: ``name``,
    ``ability_bonuses`` (Open5e list of ``{attribute, bonus}``), ``size``,
    ``speed`` (either int or ``{"walk": int}``), ``age``, ``alignment``,
    ``languages``, and ``traits_list`` (structured ``{name, level, desc}``).
    """
    s = _safe_slug(slug)
    if not s:
        return None
    rec = _load_json(_RACE_DIR / f"{s}.json")
    if not rec or _scope_of(rec) not in scopes:
        return None
    # Normalise speed to a dict so the response adapter doesn't have to
    # branch — shipped files may use either ``speed: 30`` (matches the
    # CustomRace authoring form) or ``speed: {"walk": 30}`` (matches the
    # Open5e shape).
    spd = rec.get("speed")
    if isinstance(spd, int):
        rec = {**rec, "speed": {"walk": spd}}
    # Accept ``traits`` as the structured list field on disk (more
    # natural for hand-authoring) and re-emit as ``traits_list`` for the
    # adapter, which won't synthesise a markdown blob if the structured
    # list is non-empty.
    if "traits_list" not in rec and isinstance(rec.get("traits"), list):
        rec = {**rec, "traits_list": rec.get("traits") or []}
    return rec, _label_for_fs_record(rec)


# _db_monster_provider removed in v2.0.0. See note above _db_class_provider.


def _fs_monster_provider(slug: str, *, scopes: list[str], db=None) -> tuple[dict, str] | None:
    """Reserved slot for filesystem-shipped monsters. None yet."""
    return None


# _db_background_provider removed in v2.0.0. See note above _db_class_provider.


def _fs_background_provider(slug: str, *, scopes: list[str], db=None) -> tuple[dict, str] | None:
    """Reserved slot for filesystem-shipped backgrounds. None yet."""
    return None


# _db_feat_provider removed in v2.0.0. See note above _db_class_provider.


def _fs_feat_provider(slug: str, *, scopes: list[str], db=None) -> tuple[dict, str] | None:
    """Reserved slot for filesystem-shipped feats. None yet."""
    return None


RaceProvider = Callable[..., Optional[tuple[dict, str]]]
MonsterProvider = Callable[..., Optional[tuple[dict, str]]]
BackgroundProvider = Callable[..., Optional[tuple[dict, str]]]
FeatProvider = Callable[..., Optional[tuple[dict, str]]]


# v2.0.0: the DB-backed providers were removed when CustomClass / CustomSubclass
# / CustomRace / CustomMonster / CustomBackground / CustomFeat tables were
# dropped. Homebrew now lives in per-slug JSON files served by
# ``app/local_content.py``; this module retains only the shipped-FS providers
# for the residual call sites that still go through ``resolve_*`` here.
_CLASS_PROVIDERS: list[ClassProvider] = [_fs_class_provider]
_SUBCLASS_PROVIDERS: list[SubclassProvider] = [_fs_subclass_provider]
_RACE_PROVIDERS: list[RaceProvider] = [_fs_race_provider]
_MONSTER_PROVIDERS: list[MonsterProvider] = [_fs_monster_provider]
_BACKGROUND_PROVIDERS: list[BackgroundProvider] = [_fs_background_provider]
_FEAT_PROVIDERS: list[FeatProvider] = [_fs_feat_provider]


def resolve_class(slug: str, *, scopes: list[str] | None = None, db=None) -> tuple[dict | None, str | None]:
    """Return ``(record, source)`` or ``(None, None)`` for a class slug.

    ``db`` is accepted for symmetry with ``resolve_subclass`` but not yet
    used — classes have no DB-backed provider in phase 1.
    """
    scopes = scopes or ["global"]
    for fn in _CLASS_PROVIDERS:
        result = fn(slug, scopes=scopes, db=db)
        if result:
            return result
    return None, None


def resolve_subclass(class_slug: str, sub_slug: str, *,
                     scopes: list[str] | None = None, db=None) -> tuple[dict | None, str | None]:
    """Return ``(record, source)`` or ``(None, None)`` for a subclass.

    Pass ``db`` (a SQLAlchemy session) plus a scope string like
    ``"campaign:42"`` to surface campaign-authored homebrew.  Omit either
    and only the filesystem (shipped) overrides are consulted.
    """
    scopes = scopes or ["global"]
    for fn in _SUBCLASS_PROVIDERS:
        result = fn(class_slug, sub_slug, scopes=scopes, db=db)
        if result:
            return result
    return None, None


def resolve_race(slug: str, *, scopes: list[str] | None = None, db=None) -> tuple[dict | None, str | None]:
    """Return ``(record, source)`` or ``(None, None)`` for a race slug.

    Same contract as ``resolve_class``: campaign-scoped homebrew wins over
    shipped FS files (none yet for races).
    """
    scopes = scopes or ["global"]
    for fn in _RACE_PROVIDERS:
        result = fn(slug, scopes=scopes, db=db)
        if result:
            return result
    return None, None


def resolve_monster(slug: str, *, scopes: list[str] | None = None, db=None) -> tuple[dict | None, str | None]:
    """Return ``(record, source)`` or ``(None, None)`` for a monster slug.

    Returns the full stat-block shape; callers serving the lite picker
    response trim down via ``_creature_lite`` (or equivalent).
    """
    scopes = scopes or ["global"]
    for fn in _MONSTER_PROVIDERS:
        result = fn(slug, scopes=scopes, db=db)
        if result:
            return result
    return None, None


def resolve_background(slug: str, *, scopes: list[str] | None = None, db=None) -> tuple[dict | None, str | None]:
    """Return ``(record, source)`` or ``(None, None)`` for a background slug."""
    scopes = scopes or ["global"]
    for fn in _BACKGROUND_PROVIDERS:
        result = fn(slug, scopes=scopes, db=db)
        if result:
            return result
    return None, None


def resolve_feat(slug: str, *, scopes: list[str] | None = None, db=None) -> tuple[dict | None, str | None]:
    """Return ``(record, source)`` or ``(None, None)`` for a feat slug."""
    scopes = scopes or ["global"]
    for fn in _FEAT_PROVIDERS:
        result = fn(slug, scopes=scopes, db=db)
        if result:
            return result
    return None, None


# ── Miss registry ─────────────────────────────────────────────────────────────

def record_miss(kind: str, slug: str, *, class_slug: str = "", source: str = "open5e_live") -> None:
    """Record a lookup that wasn't satisfied by a local override.

    ``kind``   — "class" or "subclass"
    ``source`` — where the response did come from
                 (``open5e_mirror``, ``open5e_live``, ``open5e_unreachable``)
    """
    if not slug:
        return
    key = f"{kind}:{class_slug}:{slug}" if class_slug else f"{kind}:{slug}"
    now = time.time()
    with _lock:
        m = _misses.get(key)
        if m is None:
            _misses[key] = {
                "kind": kind,
                "slug": slug,
                "class_slug": class_slug,
                "source": source,
                "count": 1,
                "first_seen": now,
                "last_seen": now,
            }
        else:
            m["count"] += 1
            m["last_seen"] = now
            m["source"] = source


def list_misses() -> list[dict]:
    with _lock:
        return sorted(_misses.values(), key=lambda m: m["count"], reverse=True)


def clear_misses() -> None:
    with _lock:
        _misses.clear()


# ── Discovery helpers (for admin panels) ──────────────────────────────────────

def list_local_classes() -> list[dict]:
    """Discovery helper for shipped FS classes. Returns parsed name +
    hit die alongside the slug so admin views and the search endpoint
    can render a useful summary without reopening each file."""
    if not _CLASS_DIR.exists():
        return []
    rows = []
    for p in sorted(_CLASS_DIR.glob("*.json")):
        rec = _load_json(p) or {}
        rows.append({
            "slug": p.stem,
            "name": rec.get("name") or p.stem,
            "hit_die": rec.get("hit_die"),
            "file": p.name,
        })
    return rows


def list_local_subclasses() -> list[dict]:
    if not _SUBCLASS_DIR.exists():
        return []
    rows = []
    for p in sorted(_SUBCLASS_DIR.glob("*.json")):
        stem = p.stem
        if "__" in stem:
            cls, _, sub = stem.partition("__")
        else:
            cls, sub = "", stem
        rows.append({"class_slug": cls, "sub_slug": sub, "file": p.name})
    return rows


def list_local_races() -> list[dict]:
    """Discovery helper for shipped FS races. Mirrors ``list_local_classes``
    but returns the parsed name/size alongside the slug so admin views can
    render a useful summary without reopening each file."""
    if not _RACE_DIR.exists():
        return []
    rows = []
    for p in sorted(_RACE_DIR.glob("*.json")):
        rec = _load_json(p) or {}
        rows.append({
            "slug": p.stem,
            "name": rec.get("name") or p.stem,
            "size": rec.get("size") or "",
            "file": p.name,
        })
    return rows
