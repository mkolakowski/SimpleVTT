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

Dragons of every age share the same lair-action set per color (RAW: lair
actions are tied to the LAIR, not the creature's age), so the adult and
ancient slugs of each color map to the identical list. RAW MM only gives
lair actions to dragons that occupy a lair (adult and older) — young
dragons and wyrmlings have none, so only the `adult-*` / `ancient-*`
slugs are keyed.

Coverage: all five CHROMATIC dragons (black MM p.88, blue p.91, green
p.94, red p.98, white p.101). Metallic dragons + the Lich / Kraken are a
filed follow-up backfill (they drop into `LAIR_ACTIONS_BY_SLUG` with no
code change). Some RAW lair actions don't map onto the save-or-damage /
condition engine (magical darkness, walls of ice/brush, the white
dragon's ranged ice-shard attack) — those are carried as descriptive
entries (empty `save_ability` + `damage`) so the GM sees the option text
and resolves the geometry manually; the engine simply broadcasts them.
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

# RAW MM p.88 — Black Dragon, "Lair Actions" (swamp lair).
_BLACK_DRAGON_SWAMP_LAIR: list[dict] = [
    {
        "id": "grasping-tide",
        "name": "Grasping Tide",
        "desc": ("A pool of water the dragon can see within 120 ft. surges. "
                 "Each creature within 20 ft. of that pool must succeed on a "
                 "DC 15 Strength save or be pulled up to 20 ft. into the "
                 "water and knocked prone."),
        "save_ability": "STR",
        "save_dc": 15,
        "damage": "",
        "damage_type": "",
        "half_on_save": False,
        "effect": "prone",
        "area": {"shape": "sphere", "size_ft": 20},
    },
    {
        "id": "swarming-insects",
        "name": "Swarming Insects",
        "desc": ("Swarms of insects fill a 20-ft-radius sphere centered on a "
                 "point the dragon can see within 120 ft. Each creature in "
                 "the area makes a DC 15 Constitution save, taking 10 (3d6) "
                 "piercing damage on a fail, or half on a success. The swarm "
                 "lingers as difficult terrain until the dragon acts again."),
        "save_ability": "CON",
        "save_dc": 15,
        "damage": "3d6",
        "damage_type": "piercing",
        "half_on_save": True,
        "effect": "",
        "area": {"shape": "sphere", "size_ft": 20},
    },
    {
        "id": "magical-darkness",
        "name": "Magical Darkness",
        "desc": ("Magical darkness spreads from a point the dragon can see "
                 "within 60 ft., filling a 15-ft-radius sphere until the "
                 "dragon uses this action again or dies. Darkvision can't see "
                 "through it; nonmagical light can't illuminate it. (No save "
                 "— GM places the area.)"),
        "save_ability": "",
        "save_dc": 0,
        "damage": "",
        "damage_type": "",
        "half_on_save": False,
        "effect": "",
        "area": {"shape": "sphere", "size_ft": 15},
    },
]

# RAW MM p.91 — Blue Dragon, "Lair Actions" (desert lair).
_BLUE_DRAGON_DESERT_LAIR: list[dict] = [
    {
        "id": "ceiling-collapse",
        "name": "Ceiling Collapse",
        "desc": ("Part of the ceiling collapses above a creature the dragon "
                 "can see within 120 ft. The target makes a DC 15 Dexterity "
                 "save, taking 10 (3d6) bludgeoning damage on a fail (and is "
                 "knocked prone and buried), or half on a success."),
        "save_ability": "DEX",
        "save_dc": 15,
        "damage": "3d6",
        "damage_type": "bludgeoning",
        "half_on_save": True,
        "effect": "",
        "area": {"shape": "point", "size_ft": 0},
    },
    {
        "id": "sand-cloud",
        "name": "Sand Cloud",
        "desc": ("A cloud of sand swirls in a 20-ft-radius sphere centered on "
                 "a point the dragon can see within 120 ft. Each creature "
                 "there must succeed on a DC 15 Constitution save or be "
                 "blinded for 1 minute (repeat save at end of each turn)."),
        "save_ability": "CON",
        "save_dc": 15,
        "damage": "",
        "damage_type": "",
        "half_on_save": False,
        "effect": "blinded",
        "area": {"shape": "sphere", "size_ft": 20},
    },
    {
        "id": "lightning-arc",
        "name": "Lightning Arc",
        "desc": ("Lightning arcs in a 5-ft-wide line between two solid "
                 "surfaces the dragon can see within 120 ft. Each creature in "
                 "that line makes a DC 15 Dexterity save or takes 10 (3d6) "
                 "lightning damage (no half on a success)."),
        "save_ability": "DEX",
        "save_dc": 15,
        "damage": "3d6",
        "damage_type": "lightning",
        "half_on_save": False,
        "effect": "",
        "area": {"shape": "line", "size_ft": 5},
    },
]

# RAW MM p.94 — Green Dragon, "Lair Actions" (forest lair).
_GREEN_DRAGON_FOREST_LAIR: list[dict] = [
    {
        "id": "grasping-roots",
        "name": "Grasping Roots and Vines",
        "desc": ("Grasping roots and vines erupt in a 20-ft radius around a "
                 "point the dragon can see within 120 ft.; that area becomes "
                 "difficult terrain. Each creature there must succeed on a DC "
                 "15 Strength save or be restrained."),
        "save_ability": "STR",
        "save_dc": 15,
        "damage": "",
        "damage_type": "",
        "half_on_save": False,
        "effect": "restrained",
        "area": {"shape": "sphere", "size_ft": 20},
    },
    {
        "id": "wall-of-tangled-brush",
        "name": "Wall of Tangled Brush",
        "desc": ("A wall of tangled brush up to 60 ft. long, 10 ft. high, and "
                 "5 ft. thick springs up. A creature in the wall's space when "
                 "it appears makes a DC 15 Dexterity save, taking 18 (4d8) "
                 "piercing damage on a fail (and pushed out), or half on a "
                 "success."),
        "save_ability": "DEX",
        "save_dc": 15,
        "damage": "4d8",
        "damage_type": "piercing",
        "half_on_save": True,
        "effect": "",
        "area": {"shape": "wall", "size_ft": 60},
    },
    {
        "id": "magical-fog",
        "name": "Magical Fog",
        "desc": ("The dragon wreathes one creature it can see within 120 ft. "
                 "in beguiling fog. The target must succeed on a DC 15 Wisdom "
                 "save or be charmed by the dragon until initiative count 20 "
                 "on the next round."),
        "save_ability": "WIS",
        "save_dc": 15,
        "damage": "",
        "damage_type": "",
        "half_on_save": False,
        "effect": "charmed",
        "area": {"shape": "single", "size_ft": 0},
    },
]

# RAW MM p.101 — White Dragon, "Lair Actions" (arctic lair).
_WHITE_DRAGON_ARCTIC_LAIR: list[dict] = [
    {
        "id": "freezing-fog",
        "name": "Freezing Fog",
        "desc": ("Freezing fog fills a 20-ft-radius sphere centered on a "
                 "point the dragon can see within 120 ft. Each creature there "
                 "makes a DC 10 Constitution save, taking 10 (3d6) cold "
                 "damage on a fail, or half on a success. The fog is heavily "
                 "obscured and lingers until the dragon acts again."),
        "save_ability": "CON",
        "save_dc": 10,
        "damage": "3d6",
        "damage_type": "cold",
        "half_on_save": True,
        "effect": "",
        "area": {"shape": "sphere", "size_ft": 20},
    },
    {
        "id": "jagged-ice",
        "name": "Jagged Ice Shards",
        "desc": ("The dragon flings jagged ice at up to three creatures it "
                 "can see within 120 ft. Make a ranged attack (+7 to hit) "
                 "against each; a hit deals 10 (3d6) piercing damage. (GM "
                 "rolls the attacks manually — no save.)"),
        "save_ability": "",
        "save_dc": 0,
        "damage": "",
        "damage_type": "",
        "half_on_save": False,
        "effect": "",
        "area": {"shape": "multi", "size_ft": 0},
    },
    {
        "id": "ice-wall",
        "name": "Opaque Wall of Ice",
        "desc": ("A wall of ice up to 30 ft. long, 30 ft. high, and 1 ft. "
                 "thick rises on a solid surface the dragon can see within "
                 "120 ft. Each creature in its space is pushed 5 ft. out. (No "
                 "save — GM places the wall.)"),
        "save_ability": "",
        "save_dc": 0,
        "damage": "",
        "damage_type": "",
        "half_on_save": False,
        "effect": "",
        "area": {"shape": "wall", "size_ft": 30},
    },
]

# Keyed by monster slug (the `slug` field on the shipped SRD monster
# JSON). Dragons of every lair-bearing age (adult + ancient) share their
# color's lair-action set.
LAIR_ACTIONS_BY_SLUG: dict[str, list[dict]] = {
    "adult-black-dragon": _BLACK_DRAGON_SWAMP_LAIR,
    "ancient-black-dragon": _BLACK_DRAGON_SWAMP_LAIR,
    "adult-blue-dragon": _BLUE_DRAGON_DESERT_LAIR,
    "ancient-blue-dragon": _BLUE_DRAGON_DESERT_LAIR,
    "adult-green-dragon": _GREEN_DRAGON_FOREST_LAIR,
    "ancient-green-dragon": _GREEN_DRAGON_FOREST_LAIR,
    "adult-red-dragon": _RED_DRAGON_VOLCANIC_LAIR,
    "ancient-red-dragon": _RED_DRAGON_VOLCANIC_LAIR,
    "adult-white-dragon": _WHITE_DRAGON_ARCTIC_LAIR,
    "ancient-white-dragon": _WHITE_DRAGON_ARCTIC_LAIR,
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
