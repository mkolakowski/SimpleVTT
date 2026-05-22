"""Parse plain-text "range" strings from spell / weapon JSON into feet.

v2.49.74 — Phase 2B of ``docs/plans/ruler-and-range.md``. The shipped
SRD spell JSON (under ``app/data/local/dnd5e/spells/``) stores range
as human-readable text — ``"60 feet"``, ``"Self"``, ``"Self
(30-foot radius)"``, ``"Touch"``, ``"Special"``, ``"Unlimited"``,
``"Sight"``, ``"1 mile"``. Demo weapons in ``app/demo_seed.py`` use
the abbreviated ``"5 ft"`` / ``"30/120 ft"`` (thrown / ranged with
normal/long bands) forms. This module collapses all of them into a
single number-of-feet projection the route handlers can compare
against the v2.49.73 ``_distance_ft_between_points`` reading.

Outputs:

  - ``0``           — "Self" / "Self (N-foot radius)" — self-range
                      spells skip the range check entirely; 0 is the
                      sentinel value (caller short-circuits before
                      computing distance).
  - ``5``           — "Touch" — RAW: touch = 5 ft melee reach.
  - ``int``         — "N feet" / "N ft" / "N foot" — straightforward
                      single-band range.
  - ``(N, M)``      — "N/M feet" — thrown / ranged weapons. ``N`` is
                      normal, ``M`` is long (disadvantage at long
                      range is RAW but is a separate concern; the
                      range check uses ``M`` as the absolute reach).
  - ``int``         — "N mile(s)" — RAW: 1 mile = 5280 ft. Spells
                      like Sending / Scrying use mile-scale ranges;
                      the check returns "in range" because the
                      cast endpoint's distance check would never
                      fail at this scale on a tabletop map. Kept as
                      a real number so the helper text is honest.
  - ``None``        — "Special" / "Unlimited" / "Sight" / any
                      unparseable string. Caller treats None as
                      "skip the range check" rather than 409 — the
                      conservative default for content we don't
                      understand.
"""
from __future__ import annotations

import re
from typing import Optional, Union

ParsedRange = Union[int, tuple[int, int]]

# Strings that mean "skip the range check" — special-cases for the
# RAW catch-alls Wizards.com uses on spells whose range doesn't map
# to a number.
_SKIP = frozenset({"special", "unlimited", "sight"})
_SELF = frozenset({"self"})
_TOUCH = frozenset({"touch"})

# "Self (30-foot radius)" — Spirit Guardians, Aura of Vitality, etc.
# The cast range is Self; the radius is irrelevant to the range check
# (AoE selector handles area). Anything starting with "self" + "(" is
# a self-anchored emanation.
_SELF_RADIUS_PREFIX = re.compile(r"^\s*self\s*\(", re.IGNORECASE)

# "5 feet" / "5 foot" / "5 ft" — single band.
_FEET_RE = re.compile(
    r"^\s*(\d+)\s*(?:ft|foot|feet)\.?\s*$",
    re.IGNORECASE,
)

# "20/60 feet" / "30/120 ft" — thrown / ranged with normal/long.
# Allow optional whitespace around the slash; require both numbers
# and a trailing "ft" / "feet".
_THROWN_RE = re.compile(
    r"^\s*(\d+)\s*/\s*(\d+)\s*(?:ft|foot|feet)\.?\s*$",
    re.IGNORECASE,
)

# "1 mile" / "5 miles" / "500 miles".
_MILE_RE = re.compile(r"^\s*(\d+)\s*miles?\.?\s*$", re.IGNORECASE)


def parse_range_ft(range_str: Optional[str]) -> Optional[ParsedRange]:
    """Project a range string into a feet projection.

    Returns:
      - ``int`` — single-band feet (also covers Touch=5 and Self=0).
      - ``tuple[int, int]`` — thrown / ranged weapon normal+long.
      - ``None`` — content we don't understand or that's deliberately
        outside the range-check's scope.
    """
    if not range_str:
        return None
    s = str(range_str).strip()
    if not s:
        return None
    lower = s.lower()
    if lower in _SKIP:
        return None
    if lower in _SELF:
        return 0
    if lower in _TOUCH:
        return 5
    if _SELF_RADIUS_PREFIX.match(s):
        return 0
    m = _THROWN_RE.match(s)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m = _FEET_RE.match(s)
    if m:
        return int(m.group(1))
    m = _MILE_RE.match(s)
    if m:
        return int(m.group(1)) * 5280
    return None


def max_range_ft(parsed: Optional[ParsedRange]) -> Optional[int]:
    """Collapse a parsed range to a single 'is the target reachable at
    all' integer.

    For thrown / ranged weapons returns the LONG range — the absolute
    reach. Disadvantage at long range is a separate concern that the
    range check doesn't enforce (it only gates "out of range entirely").
    Returns ``None`` when ``parsed`` is None.
    """
    if parsed is None:
        return None
    if isinstance(parsed, tuple):
        return parsed[1]
    return int(parsed)
