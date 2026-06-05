"""v2.99.238 — Knowledge Domain Cleric: Blessings of Knowledge (Phase H.1 fifth domain).

Phase H.1 fifth non-Life Cleric domain ship. RAW PHB p.59:
Knowledge Cleric Lv 1+ one-time pick — 2 skills from {Arcana,
History, Nature, Religion} (doubled prof / expertise) + 2
languages. v1 records the picks; expertise wiring is filed for
a follow-up commit.

Brother Tavik Stonebrow is the demo fixture; tests PATCH his
subclass to "Knowledge Domain".

Tests:
  - Happy: 2 skills + 2 languages → persisted, broadcast.
  - Bad skill (not in PHB list) → 400.
  - Wrong size (1 skill) → 400.
  - Duplicate skills → 400.
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


def _bok_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "blessings-of-knowledge"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_knowledge_domain(gm_client, roster):
    """PATCH Tavik to Knowledge Domain + reset knowledge_blessings."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Knowledge Domain", "knowledge_blessings": {}},
        class_slug="cleric",
    )
    try:
        yield tavik
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "knowledge_blessings": {}},
            class_slug="cleric",
        )


async def test_select_bok_happy(
    gm_client, gm_ws, tavik_knowledge_domain,
):
    """Knowledge Tavik picks Arcana + Religion + Celestial + Draconic."""
    tavik = tavik_knowledge_domain
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_knowledge_blessings",
        json={
            "character_id": tavik["id"],
            "skills": ["Arcana", "Religion"],
            "languages": ["Celestial", "Draconic"],
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["skills"] == ["arcana", "religion"]
    assert data["languages"] == ["Celestial", "Draconic"]
    await asyncio.sleep(0.3)
    feats = _bok_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_select_bok_bad_skill(
    gm_client, tavik_knowledge_domain,
):
    """Athletics isn't in the PHB Knowledge skill list → 400."""
    tavik = tavik_knowledge_domain
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_knowledge_blessings",
        json={
            "character_id": tavik["id"],
            "skills": ["Arcana", "Athletics"],
            "languages": ["Celestial", "Draconic"],
        },
    )
    assert r.status_code == 400, r.text


async def test_select_bok_wrong_count(
    gm_client, tavik_knowledge_domain,
):
    """1 skill → 400."""
    tavik = tavik_knowledge_domain
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_knowledge_blessings",
        json={
            "character_id": tavik["id"],
            "skills": ["Arcana"],
            "languages": ["Celestial", "Draconic"],
        },
    )
    assert r.status_code == 400, r.text


async def test_select_bok_duplicate_skills(
    gm_client, tavik_knowledge_domain,
):
    """Arcana + Arcana → 400."""
    tavik = tavik_knowledge_domain
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_knowledge_blessings",
        json={
            "character_id": tavik["id"],
            "skills": ["Arcana", "Arcana"],
            "languages": ["Celestial", "Draconic"],
        },
    )
    assert r.status_code == 400, r.text


async def test_select_bok_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409 wrong_subclass_or_level."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_knowledge_blessings",
        json={
            "character_id": tavik["id"],
            "skills": ["Arcana", "Religion"],
            "languages": ["Celestial", "Draconic"],
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
