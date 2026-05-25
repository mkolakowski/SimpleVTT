"""/api/campaign/{cid}/use_stillness_of_mind — Monk Lv 7 feature.

v2.49.229: Stillness of Mind shipped end-to-end. RAW (PHB p.79):
"Starting at 7th level, you can use your action to end one effect
on yourself that is causing you to be charmed or frightened."

Endpoint validates class==monk + level≥7 + buff_key is in
{charmed, frightened}, removes the matching buff from the monk's
buff list via the same `_remove_buff` helper /end_buff uses, marks
the action slot.

Tests:
  - happy path: seed Kael with a Charmed buff → POST → 200; buff
    removed; feature_used + buff_update broadcasts fire
  - happy path frightened: seed Frightened, end it
  - 409 wrong_class: Pip (Rogue)
  - 409 wrong_condition: pass buff_key="stunned"
  - 404 buff_not_present: no Charmed/Frightened on Kael
  - 400 missing buff_key
  - 400 missing character_id
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def kael_rested(gm_client, roster):
    """Long-rest Kael to clear any prior battle state."""
    kael = roster["Kael Brightleaf"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/rest",
        json={"type": "long"},
    )
    return kael


async def _seed_kael_with_buff(gm_client, kael, buff_key, buff_name):
    """Seed a single-combatant battle with Kael carrying the named
    condition buff. The shape mirrors what /cast_spell would install
    for Charm Person / Fear so the endpoint sees a realistic buff.
    """
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_som_{kael['id']}",
                "char_id": kael["id"],
                "name": kael["name"],
                "initiative": 10,
                "hp_current": 52, "hp_max": 52,
                "buffs": [{
                    "key": buff_key,
                    "name": buff_name,
                    "icon": "💗" if buff_key == "charmed" else "😱",
                    "source_caster_id": None,
                    "target_combatant_id": None,
                    "duration_rounds": 10,
                    "duration_max": 10,
                    "concentration": False,
                    "effects": ["status condition rider"],
                }],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def test_stillness_of_mind_clears_charmed(gm_client, gm_ws, kael_rested):
    """Kael with a Charmed buff → POST → 200 + buff removed + broadcasts."""
    kael = kael_rested
    await _seed_kael_with_buff(gm_client, kael, "charmed", "Charmed")
    gm_ws.mark()  # discard seed broadcast
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_stillness_of_mind",
        json={"character_id": kael["id"], "buff_key": "charmed", "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["removed_key"] == "charmed"
    assert data["removed_name"] == "Charmed"

    # buff_update broadcast (from _remove_buff) shows the buff is gone.
    bu = await gm_ws.wait_for("buff_update", timeout=2.0)
    bu_data = bu.get("data") or {}
    assert bu_data.get("character_id") == kael["id"]
    remaining = [b for b in (bu_data.get("buffs") or []) if (b or {}).get("key") == "charmed"]
    assert remaining == [], f"Charmed buff should be removed; got {bu_data.get('buffs')}"

    # feature_used roll-log card for the use.
    fu = await gm_ws.wait_for("feature_used", timeout=2.0)
    assert fu["data"]["source"] == "stillness-of-mind"
    assert "Stillness of Mind" in fu["data"]["feature_name"]
    assert fu["data"]["removed_key"] == "charmed"
    assert fu["data"]["removed_name"] == "Charmed"


async def test_stillness_of_mind_clears_frightened(gm_client, kael_rested):
    """Same path, frightened buff variant."""
    kael = kael_rested
    await _seed_kael_with_buff(gm_client, kael, "frightened", "Frightened")
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_stillness_of_mind",
        json={"character_id": kael["id"], "buff_key": "frightened", "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["removed_key"] == "frightened"
    assert data["removed_name"] == "Frightened"


async def test_stillness_of_mind_wrong_class(gm_client, roster):
    """Pip (Rogue) → 409 wrong_class."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_stillness_of_mind",
        json={"character_id": pip["id"], "buff_key": "charmed", "override": True},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "wrong_class"
    assert body["expected"] == "monk"
    assert body["got"] == "rogue"


async def test_stillness_of_mind_wrong_condition(gm_client, kael_rested):
    """buff_key='stunned' (not charmed/frightened) → 409 wrong_condition.

    Stillness of Mind RAW only ends charmed/frightened. The endpoint
    refuses other buff keys so a monk can't cheese their way out of
    Paralyzed / Stunned / etc.
    """
    kael = kael_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_stillness_of_mind",
        json={"character_id": kael["id"], "buff_key": "stunned", "override": True},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "wrong_condition"
    assert body["got"] == "stunned"
    assert "charmed" in body["allowed"]
    assert "frightened" in body["allowed"]


async def test_stillness_of_mind_buff_not_present(gm_client, kael_rested):
    """Kael without a Charmed buff → 404 buff_not_present."""
    kael = kael_rested
    # Seed a battle with NO Charmed/Frightened buff so the lookup misses.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_som_empty_{kael['id']}",
                "char_id": kael["id"],
                "name": kael["name"],
                "initiative": 10,
                "hp_current": 52, "hp_max": 52,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_stillness_of_mind",
        json={"character_id": kael["id"], "buff_key": "charmed", "override": True},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "buff_not_present"
    assert body["buff_key"] == "charmed"


async def test_stillness_of_mind_missing_buff_key(gm_client, kael_rested):
    """Missing buff_key → 400."""
    kael = kael_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_stillness_of_mind",
        json={"character_id": kael["id"]},
    )
    assert resp.status_code == 400


async def test_stillness_of_mind_missing_character_id(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_stillness_of_mind",
        json={"buff_key": "charmed"},
    )
    assert resp.status_code == 400
