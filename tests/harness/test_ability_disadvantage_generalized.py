"""v2.347.0 — generalized ability check/save disadvantage at /roll.

Prior to v2.347.0 the `effects.disadvantage_on` intercept fired only on
STR *checks* (the v2.199.0 Potion of Diminution path). This generalizes
it to ANY ability marker — `{ability}_check` / `{ability}_save` — so a
buff carrying e.g. `disadvantage_on: ["con_save"]` swaps the rolling
PC's `1d20 → 2d20kl1` on a CON save, and `["str_save"]` covers STR
saves (previously uncovered). Foundation for items like Staff of
Withering ("disadvantage on STR/CON checks AND saves").

The buff is seeded directly on the PC's combatant via PUT /battle, then
/roll is posted with the matching `stat_key`; the roll broadcast's
`expression` reveals the kl1 swap. Marker specificity is proven by a
control roll whose marker isn't in the buff.
"""
import asyncio

import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _roll(gm_ws):
    msgs = gm_ws.buffered("roll")
    return msgs[-1] if msgs else None


def _dis_broadcasts(gm_ws, character_id, marker):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == f"disadvantage-{marker}"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _tok(char, dis_markers):
    return {
        "id": f"tok_dis_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 60, "hp_max": 60,
        "buffs": [{
            "key": "withered-test",
            "name": "Withered",
            "icon": "💀",
            "duration_rounds": 10, "duration_max": 10,
            "concentration": False,
            "effects": {"disadvantage_on": list(dis_markers)},
        }],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _roll_stat(gm_client, char_id, stat_key, expr="1d20+3"):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": expr,
            "stat_key": stat_key,
            "visibility": "public",
            "character_id": char_id,
            "note": f"{stat_key} (test)",
        },
    )
    assert resp.status_code == 200, resp.text


@pytest_asyncio.fixture
async def krieger(roster):
    return roster["Krieger Stonefist"]


async def test_con_save_disadvantage_fires(gm_client, gm_ws, krieger):
    """A buff with disadvantage_on=["con_save"] swaps 1d20 → 2d20kl1 on a
    CON save + fires the disadvantage-con_save broadcast."""
    await _seed_battle(gm_client, [_tok(krieger, ["con_save"])])
    gm_ws.mark()
    await _roll_stat(gm_client, krieger["id"], "con_save")
    await asyncio.sleep(0.2)
    roll_msg = _roll(gm_ws)
    assert roll_msg is not None
    expr = (roll_msg.get("data") or {}).get("expression") or ""
    assert "2d20kl1" in expr, f"expected disadvantage on CON save; got {expr!r}"
    assert _dis_broadcasts(gm_ws, krieger["id"], "con_save"), (
        "expected feature_used(source=disadvantage-con_save)"
    )


async def test_str_save_disadvantage_fires(gm_client, gm_ws, krieger):
    """STR saves are now covered too (previously the intercept was
    check-only): disadvantage_on=["str_save"] → 2d20kl1 on a STR save."""
    await _seed_battle(gm_client, [_tok(krieger, ["str_save"])])
    gm_ws.mark()
    await _roll_stat(gm_client, krieger["id"], "str_save")
    await asyncio.sleep(0.2)
    expr = (_roll(gm_ws).get("data") or {}).get("expression") or ""
    assert "2d20kl1" in expr, f"expected disadvantage on STR save; got {expr!r}"


async def test_marker_specificity_control(gm_client, gm_ws, krieger):
    """Control: a buff that only carries con_save does NOT impose
    disadvantage on a CON *check* (marker mismatch)."""
    await _seed_battle(gm_client, [_tok(krieger, ["con_save"])])
    gm_ws.mark()
    await _roll_stat(gm_client, krieger["id"], "con_check")
    await asyncio.sleep(0.2)
    expr = (_roll(gm_ws).get("data") or {}).get("expression") or ""
    assert "2d20kl1" not in expr, (
        f"con_save marker must not affect a con_check roll; got {expr!r}"
    )
