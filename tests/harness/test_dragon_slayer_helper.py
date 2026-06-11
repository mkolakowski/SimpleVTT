"""v2.158.96 — magic-items-automation Phase 5f: route Dragon Slayer's
condition predicate through the v2.97.48 ``_attacker_creature_type``
helper so the target's creature type can be resolved from the
character sheet (or token template) when the live combatant dict
doesn't carry it directly.

Before Phase 5f, the rider only fired when the synthetic combatant
in the battle PUT explicitly set ``creature_type: "dragon"``. After
Phase 5f, the helper falls back to:
  1. ``character.sheet["creature_type"]`` (PC) — exercised here
  2. ``token_template.sheet["type"]`` (NPC) — exercised by demo
     monsters once their templates get the field set

Test method: Tavik (a demo PC) doesn't normally carry a
``creature_type`` field. We PATCH his sheet to add
``creature_type: "dragon"``, then seed a battle with Tavik as the
target (no creature_type set on the combatant dict — the dispatch
must resolve it via the helper) and verify Caelan's Dragon Slayer
rider fires. Teardown clears the field.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


CAELAN_DRAGON_SLAYER_ATTACK_IDX = 2


def _uplifts(data, source):
    return [u for u in (data.get("auto_uplifts") or [])
            if u.get("source") == source]


def _mkc(cid, char_id=None, name="X", ac=1):
    """Combatant dict that DELIBERATELY omits creature_type so the
    server-side helper path is exercised."""
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 200, "hp_max": 200,
        "ac": ac,
        "buffs": [],
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def caelan(roster):
    return roster["Sir Caelan Lightbringer"]


@pytest_asyncio.fixture
async def tavik_as_dragon(gm_client, roster):
    """PATCH Tavik's sheet to mark him as a dragon via
    ``creature_type``; the v2.97.48 helper reads this field for PCs
    when the combatant dict doesn't carry one. Restores in teardown."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"creature_type": "dragon"},
    )
    assert r.status_code == 200, r.text
    yield tavik
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"creature_type": ""},
    )


async def test_dragon_slayer_fires_via_helper_resolution(
    gm_client, caelan, tavik_as_dragon,
):
    """v2.158.96: target combatant carries char_id but NO
    creature_type field. The server's helper resolves Tavik's
    sheet.creature_type = "dragon" → rider fires.

    Pre-Phase 5f this would have failed: the v2.158.93 condition
    lambda only read target_combatant.get("creature_type") which is
    empty here. Phase 5f's resolver shim injects the helper-resolved
    value onto a shallow copy before invoking the lambda."""
    tavik = tavik_as_dragon
    caelan_cid = f"tok_dsf1_caelan_{caelan['id']}"
    tavik_cid = f"tok_dsf1_tavik_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
        _mkc(tavik_cid, tavik["id"], name=tavik["name"]),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": caelan["id"],
            "attack_index": CAELAN_DRAGON_SLAYER_ATTACK_IDX,
            "target_combatant_id": tavik_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["attack_name"] == "Dragon Slayer Longsword"

    ups = _uplifts(data, "item-dragon-slayer")
    assert len(ups) == 1, (
        "Helper-resolved creature_type must trigger the rider; "
        f"auto_uplifts={data.get('auto_uplifts')}"
    )
    assert ups[0]["damage_type"] == "slashing"
    assert ups[0]["expression"] == "3d6"


async def test_dragon_slayer_no_rider_when_pc_not_dragon(gm_client, caelan, roster):
    """v2.158.96 negative case + regression net for the helper. If
    Tavik's sheet doesn't carry creature_type (the demo default),
    targeting him with Dragon Slayer must NOT fire the rider — the
    helper returns "" and the predicate fails."""
    tavik = roster["Brother Tavik Stonebrow"]
    caelan_cid = f"tok_dsf2_caelan_{caelan['id']}"
    tavik_cid = f"tok_dsf2_tavik_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(caelan_cid, caelan["id"], name=caelan["name"]),
        _mkc(tavik_cid, tavik["id"], name=tavik["name"]),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": caelan["id"],
            "attack_index": CAELAN_DRAGON_SLAYER_ATTACK_IDX,
            "target_combatant_id": tavik_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    ups = _uplifts(resp.json(), "item-dragon-slayer")
    assert ups == [], (
        "Tavik isn't a dragon; helper-resolved creature_type must "
        f"keep the rider silent; got {ups!r}"
    )
