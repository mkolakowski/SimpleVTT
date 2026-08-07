"""v2.99.17 — (D) Phase 3 second-ship: Half-Orc Relentless Endurance.

RAW (PHB p.41, Half-Orc race trait): "When you are reduced to 0 hit
points but not killed outright, you can drop to 1 hit point instead.
You can't use this feature again until you finish a long rest."

Auto-fire — no decision, no resource cost beyond the 1/long-rest
counter. The implementation lives in `_apply_hp_change`: when
damage would set HP to 0 AND the massive-damage rule didn't fire
(`damage_amount - old_current < max_hp`) AND the
`relentless-endurance` resource is available, the function clamps
new_current to 1, decrements the resource, stays at status="alive",
and returns a `relentless_endurance_fired: True` flag.

The main damage path `_apply_damage_to_combatant` reads that flag
and emits a `feature_used(source=relentless-endurance)` broadcast
plus a `resource_update` (so the per-PC resource UI flips
1/1 → 0/1 without a manual refresh).

Test strategy:
- Set Krieger (Half-Orc Berserker) HP low (3) via sheet-fields PATCH.
- Pip attacks Krieger; loop seeded dice until a hit lands with
  enough damage to reduce Krieger to 0.
- Assert Krieger's resulting HP is 1 (not 0); status is "alive"
  (not "dying"); `feature_used(source=relentless-endurance)`
  broadcast fires; resource counter decremented from 1 → 0.
- Re-test after consuming the resource: same setup, this time
  Krieger's hp_change should NOT clamp (resource current=0 → not
  available), so a follow-on hit at low HP puts him dying.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .helpers import AttemptLog


async def _seed_dice(gm_client, seed: int):
    resp = await gm_client.post(
        "/api/test/dice/seed", json={"seed": seed},
    )
    assert resp.status_code == 200, resp.text


async def _set_hp(gm_client, char_id: int, hp_current: int):
    """Set the character's HP via sheet-fields PATCH. Bypasses the
    death-save state machine — used by the test to position Krieger
    at low HP without going through damage."""
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"hp": {"current": hp_current}},
    )


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


def _tok(char, hp_current: int = 30, hp_max: int = 60):
    return {
        "id": f"tok_re_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": hp_current,
        "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


def _re_broadcasts(gm_ws, character_id: int) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "relentless-endurance"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def pip_rested(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    return pip


@pytest_asyncio.fixture
async def krieger_rested(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    return krieger


async def test_relentless_endurance_clamps_zero_to_one(
    gm_client, gm_ws, pip_rested, krieger_rested,
):
    """Krieger is at 3 HP; Pip lands a hit dealing ≥3 damage. Krieger
    should land at HP=1 (not 0), stay alive, and a
    feature_used(source=relentless-endurance) broadcast should fire.
    Resource counter decrements from 1 → 0.
    """
    pip = pip_rested
    krieger = krieger_rested
    # Set Krieger to 3 HP so even minimum-damage attack drops him
    # to 0 (and Relentless Endurance clamps to 1).
    await _set_hp(gm_client, krieger["id"], 3)
    await _seed_battle(gm_client, [
        _tok(pip, hp_current=40, hp_max=40),
        _tok(krieger, hp_current=3, hp_max=60),
    ])
    gm_ws.mark()
    # Pip attacks Krieger; loop until a hit lands.
    krieger_tok = f"tok_re_{krieger['id']}"
    hit_landed = False
    _log = AttemptLog()
    for seed in range(1, 200):
        await _seed_dice(gm_client, seed)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": 0,  # Pip's Shortsword
                "target_combatant_id": krieger_tok,
                "override": True,
            },
        )
        _log.record(r)
        if r.status_code != 200:
            continue
        data = r.json()
        if data.get("hit") and int(data.get("damage_applied") or 0) >= 3:
            hit_landed = True
            break
    assert hit_landed, f"no hit dealing ≥3 damage landed in 200 seeds — {_log.summary()}"

    # Give async broadcasts a beat to land.
    import asyncio as _asy
    await _asy.sleep(0.3)

    # Assert: feature_used broadcast fired.
    msgs = _re_broadcasts(gm_ws, krieger["id"])
    assert msgs, (
        f"expected feature_used(source=relentless-endurance) for Krieger; "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )

    # Assert: character_hp_update broadcast carries HP=1 (not 0).
    hp_msgs = [
        m for m in gm_ws.buffered("character_hp_update")
        if (m.get("data") or {}).get("character_id") == krieger["id"]
    ]
    assert hp_msgs, "expected a character_hp_update broadcast for Krieger"
    last_hp = (hp_msgs[-1].get("data") or {}).get("hp") or {}
    _cur = last_hp.get("current")
    assert _cur == 1, (
        f"expected HP=1 after Relentless Endurance clamp; "
        f"got hp={last_hp}"
    )

    # Assert: resource_update broadcast for relentless-endurance shows
    # current=0 (decremented from 1).
    res_msgs = [
        m for m in gm_ws.buffered("resource_update")
        if (m.get("data") or {}).get("character_id") == krieger["id"]
        and (m.get("data") or {}).get("key") == "relentless-endurance"
    ]
    assert res_msgs, (
        f"expected resource_update for relentless-endurance; "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('key')) for m in gm_ws.buffered()]}"
    )
    _res_cur = (res_msgs[-1].get("data") or {}).get("current")
    assert _res_cur == 0, (
        f"expected resource current=0 after decrement; "
        f"got {res_msgs[-1].get('data')}"
    )


async def test_relentless_endurance_skips_non_half_orc(
    gm_client, gm_ws, pip_rested, roster,
):
    """Control: Lyra (Half-Elf) doesn't have the Relentless Endurance
    resource. Sleep + damage path through 0 HP → goes dying (no
    clamp). Regression guard against over-broad clamping.
    """
    pip = pip_rested
    lyra = roster["Lyra Sunstrider"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    await _set_hp(gm_client, lyra["id"], 3)
    await _seed_battle(gm_client, [
        _tok(pip, hp_current=40, hp_max=40),
        _tok(lyra, hp_current=3, hp_max=35),
    ])
    gm_ws.mark()
    lyra_tok = f"tok_re_{lyra['id']}"
    hit_landed = False
    _log = AttemptLog()
    for seed in range(1, 200):
        await _seed_dice(gm_client, seed)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": 0,
                "target_combatant_id": lyra_tok,
                "override": True,
            },
        )
        _log.record(r)
        if r.status_code != 200:
            continue
        data = r.json()
        if data.get("hit") and int(data.get("damage_applied") or 0) >= 3:
            hit_landed = True
            break
    assert hit_landed, f"no hit dealing ≥3 damage landed in 200 seeds — {_log.summary()}"

    import asyncio as _asy
    await _asy.sleep(0.3)

    # No Relentless Endurance broadcast.
    msgs = _re_broadcasts(gm_ws, lyra["id"])
    assert not msgs, (
        f"Relentless Endurance broadcast should NOT fire for Lyra: {msgs}"
    )
    # character_hp_update should show HP=0 (no clamp).
    hp_msgs = [
        m for m in gm_ws.buffered("character_hp_update")
        if (m.get("data") or {}).get("character_id") == lyra["id"]
    ]
    assert hp_msgs, "expected a character_hp_update for Lyra"
    last_hp = (hp_msgs[-1].get("data") or {}).get("hp") or {}
    _lcur = last_hp.get("current")
    assert _lcur == 0, (
        f"expected HP=0 (no Relentless Endurance clamp); got hp={last_hp}"
    )
