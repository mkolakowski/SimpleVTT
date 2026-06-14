"""v2.288.0 — Periapt of Proof against Poison (RAW DMG p.184, rare, NO
attunement).

First item on the v2.288.0 item-passive IMMUNITY substrate (the parallel of
the v2.235.0 resistance substrate): the `immunity_to: ["poison"]` payload
folds into the aggregated `immunity_to` list that `_immunity_zero` consults
(zeroes poison damage), and `condition_immunity_to: ["poisoned"]` folds into
the list that `_target_condition_immune` consults (blocks the poisoned
buff-install). Both surface on `/sheet-json` as `derived.immunities` /
`derived.condition_immunities`.

Demo fixture: Garrik Ironside (Fighter) carries the periapt as inert spare
loot (equipped=False) — he has no poison-immunity baseline. The tests PATCH
it equipped, read the derived projections, then restore the seed inventory.
No attunement, so only `equipped` is toggled.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_PERIAPT_SLUG = "periapt-of-proof-against-poison"


@pytest_asyncio.fixture
async def garrik(roster):
    return roster["Garrik Ironside"]


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _equip_and_read_derived(gm_client, char_id):
    """PATCH the spare periapt ON (equipped), read /sheet-json, then restore
    the original inventory. Returns the post-equip derived block."""
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _PERIAPT_SLUG:
            it["equipped"] = True
            found = True
    assert found, "Garrik has no periapt-of-proof-against-poison item"
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    try:
        data2 = await _sheet_json(gm_client, char_id)
        return data2.get("derived") or {}
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_periapt_grants_poison_damage_immunity(gm_client, garrik):
    """Happy path: equipping the periapt surfaces `derived.immunities` with
    "poison" in types and the periapt named in sources."""
    derived = await _equip_and_read_derived(gm_client, garrik["id"])
    imm = derived.get("immunities")
    assert imm is not None, f"expected derived.immunities, got: {derived!r}"
    assert "poison" in (imm.get("types") or []), (
        f"expected 'poison' in immunity types, got: {imm!r}"
    )
    assert any(
        "Periapt of Proof against Poison" in str(s)
        for s in imm.get("sources") or []
    ), f"expected the periapt named in sources, got: {imm!r}"


async def test_periapt_grants_poisoned_condition_immunity(gm_client, garrik):
    """The condition half: equipping the periapt surfaces
    `derived.condition_immunities` with "poisoned" in types."""
    derived = await _equip_and_read_derived(gm_client, garrik["id"])
    cond = derived.get("condition_immunities")
    assert cond is not None, (
        f"expected derived.condition_immunities, got: {derived!r}"
    )
    assert "poisoned" in (cond.get("types") or []), (
        f"expected 'poisoned' in condition-immunity types, got: {cond!r}"
    )


async def test_periapt_baseline_has_no_immunity(gm_client, garrik):
    """Control: with the periapt inert (seed state), Garrik has no
    item-sourced poison immunity — proving it's periapt-sourced, not baked
    in. (His baseline derived carries no `immunities`/`condition_immunities`
    projection from this item.)"""
    data = await _sheet_json(gm_client, garrik["id"])
    derived = data.get("derived") or {}
    imm = derived.get("immunities") or {}
    cond = derived.get("condition_immunities") or {}
    assert "poison" not in (imm.get("types") or []), (
        f"unexpected baseline poison immunity, got: {imm!r}"
    )
    assert "poisoned" not in (cond.get("types") or []), (
        f"unexpected baseline poisoned-condition immunity, got: {cond!r}"
    )
