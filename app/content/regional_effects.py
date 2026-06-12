"""Curated regional-effect data for the SRD legendary monster roster.

Regional effects (RAW MM p.11 / each monster's "Regional Effects" sidebar)
are the passive, zone-wide environmental changes that radiate from a
creature's lair while it dwells there — distinct from the initiative-20
"Lair Actions" (see `app/content/lair_actions.py`). They have no save /
damage engine in v1: they're descriptive flavor a GM narrates, so the
shape is intentionally minimal (`id`, `name`, `desc`) rather than the
save/damage/area dict a lair action carries.

Shape of one regional effect (the dict the projection puts on
`sheet["regional_effects"]`):

    {
        "id": "minor-earthquakes",   # stable kebab-case id
        "name": "Minor Earthquakes",  # display label
        "desc": "...",                # short RAW summary (rephrased)
    }

RAW MM p.11: regional effects are tied to the creature occupying its lair
and fade gradually — typically over 1d10 days — once the creature dies or
moves on. That fade is a GM narration call in v1; the engine just surfaces
the effect text on the projected monster sheet (keyed by slug) mirroring
the `lair_actions` derivation.

Like lair actions, regional effects are tied to the LAIR, so a color's
adult and ancient slugs share the same set, and only lair-bearing ages
(adult + older) are keyed — young dragons and wyrmlings have none.

Coverage: all five CHROMATIC dragons (black MM p.88, blue p.91, green
p.94, red p.98, white p.101). Descriptions are rephrased RAW summaries
(not verbatim) citing the source page. Metallic dragons + the Lich /
Kraken are a filed follow-up backfill (they drop into
`REGIONAL_EFFECTS_BY_SLUG` with no code change).
"""
from __future__ import annotations

import copy

# RAW MM p.98 — Red Dragon, "Regional Effects" (volcanic region).
_RED_DRAGON_REGION: list[dict] = [
    {
        "id": "minor-earthquakes",
        "name": "Minor Earthquakes",
        "desc": ("Small earthquakes are common within 6 miles of the "
                 "dragon's lair, rattling structures and unsettling the "
                 "ground."),
    },
    {
        "id": "fouled-water",
        "name": "Warm, Foul Water",
        "desc": ("Water sources within 1 mile of the lair are supernaturally "
                 "warm and tainted by sulfur, fouling their taste."),
    },
    {
        "id": "fire-portals",
        "name": "Fissures to the Plane of Fire",
        "desc": ("Rocky fissures within 1 mile of the lair form portals to "
                 "the Elemental Plane of Fire, letting fire creatures such "
                 "as fire elementals wander into the area."),
    },
]

# RAW MM p.88 — Black Dragon, "Regional Effects" (fetid swamp region).
_BLACK_DRAGON_REGION: list[dict] = [
    {
        "id": "obscuring-fog",
        "name": "Obscuring Fog",
        "desc": ("Fog lightly obscures the land within 6 miles of the "
                 "dragon's lair."),
    },
    {
        "id": "twisted-plants",
        "name": "Twisted Plant Growth",
        "desc": ("Plants within 1 mile of the lair grow twisted and "
                 "thorny, turning the area into difficult terrain."),
    },
    {
        "id": "tainted-water",
        "name": "Tainted Waters",
        "desc": ("Water sources within 1 mile of the lair are supernaturally "
                 "fouled — those who drink from them risk sickness."),
    },
]

# RAW MM p.91 — Blue Dragon, "Regional Effects" (arid desert region).
_BLUE_DRAGON_REGION: list[dict] = [
    {
        "id": "thunderstorms",
        "name": "Frequent Thunderstorms",
        "desc": ("Thunderstorms gather and roll across the land within 6 "
                 "miles of the dragon's lair."),
    },
    {
        "id": "treacherous-sand",
        "name": "Treacherous Sand",
        "desc": ("Sandy regions within 1 mile of the lair are dotted with "
                 "sinkholes that behave like patches of quicksand."),
    },
    {
        "id": "sand-spouts",
        "name": "Whirling Sand Spouts",
        "desc": ("Tiny twisters and sand spouts whirl up within 1 mile of "
                 "the lair, scouring travelers caught in the open."),
    },
]

# RAW MM p.94 — Green Dragon, "Regional Effects" (forest region).
_GREEN_DRAGON_REGION: list[dict] = [
    {
        "id": "labyrinth-thickets",
        "name": "Labyrinthine Thickets",
        "desc": ("Thickets within 1 mile of the lair grow dense and "
                 "shifting, forming a natural maze that intruders must "
                 "navigate as difficult terrain."),
    },
    {
        "id": "cunning-predators",
        "name": "Unnaturally Cunning Predators",
        "desc": ("Predatory plants and animals within 1 mile of the lair "
                 "act with a strange, malevolent cunning, hunting "
                 "intruders on the dragon's behalf."),
    },
    {
        "id": "whispering-glades",
        "name": "Insidious Whispers",
        "desc": ("Within 1 mile of the lair, a creature attuned to the "
                 "forest can hear faint whispers that seed paranoia and "
                 "discord among intruders."),
    },
]

# RAW MM p.101 — White Dragon, "Regional Effects" (frigid arctic region).
_WHITE_DRAGON_REGION: list[dict] = [
    {
        "id": "chill-fog",
        "name": "Chilling Fog",
        "desc": ("Frigid fog lightly obscures the land within 6 miles of "
                 "the dragon's lair."),
    },
    {
        "id": "freezing-precipitation",
        "name": "Freezing Precipitation",
        "desc": ("Icy sleet and snow fall heavily within 1 mile of the "
                 "lair whenever the dragon wills it, glazing the ground."),
    },
    {
        "id": "frozen-sculptures",
        "name": "Frozen Sculptures",
        "desc": ("Creatures slain within 1 mile of the lair are encased in "
                 "ice, becoming grim frozen sculptures that ring the "
                 "dragon's domain."),
    },
]

# Keyed by monster slug (the `slug` field on the shipped SRD monster
# JSON). Dragons of every lair-bearing age (adult + ancient) share their
# color's regional-effect set.
REGIONAL_EFFECTS_BY_SLUG: dict[str, list[dict]] = {
    "adult-black-dragon": _BLACK_DRAGON_REGION,
    "ancient-black-dragon": _BLACK_DRAGON_REGION,
    "adult-blue-dragon": _BLUE_DRAGON_REGION,
    "ancient-blue-dragon": _BLUE_DRAGON_REGION,
    "adult-green-dragon": _GREEN_DRAGON_REGION,
    "ancient-green-dragon": _GREEN_DRAGON_REGION,
    "adult-red-dragon": _RED_DRAGON_REGION,
    "ancient-red-dragon": _RED_DRAGON_REGION,
    "adult-white-dragon": _WHITE_DRAGON_REGION,
    "ancient-white-dragon": _WHITE_DRAGON_REGION,
}


def regional_effects_for_slug(slug) -> list[dict]:
    """Return a deep copy of the curated regional effects for a monster
    slug, or an empty list when the slug has no authored lair region
    (which is most monsters — only a handful of SRD legendary creatures
    radiate regional effects).

    The copy is deep so a caller that mutates the returned dicts can't
    corrupt the module-level source list.
    """
    if not slug or not isinstance(slug, str):
        return []
    effects = REGIONAL_EFFECTS_BY_SLUG.get(slug.strip().lower())
    if not effects:
        return []
    return copy.deepcopy(effects)
