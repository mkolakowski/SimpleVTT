"""Curated lair-action data for the SRD legendary monster roster.

Lair actions (RAW MM p.11 / the per-monster "Lair Actions" sidebar) fire
on initiative count 20 (losing ties) once per round while a creature is in
its lair. They are NOT part of the structured `actions` array on the
shipped monster JSON — the SRD content build doesn't carry a "Lair
Actions" block — so they're hand-authored here and folded into the
projected sheet by `_monster_dict_to_sheet` (keyed by monster slug),
mirroring the `legendary_resistance_per_day` derivation.

Shape of one lair action (the dict the projection puts on
`sheet["lair_actions"]`):

    {
        "id": "magma-erupts",        # stable kebab-case id (button data-attr)
        "name": "Magma Erupts",      # display label
        "desc": "...",               # short RAW summary (rephrased)
        "save_ability": "DEX",       # "" for no-save lair actions
        "save_dc": 15,               # 0 when save_ability is ""
        "damage": "6d6",             # "" for non-damage effects
        "damage_type": "fire",       # "" when no damage
        "half_on_save": True,        # damage halved on a successful save
        "effect": "",                # condition key applied on a failed save
                                     #   (e.g. "prone") for non-damage actions
        "area": {"shape": "sphere", "size_ft": 20},
    }

Design (see docs/plans/legendary-actions.md, Phase 3a): top-level array
on the sheet rather than `category: "lair_action"` in the unified
`actions` list — the initiative-20 scheduler reads this array directly
and no other read site wants lair actions surfaced.

Red dragons (every age) share the same volcanic lair (RAW: lair actions
are tied to the LAIR, not the creature's age), so the adult and ancient
red dragon map to the identical action set. Other chromatic/metallic
lairs (white = ice, black = swamp, etc.) + the Lich / Kraken are filed
as a follow-up backfill — this v1 ships the demo's Adult Red Dragon
fixture (and its ancient counterpart) fully and correctly rather than
hand-authoring 15 monsters' worth of data at risk of RAW errors.
"""
from __future__ import annotations

import copy

# RAW MM — Red Dragon, "Lair Actions" (volcanic lair). On initiative
# count 20 the dragon takes one of these; it can't use the same one two
# rounds in a row (that once-per-round-no-repeat nuance is a GM call in
# v1, not enforced by the engine).
_RED_DRAGON_VOLCANIC_LAIR: list[dict] = [
    {
        "id": "magma-erupts",
        "name": "Magma Erupts",
        "desc": ("Magma erupts from a point the dragon can see within "
                 "120 ft., a 20-ft-radius burst. Each creature in the "
                 "area makes a DC 15 Dexterity save, taking 21 (6d6) fire "
                 "damage on a fail, or half on a success."),
        "save_ability": "DEX",
        "save_dc": 15,
        "damage": "6d6",
        "damage_type": "fire",
        "half_on_save": True,
        "effect": "",
        "area": {"shape": "sphere", "size_ft": 20},
    },
    {
        "id": "tremor",
        "name": "Tremor",
        "desc": ("A tremor shakes the lair in a 60-ft radius around the "
                 "dragon. Each creature other than the dragon on the "
                 "ground there must succeed on a DC 15 Dexterity save or "
                 "be knocked prone."),
        "save_ability": "DEX",
        "save_dc": 15,
        "damage": "",
        "damage_type": "",
        "half_on_save": False,
        "effect": "prone",
        "area": {"shape": "sphere", "size_ft": 60},
    },
    {
        "id": "volcanic-gases",
        "name": "Volcanic Gases",
        "desc": ("Volcanic gases form a 20-ft-radius sphere centered on a "
                 "point the dragon can see within 120 ft. Each creature in "
                 "the gas must succeed on a DC 13 Constitution save or be "
                 "poisoned until the end of its next turn."),
        "save_ability": "CON",
        "save_dc": 13,
        "damage": "",
        "damage_type": "",
        "half_on_save": False,
        "effect": "poisoned",
        "area": {"shape": "sphere", "size_ft": 20},
    },
]

# Keyed by monster slug (the `slug` field on the shipped SRD monster
# JSON). Red dragons of every age share the volcanic lair.
LAIR_ACTIONS_BY_SLUG: dict[str, list[dict]] = {
    "adult-red-dragon": _RED_DRAGON_VOLCANIC_LAIR,
    "ancient-red-dragon": _RED_DRAGON_VOLCANIC_LAIR,
}


def lair_actions_for_slug(slug) -> list[dict]:
    """Return a deep copy of the curated lair actions for a monster slug,
    or an empty list when the slug has no authored lair (which is most
    monsters — only a handful of SRD legendary creatures have a lair).

    The copy is deep so a caller that mutates the returned dicts (e.g.
    the projection overlaying `save_dc` from the stat block, or a future
    GM override) can't corrupt the module-level source list.
    """
    if not slug or not isinstance(slug, str):
        return []
    actions = LAIR_ACTIONS_BY_SLUG.get(slug.strip().lower())
    if not actions:
        return []
    return copy.deepcopy(actions)


def lair_action_by_id(slug, action_id) -> dict | None:
    """Resolve a single lair action by slug + action id. Returns a deep
    copy, or None when either the slug has no lair or the id is unknown.
    Used by the trigger endpoint to look up the picked action."""
    if not action_id or not isinstance(action_id, str):
        return None
    for a in lair_actions_for_slug(slug):
        if str(a.get("id") or "") == action_id.strip():
            return a
    return None
