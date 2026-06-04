"""v2.99.199 — Indomitable post-fail reroll (Fighter Lv 9+).

Phase C.1 of the v2.99.193 phased completion plan. Mirror of the
v2.56.0 pre-roll advantage simplification (`/use_indomitable`) for
the RAW post-fail reroll path. v2.56.0's endpoint stays for the
"prep advantage on the next save" workflow; v2.99.199 closes the
RAW post-fail reroll.

RAW (PHB p.72): "When you make a saving throw and fail, you can
spend one use of Indomitable to reroll the new roll, and you must
use the new roll." 1/long rest at Lv 9, 2 at Lv 13, 3 at Lv 17.

Tests:
  - Happy path: Garrik (Fighter) rolls a d20 (low result via
    dice seed), captures the roll_id, calls /use_indomitable_reroll
    → verify the DiceRoll's breakdown + total are now different
    (the d20 was rerolled) + resource decremented + broadcasts.
  - Gate: Fighter Lv 7 → 409 level_too_low.
  - Gate: roll_id 0 → 400.
  - Gate: out of uses → 409.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _seed_dice(gm_client, seed: int):
    r = await gm_client.post(
        "/api/test/dice/seed", json={"seed": seed},
    )
    assert r.status_code == 200, r.text


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


def _indomitable_reroll_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "indomitable-reroll"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def garrik_lv9_with_indomitable(gm_client, roster):
    """PATCH Garrik to Lv 9 + ensure the indomitable resource is
    present + at full. Restore Lv 7 + empty resources in teardown.
    Garrik defaults to Lv 7 (per v2.56.0 demo seed); v2.99.27
    bumped him to Lv 9 in the wielding-polearm-master demo. This
    test brings him up via PATCH for consistency across demos.
    """
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"], {"level": 9}, class_slug="fighter",
    )
    ind_row = {
        "key": "indomitable",
        "label": "Indomitable",
        "current": 1, "max": 1,
        "reset": "long",
    }
    await _patch_sheet(
        gm_client, garrik["id"], {"resources": [ind_row]},
    )
    yield garrik
    await _patch_sheet(
        gm_client, garrik["id"], {"level": 7}, class_slug="fighter",
    )
    await _patch_sheet(
        gm_client, garrik["id"], {"resources": []},
    )


async def test_indomitable_reroll_happy_path(
    gm_client, gm_ws, garrik_lv9_with_indomitable,
):
    """Garrik (Lv 9, indomitable=1) rolls a save → captures
    roll_id → calls /use_indomitable_reroll → verify the persisted
    DiceRoll was mutated + resource decremented + broadcasts fire.
    """
    garrik = garrik_lv9_with_indomitable
    # Roll a save. Use a deterministic seed so we know the original
    # d20 value for comparison.
    await _seed_dice(gm_client, 42)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+2",
            "character_id": garrik["id"],
            "stat_key": "wis_save",
            "visibility": "public",
        },
    )
    assert r.status_code == 200, r.text
    first_data = r.json()
    first_total = int(first_data.get("total") or 0)
    # The dice_mod's roll record ID isn't in the /roll response —
    # we need to grab it from the broadcast (last roll msg).
    last_msg = _last_roll(gm_ws)
    assert last_msg is not None
    roll_id = (last_msg.get("data") or {}).get("id")
    assert roll_id, f"expected roll_id on /roll broadcast; got {last_msg}"
    # Seed a different dice value for the reroll.
    await _seed_dice(gm_client, 1000)
    gm_ws.mark()
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_indomitable_reroll",
        json={"character_id": garrik["id"], "roll_id": roll_id},
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["roll_id"] == roll_id
    assert data["old_d20"] is not None
    assert data["new_d20"] is not None
    # The reroll should produce a different total than the original.
    # With two different dice seeds it's overwhelmingly likely.
    assert data["new_total"] != data["old_total"] or data["new_d20"] != data["old_d20"], (
        f"reroll should change something; got old=({data['old_d20']}, "
        f"{data['old_total']}) new=({data['new_d20']}, {data['new_total']})"
    )
    # Resource was decremented.
    assert data["remaining"] == 0
    assert data["max"] == 1
    # Broadcasts fired.
    feats = _indomitable_reroll_broadcasts(gm_ws, garrik["id"])
    assert feats, (
        f"expected feature_used(source=indomitable-reroll); "
        f"buffered={gm_ws.buffered()}"
    )
    # Roll broadcast carries the indomitable_reroll flag.
    roll_msgs = gm_ws.buffered("roll")
    reroll_msgs = [
        m for m in roll_msgs
        if (m.get("data") or {}).get("indomitable_reroll")
    ]
    assert reroll_msgs, (
        f"expected a roll broadcast carrying indomitable_reroll=True; "
        f"got {roll_msgs}"
    )


async def test_indomitable_reroll_level_gate(
    gm_client, roster,
):
    """Control: Garrik at Lv 7 (default) → 409 level_too_low."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_indomitable_reroll",
        json={"character_id": garrik["id"], "roll_id": 1},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "level_too_low"


async def test_indomitable_reroll_requires_roll_id(
    gm_client, garrik_lv9_with_indomitable,
):
    """Body must include roll_id; missing → 400."""
    garrik = garrik_lv9_with_indomitable
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_indomitable_reroll",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 400, r.text


async def test_indomitable_reroll_out_of_uses(
    gm_client, roster,
):
    """Gate: Garrik Lv 9 but indomitable current=0 → 409 out_of_uses."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"], {"level": 9}, class_slug="fighter",
    )
    ind_row_empty = {
        "key": "indomitable",
        "label": "Indomitable",
        "current": 0, "max": 1, "reset": "long",
    }
    await _patch_sheet(
        gm_client, garrik["id"], {"resources": [ind_row_empty]},
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_indomitable_reroll",
            json={"character_id": garrik["id"], "roll_id": 1},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "out_of_uses"
    finally:
        await _patch_sheet(
            gm_client, garrik["id"], {"level": 7},
            class_slug="fighter",
        )
        await _patch_sheet(
            gm_client, garrik["id"], {"resources": []},
        )
