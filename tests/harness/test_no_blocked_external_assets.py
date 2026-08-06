"""v2.1047.4 — served pages must not reference assets their own CSP blocks.

The app sends a Content-Security-Policy of
``style-src 'self' 'unsafe-inline'`` / ``script-src 'self' 'unsafe-inline'``
/ ``font-src 'self' data:`` — no third-party origins. But ``base.html``
was loading webfonts from ``fonts.googleapis.com`` and htmx from
``unpkg.com``, so every single page logged

    Refused to load the stylesheet ... because it violates the following
    Content Security Policy directive: "style-src 'self' 'unsafe-inline'"

and the fonts silently never applied — readers have been seeing the
Georgia/serif fallbacks the whole time. It surfaced only because two
Playwright tests assert "no console errors" (CI run 31070630004).

This is a self-inflicted class of bug: a template adds a CDN tag, the CSP
rejects it, nothing throws server-side, and the page *looks* fine because
CSS falls back. So rather than assert the two specific origins, these
tests derive the rule from the CSP the app actually sends and check that
no served page references an origin it forbids — which catches the next
CDN tag someone adds, whatever it is.
"""
import re

import pytest

from .conftest import CAMPAIGN_ID

# Pages that render the full base.html chrome, for a logged-in GM.
_PAGES = (
    "/",                       # the lobby (tabletop_routes.py:13580)
    "/characters",             # user_routes.py:44
    "/settings",
    f"/campaign/{CAMPAIGN_ID}",
    f"/campaign/{CAMPAIGN_ID}/settings",
    "/wiki",
)

# src=/href= values pointing at an absolute external origin.
_EXTERNAL_REF_RE = re.compile(
    r"""(?:src|href)\s*=\s*["'](https?://[^"']+)["']""", re.I)

# Origins the CSP would have to allow for a *loaded* asset. Anchor tags
# (plain navigation links) are fine — only fetched subresources matter,
# so the scan is restricted to <link rel=stylesheet>, <script src>, and
# <img src>.
_SUBRESOURCE_RE = re.compile(
    r"""<(?:link[^>]+href|script[^>]+src|img[^>]+src)\s*=\s*["']"""
    r"""(https?://[^"']+)["']""", re.I)


async def _csp(gm_client) -> str:
    r = await gm_client.get("/wiki")
    assert r.status_code == 200, r.text
    csp = r.headers.get("content-security-policy", "")
    assert csp, "no Content-Security-Policy header — this suite's premise is gone"
    return csp


def _allows_external(csp: str, directive: str) -> bool:
    """Does ``directive`` (or its default-src fallback) permit any
    non-'self' http(s) origin?"""
    parts = {}
    for chunk in csp.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, rest = chunk.partition(" ")
        parts[name.strip().lower()] = rest.strip()
    value = parts.get(directive, parts.get("default-src", ""))
    return "http://" in value or "https://" in value or "*" in value


async def test_csp_is_present_and_locked_down(gm_client):
    """The premise: the CSP forbids third-party styles, scripts and fonts.
    If this ever changes deliberately, the scan below should be revisited
    rather than silently weakened."""
    csp = await _csp(gm_client)
    for directive in ("style-src", "script-src", "font-src"):
        assert not _allows_external(csp, directive), (
            f"{directive} now permits an external origin ({csp}) — the "
            "no-blocked-assets scan below is no longer the right check")


@pytest.mark.parametrize("page", _PAGES)
async def test_page_loads_no_csp_blocked_subresource(gm_client, page):
    """**The invariant.** No served page may pull a stylesheet, script or
    image from an origin its own CSP refuses — that asset would never
    load, and the failure is silent in the browser."""
    r = await gm_client.get(page)
    if r.status_code == 404:
        pytest.skip(f"{page} not available on this stack")
    assert r.status_code == 200, f"{page} → {r.status_code}"
    offenders = sorted(set(_SUBRESOURCE_RE.findall(r.text)))
    assert not offenders, (
        f"{page} loads external subresource(s) the app's own CSP blocks, so "
        f"they silently never apply: {offenders}. Self-host them under "
        f"/static/ (see app/static/fonts.css) rather than widening the CSP.")


async def test_fonts_are_self_hosted_and_served(gm_client):
    """The three families ship in the image and actually serve."""
    r = await gm_client.get("/static/fonts.css")
    assert r.status_code == 200, r.text
    css = r.text
    for family in ("Cormorant Garamond", "Lora", "IM Fell English"):
        assert family in css, f"{family} missing from fonts.css"
    assert "fonts.gstatic.com" not in css, (
        "fonts.css still points at Google's CDN")

    urls = sorted(set(re.findall(r"url\('(/static/fonts/[^']+)'\)", css)))
    assert urls, "fonts.css declares no local font files"
    for url in urls:
        fr = await gm_client.get(url)
        assert fr.status_code == 200, f"{url} → {fr.status_code}"
        assert fr.content[:4] == b"wOF2", (
            f"{url} is not a woff2 file (got {fr.content[:8]!r})")


async def test_font_files_are_reachable_without_auth(gm_client):
    """Fonts are static chrome, not campaign media — they must not be
    caught by the v2.1047.0 uploads gate, which lives under
    /static/uploads/ only."""
    r = await gm_client.get("/static/fonts.css")
    assert r.status_code == 200
    url = re.search(r"url\('(/static/fonts/[^']+)'\)", r.text).group(1)
    assert "/static/uploads/" not in url, (
        "fonts must not live under the gated uploads tree")
