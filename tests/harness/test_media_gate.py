"""Uploaded media outside the handouts bucket is authorization-gated.

v2.1047.0 — generalizes the v2.1046.0 handout gate to maps, thumbnails,
tokens, portraits, token_templates, encounter_bg, and audio. Every one
of those was previously served by the ``/static`` mount with **no auth
check**, so a leaked URL read a GM's unrevealed map forever.

**Note on the demo stack.** The seeded demo references *no* uploaded
media — its art lives under ``/static/demo/``, which is bundled with the
image and deliberately outside the gate. So these tests upload their own
map through the real settings endpoint, exercise the gate against it,
and delete it again. (That also means this change has near-zero blast
radius on a demo deployment; the risk lives on real installs.)

The design's real risk is not the gate, it's **resolution coverage**:
the handler denies any file it cannot map back to an owning campaign, so
a missed DB column would 404 art that used to render.
``test_uploaded_media_is_rendered_and_still_serves`` guards that by
harvesting media URLs out of the actually-rendered settings page and
asserting each one still serves — a forgotten column shows up there as a
concrete broken image rather than a silent regression.
"""
import base64
import re

import httpx
import pytest
import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .helpers import BASE_URL

_SETTINGS = f"/campaign/{CAMPAIGN_ID}/settings"
_MAPS = f"{_SETTINGS}/maps"

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")

_GATED = ("maps", "thumbnails", "tokens", "portraits", "token_templates",
          "encounter_bg", "audio")
_URL_RE = re.compile(r"/static/uploads/([a-z_]+)/([A-Za-z0-9._-]+)")
# The settings page bootstraps its map list into an inline JS array; it is
# the only surface that lists *every* campaign map (``/map-group`` returns
# just the active map's group, which a freshly-uploaded map isn't in).
_MAP_ROW_RE = re.compile(
    r"\{id:\s*(\d+),\s*name:\s*\"([^\"]*)\",\s*image_url:\s*\"([^\"]*)\"")


async def _find_map(gm_client, name):
    page = await gm_client.get(_SETTINGS)
    assert page.status_code == 200, page.text
    for map_id, row_name, image_url in _MAP_ROW_RE.findall(page.text):
        if row_name == name:
            return int(map_id), image_url
    return None, None


@pytest_asyncio.fixture
async def uploaded_map(gm_client):
    """Upload a real map into the demo campaign, yield (map_id, url),
    then delete it. Skips when uploads are disabled on the stack."""
    r = await gm_client.post(
        _MAPS,
        data={"name": "gate-probe", "grid_type": "square",
              "grid_size_px": "70"},
        files={"image": ("probe.png", _PNG, "image/png")},
    )
    if r.status_code == 403:
        pytest.skip("uploads disabled on this stack")
    assert r.status_code in (200, 303), r.text

    map_id, url = await _find_map(gm_client, "gate-probe")
    assert map_id, "uploaded map not in the settings map list"
    assert url.startswith("/static/uploads/maps/"), url
    try:
        yield map_id, url
    finally:
        await gm_client.post(f"{_MAPS}/{map_id}/delete")


async def test_member_reads_uploaded_map(gm_client, uploaded_map):
    _map_id, url = uploaded_map
    r = await gm_client.get(url)
    assert r.status_code == 200, r.text
    assert r.content == _PNG


async def test_anonymous_cannot_read_uploaded_map(gm_client, uploaded_map):
    """**The core fix:** the exact URL is useless without a session."""
    _map_id, url = uploaded_map
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as anon:
        r = await anon.get(url)
    assert r.status_code == 404, f"{r.status_code} — media served anonymously"


async def test_campaign_player_can_read_campaign_media(
    gm_client, uploaded_map, alice_client,
):
    """The gate is campaign membership, not GM-only."""
    _map_id, url = uploaded_map
    r = await alice_client.get(url)
    assert r.status_code == 200, f"{url} → {r.status_code}"


async def test_uploaded_media_is_rendered_and_still_serves(
    gm_client, uploaded_map,
):
    """**The coverage guard.** Every gated media URL the settings page
    actually renders must still serve — a DB column this gate forgot to
    resolve shows up here as a broken image."""
    page = await gm_client.get(_SETTINGS)
    assert page.status_code == 200, page.text
    urls = {f"/static/uploads/{b}/{n}"
            for b, n in _URL_RE.findall(page.text) if b in _GATED}
    assert urls, "settings page rendered no gated media URLs"
    broken = []
    for url in sorted(urls):
        r = await gm_client.get(url)
        if r.status_code != 200:
            broken.append(f"{url} → {r.status_code}")
    assert not broken, (
        "media rendered by the app no longer serves (unresolved owner?): "
        + "; ".join(broken))


async def test_deleting_the_row_closes_the_gate(gm_client):
    """Resolution is by DB reference, so deleting the map revokes access
    to its file even though the bytes stay on disk."""
    r = await gm_client.post(
        _MAPS,
        data={"name": "gate-probe-del", "grid_type": "square",
              "grid_size_px": "70"},
        files={"image": ("probe.png", _PNG, "image/png")},
    )
    if r.status_code == 403:
        pytest.skip("uploads disabled on this stack")
    map_id, url = await _find_map(gm_client, "gate-probe-del")
    assert map_id, "uploaded map not in the settings map list"
    assert (await gm_client.get(url)).status_code == 200

    d = await gm_client.post(f"{_MAPS}/{map_id}/delete")
    assert d.status_code in (200, 303), d.text
    assert (await gm_client.get(url)).status_code == 404, (
        "an orphaned file must fail closed")


async def test_orphan_media_fails_closed(gm_client):
    """A file referenced by no DB row → 404. Nothing in the UI links to
    an unreferenced file, so this breaks no rendering."""
    r = await gm_client.get(
        "/static/uploads/maps/definitely-not-a-real-file-9f3a.png")
    assert r.status_code == 404, r.text


async def test_traversal_and_nested_paths_rejected(gm_client):
    """Percent-encoded so the client can't normalize the dot segments
    away before the server sees them."""
    for path in (
        "/static/uploads/maps/%2e%2e%2f%2e%2e%2fstyle.css",
        "/static/uploads/maps/sub/dir.png",
        "/static/uploads/maps/.hidden.png",
    ):
        r = await gm_client.get(path)
        assert r.status_code == 404, f"{path} → {r.status_code}"
        assert b"--fg" not in r.content, f"{path} leaked stylesheet bytes"


async def test_ungated_static_paths_still_served(gm_client):
    """Regression: the interception is scoped to the uploads buckets and
    must not shadow the rest of /static — including the bundled demo art
    under /static/demo/, which is deliberately outside the gate."""
    for path in ("/static/style.css", "/static/demo/maps/tavern.png"):
        r = await gm_client.get(path)
        assert r.status_code == 200, f"{path} → {r.status_code}"
        assert len(r.content) > 0


async def test_media_is_browser_cacheable_but_not_shared(
    gm_client, uploaded_map,
):
    """`no-store` here would make the tabletop refetch every image on
    every load — ordinary campaign art must stay revalidatable."""
    _map_id, url = uploaded_map
    r = await gm_client.get(url)
    assert r.status_code == 200, r.text
    cc = r.headers.get("cache-control", "").lower()
    assert "private" in cc, cc
    assert "no-store" not in cc, cc
    assert r.headers.get("etag"), "no ETag — conditional requests impossible"


async def test_conditional_request_gets_304(gm_client, uploaded_map):
    """FileResponse doesn't answer If-None-Match on its own; the handler
    must, or every revalidation ships the whole file again."""
    _map_id, url = uploaded_map
    first = await gm_client.get(url)
    etag = first.headers.get("etag")
    assert etag, "no ETag to revalidate with"
    second = await gm_client.get(url, headers={"If-None-Match": etag})
    assert second.status_code == 304, second.status_code
    assert second.headers.get("etag") == etag
    assert second.content == b"", "304 must not carry a body"


async def test_handout_bucket_keeps_its_stricter_handler(gm_client):
    """The generic gate must not have swallowed handouts — those keep
    per-player reveal rules and `no-store`."""
    up = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/handouts/upload_image",
        files={"image": ("frag.png", _PNG, "image/png")},
    )
    if up.status_code == 403:
        pytest.skip("uploads disabled on this stack")
    assert up.status_code == 200, up.text
    url = up.json()["image_url"]
    r = await gm_client.get(url)
    assert r.status_code == 200, r.text
    assert "no-store" in r.headers.get("cache-control", "").lower(), (
        "handout media lost its stricter no-store handler")
