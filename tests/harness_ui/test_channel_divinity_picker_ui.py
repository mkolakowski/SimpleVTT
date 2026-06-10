"""v2.158.57 — Channel Divinity picker UI routing (Vow of Enmity).

The HTTP harness (test_vow_of_enmity*.py, test_demo_vengeance_paladin.py)
proves the /use_vow_of_enmity endpoint contract; this browser test proves
the *frontend wiring* that v2.158.55 added: clicking the Channel Divinity
resource-pill "Use" button opens the option picker, the subclass filter
surfaces "Vow of Enmity" for a Vengeance Paladin, and picking it takes the
dedicated _fireCDDedicated path — i.e. it opens the target picker and POSTs
/use_vow_of_enmity, NOT the generic /use_feature announce.

The target-picker step is the load-bearing distinguisher: a generic CD
option (Sacred Weapon, Turn the Unholy, etc.) never opens a target picker,
so its appearance proves the Vow-of-Enmity branch fired.

Uses Dame Seraphine Vael (the seeded Oath of Vengeance Lv 3 Paladin from
v2.158.56). CD is PATCHed full + a one-combatant battle is seeded into
localStorage so the picker is deterministic under shared-DB contention.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID, sheet_url

PC_NAME = "Dame Seraphine Vael"


def test_cd_picker_routes_vow_of_enmity(gm_page: Page, roster: dict) -> None:
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

    # Reset CD to a full charge (idempotent across the shared seeded
    # session) and seed a one-combatant battle into localStorage so the
    # Vow-of-Enmity target picker has a real row to tap.
    gm_page.evaluate(
        """async ({base, cid, charId}) => {
            await fetch(base+'/api/campaign/'+cid+'/character/'+charId+'/sheet-fields', {
                method: 'PATCH', credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    class_slug: 'paladin',
                    resources: [{
                        key: 'channel-divinity', name: 'Channel Divinity',
                        current: 1, max: 1, reset: 'short',
                        source: 'paladin Lv 3', class_slug: 'paladin',
                        subclass_slug: 'vengeance', manual: false,
                        desc: 'Channel an oath effect (Abjure Enemy, Vow of Enmity).',
                    }],
                }),
            });
            localStorage.setItem('simplevtt_battle_'+cid, JSON.stringify({
                combatants: [
                    {id: 'tok_ui_'+charId, char_id: charId, name: 'Dame Seraphine Vael',
                     hp_current: 28, hp_max: 28},
                    {id: 'tok_ui_bandit', char_id: null, name: 'Bandit Quarry',
                     hp_current: 50, hp_max: 50},
                ],
            }));
        }""",
        {"base": BASE_URL, "cid": CAMPAIGN_ID, "charId": pc["id"]},
    )
    gm_page.reload()

    # 1. Open the Channel Divinity option picker.
    use_cd = gm_page.locator('.res-use[data-key="channel-divinity"]')
    expect(use_cd).to_be_visible(timeout=8000)
    use_cd.click()

    picker = gm_page.locator("#resource-option-picker")
    expect(picker).to_be_visible(timeout=5000)

    # 2. The subclass filter surfaces Vow of Enmity for the Vengeance oath.
    vow_opt = picker.locator(".rop-opt", has_text="Vow of Enmity")
    expect(vow_opt).to_be_visible()
    vow_opt.click()

    # 3. The dedicated path opened the target picker — a generic CD option
    #    never does, so this proves the Vow-of-Enmity branch fired.
    target_picker = gm_page.locator(".target-picker-overlay")
    expect(target_picker).to_be_visible(timeout=5000)

    # 4. Tap the Bandit row → the picker resolves single-tap (allowMulti
    #    false) and the dedicated endpoint POST fires.
    bandit_row = target_picker.locator(
        '.target-picker-row[data-cid="tok_ui_bandit"]')
    expect(bandit_row).to_be_visible()
    bandit_row.click()

    gm_page.wait_for_timeout(600)
    assert any("/use_vow_of_enmity" in u for u in posts), (
        f"expected a POST to /use_vow_of_enmity; saw {posts}")
    assert not any("/use_feature" in u for u in posts), (
        f"Vow of Enmity must NOT route through /use_feature; saw {posts}")
    assert not errors, f"console errors firing the CD picker: {errors}"
