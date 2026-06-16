"""v2.361.0 — magic-items: Oathbow (RAW DMG p.183, very rare,
attunement, longbow). Bucket-C conditional attack rider off the
v2.344.5 stub triage. The first item on the NEW `condition_sworn_enemy`
predicate (special-cased in `_compute_attack_auto_uplifts` section 6c):
on a hit vs the wielder's DECLARED sworn enemy the rider adds +3d6
piercing AND the d20 attack roll gets advantage (via the existing
v2.158.53 `_attacker_has_vow_of_enmity_vs_target` reader, which walks
the attacker's buffs for the generic `attack_advantage_vs_target_
combatant_id` marker — not key-gated, so it lights up for Oathbow's
buff with zero new attack-roll code).

Demo fixture: Rowan Quickbow carries the Oathbow at attack_index 4 +
inventory tail, seeded INERT. Tests PATCH the inventory equipped +
attuned, POST `/declare_oathbow_sworn_enemy` to install the sworn-
enemy buff, run the rider assertion, then restore. Targets are real
**Bandit** NPC templates.

Tests:
  - `/declare_oathbow_sworn_enemy` installs the `oathbow-sworn-enemy`
    buff on the wielder carrying both effect markers.
  - The rider fires (+3d6 piercing) on a hit vs the declared sworn
    enemy.
  - The rider stays silent on a hit vs a NON-sworn target (the
    `condition_sworn_enemy` predicate gates correctly).
  - The d20 attack roll uses 2d20kh1 (advantage) vs the sworn enemy
    via the existing Vow-of-Enmity attack-adv reader.
  - Declare without an equipped+attuned Oathbow → 409
    `oathbow_not_equipped_attuned`.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


ROWAN_OATHBOW_ATTACK_IDX = 4
_OATHBOW_SLUG = "oathbow"
_SWORN_BUFF_KEY = "oathbow-sworn-enemy"


def _mkc(cid, char_id=None, name="X", token_template_id=None,
         creature_type="humanoid", ac=1, hp_max=200):
    c = {
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
    if token_template_id is not None:
        c["token_template_id"] = token_template_id
    return c


async def _seed_battle(gm_client, combatants):
    return await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _snapshot_inv(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    inv = list(((resp.json() or {}).get("sheet") or {}).get("inventory") or [])
    return [dict(it) if isinstance(it, dict) else it for it in inv]


async def _patch_inv(gm_client, char_id, *, equipped, attuned):
    snapshot = await _snapshot_inv(gm_client, char_id)
    new_inv = [dict(it) if isinstance(it, dict) else it for it in snapshot]
    found = False
    for it in new_inv:
        if isinstance(it, dict) and it.get("_slug") == _OATHBOW_SLUG:
            it["equipped"] = equipped
            it["attuned"] = attuned
            found = True
    assert found, "Rowan has no oathbow inventory item"
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": new_inv},
    )
    assert resp.status_code == 200, resp.text
    return snapshot


async def _restore_inv(gm_client, char_id, snapshot):
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"inventory": snapshot},
    )


async def _bandit_template_id(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert r.status_code == 200, r.text
    bandit = next((t for t in r.json() if t.get("name") == "Bandit"), None)
    assert bandit is not None, "Bandit template missing from the demo seed"
    return bandit["id"]


def _uplifts(data, source):
    return [u for u in (data.get("auto_uplifts") or [])
            if u.get("source") == source]


async def _declare(gm_client, char_id, target_cid):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/declare_oathbow_sworn_enemy",
        json={"target_combatant_id": target_cid},
    )


@pytest_asyncio.fixture
async def rowan(roster):
    return roster["Rowan Quickbow"]


async def test_declare_installs_sworn_enemy_buff(gm_client, rowan):
    """POST /declare_oathbow_sworn_enemy installs the `oathbow-sworn-enemy`
    buff on Rowan's combatant carrying both effect markers."""
    snap = await _patch_inv(
        gm_client, rowan["id"], equipped=True, attuned=True,
    )
    try:
        template_id = await _bandit_template_id(gm_client)
        rowan_cid = f"tok_oath_decl_rowan_{rowan['id']}"
        target_cid = "tok_oath_decl_target"
        await _seed_battle(gm_client, [
            _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
            _mkc(target_cid, None, name="Bandit",
                 token_template_id=template_id),
        ])
        resp = await _declare(gm_client, rowan["id"], target_cid)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("feature") == "oathbow-sworn-enemy"
        assert body.get("target_combatant_id") == target_cid

        battle = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
        combs = ((battle.json() or {}).get("battle") or {}).get("combatants") or []
        me = next((c for c in combs if c.get("id") == rowan_cid), None)
        assert me is not None
        sworn = next(
            (b for b in (me.get("buffs") or [])
             if isinstance(b, dict) and b.get("key") == _SWORN_BUFF_KEY),
            None,
        )
        assert sworn is not None, f"oathbow-sworn-enemy buff missing: {me.get('buffs')!r}"
        eff = sworn.get("effects") or {}
        assert str(eff.get("oathbow_sworn_enemy_id") or "") == target_cid
        assert str(eff.get("attack_advantage_vs_target_combatant_id") or "") == target_cid
    finally:
        await _restore_inv(gm_client, rowan["id"], snap)


async def test_rider_fires_on_sworn_enemy(gm_client, rowan):
    """A hit vs the declared sworn enemy with Oathbow surfaces the +3d6
    piercing uplift (source `item-oathbow`). Exercises the new
    `condition_sworn_enemy` section-6c predicate."""
    snap = await _patch_inv(
        gm_client, rowan["id"], equipped=True, attuned=True,
    )
    try:
        template_id = await _bandit_template_id(gm_client)
        rowan_cid = f"tok_oath_fire_rowan_{rowan['id']}"
        target_cid = "tok_oath_fire_target"
        await _seed_battle(gm_client, [
            _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
            _mkc(target_cid, None, name="Bandit",
                 token_template_id=template_id),
        ])
        decl = await _declare(gm_client, rowan["id"], target_cid)
        assert decl.status_code == 200, decl.text

        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": rowan["id"],
                "attack_index": ROWAN_OATHBOW_ATTACK_IDX,
                "target_combatant_id": target_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("attack_name") == "Oathbow"
        ups = _uplifts(data, "item-oathbow")
        assert len(ups) == 1, data.get("auto_uplifts")
        rider = ups[0]
        assert rider["label"] == "Oathbow"
        assert rider["expression"] == "3d6"
        assert rider["damage_type"] == "piercing"
        # Non-crit 3d6 → [3, 18]; crit-doubled 6d6 → [6, 36].
        assert 3 <= rider["total"] <= 36
    finally:
        await _restore_inv(gm_client, rowan["id"], snap)


async def test_rider_silent_on_non_sworn_target(gm_client, rowan):
    """A hit vs a target who is NOT the declared sworn enemy → no rider.
    The `condition_sworn_enemy` predicate blocks the +3d6 piercing on
    the off-target combatant."""
    snap = await _patch_inv(
        gm_client, rowan["id"], equipped=True, attuned=True,
    )
    try:
        template_id = await _bandit_template_id(gm_client)
        rowan_cid = f"tok_oath_off_rowan_{rowan['id']}"
        sworn_cid = "tok_oath_off_sworn"
        other_cid = "tok_oath_off_other"
        await _seed_battle(gm_client, [
            _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
            _mkc(sworn_cid, None, name="Bandit (Sworn)",
                 token_template_id=template_id),
            _mkc(other_cid, None, name="Bandit (Other)",
                 token_template_id=template_id),
        ])
        decl = await _declare(gm_client, rowan["id"], sworn_cid)
        assert decl.status_code == 200, decl.text

        # Attack the OTHER bandit (not the sworn enemy).
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": rowan["id"],
                "attack_index": ROWAN_OATHBOW_ATTACK_IDX,
                "target_combatant_id": other_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        ups = _uplifts(resp.json(), "item-oathbow")
        assert ups == [], (
            f"Oathbow rider fired vs non-sworn target; got {ups!r}"
        )
    finally:
        await _restore_inv(gm_client, rowan["id"], snap)


async def test_attack_has_advantage_vs_sworn_enemy(gm_client, rowan):
    """The d20 attack roll vs the sworn enemy uses 2d20kh1 — granted by
    the existing v2.158.53 `_attacker_has_vow_of_enmity_vs_target` reader
    walking Oathbow's buff for the generic `attack_advantage_vs_target_
    combatant_id` marker."""
    snap = await _patch_inv(
        gm_client, rowan["id"], equipped=True, attuned=True,
    )
    try:
        template_id = await _bandit_template_id(gm_client)
        rowan_cid = f"tok_oath_adv_rowan_{rowan['id']}"
        target_cid = "tok_oath_adv_target"
        await _seed_battle(gm_client, [
            _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
            _mkc(target_cid, None, name="Bandit",
                 token_template_id=template_id),
        ])
        decl = await _declare(gm_client, rowan["id"], target_cid)
        assert decl.status_code == 200, decl.text

        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": rowan["id"],
                "attack_index": ROWAN_OATHBOW_ATTACK_IDX,
                "target_combatant_id": target_cid,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        adv_state = (data.get("attack_roll_state_applied") or "")
        breakdown = (data.get("attack_breakdown") or "")
        assert "vow_of_enmity" in adv_state or "2d20kh1" in breakdown, (
            f"expected advantage on the d20 attack roll vs sworn enemy; "
            f"got state={adv_state!r}, breakdown={breakdown!r}"
        )
    finally:
        await _restore_inv(gm_client, rowan["id"], snap)


async def test_declare_without_equipped_attuned_returns_409(gm_client, rowan):
    """Calling /declare_oathbow_sworn_enemy while the Oathbow inventory
    item is NOT both equipped AND attuned → 409
    `oathbow_not_equipped_attuned`."""
    snap = await _patch_inv(
        gm_client, rowan["id"], equipped=True, attuned=False,
    )
    try:
        template_id = await _bandit_template_id(gm_client)
        rowan_cid = f"tok_oath_noatt_rowan_{rowan['id']}"
        target_cid = "tok_oath_noatt_target"
        await _seed_battle(gm_client, [
            _mkc(rowan_cid, rowan["id"], name=rowan["name"]),
            _mkc(target_cid, None, name="Bandit",
                 token_template_id=template_id),
        ])
        resp = await _declare(gm_client, rowan["id"], target_cid)
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body.get("error") == "oathbow_not_equipped_attuned"
    finally:
        await _restore_inv(gm_client, rowan["id"], snap)
