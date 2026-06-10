"""v2.99.324 → v2.158.16 — Eloquence College Bard: Silver Tongue (Lv 3+, TCE).

v2.99.324 shipped announce-only. v2.158.16 (Phase 8 Bard
diversification — first Bard subclass feature flipped from
announce-only to tracked this session, pushes the
diversification arc to 7/12 classes) wires the endpoint to
install a permanent `silver-tongue-active` buff carrying three
`silver_tongue_*` parameter flags (min_d20=10,
skills=["persuasion","deception"], ability="CHA"). v2.158.36
(Phase 2) wires the read site: the `/roll` endpoint reads the
buff via `_pc_silver_tongue_floor_applies` and floors the kept
d20 to 10 on CHA Persuasion/Deception checks (reusing the
Reliable Talent floor mechanic), emitting a
`feature_used(source=silver-tongue)` broadcast.

RAW TCE p.28: Cha (Persuasion) and Cha (Deception) checks
treat a d20 roll of 9 or lower as a 10.

Tests:
  - Lv 3+ happy → minimum_d20_value 10, applies_to includes
    persuasion + deception, `buff_installed == True`.
  - Wrong subclass → 409.
  - Eloquence Lv 2 → 409.
  - State contract: installed buff carries the three
    `silver_tongue_*` effect keys with the right values.
  - Phase 2 read site: a low d20 on a Persuasion check is
    floored to 10 + the broadcast fires (Athletics control
    untouched).
"""
import asyncio
import re

import pytest_asyncio

from .conftest import CAMPAIGN_ID


_D20_RE = re.compile(r"\d*d20[^d=+ ]*=(\d+)", re.IGNORECASE)


async def _seed_dice(gm_client, seed):
    r = await gm_client.post("/api/test/dice/seed", json={"seed": seed})
    assert r.status_code == 200, r.text


async def _roll(gm_client, char_id, stat_key, stat_ability="CHA"):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={
            "expression": "1d20",
            "character_id": char_id,
            "stat_key": stat_key,
            "stat_ability": stat_ability,
            "visibility": "public",
        },
    )


async def _seed_until_d20_below_10(gm_client, char_id, stat_key):
    """Find a dice seed whose kept d20 lands in [2,9] on a non-floored
    skill (so Silver Tongue does NOT fire during discovery). Returns
    (seed, d20). Excludes natural 1 for parity with the other floor
    tests, though Lyra isn't a Halfling."""
    for s in range(1, 500):
        await _seed_dice(gm_client, s)
        r = await _roll(gm_client, char_id, stat_key)
        if r.status_code != 200:
            continue
        m = _D20_RE.search(r.json().get("breakdown") or "")
        if not m:
            continue
        try:
            d20 = int(m.group(1))
        except ValueError:
            continue
        if 2 <= d20 <= 9:
            return s, d20
    raise AssertionError("Couldn't find a seed producing 2 <= d20 <= 9")


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _st_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "silver-tongue"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _pc(cid, c, *, hp_max=40):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_lyra_in_battle(gm_client, lyra):
    """v2.158.16 — `_install_buff` requires an active battle.
    Seed a minimal one with Lyra."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_st_lyra_{lyra['id']}", lyra)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


@pytest_asyncio.fixture
async def lyra_eloquence(gm_client, roster):
    """PATCH Lyra to College of Eloquence."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Eloquence"},
        class_slug="bard",
    )
    try:
        yield lyra
    finally:
        await _patch_sheet(
            gm_client, lyra["id"],
            {"subclass": "College of Lore", "level": 6},
            class_slug="bard",
        )


async def test_use_st_happy_lv6(
    gm_client, gm_ws, lyra_eloquence,
):
    """Lv 6 Eloquence → minimum_d20_value 10, buff_installed True."""
    lyra = lyra_eloquence
    await _seed_lyra_in_battle(gm_client, lyra)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_silver_tongue",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["minimum_d20_value"] == 10
    assert "persuasion" in data["applies_to"]
    assert "deception" in data["applies_to"]
    assert data["ability"] == "CHA"
    assert data["bard_level"] == 6
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _st_broadcasts(gm_ws, lyra["id"])
    assert feats


async def test_use_st_wrong_subclass(
    gm_client, roster,
):
    """Default Lyra (Lore) → 409."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_silver_tongue",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_st_level_gate(
    gm_client, roster,
):
    """Eloquence Lyra at Lv 2 → 409."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(
        gm_client, lyra["id"],
        {"subclass": "College of Eloquence", "level": 2},
        class_slug="bard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_silver_tongue",
            json={"character_id": lyra["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, lyra["id"],
            {"subclass": "College of Lore", "level": 6},
            class_slug="bard",
        )


async def test_st_buff_payload_carries_parameter_flags(
    gm_client, gm_ws, lyra_eloquence,
):
    """v2.158.16 — state contract (Phase 9): the installed
    `silver-tongue-active` buff carries the three
    `silver_tongue_*` effect keys with the right values
    (min_d20=10, skills list with persuasion + deception,
    ability="CHA"). Phase 2 (deferred) will have the ability-
    check roll resolver read these off the caster's
    `_buffs_active` and apply the min-10 floor on CHA
    Persuasion/Deception; this test pins the flag shape so that
    future read site has a stable contract."""
    lyra = lyra_eloquence
    await _seed_lyra_in_battle(gm_client, lyra)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_silver_tongue",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    bu = await gm_ws.wait_for("buff_update")
    lyra_buffs = bu["data"]["buffs"]
    st_buff = next(
        (b for b in lyra_buffs if b.get("key") == "silver-tongue-active"),
        None,
    )
    assert st_buff is not None, (
        f"silver-tongue-active buff missing; got keys="
        f"{[b.get('key') for b in lyra_buffs]}"
    )
    effects = st_buff.get("effects") or {}
    assert effects.get("silver_tongue_min_d20") == 10
    skills = effects.get("silver_tongue_skills") or []
    assert "persuasion" in skills
    assert "deception" in skills
    assert effects.get("silver_tongue_ability") == "CHA"
    # Permanent passive — no concentration, very long duration.
    assert st_buff.get("concentration") in (False, None)
    assert int(st_buff.get("duration_rounds") or 0) >= 1000


async def test_st_floors_low_d20_on_persuasion(
    gm_client, gm_ws, lyra_eloquence,
):
    """v2.158.36 — Phase 2 read site. With the `silver-tongue-active`
    buff installed, a Cha (Persuasion) check whose kept d20 is < 10 is
    floored to 10 on `/roll`, and a `feature_used(source=silver-tongue)`
    broadcast surfaces the trigger. A control roll on a non-matching
    skill (Athletics) is left untouched."""
    lyra = lyra_eloquence
    await _seed_lyra_in_battle(gm_client, lyra)
    # Install the buff.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_silver_tongue",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 200, r.text
    await asyncio.sleep(0.2)
    # Discover a seed that lands d20 in [2,9] on a NON-matching skill
    # (Athletics — not in silver_tongue_skills, so no floor fires here).
    seed, old_d20 = await _seed_until_d20_below_10(
        gm_client, lyra["id"], "Athletics",
    )
    # Control: the discovery Athletics roll passed through unfloored.
    rc = await _roll(gm_client, lyra["id"], "Athletics")
    assert rc.status_code == 200, rc.text
    # Re-seed and roll the same d20 as a Persuasion check → floor to 10.
    await _seed_dice(gm_client, seed)
    gm_ws.mark()
    rp = await _roll(gm_client, lyra["id"], "Persuasion")
    assert rp.status_code == 200, rp.text
    data = rp.json()
    assert data.get("total") == 10, (
        f"v2.158.36: Silver Tongue should floor d20={old_d20} to 10 on "
        f"Persuasion; got total={data.get('total')}, "
        f"breakdown={data.get('breakdown')!r}"
    )
    await asyncio.sleep(0.3)
    feats = _st_broadcasts(gm_ws, lyra["id"])
    assert feats, (
        f"v2.158.36: expected feature_used(source=silver-tongue) for "
        f"Lyra; buffered: {gm_ws.buffered()}"
    )
    assert (feats[-1].get("data") or {}).get("stat_key") == "Persuasion"
