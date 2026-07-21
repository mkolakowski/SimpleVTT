"""Holy Aura — L8 abjuration, Cleric.
Phase 2 #41 of ``docs/plans/cast-and-broadcast-tail.md``.

v2.508.0 — RAW PHB p.243: "Creatures of your choice in [a 30-ft]
radius ... have advantage on all saving throws, and other creatures
have disadvantage on attack rolls against them ... when a fiend or an
undead hits an affected creature with a melee attack ... The attacker
must succeed on a Constitution saving throw or be blinded."
Concentration, up to 1 minute.

The first tail spell to fan the buff out across an arbitrary number of
chosen creatures. Two effects ride existing hub-state substrates (no
sheet mirror): ``save_advantage: True`` — advantage on EVERY save via
``_buff_grants_save_advantage`` — and ``attackers_have_disadvantage:
True`` — the v2.500.0 Blur read-site ``_target_blur_imposes_disadvantage``.
Concentration anchors on the caster's own buff; companion buffs carry
``_dependent_on_caster_concentration`` so the aura drops in lock-step.
The 5-ft dim-light radius + fiend/undead blinding flash are GM-narrated.

Tests:
  - Install → caster's buff carries save_advantage True +
    attackers_have_disadvantage True, concentration True.
  - Multi-target fan-out → a companion also gets the buff, but with
    concentration False (only the caster anchors concentration).
  - Save advantage: a non-STR save (Fireball DEX save) vs a warded
    target → roll_request base_expression == "2d20kh1".
  - Attacker disadvantage: an attack against a warded creature →
    roll_state has "disadvantage".
  - Non-caster (Barbarian) → 409; missing character_id → 400.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _spell_index(gm_client, char_id, name):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    sheet = (r.json() or {}).get("sheet") or {}
    for i, sp in enumerate(sheet.get("spells") or []):
        nm = sp.get("name") if isinstance(sp, dict) else sp
        if str(nm).strip().lower() == name.strip().lower():
            return i
    return -1


def _tok(char, init=10, hp=60):
    return {
        "id": f"tok_holy_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _set_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


async def _get_buffs(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert r.status_code == 200, r.text
    return r.json().get("buffs") or []


def _find_cleric(roster):
    for name in ("Brother Tavik Stonebrow",):
        if name in roster:
            return roster[name]
    return None


@pytest_asyncio.fixture
async def thalindra(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    return thal


async def test_cast_holy_aura_installs_markers(gm_client, roster):
    """Cast → caster's buff carries save_advantage True +
    attackers_have_disadvantage True, concentration True."""
    caster = _find_cleric(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric in the demo roster")
    await _set_battle(gm_client, [_tok(caster)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_holy_aura",
        json={"character_id": caster["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "holy-aura"
    assert body["buffs_installed"] == 1
    assert body["duration_rounds"] == 10

    buffs = await _get_buffs(gm_client, caster["id"])
    ha = next((b for b in buffs if b.get("key") == "holy-aura"), None)
    assert ha is not None, f"holy-aura buff missing: {buffs}"
    eff = ha.get("effects") or {}
    assert eff.get("save_advantage") is True
    assert eff.get("attackers_have_disadvantage") is True
    assert ha.get("concentration") is True
    assert int(ha.get("duration_rounds") or 0) == 10


async def test_holy_aura_fans_out_to_companions(gm_client, roster):
    """A chosen companion also gets the aura, but with concentration
    False — only the caster's own buff anchors concentration."""
    caster = _find_cleric(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric in the demo roster")
    krieger = roster["Krieger Stonefist"]
    try:
        await _set_battle(gm_client, [_tok(caster), _tok(krieger)])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_holy_aura",
            json={"character_id": caster["id"],
                  "target_character_ids": [krieger["id"]]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Caster auto-included + the chosen companion → 2 buffs.
        assert body["buffs_installed"] == 2, body
        assert set(body["targets"]) == {caster["id"], krieger["id"]}

        # Caster's buff anchors concentration.
        caster_ha = next(
            (b for b in await _get_buffs(gm_client, caster["id"])
             if b.get("key") == "holy-aura"), None)
        assert caster_ha is not None
        assert caster_ha.get("concentration") is True

        # Companion's buff is concentration-dependent, NOT an anchor.
        comp_ha = next(
            (b for b in await _get_buffs(gm_client, krieger["id"])
             if b.get("key") == "holy-aura"), None)
        assert comp_ha is not None, "companion missing holy-aura buff"
        assert comp_ha.get("concentration") is False
        assert comp_ha.get("_dependent_on_caster_concentration") is True
        eff = comp_ha.get("effects") or {}
        assert eff.get("save_advantage") is True
        assert eff.get("attackers_have_disadvantage") is True
    finally:
        for cid in (caster["id"], krieger["id"]):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": cid, "key": "holy-aura"},
            )


async def test_holy_aura_grants_advantage_on_non_str_save(
    gm_client, gm_ws, thalindra, roster,
):
    """Holy Aura grants advantage on ALL saves — a DEX save (Fireball)
    on a warded creature rolls 2d20kh1."""
    caster = _find_cleric(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric in the demo roster")
    thal = thalindra
    krieger = roster["Krieger Stonefist"]
    fireball = await _spell_index(gm_client, thal["id"], "Fireball")
    if fireball < 0:
        import pytest
        pytest.skip("Thalindra must know Fireball")
    try:
        await _set_battle(gm_client, [
            _tok(caster, init=25), _tok(thal, init=20), _tok(krieger),
        ])
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_holy_aura",
            json={"character_id": caster["id"],
                  "target_character_ids": [krieger["id"]]},
        )
        assert r.status_code == 200, r.text
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thal["id"],
                "spell_index": fireball,
                "slot_level": 3,
                "class_slug": "wizard",
                "target_combatant_id": f"tok_holy_{krieger['id']}",
                "target_character_id": krieger["id"],
                "target_name": krieger["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert resp.status_code == 200, resp.text
        import asyncio as _asy
        await _asy.sleep(0.2)
        rrs = gm_ws.buffered("roll_request")
        assert rrs, "expected a roll_request broadcast for Krieger's DEX save"
        assert (rrs[-1].get("data") or {}).get("base_expression") == "2d20kh1", (
            f"Holy Aura should grant advantage on the DEX save; "
            f"got {rrs[-1].get('data')}"
        )
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": krieger["id"], "key": "holy-aura"},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": caster["id"], "key": "holy-aura"},
        )


async def test_holy_aura_imposes_disadvantage_on_attackers(gm_client, roster, bright_map):
    """An attack against a warded creature rolls at disadvantage (Pip is
    a clean attacker with no advantage sources to cancel it).

    ``bright_map`` neutralizes inherited ambient darkness so the roll-state
    reflects Holy Aura, not a can't-see cancellation (B16)."""
    caster = _find_cleric(roster)
    if caster is None:
        import pytest
        pytest.skip("no Cleric in the demo roster")
    krieger = roster["Krieger Stonefist"]
    pip = roster["Pip Quickfingers"]
    krieger_tok = f"tok_holy_{krieger['id']}"
    try:
        await _set_battle(gm_client, [
            _tok(caster, init=25), _tok(pip, init=20),
            {"id": krieger_tok, "char_id": krieger["id"],
             "name": krieger["name"], "initiative": 10,
             "hp_current": 60, "hp_max": 60, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ])
        # Ward Krieger; Pip attacks Krieger → disadvantage.
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_holy_aura",
            json={"character_id": caster["id"],
                  "target_character_ids": [krieger["id"]]},
        )
        assert r.status_code == 200, r.text
        a = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": pip["id"],
                "attack_index": 0,
                "target_combatant_id": krieger_tok,
                "override": True,
            },
        )
        assert a.status_code == 200, a.text
        state = a.json().get("roll_state_applied") or ""
        assert "disadvantage" in state, (
            f"expected a disadvantage roll-state from Holy Aura; got {state!r}"
        )
    finally:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": krieger["id"], "key": "holy-aura"},
        )
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": caster["id"], "key": "holy-aura"},
        )


async def test_cast_holy_aura_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_holy_aura",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "holy aura" in r.json()["expected"].lower()


async def test_cast_holy_aura_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_holy_aura",
        json={},
    )
    assert r.status_code == 400, r.text
