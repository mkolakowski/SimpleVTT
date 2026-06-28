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
import os
import shutil
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .auth import hash_password
from .campaign_wipe import wipe_campaign_children
from .character_presets import _prof_bonus
from .local_content import HOMEBREW_ROOT, write_homebrew
from .sheet_templates import get_template
from .models import (
    AdminAuditLog,
    Campaign,
    CampaignMembership,
    CampaignNote,
    Character,
    DiceRoll,
    Encounter,
    Handout,
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
# v2.591.0 — the demo grows to several leveled campaigns with shared
# players + a second GM. demo-gm2 holds the app-wide GM role (not site
# admin) and owns one campaign (the level-9 game); carol/dave/erin are
# players shared across campaigns. All share DEMO_PASSWORD.
DEMO_GM2_EMAIL = "demo-gm2@example.com"
DEMO_CAROL_EMAIL = "demo-carol@example.com"
DEMO_DAVE_EMAIL = "demo-dave@example.com"
DEMO_ERIN_EMAIL = "demo-erin@example.com"
DEMO_EMAILS = (
    DEMO_GM_EMAIL, DEMO_ALICE_EMAIL, DEMO_BOB_EMAIL,
    DEMO_GM2_EMAIL, DEMO_CAROL_EMAIL, DEMO_DAVE_EMAIL, DEMO_ERIN_EMAIL,
)
DEMO_PASSWORD = "demopass"
DEMO_CAMPAIGN_NAME = "Demo: The Sundered Vault"
# v2.590.0 — the demo is growing from one campaign to a set of leveled
# sample campaigns (docs/wiki/demo-content.md). The wipe keys on this list
# so every demo campaign is cleaned on reseed; each new campaign appends its
# name here. The Sundered Vault (level 5) stays first so it keeps id 1
# (CAMPAIGN_ID the harness uses).
DEMO_CAMPAIGN_NAMES = (DEMO_CAMPAIGN_NAME,)

_TRUTHY = ("1", "true", "yes", "on")


def _demo_gm_site_admin() -> bool:
    """Whether the demo GM is granted **site-admin** — the ``/admin``
    portal (user management, audit-log viewer, GDPR scrub, ban
    controls). This is distinct from the per-campaign **GM role**,
    which keys off campaign membership (``_user_is_gm`` /
    ``campaign.gm_user_id``) and is unaffected by this flag — the demo
    GM still runs the demo campaign either way.

    Default ON so local dev + CI keep the admin showcase and the
    six admin-portal harness suites (``test_admin_audit`` etc.) pass
    unchanged. **Set ``DEMO_GM_SITE_ADMIN=false`` on any
    internet-facing demo deploy.** The demo credentials are public —
    the login page advertises ``demopass`` — so a site-admin demo GM
    is an open admin backdoor: anyone could reach ``/admin`` and
    scrub the audit log or delete users. Read at call time so a
    reseed (boot or scheduler tick) picks up a runtime flip.
    """
    return os.getenv("DEMO_GM_SITE_ADMIN", "true").strip().lower() in _TRUTHY


# ── Level-N sheet builder (for the leveled sample campaigns) ─────────
def build_dnd5e_sheet(
    name: str,
    *,
    klass: str,
    level: int,
    abilities: dict,
    ac: int,
    hp_max: int,
    subclass: str = "",
    race: str = "",
    attacks: "list | None" = None,
    spells: "list | None" = None,
    spell_slots: "dict | None" = None,
    notes: str = "",
    extra: "dict | None" = None,
) -> dict:
    """Build a playable D&D 5e sheet dict at an arbitrary ``level`` for the
    demo's leveled sample campaigns (docs/wiki/demo-content.md).

    Starts from the blank dnd5e template (so every load-bearing field has a
    default), then sets level + derived proficiency bonus + the curated
    fields. Each PC should include its **level-N showcase feature** as a
    clickable attack/spell/ability (with slots/uses set), and ``notes``
    should carry the three blocks shown on the sheet:

        Description: …  /  Roleplay: …  /  How to play: …

    ``extra`` merges arbitrary additional sheet keys (e.g. ``class_hit_die``,
    ``resources``, ``features``) for per-PC needs.
    """
    sheet = get_template("dnd5e")
    sheet.update({
        "class": klass,
        "subclass": subclass,
        "race": race,
        "level": level,
        "proficiency_bonus": _prof_bonus(level),
        "abilities": abilities,
        "ac": ac,
        "hp": {"current": hp_max, "max": hp_max, "temp": 0},
        "hit_dice": {"current": level, "max": level},
        "attacks": attacks or [],
        "spells": spells or [],
        "spell_slots": spell_slots or {},
        "notes": notes,
    })
    if extra:
        sheet.update(extra)
    # v2.653.0 — backfill subclass features + race traits from the shipped
    # SRD content (offline) so the demo PCs show those sections on a fresh
    # reseed. No-op for non-SRD subclasses/races. See app/demo_features.py.
    from .demo_features import apply_srd_features
    apply_srd_features(sheet)
    return sheet


# ── Wipe ────────────────────────────────────────────────────────────
def wipe(db: Session) -> dict[str, int]:
    """Delete every row tagged as demo. Returns per-table counts."""
    counts: dict[str, int] = {}

    # 1) Find the demo users by email
    demo_users = db.query(User).filter(User.email.in_(DEMO_EMAILS)).all()
    demo_user_ids = [u.id for u in demo_users]
    counts["users_found"] = len(demo_users)

    # 2) Find the demo campaigns by name (defensive — only ours use
    # these exact strings). v2.590.0: a set of leveled sample campaigns —
    # the Sundered Vault (here) + the leveled campaigns registered in
    # demo_campaigns (lazy import to avoid a cycle). Names must all match so
    # each campaign's Tokens/Maps/Characters cascade-clean before the user
    # delete (which would otherwise FK-fail on a still-populated campaign).
    from . import demo_campaigns as _dc
    all_campaign_names = (*DEMO_CAMPAIGN_NAMES, *_dc.campaign_names())
    demo_campaigns = (
        db.query(Campaign).filter(Campaign.name.in_(all_campaign_names)).all()
    )
    demo_campaign_ids = [c.id for c in demo_campaigns]
    counts["campaigns_found"] = len(demo_campaigns)

    if demo_campaign_ids:
        # v2.612.6: the per-campaign child-delete sequence is extracted to
        # ``campaign_wipe.wipe_campaign_children`` so the importer's restore
        # path (backup/export-import arc Phase 7) reuses the exact ordering
        # the demo reseed has relied on. Behavior here is unchanged.
        counts.update(wipe_campaign_children(db, demo_campaign_ids))
        # Evict the in-memory battle cache for every wiped campaign. The
        # `battles` rows are gone (cascade on the campaign delete below +
        # the explicit delete in wipe_campaign_children), but on a
        # *scheduler* reseed the process never restarts, so the hub's RAM
        # cache would keep serving the previous cycle's combatants (stale
        # token ids + spent reactions) — the root cause of OAs not firing
        # and the Dash gate not prompting on reseeded demo campaigns.
        from .realtime import hub as _hub
        for _cid in demo_campaign_ids:
            _hub.evict_battle(_cid)
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
        # v2.495.1: admin_audit_log.actor_user_id is a non-nullable FK
        # to users with no ondelete clause, so once the demo GM has
        # performed any logged admin action (a cloudflare ban/unban, a
        # user purge, an audit-log scrub) those rows RESTRICT the user
        # delete and the whole reseed aborts with a ForeignKeyViolation
        # — which silently froze demo resets on the public instance.
        # The rows are demo-generated audit noise; delete them first.
        counts["admin_audit_log"] = (
            db.query(AdminAuditLog)
            .filter(AdminAuditLog.actor_user_id.in_(demo_user_ids))
            .delete(synchronize_session=False)
        )
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
    login page can advertise it. The GM is site-admin only when
    ``DEMO_GM_SITE_ADMIN`` is on (default; see ``_demo_gm_site_admin``)
    — disable it on public deploys so the well-known demo credentials
    don't grant the ``/admin`` portal. The two players are never
    admin. Per-campaign GM powers are unaffected by the flag."""
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
        is_admin=_demo_gm_site_admin(),
        # v2.584.0 — the demo GM holds the app-wide GM role so they can
        # create campaigns under the new role model. The two players are
        # players (is_gm defaults False) and so are capped + can't create
        # campaigns. See docs/plans/app-wide-roles-and-storage.md.
        is_gm=True,
        roll_log_position="left",
    )
    alice = User(
        email=DEMO_ALICE_EMAIL,
        display_name="Alice (Demo Rogue)",
        password_hash=pw,
        is_admin=False,
        is_gm=False,
    )
    bob = User(
        email=DEMO_BOB_EMAIL,
        display_name="Bob (Demo Wizard)",
        password_hash=pw,
        is_admin=False,
        is_gm=False,
    )
    # v2.591.0 — a second GM (app-wide GM role, NOT site admin) who owns one
    # campaign, plus three more shared players. demo-gm2 demonstrates the
    # role model: a GM who can create/run campaigns without admin-console
    # access (GET /admin still 403s for them).
    gm2 = User(
        email=DEMO_GM2_EMAIL,
        display_name="Demo GM 2 (Saltmarsh)",
        password_hash=pw,
        is_admin=False,
        is_gm=True,
        roll_log_position="left",
    )
    carol = User(email=DEMO_CAROL_EMAIL, display_name="Carol (Demo Paladin)",
                 password_hash=pw, is_admin=False, is_gm=False)
    dave = User(email=DEMO_DAVE_EMAIL, display_name="Dave (Demo Sorcerer)",
                password_hash=pw, is_admin=False, is_gm=False)
    erin = User(email=DEMO_ERIN_EMAIL, display_name="Erin (Demo Druid)",
                password_hash=pw, is_admin=False, is_gm=False)
    db.add_all([gm, alice, bob, gm2, carol, dave, erin])
    db.flush()
    return {"gm": gm, "alice": alice, "bob": bob,
            "gm2": gm2, "carol": carol, "dave": dave, "erin": erin}


def seed_campaign(db: Session, users: dict[str, User]) -> Campaign:
    camp = Campaign(
        name=DEMO_CAMPAIGN_NAME,
        description=(
            "The original hand-built demo campaign (party level ~5–8) — a "
            "full one-of-every-class party in the Tavern Brawl. v2.605.0: "
            "kept as the harness anchor (id 1) but seeded ARCHIVED — it now "
            "lives in the lobby's 'Archived' section as a showcase of the "
            "archive feature, while the fresh 'Demo L5: The Tide-Wracked "
            "Catacombs' is the active Level-5 game in the leveled lineup "
            "(L3 / L5 / L9 / L13 / L18; see the wiki's Demo content guide). "
            "Resets on a fixed interval — anything you change here is wiped soon."
        ),
        gm_user_id=users["gm"].id,
        game_system="dnd5e",
        gm_color="#a78bfa",
        session_active=True,
        session_started_at=datetime.utcnow(),
        # v2.605.0 — seed the original demo as archived (campaign-pc-archive
        # Phase 4). It stays id=1 (the harness CAMPAIGN_ID anchor) and is
        # fully reachable by URL + via the API; it just drops out of the
        # active lobby into the "Archived" section. See
        # docs/plans/campaign-pc-archive.md.
        is_archived=True,
        archived_at=datetime.utcnow(),
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

    # Players join as members; GM is implicit via gm_user_id. v2.596.0 —
    # carol joins too so a player is shared across campaigns (she also plays
    # in the level-3 Goblin Warrens), showing the cross-campaign roster.
    db.add_all([
        CampaignMembership(
            campaign_id=camp.id, user_id=users["alice"].id,
            is_gm=False, color="#6cb4ff",
        ),
        CampaignMembership(
            campaign_id=camp.id, user_id=users["bob"].id,
            is_gm=False, color="#4ade80",
        ),
        CampaignMembership(
            campaign_id=camp.id, user_id=users["carol"].id,
            is_gm=False, color="#f59e0b",
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
        "race": "Lightfoot Halfling",
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
            # v2.318.0 — Magic-items: Sword of Life Stealing (RAW DMG p.206,
            # rare, attunement). Extends the on_nat_20 effect="damage" substrate
            # (Sword of Sharpness precedent above) with the
            # `exempt_creature_types: ["construct", "undead"]` gate. On a nat 20
            # the +3d6 necrotic rider fires unless the target is a construct or
            # undead. Stacks with Pip's existing Sneak Attack 4d6 on crit (both
            # the SA dice AND the rider land — massive single-swing burst). The
            # base attack is a Shortsword line (no +X magic bonus baked in — RAW
            # Sword of Life Stealing doesn't grant a hit/damage bonus, unlike
            # Vorpal or Sun Blade). The temp-HP-equal-to-extra-damage clause is
            # GM-narrated in v1.
            {"name": "Sword of Life Stealing", "attack_bonus": "+6",
             "damage": "1d6+3", "damage_type": "piercing",
             "range": "5 ft", "_slug": "sword-of-life-stealing",
             "desc": "Rare shortsword, attunement. On a natural 20, deal +3d6 necrotic damage to the target (constructs and undead exempt) — RAW DMG p.206. Gain temp HP equal to the extra damage dealt (GM-narrated)."},
            # v2.335.0 — Nine Lives Stealer (RAW DMG p.183, very rare,
            # attunement). The first on_nat_20 `effect: "slay_save"` item: on
            # a natural 20 against a creature with < 100 HP, the target makes
            # a DC 15 CON save or is slain instantly (constructs/undead
            # exempt). The +2 attack/damage is baked into this attack row
            # (Vorpal / Holy Avenger precedent — Pip's Shortsword +6/1d6+3 →
            # +8/1d6+5). The slug gates the rider; the inventory item below
            # (seeded inert) must be PATCHed equipped+attuned by the harness
            # for the dispatcher's attunement check to pass.
            {"name": "Nine Lives Stealer", "attack_bonus": "+8",
             "damage": "1d6+5", "damage_type": "piercing",
             "range": "5 ft", "_slug": "nine-lives-stealer",
             "desc": "Very rare shortsword, attunement. +2 attack/damage; on a natural 20 against a creature with fewer than 100 HP, the target makes a DC 15 CON save or is slain (constructs and undead exempt). 1d8+1 charges (GM-tracked). RAW DMG p.183."},
            # v2.343.0 — Dagger of Venom (RAW DMG p.161, rare, NO attunement).
            # The +1 attack/damage is baked into this row (Pip DEX +3 + prof
            # +3 + magic +1 = +7 / 1d4+4). On a hit the on_hit_save handler
            # fires the new `damage_condition` effect: DC 15 CON save or 2d10
            # poison AND poisoned for 1 minute. No attunement → the rider
            # fires on slug match alone. The coat-the-blade action (1/min
            # usage limit) is GM-narrated in v1. A venom-coated dagger is
            # on-theme for a larcenous Halfling Rogue.
            {"name": "Dagger of Venom", "attack_bonus": "+7",
             "damage": "1d4+4", "damage_type": "piercing",
             "range": "20/60 ft", "_slug": "dagger-of-venom",
             "desc": "Rare dagger, no attunement. +1 attack/damage; on a hit, the target makes a DC 15 CON save or takes 2d10 poison and is poisoned for 1 minute (RAW DMG p.161). The coat-the-blade action (1/min) is GM-narrated."},
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
            # v2.159.28 Phase 2b — weight_lb backfilled per RAW PHB
            # pp.149-151 / DMG p.187. Pip's STR 10 → 150 lb cap.
            {"name": "Shortsword", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "piercing",
             "properties": "finesse, light", "_slug": "shortsword",
             "weight_lb": 2},
            {"name": "Dagger", "type": "weapon", "qty": 2,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d4", "damage_type": "piercing",
             "range": "20/60 ft", "properties": "finesse, light, thrown",
             "_slug": "dagger", "weight_lb": 1},
            {"name": "Studded leather", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "light", "ac_value": 12,
             "_slug": "studded-leather", "weight_lb": 13},
            {"name": "Thieves' tools", "type": "gear", "qty": 1,
             "weight_lb": 1,
             "desc": "Small files, picks, mirror, pliers, scissors. Lets you make Dexterity (Sleight of Hand) checks to disarm traps or pick locks."},
            {"name": "Burglar's pack", "type": "gear", "qty": 1,
             "weight_lb": 42,  # RAW PHB p.151
             "desc": "Backpack, 1,000 ball bearings, 10 ft string, bell, 5 candles, crowbar, hammer, 10 pitons, hooded lantern, 2 flasks of oil, 5 days rations, tinderbox, waterskin, 50 ft hempen rope."},
            {"name": "Hooded lantern", "type": "gear", "qty": 1,
             "weight_lb": 2,
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
            # v2.237.0 — Slippers of Spider Climbing (RAW DMG p.199,
            # uncommon, no attunement). Lets Pip climb vertical surfaces
            # and ceilings hands-free with a climbing speed equal to her
            # walking speed (GM-narrated numeric in v1). Rides the
            # `slippers-of-spider-climbing` catalog payload (`spider_climb`);
            # surfaced on /sheet-json as derived.spider_climb. On-theme for
            # a Halfling Rogue scaling walls. inventory_index 11.
            {"name": "Slippers of Spider Climbing", "type": "gear", "qty": 1,
             "equippable": True, "equipped": True,
             "_slug": "slippers-of-spider-climbing",
             "desc": "Uncommon wondrous item, no attunement. While you wear these light shoes, you can move up, down, and across vertical surfaces and upside down along ceilings, while leaving your hands free. You have a climbing speed equal to your walking speed. RAW DMG p.199."},
            # v2.292.0 — Eyes of Minute Seeing (RAW DMG p.166, uncommon, no
            # attunement). Lenses that grant advantage on Intelligence
            # (Investigation) checks that rely on sight at close range. Rides
            # the same check_advantage_on substrate as Eyes of the Eagle, keyed
            # on Investigation. Seeded equipped (no-attunement, Boots of
            # Elvenkind precedent) — composes freely alongside Pip's full 3/3
            # attunement loadout. On-theme for a Rogue scouring rooms for traps
            # and clues.
            {"name": "Eyes of Minute Seeing", "type": "gear", "qty": 1,
             "equippable": True, "equipped": True,
             "_slug": "eyes-of-minute-seeing",
             "desc": "Uncommon wondrous item, no attunement. While you wear these crystal lenses over your eyes, you have advantage on Intelligence (Investigation) checks that rely on sight while searching an area or studying an object within 1 foot of you. RAW DMG p.166."},
            # v2.277.0 — charged-items Phase 1 (closes the plan): Wand of
            # Enemy Detection (RAW DMG p.211, rare, attunement). The last
            # named plan item — a utility `action_kind: "buff"` charge action
            # (the Gem of Seeing shape): spend 1 of 7 charges to sense the
            # direction of the nearest hostile within 60 ft for 1 minute.
            # On-theme for Pip (Halfling Rogue scout / lookout). Her 4th
            # attuned item (seed-load bypasses the RAW 3-item cap, enforced
            # at /attune runtime only). Paired with the
            # wand-of-enemy-detection resource row below.
            {"name": "Wand of Enemy Detection", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "wand-of-enemy-detection", "weight_lb": 1,
             "desc": "Rare wand, attunement. 7 charges. Expend 1 charge to sense the direction (not distance) of the nearest creature hostile to you within 60 ft for 1 minute — even invisible, ethereal, disguised, or hidden ones. Regains 1d6+1 charges at dawn (long rest). RAW DMG p.211."},
            # v2.283.0 — Carpet of Flying (RAW DMG p.157, very rare, NO
            # attunement). Reuses the v2.238.0 Winged Boots flying-speed
            # substrate with zero new engine code: the `flying_speed` boolean
            # flag rides the `carpet-of-flying` catalog payload, aggregates in
            # `_equipped_item_effects`, and surfaces on /sheet-json as
            # `derived.flying_speed`. Like the Broom of Flying (v2.282.0) it
            # needs NO attunement — its payload omits `requires_attunement`,
            # so it surfaces while merely equipped. The command-word ride +
            # size-keyed 30-80 ft speed / 200-800 lb capacity are GM-narrated
            # in v1. Seeded as inert spare loot (unequipped/unattuned) so it
            # adds no flying speed to Pip's baseline and disturbs no existing
            # test — the harness PATCHes it equipped (no attune needed), reads
            # the derived flag, then restores. An exotic flying carpet is
            # on-theme for the demo's larcenous Halfling Rogue.
            {"name": "Carpet of Flying", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "_slug": "carpet-of-flying", "weight_lb": 0,
             "desc": "Very rare wondrous item, no attunement. Speak its command word as an action to make the carpet hover and fly, moving by your spoken directions while you're within 30 ft of it. Four sizes exist (GM's choice), with flying speeds of 30-80 ft and 200-800 lb capacity. It can carry double its capacity at half speed. RAW DMG p.157."},
            # v2.301.0 — Elven Chain (RAW DMG p.150, rare, NO attunement).
            # A shirt of finely woven silver mesh: "+1 bonus to AC while you
            # wear this armor" — rides the existing `ac_bonus` substrate
            # (cloak/ring/bracers precedent) with zero new engine code. Its
            # payload omits `requires_attunement`, so the +1 applies while
            # merely equipped. The "proficient even without medium-armor
            # proficiency" RAW clause is GM-narrated in v1. Seeded inert
            # (unequipped) so it adds nothing to Pip's baseline AC and
            # disturbs no existing test — the harness PATCHes it equipped,
            # reads the +1 target_ac delta, then restores. A silvery elven
            # mesh shirt is on-theme for the demo's stealthy Halfling Rogue.
            {"name": "Elven Chain", "type": "armor", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "armor_type": "medium", "ac_value": 14,
             "_slug": "elven-chain", "weight_lb": 20,
             "desc": "Rare medium armor (chain shirt), no attunement. You gain a +1 bonus to AC while you wear this armor. You are considered proficient with this armor even if you lack proficiency with medium armor. RAW DMG p.150."},
            # v2.318.0 — Sword of Life Stealing (RAW DMG p.206, rare,
            # attunement). Paired with the attack entry above via `_slug`. The
            # nat-20 +3d6 necrotic rider fires from the v2.158.101 on_nat_20
            # post-hit handler when (a) the d20 lands natural 20, (b) the item
            # is equipped + attuned, and (c) the target isn't a construct or
            # undead. v2.318.1 — reseated INERT (equipped=False, attuned=False)
            # as spare loot, aligning with the recent house pattern (v2.315.0
            # Scimitar of Speed on Caelan, v2.279.0 Cloak of Arachnida on Lyra,
            # v2.303.0 Boots of Striding and Springing on Caelan). The earlier
            # v2.318.0 seed-attuned shape followed the older Garrik / Lyra
            # over-cap seed precedent, but seed-inert is now the preferred
            # default — the harness PATCHes the inventory equipped+attuned via
            # /sheet-fields (which bypasses the /attune 3-item cap), runs the
            # rider tests, then restores. Pip stays at the same 4 seed-attuned
            # items she had pre-v2.318.0 (Cloak + Ring + Sharpness + Wand).
            # When the test does PATCH it active, two on_nat_20 swords on one PC
            # stress the catalog's per-slug dispatch — Sharpness fires its +4d6
            # slashing on a Sharpness swing, Life Stealing fires its +3d6
            # necrotic on a Life Stealing swing, each gated independently by
            # the attack's `_slug` matching its inventory item.
            {"name": "Sword of Life Stealing", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "hands": 1, "damage": "1d6", "damage_type": "piercing",
             "properties": "finesse, light, magic",
             "_slug": "sword-of-life-stealing", "weight_lb": 2,
             "desc": "Rare shortsword, attunement. When you attack a creature with this magic weapon and roll a 20 on the attack roll, that target takes an extra 3d6 necrotic damage, provided the target isn't a construct or undead. You also gain temporary hit points equal to the extra damage dealt (GM-narrated). RAW DMG p.206."},
            # v2.325.0 — Wand of Secrets (RAW DMG p.211, uncommon, no
            # attunement). Direct clone of v2.324.0 Wand of Magic Detection's
            # action_kind: "buff" substrate; only buff_key + duration_rounds
            # (1 = single whisper, vs Detect Magic's 100-round concentration)
            # differ. 3 charges, regain 1d3/dawn. On theme for Pip — a Halfling
            # Rogue scout who hunts traps and hidden doors. No attunement so
            # it doesn't bump her seed-attuned roster.
            {"name": "Wand of Secrets", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 1,
             "_slug": "wand-of-secrets",
             "desc": "Uncommon wand, no attunement. 3 charges. Action: expend 1 charge — the wand whispers the distance and direction of any secret door or trap within 30 ft. Regains 1d3 charges on long rest. RAW DMG p.211."},
            # v2.327.0 — "The Wayfarer's Trio" bundle: Rope of Climbing (RAW
            # DMG p.197, uncommon, no attunement). 60-ft silk rope (3 lb,
            # holds 3000 lb). Command word animates it; bonus action commands
            # the other end to a destination (10 ft/turn). Knot mode adds
            # advantage on climb checks (50 ft length). Pure GM-narrated
            # mechanic; catalog row is a stub passive so the slug counts in
            # the audit. Thematic on Pip (Halfling Rogue scout — climbing
            # and stealth fit her toolkit).
            {"name": "Rope of Climbing", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 3,
             "_slug": "rope-of-climbing",
             "desc": "Uncommon wondrous item, no attunement. 60-ft silk rope (holds 3000 lb). Command word animates the rope; bonus action commands the other end to a destination 10 ft/turn. The rope can also fasten, unfasten, knot (adds advantage on climb checks; rope shortens to 50 ft), unknot, or coil itself. AC 20, 20 HP, regenerates 1 HP per 5 min. RAW DMG p.197."},
            # v2.333.0 — "The Artisan's Spread" bundle: Chime of Opening
            # (RAW DMG p.158, rare, no attunement). 1-lb hollow metal
            # tube. 10 charges (regain all at dawn). Action: hold + strike
            # the chime within 120 ft of a locked / bound object (door,
            # chest, manacles, knot) — the chime emits a clear tone that
            # opens the target if its DC ≤ 10. Stub catalog row; the
            # 10-charge counter + per-strike DC test are GM-narrated.
            # Thematic on Pip (Halfling Rogue scout — silent unlock chimes
            # pair nicely with her Wand of Secrets + Slippers of Spider
            # Climbing toolkit).
            {"name": "Chime of Opening", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 1,
             "_slug": "chime-of-opening",
             "desc": "Rare wondrous item, no attunement. 1-lb hollow metal tube. 10 charges (regain all at dawn). Action: strike the chime within 120 ft of a locked or bound object (door, chest, manacles, knot, padlock); the tone opens the target if its DC ≤ 10. RAW DMG p.158."},
            # v2.335.0 — Nine Lives Stealer (RAW DMG p.183, very rare,
            # attunement). Paired with the attack entry above via `_slug`.
            # Seeded INERT (equipped=False, attuned=False) per the v2.318.1
            # spare-loot precedent — the harness PATCHes it equipped+attuned
            # via /sheet-fields (bypassing the /attune cap, since Pip is
            # already at 4+ seed-attuned), seeds a nat-20 roll, and asserts
            # the slay fires on a failed CON save. Pip's third on_nat_20
            # sword (after Sharpness + Life Stealing) — each gated
            # independently by its attack's `_slug`. A grim soul-stealing
            # blade is fitting loot for a larcenous Halfling Rogue.
            {"name": "Nine Lives Stealer", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "hands": 1, "damage": "1d6", "damage_type": "piercing",
             "properties": "finesse, light, magic",
             "_slug": "nine-lives-stealer", "weight_lb": 2,
             "desc": "Very rare shortsword, attunement. +2 attack/damage. The sword has 1d8+1 charges. On a critical hit against a creature with fewer than 100 HP, that creature makes a DC 15 CON save or is slain instantly (a construct or undead is immune). The sword loses 1 charge per slay; when out of charges it loses this property. RAW DMG p.183."},
            # v2.337.0 — "The Bottled Tempest" bundle: Eversmoking Bottle
            # (RAW DMG p.168, uncommon, no attunement). A brass bottle. Action:
            # remove the stopper — a 60-ft-radius cloud of thick smoke
            # (heavily obscured) billows out, growing 10 ft/round up to 60 ft
            # and lasting until the stopper is replaced (a wind disperses it
            # over rounds). Stub catalog row; the smoke cloud + obscure
            # mechanic are GM-narrated. Thematic on Pip (Halfling Rogue scout
            # — an instant smoke-screen escape pairs with her stealth kit).
            {"name": "Eversmoking Bottle", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 1,
             "_slug": "eversmoking-bottle",
             "desc": "Uncommon wondrous item, no attunement. A brass bottle. Action: remove the stopper — a cloud of thick smoke (heavily obscured) pours out in a 60-ft radius, growing 10 ft/round to that max, and lasting until the stopper is replaced. A moderate+ wind disperses it over rounds. RAW DMG p.168."},
            # v2.343.0 — Dagger of Venom (RAW DMG p.161, rare, NO attunement).
            # Paired with the attack entry above via `_slug`. No attunement →
            # the on_hit_save (DC 15 CON or 2d10 poison + poisoned) fires on
            # slug match alone, so it's seeded equipped (no PATCH-in-test).
            # The coat-the-blade action (1/min usage limit) is GM-narrated.
            {"name": "Dagger of Venom", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True,
             "hands": 1, "damage": "1d4", "damage_type": "piercing",
             "range": "20/60 ft", "properties": "finesse, light, thrown, magic",
             "_slug": "dagger-of-venom", "weight_lb": 1,
             "desc": "Rare dagger, no attunement. +1 attack/damage. You can coat the blade with poison as an action (lasts 1 min or until a hit). On a hit, the target makes a DC 15 CON save or takes 2d10 poison damage and is poisoned for 1 minute. RAW DMG p.161."},
        ],
        "feats": [],
        "resources": [
            # v2.277.0 — Wand of Enemy Detection charge pool: 7 charges,
            # regain 1d6+1 at dawn (long rest). The buff handler decrements
            # 1 per Detect Enemies activation.
            {
                "key": "wand-of-enemy-detection",
                "name": "Wand of Enemy Detection",
                "current": 7, "max": 7, "reset": "long",
                "charge_recovery": "1d6+1",
                "source": "item-wand-of-enemy-detection",
                "desc": "7 charges. Spend 1 to sense the direction of the nearest hostile within 60 ft for 1 minute. Regains 1d6+1 charges on long rest.",
                "manual": False,
            },
            # v2.325.0 — Wand of Secrets charge pool: 3 charges, regain 1d3
            # at dawn (long rest). Each charge triggers a single-round
            # secrets-detection whisper (30-ft radius secret-door & trap).
            {
                "key": "wand-of-secrets",
                "name": "Wand of Secrets",
                "current": 3, "max": 3, "reset": "long",
                "charge_recovery": "1d3",
                "source": "item-wand-of-secrets",
                "desc": "3 charges. Spend 1 to sense the distance and direction of any secret door or trap within 30 ft (single whisper). Regains 1d3 charges on long rest.",
                "manual": False,
            },
            # v2.403.4 — magic-items-automation Phase 9.2 batch 5:
            # Chime of Opening (RAW DMG p.158) — 10 lifetime uses, then
            # cracks. The chime is seeded equipped on Pip (line ~600).
            # `reset: "none"` — counter never refills; at 0 the chime
            # breaks (GM-narrated removal from inventory).
            {
                "key": "chime-of-opening",
                "name": "Chime of Opening",
                "current": 10, "max": 10, "reset": "none",
                "source": "item-chime-of-opening",
                "desc": "10 lifetime uses. Action: strike the chime at a locked / bound object within 120 ft; one lock or latch opens. After the 10th use the chime cracks and becomes useless. RAW DMG p.158.",
                "manual": False,
            },
        ],
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
        "race": "High Elf",
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
            # AoE picker (100 ft × 5 ft from the caster). NOTE: harness
            # spell_index constants (e.g. FIREBALL_INDEX in
            # tests/harness/test_cast_spell_aoe.py) index the *stored*
            # sheet, whose order differs from this source list and has
            # since drifted — Fireball now resolves at stored index 10,
            # not 7. Adding/reordering spells here can shift those
            # constants; update the test files, don't assume a fixed index.
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
            # Appended at the end so it doesn't shift earlier spells'
            # positions. Harness spell_index constants are pinned in the
            # test files (see test_cast_spell_aoe.py) and resolve against
            # the stored sheet — don't assume a fixed FIREBALL_INDEX here.
            {"name": "Sleep", "level": 1, "prepared": True, "_slug": "sleep", "casting_time": "1 action"},
            # v2.72.0 Phase 3d — Silvery Barbs (Strixhaven: SAI p.144).
            # Appended at the END of the spell list so it doesn't shift
            # earlier spells' positions (harness spell_index constants
            # live in the test files; see test_cast_spell_aoe.py).
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
            # v2.404.2 — Fly (Wizard / Sorcerer / Warlock L3). RAW PHB
            # p.244: touch a willing creature, gains 60 ft flying speed
            # for up to 10 min (concentration). Upcast: +1 target per slot
            # above 3rd. Demo fixture for the v2.404.2
            # `_SPELL_BUFF_MAP["fly"]` cap + extras (1 + (slot - 3) * 1).
            # Thalindra has L3 + L4 slots so the test exercises both base
            # cap and the +1 upcast extension. Appended at END so existing
            # spell_index assertions stay valid.
            {"name": "Fly", "level": 3, "prepared": True, "_slug": "fly", "casting_time": "1 action"},
            # v2.404.5 — Charm Person (Bard / Druid / Sorcerer / Warlock /
            # Wizard L1). RAW PHB p.221: WIS save vs Charmed for 1 hour,
            # no concentration. Upcast: +1 target per slot above 1st.
            # Demo fixture for the v2.404.5 `_SPELL_TARGET_CAPS["charm-person"]`
            # entry (1 + (slot - 1) * 1). Thalindra has L1 + L2 slots
            # natively (4/3) so the test exercises both base cap and +1
            # upcast extension. Appended at END so existing spell_index
            # assertions stay valid.
            {"name": "Charm Person", "level": 1, "prepared": True, "_slug": "charm-person", "casting_time": "1 action"},
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
            # v2.159.28 Phase 2b — weight_lb backfilled per RAW PHB
            # pp.149-151. Thalindra's STR 8 → 120 lb cap.
            {"name": "Quarterstaff", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "bludgeoning",
             "versatile": True, "properties": "versatile (1d8)",
             "_slug": "quarterstaff", "weight_lb": 4},
            {"name": "Spellbook", "type": "gear", "qty": 1, "weight_lb": 3,
             "desc": "Contains Thalindra's prepared spells + rituals. Required after a long rest to swap which spells are prepared."},
            {"name": "Component pouch", "type": "gear", "qty": 1, "weight_lb": 2,
             "desc": "A small leather belt pouch holding all material components needed to cast spells that don't list a specific costly component."},
            {"name": "Scholar's pack", "type": "gear", "qty": 1, "weight_lb": 10,
             "desc": "Backpack, book of lore, bottle of ink, ink pen, 10 sheets of parchment, small bag of sand, small knife."},
            {"name": "Robes", "type": "gear", "qty": 1, "weight_lb": 4,
             "desc": "Long flowing wizard's robes. Cosmetic — no mechanical effect."},
            {"name": "Ink and quill", "type": "gear", "qty": 1,
             "desc": "Bottle of black ink + writing quill. Required for spellbook transcription + ritual notation."},
            {"name": "Small knife", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": False, "hands": 1,
             "damage": "1d4", "damage_type": "piercing",
             "properties": "finesse, light", "_slug": "dagger", "weight_lb": 1},
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
            # v2.217.0 — the timed half of the ability-score override engine
            # (docs/plans/str-override.md Phase 4). Potion of Hill Giant
            # Strength (RAW DMG p.187, uncommon): drink → STR becomes 21 for
            # 1 hour, no concentration. Seeded on Thalindra (frail Wizard,
            # STR 8) so the boost is dramatic (mod -1 → +5) and there's no
            # equipped STR override to confound the read. The tier rides
            # `_ability_set` (mirrors the Belt of Giant Strength override),
            # stamped onto the installed buff at drink time.
            {"name": "Potion of Hill Giant Strength", "type": "consumable",
             "qty": 1, "consumable": True, "equipped": True,
             "_slug": "potion-of-giant-strength",
             "_ability_set": {"STR": 21}, "weight_lb": 0.5,
             "desc": "Drink (action, /use_item_action drink) to set your Strength score to 21 (only if higher) for 1 hour, no concentration. RAW DMG p.187 (Hill Giant tier)."},
            # v2.263.0 — charged-items Phase 1. Wand of Web (RAW DMG
            # p.213, rare, attunement). 7 charges; expend exactly 1 to
            # cast Web (DC 15, 20-ft cube, restrained on a failed DEX
            # save). No upcast RAW (min == max == 1). Seeded on
            # Thalindra (Wizard) — Web is a wizard spell and she already
            # carries the Fireballs wand, so two charge wands on one
            # caster is on-theme. Her 4th attuned item (seed-load
            # bypasses the RAW 3-item cap, enforced at /attune runtime
            # only). Paired with the wand-of-web resource row below.
            {"name": "Wand of Web", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "wand-of-web",
             "desc": "Rare wand, attunement. 7 charges. Expend 1 charge to cast Web (save DC 15) — a 20-ft cube of sticky webbing; a creature that fails a DEX save is restrained. Regains 1d6+1 charges at dawn (long rest). RAW DMG p.213."},
            # v2.267.0 — charged-items Phase 2: Staff of Frost (RAW DMG
            # p.202, very rare, attunement). 10 charges; the marquee
            # action expends 5 to cast Cone of Cold (8d8 cold, CON save
            # at her spell save DC, 60-ft cone). Thematic on Thalindra —
            # Cone of Cold is on the Wizard list. Her 5th attuned item
            # (seed-load bypasses the RAW 3-item cap, enforced at /attune
            # runtime only). Paired with the staff-of-frost resource row.
            {"name": "Staff of Frost", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "staff-of-frost", "weight_lb": 4,
             "desc": "Very rare staff, attunement. 10 charges. Cast Cone of Cold (5 charges → 8d8 cold, CON save, 60-ft cone), Fog Cloud (1), Ice Storm (4), or Wall of Ice (4) using your spell save DC. Regains 1d6+4 charges at dawn (long rest). RAW DMG p.202."},
            # v2.274.0 — charged-items Phase 2: Staff of Power (RAW DMG
            # p.202, very rare, attunement) — the iconic archmage's staff.
            # Two halves: (1) a PASSIVE +2 to AC / saving throws / spell
            # attack rolls while held (rides _MAGIC_ITEM_PASSIVES) and (2)
            # a 20-charge spell list. v1 ships the three save-for-half AoE
            # spells — Fireball + Lightning Bolt (both at 5th level, 10d6)
            # and Cone of Cold (8d8) — through the generalized handler at
            # her spell save DC. Thalindra (Wizard) is the canonical
            # wielder. Seed-load bypasses the RAW 3-item attunement cap
            # (enforced at /attune runtime only). Paired with the
            # staff-of-power resource row below. The +2 quarterstaff melee
            # bonus, the non-damaging spells (Magic Missile / Hold Monster
            # / Levitate / Globe of Invulnerability / Wall of Force / Ray
            # of Enfeeblement), and Retributive Strike are GM-narrated.
            {"name": "Staff of Power", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "staff-of-power", "weight_lb": 4,
             "desc": "Very rare staff, attunement by a sorcerer/warlock/wizard. While held: +2 AC, +2 saving throws, +2 spell attack rolls (and a +2 magic quarterstaff). 20 charges (regain 2d8+4 at dawn). Cast Cone of Cold (5 → 8d8 cold, CON), Fireball / Lightning Bolt (5 each → 10d6, 5th-level, DEX), plus Globe of Invulnerability, Hold Monster, Levitate, Magic Missile, Ray of Enfeeblement, and Wall of Force using your spell save DC. RAW DMG p.202."},
            # v2.280.0 — Helm of Brilliance (RAW DMG p.173, very rare,
            # attunement). RAW grants several benefits; v1 wires only the
            # clean passive — "as long as the helm has at least one ruby, you
            # have resistance to fire damage" — via the `resistance_to: "fire"`
            # payload (the Ring of Resistance / Dragon Scale Mail substrate).
            # The gem-fueled spells (daylight / fireball / prismatic spray /
            # wall of fire), the undead-radiant aura, the flaming-weapon rider,
            # and the gem-burst hazard are GM-narrated. Spare loot (equipped=
            # False / attuned=False): Thalindra is already past the attunement
            # cap and has no fire-resistance baseline, so the harness test
            # PATCHes the helm equipped+attuned, reads the fire
            # `derived.resistances`, then restores. A bejeweled archmage's helm
            # is on-theme for an Evoker who already wields a Staff of Power.
            {"name": "Helm of Brilliance", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "_slug": "helm-of-brilliance", "weight_lb": 3,
             "desc": "Very rare wondrous item, attunement. Set with diamonds, rubies, fire opals, and opals. While it has a ruby, you have resistance to fire damage. Gem-fueled spells (daylight, fireball, prismatic spray, wall of fire), an undead-searing aura, and a flaming-weapon rider are GM-narrated. RAW DMG p.173."},
            # v2.287.0 — Robe of Stars (RAW DMG p.193, very rare, attunement).
            # The clean passive — "+1 bonus to saving throws while you wear it"
            # — rides the `save_bonus` substrate (the Cloak of Protection
            # path). The six magic-missile stars and the Astral-Plane travel
            # clause are GM-narrated. Spare loot (equipped=False / attuned=
            # False): Thalindra is already past the attunement cap, so the
            # harness test PATCHes the robe equipped+attuned, rolls a save and
            # asserts the +1 + source attribution, then restores. A starry
            # archmage's robe is on-theme for an Evoker with a Staff of Power.
            {"name": "Robe of Stars", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "_slug": "robe-of-stars", "weight_lb": 0,
             "desc": "Very rare wondrous item, attunement. +1 bonus to saving throws while worn. Six stars cast magic missile (5th-level) as an action, and you can step onto the Astral Plane — both GM-narrated. RAW DMG p.193."},
            # v2.294.0 — Amulet of Proof against Detection and Location (RAW
            # DMG p.150, uncommon, attunement). The "and Location" sibling of
            # the v2.234.0 Amulet of Proof against Detection — identical RAW
            # text ("hidden from divination magic; can't be targeted by such
            # magic or perceived through magical scrying sensors") and the same
            # `scry_proof` boolean substrate. Seeded as inert spare loot
            # (unequipped/unattuned) so it adds no flag to Thalindra's baseline
            # (she carries no other scry-proof item) — the harness PATCHes it
            # equipped+attuned, reads derived.scry_proof, then restores. A
            # cautious archmage warding off scrying is on-theme.
            {"name": "Amulet of Proof against Detection and Location", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False, "weight_lb": 0,
             "_slug": "amulet-of-proof-against-detection-and-location",
             "desc": "Uncommon wondrous item, attunement. While wearing this amulet, you are hidden from divination magic. You can't be targeted by such magic or perceived through magical scrying sensors. RAW DMG p.150."},
            # v2.298.0 — Robe of the Archmagi (RAW DMG p.193, legendary,
            # attunement). Lands on the v2.297.0 `spell_save_advantage`
            # substrate: "advantage on saving throws against spells and other
            # magical effects." Spare loot (equipped=False / attuned=False):
            # Thalindra carries no other spell-save-advantage item so her
            # baseline cleanly proves the robe is the source — the harness
            # PATCHes it equipped+attuned, rolls a vs_spell save and asserts the
            # 2d20kh1 advantage + source, then restores. Base AC 15+Dex (worn
            # unarmored) and +2 spell save DC / spell attack are GM-narrated. An
            # archmage's robe is on-theme for an Evoker with a Staff of Power.
            {"name": "Robe of the Archmagi", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False, "weight_lb": 0,
             "_slug": "robe-of-the-archmagi",
             "desc": "Legendary wondrous item, attunement. While wearing the robe: base AC 15 + your Dexterity modifier if unarmored; advantage on saving throws against spells and other magical effects; and your spell save DC and spell attack bonus each increase by 2. RAW DMG p.193."},
            # v2.307.0 — Helm of Telepathy (RAW DMG p.169, uncommon,
            # attunement). The always-on passive — the ability to communicate
            # telepathically — rides the `telepathy` boolean substrate (the
            # mind_shield / feather_fall flag path); it surfaces on /sheet-json
            # as derived.telepathy, attunement-gated. The detect-thoughts (action)
            # and 1/dawn suggestion casts are GM-narrated. Spare loot (equipped=
            # False / attuned=False): Thalindra carries no other telepathy item
            # so her baseline cleanly proves the helm is the source — the harness
            # PATCHes it equipped+attuned, reads derived.telepathy, then restores.
            # A mind-reading helm is on-theme for a calculating Evoker.
            {"name": "Helm of Telepathy", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False, "weight_lb": 3,
             "_slug": "helm-of-telepathy",
             "desc": "Uncommon wondrous item, attunement. While wearing this helm, you can communicate telepathically with a creature you focus on, cast detect thoughts (action, save DC 13), and once per dawn cast suggestion (save DC 13) on a creature you are reading. RAW DMG p.169."},
            # v2.313.0 — Tome of Clear Thought (RAW DMG p.208, very rare, no
            # attunement). Reconciliation-plan Phase 2: completing the Tome
            # trio on the `permanent_boost` path (the same archetype as Lyra's
            # Tome of Leadership and Influence). Studying it for 48 hours over
            # 6 days permanently raises INT by 2 (and its maximum). Read via
            # /use_item_action's `read` action → _use_item_action_permanent_boost
            # edits sheet.abilities.INT and consumes the book. Seeded on
            # Thalindra (Wizard, INT 17 — her key stat); she carries NO INT
            # override (the Headband of Intellect lives on Mira), so the read
            # cleanly takes effective INT 17 → 19. Appended at END so existing
            # inventory-index assertions stay valid.
            {"name": "Tome of Clear Thought", "type": "magic",
             "qty": 1, "consumable": True, "weight_lb": 5,
             "_slug": "tome-of-clear-thought",
             "desc": "Very rare wondrous item. Studying it for 48 hours over 6 days permanently increases your Intelligence score by 2 (and its maximum). The tome then loses its magic for a century. RAW DMG p.208."},
            # v2.324.0 — Wand of Magic Detection (RAW DMG p.210, uncommon, NO
            # attunement). 3 charges, regain 1d3 at dawn (long rest). Action:
            # expend 1 charge → cast Detect Magic (30-ft radius, 10 min
            # concentration). Clean clone of v2.277.0 Wand of Enemy Detection's
            # `action_kind: "buff"` substrate — only buff_key + summary differ.
            # No attunement, so it adds nothing to Thalindra's already-past-cap
            # roster (she's at 5+ seed-attuned). On theme for an Evoker who
            # surveys arcane auras around her. Paired with the
            # wand-of-magic-detection resource row below.
            {"name": "Wand of Magic Detection", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 1,
             "_slug": "wand-of-magic-detection",
             "desc": "Uncommon wand, no attunement. 3 charges. Action: expend 1 charge to cast Detect Magic (30-ft radius, 10-min concentration). Regains 1d3 charges at dawn (long rest). RAW DMG p.210."},
            # v2.328.0 — "The Inventor's Trio" bundle: Universal Solvent (RAW
            # DMG p.209, legendary, no attunement). 1-oz tube of strongly-
            # alcoholic liquid. Action: pour onto a surface within reach to
            # dissolve up to 1 sq ft of adhesive (including Sovereign Glue).
            # Catalog stub passive — the dissolve mechanic is GM-narrated.
            # Thematic on Thalindra (Wizard — alchemy / lab-experiment fits
            # an Evoker scholar).
            {"name": "Universal Solvent", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 1,
             "_slug": "universal-solvent",
             "desc": "Legendary wondrous item, no attunement. 1 oz of strongly alcoholic liquid in a glass tube. Action: pour onto a surface within reach to dissolve up to 1 sq ft of any adhesive, including Sovereign Glue. RAW DMG p.209."},
            # v2.333.0 — "The Artisan's Spread" bundle: Marvelous Pigments
            # (Nolzur's Marvelous Pigments) (RAW DMG p.183, very rare, no
            # attunement). 2-lb wooden box with 1d4 pots of paint + a fine
            # brush. Action: paint a 2D image of any object on a flat
            # surface (10 min/cubic foot, up to 1000 cubic feet over 10
            # min); the painted object becomes a real 3D object the next
            # round, persisting until destroyed normally. Stub catalog
            # row; the paint→reality mechanic is GM-narrated. Thematic on
            # Thalindra (Wizard Evoker — Pigments paired with her Universal
            # Solvent for a "create then dissolve" alchemy demo).
            {"name": "Marvelous Pigments", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 2,
             "_slug": "marvelous-pigments",
             "desc": "Very rare wondrous item, no attunement. 2-lb wooden box: 1d4 paint pots + a fine brush. Action over 10 min: paint a 2D image on a flat surface — up to 1000 cubic feet of representational content. Next round the painted object becomes real and persists until destroyed normally. RAW DMG p.183."},
            # v2.334.0 — "The Diviner's Hoard" bundle: Cubic Gate (RAW DMG
            # p.165, legendary, no attunement). 3-in. cube with six faces,
            # each keyed to a different plane of existence. Action: press
            # a face to attune the cube to that plane; press it again to
            # cast Gate (DC 17) targeting that plane (consumes the cube's
            # daily charge — once per day per face). Stub catalog row; the
            # planar targeting + travel mechanic is GM-narrated. Thematic
            # on Thalindra (Wizard Evoker — six-plane gate fits her
            # research scholar aesthetic and pairs with her Cone of Cold
            # / Frost Brand cold/elemental theme for outer-plane visits).
            {"name": "Cubic Gate", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 0.5,
             "_slug": "cubic-gate",
             "desc": "Legendary wondrous item, no attunement. 3-in. cube with six faces (each keyed to a different plane). Action: press a face to attune the cube; press again to cast Gate (DC 17) targeting that plane. Each face has 1 daily charge (regain all at dawn). RAW DMG p.165."},
            # v2.404.0 — Phase 9.3 umbrella-slug closure: Spell Scroll
            # (RAW DMG p.200). The single SRD slug covers all spell
            # levels; the spell is keyed by the inventory item's
            # `_spell_slug` field. Seeded equipped on Thalindra (Wizard
            # — natural scroll-scribe) with Magic Missile as the demo
            # spell. The `_use_item_action_spell_scroll` handler
            # consumes the scroll on use and broadcasts the spell
            # cast; the spell's effect resolves via the standard
            # spell-casting pipeline.
            {"name": "Spell Scroll (Magic Missile)", "type": "magic",
             "qty": 1, "equippable": True, "equipped": True,
             "consumable": True, "weight_lb": 0,
             "_slug": "spell-scroll",
             "_spell_slug": "magic-missile",
             "_spell_name": "Magic Missile",
             "desc": "Common consumable. Action: read the scroll to cast Magic Missile (1st-level, 3 darts × 1d4+1 force). The scroll crumbles to dust on use. RAW DMG p.200."},
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
            # v2.263.0 — charged-items Phase 1: Wand of Web charge
            # counter. Same 7-charge / 1d6+1 recharge shape as the
            # Fireballs wand; the spell + base slot live in the catalog
            # (Web + base 2, fixed single-charge spend). Paired with the
            # Wand of Web entry in Thalindra's inventory above.
            {
                "key": "wand-of-web",
                "name": "Wand of Web",
                "current": 7, "max": 7, "reset": "long",
                "charge_recovery": "1d6+1",
                "source": "item-wand-of-web",
                "desc": "7 charges. Spend 1 to cast Web (DC 15) at slot level 2. Regains 1d6+1 charges on long rest.",
                "manual": False,
            },
            # v2.267.0 — charged-items Phase 2: Staff of Frost charge
            # counter. 10 starting charges, regains 1d6+4 at dawn (long
            # rest) via the Phase 4b dice-expression recharge path. The
            # marquee Cone of Cold action spends 5 from this resource.
            # Paired with the Staff of Frost entry in Thalindra's
            # inventory above.
            {
                "key": "staff-of-frost",
                "name": "Staff of Frost",
                "current": 10, "max": 10, "reset": "long",
                "charge_recovery": "1d6+4",
                "source": "item-staff-of-frost",
                "desc": "10 charges. Cast Cone of Cold (5 charges → 8d8 cold, CON save), Fog Cloud (1), Ice Storm (4), or Wall of Ice (4). Regains 1d6+4 charges on long rest.",
                "manual": False,
            },
            # v2.274.0 — charged-items Phase 2: Staff of Power charge
            # counter. 20 starting charges, regains 2d8+4 at dawn (long
            # rest) via the Phase 4b dice-expression recharge path. Each
            # of the three marquee spells (Fireball / Lightning Bolt /
            # Cone of Cold) spends 5 from this resource. Paired with the
            # Staff of Power entry in Thalindra's inventory above.
            {
                "key": "staff-of-power",
                "name": "Staff of Power",
                "current": 20, "max": 20, "reset": "long",
                "charge_recovery": "2d8+4",
                "source": "item-staff-of-power",
                "desc": "20 charges. Cast Fireball / Lightning Bolt (5 each → 10d6, 5th-level, DEX save) or Cone of Cold (5 → 8d8 cold, CON save) at your spell save DC; plus Globe / Hold Monster / Levitate / Magic Missile / Ray of Enfeeblement / Wall of Force. Regains 2d8+4 charges on long rest.",
                "manual": False,
            },
            # v2.324.0 — Wand of Magic Detection (RAW DMG p.210, uncommon, no
            # attunement). 3 starting charges, regains 1d3 at dawn (long rest)
            # via the standard dice-expression recharge path. The action
            # decrements 1 per Detect Magic activation, installing the
            # `magic-detection` buff (100-round / 10-min duration). Paired
            # with the Wand of Magic Detection inventory entry above.
            {
                "key": "wand-of-magic-detection",
                "name": "Wand of Magic Detection",
                "current": 3, "max": 3, "reset": "long",
                "charge_recovery": "1d3",
                "source": "item-wand-of-magic-detection",
                "desc": "3 charges. Spend 1 to cast Detect Magic (30-ft radius, 10-min concentration). Regains 1d3 charges on long rest.",
                "manual": False,
            },
            # v2.403.2 — magic-items-automation Phase 9.2 batch 3:
            # Helm of Teleportation (RAW DMG p.169) — 3 charges, regain
            # 1d3 at dawn. The helm is seeded INERT on Thalindra (vault
            # loot, equipped=False/attuned=False at line ~7100); the
            # harness PATCHes equipped+attuned before invoking. Resource
            # row is seeded up front so the dispatch can find it.
            {
                "key": "helm-of-teleportation",
                "name": "Helm of Teleportation",
                "current": 3, "max": 3, "reset": "long",
                "charge_recovery": "1d3",
                "source": "item-helm-of-teleportation",
                "desc": "3 charges; expend 1 (action) to cast Teleport (GM-narrated destination). Regain 1d3 at dawn. RAW DMG p.169.",
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
            # v2.319.0 — Magic-items: Mace of Disruption (RAW DMG p.179, rare,
            # attunement). Sun Blade-shape conditional rider with TWO creature
            # types in the predicate (fiend OR undead). The +2d6 radiant rider
            # fires from the auto-uplifts block when the wielder is attacking
            # one of those creature types and the inventory item is equipped +
            # attuned. The HP-25-destroy and fear-save RAW clauses are
            # GM-narrated in v1. The inventory item is seeded INERT (spare
            # loot) so the harness PATCHes it equipped+attuned per test (the
            # v2.318.1 Sword of Life Stealing pattern); when the PATCH is in
            # effect, Tavik's seed Warhammer attack still uses bludgeoning
            # damage — this row exists so the test can target attack_index 2
            # and hit the mace's `_slug` gate.
            {"name": "Mace of Disruption", "attack_bonus": "+5",
             "damage": "1d6+2", "damage_type": "bludgeoning",
             "range": "5 ft", "_slug": "mace-of-disruption",
             "desc": "Rare mace, attunement. 1d6+2 bludgeoning; +2d6 radiant on hit vs. fiends and undead (RAW DMG p.179). Sheds bright light in a 20-ft radius. The HP-25-destroy / fear save clauses are GM-narrated in v1."},
            # v2.339.0 — Dwarven Thrower (RAW DMG p.166, very rare,
            # attunement by a dwarf — Tavik is a Hill Dwarf, RAW-legal). A
            # thrown warhammer: +3 attack/damage baked into this row (Tavik's
            # STR +2 + prof +3 + magic +3 = +8 / 1d8+5). On a ranged hit it
            # deals +1d8 bludgeoning (the unconditional `dice` rider), or +2d8
            # vs a giant (base 1d8 + the `bonus_dice_vs` 1d8). The
            # returns-to-hand property is GM-narrated. The inventory item
            # below is seeded inert (PATCH-in-test) per the v2.318.1 pattern.
            {"name": "Dwarven Thrower (thrown)", "attack_bonus": "+8",
             "damage": "1d8+5", "damage_type": "bludgeoning",
             "range": "20/60 ft", "_slug": "dwarven-thrower",
             "desc": "Very rare warhammer, attunement (dwarf). +3 attack/damage; returns to hand after a ranged attack. On a ranged hit, +1d8 bludgeoning (or +2d8 vs. a giant). RAW DMG p.166."},
            # v2.341.0 — Mace of Smiting (RAW DMG p.179, rare, NO attunement).
            # +1 attack/damage baked into this row (Tavik's STR +2 + prof +3 +
            # magic +1 = +6 / 1d6+3); the +3-vs-construct upgrade is
            # GM-narrated. On a natural 20 the on_nat_20 handler rolls +2d6
            # bludgeoning, or +4d6 vs a construct (base 2d6 + the
            # bonus_dice_vs 2d6). The destroy-construct-at-≤25-HP clause is
            # GM-narrated. No attunement → the rider fires on slug match alone.
            # A construct-smashing mace fits a frontline Life Cleric (golems,
            # animated armor, and the like are classic dungeon foes).
            {"name": "Mace of Smiting", "attack_bonus": "+6",
             "damage": "1d6+3", "damage_type": "bludgeoning",
             "range": "5 ft", "_slug": "mace-of-smiting",
             "desc": "Rare mace, no attunement. +1 attack/damage (+3 vs. constructs). On a natural 20, deal +2d6 bludgeoning (or +4d6 vs. a construct); a construct reduced to ≤25 HP is destroyed (GM-narrated). RAW DMG p.179."},
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
            # v2.404.3 — Enhance Ability (Cleric / Druid / Bard / Sorcerer
            # L2). RAW PHB p.237: touch a creature, choose a Bear / Bull /
            # Cat / Eagle / Fox / Owl variant; concentration up to 1 hour.
            # Upcast: +1 target per slot above 2nd. Demo fixture for the
            # v2.404.3 `_SPELL_BUFF_MAP["enhance-ability"]` cap + extras
            # (1 + (slot - 2) * 1). Tavik has L2 + L3 slots so the test
            # exercises both base cap and the +1 upcast extension. Appended
            # at END so existing spell_index assertions stay valid.
            {"name": "Enhance Ability", "level": 2, "prepared": True, "_slug": "enhance-ability", "casting_time": "1 action"},
            # v2.404.7 — Command (Cleric / Warlock L1). RAW PHB p.223: WIS
            # save vs a one-word command (Approach / Drop / Flee / Grovel /
            # Halt / GM-judged other). 1 round duration, no concentration.
            # Upcast: +1 target per slot above 1st. Demo fixture for the
            # v2.404.7 first condition-install ship of the arc — the new
            # `_SPELL_CONDITION_MAP["command"]` entry installs a
            # `commanded` buff on a failed save (NPC v1 only), and the
            # `_SPELL_TARGET_CAPS["command"]` cap enforces the multi-
            # target limit before slot consumption. Appended at END so
            # existing spell_index assertions stay valid.
            {"name": "Command", "level": 1, "prepared": True, "_slug": "command", "casting_time": "1 action"},
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
            # v2.159.28 Phase 2b — weight_lb backfilled per RAW PHB
            # pp.149-151. Tavik's STR 14 → 210 lb cap.
            {"name": "Warhammer", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d8", "damage_type": "bludgeoning",
             "versatile": True, "properties": "versatile (1d10)",
             "_slug": "warhammer", "weight_lb": 2},
            {"name": "Shield", "type": "shield", "qty": 1,
             "equippable": True, "equipped": True,
             "ac_value": 2, "_slug": "shield", "weight_lb": 6},
            {"name": "Chain mail", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "heavy", "ac_value": 16,
             "_slug": "chain-mail", "weight_lb": 55},
            {"name": "Holy symbol", "type": "gear", "qty": 1, "weight_lb": 1,
             "desc": "Amulet, emblem, or reliquary used as a divine focus — replaces the material component requirement for cleric spells."},
            {"name": "Priest's pack", "type": "gear", "qty": 1, "weight_lb": 24,
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
            # v2.216.0 — ability-score override Phase 3: Amulet of Health
            # (RAW DMG p.150, rare, attunement). While worn, your CON
            # *becomes* 19 if it isn't already higher — and the CON change
            # retroactively adjusts max HP. Tavik (Cleric Lv 8, base CON 14
            # → mod +2) becomes effective CON 19 (mod +4) while worn: +2
            # CON-mod × 8 levels = +16 to his max HP (67 → 83, surfaced as
            # /sheet-json `derived.effective_max_hp`). His 3rd attuned item
            # (RAW max), after the Ring + Staff. See docs/plans/str-override.md.
            {"name": "Amulet of Health", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "amulet-of-health", "weight_lb": 0,
             "desc": "Rare wondrous item, attunement. While worn, your Constitution score becomes 19 if it isn't already higher. The CON change retroactively adjusts your max HP. RAW DMG p.150."},
            # v2.233.0 — Periapt of Health (RAW DMG p.184, uncommon, NO
            # attunement). While worn you're immune to contracting disease.
            # Needs no attunement, so it composes with Tavik's three attuned
            # items without exceeding the RAW cap — thematic on a Cleric. The
            # `disease_immune` flag rides the `periapt-of-health` catalog
            # payload and surfaces on /sheet-json as derived.disease_immune.
            {"name": "Periapt of Health", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 0,
             "_slug": "periapt-of-health",
             "desc": "Uncommon wondrous item. While wearing this pendant you are immune to contracting any disease; an existing disease's effects are suppressed while worn. RAW DMG p.184."},
            # v2.266.0 — charged-items Phase 1: Wand of Binding (RAW DMG
            # p.211, rare, attunement). 7 charges; expend 1 to cast Hold
            # Person (save DC 15). Thematic on Tavik — Hold Person is on
            # his prepared list. His 4th attuned item (seed-load bypasses
            # the RAW 3-item cap, enforced at /attune runtime only).
            # Paired with the wand-of-binding resource row below.
            {"name": "Wand of Binding", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "wand-of-binding", "weight_lb": 1,
             "desc": "Rare wand, attunement. 7 charges. Expend 1 charge to cast Hold Person (save DC 15). RAW also casts Hold Monster for 5 charges. Regains 1d6+1 charges at dawn (long rest). RAW DMG p.211."},
            # v2.295.0 — Robe of Eyes (RAW DMG p.193, rare, attunement). The
            # first item to compose THREE existing substrate fields in one
            # payload: advantage on Wisdom (Perception) checks that rely on
            # sight (the v2.253.0 check_advantage_on substrate, keyed on
            # perception), all-around vision + see-in-darkness (the v2.159.24
            # sees_in_darkness substrate, consumed by the darkness-blinded
            # attack path), and darkvision 120 ft (the descriptive darkvision_ft
            # field — Belt of Dwarvenkind shape). The see-invisible / Ethereal-
            # sight (120 ft) and the light/daylight-blind CON-save clause are
            # GM-narrated in v1. Seeded as inert spare loot (unequipped/
            # unattuned) so it adds no flag to Tavik's baseline (he carries no
            # perception-advantage or darkvision item) — the harness PATCHes it
            # equipped+attuned, rolls a Perception check, then restores. An
            # all-seeing robe is on-theme for a watchful Life Cleric.
            {"name": "Robe of Eyes", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False, "weight_lb": 0,
             "_slug": "robe-of-eyes",
             "desc": "Rare wondrous item, attunement. While wearing the robe you see in all directions and have advantage on Wisdom (Perception) checks that rely on sight; darkvision 120 ft; see invisible creatures/objects and into the Ethereal Plane out to 120 ft. A light/daylight spell on or near the robe blinds you (CON save to end). RAW DMG p.193."},
            # v2.313.0 — Tome of Understanding (RAW DMG p.208, very rare, no
            # attunement). Reconciliation-plan Phase 2: the third leg of the
            # Tome trio on the `permanent_boost` path. Studying it for 48 hours
            # over 6 days permanently raises WIS by 2 (and its maximum). Read
            # via /use_item_action's `read` action → _use_item_action_permanent_boost
            # edits sheet.abilities.WIS and consumes the book. Seeded on Tavik
            # (Cleric, WIS 16 — his spellcasting stat); he carries no WIS
            # override (the Robe of Eyes only grants Perception-check advantage,
            # not a score set), so the read cleanly takes WIS 16 → 18. Appended
            # at END so existing inventory-index assertions stay valid.
            {"name": "Tome of Understanding", "type": "magic",
             "qty": 1, "consumable": True, "weight_lb": 5,
             "_slug": "tome-of-understanding",
             "desc": "Very rare wondrous item. Studying it for 48 hours over 6 days permanently increases your Wisdom score by 2 (and its maximum). The tome then loses its magic for a century. RAW DMG p.208."},
            # v2.319.0 — Mace of Disruption (RAW DMG p.179, rare, attunement).
            # Paired with the attack entry above via `_slug`. Sun Blade-shape
            # conditional rider but with TWO creature types in the predicate
            # (fiend OR undead) — the first multi-type conditional rider in the
            # catalog. Seeded INERT (equipped=False, attuned=False) per the
            # v2.318.1 spare-loot precedent — the harness PATCHes it
            # equipped+attuned via /sheet-fields (bypassing the /attune 3-item
            # cap, since Tavik is already at 4 seed-attuned items), runs the
            # rider tests, then restores. Thematic on Tavik (Life Cleric — a
            # divine mace that disrupts undead and fiends is RAW-canonical for
            # a sun-worshipping cleric). When the PATCH is in effect, attacks
            # via attack_index 2 surface the +2d6 radiant uplift on fiend /
            # undead targets and stay silent on humanoid targets. The
            # HP-25-destroy + fear-save RAW clauses are GM-narrated in v1.
            {"name": "Mace of Disruption", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "hands": 1, "damage": "1d6", "damage_type": "bludgeoning",
             "properties": "magic",
             "_slug": "mace-of-disruption", "weight_lb": 4,
             "desc": "Rare mace, attunement. When you hit a fiend or an undead with this magic weapon, that creature takes an extra 2d6 radiant damage. If the target has 25 HP or fewer after taking this damage, it must succeed on a DC 15 WIS save or be destroyed; on a successful save, the creature becomes frightened of you until the end of your next turn (GM-narrated in v1). While held, sheds bright light in a 20-ft radius and dim light 20 ft beyond. RAW DMG p.179."},
            # v2.328.0 — "The Inventor's Trio" bundle: Decanter of Endless
            # Water (RAW DMG p.161, uncommon, no attunement). 2-lb stoppered
            # flask. Action: speak one of three command words to produce
            # water — "stream" (1 gallon per round), "fountain" (5-ft-long
            # stream, 5 gallons per round), "geyser" (20-ft long × 1-ft
            # wide, 30 gallons per round; counts as a melee attack — DEX
            # save DC 13 vs 30 gallons, knocked prone). Mode-switching +
            # geyser-attack are GM-narrated in v1; catalog row is a stub
            # passive. Thematic on Tavik (Cleric — sacred-water vessel
            # symbolism for a Life Domain healer).
            {"name": "Decanter of Endless Water", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 2,
             "_slug": "decanter-of-endless-water",
             "desc": "Uncommon wondrous item, no attunement. 2-lb stoppered flask. Action: speak one of three command words to produce water — `stream` (1 gallon/round, 10 ft), `fountain` (5-ft length, 5 gallons/round), or `geyser` (30-ft × 1-ft, 30 gallons/round, knockdown attack). RAW DMG p.161."},
            # v2.334.0 — "The Diviner's Hoard" bundle: Candle of Invocation
            # (RAW DMG p.157, very rare, attunement). A taper keyed to a
            # specific alignment; while burning near a creature of the
            # matching alignment it grants a +2 luck-style aid (RAW: the
            # candle's spells / planar-ally summon are alignment-gated).
            # Lighting it lets the attuned wielder cast Gate (1/use) to a
            # plane matching the candle's alignment. Stub catalog row; the
            # alignment gating + Gate cast are GM-narrated. Thematic on
            # Tavik (Life Cleric — a consecrated invocation candle fits his
            # divine-ritual aesthetic; pairs with his Decanter of Endless
            # Water for a "sacred vessel + sacred flame" altar kit).
            {"name": "Candle of Invocation", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 1,
             "_slug": "candle-of-invocation",
             "desc": "Very rare wondrous item, attunement. A taper keyed to a specific alignment. While burning, creatures of the matching alignment near it gain a benefit and the wielder can use the flame to cast Gate (consuming the candle). Spells / planar-ally effects are alignment-gated. RAW DMG p.157."},
            # v2.339.0 — Dwarven Thrower (RAW DMG p.166, very rare,
            # attunement by a dwarf). Paired with the attack entry above via
            # `_slug`. Seeded INERT (equipped=False, attuned=False) per the
            # v2.318.1 spare-loot precedent — the harness PATCHes it
            # equipped+attuned via /sheet-fields (bypassing the /attune cap;
            # Tavik is already at 4+ seed-attuned), then attacks a giant /
            # humanoid to assert the base +1d8 rider and the giant +1d8 bonus.
            # Tavik is a Hill Dwarf, so the dwarf-only attunement is RAW-legal.
            {"name": "Dwarven Thrower", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "hands": 1, "damage": "1d8", "damage_type": "bludgeoning",
             "range": "20/60 ft", "properties": "thrown, magic",
             "_slug": "dwarven-thrower", "weight_lb": 5,
             "desc": "Very rare warhammer, attunement by a dwarf. +3 attack/damage. It returns to your hand immediately after a ranged attack. On a ranged hit it deals an extra 1d8 bludgeoning damage, or an extra 2d8 if the target is a giant. RAW DMG p.166."},
            # v2.341.0 — Mace of Smiting (RAW DMG p.179, rare, NO attunement).
            # Paired with the attack entry above via `_slug`. No attunement →
            # the on_nat_20 +2d6 (/+4d6 vs construct) rider fires on slug
            # match alone, so it's seeded equipped (no PATCH-in-test needed).
            # A second mace on Tavik (the mace-wielding Life Cleric) alongside
            # his Mace of Disruption — showcasing the on_nat_20 bonus_dice_vs
            # construct path next to the every-hit conditional rider.
            {"name": "Mace of Smiting", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True,
             "hands": 1, "damage": "1d6", "damage_type": "bludgeoning",
             "properties": "magic", "weight_lb": 4,
             "_slug": "mace-of-smiting",
             "desc": "Rare mace, no attunement. +1 attack/damage (+3 vs. constructs). On a natural 20, the target takes an extra 2d6 bludgeoning, or 4d6 if it's a construct; a construct reduced to 25 HP or fewer after this damage is destroyed. RAW DMG p.179."},
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
            # v2.403.5 — magic-items-automation Phase 9.2 batch 6:
            # Restorative Ointment (RAW DMG p.181) — 1d4+1 doses (avg 3).
            # The jar is seeded INERT on Tavik (vault loot at line ~7205);
            # the harness PATCHes equipped=True. `reset: "none"` — the
            # jar doesn't refill (consumable).
            {
                "key": "restorative-ointment",
                "name": "Restorative Ointment",
                "current": 3, "max": 3, "reset": "none",
                "source": "item-restorative-ointment",
                "desc": "3 doses. Action: apply one dose to a creature — regain 2d8+2 HP and cure poison + disease. The jar doesn't refill. RAW DMG p.181.",
                "manual": False,
            },
            # v2.266.0 — charged-items Phase 1: Wand of Binding charge
            # counter. Same 7-charge / 1d6+1 recharge shape as the Web
            # wand; the spell + base slot live in the catalog (Hold
            # Person + base 2, fixed single-charge spend). Paired with
            # the Wand of Binding entry in Tavik's inventory above.
            {
                "key": "wand-of-binding",
                "name": "Wand of Binding",
                "current": 7, "max": 7, "reset": "long",
                "charge_recovery": "1d6+1",
                "source": "item-wand-of-binding",
                "desc": "7 charges. Spend 1 to cast Hold Person (DC 15) at slot level 2. Regains 1d6+1 charges on long rest.",
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
            # v2.322.0 — Magic-items: Holy Avenger Longsword (RAW DMG p.174,
            # legendary, attunement, "any sword"). The +3 attack/damage is
            # baked onto this attack row (Vorpal/Dragon Slayer precedent for
            # magic +X swords) — Caelan's base +6/1d8+3 → +9/1d8+6 here. The
            # +2d10 radiant rider vs fiend OR undead fires from the v2.319.0
            # multi-type conditional substrate when the inventory item is
            # equipped + attuned (a clone of Mace of Disruption with 2d10
            # instead of 2d6). The save-advantage aura is GM-narrated in v1.
            # The inventory item is seeded INERT (spare loot) — the harness
            # PATCHes equipped+attuned per test, runs the rider assertion,
            # then restores.
            {"name": "Holy Avenger Longsword", "attack_bonus": "+9",
             "damage": "1d8+6", "damage_type": "slashing",
             "range": "5 ft", "_slug": "holy-avenger",
             "desc": "Legendary longsword, attunement. +3 attack/damage; +2d10 radiant on hit vs. fiends and undead (RAW DMG p.174). 10-ft aura grants advantage on saves vs spells/magical effects to you and friendly creatures (GM-narrated)."},
            # v2.360.0 — Magic-items: Sword of Wounding Longsword (RAW DMG
            # p.207, rare, attunement, any sword). RAW gives NO magical
            # attack/damage bonus, so the row mirrors Caelan's base
            # longsword (+6 / 1d8+3). The wound-stack install + per-turn
            # 1d4 necrotic tick + DC 15 CON save fire from the
            # `_apply_magic_item_on_hit_install_effect` post-hit hook
            # when the inventory item is equipped + attuned (the
            # `_slug` field is the rider gate). The inventory item is
            # seeded INERT (spare loot, attunement-cap-friendly) — the
            # harness PATCHes equipped+attuned per test, runs the rider
            # assertion, then restores. The "once per turn" cap, the
            # ally-can-end-via-Medicine-DC-15 alternative, and the
            # "HP lost this way only returns on a rest" clause are
            # GM-narrated in v1.
            {"name": "Sword of Wounding Longsword", "attack_bonus": "+6",
             "damage": "1d8+3", "damage_type": "slashing",
             "range": "5 ft", "_slug": "sword-of-wounding",
             "desc": "Rare longsword, attunement. On each hit, append a Wound stack to the target; at the start of each of its turns it takes 1d4 necrotic per stack, then makes a DC 15 CON save — pass ends all wounds (RAW DMG p.207)."},
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
            # v2.159.28 Phase 2b — weight_lb backfilled per RAW PHB
            # pp.149-151. Caelan's STR 16 → 240 lb cap.
            {"name": "Longsword", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d8", "damage_type": "slashing",
             "properties": "versatile (1d10)", "_slug": "longsword",
             "weight_lb": 3},
            {"name": "Javelin", "type": "weapon", "qty": 4,
             "equippable": True, "equipped": False, "hands": 1,
             "damage": "1d6", "damage_type": "piercing",
             "range": "30/120 ft", "properties": "thrown", "_slug": "javelin",
             "weight_lb": 2},
            {"name": "Shield", "type": "shield", "qty": 1,
             "equippable": True, "equipped": True,
             "ac_value": 2, "_slug": "shield", "weight_lb": 6},
            {"name": "Chain mail", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "heavy", "ac_value": 16,
             "_slug": "chain-mail", "weight_lb": 55},
            {"name": "Holy symbol (amulet)", "type": "gear", "qty": 1,
             "weight_lb": 1,
             "desc": "Silver disc bearing the sun-and-anvil of the order. Divine focus — replaces material components for paladin spells."},
            {"name": "Explorer's pack", "type": "gear", "qty": 1,
             "weight_lb": 59,
             "desc": "Backpack, bedroll, mess kit, tinderbox, 10 torches, 10 days rations, waterskin, 50 ft hempen rope."},
            {"name": "Potion of Healing", "type": "consumable", "qty": 2,
             "consumable": True, "use_kind": "heal", "heal_dice": "2d4+2",
             "_slug": "potion-of-healing",
             "desc": "Drink to regain 2d4+2 HP. RAW: action. Campaign setting can flip to bonus action."},
            # v2.158.93 — Magic-items Phase 5c demo fixture. Dragon
            # Slayer Longsword. First conditional-rider item: the +3d6
            # only fires when the target carries ``creature_type:
            # "dragon"`` (any of the chromatic / metallic / gem
            # ancestries). Paired with the attack entry above via
            # ``_slug``.
            # v2.243.0 — RAW correction: Dragon Slayer (DMG p.166)
            # requires NO attunement. Dropped the `attuned` flag so the
            # weapon stays equipped + functional while freeing Caelan's
            # 3rd attunement slot (the Ring of Feather Falling fills it
            # in v2.244.0). Caelan's attuned count drops 3 → 2.
            {"name": "Dragon Slayer Longsword", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True,
             "hands": 1, "damage": "1d8", "damage_type": "slashing",
             "properties": "versatile (1d10), magic",
             "_slug": "dragon-slayer",
             "desc": "Rare longsword, no attunement. +1 attack/damage; deals +3d6 slashing damage to dragons (RAW DMG p.166)."},
            # v2.225.0 — Ioun Stone of Dexterity (RAW DMG p.176, very rare,
            # attunement). Capped-additive +2 DEX to a max of 20 (the
            # v2.224.0 `ability_bonus` substrate). Seeded on Caelan (Paladin,
            # DEX 10 → effective 12, mod 0 → +1). He wears chain mail (heavy
            # armor), so the DEX bump does NOT change his AC; it lands purely
            # on DEX saves/checks. v2.248.0 detuned it (kept equipped) to free
            # his 3rd attunement slot for the Armor of Resistance — the DEX
            # bump was the lowest-value drop (heavy-armor AC unaffected, and
            # DEX stays covered by other ability-bonus iouns).
            {"name": "Ioun Stone of Dexterity", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": False,
             "_slug": "ioun-stone", "_ability_bonus": {"DEX": 2},
             "desc": "Very rare wondrous item, attunement. This deep red sphere orbits your head and increases your Dexterity by 2, to a maximum of 20. RAW DMG p.176."},
            # v2.229.0 — stored-spell capacity drop-in. Ioun Stone of
            # Reserve (RAW DMG p.176, rare, attunement): a pearly-white
            # spindle that holds up to 3 levels of spells cast into it.
            # The capacity rides the shared `ioun-stone` slug via
            # `_spell_reserve_levels` (no ability payload), surfacing on
            # `/sheet-json` derived.spell_reserve. One of Caelan's three
            # attuned items (Ioun Stone of Dexterity + this + the v2.244.0
            # Ring of Feather Falling — the Dragon Slayer dropped its
            # attunement in v2.243.0) — and his SECOND ioun stone, showing
            # two stones composing on the one slug with different per-item
            # riders. The cast-into / cast-from mechanic is descriptive-only
            # in v1.
            {"name": "Ioun Stone of Reserve", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "ioun-stone", "_spell_reserve_levels": 3,
             "desc": "Rare wondrous item, attunement. This pearly white spindle orbits your head and can store up to 3 levels of spells cast into it, holding them until you cast them. RAW DMG p.176."},
            # v2.244.0 — Ring of Feather Falling (RAW DMG p.191, rare,
            # attunement). One of Caelan's 3 attuned items (Ioun Stone of
            # Reserve + this ring + the v2.248.0 Armor of Resistance; the DEX
            # ioun was detuned in v2.248.0). Surfaces on /sheet-json as
            # derived.feather_fall, gated on the `attuned` flag (unlike the
            # no-attunement Ring of Water Walking / Swimming in this batch).
            {"name": "Ring of Feather Falling", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "weight_lb": 0, "_slug": "ring-of-feather-falling",
             "desc": "Rare ring, attunement. When you fall while wearing this ring, you descend 60 feet per round and take no damage from falling. RAW DMG p.191."},
            # v2.248.0 — Armor of Resistance (Acid) (RAW DMG p.152, rare,
            # attunement). Caelan's 3rd attuned item, taking the slot the
            # detuned Ioun Stone of Dexterity freed. The acid resistance
            # rides the per-item `_resistance_type: "acid"` rider on the
            # shared `armor-of-resistance` slug — the same shared-slug pattern
            # as the Ring of Resistance (Seraphine, fire). The walker folds it
            # into the `resistance_to` list that `_resistance_halve` consults
            # in the live damage pipeline, so acid damage to Caelan is halved
            # while worn. A resilient suit fits a frontline Devotion paladin.
            {"name": "Armor of Resistance (Acid)", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "weight_lb": 55,
             "_slug": "armor-of-resistance", "_resistance_type": "acid",
             "desc": "Rare armor (chain mail), attunement. You have resistance to acid damage while you wear this armor. RAW DMG p.152."},
            # v2.291.0 — Spellguard Shield (RAW DMG p.201, very rare,
            # attunement). RAW: "while holding this shield, you have advantage
            # on saving throws against spells and other magical effects, and
            # spell attacks have disadvantage against you." The clean passive
            # half rides the v2.236.0 `spell_save_advantage` substrate (the
            # Mantle of Spell Resistance flag) — folds into the boolean-OR
            # field that surfaces on /sheet-json as derived.spell_save_advantage.
            # The spell-attack-disadvantage half is GM-narrated in v1. Spare
            # loot (equipped=False) so it doesn't replace Caelan's plain Shield
            # (+2 AC) or change his attuned count; the harness PATCHes it
            # equipped+attuned, reads the projection, then restores. A warded
            # shield fits a frontline Devotion paladin who steps into spells.
            {"name": "Spellguard Shield", "type": "shield", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "ac_value": 2, "weight_lb": 6, "_slug": "spellguard-shield",
             "desc": "Very rare shield, attunement. While holding this shield, you have advantage on saving throws against spells and other magical effects, and spell attacks have disadvantage against you. RAW DMG p.201."},
            # v2.303.0 — Boots of Striding and Springing (RAW DMG p.156,
            # uncommon, attunement). RAW: walking speed becomes 30 ft (if
            # not already higher), speed isn't reduced by encumbrance or
            # heavy armor, and you can jump three times the normal distance.
            # The tripled-jump half rides the v2.260.0 `jump_at_will`
            # boolean substrate (the Ring of Jumping flag) — aggregates in
            # `_equipped_item_effects` (boolean OR) and surfaces on
            # /sheet-json as derived.jump_at_will = {sources}. The
            # 30-ft-floor walking speed + ignore-encumbrance/heavy-armor
            # clause is GM-narrated in v1. Attunement-gated (the payload
            # carries requires_attunement), so worn-but-not-attuned grants
            # nothing. Seeded inert (unequipped/unattuned) as spare loot so
            # it adds no flag to Caelan's baseline (he carries no other
            # jump_at_will item — his Ring of Feather Falling is the
            # distinct feather_fall flag) — the harness PATCHes it
            # equipped+attuned, reads the derived flag, then restores.
            # Springy boots fit a heavy-armor Paladin who shrugs off the
            # speed penalty.
            {"name": "Boots of Striding and Springing", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "weight_lb": 1, "_slug": "boots-of-striding-and-springing",
             "desc": "Uncommon wondrous item, attunement. While you wear these boots, your walking speed becomes 30 ft (unless already higher), and your speed isn't reduced if you are encumbered or wearing heavy armor. In addition, you can jump three times the normal distance, though no farther than your remaining movement allows. RAW DMG p.156."},
            # v2.306.0 — Armor of Vulnerability (RAW DMG p.152, rare,
            # attunement, CURSED). The demo's plate variant resists slashing
            # but — as the curse — is vulnerable to bludgeoning + piercing.
            # Composes two substrates: the v2.235.0 `resistance_to` fold
            # (slashing halved via `_resistance_halve`) and the NEW v2.306.0
            # `vulnerability_to` fold (bludgeoning/piercing doubled via
            # `_vulnerability_double`). Seeded inert (unequipped/unattuned) so
            # it adds nothing to Caelan's baseline (he has no phys resistance or
            # vulnerability) — the harness PATCHes it equipped+attuned, deals
            # slashing/bludgeoning/piercing damage, asserts halve/double/double,
            # then restores. The curse (can't doff without remove curse) is
            # GM-narrated. A holy-looking plate that turns out cursed is a
            # fitting trap for a trusting Devotion Paladin.
            {"name": "Armor of Vulnerability", "type": "armor", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "armor_type": "heavy", "ac_value": 18, "weight_lb": 65,
             "_slug": "armor-of-vulnerability",
             "desc": "Rare armor (plate), attunement. CURSED. While wearing this armor you have resistance to slashing damage — but the curse gives you vulnerability to bludgeoning and piercing damage. Attuning curses you until targeted by remove curse; removing the armor doesn't end the curse. RAW DMG p.152."},
            # v2.315.0 — Scimitar of Speed (RAW DMG p.197, very rare,
            # attunement). RAW: +2 to attack and damage rolls with this magic
            # weapon, AND you can make one attack with it as a bonus action on
            # each of your turns. The marquee bonus-action-attack half rides
            # the v2.315.0 `bonus_action_attack` boolean substrate — aggregates
            # in `_equipped_item_effects` (boolean OR) and surfaces on
            # /sheet-json as derived.bonus_action_attack = {sources}. The +2
            # attack/damage half is RAW-described here and baked onto the
            # wielder's attack row when equipped (Dragon Slayer / Vorpal
            # precedent); the actual extra-attack action-economy is GM-narrated
            # in v1. Attunement-gated (the payload carries requires_attunement),
            # so worn-but-not-attuned grants nothing. Seeded inert
            # (unequipped/unattuned) as spare loot so it adds no flag to
            # Caelan's baseline — the harness PATCHes it equipped+attuned,
            # reads the derived flag, then restores. A captured fey blade is
            # plausible loot for a frontline Devotion paladin.
            {"name": "Scimitar of Speed", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "hands": 1, "damage": "1d6", "damage_type": "slashing",
             "properties": "finesse, light, magic", "weight_lb": 3,
             "_slug": "scimitar-of-speed",
             "desc": "Very rare scimitar, attunement. You gain a +2 bonus to attack and damage rolls made with this magic weapon. In addition, you can make one attack with it as a bonus action on each of your turns. RAW DMG p.197."},
            # v2.322.0 — Holy Avenger Longsword (RAW DMG p.174, legendary,
            # attunement, "any sword"). Paired with the attack entry above via
            # `_slug`. Pure substrate reuse — the v2.319.0 multi-type
            # conditional rider (Mace of Disruption clone) with 2d10 radiant
            # instead of 2d6. Seeded INERT (equipped=False, attuned=False) per
            # the v2.318.1 spare-loot pattern — the harness PATCHes
            # equipped+attuned via /sheet-fields (bypasses the /attune 3-item
            # cap, since Caelan is at 3 seed-attuned already: Ioun Reserve +
            # Ring of Feather Falling + Armor of Resistance) and runs the
            # rider assertions. On theme for a Devotion Paladin — Holy Avenger
            # is the iconic Paladin-Lv-17+ capstone weapon (Caelan's only Lv 7
            # today, so the larger 30-ft aura is GM-narrated as not yet
            # active). The save-advantage aura is GM-narrated.
            {"name": "Holy Avenger Longsword", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "hands": 1, "damage": "1d8", "damage_type": "slashing",
             "properties": "versatile (1d10), magic",
             "_slug": "holy-avenger", "weight_lb": 3,
             "desc": "Legendary longsword, attunement. +3 attack/damage; +2d10 radiant on hit vs. fiends and undead (RAW DMG p.174). 10-ft aura grants advantage on saves vs spells/magical effects to you and friendly creatures within the radius (30 ft at Paladin Lv 17+ — GM-narrated in v1)."},
            # v2.332.0 — "The Elemental Conclave" bundle: Brazier of
            # Commanding Fire Elementals (RAW DMG p.156, rare, no
            # attunement). 5-lb iron brazier. Action: light a fire in the
            # brazier and speak the command word — a 5-HD fire elemental
            # appears within 30 ft. The summoner makes a CHA check vs the
            # elemental's CHA to control it for 1 hour (or until the fire
            # goes out / the elemental drops to 0 HP). Stub catalog row;
            # the summon + control check are GM-narrated. Thematic on
            # Caelan (Devotion Paladin — sacred fire / divine wrath fits
            # his Oath aesthetic).
            {"name": "Brazier of Commanding Fire Elementals", "type": "magic",
             "qty": 1, "equippable": True, "equipped": True, "weight_lb": 5,
             "_slug": "brazier-of-commanding-fire-elementals",
             "desc": "Rare wondrous item, no attunement. 5-lb iron brazier. Action: light a fire in the brazier and speak the command word — a fire elemental appears within 30 ft. Make a CHA check vs the elemental's CHA to command it (concentration, up to 1 hour). RAW DMG p.156."},
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
            # v2.367.0 — Talisman of Pure Good charge pool (RAW DMG p.207):
            # 7 charges, regain all at dawn (long rest). The talisman item
            # itself is seeded INERT on Caelan (Armory's Remainder vault
            # loot, line 6927) — the harness PATCHes equipped+attuned and
            # invokes via /use_item_action. Seeding the resource row up
            # front means the test doesn't need a second PATCH to
            # bootstrap it.
            {
                "key": "talisman-of-pure-good",
                "name": "Talisman of Pure Good",
                "current": 7, "max": 7, "reset": "long",
                "source": "magic item — Talisman of Pure Good",
                "class_slug": "item",
                "desc": "7 charges (regain all at dawn). Invoke Pure Good: action — spend 1 charge to force one creature within 60 ft to make a DC 18 CHA save → 6d6 radiant on a fail, half on a save (RAW DMG p.207). Alignment gate + alignment-keyed instant-kill GM-narrated in v1.",
                "manual": False,
            },
            # v2.403.0 — magic-items-automation Phase 9.2: charge-tracked
            # announce-only Bucket D item. Brazier of Commanding Fire
            # Elementals (RAW DMG p.156) — 1/dawn. The brazier is seeded
            # equipped on Caelan (line 2089). The summon + CHA control
            # check are GM-narrated; this resource row backs the
            # /use_item_action endpoint's charge decrement.
            {
                "key": "brazier-of-commanding-fire-elementals",
                "name": "Brazier of Commanding Fire Elementals",
                "current": 1, "max": 1, "reset": "long",
                "source": "item-brazier-of-commanding-fire-elementals",
                "desc": "1/dawn. Light the brazier + speak the command word: a fire elemental appears within 30 ft. Make a CHA check vs the elemental to command it (GM-narrated, concentration up to 1 hour).",
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
            # v2.368.0 — Aura of Courage (base Paladin, Lv 10+). Listed
            # unconditionally so the picker surfaces the feature as a
            # discoverable Lv-10+ unlock; the v2.368.0 install gate at
            # `_install_buff` enforces the Lv-10 threshold. Caelan is
            # currently Lv 7 so the gate doesn't fire mechanically until
            # he's PATCH-bumped to Lv 10 (the harness fixture flow).
            {
                "key": "aura-of-courage",
                "name": "Aura of Courage (Lv 10+)",
                "desc": "Passive (Paladin Lv 10+) — you and friendly creatures within 10 ft can't be frightened while you are conscious. Range increases to 30 ft at Lv 18. Fires server-side as a pre-install gate in `_install_buff`: when a failed save would install Frightened on an ally, AoC blocks the install and broadcasts `feature_used(source=aura-of-courage)`. Currently gated off for Caelan (Lv 7); bump to Lv 10+ to unlock.",
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
        "subclass": "Oath of Devotion",
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
            # v2.159.28 Phase 2b — weight_lb backfilled per RAW PHB
            # pp.149-151. Seraphine's STR 16 → 240 lb cap.
            {"name": "Longsword", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d8", "damage_type": "slashing",
             "properties": "versatile (1d10)", "_slug": "longsword",
             "weight_lb": 3},
            {"name": "Javelin", "type": "weapon", "qty": 4,
             "equippable": True, "equipped": False, "hands": 1,
             "damage": "1d6", "damage_type": "piercing",
             "range": "30/120 ft", "properties": "thrown", "_slug": "javelin",
             "weight_lb": 2},
            {"name": "Shield", "type": "shield", "qty": 1,
             "equippable": True, "equipped": True,
             "ac_value": 2, "_slug": "shield", "weight_lb": 6},
            {"name": "Chain mail", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "heavy", "ac_value": 16,
             "_slug": "chain-mail", "weight_lb": 55},
            {"name": "Holy symbol (amulet)", "type": "gear", "qty": 1,
             "weight_lb": 1,
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
            # v2.227.0 — Periapt of Wound Closure (RAW DMG p.184,
            # uncommon, attunement). Seraphine's 2nd attuned item (after
            # the Sun Blade). The `double_hit_die_healing` passive doubles
            # her rolled short-rest Hit-Die recovery — a frontline
            # paladin's natural fit. The RAW auto-stabilize-when-dying
            # clause is descriptive-only in v1 (a start-of-turn trigger).
            {"name": "Periapt of Wound Closure", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "hands": 0, "weight_lb": 0,
             "_slug": "periapt-of-wound-closure",
             "desc": "Uncommon wondrous item, attunement. You stabilize whenever you are dying at the start of your turn; and whenever you roll a Hit Die to regain hit points, double the number of hit points it restores. RAW DMG p.184."},
            # v2.235.0 — Ring of Resistance (Fire) (RAW DMG p.192, rare,
            # attunement). Seraphine's 3rd attuned item (RAW max 3). The
            # fire resistance rides the per-item `_resistance_type: "fire"`
            # rider on the shared `ring-of-resistance` slug; the walker
            # folds it into the `resistance_to` list that `_resistance_halve`
            # consults in the live damage pipeline — so fire damage to
            # Seraphine is halved while worn. Thematic for a Vengeance
            # paladin charging through danger after a sworn foe.
            {"name": "Ring of Resistance (Fire)", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "hands": 0, "weight_lb": 0,
             "_slug": "ring-of-resistance", "_resistance_type": "fire",
             "desc": "Rare ring, attunement. You have resistance to fire damage while wearing this ring. RAW DMG p.192."},
            # v2.297.0 — Scarab of Protection (RAW DMG p.199, legendary,
            # attunement). Lands on the v2.236.0 `spell_save_advantage`
            # substrate, now upgraded this commit from a descriptive
            # /sheet-json flag into a live /roll effect: when the caller flags
            # a saving throw as `vs_spell`, `_roll_item_spell_save_advantage`
            # folds a 2d20kh1 advantage source into the roll. The scarab's
            # second benefit (12 charges; reaction to turn a failed necromancy
            # / undead-effect save into a success, then crumbles) is GM-narrated
            # in v1. Seeded as inert spare loot (unequipped/unattuned) so it
            # adds no flag to Seraphine's baseline (she carries no other
            # spell-save item) — the harness PATCHes it equipped+attuned, rolls
            # a vs_spell save, then restores. A holy ward against hostile magic
            # befits a Vengeance paladin.
            {"name": "Scarab of Protection", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False, "weight_lb": 0,
             "_slug": "scarab-of-protection",
             "desc": "Legendary wondrous item, attunement. While on your person you have advantage on saving throws against spells. The scarab has 12 charges: when you fail a save against a necromancy spell or a harmful undead effect you can use your reaction to expend 1 charge and turn the failure into a success; it crumbles to powder when the last charge is used. RAW DMG p.199."},
            # v2.304.0 — Demon Armor (RAW DMG p.158, very rare, attunement).
            # Lands on the `ac_bonus` substrate: equipped+attuned it reads as
            # target_ac = base + 1 via `_read_target_ac`. Seeded as inert spare
            # loot (unequipped/unattuned) so it adds nothing to Seraphine's
            # baseline AC (she carries no other ac_bonus item) — the harness
            # PATCHes it equipped+attuned, reads the delta, then restores. The
            # Abyssal speech, clawed-gauntlet magic unarmed strikes (1d8 +1),
            # and the curse (can't doff without remove curse; disadvantage vs
            # demons) are GM-narrated in v1. Cursed demonic plate is thematic
            # loot for a Vengeance paladin hunting the lower planes.
            {"name": "Demon Armor", "type": "armor", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "armor_type": "heavy", "ac_value": 18, "weight_lb": 65,
             "_slug": "demon-armor",
             "desc": "Very rare armor (plate), attunement. While wearing this armor you gain a +1 bonus to AC, can understand and speak Abyssal, and your clawed gauntlets turn unarmed strikes into magic weapons dealing 1d8 slashing with a +1 bonus to attack and damage. Curse: once donned you can't doff it unless targeted by remove curse, and you have disadvantage on attack rolls against demons and on saves against their spells and abilities. RAW DMG p.158."},
            # v2.332.0 — "The Elemental Conclave" bundle: Censer of
            # Controlling Air Elementals (RAW DMG p.157, rare, no
            # attunement). 1-lb brass censer. Action: burn incense and
            # speak the command word — an air elemental appears within 30
            # ft. CHA check vs the elemental's CHA to command it for 1
            # hour. Stub catalog row; the summon + control mechanic is GM-
            # narrated. Thematic on Seraphine (Vengeance Paladin — wind /
            # wrath theme; commanding sky elementals fits a divine
            # vengeance hunter who chases evil through the heavens).
            {"name": "Censer of Controlling Air Elementals", "type": "magic",
             "qty": 1, "equippable": True, "equipped": True, "weight_lb": 1,
             "_slug": "censer-of-controlling-air-elementals",
             "desc": "Rare wondrous item, no attunement. 1-lb brass censer. Action: burn incense and speak the command word — an air elemental appears within 30 ft. CHA check vs the elemental's CHA to command it (concentration, up to 1 hour). RAW DMG p.157."},
            # v2.340.0 — Mace of Terror (RAW DMG p.180, rare, attunement). A
            # near-verbatim Wand of Fear clone on the generalized save-
            # condition handler: 3 charges (regain 1d4+1 at dawn); expend 1
            # via /use_item_action (wave-of-terror) → each chosen creature
            # within 30 ft makes a DC 15 WIS save or is frightened of you for
            # 1 minute. Seeded equipped + attuned (the /use_item_action
            # dispatcher enforces the RAW attunement gate, rejecting with
            # "requires attunement" otherwise). This makes Seraphine a 4th
            # seed-attuned item; her Sun Blade detune-restore test is
            # converted to /sheet-fields in the same commit (v2.340.0,
            # mirroring the v2.320.3 B15 fix) so the /attune cap doesn't bite.
            # The magic-weapon-overcomes-resistance clause is GM-narrated.
            # Wrath-fueled terror fits a Vengeance Paladin. Paired with the
            # mace-of-terror resource row below.
            {"name": "Mace of Terror", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "hands": 1, "damage": "1d6", "damage_type": "bludgeoning",
             "properties": "magic", "weight_lb": 4,
             "_slug": "mace-of-terror",
             "desc": "Rare mace, attunement. 3 charges (regain 1d4+1 at dawn). Action: expend 1 charge to release a wave of terror — each creature of your choice within 30 ft makes a DC 15 WIS save or is frightened of you for 1 minute (must spend turns moving away). RAW DMG p.180."},
            # v2.351.0 — Rod of Rulership (RAW DMG p.197, rare, attunement).
            # Promoted out of the v2.342.0 Vault bulk loot into an explicit
            # equipped+attuned item paired with the `rod-of-rulership`
            # 1/dawn resource above. Runs through the generalized Wand of
            # Fear handler with the charmed condition. Seeded attuned (the
            # /use_item_action path gates on `attuned` for attunement items);
            # the Sun Blade detune-restore test already uses /sheet-fields
            # (v2.340.0) so the extra seed-attuned item doesn't bite the cap.
            {"name": "Rod of Rulership", "type": "wondrous", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "rod-of-rulership",
             "desc": "Rare rod, attunement. 1/dawn — action: command obedience from each creature of your choice within 120 ft; each makes a DC 15 WIS save or is charmed (regards you as its trusted leader) for 1 minute. Ends if harmed by you/allies or commanded against its nature. RAW DMG p.197."},
        ],
        "resources": [
            # v2.340.0 — Mace of Terror charge pool (RAW DMG p.180): 3
            # charges, regain 1d4+1 at dawn (long rest). The shared save-
            # condition wand handler decrements 1 per Wave of Terror.
            {
                "key": "mace-of-terror",
                "name": "Mace of Terror",
                "current": 3, "max": 3, "reset": "long",
                "charge_recovery": "1d4+1",
                "source": "magic item — Mace of Terror",
                "class_slug": "item",
                "desc": "3 charges; expend 1 (action) to release a 30-ft wave of terror — DC 15 WIS save or frightened 1 min. Regain 1d4+1 at dawn.",
                "manual": False,
            },
            # v2.351.0 — Rod of Rulership 1/dawn use (RAW DMG p.197): a
            # single "charge" that refills on a long rest. The shared save-
            # condition wand handler decrements it per Command Obedience.
            {
                "key": "rod-of-rulership",
                "name": "Rod of Rulership",
                "current": 1, "max": 1, "reset": "long",
                "source": "magic item — Rod of Rulership",
                "class_slug": "item",
                "desc": "1/dawn — action: each creature of your choice within 120 ft makes a DC 15 WIS save or is charmed (regards you as trusted leader) for 1 min. Recharges at dawn.",
                "manual": False,
            },
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
            # v2.403.0 — magic-items-automation Phase 9.2: charge-tracked
            # announce-only Bucket D item. Censer of Controlling Air
            # Elementals (RAW DMG p.157) — 1/dawn. The censer is seeded
            # equipped on Seraphine (line 2401). The summon + CHA control
            # check are GM-narrated; this resource row backs the
            # /use_item_action endpoint's charge decrement.
            {
                "key": "censer-of-controlling-air-elementals",
                "name": "Censer of Controlling Air Elementals",
                "current": 1, "max": 1, "reset": "long",
                "source": "item-censer-of-controlling-air-elementals",
                "desc": "1/dawn. Burn incense + speak the command word: an air elemental appears within 30 ft. Make a CHA check vs the elemental to command it (GM-narrated, concentration up to 1 hour).",
                "manual": False,
            },
            # v2.403.4 — magic-items-automation Phase 9.2 batch 5:
            # Ring of Three Wishes (RAW DMG p.193) — 3 lifetime charges,
            # then nonmagical. The ring is seeded INERT on Seraphine
            # (vault loot at line ~7180); the harness PATCHes equipped+
            # attuned. `reset: "none"` — counter never refills; at 0 the
            # ring becomes nonmagical (GM-narrated).
            {
                "key": "ring-of-three-wishes",
                "name": "Ring of Three Wishes",
                "current": 3, "max": 3, "reset": "none",
                "source": "item-ring-of-three-wishes",
                "desc": "3 lifetime charges. Action: expend 1 charge to cast Wish from it. After the third wish the ring becomes nonmagical (GM-narrated). RAW DMG p.193.",
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
            # v2.404.9 — Blindness/Deafness (Bard / Cleric / Sorcerer /
            # Wizard L2). RAW PHB p.219: CON save vs Blinded OR Deafened
            # for 1 minute (caster picks; v1 defaults to Blinded). End-of
            # -turn CON save to shake off. NOT concentration. Upcast: +1
            # target per slot above 2nd. Demo fixture for the v2.404.9
            # ARC-CLOSER — new `_SPELL_CONDITION_MAP["blindnessdeafness"]`
            # entry + new `_SPELL_TARGET_CAPS["blindnessdeafness"]` cap.
            # Lyra has L2 + L3 slots so the test exercises both base cap
            # and the +1 upcast extension. Appended at END so existing
            # spell_index assertions stay valid.
            {"name": "Blindness/Deafness", "level": 2, "prepared": True, "_slug": "blindnessdeafness", "casting_time": "1 action"},
        ],
        "spell_slots": {
            "bard": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 3, "used": 0},
                "3": {"total": 3, "used": 0},  # Lv 6 Bard gains the third L3 slot
            },
        },
        "inventory": [
            # v2.159.28 Phase 2b — weight_lb backfilled per RAW PHB
            # pp.149-150. Lyra's STR 10 → 150 lb cap.
            {"name": "Rapier", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d8", "damage_type": "piercing",
             "properties": "finesse", "_slug": "rapier", "weight_lb": 2},
            {"name": "Hand crossbow", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "piercing",
             "range": "30/120 ft", "properties": "light, loading",
             "_slug": "hand-crossbow", "weight_lb": 3},
            {"name": "Studded leather", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "light", "ac_value": 12,
             "_slug": "studded-leather", "weight_lb": 13},
            # v2.78.0 Phase 5 — Cloak of Displacement demo item.
            # RAW (DMG p.158, rare wondrous item, attunement):
            # "While you wear this cloak, it projects an illusion that
            # makes you appear to be standing in a place near your
            # actual location, causing any creature to have disadvantage
            # on attack rolls against you. If you take damage, the
            # property ceases to function until the start of your next
            # turn. This property is suppressed while you are
            # incapacitated, restrained, or otherwise unable to move."
            # v2.252.0 — Phase 4a: the cloak is now a true attuned passive
            # (`attuned: True`). `_equipped_item_effects` sets
            # `incoming_attacks_have_disadvantage` (attunement-gated), and the
            # /attack + /npc_attack pipelines read it via
            # `_target_wearer_imposes_attack_disadvantage` so attacks against
            # Lyra auto-roll at disadvantage (no GM click needed). The
            # informational reaction below is kept as a fallback for the
            # suppressed-after-damage clause (Phase 4b). Lyra is already at the
            # RAW 3/3 attuned cap (Demon Slayer + Staff of Charming + Ring of
            # Mind Shielding); this is a 4th attuned item — fine at seed-load
            # since the 3/3 cap is enforced only at the /attune runtime endpoint
            # (Garrik / Frost Brand precedent, v2.251.0), not in the walker.
            {"name": "Cloak of Displacement", "type": "wondrous", "qty": 1,
             "equippable": True, "equipped": True, "attunement": True,
             "attuned": True,
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
            # v2.647.0 — Ring of Spell Turning demo fixture for the
            # reaction-item CHARGE-tracking path. RAW DMG p.193 (legendary,
            # attunement): "While wearing this ring, you have advantage on
            # saving throws against any spell that targets only you ... if
            # you roll a 20 ... the spell has no effect on you and ...
            # turns back on its caster," with the deflection limited by the
            # ring's charges. SimpleVTT models the reaction's CHARGE SPEND
            # mechanically (3 charges, 1 per use, decremented in the
            # `/use_reaction` item-* dispatch + the GM-panel manual spend);
            # the reflect outcome itself stays GM-narrated. A 4th attuned
            # item — fine at seed-load (the 3/3 cap lives only on /attune;
            # Cloak-of-Displacement precedent above).
            {"name": "Ring of Spell Turning", "type": "ring", "qty": 1,
             "equippable": True, "equipped": True, "attunement": True,
             "attuned": True, "charges": 3, "max_charges": 3,
             "_slug": "ring-of-spell-turning",
             "_reactions": [
                 {
                     "key": "item-ring-spell-turning-reflect",
                     "trigger": "spell_cast_near",
                     "label": "💍 Ring of Spell Turning — reflect the spell (1 charge)",
                     "desc": "Spend 1 charge to turn a spell that targets only you back on its caster (GM adjudicates the reflect). 3 charges, regained at dawn.",
                     "kind": "item",
                     "cost_charges": 1,
                     "cost": "Reaction + 1 ring charge",
                 },
             ],
             "desc": "Ring, legendary (requires attunement). Advantage on saves vs. single-target spells; spend charges to reflect a spell back on its caster. 3 charges, regained at dawn."},
            {"name": "Lute", "type": "gear", "qty": 1, "weight_lb": 2,
             "desc": "Lyra's instrument — a polished six-string serving as her bardic focus. Lets her cast spells with material components without a separate component pouch."},
            {"name": "Entertainer's pack", "type": "gear", "qty": 1,
             "weight_lb": 38,
             "desc": "Backpack, bedroll, 2 costumes, 5 candles, 5 days rations, waterskin, disguise kit."},
            {"name": "Potion of Healing", "type": "consumable", "qty": 1,
             "consumable": True, "use_kind": "heal", "heal_dice": "2d4+2",
             "_slug": "potion-of-healing",
             "desc": "Drink to regain 2d4+2 HP. RAW: action. Campaign setting can flip to bonus action."},
            # v2.350.0 — Pipes of Haunting (RAW DMG p.184, uncommon, NO
            # attunement). Promoted out of the v2.344.0 Armory's Remainder
            # bulk loot into an explicit equipped item paired with the
            # `pipes-of-haunting` charge resource above. The radius-frighten
            # action runs through the generalized Wand of Fear handler. RAW
            # wind-instrument proficiency is GM-narrated (Lyra, a Bard, is
            # proficient anyway). On-theme for a performer.
            {"name": "Pipes of Haunting", "type": "wondrous", "qty": 1,
             "equippable": True, "equipped": True,
             "_slug": "pipes-of-haunting",
             "desc": "Uncommon wondrous item, no attunement (wind-instrument proficiency, GM-narrated). 3 charges (regain 1d3 at dawn). Action: expend 1 to play an eerie tune — each creature within 30 ft makes a DC 15 WIS save or is frightened of you for 1 minute. RAW DMG p.184."},
            # v2.354.0 — Robe of Scintillating Colors (RAW DMG p.194, very
            # rare, attunement). Promoted out of the v2.342.0 Vault bulk loot
            # into an explicit equipped+attuned item paired with the
            # `robe-of-scintillating-colors` 3-charge resource above. Runs
            # through the generalized Wand of Fear handler with the stunned
            # condition. Seeded attuned (the /use_item_action path gates on
            # `attuned`); seed-load bypasses the RAW 3-item cap (enforced at
            # /attune runtime only, per the Cloak of Arachnida precedent).
            {"name": "Robe of Scintillating Colors", "type": "wondrous", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "robe-of-scintillating-colors",
             "desc": "Very rare robe, attunement. 3 charges (regain 1d3 at dawn). Action: expend 1 to display dazzling colors until the end of your next turn — you shed bright light + attackers have disadvantage (GM-narrated), and each creature within 30 ft that can see you makes a DC 15 WIS save or is stunned until the effect ends. RAW DMG p.194."},
            # v2.279.0 — Cloak of Arachnida (RAW DMG p.158, very rare,
            # attunement). Spare loot: equipped=False / attuned=False because
            # Lyra is already at the RAW 3-item attunement cap (Cloak of
            # Displacement + Demon Slayer + Staff of Charming) and already
            # wears a cloak. Seeded inert so it disrupts no existing assertion;
            # the harness test PATCHes it equipped+attuned, reads the poison
            # `derived.resistances` + `derived.spider_climb`, then restores the
            # seed state (the v2.278.0 spare-loot + PATCH-in-test pattern).
            {"name": "Cloak of Arachnida", "type": "wondrous", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "_slug": "cloak-of-arachnida", "weight_lb": 0,
             "desc": "Very rare wondrous item, attunement. Resistance to poison damage; a climbing speed equal to your walking speed (move across vertical surfaces and ceilings hands-free); can't be caught in webs. Can cast web (DC 13, double area) once per dawn. RAW DMG p.158."},
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
            # v2.207.0 — Staff of Charming (RAW DMG p.201, rare,
            # attunement). 10 charges (regain 1d8+2 at dawn); the
            # marquee charge-action casts charm person at one creature
            # within 30 ft using Lyra's spell save DC (14). Lyra now
            # wears 3 attuned items (Cloak + Demon Slayer + Staff) — at
            # the RAW 3-item cap. The command / comprehend-languages
            # charge-spells + the enchantment-reflection reaction are
            # GM-narrated.
            {"name": "Staff of Charming", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "staff-of-charming", "weight_lb": 4,
             "desc": "Rare staff, attunement. 10 charges (regain 1d8+2 at dawn). Expend 1 to cast charm person, command, or comprehend languages using your spell save DC. Also a magic quarterstaff. Can turn a failed save vs an enchantment spell that targets only you into a success (once per dawn), and reflect a passed save back with a reaction + 1 charge."},
            # v2.222.0 — Manuals & Tomes demo fixture: a permanent
            # ability-boost book. RAW DMG p.208 Tome of Leadership and
            # Influence (very rare, no attunement): reading it permanently
            # raises CHA by 2. Routed through /use-item-action's new
            # `permanent_boost` archetype, which edits sheet.abilities.CHA
            # and consumes the book. Seeded on Lyra (Bard, CHA 17) — her
            # key stat — so reading it takes effective CHA 17 → 19.
            {"name": "Tome of Leadership and Influence", "type": "magic",
             "qty": 1, "consumable": True, "weight_lb": 5,
             "_slug": "tome-of-leadership-and-influence",
             "desc": "Very rare wondrous item. Studying it for 48 hours over 6 days permanently increases your Charisma score by 2 (and its maximum). The tome then loses its magic for a century. RAW DMG p.208."},
            # v2.225.0 — Ioun Stone of Strength (RAW DMG p.176, very rare,
            # attunement). Capped-additive ability bonus (the v2.224.0
            # `ability_bonus` substrate): +2 STR to a max of 20.
            # v2.245.0 — detuned (kept equipped) to free Lyra's 3rd attunement
            # slot for the Ring of Mind Shielding below. STR-via-ioun is the
            # most redundant ability demo (STR boosts also ride Belt of Giant
            # Strength Storm/Stone/Hill + Gauntlets of Ogre Power on 4 other
            # PCs), so its loss costs the least demo coverage. Detuned → the
            # `_ability_bonus` no longer applies (attunement-gated), so Lyra's
            # effective STR reverts to her base 8.
            {"name": "Ioun Stone of Strength", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": False,
             "_slug": "ioun-stone", "_ability_bonus": {"STR": 2},
             "desc": "Very rare wondrous item, attunement. This pale blue rhomboid orbits your head and increases your Strength by 2, to a maximum of 20. RAW DMG p.176."},
            # v2.245.0 — Ring of Mind Shielding (RAW DMG p.192, uncommon,
            # attunement). First mind-shield passive — immune to magic that
            # reads your thoughts, detects lies, or knows your alignment /
            # creature type. Surfaces on /sheet-json as derived.mind_shield,
            # gated on the `attuned` flag. Homed on Lyra (Bard) by displacing
            # the redundant Ioun Stone of Strength above (she stays at the RAW
            # 3/3 cap: Demon Slayer Rapier + Staff of Charming + this ring). A
            # mind-shielding ring fits a bard who guards her true intentions.
            {"name": "Ring of Mind Shielding", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "weight_lb": 0, "_slug": "ring-of-mind-shielding",
             "desc": "Uncommon ring, attunement. While wearing this ring, you are immune to magic that allows other creatures to read your thoughts, determine whether you are lying, know your alignment, or know your creature type. Creatures can communicate telepathically with you only if you allow it. RAW DMG p.192."},
            # v2.321.0 — Hat of Disguise (RAW DMG p.173, rare, attunement). RAW:
            # "While wearing this hat, you can use an action to cast the
            # disguise self spell from it at will. The spell ends if the hat is
            # removed." Modeled as an attunement-gated `disguise_self_at_will`
            # boolean derived flag (the v2.284.0 Boots of Levitation
            # substrate, but for an at-will *casting* trait rather than a
            # movement one). Aggregates in `_equipped_item_effects` (boolean
            # OR + sources) and surfaces on /sheet-json as
            # `derived.disguise_self_at_will = {sources}`. The action cost +
            # in-spell mechanics (concentration, 1-hour duration, illusion
            # investigation check at advantage) are GM-narrated in v1. Seeded
            # INERT (equipped=False, attuned=False) per the v2.318.1 spare-loot
            # precedent — the harness PATCHes the inventory equipped+attuned
            # via /sheet-fields (which bypasses the /attune 3-item cap, since
            # Lyra is already at 4 seed-attuned items), reads the derived
            # flag, then restores. On theme for a Bard who guards her true
            # face alongside her thoughts (Ring of Mind Shielding above).
            {"name": "Hat of Disguise", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "weight_lb": 0, "_slug": "hat-of-disguise",
             "desc": "Rare wondrous item, attunement. While wearing this hat, you can use an action to cast the disguise self spell from it at will. The spell ends if the hat is removed. RAW DMG p.173."},
            # v2.323.0 — Glamoured Studded Leather (RAW DMG p.172, rare, NO
            # attunement). Pure clone of the v2.301.0 Elven Chain ac_bonus
            # substrate ("+1 AC while worn"), with the bonus-action illusory
            # disguise property GM-narrated in v1. Seeded INERT (equipped=
            # False, attuned=False — though attunement isn't required) as
            # spare loot per the v2.318.1 pattern; the harness PATCHes
            # equipped=True via /sheet-fields and measures the target_ac
            # delta vs Lyra's baseline studded-leather AC. Thematic
            # companion to Lyra's v2.321.0 Hat of Disguise — together they
            # form a "disguise loot" bundle for the College of Lore bard.
            {"name": "Glamoured Studded Leather", "type": "armor", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "armor_type": "light", "ac_value": 12,
             "_slug": "glamoured-studded-leather", "weight_lb": 13,
             "desc": "Rare light armor (studded leather), no attunement. You gain a +1 bonus to AC while wearing this armor. Bonus action: speak the command word to make the armor appear as a normal set of clothing or some other kind of armor (illusion, GM-narrated). RAW DMG p.172."},
            # v2.326.0 — Gem of Brightness (RAW DMG p.172, uncommon, no
            # attunement). 50 charges (no recharge — when depleted, becomes a
            # non-magical 50 gp jewel). v1 wires only the "beam" mode: a
            # single-target 60-ft ray, expend 1 charge → CON save DC 15 or
            # blinded for 1 minute. Pure substrate reuse of the v2.206.0 Wand
            # of Paralysis pipe (ray + save + condition install). Modes 1 (no-
            # charge bright-light radius) and 3 (5-charge cone) are GM-narrated.
            # Thematic on Lyra (Bard, stage-light flair + concealed-strike
            # support combo with her Vicious Mockery + Demon Slayer kit). No
            # attunement, so it doesn't bump her seed-attuned roster.
            {"name": "Gem of Brightness", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 1,
             "_slug": "gem-of-brightness",
             "desc": "Uncommon wondrous item, no attunement. 50 charges. Action: expend 1 charge to fire a brilliant beam at one creature within 60 ft — CON save DC 15 or blinded for 1 minute (repeated saves at end of each turn). When depleted, the gem becomes a non-magical 50 gp jewel. Two other modes (sheds bright light; 5-charge cone) are GM-narrated. RAW DMG p.172."},
            # v2.330.0 — "The Engineer's Set" bundle: Portable Hole (RAW DMG
            # p.185, rare, no attunement). 6-ft-diameter circle of black
            # cloth (folds to handkerchief weight). Unfold on any surface
            # to open a 10-ft-deep extradimensional pit; a creature can
            # crawl in and out. Re-fold the cloth to close (objects inside
            # remain in the pocket dimension). Stub catalog row; the
            # extradimensional storage + interaction with Bag of Holding /
            # Bag of Devouring rifts are GM-narrated. Thematic on Lyra
            # (Bard, College of Lore — a hidden stash for performance
            # gear, secret manuscripts, or quick stage-trap entrances).
            {"name": "Portable Hole", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 1,
             "_slug": "portable-hole",
             "desc": "Rare wondrous item, no attunement. 6-ft-diameter circle of black cloth (folds to handkerchief weight). Action: unfold on a horizontal surface to open a 10-ft-deep extradimensional pit; re-fold the cloth to close. A creature inside can crawl up out of the unfolded hole. The hole can hold creatures or objects within its extradimensional volume. RAW DMG p.185."},
            # v2.334.0 — "The Diviner's Hoard" bundle: Crystal Ball (RAW DMG
            # p.159, very rare or legendary, attunement by a spellcaster).
            # 3-lb sphere of polished crystal. Action: cast Scrying (DC
            # 17) through the orb, scrying a creature you know or have an
            # image of. Higher-rarity variants add Detect Thoughts /
            # Telepathy / Read Thoughts modes. Stub catalog row; the spell
            # cast + per-rarity modes are GM-narrated. Thematic on Lyra
            # (College of Lore Bard — divination lore + scrying fits her
            # research aesthetic).
            {"name": "Crystal Ball", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 3,
             "_slug": "crystal-ball",
             "desc": "Very rare wondrous item, attunement by a spellcaster. 3-lb polished crystal sphere. Action: cast Scrying (DC 17) through the orb. Higher-rarity variants (legendary) add detect thoughts / telepathy / read thoughts modes. RAW DMG p.159."},
            # v2.336.0 — "The Escapist's Kit" bundle: Cape of the Mountebank
            # (RAW DMG p.157, rare, no attunement). A brimstone-scented
            # cape. Action: cast Dimension Door from it (1/dawn). On
            # disappearing you leave a cloud of smoke and appear in a
            # matching cloud at your destination (lightly obscures both
            # spaces, dissipates at end of your next turn). Stub catalog
            # row; the teleport + smoke are GM-narrated. Thematic on Lyra
            # (College of Lore Bard — a showman's vanish-and-reappear cape
            # is the perfect stage-magician escape).
            {"name": "Cape of the Mountebank", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 1,
             "_slug": "cape-of-the-mountebank",
             "desc": "Rare wondrous item, no attunement. A brimstone-scented cape. Action: cast Dimension Door from it (1/dawn). You leave a cloud of smoke and appear in a matching cloud at the destination — both spaces are lightly obscured until the end of your next turn. RAW DMG p.157."},
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
            # v2.350.0 — Pipes of Haunting charge pool (RAW DMG p.184): 3
            # charges, regain 1d3 at dawn (long rest). The shared save-
            # condition wand handler decrements 1 per Haunting Tune.
            {
                "key": "pipes-of-haunting",
                "name": "Pipes of Haunting",
                "current": 3, "max": 3, "reset": "long",
                "charge_recovery": "1d3",
                "source": "magic item — Pipes of Haunting",
                "class_slug": "item",
                "desc": "3 charges; expend 1 (action) to play an eerie tune — each creature within 30 ft makes a DC 15 WIS save or is frightened 1 min. Regain 1d3 at dawn. RAW needs wind-instrument proficiency (GM-narrated).",
                "manual": False,
            },
            # v2.354.0 — Robe of Scintillating Colors charge pool (RAW DMG
            # p.194): 3 charges, regain 1d3 at dawn (long rest). The shared
            # save-condition wand handler decrements 1 per Dazzling Display.
            {
                "key": "robe-of-scintillating-colors",
                "name": "Robe of Scintillating Colors",
                "current": 3, "max": 3, "reset": "long",
                "charge_recovery": "1d3",
                "source": "magic item — Robe of Scintillating Colors",
                "class_slug": "item",
                "desc": "3 charges; expend 1 (action) to dazzle — each creature within 30 ft that can see you makes a DC 15 WIS save or is stunned until the end of your next turn. Regain 1d3 at dawn.",
                "manual": False,
            },
            # v2.207.0 — Staff of Charming charge pool (RAW DMG p.201):
            # 10 charges, regain 1d8+2 at dawn. Decremented by the
            # generalized save-condition wand handler when Lyra casts
            # charm person from the staff.
            {
                "key": "staff-of-charming",
                "name": "Staff of Charming",
                "current": 10, "max": 10, "reset": "long",
                "charge_recovery": "1d8+2",
                "source": "magic item — Staff of Charming",
                "class_slug": "item",
                "desc": "10 charges; expend 1 to cast charm person / command / comprehend languages using your spell save DC. Regain 1d8+2 at dawn.",
                "manual": False,
            },
            # v2.403.1 — magic-items-automation Phase 9.2 batch 2:
            # Cape of the Mountebank (RAW DMG p.157) — 1/dawn dimension
            # door. The cape is seeded equipped on Lyra (line ~2899).
            # Teleport + smoke cloud are GM-narrated; this resource row
            # backs the /use_item_action endpoint's charge decrement.
            {
                "key": "cape-of-the-mountebank",
                "name": "Cape of the Mountebank",
                "current": 1, "max": 1, "reset": "long",
                "source": "item-cape-of-the-mountebank",
                "desc": "1/dawn. Action: cast Dimension Door — teleport up to 500 ft. Both spaces are lightly obscured by brimstone-scented smoke until end of your next turn (GM-narrated). RAW DMG p.157.",
                "manual": False,
            },
            # v2.326.0 — Gem of Brightness charge pool (RAW DMG p.172): 50
            # charges, NO recharge (reset: "none") — when the gem is depleted
            # it becomes a non-magical 50 gp jewel. Each beam use decrements
            # 1 charge (mode 3 cone — not yet wired in v1 — would consume 5).
            {
                "key": "gem-of-brightness",
                "name": "Gem of Brightness",
                "current": 50, "max": 50, "reset": "none",
                "source": "item-gem-of-brightness",
                "desc": "50 charges. Spend 1 to fire a brilliant beam (60 ft, CON save DC 15, blinded 1 min). When depleted, the gem becomes a non-magical 50 gp jewel.",
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
            # v2.404.4 — Longstrider (Druid / Ranger / Bard / Wizard L1).
            # RAW PHB p.255: touch a creature, +10 ft speed for 1 hour
            # (no concentration). Upcast: +1 target per slot above 1st.
            # Demo fixture for the v2.404.4 `_SPELL_BUFF_MAP["longstrider"]`
            # cap + extras (1 + (slot - 1) * 1). Mira has L1 + L2 slots so
            # the test exercises both base cap and the +1 upcast extension.
            # Appended at END so existing spell_index assertions stay valid.
            {"name": "Longstrider", "level": 1, "prepared": True, "_slug": "longstrider", "casting_time": "1 action"},
            # v2.404.8 — Animal Friendship (Bard / Druid / Ranger L1).
            # RAW PHB p.213: WIS save vs becoming friendly to caster for
            # 24 hours. Beast-only target; INT 4+ Beasts immune RAW.
            # Demo fixture for the v2.404.8 condition-install ship — new
            # `_SPELL_CONDITION_MAP["animal-friendship"]` installs a
            # `befriended-beast` buff on failed save; cap via
            # `_SPELL_TARGET_CAPS["animal-friendship"]`. Mira has L1 + L2
            # slots so the test exercises both base cap and the +1
            # upcast extension. Appended at END so existing spell_index
            # assertions stay valid.
            {"name": "Animal Friendship", "level": 1, "prepared": True, "_slug": "animal-friendship", "casting_time": "1 action"},
        ],
        "spell_slots": {
            "druid": {
                "1": {"total": 4, "used": 0},
                "2": {"total": 3, "used": 0},
                "3": {"total": 2, "used": 0},
            },
        },
        "inventory": [
            # v2.159.28 Phase 2b — weight_lb backfilled per RAW PHB
            # pp.149-150. Mira's STR 10 → 150 lb cap.
            {"name": "Scimitar", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "slashing",
             "properties": "finesse, light", "_slug": "scimitar",
             "weight_lb": 3},
            {"name": "Sling", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d4", "damage_type": "bludgeoning",
             "range": "30/120 ft", "properties": "ammunition",
             "_slug": "sling"},
            {"name": "Studded leather", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "light", "ac_value": 12,
             "_slug": "studded-leather", "weight_lb": 13},
            {"name": "Wooden shield", "type": "shield", "qty": 1,
             "equippable": True, "equipped": False,
             "ac_value": 2, "_slug": "shield", "weight_lb": 6,
             "desc": "Hand-carved oak with carved leaf motif. Mira keeps it slung in case Wild Shape isn't available."},
            {"name": "Druidic focus (sprig of mistletoe)", "type": "gear", "qty": 1,
             "weight_lb": 1,
             "desc": "Required spellcasting focus — replaces material components for druid spells."},
            {"name": "Explorer's pack", "type": "gear", "qty": 1,
             "weight_lb": 59,
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
            # v2.218.0 — ability-score override engine drop-in
            # (docs/plans/str-override.md). Headband of Intellect (RAW DMG
            # p.173, uncommon, attunement): while worn, INT *becomes* 19 if
            # not already higher. Same `ability_set` substrate as the
            # Belt/Amulet, on INT. Seeded on Mira (Druid, base INT 10 → mod
            # 0) — her 2nd attuned item (after the Vorpal Scimitar, RAW max
            # 3) — so effective INT 19 (mod +4), a clean +4 delta on INT
            # saves + Arcana/Nature/History/Investigation checks.
            {"name": "Headband of Intellect", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "headband-of-intellect",
             "desc": "Uncommon wondrous item, attunement. Your Intelligence score is 19 while worn (no effect if your INT is already 19+). RAW DMG p.173."},
            # v2.228.0 — per-item AC override drop-in. Ioun Stone of
            # Protection (RAW DMG p.176, rare, attunement): grants +1 AC
            # while orbiting your head. Rides the shared `ioun-stone` slug
            # — the AC bonus is carried by `_ac_bonus` (no ability payload),
            # winning over the catalog default in `_equipped_item_effects`.
            # Mira's 3rd attuned item (after Vorpal Scimitar + Headband,
            # RAW max 3). Base AC 15 → 16.
            {"name": "Ioun Stone of Protection", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "ioun-stone", "_ac_bonus": 1, "weight_lb": 0,
             "desc": "Rare wondrous item, attunement. This dusty rose prism orbits your head, granting +1 AC. RAW DMG p.176."},
            # Ring of Swimming (RAW DMG p.193, uncommon, NO attunement):
            # grants a swimming speed of 40 ft while worn. No attunement
            # means it rides freely alongside Mira's full 3/3 attunement
            # roster (Vorpal Scimitar + Headband + Ioun Protection) — the
            # `swim_speed` passive surfaces on /sheet-json derived.
            {"name": "Ring of Swimming", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 0,
             "_slug": "ring-of-swimming",
             "desc": "Uncommon ring, no attunement. You have a swimming speed of 40 feet while wearing this ring. RAW DMG p.193."},
            # v2.254.0 — Eyes of the Eagle (RAW DMG p.166, uncommon,
            # attunement). Rides the check_advantage_on substrate landed in
            # v2.253.0 (Cloak of Elvenkind, Phase 4b), keyed on Perception:
            # the wearer's Wisdom (Perception) /roll promotes to advantage
            # (2d20kh1). Mira is Perception-proficient (WIS 17) — a clean
            # forest-scout fixture. 4th attuned item (cap enforced only at
            # /attune, per the Lyra/Rowan seed-load precedent).
            {"name": "Eyes of the Eagle", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 0,
             "_slug": "eyes-of-the-eagle",
             "desc": "Uncommon wondrous item, attunement. While wearing these crystal lenses, you have advantage on Wisdom (Perception) checks that rely on sight. RAW DMG p.166."},
            # v2.256.0 — Cap of Water Breathing (RAW DMG p.157, uncommon, NO
            # attunement). Rides the boolean-OR `water_breath` flag (the Ring
            # of Water Walking pattern); surfaces on /sheet-json as
            # derived.water_breath. Pairs with Mira's Ring of Swimming — she
            # can both swim AND breathe underwater. No attunement, so it rides
            # alongside her loadout freely.
            {"name": "Cap of Water Breathing", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 0,
             "_slug": "cap-of-water-breathing",
             "desc": "Uncommon wondrous item, no attunement. While wearing this cap, you can breathe normally underwater. It has no effect on your ability to swim. RAW DMG p.157."},
            # v2.259.0 — Gloves of Swimming and Climbing (RAW DMG p.171,
            # uncommon, attunement). Climbing and swimming cost no extra
            # movement + a +5 Athletics bonus to climb/swim (the +5 is GM-
            # narrated in v1). The `climb_swim_ease` flag rides the
            # `gloves-of-swimming-and-climbing` catalog payload and surfaces
            # on /sheet-json as derived.climb_swim_ease. Completes Mira's
            # aquatic kit alongside her Ring of Swimming + Cap of Water
            # Breathing — she can swim freely AND breathe underwater. Her free
            # hand slot homes the gloves; seed-load bypasses the RAW 3-item
            # cap (enforced at /attune runtime only).
            {"name": "Gloves of Swimming and Climbing", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 0,
             "_slug": "gloves-of-swimming-and-climbing",
             "desc": "Uncommon wondrous item, attunement. While wearing these gloves, climbing and swimming don't cost you extra movement, and you gain a +5 bonus to Strength (Athletics) checks made to climb or swim. RAW DMG p.171. Surfaces as the derived climb_swim_ease flag."},
            # v2.268.0 — charged-items Phase 2: Staff of Swarming Insects
            # (RAW DMG p.202, rare, attunement). 10 charges; the marquee
            # action expends 5 to cast Insect Plague (4d10 piercing, CON
            # save at her spell save DC, 20-ft-radius sphere). Thematic on
            # Mira — Insect Plague is on the Druid list. Seed-load bypasses
            # the RAW 3-item cap (enforced at /attune runtime only).
            # Paired with the staff-of-swarming-insects resource row below.
            {"name": "Staff of Swarming Insects", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "staff-of-swarming-insects", "weight_lb": 4,
             "desc": "Rare staff, attunement. 10 charges. Cast Insect Plague (5 charges → 4d10 piercing, CON save, 20-ft-radius sphere) or Giant Insect (4 charges) using your spell save DC. Regains 1d6+4 charges at dawn (long rest). RAW DMG p.202."},
            # v2.352.0 — Trident of Fish Command (RAW DMG p.205, uncommon,
            # attunement). Promoted out of the v2.344.0 Armory's Remainder
            # bulk loot into an explicit equipped+attuned item paired with
            # the `trident-of-fish-command` 3-charge resource above. Runs
            # through the generalized Wand of Fear handler with the charmed
            # (dominate-beast) condition. Seeded attuned (the /use_item_action
            # path gates on `attuned`). Thematic on Mira (Wood Elf Druid with
            # an aquatic kit). The beast-only gate + control concentration
            # are GM-narrated.
            {"name": "Trident of Fish Command", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "hands": 1, "damage": "1d6", "damage_type": "piercing",
             "properties": "magic, thrown", "weight_lb": 4,
             "_slug": "trident-of-fish-command",
             "desc": "Uncommon magic trident, attunement. 3 charges (regain 1d3 at dawn). Action: expend 1 to cast dominate beast (DC 15 WIS) on a beast you can see within range. RAW: only a beast with an innate swimming speed (GM-narrated). RAW DMG p.205."},
            # v2.353.0 — Ring of Animal Influence (RAW DMG p.190, rare, NO
            # attunement). Promoted out of the v2.342.0 Vault bulk loot into
            # an explicit equipped ring paired with the
            # `ring-of-animal-influence` 3-charge resource above. Runs
            # through the generalized Wand of Fear handler with the charmed
            # (animal friendship) condition. Thematic on Mira (Druid).
            {"name": "Ring of Animal Influence", "type": "wondrous", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 0,
             "_slug": "ring-of-animal-influence",
             "desc": "Rare ring, no attunement. 3 charges (regain 1d3 at dawn). Action: expend 1 to cast animal friendship (DC 13 WIS, beast → charmed), fear on beasts (DC 13), or speak with animals. RAW DMG p.190."},
            # v2.329.0 — "The Captor's Cache" bundle: Mirror of Life Trapping
            # (RAW DMG p.181, very rare, no attunement). 4-ft-tall framed
            # mirror. When a creature other than the wielder comes within
            # 30 ft, the mirror activates: target makes a DC 15 CHA save or
            # is trapped inside one of the mirror's twelve cells (descrip-
            # tive sub-pocket-plane). Wielder can use an action to extract
            # a trapped creature; outside-the-mirror viewers can converse
            # with the trapped occupant. Stub catalog row; the CHA save +
            # cell management are GM-narrated. Thematic on Mira (Wood Elf
            # Druid — she can use the mirror to catalogue beasts or hostile
            # spirits encountered in the wild).
            {"name": "Mirror of Life Trapping", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 50,
             "_slug": "mirror-of-life-trapping",
             "desc": "Very rare wondrous item, no attunement. 4-ft-tall framed mirror with twelve sub-pocket-plane cells. When a creature other than the wielder comes within 30 ft and the mirror is active, that creature makes a DC 15 CHA save or is trapped inside one of the cells (until released by the wielder's action). The wielder can converse with trapped creatures through the mirror. RAW DMG p.181."},
            # v2.331.0 — "The Trickster's Pouch" bundle: Bag of Beans (RAW
            # DMG p.152, rare, no attunement). Heavy cloth bag with 3d4
            # dry beans. Plant a bean to roll d100 on a random table:
            # possibilities range from a 5-ft-radius pit, a fire elemental,
            # a treant, a wish-granting talking flower, or an 11d6 fire
            # explosion. Stub catalog row; the random table is GM-narrated.
            # Thematic on Mira (Wood Elf Druid — she'd be the one experimenting
            # with planting strange seeds in the forest).
            {"name": "Bag of Beans", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 0.5,
             "_slug": "bag-of-beans",
             "desc": "Rare wondrous item, no attunement. Heavy cloth bag containing 3d4 dry beans. Pour out all the beans (action) to roll on a chaotic burst table: 5-ft-radius pit, summoned monster, treant, plant grove, gp-spewing geyser, wishing flower, gas-cloud, 1-mile-tall stalk, or 11d6 fire explosion. RAW DMG p.152."},
        ],
        "feats": [],
        # v2.14.2: Wild Shape uses = 2/short rest at Lv 2 (Lv 18 unlimited).
        # Circle of the Moon raises the CR cap to 1 and lets the
        # transform fire as a bonus action — both Phase B work to
        # surface in the transform UI. Counter exists today so the
        # mini-sheet renders the chip.
        "resources": [
            # v2.403.5 — magic-items-automation Phase 9.2 batch 6:
            # Bag of Beans (RAW DMG p.152) — 3d4 beans (avg 7). The bag
            # is seeded equipped on Mira (line ~3336). `reset: "none"`
            # — beans are spent permanently (consumable).
            {
                "key": "bag-of-beans",
                "name": "Bag of Beans",
                "current": 7, "max": 7, "reset": "none",
                "source": "item-bag-of-beans",
                "desc": "7 beans. Action: plant + water one bean — roll d100 on the beanstalk table (5-ft pit, summoned creature, treant, wish-flower, fire explosion, etc.). Beans don't refill. RAW DMG p.152.",
                "manual": False,
            },
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
            # v2.268.0 — charged-items Phase 2: Staff of Swarming Insects
            # charge counter. 10 starting charges, regains 1d6+4 at dawn
            # (long rest) via the Phase 4b dice-expression recharge path.
            # The marquee Insect Plague action spends 5 from this resource.
            # Paired with the Staff of Swarming Insects entry in Mira's
            # inventory above.
            {
                "key": "staff-of-swarming-insects",
                "name": "Staff of Swarming Insects",
                "current": 10, "max": 10, "reset": "long",
                "charge_recovery": "1d6+4",
                "source": "item-staff-of-swarming-insects",
                "desc": "10 charges. Cast Insect Plague (5 charges → 4d10 piercing, CON save) or Giant Insect (4). Regains 1d6+4 charges on long rest.",
                "manual": False,
            },
            # v2.352.0 — Trident of Fish Command charge pool (RAW DMG p.205):
            # 3 charges, regain 1d3 at dawn (long rest). The shared save-
            # condition wand handler decrements 1 per Dominate Beast cast.
            {
                "key": "trident-of-fish-command",
                "name": "Trident of Fish Command",
                "current": 3, "max": 3, "reset": "long",
                "charge_recovery": "1d3",
                "source": "item-trident-of-fish-command",
                "class_slug": "item",
                "desc": "3 charges; expend 1 (action) to cast dominate beast (DC 15 WIS) on a beast. Regains 1d3 charges at dawn.",
                "manual": False,
            },
            # v2.353.0 — Ring of Animal Influence charge pool (RAW DMG p.190):
            # 3 charges, regain 1d3 at dawn (long rest). The shared save-
            # condition wand handler decrements 1 per Animal Friendship cast.
            {
                "key": "ring-of-animal-influence",
                "name": "Ring of Animal Influence",
                "current": 3, "max": 3, "reset": "long",
                "charge_recovery": "1d3",
                "source": "item-ring-of-animal-influence",
                "class_slug": "item",
                "desc": "3 charges; expend 1 (action) to cast animal friendship (DC 13 WIS → charmed), fear on beasts, or speak with animals. Regains 1d3 charges at dawn.",
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
        # v2.392.0 — Dragonborn ancestry selector. RAW PHB p.34
        # Draconic Ancestry table: bronze → lightning damage type,
        # 5×30-ft line, DEX save. Read by /use_breath_weapon to
        # pick the AoE shape + damage type + save ability without
        # parsing the breath-weapon resource's free-text desc.
        # The 10 valid values are: black, blue, brass, bronze,
        # copper, gold, green, red, silver, white.
        "_dragonborn_ancestor": "bronze",
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
            # v2.346.0 — Staff of Withering (RAW DMG p.202, rare, attunement
            # cleric/druid/warlock). A +0 magic quarterstaff (1d6+1 from STR,
            # no +N to attack/damage RAW). On a hit it adds +2d10 necrotic via
            # the `_MAGIC_ITEM_ATTACK_RIDERS["staff-of-withering"]` Frost-Brand-
            # style always-on rider (gated on the inventory item being
            # equipped+attuned). The 3-charge limit and the DC 15 CON
            # ability-drain save are GM-narrated in v1. On-theme for a warlock.
            {"name": "Staff of Withering", "attack_bonus": "+4", "damage": "1d6+1",
             "damage_type": "bludgeoning", "range": "5 ft",
             "_slug": "staff-of-withering",
             "desc": "Rare quarterstaff, attunement. On a hit, +2d10 necrotic (RAW: 1 of 3 charges; charge limit GM-narrated) AND the target makes a DC 15 CON save or is 'withered' — disadvantage on STR/CON checks + saves for 1 hour (v2.348.0; applies mechanically to a PC target's /roll checks/saves, installed + visible on NPC targets)."},
            # v2.349.0 — Staff of Striking (RAW DMG p.202, very rare,
            # attunement). A +3 magic quarterstaff: the +3 to attack/damage
            # is baked here (Magnus +4 base → +7 attack, 1d6+1 → 1d6+4). On a
            # hit it adds +1d6 force via the `_MAGIC_ITEM_ATTACK_RIDERS
            # ["staff-of-striking"]` always-on rider (the 1-charge minimum;
            # spending 2-3 charges + the 10-charge/dawn economy GM-narrated).
            {"name": "Staff of Striking", "attack_bonus": "+7", "damage": "1d6+4",
             "damage_type": "bludgeoning", "range": "5 ft",
             "_slug": "staff-of-striking",
             "desc": "Very rare quarterstaff, attunement. +3 to attack/damage (baked). On a hit, +1d6 force (RAW: 1 of up to 3 charges; spending more + the 10-charge/dawn economy GM-narrated)."},
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
            # v2.159.28 Phase 2b — weight_lb backfilled. Magnus STR 8 → 120 cap.
            {"name": "Quarterstaff", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "bludgeoning",
             "versatile": True, "properties": "versatile (1d8)",
             "_slug": "quarterstaff", "weight_lb": 4},
            {"name": "Studded leather", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "light", "ac_value": 12,
             "_slug": "studded-leather", "weight_lb": 13},
            {"name": "Arcane focus (orb of obsidian)", "type": "gear", "qty": 1,
             "weight_lb": 3,
             "desc": "Spellcasting focus — black volcanic glass. Channels Magnus's pact-bound magic; replaces material components for Warlock spells."},
            {"name": "Pact tome (Fiend's grimoire)", "type": "gear", "qty": 1,
             "weight_lb": 5,
             "desc": "Pact of the Tome would grant this as a Pact Boon; Magnus carries one as a flavor item ahead of taking Pact of the Tome at Lv 3 (or if you'd rather, he picked Pact of the Blade — held in reserve at Lv 3)."},
            {"name": "Disguise kit", "type": "gear", "qty": 1,
             "weight_lb": 3,
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
            # v2.206.0 — second save-condition wand, routed through the
            # generalized Wand of Fear handler. Wand of Paralysis (RAW
            # DMG p.213 — rare, attunement). 7 charges; spend 1 to fire
            # a ray at one creature within 60 ft → DC 15 CON save or
            # paralyzed for 1 minute (repeat save). Single-target (no
            # cone). Magnus is at 2/3 attuned items with this added.
            {"name": "Wand of Paralysis", "type": "gear", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "wand-of-paralysis",
             "desc": "RAW DMG p.213 (rare, attunement). 7 charges (regain 1d6+1 at dawn). Action: spend 1 charge to fire a ray at one creature within 60 ft — DC 15 CON save or Paralyzed for 1 min (repeat save at end of each turn). Wired via /use_item_action with action_key=\"cast-paralysis\"."},
            # v2.224.0 — capped-additive ability-bonus engine drop-in
            # (docs/plans/str-override.md). Ioun Stone of Intellect (RAW DMG
            # p.176, very rare, attunement): while orbiting your head it
            # *increases* your INT by 2, "to a maximum of 20" — a capped
            # ADD, distinct from the Headband's set-to-19. The single SRD
            # slug `ioun-stone` carries an empty default; the variant rides
            # the item via `_ability_bonus: {"INT": 2}` and the +20 cap from
            # the catalog passive. Seeded on Magnus (Warlock, base INT 10 →
            # effective 12, mod 0 → +1) — his 3rd attuned item (RAW max 3),
            # a pure-additive read with no set to confound it. The bonus
            # flows to INT saves + Arcana/History/Investigation/Nature
            # checks (/roll) automatically.
            {"name": "Ioun Stone of Intellect", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "ioun-stone", "_ability_bonus": {"INT": 2},
             "desc": "Very rare wondrous item, attunement. This dusty rose prism orbits your head and increases your Intelligence by 2, to a maximum of 20. RAW DMG p.176."},
            # v2.257.0 — Ring of X-ray Vision (RAW DMG p.193, rare,
            # attunement). The wearer can see into and through solid
            # matter (30-ft radius; blocked by 1 ft of stone / 1 in. of
            # metal / 3 ft of wood or dirt). Modeled as an attunement-
            # gated boolean derived read (xray_vision flag); the radius
            # + overuse-exhaustion clause are GM-narrated in v1. Seeded
            # on Magnus as his 4th attuned item — seed-load bypasses the
            # RAW 3-item cap (the cap is enforced at /attune runtime
            # only), and arcane sight is on-theme alongside his Devil's
            # Sight invocation.
            {"name": "Ring of X-ray Vision", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "ring-of-x-ray-vision",
             "desc": "RAW DMG p.193 (rare, attunement). Action: see into and through solid objects within 30 ft for 1 minute (blocked by 1 ft of stone / 1 in. of metal / 3 ft of wood or dirt). Using it again before a long rest risks 1 level of exhaustion (GM-narrated). Surfaces as the derived xray_vision flag."},
            # v2.265.0 — charged-items Phase 5: Wand of the War Mage, +2
            # (RAW DMG p.211, rare, attunement). A passive spell-attack
            # rider — no charges. The single SRD slug defaults to +1
            # (uncommon) in _MAGIC_ITEM_PASSIVES; this item rides the +2
            # (rare) tier via the per-item `_spell_attack_bonus` override
            # (mirrors the Ioun Stone `_ability_bonus` tier pattern). The
            # bonus folds into Magnus's Eldritch Blast (and any spell
            # attack) to-hit at cast time; the ignore-half-cover clause is
            # GM-narrated. Magnus (Fiend Warlock — the demo's blaster) is
            # the natural wielder; his 5th attuned item (seed-load bypasses
            # the RAW 3-item cap, enforced at /attune runtime only).
            {"name": "Wand of the War Mage, +2", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "wand-of-the-war-mage", "_spell_attack_bonus": 2,
             "desc": "Rare wand, attunement. While holding this wand you gain a +2 bonus to spell attack rolls and ignore half cover when making a spell attack. RAW DMG p.211."},
            # v2.272.0 — charged-items Phase 2: Staff of Thunder and
            # Lightning (RAW DMG p.202, very rare, attunement). 5 charges
            # (regain 1d6+1 at dawn). v1 surfaces the marquee Thunder
            # action — a 60-ft-radius thunderclap centered on the wielder,
            # DC 17 CON save → 2d6 thunder (half on a pass) — through the
            # generalized save-for-half AoE-damage handler. Magnus (Bronze
            # Dragonborn — lightning resistance, eldritch blaster) is the
            # on-theme wielder; his 6th attuned item (seed-load bypasses
            # the RAW 3-item cap, enforced at /attune runtime only). The
            # RAW deafen-1-min-on-fail rider + the Lightning / Lightning
            # Strike / combined 5-charge properties are GM-narrated in v1.
            # Paired with the staff-of-thunder-and-lightning resource row.
            {"name": "Staff of Thunder and Lightning", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "staff-of-thunder-and-lightning", "weight_lb": 4,
             "desc": "Very rare staff, attunement. 5 charges (regain 1d6+1 at dawn). Thunder (2 charges): each creature within 60 ft makes a DC 17 CON save — 2d6 thunder + deafened 1 min on a fail, half + no deafen on a pass. Also a magic quarterstaff with Lightning / Lightning Strike / combined properties (GM-narrated). RAW DMG p.202."},
            # v2.284.0 — Boots of Levitation (RAW DMG p.155, rare,
            # attunement). The first item on the NEW `levitate_at_will`
            # boolean substrate: while worn you can use an action to cast the
            # levitate spell on yourself at will. The flag rides the
            # `boots-of-levitation` catalog payload, aggregates in
            # `_equipped_item_effects` (boolean OR), and surfaces on
            # /sheet-json as `derived.levitate_at_will`. The action cost + the
            # spell's vertical-move / 20-min-concentration mechanics are
            # GM-narrated in v1. Seeded as inert spare loot
            # (unequipped/unattuned) so it adds no flag to Magnus's baseline
            # and disturbs no existing test — the harness PATCHes it
            # equipped+attuned, reads the derived flag, then restores. A
            # hovering Fiend-pact Warlock is on-theme.
            {"name": "Boots of Levitation", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "_slug": "boots-of-levitation", "weight_lb": 1,
             "desc": "Rare wondrous item, attunement. While you wear these boots, you can use an action to cast the levitate spell on yourself at will. RAW DMG p.155."},
            # v2.293.0 — Cloak of the Bat (RAW DMG p.158, rare, attunement).
            # The headline passive — "while wearing this cloak, you have
            # advantage on Dexterity (Stealth) checks" — rides the v2.253.0
            # check_advantage_on substrate (Cloak of Elvenkind / Boots of
            # Elvenkind / Eyes of the Eagle), keyed on the Stealth skill and
            # attunement-gated. The dim-light/darkness flight (40 ft) and the
            # polymorph-into-bat action are GM-narrated in v1. Seeded as inert
            # spare loot (unequipped/unattuned) so it adds no advantage to
            # Magnus's baseline and disturbs no existing test — the harness
            # PATCHes it equipped+attuned, rolls a Stealth check, then restores.
            # A Fiend-pact Warlock with Devil's Sight (sees in magical darkness)
            # is the natural wielder of a cloak that flies in darkness.
            {"name": "Cloak of the Bat", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "_slug": "cloak-of-the-bat", "weight_lb": 1,
             "desc": "Rare wondrous item, attunement. While wearing this cloak, you have advantage on Dexterity (Stealth) checks. In dim light or darkness you can grip its edges to fly at 40 ft, and can use an action to cast polymorph on yourself to become a bat (once per dawn). RAW DMG p.158."},
            # v2.305.0 — Ring of Elemental Command (Fire) (RAW DMG p.190,
            # legendary, attunement). The Fire variant grants resistance to
            # fire damage the moment you attune (the Air/Earth/Water resistances
            # are gated behind slaying an elemental — only Fire is immediate).
            # Lands on the `_resistance_type` substrate (Ring of Resistance /
            # Dragon Scale Mail): the resisted type rides this item, the walker
            # folds it into `resistance_to`, and `_resistance_halve` halves
            # matching damage. Seeded inert (unequipped/unattuned) so it adds no
            # resistance to Magnus's baseline (his Bronze Dragonborn resistance
            # is LIGHTNING, not fire) — the harness PATCHes it equipped+attuned,
            # deals fire damage, asserts the halving, then restores. The 5-charge
            # spell list, dominate-monster, advantage-vs-fire-elementals, Ignan
            # speech, and post-slay fire immunity are GM-narrated in v1. A Fiend-
            # pact Warlock attuned to the Elemental Plane of Fire is on-theme.
            {"name": "Ring of Elemental Command (Fire)", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "_slug": "ring-of-elemental-command", "_resistance_type": "fire",
             "weight_lb": 0,
             "desc": "Legendary ring, attunement. Linked to the Elemental Plane of Fire: you have advantage on attack rolls against fire elementals (and they have disadvantage against you), resistance to fire damage, and can speak Ignan. 5 charges (regain 1d4+1 at dawn): cast dominate monster on a fire elemental (2 charges), burning hands (1), fireball (2), or wall of fire (3). After helping slay a fire elemental you gain immunity to fire damage. RAW DMG p.190."},
            # v2.329.0 — "The Captor's Cache" bundle: Iron Flask (RAW DMG
            # p.178, legendary, no attunement). Brass flask stoppered by an
            # iron plug. Action: target a creature you can see within 60 ft
            # and speak the command word — the target makes a DC 17 WIS
            # save or is trapped inside the flask. A creature already
            # inside can be released by removing the plug; on release the
            # creature is friendly to you for 1 hour and obeys your
            # commands. Stub catalog row; the WIS-save trap + release are
            # GM-narrated. Thematic on Magnus (Fiend-pact Warlock — a
            # creature-capturing flask fits his dark-magic aesthetic).
            {"name": "Iron Flask", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 1,
             "_slug": "iron-flask",
             "desc": "Legendary wondrous item, no attunement. Brass flask with an iron plug. Action: target a creature within 60 ft — DC 17 WIS save or the creature is trapped inside (only one creature at a time; demon lords, devil princes, archfey, and other very powerful beings are immune). On release the creature is charmed-friendly for 1 hour. RAW DMG p.178."},
            # v2.333.0 — "The Artisan's Spread" bundle: Robe of Useful
            # Items (RAW DMG p.195, uncommon, no attunement). Patched
            # cloth robe with 2d4+8 (10-16) cloth patches sewn onto it,
            # each embroidered with a distinct image: dagger, lantern,
            # mirror, pole, hempen rope, sack, etc. Action: pluck a patch
            # — the embroidered item becomes the real object in the
            # plucker's hand. Once plucked, that patch is gone for good.
            # Stub catalog row; the per-patch contents + activation are
            # GM-narrated. Thematic on Magnus (Fiend-pact Warlock — a
            # robe-of-clever-tricks fits his arcane scholar aesthetic).
            {"name": "Robe of Useful Items", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 4,
             "_slug": "robe-of-useful-items",
             "desc": "Uncommon wondrous item, no attunement. Patched cloth robe with 2d4+8 cloth patches (each embroidered with a distinct image: dagger, lantern, mirror, pole, hempen rope, sack, etc.). Action: pluck a patch — the embroidered item becomes a real object in your hand. Once plucked, the patch is gone. RAW DMG p.195."},
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
            # v2.403.7 — magic-items-automation Phase 9.2 Bucket A
            # holdout #2: Medallion of Thoughts (RAW DMG p.182). 3
            # charges + 1d3/dawn recharge. The medallion is seeded
            # INERT on Magnus (vault loot at line ~7303); the harness
            # PATCHes equipped+attuned. The detect-thoughts probe + DC
            # 13 WIS save are GM-narrated; this row backs the charge
            # decrement.
            {
                "key": "medallion-of-thoughts",
                "name": "Medallion of Thoughts",
                "current": 3, "max": 3, "reset": "long",
                "charge_recovery": "1d3",
                "source": "item-medallion-of-thoughts",
                "desc": "3 charges. Action: expend 1 to cast Detect Thoughts (DC 13 WIS) — probe a target's surface thoughts for 1 minute (concentration). Regains 1d3 charges at dawn. RAW DMG p.182.",
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
            # v2.206.0 — Wand of Paralysis charge counter. Same shape
            # as the Wand of Fear (7 charges, 1d6+1 recharge); the
            # save / condition live in the catalog action_def.
            {
                "key": "wand-of-paralysis",
                "name": "Wand of Paralysis",
                "current": 7, "max": 7, "reset": "long",
                "charge_recovery": "1d6+1",
                "source": "magic item — Wand of Paralysis",
                "class_slug": "item",
                "desc": "RAW DMG p.213. 7 charges. Spend 1 via /use_item_action (cast-paralysis): ray at one creature within 60 ft, DC 15 CON save or Paralyzed 1 min. Recovers 1d6+1 at dawn.",
                "manual": False,
            },
            # v2.272.0 — Staff of Thunder and Lightning charge counter
            # (RAW DMG p.202): 5 charges, regain 1d6+1 at dawn (the
            # long-rest path reads ``charge_recovery``). The generalized
            # save-for-half AoE-damage handler decrements 2 per Thunder.
            # v2.367.0 — Talisman of Ultimate Evil charge pool (RAW DMG
            # p.207): 6 charges, regain all at dawn (long rest). The
            # talisman item itself is seeded INERT on Magnus (Armory's
            # Remainder vault loot, line 6960) — the harness PATCHes
            # equipped+attuned and invokes via /use_item_action. Seeding
            # the resource row up front means the test doesn't need a
            # second PATCH to bootstrap it.
            {
                "key": "talisman-of-ultimate-evil",
                "name": "Talisman of Ultimate Evil",
                "current": 6, "max": 6, "reset": "long",
                "source": "magic item — Talisman of Ultimate Evil",
                "class_slug": "item",
                "desc": "6 charges (regain all at dawn). Invoke Ultimate Evil: action — spend 1 charge to force one creature within 60 ft to make a DC 18 CHA save → 8d6 necrotic on a fail, half on a save (RAW DMG p.207). Alignment gate + alignment-keyed instant-kill GM-narrated in v1.",
                "manual": False,
            },
            {
                "key": "staff-of-thunder-and-lightning",
                "name": "Staff of Thunder and Lightning",
                "current": 5, "max": 5, "reset": "long",
                "charge_recovery": "1d6+1",
                "source": "magic item — Staff of Thunder and Lightning",
                "class_slug": "item",
                "desc": "5 charges; Thunder costs 2 (2d6 thunder, 60-ft-radius thunderclap, DC 17 CON save, half on a pass). Regain 1d6+1 at dawn.",
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
            # v2.338.0 — Giant Slayer Shortsword (RAW DMG p.171, rare, NO
            # attunement, "any axe or sword"). The +1 attack/damage is baked
            # into this attack row (Rowan's main-hand finesse Shortsword:
            # DEX +4 + prof +3 + magic +1 = +8 / 1d6+5). On a hit vs a giant
            # the v2.158.93 condition rider adds +2d6 (weapon-type fallback →
            # piercing) AND the v2.158.102 on_hit_save fires a DC 15 STR save
            # or prone (the new v2.338.0 "prone" effect). Pairs thematically
            # with Rowan's Arrow of Slaying (Giants) — a dedicated
            # giant-hunting Ranger. No attunement → the rider fires on slug
            # match alone (equipped state irrelevant to the gate).
            {"name": "Giant Slayer Shortsword", "attack_bonus": "+8",
             "damage": "1d6+5", "damage_type": "piercing",
             "range": "5 ft", "_slug": "giant-slayer",
             "desc": "Rare shortsword, no attunement. +1 attack/damage; on a hit vs. a giant, +2d6 piercing and the giant makes a DC 15 STR save or falls prone (RAW DMG p.171). 'Giant' includes ettins and trolls."},
            # v2.361.0 — Magic-items: Oathbow (RAW DMG p.183, very rare,
            # attunement, longbow). RAW gives NO magical attack/damage
            # bonus to the bow itself — the +3d6 piercing + advantage
            # only fire vs the wielder's declared sworn enemy, via the
            # new `condition_sworn_enemy` predicate (section 6c) +
            # `_attacker_has_vow_of_enmity_vs_target` reuse for the d20
            # advantage. So the attack row mirrors Rowan's base Longbow
            # (+7 / 1d8+4 piercing). The inventory item is seeded INERT
            # (spare loot, attunement-cap-friendly) — the harness
            # PATCHes equipped+attuned per test + POSTs
            # `/declare_oathbow_sworn_enemy`, then restores. The
            # disadvantage-on-other-weapons + ignore-resistance +
            # 7-day duration clauses are GM-narrated in v1 (the buff
            # lasts 1 minute like Vow of Enmity).
            {"name": "Oathbow", "attack_bonus": "+7", "damage": "1d8+4",
             "damage_type": "piercing", "range": "150/600 ft",
             "_slug": "oathbow",
             "desc": "Very rare longbow, attunement. Speak the command word to designate a sworn enemy; vs that target you have advantage on attack rolls + deal +3d6 piercing on a hit (RAW DMG p.183)."},
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
            # v2.159.28 Phase 2b — weight_lb. Rowan STR 12 → 180 cap.
            {"name": "Longbow", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 2,
             "damage": "1d8", "damage_type": "piercing",
             "range": "150/600 ft",
             "properties": "ammunition, heavy, two-handed",
             "_slug": "longbow", "weight_lb": 2},
            {"name": "Arrows", "type": "ammunition", "qty": 40,
             "_slug": "arrow", "weight_lb": 0.05,  # 1 lb / 20 arrows
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
             "properties": "finesse, light", "_slug": "shortsword",
             "weight_lb": 2},
            {"name": "Studded leather", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "light", "ac_value": 12,
             "_slug": "studded-leather", "weight_lb": 13},
            {"name": "Explorer's pack", "type": "gear", "qty": 1,
             "weight_lb": 59,
             "desc": "Backpack, bedroll, mess kit, tinderbox, 10 torches, 10 days rations, waterskin, 50 ft hempen rope."},
            {"name": "Hunting trap", "type": "gear", "qty": 1,
             "weight_lb": 25,
             "desc": "Outlander background — set for 1 action; STR check DC 13 to escape."},
            {"name": "Bowstring trinket", "type": "gear", "qty": 1,
             "desc": "Outlander background trinket — Rowan's first bowstring, kept wound around a wood charm."},
            {"name": "Potion of Healing", "type": "consumable", "qty": 2,
             "consumable": True, "use_kind": "heal", "heal_dice": "2d4+2",
             "_slug": "potion-of-healing",
             "desc": "Drink to regain 2d4+2 HP. RAW: action."},
            # v2.219.0 — ability-score override engine drop-in
            # (docs/plans/str-override.md). Gauntlets of Ogre Power (RAW DMG
            # p.171, uncommon, attunement): while worn, STR *becomes* 19 if
            # not already higher. Same `ability_set` substrate as the Belt
            # of Giant Strength, on STR — composes with it via the
            # highest-wins map. Seeded on Rowan (Ranger, base STR 12 → mod
            # +1) — his 1st attuned item (RAW max 3) — so effective STR 19
            # (mod +4): a +3 STR-save/check delta and carry cap 180 → 285.
            {"name": "Gauntlets of Ogre Power", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "gauntlets-of-ogre-power",
             "desc": "Uncommon wondrous item, attunement. Your Strength score is 19 while worn (no effect if your STR is already 19+). RAW DMG p.171."},
            # v2.225.0 — Ioun Stone of Charisma (RAW DMG p.176, very rare,
            # attunement). Capped-additive +2 CHA to a max of 20 (the
            # v2.224.0 `ability_bonus` substrate).
            # v2.247.0 — DETUNED (kept equipped, attuned: False) to free
            # Rowan's 3rd attunement slot for the Boots of the Winterlands
            # below. CHA-via-ioun is a dump-stat demo on a ranger; dropping the
            # CHA row from test_item_ioun_stone.py's _VARIANTS leaves DEX/WIS
            # + the INT primary still proving the shared `ioun-stone` slug.
            # Originally seeded on Rowan (Ranger, dump CHA 8 → effective 10,
            # mod −1 → 0) — was his 2nd attuned item (after the Gauntlets).
            {"name": "Ioun Stone of Charisma", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": False,
             "_slug": "ioun-stone", "_ability_bonus": {"CHA": 2},
             "desc": "Very rare wondrous item, attunement. This pale lavender ellipsoid orbits your head and increases your Charisma by 2, to a maximum of 20. RAW DMG p.176."},
            # v2.230.0 — sustenance passive drop-in. Ioun Stone of
            # Sustenance (RAW DMG p.176, rare, attunement): a clear spindle
            # that removes the need to eat or drink while it orbits your
            # head. The flag rides the shared `ioun-stone` slug via
            # `_no_food_or_drink` (no ability payload), surfacing on
            # `/sheet-json` derived.no_food_or_drink — a fitting boon for a
            # ranger on long wilderness treks. (His second ioun stone; after
            # the v2.247.0 Charisma detune it's his 2nd attuned item.)
            {"name": "Ioun Stone of Sustenance", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "ioun-stone", "_no_food_or_drink": True,
             "desc": "Rare wondrous item, attunement. This clear spindle orbits your head; while it does, you don't need to eat or drink. RAW DMG p.176."},
            # v2.241.0 — Ring of Water Walking (RAW DMG p.193, uncommon, no
            # attunement). Rides alongside Rowan's full 3/3 attunement
            # loadout because it needs no attunement slot. While worn he can
            # stand on and move across any liquid surface as if it were solid
            # ground. The `water_walk` flag rides the `ring-of-water-walking`
            # catalog payload and surfaces on /sheet-json as derived.water_walk
            # — fitting for a ranger crossing rivers and marshes on the hunt.
            {"name": "Ring of Water Walking", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 0,
             "_slug": "ring-of-water-walking",
             "desc": "Uncommon wondrous item, no attunement. While wearing this ring, you can stand on and move across any liquid surface as if it were solid ground. RAW DMG p.193."},
            # v2.247.0 — Boots of the Winterlands (RAW DMG p.156, uncommon,
            # attunement). Rowan's 3rd attuned item (Gauntlets of Ogre Power +
            # Ioun Stone of Sustenance + this, RAW max 3) — homed by detuning
            # his Ioun Stone of Charisma above. Reuses the v2.246.0 Ring of
            # Warmth cold substrate with ZERO new engine code: cold resistance
            # via the catalog `resistance_to: ["cold"]` payload (folds into the
            # live `_resistance_halve` pipeline) + the `cold_tolerance` boolean
            # flag (derived.cold_tolerance). The ignore-ice/snow-difficult-
            # terrain rider is GM-narrated in v1. A natural boon for a ranger
            # ranging the frozen wilds.
            {"name": "Boots of the Winterlands", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 1,
             "_slug": "boots-of-the-winterlands",
             "desc": "Uncommon wondrous item, attunement. While you wear these furred boots, you have resistance to cold damage, you ignore difficult terrain created by ice or snow, and you can tolerate temperatures as low as -50 degrees Fahrenheit (or -100 in heavy clothing). RAW DMG p.156."},
            # v2.253.0 — Cloak of Elvenkind (RAW DMG p.158, uncommon,
            # attunement) — advantage/disadvantage Phase 4b. While worn with
            # the hood up the wearer has advantage on Dexterity (Stealth)
            # checks; the v1 model surfaces that always-on Stealth-check
            # advantage through `_roll_item_check_advantage` on Rowan's /roll.
            # Rowan's 4th attuned item — fine at seed-load since the RAW 3/3
            # cap is enforced only at the /attune runtime endpoint (Cloak of
            # Displacement / Lyra precedent, v2.252.0). On-theme for a forest
            # ranger slipping through the underbrush. The "Wisdom (Perception)
            # checks to see you have disadvantage" half is a target-side
            # perceiver read (filed Phase 4b). Read on /sheet-json as
            # derived.check_advantage_on.
            {"name": "Cloak of Elvenkind", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 1,
             "_slug": "cloak-of-elvenkind",
             "desc": "Uncommon wondrous item, attunement. While you wear this cloak with its hood up, Wisdom (Perception) checks made to see you have disadvantage, and you have advantage on Dexterity (Stealth) checks made to hide. RAW DMG p.158."},
            # v2.261.0 — Bracers of Archery (RAW DMG p.156, uncommon,
            # attunement). While worn the wearer has proficiency with the
            # longbow and shortbow and gains +2 to damage rolls on ranged
            # attacks made with such weapons. The +2 ranged-bow damage bonus
            # rides the `bracers-of-archery` catalog payload via
            # `ranged_bow_damage_bonus` and is applied to Rowan's Longbow
            # attacks at /attack time (gated on a "bow" ranged weapon that
            # isn't a crossbow); the proficiency half is GM-narrated. On the
            # forearms — distinct from his Gauntlets of Ogre Power (hands).
            # Rowan's 5th attuned item; fine at seed-load since the RAW 3/3
            # cap is enforced only at the /attune runtime endpoint. A natural
            # boon for the demo's dedicated archer.
            {"name": "Bracers of Archery", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 1,
             "_slug": "bracers-of-archery",
             "desc": "Uncommon wondrous item, attunement. While wearing these bracers, you have proficiency with the longbow and shortbow, and you gain a +2 bonus to damage rolls on ranged attacks made with such weapons. RAW DMG p.156."},
            # v2.270.0 — Gem of Seeing (RAW DMG p.171, rare, attunement). The
            # first `action_kind: "buff"` charged item: spend 1 of 3 charges
            # to gaze through the gem and gain truesight out to 60 ft for 10
            # minutes (100 rounds). Routes through /use_item_action's
            # `gem-of-seeing` → `_use_item_action_buff` branch, which
            # decrements the charge and installs the `truesight` buff template
            # (`_SPELL_BUFF_MAP['truesight']`, effects {truesight_ft: 60}) on
            # Rowan's combatant. The gem regains 1d3 charges daily at dawn
            # (mapped to long rest via the `charge_recovery` substrate). A
            # natural scout's boon for the demo's Ranger. Rowan's 6th attuned
            # item — fine at seed-load since the RAW 3/3 cap is enforced only
            # at the /attune runtime endpoint.
            {"name": "Gem of Seeing", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 0,
             "_slug": "gem-of-seeing",
             "desc": "Rare wondrous item, attunement. The gem has 3 charges. As an action, you can speak a command word and expend 1 charge — for the next 10 minutes you have truesight out to 60 feet when peering through the gem. The gem regains 1d3 expended charges daily at dawn. RAW DMG p.171."},
            # v2.281.0 — Wings of Flying (RAW DMG p.214, rare, attunement).
            # Reuses the v2.238.0 Winged Boots flying-speed substrate with
            # zero new engine code: the `flying_speed` boolean flag rides the
            # `wings-of-flying` catalog payload, aggregates in
            # `_equipped_item_effects`, and surfaces on /sheet-json as
            # `derived.flying_speed`. The command-word activation + 1-hour
            # duration / 1d12-hour cooldown are GM-narrated in v1. Seeded as
            # inert spare loot (unequipped/unattuned) so it adds no flying
            # speed to Rowan's baseline and disturbs no existing test — the
            # harness PATCHes it equipped+attuned, reads the derived flag,
            # then restores. A flying cloak is on-theme for the demo's scout.
            {"name": "Wings of Flying", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "_slug": "wings-of-flying", "weight_lb": 0,
             "desc": "Rare wondrous item (cloak), attunement. While wearing this cloak, you can use an action to speak its command word, turning it into bat or bird wings that give you a flying speed of 60 feet for 1 hour (or until you repeat the command word). When the wings disappear, you can't use them again for 1d12 hours. RAW DMG p.214."},
            # v2.300.0 — Cloak of the Manta Ray (RAW DMG p.158, uncommon, NO
            # attunement). Composes two existing no-attunement boolean
            # substrates in one catalog payload: `water_breath` (the v2.256.0
            # Cap of Water Breathing flag) + `swim_speed` (the v2.242.0 Ring of
            # Swimming flag), both surfaced on /sheet-json as boolean derived
            # reads. The hood up/down action is GM-narrated. Seeded as inert
            # spare loot (unequipped/unattuned) so it adds neither flag to
            # Rowan's baseline (he carries Ring of Water Walking — water_walk,
            # a distinct flag — but no water_breath/swim_speed item) — the
            # harness PATCHes it equipped (no attune needed), reads the two
            # derived flags, then restores. An aquatic cloak is on-theme for a
            # wilderness ranger who already walks on water.
            {"name": "Cloak of the Manta Ray", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "_slug": "cloak-of-the-manta-ray", "weight_lb": 1,
             "desc": "Uncommon wondrous item, no attunement. While wearing this cloak with its hood up, you can breathe underwater and you have a swimming speed of 60 feet. Pulling the hood up or down requires an action. RAW DMG p.158."},
            # v2.338.0 — Giant Slayer Shortsword (RAW DMG p.171, rare, NO
            # attunement). Paired with the attack entry above via `_slug`.
            # No attunement → the +2d6-vs-giant rider + the DC 15 STR
            # save-or-prone fire on slug match alone (equipped state
            # irrelevant to the gate). Seeded equipped so it shows in
            # Rowan's loadout as his dedicated melee giant-killer alongside
            # the ranged Arrows of Slaying (Giants).
            {"name": "Giant Slayer Shortsword", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "piercing",
             "properties": "finesse, light, magic",
             "_slug": "giant-slayer", "weight_lb": 2,
             "desc": "Rare shortsword, no attunement. +1 attack/damage. On a hit vs. a giant (including ettins and trolls), the giant takes an extra 2d6 piercing and must succeed on a DC 15 Strength save or fall prone. RAW DMG p.171."},
            # v2.332.0 — "The Elemental Conclave" bundle: Bowl of Commanding
            # Water Elementals (RAW DMG p.156, rare, no attunement). 6-lb
            # silver bowl. Action: fill with water and speak the command
            # word — a water elemental appears within 30 ft. CHA check vs
            # the elemental's CHA to command it for 1 hour. Stub catalog
            # row; the summon + control mechanic is GM-narrated. Thematic
            # on Rowan (Hunter Ranger — outdoorsman commanding nature's
            # forces, water as his alpine + river travel companion).
            {"name": "Bowl of Commanding Water Elementals", "type": "magic",
             "qty": 1, "equippable": True, "equipped": True, "weight_lb": 6,
             "_slug": "bowl-of-commanding-water-elementals",
             "desc": "Rare wondrous item, no attunement. 6-lb silver bowl. Action: fill with water and speak the command word — a water elemental appears within 30 ft. CHA check vs the elemental's CHA to command it (concentration, up to 1 hour). RAW DMG p.156."},
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
        # class_features carry the announce-only buttons.
        #
        # v2.270.0 — Gem of Seeing charge pool. The gem ships with 3
        # charges; spending 1 via /use_item_action installs the truesight
        # buff. `charge_recovery: "1d3"` rolls 1d3 regained on the matching
        # rest (RAW "daily at dawn" → long rest) instead of a full refill,
        # through the v2.158.86 recharge-dice substrate.
        "resources": [
            {"key": "gem-of-seeing", "name": "Gem of Seeing charges",
             "current": 3, "max": 3, "per": "long", "charge_recovery": "1d3"},
            # v2.403.0 — magic-items-automation Phase 9.2: charge-tracked
            # announce-only Bucket D item. Bowl of Commanding Water
            # Elementals (RAW DMG p.156) — 1/dawn. The bowl is seeded
            # equipped on Rowan (line 4461). The summon + CHA control
            # check are GM-narrated; this resource row backs the
            # /use_item_action endpoint's charge decrement.
            {
                "key": "bowl-of-commanding-water-elementals",
                "name": "Bowl of Commanding Water Elementals",
                "current": 1, "max": 1, "reset": "long",
                "source": "item-bowl-of-commanding-water-elementals",
                "desc": "1/dawn. Fill with water + speak the command word: a water elemental appears within 30 ft. Make a CHA check vs the elemental to command it (GM-narrated, concentration up to 1 hour).",
                "manual": False,
            },
        ],
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
            # v2.320.0 — Magic-items: Vicious Greataxe (RAW DMG p.209 — Vicious
            # Weapon variant, rare, NO attunement). On a natural 20 attack the
            # `_apply_magic_item_nat_20_effect` post-hit handler rolls an extra
            # 2d6 damage of the weapon's type (slashing here, falls through
            # from the attack's `damage_type`). Stacks compositionally with
            # Krieger's Half-Orc Savage Attacks (+1 weapon die on a crit) for
            # a savage nat-20 burst. The `_slug` field is the rider gate; no
            # attunement check needed (substrate skips it for
            # `requires_attunement: False` items).
            {"name": "Vicious Greataxe", "attack_bonus": "+7",
             "damage": "1d12+4", "damage_type": "slashing",
             "range": "5 ft", "_slug": "vicious-weapon",
             "desc": "Rare greataxe, no attunement. 1d12+4 slashing; on a natural 20 attack roll, deal +2d6 slashing (RAW DMG p.209). Two-handed, heavy."},
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
            # v2.225.0 — Ioun Stone of Wisdom (RAW DMG p.176, very rare,
            # attunement). Capped-additive +2 WIS to a max of 20 (the
            # v2.224.0 `ability_bonus` substrate). Seeded on Krieger
            # (Barbarian, WIS 13 → effective 15, mod +1 → +2).
            # v2.249.0 — DETUNED (attuned: True → False, kept equipped) to
            # free Krieger's 3rd attunement slot (RAW max 3) for the Brooch
            # of Shielding below. Last in the ability-ioun sacrifice series
            # (STR→CON→CHA→DEX→WIS). The stone still orbits his head but no
            # longer grants the +2 WIS while detuned; its slug stays
            # catalogued so a future re-attune is a one-flag flip.
            {"name": "Ioun Stone of Wisdom", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": False,
             "_slug": "ioun-stone", "_ability_bonus": {"WIS": 2},
             "desc": "Very rare wondrous item, attunement. This incandescent blue sphere orbits your head and increases your Wisdom by 2, to a maximum of 20. RAW DMG p.176."},
            # v2.231.0 — awareness passive drop-in. Ioun Stone of Awareness
            # (RAW DMG p.176, rare, attunement): a dark blue rhomboid that
            # keeps you from being surprised while it orbits your head. The
            # flag rides the shared `ioun-stone` slug via
            # `_cannot_be_surprised` (no ability payload), surfacing on
            # `/sheet-json` derived.cannot_be_surprised. Krieger's 2nd
            # attuned item (after the Ioun Stone of Wisdom, RAW max 3) and
            # his second ioun stone — a thematic fit for a Barbarian's
            # Danger Sense.
            {"name": "Ioun Stone of Awareness", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "ioun-stone", "_cannot_be_surprised": True,
             "desc": "Rare wondrous item, attunement. This dark blue rhomboid orbits your head; while it does, you can't be surprised. RAW DMG p.176."},
            # v2.239.0 — Boots of Speed (RAW DMG p.155, rare, attunement).
            # Krieger's 3rd attuned item (after the two Ioun Stones, RAW
            # max 3). A bonus action doubles his walking speed and gives
            # opportunity attacks against him disadvantage. The
            # `speed_doubling` flag rides the `boots-of-speed` catalog
            # payload and surfaces on /sheet-json as derived.speed_doubling
            # — on-theme for a Barbarian closing distance on a target.
            {"name": "Boots of Speed", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 1,
             "_slug": "boots-of-speed",
             "desc": "Rare wondrous item, attunement. Bonus action to click the heels together: your walking speed doubles and opportunity attacks against you have disadvantage, for up to 10 minutes. RAW DMG p.155."},
            # v2.249.0 — Brooch of Shielding (RAW DMG p.156, uncommon,
            # attunement). Reuses the v2.235.0 `resistance_to` live-halving
            # substrate for force damage plus a new `magic_missile_immune`
            # boolean surfaced on /sheet-json derived. Krieger's 3rd attuned
            # item (RAW max 3) — homed in the slot freed by detuning his
            # Ioun Stone of Wisdom above. Weightless (a small brooch).
            {"name": "Brooch of Shielding", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 0,
             "_slug": "brooch-of-shielding",
             "_resistance_type": "force",
             "desc": "Uncommon wondrous item, attunement. While wearing this brooch you have resistance to force damage and immunity to the magic missile spell. RAW DMG p.156."},
            # v2.271.0 — Horn of Blasting (RAW DMG p.174, uncommon, NO
            # attunement). Closes charged-items Phase 3: a save-for-half
            # AoE-damage charge action with NO resource row (the horn has
            # no charges — it's at-will, with a RAW 20% self-destruct risk
            # per blow that is GM-narrated in v1). The `blast` action
            # routes through /use_item_action's `horn-of-blasting` →
            # `_use_item_action_horn_of_blasting` branch: each creature in
            # a 30-ft cone makes a DC 15 CON save → 5d6 thunder + deafened
            # 1 minute on a fail, half damage + no deafen on a pass. No
            # attunement → it doesn't compete for Krieger's 3/3 cap. A war
            # horn is on-theme for a bellowing Half-Orc Barbarian.
            {"name": "Horn of Blasting", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 2,
             "_slug": "horn-of-blasting",
             "desc": "Uncommon wondrous item (no attunement). As an action, blow the horn to emit a thunderous blast in a 30-foot cone. Each creature in that area makes a DC 15 Constitution saving throw — on a fail, 5d6 thunder damage and deafened for 1 minute; on a success, half damage and no deafen. RAW DMG p.174: each time you blow it there is a 20% chance the horn explodes (10d6 fire to you, horn destroyed) — GM-narrated."},
            # v2.320.0 — Vicious Greataxe (RAW DMG p.209 — Vicious Weapon
            # variant, rare, NO attunement). Paired with the attack entry
            # above via `_slug`. Seeded equipped=True (the substrate skips the
            # equipped/attuned check for no-attunement items — slug match
            # alone is sufficient), but the equip state matters for the
            # carry-weight + inventory-view shape. The nat-20 +2d6 rider fires
            # from the post-hit handler when the d20 lands natural 20 — no
            # creature exempt list, no condition predicate. Pairs nicely with
            # Krieger's Half-Orc Savage Attacks (+1 weapon die on a crit) for
            # a savage nat-20 burst. No attunement → no impact on Krieger's
            # 3/3 attunement count (Ioun Stone of Awareness + Boots of Speed
            # + Brooch of Shielding, RAW max). Heavier than the seed Greataxe
            # to reflect the magic-imbued weight increase (8 lb vs 7).
            {"name": "Vicious Greataxe", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True,
             "hands": 2, "damage": "1d12", "damage_type": "slashing",
             "properties": "heavy, two-handed, magic",
             "_slug": "vicious-weapon", "weight_lb": 8,
             "desc": "Rare greataxe, no attunement. When you roll a 20 on your attack roll with this magic weapon, your critical hit deals an extra 2d6 damage of the weapon's type (slashing). RAW DMG p.209 (Vicious Weapon variant)."},
            # v2.327.0 — "The Wayfarer's Trio" bundle: Bag of Devouring (RAW
            # DMG p.153, very rare, no attunement). Superficially resembles
            # a Bag of Holding but is a feeding orifice for a gigantic
            # extradimensional creature: living matter dropped in is
            # devoured; reaching in has a 50% chance of pulling the
            # creature inside. Inanimate objects are spat into another
            # plane once per day. Pure GM-narrated mechanic; catalog row is
            # a stub passive so the slug counts in the audit. Thematic on
            # Krieger (Half-Orc Barbarian — a cursed horror-bag fits his
            # raging adventurer aesthetic and pairs grimly with his
            # Mariner's-ally Brooch of Shielding loot).
            {"name": "Bag of Devouring", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 15,
             "_slug": "bag-of-devouring",
             "desc": "Very rare wondrous item, no attunement. Superficially resembles a Bag of Holding but is the feeding orifice of an extradimensional creature. Living matter placed inside is devoured. Reaching in has a 50% chance of pulling the creature inside (DC 15 STR check to escape; DC 20 STR check from outside to pull a creature out). Inanimate objects are spat into another plane once per day. If pierced or torn, contents transport to a random Astral Plane location. RAW DMG p.153."},
            # v2.329.0 — "The Captor's Cache" bundle: Iron Bands of Binding
            # (RAW DMG p.176, rare, no attunement). Small rusty iron sphere
            # (2-lb), action to hurl at a Huge or smaller target within 60
            # ft. On a successful ranged attack roll (treat as proficient),
            # the sphere unfolds into metal bands that restrain the target.
            # On a fail, the sphere returns to its small form. The wielder
            # ends the restraint as a bonus action; otherwise lasts until
            # the target escapes via DC 20 STR check or 25 STR magical
            # effect. Stub catalog row; the throw + restrain mechanic is
            # GM-narrated. Thematic on Krieger (Half-Orc Barbarian — a
            # brutal restraining throw fits his rage aesthetic and gives
            # him a non-Greataxe utility option).
            {"name": "Iron Bands of Binding", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 2,
             "_slug": "iron-bands-of-binding",
             "desc": "Rare wondrous item, no attunement. Small rusty iron sphere (2 lb). Action: hurl up to 60 ft at a Huge or smaller creature you can see. Treat as a proficient ranged attack. On a hit, the bands unfold and restrain the target until you end the effect as a bonus action (or the target escapes via DC 20 STR check or 25 STR magical effect). On a miss, the sphere returns. RAW DMG p.176."},
            # v2.332.0 — "The Elemental Conclave" bundle: Stone of
            # Controlling Earth Elementals (RAW DMG p.207, rare, no
            # attunement). 5-lb heavy stone. Action: place stone on the
            # ground and speak the command word — an earth elemental
            # appears within 30 ft. CHA check vs the elemental's CHA to
            # command it for 1 hour. Stub catalog row; the summon + control
            # mechanic is GM-narrated. Thematic on Krieger (Half-Orc
            # Barbarian — earthy raw strength + a literal stone for the
            # earth element completes the conclave's four-corner thematic).
            {"name": "Stone of Controlling Earth Elementals", "type": "magic",
             "qty": 1, "equippable": True, "equipped": True, "weight_lb": 5,
             "_slug": "stone-of-controlling-earth-elementals",
             "desc": "Rare wondrous item, no attunement. 5-lb heavy stone. Action: place on the ground and speak the command word — an earth elemental appears within 30 ft. CHA check vs the elemental's CHA to command it (concentration, up to 1 hour). RAW DMG p.207."},
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
            # v2.403.0 — magic-items-automation Phase 9.2: charge-tracked
            # announce-only Bucket D item. Stone of Controlling Earth
            # Elementals (RAW DMG p.207) — 1/dawn. The stone is seeded
            # equipped on Krieger (line 4782). The summon + CHA control
            # check are GM-narrated; this resource row backs the
            # /use_item_action endpoint's charge decrement.
            {
                "key": "stone-of-controlling-earth-elementals",
                "name": "Stone of Controlling Earth Elementals",
                "current": 1, "max": 1, "reset": "long",
                "source": "item-stone-of-controlling-earth-elementals",
                "desc": "1/dawn. Place on the ground + speak the command word: an earth elemental appears within 30 ft. Make a CHA check vs the elemental to command it (GM-narrated, concentration up to 1 hour).",
                "manual": False,
            },
            # v2.403.1 — magic-items-automation Phase 9.2 batch 2:
            # Iron Bands of Binding (RAW DMG p.176) — 1/dawn restrain
            # via ranged attack. The bands are seeded equipped on Krieger
            # (line 4769). The throw + restrain mechanic are GM-narrated;
            # this resource row backs the /use_item_action endpoint's
            # charge decrement.
            {
                "key": "iron-bands-of-binding",
                "name": "Iron Bands of Binding",
                "current": 1, "max": 1, "reset": "long",
                "source": "item-iron-bands-of-binding",
                "desc": "1/dawn. Action: hurl the sphere up to 60 ft at a Huge-or-smaller target. Ranged attack with DEX + PB; on a hit the bands unfold and restrain (DC 20 STR to escape; bonus action to release). RAW DMG p.176.",
                "manual": False,
            },
            # v2.403.3 — magic-items-automation Phase 9.2 batch 4:
            # Horn of Valhalla (RAW DMG p.175) — 1/7 days summon spirits.
            # The horn is seeded INERT on Krieger (vault loot at line
            # ~7100); the harness PATCHes equipped=True before invoking.
            # `reset: "none"` — GM manual reset when the 7-day cooldown
            # elapses in fiction.
            {
                "key": "horn-of-valhalla",
                "name": "Horn of Valhalla",
                "current": 1, "max": 1, "reset": "none",
                "source": "item-horn-of-valhalla",
                "desc": "1 use, then 7-day cooldown (GM manual reset). Action: blow the horn — warrior spirits (berserker stats) appear within 60 ft and fight as allies for 1 hour. Higher-metal horns require martial proficiency (GM-narrated). RAW DMG p.175.",
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
        "subclass": "Path of the Berserker",
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
            # v2.159.28 Phase 2b — weight_lb. Brakka STR 17 → 255 cap.
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
             "weight_lb": 59, "_in_bag_of_holding": True,
             "desc": "Backpack, bedroll, mess kit, tinderbox, 10 torches, 10 days rations, waterskin, 50 ft hempen rope."},
            # v2.159.30 — Phase 3 Bag of Holding demo fixture. Brakka
            # tags her Explorer's pack as `_in_bag_of_holding: True`
            # so the v2.159.27 substrate skips its 59 lb in the carry
            # sum. The bag itself adds 15 lb. Net: 7 (greataxe) + 8
            # (javelins) + 15 (bag) = 30 lb instead of 74 lb without
            # the bag. RAW DMG p.153 (uncommon, no attunement).
            {"name": "Bag of Holding", "type": "gear", "qty": 1,
             "equippable": True, "equipped": True,
             "_slug": "bag-of-holding", "weight_lb": 15,
             "desc": "RAW DMG p.153 (uncommon, no attunement). Holds up to 500 lb (tracked since v2.656.0 — the carry meter flags a rupture if exceeded). Bag weighs 15 lb regardless of contents. Tag items `_in_bag_of_holding: True` to discount their weight from the carry meter."},
            # v2.223.0 — ability-score override Phase 2c: the legendary top
            # tier of the Belt of Giant Strength (RAW DMG p.155, attunement).
            # The SRD's single `belt-of-giant-strength` slug defaults to the
            # Hill tier (STR 21) in _MAGIC_ITEM_PASSIVES; the per-item
            # `_ability_set` override (v2.215.0) rides THIS item to the Storm
            # tier (STR 29). Brakka (Barbarian, base STR 17 → mod +3) becomes
            # effective STR 29 (mod +9) — a +12 swing, the largest in the demo
            # — visible on /sheet-json `derived.effective_abilities` + a carry
            # jump (255 → 435). She had 0 attuned items, so this is her 1st of
            # the RAW-3 max. Completes the demonstrable tier span: Hill 21
            # (Garrik) → Stone 23 (Zara) → Storm 29 (Brakka). See
            # docs/plans/str-override.md.
            {"name": "Belt of Giant Strength (Storm)", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "belt-of-giant-strength", "_ability_set": {"STR": 29},
             "weight_lb": 0,
             "desc": "Legendary wondrous item, attunement. While worn, your Strength score becomes 29 (Storm giant) if it isn't already higher. RAW DMG p.155."},
            # v2.225.0 — Ioun Stone of Constitution (RAW DMG p.176, very
            # rare, attunement). Capped-additive +2 CON to a max of 20 (the
            # v2.224.0 `ability_bonus` substrate).
            # v2.246.0 — DETUNED (kept equipped, attuned: False) to free
            # Brakka's 3rd attunement slot for the Ring of Warmth below.
            # CON-via-ioun is the most redundant ability demo left after the
            # v2.245.0 STR drop — the Amulet of Health (Tavik) still covers the
            # CON `ability_bonus`/effective-max-HP surface, so dropping the CON
            # row from test_item_ioun_stone.py's _VARIANTS costs no net coverage.
            # Originally seeded on Brakka (Barbarian, CON 16 → effective 18,
            # mod +3 → +4) — was her 2nd
            # attuned item (after the Belt). The CON bump also demonstrates
            # the second-order effective-max-HP recompute (DERIVED
            # `effective_max_hp` on /sheet-json), since CON drives +mod/level
            # HP — the same surface the Amulet of Health exercises on CON.
            {"name": "Ioun Stone of Constitution", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": False,
             "_slug": "ioun-stone", "_ability_bonus": {"CON": 2},
             "desc": "Very rare wondrous item, attunement. This pink rhomboid orbits your head and increases your Constitution by 2, to a maximum of 20. RAW DMG p.176."},
            # v2.240.0 — Ring of Free Action (RAW DMG p.191, rare,
            # attunement). Difficult terrain costs her no extra movement, and
            # magic can't reduce her speed or paralyze/restrain her. The
            # `free_action` flag rides the `ring-of-free-action` catalog payload
            # and surfaces on /sheet-json as derived.free_action — on-theme for
            # an unrestrained beast barbarian.
            {"name": "Ring of Free Action", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 0,
             "_slug": "ring-of-free-action",
             "desc": "Rare wondrous item, attunement. While you wear this ring, difficult terrain doesn't cost you extra movement, and magic can neither reduce your speed nor cause you to be paralyzed or restrained. RAW DMG p.191."},
            # v2.246.0 — Ring of Warmth (RAW DMG p.193, uncommon, attunement).
            # Brakka's 3rd attuned item (Belt of Giant Strength + Ring of Free
            # Action + this, RAW max 3) — homed by detuning her Ioun Stone of
            # Constitution above. Grants resistance to cold damage (folds into
            # the `resistance_to` list via the catalog `resistance_to: ["cold"]`
            # payload, consulted live by `_resistance_halve` — the same surface
            # the Ring of Resistance exercises) plus tolerance of cold
            # environments down to −50°F (the `cold_tolerance` boolean flag,
            # surfaced on /sheet-json as derived.cold_tolerance).
            {"name": "Ring of Warmth", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 0,
             "_slug": "ring-of-warmth",
             "desc": "Uncommon ring, attunement. While wearing this ring, you have resistance to cold damage. In addition, you and everything you wear and carry are unharmed by temperatures as low as -50 degrees Fahrenheit. RAW DMG p.193."},
            # v2.331.0 — "The Trickster's Pouch" bundle: Bag of Tricks (RAW
            # DMG p.154, uncommon, no attunement). Small fur sack
            # containing 3 fuzzy balls. Action: pull one out, throw it up to
            # 20 ft, and it transforms into a random animal (size + CR
            # determined by the bag's color: gray, rust, or tan). The
            # animal acts as the wielder's ally for 10 minutes or until it
            # drops to 0 HP. Stub catalog row; the random-animal table is
            # GM-narrated. Thematic on Brakka (Goliath Beast Barbarian —
            # summoning animal allies fits the Path of the Beast aesthetic).
            {"name": "Bag of Tricks", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 0.5,
             "_slug": "bag-of-tricks",
             "desc": "Uncommon wondrous item, no attunement. Small fur sack with 3 fuzzy balls. Action: pull out + throw a ball up to 20 ft; on landing it transforms into a random animal (gray/rust/tan bag yields different size/CR pools). The animal acts as your ally for 10 min or until it drops to 0 HP. The bag refreshes its 3 balls at dawn (long rest). RAW DMG p.154."},
            # v2.337.0 — "The Bottled Tempest" bundle: Elemental Gem (RAW DMG
            # p.167, uncommon, no attunement). A small gem keyed to one
            # element (blue sapphire = air, yellow diamond = earth, red
            # corundum = fire, emerald = water). Action: crush the gem —
            # a CR 5 elemental of the matching type appears and obeys you
            # for 1 hour (or until it or you drop). The gem is destroyed on
            # use. Stub catalog row; the summon is GM-narrated. Thematic on
            # Brakka (Goliath Beast Barbarian — an elemental ally complements
            # the Path of the Beast summon aesthetic, alongside his Bag of
            # Tricks).
            {"name": "Elemental Gem", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "consumable": True,
             "weight_lb": 0,
             "_slug": "elemental-gem",
             "desc": "Uncommon wondrous item, no attunement. A gem keyed to one element (sapphire=air, diamond=earth, corundum=fire, emerald=water). Action: crush the gem — a CR 5 elemental of that type appears and obeys you for 1 hour (or until reduced to 0 HP). The gem is destroyed on use. RAW DMG p.167."},
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
            # v2.403.1 — magic-items-automation Phase 9.2 batch 2:
            # Bag of Tricks (RAW DMG p.154) — 3/dawn pulls. The bag is
            # seeded equipped on Brakka (line ~5104). The random-animal
            # roll + 10-min duration are GM-narrated; this resource row
            # backs the /use_item_action endpoint's per-pull decrement.
            {
                "key": "bag-of-tricks",
                "name": "Bag of Tricks",
                "current": 3, "max": 3, "reset": "long",
                "source": "item-bag-of-tricks",
                "desc": "3 pulls/dawn. Action: pull a fuzzy ball + throw up to 20 ft; it transforms into a random animal (rolled per bag color) that's friendly for 10 min or until 0 HP. RAW DMG p.154.",
                "manual": False,
            },
            # v2.403.2 — magic-items-automation Phase 9.2 batch 3:
            # Pipes of the Sewers (RAW DMG p.184) — 3 charges, regain
            # 1d3 at dawn. The pipes are seeded INERT on Brakka (vault
            # loot, equipped=False/attuned=False at line ~7114); the
            # harness PATCHes equipped+attuned before invoking. Resource
            # row is seeded up front so the dispatch can find it without
            # bootstrap.
            {
                "key": "pipes-of-the-sewers",
                "name": "Pipes of the Sewers",
                "current": 3, "max": 3, "reset": "long",
                "charge_recovery": "1d3",
                "source": "item-pipes-of-the-sewers",
                "desc": "3 charges; expend 1-3 (action) to summon that many rat swarms within 60 ft (if local rats are available). Regain 1d3 at dawn. RAW DMG p.184. Wind-instrument proficiency required (GM-narrated).",
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
        "subclass": "Way of the Open Hand",
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
            # v2.159.28 Phase 2b — weight_lb. Drunken Monk STR 12 → 180 cap.
            {"name": "Quarterstaff", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "bludgeoning",
             "versatile": True, "properties": "versatile (1d8), monk weapon",
             "_slug": "quarterstaff", "weight_lb": 4},
            {"name": "10 darts", "type": "weapon", "qty": 10,
             "equippable": True, "equipped": False, "hands": 1,
             "damage": "1d4", "damage_type": "piercing",
             "range": "20/60 ft", "properties": "finesse, thrown, monk weapon",
             "_slug": "dart", "weight_lb": 0.25},
            {"name": "Explorer's pack", "type": "gear", "qty": 1,
             "weight_lb": 59,
             "desc": "Backpack, bedroll, mess kit, tinderbox, 10 torches, 10 days rations, waterskin, 50 ft hempen rope."},
            {"name": "Jug of cheap wine", "type": "gear", "qty": 1,
             "weight_lb": 5,
             "desc": "Folk Hero flair — the prop the drunken weave hides behind."},
            # v2.226.0 — Belt of Dwarvenkind (RAW DMG p.155, rare,
            # attunement). Quan's 1st attuned item (he had none). Composes
            # two substrate fields at once: CON 14 → 16 (capped-additive
            # `ability_bonus`, same engine as the Ioun Stone) AND darkvision
            # 60 ft (`sees_in_darkness`, same field as Goggles of Night). As
            # a Human (non-dwarf) Quan qualifies for the belt's darkvision
            # gate. The CON +2 also bumps his effective max-HP (+1/level).
            {"name": "Belt of Dwarvenkind", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "hands": 0,
             "attuned": True, "weight_lb": 0,
             "_slug": "belt-of-dwarvenkind",
             "desc": "Rare wondrous item, attunement. CON +2 (max 20); advantage on saves vs poison and resistance to poison damage; darkvision 60 ft; advantage on CHA(Persuasion) with dwarves; speak/read/write Dwarvish. RAW DMG p.155."},
            # v2.232.0 — Ioun Stone of Mastery (RAW DMG p.176, legendary,
            # attunement). Quan's 2nd attuned item. Raises his proficiency
            # bonus by 1 (PB 3 → 4) via the shared `ioun-stone` slug + the
            # per-item `_proficiency_bonus` rider. Surfaced on /sheet-json
            # derived.proficiency_bonus and applied to his proficient
            # STR/DEX saves in /roll. Belt boosts only CON, so his DEX/STR
            # save proficiency reads the Mastery +1 unconfounded.
            {"name": "Ioun Stone of Mastery", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "hands": 0,
             "attuned": True, "weight_lb": 0,
             "_slug": "ioun-stone", "_proficiency_bonus": 1,
             "desc": "Legendary wondrous item, attunement. This dull grey ioun stone orbits your head and increases your proficiency bonus by 1. RAW DMG p.176."},
            # v2.236.0 — Mantle of Spell Resistance (RAW DMG p.180, rare,
            # attunement). Quan's 3rd attuned item (RAW max 3). While worn
            # you have advantage on saving throws against spells. Rides the
            # `mantle-of-spell-resistance` catalog payload (`spell_save_advantage`);
            # surfaced on /sheet-json as derived.spell_save_advantage. A
            # monk deflecting hostile magic with a flowing mantle is on-theme.
            {"name": "Mantle of Spell Resistance", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "hands": 0,
             "attuned": True, "weight_lb": 1,
             "_slug": "mantle-of-spell-resistance",
             "desc": "Rare wondrous item, attunement. You have advantage on saving throws against spells while you wear this cloak. RAW DMG p.180."},
            # v2.255.0 — Boots of Elvenkind (RAW DMG p.155, uncommon, NO
            # attunement). No-attunement companion to Cloak of Elvenkind on the
            # same check_advantage_on ["stealth"] substrate (v2.253.0). Rides
            # freely alongside Quan's full 3/3 attunement loadout (Belt + Ioun
            # + Mantle) — no attunement required, like Mira's Ring of Swimming.
            # On-theme for a soft-footed Drunken Master who slips away unseen.
            {"name": "Boots of Elvenkind", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 1,
             "_slug": "boots-of-elvenkind",
             "desc": "Uncommon wondrous item, no attunement. While you wear these boots, your steps make no sound, and you have advantage on Dexterity (Stealth) checks that rely on moving silently. RAW DMG p.155."},
            # v2.331.0 — "The Trickster's Pouch" bundle: Feather Token (RAW
            # DMG p.188, rare, no attunement). Tiny stylized feather; the
            # specific token type (anchor, bird, fan, swan boat, tree,
            # whip) determines its one-shot magical effect: e.g., "tree"
            # plants a fully-grown oak in 1 round, "fan" creates a wind
            # gust, "swan boat" summons a guided swan boat for 24 hours.
            # Token is consumed after activation. Stub catalog row; the
            # six per-type effects are GM-narrated. Thematic on Quan
            # (Drunken Master Monk — a feather-light trick item fits his
            # acrobatic / improvised-trick aesthetic).
            {"name": "Feather Token", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "consumable": True,
             "weight_lb": 0,
             "_slug": "feather-token",
             "desc": "Rare wondrous item, no attunement. A tiny stylized feather (one of six types: anchor, bird, fan, swan boat, tree, whip). Action: speak the command word — the token vanishes and triggers its one-shot effect (rooting a ship, calling a giant bird, summoning a wind gust, planting an oak, etc.). RAW DMG p.188."},
            # v2.336.0 — "The Escapist's Kit" bundle: Dust of Disappearance
            # (RAW DMG p.166, uncommon, no attunement). A pinch of fine
            # powder in a small packet. Action: throw the dust into the air
            # — you and everything within 10 ft of you become invisible for
            # 2d4 minutes (the duration is shared; attacking or casting ends
            # it for the attacker). Consumed on use. Stub catalog row; the
            # invisibility burst is GM-narrated. Thematic on Quan (Drunken
            # Master Monk — a vanishing-powder bolthole fits the elusive,
            # improvisational Drunken style).
            {"name": "Dust of Disappearance", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "consumable": True,
             "weight_lb": 0,
             "_slug": "dust-of-disappearance",
             "desc": "Uncommon wondrous item, no attunement. A packet of fine powder. Action: throw the dust into the air — you and each creature/object within 10 ft become invisible for 2d4 minutes. The duration is shared; attacking or casting a spell ends the invisibility for that creature. Consumed on use. RAW DMG p.166."},
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
            # v2.403.3 — magic-items-automation Phase 9.2 batch 4:
            # Rod of Security (RAW DMG p.193) — 1/10 days paradise shift.
            # The rod is seeded INERT on Quan (vault loot, equipped=False
            # at line ~7176); the harness PATCHes equipped=True before
            # invoking. `reset: "none"` so long-rest doesn't auto-refill —
            # the GM manually resets the counter when the 10-day cooldown
            # elapses in fiction.
            {
                "key": "rod-of-security",
                "name": "Rod of Security",
                "current": 1, "max": 1, "reset": "none",
                "source": "item-rod-of-security",
                "desc": "1 use, then 10-day cooldown (GM manual reset). Action: transport you + up to 199 willing creatures to an extraplanar paradise for up to 200 days ÷ travelers. Returns party to original location at the end. RAW DMG p.193.",
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
            # v2.159.28 Phase 2b — weight_lb. Kael STR 12 → 180 cap.
            {"name": "Quarterstaff", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "bludgeoning",
             "versatile": True, "properties": "versatile (1d8), monk weapon",
             "_slug": "quarterstaff", "weight_lb": 4},
            {"name": "10 darts", "type": "weapon", "qty": 10,
             "equippable": True, "equipped": False, "hands": 1,
             "damage": "1d4", "damage_type": "piercing",
             "range": "20/60 ft", "properties": "finesse, thrown, monk weapon",
             "_slug": "dart", "weight_lb": 0.25},
            {"name": "Explorer's pack", "type": "gear", "qty": 1,
             "weight_lb": 59,
             "desc": "Backpack, bedroll, mess kit, tinderbox, 10 torches, 10 days rations, waterskin, 50 ft hempen rope."},
            {"name": "Herbalism kit", "type": "gear", "qty": 1,
             "weight_lb": 3,
             "desc": "Hermit background — pouches, mortar + pestle, dried herbs."},
            {"name": "Scroll case with prayers", "type": "gear", "qty": 1,
             "desc": "Hermit background trinket — Kael's reflections from years in the wilderness."},
            # v2.355.0 — Rope of Entanglement (RAW DMG p.198, rare, NO
            # attunement). Promoted out of the v2.342.0 Vault bulk loot into
            # an explicit equipped item. Runs through the generalized Wand of
            # Fear handler with the restrained condition; the catalog flags
            # it `unlimited: True` so it needs NO charge resource (RAW: at-
            # will command word, limited only by the rope's own AC 20/20 HP,
            # GM-narrated). Thematic on Kael (a Monk who fights to restrain).
            {"name": "Rope of Entanglement", "type": "wondrous", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 3,
             "_slug": "rope-of-entanglement",
             "desc": "Rare wondrous item, no attunement. 30-ft rope. Action (command word): the rope darts to entangle a creature within 20 ft — DC 15 DEX save or restrained until you release it (bonus action). At-will (no charges); the rope has AC 20, 20 HP. RAW DMG p.198."},
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
            # v2.234.0 — Amulet of Proof against Detection (RAW DMG p.150,
            # uncommon, attunement). Kael's 2nd attuned item (after the
            # Bracers, RAW max 3). While worn he's hidden from divination
            # and magical scrying. The `scry_proof` flag rides the
            # `amulet-of-proof-against-detection` catalog payload and
            # surfaces on /sheet-json as derived.scry_proof — thematic on a
            # secluded, meditative Monk.
            {"name": "Amulet of Proof against Detection", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 0,
             "_slug": "amulet-of-proof-against-detection",
             "desc": "Uncommon wondrous item, attunement. While wearing it you are hidden from divination magic — you can't be targeted by such magic or perceived through magical scrying sensors. RAW DMG p.150."},
            # v2.238.0 — Winged Boots (RAW DMG p.214, uncommon, attunement).
            # Kael's 3rd attuned item (after Bracers + Amulet, RAW max 3).
            # While worn he has a flying speed equal to his walking speed (up
            # to 4 hours, GM-narrated). The `flying_speed` flag rides the
            # `winged-boots` catalog payload and surfaces on /sheet-json as
            # derived.flying_speed — on-theme for a fast, mobile Open Hand Monk.
            {"name": "Winged Boots", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 1,
             "_slug": "winged-boots",
             "desc": "Uncommon wondrous item, attunement. While you wear these boots, you have a flying speed equal to your walking speed. You can fly for up to 4 hours, all at once or in shorter flights. RAW DMG p.214."},
            # v2.260.0 — Ring of Jumping (RAW DMG p.191, uncommon, attunement).
            # Cast Jump on yourself at will as a bonus action (the tripled jump
            # distance is GM-narrated in v1). The `jump_at_will` flag rides the
            # `ring-of-jumping` catalog payload and surfaces on /sheet-json as
            # derived.jump_at_will. On-theme for Kael — his Step of the Wind Ki
            # option already doubles his jump distance, and the ring stacks
            # flavorfully. His free ring finger homes it; seed-load bypasses the
            # RAW 3-item cap (enforced at /attune runtime only), so it rides as
            # his 4th attuned item.
            {"name": "Ring of Jumping", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 0,
             "_slug": "ring-of-jumping",
             "desc": "Uncommon wondrous item, attunement. While wearing this ring, you can cast the jump spell from it as a bonus action at will, but can target only yourself when you do so. RAW DMG p.191. Surfaces as the derived jump_at_will flag."},
            # v2.330.0 — "The Engineer's Set" bundle: Apparatus of the Crab
            # (RAW DMG p.151, legendary, no attunement). 2-ft × 1-ft sealed
            # iron barrel; 5 lb. Touch a control rune to transform into a
            # 12-ft × 6-ft × 8-ft armored crab-walker (AC 20, 200 HP, swim
            # 30 ft, walking 30 ft, 11 levers operating waterproof seal,
            # claws, propulsion, light, and lift). Holds 2 medium creatures.
            # Pure GM-narrated mechanic; catalog stub. Thematic on Kael
            # (Wood Elf Monk — a mechanical contraption fits his
            # contemplative tinkering / hermit background, and the
            # ten-day-air-supply submersible is on-theme for a wandering
            # explorer).
            {"name": "Apparatus of the Crab", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 5,
             "_slug": "apparatus-of-the-crab",
             "desc": "Legendary wondrous item, no attunement. 5-lb sealed iron barrel (2 ft × 1 ft) that transforms via a rune-control surface into a 12 × 6 × 8-ft armored crab-walker submersible — AC 20, 200 HP, swim 30, walk 30, 11 levers for sealed propulsion / claws / lift / lights / hatch. Holds 2 medium creatures (10 days of air). RAW DMG p.151."},
            # v2.336.0 — "The Escapist's Kit" bundle: Wind Fan (RAW DMG
            # p.213, uncommon, no attunement). A woven-silk fan. Action:
            # cast Gust of Wind (save DC 13) from it. Once used, shouldn't
            # be used again until the next dawn; each extra use before then
            # has a cumulative 20% chance of tearing into useless tatters.
            # Stub catalog row; the cast + tatter-risk are GM-narrated.
            # Thematic on Kael (Wood Elf Monk — a wind-fan disengage tool
            # fits an acrobatic Open Hand monk who darts in and out).
            {"name": "Wind Fan", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 1,
             "_slug": "wind-fan",
             "desc": "Uncommon wondrous item, no attunement. A woven-silk fan. Action: cast Gust of Wind (save DC 13) from it. Once used, shouldn't be used again until the next dawn; each extra use before then has a cumulative 20% chance to tear the fan into useless nonmagical tatters. RAW DMG p.213."},
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
            # v2.403.5 — magic-items-automation Phase 9.2 batch 6:
            # Dust of Dryness (RAW DMG p.166) — 1d6+4 pinches (avg 7).
            # The dust is seeded INERT on Kael (vault loot at line
            # ~7222); the harness PATCHes equipped=True. `reset: "none"`
            # — the packet doesn't refill (it's a consumable container).
            {
                "key": "dust-of-dryness",
                "name": "Dust of Dryness",
                "current": 7, "max": 7, "reset": "none",
                "source": "item-dust-of-dryness",
                "desc": "7 pinches. Action: sprinkle one pinch over water — a cube of water up to 15 ft on a side becomes a marble-sized pellet. Shatter the pellet to release the water as a wave. The packet doesn't refill. RAW DMG p.166.",
                "manual": False,
            },
            # v2.403.6 — magic-items-automation Phase 9.2 Bucket A
            # holdout #1: Wind Fan (RAW DMG p.213). 1/dawn safe; each
            # subsequent same-day use rolls d100 vs cumulative-20%
            # tear-into-tatters. Resource shape: current=10, max=10,
            # reset=long — first use (current==max) is safe; later uses
            # roll vs (max-current_before)*20% chance to tear (item
            # destroyed). `_use_item_action_wind_fan` handler manages
            # the roll + destruction branch. The fan is seeded equipped
            # on Kael (line ~5648).
            {
                "key": "wind-fan",
                "name": "Wind Fan",
                "current": 10, "max": 10, "reset": "long",
                "source": "item-wind-fan",
                "desc": "Use #1/day: safe Gust of Wind (DC 13). Each subsequent same-day use: cumulative 20% chance per overuse to tear the fan into nonmagical tatters (1st overuse 20%, 2nd 40%, etc.). Counter resets at dawn. RAW DMG p.213.",
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
            # v2.159.28 Phase 2b — weight_lb. Zara STR 8 → 120 cap.
            {"name": "Dagger", "type": "weapon", "qty": 2,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d4", "damage_type": "piercing",
             "range": "20/60 ft", "properties": "finesse, light, thrown",
             "_slug": "dagger", "weight_lb": 1},
            {"name": "Component pouch", "type": "gear", "qty": 1,
             "weight_lb": 2,
             "desc": "Required spellcasting focus for spells with material components."},
            # v2.356.0 — Circlet of Blasting (RAW DMG p.159, uncommon, NO
            # attunement). Promoted out of the v2.342.0 Vault bulk loot into
            # an explicit equipped item paired with the `circlet-of-blasting`
            # 1/dawn resource above. Runs through the NEW spell-attack item
            # handler (Scorching Ray: 3 ranged spell attacks at +5, 2d6 fire
            # each). On-theme for a fire Sorcerer.
            {"name": "Circlet of Blasting", "type": "wondrous", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 0,
             "_slug": "circlet-of-blasting",
             "desc": "Uncommon wondrous item, no attunement. 1/dawn — action: cast scorching ray from it (3 ranged spell attacks at +5 to hit, 2d6 fire each on a hit). RAW DMG p.159."},
            # v2.357.0 — Ring of Shooting Stars (RAW DMG p.191, very rare,
            # attunement). Promoted out of the v2.342.0 Vault bulk loot into
            # an explicit equipped+attuned ring paired with the
            # `ring-of-shooting-stars` 6-charge resource above. The combat
            # "Shooting Stars" mode runs through the generalized save-for-
            # half Necklace handler (1-3 motes, DC 15 DEX, 5d4 fire each).
            # Seeded attuned (the /use_item_action path gates on `attuned`);
            # seed-load bypasses the RAW 3-item cap. On-theme for a Sorcerer.
            {"name": "Ring of Shooting Stars", "type": "wondrous", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 0,
             "_slug": "ring-of-shooting-stars",
             "desc": "Very rare ring, attunement (works outdoors at night, GM-narrated). 6 charges (regain all at dawn). Shooting Stars: expend 1-3 charges (action) to launch that many motes — each target makes a DC 15 DEX save, taking 5d4 fire (half on a save). Dancing-lights/light at will + ball-lightning mode GM-narrated. RAW DMG p.191."},
            {"name": "Dungeoneer's pack", "type": "gear", "qty": 1,
             "weight_lb": 61.5,
             "desc": "Backpack, crowbar, hammer, 10 pitons, 10 torches, tinderbox, 10 days rations, waterskin, 50 ft hempen rope."},
            {"name": "Marked deck of cards", "type": "gear", "qty": 1,
             "desc": "Charlatan background trinket — Zara's old grift kit. Cosmetic."},
            {"name": "Potion of Healing", "type": "consumable", "qty": 1,
             "consumable": True, "use_kind": "heal", "heal_dice": "2d4+2",
             "_slug": "potion-of-healing",
             "desc": "Drink to regain 2d4+2 HP. RAW: action."},
            # v2.208.0 — Eyes of Charming (RAW DMG p.168, uncommon,
            # attunement). 3 charges (regain all at dawn); expend 1 to
            # cast charm person at one humanoid within 30 ft (DC 13 WIS
            # save). Zara is a CHA face (Charlatan Sorcerer) with no
            # other attuned items, so this is a clean 1/3 attunement.
            {"name": "Eyes of Charming", "type": "wondrous", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "eyes-of-charming", "weight_lb": 0,
             "desc": "Uncommon wondrous item, attunement. Crystal lenses with 3 charges (regain all at dawn). Expend 1 (action) to cast charm person (DC 13) on a humanoid within 30 ft you can see."},
            # v2.210.0 — Staff of Fire (RAW DMG p.202, very rare,
            # attunement). 10 charges (regain 1d6+4 at dawn). Casts
            # burning hands (1), fireball (3), or wall of fire (4)
            # "using your spell save DC" (Zara's = 14). v1 surfaces the
            # marquee Fireball action (8d6 fire, 20-ft sphere, DEX save)
            # through the generalized save-for-half AoE handler. Zara
            # (Tiefling Sorcerer, fire-flavoured via Hellish Rebuke) is a
            # natural wielder — her 2nd attuned item, after the Eyes.
            {"name": "Staff of Fire", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "staff-of-fire", "weight_lb": 4,
             "desc": "Very rare staff, attunement. Resistance to fire while held. 10 charges (regain 1d6+4 at dawn): cast burning hands (1), fireball (3), or wall of fire (4) using your spell save DC."},
            # v2.215.0 — ability-score override Phase 2b: belt tier
            # backfill via per-item override. Belt of Stone Giant
            # Strength (STR 23, RAW DMG p.155, attunement). The SRD's
            # single `belt-of-giant-strength` slug defaults to the Hill
            # tier (STR 21) in _MAGIC_ITEM_PASSIVES; the `_ability_set`
            # field on THIS item overrides it to 23, proving the per-item
            # tier mechanism. Zara's base STR 8 (mod -1) becomes effective
            # 23 (mod +6) while worn — a dramatic 15-point swing, visible
            # on /sheet-json `derived.effective_abilities` + a carry jump
            # (120 → 345). Her 3rd attuned item (RAW max), after the Eyes
            # + Staff. See docs/plans/str-override.md.
            {"name": "Belt of Giant Strength (Stone)", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "belt-of-giant-strength", "_ability_set": {"STR": 23},
             "weight_lb": 0,
             "desc": "Very rare wondrous item, attunement. While worn, your Strength score becomes 23 (Stone/Frost giant) if it isn't already higher. RAW DMG p.155."},
            # v2.264.0 — charged-items Phase 1: Wand of Polymorph (RAW
            # DMG p.212, rare, attunement). 7 charges; expend 1 to cast
            # Polymorph (save DC 15) — RAW no upcast, so the catalog
            # fixes min == max == 1 at base slot 4 (the spell's own
            # level). Polymorph is on the Sorcerer list, so Zara is a
            # natural wielder. Her 4th attuned item (seed-load bypasses
            # the RAW 3-item cap, enforced at /attune runtime only).
            # Paired with the wand-of-polymorph resource row below.
            {"name": "Wand of Polymorph", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "wand-of-polymorph", "weight_lb": 1,
             "desc": "Rare wand, attunement. 7 charges. Expend 1 charge to cast Polymorph (save DC 15) — transform a creature into a beast for the duration (WIS save negates on unwilling targets). Regains 1d6+1 charges at dawn (long rest). RAW DMG p.212."},
            # v2.273.0 — charged-items Phase 4: Wand of Wonder (RAW DMG
            # p.213, rare, attunement by a spellcaster). 7 charges; expend
            # 1 to roll d100 on the chaos table (the first
            # action_kind: "random_table" item). A Sorcerer is the
            # perfect wielder — Zara's chaotic Draconic magic pairs with
            # the wand's wild-surge table. Her 5th attuned item (seed-load
            # bypasses the RAW 3-item cap, enforced at /attune runtime
            # only). Paired with the wand-of-wonder resource row below.
            {"name": "Wand of Wonder", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "wand-of-wonder", "weight_lb": 1,
             "desc": "Rare wand, attunement by a spellcaster. 7 charges. Expend 1 charge to roll d100 on the Wand of Wonder chaos table — the result is a random effect (a spell, a damage burst, a transformation, a summoned animal…) that the GM narrates/resolves. Regains 1d6+1 charges at dawn (long rest). RAW DMG p.213."},
            # v2.276.0 — charged-items Phase 5: Wand of the War Mage, +3
            # (RAW DMG p.211, very rare, attunement) — the top tier of the
            # spell-attack-bonus wand. A passive (no charges): while held it
            # grants +3 to spell attack rolls (and the wielder ignores half
            # cover on a spell attack — GM-narrated). The single SRD slug
            # defaults to +1 (uncommon) in _MAGIC_ITEM_PASSIVES; this item
            # rides the very-rare +3 tier via the per-item
            # `_spell_attack_bonus` override (mirrors the +2 wand on Magnus,
            # v2.265.0, and the Ioun Stone `_ability_bonus` tier pattern).
            # The +3 folds into Zara's Fire Bolt (and every spell attack)
            # to-hit at cast time. Zara (Draconic Sorcerer — a CHA blaster
            # with no other spell-attack item) is the natural wielder, so
            # her derived.spell_attack_bonus reads a clean +3. Her 6th
            # attuned item (seed-load bypasses the RAW 3-item cap, enforced
            # at /attune runtime only).
            {"name": "Wand of the War Mage, +3", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "wand-of-the-war-mage", "_spell_attack_bonus": 3,
             "weight_lb": 1,
             "desc": "Very rare wand, attunement. While holding this wand you gain a +3 bonus to spell attack rolls and ignore half cover when making a spell attack. RAW DMG p.211."},
            # v2.282.0 — Broom of Flying (RAW DMG p.156, uncommon, NO
            # attunement). Reuses the v2.238.0 Winged Boots flying-speed
            # substrate with zero new engine code: the `flying_speed` boolean
            # flag rides the `broom-of-flying` catalog payload, aggregates in
            # `_equipped_item_effects`, and surfaces on /sheet-json as
            # `derived.flying_speed`. Unlike the Wings/Winged Boots (both
            # attunement items), the broom needs NO attunement — its payload
            # omits `requires_attunement`, so it surfaces while merely
            # equipped. The command-word ride + 50-ft speed / 400-lb capacity
            # are GM-narrated in v1. Seeded as inert spare loot
            # (unequipped/unattuned) so it adds no flying speed to Zara's
            # baseline and disturbs no existing test — the harness PATCHes it
            # equipped (no attune needed), reads the derived flag, then
            # restores. A flying broom is on-theme for the demo's chaotic
            # Draconic Sorcerer.
            {"name": "Broom of Flying", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "_slug": "broom-of-flying", "weight_lb": 3,
             "desc": "Uncommon wondrous item, no attunement. Stand astride the broom and speak its command word to ride it in the air at a flying speed of 50 feet (30 feet while carrying over 200 lb; 400-lb max). It stops hovering when you land, and can be sent to or summoned from up to 1 mile away. RAW DMG p.156."},
            # v2.299.0 — Ring of Spell Turning (RAW DMG p.193, legendary,
            # attunement). Third carrier on the v2.297.0 `spell_save_advantage`
            # roll effect: "advantage on saving throws against any spell that
            # targets only you (not in an area of effect)." Spare loot
            # (equipped=False / attuned=False): Zara carries no other
            # spell-save-advantage item so her baseline cleanly proves the ring
            # is the source — the harness PATCHes it equipped+attuned, rolls a
            # vs_spell save and asserts the 2d20kh1 advantage + source, then
            # restores. The nat-20 spell-reflection clause is GM-narrated. A
            # legendary anti-magic ring is on-theme for a Draconic Sorcerer.
            {"name": "Ring of Spell Turning", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "_slug": "ring-of-spell-turning", "weight_lb": 0,
             "desc": "Legendary ring, attunement. While wearing this ring, you have advantage on saving throws against any spell that targets only you (not in an area of effect). If you roll a 20 for the save and the spell is 7th level or lower, the spell has no effect on you and instead targets the caster (GM-narrated). RAW DMG p.193."},
            # v2.330.0 — "The Engineer's Set" bundle: Cube of Force (RAW DMG
            # p.165, rare, attunement). 1-in. metal cube; bonus action to
            # speak one of six face-keyed command words to project an
            # invisible 5-ft cube barrier around yourself. Each command
            # selects which solid/incorporeal/spell categories the barrier
            # blocks; cube has 36 charges (1d6 spent per use), regaining
            # 1d20 at dawn. Stub catalog row; the per-face barrier modes
            # and energy-dispersal mechanic are GM-narrated. Thematic on
            # Zara (Tiefling Sorcerer — defensive arcane field for a
            # frail-frame blaster, and her first ATTUNEMENT-required stub
            # item).
            {"name": "Cube of Force", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True, "weight_lb": 1,
             "_slug": "cube-of-force",
             "desc": "Rare wondrous item, attunement. 1-in. metal cube. Bonus action: speak one of six face-keyed command words to project an invisible 5-ft cube barrier around yourself selectively blocking solids / incorporeals / spells / etc. 36 charges (regain 1d20 at dawn); each command spends a per-face cost. Energy-dispersal interactions are GM-narrated. RAW DMG p.165."},
            # v2.337.0 — "The Bottled Tempest" bundle: Efreeti Bottle (RAW DMG
            # p.167, very rare, no attunement). A brass bottle. Action: pull
            # the stopper — smoke pours out and (per a d100 roll) the efreeti
            # inside may attack, grant 3 wishes, or serve for 1 hour before
            # vanishing. Stub catalog row; the d100 release table + efreeti
            # service are GM-narrated. Thematic on Zara (Tiefling Draconic
            # Sorcerer — a fire-genie bottle pairs with her Red-Dragon-
            # ancestry fire aesthetic).
            {"name": "Efreeti Bottle", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 1,
             "_slug": "efreeti-bottle",
             "desc": "Very rare wondrous item, no attunement. A painted brass bottle (1 lb). Action: pull the stopper — a cloud of smoke flows out and, per a d100 roll, the efreeti within may attack you, grant 3 wishes, or serve you for 1 hour before disappearing. Once opened, can't be used again for 24 hours. RAW DMG p.167."},
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
            # v2.356.0 — Circlet of Blasting 1/dawn use (RAW DMG p.159): a
            # single "charge" that refills on a long rest. The spell-attack
            # item handler decrements it per Scorching Ray cast.
            {
                "key": "circlet-of-blasting",
                "name": "Circlet of Blasting",
                "current": 1, "max": 1, "reset": "long",
                "source": "magic item — Circlet of Blasting",
                "class_slug": "item",
                "desc": "1/dawn — action: cast scorching ray (3 ranged spell attacks at +5, 2d6 fire each). Recharges at dawn.",
                "manual": False,
            },
            # v2.357.0 — Ring of Shooting Stars charge pool (RAW DMG p.191):
            # 6 charges, regain all at dawn (long rest). The save-for-half
            # Necklace handler decrements N per Shooting Stars (N motes).
            {
                "key": "ring-of-shooting-stars",
                "name": "Ring of Shooting Stars",
                "current": 6, "max": 6, "reset": "long",
                "source": "magic item — Ring of Shooting Stars",
                "class_slug": "item",
                "desc": "6 charges (regain all at dawn). Shooting Stars: expend 1-3 (action) to launch that many motes — each target DC 15 DEX save or 5d4 fire (half on save).",
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
            # v2.403.1 — magic-items-automation Phase 9.2 batch 2:
            # Efreeti Bottle (RAW DMG p.167) — 1/dawn release. The bottle
            # is seeded equipped on Zara (line ~5920). The d100 release
            # table + efreeti service are GM-narrated; this resource row
            # backs the /use_item_action endpoint's charge decrement.
            {
                "key": "efreeti-bottle",
                "name": "Efreeti Bottle",
                "current": 1, "max": 1, "reset": "long",
                "source": "item-efreeti-bottle",
                "desc": "1/dawn. Action: pull the stopper — smoke pours out and (per a d100 roll) the efreeti within attacks, grants 3 wishes, or serves for 1 hour. RAW DMG p.167.",
                "manual": False,
            },
            # v2.403.2 — magic-items-automation Phase 9.2 batch 3:
            # Cube of Force (RAW DMG p.165) — 36 charges, regain 1d20
            # at dawn. The cube is seeded equipped+attuned on Zara
            # (line ~5908). v1 ships a generic "expend 1-5 charges"
            # action — the face choice + which category the barrier
            # blocks are GM-narrated. RAW per-face cost: 1 gas/fog,
            # 2 nonliving, 3 living, 4 spell effects, 5 nothing-passes.
            {
                "key": "cube-of-force",
                "name": "Cube of Force",
                "current": 36, "max": 36, "reset": "long",
                "charge_recovery": "1d20",
                "source": "item-cube-of-force",
                "desc": "36 charges; bonus action to press a face + expend 1-5 charges (per face) to project a 15-ft force barrier. Regain 1d20 at dawn. RAW DMG p.165.",
                "manual": False,
            },
            # v2.403.3 — magic-items-automation Phase 9.2 batch 4:
            # Ring of Djinni Summoning (RAW DMG p.190) — 1/24 hours.
            # The ring is seeded INERT on Zara (vault loot at line
            # ~7178); the harness PATCHes equipped+attuned. `reset:
            # "none"` — GM manual reset when 24-h cooldown elapses.
            {
                "key": "ring-of-djinni-summoning",
                "name": "Ring of Djinni Summoning",
                "current": 1, "max": 1, "reset": "none",
                "source": "item-ring-of-djinni-summoning",
                "desc": "1 use, then 24-h cooldown (GM manual reset). Action: summon the bound djinni within 120 ft — friendly + obeys commands for up to 1 hour (concentration). RAW DMG p.190.",
                "manual": False,
            },
            # v2.208.0 — Eyes of Charming charge pool (RAW DMG p.168):
            # 3 charges, regain all at dawn (full refill on long rest).
            # Decremented by the generalized save-condition handler when
            # Zara casts charm person from the lenses.
            {
                "key": "eyes-of-charming",
                "name": "Eyes of Charming",
                "current": 3, "max": 3, "reset": "long",
                "source": "magic item — Eyes of Charming",
                "class_slug": "item",
                "desc": "3 charges; expend 1 to cast charm person (DC 13) on a humanoid within 30 ft. Regain all at dawn.",
                "manual": False,
            },
            # v2.210.0 — Staff of Fire charge pool (RAW DMG p.202): 10
            # charges, regain 1d6+4 at dawn (full refill on long rest in
            # v1). The generalized AoE-damage handler decrements 3 per
            # Fireball cast.
            {
                "key": "staff-of-fire",
                "name": "Staff of Fire",
                "current": 10, "max": 10, "reset": "long",
                "source": "magic item — Staff of Fire",
                "class_slug": "item",
                "desc": "10 charges; Fireball costs 3 (8d6 fire, 20-ft sphere, DEX save at your spell save DC). Regain 1d6+4 at dawn.",
                "manual": False,
            },
            # v2.264.0 — charged-items Phase 1: Wand of Polymorph charge
            # counter. Same 7-charge / 1d6+1 recharge shape as the Web
            # wand; the spell + base slot live in the catalog (Polymorph
            # + base 4, fixed single-charge spend). Paired with the Wand
            # of Polymorph entry in Zara's inventory above.
            {
                "key": "wand-of-polymorph",
                "name": "Wand of Polymorph",
                "current": 7, "max": 7, "reset": "long",
                "charge_recovery": "1d6+1",
                "source": "item-wand-of-polymorph",
                "desc": "7 charges. Spend 1 to cast Polymorph (DC 15) at slot level 4. Regains 1d6+1 charges on long rest.",
                "manual": False,
            },
            # v2.273.0 — charged-items Phase 4: Wand of Wonder charge
            # counter. 7 charges, 1d6+1 recharge at dawn. The random-table
            # handler decrements 1 per d100 roll. Paired with the Wand of
            # Wonder entry in Zara's inventory above.
            {
                "key": "wand-of-wonder",
                "name": "Wand of Wonder",
                "current": 7, "max": 7, "reset": "long",
                "charge_recovery": "1d6+1",
                "source": "item-wand-of-wonder",
                "desc": "7 charges. Spend 1 to roll d100 on the Wand of Wonder chaos table — a random wild-magic effect. Regains 1d6+1 charges on long rest.",
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
            # v2.251.0 — Magic-items: Frost Brand (RAW DMG p.171, very
            # rare, attunement). Second weapon-rider on Garrik (the
            # weapon-rider showcase Fighter), pairing the fire-themed
            # Flame Tongue with a cold-themed sword. The ``_slug`` gate
            # matches the equipped+attuned inventory Frost Brand below to
            # fire the unconditional +1d6 cold uplift at /attack time.
            # While held it also grants resistance to fire damage (the
            # passive half rides _MAGIC_ITEM_PASSIVES["frost-brand"]).
            {"name": "Frost Brand Longsword", "attack_bonus": "+8",
             "damage": "1d8+4", "damage_type": "slashing",
             "range": "5 ft", "_slug": "frost-brand",
             "desc": "Very rare longsword, attunement. 1d8+4 slashing + 1d6 cold on every hit (always-on while attuned). Grants resistance to fire damage while held."},
        ],
        # Fighter is non-casting RAW (Champion subclass doesn't grant
        # spells either). No spells / spell_slots fields needed.
        "inventory": [
            # v2.159.28 Phase 2b — weight_lb. Garrik STR 18 → 270 cap.
            {"name": "Greatsword", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "hands": 2,
             "damage": "2d6", "damage_type": "slashing",
             "properties": "heavy, two-handed", "_slug": "greatsword",
             "weight_lb": 6},
            {"name": "Handaxe", "type": "weapon", "qty": 2,
             "equippable": True, "equipped": True, "hands": 1,
             "damage": "1d6", "damage_type": "slashing",
             "range": "20/60 ft", "properties": "light, thrown",
             "_slug": "handaxe", "weight_lb": 2},
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
             "_slug": "glaive", "weight_lb": 6},
            # v2.250.0 — Mariner's Armor (RAW DMG p.181, uncommon, NO
            # attunement): a heavy (chain-mail-base, AC 16) variant. Grants a
            # swimming speed equal to walking speed + rise-to-surface at 0 HP
            # underwater (the latter GM-narrated in v1). Replaces Garrik's
            # mundane chain mail in place — same AC 16, same 55 lb, so AC,
            # carry weight, and the test_weapon_bond index-3 "non-weapon →
            # 400" path are all unchanged; it just adds the `swim_speed`
            # passive on /sheet-json derived. No attunement, so it costs Garrik
            # no slot (he's already at 3/3: Flame Tongue + Wand of Lightning
            # Bolts + Belt of Giant Strength).
            {"name": "Mariner's Armor", "type": "armor", "qty": 1,
             "equippable": True, "equipped": True,
             "armor_type": "heavy", "ac_value": 16,
             "_slug": "mariners-armor", "weight_lb": 55,
             "desc": "Uncommon armor (heavy, chain-mail base), no attunement. While wearing it you have a swimming speed equal to your walking speed; if you start your turn underwater with 0 HP, the armor rises you 60 ft toward the surface each round. RAW DMG p.181."},
            {"name": "Explorer's pack", "type": "gear", "qty": 1,
             "weight_lb": 59,
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
            # v2.251.0 — Frost Brand Longsword (RAW DMG p.171, very rare,
            # attunement). Pair-bound with the attack entry above via the
            # ``_slug``. The cold rider fires only when (a) the attack
            # carries _slug="frost-brand", AND (b) this item is equipped +
            # attuned (the double-gate). Detuning via /attune suppresses
            # BOTH the +1d6 cold rider AND the passive fire resistance,
            # leaving a mundane longsword. Unlike Flame Tongue there's no
            # _lit toggle — RAW Frost Brand's cold is always live while
            # attuned. Seeded as an additional attuned item on Garrik (the
            # seed predates strict cap enforcement, which lives only on the
            # /attune runtime endpoint, not at seed-load or in the passive
            # walker).
            {"name": "Frost Brand Longsword", "type": "weapon", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "hands": 1, "damage": "1d8", "damage_type": "slashing",
             "properties": "versatile (1d10), magic",
             "_slug": "frost-brand",
             "desc": "Very rare longsword, attunement. +1d6 cold on every hit while attuned; grants resistance to fire damage while held. Sheds light + extinguishes nonmagical flames (GM-narrated). RAW DMG p.171."},
            # v2.184.0 — Magic-items: first "self-buff" consumable.
            # Potion of Heroism (RAW DMG p.187, rare). Drink (action,
            # /use_item_action drink) → 10 temp HP + the Bless effect
            # (no concentration) for 1 hour, then the potion is
            # consumed. Thematic on Garrik (front-line Fighter).
            {"name": "Potion of Heroism", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-heroism",
             "desc": "Drink (action, /use_item_action drink) to gain 10 temporary hit points and the effect of Bless (no concentration) for 1 hour. RAW DMG p.187."},
            # v2.185.0 — second self-buff potion. Potion of Speed (RAW
            # DMG p.187, very rare). Drink → the Haste effect (+2 AC,
            # ×2 speed, extra action, Dex-save advantage) for 1 minute,
            # no concentration.
            {"name": "Potion of Speed", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-speed",
             "desc": "Drink (action, /use_item_action drink) to gain the effect of Haste (no concentration) for 1 minute. RAW DMG p.187."},
            # v2.186.0 / v2.187.0 — third self-buff potion. Potion of
            # Resistance (RAW DMG p.188, uncommon): drink → resistance to one
            # damage type (live damage-pipeline halving) for 1 hour, no
            # concentration. RAW the GM picks the type, so the item carries a
            # `resistance_type` that the handler maps to the matching template.
            # Garrik carries the fire + cold instances to prove the type-pick.
            # First self-buff with a mechanically enforced effect (vs.
            # Heroism/Speed's marker buffs).
            {"name": "Potion of Fire Resistance", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-resistance", "resistance_type": "fire",
             "desc": "Drink (action, /use_item_action drink) to gain resistance to fire damage (no concentration) for 1 hour. RAW DMG p.188."},
            {"name": "Potion of Cold Resistance", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-resistance", "resistance_type": "cold",
             "desc": "Drink (action, /use_item_action drink) to gain resistance to cold damage (no concentration) for 1 hour. RAW DMG p.188."},
            # v2.188.0 — a GENERIC (untyped) Potion of Resistance: RAW the
            # drinker picks the damage type, so this carries no
            # `resistance_type`. The drinker supplies one at drink-time via
            # the `/use_item_action` body's `resistance_type` override.
            {"name": "Potion of Resistance", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-resistance",
             "desc": "Drink (action, /use_item_action drink) to gain resistance to one damage type you choose (no concentration) for 1 hour. RAW DMG p.188."},
            # v2.190.0 — fourth self-buff potion. Potion of Invulnerability
            # (RAW DMG p.188, rare): drink → resistance to ALL damage (live
            # damage-pipeline halving via the "all" wildcard) for 1 minute,
            # no concentration.
            {"name": "Potion of Invulnerability", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-invulnerability",
             "desc": "Drink (action, /use_item_action drink) to gain resistance to all damage (no concentration) for 1 minute. RAW DMG p.188."},
            # v2.192.0 — fifth self-buff potion. Potion of Growth (RAW
            # DMG p.187, uncommon): drink → the enlarge effect (advantage
            # on STR checks/saves, +1d4 weapon damage, size Large) for up
            # to 1d4 hours, no concentration. The advantage half is
            # mechanical via the generalized STR-advantage readers.
            {"name": "Potion of Growth", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-growth",
             "desc": "Drink (action, /use_item_action drink) to gain the enlarge effect (advantage on STR checks/saves; no concentration) for up to 1d4 hours. RAW DMG p.187."},
            # v2.193.0 — first offensive consumable. Drinking exhales fire at
            # the area (4d6 fire, DC 13 DEX save for half) and consumes the
            # potion. Reuses the Necklace of Fireballs per-target save loop.
            {"name": "Potion of Fire Breath", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-fire-breath",
             "desc": "Drink + exhale fire (bonus action, /use_item_action breathe) at the area: each target makes a DC 13 DEX save, 4d6 fire, half on a success. Consumes the potion. RAW DMG p.187."},
            # v2.195.0 — sixth self-buff potion. Potion of Climbing (RAW
            # DMG p.187, common): drink → a climbing speed + advantage on
            # STR (Athletics) checks to climb for 1 hour. The advantage
            # half is mechanical via the generalized STR-check reader; the
            # climb speed is GM-narrated.
            {"name": "Potion of Climbing", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-climbing",
             "desc": "Drink (action, /use_item_action drink) to gain a climbing speed + advantage on STR (Athletics) checks to climb for 1 hour. RAW DMG p.187."},
            # v2.196.0 — seventh self-buff potion. Potion of Water Breathing
            # (RAW DMG p.188, uncommon): drink → breathe underwater for 1
            # hour. Purely descriptive (the engine tracks no drowning rule),
            # so the buff is GM-narrated.
            {"name": "Potion of Water Breathing", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-water-breathing",
             "desc": "Drink (action, /use_item_action drink) to breathe underwater for 1 hour. RAW DMG p.188."},
            # v2.197.0 — second save-imposing consumable. Drinking probes a
            # creature's mind (DC 13 WIS save; on a failure you read its
            # surface thoughts) and consumes the potion. No damage — the
            # thought-reading is GM-narrated. Reuses the Fire Breath save loop.
            {"name": "Potion of Mind Reading", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-mind-reading",
             "desc": "Drink + probe a mind (action, /use_item_action read): the target makes a DC 13 WIS save; on a failure you read its surface thoughts. Consumes the potion. RAW DMG p.187."},
            # v2.199.0 — eighth self-buff potion, first DEbuff one. Potion of
            # Diminution (RAW DMG p.187, rare): drink → the reduce effect for
            # up to 1d4 hours (disadvantage on STR checks/saves; size one
            # smaller; -1d4 weapon damage). The STR-check disadvantage half is
            # mechanical via the v2.199.0 intercept; the rest is GM-narrated.
            {"name": "Potion of Diminution", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-diminution",
             "desc": "Drink (action, /use_item_action drink) to gain the reduce effect: disadvantage on STR checks/saves, size one smaller, -1d4 weapon damage, for up to 1d4 hours. RAW DMG p.187."},
            {"name": "Potion of Invisibility", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-invisibility",
             "desc": "Drink (action, /use_item_action drink) to become invisible for 1 hour or until you attack or cast a spell. An invisible attacker has advantage on attacks. RAW DMG p.188."},
            {"name": "Potion of Flying", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-flying",
             "desc": "Drink (action, /use_item_action drink) to gain a flying speed equal to your walking speed for 1 hour. You fall if still aloft when it ends. RAW DMG p.187."},
            {"name": "Potion of Animal Friendship", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-animal-friendship",
             "desc": "Drink (action, /use_item_action charm) to charm one beast within 10 ft (DC 13 WIS save) — cast animal friendship at will for 1 hour. RAW DMG p.187."},
            {"name": "Potion of Clairvoyance", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-clairvoyance",
             "desc": "Drink (action, /use_item_action drink) to cast clairvoyance — a scrying sensor (sight or sound) at a chosen spot for 10 minutes. RAW DMG p.187."},
            {"name": "Potion of Gaseous Form", "type": "consumable", "qty": 1,
             "consumable": True, "equipped": True,
             "_slug": "potion-of-gaseous-form",
             "desc": "Drink (action, /use_item_action drink) to enter gaseous form for up to 1 hour: resistance to nonmagical damage, advantage on STR/DEX/CON saves, 10-ft hover; can't attack or cast. RAW DMG p.187."},
            # Manual of Gainful Exercise (RAW DMG p.176, very rare, no
            # attunement): study 48 hours over 6 days → your STR score increases
            # by 2, as does its maximum, then the manual loses its magic for a
            # century. v2.314.0 (reconciliation Phase 3) re-seated this onto the
            # canonical `permanent_boost` path: read via /use_item_action's
            # `read` action → _use_item_action_permanent_boost WRITES the stored
            # STR (18 → 20) and consumes the book. Every read site
            # (effective_ability_score, /roll STR saves + Athletics, carry
            # capacity) picks it up; because the manual also raises the maximum,
            # the +2 applies unconditionally (no RAW-20 clamp). Seeded on Garrik
            # (Fighter): his equipped Belt of Giant Strength still overrides
            # effective STR to 21 (max(20,21)), proving the stored write is
            # independent of the equipped override.
            {"name": "Manual of Gainful Exercise", "type": "magic", "qty": 1,
             "consumable": True, "weight_lb": 5,
             "_slug": "manual-of-gainful-exercise",
             "desc": "Very rare wondrous item. Studying it for 48 hours over 6 days permanently increases your Strength score by 2 (and its maximum). The manual then loses its magic for a century. RAW DMG p.176."},
            # Manual of Bodily Health (RAW DMG p.176, very rare, no attunement):
            # study 48 hours over 6 days → CON +2, its maximum +2 too. Same
            # `permanent_boost` `read` path as the Gainful Exercise manual; the
            # CON branch in _use_item_action_permanent_boost ALSO recomputes max
            # HP — a CON-modifier bump raises max HP by 1 per level (RAW PHB
            # p.173, ported in v2.312.0). Seeded on Garrik (Fighter): stored CON
            # +2, and his max + current HP gain by mod_delta × level on read.
            {"name": "Manual of Bodily Health", "type": "magic", "qty": 1,
             "consumable": True, "weight_lb": 5,
             "_slug": "manual-of-bodily-health",
             "desc": "Very rare wondrous item. Studying it for 48 hours over 6 days permanently increases your Constitution score by 2 (and its maximum); your hit point maximum increases retroactively. The manual then loses its magic for a century. RAW DMG p.176."},
            # Manual of Quickness of Action (RAW DMG p.176, very rare, no
            # attunement): study 48 hours over 6 days → DEX +2, its maximum +2
            # too. Same `permanent_boost` `read` path — no DEX-specific branch
            # needed: every DEX-derived read (AC, initiative, DEX saves,
            # Stealth/Acrobatics) flows from the stored score via
            # effective_ability_score, so the one-time write propagates
            # automatically. Completes the three physical-ability manuals on
            # Garrik (STR/CON/DEX).
            {"name": "Manual of Quickness of Action", "type": "magic", "qty": 1,
             "consumable": True, "weight_lb": 5,
             "_slug": "manual-of-quickness-of-action",
             "desc": "Very rare wondrous item. Studying it for 48 hours over 6 days permanently increases your Dexterity score by 2 (and its maximum). The manual then loses its magic for a century. RAW DMG p.176."},
            # v2.205.0 — third charge-tracked wand (RAW DMG p.213, rare,
            # attunement). Same template as the Wand of Fireballs (7
            # charges, base slot level 3, 1d6+1 recharge) but casts
            # Lightning Bolt (a 100-ft line) instead of Fireball.
            # Seeded on Garrik (not Thalindra) because she's already at
            # the RAW 3-item attunement cap (Cloak + Pearl + Fireballs
            # wand); Garrik attunes nothing else, so this is his first
            # attuned item. RAW-legal: wands carry no class restriction.
            {"name": "Wand of Lightning Bolts", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "wand-of-lightning-bolts",
             "desc": "Rare wand, attunement. 7 charges. Expend N (1-7) charges to cast Lightning Bolt (DC 15) at slot level 3+(N-1). Regains 1d6+1 charges at dawn (long rest)."},
            # v2.209.0 — first passive ability-check item. Stone of Good
            # Luck (Luckstone, RAW DMG p.207, uncommon, attunement):
            # while carried, +1 to ability checks AND saving throws. The
            # save half rides the existing v2.158.74 save substrate; the
            # check half rides the new v2.209.0 ability-check read site.
            # Seeded on Garrik (his 2nd attuned item, after the Wand) —
            # STR-proficient saves + Athletics skill make both halves
            # easy to assert in the harness.
            {"name": "Stone of Good Luck", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "stone-of-good-luck-luckstone",
             "desc": "Uncommon wondrous item, attunement. While on your person you gain +1 to ability checks and saving throws. RAW DMG p.207."},
            # v2.212.0 — ability-score override Phase 1. Belt of Giant
            # Strength (Hill, STR 21, RAW DMG p.155, attunement). Garrik's
            # base STR 18 (mod +4) becomes effective 21 (mod +5) while
            # worn — visible on /sheet-json `derived.effective_abilities`
            # + a +45 lb carry-capacity jump (270 → 315). The override
            # delta also rides STR saves + Athletics checks in /roll. His
            # 3rd attuned item (the RAW max). See docs/plans/str-override.md.
            {"name": "Belt of Giant Strength (Hill)", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "belt-of-giant-strength", "weight_lb": 0,
             "desc": "Rare wondrous item, attunement. While worn, your Strength score becomes 21 (Hill giant) if it isn't already higher. RAW DMG p.155."},
            # v2.278.0 — ability-score override drop-in tail. The two
            # remaining DISTINCT giant-belt tiers (Fire STR 25, Cloud STR
            # 27) complete the RAW DMG p.155 table (Hill 21 ✅ above,
            # Stone/Frost 23 ✅ Zara, Storm 29 ✅ Brakka). They ride the
            # same single `belt-of-giant-strength` slug via the per-item
            # `_ability_set` override (the v2.215.0 tier mechanism). Shipped
            # UNEQUIPPED/UNATTUNED as spare loot in Garrik's pack so they
            # add zero effective-STR change to any PC (only equipped+attuned
            # items aggregate in `_equipped_item_effects`) — his worn Hill
            # belt keeps winning. The harness test PATCHes each equipped to
            # verify the 25/27 override resolves, then restores.
            {"name": "Belt of Giant Strength (Fire)", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "_slug": "belt-of-giant-strength", "_ability_set": {"STR": 25},
             "weight_lb": 0,
             "desc": "Very rare wondrous item, attunement. While worn, your Strength score becomes 25 (Fire giant) if it isn't already higher. RAW DMG p.155."},
            {"name": "Belt of Giant Strength (Cloud)", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "_slug": "belt-of-giant-strength", "_ability_set": {"STR": 27},
             "weight_lb": 0,
             "desc": "Legendary wondrous item, attunement. While worn, your Strength score becomes 27 (Cloud giant) if it isn't already higher. RAW DMG p.155."},
            # v2.279.0 — Dragon Scale Mail (Blue, RAW DMG p.165, very rare,
            # attunement). The resisted type is dragon-color-keyed — Blue →
            # lightning — riding the `_resistance_type` rider (the Ring-of-
            # Resistance shared-slug pattern). Blue (not Red/fire) deliberately:
            # Garrik already carries a Frost Brand Longsword that grants FIRE
            # resistance, so a lightning type keeps the harness assertion clean.
            # Spare loot: equipped=False / attuned=False so it adds zero
            # resistance to Garrik's baseline (only equipped+attuned items
            # aggregate) and leaves his belt/luckstone tests untouched. The
            # harness test PATCHes it equipped+attuned, reads the lightning
            # `derived.resistances`, then restores. The +1 AC half is
            # descriptive in v1 (armor AC isn't surfaced on /sheet-json yet).
            {"name": "Dragon Scale Mail (Blue)", "type": "armor", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "_slug": "dragon-scale-mail", "_resistance_type": "lightning",
             "ac_value": 14, "weight_lb": 45,
             "desc": "Very rare armor (scale mail), attunement. +1 AC; resistance to lightning damage (Blue dragon scales); advantage on saves vs. dragon Frightful Presence and breath weapons. RAW DMG p.165."},
            # v2.288.0 — Periapt of Proof against Poison (RAW DMG p.184, rare,
            # NO attunement). First item on the v2.288.0 item-passive IMMUNITY
            # substrate: poison damage immunity (`_immunity_zero`) + poisoned-
            # condition immunity (`_target_condition_immune`), both surfaced on
            # /sheet-json (derived.immunities / condition_immunities). Spare
            # loot (equipped=False) — Garrik has no poison-immunity baseline, so
            # the harness test PATCHes it equipped, reads the derived
            # projections, then restores. A poison-warding brooch fits a
            # frontliner who soaks dragon breath and inhaled toxins.
            {"name": "Periapt of Proof against Poison", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "_slug": "periapt-of-proof-against-poison", "weight_lb": 0,
             "desc": "Rare wondrous item (no attunement). While worn, poisons have no effect on you: you are immune to the poisoned condition and have immunity to poison damage. RAW DMG p.184."},
            # v2.290.0 — Armor of Invulnerability (RAW DMG p.152, legendary,
            # attunement). Rides the v2.235.0 item-passive resistance substrate:
            # the `armor-of-invulnerability` passive folds a full
            # `nonmagical-<type>` resistance list, so `_resistance_halve` halves
            # any nonmagical hit while passing magical-source damage at full
            # (derived.resistances). The 10-min total-immunity action is GM-
            # narrated in v1. Spare loot (equipped=False) so it doesn't override
            # Garrik's Dragon Scale Mail AC or add baseline resistance — the
            # harness PATCHes it equipped+attuned, reads the projection + deals
            # nonmagical damage, then restores. A legendary plate fits the demo's
            # frontline Fighter.
            {"name": "Armor of Invulnerability", "type": "armor", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "_slug": "armor-of-invulnerability", "weight_lb": 65,
             "desc": "Legendary armor (plate), attunement. You have resistance to nonmagical damage while you wear this armor. Additionally, you can use an action to make yourself immune to nonmagical damage for 10 minutes or until you are no longer wearing the armor; once used, it can't be used again until the next dawn. RAW DMG p.152."},
            # v2.258.0 — Necklace of Adaptation (RAW DMG p.183, uncommon,
            # attunement). The wearer can breathe normally in any environment
            # + has advantage on saves vs. harmful gases and vapors. Modeled
            # as an attunement-gated boolean derived read (env_adaptation
            # flag); the gas-save advantage is GM-narrated in v1. Seeded on
            # Garrik (Fighter) — a frontliner who eats dragon breath weapons
            # and inhaled poisons fits the gas-resistance flavor. Rides his
            # free neck slot; seed-load bypasses the RAW 3-item cap (enforced
            # at /attune runtime only).
            {"name": "Necklace of Adaptation", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "necklace-of-adaptation", "weight_lb": 0,
             "desc": "RAW DMG p.183 (uncommon, attunement). While worn, you can breathe normally in any environment, and you have advantage on saving throws made against harmful gases and vapors (cloudkill, stinking cloud, inhaled poisons, some dragon breath). Surfaces as the derived env_adaptation flag."},
            # v2.269.0 — charged-items Phase 3: Ring of the Ram (RAW DMG
            # p.193, rare, attunement). The FIRST non-spell charge action
            # — the `ram-strike` action routes through the new
            # `action_kind: "attack"` handler (1d20+7 vs AC, 2d10 force
            # per charge) instead of a spell cast. Thematic on Garrik (a
            # front-line Fighter who shoves enemies). Paired with the
            # ring-of-the-ram resource row below. Seed-load bypasses the
            # RAW 3-item attunement cap (enforced at /attune runtime only).
            {"name": "Ring of the Ram", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "attuned": True,
             "_slug": "ring-of-the-ram", "weight_lb": 0,
             "desc": "Rare ring, attunement. 3 charges. Spend 1-3 charges to make a ranged force attack (+7 to hit, 2d10 force per charge) against a creature within 60 ft; on a hit you can shove it 5 ft per charge. Regains 1d3 charges at dawn (long rest). RAW DMG p.193."},
            # v2.296.0 — Rod of Alertness (RAW DMG p.193, very rare,
            # attunement). RAW "Alertness" property: while holding the rod you
            # have advantage on Wisdom (Perception) checks and on initiative
            # rolls. The Perception-check advantage rides the v2.253.0
            # `check_advantage_on` substrate (keyed on the perception skill,
            # attunement-gated) exactly like Robe of Eyes / Eyes of the Eagle:
            # `_roll_item_check_advantage` folds a 2d20kh1 advantage source
            # into the /roll composition and `/sheet-json` surfaces it as
            # derived.check_advantage_on. The initiative-roll advantage, the
            # four detect/see-invisibility spells, and the planted protective
            # aura (+1 AC/saves, sense invisibles) are GM-narrated in v1.
            # Seeded as inert spare loot (unequipped/unattuned) so it adds no
            # flag to Garrik's baseline (he carries no other perception-
            # advantage item) — the harness PATCHes it equipped+attuned, rolls
            # a Perception check, then restores. A watchful rod befits a Lv 9
            # soldier on the front line.
            {"name": "Rod of Alertness", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False, "weight_lb": 2,
             "_slug": "rod-of-alertness",
             "desc": "Very rare rod, attunement. While holding the rod you have advantage on Wisdom (Perception) checks and on initiative rolls; you can cast detect evil and good, detect magic, detect poison and disease, or see invisibility from it; and you can plant it to create a 60-ft bright-light protective aura (+1 AC and saving throws, sense invisible foes) for 10 min. RAW DMG p.193."},
            # v2.302.0 — Dwarven Plate (RAW DMG p.150, very rare, NO
            # attunement). "While wearing this armor, you gain a +2 bonus
            # to AC." Rides the same `ac_bonus` substrate the Elven Chain
            # (v2.301.0) and Cloak/Ring of Protection feed into
            # `_read_target_ac` — an equipped Dwarven Plate reads as
            # target_ac = base + 2 at attack hit-determination time, with
            # zero new engine code. No attunement (the payload omits
            # `requires_attunement`). The reaction "reduce forced movement
            # by 10 ft" clause is GM-narrated in v1. Seeded inert
            # (unequipped) so it adds nothing to Garrik's baseline AC and
            # disturbs no existing test — the harness PATCHes it equipped,
            # reads the +2 target_ac delta, then restores. Dwarf-forged
            # plate fits the demo's heavy-armor frontline Fighter.
            {"name": "Dwarven Plate", "type": "armor", "qty": 1,
             "equippable": True, "equipped": False, "attuned": False,
             "armor_type": "heavy", "ac_value": 18,
             "_slug": "dwarven-plate", "weight_lb": 65,
             "desc": "Very rare heavy armor (plate), no attunement. While wearing this armor, you gain a +2 bonus to AC. In addition, if an effect moves you against your will along the ground, you can use your reaction to reduce the distance you are moved by up to 10 feet. RAW DMG p.150."},
            # v2.327.0 — "The Wayfarer's Trio" bundle: Folding Boat (RAW DMG
            # p.170, rare, no attunement). Wooden box (12×6×6 in., 4 lb)
            # that unfolds into a 10-ft boat (action) or 24-ft ship (action)
            # via spoken command words. Pure GM-narrated mechanic — the
            # catalog row is a stub passive so the slug counts in the
            # audit; the actual boat/ship state lives in the GM's narration.
            # Thematic on Garrik (Fighter, Soldier background — a soldier
            # who packs an emergency boat for river crossings is on theme).
            {"name": "Folding Boat", "type": "magic", "qty": 1,
             "equippable": True, "equipped": False, "weight_lb": 4,
             "_slug": "folding-boat",
             "desc": "Rare wondrous item, no attunement. A 12×6×6 in., 4-lb wooden box that unfolds via three command words into either a 10-ft boat (4 medium creatures) or a 24-ft ship (15 medium creatures), or folds back into the box. Vessel weight + contents are GM-narrated. RAW DMG p.170."},
            # v2.328.0 — "The Inventor's Trio" bundle: Sovereign Glue (RAW
            # DMG p.200, legendary, no attunement). 1-oz milky-white adhesive
            # (stored in oil-of-slipperiness-coated flask) that forms a
            # permanent bond between any two objects in contact for 1
            # minute. Catalog stub passive — the bond mechanic + the
            # Universal Solvent counter-interaction is GM-narrated.
            # Thematic on Garrik (Fighter, Soldier — improvised field
            # repair adhesive fits his frontline kit).
            {"name": "Sovereign Glue", "type": "magic", "qty": 1,
             "equippable": True, "equipped": True, "weight_lb": 1,
             "_slug": "sovereign-glue",
             "desc": "Legendary wondrous item, no attunement. 1 oz of milky-white adhesive in a glass flask. Application bonds any two surfaces within 1 round permanently — only Universal Solvent or oil of etherealness can release the bond. RAW DMG p.200."},
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
            # v2.205.0 — Wand of Lightning Bolts charge counter. Same
            # shape as the Fireballs wand (7 charges, 1d6+1 recharge);
            # the spell + base slot level live in the catalog. Paired
            # with the Wand of Lightning Bolts entry in Garrik's
            # inventory above.
            {
                "key": "wand-of-lightning-bolts",
                "name": "Wand of Lightning Bolts",
                "current": 7, "max": 7, "reset": "long",
                "charge_recovery": "1d6+1",
                "source": "item-wand-of-lightning-bolts",
                "desc": "7 charges. Spend 1-7 to cast Lightning Bolt at slot level 3+(N-1). Regains 1d6+1 charges on long rest.",
                "manual": False,
            },
            # v2.269.0 — charged-items Phase 3: Ring of the Ram charge
            # counter. 3 starting charges, regains 1d3 at dawn (long rest)
            # via the Phase 4b dice-expression recharge path. The ram-strike
            # action spends 1-3 from this resource. Paired with the Ring of
            # the Ram entry in Garrik's inventory above.
            {
                "key": "ring-of-the-ram",
                "name": "Ring of the Ram",
                "current": 3, "max": 3, "reset": "long",
                "charge_recovery": "1d3",
                "source": "item-ring-of-the-ram",
                "desc": "3 charges. Spend 1-3 to make a ranged force attack (+7 to hit, 2d10 force per charge). Regains 1d3 charges on long rest.",
                "manual": False,
            },
            # v2.403.5 — magic-items-automation Phase 9.2 batch 6:
            # Sovereign Glue (RAW DMG p.200) — 1d6+1 ounces (avg 4).
            # The flask is seeded equipped on Garrik (line ~6868).
            # `reset: "none"` — the flask doesn't refill (consumable).
            {
                "key": "sovereign-glue",
                "name": "Sovereign Glue",
                "current": 4, "max": 4, "reset": "none",
                "source": "item-sovereign-glue",
                "desc": "4 ounces. Action: apply one ounce to a surface — bonds any two objects in contact permanently (1-round set time). Only universal solvent or oil of etherealness releases the bond. Flask doesn't refill. RAW DMG p.200.",
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
        portrait_url="/static/demo/tokens/rogue.jpg",
    )
    bob_pc = Character(
        campaign_id=camp.id,
        owner_user_id=users["bob"].id,
        name="Thalindra Moonwhisper",
        template="dnd5e",
        sheet=_wizard_sheet("Thalindra Moonwhisper"),
        color="#4ade80",
        portrait_url="/static/demo/tokens/wizard.jpg",
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
        portrait_url="/static/demo/tokens/cleric.jpg",
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
    # v2.342.0 — "The Vault" bulk-stub loot. 60 remaining pure-narrative SRD
    # magic items, each seeded as inert spare loot (equipped=False) on a
    # thematic carrier. Data-driven (rather than 60 inline inventory edits):
    # the catalog rows live in `_MAGIC_ITEM_PASSIVES` (tabletop_routes.py's
    # bulk-stub loop); mechanics are GM-narrated. Appended at each carrier's
    # inventory tail so existing inventory-index assertions stay valid.
    _vault_loot = [
        # (carrier_name, slug, name, type, desc)
        ("Pip Quickfingers", "dust-of-sneezing-and-choking", "Dust of Sneezing and Choking", "consumable", "Uncommon. Thrown into the air (action): each creature in a 30-ft cube makes a DC 15 CON save or can't breathe + is incapacitated (sneezing) while choking, repeating the save each round. RAW DMG p.166."),
        ("Pip Quickfingers", "lantern-of-revealing", "Lantern of Revealing", "magic", "Uncommon. While lit (hooded lantern, 30-ft bright + 30-ft dim), it reveals invisible creatures and objects in the bright light. RAW DMG p.178."),
        ("Pip Quickfingers", "oil-of-slipperiness", "Oil of Slipperiness", "consumable", "Uncommon. Apply to a creature/object (10 min): the freedom-of-movement effect for 8 hours, or coat the floor as a grease spell. RAW DMG p.184."),
        ("Pip Quickfingers", "potion-of-poison", "Potion of Poison", "consumable", "Uncommon (cursed). Disguised as a beneficial potion; on a drink, DC 13 CON save or take 3d6 poison + poisoned 1 hour (half + no poisoned on a pass). RAW DMG p.187."),
        ("Pip Quickfingers", "ring-of-invisibility", "Ring of Invisibility", "magic", "Legendary, attunement. While worn, action to turn invisible (ends when you attack, cast, or use a bonus action to become visible). RAW DMG p.191."),
        ("Thalindra Moonwhisper", "amulet-of-the-planes", "Amulet of the Planes", "magic", "Very rare, attunement. Action: name a location on another plane + make a DC 15 INT check — on a success, cast plane shift; on a fail, you + each creature within 15 ft travel to a random plane. RAW DMG p.150."),
        ("Thalindra Moonwhisper", "helm-of-teleportation", "Helm of Teleportation", "magic", "Rare, attunement. 3 charges (regain 1d3 at dawn). Action: expend 1 to cast teleport. RAW DMG p.169."),
        ("Thalindra Moonwhisper", "manual-of-golems", "Manual of Golems", "magic", "Very rare. A tome with the procedure to build one kind of golem (clay/flesh/iron/stone) over weeks of work + materials. RAW DMG p.180."),
        ("Thalindra Moonwhisper", "ring-of-spell-storing", "Ring of Spell Storing", "magic", "Rare, attunement. Stores up to 5 levels of spells cast into it; you (or anyone wearing it) can later cast a stored spell at the original level. RAW DMG p.192."),
        ("Brother Tavik Stonebrow", "helm-of-comprehending-languages", "Helm of Comprehending Languages", "magic", "Uncommon. While worn, action to cast comprehend languages at will. RAW DMG p.169."),
        ("Brother Tavik Stonebrow", "necklace-of-prayer-beads", "Necklace of Prayer Beads", "magic", "Rare, attunement (cleric/druid/paladin). 1d6+24 beads, several special — each a stored spell (bless, cure wounds, etc.) castable as a bonus action 1/dawn. RAW DMG p.183."),
        ("Brother Tavik Stonebrow", "restorative-ointment", "Restorative Ointment", "consumable", "Uncommon. A jar of 1d4+1 doses; one dose (action) heals 2d8+2 HP and ends one poison or disease. RAW DMG p.180."),
        ("Sir Caelan Lightbringer", "arrow-catching-shield", "Arrow-Catching Shield", "shield", "Rare, attunement. +2 AC vs ranged attacks (on top of the shield's AC); ranged attacks vs targets within 5 ft of you are redirected to you. RAW DMG p.152."),
        ("Sir Caelan Lightbringer", "defender", "Defender", "weapon", "Legendary, attunement (any sword). +3 attack/damage; on each turn you may transfer some/all of the bonus to AC instead. RAW DMG p.164."),
        ("Sir Caelan Lightbringer", "instant-fortress", "Daern's Instant Fortress", "magic", "Rare. A 1-in. metal cube; speak the command word (action) to grow it into a 20-ft-square, 30-ft-tall adamantine tower (AC 20, 100 HP per wall). RAW DMG p.161."),
        ("Sir Caelan Lightbringer", "plate-armor-of-etherealness", "Plate Armor of Etherealness", "armor", "Legendary, attunement. While worn, command word (action) → etherealness for 10 min (1/dawn). RAW DMG p.187."),
        ("Sir Caelan Lightbringer", "talisman-of-pure-good", "Talisman of Pure Good", "magic", "Legendary, attunement (good-aligned). 7 charges: expend 1 to deal 6d6 radiant + scour an evil creature into a fiery pit. A good cleric/paladin gains +2 spell attack. RAW DMG p.207."),
        ("Lyra Sunstrider", "dancing-sword", "Dancing Sword", "weapon", "Very rare, attunement (any sword). Bonus action: toss it to hover and attack a target on its own for up to 4 turns (your attack bonus), then it returns. RAW DMG p.161."),
        ("Lyra Sunstrider", "deck-of-illusions", "Deck of Illusions", "magic", "Uncommon. 34 cards; action to draw + throw one → a 3D illusion of the depicted creature appears (INT-investigation DC 15 to discern). RAW DMG p.162."),
        ("Lyra Sunstrider", "philter-of-love", "Philter of Love", "consumable", "Uncommon. Drink → charmed for 1 hour by the first creature you see within 10 min (if humanoid + opposite-of-indifferent). RAW DMG p.184."),
        ("Mira Greenleaf", "figurine-of-wondrous-power", "Figurine of Wondrous Power (Silver Raven)", "magic", "By figurine. A statuette that becomes a living creature (silver raven → a raven messenger) on the command word; reverts to a figurine after its duration. RAW DMG p.169."),
        ("Mira Greenleaf", "horseshoes-of-a-zephyr", "Horseshoes of a Zephyr", "magic", "Very rare. Four horseshoes; the shod creature moves normally while floating 4 in. above the ground (ignores difficult terrain, can't leave tracks, etc.). RAW DMG p.175."),
        ("Mira Greenleaf", "oil-of-etherealness", "Oil of Etherealness", "consumable", "Rare. Apply over 10 min → the etherealness effect for 1 hour. RAW DMG p.184."),
        ("Garrik Ironside", "adamantine-armor", "Adamantine Armor", "armor", "Uncommon (medium/heavy). While worn, any critical hit against you becomes a normal hit. RAW DMG p.150."),
        ("Garrik Ironside", "handy-haversack", "Heward's Handy Haversack", "magic", "Rare. A backpack with extradimensional pouches; weighs 5 lb regardless of contents; retrieving a specific item is always a swift action. RAW DMG p.174."),
        ("Garrik Ironside", "immovable-rod", "Immovable Rod", "magic", "Uncommon. A flat iron rod; press the button (action) to fix it in place (holds 8,000 lb; DC 30 STR to move). RAW DMG p.176."),
        ("Garrik Ironside", "mithral-armor", "Mithral Armor", "armor", "Uncommon (medium/heavy). Light + flexible — if the base armor imposes disadvantage on Stealth or has a STR requirement, the mithral version doesn't. RAW DMG p.182."),
        ("Garrik Ironside", "oil-of-sharpness", "Oil of Sharpness", "consumable", "Very rare. Coat one slashing/piercing weapon (or 5 pieces of ammo); for 1 hour the item is magical with +3 attack/damage. RAW DMG p.184."),
        ("Kael Brightleaf", "dust-of-dryness", "Dust of Dryness", "consumable", "Uncommon. A packet of 1d6+4 pinches; one pinch absorbs a 15-ft cube of water into a marble-sized pellet (shatter to release). RAW DMG p.166."),
        ("Kael Brightleaf", "gloves-of-missile-snaring", "Gloves of Missile Snaring", "magic", "Uncommon, attunement. Reaction when hit by a ranged weapon attack: reduce the damage by 1d10 + DEX mod; if reduced to 0 and you have a free hand, you catch the missile. RAW DMG p.171."),
        ("Kael Brightleaf", "ring-of-evasion", "Ring of Evasion", "magic", "Rare, attunement. 3 charges (regain 1d3 at dawn). Reaction when you fail a DEX save: expend 1 charge to succeed instead. RAW DMG p.191."),
        ("Zara Emberfire", "orb-of-dragonkind", "Orb of Dragonkind", "magic", "Artifact, attunement. Advantage on saves vs dragon Frightful Presence/breath; while holding it you can cast a charge-fueled spell + attempt to dominate a dragon within 1 mile. RAW DMG p.156."),
        ("Zara Emberfire", "ring-of-djinni-summoning", "Ring of Djinni Summoning", "magic", "Legendary, attunement. Action: summon a specific djinni (1/dawn) that serves + obeys you for up to 1 hour. RAW DMG p.190."),
        ("Krieger Stonefist", "horn-of-valhalla", "Horn of Valhalla (Silver)", "magic", "Rare. Blow the horn (action) to summon 2d4+2 berserker spirits that fight for you for 1 hour (1/short-or-long rest). Higher-metal horns need martial proficiency. RAW DMG p.175."),
        ("Krieger Stonefist", "ring-of-regeneration", "Ring of Regeneration", "magic", "Very rare, attunement. While worn, regain 1d6 HP every 10 min if you have ≥1 HP; severed body parts regrow over 1d6+1 days. RAW DMG p.192."),
        ("Krieger Stonefist", "rod-of-lordly-might", "Rod of Lordly Might", "magic", "Legendary, attunement. A mace +3 with six buttons (blade, climbing pole, battering ram, paralysis/fear/drain strikes) + several daily powers. RAW DMG p.193."),
        ("Krieger Stonefist", "sphere-of-annihilation", "Sphere of Annihilation", "magic", "Legendary. A 2-ft black void that annihilates matter it touches; control it with an INT (Arcana) check (action). RAW DMG p.201."),
        ("Rowan Quickbow", "animated-shield", "Animated Shield", "shield", "Very rare, attunement. Bonus action: speak the command word to make it float + protect you (its AC bonus) for 1 min without using a hand. RAW DMG p.151."),
        ("Rowan Quickbow", "arrow-of-slaying", "Arrow of Slaying", "ammunition", "Very rare. A magic arrow keyed to a creature kind; on a hit vs that kind, +6d10 piercing (DC 17 CON save for half). RAW DMG p.151."),
        ("Rowan Quickbow", "efficient-quiver", "Efficient Quiver", "magic", "Uncommon. Three compartments, each an extradimensional space (arrows, bow-length items, scrolls/wands); draw any stored item as part of an attack. RAW DMG p.167."),
        ("Rowan Quickbow", "horseshoes-of-speed", "Horseshoes of Speed", "magic", "Rare. Four horseshoes; while all four are worn by a mount, its walking speed increases by 30 ft. RAW DMG p.175."),
        ("Magnus Hexbinder", "deck-of-many-things", "Deck of Many Things", "magic", "Legendary. Draw cards to invoke wildly powerful boons or catastrophes (wishes, planar imprisonment, level loss, etc.). RAW DMG p.162."),
        ("Magnus Hexbinder", "medallion-of-thoughts", "Medallion of Thoughts", "magic", "Uncommon, attunement. 3 charges (regain 1d3 at dawn). Action: expend 1 to cast detect thoughts (DC 13). RAW DMG p.182."),
        ("Magnus Hexbinder", "ring-of-telekinesis", "Ring of Telekinesis", "magic", "Very rare, attunement. While worn, cast telekinesis at will (objects only, not worn/carried). RAW DMG p.193."),
        ("Magnus Hexbinder", "rod-of-absorption", "Rod of Absorption", "magic", "Very rare, attunement. Reaction: absorb a single-target spell aimed at you (up to 50 levels stored); later spend stored levels to power your own spells. RAW DMG p.193."),
        ("Magnus Hexbinder", "talisman-of-ultimate-evil", "Talisman of Ultimate Evil", "magic", "Legendary, attunement (evil-aligned). 6 charges: expend 1 to deal 8d6 necrotic + scour a good creature into a fiery pit. An evil cleric/paladin gains +2 spell attack. RAW DMG p.207."),
        ("Dame Seraphine Vael", "ring-of-three-wishes", "Ring of Three Wishes", "magic", "Legendary. 3 charges; expend 1 to cast wish. When the last charge is used, there's a chance the ring vanishes. RAW DMG p.193."),
        ("Dame Seraphine Vael", "shield-of-missile-attraction", "Shield of Missile Attraction", "shield", "Rare, attunement (cursed). Resistance to ranged-weapon damage; the curse redirects ranged attacks aimed within 10 ft of you to you instead. RAW DMG p.199."),
        ("Brakka Wildmane", "dimensional-shackles", "Dimensional Shackles", "magic", "Rare. Apply to an incapacitated creature (action): the shackles prevent all extradimensional movement (teleport, planar travel) while bound. RAW DMG p.165."),
        ("Brakka Wildmane", "pipes-of-the-sewers", "Pipes of the Sewers", "magic", "Uncommon, attunement (wind-instrument proficiency). 3 charges; play to attract + command swarms of rats within 60 ft. RAW DMG p.184."),
        ("Quan Reelstep", "luck-blade", "Luck Blade", "weapon", "Legendary, attunement (any sword). +1 attack/damage; +1 to saving throws; reroll one attack/check/save per dawn; 1d4-1 charges of wish. RAW DMG p.179."),
        ("Quan Reelstep", "rod-of-security", "Rod of Security", "magic", "Very rare. Action: you + up to 199 others travel to an extradimensional paradise for up to 200 days (÷ travelers); return is unharmed + well-fed. RAW DMG p.193."),
        ("Quan Reelstep", "talisman-of-the-sphere", "Talisman of the Sphere", "magic", "Legendary, attunement. Double your proficiency on INT (Arcana) checks to control a sphere of annihilation, and levitate one you control. RAW DMG p.207."),
        ("Quan Reelstep", "well-of-many-worlds", "Well of Many Worlds", "magic", "Legendary. A black cloth that unfolds into a 6-ft planar portal to a random other plane/world; refold to close. RAW DMG p.213."),
        # v2.344.0 — "The Armory's Remainder": the last 12 mechanically-rich
        # SRD items, catalog-stubbed to close the tail (each flagged for
        # future dedicated wiring in tabletop_routes.py). Mechanics
        # GM-narrated until then.
        ("Thalindra Moonwhisper", "bead-of-force", "Bead of Force", "consumable", "Rare. Throw up to 60 ft (action): a 10-ft-radius burst — DC 15 DEX save or 5d4 force; failed-save creatures fully inside are trapped in a sphere of force for 1 min. RAW DMG p.154."),
        ("Thalindra Moonwhisper", "staff-of-the-magi", "Staff of the Magi", "weapon", "Legendary, attunement (sorcerer/warlock/wizard). 50 charges; +2 spell attack, absorb spells, and cast a large spell list (fireball, lightning bolt, web, passwall, etc.). Retributive strike on a break. RAW DMG p.202."),
        ("Krieger Stonefist", "berserker-axe", "Berserker Axe", "weapon", "Rare, attunement (cursed). +1 attack/damage; while attuned your HP max increases by 1 per level. Cursed: on taking damage, DC 15 WIS save or go berserk (attack the nearest creature). RAW DMG p.155."),
        ("Garrik Ironside", "hammer-of-thunderbolts", "Hammer of Thunderbolts", "weapon", "Legendary. +1 maul; with a Belt of Giant Strength + Gauntlets of Ogre Power, STR becomes 20 and crits hurl a thunderclap (DC 17 CON or stunned). Throw to kill a giant (DC 17 CON). RAW DMG p.173."),
        ("Rowan Quickbow", "oathbow", "Oathbow", "weapon", "Very rare, attunement (longbow). Speak the command word to declare a sworn enemy; vs that enemy you have advantage on attacks, +3d6 piercing, and ignore their resistance — until it drops or you sleep. RAW DMG p.183."),
        ("Sir Caelan Lightbringer", "sword-of-wounding", "Sword of Wounding", "weapon", "Rare, attunement (any sword). Once per turn on a hit you can wound the target: at the start of each of its turns it takes 1d4 necrotic (DC 15 CON to end), and HP lost this way returns only on a rest. RAW DMG p.207."),
        ("Mira Greenleaf", "staff-of-the-python", "Staff of the Python", "weapon", "Very rare, attunement. Action: throw the staff to become a giant constrictor snake under your control for up to 1 hour (or until 0 HP); a command word reverts it. RAW DMG p.202."),
        ("Mira Greenleaf", "staff-of-the-woodlands", "Staff of the Woodlands", "weapon", "Rare, attunement (druid). +2 quarterstaff; 10 charges to cast animal friendship, awaken, barkskin, locate animals/plants, speak with animals/plants, wall of thorns; plant it to grow a tree. RAW DMG p.202."),
        ("Magnus Hexbinder", "staff-of-striking", "Staff of Striking", "weapon", "Very rare, attunement. +3 quarterstaff; 10 charges — expend 1-3 on a hit to deal +1d6 force per charge. Regains 1d6+4 charges at dawn. RAW DMG p.202."),
        ("Magnus Hexbinder", "staff-of-withering", "Staff of Withering", "weapon", "Rare, attunement (cleric/druid/warlock). 3 charges. On a hit, expend 1 to deal +2d10 necrotic and force a DC 15 CON save or the target has disadvantage on STR/CON checks + saves for 1 hour. RAW DMG p.202."),
    ]
    _pc_by_name = {
        c.name: c for c in (
            alice_pc, bob_pc, gm_pc, paladin_pc, bard_pc, druid_pc,
            fighter_pc, monk_pc, sorcerer_pc, barbarian_pc, ranger_pc,
            warlock_pc, vengeance_pc, beast_barbarian_pc, drunken_monk_pc,
        )
    }
    for _carrier, _slug, _iname, _itype, _idesc in _vault_loot:
        _pc = _pc_by_name.get(_carrier)
        if _pc is None:
            continue
        _sheet = _pc.sheet or {}
        _inv = list(_sheet.get("inventory") or [])
        _inv.append({
            "name": _iname, "type": _itype, "qty": 1,
            "equippable": True, "equipped": False,
            "_slug": _slug, "desc": _idesc,
        })
        _sheet["inventory"] = _inv
        _pc.sheet = _sheet

    # v2.653.0 — backfill subclass features + race traits on every Vault PC
    # from the shipped SRD content (offline; no-op for non-SRD subclasses/
    # races, and never overwrites the curated class_features lists). Mirrors
    # the leveled-campaign path in build_dnd5e_sheet. See app/demo_features.py.
    from .demo_features import apply_srd_features
    for _vpc in _pc_by_name.values():
        _vs = _vpc.sheet or {}
        apply_srd_features(_vs)
        _vpc.sheet = _vs

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
        # v2.160.1 — legendary-actions Phase 1c demo fixture. The Young
        # Red Dragon above is NOT legendary (young dragons lack legendary
        # actions RAW), so the v2.160.0 GM init-tracker legendary strip
        # had no demo creature to render on. The Adult Red Dragon (CR 17)
        # carries 3 legendary actions (Detect / Tail Attack cost 1, Wing
        # Attack cost 2) with the category+cost fields the v2.159.33
        # backfill set, so its projected sheet.actions drives the strip's
        # buttons + 👑 pool meter. Not placed on the demo map by default
        # (CR 17 would obliterate the Lv 5-9 Tavern Brawl); GM drag-spawns
        # from the Templates tab → adds to init → the strip renders.
        ("adult-red-dragon", "Adult Red Dragon", "dragon"),
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
            x=700, y=210, size=2, team="villain",  # 10·70, 3·70 — on grid
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


def seed_notes(
    db: Session, camp: Campaign, users: dict[str, User]
) -> int:
    """Sample notes + handouts so the Notes drawer isn't empty in the
    demo: a few GM prep notes (folders, a pin, Markdown), two public
    player notes, and two handouts (one revealed to all, one still
    hidden). No private notes — those are end-to-end encrypted and can
    only be created client-side with a passphrase."""
    gm_id = users["gm"].id
    alice_id = users["alice"].id
    bob_id = users["bob"].id
    n = 0

    # ── GM prep notes (gm_only) ──
    gm_notes = [
        # (title, body, folder, pinned)
        ("Session 12 — The Sunken Vault",
         "Tonight's beats:\n\n"
         "- Open on the **flooded antechamber** (DC 13 Athletics to wade)\n"
         "- The vault door needs *both* halves of the bronze key\n"
         "- Reveal the doppelganger if they trust Lord Vey\n"
         "- End on the **drowned choir** waking up",
         "Sessions", True),
        ("NPC — Lord Castellan Vey",
         "Genial, silver-tongued, always *just* slightly too helpful.\n\n"
         "> Secret: Vey is a **doppelganger**. The real Vey is in the vault.\n\n"
         "Tell: he never eats at the feast.",
         "NPCs", False),
        ("Open plot threads",
         "1. Who hired the Crimson Sails to burn the docks?\n"
         "2. The amulet hums near running water — why?\n"
         "3. Sister Aldra still owes the party a favor.",
         "Plot", False),
        ("Tavern name generator",
         "When the party wanders somewhere unplanned:\n\n"
         "- The Gilded Newt\n- Three Copper Kettles\n- The Salt & Sorrow\n"
         "- The Last Lantern",
         "", False),
    ]
    for title, body, folder, pinned in gm_notes:
        db.add(CampaignNote(
            campaign_id=camp.id, author_user_id=gm_id,
            kind="gm_note", visibility="gm_only",
            title=title, body=body, folder=folder, pinned=pinned,
        ))
        n += 1

    # ── Public player notes (visible to the whole table) ──
    db.add(CampaignNote(
        campaign_id=camp.id, author_user_id=alice_id,
        kind="player_note", visibility="public",
        title="Party loot (shared)",
        body="- 47 gp, 3 sp\n- *Potion of Healing* ×2\n- A silver ring "
             "with a kraken sigil\n- The bronze key (top half)",
        folder="Party", pinned=False,
    ))
    n += 1
    db.add(CampaignNote(
        campaign_id=camp.id, author_user_id=bob_id,
        kind="player_note", visibility="public",
        title="Things we know",
        body="The choir only sings at **low tide**. The amulet got warm "
             "when we crossed the bridge. Vey *smiled* when Aldra's name "
             "came up.",
        folder="Party", pinned=False,
    ))
    n += 1

    # ── Handouts (one revealed to all, one still hidden) ──
    db.add(Handout(
        campaign_id=camp.id, author_user_id=gm_id,
        title="The Duke's Letter",
        body="*Found pinned to the harbormaster's door:*\n\n"
             "> Bring the key to the Sunken Vault by the next low tide, "
             "or the city drinks the sea. **Tell no one.**",
        folder="Reveals", revealed=True, reveal_to="all",
    ))
    n += 1
    db.add(Handout(
        campaign_id=camp.id, author_user_id=gm_id,
        title="Vault map (GM copy)",
        body="Reveal **after** the antechamber. The choir is in the "
             "north alcove; the real Lord Vey is chained in the east cell.",
        folder="Reveals", revealed=False, reveal_to=[],
    ))
    n += 1

    db.flush()
    return n


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
    notes = seed_notes(db, camp, users)
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

    # v2.592.0 — the leveled sample campaigns (levels 3/9/13/18). Seeded
    # AFTER the Sundered Vault so it keeps id 1 (the harness CAMPAIGN_ID).
    # Lazy import to avoid an import cycle (demo_campaigns imports helpers
    # from this module). See docs/wiki/demo-content.md.
    from . import demo_campaigns
    extra_campaigns = demo_campaigns.seed_leveled_campaigns(db, users)
    db.commit()

    counts = {
        "users":           len(users),
        "campaign":        1 + len(extra_campaigns),
        "memberships":     3,
        "map":             1,
        "characters":      len(chars),
        "token_templates": len(templates),
        "tokens":          len(tokens),
        "encounters":      1,
        "roll_history":    rolls,
        "homebrew_files":  homebrew_count,
        "leveled_campaigns": len(extra_campaigns),
    }
    log.info("demo reset complete: %s", counts)
    return counts
