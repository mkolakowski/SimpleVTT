"""Notes & Handouts — Phase 2: handouts.

docs/plans/notes-and-handouts.md. Covers the `handouts` CRUD + reveal
endpoints:

  - GM happy paths: create (un-revealed) / list / patch / delete.
  - Reveal-to-all: a player sees the handout in their list + by id.
  - Un-revealed handout: hidden from players (list excludes, id → 404).
  - **WS scoping (the security core):** revealing to one player delivers
    `handout_revealed` to that player's socket and NOT to another
    player's; reveal-to-all reaches every player.
  - Error paths: create missing title → 400; reveal unknown → 404;
    reveal with a bad `to` → 400; player create → 403.

GM = gm_client. Players: alice owns the demo Rogue (Pip Quickfingers),
bob owns the demo Wizard (Thalindra Moonwhisper) — the roster's
`owner_user_id` resolves their user_ids for targeted reveals.
"""
import asyncio
import base64

import pytest_asyncio

from .conftest import CAMPAIGN_ID

_BASE = f"/api/campaign/{CAMPAIGN_ID}/handouts"

# A minimal valid 1×1 PNG for the image-upload tests.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_handouts(gm_client):
    yield
    resp = await gm_client.get(_BASE)
    if resp.status_code == 200:
        for h in resp.json().get("handouts", []):
            await gm_client.delete(f"{_BASE}/{h['id']}")


def _alice_uid(roster):
    return roster["Pip Quickfingers"]["owner_user_id"]


def _bob_uid(roster):
    return roster["Thalindra Moonwhisper"]["owner_user_id"]


async def test_create_handout_unrevealed(gm_client):
    r = await gm_client.post(_BASE, json={
        "title": "The Duke's Letter", "body": "Meet at midnight."})
    assert r.status_code == 200, r.text
    h = r.json()["handout"]
    assert h["title"] == "The Duke's Letter"
    assert h["revealed"] is False
    assert h["reveal_to"] == []


async def test_gm_list_includes_handout(gm_client):
    c = await gm_client.post(_BASE, json={"title": "Map fragment"})
    hid = c.json()["handout"]["id"]
    r = await gm_client.get(_BASE)
    assert r.status_code == 200, r.text
    assert hid in [h["id"] for h in r.json()["handouts"]]


async def test_patch_handout(gm_client):
    c = await gm_client.post(_BASE, json={"title": "Draft"})
    hid = c.json()["handout"]["id"]
    p = await gm_client.patch(f"{_BASE}/{hid}", json={
        "title": "Final", "image_url": "/static/uploads/x.png"})
    assert p.status_code == 200, p.text
    h = p.json()["handout"]
    assert h["title"] == "Final"
    assert h["image_url"] == "/static/uploads/x.png"


async def test_reveal_all_visible_to_player(gm_client, alice_client):
    c = await gm_client.post(_BASE, json={"title": "Public notice"})
    hid = c.json()["handout"]["id"]
    # Before reveal: player can't see it.
    assert hid not in [h["id"] for h in (await alice_client.get(_BASE)).json()["handouts"]]
    assert (await alice_client.get(f"{_BASE}/{hid}")).status_code == 404

    r = await gm_client.post(f"{_BASE}/{hid}/reveal", json={"to": "all"})
    assert r.status_code == 200, r.text
    assert r.json()["handout"]["revealed"] is True
    # After reveal: player sees it in list + by id.
    assert hid in [h["id"] for h in (await alice_client.get(_BASE)).json()["handouts"]]
    assert (await alice_client.get(f"{_BASE}/{hid}")).status_code == 200


async def test_unrevealed_hidden_from_player(gm_client, alice_client):
    c = await gm_client.post(_BASE, json={"title": "GM eyes only"})
    hid = c.json()["handout"]["id"]
    assert hid not in [h["id"] for h in (await alice_client.get(_BASE)).json()["handouts"]]
    assert (await alice_client.get(f"{_BASE}/{hid}")).status_code == 404


async def test_reveal_to_specific_player_scopes_visibility(
    gm_client, roster, alice_client, bob_client,
):
    """Revealed to alice only → alice sees it, bob does not (HTTP view)."""
    alice_uid = _alice_uid(roster)
    c = await gm_client.post(_BASE, json={"title": "For Alice's eyes"})
    hid = c.json()["handout"]["id"]
    r = await gm_client.post(f"{_BASE}/{hid}/reveal",
                             json={"to": [alice_uid]})
    assert r.status_code == 200, r.text
    assert hid in [h["id"] for h in (await alice_client.get(_BASE)).json()["handouts"]]
    assert hid not in [h["id"] for h in (await bob_client.get(_BASE)).json()["handouts"]]
    assert (await bob_client.get(f"{_BASE}/{hid}")).status_code == 404


async def test_reveal_to_specific_player_ws_scoping(
    gm_client, roster, alice_ws, bob_ws,
):
    """**Security core:** revealing to alice delivers handout_revealed
    to alice's socket but NOT to bob's."""
    alice_uid = _alice_uid(roster)
    c = await gm_client.post(_BASE, json={
        "title": "Secret for Alice", "body": "shh"})
    hid = c.json()["handout"]["id"]
    alice_ws.mark()
    bob_ws.mark()
    r = await gm_client.post(f"{_BASE}/{hid}/reveal", json={"to": [alice_uid]})
    assert r.status_code == 200, r.text

    msg = await alice_ws.wait_for("handout_revealed")
    assert msg["data"]["handout_id"] == hid
    assert msg["data"]["title"] == "Secret for Alice"
    assert msg["data"]["revealed"] is True

    # Bob must NOT receive the event. Give delivery a moment, then assert.
    await asyncio.sleep(0.6)
    assert bob_ws.buffered("handout_revealed") == [], (
        f"bob should not receive a handout revealed only to alice; "
        f"got {bob_ws.buffered('handout_revealed')}"
    )


async def test_reveal_all_ws_reaches_everyone(gm_client, alice_ws, bob_ws):
    """Reveal-to-all delivers handout_revealed to every player socket."""
    c = await gm_client.post(_BASE, json={"title": "Town crier"})
    hid = c.json()["handout"]["id"]
    alice_ws.mark()
    bob_ws.mark()
    r = await gm_client.post(f"{_BASE}/{hid}/reveal", json={"to": "all"})
    assert r.status_code == 200, r.text
    am = await alice_ws.wait_for("handout_revealed")
    bm = await bob_ws.wait_for("handout_revealed")
    assert am["data"]["handout_id"] == hid
    assert bm["data"]["handout_id"] == hid


async def test_delete_handout(gm_client):
    c = await gm_client.post(_BASE, json={"title": "Trash me"})
    hid = c.json()["handout"]["id"]
    d = await gm_client.delete(f"{_BASE}/{hid}")
    assert d.status_code == 200, d.text
    assert (await gm_client.get(f"{_BASE}/{hid}")).status_code == 404


async def test_player_cannot_create_handout(gm_client, alice_client):
    r = await alice_client.post(_BASE, json={"title": "sneaky"})
    assert r.status_code == 403, r.text


async def test_create_requires_title(gm_client):
    r = await gm_client.post(_BASE, json={"body": "no title"})
    assert r.status_code == 400, r.text


async def test_reveal_unknown_handout_404(gm_client):
    r = await gm_client.post(f"{_BASE}/999999/reveal", json={"to": "all"})
    assert r.status_code == 404, r.text


async def test_reveal_bad_to_400(gm_client):
    c = await gm_client.post(_BASE, json={"title": "x"})
    hid = c.json()["handout"]["id"]
    r = await gm_client.post(f"{_BASE}/{hid}/reveal", json={"to": 5})
    assert r.status_code == 400, r.text


async def test_upload_handout_image(gm_client):
    """GM uploads a PNG → 200 + a /static/uploads/handouts/ URL."""
    r = await gm_client.post(
        f"{_BASE}/upload_image",
        files={"image": ("frag.png", _PNG, "image/png")},
    )
    assert r.status_code == 200, r.text
    url = r.json()["image_url"]
    assert url.startswith("/static/uploads/handouts/") and url.endswith(".png")


async def test_upload_handout_image_player_403(gm_client, alice_client):
    """A non-GM member cannot upload a handout image."""
    r = await alice_client.post(
        f"{_BASE}/upload_image",
        files={"image": ("frag.png", _PNG, "image/png")},
    )
    assert r.status_code == 403, r.text


async def test_upload_handout_image_bad_ext_400(gm_client):
    """A non-image extension → 400."""
    r = await gm_client.post(
        f"{_BASE}/upload_image",
        files={"image": ("notes.txt", b"not an image", "text/plain")},
    )
    assert r.status_code == 400, r.text
