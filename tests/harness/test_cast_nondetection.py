"""Nondetection — L3 abjuration, Bard/Cleric/Ranger/Wizard.
Phase 2 #48 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.524.0 — RAW PHB p.264: "For the duration, you hide a target that you
touch from divination magic. ... The target can't be targeted by any
divination magic or perceived through magical scrying sensors." 1 action,
V/S/M, Touch, 8 hours, non-concentration.

Single-target touch flag-buff (same shape as Tongues v2.445.0 / See
Invisibility v2.509.0): installs `effects.nondetection: True`. The flag
IS the mechanic; the detection block is GM-narrated.

Tests:
  - Self-cast installs the buff with nondetection: true (8h, non-conc).
  - Touch an ally → the buff lands on the ally, not the caster.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


def _tok(char):
    return {
        "id": f"tok_nd_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": 10,
        "hp_current": 30, "hp_max": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _set_battle(gm_client, combatants):
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


def _find_caster(roster):
    for name in (
        "Thalindra Moonwhisper", "Lyra Sunstrider",
        "Brother Tavik Stonebrow", "Mira Greenleaf",
    ):
        if name in roster:
            return roster[name]
    return None


async def test_cast_nd_self_installs_buff(gm_client, roster):
    """Self-cast → buff carries effects.nondetection == true, 8h non-conc."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no eligible caster in the demo roster")
    await _set_battle(gm_client, [_tok(caster)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_nondetection",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "nondetection"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 4800
    assert body["target_character_id"] == caster["id"]

    buffs = await _get_buffs(gm_client, caster["id"])
    nd = next((b for b in buffs if b.get("key") == "nondetection"), None)
    assert nd is not None, f"buff missing: {buffs}"
    assert (nd.get("effects") or {}).get("nondetection") is True
    assert nd.get("concentration") is False
    assert int(nd.get("duration_rounds") or 0) == 4800


async def test_cast_nd_on_ally_installs_on_ally(gm_client, roster):
    """Touching an ally installs the buff on the ally, not the caster."""
    caster = _find_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no eligible caster in the demo roster")
    ally = roster["Krieger Stonefist"]
    try:
        await _set_battle(gm_client, [_tok(caster), _tok(ally)])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_nondetection",
            json={"character_id": caster["id"],
                  "target_character_id": ally["id"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["target_character_id"] == ally["id"]
        ally_buffs = await _get_buffs(gm_client, ally["id"])
        assert any(b.get("key") == "nondetection" for b in ally_buffs), ally_buffs
        caster_buffs = await _get_buffs(gm_client, caster["id"])
        assert not any(b.get("key") == "nondetection" for b in caster_buffs)
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": ally["id"], "key": "nondetection"},
        )


async def test_cast_nd_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_nondetection",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "nondetection" in r.json()["expected"].lower()


async def test_cast_nd_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_nondetection",
        json={},
    )
    assert r.status_code == 400, r.text
