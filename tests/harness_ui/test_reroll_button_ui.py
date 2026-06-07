"""v2.106.0 — reroll button on roll-log cards (Phase 2).

The server attaches `reroll_options` to the `/roll` broadcast; the
client renders a per-option button on the card for the GM + the roller,
greyed when out of uses and absent when the character has no reroll
feature. Clicking confirms, POSTs /use_reroll, and disables the button.
These are pure client concerns the HTTP+WS harness can't see (no DOM);
the server endpoint is covered by tests/harness/test_use_reroll.py.

Demo fixture: Garrik Ironside (Fighter Lv 9) has the Lucky feat;
Pip Quickfingers (Rogue) does not.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _wait_ready(page: Page) -> None:
    expect(page.locator("#vtt-canvas")).to_be_visible(timeout=8000)
    page.wait_for_function(
        "() => typeof window.vttGetCharacters === 'function'", timeout=5000,
    )


def _long_rest(page: Page, char_id: int) -> None:
    page.evaluate(
        """async ({base, cid, charId}) => {
            await fetch(base+'/api/campaign/'+cid+'/character/'+charId+'/rest', {
                method: 'POST', credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({type: 'long'}),
            });
        }""",
        {"base": BASE_URL, "cid": CAMPAIGN_ID, "charId": char_id},
    )


def _roll(page: Page, char_id: int, expr: str = "1d20") -> None:
    page.evaluate(
        """async ({base, cid, charId, expr}) => {
            await fetch(base+'/api/campaign/'+cid+'/roll', {
                method: 'POST', credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({expression: expr, character_id: charId,
                                      note: 'reroll-ui'}),
            });
        }""",
        {"base": BASE_URL, "cid": CAMPAIGN_ID, "charId": char_id, "expr": expr},
    )


def test_gm_sees_and_uses_lucky_reroll_button(gm_page: Page, roster: dict) -> None:
    garrik = roster["Garrik Ironside"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_ready(gm_page)
    _long_rest(gm_page, garrik["id"])  # guarantee 3 luck points

    _roll(gm_page, garrik["id"])
    btn = gm_page.locator("#roll-list .reroll-btn").last
    expect(btn).to_be_visible(timeout=5000)
    assert "Lucky" in btn.inner_text()
    expect(btn).to_be_enabled()

    # Confirm dialog → accept, then click.
    gm_page.on("dialog", lambda d: d.accept())
    btn.click()
    # The clicked button disables (the use is spent); a reroll result
    # card with the "Lucky reroll" note lands via the WS rebroadcast.
    expect(btn).to_be_disabled(timeout=5000)
    expect(
        gm_page.locator("#roll-list .roll-card-note", has_text="Lucky reroll").last
    ).to_be_visible(timeout=5000)


def test_no_reroll_button_without_feature(gm_page: Page, roster: dict) -> None:
    """Pip (no Lucky feat) → the roll card carries no reroll button."""
    pip = roster["Pip Quickfingers"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_ready(gm_page)

    # Count reroll buttons before + after a Pip roll: unchanged.
    before = gm_page.locator("#roll-list .reroll-btn").count()
    _roll(gm_page, pip["id"])
    # Wait for the roll card to land (a new note row), then assert no
    # new reroll button appeared.
    gm_page.wait_for_timeout(600)
    after = gm_page.locator("#roll-list .reroll-btn").count()
    assert after == before, (
        f"Pip has no reroll feature, so no reroll button should appear "
        f"(before={before}, after={after})"
    )
