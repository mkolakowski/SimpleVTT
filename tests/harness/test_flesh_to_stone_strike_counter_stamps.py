"""v2.99.135 — Flesh to Stone strike-counter install-time stamps.

v2.99.130 shipped /cast_flesh_to_stone with a `stage` body flag
(restrained | petrified). The full RAW 3-strikes flow (3 CON save
successes end the spell; 3 fails Petrify) was filed because the
engine wiring needed for auto-transitions is non-trivial.

v2.99.135 closes one half of that filing: it stamps the strike-
counter fields on the Restrained buff at install time so the GM
UI can render the running counter, and so the engine wiring (still
filed) reads from a known data shape. The actual auto-transition
(3 successes → drop spell; 3 fails → install Petrified) is filed
as the engine ship.

Stamps added on the FtS Restrained buff:
  - strike_counter: True (marker — turns the buff into a counter-
    aware one for the v2.97.62 framework)
  - success_count: 0 (CON saves passed so far)
  - failure_count: 0 (CON saves failed so far)
  - strike_threshold: 3 (RAW: 3 of either ends/transitions)

This test casts Flesh to Stone stage="restrained" on Krieger and
verifies the Restrained buff carries all four stamps.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", speed_walk=30):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 75, "hp_max": 75,
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
    thalindra = roster["Thalindra Moonwhisper"]
    stock_slots = {
        "1": {"total": 4, "used": 0},
        "2": {"total": 3, "used": 0},
        "3": {"total": 3, "used": 0},
        "4": {"total": 1, "used": 0},
    }
    test_slots = dict(stock_slots, **{"6": {"total": 1, "used": 0}})
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"spell_slots": {"wizard": test_slots}},
    )
    yield thalindra
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={"spell_slots": {"wizard": stock_slots}},
    )


async def test_flesh_to_stone_restrained_carries_strike_counter_stamps(
    gm_client, thalindra_with_l6_slot, roster,
):
    """Cast Flesh to Stone stage=restrained on Krieger. Verify the
    Restrained buff on Krieger carries all four strike-counter
    fields with their initial values.
    """
    thalindra = thalindra_with_l6_slot
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_fts_sc_th_{thalindra['id']}"
    kr_tok = f"tok_fts_sc_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"]),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    cast_resp = await gm_client.post(
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
    assert cast_resp.status_code == 200, cast_resp.text
    # Read Krieger's buffs and find the restrained one.
    buffs_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs",
    )
    assert buffs_resp.status_code == 200, buffs_resp.text
    buffs = buffs_resp.json().get("buffs") or []
    restrained = next(
        (b for b in buffs if b.get("key") == "restrained"
         and b.get("source") == "flesh-to-stone-spell"),
        None,
    )
    assert restrained is not None, (
        f"no Flesh to Stone Restrained buff; got buffs={buffs}"
    )
    # All four strike-counter stamps with initial values.
    assert restrained.get("strike_counter") is True, restrained
    assert restrained.get("success_count") == 0, restrained
    assert restrained.get("failure_count") == 0, restrained
    assert restrained.get("strike_threshold") == 3, restrained


async def test_flesh_to_stone_petrified_skips_strike_counter_stamps(
    gm_client, thalindra_with_l6_slot, roster,
):
    """stage=petrified installs the Petrified buff directly,
    bypassing the staged Restrained progression. The Petrified buff
    should NOT carry strike-counter stamps (they're a Restrained-
    stage concept).
    """
    thalindra = thalindra_with_l6_slot
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_fts_sc_p_th_{thalindra['id']}"
    kr_tok = f"tok_fts_sc_p_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"]),
        _mkc(kr_tok, krieger["id"], name=krieger["name"], speed_walk=40),
    ])
    cast_resp = await gm_client.post(
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
    assert cast_resp.status_code == 200, cast_resp.text
    buffs_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs",
    )
    buffs = buffs_resp.json().get("buffs") or []
    petrified = next(
        (b for b in buffs if b.get("key") == "petrified"),
        None,
    )
    assert petrified is not None, buffs
    # Stamps are Restrained-only.
    assert petrified.get("strike_counter") is None, petrified
    assert petrified.get("success_count") is None, petrified
    assert petrified.get("failure_count") is None, petrified
