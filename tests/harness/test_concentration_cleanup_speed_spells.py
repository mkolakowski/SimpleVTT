"""v2.99.109 — caster-side concentration anchor cleanup tests for
the four speed-engine spells (Slow / Web / Hold Person / Hold
Monster).

Pre-v2.99.109 each `/cast_<spell>` endpoint installed only the
TARGET-side condition buff with `source_char_id: caster.id` and
`concentration: True`. When the caster's concentration ended
(via /end_buff or via casting a new concentration spell), nothing
cleared the target's buff because no anchor existed on the caster.

v2.99.109 adds `_install_caster_concentration_anchor` that installs
a `concentration-<spell_slug>` buff on the caster after each cast.
The existing v2.38.0 `_drop_paired_concentration_buffs` helper
matches buffs by `source_char_id == caster.id` + concentration,
so dropping the anchor (manually via /end_buff or automatically
via the v2.49.51 concentration-swap logic in `_install_buff`)
cascades to remove every target's spell buff in lock-step.

Tests:
  - cast Slow on Krieger; verify Krieger has the `restrained`?
    no — Slow installs a `slow` buff. Verify the slow buff is
    present.
  - end the caster's concentration anchor via /end_buff;
    verify Krieger's slow buff is gone.
  - same flow for Web / Hold Person / Hold Monster.
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


async def _get_combatant_buff_keys(gm_client, char_id):
    """Read the buffs list from /character/{id}/buffs and return
    the set of buff keys present.
    """
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert resp.status_code == 200, resp.text
    buffs = resp.json().get("buffs") or []
    return {(b or {}).get("key") for b in buffs}


async def test_slow_concentration_anchor_cleanup(gm_client, roster):
    """Thalindra casts Slow on Krieger. After /end_buff on the
    caster's anchor (`concentration-slow`), Krieger's `slow` buff
    is gone.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_cleanup_slow_th_{thalindra['id']}"
    kr_tok = f"tok_cleanup_slow_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"], speed_walk=30),
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

    # Verify caster has the anchor + Krieger has the slow buff.
    caster_keys = await _get_combatant_buff_keys(gm_client, thalindra["id"])
    assert "concentration-slow" in caster_keys, caster_keys
    krieger_keys = await _get_combatant_buff_keys(gm_client, krieger["id"])
    assert "slow" in krieger_keys, krieger_keys

    # End the caster's anchor.
    end_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": thalindra["id"], "key": "concentration-slow"},
    )
    assert end_resp.status_code == 200, end_resp.text

    # Krieger's slow buff is gone.
    krieger_after = await _get_combatant_buff_keys(gm_client, krieger["id"])
    assert "slow" not in krieger_after, (
        f"Slow buff should be cleared by caster-anchor cascade; "
        f"got {krieger_after}"
    )


async def test_web_concentration_anchor_cleanup(gm_client, roster):
    """Same flow for Web. Buff key is `restrained` (v2.99.106
    refactor); cleanup via the caster's `concentration-web` anchor.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_cleanup_web_th_{thalindra['id']}"
    kr_tok = f"tok_cleanup_web_kr_{krieger['id']}"
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

    caster_keys = await _get_combatant_buff_keys(gm_client, thalindra["id"])
    assert "concentration-web" in caster_keys, caster_keys
    krieger_keys = await _get_combatant_buff_keys(gm_client, krieger["id"])
    assert "restrained" in krieger_keys, krieger_keys

    end_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": thalindra["id"], "key": "concentration-web"},
    )
    assert end_resp.status_code == 200, end_resp.text

    krieger_after = await _get_combatant_buff_keys(gm_client, krieger["id"])
    assert "restrained" not in krieger_after, (
        f"Restrained (Web) should be cleared; got {krieger_after}"
    )


async def test_hold_person_concentration_anchor_cleanup(gm_client, roster):
    """Same flow for Hold Person. Target buff key is `paralyzed`."""
    tavik = roster["Brother Tavik Stonebrow"]
    krieger = roster["Krieger Stonefist"]
    tv_tok = f"tok_cleanup_hp_tv_{tavik['id']}"
    kr_tok = f"tok_cleanup_hp_kr_{krieger['id']}"
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

    caster_keys = await _get_combatant_buff_keys(gm_client, tavik["id"])
    assert "concentration-hold-person" in caster_keys, caster_keys
    krieger_keys = await _get_combatant_buff_keys(gm_client, krieger["id"])
    assert "paralyzed" in krieger_keys, krieger_keys

    end_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": tavik["id"], "key": "concentration-hold-person"},
    )
    assert end_resp.status_code == 200, end_resp.text

    krieger_after = await _get_combatant_buff_keys(gm_client, krieger["id"])
    assert "paralyzed" not in krieger_after, (
        f"Paralyzed (Hold Person) should be cleared; got {krieger_after}"
    )
