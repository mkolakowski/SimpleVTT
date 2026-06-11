"""v2.158.104 — magic-items-automation Phase 7d: Sun Blade +1d8
radiant vs. undead (RAW DMG p.205). Pure substrate composition —
reuses the v2.158.93 conditional-rider shape (dice + condition
predicate keyed on creature_type=undead). The bright-light bonus
action / "lit" flavor isn't modeled v1 since RAW: the +1d8 vs.
undead always fires while attuned, lit or not.

Demo fixture: Dame Seraphine Vael (Vengeance Paladin Lv 3) gets a
Sun Blade Longsword at attack_index 2 + inventory_index 5,
equipped + attuned. RAW +2 attack/damage baked in (+5/1d8+5 →
+7/1d8+7), damage_type flipped to "radiant" per RAW. Skeleton NPC
template (already in seed) extended with sheet.type="undead" so the
v2.158.96 Phase 5f helper resolution auto-fires the rider on attacks
against drag-spawned skeletons.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


SERAPHINE_SUN_BLADE_ATTACK_IDX = 2
SERAPHINE_SUN_BLADE_INV_IDX = 5


def _uplifts(data, source):
    return [u for u in (data.get("auto_uplifts") or [])
            if u.get("source") == source]


def _mkc(cid, char_id=None, name="X", creature_type="", ac=1, hp_max=200):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_max, "hp_max": hp_max,
        "ac": ac,
        "buffs": [],
        "creature_type": creature_type,
        "speed_walk": 30,
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def seraphine(roster):
    return roster["Dame Seraphine Vael"]


async def test_sun_blade_fires_on_undead_target(gm_client, seraphine):
    """v2.158.104 happy path. Attacking a target with
    ``creature_type: "undead"`` surfaces a +1d8 radiant uplift from
    the Sun Blade. Damage type is radiant (declared on the catalog
    row, not the weapon-type fallback)."""
    seraphine_cid = f"tok_sun1_seraphine_{seraphine['id']}"
    skeleton_cid = "tok_sun1_skeleton"
    await _seed_battle(gm_client, [
        _mkc(seraphine_cid, seraphine["id"], name=seraphine["name"]),
        _mkc(skeleton_cid, None, name="Skeleton", creature_type="undead"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": seraphine["id"],
            "attack_index": SERAPHINE_SUN_BLADE_ATTACK_IDX,
            "target_combatant_id": skeleton_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["attack_name"] == "Sun Blade"

    ups = _uplifts(data, "item-sun-blade")
    assert len(ups) == 1, data.get("auto_uplifts")
    rider = ups[0]
    assert rider["label"] == "Sun Blade"
    assert rider["expression"] == "1d8"
    assert rider["damage_type"] == "radiant"
    # Non-crit 1d8 → [1, 8]; crit-doubled 2d8 → [2, 16].
    assert 1 <= rider["total"] <= 16


async def test_sun_blade_silent_on_humanoid(gm_client, seraphine):
    """v2.158.104 negative case. Attacking a non-undead target →
    no rider. The condition predicate `creature_type == "undead"`
    blocks the uplift."""
    seraphine_cid = f"tok_sun2_seraphine_{seraphine['id']}"
    bandit_cid = "tok_sun2_bandit"
    await _seed_battle(gm_client, [
        _mkc(seraphine_cid, seraphine["id"], name=seraphine["name"]),
        _mkc(bandit_cid, None, name="Bandit", creature_type="humanoid"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": seraphine["id"],
            "attack_index": SERAPHINE_SUN_BLADE_ATTACK_IDX,
            "target_combatant_id": bandit_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    ups = _uplifts(resp.json(), "item-sun-blade")
    assert ups == [], (
        f"Sun Blade must not fire vs. humanoid; got {ups!r}"
    )


async def test_sun_blade_suppressed_when_detuned(gm_client, seraphine):
    """v2.158.104: detuning the Sun Blade suppresses the rider even
    on an undead target. Restores attunement in teardown."""
    detune = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{seraphine['id']}/attune",
        json={"inventory_index": SERAPHINE_SUN_BLADE_INV_IDX, "attuned": False},
    )
    assert detune.status_code == 200, detune.text

    try:
        seraphine_cid = f"tok_sun3_seraphine_{seraphine['id']}"
        skeleton_cid = "tok_sun3_skeleton"
        await _seed_battle(gm_client, [
            _mkc(seraphine_cid, seraphine["id"], name=seraphine["name"]),
            _mkc(skeleton_cid, None, name="Skeleton", creature_type="undead"),
        ])
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": seraphine["id"],
                "attack_index": SERAPHINE_SUN_BLADE_ATTACK_IDX,
                "target_combatant_id": skeleton_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        ups = _uplifts(resp.json(), "item-sun-blade")
        assert ups == [], (
            "Detuned Sun Blade must not fire even vs. undead; "
            f"got {ups!r}"
        )
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{seraphine['id']}/attune",
            json={"inventory_index": SERAPHINE_SUN_BLADE_INV_IDX,
                  "attuned": True},
        )


async def test_sun_blade_fires_via_skeleton_template(gm_client, seraphine):
    """v2.158.104: Skeleton NPC template's sheet.type='undead'
    auto-resolves the creature_type via the v2.158.96 Phase 5f
    helper — no need to set creature_type on the combatant dict
    explicitly. Mirror of test_dragon_slayer_template's path."""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert r.status_code == 200, r.text
    templates = r.json()
    skel = next((t for t in templates if t.get("name") == "Skeleton"), None)
    assert skel is not None, "Skeleton template missing"
    assert (skel.get("sheet") or {}).get("type") == "undead", (
        f"Skeleton template should be type='undead'; got "
        f"{(skel.get('sheet') or {}).get('type')!r}"
    )
    template_id = skel["id"]

    seraphine_cid = f"tok_sun4_seraphine_{seraphine['id']}"
    skeleton_cid = "tok_sun4_skel"
    await _seed_battle(gm_client, [
        _mkc(seraphine_cid, seraphine["id"], name=seraphine["name"]),
        {
            "id": skeleton_cid,
            "char_id": None,
            "name": "Skeleton",
            "token_template_id": template_id,
            "initiative": 8,
            "hp_current": 200, "hp_max": 200, "ac": 1,
            "buffs": [],
            # NO creature_type — exercise helper resolution branch.
            "speed_walk": 30,
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        },
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": seraphine["id"],
            "attack_index": SERAPHINE_SUN_BLADE_ATTACK_IDX,
            "target_combatant_id": skeleton_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    ups = _uplifts(resp.json(), "item-sun-blade")
    assert len(ups) == 1, (
        "Template-resolved creature_type=undead must trigger Sun "
        f"Blade rider; auto_uplifts={resp.json().get('auto_uplifts')}"
    )
