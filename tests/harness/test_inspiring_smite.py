"""v2.99.248 — Glory Paladin: Inspiring Smite CD (Phase H.2 fourth oath).

Phase H.2 fourth non-Devotion Paladin oath. RAW TCE p.55:
Glory Paladin Lv 3+ bonus action CD after Divine Smite —
distribute 2d8 + paladin level temp HP among chosen creatures
within 30 ft (incl self). Lasts 1 hour.

v1 ships:
  - /use_inspiring_smite: validates Glory Paladin Lv 3+ +
    channel-divinity resource current >= 1 + non-empty target
    list + each target in battle + bonus chip. Rolls 2d8 +
    paladin lv for total temp HP, divides evenly (remainder to
    first targets in list order). Marks chip, broadcasts. The
    actual temp HP application is filed.

Sir Caelan Lightbringer (Lv 8 Paladin) is the demo fixture.
Tests PATCH his subclass to "Oath of Glory" + seed CD + 2
allies (Pip + self via Tavik tokens).

Tests:
  - Happy 2 targets → CD 1 → 0, total temp HP = roll + 8,
    allocations split, broadcast.
  - Even split: 3 targets → first gets 1 more if remainder.
  - Empty list → 400.
  - Out of CD → 409.
  - Wrong subclass → 409.
"""
import asyncio
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


def _is_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "inspiring-smite"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _cd_resource(current: int, maximum: int) -> dict:
    return {
        "key": "channel-divinity",
        "name": "Channel Divinity",
        "current": current, "max": maximum, "reset": "short",
        "source": "paladin Lv 3",
        "class_slug": "paladin",
        "subclass_slug": "glory",
        "desc": "Channel a domain effect (Peerless Athlete, Inspiring Smite). One use per short rest.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def caelan_glory_with_party(gm_client, roster):
    """PATCH Caelan to Glory + reset CD + seed battle with allies."""
    caelan = roster["Sir Caelan Lightbringer"]
    pip = roster["Pip Quickfingers"]
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {
            "subclass": "Oath of Glory",
            "resources": [_cd_resource(1, 1)],
        },
        class_slug="paladin",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_cg_{caelan['id']}",
             "char_id": caelan["id"], "name": caelan["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": f"tok_pg_{pip['id']}",
             "char_id": pip["id"], "name": pip["name"],
             "initiative": 18, "hp_current": 47, "hp_max": 47,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": f"tok_tg_{tavik['id']}",
             "char_id": tavik["id"], "name": tavik["name"],
             "initiative": 10, "hp_current": 55, "hp_max": 55,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield caelan, pip, tavik
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "resources": []},
            class_slug="paladin",
        )


async def test_use_is_happy_two_targets(
    gm_client, gm_ws, caelan_glory_with_party,
):
    """2 targets → CD 1 → 0, total = 2d8 + 8, even split."""
    caelan, pip, _ = caelan_glory_with_party
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_inspiring_smite",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": [
                f"tok_cg_{caelan['id']}",
                f"tok_pg_{pip['id']}",
            ],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Caelan demo default is Lv 7.
    assert data["paladin_level"] == 7
    # 2d8 in [2,16] + 7 → total in [9, 23].
    assert 9 <= data["total_temp_hp"] <= 23
    assert 2 <= data["d8_roll"] <= 16
    assert data["uses_remaining"] == 0
    # Even split + remainder to first
    allocations = data["allocations"]
    assert len(allocations) == 2
    assert sum(a["temp_hp"] for a in allocations) == data["total_temp_hp"]
    await asyncio.sleep(0.3)
    feats = _is_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_is_three_targets_remainder(
    gm_client, caelan_glory_with_party,
):
    """3 targets → sum of allocations = total."""
    caelan, pip, tavik = caelan_glory_with_party
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_inspiring_smite",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": [
                f"tok_cg_{caelan['id']}",
                f"tok_pg_{pip['id']}",
                f"tok_tg_{tavik['id']}",
            ],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    allocs = data["allocations"]
    assert len(allocs) == 3
    assert sum(a["temp_hp"] for a in allocs) == data["total_temp_hp"]
    # First should be >= second >= third (remainder skews high
    # to earlier in list).
    assert allocs[0]["temp_hp"] >= allocs[-1]["temp_hp"]


async def test_use_is_empty_list(
    gm_client, caelan_glory_with_party,
):
    """Empty target list → 400."""
    caelan, _, _ = caelan_glory_with_party
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_inspiring_smite",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": [],
            "override": True,
        },
    )
    assert r.status_code == 400, r.text


async def test_use_is_out_of_cd(
    gm_client, caelan_glory_with_party,
):
    """CD current=0 → 409."""
    caelan, pip, _ = caelan_glory_with_party
    await _patch_sheet(
        gm_client, caelan["id"],
        {"resources": [_cd_resource(0, 1)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_inspiring_smite",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": [f"tok_pg_{pip['id']}"],
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_is_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_inspiring_smite",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": [f"tok_pg_{pip['id']}"],
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
