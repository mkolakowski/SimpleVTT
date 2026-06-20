"""Lesser Restoration — L2 abjuration,
Bard/Cleric/Druid/Paladin/Ranger. Phase 2 #19 of
``docs/plans/cast-and-broadcast-tail.md``.

v2.462.0 — RAW PHB p.255: "You touch a creature and can end
either one disease or one condition afflicting it. The condition
can be blinded, deafened, paralyzed, or poisoned." 1 action,
V/S, Touch, Instantaneous.

**Second mechanical non-buff cast in the Phase 2 arc** (after
Spare the Dying v2.461.0). The endpoint calls the existing
``_remove_buff(target, condition_key)`` helper and broadcasts a
``feature_used`` card naming what was cured.

Tests:
  - Install paralyzed on Krieger → cast Lesser Restoration with
    condition_key="paralyzed" → buff removed; response.removed=True.
  - Condition not present (no paralyzed buff) → 409
    condition_not_present.
  - Invalid condition_key → 400.
  - Missing target_character_id → 400.
  - Krieger (Barbarian) caster → 409 cannot_cast.
"""
from .conftest import CAMPAIGN_ID


async def _seed_battle_with_buff(
    gm_client, caster, target, buff_key="paralyzed",
):
    """Seed a battle that includes the target carrying a named
    condition buff. The endpoint reads buffs from hub state, so we
    install via /battle PUT rather than _install_buff."""
    pc_cb = {
        "id": f"tok_lr_caster_{caster['id']}",
        "char_id": caster["id"],
        "name": caster["name"],
        "initiative": 15,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    target_cb = {
        "id": f"tok_lr_target_{target['id']}",
        "char_id": target["id"],
        "name": target["name"],
        "initiative": 10,
        "hp_current": 30, "hp_max": 30,
        "buffs": [{"key": buff_key, "name": buff_key.title()}]
        if buff_key else [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [pc_cb, target_cb], "turn_index": 0,
              "round": 1, "active": True},
    )


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


async def test_cast_lr_removes_paralyzed(gm_client, roster):
    """Krieger carries a paralyzed buff. Tavik casts Lesser
    Restoration → buff is removed; response.removed=True and
    /buffs no longer lists paralyzed."""
    cleric = roster["Brother Tavik Stonebrow"]
    target = roster["Krieger Stonefist"]
    await _seed_battle_with_buff(
        gm_client, cleric, target, buff_key="paralyzed",
    )

    # Verify the buff is present pre-cast.
    buffs_before = await _get_buffs(gm_client, target["id"])
    assert any(
        b.get("key") == "paralyzed" for b in buffs_before
    ), f"expected paralyzed before cast; got {buffs_before}"

    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_lesser_restoration",
        json={
            "character_id": cleric["id"],
            "target_character_id": target["id"],
            "condition_key": "paralyzed",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "lesser-restoration"
    assert body["condition_key"] == "paralyzed"
    assert body["removed"] is True

    buffs_after = await _get_buffs(gm_client, target["id"])
    assert not any(
        b.get("key") == "paralyzed" for b in buffs_after
    ), f"paralyzed should be removed; got {buffs_after}"


async def test_cast_lr_condition_not_present_returns_409(
    gm_client, roster,
):
    """Krieger has no paralyzed buff → 409 condition_not_present."""
    cleric = roster["Brother Tavik Stonebrow"]
    target = roster["Krieger Stonefist"]
    # Seed a battle with no buffs on the target.
    await _seed_battle_with_buff(
        gm_client, cleric, target, buff_key=None,
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_lesser_restoration",
        json={
            "character_id": cleric["id"],
            "target_character_id": target["id"],
            "condition_key": "paralyzed",
        },
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "condition_not_present"


async def test_cast_lr_invalid_condition_key_returns_400(
    gm_client, roster,
):
    """condition_key='charmed' (not on Lesser Restoration's list)
    → 400."""
    cleric = roster["Brother Tavik Stonebrow"]
    target = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_lesser_restoration",
        json={
            "character_id": cleric["id"],
            "target_character_id": target["id"],
            "condition_key": "charmed",
        },
    )
    assert r.status_code == 400, r.text


async def test_cast_lr_missing_target_returns_400(gm_client, roster):
    """Omit target_character_id → 400."""
    cleric = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_lesser_restoration",
        json={
            "character_id": cleric["id"],
            "condition_key": "paralyzed",
        },
    )
    assert r.status_code == 400, r.text


async def test_cast_lr_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) as the caster → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    target = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_lesser_restoration",
        json={
            "character_id": krieger["id"],
            "target_character_id": target["id"],
            "condition_key": "paralyzed",
        },
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "lesser restoration" in body["expected"].lower()
