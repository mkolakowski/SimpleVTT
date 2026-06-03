"""v2.99.116 — /use_stunning_strike refactored to use the v2.99.115
factory; the NPC install path now produces a dict-shape `effects`
that the v2.99.98 speed engine reads.

Pre-v2.99.116 the buff carried list-shape `effects` (descriptive
bullets only). The v2.99.98 `_effective_speed_reduction_ft` helper
skips non-dict effects, so Stunned NPC targets could still be
moved server-side. v2.99.116 swaps the inline buff construction
for `_make_stunning_strike_stunned_buff(target_speed_walk, ...)`.

The pre-existing test_use_stunning_strike.py suite already verifies
end-to-end behavior (Ki spend + save outcomes + chat card +
undo). This file adds the FACTORY-SHAPE pin: after a successful
Stunning Strike, the installed buff carries:
  - effects.speed_reduction_ft = target's base speed
  - raw_effects (the canonical Stunned bullets)
  - source: "stunning-strike"

These assertions ensure the refactor is real — the buff actually
reaches the speed engine, not just the legacy descriptive list.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def kael_rested(gm_client, roster):
    kael = roster["Kael Brightleaf"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
        json={"type": "long"},
    )
    return kael


async def _bandit_template(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next((t for t in templates if "bandit" in t["name"].lower()), templates[0])


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def test_stunning_strike_npc_buff_uses_factory_shape(
    gm_client, gm_ws, kael_rested,
):
    """Cast Stunning Strike on a bandit; loop until save fails;
    inspect the bandit's Stunned buff to confirm it carries the
    v2.99.115 factory shape (dict effects + raw_effects + source).
    """
    kael = kael_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_test_ss_factory_bandit"

    bandit_speed = 30  # bandit RAW base speed; the buff's reduction
                       # should equal this.
    saw_failed_save = False
    for _ in range(25):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
            json={"type": "long"},
        )
        await _seed_battle(gm_client, [
            {"id": f"tok_ss_factory_{kael['id']}", "char_id": kael["id"],
             "name": kael["name"], "initiative": 10,
             "hp_current": 38, "hp_max": 38, "buffs": [],
             "speed_walk": 40,
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"id": bandit_id, "char_id": None,
             "token_template_id": bandit_tmpl["id"],
             "name": bandit_tmpl["name"], "initiative": 7,
             "hp_current": 11, "hp_max": 11, "buffs": [],
             "speed_walk": bandit_speed,
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ])
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_stunning_strike",
            json={
                "character_id": kael["id"],
                "target_combatant_id": bandit_id,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        if body.get("auto_save_passed") is False:
            saw_failed_save = True
            break

    assert saw_failed_save, "no save failure in 25 attempts"

    # Inspect the buff via the battle_update broadcast.
    bu = await gm_ws.wait_for("battle_update", timeout=3.0)
    combatants = (bu.get("data") or {}).get("combatants") or []
    bandit = next((c for c in combatants if c.get("id") == bandit_id), None)
    assert bandit is not None, f"bandit missing; got {combatants}"
    stunned_buffs = [
        b for b in (bandit.get("buffs") or [])
        if (b or {}).get("key") == "stunned"
    ]
    assert stunned_buffs, f"no stunned buff; got {bandit.get('buffs')}"
    buff = stunned_buffs[0]

    # v2.99.115 factory shape pins.
    # 1. effects is now a dict with speed_reduction_ft (was a list).
    effects = buff.get("effects")
    assert isinstance(effects, dict), (
        f"expected dict effects (v2.99.116 factory); got {type(effects)}: {effects}"
    )
    assert effects.get("speed_reduction_ft") == bandit_speed, (
        f"speed_reduction_ft should equal target's base speed "
        f"({bandit_speed}); got {effects}"
    )
    # 2. raw_effects holds the canonical Stunned bullets + Stunning
    #    Strike-specific ones.
    raw = buff.get("raw_effects") or []
    assert any("speed 0" in line.lower() for line in raw), raw
    assert any("ki point" in line.lower() for line in raw), raw
    # 3. source attribution from the factory.
    assert buff.get("source") == "stunning-strike", buff
    # 4. Legacy compat: source_spell still set for the undo flow.
    assert buff.get("source_spell") == "Stunning Strike", buff
    # 5. Existing test invariants still hold.
    assert buff.get("concentration") is False, buff
    assert buff.get("source_char_id") == kael["id"], buff
