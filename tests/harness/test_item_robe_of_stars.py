"""v2.287.0 — Robe of Stars (RAW DMG p.193, very rare, attunement).

A pure data drop-in on the v2.158.74 ``save_bonus`` substrate (same path
as Cloak of Protection / Stone of Good Luck): "+1 bonus to saving throws
while you wear it." The magic-missile stars and the Astral-Plane travel
clause are GM-narrated in v1.

Demo fixture: Thalindra Moonwhisper (Wizard) carries the robe as inert
spare loot (equipped=False / attuned=False) — she's already past the RAW
3-item attunement cap. The happy-path test PATCHes the robe equipped +
attuned, rolls a saving throw and asserts the +1 + the source attribution,
then restores the seed inventory. The control + attunement-gate tests use
the same PATCH-then-restore dance.
"""
import re

import pytest_asyncio

from .conftest import CAMPAIGN_ID

_ROBE_SLUG = "robe-of-stars"


def _save_aggregate(breakdown: str) -> int:
    """Parse the summed save bonus from a /roll breakdown, e.g.
    '... => 19 (+4 Cloak of Protection + Robe of Stars)' → 4. Returns 0
    when no aggregate bonus annotation is present."""
    m = re.search(r"\(\+(\d+)", breakdown)
    return int(m.group(1)) if m else 0


@pytest_asyncio.fixture
async def thalindra(roster):
    return roster["Thalindra Moonwhisper"]


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _patch_inventory(gm_client, char_id, inv):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": inv},
    )


async def _save_breakdown(gm_client, char_id):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+2",
            "stat_key": "wis_save",
            "character_id": char_id,
            "note": "WIS save (test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json().get("breakdown", "")


def _set_robe(inv, *, equipped, attuned):
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _ROBE_SLUG:
            it["equipped"], it["attuned"] = equipped, attuned
            found = True
    assert found, "Thalindra has no robe-of-stars item"
    return new_inv


async def test_robe_grants_save_bonus(gm_client, thalindra):
    """Happy path: with the robe PATCHed equipped+attuned, a saving-throw
    roll names the robe in the breakdown and the summed save bonus rises by
    exactly 1 over the inert baseline (Thalindra already stacks Cloak +1 and
    Staff of Power +2, so the literal '+1' is absorbed into the aggregate —
    asserting the delta is robust to those co-equipped save items)."""
    data = await _sheet_json(gm_client, thalindra["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    baseline = _save_aggregate(await _save_breakdown(gm_client, thalindra["id"]))
    try:
        await _patch_inventory(
            gm_client, thalindra["id"], _set_robe(inv, equipped=True, attuned=True)
        )
        breakdown = await _save_breakdown(gm_client, thalindra["id"])
        assert "Robe of Stars" in breakdown, (
            f"expected 'Robe of Stars' in save breakdown, got: {breakdown!r}"
        )
        assert _save_aggregate(breakdown) == baseline + 1, (
            f"expected the summed save bonus to rise by 1 (baseline {baseline}), "
            f"got: {breakdown!r}"
        )
    finally:
        await _patch_inventory(gm_client, thalindra["id"], snapshot)


async def test_robe_baseline_has_no_robe_bonus(gm_client, thalindra):
    """Control: with the robe inert (seed state), the robe contributes no
    save bonus — proving the +1 is robe-sourced, not baked in."""
    breakdown = await _save_breakdown(gm_client, thalindra["id"])
    assert "Robe of Stars" not in breakdown, (
        f"unexpected 'Robe of Stars' in baseline save breakdown, got: {breakdown!r}"
    )


async def test_robe_requires_attunement(gm_client, thalindra):
    """The robe is an attunement item — the +1 only applies while
    ``attuned: True``. Equipped-but-unattuned contributes no robe bonus;
    restores the seed inventory on teardown."""
    data = await _sheet_json(gm_client, thalindra["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    try:
        await _patch_inventory(
            gm_client, thalindra["id"], _set_robe(inv, equipped=True, attuned=False)
        )
        breakdown = await _save_breakdown(gm_client, thalindra["id"])
        assert "Robe of Stars" not in breakdown, (
            f"expected no robe bonus while equipped-but-unattuned, got: {breakdown!r}"
        )
    finally:
        await _patch_inventory(gm_client, thalindra["id"], snapshot)
