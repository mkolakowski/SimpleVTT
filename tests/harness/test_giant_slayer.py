"""v2.338.0 — magic-items: Giant Slayer (RAW DMG p.171, rare, NO attunement,
"any axe or sword"). Composes two substrates in one catalog row, both gated
on the same giant-type `condition`:

  1. The v2.158.93 Dragon Slayer conditional damage rider — `+2d6` of the
     weapon's type (piercing for Rowan's Shortsword) on a hit vs a giant,
     surfaced in `auto_uplifts` with `source: "item-giant-slayer"`.
  2. The v2.158.102 Demon Slayer `on_hit_save` — DC 15 STR save or prone
     (the NEW v2.338.0 `effect: "prone"` variant), broadcast as a
     `feature_used` with `source: "item-giant-slayer-save"` and, on a
     failed NPC save, the prone condition installed on the target.

No attunement: the rider fires on slug match alone (no equipped/attuned
gate). Demo fixture: Rowan Quickbow (Hunter Ranger) carries a Giant Slayer
Shortsword at `attack_index 3`, equipped — a dedicated giant-hunter
alongside his ranged Arrows of Slaying (Giants).

Tests:
  - Fires vs a giant (Hill Giant template): the +2d6 piercing uplift
    appears and the STR-save feature_used fires.
  - Silent vs a humanoid: no +2d6 uplift, no save.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


ROWAN_GIANT_SLAYER_ATTACK_IDX = 3


def _uplifts(data, source):
    return [u for u in (data.get("auto_uplifts") or [])
            if u.get("source") == source]


def _mkc(cid, char_id=None, name="X", creature_type="", token_template_id=None,
        ac=1, hp_max=200):
    c = {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_max, "hp_max": hp_max,
        "ac": ac,
        "buffs": [],
        "creature_type": creature_type,
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    if token_template_id is not None:
        c["token_template_id"] = token_template_id
    return c


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _hill_giant_template_id(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert r.status_code == 200, r.text
    giant = next(
        (t for t in r.json() if t.get("name") == "Hill Giant"), None,
    )
    assert giant is not None, "Hill Giant template missing from the demo seed"
    return giant["id"]


@pytest_asyncio.fixture
async def rowan(roster):
    return roster["Rowan Quickbow"]


async def test_giant_slayer_fires_on_giant(gm_client, gm_ws, rowan):
    """v2.338.0 happy path. Attacking a Hill Giant (creature_type giant via
    the template) surfaces the +2d6 piercing uplift AND the DC 15 STR
    save-or-prone feature_used."""
    template_id = await _hill_giant_template_id(gm_client)
    rowan_cid = f"tok_gs_giant_rowan_{rowan['id']}"
    giant_cid = "tok_gs_giant_target"
    await _seed_battle(gm_client, [
        _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
        _mkc(giant_cid, None, name="Hill Giant", creature_type="giant",
             token_template_id=template_id, hp_max=105),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": rowan["id"],
            "attack_index": ROWAN_GIANT_SLAYER_ATTACK_IDX,
            "target_combatant_id": giant_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["attack_name"] == "Giant Slayer Shortsword"

    # The +2d6 conditional damage rider.
    ups = _uplifts(data, "item-giant-slayer")
    assert len(ups) == 1, data.get("auto_uplifts")
    rider = ups[0]
    assert rider["expression"] == "2d6"
    assert rider["damage_type"] == "piercing"  # weapon-type fallback
    assert 2 <= rider["total"] <= 24  # 2d6 (crit-doubled upper bound)

    # The DC 15 STR save-or-prone fires as a feature_used broadcast.
    save_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "item-giant-slayer-save"
    ]
    assert save_msgs, (
        "Giant Slayer STR-save feature_used did not fire vs a giant. "
        f"feature_used sources: "
        f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
    )


async def test_giant_slayer_silent_on_humanoid(gm_client, gm_ws, rowan):
    """v2.338.0 negative case. Attacking a non-giant (humanoid) → no +2d6
    uplift and no STR-save feature_used. The condition predicate
    (creature_type == "giant") blocks both halves."""
    rowan_cid = f"tok_gs_hum_rowan_{rowan['id']}"
    bandit_cid = "tok_gs_hum_target"
    await _seed_battle(gm_client, [
        _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
        _mkc(bandit_cid, None, name="Bandit", creature_type="humanoid",
             hp_max=60),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": rowan["id"],
            "attack_index": ROWAN_GIANT_SLAYER_ATTACK_IDX,
            "target_combatant_id": bandit_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    ups = _uplifts(resp.json(), "item-giant-slayer")
    assert ups == [], f"Giant Slayer must not fire vs. humanoid; got {ups!r}"
    save_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "item-giant-slayer-save"
    ]
    assert not save_msgs, (
        f"Giant Slayer STR-save must not fire vs. humanoid; got {save_msgs!r}"
    )
