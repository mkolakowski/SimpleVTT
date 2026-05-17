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
        "inventory": [
            "Shortsword", "Two daggers", "Thieves' tools", "Burglar's pack",
            "Studded leather armor", "Hooded lantern",
        ],
        "feats": [],
        "resources": [],
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
        "spells": [
            {"name": "Fire Bolt", "level_int": 0, "prepared": True},
            {"name": "Mage Hand", "level_int": 0, "prepared": True},
            {"name": "Prestidigitation", "level_int": 0, "prepared": True},
            {"name": "Magic Missile", "level_int": 1, "prepared": True},
            {"name": "Shield", "level_int": 1, "prepared": True},
            {"name": "Misty Step", "level_int": 2, "prepared": True},
            {"name": "Scorching Ray", "level_int": 2, "prepared": True},
            {"name": "Fireball", "level_int": 3, "prepared": True},
            {"name": "Counterspell", "level_int": 3, "prepared": True},
        ],
        "spell_slots": {
            "wizard": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 3, "used": 0},
                "3": {"total": 2, "used": 0},
            },
        },
        "inventory": [
            "Quarterstaff", "Spellbook", "Component pouch", "Scholar's pack",
            "Robes", "Ink and quill", "Small knife",
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
        "spells": [
            {"name": "Sacred Flame", "level_int": 0, "prepared": True},
            {"name": "Guidance",     "level_int": 0, "prepared": True},
            {"name": "Light",        "level_int": 0, "prepared": True},
            {"name": "Bless",          "level_int": 1, "prepared": True},
            {"name": "Cure Wounds",    "level_int": 1, "prepared": True},
            {"name": "Healing Word",   "level_int": 1, "prepared": True},
            {"name": "Spiritual Weapon", "level_int": 2, "prepared": True},
            {"name": "Hold Person",      "level_int": 2, "prepared": True},
            {"name": "Spirit Guardians",  "level_int": 3, "prepared": True},
            {"name": "Mass Healing Word", "level_int": 3, "prepared": True},
        ],
        "spell_slots": {
            "cleric": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 3, "used": 0},
                "3": {"total": 2, "used": 0},
            },
        },
        "inventory": [
            "Warhammer", "Shield", "Chain mail", "Holy symbol",
            "Priest's pack", "Smith's tools", "Healer's kit",
        ],
        "feats": [],
        "resources": [],
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
    db.add_all([alice_pc, bob_pc, gm_pc])
    db.flush()
    return [alice_pc, bob_pc, gm_pc]


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

    # NPCs — near the bar (right side). v2.3.22: added a Goblin Captain
    # (homebrew, authored through the v2.3.8 structured-action editor) to
    # showcase the unified monster mini-sheet flow on the demo without
    # any GM setup. v2.3.44: every NPC now carries its own portrait jpg
    # — the three bandits use distinct alpha/beta/gamma files so the GM
    # can tell them apart at a glance (same template, different art).
    npc_placements = [
        ("bandit-captain", "Vex (Bandit Captain)",    1100, 400, "#c84a4a", "bandit-captain.jpg"),
        ("bandit",         "Bandit Alpha",            1050, 500, "#c84a4a", "bandit-alpha.jpg"),
        ("bandit",         "Bandit Beta",             1150, 500, "#c84a4a", "bandit-beta.jpg"),
        ("bandit",         "Bandit Gamma",            1100, 600, "#c84a4a", "bandit-gamma.jpg"),
        ("thug",           "Thug",                    1200, 400, "#c84a4a", "thug.jpg"),
        ("goblin-captain", "Grixxa (Goblin Captain)", 1250, 550, "#7c9c54", "goblin-captain.jpg"),
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
) -> Encounter:
    """One pre-staged 'Tavern Brawl' encounter referencing the seeded
    map + tokens with a deterministic initiative order."""
    # Initiative order — pre-rolled, nine entries (3 PCs + 6 NPCs).
    # v2.3.22: Grixxa (Goblin Captain) at the top to showcase the new
    # monster mini-sheet up front.
    # v2.3.25: Brother Tavik (GM's Cleric) added at init 14, between Pip
    # and Thalindra, with the NPC token_idx values shifted by +1 to
    # account for Tavik's token being inserted at index 2 in seed_tokens.
    initiative_order = [
        {"name": "Grixxa (Goblin Captain)", "init": 18, "hp_max": 36, "hp_current": 36, "color": "#7c9c54", "token_idx": 8},
        {"name": "Vex (Bandit Captain)",    "init": 17, "hp_max": 65, "hp_current": 65, "color": "#c84a4a", "token_idx": 3},
        {"name": chars[0].name,             "init": 15, "hp_max": 33, "hp_current": 33, "color": "#6cb4ff", "token_idx": 0},
        {"name": chars[2].name,             "init": 14, "hp_max": 43, "hp_current": 43, "color": "#f5b75c", "token_idx": 2},
        {"name": chars[1].name,             "init": 13, "hp_max": 27, "hp_current": 27, "color": "#4ade80", "token_idx": 1},
        {"name": "Thug",                    "init": 11, "hp_max": 32, "hp_current": 32, "color": "#c84a4a", "token_idx": 7},
        {"name": "Bandit Alpha",            "init":  9, "hp_max": 11, "hp_current": 11, "color": "#c84a4a", "token_idx": 4},
        {"name": "Bandit Beta",             "init":  7, "hp_max": 11, "hp_current": 11, "color": "#c84a4a", "token_idx": 5},
        {"name": "Bandit Gamma",            "init":  5, "hp_max": 11, "hp_current": 11, "color": "#c84a4a", "token_idx": 6},
    ]
    payload = {
        "tokens": [
            {
                "character_id": t.character_id,
                "token_template_id": t.token_template_id,
                "label_override": t.label,
                "color_override": t.color,
                "size": t.size,
                "x": t.x,
                "y": t.y,
                "is_hidden": t.is_hidden,
            }
            for t in tokens
        ],
        "initiative": initiative_order,
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
    db.flush()
    return enc


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
    encounter = seed_encounter(db, camp, map_, tokens, chars)

    db.commit()

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
