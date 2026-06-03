"""v2.99.101 — /cast_slow endpoint tests.

Lv 3 Wizard/Sorcerer concentration spell. v1 ships only the
speed-halving effect: installs a `slow` buff on each target
with `effects.speed_reduction_ft: base_speed // 2 (rounded down to
nearest 5)`. The v2.99.98 `_effective_speed_walk` helper subtracts
this at /token/move + Mov chip render time; the v2.99.99
`/token/move` 409 gate enforces server-side.

Tests:
  - happy path installs the buff with effects.speed_reduction_ft = 15
  - too-many-targets (7) → 409 too_many_targets
  - non-Wizard/Sorcerer class_slug → 400
  - target speed 0 → install with reduction 0 (no negative cap)

Thalindra Moonwhisper (Wizard Lv 7) is the caster. She has Slow on
her list as of v2.99.101.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", speed_walk=30, source_token_id=None):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "source_token_id": source_token_id,
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


@pytest_asyncio.fixture
async def thalindra_and_krieger(gm_client, roster):
    """Set up Thalindra + Krieger in init. Yields (thalindra, krieger,
    krieger_tok_id) tuple.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_slow_th_{thalindra['id']}"
    kr_tok = f"tok_slow_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"],
             speed_walk=30),
        _mkc(kr_tok, krieger["id"], name=krieger["name"],
             speed_walk=40),  # Krieger Barbarian Fast Movement
    ])
    yield thalindra, krieger, kr_tok


async def test_cast_slow_installs_speed_reduction_buff(
    gm_client, thalindra_and_krieger,
):
    """Cast Slow on Krieger (40 ft base) → buff installed with
    speed_reduction_ft = 20 (40 // 2 = 20, rounded to nearest 5).
    """
    thalindra, krieger, kr_tok = thalindra_and_krieger
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
    data = resp.json()
    assert data["ok"] is True
    assert data["duration_rounds"] == 10
    assert data["concentration"] is True
    affected = data.get("affected") or []
    assert len(affected) == 1, affected
    entry = affected[0]
    assert entry["combatant_id"] == kr_tok
    assert entry["base_speed_walk"] == 40
    # 40 // 2 = 20, already a multiple of 5.
    assert entry["speed_reduction_ft"] == 20, entry
    assert entry["installed"] is True


async def test_cast_slow_rejects_more_than_six_targets(gm_client, roster):
    """RAW caps Slow at 6 targets. 7 → 409 too_many_targets."""
    thalindra = roster["Thalindra Moonwhisper"]
    # Seed dummy combatants for the count check.
    fake_ids = [f"tok_slow_dummy_{i}" for i in range(7)]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 3,
            "target_combatant_ids": fake_ids,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "too_many_targets", data
    assert data.get("max") == 6, data


async def test_cast_slow_rejects_wrong_class(gm_client, roster):
    """Slow is Wizard/Sorcerer only; class_slug="cleric" → 400."""
    thalindra = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_slow",
        json={
            "character_id": thalindra["id"],
            "class_slug": "cleric",
            "slot_level": 3,
            "target_combatant_ids": ["x"],
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_cast_slow_clamps_zero_speed_target(gm_client, roster):
    """Target already at 0 speed (e.g. webbed) → reduction = 0,
    no negative. Buff installs without breaking.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_slow_zero_th_{thalindra['id']}"
    kr_tok = f"tok_slow_zero_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"],
             speed_walk=30),
        _mkc(kr_tok, krieger["id"], name=krieger["name"],
             speed_walk=0),
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
    affected = resp.json().get("affected") or []
    assert len(affected) == 1, affected
    assert affected[0]["speed_reduction_ft"] == 0, affected[0]
