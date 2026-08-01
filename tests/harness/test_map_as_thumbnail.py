"""v2.1043.0 — reuse a map image as the campaign thumbnail.

`POST /campaign/{cid}/settings/maps/{map_id}/use-as-thumbnail` points
`campaign.thumbnail_url` at an existing map's `image_url` so a GM doesn't upload
the same picture twice. Not an upload endpoint (it references a file already on
disk), so it works even when uploads are disabled on the demo.

Tests:
  - happy path: GM sets the thumbnail from a seeded map → 200, response carries
    the map's static image URL, and the settings page renders it.
  - unknown map → 404.
  - non-GM (player) → 403 (the GM gate fires before the map lookup).

No teardown: the end state (thumbnail = a map image) is exactly the intended
demo state, and the demo campaign reseeds on its interval anyway.
"""
from .conftest import CAMPAIGN_ID


async def _first_map(client):
    r = await client.get(f"/api/campaign/{CAMPAIGN_ID}/map-group")
    assert r.status_code == 200, r.text
    maps = (r.json() or {}).get("maps") or []
    assert maps, "demo campaign should have at least one map"
    return maps[0]


async def test_use_map_as_thumbnail_happy(gm_client):
    m = await _first_map(gm_client)
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/{m['id']}/use-as-thumbnail",
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["map_id"] == m["id"]
    url = data["thumbnail_url"]
    assert isinstance(url, str) and url.startswith("/static/"), f"unexpected url: {url!r}"
    # Persisted: the settings page renders the new thumbnail image.
    page = await gm_client.get(f"/campaign/{CAMPAIGN_ID}/settings")
    assert page.status_code == 200, page.text
    assert url in page.text, "settings page should show the new thumbnail URL"


async def test_use_map_as_thumbnail_unknown_map_404(gm_client):
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/99999999/use-as-thumbnail",
    )
    assert r.status_code == 404, r.text


async def test_use_map_as_thumbnail_requires_gm(alice_client):
    # The GM gate fires before the map lookup, so any map_id yields 403 for a
    # non-GM player.
    r = await alice_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/1/use-as-thumbnail",
    )
    assert r.status_code == 403, r.text
