"""v2.264.0 — charged-items Phase 1: Wand of Polymorph through the same
`/use_item_action` endpoint as the other charge wands (Magic Missiles /
Fireballs / Lightning Bolts / Web), via the generalized
`_use_item_action_charge_wand` handler. RAW DMG p.212: 7 charges; expend
exactly 1 to cast Polymorph (save DC 15). RAW gives no upcast, so the
catalog sets min == max == 1 and base_slot_level 4 (the spell's own
level) — the only deviation from the damage wands is the fixed
single-charge spend, identical in shape to the Wand of Web.

Demo home: Zara Emberfire (Sorcerer) — Polymorph is on the Sorcerer
list, so she's a natural wielder. The wand is her 4th attuned item
(seed-load bypasses the RAW 3-item cap, enforced at /attune runtime
only); the attunement guard below therefore detunes via PATCH
sheet-fields (cap-bypassing) rather than /attune so the restore can't
trip the cap.

The wand index is looked up by `_slug` rather than hardcoded because
Zara's inventory grew a magic-item tail across v2.208–v2.215.

Tests:
  - happy: spend 1 charge → cast_slot_level == 4 (Lv 4 Polymorph).
  - charge bound: charges=2 → 400 (RAW Polymorph is fixed at 1 charge,
    max_charges == 1).
  - unattuned guard: detune via PATCH → 409 attunement required.
    Inventory restored in teardown.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_POLY_SLUG = "wand-of-polymorph"


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


def _slug_index(inventory, slug):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and (it.get("_slug") or "") == slug:
            return i
    return -1


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


@pytest_asyncio.fixture
async def zara_polymorph_ready(gm_client, roster):
    """Long-rest to refresh charges; teardown long-rests."""
    zara = roster["Zara Emberfire"]
    await _long_rest(gm_client, zara["id"])
    sheet = await _sheet(gm_client, zara["id"])
    idx = _slug_index(sheet.get("inventory") or [], _POLY_SLUG)
    assert idx >= 0, "Zara must carry a seeded Wand of Polymorph"
    yield {"char": zara, "idx": idx}
    await _long_rest(gm_client, zara["id"])


async def test_polymorph_wand_single_charge_casts_lv4(gm_client, zara_polymorph_ready):
    """Happy path. 1 charge → Lv 4 cast (RAW DMG p.212: Polymorph's own
    level, no upcast)."""
    zara = zara_polymorph_ready["char"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/use_item_action",
        json={
            "inventory_index": zara_polymorph_ready["idx"],
            "action_key": "cast-polymorph",
            "charges": 1,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["item_name"] == "Wand of Polymorph"
    assert body["spell_slug"] == "polymorph"
    assert body["charges_spent"] == 1
    assert body["cast_slot_level"] == 4


async def test_polymorph_wand_rejects_two_charges_400(gm_client, zara_polymorph_ready):
    """RAW Polymorph is a fixed single-charge spend (max_charges == 1),
    so a 2-charge request is out of the [min, max] band → 400."""
    zara = zara_polymorph_ready["char"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/use_item_action",
        json={
            "inventory_index": zara_polymorph_ready["idx"],
            "action_key": "cast-polymorph",
            "charges": 2,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_polymorph_wand_requires_attunement_409(gm_client, zara_polymorph_ready):
    """RAW gate: Wand of Polymorph (rare) requires attunement. Detune
    via PATCH sheet-fields (cap-bypassing) → 409 attunement required.
    Inventory restored in teardown."""
    zara = zara_polymorph_ready["char"]
    idx = zara_polymorph_ready["idx"]
    sheet = await _sheet(gm_client, zara["id"])
    inv = list(sheet.get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    try:
        inv[idx] = {**inv[idx], "attuned": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
            json={"inventory": inv},
        )
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "cast-polymorph",
                "charges": 1,
            },
        )
        assert resp.status_code == 409, resp.text
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
