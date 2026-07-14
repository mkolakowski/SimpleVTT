"""v2.1010.0 — Overchannel (Evocation Wizard Lv 14+, PHB p.117).

"When you cast a wizard spell of 1st through 5th level that deals
damage, you can deal maximum damage with that spell. The first time you
do so, you suffer no adverse effect. If you use this feature again
before you finish a long rest, you take 2d12 necrotic damage for each
level of the spell ... increasing by 1d12 [per level] each additional
time. This damage ignores resistance and immunity."

Evocation is the SRD wizard subclass, so Overchannel is SRD-valid.
Thalindra Moonwhisper (Wizard School of Evocation Lv 7) is the demo
fixture, PATCH'd to Lv 14 for the happy paths (mirrors how
test_evocation_school.py PATCHes her to Lv 10 for Empowered Evocation).

Tests:
  - /use_overchannel arms the buff at Lv 14 (use #1, first-free).
  - Casting a damaging spell with the buff maxes its damage
    (Fireball 8d6 → 48) + drops the buff + broadcasts ⚡ Overchannel.
  - First use since long rest → no self-damage.
  - Second use → escalating necrotic self-damage applied to the caster.
  - The armed buff is one-shot: a second cast without re-arming is NOT
    maxed.
  - Level gate: Thalindra at Lv 7 → 409.
  - Error paths: missing character_id → 400; unknown char → 404; wrong
    class (Krieger the Barbarian) → 409.
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


def _pc(cid, c, *, hp_max=200):
    # Generous HP so escalating self-damage doesn't drop Thalindra to 0
    # mid-suite (we assert HP delta, not death).
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


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
async def auto_apply_on(gm_client):
    await _set_auto_apply(gm_client, True)
    yield
    await _set_auto_apply(gm_client, False)


async def _fireball_index(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    spells = (r.json().get("sheet") or {}).get("spells") or []
    for i, s in enumerate(spells):
        if (s.get("_slug") or "").lower() == "fireball":
            return i
    raise AssertionError("Thalindra has no Fireball in her spell list")


async def _seed_thal_vs_bandit(gm_client, thal):
    """Seed Thalindra + a bandit NPC so Fireball's save path applies
    server-side damage. Returns the bandit combatant id."""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(
        (t for t in templates if "bandit" in t["name"].lower()),
        templates[0],
    )
    bandit_id = f"tok_oc_bandit_{thal['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _pc(f"tok_oc_thal_{thal['id']}", thal),
            {"id": bandit_id, "char_id": None,
             "token_template_id": bandit_tmpl["id"],
             "name": bandit_tmpl["name"], "initiative": 5,
             "hp_current": 400, "hp_max": 400, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    return bandit_id


async def _cast_fireball(gm_client, thal, fb_index, bandit_id):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": fb_index,
            "target_combatant_id": bandit_id,
            "override": True,
            "override_range": True,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_overchannel_maxes_fireball_and_is_free_first_use(
    gm_client, gm_ws, roster, auto_apply_on,
):
    """Thalindra PATCH'd to Lv 14 arms Overchannel (use #1) then casts
    Fireball: the auto-save damage is maxed (8d6 → 48), the ⚡ Overchannel
    card fires, the payload reports maxed + use #1, and the first use
    since long rest costs no self-damage."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(gm_client, thal["id"], {"level": 14},
                       class_slug="wizard")
    try:
        # Fresh long rest so the use counter starts at 0.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
            json={"type": "long"},
        )
        bandit_id = await _seed_thal_vs_bandit(gm_client, thal)
        fb_index = await _fireball_index(gm_client, thal["id"])
        arm = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_overchannel",
            json={"character_id": thal["id"]},
        )
        assert arm.status_code == 200, arm.text
        assert arm.json()["use_number"] == 1
        assert arm.json()["first_free"] is True
        gm_ws.mark()
        data = await _cast_fireball(gm_client, thal, fb_index, bandit_id)
        # Fireball base is 8d6 → maxed 48. The rolled (pre-halving) value
        # is deterministic at max with Overchannel.
        assert data["auto_save_damage_rolled"] == 48, (
            f"expected maxed 8d6=48; got {data.get('auto_save_damage_rolled')}"
        )
        oc = data.get("overchannel") or {}
        assert oc.get("maxed") is True
        assert oc.get("use_number") == 1
        assert oc.get("self_damage_applied", 0) == 0  # first use is free
        await asyncio.sleep(0.3)
        cards = [
            m for m in gm_ws.buffered("feature_used")
            if (m.get("data") or {}).get("source") == "overchannel"
            and "maximum damage" in (m.get("data") or {}).get("feature_name", "")
        ]
        assert cards, "expected a ⚡ Overchannel maximum-damage feature_used card"
    finally:
        await _patch_sheet(gm_client, thal["id"], {"level": 7},
                           class_slug="wizard")


async def test_overchannel_second_use_applies_self_damage(
    gm_client, roster, auto_apply_on,
):
    """The 2nd overchannel since a long rest costs the caster
    `use_number × spell_level` d12 necrotic. Thalindra's HP drops."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(gm_client, thal["id"], {"level": 14},
                       class_slug="wizard")
    try:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
            json={"type": "long"},
        )
        bandit_id = await _seed_thal_vs_bandit(gm_client, thal)
        fb_index = await _fireball_index(gm_client, thal["id"])
        # Use #1 (free).
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_overchannel",
            json={"character_id": thal["id"]},
        )
        await _cast_fireball(gm_client, thal, fb_index, bandit_id)
        # HP before the 2nd (costly) overchannel.
        r = await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/sheet-json",
        )
        hp_before = int(((r.json().get("sheet") or {}).get("hp") or {}).get("current") or 0)
        # Use #2 — 2 d12 per spell level = 6d12 for a 3rd-level Fireball.
        arm2 = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_overchannel",
            json={"character_id": thal["id"]},
        )
        assert arm2.json()["use_number"] == 2
        assert arm2.json()["first_free"] is False
        data = await _cast_fireball(gm_client, thal, fb_index, bandit_id)
        oc = data.get("overchannel") or {}
        assert oc.get("use_number") == 2
        assert oc.get("self_damage_expr") == "6d12"
        assert oc.get("self_damage_applied", 0) > 0
        r2 = await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/sheet-json",
        )
        hp_after = int(((r2.json().get("sheet") or {}).get("hp") or {}).get("current") or 0)
        assert hp_after < hp_before, (
            f"Overchannel self-damage should lower HP; {hp_before} → {hp_after}"
        )
    finally:
        await _patch_sheet(gm_client, thal["id"], {"level": 7},
                           class_slug="wizard")


async def test_overchannel_buff_is_one_shot(
    gm_client, roster, auto_apply_on,
):
    """The armed buff is consumed by one cast — a second cast without
    re-arming rolls normal (non-maxed) damage, so no overchannel payload."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(gm_client, thal["id"], {"level": 14},
                       class_slug="wizard")
    try:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
            json={"type": "long"},
        )
        bandit_id = await _seed_thal_vs_bandit(gm_client, thal)
        fb_index = await _fireball_index(gm_client, thal["id"])
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_overchannel",
            json={"character_id": thal["id"]},
        )
        first = await _cast_fireball(gm_client, thal, fb_index, bandit_id)
        assert (first.get("overchannel") or {}).get("maxed") is True
        # Second cast — buff already consumed → no overchannel payload.
        second = await _cast_fireball(gm_client, thal, fb_index, bandit_id)
        assert "overchannel" not in second, (
            "the armed buff should be one-shot; a second cast must not max"
        )
    finally:
        await _patch_sheet(gm_client, thal["id"], {"level": 7},
                           class_slug="wizard")


async def test_overchannel_level_gate(gm_client, roster):
    """Thalindra at Lv 7 → 409 (Overchannel needs Lv 14)."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_overchannel",
        json={"character_id": thal["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json().get("error") == "wrong_subclass_or_level"


async def test_overchannel_missing_character_id(gm_client):
    """No character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_overchannel",
        json={},
    )
    assert r.status_code == 400, r.text


async def test_overchannel_unknown_character(gm_client):
    """Unknown character id → 404."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_overchannel",
        json={"character_id": 99999999},
    )
    assert r.status_code == 404, r.text


async def test_overchannel_wrong_class(gm_client, roster):
    """Krieger (Barbarian) → 409 wrong_subclass_or_level."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_overchannel",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json().get("error") == "wrong_subclass_or_level"
