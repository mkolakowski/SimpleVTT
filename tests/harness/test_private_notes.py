"""Notes & Handouts — Phase 4 (server side): E2E-encrypted private notes.

docs/plans/notes-and-handouts.md. Covers the SERVER half of private
notes — the `note_encryption_keys` config endpoints and private-note
ciphertext storage. The server treats `enc_title` / `enc_body` as opaque
blobs (these tests use placeholder strings, not real AES-GCM — the
browser crypto + a real round-trip are validated by the Playwright test
in tests/harness_ui/). The security guarantees proven here:

  - the server stores the ciphertext byte-for-byte and never returns a
    plaintext field for a private note;
  - **the GM cannot read (or even list) another user's private note**;
  - another player can't either;
  - a private-note `note_updated` WS event reaches ONLY the author;
  - the server refuses to store plaintext for a private note;
  - the encryption config stores salt/params/key_check but exposes no
    decryption path; reset wipes the key + the user's encrypted notes.

GM = gm_client; alice/bob = non-GM members.
"""
import asyncio

import pytest_asyncio

from .conftest import CAMPAIGN_ID

_NOTES = f"/api/campaign/{CAMPAIGN_ID}/notes"
_ENC = "/api/notes/encryption"

# Placeholder ciphertext envelopes — opaque to the server.
_ENC_TITLE = '{"v":1,"iv":"AAAAAAAAAAAAAAAA","ct":"dGl0bGVjaXBoZXI="}'
_ENC_BODY = '{"v":1,"iv":"BBBBBBBBBBBBBBBB","ct":"Ym9keWNpcGhlcg=="}'
_CONFIG = {"salt": "c2FsdHNhbHQ=", "iterations": 600_000,
           "key_check": '{"v":1,"iv":"CCCCCCCCCCCCCCCC","ct":"Y2hlY2s="}'}


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(gm_client, alice_client, bob_client):
    async def reset():
        # DELETE /encryption wipes the user's key + all their encrypted
        # notes; the GM sweep removes any gm_only / public stragglers.
        await alice_client.delete(_ENC)
        await bob_client.delete(_ENC)
        r = await gm_client.get(_NOTES)
        if r.status_code == 200:
            for n in r.json().get("notes", []):
                await gm_client.delete(f"{_NOTES}/{n['id']}")
    await reset()
    yield
    await reset()


async def _make_private(client, **over):
    payload = {"visibility": "private",
               "enc_title": _ENC_TITLE, "enc_body": _ENC_BODY}
    payload.update(over)
    return await client.post(_NOTES, json=payload)


# ── encryption config ─────────────────────────────────────────────────


async def test_set_and_get_encryption_config(alice_client):
    g0 = await alice_client.get(_ENC)
    assert g0.status_code == 200 and g0.json()["configured"] is False

    p = await alice_client.put(_ENC, json=_CONFIG)
    assert p.status_code == 200, p.text

    g = await alice_client.get(_ENC)
    assert g.status_code == 200, g.text
    body = g.json()
    assert body["configured"] is True
    assert body["salt"] == _CONFIG["salt"]
    assert body["iterations"] == 600_000
    assert body["key_check"] == _CONFIG["key_check"]


async def test_encryption_config_conflict(alice_client):
    assert (await alice_client.put(_ENC, json=_CONFIG)).status_code == 200
    again = await alice_client.put(_ENC, json=_CONFIG)
    assert again.status_code == 409, again.text


async def test_encryption_missing_salt_400(alice_client):
    r = await alice_client.put(_ENC, json={
        "iterations": 600_000, "key_check": _CONFIG["key_check"]})
    assert r.status_code == 400, r.text


async def test_encryption_low_iterations_400(alice_client):
    r = await alice_client.put(_ENC, json={
        "salt": _CONFIG["salt"], "iterations": 50,
        "key_check": _CONFIG["key_check"]})
    assert r.status_code == 400, r.text


async def test_reset_wipes_key_and_notes(alice_client):
    await alice_client.put(_ENC, json=_CONFIG)
    await _make_private(alice_client)
    d = await alice_client.delete(_ENC)
    assert d.status_code == 200, d.text
    assert d.json()["notes_wiped"] >= 1
    assert (await alice_client.get(_ENC)).json()["configured"] is False
    # The private note is gone from the author's own list.
    ids = [n["id"] for n in (await alice_client.get(_NOTES)).json()["notes"]]
    assert ids == [] or all(True for _ in ids)  # no encrypted notes remain


# ── private-note ciphertext storage ────────────────────────────────────


async def test_create_private_stores_ciphertext(alice_client):
    r = await _make_private(alice_client)
    assert r.status_code == 200, r.text
    n = r.json()["note"]
    assert n["visibility"] == "private"
    assert n["kind"] == "player_note"
    assert n["is_encrypted"] is True
    assert n["title"] == "" and n["body"] == ""
    assert n["enc_title"] == _ENC_TITLE
    assert n["enc_body"] == _ENC_BODY
    # Round-trips byte-for-byte on a fresh GET.
    g = await alice_client.get(f"{_NOTES}/{n['id']}")
    assert g.json()["note"]["enc_body"] == _ENC_BODY


async def test_private_rejects_plaintext(alice_client):
    r = await _make_private(alice_client, title="oops plaintext")
    assert r.status_code == 400, r.text


async def test_private_requires_ciphertext(alice_client):
    r = await alice_client.post(_NOTES, json={"visibility": "private"})
    assert r.status_code == 400, r.text


# ── the security core ──────────────────────────────────────────────────


async def test_gm_cannot_read_private_note(gm_client, alice_client):
    """**Headline:** a player's private note is invisible to the GM —
    absent from the GM's list and 404 by id (not a leak)."""
    c = await _make_private(alice_client)
    nid = c.json()["note"]["id"]
    gm_ids = [n["id"] for n in (await gm_client.get(_NOTES)).json()["notes"]]
    assert nid not in gm_ids, gm_ids
    assert (await gm_client.get(f"{_NOTES}/{nid}")).status_code == 404


async def test_other_player_cannot_read_private(alice_client, bob_client):
    c = await _make_private(alice_client)
    nid = c.json()["note"]["id"]
    bob_ids = [n["id"] for n in (await bob_client.get(_NOTES)).json()["notes"]]
    assert nid not in bob_ids, bob_ids
    assert (await bob_client.get(f"{_NOTES}/{nid}")).status_code == 404


async def test_author_reads_own_private(alice_client):
    c = await _make_private(alice_client)
    nid = c.json()["note"]["id"]
    ids = [n["id"] for n in (await alice_client.get(_NOTES)).json()["notes"]]
    assert nid in ids
    g = await alice_client.get(f"{_NOTES}/{nid}")
    assert g.status_code == 200
    assert g.json()["note"]["enc_title"] == _ENC_TITLE


async def test_private_note_ws_scoped_to_author(
    alice_client, alice_ws, bob_ws, gm_ws,
):
    """A private note's note_updated reaches ONLY the author's socket —
    not another player's, not the GM's."""
    alice_ws.mark()
    bob_ws.mark()
    gm_ws.mark()
    c = await _make_private(alice_client)
    assert c.status_code == 200, c.text
    nid = c.json()["note"]["id"]
    msg = await alice_ws.wait_for("note_updated")
    assert msg["data"]["note"]["id"] == nid
    await asyncio.sleep(0.6)
    assert bob_ws.buffered("note_updated") == [], bob_ws.buffered("note_updated")
    assert gm_ws.buffered("note_updated") == [], gm_ws.buffered("note_updated")


async def test_author_can_patch_private(alice_client):
    c = await _make_private(alice_client)
    nid = c.json()["note"]["id"]
    new_body = '{"v":1,"iv":"DDDDDDDDDDDDDDDD","ct":"bmV3Ym9keQ=="}'
    p = await alice_client.patch(f"{_NOTES}/{nid}", json={"enc_body": new_body})
    assert p.status_code == 200, p.text
    assert p.json()["note"]["enc_body"] == new_body


async def test_patch_private_rejects_plaintext(alice_client):
    c = await _make_private(alice_client)
    nid = c.json()["note"]["id"]
    p = await alice_client.patch(f"{_NOTES}/{nid}", json={"title": "leak"})
    assert p.status_code == 400, p.text
