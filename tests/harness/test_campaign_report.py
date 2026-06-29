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
    # v2.736.0 — each top-actor entry carries char_id (None for NPC actors)
    # so the report can link PC actors to their sheet.
    for a in body["top_actors"]:
        assert "char_id" in a and "name" in a and "events" in a, a


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


async def _a_session_key(gm_client):
    rep = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/report")).json()
    sess = rep.get("per_session") or []
    return sess[0]["session_key"] if sess else "1970-01-01"


async def test_session_detail_json(gm_client):
    """v2.735.0 — the per-session drill-down JSON (GM-only)."""
    key = await _a_session_key(gm_client)
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/report/session", params={"key": key})
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"session_key", "total_events", "events_by_type", "top_actors",
            "recent_events", "total_moves", "total_distance_ft"}.issubset(body)
    assert body["session_key"] == key
    assert isinstance(body["recent_events"], list)


async def test_session_detail_page_renders(gm_client):
    key = await _a_session_key(gm_client)
    r = await gm_client.get(
        f"/campaign/{CAMPAIGN_ID}/report/session", params={"key": key})
    assert r.status_code == 200, r.text
    assert "Session report" in r.text


async def test_session_detail_requires_gm(alice_client):
    j = await alice_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/report/session", params={"key": "x"})
    assert j.status_code == 403, j.text
    p = await alice_client.get(
        f"/campaign/{CAMPAIGN_ID}/report/session", params={"key": "x"})
    assert p.status_code == 403, p.text


async def test_report_date_filter(gm_client):
    """v2.739.0 — start/end narrow the report; the bounds are echoed, and a
    far-future window yields zero events."""
    # Echo: the applied date_to is exclusive (end + 1 day), date_from as given.
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/report",
        params={"start": "2020-01-01", "end": "2020-01-31"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["date_from"].startswith("2020-01-01")
    assert body["date_to"].startswith("2020-02-01")  # end inclusive → +1 day
    # A window before any events → empty.
    assert body["total_events"] == 0
    assert body["per_session"] == []

    # The CSV honors the same filter (still a valid attachment).
    c = await gm_client.get(
        f"/campaign/{CAMPAIGN_ID}/report.csv",
        params={"start": "2020-01-01", "end": "2020-01-31"})
    assert c.status_code == 200, c.text
    assert "text/csv" in c.headers.get("content-type", "")


async def test_report_csv_export(gm_client):
    """v2.738.0 — the per-session timeline downloads as CSV (GM-only)."""
    r = await gm_client.get(f"/campaign/{CAMPAIGN_ID}/report.csv")
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers.get("content-type", "")
    assert "attachment" in r.headers.get("content-disposition", "")
    body = r.text
    assert "session_key,first_event,events,damage_dealt,heal_done" in body
    assert "TOTAL" in body


async def test_report_csv_requires_gm(alice_client):
    r = await alice_client.get(f"/campaign/{CAMPAIGN_ID}/report.csv")
    assert r.status_code == 403, r.text


async def test_report_requires_gm(alice_client):
    """A non-GM campaign member can't read the report (JSON or page)."""
    j = await alice_client.get(f"/api/campaign/{CAMPAIGN_ID}/report")
    assert j.status_code == 403, j.text
    p = await alice_client.get(f"/campaign/{CAMPAIGN_ID}/report")
    assert p.status_code == 403, p.text
