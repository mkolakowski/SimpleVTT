"""v2.99.300 → v2.158.4 — Grave Domain Cleric: Keeper of Souls (Lv 17).

v2.99.300 shipped announce-only. v2.158.4 (Phase 8 fourth commit
of the [full-feature-automation](../../docs/plans/full-feature-automation.md)
plan; fourth Lv-17 cleric capstone after Avatar of Battle, Saint
of Forge and Fire, Improved Duplicity) wires the endpoint to
install a permanent `keeper-of-souls-watcher` buff carrying
`effects.keeper_of_souls_watcher: True` +
`effects.keeper_of_souls_radius_ft: 60`. Phase 1 of the standard
install-then-deferred-read split (same shape as v2.158.3 Improved
Duplicity + v2.148.0 Fancy Footwork). Phase 2 (deferred): an
on-death hook in `_apply_damage_to_combatant`'s NPC branch reads
the buff, range-gates at 60 ft, and auto-heals the watcher for
the dying NPC's Hit Dice count.

RAW XGE p.19: when an enemy within 60 ft dies, you (or creature
of your choice within 60 ft) heal HP = enemy's Hit Dice. 1/turn.
Not while incapacitated.

Tavik PATCH'd to Grave Lv 17.

Tests:
  - Lv 17 happy with enemy HD 5 → heal 5, buff_installed True.
  - Default enemy_hit_dice missing → heal 1 (clamp).
  - Wrong subclass → 409.
  - Level gate (Lv 16) → 409.
  - Installed buff carries the two `keeper_of_souls_*` flags
    on `effects` with the right values (watcher True, radius 60).
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


def _ks_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "keeper-of-souls"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _pc(cid, c, *, hp_max=80):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_tavik_in_battle(gm_client, tavik):
    """v2.158.4 — `_install_buff` requires an active battle. Seed a
    minimal one with Tavik so the endpoint can lay down the watcher
    buff."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_ks_tavik_{tavik['id']}", tavik)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


@pytest_asyncio.fixture
async def tavik_grave_lv17(gm_client, roster):
    """PATCH Tavik to Grave Domain Lv 17."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Grave Domain", "level": 17},
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


async def test_use_ks_happy_lv17(
    gm_client, gm_ws, tavik_grave_lv17,
):
    """Lv 17 Grave, enemy HD 5 → heal 5, buff_installed True."""
    tavik = tavik_grave_lv17
    await _seed_tavik_in_battle(gm_client, tavik)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_keeper_of_souls",
        json={"character_id": tavik["id"], "enemy_hit_dice": 5},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["heal_amount"] == 5
    assert data["enemy_hit_dice"] == 5
    assert data["max_range_ft"] == 60
    assert data["cleric_level"] == 17
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _ks_broadcasts(gm_ws, tavik["id"])
    assert feats


async def test_use_ks_default_hd_clamp(
    gm_client, tavik_grave_lv17,
):
    """Missing enemy_hit_dice → heal 1 (clamp)."""
    tavik = tavik_grave_lv17
    await _seed_tavik_in_battle(gm_client, tavik)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_keeper_of_souls",
        json={"character_id": tavik["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["heal_amount"] == 1
    assert data["enemy_hit_dice"] == 1


async def test_use_ks_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_keeper_of_souls",
        json={"character_id": tavik["id"], "enemy_hit_dice": 3},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ks_level_gate(
    gm_client, roster,
):
    """Grave Tavik at Lv 16 → 409."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _patch_sheet(
        gm_client, tavik["id"],
        {"subclass": "Grave Domain", "level": 16},
        class_slug="cleric",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_keeper_of_souls",
            json={"character_id": tavik["id"], "enemy_hit_dice": 3},
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


async def test_ks_buff_payload_carries_watcher_flag_and_radius(
    gm_client, gm_ws, tavik_grave_lv17,
):
    """v2.158.4 — state contract (Phase 9): the installed
    `keeper-of-souls-watcher` buff carries
    `effects.keeper_of_souls_watcher: True` +
    `effects.keeper_of_souls_radius_ft: 60`. Phase 2 (deferred)
    will have an on-death hook in `_apply_damage_to_combatant`'s
    NPC branch read these flags off PC `_buffs_active` to identify
    watchers and range-gate; this test pins the flag shape so
    that future read site has a stable contract."""
    tavik = tavik_grave_lv17
    await _seed_tavik_in_battle(gm_client, tavik)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_keeper_of_souls",
        json={"character_id": tavik["id"], "enemy_hit_dice": 3},
    )
    assert r.status_code == 200, r.text
    bu = await gm_ws.wait_for("buff_update")
    tavik_buffs = bu["data"]["buffs"]
    ks_buff = next(
        (b for b in tavik_buffs if b.get("key") == "keeper-of-souls-watcher"),
        None,
    )
    assert ks_buff is not None, (
        f"keeper-of-souls-watcher buff missing; got keys="
        f"{[b.get('key') for b in tavik_buffs]}"
    )
    effects = ks_buff.get("effects") or {}
    assert effects.get("keeper_of_souls_watcher") is True, (
        f"watcher flag missing; got effects={effects}"
    )
    assert effects.get("keeper_of_souls_radius_ft") == 60, (
        f"radius wrong; got effects={effects}"
    )
    # Permanent passive — no concentration, very long duration.
    assert ks_buff.get("concentration") in (False, None)
    assert int(ks_buff.get("duration_rounds") or 0) >= 1000


def _mkc_npc(cid, tmpl_id, *, name, hp_cur, hp_max=20):
    return {
        "id": cid, "char_id": None, "token_template_id": tmpl_id,
        "name": name, "initiative": 10,
        "hp_current": hp_cur, "hp_max": hp_max, "speed_walk": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


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


async def test_ks_on_death_hook_heals_watcher_when_npc_dies(
    gm_client, gm_ws, tavik_grave_lv17, roster, auto_apply_on,
):
    """v2.158.6 — Phase 2 end-to-end: when an NPC dies in the same
    battle as a Grave-Lv-17 watcher, the on-death hook in
    `_apply_damage_to_combatant`'s NPC branch auto-heals the
    watcher for the dying NPC's HD count.

    Setup: install Keeper of Souls watcher buff on Tavik (Grave
    Lv 17). Seed battle with Tavik (low HP, room to heal) + Pip
    (attacker) + a Bandit NPC with HP 1 so a single Pip hit kills
    it. Bandit's `hit_dice` field on its template is read from
    SRD as `"2d8"` → 2 HD. Off-grid scene (no Token rows for the
    bandit) so the range gate falls through; the auto-heal still
    fires.

    Assertions: when Pip's attack kills the bandit, Tavik's HP
    goes up by 2 (the bandit's HD count) within the same /attack
    response, AND a `feature_used` broadcast with source
    `keeper-of-souls-trigger` fires naming Tavik as the watcher."""
    tavik = tavik_grave_lv17
    pip = roster["Pip Quickfingers"]
    tavik_tok = f"tok_ks_p2_tav_{tavik['id']}"
    pip_tok = f"tok_ks_p2_pip_{pip['id']}"
    bandit_id = "tok_ks_p2_bandit"

    # Find a bandit template (SRD bandit has `hit_dice: "2d8"`).
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(
        (t for t in templates if "bandit" in t["name"].lower()), templates[0],
    )

    # First seed battle with all three combatants — Tavik low HP
    # so the heal is observable.
    pc_low_hp = 30
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": tavik_tok, "char_id": tavik["id"], "name": tavik["name"],
             "initiative": 10, "hp_current": pc_low_hp, "hp_max": 80,
             "buffs": [], "economy": {"action": False, "bonus": False,
                                       "reaction": False, "movement": 0}},
            {"id": pip_tok, "char_id": pip["id"], "name": pip["name"],
             "initiative": 10, "hp_current": 30, "hp_max": 30,
             "buffs": [], "economy": {"action": False, "bonus": False,
                                       "reaction": False, "movement": 0}},
            _mkc_npc(bandit_id, bandit_tmpl["id"],
                     name=bandit_tmpl["name"], hp_cur=1, hp_max=20),
        ], "turn_index": 1, "round": 1, "active": True},
    )

    # Damage Tavik so the heal has room to apply (sheet-level HP).
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"hp": {"current": pc_low_hp}},
    )

    # Install Keeper of Souls watcher buff on Tavik.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_keeper_of_souls",
        json={"character_id": tavik["id"], "enemy_hit_dice": 1},
    )
    assert r.status_code == 200, r.text
    assert r.json()["buff_installed"] is True

    # Read Tavik's HP after the watcher install (no change yet).
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}"
    )
    sheet_before = (r.json().get("sheet") or {})
    hp_before = int((sheet_before.get("hp") or {}).get("current") or 0)

    # Pip swings at the 1-HP bandit until a hit lands. Bandit AC ~12;
    # Pip Shortsword +6 vs AC 12 → ~70% hit. Bound to 12 swings.
    gm_ws.mark()
    killed = False
    for _ in range(12):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": pip["id"],
                  "attack_index": 0,
                  "target_combatant_id": bandit_id,
                  "override": True},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        if d.get("hit") is True and int(d.get("damage_total") or 0) >= 1:
            killed = True
            break
    assert killed, "Pip failed to hit the 1-HP bandit in 12 swings"
    await asyncio.sleep(0.3)

    # Assert a keeper-of-souls-trigger feature_used fired with Tavik
    # as the watcher.
    trigger_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "keeper-of-souls-trigger"
        and int((m.get("data") or {}).get("watcher_char_id") or 0)
            == int(tavik["id"])
    ]
    assert trigger_msgs, (
        "no keeper-of-souls-trigger broadcast fired after the bandit "
        "died — the on-death hook didn't fire or Tavik wasn't matched "
        "as a watcher"
    )
    # Bandit HD = 2 (SRD bandit `hit_dice: "2d8"`).
    last_trigger = trigger_msgs[-1]
    assert int((last_trigger.get("data") or {}).get("enemy_hit_dice") or 0) == 2, (
        f"expected enemy_hit_dice=2 from SRD bandit; got {last_trigger}"
    )
    healed = int((last_trigger.get("data") or {}).get("heal_amount") or 0)
    assert healed == 2, (
        f"watcher should heal for 2 HP (bandit HD); got {healed}"
    )

    # Verify Tavik's HP actually went up via the heal pipeline.
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}"
    )
    sheet_after = (r.json().get("sheet") or {})
    hp_after = int((sheet_after.get("hp") or {}).get("current") or 0)
    assert hp_after == hp_before + 2, (
        f"Tavik should heal 2 HP from Keeper of Souls; "
        f"hp_before={hp_before}, hp_after={hp_after}"
    )
