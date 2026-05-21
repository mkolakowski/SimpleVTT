"""Toast watcher — collects every toast that appears during a test.

See ``docs/plans/encounter-sim-test-suite.md``. Thin shell today;
the MutationObserver / queue plumbing lands in commit C when the
first test asserts on toast content.

Intended surface (from the plan):
  - ``start()``  mount a listener that pushes every new .toast /
                 .roll-toast into an in-memory queue
  - ``stop()``   detach
  - ``texts() -> list[str]``  every text seen so far
  - ``wait_for(substring, timeout_ms=3000)``  poll until a toast
                 matching the substring shows up, else assert
"""
from __future__ import annotations

from playwright.sync_api import Page


class ToastWatcher:
    def __init__(self, page: Page) -> None:
        self.page = page
