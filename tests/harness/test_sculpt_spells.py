"""v2.669.0 — Evocation Wizard: Sculpt Spells (full-feature-automation Phase 8).

RAW PHB p.117: "When you cast an evocation spell that affects other creatures
that you can see, you can choose a number of them equal to 1 + the spell's
level. The chosen creatures automatically succeed on their saving throws
against the spell, and they take no damage if they would normally take half
damage on a successful save."

Mechanically identical to the Careful Spell metamagic, so `use_sculpt_spells`
now (was announce-only) installs a `sculpt-spells-active` buff carrying
`effects.protected_combatant_ids` that the existing AoE-save read substrate
honors (`_caster_has_careful_pending_buff` extended to match the key +
`_combatant_is_careful_protected`), with a `protection_label` so the auto-pass
card names "Sculpt Spells" (not "Careful Spell").

Thalindra (CAMPAIGN_ID wizard with Fireball) is PATCHed to School of Evocation.

Tests:
  - Arming with protected ids installs the `sculpt-spells-active` buff payload.
  - End-to-end: a protected NPC auto-succeeds its Fireball save (1d20+99) +
    the Sculpt-labeled auto-pass card fires.
  - Wrong subclass (non-Evocation wizard) → 409.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch(gm_client, char_id, fields):
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={**fields, "class_slug": "wizard"},
    )
    assert r.status_code == 200, r.text


async def _sheet(gm_client, char_id):
    return (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json"
    )).json().get("sheet") or {}


def _fireball_index(sheet):
    spells = sheet.get("spells") or []
    for i, s in enumerate(spells):
        if (s.get("_slug") or "").lower() == "fireball" \
                or (s.get("name") or "").strip().lower() == "fireball":
            return i
    return None


@pytest_asyncio.fixture
async def thalindra_evocation(gm_client, roster):
    """PATCH Thalindra to School of Evocation (restore-safe)."""
    thal = roster["Thalindra Moonwhisper"]
    orig = await _sheet(gm_client, thal["id"])
    orig_sub = orig.get("subclass") or "School of Evocation"
    await _patch(gm_client, thal["id"], {"subclass": "School of Evocation"})
    try:
        yield thal
    finally:
        await _patch(gm_client, thal["id"], {"subclass": orig_sub})


async def _seed_with_bandit(gm_client, thal, bandit_tmpl_id, bandit_name,
                            bandit_cid):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_sc_t_{thal['id']}", "char_id": thal["id"],
             "name": thal["name"], "initiative": 12,
             "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": bandit_cid, "char_id": None,
             "token_template_id": bandit_tmpl_id, "name": bandit_name,
             "initiative": 7, "hp_current": 100, "hp_max": 100, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )


async def test_sculpt_arms_buff_payload(gm_client, thalindra_evocation):
    """Arming Sculpt with protected ids installs the `sculpt-spells-active`
    buff carrying the protected list + the Sculpt label."""
    thal = thalindra_evocation
    bandit_cid = "tok_sc_payload_bandit"
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    await _seed_with_bandit(gm_client, thal, bandit["id"], bandit["name"],
                            bandit_cid)
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": thal["id"], "key": "sculpt-spells-active"},
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_sculpt_spells",
        json={"character_id": thal["id"], "spell_level": 3,
              "protected_combatant_ids": [bandit_cid]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["buff_installed"] is True
    assert data["protected_combatant_ids"] == [bandit_cid]
    buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/buffs"
    )).json().get("buffs", [])
    sb = next((b for b in buffs if b.get("key") == "sculpt-spells-active"), None)
    assert sb is not None, [b.get("key") for b in buffs]
    eff = sb.get("effects") or {}
    assert eff.get("protected_combatant_ids") == [bandit_cid]
    assert eff.get("protection_label") == "Sculpt Spells"
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": thal["id"], "key": "sculpt-spells-active"},
    )


async def test_sculpt_protects_npc_from_fireball(
    gm_client, gm_ws, thalindra_evocation,
):
    """End-to-end: a Sculpt-protected NPC auto-succeeds its Fireball save
    (the read substrate forces 1d20+99) and the auto-pass card is labeled
    'Sculpt Spells' (not 'Careful Spell')."""
    thal = thalindra_evocation
    fb_idx = _fireball_index(await _sheet(gm_client, thal["id"]))
    assert fb_idx is not None, "Thalindra should have Fireball prepared"
    bandit_cid = "tok_sc_e2e_bandit"
    templates = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(
        (t for t in templates if "bandit" in (t.get("name") or "").lower()),
        templates[0],
    )
    await _seed_with_bandit(gm_client, thal, bandit["id"], bandit["name"],
                            bandit_cid)
    arm = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_sculpt_spells",
        json={"character_id": thal["id"], "spell_level": 3,
              "protected_combatant_ids": [bandit_cid]},
    )
    assert arm.status_code == 200, arm.text
    assert arm.json()["buff_installed"] is True

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={"character_id": thal["id"], "spell_index": fb_idx,
              "slot_level": 3, "class_slug": "wizard",
              "target_combatant_id": bandit_cid,
              "target_name": bandit["name"], "override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("auto_save_target_kind") == "npc", data
    assert data.get("auto_save_passed") is True, (
        f"Sculpt-protected NPC should auto-pass; got {data.get('auto_save_passed')}"
    )

    await asyncio.sleep(0.2)
    save_rolls = [
        m for m in gm_ws.buffered("roll")
        if (m.get("data") or {}).get("char_name") == bandit["name"]
    ]
    assert save_rolls, "expected a save roll for the protected bandit"
    assert "1d20+99" in save_rolls[-1]["data"]["expression"]

    # The auto-pass card names Sculpt Spells (the protection_label wire).
    sculpt_cards = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "sculpt-spells"
        and "auto-pass" in ((m.get("data") or {}).get("feature_name") or "")
    ]
    assert sculpt_cards, (
        "expected a 'Sculpt Spells (auto-pass)' card; got sources "
        f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
    )


async def test_sculpt_wrong_class(gm_client, roster):
    """A non-Evocation-wizard caster → 409. (Thalindra is an Evocation
    wizard by default, so this uses Pip — a Rogue — to exercise the gate.)"""
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_sculpt_spells",
        json={"character_id": pip["id"], "spell_level": 3,
              "protected_combatant_ids": ["tok_x"]},
    )
    assert r.status_code == 409, r.text
    assert r.json().get("error") == "wrong_subclass_or_level"
