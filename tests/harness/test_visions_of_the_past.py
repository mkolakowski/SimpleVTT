"""v2.99.301 — Knowledge Domain Cleric: Visions of the Past (H.1 deeper, Lv 17).

H.1 Lv 17 Knowledge ship. RAW PHB p.60: 1 min meditation,
then dream-like glimpses of recent events. Concentration up
to WIS-score minutes (min 1). Once per short or long rest.

Modes:
- Object Reading: hold object → 24h history + who used it.
- Area Reading: 50-ft cube → 24h history.

v1 announce-only — actual vision content is GM/DM-narrated.
Auto-bootstraps `visions-of-the-past` resource (max=1,
reset=short).

Tavik default WIS 16 → max_duration 16 minutes.

Tests:
  - Lv 17 object mode → mode "object", duration 16 min.
  - Lv 17 area mode → mode "area", duration 16 min.
  - Default missing mode → "object".
  - Wrong subclass → 409.
  - Level gate (Lv 16) → 409.
  - Out of uses → 409 (back-to-back).
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


def _vp_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "visions-of-the-past"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_knowledge_lv17(gm_client, roster):
    """PATCH Tavik to Knowledge Domain Lv 17 + long-rest."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Knowledge Domain", "level": 17},
        class_slug="cleric",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    try:
        yield tavik
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_use_vp_object_mode(
    gm_client, gm_ws, tavik_knowledge_lv17,
):
    """Lv 17 Knowledge, object mode → duration 16."""
    tavik = tavik_knowledge_lv17
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_visions_of_the_past",
        json={"character_id": tavik["id"], "mode": "object"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "object"
    assert data["max_duration_minutes"] == 16
    assert data["uses_remaining"] == 0
    assert data["cleric_level"] == 17
    await asyncio.sleep(0.3)
    feats = _vp_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_vp_area_mode(
    gm_client, tavik_knowledge_lv17,
):
    """Area mode → mode 'area'."""
    tavik = tavik_knowledge_lv17
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_visions_of_the_past",
        json={"character_id": tavik["id"], "mode": "area"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "area"


async def test_use_vp_default_mode(
    gm_client, tavik_knowledge_lv17,
):
    """Missing mode → defaults to 'object'."""
    tavik = tavik_knowledge_lv17
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_visions_of_the_past",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "object"


async def test_use_vp_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_visions_of_the_past",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_vp_level_gate(
    gm_client, roster,
):
    """Knowledge Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Knowledge Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_visions_of_the_past",
            json={"character_id": tavik["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_use_vp_out_of_uses(
    gm_client, tavik_knowledge_lv17,
):
    """Back-to-back → 409 no_uses_left."""
    tavik = tavik_knowledge_lv17
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_visions_of_the_past",
        json={"character_id": tavik["id"]},
    )
    assert r1.status_code == 200, r1.text
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_visions_of_the_past",
        json={"character_id": tavik["id"]},
    )
    assert r2.status_code == 409, r2.text
    data = r2.json()
    assert data.get("error") == "no_uses_left"
