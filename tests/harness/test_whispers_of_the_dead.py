"""v2.99.312 — Phantom Rogue: Whispers of the Dead (E.3 batch, Lv 3+).

E.3 Rogue subclass ship #8 — CLOSES the E.3 Rogue batch (8/8
PHB+XGE+TCE subclasses). RAW TCE p.61: on each rest, choose
one skill or tool proficiency; you have that prof until next
short or long rest.

v1 announce-only — the actual prof bonus application is
GM-tracked. No chip — selection happens on rest.

Tests:
  - Lv 3+ happy with explicit prof → 200, announced.
  - Default proficiency_name missing → fallback string.
  - Default Pip (Thief) → 409.
  - Phantom Lv 2 → 409.
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


def _wd_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "whispers-of-the-dead"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def pip_phantom(gm_client, roster):
    """PATCH Pip to Phantom subclass."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Phantom"},
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


async def test_use_wd_happy_lv7(
    gm_client, gm_ws, pip_phantom,
):
    """Lv 7 Phantom with explicit prof → 200, announced."""
    pip = pip_phantom
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_whispers_of_the_dead",
        json={"character_id": pip["id"], "proficiency_name": "Arcana"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["proficiency_name"] == "Arcana"
    assert data["expires_on"] == "next_rest"
    assert data["rogue_level"] == 7
    await asyncio.sleep(0.3)
    feats = _wd_broadcasts(gm_ws, pip["id"])
    assert feats


async def test_use_wd_default_prof(
    gm_client, pip_phantom,
):
    """Missing proficiency_name → fallback string."""
    pip = pip_phantom
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_whispers_of_the_dead",
        json={"character_id": pip["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "unspecified" in data["proficiency_name"]


async def test_use_wd_wrong_subclass(
    gm_client, roster,
):
    """Default Pip (Thief) → 409."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_whispers_of_the_dead",
        json={"character_id": pip["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_wd_level_gate(
    gm_client, roster,
):
    """Phantom Pip at Lv 2 → 409."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Phantom", "level": 2},
        class_slug="rogue",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_whispers_of_the_dead",
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
