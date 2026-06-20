"""Goodberry — L1 transmutation, Druid/Ranger.
Phase 2 #22 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.465.0 — RAW PHB p.248: "Up to ten berries appear in your hand
and are infused with magic for the duration. A creature can use
its action to eat one berry. Eating a berry restores 1 hit point,
and the berry provides enough nourishment to sustain a creature
for one day. The berries lose their potency if they have not
been consumed within 24 hours of the casting of this spell." 1
action, V/S/M (sprig of mistletoe), Touch (caster's hand),
Instantaneous (24-hour shelf life on the berries).

New ``_SPELL_BUFF_MAP["goodberry"]`` substrate carrying
``effects.goodberry_charges: 10`` and a 14400-round duration
(24h @ 6s/round). Same charge-counter pattern as Bless Water's
v2.447.0 ``holy-water-flask`` buff.

Tests:
  - Druid (Mira) self-cast installs buff with
    goodberry_charges: 10.
  - Buff carries duration_rounds=14400 + concentration=false.
  - Ranger (Rowan) also succeeds — asserts the dual-class gate.
  - Cleric (Tavik) → 409 (NOT on Goodberry's RAW class list —
    asserts the narrow druid/ranger gate).
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    pc_cb = {
        "id": f"tok_gb_caster_{caster['id']}",
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


async def test_cast_gb_druid_installs_buff(gm_client, roster):
    """Mira (Druid) self-casts; the installed buff carries
    effects.goodberry_charges = 10."""
    druid = roster["Mira Greenleaf"]
    await _set_battle(gm_client, druid)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_goodberry",
        json={"character_id": druid["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "goodberry"
    assert body["buff_installed"] is True
    assert body["charges"] == 10
    assert body["duration_rounds"] == 14400

    buffs = await _get_buffs(gm_client, druid["id"])
    gb_buff = next(
        (b for b in buffs if b.get("key") == "goodberry"), None,
    )
    assert gb_buff is not None, f"goodberry buff missing: {buffs}"
    effects = gb_buff.get("effects") or {}
    assert effects.get("goodberry_charges") == 10


async def test_cast_gb_buff_is_24h_non_concentration(gm_client, roster):
    """The installed buff carries duration_rounds=14400 (24h) and
    concentration=false, matching RAW."""
    druid = roster["Mira Greenleaf"]
    await _set_battle(gm_client, druid)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_goodberry",
        json={"character_id": druid["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, druid["id"])
    gb_buff = next(
        (b for b in buffs if b.get("key") == "goodberry"), None,
    )
    assert gb_buff is not None
    assert gb_buff.get("concentration") is False
    assert int(gb_buff.get("duration_rounds") or 0) == 14400


async def test_cast_gb_ranger_succeeds(gm_client, roster):
    """Rowan (Ranger) succeeds — asserts the dual-class gate covers
    both Druids and Rangers."""
    if "Rowan Quickbow" not in roster:
        import pytest
        pytest.skip("no Ranger in the demo roster")
    ranger = roster["Rowan Quickbow"]
    await _set_battle(gm_client, ranger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_goodberry",
        json={"character_id": ranger["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["buff_installed"] is True


async def test_cast_gb_cleric_rejected(gm_client, roster):
    """Tavik (Cleric) → 409. Cleric is NOT on Goodberry's RAW
    class list (Druid/Ranger only). Asserts the narrow gate vs.
    Detect Evil and Good v2.456.0 which IS on Cleric's list."""
    cleric = roster["Brother Tavik Stonebrow"]
    await _set_battle(gm_client, cleric)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_goodberry",
        json={"character_id": cleric["id"]},
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "cannot_cast"
    assert "goodberry" in body["expected"].lower()
