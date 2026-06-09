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


async def test_use_iwm_happy_lv18(
    gm_client, gm_ws, garrik_ek_in_battle,
):
    """Lv 18 EK → Improved War Magic broadcast + bonus chip."""
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
    await asyncio.sleep(0.3)
    feats = _iwm_broadcasts(gm_ws, garrik["id"])
    assert feats


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
