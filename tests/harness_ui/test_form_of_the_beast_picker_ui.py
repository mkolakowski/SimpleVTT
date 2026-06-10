"""v2.158.60 — Form of the Beast class-features button UI routing.

The HTTP harness (test_form_of_the_beast.py, test_demo_beast_barbarian.py)
proves the /use_form_of_the_beast endpoint contract; this browser test
proves the *frontend wiring* that v2.158.59 added: clicking the Form of
the Beast "Use" button in the class-features list opens the form picker
(Bite / Claws / Tail), and picking a form POSTs /use_form_of_the_beast,
NOT the generic /use_feature announce.

Unlike the Channel Divinity tests (which click a directly-visible
resource pill), the Form of the Beast button lives in a collapsed
class-features row whose .cf-body is display:none by default — so the
test expands the row first, then clicks the Use button.

Uses Brakka Wildmane (the seeded Path of the Beast Lv 5 Barbarian from
v2.158.60), whose class_features list carries a "form-of-the-beast"
entry. A server-side battle is seeded so the buff install returns a
clean 200.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, sheet_url

PC_NAME = "Brakka Wildmane"


def test_cf_button_routes_form_of_the_beast(gm_page: Page, roster: dict) -> None:
    pc = roster[PC_NAME]

    errors: list[str] = []
    gm_page.on("console", lambda m: errors.append(m.text)
               if (m.type == "error"
                   and "Failed to load resource" not in m.text) else None)

    # Capture POSTs so we can prove the picker hit the dedicated endpoint
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
                        name: 'Brakka Wildmane', initiative: 12,
                        hp_current: 55, hp_max: 55, buffs: [],
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

    # 1. Expand the Form of the Beast class-features row (its .cf-body is
    #    display:none by default) so the Use button becomes clickable.
    row = gm_page.locator(
        '.cf-row:has(.cf-use[data-feature="form-of-the-beast"])')
    expect(row).to_have_count(1, timeout=8000)
    row.locator(".cf-header").click()

    fotb_btn = row.locator('.cf-use[data-feature="form-of-the-beast"]')
    expect(fotb_btn).to_be_visible(timeout=5000)
    fotb_btn.click()

    # 2. The dedicated wiring opens the form picker (Bite / Claws / Tail).
    picker = gm_page.locator("#resource-option-picker")
    expect(picker).to_be_visible(timeout=5000)

    claws_opt = picker.locator(".rop-opt", has_text="Claws")
    expect(claws_opt).to_be_visible()
    claws_opt.click()

    # 3. Picking a form POSTs the dedicated endpoint, never /use_feature.
    gm_page.wait_for_timeout(600)
    assert any("/use_form_of_the_beast" in u for u in posts), (
        f"expected a POST to /use_form_of_the_beast; saw {posts}")
    assert not any("/use_feature" in u for u in posts), (
        f"Form of the Beast must NOT route through /use_feature; saw {posts}")
    assert not errors, f"console errors firing the Form of the Beast picker: {errors}"
