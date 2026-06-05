"""v2.99.242 — Twilight Domain Cleric: Vigilant Blessing (Phase H.1 ninth domain).

Phase H.1 ninth non-Life Cleric domain ship. RAW TCE p.41:
Twilight Cleric Lv 1+ action — give one creature (incl self)
advantage on next initiative roll. No daily cap; "ends when
roll happens or feature used again" filed.

v1 ships:
  - /use_vigilant_blessing: validates Twilight Cleric Lv 1+ +
    target in battle + action chip. Installs vigilant-blessing-
    active buff with init_advantage + consume_on_initiative_roll.
    Marks chip, broadcasts.

Brother Tavik Stonebrow is the demo fixture. Tests PATCH his
subclass to "Twilight Domain" and seed Tavik + Pip in a battle.

Tests:
  - Happy → Tavik blesses Pip → buff installed.
  - Self-target → is_self True, buff installed.
  - Unknown target → 404 target_not_in_battle.
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


def _vb_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "vigilant-blessing"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_twilight_with_pip(gm_client, roster):
    """PATCH Tavik to Twilight + seed Tavik+Pip in a battle."""
    tavik = roster["Brother Tavik Stonebrow"]
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Twilight Domain"},
        class_slug="cleric",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_tw_{tavik['id']}",
             "char_id": tavik["id"], "name": tavik["name"],
             "initiative": 10, "hp_current": 55, "hp_max": 55,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": f"tok_pi_{pip['id']}",
             "char_id": pip["id"], "name": pip["name"],
             "initiative": 18, "hp_current": 47, "hp_max": 47,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield tavik, pip
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain"},
            class_slug="cleric",
        )


async def test_use_vb_target_ally(
    gm_client, gm_ws, tavik_twilight_with_pip,
):
    """Tavik blesses Pip → buff installed + broadcast."""
    tavik, pip = tavik_twilight_with_pip
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_vigilant_blessing",
        json={
            "character_id": tavik["id"],
            "target_combatant_id": f"tok_pi_{pip['id']}",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["target_char_id"] == pip["id"]
    assert data["is_self"] is False
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _vb_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_vb_target_self(
    gm_client, tavik_twilight_with_pip,
):
    """Tavik targets himself → is_self True, buff installed.
    (RAW allows self.)"""
    tavik, _ = tavik_twilight_with_pip
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_vigilant_blessing",
        json={
            "character_id": tavik["id"],
            "target_combatant_id": f"tok_tw_{tavik['id']}",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_self"] is True


async def test_use_vb_target_not_in_battle(
    gm_client, tavik_twilight_with_pip,
):
    """Unknown target → 404."""
    tavik, _ = tavik_twilight_with_pip
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_vigilant_blessing",
        json={
            "character_id": tavik["id"],
            "target_combatant_id": "tok_unknown_xyz",
            "override": True,
        },
    )
    assert r.status_code == 404, r.text


async def test_use_vb_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_vigilant_blessing",
        json={
            "character_id": tavik["id"],
            "target_combatant_id": f"tok_pi_{pip['id']}",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
