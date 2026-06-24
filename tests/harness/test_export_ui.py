"""v2.621.0 — campaign backup export/import UI (backup/export-import Phase 9).

The campaign settings Import/Export tab gains a full-campaign backup section:
an export button (job + progress toast) and a clone-import upload. This is a
frontend-only change (the endpoints it drives are covered by
test_export_campaign.py / test_import_campaign.py); this smoke guards the
template + JS wiring renders so a future edit can't silently drop it.
"""
import httpx

from .conftest import CAMPAIGN_ID
from .helpers import BASE_URL


async def test_campaign_settings_renders_backup_ui(gm_client: httpx.AsyncClient):
    """The settings page (GM) renders the backup export + import controls and
    wires them to the Phase 4/6b endpoints."""
    resp = await gm_client.get(f"/campaign/{CAMPAIGN_ID}/settings")
    assert resp.status_code == 200, resp.text
    html = resp.text

    # v2.625.1 — Import & export is now its own top-level settings tab.
    assert 'data-tab="import-export"' in html
    assert 'id="custom-io" data-tab="import-export"' in html

    # The two new controls are present.
    assert 'id="campaign-backup-btn"' in html
    assert 'id="campaign-import-btn"' in html
    assert 'id="campaign-import-file"' in html

    # The JS wires them to the real endpoints + job-poll surface.
    assert "/api/export-jobs/" in html       # progress poll
    assert "/api/campaign/import" in html     # clone import
    # The progress toast is driven off the job status fields.
    assert "Building backup" in html


async def test_character_page_has_export_link(alice_client: httpx.AsyncClient, roster: dict):
    """v2.623.0 (9b) — the character page renders the PC-sheet export download
    link for the owner."""
    pip = roster["Pip Quickfingers"]["id"]
    resp = await alice_client.get(f"/campaign/{CAMPAIGN_ID}/character/{pip}/sheet")
    assert resp.status_code == 200, resp.text
    assert f"/api/character/{pip}/export" in resp.text
    assert "Export sheet" in resp.text


async def test_homebrew_workshop_has_export_button():
    """v2.623.0 (9b) — the homebrew workshop JS renders a per-row Export button
    wired to the item-level homebrew export endpoint."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/static/homebrew_workshop.js")
    assert resp.status_code == 200
    js = resp.text
    assert "hbw-export" in js
    assert "/homebrew/${ex.dataset.type}/${ex.dataset.slug}/export" in js
