"""v2.282.0 — Broom of Flying (RAW DMG p.156, uncommon, NO attunement).

Reuses the v2.238.0 Winged Boots flying-speed substrate with zero new
engine code: the `flying_speed` boolean flag rides the `broom-of-flying`
catalog payload, aggregates in `_equipped_item_effects` (boolean OR into
the `flying_speed` field + `flying_speed_sources`), and surfaces on
`/sheet-json` as `derived.flying_speed = {sources}`. Unlike the Wings of
Flying / Winged Boots (both attunement items), the broom's payload omits
`requires_attunement`, so the flag surfaces while merely *equipped* — no
attunement needed. The command-word ride + 50-ft speed / 400-lb capacity
are GM-narrated in v1.

Demo fixture: Zara Emberfire (Draconic Sorcerer) carries the broom as
inert spare loot (equipped=False / attuned=False) — she has no flying
baseline. The tests PATCH it equipped (no attune), read
`derived.flying_speed`, then restore the seed inventory.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_BROOM_SLUG = "broom-of-flying"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def zara(roster):
    return roster["Zara Emberfire"]


async def _patch_broom_and_read(gm_client, char_id, *, equipped, attuned):
    """PATCH the spare Broom of Flying to the given equipped/attuned state,
    read /sheet-json, then restore the original inventory. Returns the
    post-patch derived block."""
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _BROOM_SLUG:
            it["equipped"], it["attuned"] = equipped, attuned
            found = True
    assert found, "Zara has no broom-of-flying item"
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


async def test_broom_exposes_flying_speed(gm_client, zara):
    """Happy path: equipping the broom surfaces `derived.flying_speed`, with
    the broom named in its sources."""
    derived = await _patch_broom_and_read(
        gm_client, zara["id"], equipped=True, attuned=False
    )
    fs = derived.get("flying_speed")
    assert fs is not None, (
        f"expected derived.flying_speed, got: {derived!r}"
    )
    assert any(
        "Broom of Flying" in str(s) for s in fs.get("sources") or []
    ), f"expected the broom named in sources, got: {fs!r}"


async def test_broom_baseline_has_no_flying_speed(gm_client, zara):
    """Control: with the broom inert (seed state), Zara has no flying speed
    — proving it's item-sourced, not baked in."""
    data = await _sheet_json(gm_client, zara["id"])
    assert "flying_speed" not in (data.get("derived") or {}), (
        f"unexpected baseline flying_speed, got: {data.get('derived')!r}"
    )


async def test_broom_needs_no_attunement(gm_client, zara):
    """RAW distinction: the broom is a NO-attunement item. Equipped but
    UNATTUNED still surfaces `derived.flying_speed` — unlike the Wings of
    Flying / Winged Boots, whose flag requires attunement."""
    derived = await _patch_broom_and_read(
        gm_client, zara["id"], equipped=True, attuned=False
    )
    fs = derived.get("flying_speed")
    assert fs is not None, (
        f"expected flying_speed while equipped-but-unattuned (no-attunement "
        f"item), got: {derived!r}"
    )
    assert any(
        "Broom of Flying" in str(s) for s in fs.get("sources") or []
    ), f"expected the broom in sources without attunement, got: {fs!r}"
