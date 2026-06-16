"""v2.99.150 — /cast_bane endpoint tests.

L1 Enchantment, concentration up to 1 minute, 30 ft range, up
to 3 targets, CHA save (per-target saves are filed). Bard,
Cleric. Warlock-only via the v2.99.150 Thief of Five Fates
invocation (PHB p.111: "You can cast Bane once using a warlock
spell slot. You can't do so again until you finish a long
rest.").

Fifth consumer of the v2.99.140 invocation-cast registry —
after v2.99.137 / .142 / .148 / .149. The abstraction now
covers five target spells (L1 Bane, L3 Slow, L3 Bestow Curse,
L4 Polymorph, L4 Compulsion).

Magnus has eldritch-invocation-thief-of-five-fates on his
feats list + a thief-of-five-fates-uses 1/long-rest resource.
Magnus's Pact Magic slots are L3 only — the test uses
slot_level=3 (Bane upcasts naturally; the endpoint accepts any
slot_level >= 1).

Tests:
  - happy path (Magnus via Thief of Five Fates) → 200; slot +
    resource decrement; caster gets the concentration anchor
  - Warlock without via_invocation → 409 missing_invocation
  - Warlock with wrong via_invocation (mire-the-mind) → 409
    missing_invocation
  - second cast same long rest → 409 not_enough_uses
  - L0 slot → 400 (Bane is L1)
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
    """Long-rest Magnus so Thief of Five Fates use is fresh."""
    magnus = roster["Magnus Hexbinder"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    return magnus


async def test_thief_of_five_fates_happy_path(
    gm_client, magnus_rested,
):
    """Magnus casts Bane via Thief of Five Fates → 200; caster
    gets the bane concentration anchor. Uses L3 (Magnus's Pact
    Magic slot level) since Bane upcasts naturally.
    """
    magnus = magnus_rested
    mg_tok = f"tok_tof_mg_{magnus['id']}"
    await _seed_battle(gm_client, [
        _mkc(mg_tok, magnus["id"], name=magnus["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bane",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "thief-of-five-fates",
            "slot_level": 3,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["concentration"] is True
    assert data["range_ft"] == 30
    # v2.383.0 — max_targets now scales with slot_level (RAW: 3 base
    # @ L1, +1/slot). Magnus casts at L3 (Pact Magic slot) → cap = 5.
    assert data["max_targets"] == 5
    assert data["via_invocation"] == "thief-of-five-fates"
    mg_keys = await _get_buff_keys(gm_client, magnus["id"])
    assert "concentration-bane" in mg_keys


async def test_warlock_without_via_invocation_409(
    gm_client, magnus_rested,
):
    """class_slug=warlock without via_invocation → 409
    missing_invocation (Bane isn't a Warlock spell).
    """
    magnus = magnus_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bane",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "slot_level": 1,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"
    assert data.get("invocation") == "thief-of-five-fates"


async def test_warlock_wrong_invocation_409(
    gm_client, magnus_rested,
):
    """class_slug=warlock + via_invocation="mire-the-mind" → 409
    missing_invocation. The registry rejects because Mire the
    Mind's spell_slug is "slow", not "bane".
    """
    magnus = magnus_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bane",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "mire-the-mind",
            "slot_level": 1,
            "override": True,
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"


async def test_thief_of_five_fates_second_cast_409(
    gm_client, magnus_rested,
):
    """Two consecutive Thief of Five Fates casts (no rest) →
    second is 409 not_enough_uses (1/long-rest gate).
    """
    magnus = magnus_rested
    mg_tok = f"tok_tof_2x_mg_{magnus['id']}"
    await _seed_battle(gm_client, [
        _mkc(mg_tok, magnus["id"], name=magnus["name"]),
    ])
    cast1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bane",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "thief-of-five-fates",
            "slot_level": 3,
            "override": True,
        },
    )
    assert cast1.status_code == 200, cast1.text
    # Second cast — same long rest, should 409 not_enough_uses.
    cast2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bane",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "thief-of-five-fates",
            "slot_level": 3,
            "override": True,
        },
    )
    assert cast2.status_code == 409, cast2.text
    data = cast2.json()
    assert data.get("error") == "not_enough_uses"
    assert data.get("resource_key") == "thief-of-five-fates-uses"


async def test_cast_bane_l0_slot_400(gm_client, magnus_rested):
    """slot_level=0 → 400 (Bane is L1)."""
    magnus = magnus_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bane",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "thief-of-five-fates",
            "slot_level": 0,
            "override": True,
        },
    )
    assert resp.status_code == 400, resp.text


async def test_cast_bane_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bane",
        json={"class_slug": "warlock"},
    )
    assert resp.status_code == 400, resp.text


# ── v2.383.0 upcast-aware max_targets cap (RAW PHB p.216: 3 base @ L1,
# +1/slot above 1st). Fires before slot consumption; pre-targets are
# pre-validated and rejected at 400. Per-target buff install stays
# filed — these tests confirm the cap-enforcement contract only. ─────


async def test_cast_bane_l3_six_targets_returns_400(
    gm_client, magnus_rested,
):
    """L3 Bane with 6 target ids → 400 too_many_targets, limit=5.
    Magnus casts at L3 (his Pact Magic slot level) → cap = 3 + 2 = 5;
    6 ids exceeds that."""
    magnus = magnus_rested
    mg_tok = f"tok_bane_cap_mg_{magnus['id']}"
    await _seed_battle(gm_client, [
        _mkc(mg_tok, magnus["id"], name=magnus["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bane",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "thief-of-five-fates",
            "slot_level": 3,
            "override": True,
            "target_combatant_ids": [
                "tok_bane_t1", "tok_bane_t2", "tok_bane_t3",
                "tok_bane_t4", "tok_bane_t5", "tok_bane_t6",
            ],
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "too_many_targets"
    assert body.get("spell") == "bane"
    assert body.get("limit") == 5
    assert body.get("received") == 6
    assert body.get("slot_level") == 3


async def test_cast_bane_l3_five_targets_succeeds(
    gm_client, magnus_rested,
):
    """L3 Bane with 5 target ids → 200 (RAW upcast cap = 5). The
    response carries the scaled max_targets=5 + the targets are
    accepted (per-target buff install still filed in v1; this commit
    is the cap enforcement only)."""
    magnus = magnus_rested
    mg_tok = f"tok_bane_l3_mg_{magnus['id']}"
    await _seed_battle(gm_client, [
        _mkc(mg_tok, magnus["id"], name=magnus["name"]),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bane",
        json={
            "character_id": magnus["id"],
            "class_slug": "warlock",
            "via_invocation": "thief-of-five-fates",
            "slot_level": 3,
            "override": True,
            "target_combatant_ids": [
                "tok_b_t1", "tok_b_t2", "tok_b_t3",
                "tok_b_t4", "tok_b_t5",
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["max_targets"] == 5
    assert data["slot_level"] == 3
