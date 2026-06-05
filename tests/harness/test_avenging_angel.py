"""v2.99.289 — Vengeance Paladin: Avenging Angel (H.2 deeper, Lv 20).

H.2 Lv 20 Vengeance ship. RAW PHB p.88: action to transform
1 hour. Gain wings + fly 60 ft, plus 30 ft frightful aura
(Wis save DC 8 + prof + CHA on first enter or turn start, or
become frightened 1 min / until damaged; advantage vs
frightened). Once per long rest.

v1 announce-only — wings/fly, aura, frightened install
GM-tracked. Costs action chip. Auto-bootstraps an
`avenging-angel` resource if missing; refilled by long rest.

Caelan PATCH'd to Lv 20: prof_bonus is a separate field that
doesn't auto-update on level PATCH, so it stays at its demo
default of 3. CHA 16 → mod 3. DC = 8 + 3 + 3 = 14.

Tests:
  - Lv 20 happy → save_dc 14, fly_speed_ft 60,
    aura_radius_ft 30, duration 60 min.
  - Wrong subclass → 409.
  - Level gate (Lv 19) → 409.
  - Long rest refills → second call after rest → 200.
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


def _aa_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "avenging-angel"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_vengeance_lv20(gm_client, roster):
    """PATCH Caelan to Vengeance Lv 20 + long-rest."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Vengeance", "level": 20},
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


async def test_use_aa_happy_lv20(
    gm_client, gm_ws, caelan_vengeance_lv20,
):
    """Lv 20 Vengeance, prof 3 (stale) + CHA 16 → DC 14."""
    caelan = caelan_vengeance_lv20
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_avenging_angel",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["save_dc"] == 14
    assert data["fly_speed_ft"] == 60
    assert data["aura_radius_ft"] == 30
    assert data["duration_minutes"] == 60
    assert data["uses_remaining"] == 0
    assert data["paladin_level"] == 20
    await asyncio.sleep(0.3)
    feats = _aa_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_aa_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion Lv 7) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_avenging_angel",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_aa_level_gate(
    gm_client, roster,
):
    """Vengeance Caelan at Lv 19 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Vengeance", "level": 19},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_avenging_angel",
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


async def test_use_aa_long_rest_refills(
    gm_client, caelan_vengeance_lv20,
):
    """Use → long rest → use again → 200."""
    caelan = caelan_vengeance_lv20
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_avenging_angel",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r1.status_code == 200, r1.text
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_avenging_angel",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["uses_remaining"] == 0
