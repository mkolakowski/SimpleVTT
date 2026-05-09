"""
Optional local Open5e data cache for faster lookups.

Enable with the environment variable:
    LOCAL_OPEN5E=true

Then run the sync script once to download the data:
    python scripts/sync_open5e.py

Data is stored in app/data/open5e/{classes,subclasses,races,spells}.json.
When enabled the proxy endpoints skip the external HTTP call entirely.
"""
from __future__ import annotations

import json
import os
import pathlib

DATA_DIR = pathlib.Path(__file__).parent / "data" / "open5e"
ENABLED: bool = os.getenv("LOCAL_OPEN5E", "").lower() in ("1", "true", "yes")

_db: dict[str, list] = {}


def _load() -> None:
    if not ENABLED:
        return
    for name in ("classes", "subclasses", "races", "spells", "conditions"):
        p = DATA_DIR / f"{name}.json"
        if p.exists():
            with open(p, encoding="utf-8") as f:
                _db[name] = json.load(f)


def is_ready() -> bool:
    """True when local mode is enabled AND at least one data file was loaded."""
    return ENABLED and bool(_db)


def _match(item: dict, q: str) -> bool:
    return not q or q.lower() in (item.get("name") or "").lower()


def _source(item: dict) -> str:
    src = item.get("document__title", "")
    if not src:
        doc = item.get("document")
        if isinstance(doc, dict):
            src = doc.get("title", "")
    return src


# ── Classes ───────────────────────────────────────────────────────────────────

def search_classes(q: str = "", limit: int = 30) -> tuple[list, int]:
    items = [c for c in _db.get("classes", []) if _match(c, q)]
    return items[:limit], len(items)


def get_class(slug: str) -> dict | None:
    for c in _db.get("classes", []):
        if c.get("slug") == slug:
            return c
    return None


# ── Subclasses ────────────────────────────────────────────────────────────────

def _class_slug_of(s: dict) -> str:
    """Return the parent class slug for a subclass record (handles multiple API shapes)."""
    if s.get("class_slug"):
        return str(s["class_slug"])
    cls = s.get("class")
    if isinstance(cls, dict):
        return cls.get("slug", "")
    if isinstance(cls, str):
        return cls.lower().replace(" ", "-")
    return ""


def search_subclasses(q: str = "", class_slug: str = "", limit: int = 100) -> tuple[list, int]:
    items = _db.get("subclasses", [])
    if class_slug:
        items = [s for s in items if _class_slug_of(s) == class_slug]
    if q:
        items = [s for s in items if _match(s, q)]
    return items[:limit], len(items)


def get_subclass(slug: str) -> dict | None:
    for s in _db.get("subclasses", []):
        if s.get("slug") == slug:
            return s
    return None


# ── Races ─────────────────────────────────────────────────────────────────────

def search_races(q: str = "", limit: int = 30) -> tuple[list, int]:
    items = [r for r in _db.get("races", []) if _match(r, q)]
    return items[:limit], len(items)


def get_race(slug: str) -> dict | None:
    for r in _db.get("races", []):
        if r.get("slug") == slug:
            return r
    return None


# ── Conditions ────────────────────────────────────────────────────────────────

def search_conditions(q: str = "", limit: int = 50) -> tuple[list, int]:
    items = [c for c in _db.get("conditions", []) if _match(c, q)]
    return items[:limit], len(items)


def get_condition(slug: str) -> dict | None:
    for c in _db.get("conditions", []):
        if c.get("slug") == slug:
            return c
    return None


# ── Spells ────────────────────────────────────────────────────────────────────

def search_spells(q: str = "", limit: int = 20, spell_list: str = "", level: int = -1) -> tuple[list, int]:
    items = _db.get("spells", [])
    if q:
        items = [s for s in items if _match(s, q)]
    if spell_list:
        sl = spell_list.lower()
        items = [
            s for s in items
            if sl in [x.lower() for x in (s.get("spell_lists") or [])]
        ]
    if level >= 0:
        items = [s for s in items if (s.get("level_int") or s.get("spell_level") or 0) == level]
    return items[:limit], len(items)


# ── Detail formatters (shared by both local and remote code paths) ─────────────

def format_class_text(c: dict) -> str:
    parts = [f"{c.get('name', '').upper()} — Hit Die: d{c.get('hit_die', '?')}"]
    if c.get("prof_armor"):           parts.append(f"Armor: {c['prof_armor']}")
    if c.get("prof_weapons"):         parts.append(f"Weapons: {c['prof_weapons']}")
    if c.get("prof_tools"):           parts.append(f"Tools: {c['prof_tools']}")
    if c.get("prof_saving_throws"):   parts.append(f"Saving Throws: {c['prof_saving_throws']}")
    if c.get("prof_skills"):          parts.append(f"Skills: {c['prof_skills']}")
    if c.get("spellcasting_ability"): parts.append(f"Spellcasting: {c['spellcasting_ability'].upper()}")
    if c.get("equipment"):            parts.append(f"\nStarting Equipment:\n{c['equipment']}")
    return "\n".join(parts)


def format_subclass_text(s: dict) -> str:
    parts = [s.get("name", "").upper()]
    # subclass_flavor is used by /v1/subclasses/; desc is used by archetypes
    # embedded in /v1/classes/{slug}/
    flavor = s.get("subclass_flavor") or s.get("desc", "")
    if flavor:
        parts.append(flavor[:300])
    features = s.get("features", "") or s.get("feature_items", "")
    if isinstance(features, str) and features:
        parts.append(f"\n{features}")
    elif isinstance(features, list):
        for f in features:
            if isinstance(f, dict) and f.get("name"):
                desc = (f.get("desc") or "")[:600]
                parts.append(f"\n{f['name']}:\n{desc}")
    return "\n".join(parts)


import re as _re


def _extract_level_hint(text: str) -> int | None:
    """Pull the first level number out of a feature description."""
    m = (_re.search(r'\b(\d+)(?:st|nd|rd|th)[- ]level', text, _re.I)
         or _re.search(r'(?:at|reach)[^.\n]{0,30}?(\d+)(?:st|nd|rd|th)', text, _re.I))
    return int(m.group(1)) if m else None


def _parse_feature_text_blob(text: str) -> tuple[str, list]:
    """
    Try to split a flat markdown text blob into (intro_flavor, features).
    Tries (in order): ### headings, **bold** headers, paragraph title lines.
    Returns (intro, features) where features may be empty if nothing was found.
    """
    if not text:
        return "", []

    # Normalise line endings first
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    def _build(raw_parts: list) -> list:
        out = []
        for i in range(1, len(raw_parts) - 1, 2):
            fname = raw_parts[i].strip().rstrip(".")
            fdesc = (raw_parts[i + 1] if i + 1 < len(raw_parts) else "").strip()
            out.append({"name": fname, "desc": fdesc, "level": _extract_level_hint(fdesc)})
        return out

    # ── Strategy 0: split on markdown headings (Open5e uses ##### = 5 hashes) ──
    heading_pat = _re.compile(r'\n#{2,6}\s+([^\n]+)\n', _re.M)
    parts = heading_pat.split("\n" + text)
    if len(parts) >= 3:
        return parts[0].strip(), _build(parts)

    # ── Strategy 1: split on bold (**Name** or ***Name***) paragraph headers ──
    bold_pat = _re.compile(r'\n\*{2,3}([^*\n]+?)\*{2,3}\.?\s*\n', _re.M)
    parts = bold_pat.split("\n" + text)
    if len(parts) >= 3:
        return parts[0].strip(), _build(parts)

    # ── Strategy 2: split on paragraph boundaries; first paragraph = intro ──
    # Treat short title-like paragraphs as feature headers.
    paras = [p.strip() for p in _re.split(r'\n{2,}', text) if p.strip()]
    if len(paras) >= 3:
        features = []
        intro_parts: list[str] = []
        for para in paras:
            lines = para.splitlines()
            first = lines[0].strip()
            rest  = "\n".join(lines[1:]).strip()
            # Short title line (≤ 60 chars, no full-stop, looks like a proper noun)
            if (rest and len(first) <= 60 and not first.endswith(".")
                    and _re.match(r'^[A-Z][A-Za-z ,\'\-]+$', first)):
                features.append({
                    "name": first,
                    "desc": rest,
                    "level": _extract_level_hint(rest),
                })
            else:
                if not features:
                    intro_parts.append(para)
        if features:
            return "\n\n".join(intro_parts), features

    return text, []


def parse_subclass_features(s: dict) -> dict:
    """Return structured subclass data for rich front-end rendering."""
    name = s.get("name", "")
    flavor = (s.get("subclass_flavor") or s.get("desc", "") or "").strip()

    raw = s.get("features", "") or s.get("feature_items", "")
    features: list[dict] = []

    if isinstance(raw, list):
        for f in raw:
            if not isinstance(f, dict):
                continue
            fname = (f.get("name") or "").strip()
            fdesc = (f.get("desc") or "").strip()
            flevel = f.get("level") or f.get("feature_level") or f.get("min_level")
            # Some API shapes nest the feature under a "feature" key
            if not fname and isinstance(f.get("feature"), dict):
                inner = f["feature"]
                fname = (inner.get("name") or "").strip()
                fdesc = (inner.get("desc") or fdesc).strip()
            if fname or fdesc:
                features.append({
                    "name": fname,
                    "desc": fdesc,
                    "level": int(flevel) if flevel is not None else None,
                })

    # If no structured features from the list, try parsing the text blobs
    if not features:
        # Prefer the raw string field first; fall back to flavor
        blob = (raw if isinstance(raw, str) else "") or flavor
        if blob:
            parsed_flavor, parsed_features = _parse_feature_text_blob(blob)
            if parsed_features:
                # Only update flavor if we parsed FROM the flavor field
                if blob == flavor:
                    flavor = parsed_flavor
                features = parsed_features

    return {"name": name, "flavor": flavor, "features": features}


def format_race_text(r: dict) -> str:
    parts = [r.get("name", "").upper()]
    bonuses = r.get("ability_bonuses", [])
    if isinstance(bonuses, list) and bonuses:
        bs = ", ".join(
            f"+{b.get('bonus', '')} {b.get('attribute', '').replace('Ability Score', '').strip()}"
            for b in bonuses if isinstance(b, dict)
        )
        if bs:
            parts.append(f"Ability Bonuses: {bs}")
    if r.get("size"):      parts.append(f"Size: {r['size']}")
    speed = r.get("speed")
    if isinstance(speed, dict): parts.append(f"Speed: {speed.get('walk', 30)} ft.")
    elif speed:                 parts.append(f"Speed: {speed} ft.")
    if r.get("age"):       parts.append(f"\nAge: {r['age']}")
    if r.get("alignment"): parts.append(f"Alignment: {r['alignment']}")
    if r.get("languages"): parts.append(f"Languages: {r['languages']}")
    if r.get("traits"):    parts.append(f"\nTraits:\n{r['traits']}")
    return "\n".join(parts)


def parse_race_traits(r: dict) -> dict:
    """Return structured race data for rich front-end rendering.

    Mirrors parse_subclass_features() but for races.  The Open5e race object
    has stat fields (ability_bonuses, size, speed, age, alignment, languages)
    which become the flavor summary, and a free-text 'traits' blob that is
    split into individual trait cards using the same heading parser.
    """
    name = r.get("name", "")

    # ── Build a concise stat summary as the intro flavor ─────────────────
    stat_parts: list[str] = []
    bonuses = r.get("ability_bonuses", [])
    if isinstance(bonuses, list) and bonuses:
        bs = ", ".join(
            f"+{b.get('bonus', '')} {b.get('attribute', '').replace('Ability Score', '').strip()}"
            for b in bonuses if isinstance(b, dict)
        )
        if bs:
            stat_parts.append(f"Ability Bonuses: {bs}")
    if r.get("size"):
        stat_parts.append(f"Size: {r['size']}")
    speed = r.get("speed")
    if isinstance(speed, dict):
        stat_parts.append(f"Speed: {speed.get('walk', 30)} ft.")
    elif speed:
        stat_parts.append(f"Speed: {speed} ft.")
    if r.get("age"):
        stat_parts.append(f"Age: {r['age']}")
    if r.get("alignment"):
        stat_parts.append(f"Alignment: {r['alignment']}")
    if r.get("languages"):
        stat_parts.append(f"Languages: {r['languages']}")
    flavor = "\n".join(stat_parts)

    # ── Parse the traits text blob into individual trait cards ────────────
    traits_blob = (r.get("traits") or "").strip()
    traits: list[dict] = []
    if traits_blob:
        _intro, parsed = _parse_feature_text_blob(traits_blob)
        if parsed:
            traits = parsed
        else:
            # No heading structure — one card for the whole block
            traits = [{"name": "Racial Traits", "desc": traits_blob, "level": None}]

    return {"name": name, "flavor": flavor, "traits": traits}


# ── Manifest & staleness check ────────────────────────────────────────────────

_MANIFEST_PATH = DATA_DIR / "manifest.json"
_PUBLIC_API = "https://api.open5e.com/v1"
_CHECK_RESOURCES = ("classes", "subclasses", "races", "spells", "conditions")


def read_manifest() -> dict:
    if _MANIFEST_PATH.exists():
        with open(_MANIFEST_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def check_staleness() -> dict:
    """Compare local manifest counts against the live public Open5e API.

    Always hits api.open5e.com directly so we're comparing local data against
    the authoritative upstream.

    Returns:
        enabled   – False when LOCAL_OPEN5E is not set or data not loaded
        stale     – True if any resource count differs from upstream
        synced_at – ISO timestamp from the manifest, or None
        details   – per-resource {local, remote, stale}
    """
    import urllib.request as _urlreq

    if not is_ready():
        return {"enabled": False}

    manifest = read_manifest()
    local_counts: dict = manifest.get("counts", {})
    synced_at: str | None = manifest.get("synced_at")

    details: dict = {}
    any_stale = False

    for name in _CHECK_RESOURCES:
        local = local_counts.get(name, 0)
        remote: int | None = None
        try:
            url = f"{_PUBLIC_API}/{name}/?limit=1"
            req = _urlreq.Request(url, headers={"User-Agent": "SimpleVTT/1.0"})
            with _urlreq.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            remote = int(data.get("count", 0))
        except Exception:
            pass  # network unavailable — skip this resource

        is_stale = remote is not None and remote != local
        if is_stale:
            any_stale = True
        details[name] = {"local": local, "remote": remote, "stale": is_stale}

    return {
        "enabled": True,
        "stale": any_stale,
        "synced_at": synced_at,
        "details": details,
    }


# Load at import time
_load()
