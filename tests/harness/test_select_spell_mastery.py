"""v2.99.217 — Spell Mastery (Wizard Lv 18+).

Phase F.5 start of the v2.99.193 phased completion plan. RAW
PHB p.115: "At 18th level, you have achieved such mastery over
certain spells that you can cast them at will. Choose a
1st-level wizard spell and a 2nd-level wizard spell that are
in your spellbook. You can cast those spells at their lowest
level without expending a spell slot when you have them
prepared."

v1 ships `/select_spell_mastery` — picker endpoint that
persists the choice on `sheet.spell_mastery = {l1, l2}`. The
actual free-cast wiring at /cast_spell is filed (one-line
follow-up mirroring v2.99.88 Mystic Arcanum free-cast).

Thalindra Moonwhisper (Wizard Lv 7 default) is the demo
fixture; tests PATCH her Lv 7 → 18 + use her existing
Magic Missile (L1) + Misty Step (L2) picks.

Tests:
  - Happy: Thalindra Lv 18 → select Magic Missile + Misty Step.
  - Gate: Lv 7 → 409 level_too_low.
  - Gate: pick a spell not on the spells list → 409.
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


def _sm_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "spell-mastery"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def thalindra_lv18(gm_client, roster):
    """PATCH Thalindra to Lv 18. Restore in teardown."""
    thalindra = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thalindra["id"], {"level": 18},
        class_slug="wizard",
    )
    yield thalindra
    await _patch_sheet(
        gm_client, thalindra["id"], {"level": 7},
        class_slug="wizard",
    )
    await _patch_sheet(
        gm_client, thalindra["id"], {"spell_mastery": {}},
    )


async def test_select_spell_mastery_happy_path(
    gm_client, gm_ws, thalindra_lv18,
):
    """Thalindra Lv 18 → select Magic Missile (L1) + Misty Step (L2)."""
    thalindra = thalindra_lv18
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_spell_mastery",
        json={
            "character_id": thalindra["id"],
            "l1_spell_slug": "magic-missile",
            "l2_spell_slug": "misty-step",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["l1_spell_slug"] == "magic-missile"
    assert data["l2_spell_slug"] == "misty-step"
    await asyncio.sleep(0.3)
    feats = _sm_broadcasts(gm_ws, thalindra["id"])
    assert feats


async def test_select_spell_mastery_level_gate(
    gm_client, roster,
):
    """Control: Thalindra at Lv 7 → 409 level_too_low."""
    thalindra = roster["Thalindra Moonwhisper"]
    # v2.368.1 — explicitly restore Thalindra to her seed Lv 7 so a
    # prior `thalindra_lv18` fixture whose teardown failed mid-flight
    # doesn't poison this control. Idempotent — no effect when Thalindra
    # is already at Lv 7.
    await _patch_sheet(
        gm_client, thalindra["id"], {"level": 7},
        class_slug="wizard",
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_spell_mastery",
        json={
            "character_id": thalindra["id"],
            "l1_spell_slug": "magic-missile",
            "l2_spell_slug": "misty-step",
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "level_too_low"
    assert data.get("required") == 18


async def test_select_spell_mastery_spell_not_on_list(
    gm_client, thalindra_lv18,
):
    """Gate: pick a spell that's not on the spells list → 409."""
    thalindra = thalindra_lv18
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_spell_mastery",
        json={
            "character_id": thalindra["id"],
            "l1_spell_slug": "alarm",  # not on Thalindra's list
            "l2_spell_slug": "misty-step",
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "l1_spell_not_on_list"
