"""v2.99.338 — Graviturgy Magic Wizard: Adjust Density (G.1 batch close, Lv 2+, EGtW).

G.1 Wizard subclass batch ship #13 — CLOSES the batch at 13/13.
RAW EGtW p.185: action + concentration up to 1 min. Target one
willing creature within 30 ft. Double or halve weight:
- Doubled: speed -10 ft, advantage on STR checks/saves.
- Halved: speed +10 ft, disadvantage on STR checks/saves.

v1 announce-only — weight + STR-advantage application GM-tracked.
Action chip. Optional target_character_id.

Tests:
  - Lv 7 happy default (double): speed_delta -10, advantage.
  - mode="halve": speed_delta +10, disadvantage.
  - With target: target_character_name set in response + broadcast.
  - Wrong subclass → 409.
  - Graviturgy Lv 1 → 409.
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
        if (m.get("data") or {}).get("source") == "adjust-density"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def thalindra_graviturgy(gm_client, roster):
    """PATCH Thalindra to Graviturgy Magic."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "Graviturgy Magic"},
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


async def test_use_ad_happy_lv7_double(
    gm_client, gm_ws, thalindra_graviturgy,
):
    """Lv 7 Graviturgy default (double): speed_delta -10, advantage."""
    thal = thalindra_graviturgy
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_adjust_density",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "adjust-density"
    assert data["mode"] == "double"
    assert data["speed_delta"] == -10
    assert data["str_effect"] == "advantage"
    assert data["wizard_level"] == 7
    await asyncio.sleep(0.3)
    feats = _ad_broadcasts(gm_ws, thal["id"])
    assert feats


async def test_use_ad_halve_mode(
    gm_client, thalindra_graviturgy,
):
    """mode='halve' → speed_delta +10, disadvantage."""
    thal = thalindra_graviturgy
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_adjust_density",
        json={"character_id": thal["id"], "mode": "halve", "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "halve"
    assert data["speed_delta"] == 10
    assert data["str_effect"] == "disadvantage"


async def test_use_ad_with_target(
    gm_client, thalindra_graviturgy, roster,
):
    """With target_character_id: target name propagates."""
    thal = thalindra_graviturgy
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_adjust_density",
        json={
            "character_id": thal["id"],
            "target_character_id": caelan["id"],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["target_character_id"] == caelan["id"]
    assert data["target_character_name"] == "Sir Caelan Lightbringer"


async def test_use_ad_wrong_subclass(
    gm_client, roster,
):
    """Default Thalindra (Evocation) → 409."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_adjust_density",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ad_level_gate(
    gm_client, roster,
):
    """Graviturgy Thalindra at Lv 1 → 409."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "Graviturgy Magic", "level": 1},
        class_slug="wizard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_adjust_density",
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
