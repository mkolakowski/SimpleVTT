"""v2.345.0 — Luck Blade (RAW DMG p.179, legendary, attunement).

First magic-item-content commit off the v2.344.5 stub triage (Bucket B —
passive numeric buff). The clean passive — "while the sword is on your
person, you gain a +1 bonus to saving throws" — rides the v2.158.74
``save_bonus`` substrate (same path as Cloak of Protection / Robe of
Stars). The +1 attack/damage is baked onto the weapon row; the Luck
reroll (1/turn) and the 1d4-1 wish charges are GM-narrated in v1.
Promoted out of the v2.342.0 "Vault" bulk-stub loop into an explicit
mechanical ``_MAGIC_ITEM_PASSIVES`` entry.

Demo fixture: Quan Reelstep carries the blade as inert spare loot
(equipped=False / attuned=False). The happy-path test PATCHes it
equipped + attuned, rolls a saving throw and asserts the +1 + the
source attribution, then restores the seed inventory. The control +
attunement-gate tests use the same PATCH-then-restore dance.
"""
import re

import pytest_asyncio

from .conftest import CAMPAIGN_ID

_BLADE_SLUG = "luck-blade"


def _save_aggregate(breakdown: str) -> int:
    """Parse the summed save bonus from a /roll breakdown, e.g.
    '... => 19 (+4 Cloak of Protection + Luck Blade)' → 4. Returns 0
    when no aggregate bonus annotation is present."""
    m = re.search(r"\(\+(\d+)", breakdown)
    return int(m.group(1)) if m else 0


@pytest_asyncio.fixture
async def quan(roster):
    return roster["Quan Reelstep"]


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


def _set_blade(inv, *, equipped, attuned):
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _BLADE_SLUG:
            it["equipped"], it["attuned"] = equipped, attuned
            found = True
    assert found, "Quan has no luck-blade item"
    return new_inv


async def test_luck_blade_grants_save_bonus(gm_client, quan):
    """Happy path: with the blade PATCHed equipped+attuned, a saving-throw
    roll names the blade in the breakdown and the summed save bonus rises by
    exactly 1 over the inert baseline (asserting the delta is robust to any
    co-equipped save items)."""
    data = await _sheet_json(gm_client, quan["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    baseline = _save_aggregate(await _save_breakdown(gm_client, quan["id"]))
    try:
        await _patch_inventory(
            gm_client, quan["id"], _set_blade(inv, equipped=True, attuned=True)
        )
        breakdown = await _save_breakdown(gm_client, quan["id"])
        assert "Luck Blade" in breakdown, (
            f"expected 'Luck Blade' in save breakdown, got: {breakdown!r}"
        )
        assert _save_aggregate(breakdown) == baseline + 1, (
            f"expected the summed save bonus to rise by 1 (baseline {baseline}), "
            f"got: {breakdown!r}"
        )
    finally:
        await _patch_inventory(gm_client, quan["id"], snapshot)


async def test_luck_blade_baseline_has_no_blade_bonus(gm_client, quan):
    """Control: with the blade inert (seed state), it contributes no save
    bonus — proving the +1 is blade-sourced, not baked in."""
    breakdown = await _save_breakdown(gm_client, quan["id"])
    assert "Luck Blade" not in breakdown, (
        f"unexpected 'Luck Blade' in baseline save breakdown, got: {breakdown!r}"
    )


async def test_luck_blade_requires_attunement(gm_client, quan):
    """The blade is an attunement item — the +1 only applies while
    ``attuned: True``. Equipped-but-unattuned contributes no blade bonus;
    restores the seed inventory on teardown."""
    data = await _sheet_json(gm_client, quan["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    try:
        await _patch_inventory(
            gm_client, quan["id"], _set_blade(inv, equipped=True, attuned=False)
        )
        breakdown = await _save_breakdown(gm_client, quan["id"])
        assert "Luck Blade" not in breakdown, (
            f"expected no blade bonus while equipped-but-unattuned, got: {breakdown!r}"
        )
    finally:
        await _patch_inventory(gm_client, quan["id"], snapshot)
