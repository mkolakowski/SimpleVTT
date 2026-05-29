"""v2.97.34 — wires the v2.97.29 + v2.97.31 + v2.97.33 marker effects
into /use_attack's d20 attack-roll construction. Four hooks shipped in
one commit:

  - Sacred Weapon (v2.97.29): +CHA mod to attack rolls while buff active.
  - Bless (v2.97.31): +1d4 to attack rolls while buff active.
  - Bane (v2.97.33): -1d4 to attack rolls while buff active.
  - Faerie Fire (v2.97.33): advantage on attacks against the target.

The first three append to the d20 attack expression directly; the
fourth extends the existing v2.49.238 ``_target_grants_advantage_to_attackers``
walker to fire on ``key == "faerie-fired"`` as well. Each test seeds
a battle, installs the buff via its real endpoint (Channel Divinity
for Sacred Weapon, /cast_spell for the spells), then posts an attack
and asserts the breakdown carries the expected sub-expression.
"""
import pytest

from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def _seed_battle_with(gm_client, char_specs: list[dict]) -> None:
    """char_specs: list of {id, name, hp_max} dicts. Drops all into
    a fresh battle as combatants with empty buffs."""
    combatants = []
    for spec in char_specs:
        combatants.append({
            "id": spec["tok_id"],
            "char_id": spec["id"],
            "name": spec["name"],
            "initiative": spec.get("initiative", 10),
            "hp_current": spec.get("hp_max", 40),
            "hp_max": spec.get("hp_max", 40),
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        })
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def test_sacred_weapon_attack_adds_cha_mod(gm_client, roster):
    """Caelan uses Channel Divinity → Sacred Weapon, then attacks with
    his longsword. The d20 attack expression should carry +CHA mod
    (Caelan CHA 16 → +3) on top of the base +6 longsword bonus.

    Assertion: the attack_breakdown contains '+3' (the SW bonus). The
    base attack has '+6' from the longsword; the SW patch appends an
    extra '+3' segment.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    await _long_rest(gm_client, caelan["id"])
    await _seed_battle_with(gm_client, [
        {"id": caelan["id"], "name": caelan["name"], "tok_id": f"tok_sw_atk_{caelan['id']}", "hp_max": 60},
    ])

    # Install Sacred Weapon.
    sw = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": caelan["id"],
            "feature_key": "channel-divinity",
            "option_key": "sacred-weapon",
            "label": "Channel Divinity",
            "override": True,
        },
    )
    assert sw.status_code == 200, sw.text

    # Attack with Caelan's longsword (index 0).
    atk = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": caelan["id"], "attack_index": 0, "override": True},
    )
    assert atk.status_code == 200, atk.text
    data = atk.json()
    breakdown = data["attack_breakdown"]
    total = data["attack_total"]
    assert "1d20" in breakdown
    # Parse the d20 roll from the breakdown ("1d20[N]=N ...").
    import re
    m = re.search(r"1d20\[(\d+)\]=(\d+)", breakdown)
    assert m, f"couldn't parse d20 from breakdown: {breakdown}"
    d20 = int(m.group(2))
    # With Sacred Weapon active: total = d20 + 6 (longsword) + 3 (CHA).
    # Without SW: total = d20 + 6 (longsword). So total - d20 - 6 = 3
    # iff SW is active. We assert the math holds.
    assert total - d20 - 6 == 3, (
        f"expected total - d20 - 6 == 3 (SW CHA bonus); "
        f"got d20={d20}, total={total}, breakdown={breakdown}"
    )


async def test_bless_attack_adds_d4(gm_client, roster):
    """Caelan casts Bless on himself, then attacks. The d20 expression
    should carry +1d4. Assertion: breakdown contains '1d4'.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    await _long_rest(gm_client, caelan["id"])
    await _seed_battle_with(gm_client, [
        {"id": caelan["id"], "name": caelan["name"], "tok_id": f"tok_bless_atk_{caelan['id']}", "hp_max": 60},
    ])

    BLESS_INDEX = 0  # Caelan's spell list: Bless first.
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": BLESS_INDEX,
            "slot_level": 1,
            "class_slug": "paladin",
            "target_character_id": caelan["id"],
            "target_combatant_id": f"tok_bless_atk_{caelan['id']}",
            "target_name": caelan["name"],
            "override": True,
            "override_range": True,
        },
    )
    assert cast.status_code == 200, cast.text

    atk = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": caelan["id"], "attack_index": 0, "override": True},
    )
    assert atk.status_code == 200, atk.text
    breakdown = atk.json()["attack_breakdown"]
    assert "1d20" in breakdown
    # Bless suffix "+1d4" — renders as " 1d4[N]=N" (positive: no
    # minus sign). Bane would render as " -1d4[N]=N". Verify the
    # positive form lands.
    assert " 1d4[" in breakdown, (
        f"expected ' 1d4[' (Bless positive die) in breakdown; got {breakdown}"
    )
    assert "-1d4" not in breakdown, (
        f"unexpected -1d4 (Bane?) in Bless-only breakdown: {breakdown}"
    )


async def test_bane_attack_subtracts_d4(gm_client, roster):
    """Lyra casts Bane on Krieger (Cha save, low Cha → loops to a fail).
    Then Krieger attacks. Assertion: attack_breakdown contains '-1d4'
    (the Bane suffix).
    """
    lyra = roster["Lyra Sunstrider"]
    krieger = roster["Krieger Stonefist"]
    BANE_INDEX = 18  # See test_undo_refunds_resource.py — appended in v2.97.33.

    baned = False
    for _ in range(20):
        await _long_rest(gm_client, lyra["id"])
        await _long_rest(gm_client, krieger["id"])
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": krieger["id"], "key": "baned"},
        )
        await _seed_battle_with(gm_client, [
            {"id": lyra["id"], "name": lyra["name"], "tok_id": f"tok_baneatk_{lyra['id']}", "hp_max": 35, "initiative": 12},
            {"id": krieger["id"], "name": krieger["name"], "tok_id": f"tok_baneatk_{krieger['id']}", "hp_max": 55, "initiative": 8},
        ])
        cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": lyra["id"],
                "spell_index": BANE_INDEX,
                "slot_level": 1,
                "class_slug": "bard",
                "target_combatant_id": f"tok_baneatk_{krieger['id']}",
                "target_character_id": krieger["id"],
                "target_name": krieger["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert cast.status_code == 200, cast.text
        prompt_id = cast.json().get("auto_save_prompt_id")
        if not prompt_id:
            continue
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": krieger["id"]},
        )
        if r.json().get("auto_buff_installed") == "Baned":
            baned = True
            break

    assert baned, "no failed Cha save in 20 tries"

    # Krieger (now baned) attacks. Greataxe is his first attack (index 0).
    atk = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": krieger["id"], "attack_index": 0, "override": True},
    )
    assert atk.status_code == 200, atk.text
    breakdown = atk.json()["attack_breakdown"]
    assert "1d20" in breakdown
    # Bane suffix "-1d4" — renders as " -1d4[N]=N" (minus preserved).
    assert "-1d4[" in breakdown, (
        f"expected -1d4 (Bane) in breakdown; got {breakdown}"
    )


async def test_faerie_fire_attack_against_target_has_advantage(gm_client, roster):
    """Lyra casts Faerie Fire on Krieger (loop to Dex-save fail). Then
    someone else attacks Krieger. Assertion: attack_roll_state_applied
    contains 'advantage' (the v2.97.34 extension of
    _target_grants_advantage_to_attackers to read the faerie-fired key).
    """
    lyra = roster["Lyra Sunstrider"]
    krieger = roster["Krieger Stonefist"]
    # Pip will attack Krieger — Pip's first attack (shortsword, index 0).
    pip = roster["Pip Quickfingers"]
    FAERIE_FIRE_INDEX = 6

    fired = False
    krieger_tok = f"tok_ff_atk_{krieger['id']}"
    # v2.97.37 — Krieger has Danger Sense (advantage on Dex saves vs
    # spells), so save-fail probability per iteration is ~20%, not
    # ~55%. 40 iterations keeps the cumulative miss-rate well under
    # 0.1% so the test isn't flaky.
    for _ in range(40):
        await _long_rest(gm_client, lyra["id"])
        await _long_rest(gm_client, krieger["id"])
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": krieger["id"], "key": "faerie-fired"},
        )
        await _seed_battle_with(gm_client, [
            {"id": lyra["id"], "name": lyra["name"], "tok_id": f"tok_ff_atk_{lyra['id']}", "hp_max": 35, "initiative": 14},
            {"id": pip["id"], "name": pip["name"], "tok_id": f"tok_ff_atk_{pip['id']}", "hp_max": 40, "initiative": 12},
            {"id": krieger["id"], "name": krieger["name"], "tok_id": krieger_tok, "hp_max": 55, "initiative": 8},
        ])
        cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": lyra["id"],
                "spell_index": FAERIE_FIRE_INDEX,
                "slot_level": 1,
                "class_slug": "bard",
                "target_combatant_id": krieger_tok,
                "target_character_id": krieger["id"],
                "target_name": krieger["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert cast.status_code == 200, cast.text
        prompt_id = cast.json().get("auto_save_prompt_id")
        if not prompt_id:
            continue
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": krieger["id"]},
        )
        if r.json().get("auto_buff_installed") == "Faerie Fire":
            fired = True
            break

    assert fired, "no failed Dex save in 40 tries"

    # Pip attacks Krieger (the faerie-fired target).
    atk = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": 0,
            "target_combatant_id": krieger_tok,
            "target_character_id": krieger["id"],
            "target_name": krieger["name"],
            "override": True,
        },
    )
    assert atk.status_code == 200, atk.text
    data = atk.json()
    # Advantage layered in: attack_roll_state_applied should include
    # 'advantage' (specifically the v2.49.238 reckless-style label since
    # the same code path fires for both). The breakdown also carries
    # '2d20kh1' (advantage roll shape).
    state = data.get("attack_roll_state_applied", "")
    breakdown = data.get("attack_breakdown", "")
    assert "advantage" in state or "2d20kh1" in breakdown, (
        f"expected advantage from faerie-fired target; "
        f"state={state}, breakdown={breakdown}"
    )


async def test_bless_save_adds_d4(gm_client, gm_ws, roster):
    """v2.97.35 — closes the v2.97.34 filed save-roll half for Bless.
    Caelan blesses Pip; Lyra casts Hold Person on Pip; the player save
    roll_request broadcast carries '+1d4' in base_expression.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    lyra = roster["Lyra Sunstrider"]
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, caelan["id"])
    await _long_rest(gm_client, lyra["id"])
    await _long_rest(gm_client, pip["id"])

    pip_tok = f"tok_bsave_{pip['id']}"
    await _seed_battle_with(gm_client, [
        {"id": caelan["id"], "name": caelan["name"], "tok_id": f"tok_bsave_{caelan['id']}", "hp_max": 60, "initiative": 14},
        {"id": lyra["id"], "name": lyra["name"], "tok_id": f"tok_bsave_{lyra['id']}", "hp_max": 35, "initiative": 12},
        {"id": pip["id"], "name": pip["name"], "tok_id": pip_tok, "hp_max": 40, "initiative": 8},
    ])

    # Caelan casts Bless on Pip (index 0 — Caelan's first spell).
    bless = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": 0,
            "slot_level": 1,
            "class_slug": "paladin",
            "target_character_id": pip["id"],
            "target_combatant_id": pip_tok,
            "target_name": pip["name"],
            "override": True,
            "override_range": True,
        },
    )
    assert bless.status_code == 200, bless.text

    # Verify Bless installed.
    pip_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    assert any((b or {}).get("key") == "bless" for b in pip_buffs), (
        f"bless not installed on Pip; got {pip_buffs}"
    )

    gm_ws.mark()
    # Lyra casts Hold Person on Pip. Hold Person at Lyra's index 11.
    hp_cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": 11,
            "slot_level": 2,
            "class_slug": "bard",
            "target_character_id": pip["id"],
            "target_combatant_id": pip_tok,
            "target_name": pip["name"],
            "override": True,
            "override_range": True,
        },
    )
    assert hp_cast.status_code == 200, hp_cast.text

    # Capture the roll_request broadcast for Pip's save.
    rr_msg = await gm_ws.wait_for("roll_request", timeout=3.0)
    base_expr = rr_msg["data"]["base_expression"]
    assert "+1d4" in base_expr, (
        f"expected '+1d4' (Bless save bonus) in base_expression; got {base_expr!r}"
    )
    assert "-1d4" not in base_expr


async def test_bane_save_subtracts_d4(gm_client, gm_ws, roster):
    """v2.97.35 — closes the v2.97.34 filed save-roll half for Bane.
    Lyra banes Krieger (loop to fail); Lyra then casts Hold Person on
    Pip while Pip also has bane applied? No — Bane targets Krieger.
    Easier: Lyra banes Pip (loop), then casts Hold Person on Pip;
    Pip's save base_expression carries '-1d4'.
    """
    lyra = roster["Lyra Sunstrider"]
    pip = roster["Pip Quickfingers"]
    BANE_INDEX = 18

    pip_tok = f"tok_basave_{pip['id']}"

    baned = False
    for _ in range(20):
        await _long_rest(gm_client, lyra["id"])
        await _long_rest(gm_client, pip["id"])
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": pip["id"], "key": "baned"},
        )
        await _seed_battle_with(gm_client, [
            {"id": lyra["id"], "name": lyra["name"], "tok_id": f"tok_basave_{lyra['id']}", "hp_max": 35, "initiative": 12},
            {"id": pip["id"], "name": pip["name"], "tok_id": pip_tok, "hp_max": 40, "initiative": 8},
        ])
        cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": lyra["id"],
                "spell_index": BANE_INDEX,
                "slot_level": 1,
                "class_slug": "bard",
                "target_combatant_id": pip_tok,
                "target_character_id": pip["id"],
                "target_name": pip["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert cast.status_code == 200, cast.text
        prompt_id = cast.json().get("auto_save_prompt_id")
        if not prompt_id:
            continue
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": pip["id"]},
        )
        if r.json().get("auto_buff_installed") == "Baned":
            baned = True
            break
    assert baned, "no failed Cha save in 20 tries"

    # Verify the bane buff is on Pip.
    pip_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    assert any((b or {}).get("key") == "baned" for b in pip_buffs)

    gm_ws.mark()
    # Lyra casts Hold Person on baned Pip.
    hp_cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": lyra["id"],
            "spell_index": 11,
            "slot_level": 2,
            "class_slug": "bard",
            "target_character_id": pip["id"],
            "target_combatant_id": pip_tok,
            "target_name": pip["name"],
            "override": True,
            "override_range": True,
        },
    )
    assert hp_cast.status_code == 200, hp_cast.text

    rr_msg = await gm_ws.wait_for("roll_request", timeout=3.0)
    base_expr = rr_msg["data"]["base_expression"]
    assert "-1d4" in base_expr, (
        f"expected '-1d4' (Bane save penalty) in base_expression; got {base_expr!r}"
    )


async def test_place_aoe_pc_save_carries_bless_suffix(
    gm_client, gm_ws, roster,
):
    """v2.97.36 — /place_aoe PC save site now appends the v2.97.35
    Bless/Bane suffix to the d20 save expression. Closes one of the
    two filed save-roll sites the v2.97.35 commit flagged.

    Caelan blesses Pip; Thalindra casts Fireball with pending
    placement; /place_aoe resolves Pip in the AoE; the auto_save_targets
    entry for Pip carries '+1d4' in its breakdown (the Bless die).
    """
    caelan = roster["Sir Caelan Lightbringer"]
    thal = roster["Thalindra Moonwhisper"]
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, caelan["id"])
    await _long_rest(gm_client, thal["id"])
    await _long_rest(gm_client, pip["id"])

    # Place Thalindra's token (needed for /place_aoe range check).
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
    by_char = {t.get("character_id"): t for t in r.json()["tokens"]
               if t.get("character_id")}
    thal_tok_existing = by_char.get(thal["id"])
    if not thal_tok_existing:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/place-token",
            json={"x": 100, "y": 100},
        )
        r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")
        by_char = {t.get("character_id"): t for t in r.json()["tokens"]
                   if t.get("character_id")}
        thal_tok_existing = by_char[thal["id"]]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/token/{thal_tok_existing['id']}/move",
        json={"x": 100, "y": 100},
    )

    pip_tok = f"tok_aoe_bless_{pip['id']}"
    await _seed_battle_with(gm_client, [
        {"id": caelan["id"], "name": caelan["name"], "tok_id": f"tok_aoe_bless_{caelan['id']}", "hp_max": 60, "initiative": 14},
        {"id": thal["id"], "name": thal["name"], "tok_id": f"tok_aoe_bless_{thal['id']}", "hp_max": 24, "initiative": 12},
        {"id": pip["id"], "name": pip["name"], "tok_id": pip_tok, "hp_max": 40, "initiative": 8},
    ])

    # Caelan casts Bless on Pip.
    bless = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": 0,
            "slot_level": 1,
            "class_slug": "paladin",
            "target_character_id": pip["id"],
            "target_combatant_id": pip_tok,
            "target_name": pip["name"],
            "override": True,
            "override_range": True,
        },
    )
    assert bless.status_code == 200, bless.text
    # Confirm Bless installed.
    pip_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    assert any((b or {}).get("key") == "bless" for b in pip_buffs)

    # Thalindra casts Fireball (no targets — pending placement).
    # FIREBALL_INDEX on Thalindra is 7 per test_place_aoe_range.py.
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": 7,
            "slot_level": 3,
            "class_slug": "wizard",
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text
    cast_data = cast.json()
    assert cast_data.get("pending_aoe_placement") is True
    cast_id = cast_data["id"]

    # /place_aoe with Pip as the single target in the AoE.
    # Place the center near Pip — pick a coordinate within Fireball's 150 ft.
    placed = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/place_aoe",
        json={
            "cast_id": cast_id,
            "target_combatant_ids": [pip_tok],
            "center": {"x": 200, "y": 200},
        },
    )
    assert placed.status_code == 200, placed.text
    targets = placed.json().get("auto_save_targets") or []
    pip_save = next(
        (t for t in targets
         if t.get("combatant_id") == pip_tok or t.get("target_name") == pip["name"]),
        None,
    )
    assert pip_save is not None, (
        f"expected an auto_save_targets entry for Pip; got {targets}"
    )
    # The bless suffix renders as " 1d4[N]=N" in the breakdown.
    assert " 1d4[" in pip_save["breakdown"], (
        f"expected '+1d4' (Bless save bonus) in Pip's place_aoe save "
        f"breakdown; got {pip_save['breakdown']!r}"
    )
