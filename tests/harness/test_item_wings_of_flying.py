"""v2.281.0 — Wings of Flying (RAW DMG p.214, rare, attunement).

Reuses the v2.238.0 Winged Boots flying-speed substrate with zero new
engine code: the `flying_speed` boolean flag rides the `wings-of-flying`
catalog payload (`flying_speed: True`, `requires_attunement: True`),
aggregates in `_equipped_item_effects` (boolean OR into the `flying_speed`
field + `flying_speed_sources`), and surfaces on `/sheet-json` as
`derived.flying_speed = {sources}`. The command-word activation + 1-hour
duration / 1d12-hour cooldown are GM-narrated in v1.

Demo fixture: Rowan Quickbow (Ranger) carries the cloak as inert spare
loot (equipped=False / attuned=False) — he has no flying baseline. The
tests PATCH it equipped+attuned, read `derived.flying_speed`, then restore
the seed inventory.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_WINGS_SLUG = "wings-of-flying"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def rowan(roster):
    return roster["Rowan Quickbow"]


async def _equip_wings_and_read(gm_client, char_id):
    """PATCH the spare Wings of Flying ON (equipped + attuned), read
    /sheet-json, then restore the original inventory. Returns the post-equip
    derived block."""
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _WINGS_SLUG:
            it["equipped"], it["attuned"] = True, True
            found = True
    assert found, "Rowan has no wings-of-flying item"
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


async def test_wings_expose_flying_speed(gm_client, rowan):
    """Happy path: equipping the wings surfaces `derived.flying_speed`, with
    the cloak named in its sources."""
    derived = await _equip_wings_and_read(gm_client, rowan["id"])
    fs = derived.get("flying_speed")
    assert fs is not None, (
        f"expected derived.flying_speed, got: {derived!r}"
    )
    assert any(
        "Wings of Flying" in str(s) for s in fs.get("sources") or []
    ), f"expected the cloak named in sources, got: {fs!r}"


async def test_wings_baseline_has_no_flying_speed(gm_client, rowan):
    """Control: with the wings inert (seed state), Rowan has no flying speed
    — proving it's item-sourced, not baked in."""
    data = await _sheet_json(gm_client, rowan["id"])
    assert "flying_speed" not in (data.get("derived") or {}), (
        f"unexpected baseline flying_speed, got: {data.get('derived')!r}"
    )


async def test_wings_require_attunement(gm_client, rowan):
    """The cloak is an attunement item — the flag only surfaces while
    `attuned: True`. Equipped-but-unattuned yields no `derived.flying_speed`;
    restores the original inventory on teardown."""
    data = await _sheet_json(gm_client, rowan["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _WINGS_SLUG:
            it["equipped"], it["attuned"] = True, False
            found = True
    assert found, "Rowan has no wings-of-flying item"
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"inventory": new_inv},
        )
        data2 = await _sheet_json(gm_client, rowan["id"])
        assert "flying_speed" not in (data2.get("derived") or {}), (
            f"expected no flying_speed while equipped-but-unattuned, got: "
            f"{data2.get('derived')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
