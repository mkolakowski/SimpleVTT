"""v2.1021.0 — Burnt Manuscript theme.

A near-black warm ground with faded, smoke-dimmed sepia highlights —
the darker sepia variant that completes the "darker sepia themes"
UI/Mobile TODO (alongside the existing `sepia` = deep parchment and
`hearthstone` = candlelit tavern). Purely additive: a new
`[data-theme="burnt-manuscript"]` CSS block, a `VALID_THEMES` key, and
a theme-picker card.

Tests:
  - `POST /api/settings/theme {theme: "burnt-manuscript"}` → 200 (the
    key is in VALID_THEMES); an unknown theme → 400.
  - The CSS block + the picker card ship in the static/template assets.
"""
import httpx

from .conftest import CAMPAIGN_ID  # noqa: F401 (imported for parity)
from .helpers import BASE_URL


async def test_burnt_manuscript_theme_accepted(gm_client):
    """The new theme key is accepted by the settings endpoint; restore
    to a safe default afterward so the GM's theme isn't left changed."""
    r = await gm_client.post(
        "/api/settings/theme", json={"theme": "burnt-manuscript"},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("theme") == "burnt-manuscript"
    # Restore.
    r2 = await gm_client.post("/api/settings/theme", json={"theme": "dark"})
    assert r2.status_code == 200, r2.text


async def test_invalid_theme_rejected(gm_client):
    r = await gm_client.post(
        "/api/settings/theme", json={"theme": "not-a-real-theme"},
    )
    assert r.status_code == 400, r.text


async def test_burnt_manuscript_css_block_present():
    """The theme's CSS variables ship in the fantasy-themes stylesheet."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.get("/static/style-fantasy-themes.css")
    assert r.status_code == 200, r.text
    assert '[data-theme="burnt-manuscript"]' in r.text
    # A representative token from the block.
    assert "#0d0b08" in r.text


async def test_burnt_manuscript_picker_card_present(gm_client):
    """The settings theme picker renders a Burnt Manuscript card."""
    r = await gm_client.get("/settings")
    assert r.status_code == 200, r.text
    assert 'data-theme="burnt-manuscript"' in r.text
    assert "Burnt Manuscript" in r.text
