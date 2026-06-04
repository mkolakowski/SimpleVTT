"""v2.99.209 — Empty Body (Monk Lv 18+).

Phase F.2 cont'd of the v2.99.193 phased completion plan. RAW
PHB p.79: "Beginning at 18th level, you can use your action to
spend 4 ki points to become invisible for 1 minute. During that
time, you also have resistance to all damage but force damage."

v1 ships the 4-ki invisible variant. The 8-ki astral projection
variant is filed for a future follow-up (cross-plane plumbing
is out of v1 scope).

Tests:
  - Happy: Kael Lv 18 + ki 5 → /use_empty_body → buff installed
    + ki decrements 5 → 1 + broadcasts.
  - Gate: Kael Lv 7 → 409 level_too_low.
  - Gate: Kael Lv 18 + ki 3 → 409 not_enough_ki.
"""
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
        if (m.get("data") or {}).get("source") == "empty-body"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def kael_lv18(gm_client, roster):
    """PATCH Kael to Lv 18 + give him ki-points 5/15. Restore Lv 7
    in teardown."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(
        gm_client, kael["id"], {"level": 18},
        class_slug="monk",
    )
    await _patch_sheet(
        gm_client, kael["id"],
        {"resources": [
            {"key": "ki-points", "label": "Ki Points",
             "current": 5, "max": 15, "reset": "short"},
        ]},
    )
    yield kael
    await _patch_sheet(
        gm_client, kael["id"], {"level": 7},
        class_slug="monk",
    )
    await _patch_sheet(
        gm_client, kael["id"],
        {"resources": [
            {"key": "ki-points", "label": "Ki Points",
             "current": 7, "max": 7, "reset": "short"},
        ]},
    )


async def test_use_empty_body_happy_path(
    gm_client, gm_ws, kael_lv18,
):
    """Kael Lv 18, ki 5 → /use_empty_body → ki 1, broadcasts fire."""
    kael = kael_lv18
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_empty_body",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ki_spent"] == 4
    assert data["remaining"] == 1
    assert data["buff_installed"] is True
    import asyncio as _asy
    await _asy.sleep(0.3)
    feats = _eb_broadcasts(gm_ws, kael["id"])
    assert feats, (
        f"v2.99.209: expected feature_used(source=empty-body); "
        f"buffered={gm_ws.buffered()}"
    )


async def test_use_empty_body_level_gate(
    gm_client, roster,
):
    """Control: Kael at Lv 7 default → 409 level_too_low."""
    kael = roster["Kael Brightleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_empty_body",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "level_too_low"
    assert data.get("required") == 18


async def test_use_empty_body_not_enough_ki(
    gm_client, roster,
):
    """Gate: Kael Lv 18 + ki 3 → 409 not_enough_ki."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(
        gm_client, kael["id"], {"level": 18},
        class_slug="monk",
    )
    await _patch_sheet(
        gm_client, kael["id"],
        {"resources": [
            {"key": "ki-points", "label": "Ki Points",
             "current": 3, "max": 15, "reset": "short"},
        ]},
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_empty_body",
            json={"character_id": kael["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "not_enough_ki"
        assert data.get("required") == 4
    finally:
        await _patch_sheet(
            gm_client, kael["id"], {"level": 7},
            class_slug="monk",
        )
        await _patch_sheet(
            gm_client, kael["id"],
            {"resources": [
                {"key": "ki-points", "label": "Ki Points",
                 "current": 7, "max": 7, "reset": "short"},
            ]},
        )
