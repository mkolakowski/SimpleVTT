# Notes & Handouts

**Status:** ✅ All phases shipped (v2.554.0–v2.561.0). GM prep notes, handouts (author + reveal-to-all/specific + the player toast), player public notes, and end-to-end-encrypted private notes (browser PBKDF2+AES-GCM; the server stores only ciphertext) — all live in the Notes drawer. (Plan authored v2.553.2.)

A session-prep + reference system with three audiences and a hard
privacy guarantee:

1. **GM prep notes** — the GM's private prep (lore, plot beats, stat
   scratch, secrets). GM + co-GMs only; never visible to players.
2. **Handouts** — content the GM *prepares* and *reveals* to the table:
   a letter, a map fragment, an item card, an NPC portrait. Revealed to
   all players or to specific players; players see only what's revealed
   to them.
3. **Player notes** — each player keeps their own notes, marked
   **public** (visible to everyone at the table) or **private**.
   **Private notes are end-to-end encrypted: only the player can ever
   read them — not other players, not the GM, and not a server operator
   with raw database access.**

The privacy model is the defining constraint and is specified first.

---

## Privacy model — end-to-end encryption for private notes

Per the design decision (v2.553.2), private player notes are **E2E
encrypted in the core**, not merely access-controlled. The reasoning:
the GM is frequently also the server operator (the public demo runs on
the GM's own laptop), so an application-layer "the GM can't see it"
guarantee that leaves plaintext in Postgres would not actually honor
"not even the GM." Encryption makes the guarantee cryptographic.

### What the server stores for a private note

Nothing readable. For a private note the server holds **only ciphertext**
— no plaintext title, no body, no preview, no word count derived from
content. Concretely, the row carries an opaque envelope the server never
parses:

```
{ "v": 1, "iv": "<base64 96-bit IV>", "ct": "<base64 AES-GCM ciphertext+tag>" }
```

…stored in the `enc_title` and `enc_body` columns (each its own IV). The
plaintext `title` / `body` columns are NULL for encrypted notes. There is
**no server endpoint that decrypts** — the server cannot, by
construction, return plaintext for a private note, because it never has
the key.

### Key handling (browser-only, zero dependencies)

Uses the platform **Web Crypto API** (`crypto.subtle`) — no third-party
crypto library, so it works offline and inside the Docker-internal-only
network ethos.

- **Key derivation:** `PBKDF2(passphrase, salt, iterations, SHA-256)` →
  a 256-bit **AES-GCM** key. Iterations ≥ 600,000 (OWASP 2023 floor);
  pinned in the key-material row so it can be raised later without
  breaking old notes.
- **Per-user salt** (128-bit random) + KDF params live in a new
  `note_encryption_keys` row. The salt is **not** secret; the passphrase
  is. The passphrase is **never** sent to the server — not at set time,
  not at unlock time.
- **Passphrase verification:** the key-material row stores a `key_check`
  — `AES-GCM(derived_key, "simplevtt-notes-v1")`. On unlock the client
  derives the key from the entered passphrase and tries to decrypt
  `key_check`; success ⇒ correct passphrase. This detects a wrong
  passphrase without mangling a real note into garbage.
- **Per-note encryption:** fresh random 96-bit IV per field per save;
  AES-GCM provides confidentiality **and** integrity (a tampered
  ciphertext fails to decrypt).
- **Session lifetime:** the derived key lives in memory for the tab
  session only (never `localStorage`, never disk, never the wire).
  Default: re-prompt for the passphrase once per session; a per-user
  setting can relax this to "remember for this device session"
  (`sessionStorage`-held key) for convenience.

### Recovery: there is none, by design

A lost passphrase = permanently unreadable private notes. The server
cannot reset it (that's the whole point). The set-passphrase UI must
state this in plain language and require an explicit acknowledgement.
**Optional sub-feature (filed, not in the core):** an offline "recovery
key" the user downloads at set-time (a second AES key-wrap of the note
key) so a lost passphrase is recoverable from a file the user kept —
opt-in, since it widens the attack surface to "whoever holds the file."

### Defense in depth — app-layer ACL still applies

Even though private bodies are useless without the key, the server still
**refuses to hand a private note's row to anyone but its author** (SQL
`WHERE` + WS scoping below). Two independent layers: the crypto means a
leak is unreadable; the ACL means it doesn't leak in the first place,
and the GM's UI never even sees that a private note exists with a given
title-length or timestamp.

---

## Data model

Three new tables, added to `app/models.py` and created in
`_apply_inline_migrations` via `Model.__table__.create(bind=engine,
checkfirst=True)` (the established pattern — `Base.metadata.create_all`
in `init_db` creates them on fresh DBs, the explicit `create(checkfirst)`
covers existing DBs). `SCHEMA_VERSION` bumps once per table added.

### `campaign_notes` — GM prep notes + player notes

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `campaign_id` | FK → campaigns, `ON DELETE CASCADE` | |
| `author_user_id` | FK → users | the GM or the player who owns the note |
| `kind` | enum `gm_note` \| `player_note` | |
| `visibility` | enum `gm_only` \| `public` \| `private` | see access rules |
| `title` | String(200), nullable | plaintext for non-private; NULL for private |
| `body` | Text, nullable | plaintext markdown for non-private; NULL for private |
| `enc_title` | Text, nullable | ciphertext envelope for private notes |
| `enc_body` | Text, nullable | ciphertext envelope for private notes |
| `is_encrypted` | bool, default false | true ⇒ read `enc_*`, ignore `title`/`body` |
| `folder` | String(120), default "" | single-level grouping, like `Map.folder` / `Encounter.folder` |
| `pinned` | bool, default false | |
| `created_at` / `updated_at` | DateTime | `updated_at` `onupdate=func.now()` |

Visibility ↔ kind matrix:
- `gm_note` ⇒ always `gm_only` (GM + co-GMs). Sharing GM content with
  players is **not** a visibility flip — it's authoring a **handout**.
- `player_note` ⇒ `public` (all campaign members) or `private` (author
  only, encrypted).

### `handouts` — GM-authored, revealable

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `campaign_id` | FK → campaigns, CASCADE | |
| `author_user_id` | FK → users | the GM/co-GM who made it |
| `title` | String(200) | |
| `body` | Text, default "" | markdown |
| `image_url` | String(500), nullable | reuses the existing `/static/uploads` image flow (same as `Map.image_url` / `Token.image_url` / `Character.portrait_url`) |
| `folder` | String(120), default "" | |
| `revealed` | bool, default false | |
| `reveal_to` | JSON | `"all"` or a list of `user_id`s (the dialect JSON/TEXT split used by `Token.hidden_from_user_ids`) |
| `created_at` / `updated_at` | DateTime | |

Handouts are never encrypted — they're GM-authored content meant to be
shown. The "who can see it" control is `revealed` + `reveal_to`.

### `note_encryption_keys` — per-user crypto material

| Column | Type | Notes |
|---|---|---|
| `user_id` | FK → users, **PK** | one passphrase per user, across campaigns |
| `salt` | String(64) | base64 128-bit salt (not secret) |
| `kdf` | String(20), default "PBKDF2-SHA256" | |
| `iterations` | int | pinned so it can be raised without breaking old notes |
| `key_check` | Text | AES-GCM of a fixed sentinel, for passphrase verification |
| `created_at` | DateTime | |

The server stores salt + params + check token only. It holds **no key,
no passphrase, and no plaintext** — there is deliberately no column or
endpoint that could.

---

## Access rules (server-enforced)

The security core. Enforced in the SQL `WHERE` clause on **every** read
path, never client-side only.

- **`private` notes** are returned **only** when `author_user_id ==
  current_user`. The GM's "all campaign notes" query carries
  `AND NOT (visibility = 'private' AND author_user_id != :me)` so private
  rows are excluded at the database level — the GM endpoint *cannot*
  return another user's private note even if asked by id (→ 404).
- **`public` notes** → any campaign member (GM + players).
- **`gm_only` notes** → GM + co-GMs (`Campaign.gm_user_id` or a
  `CampaignMembership` row with `is_gm=True`).
- **Handouts** → GM/co-GM always; a player gets one iff `revealed AND
  (reveal_to == "all" OR current_user in reveal_to)`.

Auth reuses the existing helpers (`require_user`, `_user_is_gm`,
`_user_can_view_campaign`) already used throughout the tabletop routes.

---

## WebSocket delivery (the per-user channel already exists)

`hub.broadcast(campaign_id, msg, *, recipient_filter=…)`
(`app/realtime.py`) takes a filter called with each connection's
identity `{user_id, is_gm, …}` returning send/skip. It is **already**
used to keep `gm_only` dice rolls off non-GM sockets server-side. The
notes system reuses it verbatim:

- **`note_updated`** for a private note → delivered **only to the
  author's connections**: `recipient_filter=lambda i: i["user_id"] ==
  author_id`. **Never** a campaign-wide broadcast — the GM shares that
  room. (For public notes, broadcast to all members.)
- **`handout_revealed`** → delivered only to the targeted players
  (`reveal_to`) → pops a toast + adds the handout to their Notes drawer.
- **GM prep notes** never broadcast to players at all.

This means a private note never crosses the wire to the GM's socket,
*and* its body is ciphertext even if it did.

---

## HTTP API (mirrors the existing route style)

All under `/api/campaign/{cid}`, returning JSON, gated by the auth
helpers; every endpoint lands a happy-path + error-path harness test.

- `GET  /notes` — list notes visible to the caller (applies the access
  rules above; `?kind=` / `?folder=` filters). Private notes come back as
  ciphertext envelopes for the owner to decrypt client-side.
- `POST /notes` — create (`kind`, `visibility`, plaintext or `enc_*`).
- `PATCH /notes/{id}` / `DELETE /notes/{id}` — author-or-GM for
  non-private; **author-only** for private (the GM can't even edit/delete
  blind — 404).
- `GET/POST /handouts`, `PATCH/DELETE /handouts/{id}` — GM/co-GM only.
- `POST /handouts/{id}/reveal` — `{revealed: bool, to: "all" | [user_id]}`
  → broadcasts `handout_revealed` to the targets.
- `GET  /notes/encryption` / `PUT /notes/encryption` — fetch/set the
  caller's `note_encryption_keys` row (salt + params + key_check). The
  PUT body never contains a passphrase or key.

---

## UI

A new **"Notes"** drawer tab in the tabletop sidebar (alongside Battle /
Characters / Settings), plus a prep surface on the campaign management
page for out-of-session work.

- **GM view:** *Prep Notes* (folders, pin, markdown), *Handouts* (author
  + image upload + per-player reveal toggles), and a read-only pane of
  players' **public** notes. The GM never sees a private-note row.
- **Player view:** *My Notes* (create, **public/private** toggle,
  folders), a lock/unlock control for private notes (passphrase prompt →
  derive key → decrypt in place), *Revealed Handouts* (read-only), and
  other players' public notes.
- Markdown rendering reuses the wiki/chat markdown path. All interactive
  controls meet the 44×44px touch-target rule (32px minimum inside the
  dense notes list, with the documented compact-panel exception).
- Private notes render as "🔒 Locked — enter passphrase to read" until
  the session key is present; titles are encrypted too, so the locked
  list shows only timestamps + a lock glyph.

---

## Phases

1. **Schema + GM prep notes.** ✅ **Shipped v2.554.0.** Added the
   `campaign_notes` table (schema v72; the `handouts` +
   `note_encryption_keys` tables land with their phases rather than all
   up front) and `app/routes/notes_routes.py` with `gm_note` CRUD
   (`gm_only`, plaintext) over `/api/campaign/{id}/notes`. Harness:
   `tests/harness/test_notes.py` — CRUD happy paths + the access-control
   core (player create → 403, player can't see/get/delete a gm_note).
   The GM drawer pane is folded into Phase 5 (UI).
2. **Handouts.** ✅ **Shipped v2.555.0.** `handouts` table (schema v73) +
   CRUD + `POST …/handouts/{id}/reveal` with `reveal_to` targeting + the
   `handout_revealed` WS event scoped via `recipient_filter`. Harness:
   `tests/harness/test_handouts.py` — reveal-to-specific reaches only the
   targeted player's socket (not another's), reveal-to-all reaches
   everyone, un-revealed handouts are 404 to players, error paths. Image
   *upload* UI is folded into Phase 5; the endpoint already accepts an
   `image_url`.
3. **Player public notes.** ✅ **Shipped v2.556.0.** `public` visibility
   on the `/notes` endpoints (`kind=player_note`) + author-or-GM write
   rule (`_can_edit_note`) + a scoped `note_updated` WS broadcast
   (`_broadcast_note_event`: public → all, gm_only → GMs only, private →
   author only). `visibility=private` is rejected (400) until Phase 4's
   encrypted client — no plaintext "private" notes ever. Harness:
   `tests/harness/test_player_notes.py` — public visible to all, GM
   moderation, non-author 403, the gm_note WS scoping (player never sees
   a gm_note event). The GM-excluded-query test for *private* notes lands
   with Phase 4 (no private notes exist to exclude yet).
4. **Private notes — E2E encryption.**
   - **4a — server side. ✅ Shipped v2.557.0.** The `note_encryption_keys`
     table (schema v74) + `GET/PUT/DELETE /api/notes/encryption`
     (set-once; DELETE = wipe key + the user's encrypted notes) + the
     private branch of `create_note`/`update_note` (ciphertext-only,
     plaintext refused). Server treats `enc_title`/`enc_body` as opaque.
     Harness `tests/harness/test_private_notes.py`: ciphertext
     round-trips byte-for-byte; **the GM can't list/get a private note
     (404)**; another player can't either; private `note_updated` WS
     reaches only the author; `list_notes` excludes others' private rows
     at the SQL level. Real AES-GCM is exercised in 4b.
   - **4b — browser crypto + round-trip. ✅ Shipped v2.558.0.**
     `app/static/notes_crypto.js` (`window.NotesCrypto`: PBKDF2-SHA256 →
     AES-GCM-256, `{v,iv,ct}` envelopes, `key_check` verification — Web
     Crypto only, no deps). Playwright `tests/harness_ui/test_notes_crypto.py`:
     the module round-trips with no plaintext in the ciphertext + wrong
     passphrase fails closed, and the full path (encrypt → PUT config →
     POST private note → GET → decrypt) confirms the server stored no
     plaintext and **the POST body carried no plaintext on the wire**.
     Passphrase set/unlock UX is wired into the Phase 5 drawer.
5. **The Notes drawer UI.** 🟠 In progress.
   - **5a — GM prep notes. ✅ Shipped v2.559.0.** A "📝 Notes" tabletop
     sidebar tab + `app/static/notes.js` rendering the `#notes-drawer`
     from `/notes`: GM composer (title/body/folder/pin) + per-card
     edit/delete over `gm_only` notes, with `note_updated` WS live sync.
     Playwright `tests/harness_ui/test_notes_drawer.py`.
   - **5c — player public notes. ✅ Shipped v2.560.0.** A visibility
     `<select>` in the composer (player: Public / Private; GM also Prep);
     public notes render + edit like prep notes.
   - **5d — private-note passphrase set/unlock. ✅ Shipped v2.560.0.**
     `notes.js` wires in `notes_crypto.js`: set-up flow (passphrase + "no
     recovery" warning) → `PUT /encryption`; save encrypts title+body in
     the browser, POSTs only ciphertext; a locked private note shows
     "🔒 Locked" + Unlock (verify against `key_check`) → decrypt in place.
     Playwright `test_notes_drawer.py::test_alice_private_note_encrypt_unlock`.
   - **5b — handouts panel. ✅ Shipped v2.561.0.** A "📜 Handouts"
     sub-view toggle; GM authoring (title/body/image URL/folder) +
     edit/delete + Reveal to all / Reveal to… (per-player checkbox
     picker from `MEMBERS`) / Hide; players see revealed handouts
     read-only with a live `handout_revealed` toast + add/remove.
     Playwright `test_notes_drawer.py::test_handout_create_reveal_hide`
     (cross-context: GM reveals → player sees live → GM hides → gone).
     A dedicated image-*upload* widget (vs. a pasted URL) is filed polish.

   - **5e — search + folder grouping. ✅ Shipped v2.563.0.** A per-view
     search box + collapsible folder groups in the drawer; private notes
     are searchable only while unlocked (filter reads the decrypted
     cache, never ciphertext).

   (Original Phase-5 polish notes:) Folders/pinning/search (search covers plaintext notes
   only — private notes are unsearchable by construction), markdown
   niceties, the campaign-management prep surface, mobile layout.

### Optional / filed
- ✅ **Markdown rendering** for note + handout bodies — shipped v2.562.0
  (safe-subset client renderer in `notes.js`; scheme-validated links).
- **Downloadable recovery key** for private notes (opt-in; see Privacy
  model).
- **Handout image *upload* widget** (vs. the current pasted URL).
- **Handout media beyond images** (PDF/audio) — reuse the upload flow.
- **Cross-campaign player notebook** — the encryption key is already
  per-user; a "my notebook across all my campaigns" view is a natural
  follow-up.

---

## Substrate notes (verified against the codebase, v2.553.1)

- **Models** (`app/models.py`): `Campaign.gm_user_id`,
  `CampaignMembership(user_id, is_gm, color)`. New tables follow the
  SQLAlchemy-2.0 `Mapped[...]` style; the `Visibility` enum that exists
  today is roll-scoped (`gm_only` / `gm_and_roller` / `public`) — notes
  define their own enum.
- **Migrations** (`app/database.py::_apply_inline_migrations`): new
  tables via `Model.__table__.create(bind=engine, checkfirst=True)`;
  JSON columns use the postgres-JSON / sqlite-TEXT dialect split (see
  `Token.hidden_from_user_ids`, schema v59).
- **Per-user WS delivery** (`app/realtime.py::CampaignHub.broadcast`):
  `recipient_filter` is the existing, battle-tested mechanism (used for
  `gm_only` rolls) that makes "deliver to one user, not the GM"
  possible — no new transport needed.
- **Image upload:** handouts reuse the same `/static/uploads` flow that
  backs `Map.image_url` / `Token.image_url` / `Character.portrait_url`.
- **No existing notes/handouts model** — confirmed by reading
  `app/models.py` in full; this is greenfield (run a final
  `grep -ri "handout\|journal"` across `app/` + `templates/` at
  implementation start to rule out any client-only scratchpad).

This doc is surfaced through the wiki at
`/wiki/doc/plan-notes-and-handouts`.
