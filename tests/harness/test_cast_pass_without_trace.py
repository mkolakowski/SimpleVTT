"""Pass without Trace — L2 abjuration, Druid/Ranger. Phase 1
demonstrator #4 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.440.0 — RAW PHB p.264: "A veil of shadows and silence radiates
from you, masking you and your companions from detection. For the
duration, each creature you choose within 30 feet of you (including
you) has a +10 bonus to Dexterity (Stealth) checks and can't be
tracked except by magical means." Concentration, up to 1 hour.

Persistent (non-consuming) +10 Stealth bonus — fires on every Stealth
/roll while the buff is active. Same shape as Emboldening Bond's
+1d4 read site (v2.158.47), not Hide in Plain Sight's consume-on-use
shape. The 30-ft companion radius + the "can't be tracked except by
magical means" rider stay GM-tracked.

Caster: Mira Greenleaf (Druid) is the canonical caster; Rowan
Quickbow (Ranger) is the fallback.

Tests:
  - Cast self-targets installs the buff with effects.stealth_bonus = 10.
  - The installed buff carries duration_rounds=600 + concentration=true.
  - Stealth /roll while the buff is active gets +10 added with the
    "Pass without Trace" breakdown text.
  - Krieger Stonefist (Barbarian) → 409 cannot_cast.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    """Stand up a tiny single-combatant battle so the buff has a hub
    state to install into."""
    pc_cb = {
        "id": f"tok_pwt_caster_{caster['id']}",
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


async def _get_caster_buffs(gm_client, caster_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


async def _find_pwt_caster(roster):
    """Find a roster character on the Druid/Ranger list. Mira
    (Druid) is the canonical choice; Rowan (Ranger) is the fallback.
    """
    for name in (
        "Mira Greenleaf",        # Druid
        "Rowan Quickbow",        # Ranger
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_pass_without_trace_installs_buff(gm_client, roster):
    """A Druid self-targets Pass without Trace; the installed buff
    carries effects.stealth_bonus = 10."""
    caster = await _find_pwt_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Druid/Ranger in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_pass_without_trace",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "pass-without-trace"
    assert body["buffs_installed"] == 1
    assert body["targets"] == [caster["id"]]
    assert body["duration_rounds"] == 600

    buffs = await _get_caster_buffs(gm_client, caster["id"])
    pwt_buff = next(
        (b for b in buffs if b.get("key") == "pass-without-trace"), None,
    )
    assert pwt_buff is not None, f"pass-without-trace buff missing: {buffs}"
    effects = pwt_buff.get("effects") or {}
    assert effects.get("stealth_bonus") == 10


async def test_cast_pass_without_trace_buff_is_1_hour_concentration(
    gm_client, roster,
):
    """The installed buff carries duration_rounds=600 (1 hour) and
    concentration=true, matching RAW."""
    caster = await _find_pwt_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Druid/Ranger in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_pass_without_trace",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_caster_buffs(gm_client, caster["id"])
    pwt_buff = next(
        (b for b in buffs if b.get("key") == "pass-without-trace"), None,
    )
    assert pwt_buff is not None
    assert pwt_buff.get("concentration") is True
    assert int(pwt_buff.get("duration_rounds") or 0) == 600


async def test_pass_without_trace_adds_10_to_stealth_roll(
    gm_client, roster,
):
    """Install buff, then roll Stealth → total includes +10 with the
    'Pass without Trace' breakdown text. The bonus is PERSISTENT — a
    second Stealth roll right after also picks up the +10 (vs. the
    consume-on-use shape of Hide in Plain Sight)."""
    caster = await _find_pwt_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Druid/Ranger in the demo roster")
    await _set_battle(gm_client, caster)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_pass_without_trace",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text

    # Roll Stealth — the +10 should land.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": caster["id"],
            "stat_key": "Stealth",
            "stat_ability": "DEX",
            "visibility": "public",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    breakdown = data.get("breakdown") or ""
    total = int(data.get("total") or 0)
    assert "Pass without Trace" in breakdown, (
        f"expected breakdown to include 'Pass without Trace'; "
        f"got {breakdown!r}"
    )
    # Total is at minimum d20=1 + 10 = 11. Stealth can also include
    # DEX mod + proficiency from the sheet, so the upper bound varies
    # by character — assert the lower bound only.
    assert total >= 11, (
        f"total should be at least d20=1 + 10 = 11; got {total}, "
        f"breakdown={breakdown!r}"
    )

    # Roll Stealth a second time — buff is persistent, +10 still
    # applies (vs. consume-on-use Hide in Plain Sight).
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": caster["id"],
            "stat_key": "Stealth",
            "stat_ability": "DEX",
            "visibility": "public",
        },
    )
    assert r2.status_code == 200, r2.text
    breakdown2 = (r2.json().get("breakdown") or "")
    assert "Pass without Trace" in breakdown2, (
        f"second roll should still get the persistent bonus; "
        f"got {breakdown2!r}"
    )


async def test_cast_pass_without_trace_non_caster_rejected(
    gm_client, roster,
):
    """Krieger Stonefist is a Barbarian — not in Druid/Ranger.
    Returns 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_pass_without_trace",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "pass without trace" in body["expected"].lower()
