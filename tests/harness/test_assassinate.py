"""v2.99.306 — Assassin Rogue: Assassinate (E.3 opener, Lv 3+).

E.3 Rogue subclass batch opener (after pivot — Thief Fast
Hands was already wired in v2.99.224). RAW PHB p.97:
advantage on attack rolls vs creatures that haven't taken
a turn yet in combat; auto-crit vs surprised creatures.

v1 announce-only — the actual advantage / auto-crit
mechanics are GM-tracked at attack time. No chip — passive
declaration.

Pip (Thief Lv 7) PATCH'd to Assassin Lv 3+ for testing.

Tests:
  - Lv 3 Assassin happy → advantage_vs_pre_turn,
    auto_crit_vs_surprised.
  - Default Thief Pip → 409.
  - Assassin Lv 2 (gate) → 409.
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


def _ass_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "assassinate"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def pip_assassin(gm_client, roster):
    """PATCH Pip to Assassin subclass (level stays 7)."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Assassin"},
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


async def test_use_ass_happy_lv7(
    gm_client, gm_ws, pip_assassin,
):
    """Lv 7 Assassin → advantage vs pre-turn, auto-crit vs surprised."""
    pip = pip_assassin
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_assassinate",
        json={"character_id": pip["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["advantage_vs_pre_turn"] is True
    assert data["auto_crit_vs_surprised"] is True
    assert data["rogue_level"] == 7
    await asyncio.sleep(0.3)
    feats = _ass_broadcasts(gm_ws, pip["id"])
    assert feats


async def test_use_ass_wrong_subclass(
    gm_client, roster,
):
    """Default Pip (Thief Lv 7) → 409."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_assassinate",
        json={"character_id": pip["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ass_level_gate(
    gm_client, roster,
):
    """Assassin Pip at Lv 2 → 409."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Assassin", "level": 2},
        class_slug="rogue",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_assassinate",
            json={"character_id": pip["id"]},
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
