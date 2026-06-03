"""v2.99.148 — /cast_compulsion endpoint tests.

L4 Enchantment, concentration up to 1 minute, 30 ft radius
caster-centered, WIS save (per-target saves are filed). Bard,
Wizard. Warlock-only via the v2.99.148 Bewitching Whispers
invocation (PHB p.110: "Prerequisite: 7th level. You can cast
Compulsion once using a warlock spell slot. You can't do so
again until you finish a long rest.").

This is the spell-side half — slot decrement + invocation gate
+ concentration anchor + audit. Per-target WIS save resolution
+ the per-turn movement compulsion are filed.

Third consumer of the v2.99.140 invocation-cast registry — after
v2.99.137 Mire the Mind + v2.99.142 Sculptor of Flesh. Proves
the abstraction generalizes across multiple spells.

Magnus has eldritch-invocation-bewitching-whispers on his feats
list + a bewitching-whispers-uses 1/long-rest resource.

Tests:
  - happy path (Magnus via Bewitching Whispers) → 200; slot +
    resource decrement; caster gets the concentration anchor
  - Warlock without via_invocation → 409 missing_invocation
  - Warlock with wrong via_invocation (mire-the-mind, spell_slug
    mismatch) → 409 missing_invocation
  - second cast same long rest → 409 not_enough_uses
  - L3 slot → 400 (Compulsion is L4)
  - missing character_id → 400
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _mkc(cid, char_id=None, name="X", speed_walk=30):
    return {
        "id": cid,
        "char_id": char_id,
        "name": name,
        "initiative": 10,
        "hp_current": 50, "hp_max": 50,
        "speed_walk": speed_walk,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _get_buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    return {(b or {}).get("key") for b in resp.json().get("buffs") or []}


@pytest_asyncio.fixture
async def magnus_rested(gm_client, roster):
    """Long-rest Magnus so Bewitching Whispers use is fresh."""
    magnus = roster["Magnus Hexbinder"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    return magnus


async def test_bewitching_whispers_happy_path(
    gm_client, magnus_rested,
):
    """Magnus casts Compulsion via Bewitching Whispers → 200;
    caster gets the compulsion concentration anchor.
    """
    magnus = magnus_rested
    mg_tok = f"tok_bw_mg_{magnus['id']}"
    await _seed_battle(gm_client, [
        _mkc(mg_tok, magnus["id"], name=magnus["name"]),
    ])
    # Magnus is Lv 5 Warlock — his Pact Magic slots are L3 only.
    # Patch in an L4 slot for this test.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"spell_slots": {"warlock": {
            "3": {"total": 2, "used": 0},
            "4": {"total": 1, "used": 0},
        }}},
    )
    try:
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_compulsion",
            json={
                "character_id": magnus["id"],
                "class_slug": "warlock",
                "via_invocation": "bewitching-whispers",
                "slot_level": 4,
                "override": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["ok"] is True
        assert data["concentration"] is True
        assert data["range_ft"] == 30
        assert data["via_invocation"] == "bewitching-whispers"
        # Magnus has the concentration anchor.
        mg_keys = await _get_buff_keys(gm_client, magnus["id"])
        assert "concentration-compulsion" in mg_keys
    finally:
        # Restore Magnus's seed slot config (L3 only).
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"spell_slots": {"warlock": {
                "3": {"total": 2, "used": 0},
            }}},
        )


async def test_warlock_without_via_invocation_409(
    gm_client, magnus_rested,
):
    """class_slug=warlock without via_invocation → 409
    missing_invocation (Compulsion isn't a Warlock spell).
    """
    magnus = magnus_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_compulsion",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "slot_level": 4,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"
    assert data.get("invocation") == "bewitching-whispers"


async def test_warlock_wrong_invocation_409(
    gm_client, magnus_rested,
):
    """class_slug=warlock + via_invocation="mire-the-mind" → 409
    missing_invocation. The registry rejects because Mire the
    Mind's spell_slug is "slow", not "compulsion".
    """
    magnus = magnus_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_compulsion",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "mire-the-mind",
            "slot_level": 4,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"


async def test_bewitching_whispers_second_cast_409(
    gm_client, magnus_rested,
):
    """Two consecutive Bewitching Whispers casts (no rest) →
    second is 409 not_enough_uses (1/long-rest gate).
    """
    magnus = magnus_rested
    mg_tok = f"tok_bw_2x_mg_{magnus['id']}"
    await _seed_battle(gm_client, [
        _mkc(mg_tok, magnus["id"], name=magnus["name"]),
    ])
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"spell_slots": {"warlock": {
            "3": {"total": 2, "used": 0},
            "4": {"total": 2, "used": 0},
        }}},
    )
    try:
        cast1 = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_compulsion",
            json={
                "character_id": magnus["id"],
                "class_slug": "warlock",
                "via_invocation": "bewitching-whispers",
                "slot_level": 4,
                "override": True,
            },
        )
        assert cast1.status_code == 200, cast1.text
        # Second cast — same long rest, should 409 not_enough_uses.
        cast2 = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_compulsion",
            json={
                "character_id": magnus["id"],
                "class_slug": "warlock",
                "via_invocation": "bewitching-whispers",
                "slot_level": 4,
                "override": True,
            },
        )
        assert cast2.status_code == 409, cast2.text
        data = cast2.json()
        assert data.get("error") == "not_enough_uses"
        assert data.get("resource_key") == "bewitching-whispers-uses"
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"spell_slots": {"warlock": {
                "3": {"total": 2, "used": 0},
            }}},
        )


async def test_cast_compulsion_l3_slot_400(gm_client, magnus_rested):
    """slot_level=3 → 400 (Compulsion is L4)."""
    magnus = magnus_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_compulsion",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "bewitching-whispers",
            "slot_level": 3,
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_cast_compulsion_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_compulsion",
        json={"class_slug": "warlock"},
    )
    assert resp.status_code == 400, resp.text
