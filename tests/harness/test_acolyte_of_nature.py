"""v2.99.239 — Nature Domain Cleric: Acolyte of Nature (Phase H.1 sixth domain).

Phase H.1 sixth non-Life Cleric domain ship. RAW PHB p.61:
Nature Cleric Lv 1+ one-time picker — 1 druid cantrip + 1
skill from {Animal Handling, Nature, Survival}. v1 records the
picks; appending to sheet.spells + adding skill proficiency
filed for follow-up.

Brother Tavik Stonebrow is the demo fixture; tests PATCH his
subclass to "Nature Domain".

Tests:
  - Happy: cantrip + valid skill → persisted, broadcast.
  - Bad skill (Arcana) → 400.
  - Missing cantrip → 400.
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


def _aon_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "acolyte-of-nature"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_nature_domain(gm_client, roster):
    """PATCH Tavik to Nature Domain + reset acolyte_of_nature."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Nature Domain", "acolyte_of_nature": {}},
        class_slug="cleric",
    )
    try:
        yield tavik
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "acolyte_of_nature": {}},
            class_slug="cleric",
        )


async def test_select_aon_happy(
    gm_client, gm_ws, tavik_nature_domain,
):
    """Nature Tavik picks Druidcraft + Survival."""
    tavik = tavik_nature_domain
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_acolyte_of_nature",
        json={
            "character_id": tavik["id"],
            "cantrip": "Druidcraft",
            "skill": "Survival",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["cantrip"] == "Druidcraft"
    assert data["skill"] == "survival"
    await asyncio.sleep(0.3)
    feats = _aon_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_select_aon_bad_skill(
    gm_client, tavik_nature_domain,
):
    """Arcana isn't in {Animal Handling, Nature, Survival} → 400."""
    tavik = tavik_nature_domain
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_acolyte_of_nature",
        json={
            "character_id": tavik["id"],
            "cantrip": "Druidcraft",
            "skill": "Arcana",
        },
    )
    assert r.status_code == 400, r.text


async def test_select_aon_missing_cantrip(
    gm_client, tavik_nature_domain,
):
    """Empty cantrip → 400."""
    tavik = tavik_nature_domain
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_acolyte_of_nature",
        json={
            "character_id": tavik["id"],
            "cantrip": "",
            "skill": "Nature",
        },
    )
    assert r.status_code == 400, r.text


async def test_select_aon_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409 wrong_subclass_or_level."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_acolyte_of_nature",
        json={
            "character_id": tavik["id"],
            "cantrip": "Druidcraft",
            "skill": "Survival",
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
