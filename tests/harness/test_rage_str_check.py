"""v2.99.28 — Rage advantage on STR ability/skill checks.

RAW (PHB p.48): while raging, "you have advantage on Strength
checks and Strength saving throws." v2.99.26 closed the
`str_save` half via the save-roll construction hook. v2.99.28
closes the `str_check` half via a new `stat_key` body field on
`/roll` plus a Rage check in the `/roll` handler.

Implementation:
- Optional `stat_key` field on `/roll` body. When present, hooks
  read it for provenance. Today only the Rage STR-check helper
  consumes it; future hooks (Reliable Talent, Bardic Inspiration
  on checks/saves) can plug into the same plumbing.
- `_pc_has_rage_str_check_advantage(campaign_id, char_id)` sibling
  to `_pc_has_rage_str_save_advantage` (v2.99.26). Reads the same
  rage buff but gates on `str_check` in `advantage_on`.
- Pre-roll d20 swap (`1d20 → 2d20kh1`) in `/roll` when both gates
  fire. Composes safely with the v2.2.0 roll_state advantage path.
- `_broadcast_rage_str_check_advantage` companion fires after the
  standard roll broadcast.

Tests:
- happy: Krieger rages; POST /roll with stat_key="str_check" and
  1d20+X expression → server swaps to 2d20kh1 + broadcast fires.
- control non-raging: same body but no rage → 1d20 unchanged.
- control non-STR check: Krieger rages; stat_key="dex_check" → no
  swap (Rage gates on STR only).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _roll(gm_ws):
    msgs = gm_ws.buffered("roll")
    return msgs[-1] if msgs else None


def _rage_check_broadcasts(gm_ws, character_id: int) -> list:
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "rage-str-check"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


def _tok(char):
    return {
        "id": f"tok_rsc_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 60,
        "hp_max": 60,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


@pytest_asyncio.fixture
async def krieger_rested(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    return krieger


async def test_rage_grants_advantage_on_str_check(
    gm_client, gm_ws, krieger_rested,
):
    """Krieger rages; POST /roll with stat_key=str_check →
    expression swapped to 2d20kh1 + feature_used(source=
    rage-str-check) broadcast fires for him.
    """
    krieger = krieger_rested
    await _seed_battle(gm_client, [_tok(krieger)])
    # Activate Rage on Krieger.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    gm_ws.mark()
    # Roll an Athletics check (STR-shaped: 1d20 + STR mod + prof).
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+7",
            "stat_key": "str_check",
            "visibility": "public",
            "character_id": krieger["id"],
            "note": "Athletics check",
        },
    )
    assert resp.status_code == 200, resp.text
    import asyncio as _asy
    await _asy.sleep(0.2)

    roll_msg = _roll(gm_ws)
    assert roll_msg is not None, "expected a roll broadcast"
    expr = (roll_msg.get("data") or {}).get("expression") or ""
    assert "2d20kh1" in expr, (
        f"Rage should swap 1d20 → 2d20kh1 on STR check; "
        f"got expression={expr!r}"
    )
    msgs = _rage_check_broadcasts(gm_ws, krieger["id"])
    assert msgs, (
        f"expected feature_used(source=rage-str-check) broadcast; "
        f"buffered: {[(m.get('type'), (m.get('data') or {}).get('source')) for m in gm_ws.buffered()]}"
    )


async def test_rage_skips_str_check_when_not_raging(
    gm_client, gm_ws, krieger_rested,
):
    """Control: Krieger is NOT raging → stat_key=str_check on /roll
    keeps 1d20 (no swap, no broadcast).
    """
    krieger = krieger_rested
    await _seed_battle(gm_client, [_tok(krieger)])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+7",
            "stat_key": "str_check",
            "visibility": "public",
            "character_id": krieger["id"],
        },
    )
    assert resp.status_code == 200, resp.text
    import asyncio as _asy
    await _asy.sleep(0.2)

    roll_msg = _roll(gm_ws)
    assert roll_msg is not None
    expr = (roll_msg.get("data") or {}).get("expression") or ""
    assert "2d20kh1" not in expr, (
        f"non-raging Krieger should NOT get advantage; got "
        f"expression={expr!r}"
    )
    msgs = _rage_check_broadcasts(gm_ws, krieger["id"])
    assert not msgs


async def test_rage_skips_non_str_check_when_raging(
    gm_client, gm_ws, krieger_rested,
):
    """Control: Krieger rages; stat_key=dex_check → no rage swap.
    Confirms the Rage check advantage gates on STR only.
    """
    krieger = krieger_rested
    await _seed_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20+2",
            "stat_key": "dex_check",
            "visibility": "public",
            "character_id": krieger["id"],
        },
    )
    assert resp.status_code == 200, resp.text
    import asyncio as _asy
    await _asy.sleep(0.2)

    roll_msg = _roll(gm_ws)
    assert roll_msg is not None
    expr = (roll_msg.get("data") or {}).get("expression") or ""
    assert "2d20kh1" not in expr, (
        f"Rage should NOT grant advantage on DEX check; got "
        f"expression={expr!r}"
    )
    msgs = _rage_check_broadcasts(gm_ws, krieger["id"])
    assert not msgs
