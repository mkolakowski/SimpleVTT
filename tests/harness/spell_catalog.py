"""Spell-catalog loader + dice-expression parser.

Phase 0/1 infrastructure for the spell-validation suite at
``docs/plans/spell-validation-suite.md``. Loads every spell JSON
under ``app/data/local/dnd5e/spells/`` once at session scope so the
catalog-iterating tests (Phase 1 smoke + Phase 2 per-mechanic) can
parameterize over a real dataset instead of hard-coding names.

The dice-expression parser turns ``"8d6"`` / ``"1d10+3"`` /
``"2d6+1d4"`` into a ``(min, max)`` tuple so damage range-checks
can assert ``min <= damage_total <= max`` without seeding the RNG.
Sum-of-components form (`+` joining NdN and flat modifiers) is the
shape we see across the SRD JSON.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


# Path to the SRD spell catalog. Resolved relative to the repo root so
# tests run regardless of where pytest is invoked from.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPELL_DIR = _REPO_ROOT / "app" / "data" / "local" / "dnd5e" / "spells"

# Component regex — matches "8d6", "1d10", "1d4+1" (we strip the +N
# tail separately), and bare integers like "+3". Anchored as alternation
# in dice_range below.
_DICE_RE = re.compile(r"(\d+)d(\d+)")
_FLAT_RE = re.compile(r"(?<![d\d])([+-]?\s*\d+)(?!d\d)")


def load_all_spells() -> list[dict]:
    """Read every ``app/data/local/dnd5e/spells/<slug>.json`` and
    return the parsed list. Session-scope-cacheable; the catalog
    doesn't change between tests inside a single run.
    """
    spells: list[dict] = []
    for path in sorted(_SPELL_DIR.glob("*.json")):
        try:
            spells.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            # Skip unparseable JSON — a future commit will gate the
            # catalog parse with a smoke test that fails on broken
            # content; here we want the iterating tests to keep
            # running against the rest of the catalog.
            continue
    return spells


def damage_actions(spell: dict) -> list[dict]:
    """Yield every action dict on ``spell`` that has a non-empty
    ``damage`` expression. Most spells have a single ``cast`` action;
    some (e.g. Eldritch Blast) have variants per level.
    """
    return [a for a in (spell.get("actions") or []) if (a.get("damage") or "").strip()]


def save_ability_of(spell: dict) -> str:
    """Return the spell's declared save ability as a 3-letter uppercase
    code (``"DEX"`` / ``"WIS"`` / …), or ``""`` if the spell has no
    save. Mirrors the resolution order ``/cast_spell`` uses (line
    ~19463 of ``tabletop_routes.py``): a top-level ``save_ability``
    first, else the first action that carries one. The SRD JSON stores
    it lowercase on actions; we uppercase + clip to match the endpoint.
    """
    raw = spell.get("save_ability") or next(
        (a.get("save_ability") for a in (spell.get("actions") or []) if a.get("save_ability")),
        "",
    )
    return (raw or "").strip().upper()[:3]


def dice_range(expression: str) -> tuple[int, int]:
    """Parse a dice expression and return ``(min, max)`` total bounds.

    Examples::

        dice_range("1d10")     -> (1, 10)
        dice_range("8d6")      -> (8, 48)
        dice_range("1d10+3")   -> (4, 13)
        dice_range("2d8-1")    -> (1, 15)
        dice_range("3d4+1d6")  -> (4, 18)
        dice_range("")         -> (0, 0)

    Sign handling: a leading ``-`` on a dice term is treated as
    subtraction of the dice total; a bare ``-N`` is subtracted from
    both min and max bounds.
    """
    expr = (expression or "").strip().lower().replace(" ", "")
    if not expr:
        return (0, 0)

    lo = 0
    hi = 0
    # Walk the expression, peeling off either a dice term (NdN) or a
    # flat modifier (+N / -N). Sign is captured from the preceding
    # character. We default the first term to positive.
    i = 0
    sign = +1
    while i < len(expr):
        ch = expr[i]
        if ch == "+":
            sign = +1
            i += 1
            continue
        if ch == "-":
            sign = -1
            i += 1
            continue
        # Try dice term first.
        m = _DICE_RE.match(expr, i)
        if m:
            count = int(m.group(1))
            sides = int(m.group(2))
            lo += sign * (count * 1)
            hi += sign * (count * sides)
            i = m.end()
            sign = +1
            continue
        # Try flat number.
        m = re.match(r"\d+", expr[i:])
        if m:
            n = int(m.group(0))
            lo += sign * n
            hi += sign * n
            i += m.end()
            sign = +1
            continue
        # Unrecognized character — bail to avoid an infinite loop.
        break
    # Normalize so lo <= hi (negative-dice subtraction can flip them).
    if lo > hi:
        lo, hi = hi, lo
    return (lo, hi)
