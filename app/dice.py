"""Dice expression parser.

Supports expressions like:
    1d20
    3d6+2
    2d8-1
    1d20+1d4+3
    4d6kh3       (keep highest 3)
    4d6kl3       (keep lowest 3)
    1d20a        (advantage  = 2d20kh1)
    1d20d        (disadvantage = 2d20kl1)

Returns dict with: total (int), breakdown (str), expression (str).
"""
from __future__ import annotations

import os
import random
import re
from dataclasses import dataclass
from typing import List


_TOKEN_RE = re.compile(
    r"""
    \s*
    (?P<sign>[+-])?
    \s*
    (?:
        (?P<dice>(?P<count>\d*)d(?P<sides>\d+)(?P<mod>(?:kh|kl)\d+|a|d)?)
        |
        (?P<flat>\d+)
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

MAX_DICE = 100  # safety cap


# v2.49.12: dedicated RNG instance for the dice resolver. Two reasons:
#   1. Determinism for the encounter-sim test suite (docs/plans/
#      encounter-sim-test-suite.md). Tests POST /api/test/dice/seed
#      (TEST_MODE-only endpoint) to call ``set_seed`` with a fixed
#      value; subsequent rolls are reproducible.
#   2. Isolation from any other module-level ``random`` consumers
#      (none today, but cheap insurance).
# Seeded from ``DICE_SEED`` env var on import when set; otherwise
# seeded from OS entropy via ``Random()`` no-arg constructor, which
# matches module-level ``random``'s default behavior.
_DICE_SEED_ENV = os.environ.get("DICE_SEED", "").strip()
_DICE_RNG: random.Random = (
    random.Random(int(_DICE_SEED_ENV))
    if _DICE_SEED_ENV.lstrip("-").isdigit()
    else random.Random()
)


def get_rng() -> random.Random:
    """Return the shared RNG instance used by every gameplay roll.

    Call sites that need a randint outside this module (e.g. the
    death-save d20 in ``tabletop_routes.py``) should use this rather
    than ``random.randint`` directly so that ``set_seed`` controls
    them too.
    """
    return _DICE_RNG


def set_seed(seed: int | None) -> None:
    """Re-seed the shared RNG. Used by the TEST_MODE-only
    ``/api/test/dice/seed`` endpoint so the encounter-sim harness
    can make rolls reproducible. ``None`` re-seeds from OS entropy
    (i.e. "go back to non-deterministic").
    """
    if seed is None:
        _DICE_RNG.seed()  # OS entropy
    else:
        _DICE_RNG.seed(int(seed))


@dataclass
class RollResult:
    expression: str
    total: int
    breakdown: str


class DiceParseError(ValueError):
    pass


def roll(expression: str) -> RollResult:
    expr = (expression or "").strip().replace(" ", "")
    if not expr:
        raise DiceParseError("Empty expression")
    # Tokenize. The regex must consume the entire string.
    pos = 0
    parts: List[str] = []
    total = 0
    first = True
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if not m or m.end() == pos:
            raise DiceParseError(f"Could not parse near: {expr[pos:]!r}")
        sign = m.group("sign") or ("+" if not first else "")
        first = False
        sign_val = -1 if sign == "-" else 1
        if m.group("dice"):
            count_s = m.group("count") or "1"
            count = int(count_s)
            sides = int(m.group("sides"))
            mod = (m.group("mod") or "").lower()
            if count == 0 or sides <= 0:
                raise DiceParseError("Dice must have positive count and sides")
            if count > MAX_DICE:
                raise DiceParseError(f"Too many dice (max {MAX_DICE})")
            # Advantage/disadvantage shortcut: each count is one adv/dis roll
            if mod in ("a", "d"):
                suffix = "kh1" if mod == "a" else "kl1"
                pair_descs = []
                subtotal = 0
                for _ in range(count):
                    pair = [_DICE_RNG.randint(1, sides), _DICE_RNG.randint(1, sides)]
                    kept = max(pair) if mod == "a" else min(pair)
                    pair_descs.append(f"[{','.join(str(r) for r in pair)}]{suffix}")
                    subtotal += kept
                desc = " ".join(pair_descs)
            elif mod.startswith("kh") or mod.startswith("kl"):
                k = int(mod[2:])
                if k <= 0 or k > count:
                    raise DiceParseError("Invalid keep count")
                rolls = [_DICE_RNG.randint(1, sides) for _ in range(count)]
                ordered = sorted(rolls, reverse=mod.startswith("kh"))
                kept = ordered[:k]
                desc = f"[{','.join(str(r) for r in rolls)}]{mod}{k}"
                subtotal = sum(kept)
            else:
                rolls = [_DICE_RNG.randint(1, sides) for _ in range(count)]
                desc = f"[{','.join(str(r) for r in rolls)}]"
                subtotal = sum(rolls)
            parts.append(f"{sign}{count}d{sides}{mod}{desc}={subtotal}".lstrip("+"))
            total += sign_val * subtotal
        else:
            flat = int(m.group("flat"))
            parts.append(f"{sign}{flat}".lstrip("+"))
            total += sign_val * flat
        pos = m.end()

    breakdown = " ".join(parts) + f"  =>  {total}"
    return RollResult(expression=expression, total=total, breakdown=breakdown)
