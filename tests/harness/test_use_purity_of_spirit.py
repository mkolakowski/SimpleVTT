"""v2.99.154 — /use_purity_of_spirit endpoint tests.

Purity of Spirit is a Paladin Oath of Devotion Lv 15+ feature:
always under the effects of Protection from Evil and Good (PHB
p.87). v1 ships the audit broadcast + level/subclass gate only
— the full mechanical hooks (attack-roll disadvantage from
listed creature types, condition-install gate) need creature-
type metadata on the source and are filed.

Mirror of v2.99.143 Beguiling Influence / v2.99.146 Eyes of the
Rune Keeper pattern, but with a level + subclass gate instead
of an invocation gate.

Sir Caelan Lightbringer is the Paladin fixture. Stock sheet is
Lv 6 Oath of Devotion — below the Lv 15 prerequisite — so the
harness PATCHes him to Lv 15 in the fixture and restores Lv 6
in teardown.

Tests:
  - happy path (Caelan at Lv 15 Devotion) → 200 + WS
    feature_used broadcast with `source: purity-of-spirit` +
    `protected_against` list of 6 creature types
  - level gate (Caelan at stock Lv 6) → 409 missing_feature
  - missing character_id → 400
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def caelan_at_lv_15(gm_client, roster):
    """PATCH Sir Caelan to Paladin Lv 15 (Purity of Spirit
    prereq). Restore Lv 6 in teardown.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
        json={"class_slug": "paladin", "level": 15},
    )
    yield caelan
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
        json={"class_slug": "paladin", "level": 6},
    )


async def test_use_purity_of_spirit_happy_path(
    gm_client, gm_ws, caelan_at_lv_15,
):
    """Caelan at Lv 15 Devotion → 200 + audit broadcast with the
    6-creature protected_against list.
    """
    caelan = caelan_at_lv_15
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_purity_of_spirit",
        json={"character_id": caelan["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["character_id"] == caelan["id"]
    protected = data.get("protected_against") or []
    assert "fiend" in protected
    assert "undead" in protected
    assert len(protected) == 6
    msg = await gm_ws.wait_for("feature_used")
    bd = msg["data"]
    assert bd.get("source") == "purity-of-spirit"
    assert bd.get("character_id") == caelan["id"]
    assert "fiend" in (bd.get("protected_against") or [])


async def test_use_purity_of_spirit_below_lv_15_409(gm_client, roster):
    """Caelan at stock Lv 6 → 409 missing_feature (level gate)."""
    caelan = roster["Sir Caelan Lightbringer"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_purity_of_spirit",
        json={"character_id": caelan["id"]},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_feature"
    assert data.get("feature") == "purity-of-spirit"


async def test_use_purity_of_spirit_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_purity_of_spirit",
        json={},
    )
    assert resp.status_code == 400, resp.text
