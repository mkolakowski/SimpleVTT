"""v2.615.0 — PC sheet export (backup/export-import Phase 5).

``GET /api/character/{id}/export`` returns a single PC as a synchronous
``simplevtt-export`` zip (level=character): the sheet (stats/notes/portrait
ref), that character's own dice rolls, and its media — never any campaign-wide
data. Allowed for the character's owner or its campaign GM.

Per-character cooldown (``EXPORT_COOLDOWN_CHARACTER_SECONDS``) is bypassed in
CI (TEST_MODE) but live on a plain stack, so the successful exports skip on a
429 rather than flaking.
"""
import io
import json
import zipfile

import httpx
import pytest


async def test_export_character_owner_no_campaign_leak(
    alice_client: httpx.AsyncClient, roster: dict,
):
    """The owner exports their PC; the archive is character-scoped — no
    maps / tokens / campaign / homebrew leak into it."""
    pip = roster["Pip Quickfingers"]["id"]
    resp = await alice_client.get(f"/api/character/{pip}/export")
    if resp.status_code == 429:
        pytest.skip("character export cooldown active (non-TEST_MODE stack)")
    assert resp.status_code == 200, resp.text
    assert "application/zip" in resp.headers.get("content-type", "")

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = set(zf.namelist())
    assert "manifest.json" in names
    assert "data/character.json" in names
    assert "data/dice_rolls.json" in names
    # Character-scoped: campaign-wide collections must NOT be present.
    assert "data/campaign.json" not in names
    assert "data/tokens.json" not in names
    assert "data/homebrew.json" not in names
    assert not any(n.startswith("data/maps/") for n in names)

    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["format"] == "simplevtt-export"
    assert manifest["level"] == "character"

    char = json.loads(zf.read("data/character.json"))
    assert char["id"] == pip
    assert char["name"] == "Pip Quickfingers"


async def test_export_character_gm_allowed(
    gm_client: httpx.AsyncClient, roster: dict,
):
    """The campaign GM may export any PC in the campaign (distinct character
    from the owner test so the per-character cooldown doesn't collide)."""
    garrik = roster["Garrik Ironside"]["id"]
    resp = await gm_client.get(f"/api/character/{garrik}/export")
    if resp.status_code == 429:
        pytest.skip("character export cooldown active (non-TEST_MODE stack)")
    assert resp.status_code == 200, resp.text
    manifest = json.loads(zipfile.ZipFile(io.BytesIO(resp.content)).read("manifest.json"))
    assert manifest["level"] == "character"


async def test_export_character_errors(
    bob_client: httpx.AsyncClient, gm_client: httpx.AsyncClient, roster: dict,
):
    """A non-owner non-GM player is 403; an unknown character is 404. Both
    resolve before the rate-limiter."""
    pip = roster["Pip Quickfingers"]["id"]
    r = await bob_client.get(f"/api/character/{pip}/export")
    assert r.status_code == 403, r.text

    r = await gm_client.get("/api/character/999999/export")
    assert r.status_code == 404, r.text
