"""v2.99.332 — Necromancy Wizard: Grim Harvest (G.1 batch, Lv 2+).

G.1 Wizard subclass batch ship #6. RAW PHB p.118: once per
turn, on killing a creature with a Lv 1+ spell, regain HP =
2 × spell level, or 3 × spell level if spell is necromancy.
Doesn't apply to constructs or undead.

v1 announce-only — HP gain GM-applied via existing /heal flow.
No chip — passive on kill.

Tests:
  - Lv 7 happy spell_level=3 non-necromancy → heal 6.
  - spell_level=3 + is_necromancy=true → heal 9.
  - spell_level missing → default 1.
  - Wrong subclass → 409.
  - Necromancy Lv 1 → 409.
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


def _gh_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "grim-harvest"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def thalindra_necromancy(gm_client, roster):
    """PATCH Thalindra to School of Necromancy."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "School of Necromancy"},
        class_slug="wizard",
    )
    try:
        yield thal
    finally:
        await _patch_sheet(
            gm_client, thal["id"],
            {"subclass": "School of Evocation", "level": 7},
            class_slug="wizard",
        )


async def test_use_gh_happy_lv7_lv3_spell(
    gm_client, gm_ws, thalindra_necromancy,
):
    """Lv 7 Necromancy, spell_level 3 non-necromancy → heal 6."""
    thal = thalindra_necromancy
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_grim_harvest",
        json={"character_id": thal["id"], "spell_level": 3},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["heal_amount"] == 6
    assert data["spell_level"] == 3
    assert data["is_necromancy"] is False
    assert data["wizard_level"] == 7
    await asyncio.sleep(0.3)
    feats = _gh_broadcasts(gm_ws, thal["id"])
    assert feats


async def test_use_gh_necromancy_spell(
    gm_client, thalindra_necromancy,
):
    """spell_level=3, is_necromancy=true → heal 9."""
    thal = thalindra_necromancy
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_grim_harvest",
        json={"character_id": thal["id"], "spell_level": 3, "is_necromancy": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["heal_amount"] == 9
    assert data["is_necromancy"] is True


async def test_use_gh_default_spell_level(
    gm_client, thalindra_necromancy,
):
    """Missing spell_level → default 1 → heal 2."""
    thal = thalindra_necromancy
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_grim_harvest",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["spell_level"] == 1
    assert data["heal_amount"] == 2


async def test_use_gh_wrong_subclass(
    gm_client, roster,
):
    """Default Thalindra (Evocation) → 409."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_grim_harvest",
        json={"character_id": thal["id"], "spell_level": 3},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_gh_level_gate(
    gm_client, roster,
):
    """Necromancy Thalindra at Lv 1 → 409."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "School of Necromancy", "level": 1},
        class_slug="wizard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_grim_harvest",
            json={"character_id": thal["id"], "spell_level": 3},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, thal["id"],
            {"subclass": "School of Evocation", "level": 7},
            class_slug="wizard",
        )
