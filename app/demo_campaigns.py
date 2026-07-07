"""Leveled sample demo campaigns (demo-rework arc).

The original demo (`app/demo_seed.py`) seeds one campaign — "Demo: The
Sundered Vault" (level ~5). This module adds the OTHER leveled showcase
campaigns (levels 3, 9, 13, 18). Each is a small party (≤6 PCs) whose
members each demonstrate a **class feature gained at that level**, plus
level-appropriate NPC templates and a placeholder battle map. Every PC
carries a `notes` block: a one-line description, a roleplay hook, and how to
play (leaning on the showcase feature).

Token / map **art** is wired by adding an optional ``image`` web-path to the
relevant spec entry — ``map["image"]``, a PC dict's ``"image"``, or a 4th
element on an ``npc_tokens`` tuple ``(slug, label, color, image)``. Absent →
``image_url=None`` (the token renders as a plain coloured ring). Generate the
art from the ready-to-paste prompts at ``/wiki/doc/image-prompts``
(`docs/demo/image-prompts.md`).

Imported **lazily** by `demo_seed.reset_and_reseed` (and `wipe`) to avoid an
import cycle — this module imports `build_dnd5e_sheet` + `_npc_sheet` from
`demo_seed`.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .demo_seed import _npc_sheet, build_dnd5e_sheet
from .image_utils import average_image_color, natural_image_dims
from .models import (
    Campaign,
    CampaignMembership,
    Character,
    Encounter,
    GridType,
    Map,
    Token,
    TokenTemplate,
    User,
)


def _notes(desc: str, roleplay: str, how: str) -> str:
    return f"Description: {desc}\nRoleplay: {roleplay}\nHow to play: {how}"


def _slots(klass: str, **levels: int) -> dict:
    """`_slots("wizard", **{"1": 4, "2": 2})` → the nested spell-slot dict."""
    return {klass: {lvl: {"total": n, "used": 0} for lvl, n in levels.items()}}


def _spell(name: str, level: int, slug: str) -> dict:
    return {"name": name, "level": level, "prepared": True, "_slug": slug,
            "casting_time": "1 action"}


# ── Level 3 — The Goblin Warrens (Tier 1) ───────────────────────────
_GOBLIN_WARRENS = {
    "name": "Demo L3: The Goblin Warrens",
    "level": 3,
    "gm": "gm",
    "gm_color": "#84cc16",
    "members": [("alice", "#6cb4ff"), ("carol", "#f59e0b")],
    "desc": ("Tier-1 starter dungeon (party level 3). A goblin warband has "
             "been raiding the trade road from a warren of tunnels. Each PC "
             "shows off a feature their class gains around level 3. Demo "
             "campaign — resets on a fixed interval."),
    # v2.842.0 — dark warren, explored under dynamic fog.
    # v2.847.0 — gridless: organic, art-matched coords; party at the palisade
    # approach (SW), goblins at the tunnel mouths (NE), Grukk deep in the warren.
    # v2.940.0 — layout replaced from a map-editor JSON export (a full-width wood
    # wall with an open gate + a ring of flickering torch/brazier lights). Coords
    # are authored in the 1400×1000 design space; the loader scales them ×1.06 to
    # the goblin-warrens.png natural size (1484×1060) — same as every other spec.
    "map": {"name": "The Goblin Warrens (entrance)", "width": 1400, "height": 1000,
            "image": "/static/demo/maps/goblin-warrens.png",
            "gridless": True,
            "ambient_light": "dark",
            "weather": "",  # v2.941.1 — no ambient weather on this map
            # v2.942.0 — re-authored from a map-editor export: fog of war OFF
            # (the warren reads as a lit, explored entrance), the gate CLOSED,
            # and a tighter torch ring (hearth 13/53 + seven 3/9-ft wall torches).
            "fog_enabled": False, "fog_dynamic": True,
            "walls": [
                {"id": "w1783385893138_0", "x1": 0.0, "y1": 563.2, "x2": 1408.5, "y2": 576.4, "style": "wood", "doors": [{"id": "d1783385944228_1", "t0": 0.391137, "t1": 0.55392, "open": False, "gate": True}]}],
            "lights": [
                {"id": "l1783385987241_4", "x": 661.3, "y": 887.7, "bright_ft": 13, "dim_ft": 53, "color": "#ffb347", "color2": "#ff7a1a", "type": "custom", "flicker": 0.25},
                {"id": "l1783386072255_6", "x": 927.4, "y": 123.6, "bright_ft": 3, "dim_ft": 9, "color": "#ffb347", "color2": "#ff7a1a", "type": "custom", "flicker": 0.25},
                {"id": "l1783391915985_0", "x": 1125.5, "y": 241.5, "bright_ft": 3, "dim_ft": 9, "color": "#ffb347", "color2": "#ff7a1a", "type": "custom", "flicker": 0.25},
                {"id": "l1783391924461_1", "x": 1189.6, "y": 435.8, "bright_ft": 3, "dim_ft": 9, "color": "#ffb347", "color2": "#ff7a1a", "type": "custom", "flicker": 0.25},
                {"id": "l1783391930671_2", "x": 666.0, "y": 84.9, "bright_ft": 3, "dim_ft": 9, "color": "#ffb347", "color2": "#ff7a1a", "type": "custom", "flicker": 0.25},
                {"id": "l1783391932943_3", "x": 463.2, "y": 82.1, "bright_ft": 3, "dim_ft": 9, "color": "#ffb347", "color2": "#ff7a1a", "type": "custom", "flicker": 0.25},
                {"id": "l1783391935478_4", "x": 333.0, "y": 177.4, "bright_ft": 3, "dim_ft": 9, "color": "#ffb347", "color2": "#ff7a1a", "type": "custom", "flicker": 0.25},
                {"id": "l1783391937406_5", "x": 234.9, "y": 322.6, "bright_ft": 3, "dim_ft": 9, "color": "#ffb347", "color2": "#ff7a1a", "type": "custom", "flicker": 0.25}]},
    # Organic token placement (parallel to "party" / "npc_tokens" below).
    "party_pos": [(196, 742), (287, 803), (358, 715), (233, 641), (415, 795)],
    "npc_pos": [(842, 337), (1013, 268), (925, 472), (1146, 351)],
    "party": [
        {"owner": "gm", "name": "Thorin Battlehammer",
         "image": "/static/demo/tokens/l3-thorin.png", "sheet": dict(
            klass="Fighter", subclass="Champion", race="Mountain Dwarf", level=3,
            abilities={"STR": 16, "DEX": 12, "CON": 16, "INT": 10, "WIS": 12, "CHA": 8},
            ac=18, hp_max=28,
            attacks=[
                {"name": "Warhammer", "attack_bonus": "+5", "damage": "1d8+3",
                 "damage_type": "bludgeoning", "range": "5 ft", "desc": "Versatile (1d10)"},
                {"name": "Handaxe (thrown)", "attack_bonus": "+5", "damage": "1d6+3",
                 "damage_type": "slashing", "range": "20/60 ft"},
            ],
            notes=_notes(
                "Stout dwarven front-liner who fights like a duelist, not a wall.",
                "Gruff, clan-proud, narrates each maneuver like a tavern story.",
                "Level-3 showcase: Battle Master — 4 superiority dice (d8). Trip "
                "Attack to knock a goblin prone (melee allies get advantage), "
                "Riposte when one misses you, Menacing Attack to frighten the boss."),
        )},
        {"owner": "alice", "name": "Nyx Shadowstep",
         "image": "/static/demo/tokens/l3-nyx.png", "sheet": dict(
            klass="Rogue", subclass="Thief", race="Wood Elf", level=3,
            abilities={"STR": 10, "DEX": 17, "CON": 14, "INT": 12, "WIS": 13, "CHA": 10},
            ac=15, hp_max=24,
            attacks=[
                {"name": "Rapier", "attack_bonus": "+5", "damage": "1d8+3",
                 "damage_type": "piercing", "range": "5 ft", "desc": "Finesse"},
                {"name": "Shortbow", "attack_bonus": "+5", "damage": "1d6+3",
                 "damage_type": "piercing", "range": "80/320 ft"},
            ],
            notes=_notes(
                "Silent wood-elf scout who opens fights from the dark.",
                "Speaks rarely; lets the first strike do the talking.",
                "Level-3 showcase: Assassinate — advantage vs. anything that "
                "hasn't acted yet, and an automatic crit vs. a surprised target. "
                "Open from stealth: Sneak Attack 2d6 + crit doubling = a huge "
                "first-round burst."),
        )},
        {"owner": "carol", "name": "Sister Elsbeth",
         "image": "/static/demo/tokens/l3-elsbeth.png", "sheet": dict(
            klass="Cleric", subclass="Life Domain", race="Human", level=3,
            abilities={"STR": 12, "DEX": 10, "CON": 14, "INT": 10, "WIS": 16, "CHA": 13},
            ac=18, hp_max=24,
            attacks=[
                {"name": "Mace", "attack_bonus": "+3", "damage": "1d6+1",
                 "damage_type": "bludgeoning", "range": "5 ft"},
            ],
            spells=[
                _spell("Sacred Flame", 0, "sacred-flame"),
                _spell("Light", 0, "light"),
                _spell("Cure Wounds", 1, "cure-wounds"),
                _spell("Guiding Bolt", 1, "guiding-bolt"),
                _spell("Scorching Ray", 2, "scorching-ray"),
                _spell("Spiritual Weapon", 2, "spiritual-weapon"),
            ],
            spell_slots=_slots("cleric", **{"1": 4, "2": 2}),
            notes=_notes(
                "Radiant battle-priest who burns away the dark of the warren.",
                "Warm but unyielding; treats every goblin as a soul to judge.",
                "Level-3 showcase: Channel Divinity — Radiance of the Dawn "
                "(AoE radiant that ignores cover) plus her first 2nd-level "
                "slots (Scorching Ray, Spiritual Weapon)."),
        )},
        {"owner": "gm", "name": "Aldric the Sudden",
         "image": "/static/demo/tokens/l3-aldric.png", "sheet": dict(
            klass="Wizard", subclass="School of Evocation", race="Forest Gnome", level=3,
            abilities={"STR": 8, "DEX": 14, "CON": 13, "INT": 16, "WIS": 11, "CHA": 10},
            ac=12, hp_max=17,
            attacks=[
                {"name": "Dagger", "attack_bonus": "+4", "damage": "1d4+2",
                 "damage_type": "piercing", "range": "20/60 ft", "desc": "Finesse"},
            ],
            spells=[
                _spell("Fire Bolt", 0, "fire-bolt"),
                _spell("Mage Hand", 0, "mage-hand"),
                _spell("Magic Missile", 1, "magic-missile"),
                _spell("Burning Hands", 1, "burning-hands"),
                _spell("Scorching Ray", 2, "scorching-ray"),
                _spell("Shatter", 2, "shatter"),
            ],
            spell_slots=_slots("wizard", **{"1": 4, "2": 2}),
            notes=_notes(
                "Twitchy gnome evoker who blasts first and apologizes never.",
                "Counts seconds aloud before a fireball; oddly precise.",
                "Level-3 showcase: Sculpt Spells — carve allies out of his own "
                "Burning Hands / Shatter so he can blast into melee safely."),
        )},
        {"owner": "gm", "name": "Brisa Quickarrow",
         "image": "/static/demo/tokens/l3-brisa.png", "sheet": dict(
            klass="Ranger", subclass="Hunter", race="Lightfoot Halfling", level=3,
            abilities={"STR": 10, "DEX": 17, "CON": 14, "INT": 11, "WIS": 14, "CHA": 10},
            ac=15, hp_max=25,
            attacks=[
                {"name": "Longbow", "attack_bonus": "+7", "damage": "1d8+3",
                 "damage_type": "piercing", "range": "150/600 ft",
                 "desc": "Archery fighting style (+2 to hit baked in)"},
                {"name": "Shortsword", "attack_bonus": "+5", "damage": "1d6+3",
                 "damage_type": "piercing", "range": "5 ft", "desc": "Finesse"},
            ],
            spells=[
                _spell("Hunter's Mark", 1, "hunters-mark"),
                _spell("Cure Wounds", 1, "cure-wounds"),
            ],
            spell_slots=_slots("ranger", **{"1": 3}),
            notes=_notes(
                "Halfling archer who never misses the same goblin twice.",
                "Cheerful, keeps a tally of kills carved into her quiver.",
                "Level-3 showcase: Hunter's Prey — Colossus Slayer adds 1d6 "
                "to one hit per turn against any creature below max HP. Pair "
                "with Hunter's Mark for steady single-target damage."),
        )},
    ],
    "npcs": [
        ("goblin", "Goblin"),
        ("wolf", "Wolf"),
        ("bandit", "Bandit"),
        ("bandit-captain", "Goblin Warlord (Bandit Captain)"),
    ],
    "npc_tokens": [
        ("goblin", "Goblin Skirmisher", "#7c9c54", "/static/demo/tokens/l3-goblin-skirmisher.png"),
        ("goblin", "Goblin Sneak", "#7c9c54", "/static/demo/tokens/l3-goblin-sneak.png"),
        ("wolf", "Warg", "#8a6d3b", "/static/demo/tokens/l3-warg.png"),
        ("bandit-captain", "Grukk the Warlord", "#c84a4a", "/static/demo/tokens/l3-grukk.png"),
    ],
}


# ── Level 9 — Storm Over Saltmarsh (Tier 2→3), the second GM's game ──
_STORM_SALTMARSH = {
    "name": "Demo L9: Storm Over Saltmarsh",
    "level": 9,
    "gm": "gm2",
    "gm_color": "#38bdf8",
    "members": [("bob", "#a78bfa"), ("dave", "#f472b6"), ("erin", "#34d399")],
    "desc": ("Tier-2/3 coastal adventure (party level 9), run by the demo's "
             "second GM. Sahuagin raiders boil up from a storm-wracked reef. "
             "Each PC shows off a feature gained around level 9 — most "
             "notably full casters' first 5th-level spells. Demo campaign — "
             "resets on a fixed interval."),
    # v2.840.0 — open-water showcase: water + difficult (kelp) terrain regions,
    # public text labels, and a hotspot marking the sunken wreck.
    # v2.842.0 — storm-darkened daylight (dim ambient) with swaying lanterns and
    # rolling sea-fog over the reef.
    # v2.847.0 — gridless: party on the western reef plates, sahuagin circling
    # the central wreck, the shark prowling the deep channel, the elemental in
    # the surf; lanterns hang off the listing hull.
    "map": {"name": "The Drowned Reef", "width": 1600, "height": 1100,
            "image": "/static/demo/maps/drowned-reef.png",
            "gridless": True,
            "ambient_light": "dim",
            "lights": [
                {"id": "dr-l1", "x": 716, "y": 478, "bright_ft": 20, "dim_ft": 40,
                 "color": "#fde68a", "color2": "#ffb347", "type": "lantern"},
                {"id": "dr-l2", "x": 1178, "y": 337, "bright_ft": 15, "dim_ft": 30,
                 "color": "#fde68a", "color2": "#ffb347", "type": "lantern"}],
            "fog_enabled": True, "fog_dynamic": True,
            "fog_revealed": [{"x": 59, "y": 214, "w": 1483, "h": 660}],
            "terrain": [
                {"id": "dr-t1", "x": 127, "y": 781, "w": 1352, "h": 204, "type": "water"},
                # v2.848.0 — the kelp forest is a free-form quad (four corner
                # points; the sanitizer recomputes x/y/w/h as its bbox) so the
                # demo shows off gridless four-corner terrain.
                {"id": "dr-t2", "type": "difficult",
                 "points": [[1004, 213], [1341, 259], [1296, 588], [963, 512]]}],
            "labels": [
                {"id": "dr-lb1", "x": 218, "y": 851, "text": "Deep channel",
                 "size": 32, "color": "#bae6fd"},
                {"id": "dr-lb2", "x": 1063, "y": 273, "text": "Kelp forest",
                 "size": 28, "color": "#86efac"}],
            "hotspots": [
                {"id": "dr-h1", "x": 712, "y": 496, "label": "Sunken wreck",
                 "description": "A shattered hull. A DC 15 Investigation turns up a waterlogged chest."}]},
    # Organic token placement (parallel to "party" / "npc_tokens" below).
    "party_pos": [(312, 447), (416, 521), (247, 563), (383, 356), (491, 462)],
    "npc_pos": [(807, 533), (923, 411), (1101, 823), (688, 662)],
    "party": [
        {"owner": "dave", "name": "Vaelith Stormscale",
         "image": "/static/demo/tokens/l9-vaelith.png", "sheet": dict(
            klass="Sorcerer", subclass="Draconic Bloodline", race="Tiefling", level=9,
            abilities={"STR": 8, "DEX": 14, "CON": 16, "INT": 11, "WIS": 12, "CHA": 18},
            ac=14, hp_max=66,
            attacks=[
                {"name": "Dagger", "attack_bonus": "+6", "damage": "1d4+2",
                 "damage_type": "piercing", "range": "20/60 ft", "desc": "Finesse"},
            ],
            spells=[
                _spell("Fire Bolt", 0, "fire-bolt"),
                _spell("Frostbite", 0, "frostbite"),
                _spell("Chromatic Orb", 1, "chromatic-orb"),
                _spell("Scorching Ray", 2, "scorching-ray"),
                _spell("Fireball", 3, "fireball"),
                _spell("Ice Storm", 4, "ice-storm"),
                _spell("Cone of Cold", 5, "cone-of-cold"),
            ],
            spell_slots=_slots("sorcerer", **{"1": 4, "2": 3, "3": 3, "4": 3, "5": 1}),
            notes=_notes(
                "Storm-born tiefling sorcerer with frost in her blood.",
                "Imperious, treats the reef's storm as a rival rather than weather.",
                "Level-9 showcase: her first 5th-level slot → Cone of Cold (8d8 "
                "cold, 60-ft cone). Soften clusters with Fireball, finish with "
                "the cone; 9 Sorcery Points for Quicken/Twin."),
        )},
        {"owner": "bob", "name": "Lirael Songhaven",
         "image": "/static/demo/tokens/l9-lirael.png", "sheet": dict(
            klass="Bard", subclass="College of Lore", race="Half-Elf", level=9,
            abilities={"STR": 8, "DEX": 14, "CON": 14, "INT": 12, "WIS": 10, "CHA": 18},
            ac=15, hp_max=58,
            attacks=[
                {"name": "Rapier", "attack_bonus": "+6", "damage": "1d8+2",
                 "damage_type": "piercing", "range": "5 ft", "desc": "Finesse"},
                {"name": "Hand Crossbow", "attack_bonus": "+6", "damage": "1d6+2",
                 "damage_type": "piercing", "range": "30/120 ft"},
            ],
            spells=[
                _spell("Vicious Mockery", 0, "vicious-mockery"),
                _spell("Healing Word", 1, "healing-word"),
                _spell("Hold Person", 2, "hold-person"),
                _spell("Hypnotic Pattern", 3, "hypnotic-pattern"),
                _spell("Dimension Door", 4, "dimension-door"),
                _spell("Hold Monster", 5, "hold-monster"),
            ],
            spell_slots=_slots("bard", **{"1": 4, "2": 3, "3": 3, "4": 3, "5": 1}),
            notes=_notes(
                "Silver-tongued lore bard cataloguing the reef's drowned songs.",
                "Never stops narrating; weaponizes a good rumor.",
                "Level-9 showcase: first 5th-level slot → Hold Monster (lock "
                "down a sahuagin baron) + Countercharm vs. siren-song. "
                "Bardic Inspiration d8 keeps the front line swinging."),
        )},
        {"owner": "erin", "name": "Oakheart Mossbrook",
         "image": "/static/demo/tokens/l9-oakheart.png", "sheet": dict(
            klass="Druid", subclass="Circle of the Moon", race="Firbolg", level=9,
            abilities={"STR": 12, "DEX": 13, "CON": 16, "INT": 10, "WIS": 18, "CHA": 11},
            ac=15, hp_max=70,
            attacks=[
                {"name": "Scimitar", "attack_bonus": "+5", "damage": "1d6+1",
                 "damage_type": "slashing", "range": "5 ft"},
            ],
            spells=[
                _spell("Produce Flame", 0, "produce-flame"),
                _spell("Healing Word", 1, "healing-word"),
                _spell("Moonbeam", 2, "moonbeam"),
                _spell("Call Lightning", 3, "call-lightning"),
                _spell("Ice Storm", 4, "ice-storm"),
                _spell("Conjure Elemental", 5, "conjure-elemental"),
            ],
            spell_slots=_slots("druid", **{"1": 4, "2": 3, "3": 3, "4": 3, "5": 1}),
            notes=_notes(
                "Towering firbolg moon-druid who becomes the storm's beasts.",
                "Speaks for the reef's wildlife; slow to anger, terrifying once roused.",
                "Level-9 showcase: first 5th-level slot → Conjure Elemental "
                "(summon a water elemental ally) and high-CR Wild Shape brawling "
                "with Moonbeam up for sustained area control."),
        )},
        {"owner": "gm2", "name": "Ser Kadvan Tideward",
         "image": "/static/demo/tokens/l9-kadvan.png", "sheet": dict(
            klass="Paladin", subclass="Oath of Devotion", race="Human", level=9,
            abilities={"STR": 18, "DEX": 10, "CON": 14, "INT": 10, "WIS": 12, "CHA": 16},
            ac=20, hp_max=84,
            attacks=[
                {"name": "Longsword", "attack_bonus": "+8", "damage": "1d8+4",
                 "damage_type": "slashing", "range": "5 ft",
                 "desc": "Versatile (1d10); Extra Attack — 2 swings"},
                {"name": "Javelin (thrown)", "attack_bonus": "+8", "damage": "1d6+4",
                 "damage_type": "piercing", "range": "30/120 ft"},
            ],
            spells=[
                _spell("Bless", 1, "bless"),
                _spell("Hunter's Mark", 1, "hunters-mark"),
                _spell("Misty Step", 2, "misty-step"),
                _spell("Haste", 3, "haste"),
            ],
            spell_slots=_slots("paladin", **{"1": 4, "2": 3, "3": 2}),
            notes=_notes(
                "Grim oath-bound knight hunting the reef's raider-lord.",
                "Quiet, relentless; marks one foe and does not stop.",
                "Level-9 showcase: Aura of Courage (allies within 10 ft can't be "
                "frightened) + 3rd-level slots for Divine Smite bursts and "
                "Vow of Enmity advantage. Two attacks, then smite the hit."),
        )},
        {"owner": "gm2", "name": "Brother Tym",
         "image": "/static/demo/tokens/l9-tym.png", "sheet": dict(
            klass="Monk", subclass="Way of the Open Hand", race="Wood Elf", level=9,
            abilities={"STR": 12, "DEX": 18, "CON": 14, "INT": 10, "WIS": 16, "CHA": 9},
            ac=17, hp_max=63,
            attacks=[
                {"name": "Unarmed Strike", "attack_bonus": "+7", "damage": "1d6+4",
                 "damage_type": "bludgeoning", "range": "5 ft",
                 "desc": "Martial Arts; Extra Attack + Flurry of Blows (Ki)"},
                {"name": "Shortspear", "attack_bonus": "+7", "damage": "1d6+4",
                 "damage_type": "piercing", "range": "5 ft"},
            ],
            notes=_notes(
                "Water-genasi monk who runs across the waves to the fight.",
                "Calm to the point of eerie; speaks in tide metaphors.",
                "Level-9 showcase: Unarmored Movement now lets him run up "
                "vertical surfaces and across liquid without falling (move 55 ft "
                "over water), plus Stillness of Mind. 9 Ki: Flurry + Stunning Strike."),
        )},
    ],
    "npcs": [
        ("sahuagin", "Sahuagin"),
        ("reef-shark", "Reef Shark"),
        ("water-elemental", "Water Elemental"),
        ("young-red-dragon", "Storm Drake (Young Dragon)", "dragon"),
    ],
    "npc_tokens": [
        ("sahuagin", "Sahuagin Raider", "#0e7490", "/static/demo/tokens/l9-sahuagin-raider.png"),
        ("sahuagin", "Sahuagin Priestess", "#155e75", "/static/demo/tokens/l9-sahuagin-priestess.png"),
        ("reef-shark", "Reef Shark", "#475569", "/static/demo/tokens/l9-reef-shark.png"),
        ("water-elemental", "Tide Elemental", "#0891b2", "/static/demo/tokens/l9-tide-elemental.png"),
    ],
}


# ── Level 13 — The Shadowfell Spire (Tier 3) ────────────────────────
_SHADOWFELL_SPIRE = {
    "name": "Demo L13: The Shadowfell Spire",
    "level": 13,
    "gm": "gm",
    "gm_color": "#a855f7",
    "members": [("bob", "#818cf8"), ("dave", "#f472b6")],
    "desc": ("Tier-3 dark-fantasy siege (party level 13). A spire of black "
             "glass bleeds the Shadowfell into the world; undead and worse "
             "spill out. Each PC shows off a feature gained around level 13 — "
             "full casters' first 7th-level spells, and tier-3 martial power. "
             "Demo campaign — resets on a fixed interval."),
    # v2.840.0 — dark-tower showcase: ambient dark with coloured brazier lights,
    # fog of war (revealed generously over the play area so the live view stays
    # visible), and a GM-only pin.
    # v2.847.0 — gridless: party entering across the southern plaza, wraith +
    # spawn drifting among the shadow-rifts mid-plaza, the illithid at the
    # spire's base off the top edge; braziers moved onto the rift line. The
    # fog reveal now covers the party's southern approach (the rift field
    # stays unexplored until scouted).
    "map": {"name": "The Shadowfell Spire (threshold)", "width": 1600, "height": 1200,
            "image": "/static/demo/maps/shadowfell-spire.png",
            "gridless": True,
            "ambient_light": "dark",
            "lights": [
                {"id": "ss-l1", "x": 338, "y": 362, "bright_ft": 20, "dim_ft": 40,
                 "color": "#a855f7", "color2": "#6d28d9", "type": "torch"},
                {"id": "ss-l2", "x": 1263, "y": 341, "bright_ft": 20, "dim_ft": 40,
                 "color": "#a855f7", "color2": "#6d28d9", "type": "torch"},
                {"id": "ss-l3", "x": 786, "y": 713, "bright_ft": 15, "dim_ft": 30,
                 "color": "#38bdf8", "color2": "#22d3ee", "type": "candle"},
                {"id": "ss-l4", "x": 808, "y": 337, "bright_ft": 25, "dim_ft": 50,
                 "color": "#22d3ee", "color2": "#22d3ee", "type": "daylight"}],
            "fog_enabled": True, "fog_dynamic": True,
            "fog_revealed": [{"x": 56, "y": 580, "w": 1488, "h": 560}],
            "gm_pins": [
                {"id": "ss-p1", "x": 773, "y": 881, "label": "Shadow gate",
                 "note": "The rift opens on round 3; a shadow demon steps through."}]},
    # Organic token placement (parallel to "party" / "npc_tokens" below).
    "party_pos": [(591, 917), (703, 986), (817, 924), (688, 843), (943, 968)],
    "npc_pos": [(517, 428), (688, 337), (912, 391), (793, 216)],
    "party": [
        {"owner": "bob", "name": "Maelen Farsight",
         "image": "/static/demo/tokens/l13-maelen.png", "sheet": dict(
            klass="Wizard", subclass="School of Evocation", race="High Elf", level=13,
            abilities={"STR": 8, "DEX": 14, "CON": 14, "INT": 20, "WIS": 12, "CHA": 10},
            ac=12, hp_max=84,
            attacks=[
                {"name": "Quarterstaff", "attack_bonus": "+5", "damage": "1d6+1",
                 "damage_type": "bludgeoning", "range": "5 ft", "desc": "Versatile (1d8)"},
            ],
            spells=[
                _spell("Fire Bolt", 0, "fire-bolt"),
                _spell("Shield", 1, "shield"),
                _spell("Misty Step", 2, "misty-step"),
                _spell("Counterspell", 3, "counterspell"),
                _spell("Banishment", 4, "banishment"),
                _spell("Wall of Force", 5, "wall-of-force"),
                _spell("Chain Lightning", 6, "chain-lightning"),
                _spell("Forcecage", 7, "forcecage"),
            ],
            spell_slots=_slots("wizard", **{"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1}),
            notes=_notes(
                "Ice-calm elf diviner who has already seen how the fight ends.",
                "Speaks in certainties; unnerving because he's usually right.",
                "Level-13 showcase: his first 7th-level slot → Forcecage (trap "
                "the spire's lich). Portent: two foretold d20s replace any roll "
                "(turn the boss's save into a 1)."),
        )},
        {"owner": "dave", "name": "Cassius Emberbinder",
         "image": "/static/demo/tokens/l13-cassius.png", "sheet": dict(
            klass="Warlock", subclass="The Fiend", race="Tiefling", level=13,
            abilities={"STR": 8, "DEX": 14, "CON": 16, "INT": 11, "WIS": 12, "CHA": 20},
            ac=15, hp_max=94,
            attacks=[
                {"name": "Eldritch Blast", "attack_bonus": "+10", "damage": "1d10+5",
                 "damage_type": "force", "range": "120 ft",
                 "desc": "Cantrip — 3 beams at level 13; Agonizing Blast (+CHA each)"},
            ],
            spells=[
                _spell("Eldritch Blast", 0, "eldritch-blast"),
                _spell("Hex", 1, "hex"),
                _spell("Hunger of Hadar", 3, "hunger-of-hadar"),
                _spell("Banishment", 4, "banishment"),
                _spell("Scrying", 5, "scrying"),
                _spell("Circle of Death", 6, "circle-of-death"),
                _spell("Finger of Death", 7, "finger-of-death"),
            ],
            spell_slots=_slots("warlock", **{"5": 3}),
            notes=_notes(
                "Charismatic tiefling warlock paying a fiend's tab one soul at a time.",
                "Glib, makes terrible deals sound reasonable.",
                "Level-13 showcase: Mystic Arcanum — a free 6th- AND 7th-level "
                "spell once per long rest (Circle of Death, Finger of Death) on "
                "top of three level-5 pact slots. Spam Eldritch Blast (3 beams) "
                "between Arcanum nukes."),
        )},
        {"owner": "gm", "name": "High Cleric Doran",
         "image": "/static/demo/tokens/l13-doran.png", "sheet": dict(
            klass="Cleric", subclass="Life Domain", race="Goliath", level=13,
            abilities={"STR": 16, "DEX": 10, "CON": 15, "INT": 10, "WIS": 20, "CHA": 12},
            ac=19, hp_max=97,
            attacks=[
                {"name": "Maul", "attack_bonus": "+9", "damage": "2d6+3",
                 "damage_type": "bludgeoning", "range": "5 ft",
                 "desc": "Divine Strike adds 2d8 radiant 1/turn"},
            ],
            spells=[
                _spell("Sacred Flame", 0, "sacred-flame"),
                _spell("Healing Word", 1, "healing-word"),
                _spell("Spiritual Weapon", 2, "spiritual-weapon"),
                _spell("Spirit Guardians", 3, "spirit-guardians"),
                _spell("Guardian of Faith", 4, "guardian-of-faith"),
                _spell("Flame Strike", 5, "flame-strike"),
                _spell("Heal", 6, "heal"),
                _spell("Divine Word", 7, "divine-word"),
            ],
            spell_slots=_slots("cleric", **{"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1}),
            notes=_notes(
                "Mountainous goliath war-priest who answers the spire with light.",
                "Booming, fearless; treats retreat as heresy.",
                "Level-13 showcase: first 7th-level slot → Divine Word (banish/"
                "stun the undead host). War Priest bonus attacks + Divine Strike "
                "(+2d8 radiant) make his Maul hit like a siege ram."),
        )},
        {"owner": "gm", "name": "Hruld Skullcleaver",
         "image": "/static/demo/tokens/l13-hruld.png", "sheet": dict(
            klass="Barbarian", subclass="Path of the Berserker", race="Half-Orc", level=13,
            abilities={"STR": 20, "DEX": 14, "CON": 18, "INT": 8, "WIS": 12, "CHA": 8},
            ac=17, hp_max=140,
            attacks=[
                {"name": "Greataxe", "attack_bonus": "+9", "damage": "1d12+5",
                 "damage_type": "slashing", "range": "5 ft",
                 "desc": "Rage +3 damage; Brutal Critical +2 dice on a crit"},
                {"name": "Javelin (thrown)", "attack_bonus": "+9", "damage": "1d6+5",
                 "damage_type": "piercing", "range": "30/120 ft"},
            ],
            notes=_notes(
                "Half-orc totem barbarian who simply will not fall down.",
                "Few words; laughs when he's bloodied.",
                "Level-13 showcase: Brutal Critical (2) — a crit rolls THREE "
                "extra weapon dice. Bear Totem halves nearly all damage while "
                "raging; Relentless Rage keeps him at 1 HP instead of dropping."),
        )},
        {"owner": "gm", "name": "Wisp Underbough",
         "image": "/static/demo/tokens/l13-wisp.png", "sheet": dict(
            klass="Rogue", subclass="Thief", race="Forest Gnome", level=13,
            abilities={"STR": 8, "DEX": 20, "CON": 14, "INT": 16, "WIS": 12, "CHA": 10},
            ac=16, hp_max=82,
            attacks=[
                {"name": "Rapier +1", "attack_bonus": "+10", "damage": "1d8+6",
                 "damage_type": "piercing", "range": "5 ft",
                 "desc": "Finesse; Sneak Attack 7d6"},
                {"name": "Hand Crossbow", "attack_bonus": "+9", "damage": "1d6+5",
                 "damage_type": "piercing", "range": "30/120 ft"},
            ],
            spells=[
                _spell("Mage Hand", 0, "mage-hand"),
                _spell("Minor Illusion", 0, "minor-illusion"),
                _spell("Charm Person", 1, "charm-person"),
                _spell("Mirror Image", 2, "mirror-image"),
                _spell("Hypnotic Pattern", 3, "hypnotic-pattern"),
            ],
            spell_slots=_slots("rogue", **{"1": 4, "2": 3, "3": 2}),
            notes=_notes(
                "Gnome arcane trickster who fights dirty with a spellbook.",
                "Impish, never where you last saw her.",
                "Level-13 showcase: Magical Ambush — when she casts a spell from "
                "hiding, the target has disadvantage on the save. Open with a "
                "near-guaranteed Hypnotic Pattern, then Sneak Attack 7d6."),
        )},
    ],
    "npcs": [
        ("wraith", "Wraith"),
        ("vampire-spawn", "Vampire Spawn"),
        ("mind-flayer", "Mind Flayer"),
        ("specter", "Specter"),
    ],
    "npc_tokens": [
        ("wraith", "Spire Wraith", "#6d28d9", "/static/demo/tokens/l13-spire-wraith.png"),
        ("vampire-spawn", "Vampire Spawn", "#7f1d1d", "/static/demo/tokens/l13-vampire-spawn.png"),
        ("vampire-spawn", "Vampire Spawn", "#7f1d1d", "/static/demo/tokens/l13-vampire-spawn.png"),
        ("mind-flayer", "Illithid Adept", "#581c87", "/static/demo/tokens/l13-illithid-adept.png"),
    ],
}


# ── Level 18 — The Dragon's Apotheosis (Tier 4 capstone) ────────────
_DRAGONS_APOTHEOSIS = {
    "name": "Demo L18: The Dragon's Apotheosis",
    "level": 18,
    "gm": "gm",
    "gm_color": "#ef4444",
    "members": [("carol", "#fbbf24"), ("erin", "#34d399")],
    "desc": ("Tier-4 capstone (party level 18). An ancient red wyrm is "
             "ascending to godhood atop a volcano; the party has one shot to "
             "stop it. Each PC shows off a high-tier feature — full casters' "
             "9th-level spells and martial capstones. Demo campaign — resets "
             "on a fixed interval."),
    # v2.840.0 — volcano showcase: lava terrain regions, fiery glow lights.
    # v2.856.0 — captured from a live editor session: the lava is now three
    # free-form polygons (⬡ Free polygon tool) forming branching molten flows
    # across the caldera floor, lit by a single custom ember glow in dark
    # ambient (labels/hotspot cleared in the editor). Coords are as drawn — a
    # couple of vertices spill past the map edge into the letterbox, which the
    # tabletop clips.
    # v2.859.0 — authored in the image's NATURAL space (2400×1792): the terrain
    # + light were drawn live in the editor (which works in natural pixels), so
    # this spec's design space IS natural → the seed's rescale is a no-op here.
    "map": {"name": "The Caldera Throne", "width": 2400, "height": 1792,
            "image": "/static/demo/maps/caldera-throne.png",
            "gridless": True,
            "ambient_light": "dark",
            "lights": [
                {"id": "ct-l1", "x": 1200, "y": 767, "bright_ft": 20, "dim_ft": 40,
                 "color": "#fb923c", "color2": "#fde047", "type": "custom"}],
            "terrain": [
                {"id": "ct-t1", "type": "lava",
                 "points": [[953, 492], [1429, 483], [1717, 766], [2368, 712], [1587, 62], [526, 101]]},
                {"id": "ct-t2", "type": "lava",
                 "points": [[963, 496], [672, 784], [815, 1087], [442, 1571], [28, 1017], [110, 503], [533, 93]]},
                {"id": "ct-t3", "type": "lava",
                 "points": [[805, 1084], [1189, 1205], [1586, 1091], [1730, 764], [2366, 708],
                            [2339, 1157], [2127, 1420], [1820, 1609], [1472, 1726], [1011, 1760], [428, 1567]]}]},
    # Token positions in natural space (2400×1792), matching the terrain above.
    "party_pos": [(416, 1063), (555, 1139), (329, 1017), (489, 954), (655, 1093)],
    "npc_pos": [(1155, 844), (895, 969), (1459, 948), (1537, 684)],
    "party": [
        {"owner": "gm", "name": "Archmagus Selene",
         "image": "/static/demo/tokens/l18-selene.png", "sheet": dict(
            klass="Wizard", subclass="School of Evocation", race="High Elf", level=18,
            abilities={"STR": 8, "DEX": 14, "CON": 16, "INT": 20, "WIS": 12, "CHA": 11},
            ac=15, hp_max=122,
            attacks=[
                {"name": "Fire Bolt", "attack_bonus": "+11", "damage": "4d10",
                 "damage_type": "fire", "range": "120 ft", "desc": "Cantrip (level 17+: 4d10)"},
            ],
            spells=[
                _spell("Fire Bolt", 0, "fire-bolt"),
                _spell("Shield", 1, "shield"),
                _spell("Counterspell", 3, "counterspell"),
                _spell("Wall of Force", 5, "wall-of-force"),
                _spell("Chain Lightning", 6, "chain-lightning"),
                _spell("Delayed Blast Fireball", 7, "delayed-blast-fireball"),
                _spell("Sunburst", 8, "sunburst"),
                _spell("Meteor Swarm", 9, "meteor-swarm"),
                _spell("Wish", 9, "wish"),
            ],
            spell_slots=_slots("wizard", **{"1": 4, "2": 3, "3": 3, "4": 3, "5": 3, "6": 1, "7": 1, "8": 1, "9": 1}),
            notes=_notes(
                "Elven archmage who has prepared for this fight for a century.",
                "Detached, speaks of the wyrm the way one discusses weather.",
                "Level-18 showcase: a 9th-level slot → Meteor Swarm (40d6 across "
                "four 40-ft spheres). Overchannel max-damages a low-level evocation; "
                "Spell Mastery casts Shield / Misty Step at will."),
        )},
        {"owner": "gm", "name": "Ignar Flamesoul",
         "image": "/static/demo/tokens/l18-ignar.png", "sheet": dict(
            klass="Sorcerer", subclass="Draconic Bloodline", race="Dragonborn", level=18,
            abilities={"STR": 10, "DEX": 14, "CON": 18, "INT": 11, "WIS": 12, "CHA": 20},
            ac=15, hp_max=131,
            attacks=[
                {"name": "Fire Bolt", "attack_bonus": "+11", "damage": "4d10",
                 "damage_type": "fire", "range": "120 ft", "desc": "Cantrip (4d10 at 17+)"},
            ],
            spells=[
                _spell("Fire Bolt", 0, "fire-bolt"),
                _spell("Fireball", 3, "fireball"),
                _spell("Wall of Fire", 4, "wall-of-fire"),
                _spell("Cone of Cold", 5, "cone-of-cold"),
                _spell("Disintegrate", 6, "disintegrate"),
                _spell("Delayed Blast Fireball", 7, "delayed-blast-fireball"),
                _spell("Power Word Stun", 8, "power-word-stun"),
                _spell("Time Stop", 9, "time-stop"),
                _spell("Power Word Kill", 9, "power-word-kill"),
            ],
            spell_slots=_slots("sorcerer", **{"1": 4, "2": 3, "3": 3, "4": 3, "5": 3, "6": 1, "7": 1, "8": 1, "9": 1}),
            notes=_notes(
                "Dragonborn sorcerer who answers a dragon-god with dragon-fire.",
                "Proud, theatrical; treats the duel as a family reunion.",
                "Level-18 showcase: Draconic Presence — a 60-ft aura of awe/fear "
                "(CHA save) — plus a 9th-level slot for Time Stop → stacked nukes. "
                "20 Sorcery Points fuel Quicken + Twin."),
        )},
        {"owner": "carol", "name": "Dame Aurelia Dawnward",
         "image": "/static/demo/tokens/l18-aurelia.png", "sheet": dict(
            klass="Paladin", subclass="Oath of Devotion", race="Aasimar", level=18,
            abilities={"STR": 20, "DEX": 10, "CON": 16, "INT": 10, "WIS": 12, "CHA": 18},
            ac=21, hp_max=164,
            attacks=[
                {"name": "Holy Avenger Longsword", "attack_bonus": "+11", "damage": "1d8+5",
                 "damage_type": "slashing", "range": "5 ft",
                 "desc": "Extra Attack (2 swings); +2d10 radiant vs. fiends/undead"},
                {"name": "Javelin (thrown)", "attack_bonus": "+11", "damage": "1d6+5",
                 "damage_type": "piercing", "range": "30/120 ft"},
            ],
            spells=[
                _spell("Bless", 1, "bless"),
                _spell("Lesser Restoration", 2, "lesser-restoration"),
                _spell("Crusader's Mantle", 3, "crusaders-mantle"),
                _spell("Banishing Smite", 5, "banishing-smite"),
            ],
            spell_slots=_slots("paladin", **{"1": 4, "2": 3, "3": 3, "4": 3, "5": 2}),
            notes=_notes(
                "Radiant aasimar paladin and the party's unbreakable anchor.",
                "Serene, certain; her light steadies everyone near her.",
                "Level-18 showcase: her Auras of Protection + Devotion now reach "
                "30 ft — the whole party adds her +4 CHA to every save. Holy Nimbus "
                "(Channel Divinity) burns nearby fiends; Divine Smite on demand."),
        )},
        {"owner": "gm", "name": "Bryn Ironwall",
         "image": "/static/demo/tokens/l18-bryn.png", "sheet": dict(
            klass="Fighter", subclass="Champion", race="Goliath", level=18,
            abilities={"STR": 20, "DEX": 13, "CON": 18, "INT": 9, "WIS": 12, "CHA": 8},
            ac=20, hp_max=184,
            attacks=[
                {"name": "Greatsword", "attack_bonus": "+11", "damage": "2d6+5",
                 "damage_type": "slashing", "range": "5 ft",
                 "desc": "Extra Attack (3) — 3 swings; crit on 18–20 (Superior Critical)"},
                {"name": "Heavy Crossbow", "attack_bonus": "+7", "damage": "1d10+1",
                 "damage_type": "piercing", "range": "100/400 ft"},
            ],
            notes=_notes(
                "Goliath champion who simply outlasts dragons.",
                "Stoic mountain of a man; grins only when outnumbered.",
                "Level-18 showcase: Survivor — regains HP each turn while bloodied, "
                "and Superior Critical crits on 18–20. Three attacks a turn, four "
                "with Action Surge; Indomitable rerolls two failed saves."),
        )},
        {"owner": "erin", "name": "Thornroot Elder",
         "image": "/static/demo/tokens/l18-thornroot.png", "sheet": dict(
            klass="Druid", subclass="Circle of the Moon", race="Firbolg", level=18,
            abilities={"STR": 12, "DEX": 12, "CON": 17, "INT": 10, "WIS": 20, "CHA": 11},
            ac=16, hp_max=140,
            attacks=[
                {"name": "Shillelagh Quarterstaff", "attack_bonus": "+11", "damage": "1d8+5",
                 "damage_type": "bludgeoning", "range": "5 ft", "desc": "Shillelagh (WIS to hit/damage)"},
            ],
            spells=[
                _spell("Produce Flame", 0, "produce-flame"),
                _spell("Healing Word", 1, "healing-word"),
                _spell("Moonbeam", 2, "moonbeam"),
                _spell("Conjure Animals", 3, "conjure-animals"),
                _spell("Ice Storm", 4, "ice-storm"),
                _spell("Conjure Elemental", 5, "conjure-elemental"),
                _spell("Heal", 6, "heal"),
                _spell("Fire Storm", 7, "fire-storm"),
                _spell("Sunburst", 8, "sunburst"),
                _spell("Storm of Vengeance", 9, "storm-of-vengeance"),
            ],
            spell_slots=_slots("druid", **{"1": 4, "2": 3, "3": 3, "4": 3, "5": 3, "6": 1, "7": 1, "8": 1, "9": 1}),
            notes=_notes(
                "Ancient firbolg archdruid speaking for a mountain that hates the wyrm.",
                "Grave, elemental; refers to the volcano by name.",
                "Level-18 showcase: a 9th-level slot → Storm of Vengeance (sky-"
                "wide control), plus Archdruid — unlimited Wild Shape and ignores "
                "verbal/somatic components. Tank as a high-CR beast, control as a caster."),
        )},
    ],
    "npcs": [
        ("adult-red-dragon", "Adult Red Dragon", "dragon"),
        ("fire-giant", "Fire Giant"),
        ("archmage", "Cult Archmage"),
        ("salamander", "Salamander"),
    ],
    "npc_tokens": [
        ("adult-red-dragon", "Pyraxis the Ascendant (Adult Red Dragon)", "#b91c1c", "/static/demo/tokens/l18-pyraxis.png"),
        ("fire-giant", "Fire Giant Honor Guard", "#ea580c", "/static/demo/tokens/l18-fire-giant.png"),
        ("fire-giant", "Fire Giant Honor Guard", "#ea580c", "/static/demo/tokens/l18-fire-giant.png"),
        ("archmage", "Cult Archmage", "#7c3aed", "/static/demo/tokens/l18-cult-archmage.png"),
    ],
}


# Registry — appended to as each leveled campaign lands (D3–D6).
# ── Level 5 — The Tide-Wracked Catacombs (Tier 2) — the remade L5 ─────
# v2.605.0 — the fresh Level-5 demo. The original hand-built L5 ("Demo:
# The Sundered Vault", app/demo_seed.py) is kept as the harness anchor
# (id=1) but seeded **archived**, so this is the active L5 in the leveled
# lineup (L3 / L5 / L9 / L13 / L18). Each PC shows off a feature their
# class gains at level 5 (the Tier-2 power spike).
_TIDEWRACKED_CATACOMBS = {
    "name": "Demo L5: The Tide-Wracked Catacombs",
    "level": 5,
    "gm": "gm",
    "gm_color": "#22d3ee",
    "members": [("alice", "#6cb4ff"), ("carol", "#f59e0b")],
    "desc": ("Tier-2 sample campaign (party level 5) — the power-spike tier. "
             "A drowned crypt beneath a ruined lighthouse spills undead onto "
             "the coast at every high tide. Each PC shows off a feature their "
             "class gains at level 5 (Extra Attack, 3rd-level spells, Uncanny "
             "Dodge). The remade Level-5 demo — the original 'Sundered Vault' "
             "is kept as an archived example. Resets on a fixed interval."),
    # v2.840.0 — flooded-crypt showcase: standing-water terrain, fog of war
    # (revealed generously over the play area), and a lantern light source.
    # v2.842.0 — pitch-dark crypt (dark ambient): only the party's lanterns and
    # a guttering wall torch carve pools of light out of the black.
    # v2.847.0 — gridless: party clustered on the dry central stair, undead
    # wading through the flooded halls below; lanterns hung along the stair.
    "map": {"name": "The Tide-Wracked Catacombs", "width": 1400, "height": 1000,
            "image": "/static/demo/maps/tide-wracked-catacombs.png",
            "gridless": True,
            "ambient_light": "dark",
            "terrain": [
                {"id": "tc-t1", "x": 131, "y": 624, "w": 1138, "h": 221, "type": "water"}],
            "lights": [
                {"id": "tc-l1", "x": 681, "y": 407, "bright_ft": 20, "dim_ft": 40,
                 "color": "#fde68a", "color2": "#ffb347", "type": "lantern"},
                {"id": "tc-l2", "x": 272, "y": 291, "bright_ft": 15, "dim_ft": 30,
                 "color": "#f59e0b", "color2": "#ff7a1a", "type": "torch"},
                {"id": "tc-l3", "x": 1063, "y": 483, "bright_ft": 15, "dim_ft": 30,
                 "color": "#fde68a", "color2": "#ffb347", "type": "lantern"}],
            "fog_enabled": True, "fog_dynamic": True,
            "fog_revealed": [{"x": 63, "y": 217, "w": 1274, "h": 610}]},
    # Organic token placement (parallel to "party" / "npc_tokens" below).
    "party_pos": [(612, 373), (703, 428), (548, 447), (662, 519), (779, 361)],
    "npc_pos": [(338, 682), (517, 736), (871, 704), (1042, 651)],
    "party": [
        {"owner": "gm", "name": "Sir Gareth Tidebreaker",
         "image": "/static/demo/tokens/l5tide-gareth.png", "sheet": dict(
            klass="Fighter", subclass="Champion", race="Human", level=5,
            abilities={"STR": 18, "DEX": 13, "CON": 16, "INT": 9, "WIS": 12, "CHA": 11},
            ac=18, hp_max=44,
            attacks=[
                {"name": "Longsword", "attack_bonus": "+7", "damage": "1d8+4",
                 "damage_type": "slashing", "range": "5 ft",
                 "desc": "Versatile (1d10); two swings (Extra Attack)"},
                {"name": "Javelin (thrown)", "attack_bonus": "+7", "damage": "1d6+4",
                 "damage_type": "piercing", "range": "30/120 ft"},
            ],
            notes=_notes(
                "Storm-cloaked knight who holds the crypt stair against the tide.",
                "Steady and dutiful; calls the line and never breaks it.",
                "Level-5 showcase: Extra Attack — two longsword swings every "
                "Attack action. Champion's Improved Critical crits on 19-20, "
                "doubling that burst."),
        )},
        {"owner": "gm", "name": "Maelis Stormcaller",
         "image": "/static/demo/tokens/l5tide-maelis.png", "sheet": dict(
            klass="Wizard", subclass="School of Evocation", race="High Elf", level=5,
            abilities={"STR": 8, "DEX": 14, "CON": 14, "INT": 18, "WIS": 12, "CHA": 10},
            ac=12, hp_max=27,
            attacks=[
                {"name": "Fire Bolt", "attack_bonus": "+7", "damage": "2d10",
                 "damage_type": "fire", "range": "120 ft",
                 "desc": "Cantrip (scales to 2d10 at level 5)"},
                {"name": "Dagger", "attack_bonus": "+5", "damage": "1d4+2",
                 "damage_type": "piercing", "range": "20/60 ft", "desc": "Finesse"},
            ],
            spells=[
                _spell("Fire Bolt", 0, "fire-bolt"),
                _spell("Mage Hand", 0, "mage-hand"),
                _spell("Magic Missile", 1, "magic-missile"),
                _spell("Burning Hands", 1, "burning-hands"),
                _spell("Scorching Ray", 2, "scorching-ray"),
                _spell("Shatter", 2, "shatter"),
                _spell("Fireball", 3, "fireball"),
                _spell("Fly", 3, "fly"),
            ],
            spell_slots=_slots("wizard", **{"1": 4, "2": 3, "3": 2}),
            notes=_notes(
                "Tempest-touched elf whose first Fireball is the campaign's "
                "fireworks moment.",
                "Theatrical; narrates the blast radius like a stage cue.",
                "Level-5 showcase: 3rd-level slots — Fireball (8d6, 20-ft "
                "radius). Sculpt Spells carves allies out of the blast so he "
                "can drop it into melee."),
        )},
        {"owner": "carol", "name": "Mother Coralind",
         "image": "/static/demo/tokens/l5tide-coralind.png", "sheet": dict(
            klass="Cleric", subclass="Life Domain", race="Half-Elf", level=5,
            abilities={"STR": 12, "DEX": 10, "CON": 14, "INT": 11, "WIS": 17, "CHA": 13},
            ac=18, hp_max=38,
            attacks=[
                {"name": "Warhammer", "attack_bonus": "+4", "damage": "1d8+1",
                 "damage_type": "bludgeoning", "range": "5 ft", "desc": "Versatile (1d10)"},
            ],
            spells=[
                _spell("Sacred Flame", 0, "sacred-flame"),
                _spell("Guidance", 0, "guidance"),
                _spell("Cure Wounds", 1, "cure-wounds"),
                _spell("Guiding Bolt", 1, "guiding-bolt"),
                _spell("Spiritual Weapon", 2, "spiritual-weapon"),
                _spell("Hold Person", 2, "hold-person"),
                _spell("Spirit Guardians", 3, "spirit-guardians"),
                _spell("Revivify", 3, "revivify"),
            ],
            spell_slots=_slots("cleric", **{"1": 4, "2": 3, "3": 2}),
            notes=_notes(
                "Storm-priestess of the drowned coast who walks in a ring of "
                "spectral wrath.",
                "Grave and tidal; speaks in the cadence of breaking waves.",
                "Level-5 showcase: Spirit Guardians — a 15-ft aura of radiant "
                "wrath (3d8, half on save) that shreds the undead swarm as she "
                "advances."),
        )},
        {"owner": "alice", "name": "Vesh Quillon",
         "image": "/static/demo/tokens/l5tide-vesh.png", "sheet": dict(
            klass="Rogue", subclass="Thief", race="Wood Elf", level=5,
            abilities={"STR": 10, "DEX": 18, "CON": 14, "INT": 12, "WIS": 13, "CHA": 10},
            ac=16, hp_max=33,
            attacks=[
                {"name": "Rapier", "attack_bonus": "+7", "damage": "1d8+4",
                 "damage_type": "piercing", "range": "5 ft", "desc": "Finesse; Sneak Attack 3d6"},
                {"name": "Hand Crossbow", "attack_bonus": "+7", "damage": "1d6+4",
                 "damage_type": "piercing", "range": "30/120 ft"},
            ],
            notes=_notes(
                "Marsh-born cutthroat who opens from the dark and survives the reply.",
                "Laconic; counts the exits before the threats.",
                "Level-5 showcase: Uncanny Dodge — a reaction to halve a big "
                "hit (try the v2.600.0 reaction prompt). Sneak Attack is now 3d6."),
        )},
        {"owner": "gm", "name": "Hrudd Saltmane",
         "image": "/static/demo/tokens/l5tide-hrudd.png", "sheet": dict(
            klass="Barbarian", subclass="Path of the Berserker", race="Half-Orc", level=5,
            abilities={"STR": 18, "DEX": 14, "CON": 16, "INT": 8, "WIS": 10, "CHA": 10},
            ac=15, hp_max=52,
            attacks=[
                {"name": "Greataxe", "attack_bonus": "+7", "damage": "1d12+4",
                 "damage_type": "slashing", "range": "5 ft",
                 "desc": "Two swings (Extra Attack); +2 rage damage while raging"},
                {"name": "Handaxe (thrown)", "attack_bonus": "+7", "damage": "1d6+4",
                 "damage_type": "slashing", "range": "20/60 ft"},
            ],
            notes=_notes(
                "Half-orc reaver who wades the flooded halls swinging for two.",
                "Loud, fearless, treats the rising tide as a personal insult.",
                "Level-5 showcase: Extra Attack + Fast Movement (40 ft). "
                "Frenzy gives a bonus-action greataxe swing while raging — "
                "three hits a turn into the undead line."),
        )},
    ],
    "npcs": [
        ("skeleton", "Skeleton"),
        ("zombie", "Zombie"),
        ("ghoul", "Ghoul"),
        ("wight", "Wight"),
    ],
    "npc_tokens": [
        ("skeleton", "Brine Skeleton", "#9ca3af", "/static/demo/tokens/l5tide-brine-skeleton.png"),
        ("zombie", "Drowned Zombie", "#6b7a5a", "/static/demo/tokens/l5tide-drowned-zombie.png"),
        ("ghoul", "Tide Ghoul", "#7c8a8a", "/static/demo/tokens/l5tide-tide-ghoul.png"),
        ("wight", "Captain of the Drowned (Wight)", "#3f6f6f", "/static/demo/tokens/l5tide-drowned-captain.png"),
    ],
}


# v2.853.0 — tweaked one of these maps live in the in-app editor (moved lights,
# redrew walls, reshaped terrain, repositioned tokens)? Snapshot the running DB
# back into these specs with ``scripts/capture_demo_maps.sh`` — it prints the
# paste-ready ``map`` element keys + ``party_pos``/``npc_pos`` for each leveled
# campaign so the change survives the demo reset.
CAMPAIGN_SPECS = [
    _GOBLIN_WARRENS,
    _TIDEWRACKED_CATACOMBS,
    _STORM_SALTMARSH,
    _SHADOWFELL_SPIRE,
    _DRAGONS_APOTHEOSIS,
]


def campaign_names() -> list[str]:
    """Names of the leveled sample campaigns (for the demo wipe-by-name)."""
    return [s["name"] for s in CAMPAIGN_SPECS]


# v2.859.0 — which coordinate fields each element column carries, so the seed
# can rescale them from the spec's authored design space to the map image's
# natural pixel space (see ``_seed_one``). Each entry: (x-fields, y-fields).
_SCALE_FIELDS = {
    "walls": (("x1", "x2"), ("y1", "y2")),
    "lights": (("x",), ("y",)),
    "terrain": (("x", "w"), ("y", "h")),
    "hotspots": (("x",), ("y",)),
    "gm_pins": (("x",), ("y",)),
    "labels": (("x",), ("y",)),
    "fog_revealed": (("x", "w"), ("y", "h")),
}


def _rescale_records(col: str, records: list, sx: float, sy: float) -> list:
    """Scale every coordinate field of a sanitized element list by (sx, sy),
    including terrain ``points`` polygons. Returns the same list (mutated)."""
    if sx == 1.0 and sy == 1.0:
        return records
    xf, yf = _SCALE_FIELDS.get(col, ((), ()))
    for r in records:
        for k in xf:
            if k in r:
                r[k] = round(float(r[k]) * sx, 1)
        for k in yf:
            if k in r:
                r[k] = round(float(r[k]) * sy, 1)
        pts = r.get("points")
        if isinstance(pts, list):
            r["points"] = [[round(p[0] * sx, 1), round(p[1] * sy, 1)] for p in pts]
    return records


def _apply_map_elements(m: Map, mp: dict, sx: float = 1.0, sy: float = 1.0) -> None:
    """v2.840.0 — copy any editor-element lists present on a spec's ``map`` dict
    onto the Map so every demo board ships pre-furnished with the map editor's
    element families (walls/doors, lights, terrain, fog, hotspots, GM pins,
    labels) instead of a blank grid.

    Each list is run through the **same sanitizer the PUT endpoint uses** so the
    stored shape is guaranteed to match what a real editor save produces (default
    keys filled, coords coerced to floats) — a hand-written literal that omitted
    e.g. ``door``/``secret`` would otherwise reach clients missing those keys.

    v2.859.0 — coordinates are then scaled by (sx, sy) from the spec's authored
    design space to the image's natural pixel space, so editor and tabletop
    share one coordinate space regardless of the authored dimensions."""
    # Lazy import to avoid a circular import at module load (tabletop_routes
    # pulls in a large slice of the app).
    from .routes import tabletop_routes as _tr
    _SANITIZERS = {
        "walls": _tr._sanitize_wall_segments,
        "lights": _tr._sanitize_lights,
        "terrain": _tr._sanitize_terrain,
        "hotspots": _tr._sanitize_hotspots,
        "gm_pins": _tr._sanitize_gm_pins,
        "labels": _tr._sanitize_labels,
        "fog_revealed": _tr._sanitize_fog_rects,
    }
    for col, sanitize in _SANITIZERS.items():
        if mp.get(col):
            setattr(m, col, _rescale_records(col, sanitize(mp[col]), sx, sy))
    if mp.get("fog_enabled"):
        m.fog_enabled = True
    if mp.get("fog_dynamic"):
        m.fog_dynamic = True
    if mp.get("ambient_light"):
        m.ambient_light = mp["ambient_light"]


def _seed_one(db: Session, spec: dict, users: dict[str, User]) -> Campaign:
    gm = users[spec["gm"]]
    camp = Campaign(
        name=spec["name"], description=spec["desc"], gm_user_id=gm.id,
        game_system="dnd5e", gm_color=spec.get("gm_color", "#a78bfa"),
        session_active=True, session_started_at=datetime.utcnow(),
        auto_apply_damage=True,
    )
    db.add(camp)
    db.flush()
    for mkey, color in spec.get("members", []):
        db.add(CampaignMembership(
            campaign_id=camp.id, user_id=users[mkey].id, is_gm=False, color=color))
    db.flush()
    mp = spec["map"]
    # Optional ``image`` web-path (e.g. "/static/demo/maps/goblin-warrens.png")
    # on the map dict / party PCs / npc_tokens wires demo art generated from the
    # prompts at /wiki/doc/image-prompts. Absent → None (plain coloured ring).
    # v2.847.0 — the leveled demos are gridless boards: `gridless: True` on a
    # spec's map dict sets grid_type NONE (free token placement, no overlay, no
    # coordinate gutter). ``grid_size_px`` stays 70 regardless — it's the 5-ft
    # scale reference that keeps distance/speed/range math (Euclidean when
    # gridless) and the exploration-fog cell size working.
    gridless = bool(mp.get("gridless"))
    # v2.859.0 — store the map at the image's NATURAL resolution (the invariant
    # the editor + upload flow assume: width_px == the image's real pixel size).
    # The spec authors element/token coords in a "design space" (mp width/height);
    # we scale them to natural by (sx, sy) so the editor and tabletop render in
    # the same coordinate space. Falls back to the authored dims when the image
    # can't be read (e.g. no image).
    design_w = mp.get("width", 1400); design_h = mp.get("height", 1000)
    nat = natural_image_dims(mp.get("image"))
    map_w, map_h = nat if nat else (design_w, design_h)
    sx = map_w / design_w if design_w else 1.0
    sy = map_h / design_h if design_h else 1.0
    m = Map(
        campaign_id=camp.id, name=mp["name"], image_url=mp.get("image"),
        grid_size_px=70, width_px=map_w, height_px=map_h,
        grid_type=GridType.NONE if gridless else GridType.SQUARE,
        show_grid=not gridless,
        # v2.941.1 — ambient weather is seed-declarable ("" none / rain / snow /
        # fog); default "" so a reseed enforces "no weather" (clears any live edit).
        weather=mp.get("weather", ""),
        # v2.733.0 — ship every demo with the "match surround to map" toggle
        # ON: paint the canvas background the map image's average colour.
        letterbox_color=average_image_color(mp.get("image")),
    )
    _apply_map_elements(m, mp, sx, sy)
    db.add(m)
    db.flush()
    camp.active_map_id = m.id
    db.flush()

    chars: list[Character] = []
    for pc in spec["party"]:
        ch = Character(
            campaign_id=camp.id, name=pc["name"], template="dnd5e",
            sheet=build_dnd5e_sheet(pc["name"], **pc["sheet"]),
            owner_user_id=users[pc["owner"]].id,
            # Same 1024×1024 art as the PC's token doubles as the sheet portrait
            # (rendered at 192px on the D&D 5e sheet). Absent → initial-letter fallback.
            portrait_url=pc.get("image"),
        )
        db.add(ch)
        chars.append(ch)
    db.flush()

    tmpls: dict[str, TokenTemplate] = {}
    for npc in spec.get("npcs", []):
        slug, label, ctype = (*npc, "")[:3]
        tt = TokenTemplate(
            campaign_id=camp.id, name=label, template="dnd5e",
            sheet=_npc_sheet(slug, label, creature_type=ctype), tags=["npc", "demo"])
        db.add(tt)
        tmpls[slug] = tt
    db.flush()

    # Token placement. v2.847.0 — gridless maps carry organic, art-matched
    # positions in the spec: ``party_pos`` / ``npc_pos`` are lists of (x, y)
    # parallel to ``party`` / ``npc_tokens`` (index-keyed since NPC labels can
    # repeat). Specs without them fall back to the original row layout (PCs
    # across the top at y=280, NPCs across the bottom at y=630, step 140).
    # v2.859.0 — token positions are authored in the same design space and
    # scaled to natural by (sx, sy), matching the map elements above.
    party_pos = spec.get("party_pos") or []
    npc_pos = spec.get("npc_pos") or []
    enc_tokens: list[Token] = []
    for i, ch in enumerate(chars):
        rx, ry = party_pos[i] if i < len(party_pos) else (140 + i * 140, 280)
        px, py = rx * sx, ry * sy
        tk = Token(
            map_id=m.id, character_id=ch.id, controller_user_id=ch.owner_user_id,
            label=ch.name, color="#6cb4ff", image_url=spec["party"][i].get("image"),
            x=px, y=py, size=1, team="hero")
        db.add(tk)
        enc_tokens.append(tk)
    for i, entry in enumerate(spec.get("npc_tokens", [])):
        # entry is (slug, label, color) or (slug, label, color, image_web_path).
        slug, label, color, *rest = entry
        image = rest[0] if rest else None
        tt = tmpls.get(slug)
        if tt is None:
            continue
        _rx, _ry = npc_pos[i] if i < len(npc_pos) else (140 + i * 140, 630)
        nx, ny = _rx * sx, _ry * sy
        tk = Token(
            map_id=m.id, character_id=None, token_template_id=tt.id,
            label=label, color=color, image_url=image,
            x=nx, y=ny, size=1, team="villain")
        db.add(tk)
        enc_tokens.append(tk)
    db.flush()

    # Seed one ready-to-load encounter per campaign (a snapshot of the
    # placed tokens) so every demo campaign ships with a prepped fight —
    # not just the flagship Sundered Vault.
    scenario = spec["name"].split(":", 1)[-1].strip()
    payload = {
        "tokens": [
            {
                "template_id": t.token_template_id,
                "character_id": t.character_id,
                "controller_user_id": t.controller_user_id,
                "label_override": t.label or "",
                "color_override": t.color or "",
                "image_url": t.image_url,
                "size": int(t.size or 1),
                "x": float(t.x or 0),
                "y": float(t.y or 0),
                "is_hidden": bool(t.is_hidden),
                "team": t.team or "neutral",
            }
            for t in enc_tokens
        ],
        # No pre-rolled initiative — the GM clicks "Start initiative" to
        # roll, same as any fresh fight.
        "battle_state": {
            "combatants": [], "turn_index": 0, "round": 1, "active": False,
        },
    }
    enc = Encounter(
        campaign_id=camp.id,
        name=scenario,
        description=(
            f"{scenario}: the party squares off against the opposition. "
            "Initiative is rolled."
        ),
        map_id=m.id,
        payload=payload,
        tags=["demo", "combat"],
        folder="Demo",
    )
    db.add(enc)
    db.flush()
    camp.default_encounter_id = enc.id
    camp.current_encounter_id = enc.id
    db.flush()
    return camp


def seed_leveled_campaigns(db: Session, users: dict[str, User]) -> list[Campaign]:
    """Seed every leveled sample campaign. Called after the L5 Sundered
    Vault is seeded so it keeps id 1 (CAMPAIGN_ID the harness uses)."""
    return [_seed_one(db, spec, users) for spec in CAMPAIGN_SPECS]
