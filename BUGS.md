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

### B12 — `class-content-status.md`: stale "feat effects uniformly ⚪" note · 🟢 P3 · FIXED (v2.1032.0)
**Source:** `docs/plans/class-content-status.md` (the "Feat plans" section). An older line stated mechanical feat effects were uniformly ⚪ unstarted. **Fixed:** the line now records the six Reactions-framework-wired feats (Lucky, Defensive Duelist, War Caster, Mage Slayer ✅; Sentinel, Polearm Master 🟢) and scopes the ⚪ to what actually remains. Verified against `tabletop_routes.py` — each wired feat has a `sheet["feats"]` slug/name scan. Also corrected the Grappler bullet: the feat is genuinely unwired (the many `grappler` hits in routes are the *grappled condition*, not the feat), and its "deferred until (B) lands" gate is stale since (B) is 🟢 PARTIAL.

### B13 — `class-content-status.md`: stale "recipient die consume pending" note · 🟢 P3 · FIXED (v2.1032.0)
**Source:** `docs/plans/class-content-status.md` (cross-cutting C). Bardic Inspiration recipient side shipped (v2.97.56–.57, `/apply_bardic_inspiration_die` + banner). **Fixed:** the cross-cutting C bullet now strikes the pending claim and records the shipped endpoint + banner, the deliberate RAW divergence (post-roll declaration is spell-legal), and the one real remaining tail (60-ft recipient range check).

### B14 — `class-content-status.md`: historical template/endpoint-URL silent test-skip · 🟢 P3 · FIXED (v2.1032.0 — was already resolved)
**Source:** `docs/plans/class-content-status.md:357`. **Verified not a live bug.** The cited line is a *historical record* inside a version-note block — it documents that v2.99.192 reactivated the v2.99.180 NPC WIS save test which had been silently skipping on a wrong template endpoint URL, i.e. the fix already shipped. Confirmed by running `tests/harness/test_polymorph_npc_wis_save.py` — 1 passed, no skip. No doc edit needed; the line correctly describes past work.

---

## Borderline (almost certainly resolved — verify before closing)

- **M1 — CON max-HP recompute path.** Believed fully resolved by the permanent-ability-increase reconciliation (v2.312.0–v2.314.0). Verify no stale dual-path remains, then delete this line.
- **M4 — Demo audio never shipped.** Some demo audio cues (`tavern.ogg` / `battle.ogg`) were planned but not seeded. (The token/map half is **resolved** — every leveled demo plus the Sundered Vault ships full token + battle-map art, including the `tavern.png` map.) Cosmetic; low priority. (Tracked here, not in TODO, because it's "incomplete demo content," not a feature request.)

> **Not bugs (feature gaps tracked in [TODO.md](TODO.md)):** remaining unbuilt automation is *feature work*, not defects — per the [SRD audit (v2.553.0 refresh)](TODO.md#srd-5e-audit-v25530-refresh) the ruleset is functionally complete (~98–99% automated · 100% supported); what's left is the deliberately GM-narrated spatial/scrying/object remainder + out-of-SRD-scope content (future 3.x). (The figures this note used to cite — 116/239 magic items, ~110 unscaled spells, 24 ⚪ class-feature rows — all closed between v2.344.x and v2.599.13.)
