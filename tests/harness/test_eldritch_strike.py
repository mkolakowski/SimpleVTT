"""v2.99.268 — Eldritch Knight Fighter: Eldritch Strike (Phase E.2 Phase 3).

Phase E.2 Phase 3 per docs/plans/eldritch-knight.md. RAW PHB
p.74: Eldritch Knight Lv 10+ — on hit, target has disadvantage
on the next saving throw vs a spell you cast before the end of
your next turn.

v1 ships the buff install + announce; the consumer is filed.

Garrik PATCH'd to Lv 10. Tests:
  - Happy → buff_installed, broadcast.
  - Wrong subclass (default Champion) → 409.
  - Level gate (Lv 9 demo default) → 409.
  - Target not in battle → 404.
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


def _es_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "eldritch-strike"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def garrik_ek_lv10_with_target(gm_client, roster):
    """PATCH Garrik to Eldritch Knight + Lv 10; seed Garrik +
    Pip in a battle so the buff install can persist."""
    garrik = roster["Garrik Ironside"]
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Eldritch Knight", "level": 10},
        class_slug="fighter",
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_eg_{garrik['id']}",
             "char_id": garrik["id"], "name": garrik["name"],
             "initiative": 12, "hp_current": 85, "hp_max": 85,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": f"tok_ep_{pip['id']}",
             "char_id": pip["id"], "name": pip["name"],
             "initiative": 18, "hp_current": 47, "hp_max": 47,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    try:
        yield garrik, pip
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion", "level": 9},
            class_slug="fighter",
        )


async def test_use_es_happy(
    gm_client, gm_ws, garrik_ek_lv10_with_target,
):
    """Lv 10 EK Garrik marks Pip with Eldritch Strike → buff
    installed + broadcast."""
    garrik, pip = garrik_ek_lv10_with_target
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eldritch_strike",
        json={
            "character_id": garrik["id"],
            "target_combatant_id": f"tok_ep_{pip['id']}",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["target_char_id"] == pip["id"]
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _es_broadcasts(gm_ws, garrik["id"])
    assert feats


async def test_use_es_wrong_subclass(
    gm_client, roster,
):
    """Default Garrik (Champion) → 409."""
    garrik = roster["Garrik Ironside"]
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eldritch_strike",
        json={
            "character_id": garrik["id"],
            "target_combatant_id": f"tok_ep_{pip['id']}",
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_es_level_gate(
    gm_client, roster,
):
    """EK at Lv 9 (not 10+) → 409."""
    garrik = roster["Garrik Ironside"]
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(
        gm_client, garrik["id"],
        {"subclass": "Eldritch Knight"},
        class_slug="fighter",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_eldritch_strike",
            json={
                "character_id": garrik["id"],
                "target_combatant_id": f"tok_ep_{pip['id']}",
            },
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, garrik["id"],
            {"subclass": "Champion"},
            class_slug="fighter",
        )


async def _buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert resp.status_code == 200, resp.text
    return {(b or {}).get("key") for b in resp.json().get("buffs") or []}


async def test_es_auto_installs_on_weapon_hit(
    gm_client, gm_ws, garrik_ek_lv10_with_target,
):
    """v2.648.5 — RAW the Eldritch Strike marker fires automatically on a
    weapon hit; no manual /use_eldritch_strike call needed. Garrik (EK
    Lv 10) attacks Pip (override) until a hit lands → the
    eldritch-strike-target buff auto-installs on Pip + a
    feature_used(source=eldritch-strike) fires.
    """
    garrik, pip = garrik_ek_lv10_with_target
    # Sanity: Pip has no Eldritch Strike marker before the attack.
    assert "eldritch-strike-target" not in await _buff_keys(gm_client, pip["id"])

    gm_ws.mark()
    for _ in range(20):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": garrik["id"],
                "attack_index": 0,
                "target_combatant_id": f"tok_ep_{pip['id']}",
                "override": True,
                "override_range": True,
            },
        )
        assert r.status_code == 200, r.text
        if r.json().get("hit"):
            break
    else:
        raise AssertionError("Garrik never hit Pip in 20 swings")

    await asyncio.sleep(0.25)
    # The auto-install fired its announce (the same source the manual
    # endpoint uses — proving it ran without a /use_eldritch_strike call).
    assert _es_broadcasts(gm_ws, garrik["id"]), (
        "expected feature_used(source=eldritch-strike) from the auto-install"
    )
    # And the marker is actually on Pip.
    assert "eldritch-strike-target" in await _buff_keys(gm_client, pip["id"]), (
        "expected eldritch-strike-target auto-installed on Pip"
    )


async def test_es_does_not_auto_install_for_non_ek(gm_client, gm_ws, roster):
    """A non-EK fighter's weapon hit must NOT install the Eldritch
    Strike marker. Default Garrik is Champion Lv 9.
    """
    garrik = roster["Garrik Ironside"]
    pip = roster["Pip Quickfingers"]
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_eg2_{garrik['id']}", "char_id": garrik["id"],
             "name": garrik["name"], "initiative": 12,
             "hp_current": 85, "hp_max": 85, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": f"tok_ep2_{pip['id']}", "char_id": pip["id"],
             "name": pip["name"], "initiative": 18,
             "hp_current": 47, "hp_max": 47, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    for _ in range(20):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": garrik["id"],
                "attack_index": 0,
                "target_combatant_id": f"tok_ep2_{pip['id']}",
                "override": True,
                "override_range": True,
            },
        )
        assert r.status_code == 200, r.text
        if r.json().get("hit"):
            break
    await asyncio.sleep(0.2)
    assert "eldritch-strike-target" not in await _buff_keys(gm_client, pip["id"]), (
        "a Champion fighter must not install the Eldritch Strike marker"
    )


async def test_use_es_target_not_in_battle(
    gm_client, garrik_ek_lv10_with_target,
):
    """Unknown target → 404."""
    garrik, _ = garrik_ek_lv10_with_target
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_eldritch_strike",
        json={
            "character_id": garrik["id"],
            "target_combatant_id": "tok_ghost",
        },
    )
    assert r.status_code == 404, r.text
