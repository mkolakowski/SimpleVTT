"""v2.99.323 — Swords College Bard: Blade Flourish (F.1 batch, Lv 3+, XGE).

F.1 Bard subclass batch ship #5. RAW XGE p.16: on Attack
action walking speed +10 ft until end of turn. On weapon
hit, expend 1 BI use to apply one Flourish:
- Defensive: +BI damage + AC until next turn.
- Slashing: +BI damage to nearby creature within 5 ft of target.
- Mobile: +BI damage + push target 5 ft + free reaction-move.

Once per turn.

v1 announce-only — BI roll + applied bonus GM-tracked.

Lyra Lv 6 → walking +10, choice of flourish.

Tests:
  - Lv 3+ happy default Defensive → walking +10, flourish "defensive".
  - flourish="slashing" passthrough.
  - flourish="mobile" passthrough.
  - Wrong subclass → 409.
  - Swords Lv 2 → 409.
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


def _bf_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "blade-flourish"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def lyra_swords(gm_client, roster):
    """PATCH Lyra to College of Swords."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Swords"},
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


async def test_use_bf_happy_lv6_defensive(
    gm_client, gm_ws, lyra_swords,
):
    """Lv 6 Swords default Defensive → walking +10."""
    lyra = lyra_swords
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blade_flourish",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["flourish"] == "defensive"
    assert data["walking_speed_bonus_ft"] == 10
    assert data["consumed_bardic_inspiration"] is True
    assert data["bard_level"] == 6
    await asyncio.sleep(0.3)
    feats = _bf_broadcasts(gm_ws, lyra["id"])
    assert feats


async def test_use_bf_slashing(
    gm_client, lyra_swords,
):
    """flourish='slashing' passes through."""
    lyra = lyra_swords
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blade_flourish",
        json={"character_id": lyra["id"], "flourish": "slashing"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["flourish"] == "slashing"


async def test_use_bf_mobile(
    gm_client, lyra_swords,
):
    """flourish='mobile' passes through."""
    lyra = lyra_swords
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blade_flourish",
        json={"character_id": lyra["id"], "flourish": "mobile"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["flourish"] == "mobile"


async def test_use_bf_wrong_subclass(
    gm_client, roster,
):
    """Default Lyra (Lore) → 409."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_blade_flourish",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_bf_level_gate(
    gm_client, roster,
):
    """Swords Lyra at Lv 2 → 409."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Swords", "level": 2},
        class_slug="bard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_blade_flourish",
            json={"character_id": lyra["id"]},
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
