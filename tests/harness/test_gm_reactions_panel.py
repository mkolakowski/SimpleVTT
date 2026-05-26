"""v2.68.0 — GM Reactions Panel.

Surfaces every combatant's available reactions to the GM regardless
of trigger event. See ``docs/plans/reactions-automation.md`` for the
broader plan; the GM panel is the manual-spend bypass for narrative
reactions and reactions whose triggers aren't yet automated.

Coverage:
  - GET /available_reactions returns the catalog per combatant + a
    `reaction_used` flag mirroring the chip state.
  - PC catalog includes Uncanny Dodge (Rogue Lv 5+) for Pip.
  - NPC catalog walks the projected monster sheet's `actions` for
    `category == "reaction"` entries.
  - POST /spend_reaction_manual flips the chip + broadcasts a
    feature_used card. PCs use char_id-keyed flip; NPCs use the
    v2.67.3 combatant_id-keyed flip.
  - Auth: non-GM players can't read the catalog.
  - Already-spent reaction → 409.
  - Unknown reaction_key → 400.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _make_combatant(name, char_id, init=10, hp=40):
    return {
        "id": f"tok_gmrxn_{char_id}",
        "char_id": char_id,
        "name": name,
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": [],
        "economy": {
            "action": False, "bonus": False,
            "reaction": False, "movement": 0,
        },
    }


async def _seed_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants,
            "turn_index": 0,
            "round": 1,
            "active": True,
        },
    )


async def test_available_reactions_lists_pc_class_features(
    gm_client, roster,
):
    """Pip is Rogue Lv 7 (v2.51.6+); Uncanny Dodge appears in his
    reaction catalog. Catalog includes `reaction_used: False` since
    his chip is freshly seeded.
    """
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        _make_combatant(pip["name"], pip["id"], init=10),
    ])
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/available_reactions",
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    pip_entry = next(
        (c for c in data["combatants"] if c["char_id"] == pip["id"]),
        None,
    )
    assert pip_entry, (
        f"expected Pip in catalog; got "
        f"{[c['name'] for c in data['combatants']]}"
    )
    keys = [r["key"] for r in pip_entry["reactions"]]
    assert "uncanny-dodge" in keys, (
        f"expected uncanny-dodge in Pip's catalog; got {keys}"
    )
    assert pip_entry["reaction_used"] is False


async def test_available_reactions_lists_npc_monster_reaction(
    gm_client,
):
    """Bandit Captain has a Parry reaction in its SRD stat block.
    Spawning one + adding to init → catalog surfaces the Parry
    option keyed `monster-parry`.
    """
    tmpl_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/templates",
        json={
            "name": "Bandit Captain (Reactions panel test)",
            "template": "dnd5e",
            "tags": ["npc", "harness"],
            "sheet": {"monster_slug": "bandit-captain"},
        },
    )
    assert tmpl_resp.status_code == 200, tmpl_resp.text
    tmpl = tmpl_resp.json()
    tok_resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/tokens",
        json={
            "token_template_id": tmpl["id"],
            "label": "Bandit Captain",
            "x": 350.0, "y": 350.0,
            "color": "#822222", "size": 1,
        },
    )
    assert tok_resp.status_code == 200, tok_resp.text
    bc_tok = tok_resp.json()

    bc_cid = "tok_gmrxn_bc"
    await _seed_battle(gm_client, [
        {
            "id": bc_cid,
            "char_id": None,
            "source_token_id": bc_tok["id"],
            "token_template_id": tmpl["id"],
            "name": "Bandit Captain",
            "initiative": 9,
            "hp_current": 65, "hp_max": 65,
            "buffs": [],
            "economy": {
                "action": False, "bonus": False,
                "reaction": False, "movement": 0,
            },
        },
    ])

    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/available_reactions",
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    bc_entry = next(
        (c for c in data["combatants"] if c["combatant_id"] == bc_cid),
        None,
    )
    assert bc_entry, (
        f"expected Bandit Captain in catalog; got "
        f"{[c['name'] for c in data['combatants']]}"
    )
    keys = [r["key"] for r in bc_entry["reactions"]]
    assert any(k.startswith("monster-") for k in keys), (
        f"expected at least one monster-keyed reaction "
        f"(Parry, etc.); got {keys}"
    )


async def test_spend_reaction_manual_pc(gm_client, gm_ws, roster):
    """Spend Pip's Uncanny Dodge via the manual panel → reaction
    chip flips True (economy_update) + feature_used card fires.
    """
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        _make_combatant(pip["name"], pip["id"], init=10),
    ])
    await asyncio.sleep(0.1)
    gm_ws.mark()

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/spend_reaction_manual",
        json={
            "combatant_id": f"tok_gmrxn_{pip['id']}",
            "reaction_key": "uncanny-dodge",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["reaction_key"] == "uncanny-dodge"

    await asyncio.sleep(0.15)
    # economy_update broadcast flipped Pip's reaction.
    econ = [
        m for m in gm_ws.buffered("economy_update")
        if (m.get("data") or {}).get("character_id") == pip["id"]
        and (m.get("data") or {}).get("slot") == "reaction"
    ]
    assert econ, "expected economy_update flipping Pip's reaction"
    assert econ[-1]["data"]["used"] is True

    # feature_used card fired.
    fu = [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "manual-reaction"
        and (m.get("data") or {}).get("character_id") == pip["id"]
    ]
    assert fu, "expected feature_used card with source=manual-reaction"


async def test_spend_reaction_manual_already_used(
    gm_client, roster,
):
    """409 when the reaction slot is already used."""
    pip = roster["Pip Quickfingers"]
    pip_cb = _make_combatant(pip["name"], pip["id"], init=10)
    pip_cb["economy"]["reaction"] = True
    await _seed_battle(gm_client, [pip_cb])

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/spend_reaction_manual",
        json={
            "combatant_id": f"tok_gmrxn_{pip['id']}",
            "reaction_key": "uncanny-dodge",
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json().get("error") == "reaction_already_used"


async def test_spend_reaction_manual_unknown_key(
    gm_client, roster,
):
    """400 when the reaction_key isn't in the combatant's catalog."""
    pip = roster["Pip Quickfingers"]
    await _seed_battle(gm_client, [
        _make_combatant(pip["name"], pip["id"], init=10),
    ])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/spend_reaction_manual",
        json={
            "combatant_id": f"tok_gmrxn_{pip['id']}",
            "reaction_key": "not-a-real-reaction",
        },
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "unknown_reaction_key"


async def test_available_reactions_gm_only(alice_client, roster):
    """Non-GM players can't read the catalog (it leaks NPC info)."""
    resp = await alice_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/available_reactions",
    )
    assert resp.status_code == 403, resp.text


async def test_spend_reaction_manual_gm_only(alice_client, roster):
    """Non-GM players can't spend reactions on other combatants."""
    pip = roster["Pip Quickfingers"]
    resp = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/spend_reaction_manual",
        json={
            "combatant_id": f"tok_gmrxn_{pip['id']}",
            "reaction_key": "uncanny-dodge",
        },
    )
    assert resp.status_code == 403, resp.text


async def test_available_reactions_lists_monk_deflect_missiles(
    gm_client, roster,
):
    """v2.68.6 — Kael is Monk Lv 7. His catalog now surfaces
    Deflect Missiles (added in Phase 2b continuation alongside
    Battle Master maneuvers for Fighter Lv 3+ Battle Masters).
    """
    kael = roster["Kael Brightleaf"]
    await _seed_battle(gm_client, [
        _make_combatant(kael["name"], kael["id"], init=10),
    ])
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/available_reactions",
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    kael_entry = next(
        (c for c in data["combatants"] if c["char_id"] == kael["id"]),
        None,
    )
    assert kael_entry, (
        f"expected Kael in catalog; got "
        f"{[c['name'] for c in data['combatants']]}"
    )
    keys = [r["key"] for r in kael_entry["reactions"]]
    assert "deflect-missiles" in keys, (
        f"expected deflect-missiles in Kael's catalog; got {keys}"
    )


async def test_available_reactions_lists_caelan_protection(
    gm_client, roster,
):
    """v2.68.10 — Caelan's fighting style bumped from "defense" to
    "protection" so the v2.68.7 Phase 2c catalog has live coverage.
    The catalog now surfaces `fighting-style-protection` on Caelan.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    await _seed_battle(gm_client, [
        _make_combatant(caelan["name"], caelan["id"], init=10),
    ])
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/available_reactions",
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    caelan_entry = next(
        (c for c in data["combatants"] if c["char_id"] == caelan["id"]),
        None,
    )
    assert caelan_entry, (
        f"expected Caelan in catalog; got "
        f"{[c['name'] for c in data['combatants']]}"
    )
    keys = [r["key"] for r in caelan_entry["reactions"]]
    assert "fighting-style-protection" in keys, (
        f"expected fighting-style-protection in Caelan's catalog; "
        f"got {keys}"
    )


# ── v2.68.11 — Demo fixture consolidation v2 ──
# Tests below PATCH a demo PC's `subclass` / `fighting_style` /
# `level` via the v2.68.11 sheet-fields allowlist extension,
# assert the catalog reflects the mutation, then restore the
# original value in a finally block.


async def _patch_sheet_field(gm_client, char_id: int, **patch):
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=patch,
    )
    assert r.status_code == 200, r.text
    return r


async def _catalog_keys_for(gm_client, char_id: int) -> list[str]:
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/available_reactions",
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    entry = next(
        (c for c in data["combatants"] if c["char_id"] == char_id),
        None,
    )
    if entry is None:
        return []
    return [r["key"] for r in entry["reactions"]]


async def test_battle_master_maneuvers_via_patch(gm_client, roster):
    """v2.68.6 catalog gap closer: PATCH Garrik subclass to
    "Battle Master" → catalog includes riposte / parry / brace.
    """
    garrik = roster["Garrik Ironside"]
    await _seed_battle(gm_client, [
        _make_combatant(garrik["name"], garrik["id"], init=10),
    ])
    try:
        await _patch_sheet_field(
            gm_client, garrik["id"], subclass="Battle Master",
        )
        keys = await _catalog_keys_for(gm_client, garrik["id"])
        for k in ("riposte", "parry", "brace"):
            assert k in keys, (
                f"expected {k} in Garrik's catalog after Battle Master "
                f"patch; got {keys}"
            )
    finally:
        await _patch_sheet_field(
            gm_client, garrik["id"], subclass="Champion",
        )


async def test_interception_via_patch(gm_client, roster):
    """v2.68.7 catalog gap closer: PATCH Caelan fighting_style to
    "interception" → catalog includes fighting-style-interception.
    Restored to "protection" (the v2.68.10 default).
    """
    caelan = roster["Sir Caelan Lightbringer"]
    await _seed_battle(gm_client, [
        _make_combatant(caelan["name"], caelan["id"], init=10),
    ])
    try:
        await _patch_sheet_field(
            gm_client, caelan["id"], fighting_style="interception",
        )
        keys = await _catalog_keys_for(gm_client, caelan["id"])
        assert "fighting-style-interception" in keys, (
            f"expected fighting-style-interception in Caelan's catalog "
            f"after interception patch; got {keys}"
        )
    finally:
        await _patch_sheet_field(
            gm_client, caelan["id"], fighting_style="protection",
        )


async def test_cleric_light_via_patch(gm_client, roster):
    """v2.68.8 catalog gap closer: PATCH Tavik subclass to
    "Light Domain" → catalog includes warding-flare. Restored.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_battle(gm_client, [
        _make_combatant(tavik["name"], tavik["id"], init=10),
    ])
    try:
        await _patch_sheet_field(
            gm_client, tavik["id"], subclass="Light Domain",
        )
        keys = await _catalog_keys_for(gm_client, tavik["id"])
        assert "warding-flare" in keys, (
            f"expected warding-flare in Tavik's catalog after Light "
            f"Domain patch; got {keys}"
        )
    finally:
        await _patch_sheet_field(
            gm_client, tavik["id"], subclass="Life Domain",
        )


async def test_cleric_tempest_via_patch(gm_client, roster):
    """v2.68.8 catalog gap closer: PATCH Tavik subclass to
    "Tempest Domain" → catalog includes wrath-of-the-storm.
    Restored.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    await _seed_battle(gm_client, [
        _make_combatant(tavik["name"], tavik["id"], init=10),
    ])
    try:
        await _patch_sheet_field(
            gm_client, tavik["id"], subclass="Tempest Domain",
        )
        keys = await _catalog_keys_for(gm_client, tavik["id"])
        assert "wrath-of-the-storm" in keys, (
            f"expected wrath-of-the-storm in Tavik's catalog after "
            f"Tempest Domain patch; got {keys}"
        )
    finally:
        await _patch_sheet_field(
            gm_client, tavik["id"], subclass="Life Domain",
        )


async def test_warlock_archfey_via_patch(gm_client, roster):
    """v2.68.8 catalog gap closer: PATCH Magnus subclass to
    "The Archfey" + level to 6 → catalog includes misty-escape.
    Restored.
    """
    magnus = roster["Magnus Hexbinder"]
    await _seed_battle(gm_client, [
        _make_combatant(magnus["name"], magnus["id"], init=10),
    ])
    try:
        await _patch_sheet_field(
            gm_client, magnus["id"],
            subclass="The Archfey", level=6,
        )
        keys = await _catalog_keys_for(gm_client, magnus["id"])
        assert "misty-escape" in keys, (
            f"expected misty-escape in Magnus's catalog after Archfey "
            f"Lv 6 patch; got {keys}"
        )
    finally:
        await _patch_sheet_field(
            gm_client, magnus["id"],
            subclass="The Fiend", level=5,
        )


async def test_bard_valor_via_patch(gm_client, roster):
    """v2.68.9 catalog gap closer: PATCH Lyra subclass to
    "College of Valor" → catalog includes mantle-of-inspiration.
    Restored to "College of Lore".
    """
    lyra = roster["Lyra Sunstrider"]
    await _seed_battle(gm_client, [
        _make_combatant(lyra["name"], lyra["id"], init=10),
    ])
    try:
        await _patch_sheet_field(
            gm_client, lyra["id"], subclass="College of Valor",
        )
        keys = await _catalog_keys_for(gm_client, lyra["id"])
        assert "mantle-of-inspiration" in keys, (
            f"expected mantle-of-inspiration in Lyra's catalog after "
            f"Valor patch; got {keys}"
        )
    finally:
        await _patch_sheet_field(
            gm_client, lyra["id"], subclass="College of Lore",
        )


async def test_paladin_crown_via_patch(gm_client, roster):
    """v2.68.9 catalog gap closer: PATCH Caelan subclass to
    "Oath of the Crown" → catalog includes rebuke-the-violent.
    Restored to "Oath of Devotion".
    """
    caelan = roster["Sir Caelan Lightbringer"]
    await _seed_battle(gm_client, [
        _make_combatant(caelan["name"], caelan["id"], init=10),
    ])
    try:
        await _patch_sheet_field(
            gm_client, caelan["id"], subclass="Oath of the Crown",
        )
        keys = await _catalog_keys_for(gm_client, caelan["id"])
        assert "rebuke-the-violent" in keys, (
            f"expected rebuke-the-violent in Caelan's catalog after "
            f"Crown patch; got {keys}"
        )
    finally:
        await _patch_sheet_field(
            gm_client, caelan["id"], subclass="Oath of Devotion",
        )
