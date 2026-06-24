"""v2.620.0 — Admin Center operator backup settings (backup/export-import Phase 8).

The Admin Center's ``/backups`` page edits the automated-backup schedule +
retention by writing ``${BACKUP_DIR}/backup-settings.json`` on the shared
backup volume, which the sidecar watch-loop reads. Those routes live on the
Admin Center (port 8015, behind its own auth) — not the 8013 harness target —
so this covers the pure ``backup_admin`` helper host-side: settings read/write
round-trip, cron validation, retention clamping, demo-mode detection, and
artifact listing.
"""
import json

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
    monkeypatch.delenv("DEMO_BACKUPS_ENABLED", raising=False)
    monkeypatch.setenv("DEMO_MODE", "true")
    assert backup_admin.demo_mode_active() is True     # demo, no override → disabled
    # v2.629.0 — the testing override re-enables backups even in demo mode.
    monkeypatch.setenv("DEMO_BACKUPS_ENABLED", "true")
    assert backup_admin.backups_force_enabled() is True
    assert backup_admin.demo_mode_active() is False     # override → not disabled
    monkeypatch.delenv("DEMO_BACKUPS_ENABLED", raising=False)
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


def test_artifact_path_safe_resolution(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    (tmp_path / "daily").mkdir()
    good = tmp_path / "daily" / "simplevtt-20260624T030000Z.sql.gz"
    good.write_bytes(b"x")

    # A real backup file under daily/ resolves.
    assert backup_admin.artifact_path("daily", "simplevtt-20260624T030000Z.sql.gz") == good

    # Unknown bucket / traversal / bad suffix / missing file all return None.
    assert backup_admin.artifact_path("../etc", "simplevtt-x.sql.gz") is None
    assert backup_admin.artifact_path("daily", "../../etc/passwd") is None
    assert backup_admin.artifact_path("daily", "subdir/x.sql.gz") is None
    assert backup_admin.artifact_path("daily", "notes.txt") is None       # wrong suffix
    assert backup_admin.artifact_path("daily", "nonexistent.sql.gz") is None
    assert backup_admin.artifact_path("weekly", "simplevtt-20260624T030000Z.sql.gz") is None  # not in weekly


def test_list_backups_groups_by_timestamp(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    (tmp_path / "daily").mkdir()
    (tmp_path / "weekly").mkdir()
    ts = "20260624T030000Z"
    (tmp_path / "daily" / f"simplevtt-{ts}.sql.gz").write_bytes(b"aa")
    (tmp_path / "daily" / f"simplevtt-{ts}.homebrew.tar.gz").write_bytes(b"bbb")
    (tmp_path / "daily" / f"simplevtt-{ts}.uploads.tar.gz").write_bytes(b"cccc")
    (tmp_path / "daily" / "notes.txt").write_bytes(b"x")          # ignored
    (tmp_path / "weekly" / "simplevtt-20260623T030000Z.sql.gz").write_bytes(b"c")

    backups = backup_admin.list_backups()
    # The three daily files for one run group into a single backup.
    assert len(backups["daily"]) == 1
    g = backups["daily"][0]
    assert g["ts"] == ts
    assert len(g["files"]) == 3            # sql + homebrew + uploads
    assert g["size"] == 9                  # 2 + 3 + 4 bytes
    assert len(backups["weekly"]) == 1     # the lone sql.gz still counts as a backup


def test_backup_files_for_resolves_run_and_is_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    (tmp_path / "daily").mkdir()
    ts = "20260624T030000Z"
    (tmp_path / "daily" / f"simplevtt-{ts}.sql.gz").write_bytes(b"a")
    (tmp_path / "daily" / f"simplevtt-{ts}.homebrew.tar.gz").write_bytes(b"b")
    (tmp_path / "daily" / f"simplevtt-{ts}.uploads.tar.gz").write_bytes(b"c")

    paths = backup_admin.backup_files_for("daily", ts)
    assert len(paths) == 3                 # sql + homebrew + uploads
    assert all(p.is_file() for p in paths)

    # Bad timestamp / bucket / missing run → empty (traversal-proof).
    assert backup_admin.backup_files_for("daily", "../../etc") == []
    assert backup_admin.backup_files_for("evil", ts) == []
    assert backup_admin.backup_files_for("daily", "nonexistent") == []


def test_tags_surface_and_restore_request(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    (tmp_path / "daily").mkdir()
    ts = "20260624T030000Z"
    for suf in (".sql.gz", ".homebrew.tar.gz", ".uploads.tar.gz"):
        (tmp_path / "daily" / f"simplevtt-{ts}{suf}").write_bytes(b"x")
    (tmp_path / "daily" / f"simplevtt-{ts}.tag").write_text(
        "pre-restore safety backup (before restoring OTHER)", encoding="utf-8")

    # The tag surfaces on the grouped backup.
    g = backup_admin.list_backups()["daily"][0]
    assert g["ts"] == ts
    assert "pre-restore safety" in g["tag"]

    # request_restore writes the trigger for a real backup.
    assert backup_admin.restore_pending() is False
    assert backup_admin.request_restore(
        "daily", ts, requested_by="alice", now_iso="2026-06-24T00:00:00Z") is True
    assert backup_admin.restore_pending() is True
    req = json.loads((tmp_path / ".restore-request").read_text())
    assert req["bucket"] == "daily" and req["ts"] == ts and req["requested_by"] == "alice"

    # A second request is refused while one is pending.
    assert backup_admin.request_restore("daily", ts, requested_by="x", now_iso="t") is False


def test_request_restore_rejects_unknown_and_reads_result(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    (tmp_path / "daily").mkdir()
    # No such backup → not queued, no trigger written.
    assert backup_admin.request_restore(
        "daily", "20260101T000000Z", requested_by="x", now_iso="t") is False
    assert backup_admin.restore_pending() is False
    assert backup_admin.last_restore_result() is None

    # A result file written by the sidecar is read back.
    (tmp_path / ".restore-result").write_text(
        json.dumps({"ok": True, "ts": "20260624T030000Z", "db_ok": 1}), encoding="utf-8")
    res = backup_admin.last_restore_result()
    assert res["ok"] is True and res["ts"] == "20260624T030000Z"
