"""In-process unit tests for the import zip-bomb guard (v2.1040.0).

`app.import_bundle.open_archive` now rejects an archive whose declared
uncompressed total / per-entry size / entry count exceeds a ceiling, before any
member is read. `import_bundle` is FastAPI-free, so these run host-side.
"""
from __future__ import annotations

import io
import zipfile

import pytest

from app import import_bundle as ib


def _make_zip(members: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_small_archive_opens_ok():
    zf = ib.open_archive(_make_zip({"manifest.json": b"{}"}))
    assert zf is not None


def test_rejects_oversized_uncompressed_total(monkeypatch):
    monkeypatch.setenv("MAX_IMPORT_UNCOMPRESSED_BYTES", "10")
    raw = _make_zip({"big.bin": b"x" * 100})
    with pytest.raises(ib.BundleError):
        ib.open_archive(raw)


def test_rejects_oversized_single_entry(monkeypatch):
    monkeypatch.setattr(ib, "_MAX_ENTRY_UNCOMPRESSED_BYTES", 10)
    raw = _make_zip({"big.bin": b"y" * 100})
    with pytest.raises(ib.BundleError):
        ib.open_archive(raw)


def test_rejects_too_many_entries(monkeypatch):
    monkeypatch.setattr(ib, "_MAX_ARCHIVE_ENTRIES", 2)
    raw = _make_zip({"a": b"", "b": b"", "c": b""})
    with pytest.raises(ib.BundleError):
        ib.open_archive(raw)


def test_bad_zip_still_raises_bundle_error():
    with pytest.raises(ib.BundleError):
        ib.open_archive(b"not a zip at all")


def test_default_uncompressed_ceiling_is_1_gib(monkeypatch):
    monkeypatch.delenv("MAX_IMPORT_UNCOMPRESSED_BYTES", raising=False)
    assert ib._max_uncompressed_bytes() == 1024 * 1024 * 1024
