"""Phase 2B — save assertions across the spell catalog.

For every save-bearing spell in ``app/data/local/dnd5e/spells/``:
cast it at an NPC target and assert the ``/cast_spell`` response's
``auto_save_ability`` matches the spell's declared save ability and
``auto_save_dc`` matches the caster's spell save DC
(``8 + proficiency + spellcasting mod``).

Two contracts, both content-drift gates:
  - **Per-spell ability** — a content edit that flips a spell's save
    from (say) DEX to CON is caught the moment this runs. This is the
    valuable per-spell assertion.
  - **DC uniformity + formula** — every spell cast by the same caster
    must return the SAME DC (a spell wrongly carrying its own DC
    override breaks this), and that DC must equal the RAW formula.

Same scaffolding as ``test_spell_catalog_smoke.py`` (Phase 1): one
test patches a scratch caster with the whole catalog + abundant
slots, seeds one NPC target, and loops the save-spell subset —
paying the autouse ``clean_pcs`` long-rest once instead of per
parameterized case.
"""
from __future__ import annotations

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells, save_ability_of

_SCRATCH_CASTER = "Thalindra Moonwhisper"
_SCRATCH_CLASS = "wizard"
_ABILITIES = {"STR", "DEX", "CON", "INT", "WIS", "CHA"}

# Save spells the catalog test can't yet assert cleanly. Empty today;
# add a slug -> reason here if a spell surfaces a known engine/content
# gap rather than silently dropping it (plan design principle #5).
_SKIP_SLUGS: dict[str, str] = {}


def _expected_save_dc(sheet: dict) -> int:
    """Replicate the engine's spell-save-DC computation
    (``8 + proficiency + spellcasting mod``, matching
    ``_caster_spellcasting_mod`` in ``tabletop_routes.py`` ~line 12882)
    so the absolute value is anchored.

    v2.1033.3 (B16): the ability is ``spellcasting_ability OR
    class_spellcasting``. The demo sheets carry it under the top-level
    ``class_spellcasting`` field with ``spellcasting_ability`` ``None``,
    so the old bare read fell through to WIS and computed DC 12 for an
    INT caster the engine derives at 14."""
    prof = int(sheet.get("proficiency_bonus") or 2)
    spc = (
        sheet.get("spellcasting_ability")
        or sheet.get("class_spellcasting")
        or ""
    ).strip().upper()[:3]
    if spc not in _ABILITIES:
        spc = "WIS"
    ability_score = int((sheet.get("abilities") or {}).get(spc, 10))
    mod = (ability_score - 10) // 2
    return 8 + prof + mod


def _all_entries(spells: list[dict]) -> list[dict]:
    """Minimal sheet entries for every catalog spell (for the bulk
    inject), so the save subset can be cast by index."""
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


async def _seed_bandit(gm_client) -> str:
    """Seed one very-high-HP NPC bandit so 100+ damaging save spells
    in a row don't drop it (a dead combatant could stop resolving)."""
    templates = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")).json()
    bandit = next(t for t in templates if "bandit" in t["name"].lower())
    cid = "tok_savecatalog_target"
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": cid, "char_id": None,
                "token_template_id": bandit["id"],
                "name": "Save Catalog Target",
                "initiative": 5, "hp_current": 999999, "hp_max": 999999,
                "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return cid


async def test_every_save_spell_dc_and_ability(gm_client, roster):
    """Cast every save-bearing catalog spell at an NPC and assert the
    response's save ability matches the JSON and the DC matches the
    caster's spell save DC (uniform across all spells)."""
    caster = roster[_SCRATCH_CASTER]
    cid = caster["id"]

    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-json",
    )
    sheet = (snap.json() or {}).get("sheet") or {}
    orig_spells = sheet.get("spells") or []
    orig_slots = sheet.get("spell_slots") or {}
    expected_dc = _expected_save_dc(sheet)

    spells = load_all_spells()
    entries = _all_entries(spells)
    # Map slug -> sheet index for the bulk-injected list.
    idx_by_slug = {e["_slug"]: i for i, e in enumerate(entries)}
    # The save subset: spells whose engine-visible save ability resolves.
    save_spells = [
        s for s in spells
        if (s.get("slug") or "") not in _SKIP_SLUGS and save_ability_of(s) in _ABILITIES
    ]

    patch = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
        json={"spells": entries, "spell_slots": _abundant_slots()},
    )
    assert patch.status_code == 200, patch.text

    ability_mismatches: list[str] = []
    dc_mismatches: list[str] = []
    asserted = 0
    try:
        target_id = await _seed_bandit(gm_client)
        for s in save_spells:
            slug = s["slug"]
            idx = idx_by_slug.get(slug)
            if idx is None:
                continue
            expected_ability = save_ability_of(s)
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                json={
                    "character_id": cid,
                    "spell_index": idx,
                    "slot_level": int(s.get("level_int") or 0),
                    "class_slug": _SCRATCH_CLASS,
                    "target_combatant_id": target_id,
                    "target_name": "Save Catalog Target",
                    "override": True,
                },
            )
            if resp.status_code != 200:
                ability_mismatches.append(f"{slug}: HTTP {resp.status_code} {resp.text[:120]}")
                continue
            data = resp.json()
            got_ability = (data.get("auto_save_ability") or "").strip().upper()
            got_dc = data.get("auto_save_dc")
            if got_ability != expected_ability:
                ability_mismatches.append(
                    f"{slug}: auto_save_ability {got_ability!r} != JSON {expected_ability!r}"
                )
            if got_dc != expected_dc:
                dc_mismatches.append(
                    f"{slug}: auto_save_dc {got_dc!r} != expected {expected_dc}"
                )
            asserted += 1
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )

    assert asserted >= 100, (
        f"only asserted {asserted} save spells; expected ~116 — the "
        f"save subset may have shrunk unexpectedly."
    )
    assert not ability_mismatches, (
        f"{len(ability_mismatches)} save-ability mismatches (content drift):\n  "
        + "\n  ".join(ability_mismatches)
    )
    assert not dc_mismatches, (
        f"{len(dc_mismatches)} save-DC mismatches (expected uniform {expected_dc}):\n  "
        + "\n  ".join(dc_mismatches)
    )


async def test_save_catalog_subset_nonempty(gm_client):
    """Guard: the save subset is substantial so the catalog test can't
    pass vacuously if the JSON's save_ability fields go missing."""
    spells = load_all_spells()
    save_spells = [s for s in spells if save_ability_of(s) in _ABILITIES]
    assert len(save_spells) >= 100, (
        f"expected ~116 save spells, found {len(save_spells)} — the "
        f"catalog's save_ability fields may have regressed."
    )
