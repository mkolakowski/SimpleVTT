"""v2.99.376 — Banneret Fighter: Rallying Cry (G Fighter sweep CLOSE, Lv 3+, SCAG).

Phase G Fighter martial archetype sweep ship #7 — Banneret /
Purple Dragon Knight opens and CLOSES the Fighter sweep.
RAW SCAG p.128: when you use Second Wind, up to three allies
within 60 ft who can see or hear you each regain HP = your fighter
level.

v1 announce-only — the ally targeting + HP application are
GM-tracked. The per-ally heal is computed server-side. No separate
action cost (a rider on Second Wind).

Garrik Ironside (Fighter, PATCHed to Banneret Lv 9) is the demo
fixture (heal 9 per ally).

Tests:
  - Lv 9 happy: heal_per_ally 9, max_allies 3, range 60.
  - Wrong subclass (default Champion) → 409.
  - Wrong class (Caelan paladin) → 409.
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


def _rc_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "rallying-cry"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def garrik_banneret(gm_client, roster):
    """PATCH Garrik to Banneret; restore to Champion on teardown."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Banneret"},
        class_slug="fighter",
    )
    try:
        yield garrik
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion"},
            class_slug="fighter",
        )


async def test_use_rc_happy_lv9(
    gm_client, gm_ws, garrik_banneret,
):
    """Lv 9 Banneret → heal 9 per ally, up to 3 allies, 60 ft."""
    garrik = garrik_banneret
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rallying_cry",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "rallying-cry"
    assert data["heal_per_ally"] == 9  # fighter level
    assert data["max_allies"] == 3
    assert data["range_ft"] == 60
    assert data["fighter_level"] == 9
    await asyncio.sleep(0.3)
    feats = _rc_broadcasts(gm_ws, garrik["id"])
    assert feats
    assert feats[-1]["data"]["heal_per_ally"] == 9


async def test_use_rc_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rallying_cry",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_rc_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rallying_cry",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


def _npc(cid, name, hp_cur=10, hp_max=30):
    return {
        "id": cid, "char_id": None, "name": name,
        "initiative": 5, "hp_current": hp_cur, "hp_max": hp_max, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def test_rallying_cry_heals_allies(
    gm_client, garrik_banneret,
):
    """v2.99.454 — Rallying Cry heals the supplied allies by fighter
    level (9). Two damaged allies (10/30) each regain 9 → applied 9."""
    garrik = garrik_banneret
    a1, a2 = "tok_rc_a1", "tok_rc_a2"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_rc_g_{garrik['id']}", "char_id": garrik["id"],
             "name": garrik["name"], "initiative": 20,
             "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            _npc(a1, "Ally One"),
            _npc(a2, "Ally Two"),
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rallying_cry",
        json={"character_id": garrik["id"],
              "target_combatant_ids": [a1, a2]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    healed = {h["combatant_id"]: h for h in data["healed"]}
    assert healed[a1]["applied"] == 9  # fighter level
    assert healed[a2]["applied"] == 9


async def test_rallying_cry_caps_at_three_allies(
    gm_client, garrik_banneret,
):
    """At most 3 allies are healed even if 4 ids are supplied."""
    garrik = garrik_banneret
    ids = ["tok_rc_b1", "tok_rc_b2", "tok_rc_b3", "tok_rc_b4"]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_rc_g2_{garrik['id']}", "char_id": garrik["id"],
             "name": garrik["name"], "initiative": 20,
             "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ] + [_npc(i, f"Ally {i}") for i in ids],
        "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rallying_cry",
        json={"character_id": garrik["id"], "target_combatant_ids": ids},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["healed"]) == 3  # capped
