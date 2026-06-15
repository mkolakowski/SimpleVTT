# SimpleVTT — Bug Tracker

The single canonical list of known defects, RAW divergences, latent test-coupling hazards, and stale-doc bugs. Forward-looking *features* live in [`TODO.md`](TODO.md); *shipped* work lives in [`TODONE.md`](TODONE.md). This file is for things that are **wrong** (or known-fragile) today.

> **Why this file exists.** Bugs used to be scattered across `TODO.md`'s "Test Infrastructure" / "Class Features" sections and inline `**Status:**` notes in `docs/plans/*.md`. This tracker consolidates them so there's one place to scan. Plan docs may still carry an inline note where the bug is a *deferred design decision*, but the authoritative entry — severity, repro, fix paths — lives here.

**Severity legend:**

| Tag | Meaning |
|-----|---------|
| 🔴 P1 | Breaks a user-facing flow or masks regressions in CI; fix soon. |
| 🟡 P2 | Real defect with a workaround or local-only coverage; schedule it. |
| 🟢 P3 | Cosmetic, stale-doc, RAW divergence accepted for v1, or latent hazard not yet triggered. |

**Status vocabulary:** `OPEN` · `NEEDS-VERIFY` (likely fixed, awaiting confirmation) · `WONTFIX` (accepted divergence) · `FIXED` (move to TODONE on close).

---

## Test infrastructure

### B1 — Skull-overlay test skipped in CI (missing emoji font) · 🟡 P2 · OPEN
**Source:** was `TODO.md` › Test Infrastructure. **Filed 2026-05-25 (v2.49.241).**
`tests/encounter_sim/level_3_edge_cases/death_saves/test_skull_overlay_at_zero_hp.py::test_skull_overlay_renders_on_zero_hp_token` is skipped pending font diagnosis. CI's Playwright Chromium samples `[66, 66, 66, 255]` (gray tofu) at the token center — the ☠ emoji doesn't render because the runner image lacks an emoji font. Locally (macOS) the skull renders fine.
**Fix paths:** (1) add `sudo apt-get install -y fonts-noto-color-emoji` to the Playwright job in `.github/workflows/test-harness.yml` before `playwright install` — smallest commit; (2) change the assertion from canvas-pixel sampling to a `window.battle` + draw-fired flag — most resilient; (3) rewrite the overlay as an SVG/HTML element over the canvas — most invasive. The v2.49.4 regression class is still covered locally.

### B2 — Two encounter-sim tests skipped (Garrik not tokenized) · 🟡 P2 · OPEN
**Source:** was `TODO.md` › Test Infrastructure. **Filed 2026-05-25 (v2.49.236).**
Skipped: `tests/encounter_sim/level_2_encounter/test_tavern_brawl_baseline.py::test_tavern_brawl_3_pcs_3_npcs_round_cycle` and `tests/encounter_sim/level_3_edge_cases/action_economy/test_action_surge_refunds_chip.py::test_action_surge_refunds_action_chip`. Both seed Garrik (Fighter) via `seed_battle_into_page`, but tabletop orphan-cleanup (`tabletop.html:4807`) drops any combatant whose `char_id` isn't tokenized in the demo seed. v2.49.172's slim from 12 → 6 tokenized PCs removed Garrik from `seed_tokens()` but didn't update these tests.
**Fix paths:** (1) add Garrik back to `seed_tokens()` (cheapest if no other tokenized PC is a Fighter — the Action Surge test needs a tokenized Fighter); (2) swap fixtures to a tokenized PC (works for the brawl test, not Action Surge); (3) swap one of the tokenized six for Garrik (impacts `class-content-status.md` demo-roster notes). Backbone `tests/harness/test_use_action_surge.py` still covers the chip-refund contract via direct PUT `/battle`; only the Playwright UI assertion is gated.

### B4 — Encounter-sim coverage gap: pill-drop regressions pass the Python harness · 🟡 P2 · OPEN
**Source:** `docs/plans/encounter-sim-test-suite.md`. Pure client-side regressions (e.g. an init-tracker pill that fails to drop / render) can pass the Python HTTP+WS harness because it asserts on endpoint contracts, not on rendered DOM. The encounter-sim Playwright layer is the intended net but Level 3 is only partially landed (see B8). Until Level 3 completes, some UI regressions have no automated guard.

### B8 — `aoe_persistent_marker` Level-2 encounter-sim test never landed · 🟢 P3 · OPEN
**Source:** `docs/plans/encounter-sim-test-suite.md`. A planned Level-2 test for the persistent AoE marker (e.g. Spike Growth / Web zone rendering across rounds) was filed but never written. Low blast radius — the marker has harness coverage at the endpoint level; this is the missing UI-round assertion.

### B9 — Latent test coupling: a Caelan level-bump breaks `test_attack_divine_smite_spends_slot` · 🟡 P2 · OPEN
**Source:** was `TODO.md` › Class Features. Sir Caelan Lightbringer is seeded at Lv 7. Bumping him to Lv 9+ (e.g. for Aura of Courage) flips proficiency +3 → +4, so his Longsword attack bonus goes +6 → +7, which **breaks** the hardcoded assertion in `tests/harness/test_attack.py::test_attack_divine_smite_spends_slot`. Not broken today — but any commit that bumps Caelan must audit-and-fix this test in the same change. Filed here so it isn't a surprise.

---

## Rules-engine divergences (RAW-bent / partial automation)

### B6 — Sorcerer Quickened Spell is announce-only · 🟡 P2 · OPEN
**Source:** `docs/plans/sorcery-points-and-metamagic.md`. 7 of 8 PHB metamagics are fully automated; Quickened Spell only announces (no action-economy override that lets the spell be cast as a bonus action). Needs the action-economy override path. The AoE multi-target Empowered loop is the other outstanding metamagic finisher.

### B7 — Reaction spells only partially automated · 🟡 P2 · OPEN
**Source:** `docs/plans/reactions-automation.md`. Shield / Counterspell / Hellish Rebuke / Absorb Elements are not fully wired into the reaction pipeline — the substantial remaining slice is the v3 pending-damage state machine for auto-resolution (Phases 1–6 shipped). Until then these reactions are GM-adjudicated.

### B10 — Fighter Indomitable shipped RAW-bent (advantage, not reroll-on-failure) · 🟢 P3 · WONTFIX (v1)
**Source:** was `TODO.md` › Class Features (v2.56.0 "Iron Will"). RAW Indomitable lets you **reroll** a failed save; the v1 implementation grants **advantage on the next save** instead, because the true post-roll reroll needs an undo-and-reapply path for already-installed conditions (its own substantial commit). Accepted divergence for v1; filed for a future precise implementation.

### B3 — Roll-log card collapses when the GM rolls on behalf of a player · 🟢 P3 · NEEDS-VERIFY
**Source:** `TODONE.md` (likely fixed v2.99.71). The roll-log card reportedly collapsed/mis-rendered when a GM rolled for a player. Believed fixed in v2.99.71 but never browser-confirmed. Needs a manual click-through to close or reopen.

---

## Stale-doc bugs

### B5 — `automation-coverage.md` row counts pinned at v2.99.460 · 🟢 P3 · OPEN
**Source:** `docs/automation-coverage.md` + `docs/plans/full-feature-automation.md`. The per-feature coverage counts in `automation-coverage.md` are stale (last recomputed ~v2.99.460). Superseded for headline numbers by the [SRD audit](TODO.md#srd-5e-audit-v23150-refresh); this doc still needs a row-level refresh or a pointer to the audit.

### B11 — Unified-mini-sheet visual regressions slip past the PC harness · 🟢 P3 · OPEN
**Source:** `docs/plans/unified-mini-sheet.md`. The mini-sheet has 3 mockups but Phases 1–3 are unstarted; visual regressions in the eventual implementation won't be caught by the PC HTTP harness (same class of gap as B4). Re-evaluate when the mini-sheet ships.

### B12 — `class-content-status.md`: stale "feat effects uniformly ⚪" note · 🟢 P3 · OPEN
**Source:** `docs/plans/class-content-status.md` (the "L416 doc note"). An older line states mechanical feat effects are uniformly ⚪ unstarted; six of seven listed feats now have automated intercepts (War Caster, Mage Slayer, etc.). The living-inventory section already flags this as stale — the original line should be edited to match.

### B13 — `class-content-status.md`: stale "recipient die consume pending" note · 🟢 P3 · OPEN
**Source:** `docs/plans/class-content-status.md` (cross-cutting C). Bardic Inspiration recipient side shipped (v2.97.56–.57, `/apply_bardic_inspiration_die` + banner). An older cross-cutting note still says the recipient die-consume is pending. Edit the original line.

### B14 — `class-content-status.md`: historical template/endpoint-URL silent test-skip · 🟢 P3 · OPEN
**Source:** `docs/plans/class-content-status.md:330`. A documented case where a test silently skipped due to a template/endpoint URL mismatch. Confirm whether it's still live or already resolved, then close or fix.

---

## Borderline (almost certainly resolved — verify before closing)

- **M1 — CON max-HP recompute path.** Believed fully resolved by the permanent-ability-increase reconciliation (v2.312.0–v2.314.0). Verify no stale dual-path remains, then delete this line.
- **M4 — Demo audio + a couple of tokens never shipped.** Goblin Captain / Cleric NPCs render as color swatches rather than token art; some demo audio cues were planned but not seeded. Cosmetic; low priority. (Tracked here, not in TODO, because it's "incomplete demo content," not a feature request.)

> **Not bugs (feature gaps tracked in [TODO.md](TODO.md)):** the magic-item content tail (116/239 items), spell upcast scaling on ~110 cast-and-broadcast-only spells, and the 24 ⚪ class-feature rows are *unbuilt automation*, not defects — they live in the [SRD audit](TODO.md#srd-5e-audit-v23150-refresh) priority list.
