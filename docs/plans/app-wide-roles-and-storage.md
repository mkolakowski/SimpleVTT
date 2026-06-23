# App-wide roles + GM/player caps + storage accounting & limits

**Status:** 🟠 partial · **Arc A1 (role substrate) shipped v2.584.0** — the
app-wide `User.is_gm` role (schema v76), `PLAYER_CHARACTER_LIMIT` (default 5)
+ `GM_CAMPAIGN_LIMIT` (default 10) config, the `require_gm` auth gate, and
demo-seed role back-fill. Arcs A2–A4 (campaign-create gating + GM cap;
player character cap; Admin Center role assignment) and Arc B (storage
accounting + per-user/per-campaign limits) are pending.

## Context

SimpleVTT had a single app-wide flag, `User.is_admin`. Any logged-in user
could create a campaign (`POST /campaigns`, gated only by `require_user`),
there was no cap on character/campaign creation, and no storage accounting
or quota — uploads accumulated unbounded on the shared `uploads_data`
volume. This work introduces an **app-wide role model** + **resource
governance**.

## Role model

Three app-wide roles, independently assignable (a user can be GM *and*
admin):

- **player** — default. A regular user; capped at `PLAYER_CHARACTER_LIMIT`
  owned characters.
- **GM** — `User.is_gm`. May create + run campaigns **in the main VTT app**
  (campaign management stays in the main app, not the Admin Center). Capped
  at `GM_CAMPAIGN_LIMIT` owned campaigns.
- **admin** — `User.is_admin` (unchanged; driven by the `ADMINS` config).
  Has Admin Center access and **assigns roles** to users there. Admins are
  uncapped and implicitly may create campaigns (admin ⊇ GM for the gate).

GM is **console-only** — granted via the Admin Center (no env list). This is
distinct from per-campaign GM (`Campaign.gm_user_id` /
`CampaignMembership.is_gm`), which is unchanged.

`require_gm` (`app/auth.py`) is the gate: `is_gm or is_admin`, else 403.

## Storage attribution

Every uploaded file (`/static/uploads/<subdir>/`) is referenced by a DB URL
column tied (directly or transitively) to a `campaign_id` →
`Campaign.gm_user_id`. So each file is attributed to its **campaign**, and
the campaign to its **GM user**; per-user usage = sum over the campaigns
they GM. Files referenced by no DB row → an "unattributed" bucket. This
avoids double-counting (player-owned character portraits live in the GM's
campaign and count there). Usage is measured by an **on-demand filesystem
scan** (cached briefly) — no per-file DB size tracking. Storage limits are
**per-user** + **per-campaign**, **default unlimited** (nullable;
`0`/blank = unlimited), set in the **Admin Center**.

## Phases

### Arc A — roles + caps
1. **A1 — substrate. ✅ v2.584.0.** `User.is_gm` (schema v76),
   `PLAYER_CHARACTER_LIMIT`/`GM_CAMPAIGN_LIMIT` config, `require_gm`, demo
   roles (demo GM `is_gm=True`; players are players).
2. **A2 — campaign creation gated + GM cap.** `POST /campaigns` requires
   `is_gm or is_admin`; GM-not-admin capped at `GM_CAMPAIGN_LIMIT`. UI gating.
3. **A3 — player character cap.** The player character-create paths cap at
   `PLAYER_CHARACTER_LIMIT`; GM/admin uncapped. UI.
4. **A4 — Admin Center role assignment.** `POST /users/{id}/role`
   (MFA-gated, audited) + role pills/toggles on the Center `/users` page.

### Arc B — storage accounting + limits
1. **B1 — accounting + Admin Center storage views.** A storage module
   (on-demand scan) + `/storage` page with per-user (drill into
   per-campaign + per-type) and per-campaign breakdowns.
2. **B2 — limits + enforcement.** `User.storage_limit_bytes` +
   `Campaign.storage_limit_bytes` (schema v77), Admin Center edit UI
   (MFA-gated, audited), and a shared `check_quota` enforced before write in
   the upload routes.

## Test contract

- Role gate: `require_gm` accepts GM+admin, rejects players; demo GM seeds
  `is_gm=True`.
- A2/A3: player → 403 on campaign-create + over-cap character-create; GM
  under/over the campaign cap; admin uncapped.
- A4: role toggle round-trip (MFA-on), header-auth refused, auth-gated.
- B1: accounting attribution + buckets; `/api/storage` shape + `/storage`
  renders.
- B2: quota helper under/over both limits; an upload route rejects when the
  campaign/user is over limit; unlimited (default) passes.

This doc is surfaced through the wiki at
`/wiki/doc/plan-app-wide-roles-and-storage`.
