"""v2.99.222 — Draconic Wings + Draconic Presence (Sorcerer Draconic Bloodline).

Phase E.5 of the v2.99.193 phased completion plan. RAW PHB
p.103:
  - Draconic Wings (Lv 14): bonus action sprouts wings, flying
    speed = current speed; lasts until dismissed (bonus action).
  - Draconic Presence (Lv 18): action + 5 SP, 60 ft aura of
    awe (charmed) or fear (frightened); 1 minute or until
    concentration ends.

v1 implementations:
  - /use_draconic_wings: installs `dragon-wings-active` buff
    with `effects.fly_speed_ft = sheet.speed`. Dismiss via
    /end_buff.
  - /use_draconic_presence: announce-only — decrements 5 SP +
    broadcasts. Per-target CHA save resolution + 24-hour
    immunity tracking are filed.

Zara Emberfire (Tiefling Sorcerer Draconic Bloodline Lv 5
default) is the demo fixture; tests PATCH her Lv 5 → 14 / 18.

Tests:
  - Draconic Wings happy path: Zara Lv 14 → /use_draconic_wings
    → buff installed + fly_speed = 30.
  - Wings level gate: Lv 5 → 409.
  - Draconic Presence happy path: Lv 18 + 5 SP → 200 +
    broadcast + SP decremented.
  - Presence level gate: Lv 14 → 409.
  - Presence not enough SP: Lv 18 + SP=3 → 409.
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


def _dw_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "draconic-wings"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _dp_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "draconic-presence"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def zara_lv14(gm_client, roster):
    """PATCH Zara to Lv 14 + seed a battle so _install_buff works."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"], {"level": 14},
        class_slug="sorcerer",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_dw_{zara['id']}",
             "char_id": zara["id"], "name": zara["name"],
             "initiative": 10, "hp_current": 30, "hp_max": 30,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    yield zara
    await _patch_sheet(
        gm_client, zara["id"], {"level": 5},
        class_slug="sorcerer",
    )


@pytest_asyncio.fixture
async def zara_lv18_with_sp(gm_client, roster):
    """PATCH Zara to Lv 18 + ensure sorcery-points >= 5."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"], {"level": 18},
        class_slug="sorcerer",
    )
    await _patch_sheet(
        gm_client, zara["id"],
        {"resources": [
            {"key": "sorcery-points", "label": "Sorcery Points",
             "current": 5, "max": 18, "reset": "long"},
        ]},
    )
    yield zara
    await _patch_sheet(
        gm_client, zara["id"], {"level": 5},
        class_slug="sorcerer",
    )
    await _patch_sheet(
        gm_client, zara["id"],
        {"resources": [
            {"key": "sorcery-points", "label": "Sorcery Points",
             "current": 5, "max": 5, "reset": "long"},
        ]},
    )


async def test_draconic_wings_happy_path(
    gm_client, gm_ws, zara_lv14,
):
    """Zara Lv 14 → /use_draconic_wings → buff installed +
    fly_speed = 30 (her sheet speed).
    """
    zara = zara_lv14
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_draconic_wings",
        json={"character_id": zara["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["fly_speed_ft"] == 30
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _dw_broadcasts(gm_ws, zara["id"])
    assert feats, (
        f"v2.99.222: expected feature_used(source=draconic-wings); "
        f"buffered={gm_ws.buffered()}"
    )


async def test_draconic_wings_level_gate(
    gm_client, roster,
):
    """Control: Zara Lv 5 default → 409 level_too_low."""
    zara = roster["Zara Emberfire"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_draconic_wings",
        json={"character_id": zara["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "level_too_low"
    assert data.get("required") == 14


async def test_draconic_presence_awe_mode(
    gm_client, gm_ws, zara_lv18_with_sp,
):
    """Zara Lv 18 spends 5 SP → awe aura broadcast + SP=0."""
    zara = zara_lv18_with_sp
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_draconic_presence",
        json={
            "character_id": zara["id"],
            "mode": "awe",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "awe"
    assert data["condition"] == "charmed"
    assert data["sp_spent"] == 5
    assert data["remaining_sp"] == 0
    await asyncio.sleep(0.3)
    feats = _dp_broadcasts(gm_ws, zara["id"])
    assert feats


async def test_draconic_presence_fear_mode(
    gm_client, gm_ws, zara_lv18_with_sp,
):
    """Fear mode → frightened condition."""
    zara = zara_lv18_with_sp
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_draconic_presence",
        json={
            "character_id": zara["id"],
            "mode": "fear",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "fear"
    assert data["condition"] == "frightened"


async def test_draconic_presence_level_gate(
    gm_client, zara_lv14,
):
    """Control: Zara Lv 14 (no Presence yet) → 409 level_too_low."""
    zara = zara_lv14
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_draconic_presence",
        json={
            "character_id": zara["id"],
            "mode": "awe",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    assert r.json().get("error") == "level_too_low"
    assert r.json().get("required") == 18


async def test_draconic_presence_not_enough_sp(
    gm_client, roster,
):
    """Lv 18 + SP=3 → 409 not_enough_sp."""
    zara = roster["Zara Emberfire"]
    await _patch_sheet(
        gm_client, zara["id"], {"level": 18},
        class_slug="sorcerer",
    )
    await _patch_sheet(
        gm_client, zara["id"],
        {"resources": [
            {"key": "sorcery-points", "label": "Sorcery Points",
             "current": 3, "max": 18, "reset": "long"},
        ]},
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_draconic_presence",
            json={
                "character_id": zara["id"],
                "mode": "awe",
                "override": True,
            },
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "not_enough_sp"
    finally:
        await _patch_sheet(
            gm_client, zara["id"], {"level": 5},
            class_slug="sorcerer",
        )
        await _patch_sheet(
            gm_client, zara["id"],
            {"resources": [
                {"key": "sorcery-points", "label": "Sorcery Points",
                 "current": 5, "max": 5, "reset": "long"},
            ]},
        )


async def test_dp_resolves_npc_save_installs_condition(
    gm_client, gm_ws, zara_lv18_with_sp,
):
    """v2.99.411 — Phase 3.4: with a target list, Draconic Presence
    resolves each aura target's CHA save and installs Charmed (awe) /
    Frightened (fear) with a repeated save on a fail.

    Re-seed a deep SP pool (each use costs 5) so the loop can retry until
    a template bandit fails its CHA save.
    """
    zara = zara_lv18_with_sp
    await _patch_sheet(
        gm_client, zara["id"],
        {"resources": [
            {"key": "sorcery-points", "label": "Sorcery Points",
             "current": 200, "max": 200, "reset": "long"},
        ]},
    )
    tmpl_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = tmpl_resp.json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    zara_tok = f"tok_dp_zara_{zara['id']}"
    bandit_tok = "tok_dp_bandit"

    def _battle():
        return {"combatants": [
            {"id": zara_tok, "char_id": zara["id"], "name": zara["name"],
             "initiative": 12, "hp_current": 40, "hp_max": 40, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": bandit_tok, "char_id": None,
             "token_template_id": bandit["id"], "name": "Bandit",
             "initiative": 8, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True}

    installed = False
    for _ in range(40):
        await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/battle", json=_battle())
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_draconic_presence",
            json={"character_id": zara["id"], "mode": "fear",
                  "target_combatant_ids": [bandit_tok], "override": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["save_dc"] >= 8
        fs = data["feature_saves"]
        assert len(fs) == 1, fs
        assert fs[0]["resolved"] is True
        assert fs[0]["save_ability"] == "CHA"
        if fs[0]["condition_installed"]:
            assert fs[0]["condition_key"] == "frightened"
            installed = True
            break
    assert installed, "no failed bandit CHA save in 40 tries"

    bu = await gm_ws.wait_for("battle_update")
    cb = next((c for c in (bu["data"].get("combatants") or [])
               if c.get("id") == bandit_tok), None)
    assert cb is not None
    fr = next((b for b in (cb.get("buffs") or [])
               if (b or {}).get("key") == "frightened"), None)
    assert fr is not None, cb.get("buffs")
    assert fr.get("name") == "Frightened (Draconic Presence)"
    # Repeated save (RAW: repeat at end of each turn).
    assert (fr.get("repeated_save_ability") or "").upper() == "CHA"
