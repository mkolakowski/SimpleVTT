"""v2.99.305 → v2.158.5 — Order Domain Cleric: Order's Wrath (Lv 17).

v2.99.305 shipped announce-only. v2.158.5 (Phase 8 fifth commit
of the [full-feature-automation](../../docs/plans/full-feature-automation.md)
plan; closes the Lv-17 cleric capstone batch except Improved
Reaper) wires the endpoint to install an `orders-wrath-curse`
buff on the target combatant (when `target_combatant_id` is
supplied) carrying:
  * `effects.orders_wrath_psychic_damage_expression: "2d8"`
  * `effects.orders_wrath_caster_char_id: <cleric.id>`
  * `effects.orders_wrath_active: True`
Duration 2 rounds (covers "until the start of your next turn").
Phase 2 (deferred): `/attack` hit by an ally against a buffed
target deals 2d8 psychic + drops the curse.

RAW TCE p.40: when you deal Divine Strike damage to a creature,
curse it until the start of your next turn. Next ally hit
triggers 2d8 psychic and ends curse. Once per turn.

When no `target_combatant_id` supplied, the endpoint falls back
to the historical announce-only behavior (no buff install).

Tests:
  - Lv 17 happy (no target) → 2d8 psychic expression,
    next-turn expiry, `curse_installed == False` (no target).
  - Lv 17 with bogus `target_combatant_id` "tok_test" →
    response passes the id through, `curse_installed == False`
    (no matching combatant in battle).
  - Lv 17 with real target combatant id → `curse_installed ==
    True` + buff appears on the target combatant.
  - Wrong subclass → 409.
  - Level gate (Lv 16) → 409.
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


def _ow_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "orders-wrath"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def tavik_order_lv17(gm_client, roster):
    """PATCH Tavik to Order Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Order Domain", "level": 17},
        class_slug="cleric",
    )
    try:
        yield tavik
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_use_ow_happy_lv17(
    gm_client, gm_ws, tavik_order_lv17,
):
    """Lv 17 Order → 2d8 psychic, next-turn expiry."""
    tavik = tavik_order_lv17
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_orders_wrath",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["psychic_damage_expression"] == "2d8"
    assert data["expires_on"] == "next_turn_start"
    assert data["cleric_level"] == 17
    await asyncio.sleep(0.3)
    feats = _ow_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_ow_with_target(
    gm_client, tavik_order_lv17,
):
    """Optional target_combatant_id passed through. With a bogus
    id like "tok_test", `_install_buff_on_combatant_id` returns
    False (no matching combatant) → `curse_installed: False`."""
    tavik = tavik_order_lv17
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_orders_wrath",
        json={"character_id": tavik["id"], "target_combatant_id": "tok_test"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["target_combatant_id"] == "tok_test"
    assert data["curse_installed"] is False, (
        f"bogus target should not install a curse; got {data}"
    )


def _pc(cid, c, *, hp_max=80):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def test_ow_installs_curse_on_real_target_combatant(
    gm_client, gm_ws, tavik_order_lv17, roster,
):
    """v2.158.5 — state contract (Phase 9): when invoked with a
    real `target_combatant_id`, the endpoint installs the
    `orders-wrath-curse` buff on the target combatant via
    `_install_buff_on_combatant_id`. The installed buff carries
    the three `orders_wrath_*` effect keys (psychic damage
    expression, caster char id, active flag) so the future
    Phase 2 read site (the /attack flow detecting an ally hitting
    a cursed target) has a stable contract to look up.

    Uses Pip as the target combatant for test simplicity —
    semantically Pip is an ally, but Phase 1 just installs the
    buff payload; Phase 2's ally-vs-caster filter is what would
    skip self-hits and caster-hits at trigger time."""
    tavik = tavik_order_lv17
    pip = roster["Pip Quickfingers"]
    tavik_tok = f"tok_ow_tavik_{tavik['id']}"
    pip_tok = f"tok_ow_pip_{pip['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_pc(tavik_tok, tavik), _pc(pip_tok, pip)],
              "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_orders_wrath",
        json={"character_id": tavik["id"], "target_combatant_id": pip_tok},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["curse_installed"] is True, (
        f"real target should install the curse; got {data}"
    )

    # `_install_buff_on_combatant_id` broadcasts `battle_update`
    # (no per-combatant `buff_update` for NPCs / by-id installs).
    bu = await gm_ws.wait_for("battle_update")
    combs = {c.get("id"): c for c in (bu["data"].get("combatants") or [])}
    pip_cb = combs.get(pip_tok)
    assert pip_cb is not None, (
        f"Pip's combatant missing from battle_update; got "
        f"ids={list(combs.keys())}"
    )
    curse_buff = next(
        (b for b in (pip_cb.get("buffs") or [])
         if b.get("key") == "orders-wrath-curse"),
        None,
    )
    assert curse_buff is not None, (
        f"orders-wrath-curse buff missing from Pip; got "
        f"buffs={pip_cb.get('buffs')}"
    )
    effects = curse_buff.get("effects") or {}
    assert effects.get("orders_wrath_psychic_damage_expression") == "2d8", (
        f"psychic damage expression wrong; got effects={effects}"
    )
    assert int(effects.get("orders_wrath_caster_char_id") or 0) == int(tavik["id"]), (
        f"caster_char_id wrong; got effects={effects}"
    )
    assert effects.get("orders_wrath_active") is True, (
        f"active flag missing; got effects={effects}"
    )
    # 2-round duration covers "until the start of your next turn".
    assert int(curse_buff.get("duration_rounds") or 0) == 2
    assert curse_buff.get("concentration") in (False, None)


async def test_use_ow_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_orders_wrath",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ow_level_gate(
    gm_client, roster,
):
    """Order Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Order Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_orders_wrath",
            json={"character_id": tavik["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


def _mkc_npc(cid, tmpl_id, *, name, hp_cur=20, hp_max=20):
    return {
        "id": cid, "char_id": None, "token_template_id": tmpl_id,
        "name": name, "initiative": 10,
        "hp_current": hp_cur, "hp_max": hp_max, "speed_walk": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def _set_auto_apply(gm_client, on: bool) -> None:
    form = {
        "name": "Demo Campaign", "description": "demo",
        "game_system": "dnd5e", "gm_tab_color": "", "font_override": "",
        "default_encounter_id": "", "hp_threshold_1": "", "hp_threshold_2": "",
        "hp_threshold_3": "", "hp_threshold_4": "", "auto_play_playlist_id": "",
        "auto_play_mode": "order", "auto_play_initial_volume": "0.7",
    }
    if on:
        form["auto_apply_damage"] = "on"
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form,
        follow_redirects=False,
    )


@pytest_asyncio.fixture
async def auto_apply_on(gm_client):
    await _set_auto_apply(gm_client, True)
    yield
    await _set_auto_apply(gm_client, False)


async def test_ow_ally_hit_on_cursed_npc_triggers_psychic_and_drops_curse(
    gm_client, gm_ws, tavik_order_lv17, roster, auto_apply_on,
):
    """v2.158.8 — Phase 2 end-to-end: when an ally (not the cleric)
    hits an NPC carrying the `orders-wrath-curse` buff, the on-hit
    trigger in `_apply_damage_to_combatant` deals 2d8 psychic to
    the target + drops the curse buff.

    Setup: PATCH Tavik to Order Lv 17 + install the curse on a
    high-HP Bandit (so the 2d8 psychic doesn't kill outright + we
    can verify the curse drop on the next battle_update). Pip
    swings at the cursed Bandit until a hit lands.

    Assertions: a `feature_used` broadcast with source
    `orders-wrath-trigger` fires naming Tavik as the curse caster
    + a psychic_damage value in [2, 16] + the orders-wrath-curse
    buff is absent from the Bandit's buffs in a subsequent
    battle_update."""
    tavik = tavik_order_lv17
    pip = roster["Pip Quickfingers"]
    tavik_tok = f"tok_ow_p2_tav_{tavik['id']}"
    pip_tok = f"tok_ow_p2_pip_{pip['id']}"
    bandit_id = "tok_ow_p2_bandit"

    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(
        (t for t in templates if "bandit" in t["name"].lower()),
        templates[0],
    )

    # Seed 3-combatant battle. High-HP bandit (50 HP) so 2d8 psychic
    # damage definitely doesn't kill (max 16) and we can verify the
    # buff drop on the surviving target.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _pc(tavik_tok, tavik), _pc(pip_tok, pip),
            _mkc_npc(bandit_id, bandit_tmpl["id"],
                     name=bandit_tmpl["name"], hp_cur=50, hp_max=50),
        ], "turn_index": 0, "round": 1, "active": True},
    )

    # Install the curse on the bandit via the v2.158.5 endpoint.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_orders_wrath",
        json={"character_id": tavik["id"],
              "target_combatant_id": bandit_id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["curse_installed"] is True

    # Pip swings until a hit lands. Bandit AC ~12 vs Pip's
    # Shortsword +6 → ~70% hit; bound to 12 attempts.
    gm_ws.mark()
    hit = None
    for _ in range(12):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": pip["id"],
                  "attack_index": 0,
                  "target_combatant_id": bandit_id,
                  "override": True},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        if d.get("hit") is True and int(d.get("damage_total") or 0) >= 1:
            hit = d
            break
    assert hit is not None, "Pip failed to hit the bandit in 12 swings"
    await asyncio.sleep(0.3)

    # Assert orders-wrath-trigger fired naming Tavik as the caster.
    trigger_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "orders-wrath-trigger"
        and int((m.get("data") or {}).get("character_id") or 0)
            == int(tavik["id"])
    ]
    assert trigger_msgs, (
        "no orders-wrath-trigger broadcast fired after the ally "
        "hit the cursed bandit"
    )
    last_trigger = trigger_msgs[-1]
    psychic_dmg = int((last_trigger.get("data") or {}).get("psychic_damage") or 0)
    assert 2 <= psychic_dmg <= 16, (
        f"2d8 psychic should be in [2, 16]; got {psychic_dmg}"
    )
    assert (last_trigger.get("data") or {}).get("target_combatant_id") == bandit_id

    # Verify the curse was dropped. Check the most recent
    # battle_update for the bandit's buffs list — the
    # orders-wrath-curse buff should be gone.
    bus = gm_ws.buffered("battle_update")
    assert bus, "no battle_update broadcast received"
    last_bu = bus[-1]
    combs = {c.get("id"): c for c in (last_bu["data"].get("combatants") or [])}
    bandit_cb = combs.get(bandit_id)
    assert bandit_cb is not None, (
        f"bandit missing from last battle_update; got ids={list(combs.keys())}"
    )
    curse_still_there = next(
        (b for b in (bandit_cb.get("buffs") or [])
         if b.get("key") == "orders-wrath-curse"),
        None,
    )
    assert curse_still_there is None, (
        f"orders-wrath-curse should be dropped after triggering; "
        f"got bandit buffs={bandit_cb.get('buffs')}"
    )
