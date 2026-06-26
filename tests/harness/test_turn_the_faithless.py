"""v2.99.272 — Ancients Paladin: Turn the Faithless CD (H.2 Phase 2).

H.2 Phase 2 per docs/plans/paladin-oaths.md. RAW PHB p.87:
sibling CD to Nature's Wrath. AOE within 30 ft, fey/fiends
make Wis save DC 8 + prof + CHA or be Turned for 1 minute (or
until damaged).

Mirrors v2.99.247 Conquering Presence (multi-target AOE Wis
save) but for Ancients oath instead of Conquest.

**v2.682.0 (Phase 8):** each target's WIS save is now resolved
server-side via `_resolve_feature_save` (NPC inline, PC via
RollRequest) + Turned installed on a fail (ends on damage). The
response gains `feature_saves` (one per target).

Tests:
  - Happy 2 targets → CD 1 → 0, DC 14, broadcast.
  - Apply: 2 templated NPCs → per-target save resolved + Turned on fail.
  - Empty target list → 400.
  - Unknown target → 404.
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


def _ttf_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "turn-the-faithless"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _cd_resource(current: int, maximum: int) -> dict:
    return {
        "key": "channel-divinity",
        "name": "Channel Divinity",
        "current": current, "max": maximum, "reset": "short",
        "source": "paladin Lv 3",
        "class_slug": "paladin",
        "subclass_slug": "ancients",
        "desc": "Channel Divinity (Nature's Wrath, Turn the Faithless).",
        "manual": False,
    }


@pytest_asyncio.fixture
async def caelan_ancients_with_fiends(gm_client, roster):
    """PATCH Caelan to Ancients + reset CD + seed battle with 2 fiend-flavored bandits."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {
            "subclass": "Oath of the Ancients",
            "resources": [_cd_resource(1, 1)],
        },
        class_slug="paladin",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_at_{caelan['id']}",
             "char_id": caelan["id"], "name": caelan["name"],
             "initiative": 12, "hp_current": 60, "hp_max": 60,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_fnd_a",
             "char_id": None,
             "name": "Imp", "initiative": 10,
             "hp_current": 10, "hp_max": 10,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_fnd_b",
             "char_id": None,
             "name": "Sprite", "initiative": 8,
             "hp_current": 2, "hp_max": 2,
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


async def test_use_ttf_happy(
    gm_client, gm_ws, caelan_ancients_with_fiends,
):
    """Ancients Caelan targets Imp + Sprite → DC 14, CD 1 → 0."""
    caelan = caelan_ancients_with_fiends
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_turn_the_faithless",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": ["tok_fnd_a", "tok_fnd_b"],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["save_dc"] == 14
    assert data["uses_remaining"] == 0
    assert len(data["target_combatant_ids"]) == 2
    await asyncio.sleep(0.3)
    feats = _ttf_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_ttf_resolves_saves_and_installs_turned(
    gm_client, caelan_ancients_with_fiends,
):
    """v2.682.0 — Phase 8: each templated NPC target now has its WIS save
    rolled inline + Turned installed on a fail via `_resolve_feature_save`.
    Re-seed Caelan + 2 real bandit templates, then assert each per-target
    feature_save resolved with condition_installed == (not passed)."""
    caelan = caelan_ancients_with_fiends
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_at_{caelan['id']}", "char_id": caelan["id"],
             "name": caelan["name"], "initiative": 12,
             "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_ttf_a", "char_id": None,
             "token_template_id": bandit["id"], "name": "Fiend A",
             "initiative": 10, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": "tok_ttf_b", "char_id": None,
             "token_template_id": bandit["id"], "name": "Fiend B",
             "initiative": 8, "hp_current": 50, "hp_max": 50, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_turn_the_faithless",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": ["tok_ttf_a", "tok_ttf_b"],
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    fss = data["feature_saves"]
    assert isinstance(fss, list) and len(fss) == 2, data
    for fs in fss:
        assert fs["resolved"] is True, fs
        assert isinstance(fs["passed"], bool), fs
        assert fs["condition_installed"] == (not fs["passed"]), fs
        if fs["condition_installed"]:
            assert fs["condition_key"] == "turned", fs


async def test_use_ttf_empty_target_list(
    gm_client, caelan_ancients_with_fiends,
):
    """Empty list → 400."""
    caelan = caelan_ancients_with_fiends
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_turn_the_faithless",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": [],
            "override": True,
        },
    )
    assert r.status_code == 400, r.text


async def test_use_ttf_unknown_target(
    gm_client, caelan_ancients_with_fiends,
):
    """Unknown target → 404."""
    caelan = caelan_ancients_with_fiends
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_turn_the_faithless",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": ["tok_fnd_a", "tok_ghost"],
            "override": True,
        },
    )
    assert r.status_code == 404, r.text


async def test_use_ttf_out_of_cd(
    gm_client, caelan_ancients_with_fiends,
):
    """CD 0 → 409."""
    caelan = caelan_ancients_with_fiends
    await _patch_sheet(
        gm_client, caelan["id"],
        {"resources": [_cd_resource(0, 1)]},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_turn_the_faithless",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": ["tok_fnd_a"],
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "out_of_uses"


async def test_use_ttf_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_turn_the_faithless",
        json={
            "character_id": caelan["id"],
            "target_combatant_ids": ["tok_fnd_a"],
            "override": True,
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"
