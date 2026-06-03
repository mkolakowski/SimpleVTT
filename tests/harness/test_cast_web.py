"""v2.99.105 — /cast_web endpoint tests.

Lv 2 Wizard/Sorcerer concentration spell. v1 ships only the
speed-to-0 effect (Restrained's primary mechanical bite). Other
Restrained effects (attack/save disadvantages, advantage to
attackers) are listed in `raw_effects` for GM narration but not
yet mechanically enforced — filed pending a standalone restrained
condition buff.

Tests mirror the /cast_slow shape:
  - happy path installs the buff with speed_reduction_ft = base
  - non-Wizard/Sorcerer class_slug → 400
  - missing target_combatant_ids → 400
  - Lv 1 slot → 400 (Web is L2)
  - zero-speed target → reduction 0 (no negative)

Thalindra has Web on her list as of v2.99.105.
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


@pytest_asyncio.fixture
async def thalindra_and_krieger(gm_client, roster):
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_web_th_{thalindra['id']}"
    kr_tok = f"tok_web_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"],
             speed_walk=30),
        _mkc(kr_tok, krieger["id"], name=krieger["name"],
             speed_walk=40),
    ])
    yield thalindra, krieger, kr_tok


async def test_cast_web_installs_full_speed_reduction(
    gm_client, thalindra_and_krieger,
):
    """Cast Web on Krieger (40 ft base) → buff installed with
    speed_reduction_ft = 40 (full reduction → effective speed 0).
    """
    thalindra, krieger, kr_tok = thalindra_and_krieger
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
    data = resp.json()
    assert data["ok"] is True
    assert data["duration_rounds"] == 600  # 1 hour
    assert data["concentration"] is True
    affected = data.get("affected") or []
    assert len(affected) == 1, affected
    entry = affected[0]
    assert entry["combatant_id"] == kr_tok
    assert entry["base_speed_walk"] == 40
    # Full reduction so effective_speed_walk = max(0, 40 - 40) = 0.
    assert entry["speed_reduction_ft"] == 40, entry
    assert entry["installed"] is True


async def test_cast_web_rejects_wrong_class(gm_client, roster):
    """Web is Wizard/Sorcerer only; class_slug="cleric" → 400."""
    thalindra = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_web",
        json={
            "character_id": thalindra["id"],
            "class_slug": "cleric",
            "slot_level": 2,
            "target_combatant_ids": ["x"],
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_cast_web_requires_target_combatant_ids(gm_client, roster):
    """Empty target list → 400."""
    thalindra = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_web",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 2,
            "target_combatant_ids": [],
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_cast_web_rejects_level_1_slot(gm_client, roster):
    """Web is L2; slot_level=1 → 400."""
    thalindra = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_web",
        json={
            "character_id": thalindra["id"],
            "class_slug": "wizard",
            "slot_level": 1,
            "target_combatant_ids": ["x"],
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_cast_web_handles_zero_speed_target(gm_client, roster):
    """Target already at 0 speed (already webbed by another caster).
    reduction = base = 0; effective stays 0. Buff installs clean.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    krieger = roster["Krieger Stonefist"]
    th_tok = f"tok_web_zero_th_{thalindra['id']}"
    kr_tok = f"tok_web_zero_kr_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(th_tok, thalindra["id"], name=thalindra["name"],
             speed_walk=30),
        _mkc(kr_tok, krieger["id"], name=krieger["name"],
             speed_walk=0),
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
    affected = resp.json().get("affected") or []
    assert len(affected) == 1, affected
    assert affected[0]["speed_reduction_ft"] == 0, affected[0]
