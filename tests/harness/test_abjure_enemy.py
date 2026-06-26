"""v2.99.274 — Vengeance Paladin: Abjure Enemy sibling CD (H.2 depth).

H.2 depth ship — Vengeance Phase 2 sibling CD to Vow of
Enmity. RAW PHB p.87: action; single target within 60 ft Wis
save DC 8 + prof + CHA; fail → Frightened + speed 0; success
→ speed halved. Both end on damage. Fiends/undead at
disadvantage.

Mirrors v2.99.272 Turn the Faithless shape, but single target
instead of AOE.

**v2.681.0 (Phase 8):** the target's WIS save is now resolved
server-side via `_resolve_feature_save` — an NPC saves inline
(install Frightened on a fail), a PC is prompted via a RollRequest.
The speed-0/halved mutation stays GM-narrated. The response gains
`feature_save`.

Tests:
  - Happy → DC 14, CD 1 → 0.
  - Apply: templated NPC → WIS save resolved + Frightened on a fail.
  - Target not in battle → 404.
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


def _ae_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "abjure-enemy"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _cd_resource(current: int, maximum: int) -> dict:
    return {
        "key": "channel-divinity",
        "name": "Channel Divinity",
        "current": current, "max": maximum, "reset": "short",
        "source": "paladin Lv 3",
        "class_slug": "paladin",
        "subclass_slug": "vengeance",
        "desc": "Channel Divinity.",
        "manual": False,
    }


@pytest_asyncio.fixture
async def caelan_vengeance_with_bandit(gm_client, roster):
    """PATCH Caelan to Vengeance + reset CD + seed battle."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {
            "subclass": "Oath of Vengeance",
            "resources": [_cd_resource(1, 1)],
        },
        class_slug="paladin",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_av_{caelan['id']}",
             "char_id": caelan["id"], "name": caelan["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_bandit_ae",
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


async def test_use_ae_happy(
    gm_client, gm_ws, caelan_vengeance_with_bandit,
):
    """Vengeance Caelan adjures Bandit → DC 14, CD 1 → 0."""
    caelan = caelan_vengeance_with_bandit
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_abjure_enemy",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": "tok_bandit_ae",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["save_dc"] == 14
    assert data["uses_remaining"] == 0
    assert data["target_name"] == "Bandit Alpha"
    await asyncio.sleep(0.3)
    feats = _ae_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_ae_resolves_save_and_installs_frightened(
    gm_client, caelan_vengeance_with_bandit,
):
    """v2.681.0 — Phase 8: a templated NPC target now has its WIS save rolled
    inline + Frightened installed on a fail via `_resolve_feature_save`. Seed
    Caelan + a real bandit template, then assert the feature_save outcome is
    consistent (condition installed iff the save failed)."""
    caelan = caelan_vengeance_with_bandit
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_av_{caelan['id']}", "char_id": caelan["id"],
             "name": caelan["name"], "initiative": 12,
             "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_ae_tmpl", "char_id": None,
             "token_template_id": bandit["id"], "name": bandit["name"],
             "initiative": 8, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_abjure_enemy",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": "tok_ae_tmpl",
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    fs = data["feature_save"]
    assert fs is not None, data
    assert fs["resolved"] is True, fs
    assert isinstance(fs["passed"], bool), fs
    assert fs["condition_installed"] == (not fs["passed"]), fs
    if fs["condition_installed"]:
        assert fs["condition_key"] == "frightened", fs


async def test_use_ae_target_not_in_battle(
    gm_client, caelan_vengeance_with_bandit,
):
    """Unknown target → 404."""
    caelan = caelan_vengeance_with_bandit
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_abjure_enemy",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": "tok_ghost",
            "override": True,
        },
    )
    assert r.status_code == 404, r.text


async def test_use_ae_out_of_cd(
    gm_client, caelan_vengeance_with_bandit,
):
    """CD 0 → 409."""
    caelan = caelan_vengeance_with_bandit
    await _patch_sheet(
        gm_client, caelan["id"],
        {"resources": [_cd_resource(0, 1)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_abjure_enemy",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": "tok_bandit_ae",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_ae_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_abjure_enemy",
        json={
            "character_id": caelan["id"],
            "target_combatant_id": "tok_bandit_ae",
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
