"""v2.99.385 — Oathbreaker Paladin: Control Undead (G Paladin oath sweep, Lv 3+, DMG).

Phase G Paladin oath sweep — Oathbreaker rounds out the oaths.
RAW DMG p.97 (Channel Divinity): as an action, target an undead
within 30 ft; it makes a CHA save (DC 8 + PB + CHA mod) or obeys
your commands for 24 hours. Undead with CR ≥ your level are immune.

v2.99.393 — Phase 1: the Channel Divinity cost is now server-tracked
(spends from the shared `channel-divinity` pool; 409 `out_of_uses`
when depleted; refilled by /rest). The targeting + save + 24h
control stay GM-tracked pending the Phase 3 save resolver. The save
DC + max CR are computed server-side. Action chip.

Sir Caelan Lightbringer (Paladin, PATCHed to Oathbreaker Lv 7) is
the demo fixture (max CR 6).

Tests:
  - Lv 7 happy: CHA save DC >= 8, max_cr 6, 24h.
  - Wrong subclass (default Oath of Devotion) → 409.
  - Wrong class (Krieger barbarian) → 409.
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


def _cu_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "control-undead"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_oathbreaker(gm_client, roster):
    """PATCH Caelan to Oathbreaker + long-rest (refill Channel Divinity);
    restore to Devotion on teardown."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oathbreaker"},
        class_slug="paladin",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion"},
            class_slug="paladin",
        )


async def test_use_cu_happy_lv7(
    gm_client, gm_ws, caelan_oathbreaker,
):
    """Lv 7 Oathbreaker → CHA save DC, max CR 6, Channel Divinity 1→0."""
    caelan = caelan_oathbreaker
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_control_undead",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "control-undead"
    assert data["save"] == "cha"
    assert data["save_dc"] >= 8
    assert data["max_cr"] == 6  # paladin level 7 - 1
    assert data["duration_hours"] == 24
    assert data["cd_max"] == 1
    assert data["cd_remaining"] == 0
    assert data["paladin_level"] == 7
    await asyncio.sleep(0.3)
    feats = _cu_broadcasts(gm_ws, caelan["id"])
    assert feats
    assert feats[-1]["data"]["cd_remaining"] == 0


async def test_use_cu_out_of_channel_divinity(
    gm_client, caelan_oathbreaker,
):
    """A second Control Undead with no Channel Divinity left → 409."""
    caelan = caelan_oathbreaker
    url = f"/api/campaign/{CAMPAIGN_ID}/use_control_undead"
    r1 = await gm_client.post(url, json={
        "character_id": caelan["id"], "override": True})
    assert r1.status_code == 200, r1.text
    assert r1.json()["cd_remaining"] == 0
    r2 = await gm_client.post(url, json={
        "character_id": caelan["id"], "override": True})
    assert r2.status_code == 409, r2.text
    assert r2.json().get("error") == "out_of_uses"


async def test_use_cu_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Oath of Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_control_undead",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_cu_wrong_class(
    gm_client, roster,
):
    """Krieger (Barbarian) → 409."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_control_undead",
        json={"character_id": krieger["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_cu_resolves_npc_save_installs_control(
    gm_client, gm_ws, caelan_oathbreaker,
):
    """v2.99.414 — Phase 3.5 (completes Phase 3): against an NPC target,
    Control Undead resolves the CHA save and installs the
    `controlled-undead` marker on a fail.

    Single-target + 1 Channel Divinity use per long rest → loop with a
    long-rest refill each iteration until the bandit fails its CHA save.
    """
    caelan = caelan_oathbreaker
    tmpl_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = tmpl_resp.json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    caelan_tok = f"tok_cu_{caelan['id']}"
    bandit_tok = "tok_cu_bandit"

    def _battle():
        return {"combatants": [
            {"id": caelan_tok, "char_id": caelan["id"], "name": caelan["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": bandit_tok, "char_id": None,
             "token_template_id": bandit["id"], "name": "Skeleton",
             "initiative": 8, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True}

    installed = False
    for _ in range(40):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
            json={"type": "long"},
        )
        await gm_client.put(f"/api/campaign/{CAMPAIGN_ID}/battle", json=_battle())
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_control_undead",
            json={"character_id": caelan["id"],
                  "target_combatant_id": bandit_tok, "override": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["save_resolved"] is True, data
        assert data["save"] == "cha"
        if data["condition_installed"]:
            installed = True
            break
    assert installed, "no failed bandit CHA save in 40 tries"

    bu = await gm_ws.wait_for("battle_update")
    cb = next((c for c in (bu["data"].get("combatants") or [])
               if c.get("id") == bandit_tok), None)
    assert cb is not None
    ctrl = next((b for b in (cb.get("buffs") or [])
                 if (b or {}).get("key") == "controlled-undead"), None)
    assert ctrl is not None, cb.get("buffs")
    assert ctrl.get("name") == "Controlled (Control Undead)"
    assert not ctrl.get("repeated_save_ability")  # 24h, no re-save
