"""/api/campaign/{cid}/use_rage — Barbarian Lv 1 feature tests.

v2.19.0 Phase C.1: Rage is the first user of the buff-slot infrastructure.
Krieger (Lv 5 Barbarian Path of the Berserker, demo PC since v2.18.2)
has the resource counter at 3/3 long-rest refresh. The endpoint
installs a structured rage buff on the combatant in the hub battle
state (carrying duration_rounds, effects, etc.) + decrements the
Rage counter + marks the bonus chip.

Tests:
  - happy path: Krieger activates Rage; response carries damage_bonus
    (+2 at Lv 5), duration_rounds (10), buff_installed=True; broadcasts
    fire (feature_used + resource_update + buff_update)
  - 409 out_of_uses (drain-loop)
  - 409 wrong-class (Pip is Rogue)
  - 400 missing character_id
  - end_buff: Krieger ends his Rage manually; buff_update broadcast +
    empty list response
  - end_buff: 404 when key isn't on the combatant
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def krieger_full(gm_client, roster):
    """Long-rest Krieger to refill Rage counter before each test.
    Without this fixture other tests can deplete his counter and
    leave state ambiguous.
    """
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    return krieger


async def _seed_battle_with(gm_client, char_ids: list[int]) -> None:
    """Put a minimal battle state in the hub so _install_buff /
    _mark_battle_economy have a combatant to mutate. Mirrors the
    pattern in test_use_second_wind / test_use_action_surge.
    """
    combatants = []
    for cid in char_ids:
        combatants.append({
            "id": f"tok_test_{cid}",
            "char_id": cid,
            "name": f"PC {cid}",
            "initiative": 10,
            "hp_current": 30,
            "hp_max": 30,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        })
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def test_rage_happy_path(gm_client, gm_ws, krieger_full):
    """Krieger activates Rage. Asserts: 200 response, damage_bonus 2
    (Lv 7 — +2 holds through Lv 1-8), duration_rounds 10, remaining
    decremented from 4 to 3 (v2.57.0 bumped Krieger Lv 5 → 7, which
    in turn bumps Rage uses 3 → 4 per Lv 6+ RAW),
    feature_used + resource_update + buff_update broadcasts fire.
    """
    krieger = krieger_full
    await _seed_battle_with(gm_client, [krieger["id"]])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["damage_bonus"] == 2  # Lv 1-8 Barbarian
    assert data["duration_rounds"] == 10
    assert data["remaining"] == 3  # was 4, decremented
    assert data["max"] == 4
    assert data["buff_installed"] is True

    fu = await gm_ws.wait_for("feature_used")
    assert fu["data"]["source"] == "rage"
    assert "Rage" in fu["data"]["feature_name"]

    ru = await gm_ws.wait_for("resource_update")
    assert ru["data"]["key"] == "rage"
    assert ru["data"]["current"] == 3

    bu = await gm_ws.wait_for("buff_update")
    assert bu["data"]["character_id"] == krieger["id"]
    buffs = bu["data"]["buffs"]
    assert len(buffs) == 1
    rage = buffs[0]
    assert rage["key"] == "rage"
    assert rage["name"] == "Rage"
    assert rage["duration_rounds"] == 10
    assert rage["duration_max"] == 10
    assert rage["effects"]["melee_str_damage_bonus"] == 2
    assert "bludgeoning" in rage["effects"]["resistance_to"]


async def test_rage_out_of_uses(gm_client, krieger_full):
    """Drain Rage to 0 then attempt again — 409 out_of_uses.

    v2.57.0: Krieger now has 4 rage uses at Lv 7 (was 3 at Lv 5).
    """
    krieger = krieger_full
    await _seed_battle_with(gm_client, [krieger["id"]])
    for _ in range(4):
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_rage",
            json={"character_id": krieger["id"], "override": True},
        )
        assert resp.status_code == 200, resp.text

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert resp.status_code == 409
    assert resp.json().get("error") == "out_of_uses"


async def test_rage_wrong_class(gm_client, roster):
    """Pip is a Rogue — no Barbarian level. Endpoint returns 409."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": pip["id"], "override": True},
    )
    assert resp.status_code == 409
    detail = resp.json().get("detail", "")
    assert "Barbarian" in detail


async def test_rage_missing_character_id(gm_client):
    """Missing character_id returns 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={},
    )
    assert resp.status_code == 400


async def test_end_buff_happy_path(gm_client, gm_ws, krieger_full):
    """Install Rage, then call /end_buff. Expects 200 + buff_update
    broadcast with an empty buffs list."""
    krieger = krieger_full
    await _seed_battle_with(gm_client, [krieger["id"]])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert resp.status_code == 200
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "rage"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["removed_key"] == "rage"

    bu = await gm_ws.wait_for("buff_update")
    assert bu["data"]["character_id"] == krieger["id"]
    assert bu["data"]["removed_key"] == "rage"
    assert bu["data"]["buffs"] == []


async def test_end_buff_not_found(gm_client, roster):
    """End a buff that isn't on the combatant — 404."""
    krieger = roster["Krieger Stonefist"]
    await _seed_battle_with(gm_client, [krieger["id"]])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "rage"},
    )
    assert resp.status_code == 404


async def test_end_buff_missing_fields(gm_client):
    """Missing character_id or key returns 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"key": "rage"},
    )
    assert resp.status_code == 400

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": 1},
    )
    assert resp.status_code == 400
