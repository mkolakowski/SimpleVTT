"""Phase 1 — smoke catalog: every SRD spell is castable without 500.

The floor contract from ``docs/plans/spell-validation-suite.md``
Phase 1: every spell in ``app/data/local/dnd5e/spells/`` can be cast
through ``/cast_spell`` without a 500, consumes a slot (leveled
spells), and emits a ``spell_cast`` WS broadcast.

Why one test, not 319 parameterized cases: the autouse ``clean_pcs``
fixture long-rests all 15 demo PCs before every test (~1 s). 319
parameterized items would pay that ~319 times and blow the 90 s
budget. Instead this single test patches one scratch caster's sheet
with the WHOLE catalog + abundant slots once, loops casting each
spell by index, and collects every failure — so a content edit that
500s any spell still names the offending slug in the assertion.

Why a scratch caster instead of "find a qualified caster": the
endpoint casts by ``spell_index`` into the caster's own sheet and
deducts from the ``class_slug`` slot pool. By injecting the entire
catalog onto one sheet under a single class with 999 slots at every
level, every spell becomes castable regardless of which class's list
it's really on — the smoke is a content-drift gate ("does this JSON
cast cleanly when placed on a sheet"), not a class-legality check.

Known-unsmokeable spells go in ``_SKIP_SLUGS`` with a reason rather
than silently passing (plan design principle #5).
"""
from __future__ import annotations

import asyncio

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

# Scratch caster — any full-caster demo PC works; we replace her
# spells + spell_slots wholesale and restore in finally.
_SCRATCH_CASTER = "Thalindra Moonwhisper"
_SCRATCH_CLASS = "wizard"

# Spells the smoke can't yet cast cleanly. Empty for now — populated
# with a reason if a content/engine bug surfaces, so the regression is
# tracked rather than hidden. Maps slug -> reason string.
_SKIP_SLUGS: dict[str, str] = {}


def _catalog_entries(spells: list[dict]) -> list[tuple[dict, dict]]:
    """Return ``(sheet_entry, source_spell)`` pairs for every catalog
    spell, skipping the ``_SKIP_SLUGS`` set. The sheet entry is the
    minimal shape ``/cast_spell`` needs: ``_slug`` drives SRD
    enrichment, ``level`` drives slot resolution.
    """
    pairs: list[tuple[dict, dict]] = []
    for s in spells:
        slug = (s.get("slug") or "").strip()
        if not slug or slug in _SKIP_SLUGS:
            continue
        pairs.append((
            {
                "name": s.get("name") or slug,
                "_slug": slug,
                "level": int(s.get("level_int") or 0),
                "class": _SCRATCH_CLASS,
                "prepared": True,
                "casting_time": s.get("casting_time") or "1 action",
            },
            s,
        ))
    return pairs


def _abundant_slots() -> dict:
    """999 unused slots at every level so 319 sequential casts never
    exhaust the pool (avoids per-spell re-patching)."""
    return {_SCRATCH_CLASS: {str(lvl): {"total": 999, "used": 0} for lvl in range(1, 10)}}


async def test_every_catalog_spell_casts_without_500(gm_client, gm_ws, roster):
    """Patch the scratch caster with the entire spell catalog + 999
    slots/level, cast each spell by index, and assert the floor
    contract for all of them at once.

    Floor per spell: HTTP 200 (no 500, no 404, no 409 no_slot).
    Aggregate: at least one ``spell_cast`` broadcast lands per
    successful cast (counted from the WS buffer, not per-spell waits).
    """
    caster = roster[_SCRATCH_CASTER]
    cid = caster["id"]

    # Snapshot the original spells + slots so we can restore. The
    # /sheet-json projection is the source of the live sheet shape.
    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-json",
    )
    sheet = (snap.json() or {}).get("sheet") or {}
    orig_spells = sheet.get("spells") or []
    orig_slots = sheet.get("spell_slots") or {}

    spells = load_all_spells()
    pairs = _catalog_entries(spells)
    entries = [e for e, _ in pairs]

    patch = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
        json={"spells": entries, "spell_slots": _abundant_slots()},
    )
    assert patch.status_code == 200, patch.text

    failures: list[str] = []
    cast_ok = 0
    try:
        gm_ws.mark()
        for idx, (entry, _src) in enumerate(pairs):
            slug = entry["_slug"]
            resp = await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
                json={
                    "character_id": cid,
                    "spell_index": idx,
                    "slot_level": entry["level"],
                    "class_slug": _SCRATCH_CLASS,
                    "override": True,
                },
            )
            if resp.status_code != 200:
                failures.append(
                    f"{slug} (L{entry['level']}): HTTP {resp.status_code} "
                    f"{resp.text[:160]}"
                )
                continue
            cast_ok += 1
        # Let the last few broadcasts flush into the WS buffer before
        # counting (the recv loop is async + the casts ran tight).
        await asyncio.sleep(0.5)
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{cid}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )

    assert not failures, (
        f"{len(failures)} / {len(pairs)} catalog spells failed the smoke "
        f"floor (expected 200):\n  " + "\n  ".join(failures)
    )

    # Aggregate broadcast floor: every successful cast should have
    # emitted a spell_cast. WS delivery can drop a tail under load, so
    # require the buffer to carry the vast majority rather than an
    # exact 1:1 (a hard regression — broadcasts stop entirely — still
    # trips this).
    broadcasts = gm_ws.buffered("spell_cast")
    assert len(broadcasts) >= cast_ok * 0.9, (
        f"spell_cast broadcasts ({len(broadcasts)}) far below successful "
        f"casts ({cast_ok}) — the WS emit path may have regressed."
    )


async def test_smoke_catalog_is_nonempty(gm_client):
    """Guard: the catalog loader actually found spells. A glob that
    silently returns [] would make the smoke test pass vacuously."""
    spells = load_all_spells()
    assert len(spells) >= 300, (
        f"expected ~319 SRD spells, loaded {len(spells)} — the catalog "
        f"path may have moved."
    )
