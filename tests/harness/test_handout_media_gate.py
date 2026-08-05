"""Handout media is authorization-gated, not public static bytes.

v2.1046.0. Until this change, handout images and documents lived at
``/static/uploads/handouts/<uuid>.<ext>`` and were served by the
``/static`` mount to anyone with the URL — so the reveal gate controlled
*distribution of the URL*, not the bytes. A leaked URL read a secret
handout forever, and hiding a handout did not revoke a player who had
already seen it.

``serve_handout_media`` is now registered ahead of the ``/static`` mount
and authorizes every request against the same ``_can_see_handout`` rule
the JSON endpoints use. These tests pin that behavior:

  - Anonymous (no session) → 404, even with the exact URL.
  - A player cannot read an un-revealed handout's media; can after
    reveal; **cannot again after hide** (revocation is the headline).
  - A scoped reveal admits alice and refuses bob.
  - The GM can read a freshly-uploaded, not-yet-attached file (the
    composer preview) via the campaign id baked into the filename; a
    player cannot.
  - Path traversal / unknown names / nested paths → 404.
  - Every other ``/static`` path is untouched by the interception.
  - Served bytes carry a non-caching header, so a shared cache can't
    outlive a revoked reveal.

Failures are deliberately a flat **404**, never 401/403 — a 403 would
confirm that a given un-revealed handout's media exists.
"""
import base64

import httpx
import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .helpers import BASE_URL

_BASE = f"/api/campaign/{CAMPAIGN_ID}/handouts"
_MEDIA_PREFIX = "/static/uploads/handouts/"

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
_PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_handouts(gm_client):
    yield
    resp = await gm_client.get(_BASE)
    if resp.status_code == 200:
        for h in resp.json().get("handouts", []):
            await gm_client.delete(f"{_BASE}/{h['id']}")


def _alice_uid(roster):
    return roster["Pip Quickfingers"]["owner_user_id"]


async def _upload_image(client):
    r = await client.post(f"{_BASE}/upload_image",
                          files={"image": ("frag.png", _PNG, "image/png")})
    assert r.status_code == 200, r.text
    return r.json()["image_url"]


async def _upload_doc(client):
    r = await client.post(f"{_BASE}/upload_file",
                          files={"file": ("map.pdf", _PDF, "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()["file_url"]


async def _handout_with_image(gm_client, title="Gated art"):
    url = await _upload_image(gm_client)
    r = await gm_client.post(_BASE, json={"title": title, "image_url": url})
    assert r.status_code == 200, r.text
    return r.json()["handout"]["id"], url


async def test_upload_url_is_campaign_prefixed(gm_client):
    """The filename carries the campaign id, which is what authorizes a
    not-yet-attached file."""
    url = await _upload_image(gm_client)
    assert url.startswith(_MEDIA_PREFIX)
    assert url[len(_MEDIA_PREFIX):].startswith(f"c{CAMPAIGN_ID}-")


async def test_anonymous_cannot_read_handout_media(gm_client):
    """**The core fix:** the exact URL is useless without a session."""
    _hid, url = await _handout_with_image(gm_client)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as anon:
        r = await anon.get(url)
    assert r.status_code == 404, f"{r.status_code} — media served anonymously"


async def test_gm_can_read_own_handout_media(gm_client):
    _hid, url = await _handout_with_image(gm_client)
    r = await gm_client.get(url)
    assert r.status_code == 200, r.text
    assert r.content == _PNG


async def test_player_blocked_until_revealed_then_revoked_on_hide(
    gm_client, alice_client,
):
    """Un-revealed → 404; revealed → 200; hidden again → 404. The last
    leg is the one the old static-bytes posture could not do."""
    hid, url = await _handout_with_image(gm_client, "Revocation drill")

    assert (await alice_client.get(url)).status_code == 404

    assert (await gm_client.post(f"{_BASE}/{hid}/reveal",
                                 json={"to": "all"})).status_code == 200
    ok = await alice_client.get(url)
    assert ok.status_code == 200, ok.text
    assert ok.content == _PNG

    assert (await gm_client.post(f"{_BASE}/{hid}/reveal",
                                 json={"revealed": False,
                                       "to": "all"})).status_code == 200
    assert (await alice_client.get(url)).status_code == 404, (
        "hiding a handout must revoke access to its media")


async def test_scoped_reveal_scopes_media(gm_client, roster, alice_client,
                                          bob_client):
    """Media follows the same per-player scoping as the handout body."""
    hid, url = await _handout_with_image(gm_client, "Alice only")
    r = await gm_client.post(f"{_BASE}/{hid}/reveal",
                             json={"to": [_alice_uid(roster)]})
    assert r.status_code == 200, r.text
    assert (await alice_client.get(url)).status_code == 200
    assert (await bob_client.get(url)).status_code == 404


async def test_document_media_is_gated_too(gm_client, alice_client):
    """The PDF path is gated identically to the image path."""
    url = await _upload_doc(gm_client)
    hid = (await gm_client.post(_BASE, json={
        "title": "Sealed dispatch", "file_url": url,
        "file_name": "map.pdf", "file_size": len(_PDF),
    })).json()["handout"]["id"]

    assert (await alice_client.get(url)).status_code == 404
    await gm_client.post(f"{_BASE}/{hid}/reveal", json={"to": "all"})
    ok = await alice_client.get(url)
    assert ok.status_code == 200, ok.text
    assert ok.content.startswith(b"%PDF-")
    # Served for in-browser reading, under the GM's original filename
    # rather than the UUID on disk.
    cd = ok.headers.get("content-disposition", "")
    assert cd.startswith("inline"), cd
    assert "map.pdf" in cd, cd


async def test_unattached_upload_readable_by_gm_not_player(
    gm_client, alice_client,
):
    """The composer-preview case: a file uploaded but not yet saved onto
    a handout has no reveal flag, so it falls back to the campaign id in
    the filename — GM yes, player no."""
    url = await _upload_image(gm_client)
    assert (await gm_client.get(url)).status_code == 200
    assert (await alice_client.get(url)).status_code == 404


async def test_deleting_handout_revokes_player_media_access(
    gm_client, alice_client,
):
    """Once the referencing handout is gone there is nothing to
    authorize a player against — the fallback is GM-only."""
    hid, url = await _handout_with_image(gm_client, "Short-lived")
    await gm_client.post(f"{_BASE}/{hid}/reveal", json={"to": "all"})
    assert (await alice_client.get(url)).status_code == 200

    assert (await gm_client.delete(f"{_BASE}/{hid}")).status_code == 200
    assert (await alice_client.get(url)).status_code == 404


async def test_unknown_media_name_404(gm_client):
    r = await gm_client.get(f"{_MEDIA_PREFIX}c{CAMPAIGN_ID}-doesnotexist.png")
    assert r.status_code == 404, r.text


async def test_media_path_traversal_rejected(gm_client):
    """A traversal attempt must not escape the handouts directory."""
    for name in ("..%2F..%2Fstyle.css", "..", "sub/dir.png", ".hidden.png"):
        r = await gm_client.get(f"{_MEDIA_PREFIX}{name}")
        assert r.status_code == 404, f"{name} → {r.status_code}"


async def test_other_static_paths_still_served(gm_client):
    """Regression: the interception is scoped to the handouts prefix and
    must not shadow the rest of the /static mount."""
    r = await gm_client.get("/static/style.css")
    assert r.status_code == 200, r.text
    assert len(r.content) > 0


async def test_served_media_is_not_shared_cacheable(gm_client):
    """Gated bytes must not be parked in a shared/proxy cache, or a
    revoked reveal would keep serving."""
    _hid, url = await _handout_with_image(gm_client)
    r = await gm_client.get(url)
    assert r.status_code == 200, r.text
    cc = r.headers.get("cache-control", "").lower()
    assert "no-store" in cc and "private" in cc, cc
