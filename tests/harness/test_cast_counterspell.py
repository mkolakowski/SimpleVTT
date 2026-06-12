"""Phase 4 — Counterspell deep-dive (the reaction-prompt contract).

Counterspell (PHB p.228) is a 3rd-level reaction spell: "you take it
when you see a creature within 60 feet of you casting a spell." The
engine models this as an auto-emitted `reaction_prompt(spell_cast_near)`
fired by `_emit_counterspell_prompts` (tabletop_routes.py:6126) at the
tail of `/cast_spell`, offering each eligible PC watcher a
`cast-counterspell` option resolved later through `/use_reaction`.

Where the catalog matrix (Phases 1-3) treats Counterspell as just
another buff/utility row, this file owns its bespoke story — the
prompt-emission contract, which is fully deterministic (distance + slot
eligibility, no dice):

  - a *visible, leveled* cast within 60 ft of a Counterspell-equipped
    watcher emits the prompt, carrying a `cast-counterspell` option
    whose params name the watcher's slot + the incoming level (and the
    label flags an AUTO-COUNTER when the slot level >= the incoming
    level, RAW);
  - a *cantrip* (level 0) emits nothing — the helper short-circuits on
    `spell_level <= 0` (RAW: you can counter cantrips, but the engine
    excludes them by design to avoid reaction-chain churn);
  - a watcher *out of 60 ft* gets no prompt (the per-watcher distance
    gate);
  - a watcher *without Counterspell* on their sheet gets no prompt (the
    `_pc_has_counterspell_available` eligibility gate).

The companion `test_counterspell_subtle_immune.py` already owns the
Subtle-Spell suppression slice (no V/S → nothing to see → no trigger);
this file is the positive-emission + exclusion-gate half.

Caster: Zara Emberfire (Sorcerer), scratch-injected with the catalog +
abundant slots so the leveled (Mage Armor) and cantrip (Fire Bolt) casts
both resolve to 200 deterministically. Watcher: Thalindra Moonwhisper
(Wizard, native L3 slot after a long rest), patched with Counterspell on
her sheet. Both are placed on the active map so the 60-ft walker can
measure token distance.
"""
from __future__ import annotations

import asyncio

import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

_CASTER = "Zara Emberfire"
_CASTER_CLASS = "sorcerer"
_WATCHER = "Thalindra Moonwhisper"
_LEVELED_SLUG = "mage-armor"   # L1 — within Thalindra's L3 slot → AUTO-COUNTER.
_CANTRIP_SLUG = "fire-bolt"    # L0 — the helper short-circuits, no prompt.

_COUNTERSPELL_SPELL = {
    "name": "Counterspell", "level": 3, "_slug": "counterspell",
    "prepared": True, "casting_time": "1 reaction",
}


def _all_entries(spells: list[dict], class_slug: str) -> list[dict]:
    out: list[dict] = []
    for s in spells:
        slug = (s.get("slug") or "").strip()
        if not slug:
            continue
        out.append({
            "name": s.get("name") or slug, "_slug": slug,
            "level": int(s.get("level_int") or 0), "class": class_slug,
            "prepared": True, "casting_time": s.get("casting_time") or "1 action",
        })
    return out


def _abundant_slots(class_slug: str) -> dict:
    return {class_slug: {str(lvl): {"total": 999, "used": 0} for lvl in range(1, 10)}}


async def _place_token(gm_client, char_id, x, y):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/place-token",
        json={"x": float(x), "y": float(y)},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _seed_battle(gm_client, caster, watcher, *, watcher_reaction=False):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [
            {"id": f"tok_cs_caster_{caster['id']}", "char_id": caster["id"],
             "name": caster["name"], "initiative": 10, "hp_current": 30, "hp_max": 30,
             "buffs": [], "economy": {"action": False, "bonus": False,
                                      "reaction": False, "movement": 0}},
            {"id": f"tok_cs_watcher_{watcher['id']}", "char_id": watcher["id"],
             "name": watcher["name"], "initiative": 8, "hp_current": 30, "hp_max": 30,
             "buffs": [], "economy": {"action": False, "bonus": False,
                                      "reaction": watcher_reaction, "movement": 0}},
        ], "turn_index": 0, "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def cs_setup(gm_client, roster):
    """Long-rest + scratch-inject the caster, snapshot both sheets, and
    yield a context the tests drive. Restores both sheets + clears the
    battle on teardown so no patched spell list leaks to the next test."""
    caster = roster[_CASTER]
    watcher = roster[_WATCHER]
    for cid in (caster["id"], watcher["id"]):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/rest", json={"type": "long"},
        )

    snap_c = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/sheet-json")
    ).json().get("sheet") or {}
    snap_w = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{watcher['id']}/sheet-json")
    ).json().get("sheet") or {}
    orig_c_spells = snap_c.get("spells") or []
    orig_c_slots = snap_c.get("spell_slots") or {}
    orig_w_spells = snap_w.get("spells") or []

    spells = load_all_spells()
    entries = _all_entries(spells, _CASTER_CLASS)
    idx_by_slug = {e["_slug"]: i for i, e in enumerate(entries)}
    patch = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/sheet-fields",
        json={"spells": entries, "spell_slots": _abundant_slots(_CASTER_CLASS)},
    )
    assert patch.status_code == 200, patch.text

    async def patch_watcher_spells(spells_list):
        r = await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{watcher['id']}/sheet-fields",
            json={"spells": spells_list},
        )
        assert r.status_code == 200, r.text

    try:
        yield {
            "caster": caster, "watcher": watcher,
            "idx_by_slug": idx_by_slug, "patch_watcher_spells": patch_watcher_spells,
        }
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{caster['id']}/sheet-fields",
            json={"spells": orig_c_spells, "spell_slots": orig_c_slots},
        )
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{watcher['id']}/sheet-fields",
            json={"spells": orig_w_spells},
        )
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
        )


async def _cast(gm_client, cs, slug, *, slot_level):
    caster, watcher, idx_by_slug = cs["caster"], cs["watcher"], cs["idx_by_slug"]
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": caster["id"], "spell_index": idx_by_slug[slug],
            "slot_level": slot_level, "class_slug": _CASTER_CLASS,
            "target_character_id": watcher["id"],
            "target_combatant_id": f"tok_cs_watcher_{watcher['id']}",
            "target_name": watcher["name"],
            "override": True, "override_range": True,
        },
    )


def _spell_cast_prompts(gm_ws):
    return [m for m in gm_ws.buffered("reaction_prompt")
            if (m.get("data") or {}).get("trigger_event") == "spell_cast_near"]


async def test_counterspell_present_in_catalog():
    """Catalog anchor — Counterspell is a real catalog spell, so a
    rename/removal trips this before the behavioural tests run."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    assert "counterspell" in by_slug, "counterspell absent from catalog"


async def test_prompt_emits_on_visible_leveled_cast(gm_client, gm_ws, cs_setup):
    """A visible L1 cast within 60 ft of a Counterspell-equipped watcher
    emits a `spell_cast_near` prompt carrying a `cast-counterspell`
    option whose params name the L3 slot + the L1 incoming level (and the
    label flags AUTO-COUNTER, since the slot level >= the incoming)."""
    cs = cs_setup
    await _place_token(gm_client, cs["caster"]["id"], 350.0, 350.0)
    await _place_token(gm_client, cs["watcher"]["id"], 420.0, 350.0)  # 1 cell ≈ 5 ft.
    await cs["patch_watcher_spells"]([_COUNTERSPELL_SPELL])
    await _seed_battle(gm_client, cs["caster"], cs["watcher"])

    gm_ws.mark()
    r = await _cast(gm_client, cs, _LEVELED_SLUG, slot_level=1)
    assert r.status_code == 200, r.text
    await asyncio.sleep(0.3)

    prompts = _spell_cast_prompts(gm_ws)
    assert prompts, "expected a spell_cast_near prompt for the visible L1 cast"
    data = prompts[-1]["data"]
    assert data.get("watcher_char_id") == cs["watcher"]["id"]
    opt = next((o for o in (data.get("options") or [])
                if o.get("key") == "cast-counterspell"), None)
    assert opt is not None, f"no cast-counterspell option; got {data.get('options')}"
    params = opt.get("params") or {}
    assert params.get("incoming_spell_level") == 1, params
    assert int(params.get("slot_level") or 0) >= 3, params
    assert "AUTO-COUNTER" in (opt.get("label") or "").upper(), opt.get("label")


async def test_no_prompt_for_cantrip(gm_client, gm_ws, cs_setup):
    """A cantrip (level 0) emits no Counterspell prompt — the helper
    short-circuits on `spell_level <= 0`."""
    cs = cs_setup
    await _place_token(gm_client, cs["caster"]["id"], 350.0, 350.0)
    await _place_token(gm_client, cs["watcher"]["id"], 420.0, 350.0)
    await cs["patch_watcher_spells"]([_COUNTERSPELL_SPELL])
    await _seed_battle(gm_client, cs["caster"], cs["watcher"])

    gm_ws.mark()
    r = await _cast(gm_client, cs, _CANTRIP_SLUG, slot_level=0)
    assert r.status_code == 200, r.text
    await asyncio.sleep(0.3)

    assert not _spell_cast_prompts(gm_ws), "cantrip cast must not emit a Counterspell prompt"


async def test_no_prompt_when_watcher_out_of_range(gm_client, gm_ws, cs_setup):
    """A watcher beyond 60 ft gets no prompt — the per-watcher distance
    gate filters them out even though they have Counterspell + a slot."""
    cs = cs_setup
    await _place_token(gm_client, cs["caster"]["id"], 350.0, 350.0)
    await _place_token(gm_client, cs["watcher"]["id"], 1450.0, 350.0)  # >60 ft away.
    await cs["patch_watcher_spells"]([_COUNTERSPELL_SPELL])
    await _seed_battle(gm_client, cs["caster"], cs["watcher"])

    gm_ws.mark()
    r = await _cast(gm_client, cs, _LEVELED_SLUG, slot_level=1)
    assert r.status_code == 200, r.text
    await asyncio.sleep(0.3)

    assert not _spell_cast_prompts(gm_ws), "out-of-range watcher must not be prompted"


async def test_no_prompt_when_watcher_lacks_counterspell(gm_client, gm_ws, cs_setup):
    """A watcher without Counterspell on their sheet gets no prompt — the
    `_pc_has_counterspell_available` eligibility gate excludes them."""
    cs = cs_setup
    await _place_token(gm_client, cs["caster"]["id"], 350.0, 350.0)
    await _place_token(gm_client, cs["watcher"]["id"], 420.0, 350.0)
    await cs["patch_watcher_spells"]([])  # no Counterspell.
    await _seed_battle(gm_client, cs["caster"], cs["watcher"])

    gm_ws.mark()
    r = await _cast(gm_client, cs, _LEVELED_SLUG, slot_level=1)
    assert r.status_code == 200, r.text
    await asyncio.sleep(0.3)

    assert not _spell_cast_prompts(gm_ws), "watcher without Counterspell must not be prompted"
