"""v2.99.343 — Shadow Magic: Strength of the Grave (G.2 batch CLOSE, Lv 1+, XGE).

G.2 Sorcerer subclass batch ship #5 — Shadow Magic opens and
CLOSES the Sorcerer batch.
RAW XGE p.50: when damage reduces you to 0 HP (and doesn't kill
you outright), make a CHA save (DC 5 + damage taken); on a success
drop to 1 HP instead. Once per long rest.

v1 — rolls the CHA save server-side (d20 + CHA mod vs DC 5 +
damage); once-per-rest limit + damage-type/crit exclusions
GM-tracked. No action cost.

Tests:
  - Lv 5 happy: DC = 5 + damage, total = d20 + cha_mod, success
    coherent, broadcast fires.
  - Wrong subclass (default Zara Draconic) → 409.
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


def _sg_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "strength-of-the-grave"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def zara_shadow(gm_client, roster):
    """PATCH Zara to Shadow Magic."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"],
        {"subclass": "Shadow Magic"},
        class_slug="sorcerer",
    )
    try:
        yield zara
    finally:
        await _patch_sheet(
            gm_client, zara["id"],
            {"subclass": "Draconic Bloodline"},
            class_slug="sorcerer",
        )


async def test_use_sg_happy_lv5(
    gm_client, gm_ws, zara_shadow,
):
    """Lv 5 Shadow Magic → DC 5+damage, coherent CHA save roll."""
    zara = zara_shadow
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_strength_of_the_grave",
        json={"character_id": zara["id"], "damage": 12},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "strength-of-the-grave"
    assert data["damage"] == 12
    assert data["dc"] == 17  # 5 + 12
    assert 1 <= data["d20"] <= 20
    assert data["total"] == data["d20"] + data["cha_mod"]
    assert data["success"] == (data["total"] >= data["dc"])
    assert data["sorcerer_level"] == 5
    await asyncio.sleep(0.3)
    feats = _sg_broadcasts(gm_ws, zara["id"])
    assert feats
    assert feats[-1]["data"]["dc"] == 17


async def test_use_sg_wrong_subclass(
    gm_client, roster,
):
    """Default Zara (Draconic Bloodline) → 409."""
    zara = roster["Zara Emberfire"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_strength_of_the_grave",
        json={"character_id": zara["id"], "damage": 8},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_sg_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_strength_of_the_grave",
        json={"character_id": caelan["id"], "damage": 8},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
