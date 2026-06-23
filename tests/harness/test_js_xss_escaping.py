"""v2.599.5+ — source guards for client-side DOM-XSS fixes.

The frontend is vanilla JS with no JS test runner, so these are source-level
regression guards: the specific user-controlled values that the security
review found being injected into `innerHTML` must go through the file's HTML
escaper. They catch a future edit that drops the escape and reintroduces the
DOM XSS.
"""
from __future__ import annotations

from pathlib import Path

_STATIC = Path(__file__).resolve().parents[2] / "app" / "static"


def test_oa_modal_escapes_watcher_name():
    """v2.599.5 — the Dash/opportunity-attack modal builds `provokers` from a
    combatant's `watcher_name` (free text) and injects it via `innerHTML`. It
    must be escaped (`escapeHTML(t.watcher_name ...)`)."""
    src = (_STATIC / "tabletop.js").read_text()
    assert "escapeHTML(t.watcher_name" in src, (
        "OA-modal watcher_name must be escaped before innerHTML injection"
    )
    # The pre-fix raw form must not return.
    assert ".map(t => t.watcher_name || 'a hostile')" not in src


def test_beast_picker_escapes_cr_in_cap_warning():
    """v2.599.6 — the beast picker's CR-cap warning injects a homebrew
    monster's free-text `m.cr` into `innerHTML`. It must be escaped
    (`_esc(m.cr)`); the raw `${m.cr} exceeds` form must not return."""
    src = (_STATIC / "beast_picker.js").read_text()
    assert "${_esc(m.cr)} exceeds" in src, "CR-cap warning must escape m.cr"
    assert "${m.cr} exceeds" not in src
