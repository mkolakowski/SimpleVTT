"""Spiritual Weapon — Cleric L2, the first summon retrofit.

v2.99.438 — Phase 7.1 of docs/plans/movement-and-summons.md. Builds on
the v2.99.437 `_summon_companion` primitive: `/use_spiritual_weapon`
stands up the floating spectral-weapon combatant (the `spiritual-weapon`
registry entry) and, when a `target_combatant_id` is supplied, makes the
melee spell attack server-side (1d20 + prof + spellcasting mod vs AC) and
applies 1d8 + mod force damage on a hit.

Caster fixture: Brother Tavik Stonebrow (demo Cleric Lv 6, WIS 16 /
prof +3 → +6 to hit, knows Spiritual Weapon).

Tests:
  - summon-only: no target → the weapon combatant appears (is_summon,
    1 HP) with a token; `attacked` False. Dismissed after.
  - summon + attack: loop a fresh weapon each cast until Tavik hits a
    bandit → `damage_applied > 0`, `damage_type == "force"`.
  - 409 spell_not_known: Krieger (Barbarian).
"""
from .conftest import CAMPAIGN_ID


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": False},
    )


async def _bandit_template(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next(
        (t for t in templates if "bandit" in t["name"].lower()), templates[0]
    )


def _pc_cb(c):
    return {
        "id": f"tok_test_{c['id']}", "char_id": c["id"], "name": c["name"],
        "initiative": 10, "hp_current": 40, "hp_max": 40, "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _dismiss(gm_client, combatant_id):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/dismiss_companion",
        json={"combatant_id": combatant_id},
    )


async def _clear_concentration(gm_client, char_id):
    # v2.113.0 — Spiritual Weapon now establishes concentration on the
    # caster; clear it in teardown so the row + buff don't leak.
    await gm_client.delete(
        f"/api/campaign/{CAMPAIGN_ID}/concentration/{char_id}",
    )


async def test_spiritual_weapon_summon_only(gm_client, gm_ws, roster):
    """Tavik conjures the weapon with no target → a `spiritual-weapon`
    summon combatant + token appear; `attacked` is False."""
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_battle(gm_client, [_pc_cb(tavik)])

    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spiritual_weapon",
        json={"character_id": tavik["id"], "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    cb = body["combatant"]
    try:
        assert body["feature"] == "spiritual-weapon"
        assert body["attacked"] is False
        assert cb["is_summon"] is True
        assert cb["companion_key"] == "spiritual-weapon"
        assert cb["name"] == "Spiritual Weapon"
        assert cb["hp_max"] == 1
        assert cb["summoned_by"] == tavik["id"]
        assert body["token_id"] is not None

        ta = await gm_ws.wait_for("token_add", timeout=2.0)
        assert ta["data"]["id"] == body["token_id"]
        # v2.113.0 — casting now binds the weapon to concentration.
        assert cb["concentration_bound"] is True
    finally:
        await _dismiss(gm_client, cb["id"])
        await _clear_concentration(gm_client, tavik["id"])


async def test_spiritual_weapon_concentration_lifecycle(gm_client, gm_ws, roster):
    """v2.113.0 — the weapon joins initiative at the caster's value and
    is bound to concentration: dropping the caster's concentration buff
    (the × on the chip) dismisses the weapon's token + combatant."""
    tavik = roster["Brother Tavik Stonebrow"]
    cb = _pc_cb(tavik)
    cb["initiative"] = 15  # distinctive value to assert "after the caster"
    await _seed_battle(gm_client, [cb])

    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spiritual_weapon",
        json={"character_id": tavik["id"], "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    weapon = r.json()["combatant"]
    token_id = r.json()["token_id"]
    try:
        assert weapon["initiative"] == 15, "weapon acts at the caster's initiative"
        assert weapon["concentration_bound"] is True
        # The caster shows concentrating.
        cu = await gm_ws.wait_for("concentration_update", timeout=2.0)
        assert cu["data"]["character_id"] == tavik["id"]
        assert cu["data"]["spell_name"] == "Spiritual Weapon"
        assert cu["data"]["ended"] is False
        # The weapon is in the persisted battle.
        got = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
        combs = ((got.json() or {}).get("battle") or {}).get("combatants") or []
        assert any(c.get("companion_key") == "spiritual-weapon" for c in combs)

        # Drop the caster's concentration buff → the cascade dismisses it.
        gm_ws.mark()
        er = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": tavik["id"],
                  "key": "concentration-spiritual-weapon"},
        )
        assert er.status_code == 200, er.text
        td = await gm_ws.wait_for("token_delete", timeout=2.0)
        assert td["data"]["id"] == token_id
        got2 = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
        combs2 = ((got2.json() or {}).get("battle") or {}).get("combatants") or []
        assert not any(c.get("companion_key") == "spiritual-weapon" for c in combs2), (
            "the weapon must be dismissed when the caster's concentration drops"
        )
    finally:
        await _dismiss(gm_client, weapon["id"])
        await _clear_concentration(gm_client, tavik["id"])


async def test_spiritual_weapon_attacks_target(gm_client, roster):
    """Tavik conjures + strikes a bandit; loop a fresh weapon each cast
    until a hit lands → force damage applied. Each cast's weapon is
    dismissed so the board doesn't accumulate."""
    tavik = roster["Brother Tavik Stonebrow"]
    bandit_tmpl = await _bandit_template(gm_client)
    bandit_cb = "tok_test_sw_bandit"

    hit_seen = False
    for _ in range(30):
        await _seed_battle(gm_client, [
            _pc_cb(tavik),
            {"id": bandit_cb, "char_id": None,
             "token_template_id": bandit_tmpl["id"],
             "name": bandit_tmpl["name"], "initiative": 7,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_spiritual_weapon",
            json={"character_id": tavik["id"], "x": 700.0, "y": 700.0,
                  "target_combatant_id": bandit_cb},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["attacked"] is True
        assert body["target_ac"] > 0
        weapon_id = body["combatant"]["id"]
        try:
            if body["hit"]:
                assert body["damage_type"] == "force"
                assert body["damage_rolled"] > 0
                assert body["damage_applied"] > 0
                hit_seen = True
                break
        finally:
            await _dismiss(gm_client, weapon_id)
    await _clear_concentration(gm_client, tavik["id"])
    assert hit_seen, "no hit in 30 casts — flaky env?"


async def test_spiritual_weapon_replaces_prior_concentration_and_survives(
    gm_client, roster,
):
    """v2.113.1 — casting Spiritual Weapon while already concentrating
    drops the OLD concentration (RAW one-at-a-time) but the NEW weapon
    survives. Regression for the v2.113.0 ordering bug where the
    replace-concentration cascade fired AFTER the weapon spawned and
    dismissed it (it's concentration_bound + summoned_by self)."""
    tavik = roster["Brother Tavik Stonebrow"]
    cb = _pc_cb(tavik)
    cb["initiative"] = 15
    # Seed Tavik already concentrating on another spell.
    cb["buffs"] = [{
        "key": "concentration-spirit-guardians",
        "name": "Concentrating: Spirit Guardians",
        "concentration": True,
        "source_char_id": tavik["id"],
        "duration_rounds": 10,
    }]
    await _seed_battle(gm_client, [cb])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spiritual_weapon",
        json={"character_id": tavik["id"], "x": 700.0, "y": 700.0},
    )
    assert r.status_code == 200, r.text
    weapon = r.json()["combatant"]
    try:
        got = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
        combs = ((got.json() or {}).get("battle") or {}).get("combatants") or []
        # The new weapon must NOT have been swept up by the swap cascade.
        assert any(c.get("companion_key") == "spiritual-weapon" for c in combs), (
            "the new Spiritual Weapon must survive replacing prior concentration"
        )
        # The old concentration was replaced by Spiritual Weapon's.
        tavik_cb = next(c for c in combs if c.get("char_id") == tavik["id"])
        keys = {(b or {}).get("key") for b in (tavik_cb.get("buffs") or [])}
        assert "concentration-spirit-guardians" not in keys, "old concentration kept"
        assert "concentration-spiritual-weapon" in keys
    finally:
        await _dismiss(gm_client, weapon["id"])
        await _clear_concentration(gm_client, tavik["id"])


async def test_spiritual_weapon_spell_not_known(gm_client, roster):
    """Krieger (Barbarian) → 409 spell_not_known."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spiritual_weapon",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "spell_not_known"
