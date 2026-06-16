"""v2.360.0 — magic-items: Sword of Wounding (RAW DMG p.207, rare,
attunement, any sword). Bucket-C on-hit-install attack rider off the
v2.344.5 stub triage. The first item on the NEW `on_hit_install`
substrate: each hit appends a "wounded" stack to the target; at the
start of each of the wounded creature's turns it takes 1d4 necrotic
per stack, then makes a DC 15 CON save — pass ends all wounds.

Demo fixture: Sir Caelan Lightbringer carries a Sword of Wounding
Longsword at `attack_index 4` + inventory tail, seeded INERT
(equipped=False, attuned=False) — the seed-inert + PATCH-equipped+attuned
pattern (Holy Avenger precedent) keeps the demo's attunement count
unchanged. Tests PATCH equipped+attuned via /sheet-fields, run the
rider assertion, then restore.

Tests:
  - Hit installs a `wounded` buff with `wound_stacks: 1` carrying the
    start-of-turn tick + save markers.
  - A second hit on the same target increments `wound_stacks` to 2
    (no second buff appended).
  - A PUT /battle that advances initiative to the wounded combatant's
    turn fires the start-of-turn hook: the wounded buff persists on a
    failed save AND the target's hp dropped.
  - Across seeds, the DC 15 CON save eventually passes and the
    wounded buff drops.
  - No-attunement gate: equipped=True but attuned=False → no wound
    install.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


CAELAN_SWORD_OF_WOUNDING_ATTACK_IDX = 4
_SLUG = "sword-of-wounding"
_BUFF_KEY = "wounded"
_BUFF_SOURCE = f"item-{_SLUG}"


def _mkc(cid, char_id=None, name="X", token_template_id=None,
         creature_type="humanoid", ac=1, hp_max=60):
    c = {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_max, "hp_max": hp_max,
        "ac": ac,
        "buffs": [],
        "creature_type": creature_type,
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    if token_template_id is not None:
        c["token_template_id"] = token_template_id
    return c


async def _seed_battle(gm_client, combatants, *, turn_index=0):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": turn_index,
              "round": 1, "active": True},
    )


async def _put_battle(gm_client, state):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle", json=state,
    )


async def _get_battle(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    return ((r.json() or {}).get("battle") or {})


async def _seed_dice(gm_client, seed):
    r = await gm_client.post("/api/test/dice/seed", json={"seed": seed})
    assert r.status_code == 200, r.text


async def _snapshot_inv(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    inv = list(((resp.json() or {}).get("sheet") or {}).get("inventory") or [])
    return [dict(it) if isinstance(it, dict) else it for it in inv]


async def _patch_inv(gm_client, char_id, *, equipped, attuned):
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _SLUG:
            it["equipped"] = equipped
            it["attuned"] = attuned
            found = True
    assert found, "Sir Caelan has no sword-of-wounding inventory item"
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    assert resp.status_code == 200, resp.text
    return snapshot


async def _restore_inv(gm_client, char_id, snapshot):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": snapshot},
    )


async def _bandit_template_id(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert r.status_code == 200, r.text
    bandit = next((t for t in r.json() if t.get("name") == "Bandit"), None)
    assert bandit is not None, "Bandit template missing from the demo seed"
    return bandit["id"]


def _wounded_buff(combatant):
    for b in combatant.get("buffs") or []:
        if isinstance(b, dict) and b.get("key") == _BUFF_KEY \
                and b.get("source") == _BUFF_SOURCE:
            return b
    return None


@pytest_asyncio.fixture
async def caelan(roster):
    return roster["Sir Caelan Lightbringer"]


async def test_attack_installs_wound_stack(gm_client, caelan):
    """A successful hit with the Sword of Wounding (equipped + attuned)
    installs the `wounded` condition buff on the target with
    `wound_stacks: 1` and the start-of-turn tick + save markers."""
    snap = await _patch_inv(
        gm_client, caelan["id"], equipped=True, attuned=True,
    )
    try:
        template_id = await _bandit_template_id(gm_client)
        caelan_cid = f"tok_sow_hit_caelan_{caelan['id']}"
        target_cid = "tok_sow_hit_target"
        await _seed_battle(gm_client, [
            _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
            _mkc(target_cid, None, name="Bandit",
                 token_template_id=template_id),
        ])
        await _seed_dice(gm_client, 7)
        try:
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/attack",
                json={
                    "character_id": caelan["id"],
                    "attack_index": CAELAN_SWORD_OF_WOUNDING_ATTACK_IDX,
                    "target_combatant_id": target_cid,
                    "override": True,
                },
            )
            assert resp.status_code == 200, resp.text
            assert resp.json().get("attack_name") == "Sword of Wounding Longsword"
        finally:
            await _seed_dice(gm_client, None)

        battle = await _get_battle(gm_client)
        tgt = next(
            (c for c in battle.get("combatants") or []
             if c.get("id") == target_cid), None)
        assert tgt is not None, battle
        buff = _wounded_buff(tgt)
        assert buff is not None, f"wounded buff missing; buffs={tgt.get('buffs')!r}"
        eff = buff.get("effects") or {}
        assert int(eff.get("wound_stacks") or 0) == 1
        assert eff.get("start_of_turn_tick_dice_per_stack") == "1d4"
        assert eff.get("start_of_turn_tick_damage_type") == "necrotic"
        assert eff.get("start_of_turn_save_ability") == "CON"
        assert int(eff.get("start_of_turn_save_dc") or 0) == 15
    finally:
        await _restore_inv(gm_client, caelan["id"], snap)


async def test_second_hit_stacks_wounds(gm_client, caelan):
    """Two consecutive hits on the same target raise `wound_stacks` from
    1 → 2 (one buff entry, incremented in place)."""
    snap = await _patch_inv(
        gm_client, caelan["id"], equipped=True, attuned=True,
    )
    try:
        template_id = await _bandit_template_id(gm_client)
        caelan_cid = f"tok_sow_stack_caelan_{caelan['id']}"
        target_cid = "tok_sow_stack_target"
        await _seed_battle(gm_client, [
            _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
            _mkc(target_cid, None, name="Bandit",
                 token_template_id=template_id),
        ])
        await _seed_dice(gm_client, 11)
        try:
            for _ in range(2):
                resp = await gm_client.post(
                    f"/api/campaign/{CAMPAIGN_ID}/attack",
                    json={
                        "character_id": caelan["id"],
                        "attack_index": CAELAN_SWORD_OF_WOUNDING_ATTACK_IDX,
                        "target_combatant_id": target_cid,
                        "override": True,
                    },
                )
                assert resp.status_code == 200, resp.text
        finally:
            await _seed_dice(gm_client, None)

        battle = await _get_battle(gm_client)
        tgt = next(
            (c for c in battle.get("combatants") or []
             if c.get("id") == target_cid), None)
        assert tgt is not None
        wounded_entries = [
            b for b in (tgt.get("buffs") or [])
            if isinstance(b, dict) and b.get("key") == _BUFF_KEY
            and b.get("source") == _BUFF_SOURCE
        ]
        assert len(wounded_entries) == 1, (
            f"expected exactly one wounded buff entry; got {wounded_entries!r}"
        )
        assert int((wounded_entries[0].get("effects") or {})
                   .get("wound_stacks") or 0) == 2
    finally:
        await _restore_inv(gm_client, caelan["id"], snap)


async def test_no_attunement_no_install(gm_client, caelan):
    """If the Sword of Wounding is equipped but NOT attuned, the rider
    is gated off — no wounded buff appears on the target."""
    snap = await _patch_inv(
        gm_client, caelan["id"], equipped=True, attuned=False,
    )
    try:
        template_id = await _bandit_template_id(gm_client)
        caelan_cid = f"tok_sow_noatt_caelan_{caelan['id']}"
        target_cid = "tok_sow_noatt_target"
        await _seed_battle(gm_client, [
            _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
            _mkc(target_cid, None, name="Bandit",
                 token_template_id=template_id),
        ])
        await _seed_dice(gm_client, 7)
        try:
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/attack",
                json={
                    "character_id": caelan["id"],
                    "attack_index": CAELAN_SWORD_OF_WOUNDING_ATTACK_IDX,
                    "target_combatant_id": target_cid,
                    "override": True,
                },
            )
            assert resp.status_code == 200, resp.text
        finally:
            await _seed_dice(gm_client, None)

        battle = await _get_battle(gm_client)
        tgt = next(
            (c for c in battle.get("combatants") or []
             if c.get("id") == target_cid), None)
        assert tgt is not None
        assert _wounded_buff(tgt) is None, (
            f"wounded buff installed without attunement: {tgt.get('buffs')!r}"
        )
    finally:
        await _restore_inv(gm_client, caelan["id"], snap)


async def test_turn_start_ticks_damage(gm_client, caelan):
    """When initiative advances to the wounded creature's turn, the
    start-of-turn hook ticks N × 1d4 necrotic damage. Assertion: target's
    HP dropped by 1..4 (one stack × 1d4)."""
    snap = await _patch_inv(
        gm_client, caelan["id"], equipped=True, attuned=True,
    )
    # v2.366.1 — ensure auto-apply-damage is ON so the install-time
    # attack damage actually lands on the bandit (prior tests may
    # have toggled it off in their teardown). The hp_before
    # assertion below relies on the post-attack HP being < the seed
    # `target_hp`.
    await gm_client.post(
        f"/api/test/campaign/{CAMPAIGN_ID}/flags",
        json={"auto_apply_damage": True},
    )
    try:
        template_id = await _bandit_template_id(gm_client)
        caelan_cid = f"tok_sow_tick_caelan_{caelan['id']}"
        target_cid = "tok_sow_tick_target"
        target_hp = 60
        await _seed_battle(gm_client, [
            _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
            _mkc(target_cid, None, name="Bandit",
                 token_template_id=template_id, hp_max=target_hp),
        ])
        # Hit to install the wound stack.
        await _seed_dice(gm_client, 11)
        try:
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/attack",
                json={
                    "character_id": caelan["id"],
                    "attack_index": CAELAN_SWORD_OF_WOUNDING_ATTACK_IDX,
                    "target_combatant_id": target_cid,
                    "override": True,
                },
            )
            assert resp.status_code == 200, resp.text
        finally:
            await _seed_dice(gm_client, None)

        # Capture the post-attack battle state. The bandit's HP already
        # dropped by the attack's slashing damage (1d8+3); we want to
        # assert the ADDITIONAL drop from the start-of-turn tick (1d4
        # per stack), so we baseline off this hp_before.
        battle = await _get_battle(gm_client)
        target = next(
            (c for c in battle.get("combatants") or []
             if c.get("id") == target_cid), None)
        assert target is not None
        assert _wounded_buff(target) is not None, (
            "wound install missed before tick assertion"
        )
        hp_before = int(target.get("hp_current") or 0)
        assert hp_before < target_hp, (
            f"the install-time attack itself should have dealt damage; "
            f"got hp_before={hp_before} (target_hp={target_hp})"
        )

        # Bump turn_index to the wounded bandit's turn. The PUT-/battle
        # turn-advance hook fires the start-of-turn damage + save. Use
        # a seed that's likely to FAIL the DC 15 CON save so the buff
        # (and the tick assertion baseline) stays intact for the next
        # GET. Bandit CON +0 → needs nat 15+ to pass.
        await _seed_dice(gm_client, 0)
        try:
            battle["turn_index"] = 1  # bandit's turn
            await _put_battle(gm_client, battle)
        finally:
            await _seed_dice(gm_client, None)

        post = await _get_battle(gm_client)
        target_post = next(
            (c for c in post.get("combatants") or []
             if c.get("id") == target_cid), None)
        assert target_post is not None
        hp_after = int(target_post.get("hp_current") or 0)
        delta = hp_before - hp_after
        assert 1 <= delta <= 4, (
            f"start-of-turn tick should drop HP by 1..4 (one stack × 1d4); "
            f"got {hp_before} → {hp_after} (delta {delta})."
        )
    finally:
        await _restore_inv(gm_client, caelan["id"], snap)


async def test_passing_save_clears_wounds(gm_client, caelan):
    """Across seeds, the DC 15 CON save eventually passes and the
    wounded buff is dropped from the target. Bandit CON +0 — a d20
    of 15+ passes."""
    snap = await _patch_inv(
        gm_client, caelan["id"], equipped=True, attuned=True,
    )
    try:
        template_id = await _bandit_template_id(gm_client)
        cleared = False
        for seed in range(0, 200):
            caelan_cid = f"tok_sow_save_caelan_{caelan['id']}_{seed}"
            target_cid = f"tok_sow_save_target_{seed}"
            await _seed_battle(gm_client, [
                _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
                _mkc(target_cid, None, name="Bandit",
                     token_template_id=template_id, hp_max=80),
            ])
            await _seed_dice(gm_client, 11)
            try:
                resp = await gm_client.post(
                    f"/api/campaign/{CAMPAIGN_ID}/attack",
                    json={
                        "character_id": caelan["id"],
                        "attack_index": CAELAN_SWORD_OF_WOUNDING_ATTACK_IDX,
                        "target_combatant_id": target_cid,
                        "override": True,
                    },
                )
                assert resp.status_code == 200, resp.text
            finally:
                await _seed_dice(gm_client, None)

            battle = await _get_battle(gm_client)
            target = next(
                (c for c in battle.get("combatants") or []
                 if c.get("id") == target_cid), None)
            if target is None or _wounded_buff(target) is None:
                # Attack missed — try next seed.
                continue

            await _seed_dice(gm_client, seed)
            try:
                battle["turn_index"] = 1
                await _put_battle(gm_client, battle)
            finally:
                await _seed_dice(gm_client, None)

            post = await _get_battle(gm_client)
            target_post = next(
                (c for c in post.get("combatants") or []
                 if c.get("id") == target_cid), None)
            if target_post is not None and _wounded_buff(target_post) is None:
                cleared = True
                break

        assert cleared, (
            "Across seeds 0..199 the Bandit never passed the DC 15 CON save "
            "to clear the wounded buff — the start-of-turn save-and-drop "
            "path may be broken."
        )
    finally:
        await _restore_inv(gm_client, caelan["id"], snap)
