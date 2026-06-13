"""v2.226.0 — Belt of Dwarvenkind: the first magic item to compose TWO
existing override substrates in a single passive payload (RAW DMG p.155,
rare, attunement).

The belt carries both:
  - a capped-additive **CON +2 to max 20** — the v2.224.0 `ability_bonus`
    substrate (same engine as the Ioun Stone of Fortitude), and
  - **darkvision 60 ft** — the v2.159.24 `sees_in_darkness` substrate
    (same field as Goggles of Night).

Neither needed new engine code: both fields already aggregate in
`_equipped_item_effects` and flow to `/sheet-json` (effective CON) and the
darkness-blinded `/attack` path. This file proves the single payload lights
up both surfaces at once.

Demo fixture: Quan Reelstep (Way of the Drunken Master Monk, Human, base
CON 14 → mod +2). He wears an equipped + attuned Belt of Dwarvenkind — his
1st attuned item (he had none). Effective CON 16 (mod +3, a clean +1 delta),
and as a Human (non-dwarf) he qualifies for the belt's darkvision gate.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_BELT_SLUG = "belt-of-dwarvenkind"


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def quan(roster):
    return roster["Quan Reelstep"]


async def test_belt_exposes_effective_con_on_sheet_json(gm_client, quan):
    """`derived.effective_abilities.CON` reports base 14, effective 16,
    modifier +3 — a pure additive +2 bonus (well under the 20 cap), sourced
    to the belt."""
    data = await _sheet_json(gm_client, quan["id"])
    eff = (data.get("derived") or {}).get("effective_abilities") or {}
    assert "CON" in eff, f"expected a CON override entry, got: {eff!r}"
    assert eff["CON"]["base"] == 14
    assert eff["CON"]["effective"] == 16
    assert eff["CON"]["modifier"] == 3
    assert "Belt of Dwarvenkind" in str(eff["CON"]["source"]), eff["CON"]


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants,
            "turn_index": 0,
            "round": 1,
            "active": True,
        },
    )


def _mkc(cid, char_id=None, hp_cur=40, hp_max=40, name="X", buffs=None):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur,
        "hp_max": hp_max,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def test_belt_darkvision_negates_darkness_blinded_disadvantage(
    gm_client, quan, roster,
):
    """The belt's `sees_in_darkness` cancels the darkness-blinded attack
    disadvantage exactly as Goggles of Night do — proving the second
    substrate field rides the same payload."""
    tavik = roster["Brother Tavik Stonebrow"]
    quan_cid = f"tok_belt1_{quan['id']}"
    tavik_cid = f"tok_belt1_tavik_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(quan_cid, quan["id"], name="Quan", buffs=[{
            "key": "blinded",
            "name": "Blinded (Darkness)",
            "effects": {"from_darkness": True},
        }]),
        _mkc(tavik_cid, tavik["id"], name="Tavik"),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": quan["id"],
            "attack_index": 0,
            "target_combatant_id": tavik_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    breakdown = data.get("attack_breakdown") or ""
    assert "2d20kl1" not in breakdown, (
        f"Belt darkvision should cancel darkness-blind disadvantage; "
        f"got {breakdown!r}"
    )
    assert data.get("roll_state_applied") != "disadvantage_attacker_blinded", (
        f"roll_state_applied should not flag blinded disadvantage; "
        f"got {data.get('roll_state_applied')!r}"
    )


async def test_belt_unequip_reverts_con_bonus(gm_client, quan):
    """Unequipping the belt reverts the CON bonus. Restores the original
    inventory on teardown."""
    data = await _sheet_json(gm_client, quan["id"])
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _BELT_SLUG),
        None,
    )
    assert idx is not None, "Quan has no belt-of-dwarvenkind item"
    try:
        inv[idx] = {**inv[idx], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{quan['id']}/sheet-fields",
            json={"inventory": inv},
        )
        data2 = await _sheet_json(gm_client, quan["id"])
        eff2 = (data2.get("derived") or {}).get("effective_abilities") or {}
        assert "CON" not in eff2, (
            f"expected no CON override after unequip, got: {eff2!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{quan['id']}/sheet-fields",
            json={"inventory": snapshot},
        )
