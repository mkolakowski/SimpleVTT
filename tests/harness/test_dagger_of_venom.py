"""v2.343.0 — magic-items: Dagger of Venom (RAW DMG p.161, rare, NO
attunement). The first on_hit_save item to use the NEW
`effect: "damage_condition"` variant — damage AND a condition on the same
failed save. RAW: a hit lets the target make a DC 15 CON save or take 2d10
poison AND become poisoned for 1 minute (save negates both). No `condition`
predicate → fires on every hit. No attunement → the rider fires on slug
match alone.

Demo fixture: Pip Quickfingers (Rogue) carries it at `attack_index 5`,
equipped. Targets are real **Bandit** NPC templates (CON 11, +0 save) so
`_resolve_feature_save` rolls the save inline (a bare combatant returns
`passed=None` and never resolves). The coat-the-blade 1/min usage limit
is GM-narrated.

Tests:
  - The DC 15 CON poison save feature_used fires on a hit (proves the
    `damage_condition` on_hit_save dispatch).
  - On a failed save (sweep seeds), the target is poisoned AND took poison
    damage (proves both halves of `damage_condition`).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


PIP_DAGGER_OF_VENOM_ATTACK_IDX = 5
_SAVE_SOURCE = "item-dagger-of-venom-save"


async def _seed_dice(gm_client, seed):
    r = await gm_client.post("/api/test/dice/seed", json={"seed": seed})
    assert r.status_code == 200, r.text


def _mkc(cid, char_id=None, name="X", token_template_id=None, hp_max=60):
    c = {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_max, "hp_max": hp_max,
        "ac": 1,
        "buffs": [],
        "creature_type": "humanoid",
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    if token_template_id is not None:
        c["token_template_id"] = token_template_id
    return c


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _bandit_template_id(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert r.status_code == 200, r.text
    bandit = next((t for t in r.json() if t.get("name") == "Bandit"), None)
    assert bandit is not None, "Bandit template missing from the demo seed"
    return bandit["id"]


def _save_msgs(gm_ws):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == _SAVE_SOURCE
    ]


@pytest_asyncio.fixture
async def pip(roster):
    return roster["Pip Quickfingers"]


async def test_dagger_of_venom_save_fires_on_hit(gm_client, gm_ws, pip):
    """v2.343.0: a hit triggers the DC 15 CON poison save feature_used
    (source item-dagger-of-venom-save), proving the damage_condition
    on_hit_save dispatch. The Bandit template makes the NPC save roll
    inline."""
    template_id = await _bandit_template_id(gm_client)
    await _seed_dice(gm_client, 7)
    pip_cid = f"tok_dov1_pip_{pip['id']}"
    target_cid = "tok_dov1_target"
    target = _mkc(target_cid, None, name="Bandit", token_template_id=template_id)
    await _seed_battle(gm_client, [
        _mkc(pip_cid, pip["id"], name=pip["name"]),
        target,
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": pip["id"],
            "attack_index": PIP_DAGGER_OF_VENOM_ATTACK_IDX,
            "target_combatant_id": target_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("attack_name") == "Dagger of Venom"
    msgs = _save_msgs(gm_ws)
    assert msgs, (
        "Dagger of Venom poison-save feature_used did not fire on a hit. "
        f"sources: {[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
    )
    data = msgs[-1].get("data") or {}
    assert data.get("dc") == 15
    assert data.get("ability") == "CON"
    await _seed_dice(gm_client, None)


async def test_dagger_of_venom_poisons_on_failed_save(gm_client, gm_ws, pip):
    """v2.343.0: on a FAILED save, the target both takes poison damage AND
    gains the `poisoned` condition (proving both halves of
    `damage_condition`). Sweep seeds until a Bandit (CON 11, +0) fails the
    DC 15 save, then verify the poisoned buff is installed via GET /battle."""
    template_id = await _bandit_template_id(gm_client)
    poisoned_found = False
    for seed in range(0, 200):
        await _seed_dice(gm_client, seed)
        pip_cid = f"tok_dov2_pip_{pip['id']}_{seed}"
        target_cid = f"tok_dov2_target_{seed}"
        target = _mkc(target_cid, None, name="Bandit",
                      token_template_id=template_id, hp_max=60)
        await _seed_battle(gm_client, [
            _mkc(pip_cid, pip["id"], name=pip["name"]),
            target,
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": PIP_DAGGER_OF_VENOM_ATTACK_IDX,
                "target_combatant_id": target_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        battle = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
        combatants = (
            ((battle.json() or {}).get("battle") or {}).get("combatants") or []
        )
        me = next((c for c in combatants if c.get("id") == target_cid), None)
        if me is None:
            continue
        keys = {
            b.get("key") for b in (me.get("buffs") or [])
            if isinstance(b, dict)
        }
        if "poisoned" in keys:
            # Failed save → poisoned installed AND damage taken (< full HP).
            assert int(me.get("hp_current") or 60) < 60, (
                f"poisoned installed but no poison damage dealt: {me!r}"
            )
            poisoned_found = True
            break

    assert poisoned_found, (
        "Across seeds 0..199 the Bandit never failed the DC 15 CON save to "
        "get poisoned — the damage_condition install may be broken."
    )
    await _seed_dice(gm_client, None)
