"""Antilife Shell — L5 abjuration, Druid.
Phase 2 #45 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.512.0 — RAW PHB p.213: "A shimmering barrier extends out from you in
a 10-foot radius and moves with you ... hedging out creatures other than
undead and constructs. ... The barrier prevents an affected creature
from passing or reaching through." Concentration, up to 1 hour.

New ``_SPELL_BUFF_MAP["antilife-shell"]`` substrate carrying
``effects.antilife_shell: True`` — flag-buff shape (same as the other
geometry-bound tail spells). The moving 10-ft radius + the hedge
enforcement are a new movement-barrier substrate filed against Maps 2.0;
v1 surfaces the flag and GM-narrates the barrier.

Tests:
  - Druid self-cast installs the buff with antilife_shell: true.
  - Buff carries duration_rounds=600 (1 hour) + concentration=true.
  - Krieger (Barbarian) → 409 cannot_cast (Druid-only RAW gate).
  - Wizard (Thalindra) → 409 (Antilife Shell is NOT on the wizard list).
  - Missing character_id → 400.
"""
from .conftest import CAMPAIGN_ID


async def _set_battle(gm_client, caster):
    pc_cb = {
        "id": f"tok_als_caster_{caster['id']}",
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


def _find_druid(roster):
    for name in ("Mira Greenleaf",):
        if name in roster:
            return roster[name]
    return None


async def test_cast_als_druid_installs_buff(gm_client, roster):
    """A Druid self-casts Antilife Shell; the installed buff carries
    effects.antilife_shell = true."""
    druid = _find_druid(roster)
    if druid is None:
        import pytest
        pytest.skip("no Druid in the demo roster")
    await _set_battle(gm_client, druid)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_antilife_shell",
        json={"character_id": druid["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "antilife-shell"
    assert body["buff_installed"] is True
    assert body["duration_rounds"] == 600

    buffs = await _get_buffs(gm_client, druid["id"])
    als = next(
        (b for b in buffs if b.get("key") == "antilife-shell"), None,
    )
    assert als is not None, f"antilife-shell buff missing: {buffs}"
    assert (als.get("effects") or {}).get("antilife_shell") is True


async def test_cast_als_buff_is_1_hour_concentration(gm_client, roster):
    """The installed buff carries duration_rounds=600 (1 hour) and
    concentration=true, matching RAW."""
    druid = _find_druid(roster)
    if druid is None:
        import pytest
        pytest.skip("no Druid in the demo roster")
    await _set_battle(gm_client, druid)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_antilife_shell",
        json={"character_id": druid["id"]},
    )
    assert r.status_code == 200, r.text
    buffs = await _get_buffs(gm_client, druid["id"])
    als = next(
        (b for b in buffs if b.get("key") == "antilife-shell"), None,
    )
    assert als is not None
    assert als.get("concentration") is True
    assert int(als.get("duration_rounds") or 0) == 600


async def test_cast_als_barbarian_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_antilife_shell",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "antilife shell" in r.json()["expected"].lower()


async def test_cast_als_wizard_rejected(gm_client, roster):
    """Thalindra (Wizard) → 409 — Antilife Shell is Druid-only RAW, NOT
    on the wizard list (asserts the narrow single-class gate)."""
    wiz = roster["Thalindra Moonwhisper"]
    await _set_battle(gm_client, wiz)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_antilife_shell",
        json={"character_id": wiz["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"


async def test_cast_als_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_antilife_shell",
        json={},
    )
    assert r.status_code == 400, r.text
