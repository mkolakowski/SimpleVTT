"""v2.99.23 — Half-Orc Savage Attacks.

RAW (PHB p.41, Half-Orc race trait): "When you score a critical hit
with a melee weapon attack, you can roll one of the weapon's damage
dice one additional time and add it to the extra damage of the
critical hit." Auto-fires (no resource, no decision); applies only
on melee weapon crits.

Implementation extends `_compute_attack_auto_uplifts` with `is_crit`
and `weapon_damage_expr` kwargs. The new branch reads the attacker's
race slug via `_race_slug_from_sheet` and, when the slug is
"half-orc" + is_crit + the damage type is physical (melee proxy),
adds one extra die roll to the uplift list — labeled "Savage Attacks"
with source="savage-attacks".

Test strategy:
- Seed dice so Krieger's attack rolls 20 (crit). Krieger's Greataxe
  is 1d12+4; on crit, Savage Attacks adds one extra 1d12.
- Assert the `auto_uplifts` list in the attack response contains an
  entry with source="savage-attacks" + expression="1d12".
- Control: Same setup with Garrik (Variant Human Fighter) — no
  Savage Attacks uplift on crit.
"""
from typing import Optional
import pytest_asyncio
import re

from .conftest import CAMPAIGN_ID


async def _seed_dice(gm_client, seed: int):
    resp = await gm_client.post(
        "/api/test/dice/seed", json={"seed": seed},
    )
    assert resp.status_code == 200, resp.text


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


def _tok(char):
    return {
        "id": f"tok_sa_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 60,
        "hp_max": 60,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


_D20_RE = re.compile(r"\d*d20[^d=+ ]*=(\d+)", re.IGNORECASE)


def _kept_d20(attack_breakdown: str) -> Optional[int]:
    if not attack_breakdown:
        return None
    m = _D20_RE.search(attack_breakdown)
    return int(m.group(1)) if m else None


@pytest_asyncio.fixture
async def krieger_rested(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    return krieger


@pytest_asyncio.fixture
async def garrik_rested(gm_client, roster):
    garrik = roster["Garrik Ironside"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/rest",
        json={"type": "long"},
    )
    return garrik


async def test_savage_attacks_fires_on_half_orc_crit(
    gm_client, gm_ws, krieger_rested, roster,
):
    """Krieger attacks a Bandit; loop seeded dice until a crit lands.
    Assert the response's auto_uplifts list carries an entry with
    source="savage-attacks" + expression="1d12" (Krieger's Greataxe
    damage die).
    """
    krieger = krieger_rested
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    bandit = next(
        (t for t in r.json() if (t.get("name") or "").lower() == "bandit"),
        None,
    )
    assert bandit
    await _seed_battle(gm_client, [
        _tok(krieger),
        {"id": "tok_sa_bandit", "char_id": None,
         "token_template_id": bandit["id"], "name": bandit["name"],
         "initiative": 5, "hp_current": 30, "hp_max": 30, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    crit_landed = False
    for seed in range(1, 400):
        await _seed_dice(gm_client, seed)
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": krieger["id"],
                "attack_index": 0,  # Greataxe
                "target_combatant_id": "tok_sa_bandit",
                "override": True,
            },
        )
        if resp.status_code != 200:
            continue
        data = resp.json()
        breakdown = data.get("attack_breakdown") or ""
        kept = _kept_d20(breakdown)
        # Krieger's threshold is RAW 20 (not a Champion); v2.49.231
        # only lowered the threshold for Champion Fighters.
        if kept != 20:
            continue
        uplifts = data.get("auto_uplifts") or []
        savage = [u for u in uplifts if u.get("source") == "savage-attacks"]
        assert savage, (
            f"Krieger crit but no Savage Attacks uplift; uplifts={uplifts}"
        )
        assert savage[0].get("expression") == "1d12", (
            f"expected Savage Attacks expression=1d12 (Greataxe die); "
            f"got {savage[0]}"
        )
        crit_landed = True
        break
    assert crit_landed, "no Krieger crit observed in 400 seeds"


async def test_savage_attacks_skips_non_half_orc(
    gm_client, gm_ws, garrik_rested, roster,
):
    """Control: Garrik (Variant Human Fighter) crits with his sword
    — no Savage Attacks uplift in the response.
    """
    garrik = garrik_rested
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    bandit = next(
        (t for t in r.json() if (t.get("name") or "").lower() == "bandit"),
        None,
    )
    assert bandit
    await _seed_battle(gm_client, [
        _tok(garrik),
        {"id": "tok_sa_bandit2", "char_id": None,
         "token_template_id": bandit["id"], "name": bandit["name"],
         "initiative": 5, "hp_current": 30, "hp_max": 30, "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])
    crit_landed = False
    for seed in range(1, 400):
        await _seed_dice(gm_client, seed)
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": garrik["id"],
                "attack_index": 0,
                "target_combatant_id": "tok_sa_bandit2",
                "override": True,
            },
        )
        if resp.status_code != 200:
            continue
        data = resp.json()
        breakdown = data.get("attack_breakdown") or ""
        kept = _kept_d20(breakdown)
        # Garrik is a Champion Fighter (v2.49.231 Lv 7+) so crits on
        # 19 or 20. Either is a crit for our purposes.
        if kept not in (19, 20):
            continue
        uplifts = data.get("auto_uplifts") or []
        savage = [u for u in uplifts if u.get("source") == "savage-attacks"]
        assert not savage, (
            f"non-Half-Orc should NOT see Savage Attacks uplift; "
            f"got uplifts={uplifts}"
        )
        crit_landed = True
        break
    assert crit_landed, "no Garrik crit observed in 400 seeds"
