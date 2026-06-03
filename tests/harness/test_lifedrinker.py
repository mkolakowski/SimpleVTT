"""v2.99.97 — Lifedrinker (Warlock Lv 12+, Pact of the Blade) invocation.

RAW (PHB p.111): "Prerequisite: 12th level, Pact of the Blade
feature. When you hit a creature with your pact weapon, the
creature takes extra necrotic damage equal to your Charisma
modifier (a minimum of 1)."

v2.99.97 wires this as a separate uplift (necrotic damage type)
in `_compute_attack_auto_uplifts`. Four gates:
  1. attack.pact_weapon is True
  2. eldritch-invocation-lifedrinker on feats list
  3. Warlock level >= 12
  4. CHA score on sheet

Magnus is the Warlock fixture. Stock sheet is Lv 5 — below the
Lv 12 prerequisite — so the harness PATCHes him to Lv 12 in the
fixture and restores Lv 5 in teardown. His Quarterstaff is already
flagged ``pact_weapon: True`` in the demo seed; the invocation is
already on his feats list.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, hp_cur=50, hp_max=75, name="X"):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur, "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _try_attack_until_hit(
    gm_client, attacker_id, target_combatant_id, attack_index=0,
):
    """Loop attacks until one lands. Returns the auto_uplifts list
    from the first hit, or None if no hit across 10 attempts.
    """
    for _ in range(10):
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
async def magnus_at_lv_12(gm_client, roster):
    """PATCH Magnus to Warlock Lv 12 (Lifedrinker prerequisite).
    Restore Lv 5 in teardown.
    """
    magnus = roster["Magnus Hexbinder"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"class_slug": "warlock", "level": 12},
    )
    yield magnus
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"class_slug": "warlock", "level": 5},
    )


async def test_lifedrinker_adds_cha_necrotic_on_pact_weapon_hit(
    gm_client, magnus_at_lv_12, roster,
):
    """Magnus Lv 12 attacks Krieger with the Quarterstaff
    (pact_weapon: True). On hit, auto_uplifts should contain a
    lifedrinker entry: damage_type='necrotic', total=+3 (CHA 17 mod).
    """
    magnus = magnus_at_lv_12
    krieger = roster["Krieger Stonefist"]
    magnus_tok = f"tok_ld_{magnus['id']}"
    krieger_tok = f"tok_ld_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(magnus_tok, magnus["id"], name=magnus["name"]),
        _mkc(krieger_tok, krieger["id"], name=krieger["name"],
             hp_cur=50, hp_max=75),
    ])
    # Quarterstaff is attack index 0.
    uplifts = await _try_attack_until_hit(
        gm_client, magnus["id"], krieger_tok, attack_index=0,
    )
    assert uplifts is not None, "Quarterstaff didn't hit Krieger in 10 tries"
    ld = next((u for u in uplifts if u.get("source") == "lifedrinker"), None)
    assert ld is not None, (
        f"expected lifedrinker uplift on pact-weapon hit; "
        f"got uplifts={uplifts}"
    )
    assert ld.get("damage_type") == "necrotic", ld
    # Magnus's CHA is 17 → mod +3. Min 1 clamp doesn't trip.
    assert ld.get("total") == 3, ld


async def test_lifedrinker_skipped_below_level_12(gm_client, roster):
    """Control: Magnus's stock level is 5, below the Lv 12 gate.
    No lifedrinker uplift should fire even though the invocation
    + pact_weapon flag are present.
    """
    magnus = roster["Magnus Hexbinder"]
    krieger = roster["Krieger Stonefist"]
    magnus_tok = f"tok_ld_lv5_{magnus['id']}"
    krieger_tok = f"tok_ld_lv5_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(magnus_tok, magnus["id"], name=magnus["name"]),
        _mkc(krieger_tok, krieger["id"], name=krieger["name"],
             hp_cur=50, hp_max=75),
    ])
    uplifts = await _try_attack_until_hit(
        gm_client, magnus["id"], krieger_tok, attack_index=0,
    )
    assert uplifts is not None, "Quarterstaff didn't hit Krieger in 10 tries"
    ld = next((u for u in uplifts if u.get("source") == "lifedrinker"), None)
    assert ld is None, (
        f"Lv 5 Magnus should NOT trigger Lifedrinker; got {ld!r}"
    )


async def test_lifedrinker_skipped_on_non_pact_weapon(
    gm_client, magnus_at_lv_12, roster,
):
    """Magnus Lv 12 attacks Krieger with Eldritch Blast (no
    pact_weapon flag). No lifedrinker uplift should fire (gate 1).
    """
    magnus = magnus_at_lv_12
    krieger = roster["Krieger Stonefist"]
    magnus_tok = f"tok_ld_eb_{magnus['id']}"
    krieger_tok = f"tok_ld_eb_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(magnus_tok, magnus["id"], name=magnus["name"]),
        _mkc(krieger_tok, krieger["id"], name=krieger["name"],
             hp_cur=50, hp_max=75),
    ])
    # Eldritch Blast is attack index 1.
    uplifts = await _try_attack_until_hit(
        gm_client, magnus["id"], krieger_tok, attack_index=1,
    )
    assert uplifts is not None, "Eldritch Blast didn't hit Krieger in 10 tries"
    ld = next((u for u in uplifts if u.get("source") == "lifedrinker"), None)
    assert ld is None, (
        f"Eldritch Blast lacks pact_weapon flag — Lifedrinker should "
        f"not fire; got {ld!r}"
    )
