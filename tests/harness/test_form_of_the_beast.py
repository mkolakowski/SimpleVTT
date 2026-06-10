"""v2.99.368 — Path of the Beast Barbarian: Form of the Beast (G Barbarian batch CLOSE, Lv 3+, TCE).

Phase G Barbarian Paths subclass batch ship #6 — Path of the Beast
opens and CLOSES the Barbarian Paths batch.
RAW TCE p.9: on entering rage, manifest a natural weapon — Bite
(1d8 piercing + self-heal), Claws (1d6 slashing + extra attack),
or Tail (1d8 piercing, 10-ft reach, reaction AC).

v1 announce-only — the natural-weapon attacks + special riders are
GM-tracked. No separate action cost.

Krieger Stonefist (Barbarian, PATCHed to Path of the Beast Lv 7)
is the demo fixture.

Tests:
  - Lv 7 happy (default claws): 1d6 slashing, reach 5.
  - Lv 7 happy (tail): 1d8 piercing, reach 10.
  - Wrong subclass (default Berserker) → 409.
  - Invalid form → 400.
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


def _fb_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "form-of-the-beast"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def krieger_beast(gm_client, roster):
    """PATCH Krieger to Path of the Beast; restore to Berserker."""
    krieger = roster["Krieger Stonefist"]
    await _patch_sheet(
        gm_client, krieger["id"],
        {"subclass": "Path of the Beast"},
        class_slug="barbarian",
    )
    try:
        yield krieger
    finally:
        await _patch_sheet(
            gm_client, krieger["id"],
            {"subclass": "Path of the Berserker"},
            class_slug="barbarian",
        )


def _pc(cid, c, *, hp_max=70):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_krieger_in_battle(gm_client, krieger):
    """v2.158.20 — `_install_buff` requires an active battle."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_fb_kr_{krieger['id']}", krieger)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def test_use_fb_happy_claws(
    gm_client, gm_ws, krieger_beast,
):
    """Lv 7 Path of the Beast, default → claws 1d6 slashing,
    buff_installed True."""
    krieger = krieger_beast
    await _seed_krieger_in_battle(gm_client, krieger)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_form_of_the_beast",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "form-of-the-beast"
    assert data["form"] == "claws"
    assert data["damage_die"] == "1d6"
    assert data["damage_type"] == "slashing"
    assert data["reach_ft"] == 5
    assert data["barbarian_level"] == 7
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _fb_broadcasts(gm_ws, krieger["id"])
    assert feats
    assert feats[-1]["data"]["form"] == "claws"


async def test_use_fb_happy_tail(
    gm_client, krieger_beast,
):
    """form=tail → 1d8 piercing, reach 10."""
    krieger = krieger_beast
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_form_of_the_beast",
        json={"character_id": krieger["id"], "form": "tail"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["form"] == "tail"
    assert data["damage_die"] == "1d8"
    assert data["reach_ft"] == 10


async def test_use_fb_wrong_subclass(
    gm_client, roster,
):
    """Default Krieger (Berserker) → 409."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_form_of_the_beast",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_fb_invalid_form(
    gm_client, krieger_beast,
):
    """Invalid form → 400."""
    krieger = krieger_beast
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_form_of_the_beast",
        json={"character_id": krieger["id"], "form": "wings"},
    )
    assert r.status_code == 400, r.text


async def test_attack_with_buff_derived_natural_weapon(
    gm_client, gm_ws, krieger_beast,
):
    """v2.158.26 — Phase 2 read site: /attack merges sheet.attacks
    with the buff-derived natural weapons (from
    `_pc_active_natural_weapons`), so an attack_index past the sheet's
    regular attacks resolves to a Form-of-the-Beast entry. End-to-end:
    install bite form → POST /attack with attack_index = len(sheet.attacks)
    → expect attack_name contains "Bite", damage_type "piercing", and
    standard attack/damage rolls."""
    krieger = krieger_beast
    await _seed_krieger_in_battle(gm_client, krieger)
    # Read Krieger's sheet to find the natural-weapon index dynamically.
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-json",
    )
    assert r.status_code == 200, r.text
    sheet = r.json().get("sheet") or {}
    base_attacks = sheet.get("attacks") or []
    natural_index = len(base_attacks)
    # Install bite form.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_form_of_the_beast",
        json={"character_id": krieger["id"], "form": "bite"},
    )
    assert r.status_code == 200, r.text
    # Confirm the merged list now has the natural-weapon at natural_index.
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active_natural_weapons",
        params={"character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["natural_weapons"]) == 1
    # Attack via the merged index.
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": natural_index,
            "override": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "Bite" in data["attack_name"], (
        f"expected 'Bite' in attack_name; got {data['attack_name']!r}"
    )
    assert data["damage_type"] == "piercing"
    assert data["attack_total"] >= 1
    assert data["damage_total"] >= 1
    msg = await gm_ws.wait_for("weapon_attack")
    assert "Bite" in msg["data"]["attack_name"]


async def test_attack_natural_weapon_index_404s_without_buff(
    gm_client, krieger_beast,
):
    """Control: without the form-of-the-beast buff, an attack_index
    past sheet.attacks still 404s — the merge only kicks in when the
    buff is active."""
    krieger = krieger_beast
    # Wipe any stale battle state so no stray buff is present.
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [], "turn_index": 0, "round": 1, "active": False,
        },
    )
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-json",
    )
    sheet = r.json().get("sheet") or {}
    out_of_range_index = len(sheet.get("attacks") or [])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": out_of_range_index,
            "override": True,
        },
    )
    assert r.status_code == 404, r.text


def _mkc_npc(cid, tmpl_id, *, name, hp_cur=1, hp_max=20):
    return {
        "id": cid, "char_id": None, "token_template_id": tmpl_id,
        "name": name, "initiative": 10,
        "hp_current": hp_cur, "hp_max": hp_max, "speed_walk": 30,
        "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0, "dash_bonus_ft": 0},
    }


async def _set_auto_apply(gm_client, on: bool):
    form = {
        "name": "Demo Campaign", "description": "demo",
        "game_system": "dnd5e", "gm_tab_color": "", "font_override": "",
        "default_encounter_id": "", "hp_threshold_1": "",
        "hp_threshold_2": "", "hp_threshold_3": "", "hp_threshold_4": "",
        "auto_play_playlist_id": "", "auto_play_mode": "order",
        "auto_play_initial_volume": "0.7",
    }
    if on:
        form["auto_apply_damage"] = "on"
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form,
        follow_redirects=False,
    )


@pytest_asyncio.fixture
async def fb_bite_auto_apply_on(gm_client):
    await _set_auto_apply(gm_client, True)
    yield
    await _set_auto_apply(gm_client, False)


async def _seed_krieger_vs_bandit(
    gm_client, krieger, *, krieger_hp_cur, bandit_hp_cur=1,
):
    """Seed a 2-combatant battle: Krieger (live HP set via PATCH +
    combatant payload) plus a bandit set up for a near-guaranteed hit
    (1 HP, default bandit AC ~12). Returns the bandit token id."""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(
        (t for t in templates if "bandit" in t["name"].lower()),
        templates[0],
    )
    bandit_id = f"tok_fb_bite_bandit_{krieger['id']}"
    krieger_tok = f"tok_fb_bite_kr_{krieger['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": krieger_tok, "char_id": krieger["id"],
             "name": krieger["name"], "initiative": 20,
             "hp_current": krieger_hp_cur, "hp_max": 75,
             "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            _mkc_npc(bandit_id, bandit_tmpl["id"],
                     name=bandit_tmpl["name"], hp_cur=bandit_hp_cur),
        ], "turn_index": 0, "round": 1, "active": True},
    )
    return bandit_id


async def test_bite_self_heal_fires_when_below_half_hp_on_hit(
    gm_client, gm_ws, krieger_beast, fb_bite_auto_apply_on,
):
    """v2.158.28 — Phase 2 bite rider: Krieger Path of the Beast Lv 7
    with HP set below half max (30 / 75 → 40%), bite form installed.
    Swing at the 1-HP bandit until a hit lands → expect a
    feature_used broadcast with source "form-of-the-beast-bite-heal"
    + healed == prof_bonus (+3 at Lv 7 RAW)."""
    krieger = krieger_beast
    # PATCH Krieger's sheet HP to 30/75 (below half).
    await _patch_sheet(
        gm_client, krieger["id"],
        {"hp": {"current": 30, "max": 75, "temp": 0}},
        class_slug="barbarian",
    )
    await _seed_krieger_vs_bandit(
        gm_client, krieger, krieger_hp_cur=30,
    )
    # Read sheet to find the natural-weapon index dynamically.
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-json",
    )
    sheet = r.json().get("sheet") or {}
    natural_index = len(sheet.get("attacks") or [])
    bandit_id = (
        f"tok_fb_bite_bandit_{krieger['id']}"
    )
    # Install bite form.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_form_of_the_beast",
        json={"character_id": krieger["id"], "form": "bite"},
    )
    assert r.status_code == 200, r.text
    # Swing until a hit lands. Krieger +7 vs AC 12 → ~80% hit rate;
    # bound to 10 swings.
    gm_ws.mark()
    landed_hit = False
    for _ in range(10):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": krieger["id"],
                  "attack_index": natural_index,
                  "target_combatant_id": bandit_id,
                  "override": True},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        if d.get("hit") is True and int(d.get("damage_total") or 0) >= 1:
            landed_hit = True
            break
    assert landed_hit, "Krieger failed to bite-hit the bandit in 10 swings"
    await asyncio.sleep(0.3)
    # Bite-heal feature_used broadcast.
    heal_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "form-of-the-beast-bite-heal"
        and int((m.get("data") or {}).get("character_id") or 0)
            == int(krieger["id"])
    ]
    assert heal_msgs, (
        "no form-of-the-beast-bite-heal broadcast fired after the bite "
        "hit — the bite Phase-2 hook didn't fire or didn't match Krieger"
    )
    last = heal_msgs[-1]["data"]
    # Krieger Lv 7 proficiency_bonus = 3.
    assert int(last.get("prof_bonus") or 0) == 3, (
        f"expected prof_bonus=3 at Lv 7; got {last}"
    )
    assert int(last.get("healed") or 0) == 3, (
        f"expected healed=3 (prof bonus); got {last}"
    )


async def test_bite_self_heal_does_not_fire_at_full_hp(
    gm_client, gm_ws, krieger_beast, fb_bite_auto_apply_on,
):
    """Control: at full HP (75/75), the bite-heal RAW gate ("less than
    half") blocks. No `form-of-the-beast-bite-heal` broadcast even
    after a confirmed bite hit."""
    krieger = krieger_beast
    await _patch_sheet(
        gm_client, krieger["id"],
        {"hp": {"current": 75, "max": 75, "temp": 0}},
        class_slug="barbarian",
    )
    await _seed_krieger_vs_bandit(
        gm_client, krieger, krieger_hp_cur=75,
    )
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-json",
    )
    sheet = r.json().get("sheet") or {}
    natural_index = len(sheet.get("attacks") or [])
    bandit_id = f"tok_fb_bite_bandit_{krieger['id']}"
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_form_of_the_beast",
        json={"character_id": krieger["id"], "form": "bite"},
    )
    assert r.status_code == 200, r.text
    gm_ws.mark()
    for _ in range(6):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": krieger["id"],
                  "attack_index": natural_index,
                  "target_combatant_id": bandit_id,
                  "override": True},
        )
        assert r.status_code == 200, r.text
        if r.json().get("hit") is True:
            break
    await asyncio.sleep(0.3)
    heal_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "form-of-the-beast-bite-heal"
    ]
    assert not heal_msgs, (
        f"bite self-heal should NOT fire at full HP; got {heal_msgs}"
    )


async def test_claws_form_does_not_trigger_bite_self_heal(
    gm_client, gm_ws, krieger_beast, fb_bite_auto_apply_on,
):
    """Control: at low HP but with CLAWS form (not bite), no self-heal
    fires. Pins the form-gate in the helper."""
    krieger = krieger_beast
    await _patch_sheet(
        gm_client, krieger["id"],
        {"hp": {"current": 30, "max": 75, "temp": 0}},
        class_slug="barbarian",
    )
    await _seed_krieger_vs_bandit(
        gm_client, krieger, krieger_hp_cur=30,
    )
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/sheet-json",
    )
    sheet = r.json().get("sheet") or {}
    natural_index = len(sheet.get("attacks") or [])
    bandit_id = f"tok_fb_bite_bandit_{krieger['id']}"
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_form_of_the_beast",
        json={"character_id": krieger["id"], "form": "claws"},
    )
    assert r.status_code == 200, r.text
    gm_ws.mark()
    for _ in range(6):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": krieger["id"],
                  "attack_index": natural_index,
                  "target_combatant_id": bandit_id,
                  "override": True},
        )
        assert r.status_code == 200, r.text
        if r.json().get("hit") is True:
            break
    await asyncio.sleep(0.3)
    heal_msgs = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "form-of-the-beast-bite-heal"
    ]
    assert not heal_msgs, (
        f"claws form should not trigger bite self-heal; got {heal_msgs}"
    )


async def test_fb_buff_payload_carries_form_parameter_flags(
    gm_client, gm_ws, krieger_beast,
):
    """v2.158.20 — state contract (Phase 9): the installed
    `form-of-the-beast-active` buff carries the six
    `form_of_the_beast_*` effect keys with the right values
    (active=True, form="bite", damage_die="1d8",
    damage_type="piercing", reach_ft=5, special string)."""
    krieger = krieger_beast
    await _seed_krieger_in_battle(gm_client, krieger)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_form_of_the_beast",
        json={"character_id": krieger["id"], "form": "bite"},
    )
    assert r.status_code == 200, r.text
    bu = await gm_ws.wait_for("buff_update")
    krieger_buffs = bu["data"]["buffs"]
    fb_buff = next(
        (b for b in krieger_buffs
         if b.get("key") == "form-of-the-beast-active"),
        None,
    )
    assert fb_buff is not None, (
        f"form-of-the-beast-active buff missing; got keys="
        f"{[b.get('key') for b in krieger_buffs]}"
    )
    effects = fb_buff.get("effects") or {}
    assert effects.get("form_of_the_beast_active") is True
    assert effects.get("form_of_the_beast_form") == "bite"
    assert effects.get("form_of_the_beast_damage_die") == "1d8"
    assert effects.get("form_of_the_beast_damage_type") == "piercing"
    assert effects.get("form_of_the_beast_reach_ft") == 5
    # Rage-duration buff (1 minute = 10 rounds), not concentration.
    assert fb_buff.get("concentration") in (False, None)
    assert int(fb_buff.get("duration_rounds") or 0) == 10
