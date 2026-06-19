"""Protection from Evil and Good — L1 abjuration,
Cleric/Paladin/Warlock/Wizard. Phase 2 #12 of
``docs/plans/cast-and-broadcast-tail.md``.

v2.455.0 — RAW PHB p.270: "Until the spell ends, one willing
creature you touch is protected against certain types of
creatures: aberrations, celestials, elementals, fey, fiends, and
undead." 1 action, V/S/M (powdered silver and iron), Touch,
Concentration up to 10 minutes.

Rides the existing ``_SPELL_BUFF_MAP["protection-from-evil-and-
good"]`` substrate (``pfeag_protected_types`` list of 6 creature
types + three boolean RAW-benefit flags, 100 rounds = 10 min,
concentration). All four flags are pre-wired into the engine
read sites (the /use_attack disadvantage gate, the condition-
install gate, the save-roll suffix) — the new endpoint just
exposes a dedicated cast path.

Tests:
  - Cast self-targeted → buff installs with all four pfeag flags
    and the right protected_types list.
  - Buff carries duration_rounds=100 + concentration=true.
  - Cast targeting an ally installs the buff on the ally.
  - Krieger (Barbarian, not on the class list) → 409 cannot_cast.
  - Response carries protected_types echoing the RAW list.
"""
from .conftest import CAMPAIGN_ID


_RAW_PFEAG_TYPES = {
    "aberration", "celestial", "elemental",
    "fey", "fiend", "undead",
}


async def _set_battle(gm_client, caster, ally=None):
    combatants = [{
        "id": f"tok_pfeag_caster_{caster['id']}",
        "char_id": caster["id"],
        "name": caster["name"],
        "initiative": 15,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }]
    if ally is not None:
        combatants.append({
            "id": f"tok_pfeag_ally_{ally['id']}",
            "char_id": ally["id"],
            "name": ally["name"],
            "initiative": 10,
            "hp_current": 30, "hp_max": 30,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
        })
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


async def _find_pfeag_caster(roster):
    for name in (
        "Thalindra Moonwhisper",   # Wizard
        "Brother Tavik Stonebrow",  # Cleric
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_pfeag_self_installs_buff(gm_client, roster):
    """Caster self-targets PfE&G; the installed buff carries all
    four pfeag effect flags and the RAW 6-type protected list."""
    caster = await _find_pfeag_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no PfE&G caster in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_protection_from_evil_and_good",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "protection-from-evil-and-good"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 100
    assert body["target_character_id"] == caster["id"]
    assert set(body["protected_types"]) == _RAW_PFEAG_TYPES

    buffs = await _get_buffs(gm_client, caster["id"])
    pfeag_buff = next(
        (b for b in buffs
         if b.get("key") == "protection-from-evil-and-good"), None,
    )
    assert pfeag_buff is not None, (
        f"pfeag buff missing: {buffs}"
    )
    effects = pfeag_buff.get("effects") or {}
    assert set(effects.get("pfeag_protected_types") or []) == _RAW_PFEAG_TYPES
    assert effects.get("pfeag_attackers_have_disadvantage") is True
    assert effects.get("pfeag_immune_to_charm_frighten_possess") is True
    assert effects.get("pfeag_advantage_on_saves_vs_types") is True


async def test_cast_pfeag_buff_is_10_min_concentration(
    gm_client, roster,
):
    """The installed buff carries duration_rounds=100 (10 minutes)
    and concentration=true, matching RAW."""
    caster = await _find_pfeag_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no PfE&G caster in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_protection_from_evil_and_good",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, caster["id"])
    pfeag_buff = next(
        (b for b in buffs
         if b.get("key") == "protection-from-evil-and-good"), None,
    )
    assert pfeag_buff is not None
    assert pfeag_buff.get("concentration") is True
    assert int(pfeag_buff.get("duration_rounds") or 0) == 100


async def test_cast_pfeag_on_ally_installs_on_ally(gm_client, roster):
    """Targeting an ally wards the ally; caster doesn't carry the
    buff."""
    caster = await _find_pfeag_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no PfE&G caster in the demo roster")
    ally = roster["Krieger Stonefist"]
    await _set_battle(gm_client, caster, ally=ally)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_protection_from_evil_and_good",
        json={
            "character_id": caster["id"],
            "target_character_id": ally["id"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_character_id"] == ally["id"]
    assert body["buff_installed"] is True

    ally_buffs = await _get_buffs(gm_client, ally["id"])
    assert any(
        b.get("key") == "protection-from-evil-and-good"
        for b in ally_buffs
    ), f"pfeag buff missing on ally: {ally_buffs}"

    caster_buffs = await _get_buffs(gm_client, caster["id"])
    assert not any(
        b.get("key") == "protection-from-evil-and-good"
        for b in caster_buffs
    ), (
        f"caster shouldn't carry the buff when targeting an ally: "
        f"{caster_buffs}"
    )


async def test_cast_pfeag_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_protection_from_evil_and_good",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "protection from evil and good" in body["expected"].lower()
