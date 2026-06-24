# Backup / Export-Import Overhaul — Design Plan

> **Status:** Phase 0 (this plan) shipped v2.612.4. Phases 1–9 queued.

## Context

Today SimpleVTT has **two disconnected backup stories** and several gaps:

- **Operator backups** are a `postgres:16-alpine` sidecar (the `backup` service in
  `docker-compose.yml`) that bakes `BACKUP_CRON` / `KEEP_DAILY` / `KEEP_WEEKLY` into a
  crontab at container start (`scripts/entrypoint-backup.sh` → `scripts/backup.sh`).
  Changing the schedule or retention means editing env and recreating the container —
  there is **no UI**.
- **User-facing export** exists only as the GDPR JSON dump (`GET /api/users/me/export`)
  and the campaign **homebrew** pack (`GET /api/campaign/{cid}/homebrew/export`). There
  is **no whole-campaign archive, no per-character archive, no item-level homebrew
  export, and no media in any export** (maps / portraits / audio / handouts live on disk
  and are never bundled).
- **No importer** that re-places an exported archive (the only restore path is
  operator-level `pg_dump` restore).

This plan delivers:

1. **Move automated-backup settings into the Admin Center** (the operator console
   site-admin is migrating to).
2. **ZIP exports at three "levels"** — PC sheet, whole campaign, single homebrew item —
   each bundling its own media.
3. **An importer** that re-places archives in either **clone** (new entities) or
   **restore/overwrite** (replace existing) mode, reusing/refactoring the demo-loader.
4. **Rate-limit** export requests (avoid overloading the server).
5. A **progress toast** while a zip builds.

### Decisions locked in

- **Settings placement:** per-setting — operator cron/retention → Admin Center (8015);
  user-facing exports → in-app.
- **Import mode:** both clone-into-new **and** restore/overwrite-existing; user picks at
  import time.
- **Media:** bundle binaries inside the zip; importer rewrites paths.
- **Demo mode:** automated backups are **disabled** when `DEMO_MODE=true` (the demo DB
  reseeds every ~60 min, so scheduled `pg_dump`s are pure churn).

## Architecture

### Operator cron editing across the sidecar boundary

Use a **settings file on the shared `backup_data` volume**, not an app→sidecar RPC and
not moving `pg_dump` into the app (the app image carries no postgres client; the sidecar
separation is clean).

- Admin Center mounts `backup_data` (rw) and writes `/backups/backup-settings.json`:
  ```json
  {"format":"simplevtt-backup-settings","version":1,
   "cron":"0 3 * * *","keep_daily":7,"keep_weekly":4,
   "updated_at":"…Z","updated_by":"admin"}
  ```
- `scripts/entrypoint-backup.sh`: replace the one-shot crontab write with a **watch
  loop** — read `backup-settings.json` if present (fall back to env on first boot),
  regenerate `/etc/crontabs/root`, re-check file mtime every 60 s and rewrite on change
  (crond re-reads `/etc/crontabs` each minute).
- `scripts/backup.sh`: read `KEEP_DAILY` / `KEEP_WEEKLY` from the settings file at run
  time so retention edits apply without a crontab rewrite.
- A "run now" touches a trigger file the loop watches. Entirely offline /
  Docker-network-only; no new ports.

**Demo-mode short-circuit:** when `DEMO_MODE=true`, the sidecar must **not** take
automated backups. `scripts/entrypoint-backup.sh` reads `DEMO_MODE` and, when truthy,
skips installing the crontab and skips the initial backup (logs `"[backup] DEMO_MODE —
automated backups disabled"` and idles). `scripts/backup.sh` also bails early on
`DEMO_MODE=true` as a belt-and-braces guard so even a manual "run now" trigger is a
no-op. The Admin Center `/backups` page surfaces this state read-only ("Disabled — demo
mode") rather than offering editable schedule controls.

### ZIP archive format (mirrors the `simplevtt-homebrew` envelope)

```
manifest.json          # envelope: format, version, level, app/schema version,
                       #           source ids/names, counts, media_manifest[]
data/
  campaign.json            # campaign level only
  characters/<id>.json
  maps/<id>.json
  tokens.json
  token_templates.json
  encounters/<id>.json
  playlists.json           # + tracks
  notes.json
  handouts.json
  dice_rolls.json
  homebrew.json            # reuses the simplevtt-homebrew pack shape verbatim
media/<bucket>/<uuid><ext> # portraits, maps, tokens, token_templates,
                           # thumbnails, encounter_bg, handouts, audio
```

`manifest.level ∈ {campaign, character, homebrew-item}`. **Media path rewriting on
import:** every binary is written with a **fresh uuid** under the destination
`/app/static/uploads/<bucket>/`, and every row referencing a `*_url` / `file_url` /
`image_url` / `portrait_url` / `thumbnail_url` / `background_url` is rewritten through an
`old_url → new_url` map before insert — guarantees cross-instance round-trip with no
collisions/overwrites.

### Three export levels

| Level | Endpoint | Auth |
|---|---|---|
| PC sheet | `GET /api/character/{id}/export` | character owner **or** GM of its campaign |
| Campaign | `POST /api/campaign/{cid}/export` (job-based) | `_require_gm_for_campaign` |
| Homebrew item | `GET /api/campaign/{cid}/homebrew/{type}/{slug}/export` (`?format=json`) | `_require_gm_for_campaign` |

### Import (clone vs restore)

- `POST /api/campaign/import` (`file`, `mode=clone|restore`, optional `target_campaign_id`).
- `POST /api/campaign/{cid}/character/import` (`file`, `mode`).
- Extend existing `POST /api/campaign/{cid}/homebrew/import` with `overwrite=true`
  (currently add-only) for single-item / restore packs.
- **clone** → always new ids + fresh media uuids (safe default; reuses `demo_seed`
  creation pattern). **restore** → `wipe_campaign_children(db, target_campaign_id)` then
  re-create; requires `target_campaign_id` + GM auth.
- **Transactionality:** SQL inserts in one txn; media staged in a temp dir, atomically
  moved into `uploads/` only after `db.commit()`; homebrew JSON files written last
  (post-commit), exactly as `reset_and_reseed` does. On failure: rollback + `rmtree`
  staging.

### Rate limiting

Generalize the **already-pure** `app/user_export.py` cooldown helper into
`app/export_limit.py`: `cooldown_remaining(...)` (unchanged) + `cooldown_seconds(scope)`
reading `EXPORT_COOLDOWN_<SCOPE>_SECONDS`, registry keyed `(scope, id)`. Defaults:
campaign 300 s, character 60 s, homebrew 10 s; keep `USER_DATA_EXPORT_COOLDOWN_SECONDS`.
429 + `Retry-After`; bypassed under `TEST_MODE` (preserve existing behavior).

### Progress toast (job model, not synchronous streaming)

Campaign exports bundle tens of MB → use an **in-memory job registry**
(`app/export_jobs.py`, module-level dict, single container — same rationale as
`LAST_EXPORT_MONOTONIC`): `POST …/export` returns `{job_id}`; `GET
/api/export-jobs/{id}` → `{status, progress, stage, download_url, error}`; `GET
/api/export-jobs/{id}/download` streams the staged zip (TTL-swept, deleted after
download). Job stores `owner_user_id` → 403 for other pollers. Frontend reuses
`window.showToast` (`app/static/action_buttons.js`), polling ~1 s and triggering download
on `done`. The homebrew-item export stays **synchronous** (no media).

## Repeatable per-commit recipe

Every phase ships as one commit: ① one coherent code surface → ② bump `APP_VERSION`
(`app/version.py`; MINOR for new endpoints, PATCH for refactor/docs; bump
`SCHEMA_VERSION` + add an `_apply_inline_migrations()` block **only** if a column is
added — **no phase here needs a schema change**) → ③ CHANGELOG entry with fun name +
`**Schema version:**` → ④ README badge → ⑤ harness test(s) (happy + error path) → ⑥
`docs/test-harness-coverage.md` (+ total-count line) → ⑦ commit + `git push origin main`
→ ⑧ `docker compose up -d --build app` (+ `admin-center` / `backup` when touched), poll
`/version`.

## Phases

- **Phase 0 — Plan doc + wiki surfacing (PATCH).** This doc + `_DOC_ALLOWLIST` /
  `wiki.html` / `docs/wiki/README.md` rows + `test_wiki_doc_serves_backup_plan`.
- **Phase 1 — Generalized rate-limit helper (PATCH).** `app/export_limit.py` (generalize
  `app/user_export.py`); repoint the GDPR endpoint; add `cooldown_seconds(scope)`.
- **Phase 2 — Reusable wipe + zip-builder library (PATCH/MINOR, no endpoint).**
  `app/campaign_wipe.py::wipe_campaign_children(db, campaign_id)` extracted from
  `demo_seed.wipe()` (FK-safe order: tokens → encounters → dice_rolls → token_templates →
  characters → null active_map_id → maps → memberships); `demo_seed.wipe()` calls it.
  `app/export_bundle.py`: serialize campaign/character to the manifest+data+media layout,
  stream a zip to a staging path, resolve `*_url` columns to files. **Foundational for
  4–7.**
- **Phase 3 — Homebrew item-level export (MINOR).** `GET
  /api/campaign/{cid}/homebrew/{type}/{slug}/export` (+`?format=json`); refactor per-type
  projections out of bulk `export_homebrew`; reuse `_monster_record_to_export`. Per-row
  "Export" button. Rate-limited `scope="homebrew"`.
- **Phase 4 — Export job registry + campaign export (MINOR). [RISKIEST]**
  `app/export_jobs.py`; `POST /api/campaign/{cid}/export`, `GET /api/export-jobs/{id}`,
  `GET /api/export-jobs/{id}/download`. Uses Phase 2 bundle. Most moving parts (media
  collection across 8 buckets, background task, job lifecycle, large payloads).
- **Phase 5 — Character (PC sheet) export (MINOR).** `GET /api/character/{id}/export`
  (owner-or-GM), character-scoped bundle (sheet, notes, portrait, that char's dice_rolls
  — no campaign-wide leak). Rate-limited `scope="character"`.
- **Phase 6 — Importer: clone mode (MINOR).** `POST /api/campaign/import` + `POST
  /api/campaign/{cid}/character/import` (`mode=clone`). Reuses `demo_seed` creation
  helpers + Phase 2 reader; fresh-uuid media rewrite; staged-then-atomic move; one SQL
  txn.
- **Phase 7 — Importer: restore/overwrite mode (MINOR).** Add `mode=restore` +
  `target_campaign_id`; calls `wipe_campaign_children` then re-creates; homebrew import
  `overwrite=true`. **Destructive — safety rides on Phase 2's wipe matching
  `demo_seed.wipe()`.**
- **Phase 8 — Admin Center: operator backup settings (MINOR). [Independent of 3–7]** Add
  `backup_data:/backups` (rw) to the admin-center service + `DEMO_MODE` to the `backup`
  service in `docker-compose.yml`. `app/admin_center/backup_admin.py` + `/backups` page:
  edit cron + retention (write `backup-settings.json`), list artifacts, "run now". Gated
  by `ADMIN_CENTER_ADMIN_TOOLS` + destructive gate; audited via `operator_audit`. Update
  `scripts/entrypoint-backup.sh` + `scripts/backup.sh` (watch loop + runtime retention +
  `DEMO_MODE` short-circuit). The `/backups` page shows "Disabled — demo mode" read-only
  in demo.
- **Phase 9 — Progress-toast frontend polish (PATCH).** Wire `window.showToast` progress
  to the Phase 4/5 job-poll loop; finalize export-button UX (download trigger, error
  toast).

## Critical files

- `app/routes/tabletop_routes.py` — homebrew export/import (refactor `export_homebrew`
  ~L15395, `import_homebrew` ~L15604); new campaign/character export+import endpoints.
- `app/demo_seed.py` — extract `wipe()` ordering into `app/campaign_wipe.py`; reuse seed
  helpers in the importer.
- `app/user_export.py` → `app/export_limit.py` — generalize the cooldown limiter.
- `app/export_bundle.py` (new), `app/export_jobs.py` (new) — bundle builder + job
  registry.
- `scripts/entrypoint-backup.sh`, `scripts/backup.sh` — settings-file watch loop +
  runtime retention + demo-mode skip.
- `app/admin_center/main.py`, `app/admin_center/backup_admin.py` (new),
  `docker-compose.yml` — admin-center backup page + `backup_data` mount.
- `app/static/action_buttons.js` — progress toast wiring (`window.showToast`).

## SRD / wiki guardrails

- Exports/imports move **homebrew-tier** records only (`app/data/homebrew/…`); nothing
  under `app/data/local/`, so `test_srd_provenance.py` stays green.
- Phase 0 surfaces this plan through `/wiki` in the same commit it's created (allowlist +
  `wiki.html` + `docs/wiki/README.md` + per-slug harness test).

## Verification

- **Per phase:** `python3 -m pytest tests/harness/ -q` green; `docker compose up -d
  --build app` then `curl -s http://localhost:8013/version` reports the new `APP_VERSION`.
- **End-to-end round-trip (after Phase 7):** as GM, `POST /api/campaign/{cid}/export` →
  poll job → download zip; unzip and confirm `manifest.json` (`level=campaign`, counts) +
  `media/` binaries. Import as **clone** → new campaign with matching content and working
  (rewritten) media URLs. Import as **restore** into a throwaway campaign → its children
  replaced by the archive. Confirm rapid re-export returns 429.
- **Operator (Phase 8):** in Admin Center `/backups`, change cron + retention, confirm
  `/backups/backup-settings.json` updates and the sidecar regenerates its crontab within
  ~60 s (`docker compose logs backup`); "run now" produces a fresh `simplevtt-<ts>.sql.gz`
  pair under `daily/`. With `DEMO_MODE=true`, confirm the sidecar logs the disabled
  message, installs no crontab, and `/backups` shows "Disabled — demo mode".
