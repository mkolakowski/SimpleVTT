"""v2.99.315 — Shepherd Druid: Spirit Totem (E.4 batch, Lv 2+, XGE).

E.4 Druid ship #3 (Shepherd, XGE). RAW XGE p.24: bonus
action to summon Bear/Hawk/Unicorn spirit at point within
60 ft. 30-ft radius aura, persists 1 min. Once per short
or long rest.

Spirit effects:
- Bear: 5+druid_lv temp HP to allies in aura
- Hawk: reaction → ally advantage on attack
- Unicorn: heal-spell rider HP = druid_level

v1 announce-only — aura effects GM-tracked. Costs bonus chip.

Mira Lv 5 → bear_temp_hp 10, unicorn_heal_bonus 5.

Tests:
  - Lv 2+ happy with default Bear → temp HP 10.
  - Hawk mode → spirit "hawk".
  - Unicorn mode → spirit "unicorn".
  - Wrong subclass → 409.
  - Lv 1 gate → 409.
  - Back-to-back → 409 no_uses_left.
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


def _st_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "spirit-totem"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def mira_shepherd(gm_client, roster):
    """PATCH Mira to Shepherd + long-rest."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of the Shepherd"},
        class_slug="druid",
    )
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/rest",
        json={"type": "long"},
    )
    try:
        yield mira
    finally:
        await _patch_sheet(
            gm_client, mira["id"],
            {"subclass": "Circle of the Moon", "level": 5},
            class_slug="druid",
        )


async def test_use_st_happy_lv5_bear(
    gm_client, gm_ws, mira_shepherd,
):
    """Lv 5 Shepherd default → Bear, temp HP 10."""
    mira = mira_shepherd
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spirit_totem",
        json={"character_id": mira["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["spirit"] == "bear"
    assert data["bear_temp_hp"] == 10
    assert data["aura_radius_ft"] == 30
    assert data["duration_minutes"] == 1
    assert data["uses_remaining"] == 0
    assert data["druid_level"] == 5
    await asyncio.sleep(0.3)
    feats = _st_broadcasts(gm_ws, mira["id"])
    assert feats


async def test_use_st_hawk(
    gm_client, mira_shepherd,
):
    """spirit='hawk' passes through."""
    mira = mira_shepherd
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spirit_totem",
        json={"character_id": mira["id"], "spirit": "hawk", "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["spirit"] == "hawk"


async def test_use_st_unicorn(
    gm_client, mira_shepherd,
):
    """spirit='unicorn' → unicorn_heal_bonus 5."""
    mira = mira_shepherd
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spirit_totem",
        json={"character_id": mira["id"], "spirit": "unicorn", "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["spirit"] == "unicorn"
    assert data["unicorn_heal_bonus"] == 5


async def test_use_st_wrong_subclass(
    gm_client, roster,
):
    """Default Mira (Moon) → 409."""
    mira = roster["Mira Greenleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spirit_totem",
        json={"character_id": mira["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_st_level_gate(
    gm_client, roster,
):
    """Shepherd Mira at Lv 1 → 409."""
    mira = roster["Mira Greenleaf"]
    await _patch_sheet(
        gm_client, mira["id"],
        {"subclass": "Circle of the Shepherd", "level": 1},
        class_slug="druid",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_spirit_totem",
            json={"character_id": mira["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, mira["id"],
            {"subclass": "Circle of the Moon", "level": 5},
            class_slug="druid",
        )


async def test_use_st_out_of_uses(
    gm_client, mira_shepherd,
):
    """Back-to-back → 409 no_uses_left."""
    mira = mira_shepherd
    r1 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spirit_totem",
        json={"character_id": mira["id"], "override": True},
    )
    assert r1.status_code == 200, r1.text
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spirit_totem",
        json={"character_id": mira["id"], "override": True},
    )
    assert r2.status_code == 409, r2.text
    data = r2.json()
    assert data.get("error") == "no_uses_left"


async def test_st_bear_applies_temp_hp(
    gm_client, gm_ws, mira_shepherd,
):
    """v2.99.421 — Phase 4.2: the Bear spirit grants temp HP (5 + druid
    level) to the supplied aura allies via _grant_temp_hp.

    PUT a battle with Mira + two bare NPC allies, summon the Bear with a
    target list, and assert each NPC's temp_hp == bear_temp_hp (10 at
    Lv 5), read from battle_update.
    """
    mira = mira_shepherd
    mira_tok = f"tok_st_mira_{mira['id']}"
    tok_a, tok_b = "tok_st_a", "tok_st_b"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": mira_tok, "char_id": mira["id"], "name": mira["name"],
             "initiative": 12, "hp_current": 40, "hp_max": 40, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": tok_a, "char_id": None, "name": "Ally A",
             "initiative": 8, "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": tok_b, "char_id": None, "name": "Ally B",
             "initiative": 6, "hp_current": 30, "hp_max": 30, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spirit_totem",
        json={"character_id": mira["id"], "spirit": "bear",
              "target_combatant_ids": [tok_a, tok_b], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    bear = data["bear_temp_hp"]
    assert bear == 10  # 5 + druid level 5
    assert data["targets_applied"] == 2

    await asyncio.sleep(0.3)
    bus = gm_ws.buffered("battle_update")
    assert bus
    combs = {c.get("id"): c for c in (bus[-1]["data"].get("combatants") or [])}
    assert int(combs[tok_a].get("temp_hp") or 0) == bear
    assert int(combs[tok_b].get("temp_hp") or 0) == bear


async def test_st_bear_aura_regrants_each_turn(
    gm_client, gm_ws, roster, mira_shepherd,
):
    """v2.99.427 — Phase 5.3: the Bear spirit installs an aura buff so the
    tick re-grants temp HP to allies in the aura at the start of the
    druid's turn (ongoing re-grant, not just on summon).

    No summon target list → the only grant comes from the aura tick. Mira
    (druid, PC) + Pip (PC ally) in init; advance to Mira's turn → Pip
    gains 10 temp HP (5 + druid level 5) via _grant_temp_hp.
    """
    mira = mira_shepherd
    pip = roster["Pip Quickfingers"]  # PC ally (clean_pcs cleared temp → 0)
    mira_tok = f"tok_str_mira_{mira['id']}"
    pip_tok = f"tok_str_pip_{pip['id']}"

    def _battle(mira_buffs, turn_index):
        return {"combatants": [
            {"id": mira_tok, "char_id": mira["id"], "name": mira["name"],
             "initiative": 20, "hp_current": 40, "hp_max": 40,
             "buffs": mira_buffs,
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
            {"id": pip_tok, "char_id": pip["id"], "name": pip["name"],
             "initiative": 10, "hp_current": 47, "hp_max": 47, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": turn_index, "round": 1, "active": True}

    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle", json=_battle([], 1))
    # Summon the Bear with NO target list → installs the aura buff only.
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_spirit_totem",
        json={"character_id": mira["id"], "spirit": "bear", "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["aura_installed"] is True
    assert data["targets_applied"] == 0  # no summon grant
    bear = data["bear_temp_hp"]
    assert bear == 10

    bu = await gm_ws.wait_for("buff_update")
    mira_buffs = bu["data"]["buffs"]
    assert any(b.get("key") == "spirit-totem-bear" for b in mira_buffs)

    # Advance to Mira's turn (index 0) carrying the aura buff → tick
    # re-grants temp HP to the ally Pip.
    gm_ws.mark()
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json=_battle(mira_buffs, 0) | {"round": 2},
    )
    hp = await gm_ws.wait_for("character_hp_update")
    assert hp["data"]["character_id"] == pip["id"]
    assert int(hp["data"]["hp"].get("temp") or 0) == bear
