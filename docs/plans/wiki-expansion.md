# Wiki expansion plan

Companion to `docs/wiki/README.md`. The README enumerates a TODO list of guides to write; this doc adds prioritization, sequencing, dependencies, and the missing pages that the TODO list doesn't cover. Read this when you're picking what to write next.

## Current state (as of v2.43.12)

**Shipped:**
- `/wiki` — Jinja landing page (table of guides + TODO roadmap).
- `/wiki/roll-log-guide` — visual reference for card variants + outcome pills.
- `/wiki/toast-notifications-guide` — dice toast + status toast anatomy + gallery.

**TODO in `docs/wiki/README.md`:** 9 how-tos + 9 system explainers (one ✅) + 3 reference cards.

## Recommended sequencing

Group by *what each page unlocks* — write the foundational ones first because later guides reference them.

### Tier 0 — foundational (unblocks everything else)

Write these first. Other guides link into them rather than re-explaining the same ideas.

| Page | Format | Why first |
|------|--------|-----------|
| **Architecture overview** | MD | Every system explainer needs to point to the realtime hub, the request lifecycle, the per-campaign WS fan-out. Without this, every other contributor doc has to redefine the basics. |
| **Realtime broadcasts catalog** | MD | The shape tests at `tests/harness/test_broadcast_payload_shapes.py` document fields; this guide names the broadcast types + their handler functions in `tabletop.js`. The roll-log + toast guides already reference broadcast names without explaining the catalog. |
| **Endpoint catalog** | MD (hand-curated) | Every how-to references endpoints (`/cast_spell`, `/attack`, `/use_feature`); a single index reduces churn. Auto-generation from OpenAPI is filed as a future enhancement — the curated version is faster to ship now. |

### Tier 1 — operator + new-user onboarding

The "first-day at the table" experience. Each guide stands alone but `First-run setup` is the entry point.

| Page | Format | Notes |
|------|--------|-------|
| **First-run setup** | MD | `docker compose up`, register first user, create a campaign, invite players. Include the `APP_ALLOW_LOCAL_REGISTRATION` toggle, the demo accounts, the schema migration on first start. |
| **Inviting players** | MD | Membership flows (open vs invite-only), per-user portrait + color, demo accounts. Short; mostly screenshots. |
| **Running a session as GM** | MD + inline HTML mocks | The biggest GM-facing guide. Initiative tracker, action-economy chips, target picker, GM Tools drawer, encounter snapshots, the visibility toggle on rolls. Cross-references `Building an encounter` + the roll-log + toast guides. |
| **Player onboarding** | MD + screenshot mocks | Mirror image of "Running a session" from the player side — what they see, what they can do, the per-character action-economy chips on their own sheet. |
| **Building an encounter** | MD | Encounters CRUD panel, token templates, monsters (SRD + homebrew), spawn-point layout, default-encounter wiring. References `Maps + grids + tokens`. |
| **Maps + grids + tokens** | MD + diagrams | Uploading maps, scaling, `show_grid` toggle, placing tokens, the token-tracker side panel. Includes the per-map config (show-grid, scale, background color). |

### Tier 2 — system deep-dives (contributor-facing)

These guides assume Tier 0 has been read. They explain a single subsystem in depth.

| Page | Format | Notes |
|------|--------|-------|
| **The action-economy system** | MD | The four chips, over-budget gate, `strict_action_economy`, `_mark_battle_economy`, Phase 4a dimming, the audit badge. Cross-link `docs/plans/action-economy.md` (the design rationale; this is the operational explainer). |
| **The targeting system (Phase T.0–T.9)** | MD | Double-tap, picker modal, `window._targetingState`, localStorage cross-tab sync, the mobile 🎯 button. Link `docs/plans/targeting.md`. |
| **The buff slot system (Phase C)** | MD | `_install_buff` / `_remove_buff` / `_get_buffs`, concentration anchors, paired-buff cleanup, save-or-suck installs, the sheet-side buff descriptive layer. |
| **The damage flow (Phase B)** | MD | Resistance, vulnerability, Hunter's Mark, Colossus Slayer, Smite uplifts, `_attack_damage_log`, `/undo_attack_damage`. |
| **Auto-resolution: attack, save, heal, damage** | MD | When the server resolves rolls vs prompts the client. The `auto_apply_damage` toggle. The `auto_attack_*` / `auto_save_*` / `auto_heal_*` payload sub-trees. Cross-links the roll-log + toast guides. |
| **The click-through test harness** | MD | Why it exists, `conftest.py`, the `WSCollector`, when to add a happy-path vs error-path test, the payload-shape pattern from v2.43.12. Link `docs/plans/test-harness.md` + `docs/test-harness-coverage.md`. |
| **SRD + local content resolution** | MD | `app/data/local/dnd5e/`, `local_content.resolve`, how spells / items / monsters are enriched. The `homebrew_data` Docker volume. |
| **Schema migrations** | MD | The inline `_apply_inline_migrations()` model, `SCHEMA_VERSION` bumps, writing forward-only steps. The boot-time migration scan. |

### Tier 3 — content authoring + customization

| Page | Format | Notes |
|------|--------|-------|
| **Homebrew content authoring** | MD | Custom monsters (template editor), items, spells. The homebrew JSON contract. The Homebrew tab in the campaign settings. |
| **Theming** | MD + HTML palette mocks | The 14 themes (8 core + 6 fantasy), per-user theme + font preferences, `--c-*` semantic colors, accessibility (contrast, motion). |
| **Backups + restore** | MD | `simplevtt-backup` container, `pg_dump` daily cycle, restoring, exporting/importing a campaign. The `BACKUP_RETENTION_DAYS` env var. |
| **Audio system** | MD | Playlists, categories, GM controls, per-user volume preferences, the `auto_play_*` campaign settings. |

### Tier 4 — references (mostly visual)

| Page | Format | Notes |
|------|--------|-------|
| **Card variant reference** | HTML | Already partially shipped via the roll-log guide. Could pull all four card types into one quick visual index. |
| **Theme palette reference** | HTML | Side-by-side strip of all 14 themes' tokens. Useful when picking colors for new UI surfaces. |
| **Endpoint catalog** | MD (already listed in Tier 0 too) | Move here once Tier 0 is shipped — this is the maintenance-mode reference, not the writeup. |
| **Broadcast payload catalog** | MD | Per-broadcast-type field list with semantics. Companion to the harness's payload-shape tests. |
| **Class-by-class reference** | MD | Per-demo-PC summary — which features are wired up, which are filed. Snapshot of the class-content matrix from `docs/plans/class-content-status.md`. |

## Pages the existing TODO doesn't cover (recommended additions)

These weren't in the v2.43.12 `docs/wiki/README.md` TODO list. Add them.

| Page | Format | Tier | Why |
|------|--------|------|-----|
| **The character sheet** | MD + screenshots | 1 | The sheet is the most-touched player surface and currently has no anatomy guide. Cover the tabs (Abilities / Skills / Combat / Spells / Class / Inventory / Description), the action-economy chip strip, the spell-slot tracker. |
| **The initiative tracker drawer** | MD + HTML mock | 1 | The GM-facing drawer with buffs, chips, HP, AC, and turn-cycling. Covers buff chip mechanics + duration countdown. |
| **The target picker modal** | MD | 2 | The modal that opens for spells / Lay on Hands / Bardic Inspiration / Cutting Words when no target is preset. AoE picker is planned (T.5+) but the single-target version is shippable now. |
| **Encounters CRUD** | MD + screenshots | 1 | Save snapshot → name it → duplicate → rename → load → delete. The default-encounter wiring on a campaign. |
| **Roll requests** | MD | 2 | The GM-prompted "everyone roll X" flow. The per-player targeting (v1.7.1+), the Roll button rendering, the result correlation. |
| **Death saves + dying state machine** | MD + diagram | 2 | The 3-success / 3-failure state machine, the auto-stabilize-on-heal path, instant-kill (massive damage), the broadcast that updates the sheet + the tracker. |
| **Demo mode** | MD | 3 | What `DEMO_MODE=true` does. Reset interval, demo accounts, the "Use demo credentials" auto-fill button, why the dev's local data doesn't survive a reset. Already partially documented in `docs/plans/demo-mode.md` — promote to a wiki guide. |
| **Self-host upgrade guide** | MD | 3 | Going from version X to Y. The schema-migration model, the static-asset cache buster, when to rebuild vs restart. Reference the `ShareOnboardingGuide` flow if it ever ships. |
| **Troubleshooting + FAQ** | MD | 3 | WS disconnects, browser cache, "why is my roll missing", login-required redirects, the 401 → /login bounce. |
| **Browser support + mobile usage** | MD | 3 | What works on iOS Safari, Android Chrome, desktop. The touch-action manipulation hacks (the iPad double-fire fixes). The 44 px touch target rule. |
| **Visibility model + GM permissions** | MD | 2 | Who sees what. The `gm_only` / `gm_and_roller` / `public` filter. GM vs player permissions. The campaign membership model. |
| **Spell content library status** | MD | 4 | Per-spell status: implemented, auto-resolution support level (heal / attack / save), filed. Snapshot from `app/data/local/dnd5e/spells/`. |
| **Monster bestiary status** | MD | 4 | Per-monster status: in `app/data/local/dnd5e/bestiary/`, has actions wired, has uplift support. |
| **The Use Item / potions flow** | MD | 3 | Quaffing a potion of healing, the v2.5.0 house rule that potions are a bonus action, the `_apply_heal_to_combatant` integration. |
| **Multi-user concurrency** | MD | 4 | What happens with two clients editing the same character. The realtime hub's serialization model. Race conditions filed. |

## Cross-cutting concerns

Things every guide should follow (codify in `docs/wiki/README.md`'s "Contributing guides" section):

- **Version stamp.** Every guide carries the version it was written for in its title (so screenshots can be dated when they go stale).
- **Code-location pointers.** Every guide ends with a "Where the code lives" section listing the relevant files + functions.
- **Cross-links.** Every guide links to its design-doc sibling in `docs/plans/` when one exists, so design rationale and operational reference stay paired.
- **Self-contained HTML.** Visual guides use inline CSS that adapts to the user's theme via the `wiki_routes.py` `data-theme` injection (see `roll-log-guide.html` for the pattern).
- **Left-justified prose in centered column.** The v2.43.10 layout pattern — `max-width: ~880px; margin: 0 auto;` and natural left-aligned text inside.

## What to ship next (recommended order)

1. **Realtime broadcasts catalog** (Tier 0) — short, mostly a table. Unblocks the system explainers.
2. **Endpoint catalog** (Tier 0) — hand-curated table of every `/api/campaign/{cid}/…` endpoint.
3. **Architecture overview** (Tier 0) — high-level system map.
4. **First-run setup** (Tier 1) — the new-user landing.
5. **Running a session as GM** (Tier 1) — the densest GM doc, references all the Tier 2 system explainers.
6. **The character sheet** (new) — the most-touched player surface.
7. **Demo mode** (new, Tier 3) — promote from `docs/plans/demo-mode.md`.

After these seven, the rest can land in any order; each new guide's prerequisites are already shipped.

## Where this doc lives

`docs/plans/wiki-expansion.md`. Companion to `docs/wiki/README.md`. When a guide on this list ships, tick the box in the README and add a row to its "Available guides" table — leave this plan doc untouched as a snapshot of the v2.43.13 roadmap.
