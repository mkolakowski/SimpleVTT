"""v2.99.149 — /cast_bestow_curse endpoint tests.

L3 Necromancy, concentration up to 1 minute, touch, WIS save
(per-target saves are filed). Bard, Cleric, Wizard. Warlock-
only via the v2.99.149 Sign of Ill Omen invocation (PHB p.111:
"Prerequisite: 5th level. You can cast Bestow Curse once using
a warlock spell slot. You can't do so again until you finish
a long rest.").

Fourth consumer of the v2.99.140 invocation-cast registry —
after v2.99.137 Mire the Mind + v2.99.142 Sculptor of Flesh +
v2.99.148 Bewitching Whispers. Continues to prove the
abstraction generalizes (now across four target spells: L3
Slow, L4 Polymorph, L4 Compulsion, L3 Bestow Curse).

Magnus has eldritch-invocation-sign-of-ill-omen on his feats
list + a sign-of-ill-omen-uses 1/long-rest resource. RAW prereq
Lv 5 Warlock — Magnus qualifies natively (Lv 5 in the seed).

Tests:
  - happy path (Magnus via Sign of Ill Omen) → 200; slot +
    resource decrement; caster gets the concentration anchor
  - Warlock without via_invocation → 409 missing_invocation
  - Warlock with wrong via_invocation (mire-the-mind) → 409
    missing_invocation
  - second cast same long rest → 409 not_enough_uses
  - L2 slot → 400 (Bestow Curse is L3)
  - missing character_id → 400
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


async def _get_buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return {(b or {}).get("key") for b in resp.json().get("buffs") or []}


@pytest_asyncio.fixture
async def magnus_rested(gm_client, roster):
    """Long-rest Magnus so Sign of Ill Omen use is fresh."""
    magnus = roster["Magnus Hexbinder"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    return magnus


async def test_sign_of_ill_omen_happy_path(
    gm_client, magnus_rested,
):
    """Magnus casts Bestow Curse via Sign of Ill Omen → 200;
    caster gets the bestow-curse concentration anchor. Magnus
    has L3 Pact Magic slots natively — no slot patching needed.
    """
    magnus = magnus_rested
    mg_tok = f"tok_sio_mg_{magnus['id']}"
    await _seed_battle(gm_client, [
        _mkc(mg_tok, magnus["id"], name=magnus["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bestow_curse",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "sign-of-ill-omen",
            "slot_level": 3,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["concentration"] is True
    assert data["range_ft"] == 5
    assert data["via_invocation"] == "sign-of-ill-omen"
    mg_keys = await _get_buff_keys(gm_client, magnus["id"])
    assert "concentration-bestow-curse" in mg_keys


async def test_warlock_without_via_invocation_409(
    gm_client, magnus_rested,
):
    """class_slug=warlock without via_invocation → 409
    missing_invocation (Bestow Curse isn't a Warlock spell).
    """
    magnus = magnus_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bestow_curse",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "slot_level": 3,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"
    assert data.get("invocation") == "sign-of-ill-omen"


async def test_warlock_wrong_invocation_409(
    gm_client, magnus_rested,
):
    """class_slug=warlock + via_invocation="mire-the-mind" → 409
    missing_invocation. The registry rejects because Mire the
    Mind's spell_slug is "slow", not "bestow-curse".
    """
    magnus = magnus_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bestow_curse",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "mire-the-mind",
            "slot_level": 3,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"


async def test_sign_of_ill_omen_second_cast_409(
    gm_client, magnus_rested,
):
    """Two consecutive Sign of Ill Omen casts (no rest) →
    second is 409 not_enough_uses (1/long-rest gate).
    """
    magnus = magnus_rested
    mg_tok = f"tok_sio_2x_mg_{magnus['id']}"
    await _seed_battle(gm_client, [
        _mkc(mg_tok, magnus["id"], name=magnus["name"]),
    ])
    cast1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bestow_curse",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "sign-of-ill-omen",
            "slot_level": 3,
            "override": True,
        },
    )
    assert cast1.status_code == 200, cast1.text
    # Second cast — same long rest, should 409 not_enough_uses.
    cast2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bestow_curse",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "sign-of-ill-omen",
            "slot_level": 3,
            "override": True,
        },
    )
    assert cast2.status_code == 409, cast2.text
    data = cast2.json()
    assert data.get("error") == "not_enough_uses"
    assert data.get("resource_key") == "sign-of-ill-omen-uses"


async def test_cast_bestow_curse_l2_slot_400(gm_client, magnus_rested):
    """slot_level=2 → 400 (Bestow Curse is L3)."""
    magnus = magnus_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bestow_curse",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "sign-of-ill-omen",
            "slot_level": 2,
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_cast_bestow_curse_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bestow_curse",
        json={"class_slug": "warlock"},
    )
    assert resp.status_code == 400, resp.text
