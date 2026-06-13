"""v2.221.0 — the Amulet of Health's boosted max HP now drives the
remaining non-combat heal clamps too: short-rest hit dice, Second Wind,
and Lay on Hands. v2.220.0 threaded the effective ceiling into the combat
heal-clamp + long-rest fill; this commit extends it to every other
restore path via the shared ``_sheet_heal_ceiling`` helper.

RAW DMG p.150: the amulet sets CON to 19, raising max HP by the
CON-modifier delta × character level. The stored ``hp.max`` is left
untouched (non-destructive) — each restore path reads the effective
ceiling at clamp time instead.

Demo fixture: Brother Tavik Stonebrow (Cleric Lv 8) wears an equipped +
attuned Amulet of Health — stored max HP 67, effective max HP 83.

Second Wind has no amulet-wearing Fighter in the demo (Garrik wears the
Belt of Giant Strength, not the Amulet), so it isn't directly exercised
here — it reads the same shared ``_sheet_heal_ceiling`` helper the two
covered paths do, so the helper's behavior is the contract under test.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def tavik(roster):
    return roster["Brother Tavik Stonebrow"]


async def _set_hp(gm_client, char_id, current):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"hp": {"current": current}},
    )


async def _long_rest(gm_client, char_id):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


async def _short_rest(gm_client, char_id):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "short"},
    )


async def _ceiling(gm_client, char_id):
    """Return (stored_max, effective) for the sheet, asserting the amulet
    raises the effective ceiling above the stored max."""
    data = await _sheet_json(gm_client, char_id)
    stored_max = int(((data.get("sheet") or {}).get("hp") or {}).get("max") or 0)
    effective = ((data.get("derived") or {}).get("effective_max_hp") or {}).get(
        "effective"
    )
    assert effective and effective > stored_max, (
        f"fixture precondition: amulet should raise the ceiling above "
        f"{stored_max}; got effective_max_hp={effective!r}"
    )
    return stored_max, effective


async def test_short_rest_heals_past_stored_max_via_amulet(gm_client, tavik):
    """Tavik at his stored max spends a hit die on a short rest. Because
    the Amulet of Health raises the effective ceiling above the stored
    max, the recovered HP lands and pushes current above the stored max —
    proof the short-rest clamp now reads the boosted pool, not hp.max."""
    stored_max, effective = await _ceiling(gm_client, tavik["id"])
    try:
        # Long rest first to refill hit dice, then drop to the stored max.
        await _long_rest(gm_client, tavik["id"])
        await _set_hp(gm_client, tavik["id"], stored_max)
        resp = await _short_rest(gm_client, tavik["id"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["type"] == "short"
        hp_after = int(body["hp"]["current"])
        assert stored_max < hp_after <= effective, (
            f"short rest should heal past the stored max via the amulet "
            f"ceiling; expected {stored_max} < hp_after <= {effective}, "
            f"got {hp_after} (recovered={body.get('recovered')})"
        )
    finally:
        await _long_rest(gm_client, tavik["id"])


async def test_lay_on_hands_tops_amulet_wearer_past_stored_max(
    gm_client, roster, tavik
):
    """Sir Caelan (Paladin) lays hands on Tavik while Tavik sits at his
    stored max. The Amulet of Health ceiling lets the heal land past the
    stored max — proof the Lay on Hands clamp honors the boosted pool."""
    caelan = roster["Sir Caelan Lightbringer"]
    stored_max, effective = await _ceiling(gm_client, tavik["id"])
    headroom = effective - stored_max
    try:
        await _set_hp(gm_client, tavik["id"], stored_max)
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_lay_on_hands",
            json={
                "character_id": caelan["id"],
                "target_character_id": tavik["id"],
                "amount": headroom,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["amount_healed"] > 0, (
            f"Lay on Hands should land past the stored max via the amulet "
            f"ceiling; got amount_healed={body['amount_healed']}"
        )
        hp_after = int(body["new_hp"]["current"])
        assert stored_max < hp_after <= effective, (
            f"expected {stored_max} < hp_after <= {effective}; got {hp_after}"
        )
    finally:
        await _long_rest(gm_client, tavik["id"])
