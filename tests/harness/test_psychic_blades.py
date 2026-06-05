"""v2.99.311 — Soulknife Rogue: Psychic Blades (E.3 batch, Lv 3+).

E.3 Rogue subclass ship #7 (TCE). RAW TCE p.62: bonus action
to manifest Psychic Blades in each free hand. Simple melee +
thrown (60/120 ft), 1d6 psychic, finesse + light. Counts as
monk weapon. Usable with Sneak Attack.

v1 announce-only — actual attack rolls + Sneak Attack
integration are via the existing /attack flow. Costs bonus chip.

Tests:
  - Lv 3+ happy → 1d6 psychic + thrown 60/120 + finesse/light.
  - Default Pip (Thief) → 409.
  - Soulknife Lv 2 → 409.
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


def _pb_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "psychic-blades"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def pip_soulknife(gm_client, roster):
    """PATCH Pip to Soulknife subclass."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Soulknife"},
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


async def test_use_pb_happy_lv7(
    gm_client, gm_ws, pip_soulknife,
):
    """Lv 7 Soulknife → 1d6 psychic + thrown 60/120."""
    pip = pip_soulknife
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_psychic_blades",
        json={"character_id": pip["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["damage_expression"] == "1d6"
    assert data["damage_type"] == "psychic"
    assert data["thrown_range_ft"] == [60, 120]
    assert "finesse" in data["properties"]
    assert "light" in data["properties"]
    assert "thrown" in data["properties"]
    assert data["counts_as_monk_weapon"] is True
    assert data["rogue_level"] == 7
    await asyncio.sleep(0.3)
    feats = _pb_broadcasts(gm_ws, pip["id"])
    assert feats


async def test_use_pb_wrong_subclass(
    gm_client, roster,
):
    """Default Pip (Thief) → 409."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_psychic_blades",
        json={"character_id": pip["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_pb_level_gate(
    gm_client, roster,
):
    """Soulknife Pip at Lv 2 → 409."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Soulknife", "level": 2},
        class_slug="rogue",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_psychic_blades",
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
