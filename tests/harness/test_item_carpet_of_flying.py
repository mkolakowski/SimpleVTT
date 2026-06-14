"""v2.283.0 — Carpet of Flying (RAW DMG p.157, very rare, NO attunement).

Reuses the v2.238.0 Winged Boots flying-speed substrate with zero new
engine code: the `flying_speed` boolean flag rides the `carpet-of-flying`
catalog payload, aggregates in `_equipped_item_effects` (boolean OR into
the `flying_speed` field + `flying_speed_sources`), and surfaces on
`/sheet-json` as `derived.flying_speed = {sources}`. Like the Broom of
Flying (v2.282.0), the carpet's payload omits `requires_attunement`, so
the flag surfaces while merely *equipped* — no attunement needed. The
command-word ride + size-keyed 30-80 ft speed / 200-800 lb capacity are
GM-narrated in v1.

Demo fixture: Pip Quickfingers (Rogue) carries the carpet as inert spare
loot (equipped=False / attuned=False) — she has no flying baseline. The
tests PATCH it equipped (no attune), read `derived.flying_speed`, then
restore the seed inventory.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_CARPET_SLUG = "carpet-of-flying"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def pip(roster):
    return roster["Pip Quickfingers"]


async def _patch_carpet_and_read(gm_client, char_id, *, equipped, attuned):
    """PATCH the spare Carpet of Flying to the given equipped/attuned state,
    read /sheet-json, then restore the original inventory. Returns the
    post-patch derived block."""
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _CARPET_SLUG:
            it["equipped"], it["attuned"] = equipped, attuned
            found = True
    assert found, "Pip has no carpet-of-flying item"
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


async def test_carpet_exposes_flying_speed(gm_client, pip):
    """Happy path: equipping the carpet surfaces `derived.flying_speed`, with
    the carpet named in its sources."""
    derived = await _patch_carpet_and_read(
        gm_client, pip["id"], equipped=True, attuned=False
    )
    fs = derived.get("flying_speed")
    assert fs is not None, (
        f"expected derived.flying_speed, got: {derived!r}"
    )
    assert any(
        "Carpet of Flying" in str(s) for s in fs.get("sources") or []
    ), f"expected the carpet named in sources, got: {fs!r}"


async def test_carpet_baseline_has_no_flying_speed(gm_client, pip):
    """Control: with the carpet inert (seed state), Pip has no flying speed
    — proving it's item-sourced, not baked in."""
    data = await _sheet_json(gm_client, pip["id"])
    assert "flying_speed" not in (data.get("derived") or {}), (
        f"unexpected baseline flying_speed, got: {data.get('derived')!r}"
    )


async def test_carpet_needs_no_attunement(gm_client, pip):
    """RAW distinction: the carpet is a NO-attunement item. Equipped but
    UNATTUNED still surfaces `derived.flying_speed` — like the Broom of
    Flying, and unlike the Wings of Flying / Winged Boots."""
    derived = await _patch_carpet_and_read(
        gm_client, pip["id"], equipped=True, attuned=False
    )
    fs = derived.get("flying_speed")
    assert fs is not None, (
        f"expected flying_speed while equipped-but-unattuned (no-attunement "
        f"item), got: {derived!r}"
    )
    assert any(
        "Carpet of Flying" in str(s) for s in fs.get("sources") or []
    ), f"expected the carpet in sources without attunement, got: {fs!r}"
