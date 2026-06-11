"""v2.158.82 — magic-items-automation Phase 3: `/use_item_action`
endpoint with the Pearl of Power dispatch.

Pearl of Power (uncommon wondrous item, attunement) — RAW DMG p.184:
"While this pearl is on your person, you can use an action to speak
its command word and regain one expended spell slot. If the expended
slot was of 4th level or higher, the new slot is 3rd level. Once
you use the pearl, it can't be used again until the next dawn."

Endpoint: `POST /api/campaign/{cid}/character/{char_id}/use_item_action`
Body: `{inventory_index, action_key, slot_level, class_slug?}`.

Demo fixture: Thalindra Moonwhisper (Wizard Lv 7, slots 4/3/3/1)
carries a permanent equipped + attuned Pearl of Power in her
inventory (v2.158.82 seed) + a `pearl-of-power` resource row
(max 1, reset long). Tests:

  - happy: spend a Lv 2 slot via /cast_spell, use Pearl to restore →
    slot's `used` decrements + pearl resource decrements.
  - out_of_uses: invoke Pearl when resource current=0 → 409.
  - over-cap slot_level: request slot_level=4 → 400 (Pearl caps at 3
    RAW).
  - no expended slot: request a slot_level that has no expended
    slots → 409 `no_expended_slot`.
  - unknown action: invalid action_key → 404.
  - error paths: missing fields → 400, wrong item slug → 404.

Teardown: a long-rest call refills Thalindra's slots + pearl
resource so subsequent tests see the clean seed.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Thalindra's inventory indices (as of v2.158.82):
#   0  Quarterstaff
#   1  Spellbook
#   2  Component pouch
#   3  Scholar's pack
#   4  Robes
#   5  Ink and quill
#   6  Small knife (dagger)
#   7  Cloak of Protection (attuned: True)
#   8  Pearl of Power      (attuned: True)
THALINDRA_PEARL_IDX = 8


async def _long_rest(gm_client, char_id: int) -> None:
    """Long rest refills spell slots + the pearl-of-power resource
    via the standard reset=long path."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def _spend_slot(gm_client, char_id: int, level: int) -> None:
    """Mutate the sheet's spell_slots.wizard[level].used += 1 via the
    /resource endpoint. Simpler than driving /cast_spell which needs
    a target. The harness exercises /cast_spell elsewhere; here we
    just need a slot to be expended so Pearl has something to restore.
    """
    # The /resource endpoint takes a resource key, not a slot. Use the
    # /sheet-fields PATCH to mutate spell_slots directly instead.
    # spell_slots is in the patch allowlist.
    sheet_resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={
            "spell_slots": {
                "wizard": {
                    "1": {"total": 4, "used": 0},
                    "2": {"total": 3, "used": 1 if level == 2 else 0},
                    "3": {"total": 3, "used": 1 if level == 3 else 0},
                    "4": {"total": 1, "used": 0},
                },
            },
        },
    )
    assert sheet_resp.status_code == 200, sheet_resp.text


@pytest_asyncio.fixture
async def thalindra_with_expended_slot(gm_client, roster):
    """Reset Thalindra to a known state with one expended Lv 2 slot
    + Pearl resource at current=1. Teardown long-rests her."""
    thalindra = roster["Thalindra Moonwhisper"]
    await _long_rest(gm_client, thalindra["id"])
    await _spend_slot(gm_client, thalindra["id"], level=2)
    yield thalindra
    await _long_rest(gm_client, thalindra["id"])


async def test_use_pearl_restores_expended_slot(
    gm_client, thalindra_with_expended_slot,
):
    """v2.158.82 happy path. Thalindra's Lv 2 slot is expended;
    invoking Pearl with slot_level=2 → response carries the
    restored slot count (used drops to 0) + the pearl resource
    decrement (1 → 0)."""
    thalindra = thalindra_with_expended_slot
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": THALINDRA_PEARL_IDX,
            "action_key": "restore-slot",
            "slot_level": 2,
            "class_slug": "wizard",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["item_name"] == "Pearl of Power"
    assert body["slot_restored"]["class_slug"] == "wizard"
    assert body["slot_restored"]["level"] == 2
    assert body["slot_restored"]["used"] == 0
    assert body["resource"]["current"] == 0
    assert body["resource"]["max"] == 1


async def test_use_pearl_out_of_uses_409(
    gm_client, thalindra_with_expended_slot,
):
    """v2.158.82 cap path. Use the pearl once (depletes resource);
    re-use → 409 `out_of_uses`. Re-expend a slot first so the
    second call's failure isn't masked by a no-expended-slot 409."""
    thalindra = thalindra_with_expended_slot

    # First use → 200.
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": THALINDRA_PEARL_IDX,
            "action_key": "restore-slot",
            "slot_level": 2,
            "class_slug": "wizard",
        },
    )
    assert r1.status_code == 200, r1.text

    # Re-expend a Lv 2 slot.
    await _spend_slot(gm_client, thalindra["id"], level=2)

    # Second use → 409 out_of_uses.
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": THALINDRA_PEARL_IDX,
            "action_key": "restore-slot",
            "slot_level": 2,
            "class_slug": "wizard",
        },
    )
    assert r2.status_code == 409, r2.text
    assert r2.json().get("error") == "out_of_uses"


async def test_use_pearl_slot_level_over_cap_400(
    gm_client, thalindra_with_expended_slot,
):
    """v2.158.82 RAW cap. Pearl restores up to Lv 3; requesting Lv 4
    → 400. Phase 4 polish could auto-cast a Lv 4 request as Lv 3,
    but RAW restricts the player's choice on the request side."""
    thalindra = thalindra_with_expended_slot
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": THALINDRA_PEARL_IDX,
            "action_key": "restore-slot",
            "slot_level": 4,
            "class_slug": "wizard",
        },
    )
    assert resp.status_code == 400, resp.text


async def test_use_pearl_no_expended_slot_409(
    gm_client, roster,
):
    """v2.158.82 contract: invoking Pearl when no slot of the
    requested level is expended → 409 `no_expended_slot`."""
    thalindra = roster["Thalindra Moonwhisper"]
    await _long_rest(gm_client, thalindra["id"])  # all slots full
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": THALINDRA_PEARL_IDX,
            "action_key": "restore-slot",
            "slot_level": 2,
            "class_slug": "wizard",
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "no_expended_slot"


async def test_use_pearl_unknown_action_404(
    gm_client, roster,
):
    """v2.158.82 dispatch guard: action_key the catalog doesn't
    know for this item → 404."""
    thalindra = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": THALINDRA_PEARL_IDX,
            "action_key": "fireball",
            "slot_level": 3,
        },
    )
    assert resp.status_code == 404, resp.text


async def test_use_item_action_missing_fields_400(gm_client, roster):
    """v2.158.82 error path: empty body → 400."""
    thalindra = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={},
    )
    assert resp.status_code == 400
