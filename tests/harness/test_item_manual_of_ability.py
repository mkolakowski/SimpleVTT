"""v2.222.0 — Manuals & Tomes: permanent ability-score boost books.

RAW DMG pp.180/208: reading the book permanently raises one ability
score by 2 (and its maximum), then the book is consumed. A new
`permanent_boost` archetype on `/use_item_action`, distinct from the
timed self-buff potions and the equipped-item runtime overrides — it's
a flat base-score edit (`sheet.abilities[X] += 2`) that composes with
the override engine via the existing `effective_ability_score`
max(base, set) chain.

Demo fixture: Lyra Sunstrider (Bard, base CHA 17) carries a Tome of
Leadership and Influence (+2 CHA, very rare, no attunement). Reading it
takes her base CHA 17 → 19.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_TOME_SLUG = "tome-of-leadership-and-influence"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def lyra(roster):
    return roster["Lyra Sunstrider"]


def _find_tome(sheet):
    inv = list((sheet or {}).get("inventory") or [])
    for i, it in enumerate(inv):
        if isinstance(it, dict) and it.get("_slug") == _TOME_SLUG:
            return i, inv
    return None, inv


async def _restore(gm_client, char_id, abilities, inventory):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"abilities": abilities, "inventory": inventory},
    )


async def test_reading_tome_permanently_raises_cha(gm_client, lyra):
    """Lyra reads the Tome of Leadership and Influence. Her base CHA rises
    by 2 permanently (reflected on /sheet-json's stored abilities AND the
    derived effective_abilities base), and the book is consumed."""
    data = await _sheet_json(gm_client, lyra["id"])
    sheet = data.get("sheet") or {}
    abilities_snapshot = dict(sheet.get("abilities") or {})
    idx, inv_snapshot = _find_tome(sheet)
    assert idx is not None, "Lyra has no Tome of Leadership and Influence"
    old_cha = int(abilities_snapshot.get("CHA") or 0)
    assert old_cha > 0, "fixture precondition: Lyra should have a CHA score"
    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/use_item_action",
            json={"inventory_index": idx, "action_key": "read"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert body["ability"] == "CHA"
        assert body["amount"] == 2
        assert body["old_score"] == old_cha
        assert body["new_score"] == old_cha + 2
        assert body["consumed"] is True

        after = await _sheet_json(gm_client, lyra["id"])
        after_sheet = after.get("sheet") or {}
        assert int((after_sheet.get("abilities") or {}).get("CHA") or 0) == old_cha + 2
        # A permanent boost edits the stored base, not a runtime override, so
        # CHA does NOT appear in derived.effective_abilities (that map only
        # carries abilities an equipped item sets above base).
        eff_map = (after.get("derived") or {}).get("effective_abilities") or {}
        assert "CHA" not in eff_map, (
            f"permanent boost should not create an override entry; got {eff_map!r}"
        )
        # The book is gone from inventory.
        gone_idx, _ = _find_tome(after_sheet)
        assert gone_idx is None, "the tome should be consumed on read"
    finally:
        await _restore(gm_client, lyra["id"], abilities_snapshot, inv_snapshot)


_BODILY_HEALTH_SLUG = "manual-of-bodily-health"


def _find_slug(sheet, slug):
    inv = list((sheet or {}).get("inventory") or [])
    for i, it in enumerate(inv):
        if isinstance(it, dict) and it.get("_slug") == slug:
            return i, inv
    return None, inv


@pytest_asyncio.fixture
async def garrik(roster):
    return roster["Garrik Ironside"]


async def test_reading_bodily_health_raises_con_and_max_hp(gm_client, garrik):
    """v2.312.0 — Phase 1 of the permanent-ability-increase reconciliation:
    the permanent_boost handler now ports the CON max-HP recompute (RAW PHB
    p.173). Garrik reads the Manual of Bodily Health via /use_item_action:
    base CON +2 AND max HP rises by the CON-modifier delta × level."""
    data = await _sheet_json(gm_client, garrik["id"])
    sheet = data.get("sheet") or {}
    abilities_snapshot = dict(sheet.get("abilities") or {})
    hp_snapshot = dict(sheet.get("hp") or {})
    idx, inv_snapshot = _find_slug(sheet, _BODILY_HEALTH_SLUG)
    assert idx is not None, "Garrik has no Manual of Bodily Health"
    old_con = int(abilities_snapshot.get("CON") or 0)
    old_max = int(hp_snapshot.get("max") or 0)
    level = int(sheet.get("level") or 1)
    assert old_con > 0, "fixture precondition: Garrik should have a CON score"
    expected_mod_delta = ((old_con + 2) // 2) - (old_con // 2)
    expected_hp_gain = expected_mod_delta * max(1, level)
    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/use_item_action",
            json={"inventory_index": idx, "action_key": "read"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert body["ability"] == "CON"
        assert body["new_score"] == old_con + 2
        assert body["hp_gain"] == expected_hp_gain

        after = await _sheet_json(gm_client, garrik["id"])
        after_sheet = after.get("sheet") or {}
        assert int((after_sheet.get("abilities") or {}).get("CON") or 0) == old_con + 2
        assert int((after_sheet.get("hp") or {}).get("max") or 0) == old_max + expected_hp_gain
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"abilities": abilities_snapshot, "inventory": inv_snapshot,
                  "hp": hp_snapshot},
        )


_CLEAR_THOUGHT_SLUG = "tome-of-clear-thought"
_UNDERSTANDING_SLUG = "tome-of-understanding"


@pytest_asyncio.fixture
async def thalindra(roster):
    return roster["Thalindra Moonwhisper"]


@pytest_asyncio.fixture
async def tavik(roster):
    return roster["Brother Tavik Stonebrow"]


async def test_reading_clear_thought_permanently_raises_int(gm_client, thalindra):
    """v2.313.0 — reconciliation Phase 2: the Tome of Clear Thought (INT +2)
    completes the Tome trio on the permanent_boost path. Thalindra (Wizard)
    reads it; her base INT rises by 2 permanently and the book is consumed.
    She carries no INT override (the Headband of Intellect lives on Mira), so
    INT must NOT appear in derived.effective_abilities."""
    data = await _sheet_json(gm_client, thalindra["id"])
    sheet = data.get("sheet") or {}
    abilities_snapshot = dict(sheet.get("abilities") or {})
    idx, inv_snapshot = _find_slug(sheet, _CLEAR_THOUGHT_SLUG)
    assert idx is not None, "Thalindra has no Tome of Clear Thought"
    old_int = int(abilities_snapshot.get("INT") or 0)
    assert old_int > 0, "fixture precondition: Thalindra should have an INT score"
    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
            json={"inventory_index": idx, "action_key": "read"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert body["ability"] == "INT"
        assert body["amount"] == 2
        assert body["old_score"] == old_int
        assert body["new_score"] == old_int + 2
        assert body["consumed"] is True

        after = await _sheet_json(gm_client, thalindra["id"])
        after_sheet = after.get("sheet") or {}
        assert int((after_sheet.get("abilities") or {}).get("INT") or 0) == old_int + 2
        eff_map = (after.get("derived") or {}).get("effective_abilities") or {}
        assert "INT" not in eff_map, (
            f"permanent boost should not create an override entry; got {eff_map!r}"
        )
        gone_idx, _ = _find_slug(after_sheet, _CLEAR_THOUGHT_SLUG)
        assert gone_idx is None, "the tome should be consumed on read"
    finally:
        await _restore(gm_client, thalindra["id"], abilities_snapshot, inv_snapshot)


async def test_reading_understanding_permanently_raises_wis(gm_client, tavik):
    """v2.313.0 — reconciliation Phase 2: the Tome of Understanding (WIS +2)
    is the third leg of the Tome trio on the permanent_boost path. Tavik
    (Cleric) reads it; his base WIS rises by 2 permanently and the book is
    consumed. The Robe of Eyes only grants Perception-check advantage (not a
    score set), so WIS must NOT appear in derived.effective_abilities."""
    data = await _sheet_json(gm_client, tavik["id"])
    sheet = data.get("sheet") or {}
    abilities_snapshot = dict(sheet.get("abilities") or {})
    idx, inv_snapshot = _find_slug(sheet, _UNDERSTANDING_SLUG)
    assert idx is not None, "Tavik has no Tome of Understanding"
    old_wis = int(abilities_snapshot.get("WIS") or 0)
    assert old_wis > 0, "fixture precondition: Tavik should have a WIS score"
    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/use_item_action",
            json={"inventory_index": idx, "action_key": "read"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert body["ability"] == "WIS"
        assert body["amount"] == 2
        assert body["old_score"] == old_wis
        assert body["new_score"] == old_wis + 2
        assert body["consumed"] is True

        after = await _sheet_json(gm_client, tavik["id"])
        after_sheet = after.get("sheet") or {}
        assert int((after_sheet.get("abilities") or {}).get("WIS") or 0) == old_wis + 2
        eff_map = (after.get("derived") or {}).get("effective_abilities") or {}
        assert "WIS" not in eff_map, (
            f"permanent boost should not create an override entry; got {eff_map!r}"
        )
        gone_idx, _ = _find_slug(after_sheet, _UNDERSTANDING_SLUG)
        assert gone_idx is None, "the tome should be consumed on read"
    finally:
        await _restore(gm_client, tavik["id"], abilities_snapshot, inv_snapshot)


async def test_wrong_action_key_on_tome_404s(gm_client, lyra):
    """Guard: the tome's only action is `read`; a mismatched action_key
    (`drink`) returns 404 without mutating the sheet."""
    data = await _sheet_json(gm_client, lyra["id"])
    sheet = data.get("sheet") or {}
    idx, _ = _find_tome(sheet)
    assert idx is not None, "Lyra has no Tome of Leadership and Influence"
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink"},
    )
    assert resp.status_code == 404, resp.text
