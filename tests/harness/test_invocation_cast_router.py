"""v2.99.140 — Invocation-driven spell-cast router tests.

Closes the v2.99.137 filed item. The v2.99.140 refactor extracts
the per-invocation inline branches in /cast_<spell> endpoints into
``_INVOCATION_SPELL_CAST_REGISTRY`` + three helpers
(``_get_invocation_cast_meta``, ``_validate_invocation_cast``,
``_consume_invocation_resource``). The v2.99.137 Mire the Mind
behavior is preserved end-to-end — `test_mire_the_mind.py` is the
behavior regression net.

This file adds router-specific regression guards:
  - An unknown invocation slug + Warlock → 409 missing_invocation
    (the registry's spell_slug match rejects it).
  - A Wizard / Sorcerer passing a registered via_invocation slug
    they don't have on their feats → 409 missing_invocation (the
    registry helper enforces the feats-list check regardless of
    class).
  - Wizard passing NO via_invocation still works via the normal
    spell-list route (registry doesn't run, falls through to
    standard validation).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", speed_walk=30):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "speed_walk": speed_walk,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def magnus_rested(gm_client, roster):
    """Long-rest Magnus so Mire the Mind use is fresh."""
    magnus = roster["Magnus Hexbinder"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    return magnus


async def test_unknown_invocation_slug_warlock_409(
    gm_client, magnus_rested, roster,
):
    """Warlock with via_invocation set to a slug NOT in the registry
    → 409 missing_invocation. The registry's "spell_slug == 'slow'"
    match rejects the cast attempt.
    """
    magnus = magnus_rested
    krieger = roster["Krieger Stonefist"]
    mg_tok = f"tok_inv_unk_mg_{magnus['id']}"
    kr_tok = f"tok_inv_unk_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(mg_tok, magnus["id"], name=magnus["name"]),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "bogus-not-registered",
            "slot_level": 3,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"


async def test_wizard_with_registered_invocation_slug_missing_feats_409(
    gm_client, roster,
):
    """Thalindra (Wizard) passes ``via_invocation="mire-the-mind"``
    but doesn't have the invocation on her feats list → 409
    missing_invocation (the registry helper enforces the feats
    check regardless of the caller's class).
    """
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_inv_wiz_inv_th_{thalindra['id']}"
    kr_tok = f"tok_inv_wiz_inv_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"]),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "via_invocation": "mire-the-mind",
            "slot_level": 3,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"


async def test_wizard_no_invocation_uses_normal_route(
    gm_client, roster,
):
    """Thalindra (Wizard) casts Slow with NO via_invocation flag —
    the standard spell-list + slot route runs (registry doesn't
    fire). Confirms the refactor didn't break the Wizard path.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_inv_wiz_norm_th_{thalindra['id']}"
    kr_tok = f"tok_inv_wiz_norm_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"]),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 3,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    affected = data.get("affected") or []
    assert len(affected) == 1
    assert affected[0]["installed"] is True
