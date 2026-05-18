"""/api/campaign/{cid}/attack — weapon attack endpoint tests.

Coverage in this Phase 1 vertical slice:
  - Pip's Shortsword (PC, attack_index 0)
  - Pip's Dagger (PC, attack_index 1)
  - Tavik's Warhammer (PC, attack_index 0)
  - 404 on unknown attack_index

Phase 1.5 will add: bandit / monster strikes via /roll (separate path),
save-DC-based attacks (Sacred Flame), over-budget gate parametrization.
"""
from .conftest import CAMPAIGN_ID


async def test_attack_pip_shortsword(gm_client, gm_ws, roster):
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"], "attack_index": 0, "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["attack_name"] == "Shortsword"
    # 1d20+6 produces a total between 7 and 26.
    assert 7 <= data["attack_total"] <= 26
    # Breakdown format: "1d20[N]=N 6  =>  total". Just check the d20
    # part landed and the total is consistent.
    assert "1d20" in data["attack_breakdown"]
    # Damage: 1d6+3 → 4-9
    assert 4 <= data["damage_total"] <= 9
    assert data["damage_type"] == "piercing"

    msg = await gm_ws.wait_for("weapon_attack")
    assert msg["data"]["attack_name"] == "Shortsword"
    assert msg["data"]["caster_char_name"] == "Pip Quickfingers"
    assert msg["data"]["damage_type"] == "piercing"
    # over_budget can be True or False depending on whether Pip's
    # action chip was already burnt from a prior test or run. The
    # realtime hub keeps battle state in-memory across requests, so
    # the chip persists until init advances. Phase 1.5 adds per-test
    # battle-state reset; for now we just assert the field is present
    # and a bool.
    assert "over_budget" in msg["data"]
    assert isinstance(msg["data"]["over_budget"], bool)


async def test_attack_pip_dagger(gm_client, gm_ws, roster):
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"], "attack_index": 1, "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["attack_name"] == "Dagger (thrown)"
    # 1d4+3 → 4-7
    assert 4 <= data["damage_total"] <= 7

    msg = await gm_ws.wait_for("weapon_attack")
    assert msg["data"]["range"] == "20/60 ft"


async def test_attack_tavik_warhammer(gm_client, gm_ws, roster):
    """The v2.7.3 regression target: clicking Tavik's Warhammer should
    fire a weapon_attack broadcast that produces a roll toast."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": tavik["id"], "attack_index": 0, "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["attack_name"] == "Warhammer"
    # 1d8+2 → 3-10
    assert 3 <= data["damage_total"] <= 10
    assert data["damage_type"] == "bludgeoning"

    msg = await gm_ws.wait_for("weapon_attack")
    assert msg["data"]["attack_name"] == "Warhammer"
    assert msg["data"]["caster_char_name"] == "Brother Tavik Stonebrow"
    # The broadcast must carry both totals + breakdowns so the
    # roll_toast.js listener has what it needs to fire the toast.
    assert msg["data"]["attack_total"] is not None
    assert msg["data"]["attack_breakdown"]
    assert msg["data"]["damage_total"] is not None
    assert msg["data"]["damage_breakdown"]


async def test_attack_invalid_index(gm_client, roster):
    """Out-of-range attack_index returns 404."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"], "attack_index": 999, "override": True},
    )
    assert resp.status_code == 404


async def test_attack_missing_character_id(gm_client):
    """Missing character_id returns 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"attack_index": 0},
    )
    assert resp.status_code == 400
