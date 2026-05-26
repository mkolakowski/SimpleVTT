"""v2.63.0 — F6 magical-source resistance gate + Ki-Empowered Strikes.

Pre-v2.63.0 a creature with "resistance to nonmagical bludgeoning"
halved damage from EVERY bludgeoning attack regardless of source —
even a Monk Lv 6+ unarmed strike (which RAW counts as magical via
Ki-Empowered Strikes). v2.63.0 plumbs `is_magical` through
`_apply_damage_to_combatant` → `_resistance_halve_npc`, which now
recognizes nonmagical-X variants and skips them when the attack
qualifies as magical.

The first source-side detector is Ki-Empowered Strikes (Monk Lv 6+
unarmed strikes). Other detectors (Magic Weapon spell, Pact of the
Blade, Druid Primal Strike) filed for follow-up.

Tests:
  - Werewolf-style NPC with `nonmagical-bludgeoning` buff. Tavik
    (Cleric Lv 8) attacks with Warhammer (bludgeoning, non-magical)
    → damage halved (resistance_applied: True).
  - Same NPC. Kael (Monk Lv 7) attacks with Unarmed Strike
    (bludgeoning, magical via Ki-Empowered Strikes) → damage NOT
    halved (resistance_applied: False).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def tavik_rested(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    return tavik


@pytest_asyncio.fixture
async def kael_rested(gm_client, roster):
    kael = roster["Kael Brightleaf"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
        json={"type": "long"},
    )
    return kael


def _werewolf_npc(cid="tok_werewolf", hp_current=80, hp_max=80):
    """NPC combatant carrying the canonical lycanthrope-style
    resistance via a buff (no token template needed). The buff's
    `effects.resistance_to` carries the `nonmagical-bludgeoning`
    entry that v2.63.0's resistance gate recognizes.
    """
    return {
        "id": cid,
        "name": "Werewolf-Style NPC",
        "initiative": 5,
        "hp_current": hp_current, "hp_max": hp_max,
        "buffs": [
            {
                "key": "lycanthrope-resistance",
                "name": "Lycanthrope Resistance",
                "icon": "🐺",
                "duration_rounds": 999,
                "duration_max": 999,
                "concentration": False,
                "effects": {
                    "resistance_to": ["nonmagical-bludgeoning"],
                },
            },
        ],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


def _mkc(cid, char_id, name, init=10):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": 50, "hp_max": 50,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _enable_auto_apply(gm_client):
    """Turn on auto_apply_damage so /attack actually applies HP
    changes + reports `damage_applied` > 0. Mirror of the helper in
    test_attack_auto_damage.py.
    """
    form = {
        "name": "Demo Campaign", "description": "demo", "game_system": "dnd5e",
        "gm_tab_color": "", "font_override": "", "default_encounter_id": "",
        "hp_threshold_1": "", "hp_threshold_2": "", "hp_threshold_3": "",
        "hp_threshold_4": "", "auto_play_playlist_id": "",
        "auto_play_mode": "order", "auto_play_initial_volume": "0.7",
        "auto_apply_damage": "on",
    }
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form, follow_redirects=False,
    )


async def _disable_auto_apply(gm_client):
    form = {
        "name": "Demo Campaign", "description": "demo", "game_system": "dnd5e",
        "gm_tab_color": "", "font_override": "", "default_encounter_id": "",
        "hp_threshold_1": "", "hp_threshold_2": "", "hp_threshold_3": "",
        "hp_threshold_4": "", "auto_play_playlist_id": "",
        "auto_play_mode": "order", "auto_play_initial_volume": "0.7",
    }
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form, follow_redirects=False,
    )


async def test_warhammer_against_nonmagical_resistance_is_halved(
    gm_client, tavik_rested,
):
    """Tavik (Cleric Lv 8, no Ki-Empowered Strikes) attacks the
    werewolf NPC with his Warhammer. Bludgeoning damage, not
    magical → resistance applies → response carries
    `target_resistance_applied: True`.

    Loop attacks until at least one hit lands (Warhammer +5 vs the
    NPC's implicit AC ~10-12 hits most rolls); assert on the FIRST
    hit's response.
    """
    tavik = tavik_rested
    await _enable_auto_apply(gm_client)
    try:
        for _ in range(8):
            await _seed_battle(gm_client, [
                _mkc(f"tok_tav_{tavik['id']}", tavik["id"], tavik["name"]),
                _werewolf_npc(),
            ])
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/attack",
                json={
                    "character_id": tavik["id"],
                    "attack_index": 0,  # Warhammer
                    "target_combatant_id": "tok_werewolf",
                    "override": True,
                },
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            if not data.get("hit"):
                continue
            assert data.get("damage_type") == "bludgeoning"
            assert data.get("target_resistance_applied") is True, (
                f"Tavik's Warhammer is non-magical bludgeoning; the "
                f"nonmagical-bludgeoning resistance should halve the "
                f"damage. Got target_resistance_applied="
                f"{data.get('target_resistance_applied')!r}"
            )
            return
        raise AssertionError(
            "Tavik did not land a hit on the werewolf NPC in 8 attempts"
        )
    finally:
        await _disable_auto_apply(gm_client)


async def test_kael_unarmed_strike_bypasses_nonmagical_resistance(
    gm_client, kael_rested,
):
    """Kael (Monk Lv 7, Ki-Empowered Strikes Lv 6+) attacks with his
    Unarmed Strike. Bludgeoning damage AND magical (via Ki-Empowered
    Strikes) → resistance does NOT apply → response carries
    `target_resistance_applied: False`.
    """
    kael = kael_rested
    await _enable_auto_apply(gm_client)
    try:
        for _ in range(8):
            await _seed_battle(gm_client, [
                _mkc(f"tok_kae_{kael['id']}", kael["id"], kael["name"]),
                _werewolf_npc(),
            ])
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/attack",
                json={
                    "character_id": kael["id"],
                    "attack_index": 0,  # Unarmed Strike
                    "target_combatant_id": "tok_werewolf",
                    "override": True,
                },
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            if not data.get("hit"):
                continue
            assert data.get("damage_type") == "bludgeoning"
            assert data.get("target_resistance_applied") is False, (
                f"Kael's Unarmed Strike is magical via Ki-Empowered "
                f"Strikes (Monk Lv 6+); the nonmagical-bludgeoning "
                f"resistance should NOT apply. Got "
                f"target_resistance_applied="
                f"{data.get('target_resistance_applied')!r}"
            )
            return
        raise AssertionError(
            "Kael did not land a hit on the werewolf NPC in 8 attempts"
        )
    finally:
        await _disable_auto_apply(gm_client)
