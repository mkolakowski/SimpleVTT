"""Harness tests for the in-repo wiki routes.

Endpoint surface:
  GET /wiki              — landing page (Jinja-rendered)
  GET /wiki/{slug}       — serves docs/wiki/<slug>.{md,html}
  GET /wiki/doc/{slug}   — v2.49.9: serves plans / references / repo-root
                           docs via the _DOC_ALLOWLIST mapping

Happy-path: each route returns 200 with HTML content + a known marker
string (the page title for the landing, the version stamp for the
roll-log guide, the H1 for an allowlisted doc). Error-path: an unknown
slug 404s, a slug with directory-traversal characters 404s, and a slug
that isn't in the doc allowlist also 404s.
"""
import httpx

from .helpers import BASE_URL


async def test_wiki_home_renders():
    """GET /wiki — 200 + HTML body contains the page title."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "SimpleVTT wiki" in resp.text
    # Available-guides table includes the roll-log guide link.
    assert "/wiki/roll-log-guide" in resp.text
    # v2.49.9: the wiki nav menu is rendered on the landing too.
    assert 'class="wiki-nav"' in resp.text
    # v2.49.9: Plans + References + Repo docs sections all reachable.
    assert "/wiki/doc/plan-test-harness" in resp.text
    assert "/wiki/doc/changelog" in resp.text
    assert "/wiki/doc/roll-log-card-layout" in resp.text
    # v2.49.66: ruler/range plan listed in the design-plans table.
    assert "/wiki/doc/plan-ruler-and-range" in resp.text
    # v2.49.68: player simulacrum plan listed too.
    assert "/wiki/doc/plan-player-simulacrum" in resp.text


async def test_wiki_guide_serves_roll_log():
    """GET /wiki/roll-log-guide — 200 + body contains the version stamp
    the guide HTML carries at the top.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/roll-log-guide")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "roll-log" in resp.text.lower()
    # v2.49.9: standalone HTML guide gets the wiki nav menu injected
    # after <body> so navigation is consistent with the Jinja pages.
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_unknown_slug_404():
    """GET /wiki/no-such-page — 404."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/no-such-page")
    assert resp.status_code == 404


async def test_wiki_markdown_guide_renders():
    """v2.43.14: GET /wiki/realtime-broadcasts-catalog — markdown
    source file under docs/wiki/ is rendered through the markdown
    package + wrapped in the wiki_md.html template. 200 + body
    contains the catalog's title text + the v2.49.9 wiki nav.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/realtime-broadcasts-catalog")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "Realtime broadcasts catalog" in resp.text
    assert "<h1" in resp.text
    assert "<table" in resp.text
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_traversal_blocked():
    """Path-traversal characters in the slug are rejected before
    touching the filesystem.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/..%2Fpasswd")
    assert resp.status_code in (404, 400)


async def test_wiki_doc_serves_plan():
    """v2.49.9: GET /wiki/doc/plan-test-harness — 200 + body contains
    the plan's H1 + the nav menu. The route reads
    ``docs/plans/test-harness.md`` via the _DOC_ALLOWLIST mapping.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-test-harness")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # The test-harness plan's H1 is "Autonomous click-through test harness — plan"
    assert "click-through" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_simulacrum_plan():
    """v2.49.68: GET /wiki/doc/plan-player-simulacrum — 200 + body
    contains the plan's title + the nav menu. Resolves through the
    _DOC_ALLOWLIST to ``docs/plans/player-simulacrum.md``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-player-simulacrum")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "simulacrum" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_ruler_plan():
    """v2.49.66: GET /wiki/doc/plan-ruler-and-range — 200 + body
    contains the plan's H1 + the nav menu. The route reads
    ``docs/plans/ruler-and-range.md`` via the _DOC_ALLOWLIST mapping.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/plan-ruler-and-range")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # The plan's H1 is "Ruler & Range Enforcement — Design Plan".
    assert "ruler" in resp.text.lower()
    assert "range" in resp.text.lower()
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_serves_root_doc():
    """v2.49.9: GET /wiki/doc/claude — 200 + body contains CLAUDE.md's
    H1 + the nav menu. The route reads ``CLAUDE.md`` from the repo
    root via the _DOC_ALLOWLIST mapping.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/claude")
    assert resp.status_code == 200
    assert "SimpleVTT" in resp.text
    assert "Claude Code guidelines" in resp.text
    assert 'class="wiki-nav"' in resp.text


async def test_wiki_doc_unknown_slug_404():
    """v2.49.9: a slug that isn't in _DOC_ALLOWLIST 404s. Important
    security guarantee — the allowlist is the only way to reach a
    file outside ``docs/wiki/``.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/not-in-allowlist")
    assert resp.status_code == 404


async def test_wiki_doc_traversal_blocked():
    """v2.49.9: directory-traversal characters in the doc slug are
    rejected by the slug guard before the allowlist lookup.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/doc/..%2Fconfig")
    assert resp.status_code in (404, 400)
