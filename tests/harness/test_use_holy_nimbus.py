"""v2.99.155 — /use_holy_nimbus endpoint tests.

Holy Nimbus is the Paladin Oath of Devotion Lv 20 capstone (PHB
p.87): emanate a 30 ft sunlight aura for 1 minute. Enemies
starting their turn in the bright light take 10 radiant damage;
caster has advantage on saves vs spells from fiends or undead.
1/long-rest.

v1 ships the resource decrement + caster-side buff install +
audit broadcast. The buff carries `effects` flags for downstream
engine hooks (auto-damage on enemy turn-start, save-advantage
gate, vision-layer rendering) — those hooks are filed.

Sir Caelan Lightbringer is the Paladin fixture. Stock sheet is
Lv 6 Devotion — below the Lv 20 prerequisite — so the harness
PATCHes him to Lv 20 in the fixture and restores Lv 6 in
teardown. The `holy-nimbus-uses` resource is on his seed at 1/1
(descriptive; the endpoint enforces the Lv 20 gate).

Tests:
  - happy path (Caelan at Lv 20 Devotion + fresh resource) →
    200 + buff installs + resource decrements + WS audit
  - level gate (Caelan at stock Lv 6) → 409 missing_feature
  - second use same long rest → 409 not_enough_uses
  - missing character_id → 400
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def caelan_at_lv_20_rested(gm_client, roster):
    """PATCH Sir Caelan to Paladin Lv 20 + long-rest him so the
    holy-nimbus-uses resource is fresh. Restore Lv 6 in teardown.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
        json={"class_slug": "paladin", "level": 20},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    yield caelan
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/sheet-fields",
        json={"class_slug": "paladin", "level": 6},
    )


async def _get_buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return {(b or {}).get("key") for b in resp.json().get("buffs") or []}


async def test_use_holy_nimbus_happy_path(
    gm_client, gm_ws, caelan_at_lv_20_rested,
):
    """Caelan at Lv 20 Devotion → 200 + buff installs + audit
    broadcast. Need a battle for the buff install path.
    """
    caelan = caelan_at_lv_20_rested
    cae_tok = f"tok_hn_cae_{caelan['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": cae_tok, "char_id": caelan["id"],
                "name": caelan["name"], "initiative": 10,
                "hp_current": 70, "hp_max": 70, "buffs": [],
                "economy": {"action": False, "bonus": False,
                            "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_holy_nimbus",
        json={"character_id": caelan["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["duration_rounds"] == 10
    assert data["light_radius_ft"] == 30
    assert data["damage_per_turn_radiant"] == 10
    assert data["uses_remaining"] == 0
    # Buff is installed on Caelan.
    keys = await _get_buff_keys(gm_client, caelan["id"])
    assert "holy-nimbus" in keys
    msg = await gm_ws.wait_for("feature_used")
    bd = msg["data"]
    assert bd.get("source") == "holy-nimbus"
    assert bd.get("damage_per_turn_radiant") == 10
    assert bd.get("light_radius_ft") == 30


async def test_use_holy_nimbus_below_lv_20_409(gm_client, roster):
    """Caelan at stock Lv 6 → 409 missing_feature (level gate)."""
    caelan = roster["Sir Caelan Lightbringer"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_holy_nimbus",
        json={"character_id": caelan["id"]},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_feature"
    assert data.get("feature") == "holy-nimbus"


async def test_use_holy_nimbus_second_use_409(
    gm_client, caelan_at_lv_20_rested,
):
    """Two consecutive uses (no rest) → second is 409
    not_enough_uses (1/long-rest gate).
    """
    caelan = caelan_at_lv_20_rested
    cae_tok = f"tok_hn_2x_cae_{caelan['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": cae_tok, "char_id": caelan["id"],
                "name": caelan["name"], "initiative": 10,
                "hp_current": 70, "hp_max": 70, "buffs": [],
                "economy": {"action": False, "bonus": False,
                            "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    cast1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_holy_nimbus",
        json={"character_id": caelan["id"]},
    )
    assert cast1.status_code == 200, cast1.text
    cast2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_holy_nimbus",
        json={"character_id": caelan["id"]},
    )
    assert cast2.status_code == 409, cast2.text
    data = cast2.json()
    assert data.get("error") == "not_enough_uses"
    assert data.get("resource_key") == "holy-nimbus-uses"


async def test_use_holy_nimbus_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_holy_nimbus",
        json={},
    )
    assert resp.status_code == 400, resp.text
