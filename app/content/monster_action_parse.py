"""v2.99.469 — pure helper to derive a monster action's structured combat
fields from its SRD-style prose ``desc``.

Leaf module — no FastAPI / SQLAlchemy / hub dependencies — so both the
route layer (`app/routes/tabletop_routes.py`) and the in-process unit
tests (`tests/harness/test_monster_action_desc_parser.py`) import from
here (mirrors `app/content/effective_speed.py`).

Why this exists: the local SRD monster JSONs carry structured
``attack_bonus`` / ``save_dc`` etc. (backfilled in v2.99.465/.466), but
the Open5e API serves action payloads as prose only. Without a parse, a
monster imported live from Open5e re-introduces the data gap that broke
NPC Strike buttons (an attack-roll action with no ``attack_bonus`` falls
through to the legacy ``/roll`` path instead of ``/npc_attack``). Parsing
the desc keeps imported monsters' actions usable.
"""
from __future__ import annotations

import re

_ABILITY_ABBR = {
    "strength": "str", "dexterity": "dex", "constitution": "con",
    "intelligence": "int", "wisdom": "wis", "charisma": "cha",
}

_TO_HIT = re.compile(r"([+-]\d+)\s+to hit", re.IGNORECASE)
_SAVE = re.compile(r"DC\s*(\d+)\s+([A-Za-z]+)\s+sav", re.IGNORECASE)
_DAMAGE = re.compile(
    r"\((\d+d\d+(?:\s*[+-]\s*\d+)?)\)\s+(\w+)\s+damage", re.IGNORECASE)


def parse_monster_action_combat(desc: str | None) -> dict:
    """Return the structured combat fields parseable from an action desc:
    ``attack_roll`` + ``attack_bonus`` (from "+N to hit"), ``save_dc`` +
    ``save_ability`` (from "DC N <ability> saving throw"), and ``damage`` +
    ``damage_type`` (from "(NdM + K) <type> damage"). Only the keys it can
    parse are present; returns ``{}`` when the desc has no combat prose."""
    out: dict = {}
    d = desc or ""
    m = _TO_HIT.search(d)
    if m:
        out["attack_roll"] = True
        out["attack_bonus"] = m.group(1)
    sm = _SAVE.search(d)
    if sm:
        out["save_dc"] = int(sm.group(1))
        ab = _ABILITY_ABBR.get(sm.group(2).lower())
        if ab:
            out["save_ability"] = ab
    dm = _DAMAGE.search(d)
    if dm:
        out["damage"] = dm.group(1).replace(" ", "")
        out["damage_type"] = dm.group(2).lower()
    return out
