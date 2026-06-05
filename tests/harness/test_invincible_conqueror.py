"""v2.99.290 — Conquest Paladin: Invincible Conqueror (H.2 deeper, Lv 20).

H.2 Lv 20 Conquest ship. RAW XGE p.37: action to become an
avatar of conquest for 1 minute. Gain resistance to all
damage, +1 extra attack on Attack action, melee crits on
19-20. Once per long rest.

v1 announce-only — resistance, extra attack, expanded crit
range are GM-tracked. Costs action chip. Auto-bootstraps an
`invincible-conqueror` resource; refilled by long rest.

Tests:
  - Lv 20 happy → resistance_all_damage True, extra_attack 1,
    crit_range_min 19, duration 1 min.
  - Wrong subclass → 409.
  - Level gate (Lv 19) → 409.
  - Long rest refills → 200 after rest.
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


def _ic_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "invincible-conqueror"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_conquest_lv20(gm_client, roster):
    """PATCH Caelan to Conquest Lv 20 + long-rest."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Conquest", "level": 20},
        class_slug="paladin",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_use_ic_happy_lv20(
    gm_client, gm_ws, caelan_conquest_lv20,
):
    """Lv 20 Conquest → resist all, +1 attack, crit 19-20, 1 min."""
    caelan = caelan_conquest_lv20
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_invincible_conqueror",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["resistance_all_damage"] is True
    assert data["extra_attack"] == 1
    assert data["crit_range_min"] == 19
    assert data["duration_minutes"] == 1
    assert data["uses_remaining"] == 0
    assert data["paladin_level"] == 20
    await asyncio.sleep(0.3)
    feats = _ic_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_ic_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion Lv 7) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_invincible_conqueror",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ic_level_gate(
    gm_client, roster,
):
    """Conquest Caelan at Lv 19 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Conquest", "level": 19},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_invincible_conqueror",
            json={"character_id": caelan["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_use_ic_long_rest_refills(
    gm_client, caelan_conquest_lv20,
):
    """Use → long rest → use again → 200."""
    caelan = caelan_conquest_lv20
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_invincible_conqueror",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r1.status_code == 200, r1.text
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_invincible_conqueror",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["uses_remaining"] == 0
