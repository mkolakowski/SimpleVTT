"""Phase 2b UI smoke — the Homebrew Workshop panel.

The HTTP harness (`tests/harness/test_homebrew_fork_srd.py`) covers the
fork / edit / revert / list endpoint contracts. This Playwright test proves
the campaign-settings Workshop panel actually wires them up in the browser:
GM opens settings → Homebrew → Workshop, forks the SRD Fireball, the form
editor opens pre-filled with the spell's 8d6, the GM tweaks it to 12d6 and
saves, and the change is resolvable server-side. (Backend-green ≠ UI-green —
the v2.7.3 toast regression is why this companion exists.)

Cleanup deletes the forked variant via httpx so it doesn't linger in the
campaign's homebrew (it's a variant slug, so it never shadows the real
Fireball regardless).
"""
import json
import time

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


_LOGIN = {"email": "demo-gm@example.com", "password": "demopass"}


def _cleanup(ctype: str, slug: str) -> None:
    with httpx.Client(base_url=BASE_URL, follow_redirects=True) as c:
        c.post("/login", data=_LOGIN)
        c.delete(f"/api/campaign/{CAMPAIGN_ID}/homebrew/{ctype}/{slug}")


def _resolved_damage(ctype: str, slug: str):
    with httpx.Client(base_url=BASE_URL, follow_redirects=True) as c:
        c.post("/login", data=_LOGIN)
        r = c.get(f"/api/content/{ctype}/{slug}?campaign_id={CAMPAIGN_ID}")
        if r.status_code != 200:
            return None
        for a in (r.json().get("record") or {}).get("actions", []):
            if a.get("damage"):
                return a["damage"]
    return None


def test_workshop_fork_edit_save(gm_page: Page):
    page = gm_page
    forked_slug = None
    try:
        page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}/settings")
        # Activate Homebrew tab → Workshop sub-tab.
        page.click('.settings-tab[data-tab="homebrew"]')
        page.click('.settings-subtab[data-sub="workshop"]')
        expect(page.locator('#hbw-fork-btn')).to_be_visible()

        # Fork the SRD Fireball as a variant.
        page.select_option('#hbw-fork-type', 'spells')
        page.fill('#hbw-fork-slug', 'fireball')
        page.select_option('#hbw-fork-mode', 'variant')
        page.click('#hbw-fork-btn')

        # The form editor opens, pre-filled from the SRD record (8d6).
        expect(page.locator('#hbw-editor')).to_be_visible(timeout=8000)
        expect(page.locator('#hbw-ed-damage')).to_have_value('8d6', timeout=8000)
        forked_slug = json.loads(page.locator('#hbw-ed-raw').input_value())['slug']

        # Tweak the damage and save.
        page.fill('#hbw-ed-damage', '12d6')
        page.click('#hbw-save-btn')
        expect(page.locator('#hbw-status')).to_contain_text('Saved', timeout=8000)

        # The tweak is resolvable server-side for the campaign.
        time.sleep(0.4)
        assert _resolved_damage('spells', forked_slug) == '12d6', (
            f"expected the saved 12d6 tweak to resolve; got "
            f"{_resolved_damage('spells', forked_slug)!r}"
        )
    finally:
        if forked_slug:
            _cleanup('spells', forked_slug)
