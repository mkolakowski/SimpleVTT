"""v2.99.378 — Beast Master Ranger: Ranger's Companion (G Ranger conclave #2, Lv 3+, PHB).

Phase G Ranger conclave subclass batch ship #2 — Beast Master
opens.
RAW PHB p.93: you gain a beast companion. Add your proficiency
bonus to its AC, attacks, damage, and proficient saves/skills; its
HP max equals four times your ranger level (or its normal max,
whichever is higher). Command it (Attack/Dash/Disengage/Dodge/Help)
with your action.

v1 announce-only — the companion token + its action resolution are
GM-tracked. The HP floor + PB bonus are computed server-side.
Action chip.

Rowan Quickbow (Ranger, PATCHed to Beast Master Lv 5) is the demo
fixture (HP floor 20, PB 3).

Tests:
  - Lv 5 happy (default attack): hp floor 20, PB 3.
  - Lv 5 happy (help command): command echoes "help".
  - Wrong subclass (default Hunter) → 409.
  - Invalid command → 400.
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


def _rc_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "rangers-companion"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def rowan_beast(gm_client, roster):
    """PATCH Rowan to Beast Master; restore to Hunter on teardown."""
    rowan = roster["Rowan Quickbow"]
    await _patch_sheet(
        gm_client, rowan["id"],
        {"subclass": "Beast Master"},
        class_slug="ranger",
    )
    try:
        yield rowan
    finally:
        await _patch_sheet(
            gm_client, rowan["id"],
            {"subclass": "Hunter"},
            class_slug="ranger",
        )


async def test_use_rc_happy_attack(
    gm_client, gm_ws, rowan_beast,
):
    """Lv 5 Beast Master, default → command attack, HP floor 20, PB 3."""
    rowan = rowan_beast
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rangers_companion",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "rangers-companion"
    assert data["command"] == "attack"
    assert data["companion_hp_floor"] == 20  # 4 x ranger level 5
    assert data["proficiency_bonus"] == 3
    assert data["ranger_level"] == 5
    await asyncio.sleep(0.3)
    feats = _rc_broadcasts(gm_ws, rowan["id"])
    assert feats
    assert feats[-1]["data"]["companion_hp_floor"] == 20


async def test_use_rc_happy_help(
    gm_client, rowan_beast,
):
    """command=help echoes through."""
    rowan = rowan_beast
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rangers_companion",
        json={"character_id": rowan["id"], "command": "help",
              "override": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["command"] == "help"


async def test_use_rc_wrong_subclass(
    gm_client, roster,
):
    """Default Rowan (Hunter) → 409."""
    rowan = roster["Rowan Quickbow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rangers_companion",
        json={"character_id": rowan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_rc_invalid_command(
    gm_client, rowan_beast,
):
    """Invalid command → 400."""
    rowan = rowan_beast
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rangers_companion",
        json={"character_id": rowan["id"], "command": "fetch",
              "override": True},
    )
    assert r.status_code == 400, r.text
