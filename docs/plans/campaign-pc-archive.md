# Campaign & PC Retirement / Archive — Design Plan

**Status:** 🔥 IN PROGRESS — Phase 1 (this plan doc) shipping; Phases 2–4 queued.

Campaigns end and characters retire. Today the only non-active state is
**delete** (permanent, cascade). That's too sharp: a GM who finishes a
campaign, or a player whose character dies / is shelved, wants it **out of the
active lists but kept** — the sheet, the roll history, the encounter all
preserved, reversible later. This plan adds a soft **archive** (campaigns) /
**retire** (characters) state alongside the existing hard delete.

## Goal

- **Campaign archive** — a GM can archive a campaign they own. Archived
  campaigns drop out of the lobby's active sections into a collapsed
  "Archived" section, are reversible (unarchive), and remain fully readable
  via their direct URLs. Archive is **not** delete — no data is removed.
- **PC retirement** — a character's owner can retire a character. Retired
  characters drop out of the active `/characters` listing into a "Retired"
  section, are reversible (unretire), and keep their full sheet + history.

Archive/retire is a reversible soft-state; delete stays the permanent
destructive path (unchanged).

## Data model

Two parallel nullable columns on each table (mirrors the same shape so the
UI + queries are symmetric):

| Table | Column | Type | Meaning |
|-------|--------|------|---------|
| `campaigns` | `is_archived` | `BOOLEAN NOT NULL DEFAULT FALSE` | archived flag (fast filter) |
| `campaigns` | `archived_at` | `TIMESTAMP NULL` | when it was archived (audit / sort) |
| `characters` | `is_archived` | `BOOLEAN NOT NULL DEFAULT FALSE` | retired flag |
| `characters` | `archived_at` | `TIMESTAMP NULL` | when it was retired |

Each table's columns land in their own migration block in
`_apply_inline_migrations()` (`app/database.py`), each bumping
`SCHEMA_VERSION` by +1 in its own commit.

## Phases (one commit each)

### Phase 1 — Plan doc + wiki surfacing ✅ (this commit)

This document, surfaced through `/wiki` per the doc-surfacing rule.

### Phase 2 — Campaign archive

- **Schema:** `campaigns.is_archived` + `archived_at` (migration block,
  `SCHEMA_VERSION` +1); model fields on `Campaign`.
- **Endpoints (GM-only):**
  - `POST /campaign/{id}/archive` → sets `is_archived=True`, `archived_at=now`.
  - `POST /campaign/{id}/unarchive` → clears both.
- **Lobby** (`GET /`, `home()` in `tabletop_routes.py`): the owned / co-GM /
  member queries exclude `is_archived`; a new `archived_campaigns` list feeds
  a collapsed "Archived" section in `lobby.html` with an **Unarchive**
  control.
- **Settings** (`campaign_settings.html` danger zone + `campaign_settings_save`):
  an "Archive this campaign" control (distinct from Delete — archive is
  reversible).
- **Tests:** `tests/harness/test_campaign_archive.py` — archive → 200, lobby
  excludes it / archived section includes it, unarchive round-trip,
  non-GM 403, unknown-campaign 404.

### Phase 3 — PC retirement

- **Schema:** `characters.is_archived` + `archived_at` (migration block,
  `SCHEMA_VERSION` +1); model fields on `Character`.
- **Endpoints (owner-only):**
  - `POST /characters/{id}/retire` → sets `is_archived=True`, `archived_at=now`.
  - `POST /characters/{id}/unretire` → clears both.
- **Listing** (`all_characters()` + `all_characters.html`): the owner query
  excludes retired; a new "Retired" section lists them with an **Unretire**
  control.
- **Character page** (`character_page.html` danger zone): a "Retire this
  character" control alongside Delete.
- **Tests:** `tests/harness/test_pc_retirement.py` — retire → 200, listing
  excludes it / retired section includes it, unretire round-trip,
  non-owner 403, unknown-character 404.

### Phase 4 — Demo reseed

With the archive substrate in place, reshape the demo:

- **Archive the original demo campaign** — "Demo: The Sundered Vault"
  (`seed_campaign()`, id=1, the harness `CAMPAIGN_ID` anchor) is marked
  `is_archived=True` at seed time. It stays id=1 so every harness fixture +
  the 4,200-test suite keep their anchor; it just no longer shows in the
  active lobby (it moves to the Archived section).
- **Remake the Level 5** — add a fresh `Demo L5: <name>` spec to
  `CAMPAIGN_SPECS` in `demo_campaigns.py`, matching the L3/L9/L13/L18
  convention, so the leveled lineup becomes **L3 / L5 / L9 / L13 / L18**.
- **Tests:** update `test_demo_campaigns.py` lobby-presence assertions (the
  Vault now appears archived, not active; the new L5 appears in its GM's +
  members' lobbies).

## Out of scope

- Bulk archive / auto-archive-on-inactivity (manual only for now).
- Archiving a campaign does **not** cascade-retire its characters — the two
  states are independent (a retired PC can live in an active campaign; an
  archived campaign's PCs stay un-retired).
- Token / map archival (only the campaign + character rows carry the flag).

## Cross-references

- `app/routes/tabletop_routes.py` — `home()` lobby (`GET /`),
  `campaign_settings` / `campaign_settings_save`.
- `app/routes/user_routes.py` — `all_characters`, `standalone_character_sheet`.
- `app/demo_seed.py` `seed_campaign` / `reset_and_reseed`;
  `app/demo_campaigns.py` `CAMPAIGN_SPECS`.
