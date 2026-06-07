"""v2.100.6 — the GM client hydrates the in-memory hub battle from its
localStorage state on page load.

Regression context: the hub's battle map (`realtime.Hub._battle`) is
in-memory only and never persisted to the DB. After an app restart or
a demo reset it's empty until the GM next MUTATES the battle (the only
trigger for pushBattle). Every server-side battle read — OA detection,
the over-speed gate, reaction-prompt routing — goes through the hub, so
an un-hydrated hub silently disabled all of them: the GM saw their init
tracker (rendered from localStorage) but dragging an NPC past a PC
fired no opportunity attack because the server believed no battle
existed. v2.100.6 pushes the GM's localStorage battle to the hub once
on load.

This test is the end-to-end proof: it EMPTIES the hub, loads the GM
page with a battle in localStorage, and asserts the server's OA preview
(which reads the hub) now sees the seeded watcher — i.e. the hub was
re-hydrated by the page load alone, with no GM interaction.
"""
from __future__ import annotations

import json

from playwright.sync_api import Page, expect

from .conftest import BASE_URL, CAMPAIGN_ID

BATTLE_KEY = f"simplevtt_battle_{CAMPAIGN_ID}"


def _wait_ready(page: Page) -> None:
    expect(page.locator("#vtt-canvas")).to_be_visible(timeout=8000)
    page.wait_for_function(
        "() => typeof window.vttGetCharacters === 'function'", timeout=5000,
    )


def _eval(page: Page, fn: str, arg=None):
    return page.evaluate(fn, arg)


def test_gm_load_hydrates_hub_battle(gm_page: Page, roster: dict) -> None:
    pip = roster["Pip Quickfingers"]
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_ready(gm_page)

    # Place Pip (PC watcher) + an NPC mover one cell apart.
    tokens = _eval(gm_page, """async (cid) => {
        const r = await fetch('/api/campaign/'+cid+'/tokens', {credentials:'include'});
        return (await r.json()).tokens || [];
    }""", CAMPAIGN_ID)
    pip_tok = next(t for t in tokens if t.get("character_id") == pip["id"])
    bandit_tok = next(t for t in tokens if (t.get("label") or "").startswith("Bandit"))
    for tid, x in ((pip_tok["id"], 280.0), (bandit_tok["id"], 350.0)):
        _eval(gm_page, """async ({cid,tid,x}) => {
            await fetch('/api/campaign/'+cid+'/token/'+tid+'/move', {
                method:'POST', credentials:'include',
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify({x, y:280, override:true}),
            });
        }""", {"cid": CAMPAIGN_ID, "tid": tid, "x": x})

    # Seed the GM's localStorage with a live battle (Pip watcher + the
    # NPC mover), then EMPTY the hub to simulate a post-restart / reset
    # server with no in-memory battle.
    battle = {
        "combatants": [
            {"name": bandit_tok["label"], "id": "npc-h1", "init": 15,
             "team": "villain", "source_token_id": bandit_tok["id"],
             "token_template_id": bandit_tok.get("token_template_id"),
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            {"char_id": pip["id"], "name": pip["name"], "id": "pip-h1", "init": 12,
             "team": "hero", "source_token_id": pip_tok["id"],
             "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
        ],
        "turn_index": 0, "round": 1, "active": True,
    }
    _eval(gm_page, "([k, v]) => localStorage.setItem(k, v)",
          [BATTLE_KEY, json.dumps(battle)])
    _eval(gm_page, """async (cid) => {
        await fetch('/api/campaign/'+cid+'/battle', {
            method:'PUT', credentials:'include',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({combatants: [], round: 0, turn_index: 0, active: false}),
        });
    }""", CAMPAIGN_ID)

    # Sanity: with the hub empty, the OA preview sees no watchers.
    pre = _eval(gm_page, """async ({cid,tid}) => {
        const r = await fetch('/api/campaign/'+cid+'/token/'+tid+'/preview_move', {
            method:'POST', credentials:'include',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({x:700, y:280}),
        });
        return await r.json();
    }""", {"cid": CAMPAIGN_ID, "tid": bandit_tok["id"]})
    assert pre.get("would_trigger_oa") is False, (
        f"precondition failed — hub not empty before reload: {pre}"
    )

    # Reload: the v2.100.6 hydrate should push localStorage → hub.
    gm_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    _wait_ready(gm_page)
    gm_page.wait_for_timeout(500)  # debounced pushBattle (150ms) + fetch

    post = _eval(gm_page, """async ({cid,tid}) => {
        const r = await fetch('/api/campaign/'+cid+'/token/'+tid+'/preview_move', {
            method:'POST', credentials:'include',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({x:700, y:280}),
        });
        return await r.json();
    }""", {"cid": CAMPAIGN_ID, "tid": bandit_tok["id"]})
    try:
        assert post.get("would_trigger_oa") is True, (
            f"hub was NOT hydrated on GM load — OA preview still empty: {post}"
        )
        watchers = [t.get("watcher_char_id") for t in post.get("triggers", [])]
        assert pip["id"] in watchers, (
            f"hydrated hub should surface Pip as an OA watcher; got {post.get('triggers')}"
        )
    finally:
        _eval(gm_page, """async (cid) => {
            await fetch('/api/campaign/'+cid+'/battle', {
                method:'PUT', credentials:'include',
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify({combatants: [], round: 0, turn_index: 0, active: false}),
            });
        }""", CAMPAIGN_ID)
        _eval(gm_page, "(k) => localStorage.removeItem(k)", BATTLE_KEY)
