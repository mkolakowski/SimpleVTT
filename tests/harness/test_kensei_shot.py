"""v2.99.357 — Way of the Kensei Monk: Kensei's Shot (G Monk Ways batch #2, Lv 3+, XGE).

Phase G Monk Ways subclass batch ship #2 — Way of the Kensei
opens.
RAW XGE p.34: bonus action — ranged kensei weapon attacks this
turn deal an extra 1d4 damage of the weapon's type, until the end
of the turn. No ki.

v1 announce-only — the actual on-hit damage application is
GM-tracked. The 1d4 is rolled server-side. Bonus chip.

Kael Brightleaf (Monk, PATCHed to Way of the Kensei Lv 7) is the
demo fixture.

Tests:
  - Lv 7 happy: bonus_damage in [1,4], 1d4 dice, broadcast fires.
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


def _ks_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "kensei-shot"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def kael_kensei(gm_client, roster):
    """PATCH Kael to Way of the Kensei; restore to Way of the Open Hand."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(
        gm_client, kael["id"],
        {"subclass": "Way of the Kensei"},
        class_slug="monk",
    )
    try:
        yield kael
    finally:
        await _patch_sheet(
            gm_client, kael["id"],
            {"subclass": "Way of the Open Hand"},
            class_slug="monk",
        )


async def test_use_ks_happy_lv7(
    gm_client, gm_ws, kael_kensei,
):
    """Lv 7 Way of the Kensei → +1d4 bonus damage in [1,4]."""
    kael = kael_kensei
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_kensei_shot",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "kensei-shot"
    assert data["damage_dice"] == "1d4"
    assert 1 <= data["bonus_damage"] <= 4
    assert data["monk_level"] == 7
    await asyncio.sleep(0.3)
    feats = _ks_broadcasts(gm_ws, kael["id"])
    assert feats
    assert feats[-1]["data"]["bonus_damage"] == data["bonus_damage"]


async def test_use_ks_wrong_subclass(
    gm_client, roster,
):
    """Default Kael (Way of the Open Hand) → 409."""
    kael = roster["Kael Brightleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_kensei_shot",
        json={"character_id": kael["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ks_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_kensei_shot",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
