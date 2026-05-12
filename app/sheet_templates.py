"""Character sheet templates.

Each template defines the default JSON structure stored on Character.sheet.
The UI reads these and renders form fields. Keep them simple; users can
extend the JSON with arbitrary keys by editing the sheet.
"""
from __future__ import annotations

from typing import Any, Dict, List


GENERIC_TEMPLATE: Dict[str, Any] = {
    "summary": "",
    "stats": {},      # free-form key/value pairs
    # Free-text defenses for systems that don't have a structured damage-
    # type taxonomy. Players write whatever fits their system. The D&D
    # 5e template tracks the same concepts as four chip-toggle lists
    # below.
    "resistances": "",
    "immunities": "",
    "notes": "",
    "inventory": [],  # list of strings
}


# Per-class fields that live both on the sheet (legacy: mirrored from the
# primary class) and on each entry of sheet["classes"] (multiclass-aware).
CLASS_FIELD_KEYS = (
    "class_hit_die",
    "class_armor",
    "class_weapons",
    "class_tools",
    "class_saving_throws",
    "class_skills",
    "class_spellcasting",
    "class_equipment",
    "class_features",
    "subclass_features",
    "subclass_name",
    "subclass_flavor",
    "subclass_features_data",  # legacy blob — kept for backward-compat
)


DND5E_TEMPLATE: Dict[str, Any] = {
    "class": "",
    "subclass": "",
    "level": 1,
    # Multiclass roster — array of {class, subclass, level, class_*}.
    # The legacy flat fields above mirror the highest-level entry so callers
    # that haven't been multiclass-aware yet keep working.
    "classes": [],
    "race": "",
    "class_hit_die": "",
    "class_armor": "",
    "class_weapons": "",
    "class_tools": "",
    "class_saving_throws": "",
    "class_skills": "",
    "class_spellcasting": "",
    "class_equipment": "",
    "class_features": "",
    "subclass_features": "",
    "race_traits": "",
    "background": "",
    # Cached background detail (signature feature, description, etc.) so the
    # display block survives a reload without re-fetching from Open5e on every
    # render. Shape: {slug, name, feature, feature_desc, source}. Empty until
    # the player picks a background.
    "background_data": {},
    # List of feats this character has. Each entry caches the fetched detail:
    # {slug, name, prerequisite, desc, source}. The "Custom" badge keys off
    # ``source == "local-custom"`` — matches the subclass / race / monster
    # rendering pattern.
    "feats": [],
    "alignment": "",
    "hp": {"current": 10, "max": 10, "temp": 0},
    "ac": 10,
    "speed": 30,
    "initiative_bonus": 0,
    "proficiency_bonus": 2,
    "abilities": {
        "STR": 10, "DEX": 10, "CON": 10,
        "INT": 10, "WIS": 10, "CHA": 10,
    },
    "saving_throws": {
        "STR": False, "DEX": False, "CON": False,
        "INT": False, "WIS": False, "CHA": False,
    },
    "skills": {
        # list each skill with its ability + whether proficient/expertise
        "Acrobatics":      {"ability": "DEX", "proficient": False, "expertise": False},
        "Animal Handling": {"ability": "WIS", "proficient": False, "expertise": False},
        "Arcana":          {"ability": "INT", "proficient": False, "expertise": False},
        "Athletics":       {"ability": "STR", "proficient": False, "expertise": False},
        "Deception":       {"ability": "CHA", "proficient": False, "expertise": False},
        "History":         {"ability": "INT", "proficient": False, "expertise": False},
        "Insight":         {"ability": "WIS", "proficient": False, "expertise": False},
        "Intimidation":    {"ability": "CHA", "proficient": False, "expertise": False},
        "Investigation":   {"ability": "INT", "proficient": False, "expertise": False},
        "Medicine":        {"ability": "WIS", "proficient": False, "expertise": False},
        "Nature":          {"ability": "INT", "proficient": False, "expertise": False},
        "Perception":      {"ability": "WIS", "proficient": False, "expertise": False},
        "Performance":     {"ability": "CHA", "proficient": False, "expertise": False},
        "Persuasion":      {"ability": "CHA", "proficient": False, "expertise": False},
        "Religion":        {"ability": "INT", "proficient": False, "expertise": False},
        "Sleight of Hand": {"ability": "DEX", "proficient": False, "expertise": False},
        "Stealth":         {"ability": "DEX", "proficient": False, "expertise": False},
        "Survival":        {"ability": "WIS", "proficient": False, "expertise": False},
    },
    "attacks": [],     # [{name, bonus, damage, type}]
    "spells": [],      # [{name, level, school, casting_time, range, duration, components, concentration, ritual, prepared, desc, class}]
    # Spell slots are now nested by class slug to support multi-classing:
    # {"druid": {"1": {"total": 4, "used": 0}, ...}, "wizard": {...}}
    "spell_slots": {},
    # Trackable class / subclass features (Rage, Channel Divinity, Ki, …).
    # Items: {key, name, current, max, reset: 'short'|'long'|'none', source,
    #         class_slug, subclass_slug, desc, manual}. ``max == 0`` means
    # an unlimited / chat-only feature (button announces use, no counter).
    "resources": [],
    # Defenses — each is a list of strings. The Defenses fieldset's chip-
    # toggle UI uses a predefined set of the 13 PHB damage types / 15
    # conditions; anything else (e.g. ``"BPS from nonmagical attacks"``)
    # is stored as a custom chip in the same list. Beasts imported via
    # the Wild Shape picker populate these from Open5e's comma-separated
    # strings so a wild-shaped Druid inherits the form's defenses.
    "damage_resistances": [],
    "damage_immunities": [],
    "damage_vulnerabilities": [],
    "condition_immunities": [],
    # Beast picker favorites — list of starred Open5e creatures, each
    # stored as a lite stat block so the picker can render the
    # "★ Favorites" section without hitting Open5e on every open.
    # Shape: [{slug, name, cr, type, size, hp, ac, source}, …].
    # Legacy data may contain bare slug strings; normalize_dnd5e_sheet
    # coerces those into ``{slug: s}`` entries that the picker treats
    # as cache-misses (backfilled on next open).
    "favorite_beasts": [],
    # Per-class HP gain per character level — { class_slug: [int, int, …] }.
    # Index 0 is the HP gained at level 1 of that class (always max_die +
    # CON_at_time for the FIRST class on the roster; rolled 1dN+CON for
    # level 1 of any subsequent multiclass). Index i is the HP at level
    # i+1. Sum across all classes = total HP from rolls. Populated by the
    # "HP per Level" picker in the sheet edit panel; existing characters
    # show a prompt to backfill on first edit.
    "hp_rolls": {},
    # Wild Shape / Polymorph "active form" overlay. When set, the sheet's
    # HP / AC / speed / abilities / attacks / skills / saves come from a
    # beast statblock; ``prior_form`` is the snapshot that ``revert``
    # restores. Both are ``None`` while the character is in their own form.
    "active_form": None,    # {slug, name, source, started_at, form_sheet}
    "prior_form": None,     # {hp, ac, speed, abilities, skills, saving_throws, attacks, race, initiative_bonus}
    "features": "",
    "inventory": [],
    "notes": "",
}


def get_template(name: str) -> Dict[str, Any]:
    name = (name or "").lower()
    if name == "dnd5e":
        # deep copy by re-construction so callers don't mutate the module-level dict
        import copy
        return copy.deepcopy(DND5E_TEMPLATE)
    import copy
    return copy.deepcopy(GENERIC_TEMPLATE)


def ability_modifier(score: int) -> int:
    return (int(score) - 10) // 2


def class_slug(name: str) -> str:
    """Lower-cased, space-collapsed class slug used as a stable JSON key."""
    return (name or "").strip().lower().replace(" ", "-")


def normalize_dnd5e_sheet(sheet: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure a D&D 5e sheet has a well-formed ``classes`` roster.

    Idempotent. Mutates in place AND returns the sheet for convenience.

    - If ``classes`` is missing/empty, builds a single entry from the legacy
      flat fields (``class``, ``subclass``, ``level``, ``class_hit_die``…).
    - Mirrors the highest-level class onto the legacy flat fields so older
      callers and templates keep working.
    - Sets ``level`` to the sum of all class levels (capped at 20).
    - Migrates a flat ``spell_slots = {"1": {…}}`` to the nested
      ``spell_slots = {<primary_slug>: {"1": {…}}}`` shape.
    - Tags any spell missing ``class`` with the primary class slug.
    """
    if not isinstance(sheet, dict):
        return sheet

    classes = sheet.get("classes")
    if not isinstance(classes, list):
        classes = []

    classes = [c for c in classes if isinstance(c, dict) and (c.get("class") or "").strip()]

    # Build a single-entry roster from legacy flat fields if needed
    if not classes:
        legacy_class = (sheet.get("class") or "").strip()
        if legacy_class:
            entry: Dict[str, Any] = {
                "class": legacy_class,
                "subclass": (sheet.get("subclass") or "").strip(),
                "level": max(1, min(20, int(sheet.get("level") or 1))),
            }
            for k in CLASS_FIELD_KEYS:
                if sheet.get(k) not in (None, ""):
                    entry[k] = sheet.get(k)
            classes = [entry]

    # Normalize each entry, clamp levels into [1, 20]
    for c in classes:
        c["class"] = (c.get("class") or "").strip()
        c["subclass"] = (c.get("subclass") or "").strip()
        try:
            lv = int(c.get("level") or 1)
        except (TypeError, ValueError):
            lv = 1
        c["level"] = max(1, min(20, lv))

    # Cap total levels at 20 by trimming the lowest-level entries
    total = sum(int(c.get("level") or 0) for c in classes)
    if total > 20:
        # Reduce levels from the smallest entries first
        ordered = sorted(range(len(classes)), key=lambda i: int(classes[i].get("level") or 0))
        excess = total - 20
        for i in ordered:
            if excess <= 0:
                break
            cur = int(classes[i].get("level") or 1)
            take = min(cur - 1, excess)  # never drop below level 1
            classes[i]["level"] = cur - take
            excess -= take

    sheet["classes"] = classes

    # Mirror primary (highest-level) class onto the legacy flat fields
    if classes:
        primary = max(classes, key=lambda c: int(c.get("level") or 0))
        sheet["class"] = primary.get("class") or ""
        sheet["subclass"] = primary.get("subclass") or ""
        for k in CLASS_FIELD_KEYS:
            if k in primary:
                sheet[k] = primary.get(k)

    # Total level = sum of class levels (capped)
    sheet["level"] = min(20, sum(int(c.get("level") or 0) for c in classes)) if classes else int(sheet.get("level") or 1)

    # Migrate spell_slots to nested-by-class shape if it's the old flat shape.
    # Old: {"1": {"total": 4, "used": 0}}
    # New: {"<class-slug>": {"1": {"total": 4, "used": 0}}}
    raw_slots = sheet.get("spell_slots") or {}
    if isinstance(raw_slots, dict) and raw_slots:
        # Detect old shape: keys are "1".."9"
        if all(isinstance(k, str) and k.isdigit() for k in raw_slots.keys()):
            primary_slug = class_slug(sheet.get("class") or (classes[0].get("class") if classes else ""))
            sheet["spell_slots"] = {primary_slug: raw_slots} if primary_slug else {}
        else:
            # Already nested — make sure inner values are well-formed dicts
            cleaned: Dict[str, Dict[str, Any]] = {}
            for cslug, by_lvl in raw_slots.items():
                if isinstance(by_lvl, dict):
                    cleaned[cslug] = by_lvl
            sheet["spell_slots"] = cleaned
    else:
        sheet["spell_slots"] = {}

    # Tag legacy spells (no class field) with the primary class slug so
    # they show up under the right group.
    if classes:
        primary_slug = class_slug(sheet.get("class") or "")
        spells = sheet.get("spells")
        if isinstance(spells, list) and primary_slug:
            for s in spells:
                if isinstance(s, dict) and not (s.get("class") or "").strip():
                    s["class"] = primary_slug

    # active_form / prior_form should either be None or a dict — drop
    # malformed values rather than letting them corrupt the sheet.
    if not isinstance(sheet.get("active_form"), (dict, type(None))):
        sheet["active_form"] = None
    if not isinstance(sheet.get("prior_form"), (dict, type(None))):
        sheet["prior_form"] = None

    # favorite_beasts: list of starred creatures. Accepts either a bare
    # slug string (legacy v0.38.0 shape) or a full lite-shape dict
    # ``{slug, name, cr, type, size, hp, ac, source}``. Output is
    # always a list of dicts with at least ``slug``; missing fields
    # are left absent so the client can detect cache-misses and lazily
    # backfill from /api/open5e/creature/{slug}. Dedupes by slug,
    # preserves insertion order, caps at 50.
    raw_favs = sheet.get("favorite_beasts")
    if not isinstance(raw_favs, list):
        raw_favs = []
    _ALLOWED_FAV_KEYS = {"slug", "name", "cr", "type", "size", "hp", "ac", "source"}
    seen_slugs: set = set()
    cleaned_favs: List[Dict[str, Any]] = []
    for entry in raw_favs:
        if isinstance(entry, str):
            slug = entry.strip()
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            cleaned_favs.append({"slug": slug})
        elif isinstance(entry, dict):
            slug = str(entry.get("slug") or "").strip()
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            obj: Dict[str, Any] = {"slug": slug}
            for k in _ALLOWED_FAV_KEYS:
                if k == "slug":
                    continue
                v = entry.get(k)
                if v is None:
                    continue
                # Coerce numbers and strings; drop anything weirder.
                if isinstance(v, (str, int, float, bool)):
                    obj[k] = v
            cleaned_favs.append(obj)
        # silently skip anything else
        if len(cleaned_favs) >= 50:
            break
    sheet["favorite_beasts"] = cleaned_favs

    # Defenses — four free-form string lists. Each entry is treated as a
    # display label; the chip-toggle UI compares case-insensitively
    # against a predefined "standard" set to decide chip styling, but
    # everything goes into the same list. Coerce non-strings, strip
    # whitespace, dedupe case-insensitively (preserving first-seen
    # casing), and cap at 20 entries per list so the picker stays readable.
    for _defense_key in ("damage_resistances", "damage_immunities",
                         "damage_vulnerabilities", "condition_immunities"):
        raw = sheet.get(_defense_key)
        if not isinstance(raw, list):
            raw = []
        seen_lower: set = set()
        cleaned: List[str] = []
        for entry in raw:
            if not isinstance(entry, str):
                continue
            s = entry.strip()
            if not s:
                continue
            lower = s.lower()
            if lower in seen_lower:
                continue
            seen_lower.add(lower)
            cleaned.append(s)
            if len(cleaned) >= 20:
                break
        sheet[_defense_key] = cleaned

    # hp_rolls: {class_slug: [int, int, …]}. Trim each list to the class's
    # current level (so removing a level drops its roll); pad with zeros if
    # we haven't asked the player to backfill yet. Drop entries for classes
    # that aren't on the current roster.
    raw_rolls = sheet.get("hp_rolls")
    if not isinstance(raw_rolls, dict):
        raw_rolls = {}
    cleaned_rolls: Dict[str, List[int]] = {}
    for c in (classes or []):
        cslug = class_slug(c.get("class") or "")
        if not cslug:
            continue
        try:
            lv = max(1, min(20, int(c.get("level") or 1)))
        except (TypeError, ValueError):
            lv = 1
        existing = raw_rolls.get(cslug) or []
        if not isinstance(existing, list):
            existing = []
        coerced: List[int] = []
        for v in existing[:lv]:
            try:
                coerced.append(max(0, int(v)))
            except (TypeError, ValueError):
                coerced.append(0)
        # Pad with zeros for levels that haven't been entered yet
        while len(coerced) < lv:
            coerced.append(0)
        cleaned_rolls[cslug] = coerced
    # Preserve any historical entries for classes not on the current
    # roster only if they look sensible — most likely they were dropped
    # intentionally. Easier path: drop them. Players can re-enter if
    # they re-add a class.
    sheet["hp_rolls"] = cleaned_rolls

    # Normalize the trackable-resources list. Items must be dicts with at
    # least {key, name, max, current}. Missing fields default sensibly.
    raw_res = sheet.get("resources")
    if not isinstance(raw_res, list):
        raw_res = []
    cleaned_res: List[Dict[str, Any]] = []
    seen_keys: set = set()
    for r in raw_res:
        if not isinstance(r, dict):
            continue
        key = str(r.get("key") or "").strip()
        name = str(r.get("name") or "").strip()
        if not key or not name or key in seen_keys:
            continue
        seen_keys.add(key)
        try:
            mx = max(0, int(r.get("max") or 0))
        except (TypeError, ValueError):
            mx = 0
        try:
            cur = int(r.get("current") if r.get("current") is not None else mx)
        except (TypeError, ValueError):
            cur = mx
        cur = max(0, min(cur, mx)) if mx > 0 else max(0, cur)
        reset = str(r.get("reset") or "long").strip().lower()
        if reset not in ("short", "long", "none"):
            reset = "long"
        cleaned_res.append({
            "key": key,
            "name": name,
            "current": cur,
            "max": mx,
            "reset": reset,
            "source": str(r.get("source") or "").strip(),
            "class_slug": str(r.get("class_slug") or "").strip().lower(),
            "subclass_slug": str(r.get("subclass_slug") or "").strip().lower(),
            "desc": str(r.get("desc") or "").strip(),
            "manual": bool(r.get("manual")),
        })
    sheet["resources"] = cleaned_res

    return sheet


def class_levels_summary(sheet: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return ``classes`` ordered by level descending — used by templates
    to render the combined "Druid 5 / Wizard 3" badge."""
    classes = sheet.get("classes") or []
    return sorted(
        [c for c in classes if isinstance(c, dict) and c.get("class")],
        key=lambda c: -int(c.get("level") or 0),
    )
