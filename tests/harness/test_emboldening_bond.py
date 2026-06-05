"""v2.99.243 — Peace Domain Cleric: Emboldening Bond (Phase H.1 tenth domain).

Phase H.1 tenth non-Life Cleric domain ship. RAW TCE p.40:
Peace Cleric Lv 1+ action — forge a magical bond among up to
prof-bonus creatures. While within 30 ft of one another, each
can add 1d4 to one attack/check/save. Lasts 1 hour.

v1 ships:
  - /use_emboldening_bond: validates Peace Cleric Lv 1+ +
    target list non-empty + count <= sheet.proficiency_bonus +
    each target in battle + action chip. Installs
    emboldening-bond-active buff on each target with
    bonus_d4: True. Marks chip, broadcasts.

The 30-ft proximity check is filed (no automatic enforcement).
The 1-minute ritual is dropped — v1 is a single action.

Brother Tavik Stonebrow is the demo fixture (prof +3 at Lv 8).
Tests seed Tavik + Pip + Caelan + Zara in a battle.

Tests:
  - Happy 2 targets → buffs installed + broadcast.
  - Too many targets (4 with prof 3) → 409.
  - Unknown target → 404.
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


def _eb_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "emboldening-bond"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_peace_with_party(gm_client, roster):
    """PATCH Tavik to Peace + seed Tavik + Pip + Caelan + Zara
    in a battle. Tavik prof +3 → can bond 3."""
    tavik = roster["Brother Tavik Stonebrow"]
    pip = roster["Pip Quickfingers"]
    caelan = roster["Sir Caelan Lightbringer"]
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Peace Domain"},
        class_slug="cleric",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_tp_{tavik['id']}",
             "char_id": tavik["id"], "name": tavik["name"],
             "initiative": 10, "hp_current": 55, "hp_max": 55,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": f"tok_pp_{pip['id']}",
             "char_id": pip["id"], "name": pip["name"],
             "initiative": 18, "hp_current": 47, "hp_max": 47,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": f"tok_cp_{caelan['id']}",
             "char_id": caelan["id"], "name": caelan["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": f"tok_zp_{zara['id']}",
             "char_id": zara["id"], "name": zara["name"],
             "initiative": 14, "hp_current": 36, "hp_max": 36,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield tavik, pip, caelan, zara
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain"},
            class_slug="cleric",
        )


async def test_use_eb_two_targets_happy(
    gm_client, gm_ws, tavik_peace_with_party,
):
    """Bond 2 targets → buffs installed + broadcast."""
    tavik, pip, caelan, _ = tavik_peace_with_party
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_emboldening_bond",
        json={
            "character_id": tavik["id"],
            "target_combatant_ids": [
                f"tok_pp_{pip['id']}",
                f"tok_cp_{caelan['id']}",
            ],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["bonded_char_ids"]) == 2
    assert pip["id"] in data["bonded_char_ids"]
    assert caelan["id"] in data["bonded_char_ids"]
    assert data["max_allowed"] == 3
    await asyncio.sleep(0.3)
    feats = _eb_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_eb_too_many_targets(
    gm_client, tavik_peace_with_party,
):
    """4 targets with prof 3 → 409 too_many_targets."""
    tavik, pip, caelan, zara = tavik_peace_with_party
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_emboldening_bond",
        json={
            "character_id": tavik["id"],
            "target_combatant_ids": [
                f"tok_tp_{tavik['id']}",
                f"tok_pp_{pip['id']}",
                f"tok_cp_{caelan['id']}",
                f"tok_zp_{zara['id']}",
            ],
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "too_many_targets"
    assert data.get("max") == 3
    assert data.get("got") == 4


async def test_use_eb_unknown_target(
    gm_client, tavik_peace_with_party,
):
    """Unknown target → 404."""
    tavik, pip, _, _ = tavik_peace_with_party
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_emboldening_bond",
        json={
            "character_id": tavik["id"],
            "target_combatant_ids": [
                f"tok_pp_{pip['id']}",
                "tok_ghost",
            ],
            "override": True,
        },
    )
    assert r.status_code == 404, r.text
    data = r.json()
    assert data.get("error") == "target_not_in_battle"


async def test_use_eb_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_emboldening_bond",
        json={
            "character_id": tavik["id"],
            "target_combatant_ids": [f"tok_pp_{pip['id']}"],
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
