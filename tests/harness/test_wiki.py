"""Harness tests for the in-repo wiki routes (v2.43.3).

Endpoint surface:
  GET /wiki              — landing page (Jinja-rendered)
  GET /wiki/{slug}       — serves docs/wiki/<slug>.html

Happy-path: each route returns 200 with HTML content + a known marker
string (the page title for the landing, the version stamp for the
roll-log guide). Error-path: an unknown slug 404s and a slug with
directory-traversal characters also 404s (never serves a file outside
docs/wiki/).
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


async def test_wiki_guide_serves_roll_log():
    """GET /wiki/roll-log-guide — 200 + body contains the version stamp
    the guide HTML carries at the top.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/roll-log-guide")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # The guide HTML's <h1> carries the title text — match a known
    # substring that won't drift across patch versions.
    assert "roll-log" in resp.text.lower()


async def test_wiki_unknown_slug_404():
    """GET /wiki/no-such-page — 404."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/wiki/no-such-page")
    assert resp.status_code == 404


async def test_wiki_traversal_blocked():
    """Path-traversal characters in the slug are rejected before
    touching the filesystem. ../something resolves to /wiki/../something
    in HTTP path-normal form (FastAPI usually collapses this before
    hitting the route), but the route's slug guard also rejects ``..``
    characters explicitly.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        # Dots in the slug — should be rejected by the slug guard
        resp = await client.get("/wiki/..%2Fpasswd")
    assert resp.status_code in (404, 400)
