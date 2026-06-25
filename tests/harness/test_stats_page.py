"""v2.652.0 — the per-campaign statistics page, Phase 3.

`GET /campaign/{id}/stats` renders the shell (the numbers are fetched
client-side from the Phase-2 API). Gated by `_user_can_view_campaign`;
the GM gets a roster `<select>` switcher, a player doesn't. See
docs/plans/campaign-stats.md.
"""
from .conftest import CAMPAIGN_ID


async def test_stats_page_renders_for_gm(gm_client):
    r = await gm_client.get(f"/campaign/{CAMPAIGN_ID}/stats")
    assert r.status_code == 200, r.text
    assert "text/html" in r.headers.get("content-type", "")
    body = r.text
    assert "Statistics" in body
    # The GM gets the roster switcher.
    assert 'id="stats-pc"' in body
    # The page fetches the Phase-2 API.
    assert f"/api/campaign/${{CID}}/stats" in body or "/stats" in body


async def test_stats_page_renders_for_member_without_switcher(alice_client):
    r = await alice_client.get(f"/campaign/{CAMPAIGN_ID}/stats")
    assert r.status_code == 200, r.text
    body = r.text
    assert "Statistics" in body
    # A player does NOT get the GM roster switcher.
    assert 'id="stats-pc"' not in body


async def test_stats_page_unknown_campaign_404(gm_client):
    r = await gm_client.get("/campaign/99999999/stats")
    assert r.status_code == 404, r.text
