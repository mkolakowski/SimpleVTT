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

    return sheet


def class_levels_summary(sheet: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return ``classes`` ordered by level descending — used by templates
    to render the combined "Druid 5 / Wizard 3" badge."""
    classes = sheet.get("classes") or []
    return sorted(
        [c for c in classes if isinstance(c, dict) and c.get("class")],
        key=lambda c: -int(c.get("level") or 0),
    )
