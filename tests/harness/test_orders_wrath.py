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
