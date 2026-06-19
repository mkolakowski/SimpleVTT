"""Mage Armor — L1 abjuration, Sorcerer/Wizard. Phase 2 #2 of
``docs/plans/cast-and-broadcast-tail.md`` (Phase 1 closed v2.441.0;
Phase 2 runs indefinitely against Bucket A).

v2.443.0 — RAW PHB p.256: "You touch a willing creature who isn't
wearing armor, and a protective magical force surrounds it until
the spell ends. The target's base AC becomes 13 + its Dexterity
modifier." Action, V/S/M, Touch, 8 hours, non-concentration.

The `_SPELL_BUFF_MAP["mage-armor"]` substrate was wired v2.99.422
(`ac_bonus: 3`, 4800 rounds @ 6 s/round = 8 h, non-concentration);
the `_read_target_ac` ac_bonus walker already sums it (v2.97.39).
This commit just exposes the cast endpoint so the substrate is
reachable from a cast button. Same shape as v2.442.0 Shield of
Faith — pure endpoint exposure.

The +3 models the difference between Mage Armor's "13 + DEX" and
the unarmored base "10 + DEX" that ``sheet["ac"]`` already
reflects. The "while unarmored" rider is GM-tracked.

Caster: Thalindra Moonwhisper (Wizard) is the canonical caster;
Magnus Hexbinder (Warlock — Warlock isn't in the caster list but
Magnus has a multiclass build that doesn't fit this gate, so
Thalindra carries the test alone). The wizard demo seed is enough.

Tests:
  - Cast self-targets installs the buff with effects.ac_bonus = 3.
  - The installed buff carries duration_rounds=4800 + concentration=false.
  - /attack's target_ac on the buffed target is +3 vs baseline.
  - Krieger Stonefist (Barbarian) → 409 cannot_cast.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    """Stand up a tiny single-combatant battle so the buff has a hub
    state to install into."""
    pc_cb = {
        "id": f"tok_ma_caster_{caster['id']}",
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


async def _find_ma_caster(roster):
    """Find a roster character on the Sorcerer/Wizard list. Thalindra
    (Wizard) is the canonical demo caster.
    """
    for name in ("Thalindra Moonwhisper",):
        if name in roster:
            return roster[name]
    return None


async def test_cast_mage_armor_installs_buff(gm_client, roster):
    """A Wizard self-targets Mage Armor; the installed buff carries
    effects.ac_bonus = 3."""
    caster = await _find_ma_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Sorcerer/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mage_armor",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "mage-armor"
    assert body["buff_installed"] is True
    assert body["target_character_id"] == caster["id"]
    assert body["duration_rounds"] == 4800

    buffs = await _get_caster_buffs(gm_client, caster["id"])
    ma_buff = next(
        (b for b in buffs if b.get("key") == "mage-armor"), None,
    )
    assert ma_buff is not None, f"mage-armor buff missing: {buffs}"
    effects = ma_buff.get("effects") or {}
    assert effects.get("ac_bonus") == 3


async def test_cast_mage_armor_buff_is_8_hours_non_concentration(
    gm_client, roster,
):
    """The installed buff carries duration_rounds=4800 (8 hours)
    and concentration=false, matching RAW."""
    caster = await _find_ma_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Sorcerer/Wizard in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mage_armor",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_caster_buffs(gm_client, caster["id"])
    ma_buff = next(
        (b for b in buffs if b.get("key") == "mage-armor"), None,
    )
    assert ma_buff is not None
    assert ma_buff.get("concentration") is False
    assert int(ma_buff.get("duration_rounds") or 0) == 4800


async def test_mage_armor_raises_target_ac_by_3(gm_client, roster):
    """After casting Mage Armor on self, the target_ac reported by
    /attack rises by exactly +3 from the baseline read. Validates
    the v2.97.39 ac_bonus walker fires on the existing substrate."""
    caster = await _find_ma_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Sorcerer/Wizard in the demo roster")
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

    # Cast Mage Armor on self.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mage_armor",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text

    # Re-read target_ac — should be base + 3.
    a2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": caster["id"], "attack_index": 0,
              "target_combatant_id": caster_tok, "override": True},
    )
    assert a2.status_code == 200, a2.text
    buffed_ac = a2.json()["target_ac"]
    assert buffed_ac == base_ac + 3, (
        f"Mage Armor should add +3 to target_ac; got "
        f"base={base_ac}, buffed={buffed_ac}"
    )


async def test_cast_mage_armor_non_caster_rejected(gm_client, roster):
    """Krieger Stonefist is a Barbarian — not in Sorcerer/Wizard.
    Returns 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mage_armor",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "mage armor" in body["expected"].lower()
