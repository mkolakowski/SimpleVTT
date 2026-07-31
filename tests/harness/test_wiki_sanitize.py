"""Tests for the wiki markdown HTML sanitization (v2.1042.0).

`_render_markdown_page` now pipes the Python-Markdown output through
`nh3.clean` so embedded raw HTML can't become stored XSS. These assert the
sanitizer (as we invoke it — bare `nh3.clean`) neutralizes dangerous markup
while preserving the doc structure markdown produces. Route-level no-regression
(docs still render 200 + nav) is covered by `test_wiki.py`.
"""
from __future__ import annotations

import nh3


def test_strips_script_and_event_handlers_and_js_urls():
    dirty = (
        "<h1>Title</h1>"
        "<script>alert(1)</script>"
        '<p onclick="steal()">hi</p>'
        '<a href="javascript:alert(1)">x</a>'
        '<img src=x onerror="alert(1)">'
    )
    clean = nh3.clean(dirty)
    assert "<script" not in clean.lower()
    assert "onclick" not in clean.lower()
    assert "onerror" not in clean.lower()
    assert "javascript:" not in clean.lower()
    # Structure preserved.
    assert "<h1>" in clean
    assert "Title" in clean


def test_keeps_markdown_structure_tags():
    dirty = (
        "<h2>H</h2><table><thead><tr><th>a</th></tr></thead>"
        "<tbody><tr><td>b</td></tr></tbody></table>"
        "<pre><code>x = 1</code></pre>"
        '<a href="/wiki/readme">link</a>'
    )
    clean = nh3.clean(dirty)
    for tag in ("<h2>", "<table>", "<td>", "<code>", "<a "):
        assert tag in clean, f"sanitizer dropped {tag}: {clean!r}"
    assert 'href="/wiki/readme"' in clean
