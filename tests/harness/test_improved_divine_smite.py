"""v2.99.153 — Improved Divine Smite (Paladin Lv 11+).

RAW (PHB p.85): "By 11th level, you are so suffused with
righteous might that all your melee weapon strikes carry divine
power with them. Whenever you hit a creature with a melee
weapon, the creature takes an extra 1d8 radiant damage."

v2.99.153 wires this as a separate uplift (radiant damage type)
in `_compute_attack_auto_uplifts`. Two gates:
  1. attack is a melee weapon attack (`_attack_is_melee_weapon`
     — physical-melee damage_type + range ≤ 30 ft)
  2. attacker has Paladin level ≥ 11

Sir Caelan Lightbringer is the Paladin fixture. Stock sheet is
Lv 6 (Aura of Protection prereq, bumped Lv 5 → 6 in v2.53.0)
— below the Lv 11 prerequisite — so the harness PATCHes him to
Lv 11 in the fixture and restores Lv 6 in teardown.

Tests:
  - happy: Caelan at Lv 11 hits Krieger with Longsword → uplift
    fires with `source: improved-divine-smite`,
    `damage_type: radiant`, total in [1, 8]
  - control: Caelan at stock Lv 6 → no uplift even on a melee
    weapon hit (level gate)
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


LONGSWORD_INDEX = 0  # Sir Caelan's attacks list starts with Longsword.


def _mkc(cid, char_id=None, hp_cur=50, hp_max=75, name="X"):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur, "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1,
              "active": True},
    )


async def _try_attack_until_hit(
    gm_client, attacker_id, target_combatant_id, attack_index=0,
):
    """Loop attacks until one lands. Returns the auto_uplifts list
    from the first hit, or None if no hit across 15 attempts.
    """
    for _ in range(15):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": attacker_id,
                "attack_index": attack_index,
                "target_combatant_id": target_combatant_id,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data.get("hit"):
            return data.get("auto_uplifts") or []
    return None


@pytest_asyncio.fixture
async def caelan_at_lv_11(gm_client, roster):
    """PATCH Sir Caelan to Paladin Lv 11 (Improved Divine Smite
    prereq). Restore Lv 6 in teardown.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
        json={"class_slug": "paladin", "level": 11},
    )
    yield caelan
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
        json={"class_slug": "paladin", "level": 6},
    )


async def test_improved_divine_smite_fires_on_melee_hit_at_lv_11(
    gm_client, caelan_at_lv_11, roster,
):
    """Caelan at Lv 11 swings the Longsword at Krieger. On a hit,
    auto_uplifts should contain an `improved-divine-smite` entry
    with damage_type "radiant" and total in [1, 8].
    """
    caelan = caelan_at_lv_11
    krieger = roster["Krieger Stonefist"]
    cae_tok = f"tok_ids_cae_{caelan['id']}"
    kri_tok = f"tok_ids_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(cae_tok, caelan["id"], name=caelan["name"]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"],
             hp_cur=50, hp_max=75),
    ])
    uplifts = await _try_attack_until_hit(
        gm_client, caelan["id"], kri_tok, attack_index=LONGSWORD_INDEX,
    )
    assert uplifts is not None, "Longsword didn't hit Krieger in 15 tries"
    ids = next(
        (u for u in uplifts if u.get("source") == "improved-divine-smite"),
        None,
    )
    assert ids is not None, (
        f"expected improved-divine-smite uplift on melee weapon hit "
        f"at Paladin Lv 11; got uplifts={uplifts}"
    )
    assert ids.get("damage_type") == "radiant", ids
    total = int(ids.get("total") or 0)
    assert 1 <= total <= 8, f"1d8 total out of range: {ids}"


async def test_improved_divine_smite_skipped_below_lv_11(gm_client, roster):
    """Control: Sir Caelan's stock level is 6, below the Lv 11
    gate. No improved-divine-smite uplift should fire even on a
    melee weapon hit.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    krieger = roster["Krieger Stonefist"]
    cae_tok = f"tok_ids_lv6_cae_{caelan['id']}"
    kri_tok = f"tok_ids_lv6_kri_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(cae_tok, caelan["id"], name=caelan["name"]),
        _mkc(kri_tok, krieger["id"], name=krieger["name"],
             hp_cur=50, hp_max=75),
    ])
    uplifts = await _try_attack_until_hit(
        gm_client, caelan["id"], kri_tok, attack_index=LONGSWORD_INDEX,
    )
    assert uplifts is not None, "Longsword didn't hit Krieger in 15 tries"
    ids = next(
        (u for u in uplifts if u.get("source") == "improved-divine-smite"),
        None,
    )
    assert ids is None, (
        f"Lv 6 Caelan should NOT trigger Improved Divine Smite; "
        f"got {ids!r}"
    )
