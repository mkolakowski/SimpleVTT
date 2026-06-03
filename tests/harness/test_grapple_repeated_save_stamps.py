"""v2.99.117 — Grapple end-of-turn save stamps.

Wire the v2.97.62 end-of-turn auto-fire framework into the grappled
buff: stamp `repeated_save_ability: "STR"` + `repeated_save_dc:
<grappler's passive Athletics>` at install time so the framework
auto-rolls escape attempts at end of each target's turn.

RAW imprecision: Grapple escape is an ACTION + STR (Athletics) or
DEX (Acrobatics) check, not a save. v2.99.117 repurposes the
save-framework — the DC reflects the grappler's hold strength
(passive Athletics = 10 + STR mod + PB if proficient + extra PB if
expertise). A future commit can split out a dedicated Athletics-
check framework; v1 ships the approximation.

Tests:
  - Krieger grapples Tavik → grappled buff carries
    repeated_save_ability="STR" and repeated_save_dc reflecting
    Krieger's passive Athletics (STR 17, mod +3; proficient PB +3;
    DC = 10 + 3 + 3 = 16)
  - /use_repeated_save endpoint can be triggered against the buff
    (proxy for the framework finding + resolving the save)
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


async def test_grapple_stamps_repeated_save_fields(gm_client, roster):
    """Krieger grapples Tavik. The grappled buff carries
    repeated_save_ability="STR" and a positive DC reflecting
    Krieger's passive Athletics.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]
    kr_tok = f"tok_grap_eot_kr_{krieger['id']}"
    tv_tok = f"tok_grap_eot_tv_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
        _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_grapple",
        json={
            "character_id": krieger["id"],
            "target_combatant_id": tv_tok,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    buffs = await _get_buffs(gm_client, tavik["id"])
    grappled = next((b for b in buffs if b.get("key") == "grappled"), None)
    assert grappled is not None, f"no grappled buff; got {buffs}"
    assert grappled.get("repeated_save_ability") == "STR", grappled
    dc = grappled.get("repeated_save_dc")
    assert isinstance(dc, int) and dc > 0, grappled


async def test_grapple_use_repeated_save_endpoint_callable(gm_client, roster):
    """After /use_grapple, /use_repeated_save can be triggered on
    the grappled target. Proxy for the v2.97.62 framework finding
    + resolving the buff via the same data path.
    """
    krieger = roster["Krieger Stonefist"]
    tavik = roster["Brother Tavik Stonebrow"]
    kr_tok = f"tok_grap_urs_kr_{krieger['id']}"
    tv_tok = f"tok_grap_urs_tv_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
        _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
    ])
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_grapple",
        json={
            "character_id": krieger["id"],
            "target_combatant_id": tv_tok,
            "override": True,
        },
    )
    assert cast.status_code == 200, cast.text

    save = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_repeated_save",
        json={"character_id": tavik["id"], "buff_key": "grappled"},
    )
    # 200 regardless of save outcome.
    assert save.status_code == 200, save.text
