"""v2.1047.2 — a GIF token's ``src`` is not reassigned on every render.

``_updateGifOverlay`` (``tabletop.js``) keeps one DOM ``<img>`` per
animated-GIF token and guarded its ``src`` write with

    if (img.src !== t.image_url) img.src = t.image_url;

That comparison is **always true**: the ``src`` *property* getter returns
the resolved absolute URL (``http://host/static/uploads/tokens/x.gif``)
while ``t.image_url`` is root-relative (``/static/uploads/tokens/x.gif``).
So ``src`` was rewritten every call — and ``_updateGifOverlay`` runs at
the tail of every ``render()``, which has 60+ call sites (token drag,
pan, zoom, every inbound token WS update). Reassigning ``src`` re-runs
the HTML image-update algorithm, which restarts the GIF animation.

The fix compares ``img.getAttribute('src')`` — the literal value we set —
so the guard is stable. This test proves it the only way that actually
demonstrates the bug: it instruments the element's ``src`` setter, drives
real renders, and asserts **zero** writes after the initial one.

Needs uploads enabled (``DEMO_DISABLE_UPLOADS=false``) since the only way
to attach a GIF to a token is the upload endpoint; skips otherwise. Runs
against a token this test places and deletes, so the demo map — and the
visual-regression snapshots — are untouched.
"""
from __future__ import annotations

import base64

import httpx
import pytest
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, tabletop_url

# Smallest valid animated-ish GIF (1x1). Content doesn't matter — the
# code path keys off the ".gif" extension in the URL.
_GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


@pytest.fixture
def gif_token(gm_session_cookie, roster):
    """Place a token for a non-tokenized demo PC, give it a GIF image,
    yield its id, then delete it."""
    cookies = {gm_session_cookie["name"]: gm_session_cookie["value"]}
    with httpx.Client(base_url=BASE_URL, cookies=cookies, timeout=20.0) as c:
        # Garrik is deliberately outside the demo's tokenized-six lineup,
        # so placing him doesn't disturb the map the snapshots capture.
        # ``roster`` (conftest) is already keyed by character name.
        char = roster.get("Garrik Ironside")
        if not char:
            pytest.skip("demo roster has no Garrik Ironside")
        placed = c.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{char['id']}/place-token",
            json={"x": 700.0, "y": 700.0},
        )
        assert placed.status_code == 200, placed.text
        token_id = placed.json()["id"]
        try:
            up = c.post(
                f"/api/campaign/{CAMPAIGN_ID}/token/{token_id}/image",
                files={"image": ("anim.gif", _GIF, "image/gif")},
            )
            if up.status_code == 403:
                pytest.skip("uploads disabled on this stack")
            assert up.status_code == 200, up.text
            yield token_id, up.json()["image_url"]
        finally:
            c.delete(f"/api/campaign/{CAMPAIGN_ID}/tokens/{token_id}")


def test_gif_token_src_not_rewritten_on_every_render(
    gm_page: Page, gif_token, gm_session_cookie,
):
    token_id, image_url = gif_token
    gm_page.goto(tabletop_url())

    overlay_img = gm_page.locator("#gif-token-overlay img").first
    expect(overlay_img).to_have_count(1, timeout=10000)

    # The URL the element was given must be the ROOT-RELATIVE one — that's
    # the premise the guard rests on.
    attr = gm_page.evaluate(
        "() => document.querySelector('#gif-token-overlay img')"
        ".getAttribute('src')")
    assert attr == image_url, f"expected {image_url!r}, got {attr!r}"

    # Demonstrate WHY the old guard was broken: the property getter
    # resolves to an absolute URL, so `img.src !== t.image_url` could
    # never be false.
    resolved = gm_page.evaluate(
        "() => document.querySelector('#gif-token-overlay img').src")
    assert resolved != image_url, (
        "img.src unexpectedly equals the relative URL — the premise of "
        "this regression changed; re-check the guard in _updateGifOverlay")
    assert resolved.endswith(image_url), resolved

    initial_left = gm_page.evaluate(
        "() => document.querySelector('#gif-token-overlay img').style.left")

    # Instrument the setter, then drive real renders.
    gm_page.evaluate(
        """() => {
            const img = document.querySelector('#gif-token-overlay img');
            const desc = Object.getOwnPropertyDescriptor(
                HTMLImageElement.prototype, 'src');
            window.__srcWrites = 0;
            Object.defineProperty(img, 'src', {
                configurable: true,
                get() { return desc.get.call(this); },
                set(v) { window.__srcWrites++; desc.set.call(this, v); },
            });
        }"""
    )

    # Drive renders through the REAL path this bug fires on: a token
    # move broadcasts token_update over WS, and the client re-renders,
    # which tails into _updateGifOverlay(). Synthetic wheel events were
    # tried first and turned out not to reach render() at all, which made
    # an earlier draft of this test pass against the unfixed code.
    cookies = {gm_session_cookie["name"]: gm_session_cookie["value"]}
    with httpx.Client(base_url=BASE_URL, cookies=cookies, timeout=20.0) as c:
        for i in range(6):
            mv = c.post(
                f"/api/campaign/{CAMPAIGN_ID}/token/{token_id}/move",
                json={"x": 700.0 + (i + 1) * 70, "y": 700.0,
                      "override": True},
            )
            assert mv.status_code in (200, 409), mv.text
            gm_page.wait_for_timeout(200)
    gm_page.wait_for_timeout(600)

    # Sanity: the overlay actually re-ran (its position tracks the token),
    # so a zero-write result below means the guard held, not that
    # _updateGifOverlay never fired.
    moved_left = gm_page.evaluate(
        "() => document.querySelector('#gif-token-overlay img').style.left")
    assert moved_left != initial_left, (
        f"gif overlay never repositioned ({moved_left!r}) — _updateGifOverlay "
        "did not run, so this test would pass vacuously")

    writes = gm_page.evaluate("() => window.__srcWrites")
    assert writes == 0, (
        f"GIF token src was reassigned {writes}x across renders — the "
        "_updateGifOverlay guard is comparing the resolved property "
        "instead of the attribute again, which restarts the animation")
