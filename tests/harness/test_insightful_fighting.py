"""v2.99.310 — Inquisitive Rogue: Insightful Fighting (E.3 batch, Lv 3+).

E.3 Rogue subclass ship #6. RAW XGE p.45: bonus action
Insight vs target's Deception contest. On win, Sneak Attack
without advantage (still blocked by disadvantage) for 1 min
or until used against a different target.

v1 announce-only — contest is GM-tracked. Costs bonus chip.

Tests:
  - Lv 3+ happy → duration 1 min.
  - target_combatant_id passes through.
  - Default Pip (Thief) → 409.
  - Inquisitive Lv 2 → 409.
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


def _if_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "insightful-fighting"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def pip_inquisitive(gm_client, roster):
    """PATCH Pip to Inquisitive subclass."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Inquisitive"},
        class_slug="rogue",
    )
    try:
        yield pip
    finally:
        await _patch_sheet(
            gm_client, pip["id"],
            {"subclass": "Thief", "level": 7},
            class_slug="rogue",
        )


async def test_use_if_happy_lv7(
    gm_client, gm_ws, pip_inquisitive,
):
    """Lv 7 Inquisitive → 1 min duration."""
    pip = pip_inquisitive
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_insightful_fighting",
        json={"character_id": pip["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["duration_minutes"] == 1
    assert data["rogue_level"] == 7
    await asyncio.sleep(0.3)
    feats = _if_broadcasts(gm_ws, pip["id"])
    assert feats


async def test_use_if_with_target(
    gm_client, pip_inquisitive,
):
    """Optional target_combatant_id passes through."""
    pip = pip_inquisitive
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_insightful_fighting",
        json={"character_id": pip["id"], "target_combatant_id": "tok_test", "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["target_combatant_id"] == "tok_test"


async def test_use_if_wrong_subclass(
    gm_client, roster,
):
    """Default Pip (Thief) → 409."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_insightful_fighting",
        json={"character_id": pip["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_if_level_gate(
    gm_client, roster,
):
    """Inquisitive Pip at Lv 2 → 409."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Inquisitive", "level": 2},
        class_slug="rogue",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_insightful_fighting",
            json={"character_id": pip["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, pip["id"],
            {"subclass": "Thief", "level": 7},
            class_slug="rogue",
        )
