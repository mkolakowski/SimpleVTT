"""v2.99.171 — Backfill regression tests for the falsy-zero
parse fix across 11 /cast_<spell> endpoints.

Closes the v2.99.151 filed item ("11 other falsy-zero parse
sites"). The pattern `int(slot_level_raw) if slot_level_raw
else N` treated literal 0 as falsy and lifted it to N, masking
the "slot_level must be >= M" validation gate. v2.99.151 fixed
/cast_bane; v2.99.171 applies the same `is not None` check
across the remaining 11 endpoints:
  - /cast_hunters_mark (L1+)
  - /cast_hex (L1+)
  - /cast_sleep (L1+)
  - /cast_slow (L3+)
  - /cast_polymorph (L4+)
  - /cast_compulsion (L4+)
  - /cast_bestow_curse (L3+)
  - /cast_hold_person (L2+)
  - /cast_flesh_to_stone (L6+)
  - /cast_hold_monster (L5+)
  - /cast_web (L2+)

The bug surface is tiny (a caller passing `slot_level: 0`
explicitly), but it caused 409 `no_slot` or `wrong_class`
responses instead of the contract's 400 — surprising the
caller about which gate fired.

Tests assert that each backfilled endpoint returns 400 on
`slot_level: 0`. Doesn't test the surrounding validation chain
(other endpoints' tests cover that); just confirms the falsy-
zero gate fires correctly.
"""
import pytest

from .conftest import CAMPAIGN_ID


# Endpoints + their canonical body shape. character_id: 1
# (the demo GM Pip Quickfingers, who's the first PC) — won't
# pass the validation chain past the slot_level gate but should
# 400 before any class check fires.
_ENDPOINTS = [
    ("cast_hunters_mark", {"character_id": 1, "slot_level": 0}),
    ("cast_hex", {"character_id": 1, "slot_level": 0}),
    ("cast_sleep", {"character_id": 1, "slot_level": 0}),
    ("cast_slow", {"character_id": 1, "class_slug": "wizard",
                   "slot_level": 0, "target_combatant_ids": ["x"]}),
    ("cast_polymorph", {"character_id": 1, "class_slug": "wizard",
                        "slot_level": 0, "target_combatant_id": "x"}),
    ("cast_compulsion", {"character_id": 1, "class_slug": "wizard",
                         "slot_level": 0}),
    ("cast_bestow_curse", {"character_id": 1, "class_slug": "wizard",
                           "slot_level": 0}),
    ("cast_hold_person", {"character_id": 1, "class_slug": "wizard",
                          "slot_level": 0,
                          "target_combatant_ids": ["x"]}),
    ("cast_flesh_to_stone", {"character_id": 1, "class_slug": "wizard",
                             "slot_level": 0,
                             "target_combatant_id": "x"}),
    ("cast_hold_monster", {"character_id": 1, "class_slug": "wizard",
                           "slot_level": 0,
                           "target_combatant_ids": ["x"]}),
    ("cast_web", {"character_id": 1, "class_slug": "wizard",
                  "slot_level": 0}),
]


@pytest.mark.parametrize("endpoint,body", _ENDPOINTS)
async def test_slot_level_zero_returns_400(gm_client, endpoint, body):
    """Each backfilled endpoint returns 400 (not 409) when called
    with slot_level: 0. The pre-v2.99.171 falsy-zero bug masked
    the "slot_level must be >= N" gate, returning 409 instead.
    """
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/{endpoint}",
        json=body,
    )
    assert resp.status_code == 400, (
        f"{endpoint} should 400 on slot_level=0 (post-v2.99.171 fix); "
        f"got {resp.status_code}: {resp.text[:200]}"
    )
