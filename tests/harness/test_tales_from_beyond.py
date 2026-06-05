"""v2.99.325 — Spirits College Bard: Tales from Beyond (F.1 batch, Lv 3+, TCE).

F.1 Bard subclass batch ship #7. RAW TCE p.30: bonus action
to roll 1d6 on Spirit Tales table; action to apply the chosen
tale to a creature within 30 ft.

The 6 tales: Clever Animal / Renowned Duelist / Beloved Friends /
Brute / Tragic Romance / Traveler.

v1 announce-only — actual tale effect application GM-tracked.
Costs bonus chip. `force_tale` body param (1-6) is a TEST_MODE
escape hatch.

Tests:
  - Lv 3+ random roll → tale_roll in [1,6], tale_name set.
  - force_tale=4 (Brute) → tale 4 with brute description.
  - force_tale=2 (Renowned Duelist) → tale 2.
  - Wrong subclass → 409.
  - Spirits Lv 2 → 409.
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


def _tb_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "tales-from-beyond"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def lyra_spirits(gm_client, roster):
    """PATCH Lyra to College of Spirits."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Spirits"},
        class_slug="bard",
    )
    try:
        yield lyra
    finally:
        await _patch_sheet(
            gm_client, lyra["id"],
            {"subclass": "College of Lore", "level": 6},
            class_slug="bard",
        )


async def test_use_tb_happy_lv6(
    gm_client, gm_ws, lyra_spirits,
):
    """Lv 6 Spirits → tale_roll in [1,6], tale_name set."""
    lyra = lyra_spirits
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tales_from_beyond",
        json={"character_id": lyra["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert 1 <= data["tale_roll"] <= 6
    assert data["tale_name"]  # non-empty
    assert data["bard_level"] == 6
    await asyncio.sleep(0.3)
    feats = _tb_broadcasts(gm_ws, lyra["id"])
    assert feats


async def test_use_tb_force_tale_4_brute(
    gm_client, lyra_spirits,
):
    """force_tale=4 (Brute) → roll 4."""
    lyra = lyra_spirits
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tales_from_beyond",
        json={"character_id": lyra["id"], "force_tale": 4, "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tale_roll"] == 4
    assert "Brute" in data["tale_name"]


async def test_use_tb_force_tale_2_duelist(
    gm_client, lyra_spirits,
):
    """force_tale=2 (Renowned Duelist) → roll 2."""
    lyra = lyra_spirits
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tales_from_beyond",
        json={"character_id": lyra["id"], "force_tale": 2, "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tale_roll"] == 2
    assert "Duelist" in data["tale_name"]


async def test_use_tb_wrong_subclass(
    gm_client, roster,
):
    """Default Lyra (Lore) → 409."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tales_from_beyond",
        json={"character_id": lyra["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_tb_level_gate(
    gm_client, roster,
):
    """Spirits Lyra at Lv 2 → 409."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Spirits", "level": 2},
        class_slug="bard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_tales_from_beyond",
            json={"character_id": lyra["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, lyra["id"],
            {"subclass": "College of Lore", "level": 6},
            class_slug="bard",
        )
