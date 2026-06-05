"""v2.99.328 — Divination Wizard: The Third Eye (G.1 batch, Lv 10+).

G.1 Wizard subclass batch ship #2. Pivoted to Third Eye
(Lv 10) after discovering Portent (Lv 2) was already wired
in v2.99.219.

RAW PHB p.116: action to gain one of four magical senses
until dismissed or short/long rest: Darkvision (60 ft),
Ethereal Sight (60 ft), Greater Comprehension (read any
language), See Invisibility (10 ft).

v1 announce-only — sense application GM-tracked. Costs
action chip.

Thalindra Lv 7 default → 409 level gate. PATCH to Lv 10
to test.

Tests:
  - Lv 10 happy default Darkvision.
  - sense="see-invisibility" passes through.
  - sense="ethereal-sight" passes through.
  - sense="greater-comprehension" passes through.
  - Wrong subclass → 409.
  - Divination Lv 9 → 409.
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


def _te_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "third-eye"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def thalindra_divination_lv10(gm_client, roster):
    """PATCH Thalindra to Divination Lv 10."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "School of Divination", "level": 10},
        class_slug="wizard",
    )
    try:
        yield thal
    finally:
        await _patch_sheet(
            gm_client, thal["id"],
            {"subclass": "School of Evocation", "level": 7},
            class_slug="wizard",
        )


async def test_use_te_happy_lv10_darkvision(
    gm_client, gm_ws, thalindra_divination_lv10,
):
    """Lv 10 Divination default → Darkvision."""
    thal = thalindra_divination_lv10
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_third_eye",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sense"] == "darkvision"
    assert "Darkvision" in data["sense_description"]
    assert data["wizard_level"] == 10
    await asyncio.sleep(0.3)
    feats = _te_broadcasts(gm_ws, thal["id"])
    assert feats


async def test_use_te_see_invisibility(
    gm_client, thalindra_divination_lv10,
):
    """sense='see-invisibility' passes through."""
    thal = thalindra_divination_lv10
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_third_eye",
        json={"character_id": thal["id"], "sense": "see-invisibility", "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sense"] == "see-invisibility"


async def test_use_te_ethereal_sight(
    gm_client, thalindra_divination_lv10,
):
    """sense='ethereal-sight' passes through."""
    thal = thalindra_divination_lv10
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_third_eye",
        json={"character_id": thal["id"], "sense": "ethereal-sight", "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sense"] == "ethereal-sight"


async def test_use_te_greater_comprehension(
    gm_client, thalindra_divination_lv10,
):
    """sense='greater-comprehension' passes through."""
    thal = thalindra_divination_lv10
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_third_eye",
        json={"character_id": thal["id"], "sense": "greater-comprehension", "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sense"] == "greater-comprehension"


async def test_use_te_wrong_subclass(
    gm_client, roster,
):
    """Default Thalindra (Evocation Lv 7) → 409."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_third_eye",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_te_level_gate(
    gm_client, roster,
):
    """Divination Thalindra at Lv 9 → 409."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "School of Divination", "level": 9},
        class_slug="wizard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_third_eye",
            json={"character_id": thal["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, thal["id"],
            {"subclass": "School of Evocation", "level": 7},
            class_slug="wizard",
        )
