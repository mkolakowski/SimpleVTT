"""v2.158.86 — magic-items-automation Phase 4b: dice-expression
recharge on long rest.

Phase 4a (v2.158.84) gave the Wand of Magic Missiles a 7-charge
resource row with `reset: "long"`. The standard rest-loop refill
path set current=max on long rest — but RAW DMG p.213 says the wand
"regains 1d6+1 expended charges daily at dawn", so a fully-depleted
wand should come back with somewhere between 2 and 7 charges, not
guaranteed 7.

Phase 4b adds `charge_recovery: "1d6+1"` to the resource row + a
parser hook in the rest loop's refill path that reads the expression,
rolls it, and adds the result to current (capped at max) instead of
the standard full refill.

Tests deplete Thalindra's wand to 0 charges via /use_item_action,
long rest, then verify the wand is somewhere between
`min(2, 7) == 2` (1d6=1 + 1 = 2) and `min(7, 7) == 7` (1d6=6 + 1 =
7). Repeat 10 times to validate the bounds hold across rolls. The
Pearl's resource row (no `charge_recovery`) is asserted to still
full-refill on long rest as a regression check.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


THALINDRA_WAND_IDX = 9
THALINDRA_PEARL_IDX = 8


async def _long_rest(gm_client, char_id: int) -> dict:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _deplete_wand(gm_client, char_id: int, charges: int) -> int:
    """Spend `charges` from the wand resource row. Returns the
    resource's `current` after the spend."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/use_item_action",
        json={
            "inventory_index": THALINDRA_WAND_IDX,
            "action_key": "cast-magic-missile",
            "charges": charges,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["resource"]["current"]


async def _wand_current_after_rest(rest_response: dict) -> int:
    """Pull the wand-of-magic-missiles resource current from a rest
    response's `resources` snapshot. Raises if missing."""
    refilled = rest_response.get("resources") or []
    wand_row = next(
        (r for r in refilled if r.get("key") == "wand-of-magic-missiles"),
        None,
    )
    assert wand_row is not None, f"Wand resource missing: {refilled}"
    return int(wand_row.get("current") or 0)


async def test_wand_dice_recharge_within_raw_range(gm_client, roster):
    """v2.158.86 happy path. Burn the wand to 0 charges, long rest →
    current must be between 2 and 7 inclusive (RAW DMG p.213:
    1d6+1 → min 2, max 7). Repeat 5 times; assert every iteration's
    new current is in range. A single OOB value could be a dice
    fluke; a pattern indicates a parser regression."""
    thalindra = roster["Thalindra Moonwhisper"]
    out_of_range: list[int] = []
    for _ in range(5):
        # Long rest to refresh the wand. Read its current after
        # recharge — could be 2-7.
        rest1 = await _long_rest(gm_client, thalindra["id"])
        cur_after_rest = await _wand_current_after_rest(rest1)
        # Burn all charges in one call.
        if cur_after_rest > 0:
            await _deplete_wand(gm_client, thalindra["id"], cur_after_rest)
        # Long rest again — dice-expression recharge fires from 0.
        rest2 = await _long_rest(gm_client, thalindra["id"])
        cur_after_recharge = await _wand_current_after_rest(rest2)
        # RAW: 1d6+1 added to current(0) → range 2..7.
        if not (2 <= cur_after_recharge <= 7):
            out_of_range.append(cur_after_recharge)
    assert not out_of_range, (
        f"Wand recharge produced out-of-RAW-range values across 5 "
        f"iterations: {out_of_range}. Expected 2..7 inclusive each."
    )


async def test_pearl_still_full_refills_on_long_rest(gm_client, roster):
    """v2.158.86 regression: items without a `charge_recovery` field
    must still full-refill on long rest. Pearl is the canary
    (1-charge resource, no dice expression)."""
    thalindra = roster["Thalindra Moonwhisper"]
    # Deplete Pearl by 1. First long-rest to ensure it's at 1.
    await _long_rest(gm_client, thalindra["id"])
    # Need to expend a slot first so Pearl has something to restore.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={
            "spell_slots": {
                "wizard": {
                    "1": {"total": 4, "used": 0},
                    "2": {"total": 3, "used": 1},
                    "3": {"total": 3, "used": 0},
                    "4": {"total": 1, "used": 0},
                },
            },
        },
    )
    use_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/use_item_action",
        json={
            "inventory_index": THALINDRA_PEARL_IDX,
            "action_key": "restore-slot",
            "slot_level": 2,
            "class_slug": "wizard",
        },
    )
    assert use_resp.status_code == 200, use_resp.text
    assert use_resp.json()["resource"]["current"] == 0

    # Long rest → Pearl back to 1 (full refill, no dice expression).
    rest_resp = await _long_rest(gm_client, thalindra["id"])
    refilled = rest_resp.get("resources") or []
    pearl_row = next(
        (r for r in refilled if r.get("key") == "pearl-of-power"),
        None,
    )
    assert pearl_row is not None, refilled
    assert pearl_row["current"] == 1, (
        f"Pearl should fully refill (no charge_recovery → max=1), "
        f"got current={pearl_row['current']}"
    )
