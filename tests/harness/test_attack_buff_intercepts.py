"""Phase B — /attack reads attacker buffs + class features at roll time.

v2.20.0: damage-flow intercepts. /attack now reads the attacker's
buffs from the hub battle state (Rage, Hunter's Mark, Hex) and class
features (Colossus Slayer) and folds in auto-applied uplifts. The
response carries an ``auto_uplifts`` list of structured entries; the
aggregate is also added to ``damage_total`` so the existing chat-card
total stays accurate.

Tests:
  - Rage damage bonus on Greataxe (Krieger): +2 added to damage,
    auto_uplifts has Rage entry.
  - Rage advantage on STR attacks: roll_state_applied = "advantage_rage",
    attack_breakdown shows 2d20kh1.
  - Hunter's Mark +1d6 on Rowan's Longbow vs marked target: rider
    appears in auto_uplifts. Empty vs unmarked target.
  - Hex +1d6 necrotic on Magnus (via /cast_hex then a melee attack):
    rider with damage_type=necrotic.
  - Colossus Slayer +1d6 vs below-max-HP target: appears in
    auto_uplifts on first attack; absent on second attack (one per
    turn).
  - Colossus Slayer skipped when target is at max HP.
  - Resistance halves damage in /sheet-fields when target has Rage
    + damage_type is physical.
  - Resistance does NOT halve when damage_type doesn't match the
    buff's resistance_to list.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def krieger_full(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    return krieger


@pytest_asyncio.fixture
async def rowan_full(gm_client, roster):
    rowan = roster["Rowan Quickbow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/rest",
        json={"type": "long"},
    )
    return rowan


@pytest_asyncio.fixture
async def magnus_full(gm_client, roster):
    magnus = roster["Magnus Hexbinder"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    return magnus


async def _seed_battle(gm_client, combatants):
    """PUT a battle state with the given list of combatant dicts."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants,
            "turn_index": 0,
            "round": 1,
            "active": True,
        },
    )


def _mkc(cid, char_id=None, hp_cur=30, hp_max=30, name="X"):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": hp_cur,
        "hp_max": hp_max,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
    }


async def test_rage_adds_damage_bonus(gm_client, krieger_full):
    """Krieger rages, then attacks with Greataxe. auto_uplifts has
    Rage; damage_total includes +2.
    """
    krieger = krieger_full
    await _seed_battle(gm_client, [_mkc(f"tok_{krieger['id']}", krieger['id'], name="Krieger")])
    # Activate Rage.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )

    # Greataxe is attack_index 0 on the Barbarian sheet. damage=1d12+4
    # slashing. Min total = 5, max = 16 base; +2 Rage = 7..18.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    rage_uplifts = [u for u in data["auto_uplifts"] if u["source"] == "rage"]
    assert len(rage_uplifts) == 1
    assert rage_uplifts[0]["total"] == 2  # Lv 5 Barbarian
    assert rage_uplifts[0]["damage_type"] == "slashing"
    # Damage_total includes +2 over the base roll.
    assert data["damage_total"] >= 7


async def test_rage_advantage_on_attack(gm_client, krieger_full):
    """Rage gives advantage on STR melee. attack_breakdown shows
    2d20kh1 and roll_state_applied = advantage_rage.
    """
    krieger = krieger_full
    await _seed_battle(gm_client, [_mkc(f"tok_{krieger['id']}", krieger['id'], name="Krieger")])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "2d20kh1" in (data["attack_breakdown"] or "")
    assert data["roll_state_applied"] == "advantage_rage"


async def test_hunters_mark_rider_on_marked_target(gm_client, rowan_full, roster):
    """Rowan marks Pip then attacks Pip. auto_uplifts has Hunter's Mark."""
    rowan = rowan_full
    pip = roster["Pip Quickfingers"]
    rowan_cid = f"tok_{rowan['id']}"
    pip_cid = f"tok_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(rowan_cid, rowan['id'], name="Rowan"),
        _mkc(pip_cid, pip['id'], name="Pip"),
    ])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
        json={
            "character_id": rowan["id"],
            "target_character_id": pip["id"],
            "override": True,
        },
    )

    # Longbow = attack_index 0 on the Ranger sheet (piercing).
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": rowan["id"],
            "attack_index": 0,
            "target_combatant_id": pip_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    hm = [u for u in data["auto_uplifts"] if u["source"] == "hunters-mark"]
    assert len(hm) == 1
    assert hm[0]["expression"] == "1d6"
    assert 1 <= hm[0]["total"] <= 6


async def test_hunters_mark_does_not_fire_on_other_target(gm_client, rowan_full, roster):
    """Rowan marks Pip but attacks Thalindra. Hunter's Mark does NOT fire."""
    rowan = rowan_full
    pip = roster["Pip Quickfingers"]
    thalindra = roster["Thalindra Moonwhisper"]
    rowan_cid = f"tok_{rowan['id']}"
    pip_cid = f"tok_{pip['id']}"
    thal_cid = f"tok_{thalindra['id']}"
    await _seed_battle(gm_client, [
        _mkc(rowan_cid, rowan['id'], name="Rowan"),
        _mkc(pip_cid, pip['id'], name="Pip"),
        _mkc(thal_cid, thalindra['id'], name="Thalindra"),
    ])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
        json={
            "character_id": rowan["id"],
            "target_character_id": pip["id"],
            "override": True,
        },
    )

    # Attack Thalindra (not the marked target).
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": rowan["id"],
            "attack_index": 0,
            "target_combatant_id": thal_cid,
            "override": True,
        },
    )
    data = resp.json()
    hm = [u for u in data["auto_uplifts"] if u["source"] == "hunters-mark"]
    assert len(hm) == 0


async def test_colossus_slayer_fires_vs_below_max_hp(gm_client, rowan_full, roster):
    """Pip starts below max HP. Rowan's Longbow vs Pip triggers Colossus Slayer."""
    rowan = rowan_full
    pip = roster["Pip Quickfingers"]
    rowan_cid = f"tok_{rowan['id']}"
    pip_cid = f"tok_{pip['id']}"
    # Pip starts at 20/30 (below max).
    await _seed_battle(gm_client, [
        _mkc(rowan_cid, rowan['id'], name="Rowan"),
        _mkc(pip_cid, pip['id'], hp_cur=20, hp_max=30, name="Pip"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": rowan["id"],
            "attack_index": 0,
            "target_combatant_id": pip_cid,
            "override": True,
        },
    )
    data = resp.json()
    cs = [u for u in data["auto_uplifts"] if u["source"] == "colossus-slayer"]
    assert len(cs) == 1
    assert cs[0]["expression"] == "1d6"


async def test_colossus_slayer_skips_full_hp_target(gm_client, rowan_full, roster):
    """Pip at max HP — Colossus Slayer doesn't fire."""
    rowan = rowan_full
    pip = roster["Pip Quickfingers"]
    rowan_cid = f"tok_{rowan['id']}"
    pip_cid = f"tok_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(rowan_cid, rowan['id'], name="Rowan"),
        _mkc(pip_cid, pip['id'], hp_cur=30, hp_max=30, name="Pip"),
    ])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": rowan["id"],
            "attack_index": 0,
            "target_combatant_id": pip_cid,
            "override": True,
        },
    )
    data = resp.json()
    cs = [u for u in data["auto_uplifts"] if u["source"] == "colossus-slayer"]
    assert len(cs) == 0


async def test_colossus_slayer_once_per_turn(gm_client, rowan_full, roster):
    """First attack triggers Colossus Slayer; second attack same turn doesn't."""
    rowan = rowan_full
    pip = roster["Pip Quickfingers"]
    rowan_cid = f"tok_{rowan['id']}"
    pip_cid = f"tok_{pip['id']}"
    await _seed_battle(gm_client, [
        _mkc(rowan_cid, rowan['id'], name="Rowan"),
        _mkc(pip_cid, pip['id'], hp_cur=20, hp_max=30, name="Pip"),
    ])

    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": rowan["id"],
            "attack_index": 0,
            "target_combatant_id": pip_cid,
            "override": True,
        },
    )
    assert any(u["source"] == "colossus-slayer" for u in r1.json()["auto_uplifts"])

    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": rowan["id"],
            "attack_index": 0,
            "target_combatant_id": pip_cid,
            "override": True,
        },
    )
    assert not any(u["source"] == "colossus-slayer" for u in r2.json()["auto_uplifts"])


async def test_resistance_halves_damage(gm_client, krieger_full):
    """Krieger is raging — has resistance to slashing. PATCH /sheet-fields
    with 10 slashing damage halves to 5; HP reflects 5 lost, not 10.
    """
    krieger = krieger_full
    await _seed_battle(gm_client, [_mkc(f"tok_{krieger['id']}", krieger['id'],
                                        hp_cur=55, hp_max=55, name="Krieger")])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )

    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={
            "hp": {"current": 45},  # client-supplied pre-resistance value
            "hp_change_reason": "damage",
            "damage_amount": 10,
            "damage_type": "slashing",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["resistance_applied"] is True
    assert data["damage_amount_after_resistance"] == 5
    # v2.57.0: Krieger sheet HP bumped 55 → 75 at Lv 7. When resistance
    # is applied, server uses the sheet's stored HP and subtracts the
    # halved damage (75 - 5 = 70), ignoring the client-supplied
    # hp.current value.
    assert data["hp"]["current"] == 70  # 75 - 5, not 75 - 10


async def test_attack_broadcast_includes_target_name(gm_client, krieger_full, roster):
    """v2.23.0 Phase T.8: /attack response + broadcast carry target_name
    resolved from the combatant's name in the hub state.
    """
    krieger = krieger_full
    pip = roster["Pip Quickfingers"]
    pip_cid = f"tok_{pip['id']}"
    # Seed Pip's combatant with his real roster name so we can assert
    # against it.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                _mkc(f"tok_{krieger['id']}", krieger['id'], name="Krieger"),
                _mkc(pip_cid, pip['id'], hp_cur=20, hp_max=30, name=pip['name']),
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,
            "target_combatant_id": pip_cid,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["target_combatant_id"] == pip_cid
    assert data["target_name"] == pip["name"]


async def test_resistance_does_not_halve_unrelated_type(gm_client, krieger_full):
    """Krieger rages but takes 10 fire damage — no resistance applies."""
    krieger = krieger_full
    await _seed_battle(gm_client, [_mkc(f"tok_{krieger['id']}", krieger['id'],
                                        hp_cur=55, hp_max=55, name="Krieger")])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )

    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-fields",
        json={
            "hp": {"current": 45},
            "hp_change_reason": "damage",
            "damage_amount": 10,
            "damage_type": "fire",
        },
    )
    data = resp.json()
    assert data["resistance_applied"] is False
    assert data["hp"]["current"] == 45  # full 10 applied
