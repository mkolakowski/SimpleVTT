"""v2.599.3 — regression tests for the mini-sheet detail-bit XSS.

`_tab_actions.html` and `_tab_spells.html` build a `<span>...</span>` detail
string by Jinja string-concat (`~`) and emit it with `| safe` (to render the
literal `<span><strong>` wrappers). The interpolated values — a custom
attack's `range`/`damage_type`/`properties` and a (homebrew) spell's
`casting_time`/`range`/`duration`/`components` — are player/GM-authored free
text. Before v2.599.3 they were concatenated raw, so `| safe` disabled
autoescape on them → stored XSS rendered on the shared tabletop mini-sheet.

These render the real partials through the app's Jinja environment and assert
the payload is HTML-escaped. Pure in-process (no container), same pattern as
`test_visitor_log.py` / `test_audit_log.py`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("jinja2")

from jinja2 import (  # noqa: E402 — after importorskip
    ChainableUndefined,
    Environment,
    FileSystemLoader,
    select_autoescape,
)

# Rebuild the app's Jinja environment without importing app.templates (which
# pulls in fastapi, unavailable host-side). Mirrors app/templates.py: same
# template dir, ChainableUndefined, and autoescape on for .html. The two
# partials use only builtin filters (int/join/safe/length/.../e), so no
# custom-filter registration is needed.
_TPL_DIR = Path(__file__).resolve().parents[2] / "app" / "templates"
_ENV = Environment(
    loader=FileSystemLoader(str(_TPL_DIR)),
    undefined=ChainableUndefined,
    autoescape=select_autoescape(["html", "xml"]),
)

_PAYLOAD = "<img src=x onerror=alert(1)>"
_ESCAPED = "&lt;img src=x"


def _render(name: str, **ctx) -> str:
    return _ENV.get_template(name).render(**ctx)


def test_custom_attack_detail_bits_are_escaped():
    out = _render(
        "_tab_actions.html",
        c={"id": 1, "name": "Pip"},
        attacks_list=[{
            "name": "Custom strike",
            "range": _PAYLOAD,
            "damage_type": _PAYLOAD,
            "properties": _PAYLOAD,
        }],
    )
    assert "mini-row-detail-bits" in out, "detail-bits row should render"
    assert _PAYLOAD not in out, "raw payload must not reach the HTML output"
    assert _ESCAPED in out, "payload must be HTML-escaped"


def test_spell_detail_bits_pipe_through_escape():
    """`_tab_spells.html` builds its `_sbits` the same way `_tab_actions.html`
    builds `_bits` (string-concat + `| safe` join), but rendering its spell
    rows requires deep caster context. The runtime behavior of the shared
    pattern is covered by `test_custom_attack_detail_bits_are_escaped`; here we
    guard the source so the homebrew-spell fields stay escaped: every `_sbits`
    detail field must pipe through `| e`, and no raw `~ s.<field> ~` remains."""
    src = (_TPL_DIR / "_tab_spells.html").read_text()
    bit_lines = [ln for ln in src.splitlines() if "_sbits.append" in ln]
    assert bit_lines, "expected _sbits.append lines in _tab_spells.html"
    for ln in bit_lines:
        assert "| e)" in ln, f"detail-bit field not escaped with | e: {ln.strip()}"
    for field in ("s.casting_time", "s.range", "s.duration", "s.components"):
        assert f"~ {field} ~" not in src, (
            f"raw unescaped {field} concatenated into a | safe detail bit"
        )
