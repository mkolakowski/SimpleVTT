"""v2.375.0 — `/cast_spell` `target_set` cone-shape variant.

Extends the v2.374.0 `target_set` sphere helper to a `shape: "cone"`
variant that mirrors the geometry from `/battle/cone-targets`:

    {
      "target_set": {
        "shape": "cone",
        "apex_combatant_id": "<typically the caster>",
        "direction_combatant_id": "<any combatant the cone points at>",
        "length_ft": 15,
        "apex_half_angle_deg": 26.57,   # optional, RAW default
        "faction": "enemies"            # all | allies | enemies
      }
    }

Same rules as v2.374.0 sphere:
- Apex + direction combatants are always excluded from the result list
  (RAW: a self-anchored cone picker doesn't include the caster, and
  the direction combatant is the geometric anchor, not a target).
- Faction filter mirrors v2.373.1 cone-targets: PC ↔ PC = allies,
  PC ↔ NPC = enemies.
- Explicit `target_combatant_ids` win over `target_set`.

Tests:
  - `target_set` cone with faction="enemies" resolves bandits in the
    cone span; the cast succeeds and `auto_save_targets` is populated.
  - Missing `direction_combatant_id` → 400.
  - `length_ft` ≤ 0 → 400.
"""
from __future__ import annotations

import pytest_asyncio

from .conftest import CAMPAIGN_ID


FIREBALL_INDEX = 10  # Reusing Thalindra's spell list (see test_cast_spell_aoe.py).
                     # Fireball is RAW a sphere, but `/cast_spell` doesn't
                     # cross-check `target_set.shape` against the spell's RAW
                     # shape — the helper just resolves the target list and
                     # feeds it into the existing save+damage loop. Using
                     # Fireball keeps the test reproducible without seeding
                     # a Burning Hands entry on Thalindra (Wizards don't
                     # get Burning Hands in the demo seed).


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


async def test_target_set_cone_picks_bandits(
    gm_client, roster, thalindra_rested,
):
    """Thalindra at apex (100, 100), a bandit due east (200, 100) as
    the direction, and a second bandit also due east (250, 100) inside
    the cone span. The cone resolver should return the inside-the-cone
    bandit (200 is the direction, excluded; 250 is downrange in the
    span) and feed it into the save+damage loop."""
    thal = thalindra_rested
    map_id = await _active_map_id(gm_client)
    if map_id is None:
        # No map → validation falls through; just confirm the param
        # parses without a 500.
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thal["id"],
                "spell_index": FIREBALL_INDEX,
                "slot_level": 3, "class_slug": "wizard",
                "target_set": {
                    "shape": "cone",
                    "apex_combatant_id": "tok_unknown_apex",
                    "direction_combatant_id": "tok_unknown_dir",
                    "length_ft": 15,
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
    # Place tokens. Use a generous cone length (60 ft = 600 px in a
    # 50px-per-5ft grid = 12 grid squares) so test tolerates whatever
    # the demo map's grid_size_px is.
    thal_tok = await _place_token(gm_client, thal["id"], 100, 100, map_id)
    tmpl = await _bandit_tmpl(gm_client)
    bandit_token_ids: list[int] = []
    # Direction bandit at (200, 100) — due east of Thalindra.
    # Span bandit at (250, 100) — also due east, downrange of direction.
    for x in (200, 250):
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

    thal_cid = f"tok_tsetcone_{thal['id']}"
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
        ("Bandit Direction", "Bandit Downrange"),
        bandit_token_ids,
    )):
        cid = f"tok_tsetcone_b{i+1}"
        bandit_cids.append(cid)
        combatants.append({
            "id": cid,
            "char_id": None,
            "name": name,
            "initiative": 7 - i,
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
        # spawn-token endpoint unavailable; can't seed the geometry.
        # Just confirm the cast endpoint accepts the param shape.
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": thal["id"],
                "spell_index": FIREBALL_INDEX,
                "slot_level": 3, "class_slug": "wizard",
                "target_set": {
                    "shape": "cone",
                    "apex_combatant_id": thal_cid,
                    "direction_combatant_id": "tok_nonexistent",
                    "length_ft": 60,
                    "faction": "enemies",
                },
                "override": True,
            },
        )
        # No direction combatant → 404 from the helper.
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
                "shape": "cone",
                "apex_combatant_id": thal_cid,
                "direction_combatant_id": bandit_cids[0],
                "length_ft": 60,
                "faction": "enemies",
            },
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    targets = data.get("auto_save_targets") or []
    # Apex (Thalindra) AND direction (bandit #1) are excluded. Only the
    # downrange bandit (bandit #2) is left, and it's enemies (NPC) of
    # the PC apex → 1 outcome row.
    assert len(targets) == 1, (
        f"expected 1 resolved target (apex + direction excluded); "
        f"got {len(targets)}: {targets}"
    )
    assert targets[0].get("target_name") == "Bandit Downrange"


async def test_target_set_cone_missing_direction_400(
    gm_client, roster, thalindra_rested,
):
    """`target_set` cone with no `direction_combatant_id` → 400."""
    thal = thalindra_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3, "class_slug": "wizard",
            "target_set": {
                "shape": "cone",
                "apex_combatant_id": "tok_anything",
                # direction missing.
                "length_ft": 15,
                "faction": "enemies",
            },
            "override": True,
        },
    )
    assert resp.status_code == 400, (
        f"missing direction_combatant_id should 400; got "
        f"{resp.status_code}: {resp.text!r}"
    )


async def test_target_set_cone_invalid_length_400(
    gm_client, roster, thalindra_rested,
):
    """`target_set` cone with `length_ft=0` → 400."""
    thal = thalindra_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": FIREBALL_INDEX,
            "slot_level": 3, "class_slug": "wizard",
            "target_set": {
                "shape": "cone",
                "apex_combatant_id": "tok_anything",
                "direction_combatant_id": "tok_anything_else",
                "length_ft": 0,
                "faction": "enemies",
            },
            "override": True,
        },
    )
    assert resp.status_code == 400, (
        f"length_ft=0 should 400; got {resp.status_code}: {resp.text!r}"
    )
