"""v2.158.58 — Channel Divinity picker UI routing (Invoke Duplicity).

Sibling to test_channel_divinity_picker_ui.py (Vow of Enmity). That test
proves the *target-taking* dedicated CD branch; this proves the
*targetless* one: Invoke Duplicity (Trickery Cleric Lv 2+) routes to
/use_invoke_duplicity WITHOUT opening a target picker.

The "no target picker" assertion is the load-bearing distinguisher from
the Vow-of-Enmity branch: both take the v2.158.55 `_fireCDDedicated`
path, but only the vow opens `.target-picker-overlay`. Together the two
UI tests pin down both halves of the dispatch.

No demo PC is a Trickery Cleric, so — like the HTTP test
test_invoke_duplicity.py — this PATCHes Brother Tavik Stonebrow (Life
Domain) into Trickery Domain Lv 2 for the duration, then restores him.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, sheet_url

PC_NAME = "Brother Tavik Stonebrow"


def test_cd_picker_routes_invoke_duplicity(gm_page: Page, roster: dict) -> None:
    tavik = roster[PC_NAME]

    errors: list[str] = []
    gm_page.on("console", lambda m: errors.append(m.text)
               if (m.type == "error"
                   and "Failed to load resource" not in m.text) else None)

    posts: list[str] = []
    gm_page.on("request", lambda r: posts.append(r.url)
               if r.method == "POST" else None)

    gm_page.goto(sheet_url(tavik["id"]))

    # PATCH Tavik into Trickery Domain Lv 2 with a full CD pool + seed a
    # battle so the endpoint's _install_buff has live state. Mirrors
    # tests/harness/test_invoke_duplicity.py's fixture setup.
    cid_token = f"tok_ui_tavik_{tavik['id']}"
    gm_page.evaluate(
        """async ({base, cid, charId, token}) => {
            await fetch(base+'/api/campaign/'+cid+'/character/'+charId+'/sheet-fields', {
                method: 'PATCH', credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    class_slug: 'cleric', subclass: 'Trickery Domain', level: 2,
                    resources: [{
                        key: 'channel-divinity', name: 'Channel Divinity',
                        current: 2, max: 2, reset: 'short',
                        source: 'cleric Lv 2', class_slug: 'cleric',
                        subclass_slug: 'trickery', manual: false,
                        desc: 'Channel Divinity (Invoke Duplicity, Cloak of Shadows).',
                    }],
                }),
            });
            await fetch(base+'/api/campaign/'+cid+'/battle', {
                method: 'PUT', credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    combatants: [{
                        id: token, char_id: charId, name: 'Brother Tavik Stonebrow',
                        initiative: 10, hp_current: 60, hp_max: 60, buffs: [],
                        economy: {action: false, bonus: false, reaction: false, movement: 0},
                    }],
                    turn_index: 0, round: 1, active: true,
                }),
            });
        }""",
        {"base": BASE_URL, "cid": CAMPAIGN_ID, "charId": tavik["id"], "token": cid_token},
    )
    gm_page.reload()

    try:
        # 1. Open the Channel Divinity option picker.
        use_cd = gm_page.locator('.res-use[data-key="channel-divinity"]')
        expect(use_cd).to_be_visible(timeout=8000)
        use_cd.click()

        picker = gm_page.locator("#resource-option-picker")
        expect(picker).to_be_visible(timeout=5000)

        # 2. The subclass filter surfaces Invoke Duplicity for Trickery.
        dup_opt = picker.locator(".rop-opt", has_text="Invoke Duplicity")
        expect(dup_opt).to_be_visible()
        dup_opt.click()

        # 3. The option picker closes and NO target picker opens — the
        #    distinguisher from the Vow-of-Enmity branch (which would).
        expect(picker).to_have_count(0, timeout=5000)
        gm_page.wait_for_timeout(600)
        assert gm_page.locator(".target-picker-overlay").count() == 0, (
            "Invoke Duplicity is targetless — it must NOT open a target picker")

        # 4. It routed to the dedicated endpoint, not the generic announce.
        assert any("/use_invoke_duplicity" in u for u in posts), (
            f"expected a POST to /use_invoke_duplicity; saw {posts}")
        assert not any("/use_feature" in u for u in posts), (
            f"Invoke Duplicity must NOT route through /use_feature; saw {posts}")
        assert not errors, f"console errors firing the CD picker: {errors}"
    finally:
        # Restore Tavik to his demo default (Life Domain Lv 8) so the
        # shared seeded session isn't left mutated for later tests.
        gm_page.evaluate(
            """async ({base, cid, charId}) => {
                await fetch(base+'/api/campaign/'+cid+'/character/'+charId+'/sheet-fields', {
                    method: 'PATCH', credentials: 'include',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        class_slug: 'cleric', subclass: 'Life Domain', level: 8,
                        resources: [{
                            key: 'channel-divinity', name: 'Channel Divinity',
                            current: 2, max: 2, reset: 'short',
                            source: 'cleric Lv 2', class_slug: 'cleric',
                            subclass_slug: 'life', manual: false,
                            desc: 'Channel Divinity (Turn Undead, Preserve Life).',
                        }],
                    }),
                });
            }""",
            {"base": BASE_URL, "cid": CAMPAIGN_ID, "charId": tavik["id"]},
        )
