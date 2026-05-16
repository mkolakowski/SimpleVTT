"""Demo-mode seed dataset (v2.3.0).

A single source of truth for the public-demo dataset: three users
(GM + two players), one campaign with both players as members, one
battle map referencing a bundled placeholder image, two D&D 5e
characters (Rogue 5 + Wizard 5), seven tokens (2 PCs + 5 NPCs for
the seeded encounter), a small homebrew set, a short roll history,
and one "Tavern Brawl" encounter snapshot.

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
    m = Map(
        campaign_id=camp.id,
        name="The Sundered Tavern",
        image_url="/static/demo/maps/tavern.png",
        grid_size_px=70,
        width_px=1400,
        height_px=900,
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
    db.add_all([alice_pc, bob_pc])
    db.flush()
    return [alice_pc, bob_pc]


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
    clicking on a token can resolve the stat block."""
    specs = [
        ("bandit-captain", "Bandit Captain"),
        ("bandit", "Bandit"),
        ("thug", "Thug"),
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

    # Player tokens — near the door (left side)
    tokens.append(Token(
        map_id=map_.id, character_id=chars[0].id,
        controller_user_id=users["alice"].id,
        label=chars[0].name, color="#6cb4ff",
        image_url="/static/demo/tokens/rogue.png",
        x=200, y=500, size=1,
    ))
    tokens.append(Token(
        map_id=map_.id, character_id=chars[1].id,
        controller_user_id=users["bob"].id,
        label=chars[1].name, color="#4ade80",
        image_url="/static/demo/tokens/wizard.png",
        x=200, y=600, size=1,
    ))

    # NPCs — near the bar (right side)
    npc_placements = [
        ("bandit-captain", "Vex (Bandit Captain)", 1100, 400, "#c84a4a"),
        ("bandit",         "Bandit Alpha",          1050, 500, "#c84a4a"),
        ("bandit",         "Bandit Beta",           1150, 500, "#c84a4a"),
        ("bandit",         "Bandit Gamma",          1100, 600, "#c84a4a"),
        ("thug",           "Thug",                  1200, 400, "#c84a4a"),
    ]
    for slug, label, x, y, color in npc_placements:
        tmpl = templates.get(slug)
        if not tmpl:
            continue
        tokens.append(Token(
            map_id=map_.id,
            character_id=None,
            token_template_id=tmpl.id,
            label=label,
            color=color,
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

    # Custom monster — a flavored variant of the Bandit Captain
    write_homebrew(
        {
            "slug": "goblin-captain",
            "name": "Goblin Captain",
            "size": "Small",
            "type": "humanoid",
            "alignment": "neutral evil",
            "armor_class": 15,
            "armor_desc": "studded leather",
            "hit_points": 24,
            "hit_dice": "7d6",
            "speed": {"walk": 30},
            "strength": 12, "dexterity": 14, "constitution": 12,
            "intelligence": 10, "wisdom": 10, "charisma": 10,
            "challenge_rating": "1",
            "actions": [{
                "id": "scimitar",
                "name": "Scimitar",
                "desc": "Melee Weapon Attack: +4 to hit, reach 5 ft., one target. Hit: 5 (1d6 + 2) slashing damage.",
                "damage": "1d6+2",
                "damage_type": "slashing",
                "attack_roll": True,
                "category": "action",
            }],
            "system": "dnd5e",
            "scope": scope,
            "source": "homebrew",
            "owner": None,
            "_attribution": "Demo seed homebrew (v2.3.0).",
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
    # Initiative order — pre-rolled, seven entries (PCs + 5 NPCs):
    # Vex(17), Pip(15), Thalindra(13), Thug(11), Bandit_α(9), Bandit_β(7), Bandit_γ(5)
    initiative_order = [
        {"name": "Vex (Bandit Captain)", "init": 17, "hp_max": 65, "hp_current": 65, "color": "#c84a4a", "token_idx": 2},
        {"name": chars[0].name,           "init": 15, "hp_max": 33, "hp_current": 33, "color": "#6cb4ff", "token_idx": 0},
        {"name": chars[1].name,           "init": 13, "hp_max": 27, "hp_current": 27, "color": "#4ade80", "token_idx": 1},
        {"name": "Thug",                  "init": 11, "hp_max": 32, "hp_current": 32, "color": "#c84a4a", "token_idx": 6},
        {"name": "Bandit Alpha",          "init":  9, "hp_max": 11, "hp_current": 11, "color": "#c84a4a", "token_idx": 3},
        {"name": "Bandit Beta",           "init":  7, "hp_max": 11, "hp_current": 11, "color": "#c84a4a", "token_idx": 4},
        {"name": "Bandit Gamma",          "init":  5, "hp_max": 11, "hp_current": 11, "color": "#c84a4a", "token_idx": 5},
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
            "orders. The thug cracks his knuckles. Initiative is rolled."
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
def reset_and_reseed(db: Session) -> dict[str, int]:
    """Wipe demo records then re-seed. Returns a per-section count
    suitable for logging on every reset."""
    log.info("demo reset: wiping previous dataset…")
    wipe_counts = wipe(db)
    log.info("demo wipe: %s", wipe_counts)

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
