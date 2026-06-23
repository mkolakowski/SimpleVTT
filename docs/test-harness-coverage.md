# Test Harness Coverage

Living catalog of the click-through harness suite at `tests/harness/`.

> **Update rule.** Whenever a test is added, removed, renamed, or has its assertion shape materially changed, update this file in the same commit. The CLAUDE.md harness-discipline rule already requires harness coverage for every endpoint commit; this file makes the coverage navigable.

**Total tests:** 4195 in `tests/harness/` + 103 in `tests/harness_ui/` (as of v2.599.7, 2026-06-23). `tests/harness/test_session_cookie_hardening.py` (new, +3, v2.599.7) guards the session cookie hardening — both services plumb `SESSION_COOKIE_SECURE`, both middleware configs set `same_site="lax"` + env-driven `Secure`, and `.env.example` documents the flag. `tests/harness/test_js_xss_escaping.py` (+1, v2.599.6) extends the DOM-XSS source guards to the beast-picker CR-cap warning (a homebrew monster's `cr` must be `_esc`'d before `innerHTML` injection). `tests/harness/test_js_xss_escaping.py` (new, +1, v2.599.5) is a source guard for the DOM-XSS fix where the Dash/opportunity-attack modal injected a combatant's `watcher_name` into `innerHTML` raw — asserts it now passes through `escapeHTML()` and the raw form is gone. `tests/harness/test_upload_safety.py` (new, +6, v2.599.4) covers the `safe_ext` upload-extension allowlist (allowed exts pass + lowercase, no-suffix default, `.html`/`.svg`/`.js` rejected with 400, video-only set, audio set, + a wiring guard that the affected upload routes go through `safe_ext`/`IMAGE_VIDEO_EXTS`) — the stored-XSS fix where uploads took the on-disk extension from the user filename and served it from `/static`. `tests/harness/test_mini_sheet_xss.py` (new, +2, v2.599.3) renders `_tab_actions.html` with a malicious payload and asserts it is HTML-escaped, and guards `_tab_spells.html` at the source level — covers the stored-XSS fix where custom attack/item + homebrew-spell detail fields were concatenated raw into a `| safe` block. `tests/harness/test_visitor_log.py` (+1, v2.599.2) asserts docker-compose's `app` service plumbs `VISITOR_REQUEST_LOG_ENABLED` (it was never declared, so the feature silently never fired since v2.480.0). `tests/harness/test_visitor_log.py` (+1, v2.599.1) asserts `CF-Connecting-IP` opens the per-request visitor-log gate with `TRUSTED_PROXY_HOPS=0` (the pure-CF-Tunnel config), and the "no trustworthy IP source" test now disables `TRUST_CF_CONNECTING_IP` too. `tests/harness/test_fail2ban_ignoreip_wiring.py` (+1) asserts the published Cloudflare edge ranges (incl. `172.64.0.0/13` + an IPv6 block) are allowlisted in the jail `ignoreip`, so fail2ban can't ban the Cloudflare edge (it was self-banning `172.67.x` behind a CF Tunnel). Demo-rework arc (`tests/harness/test_demo_campaigns.py`): D3 (+3) — L3 "Goblin Warrens" in its GM's + members' lobbies (demo-gm/alice/carol); D4 (+5) — L9 "Storm Over Saltmarsh" in the second GM's (demo-gm2) + members' (bob/dave/erin) lobbies, and demo-gm2 owns *only* that campaign; D5 (+3) — L13 "Shadowfell Spire" in its GM's + members' (demo-gm/bob/dave) lobbies; D6 (+4) — L18 "Dragon's Apotheosis" in its GM's + members' (demo-gm/carol/erin) lobbies + a full-arc check that all five leveled campaigns seed; D7 (+1) — a shared player (carol) sees both the L3 and L5 campaigns in her lobby; D8 (+1, `test_wiki.py`) — `/wiki/demo-content` serves the demo catalog (all five campaign names + the collapsed generation-prompts section). `tests/harness/test_demo_gm_admin_gate.py` (+2) — the new `demo-gm2` (GM role, not site-admin) and the three new players (`demo-carol`/`demo-dave`/`demo-erin`) all get 403 on `/admin`; `tests/harness/test_demo_campaigns.py` (+7, new) — every one of the seven demo accounts logs in (grows as the five leveled campaigns land). `tests/harness/test_admin_center.py` (+6, Arc B2 of `docs/plans/app-wide-roles-and-storage.md`) covers per-user/per-campaign storage limits + enforcement: the `storage_quota.check_quota` unit (fast no-op when unlimited; blocks over the campaign + user limits; passes under; fails open when accounting is down — host-side sqlite + monkeypatched accounting); the storage-limit routes require auth + are refused for basic-auth header callers (parametrized over `/users/{id}` + `/campaigns/{id}`); and an MFA-on end-to-end — set a tiny campaign limit → over-limit Center map upload rejected (`err=`) → clear limit → upload succeeds. `tests/harness/test_admin_center.py` (+6, Arc B1 of `docs/plans/app-wide-roles-and-storage.md`) covers storage accounting: the pure `storage.aggregate` attributor (host-side, no DB — campaign→GM, standalone portrait→owner, unreferenced→unattributed, by-type sums, empty tree) and the live `/api/storage` (shape + requires-auth) + `/storage` page (redirects unauthenticated; renders By-user / By-campaign after login). `tests/harness/test_admin_center.py` (+3, Arc A4 of `docs/plans/app-wide-roles-and-storage.md`) covers Admin Center role assignment (`POST /users/{id}/role`): requires auth (unauth → 303), refused for basic-auth header callers (403/404), and an MFA-on grant-GM (pill shows) → revoke → grant/revoke admin → unknown-role err → delete round-trip on a throwaway user. `tests/harness/test_campaign_roles.py` (+3 A2 + 2 A3 = 5 total, Arc A2/A3 of `docs/plans/app-wide-roles-and-storage.md`) covers the role gates + caps: **A2** — a player (demo-alice) → 403 on `POST /campaigns` (the `require_gm` gate), a GM (demo-gm) creates a campaign (303 → campaign page), an unauthenticated POST is refused; the per-GM `GM_CAMPAIGN_LIMIT` cap is enforced inline (not live-tested — would need 10 creates). **A3** — a player creating standalone characters hits the `PLAYER_CHARACTER_LIMIT` cap → 403 with a "limit" message within a bounded number of creates, while a GM is uncapped (several creates all succeed). `tests/harness/test_wiki.py` (+1, v2.584.0 "The Three Keys") surfaces the new `docs/plans/app-wide-roles-and-storage.md` design plan (Arc A1 — the app-wide `User.is_gm` role substrate, schema v76, `require_gm` gate, `PLAYER_CHARACTER_LIMIT`/`GM_CAMPAIGN_LIMIT` config, demo-seed roles): `/wiki/doc/plan-app-wide-roles-and-storage` returns 200 with the plan H1 + nav, and the landing page lists it. The `require_gm` gate gets behavioral coverage in Arc A2 (campaign-create gating), where it becomes observable over HTTP. `tests/harness_ui/test_map_pan.py` (+2, v2.583.0, "The Unstuck Map") covers the tabletop map pan fix: a left-button drag over empty map area changes the `#map-transform` translate (the new cross-device pan gesture, added because right-button-only panning was eaten by the native context menu on macOS Safari / trackpads, leaving the map "stuck" while wheel-zoom kept working), and the wheel still zooms (guard against regressing the path that kept working). `tests/harness/test_admin_center.py` (+6) covers Phase 3b uploads (`docs/plans/admin-center-consolidation.md`) — the Center's campaign **map upload + activate** via the shared `uploads_data` volume: the `campaign_admin` `create_map`/`activate_map` round-trip (host-side sqlite — grid/dim clamping, first-map auto-activate, bad-grid fallback, cross-campaign reject); the upload + activate routes require auth (unauth → 303, parametrized) and are refused for basic-auth header callers (403/404, parametrized); and an MFA-on upload-a-tiny-PNG → listed → activate round-trip against a real campaign (skipped when MFA off). Phase 4 route-removal: **deleted** `test_admin_audit.py` (5) + `test_admin_user_audit_scrub.py` (5) + `test_admin_demo_reset.py` (2) + 3 in-app-mint tests from `test_demo_magic_link.py` — all exercised now-retired in-app `/admin` routes (user write surface v2.579.0; on-demand demo reset v2.580.0; demo magic-link mint v2.581.0); the moved behavior is covered Center-side in `test_admin_center.py`. `test_demo_magic_link.py`'s end-to-end happy path was **rewired** to mint container-side via the Admin Center (`_center_mint` — same SECRET_KEY → the token verifies at the app's `/demo-login`), exercising the real cross-service contract (Center mints → app redeems → replay 401); the mint/verify **unit** tests are unchanged. **Grew** `tests/harness/test_admin_routes_retired.py` (now +7): asserts each retired in-app route (`POST /admin/users`, `/disable`, `/reset_password`, `/delete`, `/scrub-audit-log`, `/admin/demo/reset`, `/admin/demo/mint-magic-link`) no longer succeeds (never 2xx/3xx — 404/405/401/403 only), i.e. no live duplicate write-path (`docs/plans/admin-center-consolidation.md` Phase 4). `tests/harness/test_admin_center.py` (+3) covers the Center's ported GDPR audit-log scrub (`POST /users/{id}/scrub-audit-log`, `docs/plans/admin-center-consolidation.md` Phase 4): requires auth (unauth → 303), refused for basic-auth header callers (403 gated / 404 off — never runs, so the shared log is untouched), and on an MFA-verified session a missing email → 400 + a never-logged-email scrub rewrites 0 lines with the JSON contract intact (safe no-op; skipped when MFA off). `tests/harness/test_admin_center.py` (+11) covers Phase 3b (no-upload subset) of `docs/plans/admin-center-consolidation.md` — the Center's MFA-gated campaign management: the `campaign_admin` member add/remove + system change + character create/assign/delete round-trip (host-side sqlite, `importorskip`, incl. idempotent add + wrong-campaign/unknown guards); all six management routes require auth (unauth → 303, parametrized); a representative subset (member-remove, character-delete, system) is refused for basic-auth header callers (403 gated / 404 off, parametrized); and a net-zero character create → assign → delete round-trip on a real campaign on an MFA-on stack (skipped when MFA off). `tests/harness/test_admin_center.py` (+6) covers Phase 3a of `docs/plans/admin-center-consolidation.md` — the Center's campaign-admin surface: the `campaign_admin` service list → detail → delete round-trip (host-side sqlite, `importorskip`, incl. unknown-id + re-delete raising); `/campaigns` auth-gated (unauth → 303), renders when `ADMIN_CENTER_ADMIN_TOOLS` is on + drills into the read-only detail (Overview/Members); an unknown campaign id redirects with an error (no 500); the MFA-gated delete requires auth (unauth → 303) and is refused for basic-auth header callers (403 gated / 404 off — never POSTed from a verified session, which would wipe a real demo campaign). `tests/harness/test_admin_center.py` (+6) covers Phase 2b of `docs/plans/admin-center-consolidation.md` — the MFA-gated destructive user ops: the disable/reset-password/delete routes require auth (unauth → 303, parametrized over all three), are refused for basic-auth header callers (403 gated / 404 when off — the MFA gate, since a header caller has no MFA-verified session), and a full disable → re-enable → reset-password → delete → re-delete round-trip on an MFA-on stack using a throwaway account (skipped when the stack has MFA off, since destructive ops are then always refused). `tests/harness/test_admin_center.py` (+8) covers Phase 2a of `docs/plans/admin-center-consolidation.md` — the opt-in `/users` user-admin page (read-only list + non-destructive create): the new `operator_audit` helper formats/appends operator-attributed audit lines (`actor=admin-center:<operator>`) that round-trip through the dashboard's own `audit_parse` (incl. the no-`AUDIT_LOG_PATH` path that must not raise); the `user_admin` service functions validate + reject duplicate/short-password + toggle-disable + delete (host-side in-memory sqlite, `importorskip`); and the live routes are auth-gated (unauth → 303), render when `ADMIN_CENTER_ADMIN_TOOLS` is on, reject a duplicate-email create (303 + `err=`), and require auth on create. `tests/harness/test_admin_center.py` (+4) covers the new opt-in `/tools` admin-tools page (Phase 1 of `docs/plans/admin-center-consolidation.md`): auth-gated (unauth → 303), renders when `ADMIN_CENTER_ADMIN_TOOLS` is on, the demo magic-link mint round-trips (303 + minted URL), and the destructive demo-reset is auth-gated (tested without ever firing the reseed). `tests/harness/test_wiki.py::test_wiki_doc_serves_admin_center_consolidation_plan` (+1) surfaces the new "Consolidate site-admin into the Admin Center" design plan. `tests/harness/test_admin_center.py` (+2) covers the new `/tests` admin-center dashboard: unauthenticated → 303 to /login (no basic-auth popup), and after session login the page renders the harness test-results dashboard (latest run or the empty-state). `tests/harness/test_homebrew_fork_srd.py` (→ 19) + `tests/harness_ui/test_homebrew_workshop.py` (→ 2) now also cover Phase 3: the `GET /api/campaign/{id}/srd_search` browse endpoint (finds shipped SRD by name, GM-gated, unknown-type 404) and the Workshop search→fork Playwright smoke (search "fireball" → Fork button → editor opens pre-filled). `tests/harness/test_homebrew_fork_srd.py` (→ 16) covers the fork / edit / revert / **list** endpoints (Phases 1–2 of `docs/plans/homebrew-fork-srd.md`): variant + override fork, GM-editor tweak (8d6→10d6) persisting with scope forced to campaign-N, the `/homebrew/custom` list (campaign's own records only, not shipped SRD), plus GM-gating + error paths. `tests/harness_ui/test_homebrew_workshop.py` (+1) is the Playwright smoke: GM opens Settings → Homebrew → Workshop, forks Fireball, the form editor pre-fills 8d6, the GM saves a 12d6 tweak, and it resolves server-side. `tests/harness/test_homebrew_fork_srd.py` (+9) covers the fork-SRD-as-homebrew endpoints (Phase 1 of `docs/plans/homebrew-fork-srd.md`): variant fork of an SRD spell (fresh slug, source:"custom", verbatim mechanics), override fork shadowing the SRD slug for the campaign only (no-campaign lookup still pristine SRD), 409 on double-override, type-generality (a monster), GM-gating (non-GM 403), unknown-slug/type/mode errors, and the revert (un-fork) delete + its 404. `tests/harness/test_srd_provenance.py` (+3) enforces the "SimpleVTT ships SRD 5.1 content only" rule: every shipped content record is `source:"srd"` + `scope:"global"` + SRD-attributed (the "only SRD" half), per-type counts meet a completeness floor so SRD mechanics can't silently shrink (the "all SRD present" half), and no homebrew-sourced record leaks into the shipped tree. `tests/harness/test_spell_catalog_concentration.py` (+2) now also gates the catalog `concentration` flag against each spell's duration in both directions (the v2.568.1 build-script fix that corrected 125 mis-flagged spells) + spot-checks fixed spells (Moonbeam, Bless, Fly, …). `tests/harness/test_aoe_enter_trigger.py` (+9) covers the persistent-AoE trigger (`docs/plans/aoe-enter-trigger.md`, Phases 1+3): an NPC moving into Spirit Guardians takes save-for-half damage; the trigger fires once per turn (out-and-back-in damages once); a move staying outside fires nothing; `override_barrier` skips it; the caster is immune to their own emanation; an NPC that *starts its turn* inside takes damage; an NPC *pushed in* via `/force_move` takes damage (forced-movement path); a PC moving in gets a WIS-save `roll_request`; and a *placed* sphere (Moonbeam) damages an NPC moving in (the no-save guard excludes Spike-Growth-style movement-damage AoEs). `tests/harness/test_fail2ban_discord_notify.py` (+7) covers the optional Discord webhook notify action (fail2ban Phase 4h): action file shape, ban/unban curl POSTs, the `${FAIL2BAN_DISCORD_*}` env placeholders + graceful no-op guard, and the render-script / compose / `.env.example` wiring. Recent UI tests: `tests/harness_ui/test_notes_crypto.py` (Phase 4b — browser PBKDF2+AES-GCM round-trip + full encrypt→store→fetch→decrypt, no plaintext at rest or on the wire) and `tests/harness_ui/test_notes_drawer.py` (Phase 5a GM prep-note CRUD; 5d a player writes/reloads-locked/unlocks a private note; 5b cross-context handout reveal — GM reveals → player sees it live over WS → GM hides → it disappears — zero console errors).

### `test_private_notes.py`
v2.557.0 — Notes & Handouts **Phase 4 (server side)** — E2E-encrypted private notes, [notes-and-handouts.md](../plans/notes-and-handouts.md). `note_encryption_keys` table (schema v74) + encryption-config endpoints + private-note ciphertext storage. Server tests use placeholder ciphertext (the server treats `enc_*` as opaque; real AES-GCM is the Playwright test). GM = `gm_client`; alice/bob = non-GM members.

| Test | What it asserts |
|------|-----------------|
| `test_set_and_get_encryption_config` | `GET /api/notes/encryption` → `configured:false` initially; after `PUT` → `configured:true` echoing salt/iterations/key_check. |
| `test_encryption_config_conflict` | A second `PUT` → 409 (set-once). |
| `test_encryption_missing_salt_400` / `test_encryption_low_iterations_400` | Validation: missing salt or iterations below the floor → 400. |
| `test_reset_wipes_key_and_notes` | `DELETE /api/notes/encryption` → `notes_wiped ≥ 1`, config back to `false`, the author's encrypted note gone. |
| `test_create_private_stores_ciphertext` | Private create → `is_encrypted:true`, empty title/body, `enc_*` echoed + round-trips byte-for-byte. |
| `test_private_rejects_plaintext` / `test_private_requires_ciphertext` | Private create with plaintext → 400; with no ciphertext → 400. |
| `test_gm_cannot_read_private_note` | **Headline:** a player's private note is absent from the GM's list + 404 by id. |
| `test_other_player_cannot_read_private` | Another player can't list/get it either (404). |
| `test_author_reads_own_private` | The author lists + GETs their own private note (ciphertext). |
| `test_private_note_ws_scoped_to_author` | A private note's `note_updated` reaches only the author's socket — not bob's, not the GM's. |
| `test_author_can_patch_private` / `test_patch_private_rejects_plaintext` | Author patches `enc_body`; patching plaintext on a private note → 400. |

### `test_player_notes.py`
v2.556.0 — Notes & Handouts **Phase 3** (player public notes), [notes-and-handouts.md](../plans/notes-and-handouts.md). Extends `/notes` to `kind=player_note` / `visibility=public` + the scoped `note_updated` WS broadcast. GM = `gm_client`; alice/bob = non-GM members.

| Test | What it asserts |
|------|-----------------|
| `test_player_creates_public_note` | Member POST `{visibility:"public"}` → 200, `kind == "player_note"`, `visibility == "public"`. |
| `test_public_note_visible_to_all` | A public note appears in the GM's list + another player's list + GET by id 200. |
| `test_author_can_edit_own_public` | The author PATCHes their own public note → 200. |
| `test_gm_can_moderate_player_public` | The GM may PATCH + DELETE a player's public note. |
| `test_non_author_player_cannot_edit` | A different player PATCHing another's public note → 403. |
| `test_non_author_player_cannot_delete` | A different player DELETEing another's public note → 403. |
| `test_author_can_delete_own` | The author deletes their own note → 200; GET → 404. |
| `test_private_not_available` | `visibility="private"` → 400 (deferred to Phase 4's encrypted client). |
| `test_invalid_visibility_400` | An unknown visibility → 400. |
| `test_public_note_create_broadcasts_ws` | Creating a public note broadcasts `note_updated` to the GM + other players. |
| `test_gm_note_ws_scoped_to_gms` | **Security:** a gm_note's `note_updated` reaches the GM socket but NOT a player's. |

### `test_handouts.py`
v2.555.0 — Notes & Handouts **Phase 2** (handouts), [notes-and-handouts.md](../plans/notes-and-handouts.md). `handouts` table (schema v73) + CRUD + `/reveal` (the first `handout_revealed` WS broadcast). GM = `gm_client`; alice owns the Rogue (Pip Quickfingers), bob the Wizard (Thalindra Moonwhisper) — roster `owner_user_id` resolves their user_ids.

| Test | What it asserts |
|------|-----------------|
| `test_create_handout_unrevealed` | GM POST → 200, `revealed == false`, `reveal_to == []`. |
| `test_gm_list_includes_handout` | GM list includes the created handout. |
| `test_patch_handout` | PATCH updates title + image_url. |
| `test_reveal_all_visible_to_player` | Before reveal a player can't see it (list excl. + 404); after `reveal {to:"all"}` the player sees it in list + by id. |
| `test_unrevealed_hidden_from_player` | An un-revealed handout is absent from a player's list + 404 by id. |
| `test_reveal_to_specific_player_scopes_visibility` | Revealed to alice only → alice sees it (HTTP), bob's list excludes it + bob GET → 404. |
| `test_reveal_to_specific_player_ws_scoping` | **Security core:** reveal-to-alice delivers `handout_revealed` (with title) to alice's WS, and bob's WS receives nothing. |
| `test_reveal_all_ws_reaches_everyone` | Reveal-to-all delivers `handout_revealed` to both alice's + bob's WS. |
| `test_delete_handout` | DELETE → 200; subsequent GET → 404. |
| `test_player_cannot_create_handout` | Non-GM POST → 403. |
| `test_create_requires_title` | Missing title → 400. |
| `test_reveal_unknown_handout_404` | Reveal a nonexistent handout → 404. |
| `test_reveal_bad_to_400` | `reveal {to: 5}` (not "all"/list) → 400. |
| `test_upload_handout_image` | GM `POST …/handouts/upload_image` (PNG) → 200 + a `/static/uploads/handouts/…png` URL. |
| `test_upload_handout_image_player_403` | A non-GM member uploading → 403. |
| `test_upload_handout_image_bad_ext_400` | A non-image extension → 400. |

### `test_notes.py`
v2.554.0 — Notes & Handouts **Phase 1** (GM prep notes), [notes-and-handouts.md](../plans/notes-and-handouts.md). New `notes_routes.py` + `campaign_notes` table (schema v72). GM = `gm_client`; non-GM member = `alice_client`.

| Test | What it asserts |
|------|-----------------|
| `test_create_and_get_note` | GM POST → 200, `kind == "gm_note"`, `visibility == "gm_only"`, title/body echoed, `is_encrypted == false`; GET by id round-trips. |
| `test_list_orders_pinned_first` | List returns the campaign's gm_notes with pinned ones first. |
| `test_patch_note` | PATCH updates title + pinned; omitted `body` unchanged. |
| `test_delete_note` | DELETE → 200 `deleted`; subsequent GET → 404. |
| `test_create_requires_title_or_body` | Empty title + body → 400. |
| `test_get_unknown_note_404` | Unknown note id → 404. |
| `test_player_cannot_create_note` | **Access control:** non-GM member POST → 403. |
| `test_player_list_excludes_gm_notes` | **Access control:** a gm_note never appears in a non-GM's list. |
| `test_player_cannot_get_gm_note` | **Access control:** non-GM GET of a gm_note id → 404 (not a leak). |
| `test_player_cannot_delete_gm_note` | **Access control:** non-GM DELETE of a gm_note → 404. |
**Runner:** `python3 -m pytest tests/harness/ -q` from the repo root. The harness expects the demo app to be reachable at `http://localhost:8013` (Docker Compose).

> **Spell-validation suite marker (Phase 5, v2.183.23).** The 260-test spell-validation suite (the `test_spell_*` catalog iterators + the `test_cast_*` per-spell deep-dives + `test_ac_buff_spells.py`) carries the `spell_catalog` marker, auto-applied by filename in `tests/harness/conftest.py`. Run just that suite with `python3 -m pytest tests/harness/ -m spell_catalog`. The dedicated `spell-catalog` job in `.github/workflows/test-harness.yml` is its CI gate (runs serially — the shared single-stack harness precludes safe pytest-xdist; see [the plan](plans/spell-validation-suite.md) Phase 5).

> **⚠️ Run against a FRESH DB — not a long-lived shared container.** The harness talks to one shared Docker app + Postgres over HTTP/WS. Many tests PATCH demo character sheets (subclass / level / abilities / resources / HP) and seed in-memory battle state; fixtures restore on teardown, but a long *serial* run of the **whole** suite accumulates residual state in the shared DB (a stripped resource here, a leftover battle there). Running all ~1900 tests as a single serial batch against a stale container can therefore surface **~150+ false failures from cross-test contention, not code regressions** — verified when those same tests pass after `docker compose restart app` (which re-runs `reset_and_reseed`) or in smaller batches. **CI is the authoritative full-suite gate** (`.github/workflows/test-harness.yml` runs against a fresh container per push). Locally: run per-file / per-feature batches, and `docker compose restart app` to reseed before a clean run. If a full-suite run shows a wall of failures, reseed and re-check a sample in isolation before assuming a regression.
**Fixtures:** `gm_client`, `alice_client`, `bob_client` (httpx async clients), `roster` (skinny char list), `gm_ws` / `alice_ws` / `bob_ws` (WebSocket collectors). Per-test character fixtures (e.g. `krieger_full`, `tavik_rested`, `garrik_fresh`) long-rest + reset state so each test starts from a known baseline.

---

## Categories

- [Smoke & infrastructure](#smoke--infrastructure)
- [Generic rolls + roll requests](#generic-rolls--roll-requests)
- [Weapon attacks](#weapon-attacks)
- [Spell casting](#spell-casting)
- [Class features](#class-features)
- [Items](#items)
- [HP & death-save state machine](#hp--death-save-state-machine)
- [Buffs & concentration](#buffs--concentration)
- [Tabletop operations](#tabletop-operations)

---

## Smoke & infrastructure

### `test_smoke.py`
Sanity checks that the harness can even talk to the demo app.

| Test | What it asserts |
|------|-----------------|
| `test_healthz` | `GET /healthz` → 200, JSON `{ok, app_version, schema_version}`. |
| `test_version` | `GET /version` → 200, matches `app/version.py`. |
| `test_roster_fixture` | The `roster` fixture loads and contains all 12 demo PCs by name. |
| `test_gm_can_open_ws` | `WS /ws/campaign/1` as GM accepts connection + emits an opening `state` message. |

### `test_frenzy_exhaustion.py`
v2.159.21 exhaustion-levels Phase 4 — Berserker Frenzy rage-end retrofit. Closes the v2.99.226 filed TODO + Phase E.8 of `class-content-status.md`. `/use_frenzy` stamps `sheet._frenzied_this_rage: True`; `/end_buff` with `key="rage"` detects the flag, bumps `sheet.exhaustion_level` by 1 (level 6 → death), clears the flag, mirrors to combatant, broadcasts `exhaustion_update` with source="frenzy_rage_end".

| Test | What it asserts |
|------|-----------------|
| `test_frenzy_then_end_rage_bumps_exhaustion` | /use_rage → /use_frenzy → /end_buff(rage) → exhaustion 0 → 1; `_frenzied_this_rage` flag cleared. |
| `test_end_rage_without_frenzy_no_exhaustion` | /use_rage without frenzy → /end_buff(rage) → exhaustion stays 0. |
| `test_subsequent_rage_without_frenzy_no_exhaustion` | First rage frenzied → +1; second rage NOT frenzied → +0 (flag-cleanup regression). |
| `test_frenzy_at_lv5_end_rage_kills` | Exhaustion=5 + rage + frenzy + end → level 6, death_saves.status="dead" (routes through `_set_death_save_state`). |

### `test_exhaustion_hp_max.py`
v2.159.20 exhaustion-levels Phase 3b — HP-max halving at Lv 4. Mirrors v2.97.42 Aid max-HP plumbing in reverse: `_apply_heal_to_combatant` halves `effective_max` when `exhaustion_level >= 4`, and `/set_exhaustion` clamps current HP down to `floor(max/2)` on the transition from `< 4` to `>= 4`. Going BACK below 4 does NOT auto-restore HP (RAW). The base `hp.max` field is NEVER mutated.

| Test | What it asserts |
|------|-----------------|
| `test_pc_set_lv4_clamps_current_hp_when_above_ceiling` | Pip at full HP → /set_exhaustion level=4 → current drops to floor(max/2). `hp.max` is unchanged. |
| `test_pc_set_lv4_at_low_hp_unchanged` | Pip at HP=1 → /set_exhaustion level=4 → current stays at 1 (already below the new ceiling). |
| `test_pc_lv4_to_lv3_does_not_restore_hp` | Pip at Lv 4 (HP clamped) → /set_exhaustion level=3 → current HP stays at the clamped value. RAW: player has to heal up. |
| `test_pc_set_lv3_does_not_clamp_hp` | Lv 3 → no HP touch (regression that the Lv 4 clamp doesn't fire prematurely). |

### `test_carry_weight.py`
v2.159.27 carrying-capacity Phase 1 (see [carrying-capacity.md](../plans/carrying-capacity.md)) — pure-Python unit tests against the leaf `app.content.carry_weight` module, plus 1 integration test against `/sheet-json`. RAW PHB p.176: carry capacity = `STR × 15 lb`. The leaf module exposes a defensive weight-string parser, a 3-tier item-weight resolver, STR-aware capacity, an over-capacity boolean, and a bundled summary helper that `/sheet-json` calls into.

| Test | What it asserts |
|------|-----------------|
| `test_parse_weight_*` (11 tests) | Parser handles `""`/`"3 lb."`/`"3 lb. lb"` SRD typo/`"1/2 lb."` fraction/`"2.5 lb."` decimal/`"-5 lb."` clamped/junk/non-string defensive — all map to a non-negative float. |
| `test_item_weight_lb_tier*` (5 tests) | 3-tier priority: direct override `weight_lb` wins, then item's `weight` string, then catalog fallback string, then 0.0. Non-dict input defensive. |
| `test_carry_capacity_*` (7 tests) | STR 10 → 150; STR 16 → 240; STR 20 → 300; STR 0 clamps to 1 (→ 15); missing abilities defaults to 10; nested `{"score": 14}` → 210; flat `sheet.str` → 270; uppercase `abilities.STR` key (the dnd5e demo seed's shape) → correct. |
| `test_inventory_weight_*` (7 tests) | Empty inventory → 0; single item; qty multiplies; qty default 1; sum across items; catalog fallback used when no inline weight; `_in_bag_of_holding: True` items skipped. |
| `test_is_over_capacity_*` (3 tests) | Under cap → False; over cap → True; exactly at cap → False (RAW inclusive). |
| `test_carry_summary_*` (2 tests) | Bundled summary returns the 3 fields in the right shape; over-capacity flag propagates. |
| `test_sheet_json_exposes_derived_carry` | Integration: `GET /sheet-json` for Krieger returns `derived.carry.{carry_capacity_lb, inventory_weight_lb, is_over_capacity}`; cap ≥ 240 (STR 18 Barbarian). |

### `test_exhaustion_speed.py`
v2.159.19 exhaustion-levels Phase 3a — pure-Python unit tests against the leaf `effective_speed_walk` helper. RAW PHB Appendix A: Lv 2 halves speed; Lv 5 floors to 0. Applied AFTER the existing buff `(base + bonus) × mult − reduction` math so Lv 2 composes cleanly with Slow / Lance of Lethargy / Longstrider / Haste. The route layer mirrors `sheet.exhaustion_level` → `combatant.exhaustion_level` so the leaf helper has no DB dependency.

| Test | What it asserts |
|------|-----------------|
| `test_no_exhaustion_no_penalty` | Lv 0 base 30 → 30 (regression). |
| `test_lv_1_no_penalty` | Lv 1 only affects ability checks; speed unchanged. |
| `test_lv_2_halves_speed` | Lv 2: 30 → 15. |
| `test_lv_3_still_halved` | Lv 3 (cumulatively still has Lv 2's halving) → base 40 → 20. |
| `test_lv_4_still_halved` | Lv 4: 30 → 15 (HP-max halving is Lv 4, speed is NOT halved a second time). |
| `test_lv_5_floors_to_zero` | Lv 5: 30 → 0. |
| `test_lv_5_with_haste_still_zero` | Lv 5 hard floor: Haste's ×2 multiplier can't restore speed. |
| `test_lv_2_composes_with_speed_reduction_buff` | Lv 2 + Slow (-10): (30 - 10) // 2 = 10. |
| `test_lv_2_composes_with_speed_bonus_buff` | Lv 2 + Longstrider (+10): (30 + 10) // 2 = 20. |
| `test_lv_6_is_zero` | Lv 6 = 0 (death state; helper just returns 0). |
| `test_malformed_exhaustion_level_defaults_to_zero` | Non-int level (string / None) → treated as 0. |

### `test_exhaustion_disadvantage.py`
v2.159.18 exhaustion-levels Phase 2 — disadvantage wiring at Lv 1 (ability checks) + Lv 3 (attacks + saves). Composes with the existing v2.152.0-v2.157.0 condition-disadvantage helpers via the new `_exhaustion_level(sheet_or_combatant)` helper. The five extended helpers return a synthetic key (`"exhaustion-1"` or `"exhaustion-3"`) so the existing label plumbing at the call sites just works.

| Test | What it asserts |
|------|-----------------|
| `test_exhaustion_lv1_imposes_check_disadvantage` | Pip at level=1 + STR check via /roll → 2d20kl1 in breakdown, `roll_state_applied == "auto_disadvantage_exhaustion-1"`. |
| `test_exhaustion_lv2_does_not_impose_attack_disadvantage` | Cumulative-floor regression. Pip at level=2 + WIS save → does NOT carry `auto_disadvantage_exhaustion-3` (Lv 3 effects aren't active yet). |
| `test_exhaustion_lv3_imposes_save_disadvantage` | Lv 3 imposes ALL save disadvantage (not just DEX-gated like Restrained). WIS save → 2d20kl1, `roll_state_applied == "auto_disadvantage_exhaustion-3"`. |
| `test_exhaustion_lv0_no_disadvantage` | Regression. At level=0 the helpers must NOT fire any exhaustion label. |
| `test_exhaustion_lv3_npc_imposes_check_disadvantage` | NPC mirror path — set exhaustion via `combatant_id` + skip_roll_state + /roll → response carries an exhaustion label. |

### `test_use_legendary_action.py`
v2.159.34 legendary-actions Phase 1b + v2.161.0 Phase 1c (see [legendary-actions.md](../plans/legendary-actions.md)) — budget gate + spend endpoint `POST /api/campaign/{cid}/use_legendary_action`. RAW DMG p.11: 3 legendary-action points per round, spent at the END of another creature's turn (never the legendary creature's own), refreshed at the START of the legendary creature's turn. Phase 1b is the budget gate; Phase 1c (v2.161.0) chains server-side save-AoE damage dispatch — when the spent action carries a `save_ability` + `damage` and the caller passes `aoe_target_combatant_ids`, the server resolves the action def from the monster template, rolls each target's save, and applies save-or-take damage, broadcasting `legendary_action_aoe_resolved`.

| Test | What it asserts |
|------|-----------------|
| `test_use_legendary_action_cost_1_spends_one_point` | Tail Attack (cost 1) → 200; pool 3 → 2; `legendary_action_pool_update(reason=spent, cost=1)` + `feature_used(source=legendary-action)` broadcasts. |
| `test_use_legendary_action_cost_2_spends_two_points` | Wing Attack (cost 2) → pool 3 → 1 (multi-cost spend path). |
| `test_use_legendary_action_blocked_on_own_turn` | Dragon is the active combatant → 409 `cannot_use_on_own_turn`. |
| `test_use_legendary_action_blocked_when_pool_empty` | 3 × cost-1 spends drain the pool; 4th attempt → 409 `insufficient_legendary_action_points` with `current == 0`. |
| `test_turn_start_refreshes_legendary_action_pool` | Spend to 1, advance turn back to the dragon → pool resets to 3; broadcast carries `reason=turn_start_refresh`. |
| `test_use_legendary_action_missing_combatant_id_400` | Missing `combatant_id` → 400. |
| `test_use_legendary_action_player_caller_403` | Non-GM caller → 403 (NPC legendary actions are GM-authorised). |
| `test_wing_attack_aoe_resolves_saves_and_damage` | Phase 1c. Adult Red Dragon spends Wing Attack (cost 2) with `aoe_target_combatant_ids`; server rolls each NPC target's DEX save (DC 22), applies save-or-take 2d6+8 bludgeoning; spender excluded; `damage_dealt > 0` iff `passed is False`; `legendary_action_aoe_resolved` broadcast carries save_ability=DEX, save_dc=22, damage_type=bludgeoning, 2 results. |
| `test_wing_attack_without_targets_skips_dispatch` | Phase 1c. Wing Attack with no `aoe_target_combatant_ids` → pool still spent, `aoe_results == []` (dispatch is opt-in via targets). |
| `test_tail_attack_reference_resolves_attack_and_damage` | Phase 1c. Adult Red Dragon spends Tail Attack (cost 1) with a single `target_combatant_id`; server resolves the base "Tail" action (+14 / 2d8+8), rolls 2d20kh1+14 vs the bandit's AC, applies (crit-doubled) damage on a hit; `attack_result.base_action_name == "Tail"`, hit-consistency (damage>0 iff hit), `feature_used(source=legendary-action-attack)` broadcast. |
| `test_tail_attack_without_target_skips_attack_dispatch` | Phase 1c. Tail Attack with no `target_combatant_id` → pool still spent, `attack_result is None` (reference-attack dispatch is opt-in via target). |

### `test_spend_legendary_resistance.py`
v2.165.0 legendary-actions Phase 2a (see [legendary-actions.md](../plans/legendary-actions.md)) — the per-day legendary-resistance pool. `POST /api/campaign/{cid}/spend_legendary_resistance` lets a legendary creature spend one resistance to turn a failed save into a success (RAW MM p.11). The pool's `max` seeds from the stat block — `_monster_dict_to_sheet` derives `legendary_resistance_per_day` from the "Legendary Resistance (N/Day)" special ability (Adult Red Dragon → 3). Decrements + broadcasts `legendary_resistance_spent`.

| Test | What it asserts |
|------|-----------------|
| `test_spend_legendary_resistance_decrements_pool` | Adult Red Dragon first spend → 200; pool 3 → 2; `legendary_resistance_spent(reason=spent)` broadcast carries max=3, current=2, combatant_name. |
| `test_spend_legendary_resistance_drains_to_zero_then_409` | 3 spends drain 3 → 2 → 1 → 0; 4th attempt → 409 `insufficient_legendary_resistance` with current=0, max=3. |
| `test_spend_legendary_resistance_non_legendary_409` | A Bandit (no Legendary Resistance special ability, max 0) → 409 `no_legendary_resistance`. |
| `test_spend_legendary_resistance_unknown_combatant_404` | combatant id not in the active battle → 404. |
| `test_spend_legendary_resistance_missing_combatant_id_400` | Missing `combatant_id` → 400. |
| `test_spend_legendary_resistance_player_caller_403` | Non-GM caller → 403 (legendary resistance is GM-authorised). |

### `test_legendary_resistance_prompt.py`
v2.166.0 legendary-actions Phase 2b (see [legendary-actions.md](../plans/legendary-actions.md)) — the failed-save auto-prompt. When an NPC with a resistance charge left fails a feature save that would impose a condition, `_resolve_feature_save` defers the install and broadcasts `legendary_resistance_prompt`. Spending (`/spend_legendary_resistance` with a `prompt_id`) flips the save to a success; declining (`/decline_legendary_resistance`) installs the held condition. Trigger: Battle Master Menacing Attack (DC 16 WIS → Frightened) at an Adult Red Dragon, fail-until-prompt loop.

| Test | What it asserts |
|------|-----------------|
| `test_failed_save_defers_then_spend_flips_to_success` | A failed dragon WIS save defers: `legendary_resistance_prompt` fires (combatant, WIS, DC 16, frightened, current=3, max=3), nothing installs while pending; spend with `prompt_id` → 200 (resolution=spent, pool 3 → 2), `legendary_resistance_resolved(passed=True, condition_installed=False)`, still no Frightened, replay 404. |
| `test_failed_save_decline_installs_held_condition` | Declining the prompt → 200 (resolution=declined, condition_installed=True, frightened); `legendary_resistance_resolved(passed=False, condition_installed=True)`; the dragon now carries Frightened (source_char_id = Garrik); replay 404. |
| `test_spend_unknown_prompt_404` | `/spend_legendary_resistance` with an unknown `prompt_id` → 404. |
| `test_decline_unknown_prompt_404` | `/decline_legendary_resistance` with an unknown `prompt_id` → 404. |
| `test_decline_missing_prompt_id_400` | `/decline_legendary_resistance` with no `prompt_id` → 400. |
| `test_decline_player_caller_403` | Non-GM caller → 403 (legendary resistance is GM-authorised). |

### `test_lair_actions.py`
v2.168.0 legendary-actions Phase 3a + v2.171.0 chromatic backfill (see [legendary-actions.md](../plans/legendary-actions.md)) — pure-Python unit tests against the `app.content.lair_actions` leaf module. Curated RAW lair-action data (all five chromatic dragons' lairs) folded onto the projected monster sheet by `_monster_dict_to_sheet`. No HTTP fixtures.

| Test | What it asserts |
|------|-----------------|
| `test_adult_red_dragon_has_three_lair_actions` | `lair_actions_for_slug("adult-red-dragon")` → 3 actions: magma-erupts, tremor, volcanic-gases. |
| `test_magma_erupts_is_a_dex_save_aoe` | Magma Erupts: DEX, DC 15, 6d6 fire, half_on_save=True, sphere 20 ft. |
| `test_tremor_is_a_non_damage_prone_effect` | Tremor: DEX DC 15, no damage, effect="prone", 60-ft radius. |
| `test_volcanic_gases_is_a_con_save_poison` | Volcanic Gases: CON DC 13, effect="poisoned", no damage. |
| `test_ancient_red_dragon_shares_the_volcanic_lair` | Adult + ancient red dragon resolve to the identical action set (lair tied to the lair, not the age). |
| `test_unknown_slug_returns_empty_list` | A monster with no authored lair (bandit) + a typo'd slug → `[]`. |
| `test_blank_or_non_string_slug_returns_empty_list` | `""`, `None`, and an int slug → `[]`. |
| `test_slug_lookup_is_case_and_whitespace_insensitive` | `"  Adult-Red-Dragon  "` → 3 actions. |
| `test_returned_list_is_a_deep_copy` | Mutating the returned list/dicts doesn't corrupt the module-level source. |
| `test_lair_action_by_id_resolves_known_action` | `lair_action_by_id("adult-red-dragon", "magma-erupts")` → the Magma Erupts dict. |
| `test_lair_action_by_id_unknown_id_returns_none` / `test_lair_action_by_id_unknown_slug_returns_none` / `test_lair_action_by_id_blank_id_returns_none` | Unknown id, unknown slug, and blank/None id → `None`. |
| `test_all_ten_chromatic_slugs_are_keyed` | adult + ancient × black/blue/green/red/white = 10 slugs keyed, each 3 actions. |
| `test_each_chromatic_color_shares_adult_and_ancient` | Per color, adult + ancient resolve to identical action lists. |
| `test_black_swamp_lair_shape` | Black: grasping-tide (STR prone), swarming-insects (CON 3d6 piercing half), magical-darkness (descriptive: empty save/damage/effect). |
| `test_blue_desert_lair_shape` | Blue: sand-cloud (CON blinded), lightning-arc (3d6 lightning, half_on_save=False). |
| `test_green_forest_lair_shape` | Green: grasping-roots (STR restrained), magical-fog (WIS charmed), wall-of-tangled-brush (4d8, half). |
| `test_white_arctic_lair_shape` | White: freezing-fog (CON DC 10, 3d6 cold), jagged-ice + ice-wall descriptive (empty save/damage/effect). |

### `test_regional_effects.py`
v2.178.0 legendary-actions regional effects (see [legendary-actions.md](../plans/legendary-actions.md)) — pure-Python unit tests against the `app.content.regional_effects` leaf module. RAW MM p.11 passive zone-wide regional effects (flavor-only `{id, name, desc}` entries, distinct from initiative-20 lair actions) for all five chromatic dragons, folded onto the projected monster sheet as `regional_effects`. No HTTP fixtures.

| Test | What it asserts |
|------|-----------------|
| `test_adult_red_dragon_has_three_regional_effects` | `regional_effects_for_slug("adult-red-dragon")` → 3 effects: minor-earthquakes, fouled-water, fire-portals. |
| `test_every_effect_has_id_name_desc` | Every effect dict carries non-empty id/name/desc. |
| `test_ancient_red_dragon_shares_the_volcanic_region` | Adult + ancient red dragon resolve to the identical effect set (region tied to the lair, not the age). |
| `test_unknown_slug_returns_empty_list` | A non-lair slug (bandit) + a typo'd slug → `[]`. |
| `test_blank_or_non_string_slug_returns_empty_list` | `""`, `None`, and an int slug → `[]`. |
| `test_slug_lookup_is_case_and_whitespace_insensitive` | `"  Adult-Red-Dragon  "` → 3 effects. |
| `test_returned_list_is_a_deep_copy` | Mutating the returned list/dicts doesn't corrupt the module-level source. |
| `test_all_ten_chromatic_slugs_are_keyed` | adult + ancient × black/blue/green/red/white = 10 slugs keyed, each 3 effects. |
| `test_each_chromatic_color_shares_adult_and_ancient` | Per color, adult + ancient resolve to identical effect lists. |
| `test_black_swamp_region_shape` / `test_blue_desert_region_shape` / `test_green_forest_region_shape` / `test_white_arctic_region_shape` | Each color's three effect ids match the curated RAW set. |

### `test_set_regional_fade.py`
v2.181.0 legendary-actions regional-effect fade tracker (see [legendary-actions.md](../plans/legendary-actions.md)) — RAW MM p.11: when a lair-dwelling creature dies its regional effects "fade over the course of 1d10 days." GM-only `POST /set_regional_fade` with a `start`/`advance`/`clear` action discriminator drives a `regional_fade` {days_total, days_remaining, faded, lair_slug} countdown on the battle state, broadcasting `regional_fade_changed`. HTTP + WS.

| Test | What it asserts |
|------|-----------------|
| `test_start_rolls_1d10_and_broadcasts` | `start` rolls `days_total` in 1–10, seeds `days_remaining == days_total` + `faded=False`, broadcasts `regional_fade_changed`, persists onto the battle-state dict (verified via GET /battle). |
| `test_start_defaults_lair_slug_from_battle` | `start` with no `lair_slug` in the body falls back to the battle's `lair_slug`. |
| `test_advance_ticks_days_down` | `advance` decrements `days_remaining` by 1, preserves `days_total`, keeps `faded=False` while days remain. |
| `test_advance_to_zero_marks_faded` | `advance` from `days_remaining=1` lands at 0 + flips `faded=True`; the `regional_fade_changed` broadcast carries `faded=True`. |
| `test_advance_with_no_fade_409` | `advance` with no active tracker → `409 no_active_fade`. |
| `test_clear_removes_tracker` | `clear` sets `regional_fade=None` + broadcasts the cleared tracker. |
| `test_unknown_action_400` | An unrecognized `action` → 400. |
| `test_player_403` | Non-GM caller → 403. |

### `test_trigger_lair_action.py`
v2.169.0 legendary-actions Phase 3b (see [legendary-actions.md](../plans/legendary-actions.md)) — the lair-action engine. Two GM endpoints: `POST /set_in_lair` toggles the battle's `in_lair` flag + records `lair_slug`; `POST /trigger_lair_action` resolves a lair action against the GM-picked caught targets, reusing the legendary save-AoE dispatch (`_resolve_feature_save` → roll → `_apply_damage_to_combatant`). NPC targets resolve inline; PC targets get a roll-request prompt. HTTP + WS.

| Test | What it asserts |
|------|-----------------|
| `test_set_in_lair_toggles_flag_and_broadcasts` | `set_in_lair` sets `in_lair`+`lair_slug`, broadcasts `in_lair_changed`, persists onto the battle-state dict (verified via GET /battle). |
| `test_set_in_lair_false_clears_slug` | `in_lair: false` blanks `lair_slug` to `""`. |
| `test_set_in_lair_requires_slug_400` | `in_lair: true` with no `lair_slug` → 400. |
| `test_set_in_lair_player_403` | Non-GM caller → 403. |
| `test_trigger_magma_erupts_damage_save_for_half` | Magma Erupts (DEX DC 15, 6d6 fire, half): two bandit NPCs resolve DEX saves inline, failed saves take damage; `lair_action_resolved` carries DEX/15/6d6/fire/half_on_save=True + 2 results. |
| `test_trigger_tremor_installs_prone_on_fail` | Tremor (DEX DC 15, no damage, prone): `damage_dealt == 0`; failed save → `condition_installed`; broadcast `effect=prone`, `damage=""`, `half_on_save=False`. |
| `test_trigger_sand_cloud_installs_blinded_on_fail` | v2.171.0 — Blue Dragon Sand Cloud (CON DC 15, no damage, blinded): failed save → `condition_installed`; broadcast `effect=blinded`, `damage=""`. Exercises the new `blinded` condition template. |
| `test_once_per_round_blocks_second_action` | v2.173.0 — RAW MM p.11: one lair action per round. A second action (even a different one) in the same round → `409 lair_already_acted_this_round`; first trigger parks `lair_acted_round=1`. |
| `test_once_per_round_override_succeeds` | `override: true` bypasses the once-per-round gate → 200. |
| `test_next_round_frees_lair_action` | Pre-seed round=2 / `lair_acted_round=1`; a fresh action in the new round → 200, `lair_acted_round=2` (one per round, not one per battle). |
| `test_no_repeat_same_action_next_round_409` | v2.172.0 — same action two rounds in a row → `409 lair_action_repeated`. Pre-seeded round=2 / `lair_acted_round=1` so only the no-repeat gate fires. |
| `test_no_repeat_override_succeeds` | `override: true` bypasses the no-repeat guard → 200. |
| `test_set_in_lair_clears_lair_memory` | `set_in_lair` resets both `last_lair_action_id` (→ "") and `lair_acted_round` (→ `None`), carried in `in_lair_changed`; the previously-used action fires cleanly afterward. |
| `test_trigger_lair_action_not_in_lair_409` | `in_lair` False → 409 `not_in_lair`. |
| `test_trigger_lair_action_unknown_action_409` | Bad `action_id` → 409 `unknown_lair_action`. |
| `test_trigger_lair_action_missing_action_id_400` | Missing `action_id` → 400. |
| `test_trigger_lair_action_player_403` | Non-GM caller → 403. |
| `test_lair_action_resolved_carries_owner_name` | v2.177.0 — the `lair_action_resolved` broadcast + JSON response carry `owner_name` (resolved from the combatant whose `lair_slug` matches the battle's lair) so the roll-log card is self-contained on reload. |

### `test_lair_init_20.py`
v2.175.0 legendary-actions (see [legendary-actions.md](../plans/legendary-actions.md)) — server-authoritative initiative-count-20 prompt. RAW MM p.11: lair actions fire on initiative count 20. When a `PUT /battle` lands the turn order in the init-20 zone (active combatant initiative ≤ 20, or every combatant above 20) and the lair is active + hasn't already acted / broadcast this round, the server fires a `lair_init_20_reached` WS broadcast carrying `{lair_slug, owner_name, round}`. Deduped per round via a `lair_init20_broadcast_round` marker parked on the battle state (carried forward across PUTs that omit it). Tests drive `PUT /battle` directly with manual NPC combatants carrying `lair_actions`.

| Test | What it asserts |
|------|-----------------|
| `test_init_20_broadcast_when_active_at_or_below_20` | Active combatant at init 20 (≤ 20) + in_lair → server broadcasts `lair_init_20_reached` carrying `lair_slug`, `owner_name` ("Ancient Red Dragon"), `round`. |
| `test_no_broadcast_when_active_above_20` | Active combatant at init 25 (> 20) with a sub-20 combatant present → count 20 not yet reached → no broadcast. |
| `test_all_combatants_above_20_broadcasts` | Every combatant above 20 → init count 20 falls after the last turn → broadcasts regardless of turn_index. |
| `test_no_broadcast_out_of_lair` | `in_lair` False → no init-20 prompt even at init 20. |
| `test_deduped_within_same_round` | A second PUT in the same round (still in the init-20 zone, omitting the dedup marker so carry-forward restores it) does NOT re-broadcast. |
| `test_next_round_rebroadcasts` | A new round re-arms the prompt — dedup is per-round, so round 2 broadcasts again. |
| `test_no_broadcast_when_already_acted_this_round` | `lair_acted_round == round` → the init-20 prompt is suppressed (already moot). |

### `test_monster_legendary_action_cost.py`
v2.159.33 legendary-actions Phase 1a (see [legendary-actions.md](../plans/legendary-actions.md)) — pure-Python data-invariant guard: every SRD legendary action whose name carries a `(Costs N Actions)` suffix has its `cost` integer set to N (not the default 1). Walks the shipped `app/data/local/dnd5e/monsters/*.json` content layer directly. Phase 1a backfilled 39 cost integers across 30 monsters from the suffix; this test guards the invariant against future SRD-rebuild drift so the Phase 1b `/use_legendary_action` budget gate doesn't silently re-break.

| Test | What it asserts |
|------|-----------------|
| `test_every_costs_n_legendary_action_has_matching_cost_integer` | Sweep all monster JSONs; no legendary action with a "(Costs N Actions)" suffix may carry `cost != N`. |
| `test_ancient_red_dragon_wing_attack_costs_2` | Spot-check canonical Ancient Red Dragon Wing Attack `cost == 2`. |
| `test_lich_disrupt_life_costs_3` | Spot-check Lich Disrupt Life `cost == 3` (the highest cost in SRD). |
| `test_legendary_action_costs_in_valid_range` | Every legendary action's `cost` ∈ {1, 2, 3}. RAW SRD 5.1 only uses 1/2/3. |

### `test_bag_of_holding.py`
v2.159.30 carrying-capacity Phase 3 (CLOSES the plan) — Bag of Holding (RAW DMG p.153, uncommon, no attunement). The bag weighs 15 lb regardless of contents; items "inside" don't count against the wielder's carry capacity. The v2.159.27 leaf module's `sheet_inventory_weight_lb` already skips items flagged `_in_bag_of_holding: True`; this commit lands the catalog row + demo seed + assertive test. Brakka Wildmane's Explorer's pack (59 lb) is tagged `_in_bag_of_holding: True` so it contributes 0 lb.

| Test | What it asserts |
|------|-----------------|
| `test_brakka_bag_of_holding_discounts_pack_weight` | `/sheet-json` for Brakka returns `derived.carry.inventory_weight_lb == 30` (7 greataxe + 8 javelins + 15 bag, NOT 89 with Explorer's pack counted), `carry_capacity_lb == 255` (STR 17 × 15), `is_over_capacity == False`. Catches a regression in the substrate's `_in_bag_of_holding` skip. |

### `test_bag_of_devouring.py`
v2.183.24 — Bag of Devouring (RAW DMG p.153, very rare). Catalog-only counterpart to the Bag of Holding: a descriptive, GM-adjudicated row with no automation wiring. Its cursed mechanics (creature-swallow on reach-in, daily extraplanar ejection, destruction-on-tear) are an explicit v1 NON-GOAL of the magic-items-automation framework (`docs/plans/magic-items-automation.md` lines 162-167), so they stay narration. Pins the load-bearing contrast: the carry-weight discount is `_in_bag_of_holding`-specific — a Bag of Devouring grants none.

| Test | What it asserts |
|------|-----------------|
| `test_bag_of_devouring_serves_as_catalog_only_item` | `GET /api/content/items/bag-of-devouring` → 200; record is `rarity: "very rare"`, `attunement: False`, and catalog-only (`charges`/`charge_recovery` null, `passives == []`, `actions == []`). |
| `test_bag_of_devouring_grants_no_carry_discount` | Pure-Python against `sheet_inventory_weight_lb`: an item flagged `_in_bag_of_devouring: True` still counts its full weight (7 + 59 = 66 lb); the SAME item under `_in_bag_of_holding: True` IS discounted (7 lb). Catches a spurious `_in_bag_of_devouring` skip leaking into the carry engine. |

### `test_goggles_of_night.py`
v2.159.25 magic-items follow-up — Goggles of Night (RAW DMG p.172, uncommon, no attunement). First sensory-passive item in `_MAGIC_ITEM_PASSIVES` with `sees_in_darkness: True`. Composes with the v2.158.50 Devil's Sight darkness-blinded helper (`_pc_sees_in_darkness`) so a Goggles-equipped PC who's blinded by darkness shrugs off attack disadvantage exactly as a Devil's-Sight Warlock does. Pip Quickfingers (Halfling Rogue Lv 5 — no racial darkvision) carries the Goggles at inventory_index 10 in the demo seed.

| Test | What it asserts |
|------|-----------------|
| `test_goggles_negate_darkness_blinded_disadvantage` | Pip darkness-blinded + Goggles equipped → attack roll stays 1d20 (no disadvantage). Mirror of Devil's Sight case but powered by the item passive. |
| `test_goggles_unequipped_does_not_negate_disadvantage` | Unequip the Goggles → darkness-blinded Pip rolls at disadvantage as normal (2d20kl1 + `roll_state_applied == "disadvantage_attacker_blinded"`). |
| `test_goggles_do_not_cure_non_darkness_blindness` | Goggles equipped + non-darkness blinded (e.g. Blindness/Deafness spell, no `from_darkness` marker) → disadvantage STILL applies. Goggles only negate the inability to see in darkness. |

### `test_exhaustion.py`
v2.159.17 exhaustion-levels Phase 1 (see [exhaustion-levels.md](../plans/exhaustion-levels.md)) — data shape + `POST /api/campaign/{cid}/set_exhaustion` endpoint + long-rest decrement. Replaces the legacy single-flag exhaustion treatment with RAW SRD 5.1 six-level tracking. Read-site wiring (Lv 1 ability-check disadvantage; Lv 2 speed halved; Lv 3 attack + save disadvantage; Lv 4 HP-max halved; Lv 5 speed 0) is Phase 2-3; this commit lands the data foundation + level-6-death plumbing.

| Test | What it asserts |
|------|-----------------|
| `test_set_exhaustion_absolute` | POST with `level: 3` → 200; `level: 3`, `previous: 0`, `died: False`; sheet readback confirms `exhaustion_level == 3`. |
| `test_set_exhaustion_delta` | After level=2, POST with `delta: 1` → level=3 (delta layers on the current value, not from 0). |
| `test_set_exhaustion_clamps_at_six` | POST with `delta: 99` from 0 → caps at 6, `died: True`; sheet `death_saves.status == "dead"` (routes through `_set_death_save_state`). |
| `test_set_exhaustion_clamps_at_zero` | POST with `delta: -99` from level=2 → floors at 0 (no underflow). |
| `test_long_rest_decrements_exhaustion` | Level=3 → long rest → level=2 (RAW PHB Appendix A). |
| `test_long_rest_at_zero_stays_zero` | Long rest at level=0 keeps level=0 (no underflow on rest path either). |
| `test_set_exhaustion_missing_body_returns_400` | Body missing both `level` AND `delta` → 400 (exactly-one validator). |
| `test_set_exhaustion_both_target_ids_returns_400` | Body has both `character_id` AND `combatant_id` → 400 (exactly-one target validator). |

### `test_all_items_validate.py`
v2.159.16 magic-items-automation Phase 8p (items-only) + v2.159.23 Phase 8q (all 9 content types). Boot-time validator walks every shipped JSON under `app/data/local/dnd5e/<type>/` for each type in `content_schemas.TYPE_REGISTRY` (races, class_features, subclass_features, spells, items, feats, backgrounds, monsters, conditions — 984 records total). The `/api/content-health` endpoint mirrors the result as `{type: {checked, errors}}` per type. The harness asserts every type has empty errors on every CI run.

| Test | What it asserts |
|------|-----------------|
| `test_content_health_endpoint_reports_zero_errors_for_all_types` | `GET /api/content-health` → 200 with per-type maps; EVERY content type's `errors` is empty. Regression failure dumps `<type>/<file>: <error>` per offender. |
| `test_content_health_checked_minimums_per_type` | Each content type's `checked` count meets a sane minimum (e.g. spells ≥ 100, monsters ≥ 100). Catches a validator that walked the wrong dir. |
| `test_content_health_covers_all_nine_types` | All nine `TYPE_REGISTRY` keys appear in the response. Catches a missing-type regression. |

### `test_concurrency.py`
Multi-client races and late-joiner behavior. Guards the per-campaign `CampaignHub` + WS broadcast pipeline.

| Test | What it asserts |
|------|-----------------|
| `test_concurrent_attacks_both_broadcasts_arrive` | Two simultaneous `/attack` POSTs (GM + Alice) both produce `weapon_attack` WS events to every client. |
| `test_concurrent_rolls_all_arrive` | Burst of 10 `/roll` POSTs arrives in order on the GM's WS. |
| `test_late_joiner_does_not_get_replay` | A client connecting AFTER a roll fires doesn't see the past event (intended — WS doesn't replay history). |
| `test_late_joiner_does_get_subsequent_broadcasts` | Same client sees broadcasts that fire AFTER they connected. |
| `test_multi_tab_same_user_both_receive` | Alice with two WS connections receives each broadcast on both. |

### `test_dice_seeding.py`
v2.49.12 — TEST_MODE-only `/api/test/dice/seed` endpoint that re-seeds the shared dice RNG. Foundation for the encounter-simulation suite (docs/plans/encounter-sim-test-suite.md) — reproducible dice unlock assertions like "Fireball 8d6 = 24 fire damage" without flake.

| Test | What it asserts |
|------|-----------------|
| `test_seed_endpoint_accepts_int_seed` | `POST /api/test/dice/seed {seed:42}` → 200, body echoes the seed. |
| `test_seed_endpoint_accepts_null_seed` | `seed:null` re-seeds from OS entropy, endpoint still 200. |
| `test_seeded_rolls_are_reproducible` | After re-seeding with the same value, two sequences of `4d6` rolls match index-for-index. |
| `test_different_seeds_produce_different_rolls` | Different seeds diverge — guards against a no-op seed handler. |
| `test_seeded_d20_total_in_range` | Seeded `1d20` total still lands in `[1, 20]` — regression catch for a broken seeded resolver. |

---

## Generic rolls + roll requests

### `test_roll.py`
The `/roll` endpoint + WS broadcast shape + visibility filter.

| Test | What it asserts |
|------|-----------------|
| `test_roll_d20` | `1d20` returns `{total, breakdown, expression}`; WS `roll` event matches. |
| `test_roll_4d6` | Multi-die expression rolls correctly; breakdown contains 4 brackets. |
| `test_roll_invalid_visibility` | `visibility: "garbage"` → 400. |
| `test_roll_gm_only_hidden_from_player` | `gm_only` roll's WS event doesn't reach Alice's WS but does reach the GM's. |
| `test_roll_gm_and_roller_hidden_from_non_roller` | `gm_and_roller` roll from Alice reaches Alice + GM but not Bob. |

### `test_roll_request.py`
GM-driven roll-prompt flow used by T.3 PC save spells.

| Test | What it asserts |
|------|-----------------|
| `test_gm_creates_roll_request` | `POST /roll_request` as GM → 200 + numeric `id`. |
| `test_non_gm_cannot_create_roll_request` | Alice → 403. |
| `test_roll_request_missing_label_400` | Empty `label` → 400. |
| `test_respond_to_roll_request` | GM responds on Pip's behalf; server resolves WIS-save mod + rolls `1d20+mod`; response carries `total` + `breakdown`. |
| `test_respond_invalid_req_id_404` | Bogus `req_id` → 404. |
| `test_respond_for_someone_elses_character_403` | Alice responds for Krieger (not hers) → 403 (or 404 fallback). |

---

## Weapon attacks

### `test_attack.py`
Basic `/attack` happy paths + error paths + bonus-damage uplifts.

| Test | What it asserts |
|------|-----------------|
| `test_attack_pip_shortsword` | Pip's L1 attack (`index=0`) rolls a d20 + slashing dmg; broadcast matches. |
| `test_attack_pip_dagger` | Same flow at `index=1`. |
| `test_attack_tavik_warhammer` | Tavik's L1 attack works; carries `damage_type=bludgeoning`. |
| `test_attack_invalid_index` | `attack_index=999` → 404. |
| `test_attack_missing_character_id` | Empty body → 400. |
| `test_attack_sneak_attack_uplift` | Pip with `uplifts=["sneak-attack"]` rolls extra `1d6` damage; broadcast carries the uplift in `auto_uplifts`. |
| `test_attack_divine_smite_spends_slot` | Sir Caelan's Smite consumes a L1 paladin slot + adds radiant dice. |
| `test_attack_divine_smite_no_slot` | Smite without an available slot → 409. |
| `test_attack_spend_slot_missing_class` | `spend_spell_slot` without `class_slug` → 400. |
| `test_attack_assassinate_auto_crit_vs_surprised` | v2.131.0 — PATCH-swaps Pip's subclass to Assassin, attacks with `target_surprised: true`, asserts `is_crit: true` on the broadcast + crit-doubled damage range. Restores subclass on teardown. Gated to Assassin Rogue Lv 3+ so a non-Assassin `target_surprised` is silently ignored. |

### `test_attack_auto_damage.py`
T.2 hit determination + auto-applied damage + Undo. Gated by `Campaign.auto_apply_damage` toggle.

| Test | What it asserts |
|------|-----------------|
| `test_attack_hit_determination_without_auto_apply` | Toggle off: response carries `hit` / `target_ac` but no HP change. |
| `test_attack_auto_apply_on_hit` | Toggle on: hits apply damage; `damage_applied > 0`, target HP drops. |
| `test_attack_crit_doubles_damage` | Forced crit doubles the damage dice (via `_double_dice_for_crit`). |
| `test_undo_attack_damage` | `POST /undo_attack_damage` reverses the HP change for the cast id. |
| `test_undo_unknown_attack_id` | Unknown id → 404. |
| `test_undo_missing_attack_id_field` | Empty body → 400. |

### `test_npc_attack.py`
v2.49.164 — parallel `/api/campaign/{cid}/npc_attack` endpoint for NPC monster combatants. GM-only. Mirrors PC `/attack` (d20 + damage + hit-vs-AC + auto-apply on hit) but reads attacker context from `combatant_id` instead of `character_id` + `attack_index`. Reuses the existing `weapon_attack` broadcast type with NPC-shaped caster fields (`caster_char_id: None`, `caster_char_name: <NPC name>`, `caster_combatant_id`, `is_npc_attack: True`).

| Test | What it asserts |
|------|-----------------|
| `test_npc_attack_happy_path` | Bandit `+3 to hit / 1d6+1 slashing` vs Pip: response carries `attack_total`, `damage_total`, `target_ac`, `hit`; broadcast carries `is_npc_attack=True`, `caster_combatant_id`, `caster_char_id=None`. Auto-apply off — no HP change. |
| `test_npc_attack_auto_apply_on_hit` | With `campaign.auto_apply_damage=on`, probe-fires up to 12 attacks until one lands; verifies `target_hp_after` shifts + `auto_applied=True`. |
| `test_npc_attack_no_target_still_rolls` | Endpoint called without `target_combatant_id` still rolls + broadcasts; `hit=None`, `damage_applied=0`. GM uses this for "I want the rolls in the log without committing." |
| `test_npc_attack_missing_combatant_id` | Empty body → 400. |
| `test_npc_attack_unknown_combatant_id` | Attacker not in battle → 404. |
| `test_npc_attack_unknown_target_combatant_id` | Target not in battle → 404. |
| `test_npc_attack_out_of_range_returns_409` | v2.49.166: `range` body field is parsed; endpoint accepts `override_range: true` body param without 400-ing. Fail-open semantics documented — out-of-range only fires when both attacker + target tokens are on the active map. |
| `test_npc_attack_override_range_bypasses_check` | v2.49.166: explicit `override_range: true` short-circuits the range check unconditionally. |
| `test_npc_attack_player_forbidden` | Non-GM caller → 403 (NPCs are GM-authorised). |

### `test_attack_force_gm_sync.py`
v2.49.40 — `/attack` against an NPC broadcasts `battle_update` with `force_gm_sync: True` so the GM client (whose `battle_update` handler ignores broadcasts without the flag per the v2.5.5 echo-loop guard) actually applies the HP change. Pre-fix the GM's local state stayed at pre-attack HP until something else triggered `pushBattle`, then the GM's stale local state overwrote the server's new HP — the bandit visually "came back to life."

| Test | What it asserts |
|------|-----------------|
| `test_npc_damage_broadcast_carries_force_gm_sync` | Krieger attacks Bandit Alpha; `battle_update` broadcast carries `force_gm_sync=True`; broadcasted state contains the updated combatant HP. Skips assertion gracefully on miss (no broadcast in that case). |

### `test_sheet_patch_hp_broadcast.py`
v2.49.42 — `PATCH /sheet-fields` broadcasts `character_hp_update` on HP change (not just `character_death_save` on status crossings). Pre-fix, vanilla HP edits within "alive" went silent on the WS, so non-GM clients couldn't observe HP-bar movement from GM sheet edits or test damage applications.

| Test | What it asserts |
|------|-----------------|
| `test_hp_drop_within_alive_broadcasts` | PATCH HP down (35 → 25) without crossing status fires `character_hp_update` with negative delta + `source: "sheet_patch"`. |
| `test_hp_heal_broadcasts_positive_delta` | PATCH HP up fires `character_hp_update` with positive delta. |
| `test_hp_unchanged_does_not_broadcast` | PATCH with `current == current` (no-op) suppresses the broadcast — prevents settings-form spam. |

### `test_attack_buff_intercepts.py`
Phase B damage-flow intercepts — Rage / Hunter's Mark / Colossus Slayer / resistance.

| Test | What it asserts |
|------|-----------------|
| `test_rage_adds_damage_bonus` | Krieger with Rage buff adds +2 damage to a melee strength attack. |
| `test_rage_advantage_on_attack` | Reckless attack flag rolls 2d20 keep-highest. |
| `test_hunters_mark_rider_on_marked_target` | Rowan's strike vs marked target adds 1d6 bonus dice. |
| `test_hunters_mark_does_not_fire_on_other_target` | Strike vs unmarked target → no bonus dice. |
| `test_colossus_slayer_fires_vs_below_max_hp` | Hunter Ranger's bonus 1d8 fires when target HP < max. |
| `test_colossus_slayer_skips_full_hp_target` | Same archer vs full-HP target → no bonus. |
| `test_colossus_slayer_once_per_turn` | Second attack in the same turn skips the bonus (1/turn limit). |
| `test_resistance_halves_damage` | Krieger's slashing attack on a slashing-resistant NPC → halved. |
| `test_resistance_does_not_halve_unrelated_type` | Different damage type → no halving. |
| `test_attack_broadcast_includes_target_name` | Broadcast `target_name` populated when init-tracker combatant resolves. |
| `test_assassinate_advantage_vs_target_who_hasnt_acted` | v2.132.0 — PATCH-swaps Pip's subclass to Assassin, seeds a battle with Tavik (default `has_acted: False`), attacks with `target_combatant_id=tavik_cid`; asserts `2d20kh1` in the breakdown + `roll_state_applied == "advantage_assassinate_hasnt_acted"`. |
| `test_assassinate_advantage_gate_drops_after_target_acts` | v2.132.0 — Companion: after Tavik's turn starts (`turn_index=1`), his `has_acted` flips True via the turn-advance hook in PUT `/battle`; Pip's next attack does NOT get the Assassinate advantage. |

### `test_npc_resistance.py`
v2.49.109 — closes the v2.49.107 damage-review finding that the NPC branch of `_apply_damage_to_combatant` silently no-op'd resistance. The new `_resistance_halve_npc` helper resolves resistances from (1) the combatant's TokenTemplate's `sheet.damage_resistances` list and (2) the combatant's own `buffs` list.

| Test | What it asserts |
|------|-----------------|
| `test_npc_template_fire_resistance_halves_fireball` | NPC with `damage_resistances: ["fire"]` on its template takes ≤ 24 HP from Fireball (resistance halved from max 48). |
| `test_npc_no_resistance_takes_full_fireball` | Control: NPC with empty `damage_resistances` takes normal damage — confirms the halving is conditional, not unconditional. |

---

## Spell casting

### `test_cast_spell.py`
Basic `/cast_spell` happy paths + slot-consumption errors.

| Test | What it asserts |
|------|-----------------|
| `test_cast_magic_missile` | Thalindra's Magic Missile (L1) decrements a wizard slot; broadcast names the spell. |
| `test_cast_misty_step_bonus_action` | Misty Step at L2 marks the bonus chip. |
| `test_cast_tavik_healing_word` | Tavik's bonus-action heal cast (long-rest pre-fixture). |
| `test_cast_invalid_spell_index` | `spell_index=999` → 404. |
| `test_cast_missing_fields` | Empty body → 400. |
| `test_upcast_echoes_slot_level_and_higher_level` | Up-cast echoes `slot_level` + `higher_level` on the broadcast. |
| `test_upcast_scales_damage_dice` | Burning Hands at L2 → 4d6 (v2.110.0 resolver). |
| `test_upcast_scales_moonbeam_damage` | Moonbeam at L3 → 3d10. |
| `test_upcast_scales_heat_metal_damage` | v2.123.0 — Mira casts Heat Metal at L3 → 3d8 (backfilled `damage_per_slot`). |
| `test_upcast_scales_hellish_rebuke_damage` | v2.123.0 — Magnus casts Hellish Rebuke at L3 → 4d10. |
| `test_upcast_scales_acid_arrow_multitype` | v2.124.0 — restore-safe spell-list patch → Acid Arrow at L3 → 5d4 (resolver reads the field from content by `_slug`). |
| `test_upcast_scales_from_higher_level_prose` | v2.125.0 — Thunderwave (2d8, NO structured field) at L2 → 3d8 via the `parse_upcast_dice` fallback. Restore-safe spell-list patch. |
| `test_modeled_base_healing_then_parser_scales` | v2.126.0 — Prayer of Healing (base 2d8 now modeled) cast at L3 → `spell_healing == "3d8"` (base + parser +1d8). Restore-safe spell-list patch on Tavik. |
| `test_upcast_scales_per_two_slot_spiritual_weapon` | v2.129.0 — Tavik (Cleric) casts Spiritual Weapon at L4 → 2d8 (base 1d8 just-modeled + 1d8 from `upcast_step=2`, eff_extra=1). Restore-safe spell-list patch. Flame Blade's per-two phrasing is covered by the parser-unit tests; an end-to-end cast test would need a higher-level Druid PC (Mira is Lv 2 with no L4 slot). |
| `test_upcast_scales_healing_dice` | Cure Wounds at L2 → 2d8 healing. |
| `test_upcast_base_level_leaves_dice_unscaled` | Burning Hands at base L1 stays 3d6 (no-op). |

### `test_spell_upcast_parser.py`
v2.125.0 — pure-Python unit tests for `app/content/spell_upcast_parse.py::parse_upcast_dice`, the conservative `higher_level`-prose → per-slot-dice parser the `/cast_spell` resolver uses as a fallback below manual `damage_per_slot` / `healing_per_slot` fields.

| Test | What it asserts |
|------|-----------------|
| `test_parses_per_slot_damage` | "+1d6 for each slot level above 3rd" → `{damage_per_slot: 1d6}`. |
| `test_parses_per_slot_healing` | "the healing increases by 1d8 for each slot level above 1st" → `{healing_per_slot: 1d8}`. |
| `test_parses_multi_die_term` | "+2d6 for each slot level above 7th" → `{damage_per_slot: 2d6}`. |
| `test_ignores_cantrip_character_level_scaling` | "when you reach 5th level" → `{}` (no slot). |
| `test_parses_per_two_level_damage` | v2.129.0 — "+1d6 for every two slot levels above 2nd" → `{damage_per_slot: 1d6, upcast_step: 2}`. |
| `test_parses_per_two_level_damage_spiritual_weapon` | v2.129.0 — "above the 2nd" prose variant matches the same shape. |
| `test_parses_per_two_level_healing` | v2.129.0 — heal/damage classifier still routes per-two clauses correctly. |
| `test_ignores_instance_scaling` | "one more dart for each slot level" → `{}` (no dice term). |
| `test_ignores_flat_bonus` | "increases by 5 for each slot level" → `{}`. |
| `test_empty_or_missing` | `""` / `None` → `{}`. |
| `test_target_count_hold_person` | v2.127.0 — `upcast_target_count(slot, base_level=2)` → L2/L3/L4 = 1/2/3. |
| `test_target_count_hold_monster` | v2.127.0 — `upcast_target_count(slot, base_level=5)` → L5/L6/L9 = 1/2/5. |
| `test_target_count_clamps_and_params` | v2.127.0 — clamps below base level; custom `base_targets`/`per_slot` (Bless-style 3 +1/slot). |
| `test_pool_dice_sleep` | v2.128.0 — `upcast_pool_dice(slot, base_level=1, base_dice=5, per_slot_dice=2)` → L1/L2/L3 = 5/7/9 (Sleep HP pool). |
| `test_pool_dice_clamps_below_base` | v2.128.0 — slot below base never under-rolls the base dice count. |
| `test_parses_flat_healing_aid` | v2.130.0 — Aid's "+5 hit points for each slot level above 2nd" → `{flat_healing_per_slot: 5}`. |
| `test_parses_flat_healing_heal` | v2.130.0 — Heal's "+10 healing per slot above 6th" → `{flat_healing_per_slot: 10}`. |
| `test_parses_flat_healing_false_life` | v2.130.0 — False Life's "5 additional temporary hit points" (keyword AFTER the number) → `{flat_healing_per_slot: 5}` via the broadened classifier. |
| `test_flat_does_not_match_dice_clause` | v2.130.0 — regression guard: a dice clause must not surface the dice-internal digit as a flat per-slot value. |
| `test_flat_scaler_pure_flat_base` | v2.130.0 — `scale_flat_for_upcast("70", 10, 1)` → "80" (Heal at L7). |
| `test_flat_scaler_dice_plus_flat_base` | v2.130.0 — `scale_flat_for_upcast("1d4+4", 5, 1)` → "1d4+9" (merges into the +N suffix; False Life at L2). |
| `test_flat_scaler_pure_dice_base` | v2.130.0 — `scale_flat_for_upcast("1d8", 5, 1)` → "1d8+5" (appends +N to a pure dice base). |
| `test_flat_scaler_base_unchanged_on_no_op` | v2.130.0 — extra_levels=0 / per_slot=0 / unparseable base each return the base unchanged. |

### `test_cast_counterspell.py`
v2.183.11 — spell-validation suite Phase 4 (first complex-spell deep-dive). Counterspell's mechanic *is* a reaction-prompt contract, not a damage/save formula: when a leveled spell resolves to 200 at `/cast_spell`, the tail walker `_emit_counterspell_prompts` (tabletop_routes.py:6126) broadcasts a `reaction_prompt` (`trigger_event:"spell_cast_near"`) to each eligible watcher. This file pins the positive emission plus the three exclusion gates, with the Sorcerer caster (Zara) scratch-injected with the whole catalog + abundant slots so the L1 and L0 casts both resolve deterministically. Companion to `test_counterspell_subtle_immune.py` (the suppression half) — together they fence the prompt contract on both sides.

| Test | What it asserts |
|------|-----------------|
| `test_counterspell_present_in_catalog` | Catalog anchor — Counterspell present in the spell catalog (guards against a rename/removal silently disarming the suite). |
| `test_prompt_emits_on_visible_leveled_cast` | Zara@(350,350) casts Mage Armor (L1); Thalindra@(420,350) within 60 ft holds Counterspell + a free reaction + a 3rd-level slot → a `spell_cast_near` `reaction_prompt` fires with `watcher_char_id == Thalindra`, a `cast-counterspell` option whose `params.incoming_spell_level == 1`, `slot_level >= 3`, and an "AUTO-COUNTER" label (slot ≥ incoming). |
| `test_no_prompt_for_cantrip` | Fire Bolt (L0) → no prompt — the walker excludes `spell_level == 0`. |
| `test_no_prompt_when_watcher_out_of_range` | Thalindra moved beyond `COUNTERSPELL_RANGE_FT = 60.0` → no prompt. |
| `test_no_prompt_when_watcher_lacks_counterspell` | Thalindra's sheet patched to drop Counterspell → no prompt. |

### `test_cast_spirit_guardians.py`
v2.183.12 — spell-validation suite Phase 4 (second complex-spell deep-dive). Spirit Guardians is the catalog's canonical self-anchored concentration AoE: a 15-ft `self_sphere` centred on the caster, rolling a Wisdom save (3d8 radiant, save-for-half) against everything in the area for the duration. This file owns the full live cast → place → persist story. Bundled with a one-line catalog fix: the `concentration` flag in `spirit-guardians.json` was corrected `false` → `true` (the cast path already treated it as concentration via the "Up to ..." duration fallback, but the `spell_concentration` response field read the raw flag). Caster: Brother Tavik Stonebrow (demo Cleric, native Spirit Guardians + L3 slots; spell index resolved from the live sheet). Companion to `test_cast_spell_aoe.py` (generic AoE dispatch) and `test_use_spiritual_weapon.py` (the other Cleric concentration-summon deep-dive).

| Test | What it asserts |
|------|-----------------|
| `test_spirit_guardians_present_in_catalog` | Catalog anchor — Spirit Guardians present **and** its `concentration` flag is now `true` (guards both the rename and the corrected flag). |
| `test_cast_marks_concentration_and_pending_self_sphere` | Cast with no targets → HTTP `pending_aoe_placement: true`, `area_shape == "self_sphere"`, `area_size_ft == 15`; the `spell_cast` broadcast carries `spell_concentration == true` (the field the catalog flag fix corrects — the HTTP response is a curated subset that omits it). |
| `test_place_dispatches_radiant_saves` | `/place_aoe` on 2 bandits (auto-apply on) → `auto_save_targets` has 2 entries each with an int `rolled`, bool `passed`, `damage_type == "radiant"`, and `damage_applied > 0` (3d8 save-for-half). |
| `test_place_creates_self_anchored_concentration_marker` | Placement broadcasts `concentration_aoe_update` carrying a Spirit Guardians marker with `is_self_anchored: true`, `shape == "self_sphere"`, and `caster_char_id == Tavik` (the aura follows the caster). |
| `test_self_anchored_marker_not_movable` | `/move_aoe` on the self-anchored marker → 409 `not_movable` (Spirit Guardians tracks the caster's token; it can't be repositioned like Web/Moonbeam). |

### `test_cast_eldritch_blast.py`
v2.183.13 — spell-validation suite Phase 4 (third complex-spell deep-dive). Eldritch Blast is the Warlock's signature cantrip: a 1d10 force ranged spell attack that fires additional beams as the caster levels (1 / 2 / 3 / 4 beams at L1 / L5 / L11 / L17). Where the catalog matrix treats it as a generic attack cantrip, this file owns its multi-beam scaling — driven by the cantrip `damage_scaling` tier's `extra_beams` count (`tabletop_routes.py:19252-19445`). Caster: Magnus Hexbinder (demo Warlock Lv 5 → 2 beams natively; spell index resolved from the live sheet). The level-scaling test PATCHes Magnus's sheet `level` to 1 / 11 / 17 and the fixture restores it.

| Test | What it asserts |
|------|-----------------|
| `test_eldritch_blast_present_in_catalog` | Catalog anchor — Eldritch Blast present with the `extra_beams` scaling tiers (L5 +1, L11 +2, L17 +3) that drive the beam count; a dropped/edited tier collapses the spell to a single beam. |
| `test_cast_fires_two_beams_at_level_five` | Magnus (Lv 5) casts → exactly 2 beams in `auto_attack_beams`, numbered `[1, 2]`, each carrying an int `total` + bool `hit`; aggregate `auto_attack_damage_type == "force"`. |
| `test_beam_count_tracks_character_level` | PATCH the caster's `level` to 1 / 11 / 17 → 1 / 3 / 4 beams respectively (the `extra_beams` tiers exercised end-to-end). |
| `test_aggregate_damage_is_sum_of_hit_beams` | Seed dice until a beam hits; `auto_attack_damage_rolled` is exactly the sum of the per-beam `damage_rolled`, every hit beam rolls a single 1d10 (1-10) force die and missed beams roll 0 (no `/cast_spell`-path rider — Agonizing Blast's +CHA lives on the `/attack` weapon entry). |

### `test_cast_magic_missile.py`
v2.183.14 — spell-validation suite Phase 4 (fourth complex-spell deep-dive). Magic Missile is the catalog's one true auto-hit attack: three 1d4+1 force darts with no save and no attack roll, directable at one creature or several. The engine rolls one die per target combatant id in the cast body and surfaces them in `auto_hit_targets` (when `campaign.auto_apply_damage` is on). Where Phase 2A's `test_spell_catalog_autohit.py` checks the matrix shape (3 darts at one target, in band), this file owns the bespoke story that distinguishes it from Eldritch Blast's per-beam attack rolls. Caster: Thalindra Moonwhisper (demo Wizard L7, native Magic Missile + L1 slots; spell index resolved from the live sheet).

| Test | What it asserts |
|------|-----------------|
| `test_magic_missile_present_in_catalog` | Catalog anchor — Magic Missile present as a no-save / no-attack force-damage spell whose action documents the dart-count scaling (`aoe_targets == 3` base + `extra_targets_per_slot_above_base == 1`). |
| `test_three_darts_split_across_distinct_targets` | Cast at three distinct targets → three `auto_hit_targets` entries with three distinct combatant ids, each a 1d4+1 (2-5) force roll that applied non-zero damage ("one creature or several"). |
| `test_darts_auto_hit_with_no_attack_roll` | The response carries `auto_hit_targets` and **not** `auto_attack_beams` (no spell-attack path), and every dart applies > 0 across dice seeds 1-6 (no dart ever misses) — the contrast with Eldritch Blast's missable beams. Long-rests between casts so the L1 slots don't deplete. |
| `test_aggregate_is_exact_sum_of_darts` | Seeded for determinism: each dart's `damage_applied == rolled` (full-HP force targets), and the total applied equals the sum of the per-dart rolls — no rider on the auto-hit path (Empowered Evocation +INT doesn't touch it). |

### `test_cast_spiritual_weapon.py`
v2.183.15 — spell-validation suite Phase 4 (fifth complex-spell deep-dive). Spiritual Weapon is the Cleric's bonus-action floating attacker: a 1d8 + spellcasting-mod melee spell attack, "+1d8 per two slot levels above 2nd." Modeled on `/use_spiritual_weapon` (`n`d8 + mod where `n = 1 + (slot_level - 2) // 2`). The summon / concentration-drop dismiss / single-attack lifecycle is fenced by `test_use_spiritual_weapon.py`; this file owns the upcast scaling + the catalog-vs-runtime concentration divergence. Caster: Brother Tavik Stonebrow (demo Cleric); spellcasting mod read from the live sheet. The endpoint doesn't gate on slots, so the 4th-level upcast cast needs no L4 slot.

| Test | What it asserts |
|------|-----------------|
| `test_spiritual_weapon_present_in_catalog` | Catalog anchor — present as a 2nd-level bonus-action melee spell attack (1d8 force, `attack_roll: true`), with the `higher_level` note documenting the +1d8-per-two-levels upcast scaling. |
| `test_base_cast_rolls_a_single_d8` | At a 2nd-level slot a hit's `damage_rolled` lands in [1 + mod, 8 + mod] force (a single d8 + spellcasting mod). |
| `test_upcast_adds_a_die_per_two_levels` | A 4th-level cast (→ 2d8) hits with `damage_rolled` above a single d8's ceiling (8 + mod) — impossible for one die, proving the upcast tier added a second die; capped at 16 + mod. Seeds until such a hit appears. |
| `test_cast_binds_concentration_despite_catalog_flag` | House-rule divergence: catalog flags `concentration: false`, but the cast returns a `concentration_bound: true` weapon and broadcasts a `concentration_update` for "Spiritual Weapon" (`ended: false`). |

### `test_cast_hold_person.py`
`/cast_hold_person` — a 2nd-level concentration enchantment that paralyzes a humanoid on a failed WIS save. The first six tests cover the endpoint contract (target-count gating by slot level, slot spend/refund). v2.183.16 appended the Phase 4 deep-dive: the installed buff is the canonical Paralyzed condition (`tabletop_routes.py:31011` `_make_paralyzed_buff` / `:31118` `_make_hold_person_paralyzed_buff`), and the RAW end-of-turn WIS re-save is wired via `/use_repeated_save` (`:23034`) off the buff's install-time `repeated_save_ability`/`repeated_save_dc` stamps. The auto-fail-saves / melee-auto-crit Paralyzed mechanics remain GM-narrated `raw_effects` (not engine-enforced). Caster: Brother Tavik Stonebrow (demo Cleric) on Krieger Stonefist (demo Barbarian, speed 40).

| Test | What it asserts |
|------|-----------------|
| `test_cast_hold_person_installs_paralyzed_buff` | L2 cast on Krieger → 1 target, `speed_reduction_ft == 40` (full base speed → effective 0), `concentration: true`, affected entry `installed: true`. |
| `test_cast_hold_person_upcast_l4_allows_3_targets` | L4 upcast → `max_targets == 3`; only Krieger resolves (1 affected), 2 fakes → `unaffected` with `reason: not_found`. |
| `test_cast_hold_person_l2_with_2_targets_rejected` | L2 caps at 1 target; 2 targets → 409 `too_many_targets` (`max: 1`, `got: 2`). |
| `test_cast_hold_person_l1_slot_rejected` | `slot_level == 1` → 400 (Hold Person is L2). |
| `test_cast_hold_person_rejects_invalid_class` | Barbarian isn't on the Hold Person class list → 400. |
| `test_cast_hold_person_undo_refunds_slot` | Cast carries a `cast_id`; `/undo_attack_damage` with it broadcasts a `spell_slot_update` refunding the L2 cleric slot (`used` − 1). |
| `test_cast_hold_person_buff_carries_paralyzed_contract` | Phase 4 — the installed combatant buff carries `key == "paralyzed"`, `concentration: true`, `source: "hold-person-spell"`, the WIS re-save stamps (`repeated_save_ability == "WIS"`, `repeated_save_dc > 0`), `speed_reduction_ft == 40`, and the full RAW `raw_effects` narration (incapacitated / can't speak / auto-fail STR-DEX / melee auto-crit / "WIS save at end of each turn" / "Only affects Humanoids"). |
| `test_cast_hold_person_end_of_turn_wis_resave` | Phase 4 — `/use_repeated_save {buff_key: "paralyzed"}` resolves a WIS save vs the stamped DC; a seed-loop (re-casting + long-resting Tavik to refill L2 slots) observes both a pass (`buff_dropped: true`, buff gone) and a fail (`buff_dropped: false`, buff persists); the save is always WIS vs a positive DC. |

### `test_cast_polymorph.py`
`/cast_polymorph` — a 4th-level concentration Transmutation that turns a creature into a beast (CR ≤ its level). The spell splits across `/cast_polymorph` (spell-side: slot + invocation gate + concentration anchor) and `/transform source=polymorph` (the actual stat-block swap, `tabletop_routes.py:80641`). The first six tests cover the spell-side contract (Sculptor of Flesh invocation gate, slot/level gates). v2.183.17 appended the Phase 4 deep-dive: the catalog-vs-runtime concentration divergence + the full six-ability stat-block replace that distinguishes Polymorph from Wild Shape. Casters: Magnus Hexbinder (Warlock, via Sculptor of Flesh) for the spell-side tests; Thalindra Moonwhisper (Wizard) on Krieger Stonefist (Barbarian) for the swap. The swap test is Open5e-gated.

| Test | What it asserts |
|------|-----------------|
| `test_sculptor_of_flesh_happy_path` | Magnus casts Polymorph via the Sculptor of Flesh invocation → 200, `concentration: true`, `ready_to_transform: true`, `concentration-polymorph` anchor installed. |
| `test_warlock_without_via_invocation_409` | `class_slug: warlock` without `via_invocation` → 409 `missing_invocation` (Polymorph isn't a Warlock spell). |
| `test_warlock_wrong_invocation_409` | Warlock + `via_invocation: mire-the-mind` → 409 `missing_invocation` (registry rejects: that invocation maps to "slow", not "polymorph"). |
| `test_sculptor_of_flesh_second_cast_409` | Second Sculptor of Flesh cast in the same long rest → 409 `not_enough_uses` (1/long-rest gate). |
| `test_cast_polymorph_l3_slot_400` | `slot_level: 3` → 400 (Polymorph is L4). |
| `test_cast_polymorph_missing_character_id_400` | Missing `character_id` → 400. |
| `test_polymorph_present_in_catalog` | Phase 4 — catalog anchor: 4th-level Transmutation, "Up to 1 hour" duration, WIS save, and `concentration: false` (the flag the divergence test pins against the runtime cast). |
| `test_cast_binds_concentration_despite_catalog_flag` | Phase 4 — house-rule divergence (mirror of Spiritual Weapon's): catalog flags `concentration: false`, but `/cast_polymorph` returns `concentration: true` + installs the `concentration-polymorph` caster anchor. |
| `test_polymorph_full_ability_replace_and_revert_restores` | Phase 4 (Open5e-gated) — `/transform source=polymorph` replaces ALL six abilities with the beast's (asserted structurally against the response's `active_form.form_sheet`, no hardcoded numbers) + swaps in the beast HP pool + the mental stats actually change (Wild Shape keeps them); `/revert` restores the prior form's abilities + HP exactly. |

### `test_cast_mirror_image.py`
Mirror Image (L2 Illusion). v2.543.0 (#57 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md)) promoted it from narration-only to a real, server-resolved deflection mechanic: the dedicated `/cast_mirror_image` endpoint installs a `mirror-image` buff (3 duplicates, AC 10 + DEX mod) and the `/attack` + `/npc_attack` hit path (`_resolve_mirror_image_deflection`) rolls the RAW d20 deflection (3 → 6+, 2 → 8+, 1 → 11+). The generic `/cast_spell` path stays narration-only. Casters: Zara Emberfire (Sorcerer, owns it natively at spell_index 9); attacker Pip Quickfingers.

| Test | What it asserts |
|------|-----------------|
| `test_mirror_image_present_in_catalog` | Catalog shape: `level_int == 2`, school Illusion, "self" range, "minute" duration, `concentration: false`, and every action carries no `save_ability` / `attack_roll` / `damage`. |
| `test_cast_consumes_l2_slot_and_broadcasts` | Zara casts at L2 via the generic path → `ok: true`, `slot.level == 2`, `slot.used >= 1`; `spell_cast` broadcast carries `spell_name == "Mirror Image"`, `spell_level == 2`, `spell_casting_time == "1 action"`, no damage action. |
| `test_cast_is_non_concentration` | RAW non-concentration: the cast response does NOT flag concentration and installs no `concentration-mirror-image` anchor. |
| `test_generic_cast_spell_path_installs_no_buff` | Contract pin: the generic `/cast_spell` path stays narration-only — spends the slot + broadcasts but installs no `mirror-image` buff (the mechanical duplicates live behind the dedicated endpoint). |
| `test_cast_mirror_image_installs_three_duplicates` | `/cast_mirror_image` → `feature == "mirror-image"`, `duplicates == 3`, `duplicate_ac >= 10`, `duration_rounds == 10`; buff carries `mirror_image_duplicates == 3` + `mirror_image_ac` == response AC, non-concentration. |
| `test_mirror_image_deflects_attacks_and_destroys_duplicates` | **Mechanical:** over a 40-swing loop, a deflected attack (the `mirror_image` block) met the caster's AC yet leaves `hit` False + `damage_applied` 0, and the duplicate count decrements (a destroy is observed). |
| `test_cast_mirror_image_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "mirror image". |
| `test_cast_mirror_image_missing_character_id_400` | Missing `character_id` → 400. |

### `test_ac_buff_spells.py`
+AC spell buffs (Mage Armor / Haste / Shield of Faith) via `_SPELL_BUFF_MAP` `effects.ac_bonus`, read at `/attack`'s `_read_target_ac`. v2.183.19 added the Phase 4 Mage Armor deep-dive (ninth): Mage Armor is the suite's reference case for a *documented RAW-vs-engine simplification* — RAW sets base AC to 13 + Dex, the engine installs a flat +3 ac_bonus buff (non-concentration, 8 hours, applied unconditionally). Caster: Magnus Hexbinder (Warlock) self-cast via the `magnus_with_mage_armor` fixture (Mage Armor patched onto his list at index 11).

| Test | What it asserts |
|------|-----------------|
| `test_mage_armor_installs_ac_buff_and_raises_ac` | Casting Mage Armor on self installs a `mage-armor` buff with `ac_bonus: 3`, and the target's `/attack` `target_ac` rises by exactly +3 over baseline. |
| `test_mage_armor_present_in_catalog` | Phase 4 — catalog shape: `level_int == 1`, school Abjuration, "touch" range, "hour" duration, `concentration: false`, Sorcerer + Wizard lists, every action carries no `save_ability` / `attack_roll` / `damage`. |
| `test_mage_armor_buff_is_flat_plus3_nonconcentration_8h` | Phase 4 — simplification pin: the installed buff carries a flat `effects.ac_bonus == 3` (with NO `ac_set` / `ac_base` / `ac_override` recompute field), is non-concentration (survives the caster casting a concentration spell, unlike Haste / Shield of Faith), and carries the 8-hour (≥100-round) duration that persists across short rests. |

### `test_cast_wish.py`
Wish (L9 Conjuration) — the spell-validation suite's L9 narration-only capstone: no dedicated endpoint, no `_SPELL_BUFF_MAP` entry, effect is pure DM adjudication. Rides the generic `/cast_spell` path (spends an L9 slot + broadcasts `spell_cast`). No demo PC owns Wish (no L17 casters), so the fixture patches Wish + a wizard L9 slot onto Thalindra Moonwhisper (Wizard), restored in finally. v2.183.20 — Phase 4 deep-dive (tenth).

| Test | What it asserts |
|------|-----------------|
| `test_wish_present_in_catalog` | Catalog shape: `level_int == 9`, school Conjuration, "self" range, "instantaneous" duration, `concentration: false`, Sorcerer + Wizard lists. SRD-build quirk pin: the cast action carries `damage == "1d10"` necrotic but no `attack_roll` / `save_ability` (narration-grade stress backlash, not an auto-resolved hit). |
| `test_cast_wish_spends_l9_slot_and_broadcasts` | Wish rides `/cast_spell` → 200, `ok: true`, `slot.level == 9`, `slot.used >= 1`; `spell_cast` broadcast carries `spell_name == "Wish"`, `spell_level == 9`, `spell_casting_time == "1 action"`. Contract: doesn't 500, spends the slot, names the spell. |
| `test_cast_wish_is_non_concentration` | Instantaneous + non-concentration: the cast does NOT flag concentration on the response and installs no `concentration-wish` anchor on the caster. |

### `test_cast_conjure_family.py`
The Conjure X family (narration-only summons) — the spell-validation suite's reference case for summon spells with NO engine wiring, in deliberate contrast to Conjure Animals (`/cast_conjure_animals`). The five higher siblings (Conjure Celestial L7, Elemental L5, Fey L6, Minor Elementals L4, Woodland Beings L4) have no bespoke endpoint and no `_SPELL_BUFF_MAP` entry: they ride the generic `/cast_spell` path (spends a slot + broadcasts `spell_cast`), and the GM stands up the conjured stat block by hand. Cast fixture patches Conjure Minor Elementals + a druid L4 slot onto Mira Greenleaf (Druid), restored in finally. v2.183.21 — Phase 4 deep-dive (eleventh).

| Test | What it asserts |
|------|-----------------|
| `test_conjure_family_present_in_catalog` | Catalog shape across all five siblings: each is Conjuration at the right `level_int` (7/5/6/4/4), carries the right spell-list membership, and has a single cast action with no `save_ability` / `attack_roll` / `damage` (auto-resolves nothing). Catalog-vs-runtime concentration divergence pin: each `concentration` flag is `false` yet the duration starts with "Up to" (the Open5e concentration convention). |
| `test_cast_conjure_minor_elementals_narration_only` | Conjure Minor Elementals rides `/cast_spell` → 200, `ok: true`, `slot.level == 4`, `slot.used >= 1`; `spell_cast` broadcast carries `spell_name == "Conjure Minor Elementals"`, `spell_level == 4`, `spell_casting_time == "1 minute"`. Narration contract: the response carries NO `combatants` / `token_ids` summon payload (contrast `/cast_conjure_animals`). |
| `test_cast_conjure_installs_no_buff_or_anchor` | No `_SPELL_BUFF_MAP` entry and no AoE template: the generic cast installs neither a spell buff nor a `concentration-conjure-*` anchor on the caster (diff of buff keys before/after has no `conjure`/`concentration` keys), and the response is not flagged concentration. |

### `test_cast_homebrew_spell.py`
Homebrew handling — the spell-validation suite's proof that the cast path works for a spell the GM *invents* (no JSON file, no catalog entry). Contract at tabletop_routes.py:18164-18177: `/cast_spell` reads the inline sheet spell dict and only enriches from the catalog when `_slug` resolves, via `setdefault` (sheet fields win). Fixtures patch a fictional "Bless of Bahamut" (+ a `bless`-slugged renamed variant) + a cleric slot onto Brother Tavik Stonebrow (Cleric), restored in finally. v2.183.22 — Phase 4 deep-dive (twelfth/final, closes Phase 4).

| Test | What it asserts |
|------|-----------------|
| `test_bless_of_bahamut_absent_from_catalog` | The homebrew slug `bless-of-bahamut` is NOT in `load_all_spells()` — genuinely non-SRD, so the cast path can't be leaning on a hidden JSON file. |
| `test_cast_homebrew_spell_rides_inline_definition` | A fully-homebrew spell (slug absent from the catalog) casts from its inline sheet definition: `/cast_spell` → 200, L2 slot decrement; `spell_cast` broadcast echoes `spell_name == "Bless of Bahamut"`, `spell_level == 2`, `spell_school == "Evocation"`, `spell_casting_time == "1 action"`, `spell_save_ability == "DEX"`, `spell_damage == "2d8"`, and the inline Radiant Smite action (name/save/damage/`radiant` type) verbatim — no catalog enrichment. |
| `test_homebrew_sheet_override_beats_catalog` | Sheet-side override precedence: a homebrew entry borrowing the real `bless` slug but renaming it broadcasts the SHEET name (`spell_name == "Bahamut's Greater Blessing"`, sheet wins via `setdefault`) while the un-overridden catalog field bleeds through (`spell_school == "Enchantment"` from the SRD `bless` record). |

### `test_cast_spell_target.py`
Phase T.1 target descriptors plumbed into `/cast_spell` body + WS broadcast.

| Test | What it asserts |
|------|-----------------|
| `test_cast_spell_with_target_character_id` | `target_character_id` resolves to `target_combatant_id` server-side; broadcast carries all 3 fields. |
| `test_cast_spell_target_combatant_id_wins` | When both descriptors are present, explicit combatant_id wins. |
| `test_cast_spell_no_target` | No descriptor → broadcast fields empty. |
| `test_cast_spell_target_npc_by_name` | NPC target via `target_name` only resolves to its combatant id. |

### `test_cast_spell_attack.py`
Phase T.4b auto-rolled spell attacks (Fire Bolt etc.) — hit vs AC, crit doubling, damage apply.

| Test | What it asserts |
|------|-----------------|
| `test_fire_bolt_resolves_hit_vs_npc` | Fire Bolt vs bandit: `auto_attack_hit`/`total`/`target_ac` populated; damage rolls when hit + toggle on. |
| `test_spell_attack_no_damage_when_toggle_off` | Toggle off: attack rolls but `damage_applied == 0`. |
| `test_spell_attack_no_target_skips_block` | No target → `auto_attack_hit is None`. |
| `test_fire_bolt_scales_at_l5` | v2.36.0 cantrip scaling: Thalindra (L5) Fire Bolt rolls 2d10 (range 2..20), not 1d10. |
| `test_eldritch_blast_multibeam_at_l5` | v2.40.0 multi-beam: Magnus (L5) Eldritch Blast → 2 beams, each rolling 1d10 (range 1..10 per beam). |
| `test_non_attack_spell_skips_attack_block` | Healing Word (no `attack_roll`) → block skipped. |

### `test_cast_spell_heal.py`
Phase T.4 auto-healing — target-aware HP apply, revive, undo, max-HP cap.

| Test | What it asserts |
|------|-----------------|
| `test_heal_auto_applies_on_target` | Tavik → Pip (HP=10): `auto_heal_applied > 0`, Pip's HP rises. |
| `test_cast_without_target_no_auto_heal` | No target → `auto_heal_applied == 0`, heal_claim registered. |
| `test_heal_revives_dying_target` | Dying Pip → Healing Word brings him back; `auto_heal_revived: True`. |
| `test_undo_heal_reverses_hp` | `/undo_attack_damage` reverses the heal via the `is_heal` flag. |
| `test_heal_auto_applies_with_only_character_id` | Target PC not in init: synthesized-combatant fallback still applies heal. |
| `test_heal_caps_at_max_hp` | Pip at max-1 → only 1 HP applied even if dice rolled higher. |

### `test_cast_spell_save.py`
Phase T.3 save-spell auto-resolution + T.3b save-for-half damage + T.3c condition install.

| Test | What it asserts |
|------|-----------------|
| `test_save_spell_prompts_pc_target` | Hold Person → Pip (PC): `auto_save_prompted=True`, RollRequest created for Pip's owner. |
| `test_save_spell_auto_rolls_npc` | Hold Person → bandit (NPC): server rolls save, `auto_save_rolled`/`passed` populated. |
| `test_cast_without_target_no_auto_save` | No target → save fields empty. |
| `test_save_for_half_applies_half_on_success` | Sacred Flame: full damage on fail, half on success. |
| `test_save_spell_no_auto_damage_when_toggle_off` | Toggle off: save rolls but no damage applied. |
| `test_save_or_suck_installs_buff_on_fail` | Hold Person on bandit failure: Paralyzed buff installed on combatant. |
| `test_save_or_suck_skips_unknown_spell` | Sacred Flame (has damage, not save-or-suck) → no buff installed. |
| `test_non_save_spell_no_auto_save` | Healing Word (no `save_ability`) → save block skipped. |

### `test_save_spell_pc_buff.py`
Phase T.3d — PC save-or-suck via roll-response correlation. When the PC fails their save, the condition buff installs on them through `/roll_request/{id}/respond`.

| Test | What it asserts |
|------|-----------------|
| `test_cast_hold_person_at_pc_creates_prompt` | Cast carries `auto_save_prompt_id` (numeric RollRequest id) when target is a PC. |
| `test_pc_save_fail_installs_paralyzed_buff` | PC fails the save → respond response carries `auto_buff_installed: "Paralyzed"` and `/buffs` GET lists the paralyzed entry. Loops up to 15 attempts to land a failure (Krieger Wis +1 vs DC 14). |
| `test_pc_save_pass_skips_buff` | Manual (non-cast-stashed) `/roll_request` → `/respond` returns `auto_buff_installed: ""` even when forced to fail. |

### `test_cast_spell_aoe.py`
Phase T.5a — AoE multi-target dispatch on `/cast_spell`. New `target_combatant_ids` (list) body field; loops save + save-for-half damage per target; `auto_save_targets` per-target outcome list on response.

| Test | What it asserts |
|------|-----------------|
| `test_fireball_hits_three_bandits` | Thalindra Fireball at 3 bandits → `auto_save_targets` has 3 entries with rolled/passed/damage_applied/damage_type. Each bandit took non-zero fire damage. |
| `test_single_target_fallback_unchanged` | Old single-target `target_combatant_id` (no list) still populates the headline `auto_save_*` fields AND `auto_save_targets` with 1 entry. |
| `test_aoe_list_with_pc_target_marks_pc_skipped` | AoE list with a PC token → PC entry has `pc_skipped: True`, `rolled: None`, `damage_applied: 0`, AND (v2.47.0) `pending_request_id` set so the cast card can correlate the eventual update broadcast. |
| `test_aoe_pc_response_applies_damage_and_broadcasts_update` | v2.47.0 Phase T.5d end-to-end: AoE cast at NPC+PC → PC submits the save → server applies save-for-half damage AND broadcasts `spell_cast_target_updated` with `cast_id`, `combatant_id`, `target_name`, `rolled`, `passed`, `damage_applied`, `damage_type`. v2.158.64 — the "PC's HP dropped" check moved from a `_pc_hp()` roster GET-poll to a `gm_ws.buffered("character_hp_update")` filter on the PC's `character_id` asserting the last HP-update broadcast has `delta < 0`; the `damage_applied >= -delta` cross-check uses the broadcast's delta as the load-bearing HP-change source. |
| `test_aoe_cast_without_targets_lands_pending_then_place_aoe_resolves` | v2.48.0 Phase T.5e caster-gated placement. `/cast_spell` without `target_combatant_ids` returns `pending_aoe_placement: True` + the spell's `area_shape`/`area_size_ft`. Then POST `/place_aoe` with the cast_id + target list resolves NPC saves + damage and broadcasts `spell_cast_aoe_resolved` with the resolved targets. |
| `test_place_aoe_auto_rolls_pc_save_and_applies_damage` | v2.48.3 — `/place_aoe` auto-rolls PC saves alongside NPCs (no more roll_request prompt for the new flow). PC entry has `rolled`/`passed`/`damage_applied` populated, `pc_skipped` and `pending_request_id` absent. v2.158.64 — the "PC's HP dropped server-side" check moved from a `_pc_hp()` roster GET-poll to a `gm_ws.buffered("character_hp_update")` filter on the PC's `character_id` (scoped by a `gm_ws.mark()` before `/place_aoe`) asserting the last HP-update broadcast has `delta < 0`. |
| `test_place_aoe_rejects_non_caster_non_gm` | v2.48.0 Phase T.5e auth gate. `/place_aoe` with a bogus cast_id returns 404 (stash-not-found). |

### `test_cast_lightning_bolt.py`
v2.159.14 magic-items-automation Phase 8n — first SPELL wired into the AoE-line confirm-modal substrate that v2.159.7-v2.159.13 built for items. The v2.44.0 cast_spell multi-target loop has been live for Fireball-sphere since then; this commit proves the loop also works for line-shape spells (Lightning Bolt). The accompanying UI work adds `_showAoEConfirmModal` between `_openAoePicker` and the `/cast_spell` POST for line-shape spells only.

| Test | What it asserts |
|------|-----------------|
| `test_lightning_bolt_hits_two_bandits` | Thalindra Lightning Bolt at 2 bandits → `auto_save_targets` has 2 entries, each with rolled/passed/damage_applied/damage_type, every bandit took non-zero lightning damage (8d6 min 8, half = min 4). Cast at slot_level=3 with override=True to skip action-economy gate. |

### `test_shake_awake.py`
v2.49.62 — `POST /shake_awake`. Closes the v2.49.61 filed "wake-via-shake" item. RAW Sleep's third wake branch: another creature uses an action to shake the sleeper awake. Any class can shake (RAW "someone"); costs 1 action. Scoped to Sleep-sourced Unconscious buffs only — shaking a dying-at-0-HP creature isn't a wake.

| Test | What it asserts |
|------|-----------------|
| `test_shake_awake_npc` | Pip shakes a Sleep'd bandit; assert `buffs_removed==1`, latest battle_update shows bandit without Unconscious, 🤚 log names both shaker + bandit. |
| `test_shake_awake_pc` | Pip shakes a Sleep'd Magnus; assert Unconscious dropped from both hub AND sheet mirror; 🤚 log names Pip + Magnus. |
| `test_shake_awake_not_asleep_no_buff` | Target has no Unconscious buff → 409 `not_asleep`. |
| `test_shake_awake_not_asleep_non_sleep_unconscious` | Target has generic Unconscious (no `source_spell==Sleep`) → 409 `not_asleep`. Regression guard: shaking a dying/knocked-out creature isn't a Sleep-wake. |

### `test_sleep_wake_on_damage.py`
v2.49.61 — closes the "wake-on-damage" filed item from v2.49.58. RAW Sleep wakes the sleeper on damage. The new `_wake_sleeping_on_damage` hook fires from both branches of `_apply_damage_to_combatant` after damage applies; scoped to buffs with `source_spell == "Sleep"` so other Unconscious sources (future knockout features etc.) aren't accidentally cleared. Same commit also fixes a pre-existing latent bug in `_resistance_halve` (crashed on condition buffs with `effects: list`; now skips non-dict effects).

| Test | What it asserts |
|------|-----------------|
| `test_wake_on_damage_npc` | Bandit pre-seeded with Sleep-Unconscious buff; Krieger attacks (auto_apply_damage on) → latest `battle_update` shows bandit's Unconscious dropped + 🌅 wake log fires. |
| `test_wake_on_damage_pc` | Magnus pre-seeded with Sleep-Unconscious buff; Krieger attacks → Unconscious dropped from BOTH hub and sheet mirror + 🌅 wake log names Magnus. |
| `test_non_sleep_unconscious_preserved` | Bandit pre-seeded with a generic Unconscious buff (no `source_spell == "Sleep"`); Krieger attacks → buff preserved (regression guard against over-broad clearing). |

### `test_attack_uplift_vs_label.py`
v2.99.190 — attack `damage_breakdown` suffix labels rider uplifts with "(vs NAME)" when the uplift dict carries `vs_combatant_id` (v2.99.188). The user-visible rendering path is the server-baked breakdown string; `tabletop.js` doesn't consume `auto_uplifts` directly. Closes the v2.99.188 UI follow-up.

| Test | What it asserts |
|------|-----------------|
| `test_attack_breakdown_labels_rider_vs_target` | Rowan marks Pip → attacks Pip → `damage_breakdown` contains "(vs Pip Quickfingers)" + the uplift's `vs_combatant_id` matches Pip's combatant ID. |
| `test_attack_breakdown_no_rider_no_vs_label` | Control: no Hunter's Mark in play → no "(vs ...)" suffix in `damage_breakdown` (non-rider uplifts like Rage / Colossus Slayer don't gain spurious labels). |

### `test_attack_multi_target.py`
v2.49.85 — `/attack` accepts `target_combatant_ids: list` in addition to `target_combatant_id`. Each list entry gets its own fresh attack + damage roll (RAW weapon attacks per-target). Per-target outcomes return in `auto_attack_targets`. Closes the v2.49.79 TODO's server side.

| Test | What it asserts |
|------|-----------------|
| `test_attack_legacy_single_target_emits_one_entry` | Legacy `target_combatant_id` still works; `auto_attack_targets` has 1 entry mirroring the legacy fields. |
| `test_attack_multi_target_fresh_rolls` | 3-entry list → 3 fresh per-target attack rolls + damage rolls. |
| `test_attack_multi_target_auto_apply_damage` | With `auto_apply_damage` on, each hit target's HP drops by its per-target damage_applied. |
| `test_attack_no_target_yields_empty_list` | Untargeted attack → `auto_attack_targets: []`. |

### `test_ruler_broadcast.py`
v2.49.84 — Phase 3E of the ruler/range plan. `POST /api/campaign/{cid}/ruler_broadcast` fans out the requester's ruler measurement to every connected campaign client. Auth: any campaign member. Server does no persistence; broadcast-only.

| Test | What it asserts |
|------|-----------------|
| `test_ruler_broadcast_show` | `{action: "show", points: [...], multi_segment: false}` → 200 + WS `ruler_broadcast` with `user_id`, `user_name`, `action="show"`, `points`, `multi_segment=false`. |
| `test_ruler_broadcast_show_multi_segment` | 4-point path + `multi_segment: true` → WS broadcast carries all 4 points + flag. |
| `test_ruler_broadcast_hide` | `{action: "hide"}` → 200 + WS broadcast with `action="hide"` and no points/multi_segment fields. |
| `test_ruler_broadcast_invalid_action` | Action other than `show` / `hide` → 400. |
| `test_ruler_broadcast_invalid_points_type` | Non-list `points` → 400. |
| `test_ruler_broadcast_non_member_403` | Non-existent campaign id → 403 (membership check fails). |

### `test_place_aoe_range.py`
v2.49.77 — Phase 3A of the ruler/range plan: server-side range enforcement on AoE casts via `/place_aoe`. The picker's chosen `center: {x, y}` is compared to the caster's token position vs the parsed spell range. Same three-tier override as Phase 2C (GM auto-bypass, player override + not strict, otherwise enforced). Tests use Bob (Thalindra's owner, non-GM) so the non-GM enforcement fires.

| Test | What it asserts |
|------|-----------------|
| `test_place_aoe_in_range_succeeds` | Thalindra at (100,100); Fireball center 50 ft away → 200 (well within 150 ft range). |
| `test_place_aoe_out_of_range_409` | Center 350 ft away → 409 `out_of_range` with `range_ft=150`, `distance_ft=350.0`, `spell_name="Fireball"`, `target_name="(AoE cast point)"`. |
| `test_place_aoe_override_bypasses_409` | Same out-of-range setup + `override_range=True` → 200. |
| `test_place_aoe_gm_bypasses_range_check` | gm_client places out-of-range AoE without `override_range` → 200 (auto-bypass). |

### `test_cast_attack_range.py`
v2.49.76 — Phase 2D of the ruler/range plan. Extends `_check_cast_range` to `/attack`, `/cast_hex`, `/use_stunning_strike`, `/use_open_hand_technique`. `/cast_sleep` is intentionally skipped (AoE multi-target — see endpoint comment + Phase 2C "When NOT to enforce"). Ownership limitation: only Pip (Alice's) and Thalindra (Bob's) are non-GM-owned in the demo, so the 409 path is directly testable only via `/attack`; the other three endpoints get integration-call-site happy-path coverage to confirm they don't break.

| Test | What it asserts |
|------|-----------------|
| `test_attack_in_range_succeeds` | Alice's Pip swings shortsword (5 ft) at a bandit 5 ft away → 200. |
| `test_attack_out_of_range_409` | Same setup, bandit 50 ft away → 409 `out_of_range` with `range_ft=5`, `distance_ft=50.0`, `spell_name="Shortsword"`. |
| `test_attack_thrown_long_range_uses_long_band` | Pip's Dagger (20/60 ft thrown) at a bandit ~50 ft away → 200. Pins `max_range_ft` collapsing the (20, 60) tuple to the long band. |
| `test_cast_hex_in_range_succeeds` | Magnus Hexes a bandit 5 ft away → 200. Hex range = 90 ft RAW; GM-owned caster so range auto-bypasses but the call site invocation is verified. |
| `test_stunning_strike_in_range_succeeds` | Kael's Stunning Strike on a bandit 5 ft away → 200. Melee 5 ft RAW. |
| `test_open_hand_technique_in_range_succeeds` | Kael's Open Hand Technique (no_reactions mode) on a bandit 5 ft away → 200. Melee 5 ft RAW. |

### `test_cast_spell_range.py`
v2.49.75 — Phase 2C of the ruler/range plan. New `_check_cast_range` helper + `override_range` body field on `/cast_spell` + 409 `out_of_range` response. Tests use Bob (Thalindra's owner, non-GM) so the non-GM enforcement paths fire; the GM-bypass test uses gm_client.

| Test | What it asserts |
|------|-----------------|
| `test_in_range_succeeds` | Thalindra at (100,100), bandit at +10 ft via test-NPC token; Bob casts Fire Bolt (120 ft) → 200. |
| `test_out_of_range_409` | Bandit at +350 ft; Bob casts Fire Bolt → 409 `out_of_range`. Response shape: `error`, `range_ft=120`, `distance_ft=350.0`, `spell_name="Fire Bolt"`, `source_name`, `target_name`. |
| `test_override_range_bypasses_409` | Same out-of-range setup + `override_range=True` → 200. Strict mode is off in the demo. |
| `test_gm_bypasses_range_check` | gm_client casts same out-of-range setup WITHOUT `override_range` → 200 (GM auto-bypass). |
| `test_self_range_skips_check` | Cast Shield (range=Self) → 200 regardless of any target position (parser returns 0 → check skips). |
| `test_off_map_target_skips_check` | Cast Fire Bolt at a synthesized target_name (no Token row on the active map) → 200 (helper returns None → check skips). |

### `test_cast_sleep_immunity.py`
v2.49.64 — closes the v2.49.58 "undead / charm-immune exclusion" filed item. RAW Sleep: "Undead and creatures immune to being charmed aren't affected by this spell." New `_is_sleep_immune` helper checks the target's monster template (NPCs) or character sheet (PCs) for `race contains "undead"` or `condition_immunities contains "charmed"`. Immune targets land in `unaffected` with `reason="undead"` or `reason="charm_immune"`. Same commit adds Skeleton (Undead) + Doppelganger (Monstrosity + charm-immune) templates to the demo seed + DB.

| Test | What it asserts |
|------|-----------------|
| `test_undead_excluded` | Skeleton + bandit targeted at L3. Skeleton lands in `unaffected` with `reason="undead"`; bandit still affected. |
| `test_charm_immune_excluded` | Doppelganger (non-undead but charm-immune) lands in `unaffected` with `reason="charm_immune"`. Regression guard that the two branches are distinct. |
| `test_regular_humanoid_still_affected` | Plain bandit (humanoid, no charm immunity) → affected, NOT in unaffected with an immunity reason. Regression guard against over-broad immunity filtering. |

### `test_cast_sleep_fey_ancestry.py`
v2.99.15 — (D) Phase 3 first-ship: Fey Ancestry magical sleep immunity. Extends `_is_sleep_immune._check_sheet` to read the race slug via `_race_slug_from_sheet` and return `(True, "fey-ancestry")` for `elf` / `half-elf` normalized slugs. Elf / Half-Elf / Wood Elf / High Elf / Dark Elf targets silently filter into `unaffected[]` with `reason: "fey-ancestry"` — RAW (PHB p.23): "magic can't put you to sleep."

| Test | What it asserts |
|------|-----------------|
| `test_elf_target_immune_via_fey_ancestry` | Lyra casts Sleep at Thalindra (Elf Wizard) at 5 HP under a 7d8 pool → Thalindra lands in `unaffected` with `reason="fey-ancestry"` (never counts against HP pool). |
| `test_half_elf_target_immune_via_fey_ancestry` | Lyra (Half-Elf Bard) targets herself with Sleep → same immunity gate. |
| `test_wood_elf_target_immune_via_fey_ancestry` | Mira (Wood Elf Druid) → confirms slug normalizer folds Wood Elf → elf. |
| `test_halfling_target_NOT_immune` | Control: Pip (Halfling) → affected, regression guard against over-broad immunity. |

### `test_relentless_endurance.py`
v2.99.17 — (D) Phase 3 second-ship: Half-Orc Relentless Endurance auto-clamp. `_apply_hp_change` reads the `relentless-endurance` resource (1/long-rest counter on Krieger's sheet); when damage drops the PC from alive → 0 HP AND the massive-damage rule didn't fire AND the resource is available, the function clamps `new_current = 1`, decrements the resource, and stays at `status="alive"`. Result dict carries `relentless_endurance_fired` / `relentless_endurance_damage` flags so `_apply_damage_to_combatant` can emit the `feature_used(source=relentless-endurance)` + `resource_update` broadcasts.

| Test | What it asserts |
|------|-----------------|
| `test_relentless_endurance_clamps_zero_to_one` | Krieger at 3 HP; Pip attacks; after a hit dealing ≥3 damage, the `character_hp_update` broadcast carries `current=1`, `resource_update` for `relentless-endurance` carries `current=0`, AND `feature_used(source=relentless-endurance)` broadcast fires for Krieger. |
| `test_relentless_endurance_skips_non_half_orc` | Control: Lyra at 3 HP; same attack setup; HP-update broadcast carries `current=0` (no clamp); no Relentless Endurance broadcast. Regression guard. |

### `test_savage_attacks.py`
v2.99.23 — Half-Orc Savage Attacks. `_compute_attack_auto_uplifts` extended with `is_crit` + `weapon_damage_expr` kwargs. When the attacker is Half-Orc + the hit is a crit + the damage type is physical (melee proxy via `_PHYSICAL_DAMAGE_TYPES`), the helper adds one extra die roll to the uplift list with `source="savage-attacks"`. Krieger's Greataxe (1d12) is the demo fixture.

| Test | What it asserts |
|------|-----------------|
| `test_savage_attacks_fires_on_half_orc_crit` | Krieger crits a Bandit (seeded d20=20) → `auto_uplifts` includes `{source="savage-attacks", expression="1d12"}` (the weapon's first die). |
| `test_savage_attacks_skips_non_half_orc` | Control: Garrik (Variant Human Champion Fighter) crits (d20 ∈ {19, 20}) → no Savage Attacks uplift. Regression guard. |

### `test_heavy_armor_speed_dwarf.py`
v2.397.0 — race-features plan Phase 3: Hill Dwarf heavy-armor speed bypass. New `_pc_heavy_armor_speed_penalty(sheet)` predicate + `_apply_heavy_armor_speed_penalty(base, sheet)` helper folded into `_speed_walk_from_sheet`. Dwarves are exempt regardless of STR (RAW PHB p.20); non-Dwarves wearing equipped heavy armor whose `_slug` ∈ `_HEAVY_ARMOR_STR_REQ` (chain-mail 13 / splint 15 / plate 15) lose 10 ft when STR < required. `/sheet-json` surfaces a `derived.heavy_armor_speed_penalty: {penalty_ft, source}` block only when the penalty fires.

| Test | What it asserts |
|------|-----------------|
| `test_dwarf_in_chain_mail_no_penalty` | Tavik (Hill Dwarf STR 14) in chain mail (STR req 13) → `derived` has no `heavy_armor_speed_penalty` key (STR ≥ req). |
| `test_dwarf_in_plate_no_penalty_via_race_exemption` | Tavik PATCHed into plate (STR req 15, STR 14 < 15) → `derived` STILL has no `heavy_armor_speed_penalty` key (Dwarf exemption). |
| `test_non_dwarf_in_plate_takes_penalty` | Tavik PATCHed to race "Human" + plate → `derived.heavy_armor_speed_penalty.penalty_ft = 10`; source mentions "plate". |
| `test_non_dwarf_sufficient_str_no_penalty` | Tavik PATCHed to race "Human" + plate + STR 15 → no penalty (STR ≥ req). Controls for the STR-threshold gate independently of the race gate. |

### `test_halfling_nimbleness.py`
v2.399.0 — race-features plan Phases 4a + 5a: Halfling Nimbleness + Naturally Stealthy recognition flags. Neither RAW PHB p.28 trait has a server-side enforcement substrate today (/token/move doesn't gate moving-through-creatures; /roll doesn't gate Stealth cover), so both Halfling exemptions are vacuously satisfied. v2.399.0 ships the **recognition half**: new `_pc_has_halfling_nimbleness(sheet)` + `_pc_has_naturally_stealthy(sheet)` predicates surface `derived.halfling_nimbleness` and `derived.naturally_stealthy` blocks on `/sheet-json` carrying the source citation + verbatim RAW clause + an `enforcement_status` string noting that Phases 4b + 5b (full enforcement) are filed for the future Maps 2.0 / Stealth-cover substrate arcs. Pip Quickfingers (Lightfoot Halfling Rogue) is the fixture; Krieger (Half-Orc) is the non-Halfling control.

| Test | What it asserts |
|------|-----------------|
| `test_halfling_recognition_flags_for_pip` | Pip's `/sheet-json` carries both `derived.halfling_nimbleness.applies = True` (PHB p.28 "Halfling race trait" source, Phase 4b enforcement filed) and `derived.naturally_stealthy.applies = True` (PHB p.28 "Lightfoot Halfling race trait" source, Phase 5b enforcement filed). |
| `test_halfling_recognition_flags_not_for_non_halfling` | Krieger's `derived` has neither `halfling_nimbleness` nor `naturally_stealthy`. Race-gate regression guard. |
| `test_halfling_recognition_carries_raw_clauses` | Both blocks include the verbatim RAW PHB p.28 clauses ("move through the space of any creature" / "obscured only by a creature"). Future refactors that drop these clauses silently would degrade the player-facing chat-card text; this guard catches the regression. |

### `test_check_artificers_lore.py`
v2.398.0 — race-features plan Phase 6: Rock Gnome Artificer's Lore. Twin of `test_check_stonecunning.py` shipped v2.396.0. New `_pc_has_artificers_lore(sheet)` race-gate predicate (any Gnome subrace via `_race_slug_from_sheet`) + new `POST /api/campaign/{cid}/check_artificers_lore` endpoint that rolls `1d20 + INT mod + 2 × PB` and broadcasts `feature_used(source=artificers-lore, …)`. Tavik PATCHed-to-Rock-Gnome is the test fixture since no demo PC ships as a Gnome today; the race is restored on test teardown.

| Test | What it asserts |
|------|-----------------|
| `test_artificers_lore_rolls_with_double_pb_for_gnome` | Tavik PATCHed to "Rock Gnome"; rolls; response total in [7, 26] (1d20 + 0 INT + 6 = 2 × PB 3); feature_used carries `source=artificers-lore`, `stat_key=history`, `stat_ability=INT`, math fields. |
| `test_artificers_lore_rejects_non_gnome` | Tavik (real seed = Hill Dwarf) → 409 `race_not_gnome` with `got_race` echo. Race-gate regression guard. |
| `test_artificers_lore_missing_character_id_400` | Body without `character_id` → 400. Input-gate regression guard. |
| `test_artificers_lore_echoes_note` | Tavik PATCHed to "Rock Gnome" + `note="Wand of Magic Detection"` → response carries note verbatim; feature_used `feature_desc` contains the note text. |

### `test_check_stonecunning.py`
v2.396.0 — race-features plan Phase 2: Hill Dwarf Stonecunning History check. New `_pc_has_stonecunning(sheet)` race-gate predicate + new `POST /api/campaign/{cid}/check_stonecunning` endpoint that rolls `1d20 + INT mod + 2 × PB` (RAW: double PB even when not proficient in History) and emits a `feature_used(source=stonecunning, stat_key=history, stat_ability=INT, …)` broadcast. Composes the PC's standing roll-state advantage/disadvantage. Tavik Stonebrow (Hill Dwarf Cleric Lv 8, INT 10, PB +3) is the demo fixture.

| Test | What it asserts |
|------|-----------------|
| `test_stonecunning_rolls_with_double_pb` | Tavik rolls; response total in [7, 26] (1d20 + 0 INT + 6 = 2 × PB 3); expression contains `+6`; feature_used broadcast carries `source=stonecunning`, `stat_key=history`, `stat_ability=INT`, `int_mod=0`, `proficiency_bonus=3`, `double_pb=6`. |
| `test_stonecunning_rejects_non_dwarf` | Pip (Lightfoot Halfling) → 409 `race_not_dwarf` with `got_race` echo. Race-gate regression guard. |
| `test_stonecunning_missing_character_id_400` | Body without `character_id` → 400. Input-gate regression guard. |
| `test_stonecunning_echoes_note` | Tavik with `note="Origin of these temple walls"` → response carries `note` verbatim; feature_used `feature_desc` contains the note text so the GM sees what stonework topic the player was rolling on. |

### `test_tiefling_hellish_rebuke_racial.py`
v2.395.0 — race-features plan Phase 1: Tiefling Infernal Legacy racial Hellish Rebuke. New `_pc_has_tiefling_hellish_rebuke_racial(sheet)` gate (Tiefling Lv 3+ AND `hellish-rebuke` resource current > 0) surfaces a parallel `cast-hellish-rebuke-racial` reaction option alongside the existing slot-based v2.71.0 path; picking the racial one consumes the resource (not a spell slot), broadcasts `resource_update` + `feature_used(source=hellish-rebuke-racial)`, and flips the reaction economy. Zara Emberfire (Tiefling Sorcerer Lv 5) is the demo fixture.

| Test | What it asserts |
|------|-----------------|
| `test_tiefling_racial_hellish_rebuke_consumes_resource_not_slot` | Zara at full racial resource (current=1) takes damage from Krieger; prompt offers BOTH `cast-hellish-rebuke` + `cast-hellish-rebuke-racial`; picking the racial path emits `resource_update` (hellish-rebuke → 0) + `feature_used(source=hellish-rebuke-racial, damage_expr=3d10, reaction_kind=race-feature)` + economy flip; NO `spell_slot_update` fires for Zara. |
| `test_tiefling_racial_hellish_rebuke_unavailable_at_zero` | Control: Zara at racial current=0 takes damage; prompt does NOT offer `cast-hellish-rebuke-racial` but still offers the slot-based `cast-hellish-rebuke` (slots untouched). Regression guard against over-broad gate. |

### `test_hellish_resistance.py`
v2.99.18 — (D) Phase 3 third-ship: Tiefling Hellish Resistance (sheet-level `damage_resistances` field on PCs). `_resistance_halve` extended to read the sheet root's `damage_resistances` list before walking buffs. Same field shape NPC templates already use. Zara Emberfire's demo sheet ships `damage_resistances: ["fire"]`.

| Test | What it asserts |
|------|-----------------|
| `test_tiefling_halves_fire_damage` | Thalindra casts Fire Bolt at Zara (Tiefling); deterministic seed lands a hit; `damage_applied == damage_total // 2` (resistance halving). |
| `test_no_resistance_for_non_tiefling` | Control: Fire Bolt at Pip (Halfling) → `damage_applied == damage_total` (no halving). Regression guard against over-broad resistance match. |

### `test_absorb_elements_resistance.py`
v2.158.48 — Phase 2 read site for the v2.71.0 Absorb Elements reaction buff (PHB p.211). `_resistance_halve` extended to read a buff's single `effects.resistance_damage_type` string (distinct from the `resistance_to` list) and halve matching damage. Not consumed — the buff's 1-round duration handles expiry. The next-melee-bonus-damage rider stays deferred for a future `/attack` read site.

| Test | What it asserts |
|------|-----------------|
| `test_absorb_elements_halves_matching_type` | Pip (Halfling, no innate fire resistance) carrying `absorb-elements-active` (resistance to fire); Thalindra's Fire Bolt hit is halved (`damage_applied == damage_total // 2`, `< damage_total`). |
| `test_absorb_elements_no_resistance_without_buff` | Control: Pip with no buff → Fire Bolt damage is not halved (`damage_applied == damage_total`). |

### `test_absorb_elements_melee_rider.py`
v2.158.49 — Phase 2 read site for the SECOND half of the v2.71.0 Absorb Elements reaction buff (PHB p.211): the +`next_melee_bonus_dice`d6 of `next_melee_bonus_type` on the carrier's first melee hit. New block (6b) in `_compute_attack_auto_uplifts` appends an `absorb-elements` uplift on a melee-weapon hit (gated on `_attack_is_melee_weapon`), stamped with a once-per-turn flag so it fires once and is stripped on a miss.

| Test | What it asserts |
|------|-----------------|
| `test_absorb_elements_rider_fires_on_melee_hit` | Sir Caelan carrying `absorb-elements-active` lands a Longsword (melee) hit on Krieger → `auto_uplifts` has an `absorb-elements` entry, `damage_type` "fire", `total` in [1, 6]. |
| `test_absorb_elements_rider_skipped_without_buff` | Control: Caelan with no buff → no `absorb-elements` uplift even on a melee hit. |
| `test_absorb_elements_rider_skipped_on_ranged_spell` | Melee gate: Thalindra carrying the buff casts Fire Bolt (ranged spell) → no `absorb-elements` uplift (proves the `_attack_is_melee_weapon` gate). |

### `test_devils_sight_resolver.py`
v2.158.50 — Phase 2 read site for the v2.158.14 Devil's Sight buff (Warlock invocation, PHB p.110). `_attacker_has_condition_disadvantage` now skips a darkness-sourced `blinded` condition (`_buff_is_darkness_sourced`: `effects.from_darkness: True` or a `source_spell`/`source` naming darkness) when the attacker carries `devils-sight-active` (`_pc_sees_in_darkness`). Other disadvantage conditions and non-darkness blindness are unaffected. The 120-ft range gate is not enforced (no positional distance yet); buff presence is the v1 signal.

| Test | What it asserts |
|------|-----------------|
| `test_devils_sight_negates_darkness_blinded_disadvantage` | Pip with a darkness-sourced `blinded` (`from_darkness: True`) + `devils-sight-active` → attack roll stays straight 1d20, `roll_state_applied` != `disadvantage_attacker_blinded`. |
| `test_darkness_blinded_without_devils_sight_imposes_disadvantage` | Control: darkness-blinded, no Devil's Sight → 2d20kl1 + `roll_state_applied` == `disadvantage_attacker_blinded`. |
| `test_devils_sight_does_not_cure_non_darkness_blindness` | Guard: Devil's Sight + a non-darkness `blinded` (no `from_darkness`) → disadvantage STILL applies (2d20kl1 + `disadvantage_attacker_blinded`). |

### `test_relentless_avenger_move.py`
v2.158.51 — Phase 2 read site for the v2.149.0 Relentless Avenger buff (Vengeance Paladin Lv 7+, PHB p.88). `move_token` (`/token/move`) reads `relentless-avenger-bonus-move` on the mover: suppresses OA triggers (the move doesn't provoke), exempts up to `free_movement_remaining_ft` from the over-speed cap, consumes the buff (single-use), and returns `relentless_avenger_applied`.

| Test | What it asserts |
|------|-----------------|
| `test_relentless_avenger_suppresses_oa_and_consumes_buff` | Caelan with the buff moves out of Tavik's reach (no `oa_confirmed`) → 200, `relentless_avenger_applied` True, empty `opportunity_attack_triggers`, and a `buff_update` removing the buff. |
| `test_move_provokes_oa_without_relentless_avenger` | Control: same move without the buff → 409 `oa_confirmation_required`. |
| `test_relentless_avenger_exempts_free_move_from_speed_cap` | At-cap combatant + buff moves +5 ft → 200 (free move exempt); identical drag without the buff → 409 `over_speed_cap`. |

### `test_eldritch_strike_resolver.py`
v2.158.54 — Phase 2 read site for the v2.99.268 Eldritch Strike buff (Eldritch Knight Fighter Lv 10+, PHB p.74). The new `_saver_has_eldritch_strike_vs_caster` helper reads the saver's combatant buffs for `eldritch-strike-target` and, when `effects.save_disadvantage_against_caster_id` matches the current caster, swaps the single-target PC save's `base_expression` d20 → 2d20kl1 (with RAW advantage-cancellation) and consumes the one-use buff. Closes the last Phase-8 straggler.

| Test | What it asserts |
|------|-----------------|
| `test_eldritch_strike_imposes_save_disadvantage_and_consumes` | Pip's combatant carries `eldritch-strike-target` naming Zara; Zara casts Hold Person at Pip → save `base_expression == "2d20kl1"`, a `feature_used(source="eldritch-strike")` consume broadcast fires, and the buff is dropped. Buff seeded directly on the saver's combatant; read site is class-agnostic (matches the saver's mark against the casting PC). |
| `test_eldritch_strike_no_disadvantage_for_other_caster` | Per-caster guard: the mark names a different caster id → save stays `1d20`, buff NOT consumed. |

### `test_vow_of_enmity_resolver.py`
v2.158.53 — Phase 2 read site for the v2.99.246 Vow of Enmity buff (Vengeance Paladin Lv 3+ CD, PHB p.88). The new `_attacker_has_vow_of_enmity_vs_target` helper reads the attacker's combatant buffs for `vow-of-enmity-active` and, when `effects.attack_advantage_vs_target_combatant_id` matches the current target, folds advantage onto the `/attack` d20 roll (label `advantage_vow_of_enmity`). Per-target match — advantage only vs the marked creature.

| Test | What it asserts |
|------|-----------------|
| `test_vow_of_enmity_grants_advantage_vs_marked_target` | Pip's combatant carries `vow-of-enmity-active` naming Tavik's combatant id → attack vs Tavik → `2d20kh1` + `roll_state_applied == "advantage_vow_of_enmity"`. Buff seeded directly on the attacker's combatant at PUT /battle (resolver reads hub combatant buffs). |
| `test_vow_of_enmity_no_advantage_vs_other_target` | Per-target guard: the vow names a different combatant id → attack vs Tavik stays a straight `1d20`, `roll_state_applied != "advantage_vow_of_enmity"`. |

### `test_cast_sleep_multi_class.py`
v2.49.63 — closes the "add Sleep to Bard / Sorcerer / Warlock lists" filed item. Seed-list backfill verified via one happy-path cast per class. Sleep is RAW on bard / sorcerer / warlock / wizard lists; pre-v2.49.63 only Thalindra (wizard) had it.

| Test | What it asserts |
|------|-----------------|
| `test_cast_sleep_bard` | Lyra (Bard) casts Sleep at L1 → `class_slug=bard`, `pool_expr=5d8`, single 5-HP bandit affected. |
| `test_cast_sleep_sorcerer` | Zara (Sorcerer) casts Sleep at L1 → `class_slug=sorcerer`, 5d8 pool, bandit affected. |
| `test_cast_sleep_warlock_l3` | Magnus (Warlock Lv 5, L3-only Pact Magic) casts at L3 → `pool_expr=9d8` (5 + 2*2), 9–72 pool range. |

### `test_cast_sleep.py`
v2.49.58 — `POST /cast_sleep`. RAW Sleep (1st-level enchantment, bard/sorcerer/warlock/wizard). Rolls 5d8 + 2d8 per slot level above 1st as an HP pool; affects creatures in ascending order of current HP, subtracting each affected creature's HP from the pool. No save, no concentration. Unconscious key is in `_INCAPACITATING_BUFF_KEYS`, so a PC sleeper drops their own concentration via the v2.49.51 hook. Dedicated endpoint (not `/cast_spell`) because the HP-pool targeting doesn't fit save-or-suck or save-for-half.

| Test | What it asserts |
|------|-----------------|
| `test_sleep_happy_path_npc` | Single 5-HP bandit at L1; 5d8 min=5 → always affected. Response shape: `pool_expr`, `pool_total`, `affected`, `unaffected`. |
| `test_sleep_ordering_invariant` | 3 bandits at 1/2/3 HP; affected list is non-decreasing by HP; sum(affected.hp) <= pool_total; first unaffected (if any) has hp > pool_remaining. Dice-independent. |
| `test_sleep_high_hp_skipped` | Bandit HP=50; 5d8 max=40 < 50 → always unaffected. |
| `test_sleep_already_unconscious_skipped` | Bandit pre-seeded with Unconscious buff is omitted from both `affected` and `unaffected` lists (RAW: ignored when ordering). |
| `test_sleep_drops_pc_concentration` | Magnus has Hex up (concentration); Magnus HP=5; Thalindra Sleeps Magnus. Asserts Unconscious lands on Magnus + Hex drops via v2.49.51 hook + 💀 GM log fires. |
| `test_sleep_upcast_scales_pool` | L3 slot → `pool_expr == "9d8"` (5 + 2 * 2). |
| `test_sleep_no_slot` | Drain Thalindra's 4 L1 slots; next call → 409 `no_slot`. Restores via long-rest at end to keep `test_cast_magic_missile` happy. |
| `test_sleep_wrong_class` | Krieger (Barbarian) → 409 `wrong_class` with `expected=wizard`. |

---

## Class features

### `test_use_rage.py`
Barbarian Rage install + end_buff (Phase C primitive sanity).

| Test | What it asserts |
|------|-----------------|
| `test_rage_happy_path` | `/use_rage` installs Rage buff; broadcast carries `feature_used`. |
| `test_rage_out_of_uses` | Calling beyond counter → 409. |
| `test_rage_wrong_class` | Non-Barbarian → 409. |
| `test_rage_missing_character_id` | Empty body → 400. |
| `test_end_buff_happy_path` | `/end_buff` removes Rage. |
| `test_end_buff_not_found` | Removing a buff that isn't installed → 404. |
| `test_end_buff_missing_fields` | Empty body → 400. |

### `test_use_second_wind.py`
Fighter Second Wind heal-roll (v2.34.x `dice_*` envelope).

| Test | What it asserts |
|------|-----------------|
| `test_second_wind_happy_path` | Rolls 1d10+lv, applies HP, decrements counter; `feature_used` includes `Second Wind` substring; broadcast carries v2.43.0 `heal_amount` + `heal_target_name` (== caster). |
| `test_second_wind_out_of_uses` | Counter exhausted → 409. |
| `test_second_wind_wrong_class` | Non-Fighter → 409. |
| `test_second_wind_missing_character_id` | Empty body → 400. |

### `test_use_action_surge.py`
Fighter Action Surge: refunds the action chip.

| Test | What it asserts |
|------|-----------------|
| `test_action_surge_happy_path` | Decrement counter + broadcast `feature_used`. |
| `test_action_surge_refunds_action_chip` | The `action` economy chip flips back to unused. |
| `test_action_surge_out_of_uses` | 409 when counter is empty. |
| `test_action_surge_wrong_class` | Non-Fighter → 409. |
| `test_action_surge_missing_character_id` | 400. |

### `test_use_dash.py`
v2.100.3 — `/use_dash` propagates the Dash movement-cap bonus to the authoritative hub state + broadcasts `economy_update` (carrying `dash_bonus_ft`) so the bonus survives a player's wholesale `battle_update` replace. Pip Quickfingers is the seeded fixture.

| Test | What it asserts |
|------|-----------------|
| `test_use_dash_propagates_dash_bonus` | Dash a seeded combatant → `economy_update` carries `slot=action`, `used=True`, `dash_bonus_ft=30`; `feature_used(source=dash-action)` fires; response echoes `dash_bonus_ft=30`. |
| `test_use_dash_stacks_additively` | A second Dash stacks the absolute bonus (30 → 60) rather than overwriting. |
| `test_use_dash_not_in_battle_no_economy_update` | Error path: dashing a character absent from init still fires `feature_used` but broadcasts NO `economy_update` and returns `dash_bonus_ft: null`. |

### `test_h3_invocations.py`
v2.99.250 — Phase H.3 batched 5-invocation breadth ship. Single `/use_invocation` endpoint backed by a 5-entry registry: Devil's Sight, Mask of Many Faces, Hex Warrior, Lifedrinker, Lance of Lethargy. Magnus Hexbinder (Warlock The Fiend Lv 5) is the fixture.

| Test | What it asserts |
|------|-----------------|
| `test_use_inv_devils_sight_happy` | Magnus Lv 5 → Devil's Sight (min Lv 2) succeeds; broadcast (source `eldritch-invocation`). |
| `test_use_inv_bad_slug` | Unknown slug → 400. |
| `test_use_inv_wrong_class` | Pip (Rogue) → 409 `wrong_class`. |
| `test_use_inv_lifedrinker_no_pact` | Magnus PATCH'd to Lv 12 (level prereq satisfied) but no `pact_boon == "blade"` → 409 `pact_prereq_unmet`. |
| `test_use_inv_lifedrinker_level_too_low` | Lifedrinker at Lv 5 (needs 12) → 409 `level_too_low`. |
| `test_use_inv_hex_warrior_wrong_subclass` | Magnus default subclass "The Fiend" → 409 `subclass_prereq_unmet` (Hex Warrior needs Hexblade). |

### `test_emissary_of_peace.py`
v2.99.275 — Redemption Paladin (XGE p.39) Emissary of Peace CD (H.2 depth). Bonus action self-buff: +5 Persuasion 10 min.

| Test | What it asserts |
|------|-----------------|
| `test_use_eop_happy` | Redemption Caelan → `persuasion_bonus == 5`, `duration_minutes == 10`, CD 1 → 0. |
| `test_use_eop_out_of_cd` | CD 0 → 409. |
| `test_use_eop_wrong_subclass` | Default Caelan (Devotion) → 409. |

### `test_rebuke_the_violent.py`
v2.99.249 — Oath of Redemption (Paladin subclass, XGE p.39) Rebuke the Violent reaction CD (Phase H.2 FIFTH + FINAL oath). Caelan PATCH'd to Redemption + CD 1/1 + Bandit attacker in battle. DC 14.

| Test | What it asserts |
|------|-----------------|
| `test_use_rtv_happy` | Rebuke a Bandit who dealt 15 dmg → `save_dc == 14`, `psychic_damage_on_fail == 15`, `psychic_damage_on_success == 7`, broadcast (source `rebuke-the-violent`). |
| `test_use_rtv_missing_damage` | No `damage_dealt` body → 400. |
| `test_use_rtv_zero_damage` | `damage_dealt: 0` → 400 (must be >= 1). |
| `test_use_rtv_attacker_not_in_battle` | Unknown attacker_combatant_id → 404. |
| `test_use_rtv_out_of_cd` | `channel-divinity.current = 0` → 409 `out_of_uses`. |
| `test_use_rtv_wrong_subclass` | Default Caelan (Devotion) → 409 `wrong_subclass_or_level`. |

### `test_peerless_athlete.py`
v2.99.276 — Glory Paladin (TCE p.55) Peerless Athlete CD (H.2 depth). Bonus action: 10 min advantage on Athletics + Acrobatics + +10 ft jump distance.

| Test | What it asserts |
|------|-----------------|
| `test_use_pa_happy` | Glory Caelan → `jump_bonus_ft == 10`, `duration_minutes == 10`, CD 1 → 0. |
| `test_use_pa_out_of_cd` | CD 0 → 409. |
| `test_use_pa_wrong_subclass` | Default Caelan (Devotion) → 409. |

### `test_inspiring_smite.py`
v2.99.248 — Oath of Glory (Paladin subclass, TCE p.55) Inspiring Smite bonus-action CD (Phase H.2 fourth oath). Rolls 2d8 + paladin level temp HP, divides evenly (remainder to first targets).

| Test | What it asserts |
|------|-----------------|
| `test_use_is_happy_two_targets` | 2 targets → `paladin_level == 7`, `total_temp_hp` in [9, 23], allocations sum equals total, broadcast. |
| `test_use_is_three_targets_remainder` | 3 targets → sum of allocations == total, first allocation >= last (remainder skew). |
| `test_use_is_empty_list` | Empty target list → 400. |
| `test_use_is_out_of_cd` | `channel-divinity.current = 0` → 409 `out_of_uses`. |
| `test_use_is_wrong_subclass` | Default Caelan (Devotion) → 409 `wrong_subclass_or_level`. |

### `test_aura_of_conquest.py`
v2.99.273 — Conquest Paladin (XGE p.37) Aura of Conquest passive (H.2 depth). Lv 7+ aura that reduces frightened creatures' speed to 0 + deals half-paladin-level psychic at turn start. Lv 18+ radius bumps 10 → 30 ft. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_aoc_happy_lv7` | Lv 7 Caelan → `radius_ft == 10`, `psychic_damage == 3`, broadcast (source `aura-of-conquest`). |
| `test_use_aoc_lv18_radius_upgrade` | Lv 18 Caelan → `radius_ft == 30`, `psychic_damage == 9`. |
| `test_use_aoc_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_aoc_level_gate` | Conquest at Lv 6 → 409. |

### `test_aura_of_warding.py`
v2.99.279 — Ancients Paladin (PHB p.87) Aura of Warding passive (H.2 depth). Lv 7+ aura: you + friendly creatures within have resistance to damage from spells. Lv 18+ radius bumps 10 → 30 ft. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_aow_happy_lv7` | Lv 7 Caelan → `radius_ft == 10`, broadcast (source `aura-of-warding`). |
| `test_use_aow_lv18_radius_upgrade` | Lv 18 Caelan → `radius_ft == 30`. |
| `test_use_aow_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_aow_level_gate` | Ancients at Lv 6 → 409. |

### `test_relentless_avenger.py`
v2.99.280 — Vengeance Paladin (PHB p.88) Relentless Avenger OA-rider (H.2 depth). Lv 7+: on OA hit, you can move up to half your speed as part of the same reaction without provoking OAs. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ra_happy_lv7` | Lv 7 Caelan (speed 30) → `bonus_move_ft == 15`, `base_speed == 30`, broadcast (source `relentless-avenger`). |
| `test_use_ra_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_ra_level_gate` | Vengeance at Lv 6 → 409. |

### `test_aura_of_the_guardian.py`
v2.99.281 — Redemption Paladin (XGE p.39) Aura of the Guardian reactive shield (H.2 depth). Lv 7+: when an ally within 10 ft (30 ft at Lv 18+) takes damage, you reaction-redirect the damage to yourself. Damage can't be reduced. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_aotg_happy_lv7` | Lv 7 Caelan → `radius_ft == 10`, broadcast (source `aura-of-the-guardian`). |
| `test_use_aotg_lv18_radius_upgrade` | Lv 18 Caelan → `radius_ft == 30`. |
| `test_use_aotg_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_aotg_level_gate` | Redemption at Lv 6 → 409. |

### `test_aura_of_alacrity.py`
v2.99.282 — Glory Paladin (XGE p.37) Aura of Alacrity speed aura (H.2 depth — CLOSES the H.2 Lv 7 batch). Lv 7+: your walking speed +10 ft permanently; allies starting their turn within 5 ft (10 ft at Lv 18+) get +10 ft walking speed until end of turn. Note: 5/10 radius is distinct from the 10/30 ft pattern of the other oath auras. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_aoa_happy_lv7` | Lv 7 Caelan → `radius_ft == 5`, `speed_bonus_ft == 10`, broadcast (source `aura-of-alacrity`). |
| `test_use_aoa_lv18_radius_upgrade` | Lv 18 Caelan → `radius_ft == 10` (RAW upgrade). |
| `test_use_aoa_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_aoa_level_gate` | Glory at Lv 6 → 409. |

### `test_undying_sentinel.py`
v2.99.283 — Ancients Paladin (PHB p.87) Undying Sentinel "drop to 1 HP, not 0" (H.2 deeper, Lv 15). Once-per-long-rest. Auto-bootstraps an `undying-sentinel` resource if missing; refilled by the generic long-rest resource hook. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_us_happy_lv15` | Lv 15 Caelan → `uses_remaining == 0`, broadcast (source `undying-sentinel`). |
| `test_use_us_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_us_level_gate` | Ancients at Lv 14 → 409. |
| `test_use_us_out_of_uses` | Second back-to-back call → 409 `no_uses_left`. |
| `test_use_us_long_rest_refills` | Use → long rest → use again → 200 (resource refilled). |

### `test_soul_of_vengeance.py`
v2.99.284 — Vengeance Paladin (PHB p.88) Soul of Vengeance reactive melee (H.2 deeper, Lv 15). When a Vow of Enmity target attacks, reaction → melee weapon attack against them. Costs a reaction chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_sov_happy_lv15` | Lv 15 Caelan → 200, broadcast (source `soul-of-vengeance`). |
| `test_use_sov_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_sov_level_gate` | Vengeance at Lv 14 → 409. |

### `test_scornful_rebuke.py`
v2.99.285 — Conquest Paladin (XGE p.37) Scornful Rebuke passive psychic counter (H.2 deeper, Lv 15). When a creature hits you with an attack, they take psychic damage = max(1, CHA mod). No chip — passive auto-trigger. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_sr_happy_lv15` | Lv 15 Caelan (CHA 16) → `psychic_damage == 3`, broadcast (source `scornful-rebuke`). |
| `test_use_sr_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_sr_level_gate` | Conquest at Lv 14 → 409. |

### `test_glorious_defense.py`
v2.99.286 — Glory Paladin (XGE p.38) Glorious Defense reactive AC bonus (H.2 deeper, Lv 15). When you or an ally within 10 ft is hit, reaction → +CHA mod (min +1) AC; if hit becomes miss, follow-up weapon attack on attacker. Costs a reaction chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_gd_happy_lv15` | Lv 15 Caelan (CHA 16) → `ac_bonus == 3`, broadcast (source `glorious-defense`). |
| `test_use_gd_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_gd_level_gate` | Glory at Lv 14 → 409. |

### `test_protective_spirit.py`
v2.99.287 — Redemption Paladin (XGE p.39) Protective Spirit self-heal (H.2 deeper, Lv 15 — CLOSES the H.2 Lv 15 batch). End of turn, if at half HP or less and not incapacitated: regain 1d6 + half-paladin-level HP. v1 announce-only — actual HP application is GM-tracked.

| Test | What it asserts |
|------|-----------------|
| `test_use_ps_happy_lv15` | Lv 15 Caelan → `die_rolled` in [1,6], `half_paladin_level == 7`, `heal_amount` in [8,13], broadcast (source `protective-spirit`). |
| `test_use_ps_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_ps_level_gate` | Redemption at Lv 14 → 409. |

### `test_elder_champion.py`
v2.99.288 — Ancients Paladin (PHB p.87) Elder Champion Lv 20 capstone transform (H.2 deeper). Once-per-long-rest. Auto-bootstraps an `elder-champion` resource if missing; refilled by long rest. Action chip + transform broadcast. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ec_happy_lv20` | Lv 20 Caelan → `uses_remaining == 0`, `turn_start_heal == 10`, `aura_radius_ft == 10`, `duration_minutes == 1`, broadcast (source `elder-champion`). |
| `test_use_ec_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_ec_level_gate` | Ancients at Lv 19 → 409. |
| `test_use_ec_out_of_uses` | Second back-to-back call → 409 `no_uses_left`. |
| `test_use_ec_long_rest_refills` | Use → long rest → use again → 200 (resource refilled). |

### `test_avenging_angel.py`
v2.99.289 — Vengeance Paladin (PHB p.88) Avenging Angel Lv 20 capstone transform (H.2 deeper). 1 hour: wings + fly 60 ft; 30 ft frightful aura (Wis save DC 8 + prof + CHA). Auto-bootstraps an `avenging-angel` resource if missing; refilled by long rest. Action chip + transform broadcast. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_aa_happy_lv20` | Lv 20 Caelan (stale prof 3, CHA 16) → `save_dc == 14`, `fly_speed_ft == 60`, `aura_radius_ft == 30`, `duration_minutes == 60`, broadcast (source `avenging-angel`). |
| `test_use_aa_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_aa_level_gate` | Vengeance at Lv 19 → 409. |
| `test_use_aa_long_rest_refills` | Use → long rest → use again → 200 (resource refilled). |

### `test_invincible_conqueror.py`
v2.99.290 — Conquest Paladin (XGE p.37) Invincible Conqueror Lv 20 capstone (H.2 deeper). 1 min: resistance to all damage, +1 extra attack on Attack action, melee weapon crits on 19-20. Auto-bootstraps `invincible-conqueror` resource if missing; refilled by long rest. Action chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ic_happy_lv20` | Lv 20 Caelan → `resistance_all_damage == True`, `extra_attack == 1`, `crit_range_min == 19`, `duration_minutes == 1`, broadcast (source `invincible-conqueror`). |
| `test_use_ic_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_ic_level_gate` | Conquest at Lv 19 → 409. |
| `test_use_ic_long_rest_refills` | Use → long rest → use again → 200 (resource refilled). |

### `test_living_legend.py`
v2.99.291 — Glory Paladin (XGE p.38) Living Legend Lv 20 capstone (H.2 deeper). Bonus action transform 1 min: advantage on CHA checks; 1/turn (up to 4 total) turn missed weapon attack into hit; once, reroll a failed save as reaction. Auto-bootstraps `living-legend` resource; refilled by long rest. Bonus chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ll_happy_lv20` | Lv 20 Caelan → `miss_to_hit_uses == 4`, `save_reroll_uses == 1`, `duration_minutes == 1`, broadcast (source `living-legend`). |
| `test_use_ll_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_ll_level_gate` | Glory at Lv 19 → 409. |
| `test_use_ll_long_rest_refills` | Use → long rest → use again → 200 (resource refilled). |

### `test_emissary_of_redemption.py`
v2.99.292 — Redemption Paladin (XGE p.39) Emissary of Redemption Lv 20 passive capstone (H.2 deeper — CLOSES the H.2 Lv 20 batch). Resistance to all damage from creatures + half-damage radiant counter on hit. Both negated against a creature you attack/spell/damage until next long rest. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_er_happy_lv20` | Lv 20 Caelan → `resistance_all_creature_damage == True`, `radiant_back_fraction == 0.5`, broadcast (source `emissary-of-redemption`). |
| `test_use_er_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_er_level_gate` | Redemption at Lv 19 → 409. |

### `test_corona_of_light.py`
v2.99.293 — Light Domain Cleric (PHB p.61) Corona of Light Lv 17 capstone (H.1 deeper — opens H.1 Lv 17 batch). Action: bright sunlight 60 ft + dim 30 ft beyond, 1 min, enemies in bright light have disadvantage on saves vs your fire/radiant spells. Action chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_col_happy_lv17` | Lv 17 Tavik → `bright_light_radius_ft == 60`, `dim_light_radius_ft == 90`, `duration_minutes == 1`, disadvantage types fire+radiant, broadcast (source `corona-of-light`). |
| `test_use_col_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_col_level_gate` | Light at Lv 16 → 409. |

### `test_stormborn.py`
v2.99.294 — Tempest Domain Cleric (PHB p.63) Stormborn Lv 17 passive (H.1 deeper). Fly speed = walking speed when not underground or indoors. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_sb_happy_lv17` | Lv 17 Tavik (dwarf speed 25) → `fly_speed_ft == 25`, `outdoor_only == True`, broadcast (source `stormborn`). |
| `test_use_sb_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_sb_level_gate` | Tempest at Lv 16 → 409. |

### `test_supreme_healing.py`
v2.99.295 — Life Domain Cleric (PHB p.61) Supreme Healing Lv 17 passive (H.1 deeper). When you would roll dice to restore HP with a spell, use max on each die instead. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_sh_happy_lv17` | Lv 17 Tavik → `max_dice_substitution == True`, broadcast (source `supreme-healing`). |
| `test_use_sh_wrong_subclass` | Light Domain Tavik at Lv 17 → 409. |
| `test_use_sh_level_gate` | Life at Lv 16 → 409. |

### `test_avatar_of_battle.py`
v2.99.296 — War Domain Cleric (PHB p.63) Avatar of Battle Lv 17 passive (H.1 deeper). Resistance to bludgeoning, piercing, slashing from nonmagical attacks. v2.158.0 (Phase 8 kick-off): the endpoint now installs a permanent `avatar-of-battle` buff carrying `effects.resistance_to = ["nonmagical-bludgeoning","nonmagical-piercing","nonmagical-slashing"]`; the F6 `_resistance_matches_damage` matcher (v2.63.0) halves nonmagical BPS damage through `_apply_damage_to_combatant` and skips magical attacks per RAW.

| Test | What it asserts |
|------|-----------------|
| `test_use_aob_happy_lv17` | Lv 17 Tavik → resistance_types BPS, `nonmagical_only == True`, `buff_installed == True`, broadcast (source `avatar-of-battle`). v2.158.0 — seeds Tavik into an active battle so `_install_buff` returns True. |
| `test_use_aob_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_aob_level_gate` | War at Lv 16 → 409. |
| `test_aob_buff_payload_carries_nonmagical_bps_resistance` | v2.158.0 — installed buff carries the three `nonmagical-X` resistance entries on `effects.resistance_to`; `concentration` falsy + `duration_rounds >= 1000` (permanent passive). |
| `test_aob_halves_nonmagical_piercing_damage` | v2.158.0 — end-to-end: Pip's nonmagical Shortsword (piercing) against the buffed Tavik produces `damage_applied == damage_total // 2` through `_apply_damage_to_combatant`. Retries up to 12 swings to bound hit-rate flake. Auto-apply-damage fixture. |

### `test_improved_reaper.py`
v2.99.297 — Death Domain Cleric (DMG p.97) Improved Reaper Lv 17 passive (H.1 deeper). 1st-5th level necromancy spells targeting one creature can target two creatures within range + within 5 ft of each other. v2.158.9 (Phase 8 final cleric-capstone commit, Phase 1 of install-then-deferred-read): endpoint installs a permanent `improved-reaper-active` buff carrying the six necromancy dual-target parameters as `effects.improved_reaper_*` flags. v2.158.41 (Phase 2): `/cast_spell` reads the flags via `_pc_improved_reaper_params` and surfaces an advisory `improved_reaper_eligible` + `improved_reaper_max_targets` on qualifying single-target Lv-1-5 necromancy casts (second-target damage stays GM-applied). **CLOSES the Lv-17 cleric subclass capstone batch 6/6.**

| Test | What it asserts |
|------|-----------------|
| `test_use_ir_happy_lv17` | Lv 17 Tavik → `max_targets == 2`, `max_target_separation_ft == 5`, school necromancy, levels 1-5, `buff_installed == True`, broadcast (source `improved-reaper`). v2.158.9 — seeds Tavik into an active battle so `_install_buff` returns True. |
| `test_use_ir_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_ir_level_gate` | Death at Lv 16 → 409. |
| `test_ir_buff_payload_carries_necromancy_dual_target_flags` | v2.158.9 — installed buff carries the six `improved_reaper_*` effect keys (active, min_spell_level=1, max_spell_level=5, school="necromancy", max_targets=2, max_target_separation_ft=5). Plus permanence sanity: `concentration` falsy + `duration_rounds >= 1000`. State-change contract (Phase 9). Pins the Phase-2 contract so the future `/cast_spell` read site has stable flag names to look up. |
| `test_ir_eligible_on_necromancy_cast` | v2.158.41 — Phase 2 read site: a Lv 17 Death Domain Tavik carrying `improved-reaper-active` who casts Inflict Wounds (Lv 1 necromancy, injected into the spell list for the test) sees `/cast_spell` return `improved_reaper_eligible == True` + `improved_reaper_max_targets == 2` + `improved_reaper_max_target_separation_ft == 5`. |
| `test_ir_not_eligible_on_non_necromancy_cast` | v2.158.41 — control: with the buff installed, casting Cure Wounds (evocation) reports `improved_reaper_eligible == False` + `improved_reaper_max_targets == 1`. Pins the school gate. |

### `test_improved_duplicity.py`
v2.99.298 — Trickery Domain Cleric (PHB p.62) Improved Duplicity Lv 17 passive (H.1 deeper). Invoke Duplicity now creates up to 4 duplicates (was 1). Bonus action moves any number up to 30 ft each, max 120 ft range. v2.158.3 (Phase 8 third commit): endpoint installs a permanent `improved-duplicity` buff carrying the upgraded Invoke Duplicity parameters as `effects.invoke_duplicity_max_duplicates=4` + `effects.invoke_duplicity_bonus_move_per_duplicate_ft=30` + `effects.invoke_duplicity_max_range_ft=120`. Phase 1 of the standard install-then-deferred-read split (Phase 2: `/use_invoke_duplicity` reads the flags off `_buffs_active` when shipped).

| Test | What it asserts |
|------|-----------------|
| `test_use_id_happy_lv17` | Lv 17 Tavik → `max_duplicates == 4`, `bonus_move_per_duplicate_ft == 30`, `max_range_ft == 120`, `buff_installed == True`, broadcast (source `improved-duplicity`). v2.158.3 — seeds Tavik into an active battle so `_install_buff` returns True. |
| `test_use_id_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_id_level_gate` | Trickery at Lv 16 → 409. |
| `test_id_buff_payload_carries_invoke_duplicity_flags` | v2.158.3 — installed buff carries the three `invoke_duplicity_*` flags on `effects` with the right values (4 / 30 / 120). Plus permanence sanity: `concentration` falsy + `duration_rounds >= 1000`. State-change contract (Phase 9). Pins the Phase-2 read contract so the future `/use_invoke_duplicity` endpoint has stable flag names to look up. |

### `test_invoke_duplicity.py`
v2.158.52 — Trickery Domain Cleric (PHB p.62) Invoke Duplicity Lv 2 Channel Divinity + the Phase 2 read site for the v2.158.3 `improved-duplicity` upgrade buff. The new `/use_invoke_duplicity` endpoint costs 1 CD use + an action and installs a 10-round concentration `invoke-duplicity-active` buff. Before installing, it walks the caster's combatant buffs for `improved-duplicity` and reads `effects.invoke_duplicity_max_duplicates` (4) instead of the Lv-2 baseline of 1 — flipping that previously install-only buff to consumed. Closes the last Phase-8 install-then-deferred-read gap.

| Test | What it asserts |
|------|-----------------|
| `test_use_invoke_duplicity_happy_lv2` | Lv 2 Trickery Tavik → `duplicates == 1`, `improved == False`, `bonus_move_per_duplicate_ft == 30`, `max_range_ft == 120`, `cleric_level == 2`, `channel_divinity_remaining == 1`, `buff_installed == True`, plus a `feature_used` broadcast (source `invoke-duplicity`) carrying `duplicates == 1`. Seeds Tavik into an active battle so `_install_buff` returns True; passes `override: true` to bypass the action-economy gate. |
| `test_use_invoke_duplicity_reads_improved_buff_lv17` | Phase 2 read: at Lv 17, calls `/use_improved_duplicity` first to install the upgrade buff, then `/use_invoke_duplicity` → `duplicates == 4`, `improved == True` (the read off `improved-duplicity.effects.invoke_duplicity_max_duplicates`), broadcast `duplicates == 4`. |
| `test_use_invoke_duplicity_out_of_cd` | Channel Divinity drained to 0 → 409 `out_of_uses`. |
| `test_use_invoke_duplicity_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_saint_of_forge_and_fire.py`
v2.99.299 — Forge Domain Cleric (XGE p.18) Saint of Forge and Fire Lv 17 passive (H.1 deeper). Fire immunity + (while wearing heavy armor) resistance to BPS from nonmagical attacks. v2.158.2 (Phase 8 follow-up to Avatar of Battle): the endpoint now installs a permanent `saint-of-forge-and-fire` buff carrying both `effects.immunity_to=["fire"]` (read by `_immunity_zero`) and `effects.resistance_to=["nonmagical-bludgeoning","nonmagical-piercing","nonmagical-slashing"]` (read by the v2.158.1-upgraded `_resistance_halve`).

| Test | What it asserts |
|------|-----------------|
| `test_use_sff_happy_lv17` | Lv 17 Tavik → `fire_immunity == True`, `heavy_armor_bps_resistance == True`, BPS in `resistance_types`, `buff_installed == True`, broadcast (source `saint-of-forge-and-fire`). v2.158.2 — seeds Tavik into an active battle so `_install_buff` returns True. |
| `test_use_sff_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_sff_level_gate` | Forge at Lv 16 → 409. |
| `test_sff_buff_payload_carries_fire_immunity_and_bps_resistance` | v2.158.2 — installed buff carries BOTH `effects.immunity_to=["fire"]` AND `effects.resistance_to` with the three `nonmagical-X` entries. Plus permanence sanity: `concentration` falsy + `duration_rounds >= 1000`. State-change contract (Phase 9). |

### `test_keeper_of_souls.py`
v2.99.300 — Grave Domain Cleric (XGE p.19) Keeper of Souls Lv 17 (H.1 deeper). When enemy within 60 ft dies, you or one creature within 60 ft heals HP = enemy's HD. 1/turn. v2.158.4 (Phase 8 fourth commit, Phase 1 of install-then-deferred-read): endpoint installs a permanent `keeper-of-souls-watcher` buff carrying `effects.keeper_of_souls_watcher: True` + `effects.keeper_of_souls_radius_ft: 60`. Phase 2 (deferred): on-death hook in `_apply_damage_to_combatant`'s NPC branch reads the buff + auto-heals the watcher for the dying NPC's HD count.

| Test | What it asserts |
|------|-----------------|
| `test_use_ks_happy_lv17` | Lv 17 Tavik, enemy HD 5 → `heal_amount == 5`, `max_range_ft == 60`, `buff_installed == True`, broadcast (source `keeper-of-souls`). v2.158.4 — seeds Tavik into an active battle so `_install_buff` returns True. |
| `test_use_ks_default_hd_clamp` | Missing `enemy_hit_dice` → `heal_amount == 1` (clamp). v2.158.4 — also seeds the battle so the install fires. |
| `test_use_ks_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_ks_level_gate` | Grave at Lv 16 → 409. |
| `test_ks_buff_payload_carries_watcher_flag_and_radius` | v2.158.4 — installed buff carries `effects.keeper_of_souls_watcher: True` + `effects.keeper_of_souls_radius_ft: 60`. Plus permanence sanity: `concentration` falsy + `duration_rounds >= 1000`. State-change contract (Phase 9). Pins the Phase-2 contract so the future on-death hook has stable flag names to look up. |
| `test_ks_on_death_hook_heals_watcher_when_npc_dies` | v2.158.6 — end-to-end Phase 2: seeds Tavik (Grave Lv 17 with watcher buff + low HP) + Pip + 1-HP SRD bandit, Pip kills the bandit, asserts a `keeper-of-souls-trigger` broadcast fires naming Tavik with `enemy_hit_dice == 2` (SRD bandit `2d8`) + `heal_amount == 2`. v2.158.63 — replaces the bracketing `GET /character/{id}` HP-poll with a `gm_ws.buffered("character_hp_update")` filter that asserts at least one HP-update broadcast fired for Tavik and the last one carries `delta == 2`, so the test pins the WS contract live clients actually subscribe to. Off-grid (no Token rows for the bandit) so the range gate falls through to the off-grid fallback. |

### `test_visions_of_the_past.py`
v2.99.301 — Knowledge Domain Cleric (PHB p.60) Visions of the Past Lv 17 (H.1 deeper). 1 min meditation → dream-like glimpses of recent events. Concentration up to WIS-score minutes. Modes: object (24h held-object history) or area (50-ft cube 24h history). Auto-bootstraps `visions-of-the-past` resource (max=1, reset=short). v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_vp_object_mode` | Lv 17 Tavik (WIS 16), object mode → `mode == "object"`, `max_duration_minutes == 16`, broadcast (source `visions-of-the-past`). |
| `test_use_vp_area_mode` | Area mode → `mode == "area"`. |
| `test_use_vp_default_mode` | Missing mode → defaults to "object". |
| `test_use_vp_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_vp_level_gate` | Knowledge at Lv 16 → 409. |
| `test_use_vp_out_of_uses` | Back-to-back → 409 `no_uses_left`. |

### `test_master_of_nature.py`
v2.99.302 — Nature Domain Cleric (PHB p.62) Master of Nature Lv 17 (H.1 deeper). Bonus action to verbally command beasts/plants charmed by your Charm Animals and Plants CD. Costs bonus chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_mon_happy_lv17` | Lv 17 Tavik → 200, broadcast (source `master-of-nature`). |
| `test_use_mon_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_mon_level_gate` | Nature at Lv 16 → 409. |

### `test_expansive_bond.py`
v2.99.303 — Peace Domain Cleric (TCE p.39) Expansive Bond Lv 17 (H.1 deeper — CLOSES the H.1 Lv 17 batch). Emboldening Bond now works within 60 ft between bonded creatures (was 30); d4 bonus becomes d6. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_eb_happy_lv17` | Lv 17 Tavik → `bond_radius_ft == 60`, `bonus_die == "d6"`, broadcast (source `expansive-bond`). |
| `test_use_eb_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_eb_level_gate` | Peace at Lv 16 → 409. |

### `test_arcane_mastery.py`
v2.99.304 — Arcana Domain Cleric (SCAG p.125) Arcane Mastery Lv 17 (H.1 deeper extension to 12/13 domains). Add 4 spells (one each of Lv 6/7/8/9) from any class as domain spells — always prepared, count as cleric spells. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_am_happy_lv17` | Lv 17 Tavik → `added_spell_count == 4`, `added_spell_levels == [6, 7, 8, 9]`, `source_class == "any"`, broadcast (source `arcane-mastery`). |
| `test_use_am_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_am_level_gate` | Arcana at Lv 16 → 409. |

### `test_orders_wrath.py`
v2.99.305 — Order Domain Cleric (TCE p.40) Order's Wrath Lv 17 (H.1 deeper — CLOSES H.1 Lv 17 FULL BATCH 13/13). When you Divine Strike, curse target until start of next turn; next ally-hit triggers 2d8 psychic and ends curse. Once per turn. v2.158.5 (Phase 8 fifth commit): when `target_combatant_id` supplied, endpoint installs an `orders-wrath-curse` buff on the target combatant via `_install_buff_on_combatant_id` carrying `effects.orders_wrath_psychic_damage_expression="2d8"` + `effects.orders_wrath_caster_char_id=<cleric.id>` + `effects.orders_wrath_active=True`, duration 2 rounds. Phase 2 (deferred): `/attack` flow detects ally-vs-cursed-target → deals 2d8 psychic + drops the curse. When no target supplied, falls back to historical announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ow_happy_lv17` | Lv 17 Tavik → `psychic_damage_expression == "2d8"`, `expires_on == "next_turn_start"`, broadcast (source `orders-wrath`). |
| `test_use_ow_with_target` | v2.158.5 — bogus `target_combatant_id` "tok_test" → response passes the id through + `curse_installed == False` (no matching combatant in battle). |
| `test_use_ow_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_ow_level_gate` | Order at Lv 16 → 409. |
| `test_ow_installs_curse_on_real_target_combatant` | v2.158.5 — seeds Tavik+Pip battle, calls endpoint with Pip's tok as `target_combatant_id` → `curse_installed: True` + `battle_update` broadcast shows Pip carrying the `orders-wrath-curse` buff with the three `orders_wrath_*` effect keys + the 2-round duration + non-concentration. State-change contract (Phase 9). Uses Pip as a stand-in target (Phase 2's ally-vs-caster filter is what would skip self-hits at trigger time). |
| `test_ow_ally_hit_on_cursed_npc_triggers_psychic_and_drops_curse` | v2.158.8 — end-to-end Phase 2: seeds Tavik (Order Lv 17) + Pip + 50-HP bandit, installs the curse on the bandit via the v2.158.5 endpoint, Pip hits the bandit, asserts (1) an `orders-wrath-trigger` broadcast fires naming Tavik with `psychic_damage` in [2, 16], (2) the curse buff is absent from the bandit's buffs in the latest battle_update (drop verified). High-HP bandit so 2d8 psychic doesn't kill outright; auto-apply-damage fixture. |

### `test_thief_features.py`
v2.99.224 — Thief Rogue (PHB p.97) Fast Hands (Lv 3) + Supreme Sneak (Lv 9) (E.4 Rogue batch). Fast Hands: Cunning Action bonus can drive a Sleight of Hand check / thieves' tools / Use an Object (announce + bonus-chip mark). Supreme Sneak: `/use_supreme_sneak` installs the `supreme-sneak-active` buff (+5 Stealth advantage proxy, `consume_on_stealth_roll`). v2.158.45 (Phase 2): the `/roll` Stealth post-result intercept consumes `supreme-sneak-active` (+5 to total, breakdown + note suffix, buff removed), mirroring the Hide in Plain Sight consumer.

| Test | What it asserts |
|------|-----------------|
| `test_use_fast_hands_sleight_of_hand` | Pip Lv 7 → `/use_fast_hands` sleight-of-hand → 200, `mode == "sleight-of-hand"`, broadcast (source `fast-hands`). |
| `test_use_fast_hands_bad_mode` | Bad mode `pickpocket` → 400. |
| `test_use_fast_hands_wrong_class` | Krieger (Barbarian) → 409 `wrong_subclass_or_level`. |
| `test_use_supreme_sneak_at_lv9` | Pip PATCH'd to Lv 9 → `/use_supreme_sneak` → 200, `stealth_bonus == 5`, `buff_installed == True`, broadcast (source `supreme-sneak`). |
| `test_supreme_sneak_consumes_on_stealth_roll` | v2.158.45 — Phase 2 read site: install the buff (Pip Lv 9), roll a Stealth check → total gets +5 + breakdown mentions "Supreme Sneak"; a second Stealth roll gets no bonus (one-shot consume). |
| `test_use_supreme_sneak_level_gate` | Control: Pip at Lv 7 → 409 `wrong_subclass_or_level`. |

### `test_assassinate.py`
v2.99.306 — Assassin Rogue (PHB p.97) Assassinate Lv 3+ (E.3 Rogue subclass batch opener — pivoted after Thief Fast Hands was found already wired in v2.99.224). Advantage vs creatures that haven't taken a turn; auto-crit vs surprised. No chip — passive declaration. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ass_happy_lv7` | PATCH Pip → Assassin Lv 7 → `advantage_vs_pre_turn == True`, `auto_crit_vs_surprised == True`, broadcast (source `assassinate`). |
| `test_use_ass_wrong_subclass` | Default Pip (Thief) → 409. |
| `test_use_ass_level_gate` | Assassin at Lv 2 → 409. |

### `test_fancy_footwork.py`
v2.99.307 — Swashbuckler Rogue (XGE p.47) Fancy Footwork Lv 3+ (E.3 Rogue batch). On a melee attack against a creature, that creature can't make OAs against you for the rest of your turn. No chip — passive on melee attack. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ff_happy_lv7` | PATCH Pip → Swashbuckler Lv 7 → `oa_suppressed_until == "end_of_turn"`, broadcast (source `fancy-footwork`). |
| `test_use_ff_with_target` | Optional `target_combatant_id` passes through. |
| `test_use_ff_wrong_subclass` | Default Pip (Thief) → 409. |
| `test_use_ff_level_gate` | Swashbuckler at Lv 2 → 409. |
| `test_ff_installs_block_buff_on_target` | v2.148.0 Phase 1 — targeting Tavik installs a 1-round `fancy-footwork-blocked` buff carrying `effects.fancy_footwork_blocked_against_char_id == pip.id`; `buff_installed: True` + `battle_update` shows the buff. |
| `test_ff_block_suppresses_watcher_oa` | v2.158.38 Phase 2 — a watcher marked against the mover provokes NO OA when the swashbuckler leaves reach (mark suppresses the trigger). |
| `test_ff_block_only_suppresses_named_char` | v2.158.38 specificity control — a mark naming a different char still lets the OA fire when the mover leaves reach. |

### `test_master_of_tactics.py`
v2.99.308 — Mastermind Rogue (XGE p.46) Master of Tactics Lv 3+ (E.3 Rogue batch). Bonus action Help; when helping an ally attack, target can be within 30 ft of you (not 5 ft) if it can see/hear you. Costs bonus chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_mt_happy_lv7` | PATCH Pip → Mastermind Lv 7 → `help_action_economy == "bonus"`, `help_target_range_ft == 30`, broadcast (source `master-of-tactics`). |
| `test_use_mt_wrong_subclass` | Default Pip (Thief) → 409. |
| `test_use_mt_level_gate` | Mastermind at Lv 2 → 409. |

### `test_skirmisher.py`
v2.99.309 — Scout Rogue (XGE p.46) Skirmisher Lv 3+ (E.3 Rogue batch). Reaction to move up to half speed when enemy ends turn within 5 ft; no OA. Costs reaction chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_sk_happy_lv7` | PATCH Pip → Scout Lv 7 (halfling speed 25) → `bonus_move_ft == 12`, `no_oa == True`, broadcast (source `skirmisher`). |
| `test_use_sk_wrong_subclass` | Default Pip (Thief) → 409. |
| `test_use_sk_level_gate` | Scout at Lv 2 → 409. |

### `test_insightful_fighting.py`
v2.99.310 — Inquisitive Rogue (XGE p.45) Insightful Fighting Lv 3+ (E.3 Rogue batch). Bonus action Wis (Insight) vs target Cha (Deception). On win, Sneak Attack without advantage (still blocked by disadvantage) for 1 min or until used vs different target. Costs bonus chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_if_happy_lv7` | PATCH Pip → Inquisitive Lv 7 → `duration_minutes == 1`, broadcast (source `insightful-fighting`). |
| `test_use_if_with_target` | Optional `target_combatant_id` passes through. |
| `test_use_if_wrong_subclass` | Default Pip (Thief) → 409. |
| `test_use_if_level_gate` | Inquisitive at Lv 2 → 409. |

### `test_psychic_blades.py`
v2.99.311 — Soulknife Rogue (TCE p.62) Psychic Blades Lv 3+ (E.3 Rogue batch). Bonus action to manifest Psychic Blades in each free hand. Simple melee + thrown (60/120 ft), 1d6 psychic, finesse + light. Counts as monk weapon. Usable with Sneak Attack. Costs bonus chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_pb_happy_lv7` | PATCH Pip → Soulknife Lv 7 → `damage_expression == "1d6"`, `damage_type == "psychic"`, `thrown_range_ft == [60, 120]`, properties include finesse/light/thrown, `counts_as_monk_weapon == True`, broadcast (source `psychic-blades`). |
| `test_use_pb_wrong_subclass` | Default Pip (Thief) → 409. |
| `test_use_pb_level_gate` | Soulknife at Lv 2 → 409. |

### `test_whispers_of_the_dead.py`
v2.99.312 — Phantom Rogue (TCE p.61) Whispers of the Dead Lv 3+ (E.3 Rogue batch — CLOSES the batch 8/8). On each rest, choose one skill or tool proficiency; you have that prof until next rest. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_wd_happy_lv7` | PATCH Pip → Phantom Lv 7 with explicit "Arcana" prof → `proficiency_name == "Arcana"`, `expires_on == "next_rest"`, broadcast (source `whispers-of-the-dead`). |
| `test_use_wd_default_prof` | Missing `proficiency_name` → fallback string with "unspecified". |
| `test_use_wd_wrong_subclass` | Default Pip (Thief) → 409. |
| `test_use_wd_level_gate` | Phantom at Lv 2 → 409. |

### `test_bonus_cantrip.py`
v2.99.313 — Land Druid (PHB p.68) Bonus Cantrip Lv 2+ (E.4 Druid subclass batch opener). +1 druid cantrip of your choice. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_bc_happy_lv5` | PATCH Mira → Land Lv 5 with "Shillelagh" → `cantrip_name == "Shillelagh"`, `added_cantrip_count == 1`, broadcast (source `bonus-cantrip`). |
| `test_use_bc_default_name` | Missing `cantrip_name` → fallback string with "unspecified". |
| `test_use_bc_wrong_subclass` | Default Mira (Moon) → 409. |
| `test_use_bc_level_gate` | Land at Lv 1 → 409. |

### `test_natural_recovery.py`
v2.99.314 — Land Druid (PHB p.68) Natural Recovery Lv 2+ (E.4 Druid batch). During short rest, recover spell slots totaling ceil(druid level / 2) levels (max Lv 5). Once per long rest. Auto-bootstraps `natural-recovery` resource. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_nr_happy_lv5` | PATCH Mira → Land Lv 5 → `recoverable_level_pool == 3`, `max_slot_level == 5`, broadcast (source `natural-recovery`). |
| `test_use_nr_wrong_subclass` | Default Mira (Moon) → 409. |
| `test_use_nr_level_gate` | Land at Lv 1 → 409. |
| `test_use_nr_out_of_uses` | Back-to-back → 409 `no_uses_left`. |
| `test_use_nr_long_rest_refills` | Use → long rest → use again → 200. |

### `test_spirit_totem.py`
v2.99.315 — Shepherd Druid (XGE p.24) Spirit Totem Lv 2+ (E.4 Druid batch). Bonus action to summon Bear/Hawk/Unicorn spirit at point within 60 ft. 30-ft aura, 1 min. Bear = 5+druid_lv temp HP to allies in aura; Hawk = reaction ally-attack advantage; Unicorn = heal-spell rider HP = druid level. Once per short or long rest. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_st_happy_lv5_bear` | PATCH Mira → Shepherd Lv 5 default Bear → `bear_temp_hp == 10`, `aura_radius_ft == 30`, broadcast (source `spirit-totem`). |
| `test_use_st_hawk` | spirit="hawk" passes through. |
| `test_use_st_unicorn` | spirit="unicorn" → `unicorn_heal_bonus == 5`. |
| `test_use_st_wrong_subclass` | Default Mira (Moon) → 409. |
| `test_use_st_level_gate` | Shepherd at Lv 1 → 409. |
| `test_use_st_out_of_uses` | Back-to-back → 409 `no_uses_left`. |

### `test_star_map.py`
v2.99.316 — Stars Druid (TCE p.37) Star Map Lv 2+ (E.4 Druid batch). Star chart focus + Guidance & Guiding Bolt always prepared. Guiding Bolt castable WIS_mod times (min 1) per long rest without slot. v2.158.13 (Phase 8 Druid diversification — first Druid subclass feature flipped to tracked): endpoint installs a permanent `star-map-active` buff with three `star_map_*` effect keys + auto-bootstraps a `guiding-bolt-charges` resource on the sheet (delivering on the original v2.99.316 docstring promise). v2.158.43 (Phase 2): `/cast_spell` reads the buff's `star_map_free_guiding_bolt_uses_max` effect via `_pc_star_map_free_guiding_bolt_charges` on a Guiding Bolt cast and surfaces a free-cast advisory (slot suppression stays player/GM-driven; the buff effect is read instead of the `guiding-bolt-charges` resource, which `normalize_dnd5e_sheet` drops).

| Test | What it asserts |
|------|-----------------|
| `test_use_sm_happy_lv5` | PATCH Mira → Stars Lv 5 (WIS 17 mod 3) → `free_guiding_bolt_uses == 3`, always_prepared includes Guidance + Guiding Bolt, `buff_installed == True`, `resource_bootstrapped` present in response. v2.158.13 — seeds Mira into an active battle so `_install_buff` returns True. |
| `test_use_sm_wrong_subclass` | Default Mira (Moon) → 409. |
| `test_use_sm_level_gate` | Stars at Lv 1 → 409. |
| `test_sm_buff_payload_carries_parameter_flags` | v2.158.13 — installed buff carries the three `star_map_*` effect keys (active=True, free_guiding_bolt_uses_max=3, always_prepared list with Guidance + Guiding Bolt). Plus permanence sanity: `concentration` falsy + `duration_rounds >= 1000`. State-change contract (Phase 9). Pins the Phase-2 contract so the future `/cast_spell` read site has stable flag names to look up. |
| `test_sm_cast_guiding_bolt_surfaces_free_cast` | v2.158.43 — Phase 2 read site: a Lv 5 Stars Mira carrying `star-map-active` (resource at 3) who casts Guiding Bolt (injected into the spell list) sees `/cast_spell` return `star_map_free_guiding_bolt == True` + `star_map_guiding_bolt_charges_remaining == 3`. |
| `test_sm_free_cast_not_surfaced_on_other_spell` | v2.158.43 — control: with the buff + charges, casting Druidcraft reports `star_map_free_guiding_bolt == False` + `star_map_guiding_bolt_charges_remaining == 0`. Pins the spell gate. |

### `test_halo_of_spores.py`
v2.99.317 — Spores Druid (TCE p.36) Halo of Spores Lv 2+ (E.4 Druid batch). Reaction when creature moves into or starts turn within 10 ft → necrotic damage on failed CON save. Die scales 1d4/1d6/1d8/1d10 at Lv 2/6/10/14. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_hs_happy_lv5` | PATCH Mira → Spores Lv 5 (WIS 17 prof 3) → `damage_expression == "1d4"`, `save_dc == 14`, `save_ability == "CON"`, `aura_radius_ft == 10`, broadcast (source `halo-of-spores`). |
| `test_use_hs_lv6` | Lv 6 → `damage_expression == "1d6"`. |
| `test_use_hs_lv14` | Lv 14 → `damage_expression == "1d10"`. |
| `test_use_hs_wrong_subclass` | Default Mira (Moon) → 409. |
| `test_use_hs_level_gate` | Spores at Lv 1 → 409. |

### `test_summon_wildfire_spirit.py`
v2.99.318 — Wildfire Druid (TCE p.38) Summon Wildfire Spirit Lv 2+ (E.4 Druid batch). Action + Wild Shape (default) or Lv 2+ spell slot to summon Wildfire Spirit for 1 hour. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ws_happy_lv5_default` | PATCH Mira → Wildfire Lv 5 default → `resource_used == "wild-shape"`, `duration_minutes == 60`, broadcast (source `summon-wildfire-spirit`). |
| `test_use_ws_slot_variant` | slot_level 3 → `resource_used == "spell-slot"`, `slot_level == 3`. |
| `test_use_ws_wrong_subclass` | Default Mira (Moon) → 409. |
| `test_use_ws_level_gate` | Wildfire at Lv 1 → 409. |

### `test_balm_of_the_summer_court.py`
v2.99.319 — Dreams Druid (XGE p.23) Balm of the Summer Court Lv 2+ (E.4 Druid batch). Pool of d6 fey energy = druid_lv dice. Bonus action: spend up to half-druid-lv dice → ally within 120 ft heals total + 1 temp HP per die. Pool refills on long rest. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_bsc_happy_lv5_one_die` | PATCH Mira → Dreams Lv 5 default 1 die → `heal_amount` in [1, 6], `temp_hp == 1`, `max_range_ft == 120`, `dice_remaining == 4`, broadcast (source `balm-of-the-summer-court`). |
| `test_use_bsc_two_dice` | dice_spent 2 → `heal_amount` in [2, 12], `temp_hp == 2`. |
| `test_use_bsc_dice_clamp` | dice_spent 99 → clamped to half-druid-level 2. |
| `test_use_bsc_wrong_subclass` | Default Mira (Moon) → 409. |
| `test_use_bsc_level_gate` | Dreams at Lv 1 → 409. |

### `test_combat_inspiration.py`
v2.99.320 — Valor College Bard (PHB p.55) Combat Inspiration Lv 3+ (F.1 Bard subclass batch opener — pivoted after Lore Cutting Words was found already wired). A creature with a BI die from you can roll it and add to weapon damage OR (reaction) AC. Die scales d6/d8/d10/d12 at Lv 3/5/10/15. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ci_happy_lv6` | PATCH Lyra → Valor Lv 6 default damage → `die_size == 8`, `die_expression == "1d8"`, broadcast (source `combat-inspiration`). |
| `test_use_ci_mode_ac` | Mode "ac" passes through. |
| `test_use_ci_default_mode` | Missing mode → "damage". |
| `test_use_ci_wrong_subclass` | Default Lyra (Lore) → 409. |
| `test_use_ci_level_gate` | Valor at Lv 2 → 409. |
| `test_ci_phase3a_attack_targeted_prompt_surfaces_option` | v2.158.67 — Phase 3a (option surfacing): seeds Lyra (Valor Lv 6) + Pip + Garrik; Lyra casts Bardic Inspiration on Garrik; Pip hits Garrik until a swing lands; asserts the resulting `reaction_prompt(attack_targeted)` for Garrik carries `use-combat-inspiration-ac` with `kind=class_feature`, `available=True`, a label containing "Combat Inspiration" + "+1d8 AC", and params {`die_expression=1d8`, `die_size=8`, `source_char_id=lyra.id`, integer `attack_total` + `target_ac`}. The dispatch half is deferred to Phase 3b. |
| `test_ci_phase3a_no_bi_buff_no_option` | v2.158.67 — regression guard: when no `bardic-inspiration-die` buff is installed on the watcher, `use-combat-inspiration-ac` MUST NOT surface in any `attack_targeted` prompt. Walks every prompt fired for Pip and asserts the option key is absent from each prompt's option list. |
| `test_ci_phase3b_dispatch_rolls_consumes_and_broadcasts` | v2.158.68 — Phase 3b dispatch happy path: after the Phase 3a flow surfaces the option, POSTs `/use_reaction` with `use-combat-inspiration-ac`. Asserts (a) `feature_used(source=combat-inspiration, reaction_kind=class_feature)` broadcast carries `ac_bonus ∈ 1..8` (Lv 6 → 1d8), `new_ac == base_ac + ac_bonus`, `verdict ∈ {"hit","miss"}`, `die_size=8`, `die_expression="1d8"`; (b) `buff_update` shows `bardic-inspiration-die` REMOVED from the watcher's buff list (consume per RAW); (c) `economy_update` flips the watcher's reaction chip to used. |
| `test_ci_phase3b_ud_suppression_lets_rogue_see_the_prompt` | v2.158.68 — UD-suppression regression test: when a Rogue Lv 5+ watcher carries a Valor-sourced BI buff, Uncanny Dodge's v2.49.243 auto-fire must STEP ASIDE so the `attack_targeted` prompt fires with both `cast-uncanny-dodge` + `use-combat-inspiration-ac` options. Asserts (a) NO `feature_used(source=uncanny-dodge)` auto-fired for Pip after Garrik's hit, (b) the prompt DID fire for Pip, (c) the prompt's options list both keys. |

### `test_mage_hand_legerdemain.py`
v2.99.369 — Arcane Trickster Rogue (PHB p.97) Mage Hand Legerdemain Lv 3+ (Phase G Rogue archetype sweep). When you cast Mage Hand, make the spectral hand invisible and perform extra tasks (stow/retrieve from another's container, pick locks/disarm traps at range). v2.158.17 (Phase 8 Rogue diversification — first Rogue subclass feature flipped to tracked this session, pushes the diversification arc to 8/12 classes): endpoint installs a permanent `mage-hand-legerdemain-active` buff with four `mage_hand_legerdemain_*` parameter flags. v2.158.42 (Phase 2): `/cast_spell` reads the buff via `_pc_mage_hand_legerdemain_params` on a Mage Hand cast and surfaces the Legerdemain parameters (task selection stays GM/client-driven).

| Test | What it asserts |
|------|-----------------|
| `test_use_ml_happy` | PATCH Pip → Arcane Trickster → `range_ft == 30`, `invisible == True`, tasks list ≥1, `buff_installed == True`, broadcast (source `mage-hand-legerdemain`). v2.158.17 — seeds Pip into an active battle so `_install_buff` returns True. |
| `test_use_ml_wrong_subclass` | Default Pip (Thief) → 409. |
| `test_use_ml_wrong_class` | Caelan (Paladin) → 409. |
| `test_ml_buff_payload_carries_parameter_flags` | v2.158.17 — installed buff carries four `mage_hand_legerdemain_*` effect keys (range_ft=30, invisible=True, bonus_action_control=True, unnoticed_check="sleight_of_hand_vs_passive_perception") + permanence sanity. State-change contract (Phase 9). Pins the Phase-2 contract so the future Mage Hand cast-flow read site has stable flag names. |
| `test_ml_cast_surfaces_legerdemain_params` | v2.158.42 — Phase 2 read site: an Arcane Trickster Pip carrying `mage-hand-legerdemain-active` who casts Mage Hand (injected into the spell list) sees `/cast_spell` return `mage_hand_legerdemain == True` + range 30 + invisible True + bonus-action control True + `unnoticed_check == "sleight_of_hand_vs_passive_perception"`. |
| `test_ml_not_surfaced_on_other_spell` | v2.158.42 — control: with the buff installed, casting Fire Bolt reports `mage_hand_legerdemain == False` + `range_ft == 0`. Pins the spell gate. |

### `test_mantle_of_inspiration.py`
v2.99.321 — Glamour College Bard (XGE p.16) Mantle of Inspiration Lv 3+ (F.1 Bard batch). Bonus action + 1 BI use → up to CHA-mod (min 1) allies within 60 ft each gain 5+bard_lv temp HP + immediate reaction-move at full speed without provoking OAs. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_mi_happy_lv6` | PATCH Lyra → Glamour Lv 6 (CHA 17 mod 3) → `max_targets == 3`, `temp_hp_per_target == 11`, `max_range_ft == 60`, `free_move_no_oa == True`, broadcast (source `mantle-of-inspiration`). |
| `test_use_mi_wrong_subclass` | Default Lyra (Lore) → 409. |
| `test_use_mi_level_gate` | Glamour at Lv 2 → 409. |

### `test_whispers_psychic_blades.py`
v2.99.322 — Whispers College Bard (XGE p.17) Psychic Blades Lv 3+ (F.1 Bard batch). On weapon hit, expend 1 BI use to deal extra psychic damage. Dice scale 2d6/3d6/5d6/8d6 at Lv 3/5/10/15. Endpoint slug `/use_whispers_psychic_blades` to avoid collision with Soulknife Rogue's `/use_psychic_blades` (v2.99.311). v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_wpb_happy_lv6` | PATCH Lyra → Whispers Lv 6 → `damage_expression == "3d6"`, `damage_type == "psychic"`, `consumed_bardic_inspiration == True`, broadcast (source `whispers-psychic-blades`). |
| `test_use_wpb_lv10` | Lv 10 → `damage_expression == "5d6"`. |
| `test_use_wpb_lv15` | Lv 15 → `damage_expression == "8d6"`. |
| `test_use_wpb_wrong_subclass` | Default Lyra (Lore) → 409. |
| `test_use_wpb_level_gate` | Whispers at Lv 2 → 409. |

### `test_blade_flourish.py`
v2.99.323 — Swords College Bard (XGE p.16) Blade Flourish Lv 3+ (F.1 Bard batch). On Attack action walking speed +10 ft until end of turn; on weapon hit, expend 1 BI use → one Flourish (Defensive / Slashing / Mobile). Once per turn. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_bf_happy_lv6_defensive` | PATCH Lyra → Swords Lv 6 default Defensive → `flourish == "defensive"`, `walking_speed_bonus_ft == 10`, `consumed_bardic_inspiration == True`, broadcast (source `blade-flourish`). |
| `test_use_bf_slashing` | flourish="slashing" passes through. |
| `test_use_bf_mobile` | flourish="mobile" passes through. |
| `test_use_bf_wrong_subclass` | Default Lyra (Lore) → 409. |
| `test_use_bf_level_gate` | Swords at Lv 2 → 409. |
| `test_bf_damage_with_target_applies_bonus` | v2.146.0 — Phase 1 shared-damage half: with `target_combatant_id` + `damage_type`, the endpoint rolls the BI die server-side and applies it as bonus damage to the target via `_apply_damage_to_combatant`. Asserts `bonus_rolled` ∈ 1..die_size and `bonus_applied` ∈ `{rolled, rolled // 2}` (allows resistance halve). |
| `test_bf_damage_without_target_announce_only` | v2.146.0 — without `target_combatant_id`, the endpoint stays announce-only (no BI die rolled, no damage applied). v2.158.66 — also pins `defensive_ac_bonus == 0` + `defensive_buff_installed is False` so the Phase 2 fields stay off when the BI die didn't roll. |
| `test_bf_defensive_installs_ac_buff` | v2.158.66 — Phase 2 Defensive Flourish AC self-buff finisher. With `flourish="defensive"` + `target_combatant_id`, the response carries `defensive_buff_installed is True` + `defensive_ac_bonus == bonus_rolled`; the `feature_used` broadcast surfaces the same two fields; a `buff_update` broadcast lands the `blade-flourish-defensive-active` buff on the bard's combatant entry with `effects.ac_bonus` matching the rolled value, `duration_rounds == 1`, `concentration is False`. |
| `test_bf_slashing_does_not_install_ac_buff` | v2.158.66 — regression guard: a Slashing Flourish still rolls + applies BI damage (Phase 1) but MUST NOT install the defensive AC self-buff. Asserts response has `defensive_ac_bonus == 0` + `defensive_buff_installed is False` and no `buff_update` broadcast carries the `blade-flourish-defensive-active` key for the bard. |

### `test_silver_tongue.py`
v2.99.324 — Eloquence College Bard (TCE p.28) Silver Tongue Lv 3+ (F.1 Bard batch). Cha (Persuasion) and Cha (Deception) checks treat a d20 roll of 9 or lower as a 10. v2.158.16 (Phase 8 Bard diversification — first Bard subclass feature flipped to tracked this session, pushes the diversification arc to 7/12 classes): endpoint installs a permanent `silver-tongue-active` buff with three `silver_tongue_*` parameter flags. v2.158.36 (Phase 2): the `/roll` endpoint reads the buff via `_pc_silver_tongue_floor_applies` and floors the kept d20 to 10 on a Cha (Persuasion/Deception) check (reusing the Reliable Talent floor), emitting a `feature_used(source=silver-tongue)` broadcast.

| Test | What it asserts |
|------|-----------------|
| `test_use_st_happy_lv6` | PATCH Lyra → Eloquence Lv 6 → `minimum_d20_value == 10`, applies_to includes persuasion + deception, `ability == "CHA"`, `buff_installed == True`, broadcast (source `silver-tongue`). v2.158.16 — seeds Lyra into an active battle so `_install_buff` returns True. |
| `test_use_st_wrong_subclass` | Default Lyra (Lore) → 409. |
| `test_use_st_level_gate` | Eloquence at Lv 2 → 409. |
| `test_st_buff_payload_carries_parameter_flags` | v2.158.16 — installed buff carries three `silver_tongue_*` effect keys (min_d20=10, skills list with persuasion+deception, ability="CHA") + permanence sanity. State-change contract (Phase 9). Pins the Phase-2 contract so the future ability-check resolver has stable flag names. |
| `test_st_floors_low_d20_on_persuasion` | v2.158.36 — Phase 2 read site. With the buff installed, a seeded low d20 on a Persuasion check is floored to 10 on `/roll` and a `feature_used(source=silver-tongue)` broadcast fires; an Athletics control roll (non-matching skill) is left untouched. |

### `test_tales_from_beyond.py`
v2.99.325 — Spirits College Bard (TCE p.30) Tales from Beyond Lv 3+ (F.1 Bard batch). Bonus action to roll 1d6 on Spirit Tales table; action to apply tale (6 tales: Clever Animal/Duelist/Beloved Friends/Brute/Tragic Romance/Traveler). `force_tale` body param (1-6) is a TEST_MODE escape hatch. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_tb_happy_lv6` | PATCH Lyra → Spirits Lv 6 → `tale_roll` in [1,6], `tale_name` non-empty, broadcast (source `tales-from-beyond`). |
| `test_use_tb_force_tale_4_brute` | `force_tale=4` → roll 4, name contains "Brute". |
| `test_use_tb_force_tale_2_duelist` | `force_tale=2` → roll 2, name contains "Duelist". |
| `test_use_tb_wrong_subclass` | Default Lyra (Lore) → 409. |
| `test_use_tb_level_gate` | Spirits at Lv 2 → 409. |

### `test_mote_of_potential.py`
v2.99.326 — Creation College Bard (TCE p.31) Mote of Potential Lv 3+ (F.1 Bard batch — CLOSES the batch 8/8). When a creature uses a BI die from you, the Mote attaches + triggers an effect by mode: check (re-roll BI die, add to check), attack (BI die in force damage to nearby creature), save (temp HP = BI roll + CHA mod). v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_mp_happy_lv6_check` | PATCH Lyra → Creation Lv 6 (CHA 17 mod 3) default check → `die_size == 8`, `die_expression == "1d8"`, `cha_mod == 3`, broadcast (source `mote-of-potential`). |
| `test_use_mp_mode_attack` | mode="attack" passes through. |
| `test_use_mp_mode_save` | mode="save" passes through. |
| `test_use_mp_wrong_subclass` | Default Lyra (Lore) → 409. |
| `test_use_mp_level_gate` | Creation at Lv 2 → 409. |

### `test_arcane_ward.py`
v2.99.327 — Abjuration School Wizard (PHB p.115) Arcane Ward Lv 2+ (G.1 Wizard subclass batch opener). On abjuration cast Lv 1+, create magical ward HP = 2 × wizard_lv + INT mod. Refills 2 × spell-level HP per abjuration cast. Lasts until long rest. Once-per-long-rest creation. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_aw_happy_lv7` | PATCH Thalindra → Abjuration Lv 7 (INT 16 mod 3) → `ward_hp_max == 17`, broadcast (source `arcane-ward`). |
| `test_use_aw_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_aw_level_gate` | Abjuration at Lv 1 → 409. |

### `test_third_eye.py`
v2.99.328 — Divination School Wizard (PHB p.116) The Third Eye Lv 10+ (G.1 Wizard batch — pivot after Portent was found already wired in v2.99.219). Action to gain one of 4 magical senses until dismissed or short/long rest: Darkvision / Ethereal Sight / Greater Comprehension / See Invisibility. Costs action chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_te_happy_lv10_darkvision` | PATCH Thalindra → Divination Lv 10 default → `sense == "darkvision"`, broadcast (source `third-eye`). |
| `test_use_te_see_invisibility` | sense="see-invisibility" passes through. |
| `test_use_te_ethereal_sight` | sense="ethereal-sight" passes through. |
| `test_use_te_greater_comprehension` | sense="greater-comprehension" passes through. |
| `test_use_te_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_te_level_gate` | Divination at Lv 9 → 409. |

### `test_minor_conjuration.py`
v2.99.329 — Conjuration School Wizard (PHB p.116) Minor Conjuration Lv 2+ (G.1 Wizard batch). Action to conjure a nonmagical inanimate object ≤3 ft any dim, ≤10 lb, in hand or unoccupied space within 10 ft. Persists 1 hr or until re-conjured/damaged. Costs action chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_mc_happy_lv7` | PATCH Thalindra → Conjuration Lv 7 with "torch" → `object_name == "torch"`, `duration_minutes == 60`, `max_dim_ft == 3`, `max_weight_lb == 10`, `dim_light_radius_ft == 5`, broadcast (source `minor-conjuration`). |
| `test_use_mc_default_name` | Missing `object_name` → fallback string with "unspecified". |
| `test_use_mc_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_mc_level_gate` | Conjuration at Lv 1 → 409. |

### `test_hypnotic_gaze.py`
v2.99.330 — Enchantment School Wizard (PHB p.117) Hypnotic Gaze Lv 2+ (G.1 Wizard batch). Action, target within 5 ft → WIS save DC 8 + prof + INT mod; on fail, charmed + incapacitated + speed 0 until end of next turn. Extendable. Costs action chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_hg_happy_lv7` | PATCH Thalindra → Enchantment Lv 7 (prof 3 INT 16 mod 3) → `save_dc == 14`, `save_ability == "WIS"`, `range_ft == 5`, broadcast (source `hypnotic-gaze`). |
| `test_use_hg_with_target` | `target_combatant_id` passes through. |
| `test_use_hg_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_hg_level_gate` | Enchantment at Lv 1 → 409. |

### `test_improved_minor_illusion.py`
v2.99.331 — Illusion School Wizard (PHB p.118) Improved Minor Illusion Lv 2+ (G.1 Wizard batch). Free Minor Illusion cantrip + dual-mode sound + image in single cast. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_imi_happy_lv7` | PATCH Thalindra → Illusion Lv 7 → `dual_mode == True`, free_cantrip mentions Minor Illusion, broadcast (source `improved-minor-illusion`). |
| `test_use_imi_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_imi_level_gate` | Illusion at Lv 1 → 409. |

### `test_grim_harvest.py`
v2.99.332 — Necromancy School Wizard (PHB p.118) Grim Harvest Lv 2+ (G.1 Wizard batch). Once per turn, kill with Lv 1+ spell → regain HP = 2 × spell level (3 × if necromancy). v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_gh_happy_lv7_lv3_spell` | PATCH Thalindra → Necromancy Lv 7, spell_level 3 non-necro → `heal_amount == 6`, broadcast (source `grim-harvest`). |
| `test_use_gh_necromancy_spell` | spell_level 3 + is_necromancy=true → `heal_amount == 9`. |
| `test_use_gh_default_spell_level` | Missing spell_level → default 1 → `heal_amount == 2`. |
| `test_use_gh_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_gh_level_gate` | Necromancy at Lv 1 → 409. |

### `test_minor_alchemy.py`
v2.99.333 — Transmutation School Wizard (PHB p.119) Minor Alchemy Lv 2+ (G.1 Wizard batch). 10 min / cubic foot transmute one nonmagical object (wood/stone/iron/copper/silver) into another. Reverts after 1 hour or on losing concentration. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ma_happy_lv7_default` | PATCH Thalindra → Transmutation Lv 7 default → wood → stone, `time_per_cubic_foot_minutes == 10`, `duration_minutes == 60`, `concentration == True`, broadcast (source `minor-alchemy`). |
| `test_use_ma_iron_to_copper` | source/target=iron/copper passes through. |
| `test_use_ma_invalid_material_clamps` | "gold"/"diamond" → clamped to wood/stone defaults. |
| `test_use_ma_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_ma_level_gate` | Transmutation at Lv 1 → 409. |

### `test_bladesong.py`
v2.99.334 — Bladesinging Wizard (TCE p.74) Bladesong Lv 2+ (G.1 Wizard batch — pivot after Sculpt Spells found already wired in v2.99.225). Bonus action 1 min: +CHA mod AC, +10 ft speed, advantage on Acrobatics, +INT mod concentration/weapon damage. Twice per short or long rest. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_bs_happy_lv7` | PATCH Thalindra → Bladesinging Lv 7 (CHA 10 mod 0, INT 16 mod 3) → `ac_bonus == 1` (max(1, CHA)), `speed_bonus_ft == 10`, `concentration_bonus == 3`, `weapon_damage_bonus_per_turn == 3`, `duration_minutes == 1`, `uses_remaining == 1`, broadcast (source `bladesong`). |
| `test_use_bs_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_bs_level_gate` | Bladesinging at Lv 1 → 409. |
| `test_use_bs_two_uses_then_out` | 1st → uses_remaining 1; 2nd → 0; 3rd → 409 `no_uses_left`. |

### `test_wizardly_quill.py`
v2.99.335 — Order of Scribes Wizard (TCE p.75) Wizardly Quill Lv 2+ (G.1 Wizard batch). Bonus action to conjure magical quill — no ink, any language/color, 4× speed, self-erase. Vanishes after long rest. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_wq_happy_lv7` | PATCH Thalindra → Scribes Lv 7 → `speed_multiplier == 4`, all property flags True, `duration == "until_long_rest"`, broadcast (source `wizardly-quill`). |
| `test_use_wq_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_wq_level_gate` | Scribes at Lv 1 → 409. |

### `test_arcane_deflection.py`
v2.99.336 — War Magic Wizard (XGE p.59) Arcane Deflection Lv 2+ (G.1 Wizard batch). Reaction on hit by attack or failed save → +2 AC vs the triggering attack OR +4 to the failed save. Can't cast leveled spells (cantrips only) until end of next turn. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ad_happy_lv7_ac` | PATCH Thalindra → War Magic Lv 7 → `mode == "ac"`, `bonus == 2`, `leveled_spell_lockout == True`, `wizard_level == 7`, broadcast (source `arcane-deflection`). |
| `test_use_ad_save_mode` | `mode="save"` → `bonus == 4`. |
| `test_use_ad_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_ad_level_gate` | War Magic at Lv 1 → 409. |

### `test_chronal_shift.py`
v2.99.337 — Chronurgy Magic Wizard (EGtW p.184) Chronal Shift Lv 2+ (G.1 Wizard batch). Reaction: self or a seen creature within 30 ft making an attack roll, check, or save must reroll and use the new roll. Twice per long rest. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_cs_happy_lv7` | PATCH Thalindra → Chronurgy Lv 7 → `uses_remaining == 1`, `uses_max == 2`, `wizard_level == 7`, broadcast (source `chronal-shift`). |
| `test_use_cs_two_uses_then_out` | 1st → 1; 2nd → 0; 3rd → 409 `no_uses_left`. |
| `test_use_cs_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_cs_level_gate` | Chronurgy at Lv 1 → 409. |

### `test_restore_balance.py`
v2.99.342 — Clockwork Soul Sorcerer (TCE p.69) Restore Balance Lv 1+ (G.2 Sorcerer batch). Reaction: a seen creature within 60 ft about to roll a d20 with adv/disadv rolls without it. Uses = proficiency bonus per long rest (server-tracked on `sheet.restore_balance_uses`). v2.122.0 — the cancel is now REAL: clears the target's active `roll_state` + broadcasts `character_roll_state(value=None)`.

| Test | What it asserts |
|------|-----------------|
| `test_use_rb_happy_lv5` | PATCH Zara → Clockwork Soul → `range_ft == 60`, `cancels_adv_disadv == True`, uses 3 → 2, `sorcerer_level == 5`, broadcast (source `restore-balance`). |
| `test_use_rb_out_of_uses` | `restore_balance_uses == 0` → 409 `out_of_uses`. |
| `test_use_rb_wrong_subclass` | Default Zara (Draconic Bloodline) → 409. |
| `test_use_rb_wrong_class` | Caelan (Paladin) → 409. |
| `test_rb_cancels_target_advantage` | v2.122.0 — set Krieger to `advantage`, Zara Restore-Balances him with `target_character_id` → `cancelled=True`, `previous_roll_state="advantage"`, `character_roll_state(value=None)` broadcast, `feature_used(cancelled=True)`. Restores Krieger's roll_state in finally. |
| `test_rb_no_op_when_target_neutral` | v2.122.0 — target with no active adv/disadv → 200 but `cancelled=False`, `previous_roll_state=None` (the use is still spent). |
| `test_rb_rest_refill_long_only` | Exhausted → 409; SHORT rest does NOT refill; LONG rest refills to PB. |

### `test_adjust_density.py`
v2.99.338 — Graviturgy Magic Wizard (EGtW p.185) Adjust Density Lv 2+ (G.1 Wizard batch CLOSE 13/13). Action + concentration up to 1 min: double or halve a willing creature's weight. Doubled → -10 ft speed + advantage on STR. Halved → +10 ft speed + disadvantage on STR. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ad_happy_lv7_double` | PATCH Thalindra → Graviturgy Lv 7 → `mode == "double"`, `speed_delta == -10`, `str_effect == "advantage"`, `wizard_level == 7`, broadcast (source `adjust-density`). |
| `test_use_ad_halve_mode` | `mode="halve"` → `speed_delta == 10`, `str_effect == "disadvantage"`. |
| `test_use_ad_with_target` | `target_character_id` → response carries `target_character_name == "Sir Caelan Lightbringer"`. |
| `test_use_ad_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_ad_level_gate` | Graviturgy at Lv 1 → 409. |

### `test_conquering_presence.py`
v2.99.247 — Oath of Conquest (Paladin subclass, XGE p.37) Conquering Presence CD (Phase H.2 third oath). Caelan PATCH'd to Conquest + CD 1/1 + 2 Bandits in battle. DC 14.

| Test | What it asserts |
|------|-----------------|
| `test_use_cp_happy` | Conquest Caelan targets 2 bandits → `save_dc == 14`, `uses_remaining == 0`, list of 2 ids returned, broadcast (source `conquering-presence`). |
| `test_use_cp_empty_target_list` | Empty target list → 400. |
| `test_use_cp_unknown_target` | One unknown target in list → 404 `target_not_in_battle`. |
| `test_use_cp_out_of_cd` | `channel-divinity.current = 0` → 409 `out_of_uses`. |
| `test_use_cp_wrong_subclass` | Default Caelan (Devotion) → 409 `wrong_subclass_or_level`. |

### `test_abjure_enemy.py`
v2.99.274 — Vengeance Paladin (PHB p.87) Abjure Enemy CD (H.2 depth). Sibling CD to Vow of Enmity (v2.99.246). Single target Wis save DC 8 + prof + CHA; fail Frightened + speed 0 or success speed halved (both end on damage).

| Test | What it asserts |
|------|-----------------|
| `test_use_ae_happy` | Vengeance Caelan adjures Bandit → `save_dc == 14`, `uses_remaining == 0`, broadcast. |
| `test_use_ae_target_not_in_battle` | Unknown target → 404. |
| `test_use_ae_out_of_cd` | CD 0 → 409. |
| `test_use_ae_wrong_subclass` | Default Caelan (Devotion) → 409. |

### `test_vow_of_enmity.py`
v2.99.246 — Oath of Vengeance (Paladin subclass, PHB p.87) Vow of Enmity bonus-action CD (Phase H.2 second oath). Caelan PATCH'd to Vengeance + CD 1/1 + Bandit in battle.

| Test | What it asserts |
|------|-----------------|
| `test_use_voe_happy` | Vengeance Caelan vs Bandit → CD 1 → 0, `buff_installed: True`, `target_name == "Bandit Alpha"`, broadcast (source `vow-of-enmity`). |
| `test_use_voe_target_not_in_battle` | Unknown target_combatant_id → 404 `target_not_in_battle`. |
| `test_use_voe_out_of_cd` | `channel-divinity.current = 0` → 409 `out_of_uses`. |
| `test_use_voe_wrong_subclass` | Default Caelan (Devotion) → 409 `wrong_subclass_or_level`. |

### `test_demo_vengeance_paladin.py`
v2.158.56 — Demo Vengeance Paladin (Dame Seraphine Vael, 13th demo PC) so the v2.158.55 Vow of Enmity sheet button has a live demo fixture. Exercises the REAL seeded PC (no PATCH), unlike `test_vow_of_enmity.py`.

| Test | What it asserts |
|------|-----------------|
| `test_demo_vengeance_paladin_seed_contract` | Seeded PC exists, is Paladin / Oath of Vengeance Lv 3, and carries a `channel-divinity` resource with `subclass_slug == "vengeance"` (the field the CD picker filter reads to surface Vow of Enmity). |
| `test_demo_vengeance_paladin_can_fire_vow` | Reset CD to 1 + target in battle → `/use_vow_of_enmity` → 200, `uses_remaining == 0`, `buff_installed: True`, `target_name == "Bandit Quarry"`, `feature_used(source=vow-of-enmity)` broadcast. |

### `test_demo_beast_barbarian.py`
v2.158.60 — Demo Path of the Beast Barbarian (Brakka Wildmane, 14th demo PC) so the v2.158.59 Form of the Beast class-features button has a live demo fixture. Exercises the REAL seeded PC (no PATCH), unlike `test_form_of_the_beast.py` which PATCHes Krieger.

| Test | What it asserts |
|------|-----------------|
| `test_demo_beast_barbarian_seed_contract` | Seeded PC exists, is Barbarian / Path of the Beast Lv 5, and carries a `class_features` entry keyed `form-of-the-beast` (the entry the `.cf-use` button renders + routes from). |
| `test_demo_beast_barbarian_can_manifest_form` | Battle seeded → `/use_form_of_the_beast` (form "claws") → 200, `ok: True`, `form == "claws"`, `damage_die == "1d6"`, `buff_installed: True`, `feature_used(source=form-of-the-beast)` broadcast. |

### `test_demo_drunken_monk.py`
v2.158.62 — Demo Way of the Drunken Master Monk (Quan Reelstep, 15th demo PC) so the v2.158.61 Drunken Technique class-features button has a live demo fixture. Exercises the REAL seeded PC (no PATCH), unlike `test_drunken_technique.py` which PATCHes Kael.

| Test | What it asserts |
|------|-----------------|
| `test_demo_drunken_monk_seed_contract` | Seeded PC exists, is Monk / Way of the Drunken Master Lv 5, and carries a `class_features` entry keyed `drunken-technique` (the entry the `.cf-use` button renders + routes from). |
| `test_demo_drunken_monk_can_trigger_technique` | Battle seeded → `/use_drunken_technique` → 200, `ok: True`, `feature == "drunken-technique"`, `disengage: True`, `speed_bonus_ft == 10`, `monk_level == 5`, `buff_installed: True`, `feature_used(source=drunken-technique)` broadcast. |

### `test_turn_the_faithless.py`
v2.99.272 — Ancients Paladin (PHB p.87) Turn the Faithless CD (H.2 Phase 2). Sibling CD to Nature's Wrath (v2.99.245). 30-ft AOE Wis save vs fey/fiend or Turned 1 minute.

| Test | What it asserts |
|------|-----------------|
| `test_use_ttf_happy` | Ancients Caelan vs Imp + Sprite → `save_dc == 14`, `uses_remaining == 0`, broadcast (source `turn-the-faithless`). |
| `test_use_ttf_empty_target_list` | Empty list → 400. |
| `test_use_ttf_unknown_target` | One unknown target → 404. |
| `test_use_ttf_out_of_cd` | CD 0 → 409 `out_of_uses`. |
| `test_use_ttf_wrong_subclass` | Default Caelan (Devotion) → 409. |

### `test_natures_wrath.py`
v2.99.245 — Oath of the Ancients (Paladin subclass, PHB p.86) Nature's Wrath Channel Divinity (Phase H.2 Phase 1 of [docs/plans/paladin-oaths.md](../plans/paladin-oaths.md)). Sir Caelan Lightbringer is the demo fixture; tests PATCH his subclass to "Oath of the Ancients" and seed Bandit in battle. Caelan Lv 8 CHA 16: DC = 8 + prof 3 + CHA +3 = 14.

| Test | What it asserts |
|------|-----------------|
| `test_use_nw_str_happy` | Ancients Caelan vs Bandit with `save_ability: "STR"` → `save_dc == 14`, `uses_remaining == 0`, broadcast (source `natures-wrath`). |
| `test_use_nw_dex_mode` | `save_ability: "DEX"` → mirrored in response. |
| `test_use_nw_bad_save_ability` | CON isn't in `{STR, DEX}` → 400. |
| `test_use_nw_out_of_cd` | `channel-divinity.current = 0` → 409 `out_of_uses`. |
| `test_use_nw_wrong_subclass` | Default Caelan (Devotion) → 409 `wrong_subclass_or_level`. |

### `test_voice_of_authority.py`
v2.99.244 — Order Domain Cleric (TCE p.39) Voice of Authority manual trigger (Phase H.1 final domain). Authorizes an ally to take a reaction weapon attack after the cleric casts a Lv 1+ spell. Marks the ALLY's reaction chip.

| Test | What it asserts |
|------|-----------------|
| `test_use_voa_ally_happy` | Tavik authorizes Caelan vs Bandit Alpha → ally reaction marked, broadcast (source `voice-of-authority`). |
| `test_use_voa_self_target` | Targeting self → 409 `self_targeting_not_allowed` (RAW: ally only). |
| `test_use_voa_unknown_ally` | Unknown ally_combatant_id → 404 `ally_not_in_battle`. |
| `test_use_voa_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_emboldening_bond.py`
v2.99.243 — Peace Domain Cleric (TCE p.40) Emboldening Bond multi-target buff (Phase H.1 tenth domain). Up to prof-bonus creatures get +1d4 to attack/check/save while within 30 ft of one another.

| Test | What it asserts |
|------|-----------------|
| `test_use_eb_two_targets_happy` | Tavik bonds Pip + Caelan → 2 buffs installed, `max_allowed == 3` (prof +3), broadcast. |
| `test_use_eb_too_many_targets` | 4 targets with prof 3 → 409 `too_many_targets`, `max == 3`, `got == 4`. |
| `test_use_eb_unknown_target` | One unknown target in list → 404 `target_not_in_battle`. |
| `test_use_eb_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |
| `test_eb_adds_d4_to_ability_check_and_persists` | v2.158.47 Phase 2 read site: bond Pip → her DEX check total gains +1d4 + breakdown mentions "Emboldening Bond"; a second check also gets it (persistent, not consumed). |
| `test_eb_not_applied_to_unbonded_or_non_check` | v2.158.47 control: an unbonded creature's check gets no +1d4, and a bonded creature's generic dice-tray roll (no `stat_ability`) gets no bonus. |

### `test_vigilant_blessing.py`
v2.99.242 — Twilight Domain Cleric (TCE p.41) Vigilant Blessing action (Phase H.1 ninth domain). Touch-an-ally (or self) buff installer: advantage on next init roll. No daily cap.

| Test | What it asserts |
|------|-----------------|
| `test_use_vb_target_ally` | Tavik blesses Pip → `target_char_id == pip.id`, `is_self == False`, `buff_installed: True`, broadcast (source `vigilant-blessing`). |
| `test_use_vb_target_self` | Tavik targets himself → `is_self: True`, buff installed (RAW allows self). |
| `test_use_vb_target_not_in_battle` | Unknown target_combatant_id → 404 `target_not_in_battle`. |
| `test_use_vb_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_eyes_of_the_grave.py`
v2.99.241 — Grave Domain Cleric (XGE p.19) Eyes of the Grave (Phase H.1 eighth domain). Action to detect undead within 60 ft for 1 round. WIS mod uses per long rest.

| Test | What it asserts |
|------|-----------------|
| `test_use_eotg_happy` | Grave Tavik → `uses_remaining == 2`, broadcast (source `eyes-of-the-grave`). |
| `test_use_eotg_out_of_uses` | `eyes-of-the-grave.current = 0` → 409 `out_of_uses`. |
| `test_use_eotg_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_blessing_of_the_forge.py`
v2.99.240 — Forge Domain Cleric (XGE p.18) Blessing of the Forge (Phase H.1 seventh domain). Long-rest blessing picks 1 non-magical weapon or armor; persists `sheet.blessed_object`.

| Test | What it asserts |
|------|-----------------|
| `test_use_bof_weapon_happy` | Tavik blesses Warhammer (index 0) → `kind: "weapon"`, `slug: "warhammer"`, broadcast (source `blessing-of-the-forge`). |
| `test_use_bof_armor_happy` | Tavik blesses Chain mail (index 2) → `kind: "armor"`. |
| `test_use_bof_shield_rejected` | Shield (index 1, `type: "shield"`) → 400 (RAW only weapon or armor). |
| `test_use_bof_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |
| `test_use_bof_missing_item_index` | No item_index body → 400. |

### `test_acolyte_of_nature.py`
v2.99.239 — Nature Domain Cleric (PHB p.61) Acolyte of Nature one-time picker (Phase H.1 sixth domain). Picks 1 druid cantrip + 1 skill from {Animal Handling, Nature, Survival}.

| Test | What it asserts |
|------|-----------------|
| `test_select_aon_happy` | Tavik picks Druidcraft + Survival → persisted, broadcast (source `acolyte-of-nature`). |
| `test_select_aon_bad_skill` | Arcana isn't in valid set → 400. |
| `test_select_aon_missing_cantrip` | Empty cantrip → 400. |
| `test_select_aon_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_blessings_of_knowledge.py`
v2.99.238 — Knowledge Domain Cleric (PHB p.59) Blessings of Knowledge one-time picker (Phase H.1 fifth domain). Picks 2 skills from {Arcana, History, Nature, Religion} + 2 languages.

| Test | What it asserts |
|------|-----------------|
| `test_select_bok_happy` | Tavik picks Arcana + Religion + Celestial + Draconic → 200, persisted, broadcast (source `blessings-of-knowledge`). |
| `test_select_bok_bad_skill` | Skill not in PHB list (Athletics) → 400. |
| `test_select_bok_wrong_count` | 1 skill instead of 2 → 400. |
| `test_select_bok_duplicate_skills` | Arcana + Arcana → 400. |
| `test_select_bok_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_blessing_of_the_trickster.py`
v2.99.237 — Trickery Domain Cleric (PHB p.62) Blessing of the Trickster (Phase H.1 fourth domain). Touch-an-ally buff installer (no daily cap RAW). Brother Tavik Stonebrow is the fixture; tests PATCH his subclass to "Trickery Domain" and seed Tavik + Pip in a battle.

| Test | What it asserts |
|------|-----------------|
| `test_use_botrickster_happy` | Tavik blesses Pip → `target_char_id == pip.id`, `buff_installed: True`, broadcast (source `blessing-of-the-trickster`). |
| `test_use_botrickster_self_target` | Target is Tavik himself → 409 `self_targeting_not_allowed`. |
| `test_use_botrickster_target_not_in_battle` | Unknown `target_combatant_id` → 404 `target_not_in_battle`. |
| `test_use_botrickster_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_war_priest.py`
v2.99.236 — War Domain Cleric (PHB p.63) War Priest bonus-action attack (Phase H.1 third domain). Brother Tavik Stonebrow is the demo fixture; tests PATCH his subclass to "War Domain" + seed a `war-priest` resource.

| Test | What it asserts |
|------|-----------------|
| `test_use_war_priest_happy` | War Cleric Tavik → `uses_remaining == 2`, bonus chip marked + broadcast (source `war-priest`). |
| `test_use_war_priest_out_of_uses` | `war-priest.current = 0` → 409 `out_of_uses`. |
| `test_use_war_priest_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_wrath_of_the_storm.py`
v2.99.235 — Tempest Domain Cleric (PHB p.62) Wrath of the Storm reaction (Phase H.1 second domain). Brother Tavik Stonebrow is the demo fixture; tests PATCH his subclass to "Tempest Domain" + seed a `wrath-of-the-storm` resource.

| Test | What it asserts |
|------|-----------------|
| `test_use_wots_lightning_happy` | Lightning damage_type → `damage` in 2..16, `save_dc == 14` (Tavik Lv 8: prof +3 + WIS +3), `uses_remaining == 2` + broadcast. |
| `test_use_wots_thunder` | `damage_type: "thunder"` mirrored in response. |
| `test_use_wots_bad_damage_type` | `damage_type: "fire"` → 400. |
| `test_use_wots_out_of_uses` | `wrath-of-the-storm.current = 0` → 409 `out_of_uses`. |
| `test_use_wots_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_potent_spellcasting.py`
v2.99.270 — Light Domain Cleric Lv 8 (PHB p.60) Potent Spellcasting announce (H.1 depth — first Lv 6/8/17 feature for an already-shipped Cleric domain). Tavik Lv 8 WIS 16 → +3 mod.

| Test | What it asserts |
|------|-----------------|
| `test_use_ps_happy` | Light Tavik Lv 8 → `wis_mod == 3`, cantrip_name mirrored, broadcast (source `potent-spellcasting`). |
| `test_use_ps_wrong_subclass` | Default Tavik (Life) → 409 `wrong_subclass_or_level`. |
| `test_use_ps_level_gate` | Light Tavik at Lv 7 → 409. |
| `test_use_ps_knowledge_lv8` | v2.99.271: Knowledge Domain Tavik Lv 8 also works (RAW identical for Light + Knowledge). |
| `test_use_ps_grave_lv8` | v2.99.277: Grave Domain Tavik Lv 8 also works (XGE p.19). |
| `test_use_ps_peace_lv8` | v2.99.277: Peace Domain Tavik Lv 8 also works (TCE p.40). |

### `test_warding_flare.py`
v2.99.234 — Light Domain Cleric (PHB p.60) Warding Flare reaction (Phase H.1 first ship). Brother Tavik Stonebrow is the demo fixture; tests PATCH his subclass to "Light Domain" + seed a `warding-flare` resource with 3 uses (WIS 16 → +3 mod).

| Test | What it asserts |
|------|-----------------|
| `test_use_warding_flare_happy` | Light Cleric Tavik (in battle) → `uses_remaining == 2`, broadcast (source `warding-flare`) carries `attacker_name == "Bandit Alpha"`. |
| `test_use_warding_flare_out_of_uses` | `warding-flare.current = 0` → 409 `out_of_uses`. |
| `test_use_warding_flare_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |
| `test_use_warding_flare_no_resource` | Light Cleric without the `warding-flare` resource entry → 404. |

### `test_eldritch_knight_capstones.py`
v2.99.269 — Eldritch Knight Fighter (PHB p.74) Arcane Charge + Improved War Magic announces (Phase E.2 Phase 4, **closes E.2**). Lv 15 Arcane Charge (teleport 30 ft with Action Surge); Lv 18 Improved War Magic (Lv 1+ spell variant of War Magic). v2.158.11 (Phase 8 Lv-15 tier): Arcane Charge endpoint now installs a permanent `arcane-charge-active` buff carrying the two `arcane_charge_*` teleport-budget flags. v2.158.39 (Phase 2 shipped): `/use_action_surge` reads the buff via `_pc_arcane_charge_teleport_ft` + surfaces the 30 ft teleport budget on its response + broadcast.

| Test | What it asserts |
|------|-----------------|
| `test_use_ac_happy_lv15` | Lv 15 EK Garrik → `teleport_max_ft == 30`, `buff_installed == True`, broadcast (source `arcane-charge`). v2.158.11 — happy test gains the buff assertion. |
| `test_use_ac_level_gate` | Lv 14 → 409. |
| `test_use_iwm_happy_lv18` | Lv 18 EK Garrik → broadcast (source `improved-war-magic`), bonus chip marked, `buff_installed == True` (v2.158.12). |
| `test_use_iwm_level_gate` | Lv 17 → 409. |
| `test_ac_buff_payload_carries_teleport_flags` | v2.158.11 — installed buff carries `effects.arcane_charge_teleport_max_ft == 30` + `effects.arcane_charge_requires_action_surge == True`. Plus permanence sanity: `concentration` falsy + `duration_rounds >= 1000`. State-change contract (Phase 9). Pins the Phase-2 contract so the future `/use_action_surge` read site has stable flag names to look up. |
| `test_iwm_buff_payload_carries_min_spell_level_flag` | v2.158.12 — installed `improved-war-magic-active` buff carries `effects.improved_war_magic_active == True` + `effects.improved_war_magic_min_spell_level == 1`. Plus permanence sanity. State-change contract (Phase 9). Pins the Phase-2 contract so the future War Magic / `/cast_spell` read site has stable flag names. Closes EK 2/2 Phase 8 tracked features. |
| `test_action_surge_surfaces_arcane_charge_teleport` | v2.158.39 Phase 2 — a Lv 15 EK carrying `arcane-charge-active` sees `/use_action_surge` return `arcane_charge_teleport_ft == 30` on the response + `feature_used` broadcast, with an Arcane Charge note in the desc. |
| `test_action_surge_no_teleport_without_arcane_charge` | v2.158.39 control — buff installed then ended → `/use_action_surge` reports `arcane_charge_teleport_ft == 0`; the read is scoped to the buff. |

### `test_eldritch_strike.py`
v2.99.268 — Eldritch Knight Fighter (PHB p.74) Eldritch Strike buff install (Phase E.2 Phase 3). Lv 10+; on hit, target has disadvantage on next save vs an EK spell before end of next turn.

| Test | What it asserts |
|------|-----------------|
| `test_use_es_happy` | Lv 10 EK Garrik marks Pip → `target_char_id == pip.id`, `buff_installed: True`, broadcast (source `eldritch-strike`). |
| `test_use_es_wrong_subclass` | Default Garrik (Champion) → 409 `wrong_subclass_or_level`. |
| `test_use_es_level_gate` | EK at Lv 9 → 409. |
| `test_use_es_target_not_in_battle` | Unknown target → 404 `target_not_in_battle`. |

### `test_war_magic.py`
v2.99.267 — Eldritch Knight Fighter (PHB p.74) War Magic announce (Phase E.2 Phase 2). Lv 7+; after casting a cantrip with action, make one weapon attack as a bonus action. v2.158.40 (Phase 2 read site for the v2.158.12 Improved War Magic Lv-18 buff): `/use_war_magic` reads `improved-war-magic-active` via `_pc_improved_war_magic_min_level` + widens the prerequisite to any Lv 1+ spell.

| Test | What it asserts |
|------|-----------------|
| `test_use_wm_happy` | Lv 9 Eldritch Knight Garrik → 200, broadcast (source `war-magic`), bonus chip marked. |
| `test_wm_improved_widens_prerequisite` | v2.158.40 Phase 2 — a Lv 18 EK carrying `improved-war-magic-active` sees `/use_war_magic` return `improved_war_magic == True` + `spell_min_level == 1` on the response + broadcast, with the Lv 1+ widening in the desc. |
| `test_wm_base_cantrip_only_without_buff` | v2.158.40 control — buff installed then ended → `improved_war_magic == False` + `spell_min_level == 0` (base cantrip-only War Magic). |
| `test_use_wm_wrong_subclass` | Default Garrik (Champion) → 409 `wrong_subclass_or_level`. |
| `test_use_wm_level_gate` | Eldritch Knight at Lv 6 (not 7+) → 409. |

### `test_commanders_strike.py`
v2.99.266 — Battle Master maneuver 16 of 16 — Commander's Strike (PHB p.74). **Closes the 16-maneuver batch.** Bonus action: ally takes free weapon attack as reaction + die added to damage.

| Test | What it asserts |
|------|-----------------|
| `test_use_cs_happy` | Lv 9 Garrik d8 → `extra_damage` 1..8, `ally_name == "Pip"`. |
| `test_use_cs_out_of_dice` | Dice 0 → 409. |
| `test_use_cs_wrong_subclass` | Default Champion → 409. |

### `test_maneuvering_attack.py`
v2.99.265 — Battle Master maneuver 15 of 16 — Maneuvering Attack (PHB p.74). On hit, +die damage; chosen ally can use reaction to move half speed without provoking OAs from the target.

| Test | What it asserts |
|------|-----------------|
| `test_use_ma_happy` | Lv 9 Garrik d8 → `extra_damage` 1..8, `ally_name == "Pip"`, `target_name == "Bandit Alpha"`. |
| `test_use_ma_out_of_dice` | Dice 0 → 409. |
| `test_use_ma_wrong_subclass` | Default Champion → 409. |

### `test_distracting_strike.py`
v2.99.264 — Battle Master maneuver 14 of 16 — Distracting Strike (PHB p.74). On hit, +die damage; allies have advantage on next attack vs target.

| Test | What it asserts |
|------|-----------------|
| `test_use_ds_happy` | Lv 9 Garrik d8 → `extra_damage` 1..8, `target_name` mirrored, dice 4 → 3. |
| `test_use_ds_out_of_dice` | Dice 0 → 409. |
| `test_use_ds_wrong_subclass` | Default Champion → 409. |

### `test_drunken_technique.py`
v2.99.360 — Way of the Drunken Master Monk (XGE p.33) Drunken Technique Lv 3+ (Phase G Monk Ways batch). When you use Flurry of Blows, you gain Disengage + +10 ft walking speed until end of turn. v2.158.18 (Phase 8 Monk diversification — first Monk subclass feature flipped to tracked this session, pushes the diversification arc to 9/12 classes): endpoint installs a 1-turn `drunken-technique-active` buff carrying `effects.disengage: True` (reuses Step-of-the-Wind engine flag) + two Drunken-Technique-specific flags. Different shape from the permanent-passive Phase 8 commits — a 1-turn rider that expires at next turn-start tick. v2.158.37 (Phase 2 finisher): the +10 ft speed half is now live — the buff also carries the engine-generic `effects.speed_bonus_ft: 10`, which `effective_speed_walk` folds into the `/token/move` speed cap (previously the bonus lived only under the inert `drunken_technique_speed_bonus_ft` key).

| Test | What it asserts |
|------|-----------------|
| `test_use_dt_happy_lv7` | PATCH Kael → Way of the Drunken Master Lv 7 → `disengage == True`, `speed_bonus_ft == 10`, `buff_installed == True`, broadcast (source `drunken-technique`). v2.158.18 — seeds Kael into an active battle so `_install_buff` returns True. |
| `test_dt_speed_bonus_raises_move_cap` | v2.158.37 — Phase 2 read site. A combatant carrying the `drunken-technique-active` buff (`effects.speed_bonus_ft: 10`) has its `/token/move` cap raised 30 → 40, so a 35 ft move that 409s for an unbuffed control returns 200. Exercises the `effective_speed_walk` → `effective_speed_bonus_ft` engine path. |
| `test_use_dt_wrong_subclass` | Default Kael (Open Hand) → 409. |
| `test_use_dt_wrong_class` | Caelan (Paladin) → 409. |
| `test_dt_buff_payload_carries_disengage_and_speed_flags` | v2.158.18 — installed buff carries `effects.disengage: True` + the descriptive `drunken_technique_speed_bonus_ft: 10` + `drunken_technique_rider_of: "flurry-of-blows"` + `duration_rounds == 1` + non-concentration. v2.158.37 also asserts the engine-generic `effects.speed_bonus_ft: 10`. State-change contract (Phase 9). |

### `test_evasive_footwork.py`
v2.99.263 — Battle Master maneuver 13 of 16 — Evasive Footwork (PHB p.74). Movement-tied; +die AC until movement stops.

| Test | What it asserts |
|------|-----------------|
| `test_use_ef_happy` | Lv 9 Garrik d8 → `ac_bonus` 1..8, dice 4 → 3. |
| `test_use_ef_out_of_dice` | Dice 0 → 409. |
| `test_use_ef_wrong_subclass` | Default Champion → 409. |

### `test_riposte.py`
v2.99.262 — Battle Master maneuver 12 of 16 — Riposte (PHB p.74). Reaction when missed by melee: counter-attack + die added to damage on hit.

| Test | What it asserts |
|------|-----------------|
| `test_use_ri_happy` | Lv 9 Garrik d8 → `extra_damage_on_hit` 1..8, dice 4 → 3. |
| `test_use_ri_out_of_dice` | Dice 0 → 409. |
| `test_use_ri_wrong_subclass` | Default Champion → 409. |

### `test_parry.py`
v2.99.261 — Battle Master maneuver 11 of 16 — Parry (PHB p.74). First defensive maneuver: reaction; reduce melee damage by die + DEX mod.

| Test | What it asserts |
|------|-----------------|
| `test_use_pa_happy` | Lv 9 Garrik d8 → `dex_mod == 2`, `die_roll` 1..8, `damage_reduction == die_roll + 2`, dice 4 → 3. |
| `test_use_pa_out_of_dice` | Dice 0 → 409. |
| `test_use_pa_wrong_subclass` | Default Champion → 409. |

### `test_rally.py`
v2.99.260 — Battle Master maneuver 10 of 16 — Rally (PHB p.74). Bonus action: ally gets temp HP = die + CHA mod.

| Test | What it asserts |
|------|-----------------|
| `test_use_ra_happy` | Lv 9 Garrik d8 → `cha_mod == 0` (CHA 10), `die_roll` 1..8, `temp_hp == die_roll`, ally name mirrored, dice 4 → 3. |
| `test_use_ra_out_of_dice` | Dice 0 → 409. |
| `test_use_ra_wrong_subclass` | Default Champion → 409. |

### `test_feinting_attack.py`
v2.99.259 — Battle Master maneuver 9 of 16 — Feinting Attack (PHB p.74). First per-maneuver endpoint to gate on a Phase 4 BONUS chip (bonus action; advantage + damage bump on next attack).

| Test | What it asserts |
|------|-----------------|
| `test_use_fa_happy` | Lv 9 Garrik d8 → `next_attack_advantage: True`, `extra_damage_on_hit` 1..8, `target_name == "Bandit Alpha"`, dice 4 → 3, broadcast. |
| `test_use_fa_out_of_dice` | Dice 0 → 409. |
| `test_use_fa_wrong_subclass` | Default Champion → 409. |

### `test_feinting_attack_consume.py`
v2.451.0 — Phase 1.5 follow-up of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). Feinting Attack opts into the v2.449.0 buff-consume-on-attack contract via an optional `target_combatant_id` body param. When supplied, a `feinting-attack` buff installs carrying both `attack_advantage_vs_target_combatant_id` (lit by the v2.158.53 helper for actual /attack advantage) AND `consume_on_attack: True` (dropped by the v2.449.0 walker after the first /attack). Tests reuse the Battle Master patch fixture from `test_feinting_attack.py`.

| Test | What it asserts |
|------|-----------------|
| `test_feinting_attack_without_target_combatant_no_buff` | Omit `target_combatant_id` → response + `feature_used` broadcast carry `buff_installed: False`; no `feinting-attack` buff on Garrik's combatant. Legacy GM-narrated path intact. |
| `test_feinting_attack_with_target_installs_buff` | Supply `target_combatant_id` → response + broadcast carry `buff_installed: True` + target id; buff present on Garrik with both `attack_advantage_vs_target_combatant_id` matching the target id AND `consume_on_attack: True`. |
| `test_feinting_attack_buff_consumed_after_attack` | Install buff → Garrik fires Greatsword (`attack_index: 0`) vs the marked target → v2.449.0 walker drops the buff post-resolution (verified via `/buffs`). |

### `test_sweeping_attack.py`
v2.99.258 — Battle Master maneuver 8 of 16 — Sweeping Attack (PHB p.74). Die becomes damage on a *second* target within 5 ft of the original if the same attack roll hits both.

| Test | What it asserts |
|------|-----------------|
| `test_use_sa_happy` | Lv 9 Garrik d8 → `second_target_damage` 1..8, `second_target_name == "Bandit Beta"`, dice 4 → 3. |
| `test_use_sa_out_of_dice` | Dice 0 → 409. |
| `test_use_sa_wrong_subclass` | Default Champion → 409. |

### `test_lunging_attack.py`
v2.99.257 — Battle Master maneuver 7 of 16 — Lunging Attack (PHB p.74). Melee attack only: +5 ft reach + die added to damage on hit. No save.

| Test | What it asserts |
|------|-----------------|
| `test_use_la_happy` | Lv 9 Garrik d8 → `extra_reach_ft == 5`, `extra_damage_on_hit` 1..8, dice 4 → 3, broadcast. |
| `test_use_la_out_of_dice` | Dice 0 → 409. |
| `test_use_la_wrong_subclass` | Default Champion → 409. |

### `test_precision_attack.py`
v2.99.256 — Battle Master maneuver 6 of 16 — Precision Attack (PHB p.74). First non-save maneuver: die adds to ATTACK roll (not damage).

| Test | What it asserts |
|------|-----------------|
| `test_use_pra_happy` | Lv 9 Garrik d8 → `attack_bonus` 1..8, no save fields, dice 4 → 3, broadcast (source `precision-attack`). |
| `test_use_pra_out_of_dice` | Dice 0 → 409. |
| `test_use_pra_wrong_subclass` | Default Champion → 409. |

### `test_goading_attack.py`
v2.99.255 — Battle Master maneuver 5 of 16 — Goading Attack (PHB p.74). Same shape as Menacing; on-fail effect is "disadvantage on attacks vs others than attacker."

| Test | What it asserts |
|------|-----------------|
| `test_use_ga_happy` | Lv 9 Garrik d8 → `extra_damage` 1..8, `save_dc == 16`, `save_ability == "WIS"`, dice 4 → 3, broadcast. |
| `test_use_ga_out_of_dice` | Dice 0 → 409 `out_of_uses`. |
| `test_use_ga_wrong_subclass` | Default Champion → 409. |

### `test_use_devils_sight.py`
v2.99.131 — Warlock Lv 2+ Eldritch Invocation (PHB p.110) Devil's Sight: 120 ft sight through magical+nonmagical darkness. v2.158.14 (Phase 8 Warlock diversification — first Warlock invocation flipped from announce-only to tracked): endpoint installs a permanent `devils-sight-active` buff carrying two `devils_sight_*` effect keys (`range_ft: 120`, `through_magical_darkness: True`). Phase 2 (deferred): vision/darkness resolver reads the buff.

| Test | What it asserts |
|------|-----------------|
| `test_use_devils_sight_happy_path` | Magnus has the invocation → 200 + WS `feature_used` broadcast with `source: devils-sight` + `range_ft: 120` + `buff_installed == True`. v2.158.14 — seeds Magnus into an active battle so `_install_buff` returns True. |
| `test_use_devils_sight_without_invocation_409` | Krieger (Barbarian, no invocations) → 409 `missing_invocation`. |
| `test_use_devils_sight_missing_character_id_400` | Missing `character_id` → 400. |
| `test_ds_buff_payload_carries_vision_flags` | v2.158.14 — installed buff carries `effects.devils_sight_range_ft == 120` + `effects.devils_sight_through_magical_darkness == True`. Plus permanence sanity: `concentration` falsy + `duration_rounds >= 1000`. State-change contract (Phase 9). |

### `test_use_purity_of_spirit.py`
v2.99.154 — Devotion Paladin (PHB p.87) Purity of Spirit Lv 15+ passive (Phase E.2 subclass batch). RAW: always under the effects of Protection from Evil and Good. v2.158.10 (Phase 8 step-out to Lv-15 tier): endpoint now installs a permanent `purity-of-spirit` buff carrying the same `pfeag_*` effects payload as the cast spell. The two engine read sites (`_target_attackers_have_pfeag_disadvantage_against_type` + `_pc_has_pfeag_against_type`) accept either `key="purity-of-spirit"` or `key="protection-from-evil-and-good"`.

| Test | What it asserts |
|------|-----------------|
| `test_use_purity_of_spirit_happy_path` | Caelan PATCH'd to Paladin Lv 15 → 200 + audit broadcast with 6 protected creature types + `buff_installed == True`. v2.158.10 — seeds Caelan into an active battle so `_install_buff` returns True. |
| `test_use_purity_of_spirit_below_lv_15_409` | Caelan at stock Lv 6 → 409 `missing_feature`. |
| `test_use_purity_of_spirit_missing_character_id_400` | Missing `character_id` → 400. |
| `test_pos_buff_payload_carries_pfeag_effects` | v2.158.10 — installed buff carries the four `pfeag_*` effect keys (six protected types list, attackers disadvantage flag, charm/frighten/possess immunity flag, save advantage flag). Plus permanence sanity: `concentration` falsy + `duration_rounds >= 1000`. State-change contract (Phase 9). |

### `test_pushing_attack.py`
v2.99.254 — Battle Master maneuver 4 of 16 — Pushing Attack (PHB p.74). Save ability STR; on-fail effect "pushed up to 15 ft."

| Test | What it asserts |
|------|-----------------|
| `test_use_pa_happy` | Lv 9 Garrik (d8) → `extra_damage` 1..8, `save_dc == 16`, `save_ability == "STR"`, `push_max_ft == 15`, dice 4 → 3, broadcast. |
| `test_use_pa_out_of_dice` | `superiority-dice.current = 0` → 409 `out_of_uses`. |
| `test_use_pa_wrong_subclass` | Default Garrik (Champion) → 409. |

### `test_use_thorn_whip.py`
v2.99.435 — Phase 6.3 of `docs/plans/movement-and-summons.md`. Thorn Whip (Druid/Artificer cantrip, PHB p.282): melee spell attack → on a hit, piercing damage (1d6 scaling to 2d6/3d6/4d6) + **pull the target 10 ft toward the caster** via `_force_move(pull=True)`. Third forced-move retrofit and the first to exercise the `pull` path. Caster fixture: Mira Greenleaf (demo Druid Lv 5, WIS caster, +6 to hit).

| Test | What it asserts |
|------|-----------------|
| `test_thorn_whip_pulls_target_on_hit` | Mira (placed above the bandit) loops until she hits; on the hit asserts `pull_applied` True, `pull_distance_ft == 10`, 2d6 piercing applied, and the bandit's NPC token moved −140 px (2 cells / 10 ft toward Mira). A miss applies no damage + moves nothing. NPC token created via `POST /tokens` (linked as `source_token_id`) + torn down. |
| `test_thorn_whip_wrong_class` | Krieger (Barbarian) → 409 `wrong_class`. |
| `test_thorn_whip_missing_target_400` | Missing `target_combatant_id` → 400. |
| `test_thorn_whip_target_not_in_battle_404` | Unknown target combatant → 404. |

### `test_use_thunderwave.py`
v2.99.436 — Phase 6.3 of `docs/plans/movement-and-summons.md`. Thunderwave (Bard/Druid/Sorcerer/Wizard L1, PHB p.282): each creature in the cube makes a CON save vs the caster's spell save DC; a fail takes 2d8 thunder (rolled once for the area) + is **pushed 10 ft away** from the caster via `_force_move`, a success takes half + isn't pushed. First *multi-target* forced-move retrofit. Caster fixture: Lyra Sunstrider (demo Bard, knows Thunderwave, CHA 17 / prof +3 → DC 14).

| Test | What it asserts |
|------|-----------------|
| `test_thunderwave_pushes_failed_targets` | Two bandits flank Lyra (one 10 ft above, one 10 ft below); loop until ≥1 fails its CON save, asserting per-target that a failed save → `pushed` True + token moved ±140 px (10 ft away from Lyra) and a passed save → not pushed + token unmoved. `save_dc == 14`, `any_pushed` set. Two NPC tokens created + torn down. |
| `test_thunderwave_unknown_target_per_result_error` | Unknown combatant id → 200 with a per-result `error: not_in_battle` (not a top-level 404). |
| `test_thunderwave_spell_not_known` | Krieger (Barbarian) → 409 `spell_not_known`. |
| `test_thunderwave_missing_targets_400` | Empty `target_combatant_ids` → 400. |

### `test_summon_companion.py`
v2.99.437 — Phase 7.1 of `docs/plans/movement-and-summons.md`. The summon primitive: `_summon_companion` stands up a summoned companion as a REAL combatant (NPC token + init slot + HP/AC on the combatant dict, no TokenTemplate row) so it reuses the existing damage/HP pipeline; `POST /summon_companion` wraps it and `POST /dismiss_companion` tears it down. `_read_target_ac` now honors a combatant-dict `ac`. Owner fixture: Lyra Sunstrider (demo Bard, knows Thunderwave for the deterministic damage proof).

| Test | What it asserts |
|------|-----------------|
| `test_summon_creates_combatant_and_token` | Lyra summons a Wolf → 200 with `is_summon`, `hp_max == 11`, `ac == 13`, `summoned_by == Lyra`, `source_token_id == token_id`, `initiative == 12`; a `token_add` + `battle_update` broadcast fire; the token (label "Wolf") is on the map. |
| `test_summon_is_real_combatant_takes_damage` | Lyra casts Thunderwave at her own Wolf → the per-target result shows `damage_applied > 0` (≥ half on any save → deterministic), proving the summon flows through `_apply_damage_to_combatant`. |
| `test_dismiss_removes_combatant_and_token` | Dismiss → 200 `removed`, the `token_delete` broadcast fires, the token is gone from the map, and a second dismiss → 404. |
| `test_summon_unknown_companion_400` | Unknown `companion_key` → 400 `unknown_companion`. |
| `test_dismiss_unknown_404` | Dismiss an unknown combatant id → 404. |

### `test_use_spiritual_weapon.py`
v2.99.438 — Phase 7.1 of `docs/plans/movement-and-summons.md`. The first summon retrofit: `/use_spiritual_weapon` (Cleric L2) stands up the floating spectral-weapon combatant via `_summon_companion` (`spiritual-weapon` entry) and, when a `target_combatant_id` is supplied, makes the melee spell attack server-side (1d20 + prof + spellcasting mod vs AC) + applies 1d8 + mod force damage on a hit. Caster fixture: Brother Tavik Stonebrow (demo Cleric Lv 6, WIS 16 / prof +3 → +6 to hit).

| Test | What it asserts |
|------|-----------------|
| `test_spiritual_weapon_summon_only` | No target → `attacked` False; the `spiritual-weapon` summon combatant appears (`is_summon`, 1 HP, `summoned_by` Tavik) with a token + `token_add` broadcast. Dismissed after. |
| `test_spiritual_weapon_attacks_target` | Loop a fresh weapon each cast until Tavik hits a bandit → `damage_type == "force"`, `damage_rolled`/`damage_applied > 0`. Each cast's weapon is dismissed to avoid board accumulation. |
| `test_spiritual_weapon_spell_not_known` | Krieger (Barbarian) → 409 `spell_not_known`. |

### `test_summon_rest_teardown.py`
v2.99.439 — Phase 7.1 of `docs/plans/movement-and-summons.md`. Closes the companion-lifecycle-leak risk: a long rest drops the resting character's summons (`_teardown_summons_for_owner` — combatant + token), a short rest leaves them. Owner fixture: Lyra Sunstrider.

| Test | What it asserts |
|------|-----------------|
| `test_long_rest_drops_summons` | Lyra summons a Wolf, then long-rests → the combatant id is in `dismissed_summons`, the token is deleted from the map, and a follow-up manual dismiss → 404. |
| `test_short_rest_keeps_summons` | After a refill long rest, Lyra summons a Wolf + short-rests → no `dismissed_summons` field and the token is still on the map (summon survives). |

### `test_cast_find_familiar.py`
v2.99.440 — Phase 7.2 of `docs/plans/movement-and-summons.md`. The second summon retrofit: `/cast_find_familiar` (Wizard L1 ritual) stands up the tiny non-combat `familiar` companion in a chosen animal form via `_summon_companion`. Gates on knowing Find Familiar OR being a Wizard / Artificer. Caster fixture: Thalindra Moonwhisper (demo Wizard).

| Test | What it asserts |
|------|-----------------|
| `test_find_familiar_summons_companion` | Thalindra conjures an owl familiar → `is_summon`, `companion_key == "familiar"`, `name == "Familiar (owl)"`, `ac == 11`, 1 HP, `summoned_by` Thalindra; a `token_add` broadcast + the token (matching label) on the map. Dismissed after. |
| `test_find_familiar_cannot_cast` | Krieger (Barbarian) → 409 `cannot_cast`. |

### `test_use_animal_companion.py`
v2.99.441 — Phase 7.2 of `docs/plans/movement-and-summons.md`. The third summon retrofit: `/use_animal_companion` (Beast Master Ranger Lv 3+) stands up the beast companion (HP = max(beast HP, 4 × ranger level), AC = 13 + prof) via `_summon_companion` and, when a `target_combatant_id` is supplied, makes the beast's bite (2d4 + STR-mod piercing on a hit). The demo Ranger (Rowan Quickbow) is a Hunter, so the happy paths PATCH his subclass to Beast Master then restore.

| Test | What it asserts |
|------|-----------------|
| `test_animal_companion_summon_only` | No target → `attacked` False; the beast combatant has `companion_hp == 20` (max(11, 4×5)), `companion_ac == 16` (13 + prof 3), `is_summon`, `companion_key == "beast-companion"`, `summoned_by` Rowan. Dismissed after. |
| `test_animal_companion_bites_target` | Loop a fresh companion each cast until the bite hits a bandit → `damage_type == "piercing"`, `damage_rolled`/`damage_applied > 0`. Each companion dismissed. |
| `test_animal_companion_wrong_subclass` | Default Rowan (Hunter) → 409 `wrong_subclass_or_level`. |

### `test_use_steel_defender.py`
v2.99.442 — Phase 7.2 of `docs/plans/movement-and-summons.md`. The fourth summon retrofit: `/use_steel_defender` (Battle Smith Artificer Lv 3+) stands up the construct companion (HP = 2 + INT mod + 5 × level, AC 15) via `_summon_companion` and, when a `target_combatant_id` is supplied, makes its Force-Empowered Rend (1d8 + prof force on a hit). No demo Artificer, so the happy paths PATCH Thalindra's subclass to Battle Smith then restore (her Lv 5 / INT 16 stand in → defender HP 30).

| Test | What it asserts |
|------|-----------------|
| `test_steel_defender_summon_only` | No target → `attacked` False; the construct has `defender_hp == 30`, `defender_ac == 15`, `is_summon`, `companion_key == "steel-defender"`, `summoned_by` the artificer. Dismissed after. |
| `test_steel_defender_rends_target` | Loop a fresh defender each cast until the Rend hits a bandit → `damage_type == "force"`, `damage_rolled`/`damage_applied > 0`. Each defender dismissed. |
| `test_steel_defender_wrong_subclass` | Default Thalindra (Evocation) → 409 `wrong_subclass_or_level`. |

### `test_cast_conjure_animals.py`
v2.99.443 — Phase 7.2 of `docs/plans/movement-and-summons.md`; v2.414.0 — Phase 3 summon-count scaling (first consumer of `_SPELL_SUMMON_MAP`). The first *multi*-summon: `/cast_conjure_animals` (Druid/Ranger L3) stands up wolf combatants on their own grid cells via repeated `_summon_companion` calls. `count` is now the *base* summoning option (1–8); the total = `base_count × multiplier`, where the multiplier is read from the substrate by `slot_level` (×2 @5th, ×3 @7th, ×4 @9th; ×1 at base L3–L4). Gates on knowing Conjure Animals OR being a Druid / Ranger. Caster fixture: Mira Greenleaf (demo Druid).

| Test | What it asserts |
|------|-----------------|
| `test_conjure_animals_eight_wolves` | The default → `count == 8`, 8 distinct summon combatants (all `is_summon`, `companion_key == "wolf"`, `summoned_by` Mira) + 8 tokens at x positions spaced 70 px apart from 700. All dismissed after. |
| `test_conjure_animals_count_clamp` | `count=2` → exactly two wolves. |
| `test_conjure_animals_base_slot_multiplier_one` | Explicit `slot_level=3` → `base_count 2`, `multiplier 1`, `count 2` (legacy behavior preserved at base slot). |
| `test_conjure_animals_l5_doubles` | `slot_level=5`, base 2 → `multiplier 2`, `count 4`, 4 wolves. |
| `test_conjure_animals_l7_triples` | `slot_level=7`, base 2 → `multiplier 3`, `count 6`, 6 wolves. |
| `test_conjure_animals_l9_quadruples` | `slot_level=9`, base 1 → `multiplier 4`, `count 4`, 4 wolves. |
| `test_conjure_animals_cannot_cast` | Krieger (Barbarian) → 409 `cannot_cast`. |

### `test_cast_conjure_woodland_beings.py`
v2.415.0 — Phase 3 multiplier-family second consumer. `/cast_conjure_woodland_beings` (Druid L4) mirrors `/cast_conjure_animals`'s shape but with base_level 4, a ×1/×2/×3 ladder (L4–L5/L6–L7/L8–L9; no ×4 RAW), and a Druid-only class gate. New `_COMPANION_TEMPLATES["fey-spirit"]` (AC 13, HP 7, walk 30, color `#a48cc8`) is the summoned token template. Caster fixture: Mira Greenleaf (demo Druid).

| Test | What it asserts |
|------|-----------------|
| `test_cwb_base_slot_no_multiplier` | L4 default → `base_count 8`, `multiplier 1`, `count 8`, 8 fey-spirit summons. |
| `test_cwb_l5_still_base_tier` | L5 stays in the L4–L5 tier → `multiplier 1`, base 2 → 2 fey. |
| `test_cwb_l6_doubles` | L6 enters the second tier → `multiplier 2`, base 2 → 4 fey. |
| `test_cwb_l8_triples` | L8 enters the third tier → `multiplier 3`, base 2 → 6 fey. |
| `test_cwb_l9_last_tier_fallback` | L9 falls through the last-tier fallback → `multiplier 3` (no ×4), base 1 → 3 fey. |
| `test_cwb_cannot_cast_non_druid` | Krieger (Barbarian) → 409 `cannot_cast` with `expected` mentioning "druid". |

### `test_cast_conjure_minor_elementals.py`
v2.416.0 — Phase 3 multiplier-family third (and final) consumer, closing the count-multiplier family. `/cast_conjure_minor_elementals` (Druid / Wizard L4) mirrors `/cast_conjure_woodland_beings`'s shape (base_level 4, ×1/×2/×3 ladder, no ×4) with one difference: a Druid **or Wizard** class gate. New `_COMPANION_TEMPLATES["elemental-spirit"]` (AC 13, HP 10, walk 30, ember color `#d2691e`) is the summoned token template. Caster fixtures: Mira Greenleaf (Druid) for the ladder; Thalindra Moonwhisper (Wizard) for the Wizard-branch gate.

| Test | What it asserts |
|------|-----------------|
| `test_cme_base_slot_no_multiplier` | L4 default → `base_count 8`, `multiplier 1`, `count 8`, 8 elemental-spirit summons. |
| `test_cme_l5_still_base_tier` | L5 stays in the L4–L5 tier → `multiplier 1`, base 2 → 2 elementals. |
| `test_cme_l6_doubles` | L6 enters the second tier → `multiplier 2`, base 2 → 4 elementals. |
| `test_cme_l8_triples` | L8 enters the third tier → `multiplier 3`, base 2 → 6 elementals. |
| `test_cme_l9_last_tier_fallback` | L9 falls through the last-tier fallback → `multiplier 3` (no ×4), base 1 → 3 elementals. |
| `test_cme_wizard_can_cast` | Thalindra (Wizard) passes the Druid/Wizard gate → L6 base 2 → 4 elementals (the difference from Woodland Beings' Druid-only gate). |
| `test_cme_cannot_cast_non_caster` | Krieger (Barbarian) → 409 `cannot_cast` with `expected` mentioning "wizard". |

### `test_cast_animate_dead.py`
v2.417.0 — Phase 3 first count-*additive* consumer (a second summon-scaling shape after the multiplier family). `/cast_animate_dead` (Cleric / Wizard L3) reads the new sibling `_SPELL_SUMMON_ADDITIVE_MAP` via `_spell_summon_additive_for_slot()`: count is fully slot-determined (`1 + 2 × (slot − 3)`) with no chosen base-option `count`. New `_COMPANION_TEMPLATES["undead-servant"]` (AC 13, HP 13, walk 30, bone color `#cfcabe`) is the summoned token template. Caster fixtures: Brother Tavik Stonebrow (Cleric) for the ladder; Thalindra Moonwhisper (Wizard) for the Wizard-branch gate.

| Test | What it asserts |
|------|-----------------|
| `test_animate_dead_base_slot_one` | L3 base → `count 1`, exactly 1 undead-servant summon (`is_summon`, `companion_key == "undead-servant"`, `summoned_by` Tavik). |
| `test_animate_dead_l4_three` | L4 → `count 3` (1 + 2), 3 undead. |
| `test_animate_dead_l5_five` | L5 → `count 5` (1 + 2×2), 5 undead. |
| `test_animate_dead_l9_thirteen` | L9 → `count 13` (1 + 2×6), 13 undead (top of the ladder). |
| `test_animate_dead_wizard_can_cast` | Thalindra (Wizard) passes the Cleric/Wizard gate → L4 = 3 undead. |
| `test_animate_dead_cannot_cast_non_caster` | Krieger (Barbarian) → 409 `cannot_cast` with `expected` mentioning "cleric". |

### `test_cast_conjure_elemental.py`
v2.418.0 — Phase 3 first **CR-increase** consumer (the third and final summon-scaling shape after the multiplier and additive families). `/cast_conjure_elemental` (Druid / Wizard L5) reads the new sibling `_SPELL_SUMMON_CR_MAP` via `_spell_summon_cr_for_slot()`: the summon count stays fixed at 1, but the elemental's challenge rating is slot-determined (`5 + 1 × (slot − 5)`). Reuses the `elemental-spirit` companion template. Caster fixtures: Mira Greenleaf (Druid) for the CR ladder; Thalindra Moonwhisper (Wizard) for the Wizard-branch gate.

| Test | What it asserts |
|------|-----------------|
| `test_conjure_elemental_base_slot_cr5` | L5 base → `count 1`, `challenge_rating 5`, exactly 1 elemental-spirit summon (`is_summon`, `companion_key == "elemental-spirit"`, `summoned_by` Mira). |
| `test_conjure_elemental_l6_cr6` | L6 → `challenge_rating 6` (+1 per slot above 5th), still `count 1`. |
| `test_conjure_elemental_l9_cr9` | L9 → `challenge_rating 9` (top of the ladder), still `count 1`. |
| `test_conjure_elemental_wizard_can_cast` | Thalindra (Wizard) passes the Druid/Wizard gate → L5 = CR 5, 1 elemental. |
| `test_conjure_elemental_cannot_cast_non_caster` | Krieger (Barbarian) → 409 `cannot_cast` with `expected` mentioning "druid". |

### `test_cast_conjure_fey.py`
v2.419.0 — Phase 3 second **CR-increase** consumer, after Conjure Elemental. `/cast_conjure_fey` (Druid / Warlock L6) reuses `_SPELL_SUMMON_CR_MAP` via `_spell_summon_cr_for_slot()`: count fixed at 1, the fey's CR slot-determined (`6 + 1 × (slot − 6)`). Reuses the `fey-spirit` companion template. Caster fixtures: Mira Greenleaf (Druid) for the CR ladder; Magnus Hexbinder (Warlock) for the Warlock-branch gate.

| Test | What it asserts |
|------|-----------------|
| `test_conjure_fey_base_slot_cr6` | L6 base → `count 1`, `challenge_rating 6`, exactly 1 fey-spirit summon (`is_summon`, `companion_key == "fey-spirit"`, `summoned_by` Mira). |
| `test_conjure_fey_l7_cr7` | L7 → `challenge_rating 7` (+1 per slot above 6th), still `count 1`. |
| `test_conjure_fey_l9_cr9` | L9 → `challenge_rating 9` (top of the ladder), still `count 1`. |
| `test_conjure_fey_warlock_can_cast` | Magnus (Warlock) passes the Druid/Warlock gate → L6 = CR 6, 1 fey. |
| `test_conjure_fey_cannot_cast_non_caster` | Krieger (Barbarian) → 409 `cannot_cast` with `expected` mentioning "druid". |

### `test_cast_conjure_celestial.py`
v2.420.0 — Phase 3's final consumer and the **tier-walk** CR-increase shape (closes Phase 3). `/cast_conjure_celestial` (Cleric L7) reads the new sibling `_SPELL_SUMMON_CR_TIER_MAP` via `_spell_summon_cr_tier_for_slot()`: count fixed at 1, the celestial's CR is a non-linear tier (CR 4 at L7–8, CR 5 at L9) the linear helper can't express. New `_COMPANION_TEMPLATES["celestial-spirit"]` (AC 14, HP 18, walk 30, gold `#f0d060`). Caster fixture: Brother Tavik Stonebrow (Cleric) for the ladder.

| Test | What it asserts |
|------|-----------------|
| `test_conjure_celestial_base_slot_cr4` | L7 base → `count 1`, `challenge_rating 4`, exactly 1 celestial-spirit summon (`is_summon`, `companion_key == "celestial-spirit"`, `summoned_by` Tavik). |
| `test_conjure_celestial_l8_still_cr4` | L8 → `challenge_rating 4` (same tier; the bump only lands at L9), still `count 1`. |
| `test_conjure_celestial_l9_cr5` | L9 → `challenge_rating 5` (top tier), still `count 1`. |
| `test_conjure_celestial_cannot_cast_non_caster` | Krieger (Barbarian) → 409 `cannot_cast` with `expected` mentioning "cleric". |

### `test_cast_magic_weapon.py`
v2.421.0 — **opens Phase 4** (rider/bonus scaling). `/cast_magic_weapon` (Cleric/Wizard L2) reads the new `_SPELL_BONUS_MAP` via `_spell_bonus_for_slot()` — a `(max_slot_inclusive, bonus)` tier walk (+1 @L2–3, +2 @L4–5, +3 @L6+) mirroring the Phase 3 CR tier-walk. The cast installs a 1-hour non-concentration Magic Weapon buff on the target (caster by default, or `target_character_id`) carrying scaled `weapon_attack_bonus` / `weapon_damage_bonus` effects (display-only convention, same as Bless's `bless_attack_bonus`); the install requires an active battle. Caster fixtures: Brother Tavik Stonebrow (Cleric) for the ladder, Thalindra Moonwhisper (Wizard) for the gate.

| Test | What it asserts |
|------|-----------------|
| `test_magic_weapon_base_slot_plus1` | Tavik L2 → `bonus 1`, `buff_installed True`, `target_character_id` is the caster; the persisted battle's `magic-weapon` buff carries `weapon_attack_bonus == 1`, `weapon_damage_bonus == 1`, `concentration False`. |
| `test_magic_weapon_l4_plus2` | L4 → `bonus 2` (middle tier); buff effects carry +2 on both attack and damage. |
| `test_magic_weapon_l6_plus3` | L6 → `bonus 3` (top tier); buff effects carry +3. |
| `test_magic_weapon_wizard_caster_passes_gate` | Thalindra (Wizard, not Cleric) passes the caster gate → `bonus 1`, `buff_installed True`. |
| `test_magic_weapon_cannot_cast_non_caster` | Krieger (Barbarian) → 409 `cannot_cast` with `expected` mentioning "cleric". |

### `test_cast_elemental_weapon.py`
v2.422.0 — second Phase 4 rider/bonus consumer, and the first to scale **two** riders off one tier value. `/cast_elemental_weapon` (Ranger/Paladin L3) reuses `_SPELL_BONUS_MAP` via `_spell_bonus_for_slot()`: the integer N drives both a `+N` attack bonus and an `Nd4` extra-damage die (+1/1d4 @L3–4, +2/2d4 @L5–6, +3/3d4 @L7+). Unlike Magic Weapon it's **concentration** and carries a player-chosen element (acid/cold/fire/lightning/thunder, default fire). The 1-hour buff carries `weapon_attack_bonus` / `weapon_bonus_damage_dice` / `weapon_bonus_damage_type` effects; install requires an active battle. Caster fixtures: Rowan Quickbow (Ranger) for the ladder, Sir Caelan Lightbringer (Paladin) for the gate.

| Test | What it asserts |
|------|-----------------|
| `test_elemental_weapon_base_slot_plus1_1d4` | Rowan L3 → `bonus 1`, `bonus_dice "1d4"`, `damage_type "fire"`, `buff_installed True`; the persisted `elemental-weapon` buff carries `weapon_attack_bonus == 1`, `weapon_bonus_damage_dice == "1d4"`, `weapon_bonus_damage_type == "fire"`, `concentration True`. |
| `test_elemental_weapon_l5_plus2_2d4` | L5 → `bonus 2`, `bonus_dice "2d4"` (middle tier); buff effects carry +2 / 2d4. |
| `test_elemental_weapon_l7_plus3_3d4_cold` | L7 → `bonus 3`, `bonus_dice "3d4"` (top tier); an explicit `damage_type "cold"` is honored end-to-end (response + buff effects). |
| `test_elemental_weapon_paladin_caster_passes_gate` | Sir Caelan (Paladin, not Ranger) passes the caster gate → `bonus 1`, `buff_installed True`. |
| `test_elemental_weapon_cannot_cast_non_caster` | Krieger (Barbarian) → 409 `cannot_cast` with `expected` mentioning "ranger". |

### `test_cast_false_life.py`
v2.423.0 — third Phase 4 rider/bonus consumer, and the first **linear-additive** shape. `/cast_false_life` (Sorcerer/Wizard L1) reads the new sibling `_SPELL_BONUS_ADDITIVE_MAP` via `_spell_bonus_additive_for_slot()`: a flat +5 temp HP per slot above 1st (no plateau, unlike the tier-walk weapon buffs). The endpoint rolls the 1d4+4 base server-side, adds the additive bonus, and grants the total via `_grant_temp_hp` (RAW non-stacking) — self-only, non-concentration, no battle needed. Deterministic assertions target the additive `bonus` and the `temp_hp == base_roll + bonus` identity (the 1d4+4 base is range-checked, not pinned). Caster fixtures: Thalindra Moonwhisper (Wizard) for the ladder, Zara Emberfire (Sorcerer) for the gate.

| Test | What it asserts |
|------|-----------------|
| `test_false_life_base_slot_bonus0` | Thalindra L1 → `bonus 0`, `base_roll` in [5, 8], `temp_hp == base_roll`, `temp_hp_applied` a bool. |
| `test_false_life_l2_bonus5` | L2 → `bonus 5`; `temp_hp == base_roll + 5`. |
| `test_false_life_l3_bonus10` | L3 → `bonus 10` (linear, no plateau). |
| `test_false_life_l5_bonus20` | L5 → `bonus 20` (4 slots above 1st × 5); confirms the unbounded climb. |
| `test_false_life_sorcerer_caster_passes_gate` | Zara (Sorcerer, not Wizard) passes the caster gate → `bonus 0`, `feature "false-life"`. |
| `test_false_life_cannot_cast_non_caster` | Krieger (Barbarian) → 409 `cannot_cast` with `expected` mentioning "sorcerer". |

### `test_cast_gust.py`
v2.99.445 — Phase 6.3 of `docs/plans/movement-and-summons.md`. Gust (Druid/Sorcerer/Wizard cantrip, Tasha's p.106): the target makes a STR save vs the spell save DC or is pushed 5 ft away via `_force_move`. The last forced-mover. Caster fixture: Thalindra Moonwhisper (demo Wizard).

| Test | What it asserts |
|------|-----------------|
| `test_gust_pushes_target_on_failed_save` | Thalindra (above the bandit) loops until it fails its STR save → `push_applied` True + the bandit's NPC token moved +70 px (5 ft / 1 cell away); a passed save moves nothing. NPC token created + torn down. |
| `test_gust_cannot_cast` | Krieger (Barbarian) → 409 `cannot_cast`. |
| `test_gust_missing_target_400` | Missing `target_combatant_id` → 400. |

### `test_menacing_attack.py`
v2.99.253 — Battle Master maneuver 3 of 16 — Menacing Attack (PHB p.74). Mirrors Trip/Disarming but save ability is WIS and on-fail is Frightened.

| Test | What it asserts |
|------|-----------------|
| `test_use_ma_happy` | Lv 9 Garrik (Battle Master, d8) → `extra_damage` in 1..8, `save_dc == 16`, `save_ability == "WIS"`, dice 4 → 3, broadcast (source `menacing-attack`). |
| `test_use_ma_out_of_dice` | `superiority-dice.current = 0` → 409 `out_of_uses`. |
| `test_use_ma_wrong_subclass` | Default Garrik (Champion) → 409 `wrong_subclass_or_level`. |

### `test_disarming_attack.py`
v2.99.252 — Battle Master maneuver 2 of 16 — Disarming Attack (PHB p.74). Mirrors Trip Attack's shape; on-fail effect is "drop one held object" vs Prone.

| Test | What it asserts |
|------|-----------------|
| `test_use_da_happy` | Lv 9 Garrik (Battle Master, d8) → `extra_damage` in 1..8, `save_dc == 16` (prof +4 + max(STR +4, DEX +2)), dice 4 → 3, broadcast (source `disarming-attack`). |
| `test_use_da_out_of_dice` | `superiority-dice.current = 0` → 409 `out_of_uses`. |
| `test_use_da_wrong_subclass` | Default Garrik (Champion) → 409 `wrong_subclass_or_level`. |
| `test_use_da_level_gate` | Battle Master at Lv 2 → 409. |

### `test_trip_attack.py`
v2.99.233 — Battle Master Fighter (PHB p.74) Combat Superiority pool + Trip Attack maneuver (Phase 1 of [docs/plans/battle-master.md](../plans/battle-master.md)). Garrik Ironside is the demo fixture; tests PATCH his subclass to "Battle Master" + seed a `superiority-dice` resource.

| Test | What it asserts |
|------|-----------------|
| `test_use_trip_attack_happy` | Lv 9 Garrik (Battle Master, d8 die) → `extra_damage` in 1..8, `save_dc == 16` (prof +4 + max(STR +4, DEX +2)), dice 4 → 3 + broadcast (source `trip-attack`). |
| `test_use_trip_attack_out_of_dice` | `superiority-dice.current = 0` → 409 `out_of_uses`. |
| `test_use_trip_attack_wrong_subclass` | Default Garrik (Champion) → 409 `wrong_subclass_or_level`. |
| `test_use_trip_attack_level_gate` | Battle Master at Lv 2 (not 3+) → 409. |

### `test_weapon_bond.py`
v2.99.232 — Eldritch Knight Fighter (PHB p.74) Weapon Bond (Phase 1 of [docs/plans/eldritch-knight.md](../plans/eldritch-knight.md)). Garrik Ironside is the demo fixture; tests PATCH his subclass to "Eldritch Knight".

| Test | What it asserts |
|------|-----------------|
| `test_use_weapon_bond_happy` | Bond Greatsword (index 0) → `bonded_weapons == ["greatsword"]` + broadcast (source `weapon-bond`). |
| `test_use_weapon_bond_second_weapon` | Greatsword then Glaive → `bonded_weapons` length 2. |
| `test_use_weapon_bond_cap_reached` | Two already bonded → third attempt → 409 `cap_reached` (RAW max 2). |
| `test_use_weapon_bond_wrong_subclass` | Default Garrik (Champion) → 409 `wrong_subclass_or_level`. |
| `test_use_weapon_bond_level_gate` | Eldritch Knight at Lv 2 (not 3+) → 409. |
| `test_use_weapon_bond_non_weapon` | `weapon_index` pointing at Chain mail (armor) → 400. |

### `test_wild_magic_spell_bombardment.py`
v2.99.231 — Wild Magic Sorcerer (PHB p.103) Spell Bombardment (Phase 5 of [docs/plans/wild-magic.md](../plans/wild-magic.md), final phase). Once-per-turn flag tracked via `combatant.economy.spell_bombardment_used` (mirror of Colossus Slayer's v2.60.0 flag). v2.158.15 (Phase 8 Sorcerer diversification — closes the six-class arc): endpoint now installs a permanent `spell-bombardment-active` buff carrying three `spell_bombardment_*` parameter flags. v2.158.44 (Phase 2): `/cast_spell` reads the buff + the once-per-turn flag via `_pc_spell_bombardment_params` / `_is_spell_bombardment_used` on a damage-spell cast and surfaces a `spell_bombardment_available` reroll advisory (max-die detection + reroll stays on the player-invoked `/use_spell_bombardment` endpoint).

| Test | What it asserts |
|------|-----------------|
| `test_use_spell_bombardment_happy` | Lv 18 Wild Magic Zara, `die_size: 8` → `extra_damage` in 1..8, `buff_installed == True`, broadcast (source `spell-bombardment`). v2.158.15 — happy test gains the buff assertion. |
| `test_use_spell_bombardment_once_per_turn` | First call succeeds; second call same turn → 409 `once_per_turn`. |
| `test_use_spell_bombardment_bad_die_size` | `die_size: 5` → 400 (only 4/6/8/10/12 allowed). |
| `test_use_spell_bombardment_wrong_subclass` | Default Draconic Bloodline → 409 `wrong_subclass_or_level`. |
| `test_use_spell_bombardment_level_gate` | Wild Magic at Lv 17 (not 18+) → 409. |
| `test_sb_buff_payload_carries_parameter_flags` | v2.158.15 — installed buff carries three `spell_bombardment_*` effect keys (active=True, die_sizes=[4,6,8,10,12], uses_per_turn=1) + permanence sanity. State-change contract (Phase 9). Pins the Phase-2 contract so the future `/cast_spell` read site has stable flag names. |
| `test_sb_cast_damage_spell_surfaces_advisory` | v2.158.44 — Phase 2 read site: a Lv 18 Wild Magic Zara carrying `spell-bombardment-active` (unused once-per-turn flag) who casts a damage cantrip (Fire Bolt, injected) sees `/cast_spell` return `spell_bombardment_available == True` + `spell_bombardment_uses_remaining == 1` + the eligible die sizes. |
| `test_sb_advisory_not_surfaced_on_non_damage_spell` | v2.158.44 — control: with the buff + unused flag, casting Light (no damage dice) reports `spell_bombardment_available == False` + `uses_remaining == 0` + empty die sizes. Pins the damage-spell gate. |

### `test_wild_magic_controlled_chaos.py`
v2.99.230 — Wild Magic Sorcerer (PHB p.103) Controlled Chaos (Phase 4 of [docs/plans/wild-magic.md](../plans/wild-magic.md)). Lv 14+ Wild Magic Sorcerers roll the surge table twice and pick. Uses TEST_MODE `_force_surge_d20: 1` on `/cast_spell` for determinism.

| Test | What it asserts |
|------|-----------------|
| `test_controlled_chaos_rolls_twice_at_lv14` | Lv 14 Wild Magic Zara casts Magic Missile with forced d20=1 → `wild_magic_surge` broadcast carries `controlled_chaos: true` + `alternatives` length 2 (each with slug/name/d100). |
| `test_controlled_chaos_single_entry_at_lv5` | Lv 5 Wild Magic Zara → broadcast `controlled_chaos: false` + `alternatives` length 1 (regression for the v2.99.230 backward-compat shape). |

### `test_wild_magic_bend_luck.py`
v2.99.229 — Wild Magic Sorcerer (PHB p.103) Bend Luck reaction (Phase 3 of [docs/plans/wild-magic.md](../plans/wild-magic.md)). Zara Emberfire is the demo fixture; tests PATCH her subclass to "Wild Magic" + level to 6.

| Test | What it asserts |
|------|-----------------|
| `test_use_bend_luck_bonus` | Bonus mode → SP 5 → 3, `d4` in 1..4, `signed > 0`, broadcast fired. |
| `test_use_bend_luck_penalty` | Penalty mode → `signed < 0` and equals `-d4`. |
| `test_use_bend_luck_out_of_sp` | SP at 1 → 409 `out_of_uses` (RAW: costs 2 SP). |
| `test_use_bend_luck_wrong_subclass` | Default Draconic Bloodline → 409 `wrong_subclass_or_level`. |
| `test_use_bend_luck_level_gate` | Wild Magic at Lv 5 (not 6+) → 409. |
| `test_use_bend_luck_bad_mode` | `mode: "sideways"` → 400. |

### `test_wild_magic_surge.py`
v2.99.228 — Wild Magic Sorcerer (PHB p.103) Wild Magic Surge auto-roll (Phase 2 of [docs/plans/wild-magic.md](../plans/wild-magic.md)). Zara Emberfire is the demo fixture; tests PATCH her subclass to "Wild Magic". Uses the TEST_MODE-only `_force_surge_d20` body param on /cast_spell for deterministic outcomes.

| Test | What it asserts |
|------|-----------------|
| `test_wild_magic_surge_fires_on_d20_one` | Wild Magic Zara casts Magic Missile (Lv 1) with `_force_surge_d20: 1` → `wild_magic_surge` broadcast with table entry (slug, name, desc, d100, tides_refilled). |
| `test_wild_magic_surge_refills_tides_of_chaos` | After surge fires with `tides_of_chaos_uses` at 0 pre-cast, a follow-up `/use_tides_of_chaos` succeeds (RAW refill on DM-triggered surge). |
| `test_wild_magic_no_surge_on_d20_high` | `_force_surge_d20: 20` → no surge broadcast (only natural 1 triggers). |
| `test_wild_magic_cantrip_no_surge` | Cantrip cast with `_force_surge_d20: 1` → no surge (RAW gates on Lv 1+ spell). |
| `test_wild_magic_non_subclass_no_surge` | Default Draconic Bloodline Zara with `_force_surge_d20: 1` → no surge (subclass gate). |

### `test_wild_magic_tides.py`
v2.99.227 — Wild Magic Sorcerer (PHB p.103) Tides of Chaos (Phase 1 of [docs/plans/wild-magic.md](../plans/wild-magic.md)). Zara Emberfire is the demo fixture; tests PATCH her subclass to "Wild Magic" + counter to 1.

| Test | What it asserts |
|------|-----------------|
| `test_use_tides_of_chaos_happy_path` | Wild Magic Zara counter 1 → 200, `uses_remaining == 0`, buff installed, broadcast. |
| `test_use_tides_of_chaos_out_of_uses` | Second invocation on the same turn → 409 `out_of_uses`. |
| `test_use_tides_of_chaos_wrong_class` | Krieger (Barbarian) → 409 `wrong_subclass_or_level`. |
| `test_use_tides_of_chaos_wrong_subclass` | Zara default (Draconic Bloodline) → 409 `wrong_subclass_or_level`. |
| `test_tides_of_chaos_long_rest_refill` | Consume → /rest long → second use succeeds (counter refilled to 1). Exercises the v2.99.227 `subclass` class-scope fix that keeps the PATCH'd subclass through normalize_dnd5e_sheet. |
| `test_tides_of_chaos_grants_advantage_and_consumes` | v2.158.46 Phase 2 read site: install the buff → a d20 ability check expands to `2d20kh1` + breakdown mentions "Tides of Chaos"; a second roll is a straight `1d20` (one-shot consume). |

### `test_berserker_path.py`
v2.99.226 — Path of the Berserker (PHB p.49) Frenzy (Lv 3) + Intimidating Presence (Lv 10). Krieger Stonefist is the demo fixture; IP test PATCHes him Lv 7 → 10.

| Test | What it asserts |
|------|-----------------|
| `test_use_frenzy_after_rage` | `/use_rage` to install the rage buff, then `/use_frenzy` → 200 + `feature_used` broadcast (source `frenzy`). |
| `test_use_frenzy_without_rage` | No rage buff → 409 `not_raging`. |
| `test_use_frenzy_wrong_class` | Pip (Rogue) → 409 `wrong_subclass_or_level`. |
| `test_use_intimidating_presence_at_lv10` | Krieger PATCH'd to Lv 10 → `dc == 10` (sheet prof +3 unchanged on level PATCH; CHA 8 → -1; 8 + 3 + (-1) = 10) + `target_name == "Bandit"` + broadcast. |
| `test_use_intimidating_presence_level_gate` | Control: Krieger at Lv 7 → 409 `wrong_subclass_or_level`. |

### `test_evocation_school.py`
v2.99.225 — Evocation Wizard (PHB p.117) Sculpt Spells (Lv 2) + Empowered Evocation (Lv 10). Thalindra Moonwhisper is the demo fixture; Empowered Evocation test PATCHes her Lv 7 → 10.

| Test | What it asserts |
|------|-----------------|
| `test_use_sculpt_spells_lv3_fireball` | Thalindra at Lv 7 with `spell_level=3` → `protected_count == 4` + sculpt-spells broadcast. |
| `test_use_sculpt_spells_bad_level` | `spell_level=0` → 400. |
| `test_use_sculpt_spells_wrong_class` | Krieger (Barbarian) → 409 `wrong_subclass_or_level`. |
| `test_use_empowered_evocation_at_lv10` | Thalindra PATCH'd to Lv 10 → `int_mod == 3` (INT 16) + empowered-evocation broadcast. |
| `test_use_empowered_evocation_level_gate` | Control: Thalindra at Lv 7 → 409 `wrong_subclass_or_level`. |

### `test_use_arcane_recovery.py`
Wizard Arcane Recovery: half-level slot refund.

| Test | What it asserts |
|------|-----------------|
| `test_arcane_recovery_happy_path` | Refunds requested slots up to the level/2 allowance. |
| `test_arcane_recovery_allowance` | Allowance maxes at `ceil(wiz_level/2)`. |
| `test_arcane_recovery_l6_rejected` | L6 slot rejected (RAW). |
| `test_arcane_recovery_missing_slots` | Empty body → 400. |
| `test_arcane_recovery_invalid_slot_entry` | Non-int level → 400. |
| `test_arcane_recovery_wrong_class` | Non-Wizard → 409. |
| `test_arcane_recovery_missing_character_id` | 400. |

### `test_use_bardic_inspiration.py`
Bard grants a Bardic Inspiration die to a target (Phase C resource).

| Test | What it asserts |
|------|-----------------|
| `test_bi_happy_path` | Adds BI die to target; decrements bard's counter. |
| `test_bi_missing_fields` | Missing target → 400. |
| `test_bi_self_target` | Bard grants to themselves → succeeds (RAW edge case). |
| `test_bi_no_bard_resource` | Non-Bard caller → 409. |
| `test_bi_unknown_target` | Unknown target id → 404. |

### `test_use_cutting_words.py`
Bardic Inspiration die used as a reaction debuff (College of Lore).

| Test | What it asserts |
|------|-----------------|
| `test_cutting_words_happy_path` | Rolls a BI die, broadcasts a `feature_used` describing the subtraction. |
| `test_cutting_words_no_target` | Generic broadcast text when no target was passed. |
| `test_cutting_words_target_name_fallback` | `target_name` alone is acceptable. |
| `test_cutting_words_target_character_id_wins` | Explicit char_id beats name. |
| `test_cutting_words_missing_character_id` | 400. |
| `test_cutting_words_unknown_character` | 404. |
| `test_cutting_words_wrong_class` | Non-Bard caller → 409. |
| `test_cutting_words_out_of_uses` | BI counter exhausted → 409. |

### `test_use_lay_on_hands.py`
Paladin Lay on Hands: heal from a per-day pool.

| Test | What it asserts |
|------|-----------------|
| `test_loh_happy_path` | Heals targeted PC; decrements pool; broadcast carries v2.43.0 `heal_amount` + `heal_target_name` (== target). |
| `test_loh_missing_fields` | 400. |
| `test_loh_zero_amount` | Amount ≤ 0 → 400. |
| `test_loh_no_paladin_resource` | Non-Paladin caller → 409. |
| `test_loh_unknown_target` | Unknown target id → 404. |

### `test_use_feature.py`
Generic `/use_feature` endpoint — Rogue Cunning Action, Channel Divinity options, Paladin Divine Sense, plus several curated single-shot features.

| Test | What it asserts |
|------|-----------------|
| `test_cunning_action_dash` | Pip's Dash flips the bonus chip. |
| `test_cunning_action_disengage` | Same flow for Disengage. |
| `test_cunning_action_hide` | Same flow for Hide. |
| `test_channel_divinity_turn_undead` | Tavik's Turn Undead consumes CD charge. |
| `test_channel_divinity_sacred_weapon` | Sacred Weapon variant works. |
| `test_channel_divinity_turn_the_unholy` | Turn the Unholy CD variant. |
| `test_channel_divinity_preserve_life` | Preserve Life CD variant. |
| `test_divine_sense_announces` | Paladin announces aura sense; no resource cost. |
| `test_cleansing_touch_curated` | Curated feature label fires. |
| `test_indomitable_curated` | Fighter Indomitable variant. |
| `test_stroke_of_luck_curated` | Rogue Stroke of Luck. |
| `test_font_of_magic_curated` | Sorcerer Font of Magic announce. |
| `test_action_surge_is_free` | Action Surge via the generic endpoint is action-economy-free (refunds the action chip). |
| `test_unknown_feature_key` | Unknown key → 404. |
| `test_missing_required_fields` | 400. |
| `test_feature_desc_falls_back_when_client_omits` | v2.43.11: when the client doesn't send `desc`, the server falls back to the curated `_FEATURE_ECONOMY` desc and the option-specific entry (disengage) wins over the parent feature's. |
| `test_feature_desc_client_override_wins` | Client-supplied `desc` overrides the server table. |

---

## Items

### `test_use_item.py`
`/use_item` consumable + non-consumable paths (heal potions, story items).

| Test | What it asserts |
|------|-----------------|
| `test_use_item_missing_fields` | Empty body → 400. |
| `test_use_item_unknown_index` | Out-of-range item index → 404. |
| `test_use_item_non_consumable` | Story item (qty 1, non-consumable) → fires feature_used but doesn't decrement. |

> Heal-potion happy path is covered indirectly via `heal_applied` broadcasts in `test_cast_spell_heal.py` and the v2.27.1 routing logic. A dedicated potion-heal test is **filed**.

### `test_item_schema.py`
v2.158.73 magic-items-automation Phase 0 — the SRD item content layer now ships three new top-level keys (`charges` / `charge_recovery` / `passives`) on every item under `app/data/local/dnd5e/items/`. The `Item` Pydantic model in `app/content_schemas.py` declares the new fields; the public `/api/content/items/{slug}` read endpoint surfaces them. Phase 1 will populate the values for the first-slice roster (Cloak / Bracers / Ring / Pearl); this commit's tests just assert the shape is present and uniform.

| Test | What it asserts |
|------|-----------------|
| `test_item_schema_cloak_of_protection_has_phase1a_passives` | v2.158.75 update of the original Phase 0 assertion: Phase 1a (v2.158.74) populated the Cloak's `passives` with `[{ac_bonus:1, save_bonus:1, requires_attunement:true}]`. Test now asserts the wired shape. Charges still null. |
| `test_item_schema_ring_of_protection_has_phase1b_passives` | v2.158.76: Phase 1b populated Ring with the same +1/+1 payload as Cloak. Test asserts the wired shape. |
| `test_item_schema_bracers_of_defense_has_phase1c_passives` | v2.158.77: Phase 1c populated Bracers with `[{ac_bonus:2, requires_attunement:true, requires_no_armor:true, requires_no_shield:true}]`. Different shape from Cloak/Ring (no save_bonus key, +2 AC, two new gate flags). Plan's Phase 1 fully shipped after this entry. |
| `test_item_schema_pearl_of_power_has_phase3_action` | v2.158.82: Phase 3 wired Pearl with `charges: 1`, `charge_recovery: "long-rest"`, and one `actions[]` entry (`restore-slot`). Passives stays `[]` (Pearl is active-only). Canary moves on to Wand of Magic Missiles (Phase 4 target). |
| `test_item_schema_wand_of_magic_missiles_has_phase4_action` | v2.158.84: Phase 4a populated Wand with `charges: 7`, `charge_recovery: "1d6+1"`, and one `actions[]` entry (`cast-magic-missile`). |
| `test_item_schema_unknown_slug_404` | `GET /api/content/items/no-such-srd-item` → 404 — error contract unchanged by the Phase 0 additions. |

### `test_item_cloak_of_protection.py`
v2.158.74 magic-items-automation Phase 1a — Cloak of Protection (+1 AC, +1 saves) wired into both read sites. The new `_MAGIC_ITEM_PASSIVES` catalog in `app/routes/tabletop_routes.py` + the `_equipped_item_effects` walker are the new primitives; `_read_target_ac` adds the walker's `ac_bonus` (alongside buffs + Defense style), and the `/roll` endpoint appends the walker's `save_bonus` to `*_save` expressions and annotates the breakdown with the source item name. Thalindra carries a permanent equipped+attuned Cloak in the demo seed so the test surface needs no setup PATCH.

| Test | What it asserts |
|------|-----------------|
| `test_cloak_of_protection_grants_ac_bonus` | Krieger swings at Thalindra → response `target_ac == 13` (base 12 + Cloak +1). Asserts on `target_ac` rather than the hit verdict to avoid dice flakiness. |
| `test_cloak_of_protection_grants_save_bonus` | `POST /roll` with `stat_key="int_save"` for Thalindra (`1d20+6`) → breakdown contains "Cloak of Protection" + "+1" attribution; expression was rewritten to `1d20+6+1` server-side. |
| `test_cloak_of_protection_save_skipped_for_non_save_rolls` | Save hook guard: `stat_key="int_check"` MUST NOT pick up the Cloak's +1 (saves and checks are RAW-distinct). Breakdown does not contain "Cloak of Protection". |

### `test_item_stone_of_good_luck.py`
v2.209.0 magic-items — Stone of Good Luck (Luckstone, RAW DMG p.207, uncommon, attunement): +1 to ability checks AND saving throws. The save half rides the existing v2.158.74 `save_bonus` substrate; the check half is new — `_equipped_item_effects` grows a `check_bonus` field and the `/roll` endpoint appends it for ability checks (`*_check`) and ability-based skill checks (rolls carrying `stat_ability`), the surface the Cloak/Ring deliberately skip. Garrik Ironside (Fighter 9) carries a permanent equipped+attuned Stone in the demo seed (his STR/CON saves + Athletics make both halves clean).

| Test | What it asserts |
|------|-----------------|
| `test_stone_of_good_luck_grants_save_bonus` | `POST /roll` `str_save` for Garrik (`1d20+8`) → breakdown contains "Stone of Good Luck" + "+1" (existing save substrate). |
| `test_stone_of_good_luck_grants_ability_check_bonus` | `POST /roll` `str_check` for Garrik (`1d20+4`) → breakdown contains "Stone of Good Luck" + "+1" (the NEW check read site — the surface the Cloak guard test asserts stays empty). |
| `test_stone_of_good_luck_grants_skill_check_bonus` | `POST /roll` `Athletics` with `stat_ability="STR"` for Garrik → breakdown contains "Stone of Good Luck" (ability-based skill checks also pick up the check bonus). |

### `test_item_belt_of_giant_strength.py`
v2.212.0 ability-score override engine Phase 1 (docs/plans/str-override.md) — Belt of Giant Strength (RAW DMG p.155, attunement). While worn, STR *becomes* the belt's score if higher (RAW `max(base, set)`). The override flows to three read sites: `/sheet-json` `derived.effective_abilities.STR`, the carry-capacity derivation (effective STR × 15), and `/roll` STR saves + STR-based checks (modifier delta). Garrik Ironside (base STR 18 → mod +4) carries an equipped+attuned Belt of Giant Strength (Hill, STR 21 → mod +5) in the demo seed — his 3rd attuned item. v2.213.0 (Phase 1b) adds the weapon attack/damage read site: `/attack` appends the effective-STR modifier delta to both the to-hit roll and the damage expression for STR-keyed weapons (DEX bows/finesse untouched). v2.215.0 (Phase 2b) adds the per-inventory-item tier override: the SRD's single `belt-of-giant-strength` slug defaults to the Hill tier (STR 21), and an `_ability_set: {"STR": N}` field on the inventory item overrides it — Zara Emberfire (Sorcerer, base STR 8) wears a Belt of Stone Giant Strength (`_ability_set: {"STR": 23}`) → effective STR 23. v2.223.0 (Phase 2c) seeds the legendary top tier: Brakka Wildmane (Barbarian, base STR 17) wears a Belt of Storm Giant Strength (`_ability_set: {"STR": 29}`) → effective STR 29, completing the demonstrable tier span Hill 21 → Stone 23 → Storm 29.

| Test | What it asserts |
|------|-----------------|
| `test_belt_exposes_effective_str_on_sheet_json` | `GET /sheet-json` → `derived.effective_abilities.STR` = `{base 18, effective 21, modifier 5}`. |
| `test_belt_raises_carry_capacity` | `GET /sheet-json` → `derived.carry.carry_capacity_lb` == 315 (effective STR 21 × 15, vs. base 270). |
| `test_belt_adds_str_save_override_delta` | `POST /roll` `str_save` for Garrik → breakdown contains "Belt of Giant Strength" (the +1 modifier delta annotation, composing with the Stone of Good Luck's +1). |
| `test_belt_adds_athletics_override_delta` | `POST /roll` `Athletics` with `stat_ability="STR"` → breakdown contains "Belt of Giant Strength" (override delta fires for ability-based skill checks too). |
| `test_belt_unequip_reverts_override` | PATCH the belt to `equipped: False` → `effective_abilities` drops STR + carry capacity returns to 270; restores the original inventory on teardown. |
| `test_belt_boosts_weapon_attack_and_damage` | `POST /attack` Greatsword (index 0) → `damage_expr == "2d6+4+1"` + to-hit flat bonus == 9 (base +8 + belt +1). Phase 1b. |
| `test_belt_weapon_boost_reverts_on_unequip` | PATCH belt `equipped: False` → `/attack` Greatsword `damage_expr == "2d6+4"` + to-hit flat == 8; restores inventory on teardown. Phase 1b. |
| `test_belt_tier_override_sets_higher_str` | Zara Emberfire's `GET /sheet-json` → `derived.effective_abilities.STR` = `{base 8, effective 23, modifier 6}` — the per-item `_ability_set` (23) beats the catalog Hill default (21). Phase 2b. |
| `test_belt_tier_override_raises_carry_capacity` | Zara's `derived.carry.carry_capacity_lb` == 345 (effective STR 23 × 15, vs. base 120). Phase 2b. |
| `test_belt_storm_tier_sets_str_29` | Brakka Wildmane (Barbarian, base STR 17) wears a Belt of **Storm** Giant Strength (`_ability_set: {"STR": 29}`) → `effective_abilities.STR` = `{base 17, effective 29, modifier 9}` — the legendary top tier beats the catalog default. Phase 2c (v2.223.0). |
| `test_belt_storm_tier_raises_carry_capacity` | Brakka's `derived.carry.carry_capacity_lb` == 435 (effective STR 29 × 15, vs. base 255). Phase 2c (v2.223.0). |
| `test_belt_fire_tier_sets_str_25` | v2.278.0 — PATCH Garrik's spare Belt of **Fire** Giant Strength (`_ability_set: {"STR": 25}`) equipped+attuned (Hill belt off) → `effective_abilities.STR` = `{base 18, effective 25, modifier 7}` + carry capacity 375; restores inventory on teardown. |
| `test_belt_cloud_tier_sets_str_27` | v2.278.0 — PATCH Garrik's spare Belt of **Cloud** Giant Strength (`_ability_set: {"STR": 27}`) equipped+attuned → `effective_abilities.STR` = `{base 18, effective 27, modifier 8}` + carry capacity 405; completes the RAW DMG p.155 tier table (21/23/25/27/29); restores inventory on teardown. |

### `test_item_amulet_of_health.py`
v2.216.0 ability-score override engine Phase 3 (docs/plans/str-override.md) — Amulet of Health (RAW DMG p.150, attunement). While worn, CON *becomes* 19 if higher (same `ability_set` substrate as the belt, on CON), and the CON change retroactively adjusts max HP. The max-HP effect is display-derived: `/sheet-json` `derived.effective_max_hp` adds the CON-modifier delta × character level to the stored max (the stored `hp.max` is left untouched in v1). Brother Tavik Stonebrow (Cleric Lv 8, base CON 14 → mod +2, stored max 67) carries an equipped+attuned Amulet of Health — his 3rd attuned item.

| Test | What it asserts |
|------|-----------------|
| `test_amulet_exposes_effective_con_on_sheet_json` | `GET /sheet-json` → `derived.effective_abilities.CON` = `{base 14, effective 19, modifier 4}`. |
| `test_amulet_raises_effective_max_hp` | `derived.effective_max_hp` = `{level 8, delta 16, base == stored hp.max, effective == stored + 16}` (CON mod delta +2 × level 8). |
| `test_amulet_adds_con_save_override_delta` | `POST /roll` `con_save` for Tavik → breakdown contains "Amulet of Health" (the +2 modifier delta annotation). |
| `test_amulet_unequip_reverts_override` | PATCH the amulet to `equipped: False` → `effective_abilities` drops CON + `effective_max_hp` is None; restores the original inventory on teardown. |

### `test_item_headband_of_intellect.py`
v2.218.0 ability-score override engine drop-in (docs/plans/str-override.md) — Headband of Intellect (RAW DMG p.173, uncommon, attunement). While worn, INT *becomes* 19 if higher — same `ability_set` substrate as the Belt (STR) and Amulet (CON), on INT. A pure data drop-in (one `_MAGIC_ITEM_PASSIVES` row + seed + tests), proving the engine takes score-setting items as data, not code. Mira Greenleaf (Druid, base INT 10 → mod 0) wears an equipped+attuned Headband — her 2nd attuned item (after the Vorpal Scimitar).

| Test | What it asserts |
|------|-----------------|
| `test_headband_exposes_effective_int_on_sheet_json` | `GET /sheet-json` → `derived.effective_abilities.INT` = `{base 10, effective 19, modifier 4}` with source naming "Headband of Intellect". |
| `test_headband_adds_int_save_override_delta` | `POST /roll` `int_save` for Mira → breakdown contains "+4" and "Headband of Intellect" (the modifier delta annotation). |
| `test_headband_unequip_reverts_override` | PATCH the headband to `equipped: False` → `effective_abilities` drops INT; restores the original inventory on teardown. |

### `test_amulet_health_combat_max_hp.py`
v2.220.0 ability-score override engine, Phase 3 combat follow-up (docs/plans/str-override.md) — the Amulet of Health's boosted max HP now drives the combat heal-clamp, not just the v2.216.0 `/sheet-json` display. `_apply_heal_to_combatant` folds the `_effective_max_hp_for_sheet` CON-override delta into its effective-max ceiling (non-destructive — stored `hp.max` is never mutated). Tavik Stonebrow (Cleric Lv 8, stored max 67, effective 83) self-casts Healing Word from his stored max.

| Test | What it asserts |
|------|-----------------|
| `test_heal_at_stored_max_uses_amulet_ceiling` | Tavik at stored max → self Healing Word → `auto_heal_applied > 0` and `stored_max < hp_after <= effective` (83). The combat clamp reads the boosted pool. |
| `test_heal_at_stored_max_caps_without_amulet` | Guard: amulet unequipped → same heal at stored max → `auto_heal_applied == 0` (clamp falls back to `hp.max`). Restores inventory + full HP on teardown. |

### `test_item_manual_of_ability.py`
v2.222.0 Manuals & Tomes — permanent ability-score boost books (RAW DMG pp.176/208). The `permanent_boost` archetype on `/use_item_action`: reading the book edits `sheet.abilities[X] += 2` and consumes it (no 20-cap clamp — RAW the maximum rises too). Distinct from the timed self-buff potions and equipped-item runtime overrides; the boosted base composes via the existing `effective_ability_score` chain. As of v2.314.0 (reconciliation Phase 3) this is the **single** mechanism for all six books — the parallel `/use_item` `ability_increase` branch was retired and the three Manuals re-seated here. Carriers: Lyra (Tome of Leadership/CHA), Thalindra (Tome of Clear Thought/INT), Tavik (Tome of Understanding/WIS), Garrik (all three Manuals — STR/CON/DEX).

| Test | What it asserts |
|------|-----------------|
| `test_reading_tome_permanently_raises_cha` | Lyra reads the tome → response `ability=CHA, amount=2, new_score=old+2, consumed`; `/sheet-json` shows stored `abilities.CHA` is `old+2` and CHA is absent from derived `effective_abilities` (a permanent base edit is not a runtime override); the book is gone from inventory. Restores abilities + inventory on teardown. |
| `test_reading_bodily_health_raises_con_and_max_hp` | v2.312.0 reconciliation Phase 1 — Garrik reads the Manual of Bodily Health via `/use_item_action`; response `ability=CON, new_score=old+2, hp_gain=mod_delta×level`; `/sheet-json` shows stored `abilities.CON` is `old+2` AND `hp.max` is `old+hp_gain` (RAW PHB p.173 CON max-HP recompute). Restores abilities + inventory + hp on teardown. |
| `test_reading_gainful_exercise_permanently_raises_str` | v2.314.0 reconciliation Phase 3 — Garrik reads the Manual of Gainful Exercise via `/use_item_action` `read` → `ability=STR, amount=2, new_score=old+2, consumed`; stored `abilities.STR` is `old+2`, book consumed. (Garrik's equipped Belt of Giant Strength overrides effective STR, so the test asserts only the stored write + consume.) Restores on teardown. |
| `test_reading_quickness_permanently_raises_dex` | v2.314.0 reconciliation Phase 3 — Garrik reads the Manual of Quickness of Action via `/use_item_action` `read` → `ability=DEX, amount=2, new_score=old+2, consumed`; stored `abilities.DEX` is `old+2`, DEX absent from derived `effective_abilities`, book consumed. Restores on teardown. |
| `test_reading_clear_thought_permanently_raises_int` | v2.313.0 reconciliation Phase 2 — Thalindra (Wizard) reads the Tome of Clear Thought via `/use_item_action` → `ability=INT, amount=2, new_score=old+2, consumed`; stored `abilities.INT` is `old+2`, INT absent from derived `effective_abilities`, book consumed. Restores on teardown. |
| `test_reading_understanding_permanently_raises_wis` | v2.313.0 reconciliation Phase 2 — Tavik (Cleric) reads the Tome of Understanding via `/use_item_action` → `ability=WIS, amount=2, new_score=old+2, consumed`; stored `abilities.WIS` is `old+2`, WIS absent from derived `effective_abilities`, book consumed. Restores on teardown. |
| `test_wrong_action_key_on_tome_404s` | Guard: a mismatched `action_key` (`drink` vs the tome's `read`) returns 404 without mutating the sheet. |

### `test_amulet_health_rest_heal_paths.py`
v2.221.0 ability-score override engine, Phase 3 remaining heal paths (docs/plans/str-override.md) — the Amulet of Health's boosted max HP now drives the remaining non-combat heal clamps via the shared `_sheet_heal_ceiling(sheet)` helper: short-rest hit dice, Second Wind, and Lay on Hands. Non-destructive (stored `hp.max` never mutated). Tavik Stonebrow (Cleric Lv 8, stored max 67, effective 83). Second Wind isn't directly exercised (no amulet-wearing Fighter in the demo) but reads the same helper.

| Test | What it asserts |
|------|-----------------|
| `test_short_rest_heals_past_stored_max_via_amulet` | Tavik long-rests (refill HD), drops to stored max 67, short rests → response `hp.current` lands `stored_max < hp_after <= effective` (83). The short-rest clamp reads the boosted pool. |
| `test_lay_on_hands_tops_amulet_wearer_past_stored_max` | Sir Caelan lays hands on Tavik at stored max → `amount_healed > 0` and `stored_max < new_hp.current <= effective`. The Lay on Hands clamp honors the boosted ceiling. |

### `test_item_gauntlets_of_ogre_power.py`
v2.219.0 ability-score override engine drop-in (docs/plans/str-override.md) — Gauntlets of Ogre Power (RAW DMG p.171, uncommon, attunement). While worn, STR *becomes* 19 if not already higher — same `ability_set` substrate as the Belt (STR), Amulet (CON), and Headband (INT). A pure data drop-in (one `_MAGIC_ITEM_PASSIVES` row + seed + tests), composing with the Belt via the highest-wins map. Rowan Quickbow (Ranger, base STR 12 → mod +1) wears equipped+attuned Gauntlets — his 1st attuned item.

| Test | What it asserts |
|------|-----------------|
| `test_gauntlets_expose_effective_str_on_sheet_json` | `GET /sheet-json` → `derived.effective_abilities.STR` = `{base 12, effective 19, modifier 4}` with source naming "Gauntlets of Ogre Power". |
| `test_gauntlets_raise_carry_capacity` | `GET /sheet-json` → `derived.carry.carry_capacity_lb` = 285 (19 × 15), up from base 180. |
| `test_gauntlets_add_str_save_override_delta` | `POST /roll` `str_save` for Rowan → breakdown contains "+3" and "Gauntlets of Ogre Power" (the modifier delta annotation). |
| `test_gauntlets_unequip_reverts_override` | PATCH the gauntlets to `equipped: False` → `effective_abilities` drops STR; restores the original inventory on teardown. |

### `test_item_ioun_stone.py`
v2.224.0 capped-additive ability-bonus engine drop-in (docs/plans/str-override.md) — Ioun Stone of Intellect (RAW DMG p.176, very rare, attunement). The first item on the new `ability_bonus` / `ability_bonus_cap` substrate: it *increases* INT by 2 "to a maximum of 20" (additive, not a set), composing AFTER any `ability_set` and clamping at the cap. The six SRD ability variants share the single `ioun-stone` slug; the variant rides the inventory item via `_ability_bonus: {"INT": 2}`. Magnus Hexbinder (Warlock, base INT 10 → effective 12, mod 0 → +1) wears equipped+attuned — his 3rd attuned item, a pure-additive read with no set to confound it.

| Test | What it asserts |
|------|-----------------|
| `test_ioun_stone_exposes_effective_int_on_sheet_json` | `GET /sheet-json` → `derived.effective_abilities.INT` = `{base 10, effective 12, modifier 1}` with source naming "Ioun Stone" — a pure additive +2 under the cap. |
| `test_ioun_stone_adds_int_save_override_delta` | `POST /roll` `int_save` for Magnus → breakdown contains "+1" and "Ioun Stone" (the modifier delta annotation, proving bonus-only source attribution works). |
| `test_ioun_stone_caps_at_20` | PATCH INT to 19 → `effective_abilities.INT.effective` == 20 (the +2 clamps to +1 at the cap, not 21); restores the original abilities on teardown. |
| `test_ioun_stone_unequip_reverts_bonus` | PATCH the stone to `equipped: False` → `effective_abilities` drops INT; restores the original inventory on teardown. |
| `test_ioun_variant_exposes_effective_ability` — REMOVED v2.249.0 | The parametrized ability-variant test was removed when its last row (Krieger WIS) was detuned to free a 3rd attunement slot for the Brooch of Shielding. Earlier rows were dropped one at a time: STR (Lyra, v2.245.0), CON (Brakka, v2.246.0), CHA (Rowan, v2.247.0), DEX (Caelan, v2.248.0), each when the stone was detuned for a ring/boots/armor. With the variant list empty, the test was deleted. The Magnus INT primary deep-dive above + the dedicated set-based ability item tests (Headband of Intellect, Gauntlets of Ogre Power, three Belts of Giant Strength, Amulet of Health) still prove the single `ioun-stone` slug + per-item `_ability_bonus` substrate. |

### `test_item_belt_of_dwarvenkind.py`
v2.226.0 — Belt of Dwarvenkind (RAW DMG p.155, rare, attunement): the first magic item whose single passive payload composes TWO existing override substrates at once — a capped-additive CON +2 (max 20, the v2.224.0 `ability_bonus` engine) AND darkvision 60 ft (the v2.159.24 `sees_in_darkness` engine). Neither needed new engine code. Quan Reelstep (Way of the Drunken Master Monk, Human, base CON 14 → effective 16, mod +2 → +3) wears it equipped+attuned (his 1st attuned item); as a non-dwarf he qualifies for the darkvision gate.

| Test | What it asserts |
|------|-----------------|
| `test_belt_exposes_effective_con_on_sheet_json` | `GET /sheet-json` → `derived.effective_abilities.CON` = `{base 14, effective 16, modifier 3}` with source naming "Belt of Dwarvenkind" — a pure additive +2 under the cap. |
| `test_belt_darkvision_negates_darkness_blinded_disadvantage` | Quan darkness-blinded + belt equipped → `/attack` breakdown has no `2d20kl1` and `roll_state_applied` is not `disadvantage_attacker_blinded` (mirror of the Goggles path, proving the second substrate field rides the same payload). |
| `test_belt_unequip_reverts_con_bonus` | PATCH the belt to `equipped: False` → `effective_abilities` drops CON; restores the original inventory on teardown. |

### `test_item_periapt_of_wound_closure.py`
v2.227.0 — Periapt of Wound Closure (RAW DMG p.184, uncommon, attunement): the first magic item on the rest-heal substrate. RAW "double the number of hit points a Hit Die restores" — an equipped+attuned periapt doubles the rolled short-rest recovery via the new `double_hit_die_healing` field on `_equipped_item_effects`, read by `/rest`. The response gains `hit_die_healing_doubled` (bool) + `recovered_pre_double` (int|null). Dame Seraphine Vael (Oath of Vengeance Paladin, d10 HD) wears it equipped+attuned (her 2nd attuned item). The periapt's auto-stabilize-when-dying clause is descriptive-only in v1.

| Test | What it asserts |
|------|-----------------|
| `test_periapt_doubles_short_rest_hit_die_healing` | Seraphine `/rest` short → `hit_die_healing_doubled is True`, `recovered_pre_double` ≥ 1, `recovered == 2 × recovered_pre_double`, and the breakdown names "Periapt of Wound Closure". |
| `test_short_rest_without_periapt_not_doubled` | Control: Pip (no periapt) `/rest` short → `hit_die_healing_doubled is False`, `recovered_pre_double` is null. |
| `test_periapt_unequip_stops_doubling` | Unequip the periapt → `/rest` short no longer doubles (flag False, pre null); restores the original inventory on teardown. |

### `test_item_ioun_stone_protection.py`
v2.228.0 — Ioun Stone of Protection (RAW DMG p.176, rare, attunement): the first non-ability Ioun variant and the first item to ride a per-inventory-item AC override. It grants +1 AC with no ability payload; rather than mint a fake per-variant slug, the AC bonus rides the inventory item via `_ac_bonus: 1` on the shared `ioun-stone` slug and wins over the catalog default in `_equipped_item_effects` (same per-item shape as `_ability_set` / `_ability_bonus`). Mira Greenleaf (Druid, base AC 15 = studded leather 12 + DEX +3) wears it equipped+attuned (her 3rd attuned item) → combat AC 16.

| Test | What it asserts |
|------|-----------------|
| `test_ioun_stone_protection_grants_ac_bonus` | Krieger swings at Mira → `target_ac == 16` (15 base + stone +1). |
| `test_ioun_stone_protection_unequip_reverts_ac` | PATCH the stone to `equipped: False` → `target_ac == 15` (base, no bonus); restores the original inventory on teardown. |

### `test_item_ring_of_feather_falling.py`
v2.244.0 — Ring of Feather Falling (RAW DMG p.191, rare, attunement): when you fall while wearing it, you descend 60 feet per round and take no falling damage. Reuses the boolean-OR passive substrate: the `feather_fall` flag rides the `ring-of-feather-falling` catalog payload (`requires_attunement: True`), aggregates in `_equipped_item_effects`, and surfaces on `/sheet-json` as `derived.feather_fall = {sources}`. Unlike the swim/water-walk rings this one is attunement-gated. Sir Caelan Lightbringer (Paladin) wears it — fills the slot the v2.243.0 Dragon Slayer correction freed (back to 3/3).

| Test | What it asserts |
|------|-----------------|
| `test_ring_of_feather_falling_exposes_flag` | `GET /sheet-json` → `derived.feather_fall` present with "Ring of Feather Falling" in `sources`. |
| `test_ring_of_feather_falling_requires_attunement` | Detuning the ring via `POST /attune` (`attuned: False`) → `derived.feather_fall` absent (attunement-gated, unlike the swim/water-walk rings); restores seed attunement on teardown. |
| `test_ring_of_feather_falling_unequip_drops_flag` | PATCH the ring to `equipped: False` → `derived.feather_fall` absent; restores the original inventory on teardown. |

### `test_item_boots_of_the_winterlands.py`
v2.247.0 — Boots of the Winterlands (RAW DMG p.156, uncommon, attunement): resistance to cold damage + tolerance of cold environments down to −50°F + immunity to ice/snow difficult terrain (narrative in v1). Pure substrate-reuse drop-in: the only engine change is a new `boots-of-the-winterlands` catalog entry carrying the exact v2.246.0 Ring of Warmth payload (`resistance_to: ["cold"]` folding into the live `_resistance_halve` pipeline + the `cold_tolerance` boolean flag → `derived.cold_tolerance`). Both attunement-gated. Rowan Quickbow (Ranger) wears them — homed by detuning his redundant Ioun Stone of Charisma (kept equipped) to stay at the RAW 3/3 cap.

| Test | What it asserts |
|------|-----------------|
| `test_boots_expose_cold_resistance` | `GET /sheet-json` → `derived.resistances.types` contains "cold" and `derived.cold_tolerance` present, both naming "Boots of the Winterlands" in sources. |
| `test_boots_halve_cold_damage` | End-to-end: 20 cold damage via `PATCH .../sheet-fields` drops HP by only 10 (`_resistance_halve` halves it); restores HP on teardown. |
| `test_boots_do_not_halve_other_types` | Control: 20 FIRE damage applies in full (−20), proving the resistance is type-specific; restores HP on teardown. |
| `test_boots_require_attunement` | Detuning via `POST /attune` (`attuned: False`) → cold drops from `derived.resistances` and `derived.cold_tolerance` absent (both attunement-gated); restores seed attunement on teardown. |
| `test_boots_unequip_drops_flags` | PATCH the boots to `equipped: False` → both derived surfaces absent; restores the original inventory on teardown. |

### `test_item_armor_of_resistance.py`
v2.248.0 — Armor of Resistance (RAW DMG p.152, rare, attunement): "you have resistance to one type of damage while you wear this armor." A pure reuse of the v2.235.0 Ring of Resistance substrate — the resisted type rides the per-item `_resistance_type` rider (here "acid") on a new `armor-of-resistance` slug; the walker folds it into the aggregated `resistance_to` list that `_resistance_halve` consults in the live damage pipeline. Surfaces on `/sheet-json` as `derived.resistances`. Sir Caelan Lightbringer (Paladin) wears Armor of Resistance (Acid) as his 3rd attuned item, homed by detuning his redundant Ioun Stone of Dexterity (heavy armor meant the DEX bump never touched AC).

| Test | What it asserts |
|------|-----------------|
| `test_armor_exposes_acid_resistance` | `GET /sheet-json` → `derived.resistances.types` contains "acid", naming "Armor of Resistance" in sources. |
| `test_armor_halves_acid_damage` | End-to-end: 20 acid damage via `PATCH .../sheet-fields` drops HP by only 10 (`_resistance_halve` halves it); restores HP on teardown. |
| `test_armor_does_not_halve_other_types` | Control: 20 FIRE damage applies in full (−20), proving the resistance is type-specific; restores HP on teardown. |
| `test_armor_requires_attunement` | Detuning via `POST /attune` (`attuned: False`) → acid drops from `derived.resistances` (attunement-gated); restores seed attunement on teardown. |
| `test_armor_unequip_drops_resistance` | PATCH the armor to `equipped: False` → acid resistance absent; restores the original inventory on teardown. |

### `test_item_brooch_of_shielding.py`
v2.249.0 — Brooch of Shielding (RAW DMG p.156, uncommon, attunement): "resistance to force damage and immunity to the magic missile spell." Two surfaces compose on one item. The force *resistance* reuses the v2.235.0 Ring of Resistance substrate — the resisted type rides the per-item `_resistance_type` rider ("force") on a new `brooch-of-shielding` slug, folding into the aggregated `resistance_to` list `_resistance_halve` consults in the live damage pipeline; surfaces on `/sheet-json` as `derived.resistances`. The magic-missile *immunity* is the only new engine work: a new boolean-OR `magic_missile_immune` flag (catalog payload + walker accumulator + derived block) surfaced as `derived.magic_missile_immune = {sources}` (advisory in v1). Both attunement-gated. Krieger Stonefist (Barbarian) wears it as his 3rd attuned item, homed by detuning his Ioun Stone of Wisdom (last in the ability-ioun sacrifice series; WIS was a secondary-stat read).

| Test | What it asserts |
|------|-----------------|
| `test_brooch_exposes_force_resistance` | `GET /sheet-json` → `derived.resistances.types` contains "force", naming "Brooch of Shielding" in sources. |
| `test_brooch_exposes_magic_missile_immunity` | `GET /sheet-json` → `derived.magic_missile_immune` present with "Brooch of Shielding" in sources (the new boolean substrate). |
| `test_brooch_halves_force_damage` | End-to-end: 20 force damage via `PATCH .../sheet-fields` drops HP by only 10 (`_resistance_halve` halves it); restores HP on teardown. |
| `test_brooch_does_not_halve_other_types` | Control: 20 FIRE damage applies in full (−20), proving the resistance is type-specific; restores HP on teardown. |
| `test_brooch_requires_attunement` | Detuning via `POST /attune` (`attuned: False`) → force drops from `derived.resistances` and `derived.magic_missile_immune` absent (both attunement-gated); restores seed attunement on teardown. |
| `test_brooch_unequip_drops_both_surfaces` | PATCH the brooch to `equipped: False` → both derived surfaces absent; restores the original inventory on teardown. |

### `test_item_ring_of_warmth.py`
v2.246.0 — Ring of Warmth (RAW DMG p.193, uncommon, attunement): resistance to cold damage + tolerance of cold environments down to −50°F. Composes two substrates: the cold *resistance* rides the catalog payload's `resistance_to: ["cold"]`, folding into the aggregated `resistance_to` list that `_resistance_halve` consults in the live damage pipeline (so cold damage is halved end-to-end, like the Ring of Resistance), and surfaces on `/sheet-json` as `derived.resistances`; the −50°F tolerance is a new boolean-OR `cold_tolerance` flag surfaced as `derived.cold_tolerance = {sources}`. Both attunement-gated. Brakka Wildmane (Beast Barbarian) wears it — homed by detuning her redundant Ioun Stone of Constitution (kept equipped) to stay at the RAW 3/3 cap.

| Test | What it asserts |
|------|-----------------|
| `test_ring_of_warmth_exposes_cold_resistance` | `GET /sheet-json` → `derived.resistances.types` contains "cold" and `derived.cold_tolerance` present, both naming "Ring of Warmth" in sources. |
| `test_ring_of_warmth_halves_cold_damage` | End-to-end: 20 cold damage via `PATCH .../sheet-fields` drops HP by only 10 (`_resistance_halve` halves it); restores HP on teardown. |
| `test_ring_of_warmth_does_not_halve_other_types` | Control: 20 FIRE damage applies in full (−20), proving the resistance is type-specific; restores HP on teardown. |
| `test_ring_of_warmth_requires_attunement` | Detuning the ring via `POST /attune` (`attuned: False`) → cold drops from `derived.resistances` and `derived.cold_tolerance` absent (both attunement-gated); restores seed attunement on teardown. |
| `test_ring_of_warmth_unequip_drops_flags` | PATCH the ring to `equipped: False` → both derived surfaces absent; restores the original inventory on teardown. |

### `test_item_ring_of_mind_shielding.py`
v2.245.0 — Ring of Mind Shielding (RAW DMG p.192, uncommon, attunement): while worn you are immune to magic that reads your thoughts, detects lies, or knows your alignment / creature type. Reuses the boolean-OR passive substrate: the `mind_shield` flag rides the `ring-of-mind-shielding` catalog payload (`requires_attunement: True`), aggregates in `_equipped_item_effects`, and surfaces on `/sheet-json` as `derived.mind_shield = {sources}`. Attunement-gated like the Ring of Feather Falling. Lyra Sunstrider (Bard) wears it — homed by detuning her redundant Ioun Stone of Strength (kept equipped) to stay at the RAW 3/3 cap.

| Test | What it asserts |
|------|-----------------|
| `test_ring_of_mind_shielding_exposes_flag` | `GET /sheet-json` → `derived.mind_shield` present with "Ring of Mind Shielding" in `sources`. |
| `test_ring_of_mind_shielding_requires_attunement` | Detuning the ring via `POST /attune` (`attuned: False`) → `derived.mind_shield` absent (attunement-gated); restores seed attunement on teardown. |
| `test_ring_of_mind_shielding_unequip_drops_flag` | PATCH the ring to `equipped: False` → `derived.mind_shield` absent; restores the original inventory on teardown. |

### `test_item_ring_of_swimming.py`
v2.242.0 — Ring of Swimming (RAW DMG p.193, uncommon, no attunement): grants a swimming speed of 40 feet while worn. Reuses the boolean-OR passive substrate: the `swim_speed` flag rides the `ring-of-swimming` catalog payload, aggregates in `_equipped_item_effects`, and surfaces on `/sheet-json` as `derived.swim_speed = {sources}`. Mira Greenleaf (Druid) wears it — no attunement, riding alongside her full 3/3 attunement loadout.

| Test | What it asserts |
|------|-----------------|
| `test_ring_of_swimming_exposes_flag` | `GET /sheet-json` → `derived.swim_speed` present with "Ring of Swimming" in `sources`. |
| `test_ring_of_swimming_no_attunement_required` | The no-attunement flag rides alongside the Headband of Intellect — `derived.effective_abilities.INT.effective == 19` still reports alongside `swim_speed`. |
| `test_ring_of_swimming_unequip_drops_flag` | PATCH the ring to `equipped: False` → `derived.swim_speed` absent; restores the original inventory on teardown. |

### `test_item_mariners_armor.py`
v2.250.0 — Mariner's Armor (RAW DMG p.181, uncommon, no attunement): swimming speed equal to walking speed (+ rise-to-surface-at-0-HP, GM-narrated in v1). A pure reuse of the v2.242.0 `swim_speed` boolean-OR passive — the only engine change is a new `mariners-armor` catalog entry carrying `{"swim_speed": True}`, surfacing on `/sheet-json` as `derived.swim_speed`. Garrik Ironside (Fighter) wears a heavy (chain-mail-base, AC 16) Mariner's variant in place of his mundane chain mail — same AC/weight, no attunement, no slot cost.

| Test | What it asserts |
|------|-----------------|
| `test_mariners_armor_exposes_swim_speed` | `GET /sheet-json` → `derived.swim_speed` present with "Mariner's Armor" in `sources`. |
| `test_mariners_armor_no_attunement_required` | The flag surfaces though the item carries no `attuned` flag and Garrik's 3 slots are filled — proving the no-attunement gate holds. |
| `test_mariners_armor_unequip_drops_flag` | PATCH the armor to `equipped: False` → `derived.swim_speed` absent; restores the original inventory on teardown. |

### `test_item_frost_brand.py`
v2.251.0 — Frost Brand (RAW DMG p.171, very rare, attunement): a magic sword dealing +1d6 cold on every hit + granting fire resistance while held. Double-substrate reuse with zero new engine code — the cold rider is a `frost-brand` row in `_MAGIC_ITEM_ATTACK_RIDERS` (Sun Blade shape minus the condition), the fire resistance a `frost-brand` `_MAGIC_ITEM_PASSIVES` entry reusing the v2.235.0 `resistance_to` surface. Seeded as a second attuned sword on Garrik Ironside (the weapon-rider showcase Fighter, alongside Flame Tongue). Both halves attunement-gated.

| Test | What it asserts |
|------|-----------------|
| `test_frost_brand_cold_rider_fires` | `POST /attack` (attack_index 4, override) vs. any target → `auto_uplifts` carries one `item-frost-brand` rider: label "Frost Brand", expression "1d6", damage_type "cold", total in [1, 12]. |
| `test_frost_brand_exposes_fire_resistance` | `GET /sheet-json` → `derived.resistances.types` contains "fire" with "Frost Brand" in `sources`. |
| `test_frost_brand_halves_fire_damage` | 20 fire damage to the wielder via `PATCH .../sheet-fields` drops HP by only 10 — `_resistance_halve` applies; restores HP on teardown. |
| `test_frost_brand_does_not_halve_cold` | Control: 20 cold damage applies in full (Frost Brand resists fire, not cold). |
| `test_frost_brand_suppressed_when_detuned` | Detuning via `/attune` drops fire from `derived.resistances` AND suppresses the cold rider; re-attunes on teardown. |

### `test_item_cloak_of_displacement.py`
v2.252.0 — Cloak of Displacement (RAW DMG p.158, rare, attunement): attacks against the wearer have disadvantage. The first ITEM-granted adv/dis source (advantage-disadvantage plan Phase 4a) — the wearer's equipped + attuned cloak sets `incoming_attacks_have_disadvantage` in `_equipped_item_effects` (from the `cloak-of-displacement` `_MAGIC_ITEM_PASSIVES` payload, attunement-gated), and the attack pipeline reads it at attack time via `_target_wearer_imposes_attack_disadvantage` (target combatant → character → sheet), folding it into the existing /attack + /npc_attack disadvantage source set. Seeded on Lyra Sunstrider (Bard) as a true attuned passive.

| Test | What it asserts |
|------|-----------------|
| `test_cloak_imposes_disadvantage_on_pc_attacker` | `POST /attack` (PC attacker, override) vs. the cloak-wearer → `roll_state_applied == "disadvantage_cloak_of_displacement"`. |
| `test_cloak_imposes_disadvantage_on_npc_attacker` | `POST /npc_attack` (NPC attacker) vs. the cloak-wearer → same `disadvantage_cloak_of_displacement` label (symmetric path). |
| `test_cloak_cancels_with_attacker_advantage` | Target also carries an `incoming_attacks_have_advantage` buff → adv + dis cancel to a straight `canceled_*` roll naming the cloak (PHB p.173). |
| `test_cloak_detuned_drops_disadvantage` | Detuning the cloak via `/attune` → the PC attack reverts to a straight roll (`roll_state_applied` None); re-attunes on teardown. |
| `test_cloak_exposes_derived_flag` | `GET /sheet-json` → `derived.incoming_attacks_have_disadvantage` present with "Cloak of Displacement" in `sources`. |

### `test_item_cloak_of_elvenkind.py`
v2.253.0 — Cloak of Elvenkind (RAW DMG p.158, uncommon, attunement): the wearer has advantage on Dexterity (Stealth) checks. The first ITEM-granted *check* advantage source (advantage-disadvantage plan Phase 4b) — the wearer's equipped + attuned cloak adds "stealth" to `check_advantage_on` in `_equipped_item_effects` (from the `cloak-of-elvenkind` `_MAGIC_ITEM_PASSIVES` payload, attunement-gated), and the `/roll` endpoint reads it via `_roll_item_check_advantage`, folding an advantage source into the existing PHB p.173 composition (after the Phase 2b condition-disadvantage step). Seeded on Rowan Quickbow (Ranger) as a 4th attuned item.

| Test | What it asserts |
|------|-----------------|
| `test_cloak_grants_stealth_advantage` | `POST /roll` (Stealth, `stat_key: "stealth"`) → breakdown contains `2d20kh1` + `roll_state_applied == "auto_advantage_cloak_of_elvenkind"`. |
| `test_cloak_does_not_help_non_stealth_check` | Control: `POST /roll` (Perception, `stat_key: "perception"`) → no `2d20kh1`, no advantage label (the skill gate). |
| `test_cloak_advantage_cancels_with_condition_disadvantage` | Wearer is Poisoned (ability-check disadvantage) → item adv + condition dis cancel to a straight `canceled_*` roll naming the cloak (PHB p.173). |
| `test_cloak_detuned_drops_stealth_advantage` | Detuning the cloak via a cap-independent sheet-fields PATCH → the Stealth roll reverts to a straight roll (`roll_state_applied` None); re-attunes on teardown. |
| `test_cloak_exposes_derived_flag` | `GET /sheet-json` → `derived.check_advantage_on` present with "stealth" in `skills` and "Cloak of Elvenkind" in `sources`. |

### `test_item_eyes_of_the_eagle.py`
v2.254.0 — Eyes of the Eagle (RAW DMG p.166, uncommon, attunement): the wearer has advantage on Wisdom (Perception) checks that rely on sight. A second item-granted *check* advantage source riding the v2.253.0 `check_advantage_on` substrate (Cloak of Elvenkind, Phase 4b) — only the skill key differs (`perception` vs. `stealth`). The wearer's equipped + attuned lenses add "perception" to `check_advantage_on` (from the `eyes-of-the-eagle` `_MAGIC_ITEM_PASSIVES` payload, attunement-gated), and `/roll` folds the advantage via the already-general `_roll_item_check_advantage`. Seeded on Mira Greenleaf (Druid, Perception-proficient, WIS 17) as a 4th attuned item.

| Test | What it asserts |
|------|-----------------|
| `test_eyes_grant_perception_advantage` | `POST /roll` (Perception, `stat_key: "perception"`) → breakdown contains `2d20kh1` + `roll_state_applied == "auto_advantage_eyes_of_the_eagle"`. |
| `test_eyes_do_not_help_non_perception_check` | Control: `POST /roll` (Stealth, `stat_key: "stealth"`) → no `2d20kh1`, no advantage label (the skill gate). |
| `test_eyes_advantage_cancels_with_condition_disadvantage` | Wearer is Poisoned (ability-check disadvantage) → item adv + condition dis cancel to a straight `canceled_*` roll naming the lenses (PHB p.173). |
| `test_eyes_detuned_drop_perception_advantage` | Detuning the lenses via a cap-independent sheet-fields PATCH → the Perception roll reverts to a straight roll (`roll_state_applied` None); re-attunes on teardown. |
| `test_eyes_expose_derived_flag` | `GET /sheet-json` → `derived.check_advantage_on` present with "perception" in `skills` and "Eyes of the Eagle" in `sources`. |

### `test_item_eyes_of_minute_seeing.py`
v2.292.0 — Eyes of Minute Seeing (RAW DMG p.166, uncommon, NO attunement): the wearer has advantage on Intelligence (Investigation) checks that rely on sight at close range. The no-attunement companion to Eyes of the Eagle on the same `check_advantage_on` substrate — only the skill key differs (`investigation`). The `eyes-of-minute-seeing` `_MAGIC_ITEM_PASSIVES` payload omits `requires_attunement` (Boots of Elvenkind precedent), so the lenses ride freely alongside a full 3/3 attunement loadout. No new helper or `/roll` code. Seeded equipped on Pip Quickfingers (Halfling Rogue).

| Test | What it asserts |
|------|-----------------|
| `test_eyes_grant_investigation_advantage` | `POST /roll` (Investigation, `stat_key: "investigation"`) → breakdown contains `2d20kh1` + `roll_state_applied == "auto_advantage_eyes_of_minute_seeing"`. |
| `test_eyes_do_not_help_non_investigation_check` | Control: `POST /roll` (Perception, `stat_key: "perception"`) → no `2d20kh1`, no advantage label (the skill gate). |
| `test_eyes_advantage_cancels_with_condition_disadvantage` | Wearer is Poisoned (ability-check disadvantage) → item adv + condition dis cancel to a straight `canceled_*` roll naming the lenses (PHB p.173). |
| `test_eyes_expose_derived_flag` | `GET /sheet-json` → `derived.check_advantage_on` present with "investigation" in `skills` and "Eyes of Minute Seeing" in `sources`. |

### `test_item_cloak_of_the_bat.py`
v2.293.0 — Cloak of the Bat (RAW DMG p.158, rare, attunement): the wearer has advantage on Dexterity (Stealth) checks. Another consumer of the `check_advantage_on` substrate, keyed on `stealth` and attunement-gated (the `cloak-of-the-bat` `_MAGIC_ITEM_PASSIVES` payload carries `requires_attunement`). No new helper or `/roll` code. Seeded as inert spare loot (unequipped/unattuned) on Magnus Shadowend (Fiend Warlock with Devil's Sight); tests PATCH it equipped+attuned, roll, then restore. The dim-light flight + polymorph-to-bat clauses are GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_cloak_grants_stealth_advantage` | Equipped+attuned via PATCH → `POST /roll` (Stealth) breakdown contains `2d20kh1` + `roll_state_applied == "auto_advantage_cloak_of_the_bat"`. Inventory restored on teardown. |
| `test_cloak_requires_attunement` | Equipped-but-unattuned → straight 1d20, no advantage label (the attunement gate). Restored on teardown. |
| `test_cloak_baseline_has_no_advantage` | Control: inert seed (equipped=False) → Stealth roll is a straight 1d20 (proves it's cloak-sourced). |
| `test_cloak_exposes_derived_flag` | Equipped+attuned → `GET /sheet-json` `derived.check_advantage_on` has "stealth" in `skills` and "Cloak of the Bat" in `sources`. Restored on teardown. |

### `test_item_boots_of_elvenkind.py`
v2.255.0 — Boots of Elvenkind (RAW DMG p.155, uncommon, NO attunement): the wearer has advantage on Dexterity (Stealth) checks that rely on moving silently. The no-attunement companion to Cloak of Elvenkind on the same `check_advantage_on: ["stealth"]` substrate — the `boots-of-elvenkind` `_MAGIC_ITEM_PASSIVES` payload omits `requires_attunement`, so the boots ride freely alongside a full 3/3 attunement loadout. No new helper or `/roll` code — the substrate generalizes over the skill key and the attunement gate. Seeded on Quan Reelstep (Drunken Master Monk) alongside his 3/3 attuned items (Belt of Dwarvenkind + Ioun Stone of Mastery + Mantle of Spell Resistance).

| Test | What it asserts |
|------|-----------------|
| `test_boots_grant_stealth_advantage` | `POST /roll` (Stealth, `stat_key: "stealth"`) → breakdown contains `2d20kh1` + `roll_state_applied == "auto_advantage_boots_of_elvenkind"`. |
| `test_boots_do_not_help_non_stealth_check` | Control: `POST /roll` (Perception, `stat_key: "perception"`) → no `2d20kh1`, no advantage label (the skill gate). |
| `test_boots_advantage_cancels_with_condition_disadvantage` | Wearer is Poisoned (ability-check disadvantage) → item adv + condition dis cancel to a straight `canceled_*` roll naming the boots (PHB p.173). |
| `test_boots_no_attunement_required` | The boots are NOT attuned and Quan is at the 3/3 cap, yet the Stealth roll still resolves `2d20kh1` — proving the payload rides free of the attunement gate. |
| `test_boots_unequip_drops_stealth_advantage` | Unequipping the boots via a sheet-fields PATCH → the Stealth roll reverts to a straight roll (`roll_state_applied` None); re-equips on teardown. |
| `test_boots_expose_derived_flag` | `GET /sheet-json` → `derived.check_advantage_on` present with "stealth" in `skills` and "Boots of Elvenkind" in `sources`. |

### `test_item_ring_of_water_walking.py`
v2.241.0 — Ring of Water Walking (RAW DMG p.193, uncommon, no attunement): stand on and move across any liquid surface as if it were solid ground. Reuses the boolean-OR passive substrate: the `water_walk` flag rides the `ring-of-water-walking` catalog payload, aggregates in `_equipped_item_effects`, and surfaces on `/sheet-json` as `derived.water_walk = {sources}`. Rowan Quickbow (Ranger) wears it — no attunement, riding alongside his full 3/3 attunement loadout.

| Test | What it asserts |
|------|-----------------|
| `test_ring_of_water_walking_exposes_flag` | `GET /sheet-json` → `derived.water_walk` present with "Ring of Water Walking" in `sources`. |
| `test_ring_of_water_walking_no_attunement_required` | The no-attunement flag rides alongside the Ioun Stone of Sustenance — `derived.no_food_or_drink` still reports alongside `water_walk`. |
| `test_ring_of_water_walking_unequip_drops_flag` | PATCH the ring to `equipped: False` → `derived.water_walk` absent; restores the original inventory on teardown. |

### `test_item_cap_of_water_breathing.py`
v2.256.0 — Cap of Water Breathing (RAW DMG p.157, uncommon, no attunement): the wearer can breathe normally underwater. Rides a new `water_breath` boolean-OR flag in `_equipped_item_effects` (the Ring of Water Walking pattern): the flag rides the `cap-of-water-breathing` catalog payload, aggregates with `water_breath_sources`, and surfaces on `/sheet-json` as `derived.water_breath = {sources}`. Seeded on Mira Greenleaf (Druid), pairing with her Ring of Swimming.

| Test | What it asserts |
|------|-----------------|
| `test_cap_of_water_breathing_exposes_flag` | `GET /sheet-json` → `derived.water_breath` present with "Cap of Water Breathing" in `sources`. |
| `test_cap_of_water_breathing_no_attunement_required` | The no-attunement flag rides alongside the Ring of Swimming — `derived.swim_speed` still reports alongside `water_breath`. |
| `test_cap_of_water_breathing_unequip_drops_flag` | PATCH the cap to `equipped: False` → `derived.water_breath` absent; restores the original inventory on teardown. |

### `test_item_ring_of_x_ray_vision.py`
v2.257.0 — Ring of X-ray Vision (RAW DMG p.193, rare, attunement): the wearer can see into and through solid matter (30-ft radius; blocked by 1 ft of stone / 1 in. of metal / 3 ft of wood or dirt). Rides a new `xray_vision` boolean-OR flag in `_equipped_item_effects` (the Cap of Water Breathing pattern, attunement-gated): the flag rides the `ring-of-x-ray-vision` catalog payload (`requires_attunement: True`), aggregates with `xray_vision_sources`, and surfaces on `/sheet-json` as `derived.xray_vision = {sources}` — only when equipped AND attuned. Seeded on Magnus Hexbinder (Warlock) as his 4th attuned item (seed-load bypasses the RAW 3-item cap).

| Test | What it asserts |
|------|-----------------|
| `test_ring_of_x_ray_vision_exposes_flag` | `GET /sheet-json` → `derived.xray_vision` present with "Ring of X-ray Vision" in `sources`. |
| `test_ring_of_x_ray_vision_detune_drops_flag` | PATCH the ring to `attuned: False` (still equipped) → `derived.xray_vision` absent — the attunement gate; restores the original inventory on teardown. |
| `test_ring_of_x_ray_vision_unequip_drops_flag` | PATCH the ring to `equipped: False` → `derived.xray_vision` absent; restores the original inventory on teardown. |

### `test_item_necklace_of_adaptation.py`
v2.258.0 — Necklace of Adaptation (RAW DMG p.183, uncommon, attunement): the wearer can breathe normally in any environment + has advantage on saves vs. harmful gases/vapors (GM-narrated in v1). Rides a new `env_adaptation` boolean-OR flag in `_equipped_item_effects` (the Ring of X-ray Vision pattern, attunement-gated): the flag rides the `necklace-of-adaptation` catalog payload (`requires_attunement: True`), aggregates with `env_adaptation_sources`, and surfaces on `/sheet-json` as `derived.env_adaptation = {sources}` — only when equipped AND attuned. Seeded on Garrik Ironside (Fighter) in his free neck slot.

| Test | What it asserts |
|------|-----------------|
| `test_necklace_of_adaptation_exposes_flag` | `GET /sheet-json` → `derived.env_adaptation` present with "Necklace of Adaptation" in `sources`. |
| `test_necklace_of_adaptation_detune_drops_flag` | PATCH the necklace to `attuned: False` (still equipped) → `derived.env_adaptation` absent — the attunement gate; restores the original inventory on teardown. |
| `test_necklace_of_adaptation_unequip_drops_flag` | PATCH the necklace to `equipped: False` → `derived.env_adaptation` absent; restores the original inventory on teardown. |

### `test_item_gloves_of_swimming_and_climbing.py`
v2.259.0 — Gloves of Swimming and Climbing (RAW DMG p.171, uncommon, attunement): climbing and swimming cost no extra movement + a +5 Athletics climb/swim bonus (GM-narrated in v1). Rides a new `climb_swim_ease` boolean-OR flag in `_equipped_item_effects` (the Ring of X-ray Vision pattern, attunement-gated): the flag rides the `gloves-of-swimming-and-climbing` catalog payload (`requires_attunement: True`), aggregates with `climb_swim_ease_sources`, and surfaces on `/sheet-json` as `derived.climb_swim_ease = {sources}` — only when equipped AND attuned. Seeded on Mira Greenleaf (Druid) in her free hand slot, completing her aquatic kit.

| Test | What it asserts |
|------|-----------------|
| `test_gloves_of_swimming_and_climbing_exposes_flag` | `GET /sheet-json` → `derived.climb_swim_ease` present with "Gloves of Swimming and Climbing" in `sources`. |
| `test_gloves_of_swimming_and_climbing_rides_alongside` | The attunement-gated flag rides alongside Mira's no-attunement aquatic items — `derived.water_breath` and `derived.swim_speed` still report alongside `climb_swim_ease`. |
| `test_gloves_of_swimming_and_climbing_detune_drops_flag` | PATCH the gloves to `attuned: False` (still equipped) → `derived.climb_swim_ease` absent — the attunement gate; restores the original inventory on teardown. |

### `test_item_ring_of_jumping.py`
v2.260.0 — Ring of Jumping (RAW DMG p.191, uncommon, attunement): the wearer can cast the jump spell on themselves at will as a bonus action (the tripled jump distance is GM-narrated in v1). Rides a new `jump_at_will` boolean-OR flag in `_equipped_item_effects` (the Ring of X-ray Vision pattern, attunement-gated): the flag rides the `ring-of-jumping` catalog payload (`requires_attunement: True`), aggregates with `jump_at_will_sources`, and surfaces on `/sheet-json` as `derived.jump_at_will = {sources}` — only when equipped AND attuned. Seeded on Kael Brightleaf (Monk) in his free ring finger, on-theme alongside Step of the Wind.

| Test | What it asserts |
|------|-----------------|
| `test_ring_of_jumping_exposes_flag` | `GET /sheet-json` → `derived.jump_at_will` present with "Ring of Jumping" in `sources`. |
| `test_ring_of_jumping_detune_drops_flag` | PATCH the ring to `attuned: False` (still equipped) → `derived.jump_at_will` absent — the attunement gate; restores the original inventory on teardown. |
| `test_ring_of_jumping_unequip_drops_flag` | PATCH the ring to `equipped: False` → `derived.jump_at_will` absent; restores the original inventory on teardown. |

### `test_item_bracers_of_archery.py`
v2.261.0 — Bracers of Archery (RAW DMG p.156, uncommon, attunement): +2 to damage rolls on ranged attacks made with a longbow or shortbow. The first passive-substrate item to feed the attack/damage path rather than a pure derived flag. Rides a new summed `ranged_bow_damage_bonus` int in `_equipped_item_effects` (attunement-gated): the bonus rides the `bracers-of-archery` catalog payload (`ranged_bow_damage_bonus: 2`, `requires_attunement: True`), aggregates with `ranged_bow_damage_bonus_sources`, surfaces on `/sheet-json` as `derived.ranged_bow_damage_bonus = {bonus, sources}`, and is appended to the damage expression at `/attack` time for a ranged "bow" (non-crossbow) weapon. Seeded on Rowan Quickbow (Ranger) on his forearms — distinct from his Gauntlets of Ogre Power (hands); the proficiency half is GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_bracers_of_archery_exposes_derived` | `GET /sheet-json` → `derived.ranged_bow_damage_bonus` present with `bonus: 2` and "Bracers of Archery" in `sources`. |
| `test_bracers_of_archery_detune_drops_derived` | PATCH the bracers to `attuned: False` (still equipped) → `derived.ranged_bow_damage_bonus` absent — the attunement gate; restores inventory on teardown. |
| `test_bracers_of_archery_unequip_drops_derived` | PATCH the bracers to `equipped: False` → `derived.ranged_bow_damage_bonus` absent; restores inventory on teardown. |
| `test_bracers_of_archery_adds_longbow_damage` | Dice-seeded (d20=10 no crit, d8=5): Rowan's Longbow deals 5+4+2=11 with bracers attuned; after detune the same seed deals 5+4=9. Restores inventory on teardown. |
| `test_bracers_of_archery_skips_melee_weapon` | Dice-seeded (d20=10, d6=4): Rowan's off-hand Shortsword (melee) deals 4 with no +2 — the ranged-bow gate. |

### `test_item_ring_of_free_action.py`
v2.240.0 — Ring of Free Action (RAW DMG p.191, rare, attunement): difficult terrain costs no extra movement; magic can't reduce your speed or paralyze/restrain you. Reuses the boolean-OR passive substrate: the `free_action` flag rides the `ring-of-free-action` catalog payload (with `requires_attunement`), aggregates in `_equipped_item_effects`, and surfaces on `/sheet-json` as `derived.free_action = {sources}` (descriptive in v1). Brakka Wildmane (Path of the Beast Barbarian) wears it as her 3rd attuned item.

| Test | What it asserts |
|------|-----------------|
| `test_ring_of_free_action_exposes_flag` | `GET /sheet-json` → `derived.free_action` present with "Ring of Free Action" in `sources`. |
| `test_ring_of_free_action_requires_attunement` | PATCH the ring to `attuned: False` → `derived.free_action` absent (attunement-gated); restores the original inventory on teardown. |
| `test_ring_of_free_action_composes_with_str_override` | The flag composes with Brakka's Belt of Giant Strength — `derived.effective_abilities.STR.effective == 29` still reports alongside `free_action`. |
| `test_ring_grants_paralyzed_restrained_immunity` | v2.289.0 — the mechanical half: the ring rides the v2.288.0 condition-immunity substrate, so `derived.condition_immunities.types` contains both "paralyzed" and "restrained" with the ring in `sources` (`_target_condition_immune` now blocks those installs on the wearer). |

### `test_item_boots_of_speed.py`
v2.239.0 — Boots of Speed (RAW DMG p.155, rare, attunement): a bonus action doubles walking speed and gives opportunity attacks against you disadvantage, for up to 10 minutes. Reuses the boolean-OR passive substrate: the `speed_doubling` flag rides the `boots-of-speed` catalog payload (with `requires_attunement`), aggregates in `_equipped_item_effects`, and surfaces on `/sheet-json` as `derived.speed_doubling = {sources}` (the toggle + 10-minute budget are GM-narrated in v1). Krieger Stonefist (Barbarian) wears them as his 3rd attuned item (Ioun Stone of Wisdom + Ioun Stone of Awareness + boots).

| Test | What it asserts |
|------|-----------------|
| `test_boots_of_speed_expose_speed_doubling` | `GET /sheet-json` → `derived.speed_doubling` present with "Boots of Speed" in `sources`. |
| `test_boots_of_speed_require_attunement` | PATCH the boots to `attuned: False` → `derived.speed_doubling` absent (attunement-gated); restores the original inventory on teardown. |
| `test_boots_of_speed_compose_with_awareness` | The flag composes with Krieger's Ioun Stone of Awareness — `derived.cannot_be_surprised` still reports alongside `speed_doubling` from the same walker. |

### `test_item_winged_boots.py`
v2.238.0 — Winged Boots (RAW DMG p.214, uncommon, attunement): flying speed equal to walking speed for up to 4 hours. Reuses the boolean-OR passive substrate: the `flying_speed` flag rides the `winged-boots` catalog payload (with `requires_attunement`), aggregates in `_equipped_item_effects`, and surfaces on `/sheet-json` as `derived.flying_speed = {sources}` (the 4-hour charge budget is GM-narrated in v1). Kael Brightleaf (Way of the Open Hand Monk) wears them as his 3rd attuned item (Bracers of Defense + Amulet of Proof + boots).

| Test | What it asserts |
|------|-----------------|
| `test_winged_boots_expose_flying_speed` | `GET /sheet-json` → `derived.flying_speed` present with "Winged Boots" in `sources`. |
| `test_winged_boots_require_attunement` | PATCH the boots to `attuned: False` → `derived.flying_speed` absent (attunement-gated); restores the original inventory on teardown. |
| `test_winged_boots_compose_with_scry_proof` | The flag composes with Kael's Amulet of Proof — `derived.scry_proof` still reports alongside `flying_speed` from the same walker. |

### `test_item_slippers_of_spider_climbing.py`
v2.237.0 — Slippers of Spider Climbing (RAW DMG p.199, uncommon, no attunement): while worn, you can move up, down, and across vertical surfaces and upside down along ceilings, hands-free, with a climbing speed equal to your walking speed. Reuses the boolean-OR passive substrate: the `spider_climb` flag rides the `slippers-of-spider-climbing` catalog payload, aggregates in `_equipped_item_effects`, and surfaces on `/sheet-json` as `derived.spider_climb = {sources}` (the climbing-speed numeric is GM-narrated in v1). Pip Quickfingers (Halfling Rogue) wears them — no attunement (she is at the 3/3 attunement cap).

| Test | What it asserts |
|------|-----------------|
| `test_slippers_expose_spider_climb` | `GET /sheet-json` → `derived.spider_climb` present with "Slippers of Spider Climbing" in `sources`. |
| `test_slippers_compose_with_goggles_darkvision` | The no-attunement flag rides alongside Pip's Goggles of Night — both no-attunement wondrous items contribute from the same walker; asserts she still carries the goggles. |
| `test_slippers_unequip_drops_flag` | PATCH the slippers to `equipped: False` → `derived.spider_climb` absent; restores the original inventory on teardown. |

### `test_item_mantle_of_spell_resistance.py`
v2.236.0 — Mantle of Spell Resistance (RAW DMG p.180, rare, attunement): advantage on saving throws against spells while worn. Reuses the boolean-OR passive substrate (Sustenance / Awareness / Periapt of Health / Amulet of Proof): the `spell_save_advantage` flag rides the `mantle-of-spell-resistance` catalog payload, aggregates in `_equipped_item_effects`, and surfaces on `/sheet-json` as `derived.spell_save_advantage = {sources}` (descriptive-only in v1). Quan Reelstep (Drunken Master Monk) wears it as his 3rd attuned item.

| Test | What it asserts |
|------|-----------------|
| `test_mantle_exposes_spell_save_advantage` | `GET /sheet-json` → `derived.spell_save_advantage` present with "Mantle of Spell Resistance" in `sources`. |
| `test_mantle_coexists_with_other_attuned_items` | The flag composes with the Ioun Stone of Mastery on the same PC — `derived.proficiency_bonus.effective == 4` still reports alongside `spell_save_advantage`. |
| `test_mantle_unequip_drops_flag` | PATCH the mantle to `equipped: False` → `derived.spell_save_advantage` absent; restores the original inventory on teardown. |

### `test_item_ring_of_resistance.py`
v2.235.0 — Ring of Resistance (RAW DMG p.192, rare, attunement): resistance to one damage type (the gem indicates which). Unlike the recent passive flags this is a real mechanical effect — the resisted type rides the inventory item via the per-item `_resistance_type` rider on the shared `ring-of-resistance` slug, aggregates in `_equipped_item_effects` (`resistance_to` list), and is consulted by `_resistance_halve` in the live damage pipeline so matching damage is halved through `PATCH .../sheet-fields`. Surfaces on `/sheet-json` as `derived.resistances = {types, sources}`. Dame Seraphine Vael (Vengeance Paladin) wears a Ring of Resistance (Fire) as her 3rd attuned item.

| Test | What it asserts |
|------|-----------------|
| `test_ring_exposes_resistances_on_sheet_json` | `GET /sheet-json` → `derived.resistances.types` contains "fire" with "Ring of Resistance" in `sources`. |
| `test_ring_halves_matching_damage` | 20 fire damage to the fire-resisted wearer drops HP by only 10 — `_resistance_halve` halves it; restores HP on teardown. |
| `test_ring_does_not_halve_other_types` | Control: 20 cold damage applies in full (−20) — the resistance is type-specific; restores HP on teardown. |

### `test_item_ring_of_elemental_command.py`
v2.305.0 — Ring of Elemental Command (Fire) (RAW DMG p.190, legendary, attunement): the Fire variant grants fire-damage resistance immediately on attunement (Air/Earth/Water gate theirs behind slaying an elemental). Rides the same `_resistance_type` substrate as Ring of Resistance / Dragon Scale Mail — `_resistance_halve` halves matching fire damage, surfaced on `/sheet-json` as `derived.resistances`. Seeded inert (unequipped/unattuned) on Magnus Hexbinder (Fiend Warlock, whose Bronze Dragonborn racial resistance is LIGHTNING not fire, so the baseline cleanly proves the source); tests PATCH it equipped+attuned, deal fire damage, then restore inventory + HP.

| Test | What it asserts |
|------|-----------------|
| `test_ring_baseline_takes_full_fire_damage` | Control: inert seed (equipped=False) → 20 fire lands in full (−20), proving no fire-resistance baseline. Restores on teardown. |
| `test_ring_halves_fire_damage_when_attuned` | Equip+attune → 20 fire drops HP by only 10 via `_resistance_halve`. Restores on teardown. |
| `test_ring_requires_attunement` | Attunement gate: equipped-but-un-attuned → 20 fire applies in full (−20). Restores on teardown. |
| `test_ring_exposes_resistances_on_sheet_json` | Equip+attune → `derived.resistances.types` contains "fire" with "Ring of Elemental Command" in `sources`. Restores on teardown. |

### `test_item_helm_of_telepathy.py`
v2.307.0 — Helm of Telepathy (RAW DMG p.169, uncommon, attunement): the always-on telepathic-communication ability rides the boolean-flag substrate (the v2.245.0 `mind_shield` / Ring of Feather Falling `feather_fall` path) — a `telepathy` flag aggregated in `_equipped_item_effects` and surfaced on `/sheet-json` as `derived.telepathy = {sources}`. The detect-thoughts / 1-per-dawn suggestion casts are GM-narrated in v1. Seeded inert (unequipped/unattuned) on Thalindra Moonshadow (Wizard), who carries no other telepathy item so the baseline cleanly proves the source; tests PATCH it equipped+attuned, read the projection, then restore the seed inventory.

| Test | What it asserts |
|------|-----------------|
| `test_helm_exposes_telepathy` | Equip+attune → `derived.telepathy.sources` names "Helm of Telepathy". Restores on teardown. |
| `test_helm_requires_attunement` | Attunement gate: equipped-but-un-attuned → no `telepathy` flag. Restores on teardown. |
| `test_helm_baseline_has_no_flag` | Control: inert seed (equipped=False) → no `telepathy` flag, proving it's helm-sourced. |

### `test_item_armor_of_vulnerability.py`
v2.306.0 — Armor of Vulnerability (RAW DMG p.152, rare, attunement, CURSED): the demo's plate variant resists slashing AND (the curse) is vulnerable to bludgeoning + piercing. The resistance rides the v2.235.0 `_resistance_type`/`resistance_to` substrate (`_resistance_halve`); the vulnerability needed a NEW mirror — `_vulnerability_double` now reads `_equipped_item_effects().get("vulnerability_to")`, folded by the walker from a `vulnerability_to` payload list. Both surface on `/sheet-json` as `derived.resistances` / `derived.vulnerabilities`. Seeded inert (unequipped/unattuned) on Sir Caelan Lightbringer (Paladin), who has no physical resistance/vulnerability baseline so the inert state takes full damage on all three physical types — cleanly proving the armor is the source; tests PATCH it equipped+attuned, deal typed damage, then restore inventory + HP.

| Test | What it asserts |
|------|-----------------|
| `test_baseline_takes_full_physical_damage` | Control: inert seed (equipped=False) → 20 bludgeoning lands in full (−20), proving no physical resistance/vulnerability baseline. Restores on teardown. |
| `test_armor_halves_slashing` | Equip+attune → 20 slashing drops HP by only 10 via `_resistance_halve`. Restores on teardown. |
| `test_armor_doubles_bludgeoning` | Equip+attune → 20 bludgeoning drops HP by 40 via `_vulnerability_double`. Restores on teardown. |
| `test_armor_doubles_piercing` | Equip+attune → 20 piercing drops HP by 40 (the second vulnerable type). Restores on teardown. |
| `test_armor_requires_attunement` | Attunement gate: equipped-but-un-attuned → neither resistance nor vulnerability applies; 20 bludgeoning lands in full (−20). Restores on teardown. |
| `test_armor_exposes_derived_flags` | Equip+attune → `derived.resistances.types` contains "slashing" and `derived.vulnerabilities.types` contains "bludgeoning" + "piercing" with "Armor of Vulnerability" named in vulnerability `sources`. Restores on teardown. |

### `test_item_cloak_of_arachnida.py`
v2.279.0 — Cloak of Arachnida (RAW DMG p.158, very rare, attunement): resistance to poison damage AND a climbing speed equal to walking speed. Two existing substrates compose in one passive payload — the poison `resistance_to` folds into the aggregated list `_resistance_halve` consults (surfaced as `derived.resistances`), and `spider_climb` surfaces as `derived.spider_climb` (the Slippers substrate). Seeded as inert spare loot on Lyra Sunstrider (already at the 3-item attunement cap); tests PATCH it equipped+attuned, then restore inventory/HP on teardown.

| Test | What it asserts |
|------|-----------------|
| `test_cloak_exposes_poison_resistance_and_spider_climb` | On equip, `derived.resistances.types` contains "poison" and `derived.spider_climb.sources` both name "Cloak of Arachnida". |
| `test_cloak_unequipped_baseline_has_no_poison_resistance` | Inert (seed) state: no poison resistance and no spider_climb in `derived` — both are item-sourced. |
| `test_cloak_halves_poison_damage` | 20 poison damage to the cloak-wearer drops HP by only 10 via `_resistance_halve`; restores inventory + HP on teardown. |

### `test_item_dragon_scale_mail.py`
v2.279.0 — Dragon Scale Mail (RAW DMG p.165, very rare, attunement): +1 AC (descriptive in v1) + resistance to one color-keyed damage type (Blue → lightning). The type rides the per-item `_resistance_type` rider on the shared `dragon-scale-mail` slug (the Ring of Resistance pattern), surfaced as `derived.resistances`. Seeded as inert spare loot on Garrik Ironside (Blue/lightning chosen because his Frost Brand already grants fire resistance); tests PATCH it equipped+attuned, then restore inventory/HP on teardown.

| Test | What it asserts |
|------|-----------------|
| `test_dragon_scale_mail_exposes_lightning_resistance` | On equip, `derived.resistances.types` contains "lightning" with "Dragon Scale Mail" in `sources`. |
| `test_dragon_scale_mail_baseline_has_no_lightning_resistance` | Inert (seed) state: no lightning resistance — proving it's item-sourced. |
| `test_dragon_scale_mail_halves_lightning_damage` | 20 lightning damage drops HP by only 10 via `_resistance_halve`; restores inventory + HP on teardown. |
| `test_dragon_scale_mail_does_not_halve_other_types` | Control: 20 cold damage applies in full (−20) — Blue scales resist only lightning; restores inventory + HP on teardown. |

### `test_item_helm_of_brilliance.py`
v2.280.0 — Helm of Brilliance (RAW DMG p.173, very rare, attunement): v1 wires the clean passive — "as long as the helm has at least one ruby, you have resistance to fire damage." The flat `resistance_to: "fire"` payload aggregates in `_equipped_item_effects` (the Ring of Resistance / Dragon Scale Mail substrate) and surfaces as `derived.resistances`. The gem spells, undead aura, flaming-weapon rider, and gem-burst hazard are GM-narrated. Seeded as inert spare loot on Thalindra Moonwhisper (past her attunement cap, no fire-resistance baseline); tests PATCH it equipped+attuned, then restore inventory/HP on teardown.

| Test | What it asserts |
|------|-----------------|
| `test_helm_exposes_fire_resistance` | On equip, `derived.resistances.types` contains "fire" with "Helm of Brilliance" in `sources`. |
| `test_helm_baseline_has_no_fire_resistance` | Inert (seed) state: no fire resistance — proving it's item-sourced. |
| `test_helm_halves_fire_damage` | 20 fire damage drops HP by only 10 via `_resistance_halve`; restores inventory + HP on teardown. |

### `test_item_wings_of_flying.py`
v2.281.0 — Wings of Flying (RAW DMG p.214, rare, attunement): grants a flying speed of 60 ft while worn. Reuses the v2.238.0 Winged Boots `flying_speed` boolean substrate with zero new engine code — the flag rides the `wings-of-flying` payload, aggregates in `_equipped_item_effects`, and surfaces as `derived.flying_speed`. The command-word activation + 1-hour duration / 1d12-hour cooldown are GM-narrated. Seeded as inert spare loot on Rowan Quickbow; tests PATCH it equipped+attuned, then restore inventory on teardown.

| Test | What it asserts |
|------|-----------------|
| `test_wings_expose_flying_speed` | On equip, `derived.flying_speed` is present with "Wings of Flying" in `sources`. |
| `test_wings_baseline_has_no_flying_speed` | Inert (seed) state: no `derived.flying_speed` — proving it's item-sourced. |
| `test_wings_require_attunement` | Equipped-but-unattuned yields no `derived.flying_speed` (attunement gate); restores inventory on teardown. |

### `test_item_broom_of_flying.py`
v2.282.0 — Broom of Flying (RAW DMG p.156, uncommon, NO attunement): grants a flying speed of 50 ft while ridden. Reuses the v2.238.0 Winged Boots `flying_speed` boolean substrate with zero new engine code — the flag rides the `broom-of-flying` payload (no `requires_attunement`), so it surfaces while merely equipped. The command-word ride + 50-ft speed / 400-lb capacity are GM-narrated. Seeded as inert spare loot on Zara Emberfire; tests PATCH it equipped, then restore inventory on teardown. Closes the SRD flying-item cluster.

| Test | What it asserts |
|------|-----------------|
| `test_broom_exposes_flying_speed` | On equip, `derived.flying_speed` is present with "Broom of Flying" in `sources`. |
| `test_broom_baseline_has_no_flying_speed` | Inert (seed) state: no `derived.flying_speed` — proving it's item-sourced. |
| `test_broom_needs_no_attunement` | Equipped-but-unattuned STILL surfaces `derived.flying_speed` — the broom is a no-attunement item (unlike Wings of Flying / Winged Boots). |

### `test_item_carpet_of_flying.py`
v2.283.0 — Carpet of Flying (RAW DMG p.157, very rare, NO attunement): grants a size-keyed flying speed (30-80 ft) while ridden. Reuses the v2.238.0 Winged Boots `flying_speed` boolean substrate with zero new engine code — the flag rides the `carpet-of-flying` payload (no `requires_attunement`), so it surfaces while merely equipped. The command-word ride + size-keyed speed/capacity are GM-narrated. Seeded as inert spare loot on Pip Quickfingers; tests PATCH it equipped, then restore inventory on teardown.

| Test | What it asserts |
|------|-----------------|
| `test_carpet_exposes_flying_speed` | On equip, `derived.flying_speed` is present with "Carpet of Flying" in `sources`. |
| `test_carpet_baseline_has_no_flying_speed` | Inert (seed) state: no `derived.flying_speed` — proving it's item-sourced. |
| `test_carpet_needs_no_attunement` | Equipped-but-unattuned STILL surfaces `derived.flying_speed` — the carpet is a no-attunement item (like the Broom of Flying). |

### `test_item_boots_of_levitation.py`
v2.284.0 — Boots of Levitation (RAW DMG p.155, rare, attunement). First item on the NEW `levitate_at_will` boolean substrate (init / walker boolean-OR / `/sheet-json` projection, mirroring the v2.238.0 flying-speed pattern). Seeded as inert spare loot on Magnus Hexbinder; tests PATCH it equipped+attuned and restore on teardown.

| Test | What it asserts |
|------|-----------------|
| `test_boots_expose_levitate_at_will` | On equip (attuned), `derived.levitate_at_will` is present with "Boots of Levitation" in `sources`. |
| `test_boots_baseline_has_no_levitate` | Inert (seed) state: no `derived.levitate_at_will` — proving it's item-sourced. |
| `test_boots_require_attunement` | Equipped-but-unattuned yields NO `derived.levitate_at_will` — the attunement gate holds. |

### `test_item_robe_of_stars.py`
v2.287.0 — Robe of Stars (RAW DMG p.193, very rare, attunement). Pure data drop-in on the v2.158.74 `save_bonus` substrate (the Cloak of Protection path): +1 to saving throws while worn. Seeded as inert spare loot on Thalindra Moonwhisper (already past the attunement cap); tests PATCH it equipped+attuned, roll a save, and restore on teardown.

| Test | What it asserts |
|------|-----------------|
| `test_robe_grants_save_bonus` | On equip (attuned), a `wis_save` `POST /roll` breakdown names "Robe of Stars" and the summed save bonus rises by exactly 1 over the inert baseline (robust to Thalindra's co-equipped Cloak/Staff save bonuses). |
| `test_robe_baseline_has_no_robe_bonus` | Inert (seed) state: "Robe of Stars" absent from the save breakdown — proving the +1 is robe-sourced. |
| `test_robe_requires_attunement` | Equipped-but-unattuned yields no robe bonus in the save breakdown — the attunement gate holds. |

### `test_item_periapt_of_proof_against_poison.py`
v2.288.0 — Periapt of Proof against Poison (RAW DMG p.184, rare, no attunement). First item on the v2.288.0 item-passive IMMUNITY substrate (parallel of the v2.235.0 resistance substrate): `immunity_to: ["poison"]` folds into the aggregated `immunity_to` list consulted by `_immunity_zero` (zeroes poison damage), and `condition_immunity_to: ["poisoned"]` into the list consulted by `_target_condition_immune` (blocks the poisoned buff-install). Both surface on `/sheet-json` as `derived.immunities` / `derived.condition_immunities`. Seeded as inert spare loot on Garrik Ironside; tests PATCH it equipped and restore on teardown.

| Test | What it asserts |
|------|-----------------|
| `test_periapt_grants_poison_damage_immunity` | On equip, `derived.immunities.types` contains "poison" with "Periapt of Proof against Poison" in `sources`. |
| `test_periapt_grants_poisoned_condition_immunity` | On equip, `derived.condition_immunities.types` contains "poisoned". |
| `test_periapt_baseline_has_no_immunity` | Inert (seed) state: neither poison nor poisoned surfaces — proving it's item-sourced. |

### `test_item_armor_of_invulnerability.py`
v2.290.0 — Armor of Invulnerability (RAW DMG p.152, legendary, attunement). The always-on passive ("resistance to nonmagical damage") rides the v2.235.0 item-passive resistance substrate: the `armor-of-invulnerability` payload folds the full `nonmagical-<type>` `resistance_to` list (the gaseous-form shape), so `_resistance_halve`'s F6-aware compare halves a nonmagical hit of any type but passes magical-source damage at full. Surfaces on `/sheet-json` as `derived.resistances`. The 10-min total-immunity action is GM-narrated in v1. Seeded as inert spare loot on Garrik Ironside; tests PATCH it equipped+attuned and restore inventory + HP on teardown.

| Test | What it asserts |
|------|-----------------|
| `test_armor_exposes_nonmagical_resistances` | On equip+attune, `derived.resistances.types` contains "nonmagical-bludgeoning" with "Armor of Invulnerability" in `sources`. |
| `test_armor_halves_nonmagical_damage` | End-to-end: 20 nonmagical slashing drops HP by only 10 via `_resistance_halve` (is_magical=False sheet-fields path). |
| `test_armor_baseline_has_no_resistance` | Inert (seed) state: no nonmagical-resistance projection — proving it's armor-sourced. |

### `test_item_spellguard_shield.py`
v2.291.0 — Spellguard Shield (RAW DMG p.201, very rare, attunement). The clean passive ("advantage on saves vs spells/magical effects") rides the v2.236.0 `spell_save_advantage` substrate — a verbatim clone of the Mantle of Spell Resistance payload on a new slug, folding the boolean-OR field that surfaces on `/sheet-json` as `derived.spell_save_advantage`. Advantage is descriptive in v1; the spell-attack-disadvantage half is GM-narrated. Seeded as inert spare loot on Sir Caelan Lightbringer; tests PATCH it equipped+attuned and restore on teardown.

| Test | What it asserts |
|------|-----------------|
| `test_shield_grants_spell_save_advantage` | On equip+attune, `derived.spell_save_advantage` present with "Spellguard Shield" in `sources`. |
| `test_shield_requires_attunement` | Equipped-but-unattuned: no spellguard-sourced advantage (attunement gate). |
| `test_shield_baseline_has_no_advantage` | Inert (seed) state: no spellguard-sourced advantage — proving it's shield-sourced. |

### `test_item_amulet_of_proof_against_detection.py`
v2.234.0 — Amulet of Proof against Detection (RAW DMG p.150, uncommon, attunement): hidden from divination magic + magical scrying while worn. Reuses the boolean-OR passive substrate (Sustenance / Awareness / Periapt of Health): the `scry_proof` flag rides the `amulet-of-proof-against-detection` catalog payload, aggregates in `_equipped_item_effects`, and surfaces on `/sheet-json` as `derived.scry_proof = {sources}`. Kael Brightleaf (Monk Lv 7) wears it as his 2nd attuned item.

| Test | What it asserts |
|------|-----------------|
| `test_amulet_exposes_scry_proof_on_sheet_json` | `GET /sheet-json` → `derived.scry_proof` present with "Amulet of Proof against Detection" in `sources`. |
| `test_amulet_coexists_with_bracers_ac` | The scry-proof flag rides alongside Kael's Bracers of Defense (still in inventory) — the new boolean field composes with the existing AC-bonus item. |
| `test_amulet_unequip_drops_flag` | PATCH the amulet to `equipped: False` → `derived.scry_proof` absent; restores the original inventory on teardown. |

### `test_item_amulet_of_proof_against_detection_and_location.py`
v2.294.0 — Amulet of Proof against Detection and Location (RAW DMG p.150, uncommon, attunement): the "and Location" sibling of the v2.234.0 amulet — identical RAW text + the same `scry_proof` boolean substrate. A verbatim payload clone on the new slug (`amulet-of-proof-against-detection-and-location`). Seeded as inert spare loot (unequipped/unattuned) on Thalindra Moonshadow (Wizard, no other scry-proof item, so the baseline cleanly proves the source); tests PATCH it equipped+attuned, read the projection, then restore.

| Test | What it asserts |
|------|-----------------|
| `test_amulet_exposes_scry_proof` | Equipped+attuned via PATCH → `GET /sheet-json` `derived.scry_proof` present with "Amulet of Proof against Detection and Location" in `sources`. Restored on teardown. |
| `test_amulet_requires_attunement` | Equipped-but-unattuned → no `scry_proof` flag (the attunement gate). Restored on teardown. |
| `test_amulet_baseline_has_no_flag` | Control: inert seed (equipped=False) → no `scry_proof` flag (proves it's amulet-sourced). |

### `test_item_rod_of_alertness.py`
v2.296.0 — Rod of Alertness (RAW DMG p.193, very rare, attunement): advantage on Wisdom (Perception) checks via the v2.253.0 `check_advantage_on` substrate (initiative advantage + rod spells + protective aura GM-narrated). Seeded as inert spare loot (unequipped/unattuned) on Garrik Ironside (Fighter, no other perception-advantage item, so the baseline cleanly proves the source); tests PATCH it equipped+attuned, roll a Perception check, then restore.

| Test | What it asserts |
|------|-----------------|
| `test_rod_grants_perception_advantage` | Equipped+attuned via PATCH, battle seeded → `POST /roll` (WIS Perception) breakdown contains `2d20kh1` and `roll_state_applied == auto_advantage_rod_of_alertness`. Restored on teardown. |
| `test_rod_requires_attunement` | Equipped-but-unattuned → no `2d20kh1`, no `roll_state_applied` (the attunement gate). Restored on teardown. |
| `test_rod_baseline_has_no_advantage` | Control: inert seed (equipped=False) → straight `1d20`, no advantage (proves it's rod-sourced). |
| `test_rod_exposes_derived_flag` | Equipped+attuned → `GET /sheet-json` `derived.check_advantage_on` has "perception" in `skills` and "Rod of Alertness" in `sources`. Restored on teardown. |

### `test_item_cloak_of_the_manta_ray.py`
v2.300.0 — Cloak of the Manta Ray (RAW DMG p.158, uncommon, no attunement): underwater breathing + 60 ft swim speed, composing two existing no-attunement boolean substrates in one payload (`water_breath` from the Cap of Water Breathing + `swim_speed` from the Ring of Swimming). Seeded as inert spare loot (unequipped) on Rowan Quickbow (Ranger, no other water_breath/swim_speed item — his Ring of Water Walking is the distinct `water_walk` flag); tests PATCH it equipped, read both derived flags, then restore.

| Test | What it asserts |
|------|-----------------|
| `test_cloak_equipped_exposes_both_flags` | Equipped via PATCH → `GET /sheet-json` `derived.water_breath` AND `derived.swim_speed` both present, each naming "Cloak of the Manta Ray" in `sources`. Restored on teardown. |
| `test_cloak_no_attunement_required` | Equipped while `attuned` stays False → both flags still surface (no attunement gate). Restored on teardown. |
| `test_cloak_baseline_has_neither_flag` | Control: inert seed (equipped=False) → neither `water_breath` nor `swim_speed` in derived (proves both are cloak-sourced). |
| `test_cloak_unequip_drops_flags` | Equip → both flags present; unequip → both removed. Restored on teardown. |

### `test_item_elven_chain.py`
v2.301.0 — Elven Chain (RAW DMG p.150, rare, NO attunement): "+1 bonus to AC while you wear this armor", riding the existing `ac_bonus` substrate (Cloak/Ring of Protection / Bracers of Defense precedent) consumed by `_read_target_ac`. Seeded as inert spare loot (unequipped) on Pip Quickfingers (Halfling Rogue); since she already wears a Cloak + Ring of Protection, tests measure the *delta* — read `target_ac` inert, PATCH equipped, assert +1 — via `/attack` with `override: True`, then restore.

| Test | What it asserts |
|------|-----------------|
| `test_elven_chain_adds_one_to_target_ac` | Inert baseline `target_ac` vs equipped → rises by exactly 1. Restored on teardown. |
| `test_elven_chain_no_attunement_required` | Equipped while `attuned` stays False → the +1 still applies (no attunement gate). Restored on teardown. |
| `test_elven_chain_unequip_drops_bonus` | Equip → +1; unequip → `target_ac` back to baseline. Restored on teardown. |

### `test_item_glamoured_studded_leather.py`
v2.323.0 — Glamoured Studded Leather (RAW DMG p.172, rare, NO attunement): "+1 bonus to AC while you wear this armor", riding the same `ac_bonus` substrate as Elven Chain. Seeded inert on Lyra Sunstrider (Bard); tests measure the *delta* on `target_ac` via `/attack`. The bonus-action illusory-disguise property is GM-narrated. Pairs thematically with the v2.321.0 Hat of Disguise (also on Lyra).

| Test | What it asserts |
|------|-----------------|
| `test_glamoured_adds_one_to_target_ac` | Inert baseline `target_ac` vs equipped → rises by exactly 1. Restored on teardown. |
| `test_glamoured_no_attunement_required` | Equipped while `attuned` stays False → the +1 still applies (no attunement gate). Restored on teardown. |
| `test_glamoured_unequip_drops_bonus` | Equip → +1; unequip → `target_ac` back to baseline. Restored on teardown. |

### `test_item_dwarven_plate.py`
v2.302.0 — Dwarven Plate (RAW DMG p.150, very rare, NO attunement): "+2 bonus to AC while you wear this armor", riding the same `ac_bonus` substrate as the Elven Chain (consumed by `_read_target_ac`). Seeded as inert spare loot (unequipped) on Garrik Ironside (Fighter, no other `ac_bonus` item); tests measure the *delta* — read `target_ac` inert, PATCH equipped, assert +2 — via `/attack` with `override: True`, then restore.

| Test | What it asserts |
|------|-----------------|
| `test_dwarven_plate_adds_two_to_target_ac` | Inert baseline `target_ac` vs equipped → rises by exactly 2. Restored on teardown. |
| `test_dwarven_plate_no_attunement_required` | Equipped while `attuned` stays False → the +2 still applies (no attunement gate). Restored on teardown. |
| `test_dwarven_plate_unequip_drops_bonus` | Equip → +2; unequip → `target_ac` back to baseline. Restored on teardown. |

### `test_item_boots_of_striding_and_springing.py`
v2.303.0 — Boots of Striding and Springing (RAW DMG p.156, uncommon, attunement): tripled jump distance, riding the v2.260.0 `jump_at_will` boolean substrate (the Ring of Jumping flag) surfaced on `/sheet-json` as `derived.jump_at_will = {sources}`. Seeded as inert spare loot (unequipped/unattuned) on Sir Caelan Lightbringer (Paladin, no other jump_at_will item — his Ring of Feather Falling is the distinct `feather_fall` flag); tests PATCH it equipped+attuned, read the derived flag, then restore.

| Test | What it asserts |
|------|-----------------|
| `test_boots_equipped_exposes_flag` | Equip+attune via PATCH → `GET /sheet-json` `derived.jump_at_will` present, naming "Boots of Striding and Springing" in `sources`. Restored on teardown. |
| `test_boots_detune_drops_flag` | Attunement gate: equipped-but-un-attuned → no `jump_at_will`. Restored on teardown. |
| `test_boots_baseline_has_no_flag` | Control: inert seed (equipped=False) → no `jump_at_will` (proves boots-sourced). |
| `test_boots_unequip_drops_flag` | Equip+attune → flag present; unequip → removed. Restored on teardown. |

### `test_item_scimitar_of_speed.py`
v2.315.0 — Scimitar of Speed (RAW DMG p.197, very rare, attunement): +2 attack/damage (baked on the wielder's attack row, Dragon Slayer / Vorpal precedent) AND one bonus-action attack per turn, riding the new v2.315.0 `bonus_action_attack` boolean substrate (mirrors telepathy / jump_at_will / feather_fall) surfaced on `/sheet-json` as `derived.bonus_action_attack = {sources}`. The extra-attack action-economy is GM-narrated. Seeded as inert spare loot (unequipped/unattuned) on Sir Caelan Lightbringer (Paladin, no other `bonus_action_attack` item); tests PATCH it equipped+attuned, read the derived flag, then restore.

| Test | What it asserts |
|------|-----------------|
| `test_scimitar_equipped_exposes_flag` | Equip+attune via PATCH → `GET /sheet-json` `derived.bonus_action_attack` present, naming "Scimitar of Speed" in `sources`. Restored on teardown. |
| `test_scimitar_detune_drops_flag` | Attunement gate: equipped-but-un-attuned → no `bonus_action_attack`. Restored on teardown. |
| `test_scimitar_baseline_has_no_flag` | Control: inert seed (equipped=False) → no `bonus_action_attack` (proves scimitar-sourced). |
| `test_scimitar_unequip_drops_flag` | Equip+attune → flag present; unequip → removed. Restored on teardown. |

### `test_item_demon_armor.py`
v2.304.0 — Demon Armor (RAW DMG p.158, very rare, attunement): "+1 bonus to AC", riding the same `ac_bonus` substrate the Dwarven Plate / Elven Chain / Cloak of Protection feed into `_read_target_ac` (so equipped+attuned reads as `target_ac = base + 1`). Attunement-gated (the payload carries `requires_attunement`). Abyssal speech, magic clawed-gauntlet unarmed strikes, and the can't-doff curse are GM-narrated. Seeded as inert spare loot (unequipped/unattuned) on Dame Seraphine Vael (Vengeance Paladin, no other `ac_bonus` item); tests measure the inert-vs-equipped delta via `/attack` `target_ac`, then restore.

| Test | What it asserts |
|------|-----------------|
| `test_demon_armor_adds_one_to_target_ac` | Equip+attune via PATCH → `target_ac` (from `/attack` with `override: True`) rises by exactly 1 vs the inert baseline. Restored on teardown. |
| `test_demon_armor_requires_attunement` | Attunement gate: equipped-but-un-attuned → no +1; attuning → +1 appears. Restored on teardown. |
| `test_demon_armor_unequip_drops_bonus` | Equip+attune → +1; unequip → `target_ac` back to baseline. Restored on teardown. |

### `test_item_ring_of_spell_turning.py`
v2.299.0 — Ring of Spell Turning (RAW DMG p.193, legendary, attunement): advantage on saving throws against any spell that targets only you, via the v2.297.0 `spell_save_advantage` roll effect (third carrier after the Scarab + Robe of the Archmagi; the nat-20 spell-reflection clause is GM-narrated). Seeded as inert spare loot (unequipped/unattuned) on Zara Emberfire (Sorcerer, no other spell-save item, so the baseline cleanly proves the source); tests PATCH it equipped+attuned, roll a `vs_spell` save, then restore.

| Test | What it asserts |
|------|-----------------|
| `test_ring_grants_advantage_on_vs_spell_save` | Equipped+attuned via PATCH, battle seeded → `POST /roll` WIS save with `vs_spell: true` → breakdown contains `2d20kh1` and `roll_state_applied == auto_advantage_ring_of_spell_turning`. Restored on teardown. |
| `test_ring_no_advantage_without_vs_spell_flag` | The `vs_spell` gate: same WIS save WITHOUT the flag → straight `1d20`, no `roll_state_applied`. Restored on teardown. |
| `test_ring_requires_attunement` | Equipped-but-unattuned → no `2d20kh1`, no `roll_state_applied` (the attunement gate). Restored on teardown. |
| `test_ring_baseline_has_no_advantage` | Control: inert seed (equipped=False) → `vs_spell` save is straight `1d20`, no advantage (proves it's ring-sourced). |
| `test_ring_exposes_derived_flag` | Equipped+attuned → `GET /sheet-json` `derived.spell_save_advantage` names "Ring of Spell Turning" in `sources`. Restored on teardown. |

### `test_item_robe_of_the_archmagi.py`
v2.298.0 — Robe of the Archmagi (RAW DMG p.193, legendary, attunement): advantage on saving throws against spells via the v2.297.0 `spell_save_advantage` roll effect (second carrier after the Scarab; base AC 15+Dex unarmored + spell DC/attack +2 GM-narrated). Seeded as inert spare loot (unequipped/unattuned) on Thalindra Moonshadow (Wizard, no other spell-save item, so the baseline cleanly proves the source); tests PATCH it equipped+attuned, roll a `vs_spell` save, then restore.

| Test | What it asserts |
|------|-----------------|
| `test_robe_grants_advantage_on_vs_spell_save` | Equipped+attuned via PATCH, battle seeded → `POST /roll` WIS save with `vs_spell: true` → breakdown contains `2d20kh1` and `roll_state_applied == auto_advantage_robe_of_the_archmagi`. Restored on teardown. |
| `test_robe_no_advantage_without_vs_spell_flag` | The `vs_spell` gate: same WIS save WITHOUT the flag → straight `1d20`, no `roll_state_applied`. Restored on teardown. |
| `test_robe_requires_attunement` | Equipped-but-unattuned → no `2d20kh1`, no `roll_state_applied` (the attunement gate). Restored on teardown. |
| `test_robe_baseline_has_no_advantage` | Control: inert seed (equipped=False) → `vs_spell` save is straight `1d20`, no advantage (proves it's robe-sourced). |
| `test_robe_exposes_derived_flag` | Equipped+attuned → `GET /sheet-json` `derived.spell_save_advantage` names "Robe of the Archmagi" in `sources`. Restored on teardown. |

### `test_item_spell_save_advantage_roll.py`
v2.297.0 — spell-save advantage as a live `/roll` effect. Upgrades the v2.236.0 `spell_save_advantage` substrate (Mantle of Spell Resistance, Spellguard Shield) from a descriptive `/sheet-json` flag into a real roll effect: `_roll_item_spell_save_advantage` folds a `2d20kh1` advantage source into the PHB p.173 composition at `/roll` time, gated on the caller passing `vs_spell: true`. Also lands Scarab of Protection (RAW DMG p.199) as inert spare loot on Dame Seraphine Vael. Carriers: Quan Reelstep (Mantle equipped+attuned in seed, no PATCH) + Seraphine (Scarab via PATCH, restored on teardown).

| Test | What it asserts |
|------|-----------------|
| `test_mantle_grants_advantage_on_vs_spell_save` | Quan (Mantle equipped+attuned in seed), battle seeded → `POST /roll` WIS save with `vs_spell: true` → breakdown contains `2d20kh1` and `roll_state_applied == auto_advantage_mantle_of_spell_resistance`. |
| `test_mantle_no_advantage_without_vs_spell_flag` | The `vs_spell` gate: same WIS save WITHOUT the flag → straight `1d20`, no `roll_state_applied` (a plain save, e.g. vs grapple, must not pick up the spell-only advantage). |
| `test_scarab_grants_advantage_on_vs_spell_save` | Scarab equipped+attuned via PATCH → `vs_spell` save breakdown contains `2d20kh1` and `roll_state_applied == auto_advantage_scarab_of_protection`. Restored on teardown. |
| `test_scarab_requires_attunement` | Scarab equipped-but-unattuned → no `2d20kh1`, no `roll_state_applied` (the attunement gate). Restored on teardown. |
| `test_scarab_baseline_has_no_advantage` | Control: inert seed (equipped=False) → `vs_spell` save is straight `1d20`, no advantage (proves it's scarab-sourced). |
| `test_scarab_exposes_derived_flag` | Equipped+attuned → `GET /sheet-json` `derived.spell_save_advantage` names "Scarab of Protection" in `sources` (the v2.236.0 descriptive mirror). Restored on teardown. |

### `test_item_robe_of_eyes.py`
v2.295.0 — Robe of Eyes (RAW DMG p.193, rare, attunement): advantage on sight-based Wisdom (Perception) checks via the v2.253.0 `check_advantage_on` substrate, the first 3-field composite (also carries `sees_in_darkness` + `darkvision_ft: 120`, the Belt of Dwarvenkind shape). Seeded as inert spare loot (unequipped/unattuned) on Tavik Stormcrown (Cleric, no other perception-advantage item, so the baseline cleanly proves the source); tests PATCH it equipped+attuned, roll a Perception check, then restore.

| Test | What it asserts |
|------|-----------------|
| `test_robe_grants_perception_advantage` | Equipped+attuned via PATCH, battle seeded → `POST /roll` (WIS Perception) breakdown contains `2d20kh1` and `roll_state_applied == auto_advantage_robe_of_eyes`. Restored on teardown. |
| `test_robe_requires_attunement` | Equipped-but-unattuned → no `2d20kh1`, no `roll_state_applied` (the attunement gate). Restored on teardown. |
| `test_robe_baseline_has_no_advantage` | Control: inert seed (equipped=False) → straight `1d20`, no advantage (proves it's robe-sourced). |
| `test_robe_exposes_derived_flag` | Equipped+attuned → `GET /sheet-json` `derived.check_advantage_on` has "perception" in `skills` and "Robe of Eyes" in `sources`. Restored on teardown. |

### `test_item_periapt_of_health.py`
v2.233.0 — Periapt of Health (RAW DMG p.184, uncommon, no attunement): immunity to contracting disease while worn. Reuses the boolean-OR passive substrate (Sustenance / Awareness): the `disease_immune` flag rides the `periapt-of-health` catalog payload, aggregates in `_equipped_item_effects`, and surfaces on `/sheet-json` as `derived.disease_immune = {sources}`. Brother Tavik Stonebrow (Cleric Lv 8) wears it — no attunement, so it composes with his three attuned items without exceeding the RAW cap.

| Test | What it asserts |
|------|-----------------|
| `test_periapt_exposes_disease_immune_on_sheet_json` | `GET /sheet-json` → `derived.disease_immune` present with "Periapt of Health" in `sources`. |
| `test_periapt_coexists_with_attuned_items` | The flag and the Amulet of Health override compose: `derived.disease_immune` set AND `derived.effective_abilities.CON.effective` = 19. |
| `test_periapt_unequip_drops_flag` | PATCH the periapt to `equipped: False` → `derived.disease_immune` absent; restores the original inventory on teardown. |

### `test_item_ioun_stone_mastery.py`
v2.232.0 — Ioun Stone of Mastery (RAW DMG p.176, legendary, attunement): the last common SRD Ioun variant on the shared `ioun-stone` slug and the first to carry a real mechanical effect (a +1 proficiency-bonus override) rather than a passive flag. The +1 rides the inventory item via `_proficiency_bonus: 1`, sums in `_equipped_item_effects` (new `proficiency_bonus` field), surfaces on `/sheet-json` as `derived.proficiency_bonus = {base, effective, bonus, sources}`, and is appended to proficient saving throws in `/roll` (gated on `sheet["saving_throws"][ability]`). Quan Reelstep (Drunken Master Monk Lv 5) wears it as his 2nd attuned item — STR+DEX save proficient (PB 3→4), belt boosts only CON, so DEX/STR saves read the +1 unconfounded.

| Test | What it asserts |
|------|-----------------|
| `test_mastery_exposes_proficiency_bonus_on_sheet_json` | `GET /sheet-json` → `derived.proficiency_bonus` = `{base 3, effective 4, bonus 1}` with "Ioun Stone of Mastery" in `sources`. |
| `test_mastery_adds_to_proficient_save_roll` | `POST /roll` with `stat_key: "dex_save"` (proficient) → breakdown contains "Ioun Stone of Mastery" and "+1". |
| `test_mastery_skips_non_proficient_save` | `POST /roll` with `stat_key: "con_save"` (NOT proficient) → breakdown does NOT contain "Ioun Stone of Mastery" (the gate holds). |

### `test_item_ioun_stone_awareness.py`
v2.231.0 — Ioun Stone of Awareness (RAW DMG p.176, rare, attunement): the fourth non-ability Ioun variant on the shared `ioun-stone` slug and the first to surface an awareness passive. The can't-be-surprised flag rides the inventory item via `_cannot_be_surprised: True` (no ability payload), aggregates in `_equipped_item_effects` (boolean OR into `cannot_be_surprised`), and surfaces on `/sheet-json` as `derived.cannot_be_surprised = {sources}`. Krieger Stonefist (Barbarian) wears it as his 2nd attuned item and second ioun stone — the flag and the WIS bonus compose on one slug via distinct per-item riders.

| Test | What it asserts |
|------|-----------------|
| `test_awareness_exposes_cannot_be_surprised_on_sheet_json` | `GET /sheet-json` → `derived.cannot_be_surprised` present with "Ioun Stone of Awareness" in `sources`. |
| `test_awareness_coexists_with_brooch_resistance` (v2.249.0; was `test_awareness_coexists_with_wisdom_ioun`) | Krieger's attuned items compose: `derived.cannot_be_surprised` set AND `derived.resistances.types` contains "force" (the Brooch of Shielding). Repointed in v2.249.0 — the Ioun Stone of Wisdom was detuned to free the slot for the brooch, so the old WIS-effective assertion no longer applies. |
| `test_awareness_unequip_drops_flag` | PATCH the Awareness stone to `equipped: False` → `derived.cannot_be_surprised` absent; restores the original inventory on teardown. |

### `test_item_ioun_stone_sustenance.py`
v2.230.0 — Ioun Stone of Sustenance (RAW DMG p.176, rare, attunement): the third non-ability Ioun variant on the shared `ioun-stone` slug and the first to surface a sustenance passive. The no-eat/no-drink flag rides the inventory item via `_no_food_or_drink: True` (no ability payload), aggregates in `_equipped_item_effects` (boolean OR into `no_food_or_drink`), and surfaces on `/sheet-json` as `derived.no_food_or_drink = {sources}`. Rowan Quickbow (Ranger) wears it as an attuned ioun stone; v2.247.0 detuned his Ioun Stone of Charisma to free a slot for the Boots of the Winterlands, so the coexistence test now proves the sustenance flag composes with the STR override from his still-attuned Gauntlets of Ogre Power — distinct per-item riders surfacing together in `derived`.

| Test | What it asserts |
|------|-----------------|
| `test_sustenance_exposes_no_food_or_drink_on_sheet_json` | `GET /sheet-json` → `derived.no_food_or_drink` present with "Ioun Stone of Sustenance" in `sources`. |
| `test_sustenance_coexists_with_gauntlets_str` | Rowan's distinct riders compose: `derived.no_food_or_drink` set AND `derived.effective_abilities.STR.effective` = 19 (the Gauntlets of Ogre Power `ability_set`). |
| `test_sustenance_unequip_drops_flag` | PATCH the Sustenance stone to `equipped: False` → `derived.no_food_or_drink` absent; restores the original inventory on teardown. |

### `test_item_ioun_stone_reserve.py`
v2.229.0 — Ioun Stone of Reserve (RAW DMG p.176, rare, attunement): the second non-ability Ioun variant on the shared `ioun-stone` slug and the first item to surface a stored-spell capacity. The 3-level buffer rides the inventory item via `_spell_reserve_levels: 3` (no ability payload), aggregates in `_equipped_item_effects` (new `spell_reserve_levels` sum), and surfaces on `/sheet-json` as `derived.spell_reserve = {levels, sources}`. The cast-into/cast-from mechanic is descriptive-only in v1. Sir Caelan Lightbringer (Paladin half-caster) wears it as his 3rd attuned item and second ioun stone — proving two stones compose on one slug via distinct per-item riders.

| Test | What it asserts |
|------|-----------------|
| `test_reserve_exposes_spell_reserve_on_sheet_json` | `GET /sheet-json` → `derived.spell_reserve.levels == 3` with "Ioun Stone of Reserve" in `sources`. |
| `test_reserve_coexists_with_dexterity_ioun` | Both of Caelan's ioun stones compose: `derived.spell_reserve.levels == 3` AND `derived.effective_abilities.DEX` = `{base 10, effective 12}` (the second stone's `_ability_bonus`). |
| `test_reserve_unequip_drops_capacity` | PATCH the Reserve stone to `equipped: False` → `derived.spell_reserve` absent; restores the original inventory on teardown. |

### `test_item_ring_of_protection.py`
v2.158.76 magic-items-automation Phase 1b — second catalog entry. Same +1 AC / +1 saves shape as the Cloak (RAW DMG p.191) on a different slot (finger vs neck), validating that the v2.158.74 catalog scales additively. Tavik Stonebrow (Cleric Lv 8, AC 18, WIS save +6) is the canary because his base AC + save mod are clean integers and he's a different PC from Thalindra so the AC + save assertions don't interact.

| Test | What it asserts |
|------|-----------------|
| `test_ring_of_protection_grants_ac_bonus` | Krieger swings at Tavik → `target_ac == 19` (18 base + Ring +1). |
| `test_ring_of_protection_grants_save_bonus` | `/roll` `wis_save` for Tavik (`1d20+6`) → breakdown contains "Ring of Protection" + "+1"; expression rewritten to `1d20+6+1` server-side. |

### `test_item_bracers_of_defense.py`
v2.158.77 magic-items-automation Phase 1c — third catalog entry + closes the plan's Phase 1. Different shape: +2 AC, no save_bonus, RAW no-armor + no-shield gate. New `_pc_is_wearing_shield` helper (mirror of v2.99.95 `_pc_is_wearing_armor`) + per-payload `requires_no_armor` + `requires_no_shield` gate checks in `_equipped_item_effects`. Kael Brightleaf (Monk Way of the Open Hand Lv 7, Unarmored Defense base AC 16, no equipped armor/shield) is the canary because both gates pass for his build.

| Test | What it asserts |
|------|-----------------|
| `test_bracers_of_defense_grants_ac_bonus` | Krieger swings at Kael → `target_ac == 18` (16 base + Bracers +2). |
| `test_bracers_grant_no_save_bonus` | `/roll` `dex_save` for Kael (`1d20+7`) → breakdown does NOT contain "Bracers of Defense". Shape guard: Bracers grant ONLY AC; the per-payload key shape (no `save_bonus`) must not leak into the save hook. |

### `test_item_passive_stacking.py`
v2.158.78 magic-items-automation Phase 1d — same-shape stacking validation. Pip Quickfingers (Rogue Lv 7, base AC 14) wears both an equipped+attuned Cloak of Protection (neck slot) AND Ring of Protection (finger slot) in her demo seed; RAW lets both stack for cumulative +2 AC / +2 saves. Closes Phase 1 of the magic-items plan: catalog scales additively (v2.158.74), per-payload gates work (v2.158.77), and now the accumulator handles same-shape multiplicity without dedup.

| Test | What it asserts |
|------|-----------------|
| `test_cloak_and_ring_stack_ac_bonus` | Krieger swings at Pip → `target_ac == 16` (14 base + 1 Cloak + 1 Ring). Proves walker sums `ac_bonus` across matched items. |
| `test_cloak_and_ring_stack_save_bonus` | `/roll` `dex_save` for Pip (`1d20+6`) → breakdown contains BOTH "Cloak of Protection" AND "Ring of Protection" + "+2" total. Proves sources list aggregates + accumulator sums save_bonus. |

### `test_attune_item.py`
v2.158.79 magic-items-automation Phase 2 — `POST /api/campaign/{cid}/character/{char_id}/attune` endpoint that toggles the `attuned` flag on an inventory item with server-side enforcement of the RAW DMG p.138 3-item attunement cap. The Phase 1 catalog walker already gated payloads on `attuned`; Phase 2 is the player/GM-facing surface that flips it. Phase 2b will surface this as a sheet UI checkbox.

| Test | What it asserts |
|------|-----------------|
| `test_attune_toggle_off_drops_ac` | Toggle Pip's Cloak attunement off → `target_ac == 15` (Ring still gives +1). Proves the catalog walker re-reads the `attuned` flag at attack-time. |
| `test_attune_cap_blocks_fourth` | Pip seeds at the 3/3 cap (Cloak + Ring + Sword of Sharpness, v2.158.103); detune the Sharpness → 2/3, attune Shortsword (3rd) → 200; attune Dagger (4th) → 409 with `error: attunement_cap`, `max_attuned: 3`, `current_attuned: 3`. (v2.243.1 fix: previously assumed a 2/3 seed.) |
| `test_attune_toggle_existing_no_spurious_409` | Detune Pip's seed Sharpness → 2/3, push to exactly 3 (Cloak + Ring + Shortsword); re-setting `attuned=True` on an already-attuned item at the cap returns 200. Cap counts OTHER attuned items so target index is excluded — prevents spurious 409 on sheet re-saves. (v2.243.1 fix.) |
| `test_attune_missing_fields_400` | Empty body → 400. |
| `test_attune_unknown_char_404` | Unknown char_id → 404. |
| `test_attune_index_out_of_range_400` | `inventory_index: 999` past end → 400. |

### `test_use_item_action_pearl.py`
v2.158.82 magic-items-automation Phase 3 — the `POST /api/campaign/{cid}/character/{char_id}/use_item_action` endpoint with the Pearl of Power dispatch. New `_MAGIC_ITEM_ACTIONS` catalog in `app/routes/tabletop_routes.py` maps `pearl-of-power` to the `restore-slot` action; the endpoint validates attunement + equipped + the `pearl-of-power` resource row, then decrements the resource + the matching expended spell slot. Thalindra (Wizard Lv 7) gets a permanent equipped + attuned Pearl in her seed + the `pearl-of-power` resource row (max 1, reset long).

| Test | What it asserts |
|------|-----------------|
| `test_use_pearl_restores_expended_slot` | Pre-expend Thalindra's Lv 2 slot via /sheet-fields; invoke Pearl → response carries `slot_restored.used == 0` + `resource.current == 0`. |
| `test_use_pearl_out_of_uses_409` | After first use depletes the pearl resource, re-expending a Lv 2 slot + invoking again → 409 `out_of_uses`. |
| `test_use_pearl_slot_level_over_cap_400` | RAW cap: requesting `slot_level: 4` → 400 (Pearl restores ≤ Lv 3). |
| `test_use_pearl_no_expended_slot_409` | After long rest (all slots full), invoking Pearl → 409 `no_expended_slot`. |
| `test_use_pearl_unknown_action_404` | `action_key: "fireball"` on a Pearl → 404. |
| `test_use_item_action_missing_fields_400` | Empty body → 400. |

### `test_use_item_action_wand.py`
v2.158.84 magic-items-automation Phase 4a — Wand of Magic Missiles (RAW DMG p.213) through the same `/use_item_action` endpoint. Different shape from Pearl: multi-charge spend per use (1-7 charges → Lv 1-7 Magic Missile cast). Endpoint dispatch refactored: a per-slug handler function (`_use_item_action_wand_of_magic_missiles`) is called based on item `_slug`. Wand doesn't require attunement (uncommon RAW); Thalindra carries an equipped (not attuned) Wand + a `wand-of-magic-missiles` resource row (current 7, max 7, reset long). The dice-expression recharge (`1d6+1` on long rest) ships in Phase 4b; for now reset=long fully refills.

| Test | What it asserts |
|------|-----------------|
| `test_use_wand_single_charge` | Spending 1 charge → `charges_spent: 1`, `cast_slot_level: 1`, resource 7→6. |
| `test_use_wand_multi_charge` | Spending 3 charges → `cast_slot_level: 3`, resource 7→4. |
| `test_use_wand_over_max_charges_400` | Requesting 8 charges (over RAW max of 7) → 400. |
| `test_use_wand_insufficient_charges_409` | Burn 6 charges (resource at 1); request 2 → 409 `insufficient_charges` with `current: 1, requested: 2`. |
| `test_use_wand_unknown_action_404` | Pearl action_key `restore-slot` on a Wand → 404 (catalog mismatch). |

### `test_wand_recharge.py`
v2.158.86 magic-items-automation Phase 4b — dice-expression recharge on long rest. The rest loop's resource-refill path now reads an optional `charge_recovery` field (a dice expression like `"1d6+1"`) on each resource row + rolls it on long rest, adding to current capped at max, instead of the standard full refill. Wand of Magic Missiles' resource row carries `charge_recovery: "1d6+1"` (RAW DMG p.213); Pearl of Power has no `charge_recovery` and falls back to full refill (the regression-protection canary).

| Test | What it asserts |
|------|-----------------|
| `test_wand_dice_recharge_within_raw_range` | Burn wand to 0 → long rest → current must be in 2..7 (RAW 1d6+1 range). Iterates 5 times to detect a parser regression vs. dice-fluke OOB. |
| `test_pearl_still_full_refills_on_long_rest` | Regression: items without a `charge_recovery` field must still full-refill (Pearl's `current: 0 → 1`). Catches accidental walker behavior change. |

### `test_use_item_action_fireball_wand.py`
v2.158.87 magic-items-automation Phase 4c — Wand of Fireballs through the same `/use_item_action` endpoint as the Wand of Magic Missiles, via the generalized `_use_item_action_charge_wand` handler. Catalog entry sets `base_slot_level: 3` so cast slot level = 3 + (charges - 1); spell_slug is `fireball`. RAW DMG p.212 (rare → attunement required). Thalindra is now at the RAW DMG p.138 cap of 3 attuned items: Cloak (Phase 1a), Pearl (Phase 3), Wand of Fireballs (Phase 4c).

| Test | What it asserts |
|------|-----------------|
| `test_fireball_wand_single_charge_casts_lv3` | 1 charge → `cast_slot_level: 3` (base=3 + 0). |
| `test_fireball_wand_multi_charge_casts_higher` | 3 charges → `cast_slot_level: 5` (base=3 + 2). |
| `test_fireball_wand_requires_attunement_409` | Detune the wand via /attune; invoke /use_item_action → 409 attunement required. Restores attunement in teardown. |

### `test_use_item_action_lightning_wand.py`
v2.205.0 magic-items-automation content tail — Wand of Lightning Bolts (RAW DMG p.213, rare, attunement) through the same `/use_item_action` endpoint + generalized `_use_item_action_charge_wand` handler. Identical template to the Fireballs wand (`base_slot_level: 3`, 1d6+1 recharge); `spell_slug: lightning-bolt`. Seeded on **Garrik** (not Thalindra, who's at the 3-attunement cap) — his first attuned item; the wand index is looked up by `_slug`. Same commit generalized the handler's broadcast summary to derive the spell name from `spell_slug` (was hardcoded "Magic Missile").

| Test | What it asserts |
|------|-----------------|
| `test_lightning_wand_single_charge_casts_lv3` | 1 charge → `cast_slot_level: 3` (base=3 + 0); `spell_slug: lightning-bolt`, `item_name: Wand of Lightning Bolts`. |
| `test_lightning_wand_multi_charge_casts_higher` | 3 charges → `cast_slot_level: 5` (base=3 + 2). |
| `test_lightning_wand_requires_attunement_409` | Detune the wand via /attune; invoke /use_item_action → 409 attunement required. Restores attunement in teardown. |

### `test_use_item_action_web_wand.py`
v2.263.0 charged-items Phase 1 — Wand of Web (RAW DMG p.213, rare, attunement) through the same `/use_item_action` endpoint + generalized `_use_item_action_charge_wand` handler. RAW gives no upcast, so the catalog sets `min_charges == max_charges == 1`, `base_slot_level: 2` (Web's own level), `spell_slug: web`. Seeded on **Thalindra** (Wizard — Web is a wizard spell; her 4th attuned item, seed-load bypasses the 3-item cap); the wand index is looked up by `_slug`. The attunement guard detunes via **PATCH sheet-fields** (cap-bypassing) rather than /attune so the teardown restore can't trip the cap.

| Test | What it asserts |
|------|-----------------|
| `test_web_wand_single_charge_casts_lv2` | 1 charge → `cast_slot_level: 2` (base=2 + 0); `spell_slug: web`, `item_name: Wand of Web`, `charges_spent: 1`. |
| `test_web_wand_rejects_two_charges_400` | charges=2 is outside the `[1, 1]` band → 400 (RAW Web is a fixed single-charge spend). |
| `test_web_wand_requires_attunement_409` | Detune the wand via PATCH sheet-fields; invoke /use_item_action → 409 attunement required. Restores inventory in teardown. |

### `test_use_item_action_polymorph_wand.py`
v2.264.0 charged-items Phase 1 — Wand of Polymorph (RAW DMG p.212, rare, attunement) through the same `/use_item_action` endpoint + generalized `_use_item_action_charge_wand` handler. Same single-charge drop-in shape as the Wand of Web: RAW gives no upcast, so the catalog sets `min_charges == max_charges == 1`, `base_slot_level: 4` (Polymorph's own level), `spell_slug: polymorph`. Seeded on **Zara Emberfire** (Sorcerer — Polymorph is on the Sorcerer list; her 4th attuned item, seed-load bypasses the 3-item cap); the wand index is looked up by `_slug`. The attunement guard detunes via **PATCH sheet-fields** (cap-bypassing) rather than /attune so the teardown restore can't trip the cap.

| Test | What it asserts |
|------|-----------------|
| `test_polymorph_wand_single_charge_casts_lv4` | 1 charge → `cast_slot_level: 4` (base=4 + 0); `spell_slug: polymorph`, `item_name: Wand of Polymorph`, `charges_spent: 1`. |
| `test_polymorph_wand_rejects_two_charges_400` | charges=2 is outside the `[1, 1]` band → 400 (RAW Polymorph is a fixed single-charge spend). |
| `test_polymorph_wand_requires_attunement_409` | Detune the wand via PATCH sheet-fields; invoke /use_item_action → 409 attunement required. Restores inventory in teardown. |

### `test_use_item_action_binding_wand.py`
v2.266.0 charged-items Phase 1 — Wand of Binding (RAW DMG p.211, rare, attunement) through the same `/use_item_action` endpoint + generalized `_use_item_action_charge_wand` handler. Same single-charge drop-in shape as the Wand of Web/Polymorph: RAW gives no upcast on the wand, so the catalog sets `min_charges == max_charges == 1`, `base_slot_level: 2` (Hold Person's own level), `spell_slug: hold-person`. (RAW also casts Hold Monster for 5 charges; that spell isn't yet catalogued, so v1 ships Hold Person only.) Seeded on **Brother Tavik Stonebrow** (Cleric — Hold Person is on his prepared list; his 4th attuned item, seed-load bypasses the 3-item cap); the wand index is looked up by `_slug`. The attunement guard detunes via **PATCH sheet-fields** (cap-bypassing) rather than /attune so the teardown restore can't trip the cap.

| Test | What it asserts |
|------|-----------------|
| `test_binding_wand_single_charge_casts_lv2` | 1 charge → `cast_slot_level: 2` (base=2 + 0); `spell_slug: hold-person`, `item_name: Wand of Binding`, `charges_spent: 1`. |
| `test_binding_wand_rejects_two_charges_400` | charges=2 is outside the `[1, 1]` band → 400 (RAW Hold Person via the wand is a fixed single-charge spend). |
| `test_binding_wand_requires_attunement_409` | Detune the wand via PATCH sheet-fields; invoke /use_item_action → 409 attunement required. Restores inventory in teardown. |

### `test_item_wand_of_the_war_mage.py`
v2.265.0 charged-items Phase 5 — Wand of the War Mage, +1/+2/+3 (RAW DMG p.211, uncommon–rare/very-rare, attunement). A passive (no charges) spell-attack-bonus rider on `_MAGIC_ITEM_PASSIVES` (a clone of Bracers of Archery): a summed, attunement-gated `spell_attack_bonus` int in `_equipped_item_effects` surfaced on `/sheet-json` as `derived.spell_attack_bonus = {bonus, sources}` and folded into the caster's spell attack roll at cast-resolution time. The single SRD slug defaults to +1; the +2/+3 tiers ride a per-item `_spell_attack_bonus` rider. Seeded on **Magnus** (Fiend Warlock — Eldritch Blast at +2; his 5th attuned item, seed-load bypasses the 3-item cap) and, since v2.276.0, the **+3** very-rare tier on **Zara Emberfire** (Draconic Sorcerer — Fire Bolt at +3, a clean read with no other spell-attack item). The wand index is looked up by `_slug`; the attunement guard detunes via **PATCH sheet-fields** (cap-bypassing).

| Test | What it asserts |
|------|-----------------|
| `test_war_mage_exposes_derived` | `/sheet-json derived.spell_attack_bonus` is `{bonus: 2, sources: [...War Mage...]}`. |
| `test_war_mage_detune_drops_derived` | Un-attuning the wand (still equipped) removes `derived.spell_attack_bonus` — the attunement gate. Restores inventory in teardown. |
| `test_war_mage_unequip_drops_derived` | Unequipping the wand removes `derived.spell_attack_bonus`. Restores inventory in teardown. |
| `test_war_mage_adds_spell_attack_to_hit` | An Eldritch Blast attack roll carries +2 more flat to-hit modifier attuned vs detuned (delta == 2). Restores inventory in teardown. |
| `test_war_mage_plus_three_exposes_derived` | Zara's `/sheet-json derived.spell_attack_bonus` is a clean `{bonus: 3, sources: [...War Mage...]}` (the very-rare +3 tier; no other spell-attack item confounds the read). |
| `test_war_mage_plus_three_adds_spell_attack_to_hit` | Zara's Fire Bolt attack roll carries +3 more flat to-hit modifier attuned vs detuned (delta == 3). Restores inventory in teardown. |

### `test_use_item_action_wand_of_paralysis.py`
v2.206.0 magic-items-automation content tail — Wand of Paralysis (RAW DMG p.213, rare, attunement) through the same `/use_item_action` endpoint + the **generalized** `_use_item_action_wand_of_fear` save-condition handler. The handler now reads the condition (key/label/icon/effects), save DC/ability, feature name, duration, and target shape from the catalog `action_def`; the Paralysis entry overrides the Fear defaults with DC 15 CON → Paralyzed, a 60-ft ray, 1-minute duration. Seeded on **Magnus** (his second attuned wand, 2/3 against the cap); the wand index is looked up by `_slug`. The `single-target-save` `ITEM_ACTION_SLUGS` kind renders a `💫 Paralyze` button.

| Test | What it asserts |
|------|-----------------|
| `test_wand_of_paralysis_cast_2_targets` | Cast at 2 NPC targets → 200; `save_dc: 15`, `save_ability: CON`, `charges_spent: 1`, resource 7→6, both target ids in `results`. |
| `test_wand_of_paralysis_over_cap_returns_400` | `charges: 2` when catalog max=1 → 400 (shared min/max charge validator). |
| `test_wand_of_paralysis_empty_returns_409` | Drain the wand to 0 via /sheet-fields; invoke → 409 `insufficient_charges`, `current: 0`. Restores in teardown. |

### `test_vault_stub_loot.py`
v2.342.0 — "The Vault" bulk-stub push: 60 remaining pure-narrative SRD items shipped as catalog-stub passives (one `_MAGIC_ITEM_PASSIVES` row each via a `setdefault` loop) and seeded as inert spare loot across all 15 demo PCs (`_VAULT_STUB_LOOT`). Parametrized by carrier (15 cases): each asserts every seeded Vault slug surfaces on that carrier's `/sheet-json`. Mechanics are GM-narrated; deliberately excludes the mechanically-rich leftovers (Bead of Force, Berserker Axe, etc.).

| Test | What it asserts |
|------|-----------------|
| `test_vault_stub_loot_seeded[<carrier>]` | The named carrier's `/sheet-json` inventory contains every Vault stub slug seeded on them (15 parametrized cases covering all 60 items). |

### `test_bottled_tempest.py`
v2.337.0 — "The Bottled Tempest" bundle (tenth): three SRD sealed-vessel summon/release wondrous items as catalog-stub passives. Smoke tests verify carrier seeds; the Elemental Gem test asserts `consumable: True`.

| Test | What it asserts |
|------|-----------------|
| `test_zara_carries_efreeti_bottle` | Zara carries `efreeti-bottle`, equipped, no attunement. |
| `test_pip_carries_eversmoking_bottle` | Pip carries `eversmoking-bottle`, equipped, no attunement. |
| `test_brakka_carries_elemental_gem` | Brakka carries `elemental-gem`, equipped, no attunement, `consumable: True`. |

### `test_escapists_kit.py`
v2.336.0 — "The Escapist's Kit" bundle (ninth): three SRD escape/evasion wondrous items as catalog-stub passives. Smoke tests verify carrier seeds; the Dust test asserts `consumable: True`.

| Test | What it asserts |
|------|-----------------|
| `test_kael_carries_wind_fan` | Kael carries `wind-fan`, equipped, no attunement. |
| `test_lyra_carries_cape_of_the_mountebank` | Lyra carries `cape-of-the-mountebank`, equipped, no attunement. |
| `test_quan_carries_dust_of_disappearance` | Quan carries `dust-of-disappearance`, equipped, no attunement, `consumable: True`. |

### `test_diviners_hoard.py`
v2.334.0 — "The Diviner's Hoard" bundle (eighth): three SRD divination / planar-travel wondrous items as catalog-stub passives. Crystal Ball + Candle of Invocation require attunement (tests assert `attuned: True`); Cubic Gate doesn't.

| Test | What it asserts |
|------|-----------------|
| `test_lyra_carries_crystal_ball` | Lyra carries `crystal-ball`, equipped, `attuned: True`. |
| `test_thalindra_carries_cubic_gate` | Thalindra carries `cubic-gate`, equipped, no attunement. |
| `test_tavik_carries_candle_of_invocation` | Tavik carries `candle-of-invocation`, equipped, `attuned: True`. |

### `test_artisans_spread.py`
v2.333.0 — "The Artisan's Spread" bundle (seventh): three SRD craft/utility wondrous items as catalog-stub passives. Smoke tests verify carrier seeds.

| Test | What it asserts |
|------|-----------------|
| `test_pip_carries_chime_of_opening` | Pip carries `chime-of-opening`, equipped, no attunement. |
| `test_thalindra_carries_marvelous_pigments` | Thalindra carries `marvelous-pigments`, equipped, no attunement. |
| `test_magnus_carries_robe_of_useful_items` | Magnus carries `robe-of-useful-items`, equipped, no attunement. |

### `test_elemental_conclave.py`
v2.332.0 — "The Elemental Conclave" bundle (sixth, FIRST 4-item bundle): four SRD elemental-control wondrous items shipped as catalog-stub passives — one per element. Smoke tests verify each is seeded on its thematic carrier (one per element) and surfaces via `/sheet-json`. Actual summon + CHA-check-to-command mechanics are GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_caelan_carries_brazier` | Caelan's `/sheet-json` inventory carries `_slug: "brazier-of-commanding-fire-elementals"`, equipped=True, no attunement. |
| `test_rowan_carries_bowl` | Rowan's `/sheet-json` inventory carries `_slug: "bowl-of-commanding-water-elementals"`, equipped=True, no attunement. |
| `test_seraphine_carries_censer` | Seraphine's `/sheet-json` inventory carries `_slug: "censer-of-controlling-air-elementals"`, equipped=True, no attunement. |
| `test_krieger_carries_stone` | Krieger's `/sheet-json` inventory carries `_slug: "stone-of-controlling-earth-elementals"`, equipped=True, no attunement. |

### `test_tricksters_pouch.py`
v2.331.0 — "The Trickster's Pouch" bundle (fifth after Wayfarer's / Inventor's / Captor's / Engineer's): three SRD random-effect wondrous items as catalog-stub passives. The Feather Token test additionally asserts `consumable: True`.

| Test | What it asserts |
|------|-----------------|
| `test_mira_carries_bag_of_beans` | Mira's `/sheet-json` inventory carries `_slug: "bag-of-beans"`, type `magic`, `equipped: True`, no `attuned` flag. |
| `test_brakka_carries_bag_of_tricks` | Brakka's `/sheet-json` inventory carries `_slug: "bag-of-tricks"`, type `magic`, `equipped: True`, no `attuned` flag. |
| `test_quan_carries_feather_token` | Quan's `/sheet-json` inventory carries `_slug: "feather-token"`, type `magic`, `equipped: True`, `consumable: True` (RAW one-shot), no `attuned` flag. |

### `test_engineers_set.py`
v2.330.0 — "The Engineer's Set" bundle (fourth after Wayfarer's / Inventor's / Captor's): three mechanical-contraption SRD wondrous items shipped as catalog-stub passives. Cube of Force is the first stub bundle item to declare `requires_attunement: True` (descriptive in v1; the test asserts `attuned: True` on the seed entry).

| Test | What it asserts |
|------|-----------------|
| `test_kael_carries_apparatus_of_the_crab` | Kael's `/sheet-json` inventory carries `_slug: "apparatus-of-the-crab"`, type `magic`, `equipped: True`, no `attuned` flag. |
| `test_zara_carries_cube_of_force` | Zara's `/sheet-json` inventory carries `_slug: "cube-of-force"`, type `magic`, `equipped: True`, AND `attuned: True` (the first stub item to require attunement). |
| `test_lyra_carries_portable_hole` | Lyra's `/sheet-json` inventory carries `_slug: "portable-hole"`, type `magic`, `equipped: True`, no `attuned` flag. |

### `test_captors_cache.py`
v2.329.0 — "The Captor's Cache" bundle (third after v2.327.0 Wayfarer's Trio + v2.328.0 Inventor's Trio): three SRD capture/trap wondrous items shipped as pure catalog-stub passives. Smoke tests verify each is seeded on its thematic carrier and surfaces via `/sheet-json`. Actual mechanics (thrown restraining sphere, WIS-save creature-trapping flask, CHA-save life-trapping mirror) are GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_krieger_carries_iron_bands_of_binding` | Krieger's `/sheet-json` inventory carries `_slug: "iron-bands-of-binding"`, type `magic`, `equipped: True`, no `attuned` flag. |
| `test_magnus_carries_iron_flask` | Magnus's `/sheet-json` inventory carries `_slug: "iron-flask"`, type `magic`, `equipped: True`, no `attuned` flag. |
| `test_mira_carries_mirror_of_life_trapping` | Mira's `/sheet-json` inventory carries `_slug: "mirror-of-life-trapping"`, type `magic`, `equipped: True`, no `attuned` flag. |

### `test_inventors_trio.py`
v2.328.0 — "The Inventor's Trio" bundle (sequel to v2.327.0): three utility-themed SRD wondrous items shipped as pure catalog-stub passives. Smoke tests verify each is seeded on its thematic carrier and surfaces via `/sheet-json`. Actual mechanics (water-output mode-switching, permanent adhesive bond, universal solvent dissolve) are GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_tavik_carries_decanter_of_endless_water` | Tavik's `/sheet-json` inventory carries `_slug: "decanter-of-endless-water"`, type `magic`, `equipped: True`, no `attuned` flag. |
| `test_garrik_carries_sovereign_glue` | Garrik's `/sheet-json` inventory carries `_slug: "sovereign-glue"`, type `magic`, `equipped: True`, no `attuned` flag. |
| `test_thalindra_carries_universal_solvent` | Thalindra's `/sheet-json` inventory carries `_slug: "universal-solvent"`, type `magic`, `equipped: True`, no `attuned` flag. |

### `test_wayfarers_trio.py`
v2.327.0 — "The Wayfarer's Trio" bundle: three SRD wondrous items shipped together as pure catalog-stub passives. Smoke tests verify each is seeded on its thematic carrier and surfaces via `/sheet-json`. Actual mechanics (boat/ship mode-switching, animated 60-ft rope, extradimensional digestion bag) are GM-narrated; this test layer just guards the catalog row + seed against regression.

| Test | What it asserts |
|------|-----------------|
| `test_garrik_carries_folding_boat` | Garrik's `/sheet-json` inventory carries `_slug: "folding-boat"`, type `magic`, no `attuned` flag. |
| `test_pip_carries_rope_of_climbing` | Pip's `/sheet-json` inventory carries `_slug: "rope-of-climbing"`, `equipped: True`, no `attuned` flag. |
| `test_krieger_carries_bag_of_devouring` | Krieger's `/sheet-json` inventory carries `_slug: "bag-of-devouring"`, type `magic`, no `attuned` flag. |

### `test_use_item_action_mace_of_terror.py`
v2.340.0 — Mace of Terror (RAW DMG p.180, rare, attunement). A Wand of Fear clone on the generalized `_use_item_action_wand_of_fear` handler — WIS → frightened, 3 charges (1d4+1 recharge), 30-ft radius. Carrier: Dame Seraphine Vael (equipped, NOT attuned — keeps her under the /attune cap; the use-item path ignores the attuned flag).

| Test | What it asserts |
|------|-----------------|
| `test_mace_of_terror_wave_2_targets` | Wave at 2 NPC targets → 200; `save_dc: 15`, `save_ability: WIS`, `charges_spent: 1`, resource 3→2, both ids in `results`. |
| `test_mace_of_terror_empty_returns_409` | Drain to 0 via /sheet-fields; invoke → 409 `insufficient_charges`, `current: 0`. Restores in teardown. |

### `test_use_item_action_gem_of_brightness.py`
v2.326.0 — Gem of Brightness Mode 2 ("beam"; RAW DMG p.172, uncommon, NO attunement). Pure Wand of Paralysis substrate clone — only the slug, condition_key (`blinded`), and feature label/icon differ. 50 charges, no recharge (RAW: when depleted, becomes a non-magical 50 gp jewel — resource row carries `reset: "none"`). Mode 1 (no-charge bright-light radius) and Mode 3 (5-charge 30-ft cone) are GM-narrated in v1. Seeded on **Lyra Sunstrider** (Bard, no attunement gate) with a 50-charge `gem-of-brightness` resource row.

| Test | What it asserts |
|------|-----------------|
| `test_gem_of_brightness_beam_2_targets` | Beam at 2 NPC targets → 200; `save_dc: 15`, `save_ability: CON`, `charges_spent: 1`, resource 50→49, both target ids in `results`. |
| `test_gem_of_brightness_empty_returns_409` | Drain the gem to 0 via /sheet-fields; invoke → 409 `insufficient_charges`, `current: 0`. Restores in teardown. |
| `test_gem_of_brightness_no_attunement_required` | The seed inventory entry has `equipped: True` and no `attuned: True` flag, matching the RAW no-attunement contract. |

### `test_use_item_action_eyes_of_charming.py`
v2.208.0 magic-items-automation content tail — Eyes of Charming (RAW DMG p.168, uncommon, attunement) through the same `/use_item_action` endpoint + the generalized `_use_item_action_wand_of_fear` save-condition handler. Near drop-in of the Staff of Charming: fixed DC 13 (vs the staff's `"spell"` sentinel), a 3-charge pool, charm person (WIS → Charmed, 30-ft single target, 1-hour). Seeded on **Zara Emberfire** (Draconic Sorcerer, Charlatan — a CHA face with no other attuned items, 1/3 cap); the item index is looked up by `_slug`.

| Test | What it asserts |
|------|-----------------|
| `test_eyes_of_charming_cast_fixed_dc13` | Cast at 1 NPC target → 200; `save_dc: 13` (fixed), `save_ability: WIS`, `charges_spent: 1`, resource 3→2, target id in `results`. |
| `test_eyes_of_charming_over_cap_returns_400` | `charges: 2` when catalog max=1 → 400 (shared min/max charge validator). |
| `test_eyes_of_charming_empty_returns_409` | Drain the lenses to 0 via /sheet-fields; invoke → 409 `insufficient_charges`, `current: 0`. Restores in teardown. |

### `test_use_item_action_staff_of_charming.py`
v2.207.0 magic-items-automation content tail — Staff of Charming (RAW DMG p.201, rare, attunement) through the same `/use_item_action` endpoint + the generalized `_use_item_action_wand_of_fear` save-condition handler. The marquee charge-action casts charm person (WIS → Charmed, 30-ft single target, 1-hour). New wrinkle: the catalog sets `save_dc: "spell"`, a sentinel that makes the handler compute the wielder's spell save DC from the sheet (`_compute_spell_save_dc_from_sheet`) rather than a fixed number. Seeded on **Lyra Sunstrider** (Bard Lv 6, spell save DC 14 — her third attuned item, 3/3 cap); the staff index is looked up by `_slug`.

| Test | What it asserts |
|------|-----------------|
| `test_staff_of_charming_cast_uses_spell_dc` | Cast at 1 NPC target → 200; `save_dc: 14` (Lyra's computed spell save DC via the `"spell"` sentinel), `save_ability: WIS`, `charges_spent: 1`, resource 10→9, target id in `results`. |
| `test_staff_of_charming_over_cap_returns_400` | `charges: 2` when catalog max=1 → 400 (shared min/max charge validator). |
| `test_staff_of_charming_empty_returns_409` | Drain the staff to 0 via /sheet-fields; invoke → 409 `insufficient_charges`, `current: 0`. Restores in teardown. |

### `test_dragon_slayer_rider.py`
v2.158.93 magic-items-automation Phase 5c — Dragon Slayer Longsword (RAW DMG p.166). First conditional rider: the rider catalog entry carries a `condition(target_combatant) → bool` predicate that section 6c invokes after the equip check. Caelan's seed gets the longsword (attack_index 2, inventory_index 7, +1 attack/damage baked in, equipped). v2.243.0: RAW correction — Dragon Slayer needs no attunement, so the rider fires whenever equipped (the demo item dropped its `attuned` flag, freeing Caelan's 3rd slot). Tests use the existing battle-seed pattern (PUT a battle with a synthetic target carrying `creature_type: "dragon"` or `"humanoid"`) to exercise both branches.

| Test | What it asserts |
|------|-----------------|
| `test_dragon_slayer_fires_on_dragon_target` | Attack a `creature_type: "dragon"` combatant → `auto_uplifts` carries `source: "item-dragon-slayer"`, `damage_type: "slashing"` (RAW fallback to weapon type), `expression: "3d6"`, total in [3, 36]. |
| `test_dragon_slayer_silent_on_humanoid` | Attack a `creature_type: "humanoid"` → no `item-dragon-slayer` uplift. The condition predicate gates the rider even with the weapon equipped. |
| `test_dragon_slayer_fires_without_attunement` | v2.243.0 RAW correction (DMG p.166 — no attunement): /attune detune of the longsword → rider STILL fires on a `creature_type: "dragon"` target while equipped (`expression: "3d6"`). Inverts the pre-v2.243.0 attunement-gated assertion. |

### `test_demon_slayer_rider.py`
v2.158.97 magic-items-automation Phase 6a — Demon Slayer Rapier (RAW DMG p.166). Second conditional rider after Dragon Slayer (v2.158.93) using the same Phase 5c+5f substrate: condition predicate keys on `creature_type == "fiend"`, dice are 2d6 (vs. Dragon Slayer's 3d6). Lyra Sunstrider gets the rapier (attack_index 3, inventory_index 7, equipped + attuned, +1 attack/damage RAW baked in). Frighten-on-hit DC 15 WIS save deferred — that's a separate save-handler hook.

| Test | What it asserts |
|------|-----------------|
| `test_demon_slayer_fires_on_fiend_target` | Attack a `creature_type: "fiend"` combatant → `auto_uplifts` carries `source: "item-demon-slayer"`, `damage_type: "piercing"` (RAW fallback to weapon type), `expression: "2d6"`, total in [2, 24] (crit-doubled cap). |
| `test_demon_slayer_silent_on_humanoid` | Attack a `creature_type: "humanoid"` → no `item-demon-slayer` uplift. |
| `test_demon_slayer_suppressed_when_detuned` | /attune detune → no rider even vs. fiends. Restores attunement in teardown. |

### `test_battle_sphere_cone_targets.py`
v2.159.5 magic-items-automation Phase 8e — server-side sphere + cone AoE geometry. Two new endpoints: `/battle/sphere-targets` (center + radius_ft) and `/battle/cone-targets` (apex + direction + length_ft + half-angle). Same Token-position read pattern as the Phase 8d line endpoint. Used by Fireball / Burning Hands / Cone of Cold UIs to pre-fill target lists.

| Test | What it asserts |
|------|-----------------|
| `test_sphere_includes_within_radius` | Sphere(A, 20 ft) with B at 10 ft east → B in results. |
| `test_sphere_excludes_beyond_radius` | Sphere(A, 20 ft) with C at 50 ft east → C NOT in results. |
| `test_sphere_excludes_center_combatant` | Center combatant A excluded from its own sphere's results. |
| `test_cone_includes_combatant_in_angular_span` | Cone(A → B, 60 ft) with D at 90° off-axis (30 ft south) → D NOT in results (outside 26.57° half-angle). |
| `test_cone_excludes_beyond_length` | Cone(A → B, 20 ft) with C at 50 ft east → C NOT in results (past length). |
| `test_cone_excludes_apex_and_direction` | A (apex) + B (direction) both excluded from cone results. |

### `test_battle_line_targets.py`
v2.159.4 magic-items-automation Phase 8d — server-side line-AoE geometry. POST /api/campaign/{cid}/battle/line-targets takes caster + target combatant ids + width_ft + max_length_ft, returns combatants within the band. Used by Javelin of Lightning client + future Lightning Bolt UIs. Uses /token/{id}/move to position 4 combatants in a controlled layout; teardown moves them to (200, 200).

| Test | What it asserts |
|------|-----------------|
| `test_line_targets_includes_on_line_combatant` | C placed at the midpoint of A→B segment → appears in results. |
| `test_line_targets_excludes_off_line_combatant` | D placed 20 ft perpendicular from the line → NOT in results (width_ft=5 means 2.5-ft half-band). |
| `test_line_targets_excludes_caster_and_target` | A + B are endpoints of the segment but still excluded from results (RAW "excluding you and the target"). |

### `test_javelin_of_lightning.py`
v2.159.3 magic-items-automation Phase 8c — Javelin of Lightning (RAW DMG p.178). First line-AoE item: fires via `/use_item_action` with `action_key="hurl-lightning"` + a `target_combatant_ids` list. Each target rolls DC 13 DEX save → 4d6 lightning (half on pass) via `_resolve_feature_save`. Item flips to `_used_today: True` after firing; long-rest path clears the flag. Krieger Stonefist gets the javelin (inventory_index 5).

| Test | What it asserts |
|------|-----------------|
| `test_javelin_lightning_hurl_two_targets` | Hurl with 2 synthetic targets → 200 with `results` carrying both ids, `spent_until_dawn: True`; sheet's inventory item shows `_used_today: True`. |
| `test_javelin_lightning_double_use_409` | First hurl 200; second hurl → 409 `error: "spent_until_dawn"`. |
| `test_javelin_lightning_long_rest_resets` | After first hurl + long rest, second hurl returns 200 (flag was cleared). |

### `test_wand_of_fear.py`
v2.159.11 magic-items-automation Phase 8k — Wand of Fear (RAW DMG p.213, rare + attunement). First cone-AoE magic item via `/use_item_action`. 7 charges (regain 1d6+1 at dawn — v2.158.86 dice-expression recharge); spend 1 to project a 30-ft cone, DC 15 WIS save or Frightened of caster for 1 minute (repeat save end-of-turn). No damage — the rider is the `frightened` `condition_buff` passed through `_resolve_feature_save` (same path Conquering Presence uses). Magnus Hexbinder (Warlock Lv 5) carries it at inventory_index 7.

| Test | What it asserts |
|------|-----------------|
| `test_wand_of_fear_cast_2_targets` | Cast at 2 NPC targets → 200 with `save_dc: 15`, `save_ability: "WIS"`, `charges_spent: 1`, `resource.current: 6` (7→6), `results` carries both target ids. |
| `test_wand_of_fear_over_cap_returns_400` | POST with `charges: 2` when `max_charges=1` → 400 (the same min/max validator the necklace upcast picker uses). |
| `test_wand_of_fear_empty_returns_409` | Drain the wand to 0 charges via `/sheet-fields` PATCH, then cast → 409 with `error: "insufficient_charges"` + `current: 0`. Teardown restores the snapshot. |

### `test_necklace_of_fireballs.py`
v2.159.9 magic-items-automation Phase 8i — Necklace of Fireballs (RAW DMG p.183). First sphere-AoE magic item via `/use_item_action`. Each bead is a 3rd-level Fireball (8d6 fire, DC 15 DEX save half, 20-ft sphere). Handler decrements a `necklace-of-fireballs` resource row (current 6 / max 6 / reset='none' — beads don't regenerate RAW); returns 409 `insufficient_charges` when bead count = 0. Thalindra Moonwhisper carries it at inventory_index 11. v2.159.10 Phase 8j: multi-bead upcast — `body.charges` 1-6 spends N beads for `(7+N)d6` fire damage (1 bead = Lv 3 Fireball; 6 beads = Lv 8 upcast / 13d6).

| Test | What it asserts |
|------|-----------------|
| `test_necklace_throw_bead_2_targets` | v2.159.9 single-bead happy path. Throw at 2 targets → 200 with `save_dc: 15`, `save_ability: "DEX"`, `resource.current: 5` (6→5), `results` carries both target ids. |
| `test_necklace_3_bead_upcast` | v2.159.10 Phase 8j: POST with `charges: 3` → 200, `charges_spent: 3`, `dice: "10d6"`, resource current drops 6→3 (steps by N, not 1). |
| `test_necklace_over_cap_returns_400` | v2.159.10: POST with `charges: 7` when `max_charges=6` → 400 (out-of-range validation in the handler). |
| `test_necklace_empty_returns_409` | Drain the necklace to 0 beads via `/sheet-fields` PATCH, then throw → 409 with `error: "insufficient_charges"` + `current: 0`. Teardown restores the snapshot. |

### `test_use_item_action_staff_of_fire.py`
v2.210.0 magic-items — Staff of Fire (RAW DMG p.202, very rare, attunement). The Necklace of Fireballs handler is generalized into a content-agnostic save-for-half AoE-damage handler: it takes a `slug`, honours the `"spell"` save-DC sentinel (resolved from the wielder's sheet), defaults the charge spend to the action's `min_charges` when `charges` is omitted, and reads its feature label from `action_def`. The Staff's marquee Fireball action (8d6 fire, 20-ft sphere, DEX save, fixed 3-charge spend) routes through it. Zara Emberfire (Tiefling Sorcerer Lv 5, spell save DC 14) carries an equipped+attuned Staff of Fire + a `staff-of-fire` resource row (10/10). The Fixture force-reseeds the charges to 10 and snapshots for teardown.

| Test | What it asserts |
|------|-----------------|
| `test_staff_of_fire_fireball_2_targets` | Cast Fireball at 2 targets with no `charges` param → 200 with `save_dc: 14` (Zara's spell save DC via the `"spell"` sentinel), `save_ability: "DEX"`, `dice: "8d6"`, `charges_spent: 3` (defaults to min), `resource.current: 7` (10→7), both ids resolved. |
| `test_staff_of_fire_under_min_returns_400` | POST with `charges: 1` (Fireball is min=max=3) → 400 out-of-range. |
| `test_staff_of_fire_empty_returns_409` | Drain the staff to 2 charges (below the 3-charge Fireball cost) via `/sheet-fields`, then cast → 409 with `error: "insufficient_charges"` + `current: 2`. Teardown restores the snapshot. |

### `test_use_item_action_staff_of_frost.py`
v2.267.0 charged-items Phase 2 — Staff of Frost (RAW DMG p.202, very rare, attunement). The first multi-action staff shipped against Phase 2, routed through the same generalized save-for-half AoE-damage handler as the Staff of Fire / Necklace of Fireballs. v1 ships the marquee Cone of Cold action (8d8 cold, CON save, fixed 5-charge spend); the `"spell"` save-DC sentinel resolves the DC from the wielder's sheet. Thalindra Moonwhisper (Elf Wizard Lv 7, INT 16, prof +3 → spell save DC 14) carries an equipped+attuned Staff of Frost + a `staff-of-frost` resource row (10/10). The fixture force-reseeds the charges to 10 and snapshots for teardown.

| Test | What it asserts |
|------|-----------------|
| `test_staff_of_frost_cone_of_cold_2_targets` | Cast Cone of Cold at 2 targets with no `charges` param → 200 with `save_dc: 14` (Thalindra's spell save DC via the `"spell"` sentinel), `save_ability: "CON"`, `dice: "8d8"`, `charges_spent: 5` (defaults to min), `resource.current: 5` (10→5), both ids resolved. |
| `test_staff_of_frost_under_min_returns_400` | POST with `charges: 1` (Cone of Cold is min=max=5) → 400 out-of-range. |
| `test_staff_of_frost_empty_returns_409` | Drain the staff to 4 charges (below the 5-charge Cone of Cold cost) via `/sheet-fields`, then cast → 409 with `error: "insufficient_charges"` + `current: 4`. Teardown restores the snapshot. |

### `test_use_item_action_staff_of_swarming_insects.py`
v2.268.0 charged-items Phase 2 — Staff of Swarming Insects (RAW DMG p.202, rare, attunement). A second multi-action staff routed through the generalized save-for-half AoE-damage handler. v1 ships the marquee Insect Plague action (4d10 piercing, CON save, fixed 5-charge spend); the `"spell"` save-DC sentinel resolves the DC from the wielder's sheet. Mira Greenleaf (Wood Elf Druid Lv 5, WIS 17, prof +3 → spell save DC 14) carries an equipped+attuned Staff of Swarming Insects + a `staff-of-swarming-insects` resource row (10/10). The fixture force-reseeds the charges to 10 and snapshots for teardown.

| Test | What it asserts |
|------|-----------------|
| `test_swarming_insects_insect_plague_2_targets` | Cast Insect Plague at 2 targets with no `charges` param → 200 with `save_dc: 14` (Mira's spell save DC via the `"spell"` sentinel), `save_ability: "CON"`, `dice: "4d10"`, `charges_spent: 5` (defaults to min), `resource.current: 5` (10→5), both ids resolved. |
| `test_swarming_insects_under_min_returns_400` | POST with `charges: 1` (Insect Plague is min=max=5) → 400 out-of-range. |
| `test_swarming_insects_empty_returns_409` | Drain the staff to 4 charges (below the 5-charge Insect Plague cost) via `/sheet-fields`, then cast → 409 with `error: "insufficient_charges"` + `current: 4`. Teardown restores the snapshot. |

### `test_use_item_action_ring_of_the_ram.py`
v2.269.0 charged-items Phase 3 — Ring of the Ram (RAW DMG p.193, rare, attunement). The first non-spell charge action and the first item on the new `action_kind: "attack"` shape: the `_use_item_action_attack` handler rolls a ranged force attack (1d20+7 vs the target's AC) and deals 2d10 force per charge spent (2/4/6d10) on a hit, decrementing the charge resource. Garrik Ironside (Fighter) carries an equipped+attuned Ring of the Ram + a `ring-of-the-ram` resource row (3/3). The fixture force-reseeds the charges to 3 and snapshots for teardown.

| Test | What it asserts |
|------|-----------------|
| `test_ring_of_the_ram_two_charge_strike` | A 2-charge ram-strike at a low-AC (1) target → 200 with `action_kind: "attack"`, `to_hit: 7`, `dice: "4d10"` (2d10 × 2 charges), `damage_type: "force"`, `charges_spent: 2`, `resource.current: 1` (3→1), `target_combatant_id` + `target_ac` echoed, `hit` is bool; damage > 0 on a hit (only a natural 1 misses vs AC 1). |
| `test_ring_of_the_ram_over_max_returns_400` | POST with `charges: 4` (ram-strike is min=1/max=3) → 400 out-of-range. |
| `test_ring_of_the_ram_empty_returns_409` | Drain the ring to 0 charges via `/sheet-fields`, then strike → 409 with `error: "insufficient_charges"` + `current: 0`. Teardown restores the snapshot. |

### `test_use_item_action_gem_of_seeing.py`
v2.270.0 charged-items Phase 3 — Gem of Seeing (RAW DMG p.171, rare, attunement). The first non-spell **buff** charge action and the first item on the new `action_kind: "buff"` shape: the `_use_item_action_buff` handler decrements the charge resource and installs a timed self-buff (the `truesight` template — 60-ft truesight, 100 rounds = 10 minutes) on the wielder's own combatant via `_install_buff` + `_mirror_buffs_to_sheet`. Rowan Quickbow (Ranger) carries an equipped+attuned Gem of Seeing + a `gem-of-seeing` resource row (3/3). The fixture force-reseeds the charges to 3 and snapshots for teardown.

| Test | What it asserts |
|------|-----------------|
| `test_gem_of_seeing_gaze_installs_truesight` | A gaze with Rowan in an active battle → 200 with `action_kind: "buff"`, `buff_key: "truesight"`, `charges_spent: 1`, `buff_installed: True`, `duration_rounds: 100`, `resource.current: 2` (3→2); the `truesight` buff lands on Rowan's combatant (verified via `GET /battle`). |
| `test_gem_of_seeing_empty_returns_409` | Drain the gem to 0 charges via `/sheet-fields`, then gaze → 409 with `error: "insufficient_charges"` + `current: 0`. Teardown restores the snapshot. |

### `test_use_item_action_wand_of_enemy_detection.py`
v2.277.0 charged-items Phase 1 (closes the plan) — Wand of Enemy Detection (RAW DMG p.211, rare, attunement). A utility `action_kind: "buff"` charge action (the Gem of Seeing shape): the `detect` action routes through the shared `_use_item_action_buff` handler (no save/damage), spending 1 of 7 charges and installing the `enemy-detection` buff template (60-ft hostile-direction sense, 10 rounds = 1 minute) on the wielder's own combatant. A `summary_verb` override makes the chat card read "activates" instead of the gem's "gazes through". Seeded on **Pip Quickfingers** (Halfling Rogue scout) with a 7-charge / 1d6+1 resource row.

| Test | What it asserts |
|------|-----------------|
| `test_wand_of_enemy_detection_installs_buff` | A detect with Pip in an active battle → 200 with `action_kind: "buff"`, `buff_key: "enemy-detection"`, `charges_spent: 1`, `buff_installed: True`, `duration_rounds: 10`, `resource.current: 6` (7→6); the `enemy-detection` buff lands on Pip's combatant (verified via `GET /battle`). |
| `test_wand_of_enemy_detection_empty_returns_409` | Drain the wand to 0 charges via `/sheet-fields`, then detect → 409 with `error: "insufficient_charges"` + `current: 0`. Teardown restores the snapshot. |

### `test_use_item_action_wand_of_magic_detection.py`
v2.324.0 — Wand of Magic Detection (RAW DMG p.210, uncommon, NO attunement). Pure clone of v2.277.0 Wand of Enemy Detection — only buff_key (`magic-detection`) and duration_rounds (100 = 10 min, mirroring Detect Magic's concentration) differ. 3 charges, regain 1d3 at dawn. Seeded on **Thalindra Moonwhisper** (Wizard, equipped, no attunement) with a 3-charge / 1d3 resource row.

| Test | What it asserts |
|------|-----------------|
| `test_wand_of_magic_detection_installs_buff` | A detect with Thalindra in an active battle → 200 with `action_kind: "buff"`, `buff_key: "magic-detection"`, `charges_spent: 1`, `buff_installed: True`, `duration_rounds: 100`, `resource.current: 2` (3→2); the `magic-detection` buff lands on Thalindra's combatant (verified via `GET /battle`). |
| `test_wand_of_magic_detection_empty_returns_409` | Drain the wand to 0 charges via `/sheet-fields`, then detect → 409 with `error: "insufficient_charges"` + `current: 0`. Teardown restores the snapshot. |
| `test_wand_of_magic_detection_no_attunement_required` | The seed inventory entry has `equipped: True` and no `attuned` flag — the action still fires, matching the RAW no-attunement contract. |

### `test_use_item_action_wand_of_secrets.py`
v2.325.0 — Wand of Secrets (RAW DMG p.211, uncommon, NO attunement). Direct clone of v2.324.0 Wand of Magic Detection — only buff_key (`secrets-detection`) and duration_rounds (1 = single whisper per charge) differ. 3 charges, regain 1d3 at dawn. Seeded on **Pip Quickfingers** (Halfling Rogue scout, equipped, no attunement) with a 3-charge / 1d3 resource row.

| Test | What it asserts |
|------|-----------------|
| `test_wand_of_secrets_installs_buff` | A reveal with Pip in an active battle → 200 with `action_kind: "buff"`, `buff_key: "secrets-detection"`, `charges_spent: 1`, `buff_installed: True`, `duration_rounds: 1`, `resource.current: 2` (3→2); the `secrets-detection` buff lands on Pip's combatant (verified via `GET /battle`). |
| `test_wand_of_secrets_empty_returns_409` | Drain the wand to 0 charges via `/sheet-fields`, then reveal → 409 with `error: "insufficient_charges"` + `current: 0`. Teardown restores the snapshot. |
| `test_wand_of_secrets_no_attunement_required` | The seed inventory entry has `equipped: True` and no `attuned` flag — the action still fires, matching the RAW no-attunement contract. |

### `test_use_item_action_horn_of_blasting.py`
v2.271.0 charged-items Phase 3 (closes the phase) — Horn of Blasting (RAW DMG p.174, uncommon, no attunement). The first charge-less item action: `_use_item_action_horn_of_blasting` resolves a 30-ft-cone DC 15 CON save → 5d6 thunder + deafened on a fail, half + no deafen on a pass (deafen installs only on a failed save). No resource row, no charge gate, no `resource_update`. Krieger Stonefist (Barbarian) carries an equipped Horn of Blasting (no attunement).

| Test | What it asserts |
|------|-----------------|
| `test_horn_of_blasting_blast_2_targets` | A blast at 2 targets in an active battle → 200 with `action_kind: "attack_aoe"`, `save_dc: 15`, `save_ability: "CON"`, `dice: "5d6"`, `damage_type: "thunder"`, `condition_key: "deafened"`, no `resource` field; both ids resolved with per-target `passed`/`damage_dealt` (int)/`deafened` (bool, true iff the save failed). |
| `test_horn_of_blasting_too_many_targets_returns_400` | A 25-target `target_combatant_ids` list → 400 (the 24-target cone cap). |

### `test_use_item_action_staff_of_thunder_and_lightning.py`
v2.272.0 charged-items Phase 2 — Staff of Thunder and Lightning (RAW DMG p.202, very rare, attunement). A fourth multi-action staff routed through the generalized save-for-half AoE-damage handler. v1 ships the marquee Thunder action (2d6 thunder, CON save, fixed 2-charge spend) at a flat RAW DC 17 (not the `"spell"` sentinel). Magnus Hexbinder (Bronze Dragonborn Warlock) carries an equipped+attuned Staff of Thunder and Lightning + a `staff-of-thunder-and-lightning` resource row (5/5). The fixture force-reseeds the charges to 5 and snapshots for teardown.

| Test | What it asserts |
|------|-----------------|
| `test_staff_of_thunder_and_lightning_thunder_2_targets` | Cast Thunder at 2 targets with no `charges` param → 200 with `save_dc: 17` (flat RAW DC), `save_ability: "CON"`, `dice: "2d6"`, `charges_spent: 2` (defaults to min), `resource.current: 3` (5→3), both ids resolved. |
| `test_staff_of_thunder_and_lightning_under_min_returns_400` | POST with `charges: 1` (Thunder is min=max=2) → 400 out-of-range. |
| `test_staff_of_thunder_and_lightning_empty_returns_409` | Drain the staff to 1 charge (below the 2-charge Thunder cost) via `/sheet-fields`, then cast → 409 with `error: "insufficient_charges"` + `current: 1`. Teardown restores the snapshot. |

### `test_use_item_action_wand_of_wonder.py`
v2.273.0 charged-items Phase 4 — Wand of Wonder (RAW DMG p.213, rare, attunement by a spellcaster). The first `action_kind: "random_table"` charge action: spend 1 charge → roll d100 on the `_WAND_OF_WONDER_TABLE` chaos table → return the rolled effect for the GM to narrate. The handler honors an optional `force_roll` (1-100) override for deterministic tests. Zara Emberfire (Tiefling Draconic Sorcerer) carries an equipped+attuned Wand of Wonder + a `wand-of-wonder` resource row (7/7). The fixture force-reseeds the charges to 7 and snapshots for teardown.

| Test | What it asserts |
|------|-----------------|
| `test_wand_of_wonder_roll_happy_path` | Roll with no params → 200 with `action_kind: "random_table"`, `roll` in 1..100, `charges_spent: 1`, `resource.current: 6` (7→6), non-empty `effect` + `row_key`. |
| `test_wand_of_wonder_force_roll_fireball` | POST with `force_roll: 72` (the 70-79 band) → `roll: 72`, `row_key: "fireball"`, `"Fireball"` in `effect`, `resource.current: 6`. |
| `test_wand_of_wonder_empty_returns_409` | Drain the wand to 0 charges via `/sheet-fields`, then roll → 409 with `error: "insufficient_charges"` + `current: 0`. Teardown restores the snapshot. |

### `test_use_item_action_staff_of_power.py`
v2.274.0 charged-items Phase 2 — Staff of Power (RAW DMG p.202, very rare, attunement by a spellcaster). The marquee multi-action staff: a +2 passive to AC / saving throws / spell attack rolls (via `_MAGIC_ITEM_PASSIVES`), a 20-charge pool (regain 2d8+4 at dawn), and three damaging spell actions routed through the generalized save-for-half AoE-damage handler (`cast-fireball` 10d6 fire / DEX, `cast-lightning-bolt` 10d6 lightning / DEX, `cast-cone-of-cold` 8d8 cold / CON), each a fixed 5-charge spend at the wielder's spell save DC (the `"spell"` sentinel). Thalindra Moonwhisper (High Elf Wizard) carries an equipped+attuned Staff of Power + a `staff-of-power` resource row (20/20). The fixture force-reseeds the charges to 20 and snapshots for teardown.

| Test | What it asserts |
|------|-----------------|
| `test_staff_of_power_fireball_2_targets` | Cast Fireball at 2 targets with no `charges` param → 200 with `save_ability: "DEX"`, `dice: "10d6"`, `charges_spent: 5`, `resource.current: 15` (20→15), both ids resolved. |
| `test_staff_of_power_lightning_bolt` | Cast Lightning Bolt at 1 target → `save_ability: "DEX"`, `dice: "10d6"`, `charges_spent: 5`, `resource.current: 15`. |
| `test_staff_of_power_cone_of_cold` | Cast Cone of Cold at 1 target → `save_ability: "CON"`, `dice: "8d8"`, `charges_spent: 5`, `resource.current: 15`. |
| `test_staff_of_power_empty_returns_409` | Drain the staff to 4 charges (below the 5-charge cost) via `/sheet-fields`, then cast → 409 with `error: "insufficient_charges"` + `current: 4`. Teardown restores the snapshot. |
| `test_staff_of_power_passive_spell_attack_bonus` | `/sheet-json` `derived.spell_attack_bonus` includes the held staff's +2 (`>= 2`). |

### `test_arrow_of_slaying.py`
v2.159.1 magic-items-automation Phase 8a — Arrow of Slaying (Giants) (RAW DMG p.151). First ammunition-shape catalog row, extending the v2.158.102 `on_hit_save` substrate with a new `effect: "damage"` variant for save-for-half damage. Rowan Quickbow's Longbow (Arrow of Slaying — Giants) attack at attack_index 2 fires the rider via `_slug` match. New Hill Giant token template (`sheet.type="giant"`) gives the helper-resolution path a real RAW target.

| Test | What it asserts |
|------|-----------------|
| `test_slaying_arrow_fires_save_on_giant` | Hit Hill Giant (template-resolved giant) → HP drop > 12 (base attack max + rider min, proving rider damage layered on top regardless of save pass/fail). |
| `test_slaying_arrow_silent_on_non_giant` | Hit humanoid → HP drop ≤ 12 (rider gated off by condition predicate). |
| `test_regular_longbow_no_slaying_rider` | Fire plain Longbow (attack_index 0, no slug match) at giant → HP drop ≤ 12 (slug-on-attack gate blocks rider leak across weapons, same shape as v2.158.91 Flame Tongue test). |
| `test_slaying_arrow_consumes_on_use` | v2.159.2 Phase 8b: read Rowan's initial Slaying qty (6 from seed); fire one Slaying arrow at giant; assert qty=5. Teardown PATCHes the inventory back via /sheet-fields. |

### `test_sun_blade_rider.py`
v2.158.104 magic-items-automation Phase 7d — Sun Blade +1d8 radiant vs. undead (RAW DMG p.205). Pure substrate composition using the v2.158.93 Phase 5c shape (dice + condition predicate). Damage type explicit "radiant" (not the weapon-type fallback). Skeleton NPC template extended with `sheet.type="undead"` so v2.158.96 Phase 5f helper auto-resolves on drag-spawn. Dame Seraphine Vael gets the Sun Blade Longsword (attack_index 2, inventory_index 5, +7/1d8+7 — RAW +2 baked in).

| Test | What it asserts |
|------|-----------------|
| `test_sun_blade_fires_on_undead_target` | Attack `creature_type: "undead"` → `auto_uplifts` carries `source: "item-sun-blade"`, `damage_type: "radiant"`, `expression: "1d8"`, total in [1, 16] (crit-doubled cap). |
| `test_sun_blade_silent_on_humanoid` | Attack humanoid → no rider. Condition predicate gates correctly. |
| `test_sun_blade_suppressed_when_detuned` | Detune → no rider even vs. undead. Re-attunes in teardown. |
| `test_sun_blade_fires_via_skeleton_template` | Skeleton token template's `sheet.type="undead"` auto-resolves via Phase 5f helper → rider fires on a combatant referencing the template without `creature_type` on the combatant. Validates the demo path. |

### `test_sword_of_sharpness.py`
v2.158.103 magic-items-automation Phase 7c — Sword of Sharpness +4d6 slashing on natural 20 (RAW DMG p.206). Second `on_nat_20` item using a new `effect: "damage"` variant alongside Vorpal's `effect: "decap"`. Same `_apply_magic_item_nat_20_effect` helper dispatches both. Pip's seed at attunement cap (3/3).

| Test | What it asserts |
|------|-----------------|
| `test_sharpness_no_rider_when_detuned` | Detune the Sword of Sharpness → nat-20 rider suppressed even with d20=20 seeded. Re-attunes in teardown. |
| `test_sharpness_nat_20_extra_damage` | Iterates seeds 0-199 finding one that lands d20=20 on Pip's first attack; asserts `feature_used` with `source: "item-sword-of-sharpness-nat20"` fires and `hp_dealt` is in [4, 24] (4d6 range). |

### `test_ability_disadvantage_generalized.py`
v2.347.0 engine — the `effects.disadvantage_on` roll intercept generalized from STR-checks-only to any `{ability}_check`/`{ability}_save` marker at `/roll`. Buff seeded on a PC combatant via PUT /battle, then `/roll` with the matching stat_key reveals the `2d20kl1` swap.

| Test | What it asserts |
|------|-----------------|
| `test_con_save_disadvantage_fires` | `disadvantage_on=["con_save"]` → a CON save rolls `2d20kl1` + a `disadvantage-con_save` broadcast fires. |
| `test_str_save_disadvantage_fires` | `disadvantage_on=["str_save"]` → a STR save rolls `2d20kl1` (saves were previously uncovered). |
| `test_marker_specificity_control` | A `con_save`-only buff does NOT impose disadvantage on a `con_check` roll (marker specificity). |

### `test_use_item_action_ring_of_shooting_stars.py`
v2.357.0 magic-items — Ring of Shooting Stars (RAW DMG p.191, very rare, attunement), the "Shooting Stars" mode on the generalized save-for-half Necklace of Fireballs handler (1-3 motes, DC 15 DEX save or 5d4 fire each, half on save). Carrier: Zara Emberfire (equipped+attuned + `ring-of-shooting-stars` 6-charge resource).

| Test | What it asserts |
|------|-----------------|
| `test_ring_shooting_stars_3_motes` | 3 motes (charges=3) at 3 targets → 200, item_name "Ring of Shooting Stars", save_dc 15, save_ability DEX, dice 5d4, charges_spent 3, resource 6→3, all three ids resolved. |
| `test_ring_shooting_stars_empty_returns_409` | Ring drained to 0 charges → 409 `insufficient_charges` (current 0). |

### `test_use_item_action_circlet_of_blasting.py`
v2.356.0 magic-items — Circlet of Blasting (RAW DMG p.159, uncommon, no attunement), first item on the new spell-ATTACK handler (`_use_item_action_spell_attack`). Scorching Ray: 3 ranged spell attacks at +5, 2d6 fire each on a hit, 1/dawn. Carrier: Zara Emberfire (equipped + `circlet-of-blasting` resource). AC-1 dummies + seeded dice.

| Test | What it asserts |
|------|-----------------|
| `test_circlet_scorching_ray_3_beams` | 3 rays at AC-1 dummies → 200, item_name "Circlet of Blasting", attack_bonus 5, beams 3, damage_type fire, charges_spent 1, resource 1→0, 3 results, ≥1 hit dealing fire damage. |
| `test_circlet_empty_returns_409` | Circlet drained to 0 uses → 409 `insufficient_charges` (current 0). |

### `test_use_item_action_umbrella_slugs.py`
v2.404.0 magic-items — Phase 9.3 umbrella-slug closure. Real mechanical wiring for the two action-shape umbrella slugs (`potion-of-healing`, `spell-scroll`). Carrier: Thalindra Moonwhisper (Wizard) seeded with both items.

| Test | What it asserts |
|------|-----------------|
| `test_potion_of_healing_drink_basic_tier` | Basic Potion of Healing (`_tier` unset → 1): drink → 2d4+2 heal (4 ≤ roll ≤ 10), HP rises from 5, qty=1 entry consumed. Tests the tier-1 default + qty-removal path. |
| `test_potion_of_healing_tier_picker` | Tier-3 (Superior, `_tier=3`): drink → 8d4+8 heal (16 ≤ roll ≤ 40), `dice_expression == "8d4+8"`, `item_name == "Potion of Superior Healing"`. Tests the `_tier` field driving the picker. |
| `test_spell_scroll_consumes_on_cast` | Spell Scroll (Magic Missile): `cast-spell` → 200 with `consumed=True`, `spell_slug="magic-missile"`, `spell_label="Magic Missile"`, inventory entry removed. Tests the consumable cast-from-scroll path. |

### `test_use_item_action_announce_only.py`
v2.403.0 + v2.403.1 magic-items — Phase 9.2 substrate ship: charge-tracked announce-only Bucket D items. Eight items now share the new `_use_item_action_announce_only` handler — the underlying effect (summon, planar travel, capture, exploration utility) stays GM-narrated, but the engine ticks the RAW counter on `/use_item_action` and broadcasts a `feature_used` summary. Carriers: Bowl (Rowan), Brazier (Caelan), Censer (Seraphine), Stone (Krieger) — all 1/dawn elemental quartet v2.403.0; Cape of the Mountebank (Lyra, 1/dawn), Iron Bands of Binding (Krieger, 1/dawn), Efreeti Bottle (Zara, 1/dawn), and Bag of Tricks (Brakka, 3/dawn) — v2.403.1.

| Test | What it asserts |
|------|-----------------|
| `test_announce_only_items_decrement_charge` | All eight items: `/use_item_action` → 200 with `charges_spent=1`, `resource.current = initial-1`, `item_name` populated; sheet read-back also shows the counter decremented. Pool-aware (handles both 1/1 and 3/3 initial pools via the parameterized `_BATCH`). |
| `test_second_use_same_day_returns_409` | Bowl (1/1): second invocation before a rest → 409 `insufficient_charges` (current 0, requested 1). |
| `test_long_rest_restores_charge` | Censer: spend → 0; long rest → counter back to full initial. |
| `test_unknown_action_key_returns_404` | Bowl with a bogus `action_key` → 404 `no action` (dispatch gate). |
| `test_bag_of_tricks_multi_pull_pool` (v2.403.1) | Bag of Tricks (3/3): three sequential pulls drain 3 → 2 → 1 → 0; fourth pull → 409 `insufficient_charges`. Canonical test for the multi-charge-pool variant of the shared handler. |
| `test_pipes_of_the_sewers_multi_charge_spend` (v2.403.2) | Pipes of the Sewers (3/3 + 1d3/dawn): PATCH equipped+attuned → spend 2 charges in one call (3 → 1) → `>max` (4) returns 400. Tests the multi-charge-per-call path on a vault-loot item. |
| `test_helm_of_teleportation_requires_attunement` (v2.403.2) | Helm of Teleportation: equipped + un-attuned → 409 "attunement"; PATCH attuned=True → 200 with resource 3 → 2. Tests the attunement gate. |
| `test_cube_of_force_variable_charge_spend` (v2.403.2) | Cube of Force (36/36 + 1d20/dawn): spend 3 then 5 (36 → 33 → 28), `>max` (6) returns 400, long rest strictly grows the pool from 28 (bounded by 1d20 roll, not full refill). Tests the largest-pool + dice-recharge path. |
| `test_multi_day_cooldown_items_decrement_and_resist_rest` (v2.403.3) | Multi-day cooldown items (horn-of-valhalla 1/7d, ring-of-djinni-summoning 1/24h, rod-of-security 1/10d): PATCH equipped+attuned → spend → 0 → second use returns 409 → long rest stays at 0 (`reset: "none"`). Tests the manual-reset path. |
| `test_chime_of_opening_lifetime_pool` (v2.403.4) | Chime of Opening (10/10 lifetime): drain across 10 sequential strikes (10 → 0), 11th → 409, long rest stays at 0 (`reset: "none"`). Tests the lifetime-pool drain shape. |
| `test_ring_of_three_wishes_lifetime_pool` (v2.403.4) | Ring of Three Wishes (3/3 lifetime, attunement): PATCH equipped+attuned → drain 3 → 0, 4th → 409, long rest stays at 0. Tests the lifetime-pool drain shape on an attunement-gated item. |
| `test_multi_dose_consumable_containers_drain` (v2.403.5) | Multi-dose consumable containers (restorative-ointment 3, dust-of-dryness 7, sovereign-glue 4, bag-of-beans 7): each item drains 1 dose + long rest stays put (`reset: "none"`). Tests the consumable-container shape; handles both equipped and vault-loot carriers. |
| `test_wind_fan_first_use_is_safe` (v2.403.6) | Wind Fan first use of the day (current==max): tear_chance=0, no roll, resource 10 → 9. The Bucket A holdout's safe-first-use branch. |
| `test_wind_fan_overuse_tears_on_force` (v2.403.6) | Wind Fan overuse with `force_d100=10` (≤ 20% threshold): destroyed=True, inventory item flagged `_destroyed: True` + `equipped: False`, resource is NOT decremented. Tests the destruction branch. |
| `test_wind_fan_overuse_survives_on_high_roll` (v2.403.6) | Wind Fan overuse with `force_d100=80` (> 20% threshold): destroyed=False, resource 9 → 8. Tests the survive-the-overuse branch. |
| `test_medallion_of_thoughts_charge_decrement` (v2.403.7) | Medallion of Thoughts (3/3 + 1d3/dawn, attunement): PATCH equipped+attuned → drain 3 → 0, 4th → 409, long-rest restores 1..3 via 1d3 recharge. Closes the Bucket A holdout list. |

### `test_use_item_action_rope_of_entanglement.py`
v2.355.0 magic-items — Rope of Entanglement (RAW DMG p.198, rare, no attunement), sixth Bucket A item and the first `unlimited` (no-charge) item on the shared Wand of Fear handler. DC 15 DEX save or restrained, at will. Carrier: Kael Brightleaf (equipped, NO charge resource).

| Test | What it asserts |
|------|-----------------|
| `test_rope_entangle_one_target` | Entangle at 1 NPC target → 200, item_name "Rope of Entanglement", save_dc 15, save_ability DEX, charges_spent 0, resource None, id in results. |
| `test_rope_is_unlimited` | A second invocation also returns 200 (resource None) — the unlimited path never depletes (no `insufficient_charges`). |

### `test_use_item_action_robe_of_scintillating_colors.py`
v2.354.0 magic-items — Robe of Scintillating Colors (RAW DMG p.194, very rare, attunement), fifth Bucket A charge-cast item; first to install `stunned` via the shared handler. Runs on `/use_item_action` → Wand of Fear handler (30-ft radius, DC 15 WIS save or stunned 1 round, 3 charges). Carrier: Lyra Sunstrider (equipped+attuned + `robe-of-scintillating-colors` resource).

| Test | What it asserts |
|------|-----------------|
| `test_robe_dazzling_display_2_targets` | Dazzling display at 2 NPC targets → 200, item_name "Robe of Scintillating Colors", save_dc 15, save_ability WIS, charges_spent 1, resource 3→2, both ids in results. |
| `test_robe_empty_returns_409` | Robe drained to 0 charges → 409 `insufficient_charges` (current 0). |

### `test_use_item_action_ring_of_animal_influence.py`
v2.353.0 magic-items — Ring of Animal Influence (RAW DMG p.190, rare, no attunement), fourth Bucket A charge-cast item. Runs on the `/use_item_action` → Wand of Fear handler (single-target animal friendship, DC 13 WIS save or charmed, 3 charges). Carrier: Mira Greenleaf (equipped + `ring-of-animal-influence` resource).

| Test | What it asserts |
|------|-----------------|
| `test_ring_animal_friendship_one_target` | Animal friendship at 1 NPC beast → 200, item_name "Ring of Animal Influence", save_dc 13, save_ability WIS, charges_spent 1, resource 3→2, id in results. |
| `test_ring_animal_influence_empty_returns_409` | Ring drained to 0 charges → 409 `insufficient_charges` (current 0). |

### `test_use_item_action_trident_of_fish_command.py`
v2.352.0 magic-items — Trident of Fish Command (RAW DMG p.205, uncommon, attunement), third Bucket A charge-cast item. Runs on the `/use_item_action` → Wand of Fear handler (single-target dominate beast, DC 15 WIS save or charmed, 3 charges). Carrier: Mira Greenleaf (equipped+attuned + `trident-of-fish-command` resource).

| Test | What it asserts |
|------|-----------------|
| `test_trident_dominate_beast_one_target` | Dominate beast at 1 NPC beast → 200, item_name "Trident of Fish Command", save_dc 15, save_ability WIS, charges_spent 1, resource 3→2, id in results. |
| `test_trident_empty_returns_409` | Trident drained to 0 charges → 409 `insufficient_charges` (current 0). |

### `test_use_item_action_rod_of_rulership.py`
v2.351.0 magic-items — Rod of Rulership (RAW DMG p.197, rare, attunement), second Bucket A charge-cast item. Runs on the `/use_item_action` → Wand of Fear handler (120-ft radius, DC 15 WIS save or charmed, 1/dawn use). Carrier: Dame Seraphine Vael (equipped+attuned + `rod-of-rulership` resource).

| Test | What it asserts |
|------|-----------------|
| `test_rod_of_rulership_command_2_targets` | Command Obedience at 2 NPC targets → 200, item_name "Rod of Rulership", save_dc 15, save_ability WIS, charges_spent 1, resource 1→0, both ids in results. |
| `test_rod_of_rulership_empty_returns_409` | Rod drained to 0 uses → 409 `insufficient_charges` (current 0). |

### `test_use_item_action_pipes_of_haunting.py`
v2.350.0 magic-items — Pipes of Haunting (RAW DMG p.184, uncommon, no attunement), first Bucket A charge-cast item. Runs on the `/use_item_action` → generalized Wand of Fear handler (30-ft radius, DC 15 WIS save or frightened, 3 charges). Carrier: Lyra Sunstrider (equipped + `pipes-of-haunting` charge resource).

| Test | What it asserts |
|------|-----------------|
| `test_pipes_of_haunting_tune_2_targets` | Haunting tune at 2 NPC targets → 200, item_name "Pipes of Haunting", save_dc 15, save_ability WIS, charges_spent 1, resource 3→2, both ids in results. |
| `test_pipes_of_haunting_empty_returns_409` | Pipes drained to 0 charges → 409 `insufficient_charges` (current 0). |

### `test_item_staff_of_striking.py`
v2.349.0 magic-items — Staff of Striking (RAW DMG p.202, very rare, attunement), Bucket C on-hit rider. +1d6 force rides the Frost Brand always-on dice-uplift (section 6c, `auto_uplifts` source `item-staff-of-striking`); the +3 attack/damage is baked on Magnus's weapon row. Charge economy (1-3 of 10) GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_staff_of_striking_force_rider_fires` | Equipped+attuned → an attack surfaces a single `auto_uplifts`: label "Staff of Striking", expression "1d6", damage_type "force", total in [1,12]. |
| `test_staff_of_striking_requires_attunement` | Equipped-but-unattuned → the force rider does not fire (attunement gate). |

### `test_item_staff_of_withering.py`
v2.346.0 magic-items — Staff of Withering (RAW DMG p.202, rare, attunement), Bucket C on-hit rider. +2d10 necrotic rides the Frost Brand always-on dice-uplift (section 6c, `auto_uplifts` source `item-staff-of-withering`). Carrier: Magnus Hexbinder (weapon attack row); inventory item seeded inert, PATCHed equipped+attuned in-test. Charge limit + DC15 CON disadvantage GM-narrated in v1.

| Test | What it asserts |
|------|-----------------|
| `test_staff_of_withering_necrotic_rider_fires` | Equipped+attuned → an attack surfaces a single `auto_uplifts` entry: label "Staff of Withering", expression "2d10", damage_type "necrotic", total in [2,40]. |
| `test_staff_of_withering_save_fires_on_hit` | A hit vs a Bandit → `feature_used` source `item-staff-of-withering-save`, dc 15, ability CON (v2.348.0 `ability_disadvantage` dispatch). |
| `test_staff_of_withering_withers_on_failed_save` | Sweep seeds until the Bandit fails → the `withered` buff is installed carrying `effects.disadvantage_on` with the STR/CON check+save markers. |
| `test_staff_of_withering_requires_attunement` | Equipped-but-unattuned → the necrotic rider does not fire (attunement gate). |

### `test_item_alignment_talismans.py`
v2.367.0 magic-items — alignment talismans (RAW DMG p.207, legendary, attunement). Both compose on the existing Necklace of Fireballs save-for-half handler (two slugs added to the dispatch tuple). Sir Caelan carries Pure Good inert (7 charges, 6d6 radiant, DC 18 CHA); Magnus Hexbinder carries Ultimate Evil inert (6 charges, 8d6 necrotic, DC 18 CHA). Resource rows are seeded up front. v1 GM-narrates the alignment gate, alignment-keyed instant-kill, and +2 spell attack bonus.

| Test | What it asserts |
|------|-----------------|
| `test_pure_good_invoke_charges_and_save` | Pure Good invocation reports `save_dc: 18`, `save_ability: CHA`, `dice: "6d6"`; resource decrements 7→6. |
| `test_ultimate_evil_invoke_charges_and_save` | Ultimate Evil invocation reports `save_dc: 18`, `save_ability: CHA`, `dice: "8d6"`; resource decrements 6→5. |
| `test_pure_good_empty_charges_returns_409` | Resource forced to 0 → 409 `insufficient_charges` per the Necklace handler's charge gate. |

### `test_item_shield_of_missile_attraction.py`
v2.366.0 magic-items — Shield of Missile Attraction (RAW DMG p.199, rare, attunement, cursed), Bucket B ranged-weapon damage-resistance on the new `resistance_to_ranged_weapon` boolean substrate. `_resistance_halve` gains an `is_ranged_weapon_attack: bool = False` kwarg threaded through `_apply_damage_to_combatant`. Both /attack and /npc_attack compute the flag via `_attack_is_ranged_weapon(attack)`. Dame Seraphine Vael carries the shield inert; tests PATCH equipped+attuned and toggle the auto-apply-damage flag so the resistance check runs. Rowan Quickbow's Longbow (ranged) and Shortsword (melee) drive the contrast.

| Test | What it asserts |
|------|-----------------|
| `test_ranged_attack_resistance` | Shield equipped+attuned → Rowan's Longbow hit reports `target_resistance_applied: True`. |
| `test_melee_attack_no_resistance` | Same shield equipped+attuned → Rowan's Shortsword (melee) hit reports `target_resistance_applied: False` (resistance is ranged-only). |
| `test_no_resistance_without_attunement` | Equipped-but-unattuned → ranged hit reports `target_resistance_applied: False` (attunement gate). |

### `test_item_arrow_catching_shield.py`
v2.365.0 magic-items — Arrow-Catching Shield (RAW DMG p.152, rare, attunement), Bucket B conditional-AC passive on the new `conditional_ac_bonus_vs_ranged` substrate. `_read_target_ac` gains an `is_ranged_attack: bool = False` kwarg; both /attack and /npc_attack compute the flag via `_attack_is_ranged_weapon(attack)` and thread it through. Sir Caelan carries the shield inert; the harness PATCHes equipped+attuned. Rowan Quickbow's Longbow (ranged) and Shortsword (melee) drive the contrast.

| Test | What it asserts |
|------|-----------------|
| `test_ranged_attack_adds_plus_2_ac` | Shield equipped+attuned → Rowan's Longbow attack sees `target_ac` = baseline + 2. |
| `test_melee_attack_no_bonus` | Same shield equipped+attuned → Rowan's Shortsword (melee) sees `target_ac` at baseline (no conditional bonus). |
| `test_no_bonus_without_attunement` | Equipped-but-unattuned → no +2 on ranged attacks (attunement gate). |

### `test_item_adamantine_armor.py`
v2.364.0 magic-items — Adamantine Armor (RAW DMG p.150, uncommon, NO attunement), Bucket B passive on the new `crits_become_normal` substrate. The /attack + /npc_attack pipelines call `_target_wearer_crits_become_normal` after the is_crit determination; when True, `is_crit` is flipped back to False (suppressing the damage-dice doubling + rider-crit handling) and a `feature_used` audit broadcast fires with source `item-adamantine-armor-crit-suppressed`. Garrik Ironside carries the armor inert; the harness PATCHes equipped. Sir Caelan attacks Garrik on a sweep-found nat-20 seed.

| Test | What it asserts |
|------|-----------------|
| `test_adamantine_suppresses_crit` | Armor equipped → nat-20 attack → `is_crit: False`, `adamantine_crit_suppressed: True`, `adamantine_crit_suppressor: "Adamantine Armor"`, suppression `feature_used` broadcast fires. |
| `test_no_suppression_without_armor` | Armor inert → nat-20 attack → `is_crit: True`, no suppression broadcast (the gate is armor-sourced, not baked). |

### `test_item_berserker_axe_save.py`
v2.363.0 magic-items — Berserker Axe cursed berserk save (RAW DMG p.155). Closes the v2.362.0 partial: a new `on_damage_save` payload on `_MAGIC_ITEM_PASSIVES` + the `_maybe_item_on_damage_save` helper, fired from both `_apply_damage_to_combatant` (PC path, next to concentration-save) AND PATCH /sheet-fields's damage branch. On a failed DC 15 WIS save the `berserk` buff installs with `berserk_active: True` + `berserk_attack_nearest: True` markers (the auto-attack-nearest AI is GM-narrated in v1).

| Test | What it asserts |
|------|-----------------|
| `test_berserk_save_installs_buff_on_failed_save` | Krieger attuned + takes 10 damage via PATCH /sheet-fields → sweep seeds until the DC 15 WIS save fails → `berserk` buff appears with `berserk_active: True`, `berserk_attack_nearest: True`, source `item-berserker-axe`. |
| `test_berserk_save_does_not_fire_without_attunement` | Equipped-but-unattuned axe → across 50 seeds of damage events, no `berserk` buff installs (attunement gate). |

### `test_item_berserker_axe.py`
v2.362.0 magic-items — Berserker Axe (RAW DMG p.155, rare, attunement, cursed), Bucket C HP-max passive on the new `hp_max_bonus_per_level` substrate (composed with the Amulet-of-Health CON-mod delta in `_effective_max_hp_for_sheet`). Krieger Stonefist (Lv 7, HP 75/75) carries the axe inert; PATCH-equipped+attuned + GET /sheet-json proves the +1×level → +7 effective max HP. The cursed berserk save is GM-narrated in v1.

| Test | What it asserts |
|------|-----------------|
| `test_berserker_axe_raises_effective_max_hp` | Axe equipped+attuned → /sheet-json `derived.effective_max_hp` = {base 75, effective 82, delta 7, level 7, sources ["Berserker Axe"]}. |
| `test_berserker_axe_inert_baseline` | Default seed (axe inert) → no `effective_max_hp` key on derived (the +7 is axe-sourced, not baked). |
| `test_berserker_axe_requires_attunement` | Equipped-but-unattuned → no `effective_max_hp` (attunement gate). |

### `test_item_oathbow.py`
v2.361.0 magic-items — Oathbow (RAW DMG p.183, very rare, attunement, longbow), Bucket C conditional attack rider on the new `condition_sworn_enemy` predicate. A `/declare_oathbow_sworn_enemy` endpoint installs an `oathbow-sworn-enemy` buff on the wielder carrying both `attack_advantage_vs_target_combatant_id` (rides the v2.158.53 Vow-of-Enmity attack-adv reader) and `oathbow_sworn_enemy_id` (the new dice-rider gate); on a hit vs that combatant the rider deals +3d6 piercing and the d20 attack roll gets advantage. Rowan Quickbow carries it at attack_index 4; seed-inert + PATCH-equipped+attuned per test.

| Test | What it asserts |
|------|-----------------|
| `test_declare_installs_sworn_enemy_buff` | POST /declare_oathbow_sworn_enemy installs the `oathbow-sworn-enemy` buff with `oathbow_sworn_enemy_id` AND `attack_advantage_vs_target_combatant_id` both pointing at the target combatant id. |
| `test_rider_fires_on_sworn_enemy` | A hit vs the declared sworn enemy surfaces a single `item-oathbow` uplift: 3d6 piercing, total in [3, 36] (non-crit through crit-doubled). |
| `test_rider_silent_on_non_sworn_target` | A hit vs a NON-sworn target does not produce an `item-oathbow` uplift (the `condition_sworn_enemy` predicate gates correctly). |
| `test_attack_has_advantage_vs_sworn_enemy` | The d20 attack roll vs the sworn enemy uses 2d20kh1 (existing `_attacker_has_vow_of_enmity_vs_target` reader fires on the generic adv marker). |
| `test_declare_without_equipped_attuned_returns_409` | Declaring while the Oathbow inventory item is equipped-but-unattuned returns 409 `oathbow_not_equipped_attuned`. |

### `test_item_sword_of_wounding.py`
v2.360.0 magic-items — Sword of Wounding (RAW DMG p.207, rare, attunement, any sword), Bucket C on-hit-install attack rider. The first item on the new `on_hit_install` substrate: each hit appends a `wounded` stack to the target; at the start of the wounded creature's turn the engine ticks 1d4 necrotic per stack via the new PUT /battle start-of-turn hook, then resolves a DC 15 CON save — pass clears all wounds. Sir Caelan carries it at attack_index 4; the inventory item is seed-inert (PATCH-equipped+attuned per test). Bandits make the NPC save inline.

| Test | What it asserts |
|------|-----------------|
| `test_attack_installs_wound_stack` | A hit installs a `wounded` buff carrying `wound_stacks: 1` plus the start-of-turn tick + save markers (1d4 necrotic, DC 15 CON). |
| `test_second_hit_stacks_wounds` | Two consecutive hits on the same target increment `wound_stacks` from 1 → 2 on a single buff entry (no second buff appended). |
| `test_no_attunement_no_install` | Equipped-but-unattuned → no wound install (attunement gate). |
| `test_turn_start_ticks_damage` | A turn-advance to the wounded combatant's turn drops their HP by 1..4 (one stack × 1d4) via the new start-of-turn hook. |
| `test_passing_save_clears_wounds` | Across seeds the DC 15 CON save eventually passes and the `wounded` buff is dropped (`_resolve_repeated_save_for_buff` NPC drop path). |

### `test_item_staff_of_the_magi.py`
v2.359.0 magic-items — Staff of the Magi (RAW DMG p.202, legendary, attunement), Bucket B passive reusing the v2.358.0 `spell_dc_bonus` substrate (+2 spell save DC). Observed through Thalindra casting Fireball at a Bandit (`auto_save_dc`). Seed-inert + PATCH-equipped+attuned + long rest between casts.

| Test | What it asserts |
|------|-----------------|
| `test_magi_boosts_spell_save_dc` | Fireball's `auto_save_dc` is exactly 2 higher with the staff equipped+attuned than inert. |

### `test_item_staff_of_the_woodlands.py`
v2.358.0 magic-items — Staff of the Woodlands (RAW DMG p.202, rare, attunement), Bucket B passive: +2 spell save DC via the new `spell_dc_bonus` substrate (folded into `_compute_spell_save_dc_from_sheet`). Observed through Mira's Staff of Swarming Insects (Insect Plague uses the "spell"-sentinel DC). Seed-inert + PATCH-equipped+attuned.

| Test | What it asserts |
|------|-----------------|
| `test_woodlands_boosts_spell_dc` | Woodlands staff equipped+attuned → Insect Plague reports save_dc 16 (baseline 14 + 2). |
| `test_woodlands_inert_baseline_dc` | Woodlands staff inert → Insect Plague reports the unmodified save_dc 14. |

### `test_item_luck_blade.py`
v2.345.0 magic-items — Luck Blade (RAW DMG p.179, legendary, attunement), Bucket B passive-buff drop-in. Its +1-to-all-saves rides the `save_bonus` substrate (Cloak of Protection / Robe of Stars path). Carrier: Quan Reelstep, seeded inert; tests PATCH equipped+attuned then restore.

| Test | What it asserts |
|------|-----------------|
| `test_luck_blade_grants_save_bonus` | With the blade equipped+attuned, a WIS save breakdown names "Luck Blade" and the summed save bonus rises by exactly 1 over the inert baseline. |
| `test_luck_blade_baseline_has_no_blade_bonus` | Inert (seed state) → no "Luck Blade" in the save breakdown (the +1 is blade-sourced, not baked). |
| `test_luck_blade_requires_attunement` | Equipped-but-unattuned → no blade bonus (attunement gate). |

### `test_armorys_remainder.py`
v2.344.0 magic-items — "The Armory's Remainder" bulk-stub push. The last 12 mechanically-rich SRD items (Bead of Force, Berserker Axe, Hammer of Thunderbolts, Oathbow, Pipes of Haunting, Sword of Wounding, Trident of Fish Command, and the charged staves) shipped as catalog-stub passives, each flagged for future dedicated wiring. Seeded as inert spare loot across 8 thematic carriers via the v2.344.0 block in `_vault_loot`. Closes the discrete-collectible magic-item content tail.

| Test | What it asserts |
|------|-----------------|
| `test_armorys_remainder_seeded[<carrier>]` | The named carrier's `/sheet-json` inventory contains every remainder stub slug seeded on them (8 parametrized cases covering all 12 items). |

### `test_dagger_of_venom.py`
v2.343.0 magic-items — Dagger of Venom (RAW DMG p.161, rare, NO attunement). First on_hit_save item to use the new `effect: "damage_condition"` variant — DC 15 CON save or 2d10 poison + poisoned (save negates both). Carrier: Pip Quickfingers at `attack_index 5`, equipped. Bandit-template targets roll the NPC save inline.

| Test | What it asserts |
|------|-----------------|
| `test_dagger_of_venom_save_fires_on_hit` | A hit vs a Bandit → `feature_used` with `source: "item-dagger-of-venom-save"`, `dc: 15`, `ability: "CON"`. |
| `test_dagger_of_venom_poisons_on_failed_save` | Sweep seeds until the Bandit fails the save → the `poisoned` buff is installed on the target AND its HP dropped below full (both halves of `damage_condition`). |

### `test_sword_of_life_stealing.py`
v2.318.0 magic-items — Sword of Life Stealing +3d6 necrotic on natural 20 (RAW DMG p.206, rare, attunement). Third item on the `on_nat_20` `effect: "damage"` branch (Sharpness precedent), and the first to compose `exempt_creature_types` with a damage rider (Vorpal uses the same list with `effect: "decap"`). Construct and undead targets are exempt; the dispatcher short-circuits before rolling the rider dice. Demo fixture: Pip Quickfingers carries it at `attack_index 3` + inventory tail; **v2.318.1** reseated as inert spare loot — tests PATCH equipped+attuned via `/sheet-fields` (bypassing the `/attune` 3-item cap) then restore. The RAW temp-HP-equal-to-extra-damage clause is GM-narrated in v1.

| Test | What it asserts |
|------|-----------------|
| `test_life_stealing_no_rider_on_construct` | Iterates seeds 0-199 to land d20=20 on a `creature_type: "construct"` target; asserts the `item-sword-of-life-stealing-nat20` broadcast did NOT fire (first exempt slot). |
| `test_life_stealing_no_rider_on_undead` | Iterates seeds 0-199 to land d20=20 on a `creature_type: "undead"` target; asserts the broadcast did NOT fire (second exempt slot). |
| `test_life_stealing_nat_20_extra_damage` | Iterates seeds 0-199 finding one that lands d20=20 vs. a humanoid; asserts `feature_used` with `source: "item-sword-of-life-stealing-nat20"` fires and `hp_dealt` is in [3, 18] (3d6 range). |

### `test_mace_of_smiting.py`
v2.341.0 magic-items — Mace of Smiting (RAW DMG p.179, rare, NO attunement). First on_nat_20 `effect: "damage"` item to use `bonus_dice_vs`: nat-20 → +2d6 bludgeoning, +4d6 vs a construct. Carrier: Brother Tavik Stonebrow at `attack_index 4`, equipped. The construct/humanoid distinction is verified statistically across a seed sweep.

| Test | What it asserts |
|------|-----------------|
| `test_mace_of_smiting_bonus_vs_construct` | Sweep seeds; the construct nat-20 `hp_dealt` MAX exceeds 12 (impossible with only 2d6 → proves the +2d6 construct bonus); all samples in [4, 24]. |
| `test_mace_of_smiting_base_only_vs_humanoid` | Sweep seeds; every humanoid nat-20 `hp_dealt` is in [2, 12] (no construct bonus leak). |

### `test_dwarven_thrower.py`
v2.339.0 magic-items — Dwarven Thrower (RAW DMG p.166, very rare, attunement by a dwarf). First rider to use `bonus_dice_vs`: an unconditional base +1d8 bludgeoning + an extra +1d8 vs a giant. Carrier: Brother Tavik Stonebrow (Hill Dwarf) at `attack_index 3`, seeded inert (PATCH-in-test). Base source `item-dwarven-thrower`; giant-bonus source `item-dwarven-thrower-bonus`.

| Test | What it asserts |
|------|-----------------|
| `test_dwarven_thrower_base_and_giant_bonus` | Vs a Hill Giant → both `item-dwarven-thrower` (1d8) AND `item-dwarven-thrower-bonus` (1d8) uplifts fire (RAW +2d8). |
| `test_dwarven_thrower_base_only_vs_humanoid` | Vs a humanoid → only the base `item-dwarven-thrower` (1d8); no `-bonus`. |
| `test_dwarven_thrower_suppressed_when_detuned` | Equipped-but-detuned → neither rider fires (attunement gate). |

### `test_giant_slayer.py`
v2.338.0 magic-items — Giant Slayer (RAW DMG p.171, rare, NO attunement). Composes the v2.158.93 conditional damage rider (+2d6 weapon-type vs giant) + the v2.158.102 on_hit_save (DC 15 STR or prone — the new `effect: "prone"` variant), both gated on the same giant condition. Carrier: Rowan Quickbow at `attack_index 3`, equipped (no attunement). Hill Giant template target gives the NPC save an inline roll.

| Test | What it asserts |
|------|-----------------|
| `test_giant_slayer_fires_on_giant` | Attack a Hill Giant → `auto_uplifts` carries `source: "item-giant-slayer"`, `expression: "2d6"`, `damage_type: "piercing"` (weapon fallback); a `feature_used` with `source: "item-giant-slayer-save"` (DC 15 STR) fires. |
| `test_giant_slayer_silent_on_humanoid` | Vs. a humanoid Bandit → no `item-giant-slayer` uplift AND no `item-giant-slayer-save` feature_used (condition predicate blocks both). |

### `test_nine_lives_stealer.py`
v2.335.0 magic-items — Nine Lives Stealer (RAW DMG p.183, very rare, attunement). The first `on_nat_20` `effect: "slay_save"` item: nat-20 vs a creature with < 100 HP → DC 15 CON save or slain instantly (constructs/undead exempt). Composes the nat-20 gate + `exempt_creature_types` + `_resolve_feature_save` + a new `max_target_hp` gate. Carrier: Pip Quickfingers at `attack_index 4`, seeded inert (PATCH-in-test). The slay broadcast (`item-nine-lives-stealer-nat20`) fires only on a failed save.

| Test | What it asserts |
|------|-----------------|
| `test_nine_lives_slays_on_nat_20_failed_save` | Iterates seeds 0-399; PATCH equipped+attuned, attack a 60-HP bandit until a nat-20 + failed DC 15 CON save lands → the `item-nine-lives-stealer-nat20` slay broadcast fires (feature_name contains "Nine Lives Stealer"). |
| `test_nine_lives_no_slay_on_construct` | Nat-20 vs a `creature_type: "construct"` (60 HP) → no slay broadcast (exempt gate short-circuits before the save). |
| `test_nine_lives_no_slay_above_hp_gate` | Nat-20 vs a 200-HP humanoid → no slay broadcast (the <100-HP `max_target_hp` gate blocks it). |

### `test_mace_of_disruption.py`
v2.319.0 magic-items — Mace of Disruption (RAW DMG p.179, rare, attunement). Sun Blade-shape conditional rider with TWO creature types in the predicate (fiend OR undead) — first multi-type conditional rider in the catalog. +2d6 radiant on hit when the target is a fiend or undead. Carrier: Brother Tavik Stonebrow at `attack_index 2` + inventory tail, seeded inert (v2.318.1 spare-loot pattern). The "destroy if HP ≤ 25" + fear-save-on-pass RAW clauses are GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_mace_fires_on_fiend_target` | PATCH equipped+attuned; attack a `creature_type: "fiend"` Quasit → `auto_uplifts` carries one entry with `source: "item-mace-of-disruption"`, `expression: "2d6"`, `damage_type: "radiant"`, `total` in [2, 24] (crit-doubled). |
| `test_mace_fires_on_undead_target` | Same shape vs. a `creature_type: "undead"` Skeleton — proves the lambda's `in (...)` membership check, not a single-type equality. |
| `test_mace_silent_on_humanoid` | Vs. a humanoid Bandit → no `item-mace-of-disruption` uplift in `auto_uplifts`. |

### `test_holy_avenger_rider.py`
v2.322.0 magic-items — Holy Avenger (RAW DMG p.174, legendary, attunement, "any sword"). Pure substrate clone of v2.319.0 Mace of Disruption — same fiend-OR-undead predicate, +2d10 radiant (vs. Mace's 2d6) per RAW. Carrier: Sir Caelan Lightbringer at `attack_index 3` + inventory tail, seeded inert (v2.318.1 spare-loot pattern). The +3 attack/damage half lives on the seeded attack row; the save-advantage aura is GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_holy_avenger_fires_on_fiend_target` | PATCH equipped+attuned; attack a `creature_type: "fiend"` Quasit → `auto_uplifts` carries one entry with `source: "item-holy-avenger"`, `expression: "2d10"`, `damage_type: "radiant"`, `total` in [2, 40] (crit-doubled). |
| `test_holy_avenger_fires_on_undead_target` | Same shape vs. a `creature_type: "undead"` Skeleton — proves the lambda's `in (...)` membership check. |
| `test_holy_avenger_silent_on_humanoid` | Vs. a humanoid Bandit → no `item-holy-avenger` uplift in `auto_uplifts`. |

### `test_item_hat_of_disguise.py`
v2.321.0 magic-items — Hat of Disguise (RAW DMG p.173, rare, attunement). New `disguise_self_at_will` boolean derived flag substrate (the at-will-casting analogue of `levitate_at_will`). Carrier: Lyra Sunstrider as inert spare loot; PATCH-then-restore via `/sheet-fields` (bypasses the `/attune` 3-item cap).

| Test | What it asserts |
|------|-----------------|
| `test_hat_equipped_exposes_flag` | PATCH equipped+attuned → `derived.disguise_self_at_will` present with the hat in `sources`. |
| `test_hat_detune_drops_flag` | Equipped+attuned exposes the flag → re-PATCH detuned drops the flag (attunement gate). |
| `test_hat_baseline_has_no_flag` | Inert-seed baseline: no other Lyra item sets the flag, so `derived.disguise_self_at_will` is absent. |
| `test_hat_unequip_drops_flag` | Attuned-but-unequipped drops the flag — requires_attunement payload needs BOTH equipped AND attuned. |

### `test_vicious_weapon.py`
v2.320.0 magic-items — Vicious Weapon (RAW DMG p.209, rare, NO attunement). First `on_nat_20` item to (a) `requires_attunement: False` (the dispatcher's wielder check skips the equipped/attuned gate — slug match alone fires) and (b) omit `damage_type` from its catalog row (the dispatcher falls back to the attack's own weapon type — "slashing" for Krieger's Greataxe, "bludgeoning" for a future Vicious Mace, etc.). Demo: Krieger Stonefist (Half-Orc Barbarian) at `attack_index 2`, equipped Vicious Greataxe.

| Test | What it asserts |
|------|-----------------|
| `test_vicious_nat_20_extra_damage` | Iterates seeds 0-199 finding one that lands d20=20 on Krieger's first Vicious Greataxe swing; asserts `feature_used` with `source: "item-vicious-weapon-nat20"` fires, `damage_type: "slashing"` (the weapon-type fallback, NOT declared on the catalog row), and `hp_dealt` in [2, 12] (2d6 range). |
| `test_vicious_slug_gate_blocks_vanilla_greataxe` | Nat 20 on Krieger's vanilla Greataxe (`attack_index 0`, no `_slug`) → no Vicious Weapon broadcast (slug gate). |
| `test_vicious_no_attunement_required` | /sheet-json carries the vicious-weapon item with `equipped: True` and NO `attuned: True` field — matches the RAW no-attunement contract. |

### `test_demon_slayer_frighten.py`
v2.158.102 magic-items-automation Phase 7b — Demon Slayer DC 15 WIS save-or-frightened on every fiend hit (RAW DMG p.166). Second post-hit hook type via `on_hit_save: {dc, ability, effect, duration_rounds}` catalog field. New helper `_apply_magic_item_on_hit_save_effect` delegates to v2.99.406 `_resolve_feature_save` which auto-rolls NPC saves + installs frightened buff on failure. New Quasit (CR 1 fiend) NPC template (`sheet.type='fiend'`) provides the test fiend target.

| Test | What it asserts |
|------|-----------------|
| `test_demon_slayer_frighten_save_broadcast_on_fiend` | Lyra hits a Quasit (template-resolved fiend) → save resolved server-side. If the save failed, the Quasit carries a `frightened` buff with `source` containing `demon-slayer`. |
| `test_demon_slayer_no_save_on_humanoid` | Humanoid target → no save attempted; Bandit doesn't acquire frightened. |
| `test_demon_slayer_save_suppressed_when_detuned` | Detune Lyra's Demon Slayer → no save, no frightened buff installed even vs. Quasit. Re-attunes in teardown. |

### `test_vorpal_decap.py`
v2.158.101 magic-items-automation Phase 7a — first post-hit hook in the rider substrate (Vorpal Sword nat-20 decapitation, RAW DMG p.209). Catalog row `vorpal-sword` uses a new `on_nat_20` field declaring `{effect: "decap", exempt_creature_types: [construct, ooze, plant]}`. New helper `_apply_magic_item_nat_20_effect` re-parses the raw d20 from breakdown (not the v2.49.231 Improved Critical threshold), verifies attunement, resolves target.creature_type via the v2.97.48 helper, and applies `damage_amount=current_hp` for instant kill. Mira Greenleaf gets the Vorpal Scimitar (attack_index 3, inventory_index 8, +9/1d6+6 — RAW +3 baked in).

| Test | What it asserts |
|------|-----------------|
| `test_vorpal_no_decap_on_construct` | Target `creature_type: "construct"` is on the exempt list; decap broadcast doesn't fire even on a potential d20=20. |
| `test_vorpal_no_decap_when_detuned` | /attune detune → decap doesn't fire even on a nat 20. Re-attunes in teardown. |
| `test_vorpal_decap_on_nat_20` | Iterates dice seeds 0-199 until one lands d20=20 on Mira's first attack; asserts the `feature_used` broadcast with `source: "item-vorpal-sword-nat20"` fires and the label contains "Vorpal." Resets dice seed to entropy mode in cleanup. |

### `test_demo_dragon_spawn.py`
v2.158.99 magic-items-automation Phase 6c — Drakkasha (Young Red Dragon) is spawned on the Tavern Brawl map by default + added to the pre-rolled init (token_idx 13, init 10, hp 178). Caelan's Dragon Slayer +3d6 fires automatically when he attacks her, no test plumbing needed. Encounter description gains a one-line dragon-crashes-in beat. CR 10 vs. Lv 5-9 PCs is intentionally unbalanced — this is a showcase.

| Test | What it asserts |
|------|-----------------|
| `test_yrd_token_present_in_tavern_brawl` | GETs `/encounters`, finds Tavern Brawl, asserts payload.tokens contains a Drakkasha entry with `size=2` (Large) and `team=villain`. |
| `test_yrd_combatant_in_battle_state` | Asserts payload.battle_state.combatants contains Drakkasha at `hp_max=178` with `token_template_id` set so the Phase 5f resolver can fire the rider. |

### `test_demo_adult_red_dragon_template.py`
v2.160.1 legendary-actions Phase 1c demo fixture — the Adult Red Dragon (CR 17, legendary) is a drag-spawnable template so the v2.160.0 init-tracker legendary strip has a real legendary creature to render on (the demo's Young Red Dragon is non-legendary RAW). Not placed on the map by default; the GM drag-spawns it from the Templates tab.

| Test | What it asserts |
|------|-----------------|
| `test_adult_red_dragon_template_seeded` | GETs `/templates`, finds "Adult Red Dragon", asserts `sheet.monster_slug == "adult-red-dragon"` (so its 3 legendary actions project) and `sheet.type == "dragon"`. |
| `test_adult_red_dragon_sheet_page_renders` | Looks up the template id, GETs `/monster-template/{id}/sheet`, asserts 200 + "Adult Red Dragon" in the body — smoke that the slug resolves end-to-end via `_monster_template_to_sheet`. |

### `test_dragon_slayer_template.py`
v2.158.98 magic-items-automation Phase 6b — Young Red Dragon NPC token template carries `sheet.type: "dragon"`, exercising the third branch of the v2.97.48 `_attacker_creature_type` helper (`token_template.sheet["type"]`). Validates the path a demo GM hits when they drag-spawn the dragon from the Templates drawer and Caelan attacks the resulting token. The dragon isn't on the demo map by default (CR 10 vs. Lv 5-9 PCs would steamroll the Tavern Brawl); harness GETs `/templates` to look up the id.

| Test | What it asserts |
|------|-----------------|
| `test_dragon_slayer_fires_via_template_type` | Looks up the Young Red Dragon template id; PUTs a battle with a combatant referencing it via `token_template_id` and NO `creature_type` on the combatant dict; POSTs /attack with Caelan's Dragon Slayer → rider fires via template-resolution. |

### `test_dragon_slayer_helper.py`
v2.158.96 magic-items-automation Phase 5f — the Dragon Slayer rider's `condition` predicate is now wrapped by a resolver shim: if the target combatant dict lacks `creature_type`, the v2.97.48 `_attacker_creature_type` helper resolves it from `character.sheet["creature_type"]` (PC) or `token_template.sheet["type"]` (NPC). `creature_type` added to `_SHEET_PATCH_KEYS` so tests can PATCH a PC sheet to inject the value.

| Test | What it asserts |
|------|-----------------|
| `test_dragon_slayer_fires_via_helper_resolution` | Fixture PATCHes Tavik's sheet to `creature_type: "dragon"`. Battle is seeded with Tavik as the target combatant WITHOUT `creature_type` set on the combatant dict. Caelan's Dragon Slayer attack → rider fires (helper resolved). Teardown clears via `creature_type: ""`. |
| `test_dragon_slayer_no_rider_when_pc_not_dragon` | Tavik's sheet doesn't carry `creature_type` (demo default). Battle seeded same way → rider stays silent. Regression net for the resolver shim. |

### `test_flame_tongue_ignite.py`
v2.158.92 magic-items-automation Phase 5b — Flame Tongue ignite/extinguish toggle via `/use_item_action`. Adds a per-item `_lit` boolean field on the inventory entry (persistent across rests + sessions, unlike combatant buffs). The Phase 5a rider gate gains a `requires_lit` check so the rider only fires while `_lit: True`. Two new action_keys (`ignite` / `extinguish`) flip the state; Garrik's seed ships `_lit: True` so the Phase 5a tests + out-of-the-box demo still fire the rider.

| Test | What it asserts |
|------|-----------------|
| `test_extinguish_then_attack_has_no_rider` | Extinguish → 200 + `lit: false` + the next attack has no `item-flame-tongue` uplift. Re-ignites in teardown. |
| `test_reignite_restores_rider` | Extinguish → no rider → ignite → 200 + `lit: true` → attack restores rider. Verifies bidirectional toggle. |
| `test_ignite_when_already_lit_returns_409` | Ignite a lit Flame Tongue → 409 `no_state_change` with `current: true`. Seed default is lit. |
| `test_extinguish_twice_409_on_second` | First extinguish 200; second extinguish 409 `no_state_change` with `current: false`. Re-ignites in teardown. |
| `test_unknown_action_key_404` | `cast-fireball` action_key on flame-tongue → 404 (multi-action dispatch guard from v2.158.88). |

### `test_flame_tongue_rider.py`
v2.158.91 magic-items-automation Phase 5a — Flame Tongue Longsword (RAW DMG p.170). First on-hit rider weapon: no `/use_item_action` call, the rider fires from `_compute_attack_auto_uplifts` via the new `_MAGIC_ITEM_ATTACK_RIDERS` catalog. Garrik's seed gets the longsword (attack_index 3, inventory_index 7, equipped + attuned). The rider double-gates on `attack._slug == "flame-tongue"` AND the matching inventory item being equipped + attuned, so swapping weapons or detuning suppresses the rider without removing the attack entry.

| Test | What it asserts |
|------|-----------------|
| `test_flame_tongue_fires_2d6_fire_on_hit` | Attacking with Flame Tongue at attack_index 3 surfaces an `auto_uplifts` entry with `source: "item-flame-tongue"`, `damage_type: "fire"`, `expression: "2d6"`, total in [2, 24] (covering crit-doubled 4d6). WS broadcast carries the same. |
| `test_flame_tongue_suppressed_when_detuned` | /attune detune of inventory_index 7 → next attack has no `item-flame-tongue` uplift. Restores attunement in teardown. |
| `test_non_magic_weapon_has_no_rider` | Attacking with Garrik's Greatsword (attack_index 0, no `_slug` match) → no rider despite Flame Tongue still equipped+attuned. Regression catch for any future leak where the rider follows the wielder instead of the swung weapon. |

### `test_use_item_action_staff_of_healing.py`
v2.158.88 magic-items-automation Phase 4d — Staff of Healing (RAW DMG p.202). First multi-action item in the catalog: 3 distinct `action_keys` (`cast-cure-wounds` 1-4 charges → Lv 1-4, `cast-lesser-restoration` fixed 2 charges, `cast-mass-cure-wounds` fixed 5 charges). New `actions` sub-map shape in `_MAGIC_ITEM_ACTIONS` lets the dispatch look up per-action min/max charges + spell slug + base slot level without coupling the per-item handler to a single action. Tavik gets the staff in his seed (attuned alongside Ring of Protection → 2 attuned, well under the cap) + a `staff-of-healing` resource row with `charge_recovery: "1d6+4"`.

| Test | What it asserts |
|------|-----------------|
| `test_staff_cure_wounds_single_charge` | `cast-cure-wounds` with 1 charge → `cast_slot_level: 1`. |
| `test_staff_cure_wounds_max_charges` | 4 charges → `cast_slot_level: 4` (upcast max). |
| `test_staff_cure_wounds_over_max_400` | 5 charges to `cast-cure-wounds` → 400 (RAW: this action caps at 4). |
| `test_staff_lesser_restoration_fixed_2` | `cast-lesser-restoration` with 2 charges → 200, `cast_slot_level: 2`. |
| `test_staff_lesser_restoration_wrong_charges_400` | 3 charges to `cast-lesser-restoration` → 400 (RAW fixed at 2). |
| `test_staff_mass_cure_wounds_lv5` | `cast-mass-cure-wounds` with 5 charges → `cast_slot_level: 5`. |
| `test_staff_unknown_action_404` | `cast-fireball` action_key on a Staff of Healing → 404 (catalog mismatch). Tests the multi-action sub-dispatch validation. |

### `test_use_item_action_potion_of_heroism.py`
v2.184.0 magic-items-automation — first "self-buff" item action. Potion of Heroism (RAW DMG p.187, rare consumable): `/use_item_action` with `action_key: "drink"` grants the DRINKER 10 temp HP + Bless (no concentration) for 1 hour, then consumes the potion. New archetype bits: `consumable: True` (dispatch skips the equipped gate + decrements qty) and a `self_buff` config (flat temp-HP grant + Bless installed on the drinker's own combatant, best-effort). Demo: Garrik Ironside carries the potion; the fixture snapshots + restores his inventory so the consume doesn't deplete the seed across re-runs.

| Test | What it asserts |
|------|-----------------|
| `test_drink_potion_of_heroism_grants_temp_hp_and_consumes` | 200 + `temp_hp_granted: 10`, `temp_hp >= 10` (non-stacking max), `consumed: True`, `buff_key: "bless"`, `buff_installed` is a bool. WS `character_hp_update.data.hp.temp >= 10`. Sheet reflects the temp HP and the potion row is gone (qty 1 → removed). |
| `test_drink_potion_of_heroism_unknown_action_404` | `action_key: "quaff"` (item defines only `drink`) → 404; potion untouched. |
| `test_use_item_action_missing_fields_400` | Omitting `action_key` → 400 (contract guard). |

### `test_use_item_action_potion_of_speed.py`
v2.185.0 — second self-buff consumable through the generic `_use_item_action_self_buff_potion` handler. Potion of Speed (RAW DMG p.187, very rare): `drink` → the Haste buff (best-effort install) for 1 minute, no concentration, NO temp HP. Exercises the no-temp-HP branch (handler skips the temp-HP grant + the HP broadcast). Garrik carries one alongside his Potion of Heroism; the fixture snapshots + restores his inventory.

| Test | What it asserts |
|------|-----------------|
| `test_drink_potion_of_speed_grants_haste_and_consumes` | 200 + `buff_key: "haste"`, `temp_hp_granted: 0`, `consumed: True`, `buff_installed` is a bool. WS `feature_used.data.summary` names the Haste effect. Sheet: temp HP unchanged, potion row removed. |
| `test_drink_potion_of_speed_unknown_action_404` | `action_key: "quaff"` → 404; potion untouched. |

### `test_use_item_action_potion_of_resistance.py`
v2.186.0 — third self-buff consumable through the generic `_use_item_action_self_buff_potion` handler. Potion of Resistance (RAW DMG p.188, uncommon), fire instance: `drink` → the `resistance-fire` buff (`effects.resistance_to: ["fire"]`) for 1 hour, no concentration, no temp HP. First self-buff with a **mechanically enforced** effect (the live `_resistance_halve` damage pipeline reads `resistance_to`), vs. Heroism/Speed's display markers. Garrik carries one; the fixture snapshots + restores his inventory.

| Test | What it asserts |
|------|-----------------|
| `test_drink_potion_of_resistance_grants_buff_and_consumes` | 200 + `item_name: "Potion of Fire Resistance"`, `buff_key: "resistance-fire"`, `temp_hp_granted: 0`, `consumed: True`, `buff_installed` is a bool. WS `feature_used.data.summary` names the fire resistance. Sheet: temp HP unchanged, potion row removed. |
| `test_drink_in_battle_installs_enforced_fire_resistance` | In an active battle: `buff_installed: True` AND the installed buff in `GET /character/{id}/buffs` carries `effects.resistance_to` containing `"fire"` — proving the enforced (non-marker) effect lands. |
| `test_drink_potion_of_resistance_unknown_action_404` | `action_key: "quaff"` → 404; potion untouched. |

### `test_potion_of_resistance_damage_halving.py`
v2.186.1 — end-to-end proof that the fire-resistance buff actually halves incoming fire damage through the live pipeline (not just that it installs). Chain: drink in battle → `_install_buff` + `_mirror_buffs_to_sheet` write `resistance-fire` (with `effects.resistance_to: ["fire"]`) onto the sheet `_buffs_active` → a typed-damage `PATCH .../sheet-fields` runs `_resistance_halve`, which reads the mirror. Deterministic (no dice).

| Test | What it asserts |
|------|-----------------|
| `test_fire_damage_is_halved` | After drinking, 20 fire damage drops Garrik's HP by exactly 10 (halved before HP application). |
| `test_cold_damage_is_not_halved` | Control: 20 cold damage drops HP by the full 20 — proving the buff is type-specific (the fire instance, not a `["all"]` wildcard). |

### `test_potion_of_resistance_type_pick.py`
v2.187.0 — proof that the Potion of Resistance is type-aware: the RAW GM-chosen damage type is carried on the inventory item (`resistance_type`) and the handler maps it to the matching `resistance-<type>` template. Garrik carries a second typed instance (Potion of Cold Resistance); this file drinks it in battle and proves the live damage pipeline halves COLD but not FIRE — the mirror image of `test_potion_of_resistance_damage_halving.py`.

| Test | What it asserts |
|------|-----------------|
| `test_cold_damage_is_halved` | After drinking Cold Resistance (`buff_key: "resistance-cold"`, item_name "Potion of Cold Resistance"), 20 cold damage drops Garrik's HP by exactly 10. |
| `test_fire_damage_is_not_halved` | Control: 20 fire damage drops HP by the full 20 — proving the type-pick selected cold, not fire. |

### `test_potion_of_resistance_drink_time_pick.py`
v2.188.0 — drink-time damage-type pick for a GENERIC (untyped) Potion of Resistance. RAW the drinker chooses the type, so a potion seeded without a `resistance_type` accepts a `resistance_type` override in the `/use_item_action` body. The handler resolves the override to the matching `resistance-<type>` template. Garrik carries a generic potion alongside his pre-typed fire + cold instances; this file drinks it choosing lightning and proves the live pipeline halves lightning but not fire.

| Test | What it asserts |
|------|-----------------|
| `test_chosen_lightning_is_halved` | Drink the generic potion with `resistance_type: "lightning"` (`buff_key: "resistance-lightning"`), then 20 lightning damage drops HP by exactly 10. |
| `test_unchosen_fire_is_not_halved` | Control: 20 fire damage drops HP by the full 20 — proving the drink-time pick was lightning, not fire. |

### `test_potion_of_invulnerability.py`
v2.190.0 — Potion of Invulnerability (RAW DMG p.188, rare): the fourth self-buff potion. Drinking installs the `resistance-all` template whose `effects.resistance_to: ["all"]` wildcard `_resistance_halve` already honours, so EVERY damage type is halved for 1 minute (no concentration). Garrik drinks his seeded potion in an active battle; the file proves two unrelated types are both halved from the single wildcard.

| Test | What it asserts |
|------|-----------------|
| `test_fire_is_halved` | Drink in battle (`buff_key: "resistance-all"`, `buff_installed: True`), then 20 fire damage drops HP by exactly 10. |
| `test_necrotic_is_also_halved` | A different type from the same wildcard: 20 necrotic also drops HP by 10 — distinguishes Invulnerability (all types) from Potion of Resistance (one chosen type). |

### `test_potion_of_fire_breath.py`
v2.193.0 — Potion of Fire Breath (RAW DMG p.187, uncommon): the first OFFENSIVE consumable. Drinking exhales fire at the area — each target makes a DC 13 DEX save, 4d6 fire, half on a success — and the potion is consumed. Reuses the Necklace of Fireballs per-target save loop (`_resolve_feature_save` → roll → `_apply_damage_to_combatant`) but consumes the potion instead of decrementing a charge resource. Garrik exhales at NPC bandits in an active battle.

| Test | What it asserts |
|------|-----------------|
| `test_fire_breath_exhales_and_consumes` | `breathe` at two bandits → 200, `save_dc: 13`, `save_ability: "DEX"`, `dice: "4d6"`, `consumed: True`, `remaining_qty: 0`; results carry both target ids with `passed`/`damage_dealt` keys; a `feature_used` broadcast (`source: item-potion-of-fire-breath`) fires. (Damage isn't asserted — bare NPC tokens defer the save, matching the Necklace/Javelin tests.) |
| `test_fire_breath_bad_action_key_404` | Error path: a `drink` action_key (Fire Breath only exposes `breathe`) → 404. |

### `test_potion_of_mind_reading.py`
v2.197.0 — Potion of Mind Reading (RAW DMG p.187, rare): the second save-imposing consumable. Drinking probes a creature's mind — the target makes a DC 13 WIS save; on a failure you read its surface thoughts — and the potion is consumed. Reuses the Fire Breath per-target save loop (`_resolve_feature_save`) without the damage roll (no HP changes; the thought-reading is GM-narrated). Garrik probes an NPC bandit in an active battle.

| Test | What it asserts |
|------|-----------------|
| `test_mind_reading_probes_and_consumes` | `read` at a bandit → 200, `save_dc: 13`, `save_ability: "WIS"`, `consumed: True`, `remaining_qty: 0`; results carry the target id with a `passed` key; a `feature_used` broadcast (`source: item-potion-of-mind-reading`) fires. (Save outcome isn't asserted — bare NPC tokens defer the save.) |
| `test_mind_reading_bad_action_key_404` | Error path: a `drink` action_key (Mind Reading only exposes `read`) → 404. |

### `test_potion_of_growth.py`
v2.192.0 — Potion of Growth (RAW DMG p.187, uncommon): the fifth self-buff potion. Drinking installs the `growth` template carrying `effects.advantage_on: ["str_check", "str_save"]`. v2.192.0 generalized the STR-advantage readers (rage-only until now) so any marker-bearing buff composes. Mirrors `test_rage_str_save.py`: Thalindra casts Gust of Wind (STR save) at Garrik; the save-roll swaps `1d20 → 2d20kh1` when the target has STR-save advantage. Garrik (Fighter) has no innate STR-save advantage, so Growth is the sole source — a clean control.

| Test | What it asserts |
|------|-----------------|
| `test_growth_grants_advantage_on_str_save` | Garrik drinks Growth (`buff_key: "growth"`, `buff_installed: True`), then a STR-save spell aimed at him produces a `roll_request` with `base_expression == "2d20kh1"` (advantage). |
| `test_no_growth_str_save_is_plain` | Control: without Growth, Garrik's STR save rolls plain `1d20` — proving the advantage comes from the potion, not something innate. |

### `test_potion_of_giant_strength.py`
v2.217.0 — ability-score override engine Phase 4 (docs/plans/str-override.md): the TIMED half of the substrate. Potion of Giant Strength (RAW DMG p.187): drink → STR becomes a giant's value for 1 hour, RAW max(base, set). Installs a timed `giant-strength` buff carrying `effects.ability_set`; mirrored onto the sheet as `_buffs_active`, the new fold in `_equipped_item_effects` reads it so every override consumer composes the buff with equipped overrides. The drink needs an active battle (best-effort install), so the fixture stands up a one-combatant battle, then clears the mirrored buff + restores the consumed potion on teardown. Thalindra (Wizard Lv 7, base STR 8 → mod -1, 120 lb cap) carries a Potion of Hill Giant Strength (`_ability_set {STR: 21}`) — no equipped STR override, a clean control.

| Test | What it asserts |
|------|-----------------|
| `test_giant_strength_potion_sets_str_on_sheet_json` | Drink (`buff_key: "giant-strength"`, `buff_installed: True`), then `GET /sheet-json` → `derived.effective_abilities.STR` = `{base 8, effective 21, modifier 5}` with source naming "Giant Strength". |
| `test_giant_strength_potion_raises_carry_capacity` | Carry capacity 120 lb (8 × 15) before drink → 315 lb (21 × 15) after — the timed STR flows into the carry engine for free. |
| `test_giant_strength_potion_adds_str_save_override_delta` | After drinking, a `/roll` `str_save` breakdown contains "+6" and "Giant Strength" (mod +5 − base mod -1 = +6 delta, attributed to the potion). |

### `test_potion_of_climbing.py`
v2.195.0 — Potion of Climbing (RAW DMG p.187, common): the sixth self-buff potion. Drinking installs the `climbing` template carrying `effects.advantage_on: ["str_check"]`, honoured by the generalized STR-check-advantage reader. Exercises the STR-*check* path via the `/roll` endpoint (`stat_key="str_check"`): the d20 expression swaps `1d20 → 2d20kh1` when the roller has STR-check advantage. Garrik (Fighter) has no innate STR-check advantage, so Climbing is the sole source. The climbing speed itself is GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_climbing_grants_advantage_on_str_check` | Garrik drinks Climbing (`buff_key: "climbing"`, `buff_installed: True`), then a `/roll` STR check broadcasts a `roll` with `expression == "2d20kh1"` (advantage). |
| `test_no_climbing_str_check_is_plain` | Control: without Climbing, Garrik's STR check rolls plain `1d20` — proving the advantage comes from the potion, not something innate. |

### `test_potion_of_water_breathing.py`
v2.196.0 — Potion of Water Breathing (RAW DMG p.188, uncommon): the seventh self-buff potion and the first purely-descriptive one. The `water-breathing` template carries an empty `effects` map (the engine tracks no drowning rule), so the contract worth proving is the install itself. Mirrors `test_self_buff_potion_in_battle.py` — `_install_buff` no-ops outside combat, so the test puts Garrik in an active solo battle first.

| Test | What it asserts |
|------|-----------------|
| `test_water_breathing_installs_buff_in_battle` | In an active battle: 200, `buff_key: "water-breathing"`, `buff_installed: True`, `consumed: True`; `water-breathing` present in the combatant's live buff list. |
| `test_water_breathing_bad_action_key_404` | A non-existent `breathe` action_key on the (single-key `drink`) potion → 404. |

### `test_potion_of_diminution.py`
v2.199.0 — Potion of Diminution (RAW DMG p.187, rare): the eighth self-buff potion and the first DEbuff one — the mirror image of Potion of Growth. Drinking installs the `diminution` template carrying `effects.disadvantage_on: ["str_check", "str_save"]`, honoured by the v2.199.0 STR-check disadvantage intercept in `/roll`. Exercises the STR-*check* path via the `/roll` endpoint (`stat_key="str_check"`): the d20 expression swaps `1d20 → 2d20kl1` when the roller has STR-check disadvantage. Garrik (Fighter) has no innate STR-check (dis)advantage, so the potion is the sole source. The size reduction + -1d4 weapon damage are GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_diminution_imposes_disadvantage_on_str_check` | Garrik drinks Diminution (`buff_key: "diminution"`, `buff_installed: True`), then a `/roll` STR check broadcasts a `roll` with `expression == "2d20kl1"` (disadvantage). |
| `test_no_diminution_str_check_is_plain` | Control: without Diminution, Garrik's STR check rolls plain `1d20` — proving the disadvantage comes from the potion, not something innate. |

### `test_potion_of_invisibility.py`
v2.200.0 — Potion of Invisibility (RAW DMG p.188, very rare): the ninth self-buff potion and the first to carry a *real* combat marker. Drinking installs the `invisibility-potion` template carrying `effects.invisible: True` — the same marker the Monk's Empty Body buff uses and the attack-resolution intercepts already read to grant an invisible attacker advantage, so it composes with zero new reader code. The fixture puts Garrik in an active solo battle first (the install no-ops outside combat) and restores inventory + clears the battle in teardown. The "ends when you attack or cast a spell" nuance is GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_invisibility_installs_buff_with_marker` | Garrik drinks Invisibility (`buff_key: "invisibility-potion"`, `buff_installed: True`, `consumed: True`); the buff lands on his combatant via `GET /buffs` AND carries the `effects.invisible: True` marker the attack code reads. |
| `test_invisibility_bad_action_key_404` | A non-existent action_key (`vanish`) on the potion → 404. |

### `test_potion_of_flying.py`
v2.201.0 — Potion of Flying (RAW DMG p.187, very rare): the tenth self-buff potion. Drinking installs the `flying-potion` template carrying `effects.fly_speed_ft: 30` — the same flight marker the Stormborn / levitate / dragon-wings buffs use to surface flying capability for the UI/GM on the 2D map. The fixture puts Garrik in an active solo battle first (install no-ops outside combat) and restores inventory + clears the battle in teardown. Modeled at 30 ft (default walk speed); the falls-when-it-ends nuance is GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_flying_installs_buff_with_fly_speed` | Garrik drinks Flying (`buff_key: "flying-potion"`, `buff_installed: True`, `consumed: True`); the buff lands on his combatant via `GET /buffs` AND carries an `effects.fly_speed_ft > 0` marker. |
| `test_flying_bad_action_key_404` | A non-existent action_key (`soar`) on the potion → 404. |

### `test_potion_of_animal_friendship.py`
v2.202.0 — Potion of Animal Friendship (RAW DMG p.187, uncommon): the second single-target save consumable. Routes through the generalised Mind-Reading WIS-save loop (`_resolve_feature_save`, no damage). Garrik drinks + charms an NPC beast in an active battle; the charm itself, the at-will-for-1-hour duration, and the beast-only restriction are GM-narrated. Bare NPC tokens defer the save rather than auto-rolling it.

| Test | What it asserts |
|------|-----------------|
| `test_animal_friendship_charms_and_consumes` | Garrik drinks + charms a wolf (`action_key: "charm"`): response has `save_dc: 13`, `save_ability: "WIS"`, `consumed: True`, `remaining_qty: 0`, one result for the target with a `passed` key, and a `feature_used` broadcast with `source: "item-potion-of-animal-friendship"`. |
| `test_animal_friendship_bad_action_key_404` | A `drink` action_key (the self-buff potions' key) on a charm-only potion → 404. |

### `test_potion_of_clairvoyance.py`
v2.203.0 — Potion of Clairvoyance (RAW DMG p.187, rare): the eleventh self-buff potion. Like Water Breathing it's a purely descriptive buff — the `clairvoyance-potion` template carries no mechanical effect; it just surfaces on the init strip with a 10-minute duration (the scrying sensor is GM-narrated). The fixture puts Garrik in an active solo battle first (install no-ops outside combat) and restores inventory + clears the battle in teardown.

| Test | What it asserts |
|------|-----------------|
| `test_clairvoyance_installs_buff_in_battle` | Garrik drinks Clairvoyance (`buff_key: "clairvoyance-potion"`, `buff_installed: True`, `consumed: True`); the buff lands on his combatant via `GET /buffs`. |
| `test_clairvoyance_bad_action_key_404` | A non-existent action_key (`scry`) on the potion → 404. |

### `test_potion_of_gaseous_form.py`
v2.204.0 — Potion of Gaseous Form (RAW DMG p.187, rare): the twelfth self-buff potion. Carries a real, composable engine effect — `effects.resistance_to` lists every `nonmagical-<type>` entry the F6 matcher understands (so `_resistance_halve` halves any nonmagical hit while letting magical-source damage through) plus `effects.fly_speed_ft: 10` for the hover. The save advantage and can't-act restriction are GM-narrated. The fixture puts Garrik in an active solo battle first (install no-ops outside combat) and restores inventory + clears the battle in teardown.

| Test | What it asserts |
|------|-----------------|
| `test_gaseous_form_installs_buff_with_markers` | Garrik drinks Gaseous Form (`buff_key: "gaseous-form-potion"`, `buff_installed: True`, `consumed: True`); the buff lands on his combatant via `GET /buffs` carrying `effects.resistance_to` containing `nonmagical-bludgeoning` AND `effects.fly_speed_ft > 0`. |
| `test_gaseous_form_bad_action_key_404` | A non-existent action_key (`vaporize`) on the potion → 404. |

### `test_self_buff_potion_in_battle.py`
v2.185.1 — in-battle proof that `_use_item_action_self_buff_potion` actually installs its buff. The per-potion tests only assert `buff_installed` is a *bool* (the install is best-effort and no-ops outside combat). This file puts Garrik in an active solo battle (`PUT /battle`, `active: True`) FIRST, then drinks each potion and asserts the install succeeded AND the buff key shows up in `GET /character/{id}/buffs`. The fixture snapshots/restores his inventory and clears the battle in teardown.

| Test | What it asserts |
|------|-----------------|
| `test_potion_of_speed_installs_haste_in_battle` | In an active battle: 200, `buff_key: "haste"`, `buff_installed: True`, `consumed: True`; `haste` present in the combatant's live buff list. |
| `test_potion_of_heroism_installs_bless_in_battle` | In an active battle: 200, `buff_key: "bless"`, `buff_installed: True`, `temp_hp_granted: 10`; `bless` present in the combatant's live buff list. |

---

## HP & death-save state machine

### `test_death_save.py`
The dying / stable / dead state machine. Core HP transitions through 0.

| Test | What it asserts |
|------|-----------------|
| `test_drop_to_zero_sets_dying` | Damaging Pip to 0 (with safe magnitude) → death-save POST returns 200 (state is dying). |
| `test_death_save_roll_updates_counters` | POST returns flat `{ok, raw, outcome, status, successes, failures, hp}`; one roll advances either counter. |
| `test_death_save_409_when_alive` | POST on a long-rested alive PC → 409. |
| `test_death_save_override_sets_status` | GM `/death-save/override` force-sets `{status, successes, failures}`. |
| `test_stabilize_endpoint` | `/stabilize` sets status=stable, counters=0. |
| `test_stabilize_forbidden_for_non_gm` | Alice → 403. |
| `test_override_to_alive_bumps_hp_to_1` | Override `status="alive"` from 0-HP-dying → HP bumps to 1 automatically. |

---

## Buffs & concentration

### `test_end_buff.py`
Manual buff removal via `/end_buff`.

| Test | What it asserts |
|------|-----------------|
| `test_end_buff_removes_rage` | Install Rage via `/use_rage`, then `/end_buff` drops it; `/character/{id}/buffs` no longer lists it. |
| `test_end_buff_missing_character_id_400` | 400. |
| `test_end_buff_missing_key_400` | 400. |
| `test_end_buff_unknown_key_idempotent` | Buff not present → idempotent 200 `{ok, removed_key, already_absent: true}` (v2.494.0; no longer 404, so retries don't feed the fail2ban scanner jail). |
| `test_end_buff_unknown_character_404` | Unknown `character_id` still → 404 (bad resource reference, not idempotency). |
| `test_end_buff_non_owner_403` | Alice tries to drop Krieger's buff → 403/404. |

### `test_admin_demo_reset.py`
On-demand demo reseed via `POST /admin/demo/reset` (v2.495.2 actor-after-reseed fix).

| Test | What it asserts |
|------|-----------------|
| `test_admin_demo_reset_succeeds_for_demo_actor` | demo-gm triggers its own wipe+reseed → 200 + counts (campaign stays id 1), not the old 500 from the recreated-actor. |
| `test_admin_demo_reset_forbidden_for_player` | demo-alice (player) → 403. |

### `test_demo_gm_admin_gate.py`
Demo-account site-admin role contract (`DEMO_GM_SITE_ADMIN`, v2.495.0).

| Test | What it asserts |
|------|-----------------|
| `test_demo_gm_reaches_admin_portal` | demo-gm is site-admin by default → `GET /admin` → 200. |
| `test_demo_alice_denied_admin_portal` | demo-alice (player) → `GET /admin` → 403. |
| `test_demo_bob_denied_admin_portal` | demo-bob (player) → `GET /admin` → 403. |

### `test_concentration_buffs.py`
Phase C concentration handling — Hunter's Mark, Hex, swap, concentration-save trigger.

| Test | What it asserts |
|------|-----------------|
| `test_hunters_mark_happy_path` | Ranger Rowan installs HM on target; `cast_hunters_mark` broadcasts a `buff_update`. |
| `test_hunters_mark_wrong_class` | Non-Ranger → 409. |
| `test_hunters_mark_missing_target` | No target → 400. |
| `test_hunters_mark_missing_character_id` | 400. |
| `test_hex_happy_path` | Warlock Magnus installs Hex; same buff-update shape. |
| `test_hex_wrong_class` | Non-Warlock → 409. |
| `test_concentration_swap` | Casting a second concentration spell drops the first (RAW one-at-a-time). |
| `test_concentration_save_on_damage` | Damage event triggers a concentration CON save; failure drops the buff. |

### `test_concentration_drops_on_zero_hp.py`
v2.49.48 — RAW PHB p.203: concentration ends automatically when the caster's HP drops to 0, regardless of CON save outcome. Pre-fix the save could pass at 0 HP and leave a dying/dead PC concentrating on Hex / Hunter's Mark.

| Test | What it asserts |
|------|-----------------|
| `test_concentration_force_drops_at_zero_hp` | Damage that drops Magnus to 0 HP force-drops Hex regardless of d20 outcome. `concentration_save` broadcast carries `forced_drop_on_zero_hp=True` + `passed=False` + `dropped_key="hex"`. |
| `test_concentration_normal_save_when_not_at_zero` | Damage that doesn't drop to 0 still uses the normal save path. `forced_drop_on_zero_hp=False`, `passed` follows the d20 roll. |

### `test_use_stunning_strike.py`
v2.49.55 — Monk class feature `POST /use_stunning_strike`. Lv 5+ + ki >= 1 + a target. Server rolls a CON save for NPC targets (or creates a roll_request for PCs); on fail, installs Stunned (concentration=False, 1-turn duration) via the existing save-or-suck pipeline. First endpoint to install a `concentration: False` incapacitating buff — validates the v2.49.51 hook's non-concentration branch (for PC targets via the roll_request path; NPC validation here verifies the install + buff shape).

| Test | What it asserts |
|------|-----------------|
| `test_stunning_strike_happy_path_npc` | Kael (Monk Lv 5) hits a bandit until the save fails; assert `auto_save_buff_installed=Stunned`, `concentration=False` on the broadcast buff, `source_char_id=Kael`. Retry loop because the d20 is random. |
| `test_stunning_strike_wrong_class` | Krieger (Barbarian) → 409 `wrong_class` with `expected=monk`. |
| `test_stunning_strike_no_ki` | Drain Kael's ki via repeated calls (response carries `ki_remaining`); when 0, next call → 409 `no_ki` with `available=0`. |
| `test_stunning_strike_pc_drops_own_concentration` | v2.49.56 — closes the v2.49.55 filed item. Magnus casts Hex (concentration); Kael uses Stunning Strike on Magnus → roll_request; GM-as-Magnus /responds; on save fail assert (a) Stunned lands on Magnus, (b) Magnus's Hex drops via the v2.49.51 hook's `concentration: False` branch, (c) 💀 GM log naming "stunned" + "incapacitated" fires. Retry loop because the CON save is random. |

### `test_use_metamagic_empowered.py`
v2.49.124-125 — Sorcerer Lv 3+ Empowered Spell metamagic (Phase 1 of the Sorcery Points + Metamagic plan). New endpoint `/use_metamagic_empowered_spell` spends 1 sorcery point + installs a one-cast `metamagic-empowered-pending` buff on the caster carrying `effects.rerolls_available = max(1, CHA-mod)`. The next `/cast_spell` damage roll consumes the buff and rerolls up to that many lowest dice. v2.49.124 wires the save-for-half single-target NPC path; v2.49.125 wires the multi-beam attack-roll path (Scorching Ray, Eldritch Blast, Fire Bolt) with a pool reroll across all beams. Cast payload gains an `empowered_spell` block (`rerolled_count`, `original_total`, `final_total`, `rerolls` list of `{sides, old, new}`). Demo subject: Zara (CHA 17 → +3 mod, 5 SP, knows Fire Bolt / Scorching Ray / Fireball at spell indices 0 / 10 / 11).

| Test | What it asserts |
|------|-----------------|
| `test_empowered_arms_pending_buff` | 1 SP → 200, buff installed on Zara's combatant with `effects.rerolls_available=3` + `effects.metamagic_option="empowered-spell"`. SP decremented to 4. |
| `test_empowered_409_when_no_sorcery_points` | Drain 5 SP via 5 arm calls → 6th returns 409 `not_enough_points` (`required=1`, `have=0`). |
| `test_empowered_wrong_class` | Thalindra (Wizard) → 409 `wrong_class` with `expected="sorcerer"`. |
| `test_empowered_buff_consumed_on_cast_fireball` | Arm Empowered → cast Fireball at a bandit → response `empowered_spell` block present, `rerolled_count==3`, each reroll entry has `sides==6` + `old/new` in 1-6. Buff removed after the cast. |
| `test_empowered_pool_reroll_scorching_ray` | v2.49.126 — true cross-beam Empowered. Arm Empowered → cast Scorching Ray L2 (3 beams of 2d6 = 6-die pool); retry until ≥ 2 beams hit + budget fully fires; assert `rerolled_count==3` (CHA-mod budget fully spent across the pool) + each cast fires 3 beams + at least one beam's `damage_breakdown` carries the `→` annotation. Proves the pool reroll spans beams, not just the first one. |
| `test_scorching_ray_l3_slot_fires_four_beams` | v2.49.127 — RAW upcast: cast Scorching Ray at L3 slot → assert 4 beams (3 base + 1 upcast). Exercises the new `extra_beams_per_slot_above_base` action-schema field. |
| `test_scorching_ray_l2_slot_fires_three_beams` | v2.49.127 control — cast at base L2 slot → assert 3 beams (no upcast bonus). Off-by-one regression guard for the slot-delta math. |
| `test_empowered_single_beam_fire_bolt` | v2.49.125 — attack-roll path. Arm Empowered → cast Fire Bolt (2d10 cantrip); assert `rerolled_count==2` (CHA-mod budget 3 clipped to pool size 2) + all reroll log entries are d10. |
| `test_no_empowered_block_when_buff_absent` | Control: cast Fireball without arming → `empowered_spell` key NOT present in payload (no spurious fire). |

### `test_use_font_of_magic.py`
v2.49.120 — Sorcerer Lv 2+ Font of Magic feature (Phase 0 of the Sorcery Points + Metamagic plan). Two endpoints: `/use_font_of_magic_to_points` (spell slot → sorcery points, gain = slot level) + `/use_font_of_magic_to_slot` (sorcery points → spell slot, cost table L1=2/L2=3/L3=5/L4=6/L5=7). Both bonus actions; L6+ slots not recoverable per RAW. Demo subject: Zara Emberfire (Sorcerer L5).

| Test | What it asserts |
|------|-----------------|
| `test_font_of_magic_l1_slot_to_1_sp` | Sacrifice L1 slot → +1 SP. From a full pool (5/5), the +1 overflow caps; response carries `sp_overflow_lost: 1`. |
| `test_font_of_magic_l3_slot_to_3_sp` | Sacrifice L3 slot → +3 SP (with overflow when starting full). |
| `test_font_of_magic_no_slot_to_sacrifice` | Zara has no L4 slots (Lv 5) → 409 `no_slot`. |
| `test_font_of_magic_2_sp_to_l1_slot` | After sacrificing an L1 slot, spend 2 SP to recover it. |
| `test_font_of_magic_5_sp_to_l3_slot` | After sacrificing an L3 slot, spend the full pool (5 SP) to recover it. |
| `test_font_of_magic_slot_too_high` | L6+ slots → 409 `slot_too_high` with `max_recoverable: 5`. |
| `test_font_of_magic_not_enough_points` | Drain SP to 1, try to recover an L1 slot (cost 2) → 409 `not_enough_points`. |
| `test_font_of_magic_no_used_slot_to_restore` | All L1 slots full → 409 `no_used_slot_to_restore` (the RAW "ephemeral slot creation" edge case is filed). |
| `test_font_of_magic_wrong_class` | Thalindra the Wizard → 409 `wrong_class`. |

### `test_flurry_chip_refund.py`
v2.49.117 — Phase B v2. While `flurry-of-blows-active` is on the attacker, the next two unarmed-strike attacks DON'T burn the action chip; `effects.unarmed_strikes_available` decrements per strike. When it hits 0, the buff drops. Non-unarmed attacks while Flurry active still mark the chip — RAW Flurry grants unarmed strikes only.

| Test | What it asserts |
|------|-----------------|
| `test_unarmed_strike_with_flurry_active_refunds_chip` | Activate Flurry → unarmed strike → action chip stays clear; buff counter ticks 2 → 1. |
| `test_second_unarmed_strike_consumes_flurry` | Two unarmed strikes in succession → buff DROPS after the second (counter hit 0). |
| `test_non_unarmed_attack_with_flurry_active_still_marks_chip` | Quarterstaff attack with Flurry active → chip marked normally; buff counter unchanged. |
| `test_unarmed_strike_without_flurry_marks_chip` | Control / regression guard: unarmed strike WITHOUT Flurry → action chip marked normally. |

### `test_dodging_disadvantage.py`
v2.49.115 — first Phase B effect integration. When a weapon attack targets a combatant with the `patient-defense` buff (`effects.dodging: True`), the d20 attack roll uses disadvantage (`2d20kl1`). Handles the Rage-attacker-vs-Dodging-target cancellation per RAW PHB p.173 (advantage + disadvantage = neither = straight 1d20).

| Test | What it asserts |
|------|-----------------|
| `test_attack_without_dodging_uses_straight_d20` | Control case — no buff, no `2d20kl1` in `attack_breakdown`. Regression guard. |
| `test_attack_against_dodging_target_has_disadvantage` | Kael uses Patient Defense → Krieger's attack against Kael shows `2d20kl1` in the breakdown. |
| `test_rage_attacker_vs_dodging_target_cancels` | Krieger Rages + Kael dodges → straight `1d20` (neither `2d20kh1` nor `2d20kl1` in the breakdown). |

### `test_use_flurry_of_blows.py`
v2.49.114 — Monk class feature `POST /use_flurry_of_blows` (Lv 2+). Spend 1 ki as a bonus action to install the `flurry-of-blows-active` buff (1 round, `effects.unarmed_strikes_available: 2` + `effects.is_flurry: True`). Signals "two unarmed strikes available" for a future Phase B attack-flow integration and the v2.49.57 Open Hand Technique trigger.

| Test | What it asserts |
|------|-----------------|
| `test_flurry_of_blows_happy_path` | Kael → 200, `remaining=4` (was 5), `unarmed_strikes_available=2`. `buff_update` broadcast carries `flurry-of-blows-active` key, `effects.unarmed_strikes_available=2`, `effects.is_flurry=True`, `concentration=False`, `duration_rounds=1`. |
| `test_flurry_of_blows_wrong_class` | Krieger (Barbarian) → 409 `wrong_class` with `expected=monk`. |
| `test_flurry_of_blows_no_ki` | Drain ki via 5 override calls; 6th → 409 `no_ki`. |

### `test_use_patient_defense.py`
v2.49.112 — Monk class feature `POST /use_patient_defense` (Lv 2+). Spend 1 ki as a bonus action to install Dodging (advantage on DEX saves; attackers have disadvantage). Self-buff, no target. Duration 1 round (until start of next turn).

| Test | What it asserts |
|------|-----------------|
| `test_patient_defense_happy_path` | Kael at full ki → POST → 200, `remaining=4` (was 5), `buff_installed=True`. `buff_update` broadcast carries the `patient-defense` key with `concentration=False`, `effects.dodging=True`, `dex_save` in `advantage_on`. |
| `test_patient_defense_wrong_class` | Krieger (Barbarian) → 409 `wrong_class` with `expected=monk`. |
| `test_patient_defense_no_ki` | Drain Kael's ki to 0 via 5 successive override-bypassed calls; 6th call → 409 `no_ki` with `available=0`. |

### `test_use_step_of_the_wind.py`
v2.49.112 — Monk class feature `POST /use_step_of_the_wind` (Lv 2+). Spend 1 ki as a bonus action; takes `mode: "disengage" | "dash"`. Both install a 1-round self-buff with `jump_distance_doubled`; the disengage variant adds `effects.disengage=True`, the dash variant adds `effects.dash=True`.

| Test | What it asserts |
|------|-----------------|
| `test_step_of_the_wind_disengage_mode` | Kael, mode=disengage → 200, `remaining=4`, `buff_installed=True`. `buff_update` broadcast has `step-of-the-wind-disengage` key with `effects.disengage=True` + `effects.jump_distance_doubled=True`, `concentration=False`. |
| `test_step_of_the_wind_dash_mode` | Kael, mode=dash → 200, `mode=dash` in response. `buff_update` broadcast has `step-of-the-wind-dash` key with `effects.dash=True` + `effects.jump_distance_doubled=True`. |
| `test_step_of_the_wind_wrong_class` | Krieger → 409 `wrong_class`. |
| `test_step_of_the_wind_invalid_mode` | mode="fly" → 400 with "mode" in the error body. |

### `test_use_attack_improved_critical.py`
v2.49.231 — Champion Fighter Lv 3+ subclass feature. Server-side crit threshold drops from 20 to 19 for Champion attackers; `_attacker_crit_threshold(sheet)` reads class/subclass/level. Tests use `/api/test/dice/seed` for deterministic dice + 200-roll batches per attacker, parse the `attack_breakdown` for the kept d20 value, then group-assert `is_crit` matches the expected threshold.

| Test | What it asserts |
|------|-----------------|
| `test_champion_crits_on_19` | Garrik (Lv 5 Champion) — every d20=19 in the batch crits (Improved Critical fires); every d20=20 crits (baseline); every d20<19 does NOT crit (regression guard). |
| `test_rogue_does_not_crit_on_19` | Pip (Rogue) control — d20=19 must NOT crit (Improved Critical is Champion-only); d20=20 still crits per baseline. |

### `test_use_stillness_of_mind.py`
v2.49.229 — Monk class feature `POST /use_stillness_of_mind` (Lv 7). Action, unlimited uses. Takes `{character_id, buff_key}`; validates buff_key is in `{charmed, frightened}` (refuses paralyzed/stunned/etc. per RAW). Removes the matching buff via `_remove_buff` (same helper /end_buff uses), syncs the sheet mirror, marks the action slot, broadcasts buff_update + feature_used.

| Test | What it asserts |
|------|-----------------|
| `test_stillness_of_mind_clears_charmed` | Seed Kael with a Charmed buff → 200; `removed_key=charmed`, `removed_name=Charmed`. `buff_update` shows the buff gone; `feature_used` source=stillness-of-mind. |
| `test_stillness_of_mind_clears_frightened` | Same path, Frightened buff variant → 200; `removed_key=frightened`. |
| `test_stillness_of_mind_wrong_class` | Pip (Rogue) → 409 `error=wrong_class`, `expected=monk`, `got=rogue`. |
| `test_stillness_of_mind_wrong_condition` | buff_key="stunned" → 409 `error=wrong_condition`, `got=stunned`, `allowed=[charmed,frightened]`. |
| `test_stillness_of_mind_buff_not_present` | Kael with no Charmed/Frightened buff → 404 `error=buff_not_present`. |
| `test_stillness_of_mind_missing_buff_key` | Missing buff_key → 400. |
| `test_stillness_of_mind_missing_character_id` | Missing character_id → 400. |

### `test_use_wholeness_of_body.py`
v2.49.227 — Monk subclass feature `POST /use_wholeness_of_body` (Way of the Open Hand, Lv 6). Action, 1/long rest, deterministic heal = 3 × monk level (no roll). Atomically decrements the `wholeness-of-body` counter, applies HP via `_apply_hp_change`, marks the action slot, broadcasts `feature_used` + `resource_update` + `character_death_save` (when applicable). Kael Brightleaf (bumped from Lv 5 to Lv 6 in the same release) is the demo fixture.

| Test | What it asserts |
|------|-----------------|
| `test_wholeness_of_body_happy_path` | Kael spends WoB → 200, `rolled=18` (3 × Lv 6), `actual_healed=0` (at full HP), `remaining=0`, `max=1`. `feature_used` broadcast carries `source=wholeness-of-body`, heal_target_name=Kael, `feature_desc` includes "18" and "Lv 6". `resource_update` broadcast confirms `current=0`, `max=1`. |
| `test_wholeness_of_body_out_of_uses` | Drain the one use; second call → 409 `error=out_of_uses` with `label="Wholeness of Body"`. |
| `test_wholeness_of_body_wrong_class` | Pip (Rogue) → 409 `error=wrong_class`, `expected=monk`, `got=rogue`. |
| `test_wholeness_of_body_missing_character_id` | Empty body → 400. |

### `test_use_reckless_attack.py`
v2.49.238 — Barbarian class feature `POST /use_reckless_attack` (Lv 2+). No counter cost; installs a 1-round self-buff with `effects.advantage_on=['str_attack']` + `effects.incoming_attacks_have_advantage=True`. Phase-B integration: the new `_target_grants_advantage_to_attackers` helper exposes the downside to `use_attack` so attacks AGAINST a reckless barbarian roll `2d20kh1`. The upside (advantage on the barbarian's own STR melee attacks) folds into the generalized `_attacker_has_str_attack_advantage` (formerly `_has_rage_str_advantage`).

| Test | What it asserts |
|------|-----------------|
| `test_reckless_attack_happy_path` | Krieger → 200, `buff_installed=True`, `duration_rounds=1`. `buff_update` broadcast carries `reckless-attack` key with both effect flags; `feature_used` source=reckless-attack. |
| `test_reckless_attack_wrong_class` | Pip (Rogue) → 409 `error=wrong_class`, `expected=barbarian`. |
| `test_reckless_attack_missing_character_id` | Empty body → 400. |
| `test_attack_against_reckless_target_gets_advantage` | Seeds Krieger with the reckless-attack buff pre-installed; Pip's Shortsword attack against him rolls `2d20kh1` (breakdown match) and `roll_state_applied` mentions reckless. |

### `test_settings_roll_log_position.py`
v2.49.244 — per-user UI preference. `POST /api/settings/roll_log_position` flips the Roll Log drawer between the shared right sidebar (default) and an independent left-side sidebar.

| Test | What it asserts |
|------|-----------------|
| `test_roll_log_position_left_then_right` | GM POSTs `{"position": "left"}` → 200 + `roll_log_position == "left"`; subsequent POST `{"position": "right"}` flips back, both persist. |
| `test_roll_log_position_rejects_invalid_value` | `{"position": "middle"}` → 400 with the invalid value surfaced in the response body. |
| `test_roll_log_position_persists_for_player` | Per-user isolation — Alice sets `left` independently of the GM; cleanup resets her to `right`. |

### `test_encounter_background.py`
v2.86.0 — encounter backgrounds. Fullscreen fixed-position image/video layer behind the battle map; `POST /api/campaign/{cid}/background` writes `campaign.active_background_url` + broadcasts `background_change`; `POST /api/campaign/{cid}/encounters/{eid}/background` writes `enc.background_url` without broadcasting (the encounter load flow propagates).

| Test | What it asserts |
|------|-----------------|
| `test_campaign_background_missing_payload_400` | No file + `clear=false` on the campaign endpoint → 400. Guards against silent no-op calls. |
| `test_campaign_background_upload_then_clear` | Multipart PNG upload → 200 + `active_background_url` starts with `/static/uploads/encounter_bg/` + `background_change` WS broadcast carries the new URL. Subsequent `clear=true` → 200 + URL nulled + broadcast carries `null`. |
| `test_campaign_default_falls_back_for_encounter_without_bg` | v2.87.0 — campaign endpoint sets both `default_background_url` and `active_background_url`; a no-bg encounter creates with `background_url=null`. Proves the contract that powers the fallback in `_perform_encounter_load` (enc bg → campaign default → null). |
| `test_encounter_background_upload_does_not_broadcast` | Creates a throwaway encounter, attaches a background to it via the per-encounter endpoint, asserts the encounter projection now carries `background_url`, asserts NO `background_change` broadcast fires (propagation only happens on encounter load), cleans up via the delete endpoint. |

### `test_use_indomitable.py`
v2.56.0 — Fighter Lv 9+ Indomitable. Arm-then-consume single-use save-advantage buff (`indomitable-armed`). Save-roll hook reads + consumes the buff per-save. RAW-bent v1 (advantage on next save instead of post-roll reroll-on-failure); see TODO.md.

| Test | What it asserts |
|------|-----------------|
| `test_use_indomitable_arms_buff` | `/use_indomitable` → 200, `remaining=0`, buff `indomitable-armed` lands on Garrik's combatant, arm-side `feature_used(source=indomitable)` broadcast. |
| `test_use_indomitable_wrong_class` | Pip (Rogue) → 409 `wrong_class` with `expected=fighter`. |
| `test_use_indomitable_out_of_uses` | First call burns the only use; second call → 409 `out_of_uses` with `label=Indomitable`. |
| `test_indomitable_consumes_on_save` | Arm + cast Suggestion at Garrik → save `base_expression="2d20kh1"`, buff removed from Garrik's combatant, consume-side `feature_used(source=indomitable)` broadcast. |
| `test_indomitable_one_save_only` | After consume, a second save in the same round has `base_expression="1d20"` (no kh1; buff already consumed). |

### `test_cast_spell_target_set_line.py`
v2.376.0 — extends `/cast_spell` `target_set` to `shape: "line"` — closes sphere/cone/line parity with the picker endpoints. Caller names caster + target combatants (+ optional `width_ft` / `max_length_ft` / faction); server runs the segment from caster→target token centers, catches combatants within `width_ft/2` out to `max_length_ft`. Both caster + target are excluded (target is the line's geometric anchor, not a target).

| Test | What it asserts |
|------|-----------------|
| `test_target_set_line_picks_inline_bandit` | Thalindra caster + bandit-target + bandit-inline-downrange placed on the active map; cast with line target_set returns 1 outcome row (inline bandit) — caster + target excluded. |
| `test_target_set_line_missing_target_400` | Missing `target_combatant_id` → 400 validation. |
| `test_target_set_line_invalid_width_400` | `width_ft=0` → 400 validation. |

### `test_cast_spell_target_set_cone.py`
v2.375.0 — extends `/cast_spell` `target_set` to `shape: "cone"`. Caller names apex + direction combatants + `length_ft` (+ optional half-angle + faction); server walks the active map's tokens, filters by the cone's angular span + length + faction, feeds the resulting ids into the Phase T.5 multi-target loop. Apex AND direction are both excluded (mirrors the `/battle/cone-targets` picker contract).

| Test | What it asserts |
|------|-----------------|
| `test_target_set_cone_picks_bandits` | Thalindra apex + bandit-direction + bandit-downrange placed on the active map; Fireball cast with cone target_set returns 1 outcome row (downrange bandit) — apex + direction excluded. |
| `test_target_set_cone_missing_direction_400` | Missing `direction_combatant_id` → 400 validation. |
| `test_target_set_cone_invalid_length_400` | `length_ft=0` → 400 validation. |

### `test_cast_spell_target_set.py`
v2.374.0 — `/cast_spell` accepts an optional `target_set: {shape: "sphere", center_combatant_id, radius_ft, faction}` body param that derives the AoE target id list server-side via the same geometry as `/battle/sphere-targets`. When set AND `target_combatant_ids` is empty, the resolved ids feed the Phase T.5 multi-target save+damage loop. Explicit `target_combatant_ids` win when both are passed. Sphere shape only in v1.

| Test | What it asserts |
|------|-----------------|
| `test_target_set_sphere_enemies_picks_bandits` | Thalindra + 3 bandits placed on the active map; Fireball cast with `target_set` sphere/enemies resolves all 3 bandits and loops save+damage for each (`auto_save_targets` length matches). |
| `test_target_set_invalid_radius_400` | `radius_ft=0` → 400 validation. |
| `test_target_set_invalid_faction_400` | `faction="bogus"` → 400 validation. |
| `test_explicit_ids_win_over_target_set` | When `target_combatant_ids` is non-empty, `target_set` is ignored (even if invalid — proves the early-exit on the explicit branch). |

### `test_cone_line_targets_faction_filter.py`
v2.373.1 — mirrors the v2.373.0 sphere-targets faction filter onto `/battle/cone-targets` and `/battle/line-targets`. Same shape: optional `faction` body param ("all" | "allies" | "enemies"), PC-vs-NPC heuristic relative to apex (cone) or caster (line).

| Test | What it asserts |
|------|-----------------|
| `test_cone_targets_faction_filter_validation` | Invalid `faction` value on cone-targets never returns 200. |
| `test_line_targets_faction_filter_validation` | Invalid `faction` value on line-targets never returns 200. |
| `test_cone_targets_default_faction_echo` | When the endpoint reaches the result-construct block, response carries `faction: "all"` echo. |
| `test_line_targets_default_faction_echo` | Same default-faction echo on the line-targets endpoint. |

### `test_sphere_targets_faction_filter.py`
v2.373.0 — `/battle/sphere-targets` gains an optional `faction` body param (`"all" | "allies" | "enemies"`, default `all` = current behavior). When set AND `center_combatant_id` is supplied, filters the result list by the center combatant's PC-vs-NPC faction. Useful for self-centered AoE auto-target flows (Spirit Guardians enemies-only, Aid allies-only, Fireball default).

| Test | What it asserts |
|------|-----------------|
| `test_sphere_targets_faction_filter_validation` | Invalid `faction` value never returns 200 (400 validation rejection). |
| `test_sphere_targets_default_faction_is_all` | No `faction` param → response `faction: "all"`, includes Pip in radius (back-compat preserved). |
| `test_sphere_targets_allies_filter` | `faction: "allies"` from PC center excludes Bandit (NPC) — opposite-faction creatures filtered out. |
| `test_sphere_targets_enemies_filter` | `faction: "enemies"` from PC center excludes Pip (PC) — same-faction creatures filtered out. |

### `test_cast_aid_target_cap.py`
v2.372.1 — Aid 3-target cap (RAW PHB p.211). Adds `max_targets: 3` to `_SPELL_BUFF_MAP["aid"]`; `/cast_spell`'s buff-install branch returns 400 `too_many_targets` when the caller exceeds the cap. Generic substrate ready for other "up to N creatures" buff spells (Bless, Beacon of Hope, etc.) to opt in.

| Test | What it asserts |
|------|-----------------|
| `test_aid_three_targets_succeeds` | 3 PC targets → 200 (Aid hits the RAW cap exactly). |
| `test_aid_four_targets_returns_400` | 4 PC targets → 400 `too_many_targets` with `{limit: 3, received: 4}`. |

### `test_cast_invisibility_target_cap_upcast.py`
v2.404.1 — Invisibility multi-target cap + per-slot upcast scaling (RAW PHB p.254). Wires Invisibility through the v2.380.0 `_SPELL_BUFF_MAP` substrate with `max_targets: 1, base_level: 2, extra_targets_per_slot_above_base: 1`. `/cast_spell` now installs an `invisibility` concentration buff (mirrors the `invisibility-potion` marker shape with `effects.invisible: True`) and extends the cap by `(slot_level - 2)` per slot above base. First L2-base spell to use the substrate. Lyra Sunstrider (Bard Lv 6, Invisibility at spell index 10) is the cast surface.

| Test | What it asserts |
|------|-----------------|
| `test_invisibility_l2_one_target_succeeds` | L2 cast with 1 target → 200 (RAW base cap). |
| `test_invisibility_l2_two_targets_returns_400` | L2 cast with 2 targets → 400 `too_many_targets` with `{limit: 1, received: 2}`. |
| `test_invisibility_l3_two_targets_succeeds` | L3 cast with 2 targets → 200 (extended cap = 1 + (3-2)*1 = 2). |
| `test_invisibility_l3_three_targets_returns_400` | L3 cast with 3 targets → 400 with `{limit: 2, received: 3}` — confirms the upcast field is honored, not the base 1. |

### `test_cast_fly_target_cap_upcast.py`
v2.404.2 — Fly multi-target cap + per-slot upcast scaling (RAW PHB p.244). Wires Fly through the v2.380.0 `_SPELL_BUFF_MAP` substrate with `max_targets: 1, base_level: 3, extra_targets_per_slot_above_base: 1`. First L3-base spell to use the substrate. `/cast_spell` now installs a `fly` concentration buff with `effects.fly_speed_ft: 60` (the same marker the Stormborn / levitate / dragon-wings / flying-potion buffs use). Thalindra Moonwhisper (Wizard Lv 7, Fly appended at spell index 20) is the cast surface; her L3 + L4 slots cover both base cap and +1 upcast extension.

| Test | What it asserts |
|------|-----------------|
| `test_fly_l3_one_target_succeeds` | L3 cast with 1 target → 200 (RAW base cap). |
| `test_fly_l3_two_targets_returns_400` | L3 cast with 2 targets → 400 `too_many_targets` with `{limit: 1, received: 2}`. |
| `test_fly_l4_two_targets_succeeds` | L4 cast with 2 targets → 200 (extended cap = 1 + (4-3)*1 = 2). |
| `test_fly_l4_three_targets_returns_400` | L4 cast with 3 targets → 400 with `{limit: 2, received: 3}` — confirms the upcast field is honored. |

### `test_cast_enhance_ability_target_cap_upcast.py`
v2.404.3 — Enhance Ability multi-target cap + per-slot upcast scaling (RAW PHB p.237). Wires Enhance Ability through the v2.380.0 `_SPELL_BUFF_MAP` substrate with `max_targets: 1, base_level: 2, extra_targets_per_slot_above_base: 1` (same shape as Invisibility). `/cast_spell` now installs an `enhance-ability` concentration buff with `effects.enhance_ability_active: True` (the six variant choices — Bear / Bull / Cat / Eagle / Fox / Owl — and their riders stay GM-narrated). Brother Tavik Stonebrow (Cleric Lv 8, Enhance Ability appended at spell index 13) is the cast surface; his L2 + L3 slots cover both base cap and +1 upcast extension.

| Test | What it asserts |
|------|-----------------|
| `test_enhance_ability_l2_one_target_succeeds` | L2 cast with 1 target → 200 (RAW base cap). |
| `test_enhance_ability_l2_two_targets_returns_400` | L2 cast with 2 targets → 400 `too_many_targets` with `{limit: 1, received: 2}`. |
| `test_enhance_ability_l3_two_targets_succeeds` | L3 cast with 2 targets → 200 (extended cap = 1 + (3-2)*1 = 2). |
| `test_enhance_ability_l3_three_targets_returns_400` | L3 cast with 3 targets → 400 with `{limit: 2, received: 3}` — confirms the upcast field is honored. |

### `test_cast_longstrider_target_cap_upcast.py`
v2.404.4 — Longstrider multi-target cap + per-slot upcast scaling (RAW PHB p.255). Extends the existing `_SPELL_BUFF_MAP["longstrider"]` entry (v2.99.431 Phase 6.1) with `max_targets: 1, base_level: 1, extra_targets_per_slot_above_base: 1`. First **non-concentration** spell in the v2.404.x arc (Longstrider is the 1-hour +10ft speed buff that already flows through `_effective_speed_walk` at /token/move time; this commit just adds the cap fields). Mira Greenleaf (Druid Lv 6, Longstrider appended at spell index 11) is the cast surface; her L1 + L2 slots cover both base cap and +1 upcast extension. Closes the buff-shape half of the spell utility-upcast arc.

| Test | What it asserts |
|------|-----------------|
| `test_longstrider_l1_one_target_succeeds` | L1 cast with 1 target → 200 (RAW base cap). |
| `test_longstrider_l1_two_targets_returns_400` | L1 cast with 2 targets → 400 `too_many_targets` with `{limit: 1, received: 2}`. |
| `test_longstrider_l2_two_targets_succeeds` | L2 cast with 2 targets → 200 (extended cap = 1 + (2-1)*1 = 2). |
| `test_longstrider_l2_three_targets_returns_400` | L2 cast with 3 targets → 400 with `{limit: 2, received: 3}` — confirms the upcast field is honored. |

### `test_cast_death_ward.py`
v2.496.0 — Death Ward (L4 abjuration, Cleric/Paladin, PHB p.230). Phase 2 #29 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). **First tail spell with genuinely new mechanical code:** the drop-to-1-on-first-0 floor lives in `_apply_hp_change` alongside the Half-Orc Relentless Endurance branch (gated by an `effects.death_ward` buff instead of a racial resource). New `_SPELL_BUFF_MAP["death-ward"]` template + `_pc_has_death_ward`/`_consume_death_ward` helpers + the `cast_death_ward` endpoint (mirrors the buff to the sheet so the sync HP floor reads it). Firing consumes the buff and the central damage path drops the hub copy + broadcasts. Tavik (Cleric) casts; Pip attacks the warded Garrik to trigger the floor.

| Test | What it asserts |
|------|-----------------|
| `test_cast_death_ward_installs_marker_buff` | Cleric wards an ally → 200, `feature == "death-ward"`, `duration_rounds == 4800`; buff carries `effects.death_ward == true`. |
| `test_cast_death_ward_is_8_hours_non_concentration` | Installed buff has `concentration == false` + `duration_rounds == 4800`. |
| `test_death_ward_floors_lethal_hit_at_1_hp` | **End-to-end floor:** warded Garrik at 3 HP → Pip's seeded hit ≥3 → `character_hp_update` shows HP=1 (not 0), `feature_used(source=death-ward, "held at 1 HP")` broadcast fires, and the death-ward buff is consumed. |
| `test_cast_death_ward_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "death ward". |
| `test_cast_death_ward_missing_character_id_400` | Empty body → 400. |

### `test_cast_warding_bond.py`
v2.493.0 — Warding Bond (L2 abjuration, Cleric, PHB p.287). Phase 2 #28 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_SPELL_BUFF_MAP["warding-bond"]` template (`ac_bonus: 1` + `resistance_to: ["all"]`, 600 rounds, non-concentration) + the `cast_warding_bond` endpoint. Rides two existing substrates — `ac_bonus` (read at `_read_target_ac`) + `resistance_to:["all"]` (read by `_resistance_halve`); the +1 saves (item-only read-site), damage-share rider, and 60-ft tether stay GM-narrated. Mirrors the buff to the target's sheet (the resistance reader is sheet-based). Brother Tavik (Cleric) casts; Krieger is the warded ally + non-caster reject.

| Test | What it asserts |
|------|-----------------|
| `test_cast_warding_bond_installs_ac_and_resistance` | Cleric wards an ally → 200, `feature == "warding-bond"`, `duration_rounds == 600`; buff carries `effects.ac_bonus == 1` AND `resistance_to` ⊇ {all}. |
| `test_cast_warding_bond_is_1_hour_non_concentration` | Installed buff has `concentration == false` + `duration_rounds == 600`. |
| `test_cast_warding_bond_on_ally_installs_on_ally` | Targeting an ally installs the buff on the ally, not the caster. |
| `test_cast_warding_bond_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "warding bond". |
| `test_cast_warding_bond_missing_character_id_400` | Empty body → 400. |

### `test_cast_freedom_of_movement.py`
v2.492.0 — Freedom of Movement (L4 abjuration, Bard/Cleric/Druid/Ranger, PHB p.250). Phase 2 #27 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_SPELL_BUFF_MAP["freedom-of-movement"]` template (`condition_immunity_to: ["paralyzed","restrained"]`, 600 rounds, non-concentration) + the `cast_freedom_of_movement` endpoint. Rides the existing condition-immunity gate (`_target_condition_immune` at `_install_buff`) — the same substrate the v2.289.0 Ring of Free Action uses. The endpoint mirrors the buff to the target's sheet (`_mirror_buffs_to_sheet`) so the PC gate, which reads `_buffs_active` off the sheet, sees it. Brother Tavik (Cleric) casts; Krieger (Barbarian) is the warded target + non-caster reject.

| Test | What it asserts |
|------|-----------------|
| `test_cast_fom_self_installs_condition_immunity` | Cleric self → 200, `feature == "freedom-of-movement"`, `duration_rounds == 600`; buff carries `effects.condition_immunity_to` ⊇ {paralyzed, restrained}. |
| `test_cast_fom_is_1_hour_non_concentration` | Installed buff has `concentration == false` + `duration_rounds == 600`. |
| `test_fom_suppresses_hold_person_paralyze` | **Gate test:** FoM on Krieger → Tavik casts Hold Person (override) → `affected[].installed == False` for Krieger + no `paralyzed` buff. End-to-end proof the immunity gate fires off the mirrored sheet buff. |
| `test_cast_fom_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "freedom of movement". |
| `test_cast_fom_missing_character_id_400` | Empty body → 400. |

### `test_cast_enlarge_reduce.py`
v2.491.0 — Enlarge/Reduce (L2 transmutation, Sorcerer/Wizard, PHB p.237). Phase 2 #26 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `cast_enlarge_reduce` endpoint with a required `mode` param: `enlarge` installs `effects.advantage_on: ["str_check","str_save"]`, `reduce` installs `disadvantage_on: [...]`. Rides the existing STR-marker read-sites (the same `_pc_has_rage_str_save_advantage` + v2.199.0 disadvantage intercept the Potion of Growth / Diminution use) so STR checks/saves actually roll with adv/dis; size + ±1d4 weapon damage stay GM-narrated. Concentration / 1 minute (10 rounds), unlike the non-concentration potions. Thalindra Moonwhisper (Wizard) is the cast surface.

| Test | What it asserts |
|------|-----------------|
| `test_cast_enlarge_self_installs_str_advantage` | Enlarge self → 200, `mode == "enlarge"`, `duration_rounds == 10`; buff key `enlarge` carries `effects.advantage_on` ⊇ {str_check, str_save}. |
| `test_cast_reduce_self_installs_str_disadvantage` | Reduce self → buff key `reduce` carries `effects.disadvantage_on` ⊇ {str_check, str_save}. |
| `test_cast_enlarge_is_concentration_1_minute` | Installed buff has `concentration == true` + `duration_rounds == 10` (the spell, not potion, semantics). |
| `test_cast_enlarge_on_ally_installs_on_ally` | Targeting an ally installs the buff on the ally, not the caster. |
| `test_cast_enlarge_reduce_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`. |
| `test_cast_enlarge_reduce_bad_mode_400` | An invalid `mode` (e.g. "embiggen") → 400. |
| `test_cast_enlarge_reduce_missing_character_id_400` | Body without character_id → 400. |

### `test_cast_antilife_shell.py`
v2.512.0 — Antilife Shell (L5 abjuration, Druid, PHB p.213). Phase 2 #45 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_SPELL_BUFF_MAP["antilife-shell"]` (`antilife_shell: True`, concentration, 600 rounds) + the `cast_antilife_shell` endpoint. Flag-buff shape; the moving 10-ft barrier + hedge enforcement are a new movement-barrier substrate filed against Maps 2.0. Self-targeted, Druid-only gate. Mira (Druid) casts.

| Test | What it asserts |
|------|-----------------|
| `test_cast_als_druid_installs_buff` | Druid self-cast → 200, `feature == "antilife-shell"`, `duration_rounds == 600`; buff carries `antilife_shell == true`. |
| `test_cast_als_buff_is_1_hour_concentration` | Buff carries `duration_rounds == 600` (1 hour) + `concentration == true`. |
| `test_cast_als_barbarian_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "antilife shell". |
| `test_cast_als_wizard_rejected` | Thalindra (Wizard) → 409 — asserts the Druid-only gate excludes a different caster class. |
| `test_cast_als_missing_character_id_400` | Empty body → 400. |

### `test_globe_blocks_spell.py`
v2.513.0 — Globe of Invulnerability `/cast_spell` block (Phase 2 #44 follow-up of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md)). New `_target_globe_blocks_spell` hub-read compares the spell's BASE level against the buff's `spell_immunity_max_level` (5) and rejects a single-target ≤-threshold spell at a globe'd target with 409 `globe_blocks_spell`. Thalindra (Wizard) raises the globe; Zara (Sorcerer) casts Magic Missile at her.

| Test | What it asserts |
|------|-----------------|
| `test_globe_blocks_low_level_spell` | Magic Missile (base L1) at a globed target → 409 `globe_blocks_spell`. |
| `test_no_globe_does_not_block` | **Control:** no globe up → the same cast is not globe-blocked. |
| `test_globe_blocks_even_when_upcast` | Magic Missile at `slot_level: 5` → still 409, response `spell_level == 1` (proves base-vs-slot comparison). |
| `test_globe_override_bypasses_block` | GM `override: true` → the globe gate does not fire. |
| `test_globe_blocks_caster_outside_barrier` | v2.517.0 (Phase 2): caster placed 25 ft from the globe holder (outside the 10-ft barrier) → 409 `globe_blocks_spell`. |
| `test_globe_does_not_block_caster_inside_barrier` | v2.517.0 (Phase 2): caster placed 5 ft from the holder (inside the barrier) → the globe gate does NOT fire (a creature inside casts freely). |
| `test_globe_off_grid_assumes_outside_and_blocks` | v2.517.0 (Phase 2): tokens deleted (off-grid) → `caster_distance_ft` null → assumes outside and blocks (the v2.513.0 fallback). |

### `test_cast_globe_of_invulnerability.py`
v2.511.0 — Globe of Invulnerability (L6 abjuration, Sorcerer/Wizard, PHB p.247). Phase 2 #44 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_SPELL_BUFF_MAP["globe-of-invulnerability"]` (`globe_of_invulnerability: True` + `spell_immunity_max_level: 5`, concentration) + the `cast_globe_of_invulnerability` endpoint. Flag-buff shape: surfaces the 5th-level immunity threshold; barrier geometry + the `/cast_spell` block are filed follow-ups (spatial AoE-shape work). Self-targeted.

| Test | What it asserts |
|------|-----------------|
| `test_cast_goi_wizard_installs_buff` | Wizard self-cast → 200, `feature == "globe-of-invulnerability"`, `spell_immunity_max_level == 5`; buff carries `globe_of_invulnerability == true` + `spell_immunity_max_level == 5`. |
| `test_cast_goi_buff_is_1_min_concentration` | Buff carries `duration_rounds == 10` (1 min) + `concentration == true`. |
| `test_cast_goi_sorcerer_also_succeeds` | A Sorcerer succeeds (asserts the sorcerer/wizard gate). |
| `test_cast_goi_non_caster_rejected` | Cleric (not on the RAW list) → 409 `cannot_cast`, expected string names "globe of invulnerability". |
| `test_cast_goi_missing_character_id_400` | Empty body → 400. |

### `test_attack_invisible_target_disadvantage.py`
v2.514.0 — See Invisibility target-side (Phase 2 #43 follow-up of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md)). New `_target_is_invisible` hub-read folds an invisible *target* into the PC `/attack` + NPC `/npc_attack` disadvantage source sets (RAW PHB p.291), negated when the attacker carries `effects.sees_invisible` (`_attacker_sees_invisible` / `_npc_attacker_sees_invisible`). Invisible target + sees-invisible attacker seeded directly on combatant.buffs.

| Test | What it asserts |
|------|-----------------|
| `test_pc_attacks_invisible_target_gets_disadvantage` | Pip attacks an invisible Krieger → `roll_state_applied` contains `disadvantage` + `target_invisible`. |
| `test_pc_with_see_invisibility_no_disadvantage` | Pip carrying `sees_invisible` attacks the invisible target → `roll_state_applied` no longer contains `target_invisible`. |
| `test_npc_attacks_invisible_pc_gets_disadvantage` | An NPC attacks an invisible PC → `disadvantage` + `target_invisible`. |
| `test_npc_with_see_invisibility_no_disadvantage` | An NPC carrying `sees_invisible` attacks the invisible PC → not `target_invisible`. |

### `test_see_invisibility_negates_attack_edge.py`
v2.510.0 — See Invisibility attack-edge negation (Phase 2 #43 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md)). New `_target_sees_invisible` hub-read folded into the v2.152.0 invisible-attacker advantage across all three attack branches (PC `/attack` bonused + bonusless, NPC `/npc_attack`). Thalindra casts Greater Invisibility on Krieger + See Invisibility on herself.

| Test | What it asserts |
|------|-----------------|
| `test_invisible_attacker_has_advantage_vs_normal_target` | **Control:** invisible Krieger attacks Pip (no See Invisibility) → `roll_state_applied` contains both `advantage` and `invisible`. |
| `test_see_invisibility_negates_invisible_attacker_advantage` | **Negation:** invisible Krieger attacks the See-Invisibility Thalindra → `roll_state_applied` no longer contains `invisible`. |

### `test_cast_continual_flame.py`
v2.537.0 — Continual Flame (L2 evocation, Cleric/Wizard, PHB p.227). Phase 2 #55 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `cast_continual_flame` endpoint — flexible object target: a `continual_flame` flag-buff on a tracked bearer, or a broadcast-only cast over a GM-named object. Light GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_cast_cf_on_bearer_installs_buff` | Cast on a tracked bearer → 200, `buff_installed == true`, `duration_rounds == 999999`; buff carries `continual_flame == true`, non-concentration. |
| `test_cast_cf_no_target_is_broadcast_only` | Cast with only `target_name` → `buff_installed == false`, `target_character_id == null`, `target_name` echoed. |
| `test_cast_cf_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "continual flame". |
| `test_cast_cf_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_gentle_repose.py`
v2.536.0 — Gentle Repose (L2 necromancy ritual, Cleric/Wizard, PHB p.245). Phase 2 #54 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `cast_gentle_repose` endpoint — flexible corpse target: a `gentle_repose` flag-buff on a tracked character's remains, or a broadcast-only cast over a GM-narrated corpse. Decay/undead/raise-window GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_cast_gr_on_target_installs_buff` | Cast on a tracked target → 200, `buff_installed == true`, `target_character_id` set, `duration_rounds == 144000`; buff carries `gentle_repose == true`, non-concentration. |
| `test_cast_gr_no_target_is_broadcast_only` | Cast with only `target_name` → `buff_installed == false`, `target_character_id == null`, `target_name` echoed. |
| `test_cast_gr_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "gentle repose". |
| `test_cast_gr_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_calm_emotions.py`
v2.535.0 — Calm Emotions (L2 enchantment, Bard/Cleric/Warlock, PHB p.221). Phase 2 #53 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `cast_calm_emotions` endpoint — the concentration sibling of Zone of Truth, baking the CHA save DC via `_compute_spell_save_dc_from_sheet`. Sphere + saves + effect-choice GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_cast_ce_installs_dc_marker` | Cast → 200, `feature == "calm-emotions"`, `save_ability == "CHA"`, `save_dc >= 8`; buff carries `calm_emotions == true` + `save_dc` (== response) + `save_ability == CHA`. |
| `test_cast_ce_is_concentration_1_min` | Buff carries `duration_rounds == 10` (1 min) + `concentration == true`. |
| `test_cast_ce_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "calm emotions". |
| `test_cast_ce_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_zone_of_truth.py`
v2.534.0 — Zone of Truth (L2 enchantment, Bard/Cleric/Paladin, PHB p.289). Phase 2 #52 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `cast_zone_of_truth` endpoint — a marker buff baking the CHA save DC (`_compute_spell_save_dc_from_sheet`, the Sanctuary pattern). Sphere + saves + lie-prevention GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_cast_zot_installs_dc_marker` | Cast → 200, `feature == "zone-of-truth"`, `save_ability == "CHA"`, `save_dc >= 8`; buff carries `zone_of_truth == true` + `save_dc` (== response) + `save_ability == CHA`. |
| `test_cast_zot_dc_matches_sheet` | The baked DC ≥ 8 + proficiency + spellcasting-ability mod from the caster's sheet (DC round-trip; allows an item DC bonus). |
| `test_cast_zot_is_10_min_non_concentration` | Buff carries `duration_rounds == 100` (10 min) + `concentration == false`. |
| `test_cast_zot_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "zone of truth". |
| `test_cast_zot_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_locate_object.py`
v2.544.0 — Locate Object (L2 divination, Bard/Cleric/Druid/Ranger/Wizard, PHB p.256). Phase 2 #58 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `cast_locate_object` endpoint (shared `_do_cast_locate` helper) — a concentration flag-buff marking the sought object; bearing GM-narrated, concentration ride mechanical. Caster: Mira Greenleaf (Druid).

| Test | What it asserts |
|------|-----------------|
| `test_cast_locate_object_installs_concentration_buff` | Self-cast → `feature == "locate-object"`, `locate_range_ft == 1000`, `concentration == true`, `duration_rounds == 100`, default `locate_target == "an object"`; buff carries `locate_active`/`locate_target`/`locate_range_ft` + `concentration == true`. |
| `test_cast_locate_object_named_target` | A named `object_name` ("the lost crown") surfaces as `locate_target` in both response + buff. |
| `test_locate_object_drops_on_new_concentration` | **Concentration ride:** casting Barkskin (another concentration spell) drops the `locate-object` buff (one concentration at a time). |
| `test_cast_locate_object_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "locate object". |
| `test_cast_locate_object_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_forbiddance.py`
v2.553.0 — Forbiddance (L6 abjuration, Cleric, PHB p.243). Phase 2 #67 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `cast_forbiddance` endpoint — a GM-narrated warded zone baking a 5d10 radiant/necrotic damage marker (the SRD audit's last AoE-shape gap). Caster: Brother Tavik Stonebrow (Cleric).

| Test | What it asserts |
|------|-----------------|
| `test_cast_forbiddance_installs_ward_buff` | Self-cast → `feature == "forbiddance"`, `damage_dice == "5d10"`, default `damage_type == "radiant"` + `warded_type == "your chosen creatures"`, `duration_rounds == 14400`; buff is non-concentration carrying `forbiddance` + `ward_damage_dice` + `ward_damage_type`. |
| `test_cast_forbiddance_necrotic_and_warded_type` | A chosen `damage_type: "necrotic"` + named `warded_type` ("fiends") surface; an invalid `damage_type` ("fire") falls back to radiant. |
| `test_cast_forbiddance_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "forbiddance". |
| `test_cast_forbiddance_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_illusory_script.py`
v2.552.0 — Illusory Script (L1 illusion, Bard/Warlock/Wizard, PHB p.252). Phase 2 #66 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). The L1, 10-day sibling of Magic Mouth on the shared `_do_cast_inscribed_illusion` helper. Caster: Thalindra Moonwhisper (Wizard).

| Test | What it asserts |
|------|-----------------|
| `test_cast_illusory_script_installs_ten_day_buff` | Self-cast → `feature == "illusory-script"`, `duration == "10 days"`, default `message`/`readers`; buff is non-concentration carrying `illusory_script_active` + `illusory_script_message` + `illusory_script_readers`. |
| `test_cast_illusory_script_named_message_and_readers` | A named `message` + `readers` surface on response + buff. |
| `test_cast_illusory_script_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "illusory script". |
| `test_cast_illusory_script_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_magic_mouth.py`
v2.551.0 — Magic Mouth (L2 illusion, Bard/Wizard, PHB p.259). Phase 2 #65 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `cast_magic_mouth` endpoint (shared `_do_cast_inscribed_illusion` helper) — a long-lived flag-buff recording an implanted message + trigger (GM-narrated). Caster: Thalindra Moonwhisper (Wizard).

| Test | What it asserts |
|------|-----------------|
| `test_cast_magic_mouth_installs_until_dispelled_buff` | Self-cast → `feature == "magic-mouth"`, `duration == "until dispelled"`, default `message`/`trigger`; buff is non-concentration carrying `magic_mouth_active` + `magic_mouth_message` + `magic_mouth_trigger`. |
| `test_cast_magic_mouth_named_message_and_trigger` | A named `message` + `trigger` surface on response + buff. |
| `test_cast_magic_mouth_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "magic mouth". |
| `test_cast_magic_mouth_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_detect_thoughts.py`
v2.550.0 — Detect Thoughts (L2 divination, Bard/Sorcerer/Warlock/Wizard, PHB p.231). Phase 2 #64 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `cast_detect_thoughts` endpoint — a concentration flag-buff in the Zone of Truth DC-bake mould (baked WIS deeper-probe save). Caster: Thalindra Moonwhisper (Wizard).

| Test | What it asserts |
|------|-----------------|
| `test_cast_detect_thoughts_installs_dc_concentration_buff` | Self-cast → `feature == "detect-thoughts"`, `save_ability == "WIS"`, `save_dc >= 8`, `concentration == true`, `duration_rounds == 10`; buff carries `detect_thoughts` + `save_ability == "WIS"` + `save_dc` == response + `concentration == true`. |
| `test_detect_thoughts_drops_on_new_concentration` | **Concentration ride:** casting Fly drops the `detect-thoughts` buff. |
| `test_cast_detect_thoughts_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "detect thoughts". |
| `test_cast_detect_thoughts_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_arcane_eye.py`
v2.549.0 — Arcane Eye (L4 divination, Cleric/Wizard, PHB p.213). Phase 2 #63 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). The L4, 1-hour movable sibling of Clairvoyance on the shared `_do_cast_scry_sensor` helper (no seeing/hearing mode). Caster: Thalindra Moonwhisper (Wizard).

| Test | What it asserts |
|------|-----------------|
| `test_cast_arcane_eye_installs_concentration_buff` | Self-cast → `feature == "arcane-eye"`, `concentration == true`, `duration_rounds == 600`, default `location == "within 30 ft of you"`, no `mode` field; buff carries `scry_sensor_active` + `concentration == true` + no `scry_mode`. |
| `test_cast_arcane_eye_named_location` | A named `location` ("the corridor ahead") surfaces on response + buff. |
| `test_arcane_eye_drops_on_new_concentration` | **Concentration ride:** casting Fly drops the `arcane-eye` buff. |
| `test_cast_arcane_eye_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "arcane eye". |
| `test_cast_arcane_eye_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_clairvoyance.py`
v2.548.0 — Clairvoyance (L3 divination, Bard/Cleric/Sorcerer/Warlock/Wizard, PHB p.221). Phase 2 #62 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `cast_clairvoyance` endpoint (shared `_do_cast_scry_sensor` helper) — a concentration flag-buff planting an invisible seeing/hearing sensor (GM-narrated view). Caster: Thalindra Moonwhisper (Wizard).

| Test | What it asserts |
|------|-----------------|
| `test_cast_clairvoyance_installs_concentration_buff` | Self-cast → `feature == "clairvoyance"`, `concentration == true`, `duration_rounds == 100`, default `mode == "seeing"` + `location == "a familiar location"`; buff carries `scry_sensor_active` + `scry_mode == "seeing"` + `concentration == true`. |
| `test_cast_clairvoyance_hearing_mode_and_location` | `mode: "hearing"` + a named `location` ("the war room") surface on response + buff. |
| `test_clairvoyance_drops_on_new_concentration` | **Concentration ride:** casting Fly drops the `clairvoyance` buff. |
| `test_cast_clairvoyance_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "clairvoyance". |
| `test_cast_clairvoyance_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_project_image.py`
v2.547.0 — Project Image (L7 illusion, Bard/Wizard, PHB p.270). Phase 2 #61 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `cast_project_image` endpoint — a concentration flag-buff marking a remote intangible illusory copy of the caster (GM-narrated). Caster: Thalindra Moonwhisper (Wizard).

| Test | What it asserts |
|------|-----------------|
| `test_cast_project_image_installs_concentration_buff` | Self-cast → `feature == "project-image"`, `concentration == true`, `duration_rounds == 14400`, default `location == "a remembered location"`; buff carries `project_image_active` + `project_image_location` + `concentration == true`. |
| `test_cast_project_image_named_location` | A named `location` ("the throne room") surfaces on response + buff. |
| `test_project_image_drops_on_new_concentration` | **Concentration ride:** casting Fly drops the `project-image` buff. |
| `test_cast_project_image_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "project image". |
| `test_cast_project_image_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_mislead.py`
v2.546.0 — Mislead (L5 illusion, Bard/Wizard, PHB p.260). Phase 2 #60 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `cast_mislead` endpoint — the caster turns invisible (a real attack-disadvantage ride via `effects.invisible`) + a GM-narrated double; concentration-bound. Casters: Thalindra Moonwhisper (Wizard); attacker Pip Quickfingers.

| Test | What it asserts |
|------|-----------------|
| `test_cast_mislead_installs_invisible_concentration_buff` | Self-cast → `feature == "mislead"`, `invisible == true`, `concentration == true`, `duration_rounds == 600`; buff carries `effects.invisible` + `effects.mislead_double` + `concentration == true`. |
| `test_mislead_imposes_attack_disadvantage` | **Mechanical ride:** an attacker swinging at the misleading caster gets `target_invisible` in `roll_state_applied` (a control swing before the cast does not). |
| `test_mislead_drops_on_new_concentration` | **Concentration ride:** casting Fly drops the `mislead` buff. |
| `test_cast_mislead_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "mislead". |
| `test_cast_mislead_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_locate_creature.py`
v2.545.0 — Locate Creature (L4 divination, Bard/Cleric/Druid/Ranger/Wizard, PHB p.256). Phase 2 #59 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). The L4, 1-hour sibling of Locate Object on the shared `_do_cast_locate` helper. Caster: Mira Greenleaf (Druid).

| Test | What it asserts |
|------|-----------------|
| `test_cast_locate_creature_installs_concentration_buff` | Self-cast → `feature == "locate-creature"`, `locate_range_ft == 1000`, `concentration == true`, `duration_rounds == 600`, default `locate_target == "a creature"`; buff carries `locate_active`/`locate_kind == "creature"`/`locate_range_ft` + `concentration == true`. |
| `test_cast_locate_creature_named_target` | A named `creature_name` ("the fled goblin") surfaces as `locate_target` in both response + buff. |
| `test_locate_creature_drops_on_new_concentration` | **Concentration ride:** casting Barkskin drops the `locate-creature` buff. |
| `test_cast_locate_creature_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "locate creature". |
| `test_cast_locate_creature_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_true_seeing.py`
v2.542.0 — True Seeing (L6 divination, Bard/Cleric/Sorcerer/Warlock/Wizard, PHB p.284). Phase 2 #56 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `cast_true_seeing` endpoint — a two-substrate ride: `sees_invisible` (the See Invisibility attack-edge) + `darkvision_ft: 120` (the Darkvision sense marker) + a GM-narrated `truesight` flag.

| Test | What it asserts |
|------|-----------------|
| `test_cast_ts_self_installs_two_substrate_markers` | Self-cast → 200, `truesight_ft == 120`; buff carries `sees_invisible == true` + `darkvision_ft == 120` + `truesight == true`, non-concentration, 600 rounds. |
| `test_cast_ts_on_ally` | Touch an ally → the buff lands on the ally. |
| `test_ts_attacker_negates_invisible_target_edge` | **Mechanical ride:** a True-Seeing attacker vs an invisible target → `roll_state_applied` no longer contains `target_invisible` (control without True Seeing keeps it). |
| `test_cast_ts_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "true seeing". |
| `test_cast_ts_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_darkvision.py`
v2.533.0 — Darkvision (L2 transmutation, Druid/Ranger/Sorcerer/Wizard, PHB p.230). Phase 2 #51 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `cast_darkvision` endpoint — a single-target touch flag-buff (`darkvision_ft: 60`) riding the racial/Goggles darkvision sense marker. Seeing-in-the-dark GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_cast_dv_self_installs_buff` | Self-cast → 200, `feature == "darkvision"`, `darkvision_ft == 60`, `target_character_id == caster`; buff carries `darkvision_ft == 60`, non-concentration, 4800 rounds. |
| `test_cast_dv_on_ally` | Touch an ally → the buff lands on the ally, not the caster. |
| `test_cast_dv_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "darkvision". |
| `test_cast_dv_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_nondetection.py`
v2.524.0 — Nondetection (L3 abjuration, Bard/Cleric/Ranger/Wizard, PHB p.264). Phase 2 #48 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `cast_nondetection` endpoint — a single-target touch flag-buff (`nondetection: True`) hiding a creature from divination/scrying. Detection GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_cast_nd_self_installs_buff` | Self-cast → 200, `feature == "nondetection"`, `target_character_id == caster`; buff carries `nondetection == true`, non-concentration, 4800 rounds. |
| `test_cast_nd_on_ally_installs_on_ally` | Touch an ally → the buff lands on the ally, not the caster. |
| `test_cast_nd_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "nondetection". |
| `test_cast_nd_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_fly.py`
v2.527.0 — Fly (L3 transmutation, Sorcerer/Warlock/Wizard, PHB p.243). Phase 2 #50 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `cast_fly` endpoint exposing the pre-wired `_SPELL_BUFF_MAP["fly"]` (`fly_speed_ft: 60`, concentration) substrate; upcast adds one target per slot above 3rd. Fall-on-end GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_cast_fly_self_installs_buff` | Self-cast → 200, `feature == "fly"`, `target_cap == 1`; buff carries `fly_speed_ft == 60`, concentration, 100 rounds. |
| `test_cast_fly_on_ally` | Touch an ally → the buff lands on the ally (`targets == [ally]`). |
| `test_cast_fly_upcast_allows_more_targets` | `slot_level=5` → `target_cap == 3`; casting on 3 creatures installs 3 buffs. |
| `test_cast_fly_over_cap_at_base_400` | 2 targets at base slot 3 (cap 1) → 400 `too_many_targets`, `limit == 1`. |
| `test_cast_fly_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "fly". |
| `test_cast_fly_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_water_breathing.py`
v2.525.0 — Water Breathing (L3 transmutation ritual, Druid/Ranger/Sorcerer/Wizard, PHB p.287). Phase 2 #49 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_WATER_BREATHING_MAX_TARGETS = 10` + the `cast_water_breathing` endpoint — a multi-target flag-buff (`water_breathing: True`, 24h) fanned across up to 10 creatures (caster auto-included), built inline (distinct from the 1-hour Potion of Water Breathing buff sharing the slug). Underwater breathing GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_cast_wb_self_installs_buff` | Self-cast → 200, `feature == "water-breathing"`, `buffs_installed == 1`; buff carries `water_breathing == true`, non-concentration, 14400 rounds (24h). |
| `test_cast_wb_fans_out_to_companion` | Caster + a companion → `buffs_installed == 2`; the companion carries the `water-breathing` buff. |
| `test_cast_wb_over_cap_400` | More than 10 unique targets (incl. the auto-added caster) → 400. |
| `test_cast_wb_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "water breathing". |
| `test_cast_wb_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_water_walk.py`
v2.523.0 — Water Walk (L3 transmutation ritual, Cleric/Druid/Ranger/Sorcerer, PHB p.287). Phase 2 #47 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_WATER_WALK_MAX_TARGETS = 10` + the `cast_water_walk` endpoint — a multi-target flag-buff (`water_walk: True`) fanned across up to 10 creatures (caster auto-included), same shape as Feather Fall. Surface-walking GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_cast_ww_self_installs_buff` | Self-cast → 200, `feature == "water-walk"`, `buffs_installed == 1`; buff carries `water_walk == true`, non-concentration, 600 rounds. |
| `test_cast_ww_fans_out_to_companion` | Caster + a companion → `buffs_installed == 2`; the companion carries the `water-walk` buff. |
| `test_cast_ww_over_cap_400` | More than 10 unique targets (incl. the auto-added caster) → 400. |
| `test_cast_ww_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "water walk". |
| `test_cast_ww_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_fire_shield.py`
v2.522.0 — Fire Shield (L4 evocation, Warlock/Wizard, PHB p.241). Phase 2 #46 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_FIRE_SHIELD_VARIANTS` (`warm`→cold, `chill`→fire) + the `cast_fire_shield` endpoint — the self-only sibling of Protection from Energy (#30), riding the `resistance_to` substrate with the resisted type chosen by the `shield` param. Mirrored to the sheet (per the v2.496.1 fix). 2d8 reactive damage + bright light GM-narrated.

| Test | What it asserts |
|------|-----------------|
| `test_cast_fs_warm_resists_cold` | `shield=warm` → 200, `resists==cold`, `duration_rounds==100`; buff carries `resistance_to == ["cold"]`. |
| `test_cast_fs_chill_resists_fire` | `shield=chill` → buff carries `resistance_to == ["fire"]`. |
| `test_cast_fs_non_concentration_and_mirrored` | Buff is `concentration==false` + `duration_rounds==100`, mirrored to the sheet `_buffs_active`. |
| `test_cast_fs_bad_shield_400` | An invalid `shield` (not warm/chill) → 400. |
| `test_cast_fs_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected names "fire shield". |
| `test_cast_fs_missing_character_id_400` | Missing `character_id` → 400. |

### `test_cast_see_invisibility.py`
v2.509.0 — See Invisibility (L2 divination, Bard/Sorcerer/Wizard, PHB p.274). Phase 2 #42 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_SPELL_BUFF_MAP["see-invisibility"]` (`sees_invisible: True`, 600 rounds, non-concentration) + the `cast_see_invisibility` endpoint. Flag-buff shape (same as Detect Magic / Tongues): the flag IS the mechanic; detection + Ethereal-Plane sight GM-narrated. Negating the v2.499.0 `effects.invisible` attack-edge is filed as a two-sided pipeline follow-up. Self-targeted.

| Test | What it asserts |
|------|-----------------|
| `test_cast_si_wizard_installs_buff` | Wizard self-cast → 200, `feature == "see-invisibility"`, `duration_rounds == 600`; buff carries `sees_invisible == true`. |
| `test_cast_si_buff_is_1_hour_non_concentration` | Buff carries `duration_rounds == 600` (1 hour) + `concentration == false`. |
| `test_cast_si_bard_also_succeeds` | A Bard succeeds (asserts the bard/sorcerer/wizard gate covers Bard). |
| `test_cast_si_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "see invisibility". |
| `test_cast_si_missing_character_id_400` | Empty body → 400. |

### `test_antilife_shell_barrier.py`
v2.518.0 — Antilife Shell movement barrier (Phase 3 of [aura-geometry-enforcement.md](../plans/aura-geometry-enforcement.md)). New `_move_crosses_antilife_shell` hub-read folded into `/token/{id}/move` as a 409 `barrier_blocks_move` gate — a move from outside to inside the holder's 10-ft radius is rejected (RAW PHB p.213). Mira (Druid) raises the shell at the grid center.

| Test | What it asserts |
|------|-----------------|
| `test_move_into_shell_blocked` | A mover crossing from 25 ft (outside) to ~2 ft (inside) → 409 `barrier_blocks_move`, `barrier == "antilife-shell"`. |
| `test_move_staying_outside_allowed` | A move that stays outside the 10-ft radius → 200. |
| `test_override_barrier_bypasses` | `override_barrier: true` → the mover crosses in (200) — the GM escape hatch for edge cases. |
| `test_undead_mover_passes_freely` | v2.519.0: a mover whose combatant carries `creature_type: "undead"` crosses into the shell (200) with no override (RAW undead/construct exception, auto via `_attacker_creature_type`). |
| `test_emitter_sweeps_creature_ends_shell` | v2.520.0: the holder moves so the barrier sweeps over a living creature (outside → inside) → the move stands (200) and the `antilife-shell` buff is removed (RAW "forced through" clause). |
| `test_emitter_move_no_sweep_keeps_shell` | v2.520.0: control — the holder moves but no creature crosses the barrier → the shell persists. |
| `test_npc_held_shell_blocks_mover` | v2.521.0: an NPC emitter (no `char_id`, position via `source_token_id`) carrying the shell hedges a PC mover out → 409 `barrier_blocks_move` (NPC-holder support via `_combatant_token`). |

### `test_holy_aura_membership.py`
v2.516.0 — Holy Aura aura membership (Phase 1 of [aura-geometry-enforcement.md](../plans/aura-geometry-enforcement.md)). `cast_holy_aura` registers `effects.aura = {radius_ft:30, affects:allies, buff:{key:holy-aura-radiance, ...}}` on the caster's anchor so the v2.99.425 `_tick_auras` engine maintains the benefit for allies within 30 ft each turn (auto-apply on enter, lapse on leave). Distinct `holy-aura-radiance` key avoids clobbering the cast-time `holy-aura` buffs.

| Test | What it asserts |
|------|-----------------|
| `test_cast_registers_membership_aura` | Cast → the caster's anchor buff carries `effects.aura{radius_ft:30, affects:allies, buff.key:holy-aura-radiance}` with both markers. |
| `test_in_range_ally_gains_radiance_on_tick` | A non-chosen ally 5 ft away gains `holy-aura-radiance` (both markers) after the caster's turn ticks. |
| `test_out_of_range_ally_gains_nothing_on_tick` | An ally 35 ft away (outside 30 ft) gains no `holy-aura-radiance`. |

### `test_cast_holy_aura.py`
v2.508.0 — Holy Aura (L8 abjuration, Cleric, PHB p.243). Phase 2 #41 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). The first tail spell to fan the buff out across an arbitrary number of chosen creatures (the 30-ft aura). New `_SPELL_BUFF_MAP["holy-aura"]` (`save_advantage: True` + `attackers_have_disadvantage: True`, concentration) + the `cast_holy_aura` endpoint — both effects ride existing hub-state substrates (`_buff_grants_save_advantage` all-saves + the v2.500.0 Blur read-site `_target_blur_imposes_disadvantage`); zero new mechanical code. Concentration anchors on the caster; companion buffs carry `_dependent_on_caster_concentration`. Dim-light radius + fiend/undead blinding flash GM-narrated. Tavik (Cleric) casts.

| Test | What it asserts |
|------|-----------------|
| `test_cast_holy_aura_installs_markers` | Cast → 200, `feature == "holy-aura"`, `buffs_installed == 1`, `duration_rounds == 10`; caster's buff carries `save_advantage == true` + `attackers_have_disadvantage == true` + `concentration == true`. |
| `test_holy_aura_fans_out_to_companions` | **Fan-out:** caster + a chosen companion → `buffs_installed == 2`; caster's buff anchors concentration (`concentration == true`); companion's buff is `concentration == false` + `_dependent_on_caster_concentration == true` and carries both effect markers. |
| `test_holy_aura_grants_advantage_on_non_str_save` | **Save-advantage gate:** a Fireball DEX save vs a warded creature → `roll_request` `base_expression == "2d20kh1"` (advantage on a non-STR save proves the all-saves shape). |
| `test_holy_aura_imposes_disadvantage_on_attackers` | **Attacker-disadvantage gate:** Pip attacks a warded creature → `roll_state_applied` contains `disadvantage`. |
| `test_cast_holy_aura_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "holy aura". |
| `test_cast_holy_aura_missing_character_id_400` | Empty body → 400. |

### `test_cast_beacon_of_hope.py`
v2.507.0 — Beacon of Hope (L3 abjuration, Cleric, PHB p.219). Phase 2 #40 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_pc_has_death_save_advantage` helper + a 2d20-keep-highest roll + `death_save_advantage` response flag at `/death-save` + `_SPELL_BUFF_MAP["beacon-of-hope"]` (`save_advantage: ["WIS"]` + `death_save_advantage`) + the `cast_beacon_of_hope` endpoint. Max-healing GM-narrated. Tavik (Cleric) casts.

| Test | What it asserts |
|------|-----------------|
| `test_cast_beacon_installs_markers` | Cast → 200, `feature == "beacon-of-hope"`, `duration_rounds == 10`, `concentration == true`; buff carries `save_advantage` ⊇ {WIS} + `death_save_advantage == true`. |
| `test_beacon_grants_death_save_advantage` | **Death-save gate:** a dying creature with no beacon → `/death-save` reports `death_save_advantage: false`; after Beacon of Hope → `death_save_advantage: true`. |
| `test_cast_beacon_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "beacon of hope". |
| `test_cast_beacon_missing_character_id_400` | Empty body → 400. |

### `test_cast_heroes_feast.py`
v2.506.0 — Heroes' Feast (L6 conjuration, Bard/Cleric, PHB p.250). Phase 2 #39 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_SPELL_BUFF_MAP["heroes-feast"]` + `cast_heroes_feast` endpoint — all three combat halves ride existing substrates: condition immunity (`_target_condition_immune`), `save_advantage: ["WIS"]` (`_buff_grants_save_advantage`), and `aid_hp_bonus` = a per-cast 2d10 roll (`_buff_hp_max_bonus` + `_apply_heal_to_combatant`, the Aid pattern). Mirrored to the sheet. Tavik (Cleric) casts.

| Test | What it asserts |
|------|-----------------|
| `test_cast_heroes_feast_installs_all_markers` | Cast → 200, `feature == "heroes-feast"`, `duration_rounds == 14400`, `hp_bonus` in [2,20]; buff carries `condition_immunity_to` ⊇ {poisoned, frightened}, `save_advantage` ⊇ {WIS}, `aid_hp_bonus ≥ 2`; mirrored to the sheet `_buffs_active`. |
| `test_heroes_feast_raises_max_hp_and_heals` | A full-HP target (20/20) ends at `20 + rolled 2d10` — proves both the `aid_hp_bonus` max-raise and the install-time heal. |
| `test_cast_heroes_feast_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "heroes' feast". |
| `test_cast_heroes_feast_missing_character_id_400` | Empty body → 400. |

### `test_cast_resistance.py`
v2.505.0 — Resistance (cantrip, Cleric/Druid, PHB p.272). Phase 2 #38 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). The save-side mirror of Guidance — new `_pc_has_resistance_cantrip` helper + a `/roll` save append (`+1d4`) that consumes the buff after one save + `_SPELL_BUFF_MAP["resistance-cantrip"]` (distinct from the damage `resistance-<type>` buffs) + the `cast_resistance` endpoint. Tavik (Cleric) casts.

| Test | What it asserts |
|------|-----------------|
| `test_cast_resistance_installs_marker` | Cast → 200, `feature == "resistance"`, `duration_rounds == 10`, `concentration == true`; buff's `effects.resistance_die == true`. |
| `test_resistance_adds_d4_to_save_then_consumes` | **Gate + consume:** a DEX save after Resistance appends `+1d4` + fires `feature_used(source=resistance-cantrip)`; the buff is then gone and a second save has no `+1d4`. |
| `test_resistance_does_not_add_to_a_check` | Save-only: an ability check does NOT get the `+1d4`. |
| `test_cast_resistance_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "resistance". |
| `test_cast_resistance_missing_character_id_400` | Empty body → 400. |

### `test_cast_guidance.py`
v2.504.0 — Guidance (cantrip, Cleric/Druid, PHB p.248). Phase 2 #37 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_pc_has_guidance` helper + a `/roll` ability-check append (`+1d4`) that consumes the buff after one check + `_SPELL_BUFF_MAP["guidance"]` + the `cast_guidance` endpoint. Hub-state read. Tavik (Cleric) casts.

| Test | What it asserts |
|------|-----------------|
| `test_cast_guidance_installs_marker` | Cast → 200, `feature == "guidance"`, `duration_rounds == 10`, `concentration == true`; buff's `effects.guidance == true`. |
| `test_guidance_adds_d4_to_check_then_consumes` | **Gate + consume:** a DEX check after Guidance appends `+1d4` to the broadcast roll expression + fires `feature_used(source=guidance)`; the buff is then gone and a second check has no `+1d4`. |
| `test_cast_guidance_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "guidance". |
| `test_cast_guidance_missing_character_id_400` | Empty body → 400. |

### `test_cast_barkskin.py`
v2.503.0 — Barkskin (L2 transmutation, Druid/Ranger, PHB p.217). Phase 2 #36 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `effects.ac_floor` read in `_read_target_ac` (final AC = `max(total, 16)`) + `_SPELL_BUFF_MAP["barkskin"]` + the `cast_barkskin` endpoint. Hub-state read (no mirror). Mira (Druid) casts; the gate reads the deterministic `target_ac` from `/attack`.

| Test | What it asserts |
|------|-----------------|
| `test_cast_barkskin_installs_ac_floor` | Cast → 200, `feature == "barkskin"`, `duration_rounds == 600`, `concentration == true`; buff's `effects.ac_floor == 16`. |
| `test_barkskin_floors_low_ac_to_16` | Lyra (natural AC 14) → after Barkskin, `/attack` `target_ac == 16` (the floor lifts a sub-16 AC). |
| `test_barkskin_does_not_lower_high_ac` | Caelan (natural AC 18) → unchanged after Barkskin (proves the floor is a `max()`, not a `set()`). |
| `test_cast_barkskin_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "barkskin". |
| `test_cast_barkskin_missing_character_id_400` | Empty body → 400. |

### `test_cast_foresight.py`
v2.502.0 — Foresight (L9 divination, Bard/Druid/Warlock/Wizard, PHB p.248). Phase 2 #35 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_pc_has_foresight_advantage` helper wired into the three advantage choke-points (`_attacker_has_str_attack_advantage`, `_pc_has_rage_str_save_advantage`, the `/roll` check block) so one `effects.foresight` marker grants advantage on every attack/check/save; the buff also carries `attackers_have_disadvantage` (reusing Blur's read-site). All gates deterministic on roll-state. Thalindra casts on Krieger.

| Test | What it asserts |
|------|-----------------|
| `test_cast_foresight_installs_both_markers` | Cast → 200, `feature == "foresight"`, `duration_rounds == 4800`, `concentration == false`; buff carries `effects.foresight == true` AND `effects.attackers_have_disadvantage == true`. |
| `test_foresight_grants_advantage_on_non_str_check` | `/roll` `dex_check` on the warded creature → expression swapped to `2d20kh1` (proves all-checks, not STR-gated like Rage). |
| `test_foresight_grants_advantage_on_non_str_save` | Thalindra's Fireball (DEX save) vs the warded creature → `roll_request base_expression == "2d20kh1"` (proves all-saves). |
| `test_foresight_grants_advantage_on_attack` | The warded creature's `/attack` → `roll_state_applied` contains "advantage" (no "disadvantage"). |
| `test_cast_foresight_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "foresight". |
| `test_cast_foresight_missing_character_id_400` | Empty body → 400. |

### `test_cast_mind_blank.py`
v2.501.0 — Mind Blank (L8 abjuration, Bard/Wizard, PHB p.259). Phase 2 #34 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_SPELL_BUFF_MAP["mind-blank"]` template + `cast_mind_blank` endpoint — the charmed-condition immunity rides the existing `condition_immunity_to` gate (proven generically by `test_condition_immunity.py`); psychic-damage immunity + divination/scry/wish clauses are GM-narrated. Mirrored to the target sheet. Thalindra (Wizard) casts.

| Test | What it asserts |
|------|-----------------|
| `test_cast_mind_blank_installs_charmed_immunity` | Cast → 200, `feature == "mind-blank"`, `duration_rounds == 14400`; buff's `effects.condition_immunity_to` ⊇ {charmed}. |
| `test_cast_mind_blank_is_24h_non_concentration_mirrored` | Buff is `concentration == false` + 14400 rounds, and present in the sheet's `_buffs_active` via `/sheet-json` (the gate precondition). |
| `test_cast_mind_blank_on_ally_installs_on_ally` | Targeting an ally installs the buff on the ally, not the caster. |
| `test_cast_mind_blank_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "mind blank". |
| `test_cast_mind_blank_missing_character_id_400` | Empty body → 400. |

### `test_cast_blur.py`
v2.500.0 — Blur (L2 illusion, Sorcerer/Wizard, PHB p.219). Phase 2 #33 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_target_blur_imposes_disadvantage` read-site (target combatant hub buffs for `effects.attackers_have_disadvantage`) folded into the /attack + /npc_attack disadvantage cancel logic, + `_SPELL_BUFF_MAP["blur"]` + the self-only `cast_blur` endpoint. Thalindra (Wizard) casts; Pip attacks her for the gate test.

| Test | What it asserts |
|------|-----------------|
| `test_cast_blur_installs_attacker_disadvantage` | Cast → 200, `feature == "blur"`, `duration_rounds == 10`, target is the caster; buff's `effects.attackers_have_disadvantage == true`. |
| `test_cast_blur_is_concentration_1_minute` | Buff is `concentration == true` + 10 rounds. |
| `test_blur_imposes_disadvantage_on_attacker` | **Gate test:** Pip attacks the blurred target with `override` → the attack response's `roll_state_applied == "disadvantage_blur"`. |
| `test_cast_blur_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "blur". |
| `test_cast_blur_missing_character_id_400` | Empty body → 400. |

### `test_cast_greater_invisibility.py`
v2.499.0 — Greater Invisibility (L4 illusion, Bard/Sorcerer/Wizard, PHB p.251). Phase 2 #32 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_SPELL_BUFF_MAP["greater-invisibility"]` template + `cast_greater_invisibility` endpoint — rides the existing `effects.invisible` marker the attack-resolution intercepts already read (`_attacker_has_invisible_advantage`); concentration / 1 minute, persists through attacks/casts (unlike L2), mirrored to the target sheet. Thalindra (Wizard) casts.

| Test | What it asserts |
|------|-----------------|
| `test_cast_gi_installs_invisible_marker` | Cast → 200, `feature == "greater-invisibility"`, `duration_rounds == 10`; buff's `effects.invisible == true`. |
| `test_cast_gi_is_concentration_and_mirrored` | Buff is `concentration == true` + 10 rounds, and present in the sheet's `_buffs_active` via `/sheet-json`. |
| `test_cast_gi_on_ally_installs_on_ally` | Targeting an ally installs the buff on the ally, not the caster. |
| `test_cast_gi_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "greater invisibility". |
| `test_cast_gi_missing_character_id_400` | Empty body → 400. |

### `test_cast_stoneskin.py`
v2.498.0 — Stoneskin (L4 abjuration, Druid/Ranger/Sorcerer/Wizard, PHB p.278). Phase 2 #31 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_SPELL_BUFF_MAP["stoneskin"]` template + `cast_stoneskin` endpoint — rides the `nonmagical-<type>` resistance substrate (`_resistance_halve` via `_resistance_matches_damage`, same matcher as the Gaseous Form potion); concentration / 1 hour, mirrored to the target sheet. Thalindra (Wizard) casts.

| Test | What it asserts |
|------|-----------------|
| `test_cast_stoneskin_installs_nonmagical_resistance` | Cast → 200, `feature == "stoneskin"`, `duration_rounds == 600`; buff's `effects.resistance_to` ⊇ {nonmagical-bludgeoning, nonmagical-piercing, nonmagical-slashing}. |
| `test_cast_stoneskin_is_concentration_and_mirrored` | Buff is `concentration == true` + 600 rounds, and present in the sheet's `_buffs_active` via `/sheet-json`. |
| `test_cast_stoneskin_on_ally_installs_on_ally` | Targeting an ally installs the buff on the ally, not the caster. |
| `test_cast_stoneskin_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "stoneskin". |
| `test_cast_stoneskin_missing_character_id_400` | Empty body → 400. |

### `test_cast_protection_from_energy.py`
v2.497.0 — Protection from Energy (L3 abjuration, Cleric/Druid/Ranger/Sorcerer/Wizard, PHB p.270). Phase 2 #30 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). Sibling of Protection from Poison — `cast_protection_from_energy` rides the same `resistance_to` read-site, with the type chosen via a `damage_type` body param (acid/cold/fire/lightning/thunder), concentration / 1 hour, mirrored to the target sheet. Thalindra (Wizard) casts.

| Test | What it asserts |
|------|-----------------|
| `test_cast_pfe_installs_chosen_resistance` | `damage_type=fire` → 200, `feature == "protection-from-energy"`, `damage_type == "fire"`, `duration_rounds == 600`; buff carries `effects.resistance_to == ["fire"]`. |
| `test_cast_pfe_is_concentration_and_mirrored` | Buff is `concentration == true` + 600 rounds, and present in the sheet's `_buffs_active` via `/sheet-json` (the resistance-reader precondition). |
| `test_cast_pfe_bad_damage_type_400` | An invalid `damage_type` (e.g. necrotic) → 400. |
| `test_cast_pfe_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`. |
| `test_cast_pfe_missing_character_id_400` | Body without character_id → 400. |

### `test_cast_protection_from_poison.py`
v2.490.0 — Protection from Poison (L2 abjuration, Cleric/Druid/Paladin/Ranger, PHB p.270). Phase 2 #25 of [cast-and-broadcast-tail.md](../plans/cast-and-broadcast-tail.md). New `_SPELL_BUFF_MAP["protection-from-poison"]` template (`resistance_to: ["poison"]`, 600 rounds, non-concentration) + the `cast_protection_from_poison` endpoint. Rides the existing `_resistance_halve` read-site (same substrate as the v2.186.0 Potion of Resistance), so poison damage is genuinely halved with zero new mechanical code; the advantage-on-poison-saves + neutralize clauses stay GM-narrated. Brother Tavik Stonebrow (Cleric, GM-owned) is the cast surface; Krieger (Barbarian) is the non-caster reject.

| Test | What it asserts |
|------|-----------------|
| `test_cast_pfp_self_installs_poison_resistance` | Cleric self-targets → 200, `feature == "protection-from-poison"`, `buff_installed`, `duration_rounds == 600`; the installed buff carries `effects.resistance_to` containing `"poison"` (the real damage-pipeline read-site). |
| `test_cast_pfp_buff_is_1_hour_non_concentration` | Installed buff has `concentration == false` + `duration_rounds == 600` (1 hour RAW). |
| `test_cast_pfp_on_ally_installs_on_ally` | Targeting an ally installs the buff on the ally, not the caster (touch range). |
| `test_cast_pfp_mirrors_buff_to_sheet` | v2.496.1 — after casting, `/sheet-json` shows the buff in the sheet's `_buffs_active` (the precondition `_resistance_halve` needs to actually halve poison damage; the v2.490.0 ship missed this mirror). |
| `test_cast_pfp_non_caster_rejected` | Krieger (Barbarian) → 409 `cannot_cast`, expected string names "protection from poison". |
| `test_cast_pfp_missing_character_id_400` | Empty body → 400. |

### `test_cast_charm_person_target_cap_upcast.py`
v2.404.5 — Charm Person multi-target cap + per-slot upcast scaling (RAW PHB p.221). First **condition-shape** spell to use the v2.381.0 generalized `_SPELL_TARGET_CAPS` substrate (Mass Healing Word + Mass Cure Wounds were the heal-shape consumers before this). New entry: `max_targets: 1, base_level: 1, extra_targets_per_slot_above_base: 1`. Pure data drop — the v2.381.0 cap reader at `/cast_spell` (line ~19877) already enforces the limit before slot consumption. The save-or-suck Charmed install on a failed WIS save flows through `_SPELL_CONDITION_MAP["charm-person"]` unchanged. Thalindra Moonwhisper (Wizard Lv 7, Charm Person appended at spell index 21) is the cast surface; her L1 + L2 slots cover both base cap and +1 upcast extension.

| Test | What it asserts |
|------|-----------------|
| `test_charm_person_l1_one_target_succeeds` | L1 cast with 1 target → 200 (RAW base cap). |
| `test_charm_person_l1_two_targets_returns_400` | L1 cast with 2 targets → 400 `too_many_targets` with `{limit: 1, received: 2}`. |
| `test_charm_person_l2_two_targets_succeeds` | L2 cast with 2 targets → 200 (extended cap = 1 + (2-1)*1 = 2). |
| `test_charm_person_l2_three_targets_returns_400` | L2 cast with 3 targets → 400 with `{limit: 2, received: 3}` — confirms the upcast field is honored. |

### `test_cast_command_target_cap_upcast.py`
v2.404.7 — Command condition-install + multi-target cap (RAW PHB p.223). First **condition-install ship** of the v2.404.x arc — adds both a new `_SPELL_CONDITION_MAP["command"]` entry (key: "commanded", icon: 📢, 1-round duration, descriptive effects naming the 6 RAW commands) AND a new `_SPELL_TARGET_CAPS["command"]` entry (`max_targets: 1, base_level: 1, extra_targets_per_slot_above_base: 1`). Routes through `/cast_spell` automatically — Command's SRD JSON already carries `save_ability: "wis"`. The Commanded install on a failed save (NPC-only v1 per v2.32.0) is wired but not yet test-covered; the cap-enforcement contract is what this file asserts. Brother Tavik Stonebrow (Cleric Lv 8, Command appended at spell index 14) is the cast surface; his L1 + L2 slots cover both base cap and +1 upcast extension.

| Test | What it asserts |
|------|-----------------|
| `test_command_l1_one_target_succeeds` | L1 cast with 1 target → 200 (RAW base cap). |
| `test_command_l1_two_targets_returns_400` | L1 cast with 2 targets → 400 `too_many_targets` with `{limit: 1, received: 2}`. |
| `test_command_l2_two_targets_succeeds` | L2 cast with 2 targets → 200 (extended cap = 1 + (2-1)*1 = 2). |
| `test_command_l2_three_targets_returns_400` | L2 cast with 3 targets → 400 with `{limit: 2, received: 3}` — confirms the upcast field is honored. |

### `test_cast_animal_friendship_target_cap_upcast.py`
v2.404.8 — Animal Friendship condition-install + multi-target cap (RAW PHB p.213). Second condition-install ship of the arc on the v2.404.7 recipe. New `_SPELL_CONDITION_MAP["animal-friendship"]` entry (key: "befriended-beast", icon: 🐾, duration_rounds: 14400 = 24 hours, no concentration, descriptive effects list naming the beast-only target gate + INT 4+ immunity). New `_SPELL_TARGET_CAPS["animal-friendship"]` entry (1 + 1/slot above L1). Mira Greenleaf (Druid Lv 6, Animal Friendship appended at spell index 12) is the cast surface; her L1 + L2 slots cover both base cap and +1 upcast extension.

| Test | What it asserts |
|------|-----------------|
| `test_animal_friendship_l1_one_target_succeeds` | L1 cast with 1 target → 200 (RAW base cap). |
| `test_animal_friendship_l1_two_targets_returns_400` | L1 cast with 2 targets → 400 `too_many_targets` with `{limit: 1, received: 2}`. |
| `test_animal_friendship_l2_two_targets_succeeds` | L2 cast with 2 targets → 200 (extended cap = 1 + (2-1)*1 = 2). |
| `test_animal_friendship_l2_three_targets_returns_400` | L2 cast with 3 targets → 400 with `{limit: 2, received: 3}` — confirms the upcast field is honored. |

### `test_cast_blindness_deafness_target_cap_upcast.py`
v2.404.9 — Blindness/Deafness condition-install + multi-target cap (RAW PHB p.219). **Arc-closer** for the v2.404.x spell utility-upcast arc — first L2-base condition-install spell to use the substrate. New `_SPELL_CONDITION_MAP["blindnessdeafness"]` entry (key: "blinded", icon: 🙈, duration_rounds: 10, NOT concentration, descriptive effects naming the Blinded mechanical clauses + the end-of-turn CON save). New `_SPELL_TARGET_CAPS["blindnessdeafness"]` entry (1 + 1/slot above L2). v1 defaults to installing Blinded; the deafened-variant install + caster-picker UI are filed for follow-up. Lyra Sunstrider (Bard Lv 6, Blindness/Deafness appended at spell index 20) is the cast surface; her L2 + L3 slots cover both base cap and +1 upcast extension. SRD slug: `blindnessdeafness` (no separator).

| Test | What it asserts |
|------|-----------------|
| `test_blindness_deafness_l2_one_target_succeeds` | L2 cast with 1 target → 200 (RAW base cap). |
| `test_blindness_deafness_l2_two_targets_returns_400` | L2 cast with 2 targets → 400 `too_many_targets` with `{limit: 1, received: 2}`. |
| `test_blindness_deafness_l3_two_targets_succeeds` | L3 cast with 2 targets → 200 (extended cap = 1 + (3-2)*1 = 2). |
| `test_blindness_deafness_l3_three_targets_returns_400` | L3 cast with 3 targets → 400 with `{limit: 2, received: 3}` — confirms the upcast field is honored. |

### `test_cast_dispel_magic.py`
v2.372.0 — Dispel Magic endpoint (`/cast_dispel_magic`). Resolves auto-end (buff source-spell-level ≤ slot_level) vs ability check (`1d20 + spc_mod + prof` vs DC `10 + buff_source_level`). Slot consumed up front; buff drop on auto-end or check-success via `_remove_buff` (PC) or hub-state mutation (NPC). Lyra Sunstrider (Bard Lv 6, Dispel Magic on her list) → Krieger Stonefist driver.

| Test | What it asserts |
|------|-----------------|
| `test_dispel_magic_auto_ends_low_level_buff` | L3 cast vs L1 Bless → `auto_end: True`, buff dropped from Krieger, slot consumed (≥1 used). |
| `test_dispel_magic_check_path_high_level_buff` | L3 cast vs L5 Hold-Monster → `auto_end: False`, `check_total` populated, `check_dc: 15`; buff persistence matches `check_passed`. |
| `test_dispel_magic_no_slot_returns_409` | Lyra's L3 slots PATCH'd to 3/3 used → cast returns 409 `no_slot`. |
| `test_dispel_magic_buff_not_found_returns_409` | Target has no buff with the named key → 409 `buff_not_found`. |

### `test_cast_aid_upcast.py`
v2.371.0 — Aid upcast scaling (RAW PHB p.211). Base L2 grants +5 HP-max + +5 current HP; "At Higher Levels: a target's hit points increase by an additional 5 for each slot level above 2nd." The /cast_spell handler now materializes `aid_hp_bonus = 5 + 5 * max(0, slot_level - 2)` on the installed buff (next to the v2.97.52 Sanctuary DC + v2.97.58 Heroism stamps); both the install-time heal + the `_buff_hp_max_bonus` ceiling walk read the upcast value uniformly.

| Test | What it asserts |
|------|-----------------|
| `test_aid_base_l2_grants_5_hp` | L2 Aid cast → installed buff carries `aid_hp_bonus: 5`. |
| `test_aid_l3_upcast_grants_10_hp` | L3 Aid cast → `aid_hp_bonus: 10` (5 base + 5 per upcast level). |
| `test_aid_l5_upcast_grants_20_hp` | L5 Aid cast → `aid_hp_bonus: 20` (5 + 15). PATCHes a temporary L5 slot onto Caelan since Paladin Lv 7 only natively goes to L2. |

### `test_deflect_missiles.py`
v2.370.0 — Monk Lv 3+ Deflect Missiles auto-reduction. Mirror of v2.49.243 Uncanny Dodge auto-fire in `_apply_damage_to_combatant`, gated on v2.366.0 `is_ranged_weapon_attack`. Rolls 1d10 + DEX + Monk Lv, subtracts (floor 0), marks reaction. Kael (Monk Lv 7, DEX +4) takes Rowan's Longbow hit → reduction 12..21 + broadcast.

| Test | What it asserts |
|------|-----------------|
| `test_deflect_missiles_reduces_ranged_damage` | Longbow hit on Kael → `deflect-missiles` broadcast with `reduction_amount` in [12, 21]; `post_reduction = max(0, pre - reduction)`. |
| `test_deflect_missiles_skipped_for_melee_attack` | Rowan's Shortsword (melee) hit on Kael → no `deflect-missiles` broadcast (`is_ranged_weapon_attack` gate). |
| `test_deflect_missiles_skipped_without_reaction` | Kael's combatant has `economy.reaction: True` (already spent) → no auto-fire (mirror UD gate). |

### `test_unarmored_defense.py`
v2.369.0 — Barbarian + Monk Unarmored Defense auto-AC engine (`_pc_unarmored_defense_ac` helper + `_read_target_ac` hook). `max(stored, computed)` semantics — seeded ACs stay intact, but PATCHing an ability score auto-flows to attack-time AC reads. Closes Barbarian Lv 1 + Monk Lv 1 Unarmored Defense rows on the v2.344.3 class-content-status.md reconciliation.

| Test | What it asserts |
|------|-----------------|
| `test_barbarian_unarmored_defense_baseline` | Krieger (Barb Lv 7, DEX 14 / CON 16) → `target_ac` reads 15 (10 + 2 + 3). |
| `test_barbarian_unarmored_defense_tracks_con_bump` | PATCH Krieger CON 16 → 20 → AC auto-rises 15 → 17 (CON mod +3 → +5). |
| `test_monk_unarmored_defense_baseline` | Kael (Monk Lv 7, DEX 18 / WIS 15) → `target_ac` reads 16 (10 + 4 + 2). |
| `test_monk_unarmored_defense_tracks_wis_bump` | PATCH Kael WIS 15 → 19 → AC auto-rises 16 → 18 (WIS mod +2 → +4). |
| `test_monk_shield_disables_unarmored_defense` | Kael wielding a shield + WIS bumped to 25 → formula gate skips (Monk RAW: no shield); AC stays at the seeded 16 (the floor). |

### `test_aura_of_courage.py`
v2.368.0 — Paladin Aura of Courage (base Paladin Lv 10+). Mirror of the v2.55.0 Aura of Devotion gate but oath-agnostic (Lv 10 is the base AURA-OF-X tier) and keyed on Frightened (not Charmed). Install gate lives in `_install_buff` rather than the /respond handler — so every Frightened-install path (failed save, Demon Slayer on_hit_save, Wand of Fear cone, future fear effects) is gated uniformly. Sir Caelan is Lv 7 by default; the harness PATCHes him to Lv 10 for the happy path and uses Lyra's Fear (spell_index 19) → Krieger as the failed-save driver.

| Test | What it asserts |
|------|-----------------|
| `test_aoc_blocks_frightened_install_at_lv10` | Caelan PATCH'd to Lv 10 + in init → Lyra casts Fear at Krieger; loop until save fails → no `frightened` buff on Krieger AND `feature_used(source=aura-of-courage)` broadcast names Caelan. |
| `test_aoc_does_not_fire_at_lv9_or_below` | Control: Caelan at seed Lv 7 → failed Wis save installs Frightened normally; no AoC broadcast. |
| `test_aoc_disabled_when_paladin_unconscious` | Caelan Lv 10 but HP 0 → AoC suspends → Frightened installs; no broadcast. |

### `test_aura_of_devotion.py`
v2.55.0 — Paladin Oath of Devotion Lv 7+ Aura of Devotion. First **condition-install immunity gate** — when a failed Wis save would install Charmed on a PC ally, and any Paladin Lv 7+ with subclass `devotion` is in init, the install is BLOCKED and a `feature_used(source=aura-of-devotion)` broadcast surfaces the immunity. Distinct from Aura of Protection (save modifier): AoD acts AFTER the save resolves to bypass the consequence.

| Test | What it asserts |
|------|-----------------|
| `test_aura_of_devotion_blocks_charmed_install` | Caelan + Krieger in init; Lyra casts Suggestion at Krieger; loop until save fails → response `auto_buff_installed=""`, Krieger's buff list has no `charmed` entry, broadcast names Caelan. |
| `test_charmed_installs_when_paladin_absent` | Control: Caelan NOT in init → failed save installs Charmed normally; no AoD broadcast. |
| `test_aod_skips_non_charm_conditions` | Caelan in init + Tavik casts Hold Person → failed save installs Paralyzed (AoD is charm-only). |

### `test_mindless_rage.py`
v2.57.0 — Path of the Berserker Lv 6+ Mindless Rage. **Self-targeted** condition-install immunity gate (sibling of AoD but keyed off the saver's own active rage buff instead of an ally aura). When a failed Wis/Cha save would install Charmed or Frightened on a Barbarian and the saver has a rage buff active, the install is BLOCKED and a `feature_used(source=mindless-rage)` broadcast surfaces the immunity. Helper `_pc_has_rage_active_buff` reads the active battle combatant's buff list; gate sits next to the v2.55.0 AoD branch in `/roll_request/{id}/respond`.

| Test | What it asserts |
|------|-----------------|
| `test_mindless_rage_blocks_charmed_install` | Krieger rages (`/use_rage`); Lyra casts Suggestion at Krieger; loop until save fails → response `auto_buff_installed=""`, Krieger's buff list has no `charmed` entry, broadcast names Krieger. |
| `test_charmed_installs_when_not_raging` | Control: Krieger does NOT rage → failed save installs Charmed normally; no Mindless Rage broadcast. |
| `test_mindless_rage_skips_non_charm_fright` | Krieger rages + Tavik casts Hold Person → failed save installs Paralyzed (Mindless Rage is charm/fright-only). |

### `test_life_domain_heal_uplift.py`
v2.58.0 — Life Domain Cleric heal-uplift hook. Two stacked features fire on outgoing Lv 1+ heals: **Disciple of Life** (Lv 1+) adds 2 + slot_level HP to the target heal; **Blessed Healer** (Lv 6+) ALSO self-heals the caster for 2 + slot_level when target ≠ caster. Helper `_life_domain_heal_uplift(caster_sheet, slot_level, target_is_self)` returns `(target_uplift, self_uplift)`. Wired in the /cast_spell heal-resolution branch — target gets `heal_rolled + target_uplift` via the existing single `_apply_heal_to_combatant`; caster gets a second `_apply_heal_to_combatant` call when `self_uplift > 0`. Two `feature_used` broadcasts (`source=disciple-of-life`, `source=blessed-healer`) credit the chat card.

| Test | What it asserts |
|------|-----------------|
| `test_disciple_and_blessed_healer_on_other_target` | Tavik casts Cure Wounds (L1) at Krieger → both `disciple-of-life` (+3) and `blessed-healer` (+3) broadcasts fire. |
| `test_blessed_healer_skips_self_target` | Tavik casts Healing Word at himself → only `disciple-of-life` fires (Blessed Healer RAW requires target ≠ caster). |
| `test_no_uplift_for_non_life_domain_caster` | Control: Lyra (College of Lore Bard) casts Cure Wounds at Krieger → neither broadcast fires. |

### `test_mass_healing_word_aoe.py`
v2.59.0 — Multi-target heal loop in `/cast_spell`. Extends the v2.58.0 Life Domain hook to Mass Healing Word / Mass Cure Wounds. Single-target block handles `target_combatant_ids[0]`; new extras loop walks `[1:]` applying per-target Disciple of Life uplift and one late Blessed Healer self-heal (if not already fired). Blessed Healer is per-cast, not per-target (RAW). Extras use `cast_id=None` so undo reverts the first target only.

| Test | What it asserts |
|------|-----------------|
| `test_mass_healing_word_per_target_disciple_uplift` | Tavik casts MHW (slot 3) at Krieger + Pip → 2 `disciple-of-life` broadcasts (+5 each) + 1 `blessed-healer` broadcast. |
| `test_aoe_heal_skips_uplift_for_non_life_domain` | Single-target MHW (one target via `target_combatant_ids`) → extras loop skipped (len == 1); 1 Disciple + 1 Blessed Healer from single-target block only. |
| `test_mass_healing_word_blessed_healer_skips_self_first_target` | Tavik MHW at himself + Krieger → 2 Disciple broadcasts (self + Krieger), 1 late Blessed Healer fired from extras loop (single-target block skipped it because first target was caster). |

### `test_heal_spellcasting_mod.py`
v2.59.1 — Heal expressions bake the caster's spellcasting modifier. Pre-v2.59.1, /cast_spell rolled SRD JSON heal dice bare (e.g. Cure Wounds `1d8`). RAW: heal = dice + spellcasting modifier. `_caster_spellcasting_mod(caster_sheet)` reads the ability slug + score from the sheet; the heal-resolution branch adds the modifier to `heal_rolled` before the v2.58.0 Disciple of Life uplift. Modifier > 0 gate keeps negative-mod behavior at RAW heal floor.

| Test | What it asserts |
|------|-----------------|
| `test_cure_wounds_adds_wis_modifier_to_heal` | Tavik (WIS 16 = +3) casts Cure Wounds (L1) at Krieger 5 times. Every `auto_heal_rolled` is in [4, 11] (= 1d8 + 3). Pre-fix min was 1. |

### `test_heal_claim_uplift.py`
v2.59.2 — Legacy `/apply_healing` (chat-card "🩹 Apply Healing" button) path honors caster spellcasting modifier + Life Domain uplift. Pre-v2.59.2 the claim flow rolled bare dice — bypassed the v2.58.0 + v2.59.1 corrections. Fix: `_heal_claims[cast_id]` captures `caster_char_id` + `slot_level` at registration; /apply_healing reads them, runs the same uplift composition + broadcasts as the target-bound path.

| Test | What it asserts |
|------|-----------------|
| `test_apply_healing_runs_life_domain_uplift` | Tavik casts Cure Wounds with no target → /apply_healing routes to Tavik himself (calling user's first PC fallback) → Disciple of Life broadcast fires; Blessed Healer does NOT (RAW: only when target ≠ caster). |
| `test_apply_healing_routes_to_stored_target_and_fires_blessed_healer` | Sanity check on the target-bound path still works after the heal-claim edits: Tavik casts Cure Wounds at Krieger via target_combatant_id → Disciple + Blessed Healer both fire (v2.58.0 path unchanged). |

### `test_divine_strike.py`
v2.60.0 — Divine Strike (Life Domain Cleric Lv 8+). +1d8 radiant on first weapon hit per turn, wired into `_compute_attack_auto_uplifts`. Once-per-turn lock via `combatant.economy.divine_strike_used` (mirror of v2.20.0 Colossus Slayer flag). Companion helper `_mark_divine_strike_used` flips the flag. Client-side turn-advance handlers in tabletop.html reset the flag alongside `colossus_slayer_used`.

| Test | What it asserts |
|------|-----------------|
| `test_divine_strike_fires_on_first_weapon_hit` | Tavik (Lv 8 Life Domain) attacks Krieger with Warhammer → /attack `auto_uplifts` carries a divine-strike entry with `1d8` expression + `radiant` damage_type. |
| `test_divine_strike_locks_after_first_hit` | Same turn, second attack → divine-strike NOT in auto_uplifts (once-per-turn lock). |
| `test_divine_strike_skips_non_cleric` | Pip (Rogue) attacks Krieger → no divine-strike uplift fires (subclass gate). |

### `test_aura_range_gate.py`
v2.61.0 — F1 framework lands. New helper `_distance_ft_between_chars(db, campaign_id, char_a_id, char_b_id) → float | None` wraps the existing `_distance_ft_between_points` with Token-position lookup. Wired into AoP / AoD / Countercharm as a range gate (10/30 ft / 10/30 ft / 30 ft). Fall-back-to-no-position when token data is unavailable preserves the pre-v2.61.0 "any in init" behavior, so existing aura tests continue to pass.

| Test | What it asserts |
|------|-----------------|
| `test_aura_of_devotion_blocks_when_paladin_within_10_ft` | Caelan + Krieger 5 ft apart (1 cell on demo 70 px / 5 ft grid) → AoD range gate passes → Suggestion save-fail does NOT install Charmed, broadcast fires. |
| `test_aura_of_devotion_skips_when_paladin_outside_10_ft` | Caelan + Krieger 25 ft apart (5 cells) → AoD range gate skips → Charmed install proceeds, no broadcast. |

### `test_opportunity_attack.py`
v2.66.0 — F1 follow-ups: Aura conscious-check + Opportunity Attack trigger. `_paladin_is_conscious(char)` gates both `_aura_of_protection_bonus` and `_ally_has_aura_of_devotion` on `hp > 0 AND death_saves.status ∈ {alive, stable}`. `_check_opportunity_attack_triggers(...)` walks combatants on token move, detects from ≤ 5 ft → to > 5 ft transitions, and emits `feature_used(source="opportunity-attack-trigger")` for each provoked watcher whose reaction is available.

| Test | What it asserts |
|------|-----------------|
| `test_aura_of_protection_skips_when_paladin_unconscious` | Override Caelan to `dying` via `/death-save/override` → Thalindra Fireball at Pip → `base_expression="1d20"` (no +CHA from Caelan), no aura broadcast. |
| `test_oa_fires_when_mover_leaves_watcher_reach` | Krieger token 5 ft from Tavik (350,350 vs 420,350 on 70 px / 5 ft grid) moves to 25 ft (700,350) → move response carries `opportunity_attack_triggers` naming Tavik; `feature_used(source=opportunity-attack-trigger)` broadcast fires. |
| `test_oa_skips_when_watcher_reaction_used` | Tavik combatant seeded with `economy.reaction=True` → Krieger leaves reach → no OA trigger (RAW: needs reaction). |
| `test_oa_skips_when_move_starts_out_of_reach` | Krieger starts 25 ft from Tavik → moves further away → no OA trigger (no in-reach → out-of-reach transition). |
| `test_oa_honors_explicit_melee_reach_ft_override` | v2.66.1 — Tavik seeded with `melee_reach_ft=10` (glaive/halberd) → Krieger at 10 ft moves to 15 ft → OA fires past the 10 ft threshold; trigger carries `watcher_reach_ft=10.0`; broadcast `feature_desc` references "10 ft". |
| `test_oa_5ft_reach_still_skips_at_10ft_start` | Control for the reach override — same geometry without `melee_reach_ft` set → default 5 ft → no OA at 10 ft start. |
| `test_oa_npc_reach_parses_from_monster_action_desc` | v2.66.2 — Hill Giant TokenTemplate via SRD slug `hill-giant` (Greatclub desc contains "reach 10 ft.") → spawn token + seed battle with the giant 10 ft from Krieger → Krieger moves to 15 ft → OA fires with `watcher_reach_ft=10.0` parsed from action desc (no explicit override). |
| `test_oa_polearm_master_fires_on_enter_reach` | v2.66.4 — Tavik seeded with `polearm_master=True` + `melee_reach_ft=10` → Krieger moves from 15 ft to 10 ft → enter-reach OA fires with `trigger_type="enter"` + broadcast desc references "Polearm Master". |
| `test_oa_enter_reach_skips_without_polearm_master` | Control — same geometry, but Tavik has reach 10 ft without the Polearm Master flag → no enter-reach OA (only exit-reach fires for standard combatants). |
| `test_sentinel_fires_when_ally_attacks_target_near_watcher` | v2.66.5 — Tavik flagged with `sentinel=True`; placed 5 ft from Krieger. Krieger attacks Pip → `sentinel_triggers` lists Tavik + broadcast `feature_used(source=sentinel-attack-trigger)` desc references "Sentinel". |
| `test_sentinel_skips_when_watcher_is_the_target` | Control — Krieger attacks Tavik (the sentinel) directly → no trigger (RAW: watcher must not be the target). |
| `test_sentinel_skips_without_feat_flag` | Control — same geometry without the `sentinel` flag → no trigger. |
| `test_sentinel_fires_on_npc_attack` | v2.66.6 — Bandit NPC (SRD slug) spawned via TokenTemplate + `/npc_attack` against Pip, Tavik (sentinel) 5 ft from the bandit → response carries `sentinel_triggers` + broadcast desc names the bandit. |
| `test_oa_fires_for_npc_watcher_without_source_token_id` | v2.99.62 — bandit token + combatant with ONLY `token_template_id` + `name` (demo's `seed_encounter` shape — no `source_token_id`, no `char_id`) → Krieger moves out of reach → OA fires via the template+label Token-lookup fallback. Closes the demo "OA doesn't fire" regression. |
| `test_oa_chain_multi_npc_watchers_all_get_to_attack` | v2.99.64 — two bandit NPCs (Goon-A 5 ft east, Goon-B 5 ft south of Krieger) in the demo's exact combatant shape → drag Krieger out of both reaches in one move → 2 triggers, 1 head reaction_prompt, resolve head with `skip-oa` → 1 chained next prompt for the OTHER NPC. Regression-locks the v2.99.57 per-owner sub-queue chain for multi-NPC. |
| `test_oa_chain_multi_npc_take_the_oa_path` | v2.99.64 — parallel test that resolves the head by taking the OA → chain pop fires regardless of which reaction_key resolved the head. (v2.101.1: derives the resolve key from the prompt options — a picker `take-the-oa:{idx}` when the multi-attack NPC has one, else the generic key — per v2.99.68 fallback semantics.) |
| `test_preview_move_reports_over_range_beyond_speed` | v2.100.0 — GM over-range advisory. `preview_move` of a ~78.6 ft single drag returns `over_range: true` + `token_speed_ft > 0` + `distance_ft > token_speed_ft`, and leaves the token unmoved (read-only). |
| `test_preview_move_within_speed_not_over_range` | v2.100.0 — control: a ~7 ft drag returns `over_range: false` + `distance_ft <= token_speed_ft` so the GM client suppresses the popup. |

### `test_reaction_prompt.py`
v2.67.0 — Phase 1a of the reactions-automation plan (see [`docs/plans/reactions-automation.md`](plans/reactions-automation.md)). New `reaction_prompt` WS broadcast + `/api/campaign/{cid}/use_reaction` endpoint + in-memory `_active_reaction_prompts` registry with `prompt_id` replay guard. OA exit-reach (v2.66.0) retrofits to emit both the legacy `feature_used` advisory AND the new `reaction_prompt`. Schema v60 adds `users.reaction_prompt_mode`.

| Test | What it asserts |
|------|-----------------|
| `test_oa_exit_reach_emits_reaction_prompt` | Krieger leaves Tavik's 5 ft reach → `reaction_prompt` broadcast with `take-the-oa` option + the legacy `feature_used(source=opportunity-attack-trigger)` still fires (backward compat). |
| `test_use_reaction_marks_economy_and_resolves_prompt` | POST `/use_reaction` with the prompt_id + `reaction_key=take-the-oa` → 200, `reaction_prompt_resolved` broadcast fires, Tavik's `economy.reaction` flips to True. |
| `test_use_reaction_replay_guard` | Second POST with the same prompt_id → 409 `prompt_already_resolved`. |
| `test_use_reaction_unknown_prompt_id` | POST with a fake prompt_id → 409 `prompt_expired_or_unknown`. |
| `test_use_reaction_missing_prompt_id` | POST with no prompt_id → 400. |
| `test_reaction_prompt_mode_setting_valid` | v2.67.1 — POST `/api/settings/reaction_prompt_mode` with each of `popup` / `roll_log_only` / `off` → 200 + persisted. |
| `test_reaction_prompt_mode_setting_invalid` | Invalid mode → 400. |
| `test_uncanny_dodge_emits_reaction_prompt` | v2.67.2 — Phase 2a. NPC attacks Pip (Rogue Lv 5) for flat 6 → UD auto-halves to 3 AND emits `reaction_prompt(damage_taken)` with `uncanny-dodge-ack` option; ack POSTs cleanly resolve the prompt. |
| `test_use_reaction_marks_npc_economy_via_combatant_id` | v2.67.3 — spawn bandit NPC + Krieger 5 ft adjacent + move Krieger out of reach → OA prompt fires for the bandit → POST `/use_reaction` (no `watcher_char_id`) → bandit's `economy.reaction` flips True via `economy_update` carrying `combatant_id`. |
| `test_shield_prompt_fires_on_pc_hit` | v2.69.0 — Phase 3a. Bandit NPC swings at Thalindra (Wizard with Shield prepared + Lv 1 slot) until a hit lands → `reaction_prompt(attack_targeted)` fires with `cast-shield` option carrying class_slug + slot_level + AC preview in the label. |
| `test_cast_shield_consumes_slot_and_installs_buff` | v2.69.0 — POST `/use_reaction` with `reaction_key=cast-shield` after the prompt → 200, `economy_update` for Thalindra's reaction = True, `spell_slot_update` decrements the Lv 1 wizard slot, `feature_used(source=shield-cast)` broadcast, `buff_update` installs `shield-active` with `effects.ac_bonus=5` + `immune_magic_missile=True` + `duration_rounds=1`. |
| `test_counterspell_prompt_fires_on_pc_cast` | v2.70.0 — Phase 3b. Lyra (Bard 6 with Counterspell via Magical Secrets) casts Suggestion (L2) at Krieger while Thalindra (Wizard 5 with Counterspell + L3 slot) is positioned 5 ft from her on the active map → `reaction_prompt(spell_cast_near)` fires for Thalindra with `cast-counterspell` option whose `params.slot_level=3`, `params.spell_name="suggestion"`, `params.incoming_spell_level=2`. |
| `test_cast_counterspell_consumes_slot` | v2.70.0 — POST `/use_reaction` with `reaction_key=cast-counterspell` after the prompt → 200, `economy_update` for Thalindra's reaction = True, `spell_slot_update` decrements the L3 wizard slot, `feature_used(source=counterspell-cast)` broadcast with `outcome_hint="auto"` (L3 slot ≥ L2 incoming), `slot_level=3`, `countered_spell_name="suggestion"`. |
| `test_hellish_rebuke_prompt_fires_on_pc_damage` | v2.71.0 — Phase 3c. Krieger swings on Magnus (Warlock 5 w/ Hellish Rebuke + Pact L3 slot) until a hit lands; force `auto_apply_damage=on` via the campaign-settings form-post so `_apply_damage_to_combatant` runs (restored in finally) → `reaction_prompt(damage_taken)` fires for Magnus with `cast-hellish-rebuke` option. |
| `test_cast_hellish_rebuke_consumes_slot` | v2.71.0 — POST `/use_reaction` with `reaction_key=cast-hellish-rebuke` after the prompt → 200, `economy_update` for Magnus's reaction = True, `spell_slot_update` decrements his L3 Pact slot, `feature_used(source=hellish-rebuke-cast, damage_type=fire, damage_expr=4d10, slot_level=3)`. |
| `test_silvery_barbs_prompt_fires_on_save_pass` | v2.72.0 — Phase 3d. Krieger (Barbarian +7 STR save) rolls a DC 5 STR save via `/roll_request/{id}/respond` and trivially passes; Thalindra (Wizard 5 w/ Silvery Barbs from v2.72.0 demo seed + L1 slot) in the battle → `reaction_prompt(save_resolved)` fires for Thalindra with `cast-silvery-barbs` option whose `params.slot_level=1`, `params.target_name="Krieger Stonefist"`. The rolling character is excluded from being their own watcher. |
| `test_cast_silvery_barbs_consumes_slot` | v2.72.0 — POST `/use_reaction` with `reaction_key=cast-silvery-barbs` after the prompt → 200, `economy_update` for Thalindra's reaction = True, `spell_slot_update` decrements her L1 wizard slot, `feature_used(source=silvery-barbs-cast, slot_level=1, rerolled_target_name="Krieger Stonefist")`. |
| `test_npc_parry_prompt_fires_on_hit` | v2.73.0 — Phase 6. Krieger swings on a spawned Bandit Captain (forces `auto_apply_damage=on`) until a hit lands → `reaction_prompt(attack_targeted)` fires for the captain's combatant_id with `monster-parry` option built from `_monster_template_to_sheet(tmpl).actions[].category=="reaction"`. |
| `test_use_npc_parry_marks_reaction` | v2.73.0 — POST `/use_reaction` with `reaction_key=monster-parry` (no `watcher_char_id` for NPC) → 200, `economy_update` for the captain's reaction = True (via `combatant_id` key, not `character_id`), `feature_used(source=monster-reaction, action_name="Parry", monster_name~="Bandit Captain*")`. |
| `test_defensive_duelist_prompt_fires_on_pc_hit` | v2.74.0 — Phase 4a. Krieger swings on Lyra (Bard 6 with Defensive Duelist feat from v2.74.0 demo seed + Rapier equipped/finesse) until a hit lands → `reaction_prompt(attack_targeted)` fires for Lyra with `use-defensive-duelist` option whose `params.pb == 3` (Lyra's PB at Lv 6). |
| `test_use_defensive_duelist_marks_reaction` | v2.74.0 — POST `/use_reaction` with `reaction_key=use-defensive-duelist` after the prompt → 200, `economy_update` for Lyra's reaction = True, `feature_used(source=defensive-duelist, pb_bonus=3)`. |
| `test_mage_slayer_prompt_fires_on_spell_within_5ft` | v2.75.0 — Phase 4d. Magnus and Krieger placed 5 ft apart on the active map; Magnus casts Burning Hands at L3 → `reaction_prompt(spell_cast_near)` fires for Krieger (Mage Slayer feat from v2.75.0 demo seed + Greataxe equipped) with `take-mage-slayer-strike` option. |
| `test_use_mage_slayer_strike_marks_reaction` | v2.75.0 — POST `/use_reaction` with `reaction_key=take-mage-slayer-strike` after the prompt → 200, `economy_update` for Krieger's reaction = True, `feature_used(source=mage-slayer, caster_name="Magnus Hexbinder", spell_name="Burning Hands")`. |
| `test_war_caster_prompt_offers_cast_alongside_oa` | v2.76.0 — Phase 4c. Krieger leaves Tavik's reach (Tavik has War Caster feat from v2.76.0 demo seed + Cleric spells with `casting_time="1 action"`) → existing v2.66.0 `creature_exits_reach` prompt now includes BOTH `take-the-oa` AND `take-war-caster-cast` keys. |
| `test_use_war_caster_cast_marks_reaction` | v2.76.0 — POST `/use_reaction` with `reaction_key=take-war-caster-cast` after the prompt → 200, `economy_update` for Tavik's reaction = True, `feature_used(source=war-caster, provoker_name="Krieger Stonefist")`. |
| `test_lucky_prompt_fires_on_pc_hit` | v2.77.0 — Phase 4b. Krieger swings on Garrik (Fighter w/ Lucky feat + 3/3 Luck Points resource from v2.77.0 demo seed; long-rested in setup to ensure 3/3) until a hit lands → `reaction_prompt(attack_targeted)` fires for Garrik with `use-lucky` option whose `params.charges_before == 3`. |
| `test_use_lucky_decrements_charge` | v2.77.0 — POST `/use_reaction` with `reaction_key=use-lucky` after the prompt → 200, `economy_update` for Garrik's reaction = True, `feature_used(source=lucky, charges_after=2)` (resource decremented from 3 → 2 via in-place mutation of `sheet.resources[*].current`). |
| `test_item_reaction_prompt_includes_cloak_of_displacement` | v2.78.0 — Phase 5. Krieger swings on Lyra (Cloak of Displacement equipped from v2.78.0 demo seed + DD feat from v2.74.0) until a hit lands → `attack_targeted` prompt now includes BOTH `use-defensive-duelist` AND `item-cloak-displacement-advantage` keys. Generic `_pc_item_reactions_for_trigger` walker reads `sheet.inventory[*]._reactions[]`. |
| `test_use_item_reaction_marks_reaction` | v2.78.0 — POST `/use_reaction` with `reaction_key=item-cloak-displacement-advantage` after the prompt → 200, `economy_update` for Lyra's reaction = True, `feature_used(source=item-reaction, item_slug="cloak-of-displacement", item_name="Cloak of Displacement")`. Generic `item-*` dispatch — no per-item code required. |
| `test_uncanny_dodge_suppressed_when_dd_eligible` | v2.80.0 — PATCH Defensive Duelist onto Pip's feats; Krieger swings until a hit lands → assert NO `feature_used(source=uncanny-dodge)` auto-fire broadcast AND the `attack_targeted` prompt surfaces BOTH `cast-uncanny-dodge` AND `use-defensive-duelist`. Restores Pip's empty feats in finally. Closes the v2.74.0 filing for the Pip-vs-UD interaction. |
| `test_cast_uncanny_dodge_via_prompt_heals_back_half` | v2.80.0 — same PATCH-and-restore; POST `/use_reaction` with `cast-uncanny-dodge` → 200, `economy_update` for Pip's reaction = True, `character_hp_update(source=uncanny-dodge, delta=heal_back)` restores HP by `ceil(damage_applied / 2)`, `feature_used(source=uncanny-dodge, damage_applied, heal_back)`. |
| `test_protective_field_prompt_fires_on_pc_damage` | v2.118.0 — Phase 7. `garrik_psi_warrior` restore-safe fixture PATCHes Garrik into the Psi Warrior archetype (snapshots subclass + level via `sheet-json`, restores in finally). Krieger swings until a hit lands → `reaction_prompt(damage_taken)` fires for Garrik with `use-protective-field` option whose `params.die_size == 8` (Lv 9 → d8) + `params.target_combatant_id` matches the seeded combatant. |
| `test_use_protective_field_reduces_damage` | v2.118.0 — POST `/use_reaction` with `reaction_key=use-protective-field` after the prompt → 200, `economy_update` for Garrik's reaction = True, `feature_used(source=protective-field)` with `reduction>=1`, `psionic_die="1d8"`, `applied>=1` (the damaged combatant heals back by the reduction). |
| `test_riposte_prompt_fires_on_missed_attack` | v2.119.0 — Phase 7. `garrik_riposte_bm` restore-safe fixture PATCHes Garrik into Battle Master Lv 9 + a 4/4 Superiority Dice pool. Krieger swings on Garrik until a MISS lands → `reaction_prompt(attack_missed)` fires for Garrik with a `use-riposte:{idx}` option (one per melee weapon) whose `params.target_combatant_id` == Krieger's combatant + `params.die_size=="d8"`. |
| `test_use_riposte_resolves_counter_attack` | v2.119.0 — POST `/use_reaction` with the `use-riposte:{idx}` key after the prompt → 200, `economy_update` for Garrik's reaction = True, `resource_update(key=superiority-dice, current=3)` (die spent 4→3), `feature_used(source=riposte, attacked=True, extra_damage_on_hit>=1, dice_remaining=3)`. |
| `test_chronal_shift_prompt_fires_on_failed_save` | v2.120.0 — Phase 7. `thalindra_chronurgy` restore-safe fixture PATCHes Thalindra to Chronurgy Magic + a 2/2 Chronal Shift pool. Krieger FAILS a DC 30 STR save → `save_resolved` prompt fires for Thalindra with a `use-chronal-shift` option (works on any outcome) but NO `cast-silvery-barbs` (passed-gated, save failed). Option `params.target_combatant_id` == Krieger + `uses_before==2`. |
| `test_use_chronal_shift_decrements_uses` | v2.120.0 — POST `/use_reaction` with `reaction_key=use-chronal-shift` after the prompt → 200, `economy_update` for Thalindra's reaction = True, `resource_update(key=chronal-shift, current=1)` (use spent 2→1), `feature_used(source=chronal-shift, uses_remaining=1)`. |
| `test_protective_field_ally_prompt_fires_for_nearby_psi_warrior` | v2.121.0 — Phase 7. Garrik (patched Psi Warrior, `garrik_psi_warrior` fixture) placed one cell from Tavik on the active map; Krieger hits Tavik → `_emit_protective_field_ally_prompts` walker fires `reaction_prompt(ally_damaged_near)` for Garrik with a `use-protective-field` option whose `params.target_combatant_id` is **Tavik's** combatant (the damaged ally) + `die_size==8`. |
| `test_use_protective_field_heals_damaged_ally` | v2.121.0 — POST `/use_reaction` with `use-protective-field` after the ally prompt → 200, `economy_update` for Garrik's reaction = True, `feature_used(source=protective-field, reduction>=1, applied>=1)` (Garrik shields, Tavik heals back). |

### `test_gm_reactions_panel.py`
v2.68.0 — GM Reactions Panel (see [`docs/plans/reactions-automation.md`](plans/reactions-automation.md)). New `GET /available_reactions` + `POST /spend_reaction_manual` endpoints surface every combatant's reaction catalog to the GM and let the GM flip any reaction chip with one click. PC class features (Uncanny Dodge / Cutting Words / Indomitable), PC feats (Sentinel / Polearm Master / etc.), PC reaction spells (Shield / Counterspell / etc. via `casting_time` scan), NPC monster reactions (Parry / etc. via `category == "reaction"` walk).

| Test | What it asserts |
|------|-----------------|
| `test_available_reactions_lists_pc_class_features` | Pip (Rogue Lv 7) catalog contains `uncanny-dodge` + `reaction_used: false`. |
| `test_available_reactions_lists_npc_monster_reaction` | Bandit Captain TokenTemplate spawned + added to init → catalog includes at least one `monster-*` keyed reaction (Parry). |
| `test_spend_reaction_manual_pc` | POST `/spend_reaction_manual` for Pip's uncanny-dodge → 200, `economy_update` for Pip's reaction = True, `feature_used(source=manual-reaction)` broadcast. |
| `test_spend_reaction_manual_already_used` | Pip with `economy.reaction=True` seeded → 409 `reaction_already_used`. |
| `test_spend_reaction_manual_unknown_key` | POST with a bogus reaction_key → 400 `unknown_reaction_key`. |
| `test_available_reactions_gm_only` | alice_client (non-GM) GET → 403. |
| `test_spend_reaction_manual_gm_only` | alice_client (non-GM) POST → 403. |

### `test_use_countercharm.py`
v2.54.0 — Bard Lv 6+ Countercharm. First condition-gated save aura (only fires on spells installing charmed/frightened, not all saves). `/use_countercharm` installs a 1-round self-buff; `_ally_has_countercharm_active` reads it on save-roll construction; gate on `_SPELL_CONDITION_MAP[slug].key ∈ {charmed, frightened}` via `_spell_installs_countercharmed_condition`. Same commit adds `suggestion → Charmed` to the map.

| Test | What it asserts |
|------|-----------------|
| `test_use_countercharm_installs_buff` | POST `/use_countercharm` → 200, `buff_installed=True`, `duration_rounds=1`, `feature_used(source=countercharm)` broadcast. |
| `test_countercharm_grants_advantage_on_charm_save` | Lyra activates Countercharm then casts Suggestion at Krieger → `roll_request.base_expression="2d20kh1"` + Countercharm broadcast for Lyra. |
| `test_countercharm_skips_without_active_buff` | Control: no buff → Suggestion at Krieger → `base_expression="1d20"`; no broadcast. |
| `test_countercharm_skips_wrong_condition_spell` | Lyra DOES activate, but casts Hold Person (Paralyzed, not Charmed/Frightened) → `base_expression="1d20"`; gate is condition-keyed not save-ability-keyed. |
| `test_use_countercharm_wrong_class` | Pip (Rogue) → 409 `wrong_class` with `expected=bard`. |

### `test_aura_of_protection.py`
v2.53.0 — Paladin Lv 6+ Aura of Protection. First ally-conferred save-bonus mechanic. `_aura_of_protection_bonus(db, campaign_id, saving_char_id)` returns the CHA mod of the highest-CHA Paladin Lv 6+ in init (min +1 per RAW); 0 when no paladin qualifies or saver isn't in battle. Bonus appended to `base_expression` at roll_request creation time; same hook as Danger Sense.

| Test | What it asserts |
|------|-----------------|
| `test_aura_of_protection_grants_bonus_to_ally_save` | Caelan + Pip both in init; Thalindra casts Fireball at Pip → roll_request `base_expression == "1d20+3"` (Caelan CHA 16 → +3 mod) and feature_used(source=aura-of-protection) broadcast names Caelan. |
| `test_aura_skips_when_paladin_absent` | Control: Caelan NOT in init → `base_expression == "1d20"` (no bonus); no Aura broadcast. |
| `test_paladin_own_aura_applies_to_self` | Fireball at Caelan himself → his own aura applies (`base_expression == "1d20+3"`); broadcast still names Caelan. |

### `test_danger_sense.py`
v2.52.0 — Barbarian Lv 2+ Danger Sense. First save-roll advantage intercept; `_pc_has_danger_sense_on_dex_save(char, save_ability)` flips the d20 expression to `2d20kh1` on Dex saves. Wired into `/place_aoe` PC branch + `/cast_spell` single + AoE PC save roll_request creation. Broadcasts `feature_used` with `source: "danger-sense"`.

| Test | What it asserts |
|------|-----------------|
| `test_danger_sense_advantage_on_dex_save` | Thalindra casts Fireball at Krieger (Barbarian 5) → the roll_request broadcast carries `base_expression="2d20kh1"` AND a `feature_used(source=danger-sense)` broadcast fires for Krieger. |
| `test_danger_sense_skips_non_barbarian` | Control: Thalindra casts Fireball at Pip (Rogue 7) → `base_expression="1d20"` (no kh1); no Danger Sense broadcast. |
| `test_danger_sense_skips_non_dex_save` | Tavik casts Hold Person (WIS save) at Krieger → `base_expression="1d20"`; Danger Sense is Dex-only. |

### `test_race_save_advantage.py`
v2.99.11–v2.99.12 — (D) Phase 2 race-keyed save advantage. `_race_grants_save_advantage(sheet, save_ability, spell_slug, damage_type, is_spell_save)` returns `(applies, trait_slug, trait_name)` based on the curated `_RACE_SAVE_ADVANTAGES` table. Entries: Fey Ancestry (Elf / Half-Elf) advantage on saves vs charm install; Gnome Cunning (Rock / Forest Gnome) advantage on INT/WIS/CHA saves from spells; Dwarven Resilience (Hill / Mountain Dwarf) advantage on saves vs poison damage OR poisoned-condition install (v2.99.12 — adds `damage_types` field + `_save_damage_type_from_spell` helper + OR semantics between condition_keys and damage_types). Wired into all 3 save-roll construction sites (single-target PC save, AoE PC save, `/place_aoe` server-rolled save). Broadcasts `feature_used` with `source: <trait_slug>`.

| Test | What it asserts |
|------|-----------------|
| `test_fey_ancestry_advantage_on_charm_save` | Lyra (Half-Elf Bard) casts Suggestion at Thalindra (Elf Wizard) → Wis save, Suggestion installs Charmed → `base_expression="2d20kh1"` AND `feature_used(source=fey-ancestry)` broadcast fires for Thalindra. |
| `test_fey_ancestry_skips_non_charm_save` | Control: Lyra casts Hold Person at Thalindra → Wis save, Paralyzed install (not Charmed) → `base_expression="1d20"`; no Fey Ancestry broadcast. |
| `test_fey_ancestry_skips_non_fey_race` | Control: Lyra casts Suggestion at Tavik (Hill Dwarf Cleric) → Wis save vs Charmed but Tavik isn't Elf/Half-Elf → `base_expression="1d20"`; no Fey Ancestry broadcast. |
| `test_dwarven_resilience_advantage_on_poison_save` | Thalindra (Elf Wizard) casts Poison Spray (CON save, poison damage) at Tavik (Hill Dwarf Cleric) → Dwarven Resilience fires → `base_expression="2d20kh1"` AND `feature_used(source=dwarven-resilience)` broadcast fires for Tavik. |
| `test_dwarven_resilience_skips_non_poison_save` | Control: Fireball (Dex save, fire damage) at Tavik → Dwarven Resilience doesn't fire (poison-only) → `base_expression="1d20"`; no broadcast. |
| `test_dwarven_resilience_skips_non_dwarf_race` | Control: Poison Spray at Thalindra herself (Elf) → Dwarven Resilience doesn't fire (Elf, not Dwarf) → `base_expression="1d20"`; no broadcast. |
| `test_halfling_brave_advantage_on_fright_save` | Lyra casts Fear at Pip (Halfling Rogue) → Wis save vs Frightened install → Halfling Brave fires → `base_expression="2d20kh1"` AND `feature_used(source=halfling-brave)` broadcast for Pip. |
| `test_halfling_brave_skips_non_fright_save` | Control: Lyra casts Suggestion (Charmed install) at Pip → Halfling Brave doesn't fire (gates on Frightened only); `base_expression="1d20"`. |
| `test_halfling_brave_skips_non_halfling` | Control: Lyra casts Fear at Thalindra (Elf) → no Halfling Brave broadcast (race gate). |

### `test_halfling_lucky.py`
v2.99.13 — Halfling Lucky race-trait reroll-on-natural-1 (save-roll surface). Distinct from the v2.77.0 Lucky FEAT — Halfling Lucky is unlimited, auto-fire, only triggers on natural 1. Post-result intercept in `respond_roll_request`: after `dice_mod.roll`, if `_extract_kept_d20_from_breakdown(result.breakdown) == 1` AND the rolling PC is a Halfling, reroll the full expression once. Broadcasts `feature_used` with `source: "halfling-lucky"`. Roll note carries "🍀 Lucky reroll d20 1 → N". Uses `/api/test/dice/seed` TEST_MODE endpoint for deterministic d20=1 forcing.

| Test | What it asserts |
|------|-----------------|
| `test_halfling_lucky_rerolls_on_natural_one` | Pip (Halfling Rogue) saves vs Suggestion; seed forces d20=1 → server rerolls → roll note contains "Lucky reroll d20 1 →" AND `feature_used(source=halfling-lucky)` broadcast fires for Pip. |
| `test_halfling_lucky_skips_non_halfling` | Control: Thalindra (Elf Wizard) with seeded d20=1 → no reroll, no Lucky note, no broadcast (race trait gates on Halfling slug). |
| `test_halfling_lucky_skips_non_natural_one` | Control: Pip with d20 ≥ 10 → no reroll, no broadcast (trait only fires on natural 1). |
| `test_halfling_lucky_rerolls_on_attack_natural_one` | v2.99.21 attack-roll surface. Pip attacks a Bandit with seeded d20=1 → server rerolls + `feature_used(source=halfling-lucky)` broadcast fires for Pip. |
| `test_halfling_lucky_attack_skips_non_halfling` | Control: Garrik (Variant Human) attacks with seeded d20=1 → no reroll, no broadcast. |
| `test_halfling_lucky_rerolls_on_check_natural_one` | v2.99.22 check-roll surface. Pip rolls `1d20+4` (Stealth-shaped) with seeded d20=1 → server rerolls; `feature_used(source=halfling-lucky)` broadcast + Lucky note in the roll log. |
| `test_halfling_lucky_check_skips_non_halfling` | Control: Garrik rolls `1d20+4` with seeded d20=1 → no reroll, no broadcast. |

### `test_use_save_evasion.py`
v2.51.5 — Monk Lv 7+ (and Rogue Lv 7+) Evasion. Server-side intercept of save-for-half Dex-save damage via `_apply_evasion_to_dex_save_damage` (wired into all 7 save-damage call sites). With Evasion: save → 0, fail → half. Without: standard save → half, fail → full. Broadcasts `feature_used` with `source: "evasion"` on every fire (both branches).

| Test | What it asserts |
|------|-----------------|
| `test_evasion_save_success_zero_damage` | Thalindra casts Fireball at [bandit, Kael (Monk 7)] via AoE; loop until Kael's Dex save passes → `damage_applied == 0` and feature_used(source=evasion) broadcast fires. |
| `test_evasion_save_fail_half_damage` | Same setup; loop until Kael's save fails → `damage_applied` in 8d6's half range (4-24) and the Evasion broadcast still fires on the fail branch. |
| `test_evasion_rogue_save_success_zero_damage` | v2.51.6: Pip (Rogue Lv 7 post-bump) — Fireball at [bandit, Pip], loop until save passes → `damage_applied == 0` + feature_used(source=evasion) for Pip. Proves the helper recognizes Rogue Lv 7+ alongside Monk Lv 7+. |
| `test_non_monk7_target_standard_save_for_half` | Control: Tavik (Cleric 5, no Evasion) on save success → standard half damage (not zero); no Evasion broadcast. |

### `test_use_attack_uncanny_dodge.py`
v2.49.243 — Rogue Lv 5+ passive reaction. Server-side halving wired into `_apply_damage_to_combatant` via the new `is_attack=True` kwarg + `_target_uses_uncanny_dodge` helper. Auto-fires on the first incoming attack each round; reaction-gated (a second swing in the same round takes full damage); RAW save-spell paths intentionally don't trigger.

| Test | What it asserts |
|------|-----------------|
| `test_uncanny_dodge_halves_first_attack` | `/npc_attack` Bandit hits Pip (Rogue 5) for flat 6 damage → `damage_applied == 3`, Pip's reaction chip flips on, `feature_used` broadcast carries `source=uncanny-dodge` and Pip's name. |
| `test_uncanny_dodge_only_once_per_round` | Second swing in the same round → `damage_applied == 6` (reaction already used; no halving). |
| `test_non_rogue_target_no_halving` | Control: Bandit hits Garrik (Fighter) for flat 6 → `damage_applied == 6`, Garrik's reaction chip stays unflipped. |
| `test_save_spell_does_not_trigger_uncanny_dodge` | `/npc_cast_spell` Sacred Flame DEX save against Pip → Pip's reaction chip stays unflipped (RAW: UD only fires on attack rolls, not on save spells). |

### `test_use_open_hand_technique.py`
v2.49.57 — Monk subclass feature `POST /use_open_hand_technique` (Way of the Open Hand, Lv 3+). Three modes: `prone` (DEX save → Prone via new `open-hand-prone` map entry), `push` (STR save → response carries `push_authorized` for the GM to drag the token; no buff), `no_reactions` (no save → inline install of `reaction-denied` buff). No ki cost — RAW the Flurry of Blows already paid. Same trust-the-caller convention as Stunning Strike for the "must follow a Flurry hit" gate.

| Test | What it asserts |
|------|-----------------|
| `test_open_hand_prone_happy_path_npc` | Kael uses prone on a bandit; retry until DEX save fails; assert `auto_save_buff_installed=Prone`, `concentration=False` on the broadcast buff, `source_char_id=Kael`. |
| `test_open_hand_push_npc` | Kael uses push on a bandit; assert `push_authorized` is the boolean inverse of `auto_save_passed`. No buff installed either way. |
| `test_open_hand_push_moves_target_on_failed_save` | v2.99.434 — Phase 6.3. Kael (placed above the bandit) loops until the bandit fails its STR save, then asserts `push_applied` is True + the bandit's real NPC token moved +210 px (3 cells / 15 ft) via `_force_move`; a passed save moves nothing. NPC token created via `POST /tokens` (linked as `source_token_id`) + torn down at the end. |
| `test_open_hand_no_reactions_npc` | Kael uses no_reactions on a bandit; assert `buff_installed=No Reactions (Open Hand)`, `reaction-denied` key on the bandit's buff list, `duration_rounds=1`, no `auto_save_prompted`. |
| `test_open_hand_wrong_class` | Krieger (Barbarian) → 409 `wrong_class` with `expected=monk`. |
| `test_open_hand_bad_mode` | Invalid `mode` string → 400. |
| `test_open_hand_prone_pc_installs_prone` | v2.49.65 — closes the v2.49.57 filed item. Magnus pre-cast Hex (concentrating); Kael uses Open Hand prone on Magnus → roll_request; GM-as-Magnus /responds; on save fail assert (a) Prone lands, (b) Magnus's Hex SURVIVES (Prone isn't in `_INCAPACITATING_BUFF_KEYS` — regression guard that the v2.49.51 hook does NOT fire for non-incapacitating condition buffs). Retry loop on DEX save. |
| `test_open_hand_push_pc_no_buff` | v2.49.65 — push PC path. Kael shoves Magnus → roll_request; GM responds → assert `auto_buff_installed=""` (no `_SPELL_CONDITION_MAP` entry for `open-hand-push`); Magnus's buff list carries no prone / no reaction-denied. Both deterministic (no save-outcome dependency). |
| `test_open_hand_no_reactions_pc` | v2.49.65 — no_reactions PC path. Inline `_install_buff` of `reaction-denied`; verify it lands in BOTH hub and sheet mirror; 🫷 public log names Kael + Magnus. |

### `test_swap_preserves_paired_buffs.py`
v2.49.54 — closes the bug filed in v2.49.53. The swap loop in `_install_buff` no longer drops `concentration: True` buffs sourced by another caster. RAW: the one-concentration-at-a-time rule applies only to the combatant's OWN concentration spells; a paired condition (e.g. Paralyzed on a Hold Person victim) is sustained by the SOURCE caster and must persist independently.

| Test | What it asserts |
|------|-----------------|
| `test_paired_buff_preserved_when_caster_swaps` | Magnus pre-seeded with Paralyzed (source=99999 enemy). Cast Hex → Paralyzed PRESERVED + Hex installed. Pre-fix the swap loop wrongly dropped Paralyzed. |
| `test_own_anchor_swap_still_works` | Regression guard: own anchor (concentration-bless, source=Magnus) is STILL replaced by Hex. The source filter must not over-broaden. |

### `test_swap_concentration_log.py`
v2.49.53 — closes the four-emoji concentration audit set with 🔁 for swap-replaced-by-new-cast. The RAW one-concentration-at-a-time rule already silently dropped the old anchor; this commit adds the GM log breadcrumb naming `old → new`. Filtered by `source_char_id` so paired buffs (concentration=True but sourced by another caster) don't generate spurious 🔁 logs even when the (pre-existing, separately-filed) swap-loop bug drops them.

| Test | What it asserts |
|------|-----------------|
| `test_swap_own_anchor_emits_swap_log` | Pre-seed Magnus with `concentration-bless` (own-anchor); cast Hex → `🔁 Magnus swapped concentration: Bless → Hex` with breakdown naming the swap. Uses `/battle` PUT to seed because the demo lacks two separate concentration endpoints for any single PC. |
| `test_swap_paired_buff_does_not_emit_log` | Pre-seed Magnus with `paralyzed` sourced by enemy_id=99999 (mimics Hold Person victim). Cast Hex → swap loop drops the paired buff (pre-existing bug) but 🔁 log MUST NOT fire. |
| `test_no_prior_concentration_no_swap_log` | Cast Hex on Magnus with no prior concentration → fresh install, no 🔁 log (nothing was replaced). |

### `test_voluntary_end_concentration_log.py`
v2.49.52 — closes the third concentration-log cause: voluntary `/end_buff` on a caster's own concentration anchor emits a ✋ GM-only roll-log entry. Completes the three-emoji audit set (💔 failed save / 💀 incapacitated / ✋ voluntary).

| Test | What it asserts |
|------|-----------------|
| `test_voluntary_end_concentration_emits_palm_log` | Magnus casts Hex; `/end_buff` on hex → broadcast type=roll with note `✋ Magnus lost concentration on Hex` and breakdown `Concentration ends — voluntary`. |
| `test_voluntary_end_non_concentration_buff_no_log` | Krieger has Rage (concentration=False); `/end_buff` on rage emits NO ✋ log. The audit is scoped to concentration anchors only. |
| `test_voluntary_end_paired_condition_no_log` | Tavik Hold-Persons Magnus → Magnus has Paralyzed (concentration=True, source=Tavik). Magnus `/end_buff` on paralyzed → NO ✋ log because the victim isn't the one concentrating; Tavik still is. |

### `test_incapacitation_drops_concentration.py`
v2.49.51 — RAW PHB p.203 "you also lose concentration on a spell if you are incapacitated." Closes the non-damage incapacitation gap filed in v2.49.49. `_install_buff` now detects when the incoming buff is in `_INCAPACITATING_BUFF_KEYS` (paralyzed / incapacitated / stunned / petrified / unconscious / asleep) and drops the target's OWN concentration anchors + emits a 💀 GM log naming the incapacitating buff as the cause. `_drop_caster_concentration` now filters by `source_char_id` so paired condition buffs (sustained by another caster) aren't swept.

| Test | What it asserts |
|------|-----------------|
| `test_paralyzed_pc_drops_own_concentration` | Magnus has Hex; Tavik casts Hold Person → save fails → Paralyzed lands on Magnus → Hex drops + 💀 log fires naming "Paralyzed" + "incapacitated" in breakdown. Paralyzed buff itself is preserved. |
| `test_charmed_pc_keeps_own_concentration` | Regression guard: non-incapacitating Charmed via Charm Person does NOT drop Hex. Gracefully skips if the seed doesn't expose Charm Person at the expected spell index. |
| `test_source_caster_concentration_still_cascades` | v2.49.51's `source_char_id` filter doesn't regress the v2.38.0 paired cleanup: ending Tavik's `concentration-hold-person` still cascade-removes Magnus's Paralyzed buff. |

### `test_concentration_skull_log.py`
v2.49.50 — distinguishes 💀 incapacitation drops from 💔 failed-save drops in the GM-only roll-log. The broadcast shape is unchanged (still `type=roll` with `visibility=gm_only`); the note text + breakdown carry the cause. Closes the v2.49.48 Filed item.

| Test | What it asserts |
|------|-----------------|
| `test_zero_hp_forced_drop_emits_skull_log` | Damage drops Magnus to 0 HP → note starts with 💀, breakdown contains "incapacitated" + "0 HP" + "would have been" (rolled save preserved for telemetry). |
| `test_failed_con_save_still_emits_heart_log` | Damage above 0 HP + failed CON save → note still starts with 💔. Regression guard against over-broadening the fix. Retry loop because the d20 is random. |
| `test_override_to_dead_emits_skull_log` | GM overrides Magnus → dead while Hex'd → 💀 log with breakdown naming "GM override → dead". Caster name from combatant name (not "PC {id}"). |
| `test_roll_3_failures_emits_skull_log` | `roll_death_save` 3rd-failure branch → 💀 log with breakdown naming "death saves". Distinct reason string from override path. Retry loop on the d20. |

### `test_death_save_drops_concentration.py`
v2.49.49 — RAW PHB p.203: concentration ends when the caster is incapacitated or killed. The v2.49.48 0-HP rule covered damage-induced drops, but the death-save endpoints (`POST /death-save` rolling, `POST /death-save/override` GM force) didn't go through `_maybe_concentration_save`. Both branches now call `_drop_caster_concentration` so 3 failed saves → dead, or a GM override to dying/stable/dead, also drops concentration.

| Test | What it asserts |
|------|-----------------|
| `test_override_to_dead_drops_concentration` | GM overrides Magnus to status=dead via `POST /death-save/override` → `buff_update` broadcasts a new buff list with `hex` removed; live `/buffs` re-fetch confirms. |
| `test_roll_3_failures_drops_concentration` | Dying Magnus reaches 3 failures → status transitions to dead → `buff_update` fires with `hex` absent. Uses override(failures=3, status=dead) which exercises the same `_drop_caster_concentration` codepath. |
| `test_override_to_alive_does_not_drop_concentration` | Guard against over-broad fix: override(alive) on an alive PC does not emit a hex-dropping `buff_update`; the buff stays installed. |

### `test_concentration_cleanup.py`
Phase T.3e — concentration drop cascades to paired condition buffs.

| Test | What it asserts |
|------|-----------------|
| `test_save_or_suck_installs_caster_concentration` | Cast Hold Person at a bandit who fails the save → caster gains `concentration-hold-person` anchor buff (loops up to 20 attempts). |
| `test_end_concentration_drops_caster_buff` | `/end_buff` on the caster's concentration removes it; paired NPC buff drop happens server-side via the cleanup helper. |
| `test_concentration_break_emits_gm_only_log` | v2.39.0: failed CON save on damage emits a `roll`-type event with `visibility: "gm_only"` narrating "💔 NAME lost concentration on SPELL — dropped: …". |
| `test_non_concentration_buff_removal_unaffected` | Removing Rage on Krieger (non-concentration) still works post-T.3e change. |

### `test_battle.py`
v2.101.0 — battle hub persistence + the new `GET /api/campaign/{id}/battle` endpoint. The hub is now a write-through cache over the `battles` table; the GET reads the persisted row from the DB.

| Test | What it asserts |
|------|-----------------|
| `test_battle_put_persists_and_get_round_trips` | PUT a battle (Pip combatant, active, round 1) → 200 `{"ok": True}`; GET returns `{"battle": {...}}` from the DB with `active=True`, `round=1`, and the seeded combatant; a fresh WS connect replays the state as a `battle_update`. |
| `test_battle_put_requires_gm` | A non-GM player's `PUT /battle` → 403 (the write gate the viewer-readable GET deliberately doesn't share). |

### `test_movement_lock.py`
v2.102.0 — campaign movement lock (Phase 1 server core) + v2.104.0 Phase 3 request/approve flow. GM toggles `campaign.movement_locked` via `POST /movement_lock`; non-GM `/token/move` drags are gated 409 while locked; players request a one-token unlock via `POST /movement_request`, the GM approves/denies via `/movement_request/{id}/respond`.

| Test | What it asserts |
|------|-----------------|
| `test_movement_lock_blocks_player_gm_passes` | GM `POST /movement_lock {locked:true}` → 200 `{ok, locked:true}` + a `movement_lock_update(locked=true)` broadcast; alice's drag of Pip → 409 `movement_locked` (with `token_id`); the GM's drag of the same token → 200 (arbiter); unlocking restores alice's move to 200. Unlocks in a `finally` so a failure doesn't strand the campaign locked. |
| `test_movement_lock_requires_gm` | A non-GM player's `POST /movement_lock` → 403. |
| `test_movement_request_approve_grants_one_move` | While locked, alice `POST /movement_request {token_id}` → 200 `{ok, request_id}` + GM `movement_request` broadcast (request_id / token_id / character_id); GM `respond {approved:true}` → 200 + alice `movement_request_resolved(approved, requester_user_id)`; the one-shot grant lets her FIRST locked drag 200, the SECOND 409 `movement_locked`. |
| `test_movement_request_deny_keeps_player_blocked` | GM `respond {approved:false}` → 200; alice's drag stays 409 (no grant issued). |
| `test_movement_request_unknown_token` | `movement_request` for a token not in this campaign → 404. |
| `test_respond_movement_request_requires_gm` | Non-GM `respond` → 403 (GM gate fires before the request lookup). |
| `test_respond_unknown_movement_request` | GM `respond` on an unknown/expired request id → 404. |

### `test_use_reroll.py`
v2.105.0 — generic reroll framework (Phase 1: Lucky feat). `POST /use_reroll` spends a reroll feature to reroll a roll-log card's d20; the `/roll` broadcast carries `reroll_options`. Uses demo Fighter Garrik Ironside (Lucky feat + 3 luck points).

| Test | What it asserts |
|------|-----------------|
| `test_lucky_reroll_keeps_better_and_decrements` | A d20 rolled as Garrik broadcasts a `lucky` reroll_option (`remaining=3`, `keep="better"`); `POST /use_reroll {feature_key:"lucky"}` → 200, decrements 3→2, kept d20 ≥ original (swaps in only when the new d20 strictly beats it), and fires `roll(reroll_feature="lucky")` + `feature_used(source="lucky-reroll")` + `resource_update(key="lucky", current=2)`. |
| `test_reroll_unknown_feature` | An unknown `feature_key` → 404 `unknown_feature` (checked before the roll lookup). |
| `test_reroll_feature_not_available` | A character without the feature (Pip) → 409 `out_of_uses`. |
| `test_reroll_no_d20` | A non-d20 roll (`2d6`) offers no reroll_option and `/use_reroll` → 409 `no_d20`. |
| `test_save_offers_lucky_and_indomitable_and_indomitable_takes_new` | v2.107.0 — a Lv 9 Fighter's SAVE roll (`stat_key="wis_save"`) offers both `lucky` (any) and `indomitable` (save-only); `/use_reroll {feature_key:"indomitable"}` → `took_new=True` (keep="new") + resource decrements 1→0. |
| `test_indomitable_hidden_on_non_save` | v2.107.0 — a non-save d20 for the same Fighter offers `lucky` but NOT the save-only `indomitable` (applies-gating). |

### `test_battle_put_npc_concentration_cascade.py`
v2.99.185 — `/battle PUT` auto-fires `_drop_paired_concentration_buffs_npc` when an NPC's concentration buff is removed via the canonical battle-edit path. Closes the v2.99.179 filed item; completes the Polymorph mechanical chain for NPC casters via the routine UI path.

| Test | What it asserts |
|------|-----------------|
| `test_battle_put_drops_npc_concentration_buffs` | Seed NPC with `concentration-polymorph` buff + Krieger with a `polymorph-active` marker sourced from the NPC. `/battle PUT` with the NPC's concentration buff removed → the NPC-mirror cascade fires + the v2.99.172 revert hook drops Krieger's polymorph-active marker. |

### `test_battle_put_pc_concentration_cascade.py`
v2.99.191 — PC mirror of v2.99.185. `/battle PUT` auto-fires `_drop_paired_concentration_buffs` when a PC's concentration buff is removed via the canonical battle-edit path. Closes the `/battle PUT` parallel for PC casters (PC `/end_buff` was already covered by `_remove_buff`'s cascade hook).

| Test | What it asserts |
|------|-----------------|
| `test_battle_put_drops_pc_paired_buffs` | Seed Magnus with `concentration-hold-person` + Krieger with paired Paralyzed (`source_char_id=Magnus`, `_dependent_on_caster_concentration=True`). `/battle PUT` with Magnus's concentration removed → PC cascade fires → Krieger's Paralyzed is dropped from his sheet mirror. |

### `test_npc_cast_subtle_immune.py`
v2.99.186 — `/npc_cast_spell` mirrors the PC Subtle gate. Closes a v2.99.173 filed item; an NPC carrying `metamagic-subtle-pending` on its combatant suppresses the Counterspell prompt the same way a PC caster does.

| Test | What it asserts |
|------|-----------------|
| `test_npc_cast_subtle_suppresses_counterspell_prompt` | Seed a synthetic NPC with `metamagic-subtle-pending` on its combatant + Thalindra (Counterspell on sheet) as a PC watcher. `/npc_cast_spell` → cast payload carries `was_subtle: True`, the 🤫 `metamagic-subtle-spell-consumed` `feature_used` fires, and no `reaction_prompt(spell_cast_near)` is emitted for the cast. |

### `test_hunters_mark_duration_scaling.py`
v2.405.0 — spell-utility-mechanical-depth Phase 1: duration-scaling substrate. `_SPELL_DURATION_MAP` registry + `_spell_duration_rounds_for_slot()` helper replace the hardcoded per-slot duration ladder at `/cast_hunters_mark`. Rowan Quickbow's slot table PATCH'd up to L5 so all three tiers are reachable.

| Test | What it asserts |
|------|-----------------|
| `test_hunters_mark_l1_routes_1h_duration` | Cast at L1 → substrate returns 600 rounds (1 hour); installed buff's `duration_label == "1h"`. Lower-tier branch. |
| `test_hunters_mark_l3_routes_8h_duration` | Cast at L3 → substrate returns 4800 rounds (8 hours); `duration_label == "8h"`. Middle-tier branch. |
| `test_hunters_mark_l5_routes_24h_duration` | Cast at L5 → substrate returns 14400 rounds (24 hours); `duration_label == "24h"`. Upper-tier branch. |

### `test_hunters_mark_twinned_install.py`
v2.99.187 — `/cast_hunters_mark` folds the Twinned second target into the installed buff's rider field (`effects.weapon_hit_bonus_target_combatant_id`), not just the response. The weapon-hit rider consumer at line ~21498 accepts list-or-string.

| Test | What it asserts |
|------|-----------------|
| `test_hunters_mark_twinned_installs_list_rider` | Rowan casts Hunter's Mark with Twinned armed + a second target seeded. Response carries `twinned_target_combatant_id_2`; Rowan's installed `hunters-mark` buff carries a list-shape `effects.weapon_hit_bonus_target_combatant_id` containing both targets + a top-level `target_combatant_ids` list mirroring both. |
| `test_hunters_mark_no_twinned_keeps_single_rider` | Control: cast Hunter's Mark with no Twinned pending. The buff's `effects.weapon_hit_bonus_target_combatant_id` remains a single string (backward compat with pre-v2.99.187 serialized buffs + `/cast_hex`'s still-singular field). |

### `test_hunters_mark_twinned_broadcast.py`
v2.99.188 — `/cast_hunters_mark` install broadcast names both targets when Twinned fires + stamps the weapon-hit rider with `vs_combatant_id` for downstream attack-chat-card labeling.

| Test | What it asserts |
|------|-----------------|
| `test_twinned_install_broadcast_names_both_targets` | Rowan casts Hunter's Mark with Twinned armed. The `feature_used` install broadcast's `feature_name` + `feature_desc` mention both targets, and the new metadata fields fire: `target_names` is a 2-element list, `twinned_target_combatant_id_2` matches the second target ID, `twinned_target_name` resolves to the second target's display name. |
| `test_no_twinned_broadcast_keeps_single_target` | Control: cast without Twinned pending. The install broadcast keeps the single-target shape — `target_names` is a singleton, `twinned_target_combatant_id_2` + `twinned_target_name` are falsy. |

### `test_bestow_curse_duration_scaling.py`
v2.405.2 — spell-utility-mechanical-depth Phase 1: duration-scaling substrate, third consumer + first `"permanent"` marker. The `_SPELL_DURATION_MAP` "bestow-curse" entry replaces `/cast_bestow_curse`'s flat 10-round stamp with the RAW 5-tier upcast ladder. Thalindra Moonwhisper is armed with Bestow Curse + an L1-L9 wizard slot table (snapshot + restored on teardown — the spell isn't on any demo PC's native list).

| Test | What it asserts |
|------|-----------------|
| `test_bestow_curse_l3_routes_1min` | Cast at L3 → 10 rounds (1 min); response `duration_label == "1min"`, `duration_rounds == 10`. Base tier. |
| `test_bestow_curse_l4_routes_10min` | Cast at L4 → 100 rounds (10 min); `duration_label == "10min"`, `duration_rounds == 100`. |
| `test_bestow_curse_l5_routes_8h` | Cast at L5 → 4800 rounds (8 hours); `duration_label == "8h"`, `duration_rounds == 4800`. |
| `test_bestow_curse_l7_routes_24h` | Cast at L7 → 14400 rounds (24 hours); `duration_label == "24h"`, `duration_rounds == 14400`. |
| `test_bestow_curse_l9_routes_permanent` | Cast at L9 → `"permanent"` marker (until dispelled); `duration_label == "permanent"`. First consumer of the substrate's marker-string path. |

### `test_cast_geas.py`
v2.406.0 — new `/cast_geas` endpoint + duration-scaling substrate, fourth consumer (first NEW endpoint built on the substrate). RAW L5 Enchantment, 60 ft, not concentration. Substrate `"geas"` entry uses calendar markers (`"30d"` / `"1y"` / `"permanent"`). Thalindra Moonwhisper is armed with Geas + an L5-L9 wizard slot table (snapshot + restored on teardown).

| Test | What it asserts |
|------|-----------------|
| `test_geas_l5_routes_30d` | L5 cast → 200; response `duration_label == "30d"`, `range_ft == 60`, `concentration is False`. Base tier. |
| `test_geas_l7_routes_1y` | L7 cast → `duration_label == "1y"`. Middle tier. |
| `test_geas_l9_routes_permanent` | L9 cast → `duration_label == "permanent"` (until dispelled). Reuses the marker path. |
| `test_geas_missing_character_id_400` | Missing character_id → 400. |
| `test_geas_low_slot_400` | slot_level=4 → 400 (Geas is L5). |
| `test_geas_wrong_class_409` | class_slug=barbarian (not a Geas class) → 409 `wrong_class`. |
| `test_geas_spell_not_known_409` | Wizard without Geas on her list → 409 `spell_not_known` (fires before the slot lookup; no slot patching needed). |

### `test_cast_private_sanctum.py`
v2.413.0 — new `/cast_private_sanctum` endpoint, the fifth and final consumer of the Phase 2 AoE-radius scaling substrate and the third cube-edge shape (after Create or Destroy Water and Creation), closing the arc. RAW L4 Abjuration, 120 ft, 24 hours, no save, not concentration; secures a cube up to 100 ft on a side. The cube edge scales +100 ft per slot above 4th — the largest increment in the substrate (L4 → 100, L5 → 200, L6 → 300, L9 → 600); surfaces `cube_ft`. Cast by Thalindra Moonwhisper (Wizard Lv 7), armed via a snapshot/restore fixture (L4-L9 wizard slots); a separate strip-fixture covers the spell_not_known path.

| Test | What it asserts |
|------|-----------------|
| `test_private_sanctum_l4_routes_100ft` | L4 cast → 200; `cube_ft == 100`, `range_ft == 120`, `concentration is False`. Base tier. |
| `test_private_sanctum_l5_routes_200ft` | L5 cast → `cube_ft == 200` (+100 over base). |
| `test_private_sanctum_l6_routes_300ft` | L6 cast → `cube_ft == 300` (100 + 2×100). |
| `test_private_sanctum_l9_routes_600ft` | L9 cast → `cube_ft == 600` (100 + 5×100). Top in-table slot. |
| `test_private_sanctum_missing_character_id_400` | Missing character_id → 400. |
| `test_private_sanctum_low_slot_400` | slot_level=3 → 400 (Private Sanctum is L4). |
| `test_private_sanctum_wrong_class_409` | class_slug=cleric (not a Private Sanctum class) → 409 `wrong_class`. |
| `test_private_sanctum_spell_not_known_409` | Wizard without Private Sanctum on her list → 409 `spell_not_known` (fires before the slot lookup). |

### `test_cast_creation.py`
v2.412.0 — new `/cast_creation` endpoint + the Phase 2 AoE-radius scaling substrate, fourth consumer and the second cube-edge shape (after Create or Destroy Water). RAW L5 Illusion, 30 ft, special duration, no save; conjures an object no larger than a 5-ft cube. The cube edge scales +5 ft per slot above 5th (L5 → 5, L6 → 10, L7 → 15, L9 → 25); surfaces `cube_ft`. Cast by Thalindra Moonwhisper (Wizard Lv 7), armed via a snapshot/restore fixture (L5-L9 wizard slots); a separate strip-fixture covers the spell_not_known path.

| Test | What it asserts |
|------|-----------------|
| `test_creation_l5_routes_5ft` | L5 cast → 200; `cube_ft == 5`, `range_ft == 30`, `concentration is False`. Base tier. |
| `test_creation_l6_routes_10ft` | L6 cast → `cube_ft == 10` (+5 over base). |
| `test_creation_l7_routes_15ft` | L7 cast → `cube_ft == 15` (5 + 2×5). |
| `test_creation_l9_routes_25ft` | L9 cast → `cube_ft == 25` (5 + 4×5). Top in-table slot. |
| `test_creation_missing_character_id_400` | Missing character_id → 400. |
| `test_creation_low_slot_400` | slot_level=4 → 400 (Creation is L5). |
| `test_creation_wrong_class_409` | class_slug=cleric (not a Creation class) → 409 `wrong_class`. |
| `test_creation_spell_not_known_409` | Wizard without Creation on her list → 409 `spell_not_known` (fires before the slot lookup). |

### `test_cast_create_or_destroy_water.py`
v2.411.0 — new `/cast_create_or_destroy_water` endpoint + the Phase 2 AoE-radius scaling substrate, third consumer and the FIRST cube-edge shape (after the two sphere-radius consumers Fog Cloud + Confusion). RAW L1 Transmutation, 30 ft, instantaneous, no save; rain/destroy-fog mode fills a 30-ft cube. The cube edge scales +5 ft per slot above 1st (L1 → 30, L2 → 35, L5 → 50, L9 → 70); surfaces `cube_ft`. Cast by Brother Tavik Stonebrow (Cleric Lv 8), armed via a snapshot/restore fixture (L1-L9 cleric slots); a separate strip-fixture covers the spell_not_known path.

| Test | What it asserts |
|------|-----------------|
| `test_cdw_l1_routes_30ft` | L1 cast → 200; `cube_ft == 30`, `range_ft == 30`, `concentration is False`. Base tier. |
| `test_cdw_l2_routes_35ft` | L2 cast → `cube_ft == 35` (+5 over base). |
| `test_cdw_l5_routes_50ft` | L5 cast → `cube_ft == 50` (30 + 4×5). |
| `test_cdw_l9_routes_70ft` | L9 cast → `cube_ft == 70` (30 + 8×5). Top in-table slot. |
| `test_cdw_missing_character_id_400` | Missing character_id → 400. |
| `test_cdw_low_slot_400` | slot_level=0 → 400 (Create or Destroy Water is L1). |
| `test_cdw_wrong_class_409` | class_slug=wizard (not a Create/Destroy Water class) → 409 `wrong_class`. |
| `test_cdw_spell_not_known_409` | Cleric without the spell on his list → 409 `spell_not_known` (fires before the slot lookup). |

### `test_cast_confusion.py`
v2.410.0 — new `/cast_confusion` endpoint + the Phase 2 AoE-radius scaling substrate, second consumer (after `/cast_fog_cloud`). RAW L4 Enchantment, 90 ft, concentration, WIS save, 10-ft-radius sphere. The radius scales +5 ft per slot above 4th (L4 → 10, L5 → 15, L6 → 20, L9 → 35). Thalindra Moonwhisper is armed with Confusion + an L4-L9 wizard slot table (snapshot + restored on teardown).

| Test | What it asserts |
|------|-----------------|
| `test_confusion_l4_routes_10ft` | L4 cast → 200; `radius_ft == 10`, `range_ft == 90`, `concentration is True`. Base tier. |
| `test_confusion_l5_routes_15ft` | L5 cast → `radius_ft == 15` (+5 over base). |
| `test_confusion_l6_routes_20ft` | L6 cast → `radius_ft == 20` (10 + 2×5). |
| `test_confusion_l9_routes_35ft` | L9 cast → `radius_ft == 35` (10 + 5×5). Top in-table slot. |
| `test_confusion_missing_character_id_400` | Missing character_id → 400. |
| `test_confusion_low_slot_400` | slot_level=3 → 400 (Confusion is L4). |
| `test_confusion_wrong_class_409` | class_slug=cleric (not a Confusion class) → 409 `wrong_class`. |
| `test_confusion_spell_not_known_409` | Wizard without Confusion on her list → 409 `spell_not_known` (fires before the slot lookup). |

### `test_cast_fog_cloud.py`
v2.409.0 — new `/cast_fog_cloud` endpoint + the Phase 2 AoE-radius scaling substrate (`_SPELL_AOE_MAP` + `_spell_aoe_for_slot()`), first consumer. RAW L1 Conjuration, 120 ft, concentration, no save, 20-ft-radius sphere of heavy obscurement. The radius scales +20 ft per slot above 1st (L1 → 20, L2 → 40, L5 → 100, L9 → 180). Thalindra Moonwhisper is armed with Fog Cloud + an L1-L9 wizard slot table (snapshot + restored on teardown).

| Test | What it asserts |
|------|-----------------|
| `test_fog_cloud_l1_routes_20ft` | L1 cast → 200; `radius_ft == 20`, `range_ft == 120`, `concentration is True`. Base tier. |
| `test_fog_cloud_l2_routes_40ft` | L2 cast → `radius_ft == 40` (+20 over base). |
| `test_fog_cloud_l5_routes_100ft` | L5 cast → `radius_ft == 100` (20 + 4×20). |
| `test_fog_cloud_l9_routes_180ft` | L9 cast → `radius_ft == 180` (20 + 8×20). Top in-table slot. |
| `test_fog_cloud_missing_character_id_400` | Missing character_id → 400. |
| `test_fog_cloud_low_slot_400` | slot_level=0 → 400 (Fog Cloud is L1). |
| `test_fog_cloud_wrong_class_409` | class_slug=cleric (not a Fog Cloud class) → 409 `wrong_class`. |
| `test_fog_cloud_spell_not_known_409` | Wizard without Fog Cloud on her list → 409 `spell_not_known` (fires before the slot lookup). |

### `test_cast_modify_memory.py`
v2.408.0 — new `/cast_modify_memory` endpoint + duration-scaling substrate, sixth consumer (third NEW endpoint) and the final Phase 1 spell. RAW L5 Enchantment, 30 ft, concentration, single target, WIS save. Substrate `"modify-memory"` entry uses five markers ("10min" / "1h" / "24h" / "7d" / "permanent"), one per slot level L5-L9. Thalindra Moonwhisper is armed with Modify Memory + an L5-L9 wizard slot table (snapshot + restored on teardown).

| Test | What it asserts |
|------|-----------------|
| `test_modify_memory_l5_routes_10min` | L5 cast → 200; `duration_label == "10min"`, `range_ft == 30`, `concentration is True`. Base tier. |
| `test_modify_memory_l6_routes_1h` | L6 cast → `duration_label == "1h"`. |
| `test_modify_memory_l7_routes_24h` | L7 cast → `duration_label == "24h"`. |
| `test_modify_memory_l8_routes_7d` | L8 cast → `duration_label == "7d"`. |
| `test_modify_memory_l9_routes_permanent` | L9 cast → `duration_label == "permanent"` (any time in the past). Top tier. |
| `test_modify_memory_missing_character_id_400` | Missing character_id → 400. |
| `test_modify_memory_low_slot_400` | slot_level=4 → 400 (Modify Memory is L5). |
| `test_modify_memory_wrong_class_409` | class_slug=cleric (not a Modify Memory class) → 409 `wrong_class`. |
| `test_modify_memory_spell_not_known_409` | Wizard without Modify Memory on her list → 409 `spell_not_known` (fires before the slot lookup). |

### `test_cast_mass_suggestion.py`
v2.407.0 — new `/cast_mass_suggestion` endpoint + duration-scaling substrate, fifth consumer (second NEW endpoint). RAW L6 Enchantment, 60 ft, not concentration, up to 12 targets. Substrate `"mass-suggestion"` entry uses calendar markers ("24h" / "10d" / "30d" / "1y1d"), one per slot level L6-L9. Thalindra Moonwhisper is armed with Mass Suggestion + an L6-L9 wizard slot table (snapshot + restored on teardown).

| Test | What it asserts |
|------|-----------------|
| `test_mass_suggestion_l6_routes_24h` | L6 cast → 200; `duration_label == "24h"`, `range_ft == 60`, `concentration is False`. Base tier. |
| `test_mass_suggestion_l7_routes_10d` | L7 cast → `duration_label == "10d"`. |
| `test_mass_suggestion_l8_routes_30d` | L8 cast → `duration_label == "30d"`. |
| `test_mass_suggestion_l9_routes_1y1d` | L9 cast → `duration_label == "1y1d"` (a year and a day). Top tier. |
| `test_mass_suggestion_missing_character_id_400` | Missing character_id → 400. |
| `test_mass_suggestion_low_slot_400` | slot_level=5 → 400 (Mass Suggestion is L6). |
| `test_mass_suggestion_wrong_class_409` | class_slug=cleric (not a Mass Suggestion class) → 409 `wrong_class`. |
| `test_mass_suggestion_spell_not_known_409` | Wizard without Mass Suggestion on her list → 409 `spell_not_known` (fires before the slot lookup). |

### `test_hex_duration_scaling.py`
v2.405.1 — spell-utility-mechanical-depth Phase 1: duration-scaling substrate, second consumer. The `_SPELL_DURATION_MAP` "hex" entry + `_spell_duration_rounds_for_slot()` helper replace the hardcoded per-slot duration ladder at `/cast_hex`. Magnus Hexbinder's Pact Magic slot table PATCH'd up to L5 so all three tiers are reachable.

| Test | What it asserts |
|------|-----------------|
| `test_hex_l1_routes_1h_duration` | Cast at L1 → substrate returns 600 rounds (1 hour); installed buff's `duration_label == "1h"`. Lower-tier branch. |
| `test_hex_l3_routes_8h_duration` | Cast at L3 → substrate returns 4800 rounds (8 hours); `duration_label == "8h"`. Middle-tier branch. |
| `test_hex_l5_routes_24h_duration` | Cast at L5 → substrate returns 14400 rounds (24 hours); `duration_label == "24h"`. Upper-tier branch. |

### `test_hex_twinned_install.py`
v2.99.189 — `/cast_hex` adopts the v2.99.187/.188 Hunter's Mark pattern: per-target install when Twinned fires + chat-card naming both targets.

| Test | What it asserts |
|------|-----------------|
| `test_hex_twinned_install_list_rider_and_broadcast` | Magnus Hexbinder casts Hex with Twinned armed + a synthetic "Cursed Cultist" as the second target. The installed Hex buff carries a list-shape `effects.weapon_hit_bonus_target_combatant_id` containing both targets + a `target_combatant_ids` list mirroring both. The install `feature_used` broadcast's `feature_name` + `feature_desc` mention both targets; `target_names` lists both; `twinned_target_combatant_id_2` + `twinned_target_name` are populated. |
| `test_hex_no_twinned_keeps_single_target` | Control: Magnus casts Hex without Twinned pending. The buff's rider remains a single string; the install broadcast keeps single-target shape (`target_names` is a singleton, `twinned_target_*` fields are falsy). |

### `test_buff_sheet_mirror.py`
Phase C.3 — buffs persist to `sheet["_buffs_active"]` for cross-page visibility.

| Test | What it asserts |
|------|-----------------|
| `test_use_rage_mirrors_to_sheet` | After `/use_rage`, the sheet mirror contains the Rage entry. |
| `test_end_buff_clears_sheet_mirror` | After `/end_buff`, the mirror is empty. |
| `test_hunters_mark_mirrors_to_sheet` | Hunter's Mark also mirrors. |
| `test_put_battle_mirrors_to_sheet` | A raw `PUT /battle` with buffs in the combatants array updates the sheet mirror. |
| `test_put_battle_clears_sheet_on_buff_drop` | Removing the buff via PUT clears the mirror. |

---

## Tabletop operations

### `test_move.py`
Token-list GET + token-move POST.

| Test | What it asserts |
|------|-----------------|
| `test_tokens_list` | `GET /tokens` returns all live tokens. |
| `test_move_pip_one_cell` | Single-cell move broadcasts `token_update` with the new x/y. |
| `test_move_chebyshev_diagonal` | Diagonal move counts as one cell (chebyshev distance). |
| `test_move_unknown_token` | Unknown token id → 404. |

### `test_rest.py`
Short rest (Song of Rest) + long rest.

| Test | What it asserts |
|------|-----------------|
| `test_short_rest_song_of_rest_happy_path` | Short rest with hit dice → broadcasts hp restore. |
| `test_long_rest_happy_path` | Long rest refills HP + spell slots + class features. |
| `test_short_rest_invalid_type` | `type: "bogus"` → 400. |
| `test_short_rest_no_hit_dice` | No HD left → cannot short rest. |

### `test_encounters.py`
Encounters CRUD — `GET /encounters`, `POST /encounters`, `PATCH /encounters/{id}`, duplicate / update / delete. v2.40.0 closed the v2.35.1 audit gap.

| Test | What it asserts |
|------|-----------------|
| `test_list_encounters_returns_array` | `GET /encounters` returns a JSON list. |
| `test_non_gm_cannot_list` | 403 for non-GM. |
| `test_create_blank_encounter` | `POST /encounters` with `payload` creates a build-from-blank draft; shows up in subsequent list. |
| `test_create_encounter_missing_name_400` | Empty `name` → 400. |
| `test_patch_encounter_updates_name` | `PATCH /encounters/{id}` rewrites name + description. |
| `test_duplicate_encounter` | `POST /encounters/{id}/duplicate` creates a sibling row with a new id. |
| `test_delete_encounter` | `POST /encounters/{id}/delete` removes the row from the list. |
| `test_non_gm_cannot_create_403` | 403 for non-GM POST. |
| `test_update_encounter_overwrites_payload` | `POST /encounters/{id}/update` snapshots live state into the saved payload (doesn't touch live state). |

> `POST /encounters/{id}/load` happy-path test is **filed** — loading replaces live tokens + battle state which is destructive for the standing demo seed and breaks downstream tests. Needs a save-restore harness pattern.

### `test_transform.py`
Druid Wild Shape / Polymorph form transitions.

| Test | What it asserts |
|------|-----------------|
| `test_wild_shape_happy_path` | Mira → beast form; `transform` broadcast carries new sheet. |
| `test_transform_missing_slug` | 400. |
| `test_transform_invalid_source` | `source: "garbage"` → 400. |
| `test_transform_cr_cap_enforced` | Druid CR cap rejects high-CR beasts. |
| `test_transform_already_transformed` | Cannot transform while transformed (409). |
| `test_revert_when_not_transformed` | Reverting a base-form character → 409. |
| `test_transform_over_budget_flag` | Carries `over_budget: true` when action chip already used. |

---

## Content parsers (unit tests)

Pure-Python unit tests that don't need the docker stack or any HTTP / WS fixture. Hosted under `tests/harness/` so the CI workflow picks them up alongside the harness tests; the parser modules live under `app/content/`.

### `test_range_parser.py`
v2.49.74 — Phase 2B of the ruler/range plan. Tests `app/content/range_parser.py`'s `parse_range_ft` + `max_range_ft`.

| Test | What it asserts |
|------|-----------------|
| `test_self_returns_zero` | `"Self"` (in any casing / whitespace) → 0. Self-range spells skip the range check. |
| `test_self_with_radius_returns_zero` | `"Self (30-foot radius)"` etc. → 0 (radius is an AoE concern, not the cast-range gate). |
| `test_touch_returns_five` | `"Touch"` → 5 (RAW melee reach). |
| `test_single_feet_band` | `"5 feet"` / `"30 feet"` … `"500 feet"` → int. |
| `test_feet_abbreviation` | `"5 ft"` / `"60 ft"` / `"120 ft"` → int (weapons use the abbreviation). |
| `test_feet_alt_spellings` | `"5 foot"` / `"5 feet."` / `"60 ft."` → int. |
| `test_thrown_weapon_range` | `"20/60 feet"` → `(20, 60)` etc. |
| `test_thrown_abbreviated` | `"30/120 ft"` → `(30, 120)` (the demo's javelin / hand-crossbow shape). |
| `test_mile_scale` | `"1 mile"` → 5280, `"5 miles"` → 26400, `"500 miles"` → 2640000. |
| `test_skip_strings_return_none` | `"Special"` / `"Unlimited"` / `"Sight"` → None — caller skips the range check. |
| `test_empty_inputs_return_none` | `""` / `"   "` / `None` → None. |
| `test_garbage_returns_none` | `"not a range"` / `"60"` (no unit) / `"60 leagues"` → None. Robust to unparseable content. |
| `test_max_range_passthrough_int` | `max_range_ft(60)` → 60. |
| `test_max_range_collapses_thrown` | `max_range_ft((20, 60))` → 60 (uses long range for "is target reachable at all"). |
| `test_max_range_none_passthrough` | `max_range_ft(None)` → None. |
| `test_combined_pipeline` | End-to-end: parse a string then collapse to a single int. |
| `test_srd_spell_ranges` (parametrized, 17 cases) | Pins every unique range string surveyed from `app/data/local/dnd5e/spells/*.json` against its expected ft. SRD content drift fails this test rather than silently breaking range enforcement. |

---

## Wiki

Read-only doc-hub routes added in v2.43.3, expanded in v2.49.9 with the `/wiki/doc/<slug>` route + shared nav menu injection. Tests live in `tests/harness/test_wiki.py`.

| Test | What it asserts |
|------|-----------------|
| `test_wiki_home_renders` | `GET /wiki` → 200, HTML body contains "SimpleVTT wiki", a link to `/wiki/roll-log-guide`, the `wiki-nav` menu, and links into the Plans / References / Repo Docs tables (v2.49.9). |
| `test_wiki_guide_serves_roll_log` | `GET /wiki/roll-log-guide` → 200, body contains "roll-log" + the injected `wiki-nav` menu (v2.49.9). |
| `test_wiki_unknown_slug_404` | `GET /wiki/no-such-page` → 404. |
| `test_wiki_traversal_blocked` | URL-encoded `../` in the slug → 404 / 400 (path-traversal blocked). |
| `test_wiki_markdown_guide_renders` | v2.43.14: `/wiki/realtime-broadcasts-catalog` (a `.md` source) renders through the markdown package + wraps in `wiki_md.html`. Asserts `<h1`, `<table`, the catalog's title, and the `wiki-nav` menu (v2.49.9). |
| `test_wiki_lair_regional_catalog_renders` | v2.181.1: `GET /wiki/lair-regional-catalog` (a `.md` source) → 200, body contains "lair actions" + "regional effects" + a known curated entry ("Magma Erupts") + `<h1` + `<table` + the `wiki-nav` menu. The reader-facing catalog of the five chromatic dragon lairs (mirrors the `app/content/` leaf modules). |
| `test_wiki_doc_serves_plan` | v2.49.9: `GET /wiki/doc/plan-test-harness` → 200, body contains the plan's H1 + the nav menu. Resolves through the `_DOC_ALLOWLIST` mapping to `docs/plans/test-harness.md`. |
| `test_wiki_doc_serves_ruler_plan` | v2.49.66: `GET /wiki/doc/plan-ruler-and-range` → 200, body contains "ruler" + "range" + the nav menu. Resolves through the allowlist to `docs/plans/ruler-and-range.md`. |
| `test_wiki_doc_serves_aura_geometry_enforcement_plan` | v2.515.0: `GET /wiki/doc/plan-aura-geometry-enforcement` → 200, body contains "geometry enforcement" + the nav menu. Resolves through the allowlist to `docs/plans/aura-geometry-enforcement.md` (the design plan for mechanically enforcing the cast-and-broadcast tail's aura/barrier geometry — Holy Aura, Globe of Invulnerability, Antilife Shell). |
| `test_wiki_doc_serves_conjure_family_plan` | v2.538.0: `GET /wiki/doc/plan-conjure-family` → 200, body contains "conjure family" + the nav menu. Resolves through the allowlist to `docs/plans/conjure-family.md` (the summon-catalog design plan for the six SRD `conjure-*` spells). |
| `test_wiki_doc_serves_simulacrum_plan` | v2.49.68: `GET /wiki/doc/plan-player-simulacrum` → 200, body contains "simulacrum" + the nav menu. Resolves through the allowlist to `docs/plans/player-simulacrum.md`. |
| `test_wiki_doc_serves_root_doc` | v2.49.9: `GET /wiki/doc/claude` → 200, body contains CLAUDE.md's H1 ("Claude Code guidelines") + the nav menu. Resolves through the allowlist to the repo-root `CLAUDE.md`. |
| `test_wiki_doc_serves_automation_coverage` | v2.99.447: `GET /wiki/doc/automation-coverage` → 200, body contains "automation coverage" + the nav menu. Resolves through the allowlist to `docs/automation-coverage.md` (the Phase 0 audit doc). |
| `test_wiki_doc_serves_bugs` | v2.316.2: `GET /wiki/doc/bugs` → 200, body contains "bug tracker" + the nav menu. Resolves through the allowlist to the repo-root `BUGS.md` (the consolidated known-defect tracker). |
| `test_wiki_doc_serves_magic_items_automation_plan` | v2.158.71: `GET /wiki/doc/plan-magic-items-automation` → 200, body contains "magic-item automation" + "pearl of power" + the nav menu. Resolves through the allowlist to `docs/plans/magic-items-automation.md` (the SRD-audit P1 plan). |
| `test_wiki_doc_serves_exhaustion_levels_plan` | v2.158.72: `GET /wiki/doc/plan-exhaustion-levels` → 200, body contains "exhaustion levels" + the nav menu. Resolves through the allowlist to `docs/plans/exhaustion-levels.md` (the SRD-audit P1 plan to replace single-flag exhaustion with RAW 6-level tracking). |
| `test_wiki_doc_serves_carrying_capacity_plan` | v2.159.26: `GET /wiki/doc/plan-carrying-capacity` → 200, body contains "carrying capacity" + the nav menu. Resolves through the allowlist to `docs/plans/carrying-capacity.md` (filed to unblock Bag of Holding — needed an STR × 15 carry-capacity engine to discount). |
| `test_wiki_doc_serves_legendary_actions_plan` | v2.159.32: `GET /wiki/doc/plan-legendary-actions` → 200, body contains "legendary actions" + the nav menu. Resolves through the allowlist to `docs/plans/legendary-actions.md` (top P1 of the 2026-06-11 SRD audit refresh — 15 SRD monsters carry legendary-action data in their unified `actions` array but the engine has no `/use_legendary_action` dispatch). |
| `test_wiki_doc_serves_str_override_plan` | v2.211.0: `GET /wiki/doc/plan-str-override` → 200, body contains "ability-score override" + the nav menu. Resolves through the allowlist to `docs/plans/str-override.md` (filed to unblock Belt of Giant Strength / Amulet of Health / Potion of Giant Strength — needs an effective-ability-score override substrate with RAW `max(base, set)` semantics). |
| `test_wiki_doc_serves_charged_items_plan` | v2.262.0: `GET /wiki/doc/plan-charged-items` → 200, body contains "charged magic items" + the nav menu. Resolves through the allowlist to `docs/plans/charged-items.md` (backlog plan for extending the existing charge/recharge substrate to remaining SRD charged items — Staff of Power, Ring of the Ram, Gem of Seeing, Wand of Wonder). |
| `test_wiki_doc_serves_spell_utility_upcast_plan` | v2.404.10: `GET /wiki/doc/plan-spell-utility-upcast` → 200, body contains "spell utility-upcast" + the nav menu. Resolves through the allowlist to `docs/plans/spell-utility-upcast.md` (the closure-retrospective plan doc for the v2.404.1 → v2.404.9 arc that closed 9 target-scaling utility spells across `_SPELL_BUFF_MAP` + `_SPELL_TARGET_CAPS`). |
| `test_wiki_doc_serves_demo_magic_link_plan` | v2.423.3: `GET /wiki/doc/plan-demo-magic-link` → 200, body contains "demo magic-link" + the nav menu. Resolves through the allowlist to `docs/plans/demo-magic-link.md` (URL-based passwordless login for the demo instance only, double-env-var gated, single-use HMAC tokens; sibling TODOs for fail2ban/CrowdSec log integration + Cloudflare edge banning). |
| `test_wiki_doc_serves_fail2ban_crowdsec_integration_plan` | v2.423.4: `GET /wiki/doc/plan-fail2ban-crowdsec-integration` → 200, body contains "fail2ban" + "crowdsec" + the nav menu. Resolves through the allowlist to `docs/plans/fail2ban-crowdsec-integration.md` (canonical structured log lines + reference fail2ban filter.d/jail.d configs + reference CrowdSec parsers/scenarios configs shipped in-repo under docs/integrations/; sibling plans for demo magic-link login and Cloudflare edge banning). |
| `test_wiki_doc_serves_cloudflare_edge_banning_plan` | v2.423.5: `GET /wiki/doc/plan-cloudflare-edge-banning` → 200, body contains "cloudflare" + "edge-banning" + the nav menu. Resolves through the allowlist to `docs/plans/cloudflare-edge-banning.md` (outbound Cloudflare API client + GM-only "Ban IP at edge" button + admin-audit log + wiremock service in docker-compose for dev per the third-party-API rule; closes the three-piece security spine started in v2.423.2). |
| `test_wiki_doc_serves_cast_and_broadcast_tail_plan` | v2.436.0: `GET /wiki/doc/plan-cast-and-broadcast-tail` → 200, body contains "cast-and-broadcast" + "true strike" + the nav menu. Resolves through the allowlist to `docs/plans/cast-and-broadcast-tail.md` (Phase 1 opens an arc for mechanizing Bucket A utility spells — True Strike, Find Steed, Speak with Animals, Pass Without Trace, Spider Climb — that currently cast + broadcast without a server-side effect; Bucket B filed as permanently GM-narrated). |
| `test_wiki_doc_unknown_slug_404` | v2.49.9: a slug that isn't in `_DOC_ALLOWLIST` → 404. Important security guarantee — the allowlist is the only way to reach a file outside `docs/wiki/`. |
| `test_wiki_doc_traversal_blocked` | v2.49.9: directory-traversal characters in the doc slug → 404 / 400, rejected by the slug guard before the allowlist lookup. |

---

## CrowdSec config validation (Phase 2 — v2.429.0)

YAML syntax + schema validation for the CrowdSec parser + scenarios at `docs/integrations/crowdsec/`. Pure in-process — no CrowdSec container needed. Lives in `tests/harness/test_crowdsec_configs.py`. A real end-to-end test that brings up CrowdSec and replays events is filed as Phase 2B (gated on Docker Hub image availability).

| Test | What it asserts |
|------|-----------------|
| `test_crowdsec_dir_exists` | The `docs/integrations/crowdsec/` directory is present. |
| `test_parsers_present` | At least one parser YAML file exists. |
| `test_scenarios_present` | At least 5 scenario YAMLs exist (README documents 5). |
| `test_scenario_yaml_parses[…]` × 5 | Every scenario file is valid YAML (parses to a dict). |
| `test_scenario_has_required_keys[…]` × 5 | `type` / `name` / `filter` / `groupby` / `blackhole` / `labels` all present. A missing key silently disables the scenario when CrowdSec reloads — assertion catches it pre-ship. |
| `test_scenario_type_is_valid[…]` × 5 | `type` is one of `leaky` / `trigger` / `counter`. |
| `test_scenario_name_is_namespaced[…]` × 5 | Every scenario name starts with `simplevtt/` so multi-deployment operators can tell which one fired a decision. |
| `test_scenario_labels_have_service_simplevtt[…]` × 5 | `labels.service == 'simplevtt'`. |
| `test_scenario_remediation_flag_set[…]` × 5 | `labels.remediation == True` — every shipped scenario drives a real ban. |
| `test_scenario_filter_references_simplevtt_log[…]` × 5 | Filter expression references the `simplevtt-audit` log_type tag so scenarios don't silently match unrelated CrowdSec events. |
| `test_leaky_scenarios_have_capacity_and_leakspeed[…]` × 5 | Leaky scenarios carry both. The trigger-type magic-link-replay scenario is `pytest.skip`-ped. |
| `test_parser_yaml_parses[path0]` | Parser YAML parses. |
| `test_parser_has_required_keys[path0]` | `name` / `filter` / `nodes` all present. |
| `test_parser_has_audit_log_type_static[path0]` | Parser emits `meta: log_type, value: simplevtt-audit` somewhere in its nodes — without it, every scenario silently no-ops. |
| `test_readme_documents_all_scenarios` | README's scenario table mentions every shipped scenario by name. Catches doc-vs.-files drift. |

---

## In-app user-admin routes RETIRED → Admin Center (v2.579.0)

The in-app `/admin` user write surface (create / disable / reset-password / delete / scrub-audit-log, removed v2.579.0) and the on-demand demo reset (`POST /admin/demo/reset`, removed v2.580.0) were **retired** (Phase 4 of `docs/plans/admin-center-consolidation.md`) once they gained full parity in the standalone Admin Center. The former suites `test_admin_audit.py` (the `record_admin_action` plumbing, v2.431.0), `test_admin_user_audit_scrub.py` (the GDPR Art. 17 scrub, v2.489.0), and `test_admin_demo_reset.py` (the on-demand reseed, v2.3.0) were deleted along with the routes.

- **Replacement coverage (in-app):** `tests/harness/test_admin_routes_retired.py` asserts each retired route (`POST /admin/users`, `/disable`, `/reset_password`, `/delete`, `/scrub-audit-log`, `/admin/demo/reset`) no longer succeeds (never 2xx/3xx — only 404/405/401/403), proving there's no live duplicate write-path.
- **Replacement coverage (Center):** the moved behavior is now tested in `tests/harness/test_admin_center.py` — user create/disable/reset/delete via the `/users` page (operator-attributed audit through `operator_audit`), and the audit-log scrub via `POST /users/{id}/scrub-audit-log`. The Center attributes mutations to `actor=admin-center:<operator>` in the audit-log stream rather than an `admin_audit_log` DB row (no app `User` actor exists in the Center).

---

## Cloudflare edge-banning (Phase 1 — v2.427.0)

Mix of in-process unit tests on `app/integrations/cloudflare.py` predicates + integration tests against the dev container with the gates off. Lives in `tests/harness/test_cloudflare_banning.py`. The actual HTTP-call paths are exercised manually against the wiremock service (`docker compose --profile dev up cloudflare-mock`) + flipped env vars; a permanent end-to-end test is filed for Phase 1B.

| Test | What it asserts |
|------|-----------------|
| `test_integration_disabled_by_default` | With `CLOUDFLARE_API_TOKEN` + `ZONE_ID` unset, `integration_enabled()` is False and `_read_config()` returns None. |
| `test_integration_requires_both_token_and_zone` | Either env var alone doesn't enable the client. |
| `test_integration_uses_custom_base_url` | `CLOUDFLARE_API_BASE_URL` override is honored; trailing slash stripped so URL composition stays clean. |
| `test_integration_defaults_to_public_api` | Without override, base URL defaults to `https://api.cloudflare.com/client/v4`. |
| `test_banning_requires_both_client_and_ui_gate` | Client config + `SIMPLEVTT_CLOUDFLARE_BANNING_ENABLED=true` both required for `cloudflare_banning_enabled()` to return True. Either off → False. |
| `test_banning_gate_accepts_truthy_variants` | Truthy parse for `1/true/yes/on` case-insensitively; falsy parse for `0/false/no/off/empty/garbage`. |
| `test_ban_ip_returns_503_when_gate_off` | `POST /admin/cloudflare/ban_ip` against the dev container (gates off by default) → 503 even for admin. `detail=cloudflare_banning_not_configured`. |
| `test_unban_ip_returns_503_when_gate_off` | `POST /admin/cloudflare/unban_ip` → 503. |
| `test_edge_bans_list_returns_503_when_gate_off` | `GET /admin/cloudflare/edge_bans` → 503. |
| `test_ban_ip_returns_403_for_non_admin` | Logged-in non-admin (`demo-alice`) → 403 even before the gate check (`require_admin` fires first, by design — preserves the standard `/login` redirect for users exploring the UI). |
| `test_ban_ip_returns_401_for_anonymous` | Anonymous → 401. |
| `test_add_ip_access_rule_sends_correct_request` | v2.428.0: monkeypatches `httpx.AsyncClient` with a request-capturing fake. Asserts the POST URL composes correctly from `base + /zones/{zoneId}/firewall/access_rules/rules`, the `Authorization: Bearer <token>` + `Content-Type: application/json` headers are sent, and the JSON body carries the right `mode`/`configuration.target`/`configuration.value`/`notes` fields. Parses `result.id` out of the canned success response. |
| `test_add_ip_access_rule_raises_on_non_200` | A 500 upstream raises `CloudflareApiError` with `status_code=500`. |
| `test_add_ip_access_rule_raises_on_success_false` | A 200 response with `success: false` (e.g. invalid token, validation error) raises `CloudflareApiError`. |
| `test_add_ip_access_rule_raises_disabled_when_env_unset` | With token + zone env unset, the call raises `CloudflareDisabledError` **before** any HTTP attempt. |
| `test_remove_ip_access_rule_sends_delete` | `DELETE` request, URL composes to `.../rules/{rule_id}`. |
| `test_remove_ip_access_rule_treats_404_as_success` | A 404 from Cloudflare is logged + treated as success — the rule was already gone (operator removed via dashboard, etc.). Idempotent. |
| `test_list_ip_access_rules_returns_array` | Parses `result` array out of the response; sends `per_page=100`. |
| `test_list_ip_access_rules_with_ip_filter` | `ip="..."` argument adds the `configuration.value` query param. |
| `test_notes_truncated_at_1024_chars` | Notes longer than Cloudflare's 1024-char cap are truncated client-side before being sent. |
| `test_cache_purge_gate_requires_client_and_flag` | v2.531.0: `cloudflare_cache_purge_enabled()` needs BOTH the client configured AND `SIMPLEVTT_CLOUDFLARE_CACHE_PURGE_ENABLED` on — default closed; client missing → off. |
| `test_cache_purge_gate_truthy_variants` | v2.531.0: the purge flag accepts `1/true/yes/on` (case-insensitive) and rejects everything else. |
| `test_purge_cache_posts_purge_everything` | v2.531.0: `purge_cache()` POSTs `{"purge_everything": true}` to `.../zones/{zone}/purge_cache` with the `Authorization: Bearer` header. |
| `test_purge_cache_with_files_targets_them` | v2.531.0: `purge_cache(files=[...])` POSTs `{"files": [...]}` instead of purging everything. |
| `test_purge_cache_raises_disabled_when_env_unset` | v2.531.0: token/zone unset → `CloudflareDisabledError` before any HTTP attempt. |
| `test_purge_cache_raises_on_non_200` | v2.531.0: a 403 upstream raises `CloudflareApiError` with `status_code=403`. |

---

## API-surface audit emission (Phase 1 finisher — v2.426.0)

Integration tests for the v2.426.0 `app/main.py::_auth_redirect_handler` plumbing — every protected-endpoint 401/403 response now emits a canonical `api.unauthorized` or `api.forbidden` audit-log line for fail2ban / CrowdSec consumption. The legitimate browser-bounce path (HTML request to a guarded page that gets redirected to `/login`) is explicitly excluded so the log doesn't drown in normal browser noise. Lives in `tests/harness/test_api_audit_emission.py`.

These tests don't verify the audit emission directly (that's covered by `test_audit_log.py`) — they verify the **response codes** that trigger it.

| Test | What it asserts |
|------|-----------------|
| `test_anonymous_api_request_to_protected_endpoint_returns_401` | `GET /admin` with `Accept: application/json` → 401. Triggers the `api.unauthorized` emit. |
| `test_anonymous_html_browser_bounce_is_redirect_not_401` | `GET /admin` with `Accept: text/html` → 303 redirect to `/login?next=…`. NO audit emit on this path — legitimate browser navigation. |
| `test_non_admin_user_hitting_admin_endpoint_returns_403` | Logged-in `demo-alice` (non-admin) hits `/admin` → 403. Triggers the `api.forbidden` emit so an operator can spot privilege-escalation probes. |

---

## Demo magic-link login (Phase 1 — v2.425.0)

Mix of in-process unit tests (helpers in `app/demo_magic_link.py` — `mint_token` / `verify_token` / `magic_link_enabled`) and integration tests against the dev container with the gates off (their default). Lives in `tests/harness/test_demo_magic_link.py`.

The dev container boots with `DEMO_MODE=false` and `SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED=false` so the only integration-level behavior asserted here is the gate-off path (both endpoints 404). The happy-path end-to-end (mint via admin + verify via public URL + replay 401) was exercised manually with both gates flipped on; a permanent regression test for it is filed for a future docker-compose override that boots a second `app-demo` service with the gates on.

| Test | What it asserts |
|------|-----------------|
| `test_mint_then_verify_roundtrip` | `mint_token(sub)` returns `<payload>.<sig>`; `verify_token(token)` returns `ok=True, sub=sub, jti=<22 chars>` (16 bytes urlsafe-b64). |
| `test_verify_rejects_tampered_payload` | Flip one byte in the payload → HMAC mismatch → `ok=False, reason="signature"`. |
| `test_verify_rejects_tampered_signature` | Flip one byte in the signature segment → HMAC mismatch → `ok=False, reason="signature"`. |
| `test_verify_rejects_empty_token` | Empty string → `ok=False, reason="signature"`. |
| `test_verify_rejects_token_without_dot` | Tokens with no `.` separator can't be valid itsdangerous blobs → `ok=False`. |
| `test_verify_rejects_garbage_token` | Bytes that look base64-ish but won't sig-verify → `ok=False, reason="signature"`. |
| `test_jti_is_unique_per_mint` | 20 successive mints produce 20 distinct jtis — `secrets.token_urlsafe(16)` collision resistance. |
| `test_gate_off_by_default` | With both env vars unset, `magic_link_enabled()` is False. Protects against `.env.example` typos. |
| `test_gate_requires_both_env_vars` | Setting only `DEMO_MODE` OR only `SIMPLEVTT_DEMO_MAGIC_LINK_ENABLED` keeps the gate closed; both together open it. |
| `test_gate_accepts_truthy_variants` | Truthy parse for `1/true/yes/on` + case-insensitive; falsy parse for `0/false/no/off/empty/garbage`. |
| `test_demo_login_endpoint_404_when_gate_off` | `GET /demo-login?token=anything` against the dev container → 404. Hides whether the feature exists. Auto-skips (via the v2.430.0 `pytest.skip`) when the running container has both gates open — the happy-path tests below cover the gate-on shape. |
| `test_mint_endpoint_404_when_gate_off_even_for_admin` | `POST /admin/demo/mint-magic-link` against the dev container → 401/303/404. The admin-auth check fires before the gate check by design — the standard `/login` redirect still works for admins exploring the UI. |
| `test_admin_home_does_not_show_mint_section_when_gate_off` | `GET /admin` without auth → 401. The `{% if magic_link_enabled %}` gate on the admin_home template means the section literally doesn't render when the gate is off, but the harness has no admin session by default so we settle for the easier check; the gate predicate has its own dedicated unit tests above. |
| `test_happy_path_when_gate_open` | v2.430.0: auto-detecting end-to-end test. Probes `/demo-login?token=garbage` — if 401 (gate open), runs the full mint→verify→replay flow against the running container; if 404 (gate closed, default), `pytest.skip` with a pointer to the operator-side `docs/integrations/demo-magic-link/docker-compose.app-demo.yml` override. Asserts mint returns the URL + 15-min TTL, first verify returns 303 + session cookie, second verify with the same token returns 401 (replay). |
| `test_unknown_sub_when_gate_open` | v2.430.0: auto-detecting. With the gate open, requesting a mint for `real-user@example.com` (not in `DEMO_EMAILS`) returns 400 + `detail=unknown_sub`. Defense-in-depth against an admin minting a token for a real user's account. |

---

## Audit-log emission (Phase 1 of fail2ban/CrowdSec — v2.424.0)

Unit tests on the `app.audit_log` typed emission module. Pure in-process (no httpx, no running container) — verify the canonical line shape the fail2ban filters + CrowdSec parsers will consume. Lives in `tests/harness/test_audit_log.py` to keep the audit module's regression net next to the harness suite, even though these tests don't talk to the server.

| Test | What it asserts |
|------|-----------------|
| `test_emits_canonical_line_with_required_keys` | `audit("auth.login_failed", request=req, username=…)` emits a line that matches the parser regex and carries `ip=…` + `ua="…"` + `username=…` in order. |
| `test_login_ok_at_info_level` | `audit("auth.login_ok", request=req, user_id=42)` emits at INFO and carries `user_id=42` as a bare token. |
| `test_x_forwarded_for_ignored_by_default` | With `TRUSTED_PROXY_HOPS` unset, an XFF header is ignored entirely — the audit log records the direct client IP. |
| `test_x_forwarded_for_trusted_when_hops_set` | With `TRUSTED_PROXY_HOPS=1`, a 2-entry XFF chain returns the leftmost entry (the real client) — protects the fail2ban filter from banning the reverse-proxy's IP instead of the attacker's. |
| `test_x_forwarded_for_multi_hop` | With `TRUSTED_PROXY_HOPS=2`, a 3-entry XFF chain returns the leftmost entry. Confirms the `parts[-(hops+1)]` index formula. |
| `test_x_forwarded_for_hops_exceeds_chain` | When `TRUSTED_PROXY_HOPS` exceeds the chain length, the helper clamps to the leftmost entry — defends against a mis-configured hops value reading off the front of the array. |
| `test_unknown_ip_when_no_request` | `audit(..., request=None, ...)` emits `ip=unknown ua=""` — covers background-task or test-harness call sites that don't have a Request object. |
| `test_value_quoting_handles_whitespace_and_quotes` | Values with whitespace get double-quoted; embedded quotes are backslash-escaped — so a parser regex can split key=value pairs deterministically. |
| `test_explicit_ip_kv_overrides_request` | Passing `ip=` as a kwarg overrides the request-extracted IP. |
| `test_bool_and_int_render_as_bare_tokens` | `bool` → `true`/`false`; `int` → unquoted decimal — so CrowdSec's typed parsers can read them without unquoting. |
| `test_invalid_trusted_proxy_hops_falls_back_to_zero` | `TRUSTED_PROXY_HOPS="not-a-number"` falls back to 0 (XFF ignored), not a crash. |
| `test_negative_trusted_proxy_hops_falls_back_to_zero` | `TRUSTED_PROXY_HOPS="-3"` clamps to 0 — defensive against a typo in `.env`. |
| `test_cf_connecting_ip_ignored_by_default` | `CF-Connecting-IP` ignored unless `TRUST_CF_CONNECTING_IP` is on (direct client IP wins). |
| `test_cf_connecting_ip_trusted_when_enabled` | With the flag on + a Cloudflare peer, the real visitor from `CF-Connecting-IP` wins. |
| `test_cf_connecting_ip_takes_precedence_over_xff` | `CF-Connecting-IP` wins over the `X-Forwarded-For` chain when both are trusted. |
| `test_cf_trusted_but_absent_falls_back_to_xff` | Flag on but header absent → falls through to the XFF path. |

---

## Visitor-request logging (opt-in per-request audit — v2.480.0)

Unit tests on the `app.visitor_log` module — the opt-in `visitor.request` audit event emitted per HTTP request by the outermost middleware in `app/main.py`. Pure in-process (caplog + monkeypatch, same pattern as `test_audit_log.py`). Lives in `tests/harness/test_visitor_log.py`.

| Test | What it asserts |
|------|-----------------|
| `test_disabled_by_default` | No env set → `visitor_request_log_enabled()` is False (default OFF). |
| `test_flag_on_but_no_trusted_hop_stays_closed` | `VISITOR_REQUEST_LOG_ENABLED=true` with `TRUSTED_PROXY_HOPS=0` → gate closed; the trusted-hop interlock prevents recording the proxy's IP. |
| `test_trusted_hop_but_flag_off_stays_closed` | `TRUSTED_PROXY_HOPS=1` without the explicit opt-in → gate closed. |
| `test_both_gates_open` | Both `VISITOR_REQUEST_LOG_ENABLED=true` + `TRUSTED_PROXY_HOPS=1` → gate open. |
| `test_flag_accepts_truthy_synonyms` | `1/true/TRUE/Yes/on` open the flag; `0/false/no/off/""` keep it closed. |
| `test_emit_noop_when_disabled` | `emit_visitor_request()` writes nothing when the gate is closed. |
| `test_emit_canonical_line_when_enabled` | Gate open → one `visitor.request` line carrying the trusted-XFF `ip=` (matching every other audit event for the client), `ua=`, `method=`, `path=`, `status=`, `ms=`. |
| `test_emit_quotes_path_with_query_chars` | A non-bare-token path (query string / spaces) is double-quoted so the canonical-line parser doesn't split on it. |

---

## Request-flood jail wiring (`simplevtt-flood` — v2.481.0)

Static config-shape validation for the opt-in `simplevtt-flood` fail2ban jail that bans IPs on raw request rate (consumes the v2.480.0 `visitor.request` event). No running container needed. Lives in `tests/harness/test_fail2ban_flood_jail_wiring.py`.

| Test | What it asserts |
|------|-----------------|
| `test_flood_filter_file_exists` | `filter.d/simplevtt-flood.conf` ships. |
| `test_flood_filter_matches_visitor_request` | The failregex references `visitor.request` + uses the `<HOST>` placeholder so fail2ban can extract the IP. |
| `test_jail_config_includes_flood_block` | `jail.d/simplevtt.conf` carries an uncommented `[simplevtt-flood]` block with all four `${FAIL2BAN_FLOOD_*}` placeholders. |
| `test_flood_jail_enabled_is_env_gated` | The jail's `enabled` is `${FAIL2BAN_FLOOD_ENABLED}`, NOT a hardcoded `true` — it ships disarmed. |
| `test_env_example_gates_flood_off_by_default` | `.env.example` carries every `FAIL2BAN_FLOOD_*` default and `FAIL2BAN_FLOOD_ENABLED=false` so a fresh `.env` leaves the jail off. |
| `test_compose_passes_flood_env_vars` | The compose fail2ban service plumbs every `FAIL2BAN_FLOOD_*` var, with the enabled gate defaulting to `false`. |
| `test_render_script_allowlist_includes_flood_placeholders` | `render-jail.sh`'s substitution allowlist covers all four placeholders. |

## Jail allowlist wiring (`FAIL2BAN_IGNOREIP` — v2.495.4)

Static config-shape validation for the env-driven jail allowlist that lets an operator exempt a trusted source (e.g. a smoke-test host that self-bans on its own error-path tests) from all jails. No running container needed. Lives in `tests/harness/test_fail2ban_ignoreip_wiring.py`.

| Test | What it asserts |
|------|-----------------|
| `test_jail_default_block_has_ignoreip_placeholder` | `jail.d/simplevtt.conf` has a `[DEFAULT]` whose `ignoreip` keeps localhost AND appends `${FAIL2BAN_IGNOREIP}`. |
| `test_render_script_substitutes_ignoreip` | `render-jail.sh`'s `VARS` allowlist includes `FAIL2BAN_IGNOREIP` so the placeholder is substituted (not rendered literally). |
| `test_compose_passes_ignoreip_env` | The compose fail2ban service plumbs `FAIL2BAN_IGNOREIP` through from the host shell. |
| `test_env_example_documents_ignoreip` | `.env.example` carries a `FAIL2BAN_IGNOREIP` default (empty). |

---

## User data export (GDPR Article 15/20 — v2.482.0)

`GET /api/users/me/export` — a logged-in user's self-serve data export. Live endpoint tests (httpx) + pure cooldown-helper unit tests (`app.user_export`, FastAPI-free). Lives in `tests/harness/test_user_data_export.py`.

| Test | What it asserts |
|------|-----------------|
| `test_export_happy_path` | 200 + `Content-Disposition: attachment`; archive carries the 8 top-level keys; `account` has the email, role, `has_password`/`has_google_sso` booleans, preferences block; `password_hash`/`google_sub` are NOT present; collections are lists. |
| `test_export_generated_for_self` | `generated_for_user_id` matches `account.id` — the archive is scoped to the caller, never another user. |
| `test_export_requires_auth` | Unauthenticated GET → 401 (no empty/foreign archive leak). |
| `test_cooldown_zero_when_never_exported` | `export_cooldown_remaining` returns 0 when the user has never exported. |
| `test_cooldown_zero_when_window_elapsed` | Returns 0 once the cooldown window has fully elapsed. |
| `test_cooldown_positive_within_window` | Returns the correct remaining seconds within the window. |
| `test_cooldown_disabled_when_window_nonpositive` | `cooldown_seconds <= 0` disables the gate (returns 0). |

---

## Admin Center (standalone operator dashboard — v2.483.0)

The standalone read-only dashboard on port 8015. Unit tests (host-side) for the audit-log parser / stats / basic-auth modules + live tests (httpx → :8015) for the auth gate + dashboard + JSON APIs. Live tests skip when the service isn't reachable. Lives in `tests/harness/test_admin_center.py`.

| Test | What it asserts |
|------|-----------------|
| `test_parse_line_canonical_event` | `audit_parse.parse_line` extracts event tag, level, and kv fields (quoted UA reassembled intact). |
| `test_parse_line_quoted_path_with_space` | A `path="/a b"` quoted value with whitespace parses to one field. |
| `test_parse_line_rejects_non_audit_lines` | App-startup logs / junk / empty lines → `None`. |
| `test_load_events_from_file` | Tails + parses a sample log: 3 events, newest-first ordering, `event_prefix` filter. |
| `test_load_events_missing_file_is_empty` | A missing log path → `[]` (empty state, not an error). |
| `test_summarize_counts_and_top_lists` | `stats.summarize` rolls up total, by-event, named signals, top IPs, top paths, unique-IP count. |
| `test_header_authorizes_valid` | A correct `Authorization: Basic` header passes the gate. |
| `test_header_authorizes_rejects_bad` | Wrong password / missing / non-basic / non-b64 headers all rejected. |
| `test_is_default_password` | `is_default_password()` true on `changeme`, false otherwise (UI nag signal). |
| `test_favicon_served_without_auth` | `/favicon.svg` → 200 (svg, no auth) and matches the main site's `/static/favicon.svg` bytes. |
| `test_login_page_references_favicon` | The login page links `/favicon.svg`. |
| `test_healthz_open_without_auth` | `/healthz` → 200 without creds (for the compose healthcheck). |
| `test_unauthenticated_bounces_to_login_page_not_popup` | `/` with no session → 303 to `/login` and NO `WWW-Authenticate` header (login page, not a basic-auth popup). |
| `test_login_page_renders` | `/login` → 200 + a real sign-in form (`name="password"`). |
| `test_login_flow_sets_session_and_grants_access` | POST valid creds → 303 + `admin_center_session` cookie → dashboard renders with "Log out". |
| `test_login_rejects_wrong_password` | POST wrong password → 303 back to `/login?...error`. |
| `test_logout_clears_session` | After `/logout`, the dashboard 303s back to `/login`. |
| `test_dashboard_renders_with_basic_auth_header` | A supplied basic-auth header still grants access (scripting path) — but no popup is ever challenged. |
| `test_login_guard_not_locked_under_threshold` | `login_guard`: 4 failures with a max of 5 → not locked. |
| `test_login_guard_locks_at_threshold` | 5 failures → locked, `lockout_remaining` returns the full window. |
| `test_login_guard_reset_clears` | `reset()` (called on successful login) clears the lockout. |
| `test_login_guard_window_expires_old_failures` | Failures older than the window age out → no lockout. |
| `test_login_guard_is_per_ip` | One IP's failures don't lock out a different IP. |
| `test_dns_reverse_lookup_uses_cache` | `dns_lookup.reverse_lookup` caches — a repeat IP doesn't re-invoke the resolver. |
| `test_dns_reverse_lookup_failure_caches_none` | A resolver error → None, cached (no repeated slow failures). |
| `test_dns_resolve_many_dedupes_skips_and_caps` | `resolve_many` dedupes, skips empty/`unknown`, and caps new lookups at the limit. |
| `test_dashboard_dns_toggle_renders_column` | `?dns=1` adds the "Host (DNS)" column; off by default. |
| `test_api_events_dns_adds_ptr_field` | `/api/events?dns=1` adds a `ptr` field per event. |
| `test_event_help_exact_match` | `event_help.explain` returns the right text for known tags (login_failed → "credential stuffing", not_found → "scanner"). |
| `test_event_help_prefix_fallback` | `admin.*` / `cloudflare.*` tags fall back to the family explanation. |
| `test_event_help_generic_fallback` | An unknown tag → generic "audit event" help. |
| `test_event_help_empty` | Empty tag → the generic fallback. |
| `test_event_help_covers_every_signal_event` | Every named traffic-signal event has a non-generic explanation. |
| `test_dashboard_renders_event_hover_help` | The events table carries the `.evt` hover affordance + `role="tooltip"`. |
| `test_timefmt_log_ts_converts_utc_to_offset` | `timefmt.fmt_log_ts` converts a UTC audit-log timestamp to the display offset. |
| `test_timefmt_log_ts_passthrough_on_unparseable` | Unparseable / empty timestamp returned unchanged. |
| `test_timefmt_epoch_in_offset` | `fmt_epoch` renders an epoch in the display offset; blank/None → "". |
| `test_timefmt_display_tz_name_default_and_override` | `ADMIN_CENTER_TZ` defaults to `America/New_York`; env override honored. |
| `test_timefmt_display_tz_falls_back_on_bad_name` | A bad tz name falls back to UTC (never crashes a render). |
| `test_unban_request_writes_spool_file` | `fail2ban_control.request_unban` writes one `unban-*.req` file with the IP as content. |
| `test_unban_request_accepts_ipv6` | IPv6 addresses are accepted + spooled. |
| `test_unban_request_rejects_invalid_ip` | Garbage / injection / empty IPs rejected; nothing written. |
| `test_unban_request_filename_is_sanitized` | The spool filename stays within the dir (no `/` or `..`). |
| `test_cloudflare_unban_skips_when_not_configured` | `cloudflare_unban.unban_ip` → None when the CF client isn't configured. |
| `test_cloudflare_unban_removes_only_matching_ban_rules` | Removes only block/challenge rules for the exact IP; skips whitelist + other IPs; returns the count. |
| `test_cloudflare_unban_graceful_on_api_error` | A Cloudflare API error → None (the local unban still happened, no raise). |
| `test_clear_audit_log_truncates_and_marks` | `log_control.clear_audit_log` empties the file + appends the marker line. |
| `test_clear_audit_log_removes_rotated_backups` | Rotated `audit.log.N` backups are removed; count reported. |
| `test_clear_audit_log_missing_file_is_ok` | A missing log → ok with `cleared=False` (no error). |
| `test_logs_clear_requires_auth` | `POST /logs/clear` without a session → 303 to `/login`, not executed (the happy path is unit-covered to avoid wiping the shared log). |
| `test_unban_endpoint_accepts_valid_ip` | `POST /fail2ban/unban` (authed) with a valid IP → 303 to `/?unbanned=…`. |
| `test_unban_endpoint_rejects_invalid_ip` | Invalid IP → 303 to `/?unban_error=…`. |
| `test_unban_endpoint_requires_auth` | Unauthenticated POST → 303 to `/login` (not executed). |
| `test_totp_matches_rfc6238_vector` | `mfa.verify_totp` reproduces the RFC 6238 6-digit code (287082) — pins it to what real authenticators generate. |
| `test_totp_rejects_wrong_code` | A wrong code is rejected. |
| `test_totp_window_tolerance` | ±1 step skew accepted; 3 steps away rejected. |
| `test_totp_rejects_blank_and_nondigit` | Blank / non-digit code / missing secret → False. |
| `test_recovery_blank_config_accepts_nothing` | Blank recovery config rejects everything (incl. a blank submission) — the headline safety property. |
| `test_recovery_set_matches_then_one_shot` | A set code matches (constant-time); one-shot consume then re-arm via reset. |
| `test_mfa_config_gates` | `mfa_enabled` / `totp_configured` / `mfa_misconfigured` (enabled + no secret → fail-closed). |
| `test_provisioning_uri` | `otpauth://` URI carries the secret; blank when no secret set. |
| `test_mfa_step_requires_pending_session` | `GET /login/mfa` without a mid-login session → 303 to `/login` (can't skip to the 2FA step). |
| `test_mfa_disabled_login_still_grants_directly` | With MFA off (default), a valid password lands straight on the dashboard (no detour). |

> The MFA-**enabled** end-to-end flow (password → TOTP → dashboard, recovery code, wrong-code reject, fail-closed) is unit-covered by the `mfa.*` tests above and verified manually against a temporarily-MFA-on container; it isn't in the default suite because the shared admin-center container runs MFA-off.
| `test_api_stats_shape` | `/api/stats` → 200 + the roll-up keys. |
| `test_api_events_shape` | `/api/events?limit=10` → 200 + `{count, events: []}`. |
| `test_api_events_requires_auth` | `/api/events` without creds → 401. |
| `test_fail2ban_missing_db_is_unavailable` | `fail2ban.read_status` on a missing db → `available=False` + a human reason, empty ban list. |
| `test_fail2ban_reads_active_and_permanent_only` | Against a seeded sqlite (active + expired + permanent bans): expired excluded, permanent flagged, active carries remaining-seconds + bancount, historical count + jail list + per-jail counts correct. |
| `test_api_fail2ban_shape` | `/api/fail2ban` → 200 + the ban-status envelope keys (same shape whether or not the fail2ban profile is up). |
| `test_api_fail2ban_requires_auth` | `/api/fail2ban` without creds → 401. |
| `test_dashboard_shows_fail2ban_panel` | The dashboard HTML includes the fail2ban panel. |
| `test_api_inventory_shape` | `/api/inventory` → 200 + `{available, counts}`; when available, `Users` is a non-negative int. |
| `test_api_inventory_requires_auth` | `/api/inventory` without creds → 401. |
| `test_dashboard_shows_data_inventory` | The dashboard HTML includes the "Data inventory" panel. |

---

## Mini-sheet partials (Phase 2.6 — v2.49.200)

Regression net for the v2.49.193–.198 per-tab partial extractions from `_mini_sheet_card.html` (Mockup B Phase 2 of [`docs/plans/unified-mini-sheet.md`](../plans/unified-mini-sheet.md)). Loads the demo campaign tabletop page (`GET /campaign/1`) and asserts that the four per-tab partials (`_tab_actions.html`, `_tab_spells.html`, `_tab_skills.html`, `_tab_features.html`) still produce their expected markup when iterated from the unified `_tabs_present` list. Tests live in `tests/harness/test_mini_sheet_partials.py`. NPC mini-sheets are still rendered client-side via `buildMonsterInitSheet` — Phase 2.5's NPC body swap will add matching coverage.

| Test | What it asserts |
|------|-----------------|
| `test_tabletop_renders_all_demo_pc_mini_sheets` | `GET /campaign/1` → 200; all 12 demo PCs' `.mini-header-name` blocks present in the response. A single Jinja error in any sub-partial would 500 the page; this test fails fast. |
| `test_tab_strip_renders_per_tabs_present_list` | Phase 2.4: Zara Emberfire (Sorcerer 5) renders all four tab buttons (`data-tab="attacks"` "Actions" / `"spells"` "Spells" / `"features"` "Features" / `"skills"` "Skills") in the documented order. Validates the `_tabs_present` iteration emits the right `{panel, label}` pairs for a full caster. |
| `test_actions_panel_renders_when_attacks_present` | Phase 2.1: Pip Quickfingers (Rogue) renders the `data-panel="attacks"` panel with at least one `.mini-attack-row` + a `🗡 Strike` button — the partial's tell-tale markup. |
| `test_spells_panel_renders_for_caster_with_slots` | Phase 2.2: Zara renders the `data-panel="spells"` panel with at least one `.mini-spell-row` + `✨ Cast` button + a `.mini-slot-row` slot-pip bar (level ≥ 1 spell present). Validates the multiclass loop + slot-pip rendering in `_tab_spells.html`. |
| `test_skills_panel_renders_all_18_skills` | Phase 2.3: Pip's `data-panel="skills"` contains exactly 18 `.mini-sk-btn` buttons — the `SKILLS_LIST` constant inside `_tab_skills.html` produces the full standard 5e skill grid for every PC. |
| `test_features_panel_renders_for_pc_with_class_features` | Phase 2.3b: at least one PC in the demo roster renders the `data-panel="features"` panel with `.mini-feature-row` + `🪄 Use` button. `_features_list` is the per-character gate; the assertion doesn't hardcode which PC since the demo seed gives every PHB class some class-feature entries. |
| `test_monster_card_pool_renders_for_gm` | Phase 2.5a (v2.49.202): GM sees a hidden `#monster-card-pool` div with at least one `#char-detail-monster-template-{tid}` child per dnd5e TokenTemplate. Canary asserts the `-template-` infix is preserved — the existing `hasCharDetail` lookup matches `char-detail-monster-{tid}` (no infix), so any commit that accidentally drops the infix would activate the legacy `buildMonsterInitSheet` hoist for the first combatant of each template + break multi-combatant cases. |
| `test_monster_card_pool_hidden_from_players` | Phase 2.5a: non-GM users (alice) don't see the pool div in their page DOM at all. NPC sheet data is GM-only. |
| `test_monster_card_pool_partial_renders_for_dnd5e_monster` | Phase 2.5a: the partial doesn't crash on `is_monster=True` against a monster sheet shape (no `classes` / `hit_dice` / etc.). Anchors on the first monster-template card, asserts the 100 KB window contains a `.mini-tabs` block + Skills tab + at least one `.mini-sk-btn` — i.e., the unified `_tabs_present` iteration produced output, `_tab_skills.html` ran against the monster's abilities dict + 18-skill grid emitted buttons. |
| `test_renderbattle_wires_hydration_helper_for_monsters` | Phase 2.5b (v2.49.203): the tabletop page source carries the `_hydrateMonsterCard` JS helper, the slotId computation prefers `c.id` over `'monster-{tid}'` for monsters, and `renderBattle()` actually calls the helper. If a future commit removes any of the three, monster mini-sheets silently regress to `buildMonsterInitSheet` for all combatants and Phase 2.5b's user-visible benefit (unified renderer, per-tab partial parity) is lost. |
| `test_spell_slug_npc_renders_spells_tab` | Bug 3 fix (v2.49.206): Soren the Cult Acolyte's mini-sheet in the monster pool contains a `data-tab="spells"` button + `data-panel="spells"` panel + at least one `✨ Inflict Wounds` or `✨ Sacred Flame` row. Validates that `_monster_template_to_sheet` projects spell_slug actions into `sh['spells']` AND the partial's empty-`_iter_classes` fallback fires for monsters (which have no class hierarchy). |

---

## NPC cast spell (Phase 2.5b finale — v2.49.215)

`/api/campaign/{cid}/npc_cast_spell` — NPC-caster spell endpoint that emits a `spell_cast` WS event so the chat card renders with PC-style spell-card chrome instead of multiple plain dice cards. Mirrors `/npc_attack`'s GM-only stance; rolls attack + damage server-side; on attack hit + `auto_apply_damage` applies damage via `_apply_damage_to_combatant`; for save spells emits the DC + ability chip (save resolution stays GM-manual for v1). Tests live in `tests/harness/test_npc_cast_spell.py`.

| Test | What it asserts |
|------|-----------------|
| `test_npc_cast_spell_requires_combatant_id` | POST without `combatant_id` → 400. |
| `test_npc_cast_spell_gm_only` | Non-GM POST → 403 (alice client). |
| `test_npc_cast_spell_bad_combatant_404` | GM POST with an unknown combatant_id → 404. |
| `test_npc_cast_spell_happy_path_save_spell` | GM POST for Soren (Cult Acolyte) casting Sacred Flame → 200 + `spell_cast` WS broadcast with the right shape (`spell_name=Sacred Flame`, `save_ability=DEX`, `save_dc=13`, `is_save=True`, `caster_char_name=<nickname>`, `caster_combatant_id=tok_…`, `caster_char_id=None`, `is_npc_cast=True`). Skips gracefully when the demo's battle.combatants doesn't currently include the Acolyte. |
| `test_npc_cast_spell_aoe_multi_target_save_loop` | v2.49.217: GM POST for Burning Hands with `aoe_target_combatant_ids=[tok_a, tok_b]` + `area_shape=cone` + `area_size_ft=15` → broadcast contains `area_shape="cone"` + `auto_save_targets` array with ≥1 entry. NPC target entries carry a rolled save value (PC entries pc_skipped=true). Skips when the demo doesn't have the Acolyte. |

---

## Broadcast payload shapes

Field-presence assertions on the WS broadcasts that drive the roll-log cards + the dice / status toasts. Tests live in `tests/harness/test_broadcast_payload_shapes.py` (added v2.43.12). Behavior tests stay in per-endpoint files; these focus purely on what fields the client reads.

| Test | What it asserts |
|------|-----------------|
| `test_roll_broadcast_carries_all_required_fields` | `/roll` broadcast has `total`, `expression`, `breakdown`, `user_id`, `user_name`, `visibility`, `note`. |
| `test_roll_broadcast_carries_visibility_field` | `visibility: "gm_only"` round-trips correctly. |
| `test_weapon_attack_broadcast_carries_all_required_fields` | `/attack` broadcast has `attack_total`, `attack_breakdown`, `attack_name`, `damage_total`, `damage_breakdown`, `damage_type`, `caster_*`, `id`, `hit`, `is_crit`, `is_save`, `over_budget`. |
| `test_spell_cast_heal_broadcast_carries_all_required_fields` | Tavik Healing Word → Pip; broadcast has spell-cast header fields + `auto_heal_*` heal pill fields. |
| `test_spell_cast_attack_broadcast_carries_all_required_fields` | Thalindra Fire Bolt → bandit; broadcast has `auto_attack_*` fields. |
| `test_spell_cast_save_broadcast_carries_all_required_fields` | Tavik Hold Person → bandit; broadcast has `auto_save_*` fields. |
| `test_feature_used_simple_broadcast_carries_all_required_fields` | Cunning Action: Dash; broadcast has header + `feature_desc` (server-side fallback). |
| `test_second_wind_broadcast_carries_dice_and_heal_fields` | `/use_second_wind` broadcast has both the v2.35.0 `dice_*` fields (for the dice toast) AND the v2.43.0 `heal_*` fields (for the card's heal pill), and v2.43.12's `feature_desc` contains "rolled". |
| `test_lay_on_hands_broadcast_carries_heal_fields` | `/use_lay_on_hands` broadcast has the heal pill fields. |

---

## Spell catalog (Phase 2A — v2.49.108)

First slice of the spell-validation suite proposed at [`plan-spell-validation-suite`](../plans/spell-validation-suite.md). Loads every SRD spell JSON under `app/data/local/dnd5e/spells/` (319 entries) and asserts mechanical contracts per spell. v1 covers single-target attack-roll spells (damage range-check only); save / multi-beam / auto-hit variants are filed for follow-up commits.

### `spell_catalog.py` (helper, not a test file)
The session-scope catalog loader + dice-expression parser. `load_all_spells()` reads every JSON file; `dice_range("8d6")` returns `(8, 48)`; `damage_actions(spell)` filters a spell's actions list to those with non-empty `damage`.

### `spell_assert.py` (helper, not a test file)
Assertion helpers — `assert_damage_in_range(damage_total, expression, *, spell_name, slot_level, upcast_dice)` checks the rolled total is inside the dice expression's [min, max] bounds. Failure messages lead with the spell slug + expression so a CI log points at the broken row.

### `test_spell_catalog_loader.py`
Unit tests for the loader + parser. Pure Python; doesn't need the harness server.

| Test | What it asserts |
|------|-----------------|
| `test_load_all_spells_returns_non_empty` | The SRD catalog loads ≥ 200 spells; each has a slug + name. |
| `test_dice_range_single_die` | `1d10` → (1, 10); `1d4` → (1, 4); `1d20` → (1, 20). |
| `test_dice_range_multi_die` | `8d6` → (8, 48); `3d4` → (3, 12); `4d8` → (4, 32). |
| `test_dice_range_flat_bonus` | `1d10+3` → (4, 13); `2d6+5` → (7, 17). |
| `test_dice_range_negative_modifier` | `1d6-1` → (0, 5); `2d8-1` → (1, 15). |
| `test_dice_range_mixed_dice_terms` | `1d8+1d6` → (2, 14); `1d4+1d6+1d8` → (3, 18). |
| `test_dice_range_empty_string` | `""` and whitespace → (0, 0). |
| `test_dice_range_whitespace_tolerated` | ` 1d10 + 3 ` and `8 d 6` parse the same as their compact forms. |
| `test_damage_actions_finds_damage_only` | Filters action lists to entries with non-empty `damage`. |
| `test_save_ability_of_resolution` | `save_ability_of` resolves top-level first, else first action; uppercases + clips to 3; `''` when absent. |

### `test_spell_catalog_smoke.py`
Phase 1 smoke catalog (`docs/plans/spell-validation-suite.md`). Patches one scratch caster (Thalindra) with the WHOLE 319-spell SRD catalog + 999 slots/level in a single `/sheet-fields` PATCH, then loops casting every spell by index and asserts the floor contract — no 500/404/409, a `spell_cast` broadcast per cast — collecting every failure so a content edit that breaks any one spell names the offending slug. One test (not 319 parameterized) to pay the autouse `clean_pcs` long-rest cost once and stay under the runtime budget (~11 s). Sheet is restored in `finally`.

| Test | What it asserts |
|------|-----------------|
| `test_every_catalog_spell_casts_without_500` | Every catalog spell casts at HTTP 200 (floor); the `spell_cast` broadcast count is ≥ 90 % of successful casts. Any non-200 is collected into the assertion message with slug + level + body. |
| `test_smoke_catalog_is_nonempty` | Guard: the loader finds ≥ 300 spells so the smoke can't pass vacuously on an empty glob. |

### `test_spell_catalog_save.py`
Phase 2B save assertions. Patches the scratch caster (Thalindra) with the whole catalog + 999 slots/level, seeds one very-high-HP NPC bandit, then casts every save-bearing spell (~116) at the bandit and asserts the `/cast_spell` response's `auto_save_ability` matches the spell's declared JSON save ability and `auto_save_dc` matches the engine's spell-save-DC formula (`8 + prof + spellcasting mod`, with the WIS fallback when `spellcasting_ability` is unset — uniform across all of one caster's spells). Mismatches are collected by slug. ~7 s.

| Test | What it asserts |
|------|-----------------|
| `test_every_save_spell_dc_and_ability` | Every save spell returns its JSON save ability + the uniform caster DC; ≥ 100 spells asserted; ability/DC mismatches collected with the offending slug. |
| `test_save_catalog_subset_nonempty` | Guard: ≥ 100 save spells exist so the catalog test can't pass vacuously. |

### `test_spell_catalog_attack.py`
Phase 2C spell-attack-roll assertions. Patches the scratch caster (Thalindra) with the whole catalog + 999 slots/level, seeds one very-high-HP NPC bandit, then casts every spell `/cast_spell` resolves as a spell-attack roll (15 spells with an `attack_roll` flag and no `save_ability`). Derives the attack bonus from `auto_attack_total` minus the natural d20 (parsed from `auto_attack_breakdown`'s `[N]`) and asserts it equals the caster's `prof + spellcasting mod` (uniform); asserts `auto_attack_hit` follows the d20 rules (nat 20 hits, nat 1 misses, else `total >= AC`). Crit-doubling is proven deterministically via `/api/test/dice/seed`. Mismatches collected by slug. ~7 s.

| Test | What it asserts |
|------|-----------------|
| `test_every_attack_spell_bonus_and_hit` | Every attack spell's derived bonus = `prof + spell mod` (uniform) + the hit/miss verdict matches nat/AC rules; ≥ 12 spells asserted; bonus/hit mismatches collected by slug. |
| `test_attack_crit_doubles_damage_dice` | Seeds the RNG until Fire Bolt crits, then asserts the damage breakdown shows the doubled dice count (2d10 → 4d10) and the rolled damage is inside the doubled range; the crit registers as a hit. |
| `test_attack_catalog_subset_nonempty` | Guard: ≥ 12 attack-roll spells exist so the catalog test can't pass vacuously. |

### `test_spell_catalog_heal.py`
Phase 2D healing assertions. Patches the scratch caster (Thalindra) with the whole catalog + 999 slots/level, then casts every healing spell (the 7 with a non-empty `healing` expression — Cure Wounds, Healing Word, Heal, Mass Cure Wounds, Mass Healing Word, Prayer of Healing, Regenerate) at the caster (self-heal) and reads the `spell_cast` WS broadcast's `auto_heal_rolled` (the HTTP body only carries `auto_heal_applied`, 0 at full HP). Range-checks the rolled total against `dice_range(spell_healing)` shifted by the caster's spellcasting mod (replicating `_caster_spellcasting_mod` — `spellcasting_ability` else `class_spellcasting`, no WIS fallback, added only when > 0). Range derives from the WS-reported post-upcast expression so upcast is handled for free. Mismatches collected by slug.

| Test | What it asserts |
|------|-----------------|
| `test_every_heal_spell_in_declared_range` | Every healer's `auto_heal_rolled` is inside the declared healing dice + spellcasting mod; ≥ 6 spells asserted; out-of-range rolls collected by slug. |
| `test_heal_catalog_subset_nonempty` | Guard: ≥ 6 healing spells exist so the catalog test can't pass vacuously. |

### `test_spell_catalog_concentration.py`
Phase 2E concentration assertions. Patches the scratch caster (Thalindra) with the whole catalog + 999 slots/level, seeds a battle, then **self-casts** each concentration buff-spell the engine installs (the 5 `_SPELL_BUFF_MAP` entries flagged `concentration: True` — Bless, Heroism, Shield of Faith, Protection from Evil and Good, Haste; listed explicitly in the test since the HTTP harness can't import the fastapi route module locally). Self-cast so the buff lands on the caster's own combatant — where `_install_buff`'s one-at-a-time swap loop fires (buffs cast on others are correctly kept). Asserts the install carries `concentration: True` (read off live battle state) and that each subsequent cast drops the prior anchor in both the battle state and the `buff_update` broadcast's `replaced_concentration` list. Failures collected by slug.

| Test | What it asserts |
|------|-----------------|
| `test_every_concentration_spell_installs_and_swaps` | Every concentration buff-spell installs with the `concentration` flag set; the next cast drops the prior anchor (battle state + `replaced_concentration` broadcast); ≥ 4 asserted. |
| `test_concentration_catalog_subset_nonempty` | Guard: ≥ 5 concentration buff-spells listed and every slug resolves to a real catalog spell. |

### `test_spell_catalog_buff_install.py`
Phase 2F buff-install payload assertions. Patches the scratch caster (Thalindra) with the whole catalog + 999 slots/level, seeds a battle, then casts each of the 9 `_SPELL_BUFF_MAP` spells (Bless, Heroism, Shield of Faith, Aid, Sanctuary, Protection from Evil and Good, Mage Armor, Haste, Longstrider) at a **separate** PC target (Krieger) — the cross-combatant `_install_buff` path, distinct from 2E's self-cast. Reads the target's installed buff off live battle state and asserts its `key` (== slug), `name`, `duration_rounds`, and `concentration` flag against an expected table mirroring the registry; `effects` asserted non-empty. Deterministic — these buffs install unconditionally (no save gate). Failures collected by slug.

| Test | What it asserts |
|------|-----------------|
| `test_every_buff_spell_installs_expected_payload` | Every buff-map spell installs on the target with the expected key/name/duration_rounds/concentration + non-empty effects; all 9 asserted; drift collected by slug. |
| `test_buff_install_catalog_subset_nonempty` | Guard: ≥ 9 buff-install spells listed and every slug resolves to a real catalog spell. |

### `test_spell_catalog_aoe.py`
Phase 2G area-of-effect shape drift gate — a pure-Python content gate (no HTTP/WS fixtures; imports the catalog loader directly, same shape as `test_spell_catalog_range.py`). The server treats a spell as an AoE only when an action's `area.shape` is in `tabletop_routes._AOE_SHAPE_SET = {sphere, cone, line, cube, self_sphere, self_cube}` AND `size_ft > 0` (`_extract_aoe_area`). That module imports fastapi so it can't be imported by the harness — the test replicates the frozenset locally (same approach Phase 2E/2F take) and keeps it in lock step via count + two-way coverage assertions. Iterates the 319-spell catalog and asserts every spell declaring a non-empty `area.shape` uses a RAW-valid shape with positive `size_ft`, the one `line` spell carries a positive `secondary_ft` width, the AoE count is exactly 27 (so a zeroed shape can't pass vacuously), and no catalog shape falls outside the set / no `_RAW_SHAPES` entry is dead. Catches a corrupted shape ("sphere" → "spheer") or zeroed size that would make the server silently stop painting the template. The HTTP `/place_aoe` inside-vs-outside geometry test is a filed follow-up (needs map + token positioning).

| Test | What it asserts |
|------|-----------------|
| `test_every_aoe_spell_has_a_valid_raw_shape_and_size` | Every spell with a non-empty `area.shape` uses a RAW shape with positive `size_ft`; the line spell has positive width; exactly 27 AoE spells; drift collected by slug. |
| `test_aoe_shape_set_covers_every_shape_in_use` | Two-way lock step: no catalog shape outside `_RAW_SHAPES`, and every `_RAW_SHAPES` entry is used by some spell. |

### `test_spell_catalog_aoe_placement.py`
Phase 2G HTTP placement + resolution gate — the companion to the offline `test_spell_catalog_aoe.py` shape gate. Drives the live server end to end across three distinct RAW non-concentration damage AoE shapes (sphere = Fireball, cone = Burning Hands, line = Lightning Bolt): casts each *without* targets so it lands in pending-placement state, then resolves it through `/place_aoe`. Uses the scratch-caster bulk-inject scaffolding (so cone/line spells outside Thalindra's demo list are castable) and the v2.183.0 TEST_MODE `/api/test/campaign/{id}/flags` toggle to enable the server-side damage roll. Adds the cone + line shapes that no prior placement test exercised (`test_cast_spell_aoe.py` covered sphere + the cube concentration path) plus the inside-vs-outside resolution contract — a second battle bandit left outside the placement is asserted untouched.

| Test | What it asserts |
|------|-----------------|
| `test_every_aoe_shape_places_resolves_inside_and_skips_outside` | For sphere/cone/line: cast→pending carries catalog `area_shape`+`area_size_ft`; `/place_aoe` resolves the inside bandit's save + in-band damage + type; the `aoe_pulse` + `spell_cast_aoe_resolved` broadcasts carry the catalog shape/size + cast_id; the outside bandit is absent from `auto_save_targets` and its HP is unchanged. |
| `test_aoe_placement_cases_present_in_catalog` | Guard: every case slug resolves to a catalog spell whose first AoE-shaped action matches the expected shape + size, so the HTTP test can't drift from the catalog. |

### `test_spell_catalog_buff_effects.py`
Phase 3a/3b/3c/3d/3e — buff *effect* validation (not just install). Where Phases 2F / 2F-2 prove a buff lands on the target, this proves the installed buff's mechanical effect is actually applied during play — by the exact amount RAW declares. Covers the auto-applied Bless (+1d4, key `bless`) / Bane (−1d4, key `baned`) d4 uplifts on both attack rolls (3a, `/attack` via `_attacker_has_bless` / `_attacker_has_bane`) and saving throws (3b, NPC save in `/cast_spell` via `_saver_bless_bane_save_suffix`), plus the flat-AC buffs (3c, Shield of Faith +2 / Mage Armor +3 / Haste +2) resolved through `_read_target_ac`'s `effects.ac_bonus` sum. The d4 check is exact, not "token appears": the relevant d20 is rolled twice under one dice seed — once with the buff pre-seeded into the combatant (PUT /battle), once without — and the total delta (which isolates the buff die, since the same seed holds the d20 + flat modifier constant) must equal exactly the d4 value the engine printed, with the registry sign. Pre-seeding the buff avoids any save-fail loop. The AC check is likewise exact: a baseline `/attack` reads `target_ac`, the spell is really cast (so the delta is driven by `_SPELL_BUFF_MAP`'s `ac_bonus`, making the gate sensitive to registry drift), and the boosted-minus-baseline `target_ac` delta must equal the registry bonus. Phase 3d adds the weapon-hit damage riders (Hunter's Mark / Hex, +1d6 on hits): a real cast through the dedicated endpoint installs a `weapon_hit_bonus_dice: "1d6"` rider on the caster keyed to the target, and the caster's seeded `/attack` against that target surfaces the rolled die in `auto_uplifts` under `source == <buff key>` — the gate pins the `1d6` expression, the in-band roll matching its own breakdown + total, and Hex's necrotic damage type. Phase 3e adds the movement-speed riders (Haste ×2 / Slow ½): a real cast installs a `speed_multiplier: 2` (Haste, via `/cast_spell`) or `speed_reduction_ft = base // 2` (Slow, via `/cast_slow`) effect on an active mover that owns a real map token, and an over-cap `/token/move` returns 409 `over_speed_cap` whose `cap_ft` must equal the registry-derived effective speed exactly (Haste base 15 → 30, Slow base 30 → 15). With 3e shipped, Phase 3 covers all five auto-applied buff mechanical surfaces (attack, save, AC, weapon-hit damage, movement speed); the "Bane on ability checks" slice is dropped as a RAW misnomer (Bane affects attacks + saves only, both already covered).

| Test | What it asserts |
|------|-----------------|
| `test_bless_bane_attack_uplift_contribution_is_exact` | 3a — Bless (+1d4) / Bane (−1d4): the with-buff vs. without-buff `attack_total` delta equals exactly the printed d4 × registry sign (same-seed pair), with the correct sign in the breakdown. |
| `test_bless_bane_save_uplift_contribution_is_exact` | 3b — Hold Person cast at a Bless/Bane-carrying NPC: the with-buff vs. without-buff `auto_save_rolled` delta equals exactly the printed save d4 × registry sign (same-seed pair). |
| `test_ac_buff_spells_apply_exact_ac_bonus` | 3c — Shield of Faith (+2) / Mage Armor (+3) / Haste (+2): really cast at a target, the boosted-minus-baseline `target_ac` delta equals exactly the `_SPELL_BUFF_MAP` `ac_bonus`, after confirming the buff installed on the target combatant. |
| `test_weapon_hit_riders_apply_exact_bonus_damage` | 3d — Hunter's Mark / Hex (+1d6 on hits): real-cast the rider, attack the marked target under a dice seed, and assert the `auto_uplifts` entry sourced from the buff carries exactly `1d6`, an in-band roll matching its breakdown + total, and the registry damage type (Hex → necrotic; Hunter's Mark → non-empty weapon type). |
| `test_speed_rider_spells_apply_exact_move_cap` | 3e — Haste (×2) / Slow (½): real-cast the rider onto an active mover with a real map token, then an over-cap `/token/move` returns 409 `over_speed_cap` whose `cap_ft` equals the registry-derived effective speed exactly (Haste base 15 → 30, Slow base 30 → 15). |
| `test_attack_uplift_buffs_present_in_catalog` | Catalog anchor: Bless and Bane are present as real catalog spells, so a renamed/removed spell trips the gate. |
| `test_ac_buff_spells_present_in_catalog` | Catalog anchor: Shield of Faith, Mage Armor, and Haste are present as real catalog spells, so a renamed/removed AC-buff spell trips the gate. |
| `test_weapon_hit_rider_buffs_present_in_catalog` | Catalog anchor: the catalog-backed weapon-hit riders (Hunter's Mark) are present; Hex is PHB-only (`catalog=False`) and excluded from the anchor but still gated behaviourally. |
| `test_speed_rider_buffs_present_in_catalog` | Catalog anchor: Haste and Slow are present as real catalog spells, so a renamed/removed speed-rider spell trips the gate. |

### `test_spell_catalog_conditions.py`
Phase 2F-2 — save-gated condition installs (`_SPELL_CONDITION_MAP`). Bulk-injects the catalog + abundant slots into the scratch caster (Thalindra), then for each of the 8 genuine single-target save-or-suck spells (Hold Person, Charm Person, Suggestion, Fear, Hideous Laughter, Confusion, Banishment, Bane) seeds the RNG and loops seeds until the NPC bandit *fails* its save, asserting the response's `auto_save_buff_key` / `auto_save_buff_name` / `auto_save_buff_duration` match the registry AND the condition buff lands on the bandit combatant in the persisted battle state (with `source_char_id` == caster). `hold-monster` (no save in its catalog action), `faerie-fire` (cube AoE), and the two Monk class-feature entries are excluded with documented reasons. A guard test pins the catalog preconditions (each present, expected save ability, no damage, no AoE area).

| Test | What it asserts |
|------|-----------------|
| `test_every_condition_spell_installs_on_failed_save` | Each of 8 `_SPELL_CONDITION_MAP` spells installs its condition on a seed-forced failed NPC save — registry key/name/duration in the response + the buff on the bandit combatant. |
| `test_condition_spells_present_with_save_and_no_damage_or_area` | Guard: each condition spell is in the catalog with the expected save ability, no damage roll, and no AoE area (the install path's preconditions). |

### `test_spell_catalog_exact_damage.py`
Phase 2A.2 — deterministic exact-value damage gate across all four shapes. Seeds the RNG via the TEST_MODE `/api/test/dice/seed` endpoint, flips `auto_apply_damage` on, bulk-injects the catalog + abundant slots into the scratch caster, then casts one spell of each damage shape and parses the engine's own breakdown string for arithmetic self-consistency: attack-roll (Fire Bolt 2d10), multi-beam (Scorching Ray 2d6/beam), save-for-half (Fireball 8d6), auto-hit (Magic Missile 1d4+1/dart). For each `NdM[r,…]=subtotal` token it checks the dice count (crit-doubling allowed as {2}|{4}), every roll in `[1,sides]`, rolls summing to the subtotal, and subtotals summing to the printed grand total — which must equal the field the engine reports as `rolled`. The seed only removes flakiness; the assertion is exact. Loops seeds until the attack-roll shapes hit. Restores seed + flag + sheet in a `finally`.

| Test | What it asserts |
|------|-----------------|
| `test_exact_damage_breakdown_is_self_consistent_across_shapes` | Across Fire Bolt / Scorching Ray / Fireball / Magic Missile: each damage breakdown's dice count, roll bounds, subtotal sum, and grand total are internally exact and equal the reported `rolled`; all four shapes checked. |

### `test_spell_catalog_autohit.py`
Phase 2A backfill — auto-hit damage (Magic Missile), the last of the four damage shapes. Flips `auto_apply_damage` on via the TEST_MODE `/api/test/campaign/{id}/flags` endpoint, then fires Magic Missile's 3 darts at an NPC (3 entries in `target_combatant_ids`) and asserts each `auto_hit_targets` entry rolled inside the `1d4+1` force band, carried force damage type, and applied non-zero damage. The server contract is "one in-band roll per target id sent" — dart count is the client's responsibility. Range-check only.

| Test | What it asserts |
|------|-----------------|
| `test_magic_missile_autohit_rolls_each_dart` | Magic Missile fires one in-band 1d4+1 force dart per target id, each applying non-zero damage; 3 darts asserted. |
| `test_autohit_catalog_spell_present` | Guard: Magic Missile still carries a no-save, no-attack-roll force-damage action. |

### `test_spell_catalog_save_damage.py`
Phase 2A backfill — save-for-half damage. Flips `campaign.auto_apply_damage` on (via the TEST_MODE `/api/test/campaign/{id}/flags` endpoint), patches the scratch caster (Thalindra) with the whole catalog + abundant slots, seeds one very-high-HP NPC, then casts 8 save-for-half spells: Fireball (8d6), Lightning Bolt (8d6), Burning Hands (3d6), Thunderwave (2d8), Shatter (3d8), Cone of Cold (8d8), plus the Sacred Flame (2d8 at L5) and Poison Spray (2d12 at L5) cantrips that exercise the save-block tier scaling. For each it range-checks `auto_save_damage_rolled` (the full pre-halving roll) against the dice band and asserts the damage type. Restores the flag in a `finally`. Range-check only.

| Test | What it asserts |
|------|-----------------|
| `test_every_save_spell_rolls_damage_in_range` | Each save-for-half spell rolls `auto_save_damage_rolled` inside its dice band with matching damage type; all 8 asserted; drift collected by slug. |
| `test_save_damage_catalog_subset_present` | Guard: every slug resolves to a catalog spell that still carries a save_ability + damage action and no attack_roll. |

### `test_campaign_flags.py`
Coverage for the TEST_MODE-only `POST /api/test/campaign/{id}/flags` endpoint, which flips campaign booleans (today `auto_apply_damage`) without driving the multipart GM settings form. Used by the save-for-half damage test to enable the server-side damage roll.

| Test | What it asserts |
|------|-----------------|
| `test_flags_read_then_toggle_then_restore` | A no-field POST reads the current value; setting true/false mutates + echoes; restore round-trips. |
| `test_flags_unknown_campaign_404` | Unknown campaign id → 404. |

### `test_spell_catalog_multibeam.py`
Phase 2A backfill — multi-beam attack-roll damage. Patches the scratch caster (Thalindra, Wizard L5) with the whole catalog + abundant slots, seeds a battle with a low-AC NPC so beams reliably connect, then casts Scorching Ray (3 rays of 2d6 fire at base slot 2) and Eldritch Blast (2 beams of 1d10 force at caster L5). For each spell it reads the `auto_attack_beams` list and asserts: the beam count matches the expected scaling; every hitting beam's `damage_rolled` falls in the single-beam dice band (widened on a crit beam, which doubles the dice); the aggregate `auto_attack_damage_rolled` equals the sum of the per-beam rolls; and the damage type matches the catalog. Retries up to 8× for a hitting beam. The multi-beam path populates `auto_attack_damage_rolled` on hit without `campaign.auto_apply_damage`, so no settings toggle is needed (unlike the save-for-half / auto-hit paths, still filed). Range-check only.

| Test | What it asserts |
|------|-----------------|
| `test_every_multibeam_spell_rolls_per_beam_damage` | Each multi-beam spell fires the expected beam count; every hitting beam rolls in-band damage; aggregate == sum of beams; damage type matches catalog; both spells asserted. |
| `test_multibeam_catalog_subset_present` | Guard: every multi-beam slug resolves to a catalog spell that still carries an attack-roll damage action. |

### `test_spell_catalog_range.py`
Phase 2H range assertions — a pure-Python content-drift gate (no HTTP/WS fixtures; imports `app.content.range_parser` + the catalog loader directly, same shape as `test_range_parser.py`). For every spell in the catalog it parses the declared `range` string and asserts the projection matches the string's category: skip tokens (Special / Unlimited / Sight) → `None`, Self / Self (N-foot …) → `0`, Touch → `5`, `N feet/foot/ft` → `N`, `N mile(s)` → `N × 5280`; anything else fails as drift. Catches a corrupted range field ("60 feet" → "60 fee", "Touch" → "Touchh") that would make the parser return `None` for a non-skip string. The HTTP cast-from-position range gate (cast inside range → success, outside → 409 with a `range` body field) is a filed follow-up — it needs a position-based range check that `/cast_spell` doesn't enforce today.

| Test | What it asserts |
|------|-----------------|
| `test_every_spell_range_parses_to_its_category` | Every catalog spell's range parses to the projection its string category implies; unrecognized strings (typos / drift) fail; ≥ 300 asserted. |
| `test_range_catalog_every_spell_has_a_range` | Guard: ≥ 300 spells and every one carries a non-empty `range` field so the parse gate can't pass vacuously. |

### `test_spell_catalog_damage.py`
Parameterized over `(caster_name, spell_slug, spell_index, slot_level, base_dmg_expr, upcast_dice)` rows in the `DAMAGE_SPELL_CASES` table. v1 has one row (Fire Bolt at Wizard L5 → 2d10). Each case long-rests the caster, seeds a target combatant, casts the spell, and asserts `response.auto_attack_damage_rolled` is inside the dice expression's [min, max]. Damage type is verified against the catalog JSON.

| Test | What it asserts |
|------|-----------------|
| `test_spell_damage_in_declared_range[Thalindra Moonwhisper-fire-bolt-L0]` | Fire Bolt cast by Thalindra (Wizard L5) → response rolls 2d10 fire damage; range-check 2-20. |

**Filed for follow-up** (each is a separate response-shape adapter):
- Save spells (Fireball, Sacred Flame, …) — read `auto_save_damage_rolled` / per-target `auto_save_targets[*].damage_applied`; requires `auto_apply_damage` toggled on for the cast.
- Multi-beam spells (Scorching Ray, Eldritch Blast) — read `auto_attack_beams[*]`; expected expression is per-beam, not summed.
- Auto-hit damage spells (Magic Missile) — read whichever field carries the auto-hit dart sum; no attack roll, no save.

---

## Browser-level UI harness (`tests/harness_ui/`)

The HTTP+WS suite at `tests/harness/` can't reach canvas event handlers, modal dialogs, or other DOM-level behavior. The Playwright suite at `tests/harness_ui/` covers those — it boots a real Chromium, navigates the demo as a logged-in user, and asserts on observable DOM / network state. Runs in CI under the `harness-ui` job.

### `test_smoke.py`
| Test | What it asserts |
|------|-----------------|
| `test_sheet_loads_for_pip` | Pip's standalone character sheet renders without console errors; `#attacks-fieldset` is visible. |
| `test_sheet_loads_for_tavik` | Same smoke check for Tavik; `#resources-fieldset` also visible. |

### `test_attack_toast.py`
v2.7.3 regression catcher — the broadcast was correct but the toast never appeared in the DOM. See file for exact assertions. **NOTE (v2.49.93):** these two tests have been silently failing since v2.16.0 added the Sneak Attack uplift modal — the click handler now opens `#uplift-modal` for Pip (Rogue Lv 1+) before reaching the fetch, and the test never dismisses it. Tracked for follow-up; not introduced by v2.49.93.

### `test_attack_toast_multi_target.py`
v2.49.93 — chat-card multi-target rendering. When `/attack` fires with `target_combatant_ids: [a, b, c]`, the server's `weapon_attack` broadcast carries `auto_attack_targets` with one entry per target (v2.49.85). Pre-v2.49.93, the client's chat card only rendered the primary target's outcome — the secondary + tertiary names were silently dropped. v2.49.93 fans the chain out: one attack + one damage toast per per-target outcome, staggered 700 ms apart so they don't pile on each other.

| Test | What it asserts |
|------|-----------------|
| `test_multi_target_attack_renders_one_toast_chain_per_target` | Seeds a 3-bandit battle, POSTs `/attack` with `target_combatant_ids` of 3, asserts 6 `.roll-toast` elements appear (3 attack + 3 damage), and every bandit's name shows up in at least one toast label. |
| `test_single_target_attack_still_renders_one_chain` | Backward-compat smoke. Same setup, but POSTs with the legacy singular `target_combatant_id`, asserts exactly 2 toasts (one chain only) and only the primary target's name appears. Catches an accidental double-render on the single-target path. |

### `test_tabletop_canvas.py`
v2.49.92 — canvas pan + drag regression suite. Built when the v2.49.81 `_hoverCursor` TDZ bug silently broke every canvas listener for 11 versions and no existing test could detect it. The suite is the gate for any future change that touches canvas event handlers, CSS on `.map-pane` / `#vtt-canvas`, or the tabletop's IIFE structure.

| Test | What it asserts |
|------|-----------------|
| `test_tabletop_loads_without_js_errors` | `page.on("pageerror", ...)` collects exceptions during navigation to `/campaign/1`; assert list is empty after `window.vttGetCharacters` is defined. Would catch a TDZ / undeclared-variable / syntax error in tabletop.js. |
| `test_right_click_drag_pans_canvas` | Drives a right-mouse drag inside the visible `.map-pane`; asserts `#vtt-canvas`'s `style.transform`'s translate(...) component shifted by > 20 px horizontally + > 10 px vertically. Would catch v2.49.88-class CSS regressions, v2.49.90-class JS event-pipeline regressions, OR the v2.49.81 IIFE-crash regression that broke pan silently. |
| `test_left_click_drag_moves_token` | Resets a known token (Pip) to a fixed on-screen position via the `/token/{id}/move?override=true` REST API; drives a left-mouse drag on the canvas; asserts the token's persisted x/y mutated by at least one grid cell in the dragged direction. Would catch any regression that prevents the mousedown → POST `/token/{id}/move` chain from firing end-to-end. |

### `test_channel_divinity_picker_ui.py`
v2.158.57 — browser coverage of the v2.158.55 Channel Divinity picker wiring against the v2.158.56 seeded Vengeance Paladin (Dame Seraphine Vael). The HTTP harness covers the `/use_vow_of_enmity` contract; this proves the sheet click path (`_fireCDDedicated` branch).

| Test | What it asserts |
|------|-----------------|
| `test_cd_picker_routes_vow_of_enmity` | PATCHes Dame Seraphine Vael's CD full + seeds a one-combatant battle into `localStorage`, clicks `.res-use[data-key="channel-divinity"]`, asserts `#resource-option-picker` surfaces a `.rop-opt` labelled "Vow of Enmity" (the class+subclass+level filter matches her Oath of Vengeance Lv 3), picks it, asserts the `.target-picker-overlay` opens (the distinguisher — generic CD options never open a target picker), taps the seeded Bandit row, and asserts a POST fired to `/use_vow_of_enmity` (never `/use_feature`) with no console errors. |

### `test_invoke_duplicity_picker_ui.py`
v2.158.58 — the targetless sibling of the Vow-of-Enmity UI test. Proves Invoke Duplicity takes the same v2.158.55 `_fireCDDedicated` path but opens NO target picker. PATCHes Tavik into Trickery Domain Lv 2 (no demo Trickery Cleric exists) and restores him afterward.

| Test | What it asserts |
|------|-----------------|
| `test_cd_picker_routes_invoke_duplicity` | PATCHes Brother Tavik Stonebrow into Trickery Domain Lv 2 (CD full) + seeds a battle, clicks `.res-use[data-key="channel-divinity"]`, asserts `#resource-option-picker` surfaces a `.rop-opt` labelled "Invoke Duplicity", picks it, asserts the option picker closes with NO `.target-picker-overlay` opening (the distinguisher from the vow branch), and asserts a POST fired to `/use_invoke_duplicity` (never `/use_feature`) with no console errors. Restores Tavik to Life Domain Lv 8 in a `finally`. |

### `test_form_of_the_beast_picker_ui.py`
v2.158.60 — browser coverage of the v2.158.59 Form of the Beast class-features button against the v2.158.60 seeded Path of the Beast Barbarian (Brakka Wildmane). The first UI test to drive a class-features `.cf-use` button (prior UI tests clicked directly-visible resource pills), so it expands the collapsed `.cf-body` row first.

| Test | What it asserts |
|------|-----------------|
| `test_cf_button_routes_form_of_the_beast` | Seeds a one-combatant server-side battle, expands Brakka's Form of the Beast `.cf-row` (clicks `.cf-header`), clicks `.cf-use[data-feature="form-of-the-beast"]`, asserts `#resource-option-picker` opens with a `.rop-opt` "Claws" option, picks it, and asserts a POST fired to `/use_form_of_the_beast` (never `/use_feature`) with no console errors. |

### `test_drunken_technique_picker_ui.py`
v2.158.62 — browser coverage of the v2.158.61 Drunken Technique class-features button against the v2.158.62 seeded Way of the Drunken Master Monk (Quan Reelstep). Unlike Form of the Beast, Drunken Technique has no picker — the click fires the dedicated endpoint directly.

| Test | What it asserts |
|------|-----------------|
| `test_cf_button_routes_drunken_technique` | Seeds a one-combatant server-side battle, expands Quan's Drunken Technique `.cf-row` (clicks `.cf-header`), clicks `.cf-use[data-feature="drunken-technique"]`, and asserts a POST fired to `/use_drunken_technique` (never `/use_feature`) with no console errors. |

### `test_use_item_action_buttons.py`
v2.158.85 magic-items-automation Phase 3b — Use buttons render on the inventory rows for catalog-action items (Pearl, both wands) on Thalindra. v2.158.89 Phase 3c extended with modal-shape assertions: clicking the button opens an in-page `#item-action-modal` overlay (replaces the placeholder `window.prompt`); Pearl gets a `<select>` of slot levels; both wands get a numeric spinner (1-7) with a live "Cast at Lv X" preview. v2.158.90 Phase 3d adds the Staff of Healing's 2-stage modal (action picker → adaptive charge spinner) on Tavik.

| Test | What it asserts |
|------|-----------------|
| `test_pearl_use_button_renders` | 🔮 Use Pearl button visible on Thalindra's Pearl of Power row. |
| `test_wand_use_button_renders` | 🪄 Cast MM button visible on Thalindra's Wand of Magic Missiles row. |
| `test_pearl_use_button_opens_modal_with_slot_select` | Clicking Pearl opens `#item-action-modal` containing the title "Pearl of Power" + a `<select>` with 3 options; Cancel dismisses. |
| `test_wand_use_button_opens_modal_with_charge_spinner` | Clicking the MM wand opens the modal with a `type=number min=1 max=7` spinner; the preview reads "1" at the default charge, "3" after fill("3"). |
| `test_fireball_wand_modal_shows_base_3_offset` | Same for Wand of Fireballs but the `cast_level(n) = n + 2` mapper shows "3" at 1 charge / "6" at 4 charges. |
| `test_staff_use_button_renders` | 🩹 Use Staff button visible on Tavik's Staff of Healing row. |
| `test_staff_use_button_opens_action_picker_modal` | Click opens modal with 3 radios (Cure Wounds / Lesser Restoration / Mass Cure Wounds); charge block hidden + submit disabled until a pick. |
| `test_staff_pick_cure_wounds_shows_variable_spinner` | Picking Cure Wounds reveals a `min=1 max=4` spinner with Lv-X preview tracking the value (1→1, 3→3). |
| `test_staff_pick_lesser_restoration_locks_at_2` | Picking Lesser Restoration locks the spinner readonly at value=2 (min==max==2); preview reads "Lesser Restoration" + "Lv 2". |
| `test_flame_tongue_use_button_renders` | v2.158.94: Flame Tongue button visible on Garrik's row with "Extinguish" label (seed default _lit: True). |
| `test_flame_tongue_click_toggles_label_and_relabels` | Click flips label Extinguish → Ignite; second click flips back. httpx finally-block force-restores via the API so test order doesn't matter. |
| `test_javelin_lightning_button_renders_when_unspent` | v2.159.6 Phase 8f: ⚡ Hurl Lightning button visible + enabled on Krieger's Javelin row. Force-rests Krieger via the API first so seed-default `_used_today: False` is guaranteed. |
| `test_aoe_line_confirm_modal_renders_combatant_list` | v2.159.7 Phase 8g: drives `window._showAoELineConfirmModal` via page.evaluate with 2 synthetic combatants. Asserts modal renders both with name + distance + default-checked checkboxes. Unchecks one, clicks Fire, asserts the resolved promise carries only the checked id. |
| `test_aoe_line_confirm_modal_cancel_returns_null` | v2.159.7 Phase 8g: Cancel button → promise resolves to `null`. |
| `test_javelin_lightning_click_fires_use_item_action` | v2.159.8 Phase 8h: end-to-end click chain — click button → stubbed picker → intercepted /battle + /battle/line-targets → AoE confirm modal renders → Fire → REAL /use_item_action POST asserted with right body → button relabels to "spent until dawn" after sheet flag flips. First full click-to-fire E2E in the Phase 8 work. |
| `test_staff_of_power_renders_three_action_buttons` | v2.275.0: the Staff of Power row surfaces THREE `.inv-item-action` buttons (primary Fireball aoe-sphere + Lightning Bolt aoe-line + Cone of Cold aoe-cone via the new `extra_actions` array). Asserts count == 3 and all three labels present on Thalindra's row. |
| `test_staff_of_power_cone_button_fires_use_item_action` | v2.275.0: end-to-end click of the Cone of Cold extra-action button (`data-action-idx=1`) — stubbed picker + intercepted /battle + /battle/cone-targets → AoE confirm modal renders the overridden cold-damage body (asserts "cold", not the Wand-of-Fear Frightened text) → Fire → REAL /use_item_action POST asserted with `action_key: "cast-cone-of-cold"` + the in-cone id; resource decrements 20 → 15. Proves the extra-action resolution path dispatches the right config. |

### `test_legendary_action_buttons.py`
v2.160.0 legendary-actions Phase 1c (UI) + v2.162.0 (target-pick) — GM init-tracker legendary-action spend strip. Seeds a two-combatant battle into `localStorage` (Hero + Ancient Red Dragon carrying `legendary_actions: {max:3,current:3}` + `legendary_action_options`), so it exercises the client render path without depending on the server hub. The strip is GM-only and renders one `.legendary-act-btn` per option plus a 👑 dot meter. v2.162.0 adds the save-AoE target-pick path: options carrying `save_ability`+`damage` flag the button `data-is-save-aoe` and route the click through `vttOpenMultiTargetPicker` before POSTing `aoe_target_combatant_ids`. v2.163.0 adds the result chat card: `_appendLegendaryAoeResolved` renders the `legendary_action_aoe_resolved` broadcast as a 👑 roll-log card with per-target saved / failed-with-damage / pending pills.

| Test | What it asserts |
|------|-----------------|
| `test_legendary_strip_renders_meter_and_buttons` | With the dragon NOT on its own turn (turn_index=0), the strip shows a "3/3" meter and 2 enabled buttons with cost pills "1" / "2". |
| `test_legendary_buttons_disabled_on_own_turn` | With the dragon active (turn_index=1), both `.legendary-act-btn` are disabled — RAW: legendary actions are spent at the END of OTHER creatures' turns, never on your own. |
| `test_legendary_button_click_posts_use_legendary_action` | `page.route` intercepts the POST to `/use_legendary_action`; clicking the Wing Attack button fires a body with `combatant_id`, `action_id='wing-attack-costs-2-actions'`, `action_name='Wing Attack'`, `cost=2`. Non-AoE seed → asserts `aoe_target_combatant_ids` absent. |
| `test_wing_attack_save_aoe_opens_picker_and_posts_targets` | v2.162.0 — Wing Attack seeded with `save_ability`+`damage` → button flagged `data-is-save-aoe="1"`; clicking opens the (stubbed) `vttOpenMultiTargetPicker`; the picked ids ride along as `aoe_target_combatant_ids` on the POST. |
| `test_wing_attack_save_aoe_picker_cancel_aborts_spend` | v2.162.0 — stubbed picker resolves `null` (cancel) → no `/use_legendary_action` POST fires + the button stays enabled. |
| `test_legendary_aoe_resolved_card_renders_per_target_pills` | v2.163.0 — drives `window._appendLegendaryAoeResolved` with a 3-target payload; asserts the 👑 roll-log card shows the save line + a `chip-hit` saved pill, a `chip-miss` failed pill carrying the damage + type, and a `chip-buff` pending pill. |

### `test_legendary_resistance_ui.py`
v2.167.0 legendary-actions Phase 2 UI — the GM-facing surface for the per-day resistance pool + the failed-save prompt. Seeds a two-combatant battle into `localStorage` (Hero + Ancient Red Dragon carrying `legendary_resistance: {max:3,current:3}`, no action options) so it exercises the client render + WS-handler path without the server hub. Asserts the 🛡️ `.legendary-lr-meter` badge renders, and that a `legendary_resistance_prompt` WS message (dispatched via a `vtt:ws-message` CustomEvent) surfaces the floating `#_legendary_resistance_prompt` banner with Spend/Decline buttons that POST the prompt_id.

| Test | What it asserts |
|------|-----------------|
| `test_lr_badge_renders` | The dragon's card shows the `.legendary-lr-meter` badge containing "3/3" even with no legendary-action options; no 👑 `.legendary-meter` is present. |
| `test_lr_prompt_banner_appears_and_spend_clears_it` | No banner before any prompt; dispatching `legendary_resistance_prompt` surfaces `#_legendary_resistance_prompt` with "Ancient Red Dragon", "WIS DC 16", a "Spend (3 left)" + "Decline" pair; clicking Spend POSTs `/spend_legendary_resistance` with the `prompt_id`; a following `legendary_resistance_resolved` event clears the banner. |
| `test_lr_decline_button_posts_decline` | Dispatching the prompt then clicking Decline POSTs `/decline_legendary_resistance` carrying the `prompt_id`. |

### `test_lair_action_ui.py`
v2.170.0 legendary-actions Phase 3c UI — the GM-facing lair-action panel. Seeds a two-combatant battle into `localStorage` (Hero + Ancient Red Dragon carrying `lair_slug` + a two-entry `lair_actions` list directly on the combatant, plus the battle-level `in_lair` / `lair_slug` flags) so it exercises the client render + WS-handler path without the server hub. Asserts the floating `#_lair_action_panel` renders for the GM with an Enter/Exit toggle, that an `in_lair_changed` WS message flips the panel into the in-lair state listing each action with a Trigger button, and that the toggle + Trigger buttons POST `/set_in_lair` / `/trigger_lair_action` with the expected bodies (the multi-target picker stubbed to resolve the hero's id).

| Test | What it asserts |
|------|-----------------|
| `test_lair_panel_toggle_renders` | With a lair-bearing combatant in the battle, the GM sees `#_lair_action_panel` containing "Lair Actions" + "Ancient Red Dragon" and an "Enter lair" toggle; out of lair → no `._lair_trigger_btn` buttons. |
| `test_in_lair_changed_shows_action_list` | Dispatching `in_lair_changed` `{in_lair:true}` flips the toggle to "Exit lair" and lists two `._lair_trigger_btn` actions ("Magma Erupts", "Tremor", "DEX DC 15"). |
| `test_toggle_posts_set_in_lair` | Clicking the toggle POSTs `/set_in_lair` with `{in_lair:true, lair_slug:"ancient-red-dragon"}`. |
| `test_trigger_posts_trigger_lair_action` | In the in-lair state, clicking Trigger opens the (stubbed) multi-target picker then POSTs `/trigger_lair_action` with `action_id:"magma-erupts"`, the lair_slug, and the picked `aoe_target_combatant_ids`. |
| `test_resolved_action_disables_its_trigger_no_repeat` | v2.172.0 — after a `lair_action_resolved` parks `last_lair_action_id`, that action's Trigger button is disabled + reads "Used last round" while the other stays enabled (RAW MM p.11 no-repeat). |
| `test_resolved_action_disables_all_triggers_once_per_round` | v2.173.0 — a `lair_action_resolved` carrying `lair_acted_round` matching the battle's round disables EVERY Trigger ("Acted this round") + shows the "already acted this round" banner (RAW MM p.11 one-per-round). |
| `test_init_20_banner_surfaces_when_reached` | v2.174.0 — RAW MM p.11: when the active combatant's initiative ≤ 20 (init count 20 reached), the panel shows the "⚠️ Initiative count 20 — … acts now" banner; when the active combatant's initiative > 20 it shows the "not yet reached" hint instead. |
| `test_init_20_player_gets_flavor_toast` | v2.176.0 — RAW MM p.11: a player (`alice_page`) receiving a `lair_init_20_reached` broadcast sees a "🌋 The lair stirs…" `.vtt-toast` and NOT the GM-only "may take a lair action" phrasing. |
| `test_init_20_gm_gets_mechanical_toast` | v2.176.0 — the GM receiving `lair_init_20_reached` still sees the mechanical "may take a lair action" toast naming the owner ("Ancient Red Dragon"). |
| `test_lair_action_resolved_renders_roll_log_card` | v2.177.0 — a `lair_action_resolved` broadcast renders a persistent `#roll-list .feature-used-card` headed by the owner ("Ancient Red Dragon") + "Lair Action" with the action name, "DEX save · DC 15" line, a ❌ chip-miss pill carrying the damage ("17 fire") for a failed save, and a ✅ chip-hit pill for a passed one. |
| `test_regional_effects_render_in_panel` | v2.179.0 — the lair-action panel lists the lair owner's passive regional effects under a "🌐 Regional Effects" heading (name + desc per effect), rendered out of lair (no Enter-lair toggle needed) since they radiate while the creature dwells in its lair. |
| `test_regional_effects_render_for_player` | v2.180.0 — a player (non-GM) sees a read-only `#_regional_effects_panel` with the lair's passive effects, but NOT the GM `#_lair_action_panel`, the creature's name, or the trigger controls. |
| `test_fade_start_button_renders_and_posts` | v2.182.0 — with regional effects + no fade running, the GM panel shows a "🕯️ Regional Fade" block with a `#_fade_start_btn`; clicking it POSTs `/set_regional_fade` with `{action:"start", lair_slug}`. |
| `test_fade_changed_shows_countdown_and_controls` | v2.182.0 — a `regional_fade_changed` WS message carrying an active fade flips the panel to a "4 / 6 days remaining" readout with `#_fade_advance_btn` + `#_fade_clear_btn` and no `#_fade_start_btn`. |
| `test_fade_faded_state_hides_advance` | v2.182.0 — a `regional_fade_changed` with `faded:true` reads "have faded", hides `#_fade_advance_btn`, and keeps only `#_fade_clear_btn`. |
| `test_fade_player_gets_atmospheric_cue` | v2.182.0 — a player whose `battle_update` carries an active `regional_fade` sees an italic 🕯️ "waning" cue on `#_regional_effects_panel` — no day numbers ("days remaining") and no `#_fade_advance_btn` controls. |

### `test_resistance_picker_ui.py`
v2.189.0 "The Apothecary's Menu" — the sheet-UI surface for the v2.188.0 drink-time `resistance_type` override. The HTTP harness (`test_potion_of_resistance_drink_time_pick.py`) proves the endpoint halves the chosen type; this proves the player can pick it. Garrik carries three Potion of Resistance rows (fire, cold, generic); `has_text="Potion of Resistance"` matches only the generic (untyped) row.

| Test | What it asserts |
|------|-----------------|
| `test_generic_resistance_drink_button_renders` | The generic Potion of Resistance row shows a 🧪 Drink `.inv-item-action` button (resistance-pick kind in `ITEM_ACTION_SLUGS`, equipped consumable). |
| `test_generic_potion_opens_type_picker_modal` | Clicking 🧪 Drink on the generic potion opens `#item-action-modal` containing "Potion of Resistance" + an `#ia-rtype` `<select>` with the ten RAW damage-type options; Cancel (`#ia-cancel`) dismisses without firing the endpoint. |
| `test_generic_potion_drink_posts_chosen_type` | Picking "radiant" in `#ia-rtype` and clicking Drink (`#ia-confirm`) POSTs `/use_item_action` with `action_key:"drink"` + `resistance_type:"radiant"`. The POST is intercepted via `page.route` so the seeded potion isn't consumed. |

### `test_self_buff_drink_buttons_ui.py`
v2.191.0 — plain Drink buttons for the parameterless self-buff potions (Heroism / Speed / Invulnerability). They were API-only; only Potion of Resistance had a sheet button (v2.189.0). The `self-buff-drink` `ITEM_ACTION_SLUGS` kind renders a one-click Drink button (no modal) that POSTs `action_key:"drink"`. Garrik carries all three.

| Test | What it asserts |
|------|-----------------|
| `test_self_buff_drink_buttons_render` | Each of the three rows (Potion of Heroism / Speed / Invulnerability) shows a visible `.inv-item-action` Drink button. |
| `test_invulnerability_drink_posts_plain_action` | Clicking 🛡️ Drink on Potion of Invulnerability POSTs `/use_item_action` with `action_key:"drink"` and NO `resistance_type` (no modal). POST intercepted via `page.route` so the seeded potion isn't consumed. |

### `test_fire_breath_button_ui.py`
v2.194.0 — sheet inventory button for the Potion of Fire Breath. The offensive consumable shipped API-only in v2.193.0; the `aoe-sphere` `ITEM_ACTION_SLUGS` entry renders a 🔥 Exhale Fire button (the full center-target → sphere-targets → AoE-confirm click chain needs a loaded battle/map, so this proves the button renders only). Garrik carries the seeded potion.

| Test | What it asserts |
|------|-----------------|
| `test_fire_breath_button_renders` | Garrik's Potion of Fire Breath `.inv-row` shows a visible `.inv-item-action` button containing "Exhale Fire" (aoe-sphere kind, equipped consumable). |

### `test_mind_reading_button_ui.py`
v2.198.0 — sheet inventory button for the Potion of Mind Reading. The save-imposing consumable shipped API-only in v2.197.0; the `single-target-save` `ITEM_ACTION_SLUGS` entry renders a 🧠 Read Thoughts button (the full picker → POST click chain needs a loaded battle/map, so this proves the button renders only). Garrik carries the seeded potion.

| Test | What it asserts |
|------|-----------------|
| `test_mind_reading_button_renders` | Garrik's Potion of Mind Reading `.inv-row` shows a visible `.inv-item-action` button containing "Read Thoughts" (single-target-save kind, equipped consumable). |

### `test_ability_override_display.py`
v2.214.0 "The Visible Might" — ability-score override Phase 2a. The `#ab-card-view` ability cards render the EFFECTIVE score + modifier with an item-boost marker (a ▲ badge + accent colour) when an equipped item sets the score above its base (RAW `max(base, set)` — Belt of Giant Strength, DMG p.155). Garrik Ironside (base STR 18 → mod +4) wears an equipped+attuned Belt of Giant Strength (Hill, STR 21 → mod +5), so his STR card shows 21 with the badge; DEX (14, no override) shows the base value with the badge hidden.

| Test | What it asserts |
|------|-----------------|
| `test_garrik_str_card_shows_boosted_score` | Garrik's `.ab-score-disp[data-ab="STR"]` reads "21" (effective, not base 18), `.ab-mod-disp[data-ab="STR"]` reads "+5", and `.ab-boost-badge[data-ab="STR"]` is visible. |
| `test_garrik_dex_card_unboosted` | DEX has no override → `.ab-score-disp[data-ab="DEX"]` reads "14" (base) and `.ab-boost-badge[data-ab="DEX"]` is hidden. |

### `test_movement_trait_badges.py`
v2.286.0 "The Drifting Set" — generalized the v2.285.0 levitate chip into a `#movement-traits` strip covering all four item-sourced movement derived flags (`_movement_traits_for_sheet`): flying speed, levitate at will, spider climb, speed doubling. Each chip has id `#movement-trait-<flag>`. Most demo carriers wear their item equipped+attuned at seed, so those chips render on a plain page load; the inert Boots of Levitation on Magnus are PATCHed on via httpx. (Replaces the v2.285.0 `test_levitate_badge.py`.)

| Test | What it asserts |
|------|-----------------|
| `test_flying_speed_badge_for_kael` | Kael (equipped+attuned Winged Boots) renders `#movement-trait-flying_speed` naming the boots. |
| `test_spider_climb_badge_for_pip` | Pip (equipped Slippers of Spider Climbing) renders `#movement-trait-spider_climb` naming the slippers. |
| `test_speed_doubling_badge_for_krieger` | Krieger (equipped+attuned Boots of Speed) renders `#movement-trait-speed_doubling` naming the boots. |
| `test_levitate_badge_renders_when_boots_attuned` | PATCH Magnus's boots equipped+attuned → `#movement-trait-levitate_at_will` visible naming "Boots of Levitation". Inventory restored after. |
| `test_no_movement_traits_for_plain_pc` | Garrik (no movement item) renders no `.movement-trait-badge` — proving the chips are item-sourced. |

---

## Filed (not yet implemented)

The following endpoint surfaces are exercised indirectly by other tests but lack a dedicated test file. Tracked for future expansion; low regression risk today.

- `/api/campaign/{cid}/encounters/{id}/load` happy-path (destructive — wipes live tokens). The rest of the CRUD surface is now covered in `test_encounters.py`.
- `/api/campaign/{cid}/encounters/{id}/spawn` — not yet covered.
- `/api/campaign/{cid}/character/{id}/economy` GET — the action-chip JSON view.
- Token CRUD beyond `/move` — create, image upload, delete.
- Template CRUD — `/templates`, `/templates/{id}`, image upload, monster import.
- `/character/{id}/sheet-fields` PATCH edge cases — massive-damage instant-kill, temp HP absorption, `hp_change_reason: "heal"` death-save reset.
- `/character/{id}/resource` POST — used by class-feature charge counters.
- `/character/{id}/place-token` POST.
- `/use_item` heal happy path — covered indirectly via the `heal_applied` broadcast in `test_cast_spell_heal.py`.

---

## Known flakes (test-isolation pollution)

The following tests pass in isolation (running the file alone or the test alone) but fail when run as part of the full `pytest tests/harness/` suite due to state pollution from earlier-running tests. Tracked here because the bisection cost per flake is non-trivial (each requires running subsets of the 568-test suite to find the polluter) and the failures are not regressions from any specific commit — they accumulated across the reactions push (v2.69 → v2.80) as more tests share the demo campaign without resetting state between them.

Bisection-find pattern (when you decide to chase one):
1. Confirm the test passes in isolation: `python3 -m pytest tests/harness/<test_file>::<test_name> -v`
2. Run the failing test after each alphabetical group: `python3 -m pytest tests/harness/test_a*.py tests/harness/<file>::<name> -q`, then `test_b*.py`, etc.
3. The group that fails contains the polluter. Bisect down to a single test.
4. Read that test's `finally` block. The pattern is almost always "removes a campaign-setting form key" (interpreted server-side as resetting to OFF) instead of "restores to the demo seed default." v2.79.0 fixed one instance (auto_apply_damage in the v2.67.2 UD test); the same playbook applies here.

| Flake | Failure | First-noticed |
|-------|---------|---------------|
| ~~`test_attack_auto_damage.py::test_attack_auto_apply_on_hit`~~ | ~~Asserts `target_hp_after < pip_hp_before` after a hit. Fails when run after some other test in the suite (depends on `auto_apply_damage` campaign setting + Pip's sheet HP state). The fixture-level `auto_apply_on` cleanup at line 73-76 removes the form key (= OFF) on teardown, matching the v2.79.0-fixed pattern. Likely the source.~~ **Fixed in v2.80.2** — `auto_apply_on` fixture teardown now restores the demo default (ON) instead of removing the key. Full 568-test suite passes. | v2.51.6 (fixed in v2.80.2) |
| `test_aura_of_devotion.py::test_aura_of_devotion_blocks_charmed_install` | Fails when test_aura_of_devotion runs after some other test that polluted Caelan's sheet (lost his aura-of-devotion class feature, or his action economy is in the wrong state). | reactions push era |
| `test_heal_claim_uplift.py::test_apply_healing_runs_life_domain_uplift` | Asserts a `disciple-of-life` broadcast on heal-claim resolution but the buffered broadcasts show only `spell_cast` + `spell_slot_update`. Tavik's action economy or Life Domain feature state is polluted. | reactions push era |
| `test_aura_of_protection.py` (various) | Caelan's level / aura-of-protection state polluted by tests that touched his sheet. | reactions push era |
| `test_danger_sense.py` (various) | Krieger's class_features / level / sheet state polluted. | reactions push era |
| `test_spell_catalog_damage.py` (various) | Demo spell-list state assertions affected by tests that touched sheet.spells (e.g. v2.72.0 Silvery Barbs test patches Thalindra). | reactions push era |

When a flake is fixed at the source, remove its row.

---

## Updating this doc

When you change tests, update the corresponding section in the same commit. Conventions:

- **Added test** → new row in the file's table.
- **Removed test** → strike the row out (`~~test_name~~`) and leave the file's total-test-count number in the header in sync.
- **Renamed test** → rename the row.
- **Behavior change** → update the "What it asserts" cell.

When a whole new test file lands, add a new H3 (`###`) section under the appropriate category. If the category doesn't fit, add a new H2 (`##`) and link it from the [Categories](#categories) list.

The total-test-count line at the top is updated each time the file changes. Run `python3 -m pytest tests/harness/ -q` to confirm the number.
