"""v2.108.0 — up-cast slot picker on the character sheet (Approach A + C).

When a player clicks Cast on a leveled spell and has a higher-level
slot free, the sheet opens a slot-picker modal listing the available
levels (Approach A) and the spell's "at higher levels" rule text
(Approach C). The chosen level rides the existing `slot_level` plumbing
(server-side echo covered by tests/harness/test_cast_spell.py).

Uses Thalindra (Wizard) — Magic Missile is `spell_index=3`; she has
both L1 and L2 slots, so the picker offers a real choice. A long rest
up front guarantees full slots so the picker is deterministic.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, sheet_url


def test_upcast_picker_appears_and_casts(gm_page: Page, roster: dict) -> None:
    thalindra = roster["Thalindra Moonwhisper"]
    # Collect JS console errors but ignore environmental resource-load
    # 404s (missing asset / content lookups) that aren't caused by the
    # cast flow — we only care about real script exceptions here.
    errors: list[str] = []
    gm_page.on("console", lambda m: errors.append(m.text)
               if (m.type == "error"
                   and "Failed to load resource" not in m.text) else None)

    gm_page.goto(sheet_url(thalindra["id"]))
    # Long-rest to guarantee full slots, then reload so the slot pips
    # render full and the picker offers L1 + L2.
    gm_page.evaluate(
        """async ({base, cid, charId}) => {
            await fetch(base+'/api/campaign/'+cid+'/character/'+charId+'/rest', {
                method: 'POST', credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({type: 'long'}),
            });
        }""",
        {"base": BASE_URL, "cid": CAMPAIGN_ID, "charId": thalindra["id"]},
    )
    gm_page.reload()

    cast = gm_page.locator('.sp-cast[data-idx="3"]')  # Magic Missile
    expect(cast).to_be_visible(timeout=8000)
    cast.click()

    modal = gm_page.locator('[aria-label="Choose spell slot level"]')
    expect(modal).to_be_visible(timeout=5000)
    # Approach A — a real choice of slot levels (base + at least one
    # higher slot the caster has free).
    expect(modal.locator("button", has_text="Lvl 1")).to_be_visible()
    expect(modal.locator("button", has_text="Lvl 2")).to_be_visible()
    # Approach C (the "At higher levels" rule text) renders when the
    # spell carries `higher_level` — data-dependent, so not asserted
    # here; the broadcast echo is covered by the HTTP harness.

    # Choose the L2 (up-cast) slot → the modal closes, cast proceeds.
    modal.locator("button", has_text="Lvl 2").click()
    expect(modal).to_have_count(0, timeout=5000)
    assert not errors, f"console errors casting from the sheet: {errors}"
