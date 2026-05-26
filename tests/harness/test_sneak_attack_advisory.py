"""v2.62.1 — F1 Sneak Attack ally-adjacency advisory in /attack response.

Sneak Attack RAW: rogue gets the bonus dice when (a) attacker has
advantage on the attack roll, OR (b) "another enemy of the target
is within 5 feet of it, not incapacitated, and you don't have
disadvantage." Pre-v2.62.1 the (b) branch was trust-based; v2.62.1
auto-detects it server-side via the v2.61.0 token-adjacency primitive
and surfaces it as `sneak_attack_ally_adjacent: bool` on the /attack
response. Advisory only — no enforcement.

Tests:
  - Rogue Pip attacks Krieger with an ally (Caelan) placed 5 ft from
    Krieger → response carries `sneak_attack_ally_adjacent: True`.
  - Same setup but Caelan placed 25 ft from Krieger → False.
  - Non-Rogue attacker (Tavik) → always False (advisory gated on
    rogue class).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def pip_rested(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    return pip


def _make_combatant(name, char_id, hp_current=30, hp_max=50, init=10):
    return {
        "id": f"tok_sa_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp_current, "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


async def _restore_token(gm_client, char_id):
    """Move token to a benign corner (avoids breaking test_move which
    expects demo tokens to still exist). See v2.61.1 notes."""
    await _place_token(gm_client, char_id, 50.0, 50.0)


async def test_sneak_attack_advisory_fires_when_ally_within_5_ft(
    gm_client, pip_rested, roster,
):
    """Pip attacks Krieger with Caelan placed 5 ft from Krieger →
    advisory True.
    """
    pip = pip_rested
    krieger = roster["Krieger Stonefist"]
    caelan = roster["Sir Caelan Lightbringer"]

    # Pip at (350, 350); Krieger at (700, 350) — 25 ft (irrelevant
    # to advisory, which checks ally vs target distance); Caelan at
    # (770, 350) — 1 cell = 5 ft from Krieger.
    await _place_token(gm_client, pip["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 700.0, 350.0)
    await _place_token(gm_client, caelan["id"], 770.0, 350.0)

    await _seed_battle(gm_client, [
        _make_combatant(pip["name"], pip["id"]),
        _make_combatant(krieger["name"], krieger["id"], hp_current=50, hp_max=75),
        _make_combatant(caelan["name"], caelan["id"]),
    ])

    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": 0,
                "target_combatant_id": f"tok_sa_{krieger['id']}",
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("sneak_attack_ally_adjacent") is True, (
            f"expected sneak_attack_ally_adjacent=True with Caelan 5 ft "
            f"from Krieger; got {data.get('sneak_attack_ally_adjacent')}"
        )
    finally:
        await _restore_token(gm_client, pip["id"])
        await _restore_token(gm_client, krieger["id"])
        await _restore_token(gm_client, caelan["id"])


async def test_sneak_attack_advisory_false_when_ally_out_of_range(
    gm_client, pip_rested, roster,
):
    """Pip attacks Krieger with no other combatants within 5 ft of
    Krieger → advisory False.
    """
    pip = pip_rested
    krieger = roster["Krieger Stonefist"]
    caelan = roster["Sir Caelan Lightbringer"]

    # Caelan placed 5 cells (25 ft) from Krieger — out of range.
    await _place_token(gm_client, pip["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 700.0, 350.0)
    await _place_token(gm_client, caelan["id"], 1050.0, 350.0)

    await _seed_battle(gm_client, [
        _make_combatant(pip["name"], pip["id"]),
        _make_combatant(krieger["name"], krieger["id"], hp_current=50, hp_max=75),
        _make_combatant(caelan["name"], caelan["id"]),
    ])

    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": 0,
                "target_combatant_id": f"tok_sa_{krieger['id']}",
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("sneak_attack_ally_adjacent") is False, (
            f"expected sneak_attack_ally_adjacent=False with Caelan 25 ft "
            f"from Krieger; got {data.get('sneak_attack_ally_adjacent')}"
        )
    finally:
        await _restore_token(gm_client, pip["id"])
        await _restore_token(gm_client, krieger["id"])
        await _restore_token(gm_client, caelan["id"])


async def test_sneak_attack_advisory_false_for_non_rogue(
    gm_client, roster,
):
    """Tavik (Cleric, not Rogue) attacks Krieger with Caelan 5 ft
    away — the advisory is gated on Rogue class so it stays False
    for non-Rogues regardless of adjacency.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    krieger = roster["Krieger Stonefist"]
    caelan = roster["Sir Caelan Lightbringer"]

    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )

    await _place_token(gm_client, tavik["id"], 350.0, 350.0)
    await _place_token(gm_client, krieger["id"], 700.0, 350.0)
    await _place_token(gm_client, caelan["id"], 770.0, 350.0)  # 5 ft from Krieger

    await _seed_battle(gm_client, [
        _make_combatant(tavik["name"], tavik["id"]),
        _make_combatant(krieger["name"], krieger["id"], hp_current=50, hp_max=75),
        _make_combatant(caelan["name"], caelan["id"]),
    ])

    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik["id"],
                "attack_index": 0,
                "target_combatant_id": f"tok_sa_{krieger['id']}",
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("sneak_attack_ally_adjacent") is False, (
            f"non-Rogue attacker should always see advisory=False; "
            f"got {data.get('sneak_attack_ally_adjacent')}"
        )
    finally:
        await _restore_token(gm_client, tavik["id"])
        await _restore_token(gm_client, krieger["id"])
        await _restore_token(gm_client, caelan["id"])
