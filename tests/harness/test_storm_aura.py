"""v2.99.367 — Path of the Storm Herald Barbarian: Storm Aura (G Barbarian #4, Lv 3+, XGE).

Phase G Barbarian Paths subclass batch ship #4 — Path of the Storm
Herald opens.
RAW XGE p.10: a 10-ft aura while raging. Desert (each other
creature in the aura takes fire damage), Sea (one creature makes a
DEX save or takes lightning), or Tundra (one creature gains temp
HP). Magnitudes scale at Lv 10/15/20.

v1 announce-only — the aura targeting + saves + HP/damage
application are GM-tracked. The Sea lightning is rolled
server-side. No action cost.

Krieger Stonefist (Barbarian, PATCHed to Path of the Storm Herald
Lv 7) is the demo fixture (base magnitudes — no tier bumps).

Tests:
  - Lv 7 happy (default desert): fire 2, aura 10 ft.
  - Lv 7 happy (sea): lightning 1d6 in [1,6], DEX save.
  - Wrong subclass (default Berserker) → 409.
  - Invalid environment → 400.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _sa_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "storm-aura"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def krieger_storm(gm_client, roster):
    """PATCH Krieger to Path of the Storm Herald; restore to Berserker."""
    krieger = roster["Krieger Stonefist"]
    await _patch_sheet(
        gm_client, krieger["id"],
        {"subclass": "Path of the Storm Herald"},
        class_slug="barbarian",
    )
    try:
        yield krieger
    finally:
        await _patch_sheet(
            gm_client, krieger["id"],
            {"subclass": "Path of the Berserker"},
            class_slug="barbarian",
        )


async def test_use_sa_happy_desert(
    gm_client, gm_ws, krieger_storm,
):
    """Lv 7 Storm Herald, default → desert, 2 fire, 10-ft aura."""
    krieger = krieger_storm
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_storm_aura",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "storm-aura"
    assert data["environment"] == "desert"
    assert data["aura_radius_ft"] == 10
    assert data["fire_damage"] == 2
    assert data["barbarian_level"] == 7
    await asyncio.sleep(0.3)
    feats = _sa_broadcasts(gm_ws, krieger["id"])
    assert feats
    assert feats[-1]["data"]["fire_damage"] == 2


async def test_use_sa_happy_sea(
    gm_client, krieger_storm,
):
    """Lv 7 sea → 1d6 lightning in [1,6], DEX save."""
    krieger = krieger_storm
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_storm_aura",
        json={"character_id": krieger["id"], "environment": "sea"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["environment"] == "sea"
    assert data["lightning_dice"] == "1d6"
    assert 1 <= data["lightning_damage"] <= 6
    assert data["save"] == "dex"


async def test_use_sa_wrong_subclass(
    gm_client, roster,
):
    """Default Krieger (Berserker) → 409."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_storm_aura",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_sa_invalid_environment(
    gm_client, krieger_storm,
):
    """Invalid environment → 400."""
    krieger = krieger_storm
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_storm_aura",
        json={"character_id": krieger["id"], "environment": "jungle"},
    )
    assert r.status_code == 400, r.text


def _npc(cid, name, hp=30):
    return {
        "id": cid, "char_id": None, "name": name,
        "initiative": 5, "hp_current": hp, "hp_max": hp, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def test_sa_desert_installs_aura_and_ticks_fire(
    gm_client, gm_ws, krieger_storm,
):
    """v2.99.426 — Phase 5.2: desert Storm Aura installs a storm-aura
    aura buff, and the v2.99.425 tick deals its fire damage to every
    other creature at the start of the barbarian's turn.

    End-to-end: activate → assert the installed buff's aura payload →
    advance the turn to the barbarian (carrying the captured buff) →
    assert each other creature took 2 fire (Lv 7 → tiers 0 → 2+0).
    """
    krieger = krieger_storm
    krieger_tok = f"tok_sa_krieger_{krieger['id']}"
    npc_a, npc_b = "tok_sa_a", "tok_sa_b"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": krieger_tok, "char_id": krieger["id"], "name": krieger["name"],
             "initiative": 20, "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            _npc(npc_a, "Bandit A"),
            _npc(npc_b, "Bandit B"),
        ], "turn_index": 1, "round": 1, "active": True},
    )

    # Activate the desert aura → installs the storm-aura buff on Krieger.
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_storm_aura",
        json={"character_id": krieger["id"], "environment": "desert"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["aura_installed"] is True

    bu = await gm_ws.wait_for("buff_update")
    sa = next((b for b in bu["data"]["buffs"]
               if b.get("key") == "storm-aura"), None)
    assert sa is not None, bu["data"]["buffs"]
    aura = (sa.get("effects") or {}).get("aura") or {}
    assert aura.get("radius_ft") == 10
    assert aura.get("affects") == "others"
    assert (aura.get("damage") or {}).get("type") == "fire"
    assert (aura.get("damage") or {}).get("expr") == "2"
    krieger_buffs = bu["data"]["buffs"]  # includes storm-aura

    # Advance the turn to Krieger (index 0), carrying the installed buff,
    # so the aura tick fires.
    gm_ws.mark()
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": krieger_tok, "char_id": krieger["id"], "name": krieger["name"],
             "initiative": 20, "hp_current": 60, "hp_max": 60,
             "buffs": krieger_buffs,
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            _npc(npc_a, "Bandit A"),
            _npc(npc_b, "Bandit B"),
        ], "turn_index": 0, "round": 2, "active": True},
    )
    await asyncio.sleep(0.3)
    bus = gm_ws.buffered("battle_update")
    assert bus
    combs = {c.get("id"): c for c in (bus[-1]["data"].get("combatants") or [])}
    # Each other creature took 2 fire (30 → 28).
    assert int(combs[npc_a].get("hp_current") or 0) == 28
    assert int(combs[npc_b].get("hp_current") or 0) == 28
