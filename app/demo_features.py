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

import re


def _slug(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "-")


def _parse_class_features(blob: str, max_level: int) -> list:
    """Parse the shipped SRD class-features markdown blob (from
    `local_features.resolve_class`) into the structured
    `[{key, name, desc, level}]` list the sheet renders, keeping only
    features whose level is ≤ ``max_level``.

    The blob is a stable shape: a top-level ``## <Class> Features`` title
    followed by ``### <Feature>`` sections, each whose first body line is
    a ``*Nth-level <class> feature*`` annotation (ASI uses a multi-level
    list — we take the first number). The parsed entries carry no
    automation ``key`` matches (they're display-only); the curated Vault
    PCs that DO drive automation keep their hand-authored lists (this only
    fills empty `class_features`)."""
    out: list = []
    for part in re.split(r"(?m)^###\s+", blob or ""):
        part = part.strip()
        if not part:
            continue
        head, _, body = part.partition("\n")
        name = head.strip()
        if not name or name.startswith("#"):
            continue  # the "## <Class> Features" preamble
        body = body.strip()
        m = re.search(r"\*\s*(\d+)(?:st|nd|rd|th)\b", body)
        level = int(m.group(1)) if m else 1
        if level > max_level:
            continue
        desc = re.sub(r"^\*[^*\n]*\*\s*", "", body).strip()
        key = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        out.append({
            "key": key, "name": name, "desc": desc[:800], "level": level,
        })
    return out


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

    # --- class features (parsed from the SRD markdown blob, level-filtered) ---
    # Only fills an EMPTY class_features — the curated Vault PCs keep their
    # hand-authored automation-driving lists. The parsed entries are
    # display-only (no automation key matches).
    if not (sheet.get("class_features") or []):
        class_slug = _slug(sheet.get("class") or sheet.get("klass") or "")
        try:
            level = int(sheet.get("level") or 1)
        except (TypeError, ValueError):
            level = 1
        if class_slug:
            try:
                crec, _csrc = lf.resolve_class(class_slug, scopes=["global"])
            except Exception:
                crec = None
            blob = (crec or {}).get("features") or ""
            feats = _parse_class_features(blob, level) if blob else []
            if feats:
                sheet["class_features"] = feats

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
