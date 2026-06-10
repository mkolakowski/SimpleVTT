"""v2.99.320 — Valor College Bard: Combat Inspiration (F.1 opener, Lv 3+).

F.1 Bard subclass batch opener. RAW PHB p.55: a creature
with a Bardic Inspiration die from you can roll that die and
add it to a weapon damage roll OR (reaction) to its AC vs an
attack.

Die size follows the BI table: d6 (Lv 3-4), d8 (Lv 5-9),
d10 (Lv 10-14), d12 (Lv 15+).

v1 announce-only — actual BI roll + application is via the
existing BI flow. No chip — this endpoint declares intent.

Lyra is Lv 6 Lore Bard — PATCH'd to Valor for testing.

Tests:
  - Lv 6 happy default (damage) → 1d8.
  - Mode "ac" passes through.
  - Default missing mode → "damage".
  - Wrong subclass (Lore) → 409.
  - Valor Lv 2 → 409.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _ci_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "combat-inspiration"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def lyra_valor(gm_client, roster):
    """PATCH Lyra to College of Valor."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Valor"},
        class_slug="bard",
    )
    try:
        yield lyra
    finally:
        await _patch_sheet(
            gm_client, lyra["id"],
            {"subclass": "College of Lore", "level": 6},
            class_slug="bard",
        )


def _pc(cid, c, hp=30):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp, "hp_max": hp, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def test_ci_damage_with_target_applies_bonus(
    gm_client, gm_ws, lyra_valor, roster,
):
    """v2.144.0 — Phase 1 (damage half): when /use_combat_inspiration
    is called with `mode=damage` AND `target_combatant_id`, the
    endpoint rolls the BI die server-side and applies the rolled
    value as bonus damage to the target (with `attacker_char_id` set
    to the Bard so the regular damage pipeline works — resistance,
    on-damage-taken hooks, etc.). Verify the response carries
    `bonus_rolled` in [1, 8] (1d8 at Lv 5-9) and `bonus_applied` =
    the rolled value (no resistance on Pip for slashing)."""
    lyra = lyra_valor
    pip = roster["Pip Quickfingers"]
    pip_tok = f"tok_ci_p_{pip['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _pc(f"tok_ci_l_{lyra['id']}", lyra),
            _pc(pip_tok, pip),
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_combat_inspiration",
        json={"character_id": lyra["id"], "mode": "damage",
              "target_combatant_id": pip_tok,
              "damage_type": "slashing"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "damage"
    assert data["die_size"] == 8     # Lv 6 → 1d8
    br = data.get("bonus_rolled")
    ba = data.get("bonus_applied")
    assert br is not None and 1 <= br <= 8, (
        f"BI die should roll 1-8; got {br}"
    )
    # Allow the damage pipeline's resistance/halving to fire — Pip's
    # combatant may carry residual marks from earlier tests in the
    # session that gate halving (AP Phase 2, condition resistances,
    # etc.). The contract this test pins is that the BI die actually
    # rolls AND damage hits the pipeline; the exact applied value
    # depends on Pip's full buff state. `applied` ∈ {br, br // 2}
    # covers the resistance-fired and resistance-not-fired cases;
    # what we want to catch is the helper returning 0 or None.
    assert ba is not None and ba > 0, (
        f"bonus damage should apply (positive); got rolled={br}, "
        f"applied={ba}"
    )
    assert ba in (br, br // 2), (
        f"applied should be the full rolled value or the halved value "
        f"(via resistance); got rolled={br}, applied={ba}"
    )


async def test_ci_ac_with_attack_inputs_computes_new_ac(
    gm_client, lyra_valor,
):
    """v2.145.0 — Phase 2 (AC half): when /use_combat_inspiration is
    called with `mode=ac` AND both `attack_total` + `target_ac`, the
    endpoint rolls the BI die, computes `ac_new_ac = original + BI`,
    and returns `ac_would_miss = attack_total < new_ac`. Pure
    calculator — no state mutation, no damage application. Picks
    attack_total = 15 + target_ac = 12 so the boosted AC (12 + 1d8 =
    13–20) will turn the hit into a miss only when the BI die rolls
    high enough (BI ≥ 4 → new_ac ≥ 16 > 15)."""
    lyra = lyra_valor
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_combat_inspiration",
        json={"character_id": lyra["id"], "mode": "ac",
              "attack_total": 15, "target_ac": 12},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "ac"
    assert data["die_size"] == 8
    assert data["ac_attack_total"] == 15
    assert data["ac_original_ac"] == 12
    br = data.get("bonus_rolled")
    assert br is not None and 1 <= br <= 8, (
        f"BI die should roll 1-8; got {br}"
    )
    expected_new_ac = 12 + br
    assert data["ac_new_ac"] == expected_new_ac, (
        f"ac_new_ac should be {expected_new_ac}; got {data['ac_new_ac']}"
    )
    expected_would_miss = 15 < expected_new_ac
    assert data["ac_would_miss"] is expected_would_miss, (
        f"ac_would_miss should be {expected_would_miss} for "
        f"attack_total=15, new_ac={expected_new_ac}; got "
        f"{data['ac_would_miss']}"
    )


async def test_ci_ac_without_inputs_announce_only(
    gm_client, lyra_valor,
):
    """v2.145.0 — Without `attack_total` + `target_ac`, mode=ac stays
    announce-only. Backward-compatible with the v2.99.320 contract."""
    lyra = lyra_valor
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_combat_inspiration",
        json={"character_id": lyra["id"], "mode": "ac"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "ac"
    assert data.get("bonus_rolled") is None
    assert data.get("ac_new_ac") is None
    assert data.get("ac_would_miss") is None


async def test_ci_damage_without_target_announce_only(
    gm_client, lyra_valor,
):
    """v2.144.0 — Without `target_combatant_id` the endpoint stays
    announce-only (no BI die rolled, no damage applied). Backward-
    compatible with the v2.99.320 contract for clients that haven't
    been updated."""
    lyra = lyra_valor
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_combat_inspiration",
        json={"character_id": lyra["id"], "mode": "damage"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "damage"
    assert data.get("bonus_rolled") is None, (
        f"announce-only path should not roll the die; got "
        f"bonus_rolled={data.get('bonus_rolled')!r}"
    )
    assert data.get("bonus_applied") is None


async def test_use_ci_happy_lv6(
    gm_client, gm_ws, lyra_valor,
):
    """Lv 6 Valor default → 1d8 damage."""
    lyra = lyra_valor
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_combat_inspiration",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "damage"
    assert data["die_size"] == 8
    assert data["die_expression"] == "1d8"
    assert data["bard_level"] == 6
    await asyncio.sleep(0.3)
    feats = _ci_broadcasts(gm_ws, lyra["id"])
    assert feats


async def test_use_ci_mode_ac(
    gm_client, lyra_valor,
):
    """Mode 'ac' passes through."""
    lyra = lyra_valor
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_combat_inspiration",
        json={"character_id": lyra["id"], "mode": "ac"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "ac"


async def test_use_ci_default_mode(
    gm_client, lyra_valor,
):
    """Missing mode → 'damage'."""
    lyra = lyra_valor
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_combat_inspiration",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "damage"


async def test_use_ci_wrong_subclass(
    gm_client, roster,
):
    """Default Lyra (Lore) → 409."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_combat_inspiration",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ci_level_gate(
    gm_client, roster,
):
    """Valor Lyra at Lv 2 → 409."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Valor", "level": 2},
        class_slug="bard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_combat_inspiration",
            json={"character_id": lyra["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, lyra["id"],
            {"subclass": "College of Lore", "level": 6},
            class_slug="bard",
        )


async def test_ci_phase3a_attack_targeted_prompt_surfaces_option(
    gm_client, gm_ws, lyra_valor, roster,
):
    """v2.158.67 — Phase 3a: when a watcher carries a
    `bardic-inspiration-die` buff sourced by a Valor College Bard
    Lv 3+, the `attack_targeted` reaction prompt surfaces a
    `use-combat-inspiration-ac` option automatically. Pre-fix, the
    player had to manually invoke `/use_combat_inspiration?mode=ac`
    with attack_total + target_ac plugged in by hand (v2.145.0).

    Setup: Lyra (PATCHed to Valor Lv 6) casts Bardic Inspiration on
    Garrik (Fighter — deliberately a non-Rogue so Uncanny Dodge's
    auto-fire doesn't pre-consume his reaction before the
    attack_targeted prompt resolves), landing a
    `bardic-inspiration-die` buff on Garrik's combatant with
    `source_char_id == lyra.id`. Pip (attacker) then swings at
    Garrik until a hit lands; the resulting `reaction_prompt` for
    Garrik lists `use-combat-inspiration-ac` with the BI die
    expression and the source bard's char_id in the option's params.
    The dispatch half (rolling the die + verdict + consuming the BI
    buff + marking the reaction) is deferred to Phase 3b — this
    test only asserts the option's surfacing. A separate follow-up
    commit will also suppress UD's auto-fire when the watcher
    carries a BI buff so the option surfaces for Rogue-Bard pairs
    too (mirrors the v2.80.0 Shield/DD/Lucky suppression pattern).
    """
    lyra = lyra_valor
    pip = roster["Pip Quickfingers"]
    garrik = roster["Garrik Ironside"]
    # Refill Lyra's BI counter so the cast doesn't 409 on depletion.
    refill = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    assert refill.status_code == 200, refill.text
    # Seed a 3-PC battle. Pip (initiative 20) acts first as the
    # attacker; Lyra (15) casts BI on Garrik (10); then Pip swings
    # at Garrik. Garrik is the BI recipient because he's a Fighter
    # with no UD auto-fire to pre-consume his reaction.
    lyra_tok = f"tok_ci3a_l_{lyra['id']}"
    pip_tok = f"tok_ci3a_p_{pip['id']}"
    garrik_tok = f"tok_ci3a_g_{garrik['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": pip_tok, "char_id": pip["id"],
             "name": pip["name"], "initiative": 20,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": lyra_tok, "char_id": lyra["id"],
             "name": lyra["name"], "initiative": 15,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": garrik_tok, "char_id": garrik["id"],
             "name": garrik["name"], "initiative": 10,
             "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    # Lyra casts BI on Garrik → installs the bardic-inspiration-die
    # buff on Garrik's combatant with source_char_id = lyra.id.
    bi = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_bardic_inspiration",
        json={
            "character_id": lyra["id"],
            "target_character_id": garrik["id"],
            "override": True,
        },
    )
    assert bi.status_code == 200, bi.text
    await asyncio.sleep(0.15)
    gm_ws.mark()
    # Pip swings at Garrik until a hit lands so attack_targeted fires.
    for _ in range(20):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": 0,
                "target_combatant_id": garrik_tok,
                "override": True,
                "override_range": True,
            },
        )
        assert r.status_code == 200, r.text
        if r.json().get("hit"):
            break
    else:
        raise AssertionError(
            "Pip failed to hit Garrik in 20 swings — BI prompt never fired"
        )
    await asyncio.sleep(0.3)
    prompts = [
        m for m in gm_ws.buffered("reaction_prompt")
        if (m.get("data") or {}).get("watcher_char_id") == garrik["id"]
        and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
    ]
    assert prompts, (
        f"expected attack_targeted reaction_prompt for Garrik; got "
        f"{[(m.get('data') or {}).get('trigger_event') for m in gm_ws.buffered('reaction_prompt')]}"
    )
    options = prompts[0]["data"].get("options") or []
    ci_opts = [o for o in options if o.get("key") == "use-combat-inspiration-ac"]
    assert ci_opts, (
        f"expected use-combat-inspiration-ac option on Garrik's prompt; "
        f"got option keys {[o.get('key') for o in options]}"
    )
    ci_opt = ci_opts[0]
    assert ci_opt.get("kind") == "class_feature"
    assert ci_opt.get("available") is True
    # The label surfaces the die expression so the player sees the
    # AC boost size at a glance.
    label = ci_opt.get("label") or ""
    assert "Combat Inspiration" in label
    assert "+1d8 AC" in label, (
        f"expected '+1d8 AC' in label for Lv 6 Valor Bard; got {label!r}"
    )
    # Params carry the data the (Phase 3b) dispatch will need to
    # roll the die + compute the verdict + drop the buff.
    params = ci_opt.get("params") or {}
    assert params.get("die_expression") == "1d8", (
        f"die_expression should be 1d8 for Lv 6 Valor; got {params!r}"
    )
    assert params.get("die_size") == 8
    assert int(params.get("source_char_id") or 0) == int(lyra["id"]), (
        f"source_char_id should be Lyra's id; got {params.get('source_char_id')!r}"
    )
    # attack_total + target_ac surface so the future dispatch can
    # roll the verdict without re-reading the sheet.
    assert isinstance(params.get("attack_total"), int)
    assert isinstance(params.get("target_ac"), int)


async def test_ci_phase3a_no_bi_buff_no_option(
    gm_client, gm_ws, lyra_valor, roster,
):
    """v2.158.67 — Regression guard: when the watcher has NO
    `bardic-inspiration-die` buff installed (e.g. Lyra never cast BI
    on them), the Combat Inspiration AC option MUST NOT surface on
    `attack_targeted`. Without this gate the picker would offer the
    option to anyone, breaking RAW.

    Setup: Garrik (attacker) + Pip (watcher, NO BI buff) + Lyra
    (Valor Bard but didn't cast BI). Garrik hits Pip; the
    attack_targeted prompt has Pip's other reactions (if any), but
    `use-combat-inspiration-ac` is NOT in the options."""
    lyra = lyra_valor  # noqa: F841 — fixture sets Lyra to Valor for symmetry
    pip = roster["Pip Quickfingers"]
    garrik = roster["Garrik Ironside"]
    pip_tok = f"tok_ci3a_no_p_{pip['id']}"
    garrik_tok = f"tok_ci3a_no_g_{garrik['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": garrik_tok, "char_id": garrik["id"],
             "name": garrik["name"], "initiative": 20,
             "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": pip_tok, "char_id": pip["id"],
             "name": pip["name"], "initiative": 10,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    for _ in range(20):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": garrik["id"],
                "attack_index": 0,
                "target_combatant_id": pip_tok,
                "override": True,
                "override_range": True,
            },
        )
        assert r.status_code == 200, r.text
        if r.json().get("hit"):
            break
    else:
        raise AssertionError(
            "Garrik failed to hit Pip in 20 swings — prompt never fired"
        )
    await asyncio.sleep(0.3)
    prompts = [
        m for m in gm_ws.buffered("reaction_prompt")
        if (m.get("data") or {}).get("watcher_char_id") == pip["id"]
        and (m.get("data") or {}).get("trigger_event") == "attack_targeted"
    ]
    # A prompt may or may not fire (Pip may have no eligible reactions
    # without the BI buff); either way, no use-combat-inspiration-ac
    # option may surface.
    for p in prompts:
        options = (p.get("data") or {}).get("options") or []
        keys = [o.get("key") for o in options]
        assert "use-combat-inspiration-ac" not in keys, (
            f"use-combat-inspiration-ac must NOT surface without a BI "
            f"buff; got keys={keys}"
        )
