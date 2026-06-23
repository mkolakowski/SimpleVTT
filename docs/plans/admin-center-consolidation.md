# Consolidate site-admin into the Admin Center

**Status:** 🟠 partial · **Phase 1 (demo tools) shipped v2.573.2** — an opt-in `/tools` page in the Center (demo magic-link mint + demo reset), gated by `ADMIN_CENTER_ADMIN_TOOLS` (default off). **Stubs is deferred** out of Phase 1: its miss-store (`local_features._misses`) is an **in-memory module global in the main-app process**, so a separate Center process would always show an empty list — it can't move until the miss-store is made shared (DB/file-backed). **Phase 2a (user list + create) shipped v2.574.0** — an opt-in `/users` page (read-only list + non-destructive create), same flag, with operator-attributed audit via the new `operator_audit` helper (`actor=admin-center:<operator>`). **Phase 2b (destructive user ops — disable/reset-password/delete, MFA-gated) shipped v2.575.0** — refused unless the session is MFA-verified (403 to header-auth callers); per-row controls render only when verified. **Phase 3a (campaign browse + delete) shipped v2.576.0** — `/campaigns` list + read-only detail + MFA-gated delete. **Phase 3b (member/system/character management, no-upload subset) shipped v2.577.0** — MFA-gated member add/remove, system change, character create/assign/delete. **Audit-scrub ported to the Center (v2.578.0). Phase 4 (route removal) — user CRUD (v2.579.0) + demo reset (v2.580.0) + demo magic-link mint (v2.581.0) removed from the in-app portal; in-app Users is read-only; the public `/demo-login` redemption stays.** **Phase 3b map upload shipped v2.582.0** — MFA-gated campaign map upload + activate via the shared `uploads_data` volume. The thumbnail upload (the last upload remainder of 3b) + Phase 4 removal of the campaign-mgmt/stubs in-app routes remain.

Move the scattered **site-admin** surfaces out of the main app's in-app
`/admin` portal and into the standalone **Admin Center** (port 8015), so
there is one operator console. In scope (per the request): **stubs + demo
tools**, then **user admin**, then **campaign admin**. **Out of scope:**
per-campaign GM settings (`/campaign/{id}/settings` — that's campaign-GM,
not site-admin, and stays put) and homebrew authoring (a separate arc).

This is **security-sensitive**: the Admin Center is today a *read-only*
operator dashboard on the public-demo box; moving write-admin (delete/disable
users, reset passwords, delete campaigns) into it turns it into a read-write
admin app behind the operator credentials. The design below makes that an
explicit, MFA-gated, opt-in escalation — not a silent one.

---

## Substrate as-built (verified v2.573.0)

Two distinct admin systems exist:

- **Admin Center** — `app/admin_center/main.py`, a standalone ASGI app on
  **port 8015**, separate Docker service. **Built from the same image**
  (`simplevtt-app:latest`) so all app models/logic are importable; has
  **DB access** (`DATABASE_URL`, used read-only today for the inventory
  panel); **own auth** — `ADMIN_CENTER_USER`/`PASS` session login (basic-auth
  for `/api/*`) + **optional TOTP MFA** (`ADMIN_CENTER_MFA_ENABLED`,
  `ADMIN_CENTER_TOTP_SECRET`, recovery code). Pages are standalone templates
  (`app/admin_center/templates/*.html`) — no `base.html`; the new
  v2.573.0 `/tests` page is the current model for adding one.
- **In-app `/admin` portal** — `app/routes/admin_routes.py` (prefix `/admin`,
  `require_admin` = a logged-in `is_admin` **User**), with `admin_home.html`.

### Move candidates (verified, file:line)

| Surface | Routes | File | Template | Sensitivity |
|---|---|---|---|---|
| **Stubs tracker** | `GET /admin/stubs`, `/admin/stubs/clear`, `.json` | `admin_routes.py:576-829` | `admin_stubs.html` | low |
| **Demo tools** | `POST /admin/demo/reset`, `POST /admin/demo/mint-magic-link` | `admin_routes.py:768-814`, `demo_magic_link_routes.py:72-106` | inline in `admin_home.html` | low (demo-gated) |
| **User admin** | `GET /admin` + `POST /admin/users/*` (create / disable / reset-password / delete / scrub-audit) | `admin_routes.py:70-267` | `admin_home.html` | **high — destructive** |
| **Campaign admin** | `GET/POST /admin/campaign/{id}/*` (members / characters / maps / system / delete) | `admin_routes.py:268-525` | `admin_campaign.html` | **high — destructive** |

The **auth gap** is the crux: the in-app routes run as a specific
`require_admin` **User**; the Center has no "current User" — it authenticates
an **operator identity** (the `admin_user` session string). Moving the routes
means dropping `require_admin`, running under the Center's auth middleware,
and attributing audit events to the operator, not a User row.

---

## Design

### 1. Identity & audit
The Center authenticates an operator, not an app User. Moved admin actions
run under the Center's existing auth middleware (session, MFA where required)
and **audit-log every mutation** with `actor=admin-center:<admin_user>` +
the target (user id / campaign id) so the action is attributable. (The app's
audit log is the same volume the Center already reads.)

### 2. DB: read-only → scoped read-write
The Center's `DATABASE_URL` is used read-only today. The moved mutations need
write access. Rather than make the whole Center read-write, route the
mutations through a **small set of explicit service functions** (reuse the
existing logic from `admin_routes.py`, imported from the shared image) called
only from the gated write routes — keeping the read paths (inventory) as-is.

### 3. Security gate (the escalation, made explicit)
- A new **`ADMIN_CENTER_ADMIN_TOOLS` env flag (default `false`)** enables the
  write-admin surface at all. Off by default, so existing deployments don't
  silently gain write-admin.
- The write routes are **refused unless MFA is enabled** (`ADMIN_CENTER_MFA_ENABLED`)
  AND the session is MFA-verified — destructive operator actions on a public
  box must sit behind a second factor. The dashboard nags if admin-tools are
  on without MFA.
- Destructive actions (user delete, campaign delete, password reset) require
  an explicit confirm + are audit-logged. No bulk/scriptable delete.

### 4. Route/template porting
Re-home each surface into `app/admin_center/` (routes appended to `main.py`
or a `main`-imported submodule; templates adapted to the Center's standalone
shell, like `tests.html`). The in-app `/admin` pages become a **thin
redirect** to the Center (or a notice) once a surface has moved — they are
NOT left as a live duplicate write-path.

---

## Phases

1. **Phase 1 — demo tools (low-risk). 🟠 Shipped v2.573.2; stubs deferred.**
   A `/tools` page in the Center (`main.py` + `tools.html`, the `/tests`
   pattern) gated by `ADMIN_CENTER_ADMIN_TOOLS` (default off), wiring the
   **demo magic-link mint** (non-destructive) and **demo reset**
   (destructive — double-gated by `DEMO_MODE`, behind a confirm, audit-logged
   with the operator identity). The Center service gets the demo flags +
   `APP_BASE_URL` to mirror the app. The in-app `/admin` demo tools stay live
   for now (additive; retirement is Phase 4 to avoid breaking `/admin`
   mid-migration). **Stubs did NOT move** — `local_features._misses` is an
   in-memory main-app global the Center process can't see; moving it needs a
   shared (DB/file) miss-store first. **Filed follow-up: share the
   `_misses` store, then move the stubs tracker.**
2. **Phase 2 — user admin (high-risk, MFA-gated).** Port user CRUD; the
   destructive routes (disable/delete/reset-password) refused unless MFA is
   on + verified. Audit each mutation. Redirect the in-app `/admin` users
   section to the Center.
   - **Phase 2a — list + create (non-destructive). ✅ Shipped v2.574.0.**
     `/users` page (read-only list + create form) gated by
     `ADMIN_CENTER_ADMIN_TOOLS`. New `operator_audit` helper appends
     operator-attributed audit lines (`actor=admin-center:<operator>`) to
     the shared log — the Center has no `User` row so `record_admin_action`
     (User-FK row) doesn't apply. Service functions live in
     `user_admin.py` (the destructive ones ship but are wired by 2b).
   - **Phase 2b — destructive ops (disable/reset-password/delete). ✅ Shipped v2.575.0.**
     The destructive routes share a `_destructive_gate()` (404 when
     admin-tools off, 403 when not MFA-verified). `_mfa_verified()` =
     `mfa_enabled()` AND session `admin_authed` — so a basic-auth *header*
     caller (no session) is always refused. Per-row controls render only
     when verified; otherwise a 🔒 nag explains how to unlock. Each
     mutation is audited via `operator_audit`. The in-app `/admin` user
     redirect is deferred to Phase 4 (still additive, no live duplicate
     removed yet).
3. **Phase 3 — campaign admin (high-risk, MFA-gated).** Port site-admin
   campaign management (members/characters/maps/system/**delete**), same MFA
   gate + audit. Redirect `/admin/campaign/{id}`.
   - **Phase 3a — browse + delete. ✅ Shipped v2.576.0.** `/campaigns` list +
     read-only `/campaigns/{id}` detail (members/characters/maps/system) +
     **delete campaign** behind the shared `_destructive_gate()` (MFA-gated,
     audited `admin.campaign_delete`). Service funcs in `campaign_admin.py`.
   - **Phase 3b (no-upload subset) — member/system/character mgmt. ✅ Shipped v2.577.0.**
     MFA-gated `POST /campaigns/{id}/members/add|remove`, `/system`, and
     `/characters/create|{cid}/assign|{cid}/delete`, audited; the management
     controls render only on an MFA-verified detail page. Service funcs in
     `campaign_admin.py`.
   - **Phase 3b (uploads) — map upload + activate. ✅ Shipped v2.582.0.**
     Answered the upload-target question with a **shared volume**: the app's
     `uploads_data` volume is mounted RW into the admin-center at the same
     path, so the Center writes the file (uuid-named, Pillow dimension
     detection, ≤80 MB) and the app serves it at `/static/uploads/maps/...`.
     `create_map`/`activate_map` in `campaign_admin.py`; MFA-gated + audited.
   - **Phase 3b (uploads) — thumbnails. ⚪ Next.** Port thumbnail
     upload/clear (same shared volume, smaller surface). After this the
     in-app campaign upload routes can retire.
4. **Phase 4 — retire the in-app portal.** Once 1–3 are in the Center, reduce
   `admin_home.html` to a pointer to the Center; drop the moved routes.
   - **Phase 4 (soft-deprecation step). 🟠 Shipped v2.577.2.** A migration
     notice atop the in-app `/admin` page points operators to the Center;
     the in-app forms stay live. Hard route removal is deferred per-surface
     because (a) three surfaces lack Center parity — `users/{id}/scrub-audit-log`,
     campaign `maps`/`thumbnail` uploads, and the stubs tracker — and (b) five
     harness suites (`test_admin_audit`, `test_demo_magic_link`,
     `test_admin_user_audit_scrub`, `test_admin_demo_reset`,
     `test_cloudflare_banning`) still exercise the in-app routes.
   - **Audit-scrub ported. ✅ v2.578.0.** `POST /users/{id}/scrub-audit-log`
     now lives in the Center (MFA-gated, JSON-contract parity, per-row
     **Scrub log** button) — the last user-admin parity gap. In-app user
     CRUD is now fully duplicated and ready to retire.
   - **Phase 4 (route removal) — user CRUD. ✅ Shipped v2.579.0.** Removed the
     five in-app user write routes (`POST /admin/users`, `/disable`,
     `/reset_password`, `/delete`, `/scrub-audit-log`); the in-app Users
     section is now read-only with a pointer to the Center. Deleted the
     superseded `test_admin_audit.py` + `test_admin_user_audit_scrub.py`;
     added `test_admin_routes_retired.py` (routes-are-gone regression).
   - **Phase 4 (route removal) — demo tools. ✅ Shipped v2.580.0 + v2.581.0.**
     Removed the in-app `POST /admin/demo/reset` (v2.580.0) and `POST
     /admin/demo/mint-magic-link` + its UI (v2.581.0) — the Center `/tools`
     carries both. The public `/demo-login` redemption stays; the demo
     magic-link happy-path test was rewired to mint via the Center (real
     cross-service contract). Scheduler reseed unchanged.
   - **Phase 4 (route removal) — remaining. ⚪ Per-surface, after parity.**
     Campaign mgmt routes (needs uploads ported to the Center first) and the
     stubs tracker (needs the shared miss-store) still live in-app.

---

## Test contract

- Each moved surface: a `tests/harness/test_admin_center.py` case (session
  login → the page renders / the action mutates) following the v2.573.0
  `/tests` pattern. The Center's harness tests already hit port 8015.
- **Security gates:** the write routes return 403/disabled when
  `ADMIN_CENTER_ADMIN_TOOLS` is off; the destructive routes return 403 when
  MFA is off (or session unverified); a mutation writes an audit event with
  the operator actor.
- A regression test that the in-app `/admin` write routes are gone /
  redirected after each phase (no live duplicate).

---

## Non-goals / open questions

- **Out of scope:** campaign-GM settings (`/campaign/{id}/settings`) and
  homebrew authoring (`/admin/homebrew`) — separate concerns.
- **Open:** do we unify the two auth systems (app `is_admin` Users vs the
  Center's operator creds), or keep them separate (this plan assumes
  separate — operator identity)? Unification is a bigger, later effort.
- **Open:** whether MFA should be a *hard* requirement (routes disabled) or a
  *strong nag* for the destructive surface. This plan proposes hard-gate for
  destructive actions on the public box.

This doc is surfaced through the wiki at `/wiki/doc/plan-admin-center-consolidation`.
