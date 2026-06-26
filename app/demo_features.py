"""Seed-time population of demo-PC subclass + race features from the
shipped SRD content layer (see docs/plans/campaign-stats.md is unrelated;
this is the demo-feature backfill discussed in the v2.652.x audit).

The character sheet stores `subclass_features` / `race_trait_items` as
structured lists; the sheet UI normally fetches them from the
`/api/open5e/*-detail` endpoints (local SRD first, live Open5e fallback)
on sheet open. Demo PCs ship with those fields EMPTY, so a freshly
reseeded demo shows blank subclass/race sections until a sheet is opened
online. This helper fills them at seed time from `local_features`
(shipped SRD, OFFLINE — it never touches live Open5e), matching the exact
shapes the UI's `_saveSubclassCache` / `_saveRaceCache` write:

  subclass: `subclass_features` = [{name, level, desc}], `subclass_name`,
            `subclass_flavor`
  race:     `race_trait_items` = [{name, level, desc}], `race_flavor`

SRD 5.1 ships only one subclass per class + 9 races, so the ~25 demo PCs
on non-SRD subclasses/races (Battle Master, Wood Elf, …) won't resolve —
those fields are left empty (the UI still backfills them from live Open5e
when the sheet is opened). Only empty fields are filled; curated
`class_features` lists and any pre-set features are never overwritten.
"""
from __future__ import annotations


def _slug(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "-")


# A few demo subrace/variant names map onto a shipped SRD base record.
_RACE_ALIASES = {
    "variant-human": "human",
}


def apply_srd_features(sheet: dict) -> dict:
    """Fill empty `subclass_features` / `race_trait_items` (+ companion
    name/flavor fields) on a dnd5e sheet from the shipped SRD content,
    when the PC's subclass / race resolves there. Mutates + returns the
    sheet. No-op for non-dnd5e sheets or unresolved (non-SRD) slugs.
    Offline-only — uses `local_features`, never live Open5e."""
    if not isinstance(sheet, dict):
        return sheet
    try:
        from . import local_features as lf
    except Exception:
        return sheet

    # --- subclass features ---
    if not (sheet.get("subclass_features") or []):
        class_slug = _slug(sheet.get("class") or sheet.get("klass") or "")
        sub_slug = _slug(sheet.get("subclass") or "")
        if class_slug and sub_slug:
            try:
                rec, _src = lf.resolve_subclass(
                    class_slug, sub_slug, scopes=["global"],
                )
            except Exception:
                rec = None
            feats = (rec or {}).get("features") or []
            if rec and feats:
                sheet["subclass_features"] = feats
                if not sheet.get("subclass_name"):
                    sheet["subclass_name"] = rec.get("name") or ""
                if not sheet.get("subclass_flavor"):
                    sheet["subclass_flavor"] = rec.get("flavor") or ""

    # --- race traits ---
    if not (sheet.get("race_trait_items") or []):
        race_slug = _slug(sheet.get("race") or "")
        race_slug = _RACE_ALIASES.get(race_slug, race_slug)
        if race_slug:
            try:
                rrec, _rsrc = lf.resolve_race(race_slug, scopes=["global"])
            except Exception:
                rrec = None
            traits = (rrec or {}).get("traits") or []
            if rrec and traits:
                sheet["race_trait_items"] = traits
                if not sheet.get("race_flavor"):
                    sheet["race_flavor"] = (
                        rrec.get("flavor") or rrec.get("alignment") or ""
                    )

    return sheet
