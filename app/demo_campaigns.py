"""Leveled sample demo campaigns (demo-rework arc).

The original demo (`app/demo_seed.py`) seeds one campaign — "Demo: The
Sundered Vault" (level ~5). This module adds the OTHER leveled showcase
campaigns (levels 3, 9, 13, 18). Each is a small party (≤6 PCs) whose
members each demonstrate a **class feature gained at that level**, plus
level-appropriate NPC templates and a placeholder battle map (art is added
later — see the generation prompts in `docs/wiki/demo-content.md`). Every PC
carries a `notes` block: a one-line description, a roleplay hook, and how to
play (leaning on the showcase feature).

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
    "map": {"name": "The Goblin Warrens (entrance)", "width": 1400, "height": 1000},
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


# Registry — appended to as each leveled campaign lands (D3–D6).
CAMPAIGN_SPECS = [
    _GOBLIN_WARRENS,
    _STORM_SALTMARSH,
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
    m = Map(
        campaign_id=camp.id, name=mp["name"], image_url=None,
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

    # PC tokens across the top, NPC tokens across the bottom (placeholder
    # map → positions just need to sit on the grid).
    for i, ch in enumerate(chars):
        db.add(Token(
            map_id=m.id, character_id=ch.id, controller_user_id=ch.owner_user_id,
            label=ch.name, color="#6cb4ff", image_url=None,
            x=140 + i * 105, y=280, size=1, team="hero"))
    for i, (slug, label, color) in enumerate(spec.get("npc_tokens", [])):
        tt = tmpls.get(slug)
        if tt is None:
            continue
        db.add(Token(
            map_id=m.id, character_id=None, token_template_id=tt.id,
            label=label, color=color, image_url=None,
            x=140 + i * 105, y=640, size=1, team="villain"))
    db.flush()
    return camp


def seed_leveled_campaigns(db: Session, users: dict[str, User]) -> list[Campaign]:
    """Seed every leveled sample campaign. Called after the L5 Sundered
    Vault is seeded so it keeps id 1 (CAMPAIGN_ID the harness uses)."""
    return [_seed_one(db, spec, users) for spec in CAMPAIGN_SPECS]
