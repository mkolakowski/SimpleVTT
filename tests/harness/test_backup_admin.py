"""v2.620.0 — Admin Center operator backup settings (backup/export-import Phase 8).

The Admin Center's ``/backups`` page edits the automated-backup schedule +
retention by writing ``${BACKUP_DIR}/backup-settings.json`` on the shared
backup volume, which the sidecar watch-loop reads. Those routes live on the
Admin Center (port 8015, behind its own auth) — not the 8013 harness target —
so this covers the pure ``backup_admin`` helper host-side: settings read/write
round-trip, cron validation, retention clamping, demo-mode detection, and
artifact listing.
"""
from app.admin_center import backup_admin


def test_read_settings_env_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    monkeypatch.delenv("BACKUP_CRON", raising=False)
    monkeypatch.delenv("KEEP_DAILY", raising=False)
    monkeypatch.delenv("KEEP_WEEKLY", raising=False)
    s = backup_admin.read_settings()
    assert s["source"] == "env"            # no file yet
    assert s["cron"] == "0 3 * * *"
    assert s["keep_daily"] == 7
    assert s["keep_weekly"] == 4


def test_write_then_read_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    written = backup_admin.write_settings(
        cron="30 2 * * 0", keep_daily=14, keep_weekly=8,
        updated_by="alice", now_iso="2026-06-24T00:00:00Z",
    )
    assert written["cron"] == "30 2 * * 0"
    s = backup_admin.read_settings()
    assert s["source"] == "file"
    assert s["cron"] == "30 2 * * 0"
    assert s["keep_daily"] == 14
    assert s["keep_weekly"] == 8
    assert s["updated_by"] == "alice"
    assert (tmp_path / "backup-settings.json").is_file()


def test_validate_cron():
    assert backup_admin.validate_cron("0 3 * * *") is True
    assert backup_admin.validate_cron("*/5 * * * *") is True
    assert backup_admin.validate_cron("0 3 * *") is False    # 4 fields
    assert backup_admin.validate_cron("") is False
    assert backup_admin.validate_cron("   ") is False


def test_write_rejects_bad_cron(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    import pytest
    with pytest.raises(ValueError):
        backup_admin.write_settings(
            cron="not a cron", keep_daily=7, keep_weekly=4,
            updated_by="x", now_iso="2026-06-24T00:00:00Z",
        )


def test_retention_clamped(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    # 0 → min 1; 9999 → max 365; non-int → default.
    w = backup_admin.write_settings(
        cron="0 3 * * *", keep_daily=0, keep_weekly=9999,
        updated_by="x", now_iso="2026-06-24T00:00:00Z",
    )
    assert w["keep_daily"] == 1
    assert w["keep_weekly"] == 365


def test_demo_mode_active(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    assert backup_admin.demo_mode_active() is True
    monkeypatch.setenv("DEMO_MODE", "false")
    assert backup_admin.demo_mode_active() is False
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert backup_admin.demo_mode_active() is False


def test_trigger_run_and_list_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    # run-now trigger file is dropped.
    backup_admin.trigger_run()
    assert (tmp_path / ".run-now").is_file()

    # Artifacts under daily/ + weekly/ are listed (ignoring non-backup files).
    (tmp_path / "daily").mkdir()
    (tmp_path / "weekly").mkdir()
    (tmp_path / "daily" / "simplevtt-20260624T030000Z.sql.gz").write_bytes(b"x")
    (tmp_path / "daily" / "simplevtt-20260624T030000Z.homebrew.tar.gz").write_bytes(b"y")
    (tmp_path / "daily" / "notes.txt").write_bytes(b"ignore me")
    (tmp_path / "weekly" / "simplevtt-20260621T030000Z.sql.gz").write_bytes(b"z")

    arts = backup_admin.list_artifacts()
    daily_names = {a["name"] for a in arts["daily"]}
    assert "simplevtt-20260624T030000Z.sql.gz" in daily_names
    assert "simplevtt-20260624T030000Z.homebrew.tar.gz" in daily_names
    assert "notes.txt" not in daily_names      # only backup artifacts listed
    assert len(arts["weekly"]) == 1
