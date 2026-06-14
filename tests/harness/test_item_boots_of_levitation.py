"""v2.284.0 — Boots of Levitation (RAW DMG p.155, rare, attunement).

First item on the NEW `levitate_at_will` boolean substrate. The flag rides
the `boots-of-levitation` catalog payload (`levitate_at_will: True`,
`requires_attunement: True`), aggregates in `_equipped_item_effects`
(boolean OR into the `levitate_at_will` field + `levitate_at_will_sources`),
and surfaces on `/sheet-json` as `derived.levitate_at_will = {sources}`. The
action cost + the levitate spell's vertical-move / 20-min-concentration
mechanics are GM-narrated in v1.

Demo fixture: Magnus Hexbinder (Warlock) carries the boots as inert spare
loot (equipped=False / attuned=False) — he has no levitate baseline. The
tests PATCH the boots equipped+attuned, read `derived.levitate_at_will`,
then restore the seed inventory.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_BOOTS_SLUG = "boots-of-levitation"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def magnus(roster):
    return roster["Magnus Hexbinder"]


async def _equip_boots_and_read(gm_client, char_id):
    """PATCH the spare Boots of Levitation ON (equipped + attuned), read
    /sheet-json, then restore the original inventory. Returns the post-equip
    derived block."""
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _BOOTS_SLUG:
            it["equipped"], it["attuned"] = True, True
            found = True
    assert found, "Magnus has no boots-of-levitation item"
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    try:
        data2 = await _sheet_json(gm_client, char_id)
        return data2.get("derived") or {}
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_boots_expose_levitate_at_will(gm_client, magnus):
    """Happy path: equipping the boots surfaces `derived.levitate_at_will`,
    with the boots named in their sources."""
    derived = await _equip_boots_and_read(gm_client, magnus["id"])
    lv = derived.get("levitate_at_will")
    assert lv is not None, (
        f"expected derived.levitate_at_will, got: {derived!r}"
    )
    assert any(
        "Boots of Levitation" in str(s) for s in lv.get("sources") or []
    ), f"expected the boots named in sources, got: {lv!r}"


async def test_boots_baseline_has_no_levitate(gm_client, magnus):
    """Control: with the boots inert (seed state), Magnus has no
    levitate-at-will — proving it's item-sourced, not baked in."""
    data = await _sheet_json(gm_client, magnus["id"])
    assert "levitate_at_will" not in (data.get("derived") or {}), (
        f"unexpected baseline levitate_at_will, got: {data.get('derived')!r}"
    )


async def test_boots_require_attunement(gm_client, magnus):
    """The boots are an attunement item — the flag only surfaces while
    `attuned: True`. Equipped-but-unattuned yields no
    `derived.levitate_at_will`; restores the original inventory on teardown."""
    data = await _sheet_json(gm_client, magnus["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _BOOTS_SLUG:
            it["equipped"], it["attuned"] = True, False
            found = True
    assert found, "Magnus has no boots-of-levitation item"
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"inventory": new_inv},
        )
        data2 = await _sheet_json(gm_client, magnus["id"])
        assert "levitate_at_will" not in (data2.get("derived") or {}), (
            f"expected no levitate_at_will while equipped-but-unattuned, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
