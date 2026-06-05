"""v2.99.337 — Chronurgy Magic Wizard: Chronal Shift (G.1 batch, Lv 2+, EGtW).

G.1 Wizard subclass batch ship #12. RAW EGtW p.184: reaction
when self or a seen creature within 30 ft makes an attack roll,
ability check, or saving throw — force a reroll; new roll
is used. Twice per long rest.

v1 announce-only — actual reroll application GM-tracked.
Costs a reaction chip. Auto-bootstraps `chronal-shift` resource
(max=2, reset=long).

Tests:
  - Lv 7 happy → uses_remaining 1.
  - Two uses then out (3rd → 409 no_uses_left).
  - Wrong subclass → 409.
  - Chronurgy Lv 1 → 409.
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


def _cs_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "chronal-shift"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def thalindra_chronurgy(gm_client, roster):
    """PATCH Thalindra to Chronurgy Magic."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "Chronurgy Magic"},
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


async def test_use_cs_happy_lv7(
    gm_client, gm_ws, thalindra_chronurgy,
):
    """Lv 7 Chronurgy → uses_remaining 1."""
    thal = thalindra_chronurgy
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_chronal_shift",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "chronal-shift"
    assert data["uses_remaining"] == 1
    assert data["uses_max"] == 2
    assert data["wizard_level"] == 7
    await asyncio.sleep(0.3)
    feats = _cs_broadcasts(gm_ws, thal["id"])
    assert feats


async def test_use_cs_two_uses_then_out(
    gm_client, thalindra_chronurgy,
):
    """1st → 1; 2nd → 0; 3rd → 409 no_uses_left."""
    thal = thalindra_chronurgy
    for expected in (1, 0):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_chronal_shift",
            json={"character_id": thal["id"], "override": True},
        )
        assert r.status_code == 200, r.text
        assert r.json()["uses_remaining"] == expected
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_chronal_shift",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    assert r.json().get("error") == "no_uses_left"


async def test_use_cs_wrong_subclass(
    gm_client, roster,
):
    """Default Thalindra (Evocation) → 409."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_chronal_shift",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_cs_level_gate(
    gm_client, roster,
):
    """Chronurgy Thalindra at Lv 1 → 409."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "Chronurgy Magic", "level": 1},
        class_slug="wizard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_chronal_shift",
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
