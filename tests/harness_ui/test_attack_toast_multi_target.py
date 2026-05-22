"""v2.49.93 — chat-card multi-target rendering.

When ``/attack`` fires with ``target_combatant_ids: [a, b, c]`` the
server's ``weapon_attack`` broadcast carries an ``auto_attack_targets``
array with one entry per target (set up in v2.49.85). The chat card
(``roll_toast.js``'s ``weapon_attack`` handler) used to read only the
primary target's top-level fields, so the additional targets never
rendered a toast. v2.49.93 fans the chain out: one attack + one damage
toast per per-target outcome, staggered 700 ms apart so they don't
pile on top of each other.

This suite navigates the tabletop as the GM, seeds a battle with three
bandits via the existing REST surface, fires a multi-target attack
against all three, and asserts that all three bandit names show up
across the rendered ``.roll-toast`` elements. Backward-compat single-
target coverage already lives in ``test_attack_toast.py``.
"""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID


def _gm_http_client() -> httpx.Client:
    """Logged-in synchronous httpx client for REST-side setup. Caller
    owns the close() call — don't use ``with`` since the constructor
    already opened the underlying transport (httpx 0.27 raises if you
    try to re-enter via __enter__)."""
    client = httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0)
    resp = client.post("/login", data={"email": "demo-gm@example.com", "password": "demopass"})
    assert resp.status_code in (200, 303), f"login failed: {resp.status_code}"
    return client


def _clear_battle(client: httpx.Client) -> None:
    """Reset the campaign battle to inactive with no combatants. The
    sheet's ``.atk-strike`` handler pops the target-picker modal when
    there are combatants to choose from; without this teardown, every
    subsequent test that doesn't pre-set a target hangs in that modal.
    """
    client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 0, "active": False},
    )


def _seed_three_bandit_battle(client: httpx.Client, roster: dict) -> dict:
    """PUT the battle into a known state with Pip + three bandits, all
    on full HP. Returns the combatant IDs we'll target."""
    templates = client.get(f"/api/campaign/{CAMPAIGN_ID}/templates").json()
    bandit = next(t for t in templates if t["name"].lower() == "bandit")
    pip = roster["Pip Quickfingers"]
    combatants = [
        {
            "id": f"tok_ct_pip_{pip['id']}",
            "char_id": pip["id"],
            "name": pip["name"],
            "initiative": 10,
            "hp_current": 30,
            "hp_max": 30,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        },
        {
            "id": "tok_ct_b1",
            "char_id": None,
            "token_template_id": bandit["id"],
            "name": "Bandit Alpha",
            "initiative": 7,
            "hp_current": 30,
            "hp_max": 30,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        },
        {
            "id": "tok_ct_b2",
            "char_id": None,
            "token_template_id": bandit["id"],
            "name": "Bandit Beta",
            "initiative": 6,
            "hp_current": 30,
            "hp_max": 30,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        },
        {
            "id": "tok_ct_b3",
            "char_id": None,
            "token_template_id": bandit["id"],
            "name": "Bandit Gamma",
            "initiative": 5,
            "hp_current": 30,
            "hp_max": 30,
            "buffs": [],
            "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
        },
    ]
    resp = client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0, "round": 1, "active": True},
    )
    assert resp.status_code == 200, resp.text
    return {"pip": pip, "bandit_ids": ["tok_ct_b1", "tok_ct_b2", "tok_ct_b3"]}


def test_multi_target_attack_renders_one_toast_chain_per_target(gm_page: Page, roster: dict):
    """3-target attack → at least 3 distinct target names appear across
    the rendered ``.roll-toast`` elements. The pre-v2.49.93 behavior
    would have shown the toast for ONLY the primary target (Bandit
    Alpha) — the secondary + tertiary names would be absent.
    """
    client = _gm_http_client()
    try:
        setup = _seed_three_bandit_battle(client, roster)

        # Open the tabletop so roll_toast.js's WS listener is live. The
        # broadcast arrives via the /ws/campaign/{cid} subscription that
        # tabletop.js opens during its IIFE.
        gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
        expect(gm_page.locator("#vtt-canvas")).to_be_visible(timeout=8000)
        gm_page.wait_for_function(
            "() => typeof window.vttGetCharacters === 'function'",
            timeout=5000,
        )
        # Give the WS connection a beat to finish handshaking; the
        # roll_toast container is created lazily on the first toast, so we
        # can't probe for that yet — just sleep briefly.
        gm_page.wait_for_timeout(400)

        # Fire the multi-target attack via /attack. Posting in the
        # browser context so the WS broadcast reaches THIS page (the hub
        # fans out per-campaign, so it would land regardless of who
        # POSTed; routing inside the page is what we're testing).
        attack_resp = gm_page.evaluate(
            """async (params) => {
                const r = await fetch('/api/campaign/' + params.cid + '/attack', {
                    method: 'POST',
                    credentials: 'include',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        character_id: params.pipId,
                        attack_index: 0,
                        target_combatant_ids: params.targetIds,
                        override: true,
                    }),
                });
                return {status: r.status, body: await r.text()};
            }""",
            {"cid": CAMPAIGN_ID, "pipId": setup["pip"]["id"], "targetIds": setup["bandit_ids"]},
        )
        assert attack_resp["status"] == 200, f"attack failed: {attack_resp}"

        # The attack chain renders one .roll-toast per target's d20, then
        # 1600ms later the matching damage toast. With 3 targets staggered
        # 700ms apart, the last damage toast lands at ~(2*700)+1600 = 3000
        # ms. Wait for at least 3 toasts to appear.
        expect(gm_page.locator(".roll-toast")).to_have_count(6, timeout=5000)

        # Now scrape every toast's label and assert each bandit name shows
        # up at least once across the chain.
        labels = gm_page.evaluate(
            "() => Array.from(document.querySelectorAll('.roll-toast .rt-label')).map(el => el.textContent)"
        )
        joined = " | ".join(labels)
        for name in ("Bandit Alpha", "Bandit Beta", "Bandit Gamma"):
            assert name in joined, (
                f"Expected target name {name!r} in roll toasts, got: {joined!r}. "
                f"Multi-target chat-card rendering didn't fan out — only the primary "
                f"target's toasts appeared."
            )
    finally:
        # Always restore battle state so the next test in the suite
        # (e.g. the sheet-side .atk-strike click tests in
        # test_attack_toast.py) doesn't trigger the target-picker
        # modal off our left-behind combatants.
        _clear_battle(client)
        client.close()


def test_single_target_attack_still_renders_one_chain(gm_page: Page, roster: dict):
    """Backward-compat smoke: when ``target_combatant_ids`` has one
    entry (legacy single-target path), only ONE chain of toasts fires
    — same as the pre-v2.49.93 behavior. Guards against the refactor
    accidentally double-rendering on the single-target path.
    """
    client = _gm_http_client()
    try:
        setup = _seed_three_bandit_battle(client, roster)

        gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
        expect(gm_page.locator("#vtt-canvas")).to_be_visible(timeout=8000)
        gm_page.wait_for_function("() => typeof window.vttGetCharacters === 'function'", timeout=5000)
        gm_page.wait_for_timeout(400)

        attack_resp = gm_page.evaluate(
            """async (params) => {
                const r = await fetch('/api/campaign/' + params.cid + '/attack', {
                    method: 'POST',
                    credentials: 'include',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        character_id: params.pipId,
                        attack_index: 0,
                        target_combatant_id: params.targetIds[0],
                        override: true,
                    }),
                });
                return {status: r.status, body: await r.text()};
            }""",
            {"cid": CAMPAIGN_ID, "pipId": setup["pip"]["id"], "targetIds": setup["bandit_ids"]},
        )
        assert attack_resp["status"] == 200

        # Single-target = 2 toasts (attack + damage). Wait for both.
        expect(gm_page.locator(".roll-toast")).to_have_count(2, timeout=4000)
        # Only the primary target's name should appear.
        labels = gm_page.evaluate(
            "() => Array.from(document.querySelectorAll('.roll-toast .rt-label')).map(el => el.textContent)"
        )
        joined = " | ".join(labels)
        assert "Bandit Alpha" in joined, f"primary target missing: {joined}"
        assert "Bandit Beta" not in joined, (
            f"secondary target should NOT appear in single-target path: {joined}"
        )
    finally:
        _clear_battle(client)
        client.close()
