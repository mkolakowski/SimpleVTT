"""Broadcast payload-shape assertions (v2.43.12).

Locks in the fields each broadcast type must carry so the roll-log
cards + the dice/status toasts can render correctly. The client
readers are:

  - ``appendRoll`` / ``appendSpellCast`` / ``appendWeaponAttack`` /
    ``_appendFeatureUsed`` in ``app/static/tabletop.js`` — render the
    persistent roll-log cards.
  - ``showRollToast`` + the ``vtt:ws-message`` listener in
    ``app/static/roll_toast.js`` — fire the transient dice toasts.

Each test below fires a single happy-path call to a real endpoint and
asserts every field the client side reads is populated. When a field
becomes optional or gets renamed, the corresponding test breaks
loudly — the goal is to catch silent payload regressions before they
ship.

These tests are *additive* to the existing per-endpoint files (which
focus on behavior — chip flips, HP deltas, counter decrements, error
paths). The split: behavior tests in ``test_<endpoint>.py``, payload
shape tests here.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# ─────────────────────────────────────────────────────────────────────
# Fixtures — long-rest the demo PCs so resource counters are full and
# HP is at max. The shape tests don't care about state mutations; they
# just need a known starting point.
# ─────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def garrik_rested(gm_client, roster):
    garrik = roster["Garrik Ironside"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/rest",
        json={"type": "long"},
    )
    return garrik


@pytest_asyncio.fixture
async def caelan_rested(gm_client, roster):
    caelan = roster["Sir Caelan Lightbringer"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    return caelan


@pytest_asyncio.fixture
async def tavik_rested(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    return tavik


@pytest_asyncio.fixture
async def thal_rested(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    return thal


# ─────────────────────────────────────────────────────────────────────
# Helper — assert every key in ``required`` is present on ``payload``
# (does not assert types or non-emptiness; null is allowed unless the
# test asserts otherwise inline).
# ─────────────────────────────────────────────────────────────────────


def _assert_keys(payload: dict, required: set[str], context: str) -> None:
    missing = required - set(payload.keys())
    assert not missing, (
        f"{context}: broadcast payload missing required keys: {sorted(missing)}. "
        f"Got keys: {sorted(payload.keys())}"
    )


# ─────────────────────────────────────────────────────────────────────
# /roll  — plain dice roll
# Client reader: appendRoll in tabletop.js + showRollToast in roll_toast.js
# ─────────────────────────────────────────────────────────────────────


async def test_roll_broadcast_carries_all_required_fields(gm_client, gm_ws):
    """``/roll`` broadcast must carry every field both the roll-log card
    (``appendRoll``) and the dice toast (``showRollToast``) read.
    """
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={"expression": "2d6+3", "label": "Payload shape test"},
    )
    assert resp.status_code == 200
    msg = await gm_ws.wait_for("roll")
    d = msg["data"]

    _assert_keys(d, {
        # required for the big-number column + breakdown pill
        "total", "expression", "breakdown",
        # required for the header (avatar + name + visibility badge + time)
        "user_id", "user_name", "visibility",
        # the note line in the body
        "note",
    }, "/roll broadcast")

    # Values should match the request.
    assert isinstance(d["total"], int)
    assert "1" <= d["breakdown"][0] <= "9"  # breakdown starts with the die count
    assert d["expression"] == "2d6+3"
    assert d["visibility"] in ("public", "gm_only", "gm_and_roller")


async def test_roll_broadcast_carries_visibility_field(gm_client, gm_ws):
    """The visibility filter on both surfaces requires this field."""
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={"expression": "1d20", "visibility": "gm_only"},
    )
    assert resp.status_code == 200
    msg = await gm_ws.wait_for("roll")
    assert msg["data"]["visibility"] == "gm_only"


# ─────────────────────────────────────────────────────────────────────
# /attack  — weapon_attack
# Client reader: appendWeaponAttack in tabletop.js + roll_toast.js
# ─────────────────────────────────────────────────────────────────────


async def test_weapon_attack_broadcast_carries_all_required_fields(gm_client, gm_ws, roster):
    """A weapon strike's WS broadcast must carry every field the
    weapon-attack card + the attack/damage toasts read.
    """
    krieger = roster["Krieger Stonefist"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={"character_id": krieger["id"], "attack_index": 0, "override": True},
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("weapon_attack")
    d = msg["data"]

    _assert_keys(d, {
        # Card body — attack pill
        "attack_total", "attack_breakdown", "attack_name",
        # Card body — damage pill
        "damage_total", "damage_breakdown", "damage_type",
        # Card header
        "caster_user_id", "caster_user_name", "caster_char_name",
        # Toast + Undo wiring
        "id",
        # The hit-determination fields (T.2). When no target was set,
        # ``hit`` is null but the field is still present.
        "hit", "is_crit",
        # is_save gates the attack-line pill vs save-prompt pill.
        "is_save",
        # Over-budget gating + audit badge
        "over_budget",
    }, "/attack broadcast")

    # Concrete values.
    assert isinstance(d["attack_total"], int) and d["attack_total"] >= 1
    assert isinstance(d["damage_total"], int) and d["damage_total"] >= 1
    assert d["attack_name"]  # non-empty
    assert d["damage_type"]  # non-empty


# ─────────────────────────────────────────────────────────────────────
# /cast_spell  — spell_cast (heal path)
# ─────────────────────────────────────────────────────────────────────


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )


async def test_spell_cast_heal_broadcast_carries_all_required_fields(
    gm_client, gm_ws, roster, tavik_rested,
):
    """Tavik casts Healing Word on Pip — the spell-cast card's heal
    pill needs the ``auto_heal_*`` fields, plus the common spell-cast
    header fields.
    """
    tavik = tavik_rested
    pip = roster["Pip Quickfingers"]
    # Drop Pip below max so the heal actually lands.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"hp": {"current": 10}},
    )
    await _seed_battle(gm_client, [
        {"id": f"tok_shape_{tavik['id']}", "char_id": tavik["id"],
         "name": tavik["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": f"tok_shape_{pip['id']}", "char_id": pip["id"],
         "name": pip["name"], "initiative": 8, "hp_current": 10, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])

    gm_ws.mark()
    HEALING_WORD_INDEX = 5
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": HEALING_WORD_INDEX,
            "slot_level": 1,
            "class_slug": "cleric",
            "target_character_id": pip["id"],
            "target_combatant_id": f"tok_shape_{pip['id']}",
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("spell_cast")
    d = msg["data"]

    _assert_keys(d, {
        # Header
        "spell_name", "slot_level", "spell_level",
        "caster_user_id", "caster_user_name", "caster_char_name",
        # Inline meta row
        "spell_school", "spell_casting_time", "spell_range",
        # Target tag (in header)
        "target_name",
        # Auto-resolution heal pill
        "auto_heal_applied", "auto_heal_target_name",
        "auto_heal_hp_before", "auto_heal_hp_after",
        # Undo wiring
        "id",
        # Manual-button gating
        "actions",
    }, "/cast_spell (heal) broadcast")

    assert d["auto_heal_applied"] > 0
    assert d["auto_heal_target_name"] == pip["name"]
    assert d["auto_heal_hp_after"] > d["auto_heal_hp_before"]


async def test_spell_cast_attack_broadcast_carries_all_required_fields(
    gm_client, gm_ws, roster, thal_rested,
):
    """Thalindra casts Fire Bolt at a bandit — the spell-cast card's
    attack-roll pill needs ``auto_attack_*`` fields.
    """
    thal = thal_rested
    # Need an NPC target.
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(t for t in templates if "bandit" in t["name"].lower())
    await _seed_battle(gm_client, [
        {"id": f"tok_shape_{thal['id']}", "char_id": thal["id"],
         "name": thal["name"], "initiative": 10, "hp_current": 24, "hp_max": 24,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_shape_bandit_atk", "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7, "hp_current": 50, "hp_max": 50,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])

    gm_ws.mark()
    FIRE_BOLT_INDEX = 0
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIRE_BOLT_INDEX,
            "slot_level": 0,
            "class_slug": "wizard",
            "target_combatant_id": "tok_shape_bandit_atk",
            "target_name": bandit_tmpl["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("spell_cast")
    d = msg["data"]

    _assert_keys(d, {
        "spell_name",
        "caster_user_id", "caster_char_name",
        "auto_attack_hit", "auto_attack_total", "auto_attack_breakdown",
        "auto_attack_target_name", "auto_attack_target_ac",
        "auto_attack_damage_type",
        "id",
    }, "/cast_spell (attack) broadcast")

    # auto_attack_hit can be True / False but should never be null here
    # since a target was set.
    assert d["auto_attack_hit"] in (True, False)
    assert isinstance(d["auto_attack_total"], int)


async def test_spell_cast_save_broadcast_carries_all_required_fields(
    gm_client, gm_ws, roster, tavik_rested,
):
    """Tavik casts Hold Person on a bandit — the spell-cast card's
    save pill needs ``auto_save_*`` fields. Loops up to 10 attempts in
    case the random save lands ``auto_save_passed`` False vs True (the
    shape is the same either way).
    """
    tavik = tavik_rested
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(t for t in templates if "bandit" in t["name"].lower())
    await _seed_battle(gm_client, [
        {"id": f"tok_shape_{tavik['id']}", "char_id": tavik["id"],
         "name": tavik["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        {"id": "tok_shape_bandit_save", "char_id": None,
         "token_template_id": bandit_tmpl["id"],
         "name": bandit_tmpl["name"], "initiative": 7, "hp_current": 11, "hp_max": 11,
         "buffs": [],
         "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
    ])

    HOLD_PERSON_INDEX = 8
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": HOLD_PERSON_INDEX,
            "slot_level": 2,
            "class_slug": "cleric",
            "target_combatant_id": "tok_shape_bandit_save",
            "target_name": bandit_tmpl["name"],
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("spell_cast")
    d = msg["data"]

    _assert_keys(d, {
        "spell_name",
        "auto_save_target_kind", "auto_save_target_name",
        "auto_save_ability", "auto_save_dc",
        "auto_save_rolled", "auto_save_breakdown", "auto_save_passed",
        "id",
    }, "/cast_spell (save) broadcast")

    assert d["auto_save_target_kind"] == "npc"
    assert d["auto_save_ability"] == "WIS"
    assert isinstance(d["auto_save_dc"], int)
    assert isinstance(d["auto_save_rolled"], int)
    assert isinstance(d["auto_save_passed"], bool)


# ─────────────────────────────────────────────────────────────────────
# /use_feature  — feature_used (generic class feature, no dice)
# ─────────────────────────────────────────────────────────────────────


async def test_feature_used_simple_broadcast_carries_all_required_fields(
    gm_client, gm_ws, roster,
):
    """A generic class feature (Cunning Action) — no dice, no heal,
    just the header / inline-desc fields. v2.43.11 server-side fallback
    populates ``feature_desc`` from the curated table.
    """
    pip = roster["Pip Quickfingers"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": pip["id"],
            "feature_key": "cunning-action",
            "option_key": "dash",
            "label": "Cunning Action",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("feature_used")
    d = msg["data"]

    _assert_keys(d, {
        # Header
        "character_id", "character_name", "user_color",
        # Body row
        "feature_name", "feature_desc",
        # Header chip + counter
        "source", "remaining", "max",
        # Over-budget gating
        "over_budget",
    }, "/use_feature (simple) broadcast")

    assert "Cunning Action" in d["feature_name"]
    assert "Dash" in d["feature_name"]
    # v2.43.11: desc populated from server-side fallback table.
    assert d["feature_desc"], "expected feature_desc to be auto-populated"
    assert d["source"] == "class-feature"


# ─────────────────────────────────────────────────────────────────────
# /use_second_wind  — feature_used (with dice + heal pill)
# ─────────────────────────────────────────────────────────────────────


async def test_second_wind_broadcast_carries_dice_and_heal_fields(
    gm_client, gm_ws, garrik_rested,
):
    """Second Wind — the most field-rich feature_used broadcast. Has
    both dice fields (for the dice toast) AND heal fields (for the
    feature-used card's heal pill). v2.43.12 also brings back the
    rolled-expression info in ``feature_desc``.
    """
    garrik = garrik_rested
    # Drop Garrik's HP so the heal actually applies.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-fields",
        json={"hp": {"current": 20}},
    )
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_second_wind",
        json={"character_id": garrik["id"], "override": True},
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("feature_used")
    d = msg["data"]

    _assert_keys(d, {
        # Header
        "character_id", "character_name", "user_color",
        "source",
        # Body row
        "feature_name", "feature_desc",
        # Counter
        "remaining", "max",
        # v2.35.0 dice toast fields (for the separate dice popup)
        "dice_expression", "dice_total", "dice_breakdown", "dice_note",
        # v2.43.0 heal pill fields (for the feature-card pill row)
        "heal_amount", "heal_target_name",
        "heal_hp_before", "heal_hp_after",
    }, "/use_second_wind broadcast")

    assert d["source"] == "second-wind"
    assert "Second Wind" in d["feature_name"]
    # v2.43.12: feature_desc carries the rolled expression + total.
    assert "rolled" in d["feature_desc"].lower(), (
        f"expected v2.43.12 feature_desc to include the rolled-dice info, got: {d['feature_desc']!r}"
    )
    assert d["dice_expression"] == "1d10+5"  # Lv 5 fighter
    assert isinstance(d["dice_total"], int)
    # Heal pill: amount > 0 since Garrik was at 20/49 HP.
    assert d["heal_amount"] > 0
    assert d["heal_target_name"] == garrik["name"]
    assert d["heal_hp_after"] > d["heal_hp_before"]


# ─────────────────────────────────────────────────────────────────────
# /use_lay_on_hands  — feature_used (with heal pill, no dice)
# ─────────────────────────────────────────────────────────────────────


async def test_lay_on_hands_broadcast_carries_heal_fields(
    gm_client, gm_ws, roster, caelan_rested,
):
    """Lay on Hands — heal pill fields without dice fields (the
    paladin chooses the amount; no dice are rolled).
    """
    caelan = caelan_rested
    pip = roster["Pip Quickfingers"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"hp": {"current": 5}},
    )
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_lay_on_hands",
        json={
            "character_id": caelan["id"],
            "target_character_id": pip["id"],
            "amount": 5,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("feature_used")
    d = msg["data"]

    _assert_keys(d, {
        "character_id", "character_name", "user_color",
        "feature_name", "feature_desc",
        "source",
        # Heal pill fields
        "heal_amount", "heal_target_name",
        "heal_hp_before", "heal_hp_after",
    }, "/use_lay_on_hands broadcast")

    assert d["source"] == "lay-on-hands"
    assert d["heal_amount"] > 0
    assert d["heal_target_name"] == pip["name"]
