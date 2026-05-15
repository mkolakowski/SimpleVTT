# Changelog

All notable changes to SimpleVTT are documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) — Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

The current version is the topmost release section below.
Application version and database schema version are also published at runtime by `GET /version` and `GET /healthz`, and are defined as constants in [`app/version.py`](app/version.py).

> For pre-2.0.0 history, see [CHANGELOG_v1.md](CHANGELOG_v1.md).

---

## [2.0.4] - 2026-05-15

**Schema version:** 52
**Commit summary:** Move the Demo Mode design into a dedicated planning file; trim the TODO entry to a one-line pointer.
**Description:** The Demo Mode TODO entry had grown to a multi-paragraph brief and would have grown further as design decisions accumulated (hourly auto-reset, surgical wipe strategy, NPC tokens in the seeded encounter, safety guards, verification). Detailed plans don't fit the TODO format — it's meant to be scannable. Moves the full plan to a new `docs/plans/` directory and shrinks the TODO entry to one sentence plus a link. Establishes the convention: any feature whose plan exceeds a paragraph gets its own file under `docs/plans/`.

### Added
- `docs/plans/demo-mode.md` — full design plan for the planned v2.1.0 Demo Mode feature: in-process asyncio reset loop, tag-based surgical wipe, seed module with NPC-populated tavern encounter, bundled-asset strategy, safety guards, and verification steps.
- `docs/plans/` directory for future feature design docs.

### Changed
- `TODO.md`: Demo Mode entry trimmed from ~12 lines to one sentence + a link to the plan file.

**Schema version:** 52
**Commit summary:** Credit Open5e in the per-file `_attribution` of every shipped SRD JSON record; regenerate all 984 files from the live Open5e API with the new credit chain.
**Description:** The per-file `_attribution` previously cited only "the D&D 5e SRD (CC BY 4.0 / OGL 1.0a)" without naming Open5e, the intermediate CC BY 4.0 source the JSON shape was derived from. CC BY 4.0's attribution clause flows downstream — Open5e itself must be credited in works that redistribute its data. Updates the `ATTRIBUTION` constant in `scripts/build_srd_content.py` to name Wizards of the Coast AND Open5e (with the URL) AND point to `CREDITS.md` for the full chain, then re-runs the builder against `https://api.open5e.com/v1/` to refresh every file. The script's `wotc-srd` document filter still gates the redistribution perimeter; the rebuild was a no-op on the file-list dimension (same 984 files, same slugs) but every record now carries the corrected credit string.

### Changed
- `scripts/build_srd_content.py`: `ATTRIBUTION` constant rewritten to credit both Wizards of the Coast (the upstream work) and Open5e (the intermediate distributor), with a pointer to `CREDITS.md`.
- Every JSON file under `app/data/local/dnd5e/` regenerated with the new `_attribution` string. Counts unchanged: 319 spells / 322 monsters / 292 items / 15 conditions / 13 subclass_features / 12 class_features / 9 races / 1 feat / 1 background. All 984 files still validate against their Pydantic models.

---

## [2.0.2] - 2026-05-15

**Schema version:** 52
**Commit summary:** Add `CREDITS.md` with the full third-party attribution chain (D&D 5e SRD via Open5e, htmx, Google Fonts, Python deps).
**Description:** SimpleVTT redistributes the ~984 SRD-derived JSON files generated in 1.7.0; CC BY 4.0 requires reasonable attribution at the work level, not just per-record. Adds a `CREDITS.md` at the repo root listing Wizards of the Coast (SRD 5.1, CC BY 4.0 / OGL 1.0a), Open5e (the intermediate source, CC BY 4.0), htmx (BSD), Google Fonts (SIL OFL 1.1), and every Python dependency from `requirements.txt` with its license. The `LICENSE` file's trailing notice already points here for the content credit chain.

### Added
- `CREDITS.md` at repo root. Three sections: game-rules content (SRD via Open5e), frontend dependencies (CDN-loaded htmx + Google Fonts), Python dependencies (everything in `requirements.txt`). Each entry links to the upstream project and names the SPDX license.

---

## [2.0.1] - 2026-05-15

**Schema version:** 52
**Commit summary:** Add MIT LICENSE at the repo root.
**Description:** SimpleVTT had no project-level license file. Without one, the project defaults to "all rights reserved" — contributors can't legally contribute, forkers can't legally fork, and registries flag the project as unlicensed. Adds an MIT LICENSE plus a short third-party content notice pointing to `CREDITS.md` (added in 2.0.2) for the SRD attribution.

### Added
- `LICENSE` at repo root — MIT for the project itself, with a trailing notice that the shipped SRD JSON content is separately licensed (CC BY 4.0 / OGL 1.0a) via the Open5e project.

---

## [2.0.0] - 2026-05-15

**Schema version:** 52
**Commit summary:** Destructive cutover from DB-backed `custom_*` tables to file-based homebrew. Six tables exported then DROPPED at boot; ~150 ORM references in routes / admin / resolver replaced with `local_content.*`; Custom* SQLAlchemy models deleted; URL contracts for every GM-authored homebrew type changed from `{type_id: int}` to `{type_slug: str}`.
**Description:** Completes the file-based content framework introduced in 1.7.0. Homebrew classes, subclasses, races, feats, monsters, and backgrounds no longer live in SQL — every record is now a per-slug JSON file under the `homebrew_data` Docker volume, validated through the Pydantic schemas in `content_schemas.py`. **Operator action required before upgrading: back up your Postgres database AND verify the `homebrew_data` volume exists.** On first v2.0.0 boot the inline migration framework (schema v52) calls `app/_migrate_v52.py`, which exports every row in the six `custom_*` tables to JSON files, then DROPs all six tables in a single transaction. Both export and drop happen inside one SQLAlchemy `engine.begin()` block, so any export error aborts the migration before any table is destroyed. After the migration, the GM authoring forms on the campaign settings page write JSON files directly via `local_content.write_homebrew`; the admin `/admin/stubs` audit page walks the homebrew volume rather than joining six SQL tables; and `app/local_features.py` retains only the shipped-FS providers — its DB providers (`_db_class_provider`, `_db_subclass_provider`, …) are removed in lockstep with the model classes.

### Added
- `app/_migrate_v52.py` runner — `run_v52_migration(engine)` — wired into `_apply_inline_migrations` at the v52 step. Idempotent: no-op when the legacy tables are already gone. Single transaction wraps both the per-table exports and the `DROP TABLE` statements; partial JSON writes from a failed export are overwritten on the next attempt (writes are atomic + deterministic).
- `_enumerate_homebrew(type_dir)` helper in `app/routes/admin_routes.py` — walks every scope directory under the homebrew volume for a given content type and yields each loaded record with `_campaign_id` / `_scope` / `_mtime` synthetic keys. Replaces the six per-table SQL joins on the `/admin/stubs` audit page; the JSON twin at `/admin/stubs.json` reads from the same helper.
- Pre-flight + post-flight row counts logged at INFO level so the boot log shows `"v52 migration: N Custom* rows to export across M table(s)"` followed by per-table `"exported K rows from <table>"` and `"dropped <table>"` lines.

### Changed
- **`ClassFeature.features` is now `Any`** (was `str`). Matches the existing `SubclassFeature.features: Any` pattern so shipped SRD class files (markdown blob) and homebrew records (structured `[{name, level, desc}, ...]` list from the campaign-settings editor) both load through the same schema. The migration dumper preserves the structured list verbatim — no flattening to markdown on the export path — so the GM-side feature editor round-trips after migration.
- `_dump_custom_class` in the v52 migration no longer flattens features through `features_to_markdown`; the helper itself stays in `local_content.py` for ad-hoc use but the migration writes structured data directly.
- Every Custom* CRUD endpoint in `app/routes/tabletop_routes.py` (classes, subclasses, races, feats, monsters, backgrounds) refactored to file-based: `db.query(Custom*)` calls replaced with `local_content.resolve` / `local_content.search`; inserts/updates replaced with `local_content.write_homebrew`; deletes replaced with `local_content.delete_homebrew`. URL contracts changed from `{type_id: int}` to `{type_slug: str}` (CustomSubclass uses combined `<class>__<sub>` slug). The matching `campaign_settings.html` form `action=` URLs and visible `<code>` slug labels updated to match.
- `app/routes/tabletop_routes.py`: import / export endpoints (`/api/campaign/{id}/homebrew/{import,export}`) projects the file records back to the legacy field-name shape (`feat_slug`, `background_slug`, `race_slug`, `monster_slug`, `class_slug`, `sub_slug`) for the import payload's bulk-create shape. Round-trips a v1 export pack into a v2.0.0 campaign without edits.
- `app/routes/tabletop_routes.py`: search proxies (`/api/open5e/{feats,backgrounds,races,subclasses,monsters,classes}`) now consult `local_content.search(...)` for the homebrew tier; Open5e mirror / live API only fires on shipped-SRD + homebrew miss.
- `app/routes/tabletop_routes.py`: `_custom_monster_lite(row)` signature changed from `CustomMonster` ORM row to a plain `dict` (file record).
- `app/routes/tabletop_routes.py`: monster bulk-import collapses the four legacy parallel action lists (`actions`, `reactions`, `special_abilities`, `legendary_actions`) into a single `actions: list[Action]` array via the new `_coalesce_monster_actions` helper; the matching `_monster_record_to_export(r)` projects the unified array back to the four split lists for the export endpoint.
- `app/routes/admin_routes.py` `/admin/stubs` HTML view + `/admin/stubs.json` audit endpoint rewritten to walk the homebrew volume; campaign + creator names resolved in-process via a single Campaign / User lookup map per request rather than per-record SQL joins.
- `app/local_features.py` chain lists (`_CLASS_PROVIDERS`, `_SUBCLASS_PROVIDERS`, `_RACE_PROVIDERS`, `_MONSTER_PROVIDERS`, `_BACKGROUND_PROVIDERS`, `_FEAT_PROVIDERS`) collapsed to a single-entry list containing only the shipped-FS provider. The DB-backed providers no longer exist; resolver call sites that need homebrew should use `app/local_content.py` directly.

### Removed
- **SQLAlchemy models (and their tables):** `CustomClass`, `CustomSubclass`, `CustomRace`, `CustomFeat`, `CustomMonster`, `CustomBackground` in `app/models.py`. The corresponding tables — `custom_classes` / `custom_subclasses` / `custom_races` / `custom_feats` / `custom_monsters` / `custom_backgrounds` — are dropped by the v52 boot migration after their rows export to the homebrew Docker volume.
- DB-backed provider functions in `app/local_features.py`: `_db_class_provider`, `_db_subclass_provider`, `_db_race_provider`, `_db_monster_provider`, `_db_background_provider`, `_db_feat_provider`.
- `_class_to_dict(c)` and the other Custom* `_*_to_dict` helpers in `tabletop_routes.py` — the export endpoint inlines each projection from file records.
- Schema v22-v30 `CREATE TABLE` calls in `app/database.py`'s `_apply_inline_migrations`. The version stamps are kept for upgrade-path bookkeeping; the actual `CREATE` is now a no-op since v52 drops the tables anyway. Databases initialised at v2.0.0+ never have the tables.
- Imports of `Custom*` model classes from `app/routes/admin_routes.py` and `app/routes/tabletop_routes.py`.

### Schema
- **v52 (destructive, forward-only).** The six legacy `custom_*` tables are exported to JSON files in the `homebrew_data` Docker volume, then DROPped in one SQL transaction. Idempotent on subsequent boots (no Custom* tables present → no-op).
- **Operator action required:**
  1. **Back up Postgres before upgrading.** A standard `pg_dump` is sufficient. The migration is destructive; if you discover after the fact that an export failed silently, your only recovery is from the SQL dump.
  2. Pull the v2.0.0 image and `docker compose up`. Watch the boot log for `"v52 migration: N Custom* rows to export across M table(s)"` followed by `"exported K rows from <table>"` for each table that had data. The final per-table count should equal the pre-flight count; mismatch logs as `ERROR` and recommends a manual review of the homebrew volume.
  3. Verify the `homebrew_data` named volume exists and contains files: `docker compose run --rm app ls /app/app/data/homebrew/dnd5e/`. You should see one or more `campaign-<id>` (or `global`) subdirectories, each with per-content-type folders.
  4. Recommended: take a `tar` snapshot of the populated `homebrew_data` volume as a second backup line.
- After successful upgrade, the `custom_*` tables no longer exist. Subsequent boots see no Custom* tables and the v52 migration is a no-op.

### Migration notes
- **Partial-failure recovery.** If the SQL transaction rolls back mid-export, the JSON files written before the failure are harmless and overwritten deterministically on the next attempt. Identify the offending row from the error message, fix or delete the row, then reboot — the migration completes idempotently.
- **Operators on a brand-new database** (no v1.x data to migrate) see `"v52 migration: no Custom* tables present; nothing to do."` and proceed to start.
- The `app/data/homebrew/` directory in the Docker image is created empty so the named volume mounts cleanly even before any file has been authored.
