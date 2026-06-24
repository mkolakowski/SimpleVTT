"""v2.616.0 — character import, clone mode (backup/export-import Phase 6).

``POST /api/campaign/{cid}/character/import`` (GM-only) re-places a
``simplevtt-export`` (level=character) zip as a brand-new character owned by
the importing GM, with bundled media rewritten to fresh uuids.

The endpoint tests build synthetic archives (so they don't depend on the
export endpoint's cooldown) and clean up the created character afterward. The
reader primitives in ``app/import_bundle.py`` get pure host-side unit tests.
"""
import io
import json
import zipfile

import httpx
import pytest

from .conftest import CAMPAIGN_ID


def _char_zip(*, name="Imported Test Hero", level="character", with_media=False):
    """Build a minimal simplevtt-export character archive in memory."""
    buf = io.BytesIO()
    manifest = {"format": "simplevtt-export", "version": 1, "level": level}
    char = {"name": name, "template": "dnd5e", "sheet": {"abilities": {"str": 12}}}
    if with_media:
        char["portrait_url"] = "/static/uploads/portraits/orig.png"
        manifest["media_manifest"] = [
            {"archive_path": "media/portraits/orig.png",
             "original_url": "/static/uploads/portraits/orig.png"},
        ]
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("data/character.json", json.dumps(char))
        if with_media:
            zf.writestr("media/portraits/orig.png", b"\x89PNG fake")
    return buf.getvalue()


# ---- pure reader primitives (host-side, no container) ----------------

def test_read_manifest_validation():
    from app import import_bundle as ib

    # Wrong format → BundleError.
    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": "nope", "version": 1}))
    with pytest.raises(ib.BundleError):
        ib.read_manifest(ib.open_archive(bad.getvalue()))

    # Level mismatch → BundleError.
    zf = ib.open_archive(_char_zip(level="campaign"))
    with pytest.raises(ib.BundleError):
        ib.read_manifest(zf, expected_level="character")

    # Good archive → manifest returned.
    zf = ib.open_archive(_char_zip())
    man = ib.read_manifest(zf, expected_level="character")
    assert man["level"] == "character"


def test_extract_media_fresh_uuid_and_rewrite(tmp_path):
    from app import import_bundle as ib

    zf = ib.open_archive(_char_zip(with_media=True))
    manifest = ib.read_manifest(zf, expected_level="character")
    url_map = ib.extract_media(zf, manifest, uploads_root=tmp_path)

    orig = "/static/uploads/portraits/orig.png"
    assert orig in url_map
    new_url = url_map[orig]
    # Fresh server-generated name under the same bucket — not the archive name.
    assert new_url.startswith("/static/uploads/portraits/")
    assert "orig.png" not in new_url
    assert (tmp_path / new_url[len("/static/uploads/"):]).read_bytes() == b"\x89PNG fake"

    # rewrite threads the new url through the data.
    rewritten = ib.rewrite_urls({"portrait_url": orig, "x": [orig, "keep"]}, url_map)
    assert rewritten["portrait_url"] == new_url
    assert rewritten["x"] == [new_url, "keep"]


# ---- live endpoint ---------------------------------------------------

async def test_import_character_clone_round_trip(gm_client: httpx.AsyncClient):
    """GM imports a synthetic character archive → a new character is created;
    cleaned up afterward so the demo roster isn't polluted."""
    files = {"file": ("char.zip", _char_zip(name="Imported Test Hero"), "application/zip")}
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/import",
        files=files, data={"mode": "clone"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    new_id = body["character_id"]
    assert isinstance(new_id, int)
    assert body["name"] == "Imported Test Hero"
    try:
        # The new character is in the campaign roster.
        r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/roster")
        names = {c["name"] for c in r.json()["characters"]}
        assert "Imported Test Hero" in names
    finally:
        # Detach the clone from the campaign so the roster stays clean.
        await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/settings/characters/{new_id}/delete"
        )


async def test_import_character_errors(
    gm_client: httpx.AsyncClient, bob_client: httpx.AsyncClient,
):
    """Non-zip → 400, wrong-level archive → 400, non-GM → 403."""
    # Not a zip.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/import",
        files={"file": ("x.zip", b"not a zip", "application/zip")},
        data={"mode": "clone"},
    )
    assert r.status_code == 400, r.text

    # Wrong level (campaign archive sent to the character importer).
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/import",
        files={"file": ("c.zip", _char_zip(level="campaign"), "application/zip")},
        data={"mode": "clone"},
    )
    assert r.status_code == 400, r.text

    # Non-GM member is refused.
    r = await bob_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/import",
        files={"file": ("char.zip", _char_zip(), "application/zip")},
        data={"mode": "clone"},
    )
    assert r.status_code == 403, r.text
