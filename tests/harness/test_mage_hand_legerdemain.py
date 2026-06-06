"""v2.99.369 — Arcane Trickster Rogue: Mage Hand Legerdemain (G Rogue sweep, Lv 3+, PHB).

Phase G Rogue archetype sweep — Arcane Trickster was the last
untouched Rogue archetype.
RAW PHB p.97: when you cast Mage Hand, make the spectral hand
invisible and perform extra tasks — stow/retrieve from another's
container, pick locks / disarm traps at range, all controlled as a
bonus action, unnoticed on a Sleight of Hand check.

v1 announce-only — the hand's tasks + Stealth checks are
GM-tracked. No action cost beyond the Mage Hand cast.

Pip Quickfingers (Rogue, PATCHed to Arcane Trickster) is the demo
fixture.

Tests:
  - Lv 7 happy: range 30, invisible True, tasks listed.
  - Wrong subclass (default Thief) → 409.
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


def _ml_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "mage-hand-legerdemain"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def pip_arcane_trickster(gm_client, roster):
    """PATCH Pip to Arcane Trickster; restore to Thief on teardown."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, pip["id"],
        {"subclass": "Arcane Trickster"},
        class_slug="rogue",
    )
    try:
        yield pip
    finally:
        await _patch_sheet(
            gm_client, pip["id"],
            {"subclass": "Thief"},
            class_slug="rogue",
        )


async def test_use_ml_happy(
    gm_client, gm_ws, pip_arcane_trickster,
):
    """Arcane Trickster → invisible hand, range 30, tasks listed."""
    pip = pip_arcane_trickster
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mage_hand_legerdemain",
        json={"character_id": pip["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "mage-hand-legerdemain"
    assert data["range_ft"] == 30
    assert data["invisible"] is True
    assert len(data["tasks"]) >= 1
    await asyncio.sleep(0.3)
    feats = _ml_broadcasts(gm_ws, pip["id"])
    assert feats
    assert feats[-1]["data"]["invisible"] is True


async def test_use_ml_wrong_subclass(
    gm_client, roster,
):
    """Default Pip (Thief) → 409."""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mage_hand_legerdemain",
        json={"character_id": pip["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ml_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_mage_hand_legerdemain",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
