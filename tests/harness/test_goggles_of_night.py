"""v2.159.24 — Magic-items follow-up: Goggles of Night.

RAW DMG p.172 (uncommon, no attunement): "While you wear these dark
lenses, you have darkvision out to 60 ft." Composes with the v2.158.50
Devil's Sight darkness-blinded helper — a Goggles-equipped PC who's
blinded by darkness shrugs off the attack disadvantage exactly as a
Devil's-Sight Warlock does. First sensory-passive magic item; future
Eyes of the Eagle / True Sight items extend the same dict shape with
new sensory fields.

Pip Quickfingers (Halfling Rogue Lv 5) carries the Goggles at
inventory_index 10 in the demo seed (after the Cloak / Ring of
Protection / Sword of Sharpness — Pip's Halfling race has no native
darkvision, so the Goggles add a meaningful sense).

Tests mirror `test_devils_sight_resolver.py`:
  - Darkness-blinded + Goggles → disadvantage NEGATED.
  - Darkness-blinded with Goggles unequipped (control) → disadvantage
    applies.
  - Non-darkness blinded + Goggles → disadvantage STILL applies
    (Goggles only negate darkness-blindness).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


PIP_GOGGLES_INV_IDX = 10


@pytest_asyncio.fixture
async def pip(roster):
    return roster["Pip Quickfingers"]


@pytest_asyncio.fixture
async def pip_with_goggles_equipped(gm_client, pip):
    """Ensure Pip's inventory[10] (Goggles of Night) is equipped, then
    long-rest. Restores state on teardown."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/rest",
        json={"type": "long"},
    )
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    inv = list(sheet.get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    if PIP_GOGGLES_INV_IDX < len(inv):
        inv[PIP_GOGGLES_INV_IDX] = {**inv[PIP_GOGGLES_INV_IDX], "equipped": True}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
            json={"inventory": inv},
        )
    yield pip
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"inventory": snapshot},
    )


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants,
            "turn_index": 0,
            "round": 1,
            "active": True,
        },
    )


def _mkc(cid, char_id=None, hp_cur=40, hp_max=40, name="X", buffs=None):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur,
        "hp_max": hp_max,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _attack(gm_client, attacker_id, target_cid):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": attacker_id,
            "attack_index": 0,
            "target_combatant_id": target_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_goggles_negate_darkness_blinded_disadvantage(
    gm_client, pip_with_goggles_equipped, roster,
):
    """v2.159.24 happy path. Pip's darkness-blinded + Goggles equipped
    → attack roll stays 1d20 (no disadvantage). Mirror of v2.158.50
    Devil's Sight case but powered by the item passive."""
    pip = pip_with_goggles_equipped
    tavik = roster["Brother Tavik Stonebrow"]
    pip_cid = f"tok_gog1_{pip['id']}"
    tavik_cid = f"tok_gog1_tavik_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(pip_cid, pip["id"], name="Pip", buffs=[{
            "key": "blinded",
            "name": "Blinded (Darkness)",
            "effects": {"from_darkness": True},
        }]),
        _mkc(tavik_cid, tavik["id"], name="Tavik"),
    ])
    data = await _attack(gm_client, pip["id"], tavik_cid)
    breakdown = data.get("attack_breakdown") or ""
    assert "2d20kl1" not in breakdown, (
        f"Goggles should cancel darkness-blind disadvantage; "
        f"got {breakdown!r}"
    )
    assert data.get("roll_state_applied") != "disadvantage_attacker_blinded", (
        f"roll_state_applied should not flag blinded disadvantage; "
        f"got {data.get('roll_state_applied')!r}"
    )


async def test_goggles_unequipped_does_not_negate_disadvantage(
    gm_client, pip, roster,
):
    """Control: unequip the Goggles → darkness-blinded Pip rolls at
    disadvantage as normal."""
    tavik = roster["Brother Tavik Stonebrow"]
    sheet_resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-json",
    )
    sheet = sheet_resp.json().get("sheet") or {}
    inv = list(sheet.get("inventory") or [])
    snapshot = [dict(it) if isinstance(it, dict) else it for it in inv]
    if PIP_GOGGLES_INV_IDX < len(inv):
        inv[PIP_GOGGLES_INV_IDX] = {**inv[PIP_GOGGLES_INV_IDX], "equipped": False}
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
            json={"inventory": inv},
        )
    try:
        pip_cid = f"tok_gog2_{pip['id']}"
        tavik_cid = f"tok_gog2_tavik_{tavik['id']}"
        await _seed_battle(gm_client, [
            _mkc(pip_cid, pip["id"], name="Pip", buffs=[{
                "key": "blinded",
                "name": "Blinded (Darkness)",
                "effects": {"from_darkness": True},
            }]),
            _mkc(tavik_cid, tavik["id"], name="Tavik"),
        ])
        data = await _attack(gm_client, pip["id"], tavik_cid)
        assert "2d20kl1" in (data.get("attack_breakdown") or ""), (
            f"Expected 2d20kl1 without Goggles; "
            f"got {data.get('attack_breakdown')!r}"
        )
        assert data.get("roll_state_applied") == "disadvantage_attacker_blinded", (
            f"roll_state_applied mismatch; got "
            f"{data.get('roll_state_applied')!r}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
            json={"inventory": snapshot},
        )


async def test_goggles_do_not_cure_non_darkness_blindness(
    gm_client, pip_with_goggles_equipped, roster,
):
    """Guard: Pip has Goggles equipped but the `blinded` condition is
    NOT darkness-sourced (e.g. Blindness/Deafness spell). Disadvantage
    STILL applies — Goggles only negate the inability to see in
    darkness."""
    pip = pip_with_goggles_equipped
    tavik = roster["Brother Tavik Stonebrow"]
    pip_cid = f"tok_gog3_{pip['id']}"
    tavik_cid = f"tok_gog3_tavik_{tavik['id']}"
    await _seed_battle(gm_client, [
        _mkc(pip_cid, pip["id"], name="Pip", buffs=[{
            "key": "blinded",
            "name": "Blinded",
            # No from_darkness — generic blindness from Blindness spell.
        }]),
        _mkc(tavik_cid, tavik["id"], name="Tavik"),
    ])
    data = await _attack(gm_client, pip["id"], tavik_cid)
    assert "2d20kl1" in (data.get("attack_breakdown") or ""), (
        f"Goggles should NOT cure non-darkness blindness; "
        f"got {data.get('attack_breakdown')!r}"
    )
    assert data.get("roll_state_applied") == "disadvantage_attacker_blinded", (
        f"roll_state_applied mismatch; got "
        f"{data.get('roll_state_applied')!r}"
    )
