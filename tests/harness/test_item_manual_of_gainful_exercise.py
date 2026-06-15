"""v2.308.0 — Manual of Gainful Exercise (RAW DMG p.176, very rare, no
attunement): study 48 hours over 6 days → your Strength score increases by 2,
as does its maximum, then the manual loses its magic for a century.

The first PERMANENT ability-increase consumable. It rides a new
`use_kind: "ability_increase"` branch in the `/use_item` dispatch: the handler
reads the item's `ability` + `ability_increase`, permanently WRITES the stored
ability score (clamped to 30, no RAW-20 clamp because the manual also raises
the maximum), consumes the manual, and broadcasts `character_update` so open
sheets re-render. The stored write flows to every read site
(effective_ability_score, /roll STR saves + Athletics, carry capacity).

Demo fixture: Garrik Ironside (Fighter) carries the manual. His stored STR is
18; using the manual writes 20. (His equipped Belt of Giant Strength still
overrides EFFECTIVE STR to 21 = max(20, 21) — the stored write is independent.)
The fixture snapshots + restores his inventory AND abilities so the permanent
mutation doesn't leak across re-runs against the same container.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_MANUAL_SLUG = "manual-of-gainful-exercise"


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    return (r.json() or {}).get("sheet") or {}


def _manual_index(inventory):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and (it.get("_slug") or "") == _MANUAL_SLUG:
            return i
    return -1


def _stored_str(sheet):
    return int((sheet.get("abilities") or {}).get("STR") or 0)


@pytest_asyncio.fixture
async def garrik_manual(gm_client, roster):
    """Resolve Garrik's manual index; snapshot inventory + abilities and
    restore both in teardown (the happy-path test permanently mutates STR
    and consumes the manual)."""
    garrik = roster["Garrik Ironside"]
    sheet = await _sheet(gm_client, garrik["id"])
    inventory = list(sheet.get("inventory") or [])
    abilities = dict(sheet.get("abilities") or {})
    idx = _manual_index(inventory)
    assert idx >= 0, "Garrik must carry a seeded Manual of Gainful Exercise"
    try:
        yield {"char": garrik, "index": idx, "str": int(abilities.get("STR") or 0)}
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": inventory, "abilities": abilities},
        )


async def test_manual_raises_stored_str_and_consumes(
    gm_client, gm_ws, garrik_manual,
):
    """Happy path: using the manual writes stored STR +2, consumes the row,
    returns the ability_increase payload, and broadcasts character_update."""
    garrik = garrik_manual["char"]
    idx = garrik_manual["index"]
    before = garrik_manual["str"]
    assert before > 0, "Garrik should have a stored STR"
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_item",
        json={"character_id": garrik["id"], "inventory_index": idx,
              "override": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    ai = body.get("ability_increase")
    assert ai is not None, f"expected ability_increase in body, got: {body!r}"
    assert ai["ability"] == "STR"
    assert ai["amount"] == 2
    assert ai["new_score"] == before + 2

    # WS: clients re-fetch on character_update.
    msg = await gm_ws.wait_for("character_update")
    assert msg["data"]["id"] == garrik["id"]

    # Sheet reflects the permanent stored STR bump + the consumed manual.
    sheet = await _sheet(gm_client, garrik["id"])
    assert _stored_str(sheet) == before + 2, (
        f"stored STR not raised: {before} → {_stored_str(sheet)}"
    )
    assert _manual_index(sheet.get("inventory") or []) == -1, (
        "manual should be consumed (row removed)"
    )


async def test_manual_baseline_str_unchanged(gm_client, garrik_manual):
    """Control: before using the manual, Garrik's stored STR is the seed
    value — proving the bump is manual-sourced, not baseline."""
    garrik = garrik_manual["char"]
    before = garrik_manual["str"]
    sheet = await _sheet(gm_client, garrik["id"])
    assert _stored_str(sheet) == before, (
        f"unexpected baseline STR drift: {before} → {_stored_str(sheet)}"
    )
