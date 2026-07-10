# Backups & restore

SimpleVTT has **two different backup systems** for two different jobs. Knowing
which is which saves a lot of confusion:

| System | Scope | Where | Use it to… |
|---|---|---|---|
| **Operator backups** | The **whole application** (every campaign + user) | Admin Center → **Backups** | Recover the whole instance — disaster recovery, server migration, restore from a fresh install. |
| **Campaign / character / homebrew exports** | **One** campaign, PC, or homebrew record | In the app (campaign settings, character sheet, homebrew Workshop) | Share, clone, or move a single piece of content between campaigns or instances. |

They produce **different files with different structures** — covered separately
below.

---

## 1. Operator backups (the `simplevtt-backup` sidecar)

A dedicated `postgres:16-alpine` sidecar container (`simplevtt-backup`) takes
scheduled, full-application backups on the internal Docker network.

### What a backup run produces

Each run writes **three artifacts** that share one UTC timestamp, into
`daily/` (and, on Sundays, also `weekly/`) on the `backup_data` volume:

| Artifact | What it is |
|---|---|
| `simplevtt-<ts>.sql.gz` | Gzipped `pg_dump --clean --if-exists` of the **whole database** — every user, campaign, character, dice roll, note, handout, setting. This includes the `maps` table's **walls / doors / locks / terrain / lights / fog** JSON, so every map edit is captured. |
| `simplevtt-<ts>.homebrew.tar.gz` | The file-based homebrew content volume (custom classes / monsters / feats / …). |
| `simplevtt-<ts>.uploads.tar.gz` | Uploaded media — maps, portraits, tokens, token templates, audio, handouts, encounter backgrounds, thumbnails (everything under `/static/uploads`). |

Together these three are **everything needed to restore the application from a
fresh install**: the database has the rows, the two tarballs have the files
those rows reference.

> **Videos are never backed up.** The demo self-test's screen recordings
> (`.webm`) live on their own `selftest_results` volume, which the backup
> sidecar doesn't mount — and both tarballs additionally exclude any `video/`
> directory and `*.webm` files as a belt-and-braces guarantee (v2.997.2).

### What campaign content is captured

The `.sql.gz` is a dump of the **entire PostgreSQL database**, so it contains
**every piece of content needed to play a campaign** — not a curated subset.
That includes:

- **Accounts & membership** — all users (login + preferences) and who belongs
  to which campaign (GM / player roles).
- **Campaigns** — every campaign, its settings, game system, and archive state.
- **Player characters** — each PC's full character sheet (abilities, HP, AC,
  inventory, spells, features, portrait reference, colour/ring style), for
  every campaign and every standalone PC.
- **NPCs / monsters** — token templates (reusable stat blocks).
- **Maps & tokens** — every map (grid + background reference) and the tokens
  placed on them (positions, sizes, controllers, disguises, fog state).
- **Encounters** — saved encounter snapshots (token layout, initiative seed,
  bound playlist, background).
- **Audio** — playlists and their track lists.
- **Notes & handouts** — GM prep notes and player notes (including the
  *ciphertext* of end-to-end-encrypted private notes), and handouts with their
  reveal state.
- **Dice-roll history**, **concentration / battle state**, and the rest of the
  app's tables.

The two tarballs complete the picture with the *files* those rows point at: the
**homebrew** tarball carries campaign-authored custom content (classes,
subclasses, races, monsters, backgrounds, feats), and the **uploads** tarball
carries the binary media (map images, character portraits, token art, audio
files, handout images, thumbnails). A character row, for example, lives in the
SQL dump while its portrait image lives in the uploads tarball — restoring all
three brings the PC back intact.

> **One exception worth noting:** end-to-end-encrypted private notes are dumped
> as ciphertext. They restore byte-for-byte, but they can only be *read* again
> with the same per-campaign encryption passphrase — the backup can't (and
> deliberately doesn't) capture that key.

### Inside the tarballs — where to find things

The two tarballs are plain `tar -czf` of their volumes, so you can `tar tzf` /
`tar xzf` them with any tar tool. Their layout:

**`simplevtt-<ts>.uploads.tar.gz`** — one folder per media bucket (files are
named by UUID; a DB row references them as `/static/uploads/<bucket>/<file>`):

```
uploads.tar.gz
├── maps/             # battle-map background images
├── portraits/        # character portraits
├── tokens/           # custom token art
├── token_templates/  # NPC / template-token art
├── thumbnails/       # cached map thumbnails (.webp)
├── encounter_bg/     # encounter background images / video
├── handouts/         # handout images
└── audio/            # playlist track files
```

**`simplevtt-<ts>.homebrew.tar.gz`** — one JSON file per homebrew record,
filed by game system → scope → content type. Campaign-authored content lives
under `campaign-<id>/`:

```
homebrew.tar.gz
└── dnd5e/
    ├── global/                       # instance-wide homebrew (rare)
    │   └── <type>/<slug>.json
    └── campaign-<id>/                # one dir per campaign with homebrew
        ├── monsters/<slug>.json
        ├── feats/<slug>.json
        ├── class_features/<slug>.json
        ├── subclass_features/<slug>.json
        ├── races/<slug>.json
        ├── backgrounds/<slug>.json
        └── items/<slug>.json
```

So to find, say, campaign 7's custom monsters: `dnd5e/campaign-7/monsters/` in
the homebrew tarball. To find a character's portrait: `portraits/` in the
uploads tarball (the filename is the UUID in the character's `portrait_url`).

> **Note the split:** the *campaigns, player sheets, notes, encounters,
> tokens* themselves are **not** in the tarballs — those are database rows in
> the `.sql.gz` dump. The tarballs only carry homebrew JSON + uploaded media
> (the files the rows point at).

### Can I restore individual items with the in-app import tools?

**No — the operator backup and the in-app exports use different formats and
aren't interchangeable.** Pulling files out of the tarballs won't make them
importable through the app's campaign / character / homebrew **Import**
buttons, because:

- **Campaigns & player sheets** aren't in the tarballs at all — they're rows in
  the `.sql.gz` dump, and that's a PostgreSQL dump, not a `simplevtt-export`
  zip. The in-app "Import" tools only read `simplevtt-export` / `simplevtt-
  homebrew` archives, so there's nothing to hand them. Recover these by
  restoring the whole database (Admin Center → **Restore**, or `psql`).
- **Homebrew** files in the tarball are in the content-volume shape
  (`{slug, name, …}`), not the `simplevtt-homebrew` *pack* shape the in-app
  homebrew import expects — so a raw file isn't directly importable. (As an
  operator you can drop it straight into the homebrew volume; or re-export it
  from the app to get an importable pack.)
- **Media** files are raw binaries; the in-app importers expect media bundled
  *inside* an export zip, not loose.

**If you want one campaign / PC / homebrew item in a portable, re-importable
form, use the in-app exports instead** — campaign settings → *Import & export* →
**Download full backup**, the character sheet's **Export sheet**, or the
homebrew Workshop's per-row **Export**. Those produce the `simplevtt-export` /
`simplevtt-homebrew` archives the in-app importers accept (see §2 below). The
operator backup is for rebuilding the **whole** instance, not cherry-picking a
single item.

### Schedule, retention, and demo mode

- **Schedule + retention** are editable at runtime from **Admin Center →
  Backups** (a cron expression + how many `daily` days / `weekly` weeks to
  keep). The page writes `backup-settings.json` onto the shared volume and the
  sidecar regenerates its cron within ~60 s. First-boot defaults come from the
  `BACKUP_CRON` / `KEEP_DAILY` / `KEEP_WEEKLY` env vars.
- **Run now** takes an immediate backup.
- **Demo mode** (`DEMO_MODE=true`) **disables automated backups entirely** — a
  demo database reseeds hourly, so scheduled dumps would be pure churn. The
  Backups page shows "Disabled — demo mode" and the schedule controls are
  hidden.

> The Backups page only appears when the operator write-surface is enabled
> (`ADMIN_CENTER_ADMIN_TOOLS=true`).

### Offsite (cloud) uploads — S3, Google Drive, Dropbox, OneDrive

Every backup run can also be **pushed offsite** (v2.998–2.999) so a disk
failure can't take the app *and* its backups. The uploader is **rclone**
(baked into the sidecar image); configure it from **Admin Center → Backups →
☁️ Offsite uploads**:

1. **Pick a provider** and enter credentials:
   - **Amazon S3 / S3-compatible** — paste an access key id + secret. For
     S3-compatibles (MinIO, Cloudflare R2, Backblaze B2, Wasabi) also set the
     **endpoint** URL. The **remote path** is `bucket/prefix` (the bucket is
     created on first use if the key may).
   - **Google Drive / Dropbox / OneDrive** — OAuth can't complete on a
     headless server, so run rclone's standard one-liner **on any machine with
     a browser** (`brew install rclone` / `winget install Rclone.Rclone`):

     ```bash
     rclone authorize "drive"      # or "dropbox" / "onedrive"
     ```

     Approve the browser prompt, then paste the printed JSON token blob into
     the form's **OAuth token** field. (OneDrive business accounts may also
     need a **drive id** — `rclone config` on your laptop shows it.)
2. Choose the **retention mode**:
   - **accumulate (`copy`)** — the remote only ever gains files; old backups
     are never deleted offsite. Survives local corruption/ransomware best;
     grows unbounded until you prune it yourself. *(Default.)*
   - **mirror (`sync`)** — the remote mirrors the local backup dir, so the
     `KEEP_DAILY`/`KEEP_WEEKLY` pruning propagates and the remote stays
     bounded.
3. Tick **Upload after every backup run**, **Save**, then hit
   **🔌 Test connection** — the sidecar probes the remote and the result
   appears on the card. **⬆ Upload now** pushes the existing artefacts
   without taking a new backup.

Mechanics + security notes:

- Uploads run as a final `offsite` stage of each backup (after retention
  pruning). An upload failure **never fails the backup** — the artefacts are
  already safe locally; the failure is shown on the card.
- Credentials are **write-only**: they live solely in `rclone.conf` on the
  backup volume (mode `0600`), are never echoed back to the page or any JSON
  endpoint, and are **not inside the backup artefacts themselves**. Re-saving
  the settings with blank credential fields keeps the existing remote.
- **Remove offsite config** stops uploads and deletes the stored credentials;
  artefacts already uploaded are untouched.
- To try it locally without a cloud account: `docker compose --profile dev up
  -d minio`, then configure provider *S3* with endpoint `http://minio:9000`
  and the `minioadmin`/`minioadmin` dev credentials.

### Structure of an operator backup **download**

The Backups page lists **one row per backup run** (the three artifacts grouped
by timestamp). The **⬇ Download .zip** button bundles that run into a single
zip:

```
simplevtt-backup-<ts>.zip
├── simplevtt-<ts>.sql.gz            # gzipped pg_dump (psql-restorable)
├── simplevtt-<ts>.homebrew.tar.gz   # tar.gz of the homebrew volume
└── simplevtt-<ts>.uploads.tar.gz    # tar.gz of the uploads volume
```

The zip uses **STORED** (no compression) because the three members are already
gzip-compressed — unzipping gives you the originals untouched.

### Restoring (operator)

From **Admin Center → Backups**, click **♻ Restore** on a backup row and
confirm. The sidecar then:

1. **Takes a fresh safety backup first**, tagged `pre-restore safety backup
   (before restoring <ts>)` — visible in the **Tag** column, so your pre-restore
   state is one click away if you need to roll the restore back.
2. Loads the chosen `.sql.gz` into the live database (`--clean --if-exists`, so
   it drops + recreates each object).
3. Clears and unpacks the homebrew and uploads tarballs back into their volumes.

**Gating + caveats.** Restore is the most destructive operator action, so it is
refused unless the write-surface is on, the instance is **not** in demo mode,
and — when MFA is configured — your session is MFA-verified. It **overwrites
live data and briefly disrupts the running app**; the automatic safety backup
is your undo. Treat it as a maintenance-window operation.

**Manual / CLI restore** (e.g. onto a fresh install) is just the inverse of the
three artifacts:

```sh
# database
gunzip -c simplevtt-<ts>.sql.gz | psql -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB"
# homebrew volume  (into the homebrew_data mount)
tar -xzf simplevtt-<ts>.homebrew.tar.gz -C /path/to/homebrew_data
# uploaded media   (into the uploads_data mount)
tar -xzf simplevtt-<ts>.uploads.tar.gz -C /path/to/uploads_data
```

---

## 2. Campaign / character / homebrew exports (portable archives)

These are produced **in the app** and are scoped to a single piece of content.
They're for sharing and cloning, not whole-instance recovery.

### Campaign export — `simplevtt-export` zip

Campaign settings → **Import & export** → **Download full backup (.zip)**. A
background job builds it (a progress toast shows each stage), then it downloads:

```
manifest.json                 # {format:"simplevtt-export", version, level:"campaign",
                              #  source_campaign_id/name, counts{}, media_manifest[]}
data/
  campaign.json               # the campaign row
  characters/<id>.json        # one file per PC
  maps/<id>.json              # one file per map
  tokens.json
  token_templates.json        # NPC stat blocks
  encounters/<id>.json
  playlists.json              # playlists + tracks
  notes.json                  # non-encrypted notes
  handouts.json
  dice_rolls.json
  homebrew.json               # a simplevtt-homebrew pack (round-trips into /homebrew/import)
media/<bucket>/<file>         # every uploaded file the data references, bundled in
```

The `media_manifest` in `manifest.json` maps each bundled file back to its
original `/static/uploads/...` URL, so an importer can rewrite the references.

### PC sheet export — `simplevtt-export` zip (`level:"character"`)

Character page → **⬇ Export sheet (.zip)**. A character-scoped archive:
`manifest.json` (`level:"character"`), `data/character.json` (the sheet — stats,
notes, portrait reference), `data/dice_rolls.json` (that PC's rolls), and any
`media/` the sheet references. **No** campaign-wide data is included.

### Homebrew item export — `simplevtt-homebrew` JSON

Homebrew Workshop → **Export** on a custom row. A single-record JSON pack (no
zip — a homebrew record has no media) in the same shape `/homebrew/import`
accepts, so one custom monster/feat/class round-trips into another campaign.

### Importing exports

- **Campaign import** (campaign settings → Import & export → Import backup):
  **clone** creates a brand-new campaign (fresh ids + fresh media uuids), or
  **restore** overwrites an existing campaign's content in place (its people
  stay; the rest is replaced).
- **Character import** clones a PC archive into a campaign.
- **Homebrew import** is add-only — rows whose slug already exists are skipped.

---

## Which one do I want?

- **"I need to be able to rebuild the whole server."** → Operator backups
  (Admin Center → Backups). Keep the zips somewhere off-box.
- **"I want to copy/share one campaign (or PC, or monster)."** → The in-app
  exports above.

See also: [First-run setup](/wiki/first-run-setup) (operator deployment),
[Admin Center](/wiki/admin-center), and the
[backup / export-import design plan](/wiki/doc/plan-backup-export-overhaul).
