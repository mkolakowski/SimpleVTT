"""v2.99.94 — Divine Strike for non-Life domains.

v2.60.0 wired Life Domain only (1d8 radiant). v2.99.94 extends to
the seven other Divine-Strike-bearing domains via a subclass →
damage_type map:

    Life      → radiant
    Tempest   → thunder
    Trickery  → poison
    War       → weapon's damage type (None in the map; falls back
                to attack_damage_type)
    Death     → necrotic
    Nature    → fire (DM choice; v1 picks fire)
    Forge     → fire
    Twilight  → radiant

The once-per-turn lock (via `economy.divine_strike_used`) and the
1d8/2d8 dice scaling (Lv 8-13/14+) carry over from v2.60.0
unchanged.

Tests PATCH Tavik (Cleric Lv 6 Life Domain) to each new subclass +
bump him to Lv 8 to clear the Divine Strike gate. Tavik's
Warhammer (1d8 bludgeoning) is the attack — War Domain uses the
weapon's bludgeoning type; others use the mapped flavor type.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def tavik_at_lv_8(gm_client, roster):
    """Bump Tavik to Lv 8 (the Divine Strike unlock level) +
    long-rest. Restores Lv 6 + 'Life Domain' subclass in teardown.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"class_slug": "cleric", "level": 8},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    yield tavik
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={
            "class_slug": "cleric", "level": 6,
            "subclass": "Life Domain",
        },
    )


def _mkc(cid, char_id=None, hp_cur=50, hp_max=75, name="X"):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur, "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def _try_attack_until_hit(
    gm_client, tavik_id, krieger_tok,
):
    """Loop Warhammer attacks until one lands. Returns the auto_uplifts
    list from the first hit, or None if no hit across 10 attempts.
    """
    for _ in range(10):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik_id,
                "attack_index": 0,
                "target_combatant_id": krieger_tok,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data.get("hit"):
            return data.get("auto_uplifts") or []
    return None


async def _run_domain_test(
    gm_client, tavik, krieger, subclass, expected_dmg_type,
):
    """Shared body — PATCH Tavik to the requested subclass, seed
    battle, attack, assert the divine-strike uplift uses the
    expected damage type.
    """
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"subclass": subclass},
    )
    tavik_tok = f"tok_dsd_{tavik['id']}"
    krieger_tok = f"tok_dsd_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(tavik_tok, tavik["id"], name=tavik["name"]),
        _mkc(krieger_tok, krieger["id"], name=krieger["name"],
             hp_cur=50, hp_max=75),
    ])
    uplifts = await _try_attack_until_hit(gm_client, tavik["id"], krieger_tok)
    assert uplifts is not None, (
        f"{subclass}: Warhammer didn't hit Krieger in 10 tries"
    )
    ds = next((u for u in uplifts if u.get("source") == "divine-strike"), None)
    assert ds is not None, (
        f"{subclass}: expected divine-strike uplift on hit; "
        f"got uplifts={uplifts}"
    )
    assert ds.get("damage_type") == expected_dmg_type, (
        f"{subclass}: expected damage_type={expected_dmg_type!r}; "
        f"got {ds!r}"
    )
    assert ds.get("expression") == "1d8", ds


async def test_divine_strike_tempest_thunder(gm_client, tavik_at_lv_8, roster):
    """Tempest Domain → 1d8 thunder."""
    await _run_domain_test(
        gm_client, tavik_at_lv_8, roster["Krieger Stonefist"],
        "Tempest Domain", "thunder",
    )


async def test_divine_strike_trickery_poison(gm_client, tavik_at_lv_8, roster):
    """Trickery Domain → 1d8 poison."""
    await _run_domain_test(
        gm_client, tavik_at_lv_8, roster["Krieger Stonefist"],
        "Trickery Domain", "poison",
    )


async def test_divine_strike_death_necrotic(gm_client, tavik_at_lv_8, roster):
    """Death Domain → 1d8 necrotic."""
    await _run_domain_test(
        gm_client, tavik_at_lv_8, roster["Krieger Stonefist"],
        "Death Domain", "necrotic",
    )


async def test_divine_strike_nature_fire(gm_client, tavik_at_lv_8, roster):
    """Nature Domain → 1d8 fire (DM choice in RAW; v1 picks fire)."""
    await _run_domain_test(
        gm_client, tavik_at_lv_8, roster["Krieger Stonefist"],
        "Nature Domain", "fire",
    )


async def test_divine_strike_forge_fire(gm_client, tavik_at_lv_8, roster):
    """Forge Domain → 1d8 fire."""
    await _run_domain_test(
        gm_client, tavik_at_lv_8, roster["Krieger Stonefist"],
        "Forge Domain", "fire",
    )


async def test_divine_strike_twilight_radiant(gm_client, tavik_at_lv_8, roster):
    """Twilight Domain → 1d8 radiant."""
    await _run_domain_test(
        gm_client, tavik_at_lv_8, roster["Krieger Stonefist"],
        "Twilight Domain", "radiant",
    )


async def test_divine_strike_order_psychic(gm_client, tavik_at_lv_8, roster):
    """v2.99.278 — Order Domain → 1d8 psychic (XGE p.39)."""
    await _run_domain_test(
        gm_client, tavik_at_lv_8, roster["Krieger Stonefist"],
        "Order Domain", "psychic",
    )


async def test_divine_strike_war_uses_weapon_damage_type(
    gm_client, tavik_at_lv_8, roster,
):
    """War Domain → 1d8 of the weapon's damage type. Tavik's
    Warhammer is bludgeoning; the divine-strike damage_type should
    match.
    """
    await _run_domain_test(
        gm_client, tavik_at_lv_8, roster["Krieger Stonefist"],
        "War Domain", "bludgeoning",
    )


async def test_divine_strike_skipped_for_non_strike_domain(
    gm_client, tavik_at_lv_8, roster,
):
    """Light Domain doesn't have Divine Strike (it has Potent
    Spellcasting). Switching Tavik to Light → no uplift fires.
    """
    tavik = tavik_at_lv_8
    krieger = roster["Krieger Stonefist"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"subclass": "Light Domain"},
    )
    tavik_tok = f"tok_dsd_light_{tavik['id']}"
    krieger_tok = f"tok_dsd_light_{krieger['id']}"
    await _seed_battle(gm_client, [
        _mkc(tavik_tok, tavik["id"], name=tavik["name"]),
        _mkc(krieger_tok, krieger["id"], name=krieger["name"],
             hp_cur=50, hp_max=75),
    ])
    uplifts = await _try_attack_until_hit(gm_client, tavik["id"], krieger_tok)
    assert uplifts is not None, "Warhammer didn't hit"
    ds = next((u for u in uplifts if u.get("source") == "divine-strike"), None)
    assert ds is None, (
        f"Light Domain should NOT trigger Divine Strike; got {ds!r}"
    )
