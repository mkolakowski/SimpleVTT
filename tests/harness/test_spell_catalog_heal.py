"""Phase 2D — healing assertions across the spell catalog.

For every healing spell in ``app/data/local/dnd5e/spells/`` (Cure
Wounds, Healing Word, Heal, Mass Cure Wounds, Mass Healing Word,
Prayer of Healing, Regenerate): cast it at the caster (self-heal) and
assert the ``spell_cast`` broadcast's ``auto_heal_rolled`` falls inside
the spell's declared healing expression's range, shifted by the
caster's spellcasting modifier (RAW: "Cure Wounds heals 1d8 + your
spellcasting modifier", and the engine bakes the mod into every heal).

Why the WS broadcast and not the HTTP response: the ``/cast_spell``
HTTP body only carries ``auto_heal_applied`` (the HP actually
restored, capped by the target's missing HP — 0 at full health). The
rolled total + breakdown live on the ``spell_cast`` WS payload, so the
test reads them off ``gm_ws``.

The expected range is derived from the WS-reported (post-upcast)
``spell_healing`` expression rather than the catalog JSON, so upcast
scaling is handled for free; the catalog value is still asserted
non-empty as a content-drift guard.

Same scaffolding as the other Phase 2 catalog tests: one test patches
a scratch caster (Thalindra) with the whole catalog + abundant slots
and loops the healer subset — paying the autouse ``clean_pcs``
long-rest once.
"""
from __future__ import annotations

import asyncio

from .conftest import CAMPAIGN_ID
from .spell_catalog import dice_range, healing_expr_of, load_all_spells

_SCRATCH_CASTER = "Thalindra Moonwhisper"
_SCRATCH_CLASS = "wizard"
_ABILITIES = {"STR", "DEX", "CON", "INT", "WIS", "CHA"}

# Healers the catalog test can't yet assert cleanly. Empty today; add a
# slug -> reason here if a spell surfaces a known engine/content gap.
_SKIP_SLUGS: dict[str, str] = {}


def _heal_mod(sheet: dict) -> int:
    """Replicate ``_caster_spellcasting_mod`` (``tabletop_routes.py``
    ~line 8349): reads ``spellcasting_ability`` else ``class_spellcasting``,
    NO WIS fallback (returns 0 when neither names a valid ability), then
    ``(score - 10) // 2``. The engine only ADDS this to the heal when it's
    > 0 (RAW heal floor), so callers must apply the same guard."""
    spc = (
        sheet.get("spellcasting_ability") or sheet.get("class_spellcasting") or ""
    ).strip().upper()[:3]
    if spc not in _ABILITIES:
        return 0
    try:
        score = int((sheet.get("abilities") or {}).get(spc, 10))
    except (TypeError, ValueError):
        return 0
    return (score - 10) // 2


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


async def test_every_heal_spell_in_declared_range(gm_client, gm_ws, roster):
    """Cast every healing catalog spell at the caster and assert the
    ``spell_cast`` broadcast's ``auto_heal_rolled`` is inside the
    declared healing expression's [min, max], shifted by the caster's
    spellcasting modifier."""
    caster = roster[_SCRATCH_CASTER]
    cid = caster["id"]

    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-json",
    )
    sheet = (snap.json() or {}).get("sheet") or {}
    orig_spells = sheet.get("spells") or []
    orig_slots = sheet.get("spell_slots") or {}
    mod = _heal_mod(sheet)
    shift = mod if mod > 0 else 0

    spells = load_all_spells()
    entries = _all_entries(spells)
    idx_by_slug = {e["_slug"]: i for i, e in enumerate(entries)}
    heal_spells = [
        s for s in spells
        if (s.get("slug") or "") not in _SKIP_SLUGS and healing_expr_of(s)
    ]

    patch = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
        json={"spells": entries, "spell_slots": _abundant_slots()},
    )
    assert patch.status_code == 200, patch.text

    range_mismatches: list[str] = []
    unrolled: list[str] = []
    asserted = 0
    try:
        for s in heal_spells:
            slug = s["slug"]
            idx = idx_by_slug.get(slug)
            if idx is None:
                continue
            gm_ws.mark()
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                json={
                    "character_id": cid,
                    "spell_index": idx,
                    "slot_level": int(s.get("level_int") or 0),
                    "class_slug": _SCRATCH_CLASS,
                    "target_character_id": cid,
                    "target_name": _SCRATCH_CASTER,
                    "override": True,
                },
            )
            if resp.status_code != 200:
                unrolled.append(f"{slug}: HTTP {resp.status_code} {resp.text[:120]}")
                continue
            try:
                msg = await gm_ws.wait_for("spell_cast", timeout=3.0)
            except AssertionError:
                unrolled.append(f"{slug}: no spell_cast broadcast")
                continue
            data = msg.get("data") or {}
            rolled = data.get("auto_heal_rolled")
            expr = (data.get("spell_healing") or "").strip()
            if rolled is None or not expr:
                unrolled.append(
                    f"{slug}: no auto_heal_rolled / spell_healing in broadcast "
                    f"(rolled={rolled!r}, expr={expr!r})"
                )
                continue
            base_lo, base_hi = dice_range(expr)
            lo, hi = base_lo + shift, base_hi + shift
            if not (lo <= int(rolled) <= hi):
                range_mismatches.append(
                    f"{slug}: auto_heal_rolled {rolled} outside [{lo}, {hi}] "
                    f"(expr {expr!r} + mod {shift})"
                )
            asserted += 1
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )

    assert asserted >= 6, (
        f"only asserted {asserted} heal spells (expected ~7); unrolled={unrolled}"
    )
    assert not range_mismatches, (
        f"{len(range_mismatches)} heal-range mismatches:\n  "
        + "\n  ".join(range_mismatches)
    )


async def test_heal_catalog_subset_nonempty():
    """Guard: the healer subset is non-trivial so the catalog test can't
    pass vacuously if the JSON's healing fields go missing."""
    spells = load_all_spells()
    healers = [s for s in spells if healing_expr_of(s)]
    assert len(healers) >= 6, (
        f"expected ~7 healing spells, found {len(healers)} — the catalog's "
        f"healing fields may have regressed."
    )
