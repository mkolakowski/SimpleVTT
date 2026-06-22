"""Notes & Handouts — Phase 1: GM prep notes.

docs/plans/notes-and-handouts.md. Covers the `campaign_notes` CRUD
endpoints for `gm_note` (visibility `gm_only`):

  - GM happy paths: create / get / list (pinned-first) / patch / delete.
  - Error paths: empty title+body → 400; unknown note → 404.
  - **Access control (the security core):** a non-GM member (alice)
    cannot create a note (403), does not see gm_notes in her list, and
    gets 404 (not a leak) probing a gm_note by id.

GM = demo-gm@example.com (gm_client); player = demo-alice@example.com
(alice_client), a non-GM member of the demo campaign.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID

_BASE = f"/api/campaign/{CAMPAIGN_ID}/notes"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_notes(gm_client):
    """Delete every note in the campaign after each test so rows don't
    accumulate across the run (the GM can delete any gm_note)."""
    yield
    resp = await gm_client.get(_BASE)
    if resp.status_code == 200:
        for n in resp.json().get("notes", []):
            await gm_client.delete(f"{_BASE}/{n['id']}")


async def test_create_and_get_note(gm_client):
    """GM creates a note → 200 with kind/visibility + echoed content;
    GET by id round-trips it."""
    r = await gm_client.post(_BASE, json={
        "title": "Villain's secret", "body": "The duke is a doppelganger."})
    assert r.status_code == 200, r.text
    note = r.json()["note"]
    assert note["kind"] == "gm_note"
    assert note["visibility"] == "gm_only"
    assert note["title"] == "Villain's secret"
    assert note["body"] == "The duke is a doppelganger."
    assert note["is_encrypted"] is False

    g = await gm_client.get(f"{_BASE}/{note['id']}")
    assert g.status_code == 200, g.text
    assert g.json()["note"]["title"] == "Villain's secret"


async def test_list_orders_pinned_first(gm_client):
    """The list returns the campaign's gm_notes, pinned ones first."""
    await gm_client.post(_BASE, json={"title": "Plain note", "body": "x"})
    await gm_client.post(_BASE, json={"title": "Pinned note", "body": "y",
                                      "pinned": True})
    r = await gm_client.get(_BASE)
    assert r.status_code == 200, r.text
    notes = r.json()["notes"]
    titles = [n["title"] for n in notes]
    assert "Pinned note" in titles and "Plain note" in titles
    assert notes[0]["title"] == "Pinned note", titles


async def test_patch_note(gm_client):
    """PATCH updates title + pinned; omitted fields stay put."""
    c = await gm_client.post(_BASE, json={"title": "Draft", "body": "keep me"})
    nid = c.json()["note"]["id"]
    p = await gm_client.patch(f"{_BASE}/{nid}",
                              json={"title": "Final", "pinned": True})
    assert p.status_code == 200, p.text
    note = p.json()["note"]
    assert note["title"] == "Final"
    assert note["pinned"] is True
    assert note["body"] == "keep me"  # untouched


async def test_delete_note(gm_client):
    """DELETE removes the note; a subsequent GET is 404."""
    c = await gm_client.post(_BASE, json={"body": "ephemeral"})
    nid = c.json()["note"]["id"]
    d = await gm_client.delete(f"{_BASE}/{nid}")
    assert d.status_code == 200, d.text
    assert d.json()["deleted"] == nid
    g = await gm_client.get(f"{_BASE}/{nid}")
    assert g.status_code == 404


async def test_create_requires_title_or_body(gm_client):
    """Empty title AND body → 400."""
    r = await gm_client.post(_BASE, json={"title": "  ", "body": ""})
    assert r.status_code == 400, r.text


async def test_get_unknown_note_404(gm_client):
    """Unknown note id → 404."""
    r = await gm_client.get(f"{_BASE}/999999")
    assert r.status_code == 404, r.text


async def test_player_cannot_create_note(gm_client, alice_client):
    """A non-GM member → 403 on create."""
    r = await alice_client.post(_BASE, json={"title": "sneaky", "body": "x"})
    assert r.status_code == 403, r.text


async def test_player_list_excludes_gm_notes(gm_client, alice_client):
    """A GM note must NOT appear in a non-GM member's list (Phase 1 has
    no player-visible notes yet)."""
    c = await gm_client.post(_BASE, json={"title": "GM only", "body": "secret"})
    gm_note_id = c.json()["note"]["id"]
    r = await alice_client.get(_BASE)
    assert r.status_code == 200, r.text
    ids = [n["id"] for n in r.json()["notes"]]
    assert gm_note_id not in ids, ids


async def test_player_cannot_get_gm_note(gm_client, alice_client):
    """A non-GM probing a gm_note by id gets 404 — never a leak that
    the note exists."""
    c = await gm_client.post(_BASE, json={"title": "GM only", "body": "secret"})
    gm_note_id = c.json()["note"]["id"]
    r = await alice_client.get(f"{_BASE}/{gm_note_id}")
    assert r.status_code == 404, r.text


async def test_player_cannot_delete_gm_note(gm_client, alice_client):
    """A non-GM cannot delete a gm_note (404 — not visible to her)."""
    c = await gm_client.post(_BASE, json={"title": "GM only", "body": "secret"})
    gm_note_id = c.json()["note"]["id"]
    r = await alice_client.delete(f"{_BASE}/{gm_note_id}")
    assert r.status_code == 404, r.text
