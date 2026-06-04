"""v2.99.211 — Diamond Soul ki-spend reroll (Monk Lv 14+).

Phase F.2 final of the v2.99.193 phased completion plan. RAW
PHB p.79: "Additionally, whenever you make a saving throw and
fail, you can spend 1 ki point to reroll it and take the second
result."

Direct mirror of v2.99.199 /use_indomitable_reroll. Validates
Monk Lv 14+ + ki >= 1 + roll_id resolves to a DiceRoll. Rerolls
the d20, mutates the DiceRoll record, broadcasts an updated
`roll` event + feature_used(source="diamond-soul-reroll") +
resource_update.

Kael Brightleaf PATCH'd Lv 7 → 14 + ki seeded for tests.

Tests:
  - Happy: Kael rolls a save → /use_diamond_soul_reroll →
    DiceRoll mutated + ki decremented + broadcasts.
  - Gate: Kael Lv 7 → 409 level_too_low.
  - Gate: Lv 14 + ki=0 → 409 not_enough_ki.
"""
import asyncio
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


def _ds_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "diamond-soul-reroll"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _last_roll(gm_ws):
    msgs = gm_ws.buffered("roll")
    return msgs[-1] if msgs else None


@pytest_asyncio.fixture
async def kael_lv14_with_ki(gm_client, roster):
    """PATCH Kael to Lv 14 + ki 5/15. Restore Lv 7 in teardown."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(
        gm_client, kael["id"], {"level": 14},
        class_slug="monk",
    )
    await _patch_sheet(
        gm_client, kael["id"],
        {"resources": [
            {"key": "ki-points", "label": "Ki Points",
             "current": 5, "max": 15, "reset": "short"},
        ]},
    )
    yield kael
    await _patch_sheet(
        gm_client, kael["id"], {"level": 7},
        class_slug="monk",
    )
    await _patch_sheet(
        gm_client, kael["id"],
        {"resources": [
            {"key": "ki-points", "label": "Ki Points",
             "current": 7, "max": 7, "reset": "short"},
        ]},
    )


async def test_diamond_soul_reroll_happy_path(
    gm_client, gm_ws, kael_lv14_with_ki,
):
    """Kael Lv 14 + ki 5 → roll a save → /use_diamond_soul_reroll →
    DiceRoll mutated + ki decremented + broadcasts.
    """
    kael = kael_lv14_with_ki
    await _seed_dice(gm_client, 42)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+2",
            "character_id": kael["id"],
            "stat_key": "wis_save",
            "visibility": "public",
        },
    )
    assert r.status_code == 200, r.text
    first_data = r.json()
    first_total = int(first_data.get("total") or 0)
    last_msg = _last_roll(gm_ws)
    assert last_msg is not None
    roll_id = (last_msg.get("data") or {}).get("id")
    assert roll_id
    # Reroll.
    await _seed_dice(gm_client, 1000)
    gm_ws.mark()
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_diamond_soul_reroll",
        json={"character_id": kael["id"], "roll_id": roll_id},
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["roll_id"] == roll_id
    assert data["ki_spent"] == 1
    assert data["remaining"] == 4
    assert data["old_d20"] is not None
    assert data["new_d20"] is not None
    # Reroll should change something with different seeds.
    assert (
        data["new_total"] != data["old_total"]
        or data["new_d20"] != data["old_d20"]
    )
    await asyncio.sleep(0.3)
    feats = _ds_broadcasts(gm_ws, kael["id"])
    assert feats, (
        f"v2.99.211: expected feature_used(source=diamond-soul-reroll); "
        f"buffered={gm_ws.buffered()}"
    )


async def test_diamond_soul_reroll_level_gate(
    gm_client, roster,
):
    """Control: Kael Lv 7 → 409 level_too_low."""
    kael = roster["Kael Brightleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_diamond_soul_reroll",
        json={"character_id": kael["id"], "roll_id": 1},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "level_too_low"
    assert data.get("required") == 14


async def test_diamond_soul_reroll_not_enough_ki(
    gm_client, roster,
):
    """Gate: Kael Lv 14 + ki=0 → 409 not_enough_ki."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(
        gm_client, kael["id"], {"level": 14},
        class_slug="monk",
    )
    await _patch_sheet(
        gm_client, kael["id"],
        {"resources": [
            {"key": "ki-points", "label": "Ki Points",
             "current": 0, "max": 15, "reset": "short"},
        ]},
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_diamond_soul_reroll",
            json={"character_id": kael["id"], "roll_id": 1},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "not_enough_ki"
    finally:
        await _patch_sheet(
            gm_client, kael["id"], {"level": 7},
            class_slug="monk",
        )
        await _patch_sheet(
            gm_client, kael["id"],
            {"resources": [
                {"key": "ki-points", "label": "Ki Points",
                 "current": 7, "max": 7, "reset": "short"},
            ]},
        )
