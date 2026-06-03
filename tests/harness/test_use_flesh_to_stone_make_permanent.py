"""v2.99.139 — /use_flesh_to_stone_make_permanent endpoint tests.

Closes the v2.99.136 filed item. RAW (PHB p.243): if the caster
maintains concentration on Flesh to Stone for the full minute, the
target's petrification becomes permanent. This endpoint is the
GM-callable trigger: flips the Petrified buff from
concentration-bonded to permanent and drops the caster's
concentration anchor.

Tests:
  - happy path: cast FtS petrified → make_permanent → buff dropped
    concentration, has permanent flag + extended duration, caster's
    anchor is gone
  - missing buff (target has no FtS Petrified) → 409
    no_flesh_to_stone_petrified
  - missing target_combatant_id → 400
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


async def _get_buffs(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return resp.json().get("buffs") or []


@pytest_asyncio.fixture
async def thalindra_with_l6_slot(gm_client, roster):
    """PATCH a L6 spell slot for Thalindra (Lv 7 Wizard stock has
    L1-L4 only). Restore stock on teardown.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    stock_slots = {
        "1": {"total": 4, "used": 0},
        "2": {"total": 3, "used": 0},
        "3": {"total": 3, "used": 0},
        "4": {"total": 1, "used": 0},
    }
    test_slots = dict(stock_slots, **{
        "6": {"total": 1, "used": 0},
    })
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"spell_slots": {"wizard": test_slots}},
    )
    yield thalindra
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"spell_slots": {"wizard": stock_slots}},
    )


async def test_make_permanent_happy_path(
    gm_client, thalindra_with_l6_slot, roster,
):
    """Cast FtS at stage=petrified, then make_permanent. The Petrified
    buff loses its concentration flag and gains the permanent flag;
    the caster's concentration-flesh-to-stone anchor is removed.
    """
    thalindra = thalindra_with_l6_slot
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_ftsmp_th_{thalindra['id']}"
    kr_tok = f"tok_ftsmp_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"]),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    # Cast Flesh to Stone Petrified stage.
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_flesh_to_stone",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 6,
            "target_combatant_id": kr_tok,
            "stage": "petrified",
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text

    # Sanity: Krieger has a concentration-bonded Petrified buff,
    # Thalindra has the anchor.
    pre_kr = await _get_buffs(gm_client, krieger["id"])
    fts_pre = next(
        (b for b in pre_kr if b.get("key") == "petrified"
         and b.get("source") == "flesh-to-stone-spell"),
        None,
    )
    assert fts_pre is not None
    assert fts_pre.get("concentration") is True
    assert fts_pre.get("permanent") is not True
    pre_th = await _get_buffs(gm_client, thalindra["id"])
    pre_th_keys = {b.get("key") for b in pre_th}
    assert "concentration-flesh-to-stone" in pre_th_keys

    # Make it permanent.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_flesh_to_stone_make_permanent",
        json={
            "character_id": thalindra["id"],
            "target_combatant_id": kr_tok,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["permanent"] is True
    assert data["concentration"] is False
    assert data["target_combatant_id"] == kr_tok

    # Post-mutation: Krieger's Petrified buff is no longer
    # concentration-bonded, has permanent flag, and has a very large
    # duration.
    post_kr = await _get_buffs(gm_client, krieger["id"])
    fts_post = next(
        (b for b in post_kr if b.get("key") == "petrified"
         and b.get("source") == "flesh-to-stone-spell"),
        None,
    )
    assert fts_post is not None
    assert fts_post.get("concentration") is False
    assert fts_post.get("permanent") is True
    assert int(fts_post.get("duration_rounds") or 0) >= 1000
    assert int(fts_post.get("duration_max") or 0) >= 1000

    # Thalindra's concentration anchor is gone.
    post_th = await _get_buffs(gm_client, thalindra["id"])
    post_th_keys = {b.get("key") for b in post_th}
    assert "concentration-flesh-to-stone" not in post_th_keys


async def test_make_permanent_no_buff_409(
    gm_client, thalindra_with_l6_slot, roster,
):
    """Target has no FtS Petrified buff → 409 no_flesh_to_stone_petrified."""
    thalindra = thalindra_with_l6_slot
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_ftsmp_nb_th_{thalindra['id']}"
    kr_tok = f"tok_ftsmp_nb_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"]),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    # Skip the cast — target has no FtS Petrified buff.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_flesh_to_stone_make_permanent",
        json={
            "character_id": thalindra["id"],
            "target_combatant_id": kr_tok,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "no_flesh_to_stone_petrified"


async def test_make_permanent_missing_target_400(
    gm_client, thalindra_with_l6_slot,
):
    """Missing target_combatant_id → 400."""
    thalindra = thalindra_with_l6_slot
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_flesh_to_stone_make_permanent",
        json={"character_id": thalindra["id"]},
    )
    assert resp.status_code == 400, resp.text


async def test_make_permanent_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_flesh_to_stone_make_permanent",
        json={"target_combatant_id": "x"},
    )
    assert resp.status_code == 400, resp.text
