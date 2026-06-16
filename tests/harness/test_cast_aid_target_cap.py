"""v2.372.1 — Aid 3-target cap (RAW PHB p.211: "Choose up to three
creatures within range").

The v2.372.1 `_SPELL_BUFF_MAP["aid"]` entry gains a `max_targets: 3`
field; /cast_spell's buff-install branch reads it and returns 400
`too_many_targets` when the caller passes more target ids than the
cap. Upcasting Aid scales HP per target (v2.371.0) but does NOT
raise the count.

Tests:
  - 3 targets → 200 (the RAW cap).
  - 4 targets → 400 `too_many_targets`.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


CAELAN_AID_INDEX = 5


async def _long_rest(gm_client, char_id):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )


def _mkc(cid, char_id=None, name="X"):
    return {
        "id": cid, "char_id": char_id, "name": name,
        "initiative": 10, "hp_current": 30, "hp_max": 40,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _end_aid(gm_client, char_id):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": char_id, "key": "aid"},
    )


async def _seed_battle(gm_client, caelan, targets):
    """Seed a battle with Caelan + N PC targets. Returns the list of
    target combatant ids in the order they were placed."""
    combatants = [_mkc(
        f"tok_aid_cap_caelan_{caelan['id']}", caelan["id"],
        name=caelan["name"],
    )]
    target_toks = []
    for i, t in enumerate(targets):
        tok = f"tok_aid_cap_{t['id']}_{i}"
        combatants.append(_mkc(tok, t["id"], name=t["name"]))
        target_toks.append(tok)
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )
    return target_toks


@pytest_asyncio.fixture
async def caelan(gm_client, roster):
    caelan = roster["Sir Caelan Lightbringer"]
    await _long_rest(gm_client, caelan["id"])
    return caelan


@pytest_asyncio.fixture
async def three_targets(gm_client, roster):
    pcs = [
        roster["Pip Quickfingers"],
        roster["Krieger Stonefist"],
        roster["Kael Brightleaf"],
    ]
    for pc in pcs:
        await _end_aid(gm_client, pc["id"])
    return pcs


@pytest_asyncio.fixture
async def four_targets(gm_client, three_targets, roster):
    fourth = roster["Mira Greenleaf"]
    await _end_aid(gm_client, fourth["id"])
    return three_targets + [fourth]


async def test_aid_three_targets_succeeds(
    gm_client, caelan, three_targets,
):
    """RAW cap: Aid hits up to 3 creatures. 3 targets → 200."""
    toks = await _seed_battle(gm_client, caelan, three_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": CAELAN_AID_INDEX,
            "slot_level": 2,
            "class_slug": "paladin",
            "target_combatant_ids": toks,
            "target_name": "Aid (3 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 200, resp.text
    # Cleanup
    for pc in three_targets:
        await _end_aid(gm_client, pc["id"])


async def test_aid_four_targets_returns_400(
    gm_client, caelan, four_targets,
):
    """RAW cap: 4 targets exceeds the limit. /cast_spell returns 400
    `too_many_targets` with `limit: 3`."""
    toks = await _seed_battle(gm_client, caelan, four_targets)
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caelan["id"],
            "spell_index": CAELAN_AID_INDEX,
            "slot_level": 2,
            "class_slug": "paladin",
            "target_combatant_ids": toks,
            "target_name": "Aid (4 targets)",
            "override": True,
            "override_range": True,
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "too_many_targets"
    assert body.get("limit") == 3
    assert body.get("received") == 4
    # No cleanup needed — the 400 means no buff was installed.
