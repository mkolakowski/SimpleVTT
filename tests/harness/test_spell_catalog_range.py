"""Phase 2H — range assertions across the spell catalog.

For every spell in ``app/data/local/dnd5e/spells/``: parse its declared
``range`` string through ``app/content/range_parser.py`` and assert the
projection matches the string's category. A content edit that corrupts a
range ("60 feet" → "60 fee", "Touch" → "Touchh") would make the parser
return ``None`` for a string that isn't a recognized skip token — caught
here as drift.

Categories (RAW, per the range_parser module docstring):
  - "Special" / "Unlimited" / "Sight" → ``None`` (deliberately skip the
    range check — content the parser doesn't reduce to a number).
  - "Self" / "Self (N-foot radius)"   → ``0`` (self-range sentinel).
  - "Touch"                            → ``5`` (5 ft melee reach).
  - "N feet" / "N foot" / "N ft"       → ``N``.
  - "N mile(s)"                        → ``N × 5280``.
  - anything else                      → **fail** (unrecognized → drift).

Pure-Python: imports the parser + the catalog loader directly, no HTTP /
WS fixtures (same pattern as ``test_range_parser.py``). Runs in CI under
the existing harness job. The HTTP cast-from-position range gate (cast
inside range succeeds, outside → 409 with a ``range`` body field) is a
filed follow-up — it needs the generic ``/cast_spell`` to enforce a
position-based range check, which isn't wired today.
"""
from __future__ import annotations

import re

from app.content.range_parser import max_range_ft, parse_range_ft

from .spell_catalog import load_all_spells

_SKIP_TOKENS = {"special", "unlimited", "sight"}
_NUM_RE = re.compile(r"(\d+)")


def test_every_spell_range_parses_to_its_category():
    """Every catalog spell's range parses to the projection its string
    category implies; an unrecognized string (typo / drift) fails."""
    spells = load_all_spells()
    failures: list[str] = []
    asserted = 0
    for s in spells:
        slug = (s.get("slug") or "?")
        raw = s.get("range")
        if not raw or not str(raw).strip():
            failures.append(f"{slug}: empty range field")
            continue
        text = str(raw).strip()
        lower = text.lower()
        parsed = parse_range_ft(text)
        reach = max_range_ft(parsed)
        asserted += 1

        if lower in _SKIP_TOKENS:
            if parsed is not None:
                failures.append(
                    f"{slug}: {text!r} is a skip token but parsed to {parsed!r}"
                )
        elif lower == "self" or lower.startswith("self ("):
            if parsed != 0:
                failures.append(f"{slug}: {text!r} should parse Self → 0, got {parsed!r}")
        elif lower == "touch":
            if parsed != 5:
                failures.append(f"{slug}: {text!r} should parse Touch → 5, got {parsed!r}")
        else:
            # Numeric band (feet or miles). Must parse, and the reach
            # must equal the embedded number (× 5280 for miles).
            if parsed is None:
                failures.append(f"{slug}: unrecognized range {text!r} (parsed None)")
                continue
            m = _NUM_RE.search(text)
            if not m:
                failures.append(f"{slug}: range {text!r} has no number but parsed {parsed!r}")
                continue
            n = int(m.group(1))
            expected = n * 5280 if "mile" in lower else n
            if reach != expected:
                failures.append(
                    f"{slug}: {text!r} reach {reach!r} != expected {expected}"
                )

    assert asserted >= 300, (
        f"only checked {asserted} spell ranges; expected ~319 — the "
        f"catalog may have shrunk or lost its range fields."
    )
    assert not failures, (
        f"{len(failures)} spell-range parse failures (content drift):\n  "
        + "\n  ".join(failures)
    )


def test_range_catalog_every_spell_has_a_range():
    """Guard: every catalog spell carries a non-empty range field so the
    parse gate can't pass vacuously."""
    spells = load_all_spells()
    assert len(spells) >= 300, f"catalog shrank to {len(spells)} spells"
    missing = [
        (s.get("slug") or "?") for s in spells
        if not s.get("range") or not str(s.get("range")).strip()
    ]
    assert not missing, f"spells missing a range field: {missing}"
