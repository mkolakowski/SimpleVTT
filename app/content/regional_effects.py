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
p.94, red p.98, white p.101), all five METALLIC dragons (brass p.107,
bronze p.110, copper p.113, gold p.116, silver p.119), plus Lich (p.202)
and Kraken (p.197). Descriptions are rephrased RAW summaries (not
verbatim) citing the source page. Closes the lair-action arc's last
filed follow-up — every SRD legendary lair-bearing creature now carries
authored regional-effect data the engine can read.
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

# RAW MM p.107 — Brass Dragon, "Regional Effects" (desert / canyon region).
# v2.382.0 metallic-dragon backfill.
_BRASS_DRAGON_REGION: list[dict] = [
    {
        "id": "warm-winds",
        "name": "Warm, Dry Winds",
        "desc": ("Warm, dry winds gust through the area within 6 miles of "
                 "the dragon's lair, even at night and out of season."),
    },
    {
        "id": "dust-devils",
        "name": "Whirling Dust Devils",
        "desc": ("Dust devils whirl across the open within 1 mile of the "
                 "lair, kicking up sand and obscuring sightlines."),
    },
    {
        "id": "talking-creatures",
        "name": "Speaking Creatures",
        "desc": ("Beasts and humanoids within 1 mile of the lair may "
                 "briefly speak Draconic — sharing a half-remembered "
                 "phrase or whispered secret — at the dragon's whim."),
    },
]

# RAW MM p.110 — Bronze Dragon, "Regional Effects" (coastal / sea region).
# v2.382.0 metallic-dragon backfill.
_BRONZE_DRAGON_REGION: list[dict] = [
    {
        "id": "sea-mist",
        "name": "Briny Sea Mist",
        "desc": ("Sea mist drifts inland up to 6 miles from the dragon's "
                 "coastal lair, leaving a salty tang in the air."),
    },
    {
        "id": "sudden-storms",
        "name": "Sudden Sea Storms",
        "desc": ("Small thunderheads and brief gales gather without "
                 "warning within 1 mile of the lair, sweeping over the "
                 "waves before dispersing."),
    },
    {
        "id": "kindly-sea-creatures",
        "name": "Friendly Sea Beasts",
        "desc": ("Whales, dolphins, and seabirds within 1 mile of the lair "
                 "act with unusual interest in passersby, often shadowing "
                 "boats or escorting swimmers."),
    },
]

# RAW MM p.113 — Copper Dragon, "Regional Effects" (rocky highland region).
# v2.382.0 metallic-dragon backfill.
_COPPER_DRAGON_REGION: list[dict] = [
    {
        "id": "echoing-laughter",
        "name": "Echoing Laughter",
        "desc": ("Within 6 miles of the dragon's lair, distant peals of "
                 "laughter echo from canyons and cliffs without obvious "
                 "source."),
    },
    {
        "id": "rolling-stones",
        "name": "Rolling Stones",
        "desc": ("Loose stones within 1 mile of the lair occasionally "
                 "tumble downhill without provocation — practical jokes "
                 "the dragon plays on intruders."),
    },
    {
        "id": "trickster-beasts",
        "name": "Trickster Beasts",
        "desc": ("Animals within 1 mile of the lair play harmless tricks "
                 "on passersby — leading travelers astray, hiding their "
                 "supplies, mimicking their voices."),
    },
]

# RAW MM p.116 — Gold Dragon, "Regional Effects" (any region the dragon claims).
# v2.382.0 metallic-dragon backfill.
_GOLD_DRAGON_REGION: list[dict] = [
    {
        "id": "calm-weather",
        "name": "Benign Weather",
        "desc": ("Weather within 6 miles of the dragon's lair is mild and "
                 "fair — storms part, fogs lift, and the land enjoys a "
                 "pleasant calm regardless of the season."),
    },
    {
        "id": "speaking-animals",
        "name": "Speaking Animals",
        "desc": ("Beasts within 1 mile of the lair can briefly speak as if "
                 "by the Speak with Animals spell when the dragon wills, "
                 "sharing news of intruders or guiding travelers."),
    },
    {
        "id": "prophetic-dreams",
        "name": "Prophetic Dreams",
        "desc": ("Intruders sleeping within 1 mile of the lair receive "
                 "vivid dreams in which the dragon appears as a sage — "
                 "glimpses of future consequences or moral counsel."),
    },
]

# RAW MM p.119 — Silver Dragon, "Regional Effects" (mountain region).
# v2.382.0 metallic-dragon backfill.
_SILVER_DRAGON_REGION: list[dict] = [
    {
        "id": "light-snowfall",
        "name": "Gentle Snowfall",
        "desc": ("A light snowfall drifts continuously within 6 miles of "
                 "the dragon's mountain lair, even in midsummer."),
    },
    {
        "id": "cloud-mounts",
        "name": "Cloud Mounts",
        "desc": ("Clouds within 1 mile of the lair condense into rideable "
                 "platforms the dragon — or its guests — can stand upon, "
                 "moving as the dragon wills."),
    },
    {
        "id": "inquisitive-birds",
        "name": "Inquisitive Birds",
        "desc": ("Birds within 1 mile of the lair watch intruders closely "
                 "and relay what they see back to the dragon (Speak with "
                 "Animals at the dragon's will)."),
    },
]

# RAW MM p.202 — Lich, "Regional Effects" (necromantic / phylactery region).
# v2.382.0 non-dragon backfill.
_LICH_REGION: list[dict] = [
    {
        "id": "restless-dead",
        "name": "Restless Dead",
        "desc": ("Corpses within 1 mile of the lich's lair twitch and "
                 "stir of their own accord, occasionally rising as weak "
                 "undead until the lich is destroyed."),
    },
    {
        "id": "unsettling-whispers",
        "name": "Unsettling Whispers",
        "desc": ("Voices echo through halls and tunnels within 6 miles "
                 "of the lair — half-heard phrases in long-dead tongues "
                 "that follow intruders no matter where they turn."),
    },
    {
        "id": "creeping-decay",
        "name": "Creeping Decay",
        "desc": ("Plants wither and animals shun the area within 1 mile "
                 "of the lair. Food spoils faster than nature should "
                 "allow; water turns brackish and stale."),
    },
]

# RAW MM p.197 — Kraken, "Regional Effects" (submerged ocean region).
# v2.382.0 non-dragon backfill.
_KRAKEN_REGION: list[dict] = [
    {
        "id": "abrupt-squalls",
        "name": "Abrupt Squalls",
        "desc": ("Squalls and storms gather without warning within 6 "
                 "miles of the kraken's lair, scattering ships and "
                 "swamping small boats."),
    },
    {
        "id": "treacherous-currents",
        "name": "Treacherous Currents",
        "desc": ("Sea currents within 1 mile of the lair shift "
                 "unpredictably, dragging vessels off course and pulling "
                 "swimmers under without warning."),
    },
    {
        "id": "aggressive-sea-beasts",
        "name": "Aggressive Sea Beasts",
        "desc": ("Sharks, giant octopuses, and other ocean predators "
                 "within 1 mile of the lair behave with unusual "
                 "aggression — answering the kraken's silent call."),
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
    # v2.382.0 metallic-dragon backfill — 5 dragons × 2 ages each.
    "adult-brass-dragon": _BRASS_DRAGON_REGION,
    "ancient-brass-dragon": _BRASS_DRAGON_REGION,
    "adult-bronze-dragon": _BRONZE_DRAGON_REGION,
    "ancient-bronze-dragon": _BRONZE_DRAGON_REGION,
    "adult-copper-dragon": _COPPER_DRAGON_REGION,
    "ancient-copper-dragon": _COPPER_DRAGON_REGION,
    "adult-gold-dragon": _GOLD_DRAGON_REGION,
    "ancient-gold-dragon": _GOLD_DRAGON_REGION,
    "adult-silver-dragon": _SILVER_DRAGON_REGION,
    "ancient-silver-dragon": _SILVER_DRAGON_REGION,
    # v2.382.0 non-dragon backfill — single slug each, no age variants.
    "lich": _LICH_REGION,
    "kraken": _KRAKEN_REGION,
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
