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
        # The campaign itself. v2.49.173: use bulk delete (consistent
        # with the other tables above) instead of ``for c in ...:
        # db.delete(c)``. The per-row delete marks the rows for
        # deletion but doesn't flush — when the next section deletes
        # demo users, SQLAlchemy's flush ordering tries to drop users
        # before campaigns and FK constraint
        # ``campaigns_gm_user_id_fkey`` fires. Bulk delete + flush
        # forces the campaign rows out before the user delete runs.
        db.query(Campaign).filter(
            Campaign.id.in_(demo_campaign_ids)
        ).delete(synchronize_session=False)

    # Flush so the campaign deletions are committed to the DB before
    # the user deletions try to remove rows still referenced by them.
    db.flush()

    # 3) Demo users (might also own standalone characters/campaigns we
    # don't care about cleaning up — the unique email constraint forces
    # us to delete them so seeding can recreate cleanly)
    if demo_user_ids:
        # Standalone characters owned by demo users (no campaign)
        db.query(Character).filter(
            Character.owner_user_id.in_(demo_user_ids)
        ).delete(synchronize_session=False)
        # Drop any standalone campaigns owned by demo users (e.g. from
        # a partial prior reseed that didn't share the demo campaign
        # name). Without this the user delete still 409s on FK.
        db.query(Campaign).filter(
            Campaign.gm_user_id.in_(demo_user_ids)
        ).delete(synchronize_session=False)
        db.flush()
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
    # v2.51.1: default the demo GM's roll-log drawer to the left side
    # so the GM controls + initiative + characters tabs sit on the
    # right where the GM expects them, and roll history streams up
    # the left. Players still default to "right" (the User model
    # default) since each player has their own ergonomic preference
    # to pick from /settings.
    gm = User(
        email=DEMO_GM_EMAIL,
        display_name="Demo GM",
        password_hash=pw,
        is_admin=True,
        roll_log_position="left",
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
        # v2.49.209: enable auto-apply-damage on the demo campaign. The
        # Campaign model defaults this to False (per the v2.21.0
        # rationale: "existing tables aren't surprised by unexpected
        # HP changes; GMs opt in once they trust the flow") but the
        # demo's whole point is to SHOWCASE the auto-apply pipeline —
        # cast Fireball → server rolls saves per NPC → damage applies
        # → mini-sheet HP updates → 💀 overlay on the canvas when HP
        # hits 0. With auto_apply off the demo halts at "damage rolled,
        # GM clicks Apply" which doesn't surface as broken behavior;
        # it looks like the mini-sheet HP just doesn't update (the
        # v2.49.203 Phase 2.5b regression user reported). Enabling on
        # the demo also means the v2.49.205 _hydrateMonsterCard HP
        # patch step has something to react to.
        auto_apply_damage=True,
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
    """Minimal D&D 5e Rogue 7 sheet. Skips the long features text — the
    sheet's auto-fill flow can fetch race/class details from the local
    SRD content tier when the player opens it.

    v2.51.6: bumped Lv 5 → Lv 7 to unlock Evasion on the demo Rogue.
    Helper `_target_uses_evasion` (v2.51.5) already recognized Rogue
    Lv 7+; this commit's level bump + class_features row makes Pip
    the second Evasion demo fixture alongside Kael (Monk Lv 7).
    HP scales d8(5)+CON(2) per level × 2 = +14 → 47/47. Hit dice
    follow. Sneak Attack die is computed JS-side (`_sneakAttackDie(7)
    = ceil(7/2)d6 = 4d6`); no sheet field changes for it.
    Proficiency bonus stays +3 (Lv 5-8 = +3).
    """
    return {
        "class": "Rogue",
        "subclass": "Thief",
        "level": 7,
        "race": "Halfling",
        "alignment": "Chaotic Good",
        "background": "Criminal",
        "abilities": {"STR": 8, "DEX": 16, "CON": 14, "INT": 12, "WIS": 13, "CHA": 10},
        "ac": 14,
        "speed": 25,
        "hp": {"current": 47, "max": 47, "temp": 0},
        "initiative_bonus": 3,
        "proficiency_bonus": 3,
        "hit_dice": {"current": 7, "max": 7},
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
            # v2.158.103 — Magic-items Phase 7c demo fixture. Sword
            # of Sharpness Shortsword (RAW DMG p.206). +1 attack /
            # damage RAW-style baked in. On a natural 20, the
            # v2.158.101 + 7c post-hit handler rolls +4d6 slashing
            # via the on_nat_20 effect="damage" branch (Pip's
            # existing Sneak Attack 4d6 still doubles on crit too —
            # massive nat-20 swing). The "lop off a limb on a second
            # nat 20" RAW follow-up is GM narrative, not modeled.
            {"name": "Sword of Sharpness", "attack_bonus": "+7",
             "damage": "1d6+4", "damage_type": "slashing",
             "range": "5 ft", "_slug": "sword-of-sharpness",
             "desc": "Very rare shortsword, attunement. +1 attack/damage; on a natural 20, deal +4d6 slashing (RAW DMG p.206). Magical glow at command."},
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
            # v2.158.78 — Magic-items Phase 1d stacking fixture. Pip
            # wears BOTH a Cloak of Protection (neck slot) AND a Ring
            # of Protection (finger slot) — RAW lets a PC stack them
            # for cumulative +2 AC / +2 saves. Exercises the
            # _equipped_item_effects accumulator (the walker sums
            # numeric payloads across all matched items, doesn't
            # dedupe by item shape). Appended at END so existing
            # inventory-index assertions stay valid.
            {"name": "Cloak of Protection", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "cloak-of-protection",
             "desc": "Uncommon wondrous item, attunement. +1 AC and +1 to saving throws."},
            {"name": "Ring of Protection", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "ring-of-protection",
             "desc": "Rare ring, attunement. +1 AC and +1 to saving throws."},
            # v2.158.103 — Magic-items Phase 7c demo fixture. Sword of
            # Sharpness Shortsword (very rare, attunement). Pip caps
            # her attunement at 3/3 (Cloak + Ring + Sharpness — RAW
            # DMG p.138 cap exactly). Showcases a PC at the cap for
            # the attunement-pressure mechanic. The nat-20 rider
            # fires from the v2.158.101 + 7c post-hit handler via
            # the catalog's on_nat_20 = effect:"damage" branch.
            {"name": "Sword of Sharpness", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "hands": 1, "damage": "1d6", "damage_type": "slashing",
             "properties": "finesse, light, magic",
             "_slug": "sword-of-sharpness",
             "desc": "Very rare shortsword, attunement. +1 attack/damage; on a natural 20 attack roll, deal +4d6 slashing damage (RAW DMG p.206). On a second nat 20 — GM discretion — lop off a limb."},
            # v2.159.24 — first sensory-passive magic item. Goggles of
            # Night (RAW DMG p.172, uncommon, no attunement). Pip is a
            # Halfling — no racial darkvision — so the Goggles add a
            # meaningful sense + compose with the v2.158.50 Devil's
            # Sight darkness-blinded helper. inventory_index 10.
            {"name": "Goggles of Night", "type": "gear", "qty": 1,
             "equippable": True, "equipped": True,
             "_slug": "goggles-of-night",
             "desc": "Uncommon wondrous item, no attunement. While you wear these dark lenses, you have darkvision out to 60 ft. Composes with the Devil's Sight attack-disadvantage helper so a darkness-blinded wielder doesn't roll at disadvantage on attacks."},
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
            {
                "key": "uncanny-dodge",
                "name": "Uncanny Dodge",
                "desc": "When an attacker that you can see hits you with an attack, you can use your reaction to halve the attack's damage against you. Fires automatically server-side on the first incoming attack each round.",
            },
            # v2.51.6: Evasion (Rogue Lv 7). Mirror of Kael's Monk
            # Lv 7 entry (v2.51.5). Helper already recognized Rogue
            # Lv 7+; this commit's Pip level bump (5 → 7) + class_features
            # row makes Pip the Rogue-side demo fixture. Passive — no
            # /use endpoint or button; fires automatically inside
            # `_apply_evasion_to_dex_save_damage` on Dex-save damage.
            {
                "key": "evasion",
                "name": "Evasion",
                "desc": "Passive — when a Dex save would deal half damage, take none on success and half on failure. Fires automatically server-side on Dex-save spells like Fireball.",
            },
        ],
    }


def _wizard_sheet(name: str) -> dict:
    """Minimal D&D 5e Wizard 7 sheet.

    v2.97.72 — bumped Lv 5 → 7 so Thalindra has Lv 4 spell slots.
    Unlocks ``Confusion`` and ``Banishment`` (both Lv 4 wizard
    spells) on her list, which exercises the v2.97.62/69 end-of-
    turn auto-fire infrastructure (Confusion has end-of-turn Wis
    save RAW; Banishment doesn't, and the catalog reflects that).
    """
    return {
        "class": "Wizard",
        "subclass": "School of Evocation",
        "level": 7,
        "race": "Elf",
        "alignment": "Neutral Good",
        "background": "Sage",
        "abilities": {"STR": 8, "DEX": 14, "CON": 13, "INT": 16, "WIS": 12, "CHA": 10},
        "ac": 12,
        "speed": 30,
        "hp": {"current": 37, "max": 37, "temp": 0},
        "initiative_bonus": 2,
        "proficiency_bonus": 3,
        "hit_dice": {"current": 7, "max": 7},
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
            # v2.99.105 — Web. Lv 2 Conjuration, concentration up to
            # 1 hour, DEX save. Routed via /cast_web (NOT /cast_spell)
            # for the same reasons as Slow (v2.99.101) — dict-shape
            # mechanical effects don't fit the existing list-shape
            # _SPELL_CONDITION_MAP. Installs a `web` buff with
            # `effects.speed_reduction_ft: base` (clamps speed to 0)
            # on each target; descriptive Restrained effects
            # (advantage/disadvantage) surface as raw_effects bullets
            # for GM narration.
            {"name": "Web", "level": 2, "prepared": True, "_slug": "web",
             "casting_time": "1 action", "save_ability": "DEX",
             "desc": "60 ft, 20-ft cube, concentration up to 1 hour, DEX save DC 14. v1: routed via /cast_web; installs a per-target Restrained buff with speed_reduction_ft = base (→ speed 0). STR (Athletics) check to break free."},
            # v2.99.108 — Hold Monster. Lv 5 Enchantment,
            # concentration up to 1 min, WIS save. Routed via
            # /cast_hold_monster. Descriptive at Thalindra Lv 7
            # since she has no L5 slot in the demo; the harness
            # fixture PATCHes the slot in to exercise the endpoint.
            {"name": "Hold Monster", "level": 5, "prepared": True, "_slug": "hold-monster",
             "casting_time": "1 action", "save_ability": "WIS",
             "desc": "90 ft, concentration up to 1 min, WIS save DC 14. Any creature except Undead. Paralyzed. 1 target at L5; +1 per upcast level."},
            # v2.99.130 — Flesh to Stone. L6 Transmutation,
            # concentration up to 1 min, CON save. Descriptive at
            # Thalindra Lv 7 (no L6 slot stock); the test fixture
            # PATCHes a L6 slot to exercise the endpoint. Routes via
            # /cast_flesh_to_stone with stage="restrained" (initial
            # hardening) or stage="petrified" (after 3 fails — GM
            # decides). 3-strikes save tracking is filed.
            {"name": "Flesh to Stone", "level": 6, "prepared": True, "_slug": "flesh-to-stone",
             "casting_time": "1 action", "save_ability": "CON",
             "desc": "60 ft, concentration up to 1 min, CON save DC 14. On fail: Restrained as flesh hardens. CON save at end of each turn — 3 fails → Petrified for the duration (full minute = permanent). 3 successes end the spell."},
            {"name": "Fireball", "level": 3, "prepared": True, "_slug": "fireball", "casting_time": "1 action"},
            # v2.46.0 T.7a — Lightning Bolt exercises the line-shape
            # AoE picker (100 ft × 5 ft from the caster). Sits AFTER
            # Fireball so the FIREBALL_INDEX = 7 assumption in
            # tests/harness/test_cast_spell_aoe.py stays valid; this
            # spell lands at index 8.
            {"name": "Lightning Bolt", "level": 3, "prepared": True, "_slug": "lightning-bolt",
             "casting_time": "1 action", "damage": "8d6", "save_ability": "DEX",
             "desc": "100 ft × 5 ft line from caster, DEX save DC 14 for half. 8d6 lightning."},
            {"name": "Counterspell", "level": 3, "prepared": True, "_slug": "counterspell", "casting_time": "1 reaction"},
            # v2.99.101 — Slow. Lv 3 Transmutation, concentration.
            # Halves up to 6 targets' speed (WIS save). v1 wires the
            # speed-reduction effect into /cast_slow which installs a
            # `slow` buff with `effects.speed_reduction_ft: base // 2`
            # on each target. The reduced cap is honored by the
            # v2.99.98 _effective_speed_walk engine + the v2.99.99
            # /token/move 409 gate. Other Slow effects (-2 AC, no
            # reactions, action OR bonus action, single attack, spell
            # delay roll) are surfaced in the buff's raw_effects
            # tooltip but not yet mechanically enforced. Routed via
            # /cast_slow (NOT /cast_spell) so the multi-target install
            # + speed math can run without a refactor of the
            # _SPELL_CONDITION_MAP list-effects shape.
            {"name": "Slow", "level": 3, "prepared": True, "_slug": "slow",
             "casting_time": "1 action", "save_ability": "WIS",
             "desc": "120 ft, 40-ft cube, concentration up to 1 min, WIS save DC 14. v1: routed via /cast_slow; installs a per-target speed-reduction buff (base // 2 ft) that the v2.99.98 engine reads at /token/move time."},
            # v2.49.58 — Sleep. RAW: 5d8 + 2d8/extra slot HP-pool that
            # affects creatures by ascending current HP, no save, no
            # concentration. Routed through the dedicated /cast_sleep
            # endpoint rather than /cast_spell because the HP-pool
            # targeting doesn't fit the existing AoE/save pipeline.
            # Appended to keep the FIREBALL_INDEX = 7 + Counterspell = 9
            # assumptions in existing harness tests intact.
            {"name": "Sleep", "level": 1, "prepared": True, "_slug": "sleep", "casting_time": "1 action"},
            # v2.72.0 Phase 3d — Silvery Barbs (Strixhaven: SAI p.144).
            # Appended at the END of the spell list so existing
            # spell_index assertions (FIREBALL_INDEX=7, etc.) stay valid.
            # Wizard spell list (SAI): "1 reaction" trigger when a
            # creature within 60 ft you can see succeeds on a save /
            # attack / check; they reroll the d20 and take lower.
            {"name": "Silvery Barbs", "level": 1, "prepared": True, "_slug": "silvery-barbs",
             "casting_time": "1 reaction",
             "desc": "Reaction (when a creature within 60 ft succeeds on a d20 roll): they reroll and take the lower. You may also grant advantage to a different creature within 60 ft on its next attack/check/save within 1 minute."},
            # v2.97.72 — appended at the END of the spell list so
            # existing spell_index assertions stay valid. Both are
            # Lv 4 wizard spells with save-or-suck flows that route
            # through /respond's PC install path; the v2.97.71 catalog
            # entries handle the buff installation.
            {"name": "Confusion", "level": 4, "prepared": True, "_slug": "confusion",
             "casting_time": "1 action", "save_ability": "WIS",
             "desc": "10-ft-radius sphere within 90 ft. WIS save DC 14 or be Confused (d10 random behavior). Concentration up to 1 min. End-of-turn Wis save to shake off (RAW)."},
            {"name": "Banishment", "level": 4, "prepared": True, "_slug": "banishment",
             "casting_time": "1 action", "save_ability": "CHA",
             "desc": "60 ft single target. CHA save DC 14 or be Banished (incapacitated on harmless demiplane). Concentration up to 1 min. NO end-of-turn save RAW."},
            # v2.99.12 — Poison Spray. Wizard cantrip, CON save vs
            # 1d12 poison damage (2d12 at Lv 5+, 3d12 at Lv 11+, 4d12
            # at Lv 17+). Demo fixture for Dwarven Resilience: Tavik
            # (Hill Dwarf) saving against Thalindra's Poison Spray
            # exercises the v2.99.12 race save advantage gate. Damage
            # type "poison" matches the Dwarven Resilience rule's
            # damage_types list. Appended at END so existing
            # spell_index assertions stay valid.
            {"name": "Poison Spray", "level": 0, "prepared": True, "_slug": "poison-spray",
             "casting_time": "1 action", "save_ability": "CON",
             "damage": "1d12", "damage_type": "poison",
             "desc": "10 ft, CON save DC 14 or take 1d12 poison damage. Scales: 2d12 at L5+, 3d12 at L11+, 4d12 at L17+."},
            # v2.99.26 — Gust of Wind. Wizard Lv 2 spell, STR save
            # vs being pushed 15 ft. Demo fixture for Rage's STR-save
            # advantage hook: Krieger raging while caught in
            # Thalindra's Gust of Wind exercises the v2.99.26 wire.
            # No damage — this is a pure STR-save spell so the test
            # focuses on the d20 swap rather than damage halving.
            # Appended at END so existing spell_index assertions
            # stay valid.
            {"name": "Gust of Wind", "level": 2, "prepared": True, "_slug": "gust-of-wind",
             "casting_time": "1 action", "save_ability": "STR",
             "desc": "60 ft × 10 ft line from caster, STR save DC 14 or be pushed 15 ft. Disperses gas / extinguishes candles. Concentration up to 1 min."},
        ],
        "spell_slots": {
            "wizard": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 3, "used": 0},
                "3": {"total": 3, "used": 0},
                "4": {"total": 1, "used": 0},
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
            # v2.158.74 — Magic-items Phase 1a demo fixture. Cloak of
            # Protection (+1 AC, +1 saves) on Thalindra, equipped +
            # attuned, exercises the new _equipped_item_effects walker
            # at attack hit-determination time (_read_target_ac) and
            # at save-roll time (the /roll endpoint's *_save hook).
            # Appended at END so existing inventory-index assertions
            # stay valid.
            {"name": "Cloak of Protection", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "cloak-of-protection",
             "desc": "Uncommon wondrous item, attunement. +1 AC and +1 to saving throws."},
            # v2.158.82 — Magic-items Phase 3 demo fixture. Pearl of
            # Power (1/day spell-slot recovery, ≤ Lv 3) on Thalindra,
            # equipped + attuned. Exercises the new
            # /use_item_action endpoint + the _MAGIC_ITEM_ACTIONS
            # dispatch catalog. Paired with the pearl-of-power
            # resource row (max 1, reset long) added to her
            # ``resources`` array below.
            {"name": "Pearl of Power", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "pearl-of-power",
             "desc": "Uncommon wondrous item, attunement. 1/day at dawn (long rest), regain one expended spell slot of 3rd level or lower."},
            # v2.158.84 — Magic-items Phase 4a demo fixture. Wand of
            # Magic Missiles (7 charges, recharge 1d6+1 on long rest).
            # No attunement RAW (it's uncommon). Equipped so the
            # /use_item_action endpoint can fire against it. Paired
            # with the wand-of-magic-missiles resource row added to
            # her ``resources`` array below.
            {"name": "Wand of Magic Missiles", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": False,
             "_slug": "wand-of-magic-missiles",
             "desc": "Uncommon wand. 7 charges. Expend N (1-7) charges to cast Magic Missile at slot level N. Regains 1d6+1 charges daily at dawn (long rest)."},
            # v2.158.87 — Magic-items Phase 4c demo fixture. Wand of
            # Fireballs (rare, attunement). 7 charges, same recharge
            # as MM. Each charge casts Fireball at Lv 3 + (charges-1).
            # Paired with the wand-of-fireballs resource row below.
            {"name": "Wand of Fireballs", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "wand-of-fireballs",
             "desc": "Rare wand, attunement. 7 charges. Expend N (1-7) charges to cast Fireball (DC 15) at slot level 3+(N-1). Regains 1d6+1 charges at dawn (long rest)."},
            # v2.159.9 — Magic-items Phase 8i demo fixture. Necklace
            # of Fireballs (RAW DMG p.183, rare wondrous item, no
            # attunement). 6 beads in the resource row below. v1
            # ships single-bead throws (Lv 3 Fireball — 8d6 fire, DC
            # 15 DEX save half, 20-ft sphere). RAW lets the wearer
            # hurl multiple beads at once to upcast; Phase 8j will
            # ship the multi-bead picker.
            {"name": "Necklace of Fireballs", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True,
             "_slug": "necklace-of-fireballs",
             "desc": "Rare wondrous item. 6 fireball beads. Each thrown bead is a 3rd-level Fireball (8d6 fire, DC 15 DEX save half, 20-ft sphere). Beads don't regenerate."},
        ],
        "feats": [],
        # v2.16.1: Arcane Recovery counter (Wizard Lv 1 feature). Once per
        # day during a short rest, Thalindra can restore spell slots whose
        # combined level ≤ ceil(wizard_lv/2) — at Lv 5 that's 3 slot
        # levels (e.g., 3× L1, 1× L1 + 1× L2, 1× L3, etc.; L6+ slots are
        # not eligible). The resource ⚡ Use button opens a slot-restore
        # modal; /use_arcane_recovery decrements this counter + restores
        # the picked slots atomically.
        "resources": [
            {
                "key": "arcane-recovery",
                "name": "Arcane Recovery",
                "current": 1, "max": 1, "reset": "long",
                "source": "wizard Lv 1",
                "class_slug": "wizard",
                "desc": "Once per day during a short rest, regain spell slots whose combined level ≤ ⌈wizard_lv/2⌉ (3 levels at Lv 5). L6+ slots aren't eligible.",
                "manual": False,
            },
            # v2.158.82 — Magic-items Phase 3: Pearl of Power gate.
            # The /use_item_action endpoint decrements this counter on
            # each use + the rest loop refills it on a long rest via
            # the standard reset=long path. Pairs with the Pearl entry
            # in Thalindra's inventory above.
            {
                "key": "pearl-of-power",
                "name": "Pearl of Power",
                "current": 1, "max": 1, "reset": "long",
                "source": "item-pearl-of-power",
                "desc": "1/day at dawn (long rest): regain one expended spell slot of 3rd level or lower.",
                "manual": False,
            },
            # v2.158.84 — Magic-items Phase 4a: Wand of Magic Missiles
            # charge counter. Decremented by /use_item_action per
            # charge spent. The dice-expression recharge (1d6+1 at
            # dawn) lands in Phase 4b; for now the rest loop's
            # reset=long path refills it to max.
            {
                "key": "wand-of-magic-missiles",
                "name": "Wand of Magic Missiles",
                "current": 7, "max": 7, "reset": "long",
                # v2.158.86 — Phase 4b: dice-expression recharge.
                # The rest loop's refill path reads this expression
                # at long rest and rolls add-to-current capped at
                # max instead of the standard full refill.
                "charge_recovery": "1d6+1",
                "source": "item-wand-of-magic-missiles",
                "desc": "7 charges. Spend 1-7 to cast Magic Missile at the matching slot level. Regains 1d6+1 charges on long rest.",
                "manual": False,
            },
            # v2.158.87 — Magic-items Phase 4c: Wand of Fireballs
            # charge counter. Same shape as the MM wand (7 charges,
            # 1d6+1 recharge) but the spell + base slot level live
            # in the catalog (Fireball + base 3).
            {
                "key": "wand-of-fireballs",
                "name": "Wand of Fireballs",
                "current": 7, "max": 7, "reset": "long",
                "charge_recovery": "1d6+1",
                "source": "item-wand-of-fireballs",
                "desc": "7 charges. Spend 1-7 to cast Fireball at slot level 3+(N-1). Regains 1d6+1 charges on long rest.",
                "manual": False,
            },
            # v2.159.9 — Magic-items Phase 8i: Necklace of Fireballs
            # bead counter. RAW: starts with 1d6+3 beads (we ship 6
            # for the demo — average roll) and "the necklace is
            # destroyed" once depleted; the resource row has
            # ``reset: "none"`` so the rest loop doesn't refill it.
            # Each thrown bead is a Lv 3 Fireball (DC 15, 8d6 fire).
            {
                "key": "necklace-of-fireballs",
                "name": "Necklace of Fireballs",
                "current": 6, "max": 6, "reset": "none",
                "source": "item-necklace-of-fireballs",
                "desc": "6 fireball beads. Each thrown bead is a Lv 3 Fireball (DC 15 DEX save, 8d6 fire, 20-ft sphere). No regeneration.",
                "manual": False,
            },
        ],
    }


def _cleric_sheet(name: str) -> dict:
    """v2.3.25: minimal D&D 5e Cleric 5 (Life Domain) sheet for the GM's
    character — fills the obvious gap in the demo party (no divine
    healer) and gives the GM a PC to play alongside the players when
    showing off the new mini-sheet flow.

    v2.57.1: bumped Lv 5 → 6 to unlock Channel Divinity 2/short rest
    (Lv 6+ RAW) + Blessed Healer (Life Domain Lv 6 — passive temp HP
    on outgoing healing). Prof bonus stays +3 (Lv 5-8 band) so attack
    bonus + save DCs don't drift. L3 spell slot count 2 → 3 per
    Lv 6 cleric table (4/3/3 base).

    v2.60.0: bumped Lv 6 → 8 to unlock Divine Strike (Life Domain
    Lv 8+ — +1d8 radiant on weapon hits once per turn, wired into
    the /attack auto-uplifts list). Prof bonus still +3 (Lv 5-8
    band). Gains L4 slots (4/3/3/2 at Lv 8 per cleric table).
    """
    return {
        "class": "Cleric",
        "subclass": "Life Domain",
        "level": 8,
        "race": "Hill Dwarf",
        "alignment": "Lawful Good",
        "background": "Folk Hero",
        "abilities": {"STR": 14, "DEX": 10, "CON": 14, "INT": 10, "WIS": 16, "CHA": 12},
        "ac": 18,
        "speed": 25,
        # 8 (Lv 1 d8) + 7× avg d8 (5) + CON +2 × 8 + Dwarven Toughness +1 × 8
        # = 8 + 35 + 16 + 8 = 67. (v2.60.0: was 51 at Lv 6 — added 8 per level for Lv 7/8.)
        "hp": {"current": 67, "max": 67, "temp": 0},
        # v2.99.19 — Hill Dwarf Dwarven Resilience: resistance to
        # poison damage. RAW (PHB p.20). v2.99.12 shipped the
        # save-advantage half (Dwarven Resilience grants advantage
        # on saves vs poison); v2.99.18 extended _resistance_halve
        # to read sheet-level damage_resistances; v2.99.19 closes
        # the loop by declaring the resistance on Tavik's sheet.
        # Fire / acid / cold / etc. unaffected.
        "damage_resistances": ["poison"],
        "initiative_bonus": 0,
        "proficiency_bonus": 3,  # +3 through Lv 5-8.
        "hit_dice": {"current": 8, "max": 8},
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
        # Lv 8 cleric slot progression — 4/3/3/2 (v2.60.0: L4 added).
        "spell_slots": {
            "cleric": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 3, "used": 0},
                "3": {"total": 3, "used": 0},
                "4": {"total": 2, "used": 0},
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
            # v2.158.76 — Magic-items Phase 1b demo fixture. Ring of
            # Protection (+1 AC, +1 saves) on Tavik, equipped +
            # attuned. Same shape as Thalindra's Cloak (v2.158.74),
            # second catalog entry, different PC so attack-time AC +
            # /roll save assertions can target either fixture without
            # interfering. Tavik's WIS save is wired through the
            # existing Cleric proficiency so the save half of the
            # test exercises the same /roll hook.
            {"name": "Ring of Protection", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "ring-of-protection",
             "desc": "Rare ring, attunement. +1 AC and +1 to saving throws."},
            # v2.158.88 — Magic-items Phase 4d demo fixture. Staff
            # of Healing (rare, attunement). 10 charges, recharge
            # 1d6+4 at dawn. Multi-action: cast-cure-wounds 1-4
            # charges (Lv 1-4), cast-lesser-restoration 2, cast-mass-
            # cure-wounds 5. Thematic on Tavik (Cleric). Paired with
            # the staff-of-healing resource row below.
            {"name": "Staff of Healing", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "staff-of-healing",
             "desc": "Rare staff, attunement. 10 charges. Cast Cure Wounds (1-4 charges → Lv 1-4), Lesser Restoration (2 charges), or Mass Cure Wounds (5 charges). Regains 1d6+4 charges at dawn (long rest)."},
        ],
        # v2.76.0 Phase 4c — War Caster feat for Tavik. RAW (PHB
        # p.170): the reaction part lets Tavik cast a 1-action
        # single-target spell instead of an OA when a creature
        # provokes one (Sacred Flame, Guiding Bolt, Inflict Wounds,
        # etc.). Wired through the v2.66.0 creature_exits_reach
        # trigger event alongside the standard OA option.
        "feats": [
            {"slug": "war-caster", "name": "War Caster",
             "desc": "Advantage on Constitution saves to maintain concentration when you take damage. Somatic-while-holding-weapons. When a creature's movement provokes an OA from you, you can use your reaction to cast a 1-action spell at it instead of attacking."},
        ],
        # v2.4.15: seed the Channel Divinity resource so Tavik's class-resources
        # panel shows the counter from first sheet open instead of requiring
        # the player to click "Auto-fill Resources". Shape mirrors the recipe
        # in ``app/static/dnd5e_class_resources.js`` line 67-72: cleric Lv 2-5
        # gets 1 use, Lv 6-17 gets 2, Lv 18+ gets 3, refilling on short rest.
        # v2.57.1: Tavik Lv 6 → 2/2 (was 1/1 at Lv 5).
        "resources": [
            {
                "key": "channel-divinity",
                "name": "Channel Divinity",
                "current": 2,
                "max": 2,
                "reset": "short",
                "source": "cleric Lv 2",
                "class_slug": "cleric",
                "subclass_slug": "life",
                "desc": "Use a domain-granted effect (Turn Undead, Preserve Life). 2/short rest at Lv 6+.",
                "manual": False,
            },
            # v2.99.47 — Divine Intervention (Cleric Lv 10+). Roll
            # d100; if ≤ cleric level, deity intervenes (success).
            # At Lv 20, auto-success (no roll). Once per long rest
            # in v1 (RAW says 7-day cooldown on success — simplified
            # to long-rest for v1; the 7-day cooldown is filed for a
            # future multi-day tracker). Endpoint /use_divine_intervention
            # enforces the Lv 10+ gate. Descriptive at Lv 8.
            {
                "key": "divine-intervention-uses",
                "name": "Divine Intervention",
                "current": 1, "max": 1, "reset": "long",
                "source": "cleric Lv 10 / Divine Intervention",
                "class_slug": "cleric",
                "desc": "Action (Lv 10+): roll d100, if ≤ cleric level your deity intervenes. Lv 20 auto-succeeds. 1/long rest in v1 (RAW: 7-day cooldown on success — simplified). Use /use_divine_intervention.",
                "manual": False,
            },
            # v2.158.88 — Magic-items Phase 4d: Staff of Healing
            # charge counter. 10 starting charges, regains 1d6+4 at
            # dawn (long rest) via the Phase 4b dice-expression
            # recharge path. Multi-action item — the cure-wounds /
            # lesser-restoration / mass-cure-wounds actions all spend
            # from this single resource.
            {
                "key": "staff-of-healing",
                "name": "Staff of Healing",
                "current": 10, "max": 10, "reset": "long",
                "charge_recovery": "1d6+4",
                "source": "item-staff-of-healing",
                "desc": "10 charges. Cast Cure Wounds (1-4 charges), Lesser Restoration (2), or Mass Cure Wounds (5). Regains 1d6+4 charges on long rest.",
                "manual": False,
            },
        ],
        # v2.57.1: Blessed Healer (Life Domain Lv 6+).
        # v2.58.0: ships with the heal-uplift hook
        # ``_life_domain_heal_uplift`` wired at /cast_spell — both
        # Disciple of Life (Lv 1+ — uplift the target heal) and
        # Blessed Healer (Lv 6+ — self-heal the caster) fire
        # automatically when Tavik casts a Lv 1+ heal. Two
        # ``feature_used`` broadcasts surface the uplifts to the
        # chat card.
        "class_features": [
            {
                "key": "disciple-of-life",
                "name": "Disciple of Life",
                "desc": "Passive (Life Domain Lv 1+) — your Lv 1+ heal spells restore an extra 2 + spell level HP to the target. Fires automatically via /cast_spell hook (v2.58.0).",
            },
            {
                "key": "blessed-healer",
                "name": "Blessed Healer",
                "desc": "Passive (Life Domain Lv 6+) — when you cast a Lv 1+ heal spell on a creature other than yourself, you ALSO regain 2 + spell level HP. Fires automatically via /cast_spell hook (v2.58.0).",
            },
            # v2.60.0: Divine Strike (Life Domain Lv 8+). Once per turn
            # when you hit with a weapon attack, add +1d8 radiant
            # damage to the hit. Wired into /attack via the auto-
            # uplifts list — uses the same once-per-turn flag pattern
            # as Colossus Slayer (combatant.economy.divine_strike_used,
            # reset by the GM-side nextTurn handler).
            {
                "key": "divine-strike",
                "name": "Divine Strike",
                "desc": "Passive (Life Domain Lv 8+) — once per turn, hits with a weapon attack deal an extra 1d8 radiant damage. Fires automatically via /attack hook (v2.60.0).",
            },
            # v2.99.47 — Divine Intervention (Cleric Lv 10+). PHB
            # p.59. Action: roll d100; if ≤ cleric level, deity
            # intervenes. At Lv 20, auto-success. Descriptive entry;
            # endpoint /use_divine_intervention enforces the gate.
            {
                "key": "divine-intervention",
                "name": "Divine Intervention (Lv 10)",
                "desc": "Action: call on your deity to intervene. Roll d100; on a result equal to or less than your cleric level, your deity intervenes (DM narrates the help). At 20th level the call auto-succeeds. v1 ship: 1/long rest (RAW: 7-day cooldown on success — simplified). Use /use_divine_intervention.",
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
        # v2.53.0: bumped Lv 5 → Lv 6 to unlock Aura of Protection.
        # v2.55.0: bumped Lv 6 → Lv 7 to unlock Aura of Devotion
        # (Oath of Devotion subclass): allies within 10 ft are immune
        # to being charmed. HP scales d10(avg 6)+CON(+2) per level × 1
        # more level = +8 → 60/60. hit_dice 6 → 7. Lay on Hands pool
        # 5×lv = 30 → 35 HP. Proficiency stays +3 (Lv 5-8 = +3). No
        # new spell slots at Paladin Lv 7 (4×L1 + 3×L2 unchanged from
        # Lv 6 — wait, Lv 7 actually gets L3 slots... no, Lv 7
        # paladin has 4/3/0/0). Actually Paladin Lv 7 = 4 L1 + 3 L2
        # slots, same as Lv 6 — L3 slots unlock at Lv 9 (half-caster
        # progression). Slot counts unchanged.
        "level": 7,
        "race": "Human",  # standard +1 to all
        "alignment": "Lawful Good",
        "background": "Soldier",
        "abilities": {"STR": 16, "DEX": 10, "CON": 14, "INT": 10, "WIS": 12, "CHA": 16},
        # v2.68.10: fighting style swapped Defense → Protection so the
        # v2.68.7 GM Reactions catalog has live Phase 2c coverage. AC
        # drops 19 → 18 (lose Defense's +1 AC); gains the Protection
        # reaction. Sir Caelan Lightbringer is a defender-flavored
        # paladin so the swap fits his archetype.
        "ac": 18,  # chain mail 16 + shield 2 (no Defense +1 anymore)
        "speed": 30,
        "hp": {"current": 60, "max": 60, "temp": 0},  # 10 + 6×(6+CON) Lv 7 paladin
        "initiative_bonus": 0,
        "proficiency_bonus": 3,
        "hit_dice": {"current": 7, "max": 7},
        "class_hit_die": "d10",
        "class_spellcasting": "CHA",
        "saving_throws": {"WIS": True, "CHA": True},
        "skills": {
            "Persuasion":  {"ability": "CHA", "proficient": True, "expertise": False},
            "Religion":    {"ability": "INT", "proficient": True, "expertise": False},
            "Insight":     {"ability": "WIS", "proficient": True, "expertise": False},
            "Athletics":   {"ability": "STR", "proficient": True, "expertise": False},
        },
        # v2.68.10: Protection style (PHB) — reaction: when an
        # attacker targets an ally within 5 ft (you must have a
        # shield), impose disadvantage on the attack roll. Powers
        # the v2.68.7 fighting-style-protection catalog entry.
        "fighting_style": "protection",
        "attacks": [
            {"name": "Longsword", "attack_bonus": "+6", "damage": "1d8+3",
             "damage_type": "slashing", "range": "5 ft", "desc": "Versatile (1d10). Sir Caelan's family blade."},
            {"name": "Javelin", "attack_bonus": "+6", "damage": "1d6+3",
             "damage_type": "piercing", "range": "30/120 ft", "desc": "Thrown finesse — keep a few in the bandolier."},
            # v2.158.93 — Magic-items Phase 5c demo fixture. Dragon
            # Slayer Longsword (RAW DMG p.166). +1 to attack + damage
            # baked into this entry; the +3d6-vs-dragons rider fires
            # from `_compute_attack_auto_uplifts` section 6c when the
            # target carries ``creature_type: "dragon"``. The
            # ``_slug`` field is the rider gate.
            {"name": "Dragon Slayer Longsword", "attack_bonus": "+7",
             "damage": "1d8+4", "damage_type": "slashing",
             "range": "5 ft", "_slug": "dragon-slayer",
             "desc": "Rare longsword, attunement. +1 attack/damage; +3d6 slashing vs. dragons (DMG p.166)."},
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
            # v2.97.73 — Banishment appended to Caelan's known paladin
            # spell list. RAW: Banishment is on the Paladin class list
            # at Lv 4. RAW paladin L4 slots unlock at class Lv 13 (half
            # caster progression); Caelan is currently Lv 7 so he can
            # PREPARE Banishment but cannot CAST it until levelup (or
            # via the v2.49.124 metamagic / Sorcery Points flexible
            # casting routes — neither of which Caelan has). The entry
            # documents the spell as a known / preparable spell rather
            # than as a currently-castable one. /cast_spell will return
            # 409 ``no_slot`` for slot_level=4 without an L4 pool —
            # which is RAW-correct behavior at Caelan's current level.
            # Future Caelan Lv 13 bump would just add ``"4": {"total":
            # 1, "used": 0}`` to spell_slots.paladin.
            {"name": "Banishment", "level": 4, "prepared": True, "_slug": "banishment",
             "casting_time": "1 action", "save_ability": "CHA",
             "desc": "60 ft single target. CHA save DC 14 or be Banished (incapacitated on harmless demiplane). Concentration up to 1 min. NO end-of-turn save RAW. L4 slot — preparable today, castable once Caelan reaches Paladin Lv 13."},
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
            # v2.158.93 — Magic-items Phase 5c demo fixture. Dragon
            # Slayer Longsword (rare, attunement). First conditional-
            # rider item: the +3d6 only fires when the target carries
            # ``creature_type: "dragon"`` (any of the chromatic /
            # metallic / gem ancestries). Paired with the attack entry
            # above via ``_slug``. Caelan ships equipped + attuned;
            # cap of 3 attuned unchanged (1 / 3).
            {"name": "Dragon Slayer Longsword", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "hands": 1, "damage": "1d8", "damage_type": "slashing",
             "properties": "versatile (1d10), magic",
             "_slug": "dragon-slayer",
             "desc": "Rare longsword, attunement. +1 attack/damage; while attuned, deals +3d6 slashing damage to dragons (RAW DMG p.166)."},
        ],
        # v2.99.24 — Caelan is a Variant Human (RAW: free Lv 1 feat).
        # Sentinel fits his Paladin Devotion frontline-protector role:
        # ally-attacked-near-you OA advisory (v2.66.5 effect 3 wired
        # through /attack + /npc_attack). Effects 1 (OA-hit speed-0)
        # and 2 (Disengage bypass denial) are filed pending the OA
        # auto-fire stack + Disengage modeling. Distinct from
        # Tavik's War Caster, Lyra's Defensive Duelist, Krieger's
        # Mage Slayer, and Garrik's Lucky.
        "feats": [
            {"slug": "sentinel", "name": "Sentinel",
             "desc": "When you hit a creature with an OA, its speed becomes 0 for the rest of the turn. Creatures within 5 ft provoke OAs even after taking Disengage. When a creature within 5 ft of you attacks an ally (not you), you can use your reaction to make a melee weapon attack against it."},
        ],
        # v2.14.0: Lay on Hands pool (5 × Lv = 25 HP), Divine Sense
        # (1 + CHA mod = 4 / long rest), Channel Divinity (1 / short
        # rest), Cleansing Touch (CHA mod / long rest — locked at Lv 14
        # but pre-seeded as 0/0 so the Auto-fill flow stays idempotent).
        "resources": [
            {
                "key": "lay-on-hands",
                "name": "Lay on Hands",
                # v2.53.0: Lv 6 bump → pool 5×6 = 30 HP (was 25 at Lv 5).
                # v2.55.0: Lv 7 bump → pool 5×7 = 35 HP.
                "current": 35, "max": 35, "reset": "long",
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
            # v2.99.155 — Holy Nimbus (Paladin Devotion Lv 20
            # capstone). Shown at 1/1 even at Lv 6 (descriptive);
            # /use_holy_nimbus enforces the Lv 20+ gate before
            # allowing the spend. Mirror of v2.99.45 Mystic
            # Arcanum's "show the resource regardless of level"
            # pattern.
            {
                "key": "holy-nimbus-uses",
                "name": "Holy Nimbus",
                "current": 1, "max": 1, "reset": "long",
                "source": "paladin Lv 20 / Oath of Devotion",
                "class_slug": "paladin",
                "subclass_slug": "devotion",
                "desc": "Action (Lv 20+ Devotion): emanate sunlight in 30 ft for 1 minute. Enemies start turn in light → 10 radiant. Advantage on saves vs fiend/undead spells. Use /use_holy_nimbus to spend the charge.",
                "manual": False,
            },
            # v2.99.157 — Cleansing Touch (Paladin Lv 14+). RAW:
            # "you can use your action to end one spell on yourself
            # or on one willing creature that you touch. You can
            # use this feature a number of times equal to your
            # Charisma modifier (a minimum of once)." Caelan's CHA
            # mod is +3, so 3/3. Shown at 3/3 regardless of level;
            # /use_cleansing_touch enforces the Lv 14+ gate.
            {
                "key": "cleansing-touch-uses",
                "name": "Cleansing Touch",
                "current": 3, "max": 3, "reset": "long",
                "source": "paladin Lv 14",
                "class_slug": "paladin",
                "desc": "Action (Lv 14+): end one spell on yourself or a willing creature you touch. CHA mod uses per long rest (min 1). Use /use_cleansing_touch to spend a charge + name the buff to end.",
                "manual": False,
            },
        ],
        # v2.53.0: Aura of Protection (Paladin Lv 6+). Passive aura —
        # allies within 10 ft of Caelan add his CHA mod (+3 with CHA 16)
        # to all saving throws. Fires automatically server-side via
        # `_aura_of_protection_bonus` (v1 simplification: any PC in the
        # active battle's init counts as "within range"; 10 ft radius
        # check filed for follow-up).
        "class_features": [
            {
                "key": "aura-of-protection",
                "name": "Aura of Protection",
                "desc": "Passive — allies within 10 ft add Caelan's CHA mod (+3) to all saves. Fires automatically server-side on every save prompt that lands inside the active battle.",
            },
            # v2.55.0: Aura of Devotion (Oath of Devotion subclass,
            # Lv 7+). Passive — allies within 10 ft are immune to
            # being charmed. Fires server-side as a pre-install gate
            # in `/roll_request/{id}/respond`: when a failed Wis save
            # would install Charmed on an ally, AoD blocks the
            # install and broadcasts `feature_used(source=
            # aura-of-devotion)`.
            {
                "key": "aura-of-devotion",
                "name": "Aura of Devotion",
                "desc": "Passive (Oath of Devotion, Lv 7+) — allies within 10 ft are immune to being charmed. Fires automatically server-side when a failed save would install Charmed (e.g. Suggestion, Charm Person).",
            },
        ],
    }


def _paladin_vengeance_sheet(name: str) -> dict:
    """v2.158.56: demo Paladin Lv 3 (Oath of Vengeance) for the GM.
    Added so the v2.158.55 Vow of Enmity sheet button (Vengeance
    Paladin Lv 3+ Channel Divinity → /use_vow_of_enmity) is actually
    reachable in the live demo — Sir Caelan is Oath of Devotion, whose
    CD options filter out Vow of Enmity. This PC's `channel-divinity`
    resource carries `subclass_slug: "vengeance"` so the picker's
    class+subclass+min_level filter surfaces Vow of Enmity (and Abjure
    Enemy). Lv 3 is the Vow of Enmity unlock level. Distinct from
    Caelan so his Devotion-feature harness coverage stays untouched.
    """
    return {
        "class": "Paladin",
        "subclass": "Oath of Vengeance",
        "level": 3,
        "race": "Human",
        "alignment": "Lawful Neutral",
        "background": "Soldier",
        "abilities": {"STR": 16, "DEX": 10, "CON": 14, "INT": 10, "WIS": 11, "CHA": 16},
        "ac": 18,  # chain mail 16 + shield 2
        "speed": 30,
        "hp": {"current": 28, "max": 28, "temp": 0},  # 10 + 2×(6+CON 2) Lv 3 paladin
        "initiative_bonus": 0,
        "proficiency_bonus": 2,
        "hit_dice": {"current": 3, "max": 3},
        "class_hit_die": "d10",
        "class_spellcasting": "CHA",
        "saving_throws": {"WIS": True, "CHA": True},
        "skills": {
            "Intimidation": {"ability": "CHA", "proficient": True, "expertise": False},
            "Athletics":    {"ability": "STR", "proficient": True, "expertise": False},
            "Perception":   {"ability": "WIS", "proficient": True, "expertise": False},
        },
        # Dueling: +2 damage when wielding a single one-handed weapon
        # with no other weapon in hand (chosen at Paladin Lv 2).
        "fighting_style": "dueling",
        "attacks": [
            {"name": "Longsword", "attack_bonus": "+5", "damage": "1d8+5",
             "damage_type": "slashing", "range": "5 ft", "desc": "Versatile (1d10). +2 damage from Dueling."},
            {"name": "Javelin", "attack_bonus": "+5", "damage": "1d6+3",
             "damage_type": "piercing", "range": "30/120 ft", "desc": "Thrown."},
            # v2.158.104 — Magic-items Phase 7d demo fixture. Sun
            # Blade Longsword (RAW DMG p.205). +2 attack/damage RAW
            # baked in (Longsword +5/1d8+5 → +7/1d8+7), damage type
            # radiant (RAW). The +1d8 vs. undead rider fires from
            # section 6c via the v2.158.93 conditional-rider shape
            # (condition: target.creature_type == "undead"). The
            # bright-light bonus action / lit-state mechanics aren't
            # modeled v1 since they don't gate the damage rider.
            {"name": "Sun Blade", "attack_bonus": "+7",
             "damage": "1d8+7", "damage_type": "radiant",
             "range": "5 ft", "_slug": "sun-blade",
             "desc": "Rare longsword (versatile 1d8/1d10), attunement. +2 attack/damage, radiant damage type, +1d8 radiant vs. undead (RAW DMG p.205). Sheds bright light in a 15-ft radius when held."},
        ],
        # Oath of Vengeance Lv 3 always-prepared spells: Bane + Hunter's
        # Mark (PHB p.88), plus a couple of core paladin picks.
        "spells": [
            {"name": "Bane", "level": 1, "prepared": True, "_slug": "bane", "casting_time": "1 action",
             "save_ability": "CHA",
             "_subclass_granted": True, "_granted_by": "Oath of Vengeance"},
            {"name": "Hunter's Mark", "level": 1, "prepared": True, "_slug": "hunters-mark", "casting_time": "1 bonus action",
             "_subclass_granted": True, "_granted_by": "Oath of Vengeance"},
            {"name": "Cure Wounds", "level": 1, "prepared": True, "_slug": "cure-wounds", "casting_time": "1 action"},
            {"name": "Shield of Faith", "level": 1, "prepared": True, "_slug": "shield-of-faith", "casting_time": "1 bonus action"},
        ],
        "spell_slots": {
            "paladin": {
                "1": {"total": 3, "used": 0},
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
             "desc": "Divine focus — replaces material components for paladin spells."},
            # v2.158.104 — Magic-items Phase 7d demo fixture. Sun
            # Blade Longsword (rare, attunement). Dame Seraphine's
            # first magic item (1/3 attunement). RAW: deals radiant
            # damage instead of slashing (note damage_type="radiant"
            # on the attack entry). Always-on while attuned for the
            # +1d8 vs. undead rider (lit-state bright-light flavor
            # not gated by a `_lit` field — RAW: damage rider always
            # fires while attuned, lit or not).
            {"name": "Sun Blade", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "hands": 1, "damage": "1d8", "damage_type": "radiant",
             "properties": "versatile (1d10), magic",
             "_slug": "sun-blade",
             "desc": "Rare longsword, attunement. +2 attack/damage; radiant damage type; +1d8 radiant vs. undead (RAW DMG p.205). Bonus action: bright light in a 15-ft radius."},
        ],
        "resources": [
            {
                "key": "lay-on-hands",
                "name": "Lay on Hands",
                "current": 15, "max": 15, "reset": "long",
                "source": "paladin Lv 1",
                "class_slug": "paladin",
                "desc": "Touch-heal pool (5 × Lv = 15 HP). Refreshes on a long rest.",
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
                "subclass_slug": "vengeance",
                "desc": "Channel an oath effect (Abjure Enemy, Vow of Enmity). One use per short rest.",
                "manual": False,
            },
        ],
        "class_features": [
            {
                "key": "vow-of-enmity",
                "name": "Vow of Enmity",
                "desc": "Channel Divinity (bonus action) — utter a vow against a creature within 10 ft. Gain advantage on attack rolls against it for 1 minute. Fire via the Channel Divinity resource pill → /use_vow_of_enmity.",
            },
        ],
    }


def _bard_sheet(name: str) -> dict:
    """v2.15.1: demo Bard Lv 6 (College of Lore) for the GM. Bumped
    from Lv 5 (v2.14.1) so the v2.15.0 Magical Secrets toggle in the
    Browse Spells modal is exercisable in the live demo — Lore Bard
    Lv 6 unlocks Additional Magical Secrets (2 spells from any class
    list). Lyra's 2 picks are Fireball (Wizard L3) for the AoE damage
    Lore Bards don't otherwise get, and Counterspell (Wizard L3) for
    the reaction-counter slot. Both are tagged ``_via:
    "magical-secrets"`` so the sheet renders the 🪄 purple badge from
    spellRowHtml(). Cantrips still include Vicious Mockery for the
    demo's "pick a save-DC cantrip" flow.
    """
    return {
        "class": "Bard",
        "subclass": "College of Lore",
        "level": 6,
        "race": "Half-Elf",  # +2 CHA, +1 to two others
        "alignment": "Chaotic Good",
        "background": "Entertainer",
        "abilities": {"STR": 8, "DEX": 14, "CON": 13, "INT": 12, "WIS": 10, "CHA": 17},
        "ac": 14,  # studded leather 12 + DEX +2
        "speed": 30,
        "hp": {"current": 38, "max": 38, "temp": 0},  # 8 + 5×(avg 5 + CON +1)
        "initiative_bonus": 0,
        "proficiency_bonus": 3,
        "hit_dice": {"current": 6, "max": 6},
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
            # v2.158.97 — Magic-items Phase 6a demo fixture. Demon
            # Slayer Rapier (RAW DMG p.166). +1 attack/damage baked
            # in (Rapier +5 → +6, 1d8+2 → 1d8+3); the +2d6 vs. fiends
            # rider fires from section 6c via `creature_type` predicate
            # (same shape as Dragon Slayer v2.158.93). RAW's frighten-
            # on-hit DC 15 WIS save is deferred — that's a separate
            # save-handler hook, not a rider. The `_slug` field is the
            # rider gate.
            {"name": "Demon Slayer Rapier", "attack_bonus": "+6",
             "damage": "1d8+3", "damage_type": "piercing",
             "range": "5 ft", "_slug": "demon-slayer",
             "desc": "Rare rapier, attunement. +1 attack/damage; +2d6 piercing vs. fiends (DMG p.166)."},
        ],
        # Lv 6 Bard known spells: 4 cantrips, 9 leveled (per Bard table)
        # + 2 Magical Secrets picks from any class list (Lore Bard Lv 6
        # Additional Magical Secrets, RAW). ``casting_time`` tagged for
        # the v2.5.3 action-economy. ``_via: "magical-secrets"`` on the
        # last two entries drives the 🪄 purple badge in the spell row
        # (v2.15.0 spellRowHtml) so the GM can audit the cross-class picks.
        "spells": [
            {"name": "Vicious Mockery", "level": 0, "prepared": True, "_slug": "vicious-mockery", "casting_time": "1 action"},
            {"name": "Mage Hand", "level": 0, "prepared": True, "_slug": "mage-hand", "casting_time": "1 action"},
            {"name": "Minor Illusion", "level": 0, "prepared": True, "_slug": "minor-illusion", "casting_time": "1 action"},
            {"name": "Prestidigitation", "level": 0, "prepared": True, "_slug": "prestidigitation", "casting_time": "1 action"},
            {"name": "Healing Word", "level": 1, "prepared": True, "_slug": "healing-word", "casting_time": "1 bonus action"},
            {"name": "Cure Wounds", "level": 1, "prepared": True, "_slug": "cure-wounds", "casting_time": "1 action"},
            {"name": "Faerie Fire", "level": 1, "prepared": True, "_slug": "faerie-fire", "casting_time": "1 action"},
            {"name": "Heroism", "level": 1, "prepared": True, "_slug": "heroism", "casting_time": "1 action"},
            # v2.46.4 — Thunderwave exercises the T.7b.2 self-anchored
            # cube picker: 15 ft cube originating from the caster,
            # aimed via the cursor. Bard list, CON save vs thunder.
            {"name": "Thunderwave", "level": 1, "prepared": True, "_slug": "thunderwave",
             "casting_time": "1 action", "damage": "2d8", "save_ability": "CON",
             "desc": "15 ft cube from caster (aim with cursor), CON save DC 14 for half. 2d8 thunder. Push 10 ft on fail."},
            {"name": "Suggestion", "level": 2, "prepared": True, "_slug": "suggestion", "casting_time": "1 action"},
            {"name": "Invisibility", "level": 2, "prepared": True, "_slug": "invisibility", "casting_time": "1 action"},
            {"name": "Hold Person", "level": 2, "prepared": True, "_slug": "hold-person", "casting_time": "1 action"},
            # v2.44.2 — Shatter showcases the T.5b AoE picker at the
            # smaller 10 ft radius (2 squares vs Fireball's 20 ft / 4
            # squares), so GMs comparing the two see how the picker
            # scales. Bard list spell; CON save vs thunder damage.
            {"name": "Shatter", "level": 2, "prepared": True, "_slug": "shatter",
             "casting_time": "1 action", "damage": "3d8", "save_ability": "CON",
             "desc": "10 ft radius sphere within 60 ft, CON save DC 14 for half. 3d8 thunder. Inorganic targets have disadvantage on the save."},
            {"name": "Hypnotic Pattern", "level": 3, "prepared": True, "_slug": "hypnotic-pattern", "casting_time": "1 action"},
            {"name": "Dispel Magic", "level": 3, "prepared": True, "_slug": "dispel-magic", "casting_time": "1 action"},
            {"name": "Fireball", "level": 3, "prepared": True, "_slug": "fireball",
             "casting_time": "1 action", "class": "bard", "_via": "magical-secrets",
             "damage": "8d6", "save_ability": "DEX",
             "desc": "20 ft radius sphere, DEX save DC 14 for half. 8d6 fire."},
            {"name": "Counterspell", "level": 3, "prepared": True, "_slug": "counterspell",
             "casting_time": "1 reaction", "class": "bard", "_via": "magical-secrets",
             "desc": "Reaction when a creature within 60 ft casts a spell: their spell fails if its level ≤ 3, otherwise ability check DC 10 + spell level."},
            # v2.49.63 — Sleep. RAW Bard spell list. Routed via the
            # dedicated /cast_sleep endpoint with class_slug="bard".
            # Appended to preserve any spell-index assumptions in other
            # harness tests.
            {"name": "Sleep", "level": 1, "prepared": True, "_slug": "sleep", "casting_time": "1 action"},
            # v2.97.33 — Bane. RAW Bard spell list (also Cleric). CHA save,
            # 1 minute, concentration. Routed via /cast_spell; failed save
            # installs the 'baned' debuff via _SPELL_CONDITION_MAP. Appended
            # to preserve existing spell-index assumptions.
            {"name": "Bane", "level": 1, "prepared": True, "_slug": "bane", "casting_time": "1 action"},
            # v2.97.43 — Fear. RAW Bard L3 spell. WIS save, 1 minute,
            # concentration. Routed via /cast_spell; failed save installs
            # the 'frightened' condition via _SPELL_CONDITION_MAP. Lets the
            # v2.97.43 Heroism Frightened-immunity test exercise the new
            # gate (Heroism on Pip should now short-circuit a Fear install).
            # Appended to preserve existing spell-index assumptions.
            {"name": "Fear", "level": 3, "prepared": True, "_slug": "fear", "casting_time": "1 action"},
        ],
        "spell_slots": {
            "bard": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 3, "used": 0},
                "3": {"total": 3, "used": 0},  # Lv 6 Bard gains the third L3 slot
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
            # v2.78.0 Phase 5 — Cloak of Displacement demo item.
            # RAW (DMG p.158, rare wondrous item, attunement):
            # "While you wear this cloak, it projects an illusion that
            # makes you appear to be standing in a place near your
            # actual location, causing any creature to have disadvantage
            # on attack rolls against you. If you take damage, the
            # property ceases to function until the start of your next
            # turn. This property is suppressed while you are
            # incapacitated, restrained, or otherwise unable to move."
            # v1 surfaces the v2.78.0 generic item-reaction option on
            # the attack_targeted trigger so the GM can apply
            # disadvantage retroactively when the cloak hasn't been
            # suppressed yet. Auto-resolution + the "suppressed for 1
            # round on damage" tracking are filed for v3.
            {"name": "Cloak of Displacement", "type": "wondrous", "qty": 1,
             "equippable": True, "equipped": True, "attunement": True,
             "_slug": "cloak-of-displacement",
             "_reactions": [
                 {
                     "key": "item-cloak-displacement-advantage",
                     "trigger": "attack_targeted",
                     "label": "🌫 Cloak of Displacement — declare attacker had disadvantage",
                     "desc": "While the cloak is active (suppressed for 1 round after you take damage), attacks against you have disadvantage. GM adjudicates whether the trigger qualifies.",
                     "kind": "item",
                     "cost": "Reaction (informational — passive disadvantage)",
                 },
             ],
             "desc": "Wondrous item, rare (requires attunement). Attackers have disadvantage against you. Property suppressed for 1 round after you take damage."},
            {"name": "Lute", "type": "gear", "qty": 1,
             "desc": "Lyra's instrument — a polished six-string serving as her bardic focus. Lets her cast spells with material components without a separate component pouch."},
            {"name": "Entertainer's pack", "type": "gear", "qty": 1,
             "desc": "Backpack, bedroll, 2 costumes, 5 candles, 5 days rations, waterskin, disguise kit."},
            {"name": "Potion of Healing", "type": "consumable", "qty": 1,
             "consumable": True, "use_kind": "heal", "heal_dice": "2d4+2",
             "_slug": "potion-of-healing",
             "desc": "Drink to regain 2d4+2 HP. RAW: action. Campaign setting can flip to bonus action."},
            # v2.158.97 — Magic-items Phase 6a demo fixture. Demon
            # Slayer Rapier (rare, attunement). Paired with the
            # attack entry above via ``_slug``. Lyra now wears 2
            # attuned items (Cloak of Displacement + Demon Slayer).
            {"name": "Demon Slayer Rapier", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "hands": 1, "damage": "1d8", "damage_type": "piercing",
             "properties": "finesse, magic",
             "_slug": "demon-slayer",
             "desc": "Rare rapier, attunement. +1 attack/damage; while attuned, deals +2d6 piercing damage to fiends (RAW DMG p.166). Frighten-on-hit save deferred."},
        ],
        # v2.74.0 Phase 4a — Defensive Duelist feat for Lyra. RAW
        # (PHB p.166): reaction-based +PB AC against one melee hit
        # when wielding a finesse weapon (Lyra has Rapier equipped,
        # which is finesse). Picked Lyra over Pip because Pip's
        # Uncanny Dodge (Rogue Lv 5+) auto-fires on damage and burns
        # the reaction before the attack_targeted prompt can offer
        # DD as an alternative — Lyra (Bard) has no UD so the
        # reaction is free for DD. Wired through the v2.69.0
        # attack_targeted trigger event alongside Shield.
        "feats": [
            {"slug": "defensive-duelist", "name": "Defensive Duelist",
             "desc": "When wielding a finesse weapon and another creature hits you with a melee attack, you can use your reaction to add your proficiency bonus to your AC for that attack."},
        ],
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
        # v2.15.7: Lore Bard Lv 3 features that aren't resource counters
        # in their own right — they consume Bardic Inspiration. Cutting
        # Words rolls a BI die and subtracts the result from an enemy
        # roll within 60 ft. The Class abilities panel renders the
        # button; clicking POSTs /use_cutting_words (which decrements
        # the BI resource, rolls the die, marks the reaction slot,
        # announces in the roll log).
        "class_features": [
            {
                "key": "cutting-words",
                "name": "Cutting Words",
                "desc": "Reaction (Lore Lv 3): spend 1 Bardic Inspiration use to subtract a BI die from an enemy attack roll, ability check, or damage roll within 60 ft.",
            },
            # v2.54.0: Countercharm (Bard Lv 6). Action — install a
            # 1-round self-buff (countercharm-active) that grants
            # allies within 30 ft (any PC in init under v1
            # simplification) advantage on saves vs spells that
            # would install charmed or frightened. Routed through
            # /use_countercharm.
            {
                "key": "countercharm",
                "name": "Countercharm",
                "desc": "Action — allies within 30 ft get advantage on saves vs charmed / frightened until end of next turn. Re-perform with your action to maintain.",
            },
            # v2.99.44 — Superior Inspiration (Lv 20 capstone). PHB
            # p.54. When you roll initiative and have no uses of
            # Bardic Inspiration left, regain one. Auto-applied in
            # /battle PUT when the battle transitions inactive →
            # active, gated on class==bard AND level>=20 AND BI=0.
            # Descriptive entry until Lyra hits Lv 20 in a future
            # fixture bump.
            {
                "key": "superior-inspiration",
                "name": "Superior Inspiration (Lv 20)",
                "desc": "At 20th level, when you roll initiative and have no uses of Bardic Inspiration left, you regain one use. Auto-applied by the /battle PUT endpoint when class=Bard AND level>=20 AND BI current=0.",
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
            # v2.158.101 — Magic-items Phase 7a demo fixture. Vorpal
            # Scimitar (RAW DMG p.209). +3 attack/damage baked in
            # (Scimitar +6/1d6+3 → +9/1d6+6). The nat-20 decap fires
            # from the v2.158.101 post-hit handler via the catalog's
            # ``on_nat_20`` field. Vorpal RAW is "any sword" — the
            # Scimitar is a martial sword, perfect Druid fit. The
            # ``_slug`` field is the rider gate.
            {"name": "Vorpal Scimitar", "attack_bonus": "+9",
             "damage": "1d6+6", "damage_type": "slashing",
             "range": "5 ft", "_slug": "vorpal-sword",
             "desc": "Legendary scimitar, attunement. +3 attack/damage; on a natural 20 the target's head is cut off (RAW DMG p.209). Constructs / oozes / plants exempt."},
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
            # v2.158.101 — Magic-items Phase 7a demo fixture. Vorpal
            # Scimitar (legendary, attunement). Paired with the
            # attack entry above via ``_slug``. Mira goes from 0 to
            # 1 attuned item (cap 3 unchanged). The nat-20 decap
            # only fires from the catalog's ``on_nat_20`` entry —
            # no UI surface needed (a nat 20 is its own indicator).
            {"name": "Vorpal Scimitar", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "hands": 1, "damage": "1d6", "damage_type": "slashing",
             "properties": "finesse, light, magic",
             "_slug": "vorpal-sword",
             "desc": "Legendary scimitar, attunement. +3 attack/damage; on a natural 20 attack roll, cut off the target's head — the creature dies if it can't survive without a head (RAW DMG p.209). Constructs, oozes, and plants are exempt."},
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


def _warlock_sheet(name: str) -> dict:
    """v2.18.4: demo Warlock Lv 5 (The Fiend) for the GM. Added in
    Phase A.9 to wrap PHB class coverage. Unblocks per-feature work for
    Pact Magic (Warlock's unique short-rest spell-slot pool — 2/2 slots
    at Lv 5, both at L3, refresh on short rest — distinct from every
    other class's long-rest slot table), Dark One's Blessing (Fiend
    Lv 1: gain CHA mod + Warlock level temp HP when you reduce a
    creature to 0 HP — passive trigger, needs (B) damage roll-time
    intercept), Eldritch Invocations (Lv 5: 3 known, picked Agonizing
    Blast + Hex-warden + Devil's Sight — Agonizing Blast adds CHA mod
    to Eldritch Blast damage, the curated entry from the cantrip), and
    Mystic Arcanum (Lv 11 — wait on Lv 11+ Warlock). Bronze Dragonborn
    for the lightning breath weapon (1d6 racial save-based AoE — second
    racial resource counter pattern after Tiefling's Hellish Rebuke in
    v2.18.1). Color `#6a3a8e` (deep purple — fiendish / eldritch
    palette, distinct from Lyra's `#d977b8` magenta).
    """
    return {
        "class": "Warlock",
        "subclass": "The Fiend",
        "level": 5,
        "race": "Dragonborn",  # +2 STR, +1 CHA, Draconic Ancestry, Breath Weapon, damage resistance
        "alignment": "Chaotic Neutral",
        "background": "Charlatan",
        # Rolled stats post-racial: STR 13 (10+2 racial / dump), DEX 14,
        # CON 14, INT 10, WIS 12, CHA 17 (16+1 racial). Lv 4 ASI bumps
        # CHA to 18 — but we hold the ASI at +1 CHA + 1 feat slot for
        # potential Eldritch Adept (held in reserve).
        "abilities": {"STR": 13, "DEX": 14, "CON": 14, "INT": 10, "WIS": 12, "CHA": 17},
        # Studded leather 12 + DEX +2 = 14. No shield.
        "ac": 14,
        "speed": 30,
        # Lv 1 max d8 (8) + 4× avg d8 (5) + CON +2 × 5 = 8 + 20 + 10 = 38.
        "hp": {"current": 38, "max": 38, "temp": 0},
        # v2.99.20 — Bronze Dragonborn Damage Resistance: resistance
        # to lightning damage. RAW (PHB p.34, Draconic Ancestry
        # table): Bronze ancestor → lightning damage resistance.
        # Same shape as v2.99.18 Tiefling Hellish Resistance and
        # v2.99.19 Hill Dwarf Dwarven Resilience poison — sheet-level
        # damage_resistances list read by _resistance_halve.
        "damage_resistances": ["lightning"],
        "initiative_bonus": 2,  # DEX 14 mod
        "proficiency_bonus": 3,
        "hit_dice": {"current": 5, "max": 5},
        "class_hit_die": "d8",
        "class_spellcasting": "CHA",
        # Warlock prof saves are WIS + CHA.
        "saving_throws": {"WIS": True, "CHA": True},
        # Charlatan background grants Deception + Sleight of Hand;
        # Warlock Lv 1 picks two from a curated list (Arcana +
        # Intimidation fit the demonic-pact vibe).
        "skills": {
            "Arcana":          {"ability": "INT", "proficient": True, "expertise": False},
            "Intimidation":    {"ability": "CHA", "proficient": True, "expertise": False},
            "Deception":       {"ability": "CHA", "proficient": True, "expertise": False},
            "Sleight of Hand": {"ability": "DEX", "proficient": True, "expertise": False},
            # v2.99.143 — Beguiling Influence (Eldritch Invocation)
            # grants proficiency in Deception + Persuasion. Magnus
            # already has Deception from his Charlatan background;
            # this is the net add from the invocation.
            "Persuasion":      {"ability": "CHA", "proficient": True, "expertise": False, "source": "beguiling-influence"},
        },
        "attacks": [
            # v2.99.93 — Hex Warrior bound weapon. Magnus's Quarterstaff
            # is the bound weapon (touched after long rest, lacks the
            # two-handed property in its 1H grip — note RAW: must lack
            # the two-handed property, which Versatile satisfies in 1H
            # mode). With the Hex Warrior invocation, /attack swaps
            # STR (+1) for CHA (+3) on both attack roll AND damage,
            # appending a +2 delta to both. End-roll: 1d20+6 attack,
            # 1d6+3 damage (was 1d20+4 / 1d6+1).
            {"name": "Quarterstaff", "attack_bonus": "+4", "damage": "1d6+1",
             "damage_type": "bludgeoning", "range": "5 ft",
             "hex_warrior": True, "pact_weapon": True,
             "desc": "Versatile (1d8). Hex Warrior bound weapon (Lv 2+ invocation): uses CHA in place of STR for attack + damage — auto-applied at /attack time per v2.99.93. Also flagged ``pact_weapon: True`` for the v2.99.97 Lifedrinker invocation (Lv 12+ gate; the helper rejects at Magnus's Lv 5 until PATCH'd up). Magnus carries one mostly for poking around dark places; he'd rather Eldritch Blast you."},
            # v2.99.89 — Agonizing Blast +CHA mod is now auto-applied
            # at /attack time per _pc_agonizing_blast_bonus. Pre-v2.99.89
            # the +3 (CHA 17 mod) was pre-baked into the damage; v2.99.89
            # drops the baseline to "1d10" so the auto-apply doesn't
            # double-add. End-roll is identical for Magnus.
            {"name": "Eldritch Blast (cantrip)", "attack_bonus": "+6", "damage": "1d10",
             "damage_type": "force", "range": "120 ft",
             "desc": "Two beams at Lv 5 (Eldritch Blast scales: Lv 5 = 2 beams). Agonizing Blast invocation adds CHA mod (+3) to each beam's damage — auto-applied at /attack time. Spell attack, not weapon."},
        ],
        # Warlock spells: known list (not prepared). Lv 5 = 6 known
        # spells + 3 known cantrips. All slots at L3 (Pact Magic table).
        # Subclass-granted spells (The Fiend's Expanded Spells: Burning
        # Hands + Command at L1; Blindness/Deafness + Scorching Ray at
        # L2; Fireball + Stinking Cloud at L3) are always available
        # alongside the known-list picks — tagged via _subclass_granted.
        # Hex is the iconic Warlock concentration buff; Eldritch Blast
        # is the universal damage cantrip; Mage Armor lets Magnus get
        # AC 13 + DEX without armor (he's wearing studded leather
        # anyway, so it's situational). Burning Hands + Fireball from
        # The Fiend's bonus list cover the AoE damage role; Hellish
        # Rebuke (Warlock spell — distinct from Tiefling's racial in
        # v2.18.1) covers the reaction-counter slot.
        "spells": [
            # Cantrips (3 known)
            {"name": "Eldritch Blast", "level": 0, "prepared": True, "_slug": "eldritch-blast",
             "attack_bonus": "+6", "damage": "1d10",
             "casting_time": "1 action",
             "desc": "Lv 5 scaling: 2 beams. Agonizing Blast invocation adds CHA +3 to each beam."},
            {"name": "Prestidigitation", "level": 0, "prepared": True, "_slug": "prestidigitation",
             "casting_time": "1 action"},
            {"name": "Mage Hand", "level": 0, "prepared": True, "_slug": "mage-hand",
             "casting_time": "1 action"},
            # Warlock known spells (6 known at Lv 5)
            {"name": "Hex", "level": 1, "prepared": True, "_slug": "hex",
             "casting_time": "1 bonus action",
             "_concentration": True,
             "desc": "Concentration, up to 1 hour. Hex a creature: +1d6 necrotic damage on weapon/spell hits + disadvantage on a chosen ability check. Re-mark as a bonus action on creature death."},
            {"name": "Hellish Rebuke", "level": 1, "prepared": True, "_slug": "hellish-rebuke",
             "casting_time": "1 reaction",
             "desc": "Reaction (when damaged): the attacker takes 2d10 fire damage (DEX save half). Uses a Warlock spell slot (distinct from Tiefling's racial 1/long version)."},
            {"name": "Burning Hands", "level": 1, "prepared": True, "_slug": "burning-hands",
             "casting_time": "1 action",
             "_subclass_granted": True, "_granted_by": "The Fiend (Expanded Spells)",
             "desc": "15-ft cone, 3d6 fire (DEX save half). Subclass-granted: doesn't count against known."},
            {"name": "Scorching Ray", "level": 2, "prepared": True, "_slug": "scorching-ray",
             "casting_time": "1 action",
             "_subclass_granted": True, "_granted_by": "The Fiend (Expanded Spells)",
             "desc": "3 rays, each +6 spell attack for 2d6 fire. Subclass-granted."},
            {"name": "Mirror Image", "level": 2, "prepared": True, "_slug": "mirror-image",
             "casting_time": "1 action",
             "desc": "Three illusory duplicates protect you. Lasts 1 minute, no concentration."},
            {"name": "Counterspell", "level": 3, "prepared": True, "_slug": "counterspell",
             "casting_time": "1 reaction",
             "desc": "Reaction (when a creature within 60 ft casts a spell): interrupt the cast. L3 slot auto-succeeds for L3-and-below spells; L4+ needs ability check (DC 10 + spell level)."},
            {"name": "Fireball", "level": 3, "prepared": True, "_slug": "fireball",
             "casting_time": "1 action",
             "_subclass_granted": True, "_granted_by": "The Fiend (Expanded Spells)",
             "desc": "20-ft radius, 8d6 fire (DEX save half). Subclass-granted. Pairs with Hex for +1d6 necrotic on the marked target."},
            # v2.49.63 — Sleep. RAW on the Warlock spell list. Magnus
            # has only L3 slots (Pact Magic), so casts at L3 → 9d8
            # pool. Routed via /cast_sleep with class_slug="warlock".
            {"name": "Sleep", "level": 1, "prepared": True, "_slug": "sleep", "casting_time": "1 action"},
            # v2.99.422 — Mage Armor (the comment above always claimed
            # Magnus had it; now it's actually on the list). The Fiend's
            # known list; +3 AC while unarmored via the v2.99.422
            # _SPELL_BUFF_MAP entry. Index 11 (appended last so existing
            # spell indices used by other harness tests are unchanged).
            {"name": "Mage Armor", "level": 1, "prepared": True, "_slug": "mage-armor", "casting_time": "1 action"},
        ],
        # Pact Magic: 2 slots, ALL at the highest level Magnus can cast
        # (Lv 5 = L3). Refreshes on a SHORT rest (this is the unique
        # Warlock mechanic — Pact Magic is short-rest distinct from
        # every other caster's long-rest slots). The slot key
        # "warlock" is intentional — v2.16.0+'s spell-slot tracker
        # keys off class_slug for routing.
        # v2.99.25 — `reset: "short"` field on each Pact Magic slot.
        # The /rest short-rest branch reads this field per-slot to
        # decide whether to refresh on a short rest (parallel to the
        # existing resource-level `reset` field for short-rest
        # resources like Ki / Channel Divinity). Without this field
        # the short-rest handler doesn't touch spell slots at all,
        # so Pact Magic slots would only refresh on long rest —
        # breaking the Warlock's defining short-rest mechanic.
        "spell_slots": {
            "warlock": {
                "3": {"total": 2, "used": 0, "reset": "short"},
            },
        },
        "inventory": [
            {"name": "Quarterstaff", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "bludgeoning",
             "versatile": True, "properties": "versatile (1d8)",
             "_slug": "quarterstaff"},
            {"name": "Studded leather", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "light", "ac_value": 12,
             "_slug": "studded-leather"},
            {"name": "Arcane focus (orb of obsidian)", "type": "gear", "qty": 1,
             "desc": "Spellcasting focus — black volcanic glass. Channels Magnus's pact-bound magic; replaces material components for Warlock spells."},
            {"name": "Pact tome (Fiend's grimoire)", "type": "gear", "qty": 1,
             "desc": "Pact of the Tome would grant this as a Pact Boon; Magnus carries one as a flavor item ahead of taking Pact of the Tome at Lv 3 (or if you'd rather, he picked Pact of the Blade — held in reserve at Lv 3)."},
            {"name": "Disguise kit", "type": "gear", "qty": 1,
             "desc": "Charlatan background — 1 hour to assume a new identity."},
            {"name": "Marked card trinket", "type": "gear", "qty": 1,
             "desc": "Charlatan background trinket — Magnus's old swindler's tell."},
            {"name": "Potion of Healing", "type": "consumable", "qty": 2,
             "consumable": True, "use_kind": "heal", "heal_dice": "2d4+2",
             "_slug": "potion-of-healing",
             "desc": "Drink to regain 2d4+2 HP. RAW: action."},
            # v2.159.11 — Phase 8k: first cone-AoE magic item. Wand of
            # Fear (RAW DMG p.213 — rare, attunement required). 7
            # charges; spend 1 to project a 30-ft cone forcing each
            # creature in the cone to make a DC 15 WIS save or be
            # Frightened of the wielder for 1 minute. Regains 1d6+1
            # charges at dawn (Phase 4b dice-expression recharge).
            # Magnus's Fiend pact already trades in fear flavor — the
            # wand is on-theme for him. inventory_index 7.
            {"name": "Wand of Fear", "type": "gear", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "wand-of-fear",
             "desc": "RAW DMG p.213 (rare, attunement). 7 charges (regain 1d6+1 at dawn). Action: spend 1 charge to project a 30-ft cone — DC 15 WIS save or Frightened of you for 1 min (repeat save at end of each turn). Wired via /use_item_action with action_key=\"cast-fear\"."},
        ],
        # v2.18.4: 3 known Eldritch Invocations at Lv 5 (Warlock gets
        # Lv 2: 2 known; Lv 5: 3 known; Lv 7: 4 known...). Magnus's
        # picks: Agonizing Blast (cantrip-specific) + Devil's Sight
        # (see-through-magical-darkness rider; pairs with Darkness
        # spell for an "always-on advantage" combo) + Mask of Many
        # Faces (Disguise Self at-will). Captured as feats entries
        # since invocations don't have a dedicated sheet field today.
        "feats": [
            {"slug": "eldritch-invocation-agonizing-blast", "name": "Eldritch Invocation: Agonizing Blast",
             "desc": "When you cast Eldritch Blast, add your Charisma modifier to the damage of each beam it deals."},
            {"slug": "eldritch-invocation-devils-sight", "name": "Eldritch Invocation: Devil's Sight",
             "desc": "You can see normally in darkness, both magical and nonmagical, to a distance of 120 feet."},
            # v2.99.90 — Repelling Blast: on a successful Eldritch
            # Blast hit, push the target up to 10 ft away in a
            # straight line. Wired server-side via
            # _apply_repelling_blast_push at /attack time.
            {"slug": "eldritch-invocation-repelling-blast", "name": "Eldritch Invocation: Repelling Blast",
             "desc": "When you hit a creature with Eldritch Blast, you can push the creature up to 10 ft away in a straight line — auto-applied at /attack time per v2.99.90."},
            # v2.99.92 — Lance of Lethargy: on a successful Eldritch
            # Blast hit, reduce the target's speed by 10 ft until
            # end of caster's next turn. Installs a 1-round buff
            # via _apply_lance_of_lethargy at /attack time.
            {"slug": "eldritch-invocation-lance-of-lethargy", "name": "Eldritch Invocation: Lance of Lethargy",
             "desc": "When you hit a creature with Eldritch Blast, you can reduce that creature's speed by 10 ft until end of your next turn — buff auto-installed at /attack time per v2.99.92."},
            # v2.99.93 — Hex Warrior: swap STR/DEX for CHA on a
            # bound weapon's attack + damage rolls. Magnus's
            # Quarterstaff is flagged ``hex_warrior: True``;
            # _pc_hex_warrior_bonus appends the CHA - original_mod
            # delta to both atk_expr and damage_expr_raw at /attack
            # time.
            {"slug": "eldritch-invocation-hex-warrior", "name": "Eldritch Invocation: Hex Warrior",
             "desc": "Touch a weapon you're proficient with (lacking the two-handed property) after a long rest; you can use CHA in place of STR or DEX for attack + damage rolls with it — auto-applied at /attack time per v2.99.93."},
            # v2.99.97 — Lifedrinker: on a pact-weapon hit, the target
            # takes extra necrotic damage equal to CHA mod (min 1).
            # Requires Lv 12 + Pact of the Blade — auto-uplift fires
            # at /attack time per _pc_lifedrinker_bonus. Magnus's
            # Quarterstaff is flagged ``pact_weapon: True``;
            # descriptive at Lv 5 (the helper rejects on the Lv 12
            # gate until the harness PATCHes Magnus up).
            {"slug": "eldritch-invocation-lifedrinker", "name": "Eldritch Invocation: Lifedrinker",
             "desc": "Prerequisite: Lv 12+ Warlock, Pact of the Blade. When you hit a creature with your pact weapon, the creature takes extra necrotic damage equal to your CHA mod (minimum 1) — auto-applied at /attack time per v2.99.97."},
            # v2.99.137 — Mire the Mind. Once per long rest, cast
            # Slow using a Warlock spell slot. Magnus has L3 pact
            # slots so the cast is feasible; the resource entry
            # below carries the 1/long-rest gate. The cast routes
            # through /cast_slow with class_slug="warlock" +
            # via_invocation="mire-the-mind".
            {"slug": "eldritch-invocation-mire-the-mind", "name": "Eldritch Invocation: Mire the Mind",
             "desc": "Prerequisite: Lv 5+ Warlock. Once per long rest, cast Slow using a Warlock spell slot — routed via /cast_slow with via_invocation=\"mire-the-mind\" per v2.99.137."},
            # v2.99.138 — Eldritch Sight: cast Detect Magic at will.
            # Audit-only endpoint /use_eldritch_sight broadcasts the
            # cast; the full magic-aura visualization layer is
            # filed (no map magic-aura layer in SimpleVTT today).
            {"slug": "eldritch-invocation-eldritch-sight", "name": "Eldritch Invocation: Eldritch Sight",
             "desc": "At will: cast Detect Magic without expending a spell slot — routed via /use_eldritch_sight per v2.99.138. Aura-on-map visualization is filed."},
            # v2.99.141 — Ascendant Step: cast Levitate on self at
            # will. RAW prereq is Lv 9 Warlock — Magnus is Lv 5 in
            # the seed, but the demo seed grants the invocation for
            # /use_ascendant_step coverage. Audit-only endpoint;
            # vertical-position map plumbing is filed (SimpleVTT
            # has no 2D-with-altitude layer today).
            {"slug": "eldritch-invocation-ascendant-step", "name": "Eldritch Invocation: Ascendant Step",
             "desc": "At will: cast Levitate on yourself without expending a spell slot — routed via /use_ascendant_step per v2.99.141. RAW prereq Lv 9 Warlock."},
            # v2.99.142 — Sculptor of Flesh: 1/long-rest cast
            # Polymorph using a Warlock spell slot. RAW prereq Lv
            # 7 Warlock; demo seed grants it at Lv 5 for endpoint
            # coverage. Second consumer of the v2.99.140 invocation-
            # cast registry — proves the abstraction extends past
            # Mire the Mind to a different target spell.
            {"slug": "eldritch-invocation-sculptor-of-flesh", "name": "Eldritch Invocation: Sculptor of Flesh",
             "desc": "1/long rest: cast Polymorph using a Warlock spell slot — routed via /cast_polymorph with class_slug=\"warlock\" + via_invocation=\"sculptor-of-flesh\" per v2.99.142. RAW prereq Lv 7 Warlock. Target the transform via /transform with source=\"polymorph\" after the cast."},
            # v2.99.148 — Bewitching Whispers: 1/long-rest cast
            # Compulsion using a Warlock spell slot. RAW prereq Lv
            # 7 Warlock; demo seed grants at Lv 5 for endpoint
            # coverage. Third consumer of the v2.99.140 invocation-
            # cast registry.
            {"slug": "eldritch-invocation-bewitching-whispers", "name": "Eldritch Invocation: Bewitching Whispers",
             "desc": "1/long rest: cast Compulsion using a Warlock spell slot — routed via /cast_compulsion with class_slug=\"warlock\" + via_invocation=\"bewitching-whispers\" per v2.99.148. RAW prereq Lv 7 Warlock."},
            # v2.99.149 — Sign of Ill Omen: 1/long-rest cast
            # Bestow Curse using a Warlock spell slot. RAW prereq
            # Lv 5 Warlock — Magnus qualifies natively. Fourth
            # consumer of the v2.99.140 invocation-cast registry.
            {"slug": "eldritch-invocation-sign-of-ill-omen", "name": "Eldritch Invocation: Sign of Ill Omen",
             "desc": "1/long rest: cast Bestow Curse using a Warlock spell slot — routed via /cast_bestow_curse with class_slug=\"warlock\" + via_invocation=\"sign-of-ill-omen\" per v2.99.149. RAW prereq Lv 5 Warlock."},
            # v2.99.150 — Thief of Five Fates: 1/long-rest cast
            # Bane using a Warlock spell slot. No RAW level
            # prereq. Fifth consumer of the v2.99.140 invocation-
            # cast registry.
            {"slug": "eldritch-invocation-thief-of-five-fates", "name": "Eldritch Invocation: Thief of Five Fates",
             "desc": "1/long rest: cast Bane using a Warlock spell slot — routed via /cast_bane with class_slug=\"warlock\" + via_invocation=\"thief-of-five-fates\" per v2.99.150. RAW prereq Lv 2 Warlock."},
            # v2.99.143 — Beguiling Influence: passive proficiency in
            # Deception + Persuasion. Magnus's Charlatan background
            # already granted Deception, so the invocation's net add
            # is Persuasion (now stamped on the skills dict below
            # with source: "beguiling-influence"). The audit endpoint
            # /use_beguiling_influence is a chat-log declaration for
            # social-scene moments where the GM wants the table to
            # see the bonus claimed.
            {"slug": "eldritch-invocation-beguiling-influence", "name": "Eldritch Invocation: Beguiling Influence",
             "desc": "Passive: gain proficiency in Deception + Persuasion (CHA) — granted at seed. Audit declaration via /use_beguiling_influence per v2.99.143. RAW prereq Lv 2 Warlock."},
            # v2.99.144 — Eldritch Spear: extends Eldritch Blast's
            # range from 120 ft to 300 ft. Wired into the /attack
            # range-enforcement gate (v2.49.76 _check_cast_range) via
            # `_pc_eldritch_spear_range_ft` — the sheet-authored
            # range_str is overridden to "300 ft" when the
            # invocation is present and the attack is Eldritch Blast.
            {"slug": "eldritch-invocation-eldritch-spear", "name": "Eldritch Invocation: Eldritch Spear",
             "desc": "Eldritch Blast range extends to 300 ft (was 120 ft) — auto-applied at /attack time per v2.99.144. RAW prereq Lv 2 Warlock."},
            # v2.99.145 — Beast Speech: cast Speak with Animals at
            # will. Audit-only endpoint /use_beast_speech broadcasts
            # the cast. RAW prereq Lv 2 Warlock.
            {"slug": "eldritch-invocation-beast-speech", "name": "Eldritch Invocation: Beast Speech",
             "desc": "At will: cast Speak with Animals without expending a spell slot — routed via /use_beast_speech per v2.99.145. RAW prereq Lv 2 Warlock."},
            # v2.99.146 — Eyes of the Rune Keeper: passive, read all
            # writing. Audit endpoint /use_eyes_of_the_rune_keeper
            # broadcasts the cast. RAW prereq Lv 2 Warlock.
            {"slug": "eldritch-invocation-eyes-of-the-rune-keeper", "name": "Eldritch Invocation: Eyes of the Rune Keeper",
             "desc": "Passive: can read all writing (Druidic, Thieves' Cant, ancient glyphs, etc.) without Comprehend Languages — audit declaration via /use_eyes_of_the_rune_keeper per v2.99.146. RAW prereq Lv 2 Warlock."},
            # v2.99.147 — Whispers of the Grave: cast Speak with
            # Dead at will. RAW prereq Lv 9 Warlock; demo seed
            # grants at Lv 5 for endpoint coverage.
            {"slug": "eldritch-invocation-whispers-of-the-grave", "name": "Eldritch Invocation: Whispers of the Grave",
             "desc": "At will: cast Speak with Dead without expending a spell slot — routed via /use_whispers_of_the_grave per v2.99.147. RAW prereq Lv 9 Warlock."},
            # v2.99.152 — Visions of Distant Realms: cast Arcane
            # Eye at will. RAW prereq Lv 15 Warlock; demo seed
            # grants at Lv 5 for endpoint coverage. **20th and
            # final SRD Eldritch Invocation** — closes Magnus's
            # roster at 20/20.
            {"slug": "eldritch-invocation-visions-of-distant-realms", "name": "Eldritch Invocation: Visions of Distant Realms",
             "desc": "At will: cast Arcane Eye without expending a spell slot — routed via /use_visions_of_distant_realms per v2.99.152. RAW prereq Lv 15 Warlock."},
            {"slug": "eldritch-invocation-mask-of-many-faces", "name": "Eldritch Invocation: Mask of Many Faces",
             "desc": "You can cast Disguise Self at will, without expending a spell slot."},
        ],
        # v2.18.4: Warlock Lv 5 resources. Dragonborn Breath Weapon
        # (1/short-rest 2d6 lightning save-DC 13 — Magnus is a Bronze
        # Dragonborn). Dark One's Blessing (passive, no counter —
        # triggered when Magnus reduces an enemy to 0 HP, grants temp
        # HP = CHA mod + Warlock level). Dark One's Own Luck (Lv 6
        # Fiend feature — held until level-up, no entry at Lv 5).
        "resources": [
            {
                "key": "breath-weapon",
                "name": "Breath Weapon (Lightning)",
                "current": 1, "max": 1, "reset": "short",
                "source": "dragonborn racial",
                "class_slug": "dragonborn",
                "desc": "Action — 5×30-ft line of lightning, 2d6 damage, DEX save DC 13 (8 + PB + CON mod) for half. Bronze Dragonborn ancestry. Refreshes on short rest.",
                "manual": False,
            },
            # v2.99.137 — Mire the Mind 1/long-rest resource. /cast_slow
            # with via_invocation="mire-the-mind" gates on this row
            # being current >= 1 + decrements on cast.
            {
                "key": "mire-the-mind-uses",
                "name": "Mire the Mind",
                "current": 1, "max": 1, "reset": "long",
                "source": "warlock Lv 5 / Eldritch Invocation",
                "class_slug": "warlock",
                "desc": "1/long rest: cast Slow using a Warlock spell slot — routed via /cast_slow with class_slug=\"warlock\" + via_invocation=\"mire-the-mind\" per v2.99.137.",
                "manual": False,
            },
            # v2.99.142 — Sculptor of Flesh 1/long-rest resource.
            # /cast_polymorph with via_invocation="sculptor-of-flesh"
            # gates on this row being current >= 1 + decrements on
            # cast. Second consumer of the v2.99.140 invocation-cast
            # registry.
            {
                "key": "sculptor-of-flesh-uses",
                "name": "Sculptor of Flesh",
                "current": 1, "max": 1, "reset": "long",
                "source": "warlock Lv 7 / Eldritch Invocation",
                "class_slug": "warlock",
                "desc": "1/long rest: cast Polymorph using a Warlock spell slot — routed via /cast_polymorph with class_slug=\"warlock\" + via_invocation=\"sculptor-of-flesh\" per v2.99.142.",
                "manual": False,
            },
            # v2.99.148 — Bewitching Whispers 1/long-rest resource.
            # /cast_compulsion with via_invocation="bewitching-whispers"
            # gates on this row being current >= 1 + decrements on
            # cast. Third consumer of the v2.99.140 invocation-cast
            # registry.
            {
                "key": "bewitching-whispers-uses",
                "name": "Bewitching Whispers",
                "current": 1, "max": 1, "reset": "long",
                "source": "warlock Lv 7 / Eldritch Invocation",
                "class_slug": "warlock",
                "desc": "1/long rest: cast Compulsion using a Warlock spell slot — routed via /cast_compulsion with class_slug=\"warlock\" + via_invocation=\"bewitching-whispers\" per v2.99.148.",
                "manual": False,
            },
            # v2.99.149 — Sign of Ill Omen 1/long-rest resource.
            # /cast_bestow_curse with via_invocation="sign-of-ill-omen"
            # gates on this row being current >= 1 + decrements on
            # cast.
            {
                "key": "sign-of-ill-omen-uses",
                "name": "Sign of Ill Omen",
                "current": 1, "max": 1, "reset": "long",
                "source": "warlock Lv 5 / Eldritch Invocation",
                "class_slug": "warlock",
                "desc": "1/long rest: cast Bestow Curse using a Warlock spell slot — routed via /cast_bestow_curse with class_slug=\"warlock\" + via_invocation=\"sign-of-ill-omen\" per v2.99.149.",
                "manual": False,
            },
            # v2.99.150 — Thief of Five Fates 1/long-rest resource.
            # /cast_bane with via_invocation="thief-of-five-fates"
            # gates on this row being current >= 1 + decrements
            # on cast.
            {
                "key": "thief-of-five-fates-uses",
                "name": "Thief of Five Fates",
                "current": 1, "max": 1, "reset": "long",
                "source": "warlock Lv 2 / Eldritch Invocation",
                "class_slug": "warlock",
                "desc": "1/long rest: cast Bane using a Warlock spell slot — routed via /cast_bane with class_slug=\"warlock\" + via_invocation=\"thief-of-five-fates\" per v2.99.150.",
                "manual": False,
            },
            # v2.99.45 — Mystic Arcanum L6 (Warlock Lv 11+ capstone-ish
            # feature). RAW PHB p.108: choose one 6th-level Warlock
            # spell as your arcanum, castable 1/long-rest without
            # consuming a Pact Magic slot. The resource is shown at
            # 1/1 even at Lv 5 (descriptive); /use_mystic_arcanum
            # enforces the Lv 11+ gate before allowing the spend.
            # v2.99.86 — L7/L8/L9 tier resources added below. Each
            # is its own 1/long-rest resource so the per-tier gate
            # in /use_mystic_arcanum can read each independently.
            # Levels 13/15/17 enforced server-side.
            {
                "key": "mystic-arcanum-l6",
                "name": "Mystic Arcanum (L6)",
                "current": 1, "max": 1, "reset": "long",
                "source": "warlock Lv 11 / Mystic Arcanum",
                "class_slug": "warlock",
                "desc": "1/long rest (Lv 11+): cast a chosen 6th-level Warlock spell without expending a Pact Magic slot. Use /use_mystic_arcanum to spend the charge.",
                "manual": False,
            },
            {
                "key": "mystic-arcanum-l7",
                "name": "Mystic Arcanum (L7)",
                "current": 1, "max": 1, "reset": "long",
                "source": "warlock Lv 13 / Mystic Arcanum",
                "class_slug": "warlock",
                "desc": "1/long rest (Lv 13+): cast a chosen 7th-level Warlock spell without expending a Pact Magic slot.",
                "manual": False,
            },
            {
                "key": "mystic-arcanum-l8",
                "name": "Mystic Arcanum (L8)",
                "current": 1, "max": 1, "reset": "long",
                "source": "warlock Lv 15 / Mystic Arcanum",
                "class_slug": "warlock",
                "desc": "1/long rest (Lv 15+): cast a chosen 8th-level Warlock spell without expending a Pact Magic slot.",
                "manual": False,
            },
            {
                "key": "mystic-arcanum-l9",
                "name": "Mystic Arcanum (L9)",
                "current": 1, "max": 1, "reset": "long",
                "source": "warlock Lv 17 / Mystic Arcanum",
                "class_slug": "warlock",
                "desc": "1/long rest (Lv 17+): cast a chosen 9th-level Warlock spell without expending a Pact Magic slot.",
                "manual": False,
            },
            # v2.99.46 — Eldritch Master (Warlock Lv 20 capstone).
            # RAW PHB p.107: spend 1 minute entreating your patron
            # to regain all Pact Magic spell slots. 1/long rest.
            # Endpoint /use_eldritch_master enforces the Lv 20 gate.
            # Descriptive at Lv 5 (endpoint rejects with level_too_low).
            {
                "key": "eldritch-master-uses",
                "name": "Eldritch Master",
                "current": 1, "max": 1, "reset": "long",
                "source": "warlock Lv 20 / Eldritch Master",
                "class_slug": "warlock",
                "desc": "1/long rest (Lv 20): spend 1 minute entreating your patron to regain all Pact Magic spell slots. Use /use_eldritch_master to invoke.",
                "manual": False,
            },
            # v2.159.11 — Phase 8k: Wand of Fear charge counter (RAW
            # DMG p.213). 7 charges, regains 1d6+1 at dawn (Phase 4b
            # dice-expression recharge — long-rest path reads
            # ``charge_recovery``). Each /use_item_action cast-fear
            # decrements by 1. No upcast (single-cast-per-spend).
            {
                "key": "wand-of-fear",
                "name": "Wand of Fear",
                "current": 7, "max": 7, "reset": "long",
                "charge_recovery": "1d6+1",
                "source": "magic item — Wand of Fear",
                "class_slug": "item",
                "desc": "RAW DMG p.213. 7 charges. Spend 1 via /use_item_action (cast-fear): 30-ft cone, DC 15 WIS save or Frightened 1 min. Recovers 1d6+1 at dawn.",
                "manual": False,
            },
        ],
        # v2.18.4: clickable Class abilities buttons. The Fiend's Dark
        # One's Blessing is a passive trigger (no button) — the (B)
        # roll-time intercept needs to fire when Magnus's damage roll
        # reduces an enemy to 0 HP, granting temp HP. Today it's
        # descriptive on the sheet. The Eldritch Invocations are
        # toggles — Agonizing Blast applies passively to every
        # Eldritch Blast cast (needs the per-attack uplift picker to
        # surface its +CHA-to-each-beam rider); Devil's Sight is
        # informational; Mask of Many Faces is at-will Disguise Self
        # (no slot cost, no combat impact — flavor for the GM to
        # narrate). All filed for the Phase B invocation-routing
        # commit.
        "class_features": [
            {
                "key": "dark-ones-blessing",
                "name": "Dark One's Blessing",
                "desc": "Passive — when you reduce a hostile creature to 0 HP, you gain temp HP equal to your CHA mod + Warlock level (3 + 5 = 8). Triggers off damage rolls — needs (B) roll-time intercept to auto-apply.",
            },
            {
                "key": "agonizing-blast",
                "name": "Agonizing Blast",
                "desc": "Passive — when you cast Eldritch Blast, add CHA mod (+3) to each beam's damage. Already baked into the Eldritch Blast attack entry's +3 modifier — informational only.",
            },
            # v2.99.45 — Mystic Arcanum (Warlock Lv 11+). PHB p.108.
            # Daily 1/long-rest free cast of a chosen 6/7/8/9-th level
            # Warlock spell (Lv 11/13/15/17 respectively). v1 ship
            # covers the L6 tier only; L7/L8/L9 filed. Descriptive
            # entry until Magnus hits Lv 11 in a future fixture bump.
            {
                "key": "mystic-arcanum",
                "name": "Mystic Arcanum (Lv 11)",
                "desc": "Beginning at 11th level: choose one 6th-level Warlock spell as your arcanum; cast it 1/long rest without expending a Pact Magic slot. Lv 13/15/17 unlock L7/L8/L9 picks. Use /use_mystic_arcanum to spend the daily charge.",
            },
            # v2.99.46 — Eldritch Master (Warlock Lv 20 capstone).
            # PHB p.107. 1-minute ritual to refill all Pact Magic
            # slots, 1/long rest. Endpoint /use_eldritch_master
            # validates Lv 20 gate. Descriptive until Magnus hits
            # Lv 20 in a future fixture bump.
            {
                "key": "eldritch-master",
                "name": "Eldritch Master (Lv 20)",
                "desc": "At 20th level, spend 1 minute entreating your patron to regain all expended Pact Magic spell slots. Once used, must finish a long rest before invoking again. Use /use_eldritch_master to invoke.",
            },
        ],
        # Pact Boon (Lv 3): Pact of the Tome / Pact of the Blade / Pact
        # of the Chain. Magnus's pick is descriptive (Tome — held in
        # the grimoire inventory item) but not mechanically wired
        # because the Pact Boon features either grant additional
        # cantrips (Tome) or summon a familiar (Chain) or summon a
        # pact weapon (Blade) — all need follow-up infra. Filed.
        # Mystic Arcanum (Lv 11): unlocks one L6 spell castable
        # 1/long-rest. Wait on Lv 11+ Warlock fixture.
    }


def _ranger_sheet(name: str) -> dict:
    """v2.18.3: demo Ranger Lv 5 (Hunter) for the GM. Added in Phase A.8
    to unlock per-feature work for Hunter's Mark (concentration buff
    that adds 1d6 damage — needs the (C) buff slot + a concentration
    slot tracker), Favored Enemy (announce-only at the demo's RAW
    interpretation: "humanoids (bandits)" matches every NPC in the
    Tavern Brawl), Natural Explorer (announce-only: "forest"), and
    Hunter's Prey (Lv 3 Hunter pick: "Colossus Slayer" — +1d8 to a
    creature already below max HP). Variant Human for the bonus feat
    (Sharpshooter is the canonical Hunter pick but Hunter / Crossbow
    Expert / Sharpshooter are all viable; Sharpshooter chosen for the
    -5/+10 damage trade and the ignore-cover rider). Color `#5d7c4a`
    (forest green — distinct from Mira's `#4d9d6d` druid green +
    Bandit's red palette).
    """
    return {
        "class": "Ranger",
        "subclass": "Hunter",
        "level": 5,
        "race": "Variant Human",  # +1 to two abilities + 1 skill + 1 feat at Lv 1
        "alignment": "Neutral Good",
        "background": "Outlander",
        # Variant Human: +1 DEX, +1 WIS from the racial pick. Pre-racial
        # rolled 15 DEX 14 WIS → 16 DEX, 15 WIS. Lv 4 ASI bumps DEX to 18
        # (or could feat for Crossbow Expert — held in reserve).
        "abilities": {"STR": 12, "DEX": 18, "CON": 14, "INT": 10, "WIS": 15, "CHA": 8},
        # Studded leather 12 + DEX 4 = 16. No shield (two-handed bow build).
        "ac": 16,
        "speed": 30,
        # Lv 1 max d10 (10) + 4× avg d10 (6) + CON +2 × 5 = 10 + 24 + 10 = 44.
        "hp": {"current": 44, "max": 44, "temp": 0},
        "initiative_bonus": 4,  # DEX 18 mod
        "proficiency_bonus": 3,
        "hit_dice": {"current": 5, "max": 5},
        "class_hit_die": "d10",
        "class_spellcasting": "WIS",
        # Ranger prof saves are STR + DEX.
        "saving_throws": {"STR": True, "DEX": True},
        # Outlander background grants Athletics + Survival; Ranger Lv 1
        # picks three from a curated list (Perception + Stealth + Animal
        # Handling fit the wilderness scout vibe). Variant Human bonus
        # skill: Investigation.
        "skills": {
            "Athletics":       {"ability": "STR", "proficient": True, "expertise": False},
            "Survival":        {"ability": "WIS", "proficient": True, "expertise": False},
            "Perception":      {"ability": "WIS", "proficient": True, "expertise": False},
            "Stealth":         {"ability": "DEX", "proficient": True, "expertise": False},
            "Animal Handling": {"ability": "WIS", "proficient": True, "expertise": False},
            "Investigation":   {"ability": "INT", "proficient": True, "expertise": False},
        },
        "fighting_style": "archery",  # +2 to ranged attack rolls (auto-applied at /attack time per v2.99.83)
        "attacks": [
            # v2.99.83: Longbow attack_bonus was "+9" (DEX 18 mod +4
            # + Lv 5 PB +3 + Archery +2 pre-baked). The Archery +2
            # is now auto-applied server-side via
            # _pc_archery_bonus(sheet, attack); base bonus drops to
            # +7 (DEX 18 mod +4 + PB +3). End-roll is identical.
            {"name": "Longbow", "attack_bonus": "+7", "damage": "1d8+4",
             "damage_type": "piercing", "range": "150/600 ft",
             "desc": "Two-handed, heavy. Fighting Style: Archery (+2 to ranged attack — auto-applied at attack time, no pre-baked bonus). Sharpshooter feat: optional -5 attack / +10 damage trade + ignore cover up to total cover."},
            # v2.99.87 — off_hand flag + damage stripped of the DEX
            # mod baseline. RAW (PHB p.195): off-hand attacks don't
            # add the ability modifier to damage UNLESS the attacker
            # has the Two-Weapon Fighting style (PHB p.72). The
            # v2.99.87 _pc_two_weapon_fighting_bonus helper appends
            # the mod at /attack time when style == "two_weapon" +
            # attack.off_hand. Damage drops 1d6+4 → 1d6 to reflect
            # the no-TWF baseline; Rowan (Archery) takes 1d6 on this
            # weapon; a PATCH to "two_weapon" + this same Shortsword
            # rolls 1d6+4. The +4 is DEX mod (finesse weapon).
            {"name": "Shortsword", "attack_bonus": "+7", "damage": "1d6",
             "damage_type": "piercing", "range": "5 ft", "off_hand": True,
             "desc": "Finesse, light, off-hand. RAW: no ability mod on damage; Two-Weapon Fighting style adds it. Rowan keeps it for when enemies close — but his style is Archery, so the off-hand bite stays modest."},
            # v2.159.1 — Magic-items Phase 8a demo fixture. Longbow
            # firing an Arrow of Slaying (Giants). RAW DMG p.151: the
            # arrow is keyed to a creature kind — on hit vs. a giant,
            # the target makes a DC 17 CON save or takes +6d10
            # piercing (half on pass). The base attack stats are
            # Rowan's normal Longbow line; the `_slug` field is the
            # rider gate and the save fires via the v2.158.102 +
            # v2.159.1 on_hit_save substrate. Once used the arrow
            # becomes nonmagical RAW — qty decrement is Phase 8b.
            {"name": "Longbow (Arrow of Slaying — Giants)",
             "attack_bonus": "+7", "damage": "1d8+4",
             "damage_type": "piercing", "range": "150/600 ft",
             "_slug": "arrow-of-slaying-giants",
             "desc": "Magic arrow fired through the longbow. RAW DMG p.151: on hit vs. a giant, the target makes a DC 17 CON save or takes +6d10 piercing (half on a pass). The arrow becomes nonmagical after dealing the extra damage. Each shot uses one of Rowan's Arrows of Slaying stash."},
        ],
        # Hunter Ranger Lv 5: Lv 1-2 spells, 4/2 slots. Spells known is
        # the Ranger's known-not-prepared list (Lv 5 = 4 known).
        # Hunter's Mark is the iconic Ranger concentration buff; Cure
        # Wounds for the half-caster healer role; Goodberry for the
        # 10-HP-per-cast trail food; Pass Without Trace for the L2
        # group-stealth aura that exercises the buff-slot infrastructure
        # in the future.
        "spells": [
            {"name": "Hunter's Mark", "level": 1, "prepared": True, "_slug": "hunters-mark",
             "casting_time": "1 bonus action",
             "_concentration": True,
             "desc": "Bonus action — mark a creature. Add 1d6 damage on weapon hits + advantage on Perception/Survival checks to find it. Concentration, up to 1 hour."},
            {"name": "Cure Wounds", "level": 1, "prepared": True, "_slug": "cure-wounds",
             "casting_time": "1 action"},
            {"name": "Goodberry", "level": 1, "prepared": True, "_slug": "goodberry",
             "casting_time": "1 action"},
            {"name": "Pass Without Trace", "level": 2, "prepared": True, "_slug": "pass-without-trace",
             "casting_time": "1 action",
             "_concentration": True,
             "desc": "Concentration, up to 1 hour. +10 to Stealth checks + can't be tracked except by magical means for all allies within 30 ft."},
        ],
        "spell_slots": {
            "ranger": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 2, "used": 0},
            },
        },
        "inventory": [
            {"name": "Longbow", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 2,
             "damage": "1d8", "damage_type": "piercing",
             "range": "150/600 ft",
             "properties": "ammunition, heavy, two-handed",
             "_slug": "longbow"},
            {"name": "Arrows", "type": "ammunition", "qty": 40,
             "_slug": "arrow",
             "desc": "Standard quiver — Rowan tracks consumption manually in v1."},
            # v2.159.1 — Magic-items Phase 8a demo fixture. Arrow
            # of Slaying (Giants) — RAW DMG p.151 magic arrow. Qty 6
            # = a flavor-sized stash; qty decrement on use is filed
            # as Phase 8b polish (today RAW says "becomes nonmagical
            # after dealing the extra damage" but the demo doesn't
            # model the conversion). Paired with the attack entry
            # above via `_slug="arrow-of-slaying-giants"`. The
            # ammunition itself isn't attuneable (RAW ammunition
            # doesn't require attunement), so attuned/equipped fields
            # are omitted.
            {"name": "Arrows of Slaying (Giants)", "type": "ammunition",
             "qty": 6, "_slug": "arrow-of-slaying-giants",
             "desc": "Magic arrow, very rare. Keyed to giants — on hit vs. a giant, DC 17 CON save or take +6d10 piercing (half on pass). Becomes nonmagical after the special damage fires."},
            {"name": "Shortsword", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": False, "hands": 1,
             "damage": "1d6", "damage_type": "piercing",
             "properties": "finesse, light", "_slug": "shortsword"},
            {"name": "Studded leather", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "light", "ac_value": 12,
             "_slug": "studded-leather"},
            {"name": "Explorer's pack", "type": "gear", "qty": 1,
             "desc": "Backpack, bedroll, mess kit, tinderbox, 10 torches, 10 days rations, waterskin, 50 ft hempen rope."},
            {"name": "Hunting trap", "type": "gear", "qty": 1,
             "desc": "Outlander background — set for 1 action; STR check DC 13 to escape."},
            {"name": "Bowstring trinket", "type": "gear", "qty": 1,
             "desc": "Outlander background trinket — Rowan's first bowstring, kept wound around a wood charm."},
            {"name": "Potion of Healing", "type": "consumable", "qty": 2,
             "consumable": True, "use_kind": "heal", "heal_dice": "2d4+2",
             "_slug": "potion-of-healing",
             "desc": "Drink to regain 2d4+2 HP. RAW: action."},
        ],
        # v2.18.3: Variant Human bonus feat = Sharpshooter. Captured as
        # a feats entry; mechanical effects (ignore long-range disadvantage,
        # ignore cover up to total cover, -5/+10 trade option) wait on
        # the per-attack uplift picker (v2.16.0) extending to support
        # feat-driven uplifts. Today Sharpshooter is announce-only.
        "feats": [
            {"slug": "sharpshooter", "name": "Sharpshooter",
             "desc": "Ignore long-range disadvantage on ranged weapon attacks. Cover up to total cover doesn't impose disadvantage. Optional: -5 attack roll / +10 damage on a ranged weapon attack with a weapon you're proficient with."},
        ],
        # v2.18.3: Ranger Lv 5 resources. Favored Enemy (Lv 1) +
        # Natural Explorer (Lv 1) are announce-only — they don't have
        # numeric counters RAW. Hunter's Prey (Lv 3 Hunter pick:
        # Colossus Slayer) is a passive — +1d8 damage once per turn to
        # a creature already below max HP — also no counter RAW. The
        # one numeric Ranger resource at this level is no resource at
        # all; spell slots cover Hunter's Mark + Pass Without Trace.
        # Left empty intentionally; class_features carry the
        # announce-only buttons.
        "resources": [],
        # v2.18.3: clickable Class abilities buttons. Each is announce-only
        # in v1 — Favored Enemy + Natural Explorer fire /use_feature and
        # log a roll-chat line; Hunter's Mark routes through /cast_spell
        # via the standard spell button. Colossus Slayer is passive (no
        # button), captured in the description for the GM. All curated in
        # `_FEATURE_ECONOMY` since v2.6.0 with slot:'free' (announce-only).
        "class_features": [
            {
                "key": "favored-enemy",
                "name": "Favored Enemy (Humanoids)",
                "desc": "Free — advantage on Survival checks to track + Intelligence checks to recall info about humanoids. Pick when entering a combat with the Tavern Brawl — the bandits all qualify.",
            },
            {
                "key": "natural-explorer",
                "name": "Natural Explorer (Forest)",
                "desc": "Free — double proficiency on Intelligence + Wisdom checks involving forest terrain; party travels at normal pace while stealthing + can't be lost.",
            },
            {
                "key": "colossus-slayer",
                "name": "Colossus Slayer (Hunter's Prey)",
                "desc": "Passive — once per turn, add +1d6 damage to a creature already below its HP maximum. Hunter's Prey pick at Lv 3 (Hunter subclass).",
            },
            # v2.158.24 — Vanish (Ranger Lv 14+). Surfaces a curated
            # "🌑 Vanish" button in the Class abilities panel via the
            # v2.158.23 `_FEATURE_ECONOMY['vanish']` entry. Rowan is
            # Lv 7 by default, so clicking the button returns 409
            # level_too_low until she's PATCH-bumped to Lv 14
            # (see tests/harness/test_use_vanish.py for the fixture).
            # Listed unconditionally so the picker button is a
            # discoverable visual cue that the feature exists at Lv
            # 14 — the test fixture flow + any future Lv-14 demo
            # Ranger fixture (or homebrew bump) immediately unlocks
            # it without needing a separate class_features insertion.
            {
                "key": "vanish",
                "name": "Vanish (Lv 14+)",
                "desc": "Hide as a bonus action; can't be tracked by nonmagical means unless you choose to leave a trail. Routes to /use_vanish which installs the permanent `vanish-active` parameter buff (v2.158.21) and marks the bonus chip. Currently 409 level_too_low for Rowan (Lv 7); bump to Lv 14+ to unlock.",
            },
        ],
        # Hunter Lv 7 features (Defensive Tactics / Multiattack Defense /
        # Escape the Horde) and Lv 11 Multiattack pick wait on a Lv 7+
        # Ranger fixture or bump Rowan.
    }


def _barbarian_sheet(name: str) -> dict:
    """v2.18.2: demo Barbarian Lv 5 (Path of the Berserker) for the GM.
    Added in Phase A.7 to unlock per-feature work for Rage (the demo's
    first feature that depends on the (C) buff slot infrastructure —
    damage bonus + advantage on STR + resistance to physical damage
    while raging, all timed effects) + Reckless Attack (advantage on
    attack rolls flag, attacks vs you have advantage until next turn)
    + Brutal Critical (extra crit dice — extends the v2.16.0 attack
    picker with a crit-detection hook). Half-Orc for the canonical
    +STR + Savage Attacks (crit-die bonus) + Relentless Endurance
    (1/long-rest 1-HP save) racial. Color `#993333` (dark blood-red).

    v2.57.0: bumped Lv 5 → 7 to unlock Mindless Rage (Berserker Lv 6 —
    can't be charmed or frightened while raging) and Feral Instinct
    (Barbarian Lv 7 — advantage on initiative + act normally on
    surprised-round if raging). Proficiency stays +3 at Lv 5-8 so
    attack-bonus tests don't drift; rage uses bump 3 → 4 (Lv 6+).
    """
    return {
        "class": "Barbarian",
        "subclass": "Path of the Berserker",
        "level": 7,
        "race": "Half-Orc",  # +2 STR, +1 CON, Savage Attacks, Relentless Endurance, Darkvision, Menacing
        "alignment": "Chaotic Neutral",
        "background": "Outlander",
        # Pre-racial rolled: 15 STR, 14 CON, 14 DEX, 13 WIS, 8 INT, 8 CHA.
        # Half-Orc +2 STR (→ 17), +1 CON (→ 15). Lv 4 ASI +1 STR +1 CON
        # → STR 18, CON 16.
        "abilities": {"STR": 18, "DEX": 14, "CON": 16, "INT": 8, "WIS": 13, "CHA": 8},
        # Unarmored Defense: 10 + DEX +2 + CON +3 = 15. Two-handed
        # Greataxe means no shield, so this is the operating AC.
        "ac": 15,
        # Fast Movement (Lv 5): +10 ft speed when not in heavy armor.
        # Half-Orc base 30 + Fast Movement = 40.
        "speed": 40,
        # Lv 1 max d12 (12) + 6× avg d12 (7) + CON +3 × 7 = 12 + 42 + 21 = 75.
        # (v2.57.0: was 55 at Lv 5 — added 7 + 3 = 10 per level for Lv 6/7.)
        "hp": {"current": 75, "max": 75, "temp": 0},
        "initiative_bonus": 2,  # DEX 14 mod
        "proficiency_bonus": 3,  # +3 through Lv 5-8.
        "hit_dice": {"current": 7, "max": 7},
        "class_hit_die": "d12",
        # Barbarian prof saves are STR + CON.
        "saving_throws": {"STR": True, "CON": True},
        # Outlander background grants Athletics + Survival; Barbarian
        # Lv 1 picks two from a curated list (Intimidation +
        # Perception fit Krieger's "wandering hunter" vibe). Half-Orc
        # racial Intimidation proficiency stacks (but you only get
        # the proficiency once per skill RAW — the racial grant is
        # superseded by the class pick, no double-PB).
        "skills": {
            "Athletics":    {"ability": "STR", "proficient": True, "expertise": False},
            "Survival":     {"ability": "WIS", "proficient": True, "expertise": False},
            "Intimidation": {"ability": "CHA", "proficient": True, "expertise": False},
            "Perception":   {"ability": "WIS", "proficient": True, "expertise": False},
        },
        "attacks": [
            {"name": "Greataxe", "attack_bonus": "+7", "damage": "1d12+4",
             "damage_type": "slashing", "range": "5 ft",
             "desc": "Two-handed, heavy. While raging: +2 damage (Lv 1-8 Rage bonus). Half-Orc Savage Attacks: on a crit, add +1 die of weapon damage."},
            {"name": "Javelin", "attack_bonus": "+7", "damage": "1d6+4",
             "damage_type": "piercing", "range": "30/120 ft",
             "desc": "Thrown. Krieger carries 4 — has both melee and ranged options without dropping the Greataxe (he can stash it for the throw)."},
        ],
        # Barbarian is non-casting RAW; no spells / spell_slots fields.
        "inventory": [
            # v2.159.28 — carrying-capacity Phase 2a: backfilled
            # `weight_lb` per RAW PHB pp.149-151 / DMG p.178 / DMG p.187.
            # Krieger's full inventory now has real weight numbers so
            # the v2.159.27 carry meter renders a meaningful 78/270 lb
            # bar instead of 0/270 lb (Barbarian STR 18 → 270 cap).
            {"name": "Greataxe", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 2,
             "damage": "1d12", "damage_type": "slashing",
             "properties": "heavy, two-handed", "_slug": "greataxe",
             "weight_lb": 7},
            {"name": "Javelin", "type": "weapon", "qty": 4,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "piercing",
             "range": "30/120 ft", "properties": "thrown",
             "_slug": "javelin", "weight_lb": 2},
            {"name": "Explorer's pack", "type": "gear", "qty": 1,
             "weight_lb": 59,  # RAW PHB p.151
             "desc": "Backpack, bedroll, mess kit, tinderbox, 10 torches, 10 days rations, waterskin, 50 ft hempen rope."},
            {"name": "Staff trophy", "type": "gear", "qty": 1,
             "weight_lb": 1,
             "desc": "Outlander background trinket — gnarled staff carved with kill-marks from Krieger's hunts."},
            {"name": "Potion of Healing", "type": "consumable", "qty": 2,
             "consumable": True, "use_kind": "heal", "heal_dice": "2d4+2",
             "_slug": "potion-of-healing", "weight_lb": 0.5,
             "desc": "Drink to regain 2d4+2 HP. RAW: action."},
            # v2.159.3 — Magic-items Phase 8c demo fixture. Javelin
            # of Lightning (RAW DMG p.178). Different shape from
            # prior items: no inventory equipped state needed (it's
            # a thrown weapon), no attunement. The use is fired
            # via the v2.158.82 /use_item_action endpoint with the
            # new "hurl-lightning" action_key and a list of
            # target_combatant_ids the GM picks (the creatures in
            # the 5-ft × 120-ft line). State field ``_used_today``
            # starts False; flips True on use, blocks re-use until
            # next long rest (v2.159.3 dawn-reset).
            {"name": "Javelin of Lightning", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True,
             "hands": 1, "damage": "1d6", "damage_type": "piercing",
             "properties": "thrown, magic", "range": "30/120 ft",
             "_used_today": False, "weight_lb": 2,
             "_slug": "javelin-of-lightning",
             "desc": "Uncommon thrown magic weapon. Throw + speak the command word: lightning line 5 ft × 120 ft, DC 13 DEX save each creature in line (excluding caster + target) → 4d6 lightning (half on pass). The javelin lands at the target's feet and can be retrieved. Once used, nonmagical until next dawn (long rest)."},
        ],
        # v2.75.0 Phase 4d — Mage Slayer feat for Krieger. RAW (PHB
        # p.168): reaction-based melee attack against a creature
        # within 5 ft of you that casts a spell. Krieger's Greataxe
        # qualifies as the melee weapon. Wired through the v2.70.0
        # spell_cast_near trigger with a 5 ft gate via
        # context.distance_ft.
        "feats": [
            {"slug": "mage-slayer", "name": "Mage Slayer",
             "desc": "When a creature within 5 ft of you casts a spell, you can use your reaction to make a melee weapon attack against that creature. Plus advantage on saves against spells cast by creatures within 5 ft, and they have disadvantage on concentration checks for damage you deal."},
        ],
        # v2.18.2: Barbarian Lv 5 resources. Rage counter (3/long-rest
        # at Lv 3-5; scales to 4/long at Lv 6, 5/long at Lv 12, etc.).
        # The rage's mechanical effects (damage bonus / advantage on
        # STR / resistance) are timed — they last 1 minute or until
        # Krieger ends turn without attacking / taking damage. Modelling
        # them properly needs the (C) buff slot infrastructure to
        # auto-expire after 10 rounds and broadcast end-of-rage. Today
        # the rage class_features button announces the start; the GM
        # tracks duration manually.
        "resources": [
            {
                "key": "rage",
                "name": "Rage",
                "current": 4, "max": 4, "reset": "long",
                "source": "barbarian Lv 1",
                "class_slug": "barbarian",
                "desc": "Bonus action — enter rage: +2 damage on STR melee attacks (Lv 1-8), advantage on STR checks / saves, resistance to bludgeoning / piercing / slashing. Lasts 1 min or until turn ends without attacking / taking damage. 4 uses at Lv 6-11; refreshes on long rest.",
                "manual": False,
            },
            # v2.99.17 — Half-Orc Relentless Endurance. RAW (PHB
            # p.41): "When you are reduced to 0 hit points but not
            # killed outright, you can drop to 1 hit point instead.
            # You can't use this feature again until you finish a
            # long rest." Auto-fires when damage would set Krieger
            # to 0 HP (not killed outright by massive damage); the
            # server-side _apply_hp_change hook reads this resource
            # via `_pc_has_relentless_endurance_available(sheet)`
            # and clamps HP to 1.
            {
                "key": "relentless-endurance",
                "name": "Relentless Endurance",
                "current": 1, "max": 1, "reset": "long",
                "source": "Half-Orc",
                "desc": "When reduced to 0 HP but not killed outright, drop to 1 HP instead. 1/long rest.",
                "manual": False,
            },
        ],
        # v2.18.2: clickable Class abilities buttons. Rage's curated
        # entry is slot:'bonus' (since v2.6.0); clicking announces +
        # flips the Bns chip. Reckless Attack is slot:'free' (since
        # v2.6.0) — modifier toggle, not chip cost. v1 deviations:
        # rage announces but doesn't apply the damage bonus / advantage
        # / resistance (needs (C) buff slot); reckless-attack announces
        # but doesn't flag the next attack as advantaged or mark
        # attacks against Krieger as advantaged. Both deviations are
        # filed for the (C) infrastructure commit.
        "class_features": [
            {
                "key": "rage",
                "name": "Rage",
                "desc": "Bonus action — enter rage: damage bonus + advantage on STR + resistance to physical damage. Lasts 1 min.",
            },
            {
                "key": "reckless-attack",
                "name": "Reckless Attack",
                "desc": "Free — declare on your first attack: gain advantage on STR melee attacks this turn; attacks against you have advantage until your next turn.",
            },
            # v2.52.0: Danger Sense (Barbarian Lv 2+). Passive — when
            # a Dex save is rolled vs an effect you can see, the d20
            # rolls with advantage. Fires automatically server-side
            # in `_pc_has_danger_sense_on_dex_save` (the /place_aoe
            # PC branch + the cast_spell roll_request creation paths
            # check this gate). No /use endpoint or button.
            {
                "key": "danger-sense",
                "name": "Danger Sense",
                "desc": "Passive — advantage on Dex saves vs effects you can see (traps, spells). Fires automatically server-side on Dex-save spells like Fireball.",
            },
            # v2.54.1: Fast Movement (Barbarian Lv 5+). Passive
            # +10 ft speed while not in heavy armor. Already baked
            # into Krieger's listed speed (40 ft = 30 base + 10
            # Fast Movement). Descriptive entry for the sheet.
            {
                "key": "fast-movement",
                "name": "Fast Movement",
                "desc": "Passive (Lv 5+) — +10 ft speed while not in heavy armor. Already baked into Krieger's listed speed (40 ft).",
            },
            # v2.57.0: Mindless Rage (Berserker Lv 6+). Charm/fright
            # immunity *while raging* — server-side gate at the
            # condition-install site in /roll_request/{id}/respond
            # short-circuits the buff install when the saver has an
            # active rage buff AND the failing save would install
            # charmed OR frightened. Pre-install gate (the save still
            # fails RAW); broadcast surfaces the immunity.
            {
                "key": "mindless-rage",
                "name": "Mindless Rage",
                "desc": "Passive (Lv 6+) — can't be charmed or frightened while raging. Fires automatically server-side when a save vs Suggestion / Fear / etc. fails during rage.",
            },
            # v2.57.0: Feral Instinct (Barbarian Lv 7+). Advantage on
            # initiative rolls + can act normally on a surprised round
            # if Krieger rages (no action) on his turn. Initiative
            # advantage doesn't have a wired-in hook today — initiative
            # is rolled out-of-band in v1. Filed as descriptive; surfaces
            # in the sheet so the player remembers to flag it manually.
            {
                "key": "feral-instinct",
                "name": "Feral Instinct",
                "desc": "Passive (Lv 7+) — advantage on initiative rolls + can act normally on a surprised round (if you rage on your turn). Initiative rolled out-of-band today; flag manually for now.",
            },
        ],
        # Frenzy is the Berserker subclass feature (Lv 3): bonus
        # action while raging, +1 weapon attack on every subsequent
        # turn, but exhaustion when rage ends. Filed as a future
        # class_features entry after the rage state machine ships.
        # Half-Orc Relentless Endurance (1/long-rest, drop to 1 HP
        # instead of 0) is a passive — descriptive on the sheet
        # today; would auto-trigger in _apply_hp_change when the
        # (B) roll-time intercept lands a hook to consult resources.
    }


def _barbarian_beast_sheet(name: str) -> dict:
    """v2.158.60: demo Barbarian Lv 5 (Path of the Beast, TCE) — the
    14th demo PC. Krieger Stonefist is Path of the Berserker, whose
    class-features list has no Form of the Beast entry, so the
    v2.158.59 Form of the Beast sheet button (Path of the Beast
    Barbarian Lv 3+ → /use_form_of_the_beast) was unreachable in the
    live demo. This PC carries a `form-of-the-beast` class feature so
    the button renders + the Bite/Claws/Tail picker is verifiable.

    A distinct PC from Krieger so his Berserker coverage (Frenzy /
    Mindless Rage / Feral Instinct) stays untouched — mirrors the
    v2.158.56 Vengeance Paladin decision (a new PC rather than
    converting Sir Caelan).
    """
    return {
        "class": "Barbarian",
        "subclass": "Path of the Beast",
        "level": 5,
        "race": "Human",
        "alignment": "Chaotic Good",
        "background": "Outlander",
        "abilities": {"STR": 17, "DEX": 14, "CON": 16, "INT": 8, "WIS": 12, "CHA": 10},
        # Unarmored Defense: 10 + DEX +2 + CON +3 = 15.
        "ac": 15,
        # Fast Movement (Lv 5): base 30 + 10 = 40.
        "speed": 40,
        # Lv 1 max d12 (12) + 4× avg d12 (7) + CON +3 × 5 = 12 + 28 + 15 = 55.
        "hp": {"current": 55, "max": 55, "temp": 0},
        "initiative_bonus": 2,
        "proficiency_bonus": 3,
        "hit_dice": {"current": 5, "max": 5},
        "class_hit_die": "d12",
        "saving_throws": {"STR": True, "CON": True},
        "skills": {
            "Athletics":    {"ability": "STR", "proficient": True, "expertise": False},
            "Survival":     {"ability": "WIS", "proficient": True, "expertise": False},
            "Intimidation": {"ability": "CHA", "proficient": True, "expertise": False},
            "Perception":   {"ability": "WIS", "proficient": True, "expertise": False},
        },
        "attacks": [
            {"name": "Greataxe", "attack_bonus": "+6", "damage": "1d12+3",
             "damage_type": "slashing", "range": "5 ft",
             "desc": "Two-handed, heavy. While raging: +2 damage (Lv 1-8 Rage bonus)."},
            {"name": "Javelin", "attack_bonus": "+6", "damage": "1d6+3",
             "damage_type": "piercing", "range": "30/120 ft",
             "desc": "Thrown."},
        ],
        "inventory": [
            {"name": "Greataxe", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 2,
             "damage": "1d12", "damage_type": "slashing",
             "properties": "heavy, two-handed", "_slug": "greataxe"},
            {"name": "Javelin", "type": "weapon", "qty": 4,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "piercing",
             "range": "30/120 ft", "properties": "thrown",
             "_slug": "javelin"},
            {"name": "Explorer's pack", "type": "gear", "qty": 1,
             "desc": "Backpack, bedroll, mess kit, tinderbox, 10 torches, 10 days rations, waterskin, 50 ft hempen rope."},
        ],
        "resources": [
            {
                "key": "rage",
                "name": "Rage",
                "current": 3, "max": 3, "reset": "long",
                "source": "barbarian Lv 1",
                "class_slug": "barbarian",
                "desc": "Bonus action — enter rage: +2 damage on STR melee attacks (Lv 1-8), advantage on STR checks / saves, resistance to bludgeoning / piercing / slashing. 3 uses at Lv 3-5; refreshes on long rest.",
                "manual": False,
            },
        ],
        "class_features": [
            {
                "key": "rage",
                "name": "Rage",
                "desc": "Bonus action — enter rage: damage bonus + advantage on STR + resistance to physical damage. Lasts 1 min.",
            },
            {
                "key": "reckless-attack",
                "name": "Reckless Attack",
                "desc": "Free — declare on your first attack: gain advantage on STR melee attacks this turn; attacks against you have advantage until your next turn.",
            },
            {
                "key": "danger-sense",
                "name": "Danger Sense",
                "desc": "Passive — advantage on Dex saves vs effects you can see (traps, spells). Fires automatically server-side on Dex-save spells like Fireball.",
            },
            {
                "key": "fast-movement",
                "name": "Fast Movement",
                "desc": "Passive (Lv 5+) — +10 ft speed while not in heavy armor. Already baked into the listed speed (40 ft).",
            },
            # v2.158.60: Form of the Beast (Path of the Beast Lv 3+,
            # TCE). The Use button routes to /use_form_of_the_beast
            # (v2.158.59 wiring) and opens a Bite/Claws/Tail picker;
            # the chosen form installs the natural-weapon buff that the
            # v2.158.25 natural-weapons panel + bonus claw attack read.
            {
                "key": "form-of-the-beast",
                "name": "Form of the Beast",
                "desc": "When you enter your rage, manifest a natural weapon as part of the bonus action — Bite (1d8 piercing, self-heal), Claws (1d6 slashing, extra attack), or Tail (1d8 piercing, 10-ft reach, reaction AC). Lasts until your rage ends.",
            },
        ],
    }


def _monk_drunken_sheet(name: str) -> dict:
    """v2.158.62: demo Monk Lv 5 (Way of the Drunken Master, XGE) —
    the 15th demo PC. Kael Brightleaf is Way of the Open Hand, whose
    class-features list has no Drunken Technique entry, so the
    v2.158.61 Drunken Technique sheet button (Way of the Drunken
    Master Monk Lv 3+ → /use_drunken_technique) was unreachable in the
    live demo. This PC carries a `drunken-technique` class feature so
    the button renders + the Disengage + 10 ft speed rider install is
    verifiable.

    A distinct PC from Kael so his Open Hand coverage (Flurry / Patient
    Defense / Step of the Wind / Wholeness of Body / Stillness of Mind)
    stays untouched — mirrors the v2.158.60 Beast Barbarian decision (a
    new PC rather than converting the existing one).
    """
    return {
        "class": "Monk",
        "subclass": "Way of the Drunken Master",
        "level": 5,
        "race": "Human",
        "alignment": "Chaotic Good",
        "background": "Folk Hero",
        "abilities": {"STR": 12, "DEX": 16, "CON": 14, "INT": 10, "WIS": 15, "CHA": 8},
        # Unarmored Defense: 10 + DEX +3 + WIS +2 = 15.
        "ac": 15,
        # Base 30 + Unarmored Movement +10 (Lv 2+) = 40.
        "speed": 40,
        # Lv 1 max d8 (8) + 4× avg d8 (5) + CON +2 × 5 = 8 + 20 + 10 = 38.
        "hp": {"current": 38, "max": 38, "temp": 0},
        "initiative_bonus": 3,  # DEX 16 mod
        "proficiency_bonus": 3,  # PB +3 at Lv 5
        "hit_dice": {"current": 5, "max": 5},
        "class_hit_die": "d8",
        "saving_throws": {"STR": True, "DEX": True},
        "skills": {
            "Acrobatics": {"ability": "DEX", "proficient": True, "expertise": False},
            "Performance": {"ability": "CHA", "proficient": True, "expertise": False},
            "Animal Handling": {"ability": "WIS", "proficient": True, "expertise": False},
            "Survival": {"ability": "WIS", "proficient": True, "expertise": False},
        },
        "attacks": [
            {"name": "Unarmed Strike", "attack_bonus": "+6", "damage": "1d6+3",
             "damage_type": "bludgeoning", "range": "5 ft",
             "desc": "Martial Arts: DEX replaces STR; Lv 5 die is 1d6. Counts as a monk weapon (qualifies for Flurry of Blows + Stunning Strike)."},
            {"name": "Quarterstaff (Martial Arts)", "attack_bonus": "+6", "damage": "1d6+3",
             "damage_type": "bludgeoning", "range": "5 ft",
             "desc": "Versatile (1d8 two-handed). Martial Arts allows DEX in place of STR. Counts as a monk weapon."},
        ],
        "inventory": [
            {"name": "Quarterstaff", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "bludgeoning",
             "versatile": True, "properties": "versatile (1d8), monk weapon",
             "_slug": "quarterstaff"},
            {"name": "10 darts", "type": "weapon", "qty": 10,
             "equippable": True, "equipped": False, "hands": 1,
             "damage": "1d4", "damage_type": "piercing",
             "range": "20/60 ft", "properties": "finesse, thrown, monk weapon",
             "_slug": "dart"},
            {"name": "Explorer's pack", "type": "gear", "qty": 1,
             "desc": "Backpack, bedroll, mess kit, tinderbox, 10 torches, 10 days rations, waterskin, 50 ft hempen rope."},
            {"name": "Jug of cheap wine", "type": "gear", "qty": 1,
             "desc": "Folk Hero flair — the prop the drunken weave hides behind."},
        ],
        "feats": [],
        "resources": [
            {
                "key": "ki",
                "name": "Ki",
                "current": 5, "max": 5, "reset": "short",
                "source": "monk Lv 2",
                "class_slug": "monk",
                "desc": "Spend 1 Ki for Flurry of Blows / Patient Defense / Step of the Wind (bonus action). 5 points at Lv 5; refreshes on short rest.",
                "manual": False,
            },
        ],
        "class_features": [
            {
                "key": "flurry-of-blows",
                "name": "Flurry of Blows",
                "desc": "Bonus action — spend 1 Ki to make two unarmed strikes (1d6+DEX each at Lv 5).",
            },
            {
                "key": "patient-defense",
                "name": "Patient Defense",
                "desc": "Bonus action — spend 1 Ki to take the Dodge action.",
            },
            {
                "key": "step-of-the-wind",
                "name": "Step of the Wind",
                "desc": "Bonus action — spend 1 Ki to take the Disengage or Dash action; jump distance doubles for the turn.",
            },
            # v2.158.62: Drunken Technique (Way of the Drunken Master
            # Lv 3+, XGE). The Use button routes to
            # /use_drunken_technique (v2.158.61 wiring) and installs the
            # 1-turn rider buff — Disengage + 10 ft speed until end of
            # turn — that the OA-prompt flow + `effective_speed_walk`
            # read.
            {
                "key": "drunken-technique",
                "name": "Drunken Technique",
                "desc": "Whenever you use Flurry of Blows, you gain the benefit of the Disengage action and your walking speed increases by 10 ft until the end of the current turn.",
            },
        ],
    }


def _monk_sheet(name: str) -> dict:
    """v2.18.0: demo Monk Kael Brightleaf (Way of the Open Hand).
    Bumped to Lv 6 in v2.49.227 to unlock Wholeness of Body. Bumped to
    Lv 7 in v2.49.229 to unlock Stillness of Mind (also unlocks
    Evasion + Ki-Empowered Strikes for future commits). Added in
    Phase A.5
    to unlock per-feature work for Ki spending (Flurry of Blows /
    Patient Defense / Step of the Wind — all bonus-action spend-1-Ki
    options curated in `_FEATURE_ECONOMY` since v2.6.0). Wood Elf for
    the canonical "DEX + WIS + speed" Monk build. Unarmored Defense
    (AC 10 + DEX + WIS) and Unarmored Movement (+10 at Lv 5) compose
    with Wood Elf's Fleet of Foot (base 35) → total speed 45. Color
    `#ff8c42` (saffron / monastic orange-red) — distinct from every
    existing PC + NPC palette.
    """
    return {
        "class": "Monk",
        "subclass": "Way of the Open Hand",
        "level": 7,
        "race": "Wood Elf",  # +2 DEX, +1 WIS, Fleet of Foot (speed 35)
        "alignment": "Lawful Good",
        "background": "Hermit",
        # Rolled stats post-racial: STR 12 / DEX 18 / CON 14 / INT 10 /
        # WIS 15 / CHA 8. Wood Elf +2 DEX (→ 18) + +1 WIS (→ 15) from
        # pre-racial 16 DEX + 14 WIS rolled. Lv 4 ASI bumps DEX to 18
        # (or could be a feat like Mobile — held in reserve).
        "abilities": {"STR": 12, "DEX": 18, "CON": 14, "INT": 10, "WIS": 15, "CHA": 8},
        # Unarmored Defense: AC = 10 + DEX mod + WIS mod = 10 + 4 + 2 = 16.
        "ac": 16,
        # Wood Elf Fleet of Foot (base 35) + Monk Unarmored Movement
        # (+10 at Lv 5) = 45 ft. Notable demo: Kael can dash 90 ft in
        # one turn with Step of the Wind.
        "speed": 45,
        # Lv 1 max d8 (8) + 6× avg d8 (5) + CON +2 × 7 = 8 + 30 + 14 = 52
        # (Lv 7 bump v2.49.229: prior Lv 6 was 8 + 25 + 12 = 45).
        "hp": {"current": 52, "max": 52, "temp": 0},
        "initiative_bonus": 4,  # DEX 18 mod
        "proficiency_bonus": 3,  # PB +3 holds from Lv 5-8
        "hit_dice": {"current": 7, "max": 7},
        "class_hit_die": "d8",
        # Monk prof saves are STR + DEX.
        "saving_throws": {"STR": True, "DEX": True},
        # Hermit background grants Medicine + Religion; Monk Lv 1 picks
        # two from a curated list (Acrobatics + Insight). Wood Elf
        # racial Perception proficiency on top.
        "skills": {
            "Acrobatics":  {"ability": "DEX", "proficient": True, "expertise": False},
            "Insight":     {"ability": "WIS", "proficient": True, "expertise": False},
            "Medicine":    {"ability": "WIS", "proficient": True, "expertise": False},
            "Religion":    {"ability": "INT", "proficient": True, "expertise": False},
            "Perception":  {"ability": "WIS", "proficient": True, "expertise": False},
        },
        # Martial Arts (Lv 1): can use DEX instead of STR for monk
        # weapons + unarmed strikes; unarmed damage scales by level
        # (Lv 5: 1d6). At Lv 5 Quarterstaff (monk weapon) also deals
        # 1d8 versatile and Martial Arts lets it use DEX.
        "attacks": [
            {"name": "Unarmed Strike", "attack_bonus": "+7", "damage": "1d6+4",
             "damage_type": "bludgeoning", "range": "5 ft",
             "desc": "Martial Arts: DEX replaces STR on unarmed strikes; Lv 5 die is 1d6. Counts as a monk weapon so it qualifies for Flurry of Blows + Stunning Strike."},
            {"name": "Quarterstaff (Martial Arts)", "attack_bonus": "+7", "damage": "1d6+4",
             "damage_type": "bludgeoning", "range": "5 ft",
             "desc": "Versatile (1d8 two-handed, 1d6 one-handed). Martial Arts allows DEX in place of STR. Counts as a monk weapon. Two-handed grip if not throwing or pairing with an off-hand."},
        ],
        # Monk is non-casting RAW; no spells / spell_slots fields.
        "inventory": [
            {"name": "Quarterstaff", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "bludgeoning",
             "versatile": True, "properties": "versatile (1d8), monk weapon",
             "_slug": "quarterstaff"},
            {"name": "10 darts", "type": "weapon", "qty": 10,
             "equippable": True, "equipped": False, "hands": 1,
             "damage": "1d4", "damage_type": "piercing",
             "range": "20/60 ft", "properties": "finesse, thrown, monk weapon",
             "_slug": "dart"},
            {"name": "Explorer's pack", "type": "gear", "qty": 1,
             "desc": "Backpack, bedroll, mess kit, tinderbox, 10 torches, 10 days rations, waterskin, 50 ft hempen rope."},
            {"name": "Herbalism kit", "type": "gear", "qty": 1,
             "desc": "Hermit background — pouches, mortar + pestle, dried herbs."},
            {"name": "Scroll case with prayers", "type": "gear", "qty": 1,
             "desc": "Hermit background trinket — Kael's reflections from years in the wilderness."},
            {"name": "Potion of Healing", "type": "consumable", "qty": 1,
             "consumable": True, "use_kind": "heal", "heal_dice": "2d4+2",
             "_slug": "potion-of-healing",
             "desc": "Drink to regain 2d4+2 HP. RAW: action."},
            # v2.158.77 — Magic-items Phase 1c demo fixture. Bracers
            # of Defense (+2 AC, no-armor + no-shield gate) on Kael,
            # equipped + attuned. Kael's Monk build (Unarmored Defense
            # base AC 16, no equipped armor or shield) is the natural
            # canary for the new gate primitives — a Fighter PC with
            # equipped chain mail would have the Bracers bonus
            # correctly suppressed by the walker. Appended at END so
            # existing inventory-index assertions stay valid.
            {"name": "Bracers of Defense", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "bracers-of-defense",
             "desc": "Rare wondrous item, attunement. +2 AC while wearing no armor and using no shield."},
        ],
        "feats": [],
        # v2.18.0: Ki counter (max = monk level). Refreshes on short rest.
        # Each Ki spend funds a bonus-action Flurry / Patient Defense /
        # Step of the Wind option (all curated in `_FEATURE_ECONOMY`
        # since v2.6.0 with slot:'bonus'). Stunning Strike (Lv 5) also
        # spends 1 Ki but it's a per-attack uplift — pending the v2.16.0
        # attack-picker pattern extending for Monks.
        # v2.49.227: Lv 6 bump → Ki max 6 + Wholeness of Body counter.
        # v2.49.229: Lv 7 bump → Ki max 7 + Stillness of Mind unlock
        # (no counter — RAW unlimited uses; the action chip is the gate).
        "resources": [
            {
                "key": "ki",
                "name": "Ki",
                "current": 7, "max": 7, "reset": "short",
                "source": "monk Lv 2",
                "class_slug": "monk",
                "desc": "Spend 1 Ki for Flurry of Blows / Patient Defense / Step of the Wind (bonus action). 7 points at Lv 7; refreshes on short rest.",
                "manual": False,
            },
            {
                "key": "wholeness-of-body",
                "name": "Wholeness of Body",
                "current": 1, "max": 1, "reset": "long",
                "source": "Way of the Open Hand Lv 6",
                "class_slug": "monk",
                "desc": "Action: regain 3× monk level HP (21 at Lv 7). Once per long rest.",
                "manual": False,
            },
        ],
        # v2.18.0: clickable Ki-spend buttons in the Class abilities
        # panel. Each option is a bonus action (slot:'bonus' per the
        # curated table); clicking fires /use_feature which announces
        # + flips the Bns chip. v1 deviation: the Ki counter isn't
        # auto-decremented on click — the GM (or the player) clicks
        # the resource pip to spend the Ki separately. A future
        # per-feature commit will route Ki options through a dedicated
        # /use_ki endpoint that atomically decrements the Ki counter +
        # marks the bonus slot + announces, mirroring v2.17.1 Second
        # Wind.
        "class_features": [
            {
                "key": "flurry-of-blows",
                "name": "Flurry of Blows",
                "desc": "Bonus action — spend 1 Ki to make two unarmed strikes (1d6+DEX each at Lv 5).",
            },
            {
                "key": "patient-defense",
                "name": "Patient Defense",
                "desc": "Bonus action — spend 1 Ki to take the Dodge action (attacks against you have disadvantage; you have advantage on DEX saves).",
            },
            {
                "key": "step-of-the-wind",
                "name": "Step of the Wind",
                "desc": "Bonus action — spend 1 Ki to take the Disengage or Dash action; jump distance doubles for the turn.",
            },
            # v2.49.227: Wholeness of Body (Way of the Open Hand Lv 6).
            # Action — regain HP equal to 3 × monk level (21 at Lv 7).
            # Once per long rest. Decremented by /use_wholeness_of_body.
            {
                "key": "wholeness-of-body",
                "name": "Wholeness of Body",
                "desc": "Action — regain 3× monk level HP (21 at Lv 7). Once per long rest.",
            },
            # v2.49.229: Stillness of Mind (Monk Lv 7). Action — end
            # one charmed or frightened condition on yourself. No
            # counter — RAW unlimited uses; the action chip is the
            # gate. Routed through /use_stillness_of_mind.
            {
                "key": "stillness-of-mind",
                "name": "Stillness of Mind",
                "desc": "Action — end one charmed or frightened condition on yourself. Unlimited uses.",
            },
            # v2.51.5: Evasion (Monk Lv 7+). Passive — when a Dex save
            # would have you take half damage, you take none on success
            # and half on failure. Fires automatically server-side
            # inside the save-spell damage path via
            # `_apply_evasion_to_dex_save_damage`; no /use endpoint, no
            # counter, no UI buttons — pure description for the sheet.
            {
                "key": "evasion",
                "name": "Evasion",
                "desc": "Passive — when a Dex save would deal half damage, take none on success and half on failure. Fires automatically server-side on Dex-save spells like Fireball.",
            },
            # v2.54.1: pure-descriptive Monk passives. RAW values
            # already reflected on the sheet (speed reflects the
            # Unarmored Movement bonus; no fall-damage or
            # magical-vs-mundane resistance system in app today).
            # See `docs/plans/class-content-status.md` for the
            # "would need system X" rationales per feature.
            {
                "key": "unarmored-movement",
                "name": "Unarmored Movement",
                "desc": "Passive (Lv 2+) — +10 ft speed while not wearing armor or carrying a shield. Already baked into Kael's listed speed (40 ft). Scales to +15 ft at Lv 6+ (45 ft), +20 ft at Lv 10+, +25 ft at Lv 14+, +30 ft at Lv 18+.",
            },
            {
                "key": "slow-fall",
                "name": "Slow Fall",
                "desc": "Reaction (Lv 4+) — reduce fall damage by 5 × monk level (35 at Lv 7). SimpleVTT doesn't model fall damage yet; descriptive only until a fall-damage system ships.",
            },
            {
                "key": "ki-empowered-strikes",
                "name": "Ki-Empowered Strikes",
                "desc": "Passive (Lv 6+) — unarmed strikes count as magical for the purpose of bypassing resistance / immunity to nonmagical attacks. SimpleVTT doesn't gate resistance on magical-vs-mundane today; descriptive only until that gate ships.",
            },
        ],
    }


def _sorcerer_sheet(name: str) -> dict:
    """v2.18.1: demo Sorcerer Lv 5 (Draconic Bloodline / Red Dragon)
    for the GM. Added in Phase A.6 to unlock per-feature work for
    Font of Magic SP↔slot conversion (curated table entry from
    v2.16.2 with slot:'free') + Metamagic (Quickened Spell from
    v2.6.0 + Twinned Spell follow-up) + Draconic Bloodline's
    Elemental Affinity (Lv 6, deferred). Tiefling for the canonical
    "CHA + Hellish Resistance + 1/long-rest infernal spells" build.
    Color `#c4452a` (rust / burnt orange) for fire-themed Red Dragon
    flavor — distinct from every existing palette.
    """
    return {
        "class": "Sorcerer",
        "subclass": "Draconic Bloodline",  # Red Dragon ancestor
        "level": 5,
        "race": "Tiefling",  # +2 CHA, +1 INT, Hellish Resistance (fire), Infernal Legacy
        "alignment": "Chaotic Good",
        "background": "Charlatan",
        # Rolled stats post-racial: STR 8 / DEX 14 / CON 14 / INT 11 /
        # WIS 12 / CHA 17. Tiefling +2 CHA (→ 17) + +1 INT (→ 11)
        # from pre-racial 15 CHA + 10 INT.
        "abilities": {"STR": 8, "DEX": 14, "CON": 14, "INT": 11, "WIS": 12, "CHA": 17},
        # Draconic Resilience: AC = 13 + DEX mod when unarmored. So
        # 13 + 2 = 15. Sorcerer's no-armor default would be 12
        # (10 + DEX); Draconic Resilience makes Zara surprisingly
        # tanky without armor.
        "ac": 15,
        "speed": 30,
        # Lv 1 max d6 (6) + 4× avg d6 (4) + CON +2 × 5 = 6 + 16 + 10 = 32,
        # plus Draconic Resilience +1 HP / sorcerer level = +5. Total 37.
        "hp": {"current": 37, "max": 37, "temp": 0},
        # v2.99.18 — Tiefling Hellish Resistance: resistance to fire
        # damage. RAW (PHB p.43). The v2.99.18 _resistance_halve
        # extension reads this list at the sheet root and halves
        # incoming damage of any matching type before applying it.
        # Same shape as NPC monster templates' damage_resistances
        # field.
        "damage_resistances": ["fire"],
        "initiative_bonus": 2,  # DEX 14 mod
        "proficiency_bonus": 3,
        "hit_dice": {"current": 5, "max": 5},
        "class_hit_die": "d6",
        "class_spellcasting": "CHA",
        # Sorcerer prof saves are CON + CHA.
        "saving_throws": {"CON": True, "CHA": True},
        # Charlatan background grants Deception + Sleight of Hand;
        # Sorcerer Lv 1 picks two from a curated list (Arcana + Persuasion).
        "skills": {
            "Arcana":         {"ability": "INT", "proficient": True, "expertise": False},
            "Persuasion":     {"ability": "CHA", "proficient": True, "expertise": False},
            "Deception":      {"ability": "CHA", "proficient": True, "expertise": False},
            "Sleight of Hand": {"ability": "DEX", "proficient": True, "expertise": False},
        },
        # Sorcerer Lv 5 known cantrips = 5; known leveled spells = 6.
        # Draconic Bloodline's Lv 1 feature picks a draconic ancestor
        # (Red = fire); the curated subclass-spell table in
        # app/static/dnd5e_subclass_spells.js doesn't grant bonus
        # spells for Draconic Bloodline RAW (the Bloodline grants
        # passive features, not spell prep). Sorcerers also know
        # Tiefling's Infernal Legacy spells separately (Thaumaturgy
        # cantrip, Hellish Rebuke 1/long, Darkness 1/long).
        "attacks": [
            {"name": "Dagger", "attack_bonus": "+5", "damage": "1d4+2",
             "damage_type": "piercing", "range": "20/60 ft",
             "desc": "Finesse, light, thrown. DEX-based melee + ranged option."},
            {"name": "Fire Bolt (cantrip)", "attack_bonus": "+6", "damage": "2d10",
             "damage_type": "fire", "range": "120 ft",
             "desc": "Ranged spell attack. Cantrip damage scales: 1d10 at Lv 1, 2d10 at Lv 5. Red Dragon Bloodline doesn't grant Fire Bolt for free RAW; Zara picked it as one of her 5 cantrips."},
        ],
        # Lv 5 Sorcerer: 5 cantrips known + 6 leveled spells known.
        # Tiefling's Thaumaturgy cantrip is racial (free, doesn't count
        # toward the 5 known). Hellish Rebuke + Darkness are 1/long-
        # rest racial spells (tracked via resource counters below).
        "spells": [
            {"name": "Fire Bolt", "level": 0, "prepared": True, "_slug": "fire-bolt", "casting_time": "1 action"},
            {"name": "Mage Hand", "level": 0, "prepared": True, "_slug": "mage-hand", "casting_time": "1 action"},
            {"name": "Minor Illusion", "level": 0, "prepared": True, "_slug": "minor-illusion", "casting_time": "1 action"},
            {"name": "Prestidigitation", "level": 0, "prepared": True, "_slug": "prestidigitation", "casting_time": "1 action"},
            {"name": "Shocking Grasp", "level": 0, "prepared": True, "_slug": "shocking-grasp", "casting_time": "1 action"},
            {"name": "Thaumaturgy", "level": 0, "prepared": True, "_slug": "thaumaturgy",
             "casting_time": "1 action", "_racial_granted": True, "_granted_by": "Tiefling"},
            {"name": "Shield", "level": 1, "prepared": True, "_slug": "shield", "casting_time": "1 reaction"},
            {"name": "Magic Missile", "level": 1, "prepared": True, "_slug": "magic-missile", "casting_time": "1 action"},
            {"name": "Burning Hands", "level": 1, "prepared": True, "_slug": "burning-hands", "casting_time": "1 action"},
            {"name": "Mirror Image", "level": 2, "prepared": True, "_slug": "mirror-image", "casting_time": "1 action"},
            {"name": "Scorching Ray", "level": 2, "prepared": True, "_slug": "scorching-ray", "casting_time": "1 action"},
            {"name": "Fireball", "level": 3, "prepared": True, "_slug": "fireball", "casting_time": "1 action"},
            # v2.49.63 — Sleep. RAW on the Sorcerer spell list. Routed
            # via /cast_sleep with class_slug="sorcerer".
            {"name": "Sleep", "level": 1, "prepared": True, "_slug": "sleep", "casting_time": "1 action"},
            # v2.99.35 — Hold Person. RAW Sorcerer L2 spell, WIS save
            # → Paralyzed condition. Demo fixture for Heightened
            # Spell metamagic — Zara casts Hold Person with
            # Heightened armed at a target, the target's first save
            # rolls at disadvantage (2d20kl1).
            {"name": "Hold Person", "level": 2, "prepared": True, "_slug": "hold-person", "casting_time": "1 action"},
        ],
        # Lv 5 Sorcerer slots per the Sorcerer table.
        "spell_slots": {
            "sorcerer": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 3, "used": 0},
                "3": {"total": 2, "used": 0},
            },
        },
        "inventory": [
            {"name": "Dagger", "type": "weapon", "qty": 2,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d4", "damage_type": "piercing",
             "range": "20/60 ft", "properties": "finesse, light, thrown",
             "_slug": "dagger"},
            {"name": "Component pouch", "type": "gear", "qty": 1,
             "desc": "Required spellcasting focus for spells with material components."},
            {"name": "Dungeoneer's pack", "type": "gear", "qty": 1,
             "desc": "Backpack, crowbar, hammer, 10 pitons, 10 torches, tinderbox, 10 days rations, waterskin, 50 ft hempen rope."},
            {"name": "Marked deck of cards", "type": "gear", "qty": 1,
             "desc": "Charlatan background trinket — Zara's old grift kit. Cosmetic."},
            {"name": "Potion of Healing", "type": "consumable", "qty": 1,
             "consumable": True, "use_kind": "heal", "heal_dice": "2d4+2",
             "_slug": "potion-of-healing",
             "desc": "Drink to regain 2d4+2 HP. RAW: action."},
        ],
        "feats": [],
        # v2.18.1: Sorcerer Lv 5 resources. sorcery-points (max = sorcerer
        # level = 5); refreshes on long rest. Tiefling racial spells
        # Hellish Rebuke + Darkness are 1/long-rest each. Future
        # commit ships the dedicated /use_font_of_magic endpoint
        # (atomic SP↔slot conversion picker, mirrors the v2.16.1
        # /use_arcane_recovery shape).
        "resources": [
            {
                "key": "sorcery-points",
                "name": "Sorcery Points",
                "current": 5, "max": 5, "reset": "long",
                "source": "sorcerer Lv 2 / Font of Magic",
                "class_slug": "sorcerer",
                "desc": "Spend to fuel Metamagic + convert to/from spell slots via Font of Magic. Refreshes on long rest. (Lv 20 Sorcerous Restoration refills 4 SP on short rest — not yet at Lv 5.)",
                "manual": False,
            },
            {
                "key": "hellish-rebuke",
                "name": "Hellish Rebuke (racial)",
                "current": 1, "max": 1, "reset": "long",
                "source": "Tiefling Infernal Legacy",
                "class_slug": "tiefling",
                "desc": "Reaction (Tiefling Lv 3+): cast Hellish Rebuke L2 (3d10 fire, DEX save half) when you take damage from a creature within 60 ft you can see. 1/long rest.",
                "manual": False,
            },
            {
                "key": "darkness-racial",
                "name": "Darkness (racial)",
                "current": 1, "max": 1, "reset": "long",
                "source": "Tiefling Infernal Legacy",
                "class_slug": "tiefling",
                "desc": "Action (Tiefling Lv 5+): cast Darkness without expending a spell slot. 1/long rest.",
                "manual": False,
            },
        ],
        # v2.18.1: clickable class-feature buttons in the Class abilities
        # panel. font-of-magic is the announce-only entry today
        # (curated `slot: 'free'` since v2.16.2); the dedicated
        # /use_font_of_magic endpoint that handles SP↔slot conversion
        # picker is a future per-feature commit. Quickened Spell is
        # a metamagic (slot: 'bonus' per the curated table); clicking
        # it announces "Quickened Spell" + flips the Bns chip — the
        # player still casts the actual spell separately via the spell
        # browser. Metamagic picker UI (which metamagic options does
        # Zara know?) is filed; she's marked as knowing Quickened
        # Spell + Twinned Spell per Lv 3 choice but only Quickened
        # appears as a Class abilities button until twinned-spell
        # lands its own curated entry.
        "class_features": [
            {
                "key": "font-of-magic",
                "name": "Font of Magic",
                "desc": "Convert spell slots ↔ sorcery points. Costs: 2/3/5/6/7 SP per L1/L2/L3/L4/L5 slot; slot → SP at the slot level (L3 slot → 3 SP).",
            },
            {
                "key": "quickened-spell",
                "name": "Quickened Spell (metamagic)",
                "desc": "Spend 2 sorcery points: change a 1-action spell's casting time to 1 bonus action this turn.",
            },
            # v2.49.124 Sorcery Phase 1 — Empowered Spell. Clickable
            # button arms a one-cast ``metamagic-empowered-pending``
            # buff; the next ``/cast_spell`` damage roll rerolls up
            # to CHA-mod lowest dice. PHB p.102.
            {
                "key": "empowered-spell",
                "name": "Empowered Spell (metamagic)",
                "desc": "Spend 1 sorcery point: when you roll damage for a spell, reroll up to CHA-mod of the lowest damage dice once (you must use the new rolls).",
            },
            # v2.99.33 — Twinned Spell. Variable SP cost (spell
            # level, min 1 for cantrip). Announce-only in v1
            # (player makes the second-target cast manually).
            # PHB p.102.
            {
                "key": "twinned-spell",
                "name": "Twinned Spell (metamagic)",
                "desc": "Spend SP = spell level (min 1 for cantrip): when you cast a single-target spell with range > Self, target a second creature in range. v1: announce-only — cast the spell at the second target via a follow-up Cast.",
            },
            # v2.99.34 — Distant Spell. 1 SP flat. Announce-only.
            # PHB p.102.
            {
                "key": "distant-spell",
                "name": "Distant Spell (metamagic)",
                "desc": "Spend 1 sorcery point: double the range of a spell with range ≥ 5 ft, OR extend a Touch spell to 30 ft. v1: announce-only — GM applies the extended range at cast time.",
            },
            # v2.99.35 — Heightened Spell. 3 SP flat. Mechanical:
            # arms a `metamagic-heightened-pending` buff on the
            # caster; the next save-roll construction site reads the
            # buff + swaps the target's d20 → 2d20kl1 (disadvantage)
            # AND drops the buff (one-use). PHB p.102.
            {
                "key": "heightened-spell",
                "name": "Heightened Spell (metamagic)",
                "desc": "Spend 3 sorcery points: when you cast a save-spell, ONE target rolls its first save with disadvantage. Auto-consumed on the next save-roll resolution.",
            },
            # v2.99.37 — Extended Spell. 1 SP flat. Announce-only.
            # PHB p.102.
            {
                "key": "extended-spell",
                "name": "Extended Spell (metamagic)",
                "desc": "Spend 1 sorcery point: when you cast a spell with a duration ≥ 1 minute, double its duration (max 24 hours). v1: announce-only — GM applies the extended duration at cast time.",
            },
            # v2.99.38 — Careful Spell. 1 SP flat. Mechanical: arms a
            # `metamagic-careful-pending` buff on the caster with a
            # list of protected combatant_ids; the next save-spell's
            # save-roll construction sites read the buff + swap
            # protected targets' d20 → "1d20+99" (auto-pass). PHB
            # p.102.
            {
                "key": "careful-spell",
                "name": "Careful Spell (metamagic)",
                "desc": "Spend 1 sorcery point: when you cast a save-spell, choose up to CHA-mod creatures (min 1). Those creatures auto-succeed on their first saving throw vs the spell. Auto-consumed on the next save-roll resolution.",
            },
            # v2.99.39 — Sorcerous Restoration (Lv 20 capstone).
            # PHB p.101. Refunds 4 SP on every short rest. Wired
            # in /rest short-rest path; gated on class==sorcerer
            # AND level>=20. Descriptive entry until Zara hits
            # Lv 20 in a future fixture bump.
            {
                "key": "sorcerous-restoration",
                "name": "Sorcerous Restoration (Lv 20)",
                "desc": "Beginning at 20th level, you regain 4 expended sorcery points whenever you finish a short rest. Auto-applied by the /rest endpoint when class=Sorcerer AND level>=20.",
            },
            # v2.99.43 — Elemental Affinity (Draconic Bloodline Lv 6).
            # PHB p.103. Auto-fire +CHA mod to one damage roll per
            # spell-cast when the damage type matches the ancestor's
            # type (Red → fire); optional 1 SP for 1-hour resistance
            # via /use_elemental_affinity. Descriptive entry until
            # Zara hits Lv 6 in a future fixture bump.
            {
                "key": "elemental-affinity",
                "name": "Elemental Affinity (Lv 6)",
                "desc": "Beginning at 6th level, when you cast a spell that deals damage of your draconic ancestor's type (Zara → fire), add CHA-mod to one damage roll. You can also spend 1 SP to gain resistance to that damage type for 1 hour (/use_elemental_affinity).",
            },
        ],
        # Sorcerer's Metamagic at Lv 3 picks 2 options. Zara's picks:
        # Quickened (v2.6.0) + Empowered (v2.49.124) + Twinned
        # (v2.99.33) + Distant (v2.99.34) + Heightened (v2.99.35) +
        # Extended (v2.99.37) + Careful (v2.99.38). 7 picks despite
        # RAW Lv 3 = 2 known — demo expansion houserule so the test
        # fixture exercises the full metamagic stack as it ships.
        "_metamagic_options": [
            "quickened-spell", "empowered-spell",
            "twinned-spell", "distant-spell",
            "heightened-spell", "extended-spell",
            "careful-spell",
        ],
        # Draconic Bloodline subclass picks an ancestor at Lv 1.
        # Red = fire (matches Tiefling's flame motif + Hellish
        # Resistance). Elemental Affinity (Lv 6) is deferred until
        # a level-bump fixture, but the ancestor tag is on the
        # sheet for future feature gates.
        "_draconic_ancestor": "red",
    }


def _fighter_sheet(name: str) -> dict:
    """v2.17.0: demo Fighter Garrik Ironside (Champion). Added in
    Phase A.4 to unlock per-feature work for Second Wind / Action
    Surge / Improved Critical (Champion Lv 3) and the deferred
    Indomitable (Lv 9+) when that feature finally ships with the
    roll-time intercept. Bumped to Lv 7 in v2.49.237 to unlock
    Remarkable Athlete (Champion Lv 7 — +ceil(PB/2) on STR/DEX/CON
    checks that don't already use PB). Variant Human + two-handed
    style + Great Weapon Fighting + Greatsword. Skips a shield so
    Action Surge's "swing twice with the same weapon" doesn't fight
    with the sword-and-board ergonomics that Caelan already covers.
    Color `#8a96a3` (steel grey) — distinct from every existing
    PC + NPC palette.
    """
    return {
        "class": "Fighter",
        "subclass": "Champion",
        # v2.49.237: bumped Lv 5 → Lv 7 for Remarkable Athlete.
        # v2.56.0: bumped Lv 7 → Lv 9 to unlock Indomitable (Fighter
        # Lv 9+: reroll a failed save, 1/long rest; 2 at Lv 13, 3 at
        # Lv 17). HP scales d10(avg 6)+CON(+3) per level × 2 levels
        # = +18 → 85/85. hit_dice 7 → 9. Proficiency bonus +3 → +4
        # at Lv 9 — cascades into attack-bonus bumps (Greatsword +7
        # → +8, Handaxe +7 → +8) + every prof-using check / save.
        # Second Wind HP gain: 1d10 + lv = 1d10 + 9.
        "level": 9,
        "race": "Variant Human",  # +1 STR + 1 CON at character creation
        "alignment": "Lawful Good",
        "background": "Soldier",
        # Rolled stats post-racial: STR 18 / DEX 14 / CON 16 / INT 8 /
        # WIS 12 / CHA 10. The Lv 4 ASI hasn't been spent yet — leaves
        # room for a future homebrew "give Garrik Great Weapon Master"
        # feat without rebalancing the stat block.
        "abilities": {"STR": 18, "DEX": 14, "CON": 16, "INT": 8, "WIS": 12, "CHA": 10},
        "ac": 16,  # chain mail 16 (no shield — two-handed Greatsword)
        "speed": 30,
        # Lv 1 max d10 (10) + 8× avg d10 (6) + CON +3 × 9 = 10 + 48 + 27 = 85
        # (Lv 9 bump v2.56.0: prior Lv 7 was 10 + 36 + 21 = 67).
        "hp": {"current": 85, "max": 85, "temp": 0},
        "initiative_bonus": 2,  # DEX 14 mod
        "proficiency_bonus": 4,  # v2.56.0: Lv 9 bump — PB +3 → +4 (Lv 9-12 = +4)
        "hit_dice": {"current": 9, "max": 9},
        "class_hit_die": "d10",
        # Fighter prof saves are STR + CON.
        "saving_throws": {"STR": True, "CON": True},
        # Soldier background grants Athletics + Intimidation; Fighter Lv 1
        # picks two from a curated list (Perception + Survival).
        "skills": {
            "Athletics":   {"ability": "STR", "proficient": True, "expertise": False},
            "Intimidation": {"ability": "CHA", "proficient": True, "expertise": False},
            "Perception":  {"ability": "WIS", "proficient": True, "expertise": False},
            "Survival":    {"ability": "WIS", "proficient": True, "expertise": False},
        },
        # v2.99.85 — Fighting Style: Great Weapon Fighting. Pre-v2.99.85
        # the style was only referenced in the Greatsword desc as a
        # manual reminder; v2.99.85's _apply_great_weapon_fighting_reroll
        # auto-rerolls 1s and 2s on the damage roll at /attack time
        # when sheet.fighting_style == "great_weapon" + attack is 2H melee.
        "fighting_style": "great_weapon",
        "attacks": [
            # v2.56.0: attack bonuses bumped +7 → +8 (STR +4 + prof +4).
            {"name": "Greatsword", "attack_bonus": "+8", "damage": "2d6+4",
             "damage_type": "slashing", "range": "5 ft",
             "desc": "Two-handed, heavy. Great Weapon Fighting (Lv 1 style): reroll 1s and 2s on the damage roll once each — auto-applied at /attack time per v2.99.85."},
            {"name": "Handaxe (thrown)", "attack_bonus": "+8", "damage": "1d6+4",
             "damage_type": "slashing", "range": "20/60 ft",
             "desc": "Light, thrown. Can also be wielded melee. Garrik carries two so an Action Surge thrown-attack combo is possible."},
            # v2.99.27 — Glaive (martial polearm, 1d10 slashing, reach
            # 10 ft). Demo fixture for Polearm Master enter-reach OA
            # trigger (v2.66.4 helper now gates on equipped polearm
            # per RAW). Garrik can swap to the Glaive when the encounter
            # calls for reach control.
            {"name": "Glaive", "attack_bonus": "+8", "damage": "1d10+4",
             "damage_type": "slashing", "range": "10 ft",
             "desc": "Two-handed, heavy, reach 10 ft. Polearm Master: enter-reach OA + bonus-action butt-end strike (1d4)."},
            # v2.158.91 — Magic-items Phase 5a demo fixture. Flame
            # Tongue Longsword (RAW DMG p.170). The ``_slug`` field is
            # the rider gate: ``_compute_attack_auto_uplifts`` reads it
            # at /attack time and matches against the wielder's
            # equipped+attuned inventory item to fire the +2d6 fire
            # uplift. RAW versatile (1d8/1d10) — sheet expression uses
            # the 1-handed line since Garrik holds it solo.
            {"name": "Flame Tongue Longsword", "attack_bonus": "+8",
             "damage": "1d8+4", "damage_type": "slashing",
             "range": "5 ft", "_slug": "flame-tongue",
             "desc": "Rare longsword, attunement. 1d8+4 slashing + 2d6 fire on hit (always-on while attuned)."},
        ],
        # Fighter is non-casting RAW (Champion subclass doesn't grant
        # spells either). No spells / spell_slots fields needed.
        "inventory": [
            {"name": "Greatsword", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 2,
             "damage": "2d6", "damage_type": "slashing",
             "properties": "heavy, two-handed", "_slug": "greatsword"},
            {"name": "Handaxe", "type": "weapon", "qty": 2,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "slashing",
             "range": "20/60 ft", "properties": "light, thrown",
             "_slug": "handaxe"},
            # v2.99.27 — Glaive (martial polearm). Default equipped=False
            # so Garrik defaults to Greatsword. Tests + GM can flip
            # equipped=True via sheet-fields PATCH to trigger the
            # Polearm Master enter-reach OA. The v2.99.27 wire reads
            # this `equipped` field in `_pc_wields_polearm` and only
            # fires Polearm Master when an equipped polearm is found.
            {"name": "Glaive", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": False, "hands": 2,
             "damage": "1d10", "damage_type": "slashing",
             "range": "10 ft", "properties": "heavy, two-handed, reach",
             "_slug": "glaive"},
            {"name": "Chain mail", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "heavy", "ac_value": 16,
             "_slug": "chain-mail"},
            {"name": "Explorer's pack", "type": "gear", "qty": 1,
             "desc": "Backpack, bedroll, mess kit, tinderbox, 10 torches, 10 days rations, waterskin, 50 ft hempen rope."},
            {"name": "Insignia of rank", "type": "gear", "qty": 1,
             "desc": "Soldier background trinket — old captain's badge. Cosmetic; no mechanic."},
            {"name": "Potion of Healing", "type": "consumable", "qty": 2,
             "consumable": True, "use_kind": "heal", "heal_dice": "2d4+2",
             "_slug": "potion-of-healing",
             "desc": "Drink to regain 2d4+2 HP. RAW: action."},
            # v2.158.91 — Magic-items Phase 5a demo fixture. Flame
            # Tongue Longsword (rare, attunement). Pair-bound with
            # the attack entry above via ``_slug``. The rider fires
            # only when (a) the attack carries _slug="flame-tongue",
            # AND (b) the inventory item with the same slug is
            # equipped + attuned. Detuning the item via /attune
            # suppresses the rider without removing the attack
            # option — RAW: weapon still works mundane.
            # v2.158.92 — ``_lit: True`` ships the staff already
            # ablaze at session start so out-of-the-box demos still
            # produce the +2d6 fire rider without requiring a manual
            # /use_item_action ignite. RAW: the GM can extinguish with
            # the Phase 5b endpoint; non-RAW: the sword starts lit
            # rather than dark. Tradeoff favors discoverability.
            {"name": "Flame Tongue Longsword", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_lit": True,
             "hands": 1, "damage": "1d8", "damage_type": "slashing",
             "properties": "versatile (1d10), magic",
             "_slug": "flame-tongue",
             "desc": "Rare longsword, attunement. Speak the command word (bonus action — /use_item_action ignite|extinguish) to toggle. While ablaze, +2d6 fire damage on every hit."},
        ],
        # v2.77.0 Phase 4b — Lucky feat for Garrik. RAW (PHB p.167):
        # 3 luck points / long rest; reaction-style "roll a new d20
        # and pick the higher" against attack rolls against you OR
        # your own attack/check/save rolls. v1 only surfaces the
        # against-you trigger via the v2.69.0 attack_targeted event.
        # Picked Garrik (Fighter) over other PCs because his reaction
        # slot is otherwise quiet — no Uncanny Dodge (Pip), no
        # Defensive Duelist (Lyra), no War Caster (Tavik).
        "feats": [
            {"slug": "lucky", "name": "Lucky",
             "desc": "3 luck points per long rest. Spend 1 to roll an extra d20 on your attack, check, or save (pick which to use). Also spend 1 when an attack roll is made against you: roll a d20, choose whether the attack uses the attacker's roll or yours."},
            # v2.99.27 — Polearm Master added via Garrik's Lv 4 ASI
            # (replaced the +2 STR/CON ASI with the feat). Lv 9
            # Champion has had 3 ASIs (Lv 4, 6, 8); using one for a
            # feat is RAW-legal. Polearm Master enables the v2.66.4
            # enter-reach OA trigger when Garrik equips his Glaive,
            # AND the bonus-action butt-end strike (filed: needs a
            # dedicated action button + 1d4 attack). Garrik is the
            # demo's two-feat Fighter fixture (Variant Human free
            # Lv 1 feat = Lucky; Lv 4 ASI-feat = Polearm Master).
            {"slug": "polearm-master", "name": "Polearm Master",
             "desc": "When you take the Attack action and attack with only a glaive / halberd / pike / quarterstaff / spear, you can make a bonus-action melee attack with the opposite end (1d4 + STR mod). Other creatures provoke an OA from you when they enter your reach (5 ft for quarterstaff/spear; 10 ft for glaive/halberd/pike)."},
        ],
        # v2.17.0: Fighter Lv 5 resources. Both refresh on short rest.
        # v2.56.0: Indomitable counter added (Lv 9 unlock): 1/long rest;
        # 2 uses at Lv 13, 3 uses at Lv 17. Reset is "long" per RAW.
        # Champion's Improved Critical (Lv 3: crit on 19-20) is passive;
        # it doesn't need a counter (handled at server-side via
        # `_attacker_crit_threshold` since v2.49.231).
        # v2.77.0: Lucky luck points (3/long rest).
        "resources": [
            {
                "key": "lucky",
                "name": "Luck Points",
                "current": 3, "max": 3, "reset": "long",
                "source": "feat: Lucky",
                "desc": "Spend 1 to roll a new d20 (own attack/check/save → pick higher; vs attack against you → pick lower for the attacker). 3/long rest.",
            },
            {
                "key": "second-wind",
                "name": "Second Wind",
                "current": 1, "max": 1, "reset": "short",
                "source": "fighter Lv 1",
                "class_slug": "fighter",
                "desc": "Bonus action: regain 1d10 + fighter level (9) HP. Refreshes on a short or long rest.",
                "manual": False,
            },
            {
                "key": "action-surge",
                "name": "Action Surge",
                "current": 1, "max": 1, "reset": "short",
                "source": "fighter Lv 2",
                "class_slug": "fighter",
                "desc": "Take one additional action on this turn. Free — refreshes on a short or long rest. (Lv 17: 2 uses per rest.)",
                "manual": False,
            },
            {
                "key": "indomitable",
                "name": "Indomitable",
                "current": 1, "max": 1, "reset": "long",
                "source": "fighter Lv 9",
                "class_slug": "fighter",
                "desc": "Free — when you'd make a saving throw, spend an Indomitable use to roll with advantage instead. 1 use per long rest (2 at Lv 13, 3 at Lv 17).",
                "manual": False,
            },
        ],
        # v2.17.0: Class abilities buttons. The Cunning Action pattern
        # (Pip / v2.6.0) is the precedent — clicking POSTs /use_feature
        # which decrements + announces + chip-flips per the curated
        # `_FEATURE_ECONOMY` entry. v1 deviations: Second Wind doesn't
        # auto-roll the heal (GM rolls 1d10+5 and applies HP manually);
        # Action Surge's "extra action" isn't auto-refunded on the chip
        # strip (the player needs to shift+click the Act chip to refund
        # it, OR the GM does it from the init tracker). Both are filed
        # for a future per-feature commit that wires the actual mechanics
        # alongside the announce.
        "class_features": [
            {
                "key": "second-wind",
                "name": "Second Wind",
                "desc": "Bonus action: heal 1d10 + Fighter level (5) HP. Refreshes on short rest.",
            },
            {
                "key": "action-surge",
                "name": "Action Surge",
                "desc": "Take one additional action on this turn. Free slot — refreshes on short rest.",
            },
            # v2.56.0: Indomitable (Fighter Lv 9+). Free — when about
            # to make a saving throw, spend an Indomitable use to arm
            # the next save with advantage. Server-side, /use_indomitable
            # decrements the counter + installs a single-use
            # ``indomitable-armed`` self-buff; the save-roll construction
            # hook reads + consumes the buff, swapping the d20 to
            # 2d20kh1. RAW is "reroll on failure" — we ship advantage-
            # on-the-next-save as a v1 simplification (the post-roll
            # reroll-with-consequence-undo flow is filed in TODO.md).
            {
                "key": "indomitable",
                "name": "Indomitable",
                "desc": "Free (Lv 9+) — arm the next save with advantage. Decrements the Indomitable counter. 1/long rest at Lv 9-12, 2 at Lv 13, 3 at Lv 17.",
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
    # v2.17.0: Phase A.4 — demo Fighter (Garrik Ironside). 7th PC.
    # Champion Lv 5, two-handed Greatsword build. Unblocks per-feature
    # work for Second Wind (Lv 1) + Action Surge (Lv 2) + Improved
    # Critical (Champion Lv 3 — passive crit-on-19-20, ships when the
    # (B) roll-time intercept lands) + Remarkable Athlete (Champion
    # Lv 7, deferred). With Garrik the demo party is 7 PCs vs 6 NPCs;
    # the Tavern Brawl encounter is now player-favored — filed as a
    # future encounter-rebalance commit if play-testing reveals it's
    # too easy.
    fighter_pc = Character(
        campaign_id=camp.id,
        owner_user_id=users["gm"].id,
        name="Garrik Ironside",
        template="dnd5e",
        sheet=_fighter_sheet("Garrik Ironside"),
        color="#8a96a3",
    )
    # v2.18.0: Phase A.5 — demo Monk (Kael Brightleaf). 8th PC.
    # Way of the Open Hand, Lv 5, Wood Elf. DEX 18 / WIS 15. Unblocks
    # per-feature work for Ki-spending (Flurry of Blows / Patient
    # Defense / Step of the Wind — all curated since v2.6.0 with
    # slot:'bonus'). Stunning Strike (per-attack uplift, Monk Lv 5)
    # and Open Hand Technique (on-hit prone/push/no-reactions) are
    # deferred follow-ups.
    monk_pc = Character(
        campaign_id=camp.id,
        owner_user_id=users["gm"].id,
        name="Kael Brightleaf",
        template="dnd5e",
        sheet=_monk_sheet("Kael Brightleaf"),
        color="#ff8c42",
    )
    # v2.18.1: Phase A.6 — demo Sorcerer (Zara Emberfire). 9th PC.
    # Draconic Bloodline (Red Dragon), Lv 5, Tiefling. CHA 17 with
    # 6 leveled spells (Magic Missile / Burning Hands / Mirror Image
    # / Scorching Ray / Fireball / Shield). Sorcery Points 5/5 long-
    # rest + Tiefling racial Hellish Rebuke + Darkness 1/long each.
    # Unblocks Phase B work for Font of Magic SP↔slot conversion
    # picker (curated since v2.16.2 with slot:'free') + Metamagic
    # picker (Quickened Spell curated since v2.6.0; Twinned Spell
    # follow-up). Demo party is now 9 PCs vs 6 NPCs — Tavern Brawl
    # is solidly player-favored; an encounter-rebalance commit
    # (extra NPCs) is filed but doesn't block.
    sorcerer_pc = Character(
        campaign_id=camp.id,
        owner_user_id=users["gm"].id,
        name="Zara Emberfire",
        template="dnd5e",
        sheet=_sorcerer_sheet("Zara Emberfire"),
        color="#c4452a",
    )
    # v2.18.2: Phase A.7 — demo Barbarian (Krieger Stonefist). 10th PC.
    # Path of the Berserker, Lv 5, Half-Orc. STR 18 / CON 16, HP 55
    # (highest in the party), Greataxe 1d12+4 + Javelin (thrown).
    # Rage 3/long-rest. Unblocks per-feature work for Rage damage /
    # advantage / resistance (needs (C) buff slot infrastructure),
    # Reckless Attack advantage flag (needs (B) roll-time intercept),
    # Brutal Critical extra crit dice (extends v2.16.0 attack picker
    # with a crit-detection hook at Barbarian Lv 9+ — Krieger is
    # Lv 5 so not eligible yet), and Frenzy (Berserker Lv 3 — bonus
    # action while raging, ships after the rage state machine).
    barbarian_pc = Character(
        campaign_id=camp.id,
        owner_user_id=users["gm"].id,
        name="Krieger Stonefist",
        template="dnd5e",
        sheet=_barbarian_sheet("Krieger Stonefist"),
        color="#993333",
    )
    # v2.18.3: Phase A.8 — demo Ranger (Rowan Quickbow). 11th PC.
    # Hunter, Lv 5, Variant Human + Sharpshooter feat. DEX 18 / WIS 15
    # ranged-focused archer. Longbow +9 / 1d8+4 (Archery Fighting Style)
    # + Hunter's Mark concentration buff + Colossus Slayer +1d6 on
    # below-max-HP targets. Unblocks Phase B work for the Hunter's Mark
    # concentration buff (needs (C) buff slot + concentration tracker),
    # Favored Enemy + Natural Explorer announce-only flows (already
    # curated in `_FEATURE_ECONOMY`), and Sharpshooter -5/+10 per-attack
    # uplift (extends the v2.16.0 attack-picker for feat-driven uplifts).
    ranger_pc = Character(
        campaign_id=camp.id,
        owner_user_id=users["gm"].id,
        name="Rowan Quickbow",
        template="dnd5e",
        sheet=_ranger_sheet("Rowan Quickbow"),
        color="#5d7c4a",
    )
    # v2.18.4: Phase A.9 — demo Warlock (Magnus Hexbinder). 12th PC.
    # The Fiend, Lv 5, Bronze Dragonborn. CHA 17, Eldritch Blast +6 /
    # 2d10 force (2 beams at Lv 5; Agonizing Blast adds CHA mod to
    # each beam). Pact Magic 2/2 L3 slots short-rest refresh — the
    # unique-to-Warlock spell-slot table. Hex (concentration buff,
    # +1d6 necrotic on hits). Dark One's Blessing (passive: temp HP
    # on kill). Bronze Dragonborn breath weapon 1/short. Wraps Phase
    # A — 12/12 PHB classes now in the demo party. Unlocks Phase B
    # work for Pact Magic short-rest slot refresh, Hex (mirrors
    # Hunter's Mark's concentration buff + per-attack rider), Dark
    # One's Blessing temp-HP-on-kill trigger (needs (B) damage
    # roll-time intercept with a "did target reach 0 HP" hook),
    # and Eldritch Invocation toggles (Agonizing Blast's per-beam
    # uplift is the canonical test case).
    warlock_pc = Character(
        campaign_id=camp.id,
        owner_user_id=users["gm"].id,
        name="Magnus Hexbinder",
        template="dnd5e",
        sheet=_warlock_sheet("Magnus Hexbinder"),
        color="#6a3a8e",
    )
    # v2.158.56: 13th PC — demo Vengeance Paladin (Dame Seraphine Vael).
    # Oath of Vengeance Lv 3 so the v2.158.55 Vow of Enmity sheet button
    # (Vengeance Paladin Lv 3+ Channel Divinity → /use_vow_of_enmity) is
    # reachable in the live demo. Caelan is Oath of Devotion, whose CD
    # options filter out Vow of Enmity. GM-owned like the other party PCs.
    vengeance_pc = Character(
        campaign_id=camp.id,
        owner_user_id=users["gm"].id,
        name="Dame Seraphine Vael",
        template="dnd5e",
        sheet=_paladin_vengeance_sheet("Dame Seraphine Vael"),
        color="#b03a4a",
    )
    # v2.158.60: 14th PC — demo Path of the Beast Barbarian (Brakka
    # Wildmane). Lv 5 so the v2.158.59 Form of the Beast sheet button
    # (Path of the Beast Lv 3+ → /use_form_of_the_beast) is reachable
    # in the live demo. Krieger is Path of the Berserker, whose
    # class-features list has no Form of the Beast entry. GM-owned.
    beast_barbarian_pc = Character(
        campaign_id=camp.id,
        owner_user_id=users["gm"].id,
        name="Brakka Wildmane",
        template="dnd5e",
        sheet=_barbarian_beast_sheet("Brakka Wildmane"),
        color="#7a4a2a",
    )
    # v2.158.62: 15th PC — demo Way of the Drunken Master Monk (Quan
    # Reelstep). Lv 5 so the v2.158.61 Drunken Technique sheet button
    # (Way of the Drunken Master Lv 3+ → /use_drunken_technique) is
    # reachable in the live demo. Kael is Way of the Open Hand, whose
    # class-features list has no Drunken Technique entry. GM-owned.
    drunken_monk_pc = Character(
        campaign_id=camp.id,
        owner_user_id=users["gm"].id,
        name="Quan Reelstep",
        template="dnd5e",
        sheet=_monk_drunken_sheet("Quan Reelstep"),
        color="#6b2d3c",
    )
    db.add_all([alice_pc, bob_pc, gm_pc, paladin_pc, bard_pc, druid_pc, fighter_pc, monk_pc, sorcerer_pc, barbarian_pc, ranger_pc, warlock_pc, vengeance_pc, beast_barbarian_pc, drunken_monk_pc])
    db.flush()
    return [alice_pc, bob_pc, gm_pc, paladin_pc, bard_pc, druid_pc, fighter_pc, monk_pc, sorcerer_pc, barbarian_pc, ranger_pc, warlock_pc, vengeance_pc, beast_barbarian_pc, drunken_monk_pc]


def _npc_sheet(slug: str, label: str, creature_type: str = "") -> dict:
    """Minimal NPC sheet that points at a shipped SRD monster slug. The
    actual stat block resolves via local_content when the GM opens it.

    v2.158.98 — optional ``creature_type`` field. When supplied (e.g.
    ``"dragon"`` on the Young Red Dragon template), the v2.97.48
    ``_attacker_creature_type`` helper reads it via
    ``token_template.sheet["type"]`` and the v2.158.96 Phase 5f
    resolver injects it into the condition predicate, so e.g. Dragon
    Slayer's rider auto-fires when the GM drag-spawns this template
    on the map and Caelan attacks it. Existing templates default to
    empty (unchanged behavior — the helper falls through to the
    monster's content JSON resolver, which is the v2.97.48 path)."""
    sheet = {
        "class": "NPC",
        "monster_slug": slug,
        "level": 1,
        "abilities": {"STR": 10, "DEX": 10, "CON": 10, "INT": 10, "WIS": 10, "CHA": 10},
    }
    if creature_type:
        sheet["type"] = creature_type
    return sheet


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
        # v2.49.64 — undead + charm-immune templates so Sleep can
        # demo its RAW exclusion rule. Skeleton is undead (Sleep
        # skips it entirely); Doppelganger is Monstrosity + charm-
        # immune (Sleep skips on the second exclusion branch). Both
        # resolve via the shipped SRD JSONs.
        # v2.158.104 — extend with creature_type="undead" so Sun
        # Blade's vs-undead rider auto-fires via the v2.158.96 helper
        # resolution (same pattern as the Young Red Dragon template).
        ("skeleton", "Skeleton", "undead"),
        ("doppelganger", "Doppelganger"),
        # v2.49.171 — spellcasting NPC homebrew (Cult Acolyte). Two
        # spell actions (Inflict Wounds + Sacred Flame) exercise both
        # NPC strike flows: attack-roll → /npc_attack picker; save-DC
        # → 📋 Save announce.
        ("cult-acolyte", "Cult Acolyte"),
        # v2.97.74 — SRD Archmage Lv 18. Resolves via the shipped
        # SRD JSON ``app/data/local/dnd5e/monsters/archmage.json``,
        # which lists Banishment among its 4th-level spells. Gives
        # the demo a high-CR caster who CAN actually cast Banishment
        # at slot_level=4 (Caelan still can't until Lv 13 — that's
        # filed). The template isn't placed on the demo map by
        # default (would clutter the bandit-encounter scene with
        # a CR 12 caster), but a GM can drag-spawn it from the
        # Templates tab for set-piece encounters or for testing.
        ("archmage", "Archmage"),
        # v2.158.98 — Magic-items Phase 6b demo fixture. Young Red
        # Dragon template carries ``creature_type: "dragon"`` so
        # Caelan's v2.158.93 Dragon Slayer rider auto-fires when the
        # GM drag-spawns this template on the map. The 3rd tuple
        # element is the creature type — defaults to "" for every
        # other template (helper falls through to content JSON).
        # Not placed on the demo map by default (CR 10 vs. Lv 5-9
        # PCs would steamroll the Tavern Brawl); GM drags from the
        # Templates tab when they want to showcase the rider.
        ("young-red-dragon", "Young Red Dragon", "dragon"),
        # v2.158.102 — Magic-items Phase 7b demo fixture. Quasit
        # (CR 1, fiend). Lyra's Demon Slayer Rapier's +2d6 fiend
        # rider (v2.158.97 Phase 6a) + the Phase 7b DC 15 WIS save-
        # or-frighten both auto-fire when she attacks one. Quasit
        # is small (size=1) and squishy (CR 1, HP 7 RAW), so it
        # doesn't crowd the demo's tactical-balance picture the way
        # a Pit Fiend would. Like the Young Red Dragon, it's not
        # placed on the demo map by default — drag-spawn from
        # Templates when showcasing the rider.
        ("quasit", "Quasit", "fiend"),
        # v2.159.1 — Magic-items Phase 8a demo fixture. Hill Giant
        # (CR 5, giant). Gives Rowan's Arrow of Slaying (Giants) a
        # real RAW-giant target — the Phase 5f helper resolves
        # sheet.type="giant" on drag-spawn so the +6d10 piercing
        # save-for-half rider auto-fires. Not placed on the demo
        # map — drag-spawn from Templates when showcasing.
        ("hill-giant", "Hill Giant", "giant"),
    ]
    # v2.158.98 — specs now mixes 2-tuples and 3-tuples; the third
    # element is the optional creature_type. Unpack with a default so
    # both shapes work without rewriting every entry above.
    out: dict[str, TokenTemplate] = {}
    for spec in specs:
        slug, label, creature_type = (*spec, "")[:3]
        tt = TokenTemplate(
            campaign_id=camp.id,
            name=label,
            template="dnd5e",
            sheet=_npc_sheet(slug, label, creature_type=creature_type),
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

    # Player tokens. v2.49.172: the encounter is slimmed from 12 PCs
    # to 6 — a typical D&D party size. All 12 Character rows still
    # exist in the campaign roster (so the Characters tab + harness
    # ``roster`` fixture still find them) but only the 6 selected
    # PCs get tokens spawned on the map + entries in the pre-rolled
    # initiative below. The 6 keepers cover broad class coverage:
    # Rogue (Pip), Druid (Thalindra), Cleric (Tavik), Sorcerer (Zara),
    # Barbarian (Krieger), Warlock (Magnus). The 6 sidelined PCs
    # (Sir Caelan / Lyra / Mira / Garrik / Kael / Rowan) remain in
    # the roster but aren't visible on the map until the GM
    # drag-spawns them from the Characters drawer.
    # v2.99.58 — every player token lands on team="hero" so the
    # v2.99.52 same-team filter (Phase 1 of plan-movement-oa-flow)
    # is exercised out of the box. The GM can override per-token
    # via the Token Management edit toggle (Phase 2) if a PC ever
    # needs to be tagged villain (mind-controlled / charmed flavor).
    tokens.append(Token(
        map_id=map_.id, character_id=chars[0].id,
        controller_user_id=users["alice"].id,
        label=chars[0].name, color="#6cb4ff",
        image_url="/static/demo/tokens/rogue.jpg",
        x=350, y=490, size=1, team="hero",
    ))
    tokens.append(Token(
        map_id=map_.id, character_id=chars[1].id,
        controller_user_id=users["bob"].id,
        label=chars[1].name, color="#4ade80",
        image_url="/static/demo/tokens/wizard.jpg",
        x=420, y=560, size=1, team="hero",
    ))
    tokens.append(Token(
        map_id=map_.id, character_id=chars[2].id,
        controller_user_id=users["gm"].id,
        label=chars[2].name, color="#f5b75c",
        image_url="/static/demo/tokens/cleric.jpg",
        x=420, y=420, size=1, team="hero",
    ))
    # Zara Emberfire (Sorcerer, chars[8]) — back-line caster on the
    # west flank, Fire Bolt's 120 ft covers the NPC cluster.
    tokens.append(Token(
        map_id=map_.id, character_id=chars[8].id,
        controller_user_id=users["gm"].id,
        label=chars[8].name, color="#c4452a",
        image_url=None,
        x=280, y=490, size=1, team="hero",
    ))
    # Krieger Stonefist (Barbarian, chars[9]) — front-line tank,
    # Half-Orc Speed 40 closes ground first.
    tokens.append(Token(
        map_id=map_.id, character_id=chars[9].id,
        controller_user_id=users["gm"].id,
        label=chars[9].name, color="#993333",
        image_url=None,
        x=490, y=420, size=1, team="hero",
    ))
    # Magnus Hexbinder (Warlock, chars[11]) — far west flank,
    # Eldritch Blast 120 ft covers the whole map.
    tokens.append(Token(
        map_id=map_.id, character_id=chars[11].id,
        controller_user_id=users["gm"].id,
        label=chars[11].name, color="#6a3a8e",
        image_url=None,
        x=210, y=490, size=1, team="hero",
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
        # v2.49.171 — spellcasting NPC. The party's first encounter
        # with a divine-magic NPC: Soren is a hired Cult Acolyte
        # standing behind Vex's crew, ready to drop a Sacred Flame on
        # the party's healer and reach in with Inflict Wounds when
        # someone gets close. Demonstrates both NPC strike flows in
        # the same combatant: attack-roll spell (Inflict Wounds →
        # /npc_attack picker) and save-DC spell (Sacred Flame → 📋
        # Save announce). No portrait jpg yet — falls back to the
        # color ring + label.
        ("cult-acolyte",   "Soren (Cult Acolyte)",    1190, 490, "#9d4edd", None),
    ]
    for slug, label, x, y, color, image in npc_placements:
        tmpl = templates.get(slug)
        if not tmpl:
            continue
        # v2.99.58 — NPCs default to villain. Same plan-movement-oa-flow
        # Phase 1 reasoning as the hero-tag block above: out-of-the-
        # box same-team filter coverage so Bandit Alpha doesn't OA
        # Bandit Beta on a flanking maneuver, and the demo encounter
        # exercises the team filter end-to-end on the FIRST load.
        tokens.append(Token(
            map_id=map_.id,
            character_id=None,
            token_template_id=tmpl.id,
            label=label,
            color=color,
            image_url=(f"/static/demo/tokens/{image}" if image else None),
            x=x, y=y, size=1, team="villain",
        ))

    # v2.158.99 — Magic-items Phase 6c: cinematic "boss-vs-heroes"
    # spawn. The Young Red Dragon template (v2.158.98) gets dropped
    # at the top of the room — having just crashed through the
    # tavern roof above the bandits. CR 10 vs. Lv 5-9 PCs is
    # deliberately unbalanced; this is a showcase for Caelan's
    # Dragon Slayer rider (v2.158.93 +3d6 fires automatically via
    # the v2.158.96 helper resolution + v2.158.98 template type),
    # not a winnable encounter. A demo GM who wants the playable
    # bandit fight can right-click the dragon → Remove.
    _yrd_tmpl = templates.get("young-red-dragon")
    if _yrd_tmpl is not None:
        tokens.append(Token(
            map_id=map_.id,
            character_id=None,
            token_template_id=_yrd_tmpl.id,
            label="Drakkasha (Young Red Dragon)",
            color="#aa3322",
            image_url=None,  # color ring + label only — no portrait jpg yet
            x=700, y=200, size=2, team="villain",
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

    # v2.49.171 — spellcasting NPC. Cult Acolyte demonstrates both
    # NPC strike flows in a single combatant:
    #   - Inflict Wounds: melee touch attack-roll → /npc_attack (the
    #     server rolls 1d20+4 vs target AC, auto-applies 3d10 necrotic
    #     on hit, all via the existing v2.49.164 weapon-attack pipeline).
    #   - Sacred Flame: DC 13 DEX save, 1d8 radiant, 60 ft → the 📋 Save
    #     button announces the DC + ability to chat and the targeted
    #     PCs roll their own save.
    #   - Dagger backup: regular melee for when out of spells (gives the
    #     GM a non-magical fallback action on the same combatant).
    # Filed via the same v2.3.8 homebrew-monster editor path the Goblin
    # Captain uses; ``_monster_template_to_sheet`` resolves homebrew
    # tier first so the slug ``cult-acolyte`` overlays the
    # TokenTemplate pointer seed_token_templates registers.
    write_homebrew(
        {
            "slug": "cult-acolyte",
            "name": "Cult Acolyte",
            "size": "Medium",
            "type": "Humanoid",
            "alignment": "any evil alignment",
            "armor_class": 12,
            "armor_desc": "leather armor",
            "hit_points": 18,
            "hit_dice": "4d8",
            "speed": {"walk": 30},
            "strength": 10, "dexterity": 14, "constitution": 10,
            "intelligence": 10, "wisdom": 14, "charisma": 11,
            "damage_immunities": "",
            "condition_immunities": "",
            "senses": "passive Perception 12",
            "languages": "any one language (usually Common)",
            "challenge_rating": "1/4",
            "prof_saving_throws": "Wis +4",
            "prof_skills": "Medicine +4, Religion +2",
            "actions": [
                {
                    # v2.49.174: spell_slug references the shared
                    # spell catalog (app/data/local/dnd5e/spells/
                    # inflict-wounds.json) — _resolve_spell_slug_action
                    # in tabletop_routes.py merges the spell's
                    # damage / damage_type / attack_roll / range
                    # fields into this action at sheet-render time.
                    # Monster-only fields here: attack_bonus (caster-
                    # dependent), charges_max (NPC slot equivalent),
                    # name (display label), id (charge-state key).
                    # If the spell catalog gets updated, this NPC's
                    # cast updates with it.
                    "id": "inflict-wounds",
                    "name": "Inflict Wounds (Spell)",
                    "spell_slug": "inflict-wounds",
                    "attack_bonus": "+4",
                    "charges_max": 2,
                    "category": "action",
                },
                {
                    # v2.49.174: same spell-catalog reference for the
                    # save-DC cantrip. save_dc is monster-specific
                    # (caster spellcasting DC = 13 for this acolyte);
                    # everything else comes from sacred-flame.json.
                    "id": "sacred-flame",
                    "name": "Sacred Flame (Cantrip)",
                    "spell_slug": "sacred-flame",
                    "save_dc": 13,
                    "category": "action",
                },
                {
                    # v2.49.217: AoE save-spell exercise. Burning Hands is
                    # a 15-ft cone, 3d6 fire damage, DEX save for half.
                    # Catalog's actions[0].area = {shape: "cone", size_ft: 15}
                    # so the unified mini-sheet's cast handler routes
                    # through _openAoePicker instead of single-target.
                    # Cult Acolyte normally doesn't have this spell —
                    # it's added here purely as a demo exercise for the
                    # /npc_cast_spell AoE multi-target loop (the picker
                    # passes target_combatant_ids to the server, which
                    # loops per-target save + save-for-half damage).
                    "id": "burning-hands",
                    "name": "Burning Hands (Cone)",
                    "spell_slug": "burning-hands",
                    "save_dc": 13,
                    "charges_max": 1,
                    "category": "action",
                },
                {
                    "id": "dagger",
                    "name": "Dagger",
                    "desc": "Melee or Ranged Weapon Attack: +4 to hit, reach 5 ft. or range 20/60 ft., one target. Hit: 4 (1d4 + 2) piercing damage.",
                    "damage": "1d4+2",
                    "damage_type": "piercing",
                    "attack_roll": True,
                    "attack_bonus": "+4",
                    "category": "action",
                },
                {
                    "id": "divine-eminence",
                    "name": "Divine Eminence",
                    "desc": "As a bonus action, the acolyte can expend a spell slot to cause its melee weapon attacks to magically deal an extra 10 (3d6) radiant damage to a target on a hit. (Stub; not mechanically enforced — kept here so the mini-sheet renders the Divine Eminence trait.)",
                    "category": "special_ability",
                },
            ],
            "system": "dnd5e",
            "scope": scope,
            "source": "homebrew",
            "owner": None,
            "_attribution": "Demo seed homebrew (v2.49.171). Authored to showcase the NPC strike flows for both attack-roll spells (Inflict Wounds → /npc_attack) and save-DC spells (Sacred Flame → 📋 Save announce). Stat block loosely inspired by the D&D 5e SRD Acolyte / Cult Fanatic.",
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
    # v2.49.172 — encounter slimmed to 13 entries: 6 PCs + 7 NPCs.
    # The 6 sidelined PCs (Sir Caelan / Lyra / Mira / Garrik / Kael /
    # Rowan) stay in the campaign roster but don't have tokens spawned
    # in seed_tokens, so they're not in init either. Token indices
    # shift accordingly:
    #   tokens[0]   Pip
    #   tokens[1]   Thalindra
    #   tokens[2]   Brother Tavik
    #   tokens[3]   Zara
    #   tokens[4]   Krieger
    #   tokens[5]   Magnus
    #   tokens[6]   Vex (Bandit Captain)     — was 12
    #   tokens[7]   Bandit Alpha             — was 13
    #   tokens[8]   Bandit Beta              — was 14
    #   tokens[9]   Bandit Gamma             — was 15
    #   tokens[10]  Thug                     — was 16
    #   tokens[11]  Grixxa (Goblin Captain)  — was 17
    #   tokens[12]  Soren (Cult Acolyte)     — was 18
    #   tokens[13]  Drakkasha (Young Red Dragon)  — v2.158.99
    # Specs: (token_idx, initiative_roll, hp_max, dex_mod).
    init_specs = [
        # token_idx, init, hp_max, dex_mod
        (11, 18, 36, 3),   # Grixxa (Goblin Captain)
        (6,  17, 65, 3),   # Vex (Bandit Captain)
        (0,  15, 33, 3),   # Pip Quickfingers
        (2,  14, 43, 0),   # Brother Tavik Stonebrow
        (1,  13, 27, 2),   # Thalindra Moonwhisper
        (10, 11, 32, 0),   # Thug
        (3,  10, 37, 2),   # Zara Emberfire
        # v2.158.99 — Drakkasha (Young Red Dragon, CR 10). DEX 10
        # (+0 mod, so init = pure d20 roll). HP 178 RAW. Initiative
        # 10 lands her mid-pack so the dragon isn't a one-shot
        # threat on round 1 — a few PCs act first (Caelan's Dragon
        # Slayer can land before Drakkasha breathes fire).
        (13, 10, 178, 0),  # Drakkasha (Young Red Dragon)
        (7,   9, 11, 1),   # Bandit Alpha
        (8,   7, 11, 1),   # Bandit Beta
        (4,   6, 55, 2),   # Krieger Stonefist
        (9,   5, 11, 1),   # Bandit Gamma
        (5,   3, 38, 2),   # Magnus Hexbinder
        (12,  2, 18, 2),   # Soren (Cult Acolyte) — v2.49.171
    ]
    # v2.99.65 — index PC sheets + template sheets up front so the
    # combatant loop can read the canonical speed without re-querying
    # per-token. _perform_encounter_load also heals missing
    # speed_walk on Load (Pass 3), but writing it at seed time
    # avoids the heal pass for fresh seeds AND makes the hub.set_battle
    # at the bottom of seed_demo_data correct without round-tripping
    # through Load.
    chars_by_id = {c.id: c for c in chars}
    tmpls_by_id: dict[int, TokenTemplate] = {}
    combatants = []
    for token_idx, init_roll, hp_max, dex_mod in init_specs:
        tok = tokens[token_idx]
        _speed_walk = 30
        if tok.character_id and tok.character_id in chars_by_id:
            _sheet = chars_by_id[tok.character_id].sheet or {}
            _v = _sheet.get("speed")
            if isinstance(_v, (int, float)) and _v > 0:
                _speed_walk = int(_v)
            elif isinstance(_v, dict):
                _w = _v.get("walk")
                if isinstance(_w, (int, float)) and _w > 0:
                    _speed_walk = int(_w)
        elif tok.token_template_id:
            if tok.token_template_id not in tmpls_by_id:
                tmpls_by_id[tok.token_template_id] = (
                    db.query(TokenTemplate)
                    .filter(TokenTemplate.id == tok.token_template_id)
                    .first()
                )
            _tmpl = tmpls_by_id.get(tok.token_template_id)
            if _tmpl:
                _tsheet = _tmpl.sheet or {}
                _v = _tsheet.get("speed")
                if isinstance(_v, (int, float)) and _v > 0:
                    _speed_walk = int(_v)
                elif isinstance(_v, dict):
                    _w = _v.get("walk")
                    if isinstance(_w, (int, float)) and _w > 0:
                        _speed_walk = int(_w)
        combatants.append({
            "id": f"tok_{tok.id}_demo",
            "char_id": tok.character_id,
            "token_template_id": tok.token_template_id,
            # v2.99.73 — write source_token_id so the unambiguous
            # v2.6.2 client/server lookup path works on every drag
            # in the demo. Without this, the OA helper's
            # mover_combatant_id resolution + the client's
            # token_move handler + every other source_token_id-keyed
            # join fall back to template+label matching, which fails
            # for NPCs whose label changed since the seed AND
            # silently breaks the OA chain (v2.99.68's auto-roll
            # depends on mover_combatant_id being non-null).
            "source_token_id": tok.id,
            "name": tok.label,
            "initiative": init_roll,
            "hp_current": hp_max,
            "hp_max": hp_max,
            "color": tok.color,
            "dex_mod": dex_mod,
            "image_url": tok.image_url,
            # v2.99.65 — populate speed_walk so the init tracker's
            # Mov chip + /token/move's enforcement read the actual
            # PC/NPC speed from the seed (Krieger 40, Kael 45, Vex
            # 35, etc.). Pre-v2.99.65 the field was dropped and
            # every combatant defaulted to 30.
            "speed_walk": _speed_walk,
            # v2.19.0 Phase C.1: structured buff list (Rage, Hunter's
            # Mark, Hex, Bless, ...). Empty at seed time; /use_rage etc.
            # install entries when fired. Auto-expire ticks down at
            # each turn boundary; client renders one chip per buff.
            "buffs": [],
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
                # v2.99.58 — propagate the v2.99.52 team field through
                # the encounter payload so Load preserves the same-
                # team filter the FIRST tabletop view already
                # exercised.
                "team": t.team or "neutral",
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
            "Tavik unslings his warhammer behind you. Then the roof caves "
            "in: Drakkasha, a young red dragon, crashes down from the rafters "
            "in a shower of timbers — and suddenly nobody cares about the "
            "bandits any more. Initiative is rolled."
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
