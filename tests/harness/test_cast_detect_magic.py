"""Detect Magic — L1 divination ritual,
Bard/Cleric/Druid/Paladin/Ranger/Sorcerer/Wizard. Phase 2 #14 of
``docs/plans/cast-and-broadcast-tail.md``.

v2.457.0 — RAW PHB p.231: "For the duration, you sense the
presence of magic within 30 feet of you. If you sense magic in
this way, you can use your action to see a faint aura around any
visible creature or object in the area that bears magic, and you
learn its school of magic, if any." 1 action (ritual), V/S, Self,
Concentration up to 10 minutes.

New ``_SPELL_BUFF_MAP["detect-magic"]`` substrate carrying
``effects.senses_magic_within_30ft: True`` — flag-buff shape
(same as Detect Evil and Good v2.456.0 / Tongues v2.445.0 /
Comprehend Languages v2.450.0).

Widest class gate on the Phase 2 arc: 7 of 11 SRD caster classes
can prepare Detect Magic per RAW.

Tests:
  - Wizard self-cast installs buff with
    senses_magic_within_30ft: true.
  - Buff carries duration_rounds=100 + concentration=true.
  - Cleric (Tavik) succeeds (widest gate, asserts a non-arcane
    caster also passes).
  - Krieger (Barbarian) → 409 cannot_cast (one of the 4
    non-Detect-Magic classes: Barbarian, Fighter, Monk, Rogue —
    none of which can prepare it RAW).
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    pc_cb = {
        "id": f"tok_dm_caster_{caster['id']}",
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


async def test_cast_dm_wizard_installs_buff(gm_client, roster):
    """A Wizard self-casts Detect Magic; the installed buff carries
    effects.senses_magic_within_30ft = true."""
    wiz = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, wiz)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_detect_magic",
        json={"character_id": wiz["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "detect-magic"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 100

    buffs = await _get_buffs(gm_client, wiz["id"])
    dm_buff = next(
        (b for b in buffs if b.get("key") == "detect-magic"), None,
    )
    assert dm_buff is not None, (
        f"detect-magic buff missing: {buffs}"
    )
    effects = dm_buff.get("effects") or {}
    assert effects.get("senses_magic_within_30ft") is True


async def test_cast_dm_buff_is_10_min_concentration(gm_client, roster):
    """The installed buff carries duration_rounds=100 (10 minutes)
    and concentration=true, matching RAW."""
    wiz = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, wiz)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_detect_magic",
        json={"character_id": wiz["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, wiz["id"])
    dm_buff = next(
        (b for b in buffs if b.get("key") == "detect-magic"), None,
    )
    assert dm_buff is not None
    assert dm_buff.get("concentration") is True
    assert int(dm_buff.get("duration_rounds") or 0) == 100


async def test_cast_dm_cleric_also_succeeds(gm_client, roster):
    """A Cleric (non-arcane caster) succeeds — asserts the wide
    class gate covers divine casters too."""
    cleric = roster["Brother Tavik Stonebrow"]
    await _set_battle(gm_client, cleric)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_detect_magic",
        json={"character_id": cleric["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["buff_installed"] is True


async def test_cast_dm_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast. Barbarian is one of
    the 4 SRD classes that CAN'T cast Detect Magic per RAW
    (Barbarian/Fighter/Monk/Rogue)."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_detect_magic",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "detect magic" in body["expected"].lower()
