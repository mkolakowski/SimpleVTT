"""v2.99.285 — Conquest Paladin: Scornful Rebuke (H.2 deeper, Lv 15).

H.2 Lv 15 Conquest ship. RAW XGE p.37: when a creature hits
you with an attack, that creature takes psychic damage equal
to your CHA modifier (minimum 1) if you're not incapacitated.

v1 announce-only — actual psychic-damage application to the
attacker is GM-tracked. Passive — no chip cost.

Caelan default CHA 16 → mod 3 → psychic_damage 3 (max(1, 3)).

Tests:
  - Lv 15 happy → psychic_damage 3, broadcast.
  - Wrong subclass → 409.
  - Level gate (Lv 14) → 409.
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


def _sr_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "scornful-rebuke"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def caelan_conquest_lv15(gm_client, roster):
    """PATCH Caelan to Conquest Lv 15."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Conquest", "level": 15},
        class_slug="paladin",
    )
    try:
        yield caelan
    finally:
        await _patch_sheet(
            gm_client, caelan["id"],
            {"subclass": "Oath of Devotion", "level": 7},
            class_slug="paladin",
        )


async def test_use_sr_happy_lv15(
    gm_client, gm_ws, caelan_conquest_lv15,
):
    """Lv 15 Conquest, CHA 16 → psychic_damage 3."""
    caelan = caelan_conquest_lv15
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_scornful_rebuke",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["psychic_damage"] == 3
    assert data["paladin_level"] == 15
    await asyncio.sleep(0.3)
    feats = _sr_broadcasts(gm_ws, caelan["id"])
    assert feats


async def test_use_sr_wrong_subclass(
    gm_client, roster,
):
    """Default Caelan (Devotion Lv 7) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_scornful_rebuke",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_sr_level_gate(
    gm_client, roster,
):
    """Conquest Caelan at Lv 14 → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    await _patch_sheet(
        gm_client, caelan["id"],
        {"subclass": "Oath of Conquest", "level": 14},
        class_slug="paladin",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_scornful_rebuke",
            json={"character_id": caelan["id"]},
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


def _pc(cid, c, hp=30):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp, "hp_max": hp, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _set_auto_apply(gm_client, on: bool) -> None:
    form = {
        "name": "Demo Campaign", "description": "demo",
        "game_system": "dnd5e", "gm_tab_color": "", "font_override": "",
        "default_encounter_id": "", "hp_threshold_1": "", "hp_threshold_2": "",
        "hp_threshold_3": "", "hp_threshold_4": "", "auto_play_playlist_id": "",
        "auto_play_mode": "order", "auto_play_initial_volume": "0.7",
    }
    if on:
        form["auto_apply_damage"] = "on"
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form,
        follow_redirects=False,
    )


@pytest_asyncio.fixture
async def auto_apply_on(gm_client):
    await _set_auto_apply(gm_client, True)
    yield
    await _set_auto_apply(gm_client, False)


async def test_sr_fires_on_attack_against_conquest_lv15(
    gm_client, gm_ws, caelan_conquest_lv15, roster, auto_apply_on,
):
    """v2.142.0 — Phase 1 (on-damage-taken hook). When a Conquest
    Paladin Lv 15+ is hit by an attack, the attacker takes psychic
    damage = max(1, CHA mod). End-to-end: Caelan PATCHed to Conquest
    Lv 15 (CHA 16 → mod 3), seed Caelan + Pip in battle with auto-
    apply on. Pip attacks Caelan → on a hit, the broadcast carries a
    `feature_used` with source `scornful-rebuke`. Retry-on-miss bound
    to 10 (Pip +6 vs Caelan AC ~18, ~45% hit)."""
    caelan = caelan_conquest_lv15
    pip = roster["Pip Quickfingers"]
    cael_tok = f"tok_sr_c_{caelan['id']}"
    pip_tok = f"tok_sr_p_{pip['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_pc(cael_tok, caelan), _pc(pip_tok, pip)],
              "turn_index": 1, "round": 1, "active": True},
    )
    sr_fired = False
    for _ in range(10):
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": pip["id"],
                  "attack_index": 0,
                  "target_combatant_id": cael_tok,
                  "override": True},
        )
        assert r.status_code == 200, r.text
        if r.json().get("hit") is not True:
            continue
        await asyncio.sleep(0.3)
        feats = _sr_broadcasts(gm_ws, caelan["id"])
        if feats:
            sr_fired = True
            data = feats[-1]["data"]
            assert data["psychic_damage"] == 3, (
                f"CHA 16 → mod 3 → psychic 3; got {data['psychic_damage']}"
            )
            assert int(data.get("attacker_char_id") or 0) == int(pip["id"]), (
                f"attacker_char_id should be Pip; got {data.get('attacker_char_id')!r}"
            )
            break
    assert sr_fired, (
        "Scornful Rebuke didn't fire after Pip's hit on Caelan; "
        "check the on-damage-taken hook"
    )
