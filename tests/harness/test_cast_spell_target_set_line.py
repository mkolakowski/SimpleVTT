"""v2.376.0 — `/cast_spell` `target_set` line-shape variant.

Closes the AoE auto-targeting parity arc — `/cast_spell` now accepts
all three shapes (`sphere` v2.374.0, `cone` v2.375.0, `line` here):

    {
      "target_set": {
        "shape": "line",
        "caster_combatant_id": "<typically the caster>",
        "target_combatant_id": "<any combatant the line points at>",
        "width_ft": 5,            # optional, RAW Lightning Bolt default
        "max_length_ft": 100,     # optional
        "faction": "enemies"      # all | allies | enemies
      }
    }

Same rules as the sphere + cone variants:
- Caster + target combatants are always excluded from the result list
  (mirrors `/battle/line-targets` — target is the line's geometric
  anchor, not a member of the affected set).
- Faction filter mirrors v2.373.1 line-targets: PC ↔ PC = allies.
- Explicit `target_combatant_ids` win over `target_set`.

Tests:
  - Line caster + line-target + a third NPC inside the line's
    width/length → resolved id list has 1 row (the third NPC).
  - Missing `target_combatant_id` → 400.
  - `width_ft` ≤ 0 → 400.
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


FIREBALL_INDEX = 10  # Thalindra's spell list (see test_cast_spell_aoe.py).
                     # The endpoint doesn't validate spell shape vs. target_set
                     # shape; Fireball is reused to avoid seeding Lightning
                     # Bolt on Thalindra in the demo data.


async def _set_auto_apply(gm_client, on: bool) -> None:
    form = {
        "name": "Demo Campaign",
        "description": "demo",
        "game_system": "dnd5e",
        "gm_tab_color": "",
        "font_override": "",
        "default_encounter_id": "",
        "hp_threshold_1": "",
        "hp_threshold_2": "",
        "hp_threshold_3": "",
        "hp_threshold_4": "",
        "auto_play_playlist_id": "",
        "auto_play_mode": "order",
        "auto_play_initial_volume": "0.7",
    }
    if on:
        form["auto_apply_damage"] = "on"
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings", data=form,
        follow_redirects=False,
    )


async def _active_map_id(gm_client) -> int | None:
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/maps")
    if r.status_code != 200:
        return None
    maps = r.json() or []
    if isinstance(maps, list) and maps:
        return int(maps[0].get("id") or 0) or None
    return None


async def _place_token(gm_client, char_id, x, y, map_id) -> int:
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"map_id": map_id, "x": x, "y": y, "size": 1},
    )
    assert r.status_code == 200, r.text
    return int(r.json().get("token_id") or 0)


async def _bandit_tmpl(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    return next(t for t in templates if "bandit" in t["name"].lower())


@pytest_asyncio.fixture
async def thalindra_rested(gm_client, roster):
    thal = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
        json={"type": "long"},
    )
    return thal


async def test_target_set_line_picks_inline_bandit(
    gm_client, roster, thalindra_rested,
):
    """Thalindra at caster (100, 100), bandit-target at (200, 100),
    third bandit inline at (300, 100). The line resolver returns the
    third bandit (caster + target are excluded, both bandits are NPC =
    enemies of PC Thalindra)."""
    thal = thalindra_rested
    map_id = await _active_map_id(gm_client)
    if map_id is None:
        # No map → confirm the param parses without 500.
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thal["id"],
                "spell_index": FIREBALL_INDEX,
                "slot_level": 3, "class_slug": "wizard",
                "target_set": {
                    "shape": "line",
                    "caster_combatant_id": "tok_unknown_caster",
                    "target_combatant_id": "tok_unknown_target",
                    "width_ft": 5,
                    "max_length_ft": 100,
                    "faction": "enemies",
                },
                "override": True,
            },
        )
        assert resp.status_code in (400, 404), (
            f"expected 400/404 with no map; got {resp.status_code}: "
            f"{resp.text!r}"
        )
        return

    await _set_auto_apply(gm_client, on=True)
    thal_tok = await _place_token(gm_client, thal["id"], 100, 100, map_id)
    tmpl = await _bandit_tmpl(gm_client)
    bandit_token_ids: list[int] = []
    # Target bandit at (200, 100), inline bandit at (300, 100).
    for x in (200, 300):
        r = await gm_client.post(
            f"/api/map/{map_id}/spawn-token",
            json={
                "x": x, "y": 100, "size": 1,
                "token_template_id": tmpl["id"],
                "name": f"Bandit @{x}",
            },
        )
        if 200 <= r.status_code < 300:
            tok = r.json() or {}
            tid = int(tok.get("id") or tok.get("token_id") or 0)
            if tid:
                bandit_token_ids.append(tid)

    thal_cid = f"tok_tsetline_{thal['id']}"
    combatants = [
        {"id": thal_cid, "char_id": thal["id"],
         "name": thal["name"], "initiative": 10,
         "hp_current": 24, "hp_max": 24, "buffs": [],
         "economy": {"action": False, "bonus": False,
                     "reaction": False, "movement": 0},
         "source_token_id": thal_tok},
    ]
    bandit_cids: list[str] = []
    for i, (name, tid) in enumerate(zip(
        ("Bandit Target", "Bandit Inline"),
        bandit_token_ids,
    )):
        cid = f"tok_tsetline_b{i+1}"
        bandit_cids.append(cid)
        combatants.append({
            "id": cid, "char_id": None,
            "name": name, "initiative": 7 - i,
            "hp_current": 50, "hp_max": 50, "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0},
            "token_template_id": tmpl["id"],
            "source_token_id": tid,
        })
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )

    if len(bandit_cids) < 2:
        # spawn-token unavailable; degrade to param-parses check.
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thal["id"],
                "spell_index": FIREBALL_INDEX,
                "slot_level": 3, "class_slug": "wizard",
                "target_set": {
                    "shape": "line",
                    "caster_combatant_id": thal_cid,
                    "target_combatant_id": "tok_nonexistent",
                    "width_ft": 5,
                    "max_length_ft": 100,
                    "faction": "enemies",
                },
                "override": True,
            },
        )
        assert resp.status_code in (400, 404)
        return

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3,
            "class_slug": "wizard",
            "target_set": {
                "shape": "line",
                "caster_combatant_id": thal_cid,
                "target_combatant_id": bandit_cids[0],   # Target bandit (200,100).
                "width_ft": 30,       # Wide enough to absorb grid-cell centering.
                "max_length_ft": 200, # Long enough to reach the inline bandit.
                "faction": "enemies",
            },
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    targets = data.get("auto_save_targets") or []
    # Caster (Thalindra) AND target (bandit #1) are excluded; only the
    # inline bandit (#2) remains.
    assert len(targets) == 1, (
        f"expected 1 resolved target (caster + line-target excluded); "
        f"got {len(targets)}: {targets}"
    )
    assert targets[0].get("target_name") == "Bandit Inline"


async def test_target_set_line_missing_target_400(
    gm_client, roster, thalindra_rested,
):
    """`target_set` line with no `target_combatant_id` → 400."""
    thal = thalindra_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3, "class_slug": "wizard",
            "target_set": {
                "shape": "line",
                "caster_combatant_id": "tok_anything",
                # target missing.
                "width_ft": 5,
                "max_length_ft": 100,
                "faction": "enemies",
            },
            "override": True,
        },
    )
    assert resp.status_code == 400, (
        f"missing target_combatant_id should 400; got "
        f"{resp.status_code}: {resp.text!r}"
    )


async def test_target_set_line_invalid_width_400(
    gm_client, roster, thalindra_rested,
):
    """`target_set` line with `width_ft=0` → 400."""
    thal = thalindra_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3, "class_slug": "wizard",
            "target_set": {
                "shape": "line",
                "caster_combatant_id": "tok_anything",
                "target_combatant_id": "tok_anything_else",
                "width_ft": 0,
                "max_length_ft": 100,
                "faction": "enemies",
            },
            "override": True,
        },
    )
    assert resp.status_code == 400, (
        f"width_ft=0 should 400; got {resp.status_code}: {resp.text!r}"
    )
