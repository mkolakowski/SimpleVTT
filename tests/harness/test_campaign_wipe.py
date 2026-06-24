"""v2.612.6 — reusable campaign child-wipe (backup/export-import Phase 2).

``app/campaign_wipe.py::wipe_campaign_children`` is the FK-safe per-campaign
child-delete sequence extracted from ``demo_seed.wipe()`` so the importer's
restore path (Phase 7) reuses the exact ordering the demo reseed relies on.

Exercised host-side against an in-memory sqlite — the same pattern as the
admin-center service tests — so it needs no running container (skips on a
host without the app deps). The live demo reseed (which now calls this
helper) stays covered by ``tests/harness/test_demo_campaigns.py``.
"""
import pytest

# The whole module exercises a DB module against in-memory sqlite — skip
# cleanly on a host without the app deps (it runs in the container / CI).
pytest.importorskip("sqlalchemy")


def _seed_campaign_with_children(db, Models, *, name):
    """Create a GM, a campaign, and one row in each child table the wipe
    touches; return (campaign, map, second_user)."""
    User, Campaign, Map, Token, Character, Encounter, DiceRoll, TokenTemplate, CampaignMembership = Models
    gm = User(email=f"gm-{name}@example.com", display_name="GM", password_hash="x")
    player = User(email=f"pl-{name}@example.com", display_name="PL", password_hash="x")
    db.add_all([gm, player])
    db.commit()

    camp = Campaign(name=name, gm_user_id=gm.id, game_system="dnd5e", description="")
    db.add(camp)
    db.commit()

    m = Map(campaign_id=camp.id, name="M1", image_url="/static/uploads/maps/m.png")
    db.add(m)
    db.commit()
    db.add_all([
        Token(map_id=m.id, label="T1", x=1, y=1),
        Character(campaign_id=camp.id, owner_user_id=player.id, name="C1"),
        Encounter(campaign_id=camp.id, name="E1"),
        DiceRoll(campaign_id=camp.id, user_id=gm.id, expression="1d20"),
        TokenTemplate(campaign_id=camp.id, name="NPC"),
        CampaignMembership(campaign_id=camp.id, user_id=player.id),
    ])
    # Campaign points at the map — the wipe must null this before maps drop.
    camp.active_map_id = m.id
    db.commit()
    return camp, m, player


def _make_db():
    pytest.importorskip("sqlalchemy")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import (
        Base, User, Campaign, Map, Token, Character, Encounter,
        DiceRoll, TokenTemplate, CampaignMembership,
    )

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    Models = (User, Campaign, Map, Token, Character, Encounter, DiceRoll, TokenTemplate, CampaignMembership)
    return db, Models


def test_wipe_removes_children_keeps_campaign_row():
    """All child rows for the campaign are deleted; the campaign row itself
    survives (the importer keeps it) and its active_map_id is nulled."""
    from app.campaign_wipe import wipe_campaign_children

    db, Models = _make_db()
    User, Campaign, Map, Token, Character, Encounter, DiceRoll, TokenTemplate, CampaignMembership = Models
    try:
        camp, m, _player = _seed_campaign_with_children(db, Models, name="Wipe Quest")

        counts = wipe_campaign_children(db, [camp.id])
        db.commit()

        # Every child table reported one delete.
        for key in ("tokens", "encounters", "dice_rolls", "token_templates", "characters", "maps", "memberships"):
            assert counts.get(key) == 1, f"{key}: expected 1 delete, got {counts.get(key)}"

        # The campaign row survives, with active_map_id nulled.
        survived = db.query(Campaign).filter(Campaign.id == camp.id).one()
        assert survived.active_map_id is None
        # No child rows remain.
        assert db.query(Map).filter(Map.campaign_id == camp.id).count() == 0
        assert db.query(Token).filter(Token.map_id == m.id).count() == 0
        assert db.query(Character).filter(Character.campaign_id == camp.id).count() == 0
        assert db.query(Encounter).filter(Encounter.campaign_id == camp.id).count() == 0
        assert db.query(DiceRoll).filter(DiceRoll.campaign_id == camp.id).count() == 0
        assert db.query(TokenTemplate).filter(TokenTemplate.campaign_id == camp.id).count() == 0
        assert db.query(CampaignMembership).filter(CampaignMembership.campaign_id == camp.id).count() == 0
    finally:
        db.close()


def test_wipe_keeps_memberships_when_flag_false():
    """The restore path keeps the people in the campaign — memberships
    survive when delete_memberships=False while content is still wiped."""
    from app.campaign_wipe import wipe_campaign_children

    db, Models = _make_db()
    User, Campaign, Map, Token, Character, Encounter, DiceRoll, TokenTemplate, CampaignMembership = Models
    try:
        camp, _m, _player = _seed_campaign_with_children(db, Models, name="Restore Quest")

        counts = wipe_campaign_children(db, [camp.id], delete_memberships=False)
        db.commit()

        assert "memberships" not in counts
        assert db.query(CampaignMembership).filter(CampaignMembership.campaign_id == camp.id).count() == 1
        # Content is still gone.
        assert db.query(Character).filter(Character.campaign_id == camp.id).count() == 0
    finally:
        db.close()


def test_wipe_is_scoped_to_target_campaign():
    """A second campaign's children are untouched — the wipe is id-scoped."""
    from app.campaign_wipe import wipe_campaign_children

    db, Models = _make_db()
    User, Campaign, Map, Token, Character, Encounter, DiceRoll, TokenTemplate, CampaignMembership = Models
    try:
        target, _m, _p = _seed_campaign_with_children(db, Models, name="Target Quest")
        other, _m2, _p2 = _seed_campaign_with_children(db, Models, name="Bystander Quest")

        wipe_campaign_children(db, [target.id])
        db.commit()

        # The bystander campaign keeps all its children.
        assert db.query(Character).filter(Character.campaign_id == other.id).count() == 1
        assert db.query(Map).filter(Map.campaign_id == other.id).count() == 1
        assert db.query(Character).filter(Character.campaign_id == target.id).count() == 0
    finally:
        db.close()


def test_wipe_empty_list_is_noop():
    from app.campaign_wipe import wipe_campaign_children

    db, _Models = _make_db()
    try:
        assert wipe_campaign_children(db, []) == {}
    finally:
        db.close()
