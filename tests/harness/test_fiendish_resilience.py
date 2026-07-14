"""v2.1015.0 — Fiendish Resilience (The Fiend Warlock Lv 10+, PHB p.110).

"You can choose one damage type when you finish a short or long rest.
You gain resistance to that damage type until you choose a different one
with this feature." The Fiend is the SRD warlock patron, so this is
SRD-valid. Magnus Hexbinder (Warlock The Fiend Lv 5) is the demo
fixture, PATCH'd to Lv 10. `_install_buff` needs an active battle, so
the happy paths seed one.

Tests:
  - Happy path: Magnus@Lv10 picks "fire" → a `fiendish-resilience` buff
    with `effects.resistance_to: ["fire"]` (asserted via the buff_update
    WS + GET /buffs), mirrored to the sheet.
  - Re-pick: choosing "cold" replaces the buff (resistance_to flips,
    single buff by stable key).
  - Bad damage type → 400.
  - Level gate: Magnus@Lv5 → 409.
  - Error paths: missing character_id → 400; unknown char → 404.
"""
import asyncio

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


def _pc(cid, c, *, hp_max=90):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed(gm_client, magnus):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_pc(f"tok_fr_magnus_{magnus['id']}", magnus)],
              "turn_index": 0, "round": 1, "active": True},
    )


async def _fr_buff(gm_client, char_id):
    buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs"
    )).json().get("buffs", [])
    return next(
        (b for b in buffs if (b or {}).get("key") == "fiendish-resilience"),
        None,
    )


async def test_fiendish_resilience_grants_resistance(gm_client, roster):
    """Magnus@Lv10 picks fire → a fiendish-resilience buff carrying
    resistance_to: ["fire"]."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(gm_client, magnus["id"], {"level": 10},
                       class_slug="warlock")
    try:
        await _seed(gm_client, magnus)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_fiendish_resilience",
            json={"character_id": magnus["id"], "damage_type": "fire"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["damage_type"] == "fire"
        assert data["buff_installed"] is True
        await asyncio.sleep(0.2)
        buff = await _fr_buff(gm_client, magnus["id"])
        assert buff is not None, "fiendish-resilience buff missing"
        assert (buff.get("effects") or {}).get("resistance_to") == ["fire"]
    finally:
        await _patch_sheet(gm_client, magnus["id"], {"level": 5},
                           class_slug="warlock")


async def test_fiendish_resilience_repick_replaces(gm_client, roster):
    """Re-invoking with a different type flips the resistance (single
    buff by stable key)."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(gm_client, magnus["id"], {"level": 10},
                       class_slug="warlock")
    try:
        await _seed(gm_client, magnus)
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_fiendish_resilience",
            json={"character_id": magnus["id"], "damage_type": "fire"},
        )
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_fiendish_resilience",
            json={"character_id": magnus["id"], "damage_type": "cold"},
        )
        assert r.status_code == 200, r.text
        await asyncio.sleep(0.2)
        buff = await _fr_buff(gm_client, magnus["id"])
        assert buff is not None
        assert (buff.get("effects") or {}).get("resistance_to") == ["cold"]
    finally:
        await _patch_sheet(gm_client, magnus["id"], {"level": 5},
                           class_slug="warlock")


async def test_fiendish_resilience_bad_damage_type(gm_client, roster):
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(gm_client, magnus["id"], {"level": 10},
                       class_slug="warlock")
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_fiendish_resilience",
            json={"character_id": magnus["id"], "damage_type": "sonic"},
        )
        assert r.status_code == 400, r.text
    finally:
        await _patch_sheet(gm_client, magnus["id"], {"level": 5},
                           class_slug="warlock")


async def test_fiendish_resilience_level_gate(gm_client, roster):
    """Magnus at Lv 5 → 409 (Fiendish Resilience needs Lv 10)."""
    magnus = roster["Magnus Hexbinder"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fiendish_resilience",
        json={"character_id": magnus["id"], "damage_type": "fire"},
    )
    assert r.status_code == 409, r.text
    assert r.json().get("error") == "wrong_subclass_or_level"


async def test_fiendish_resilience_missing_character_id(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fiendish_resilience",
        json={"damage_type": "fire"},
    )
    assert r.status_code == 400, r.text


async def test_fiendish_resilience_unknown_character(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_fiendish_resilience",
        json={"character_id": 99999999, "damage_type": "fire"},
    )
    assert r.status_code == 404, r.text
