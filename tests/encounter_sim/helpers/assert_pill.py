"""Assertion helper for roll-log card pills.

A "pill" is one of the oversized outcome chips rendered inside a
``.roll-card`` — e.g. ``.result-pill.chip-damage`` showing "7 dmg",
or ``.result-pill.chip-success`` showing "Saved!" on a save spell.
See ``docs/wiki/roll-log-guide.html`` for the full pill taxonomy.

Tests call ``assert_pill(card, chip_class="chip-damage", text="7")``
where ``card`` is a Playwright Locator for the .roll-card element.
Keeping the helper here (rather than inline) means the pill DOM
shape lives in one file — when v2.50+ renames a chip class, the
diff is one line.
"""
from __future__ import annotations

from playwright.sync_api import Locator, expect


def assert_pill(
    card: Locator,
    *,
    chip_class: str,
    text: str | None = None,
    timeout_ms: int = 3000,
) -> Locator:
    """Assert the card has at least one pill with the given chip
    class (e.g. ``chip-damage``, ``chip-success``, ``chip-heal``,
    ``chip-crit``).

    If ``text`` is given, the pill must contain that substring too
    (e.g. ``text="7"`` for "7 dmg"). If omitted, only the class is
    asserted — useful when the test cares that *a* damage pill exists
    but not the exact value.

    Returns the matched pill Locator so the caller can chain further
    assertions if needed.
    """
    selector = f".result-pill.{chip_class}"
    pill = card.locator(selector).first
    expect(pill).to_be_visible(timeout=timeout_ms)
    if text is not None:
        expect(pill).to_contain_text(text, timeout=timeout_ms)
    return pill
