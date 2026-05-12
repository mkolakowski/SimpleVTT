"""Character preset registry — pre-generated, leveled-up D&D 5e characters
for fast testing.

Each preset has a stable ``key`` (used in form submissions), a display
``label``, a ``description`` shown in the picker, a ``template`` ("dnd5e"
or "generic"), and a ``suggested_name``. The ``build()`` function returns
a fully-populated sheet dict that callers slot into ``Character.sheet``.

Add new presets by appending to the ``PRESETS`` list. Each preset uses
the same helpers (``_dnd5e_base``, ``_add_class``, ``_add_attack``,
``_add_spell``, ``_set_spell_slots``) so the data stays consistent.
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Dict, List

from .sheet_templates import DND5E_TEMPLATE, GENERIC_TEMPLATE, normalize_dnd5e_sheet


# ── Helpers ─────────────────────────────────────────────────────────────

def _mod(score: int) -> int:
    return (int(score) - 10) // 2


def _prof_bonus(level: int) -> int:
    if level >= 17: return 6
    if level >= 13: return 5
    if level >= 9:  return 4
    if level >= 5:  return 3
    return 2


def _dnd5e_base(abilities: Dict[str, int], level: int) -> Dict[str, Any]:
    """Start a D&D 5e sheet shell with abilities + proficiency bonus +
    DEX-derived initiative pre-filled. Caller fills the rest."""
    sheet = copy.deepcopy(DND5E_TEMPLATE)
    sheet["abilities"] = dict(abilities)
    sheet["proficiency_bonus"] = _prof_bonus(level)
    sheet["initiative_bonus"] = _mod(abilities.get("DEX", 10))
    sheet["level"] = level
    return sheet


def _add_class(sheet: Dict[str, Any], cls: str, subclass: str, level: int,
               hit_die: str, armor: str = "", weapons: str = "",
               saves: str = "", skills: str = "",
               spellcasting: str = "", equipment: str = "") -> None:
    entry = {
        "class": cls,
        "subclass": subclass,
        "level": level,
        "class_hit_die": hit_die,
        "class_armor": armor,
        "class_weapons": weapons,
        "class_saving_throws": saves,
        "class_skills": skills,
        "class_spellcasting": spellcasting,
        "class_equipment": equipment,
    }
    sheet["classes"] = [entry]


def _set_hp(sheet: Dict[str, Any], hp_max: int) -> None:
    sheet["hp"] = {"current": hp_max, "max": hp_max, "temp": 0}
    # Hit dice
    sheet["hit_dice"] = {"max": sheet.get("level", 1), "current": sheet.get("level", 1)}


def _set_ac_speed(sheet: Dict[str, Any], ac: int, speed: int = 30) -> None:
    sheet["ac"] = ac
    sheet["base_ac"] = ac
    sheet["speed"] = speed


def _mark_save_prof(sheet: Dict[str, Any], *abilities: str) -> None:
    for ab in abilities:
        if ab in sheet["saving_throws"]:
            sheet["saving_throws"][ab] = True


def _mark_skill_prof(sheet: Dict[str, Any], *skill_names: str,
                     expertise: tuple = ()) -> None:
    for sk in skill_names:
        if sk in sheet["skills"]:
            sheet["skills"][sk]["proficient"] = True
            if sk in expertise:
                sheet["skills"][sk]["expertise"] = True


def _add_attack(sheet: Dict[str, Any], name: str, bonus: str, damage: str,
                damage_type: str = "", range_str: str = "5 ft.",
                desc: str = "") -> None:
    sheet["attacks"].append({
        "name": name,
        "attack_bonus": bonus,
        "damage": damage,
        "damage_type": damage_type,
        "range": range_str,
        "desc": desc,
    })


def _add_spell(sheet: Dict[str, Any], name: str, level: int, school: str,
               class_slug: str, casting_time: str = "1 action",
               range_str: str = "", duration: str = "", components: str = "V, S",
               concentration: bool = False, ritual: bool = False,
               desc: str = "", prepared: bool = True,
               damage: str = "", save_ability: str = "", healing: str = "") -> None:
    sheet["spells"].append({
        "name": name,
        "level": level,
        "school": school,
        "class": class_slug,
        "casting_time": casting_time,
        "range": range_str,
        "duration": duration,
        "components": components,
        "concentration": concentration,
        "ritual": ritual,
        "desc": desc,
        "damage": damage,
        "save_ability": save_ability,
        "healing": healing,
        "prepared": prepared,
    })


def _set_spell_slots(sheet: Dict[str, Any], class_slug: str,
                     slots_by_level: Dict[int, int]) -> None:
    """slots_by_level: {1: 4, 2: 3, 3: 2} sets totals at full availability."""
    per_class: Dict[str, Dict[str, int]] = {}
    for lvl, total in slots_by_level.items():
        per_class[str(lvl)] = {"total": total, "used": 0}
    all_slots = dict(sheet.get("spell_slots") or {})
    all_slots[class_slug] = per_class
    sheet["spell_slots"] = all_slots


# ── Standard array of ability scores, common across presets ─────────────
#
# Generous statline that leaves room for testing without being overpowered.
# Each preset boosts the class's primary stat by +1 via "racial" bonus and
# secondary stat by +1, giving plausible point-buy + race totals.
_STD = {"STR": 14, "DEX": 14, "CON": 14, "INT": 10, "WIS": 10, "CHA": 10}


# ────────────────────────────────────────────────────────────────────────
# D&D 5e Presets
# ────────────────────────────────────────────────────────────────────────

def _preset_dnd5e_blank() -> Dict[str, Any]:
    return copy.deepcopy(DND5E_TEMPLATE)


def _preset_druid_moon_5() -> Dict[str, Any]:
    """Moon Druid Lv5 — Wild Shape into CR 1 beasts, full caster.
    Designed for Wild Shape / Polymorph framework testing."""
    abilities = {"STR": 10, "DEX": 14, "CON": 14, "INT": 10, "WIS": 16, "CHA": 10}
    sheet = _dnd5e_base(abilities, level=5)
    _add_class(
        sheet, "Druid", "Circle of the Moon", 5, "d8",
        armor="Light, medium (non-metal), shields (non-metal)",
        weapons="Clubs, daggers, darts, javelins, maces, quarterstaffs, scimitars, sickles, slings, spears",
        saves="INT, WIS",
        skills="Animal Handling, Nature, Perception, Survival",
        spellcasting="WIS — prepared spells",
        equipment="Wooden shield, scimitar, leather armor, explorer's pack, druidic focus",
    )
    _set_hp(sheet, 33)               # 8 + 4*(5 + 2 CON mod) = 36; rounded down
    _set_ac_speed(sheet, ac=15)      # leather (11) + DEX(+2) + shield (+2)
    _mark_save_prof(sheet, "INT", "WIS")
    _mark_skill_prof(sheet, "Animal Handling", "Nature", "Perception", "Survival")
    sheet["race"] = "Wood Elf"
    sheet["background"] = "Outlander"
    sheet["alignment"] = "Neutral Good"
    sheet["speed"] = 35              # Wood Elf bonus

    # Attacks
    _add_attack(sheet, "Scimitar", "+4", "1d6+2", "slashing",
                desc="Finesse, light")
    _add_attack(sheet, "Quarterstaff", "+2", "1d6", "bludgeoning",
                desc="Versatile (d8 two-handed)")
    _add_attack(sheet, "Shillelagh (Quarterstaff)", "+5", "1d8+3", "bludgeoning",
                desc="Cantrip-buffed, uses WIS for attack & damage")

    # Spells — Druid prepares (level + WIS mod) = 5+3 = 8 spells
    _add_spell(sheet, "Druidcraft", 0, "Transmutation", "druid",
               range_str="30 ft.", duration="Instantaneous",
               desc="Predict weather, make a flower bloom, etc.")
    _add_spell(sheet, "Produce Flame", 0, "Conjuration", "druid",
               range_str="Self", duration="10 min", damage="1d8",
               desc="Flame in your hand, attack to hurl (1d8 fire).")
    _add_spell(sheet, "Shillelagh", 0, "Transmutation", "druid", components="V, S, M",
               casting_time="1 bonus action", range_str="Touch", duration="1 min",
               desc="Imbue a club/quarterstaff; uses WIS for attacks, d8 base damage.")
    _add_spell(sheet, "Cure Wounds", 1, "Evocation", "druid",
               casting_time="1 action", range_str="Touch", duration="Instantaneous",
               healing="1d8+3", desc="Touch heals 1d8 + spellcasting modifier HP.")
    _add_spell(sheet, "Entangle", 1, "Conjuration", "druid", components="V, S",
               range_str="90 ft.", duration="Concentration, up to 1 min",
               concentration=True, save_ability="STR",
               desc="20-foot square of grasping plants; STR save or restrained.")
    _add_spell(sheet, "Faerie Fire", 1, "Evocation", "druid",
               range_str="60 ft.", duration="Concentration, up to 1 min",
               concentration=True, save_ability="DEX",
               desc="Objects/creatures in 20-ft cube glow; advantage to hit them.")
    _add_spell(sheet, "Moonbeam", 2, "Evocation", "druid",
               range_str="120 ft.", duration="Concentration, up to 1 min",
               concentration=True, save_ability="CON", damage="2d10",
               desc="5-ft-radius beam; creatures in/entering it save vs. 2d10 radiant.")
    _add_spell(sheet, "Pass without Trace", 2, "Abjuration", "druid",
               range_str="Self", duration="Concentration, up to 1 hour",
               concentration=True, desc="+10 Stealth & no tracks for allies in 30 ft.")
    _add_spell(sheet, "Conjure Animals", 3, "Conjuration", "druid",
               range_str="60 ft.", duration="Concentration, up to 1 hour",
               concentration=True, desc="Summon fey spirits as beasts (CR 2 / 1 / 1/2 / 1/4).")
    _add_spell(sheet, "Call Lightning", 3, "Conjuration", "druid",
               range_str="120 ft.", duration="Concentration, up to 10 min",
               concentration=True, save_ability="DEX", damage="3d10",
               desc="Storm cloud; bonus action for 3d10 lightning bolt per round.")

    _set_spell_slots(sheet, "druid", {1: 4, 2: 3, 3: 2})

    sheet["inventory"] = ["Scimitar", "Wooden shield", "Leather armor",
                          "Druidic focus (sprig of mistletoe)", "Explorer's pack",
                          "Hunting trap", "Trophy from a defeated animal",
                          "Staff", "50 gp"]
    sheet["notes"] = ("Wild Shape: 2 uses / short rest. Moon Druid Lv 2-5 → max CR 1 beasts. "
                      "Try a Brown Bear or Dire Wolf!\n\n"
                      "Combat Wild Shape (Moon): use a bonus action to transform, "
                      "and spend a spell slot to heal 1d8 per slot level while in beast form.")
    return sheet


def _preset_fighter_battlemaster_5() -> Dict[str, Any]:
    """Battle Master Fighter Lv5 — Action Surge, Second Wind, Superiority Dice (4d8)."""
    abilities = {"STR": 16, "DEX": 14, "CON": 14, "INT": 10, "WIS": 12, "CHA": 8}
    sheet = _dnd5e_base(abilities, level=5)
    _add_class(
        sheet, "Fighter", "Battle Master", 5, "d10",
        armor="All armor, shields",
        weapons="Simple, martial",
        saves="STR, CON",
        skills="Athletics, Intimidation, Perception",
        equipment="Chain mail, shield, longsword, light crossbow + 20 bolts, dungeoneer's pack",
    )
    _set_hp(sheet, 44)               # 10 + 4*(6 + 2 CON) = 42-44
    _set_ac_speed(sheet, ac=18)      # chain mail (16) + shield (+2)
    _mark_save_prof(sheet, "STR", "CON")
    _mark_skill_prof(sheet, "Athletics", "Intimidation", "Perception")
    sheet["race"] = "Mountain Dwarf"
    sheet["background"] = "Soldier"
    sheet["alignment"] = "Lawful Good"

    # Extra Attack at level 5 — both attacks land in one Action
    _add_attack(sheet, "Longsword (1H)", "+6", "1d8+3", "slashing",
                desc="Versatile (d10 two-handed). Extra Attack: hit twice per Attack action.")
    _add_attack(sheet, "Longsword (2H)", "+6", "1d10+3", "slashing",
                desc="Both hands. Extra Attack still applies.")
    _add_attack(sheet, "Light Crossbow", "+5", "1d8+2", "piercing",
                range_str="80/320 ft.", desc="Loading, two-handed.")

    sheet["inventory"] = ["Longsword", "Shield", "Chain mail", "Light crossbow",
                          "20 crossbow bolts", "Dungeoneer's pack",
                          "Trophy from a fallen enemy", "Gambling set",
                          "10 gp"]
    sheet["notes"] = ("Battle Master maneuvers: Riposte, Trip Attack, Disarming Attack, "
                      "Menacing Attack (pick three at Lv 3, +2 at Lv 7).\n\n"
                      "Superiority Dice: 4d8 / short rest. Action Surge: 1 / short rest. "
                      "Second Wind: 1 / short rest (heal 1d10 + Fighter level).")
    return sheet


def _preset_cleric_life_5() -> Dict[str, Any]:
    """Life Domain Cleric Lv5 — Channel Divinity, full caster, heavy armor."""
    abilities = {"STR": 14, "DEX": 10, "CON": 14, "INT": 10, "WIS": 16, "CHA": 12}
    sheet = _dnd5e_base(abilities, level=5)
    _add_class(
        sheet, "Cleric", "Life Domain", 5, "d8",
        armor="Light, medium, heavy, shields",
        weapons="Simple",
        saves="WIS, CHA",
        skills="Insight, Medicine, Religion",
        spellcasting="WIS — prepared spells",
        equipment="Chain mail, shield, mace, light crossbow + 20 bolts, priest's pack, holy symbol",
    )
    _set_hp(sheet, 38)
    _set_ac_speed(sheet, ac=18)      # chain mail (16) + shield (+2) — Life Domain heavy armor
    _mark_save_prof(sheet, "WIS", "CHA")
    _mark_skill_prof(sheet, "Insight", "Medicine", "Religion", "Persuasion")
    sheet["race"] = "Hill Dwarf"
    sheet["background"] = "Acolyte"
    sheet["alignment"] = "Lawful Good"
    sheet["speed"] = 25              # Dwarf

    _add_attack(sheet, "Mace", "+4", "1d6+2", "bludgeoning",
                desc="Standard cleric weapon.")
    _add_attack(sheet, "Light Crossbow", "+2", "1d8", "piercing",
                range_str="80/320 ft.")
    _add_attack(sheet, "Spiritual Weapon (concentration-free)", "+6", "1d8+3", "force",
                range_str="60 ft.",
                desc="Lv 2 spell: bonus action to summon, bonus action to attack each round.")

    # Cleric prepares (level + WIS mod) = 5+3 = 8 spells. Domain spells always prepared.
    # Cantrips
    _add_spell(sheet, "Light", 0, "Evocation", "cleric",
               range_str="Touch", duration="1 hour")
    _add_spell(sheet, "Sacred Flame", 0, "Evocation", "cleric",
               range_str="60 ft.", duration="Instantaneous",
               save_ability="DEX", damage="2d8",
               desc="DEX save or 2d8 radiant (no cover bonus).")
    _add_spell(sheet, "Spare the Dying", 0, "Necromancy", "cleric",
               range_str="Touch", duration="Instantaneous",
               desc="Stabilize a dying creature (0 HP) without a check.")

    # Domain Spells (Life)
    _add_spell(sheet, "Bless", 1, "Enchantment", "cleric",
               range_str="30 ft.", duration="Concentration, up to 1 min",
               concentration=True, components="V, S, M",
               desc="Up to 3 creatures add 1d4 to attacks and saves.")
    _add_spell(sheet, "Cure Wounds", 1, "Evocation", "cleric",
               range_str="Touch", duration="Instantaneous", healing="1d8+3",
               desc="Life Domain: +2 + spell level bonus healing.")
    _add_spell(sheet, "Healing Word", 1, "Evocation", "cleric",
               casting_time="1 bonus action", range_str="60 ft.",
               healing="1d4+3", duration="Instantaneous",
               desc="Ranged heal as a bonus action.")
    _add_spell(sheet, "Lesser Restoration", 2, "Abjuration", "cleric",
               range_str="Touch", duration="Instantaneous",
               desc="End one disease, poisoned, paralyzed, or blinded condition.")
    _add_spell(sheet, "Spiritual Weapon", 2, "Evocation", "cleric",
               casting_time="1 bonus action", range_str="60 ft.",
               duration="1 min", damage="1d8+3",
               desc="Summon a force weapon; bonus action attack each round.")
    _add_spell(sheet, "Beacon of Hope", 3, "Abjuration", "cleric",
               range_str="30 ft.", duration="Concentration, up to 1 min",
               concentration=True,
               desc="Targets have advantage on WIS saves and death saves; max-roll healing.")
    _add_spell(sheet, "Revivify", 3, "Necromancy", "cleric", components="V, S, M",
               casting_time="1 action", range_str="Touch", duration="Instantaneous",
               desc="Return a creature dead < 1 min to 1 HP (300 gp diamond consumed).")

    _set_spell_slots(sheet, "cleric", {1: 4, 2: 3, 3: 2})

    sheet["inventory"] = ["Mace", "Chain mail", "Shield", "Light crossbow",
                          "20 crossbow bolts", "Priest's pack", "Holy symbol (amulet)",
                          "Prayer book", "5 sticks of incense", "Vestments", "25 gp"]
    sheet["notes"] = ("Channel Divinity: 2 / short rest (Turn Undead, Preserve Life). "
                      "Preserve Life: heal up to 5×Cleric level = 25 HP, distributed.\n\n"
                      "Disciple of Life: when you cast a 1st-level+ spell that restores HP, "
                      "target regains 2 + spell level extra HP.")
    return sheet


def _preset_wizard_evocation_5() -> Dict[str, Any]:
    """Evocation Wizard Lv5 — Sculpt Spells, blasty cantrips, Fireball-ready."""
    abilities = {"STR": 8, "DEX": 14, "CON": 14, "INT": 16, "WIS": 12, "CHA": 10}
    sheet = _dnd5e_base(abilities, level=5)
    _add_class(
        sheet, "Wizard", "School of Evocation", 5, "d6",
        armor="—",
        weapons="Daggers, darts, slings, quarterstaffs, light crossbows",
        saves="INT, WIS",
        skills="Arcana, History, Investigation, Insight",
        spellcasting="INT — prepared spells from spellbook",
        equipment="Quarterstaff, spellbook, scholar's pack, arcane focus (crystal)",
    )
    _set_hp(sheet, 28)
    _set_ac_speed(sheet, ac=12)      # unarmored, DEX+2
    _mark_save_prof(sheet, "INT", "WIS")
    _mark_skill_prof(sheet, "Arcana", "History", "Investigation", "Insight")
    sheet["race"] = "High Elf"
    sheet["background"] = "Sage"
    sheet["alignment"] = "Neutral Good"

    _add_attack(sheet, "Quarterstaff", "+1", "1d6-1", "bludgeoning",
                desc="Versatile (d8). Backup when out of spells.")
    _add_attack(sheet, "Dagger", "+5", "1d4+2", "piercing",
                range_str="20/60 ft.", desc="Finesse, thrown.")

    # Cantrips (3 + 1 from High Elf = 4 known)
    _add_spell(sheet, "Fire Bolt", 0, "Evocation", "wizard",
               range_str="120 ft.", damage="2d10",
               desc="Ranged spell attack, 2d10 fire (scales at lv 5).")
    _add_spell(sheet, "Mage Hand", 0, "Conjuration", "wizard",
               range_str="30 ft.", duration="1 min",
               desc="Spectral hand manipulates objects up to 10 lb.")
    _add_spell(sheet, "Prestidigitation", 0, "Transmutation", "wizard",
               range_str="10 ft.", duration="1 hour",
               desc="Minor magical effect: light a fire, clean an object, etc.")
    _add_spell(sheet, "Ray of Frost", 0, "Evocation", "wizard",
               range_str="60 ft.", damage="2d8",
               desc="Spell attack, 2d8 cold + speed reduced by 10 ft.")

    # Prepared spells (INT mod + level = 3+5 = 8)
    _add_spell(sheet, "Magic Missile", 1, "Evocation", "wizard",
               range_str="120 ft.", damage="3d4+3",
               desc="Three darts of force, each auto-hits for 1d4+1 (3 darts at lv 1).")
    _add_spell(sheet, "Mage Armor", 1, "Abjuration", "wizard",
               range_str="Touch", duration="8 hours", components="V, S, M",
               desc="Target's base AC becomes 13 + DEX mod (no armor).")
    _add_spell(sheet, "Shield", 1, "Abjuration", "wizard",
               casting_time="1 reaction", range_str="Self", duration="1 round",
               desc="Reaction to being hit: +5 AC until your next turn.")
    _add_spell(sheet, "Misty Step", 2, "Conjuration", "wizard",
               casting_time="1 bonus action", range_str="Self", duration="Instantaneous",
               desc="Teleport up to 30 ft. to an unoccupied space you can see.")
    _add_spell(sheet, "Scorching Ray", 2, "Evocation", "wizard",
               range_str="120 ft.", damage="6d6",
               desc="Three rays of fire, 2d6 each. Sculpt Spells: choose allies to take no damage.")
    _add_spell(sheet, "Web", 2, "Conjuration", "wizard",
               range_str="60 ft.", duration="Concentration, up to 1 hour",
               concentration=True, save_ability="DEX",
               desc="20-ft cube of webs; DEX save or restrained.")
    _add_spell(sheet, "Fireball", 3, "Evocation", "wizard",
               range_str="150 ft.", damage="8d6", save_ability="DEX",
               desc="20-ft-radius sphere, 8d6 fire (DEX save half). "
                    "Sculpt Spells: protect 5 allies (no damage even on fail).")
    _add_spell(sheet, "Counterspell", 3, "Abjuration", "wizard",
               casting_time="1 reaction", range_str="60 ft.",
               desc="Auto-stop a spell of 3rd level or lower; higher needs ability check.")

    _set_spell_slots(sheet, "wizard", {1: 4, 2: 3, 3: 2})

    sheet["inventory"] = ["Quarterstaff", "Spellbook", "Arcane focus (crystal)",
                          "Scholar's pack", "Ink and quill", "Letter of recommendation",
                          "30 gp"]
    sheet["notes"] = ("Arcane Recovery: once per long rest, on a short rest, "
                      "recover spell slots totalling ⌈Wizard level / 2⌉ = 3 levels.\n\n"
                      "Sculpt Spells (Evocation): when you cast an evocation spell that affects "
                      "an area, you can pick (1 + spell level) allies to automatically pass the "
                      "saving throw and take no damage.")
    return sheet


def _preset_barbarian_berserker_4() -> Dict[str, Any]:
    """Berserker Barbarian Lv4 — Reckless Attack, Rage 3/long, Frenzy on subclass."""
    abilities = {"STR": 18, "DEX": 14, "CON": 16, "INT": 8, "WIS": 12, "CHA": 8}
    sheet = _dnd5e_base(abilities, level=4)
    _add_class(
        sheet, "Barbarian", "Path of the Berserker", 4, "d12",
        armor="Light, medium, shields",
        weapons="Simple, martial",
        saves="STR, CON",
        skills="Athletics, Intimidation, Survival",
        equipment="Greataxe, 2 handaxes, explorer's pack, 4 javelins",
    )
    _set_hp(sheet, 47)               # d12 + 3*(7 + 3 CON) = 12 + 30 = 42 max-rolled
    _set_ac_speed(sheet, ac=15)      # Unarmored Defense = 10 + DEX + CON = 10+2+3
    _mark_save_prof(sheet, "STR", "CON")
    _mark_skill_prof(sheet, "Athletics", "Intimidation", "Survival")
    sheet["race"] = "Half-Orc"
    sheet["background"] = "Outlander"
    sheet["alignment"] = "Chaotic Good"

    _add_attack(sheet, "Greataxe (Rage)", "+6", "1d12+6", "slashing",
                desc="STR mod (+4) + Rage damage (+2). Heavy, two-handed.")
    _add_attack(sheet, "Greataxe (No Rage)", "+6", "1d12+4", "slashing",
                desc="No rage damage bonus.")
    _add_attack(sheet, "Handaxe", "+6", "1d6+4", "slashing",
                range_str="20/60 ft.", desc="Light, thrown.")
    _add_attack(sheet, "Javelin", "+6", "1d6+4", "piercing",
                range_str="30/120 ft.")

    sheet["inventory"] = ["Greataxe", "2 handaxes", "4 javelins", "Explorer's pack",
                          "Trophy (orc skull)", "Bone necklace", "10 gp"]
    sheet["notes"] = ("Rage: 3 uses / long rest, bonus action to enter, lasts 1 minute. "
                      "While raging: advantage on STR checks/saves, +2 damage on STR melee, "
                      "resistance to bludgeoning/piercing/slashing damage.\n\n"
                      "Reckless Attack: advantage on STR melee attacks this turn, but attacks "
                      "against you have advantage until your next turn.\n\n"
                      "Frenzy (Berserker): rage as a Frenzy → make a single melee weapon attack "
                      "as a bonus action each round of rage. Causes 1 level of exhaustion at end.")
    return sheet


def _preset_rogue_thief_3() -> Dict[str, Any]:
    """Thief Rogue Lv3 — Sneak Attack 2d6, Cunning Action, Fast Hands."""
    abilities = {"STR": 10, "DEX": 16, "CON": 14, "INT": 12, "WIS": 12, "CHA": 14}
    sheet = _dnd5e_base(abilities, level=3)
    _add_class(
        sheet, "Rogue", "Thief", 3, "d8",
        armor="Light",
        weapons="Simple, hand crossbows, longswords, rapiers, shortswords",
        saves="DEX, INT",
        skills="Acrobatics, Stealth, Sleight of Hand, Investigation, Perception, Deception",
        equipment="Rapier, shortbow + quiver of 20 arrows, burglar's pack, leather armor, 2 daggers, thieves' tools",
    )
    _set_hp(sheet, 22)
    _set_ac_speed(sheet, ac=14)      # leather (11) + DEX +3
    _mark_save_prof(sheet, "DEX", "INT")
    _mark_skill_prof(
        sheet, "Acrobatics", "Stealth", "Sleight of Hand",
        "Investigation", "Perception", "Deception",
        expertise=("Stealth", "Sleight of Hand"),
    )
    sheet["race"] = "Halfling (Lightfoot)"
    sheet["background"] = "Criminal"
    sheet["alignment"] = "Chaotic Neutral"
    sheet["speed"] = 25              # Halfling

    _add_attack(sheet, "Rapier", "+5", "1d8+3", "piercing",
                desc="Finesse. Sneak Attack: +2d6 on advantage or ally adjacent.")
    _add_attack(sheet, "Shortbow", "+5", "1d6+3", "piercing",
                range_str="80/320 ft.",
                desc="Two-handed. Sneak Attack applies on first attack with advantage.")
    _add_attack(sheet, "Dagger", "+5", "1d4+3", "piercing",
                range_str="20/60 ft.", desc="Finesse, light, thrown.")
    _add_attack(sheet, "Sneak Attack Bonus", "—", "2d6", "—",
                desc="Add 2d6 to one qualifying attack per turn (advantage or "
                     "ally adjacent to target, and no disadvantage on the roll).")

    sheet["inventory"] = ["Rapier", "Shortbow", "Quiver", "20 arrows",
                          "Leather armor", "2 daggers", "Burglar's pack",
                          "Thieves' tools", "Crowbar", "Dark hooded clothes",
                          "Belt pouch (15 gp)"]
    sheet["notes"] = ("Sneak Attack 2d6 — once per turn, on a hit with a finesse/ranged "
                      "weapon when you have advantage OR an ally is within 5 ft. of target.\n\n"
                      "Cunning Action: bonus action to Dash, Disengage, or Hide.\n\n"
                      "Thief (Lv 3): Fast Hands — use Cunning Action to use thieves' tools, "
                      "Sleight of Hand, or use an object. Second-Story Work — climb at full speed, "
                      "+3 ft. running long jump.")
    return sheet


# ── Registry ───────────────────────────────────────────────────────────

PRESETS: List[Dict[str, Any]] = [
    {
        "key": "blank-generic",
        "label": "Blank — Generic",
        "description": "Empty free-form sheet. Custom system or non-D&D play.",
        "template": "generic",
        "suggested_name": "",
        "build": lambda: copy.deepcopy(GENERIC_TEMPLATE),
    },
    {
        "key": "blank-dnd5e",
        "label": "Blank — D&D 5e",
        "description": "Empty 5e sheet (level 1, no class). Fill in by hand.",
        "template": "dnd5e",
        "suggested_name": "",
        "build": _preset_dnd5e_blank,
    },
    {
        "key": "druid-moon-5",
        "label": "🐺 Moon Druid Lv 5",
        "description": "Wood Elf Circle of the Moon druid — tests Wild Shape (CR 1 beasts), spells, full caster.",
        "template": "dnd5e",
        "suggested_name": "Thalindra Moonwhisper",
        "build": _preset_druid_moon_5,
    },
    {
        "key": "fighter-bm-5",
        "label": "⚔ Battle Master Fighter Lv 5",
        "description": "Dwarf Battle Master — Action Surge, Second Wind, 4d8 Superiority Dice, Extra Attack.",
        "template": "dnd5e",
        "suggested_name": "Bardin Stoneheart",
        "build": _preset_fighter_battlemaster_5,
    },
    {
        "key": "cleric-life-5",
        "label": "✨ Life Cleric Lv 5",
        "description": "Hill Dwarf Life Cleric — Channel Divinity, prepared spells with bonus healing, heavy armor.",
        "template": "dnd5e",
        "suggested_name": "Bellweather Goldhand",
        "build": _preset_cleric_life_5,
    },
    {
        "key": "wizard-evoc-5",
        "label": "🔥 Evocation Wizard Lv 5",
        "description": "High Elf Evocation Wizard — Fireball, Sculpt Spells, Arcane Recovery, prepared spellbook.",
        "template": "dnd5e",
        "suggested_name": "Faelar Quickspark",
        "build": _preset_wizard_evocation_5,
    },
    {
        "key": "barbarian-berserker-4",
        "label": "💢 Berserker Barbarian Lv 4",
        "description": "Half-Orc Berserker — Rage 3/long, Reckless Attack, Frenzy, greataxe smash.",
        "template": "dnd5e",
        "suggested_name": "Grok Bloodaxe",
        "build": _preset_barbarian_berserker_4,
    },
    {
        "key": "rogue-thief-3",
        "label": "🗡 Thief Rogue Lv 3",
        "description": "Lightfoot Halfling Thief — Sneak Attack 2d6, Cunning Action, Fast Hands, expertise.",
        "template": "dnd5e",
        "suggested_name": "Pip Quickfingers",
        "build": _preset_rogue_thief_3,
    },
]


def list_presets() -> List[Dict[str, Any]]:
    """Return all presets in display order (without their build functions)."""
    return [
        {k: v for k, v in p.items() if k != "build"}
        for p in PRESETS
    ]


def get_preset(key: str) -> Dict[str, Any] | None:
    """Return the preset dict for ``key``, or None if not found."""
    for p in PRESETS:
        if p["key"] == key:
            return p
    return None


def build_sheet(key: str) -> Dict[str, Any] | None:
    """Build a fresh sheet from a preset. Normalizes D&D 5e sheets so
    mirror fields (legacy ``class``/``subclass`` flats, multiclass roster
    invariants) are populated before save."""
    preset = get_preset(key)
    if not preset:
        return None
    sheet = preset["build"]()
    if preset.get("template") == "dnd5e":
        normalize_dnd5e_sheet(sheet)
    return sheet


def preset_template(key: str) -> str:
    """Return the sheet template ("dnd5e" / "generic") for a preset key."""
    preset = get_preset(key)
    return preset["template"] if preset else "generic"


def preset_suggested_name(key: str) -> str:
    preset = get_preset(key)
    return preset.get("suggested_name", "") if preset else ""
