"""v2.217.0 — ability-score override engine Phase 4: Potion of Giant
Strength (RAW DMG p.187), the TIMED half of the substrate. Drinking sets
the drinker's Strength to a giant's value for 1 hour (no concentration,
no attunement) — RAW max(base, set), enforced downstream in
`effective_ability_score`. See docs/plans/str-override.md.

Unlike the Belt of Giant Strength (Phase 1, an equipped-item override),
the potion installs a timed `giant-strength` buff carrying
`effects.ability_set`. The buff is mirrored onto the sheet as
`_buffs_active`, and the v2.217.0 fold in `_equipped_item_effects` reads
it — so every override consumer (sheet display, /roll, /sheet-json carry,
attacks) picks up the timed STR set with no new read site.

Demo fixture: Thalindra Moonwhisper (Wizard Lv 7, base STR 8 → mod -1,
120 lb carry cap) carries a Potion of Hill Giant Strength (STR 21). She
has no equipped STR override, so the drink is the sole source — a clean
control. After drinking:
  - effective STR 21, modifier +5.
  - carry capacity 21 × 15 = 315 lb.
  - a STR save picks up the +6 modifier delta (mod +5 − base mod -1).

The drink needs an active battle (the buff install is best-effort — it
only lands when the drinker is in init), so the fixture stands up a
one-combatant battle, then tears it down + clears the mirrored buff +
restores the consumed potion on teardown.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_POTION_SLUG = "potion-of-giant-strength"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _potion_index(inventory):
    for i, it in enumerate(inventory):
        if isinstance(it, dict) and (it.get("_slug") or "") == _POTION_SLUG:
            return i
    return -1


def _tok(char):
    return {
        "id": f"tok_giant_{char['id']}",
        "char_id": char["id"], "name": char["name"],
        "initiative": 10, "hp_current": 37, "hp_max": 37,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


@pytest_asyncio.fixture
async def battle_thalindra(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    data = await _sheet_json(gm_client, thal["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_tok(thal)],
              "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield thal, inv
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/sheet-fields",
            json={"inventory": snapshot, "_buffs_active": []},
        )
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1,
                  "active": False},
        )


async def _drink(gm_client, char_id, idx):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/use_item_action",
        json={"inventory_index": idx, "action_key": "drink"},
    )


async def test_giant_strength_potion_sets_str_on_sheet_json(
    gm_client, battle_thalindra,
):
    """Drinking the potion sets effective STR to 21 (mod +5) over base 8
    via `derived.effective_abilities.STR` — the timed buff folds into the
    same override surface the Belt of Giant Strength uses."""
    thal, inv = battle_thalindra
    idx = _potion_index(inv)
    assert idx >= 0, "Thalindra must carry a Potion of Giant Strength"

    drink = await _drink(gm_client, thal["id"], idx)
    assert drink.status_code == 200, drink.text
    body = drink.json()
    assert body["buff_key"] == "giant-strength", body
    assert body["buff_installed"] is True, body

    data = await _sheet_json(gm_client, thal["id"])
    eff = (data.get("derived") or {}).get("effective_abilities") or {}
    assert "STR" in eff, f"expected a STR override entry, got: {eff!r}"
    assert eff["STR"]["base"] == 8
    assert eff["STR"]["effective"] == 21
    assert eff["STR"]["modifier"] == 5
    assert "Giant Strength" in str(eff["STR"]["source"]), eff["STR"]


async def test_giant_strength_potion_raises_carry_capacity(
    gm_client, battle_thalindra,
):
    """The boosted STR flows into carry capacity: 21 × 15 = 315 lb (up
    from the base 8 × 15 = 120 lb)."""
    thal, inv = battle_thalindra
    idx = _potion_index(inv)
    assert idx >= 0

    before = await _sheet_json(gm_client, thal["id"])
    cap_before = ((before.get("derived") or {}).get("carry") or {}).get(
        "carry_capacity_lb"
    )
    assert cap_before == 120, f"expected base cap 120, got {cap_before!r}"

    drink = await _drink(gm_client, thal["id"], idx)
    assert drink.status_code == 200, drink.text

    after = await _sheet_json(gm_client, thal["id"])
    cap_after = ((after.get("derived") or {}).get("carry") or {}).get(
        "carry_capacity_lb"
    )
    assert cap_after == 315, f"expected boosted cap 315, got {cap_after!r}"


async def test_giant_strength_potion_adds_str_save_override_delta(
    gm_client, battle_thalindra,
):
    """A `str_save` roll picks up the +6 modifier delta (mod +5 −
    base mod -1) with the potion attributed in the breakdown."""
    thal, inv = battle_thalindra
    idx = _potion_index(inv)
    assert idx >= 0

    drink = await _drink(gm_client, thal["id"], idx)
    assert drink.status_code == 200, drink.text

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20-1",
            "stat_key": "str_save",
            "character_id": thal["id"],
            "note": "STR save (giant strength test)",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    breakdown = resp.json().get("breakdown", "")
    assert "+6" in breakdown and "Giant Strength" in breakdown, (
        f"expected +6 giant-strength delta in save breakdown, got: "
        f"{breakdown!r}"
    )
