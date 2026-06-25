"""v2.252.0 — advantage/disadvantage Phase 4a: Cloak of Displacement
(RAW DMG p.158, rare, attunement). "the cloak ... causes any creature to
have disadvantage on attack rolls against you."

This is the first ITEM-granted adv/dis source. The condition/feature
substrate (Phase 2a–2f) reads adv/dis from combatant buffs; the cloak is a
passive on the wearer's CHARACTER SHEET, so the attack pipeline resolves
the target combatant → character → sheet via
``_target_wearer_imposes_attack_disadvantage`` and folds an
``incoming_attacks_have_disadvantage`` boolean (set in
``_equipped_item_effects`` from the ``cloak-of-displacement`` catalog
payload, attunement-gated) into the existing /attack + /npc_attack
disadvantage source set. Cancel logic (PHB p.173) comes for free.

Demo fixture: Lyra Sunstrider (Bard) wears it as a (4th) attuned item —
the seed predates the strict 3/3 cap, which lives only on the /attune
runtime endpoint (Garrik / Frost Brand precedent, v2.251.0).
"""
import asyncio

import pytest_asyncio

from .conftest import CAMPAIGN_ID

_SLUG = "cloak-of-displacement"


def _mkc(cid, char_id=None, name="X", buffs=None, ac=1):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 200, "hp_max": 200,
        "ac": ac,
        "buffs": buffs or [],
        "creature_type": "",
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


async def _sheet_json(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _cloak_inv_idx(gm_client, char_id):
    data = await _sheet_json(gm_client, char_id)
    inv = (data.get("sheet") or {}).get("inventory") or []
    for i, it in enumerate(inv):
        if it.get("_slug") == _SLUG:
            return i
    raise AssertionError(f"Cloak of Displacement not found: {inv!r}")


@pytest_asyncio.fixture
async def lyra(roster):
    return roster["Lyra Sunstrider"]


@pytest_asyncio.fixture
async def garrik(roster):
    return roster["Garrik Ironside"]


async def test_cloak_imposes_disadvantage_on_pc_attacker(
    gm_client, garrik, lyra,
):
    """A PC attacking the cloak-wearer rolls at disadvantage — the
    /attack response's roll_state_applied carries the cloak label."""
    atk_cid = f"tok_cod_garrik_{garrik['id']}"
    tgt_cid = f"tok_cod_lyra_{lyra['id']}"
    await _seed_battle(gm_client, [
        _mkc(atk_cid, garrik["id"], name=garrik["name"]),
        _mkc(tgt_cid, lyra["id"], name=lyra["name"]),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": garrik["id"],
            "attack_index": 0,
            "target_combatant_id": tgt_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("roll_state_applied") == (
        "disadvantage_cloak_of_displacement"
    ), resp.json()


async def test_cloak_imposes_disadvantage_on_npc_attacker(
    gm_client, lyra,
):
    """An NPC attacking the cloak-wearer is symmetric — /npc_attack also
    rolls at disadvantage with the cloak label."""
    npc_cid = "tok_cod_bandit"
    tgt_cid = f"tok_cod_npc_lyra_{lyra['id']}"
    await _seed_battle(gm_client, [
        _mkc(npc_cid, None, name="Bandit"),
        _mkc(tgt_cid, lyra["id"], name=lyra["name"]),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/npc_attack",
        json={
            "combatant_id": npc_cid,
            "action_name": "Scimitar",
            "attack_bonus": "+4",
            "damage": "1d6+2",
            "damage_type": "slashing",
            "target_combatant_id": tgt_cid,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("roll_state_applied") == (
        "disadvantage_cloak_of_displacement"
    ), resp.json()


async def test_cloak_cancels_with_attacker_advantage(
    gm_client, garrik, lyra,
):
    """PHB p.173: a source of advantage cancels the cloak's
    disadvantage to a straight roll. Lyra carries an
    incoming_attacks_have_advantage buff (Reckless-style) on her
    combatant — adv + dis = neither, labeled canceled_*."""
    atk_cid = f"tok_cod_cancel_garrik_{garrik['id']}"
    tgt_cid = f"tok_cod_cancel_lyra_{lyra['id']}"
    await _seed_battle(gm_client, [
        _mkc(atk_cid, garrik["id"], name=garrik["name"]),
        _mkc(tgt_cid, lyra["id"], name=lyra["name"], buffs=[
            {"key": "reckless-test", "name": "Reckless",
             "effects": {"incoming_attacks_have_advantage": True}},
        ]),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": garrik["id"],
            "attack_index": 0,
            "target_combatant_id": tgt_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    state = resp.json().get("roll_state_applied") or ""
    assert state.startswith("canceled_"), resp.json()
    assert "cloak_of_displacement" in state, resp.json()


async def _set_cloak_attuned(gm_client, char_id, attuned):
    """Flip the cloak's `attuned` flag via a sheet-fields PATCH rather
    than /attune. The cloak is Lyra's 4th attuned item (the demo seed
    predates the RAW 3/3 cap, which lives only on the /attune endpoint),
    so re-attuning via /attune would 409 on the cap. The PATCH path
    mirrors the seed-load bypass and exercises the walker's attunement
    gate directly — which is exactly what this test asserts on."""
    data = await _sheet_json(gm_client, char_id)
    inv = list((data.get("sheet") or {}).get("inventory") or [])
    idx = next(
        (i for i, it in enumerate(inv)
         if isinstance(it, dict) and it.get("_slug") == _SLUG),
        None,
    )
    assert idx is not None, "Cloak of Displacement not in inventory"
    inv[idx] = {**inv[idx], "attuned": attuned}
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": inv},
    )
    assert resp.status_code == 200, resp.text


async def test_cloak_detuned_drops_disadvantage(gm_client, garrik, lyra):
    """Detuning the cloak drops the disadvantage — the PC attack reverts
    to a straight roll (roll_state_applied None). Restores attunement in
    teardown via PATCH (cap-independent)."""
    await _set_cloak_attuned(gm_client, lyra["id"], False)
    try:
        atk_cid = f"tok_cod_detune_garrik_{garrik['id']}"
        tgt_cid = f"tok_cod_detune_lyra_{lyra['id']}"
        await _seed_battle(gm_client, [
            _mkc(atk_cid, garrik["id"], name=garrik["name"]),
            _mkc(tgt_cid, lyra["id"], name=lyra["name"]),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": garrik["id"],
                "attack_index": 0,
                "target_combatant_id": tgt_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json().get("roll_state_applied") is None, resp.json()
    finally:
        await _set_cloak_attuned(gm_client, lyra["id"], True)


async def test_cloak_suppressed_after_taking_damage(
    gm_client, gm_ws, garrik, lyra,
):
    """v2.645.0 — RAW DMG p.158 suppression clause: "If you take damage,
    the property ceases to function until the start of your next turn."
    Garrik attacks the cloak-wearer (Lyra, AC 1 so hits land); the first
    attack still rolls at disadvantage (roll_state computed before the
    hit's damage), the hit stamps the suppression + fires a
    feature_used(source=cloak-displacement-suppressed) broadcast, and a
    later attack the same round rolls straight (no cloak label).
    """
    # Full-heal Lyra first so she isn't left unconscious by an earlier
    # test — an unconscious target would add attacker advantage and
    # cancel the cloak's disadvantage label.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{lyra['id']}/rest",
        json={"type": "long"},
    )
    atk_cid = f"tok_cod_supp_garrik_{garrik['id']}"
    tgt_cid = f"tok_cod_supp_lyra_{lyra['id']}"
    await _seed_battle(gm_client, [
        _mkc(atk_cid, garrik["id"], name=garrik["name"]),
        _mkc(tgt_cid, lyra["id"], name=lyra["name"], ac=1),
    ])
    await asyncio.sleep(0.1)
    gm_ws.mark()

    async def _attack():
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": garrik["id"],
                "attack_index": 0,
                "target_combatant_id": tgt_cid,
                "override": True,
            },
        )
        assert r.status_code == 200, r.text
        return r.json()

    # Attack #1 — cloak active (disadvantage), regardless of hit/miss.
    first = await _attack()
    assert (first.get("roll_state_applied") or "") == (
        "disadvantage_cloak_of_displacement"
    ), first

    # Land a hit (AC 1 → near-certain; loop guards a nat-1 miss) so the
    # applied damage stamps the suppression for this round.
    hit = bool(first.get("hit")) or (first.get("damage_applied") or 0) > 0
    tries = 0
    while not hit and tries < 15:
        d = await _attack()
        hit = bool(d.get("hit")) or (d.get("damage_applied") or 0) > 0
        tries += 1
    assert hit, "Garrik never hit Lyra (AC 1) — extreme flake"

    await asyncio.sleep(0.15)
    supp = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "cloak-displacement-suppressed"
        and (m.get("data") or {}).get("character_id") == lyra["id"]
    ]
    assert supp, "expected feature_used(source=cloak-displacement-suppressed)"

    # A later attack the same round — cloak is suppressed, so no
    # disadvantage label (straight roll → roll_state_applied None).
    after = await _attack()
    assert "cloak_of_displacement" not in (
        after.get("roll_state_applied") or ""
    ), after


async def test_cloak_exposes_derived_flag(gm_client, lyra):
    """The wearer's /sheet-json reports
    derived.incoming_attacks_have_disadvantage naming the cloak."""
    data = await _sheet_json(gm_client, lyra["id"])
    flag = (data.get("derived") or {}).get(
        "incoming_attacks_have_disadvantage"
    )
    assert flag is not None, (
        f"expected derived.incoming_attacks_have_disadvantage, "
        f"got: {data.get('derived')!r}"
    )
    assert any(
        "Cloak of Displacement" in str(s) for s in flag.get("sources") or []
    ), f"expected the cloak named in sources, got: {flag!r}"
