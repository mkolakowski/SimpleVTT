"""v2.614.0 — campaign-level zip export job (backup/export-import Phase 4).

``POST /api/campaign/{cid}/export`` starts a background build and returns a
``job_id``; ``GET /api/export-jobs/{id}`` polls progress; ``GET
/api/export-jobs/{id}/download`` streams the finished ``simplevtt-export`` zip.

The per-campaign export cooldown (``EXPORT_COOLDOWN_CAMPAIGN_SECONDS``) is
bypassed in the CI harness container (TEST_MODE=true) but live on a plain
stack, so the POST-driven tests skip cleanly on a 429 rather than flaking.
The cooldown's pure logic is covered in ``test_export_limit.py``.
"""
import asyncio
import io
import json
import zipfile

import httpx
import pytest

from .conftest import CAMPAIGN_ID


async def _poll_until_done(client: httpx.AsyncClient, job_id: str, *, tries: int = 80) -> dict:
    status = None
    for _ in range(tries):
        r = await client.get(f"/api/export-jobs/{job_id}")
        assert r.status_code == 200, r.text
        status = r.json()
        if status["status"] in ("done", "error"):
            return status
        await asyncio.sleep(0.5)
    raise AssertionError(f"export job {job_id} did not finish: {status}")


async def test_export_job_unknown_404(gm_client: httpx.AsyncClient):
    """An unknown job id 404s (no POST needed — always runs)."""
    r = await gm_client.get("/api/export-jobs/deadbeefdeadbeef")
    assert r.status_code == 404, r.text


async def test_campaign_export_round_trip_and_auth(
    gm_client: httpx.AsyncClient, bob_client: httpx.AsyncClient,
):
    """Full happy path (start → poll → download a valid zip) plus the
    ownership guard (a different user can't poll or download the job)."""
    resp = await gm_client.post(f"/api/campaign/{CAMPAIGN_ID}/export")
    if resp.status_code == 429:
        pytest.skip("campaign export cooldown active (non-TEST_MODE stack)")
    assert resp.status_code == 200, resp.text
    job = resp.json()
    job_id = job["job_id"]
    assert job["status"] == "running"

    # Ownership: a non-owner can't poll or download this job.
    r = await bob_client.get(f"/api/export-jobs/{job_id}")
    assert r.status_code == 403, r.text
    r = await bob_client.get(f"/api/export-jobs/{job_id}/download")
    assert r.status_code in (403, 409), r.text

    # Poll to completion.
    status = await _poll_until_done(gm_client, job_id)
    assert status["status"] == "done", status
    assert status["download_url"] == f"/api/export-jobs/{job_id}/download"

    # Download + inspect the archive.
    d = await gm_client.get(f"/api/export-jobs/{job_id}/download")
    assert d.status_code == 200, d.text
    assert "application/zip" in d.headers.get("content-type", "")

    zf = zipfile.ZipFile(io.BytesIO(d.content))
    names = set(zf.namelist())
    assert "manifest.json" in names
    assert "data/campaign.json" in names
    # The homebrew pack rides along in the same simplevtt-homebrew shape.
    assert "data/homebrew.json" in names

    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["format"] == "simplevtt-export"
    assert manifest["level"] == "campaign"
    assert manifest["source_campaign_id"] == CAMPAIGN_ID
    # Counts envelope is populated for the demo campaign's child tree.
    assert "characters" in manifest["counts"]
    assert manifest["counts"]["characters"] >= 1

    # data/campaign.json is the campaign row.
    camp = json.loads(zf.read("data/campaign.json"))
    assert camp["id"] == CAMPAIGN_ID
