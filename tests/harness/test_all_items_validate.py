"""v2.159.16 — magic-items-automation Phase 8p: boot-time item-schema
validator + the new /api/content-health endpoint that mirrors its
result.

Filed in the v2.158.83 retro: the Pearl ``key`` / ``id`` bug shipped
silently because the only runtime validator was per-endpoint
(``/api/content/items/{slug}``) — items only get checked when
fetched. The boot-time sweep walks every item JSON at app startup and
stashes the result; this harness asserts the result is empty on every
CI run.

If a future commit ships a malformed item JSON, the v2.159.16 startup
hook in ``app/main.py::on_startup`` logs the error but the app still
boots (so existing operators don't get a crash on an old item that's
been silently broken). The harness is the assertive gate: it red-
lights the regression before merge.

Tests:
  - GET /api/content-health → 200 with {items: {checked, errors}};
    asserts errors is empty.
  - Smoke that checked >= 100 (regression guard — if the count drops
    drastically, something walked the wrong dir).
"""
import pytest

from .conftest import CAMPAIGN_ID  # noqa: F401 — module load order


@pytest.mark.asyncio
async def test_content_health_endpoint_reports_zero_item_errors(
    gm_client,
):
    """v2.159.16 happy path. GET /api/content-health → 200 with the
    item-validator's boot-time result. ``errors`` should be empty
    (every shipped item validates cleanly). If a future commit ships
    a malformed item JSON, this test fails CI before merge — the
    failure body lists the offending files.
    """
    resp = await gm_client.get("/api/content-health")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    items = data.get("items") or {}
    errors = items.get("errors") or []
    assert errors == [], (
        f"{len(errors)} item(s) failed schema validation:\n"
        + "\n".join(
            f"  {e.get('file')}: {e.get('error')}" for e in errors
        )
    )


@pytest.mark.asyncio
async def test_content_health_checked_at_least_100_items(
    gm_client,
):
    """v2.159.16 — regression guard. The v2.158.73 note says 292 SRD
    items ship; if the count drops below 100, the validator probably
    walked the wrong dir + the "all items validate" check would give
    a false-OK by walking zero files.
    """
    resp = await gm_client.get("/api/content-health")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    items = data.get("items") or {}
    assert items.get("checked", 0) >= 100, (
        f"expected ≥ 100 items checked, got {items.get('checked')}"
    )
