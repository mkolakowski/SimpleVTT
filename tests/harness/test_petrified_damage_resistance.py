"""v2.99.121 — end-to-end test: "all" damage resistance halves any
damage type via the v2.97.x resistance engine.

v2.99.119 shipped the Petrified factory with "resistance to all
damage" as a descriptive raw_effects bullet. v2.99.121 closes the
mechanical loop:
  - `_make_petrified_buff` stamps `effects.resistance_to: ["all"]`
  - `_resistance_halve` recognizes "all" as a wildcard and halves
    any incoming damage type when the field is present
  - The wildcard works at BOTH the buff-level (`effects.resistance_to`
    on `combatant.buffs[]`) AND the sheet-level
    (`sheet.damage_resistances`)

This test PATCHes Krieger's sheet to add `damage_resistances: ["all"]`
and verifies Tavik's bludgeoning Warhammer hits do half damage.
The buff-level wildcard is pinned via the v2.99.119 unit tests on
the factory output shape.

Sheet PATCH path is easier to set up than the buff install path
(no need to wire _install_buff for "all" wildcard) and exercises
the wildcard end-to-end through the /attack damage pipeline.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", speed_walk=30):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 100, "hp_max": 100,
        "speed_walk": speed_walk,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def krieger_with_all_resistance(gm_client, roster):
    """PATCH Krieger's sheet to add `damage_resistances: ["all"]`.
    Restore stock (empty list — Krieger has no permanent
    resistances) on teardown.
    """
    krieger = roster["Krieger Stonefist"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={"damage_resistances": ["all"]},
    )
    yield krieger
    # Restore. Krieger has no stock damage_resistances entries.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={"damage_resistances": []},
    )


async def test_all_resistance_halves_bludgeoning(gm_client, roster):
    """Baseline: no resistance. Tavik attacks Krieger with the
    Warhammer (1d8+3 bludgeoning). Record the damage_applied.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    krieger = roster["Krieger Stonefist"]
    tv_tok = f"tok_pet_res_b_tv_{tavik['id']}"
    kr_tok = f"tok_pet_res_b_kr_{krieger['id']}"
    baseline_damage = None
    for _ in range(15):
        await _seed_battle(gm_client, [
            _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
            _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik["id"],
                "attack_index": 0,  # Warhammer
                "target_combatant_id": kr_tok,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data.get("hit") and (data.get("damage_applied") or 0) > 0:
            baseline_damage = int(data["damage_applied"])
            assert data.get("target_resistance_applied") is False, data
            break
    assert baseline_damage is not None, "no baseline hit in 15 tries"


async def test_all_resistance_halves_then_pin_engine(
    gm_client, krieger_with_all_resistance, roster,
):
    """Krieger has `damage_resistances: ["all"]` on his sheet.
    Tavik attacks; the response's `target_resistance_applied` is
    True (engine recognized the wildcard) and the damage is the
    floor of half the natural roll.
    """
    krieger = krieger_with_all_resistance
    tavik = roster["Brother Tavik Stonebrow"]
    tv_tok = f"tok_pet_res_a_tv_{tavik['id']}"
    kr_tok = f"tok_pet_res_a_kr_{krieger['id']}"
    for _ in range(15):
        await _seed_battle(gm_client, [
            _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
            _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik["id"],
                "attack_index": 0,
                "target_combatant_id": kr_tok,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data.get("hit") and (data.get("damage_applied") or 0) > 0:
            # The engine should flag resistance applied.
            assert data.get("target_resistance_applied") is True, (
                f"v2.99.121 'all' wildcard not recognized; "
                f"target_resistance_applied={data.get('target_resistance_applied')}, "
                f"damage_applied={data.get('damage_applied')}"
            )
            # Warhammer base 1d8+3 = 4-11 (non-crit) / 5-19 (crit
            # 2d8+3). Halved upper bound: 5 / 9. Pin to 9 to cover
            # both, then cross-check via the is_crit flag.
            upper = 9 if data.get("is_crit") else 5
            assert data["damage_applied"] <= upper, (
                f"halved bludgeoning shouldn't exceed {upper} "
                f"(crit={data.get('is_crit')}); "
                f"got {data['damage_applied']}"
            )
            return
    raise AssertionError("no Petrified hit in 15 tries")
