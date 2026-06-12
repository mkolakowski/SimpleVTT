"""Phase 2G — HTTP AoE placement + resolution across RAW shapes.

The companion to the pure-Python `test_spell_catalog_aoe.py` content
gate. That file asserts the catalog's `area.shape`/`size_ft` blocks are
RAW-valid; this one drives the live server end to end: cast an AoE spell
*without* targets so it lands in pending-placement state, then resolve it
through `/place_aoe` and assert the server (a) emits the catalog's shape +
size on the `aoe_pulse` broadcast, (b) resolves a save + damage for every
target id the client swept up, and (c) leaves a battle combatant that was
NOT swept up completely untouched (absent from `auto_save_targets`, HP
unchanged). That last pair is the "targets inside the AoE get the
broadcast, targets outside don't" contract the plan's Phase 2G vision
calls for — expressed at the resolution layer, since the inside/outside
*geometry* itself is computed client-side and the server resolves exactly
the id set it's handed.

`test_cast_spell_aoe.py` / `test_place_aoe_range.py` already cover the
sphere (Fireball) + cube (Web, concentration) placement paths and the
range gate. This test adds the **cone** and **line** shapes (Burning
Hands, Lightning Bolt) that no placement test exercised, alongside sphere,
so all three non-concentration damage AoE shapes round-trip through
`/place_aoe`. (Every cube AoE in the catalog is concentration, so it goes
down the `concentration_aoe_update` marker path covered by
`test_cast_spell_aoe.py::test_move_aoe_*` rather than `aoe_pulse`.)

Reuses the scratch-caster bulk-inject scaffolding (Thalindra + whole
catalog + abundant slots) so cone/line spells outside her demo list are
castable, and the v2.183.0 TEST_MODE `/api/test/campaign/{id}/flags`
endpoint to enable the server-side damage roll. One test loops the three
shapes, paying the autouse `clean_pcs` long-rest once.
"""
from __future__ import annotations

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

_SCRATCH_CASTER = "Thalindra Moonwhisper"
_SCRATCH_CLASS = "wizard"

# slug -> expected catalog area + cast inputs. Shapes chosen so each is a
# distinct RAW non-concentration damage AoE: sphere / cone / line. Values
# mirror the catalog `area` block (asserted against the live cast + pulse).
_CASES: dict[str, dict] = {
    "fireball": {"shape": "sphere", "size_ft": 20, "slot": 3, "dtype": "fire"},
    "burning-hands": {"shape": "cone", "size_ft": 15, "slot": 1, "dtype": "fire"},
    "lightning-bolt": {"shape": "line", "size_ft": 100, "slot": 3, "dtype": "lightning"},
}


def _all_entries(spells: list[dict]) -> list[dict]:
    out: list[dict] = []
    for s in spells:
        slug = (s.get("slug") or "").strip()
        if not slug:
            continue
        out.append({
            "name": s.get("name") or slug,
            "_slug": slug,
            "level": int(s.get("level_int") or 0),
            "class": _SCRATCH_CLASS,
            "prepared": True,
            "casting_time": s.get("casting_time") or "1 action",
        })
    return out


def _abundant_slots() -> dict:
    return {_SCRATCH_CLASS: {str(lvl): {"total": 999, "used": 0} for lvl in range(1, 10)}}


async def _bandit_tmpl(gm_client) -> dict:
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    return next(t for t in r.json() if "bandit" in t["name"].lower())


async def _seed_battle(gm_client, caster: dict, tmpl: dict, tag: str) -> tuple[str, str]:
    """Seed the caster + two bandits (one to sweep up, one to leave
    outside the placement). Returns the (in, out) combatant ids."""
    in_id = f"tok_aoeplace_{tag}_in"
    out_id = f"tok_aoeplace_{tag}_out"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": f"tok_aoeplace_{tag}_caster", "char_id": caster["id"],
                 "name": caster["name"], "initiative": 20,
                 "hp_current": 60, "hp_max": 60, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
                {"id": in_id, "char_id": None, "token_template_id": tmpl["id"],
                 "name": "Bandit Inside", "initiative": 10,
                 "hp_current": 60, "hp_max": 60, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
                {"id": out_id, "char_id": None, "token_template_id": tmpl["id"],
                 "name": "Bandit Outside", "initiative": 9,
                 "hp_current": 60, "hp_max": 60, "buffs": [],
                 "economy": {"action": False, "bonus": False,
                             "reaction": False, "movement": 0}},
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return in_id, out_id


async def _combatant_hp(gm_client, combatant_id: str) -> int:
    got = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/battle")
    combs = ((got.json() or {}).get("battle") or {}).get("combatants") or []
    c = next((c for c in combs if c.get("id") == combatant_id), {})
    return int(c.get("hp_current") or 0)


async def test_every_aoe_shape_places_resolves_inside_and_skips_outside(
    gm_client, gm_ws, roster,
):
    """For sphere / cone / line: cast with no targets → pending
    placement carries the catalog shape + size; `/place_aoe` with one
    swept-up bandit resolves its save + damage and pulses the catalog
    shape, while a second battle bandit left outside the placement is
    untouched (absent from `auto_save_targets`, HP unchanged)."""
    caster = roster[_SCRATCH_CASTER]
    cid = caster["id"]

    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-json",
    )
    sheet = (snap.json() or {}).get("sheet") or {}
    orig_spells = sheet.get("spells") or []
    orig_slots = sheet.get("spell_slots") or {}

    spells = load_all_spells()
    entries = _all_entries(spells)
    idx_by_slug = {e["_slug"]: i for i, e in enumerate(entries)}
    by_slug = {(s.get("slug") or ""): s for s in spells}

    # Capture + enable the server-side damage roll.
    flag_read = await gm_client.post(
        f"/api/test/campaign/{CAMPAIGN_ID}/flags", json={},
    )
    assert flag_read.status_code == 200, flag_read.text
    orig_flag = bool(flag_read.json()["auto_apply_damage"])

    patch = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
        json={"spells": entries, "spell_slots": _abundant_slots()},
    )
    assert patch.status_code == 200, patch.text

    failures: list[str] = []
    asserted = 0
    try:
        await gm_client.post(
            f"/api/test/campaign/{CAMPAIGN_ID}/flags",
            json={"auto_apply_damage": True},
        )
        tmpl = await _bandit_tmpl(gm_client)

        for slug, want in _CASES.items():
            idx = idx_by_slug.get(slug)
            spell = by_slug.get(slug)
            if idx is None or spell is None:
                failures.append(f"{slug}: not in catalog")
                continue

            in_id, out_id = await _seed_battle(gm_client, caster, tmpl, slug)
            out_hp_before = await _combatant_hp(gm_client, out_id)

            # Cast WITHOUT targets → pending placement.
            cast = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                json={
                    "character_id": cid,
                    "spell_index": idx,
                    "slot_level": want["slot"],
                    "class_slug": _SCRATCH_CLASS,
                    "override": True,
                },
            )
            if cast.status_code != 200:
                failures.append(f"{slug}: cast HTTP {cast.status_code} {cast.text[:120]}")
                continue
            cdata = cast.json()
            if cdata.get("pending_aoe_placement") is not True:
                failures.append(f"{slug}: not pending_aoe_placement: {cdata.get('pending_aoe_placement')!r}")
                continue
            if cdata.get("area_shape") != want["shape"]:
                failures.append(f"{slug}: cast area_shape {cdata.get('area_shape')!r} != {want['shape']!r}")
            if cdata.get("area_size_ft") != want["size_ft"]:
                failures.append(f"{slug}: cast area_size_ft {cdata.get('area_size_ft')!r} != {want['size_ft']}")
            cast_id = cdata["id"]

            gm_ws.mark()
            # Place on the INSIDE bandit only; leave the OUTSIDE one alone.
            place = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/place_aoe",
                json={
                    "cast_id": cast_id,
                    "target_combatant_ids": [in_id],
                    "center": {"x": 100, "y": 100},
                },
            )
            if place.status_code != 200:
                failures.append(f"{slug}: place HTTP {place.status_code} {place.text[:120]}")
                continue
            targets = place.json().get("auto_save_targets") or []
            names = {t.get("target_name") for t in targets}
            if names != {"Bandit Inside"}:
                failures.append(f"{slug}: resolved targets {names} != {{'Bandit Inside'}}")
            in_entry = next((t for t in targets if t.get("target_name") == "Bandit Inside"), None)
            if in_entry is None:
                failures.append(f"{slug}: inside bandit not resolved")
            else:
                if not isinstance(in_entry.get("rolled"), int):
                    failures.append(f"{slug}: inside rolled not int: {in_entry.get('rolled')!r}")
                if not (in_entry.get("damage_applied") or 0) > 0:
                    failures.append(f"{slug}: inside damage_applied not > 0: {in_entry}")
                if in_entry.get("damage_type") != want["dtype"]:
                    failures.append(f"{slug}: inside damage_type {in_entry.get('damage_type')!r} != {want['dtype']!r}")

            # The pulse carries the catalog shape + size.
            pulse = await gm_ws.wait_for("aoe_pulse", timeout=3.0)
            pdata = pulse["data"]
            if pdata.get("shape") != want["shape"]:
                failures.append(f"{slug}: pulse shape {pdata.get('shape')!r} != {want['shape']!r}")
            if pdata.get("size_ft") != want["size_ft"]:
                failures.append(f"{slug}: pulse size_ft {pdata.get('size_ft')!r} != {want['size_ft']}")

            # The resolved broadcast mirrors the response.
            res = await gm_ws.wait_for("spell_cast_aoe_resolved", timeout=3.0)
            rdata = res["data"]
            if rdata.get("cast_id") != cast_id:
                failures.append(f"{slug}: resolved cast_id {rdata.get('cast_id')!r} != {cast_id!r}")
            if len(rdata.get("auto_save_targets") or []) != 1:
                failures.append(f"{slug}: resolved target count != 1: {rdata.get('auto_save_targets')}")

            # The OUTSIDE bandit is untouched: not resolved, HP unchanged.
            if "Bandit Outside" in names:
                failures.append(f"{slug}: outside bandit was resolved but shouldn't be")
            out_hp_after = await _combatant_hp(gm_client, out_id)
            if out_hp_after != out_hp_before:
                failures.append(
                    f"{slug}: outside bandit HP changed {out_hp_before} -> {out_hp_after} "
                    f"(it was outside the placement)"
                )
            asserted += 1
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )
        await gm_client.post(
            f"/api/test/campaign/{CAMPAIGN_ID}/flags",
            json={"auto_apply_damage": orig_flag},
        )

    assert asserted == len(_CASES), (
        f"only resolved {asserted}/{len(_CASES)} AoE shapes; the catalog "
        f"may have dropped a shape's spell or changed its area block."
    )
    assert not failures, (
        f"{len(failures)} AoE-placement failures:\n  " + "\n  ".join(failures)
    )


def test_aoe_placement_cases_present_in_catalog():
    """Guard: every placement case slug resolves to a catalog spell
    whose first AoE-shaped action matches the expected shape + size, so
    the HTTP test can't silently drift from the catalog it asserts."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    for slug, want in _CASES.items():
        spell = by_slug.get(slug)
        assert spell is not None, f"{slug} missing from catalog"
        area = None
        for a in spell.get("actions") or []:
            ar = a.get("area") or {}
            if (ar.get("shape") or "").strip():
                area = ar
                break
        assert area is not None, f"{slug} has no AoE-shaped action"
        assert (area.get("shape") or "").strip() == want["shape"], (
            f"{slug} shape {area.get('shape')!r} != {want['shape']!r}"
        )
        assert int(area.get("size_ft") or 0) == want["size_ft"], (
            f"{slug} size_ft {area.get('size_ft')!r} != {want['size_ft']}"
        )
