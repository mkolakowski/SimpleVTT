"""v2.900.0 — embedded doors P2: the client vision engine expands a wall into
its solid sub-spans, so an OPEN embedded door becomes a real gap for lighting +
fog shadow-casting (both blocker filters flatMap through `_wallSolidSpans`)."""
from __future__ import annotations

from playwright.sync_api import Page

from .conftest import tabletop_url


def test_wall_solid_spans_expands_open_embedded_doors(gm_page: Page) -> None:
    gm_page.goto(tabletop_url())
    gm_page.wait_for_function("() => typeof window._wallSolidSpans === 'function'", timeout=8000)

    r = gm_page.evaluate(
        """() => {
            const base = { x1: 0, y1: 0, x2: 100, y2: 0 };
            const plain = window._wallSolidSpans(base);
            const closed = window._wallSolidSpans(
                { ...base, doors: [{ id: 'd', t0: 0.3, t1: 0.7, open: false }] });
            const opened = window._wallSolidSpans(
                { ...base, doors: [{ id: 'd', t0: 0.3, t1: 0.7, open: true }] });
            const win = window._wallSolidSpans({ ...base, window: true });
            const legacyOpen = window._wallSolidSpans({ ...base, door: true, open: true });
            return {
                plain: plain.length,
                closed: closed.length,
                win: win.length,
                legacyOpen: legacyOpen.length,
                opened: opened,
            };
        }"""
    )
    assert r["plain"] == 1          # a plain wall → one whole segment
    assert r["closed"] == 1         # a CLOSED embedded door still blocks (whole wall)
    assert r["win"] == 0            # a window blocks nothing
    assert r["legacyOpen"] == 0     # a legacy open door blocks nothing
    # An OPEN embedded door leaves a gap → two solid spans ([0,0.3] + [0.7,1]).
    spans = sorted([[s["x1"], s["x2"]] for s in r["opened"]])
    assert len(spans) == 2, spans
    assert abs(spans[0][1] - 30) < 1, spans   # first span ends at the door start (x=30)
    assert abs(spans[1][0] - 70) < 1, spans   # second span starts at the door end (x=70)
