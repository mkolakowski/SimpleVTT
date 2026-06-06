"""v2.99.366 — Path of the Ancestral Guardian Barbarian: Ancestral Protectors (G Barbarian #3, Lv 3+, XGE).

Phase G Barbarian Paths subclass batch ship #3 — Path of the
Ancestral Guardian opens.
RAW XGE p.9: while raging, the first creature you hit each turn
becomes the target of warrior spirits — until the start of your
next turn it has disadvantage on attacks not against you, and its
targets resist the damage it deals.

v1 announce-only — the disadvantage + resistance effects +
first-hit-per-turn limit are GM-tracked. No action cost.

Krieger Stonefist (Barbarian, PATCHed to Path of the Ancestral
Guardian Lv 7) is the demo fixture.

Tests:
  - Lv 7 happy: disadvantage + resistance flags True, broadcast.
  - Wrong subclass (default Berserker) → 409.
  - Wrong class (Caelan paladin) → 409.
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


def _ap_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "ancestral-protectors"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def krieger_ancestral(gm_client, roster):
    """PATCH Krieger to Path of the Ancestral Guardian; restore to Berserker."""
    krieger = roster["Krieger Stonefist"]
    await _patch_sheet(
        gm_client, krieger["id"],
        {"subclass": "Path of the Ancestral Guardian"},
        class_slug="barbarian",
    )
    try:
        yield krieger
    finally:
        await _patch_sheet(
            gm_client, krieger["id"],
            {"subclass": "Path of the Berserker"},
            class_slug="barbarian",
        )


async def test_use_ap_happy_lv7(
    gm_client, gm_ws, krieger_ancestral,
):
    """Lv 7 Ancestral Guardian → disadvantage + resistance flags."""
    krieger = krieger_ancestral
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_ancestral_protectors",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "ancestral-protectors"
    assert data["target_attack_disadvantage"] is True
    assert data["target_damage_resisted"] is True
    assert data["barbarian_level"] == 7
    await asyncio.sleep(0.3)
    feats = _ap_broadcasts(gm_ws, krieger["id"])
    assert feats
    assert feats[-1]["data"]["target_attack_disadvantage"] is True


async def test_use_ap_wrong_subclass(
    gm_client, roster,
):
    """Default Krieger (Berserker) → 409."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_ancestral_protectors",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ap_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_ancestral_protectors",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
