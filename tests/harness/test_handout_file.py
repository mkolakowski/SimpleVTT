"""Handout document attachments — the "Resources" tier (v2.1045.0).

docs/plans/notes-and-handouts.md (the filed "handout media beyond images"
follow-up). A GM uploads a PDF to a handout; players read it inline in
the browser once the handout is revealed to them. The document rides the
handout's existing ``revealed`` / ``reveal_to`` gate rather than adding a
second access-control surface, so the tests below assert the *gate* as
much as the upload:

  - Happy path: ``POST /handouts/upload_file`` → 200 + a
    /static/uploads/handouts/ URL, the original filename, and the byte
    count; attaching the trio to a handout round-trips through create,
    list, and PATCH.
  - **The access gate:** an un-revealed document is invisible to a
    player (list excludes it, by-id → 404) and becomes visible on
    reveal — i.e. no ``file_url`` leaks before the reveal.
  - The reveal WS broadcast carries ``has_file`` so a client can pick
    the document toast/icon without a second fetch.
  - Detach: PATCH ``file_url: ""`` drops the name + size with the URL.
  - Error paths: non-GM upload → 403; a non-PDF extension → 400; a
    ``.pdf`` whose bytes are not a PDF → 400.

GM = gm_client; alice owns the demo Rogue (Pip Quickfingers), bob the
Wizard (Thalindra Moonwhisper).
"""
import asyncio

import pytest_asyncio

from .conftest import CAMPAIGN_ID

_BASE = f"/api/campaign/{CAMPAIGN_ID}/handouts"

# The smallest bytes that satisfy both the extension check and the
# %PDF- magic-byte check. Browsers won't render it, but the server only
# validates the header — that's the contract under test.
_PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
_NOT_PDF = b"MZ\x90\x00 this is not a pdf at all"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_handouts(gm_client):
    yield
    resp = await gm_client.get(_BASE)
    if resp.status_code == 200:
        for h in resp.json().get("handouts", []):
            await gm_client.delete(f"{_BASE}/{h['id']}")


def _alice_uid(roster):
    return roster["Pip Quickfingers"]["owner_user_id"]


async def _upload(client, name="tavern-map.pdf", data=_PDF):
    return await client.post(
        f"{_BASE}/upload_file",
        files={"file": (name, data, "application/pdf")},
    )


async def test_upload_handout_file(gm_client):
    """GM uploads a PDF → 200 + a /static/uploads/handouts/ URL, the
    original filename, and the real byte count."""
    r = await _upload(gm_client)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["file_url"].startswith("/static/uploads/handouts/")
    assert d["file_url"].endswith(".pdf")
    assert d["file_name"] == "tavern-map.pdf"
    assert d["file_size"] == len(_PDF)


async def test_uploaded_file_is_served(gm_client):
    """The returned URL actually resolves — an inline viewer pointed at
    it gets the bytes back, not a 404."""
    up = (await _upload(gm_client)).json()
    r = await gm_client.get(up["file_url"])
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"%PDF-")


async def test_create_handout_with_file_round_trips(gm_client):
    """The file_url/file_name/file_size trio survives create → get."""
    up = (await _upload(gm_client, name="the-ledger.pdf")).json()
    c = await gm_client.post(_BASE, json={
        "title": "The Harbormaster's Ledger",
        "body": "Every shipment for the last month.",
        "file_url": up["file_url"],
        "file_name": up["file_name"],
        "file_size": up["file_size"],
    })
    assert c.status_code == 200, c.text
    h = c.json()["handout"]
    assert h["file_url"] == up["file_url"]
    assert h["file_name"] == "the-ledger.pdf"
    assert h["file_size"] == len(_PDF)

    got = (await gm_client.get(f"{_BASE}/{h['id']}")).json()["handout"]
    assert got["file_url"] == up["file_url"]
    assert got["file_name"] == "the-ledger.pdf"
    assert got["file_size"] == len(_PDF)


async def test_patch_attaches_and_detaches_file(gm_client):
    """PATCH attaches a document to an existing handout; clearing
    file_url drops the display metadata with it."""
    up = (await _upload(gm_client, name="map.pdf")).json()
    hid = (await gm_client.post(_BASE, json={"title": "Bare"})).json()["handout"]["id"]

    p = await gm_client.patch(f"{_BASE}/{hid}", json={
        "file_url": up["file_url"],
        "file_name": up["file_name"],
        "file_size": up["file_size"],
    })
    assert p.status_code == 200, p.text
    assert p.json()["handout"]["file_name"] == "map.pdf"

    d = await gm_client.patch(f"{_BASE}/{hid}", json={"file_url": ""})
    assert d.status_code == 200, d.text
    h = d.json()["handout"]
    assert h["file_url"] is None
    assert h["file_name"] == ""
    assert h["file_size"] is None


async def test_document_hidden_until_revealed(gm_client, alice_client):
    """**The access gate.** An un-revealed handout's file_url never
    reaches a player; revealing it makes the document readable."""
    up = (await _upload(gm_client, name="secret-plans.pdf")).json()
    hid = (await gm_client.post(_BASE, json={
        "title": "Cult Plans",
        "file_url": up["file_url"],
        "file_name": up["file_name"],
        "file_size": up["file_size"],
    })).json()["handout"]["id"]

    listed = (await alice_client.get(_BASE)).json()["handouts"]
    assert hid not in [h["id"] for h in listed]
    assert (await alice_client.get(f"{_BASE}/{hid}")).status_code == 404

    r = await gm_client.post(f"{_BASE}/{hid}/reveal", json={"to": "all"})
    assert r.status_code == 200, r.text

    seen = (await alice_client.get(f"{_BASE}/{hid}")).json()["handout"]
    assert seen["file_url"] == up["file_url"]
    assert seen["file_name"] == "secret-plans.pdf"


async def test_document_scoped_reveal_excludes_other_player(
    gm_client, roster, alice_client, bob_client,
):
    """A document revealed to alice only is not listed for bob."""
    up = (await _upload(gm_client)).json()
    hid = (await gm_client.post(_BASE, json={
        "title": "For Alice only",
        "file_url": up["file_url"],
        "file_name": up["file_name"],
        "file_size": up["file_size"],
    })).json()["handout"]["id"]

    r = await gm_client.post(f"{_BASE}/{hid}/reveal",
                             json={"to": [_alice_uid(roster)]})
    assert r.status_code == 200, r.text
    assert hid in [h["id"] for h in (await alice_client.get(_BASE)).json()["handouts"]]
    assert hid not in [h["id"] for h in (await bob_client.get(_BASE)).json()["handouts"]]


async def test_reveal_broadcast_carries_has_file(gm_client, alice_ws):
    """The handout_revealed payload flags a document so the client can
    render the 📄 toast without a second fetch."""
    up = (await _upload(gm_client)).json()
    hid = (await gm_client.post(_BASE, json={
        "title": "The Charter",
        "file_url": up["file_url"],
        "file_name": up["file_name"],
        "file_size": up["file_size"],
    })).json()["handout"]["id"]

    alice_ws.mark()
    r = await gm_client.post(f"{_BASE}/{hid}/reveal", json={"to": "all"})
    assert r.status_code == 200, r.text

    msg = await alice_ws.wait_for("handout_revealed")
    assert msg["data"]["handout_id"] == hid
    assert msg["data"]["has_file"] is True
    assert msg["data"]["revealed"] is True


async def test_reveal_broadcast_has_file_false_without_document(
    gm_client, alice_ws,
):
    """A text-only handout reports has_file False (not missing)."""
    hid = (await gm_client.post(
        _BASE, json={"title": "Just a note"})).json()["handout"]["id"]
    alice_ws.mark()
    await gm_client.post(f"{_BASE}/{hid}/reveal", json={"to": "all"})
    msg = await alice_ws.wait_for("handout_revealed")
    assert msg["data"]["has_file"] is False


async def test_upload_handout_file_player_403(alice_client):
    """A non-GM member cannot upload a document."""
    r = await _upload(alice_client)
    assert r.status_code == 403, r.text


async def test_upload_handout_file_bad_ext_400(gm_client):
    """A non-PDF extension → 400 (PDF only, so it renders inline)."""
    r = await gm_client.post(
        f"{_BASE}/upload_file",
        files={"file": ("notes.docx", _PDF, "application/msword")},
    )
    assert r.status_code == 400, r.text


async def test_upload_handout_file_bad_magic_400(gm_client):
    """A .pdf extension over non-PDF bytes → 400: the extension is a
    claim, and the viewer would render nothing."""
    r = await _upload(gm_client, name="trojan.pdf", data=_NOT_PDF)
    assert r.status_code == 400, r.text


async def test_bad_file_size_degrades_to_null(gm_client):
    """A junk file_size is cosmetic — it nulls out rather than 400-ing a
    save whose real payload is the URL."""
    up = (await _upload(gm_client)).json()
    c = await gm_client.post(_BASE, json={
        "title": "Junk size",
        "file_url": up["file_url"],
        "file_name": up["file_name"],
        "file_size": "not-a-number",
    })
    assert c.status_code == 200, c.text
    assert c.json()["handout"]["file_size"] is None
    # And the document itself still round-trips.
    assert c.json()["handout"]["file_url"] == up["file_url"]


async def test_unrevealed_document_not_in_player_list_after_hide(
    gm_client, alice_client,
):
    """Hiding a revealed document withdraws it again — the gate is not
    one-way."""
    up = (await _upload(gm_client)).json()
    hid = (await gm_client.post(_BASE, json={
        "title": "Recalled dispatch",
        "file_url": up["file_url"],
        "file_name": up["file_name"],
        "file_size": up["file_size"],
    })).json()["handout"]["id"]
    await gm_client.post(f"{_BASE}/{hid}/reveal", json={"to": "all"})
    assert (await alice_client.get(f"{_BASE}/{hid}")).status_code == 200

    h = await gm_client.post(f"{_BASE}/{hid}/reveal",
                             json={"revealed": False, "to": "all"})
    assert h.status_code == 200, h.text
    await asyncio.sleep(0.2)
    assert (await alice_client.get(f"{_BASE}/{hid}")).status_code == 404
