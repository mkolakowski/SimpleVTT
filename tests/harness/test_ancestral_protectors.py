"""v2.99.366 — Path of the Ancestral Guardian Barbarian: Ancestral Protectors (G Barbarian #3, Lv 3+, XGE).

Phase G Barbarian Paths subclass batch ship #3 — Path of the
Ancestral Guardian opens.
RAW XGE p.9: while raging, the first creature you hit each turn
becomes the target of warrior spirits — until the start of your
next turn it has disadvantage on attacks not against you, and its
targets resist the damage it deals.

v1 announce-only — the disadvantage + resistance effects +
first-hit-per-turn limit are GM-tracked. No action cost.

Krieger Stonefist (Barbarian, PATCHed to Path of the Ancestral
Guardian Lv 7) is the demo fixture.

Tests:
  - Lv 7 happy: disadvantage + resistance flags True, broadcast.
  - Wrong subclass (default Berserker) → 409.
  - Wrong class (Caelan paladin) → 409.
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


def _ap_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "ancestral-protectors"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def krieger_ancestral(gm_client, roster):
    """PATCH Krieger to Path of the Ancestral Guardian; restore to Berserker."""
    krieger = roster["Krieger Stonefist"]
    await _patch_sheet(
        gm_client, krieger["id"],
        {"subclass": "Path of the Ancestral Guardian"},
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


async def test_use_ap_happy_lv7(
    gm_client, gm_ws, krieger_ancestral,
):
    """Lv 7 Ancestral Guardian → disadvantage + resistance flags."""
    krieger = krieger_ancestral
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_ancestral_protectors",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "ancestral-protectors"
    assert data["target_attack_disadvantage"] is True
    assert data["target_damage_resisted"] is True
    assert data["barbarian_level"] == 7
    await asyncio.sleep(0.3)
    feats = _ap_broadcasts(gm_ws, krieger["id"])
    assert feats
    assert feats[-1]["data"]["target_attack_disadvantage"] is True


async def test_use_ap_wrong_subclass(
    gm_client, roster,
):
    """Default Krieger (Berserker) → 409."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_ancestral_protectors",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ap_wrong_class(
    gm_client, roster,
):
    """Caelan (Paladin) → 409."""
    caelan = roster["Sir Caelan Lightbringer"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_ancestral_protectors",
        json={"character_id": caelan["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


def _pc(cid, c):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": 30, "hp_max": 30, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def test_ap_install_on_raging_hit(
    gm_client, gm_ws, krieger_ancestral, roster,
):
    """v2.136.0 — Phase 1: when a raging Ancestral Guardian hits a
    creature, install the `ancestral-protectors-mark` buff on the
    target. End-to-end: PATCH Krieger to Ancestral Guardian, rest +
    enter rage, seed battle with Krieger + Pip, POST /attack →
    Greataxe hits Pip → battle_update broadcast shows Pip carrying
    the mark buff with `effects.ancestral_protectors_protected_char_id`
    pointing at Krieger's char_id. The disadvantage half (Phase 1b)
    + resistance half (Phase 2) read this buff at attack/damage time."""
    krieger = krieger_ancestral
    pip = roster["Pip Quickfingers"]
    krieger_tok = f"tok_ap_kri_{krieger['id']}"
    pip_tok = f"tok_ap_pip_{pip['id']}"
    # Long-rest Krieger so rage uses are available.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_pc(krieger_tok, krieger), _pc(pip_tok, pip)],
              "turn_index": 0, "round": 1, "active": True},
    )
    # Enter rage so the install gate passes.
    rr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert rr.status_code == 200, rr.text
    # Krieger swings Greataxe at Pip — retry until a hit lands (the
    # default Krieger to-hit +6 vs Pip's AC has a real miss chance per
    # roll; 5 tries gives >99.5% chance of at least one hit).
    hit_resp = None
    for _ in range(5):
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": krieger["id"],
                  "attack_index": 0,
                  "target_combatant_id": pip_tok,
                  "override": True},
        )
        assert r.status_code == 200, r.text
        if r.json().get("hit") is True:
            hit_resp = r.json()
            break
    assert hit_resp is not None, (
        "Krieger's Greataxe missed Pip on 5 consecutive swings "
        "(very unlikely; check the test fixtures)"
    )
    # On a hit the install hook fires + broadcasts battle_update
    # (the install path of `_install_buff_on_combatant_id`).
    await asyncio.sleep(0.3)
    bus = gm_ws.buffered("battle_update")
    assert bus, "no battle_update broadcast received after Krieger's hit"
    combs = {c.get("id"): c for c in (bus[-1]["data"].get("combatants") or [])}
    pip_cb = combs.get(pip_tok)
    assert pip_cb is not None, (
        f"Pip's combatant missing; got ids={list(combs.keys())}"
    )
    mark_buff = next(
        (b for b in (pip_cb.get("buffs") or [])
         if b.get("key") == "ancestral-protectors-mark"),
        None,
    )
    assert mark_buff is not None, (
        f"mark buff missing from Pip after Krieger's hit; got buffs="
        f"{pip_cb.get('buffs')}"
    )
    effects = mark_buff.get("effects") or {}
    assert int(effects.get(
        "ancestral_protectors_protected_char_id") or 0) == int(krieger["id"]), (
        f"mark buff should point at Krieger's char_id; got effects={effects}"
    )


async def _seed_three_pc_battle(gm_client, krieger, pip, tavik):
    """Krieger, Pip, Tavik in init for the Phase 1b disadvantage tests."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _pc(f"tok_ap_kri_{krieger['id']}", krieger),
            _pc(f"tok_ap_pip_{pip['id']}", pip),
            _pc(f"tok_ap_tav_{tavik['id']}", tavik),
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def _hit_pip_once(gm_client, gm_ws, krieger, pip_tok):
    """Krieger swings until a hit lands. Returns the hit response or
    raises if all 5 attempts miss."""
    for _ in range(5):
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": krieger["id"],
                  "attack_index": 0,
                  "target_combatant_id": pip_tok,
                  "override": True},
        )
        assert r.status_code == 200, r.text
        if r.json().get("hit") is True:
            return r.json()
    raise AssertionError("Krieger missed Pip on 5 swings; check fixtures")


async def test_ap_marked_pc_attacks_third_party_has_disadvantage(
    gm_client, gm_ws, krieger_ancestral, roster,
):
    """v2.137.0 — Phase 1b: once Pip carries the AP mark (from
    Krieger's raging hit), Pip's next attack against Tavik (a
    non-protector) gets `disadvantage_ancestral_protectors_vs_other`
    + 2d20kl1 in the breakdown. Three-PC battle so Pip can swing at
    a target other than Krieger."""
    krieger = krieger_ancestral
    pip = roster["Pip Quickfingers"]
    tavik = roster["Brother Tavik Stonebrow"]
    pip_tok = f"tok_ap_pip_{pip['id']}"
    tav_tok = f"tok_ap_tav_{tavik['id']}"
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    await _seed_three_pc_battle(gm_client, krieger, pip, tavik)
    # Activate rage + land the mark on Pip.
    rr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert rr.status_code == 200, rr.text
    await _hit_pip_once(gm_client, gm_ws, krieger, pip_tok)
    # Now Pip swings at Tavik — Phase 1b gate should fire.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"],
              "attack_index": 0,
              "target_combatant_id": tav_tok,
              "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "2d20kl1" in (data.get("attack_breakdown") or ""), (
        f"AP mark should produce 2d20kl1 disadvantage; got "
        f"{data.get('attack_breakdown')!r}"
    )
    assert data.get("roll_state_applied") == "disadvantage_ancestral_protectors_vs_other", (
        f"roll_state_applied mismatch; got {data.get('roll_state_applied')!r}"
    )


async def test_ap_marked_pc_attacking_protector_no_disadvantage(
    gm_client, gm_ws, krieger_ancestral, roster,
):
    """v2.137.0 — Phase 1b complement: when the marked creature (Pip)
    swings AT the protector (Krieger), the gate is silent (RAW: "any
    attack roll that ISN'T against you"). No `2d20kl1` from AP, no
    `disadvantage_ancestral_protectors_vs_other` label."""
    krieger = krieger_ancestral
    pip = roster["Pip Quickfingers"]
    tavik = roster["Brother Tavik Stonebrow"]
    kri_tok = f"tok_ap_kri_{krieger['id']}"
    pip_tok = f"tok_ap_pip_{pip['id']}"
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    await _seed_three_pc_battle(gm_client, krieger, pip, tavik)
    rr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert rr.status_code == 200, rr.text
    await _hit_pip_once(gm_client, gm_ws, krieger, pip_tok)
    # Pip swings AT Krieger — should NOT get AP disadvantage.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": pip["id"],
              "attack_index": 0,
              "target_combatant_id": kri_tok,
              "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    label = data.get("roll_state_applied") or ""
    assert "ancestral_protectors_vs_other" not in label, (
        f"AP mark must not fire when swinging at the protector; "
        f"roll_state_applied={label!r}"
    )


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


async def test_ap_marked_pc_attacking_third_party_halves_damage(
    gm_client, gm_ws, krieger_ancestral, roster, auto_apply_on,
):
    """v2.138.0 — Phase 2: when Pip (carrying the AP mark) hits Tavik
    (the non-protector), the damage Tavik takes is halved. End-to-end:
    Krieger raging hits Pip → mark installed → Pip swings at Tavik → on
    a hit, `damage_applied == damage_total // 2` (and `damage_total`
    on the broadcast stays the un-halved roll for chat-card display).
    Retries until both Krieger's hit lands AND Pip's hit lands (each
    independently flaky; bound to 5+5 attempts)."""
    krieger = krieger_ancestral
    pip = roster["Pip Quickfingers"]
    tavik = roster["Brother Tavik Stonebrow"]
    pip_tok = f"tok_ap_pip_{pip['id']}"
    tav_tok = f"tok_ap_tav_{tavik['id']}"
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{krieger['id']}/rest",
        json={"type": "long"},
    )
    await _seed_three_pc_battle(gm_client, krieger, pip, tavik)
    rr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_rage",
        json={"character_id": krieger["id"], "override": True},
    )
    assert rr.status_code == 200, rr.text
    await _hit_pip_once(gm_client, gm_ws, krieger, pip_tok)
    # Pip swings at Tavik — retry until a hit lands so we can assert
    # the post-resistance damage_applied == damage_total // 2. Pip's
    # Shortsword +6 vs Tavik AC ~18 has ~45% hit; bound to 10 attempts
    # gives P(miss × 10) ≈ 0.25%.
    pip_hit = None
    for _ in range(10):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": pip["id"],
                  "attack_index": 0,
                  "target_combatant_id": tav_tok,
                  "override": True},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        if d.get("hit") is True:
            pip_hit = d
            break
    assert pip_hit is not None, (
        "Pip missed Tavik on 10 swings; check fixtures"
    )
    # AP halving: damage_applied is half of the rolled damage_total.
    # (Tavik isn't resistant to piercing; any halving here is from AP.)
    dt = int(pip_hit.get("damage_total") or 0)
    da = int(pip_hit.get("damage_applied") or 0)
    assert da == dt // 2, (
        f"AP Phase 2 should halve Tavik's damage_applied "
        f"(damage_total={dt}, expected applied={dt // 2}, got {da})"
    )
