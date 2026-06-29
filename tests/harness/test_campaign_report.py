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
         "per_session", "top_actors", "total_moves", "total_distance_ft"}


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


async def test_token_move_is_logged_in_report(gm_client):
    """v2.734.0 — moving a token logs a `token_move` stat event, so the
    report's total_moves + total_distance_ft climb. Uses a throwaway
    standalone token (no character_id) so it never disturbs the demo PC
    tokens other tests rely on, then cleans it up."""
    # Create a standalone token to move (not a demo PC's shared token).
    created = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/tokens",
        json={"label": "ReportMoveProbe", "x": 100.0, "y": 100.0})
    assert created.status_code == 200, created.text
    tok = created.json()
    try:
        before = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/report")).json()
        bm, bd = before["total_moves"], before["total_distance_ft"]

        # Move 15 ft (210 px on the 70px=5ft grid).
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/token/{tok['id']}/move",
            json={"x": float(tok["x"]) + 210.0, "y": float(tok["y"])})
        assert r.status_code == 200, r.text
        assert r.json()["distance_ft"] == 15.0, r.json()

        after = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/report")).json()
        assert after["total_moves"] >= bm + 1, (bm, after["total_moves"])
        assert after["total_distance_ft"] >= bd + 15, (bd, after["total_distance_ft"])
        assert after["events_by_type"].get("token_move", 0) >= 1
    finally:
        await gm_client.delete(
            f"/api/campaign/{CAMPAIGN_ID}/tokens/{tok['id']}")


async def test_report_requires_gm(alice_client):
    """A non-GM campaign member can't read the report (JSON or page)."""
    j = await alice_client.get(f"/api/campaign/{CAMPAIGN_ID}/report")
    assert j.status_code == 403, j.text
    p = await alice_client.get(f"/campaign/{CAMPAIGN_ID}/report")
    assert p.status_code == 403, p.text
