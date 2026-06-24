"""v2.612.6 — simplevtt-export zip primitives (backup/export-import Phase 2).

``app/export_bundle.py`` carries the mechanics every export level shares:
generic ORM-row projection, media-URL discovery, the manifest envelope, and
the zip writer. Pure (only SQLAlchemy), so these run host-side with no
container. The per-level data-tree assembly + endpoints land in Phase 4.
"""
import json
import zipfile

import pytest

from app.export_bundle import (
    EXPORT_FORMAT,
    EXPORT_VERSION,
    abs_path_for_url,
    archive_path_for,
    build_manifest,
    find_media_urls,
    row_to_dict,
    write_bundle_zip,
)


def test_find_media_urls_recurses_and_dedupes():
    data = {
        "portrait_url": "/static/uploads/portraits/a.png",
        "nested": {"image_url": "/static/uploads/tokens/b.png", "name": "x"},
        "list": [
            {"file_url": "/static/uploads/audio/c.mp3"},
            {"file_url": "/static/uploads/audio/c.mp3"},  # dupe
            {"external": "https://example.com/not-bundled.png"},
        ],
        "no_media": "just a string",
    }
    urls = find_media_urls(data)
    assert urls == [
        "/static/uploads/portraits/a.png",
        "/static/uploads/tokens/b.png",
        "/static/uploads/audio/c.mp3",
    ]


def test_archive_and_abs_path_mapping(tmp_path):
    url = "/static/uploads/maps/x.png"
    assert archive_path_for(url) == "media/maps/x.png"
    abs_p = abs_path_for_url(url, static_root=tmp_path)
    assert abs_p == tmp_path / "uploads/maps/x.png"
    # A non-uploads URL is not a bundle source.
    assert abs_path_for_url("https://example.com/x.png", static_root=tmp_path) is None


def test_row_to_dict_is_json_safe():
    pytest.importorskip("sqlalchemy")
    from app.models import Map

    # Transient instance — no session/DB needed. Datetime/enum columns are
    # coerced; unset columns read as None.
    m = Map(campaign_id=7, name="Cavern", image_url="/static/uploads/maps/x.png")
    d = row_to_dict(m)
    assert d["campaign_id"] == 7
    assert d["name"] == "Cavern"
    assert d["image_url"] == "/static/uploads/maps/x.png"
    # The whole dict must be JSON-serializable (the point of _json_safe).
    json.dumps(d)


def test_build_manifest_envelope():
    man = build_manifest(
        "campaign",
        app_version="2.612.6",
        schema_version=80,
        exported_at="2026-06-24T00:00:00Z",
        source_campaign_id=3,
        source_campaign_name="Quest",
        counts={"characters": 2},
    )
    assert man["format"] == EXPORT_FORMAT
    assert man["version"] == EXPORT_VERSION
    assert man["level"] == "campaign"
    assert man["source_campaign_id"] == 3
    assert man["counts"] == {"characters": 2}
    assert man["media_manifest"] == []


def test_write_bundle_zip_round_trip(tmp_path):
    # A real media source on disk + a stale one that must be skipped.
    media_src = tmp_path / "uploads" / "maps" / "x.png"
    media_src.parent.mkdir(parents=True)
    media_src.write_bytes(b"\x89PNG fake")
    missing_src = tmp_path / "uploads" / "maps" / "gone.png"

    manifest = build_manifest(
        "campaign", app_version="2.612.6", schema_version=80,
        exported_at="2026-06-24T00:00:00Z",
    )
    zip_path = tmp_path / "out" / "bundle.zip"
    write_bundle_zip(
        zip_path,
        manifest=manifest,
        data_files={"data/campaign.json": {"name": "Quest"}},
        media_files=[
            ("media/maps/x.png", media_src),
            ("media/maps/gone.png", missing_src),  # skipped, not fatal
        ],
    )

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "data/campaign.json" in names
        assert "media/maps/x.png" in names
        # The missing source was skipped rather than aborting the write.
        assert "media/maps/gone.png" not in names

        man = json.loads(zf.read("manifest.json"))
        assert man["level"] == "campaign"
        assert json.loads(zf.read("data/campaign.json"))["name"] == "Quest"
        assert zf.read("media/maps/x.png") == b"\x89PNG fake"
