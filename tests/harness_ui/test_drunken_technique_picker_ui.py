"""v2.158.62 — Drunken Technique class-features button UI routing.

The HTTP harness (test_drunken_technique.py, test_demo_drunken_monk.py)
proves the /use_drunken_technique endpoint contract; this browser test
proves the *frontend wiring* that v2.158.61 added: clicking the Drunken
Technique "Use" button in the class-features list POSTs
/use_drunken_technique, NOT the generic /use_feature announce.

Unlike Form of the Beast (which opens a Bite/Claws/Tail picker), Drunken
Technique has no options — clicking the button fires the dedicated
endpoint directly. Like all class-features buttons it lives in a
collapsed .cf-body row (display:none by default), so the test expands
the row first.

Uses Quan Reelstep (the seeded Way of the Drunken Master Lv 5 Monk from
v2.158.62), whose class_features list carries a "drunken-technique"
entry. A server-side battle is seeded so the buff install returns a
clean 200.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, sheet_url

PC_NAME = "Quan Reelstep"


def test_cf_button_routes_drunken_technique(gm_page: Page, roster: dict) -> None:
    pc = roster[PC_NAME]

    errors: list[str] = []
    gm_page.on("console", lambda m: errors.append(m.text)
               if (m.type == "error"
                   and "Failed to load resource" not in m.text) else None)

    # Capture POSTs so we can prove the click hit the dedicated endpoint
    # (the contract under test) rather than the generic /use_feature.
    posts: list[str] = []
    gm_page.on("request", lambda r: posts.append(r.url)
               if r.method == "POST" else None)

    gm_page.goto(sheet_url(pc["id"]))

    # Seed a one-combatant server-side battle so the buff install (which
    # requires an active battle) returns a clean 200 — keeps the console
    # error-free under shared-DB contention.
    gm_page.evaluate(
        """async ({base, cid, charId}) => {
            await fetch(base+'/api/campaign/'+cid+'/battle', {
                method: 'PUT', credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    combatants: [{
                        id: 'tok_ui_'+charId, char_id: charId,
                        name: 'Quan Reelstep', initiative: 12,
                        hp_current: 38, hp_max: 38, buffs: [],
                        economy: {action: false, bonus: false,
                                  reaction: false, movement: 0},
                    }],
                    turn_index: 0, round: 1, active: true,
                }),
            });
        }""",
        {"base": BASE_URL, "cid": CAMPAIGN_ID, "charId": pc["id"]},
    )
    gm_page.reload()

    # 1. Expand the Drunken Technique class-features row (its .cf-body is
    #    display:none by default) so the Use button becomes clickable.
    row = gm_page.locator(
        '.cf-row:has(.cf-use[data-feature="drunken-technique"])')
    expect(row).to_have_count(1, timeout=8000)
    row.locator(".cf-header").click()

    dt_btn = row.locator('.cf-use[data-feature="drunken-technique"]')
    expect(dt_btn).to_be_visible(timeout=5000)
    dt_btn.click()

    # 2. No picker — the click POSTs the dedicated endpoint directly,
    #    never /use_feature.
    gm_page.wait_for_timeout(600)
    assert any("/use_drunken_technique" in u for u in posts), (
        f"expected a POST to /use_drunken_technique; saw {posts}")
    assert not any("/use_feature" in u for u in posts), (
        f"Drunken Technique must NOT route through /use_feature; saw {posts}")
    assert not errors, f"console errors firing Drunken Technique: {errors}"
