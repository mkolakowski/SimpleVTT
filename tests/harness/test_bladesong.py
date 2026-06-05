"""v2.99.334 — Bladesinging Wizard: Bladesong (G.1 batch, Lv 2+, TCE).

G.1 Wizard subclass batch ship #8 (pivot from Sculpt Spells
which was already wired in v2.99.225 / Phase E.7).

RAW TCE p.74: bonus action to start 1-min bladesong. Benefits
while active: +CHA mod (min +1) to AC; +10 ft walking speed;
advantage on Dex (Acrobatics); +INT mod (min +1) to
concentration; +INT mod to one weapon damage per turn. Ends
when incapacitated, donning medium/heavy armor or shield,
holding two-handed weapon, or re-activation. Twice per short
or long rest.

v1 announce-only — buff application GM-tracked. Costs bonus
chip. Auto-bootstraps `bladesong-uses` resource (max=2,
reset=short).

Thalindra Lv 7 INT 16 mod 3, CHA 10 mod 0 → AC bonus 1
(min(1, CHA)), int_mod 3.

Tests:
  - Lv 7 happy → AC +1, speed +10, INT +3, damage +3.
  - Wrong subclass → 409.
  - Bladesinging Lv 1 → 409.
  - Back-to-back twice → 200; third → 409 no_uses_left.
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


def _bs_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "bladesong"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def thalindra_bladesinging(gm_client, roster):
    """PATCH Thalindra to Bladesinging + long-rest to refill."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "Bladesinging"},
        class_slug="wizard",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    try:
        yield thal
    finally:
        await _patch_sheet(
            gm_client, thal["id"],
            {"subclass": "School of Evocation", "level": 7},
            class_slug="wizard",
        )


async def test_use_bs_happy_lv7(
    gm_client, gm_ws, thalindra_bladesinging,
):
    """Lv 7 Bladesinging → AC +1, speed +10, INT bonuses 3."""
    thal = thalindra_bladesinging
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bladesong",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ac_bonus"] == 1  # max(1, CHA mod 0) → 1
    assert data["speed_bonus_ft"] == 10
    assert data["concentration_bonus"] == 3  # INT mod 3
    assert data["weapon_damage_bonus_per_turn"] == 3
    assert data["duration_minutes"] == 1
    assert data["uses_remaining"] == 1
    assert data["wizard_level"] == 7
    await asyncio.sleep(0.3)
    feats = _bs_broadcasts(gm_ws, thal["id"])
    assert feats


async def test_use_bs_wrong_subclass(
    gm_client, roster,
):
    """Default Thalindra (Evocation) → 409."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bladesong",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_bs_level_gate(
    gm_client, roster,
):
    """Bladesinging Thalindra at Lv 1 → 409."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "Bladesinging", "level": 1},
        class_slug="wizard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_bladesong",
            json={"character_id": thal["id"], "override": True},
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


async def test_use_bs_two_uses_then_out(
    gm_client, thalindra_bladesinging,
):
    """First → uses_remaining 1. Second → 0. Third → 409."""
    thal = thalindra_bladesinging
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bladesong",
        json={"character_id": thal["id"], "override": True},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["uses_remaining"] == 1

    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bladesong",
        json={"character_id": thal["id"], "override": True},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["uses_remaining"] == 0

    r3 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bladesong",
        json={"character_id": thal["id"], "override": True},
    )
    assert r3.status_code == 409, r3.text
    assert r3.json().get("error") == "no_uses_left"
