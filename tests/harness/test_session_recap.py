"""v2.885.0 — session recaps (schema v100).

Ending a session stamps a recap keyed by ``(campaign_id, session_key)``:
a GM nickname + GM-only notes, plus each player's own note. GM notes and
other players' notes are never returned to a player; a player only ever
sees the nickname + their own note.
"""
from __future__ import annotations

import httpx

BASE_URL = "http://localhost:8013"
CAMPAIGN_ID = 1
KEY = "harness-recap-key"

GM_EMAIL = "demo-gm@example.com"
PLAYER_EMAIL = "demo-alice@example.com"  # Alice is a member of campaign 1
PASSWORD = "demopass"


def _client(email: str):
    """A logged-in client as a context manager (login happens on __enter__
    via a fresh Client so the `with` block owns the open/close)."""
    import contextlib

    @contextlib.contextmanager
    def _cm():
        with httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=10.0) as c:
            r = c.post("/login", data={"email": email, "password": PASSWORD})
            assert r.status_code in (200, 303), r.status_code
            yield c

    return _cm()


def test_gm_sets_recap_and_reads_it_back():
    with _client(GM_EMAIL) as gm:
        r = gm.put(
            f"/api/campaign/{CAMPAIGN_ID}/session-recap/{KEY}",
            json={"nickname": "The Goblin Ambush", "gm_notes": "They fled north."},
        )
        assert r.status_code == 200, r.text
        assert r.json()["recap"]["nickname"] == "The Goblin Ambush"

        g = gm.get(f"/api/campaign/{CAMPAIGN_ID}/session-recap/{KEY}")
        assert g.status_code == 200, g.text
        body = g.json()
        assert body["exists"] is True
        assert body["nickname"] == "The Goblin Ambush"
        assert body["gm_notes"] == "They fled north."
        assert body["is_gm"] is True


def test_player_note_is_author_scoped_and_gm_sees_every_note():
    # A player writes their own note and sees only the nickname + their note.
    with _client(PLAYER_EMAIL) as alice:
        r = alice.put(
            f"/api/campaign/{CAMPAIGN_ID}/session-recap/{KEY}/my-note",
            json={"body": "I looted the chest."},
        )
        assert r.status_code == 200, r.text
        assert r.json()["body"] == "I looted the chest."

        g = alice.get(f"/api/campaign/{CAMPAIGN_ID}/session-recap/{KEY}")
        assert g.status_code == 200, g.text
        body = g.json()
        assert body["my_note"] == "I looted the chest."
        assert body["is_gm"] is False
        # GM-only content must NOT reach a player.
        assert "gm_notes" not in body, body
        assert "player_notes" not in body, body

    # The GM sees the player's note in the aggregated player_notes list.
    with _client(GM_EMAIL) as gm:
        g = gm.get(f"/api/campaign/{CAMPAIGN_ID}/session-recap/{KEY}")
        pnotes = g.json()["player_notes"]
        assert any(n["body"] == "I looted the chest." for n in pnotes), pnotes


def test_player_cannot_write_the_gm_recap():
    with _client(PLAYER_EMAIL) as alice:
        r = alice.put(
            f"/api/campaign/{CAMPAIGN_ID}/session-recap/{KEY}",
            json={"nickname": "hax", "gm_notes": "nope"},
        )
        assert r.status_code == 403, r.text


def test_invalid_session_key_rejected():
    with _client(GM_EMAIL) as gm:
        r = gm.get(f"/api/campaign/{CAMPAIGN_ID}/session-recap/{'x' * 65}")
        assert r.status_code == 400, r.text


def test_end_session_stamps_recap_and_returns_the_key():
    with _client(GM_EMAIL) as gm:
        # Start a session so session_started_at (→ session_key) is set.
        gm.post(f"/campaign/{CAMPAIGN_ID}/session/start")
        try:
            r = gm.post(
                f"/campaign/{CAMPAIGN_ID}/session/end",
                headers={"Accept": "application/json"},
                json={"nickname": "Ended via harness", "gm_notes": "gm secret"},
            )
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["ok"] is True
            key = data["session_key"]
            assert key, data

            g = gm.get(f"/api/campaign/{CAMPAIGN_ID}/session-recap/{key}")
            assert g.status_code == 200, g.text
            assert g.json()["nickname"] == "Ended via harness"
            assert g.json()["gm_notes"] == "gm secret"
        finally:
            # Restore an active session so we don't leave the demo tabletop
            # in the "waiting for GM" state for the next viewer/test.
            gm.post(f"/campaign/{CAMPAIGN_ID}/session/start")
