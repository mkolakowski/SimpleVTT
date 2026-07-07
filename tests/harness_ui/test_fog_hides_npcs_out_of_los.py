"""v2.956.0 — dynamic fog hides tokens that aren't in the player's CURRENT line
of sight. Exploration memory shows the remembered ground, not who is standing in
it now — so an NPC behind a closed door is hidden even after the party has been
in that room; opening the door (a walls change) reveals it again.
"""
from __future__ import annotations

from playwright.sync_api import Page

from .conftest import BASE_URL, CAMPAIGN_ID


def test_npc_hidden_out_of_los_even_when_explored(alice_page: Page) -> None:
    alice_page.goto(f"{BASE_URL}/campaign/{CAMPAIGN_ID}")
    alice_page.wait_for_function(
        "() => window.__testDrawFog && window.__tokenVisForTest && window.__fogCellForTest && window.ME",
        timeout=10000)

    r = alice_page.evaluate(
        """() => {
            const g = 70, myId = window.ME.id, fc = window.__fogCellForTest();
            const owned    = { id: 1, x: 900, y: 660, size: 1, controller_user_id: myId,
                               light_bright_ft: 0, light_dim_ft: 0 };
            const npcBehind = { id: 2, x: 900, y: 250, controller_user_id: myId + 9999 };  // above the wall
            const npcNear   = { id: 3, x: 900, y: 720, controller_user_id: myId + 9999 };  // below, near me
            const cellOf = (t) => [Math.floor((t.x + g/2)/fc), Math.floor((t.y + g/2)/fc)];
            // A full-width wall between me (below) and the NPC (above), and mark
            // the NPC's ground as already explored (the party has been there).
            window.__testDrawFog({
                dynamic: true,
                walls: [{ x1: 0, y1: 600, x2: 4000, y2: 600 }],
                tokens: [owned, npcBehind, npcNear],
                explored: [cellOf(npcBehind)],
            });
            const V = window.__tokenVisForTest;
            const closed = { behind: V.hidden(npcBehind), near: V.hidden(npcNear), own: V.hidden(owned) };
            // Open the way (remove the wall) → walls change recomputes vision.
            window._setMapWalls([]);
            const opened = { behind: V.hidden(npcBehind) };
            return { closed, opened };
        }"""
    )
    # Door closed: the NPC behind it is hidden despite the room being explored;
    # the NPC in my line of sight and my own token are shown.
    assert r["closed"]["behind"] is True, r
    assert r["closed"]["near"] is False, r
    assert r["closed"]["own"] is False, r
    # Door opened (wall removed → vision recomputed): the NPC is revealed.
    assert r["opened"]["behind"] is False, r
