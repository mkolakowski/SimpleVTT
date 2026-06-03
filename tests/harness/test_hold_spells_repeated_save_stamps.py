"""v2.99.110 — Hold Person + Hold Monster install-time stamps for
the v2.97.62 end-of-turn auto-fire framework.

Pre-v2.99.110 the Paralyzed buff carried no `repeated_save_*`
fields — the v2.97.62 / v2.97.69 framework that auto-fires end-of-
turn saves on the previous combatant walks the buffs and looks for
`repeated_save_ability` + `repeated_save_dc`. Without those
stamps Hold Person targets stayed Paralyzed forever.

v2.99.110 adds `_compute_spell_save_dc_from_sheet(sheet)` + the
DC plumb-through to `_make_hold_person_paralyzed_buff` and
`_make_hold_monster_paralyzed_buff`. The Paralyzed factory now
stamps `repeated_save_ability: "WIS"` + `repeated_save_dc: <dc>`
on the buff whenever both are supplied (when not, the helper
silently omits them — Sleep / Banishment opt-out).

Tests:
  - Hold Person installs a buff carrying repeated_save_ability=WIS
    and repeated_save_dc>0
  - Hold Monster same shape
  - The /use_repeated_save endpoint can be triggered on the
    paralyzed target (proxy for "the v2.97.62 auto-fire would
    find this buff at end-of-turn")
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


async def test_hold_person_stamps_repeated_save_fields(gm_client, roster):
    """Tavik casts Hold Person on Krieger. The paralyzed buff on
    Krieger carries repeated_save_ability=WIS and a positive DC.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    krieger = roster["Krieger Stonefist"]
    tv_tok = f"tok_hp_eot_tv_{tavik['id']}"
    kr_tok = f"tok_hp_eot_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": tavik["id"],
            "class_slug": "cleric",
            "slot_level": 2,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    buffs = await _get_buffs(gm_client, krieger["id"])
    paralyzed = next((b for b in buffs if b.get("key") == "paralyzed"), None)
    assert paralyzed is not None, f"no paralyzed buff; got {buffs}"
    assert paralyzed.get("repeated_save_ability") == "WIS", paralyzed
    dc = paralyzed.get("repeated_save_dc")
    assert isinstance(dc, int) and dc > 0, paralyzed


async def test_hold_monster_stamps_repeated_save_fields(gm_client, roster):
    """Thalindra casts Hold Monster on Krieger. Same shape — WIS save
    + positive DC on the paralyzed buff. Uses the v2.99.108 spell-
    slot PATCH fixture pattern inline.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    # PATCH a L5 slot in (Thalindra Lv 7 doesn't have one stock).
    stock_slots = {
        "1": {"total": 4, "used": 0},
        "2": {"total": 3, "used": 0},
        "3": {"total": 3, "used": 0},
        "4": {"total": 1, "used": 0},
    }
    test_slots = dict(stock_slots, **{"5": {"total": 1, "used": 0}})
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"spell_slots": {"wizard": test_slots}},
    )
    try:
        th_tok = f"tok_hm_eot_th_{thalindra['id']}"
        kr_tok = f"tok_hm_eot_kr_{krieger['id']}"
        await _seed_battle(gm_client, [
            _mkc(th_tok, thalindra["id"], name=thalindra["name"], speed_walk=30),
            _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_hold_monster",
            json={
                "character_id": thalindra["id"],
                "class_slug": "wizard",
                "slot_level": 5,
                "target_combatant_ids": [kr_tok],
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text

        buffs = await _get_buffs(gm_client, krieger["id"])
        paralyzed = next((b for b in buffs if b.get("key") == "paralyzed"), None)
        assert paralyzed is not None, f"no paralyzed buff; got {buffs}"
        assert paralyzed.get("repeated_save_ability") == "WIS", paralyzed
        dc = paralyzed.get("repeated_save_dc")
        assert isinstance(dc, int) and dc > 0, paralyzed
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
            json={"spell_slots": {"wizard": stock_slots}},
        )


async def test_hold_person_use_repeated_save_endpoint_callable(
    gm_client, roster,
):
    """End-to-end-ish: after casting Hold Person, the manual
    `/use_repeated_save` endpoint can be triggered on Krieger.
    Verifies the buff carries enough info for the framework to
    resolve a save (regardless of pass/fail outcome).
    """
    tavik = roster["Brother Tavik Stonebrow"]
    krieger = roster["Krieger Stonefist"]
    tv_tok = f"tok_hp_urs_tv_{tavik['id']}"
    kr_tok = f"tok_hp_urs_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(tv_tok, tavik["id"], name=tavik["name"], speed_walk=30),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    cast_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hold_person",
        json={
            "character_id": tavik["id"],
            "class_slug": "cleric",
            "slot_level": 2,
            "target_combatant_ids": [kr_tok],
            "override": True,
        },
    )
    assert cast_resp.status_code == 200, cast_resp.text

    save_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_repeated_save",
        json={
            "character_id": krieger["id"],
            "buff_key": "paralyzed",
        },
    )
    # 200 regardless of save outcome — endpoint just needs to be
    # callable + the buff needs to be resolvable.
    assert save_resp.status_code == 200, save_resp.text
