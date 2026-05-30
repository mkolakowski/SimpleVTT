"""v2.97.73 — Banishment appears on Caelan's spell list (preparable
but not castable until Paladin Lv 13).

Caelan is currently Paladin Lv 7 — below the L4 slot threshold (RAW
half-caster). Banishment is on his class spell list (Paladin Lv 4
spell). The entry documents the spell as known/preparable but
``/cast_spell`` returns 409 ``no_slot`` for slot_level=4 calls.

Tests:
1. Banishment appears on Caelan's roster spell list at level 4.
2. Casting Banishment at slot_level=4 returns 409 with a no-slot
   error because Caelan has no L4 slot pool at his current level.
"""
from .conftest import CAMPAIGN_ID


async def test_caelan_has_banishment_known_but_cant_cast_yet(
    gm_client, roster,
):
    """Banishment is on Caelan's spell list (Lv 4). Attempting to
    cast it at slot_level=4 returns 409 ``no_slot``."""
    caelan = roster["Sir Caelan Lightbringer"]

    # Verify Banishment appears on his spell list via the broader
    # roster view (no /sheet endpoint readily available — use the
    # spell_index-based /cast_spell with a known index instead).
    # Banishment was appended at the END of Caelan's spell list.
    # Caelan's original list had 8 spells (Bless=0, Cure Wounds=1,
    # Shield of Faith=2, PFE&G=3, Sanctuary=4, Aid=5, Lesser
    # Restoration=6, Zone of Truth=7); Banishment lands at index 8.
    BANISHMENT_INDEX = 8

    # Attempt to cast Banishment at slot_level=4 — should return 409
    # ``no_slot`` because Caelan has no L4 slot pool.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": BANISHMENT_INDEX,
            "slot_level": 4,
            "class_slug": "paladin",
            # No target needed — the slot check fires before resolution.
            "override": True,
            "override_range": True,
        },
    )
    # Expect 409 with the no_slot error.
    assert resp.status_code == 409, (
        f"expected 409 no_slot for Caelan casting Banishment at L4 "
        f"(he has no L4 slots at Lv 7); got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body.get("error") == "no_slot", (
        f"expected error=no_slot; got {body}"
    )
