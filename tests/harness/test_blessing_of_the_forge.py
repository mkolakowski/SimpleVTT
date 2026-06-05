"""v2.99.240 — Forge Domain Cleric: Blessing of the Forge (Phase H.1 seventh domain).

Phase H.1 seventh non-Life Cleric domain ship. RAW XGE p.18:
Forge Cleric Lv 1+ — at end of long rest, bless one non-magical
weapon or armor; until next long rest or recast, it becomes a
magic item granting +1 attack+damage (weapon) or +1 AC (armor).

v1 ships persistence + announce; the actual +1 application to
weapon attack_bonus / damage or to armor ac_value is filed for
a follow-up commit.

Brother Tavik Stonebrow is the demo fixture. Tavik's inventory:
  0: Warhammer (weapon)
  1: Shield (type 'shield' — not valid for Forge blessing)
  2: Chain mail (armor)
  3: Holy symbol (gear — not valid)

Tests:
  - Happy weapon (Warhammer index 0) → kind 'weapon', broadcast.
  - Happy armor (Chain mail index 2) → kind 'armor'.
  - Shield (index 1) → 400 (not weapon/armor).
  - Wrong subclass → 409.
  - Missing item_index → 400.
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


def _bof_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "blessing-of-the-forge"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_forge_domain(gm_client, roster):
    """PATCH Tavik to Forge Domain + reset blessed_object."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Forge Domain", "blessed_object": {}},
        class_slug="cleric",
    )
    try:
        yield tavik
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "blessed_object": {}},
            class_slug="cleric",
        )


async def test_use_bof_weapon_happy(
    gm_client, gm_ws, tavik_forge_domain,
):
    """Forge Tavik blesses Warhammer (index 0)."""
    tavik = tavik_forge_domain
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blessing_of_the_forge",
        json={"character_id": tavik["id"], "item_index": 0},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["kind"] == "weapon"
    assert data["slug"] == "warhammer"
    await asyncio.sleep(0.3)
    feats = _bof_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_bof_armor_happy(
    gm_client, tavik_forge_domain,
):
    """Forge Tavik blesses Chain mail (index 2)."""
    tavik = tavik_forge_domain
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blessing_of_the_forge",
        json={"character_id": tavik["id"], "item_index": 2},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["kind"] == "armor"
    assert data["slug"] == "chain-mail"


async def test_use_bof_shield_rejected(
    gm_client, tavik_forge_domain,
):
    """Shield (index 1, type 'shield') → 400."""
    tavik = tavik_forge_domain
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blessing_of_the_forge",
        json={"character_id": tavik["id"], "item_index": 1},
    )
    assert r.status_code == 400, r.text


async def test_use_bof_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409 wrong_subclass_or_level."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blessing_of_the_forge",
        json={"character_id": tavik["id"], "item_index": 0},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_bof_missing_item_index(
    gm_client, tavik_forge_domain,
):
    """No item_index → 400."""
    tavik = tavik_forge_domain
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blessing_of_the_forge",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 400, r.text
