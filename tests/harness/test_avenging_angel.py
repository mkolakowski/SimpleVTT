"""v2.99.289 — Vengeance Paladin: Avenging Angel (H.2 deeper, Lv 20).

H.2 Lv 20 Vengeance ship. RAW PHB p.88: action to transform
1 hour. Gain wings + fly 60 ft, plus 30 ft frightful aura
(Wis save DC 8 + prof + CHA on first enter or turn start, or
become frightened 1 min / until damaged; advantage vs
frightened). Once per long rest.

v1 announce-only — wings/fly, aura, frightened install
GM-tracked. Costs action chip. Auto-bootstraps an
`avenging-angel` resource if missing; refilled by long rest.

Caelan PATCH'd to Lv 20: prof_bonus is a separate field that
doesn't auto-update on level PATCH, so it stays at its demo
default of 3. CHA 16 → mod 3. DC = 8 + 3 + 3 = 14.

Tests:
  - Lv 20 happy → save_dc 14, fly_speed_ft 60,
    aura_radius_ft 30, duration 60 min.
  - Wrong subclass → 409.
  - Level gate (Lv 19) → 409.
  - Long rest refills → second call after rest → 200.
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


def _aa_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "avenging-angel"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_vengeance_lv20(gm_client, roster):
    """PATCH Caelan to Vengeance Lv 20 + long-rest."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Vengeance", "level": 20},
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
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_use_aa_happy_lv20(
    gm_client, gm_ws, caelan_vengeance_lv20,
):
    """Lv 20 Vengeance, prof 3 (stale) + CHA 16 → DC 14."""
    caelan = caelan_vengeance_lv20
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_avenging_angel",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["save_dc"] == 14
    assert data["fly_speed_ft"] == 60
    assert data["aura_radius_ft"] == 30
    assert data["duration_minutes"] == 60
    assert data["uses_remaining"] == 0
    assert data["paladin_level"] == 20
    await asyncio.sleep(0.3)
    feats = _aa_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_aa_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion Lv 7) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_avenging_angel",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_aa_level_gate(
    gm_client, roster,
):
    """Vengeance Caelan at Lv 19 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Vengeance", "level": 19},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_avenging_angel",
            json={"character_id": caelan["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_use_aa_long_rest_refills(
    gm_client, caelan_vengeance_lv20,
):
    """Use → long rest → use again → 200."""
    caelan = caelan_vengeance_lv20
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_avenging_angel",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r1.status_code == 200, r1.text
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_avenging_angel",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["uses_remaining"] == 0


async def test_aa_aura_frightens_enemy_on_its_turn(
    gm_client, gm_ws, caelan_vengeance_lv20,
):
    """v2.99.429 — Phase 5.4: Avenging Angel installs a subject-turn-start
    save aura, and the tick frightens an enemy that starts its turn in the
    30-ft aura (WIS save vs DC 14, NPC inline).

    Activate → assert the aura buff's save payload → loop: advance to the
    bandit's turn until it fails the WIS save and Frightened installs.
    """
    caelan = caelan_vengeance_lv20
    tmpl_resp = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = tmpl_resp.json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    caelan_tok = f"tok_aa_{caelan['id']}"
    bandit_tok = "tok_aa_bandit"

    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": caelan_tok, "char_id": caelan["id"], "name": caelan["name"],
             "initiative": 20, "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": bandit_tok, "char_id": None,
             "token_template_id": bandit["id"], "name": "Bandit",
             "initiative": 8, "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_avenging_angel",
        json={"character_id": caelan["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["buff_installed"] is True

    bu = await gm_ws.wait_for("buff_update")
    aa = next((b for b in bu["data"]["buffs"]
               if b.get("key") == "avenging-angel"), None)
    assert aa is not None, bu["data"]["buffs"]
    aura = (aa.get("effects") or {}).get("aura") or {}
    assert aura.get("on") == "subject_turn_start"
    assert aura.get("affects") == "enemies"
    assert (aura.get("save") or {}).get("ability") == "WIS"
    caelan_buffs = bu["data"]["buffs"]

    def _combs(turn_index):
        return [
            {"id": caelan_tok, "char_id": caelan["id"], "name": caelan["name"],
             "initiative": 20, "hp_current": 60, "hp_max": 60,
             "buffs": caelan_buffs,
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": bandit_tok, "char_id": None,
             "token_template_id": bandit["id"], "name": "Bandit",
             "initiative": 8, "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ]

    landed = False
    for _ in range(40):
        # Reset to Caelan's turn (bandit cleared), then advance to the
        # bandit's turn so the subject-turn-start save fires on it.
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": _combs(0), "turn_index": 0, "round": 1,
                  "active": True})
        gm_ws.mark()
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": _combs(1), "turn_index": 1, "round": 1,
                  "active": True})
        await asyncio.sleep(0.25)
        bus = gm_ws.buffered("battle_update")
        latest = bus[-1] if bus else None
        if latest:
            band = next((c for c in (latest["data"].get("combatants") or [])
                         if c.get("id") == bandit_tok), None)
            if band and any((b or {}).get("key") == "frightened"
                            for b in (band.get("buffs") or [])):
                landed = True
                break
    assert landed, "no failed bandit WIS save in 40 turn-starts"
