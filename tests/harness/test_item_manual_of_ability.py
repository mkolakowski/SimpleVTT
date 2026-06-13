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
