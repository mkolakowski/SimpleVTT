"""SRD-only scope gate — enforces the "ships SRD 5.1 content only" rule.

See the "SimpleVTT ships SRD 5.1 content only" section in CLAUDE.md. The
shipped content library (``app/data/local/dnd5e/``, the ``SHIPPED_ROOT``
tier the engine loads as global content) must contain **only** SRD 5.1
mechanics; non-SRD content (Tasha's / Xanathar's / 2024 PHB / homebrew)
belongs in the campaign/operator **homebrew tier**
(``app/data/homebrew/`` · ``source: "local-homebrew"``), never baked into
the shipped image.

Two falsifiable halves of the rule are gated here:

  - **Only SRD** — every shipped record carries ``source: "srd"`` +
    ``scope: "global"`` + an SRD ``_attribution``. A non-SRD file dropped
    into the shipped tree trips this immediately.
  - **All SRD present (completeness floor)** — per-type record counts can
    only grow, never silently shrink. A destructive regen / accidental
    deletion (e.g. the build-script foot-gun guarded in v2.568.2) that
    drops files trips this.

The third half — "every SRD mechanic is *implemented*" — is NOT a pure
data assertion: much of the SRD is GM-narrated by design (a VTT where the
GM is the rules authority), so "supported" ≠ "fully automated". That
completeness is tracked by the SRD audit in ``TODO.md`` +
``docs/test-harness-coverage.md``, not claimed here.

Pure-Python: reads the shipped JSON tree directly (same pattern as
``test_spell_catalog_aoe.py``), no HTTP / WS fixtures.
"""
from __future__ import annotations

import json
import pathlib

# tests/harness/<this> → repo root is two parents up.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SHIPPED_DND5E = _REPO_ROOT / "app" / "data" / "local" / "dnd5e"

# Per-type completeness FLOORS — the current SRD 5.1 catalog counts. These
# are minimums (``>=``): adding SRD content is fine, silent loss is not.
# SRD 5.1 ships exactly one feat (Grappler) and a single sample background,
# so feats/backgrounds == 1 is correct, not a stub.
_FLOORS = {
    "spells": 319,
    "monsters": 322,
    "items": 294,
    "conditions": 15,
    "races": 16,
    "class_features": 12,
    "subclass_features": 13,
    "feats": 1,
    "backgrounds": 1,
}


def _load_type(type_dir: str) -> list[tuple[str, dict]]:
    d = _SHIPPED_DND5E / type_dir
    out: list[tuple[str, dict]] = []
    for path in sorted(d.glob("*.json")):
        out.append((path.name, json.loads(path.read_text())))
    return out


def test_all_shipped_content_is_srd_sourced():
    """Every record in the shipped content tree is SRD-provenanced — the
    "only SRD mechanics" half. Non-SRD content must live in the homebrew
    tier, never the shipped image."""
    offenders: list[str] = []
    checked = 0
    for type_dir in _FLOORS:
        for fname, rec in _load_type(type_dir):
            checked += 1
            where = f"{type_dir}/{fname}"
            if rec.get("source") != "srd":
                offenders.append(f"{where}: source={rec.get('source')!r} (want 'srd')")
            if rec.get("scope") != "global":
                offenders.append(f"{where}: scope={rec.get('scope')!r} (want 'global')")
            if "srd" not in (rec.get("_attribution") or "").lower():
                offenders.append(f"{where}: _attribution does not cite the SRD")
    assert checked > 900, f"only inspected {checked} records — content tree may be missing"
    assert not offenders, (
        f"{len(offenders)} shipped record(s) are not SRD-provenanced — non-SRD "
        f"content belongs in the homebrew tier (app/data/homebrew/), not the "
        f"shipped image:\n  " + "\n  ".join(offenders[:25])
    )


def test_srd_catalog_meets_completeness_floor():
    """Each content type still ships at least its known SRD 5.1 count — the
    "all SRD content present" half. A drop means a destructive regen or an
    accidental deletion silently shed SRD mechanics."""
    shortfalls: list[str] = []
    for type_dir, floor in _FLOORS.items():
        n = len(list((_SHIPPED_DND5E / type_dir).glob("*.json")))
        if n < floor:
            shortfalls.append(f"{type_dir}: {n} files < floor {floor}")
    assert not shortfalls, (
        "SRD content shrank below the known-good floor — investigate a "
        "dropped/clobbered content set:\n  " + "\n  ".join(shortfalls)
    )


def test_homebrew_tier_is_the_documented_extension_point():
    """Guard the rule's escape hatch: the homebrew tier is where non-SRD
    content goes. We don't require it to exist (operators may not use it),
    but if a shipped record ever needs non-SRD mechanics, this is the
    documented home — asserted by the loader's HOMEBREW_ROOT split, not
    baked into app/data/local/. This test documents the boundary so a
    future contributor sees *why* the SRD gate above is scoped to the
    shipped tree only."""
    # The shipped SRD tree and the homebrew tree are distinct roots.
    assert _SHIPPED_DND5E.is_dir(), "shipped SRD content tree missing"
    # No homebrew-sourced record may hide in the shipped tree.
    leaked = []
    for type_dir in _FLOORS:
        for fname, rec in _load_type(type_dir):
            if (rec.get("source") or "").lower() in ("homebrew", "local-homebrew"):
                leaked.append(f"{type_dir}/{fname}")
    assert not leaked, (
        f"homebrew-sourced records found in the shipped SRD tree: {leaked[:10]}"
    )
