"""v2.99.237 — Trickery Domain Cleric: Blessing of the Trickster (Phase H.1 fourth domain).

Phase H.1 fourth non-Life Cleric domain ship. RAW PHB p.62:
Trickery Lv 1 action — touch a willing creature OTHER than
yourself; advantage on Dex (Stealth) for 1 hour or until
recast. No daily cap (no resource).

v1 ships:
  - /use_blessing_of_the_trickster: validates Trickery Cleric
    Lv 1+ + target_combatant_id in battle + non-self + action
    chip. Installs `blessing-of-the-trickster` buff with
    stealth_advantage + stealth_bonus 5 (advantage proxy for
    the v2.99.214 /roll consumer). Marks action chip,
    broadcasts.

Brother Tavik Stonebrow is the demo fixture. Tests PATCH his
subclass to "Trickery Domain" and seed Tavik + Pip in a battle
so Pip can be the target.

Tests:
  - Happy → buff installed on Pip + broadcast.
  - Self-target → 409 self_targeting_not_allowed.
  - Target not in battle → 404 target_not_in_battle.
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


def _bt_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "blessing-of-the-trickster"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_trickery_with_pip(gm_client, roster):
    """PATCH Tavik to Trickery + seed Tavik+Pip in a fresh battle."""
    tavik = roster["Brother Tavik Stonebrow"]
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Trickery Domain"},
        class_slug="cleric",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_tav_{tavik['id']}",
             "char_id": tavik["id"], "name": tavik["name"],
             "initiative": 10, "hp_current": 55, "hp_max": 55,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": f"tok_pip_{pip['id']}",
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


async def test_use_botrickster_happy(
    gm_client, gm_ws, tavik_trickery_with_pip,
):
    """Trickery Tavik touches Pip → buff installed + broadcast."""
    tavik, pip = tavik_trickery_with_pip
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blessing_of_the_trickster",
        json={
            "character_id": tavik["id"],
            "target_combatant_id": f"tok_pip_{pip['id']}",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["target_char_id"] == pip["id"]
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _bt_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_botrickster_self_target(
    gm_client, tavik_trickery_with_pip,
):
    """Self-target → 409 self_targeting_not_allowed (RAW: 'other
    than yourself')."""
    tavik, _ = tavik_trickery_with_pip
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blessing_of_the_trickster",
        json={
            "character_id": tavik["id"],
            "target_combatant_id": f"tok_tav_{tavik['id']}",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "self_targeting_not_allowed"


async def test_use_botrickster_target_not_in_battle(
    gm_client, tavik_trickery_with_pip,
):
    """Unknown target_combatant_id → 404."""
    tavik, _ = tavik_trickery_with_pip
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blessing_of_the_trickster",
        json={
            "character_id": tavik["id"],
            "target_combatant_id": "tok_unknown_xyz",
            "override": True,
        },
    )
    assert r.status_code == 404, r.text
    data = r.json()
    assert data.get("error") == "target_not_in_battle"


async def test_use_botrickster_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409 wrong_subclass_or_level."""
    tavik = roster["Brother Tavik Stonebrow"]
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blessing_of_the_trickster",
        json={
            "character_id": tavik["id"],
            "target_combatant_id": f"tok_pip_{pip['id']}",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
