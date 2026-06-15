"""v2.309.0 — Manual of Bodily Health (RAW DMG p.176, very rare, no
attunement): study 48 hours over 6 days → your Constitution score increases
by 2, as does its maximum, then the manual loses its magic for a century.

Rides the same `use_kind: "ability_increase"` dispatch as the Gainful Exercise
manual (v2.308.0), but the CON branch ALSO recomputes max HP: a CON-modifier
bump raises max HP by 1 per level (RAW PHB p.173). The handler permanently
WRITES the stored CON, bumps max + current HP by mod_delta × level, consumes
the manual, and broadcasts `character_update` so open sheets re-render.

Demo fixture: Garrik Ironside (Fighter) carries the manual. The fixture
snapshots + restores his inventory, abilities, AND hp so the permanent
mutation doesn't leak across re-runs against the same container.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_MANUAL_SLUG = "manual-of-bodily-health"


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


def _stored_con(sheet):
    return int((sheet.get("abilities") or {}).get("CON") or 0)


def _max_hp(sheet):
    return int((sheet.get("hp") or {}).get("max") or 0)


@pytest_asyncio.fixture
async def garrik_manual(gm_client, roster):
    """Resolve Garrik's CON manual index; snapshot inventory + abilities +
    hp and restore all three in teardown (the happy-path test permanently
    mutates CON, max HP, and consumes the manual)."""
    garrik = roster["Garrik Ironside"]
    sheet = await _sheet(gm_client, garrik["id"])
    inventory = list(sheet.get("inventory") or [])
    abilities = dict(sheet.get("abilities") or {})
    hp = dict(sheet.get("hp") or {})
    level = int(sheet.get("level") or 1)
    idx = _manual_index(inventory)
    assert idx >= 0, "Garrik must carry a seeded Manual of Bodily Health"
    try:
        yield {
            "char": garrik, "index": idx,
            "con": int(abilities.get("CON") or 0),
            "max_hp": int(hp.get("max") or 0),
            "level": max(1, level),
        }
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
            json={"inventory": inventory, "abilities": abilities, "hp": hp},
        )


async def test_manual_raises_con_and_max_hp_and_consumes(
    gm_client, gm_ws, garrik_manual,
):
    """Happy path: using the manual writes stored CON +2, bumps max HP by the
    CON-modifier delta × level, consumes the row, returns the ability_increase
    payload (with hp_gain), and broadcasts character_update."""
    garrik = garrik_manual["char"]
    idx = garrik_manual["index"]
    before_con = garrik_manual["con"]
    before_max = garrik_manual["max_hp"]
    level = garrik_manual["level"]
    assert before_con > 0, "Garrik should have a stored CON"
    expected_mod_delta = ((before_con + 2) // 2) - (before_con // 2)
    expected_hp_gain = expected_mod_delta * level
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
    assert ai["ability"] == "CON"
    assert ai["amount"] == 2
    assert ai["new_score"] == before_con + 2
    assert ai.get("hp_gain") == expected_hp_gain

    msg = await gm_ws.wait_for("character_update")
    assert msg["data"]["id"] == garrik["id"]

    sheet = await _sheet(gm_client, garrik["id"])
    assert _stored_con(sheet) == before_con + 2, (
        f"stored CON not raised: {before_con} → {_stored_con(sheet)}"
    )
    assert _max_hp(sheet) == before_max + expected_hp_gain, (
        f"max HP not raised: {before_max} → {_max_hp(sheet)} "
        f"(expected +{expected_hp_gain})"
    )
    assert _manual_index(sheet.get("inventory") or []) == -1, (
        "manual should be consumed (row removed)"
    )


async def test_manual_baseline_con_unchanged(gm_client, garrik_manual):
    """Control: before using the manual, Garrik's stored CON + max HP are the
    seed values — proving the bump is manual-sourced, not baseline."""
    garrik = garrik_manual["char"]
    sheet = await _sheet(gm_client, garrik["id"])
    assert _stored_con(sheet) == garrik_manual["con"], (
        f"unexpected baseline CON drift: {garrik_manual['con']} → {_stored_con(sheet)}"
    )
    assert _max_hp(sheet) == garrik_manual["max_hp"], (
        f"unexpected baseline max HP drift: {garrik_manual['max_hp']} → {_max_hp(sheet)}"
    )
