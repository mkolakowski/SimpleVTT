"""v2.1014.0 — Quivering Palm (Way of the Open Hand Monk Lv 17+).

PHB p.79, a two-step feature:
  - setup: spend 3 ki to set lethal vibrations on a target (one at a
    time), riding an unarmed-strike hit.
  - trigger: use your action to end them — the target makes a CON save;
    fail → drops to 0 HP, success → 10d10 necrotic.

Way of the Open Hand is the SRD monk subclass, so Quivering Palm is
SRD-valid. Kael Brightleaf (Monk Open Hand Lv 5) is the demo fixture,
PATCH'd to Lv 17. The trigger marks the action chip, so the trigger
tests pass ``override: true`` per the harness contract.

Tests:
  - setup: spends 3 ki + installs the ☠️ quivering-palm buff on the
    target (asserted via GET /battle).
  - trigger: resolves the CON save; on fail the target is at 0 HP, on
    success 10d10 necrotic is applied; the buff is consumed either way.
  - trigger without setup → 409 not_set_up.
  - setup with < 3 ki → 409 out_of_uses.
  - level gate: Kael@Lv5 → 409.
  - error paths: bad mode → 400; missing target → 400; unknown char → 404.
"""
import asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


async def _set_ki(gm_client, char_id, value):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    resources = (r.json().get("sheet") or {}).get("resources") or []
    for res in resources:
        if (res.get("key") or "").lower() == "ki":
            res["current"] = value
    await _patch_sheet(gm_client, char_id, {"resources": resources})


def _pc(cid, c, *, hp_max=140):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


def _npc(cid, name, *, hp=60):
    return {"id": cid, "char_id": None, "name": name,
            "initiative": 5, "hp_current": hp, "hp_max": hp, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed(gm_client, kael, target_id, *, target_hp=60):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _pc(f"tok_qp_kael_{kael['id']}", kael),
            _npc(target_id, "Bandit", hp=target_hp),
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def _battle_combatants(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    return ((r.json().get("battle") or {}).get("combatants") or [])


async def _target_buff_keys(gm_client, target_id):
    for c in await _battle_combatants(gm_client):
        if c.get("id") == target_id:
            return [b.get("key") for b in (c.get("buffs") or [])]
    return []


async def _target_hp(gm_client, target_id):
    for c in await _battle_combatants(gm_client):
        if c.get("id") == target_id:
            return int(c.get("hp_current") or 0)
    return None  # combatant removed (e.g. a defeated NPC dropped to 0)


async def test_quivering_palm_setup_spends_ki_and_marks_target(
    gm_client, roster,
):
    """Kael@Lv17 setup → 3 ki spent + the ☠️ quivering-palm buff on the
    target."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(gm_client, kael["id"], {"level": 17},
                       class_slug="monk")
    try:
        await _set_ki(gm_client, kael["id"], 10)
        target_id = f"tok_qp_b1_{kael['id']}"
        await _seed(gm_client, kael, target_id)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_quivering_palm",
            json={"character_id": kael["id"],
                  "target_combatant_id": target_id, "mode": "setup"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["phase"] == "setup"
        assert data["ki_remaining"] == 7  # 10 - 3
        assert data["save_dc"] >= 8
        assert "quivering-palm" in await _target_buff_keys(gm_client, target_id)
    finally:
        await _patch_sheet(gm_client, kael["id"], {"level": 5},
                           class_slug="monk")


async def test_quivering_palm_trigger_resolves_save(gm_client, roster):
    """After setup, trigger (override) resolves the CON save: on fail the
    target is at 0 HP; on success 10d10 necrotic; the buff is consumed."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(gm_client, kael["id"], {"level": 17},
                       class_slug="monk")
    try:
        await _set_ki(gm_client, kael["id"], 10)
        target_id = f"tok_qp_b2_{kael['id']}"
        await _seed(gm_client, kael, target_id, target_hp=60)
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_quivering_palm",
            json={"character_id": kael["id"],
                  "target_combatant_id": target_id, "mode": "setup"},
        )
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_quivering_palm",
            json={"character_id": kael["id"],
                  "target_combatant_id": target_id, "mode": "trigger",
                  "override": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["phase"] == "trigger"
        assert isinstance(data["save_passed"], bool)
        await asyncio.sleep(0.2)
        hp = await _target_hp(gm_client, target_id)
        if data["save_passed"]:
            # 10d10 necrotic (may or may not drop a 60-HP bandit).
            assert data["damage_applied"] >= 0
            assert data["dropped_to_0"] is False
        else:
            assert data["dropped_to_0"] is True
            # A defeated NPC is at 0 HP or removed from the tracker.
            assert hp in (0, None)
        # The buff is consumed either way.
        assert "quivering-palm" not in await _target_buff_keys(
            gm_client, target_id)
    finally:
        await _patch_sheet(gm_client, kael["id"], {"level": 5},
                           class_slug="monk")


async def test_quivering_palm_trigger_without_setup(gm_client, roster):
    """Trigger with no vibrations set → 409 not_set_up."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(gm_client, kael["id"], {"level": 17},
                       class_slug="monk")
    try:
        target_id = f"tok_qp_b3_{kael['id']}"
        await _seed(gm_client, kael, target_id)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_quivering_palm",
            json={"character_id": kael["id"],
                  "target_combatant_id": target_id, "mode": "trigger",
                  "override": True},
        )
        assert r.status_code == 409, r.text
        assert r.json().get("error") == "not_set_up"
    finally:
        await _patch_sheet(gm_client, kael["id"], {"level": 5},
                           class_slug="monk")


async def test_quivering_palm_setup_out_of_ki(gm_client, roster):
    """Setup with < 3 ki → 409 out_of_uses."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(gm_client, kael["id"], {"level": 17},
                       class_slug="monk")
    try:
        await _set_ki(gm_client, kael["id"], 2)
        target_id = f"tok_qp_b4_{kael['id']}"
        await _seed(gm_client, kael, target_id)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_quivering_palm",
            json={"character_id": kael["id"],
                  "target_combatant_id": target_id, "mode": "setup"},
        )
        assert r.status_code == 409, r.text
        assert r.json().get("error") == "out_of_uses"
    finally:
        await _set_ki(gm_client, kael["id"], 7)
        await _patch_sheet(gm_client, kael["id"], {"level": 5},
                           class_slug="monk")


async def test_quivering_palm_level_gate(gm_client, roster):
    """Kael at Lv 5 → 409 (Quivering Palm needs Lv 17)."""
    kael = roster["Kael Brightleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_quivering_palm",
        json={"character_id": kael["id"],
              "target_combatant_id": "tok_x", "mode": "setup"},
    )
    assert r.status_code == 409, r.text
    assert r.json().get("error") == "wrong_subclass_or_level"


async def test_quivering_palm_bad_mode(gm_client, roster):
    kael = roster["Kael Brightleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_quivering_palm",
        json={"character_id": kael["id"],
              "target_combatant_id": "tok_x", "mode": "bogus"},
    )
    assert r.status_code == 400, r.text


async def test_quivering_palm_missing_target(gm_client, roster):
    kael = roster["Kael Brightleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_quivering_palm",
        json={"character_id": kael["id"], "mode": "setup"},
    )
    assert r.status_code == 400, r.text


async def test_quivering_palm_unknown_character(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_quivering_palm",
        json={"character_id": 99999999,
              "target_combatant_id": "tok_x", "mode": "setup"},
    )
    assert r.status_code == 404, r.text
