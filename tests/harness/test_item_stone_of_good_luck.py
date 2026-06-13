"""v2.209.0 — magic-items Stone of Good Luck (Luckstone, RAW DMG
p.207, uncommon, attunement): while carried, +1 to ability checks AND
saving throws.

The save half rides the existing v2.158.74 ``save_bonus`` substrate
(same path as Cloak of Protection). The check half is the NEW wiring
this commit: ``_equipped_item_effects`` grows a ``check_bonus`` field,
and the /roll endpoint appends it for ability checks (``*_check``
stat_keys) and ability-based skill checks (rolls carrying
``stat_ability``) — but NOT for saves (handled by the save branch) or
plain dice rolls with no stat context.

Demo fixture: Garrik Ironside (Fighter 9) carries an equipped +
attuned Stone of Good Luck. His STR + CON saves are class-proficient
and Athletics is a STR skill, so both halves assert cleanly.
"""
import pytest

from .conftest import CAMPAIGN_ID


async def test_stone_of_good_luck_grants_save_bonus(gm_client, roster):
    """The save half (existing substrate): a ``str_save`` roll on
    Garrik picks up the Stone's +1 and the source attribution."""
    garrik = roster["Garrik Ironside"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+8",
            "stat_key": "str_save",
            "character_id": garrik["id"],
            "note": "STR save (test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    breakdown = resp.json().get("breakdown", "")
    assert "Stone of Good Luck" in breakdown, (
        f"expected 'Stone of Good Luck' in save breakdown, got: {breakdown!r}"
    )
    assert "+1" in breakdown, (
        f"expected '+1' bonus annotation, got: {breakdown!r}"
    )


async def test_stone_of_good_luck_grants_ability_check_bonus(gm_client, roster):
    """The NEW check half: a ``str_check`` roll on Garrik picks up the
    Stone's +1 via the v2.209.0 ability-check read site. This is the
    surface the Cloak deliberately does NOT touch (see the cloak guard
    test) — the Luckstone is the first item that does."""
    garrik = roster["Garrik Ironside"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+4",
            "stat_key": "str_check",
            "character_id": garrik["id"],
            "note": "STR check (test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    breakdown = resp.json().get("breakdown", "")
    assert "Stone of Good Luck" in breakdown, (
        f"expected 'Stone of Good Luck' in check breakdown, got: {breakdown!r}"
    )
    assert "+1" in breakdown, (
        f"expected '+1' bonus annotation, got: {breakdown!r}"
    )


async def test_stone_of_good_luck_grants_skill_check_bonus(gm_client, roster):
    """The check half also fires for ability-based skill rolls — these
    carry ``stat_ability`` (e.g. "STR" for Athletics) rather than a
    ``*_check`` stat_key. Garrik's Athletics roll picks up the +1."""
    garrik = roster["Garrik Ironside"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+8",
            "stat_key": "Athletics",
            "stat_ability": "STR",
            "character_id": garrik["id"],
            "note": "Athletics check (test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    breakdown = resp.json().get("breakdown", "")
    assert "Stone of Good Luck" in breakdown, (
        f"expected 'Stone of Good Luck' in skill breakdown, got: {breakdown!r}"
    )
