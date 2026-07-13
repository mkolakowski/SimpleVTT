"""v2.1006.0 — /api/settings/map_controls — per-user tabletop
map-control scheme.

Default (alternative=False) is the new scroll-to-pan scheme: a bare
mouse wheel pans the map (vertical wheel → Y, horizontal wheel /
Shift+wheel → X) and Ctrl+wheel zooms at the cursor. alternative=True
("Alternative controls") restores the pre-v2.1006.0 behavior where a
bare wheel zooms. The tabletop reads the flag via ``ME.altControls``
(templated off ``user.alternative_controls``); right-drag and
left-drag-on-empty panning work in both schemes.

Tests:
  - happy path: POST {alternative: true} → 200 + persisted; POST
    {alternative: false} flips back to the default.
  - per-user: Alice's preference is independent of the GM's.
  - error path: missing body field → 422 (pydantic validation).
  - the /settings page renders the new Map controls section + the
    v2.1006.0 group reorganization headers, and the tabletop's ME
    bootstrap carries altControls.
"""
from .conftest import CAMPAIGN_ID


async def test_map_controls_alternative_on_then_off(gm_client):
    """Toggle alternative controls on, then back off. Both persist."""
    resp = await gm_client.post(
        "/api/settings/map_controls",
        json={"alternative": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["alternative_controls"] is True

    resp = await gm_client.post(
        "/api/settings/map_controls",
        json={"alternative": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["alternative_controls"] is False


async def test_map_controls_persists_for_player(alice_client):
    """Per-user — Alice's preference is independent of the GM's."""
    resp = await alice_client.post(
        "/api/settings/map_controls",
        json={"alternative": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["alternative_controls"] is True
    # Flip back to the default so demo Alice keeps scroll-to-pan.
    resp = await alice_client.post(
        "/api/settings/map_controls",
        json={"alternative": False},
    )
    assert resp.status_code == 200, resp.text


async def test_map_controls_missing_field_422(gm_client):
    """Error path — pydantic rejects a body without `alternative`."""
    resp = await gm_client.post("/api/settings/map_controls", json={})
    assert resp.status_code == 422, resp.text


async def test_settings_page_renders_map_controls_and_groups(gm_client):
    """The /settings page carries the new Map controls section and the
    v2.1006.0 group reorganization (Appearance / Tabletop & controls /
    Gameplay / Audio headers)."""
    resp = await gm_client.get("/settings")
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "Map controls" in body
    assert "Scroll to pan (default)" in body
    assert "Alternative controls (wheel zooms)" in body
    assert "/api/settings/map_controls" in body
    for header in (
        "🎨 Appearance", "Tabletop &amp; controls", "⚔️ Gameplay", "🎵 Audio",
    ):
        assert header in body, f"missing settings group header {header!r}"


async def test_tabletop_bootstraps_alt_controls_flag(gm_client):
    """The tabletop page's ME bootstrap carries altControls so
    tabletop.js can pick the wheel scheme."""
    resp = await gm_client.get(f"/campaign/{CAMPAIGN_ID}")
    assert resp.status_code == 200, resp.text
    assert "altControls:" in resp.text
