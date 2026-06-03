"""v2.99.120 — Web spell repeated-save stamps.

Wire the v2.97.62 end-of-turn auto-fire framework into the
restrained buff installed by /cast_web. RAW Web: "A creature
restrained by the webs can use its action to make a Strength
check against your spell save DC. If it succeeds, it is no
longer restrained." v2.99.120 stamps the install-time fields so
the framework auto-rolls the STR break-free at end of each turn.

v1 imprecision (carried over from v2.99.117 Grapple): the save
framework rolls a STR save (STR + STR-save proficiency), not a
STR check (STR + Athletics proficiency). A future Athletics-check
framework will close the gap.

Tests:
  - Thalindra casts Web on Krieger → restrained buff carries
    repeated_save_ability="STR" + repeated_save_dc > 0
  - /use_repeated_save endpoint can be triggered against the buff
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
    assert resp.status_code == 200, resp.text
    return resp.json().get("buffs") or []


async def test_web_stamps_repeated_save_fields(gm_client, roster):
    """Thalindra casts Web on Krieger → restrained buff carries
    STR + DC > 0.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_web_eot_th_{thalindra['id']}"
    kr_tok = f"tok_web_eot_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"], speed_walk=30),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_web",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 2,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    buffs = await _get_buffs(gm_client, krieger["id"])
    restrained = next((b for b in buffs if b.get("key") == "restrained"), None)
    assert restrained is not None, f"no restrained buff; got {buffs}"
    assert restrained.get("repeated_save_ability") == "STR", restrained
    dc = restrained.get("repeated_save_dc")
    assert isinstance(dc, int) and dc > 0, restrained


async def test_web_use_repeated_save_endpoint_callable(gm_client, roster):
    """After /cast_web, /use_repeated_save can be triggered on the
    restrained target against the `restrained` key.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_web_urs_th_{thalindra['id']}"
    kr_tok = f"tok_web_urs_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"], speed_walk=30),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_web",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 2,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text

    save = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_repeated_save",
        json={"character_id": krieger["id"], "buff_key": "restrained"},
    )
    # 200 regardless of save outcome — endpoint just needs to be
    # callable.
    assert save.status_code == 200, save.text
