"""v2.99.371 — Psi Warrior Fighter: Protective Field (G Fighter sweep #2, Lv 3+, TCE).

Phase G Fighter martial archetype sweep ship #2 — Psi Warrior
opens.
RAW TCE p.40: as a reaction, when you or a creature within 30 ft
takes damage, expend a Psionic Energy die and reduce the damage by
the roll + your INT modifier (min 1). The die scales with Fighter
level (d6/d8/d10/d12).

v1 announce-only — the damage reduction application + the Psionic
Energy dice pool are GM-tracked. The die + INT mod are rolled
server-side. Reaction chip.

Garrik Ironside (Fighter, PATCHed to Psi Warrior Lv 9) is the demo
fixture (Psionic Energy die 1d8 at Lv 5-10).

Tests:
  - Lv 9 happy: reduction >= 1, die 1d8, reaction.
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


def _pf_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "protective-field"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def garrik_psi(gm_client, roster):
    """PATCH Garrik to Psi Warrior; restore to Champion on teardown."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Psi Warrior"},
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


async def test_use_pf_happy_lv9(
    gm_client, gm_ws, garrik_psi,
):
    """Lv 9 Psi Warrior → reduction >= 1, 1d8 Psionic Energy die."""
    garrik = garrik_psi
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_protective_field",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "protective-field"
    assert data["psionic_die"] == "1d8"
    assert 1 <= data["die_roll"] <= 8
    assert data["reduction"] == max(1, data["die_roll"] + data["int_mod"])
    assert data["reduction"] >= 1
    assert data["fighter_level"] == 9
    await asyncio.sleep(0.3)
    feats = _pf_broadcasts(gm_ws, garrik["id"])
    assert feats
    assert feats[-1]["data"]["reduction"] == data["reduction"]


async def test_use_pf_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_protective_field",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_pf_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_protective_field",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
