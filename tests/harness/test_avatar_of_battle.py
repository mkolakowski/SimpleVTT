"""v2.99.296 → v2.158.0 — War Domain Cleric: Avatar of Battle (Lv 17).

v2.99.296 shipped announce-only. v2.158.0 (Phase 8 of the
full-feature-automation plan kick-off) wires the endpoint to install
a permanent `avatar-of-battle` buff carrying
`effects.resistance_to = ["nonmagical-bludgeoning",
"nonmagical-piercing", "nonmagical-slashing"]`. The F6
`_resistance_matches_damage` matcher (v2.63.0) skips the resistance
when the incoming attack is flagged `is_magical=True` so the damage
pipeline halves only mundane BPS attacks.

RAW PHB p.63: resistance to bludgeoning, piercing, and slashing
damage from nonmagical attacks. No chip cost — passive permanent.

Tests:
  - Lv 17 happy → resistance_types BPS, nonmagical_only True,
    buff_installed True, broadcast.
  - Wrong subclass → 409.
  - Level gate (Lv 16) → 409.
  - Installed buff carries the three nonmagical-X resistance
    entries (`effects.resistance_to`).
  - End-to-end: Pip's nonmagical Shortsword (piercing) against the
    War-Lv-17 Tavik who carries the buff produces
    `damage_applied == damage_total // 2`.
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


def _aob_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "avatar-of-battle"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _pc(cid, c, *, hp_max=80):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_tavik_in_battle(gm_client, tavik):
    """v2.158.0 — `_install_buff` requires an active battle + the
    cleric to be in init. Seed a minimal battle with Tavik as the
    sole combatant so the endpoint can install the resistance buff.
    """
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_aob_tavik_{tavik['id']}", tavik)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


@pytest_asyncio.fixture
async def tavik_war_lv17(gm_client, roster):
    """PATCH Tavik to War Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "War Domain", "level": 17},
        class_slug="cleric",
    )
    try:
        yield tavik
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_use_aob_happy_lv17(
    gm_client, gm_ws, tavik_war_lv17,
):
    """Lv 17 War → resistance to nonmagical BPS, buff installed."""
    tavik = tavik_war_lv17
    await _seed_tavik_in_battle(gm_client, tavik)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_avatar_of_battle",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "bludgeoning" in data["resistance_types"]
    assert "piercing" in data["resistance_types"]
    assert "slashing" in data["resistance_types"]
    assert data["nonmagical_only"] is True
    assert data["cleric_level"] == 17
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _aob_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_aob_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_avatar_of_battle",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_aob_level_gate(
    gm_client, roster,
):
    """War Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "War Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_avatar_of_battle",
            json={"character_id": tavik["id"]},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, tavik["id"],
            {"subclass": "Life Domain", "level": 6},
            class_slug="cleric",
        )


async def test_aob_buff_payload_carries_nonmagical_bps_resistance(
    gm_client, gm_ws, tavik_war_lv17,
):
    """v2.158.0 — assert the installed `avatar-of-battle` buff carries
    `effects.resistance_to` with all three `nonmagical-X` entries.
    These are the strings the F6 `_resistance_matches_damage` matcher
    looks for; if any go missing the damage pipeline stops halving
    that type. State-change contract (Phase 9): the test asserts the
    buff payload, not just the broadcast."""
    tavik = tavik_war_lv17
    await _seed_tavik_in_battle(gm_client, tavik)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_avatar_of_battle",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    bu = await gm_ws.wait_for("buff_update")
    tavik_buffs = bu["data"]["buffs"]
    aob_buff = next(
        (b for b in tavik_buffs if b.get("key") == "avatar-of-battle"),
        None,
    )
    assert aob_buff is not None, (
        f"avatar-of-battle buff missing from Tavik; got keys="
        f"{[b.get('key') for b in tavik_buffs]}"
    )
    effects = aob_buff.get("effects") or {}
    resist = [(str(r) or "").strip().lower()
              for r in (effects.get("resistance_to") or [])]
    assert "nonmagical-bludgeoning" in resist, (
        f"missing nonmagical-bludgeoning; got resist={resist}"
    )
    assert "nonmagical-piercing" in resist, (
        f"missing nonmagical-piercing; got resist={resist}"
    )
    assert "nonmagical-slashing" in resist, (
        f"missing nonmagical-slashing; got resist={resist}"
    )
    # Permanent passive — no concentration, very long duration.
    assert aob_buff.get("concentration") in (False, None)
    assert int(aob_buff.get("duration_rounds") or 0) >= 1000


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


async def test_aob_halves_nonmagical_piercing_damage(
    gm_client, gm_ws, tavik_war_lv17, roster, auto_apply_on,
):
    """v2.158.0 — end-to-end: Pip's Shortsword (nonmagical piercing)
    against the Avatar-of-Battle-buffed Tavik should produce
    `damage_applied == damage_total // 2`. This is the Phase-9 state
    contract for the feature: the resistance buff actually halves
    incoming damage through the pipeline, not just the broadcast.

    Retries up to 12 attempts to bound flakiness (Pip's hit chance
    against Tavik AC ~18 is ~40%; floor `damage_total >= 2` so
    integer-half is non-trivial). Reuses the test_ancestral_protectors
    auto_apply pattern."""
    tavik = tavik_war_lv17
    pip = roster["Pip Quickfingers"]
    tavik_tok = f"tok_aob_tavik_{tavik['id']}"
    pip_tok = f"tok_aob_pip_{pip['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_pc(tavik_tok, tavik), _pc(pip_tok, pip)],
              "turn_index": 1, "round": 1, "active": True},
    )
    # Install Avatar of Battle on Tavik.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_avatar_of_battle",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["buff_installed"] is True

    # Pip swings until a hit lands and damage rolls high enough that
    # integer-half is non-trivial (damage_total >= 2).
    hit = None
    for _ in range(12):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": pip["id"],
                  "attack_index": 0,
                  "target_combatant_id": tavik_tok,
                  "override": True},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        if d.get("hit") is True and int(d.get("damage_total") or 0) >= 2:
            hit = d
            break
    assert hit is not None, (
        "Pip's Shortsword failed to land a hit with damage>=2 in 12 "
        "swings — investigate fixture / AC drift"
    )
    dt = int(hit.get("damage_total") or 0)
    da = int(hit.get("damage_applied") or 0)
    assert da == dt // 2, (
        f"Avatar of Battle should halve Pip's nonmagical piercing "
        f"damage_applied (damage_total={dt}, expected applied={dt // 2}, "
        f"got {da})"
    )
