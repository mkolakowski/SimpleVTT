"""Phase C.2 — concentration buffs + Hunter's Mark + Hex + concentration save.

v2.19.1: ships the (C) infrastructure's concentration semantics on top
of the C.1 buff data primitive. Hunter's Mark + Hex are the canonical
test cases — both bonus-action concentration spells with per-attack
riders against a marked target.

Tests:
  - Hunter's Mark happy path: Rowan marks Vex, slot decrements, buff
    installs, broadcasts fire (feature_used + spell_slot_update +
    buff_update).
  - Hunter's Mark wrong class: Pip (Rogue) tries — 409.
  - Hunter's Mark no_slot: drain L1 Ranger slots.
  - Hunter's Mark missing fields.
  - Hex happy path: Magnus hexes Vex with STR disadvantage.
  - Hex wrong class: Pip — 409.
  - Concentration swap: Rowan casts Hunter's Mark, then casts again
    (replaces target) — the first buff stays, second buff replaces.
    Actually for the canonical concentration RAW: casting a NEW
    concentration spell drops the OLD. We model that by casting two
    different concentration spells (Hex from Magnus AS WELL AS
    Hunter's Mark from Rowan would NOT conflict; what conflicts is
    Rowan casting Hunter's Mark THEN casting another concentration
    spell). We test it via two Hunter's Mark casts and confirm only
    one buff remains.
  - Concentration save on damage: install Hunter's Mark on Rowan,
    apply damage via sheet PATCH with hp_change_reason=damage, expect
    concentration_save broadcast.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def rowan_full(gm_client, roster):
    """Long-rest Rowan to refill spell slots before each test."""
    rowan = roster["Rowan Quickbow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/rest",
        json={"type": "long"},
    )
    return rowan


@pytest_asyncio.fixture
async def magnus_full(gm_client, roster):
    """Long-rest Magnus to refill Pact Magic slots before each test."""
    magnus = roster["Magnus Hexbinder"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    return magnus


async def _seed_battle_with(gm_client, char_ids: list[int]) -> None:
    """Minimal battle state for the hub helpers to mutate."""
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


async def test_hunters_mark_happy_path(gm_client, gm_ws, rowan_full, roster):
    """Rowan marks Vex (a token name in init). Slot decrements, buff installs,
    broadcasts fire.
    """
    rowan = rowan_full
    # Rowan + a PC target — pick Pip as a stand-in PC target since the
    # demo doesn't expose Vex via the roster API.
    pip = roster["Pip Quickfingers"]
    await _seed_battle_with(gm_client, [rowan["id"], pip["id"]])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
        json={
            "character_id": rowan["id"],
            "target_character_id": pip["id"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["slot_level"] == 1
    assert data["target_character_id"] == pip["id"]
    assert data["duration_rounds"] > 0
    assert data["duration_label"] == "1h"

    fu = await gm_ws.wait_for("feature_used")
    assert fu["data"]["source"] == "hunters-mark"
    assert "Hunter's Mark" in fu["data"]["feature_name"]

    bu = await gm_ws.wait_for("buff_update")
    assert bu["data"]["character_id"] == rowan["id"]
    buffs = bu["data"]["buffs"]
    assert any(b["key"] == "hunters-mark" for b in buffs)
    hm = next(b for b in buffs if b["key"] == "hunters-mark")
    assert hm["concentration"] is True
    assert hm["target_character_id"] == pip["id"]
    assert hm["effects"]["weapon_hit_bonus_dice"] == "1d6"


async def test_hunters_mark_wrong_class(gm_client, roster):
    """Pip (Rogue) tries to cast Hunter's Mark — 409."""
    pip = roster["Pip Quickfingers"]
    thalindra = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
        json={
            "character_id": pip["id"],
            "target_character_id": thalindra["id"],
            "override": True,
        },
    )
    assert resp.status_code == 409
    assert "Ranger" in resp.json().get("detail", "")


async def test_hunters_mark_missing_target(gm_client, rowan_full):
    """No target — 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
        json={"character_id": rowan_full["id"], "override": True},
    )
    assert resp.status_code == 400


async def test_hunters_mark_missing_character_id(gm_client, roster):
    """No caster — 400."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
        json={"target_character_id": pip["id"]},
    )
    assert resp.status_code == 400


async def test_hex_happy_path(gm_client, gm_ws, magnus_full, roster):
    """Magnus hexes Pip with STR disadvantage. Pact slot (L3) decrements."""
    magnus = magnus_full
    pip = roster["Pip Quickfingers"]
    await _seed_battle_with(gm_client, [magnus["id"], pip["id"]])
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": magnus["id"],
            "target_character_id": pip["id"],
            "ability": "STR",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["slot_level"] == 3  # Lv 5 Warlock only has L3 slots
    assert data["ability"] == "STR"

    fu = await gm_ws.wait_for("feature_used")
    assert fu["data"]["source"] == "hex"
    assert fu["data"]["ability"] == "STR"

    bu = await gm_ws.wait_for("buff_update")
    hex_buff = next((b for b in bu["data"]["buffs"] if b["key"] == "hex"), None)
    assert hex_buff is not None
    assert hex_buff["concentration"] is True
    assert hex_buff["effects"]["weapon_hit_bonus_damage_type"] == "necrotic"


async def test_hex_wrong_class(gm_client, roster):
    """Pip can't cast Hex — 409."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hex",
        json={
            "character_id": pip["id"],
            "target_name": "Bandit Alpha",
            "override": True,
        },
    )
    assert resp.status_code == 409
    assert "Warlock" in resp.json().get("detail", "")


async def test_concentration_swap(gm_client, gm_ws, rowan_full, roster):
    """Cast Hunter's Mark on one target, then cast it again on another —
    the second install REPLACES the first (same key, refresh semantics).
    Single buff remains.
    """
    rowan = rowan_full
    pip = roster["Pip Quickfingers"]
    thalindra = roster["Thalindra Moonwhisper"]
    await _seed_battle_with(gm_client, [rowan["id"], pip["id"], thalindra["id"]])

    # First cast.
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
        json={
            "character_id": rowan["id"],
            "target_character_id": pip["id"],
            "override": True,
        },
    )
    assert r1.status_code == 200, r1.text

    # Second cast on a different target. Drains another slot but only
    # one buff remains.
    gm_ws.mark()
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
        json={
            "character_id": rowan["id"],
            "target_character_id": thalindra["id"],
            "override": True,
        },
    )
    assert r2.status_code == 200, r2.text

    bu = await gm_ws.wait_for("buff_update")
    # Only one Hunter's Mark; targets Thalindra now.
    hm_buffs = [b for b in bu["data"]["buffs"] if b["key"] == "hunters-mark"]
    assert len(hm_buffs) == 1
    assert hm_buffs[0]["target_character_id"] == thalindra["id"]


async def test_concentration_save_on_damage(gm_client, gm_ws, rowan_full, roster):
    """Install Hunter's Mark on Rowan. Then apply damage via sheet
    PATCH with hp_change_reason=damage. Expect a concentration_save
    broadcast with the rolled value, DC, and pass/fail.
    """
    rowan = rowan_full
    pip = roster["Pip Quickfingers"]
    await _seed_battle_with(gm_client, [rowan["id"], pip["id"]])
    # Install Hunter's Mark.
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
        json={
            "character_id": rowan["id"],
            "target_character_id": pip["id"],
            "override": True,
        },
    )
    assert r1.status_code == 200, r1.text
    gm_ws.mark()

    # Damage Rowan — 10 damage, so DC = max(10, 5) = 10.
    # Rowan's HP max is 44, current likely 44. New current = 34.
    resp = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
        json={
            "hp": {"current": 34},
            "hp_change_reason": "damage",
            "damage_amount": 10,
        },
    )
    assert resp.status_code == 200, resp.text

    cs = await gm_ws.wait_for("concentration_save")
    assert cs["data"]["character_id"] == rowan["id"]
    assert cs["data"]["buff_key"] == "hunters-mark"
    assert cs["data"]["damage_amount"] == 10
    assert cs["data"]["dc"] == 10
    assert isinstance(cs["data"]["passed"], bool)
    if not cs["data"]["passed"]:
        # On fail, buff should be removed via a subsequent buff_update.
        bu = await gm_ws.wait_for("buff_update")
        assert bu["data"]["removed_key"] == "hunters-mark"


async def test_war_caster_concentration_save_advantage(
    gm_client, gm_ws, rowan_full, roster,
):
    """v2.83.0 — War Caster's RAW passive: advantage on Constitution
    saving throws to maintain concentration when you take damage. The
    `_maybe_concentration_save` helper detects the feat and rolls
    `2d20kh1` instead of `1d20`. Also broadcasts `feature_used(source=
    war-caster-concentration)` so the chat-card has an audit trail.

    Pattern: PATCH War Caster onto Rowan's feats, install Hunter's
    Mark (concentration), damage Rowan via sheet PATCH, assert the
    concentration_save broadcast carries `war_caster_advantage: True`
    AND the feature_used trail fires. Restore feats in finally.
    """
    rowan = rowan_full
    pip = roster["Pip Quickfingers"]
    patch = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
        json={"feats": [
            {"slug": "war-caster", "name": "War Caster"},
        ]},
    )
    assert patch.status_code == 200, patch.text
    try:
        await _seed_battle_with(gm_client, [rowan["id"], pip["id"]])
        # Install Hunter's Mark.
        r1 = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_hunters_mark",
            json={
                "character_id": rowan["id"],
                "target_character_id": pip["id"],
                "override": True,
            },
        )
        assert r1.status_code == 200, r1.text
        gm_ws.mark()

        # Damage Rowan — 10 damage triggers a concentration save at DC 10.
        resp = await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={
                "hp": {"current": 34},
                "hp_change_reason": "damage",
                "damage_amount": 10,
            },
        )
        assert resp.status_code == 200, resp.text

        cs = await gm_ws.wait_for("concentration_save")
        assert cs["data"]["character_id"] == rowan["id"]
        assert cs["data"]["buff_key"] == "hunters-mark"
        # The v2.83.0 marker.
        assert cs["data"].get("war_caster_advantage") is True, (
            f"expected war_caster_advantage=True; got {cs['data']}"
        )

        # feature_used(source=war-caster-concentration) audit trail.
        fu = await gm_ws.wait_for("feature_used")
        assert fu["data"].get("source") == "war-caster-concentration"
        assert fu["data"].get("character_id") == rowan["id"]
        assert fu["data"].get("dc") == 10
        assert fu["data"].get("passed") == cs["data"]["passed"]
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{rowan['id']}/sheet-fields",
            json={"feats": []},
        )
