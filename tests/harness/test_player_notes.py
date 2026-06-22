"""Notes & Handouts — Phase 3: player public notes.

docs/plans/notes-and-handouts.md. Extends the `/notes` endpoints to
`kind="player_note"`, `visibility="public"`: any campaign member may
create a note visible to everyone, edit/delete their own (the GM may
moderate any public note), and changes broadcast a `note_updated` WS
event. `visibility="private"` is rejected until Phase 4 ships the
end-to-end encryption (no plaintext "private" notes).

GM = gm_client; alice/bob = non-GM members.
"""
import asyncio

import pytest_asyncio

from .conftest import CAMPAIGN_ID

_BASE = f"/api/campaign/{CAMPAIGN_ID}/notes"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_notes(gm_client):
    """The GM can see + delete every gm_note and public note, so a single
    GM sweep cleans up after each test."""
    yield
    resp = await gm_client.get(_BASE)
    if resp.status_code == 200:
        for n in resp.json().get("notes", []):
            await gm_client.delete(f"{_BASE}/{n['id']}")


async def test_player_creates_public_note(alice_client):
    r = await alice_client.post(_BASE, json={
        "visibility": "public", "title": "Party loot",
        "body": "3 gp, a silver ring"})
    assert r.status_code == 200, r.text
    n = r.json()["note"]
    assert n["kind"] == "player_note"
    assert n["visibility"] == "public"
    assert n["title"] == "Party loot"


async def test_public_note_visible_to_all(gm_client, alice_client, bob_client):
    c = await alice_client.post(_BASE, json={
        "visibility": "public", "title": "Shared clue"})
    nid = c.json()["note"]["id"]
    assert nid in [n["id"] for n in (await gm_client.get(_BASE)).json()["notes"]]
    assert nid in [n["id"] for n in (await bob_client.get(_BASE)).json()["notes"]]
    assert (await bob_client.get(f"{_BASE}/{nid}")).status_code == 200


async def test_author_can_edit_own_public(alice_client):
    c = await alice_client.post(_BASE, json={"visibility": "public",
                                             "title": "Draft"})
    nid = c.json()["note"]["id"]
    p = await alice_client.patch(f"{_BASE}/{nid}", json={"title": "Updated"})
    assert p.status_code == 200, p.text
    assert p.json()["note"]["title"] == "Updated"


async def test_gm_can_moderate_player_public(gm_client, alice_client):
    """The GM may edit/delete a player's public note (moderation)."""
    c = await alice_client.post(_BASE, json={"visibility": "public",
                                             "title": "Oops"})
    nid = c.json()["note"]["id"]
    p = await gm_client.patch(f"{_BASE}/{nid}", json={"title": "Moderated"})
    assert p.status_code == 200, p.text
    d = await gm_client.delete(f"{_BASE}/{nid}")
    assert d.status_code == 200, d.text


async def test_non_author_player_cannot_edit(alice_client, bob_client):
    c = await alice_client.post(_BASE, json={"visibility": "public",
                                             "title": "Alice's"})
    nid = c.json()["note"]["id"]
    p = await bob_client.patch(f"{_BASE}/{nid}", json={"title": "hijack"})
    assert p.status_code == 403, p.text


async def test_non_author_player_cannot_delete(alice_client, bob_client):
    c = await alice_client.post(_BASE, json={"visibility": "public",
                                             "title": "Alice's"})
    nid = c.json()["note"]["id"]
    d = await bob_client.delete(f"{_BASE}/{nid}")
    assert d.status_code == 403, d.text


async def test_author_can_delete_own(alice_client):
    c = await alice_client.post(_BASE, json={"visibility": "public",
                                             "body": "temp"})
    nid = c.json()["note"]["id"]
    d = await alice_client.delete(f"{_BASE}/{nid}")
    assert d.status_code == 200, d.text
    assert (await alice_client.get(f"{_BASE}/{nid}")).status_code == 404


async def test_private_not_available(alice_client):
    """visibility=private is rejected until Phase 4's encrypted client."""
    r = await alice_client.post(_BASE, json={
        "visibility": "private", "title": "secret", "body": "x"})
    assert r.status_code == 400, r.text


async def test_invalid_visibility_400(alice_client):
    r = await alice_client.post(_BASE, json={
        "visibility": "everyone", "title": "x"})
    assert r.status_code == 400, r.text


async def test_public_note_create_broadcasts_ws(alice_client, gm_ws, bob_ws):
    """Creating a public note broadcasts note_updated to all members."""
    gm_ws.mark()
    bob_ws.mark()
    c = await alice_client.post(_BASE, json={
        "visibility": "public", "title": "Broadcast me"})
    assert c.status_code == 200, c.text
    nid = c.json()["note"]["id"]
    gm_msg = await gm_ws.wait_for("note_updated")
    bob_msg = await bob_ws.wait_for("note_updated")
    assert gm_msg["data"]["note"]["id"] == nid
    assert bob_msg["data"]["note"]["id"] == nid
    assert bob_msg["data"]["note"]["title"] == "Broadcast me"


async def test_gm_note_ws_scoped_to_gms(gm_client, gm_ws, alice_ws):
    """A gm_note's note_updated reaches the GM's socket but NOT a
    player's — a player never even learns a gm_note changed."""
    gm_ws.mark()
    alice_ws.mark()
    c = await gm_client.post(_BASE, json={"title": "GM secret", "body": "x"})
    assert c.status_code == 200, c.text
    nid = c.json()["note"]["id"]
    gm_msg = await gm_ws.wait_for("note_updated")
    assert gm_msg["data"]["note"]["id"] == nid
    await asyncio.sleep(0.6)
    assert alice_ws.buffered("note_updated") == [], (
        f"player must not receive a gm_note event; "
        f"got {alice_ws.buffered('note_updated')}"
    )
