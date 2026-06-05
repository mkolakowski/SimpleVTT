"""v2.99.327 — Abjuration School Wizard: Arcane Ward (G.1 opener, Lv 2+).

G.1 Wizard subclass batch opener. RAW PHB p.115: when you
cast an abjuration spell of 1st level or higher, you create a
magical ward on yourself. Ward HP = 2 × wizard_level + INT mod.
Refills 2 × spell-level HP per abjuration cast. Lasts until
long rest. Once per long rest creation.

v1 announce-only — actual damage-absorption hook is GM-tracked;
ward HP is tracked as an `arcane-ward-hp` resource.

Thalindra Lv 7 INT 16 mod 3 → ward max HP = 17.

Tests:
  - Lv 7 happy → ward_hp_max 17 (2*7 + 3).
  - Wrong subclass → 409.
  - Abjuration Lv 1 → 409.
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


def _aw_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "arcane-ward"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def thalindra_abjuration(gm_client, roster):
    """PATCH Thalindra to School of Abjuration."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "School of Abjuration"},
        class_slug="wizard",
    )
    try:
        yield thal
    finally:
        await _patch_sheet(
            gm_client, thal["id"],
            {"subclass": "School of Evocation", "level": 7},
            class_slug="wizard",
        )


async def test_use_aw_happy_lv7(
    gm_client, gm_ws, thalindra_abjuration,
):
    """Lv 7 Abjuration, INT 16 mod 3 → ward HP 17."""
    thal = thalindra_abjuration
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_ward",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ward_hp_max"] == 17
    assert data["wizard_level"] == 7
    assert data["int_mod"] == 3
    await asyncio.sleep(0.3)
    feats = _aw_broadcasts(gm_ws, thal["id"])
    assert feats


async def test_use_aw_wrong_subclass(
    gm_client, roster,
):
    """Default Thalindra (Evocation) → 409."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_ward",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_aw_level_gate(
    gm_client, roster,
):
    """Abjuration Thalindra at Lv 1 → 409."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "School of Abjuration", "level": 1},
        class_slug="wizard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_arcane_ward",
            json={"character_id": thal["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, thal["id"],
            {"subclass": "School of Evocation", "level": 7},
            class_slug="wizard",
        )
