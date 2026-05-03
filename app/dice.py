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
            # Advantage/disadvantage shortcut on a single d20-style die
            if mod in ("a", "d"):
                # 2dX, keep highest or lowest 1
                rolls = [random.randint(1, sides) for _ in range(2)]
                kept = max(rolls) if mod == "a" else min(rolls)
                desc = f"[{','.join(str(r) for r in rolls)}]{'kh1' if mod=='a' else 'kl1'}"
                subtotal = kept
            elif mod.startswith("kh") or mod.startswith("kl"):
                k = int(mod[2:])
                if k <= 0 or k > count:
                    raise DiceParseError("Invalid keep count")
                rolls = [random.randint(1, sides) for _ in range(count)]
                ordered = sorted(rolls, reverse=mod.startswith("kh"))
                kept = ordered[:k]
                desc = f"[{','.join(str(r) for r in rolls)}]{mod}{k}"
                subtotal = sum(kept)
            else:
                rolls = [random.randint(1, sides) for _ in range(count)]
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
