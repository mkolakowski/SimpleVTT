"""v2.99.362 — Way of the Four Elements Monk: Fangs of the Fire Snake (G Monk #8, Lv 3+, PHB).

Phase G Monk Ways subclass batch ship #8 — Way of the Four
Elements opens.
RAW PHB p.81: when you take the Attack action, spend 1 ki to grow
flame tendrils — unarmed strike reach +10 ft for that action; on a
hit you may spend a 2nd ki to deal an extra 1d10 fire damage.

v1 announce-only — the attacks + the 2nd-ki fire spend are
GM-tracked. The +10 ft reach + the potential 1d10 fire are
reported server-side. Action chip + 1 ki.

Kael Brightleaf (Monk, PATCHed to Way of the Four Elements Lv 7)
is the demo fixture.

Tests:
  - Lv 7 happy: reach +10, fire in [1,10], 1d10, 1 ki spent.
  - Wrong subclass (default Way of the Open Hand) → 409.
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


def _ff_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "fangs-of-the-fire-snake"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def kael_four_elements(gm_client, roster):
    """PATCH Kael to Way of the Four Elements + long-rest (full ki);
    restore to Way of the Open Hand on teardown."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(
        gm_client, kael["id"],
        {"subclass": "Way of the Four Elements"},
        class_slug="monk",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
        json={"type": "long"},
    )
    try:
        yield kael
    finally:
        await _patch_sheet(
            gm_client, kael["id"],
            {"subclass": "Way of the Open Hand"},
            class_slug="monk",
        )


async def test_use_ff_happy_lv7(
    gm_client, gm_ws, kael_four_elements,
):
    """Lv 7 Four Elements → +10 reach, 1d10 fire in [1,10], 1 ki."""
    kael = kael_four_elements
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fangs_of_the_fire_snake",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "fangs-of-the-fire-snake"
    assert data["reach_bonus_ft"] == 10
    assert data["fire_damage_die"] == "1d10"
    assert 1 <= data["fire_damage"] <= 10
    assert data["ki_spent"] == 1
    assert data["monk_level"] == 7
    await asyncio.sleep(0.3)
    feats = _ff_broadcasts(gm_ws, kael["id"])
    assert feats
    assert feats[-1]["data"]["fire_damage"] == data["fire_damage"]


async def test_use_ff_wrong_subclass(
    gm_client, roster,
):
    """Default Kael (Way of the Open Hand) → 409."""
    kael = roster["Kael Brightleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fangs_of_the_fire_snake",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ff_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fangs_of_the_fire_snake",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
