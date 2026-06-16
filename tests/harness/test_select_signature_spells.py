"""v2.99.218 — Signature Spells (Wizard Lv 20).

Phase F.5 final of the v2.99.193 phased completion plan —
**Phase F.5 ✅ COMPLETE (2/2)**. RAW PHB p.115: "Choose two
3rd-level wizard spells in your spellbook as your signature
spells. You always have these spells prepared, they don't
count against the number of spells you have prepared, and you
can cast each of them once at 3rd level without expending a
spell slot. When you do so, you can't do so again until you
finish a short or long rest."

v1 ships `/select_signature_spells` — picker endpoint that
validates Wizard Lv 20+ + both slugs on the spells list at
level 3 + persists `signature_spells = {spell_1, spell_2,
spell_1_used, spell_2_used}`. The use flags reset on short
or long rest (filed `/rest` hook); the free-cast wiring at
`/cast_spell` is filed (one-line follow-up).

Mirrors v2.99.217 Spell Mastery's picker shape.

Tests:
  - Happy: Thalindra Lv 20 → select Fireball + Counterspell.
  - Gate: Lv 7 → 409 level_too_low.
  - Gate: pick a non-L3 spell → 409.
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


def _ss_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "signature-spells"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def thalindra_lv20(gm_client, roster):
    """PATCH Thalindra to Lv 20. Restore Lv 7 in teardown."""
    thalindra = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thalindra["id"], {"level": 20},
        class_slug="wizard",
    )
    yield thalindra
    await _patch_sheet(
        gm_client, thalindra["id"], {"level": 7},
        class_slug="wizard",
    )
    await _patch_sheet(
        gm_client, thalindra["id"], {"signature_spells": {}},
    )


async def test_select_signature_spells_happy_path(
    gm_client, gm_ws, thalindra_lv20,
):
    """Thalindra Lv 20 → select Fireball + Counterspell."""
    thalindra = thalindra_lv20
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_signature_spells",
        json={
            "character_id": thalindra["id"],
            "spell_1_slug": "fireball",
            "spell_2_slug": "counterspell",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["spell_1_slug"] == "fireball"
    assert data["spell_2_slug"] == "counterspell"
    await asyncio.sleep(0.3)
    feats = _ss_broadcasts(gm_ws, thalindra["id"])
    assert feats


async def test_select_signature_spells_level_gate(
    gm_client, roster,
):
    """Control: Thalindra at Lv 7 → 409 level_too_low."""
    thalindra = roster["Thalindra Moonwhisper"]
    # v2.368.1 — explicitly restore Thalindra to her seed Lv 7 so a
    # prior `thalindra_lv20` (or sibling `thalindra_lv18`) fixture
    # whose teardown failed mid-flight doesn't poison this control.
    # Idempotent — no effect when Thalindra is already at Lv 7.
    await _patch_sheet(
        gm_client, thalindra["id"], {"level": 7},
        class_slug="wizard",
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_signature_spells",
        json={
            "character_id": thalindra["id"],
            "spell_1_slug": "fireball",
            "spell_2_slug": "counterspell",
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "level_too_low"
    assert data.get("required") == 20


async def test_select_signature_spells_non_l3_spell(
    gm_client, thalindra_lv20,
):
    """Gate: Magic Missile is L1, not L3 → 409 spell_1_not_on_list."""
    thalindra = thalindra_lv20
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_signature_spells",
        json={
            "character_id": thalindra["id"],
            "spell_1_slug": "magic-missile",  # L1, not L3
            "spell_2_slug": "counterspell",
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "spell_1_not_on_list"
    assert data.get("expected_level") == 3
