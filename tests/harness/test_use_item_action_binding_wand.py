"""v2.266.0 — charged-items Phase 1: Wand of Binding through the same
`/use_item_action` endpoint as the other charge wands (Magic Missiles /
Fireballs / Lightning Bolts / Web / Polymorph), via the generalized
`_use_item_action_charge_wand` handler. RAW DMG p.211: 7 charges; expend
1 charge to cast Hold Person (save DC 15). RAW also casts Hold Monster
for 5 charges, but that spell is not yet catalogued, so v1 ships Hold
Person only: the catalog sets min == max == 1 and base_slot_level 2
(the spell's own level) — identical in shape to the Wand of Web.

Demo home: Brother Tavik Stonebrow (Cleric) — Hold Person is on his
prepared list, so he's a natural wielder. The wand is his 4th attuned
item (seed-load bypasses the RAW 3-item cap, enforced at /attune
runtime only); the attunement guard below therefore detunes via PATCH
sheet-fields (cap-bypassing) rather than /attune so the restore can't
trip the cap.

The wand index is looked up by `_slug` rather than hardcoded because
Tavik's inventory grew a magic-item tail across the v2.21x–v2.23x runs.

Tests:
  - happy: spend 1 charge → cast_slot_level == 2 (Lv 2 Hold Person).
  - charge bound: charges=2 → 400 (RAW Hold Person via wand is fixed at
    1 charge, max_charges == 1).
  - unattuned guard: detune via PATCH → 409 attunement required.
    Inventory restored in teardown.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_BIND_SLUG = "wand-of-binding"


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
async def tavik_binding_ready(gm_client, roster):
    """Long-rest to refresh charges; teardown long-rests."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _long_rest(gm_client, tavik["id"])
    sheet = await _sheet(gm_client, tavik["id"])
    idx = _slug_index(sheet.get("inventory") or [], _BIND_SLUG)
    assert idx >= 0, "Tavik must carry a seeded Wand of Binding"
    yield {"char": tavik, "idx": idx}
    await _long_rest(gm_client, tavik["id"])


async def test_binding_wand_single_charge_casts_lv2(gm_client, tavik_binding_ready):
    """Happy path. 1 charge → Lv 2 cast (RAW DMG p.211: Hold Person's
    own level, no upcast)."""
    tavik = tavik_binding_ready["char"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/use_item_action",
        json={
            "inventory_index": tavik_binding_ready["idx"],
            "action_key": "cast-hold-person",
            "charges": 1,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["item_name"] == "Wand of Binding"
    assert body["spell_slug"] == "hold-person"
    assert body["charges_spent"] == 1
    assert body["cast_slot_level"] == 2


async def test_binding_wand_rejects_two_charges_400(gm_client, tavik_binding_ready):
    """RAW Hold Person via the wand is a fixed single-charge spend
    (max_charges == 1), so a 2-charge request is out of the [min, max]
    band → 400."""
    tavik = tavik_binding_ready["char"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/use_item_action",
        json={
            "inventory_index": tavik_binding_ready["idx"],
            "action_key": "cast-hold-person",
            "charges": 2,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_binding_wand_requires_attunement_409(gm_client, tavik_binding_ready):
    """RAW gate: Wand of Binding (rare) requires attunement. Detune via
    PATCH sheet-fields (cap-bypassing) → 409 attunement required.
    Inventory restored in teardown."""
    tavik = tavik_binding_ready["char"]
    idx = tavik_binding_ready["idx"]
    sheet = await _sheet(gm_client, tavik["id"])
    inv = list(sheet.get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    try:
        inv[idx] = {**inv[idx], "attuned": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={"inventory": inv},
        )
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "cast-hold-person",
                "charges": 1,
            },
        )
        assert resp.status_code == 409, resp.text
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
