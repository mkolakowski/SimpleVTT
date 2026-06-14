"""v2.280.0 — Helm of Brilliance (RAW DMG p.173, very rare, attunement).

Of its several benefits, v1 wires the clean passive: "as long as the helm
has at least one ruby, you have resistance to fire damage." The flat
`resistance_to: "fire"` payload folds into the aggregated `resistance_to`
list that `_resistance_halve` consults in the live damage pipeline (the Ring
of Resistance / Dragon Scale Mail substrate) and surfaces on `/sheet-json` as
`derived.resistances = {types, sources}`. The gem-fueled spells, undead aura,
flaming-weapon rider, and gem-burst hazard are GM-narrated.

Demo fixture: Thalindra Moonwhisper (Wizard) carries the helm as inert spare
loot (equipped=False / attuned=False) — she's already past the attunement cap
and has no fire-resistance baseline (her Wand/Necklace of Fireballs deal fire,
they don't resist it). The tests PATCH it equipped+attuned, read the fire
`derived.resistances`, then restore the seed inventory (and HP for the
damage-pipeline test).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_HELM_SLUG = "helm-of-brilliance"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def thalindra(roster):
    return roster["Thalindra Moonwhisper"]


async def _equip_helm_and_read(gm_client, char_id):
    """PATCH the spare Helm of Brilliance ON (equipped + attuned), read
    /sheet-json, then restore the original inventory. Returns the post-equip
    derived block."""
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _HELM_SLUG:
            it["equipped"], it["attuned"] = True, True
            found = True
    assert found, "Thalindra has no helm-of-brilliance item"
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


async def test_helm_exposes_fire_resistance(gm_client, thalindra):
    """Happy path: equipping the helm surfaces fire in `derived.resistances`,
    with the helm named in its sources."""
    derived = await _equip_helm_and_read(gm_client, thalindra["id"])
    res = derived.get("resistances") or {}
    assert "fire" in (res.get("types") or []), (
        f"expected fire in resistances, got: {res!r}"
    )
    assert any(
        "Helm of Brilliance" in str(s) for s in res.get("sources") or []
    ), f"expected the helm named in resistance sources, got: {res!r}"


async def test_helm_baseline_has_no_fire_resistance(gm_client, thalindra):
    """Control: with the helm inert (seed state), Thalindra has no fire
    resistance — proving it's item-sourced, not baked in."""
    data = await _sheet_json(gm_client, thalindra["id"])
    res = (data.get("derived") or {}).get("resistances") or {}
    assert "fire" not in (res.get("types") or []), (
        f"unexpected baseline fire resistance, got: {res!r}"
    )


async def test_helm_halves_fire_damage(gm_client, thalindra):
    """End-to-end: 20 fire damage to the helm-wearer drops HP by only 10 —
    the equipped helm halves it through `_resistance_halve`. Restores the
    seed inventory AND HP on teardown."""
    data = await _sheet_json(gm_client, thalindra["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    hp = dict((data.get("sheet") or {}).get("hp") or {})
    new_inv = [dict(it) if isinstance(it, dict) else it for it in inv]
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _HELM_SLUG:
            it["equipped"], it["attuned"] = True, True
    try:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
            json={"inventory": new_inv},
        )
        before = int(hp.get("current") or 0)
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
            json={
                "hp": {"current": before - 20},
                "hp_change_reason": "damage",
                "damage_amount": 20,
                "damage_type": "fire",
            },
        )
        data2 = await _sheet_json(gm_client, thalindra["id"])
        after = int(((data2.get("sheet") or {}).get("hp") or {}).get("current") or 0)
        assert after == before - 10, (
            f"fire damage not halved by the helm: {before} → {after} "
            "(expected -10)"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
            json={"inventory": snapshot, "hp": hp},
        )
