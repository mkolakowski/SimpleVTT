"""Demo-mode seed dataset (v2.3.0; enriched v2.3.22, v2.3.25, v2.3.31).

A single source of truth for the public-demo dataset: three users
(GM + two players), one campaign with both players as members, one
battle map referencing a bundled placeholder image, three D&D 5e
characters (Rogue 5 for Alice, Wizard 5 for Bob, Cleric 5 for the
GM — added v2.3.25 so the demo party has a divine healer and the GM
has a PC mini-sheet to demo alongside the players), nine tokens
(3 PCs + 6 NPCs for the seeded encounter — incl. a v2.3.22 homebrew
Goblin Captain whose structured actions exercise the unified monster
mini-sheet flow), a small homebrew set (one feat + four richly-
authored monsters — v2.3.31 brought the Bandit Captain / Bandit /
Thug into the homebrew tier alongside the Goblin Captain so all
NPCs resolve via the same end-to-end editor → projection →
mini-sheet flow), a short roll history, and one "Tavern Brawl"
encounter snapshot.

When ``DEMO_MODE`` is enabled, ``app/demo_scheduler.py`` calls
``reset_and_reseed`` on boot (optional, default on) and again every
``DEMO_RESET_INTERVAL_MINUTES`` so the demo URL hands out a clean
slate. See ``docs/plans/demo-mode.md`` for the full design.

Wipe strategy: surgical, by deterministic emails + campaign-name
sentinel. If ``DEMO_MODE`` accidentally lands on a production deploy,
the wipe only touches rows tagged with these constants — none of which
exist in a real deployment. Full-DB wipe was deliberately rejected.

NPC stat blocks: each NPC token uses a TokenTemplate row whose ``sheet``
JSON is a minimal stat block. Live stat-block data still resolves
through the v2.0.0 shipped SRD content (e.g. ``bandit-captain.json``)
at view time — the demo just ensures the GM has a token to drop.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_password
from .local_content import HOMEBREW_ROOT, write_homebrew
from .models import (
    Campaign,
    CampaignMembership,
    Character,
    DiceRoll,
    Encounter,
    Map,
    Token,
    TokenTemplate,
    User,
    Visibility,
)

log = logging.getLogger(__name__)


# ── Constants (deterministic so the wipe-by-tag stays accurate) ─────
DEMO_GM_EMAIL = "demo-gm@example.com"
DEMO_ALICE_EMAIL = "demo-alice@example.com"
DEMO_BOB_EMAIL = "demo-bob@example.com"
DEMO_EMAILS = (DEMO_GM_EMAIL, DEMO_ALICE_EMAIL, DEMO_BOB_EMAIL)
DEMO_PASSWORD = "demopass"
DEMO_CAMPAIGN_NAME = "Demo: The Sundered Vault"


# ── Wipe ────────────────────────────────────────────────────────────
def wipe(db: Session) -> dict[str, int]:
    """Delete every row tagged as demo. Returns per-table counts."""
    counts: dict[str, int] = {}

    # 1) Find the demo users by email
    demo_users = db.query(User).filter(User.email.in_(DEMO_EMAILS)).all()
    demo_user_ids = [u.id for u in demo_users]
    counts["users_found"] = len(demo_users)

    # 2) Find the demo campaign by name (defensive — only ours uses
    # this exact string)
    demo_campaigns = (
        db.query(Campaign).filter(Campaign.name == DEMO_CAMPAIGN_NAME).all()
    )
    demo_campaign_ids = [c.id for c in demo_campaigns]
    counts["campaigns_found"] = len(demo_campaigns)

    if demo_campaign_ids:
        # Tokens (FK to maps in the campaign)
        map_id_subq = select(Map.id).where(Map.campaign_id.in_(demo_campaign_ids))
        counts["tokens"] = (
            db.query(Token)
            .filter(Token.map_id.in_(map_id_subq))
            .delete(synchronize_session=False)
        )
        # Encounters
        counts["encounters"] = (
            db.query(Encounter)
            .filter(Encounter.campaign_id.in_(demo_campaign_ids))
            .delete(synchronize_session=False)
        )
        # DiceRolls
        counts["dice_rolls"] = (
            db.query(DiceRoll)
            .filter(DiceRoll.campaign_id.in_(demo_campaign_ids))
            .delete(synchronize_session=False)
        )
        # TokenTemplates
        counts["token_templates"] = (
            db.query(TokenTemplate)
            .filter(TokenTemplate.campaign_id.in_(demo_campaign_ids))
            .delete(synchronize_session=False)
        )
        # Characters
        counts["characters"] = (
            db.query(Character)
            .filter(Character.campaign_id.in_(demo_campaign_ids))
            .delete(synchronize_session=False)
        )
        # Null out campaigns.active_map_id before deleting maps —
        # ``fk_campaign_active_map`` has no ondelete clause (and can't
        # easily get one because the FK is declared with ``use_alter`` to
        # break the campaigns↔maps cycle), so a DELETE on maps while a
        # demo campaign still points at one raises ForeignKeyViolation.
        db.query(Campaign).filter(
            Campaign.id.in_(demo_campaign_ids)
        ).update({Campaign.active_map_id: None}, synchronize_session=False)
        # Maps
        counts["maps"] = (
            db.query(Map)
            .filter(Map.campaign_id.in_(demo_campaign_ids))
            .delete(synchronize_session=False)
        )
        # Memberships
        counts["memberships"] = (
            db.query(CampaignMembership)
            .filter(CampaignMembership.campaign_id.in_(demo_campaign_ids))
            .delete(synchronize_session=False)
        )
        # The campaign itself
        for c in demo_campaigns:
            db.delete(c)

    # 3) Demo users (might also own standalone characters/campaigns we
    # don't care about cleaning up — the unique email constraint forces
    # us to delete them so seeding can recreate cleanly)
    if demo_user_ids:
        # Standalone characters owned by demo users (no campaign)
        db.query(Character).filter(
            Character.owner_user_id.in_(demo_user_ids)
        ).delete(synchronize_session=False)
        for u in demo_users:
            db.delete(u)

    db.commit()

    # 4) Homebrew JSON files for the demo campaign's scope
    for cid in demo_campaign_ids:
        scope_dir = HOMEBREW_ROOT / "dnd5e" / f"campaign-{cid}"
        if scope_dir.is_dir():
            try:
                shutil.rmtree(scope_dir)
                counts["homebrew_dirs"] = counts.get("homebrew_dirs", 0) + 1
            except OSError as e:
                log.warning("demo wipe: failed to remove %s: %s", scope_dir, e)

    return counts


# ── Seed helpers ────────────────────────────────────────────────────
def seed_users(db: Session) -> dict[str, User]:
    """Create the three demo users. All share the same password so the
    login page can advertise it. ``is_admin`` is True for the GM so the
    GM tools panel is reachable; the two players are non-admin."""
    pw = hash_password(DEMO_PASSWORD)
    gm = User(
        email=DEMO_GM_EMAIL,
        display_name="Demo GM",
        password_hash=pw,
        is_admin=True,
    )
    alice = User(
        email=DEMO_ALICE_EMAIL,
        display_name="Alice (Demo Rogue)",
        password_hash=pw,
        is_admin=False,
    )
    bob = User(
        email=DEMO_BOB_EMAIL,
        display_name="Bob (Demo Wizard)",
        password_hash=pw,
        is_admin=False,
    )
    db.add_all([gm, alice, bob])
    db.flush()
    return {"gm": gm, "alice": alice, "bob": bob}


def seed_campaign(db: Session, users: dict[str, User]) -> Campaign:
    camp = Campaign(
        name=DEMO_CAMPAIGN_NAME,
        description=(
            "Public demo campaign. Resets on a fixed interval — anything "
            "you change here will be wiped soon."
        ),
        gm_user_id=users["gm"].id,
        game_system="dnd5e",
        gm_color="#a78bfa",
        session_active=True,
        session_started_at=datetime.utcnow(),
    )
    db.add(camp)
    db.flush()

    # Players join as members; GM is implicit via gm_user_id.
    db.add_all([
        CampaignMembership(
            campaign_id=camp.id, user_id=users["alice"].id,
            is_gm=False, color="#6cb4ff",
        ),
        CampaignMembership(
            campaign_id=camp.id, user_id=users["bob"].id,
            is_gm=False, color="#4ade80",
        ),
    ])
    db.flush()
    return camp


def seed_map(db: Session, camp: Campaign) -> Map:
    # v2.4.1: dimensions match the new 1254×1254 tavern.png (replaced
    # the v2.3.0 placeholder). ``show_grid=True`` is the column default,
    # asserted explicitly here so a future seed-author who sees a map
    # with a baked-in grid background knows to flip it off rather than
    # remove the kwarg.
    m = Map(
        campaign_id=camp.id,
        name="The Sundered Tavern",
        image_url="/static/demo/maps/tavern.png",
        grid_size_px=70,
        width_px=1254,
        height_px=1254,
        show_grid=True,
    )
    db.add(m)
    db.flush()
    camp.active_map_id = m.id
    db.flush()
    return m


def _rogue_sheet(name: str) -> dict:
    """Minimal D&D 5e Rogue 5 sheet. Skips the long features text — the
    sheet's auto-fill flow can fetch race/class details from the local
    SRD content tier when the player opens it."""
    return {
        "class": "Rogue",
        "subclass": "Thief",
        "level": 5,
        "race": "Halfling",
        "alignment": "Chaotic Good",
        "background": "Criminal",
        "abilities": {"STR": 8, "DEX": 16, "CON": 14, "INT": 12, "WIS": 13, "CHA": 10},
        "ac": 14,
        "speed": 25,
        "hp": {"current": 33, "max": 33, "temp": 0},
        "initiative_bonus": 3,
        "proficiency_bonus": 3,
        "hit_dice": {"current": 5, "max": 5},
        "class_hit_die": "d8",
        "saving_throws": {"DEX": True, "INT": True},
        "skills": {
            "Stealth": {"ability": "DEX", "proficient": True, "expertise": True},
            "Sleight of Hand": {"ability": "DEX", "proficient": True, "expertise": True},
            "Perception": {"ability": "WIS", "proficient": True, "expertise": False},
            "Acrobatics": {"ability": "DEX", "proficient": True, "expertise": False},
            "Investigation": {"ability": "INT", "proficient": True, "expertise": False},
        },
        "attacks": [
            {"name": "Shortsword", "attack_bonus": "+6", "damage": "1d6+3",
             "damage_type": "piercing", "range": "5 ft", "desc": "Finesse, light"},
            {"name": "Dagger (thrown)", "attack_bonus": "+6", "damage": "1d4+3",
             "damage_type": "piercing", "range": "20/60 ft"},
        ],
        "spells": [],
        # v2.4.13: rich inventory items (was bare strings). Weapons /
        # armor / shield carry ``equippable: True`` so the equip toggle
        # renders on the sheet and the auto-attack engine in
        # ``sheet_dnd5e.html`` picks them up. ``_slug`` references the
        # shipped SRD content (under ``app/data/local/dnd5e/items/``)
        # so expanding a row lazy-loads the full description through
        # ``/api/content/items/<slug>``. Mundane gear that has no SRD
        # slug carries an inline ``desc`` so the expanded panel still
        # shows something useful.
        "inventory": [
            {"name": "Shortsword", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "piercing",
             "properties": "finesse, light", "_slug": "shortsword"},
            {"name": "Dagger", "type": "weapon", "qty": 2,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d4", "damage_type": "piercing",
             "range": "20/60 ft", "properties": "finesse, light, thrown",
             "_slug": "dagger"},
            {"name": "Studded leather", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "light", "ac_value": 12,
             "_slug": "studded-leather"},
            {"name": "Thieves' tools", "type": "gear", "qty": 1,
             "desc": "Small files, picks, mirror, pliers, scissors. Lets you make Dexterity (Sleight of Hand) checks to disarm traps or pick locks."},
            {"name": "Burglar's pack", "type": "gear", "qty": 1,
             "desc": "Backpack, 1,000 ball bearings, 10 ft string, bell, 5 candles, crowbar, hammer, 10 pitons, hooded lantern, 2 flasks of oil, 5 days rations, tinderbox, waterskin, 50 ft hempen rope."},
            {"name": "Hooded lantern", "type": "gear", "qty": 1,
             "desc": "Bright light in a 30-ft radius, dim light 30 ft beyond. Burns for 6 hours per flask of oil."},
            # v2.7.0: Potions of Healing for the /use_item demo path.
            # RAW (5e): drinking a potion is an action. With the
            # ``potions_as_bonus_action`` campaign setting (v2.5.0) on, the
            # /use_item endpoint instead consumes the bonus economy slot
            # and the Phase 4 over-budget gate fires on the bonus chip.
            {"name": "Potion of Healing", "type": "consumable", "qty": 2,
             "consumable": True, "use_kind": "heal", "heal_dice": "2d4+2",
             "_slug": "potion-of-healing",
             "desc": "Drink to regain 2d4+2 HP. RAW: action. Campaign setting can flip to bonus action."},
        ],
        "feats": [],
        "resources": [],
        # v2.6.0 (action-economy Phase 3): clickable class-feature
        # entries. The Class abilities section of sheet_dnd5e.html
        # renders each row as an expandable button; clicking an option
        # POSTs to /api/campaign/{id}/use_feature which announces the
        # use in the roll log + flips the action-economy chip via the
        # curated table in app/static/dnd5e_feature_economy.js.
        # Pip is Rogue 5 so Cunning Action (unlocked at Lv 2) applies.
        "class_features": [
            {
                "key": "cunning-action",
                "name": "Cunning Action",
                "desc": "On each of your turns in combat, you can use a bonus action to take the Dash, Disengage, or Hide action.",
                "options": ["dash", "disengage", "hide"],
            },
        ],
    }


def _wizard_sheet(name: str) -> dict:
    """Minimal D&D 5e Wizard 5 sheet."""
    return {
        "class": "Wizard",
        "subclass": "School of Evocation",
        "level": 5,
        "race": "Elf",
        "alignment": "Neutral Good",
        "background": "Sage",
        "abilities": {"STR": 8, "DEX": 14, "CON": 13, "INT": 16, "WIS": 12, "CHA": 10},
        "ac": 12,
        "speed": 30,
        "hp": {"current": 27, "max": 27, "temp": 0},
        "initiative_bonus": 2,
        "proficiency_bonus": 3,
        "hit_dice": {"current": 5, "max": 5},
        "class_hit_die": "d6",
        "class_spellcasting": "INT",
        "saving_throws": {"INT": True, "WIS": True},
        "skills": {
            "Arcana": {"ability": "INT", "proficient": True, "expertise": False},
            "History": {"ability": "INT", "proficient": True, "expertise": False},
            "Investigation": {"ability": "INT", "proficient": True, "expertise": False},
            "Perception": {"ability": "WIS", "proficient": True, "expertise": False},
        },
        "attacks": [
            {"name": "Quarterstaff", "attack_bonus": "+1", "damage": "1d6-1",
             "damage_type": "bludgeoning", "range": "5 ft", "desc": "Versatile"},
            {"name": "Fire Bolt (cantrip)", "attack_bonus": "+6", "damage": "2d10",
             "damage_type": "fire", "range": "120 ft", "desc": "Wizard cantrip"},
        ],
        # v2.4.19: ``_slug`` references the shipped SRD JSON under
        # ``app/data/local/dnd5e/spells/<slug>.json`` so expanding a spell
        # row lazy-loads its description through ``/api/content/spells/<slug>``
        # (helper ``_loadSpellContent`` in sheet_dnd5e.html). Same pattern
        # as the v2.4.13 inventory ``_slug`` references.
        # v2.5.3: ``casting_time`` field per the action-economy Phase 2
        # plan — the mini-cast-btn renderer passes it through as a
        # ``data-spell-casting-time`` attribute, and the click handler
        # derives the economy slot (action / bonus / reaction) from it.
        # Values match the SRD canonical casting_time strings.
        "spells": [
            {"name": "Fire Bolt", "level": 0, "prepared": True, "_slug": "fire-bolt", "casting_time": "1 action"},
            {"name": "Mage Hand", "level": 0, "prepared": True, "_slug": "mage-hand", "casting_time": "1 action"},
            {"name": "Prestidigitation", "level": 0, "prepared": True, "_slug": "prestidigitation", "casting_time": "1 action"},
            {"name": "Magic Missile", "level": 1, "prepared": True, "_slug": "magic-missile", "casting_time": "1 action"},
            {"name": "Shield", "level": 1, "prepared": True, "_slug": "shield", "casting_time": "1 reaction"},
            {"name": "Misty Step", "level": 2, "prepared": True, "_slug": "misty-step", "casting_time": "1 bonus action"},
            {"name": "Scorching Ray", "level": 2, "prepared": True, "_slug": "scorching-ray", "casting_time": "1 action"},
            {"name": "Fireball", "level": 3, "prepared": True, "_slug": "fireball", "casting_time": "1 action"},
            {"name": "Counterspell", "level": 3, "prepared": True, "_slug": "counterspell", "casting_time": "1 reaction"},
        ],
        "spell_slots": {
            "wizard": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 3, "used": 0},
                "3": {"total": 2, "used": 0},
            },
        },
        # v2.4.13: rich inventory items (was bare strings). See the
        # corresponding ``_rogue_sheet`` comment for the schema rationale.
        "inventory": [
            {"name": "Quarterstaff", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "bludgeoning",
             "versatile": True, "properties": "versatile (1d8)",
             "_slug": "quarterstaff"},
            {"name": "Spellbook", "type": "gear", "qty": 1,
             "desc": "Contains Thalindra's prepared spells + rituals. Required after a long rest to swap which spells are prepared."},
            {"name": "Component pouch", "type": "gear", "qty": 1,
             "desc": "A small leather belt pouch holding all material components needed to cast spells that don't list a specific costly component."},
            {"name": "Scholar's pack", "type": "gear", "qty": 1,
             "desc": "Backpack, book of lore, bottle of ink, ink pen, 10 sheets of parchment, small bag of sand, small knife."},
            {"name": "Robes", "type": "gear", "qty": 1,
             "desc": "Long flowing wizard's robes. Cosmetic — no mechanical effect."},
            {"name": "Ink and quill", "type": "gear", "qty": 1,
             "desc": "Bottle of black ink + writing quill. Required for spellbook transcription + ritual notation."},
            {"name": "Small knife", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": False, "hands": 1,
             "damage": "1d4", "damage_type": "piercing",
             "properties": "finesse, light", "_slug": "dagger"},
        ],
        "feats": [],
        "resources": [],
    }


def _cleric_sheet(name: str) -> dict:
    """v2.3.25: minimal D&D 5e Cleric 5 (Life Domain) sheet for the GM's
    character — fills the obvious gap in the demo party (no divine
    healer) and gives the GM a PC to play alongside the players when
    showing off the new mini-sheet flow."""
    return {
        "class": "Cleric",
        "subclass": "Life Domain",
        "level": 5,
        "race": "Hill Dwarf",
        "alignment": "Lawful Good",
        "background": "Folk Hero",
        "abilities": {"STR": 14, "DEX": 10, "CON": 14, "INT": 10, "WIS": 16, "CHA": 12},
        "ac": 18,
        "speed": 25,
        "hp": {"current": 43, "max": 43, "temp": 0},  # 8 + 4×6 (avg+CON) + 5 (Dwarven Toughness)
        "initiative_bonus": 0,
        "proficiency_bonus": 3,
        "hit_dice": {"current": 5, "max": 5},
        "class_hit_die": "d8",
        "class_spellcasting": "WIS",
        "saving_throws": {"WIS": True, "CHA": True},
        "skills": {
            "Religion": {"ability": "INT", "proficient": True, "expertise": False},
            "Insight": {"ability": "WIS", "proficient": True, "expertise": False},
            "Medicine": {"ability": "WIS", "proficient": True, "expertise": False},
            "Athletics": {"ability": "STR", "proficient": True, "expertise": False},
            "Animal Handling": {"ability": "WIS", "proficient": True, "expertise": False},
        },
        "attacks": [
            {"name": "Warhammer", "attack_bonus": "+5", "damage": "1d8+2",
             "damage_type": "bludgeoning", "range": "5 ft", "desc": "Versatile (1d10)"},
            {"name": "Sacred Flame (cantrip)", "save_dc": 14, "save_ability": "DEX",
             "damage": "2d8", "damage_type": "radiant", "range": "60 ft",
             "desc": "Cleric cantrip — target makes a DEX save or takes radiant damage."},
        ],
        # v2.4.15: Life Domain grants 6 domain spells unlocked by Cleric Lv 5
        # — Bless / Cure Wounds (L1), Lesser Restoration / Spiritual Weapon
        # (L2), Beacon of Hope / Revivify (L3). All carry
        # ``_subclass_granted: True`` so the sheet exempts them from the
        # prepared-spell cap (per ``_subclass_granted ? skip`` checks in
        # ``sheet_dnd5e.html`` ~line 1965/1992) and renders them with the
        # "granted" marker. ``_granted_by`` labels the source feature so the
        # tooltip / detail panel shows "Life Domain" rather than a generic
        # "Subclass" badge.
        # v2.4.19: ``_slug`` references the SRD spell JSON; see the wizard
        # sheet's spell list for the explanation.
        # v2.5.3: ``casting_time`` per the action-economy Phase 2 plan.
        "spells": [
            {"name": "Sacred Flame", "level": 0, "prepared": True, "_slug": "sacred-flame", "casting_time": "1 action"},
            {"name": "Guidance",     "level": 0, "prepared": True, "_slug": "guidance", "casting_time": "1 action"},
            {"name": "Light",        "level": 0, "prepared": True, "_slug": "light", "casting_time": "1 action"},
            {"name": "Bless",          "level": 1, "prepared": True, "_slug": "bless", "casting_time": "1 action",
             "_subclass_granted": True, "_granted_by": "Life Domain"},
            {"name": "Cure Wounds",    "level": 1, "prepared": True, "_slug": "cure-wounds", "casting_time": "1 action",
             "_subclass_granted": True, "_granted_by": "Life Domain"},
            {"name": "Healing Word",   "level": 1, "prepared": True, "_slug": "healing-word", "casting_time": "1 bonus action"},
            {"name": "Lesser Restoration", "level": 2, "prepared": True, "_slug": "lesser-restoration", "casting_time": "1 action",
             "_subclass_granted": True, "_granted_by": "Life Domain"},
            {"name": "Spiritual Weapon", "level": 2, "prepared": True, "_slug": "spiritual-weapon", "casting_time": "1 bonus action",
             "_subclass_granted": True, "_granted_by": "Life Domain"},
            {"name": "Hold Person",      "level": 2, "prepared": True, "_slug": "hold-person", "casting_time": "1 action"},
            {"name": "Beacon of Hope",  "level": 3, "prepared": True, "_slug": "beacon-of-hope", "casting_time": "1 action",
             "_subclass_granted": True, "_granted_by": "Life Domain"},
            {"name": "Revivify",        "level": 3, "prepared": True, "_slug": "revivify", "casting_time": "1 action",
             "_subclass_granted": True, "_granted_by": "Life Domain"},
            {"name": "Spirit Guardians",  "level": 3, "prepared": True, "_slug": "spirit-guardians", "casting_time": "1 action"},
            {"name": "Mass Healing Word", "level": 3, "prepared": True, "_slug": "mass-healing-word", "casting_time": "1 bonus action"},
        ],
        "spell_slots": {
            "cleric": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 3, "used": 0},
                "3": {"total": 2, "used": 0},
            },
        },
        # v2.4.13: rich inventory items (was bare strings). Chain mail
        # + shield are pre-equipped — the AC calc in
        # ``computeEffectiveAC`` (sheet_dnd5e.html ~line 4385) reads
        # ``ac_value=16`` from the chain mail + ``ac_value=2`` from the
        # shield = 18 total, matching the manually-set ``ac`` field.
        "inventory": [
            {"name": "Warhammer", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d8", "damage_type": "bludgeoning",
             "versatile": True, "properties": "versatile (1d10)",
             "_slug": "warhammer"},
            {"name": "Shield", "type": "shield", "qty": 1,
             "equippable": True, "equipped": True,
             "ac_value": 2, "_slug": "shield"},
            {"name": "Chain mail", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "heavy", "ac_value": 16,
             "_slug": "chain-mail"},
            {"name": "Holy symbol", "type": "gear", "qty": 1,
             "desc": "Amulet, emblem, or reliquary used as a divine focus — replaces the material component requirement for cleric spells."},
            {"name": "Priest's pack", "type": "gear", "qty": 1,
             "desc": "Backpack, blanket, 10 candles, tinderbox, alms box, 2 blocks of incense, censer, vestments, 2 days rations, waterskin."},
            {"name": "Smith's tools", "type": "gear", "qty": 1,
             "desc": "Hammers, tongs, charcoal, bellows, whetstone. Used to repair weapons + armor with a Strength (Smith's tools) check."},
            {"name": "Healer's kit", "type": "gear", "qty": 1,
             "desc": "10 uses. Spend an action + one use to stabilize a creature at 0 HP without a Wisdom (Medicine) check."},
            # v2.7.0: Potion of Healing for the /use_item demo path. See
            # the corresponding entry on ``_rogue_sheet`` for the action /
            # bonus-action house-rule semantics.
            {"name": "Potion of Healing", "type": "consumable", "qty": 1,
             "consumable": True, "use_kind": "heal", "heal_dice": "2d4+2",
             "_slug": "potion-of-healing",
             "desc": "Drink to regain 2d4+2 HP. RAW: action. Campaign setting can flip to bonus action."},
        ],
        "feats": [],
        # v2.4.15: seed the Channel Divinity resource so Tavik's class-resources
        # panel shows the counter from first sheet open instead of requiring
        # the player to click "Auto-fill Resources". Shape mirrors the recipe
        # in ``app/static/dnd5e_class_resources.js`` line 67-72: cleric Lv 2-5
        # gets 1 use, Lv 6-17 gets 2, Lv 18+ gets 3, refilling on short rest.
        # Tavik is Lv 5 → 1/1.
        "resources": [
            {
                "key": "channel-divinity",
                "name": "Channel Divinity",
                "current": 1,
                "max": 1,
                "reset": "short",
                "source": "cleric Lv 2",
                "class_slug": "cleric",
                "subclass_slug": "life",
                "desc": "Use a domain-granted effect (Turn Undead, Preserve Life).",
                "manual": False,
            },
        ],
    }


def _paladin_sheet(name: str) -> dict:
    """v2.14.0: demo Paladin Lv 5 (Oath of Devotion) for the GM.
    Added in the Phase A demo-party expansion alongside Brother Tavik
    so happy-path harness tests for /use_lay_on_hands (shipped without
    demo coverage in v2.10.0) can finally fire end-to-end. Also pre-
    populates Channel Divinity (Devotion options ship in a follow-up
    commit), Divine Sense, Fighting Style: Defense, and the L1-L2
    Paladin spell slate.
    """
    return {
        "class": "Paladin",
        "subclass": "Oath of Devotion",
        "level": 5,
        "race": "Human",  # standard +1 to all
        "alignment": "Lawful Good",
        "background": "Soldier",
        "abilities": {"STR": 16, "DEX": 10, "CON": 14, "INT": 10, "WIS": 12, "CHA": 16},
        "ac": 19,  # chain mail 16 + shield 2 + Fighting Style: Defense +1
        "speed": 30,
        "hp": {"current": 44, "max": 44, "temp": 0},  # 10 + 4×(6+CON) Lv 5 paladin
        "initiative_bonus": 0,
        "proficiency_bonus": 3,
        "hit_dice": {"current": 5, "max": 5},
        "class_hit_die": "d10",
        "class_spellcasting": "CHA",
        "saving_throws": {"WIS": True, "CHA": True},
        "skills": {
            "Persuasion":  {"ability": "CHA", "proficient": True, "expertise": False},
            "Religion":    {"ability": "INT", "proficient": True, "expertise": False},
            "Insight":     {"ability": "WIS", "proficient": True, "expertise": False},
            "Athletics":   {"ability": "STR", "proficient": True, "expertise": False},
        },
        "fighting_style": "defense",  # +1 AC while wearing armor
        "attacks": [
            {"name": "Longsword", "attack_bonus": "+6", "damage": "1d8+3",
             "damage_type": "slashing", "range": "5 ft", "desc": "Versatile (1d10). Sir Caelan's family blade."},
            {"name": "Javelin", "attack_bonus": "+6", "damage": "1d6+3",
             "damage_type": "piercing", "range": "30/120 ft", "desc": "Thrown finesse — keep a few in the bandolier."},
        ],
        # Paladin spells per Oath of Devotion (always prepared) + a few
        # core picks. Slugs reference the shipped SRD JSON. Casting
        # times tagged for the v2.5.3 action-economy auto-advance.
        "spells": [
            {"name": "Bless", "level": 1, "prepared": True, "_slug": "bless", "casting_time": "1 action"},
            {"name": "Cure Wounds", "level": 1, "prepared": True, "_slug": "cure-wounds", "casting_time": "1 action"},
            {"name": "Shield of Faith", "level": 1, "prepared": True, "_slug": "shield-of-faith", "casting_time": "1 bonus action"},
            {"name": "Protection from Evil and Good", "level": 1, "prepared": True, "_slug": "protection-from-evil-and-good", "casting_time": "1 action",
             "_subclass_granted": True, "_granted_by": "Oath of Devotion"},
            {"name": "Sanctuary", "level": 1, "prepared": True, "_slug": "sanctuary", "casting_time": "1 bonus action",
             "_subclass_granted": True, "_granted_by": "Oath of Devotion"},
            {"name": "Aid", "level": 2, "prepared": True, "_slug": "aid", "casting_time": "1 action"},
            {"name": "Lesser Restoration", "level": 2, "prepared": True, "_slug": "lesser-restoration", "casting_time": "1 action",
             "_subclass_granted": True, "_granted_by": "Oath of Devotion"},
            {"name": "Zone of Truth", "level": 2, "prepared": True, "_slug": "zone-of-truth", "casting_time": "1 action",
             "_subclass_granted": True, "_granted_by": "Oath of Devotion"},
        ],
        "spell_slots": {
            "paladin": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 2, "used": 0},
            },
        },
        "inventory": [
            {"name": "Longsword", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d8", "damage_type": "slashing",
             "properties": "versatile (1d10)", "_slug": "longsword"},
            {"name": "Javelin", "type": "weapon", "qty": 4,
             "equippable": True, "equipped": False, "hands": 1,
             "damage": "1d6", "damage_type": "piercing",
             "range": "30/120 ft", "properties": "thrown", "_slug": "javelin"},
            {"name": "Shield", "type": "shield", "qty": 1,
             "equippable": True, "equipped": True,
             "ac_value": 2, "_slug": "shield"},
            {"name": "Chain mail", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "heavy", "ac_value": 16,
             "_slug": "chain-mail"},
            {"name": "Holy symbol (amulet)", "type": "gear", "qty": 1,
             "desc": "Silver disc bearing the sun-and-anvil of the order. Divine focus — replaces material components for paladin spells."},
            {"name": "Explorer's pack", "type": "gear", "qty": 1,
             "desc": "Backpack, bedroll, mess kit, tinderbox, 10 torches, 10 days rations, waterskin, 50 ft hempen rope."},
            {"name": "Potion of Healing", "type": "consumable", "qty": 2,
             "consumable": True, "use_kind": "heal", "heal_dice": "2d4+2",
             "_slug": "potion-of-healing",
             "desc": "Drink to regain 2d4+2 HP. RAW: action. Campaign setting can flip to bonus action."},
        ],
        "feats": [],
        # v2.14.0: Lay on Hands pool (5 × Lv = 25 HP), Divine Sense
        # (1 + CHA mod = 4 / long rest), Channel Divinity (1 / short
        # rest), Cleansing Touch (CHA mod / long rest — locked at Lv 14
        # but pre-seeded as 0/0 so the Auto-fill flow stays idempotent).
        "resources": [
            {
                "key": "lay-on-hands",
                "name": "Lay on Hands",
                "current": 25, "max": 25, "reset": "long",
                "source": "paladin Lv 1",
                "class_slug": "paladin",
                "desc": "Touch-heal pool. Spend HP from the pool to heal a creature you touch. The 5 × Lv pool refreshes on a long rest.",
                "manual": False,
            },
            {
                "key": "divine-sense",
                "name": "Divine Sense",
                "current": 4, "max": 4, "reset": "long",
                "source": "paladin Lv 1",
                "class_slug": "paladin",
                "desc": "Action — detect celestials / fiends / undead within 60 ft until end of next turn. 1 + CHA mod uses per long rest.",
                "manual": False,
            },
            {
                "key": "channel-divinity",
                "name": "Channel Divinity",
                "current": 1, "max": 1, "reset": "short",
                "source": "paladin Lv 3",
                "class_slug": "paladin",
                "subclass_slug": "devotion",
                "desc": "Channel a domain effect (Sacred Weapon, Turn the Unholy). One use per short rest.",
                "manual": False,
            },
        ],
    }


def _bard_sheet(name: str) -> dict:
    """v2.14.1: demo Bard Lv 5 (College of Lore) for the GM. Added in
    Phase A.2 to unlock the deferred /use_bardic_inspiration happy-
    path harness test (priority #5, picker shipped in v2.11.0 without
    demo coverage). Cantrips include Vicious Mockery for the demo's
    "pick a save-DC cantrip" flow; spell list mixes the canonical
    Lv 5 Bard picks — Healing Word + Faerie Fire + Hypnotic Pattern —
    so the GM can drive a varied caster from one PC.
    """
    return {
        "class": "Bard",
        "subclass": "College of Lore",
        "level": 5,
        "race": "Half-Elf",  # +2 CHA, +1 to two others
        "alignment": "Chaotic Good",
        "background": "Entertainer",
        "abilities": {"STR": 8, "DEX": 14, "CON": 13, "INT": 12, "WIS": 10, "CHA": 17},
        "ac": 14,  # studded leather 12 + DEX +2
        "speed": 30,
        "hp": {"current": 33, "max": 33, "temp": 0},  # 8 + 4×(avg 5 + CON +1)
        "initiative_bonus": 0,
        "proficiency_bonus": 3,
        "hit_dice": {"current": 5, "max": 5},
        "class_hit_die": "d8",
        "class_spellcasting": "CHA",
        "saving_throws": {"DEX": True, "CHA": True},
        # Bards get any 3 skills + College of Lore grants 3 more at Lv 3.
        # Expertise (Lv 3) doubles proficiency on 2 chosen skills.
        "skills": {
            "Performance":  {"ability": "CHA", "proficient": True, "expertise": True},
            "Persuasion":   {"ability": "CHA", "proficient": True, "expertise": True},
            "Deception":    {"ability": "CHA", "proficient": True, "expertise": False},
            "Insight":      {"ability": "WIS", "proficient": True, "expertise": False},
            "Perception":   {"ability": "WIS", "proficient": True, "expertise": False},
            "Investigation": {"ability": "INT", "proficient": True, "expertise": False},
        },
        "attacks": [
            {"name": "Rapier", "attack_bonus": "+5", "damage": "1d8+2",
             "damage_type": "piercing", "range": "5 ft", "desc": "Finesse, one-handed."},
            {"name": "Hand crossbow", "attack_bonus": "+5", "damage": "1d6+2",
             "damage_type": "piercing", "range": "30/120 ft", "desc": "Light, loading."},
            {"name": "Vicious Mockery (cantrip)", "save_dc": 14, "save_ability": "WIS",
             "damage": "1d4", "damage_type": "psychic", "range": "60 ft",
             "desc": "WIS save or take psychic damage AND disadvantage on next attack roll before end of next turn."},
        ],
        # Lv 5 Bard known spells: 4 cantrips, 9 leveled (per Bard table).
        # ``casting_time`` tagged for the v2.5.3 action-economy.
        "spells": [
            {"name": "Vicious Mockery", "level": 0, "prepared": True, "_slug": "vicious-mockery", "casting_time": "1 action"},
            {"name": "Mage Hand", "level": 0, "prepared": True, "_slug": "mage-hand", "casting_time": "1 action"},
            {"name": "Minor Illusion", "level": 0, "prepared": True, "_slug": "minor-illusion", "casting_time": "1 action"},
            {"name": "Prestidigitation", "level": 0, "prepared": True, "_slug": "prestidigitation", "casting_time": "1 action"},
            {"name": "Healing Word", "level": 1, "prepared": True, "_slug": "healing-word", "casting_time": "1 bonus action"},
            {"name": "Cure Wounds", "level": 1, "prepared": True, "_slug": "cure-wounds", "casting_time": "1 action"},
            {"name": "Faerie Fire", "level": 1, "prepared": True, "_slug": "faerie-fire", "casting_time": "1 action"},
            {"name": "Heroism", "level": 1, "prepared": True, "_slug": "heroism", "casting_time": "1 action"},
            {"name": "Suggestion", "level": 2, "prepared": True, "_slug": "suggestion", "casting_time": "1 action"},
            {"name": "Invisibility", "level": 2, "prepared": True, "_slug": "invisibility", "casting_time": "1 action"},
            {"name": "Hold Person", "level": 2, "prepared": True, "_slug": "hold-person", "casting_time": "1 action"},
            {"name": "Hypnotic Pattern", "level": 3, "prepared": True, "_slug": "hypnotic-pattern", "casting_time": "1 action"},
            {"name": "Dispel Magic", "level": 3, "prepared": True, "_slug": "dispel-magic", "casting_time": "1 action"},
        ],
        "spell_slots": {
            "bard": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 3, "used": 0},
                "3": {"total": 2, "used": 0},
            },
        },
        "inventory": [
            {"name": "Rapier", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d8", "damage_type": "piercing",
             "properties": "finesse", "_slug": "rapier"},
            {"name": "Hand crossbow", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "piercing",
             "range": "30/120 ft", "properties": "light, loading", "_slug": "hand-crossbow"},
            {"name": "Studded leather", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "light", "ac_value": 12,
             "_slug": "studded-leather"},
            {"name": "Lute", "type": "gear", "qty": 1,
             "desc": "Lyra's instrument — a polished six-string serving as her bardic focus. Lets her cast spells with material components without a separate component pouch."},
            {"name": "Entertainer's pack", "type": "gear", "qty": 1,
             "desc": "Backpack, bedroll, 2 costumes, 5 candles, 5 days rations, waterskin, disguise kit."},
            {"name": "Potion of Healing", "type": "consumable", "qty": 1,
             "consumable": True, "use_kind": "heal", "heal_dice": "2d4+2",
             "_slug": "potion-of-healing",
             "desc": "Drink to regain 2d4+2 HP. RAW: action. Campaign setting can flip to bonus action."},
        ],
        "feats": [],
        # v2.14.1: Bardic Inspiration uses = CHA mod (3 at CHA 17),
        # refreshes on short rest from Lv 5 onward via Font of
        # Inspiration. Song of Rest exists as a passive (no counter
        # in RAW); will be wired into the short-rest endpoint when
        # Phase B Bard work ships.
        "resources": [
            {
                "key": "bardic-inspiration",
                "name": "Bardic Inspiration",
                "current": 3, "max": 3, "reset": "short",
                "source": "bard Lv 1 / Lv 5 (Font of Inspiration)",
                "class_slug": "bard",
                "desc": "Bonus action — pick an ally within 60 ft; they gain a Bardic Inspiration d8 for 10 minutes (add to one attack, check, or save). Refreshes on short rest from Lv 5.",
                "manual": False,
            },
        ],
    }


def _druid_sheet(name: str) -> dict:
    """v2.14.2: demo Druid Lv 5 (Circle of the Moon) for the GM.
    Added in Phase A.3 to set up the priority #4 Wild Shape work
    (transform UI completion). Circle of the Moon is the canonical
    combat-druid subclass — Wild Shape becomes a bonus action and
    the CR cap rises to 1 at Lv 2, both relevant for the demo's
    Tavern Brawl encounter. Spell list mixes utility (Faerie Fire,
    Pass Without Trace) with combat (Moonbeam, Call Lightning).
    """
    return {
        "class": "Druid",
        "subclass": "Circle of the Moon",
        "level": 5,
        "race": "Wood Elf",  # +2 DEX, +1 WIS
        "alignment": "Neutral Good",
        "background": "Outlander",
        "abilities": {"STR": 10, "DEX": 16, "CON": 14, "INT": 10, "WIS": 17, "CHA": 8},
        "ac": 15,  # studded leather 12 + DEX +3 (druids can't wear metal armor)
        "speed": 35,  # Wood Elf base 35 (Fleet of Foot)
        "hp": {"current": 36, "max": 36, "temp": 0},  # 8 + 4×(avg 5 + CON +2)
        "initiative_bonus": 0,
        "proficiency_bonus": 3,
        "hit_dice": {"current": 5, "max": 5},
        "class_hit_die": "d8",
        "class_spellcasting": "WIS",
        "saving_throws": {"INT": True, "WIS": True},
        "skills": {
            "Nature":          {"ability": "INT", "proficient": True, "expertise": False},
            "Animal Handling": {"ability": "WIS", "proficient": True, "expertise": False},
            "Perception":      {"ability": "WIS", "proficient": True, "expertise": False},
            "Survival":        {"ability": "WIS", "proficient": True, "expertise": False},
        },
        "attacks": [
            {"name": "Scimitar", "attack_bonus": "+6", "damage": "1d6+3",
             "damage_type": "slashing", "range": "5 ft", "desc": "Finesse — Mira's curved druidic blade."},
            {"name": "Sling", "attack_bonus": "+6", "damage": "1d4+3",
             "damage_type": "bludgeoning", "range": "30/120 ft", "desc": "Simple ranged option for when Wild Shape isn't on the table."},
            {"name": "Produce Flame (cantrip)", "attack_bonus": "+6", "damage": "1d8",
             "damage_type": "fire", "range": "30 ft", "desc": "Hurl flame as a ranged spell attack; scales to 2d8 at Lv 5."},
        ],
        # Lv 5 druid prepares WIS mod + level = 3 + 5 = 8 spells.
        # ``casting_time`` tagged for the v2.5.3 action-economy.
        "spells": [
            {"name": "Druidcraft",      "level": 0, "prepared": True, "_slug": "druidcraft", "casting_time": "1 action"},
            {"name": "Produce Flame",   "level": 0, "prepared": True, "_slug": "produce-flame", "casting_time": "1 action"},
            {"name": "Shillelagh",      "level": 0, "prepared": True, "_slug": "shillelagh", "casting_time": "1 bonus action"},
            {"name": "Healing Word",    "level": 1, "prepared": True, "_slug": "healing-word", "casting_time": "1 bonus action"},
            {"name": "Cure Wounds",     "level": 1, "prepared": True, "_slug": "cure-wounds", "casting_time": "1 action"},
            {"name": "Faerie Fire",     "level": 1, "prepared": True, "_slug": "faerie-fire", "casting_time": "1 action"},
            {"name": "Moonbeam",        "level": 2, "prepared": True, "_slug": "moonbeam", "casting_time": "1 action",
             "_subclass_granted": True, "_granted_by": "Circle of the Moon"},
            {"name": "Pass Without Trace", "level": 2, "prepared": True, "_slug": "pass-without-trace", "casting_time": "1 action"},
            {"name": "Heat Metal",      "level": 2, "prepared": True, "_slug": "heat-metal", "casting_time": "1 action"},
            {"name": "Call Lightning",  "level": 3, "prepared": True, "_slug": "call-lightning", "casting_time": "1 action"},
            {"name": "Conjure Animals", "level": 3, "prepared": True, "_slug": "conjure-animals", "casting_time": "1 action"},
        ],
        "spell_slots": {
            "druid": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 3, "used": 0},
                "3": {"total": 2, "used": 0},
            },
        },
        "inventory": [
            {"name": "Scimitar", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "slashing",
             "properties": "finesse, light", "_slug": "scimitar"},
            {"name": "Sling", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d4", "damage_type": "bludgeoning",
             "range": "30/120 ft", "properties": "ammunition", "_slug": "sling"},
            {"name": "Studded leather", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "light", "ac_value": 12,
             "_slug": "studded-leather"},
            {"name": "Wooden shield", "type": "shield", "qty": 1,
             "equippable": True, "equipped": False,
             "ac_value": 2, "_slug": "shield",
             "desc": "Hand-carved oak with carved leaf motif. Mira keeps it slung in case Wild Shape isn't available."},
            {"name": "Druidic focus (sprig of mistletoe)", "type": "gear", "qty": 1,
             "desc": "Required spellcasting focus — replaces material components for druid spells."},
            {"name": "Explorer's pack", "type": "gear", "qty": 1,
             "desc": "Backpack, bedroll, mess kit, tinderbox, 10 torches, 10 days rations, waterskin, 50 ft hempen rope."},
            {"name": "Herbalism kit", "type": "gear", "qty": 1,
             "desc": "Pouches, mortar + pestle, dried herbs. Proficient (druid)."},
            {"name": "Potion of Healing", "type": "consumable", "qty": 1,
             "consumable": True, "use_kind": "heal", "heal_dice": "2d4+2",
             "_slug": "potion-of-healing",
             "desc": "Drink to regain 2d4+2 HP. RAW: action. Campaign setting can flip to bonus action."},
        ],
        "feats": [],
        # v2.14.2: Wild Shape uses = 2/short rest at Lv 2 (Lv 18 unlimited).
        # Circle of the Moon raises the CR cap to 1 and lets the
        # transform fire as a bonus action — both Phase B work to
        # surface in the transform UI. Counter exists today so the
        # mini-sheet renders the chip.
        "resources": [
            {
                "key": "wild-shape",
                "name": "Wild Shape",
                "current": 2, "max": 2, "reset": "short",
                "source": "druid Lv 2 / Circle of the Moon",
                "class_slug": "druid",
                "subclass_slug": "moon",
                "desc": "Transform into a beast you've seen. Circle of the Moon: bonus-action shift, CR cap 1 at Lv 2 (scales with druid level). Two uses per short rest.",
                "manual": False,
            },
        ],
    }


def seed_characters(
    db: Session, camp: Campaign, users: dict[str, User]
) -> list[Character]:
    alice_pc = Character(
        campaign_id=camp.id,
        owner_user_id=users["alice"].id,
        name="Pip Quickfingers",
        template="dnd5e",
        sheet=_rogue_sheet("Pip Quickfingers"),
        color="#6cb4ff",
    )
    bob_pc = Character(
        campaign_id=camp.id,
        owner_user_id=users["bob"].id,
        name="Thalindra Moonwhisper",
        template="dnd5e",
        sheet=_wizard_sheet("Thalindra Moonwhisper"),
        color="#4ade80",
    )
    # v2.3.25: GM gets a Cleric so the demo party has a divine healer
    # and the GM has a PC mini-sheet to demo alongside the player ones.
    # Owned by ``gm`` so the GM controls them; campaign membership is
    # implicit via gm_user_id on the campaign.
    gm_pc = Character(
        campaign_id=camp.id,
        owner_user_id=users["gm"].id,
        name="Brother Tavik Stonebrow",
        template="dnd5e",
        sheet=_cleric_sheet("Brother Tavik Stonebrow"),
        color="#f5b75c",
    )
    # v2.14.0: Phase A.1 — demo Paladin (Sir Caelan Lightbringer).
    # Adds a 4th PC to unlock harness happy-paths for Lay on Hands
    # (priority #3 / shipped picker in v2.10.0) and queue Channel
    # Divinity (Devotion) + Divine Smite tests for Phase B-E. Same
    # GM-owned ownership pattern as Tavik.
    paladin_pc = Character(
        campaign_id=camp.id,
        owner_user_id=users["gm"].id,
        name="Sir Caelan Lightbringer",
        template="dnd5e",
        sheet=_paladin_sheet("Sir Caelan Lightbringer"),
        color="#e8c14a",
    )
    # v2.14.1: Phase A.2 — demo Bard (Lyra Sunstrider). 5th PC.
    # Unlocks the deferred /use_bardic_inspiration happy-path test
    # (priority #5 / shipped picker in v2.11.0 without demo coverage)
    # and queues Magical Secrets + Jack of All Trades + Song of Rest
    # work for Phase B.
    bard_pc = Character(
        campaign_id=camp.id,
        owner_user_id=users["gm"].id,
        name="Lyra Sunstrider",
        template="dnd5e",
        sheet=_bard_sheet("Lyra Sunstrider"),
        color="#d977b8",
    )
    # v2.14.2: Phase A.3 — demo Druid (Mira Greenleaf). 6th PC.
    # Sets up Phase B Wild Shape work (priority #4). Circle of the
    # Moon for combat-relevant Wild Shape (CR 1 cap at Lv 2, bonus-
    # action shift). After this commit the demo party is "6 PCs vs
    # 6 NPCs" — the Tavern Brawl encounter may want a 7th NPC for
    # tension; filed for the next demo-data commit.
    druid_pc = Character(
        campaign_id=camp.id,
        owner_user_id=users["gm"].id,
        name="Mira Greenleaf",
        template="dnd5e",
        sheet=_druid_sheet("Mira Greenleaf"),
        color="#4d9d6d",
    )
    db.add_all([alice_pc, bob_pc, gm_pc, paladin_pc, bard_pc, druid_pc])
    db.flush()
    return [alice_pc, bob_pc, gm_pc, paladin_pc, bard_pc, druid_pc]


def _npc_sheet(slug: str, label: str) -> dict:
    """Minimal NPC sheet that points at a shipped SRD monster slug. The
    actual stat block resolves via local_content when the GM opens it."""
    return {
        "class": "NPC",
        "monster_slug": slug,
        "level": 1,
        "abilities": {"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
    }


def seed_token_templates(db: Session, camp: Campaign) -> dict[str, TokenTemplate]:
    """One TokenTemplate per NPC role. Tokens reference these so right-
    clicking on a token can resolve the stat block.

    v2.3.22: ``goblin-captain`` here is a pointer to the homebrew monster
    JSON that ``seed_homebrew_files`` writes later in the orchestration —
    ``_monster_template_to_sheet`` resolves the slug via local_content at
    view time (homebrew tier first), so the order of operations within
    ``reset_and_reseed`` works as long as the homebrew file lands before
    the GM first opens its sheet. The homebrew tier overlays the full
    structured action list (multiattack, scimitar, javelin, frightful
    howl + pack tactics / nimble escape) onto this minimal pointer."""
    specs = [
        ("bandit-captain", "Bandit Captain"),
        ("bandit", "Bandit"),
        ("thug", "Thug"),
        ("goblin-captain", "Goblin Captain"),
    ]
    out: dict[str, TokenTemplate] = {}
    for slug, label in specs:
        tt = TokenTemplate(
            campaign_id=camp.id,
            name=label,
            template="dnd5e",
            sheet=_npc_sheet(slug, label),
            tags=["npc", "demo"],
        )
        db.add(tt)
        out[slug] = tt
    db.flush()
    return out


def seed_tokens(
    db: Session,
    map_: Map,
    chars: list[Character],
    templates: dict[str, TokenTemplate],
    users: dict[str, User],
) -> list[Token]:
    tokens: list[Token] = []

    # Player tokens — near the door (left side). v2.3.25: chars[2] is the
    # GM's Cleric (Brother Tavik); placed alongside the other PCs so the
    # demo party is visibly three-strong on the map. v2.3.44: all three
    # PCs now carry portrait jpgs from app/static/demo/tokens/ (the
    # color swatch on each combatant becomes the ring around the
    # portrait rather than the whole token face). v2.4.1: spawn positions
    # repositioned for the new 1254×1254 tavern.png — Brother Tavik on
    # the front line, Pip behind, Thalindra slightly off to the side.
    tokens.append(Token(
        map_id=map_.id, character_id=chars[0].id,
        controller_user_id=users["alice"].id,
        label=chars[0].name, color="#6cb4ff",
        image_url="/static/demo/tokens/rogue.jpg",
        x=350, y=490, size=1,
    ))
    tokens.append(Token(
        map_id=map_.id, character_id=chars[1].id,
        controller_user_id=users["bob"].id,
        label=chars[1].name, color="#4ade80",
        image_url="/static/demo/tokens/wizard.jpg",
        x=420, y=560, size=1,
    ))
    tokens.append(Token(
        map_id=map_.id, character_id=chars[2].id,
        controller_user_id=users["gm"].id,
        label=chars[2].name, color="#f5b75c",
        image_url="/static/demo/tokens/cleric.jpg",
        x=420, y=420, size=1,
    ))
    # v2.14.0: Phase A.1 — Sir Caelan token. Placed on the front line
    # slightly ahead of Tavik so the demo's "front-line martial" role
    # has visible representation. No portrait jpg ships yet; falls
    # back to the colored ring + label per the token render.
    tokens.append(Token(
        map_id=map_.id, character_id=chars[3].id,
        controller_user_id=users["gm"].id,
        label=chars[3].name, color="#e8c14a",
        image_url=None,
        x=490, y=420, size=1,
    ))
    # v2.14.1: Phase A.2 — Lyra token. Bards stay back; placed above
    # Pip at (350, 420) so the party reads visually as "Caelan + Tavik
    # front line, Pip / Thalindra middle, Lyra slightly off to the
    # north supporting".
    tokens.append(Token(
        map_id=map_.id, character_id=chars[4].id,
        controller_user_id=users["gm"].id,
        label=chars[4].name, color="#d977b8",
        image_url=None,
        x=350, y=420, size=1,
    ))
    # v2.14.2: Phase A.3 — Mira token. Druid stays at the northern
    # edge of the party — close enough for healing spells, far enough
    # to drop Moonbeam without catching allies in the AoE. (350, 350)
    # is one cell above Lyra.
    tokens.append(Token(
        map_id=map_.id, character_id=chars[5].id,
        controller_user_id=users["gm"].id,
        label=chars[5].name, color="#4d9d6d",
        image_url=None,
        x=350, y=350, size=1,
    ))

    # NPCs — near the bar (right side). v2.3.22: added a Goblin Captain
    # (homebrew, authored through the v2.3.8 structured-action editor) to
    # showcase the unified monster mini-sheet flow on the demo without
    # any GM setup. v2.3.44: every NPC now carries its own portrait jpg
    # — the three bandits use distinct alpha/beta/gamma files so the GM
    # can tell them apart at a glance (same template, different art).
    # v2.4.2: positions regridded for the 1254×1254 tavern.png (v2.4.1).
    # Two-column / three-row formation centred around x=910–1120 — all
    # tokens snapped to the 70-px grid and fit within the map (max x for
    # a 1×1 token = 1184). Vex up front, Thug back-right corner, Grixxa
    # bottom-right ("on a tabletop" per the encounter description), three
    # bandits filling the middle row + flanks. Roughly preserves the
    # original spatial relationships from the 1400×900 layout but
    # compressed into the new square room.
    npc_placements = [
        ("bandit-captain", "Vex (Bandit Captain)",     980, 420, "#c84a4a", "bandit-captain.jpg"),
        ("bandit",         "Bandit Alpha",             910, 490, "#c84a4a", "bandit-alpha.jpg"),
        ("bandit",         "Bandit Beta",             1050, 490, "#c84a4a", "bandit-beta.jpg"),
        ("bandit",         "Bandit Gamma",             980, 560, "#c84a4a", "bandit-gamma.jpg"),
        ("thug",           "Thug",                    1120, 420, "#c84a4a", "thug.jpg"),
        ("goblin-captain", "Grixxa (Goblin Captain)", 1120, 560, "#7c9c54", "goblin-captain.jpg"),
    ]
    for slug, label, x, y, color, image in npc_placements:
        tmpl = templates.get(slug)
        if not tmpl:
            continue
        tokens.append(Token(
            map_id=map_.id,
            character_id=None,
            token_template_id=tmpl.id,
            label=label,
            color=color,
            image_url=f"/static/demo/tokens/{image}",
            x=x, y=y, size=1,
        ))

    db.add_all(tokens)
    db.flush()
    return tokens


def seed_homebrew_files(camp: Campaign) -> int:
    """Write a couple of homebrew JSON files into the campaign's homebrew
    scope so the demo exercises the v2.0.0 file-based content path."""
    scope = f"campaign-{camp.id}"
    written = 0

    # Custom feat
    write_homebrew(
        {
            "slug": "lucky-strike",
            "name": "Lucky Strike",
            "prerequisite": "Dexterity 13 or higher",
            "desc": (
                "Once per short rest, when you miss with an attack roll, "
                "you may reroll the d20 and use the new result."
            ),
            "actions": [],
            "system": "dnd5e",
            "scope": scope,
            "source": "homebrew",
            "owner": None,
            "_attribution": "Demo seed homebrew (v2.3.0).",
        },
        type="feats",
        scope=scope,
    )
    written += 1

    # Custom monster — a goblin captain variant authored end-to-end through
    # the v2.3.8 structured-action editor. v2.3.22: expanded from one action
    # to a richer four-action loadout + two passive special abilities so the
    # demo showcases the full breadth of the editor → projection → mini-sheet
    # → click-to-roll pipeline that 2.3.7–2.3.21 built. Mix of attack-roll
    # melee, attack-roll ranged, and a save-based AoE so the GM can click
    # each tab on the new monster mini-sheet (rendered in the init tracker)
    # and see all three roll patterns fire into the campaign roll log.
    write_homebrew(
        {
            "slug": "goblin-captain",
            "name": "Goblin Captain",
            "size": "Small",
            "type": "humanoid",
            "alignment": "neutral evil",
            "armor_class": 15,
            "armor_desc": "studded leather",
            "hit_points": 36,
            "hit_dice": "8d6+8",
            "speed": {"walk": 30},
            "strength": 12, "dexterity": 16, "constitution": 12,
            "intelligence": 10, "wisdom": 12, "charisma": 13,
            "damage_immunities": "",
            "condition_immunities": "",
            "senses": "darkvision 60 ft., passive Perception 11",
            "languages": "Common, Goblin",
            "challenge_rating": "1",
            "actions": [
                {
                    "id": "multiattack",
                    "name": "Multiattack",
                    "desc": "The goblin captain makes two scimitar attacks, or one scimitar attack and one javelin attack.",
                    "category": "action",
                },
                {
                    "id": "scimitar",
                    "name": "Scimitar",
                    "desc": "Melee Weapon Attack: +5 to hit, reach 5 ft., one target. Hit: 6 (1d6 + 3) slashing damage.",
                    "damage": "1d6+3",
                    "damage_type": "slashing",
                    "attack_roll": True,
                    "attack_bonus": "+5",
                    "category": "action",
                },
                {
                    "id": "javelin",
                    "name": "Javelin",
                    "desc": "Melee or Ranged Weapon Attack: +5 to hit, reach 5 ft. or range 30/120 ft., one target. Hit: 6 (1d6 + 3) piercing damage.",
                    "damage": "1d6+3",
                    "damage_type": "piercing",
                    "attack_roll": True,
                    "attack_bonus": "+5",
                    "category": "action",
                },
                {
                    "id": "frightful-howl",
                    "name": "Frightful Howl (Recharge 5–6)",
                    "desc": "The goblin captain emits a piercing battle cry. Each creature within 30 feet that can hear it must succeed on a DC 12 Wisdom saving throw or become frightened of the goblin captain until the end of its next turn.",
                    "save_ability": "wis",
                    "save_dc": 12,
                    # v2.3.40: "Recharge 5-6" modeled as 1 charge per
                    # encounter — the GM clicks 📋 Save once, then
                    # manually clicks the ↻ recharge button when the
                    # die comes up at the start of a future turn. The
                    # init-tracker view shows "1/1" → "0/1" + disables
                    # the save button so the GM can't accidentally
                    # double-fire it.
                    "charges_max": 1,
                    "category": "action",
                },
                # Special abilities ride alongside actions on the unified
                # Monster.actions list with category="special_ability" — the
                # 2.3.8 coalescer / 2.3.10 adapter / mini-sheet rendering
                # all key off the category discriminator.
                {
                    "id": "pack-tactics",
                    "name": "Pack Tactics",
                    "desc": "The goblin captain has advantage on attack rolls against a creature if at least one of the goblin captain's allies is within 5 feet of the creature and the ally isn't incapacitated.",
                    "category": "special_ability",
                },
                {
                    "id": "nimble-escape",
                    "name": "Nimble Escape",
                    "desc": "The goblin captain can take the Disengage or Hide action as a bonus action on each of its turns.",
                    "category": "special_ability",
                },
            ],
            "system": "dnd5e",
            "scope": scope,
            "source": "homebrew",
            "owner": None,
            "_attribution": "Demo seed homebrew (v2.3.0; expanded v2.3.22).",
        },
        type="monsters",
        scope=scope,
    )
    written += 1

    # v2.3.31: convert the three SRD-resolved NPCs (Bandit Captain /
    # Bandit / Thug) to homebrew-authored monsters so all four demo
    # combatants resolve through the homebrew tier (parallel to Grixxa
    # above). Each one shadows the shipped SRD slug — same name, same
    # baseline stats, but with explicit ``attack_bonus`` populated (no
    # desc-regex fallback) and Special Abilities surfaced as
    # ``category: "special_ability"`` entries on the unified actions
    # list. ``_monster_template_to_sheet`` resolves homebrew tier
    # first, so the campaign's TokenTemplate pointers
    # (``monster_slug: "bandit-captain"`` etc.) now overlay these
    # homebrew records instead of the shipped SRD files.
    write_homebrew(
        {
            "slug": "bandit-captain",
            "name": "Bandit Captain",
            "size": "Medium",
            "type": "Humanoid",
            "alignment": "any non-lawful alignment",
            "armor_class": 15,
            "armor_desc": "studded leather",
            "hit_points": 65,
            "hit_dice": "10d8+20",
            "speed": {"walk": 30},
            "strength": 15, "dexterity": 16, "constitution": 14,
            "intelligence": 14, "wisdom": 11, "charisma": 14,
            "damage_immunities": "",
            "condition_immunities": "",
            "senses": "passive Perception 12",
            "languages": "any two languages",
            "challenge_rating": "2",
            "prof_saving_throws": "Str +4, Dex +5, Wis +2",
            "prof_skills": "Athletics +4, Deception +4",
            "actions": [
                {
                    "id": "multiattack",
                    "name": "Multiattack",
                    "desc": "The bandit captain makes three melee attacks: two with its scimitar and one with its dagger. Or the bandit captain makes two ranged attacks with its daggers.",
                    "category": "action",
                },
                {
                    "id": "scimitar",
                    "name": "Scimitar",
                    "desc": "Melee Weapon Attack: +5 to hit, reach 5 ft., one target. Hit: 6 (1d6 + 3) slashing damage.",
                    "damage": "1d6+3",
                    "damage_type": "slashing",
                    "attack_roll": True,
                    "attack_bonus": "+5",
                    "category": "action",
                },
                {
                    "id": "dagger",
                    "name": "Dagger",
                    "desc": "Melee or Ranged Weapon Attack: +5 to hit, reach 5 ft. or range 20/60 ft., one target. Hit: 5 (1d4 + 3) piercing damage.",
                    "damage": "1d4+3",
                    "damage_type": "piercing",
                    "attack_roll": True,
                    "attack_bonus": "+5",
                    "category": "action",
                },
                {
                    "id": "parry",
                    "name": "Parry",
                    "desc": "The bandit captain adds 2 to its AC against one melee attack that would hit it. To do so, the bandit captain must see the attacker and be wielding a melee weapon.",
                    "category": "reaction",
                },
                {
                    "id": "leadership",
                    "name": "Leadership (Recharges after a Short or Long Rest)",
                    "desc": "For 1 minute, the bandit captain can utter a special command or warning whenever a nonhostile creature that it can see within 30 feet of it makes an attack roll or a saving throw. The creature can add a d4 to its roll provided it can hear and understand the bandit captain. A creature can benefit from only one Leadership die at a time. This effect ends if the bandit captain is incapacitated.",
                    "category": "special_ability",
                },
            ],
            "system": "dnd5e",
            "scope": scope,
            "source": "homebrew",
            "owner": None,
            "_attribution": "Demo seed homebrew (v2.3.31). Stats from D&D 5e SRD 5.1; authored as homebrew so the demo exercises the homebrew tier end-to-end.",
        },
        type="monsters",
        scope=scope,
    )
    written += 1

    write_homebrew(
        {
            "slug": "bandit",
            "name": "Bandit",
            "size": "Medium",
            "type": "Humanoid",
            "alignment": "any non-lawful alignment",
            "armor_class": 12,
            "armor_desc": "leather armor",
            "hit_points": 11,
            "hit_dice": "2d8+2",
            "speed": {"walk": 30},
            "strength": 11, "dexterity": 12, "constitution": 12,
            "intelligence": 10, "wisdom": 10, "charisma": 10,
            "damage_immunities": "",
            "condition_immunities": "",
            "senses": "passive Perception 10",
            "languages": "any one language (usually Common)",
            "challenge_rating": "1/8",
            "actions": [
                {
                    "id": "scimitar",
                    "name": "Scimitar",
                    "desc": "Melee Weapon Attack: +3 to hit, reach 5 ft., one target. Hit: 4 (1d6 + 1) slashing damage.",
                    "damage": "1d6+1",
                    "damage_type": "slashing",
                    "attack_roll": True,
                    "attack_bonus": "+3",
                    "category": "action",
                },
                {
                    "id": "light-crossbow",
                    "name": "Light Crossbow",
                    "desc": "Ranged Weapon Attack: +3 to hit, range 80/320 ft., one target. Hit: 5 (1d8 + 1) piercing damage.",
                    "damage": "1d8+1",
                    "damage_type": "piercing",
                    "attack_roll": True,
                    "attack_bonus": "+3",
                    "category": "action",
                },
            ],
            "system": "dnd5e",
            "scope": scope,
            "source": "homebrew",
            "owner": None,
            "_attribution": "Demo seed homebrew (v2.3.31). Stats from D&D 5e SRD 5.1; authored as homebrew so the demo exercises the homebrew tier end-to-end.",
        },
        type="monsters",
        scope=scope,
    )
    written += 1

    write_homebrew(
        {
            "slug": "thug",
            "name": "Thug",
            "size": "Medium",
            "type": "Humanoid",
            "alignment": "any non-good alignment",
            "armor_class": 11,
            "armor_desc": "leather armor",
            "hit_points": 32,
            "hit_dice": "5d8+10",
            "speed": {"walk": 30},
            "strength": 15, "dexterity": 11, "constitution": 14,
            "intelligence": 10, "wisdom": 10, "charisma": 11,
            "damage_immunities": "",
            "condition_immunities": "",
            "senses": "passive Perception 10",
            "languages": "any one language (usually Common)",
            "challenge_rating": "1/2",
            "prof_skills": "Intimidation +2",
            "actions": [
                {
                    "id": "multiattack",
                    "name": "Multiattack",
                    "desc": "The thug makes two melee attacks.",
                    "category": "action",
                },
                {
                    "id": "mace",
                    "name": "Mace",
                    "desc": "Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 5 (1d6 + 2) bludgeoning damage.",
                    "damage": "1d6+2",
                    "damage_type": "bludgeoning",
                    "attack_roll": True,
                    "attack_bonus": "+4",
                    "category": "action",
                },
                {
                    "id": "heavy-crossbow",
                    "name": "Heavy Crossbow",
                    "desc": "Ranged Weapon Attack: +2 to hit, range 100/400 ft., one target. Hit: 5 (1d10) piercing damage.",
                    "damage": "1d10",
                    "damage_type": "piercing",
                    "attack_roll": True,
                    "attack_bonus": "+2",
                    "category": "action",
                },
                {
                    "id": "pack-tactics",
                    "name": "Pack Tactics",
                    "desc": "The thug has advantage on an attack roll against a creature if at least one of the thug's allies is within 5 feet of the creature and the ally isn't incapacitated.",
                    "category": "special_ability",
                },
            ],
            "system": "dnd5e",
            "scope": scope,
            "source": "homebrew",
            "owner": None,
            "_attribution": "Demo seed homebrew (v2.3.31). Stats from D&D 5e SRD 5.1; authored as homebrew so the demo exercises the homebrew tier end-to-end.",
        },
        type="monsters",
        scope=scope,
    )
    written += 1

    return written


def seed_roll_history(
    db: Session, camp: Campaign, users: dict[str, User]
) -> int:
    """Eight sample rolls spread over the last hour so the roll log
    isn't empty when the demo loads."""
    base = datetime.utcnow() - timedelta(minutes=42)
    rolls = [
        # (offset_min, user_key, expr, total, breakdown, note)
        (0,  "alice", "1d20+5",      18, "1d20[13]=13 +5  =>  18", "Stealth check"),
        (3,  "bob",   "1d20+5",      11, "1d20[6]=6 +5  =>  11",   "Arcana check"),
        (8,  "alice", "1d20+7",      19, "1d20[12]=12 +7  =>  19", "Sleight of Hand"),
        (12, "bob",   "8d6",         28, "8d6[6,5,4,3,3,3,2,2]=28  =>  28", "Fireball damage"),
        (15, "gm",    "1d20+4",      16, "1d20[12]=12 +4  =>  16", "Bandit Captain attack"),
        (24, "alice", "1d8+3",        9, "1d8[6]=6 +3  =>  9",     "Shortsword damage"),
        (33, "bob",   "2d20kh1+6",   23, "2d20kh1[3,17]kh11=17 +6  =>  23", "Magic Missile cast (auto advantage)"),
        (40, "alice", "1d20+3",       8, "1d20[5]=5 +3  =>  8",    "Acrobatics check"),
    ]
    out = 0
    for off, key, expr, total, brk, note in rolls:
        db.add(DiceRoll(
            campaign_id=camp.id,
            user_id=users[key].id,
            expression=expr,
            breakdown=brk,
            total=total,
            visibility=Visibility.PUBLIC,
            note=note,
            created_at=base + timedelta(minutes=off),
        ))
        out += 1
    db.flush()
    return out


def seed_encounter(
    db: Session,
    camp: Campaign,
    map_: Map,
    tokens: list[Token],
    chars: list[Character],
) -> tuple[Encounter, dict]:
    """One pre-staged 'Tavern Brawl' encounter referencing the seeded
    map + tokens with a deterministic initiative order.

    v2.4.3: rewritten to produce the **canonical** encounter payload
    shape consumed by ``_perform_encounter_load`` (in
    ``app/routes/tabletop_routes.py``) instead of the original
    pre-v0.73.0 shape this seed predated:

    - ``payload.tokens[].template_id`` (was ``token_template_id``) —
      NPC tokens recreated by Load now get their TokenTemplate
      binding back, so right-clicking a recreated bandit / thug /
      goblin captain opens the monster sheet rather than a bare
      label-only token.
    - ``payload.tokens[].image_url`` populated from each Token row —
      Load no longer strips the v2.3.44 portrait wiring.
    - ``payload.battle_state`` (was the dead-code ``initiative``
      key) — Load now seeds the in-memory battle hub with the full
      pre-rolled initiative including ``image_url`` on every
      combatant, so the GM init tracker auto-populates with
      portraits the instant the encounter is loaded.

    Returns ``(encounter, battle_state)`` — the second value lets
    ``reset_and_reseed`` push the same state into the realtime hub
    so fresh demo visitors see the populated init tracker on first
    WebSocket connect without anyone having to click "Load
    encounter" or "From Map" by hand. (Players hydrate from the WS
    ``battle_update`` push automatically; the GM client ignores
    that broadcast and instead reads its own localStorage, so the
    GM still needs a "From Map" / "Load encounter" click on first
    visit — that's a separate UX gap.)
    """
    # Initiative order — pre-rolled, twelve entries (6 PCs + 6 NPCs).
    # v2.3.22: Grixxa (Goblin Captain) at the top to showcase the new
    # monster mini-sheet up front.
    # v2.3.25: Brother Tavik (GM's Cleric) added at init 14.
    # v2.14.0: Sir Caelan (GM's Paladin) added at init 12.
    # v2.14.1: Lyra Sunstrider (GM's Bard) added at init 16.
    # v2.14.2: Mira Greenleaf (GM's Druid) added at init 8, between
    # Bandit Alpha (9) and Bandit Beta (7). NPC token indices +1
    # again to account for Mira at tokens[5].
    # Specs: (token_idx, initiative_roll, hp_max, dex_mod).
    init_specs = [
        # token_idx, init, hp_max, dex_mod
        (11, 18, 36, 3),   # Grixxa (Goblin Captain)
        (6,  17, 65, 3),   # Vex (Bandit Captain)
        (4,  16, 33, 2),   # Lyra Sunstrider (v2.14.1)
        (0,  15, 33, 3),   # Pip Quickfingers
        (2,  14, 43, 0),   # Brother Tavik Stonebrow
        (1,  13, 27, 2),   # Thalindra Moonwhisper
        (3,  12, 44, 0),   # Sir Caelan Lightbringer (v2.14.0)
        (10, 11, 32, 0),   # Thug
        (7,   9, 11, 1),   # Bandit Alpha
        (5,   8, 36, 3),   # Mira Greenleaf (v2.14.2)
        (8,   7, 11, 1),   # Bandit Beta
        (9,   5, 11, 1),   # Bandit Gamma
    ]
    combatants = []
    for token_idx, init_roll, hp_max, dex_mod in init_specs:
        tok = tokens[token_idx]
        combatants.append({
            "id": f"tok_{tok.id}_demo",
            "char_id": tok.character_id,
            "token_template_id": tok.token_template_id,
            "name": tok.label,
            "initiative": init_roll,
            "hp_current": hp_max,
            "hp_max": hp_max,
            "color": tok.color,
            "dex_mod": dex_mod,
            "image_url": tok.image_url,
        })
    battle_state = {
        "combatants": combatants,
        "turn_index": 0,
        "round": 1,
        # ``active=False`` keeps the "Start initiative" button live —
        # the GM clicks it to begin the round-tracker, matching how
        # they'd start any other fight. The pre-rolled initiative
        # values mean no roll-and-enter dance.
        "active": False,
    }
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
            }
            for t in tokens
        ],
        "battle_state": battle_state,
    }
    enc = Encounter(
        campaign_id=camp.id,
        name="Tavern Brawl",
        description=(
            "The bandits have you cornered against the bar. Vex barks "
            "orders, Grixxa the goblin captain hops onto a tabletop with "
            "scimitar drawn, and the thug cracks his knuckles. Brother "
            "Tavik unslings his warhammer behind you. Initiative is rolled."
        ),
        map_id=map_.id,
        payload=payload,
        tags=["demo", "combat"],
        folder="Demo",
    )
    db.add(enc)
    db.flush()
    camp.default_encounter_id = enc.id
    camp.current_encounter_id = enc.id
    db.flush()
    return enc, battle_state


# ── Orchestration ───────────────────────────────────────────────────
def _reset_sequences(db: Session) -> None:
    """v2.3.27: reset Postgres auto-increment sequences for the URL-keyed
    tables so each demo cycle hands out the same predictable ids
    (``/campaign/1``, ``/campaign/1/character/1/sheet``,
    ``/campaign/1/monster-template/22/sheet`` etc.) instead of drifting
    upward (``/campaign/4`` → ``/campaign/5`` → ...) every reset.

    Uses ``setval(seq, MAX(id), false)`` so the next INSERT picks
    ``MAX(id) + 1`` — which is 1 when the table is empty (the normal
    demo case post-wipe) and ``existing_max + 1`` when a real admin
    has populated the table with non-demo rows (no conflict).

    SQLite path is a no-op: SQLAlchemy's ``Integer primary_key=True``
    maps to plain ``INTEGER PRIMARY KEY`` (no AUTOINCREMENT keyword),
    and SQLite's default behavior is "next id = max(rowid) + 1" which
    already gives stable demo ids after the wipe deletes everything.
    Only Postgres's strict no-reuse `SERIAL` / `IDENTITY` exhibits the
    creep the user noticed.

    Scoped to the URL-visible tables (campaigns / characters /
    token_templates) — tokens / maps / encounters / users etc. still
    creep upward but their ids aren't bookmarked so it doesn't matter.
    """
    from sqlalchemy import text
    bind = db.get_bind()
    dialect = bind.dialect.name
    if dialect != "postgresql":
        return
    tables = ("campaigns", "characters", "token_templates")
    for t in tables:
        try:
            db.execute(text(
                f"SELECT setval('{t}_id_seq', "
                f"COALESCE((SELECT MAX(id) FROM {t}), 0) + 1, false)"
            ))
        except Exception as e:  # noqa: BLE001
            log.warning("demo wipe: couldn't reset %s_id_seq: %s", t, e)
    db.commit()


def reset_and_reseed(db: Session) -> dict[str, int]:
    """Wipe demo records then re-seed. Returns a per-section count
    suitable for logging on every reset."""
    log.info("demo reset: wiping previous dataset…")
    wipe_counts = wipe(db)
    log.info("demo wipe: %s", wipe_counts)

    # v2.3.27: ensure the post-wipe reseed gets stable ids (1, 1, 1, …)
    # for the URL-keyed tables. See ``_reset_sequences`` for the why.
    _reset_sequences(db)

    log.info("demo reset: seeding fresh dataset…")
    users = seed_users(db)
    camp = seed_campaign(db, users)
    map_ = seed_map(db, camp)
    chars = seed_characters(db, camp, users)
    templates = seed_token_templates(db, camp)
    tokens = seed_tokens(db, map_, chars, templates, users)
    rolls = seed_roll_history(db, camp, users)
    encounter, battle_state = seed_encounter(db, camp, map_, tokens, chars)

    db.commit()

    # v2.4.3: push the seeded battle state into the realtime hub so the
    # init tracker is pre-populated for player WebSocket connects (the
    # WS handshake pushes ``battle_update`` to new clients automatically
    # via ``hub.connect``). GM clients ignore that broadcast and read
    # their own localStorage, so a fresh-browser GM still needs to
    # click "From Map" or "Load encounter" once to populate their local
    # view — but the encounter payload now carries ``image_url`` on
    # every token AND a canonical ``battle_state`` so either click
    # gives them the portraits.
    from .realtime import hub
    hub.set_battle(camp.id, battle_state)

    # Homebrew JSON writes go to disk outside the SQL transaction —
    # do them AFTER commit so any DB failure rolls back the records.
    homebrew_count = seed_homebrew_files(camp)

    counts = {
        "users":           3,
        "campaign":        1,
        "memberships":     2,
        "map":             1,
        "characters":      len(chars),
        "token_templates": len(templates),
        "tokens":          len(tokens),
        "encounters":      1,
        "roll_history":    rolls,
        "homebrew_files":  homebrew_count,
    }
    log.info("demo reset complete: %s", counts)
    return counts
