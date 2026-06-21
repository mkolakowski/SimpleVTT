"""Heroes' Feast — L6 conjuration, Bard/Cleric.
Phase 2 #39 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.506.0 — RAW PHB p.250: the feaster "becomes immune to poison and
being frightened, and makes all Wisdom saving throws with advantage.
In addition, its hit point maximum increases by 2d10, and it gains the
same number of hit points." 24 hours, non-concentration.

All three combat halves ride existing substrates: condition immunity
(the `_install_buff` gate), `save_advantage: ["WIS"]`
(`_buff_grants_save_advantage`), and `aid_hp_bonus` = a per-cast 2d10
roll (`_buff_hp_max_bonus` raises the max; the endpoint heals current
HP by the same). The buff is mirrored to the target sheet. Cure-of-
disease/poison + the multi-creature feast are GM-narrated.

Tests:
  - Install → buff carries the three markers + is mirrored to the sheet.
  - HP gate: a full-HP target ends up at max + the rolled 2d10 (proves
    both the max-raise and the heal).
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


def _tok(char):
    return {
        "id": f"tok_hf_{char['id']}",
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


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    return r.json().get("sheet") or {}


def _find_hf_caster(roster):
    for name in ("Brother Tavik Stonebrow", "Lyra Sunstrider"):  # Cleric, Bard
        if name in roster:
            return roster[name]
    return None


async def test_cast_heroes_feast_installs_all_markers(gm_client, roster):
    """Cast → buff carries the poison/frightened immunity, WIS save
    advantage, and a rolled aid_hp_bonus; mirrored to the sheet."""
    caster = _find_hf_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Bard in the demo roster")
    await _set_battle(gm_client, [_tok(caster)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_heroes_feast",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "heroes-feast"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 14400
    assert 2 <= int(body["hp_bonus"]) <= 20

    buffs = await _get_buffs(gm_client, caster["id"])
    hf = next((b for b in buffs if b.get("key") == "heroes-feast"), None)
    assert hf is not None, f"heroes-feast buff missing: {buffs}"
    eff = hf.get("effects") or {}
    ci = set(eff.get("condition_immunity_to") or [])
    assert {"poisoned", "frightened"} <= ci, ci
    sa = [str(x).upper()[:3] for x in (eff.get("save_advantage") or [])]
    assert "WIS" in sa, sa
    assert int(eff.get("aid_hp_bonus") or 0) >= 2
    assert hf.get("concentration") is False

    # Mirrored to the sheet (condition-immunity gate precondition).
    active = (await _sheet(gm_client, caster["id"])).get("_buffs_active") or []
    assert any(b.get("key") == "heroes-feast" for b in active), active


async def test_heroes_feast_raises_max_hp_and_heals(gm_client, roster):
    """A full-HP target ends at (max + rolled 2d10) — proving both the
    `aid_hp_bonus` max-raise and the install-time heal (a non-raised
    max would cap the heal at the base max → no change)."""
    caster = _find_hf_caster(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric/Bard in the demo roster")
    tgt = roster["Krieger Stonefist"]
    orig = (await _sheet(gm_client, tgt["id"])).get("hp") or {}
    # Put the target at full HP so the heal only lands if the max rose.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tgt['id']}/sheet-fields",
        json={"hp": {"current": 20, "max": 20, "temp": 0}},
    )
    try:
        await _set_battle(gm_client, [_tok(caster), _tok(tgt)])
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": tgt["id"], "key": "heroes-feast"},
        )
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_heroes_feast",
            json={"character_id": caster["id"],
                  "target_character_id": tgt["id"]},
        )
        assert r.status_code == 200, r.text
        hp_bonus = int(r.json()["hp_bonus"])
        cur = int(((await _sheet(gm_client, tgt["id"])).get("hp") or {}).get("current") or 0)
        assert cur == 20 + hp_bonus, (
            f"expected current HP 20+{hp_bonus}={20 + hp_bonus}, got {cur}"
        )
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tgt['id']}/sheet-fields",
            json={"hp": orig},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": tgt["id"], "key": "heroes-feast"},
        )


async def test_cast_heroes_feast_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_heroes_feast",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "heroes' feast" in r.json()["expected"].lower()


async def test_cast_heroes_feast_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_heroes_feast",
        json={},
    )
    assert r.status_code == 400, r.text
