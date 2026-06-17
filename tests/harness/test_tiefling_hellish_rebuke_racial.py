"""v2.395.0 — Tiefling Infernal Legacy racial Hellish Rebuke
(race-features plan Phase 1).

RAW PHB p.43 — Tiefling Infernal Legacy: "Once you reach 3rd level,
you can cast the hellish rebuke spell as a 2nd-level spell once with
this trait and regain the ability to do so when you finish a long
rest." The racial cast is FREE (no spell slot) and runs in parallel
with the v2.71.0 slot-based Hellish Rebuke reaction — a Tiefling Lv
3+ with both slots + the racial use available sees BOTH options on
the damage_taken reaction prompt:
  - "🔥 Cast Hellish Rebuke (L1: 2d10 fire ...)" — slot path
  - "🔥 Cast Hellish Rebuke (racial 1/long) (L2: 3d10 fire ...)" —
    racial path

Picking the racial path consumes the `hellish-rebuke` resource (not
a spell slot), broadcasts resource_update + feature_used with
source="hellish-rebuke-racial", and marks the reaction economy.
Once the racial resource hits 0 the option disappears from future
prompts; the slot-based option remains while slots last.

Test strategy (2 tests):

1. Happy path — Zara (Tiefling Sorcerer Lv 5, hellish-rebuke racial
   current=1) takes damage; the prompt offers BOTH options. POST
   /use_reaction with cast-hellish-rebuke-racial. Assert:
     - resource_update fires for key="hellish-rebuke" with current=0
     - feature_used fires with source="hellish-rebuke-racial"
     - NO spell_slot_update fires
     - economy_update flips reaction → True

2. Exhausted-resource control — Zara at racial current=0 takes
   damage. Assert: the cast-hellish-rebuke-racial option is NOT in
   the prompt (the existing slot-based cast-hellish-rebuke is still
   offered — slots untouched).
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _make_combatant(name, char_id, init=10, hp=40):
    return {
        "id": f"tok_til_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": [],
        "economy": {
            "action": False, "bonus": False,
            "reaction": False, "movement": 0,
        },
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants,
            "turn_index": 0,
            "round": 1,
            "active": True,
        },
    )


async def _patch_racial_current(gm_client, char_id: int, current: int) -> None:
    """PATCH the `hellish-rebuke` resource's `current` field on the
    sheet via sheet-fields. Used to set up the exhausted-resource
    control test without needing to long-rest -> cast first."""
    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = (snap.json() or {}).get("sheet") or {}
    resources = list(sheet.get("resources") or [])
    for i, r in enumerate(resources):
        if isinstance(r, dict) and (r.get("key") or "").lower() == "hellish-rebuke":
            updated = dict(r)
            updated["current"] = int(current)
            resources[i] = updated
            break
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"resources": resources},
    )


@pytest_asyncio.fixture
async def zara_rested(gm_client, roster):
    zara = roster["Zara Emberfire"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "long"},
    )
    return zara


@pytest_asyncio.fixture
async def krieger_rested(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    return krieger


async def _land_hit_and_get_prompt(gm_client, gm_ws, attacker, target_cid, target_char_id):
    """Drive attacker swings until a hit lands; return the most
    recent damage_taken reaction_prompt for target_char_id. Helper
    consolidates the Krieger-swings-until-hit loop reused across both
    tests."""
    for _ in range(40):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": attacker["id"],
                "attack_index": 0,
                "target_combatant_id": target_cid,
                "override": True,
                "override_range": True,
            },
        )
        if resp.status_code != 200:
            continue
        if resp.json().get("hit"):
            break
    else:
        raise AssertionError("no hit landed in 40 swings")
    await asyncio.sleep(0.25)
    prompts = [
        m for m in gm_ws.buffered("reaction_prompt")
        if (m.get("data") or {}).get("watcher_char_id") == target_char_id
        and (m.get("data") or {}).get("trigger_event") == "damage_taken"
    ]
    assert prompts, (
        f"expected damage_taken reaction_prompt for char_id={target_char_id}; "
        f"buffered events: "
        f"{[(m.get('data') or {}).get('trigger_event') for m in gm_ws.buffered('reaction_prompt')]}"
    )
    return prompts[-1]


async def test_tiefling_racial_hellish_rebuke_consumes_resource_not_slot(
    gm_client, gm_ws, zara_rested, krieger_rested,
):
    """Zara (Tiefling Sorcerer Lv 5, racial Hellish Rebuke current=1)
    takes damage. The prompt offers both the slot-based cast and the
    racial cast. Picking the racial decrements the `hellish-rebuke`
    resource to 0, fires feature_used(source=hellish-rebuke-racial),
    does NOT fire spell_slot_update, and flips Zara's reaction."""
    zara = zara_rested
    krieger = krieger_rested
    zara_cid = f"tok_til_{zara['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": zara_cid,
            "char_id": zara["id"],
            "name": zara["name"],
            "initiative": 10,
            "hp_current": 37, "hp_max": 37,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    prompt = await _land_hit_and_get_prompt(
        gm_client, gm_ws, krieger, zara_cid, zara["id"],
    )
    keys = [o.get("key") for o in prompt["data"].get("options", [])]
    assert "cast-hellish-rebuke-racial" in keys, (
        f"expected racial Hellish Rebuke option for Tiefling Lv 5; got {keys}"
    )
    # Both the slot-based and racial paths should be offered when
    # both are available — Zara has Sorcerer L1 slots + the racial.
    assert "cast-hellish-rebuke" in keys, (
        f"expected slot-based Hellish Rebuke option to remain alongside the "
        f"racial path; got {keys}"
    )
    prompt_id = prompt["data"]["prompt_id"]

    gm_ws.mark()
    cast = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reaction",
        json={
            "prompt_id": prompt_id,
            "reaction_key": "cast-hellish-rebuke-racial",
            "watcher_char_id": zara["id"],
        },
    )
    assert cast.status_code == 200, cast.text

    await asyncio.sleep(0.25)

    # resource_update: hellish-rebuke current decremented to 0.
    res_msgs = [
        m for m in gm_ws.buffered("resource_update")
        if (m.get("data") or {}).get("character_id") == zara["id"]
        and (m.get("data") or {}).get("key") == "hellish-rebuke"
    ]
    assert res_msgs, (
        f"expected resource_update for hellish-rebuke; "
        f"buffered keys: "
        f"{[(m.get('data') or {}).get('key') for m in gm_ws.buffered('resource_update')]}"
    )
    assert int(res_msgs[-1]["data"]["current"]) == 0, (
        f"expected hellish-rebuke current=0 after racial cast; got "
        f"{res_msgs[-1]['data']}"
    )

    # feature_used: source="hellish-rebuke-racial".
    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "hellish-rebuke-racial"
        and (m.get("data") or {}).get("character_id") == zara["id"]
    ]
    assert fu, (
        f"expected feature_used(source=hellish-rebuke-racial); buffered: "
        f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
    )
    assert fu[-1]["data"]["damage_type"] == "fire"
    assert fu[-1]["data"]["damage_expr"] == "3d10"
    assert fu[-1]["data"]["reaction_kind"] == "race-feature"

    # NO spell_slot_update fires for the racial path — slots stay intact.
    slot_msgs = [
        m for m in gm_ws.buffered("spell_slot_update")
        if (m.get("data") or {}).get("character_id") == zara["id"]
    ]
    assert not slot_msgs, (
        f"racial Hellish Rebuke must NOT consume a spell slot; got "
        f"spell_slot_update events: {[m.get('data') for m in slot_msgs]}"
    )

    # economy_update: reaction flipped.
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == zara["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, "expected economy_update for Zara's reaction"
    assert econ[-1]["data"]["used"] is True


async def test_tiefling_racial_hellish_rebuke_unavailable_at_zero(
    gm_client, gm_ws, zara_rested, krieger_rested,
):
    """Control: Zara at racial Hellish Rebuke current=0 takes damage.
    The cast-hellish-rebuke-racial option must NOT appear in the
    prompt (resource exhausted). The slot-based cast-hellish-rebuke
    remains because Zara still has spell slots."""
    zara = zara_rested
    krieger = krieger_rested
    # Drain Zara's racial Hellish Rebuke use via sheet-fields PATCH.
    await _patch_racial_current(gm_client, zara["id"], 0)

    zara_cid = f"tok_til_{zara['id']}"
    await _seed_battle(gm_client, [
        _make_combatant(krieger["name"], krieger["id"], init=12, hp=75),
        {
            "id": zara_cid,
            "char_id": zara["id"],
            "name": zara["name"],
            "initiative": 10,
            "hp_current": 37, "hp_max": 37,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])
    await asyncio.sleep(0.15)
    gm_ws.mark()

    prompt = await _land_hit_and_get_prompt(
        gm_client, gm_ws, krieger, zara_cid, zara["id"],
    )
    keys = [o.get("key") for o in prompt["data"].get("options", [])]
    assert "cast-hellish-rebuke-racial" not in keys, (
        f"racial Hellish Rebuke option must NOT appear when resource "
        f"is exhausted (current=0); got {keys}"
    )
    # Slot-based path stays — Zara still has L1+ slots.
    assert "cast-hellish-rebuke" in keys, (
        f"slot-based Hellish Rebuke must still appear when resource "
        f"is exhausted but slots remain; got {keys}"
    )

    # Restore for any downstream tests in the same suite.
    await _patch_racial_current(gm_client, zara["id"], 1)
