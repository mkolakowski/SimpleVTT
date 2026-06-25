"""v2.651.0 — per-campaign statistics read API, Phase 2.

`GET /api/campaign/{id}/stats` aggregates the campaign_stat_events log
(written by the capture hooks). Visibility: GM sees everyone; a non-GM
sees only their own characters. See docs/plans/campaign-stats.md.

Coverage:
  - GM: an attack + a cast are reflected in the aggregate totals
    (baseline-delta so prior tests' rows don't matter).
  - A non-GM player gets scope="self" and only their own characters —
    never another player's, even if they pass that character_id.
  - Unknown campaign → 404.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _stats(client, *, character_id=None):
    url = f"/api/campaign/{CAMPAIGN_ID}/stats"
    if character_id is not None:
        url += f"?character_id={character_id}"
    r = await client.get(url)
    assert r.status_code == 200, r.text
    return r.json()


def _char(blocks, char_id):
    return next((c for c in blocks if c["id"] == char_id), None)


async def test_stats_reflects_attack_and_cast(gm_client, roster):
    """A weapon hit (damage + attack) and a spell cast show up in the
    GM-scoped aggregate for the acting characters."""
    garrik = roster["Garrik Ironside"]
    zara = roster["Zara Emberfire"]

    # Baselines (GM view, per character).
    g0 = _char((await _stats(gm_client, character_id=garrik["id"]))["characters"], garrik["id"])
    g0_dmg = (g0 or {}).get("totals", {}).get("damage_dealt", 0)
    g0_atk = (g0 or {}).get("totals", {}).get("attacks", 0)
    z0 = _char((await _stats(gm_client, character_id=zara["id"]))["characters"], zara["id"])
    z0_casts = (z0 or {}).get("totals", {}).get("spells_cast", 0)

    npc_cid = "tok_statapi_dummy"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_statapi_g_{garrik['id']}", "char_id": garrik["id"],
             "name": garrik["name"], "initiative": 12,
             "hp_current": 85, "hp_max": 85, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": f"tok_statapi_z_{zara['id']}", "char_id": zara["id"],
             "name": zara["name"], "initiative": 14,
             "hp_current": 37, "hp_max": 37, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": npc_cid, "char_id": None, "name": "API Dummy",
             "initiative": 1, "hp_current": 300, "hp_max": 300, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )

    # Garrik attacks until a damaging hit lands.
    for _ in range(20):
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": garrik["id"], "attack_index": 0,
                  "target_combatant_id": npc_cid,
                  "override": True, "override_range": True},
        )
        assert r.status_code == 200, r.text
        if r.json().get("hit") and (r.json().get("damage_applied") or 0) > 0:
            break

    # Zara casts a spell (index 0).
    rc = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={"character_id": zara["id"], "spell_index": 0,
              "target_combatant_id": npc_cid, "override": True},
    )
    assert rc.status_code == 200, rc.text

    g1 = _char((await _stats(gm_client, character_id=garrik["id"]))["characters"], garrik["id"])
    assert g1 is not None
    assert g1["totals"]["damage_dealt"] > g0_dmg, g1["totals"]
    assert g1["totals"]["attacks"] > g0_atk, g1["totals"]

    z1 = _char((await _stats(gm_client, character_id=zara["id"]))["characters"], zara["id"])
    assert z1 is not None
    assert z1["totals"]["spells_cast"] > z0_casts, z1["totals"]
    assert z1["top_spells"], "expected at least one top-spell entry for Zara"


async def test_stats_player_sees_only_own(alice_client, gm_client, roster):
    """A non-GM player gets scope='self' and only their own characters —
    never another player's, even when passing that character_id."""
    garrik = roster["Garrik Ironside"]  # GM-owned, not Alice's

    data = await _stats(alice_client)
    assert data["scope"] == "self"
    returned_ids = {c["id"] for c in data["characters"]}
    assert garrik["id"] not in returned_ids, (
        "a player must not see a GM-owned character's stats"
    )

    # Passing another character's id is ignored — still scoped to self.
    data2 = await _stats(alice_client, character_id=garrik["id"])
    assert data2["scope"] == "self"
    assert garrik["id"] not in {c["id"] for c in data2["characters"]}


async def test_stats_unknown_campaign_404(gm_client):
    r = await gm_client.get("/api/campaign/99999999/stats")
    assert r.status_code == 404, r.text


async def test_stats_captures_lay_on_hands_healing(gm_client, roster):
    """v2.652.1 — Lay on Hands healing now feeds heal_done. Caelan
    long-rests (full pool), Pip is damaged so the heal lands, and the
    paladin's heal_done total increases."""
    caelan = roster["Sir Caelan Lightbringer"]
    pip = roster["Pip Quickfingers"]

    # Full pool.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caelan['id']}/rest",
        json={"type": "long"},
    )
    c0 = _char(
        (await _stats(gm_client, character_id=caelan["id"]))["characters"],
        caelan["id"],
    )
    c0_heal = (c0 or {}).get("totals", {}).get("heal_done", 0)

    # Damage Pip below max so the heal applies (restore after).
    sj = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-json"
    )).json().get("sheet") or {}
    orig_hp = sj.get("hp")
    _max = (orig_hp or {}).get("max") or 47
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
        json={"hp": {"current": 1, "max": _max}},
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_lay_on_hands",
            json={"character_id": caelan["id"],
                  "target_character_id": pip["id"],
                  "amount": 10, "override": True},
        )
        assert r.status_code == 200, r.text
        c1 = _char(
            (await _stats(gm_client, character_id=caelan["id"]))["characters"],
            caelan["id"],
        )
        assert c1 is not None
        assert c1["totals"]["heal_done"] > c0_heal, c1["totals"]
    finally:
        if orig_hp:
            await gm_client.patch(
                f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-fields",
                json={"hp": orig_hp},
            )
