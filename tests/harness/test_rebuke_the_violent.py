"""v2.99.249 — Redemption Paladin: Rebuke the Violent CD (Phase H.2 FIFTH + FINAL oath).

Phase H.2 fifth and FINAL non-Devotion Paladin oath. RAW XGE
p.39: Redemption Paladin Lv 3+ reaction CD — when an attacker
within 30 ft damages a creature other than you, attacker Wis
save DC 8 + prof + CHA or take psychic damage = damage dealt
(half on success).

v1 ships:
  - /use_rebuke_the_violent: validates Redemption Paladin Lv 3+
    + channel-divinity resource current >= 1 + attacker in
    battle + reaction chip. Decrements CD, marks chip, computes
    DC, broadcasts.

With this commit, Phase H.2 (5 non-Devotion oaths) is
substantially complete.

**v2.672.0 (Phase 8):** the attacker's Wis save is now rolled +
the psychic damage applied server-side (was announce-only) when
the attacker combatant resolves to a sheet (NPC via template, PC
via Character.sheet). Full psychic on a fail, half on a success,
routed through `_apply_damage_to_combatant` (`is_magical=True`).

Sir Caelan Lightbringer is the demo fixture. Tests PATCH his
subclass to "Oath of Redemption" + seed Caelan + Bandit
attacker in battle. Caelan Lv 7 CHA 16 → DC 14.

Tests:
  - Happy 15 dmg → DC 14, on_fail 15, on_success 7, broadcast.
  - Apply: templated bandit attacker → save rolled + psychic applied.
  - Missing damage_dealt → 400.
  - Damage_dealt < 1 → 400.
  - Attacker not in battle → 404.
  - Out of CD → 409.
  - Wrong subclass → 409.
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


def _rtv_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "rebuke-the-violent"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _cd_resource(current: int, maximum: int) -> dict:
    return {
        "key": "channel-divinity",
        "name": "Channel Divinity",
        "current": current, "max": maximum, "reset": "short",
        "source": "paladin Lv 3",
        "class_slug": "paladin",
        "subclass_slug": "redemption",
        "desc": "Channel a domain effect (Emissary of Peace, Rebuke the Violent). One use per short rest.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def caelan_redemption_with_bandit(gm_client, roster):
    """PATCH Caelan to Redemption + reset CD + seed battle."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {
            "subclass": "Oath of Redemption",
            "resources": [_cd_resource(1, 1)],
        },
        class_slug="paladin",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_cr_{caelan['id']}",
             "char_id": caelan["id"], "name": caelan["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_bandit_rtv",
             "char_id": None,
             "name": "Bandit Alpha", "initiative": 8,
             "hp_current": 50, "hp_max": 50,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "resources": []},
            class_slug="paladin",
        )


async def test_use_rtv_happy(
    gm_client, gm_ws, caelan_redemption_with_bandit,
):
    """Redemption Caelan rebukes Bandit who dealt 15 dmg → DC 14,
    on_fail 15, on_success 7."""
    caelan = caelan_redemption_with_bandit
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rebuke_the_violent",
        json={
            "character_id": caelan["id"],
            "attacker_combatant_id": "tok_bandit_rtv",
            "damage_dealt": 15,
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["save_dc"] == 14
    assert data["psychic_damage_on_fail"] == 15
    assert data["psychic_damage_on_success"] == 7  # 15 // 2
    assert data["uses_remaining"] == 0
    await asyncio.sleep(0.3)
    feats = _rtv_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_rtv_applies_psychic_damage(
    gm_client, caelan_redemption_with_bandit,
):
    """v2.672.0 — Phase 8: a templated NPC attacker now has its WIS save
    rolled + the psychic damage applied server-side. Re-seed the battle with
    a real bandit *template* (the fixture's bandit carries no
    token_template_id, so the save mod can't resolve). Full damage on a fail,
    half on a success; either way the applied amount is consistent with the
    save outcome (vanilla bandit → no psychic resistance → exact)."""
    caelan = caelan_redemption_with_bandit
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_cr_{caelan['id']}",
             "char_id": caelan["id"], "name": caelan["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_bandit_rtv_tmpl", "char_id": None,
             "token_template_id": bandit["id"], "name": bandit["name"],
             "initiative": 8, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rebuke_the_violent",
        json={
            "character_id": caelan["id"],
            "attacker_combatant_id": "tok_bandit_rtv_tmpl",
            "damage_dealt": 15,
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["save_dc"] == 14
    assert data["save_total"] is not None, data
    assert isinstance(data["save_passed"], bool), data
    applied = data["psychic_damage_applied"]
    assert applied is not None, data
    # full (15) on fail, half (7) on success — consistent with the outcome.
    expected = 7 if data["save_passed"] else 15
    assert applied == expected, data


async def test_use_rtv_missing_damage(
    gm_client, caelan_redemption_with_bandit,
):
    """No damage_dealt → 400."""
    caelan = caelan_redemption_with_bandit
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rebuke_the_violent",
        json={
            "character_id": caelan["id"],
            "attacker_combatant_id": "tok_bandit_rtv",
            "override": True,
        },
    )
    assert r.status_code == 400, r.text


async def test_use_rtv_zero_damage(
    gm_client, caelan_redemption_with_bandit,
):
    """damage_dealt 0 → 400 (must be >= 1)."""
    caelan = caelan_redemption_with_bandit
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rebuke_the_violent",
        json={
            "character_id": caelan["id"],
            "attacker_combatant_id": "tok_bandit_rtv",
            "damage_dealt": 0,
            "override": True,
        },
    )
    assert r.status_code == 400, r.text


async def test_use_rtv_attacker_not_in_battle(
    gm_client, caelan_redemption_with_bandit,
):
    """Unknown attacker → 404."""
    caelan = caelan_redemption_with_bandit
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rebuke_the_violent",
        json={
            "character_id": caelan["id"],
            "attacker_combatant_id": "tok_ghost",
            "damage_dealt": 15,
            "override": True,
        },
    )
    assert r.status_code == 404, r.text


async def test_use_rtv_out_of_cd(
    gm_client, caelan_redemption_with_bandit,
):
    """CD current=0 → 409."""
    caelan = caelan_redemption_with_bandit
    await _patch_sheet(
        gm_client, caelan["id"],
        {"resources": [_cd_resource(0, 1)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rebuke_the_violent",
        json={
            "character_id": caelan["id"],
            "attacker_combatant_id": "tok_bandit_rtv",
            "damage_dealt": 15,
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_rtv_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rebuke_the_violent",
        json={
            "character_id": caelan["id"],
            "attacker_combatant_id": "tok_bandit_rtv",
            "damage_dealt": 15,
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
