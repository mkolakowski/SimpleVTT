"""v2.263.0 — charged-items Phase 1: Wand of Web through the same
`/use_item_action` endpoint as the damage wands (Magic Missiles /
Fireballs / Lightning Bolts), via the generalized
`_use_item_action_charge_wand` handler. RAW DMG p.213: 7 charges;
expend exactly 1 to cast Web (save DC 15). RAW gives no upcast, so the
catalog sets min == max == 1 and base_slot_level 2 (the spell's own
level) — the only deviation from the damage wands is the fixed
single-charge spend.

Demo home: Thalindra Moonwhisper (Wizard) — Web is a wizard spell and
she already carries the Wand of Fireballs, so two charge wands on one
caster is on-theme. The wand is her 4th attuned item (seed-load bypasses
the RAW 3-item cap, enforced at /attune runtime only); the attunement
guard below therefore detunes via PATCH sheet-fields (cap-bypassing)
rather than /attune so the restore can't trip the cap.

The wand index is looked up by `_slug` rather than hardcoded because
Thalindra's inventory grew a long magic-item tail across v2.158–v2.217.

Tests:
  - happy: spend 1 charge → cast_slot_level == 2 (Lv 2 Web).
  - charge bound: charges=2 → 400 (RAW Web is fixed at 1 charge,
    max_charges == 1).
  - unattuned guard: detune via PATCH → 409 attunement required.
    Inventory restored in teardown.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_WEB_SLUG = "wand-of-web"


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
async def thalindra_web_ready(gm_client, roster):
    """Long-rest to refresh charges; teardown long-rests."""
    thal = roster["Thalindra Moonwhisper"]
    await _long_rest(gm_client, thal["id"])
    sheet = await _sheet(gm_client, thal["id"])
    idx = _slug_index(sheet.get("inventory") or [], _WEB_SLUG)
    assert idx >= 0, "Thalindra must carry a seeded Wand of Web"
    yield {"char": thal, "idx": idx}
    await _long_rest(gm_client, thal["id"])


async def test_web_wand_single_charge_casts_lv2(gm_client, thalindra_web_ready):
    """Happy path. 1 charge → Lv 2 cast (RAW DMG p.213: Web's own
    level, no upcast)."""
    thal = thalindra_web_ready["char"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/use_item_action",
        json={
            "inventory_index": thalindra_web_ready["idx"],
            "action_key": "cast-web",
            "charges": 1,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["item_name"] == "Wand of Web"
    assert body["spell_slug"] == "web"
    assert body["charges_spent"] == 1
    assert body["cast_slot_level"] == 2


async def test_web_wand_rejects_two_charges_400(gm_client, thalindra_web_ready):
    """RAW Web is a fixed single-charge spend (max_charges == 1), so a
    2-charge request is out of the [min, max] band → 400."""
    thal = thalindra_web_ready["char"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/use_item_action",
        json={
            "inventory_index": thalindra_web_ready["idx"],
            "action_key": "cast-web",
            "charges": 2,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_web_wand_requires_attunement_409(gm_client, thalindra_web_ready):
    """RAW gate: Wand of Web (rare) requires attunement. Detune via
    PATCH sheet-fields (cap-bypassing) → 409 attunement required.
    Inventory restored in teardown."""
    thal = thalindra_web_ready["char"]
    idx = thalindra_web_ready["idx"]
    sheet = await _sheet(gm_client, thal["id"])
    inv = list(sheet.get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    try:
        inv[idx] = {**inv[idx], "attuned": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/sheet-fields",
            json={"inventory": inv},
        )
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/use_item_action",
            json={
                "inventory_index": idx,
                "action_key": "cast-web",
                "charges": 1,
            },
        )
        assert resp.status_code == 409, resp.text
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
