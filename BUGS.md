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

### B6 — Sorcerer Quickened Spell is announce-only · 🟡 P2 · FIXED (v2.1032.1 — was stale, shipped v2.649.0)
**Source:** `docs/plans/sorcery-points-and-metamagic.md`. **Both halves of this entry were stale audit text, not open work.** Verified against the code:
- **Quickened Spell — mechanized v2.649.0.** `POST /use_metamagic_quickened_spell` spends 2 SP and installs `metamagic-quickened-pending`; `/cast_spell` reads it via `_caster_has_quickened_pending` (`tabletop_routes.py:~25362`) and **does** perform the action-economy override the bug says is missing — `slot_for_economy` is retargeted `"action"` → `"bonus"`, the one-use buff is consumed, and a `feature_used` card broadcasts. Built on the v2.643.0–v2.648.8 economy-slot-retarget plumbing (`as_reaction` / `as_war_magic_bonus`). Harness `test_use_metamagic_quickened.py` — 3 tests, green.
- **AoE multi-target Empowered loop — shipped v2.661.0** (`_aoe_empowered_log` / `_place_empowered_fired` on the `/place_aoe` path, first-target-wins once per cast).

All 8 PHB metamagics are fully shipped end-to-end. The plan doc's own status line has said so since v2.158.68; this tracker entry simply never caught up.

**The genuine remainder this entry was masking** is narrower and is now filed as B15 below: the PHB p.202 bonus-action-spell pairing rule (the plan's Phase 2 `over_quickened_limit` 409), which is unimplemented.

### B15 — PHB p.202 bonus-action spell pairing rule unenforced · 🟡 P2 · OPEN
**Source:** `docs/plans/sorcery-points-and-metamagic.md` Phase 2 (filed v2.1032.1, split out of the stale B6). RAW: a caster who casts a spell as a **bonus action** can't cast another spell that turn except a cantrip with a 1-action casting time. Quickened Spell makes this reachable — a Sorcerer can Quicken a leveled spell into the bonus slot and then cast a second leveled spell with their action, which SimpleVTT currently allows. The plan spec'd a 409 `over_quickened_limit` for this; `grep` finds no such path in `tabletop_routes.py`. Needs per-turn state recording *that a leveled spell took a given economy slot* (today's `economy` dict records only that a slot is burnt, not what burnt it), then a gate in `/cast_spell`. GM-adjudicable meanwhile.

### B10 — Fighter Indomitable shipped RAW-bent (advantage, not reroll-on-failure) · 🟢 P3 · WONTFIX (v1)
**Source:** was `TODO.md` › Class Features (v2.56.0 "Iron Will"). RAW Indomitable lets you **reroll** a failed save; the v1 implementation grants **advantage on the next save** instead, because the true post-roll reroll needs an undo-and-reapply path for already-installed conditions (its own substantial commit). Accepted divergence for v1; filed for a future precise implementation.

### B3 — Roll-log card collapses when the GM rolls on behalf of a player · 🟢 P3 · NEEDS-VERIFY
**Source:** `TODONE.md` (likely fixed v2.99.71). The roll-log card reportedly collapsed/mis-rendered when a GM rolled for a player. Believed fixed in v2.99.71 but never browser-confirmed. Needs a manual click-through to close or reopen.

---

## Stale-doc bugs

### B5 — `automation-coverage.md` row counts pinned at v2.99.460 · 🟢 P3 · FIXED (v2.1031.2)
**Source:** `docs/automation-coverage.md` + `docs/plans/full-feature-automation.md`. **Fixed:** classifier rerun, counts refreshed 289/35/8 → **306/31/9** (total 332 → 346). The rerun also exposed and fixed a real **classifier blind spot** — `_MUTATORS` in `scripts/classify_feature_endpoints.py` listed `_install_buff` but not `_install_buff_on_combatant_id`, so every endpoint buffing a *target* combatant rather than the caster was mis-tagged announce-only; adding it (plus `_grant_movement`) flipped `fancy_footwork` + `orders_wrath` to tracked. That accounts for two of the six rows the v2.665.0 drift note had hand-flagged. **Partly-open nuance recorded in the doc, not re-filed as a bug:** the last two flagged rows (`unwavering_mark`, `scornful_rebuke`) are *correctly* tagged — the classifier scores **endpoints**, and those endpoints are announce-only by design while the feature is mechanized in the `/attack` on-hit path. A ⚪ endpoint tag therefore doesn't imply an unautomated feature; the doc now says so explicitly so the distinction isn't re-discovered as "drift" a third time.

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
