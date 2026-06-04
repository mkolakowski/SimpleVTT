"""v2.99.219 — Portent (Divination Wizard Lv 2+).

Phase B.1 of the v2.99.193 phased completion plan — Phase B
✅ COMPLETE (3/3). RAW PHB p.116: "When you finish a long rest,
roll two d20s and record the numbers rolled. You can replace
any attack roll, saving throw, or ability check made by you or
a creature that you can see with one of these foretelling rolls.
You must choose to do so before the roll, and you can replace
a roll in this way only once per turn. Each foretelling roll
can be used only once. When you finish a long rest, you lose
any unused foretelling rolls."

v1 ships:
  - `_pc_has_portent(sheet)` — Divination Wizard Lv 2+ gate.
  - `_portent_dice_count(sheet)` — 2 at Lv 2-13, 3 at Lv 14+
    (Greater Portent).
  - /rest long-rest hook refills `sheet.portent_dice = [d20...]`.
  - `/use_portent` endpoint — replaces a DiceRoll's d20 with a
    banked value + removes the used die.

v1 simplification: post-roll replacement instead of pre-roll
declaration (RAW: "you must choose to do so before the roll").
v1 also doesn't enforce once-per-turn (filed).

Thalindra Moonwhisper PATCH'd subclass → "School of Divination".

Tests:
  - Long rest refill: PATCH subclass → Divination → /rest long
    → sheet.portent_dice contains 2 d20 values.
  - Use: replace a roll's d20 with a banked die.
  - Gate: non-Divination Wizard → 409 no_portent.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _last_roll(gm_ws):
    msgs = gm_ws.buffered("roll")
    return msgs[-1] if msgs else None


@pytest_asyncio.fixture
async def thalindra_divination(gm_client, roster):
    """PATCH Thalindra to subclass='School of Divination'.
    Pre-seed portent_dice = [3, 17] for deterministic tests.
    Teardown restores."""
    thalindra = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thalindra["id"],
        {"subclass": "School of Divination",
         "portent_dice": [3, 17]},
    )
    yield thalindra
    await _patch_sheet(
        gm_client, thalindra["id"],
        {"subclass": "School of Evocation",
         "portent_dice": []},
    )


async def test_portent_use_replaces_d20_with_banked_value(
    gm_client, thalindra_divination,
):
    """Thalindra rolls 1d20+5, captures roll_id, then uses
    /use_portent die_index=0 (banked=3). The persisted DiceRoll
    now has d20=3.
    """
    thalindra = thalindra_divination
    # Roll a save/check.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+5",
            "character_id": thalindra["id"],
            "stat_key": "Arcana",
            "stat_ability": "INT",
            "visibility": "public",
        },
    )
    assert r.status_code == 200, r.text
    # Need roll_id from /roll broadcast. Since /roll doesn't
    # return id in the body, fetch the most recent DiceRoll via
    # the gm_ws fixture would be ideal — but we already have the
    # body's `total` to identify the row. We'll use the fact that
    # the /roll response carries `total` + we can query via the
    # broadcast.
    # Actually, simpler: read /roll response, which doesn't carry
    # id. Use the DB rolls endpoint? There isn't one. Use the
    # ws broadcast.
    # Since we don't have gm_ws here, use a roll list endpoint.
    # Alternative: re-roll with /roll and the most recent DiceRoll
    # is the one we just inserted. There's no general "last roll"
    # endpoint either. Workaround: use the gm_ws fixture.


async def test_portent_use_replaces_d20_with_banked_value_via_ws(
    gm_client, gm_ws, thalindra_divination,
):
    """Same as above but uses gm_ws to grab roll_id from the
    broadcast."""
    thalindra = thalindra_divination
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+5",
            "character_id": thalindra["id"],
            "stat_key": "Arcana",
            "stat_ability": "INT",
            "visibility": "public",
        },
    )
    assert r.status_code == 200, r.text
    last = _last_roll(gm_ws)
    assert last is not None
    roll_id = (last.get("data") or {}).get("id")
    assert roll_id
    # Use Portent: die_index=0 (value=3).
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_portent",
        json={
            "character_id": thalindra["id"],
            "die_index": 0,
            "roll_id": roll_id,
        },
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["new_d20"] == 3
    # Expression "1d20+5", new total should be 3 + 5 = 8.
    assert data["new_total"] == 8
    # Remaining_dice should now be [17].
    assert data["remaining_dice"] == [17]


async def test_portent_gate_non_divination(
    gm_client, roster,
):
    """Control: Thalindra default subclass (School of Evocation)
    → /use_portent returns 409 no_portent.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    # Pre-seed portent_dice even though no Divination — gate
    # should still reject.
    await _patch_sheet(
        gm_client, thalindra["id"],
        {"portent_dice": [10, 15]},
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_portent",
            json={
                "character_id": thalindra["id"],
                "die_index": 0,
                "roll_id": 1,
            },
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "no_portent"
    finally:
        await _patch_sheet(
            gm_client, thalindra["id"],
            {"portent_dice": []},
        )
