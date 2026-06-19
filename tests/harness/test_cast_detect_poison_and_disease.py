"""Detect Poison and Disease — L1 divination ritual,
Cleric/Druid/Paladin/Ranger. Phase 2 #15 of
``docs/plans/cast-and-broadcast-tail.md``.

v2.458.0 — RAW PHB p.231: "For the duration, you can sense the
presence and location of poisons, poisonous creatures, and
diseases within 30 feet of you. You also identify the kind of
poison, poisonous creature, or disease in each case." 1 action
(ritual), V/S/M (a yew leaf), Self, Concentration up to 10
minutes.

New ``_SPELL_BUFF_MAP["detect-poison-and-disease"]`` substrate
carrying ``effects.senses_poison_and_disease_within_30ft: True``
— flag-buff shape (same as Detect Evil and Good v2.456.0 /
Detect Magic v2.457.0). Completes the L1-ritual detection trio.

Tests:
  - Cleric (Tavik) self-cast installs buff with
    senses_poison_and_disease_within_30ft: true.
  - Buff carries duration_rounds=100 + concentration=true.
  - Krieger (Barbarian) → 409 cannot_cast.
  - Thalindra (Wizard) → 409 — Wizards are NOT on this spell's
    RAW class list (Cleric/Druid/Paladin/Ranger only).
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    pc_cb = {
        "id": f"tok_dpd_caster_{caster['id']}",
        "char_id": caster["id"],
        "name": caster["name"],
        "initiative": 15,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [pc_cb], "turn_index": 0,
              "round": 1, "active": True},
    )


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


async def test_cast_dpd_installs_buff(gm_client, roster):
    """A Cleric self-casts Detect Poison and Disease; the installed
    buff carries effects.senses_poison_and_disease_within_30ft =
    true."""
    cleric = roster["Brother Tavik Stonebrow"]
    await _set_battle(gm_client, cleric)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_detect_poison_and_disease",
        json={"character_id": cleric["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "detect-poison-and-disease"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 100

    buffs = await _get_buffs(gm_client, cleric["id"])
    dpd_buff = next(
        (b for b in buffs
         if b.get("key") == "detect-poison-and-disease"), None,
    )
    assert dpd_buff is not None, (
        f"detect-poison-and-disease buff missing: {buffs}"
    )
    effects = dpd_buff.get("effects") or {}
    assert effects.get("senses_poison_and_disease_within_30ft") is True


async def test_cast_dpd_buff_is_10_min_concentration(gm_client, roster):
    """The installed buff carries duration_rounds=100 (10 minutes)
    and concentration=true, matching RAW."""
    cleric = roster["Brother Tavik Stonebrow"]
    await _set_battle(gm_client, cleric)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_detect_poison_and_disease",
        json={"character_id": cleric["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, cleric["id"])
    dpd_buff = next(
        (b for b in buffs
         if b.get("key") == "detect-poison-and-disease"), None,
    )
    assert dpd_buff is not None
    assert dpd_buff.get("concentration") is True
    assert int(dpd_buff.get("duration_rounds") or 0) == 100


async def test_cast_dpd_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_detect_poison_and_disease",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "detect poison and disease" in body["expected"].lower()


async def test_cast_dpd_wizard_rejected(gm_client, roster):
    """Wizards are NOT on the Detect Poison and Disease class list
    per RAW (Cleric/Druid/Paladin/Ranger only — divine + primal
    only, no arcane). Thalindra → 409."""
    wiz = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, wiz)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_detect_poison_and_disease",
        json={"character_id": wiz["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
