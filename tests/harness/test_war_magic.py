"""v2.99.267 — Eldritch Knight Fighter: War Magic (Phase E.2 Phase 2).

Phase E.2 Phase 2 per docs/plans/eldritch-knight.md. RAW PHB
p.74: Eldritch Knight Lv 7+ — after casting a cantrip with
your action, make one weapon attack as a bonus action.

v1 ships announce-only — the cantrip prereq is GM-tracked;
deeper /cast_spell-hook integration filed for follow-up.

Garrik Lv 9 is the demo fixture. Tests PATCH his subclass to
"Eldritch Knight"; he's already past Lv 7.

Tests:
  - Happy → bonus chip marked + broadcast.
  - Wrong subclass (default Champion) → 409.
  - Level gate (Lv 6) → 409.
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


def _wm_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "war-magic"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def garrik_eldritch_knight(gm_client, roster):
    """PATCH Garrik to Eldritch Knight + put him in a battle so
    the bonus chip can be marked."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Eldritch Knight"},
        class_slug="fighter",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_gk_{garrik['id']}",
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
            {"subclass": "Champion"},
            class_slug="fighter",
        )


async def test_use_wm_happy(
    gm_client, gm_ws, garrik_eldritch_knight,
):
    """Lv 9 Eldritch Knight Garrik → 200 + broadcast."""
    garrik = garrik_eldritch_knight
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_war_magic",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "war-magic"
    await asyncio.sleep(0.3)
    feats = _wm_broadcasts(gm_ws, garrik["id"])
    assert feats


async def test_wm_improved_widens_prerequisite(
    gm_client, gm_ws, garrik_eldritch_knight,
):
    """v2.158.40 — Phase 2 read site for the v2.158.12 Improved War
    Magic buff. A Lv 18 EK carrying `improved-war-magic-active` sees
    `/use_war_magic` widen the prerequisite to any Lv 1+ spell: the
    response carries `improved_war_magic == True` + `spell_min_level
    == 1`, the broadcast names "Improved War Magic", and the desc
    mentions the Lv 1+ widening."""
    garrik = garrik_eldritch_knight
    await _patch_sheet(
        gm_client, garrik["id"], {"level": 18}, class_slug="fighter",
    )
    try:
        # Phase 1: install the Improved War Magic buff.
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_improved_war_magic",
            json={"character_id": garrik["id"], "override": True},
        )
        assert r.status_code == 200, r.text
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_war_magic",
            json={"character_id": garrik["id"], "override": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("improved_war_magic") is True, (
            f"buff present → improved_war_magic True; got {data}"
        )
        assert data.get("spell_min_level") == 1
        msg = await gm_ws.wait_for("feature_used")
        assert msg["data"]["source"] == "war-magic"
        assert msg["data"].get("improved_war_magic") is True
        assert msg["data"].get("spell_min_level") == 1
        assert "Lv 1+" in (msg["data"].get("feature_desc") or "")
    finally:
        await _patch_sheet(
            gm_client, garrik["id"], {"level": 9}, class_slug="fighter",
        )


async def test_wm_base_cantrip_only_without_buff(
    gm_client, garrik_eldritch_knight,
):
    """Control: with the Improved War Magic buff removed,
    `/use_war_magic` reports the base cantrip-only prerequisite
    (`improved_war_magic == False`, `spell_min_level == 0`). Installs
    then ends the buff so the sheet mirror is clean regardless of
    prior test state (the buff is permanent)."""
    garrik = garrik_eldritch_knight
    await _patch_sheet(
        gm_client, garrik["id"], {"level": 18}, class_slug="fighter",
    )
    try:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_improved_war_magic",
            json={"character_id": garrik["id"], "override": True},
        )
        end = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": garrik["id"],
                  "key": "improved-war-magic-active"},
        )
        assert end.status_code == 200, end.text
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_war_magic",
            json={"character_id": garrik["id"], "override": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("improved_war_magic") is False, (
            f"no buff → improved_war_magic False; got {data}"
        )
        assert data.get("spell_min_level") == 0
    finally:
        await _patch_sheet(
            gm_client, garrik["id"], {"level": 9}, class_slug="fighter",
        )


async def test_use_wm_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_war_magic",
        json={"character_id": garrik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_wm_level_gate(
    gm_client, roster,
):
    """Eldritch Knight at Lv 6 (not 7+) → 409."""
    garrik = roster["Garrik Ironside"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Eldritch Knight", "level": 6},
        class_slug="fighter",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_war_magic",
            json={"character_id": garrik["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion", "level": 9},
            class_slug="fighter",
        )
