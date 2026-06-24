"""v2.617.0 — campaign-clone import (backup/export-import Phase 6b).

``POST /api/campaign/import?mode=clone`` (GM-role only) re-places a
``simplevtt-export`` (level=campaign) archive as a brand-new campaign,
FK-remapping the child tree (token a→map/char/template, encounter→map/playlist
+ payload refs, track→playlist) to fresh ids.

Uses a synthetic archive with cross-referencing ids so the remap is exercised
without depending on the campaign export job. Cleans up by archiving the
cloned campaign (the demo reseed also wipes demo-owned campaigns).
"""
import io
import json
import zipfile

import httpx


def _campaign_zip(level="campaign"):
    """A minimal cross-referencing campaign archive: 1 map, 1 character, 1
    NPC template, 1 token (→ all three), 1 playlist + track, 1 encounter
    (→ map + playlist + payload refs)."""
    buf = io.BytesIO()
    manifest = {"format": "simplevtt-export", "version": 1, "level": level}
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("data/campaign.json", json.dumps(
            {"id": 1, "name": "Clone Test Campaign", "description": "d", "game_system": "dnd5e"}))
        zf.writestr("data/characters/20.json", json.dumps(
            {"id": 20, "name": "Cloned Hero", "template": "dnd5e", "sheet": {"abilities": {"str": 10}}}))
        zf.writestr("data/maps/10.json", json.dumps(
            {"id": 10, "name": "Clone Map", "grid_type": "square", "width_px": 1000, "height_px": 800}))
        zf.writestr("data/token_templates.json", json.dumps(
            [{"id": 30, "name": "Clone NPC", "template": "generic", "sheet": {}}]))
        zf.writestr("data/tokens.json", json.dumps(
            [{"id": 50, "map_id": 10, "character_id": 20, "token_template_id": 30, "label": "T", "x": 1, "y": 2, "size": 1}]))
        zf.writestr("data/playlists.json", json.dumps(
            {"playlists": [{"id": 40, "name": "Clone Tunes"}],
             "tracks": [{"id": 60, "playlist_id": 40, "name": "Trk", "file_url": "/static/uploads/audio/x.mp3", "position": 0}]}))
        zf.writestr("data/encounters/70.json", json.dumps(
            {"id": 70, "name": "Clone Fight", "map_id": 10, "auto_play_playlist_id": 40,
             "payload": {"tokens": [{"character_id": 20, "template_id": 30, "x": 1, "y": 1}]}}))
        zf.writestr("data/handouts.json", json.dumps(
            [{"id": 80, "title": "Clone Letter", "body": "Dear hero", "revealed": True}]))
        zf.writestr("data/notes.json", json.dumps([
            {"id": 90, "kind": "gm_note", "visibility": "gm_only", "title": "Prep", "body": "plan", "is_encrypted": False},
            {"id": 91, "is_encrypted": True, "enc_title": "opaque", "enc_body": "opaque"},
        ]))
    return buf.getvalue()


async def test_campaign_import_clone_round_trip(gm_client: httpx.AsyncClient):
    """A whole-campaign archive clones into a new campaign with the full child
    tree remapped; cleaned up by archiving the clone afterward."""
    resp = await gm_client.post(
        "/api/campaign/import",
        files={"file": ("camp.zip", _campaign_zip(), "application/zip")},
        data={"mode": "clone"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    nc = body["campaign_id"]
    counts = body["counts"]
    assert counts["maps"] == 1
    assert counts["characters"] == 1
    assert counts["token_templates"] == 1
    assert counts["tokens"] == 1            # token's map/char/template all remapped
    assert counts["playlists"] == 1
    assert counts["playlist_tracks"] == 1   # track's playlist remapped
    assert counts["encounters"] == 1        # encounter's map/playlist remapped
    assert counts["handouts"] == 1
    assert counts["notes"] == 1                       # the non-encrypted note
    assert counts["notes_skipped_encrypted"] == 1     # the encrypted one skipped
    try:
        # The cloned character lives in the NEW campaign's roster.
        r = await gm_client.get(f"/api/campaign/{nc}/roster")
        assert r.status_code == 200, r.text
        names = {c["name"] for c in r.json()["characters"]}
        assert "Cloned Hero" in names
    finally:
        # Archive the clone so it drops out of the active lobby (demo reseed
        # wipes demo-owned campaigns regardless).
        await gm_client.post(f"/campaign/{nc}/archive")


async def test_campaign_import_errors(
    gm_client: httpx.AsyncClient, bob_client: httpx.AsyncClient,
):
    """Non-zip → 400, wrong-level archive → 400, non-GM-role → 403."""
    r = await gm_client.post(
        "/api/campaign/import",
        files={"file": ("x.zip", b"not a zip", "application/zip")},
        data={"mode": "clone"},
    )
    assert r.status_code == 400, r.text

    r = await gm_client.post(
        "/api/campaign/import",
        files={"file": ("c.zip", _campaign_zip(level="character"), "application/zip")},
        data={"mode": "clone"},
    )
    assert r.status_code == 400, r.text

    # A player without the GM role can't import a campaign.
    r = await bob_client.post(
        "/api/campaign/import",
        files={"file": ("c.zip", _campaign_zip(), "application/zip")},
        data={"mode": "clone"},
    )
    assert r.status_code == 403, r.text
