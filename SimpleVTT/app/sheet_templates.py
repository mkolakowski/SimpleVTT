"""Character sheet templates.

Each template defines the default JSON structure stored on Character.sheet.
The UI reads these and renders form fields. Keep them simple; users can
extend the JSON with arbitrary keys by editing the sheet.
"""
from __future__ import annotations

from typing import Any, Dict


GENERIC_TEMPLATE: Dict[str, Any] = {
    "summary": "",
    "stats": {},      # free-form key/value pairs
    "notes": "",
    "inventory": [],  # list of strings
}


DND5E_TEMPLATE: Dict[str, Any] = {
    "class": "",
    "level": 1,
    "race": "",
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
    "spells": [],      # [{name, level, description}]
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
