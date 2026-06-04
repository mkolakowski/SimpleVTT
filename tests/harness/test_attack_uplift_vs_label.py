"""v2.99.190 — Attack chat-card breakdown labels rider with "(vs NAME)".

Closes the v2.99.188 follow-up. v2.99.188 stamped the weapon-hit
rider uplift dict with `vs_combatant_id` so the attack chat card
could render "Hunter's Mark (vs NAME)" without re-resolving
combatant ids. The user-visible rendering path is the broadcast's
`damage_breakdown` string (server-baked; `tabletop.js` doesn't
consume `auto_uplifts` directly today). v2.99.190 enriches the
suffix builder at line ~39348 to insert "(vs NAME)" when an
uplift carries `vs_combatant_id`.

Tests:
  - Rowan marks Pip + attacks Pip → `damage_breakdown` ends with
    "Hunter's Mark (vs NAME) <breakdown>".
  - Rowan attacks Pip with no rider in play → `damage_breakdown`
    has no "(vs ...)" suffix (no uplifts fired).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X"):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "buffs": [],
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def rowan_rested(gm_client, roster):
    rowan = roster["Rowan Quickbow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/rest",
        json={"type": "long"},
    )
    return rowan


async def test_attack_breakdown_labels_rider_vs_target(
    gm_client, rowan_rested, roster,
):
    """Rowan marks Pip then attacks Pip. The damage_breakdown
    string should include "Hunter's Mark (vs Pip Quickfingers)".
    """
    rowan = rowan_rested
    pip = roster["Pip Quickfingers"]
    rowan_cid = f"tok_aulvl_rw_{rowan['id']}"
    pip_cid = f"tok_aulvl_pip_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
        _mkc(pip_cid, pip["id"], name=pip["name"]),
    ])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
        json={
            "character_id": rowan["id"],
            "target_character_id": pip["id"],
            "override": True,
        },
    )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": rowan["id"],
            "attack_index": 0,
            "target_combatant_id": pip_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    breakdown = data.get("damage_breakdown") or ""
    assert "(vs " in breakdown, (
        f"v2.99.190: damage_breakdown should include '(vs ...)' for "
        f"a marked target; got {breakdown!r}"
    )
    assert pip["name"] in breakdown, (
        f"v2.99.190: damage_breakdown should name the marked target "
        f"({pip['name']}); got {breakdown!r}"
    )
    # Sanity: the rider's still in auto_uplifts with vs_combatant_id.
    hm = [u for u in (data.get("auto_uplifts") or [])
          if u.get("source") == "hunters-mark"]
    assert len(hm) == 1
    assert hm[0].get("vs_combatant_id") == pip_cid, (
        f"v2.99.190: auto_uplifts entry should carry vs_combatant_id "
        f"matching the swing's target; got {hm[0]}"
    )


async def test_attack_breakdown_no_rider_no_vs_label(
    gm_client, rowan_rested, roster,
):
    """Control: Rowan attacks Pip with no Hunter's Mark in play.
    The damage_breakdown has no "(vs ...)" suffix.
    """
    rowan = rowan_rested
    pip = roster["Pip Quickfingers"]
    rowan_cid = f"tok_aulvl2_rw_{rowan['id']}"
    pip_cid = f"tok_aulvl2_pip_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
        _mkc(pip_cid, pip["id"], name=pip["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": rowan["id"],
            "attack_index": 0,
            "target_combatant_id": pip_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    breakdown = data.get("damage_breakdown") or ""
    assert "(vs " not in breakdown, (
        f"v2.99.190: no rider → no '(vs ...)' suffix in breakdown; "
        f"got {breakdown!r}"
    )
