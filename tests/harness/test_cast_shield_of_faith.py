"""Shield of Faith — L1 abjuration, Cleric/Paladin. Phase 2 opener
of ``docs/plans/cast-and-broadcast-tail.md`` (Phase 1 closed
v2.441.0; Phase 2 runs indefinitely against Bucket A).

v2.442.0 — RAW PHB p.275: "A shimmering field appears and surrounds
a creature of your choice within range, granting it a +2 bonus to
AC for the duration." Bonus action, V/S/M, 60 ft, Concentration,
up to 10 minutes.

The `_SPELL_BUFF_MAP["shield-of-faith"]` substrate was already
wired v2.97.38 (`ac_bonus: 2`, concentration, 100 rounds); the
`_read_target_ac` walker was already summing `effects.ac_bonus`
across the target's buffs v2.97.39. This commit just exposes the
cast endpoint so the substrate is reachable from a cast button.

Caster: Brother Tavik Stonebrow (Cleric) is the canonical caster;
Dame Seraphine Vael (Paladin) is the fallback.

Tests:
  - Cast self-targets installs the buff with effects.ac_bonus = 2.
  - The installed buff carries duration_rounds=100 + concentration=true.
  - /attack's target_ac on the buffed target is +2 vs baseline.
  - Krieger Stonefist (Barbarian) → 409 cannot_cast.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    """Stand up a tiny single-combatant battle so the buff has a hub
    state to install into."""
    pc_cb = {
        "id": f"tok_sof_caster_{caster['id']}",
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
    return pc_cb["id"]


async def _get_caster_buffs(gm_client, caster_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


async def _find_sof_caster(roster):
    """Find a roster character on the Cleric/Paladin list."""
    for name in (
        "Brother Tavik Stonebrow",  # Cleric
        "Dame Seraphine Vael",      # Paladin
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_shield_of_faith_installs_buff(gm_client, roster):
    """A Cleric self-targets Shield of Faith; the installed buff
    carries effects.ac_bonus = 2."""
    caster = await _find_sof_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Paladin in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_shield_of_faith",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "shield-of-faith"
    assert body["buff_installed"] is True
    assert body["target_character_id"] == caster["id"]
    assert body["duration_rounds"] == 100

    buffs = await _get_caster_buffs(gm_client, caster["id"])
    sof_buff = next(
        (b for b in buffs if b.get("key") == "shield-of-faith"), None,
    )
    assert sof_buff is not None, f"shield-of-faith buff missing: {buffs}"
    effects = sof_buff.get("effects") or {}
    assert effects.get("ac_bonus") == 2


async def test_cast_shield_of_faith_buff_is_10_minutes_concentration(
    gm_client, roster,
):
    """The installed buff carries duration_rounds=100 (10 minutes)
    and concentration=true, matching RAW."""
    caster = await _find_sof_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Paladin in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_shield_of_faith",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_caster_buffs(gm_client, caster["id"])
    sof_buff = next(
        (b for b in buffs if b.get("key") == "shield-of-faith"), None,
    )
    assert sof_buff is not None
    assert sof_buff.get("concentration") is True
    assert int(sof_buff.get("duration_rounds") or 0) == 100


async def test_shield_of_faith_raises_target_ac_by_2(gm_client, roster):
    """After casting Shield of Faith on self, the target_ac reported
    by /attack rises by exactly +2 from the baseline read. Validates
    the v2.97.39 ac_bonus walker fires on the new substrate entry."""
    caster = await _find_sof_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Paladin in the demo roster")
    caster_tok = await _set_battle(gm_client, caster)

    # Baseline target_ac via a /attack on the caster's own combatant.
    a1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": caster["id"], "attack_index": 0,
              "target_combatant_id": caster_tok, "override": True},
    )
    assert a1.status_code == 200, a1.text
    base_ac = a1.json()["target_ac"]
    assert base_ac is not None

    # Cast Shield of Faith on self.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_shield_of_faith",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text

    # Re-read target_ac — should be base + 2.
    a2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": caster["id"], "attack_index": 0,
              "target_combatant_id": caster_tok, "override": True},
    )
    assert a2.status_code == 200, a2.text
    buffed_ac = a2.json()["target_ac"]
    assert buffed_ac == base_ac + 2, (
        f"Shield of Faith should add +2 to target_ac; got "
        f"base={base_ac}, buffed={buffed_ac}"
    )


async def test_cast_shield_of_faith_non_caster_rejected(gm_client, roster):
    """Krieger Stonefist is a Barbarian — not in Cleric/Paladin.
    Returns 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_shield_of_faith",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "shield of faith" in body["expected"].lower()
