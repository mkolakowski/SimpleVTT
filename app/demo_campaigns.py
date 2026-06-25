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
from .models import (
    Campaign,
    CampaignMembership,
    Character,
    Encounter,
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
    "map": {"name": "The Goblin Warrens (entrance)", "width": 1400, "height": 1000,
            "image": "/static/demo/maps/goblin-warrens.png"},
    "party": [
        {"owner": "gm", "name": "Thorin Battlehammer", "sheet": dict(
            klass="Fighter", subclass="Battle Master", race="Mountain Dwarf", level=3,
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
        {"owner": "alice", "name": "Nyx Shadowstep", "sheet": dict(
            klass="Rogue", subclass="Assassin", race="Wood Elf", level=3,
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
        {"owner": "carol", "name": "Sister Elsbeth", "sheet": dict(
            klass="Cleric", subclass="Light Domain", race="Human", level=3,
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
        {"owner": "gm", "name": "Aldric the Sudden", "sheet": dict(
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
        {"owner": "gm", "name": "Brisa Quickarrow", "sheet": dict(
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
        ("goblin", "Goblin Skirmisher", "#7c9c54"),
        ("goblin", "Goblin Sneak", "#7c9c54"),
        ("wolf", "Warg", "#8a6d3b"),
        ("bandit-captain", "Grukk the Warlord", "#c84a4a"),
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
    "map": {"name": "The Drowned Reef", "width": 1600, "height": 1100},
    "party": [
        {"owner": "dave", "name": "Vaelith Stormscale", "sheet": dict(
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
        {"owner": "bob", "name": "Lirael Songhaven", "sheet": dict(
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
        {"owner": "erin", "name": "Oakheart Mossbrook", "sheet": dict(
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
        {"owner": "gm2", "name": "Ser Kadvan Tideward", "sheet": dict(
            klass="Paladin", subclass="Oath of Vengeance", race="Human", level=9,
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
        {"owner": "gm2", "name": "Brother Tym", "sheet": dict(
            klass="Monk", subclass="Way of the Open Hand", race="Water Genasi", level=9,
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
        ("sahuagin", "Sahuagin Raider", "#0e7490"),
        ("sahuagin", "Sahuagin Priestess", "#155e75"),
        ("reef-shark", "Reef Shark", "#475569"),
        ("water-elemental", "Tide Elemental", "#0891b2"),
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
    "map": {"name": "The Shadowfell Spire (threshold)", "width": 1600, "height": 1200},
    "party": [
        {"owner": "bob", "name": "Maelen Farsight", "sheet": dict(
            klass="Wizard", subclass="School of Divination", race="High Elf", level=13,
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
        {"owner": "dave", "name": "Cassius Emberbinder", "sheet": dict(
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
        {"owner": "gm", "name": "High Cleric Doran", "sheet": dict(
            klass="Cleric", subclass="War Domain", race="Goliath", level=13,
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
        {"owner": "gm", "name": "Hruld Skullcleaver", "sheet": dict(
            klass="Barbarian", subclass="Path of the Totem Warrior", race="Half-Orc", level=13,
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
        {"owner": "gm", "name": "Wisp Underbough", "sheet": dict(
            klass="Rogue", subclass="Arcane Trickster", race="Forest Gnome", level=13,
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
        ("wraith", "Spire Wraith", "#6d28d9"),
        ("vampire-spawn", "Vampire Spawn", "#7f1d1d"),
        ("vampire-spawn", "Vampire Spawn", "#7f1d1d"),
        ("mind-flayer", "Illithid Adept", "#581c87"),
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
    "map": {"name": "The Caldera Throne", "width": 1800, "height": 1300},
    "party": [
        {"owner": "gm", "name": "Archmagus Selene", "sheet": dict(
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
        {"owner": "gm", "name": "Ignar Flamesoul", "sheet": dict(
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
        {"owner": "carol", "name": "Dame Aurelia Dawnward", "sheet": dict(
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
        {"owner": "gm", "name": "Bryn Ironwall", "sheet": dict(
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
        {"owner": "erin", "name": "Thornroot Elder", "sheet": dict(
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
        ("adult-red-dragon", "Pyraxis the Ascendant (Adult Red Dragon)", "#b91c1c"),
        ("fire-giant", "Fire Giant Honor Guard", "#ea580c"),
        ("fire-giant", "Fire Giant Honor Guard", "#ea580c"),
        ("archmage", "Cult Archmage", "#7c3aed"),
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
    "map": {"name": "The Tide-Wracked Catacombs", "width": 1400, "height": 1000},
    "party": [
        {"owner": "gm", "name": "Sir Gareth Tidebreaker", "sheet": dict(
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
        {"owner": "gm", "name": "Maelis Stormcaller", "sheet": dict(
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
        {"owner": "carol", "name": "Mother Coralind", "sheet": dict(
            klass="Cleric", subclass="Tempest Domain", race="Half-Elf", level=5,
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
        {"owner": "alice", "name": "Vesh Quillon", "sheet": dict(
            klass="Rogue", subclass="Assassin", race="Wood Elf", level=5,
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
        {"owner": "gm", "name": "Hrudd Saltmane", "sheet": dict(
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
        ("skeleton", "Brine Skeleton", "#9ca3af"),
        ("zombie", "Drowned Zombie", "#6b7a5a"),
        ("ghoul", "Tide Ghoul", "#7c8a8a"),
        ("wight", "Captain of the Drowned (Wight)", "#3f6f6f"),
    ],
}


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
    m = Map(
        campaign_id=camp.id, name=mp["name"], image_url=mp.get("image"),
        grid_size_px=70, width_px=mp.get("width", 1400),
        height_px=mp.get("height", 1000), show_grid=True,
    )
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

    # PC tokens across the top, NPC tokens across the bottom. Positions are
    # multiples of the 70 px grid (step 140 = two cells; rows at 4·70 and
    # 9·70) so every token lands squarely on a grid cell.
    enc_tokens: list[Token] = []
    for i, ch in enumerate(chars):
        tk = Token(
            map_id=m.id, character_id=ch.id, controller_user_id=ch.owner_user_id,
            label=ch.name, color="#6cb4ff", image_url=spec["party"][i].get("image"),
            x=140 + i * 140, y=280, size=1, team="hero")
        db.add(tk)
        enc_tokens.append(tk)
    for i, entry in enumerate(spec.get("npc_tokens", [])):
        # entry is (slug, label, color) or (slug, label, color, image_web_path).
        slug, label, color, *rest = entry
        image = rest[0] if rest else None
        tt = tmpls.get(slug)
        if tt is None:
            continue
        tk = Token(
            map_id=m.id, character_id=None, token_template_id=tt.id,
            label=label, color=color, image_url=image,
            x=140 + i * 140, y=630, size=1, team="villain")
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
