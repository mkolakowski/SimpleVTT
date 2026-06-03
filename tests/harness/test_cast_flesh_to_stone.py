"""v2.99.130 — /cast_flesh_to_stone endpoint tests.

L6 Transmutation, concentration up to 1 minute, CON save. Wizard /
Sorcerer. v1 ships a `stage` body flag for the install:
  - "restrained" → install Restrained buff (Flesh to Stone stage 1)
  - "petrified"  → install Petrified buff (skips the 3-strikes
    progression; GM has resolved the staged transition manually)

3-strikes save tracking is filed; the v2.97.62 framework's
end-of-turn save fires the repeated CON save automatically (the
buff carries the install-time stamps) but the strike-counter
transition between Restrained and Petrified needs a separate hook.

Thalindra has Flesh to Stone descriptively at Lv 7 (no L6 slot
stock); fixture PATCHes a L6 slot in for tests.

Tests:
  - happy path stage=restrained → Restrained buff installs
  - happy path stage=petrified → Petrified buff installs
  - wrong class (cleric) → 400
  - L5 slot → 400
  - bad stage → 400
  - missing target → 404 target_not_found
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


async def _get_buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return {(b or {}).get("key") for b in resp.json().get("buffs") or []}


async def test_cast_flesh_to_stone_restrained_stage(
    gm_client, thalindra_with_l6_slot, roster,
):
    """stage=restrained → restrained buff installs on Krieger;
    Thalindra gets the concentration anchor.
    """
    thalindra = thalindra_with_l6_slot
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_fts_r_th_{thalindra['id']}"
    kr_tok = f"tok_fts_r_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"]),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_flesh_to_stone",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 6,
            "target_combatant_id": kr_tok,
            "stage": "restrained",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["stage"] == "restrained"
    assert data["installed"] is True
    assert data["concentration"] is True
    # Krieger has Restrained.
    krieger_keys = await _get_buff_keys(gm_client, krieger["id"])
    assert "restrained" in krieger_keys
    # Thalindra has the concentration anchor.
    th_keys = await _get_buff_keys(gm_client, thalindra["id"])
    assert "concentration-flesh-to-stone" in th_keys


async def test_cast_flesh_to_stone_petrified_stage(
    gm_client, thalindra_with_l6_slot, roster,
):
    """stage=petrified → petrified buff installs (GM resolved 3
    fails externally).
    """
    thalindra = thalindra_with_l6_slot
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_fts_p_th_{thalindra['id']}"
    kr_tok = f"tok_fts_p_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"]),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    resp = await gm_client.post(
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
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["stage"] == "petrified"
    assert data["installed"] is True
    krieger_keys = await _get_buff_keys(gm_client, krieger["id"])
    assert "petrified" in krieger_keys


async def test_cast_flesh_to_stone_wrong_class_400(
    gm_client, thalindra_with_l6_slot,
):
    """class_slug="cleric" → 400 (Wizard/Sorcerer only)."""
    thalindra = thalindra_with_l6_slot
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_flesh_to_stone",
        json={
            "character_id": thalindra["id"],
            "class_slug": "cleric",
            "slot_level": 6,
            "target_combatant_id": "x",
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_cast_flesh_to_stone_l5_slot_400(
    gm_client, thalindra_with_l6_slot,
):
    """slot_level=5 → 400 (Flesh to Stone is L6)."""
    thalindra = thalindra_with_l6_slot
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_flesh_to_stone",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 5,
            "target_combatant_id": "x",
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_cast_flesh_to_stone_bad_stage_400(
    gm_client, thalindra_with_l6_slot,
):
    """stage="banished" → 400 (must be restrained or petrified)."""
    thalindra = thalindra_with_l6_slot
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_flesh_to_stone",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 6,
            "target_combatant_id": "x",
            "stage": "banished",
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_cast_flesh_to_stone_missing_target_404(
    gm_client, thalindra_with_l6_slot,
):
    """target_combatant_id refers to a non-existent combatant →
    404 target_not_found.
    """
    thalindra = thalindra_with_l6_slot
    # Seed battle with only Thalindra; the bogus target ID won't
    # resolve.
    await _seed_battle(gm_client, [
        _mkc(f"tok_fts_404_th_{thalindra['id']}", thalindra["id"],
             name=thalindra["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_flesh_to_stone",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 6,
            "target_combatant_id": "bogus_target_id",
            "override": True,
        },
    )
    assert resp.status_code == 404, resp.text
    data = resp.json()
    assert data.get("error") == "target_not_found"
