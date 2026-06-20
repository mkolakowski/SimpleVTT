"""/eat_goodberry — consume one Goodberry charge + heal 1 HP.
Phase 2 #23 of ``docs/plans/cast-and-broadcast-tail.md``. Closes
the loop on the v2.465.0 Goodberry charge-counter buff.

v2.466.0 — RAW PHB p.248: "A creature can use its action to eat
one berry. Eating a berry restores 1 hit point...." The berry-
holder doesn't have to be the eater — RAW lets the caster hand
one to any creature.

Body: ``{character_id, target_character_id?}``. character_id
holds the goodberry buff; target_character_id is the eater
(defaults to character_id when omitted — caster eats their own).

Tests:
  - Self-eat: Mira casts Goodberry, then eats one → charges
    10 → 9, +1 HP, buff still present.
  - Cross-character: Mira casts; Krieger (target_character_id)
    eats one of her berries → Mira's charges decrement, Krieger
    gets +1 HP.
  - Exhaust counter: cast Goodberry, eat 10 times → the 10th
    consumption sets buff_removed=True and the buff disappears
    from the holder's buff list.
  - No goodberry buff → 409 no_goodberry_buff.
  - Eat at full HP: charges still decrement (the consumption is
    real even if the HP gain is capped at max).
"""
import asyncio

from .conftest import CAMPAIGN_ID


async def _cast_goodberry(gm_client, caster):
    """Cast goodberry to install the buff with 10 charges."""
    pc_cb = {
        "id": f"tok_gb2_caster_{caster['id']}",
        "char_id": caster["id"],
        "name": caster["name"],
        "initiative": 15,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [pc_cb], "turn_index": 0,
              "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_goodberry",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text


async def _cast_goodberry_with_target(gm_client, caster, target):
    """Cast goodberry on a battle that also includes a target
    combatant (for cross-character feeding)."""
    pc_cb = {
        "id": f"tok_gb3_caster_{caster['id']}",
        "char_id": caster["id"],
        "name": caster["name"],
        "initiative": 15,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    target_cb = {
        "id": f"tok_gb3_target_{target['id']}",
        "char_id": target["id"],
        "name": target["name"],
        "initiative": 10,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [pc_cb, target_cb], "turn_index": 0,
              "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_goodberry",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


async def _get_hp(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    sheet = (r.json() or {}).get("sheet") or {}
    return dict(sheet.get("hp") or {})


async def _set_hp(gm_client, char_id, hp_current):
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"hp": {"current": hp_current}},
    )
    assert r.status_code == 200, r.text


async def _long_rest(gm_client, char_id):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


async def test_eat_self_decrements_and_heals(gm_client, roster):
    """Mira casts Goodberry, drops to 5 HP, then eats one berry →
    charges 10 → 9, HP +1, buff still present."""
    druid = roster["Mira Greenleaf"]
    try:
        await _set_hp(gm_client, druid["id"], 5)
        await asyncio.sleep(0.1)
        await _cast_goodberry(gm_client, druid)

        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/eat_goodberry",
            json={"character_id": druid["id"]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["charges_before"] == 10
        assert body["charges_after"] == 9
        assert body["buff_removed"] is False
        assert body["heal_delta"] == 1
        assert body["hp_after"] == body["hp_before"] + 1

        # Buff still present with the new charge count.
        buffs = await _get_buffs(gm_client, druid["id"])
        gb_buff = next(
            (b for b in buffs if b.get("key") == "goodberry"), None,
        )
        assert gb_buff is not None
        assert (gb_buff.get("effects") or {}).get("goodberry_charges") == 9
    finally:
        await _long_rest(gm_client, druid["id"])


async def test_eat_cross_character_holder_decrements_eater_heals(
    gm_client, roster,
):
    """Mira casts Goodberry; Krieger eats one (target_character_id).
    Mira's charges decrement, Krieger's HP rises."""
    druid = roster["Mira Greenleaf"]
    eater = roster["Krieger Stonefist"]
    try:
        await _set_hp(gm_client, eater["id"], 5)
        await asyncio.sleep(0.1)
        await _cast_goodberry_with_target(gm_client, druid, eater)

        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/eat_goodberry",
            json={
                "character_id": druid["id"],
                "target_character_id": eater["id"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["charges_after"] == 9
        assert body["heal_delta"] == 1
        assert body["eater_character_id"] == eater["id"]
        assert body["buff_holder_character_id"] == druid["id"]

        # Eater's HP rose; holder's HP unchanged.
        eater_hp = await _get_hp(gm_client, eater["id"])
        assert int(eater_hp.get("current") or 0) == 6
    finally:
        await _long_rest(gm_client, eater["id"])
        await _long_rest(gm_client, druid["id"])


async def test_eat_exhausts_counter_removes_buff(gm_client, roster):
    """Cast Goodberry, eat all 10 berries → the 10th consumption
    sets buff_removed=True and the buff disappears."""
    druid = roster["Mira Greenleaf"]
    try:
        await _cast_goodberry(gm_client, druid)

        last_body = None
        for i in range(10):
            r = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/eat_goodberry",
                json={"character_id": druid["id"]},
            )
            assert r.status_code == 200, f"iteration {i}: {r.text}"
            last_body = r.json()

        assert last_body is not None
        assert last_body["charges_before"] == 1
        assert last_body["charges_after"] == 0
        assert last_body["buff_removed"] is True

        buffs = await _get_buffs(gm_client, druid["id"])
        assert not any(
            b.get("key") == "goodberry" for b in buffs
        ), f"goodberry buff should be removed; got {buffs}"
    finally:
        await _long_rest(gm_client, druid["id"])


async def test_eat_no_buff_returns_409(gm_client, roster):
    """No goodberry buff on the holder → 409 no_goodberry_buff."""
    druid = roster["Mira Greenleaf"]
    # Seed a battle so the helper sees Mira, but skip the cast.
    pc_cb = {
        "id": f"tok_gb4_caster_{druid['id']}",
        "char_id": druid["id"],
        "name": druid["name"],
        "initiative": 15,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [pc_cb], "turn_index": 0,
              "round": 1, "active": True},
    )

    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/eat_goodberry",
        json={"character_id": druid["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "no_goodberry_buff"


async def test_eat_at_full_hp_still_decrements_charge(gm_client, roster):
    """Mira at full HP eats a berry — heal_delta is 0 (capped at
    max) but charges still decrement 10 → 9."""
    druid = roster["Mira Greenleaf"]
    try:
        await _long_rest(gm_client, druid["id"])
        hp_before = await _get_hp(gm_client, druid["id"])
        assert int(hp_before.get("current") or 0) == int(hp_before.get("max") or 0)
        await _cast_goodberry(gm_client, druid)

        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/eat_goodberry",
            json={"character_id": druid["id"]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["charges_after"] == 9
        assert body["heal_delta"] == 0
        assert body["hp_before"] == body["hp_after"]
    finally:
        await _long_rest(gm_client, druid["id"])
