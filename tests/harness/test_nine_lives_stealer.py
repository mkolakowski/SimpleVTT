"""v2.335.0 — magic-items: Nine Lives Stealer (RAW DMG p.183, very rare,
attunement). The first on_nat_20 item to use the NEW `effect: "slay_save"`
variant: on a critical hit against a creature with fewer than 100 HP, the
target makes a DC 15 CON save or is slain instantly (constructs/undead
immune). Composes three substrate pieces — the v2.158.101 nat-20 gate, the
v2.158.101 `exempt_creature_types` list (Vorpal / Life Stealing), and the
v2.99.406 `_resolve_feature_save` helper (Demon Slayer on_hit_save path) —
plus the new `max_target_hp` HP gate.

Demo fixture: Pip Quickfingers (Rogue Lv 7) carries the sword at
`attack_index 4` + inventory tail, seeded INERT (equipped=False,
attuned=False). Tests PATCH the inventory equipped+attuned via
/sheet-fields (bypassing the /attune cap), then drive seeded nat-20 rolls.
The slay only fires on a FAILED save, so the happy-path test iterates
seeds until a nat-20 lands AND the bare-CON bandit fails its DC 15 save.

Tests:
  - Happy path: nat-20 vs a low-HP humanoid that fails the save → the
    `item-nine-lives-stealer-nat20` slay broadcast fires.
  - Construct exempt: nat-20 vs a construct → no slay (exempt gate).
  - HP gate: nat-20 vs a 200-HP humanoid → no slay (≥100 HP gate).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


PIP_NINE_LIVES_ATTACK_IDX = 4
_NINE_LIVES_SLUG = "nine-lives-stealer"
_SLAY_SOURCE = "item-nine-lives-stealer-nat20"


async def _seed_dice(gm_client, seed):
    r = await gm_client.post("/api/test/dice/seed", json={"seed": seed})
    assert r.status_code == 200, r.text


def _mkc(cid, char_id=None, name="X", creature_type="", ac=1, hp_max=60):
    return {
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


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _snapshot_inv(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    inv = list((resp.json().get("sheet") or {}).get("inventory") or [])
    return [dict(it) if isinstance(it, dict) else it for it in inv]


async def _patch_inv(gm_client, char_id, slug, *, equipped, attuned):
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == slug:
            it["equipped"] = equipped
            it["attuned"] = attuned
            found = True
    assert found, f"Pip has no {slug} item"
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


def _slay_msgs(gm_ws):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == _SLAY_SOURCE
    ]


async def _d20_is_20(data):
    import re
    breakdown = data.get("attack_breakdown") or ""
    m = re.search(r"\d*d20[^d=+ ]*=(\d+)", breakdown, re.IGNORECASE)
    return bool(m and int(m.group(1)) == 20)


@pytest_asyncio.fixture
async def pip(roster):
    return roster["Pip Quickfingers"]


async def _bandit_template_id(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert r.status_code == 200, r.text
    bandit = next(
        (t for t in r.json() if t.get("name") == "Bandit"), None,
    )
    assert bandit is not None, "Bandit template missing from the demo seed"
    return bandit["id"]


async def test_nine_lives_slays_on_nat_20_failed_save(gm_client, gm_ws, pip):
    """v2.335.0 happy path. PATCH the sword equipped+attuned, then iterate
    seeds until a nat-20 lands AND the target fails its DC 15 CON save — at
    which point the slay broadcast fires and the target is slain.

    The target is a real **Bandit** NPC template (CON 11, +0 save) so
    `_resolve_feature_save` rolls the save inline (a bare combatant with
    neither `token_template_id` nor `char_id` returns `passed=None` and
    never slays). HP is forced to 60 on the combatant (< the 100-HP gate)."""
    template_id = await _bandit_template_id(gm_client)
    snap = await _patch_inv(
        gm_client, pip["id"], _NINE_LIVES_SLUG, equipped=True, attuned=True,
    )
    try:
        fired = False
        for seed in range(0, 400):
            await _seed_dice(gm_client, seed)
            pip_cid = f"tok_nls_hit_pip_{pip['id']}_{seed}"
            target_cid = f"tok_nls_hit_target_{seed}"
            target = _mkc(target_cid, None, name="Bandit", hp_max=60)
            target["token_template_id"] = template_id
            await _seed_battle(gm_client, [
                _mkc(pip_cid, pip["id"], name=pip["name"]),
                target,
            ])
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/attack",
                json={
                    "character_id": pip["id"],
                    "attack_index": PIP_NINE_LIVES_ATTACK_IDX,
                    "target_combatant_id": target_cid,
                    "override": True,
                },
            )
            assert resp.status_code == 200, resp.text
            if _slay_msgs(gm_ws):
                fired = True
                break

        assert fired, (
            "Across seeds 0..399 no nat-20 + failed-save slay fired — the "
            "slay_save dispatch or the save resolution may be broken. "
            f"feature_used sources seen: "
            f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
        )
        msg = _slay_msgs(gm_ws)[-1].get("data") or {}
        assert "Nine Lives Stealer" in (msg.get("feature_name") or "")
    finally:
        await _restore_inv(gm_client, pip["id"], snap)
        await _seed_dice(gm_client, None)


async def test_nine_lives_no_slay_on_construct(gm_client, gm_ws, pip):
    """v2.335.0: a construct is exempt (RAW: construct/undead immune). Even
    on a nat-20 the slay broadcast must NOT fire — the exempt gate
    short-circuits before the save. Iterates seeds to land a real nat-20."""
    snap = await _patch_inv(
        gm_client, pip["id"], _NINE_LIVES_SLUG, equipped=True, attuned=True,
    )
    try:
        nat_20_seed = None
        for seed in range(0, 200):
            await _seed_dice(gm_client, seed)
            pip_cid = f"tok_nls_con_pip_{pip['id']}_{seed}"
            target_cid = f"tok_nls_con_target_{seed}"
            await _seed_battle(gm_client, [
                _mkc(pip_cid, pip["id"], name=pip["name"]),
                _mkc(target_cid, None, name="Iron Golem",
                     creature_type="construct", hp_max=60),
            ])
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/attack",
                json={
                    "character_id": pip["id"],
                    "attack_index": PIP_NINE_LIVES_ATTACK_IDX,
                    "target_combatant_id": target_cid,
                    "override": True,
                },
            )
            assert resp.status_code == 200, resp.text
            if await _d20_is_20(resp.json()):
                nat_20_seed = seed
                break

        assert nat_20_seed is not None, (
            "Couldn't land a nat-20 in seeds 0..199 vs a construct."
        )
        assert not _slay_msgs(gm_ws), (
            f"Nat-20 landed on seed {nat_20_seed} vs a construct, but the "
            f"slay fired anyway (should be exempt)."
        )
    finally:
        await _restore_inv(gm_client, pip["id"], snap)
        await _seed_dice(gm_client, None)


async def test_nine_lives_no_slay_above_hp_gate(gm_client, gm_ws, pip):
    """v2.335.0: a target with ≥ 100 HP is above the RAW gate ("fewer than
    100 hit points"), so the slay must NOT fire even on a nat-20. Iterates
    seeds to land a real nat-20 vs a 200-HP humanoid."""
    snap = await _patch_inv(
        gm_client, pip["id"], _NINE_LIVES_SLUG, equipped=True, attuned=True,
    )
    try:
        nat_20_seed = None
        for seed in range(0, 200):
            await _seed_dice(gm_client, seed)
            pip_cid = f"tok_nls_hp_pip_{pip['id']}_{seed}"
            target_cid = f"tok_nls_hp_target_{seed}"
            await _seed_battle(gm_client, [
                _mkc(pip_cid, pip["id"], name=pip["name"]),
                _mkc(target_cid, None, name="Ogre Chief",
                     creature_type="humanoid", hp_max=200),
            ])
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/attack",
                json={
                    "character_id": pip["id"],
                    "attack_index": PIP_NINE_LIVES_ATTACK_IDX,
                    "target_combatant_id": target_cid,
                    "override": True,
                },
            )
            assert resp.status_code == 200, resp.text
            if await _d20_is_20(resp.json()):
                nat_20_seed = seed
                break

        assert nat_20_seed is not None, (
            "Couldn't land a nat-20 in seeds 0..199 vs a 200-HP target."
        )
        assert not _slay_msgs(gm_ws), (
            f"Nat-20 landed on seed {nat_20_seed} vs a 200-HP target, but "
            f"the slay fired anyway (should be gated by the <100 HP rule)."
        )
    finally:
        await _restore_inv(gm_client, pip["id"], snap)
        await _seed_dice(gm_client, None)
