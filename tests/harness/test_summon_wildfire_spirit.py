"""v2.99.318 — Wildfire Druid: Summon Wildfire Spirit (E.4 batch, Lv 2+, TCE).

E.4 Druid ship #6 (Wildfire, TCE). RAW TCE p.38: action +
Wild Shape (default) or Lv 2+ spell slot to summon Wildfire
Spirit companion for 1 hour. Once per long rest unless a
spell slot is used.

v2.1005.0 (Phase 8) — the spirit now stands up as a REAL combatant
via `_summon_companion` (token + battle-state entry, `is_summon` +
`summoned_by` tags, level-scaled HP = 5 + 5 × druid level), surfacing
`summon_combatant_id` / `summon_token_id`. Still GM-tracked: the Wild
Shape / slot consumption and the 1-hour expiry. Costs action chip.

Tests:
  - Lv 2+ happy default → resource "wild-shape", 60 min.
  - slot_level 3 → resource "spell-slot", slot_level 3.
  - v2.1005.0 → the summon lands in battle state with is_summon,
    summoned_by = Mira, and hp_max 30 at Lv 5.
  - Wrong subclass → 409.
  - Lv 1 gate → 409.
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


def _ws_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "summon-wildfire-spirit"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def mira_wildfire(gm_client, roster):
    """PATCH Mira to Wildfire."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of Wildfire"},
        class_slug="druid",
    )
    try:
        yield mira
    finally:
        await _patch_sheet(
            gm_client, mira["id"],
            {"subclass": "Circle of the Moon", "level": 5},
            class_slug="druid",
        )


async def test_use_ws_happy_lv5_default(
    gm_client, gm_ws, mira_wildfire,
):
    """Lv 5 Wildfire default → wild-shape, 60 min."""
    mira = mira_wildfire
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_summon_wildfire_spirit",
        json={"character_id": mira["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    try:
        assert data["resource_used"] == "wild-shape"
        assert data["slot_level"] is None
        assert data["duration_minutes"] == 60
        assert data["druid_level"] == 5
        await asyncio.sleep(0.3)
        feats = _ws_broadcasts(gm_ws, mira["id"])
        assert feats
    finally:
        # v2.1005.0 — the endpoint now stands up a real summon; dismiss
        # it so repeated runs don't accumulate spirits on the demo map.
        if data.get("summon_combatant_id"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
                json={"combatant_id": data["summon_combatant_id"]},
            )


async def test_use_ws_slot_variant(
    gm_client, mira_wildfire,
):
    """slot_level 3 → resource 'spell-slot'."""
    mira = mira_wildfire
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_summon_wildfire_spirit",
        json={"character_id": mira["id"], "slot_level": 3, "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    try:
        assert data["resource_used"] == "spell-slot"
        assert data["slot_level"] == 3
    finally:
        if data.get("summon_combatant_id"):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
                json={"combatant_id": data["summon_combatant_id"]},
            )


async def test_ws_summon_lands_in_battle_state(
    gm_client, gm_ws, mira_wildfire,
):
    """v2.1005.0 Phase 9 state contract — the spirit is a real
    combatant: seed a battle with Mira, summon, and the
    `battle_update` broadcast carries the returned
    `summon_combatant_id` tagged is_summon / summoned_by=Mira with
    level-scaled HP (Lv 5 → 5 + 25 = 30) at the caster's init slot."""
    mira = mira_wildfire
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_wfs_{mira['id']}", "char_id": mira["id"],
             "name": mira["name"], "initiative": 12,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_summon_wildfire_spirit",
        json={"character_id": mira["id"], "override": True,
              "x": 770.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    summon_cid = data.get("summon_combatant_id")
    assert summon_cid, data
    try:
        # The summon append broadcasts battle_update (force_gm_sync) —
        # the same assertion surface test_summon_companion.py uses.
        await asyncio.sleep(0.3)
        summon = None
        for m in gm_ws.buffered("battle_update"):
            for c in (m.get("data") or {}).get("combatants") or []:
                if c.get("id") == summon_cid:
                    summon = c
        assert summon is not None, (
            f"summon {summon_cid} missing from battle_update broadcasts"
        )
        assert summon.get("is_summon") is True
        assert summon.get("summoned_by") == mira["id"]
        assert "Wildfire Spirit" in (summon.get("name") or "")
        # Lv 5 druid → 5 + 5×5 = 30 HP per the TCE stat block.
        assert int(summon.get("hp_max") or 0) == 30, summon
        # The summon defaults to the caster's initiative slot.
        assert int(summon.get("initiative") or 0) == 12, summon
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
            json={"combatant_id": summon_cid},
        )


async def test_use_ws_wrong_subclass(
    gm_client, roster,
):
    """Default Mira (Moon) → 409."""
    mira = roster["Mira Greenleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_summon_wildfire_spirit",
        json={"character_id": mira["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ws_level_gate(
    gm_client, roster,
):
    """Wildfire Mira at Lv 1 → 409."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of Wildfire", "level": 1},
        class_slug="druid",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_summon_wildfire_spirit",
            json={"character_id": mira["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, mira["id"],
            {"subclass": "Circle of the Moon", "level": 5},
            class_slug="druid",
        )
