"""v2.99.308 — Mastermind Rogue: Master of Tactics (E.3 batch, Lv 3+).

E.3 Rogue subclass ship #4. RAW XGE p.46: bonus action Help;
when helping an ally attack, target can be within 30 ft of
you (not 5 ft) if it can see/hear you.

v1 announce-only — actual Help advantage on ally attack is
GM-tracked. Costs bonus chip.

Tests:
  - Lv 3+ happy → help_action_economy bonus, range 30 ft.
  - Default Pip (Thief) → 409.
  - Mastermind Lv 2 → 409.
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


def _mt_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "master-of-tactics"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def pip_mastermind(gm_client, roster):
    """PATCH Pip to Mastermind subclass."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Mastermind"},
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


async def test_use_mt_happy_lv7(
    gm_client, gm_ws, pip_mastermind,
):
    """Lv 7 Mastermind → bonus Help, 30 ft range."""
    pip = pip_mastermind
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_master_of_tactics",
        json={"character_id": pip["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["help_action_economy"] == "bonus"
    assert data["help_target_range_ft"] == 30
    assert data["rogue_level"] == 7
    await asyncio.sleep(0.3)
    feats = _mt_broadcasts(gm_ws, pip["id"])
    assert feats


async def test_use_mt_wrong_subclass(
    gm_client, roster,
):
    """Default Pip (Thief) → 409."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_master_of_tactics",
        json={"character_id": pip["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_mt_level_gate(
    gm_client, roster,
):
    """Mastermind Pip at Lv 2 → 409."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Mastermind", "level": 2},
        class_slug="rogue",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_master_of_tactics",
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
