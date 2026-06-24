"""v2.613.0 — item-level homebrew export (backup/export-import Phase 3).

``GET /api/campaign/{cid}/homebrew/{type}/{slug}/export`` returns a single
homebrew record as a one-row ``simplevtt-homebrew`` pack that round-trips
straight back through ``/homebrew/import``. GM-only, rate-limited per
campaign (bypassed under TEST_MODE).

The demo campaign seeds ``monsters/goblin-captain`` + ``feats/lucky-strike``
(see ``app/demo_seed.py::seed_homebrew_files``), the deterministic targets
used here.

Note on the cooldown: the live per-campaign homebrew cooldown is bypassed in
the CI harness container (TEST_MODE=true). The error-path assertions are
ordered before any successful export so they never trip a 429 even on a
local stack running with the cooldown live.
"""
import httpx

from .conftest import CAMPAIGN_ID


async def test_export_homebrew_item_errors(
    gm_client: httpx.AsyncClient, bob_client: httpx.AsyncClient,
):
    """403 for a non-GM and 404 for an unknown type — both resolve before
    the rate-limiter, so they never mark the cooldown."""
    base = f"/api/campaign/{CAMPAIGN_ID}/homebrew"

    # Non-GM member is refused by the GM guard.
    resp = await bob_client.get(f"{base}/monsters/goblin-captain/export")
    assert resp.status_code == 403, resp.text

    # Unknown content type 404s (guarded before the limiter).
    resp = await gm_client.get(f"{base}/widgets/goblin-captain/export")
    assert resp.status_code == 404, resp.text


async def test_export_homebrew_item_happy_path(gm_client: httpx.AsyncClient):
    """A shipped-SRD slug + an unknown slug 404 (only the campaign's own
    homebrew is exportable), then the seeded custom monster exports as a
    one-row simplevtt-homebrew pack."""
    base = f"/api/campaign/{CAMPAIGN_ID}/homebrew"

    # A shipped SRD monster is NOT exportable through the homebrew surface.
    resp = await gm_client.get(f"{base}/monsters/goblin/export")
    assert resp.status_code == 404, resp.text

    # An unknown slug 404s (resolves before the success-only cooldown mark).
    resp = await gm_client.get(f"{base}/monsters/nonesuch-xyz/export")
    assert resp.status_code == 404, resp.text

    # Happy path — the seeded custom Goblin Captain.
    resp = await gm_client.get(f"{base}/monsters/goblin-captain/export")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Envelope matches the bulk-export / importer shape.
    assert body["format"] == "simplevtt-homebrew"
    assert body["version"] >= 1
    assert "exported_at" in body

    # Exactly the one requested monster, projected to the legacy export row.
    monsters = body["monsters"]
    assert isinstance(monsters, list) and len(monsters) == 1
    row = monsters[0]
    assert row["monster_slug"] == "goblin-captain"
    assert row["name"] == "Goblin Captain"
    # The pack carries only the monster list (single-item, partial envelope).
    assert "classes" not in body or body.get("classes") in (None, [])
