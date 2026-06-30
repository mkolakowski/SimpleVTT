"""v2.760.0 — dedicated map editor page.

`GET /campaign/{cid}/map/{map_id}/edit` renders the GM-only map editor (image
+ wall/hotspot SVG overlay + grid/ambient controls). GM-only; unknown map 404.
"""
from .conftest import CAMPAIGN_ID


async def _active_map_id(gm_client) -> int:
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/active-map")
    return int(r.json()["map_id"])


async def test_editor_renders_for_gm(gm_client):
    mid = await _active_map_id(gm_client)
    r = await gm_client.get(f"/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    assert r.status_code == 200, r.status_code
    body = r.text
    assert "Edit map" in body
    assert 'id="me-overlay"' in body
    assert 'id="me-wall-btn"' in body and 'id="me-spot-btn"' in body


async def test_editor_requires_gm(gm_client, alice_client):
    mid = await _active_map_id(gm_client)
    r = await alice_client.get(f"/campaign/{CAMPAIGN_ID}/map/{mid}/edit")
    assert r.status_code == 403, r.status_code


async def test_editor_unknown_map_404(gm_client):
    r = await gm_client.get(f"/campaign/{CAMPAIGN_ID}/map/99999999/edit")
    assert r.status_code == 404, r.status_code
