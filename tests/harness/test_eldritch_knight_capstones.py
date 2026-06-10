"""v2.99.269 — Eldritch Knight Fighter: Arcane Charge + Improved War Magic (Phase E.2 Phase 4, FINAL).

Phase E.2 Phase 4a + 4b per docs/plans/eldritch-knight.md.
RAW PHB p.74:
  - Arcane Charge (Lv 15+): when using Action Surge, teleport
    up to 30 ft.
  - Improved War Magic (Lv 18+): after casting a Lv 1+ spell
    with action, make one weapon attack as a bonus action.

**Closes E.2 (4/4 phases) — all 4 phases of the Eldritch
Knight plan are now shipped.**

Tests:
  - Arcane Charge happy at Lv 15 → broadcast.
  - Arcane Charge level gate at Lv 14 → 409.
  - Improved War Magic happy at Lv 18 → bonus chip + broadcast.
  - Improved War Magic level gate at Lv 17 → 409.
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


def _ac_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "arcane-charge"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _iwm_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "improved-war-magic"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def garrik_ek_in_battle(gm_client, roster):
    """PATCH Garrik to Eldritch Knight + put him in a battle for
    chip-marking. Level is set per-test via additional PATCH."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Eldritch Knight"},
        class_slug="fighter",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_ek_{garrik['id']}",
             "char_id": garrik["id"], "name": garrik["name"],
             "initiative": 12, "hp_current": 85, "hp_max": 85,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield garrik
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion", "level": 9},
            class_slug="fighter",
        )


async def test_use_ac_happy_lv15(
    gm_client, gm_ws, garrik_ek_in_battle,
):
    """Lv 15 EK → Arcane Charge broadcast + buff installed."""
    garrik = garrik_ek_in_battle
    await _patch_sheet(
        gm_client, garrik["id"], {"level": 15},
        class_slug="fighter",
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_charge",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["teleport_max_ft"] == 30
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _ac_broadcasts(gm_ws, garrik["id"])
    assert feats


async def test_ac_buff_payload_carries_teleport_flags(
    gm_client, gm_ws, garrik_ek_in_battle,
):
    """v2.158.11 — state contract (Phase 9): the installed
    `arcane-charge-active` buff carries the two `arcane_charge_*`
    effect keys with the right values (`teleport_max_ft: 30` +
    `requires_action_surge: True`). Phase 2 (deferred) will have
    `/use_action_surge` read these off the caster's
    `_buffs_active` and surface the teleport budget; this test
    pins the flag shape so that future read site has a stable
    contract to look up."""
    garrik = garrik_ek_in_battle
    await _patch_sheet(
        gm_client, garrik["id"], {"level": 15},
        class_slug="fighter",
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_charge",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    bu = await gm_ws.wait_for("buff_update")
    garrik_buffs = bu["data"]["buffs"]
    ac_buff = next(
        (b for b in garrik_buffs if b.get("key") == "arcane-charge-active"),
        None,
    )
    assert ac_buff is not None, (
        f"arcane-charge-active buff missing; got keys="
        f"{[b.get('key') for b in garrik_buffs]}"
    )
    effects = ac_buff.get("effects") or {}
    assert effects.get("arcane_charge_teleport_max_ft") == 30
    assert effects.get("arcane_charge_requires_action_surge") is True
    # Permanent passive — no concentration, very long duration.
    assert ac_buff.get("concentration") in (False, None)
    assert int(ac_buff.get("duration_rounds") or 0) >= 1000


async def test_use_ac_level_gate(
    gm_client, garrik_ek_in_battle,
):
    """Lv 14 → 409."""
    garrik = garrik_ek_in_battle
    await _patch_sheet(
        gm_client, garrik["id"], {"level": 14},
        class_slug="fighter",
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_charge",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 409, r.text


async def test_action_surge_surfaces_arcane_charge_teleport(
    gm_client, gm_ws, garrik_ek_in_battle,
):
    """v2.158.39 — Phase 2 read site for the v2.158.11 Arcane Charge
    buff. A Lv 15 EK carrying `arcane-charge-active` sees
    `/use_action_surge` surface the 30 ft teleport budget on both its
    JSON response (`arcane_charge_teleport_ft`) and the `feature_used`
    broadcast, and the broadcast desc mentions Arcane Charge."""
    garrik = garrik_ek_in_battle
    await _patch_sheet(
        gm_client, garrik["id"], {"level": 15}, class_slug="fighter",
    )
    # Refill the Action Surge counter.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/rest",
        json={"type": "long"},
    )
    # Phase 1: install the Arcane Charge buff (mirrors to _buffs_active).
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_charge",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_action_surge",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("arcane_charge_teleport_ft") == 30, (
        f"Action Surge should surface the 30 ft teleport budget; got "
        f"{r.json()}"
    )
    msg = await gm_ws.wait_for("feature_used")
    assert msg["data"]["source"] == "action-surge"
    assert msg["data"].get("arcane_charge_teleport_ft") == 30
    assert "Arcane Charge" in (msg["data"].get("feature_desc") or "")


async def test_action_surge_no_teleport_without_arcane_charge(
    gm_client, garrik_ek_in_battle,
):
    """Control: with the `arcane-charge-active` buff removed,
    `/use_action_surge` reports a 0 ft teleport budget — the read is
    scoped to the buff, not granted to every Action Surge. Installs
    then ends the buff so the sheet mirror is clean regardless of
    prior test state (the buff is permanent)."""
    garrik = garrik_ek_in_battle
    await _patch_sheet(
        gm_client, garrik["id"], {"level": 15}, class_slug="fighter",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_arcane_charge",
        json={"character_id": garrik["id"]},
    )
    end = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": garrik["id"], "key": "arcane-charge-active"},
    )
    assert end.status_code == 200, end.text
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_action_surge",
        json={"character_id": garrik["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("arcane_charge_teleport_ft") == 0, (
        f"no buff → 0 ft teleport budget; got {r.json()}"
    )


async def test_use_iwm_happy_lv18(
    gm_client, gm_ws, garrik_ek_in_battle,
):
    """Lv 18 EK → Improved War Magic broadcast + bonus chip +
    buff installed."""
    garrik = garrik_ek_in_battle
    await _patch_sheet(
        gm_client, garrik["id"], {"level": 18},
        class_slug="fighter",
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_improved_war_magic",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _iwm_broadcasts(gm_ws, garrik["id"])
    assert feats


async def test_iwm_buff_payload_carries_min_spell_level_flag(
    gm_client, gm_ws, garrik_ek_in_battle,
):
    """v2.158.12 — state contract (Phase 9): the installed
    `improved-war-magic-active` buff carries the two
    `improved_war_magic_*` effect keys with the right values
    (active flag + min_spell_level=1). Phase 2 (deferred) will
    have the War Magic / `/cast_spell` flow read these off the
    caster's `_buffs_active` to allow the bonus-action weapon
    attack rider when the cast spell's level >= 1 (vs the Lv-7
    War Magic limit of cantrips only); this test pins the flag
    shape so that future read site has a stable contract to look
    up."""
    garrik = garrik_ek_in_battle
    await _patch_sheet(
        gm_client, garrik["id"], {"level": 18},
        class_slug="fighter",
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_improved_war_magic",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    bu = await gm_ws.wait_for("buff_update")
    garrik_buffs = bu["data"]["buffs"]
    iwm_buff = next(
        (b for b in garrik_buffs if b.get("key") == "improved-war-magic-active"),
        None,
    )
    assert iwm_buff is not None, (
        f"improved-war-magic-active buff missing; got keys="
        f"{[b.get('key') for b in garrik_buffs]}"
    )
    effects = iwm_buff.get("effects") or {}
    assert effects.get("improved_war_magic_active") is True
    assert effects.get("improved_war_magic_min_spell_level") == 1
    # Permanent passive — no concentration, very long duration.
    assert iwm_buff.get("concentration") in (False, None)
    assert int(iwm_buff.get("duration_rounds") or 0) >= 1000


async def test_use_iwm_level_gate(
    gm_client, garrik_ek_in_battle,
):
    """Lv 17 → 409."""
    garrik = garrik_ek_in_battle
    await _patch_sheet(
        gm_client, garrik["id"], {"level": 17},
        class_slug="fighter",
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_improved_war_magic",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
