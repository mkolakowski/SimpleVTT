"""v2.99.373 — Echo Knight Fighter: Manifest Echo (G Fighter sweep #4, Lv 3+, EGtW).

Phase G Fighter martial archetype sweep ship #4 — Echo Knight
opens.
RAW EGtW p.183: as a bonus action, manifest a spectral echo within
15 ft (AC 14 + proficiency bonus, 1 HP, immune to all conditions).
Swap places with it (within 30 ft), attack from its space, or move
it 30 ft as a bonus action.

v1 announce-only — the echo token placement, swap, and
attack-from-echo are GM-tracked. The echo AC is computed
server-side. Bonus chip.

Garrik Ironside (Fighter, PATCHed to Echo Knight Lv 9) is the demo
fixture (PB 4 → echo AC 18).

Tests:
  - Lv 9 happy: echo_ac 18 (14 + PB 4), 1 HP, 15-ft manifest.
  - Wrong subclass (default Champion) → 409.
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


def _me_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "manifest-echo"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def garrik_echo(gm_client, roster):
    """PATCH Garrik to Echo Knight; restore to Champion on teardown."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Echo Knight"},
        class_slug="fighter",
    )
    try:
        yield garrik
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion"},
            class_slug="fighter",
        )


async def test_use_me_happy_lv9(
    gm_client, gm_ws, garrik_echo,
):
    """Lv 9 Echo Knight → echo AC 18 (14 + PB 4), 1 HP, 15 ft."""
    garrik = garrik_echo
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_manifest_echo",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "manifest-echo"
    assert data["echo_ac"] == 18  # 14 + proficiency bonus 4 at Lv 9
    assert data["echo_hp"] == 1
    assert data["manifest_range_ft"] == 15
    assert data["swap_range_ft"] == 30
    assert data["fighter_level"] == 9
    await asyncio.sleep(0.3)
    feats = _me_broadcasts(gm_ws, garrik["id"])
    assert feats
    assert feats[-1]["data"]["echo_ac"] == 18


async def test_use_me_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_manifest_echo",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_me_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_manifest_echo",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
