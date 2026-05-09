# Changelog

All notable changes to SimpleVTT are documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) — Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

The current version is the topmost release section below.
Application version and database schema version are also published at runtime by `GET /version` and `GET /healthz`, and are defined as constants in [`app/version.py`](app/version.py).

---

## Instructions for AI agents updating this file

Read this section in full before modifying any version-related file. Follow it exactly.

### When to add a new entry

Add a new release section every time you make a user-visible, behavior-changing, or schema-changing edit. Pure refactors with no observable difference do **not** require an entry. If unsure, add one — extra entries are easier to live with than missing ones.

Group multiple in-flight edits under an `## [Unreleased]` section at the top until the user asks you to "cut a release", at which point you rename `[Unreleased]` → `[X.Y.Z] - YYYY-MM-DD` and create a fresh empty `[Unreleased]` block above it.

### How to bump `APP_VERSION` (semantic versioning)

The application version lives in [`app/version.py`](app/version.py) as `APP_VERSION = "MAJOR.MINOR.PATCH"`. Update it according to these rules:

- **MAJOR** — break a public contract: incompatible API changes, removed routes, removed config keys, breaking changes to the docker-compose stack, or any change requiring user action to upgrade beyond a normal redeploy.
- **MINOR** — new feature added in a backward-compatible way: new route, new optional config key, new template, new admin capability, etc.
- **PATCH** — backward-compatible bug fixes, security fixes, dependency bumps with no behavior change, copy/wording tweaks.

Bump exactly one component at a time. When MAJOR bumps, reset MINOR and PATCH to 0. When MINOR bumps, reset PATCH to 0.

### How to bump `SCHEMA_VERSION`

The schema version lives in [`app/version.py`](app/version.py) as `SCHEMA_VERSION = N` (an integer). Bump it by exactly **+1** the moment you make any change to `app/models.py` that alters the database schema:

- adding/removing a table
- adding/removing a column
- changing a column's type, default, nullable, unique, or index
- adding/removing a foreign key or constraint
- renaming any of the above

Do **not** bump `SCHEMA_VERSION` for changes that don't touch the schema (e.g., adding a method on a model class, editing a docstring). The schema version is independent of `APP_VERSION` — many app releases will leave it untouched. Every boot stamps the current value into the `schema_version` table, so the row history acts as a deployment log.

If a schema change is breaking (existing DBs need a real migration, not just `create_all`), the matching `APP_VERSION` bump must be MAJOR. For additive changes, append a new conditional ALTER block to `_apply_inline_migrations()` in `app/database.py` so existing deployments auto-upgrade on next boot.

### Required fields for every release entry

Each release section must include all five of these, in this order:

1. **Heading** — `## [X.Y.Z] - YYYY-MM-DD` (use today's date in UTC).
2. **Schema version line** — exactly `**Schema version:** N` where N is the value of `SCHEMA_VERSION` at the time of release. State this even if it didn't change.
3. **Commit summary** — one line, 10–15 words, imperative mood, no trailing period. Suitable for use as the GitHub commit subject. Prefix with `**Commit summary:**`.
4. **Description** — 2–4 sentences in plain prose explaining the user-facing impact, motivation, and any required operator action. Prefix with `**Description:**`.
5. **Categorized change list** — use any of these subsections that apply: `### Added`, `### Changed`, `### Deprecated`, `### Removed`, `### Fixed`, `### Security`, `### Schema`. Each bullet starts with a verb.

### Checklist before you finalize an entry

- [ ] `app/version.py` updated with the new `APP_VERSION` and (if changed) `SCHEMA_VERSION`.
- [ ] CHANGELOG.md has a new section at the top with all five required fields.
- [ ] If `SCHEMA_VERSION` bumped, the `### Schema` subsection lists every schema change AND `_apply_inline_migrations()` has a new conditional ALTER block.
- [ ] If the change is breaking, the description spells out the upgrade steps.
- [ ] Date is today's UTC date in `YYYY-MM-DD` format.
- [ ] Commit summary is between 10 and 15 words and reads as a verb phrase ("Add X", "Fix Y", "Refactor Z").
- [ ] You did not edit version numbers in any other file — `APP_VERSION` is the single source of truth and `app/main.py` reads it dynamically.

### Example template (copy this when adding a new entry)

````markdown
## [X.Y.Z] - YYYY-MM-DD

**Schema version:** N

**Commit summary:** Add per-campaign chat panel and persist chat history across sessions

**Description:** Players can now exchange in-character and out-of-character chat messages from the tabletop side panel. Messages are persisted to the database and replayed on reconnect. No operator action is needed beyond a redeploy; the chat table is created automatically on first boot.

### Added
- `ChatMessage` model and `/api/campaign/{id}/chat` endpoint.
- Chat panel below the dice roller with OOC/IC toggle.

### Schema
- New table `chat_messages` (id, campaign_id, user_id, body, kind, created_at).
- `SCHEMA_VERSION` bumped from N-1 to N.
````

(Replace `X.Y.Z`, `YYYY-MM-DD`, and `N` with actual values when you copy this.)

---

## [0.8.0] - 2026-05-04

**Schema version:** 6

**Commit summary:** Add mini character sheets, roll toasts, proficiency highlights, and collapsible sidebar

**Description:** The Player sidebar tab has been significantly upgraded: players now see only their own characters, can favourite them (persisted in localStorage), and can expand each character inline to a compact mini sheet. The mini sheet shows HP/AC/Speed, all six abilities with Check and Save roll buttons, and all 18 skills with roll buttons — all wired into the existing roll log and WebSocket broadcast. A roll toast container at the bottom-centre of the screen shows each player their own roll results as they come in, auto-dismissing after 10 seconds. The sidebar itself now fully collapses to zero width when unpinned, giving the map the full viewport. No operator action or database migration is required.

### Added
- Roll toast popup fixed to the bottom-centre of the tabletop: shows expression, total, and breakdown for the current player's own rolls; auto-dismisses after 10 seconds; click to dismiss early.
- Expandable inline mini character sheet per character card in the Player tab: HP / AC / Speed combat stats, a 6-column ability grid with Check and Save roll buttons, and a 2-column skill grid with roll buttons for all 18 skills.
- Favourite toggle on character cards in the Player tab; favourites float to the top of the list and preference is persisted per-campaign in localStorage.
- Proficiency column highlight on ability names in the mini sheet: a teal dot and teal name colour mark abilities that have a save proficiency.
- Skill proficiency colouring in the mini sheet: teal name = proficient, gold name = expertise; linked ability abbreviation shown on each skill row.

### Changed
- "Players" sidebar tab renamed to "Player".
- Player tab now filters characters to only show those owned by the current player; GMs continue to see all characters.
- Sidebar collapses fully to zero width when an active tab is clicked while the sidebar is unpinned; a floating ☰ button re-opens it so the map can use the full viewport width.
- Mini sheet Abilities & Saves section restructured from a vertical list to a compact 6-column grid: ability name and score span the top, with Check and Save roll buttons stacked below each column.
- Mini sheet skills section changed from a single column to a two-column layout.

---

## [0.7.0] - 2026-05-02

**Schema version:** 6

**Commit summary:** Gate the tabletop behind a GM-controlled session start so players can't peek before play

**Description:** Campaigns now have an explicit Open/Closed lifecycle. The GM (or admin) hits ▶ Start session from the lobby card or the tabletop header to open the tabletop to players; ⏹ End session closes it again. While a session is closed, non-GM members who navigate to the campaign URL see a "Waiting for the GM to start the session" page that auto-redirects them in the moment the GM hits Start (via the existing per-campaign WebSocket, with a 10-second polling fallback). Players already inside the tabletop when the GM ends the session are bounced back to the lobby. GMs and admins always have access regardless — they need to set up maps, characters, and audio before opening the doors. Lobby cards now show a Live/Closed (GM view) or Live/Waiting (player view) badge so everyone knows the state at a glance. Existing campaigns auto-migrate to `session_active=False` so deploying this version doesn't suddenly expose any tabletops; GMs need to Start them.

### Added
- `Campaign.session_active` (boolean, default False) and `Campaign.session_started_at` (DateTime nullable) columns.
- `POST /campaign/{id}/session/start` and `POST /campaign/{id}/session/end` endpoints, GM-only.
- `session_waiting.html` template with auto-redirect via WebSocket + 10s polling fallback.
- `session_started` and `session_ended` WebSocket message types.
- ▶ Start session / ⏹ End session buttons in the lobby card body and the tabletop header.
- Live/Closed/Waiting status badges on lobby cards.

### Changed
- `campaign_view` returns the waiting page for non-GM members when `session_active=False` instead of letting them in.
- `tabletop.js` redirects non-GM clients to the lobby when it receives `session_ended`.

### Schema
- `campaigns.session_active BOOLEAN NOT NULL DEFAULT FALSE` — added.
- `campaigns.session_started_at TIMESTAMP NULL` — added.
- `SCHEMA_VERSION` bumped from 5 to 6.

### Notes
- GMs can re-Start an already-active session — it's idempotent and just refreshes `session_started_at`. Useful if WebSocket clients drifted out of state.
- Admins are treated as GMs for session control in any campaign, matching the existing pattern for token / sheet / audio permissions.
- Future: a per-campaign "session ends in 5 minutes" warning broadcast would be a nice polish; not included in this release.

---

## [0.6.0] - 2026-05-02

**Schema version:** 5

**Commit summary:** Add user settings page with per-track volume and synchronize audio playback across all clients

**Description:** Players and GMs now hear the same point in every track. The server records a UTC timestamp the moment the GM hits Play and broadcasts it with each `audio_play` event; clients seek their `<audio>` element to the matching offset and run a 5-second drift-correction loop so a tab that was throttled in the background snaps back to the right position. A new `/settings` page in the top navigation lists every track in every campaign the user can see, with a slider per track that persists server-side as a per-track volume override; the effective playback volume is master × per-track. The tabletop sound panel also exposes a "this track" slider that appears whenever something is playing, plus a ⟳ Resync button anyone can use if they suspect drift. Existing PostgreSQL deployments will auto-migrate on first boot via additive ALTER TABLE statements; the new `user_audio_preferences` table is created automatically.

### Added
- `Campaign.now_playing_started_at` (DateTime nullable) — server timestamp used for client-side time sync.
- `UserAudioPreference` table (user_id, track_id, volume) for per-user-per-track volume overrides.
- `app/routes/user_routes.py` + `/settings` page listing all per-track overrides grouped by campaign and playlist.
- `GET /api/audio/preferences` and `POST /api/audio/preferences/{track_id}` endpoints.
- `POST /campaign/{id}/audio/resync` endpoint that re-broadcasts the current playback state on demand.
- "This track" volume slider in the tabletop sound panel (visible only while audio is playing).
- ⟳ Resync button in the sound panel.
- "Settings" link in the top navigation.
- Drift-correction loop in `audio.js` that snaps playback to the expected position if it drifts more than 0.75 s.

### Changed
- `audio_play` WebSocket payload now includes `started_at_ms` (UTC epoch) so all clients can compute the same offset.
- Tabletop view passes `now_playing_started_at_ms` to the template so reconnecting clients sync immediately on first paint.
- Effective `<audio>` volume is now `master × per-track`. Master volume continues to live in localStorage; per-track overrides persist server-side.

### Schema
- `campaigns.now_playing_started_at TIMESTAMP NULL` — added.
- New table `user_audio_preferences` (id, user_id, track_id, volume, updated_at) with unique (user_id, track_id).
- `SCHEMA_VERSION` bumped from 4 to 5.

### Notes
- Time sync depends on the player's clock being roughly correct (no NTP drift > a few seconds). Browsers and OSes generally are; if a client's wall clock is wildly off, the resync interval will keep yanking them, which is the right behavior — just less pleasant. A future "audio_sync" handshake on connect could measure the round-trip and correct for it; for ambient music this is overkill.
- Per-track override of `null` means "use 100%". A user can reset an override from `/settings` by clicking the Reset button.

---

## [0.5.0] - 2026-05-01

**Schema version:** 4

**Commit summary:** Add per-campaign audio playlists with GM playback controls and player volume panel

**Description:** GMs can now upload mp3/ogg/wav/m4a tracks into named playlists per campaign and play them to all connected players in real time. Playback state is persisted on the Campaign row so reconnecting players resume the current track. Tracks auto-advance through the playlist when one ends, with an optional loop-at-end setting. Players get a sound panel with a volume slider, mute toggle, and "click to enable audio" prompt for browsers that block autoplay; volume and mute are persisted per-browser via localStorage. The first incoming `audio_play` for a player who hasn't interacted with the page yet may be blocked by the browser — they'll see the "click to enable" button and one click unblocks all subsequent tracks. Existing PostgreSQL deployments will auto-migrate on first boot via additive ALTER TABLEs.

### Added
- `Playlist` and `PlaylistTrack` models; `/static/uploads/audio/` storage directory.
- `Campaign.now_playing_track_id` (nullable INTEGER FK to playlist_tracks) and `Campaign.now_playing_loop` (boolean) for persisted playback state.
- `app/routes/audio_routes.py` exposing `/campaign/{id}/playlists`, `/campaign/{id}/playlists/{pid}/tracks`, `/campaign/{id}/audio/play`, `/audio/stop`, `/audio/next`, `/audio/loop`.
- Player audio panel in the tabletop sidebar (volume + mute + now-playing line + autoplay-unblock button).
- GM audio-management UI in `/campaign/{id}/settings#audio` (playlist CRUD, track upload, per-track Play, stop-everyone button).
- WebSocket message types `audio_play` and `audio_stop` broadcast through the existing per-campaign hub.
- `tabletop.js` now redispatches every WebSocket message as a `vtt:ws-message` CustomEvent so additional client modules (like `audio.js`) can react without re-opening the socket.

### Changed
- Tabletop view now passes `now_playing` (a PlaylistTrack or None) to the template so reconnecting clients immediately resume.
- Campaign settings view now passes `playlists` for GM management.
- `app/main.py` ensures `static/uploads/{maps,tokens,thumbnails,audio}/` exist on startup.

### Schema
- New table `playlists` (id, campaign_id, name, created_at).
- New table `playlist_tracks` (id, playlist_id, name, file_url, position, created_at).
- `campaigns.now_playing_track_id INTEGER NULL` — added.
- `campaigns.now_playing_loop BOOLEAN NOT NULL DEFAULT TRUE` — added.
- `SCHEMA_VERSION` bumped from 3 to 4.

### Notes
- Time-position sync across clients is intentionally not implemented in this release. When the GM hits play, every client starts the track from t=0. This is the right trade-off for ambient music loops; tight cinematic sync would need a clock-synchronization protocol that's worth its own ticket.
- Audio file URLs under `/static/uploads/audio/` are public to anyone who knows the UUID-randomized URL. Acceptable for the home-LAN use case but if you ever expose SimpleVTT to the open internet, consider proxying audio through an auth-checked endpoint.
- Per-client per-track volume control is not exposed; players can only adjust their global master volume. Could be added later if needed.

---

## [0.4.0] - 2026-05-01

**Schema version:** 3

**Commit summary:** Add per-campaign co-GM role so multiple users can run the same game

**Description:** Campaign membership now carries an `is_gm` flag, making it possible to have multiple GMs per campaign. The campaign's primary GM (owner/creator) and any user with `is_gm=True` on a membership row both get full GM powers in that campaign. GMs can promote or demote players to/from GM only for the campaigns they're a GM in. Site admins can manage GM roles in any campaign. The primary GM cannot be demoted via this UI — admins would need to transfer ownership separately. Existing PostgreSQL deployments auto-migrate on first boot.

### Schema
- `campaign_memberships.is_gm BOOLEAN NOT NULL DEFAULT FALSE` — added.
- `SCHEMA_VERSION` bumped from 2 to 3.

---

## [0.3.0] - 2026-05-01

**Schema version:** 2

**Commit summary:** Lock campaigns to a game system, add thumbnails, polish lobby with badges and cards

**Description:** Campaigns now declare a game system (generic or D&D 5e for now), and all characters in a campaign are forced to use that system's sheet template. The 5e sheet becomes rollable. Quick-die buttons in the dice tray are also system-aware. Campaigns can have an uploaded thumbnail. The lobby was redesigned as a card grid with role and system badges.

### Schema
- `campaigns.game_system VARCHAR(40) NOT NULL DEFAULT 'generic'` — added.
- `campaigns.thumbnail_url VARCHAR(500) NULL` — added.
- `SCHEMA_VERSION` bumped from 1 to 2.

---

## [0.2.0] - 2026-05-01

**Schema version:** 1

**Commit summary:** Move all configuration to environment variables and switch default port to 8013

**Description:** Configuration is now driven entirely by environment variables (loaded from `.env` in Docker), removing the separate `config.yaml` file. The default listening port changes from 8000 to 8013. This is a breaking change: existing deployments must copy their previous YAML values into `.env`.

---

## [0.1.0] - 2026-05-01

**Schema version:** 1

**Commit summary:** Initial SimpleVTT release with auth, real-time tabletop, character sheets, and Docker stack

**Description:** First working version of SimpleVTT. Provides a self-hosted virtual tabletop with local + Google SSO login, square or hex grid maps with click-and-drag tokens, a dice roller with three-tier visibility, generic and D&D 5e character sheets, an admin portal, and an automated PostgreSQL backup sidecar. The full stack ships as multi-arch Docker images.
