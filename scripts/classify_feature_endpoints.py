#!/usr/bin/env python3
"""Heuristic classifier for the automation-coverage audit.

Regenerates the tracked / announce-only / mechanical split documented in
``docs/automation-coverage.md``. An endpoint is a ``use_*`` / ``cast_*``
POST route in ``app/routes/tabletop_routes.py``; it is tagged:

  * ``tracked``       — body calls a state-mutating primitive or a
                        resource/economy decrement (see _MUTATORS).
  * ``announce-only`` — only broadcasts a ``feature_used`` card, no
                        state mutation detected.
  * ``mechanical``    — neither a feature card nor a mutation (helper
                        endpoints like use_dash that just flag movement).

The split is heuristic (±a few) by design — see the doc's "How to
regenerate" section. Run: ``python3 scripts/classify_feature_endpoints.py``.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROUTES = Path(__file__).resolve().parent.parent / "app" / "routes" / "tabletop_routes.py"

# State-mutating primitives + resource/economy decrements. A call to any
# of these inside an endpoint body marks it "tracked".
_MUTATORS = {
    "_install_buff",
    # v2.1031.2 — the target-side install helper. Its absence was a real
    # blind spot: endpoints that buff a *target* combatant (Fancy Footwork,
    # Order's Wrath, Unwavering Mark, Scornful Rebuke …) call only this and
    # were mis-tagged announce-only, which is exactly the drift the
    # v2.665.0 note in docs/automation-coverage.md spot-checked by hand.
    "_install_buff_on_combatant_id",
    "_grant_movement",
    "_apply_damage_to_combatant",
    "_grant_temp_hp",
    "_force_move",
    "_summon_companion",
    "_resolve_feature_save",
    "_tick_auras",
    "_mark_battle_economy",
    "_apply_heal_to_combatant",
    "_apply_heal",
    "_consume_feature_use",
    "_spend_feature_use",
}
# Regex fallbacks for mutation signals that aren't a bare call name.
_MUTATOR_PATTERNS = [
    re.compile(r"\bresource_update\b"),
    re.compile(r"\bspell_slot_update\b"),
    re.compile(r"flag_modified\(\s*char"),
    re.compile(r'\["used"\]\s*\+?='),
    re.compile(r"\.used\s*\+?="),
    re.compile(r"resources?\[[^\]]+\]\[[\"']current[\"']\]\s*[-+]?="),
]
_FEATURE_CARD = re.compile(r'["\']type["\']\s*:\s*["\']feature_used["\']')
_ENDPOINT_PATH = re.compile(r'router\.(post|get)\(\s*["\'][^"\']*?/(use_|cast_)([A-Za-z0-9_]+)')


def _called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                names.add(f.id)
            elif isinstance(f, ast.Attribute):
                names.add(f.attr)
    return names


def main() -> int:
    src = ROUTES.read_text()
    lines = src.splitlines()
    tree = ast.parse(src)

    # Map endpoint function node -> (kind: use|cast, slug) by scanning the
    # decorator lines directly (cheap line-slice, not get_source_segment).
    endpoints: dict[ast.AST, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for dec in node.decorator_list:
            dlines = "\n".join(lines[dec.lineno - 1: (dec.end_lineno or dec.lineno)])
            m = _ENDPOINT_PATH.search(dlines)
            if m:
                endpoints[node] = (m.group(2).rstrip("_"), m.group(3))
                break

    tracked: list[str] = []
    announce: list[str] = []
    mechanical: list[str] = []

    for node, (_kind, slug) in endpoints.items():
        seg = "\n".join(lines[node.lineno - 1: (node.end_lineno or node.lineno)])
        called = _called_names(node)
        is_tracked = bool(called & _MUTATORS) or any(p.search(seg) for p in _MUTATOR_PATTERNS)
        has_card = bool(_FEATURE_CARD.search(seg))
        if is_tracked:
            tracked.append(slug)
        elif has_card:
            announce.append(slug)
        else:
            mechanical.append(slug)

    total = len(tracked) + len(announce) + len(mechanical)
    print(f"Endpoints scanned: {total} (use_* / cast_* POST/GET routes)")
    print(f"  tracked       : {len(tracked)}")
    print(f"  announce-only : {len(announce)}")
    print(f"  mechanical    : {len(mechanical)}")
    print()
    print("announce-only slugs:")
    for s in sorted(set(announce)):
        print(f"  - {s}")
    print()
    print("mechanical slugs:")
    for s in sorted(set(mechanical)):
        print(f"  - {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
