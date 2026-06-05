"""v2.99.320 — Valor College Bard: Combat Inspiration (F.1 opener, Lv 3+).

F.1 Bard subclass batch opener. RAW PHB p.55: a creature
with a Bardic Inspiration die from you can roll that die and
add it to a weapon damage roll OR (reaction) to its AC vs an
attack.

Die size follows the BI table: d6 (Lv 3-4), d8 (Lv 5-9),
d10 (Lv 10-14), d12 (Lv 15+).

v1 announce-only — actual BI roll + application is via the
existing BI flow. No chip — this endpoint declares intent.

Lyra is Lv 6 Lore Bard — PATCH'd to Valor for testing.

Tests:
  - Lv 6 happy default (damage) → 1d8.
  - Mode "ac" passes through.
  - Default missing mode → "damage".
  - Wrong subclass (Lore) → 409.
  - Valor Lv 2 → 409.
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


def _ci_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "combat-inspiration"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def lyra_valor(gm_client, roster):
    """PATCH Lyra to College of Valor."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Valor"},
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


async def test_use_ci_happy_lv6(
    gm_client, gm_ws, lyra_valor,
):
    """Lv 6 Valor default → 1d8 damage."""
    lyra = lyra_valor
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_combat_inspiration",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "damage"
    assert data["die_size"] == 8
    assert data["die_expression"] == "1d8"
    assert data["bard_level"] == 6
    await asyncio.sleep(0.3)
    feats = _ci_broadcasts(gm_ws, lyra["id"])
    assert feats


async def test_use_ci_mode_ac(
    gm_client, lyra_valor,
):
    """Mode 'ac' passes through."""
    lyra = lyra_valor
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_combat_inspiration",
        json={"character_id": lyra["id"], "mode": "ac"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "ac"


async def test_use_ci_default_mode(
    gm_client, lyra_valor,
):
    """Missing mode → 'damage'."""
    lyra = lyra_valor
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_combat_inspiration",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "damage"


async def test_use_ci_wrong_subclass(
    gm_client, roster,
):
    """Default Lyra (Lore) → 409."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_combat_inspiration",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ci_level_gate(
    gm_client, roster,
):
    """Valor Lyra at Lv 2 → 409."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Valor", "level": 2},
        class_slug="bard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_combat_inspiration",
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
