"""Canvas reader — pixel-sample helpers for canvas-only checks like
the 💀 skull overlay (v2.49.4) or AoE persistent markers.

See ``docs/plans/encounter-sim-test-suite.md``. Canvas pixel sampling
is intentionally a Phase 3 concern (used by Level 2 ``test_aoe_
persistent_marker.py`` first); this skeleton lands now so the
directory layout matches the plan. No method bodies until a test
needs them.

Intended surface (from the plan):
  - ``pixel_at(x, y) -> tuple[int, int, int, int]``  RGBA at a coord
  - ``has_skull_at(token_x, token_y) -> bool``       v2.49.4 overlay
                                                     present sample
  - ``marker_visible(name) -> bool``                  Spike Growth /
                                                     Spirit Guardians /
                                                     etc. marker present
"""
from __future__ import annotations

from playwright.sync_api import Page


class CanvasReader:
    def __init__(self, page: Page) -> None:
        self.page = page
