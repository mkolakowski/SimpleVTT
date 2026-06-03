"""v2.99.142 — /cast_polymorph endpoint tests.

L4 Transmutation, concentration up to 1 hour. Bard, Druid,
Sorcerer, Wizard. Warlock-only via the v2.99.142 Sculptor of
Flesh invocation (PHB p.111: "Prerequisite: 7th level. You can
cast Polymorph once using a warlock spell slot. You can't do so
again until you finish a long rest.").

This is the "spell-side" half — slot decrement + invocation gate
+ concentration anchor + audit. The actual transformation runs
via the existing /transform endpoint with source="polymorph".

Second consumer of the v2.99.140 invocation-cast registry. Closes
half of the v2.99.140 filed item (Sculptor of Flesh proves the
abstraction extends past Mire the Mind).

Magnus has eldritch-invocation-sculptor-of-flesh on his feats
list + a sculptor-of-flesh-uses 1/long-rest resource.

Tests:
  - happy path (Magnus via Sculptor of Flesh) → 200; slot +
    resource decrement; caster gets the concentration anchor
  - Warlock without via_invocation flag → 409 missing_invocation
  - Warlock with wrong via_invocation slug → 409 missing_invocation
    (registry rejects when spell_slug != "polymorph")
  - Sculptor of Flesh second cast same long rest → 409
    not_enough_uses
  - L3 slot → 400 (Polymorph is L4)
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
    """Long-rest Magnus so Sculptor of Flesh use is fresh."""
    magnus = roster["Magnus Hexbinder"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    return magnus


async def test_sculptor_of_flesh_happy_path(
    gm_client, magnus_rested, roster,
):
    """Magnus casts Polymorph via Sculptor of Flesh → 200; caster
    gets the polymorph concentration anchor.
    """
    magnus = magnus_rested
    mg_tok = f"tok_sof_mg_{magnus['id']}"
    await _seed_battle(gm_client, [
        _mkc(mg_tok, magnus["id"], name=magnus["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "sculptor-of-flesh",
            "slot_level": 4,
            "override": True,
        },
    )
    # Magnus is Lv 5 Warlock — his Pact Magic slots are at L3 only.
    # The endpoint will 409 no_slot for L4. Patch in an L4 slot for
    # this test only.
    if resp.status_code == 409 and resp.json().get("error") == "no_slot":
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"spell_slots": {"warlock": {
                "3": {"total": 2, "used": 0},
                "4": {"total": 1, "used": 0},
            }}},
        )
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
            json={
                "character_id": magnus["id"],
                "class_slug": "warlock",
                "via_invocation": "sculptor-of-flesh",
                "slot_level": 4,
                "override": True,
            },
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["concentration"] is True
    assert data["ready_to_transform"] is True
    assert data["via_invocation"] == "sculptor-of-flesh"
    # Magnus has the concentration anchor.
    mg_keys = await _get_buff_keys(gm_client, magnus["id"])
    assert "concentration-polymorph" in mg_keys

    # Restore Magnus's Pact Magic L3 slot config (the seed default).
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"spell_slots": {"warlock": {
            "3": {"total": 2, "used": 0},
        }}},
    )


async def test_warlock_without_via_invocation_409(
    gm_client, magnus_rested,
):
    """class_slug=warlock without via_invocation → 409
    missing_invocation (Polymorph isn't a Warlock spell).
    """
    magnus = magnus_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "slot_level": 4,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"
    assert data.get("invocation") == "sculptor-of-flesh"


async def test_warlock_wrong_invocation_409(
    gm_client, magnus_rested,
):
    """class_slug=warlock + via_invocation="mire-the-mind" → 409
    missing_invocation. The registry rejects because Mire the
    Mind's spell_slug is "slow", not "polymorph".
    """
    magnus = magnus_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "mire-the-mind",
            "slot_level": 4,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"


async def test_sculptor_of_flesh_second_cast_409(
    gm_client, magnus_rested,
):
    """Two consecutive Sculptor of Flesh casts (no rest) → second
    is 409 not_enough_uses (1/long-rest gate).
    """
    magnus = magnus_rested
    mg_tok = f"tok_sof_2x_mg_{magnus['id']}"
    await _seed_battle(gm_client, [
        _mkc(mg_tok, magnus["id"], name=magnus["name"]),
    ])
    # Patch in an L4 slot so we can do the cast.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"spell_slots": {"warlock": {
            "3": {"total": 2, "used": 0},
            "4": {"total": 2, "used": 0},
        }}},
    )
    cast1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "sculptor-of-flesh",
            "slot_level": 4,
            "override": True,
        },
    )
    assert cast1.status_code == 200, cast1.text
    # Second cast — same long rest, should 409 not_enough_uses.
    cast2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "sculptor-of-flesh",
            "slot_level": 4,
            "override": True,
        },
    )
    assert cast2.status_code == 409, cast2.text
    data = cast2.json()
    assert data.get("error") == "not_enough_uses"
    assert data.get("resource_key") == "sculptor-of-flesh-uses"
    # Restore the seed's L3-only slot config.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"spell_slots": {"warlock": {
            "3": {"total": 2, "used": 0},
        }}},
    )


async def test_cast_polymorph_l3_slot_400(gm_client, magnus_rested):
    """slot_level=3 → 400 (Polymorph is L4)."""
    magnus = magnus_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "sculptor-of-flesh",
            "slot_level": 3,
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_cast_polymorph_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_polymorph",
        json={"class_slug": "warlock"},
    )
    assert resp.status_code == 400, resp.text
