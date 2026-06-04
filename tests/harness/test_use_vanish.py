"""v2.99.215 — Vanish (Ranger Lv 14+).

Phase F.3 cont'd of the v2.99.193 phased completion plan. RAW
PHB p.92: "Starting at 14th level, you can use the Hide action
as a bonus action on your turn. Also, you can't be tracked by
nonmagical means, unless you choose to leave a trail."

v1 ships announce-style — `/use_vanish` marks the bonus action
slot + broadcasts feature_used. The actual Hide check (Stealth)
is rolled normally via /roll. The "can't be tracked by
nonmagical means" half is filed (SimpleVTT doesn't model
tracking checks).

Tests:
  - Happy: Rowan Lv 14 → /use_vanish → 200 + broadcast.
  - Gate: Rowan Lv 7 → 409 level_too_low.
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


def _vanish_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "vanish"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def rowan_lv14(gm_client, roster):
    """PATCH Rowan to Lv 14. Restore Lv 7 in teardown."""
    rowan = roster["Rowan Quickbow"]
    await _patch_sheet(
        gm_client, rowan["id"], {"level": 14},
        class_slug="ranger",
    )
    yield rowan
    await _patch_sheet(
        gm_client, rowan["id"], {"level": 7},
        class_slug="ranger",
    )


async def test_use_vanish_happy_path(
    gm_client, gm_ws, rowan_lv14,
):
    """Rowan Lv 14 → /use_vanish → 200 + broadcast."""
    rowan = rowan_lv14
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_vanish",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "vanish"
    await asyncio.sleep(0.3)
    feats = _vanish_broadcasts(gm_ws, rowan["id"])
    assert feats, (
        f"v2.99.215: expected feature_used(source=vanish); "
        f"buffered={gm_ws.buffered()}"
    )


async def test_use_vanish_level_gate(
    gm_client, roster,
):
    """Control: Rowan at Lv 7 → 409 level_too_low."""
    rowan = roster["Rowan Quickbow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_vanish",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "level_too_low"
    assert data.get("required") == 14
