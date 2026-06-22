"""Forbiddance — L6 abjuration, Cleric.
Phase 2 #67 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.553.0 — RAW PHB p.243: "You create a ward against magical travel ...
A creature of the chosen type or alignment takes 5d10 radiant or
necrotic damage ... when it enters the area for the first time on a turn
or starts its turn there." Touch, 24 hours, non-concentration. The last
AoE-shape gap from the SRD audit — a GM-narrated warded zone in the Zone
of Truth mould, but baking a damage marker (5d10 + type) instead of a
save-DC.

Tests:
  - Self-cast installs a non-concentration `forbiddance` buff carrying
    5d10 + default radiant + default warded_type (24h).
  - A chosen necrotic type + named warded_type surface; an invalid
    damage_type falls back to radiant.
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _tok(char, tid=None, init=10):
    return {
        "id": tid or f"tok_fb_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": init,
        "hp_current": 40, "hp_max": 40,
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


async def _buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(gm_client, roster):
    yield
    tavik = roster.get("Brother Tavik Stonebrow")
    if tavik:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": tavik["id"], "key": "forbiddance"},
        )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
    )


async def test_cast_forbiddance_installs_ward_buff(gm_client, roster):
    """Self-cast → non-concentration `forbiddance` buff with 5d10 +
    default radiant + default warded_type (24h)."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _set_battle(gm_client, [_tok(tavik)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_forbiddance",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "forbiddance"
    assert body["damage_dice"] == "5d10"
    assert body["damage_type"] == "radiant"
    assert body["warded_type"] == "your chosen creatures"
    assert body["duration_rounds"] == 14400

    buffs = await _buffs(gm_client, tavik["id"])
    fb = next((b for b in buffs if b.get("key") == "forbiddance"), None)
    assert fb is not None, f"buff missing: {buffs}"
    assert fb.get("concentration") is False
    eff = fb.get("effects") or {}
    assert eff.get("forbiddance") is True
    assert eff.get("ward_damage_dice") == "5d10"
    assert eff.get("ward_damage_type") == "radiant"


async def test_cast_forbiddance_necrotic_and_warded_type(gm_client, roster):
    """A chosen necrotic type + named warded_type surface; an invalid
    damage_type falls back to radiant."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _set_battle(gm_client, [_tok(tavik)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_forbiddance",
        json={"character_id": tavik["id"], "damage_type": "necrotic",
              "warded_type": "fiends"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["damage_type"] == "necrotic"
    assert body["warded_type"] == "fiends"
    buffs = await _buffs(gm_client, tavik["id"])
    fb = next((b for b in buffs if b.get("key") == "forbiddance"), None)
    eff = fb.get("effects") or {}
    assert eff.get("ward_damage_type") == "necrotic"
    assert eff.get("warded_type") == "fiends"

    # Invalid damage type → radiant fallback.
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_forbiddance",
        json={"character_id": tavik["id"], "damage_type": "fire"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["damage_type"] == "radiant"


async def test_cast_forbiddance_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_forbiddance",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "forbiddance" in r.json()["expected"].lower()


async def test_cast_forbiddance_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_forbiddance",
        json={},
    )
    assert r.status_code == 400, r.text
