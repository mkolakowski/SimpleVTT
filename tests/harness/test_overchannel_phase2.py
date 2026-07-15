"""v2.1019.0 — Overchannel Phase 2 (Evocation Wizard Lv 14+).

Phase 1 (v2.1010.0) maxed the two NPC-auto-save damage paths in
`/cast_spell` (single-target save + AoE loop). Phase 2 extends the same
`_max_dice_total` read to the **spell-attack-roll** damage path in
`/cast_spell` (Guiding Bolt / Inflict Wounds / Scorching Ray) so an
armed Evoker's attack-roll damage spell also deals maximum damage.

Thalindra Moonwhisper (Wizard School of Evocation) is PATCH'd to Lv 14
and given Guiding Bolt (L1, 4d6 radiant, ranged spell attack → max 24).

Test:
  - Arm Overchannel, cast Guiding Bolt at a bandit; loop until a beam
    hits, then assert `auto_attack_damage_rolled` == 24 (4d6 maxed) and
    the ⚡ Overchannel card fired.
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


async def _add_guiding_bolt(gm_client, char_id):
    """Append Guiding Bolt to the wizard's spell list; return its index."""
    sj = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json"
    )).json().get("sheet") or {}
    spells = list(sj.get("spells") or [])
    for i, s in enumerate(spells):
        if (s.get("_slug") or "").lower() == "guiding-bolt":
            return i
    spells.append({"name": "Guiding Bolt", "level": 1, "prepared": True,
                   "_slug": "guiding-bolt"})
    await _patch_sheet(gm_client, char_id, {"spells": spells})
    return len(spells) - 1


async def _seed_vs_bandit(gm_client, thal):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    templates = r.json()
    bandit_tmpl = next(
        (t for t in templates if "bandit" in t["name"].lower()),
        templates[0])
    bandit_id = f"tok_ocp2_bandit_{thal['id']}"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            _pc(f"tok_ocp2_thal_{thal['id']}", thal),
            {"id": bandit_id, "char_id": None,
             "token_template_id": bandit_tmpl["id"],
             "name": bandit_tmpl["name"], "initiative": 5,
             "hp_current": 400, "hp_max": 400, "buffs": [],
             "economy": {"action": False, "bonus": False,
                         "reaction": False, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )
    return bandit_id


async def test_overchannel_maxes_attack_roll_spell(
    gm_client, gm_ws, roster, auto_apply_on,
):
    """Thalindra@Lv14 arms Overchannel then casts Guiding Bolt (4d6
    ranged spell attack). On a hit the attack-roll damage is maxed to 24
    and the ⚡ Overchannel card fires."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(gm_client, thal["id"], {"level": 14},
                       class_slug="wizard")
    try:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/rest",
            json={"type": "long"},
        )
        bandit_id = await _seed_vs_bandit(gm_client, thal)
        gb_index = await _add_guiding_bolt(gm_client, thal["id"])
        # Re-seed after the spell patch so the caster combatant persists.
        bandit_id = await _seed_vs_bandit(gm_client, thal)
        hit_seen = False
        for _ in range(25):
            # Re-arm each iteration (the buff is one-shot; a miss doesn't
            # consume it, but arming again is harmless — use_number just
            # increments, and we assert the maxed damage on the hit).
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/use_overchannel",
                json={"character_id": thal["id"]},
            )
            gm_ws.mark()
            r = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                json={
                    "character_id": thal["id"],
                    "spell_index": gb_index,
                    "target_combatant_id": bandit_id,
                    "override": True,
                    "override_range": True,
                },
            )
            assert r.status_code == 200, r.text
            data = r.json()
            if data.get("auto_attack_hit"):
                # 4d6 maxed = 24; a nat-20 crit doubles the dice → 8d6
                # maxed = 48. Both are the correct Overchannel maximum.
                expected = 48 if data.get("auto_attack_crit") else 24
                assert data["auto_attack_damage_rolled"] == expected, (
                    f"Guiding Bolt maxed should be {expected} "
                    f"({'8d6 crit' if data.get('auto_attack_crit') else '4d6'}); "
                    f"got {data.get('auto_attack_damage_rolled')}"
                )
                hit_seen = True
                await asyncio.sleep(0.3)
                cards = [
                    m for m in gm_ws.buffered("feature_used")
                    if (m.get("data") or {}).get("source") == "overchannel"
                    and "maximum damage" in (
                        m.get("data") or {}).get("feature_name", "")
                ]
                assert cards, "expected a ⚡ Overchannel card on the maxed hit"
                break
        assert hit_seen, "Guiding Bolt never hit the bandit in 25 casts"
    finally:
        await _patch_sheet(gm_client, thal["id"], {"level": 7},
                           class_slug="wizard")
