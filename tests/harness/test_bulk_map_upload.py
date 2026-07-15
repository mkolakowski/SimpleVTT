"""v2.1024.0 — Bulk map upload.

`POST /campaign/{cid}/settings/maps/bulk` accepts multiple image files in
one request and creates a Map per file — each named from its filename —
with the shared grid settings applied to all. Returns a JSON summary
(created / skipped / maps / errors). GM-only; bad files are skipped
(recorded in `errors`) rather than failing the whole batch.

Tests:
  - 3 PNGs → created 3, names derived from filenames; cleaned up after.
  - A mix of a valid PNG + a bad (text) file → created 1, skipped 1,
    the bad file named in errors.
  - A player → 403.
  - No files → 400.
"""
import io

from .conftest import CAMPAIGN_ID

# 1x1 transparent PNG (same tiny asset the background tests use).
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63000100000005000100"
    "0d0a2db40000000049454e44ae426082"
)


def _png(name):
    return ("images", (name, io.BytesIO(_PNG), "image/png"))


async def _delete_maps(gm_client, map_ids):
    for mid in map_ids:
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/maps/{mid}/delete")


async def test_bulk_upload_creates_multiple(gm_client):
    files = [
        _png("goblin-cave.png"),
        _png("tavern_interior.png"),
        _png("Forest Clearing.png"),
    ]
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/bulk",
        data={"grid_type": "square", "grid_size_px": "70", "show_grid": "1",
              "folder": "BulkTest", "tags": "bulk,test"},
        files=files,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    try:
        assert d["created"] == 3, d
        assert d["skipped"] == 0, d
        names = {m["name"] for m in d["maps"]}
        # Names derived + cleaned from the filenames.
        assert "Goblin Cave" in names
        assert "Tavern Interior" in names
        assert "Forest Clearing" in names
    finally:
        await _delete_maps(gm_client, [m["id"] for m in d.get("maps", [])])


async def test_bulk_upload_skips_bad_files(gm_client):
    files = [
        _png("good-map.png"),
        ("images", ("notes.txt", io.BytesIO(b"not an image"), "text/plain")),
    ]
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/bulk",
        data={"grid_type": "square", "grid_size_px": "70"},
        files=files,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    try:
        assert d["created"] == 1, d
        assert d["skipped"] == 1, d
        assert any(e["filename"] == "notes.txt" for e in d["errors"]), d
        assert d["maps"][0]["name"] == "Good Map"
    finally:
        await _delete_maps(gm_client, [m["id"] for m in d.get("maps", [])])


async def test_bulk_upload_gm_only(alice_client):
    r = await alice_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/bulk",
        data={"grid_type": "square"},
        files=[_png("x.png")],
    )
    assert r.status_code == 403, r.text


async def test_bulk_upload_no_files(gm_client):
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/settings/maps/bulk",
        data={"grid_type": "square"},
    )
    assert r.status_code in (400, 422), r.text
