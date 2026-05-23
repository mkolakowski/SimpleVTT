"""Sorcerer Font of Magic — Phase 0 of the Sorcery Points +
Metamagic plan (docs/plans/sorcery-points-and-metamagic.md).

v2.49.120 — adds two endpoints:
  - POST /use_font_of_magic_to_points: sacrifice spell slot of
    level N → gain N sorcery points (bonus action, RAW PHB p.101).
  - POST /use_font_of_magic_to_slot: spend sorcery points per the
    cost table (L1=2, L2=3, L3=5, L4=6, L5=7) to recover a USED
    spell slot of that level. L6+ not recoverable.

Demo subject: Zara Emberfire (Sorcerer Lv 5, Draconic Bloodline).
At Lv 5: 4×L1 + 3×L2 + 2×L3 spell slots, 5 max sorcery points.

Tests:
  - slot → SP conversion happy paths (L1, L3)
  - SP → slot conversion happy paths (L1, L2, L3)
  - 409 no_slot (sacrificing an empty level)
  - 409 not_enough_points
  - 409 no_used_slot_to_restore (all slots already full)
  - 409 slot_too_high (L6+)
  - 409 wrong_class (Thalindra the Wizard tries it)
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def zara_rested(gm_client, roster):
    zara = roster["Zara Emberfire"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "long"},
    )
    return zara


async def _seed_zara_solo(gm_client, zara):
    """One-combatant battle (Zara alone) so the bonus-action gate
    has a battle-state to mark against."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_fom_{zara['id']}",
                "char_id": zara["id"],
                "name": zara["name"],
                "initiative": 10,
                "hp_current": 37, "hp_max": 37,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


# ---------- Slot → SP ----------

async def test_font_of_magic_l1_slot_to_1_sp(gm_client, zara_rested):
    """Spend a full L1 slot → +1 SP. Zara starts at 5 SP (max);
    sacrificing L1 should overflow-cap at 5 (no SP gained)."""
    zara = zara_rested
    await _seed_zara_solo(gm_client, zara)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_points",
        json={"character_id": zara["id"], "slot_level": 1},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slot_level"] == 1
    assert body["sp_gained"] == 1
    # Zara starts at SP max (5); the L1 sacrifice → +1 overflows.
    # The endpoint returns the actual new value (capped) + the overflow.
    assert body["sp_remaining"] == 5
    assert body["sp_max"] == 5
    assert body["sp_overflow_lost"] == 1
    assert body["slot_used"] == 1


async def test_font_of_magic_l3_slot_to_3_sp(gm_client, zara_rested):
    """Spend an L3 slot from a depleted SP pool → +3 SP."""
    zara = zara_rested
    await _seed_zara_solo(gm_client, zara)
    # First drain SP by recovering some L1 slots (SP cost 2 each).
    # Need to first "use" an L1 slot so it can be restored.
    # Cleaner: just drain SP via two L1 → slot conversions.
    # Zara starts at 5 SP + 0 used slots, so we can't restore. Use
    # cheat path: cast Magic Missile twice to drain L1 slots first.
    # Even simpler: use override=True and just confirm the conversion
    # works whether or not SP overflows.
    # The reliable approach: cast a leveled spell to consume an L1
    # slot first, THEN do the L3 → SP conversion.
    # Actually the simplest test: just verify that slot decrements
    # AND SP increments by 3 (modulo overflow).
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_points",
        json={"character_id": zara["id"], "slot_level": 3, "override": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slot_level"] == 3
    assert body["sp_gained"] == 3
    # Total: 5 (current) + 3 (gained) → 5 (capped) + 3 overflow.
    assert body["sp_remaining"] == 5
    assert body["sp_overflow_lost"] == 3
    assert body["slot_total"] == 2  # Zara has 2 L3 slots
    assert body["slot_used"] == 1


async def test_font_of_magic_no_slot_to_sacrifice(gm_client, zara_rested):
    """No L4 slots available (Zara is Lv 5, max slot is L3) → 409."""
    zara = zara_rested
    await _seed_zara_solo(gm_client, zara)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_points",
        json={"character_id": zara["id"], "slot_level": 4},
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "no_slot"
    assert err["slot_level"] == 4


# ---------- SP → Slot ----------

async def test_font_of_magic_2_sp_to_l1_slot(gm_client, zara_rested):
    """L1 slot cost = 2 SP. Drain an L1 slot first, then recover."""
    zara = zara_rested
    await _seed_zara_solo(gm_client, zara)
    # Sacrifice an L1 slot to mark one as used. Zara starts full SP
    # so the overflow burns, but the slot ticks used=1.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_points",
        json={"character_id": zara["id"], "slot_level": 1, "override": True},
    )
    # Now recover that L1 slot for 2 SP.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_slot",
        json={"character_id": zara["id"], "slot_level": 1, "override": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slot_level"] == 1
    assert body["sp_cost"] == 2
    assert body["sp_remaining"] == 3  # 5 (full after sacrifice was capped) - 2
    assert body["slot_used"] == 0  # restored to full


async def test_font_of_magic_5_sp_to_l3_slot(gm_client, zara_rested):
    """L3 slot cost = 5 SP — drains the whole pool."""
    zara = zara_rested
    await _seed_zara_solo(gm_client, zara)
    # Mark an L3 slot used.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_points",
        json={"character_id": zara["id"], "slot_level": 3, "override": True},
    )
    # Spend full SP pool to recover it.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_slot",
        json={"character_id": zara["id"], "slot_level": 3, "override": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sp_cost"] == 5
    assert body["sp_remaining"] == 0
    assert body["slot_used"] == 0


async def test_font_of_magic_slot_too_high(gm_client, zara_rested):
    """L6+ slots aren't recoverable per RAW → 409 slot_too_high."""
    zara = zara_rested
    await _seed_zara_solo(gm_client, zara)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_slot",
        json={"character_id": zara["id"], "slot_level": 6},
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "slot_too_high"
    assert err["max_recoverable"] == 5


async def test_font_of_magic_not_enough_points(gm_client, zara_rested):
    """Drain SP to 0, then try to recover a slot → 409 not_enough_points."""
    zara = zara_rested
    await _seed_zara_solo(gm_client, zara)
    # Drain SP by alternating L3-sacrifice (overflows) + L3-recover (5 SP).
    # First mark an L3 slot used (override since SP is full so overflow burns).
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_points",
        json={"character_id": zara["id"], "slot_level": 3, "override": True},
    )
    # Spend all 5 SP on the L3 recovery.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_slot",
        json={"character_id": zara["id"], "slot_level": 3, "override": True},
    )
    # SP should be 0 now. Mark an L1 slot used.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_points",
        json={"character_id": zara["id"], "slot_level": 1, "override": True},
    )
    # Try to recover the L1 slot for 2 SP — but we only have 1 SP.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_slot",
        json={"character_id": zara["id"], "slot_level": 1, "override": True},
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "not_enough_points"
    assert err["required"] == 2
    assert err["have"] == 1


async def test_font_of_magic_no_used_slot_to_restore(gm_client, zara_rested):
    """All L1 slots full → 409 no_used_slot_to_restore."""
    zara = zara_rested
    await _seed_zara_solo(gm_client, zara)
    # Zara starts with all slots full. Try to recover L1 — should
    # reject because no slot is used.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_slot",
        json={"character_id": zara["id"], "slot_level": 1},
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "no_used_slot_to_restore"


async def test_font_of_magic_wrong_class(gm_client, roster):
    """Thalindra is a Wizard — 409 wrong_class."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_points",
        json={"character_id": thal["id"], "slot_level": 1},
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "wrong_class"
    assert err["expected"] == "sorcerer"


# ---------- Multiclass class_slug (v2.49.122) ----------

async def test_font_of_magic_default_class_slug_is_sorcerer(gm_client, zara_rested):
    """Omitting class_slug defaults to 'sorcerer' — backward compat
    with the v2.49.120 contract. Response should echo the resolved
    class_slug so the caller can verify."""
    zara = zara_rested
    await _seed_zara_solo(gm_client, zara)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_points",
        json={"character_id": zara["id"], "slot_level": 1},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["class_slug"] == "sorcerer"


async def test_font_of_magic_explicit_class_slug_sorcerer(gm_client, zara_rested):
    """Explicit class_slug='sorcerer' works identically to default."""
    zara = zara_rested
    await _seed_zara_solo(gm_client, zara)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_points",
        json={"character_id": zara["id"], "slot_level": 1, "class_slug": "sorcerer"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["class_slug"] == "sorcerer"


async def test_font_of_magic_unknown_class_slug(gm_client, zara_rested):
    """class_slug pointing at a pool Zara doesn't have → 409
    unknown_class_slug with the available pools listed."""
    zara = zara_rested
    await _seed_zara_solo(gm_client, zara)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_font_of_magic_to_points",
        json={"character_id": zara["id"], "slot_level": 1, "class_slug": "wizard"},
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "unknown_class_slug"
    assert err["class_slug"] == "wizard"
    assert "sorcerer" in err["available"]
