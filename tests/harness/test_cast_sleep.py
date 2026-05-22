"""Sleep spell — HP-pool targeting endpoint.

v2.49.58 — adds ``POST /api/campaign/{cid}/cast_sleep``. 1st-level
enchantment (bard / sorcerer / warlock / wizard). RAW: roll 5d8 (+2d8
per slot level above 1st) as an HP pool; affect creatures in ascending
order of current HP, subtracting each affected creature's HP from the
pool until exhausted or the candidate list is empty. No save, no
concentration. Affected creatures are Unconscious for 1 minute or
until damaged / shaken awake.

This endpoint doesn't share /cast_spell's pipeline because the
HP-pool targeting + no-save mechanic doesn't fit either save-or-suck
or save-for-half. Dedicated endpoint mirrors the cast_hex pattern.

Tests:
  - happy path NPC: single low-HP bandit → always affected (5d8
    min=5; bandit HP=5 always fits).
  - ordering invariant: 3 bandits at 1/2/3 HP → affected list is
    non-decreasing by HP, sum of affected_hp <= pool_total, first
    unaffected (if any) has hp > pool_remaining.
  - high-HP skip: bandit at HP=50 → 5d8 max=40 < 50 → always
    unaffected.
  - already-unconscious skip: bandit pre-seeded with Unconscious
    buff is skipped entirely (RAW: ignored when ordering).
  - drops PC concentration: Magnus casts Hex (concentration); set
    Magnus HP=5; Thalindra casts Sleep targeting Magnus; on affect
    assert Magnus's Hex drops via v2.49.51 hook (Unconscious is in
    _INCAPACITATING_BUFF_KEYS) + 💀 GM log fires.
  - upcast scales pool: L3 slot → pool_expr = "9d8" (5 + 2*2).
  - 409 no_slot: drain wizard slots → try → 409.
  - 409 wrong_class: Krieger (Barbarian) → 409.
"""
import asyncio
import time
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def thalindra_rested(gm_client, roster):
    thalindra = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )
    return thalindra


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _bandit_template(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next((t for t in templates if "bandit" in t["name"].lower()), templates[0])


def _bandit_combatant(bandit_tmpl, tid: str, hp: int, init: int = 5,
                      buffs=None):
    return {
        "id": tid,
        "char_id": None,
        "token_template_id": bandit_tmpl["id"],
        "name": bandit_tmpl["name"],
        "initiative": init,
        "hp_current": hp,
        "hp_max": max(hp, 11),
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


def _pc_combatant(char, tid: str, hp: int = 30, init: int = 10, buffs=None):
    return {
        "id": tid,
        "char_id": char["id"],
        "name": char["name"],
        "initiative": init,
        "hp_current": hp,
        "hp_max": max(hp, 30),
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def test_sleep_happy_path_npc(gm_client, thalindra_rested):
    """Thalindra casts Sleep at L1 on a single 5-HP bandit. 5d8 min=5
    so the bandit always falls asleep."""
    thalindra = thalindra_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_sleep_happy"
    await _seed_battle(gm_client, [
        _pc_combatant(thalindra, f"tok_sleep_th_{thalindra['id']}"),
        _bandit_combatant(bandit_tmpl, bandit_id, hp=5),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 1,
            "target_combatant_ids": [bandit_id],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["slot_level"] == 1
    assert body["pool_expr"] == "5d8"
    assert 5 <= body["pool_total"] <= 40
    assert len(body["affected"]) == 1
    assert body["affected"][0]["combatant_id"] == bandit_id
    assert body["affected"][0]["hp"] == 5
    assert body["affected"][0]["installed"] is True
    assert body["unaffected"] == []


async def test_sleep_ordering_invariant(gm_client, thalindra_rested):
    """Three bandits at 1/2/3 HP. Verify the ordering + pool-math
    invariants hold for any 5d8 roll (min 5)."""
    thalindra = thalindra_rested
    bandit_tmpl = await _bandit_template(gm_client)
    await _seed_battle(gm_client, [
        _pc_combatant(thalindra, f"tok_sleep_th_{thalindra['id']}"),
        _bandit_combatant(bandit_tmpl, "tok_sleep_o3", hp=3, init=7),
        _bandit_combatant(bandit_tmpl, "tok_sleep_o1", hp=1, init=8),
        _bandit_combatant(bandit_tmpl, "tok_sleep_o2", hp=2, init=6),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 1,
            "target_combatant_ids": ["tok_sleep_o3", "tok_sleep_o1", "tok_sleep_o2"],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    affected = body["affected"]
    unaffected = body["unaffected"]
    # 5d8 min=5, max=40. 1+2+3=6. Pool>=5 always handles the 1-HP.
    assert len(affected) >= 1
    # Non-decreasing HP order in affected.
    aff_hp = [a["hp"] for a in affected]
    assert aff_hp == sorted(aff_hp), f"affected not ascending: {aff_hp}"
    # Sum of affected HP doesn't exceed pool.
    assert sum(aff_hp) <= body["pool_total"]
    # Pool remaining == pool_total - sum(affected).
    assert body["pool_remaining"] == body["pool_total"] - sum(aff_hp)
    # First unaffected (if any) has HP > pool_remaining at stop time.
    if unaffected:
        assert unaffected[0]["hp"] > body["pool_remaining"]


async def test_sleep_high_hp_skipped(gm_client, thalindra_rested):
    """Bandit at HP=50. 5d8 max=40 < 50 → always unaffected."""
    thalindra = thalindra_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_sleep_high"
    await _seed_battle(gm_client, [
        _pc_combatant(thalindra, f"tok_sleep_th_{thalindra['id']}"),
        _bandit_combatant(bandit_tmpl, bandit_id, hp=50),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 1,
            "target_combatant_ids": [bandit_id],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["affected"] == []
    assert len(body["unaffected"]) == 1
    assert body["unaffected"][0]["combatant_id"] == bandit_id
    assert body["unaffected"][0]["hp"] == 50


async def test_sleep_already_unconscious_skipped(gm_client, thalindra_rested):
    """Bandit pre-seeded with Unconscious buff is skipped entirely
    (RAW: 'ignoring unconscious creatures' when ordering)."""
    thalindra = thalindra_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_asleep = _bandit_combatant(
        bandit_tmpl, "tok_sleep_asleep", hp=5,
        buffs=[{
            "key": "unconscious",
            "name": "Unconscious",
            "icon": "💤",
            "concentration": False,
            "duration_rounds": 10,
            "effects": ["pre-seeded for test"],
        }],
    )
    bandit_awake = _bandit_combatant(bandit_tmpl, "tok_sleep_awake", hp=5, init=4)
    await _seed_battle(gm_client, [
        _pc_combatant(thalindra, f"tok_sleep_th_{thalindra['id']}"),
        bandit_asleep,
        bandit_awake,
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 1,
            "target_combatant_ids": ["tok_sleep_asleep", "tok_sleep_awake"],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Only the awake bandit should be in affected/unaffected lists —
    # the asleep one is skipped entirely.
    all_ids = [a["combatant_id"] for a in body["affected"]] + \
              [u["combatant_id"] for u in body["unaffected"]]
    assert "tok_sleep_asleep" not in all_ids
    assert "tok_sleep_awake" in all_ids


async def test_sleep_drops_pc_concentration(gm_client, gm_ws, thalindra_rested, roster):
    """Magnus has Hex up (concentration). Set Magnus HP=5; Thalindra
    casts Sleep targeting Magnus. Magnus falls asleep (Unconscious is
    in _INCAPACITATING_BUFF_KEYS) → v2.49.51 hook drops Magnus's Hex +
    fires 💀 GM log."""
    thalindra = thalindra_rested
    magnus = roster["Magnus Hexbinder"]
    pip = roster["Pip Quickfingers"]

    # Reset Magnus + Pip.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    for k in ("hex", "unconscious"):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": magnus["id"], "key": k},
        )

    await _seed_battle(gm_client, [
        _pc_combatant(thalindra, f"tok_sleep_th_{thalindra['id']}"),
        _pc_combatant(magnus, f"tok_sleep_m_{magnus['id']}", hp=5),
        _pc_combatant(pip, f"tok_sleep_p_{pip['id']}"),
    ])

    # Magnus casts Hex on Pip → Magnus is concentrating.
    h = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus["id"],
            "target_character_id": pip["id"],
            "ability": "STR",
            "override": True,
        },
    )
    assert h.status_code == 200, h.text

    # Verify pre-condition.
    b = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/buffs"
    )
    pre_keys = [(bf or {}).get("key") for bf in b.json().get("buffs", [])]
    assert "hex" in pre_keys

    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 1,
            "target_combatant_ids": [f"tok_sleep_m_{magnus['id']}"],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Magnus HP=5; pool >= 5 always; affected.
    assert len(body["affected"]) == 1
    assert body["affected"][0]["installed"] is True

    # Magnus's buffs should now have Unconscious AND no Hex.
    b = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/buffs"
    )
    post_keys = [(bf or {}).get("key") for bf in b.json().get("buffs", [])]
    assert "unconscious" in post_keys, f"Unconscious should land; got {post_keys}"
    assert "hex" not in post_keys, (
        f"Magnus's Hex should drop via v2.49.51 incapacitation hook; got {post_keys}"
    )

    # 💀 GM log entry should fire naming Hex as the dropped anchor.
    deadline = time.monotonic() + 2.0
    skull_logs: list = []
    while time.monotonic() < deadline:
        skull_logs = [
            m for m in gm_ws.buffered("roll")
            if (m.get("data") or {}).get("visibility") == "gm_only"
            and "💀" in ((m.get("data") or {}).get("note") or "")
            and "hex" in ((m.get("data") or {}).get("note") or "").lower()
        ]
        if skull_logs:
            break
        await asyncio.sleep(0.02)
    assert skull_logs, (
        f"expected 💀 GM log; got "
        f"{[(m.get('data') or {}).get('note') for m in gm_ws.buffered('roll')]}"
    )

    # Cleanup.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": magnus["id"], "key": "unconscious"},
    )


async def test_sleep_upcast_scales_pool(gm_client, thalindra_rested):
    """L3 slot → pool_expr should be '9d8' (5 + 2 * 2)."""
    thalindra = thalindra_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_sleep_upcast"
    await _seed_battle(gm_client, [
        _pc_combatant(thalindra, f"tok_sleep_th_{thalindra['id']}"),
        _bandit_combatant(bandit_tmpl, bandit_id, hp=5),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 3,
            "target_combatant_ids": [bandit_id],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slot_level"] == 3
    assert body["pool_expr"] == "9d8"  # 5 + 2 * (3 - 1)
    assert 9 <= body["pool_total"] <= 72


async def test_sleep_no_slot(gm_client, thalindra_rested):
    """Drain all wizard L1 slots and Sleep at L1 should 409 no_slot."""
    thalindra = thalindra_rested
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_sleep_noslot"

    # Drain L1 slots: Thalindra has 4 L1 slots; cast Sleep 4 times.
    for i in range(4):
        await _seed_battle(gm_client, [
            _pc_combatant(thalindra, f"tok_sleep_th_{thalindra['id']}"),
            _bandit_combatant(bandit_tmpl, f"{bandit_id}_{i}", hp=5),
        ])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
            json={
                "character_id": thalindra["id"],
                "class_slug": "wizard",
                "slot_level": 1,
                "target_combatant_ids": [f"{bandit_id}_{i}"],
                "override": True,
            },
        )
        assert r.status_code == 200, f"drain iter {i}: {r.text}"

    # 5th attempt at L1 → no slot.
    await _seed_battle(gm_client, [
        _pc_combatant(thalindra, f"tok_sleep_th_{thalindra['id']}"),
        _bandit_combatant(bandit_tmpl, f"{bandit_id}_x", hp=5),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 1,
            "target_combatant_ids": [f"{bandit_id}_x"],
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "no_slot"
    assert err["level"] == 1

    # Restore Thalindra's slots so subsequent tests in the suite have
    # a fresh L1 pool. Without this, /test_cast_spell::test_cast_magic_missile
    # (which also targets a L1 slot) flakes depending on test ordering.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )


async def test_sleep_wrong_class(gm_client, roster):
    """Krieger (Barbarian) tries Sleep → 409 wrong_class."""
    krieger = roster["Krieger Stonefist"]
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_id = "tok_sleep_wrong"
    await _seed_battle(gm_client, [
        _pc_combatant(krieger, f"tok_sleep_k_{krieger['id']}", hp=55),
        _bandit_combatant(bandit_tmpl, bandit_id, hp=5),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_sleep",
        json={
            "character_id": krieger["id"],
            "class_slug": "wizard",
            "slot_level": 1,
            "target_combatant_ids": [bandit_id],
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "wrong_class"
    assert err["expected"] == "wizard"
