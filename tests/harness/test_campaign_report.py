"""v2.730.0 — GM campaign activity Report page (the "Reporting Page" item).

A GM-only campaign ACTIVITY summary (session count, event mix, per-session
timeline, most-active actors) derived from the `campaign_stat_events` log —
complementing the per-character combat stats page.

  - `GET /api/campaign/{cid}/report` (JSON, GM-only) — the report shape.
  - `GET /campaign/{cid}/report` (page, GM-only) — renders the report.
  - non-GM members get 403.
"""
from .conftest import CAMPAIGN_ID

_KEYS = {"session_count", "total_events", "events_by_type",
         "per_session", "top_actors"}


async def test_report_json_shape(gm_client):
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/report")
    assert r.status_code == 200, r.text
    body = r.json()
    assert _KEYS.issubset(body.keys()), body.keys()
    assert isinstance(body["session_count"], int)
    assert isinstance(body["total_events"], int)
    assert isinstance(body["events_by_type"], dict)
    assert isinstance(body["per_session"], list)
    assert isinstance(body["top_actors"], list)


async def test_report_page_renders_for_gm(gm_client):
    r = await gm_client.get(f"/campaign/{CAMPAIGN_ID}/report")
    assert r.status_code == 200, r.text
    assert "Activity report" in r.text
    assert "Sessions" in r.text


async def test_report_requires_gm(alice_client):
    """A non-GM campaign member can't read the report (JSON or page)."""
    j = await alice_client.get(f"/api/campaign/{CAMPAIGN_ID}/report")
    assert j.status_code == 403, j.text
    p = await alice_client.get(f"/campaign/{CAMPAIGN_ID}/report")
    assert p.status_code == 403, p.text
