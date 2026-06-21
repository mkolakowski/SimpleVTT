"""Holy Aura — aura membership (Phase 1 of
``docs/plans/aura-geometry-enforcement.md``).

v2.516.0 — the cast (#41, v2.508.0) installs the two markers directly on
chosen targets; Phase 1 additionally registers a **membership aura** on
the caster's anchor buff so the v2.99.425 `_tick_auras` engine maintains
the benefit for allies within 30 ft each turn — granting it to an ally
who moves into the radius and letting it lapse (~2 rounds) when they
leave. The tick grants a DISTINCT key (`holy-aura-radiance`) carrying the
same `save_advantage` + `attackers_have_disadvantage` markers (the reads
are key-agnostic), so it never clobbers the cast-time `holy-aura` buffs
on chosen targets.

Grid: demo map is 70 px / cell, 5 ft / cell; 30 ft = 6 cells = 420 px.

Tests:
  - Registration: cast → the caster's anchor buff carries
    effects.aura{radius_ft:30, affects:allies, buff.key:holy-aura-radiance}.
  - In-range tick: a non-chosen ally 5 ft away gains holy-aura-radiance
    after the caster's turn ticks.
  - Out-of-range tick: an ally 35 ft away gains nothing.
"""
import asyncio

import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _find_cleric(roster):
    return roster.get("Brother Tavik Stonebrow")


def _tok(char, init=10, hp=40):
    return {
        "id": f"tok_hamem_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _put_battle(gm_client, combatants, turn_index, rnd):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": turn_index,
              "round": rnd, "active": True},
    )


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


async def _place(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(gm_client, roster):
    yield
    for name in ("Brother Tavik Stonebrow", "Krieger Stonefist"):
        ch = roster.get(name)
        if not ch:
            continue
        for key in ("holy-aura", "holy-aura-radiance"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": ch["id"], "key": key},
            )
        await gm_client.delete(
            f"/api/campaign/{CAMPAIGN_ID}/character/{ch['id']}/token",
        )
    await _put_battle(gm_client, [], 0, 1)


async def test_cast_registers_membership_aura(gm_client, roster):
    """Cast → the caster's anchor buff carries the membership aura."""
    caster = _find_cleric(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric in the demo roster")
    await _put_battle(gm_client, [_tok(caster)], 0, 1)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_holy_aura",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, caster["id"])
    anchor = next((b for b in buffs if b.get("key") == "holy-aura"), None)
    assert anchor is not None, f"anchor buff missing: {buffs}"
    aura = (anchor.get("effects") or {}).get("aura")
    assert isinstance(aura, dict), f"no membership aura registered: {anchor}"
    assert int(aura.get("radius_ft") or 0) == 30
    assert aura.get("affects") == "allies"
    grant = aura.get("buff") or {}
    assert grant.get("key") == "holy-aura-radiance"
    geff = grant.get("effects") or {}
    assert geff.get("save_advantage") is True
    assert geff.get("attackers_have_disadvantage") is True


def _anchor_buff(caster_id):
    """The exact membership-aura anchor `cast_holy_aura` installs on the
    caster (the registration test above proves the cast produces this).
    Used here as an explicit PUT payload so the tick path is deterministic
    — the same approach as test_aura_tick.py."""
    return {
        "key": "holy-aura", "name": "Holy Aura",
        "duration_rounds": 10, "duration_max": 10,
        "concentration": True, "source_char_id": caster_id,
        "effects": {
            "save_advantage": True,
            "attackers_have_disadvantage": True,
            "aura": {
                "radius_ft": 30, "affects": "allies",
                "source": "holy-aura", "label": "Holy Aura",
                "buff": {
                    "key": "holy-aura-radiance", "name": "Holy Aura",
                    "icon": "☀️",
                    "effects": {
                        "save_advantage": True,
                        "attackers_have_disadvantage": True,
                    },
                    "duration_rounds": 2,
                },
            },
        },
    }


async def _seed_anchor_and_tick(gm_client, caster, ally, ally_xy):
    """Seed [caster@idx0 (carrying the Holy Aura anchor), ally@idx1],
    place tokens, then advance the turn to the caster (idx1 → idx0) so
    `_tick_auras` fires for the emitter. Returns the ally's buffs."""
    caster_tok = _tok(caster, init=20)
    caster_tok["buffs"] = [_anchor_buff(caster["id"])]
    combs = [caster_tok, _tok(ally, init=10)]
    await _put_battle(gm_client, combs, 1, 1)  # ally active first
    await _place(gm_client, caster["id"], 350.0, 350.0)
    await _place(gm_client, ally["id"], ally_xy[0], ally_xy[1])
    await _put_battle(gm_client, combs, 0, 2)  # caster active → tick
    await asyncio.sleep(0.3)
    return await _get_buffs(gm_client, ally["id"])


async def test_in_range_ally_gains_radiance_on_tick(gm_client, roster):
    """A non-chosen ally 5 ft from the caster gains holy-aura-radiance
    after the caster's turn ticks."""
    caster = _find_cleric(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric in the demo roster")
    ally = roster["Krieger Stonefist"]
    # 420,350 is 1 cell (5 ft) east of the caster at 350,350.
    buffs = await _seed_anchor_and_tick(gm_client, caster, ally, (420.0, 350.0))
    rad = next((b for b in buffs if b.get("key") == "holy-aura-radiance"), None)
    assert rad is not None, (
        f"in-range ally should gain holy-aura-radiance on the tick: {buffs}"
    )
    eff = rad.get("effects") or {}
    assert eff.get("save_advantage") is True
    assert eff.get("attackers_have_disadvantage") is True


async def test_out_of_range_ally_gains_nothing_on_tick(gm_client, roster):
    """An ally 35 ft from the caster (outside the 30-ft aura) gains no
    holy-aura-radiance."""
    caster = _find_cleric(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric in the demo roster")
    ally = roster["Krieger Stonefist"]
    # 700,350 is 5 cells away... 350 + 7*70 = 840 → 7 cells = 35 ft.
    buffs = await _seed_anchor_and_tick(gm_client, caster, ally, (840.0, 350.0))
    rad = next((b for b in buffs if b.get("key") == "holy-aura-radiance"), None)
    assert rad is None, (
        f"out-of-range ally should NOT gain holy-aura-radiance: {buffs}"
    )
