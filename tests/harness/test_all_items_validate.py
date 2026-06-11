"""v2.159.16 — magic-items-automation Phase 8p: boot-time item-schema
validator + the new /api/content-health endpoint that mirrors its
result. v2.159.23 — Phase 8q extends from items-only to all nine
content types (races / class_features / subclass_features / spells /
items / feats / backgrounds / monsters / conditions).

Filed in the v2.158.83 retro: the Pearl ``key`` / ``id`` bug shipped
silently because the only runtime validator was per-endpoint
(``/api/content/items/{slug}``) — content only got checked when
fetched. The boot-time sweep walks every JSON at app startup and
stashes the result; this harness asserts the result is empty on every
CI run.

If a future commit ships a malformed JSON for any content type, the
v2.159.16 startup hook in ``app/main.py::on_startup`` logs the error
but the app still boots (so existing operators don't get a crash on
old content that's been silently broken). The harness is the
assertive gate: it red-lights the regression before merge.

Tests:
  - GET /api/content-health → 200 with per-type maps;
    asserts errors is empty for EVERY content type.
  - Smoke regression that the validator walked the right dirs (each
    type has at least a sane minimum count).
"""
import pytest

from .conftest import CAMPAIGN_ID  # noqa: F401 — module load order


_MIN_COUNTS = {
    "races": 5,
    "class_features": 10,
    "subclass_features": 10,
    "spells": 100,  # 319 SRD spells ship
    "items": 100,   # 292 SRD items
    "feats": 1,
    "backgrounds": 1,
    "monsters": 100,  # 322 SRD monsters
    "conditions": 10,
}


@pytest.mark.asyncio
async def test_content_health_endpoint_reports_zero_errors_for_all_types(
    gm_client,
):
    """v2.159.23 — Phase 8q happy path. GET /api/content-health → 200
    with per-type maps. EVERY content type must have empty errors. If
    any type has errors, the failure message lists the offending files
    so the regression is fixable from the test output alone.
    """
    resp = await gm_client.get("/api/content-health")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    failures = []
    for type_name, payload in data.items():
        if not isinstance(payload, dict):
            continue
        errors = payload.get("errors") or []
        if errors:
            for e in errors:
                failures.append(
                    f"{type_name}/{e.get('file')}: {e.get('error')}"
                )
    assert not failures, (
        f"{len(failures)} content record(s) failed schema validation:\n"
        + "\n".join(f"  {f}" for f in failures)
    )


@pytest.mark.asyncio
async def test_content_health_checked_minimums_per_type(gm_client):
    """v2.159.23 — Phase 8q regression. Each content type has a
    minimum-file-count gate so a validator walking the wrong dir
    returns a noisy red instead of a silent green.
    """
    resp = await gm_client.get("/api/content-health")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for type_name, min_n in _MIN_COUNTS.items():
        payload = data.get(type_name) or {}
        checked = int(payload.get("checked") or 0)
        assert checked >= min_n, (
            f"{type_name}: expected ≥ {min_n} records checked, got {checked}"
        )


@pytest.mark.asyncio
async def test_content_health_covers_all_nine_types(gm_client):
    """v2.159.23 — Phase 8q regression. Every type key in
    ``content_schemas.TYPE_REGISTRY`` must appear in the response.
    """
    resp = await gm_client.get("/api/content-health")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    expected = set(_MIN_COUNTS)
    actual = set(data.keys())
    missing = expected - actual
    assert not missing, (
        f"missing content types in response: {sorted(missing)}; "
        f"response had: {sorted(actual)}"
    )
