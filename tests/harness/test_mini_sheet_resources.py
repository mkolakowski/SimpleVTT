"""v2.744.0 — class-resource trackers in the mini-sheet.

The tabletop's per-character mini-sheet (`_mini_sheet_card.html`) now renders
each countable class/subclass resource (Rage, Ki, Bardic Inspiration, …) with
+/- steppers wired to the existing `POST /resource` endpoint and the
`resource_update` WS broadcast. This covers:

  - the tabletop page server-renders the `.msb-res*` markup + data attributes
    the stepper JS reads, for a PC that has persisted resources;
  - the spend/restore round-trip the steppers call (delta -1 then reset);
  - the error path (unknown resource key → 404).
"""
from .conftest import CAMPAIGN_ID


async def _pip_resource_key(gm_client, pip_id):
    sheet = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip_id}/sheet-json"
    )).json()["sheet"]
    for r in (sheet.get("resources") or []):
        if int(r.get("max") or 0) > 0 and r.get("key"):
            return r["key"], int(r.get("current") or 0), int(r["max"])
    return None, 0, 0


async def test_tabletop_renders_resource_trackers(gm_client):
    r = await gm_client.get(f"/campaign/{CAMPAIGN_ID}")
    assert r.status_code == 200, r.status_code
    html = r.text
    # The container + pip count span + at least one stepper button.
    assert "msb-resources" in html
    assert "msb-res-cur" in html
    assert "msb-res-step" in html
    # The stepper carries the data the JS reads.
    assert 'data-res-key="' in html and 'data-delta="-1"' in html


async def test_resource_spend_and_restore_round_trip(gm_client, roster):
    """The +/- steppers POST {key, delta}; spend decrements + broadcasts, and a
    reset refills. Leaves the demo resource back at full so other suites + the
    click-through demo see unchanged state."""
    pip = roster["Pip Quickfingers"]
    key, cur, mx = await _pip_resource_key(gm_client, pip["id"])
    assert key, "Pip should have a countable resource"
    url = f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/resource"
    try:
        spend = await gm_client.post(url, json={"key": key, "delta": -1})
        assert spend.status_code == 200, spend.text
        assert spend.json()["current"] == max(0, cur - 1)
    finally:
        # Refill to max (the value the steppers' "+" climbs back toward).
        restore = await gm_client.post(url, json={"key": key, "reset": True})
        assert restore.status_code == 200, restore.text
        assert restore.json()["current"] == mx


async def test_resource_unknown_key_404(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/resource",
        json={"key": "no-such-resource-xyz", "delta": -1})
    assert r.status_code == 404, r.text
