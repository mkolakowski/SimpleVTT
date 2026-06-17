"""v2.396.0 — Hill Dwarf Stonecunning History check (race-features
plan Phase 2).

RAW PHB p.20: "Whenever you make an Intelligence (History) check
related to the origin of stonework, you are considered proficient in
the History skill and add double your proficiency bonus to the check,
instead of your normal proficiency bonus." Race-gated to Dwarf (any
subrace — Hill / Mountain / generic via `_race_slug_from_sheet`).

New endpoint `POST /api/campaign/{cid}/check_stonecunning` rolls
``1d20 + INT mod + 2 × PB`` and broadcasts a `feature_used` event
with `source: "stonecunning"` so chat-card / harness can attribute
the bonus. The optional free-text `note` echoes back as
"(topic: <note>)" in the feature description.

Test strategy (4 tests):
1. Happy path — Tavik (Hill Dwarf Cleric Lv 8) rolls; 200 with
   total = d20_value + INT mod (+0) + 2× PB (+3 → +6); breakdown
   contains the 2× PB modifier; feature_used broadcast carries
   source="stonecunning" + stat_key="history" + the right math.
2. Non-Dwarf 409 — Pip (Lightfoot Halfling) hits the endpoint and
   gets 409 race_not_dwarf. Race-gate regression guard.
3. Missing character_id 400 — body without character_id is rejected
   at the input gate.
4. Note echo — Tavik with note="Origin of these temple walls" gets
   the note back in the response + the feature_desc broadcast.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def tavik_rested(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    return tavik


@pytest_asyncio.fixture
async def pip_rested(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    return pip


async def test_stonecunning_rolls_with_double_pb(
    gm_client, gm_ws, tavik_rested,
):
    """Tavik (Hill Dwarf, INT 10 → +0 mod, PB +3): the endpoint
    rolls 1d20 + 0 + (2 × 3) = 1d20 + 6. Total should be in
    [7, 26]; breakdown should mention +6. feature_used broadcast
    fires with source=stonecunning + the right ability/PB fields."""
    tavik = tavik_rested
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/check_stonecunning",
        json={"character_id": tavik["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["int_mod"] == 0
    assert data["proficiency_bonus"] == 3
    assert data["double_pb"] == 6
    # Total = d20 + INT mod + 2*PB = 1..20 + 0 + 6 = 7..26.
    assert 7 <= data["total"] <= 26, (
        f"total out of expected [7, 26] range; got {data['total']}"
    )
    # Expression should be "1d20+6".
    assert "+6" in data["expression"], (
        f"expected '+6' in expression; got {data['expression']!r}"
    )

    await asyncio.sleep(0.2)
    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "stonecunning"
        and (m.get("data") or {}).get("character_id") == tavik["id"]
    ]
    assert fu, (
        f"expected feature_used(source=stonecunning); buffered sources: "
        f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
    )
    fu_data = fu[-1]["data"]
    assert fu_data["stat_key"] == "history"
    assert fu_data["stat_ability"] == "INT"
    assert fu_data["double_pb"] == 6
    assert fu_data["int_mod"] == 0
    assert fu_data["proficiency_bonus"] == 3


async def test_stonecunning_rejects_non_dwarf(gm_client, pip_rested):
    """Control: Pip (Lightfoot Halfling) hits the endpoint and gets
    409 race_not_dwarf. Race-gate regression guard against the trait
    firing for non-Dwarves."""
    pip = pip_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/check_stonecunning",
        json={"character_id": pip["id"]},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "race_not_dwarf"
    assert body["char_name"] == pip["name"]
    # Demo seed stores Pip's race as plain "Halfling" (the Lightfoot
    # subrace is the v2.99.13 _race_slug_from_sheet default). Accept
    # either form so a future Stout-Halfling subrace demo doesn't
    # regress the assertion.
    assert "halfling" in (body["got_race"] or "").lower()


async def test_stonecunning_missing_character_id_400(gm_client):
    """Body without character_id is rejected at the input gate."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/check_stonecunning",
        json={},
    )
    assert resp.status_code == 400


async def test_stonecunning_echoes_note(gm_client, gm_ws, tavik_rested):
    """When the caller passes a free-text `note`, it echoes back in
    the response + appears in the feature_desc broadcast string
    (verbatim, truncated to 200 chars)."""
    tavik = tavik_rested
    note = "Origin of these temple walls"
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/check_stonecunning",
        json={"character_id": tavik["id"], "note": note},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["note"] == note

    await asyncio.sleep(0.2)
    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "stonecunning"
        and (m.get("data") or {}).get("character_id") == tavik["id"]
    ]
    assert fu
    fu_data = fu[-1]["data"]
    assert fu_data["note"] == note
    assert note in (fu_data.get("feature_desc") or "")
