"""v2.621.0 — campaign backup export/import UI (backup/export-import Phase 9).

The campaign settings Import/Export tab gains a full-campaign backup section:
an export button (job + progress toast) and a clone-import upload. This is a
frontend-only change (the endpoints it drives are covered by
test_export_campaign.py / test_import_campaign.py); this smoke guards the
template + JS wiring renders so a future edit can't silently drop it.
"""
import httpx

from .conftest import CAMPAIGN_ID


async def test_campaign_settings_renders_backup_ui(gm_client: httpx.AsyncClient):
    """The settings page (GM) renders the backup export + import controls and
    wires them to the Phase 4/6b endpoints."""
    resp = await gm_client.get(f"/campaign/{CAMPAIGN_ID}/settings")
    assert resp.status_code == 200, resp.text
    html = resp.text

    # The two new controls are present.
    assert 'id="campaign-backup-btn"' in html
    assert 'id="campaign-import-btn"' in html
    assert 'id="campaign-import-file"' in html

    # The JS wires them to the real endpoints + job-poll surface.
    assert "/api/export-jobs/" in html       # progress poll
    assert "/api/campaign/import" in html     # clone import
    # The progress toast is driven off the job status fields.
    assert "Building backup" in html
