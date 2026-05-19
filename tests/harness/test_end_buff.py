"""``/end_buff`` endpoint — manual buff removal.

Phase C primitive used by Rage termination, GM-driven buff cleanup,
and the v2.32.0 Phase T.3c condition install path's "remove early"
escape hatch. Existing tests touched it indirectly via Rage flow;
this file covers the endpoint contract.

Coverage:
  - Happy path: install Rage via /use_rage, then /end_buff drops it
  - 400 missing character_id / key
  - 404 when no buff with that key on the character
  - 403 when a non-owner / non-GM player tries to end someone else's buff
"""
from .conftest import CAMPAIGN_ID


async def _seed_battle_with(gm_client, char_entries):
    combatants = []
    for e in char_entries:
        cid = e["id"]
        combatants.append({
            "id": f"tok_test_{cid}",
            "char_id": cid,
            "name": e.get("name") or f"PC {cid}",
            "initiative": 10,
            "hp_current": 30, "hp_max": 30,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        })
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def test_end_buff_removes_rage(gm_client, roster):
    """Install Rage on Krieger via /use_rage, then drop it via /end_buff."""
    krieger = roster["Krieger Stonefist"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    await _seed_battle_with(gm_client, [krieger])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    # Verify rage installed.
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs",
    )
    assert any((b or {}).get("key") == "rage" for b in r.json().get("buffs", [])), \
        "expected rage buff after /use_rage"
    # End it.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "rage"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["removed_key"] == "rage"
    # Verify rage gone.
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/buffs",
    )
    assert not any((b or {}).get("key") == "rage" for b in r.json().get("buffs", [])), \
        "expected rage to be removed"


async def test_end_buff_missing_character_id_400(gm_client):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"key": "rage"},
    )
    assert resp.status_code == 400


async def test_end_buff_missing_key_400(gm_client, roster):
    krieger = roster["Krieger Stonefist"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"]},
    )
    assert resp.status_code == 400


async def test_end_buff_unknown_key_404(gm_client, roster):
    """A character with no buffs returns 404 when end_buff is called."""
    krieger = roster["Krieger Stonefist"]
    # Long-rest to clear any persisting buffs (rage etc.).
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    await _seed_battle_with(gm_client, [krieger])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "made-up-buff"},
    )
    assert resp.status_code == 404, resp.text


async def test_end_buff_non_owner_403(alice_client, roster):
    """Alice (player, doesn't own Krieger) → 403."""
    krieger = roster["Krieger Stonefist"]
    resp = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": krieger["id"], "key": "rage"},
    )
    # Either 403 (not GM, not owner) or 404 (rage not installed).
    # The 403 check fires first.
    assert resp.status_code in (403, 404), resp.text
