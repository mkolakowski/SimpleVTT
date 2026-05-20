# SimpleVTT wiki

In-repo documentation hub for SimpleVTT — how-to guides, system explainers, and visual references for contributors and operators. New guides land here as `.md` (for prose) or `.html` (for visual mocks). Versioned alongside the code so every guide carries the version it was written for.

This wiki complements the canonical references that live elsewhere in the repo:

- **`README.md`** (repo root) — install + deploy quickstart.
- **`CHANGELOG.md`** (repo root) — release history + version-bump rules.
- **`CLAUDE.md`** (repo root) — contributor / agent guidelines.
- **`docs/roll-log-card-layout.md`** — text/semantic reference for the roll-log card structure (companion to `roll-log-guide.html`).
- **`docs/test-harness-coverage.md`** — categorized index of every harness test.
- **`docs/plans/`** — design docs + implementation roadmaps (action-economy, targeting, test-harness, etc.).

## Available guides

| Guide | Format | Audience | Status |
|-------|--------|----------|--------|
| [Roll-log guide](roll-log-guide.html) | HTML (visual) | GMs + contributors | ✅ shipped (v2.43.1) |
| [Toast notifications guide](toast-notifications-guide.html) | HTML (visual) | GMs + contributors | ✅ shipped (v2.43.8) |

## TODO — guides to write

This wiki is a stub. The list below is what we want it to grow into.

### How-to guides (operator + GM-facing)

- [ ] **First-run setup.** Stand up a fresh `docker compose up`, register the first user, create a campaign, invite players, and run a first session. Where the seed data goes; how to disable demo mode; how to reset the database.
- [ ] **Inviting players.** The two membership flows (open registration vs invite-only), GM colors, per-player portrait, the demo-user accounts.
- [ ] **Running a session as GM.** Initiative tracker, action-economy chips, target picker, the GM Tools drawer, encounter snapshots.
- [ ] **Building an encounter.** Encounters panel CRUD, token templates, monsters from the SRD bestiary vs homebrew, spawn-point layout, default-encounter wiring on a campaign.
- [ ] **Maps + grids + tokens.** Uploading maps, scaling, grid overlay (`show_grid`), placing PC and monster tokens, the token-tracker side panel.
- [ ] **Homebrew content authoring.** Custom monsters (template editor), custom items, custom spells, the homebrew JSON contract.
- [ ] **Player onboarding.** What players see vs. what the GM sees, the character sheet, the roll log, the dice toast, the per-character action economy chips.
- [ ] **Backups + restore.** The `simplevtt-backup` container, daily `pg_dump` cycle, restoring from a backup, exporting / importing a campaign.
- [ ] **Theming.** The 8 built-in themes (Dark / Midnight / Dim / Light / Forest / Bubblegum / OLED / Fire), the per-user theme preference, font preferences, accessibility considerations (contrast, motion).

### System explainers (contributor-facing)

- [ ] **Architecture overview.** FastAPI + SQLAlchemy + Jinja2 + HTMX + vanilla JS + Postgres. Where the realtime hub lives (`app/realtime.py`). The per-campaign WebSocket fan-out model. Why no SPA framework.
- [ ] **The action-economy system.** The four chips (Act / Bns / Rxn / Mov), the over-budget gate, strict-action-economy mode, the `_mark_battle_economy` helper, Phase 4a layered dimming, the audit badge. See also `docs/plans/action-economy.md`.
- [ ] **The targeting system (Phase T.0–T.9).** Double-tap targeting, the target-picker modal, the targeting state machine (`window._targetingState`), localStorage cross-tab sync, the mobile 🎯 button. See also `docs/plans/targeting.md`.
- [ ] **The buff slot system (Phase C).** `_install_buff` / `_remove_buff` / `_get_buffs`, concentration anchors, paired-buff cleanup on concentration drop, save-or-suck condition install, the buff descriptive layer on the sheet.
- [ ] **The damage flow (Phase B).** Resistance, vulnerability, Hunter's Mark, Colossus Slayer, Smite uplifts, the `_attack_damage_log` for Undo, the `/undo_attack_damage` endpoint.
- [ ] **Auto-resolution: attack, save, heal, damage.** When the server resolves rolls server-side vs prompts the client; the campaign-level `auto_apply_damage` toggle; `auto_attack_*` / `auto_save_*` / `auto_heal_*` payload fields; the spell-cast pill row.
- [x] **The roll log + dice toast.** Card variants, the oversized pill row, persistence in localStorage, visibility filtering, the dice toast lifecycle. → [roll-log-guide.html](roll-log-guide.html) + [toast-notifications-guide.html](toast-notifications-guide.html).
- [ ] **The click-through test harness.** Why the harness exists, how `conftest.py` wires the demo PCs to authenticated httpx clients, the `WSCollector` contract, when to add a happy-path vs error-path test. See also `docs/plans/test-harness.md`.
- [ ] **SRD + local content resolution.** `app/data/local/dnd5e/` JSON files, the `local_content.resolve(slug, type=…)` lookup, how spells / items / monsters are enriched.
- [ ] **Schema migrations.** The inline `_apply_inline_migrations()` model in `app/database.py`, `SCHEMA_VERSION` bumps, how to write a forward-only migration step.
- [ ] **Realtime broadcasts.** The full broadcast catalog (battle_update, roll, weapon_attack, spell_cast, feature_used, resource_update, presence_update, character_death_save, heal_applied, …), payload shapes, visibility filtering, client handler map.

### Reference cards

- [ ] **Card variant reference** — quick visual index of every roll-log card type. (Roll-log guide HTML is the first entry of this category.)
- [ ] **Theme palette reference** — side-by-side strip showing all 8 themes' tokens (--bg, --bg-2, --fg, --accent, --danger, --c-heal, --c-crit, --c-damage, --c-buff).
- [ ] **Endpoint catalog** — every `/api/campaign/{cid}/…` endpoint with method, payload shape, broadcast(s) emitted. Generated or hand-curated.

## Contributing guides

A guide entry lives at `docs/wiki/<slug>.{md,html}` and gets a row in the "Available guides" table above. Each guide should:

- Open with a one-sentence summary of what it covers + audience.
- State the version it was written for (so future readers can date the screenshots / examples).
- Include code-location pointers for anything in the codebase the reader might want to grep.
- For HTML mocks: be self-contained (inline CSS, no external assets) so it can be opened with `file://` and not break.

Update this README's table when you add a guide so the index stays in sync.
