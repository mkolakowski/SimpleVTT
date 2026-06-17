"""v2.388.0 — /use_feature incapacitated gate.

RAW PHB p.290: "An incapacitated creature can't take actions or
reactions." Mirror of the v2.386.0 /attack + v2.387.0 /cast_spell
gates. Closes clause #2c — the third and final endpoint for the
general action gate in the v2.384.0 condition-enforcement audit.

Tests:
  - Paralyzed Pip calling /use_feature → 409 `incapacitated` with
    feature_key + char_name + source echoed.
  - Same setup with `override: True` → the gate is bypassed; the
    feature use proceeds (200).
  - Non-incapacitated Pip → /use_feature proceeds normally (200).
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _make_combatant(name, char_id, hp=50, init=10, buffs=None):
    return {
        "id": f"tok_ufi_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


PARALYZED_BUFF = {
    "key": "paralyzed",
    "name": "Paralyzed (Hold Person)",
    "icon": "🥶",
    "duration_rounds": 10,
    "concentration": False,
}


@pytest_asyncio.fixture
async def pip_rested(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    return pip


async def test_paralyzed_caster_use_feature_returns_409(
    gm_client, pip_rested,
):
    """Pip is paralyzed; calling /use_feature returns 409
    `incapacitated`. Uses Cunning Action (Dash) — the simplest
    no-resource feature on Pip's sheet."""
    pip = pip_rested
    await _seed_battle(gm_client, [
        _make_combatant(pip["name"], pip["id"], buffs=[PARALYZED_BUFF]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": pip["id"],
            "feature_key": "cunning-action",
            "option_key": "dash",
            "label": "Cunning Action",
        },
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body.get("error") == "incapacitated"
    assert body.get("char_name") == pip["name"]
    assert body.get("source") == "use_feature"
    assert body.get("feature_key") == "cunning-action"


async def test_paralyzed_caster_use_feature_with_override_succeeds(
    gm_client, pip_rested,
):
    """Same setup but with `override: True` → the gate is bypassed;
    the feature use proceeds (200)."""
    pip = pip_rested
    await _seed_battle(gm_client, [
        _make_combatant(pip["name"], pip["id"], buffs=[PARALYZED_BUFF]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": pip["id"],
            "feature_key": "cunning-action",
            "option_key": "dash",
            "label": "Cunning Action",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text


async def test_non_incapacitated_caster_use_feature_succeeds(
    gm_client, pip_rested,
):
    """Pip has no incapacitating buff; /use_feature proceeds normally."""
    pip = pip_rested
    await _seed_battle(gm_client, [
        _make_combatant(pip["name"], pip["id"]),  # No buffs.
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": pip["id"],
            "feature_key": "cunning-action",
            "option_key": "dash",
            "label": "Cunning Action",
            "override": True,  # Bypass the over-budget gate so we don't
                               # collide with other tests that consumed
                               # the bonus slot earlier in the run.
        },
    )
    assert resp.status_code == 200, resp.text
