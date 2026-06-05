"""v2.99.336 — War Magic Wizard: Arcane Deflection (G.1 batch, Lv 2+, XGE).

G.1 Wizard subclass batch ship #11. RAW XGE p.59: reaction
on being hit by attack or failing save: +2 AC (vs that
attack) OR +4 to that failed save. Can't cast leveled spells
(cantrips only) until end of next turn.

v1 announce-only — bonus application + leveled-spell lockout
GM-tracked. Costs reaction chip.

Tests:
  - Lv 7 happy default AC → bonus 2.
  - mode="save" → bonus 4.
  - Wrong subclass → 409.
  - War Magic Lv 1 → 409.
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


def _ad_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "arcane-deflection"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def thalindra_war_magic(gm_client, roster):
    """PATCH Thalindra to War Magic."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "War Magic"},
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


async def test_use_ad_happy_lv7_ac(
    gm_client, gm_ws, thalindra_war_magic,
):
    """Lv 7 War Magic default AC → bonus 2."""
    thal = thalindra_war_magic
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_deflection",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "ac"
    assert data["bonus"] == 2
    assert data["leveled_spell_lockout"] is True
    assert data["wizard_level"] == 7
    await asyncio.sleep(0.3)
    feats = _ad_broadcasts(gm_ws, thal["id"])
    assert feats


async def test_use_ad_save_mode(
    gm_client, thalindra_war_magic,
):
    """mode='save' → bonus 4."""
    thal = thalindra_war_magic
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_deflection",
        json={"character_id": thal["id"], "mode": "save", "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "save"
    assert data["bonus"] == 4


async def test_use_ad_wrong_subclass(
    gm_client, roster,
):
    """Default Thalindra (Evocation) → 409."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_deflection",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ad_level_gate(
    gm_client, roster,
):
    """War Magic Thalindra at Lv 1 → 409."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "War Magic", "level": 1},
        class_slug="wizard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_arcane_deflection",
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
