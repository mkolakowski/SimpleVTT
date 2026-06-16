# SimpleVTT — Planned Features

Backlog of features to implement.

> Completed items live in [`TODONE.md`](TODONE.md). When an item ships, move it there (preserving the version reference) rather than leaving a strikethrough or ✅ stub here.

**Priority legend (Manually Added section only; other sections are time-ordered by header):**

| Tag | Meaning |
|-----|---------|
| `🔥 IN PROGRESS` | Actively being shipped (a plan doc + ongoing commits exist). |
| `🔴 P1` | High priority — bugs, regressions, top-of-the-list features the user has explicitly asked for. |
| `🟡 P2` | Medium priority — substantial features that are planned but not blocking anyone. |
| `🟢 P3` | Low priority — polish / cosmetic / nice-to-have UX tweaks. |

When the assistant offers a single-option "what's next?" via `AskUserQuestion` after a commit, the **top-priority** item (highest P-level, or the IN PROGRESS phase) should be the **(Recommended)** option per the rule in [`CLAUDE.md`](CLAUDE.md#offer-whats-next-as-multiple-choice-questions).

**Quick map of where to look:**

- **SRD 5e (CC BY 4.0) audit findings** → see [SRD 5e Audit (v2.344.1 refresh)](#srd-5e-audit-v23441-refresh) for the current per-category coverage table and re-prioritisation (magic-item content tail **closed**), then [SRD 5e Audit (v2.315.0 refresh)](#srd-5e-audit-v23150-refresh) for the prior pass, then [SRD 5e Audit (2026-06-14 refresh)](#srd-5e-audit-2026-06-14-refresh), [SRD 5e Audit (2026-06-13 refresh)](#srd-5e-audit-2026-06-13-refresh), [SRD 5e Audit (2026-06-11 refresh)](#srd-5e-audit-2026-06-11-refresh) and [SRD 5e Audit (2026-06-10)](#srd-5e-audit-2026-06-10) for the prior passes. The v2.315.0 refresh **corrects two denominators** that all prior passes got wrong: magic items are **123 / 239 wired (~51%)** — the old "292" figure counted total equipment (239 magic + 37 mundane weapons + 18 mundane armor), so the percentage was understated; and class features are **222 per-row entries (~81%)**, not the stale "133". Overall SRD automation is **~75%**.
- **Active class-feature automation backlog** → see [Full Class-Feature Automation — remaining backlog](#full-class-feature-automation--remaining-backlog) (just Phase 8 + a few per-feature Phase-2 finishers remain after v2.149.1).
- **Design plans with deferred phases** → see [Design Plans Backlog](#design-plans-backlog) (every `docs/plans/*.md` indexed with a priority tag).
- **One-off bugs + UI polish that don't have a design plan** → see [Manually Added](#manually-added).
- **Big feature buckets that aren't tracked by a plan** → see the topic sections below (Character Sheet, GM Tools, Combat, Maps, Media, Player Features, UI/Mobile, Rules Reference, Legal & Compliance, Test Infrastructure, Integrations, Visual, Class Features (next cycle)). The priority legend doesn't apply to these — they're topic-grouped, not P-tagged.

---

## SRD 5e Audit (v2.344.1 refresh)

**Audit scope.** Recomputed directly from the content JSON (`app/data/local/dnd5e/items/`, 294 equipment files) + the three magic-item registry dicts in `app/routes/tabletop_routes.py` as of v2.344.1, after the v2.316.0→v2.344.0 magic-item content sprint (Sword of Life Stealing through "The Armory's Remainder"). This pass records that **the magic-item content tail is now closed**. A follow-up correction in **v2.344.2** found the spell upcast dice/heal scaling is *also* effectively complete (the prose parser covers it — see the Spells row). A further reconciliation in **v2.344.3** found the **class-feature ⚪ tail was likewise stale** — 22 of 24 rows were already shipped (v2.99.197–.221) and just never flipped. After all three corrections the SRD ruleset is **~88% automated**, and the single remaining genuine gap is **Aura of Courage** (Paladin Lv 10/18).

### Per-category coverage (the headline numbers)

| Category | SRD count | Automated | Notes |
|---|---|---|---|
| Races | 9 | **~90%** | Unchanged from v2.315.0. |
| Monsters | 322 | **~85%** | Unchanged. |
| Conditions | 15 | **~85%** | Unchanged. |
| Class features | **222 rows** | **~99%** | **Reconciliation correction (v2.344.3):** the prior ~81% / "24 ⚪ rows" was stale doc-status, not missing code. 22 of those 24 rows were already shipped end-to-end (v2.99.197–.221, each with a dedicated harness test) but never flipped from ⚪ in [`class-content-status.md`](plans/class-content-status.md). All flipped to ✅ (Deflect Missiles → 🟢). **The lone genuine ⚪ is Aura of Courage** (Paladin Lv 10/18) — no code/test. |

| Spells | 319 | **~72%** | **Upcast scaling correction (v2.344.2):** the prior "~110 lack upcast scaling" figure counted spells lacking the *structured field*, not spells lacking *scaling* — the v2.125.0 prose parser derives per-slot dice from `higher_level` at cast time. Of 73 leveled spells with a modeled base, **39 dice-scale automatically** (32 structured + 7 parser); the other 34 carry no per-slot dice clause because RAW they don't dice-scale (Finger of Death, Meteor Swarm, Sunburst) or scale by count/duration/area handled elsewhere. **Dice/heal upcast scaling is effectively complete.** The remaining spell gap is area-effect automation + cast-and-broadcast utility spells, not upcast. |
| Magic items | **235 / 239 wired** | **~98%** | **Up from 123/239 (~51%) at v2.315.0.** The v2.316–v2.344 content sprint wired the entire tail. The only 4 unwired are the generic/meta slugs (`potion-of-healing`, `spell-scroll`, `weapon-1-2-or-3`, `wand-of-the-war-mage-1-2-or-3`) — intentionally **not** discrete collectibles. Effectively **100% of discrete SRD magic items** are now wired. |

**Overall ~88%** automated across the SRD ruleset (up from ~75% at v2.315.0 — the magic-item jump from ~51% → ~98% and the class-feature correction from ~81% → ~99% are the movers).

### How the count was computed

294 equipment files = 239 magic items + 37 mundane weapons + 18 mundane armor (the mundane rows need no magic wiring). Distinct wired slugs across `_MAGIC_ITEM_PASSIVES` (176) + `_MAGIC_ITEM_ACTIONS` (51) + `_MAGIC_ITEM_ATTACK_RIDERS` (17) = 241, of which 235 map onto SRD item files. 239 − 235 = 4 unwired, all generic/meta. Most are catalog-stub passives (mechanics GM-narrated in v1); ~70 have full mechanical handlers (on-hit riders, charge-with-spell, nat-20 hooks, ability-overrides, action dispatchers).

### Remaining gaps (priority order — toward full SRD automation)

The engine substrate is complete; everything below is content/scaling-data, not engine code.

1. 🔴 **P1 — Aura of Courage (Paladin Lv 10/18).** The single remaining genuine ⚪ class feature after the v2.344.3 reconciliation. RAW: the paladin + friendly creatures within 10 ft (30 ft at Lv 18) can't be frightened while the paladin is conscious. Build it on the `_aura_of_protection_bonus` init-walk pattern as a frightened-immunity aura + a `feature_used(source=aura-of-courage)` broadcast. One real code commit + harness test.
2. 🟡 **P2 — Spell area-effect + utility automation.** With dice/heal upcast scaling complete (below), the remaining spell lever is automating area-of-effect targeting and the cast-and-broadcast-only utility spells.
3. 🟢 **P3 — Class-feature test-hygiene + bespoke upcast refactor.** (a) ✅ **Capstone seed-drift fixed v2.368.1** — `test_persistent_rage` long-rests Krieger first; `test_select_spell_mastery` + `test_select_signature_spells` level-gate tests PATCH Thalindra to seed Lv 7 first. (b) Migrate Sleep / Hold Person / Hold Monster off per-endpoint constants onto a shared structured `upcast` param field. See [`spell-upcasting.md`](plans/spell-upcasting.md).
4. ✅ **DONE — Class-feature ⚪ tail.** Reconciled v2.344.3 — 22 of 24 "⚪" rows were already shipped (v2.99.197–.221); flipped to ✅ in [`class-content-status.md`](plans/class-content-status.md). Only Aura of Courage remains (now P1 above).
5. ✅ **DONE — Spell upcast dice/heal scaling.** Effectively complete via structured fields + the v2.125.0 prose parser (39/73 modeled-base leveled spells dice-scale; the rest are RAW non-scalers or count/duration scalers). Corrected v2.344.2 — see the Spells row above.
6. ✅ **DONE — Magic-item content tail.** Closed across v2.316.0–v2.344.0. Only the 4 generic/meta slugs remain, which are intentionally out of scope.

### Out-of-scope (unchanged)

Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte stay future-3.x scope.

---

## SRD 5e Audit (v2.315.0 refresh)

**Audit scope.** Fifth pass against `app/data/local/dnd5e/`, recomputed directly from the content JSON + the three magic-item registry dicts in `app/routes/tabletop_routes.py` as of v2.315.0. This pass exists to answer one question — *what percentage of the SRD does SimpleVTT mechanically automate, per category* — and to **correct two denominators** that every prior audit carried forward incorrectly. Excludes setting-specific / post-SRD content (Tasha's, Xanathar's-beyond-SRD, Strixhaven) and homebrew, same as prior passes.

### Per-category coverage (the headline numbers)

| Category | SRD count | Automated | Notes |
|---|---|---|---|
| Races | 9 | **~90%** | Racial passives + speed + darkvision derived; a few flavor traits GM-narrated. |
| Monsters | 322 | **~85%** | Stat blocks + attacks + legendary/lair actions + legendary resistance all engine-driven. |
| Conditions | 15 | **~85%** | Mechanical conditions enforce; exhaustion ladder shipped. |
| Class features | **222 rows** (179 ✅ / 19 🟡 / 24 ⚪) | **~81%** | Denominator corrected from the stale "133". Tail is Barbarian Lv 9–20, Monk capstones, Ranger Lv 10–20, Rogue Reliable Talent / Stroke of Luck. |
| Spells | 319 | **~70%** | Catalog 319/319; 116 have save dispatch, 76 damage, 27 area, 29 upcast scaling. ~110 cast-and-broadcast-only spells still lack upcast scaling. |
| Magic items | **123 / 239 wired** | **~51%** | Denominator corrected: 294 equipment rows = 239 magic + 37 mundane weapons + 18 mundane armor. Wiring across `_MAGIC_ITEM_ACTIONS` (47) + `_MAGIC_ITEM_PASSIVES` (71) + `_MAGIC_ITEM_ATTACK_RIDERS` (8); 123 distinct slugs (3 span two layers). |

**Overall ~75%** automated across the SRD ruleset.

### Denominator corrections (why the numbers moved up)

- **Magic items: 292 → 239 denominator.** Prior passes divided the wired count by 292, which was the *total equipment* row count (it bundled 37 mundane weapons and 18 mundane armor that are not "magic items" and need no passive wiring). The honest denominator is the 239 magic-item rows. With 123 distinct slugs wired, coverage is **~51%**, not the ~34% the v2.314-era TODO reported.
- **Class features: 133 → 222 denominator.** The "133" was a stale count from an early class-content snapshot. The living inventory in [`class-content-status.md`](docs/plans/class-content-status.md) now enumerates **222 per-row entries** (179 ✅ shipped / 19 🟡 partial / 24 ⚪ unstarted) = **~81%**.

### Remaining gaps (priority order — toward full SRD automation)

The engine substrate (actions / passives / attack-riders / ability-override / buff / save-dispatch / upcast) is complete. Every remaining item below is **content drop-in or scaling-data**, not new engine code.

1. 🔴 **P1 — Magic-item content tail (116 items).** The single biggest lever on the overall %. 116 of 239 SRD magic items remain GM-narrated. Each fits an existing template (on-hit rider, charge-with-spell, passive buff, nat-20 hook, ability-override, boolean derived flag). Ship in ~10–15-item batches, each its own MINOR commit + 3 harness tests.
2. 🟡 **P2 — Spell upcast scaling (~110 spells).** Add `damage_per_slot` / scaling data to the cast-and-broadcast-only spells so higher-slot casts scale automatically. Moves Spells from ~70% → ~90%+.
3. 🟢 **P3 — Class-feature ⚪ tail (24 rows).** Barbarian Lv 9–20, Monk Deflect Missiles / Diamond Soul / Empty Body / Perfect Self, Ranger Lv 10–20 (minus Vanish), Rogue Reliable Talent / Slippery Mind / Elusive / Stroke of Luck.

### Out-of-scope (unchanged)

Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte stay future-3.x scope.

---

## SRD 5e Audit (2026-06-14 refresh)

**Audit scope.** Fourth pass against `app/data/local/dnd5e/`, capturing the window from v2.222.0 → v2.284.0. The defining event is the **charged-items plan closing all phases (0–5)** — the magic-item wiring count was re-counted directly by AST-parsing the three registry dicts in `app/routes/tabletop_routes.py`. The tail of the window (v2.280.0–v2.284.0) closed the **SRD movement/levitation item family** on the passive substrate. Excludes setting-specific / post-SRD content (Tasha's, Xanathar's-beyond-SRD, Strixhaven) and homebrew, same as prior passes.

### Headline state (delta vs 2026-06-13)

| Layer | SRD count | 2026-06-13 | 2026-06-14 | % | Movement |
|---|---|---|---|---|---|
| Magic items | 292 | ~49 wired | **100 distinct wired** | **~34%** | **47 `_MAGIC_ITEM_ACTIONS` + 48 `_MAGIC_ITEM_PASSIVES` + 8 `_MAGIC_ITEM_ATTACK_RIDERS`** (3 slugs span two layers). Charged-items plan ✅ closed all phases; the v2.280.0–v2.284.0 tail closed the movement/levitation family — Helm of Brilliance (fire resistance), Wings of Flying, Broom of Flying, Carpet of Flying (all on the `flying_speed` flag), and Boots of Levitation (NEW `levitate_at_will` flag). |
| Spells | 319 | ~70% | ~70% | ~70% | No movement this window. Catalog 319/319; ~18 validation suites CI-gated. |
| Monsters | 322 | ~85% | ~85% | ~85% | No movement. Legendary actions / resistance / lair actions all ✅. |
| Conditions | 15 | ~85% | ~85% | ~85% | No movement. |
| Class features | 133 | ~82% | ~82% | ~82% | No movement this window. |
| Races | 9 | ~90% | ~90% | ~90% | No movement. |
| Ability-score override engine | — | ✅ shipped | ✅ shipped | — | Stable. |

### What closed since 2026-06-13

✅ **Charged-items plan — all phases (0–5)** ([plan ✅](docs/plans/charged-items.md)) — every named item on the plan shipped on the mature charge engine (`_MAGIC_ITEM_ACTIONS` + `/use_item_action` + per-slug dispatch + the generalized `action_kind: "buff"` substrate). Final commits: Staff of Power (v2.274.0), Wand of Wonder (v2.273.0), Staff of Thunder & Lightning, Wand of the War Mage +3 (v2.276.0, completing the +1/+2/+3 tier set), Wand of Enemy Detection (v2.277.0). Zero new engine code required for the last items — pure content drop-ins.

✅ **SRD movement/levitation item family** (v2.280.0–v2.284.0) — closed the passive-flag movement items on the shipped `flying_speed` substrate (v2.238.0 Winged Boots) plus one new flag. Helm of Brilliance (fire resistance via the resistance substrate, v2.280.0); Wings of Flying (attunement), Broom of Flying (no attunement), Carpet of Flying (no attunement) — all on `flying_speed` with zero new engine code (v2.281.0–v2.283.0); Boots of Levitation (v2.284.0) landed the **NEW `levitate_at_will` boolean derived flag** (init / walker boolean-OR / `/sheet-json` projection), the reusable surface for future "cast X at will" items. Each shipped as inert spare loot on a thematically-fit demo PC + 3 harness tests.

### Remaining gaps (re-prioritized)

The substrate (actions / passives / attack-riders / ability-override / buff) is complete. All remaining magic-item work is content drop-ins with no new engine code.

🟡 **P2 — Magic-item action backfill long tail.** ~197 of 292 SRD items still have no code-side wiring (down from ~245). Most are weightless/flavor or one-off mechanics. Pick the next ~10–15-item batch that fits an existing template (on-hit riders, charge-with-spell, passive buff, nat-20 hook, ability-override).

🟡 **P2 — Ability-score engine drop-in tail (small).** Still trivially absorbed: giant-tier Belts (Stone/Frost STR 23, Fire 25, Cloud 27, Storm 29) and the Ioun Stone ability variants. Each ~1 commit on the shipped engine.

🟡 **P2 — Spell-validation suite finishers.** Upcast scaling on the ~110 cast-and-broadcast-only spells.

🟡 **P2 — Wizard capstone Spell Mastery / Signature Spells, Aura of Courage, Reactions v3 pending-damage state machine, Sorcerer Quickened Spell.** Unchanged.

🟢 **P3 — Eldritch Knight Phase 2 read sites; class-feature ⚪ tail** (Barbarian Lv 9–20, Monk Deflect Missiles / Diamond Soul / Empty Body / Perfect Self, Ranger Lv 10–20 minus Vanish, Rogue Reliable Talent / Slippery Mind / Elusive / Stroke of Luck). Unchanged.

### Out-of-scope (unchanged)

Same as prior passes: Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte stay future-3.x scope.

---

## SRD 5e Audit (2026-06-13 refresh)

**Audit scope.** Third pass against `app/data/local/dnd5e/` capturing the delta over ~63 MINOR/PATCH releases between v2.159.30 → v2.222.0 (the largest single window so far). Re-shapes the [Design Plans Backlog](#design-plans-backlog) priorities. Excludes setting-specific / post-SRD content (Tasha's, Xanathar's-beyond-SRD, Strixhaven, etc.) and homebrew, same as the prior passes.

### Headline state (delta vs 2026-06-11)

| Layer | 2026-06-11 coverage | 2026-06-13 coverage | Movement |
|---|---|---|---|
| Spells (319 SRD) | ~66% mechanical | ~70% mechanical | Spell-validation suite went from 1 catalog test (Fire Bolt) to **~18 catalog suites** (loader, smoke, damage, exact-damage, save, save-damage, attack, heal, conditions, concentration, range, aoe, aoe-placement, autohit, multibeam, buff-install, buff-effects, upcast) — CI-gated catalog drift is now broad. |
| Monsters (322 SRD) | ~75% mechanical | ~85% mechanical | **Legendary actions, legendary resistance, AND lair actions all ✅** — the 2026-06-11 audit's NEW #1 P1 surface, closed end-to-end v2.159.32–v2.167.0. |
| Conditions (15/15) | ~85% | ~85% | No movement. |
| Items (292 SRD) | ~50% framework + 42 wired | framework ✅ + **~49 items wired in code** (35 `_MAGIC_ITEM_ACTIONS` + 10 `_MAGIC_ITEM_PASSIVES` + 6 `_MAGIC_ITEM_ATTACK_RIDERS`) | Content tail still the long pole, but the **NEW ability-score override engine** (below) added a whole item class. |
| Ability-score override engine (NEW) | not audited | ✅ shipped | RAW `max(base, set)` runtime engine + 6 drop-ins: Belt of Giant Strength (Hill), Amulet of Health, Headband of Intellect, Gauntlets of Ogre Power, Potion of Giant Strength (tiered), Manuals & Tomes (permanent +2). v2.211.0–v2.222.0. |
| Class features (133) | ~82% | ~82% | No movement this window. |

### What closed since 2026-06-11

✅ **Legendary actions + legendary resistance + lair actions** ([plan ⚪→✅](docs/plans/legendary-actions.md)) — the prior audit's NEW #1 P1, shipped v2.159.32–v2.167.0: per-round action-point budget, `/use_legendary_action` dispatch (attack + AoE-save shapes + chat card), a 3/day legendary-resistance pool with deferred failed-save interception (`/spend_legendary_resistance` + `/decline_legendary_resistance` + GM prompt banner), and curated `lair_actions` data + `/trigger_lair_action` (initiative-20 trigger, AoE dispatch, GM banner). The single biggest un-planned SRD surface from the prior audit is now closed.

✅ **Ability-score override engine + 6 drop-in items** ([plan ⚪→✅](docs/plans/str-override.md)) — a surface that wasn't on any prior audit. RAW `max(base, set)` runtime semantics via `effective_ability_score`, routed through every read site (saves, checks, sheet card, carry capacity, `/sheet-json`). Drop-ins: Belt of Giant Strength (Hill, STR 21), Amulet of Health (CON 19, with boosted-max-HP threading into combat + all rest/heal paths), Headband of Intellect (INT 19), Gauntlets of Ogre Power (STR 19), Potion of Giant Strength (tiered timed buff), and the six Manuals & Tomes (DMG pp.180/208) as a permanent base-score `permanent_boost` archetype. v2.211.0–v2.222.0.

✅ **Spell-validation suite — most of it** ([plan 🟠](docs/plans/spell-validation-suite.md)) — the 2026-06-11 audit's carry-over P1. From a single Fire Bolt slice to ~18 catalog suites covering loader/damage/save/attack/heal/conditions/concentration/range/aoe/upcast and more. The CI-gated drift net the prior audits kept asking for is now largely in place.

✅ **Magic-item action backfill — continued** (Phase 9 of [magic-items-automation](docs/plans/magic-items-automation.md)) — ~49 items now wired in code (vs 42). New since the prior audit: Potion of Heroism / Resistance / Mind Reading / Diminution, Wand of Lightning Bolts / Paralysis, Eyes of Charming, Stone of Good Luck, Staff of Fire, plus the ability-score passives above.

### Remaining gaps (re-prioritized)

With magic-item framework, legendary/lair actions, and the ability-score engine all closed, there is **no single headline P1 surface left** — the remaining work is breadth (content tails) and a handful of mid-size class/spell features.

🟡 **P2 — Magic-item action backfill long tail.** ~245 of 294 SRD items still have no code-side wiring. The framework + templates are all in place; each remaining item is a content commit. Bag of Devouring is shipped; pick the next ~10–15-item batch from the Phase 1–8 templates (on-hit riders, charge-with-spell, passive buff, nat-20 hook).

🟡 **P2 — Ability-score engine drop-in tail (NEW, small).** The override substrate now trivially absorbs: the **giant-tier Belts** (Stone/Frost STR 23, Fire 25, Cloud 27, Storm 29 — one passive row + demo seed each) and the **Ioun Stone ability variants** (Strength/Dexterity/Constitution/Intelligence/Wisdom/Charisma — +2-to-max-20 equipped boost). Each is a ~1-commit slice on the shipped engine.

🟡 **P2 — Spell-validation suite finishers.** The catalog suites are broad now; remaining work is closing the specific cast paths still flagged partial (upcast scaling on the ~110 cast-and-broadcast-only spells).

🟡 **P2 — Wizard capstone Spell Mastery / Signature Spells, Aura of Courage, Reactions v3 pending-damage state machine, Sorcerer Quickened Spell.** Unchanged from 2026-06-11.

🟢 **P3 — Eldritch Knight Phase 2 read sites; class-feature ⚪ tail** (Barbarian Lv 9–20, Monk Deflect Missiles / Diamond Soul / Empty Body / Perfect Self, Ranger Lv 10–20 minus Vanish, Rogue Reliable Talent / Slippery Mind / Elusive / Stroke of Luck). Unchanged.

### Removed from gap list (since shipped)

- ~~Legendary actions + lair actions~~ — closed (the prior audit's NEW #1 P1).
- ~~Legendary resistance~~ — closed.
- ~~Spell-validation suite Phase 1+~~ — mostly closed (broad catalog coverage; only cast-path finishers remain).

### Out-of-scope (unchanged)

Same as the prior passes: Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte stay future-3.x scope. Out-of-scope-by-design RAW-narrative features unchanged.

---

## SRD 5e Audit (2026-06-11 refresh)

**Audit scope.** Follow-up pass against `app/data/local/dnd5e/` after the [2026-06-10 audit](#srd-5e-audit-2026-06-10). Captures the delta over ~60 commits between v2.158.69 → v2.159.30 and re-shapes the [Design Plans Backlog](#design-plans-backlog) priorities. Excludes setting-specific / post-SRD content (Tasha's, Xanathar's-beyond-SRD, Strixhaven, etc.) and homebrew, same as the prior pass.

### Headline state (delta vs 2026-06-10)

| Layer | 2026-06-10 coverage | 2026-06-11 coverage | Movement |
|---|---|---|---|
| Spells (319 SRD) | ~66% mechanical | ~66% mechanical | No movement (spell-validation suite Phase 1+ still pending). |
| Monsters (322 SRD) | ~75% mechanical | ~75% mechanical | Legendary actions still ⚪ (15 monsters carry data; engine has no dispatch). **NEW P1 surface this audit.** |
| Conditions (15/15) | ~70% (Exhaustion single-flag) | ~85% (Exhaustion ✅ 6-level) | Exhaustion levels closed v2.159.17–.22. |
| Items (292 SRD) | <25% (every `actions: []`) | ~50%+ (framework ✅ + 42 of 292 items wired) | Phases 1–8 ✅ v2.158.74–v2.159.25. Content tail (~250 items) now P2. |
| Class features (133) | ~80% | ~82% | Berserker Frenzy + non-Devotion Lv 15/20 + Battle Master 16/16 + Pact Boon all ✅. |
| Carrying capacity (NEW) | not audited | ✅ shipped | RAW STR × 15 engine + Bag of Holding ✅ v2.159.26–.30. |

### What closed since 2026-06-10

✅ **Magic-items-automation Phases 1–8** ([plan ⚪→✅](docs/plans/magic-items-automation.md)) — shipped end-to-end across v2.158.74 → v2.159.25 (32 PATCH commits) + v2.159.0 MINOR milestone. Framework closed: passives → attunement → actions → on-hit riders → AoE shapes → ammunition. The content tail (~250 of 292 items still have `actions: []`) is the new P2 below.

✅ **Exhaustion-levels Phases 1–4** ([plan ⚪→✅](docs/plans/exhaustion-levels.md)) — shipped v2.159.17 → v2.159.22: `set_exhaustion` endpoint, 6-level integer field, disadvantage wiring (Lv 1/3), speed wiring (Lv 2/5), HP-max halving (Lv 4), Berserker Frenzy rage-end hook, JS-side speed mirror.

✅ **Carrying-capacity Phases 0–3** ([plan ⚪→✅](docs/plans/carrying-capacity.md)) — not surfaced in the 2026-06-10 audit; surfaced + shipped during the magic-items wave. STR × 15 capacity engine, `/sheet-json` exposure, 12-PC weight backfill, carry meter UI, Bag of Holding.

✅ **Battle Master 16/16 maneuvers** ([plan 🟠→✅](docs/plans/battle-master.md)) — 2026-06-10 audit kept this in P2 but 16/16 maneuvers had actually shipped at v2.99.266 (v-numbers pre-dated the audit; header missed). Refreshed in this audit.

✅ **Warlock Pact Boon** ([plan ⚪→✅](docs/plans/warlock-pact-boon.md)) — same story. Tome v2.99.200 + Blade v2.99.212 + Chain v2.99.213 all shipped pre-audit; header missed. Refreshed.

✅ **Non-Devotion Paladin Lv 15/20 capstones** ([plan refresh](docs/plans/paladin-oaths.md)) — 2026-06-10 audit kept these as P3 outstanding; actually shipped v2.99.283 → v2.99.292 (Undying Sentinel, Soul of Vengeance, Scornful Rebuke, Glorious Defense, Protective Spirit, Elder Champion, Avenging Angel, Invincible Conqueror, Living Legend, Emissary of Redemption — 10 capstones in one batch). Header refreshed. Outstanding scope shrinks to Conquest Lv 3/7 + Redemption Lv 3 + Glory Lv 3 + Vengeance Phase 2 OA-flow.

### NEW headline gap (RAW-implementable, no system blocker)

🔴 **P1 — Legendary actions + lair actions (NEW — no plan doc today).** 15 SRD monsters carry `legendary_actions` data arrays (ancient red/silver/gold/bronze/copper/green/white dragons, lich, vampire, tarrasque, kraken, mummy lord, solar, androsphinx, unicorn) but the engine has no `/use_legendary_action` dispatch, no legendary-resistance pool (RAW: 3/day auto-pass on a failed save), and no per-round legendary-action point budget (RAW: 3 action points / round, refresh at end of each non-legendary turn). Zero monsters carry `lair_actions` data despite RAW SRD specifying them on the same roster (initiative count 20 trigger; thematic environmental effect each round in lair). Today a GM running an ancient dragon adjudicates these by hand. **Suggested approach:** write `docs/plans/legendary-actions.md`; first slice plumbs the action-point budget + a `/use_legendary_action` dispatch reusing the `/npc_attack` pipeline for the attack-shape actions (Tail / Wing / Claw); defer save-shape actions (Frightful Presence, Detect) until on-monster reactions land. Lair actions ship as a separate Phase 2 once the data layer carries them. This is the single biggest un-planned SRD surface left, now that magic items + exhaustion are closed.

### Carry-over P1/P2/P3 (unchanged from 2026-06-10)

🔴 **P1 — Spell-validation suite Phase 1+** ([`docs/plans/spell-validation-suite.md`](docs/plans/spell-validation-suite.md)). 4 spell-specific harness tests for 319 spells (`test_spell_catalog_damage`, `test_spell_catalog_loader`, `test_spell_condition_catalog_confusion_banishment`, `test_spell_upcast_parser`). CI-gated catalog drift remains the cheapest way to lock spell mechanics. No movement since 2026-06-10.

🟡 **P2 — Magic-item action backfill (NEW — Phase 9 of magic-items-automation).** 250 of 292 SRD items still carry `actions: []`. The framework is in place; each remaining item is a content commit picking from the existing Phase 1–8 templates (Potion of Heroism → passive buff; Potion of Healing → spell-effect dispatch; Wand of Polymorph / Lightning Bolts → charges-with-spell; Frost Brand / Flame Tongue → on-hit rider; Vorpal Sword / Hammer of Thunderbolts → nat-20 hook). Estimate: ~10–15 items per commit; ~20 commits to close the long tail. Bag of Devouring (paired counterpart to Bag of Holding) is the natural first slice.

🟡 **P2 — Wizard capstone Spell Mastery / Signature Spells (Lv 18/20).** Unchanged.

🟡 **P2 — Aura of Courage (Paladin Lv 10/18).** Unchanged.

🟡 **P2 — Reactions v3 pending-damage state machine** ([`docs/plans/reactions-automation.md`](docs/plans/reactions-automation.md) v3 backlog). Unchanged.

🟡 **P2 — Sorcerer Quickened Spell.** Unchanged.

🟢 **P3 — Eldritch Knight Phase 2 read sites** ([`docs/plans/eldritch-knight.md`](docs/plans/eldritch-knight.md)). Unchanged.

🟢 **P3 — Class-feature ⚪ tail.** Unchanged (Barbarian Lv 9–20, Monk Deflect Missiles / Diamond Soul / Empty Body / Perfect Self, Ranger Lv 10–20 minus Vanish, Rogue Reliable Talent / Slippery Mind / Elusive / Stroke of Luck).

### Removed from gap list (since shipped)

- ~~Magic-items-automation~~ — closed (framework; content tail moved to P2).
- ~~Exhaustion-level tracking~~ — closed.
- ~~Pact Boon~~ — closed.
- ~~Battle Master 15 maneuvers~~ — closed.
- ~~Non-Devotion Paladin Lv 15/20 capstones~~ — closed (10 of 11 capstones shipped; Conquest Lv 3/7 + Redemption Lv 3 + Glory Lv 3 + Vengeance Phase 2 remain as small follow-ups under the paladin-oaths plan).

### Out-of-scope (unchanged)

Same as the 2026-06-10 audit: Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats (Tough, Resilient, etc.), backgrounds beyond Acolyte stay future-3.x scope. Out-of-scope-by-design RAW-narrative features (Beast Speech, Mask of Many Faces, Druid Land's Stride, Monk Slow Fall, Cleric/Paladin Divine Health) also unchanged.

---

## SRD 5e Audit (2026-06-10)

**Audit scope.** Walk every piece of SRD 5.1 (CC BY 4.0 — the "free" 5e release from Wizards of the Coast) content shipped under `app/data/local/dnd5e/` and confirm whether the mechanical wiring is in place to automate it. The audit excludes setting-specific / post-SRD content (Tasha's, Xanathar's beyond the bits already in SRD, Strixhaven, etc.) and homebrew. Findings below feed directly into the [Design Plans Backlog](#design-plans-backlog) re-priorities.

### Headline state

| Layer | Shipped count | Automated count | Coverage |
|---|---|---|---|
| Spells (319 SRD entries) | 319 ✅ data | ~210 cast endpoints route through the engine; ~110 still cast-and-broadcast-only or partial scaling | ~66% mechanical |
| Monsters (322 SRD) | 322 ✅ data + structured actions | `/npc_attack` + `/npc_cast_spell` route most actions through the damage pipeline; legendary / lair actions still ⚪ | ~75% mechanical |
| Conditions (15/15 SRD) | 15 ✅ data | 10 fully wired; **Exhaustion levels ⚪** (single-flag today, RAW has 6 stacking levels with cumulative penalties); Deafened/Petrified-detail/Restrained-grapple-source partial | ~70% mechanical |
| Items (292 SRD equipment + magic items) | 292 ✅ data | **0% magic-item automation** — every magic item's `actions` array is empty; no attunement gate, no charges, no spell effects, no on-hit riders | <25% mechanical (weapons + armor only) |
| Class features (133 per-row entries) | 107 ✅ / 5 🟢 / 1 🟡 / 20 ⚪ | ~80% ✅ across the 12 classes (per `docs/plans/class-content-status.md`) | ~80% mechanical |
| SRD feats (1 in SRD 5.1 — Grappler) | 1 ✅ data (`grappler.json`) | Grappler 🟡 announce-only; 6 PHB-not-SRD feats (Lucky, Defensive Duelist, War Caster, Mage Slayer, Sentinel, Polearm Master) wired via the reactions framework but data layer doesn't list them | N/A — SRD 5.1 only ships 1 feat |
| SRD backgrounds (1 in SRD 5.1 — Acolyte) | 1 ✅ data (`acolyte.json`) | Pure descriptive, RAW-correct | 100% (RAW backgrounds carry no mechanical effect server-side) |
| SRD races (9/9) | 9 ✅ data + traits curated | 8 wired through `_RACE_SAVE_ADVANTAGES` + damage-resistance + sleep-immunity + Relentless Endurance + Halfling Lucky (all 5 surfaces) | ~90% mechanical |

### Headline gaps (RAW-implementable, no system blocker)

🔴 **P1 — Magic-item automation (NEW — no plan doc today).** 292 SRD magic items shipped as data but `actions: []` on every entry. RAW shape is identical to spell endpoints: attunement gate, charges-per-day, spell-effect dispatch, on-hit rider buffs (Flame Tongue, Frost Brand), passive AC/save bonuses (Cloak of Protection — partially shipped as Cloak of Displacement reaction in v2.78.0 but item-walk doesn't read `sheet.inventory[*]._reactions[]` yet). **Suggested first slice:** Pearl of Power (recover one spell slot — already a primitive); Wand of Magic Missiles (auto-cast with charges); Cloak of Protection (+1 AC + saves passive); Bracers of Defense (+2 AC unarmored). Write `docs/plans/magic-items-automation.md` before starting; this is the largest single un-planned SRD surface.

🔴 **P1 — Exhaustion-level tracking (NEW — no plan doc today).** RAW: 6 cumulative levels with disadvantage on ability checks (Lv 1), speed halved (Lv 2), disadvantage on attacks + saves (Lv 3), HP max halved (Lv 4), speed → 0 (Lv 5), death (Lv 6). Today's engine treats Exhaustion as a single-flag buff. Unlocks: Barbarian Frenzy (Lv 3 Berserker — gain exhaustion on rage end), Wizard Spell Mastery overuse, environmental-hazard hooks. **Suggested approach:** `sheet.conditions.exhaustion.level` int field + a `_exhaustion_disadvantage` helper that composes with the v2.152.0–v2.155.0 condition-disadvantage stack at the same construction sites.

🔴 **P1 — Spell-validation suite Phase 1+** ([`docs/plans/spell-validation-suite.md`](docs/plans/spell-validation-suite.md)). 319 spells shipped, only ~25 have explicit harness tests. Phase 2A v1 (Fire Bolt) is the only shipped slice. CI-gated catalog iteration is the cheapest way to catch SRD-content drift; closes the audit's "spell mechanics ~66% mechanical" gap one batch at a time.

🟡 **P2 — Pact Boon (Warlock Lv 3)** ([`docs/plans/warlock-pact-boon.md`](docs/plans/warlock-pact-boon.md)). Plan exists ⚪ proposed. RAW SRD content; Tome is the cheapest first ship (+3 cantrips picker); Chain unlocks the familiar-summon primitive (extends v2.99.443 summon-companion); Blade adds a CHA-based summoned weapon. Unblocks ~8 Pact-gated invocations downstream.

🟡 **P2 — Battle Master 15 maneuvers** ([`docs/plans/battle-master.md`](docs/plans/battle-master.md)). All 16 maneuvers are SRD RAW; Phase 1 shipped Trip Attack. Remaining 15 compose on the v2.99.405–.414 feature-save resolver + the v2.99.395–.401 on-hit rider primitive — each maneuver is mostly a thin endpoint over those primitives. ~15 commits at one-per-day cadence.

🟡 **P2 — Wizard capstone Spell Mastery / Signature Spells (Lv 18/20).** Both are SRD; both need a spell-picker (pattern: v2.16.1 Arcane Recovery) + a per-rest counter. Two small endpoints unblock Thalindra's Lv 18+ capstones.

🟡 **P2 — Aura of Courage (Paladin Lv 10/18).** Same gate shape as Aura of Devotion (v2.55.0). One commit when a Paladin Lv 10+ fixture lands. Filed in Class Features (next cycle) below.

🟡 **P2 — Reactions v3 pending-damage state machine** ([`docs/plans/reactions-automation.md`](docs/plans/reactions-automation.md) v3 backlog). Closes auto-resolution for Shield AC negation, HR damage-to-attacker, Lucky / SB d20 reroll, Counterspell undo. The framework is shipped (Phases 1–6); v3 replaces the advisory chat-card with state-machine auto-resolution.

🟡 **P2 — Sorcerer Quickened Spell.** The one of 8 SRD metamagics still announce-only. Bonus-action cast routing needs a `/cast_spell` action-economy override path; small lift.

🟢 **P3 — Eldritch Knight Phase 2 read sites** ([`docs/plans/eldritch-knight.md`](docs/plans/eldritch-knight.md)). The Lv 15/18 Phase 1 flag buffs shipped v2.158.11/.12; the Lv 7/10 War Magic + Eldritch Strike are the next slice.

🟢 **P3 — Non-Devotion Paladin Lv 15/20 capstones** ([`docs/plans/paladin-oaths.md`](docs/plans/paladin-oaths.md)). Ancients Undying Sentinel / Elder Champion; Vengeance Soul of Vengeance / Avenging Angel; Conquest Invincible Conqueror; Redemption Protective Spirit / Emissary of Redemption; full Glory oath. Phase 1 plumbing for each landed in v2.99.245–v2.158.x.

🟢 **P3 — Class-feature ⚪ tail** (~20 rows per the [class-content-status](docs/plans/class-content-status.md) re-audit): Barbarian Lv 9–20, Monk Deflect Missiles + Diamond Soul + Empty Body + Perfect Self, Ranger Lv 10–20 (Hide in Plain Sight, Vanish, Feral Senses, Foe Slayer — Vanish Phase 1 shipped v2.158.21), Rogue Reliable Talent / Slippery Mind / Elusive / Stroke of Luck. Most are RAW-implementable but blocked on a Lv 10+ demo fixture for the relevant class. Group by demo-PC bump rather than by class.

### Out-of-scope-by-design (RAW intentionally narrative)

These show up as ⚪ / 🟡 in the per-class tables but RAW is "narrative description, no mechanical effect server-side": Beast Speech, Devil's Sight (Phase 1 install ✅ v2.158.14; engine read site filed), Mask of Many Faces, Pact of the Tome cantrip selection (data-only — counted under Pact Boon plan), Druid Land's Stride (blocked on difficult terrain F11), Monk Slow Fall (blocked on fall-damage F4), Cleric Divine Health / Paladin Divine Health (blocked on disease F5). These stay descriptive until the framework lands — not part of the SRD audit's "should automate" list.

### Out-of-scope (not in SRD 5.1)

Setting-specific subclasses (Tasha's: Beast Barbarian Phase 1 shipped v2.158.20 but the rest of the subclass is Tasha's-only and stays gated on user choice); post-SRD feats (Tough, Resilient, Skilled, Magic Initiate — the data layer correctly carries only Grappler); backgrounds beyond Acolyte. None of these belong in this audit; they're the future-3.x scope per the long-standing user direction.

---

## Manually Added

- 🟢 **P3** — Feature: More pills in the roll log for spells
    - Move spell type, range, action type and details to pills
        - details should be an expanding pill
        - pills should be different color than damage pills
- 🟢 **P3** — Allow the map and roll log (when on the left) to move over the tt-topbar but not over the title of the campaign or the ruler, roll log, battle, characters, tools buttons
- 🟢 **P3** — Change the logout button under tools > quick links to reverse how its animated (better for backgrounds)
- 🟢 **P3** — Update all of roll log to look like spells

---

## Character Sheet

### Ability Score Generation
Two methods for players to generate ability scores during character creation:
- **Point buy** — players spend a fixed pool of points (standard D&D 5e: 27 points, scores 8–15 before racial bonuses) with an interactive cost table shown in the sheet UI. Should enforce the budget in real time and show remaining points.
- **Dice rolling** — roll 4d6 drop lowest for each attribute, with an in-sheet button per score and a "Re-roll all" option. Should show the individual dice results before committing. Optionally allow the GM to lock or unlock rerolls per campaign.

### Class Resource Tracking in Mini-Sheet
Review every D&D 5e class and subclass resource and surface the most commonly used ones in the mini-sheet panel. Current mini-sheet only shows HP and basic rolls. Resources to audit and add:
- **Rage** (Barbarian) — uses per long rest; toggle button to mark active (grants resistance, damage bonus) with a use counter
- **Ki points** (Monk), **Sorcery points** (Sorcerer), **Superiority dice** (Battle Master Fighter), **Bardic Inspiration** — numeric trackers with per-rest reset
- **Channel Divinity**, **Second Wind**, **Action Surge**, **Lay on Hands** pool — binary or pool trackers
- **Wild Shape** uses (Druid), **Arcane Recovery** (Wizard) — per-rest binary toggles

Goal: a compact resource row below HP in the mini-sheet that auto-populates based on the character's class(es). Resources should persist server-side (stored in the character JSON) and broadcast updates via WebSocket so the GM can see resource consumption in real time.

### Dynamic Character Art Updates
When a player updates their character portrait on their sheet, the change should propagate in real time to the tabletop — updating the token image, the player list, and any other places the portrait is displayed — without requiring a page reload. Should use the existing WebSocket broadcast infrastructure so all connected clients (GM and other players) see the new art immediately.

---

## GM Tools

### GM Access to All Character Sheets
GMs should be able to open and read any player's character sheet in the campaign directly from the tabletop or campaign settings, without needing to be assigned as the character's owner. Read-only access is the minimum; optionally allow the GM to make edits (e.g. to update HP after a session or correct a mistake). Needs a clear UI entry point — likely a "View Sheet" button next to each character in the GM's player list.

### Reporting Page
Admin/GM dashboard showing campaign activity: session count, token move history, roll statistics, active players over time. Useful for GMs who want a post-session summary.

### Initiative Tracker Roll Prompt
When a combatant is added to the initiative order without a roll (e.g. added mid-combat from the token sheet or manually), show the GM a "Prompt Roll" button next to that entry. Clicking it sends a WebSocket message to the relevant player's client asking them to roll initiative. The button disappears automatically once the player's initiative is recorded (either via self-roll or GM entry).

### Homebrew Clone
Add a "Clone" button on every homebrew entry in the campaign settings homebrew menu — feats, backgrounds, races, subclasses, monsters, and classes (the six file-based homebrew types as of v2.0.0). Clicking it duplicates the source record as a new homebrew JSON file with a name pre-populated to "Copy of \<original\>" and a fresh auto-generated slug, then opens the new entry in the editor for the GM to tweak. Makes it trivial to spin off variants (e.g. clone "Bandit" → tweak HP / abilities → save as "Veteran Bandit") without retyping every field. Behaviour: server-side endpoint reads the source JSON, mutates the `slug`/`name` fields, writes a new file in the same campaign scope, redirects to the edit form. Existing-slug guard already applies (the existing `_existing_*` check in `homebrew/import` rejects duplicates). No clone for shipped SRD content — that lives in `app/data/local/dnd5e/` and is read-only; cloning shipped → homebrew would be a separate feature.

### Homebrew Monster Attack Fields → Rollable Attack Buttons
Expand the homebrew-monster Actions editor (`app/templates/campaign_settings.html` ~line 2188-2192, currently a generic `data-features-editor` exposing only `name` + `desc`) so each action carries the same structured fields the shipped SRD stat blocks already use — `attack_roll: bool`, `attack_bonus: int` (or derived "+to_hit"), `damage: "1d8"`, `damage_type`, optional `save_ability` / save DC for save-based attacks. With those fields populated, the stat-block view can render each attack as a clickable button that pipes through the existing `/roll` endpoint (mirroring the character sheet's weapon attack flow at `app/static/sheet.js`) so GMs running a homebrew "Veteran Bandit" don't have to manually retype `1d20+5` and `1d8+3 slashing` into chat for every swing. Scope: (1) extend the features-editor JS to render the extra attack fields when the parent fieldset is the Actions list (Special Abilities / Reactions / Legendary can stay name+desc-only — those are mostly narrative), (2) update the homebrew monster POST handler to persist the structured fields into the JSON file, (3) extend the monster stat-block read-view to render attack buttons when `attack_roll: true` is set, with hover/click semantics matching the character-sheet attack buttons. Bonus follow-up: a "Parse from description" button that regex-extracts `+N to hit` / `NdM damage type` from a pasted SRD-style description so importing a homebrew monster doesn't require filling every field manually.

### Unified Monster Sheet in Initiative Tracker (reuse character sheet UI)
Today the initiative tracker opens a read-only stat-block popover for monster entries, while character entries open the full interactive D&D 5e sheet (`app/templates/sheet_dnd5e.html`) with clickable ability checks, skill checks, saves, and weapon-attack buttons that pipe through `/roll`. Goal: replace the monster popover with the same sheet shell so the GM can click an attack on "Bandit Captain" the same way a player clicks an attack on their PC — one-click roll, auto-applied advantage/disadvantage from `roll_state`, breakdown lands in the shared roll log. Pairs naturally with the "Homebrew Monster Attack Fields" TODO above (the structured `attack_roll` / `damage` fields are the data the buttons bind to). Scope sketch: (1) backend — extend the sheet route or add a "monster sheet" sibling that reads a stat block (SRD JSON or homebrew JSON) and projects it into the same context shape `sheet_dnd5e.html` expects (abilities, modifiers, skills, attacks, spells). Most fields map cleanly; HP/AC/speed/CR have direct equivalents, skills need to be derived from the monster's `skills` list + ability modifiers, attacks come from the Actions list. (2) frontend — reuse `sheet.js`'s `wireDnd5eRollButtons` against the monster sheet so ability/skill/save/attack clicks all hit `/roll` and respect roll-state. (3) initiative tracker — open the new sheet (full-screen or large modal) instead of the popover, keyed by token's stat-block reference (slug or homebrew slug). (4) ownership/scope — monsters are GM-only; the sheet should hide the "edit" affordances available to a PC owner (or route them to the homebrew editor for homebrew monsters). Open question: do legendary actions and lair actions get first-class buttons too, or stay as narrative text? Probably first-class buttons since they're the rolling-heavy content. Builds on the structured-attack-fields TODO above; can ship the read-mostly version first and incrementally add roll wiring per field category.

---

## Combat

### Advantage & Disadvantage Tracking
Per-character roll-state toggle (adv / normal / dis) that the server applies to d20 rolls automatically, with the existing manual `adv` / `dis` dice buttons preserved as one-shot overrides. Three phases: manual toggle, condition automation, context-aware rolls. See [`docs/plans/advantage-disadvantage.md`](docs/plans/advantage-disadvantage.md) for the full design.

### Death Saving Throws
Triggered automatically when a character hits 0 HP. Mini-sheet + full sheet show success/failure pips; "Roll Death Save" button rolls a 1d20 through the regular roll pipeline (so it honors the adv/dis roll-state toggle). Healing wakes the character up; damage at 0 HP ticks failures (with crit and massive-damage rules per 5e RAW). GM gets override + stabilize controls. See [`docs/plans/death-saves.md`](docs/plans/death-saves.md) for the full design.

### Combat 2.0 — Action Economy Tracking
Full per-turn action economy tracker surfaced in the initiative tracker and each player's mini-sheet. Tracks the four action types defined by D&D 5e:

- **Action** — one per turn; used for attacks, casting most spells, Dash/Disengage/Dodge/Help/Hide/Ready
- **Bonus action** — one per turn; class features, certain spells, off-hand attacks
- **Movement** — up to the character's speed (in feet); partially consumed by moving between tokens (requires Maps 2.0 grid distance awareness)
- **Free action / Reaction** — one reaction per round; tracked separately, auto-resets at the start of the character's next turn

UI: a compact row of four icons in the initiative tracker entry and mini-sheet. Clicking an icon marks it spent (greyed out). At the start of a character's turn the GM can click "New Turn" to reset all four. The GM can also manually mark/unmark any action for any combatant. State is broadcast over WebSocket so all clients stay in sync.

---

## Maps & Map Editor

### Bulk Map Upload
Allow GMs and admins to upload multiple map images at once (e.g. a zip or multi-file picker) rather than one at a time. Should probably show a progress indicator and let the user assign names/grid settings to each before committing.

### Map Generator
Procedural in-browser map generation — produce a playable battle map without any external upload. Minimum viable output: a dungeon room layout (walls, corridors, door placements) rendered to a canvas the GM can place tokens on immediately. Stretch goals: biome presets (dungeon, wilderness, tavern interior), adjustable density/size parameters, and one-click export as a PNG that feeds into the existing map upload flow.

### Bundled Art Assets (Maps, Player Tokens, Monster Tokens)
Source and bundle a starter set of free-to-use art so new campaigns have something to work with out of the box. Three separate asset packs:
- **Battle maps** — a handful of generic scenes (dungeon room, tavern, forest clearing, city street) usable as starting maps
- **Player tokens** — a set of generic adventurer portraits (warrior, rogue, mage, cleric, ranger, etc.)
- **Monster tokens** — common encounter creatures (goblin, skeleton, orc, wolf, spider, etc.)

Licensing requirements: CC0 or CC BY with attribution in a bundled `CREDITS.md`. Consider AI-generated art (e.g. Stable Diffusion with a permissive licence) as a practical source for a consistent style across all three packs. Assets should ship inside the Docker image under `app/static/bundled/` so they are available without any upload step.

### Maps 2.0 — Advanced Map Features
Extends the existing battle map canvas with GM-controlled environmental features. Builds on the Map Editor Framework groundwork below; these items represent the prioritised feature set for a Maps 2.0 milestone.

- **Combat movement locking** — when a combat encounter is active, token movement is capped at the character's speed (in feet). Each move broadcasts the distance consumed; the token becomes unmovable once the movement budget is exhausted for that turn. Requires grid scale (ft per square/hex) to be set on the map. Integrates with Combat 2.0 action economy tracking.
- **Fog of war** — GM-controlled per-cell reveal overlay. Players see black/obscured cells until the GM reveals them. Two modes: manual brush reveal (GM paints explored areas) and auto-reveal based on token line-of-sight. GM always sees the full map.
- **Walls & doors** — the GM places wall segments (line tools) directly on the battle map. Wall data is saved at the map level (not per-encounter) so the same map always loads with its walls intact. Doors are interactive wall segments: players and GMs can toggle them open/closed, which updates the fog-of-war LOS calculation in real time.
- **Dedicated wall editor** — a separate editing mode (toggle in the GM toolbar) for placing, moving, and deleting wall segments. Should be distinct from normal token-interaction mode to prevent accidental edits during play. Wall data stored as a JSON array of line segments on the `BattleMap` record.
- **Clickable map items** — hotspots placed by the GM that trigger a description popup or roll prompt when a token moves onto or a player clicks them.

### Map Editor Framework
Groundwork for in-browser map authoring tools. Planned capabilities:
- **Fog of war** — GM-controlled reveal of map regions; players see only explored areas
- **Walls** — line segments that block token line-of-sight
- **Doors** — interactive wall segments that players/GMs can open or close
- **Clickable items** — hotspots on the map that trigger a description popup or roll prompt
- **Multi-map encounters** — link multiple maps into a single encounter (e.g. interior/exterior transitions) without switching the active map for the whole campaign

### Lighting
GM can place different kinds of light sources on the map — torches, lanterns, campfires, magical lights — each with their own radius, colour, and behaviour. Flicker animation for fire-based sources (gentle brightness/radius oscillation), steady glow for magical lights, etc. Integrates with fog of war and player vision: tokens illuminate the area around them based on attached lights, and players only see what their token's light source(s) cover (plus any GM-revealed fog area). The GM has full visibility regardless. Stretch goals: ambient map-wide lighting (day/night/dim), per-token vision types (darkvision out to N ft as dim light, blindsight ignoring lighting entirely), and "extinguish" interaction on placed lights. Builds on the Maps 2.0 / Map Editor Framework groundwork above — both fog-of-war LOS and wall segments need to land first so lighting can compute shadows correctly.

---

## Media & Content

### Resources
A dedicated section for GMs and admins to upload documents (PDFs, images, handouts) that players can view directly in the browser — inline PDF rendering, no download required. Needs access control so GMs can choose whether a resource is visible to all players or GM-only.

### Playlist Builder with Existing Songs
Allow GMs to create playlists from tracks already uploaded to the campaign rather than re-uploading. UI: a picker listing existing campaign audio tracks, drag-to-reorder, save as a named playlist. Backend: new playlist model + endpoints; guard file deletion to prevent removing audio that is still referenced by a playlist.

---

## Player Features

### User Presence on the Tabletop
Show who is currently connected to the session in real time. All connected users (GM and players) should be able to see at a glance which other players are online, idle, or have disconnected. Planned scope:

- **Presence indicators** — a small online/offline dot (or avatar badge) next to each player's name in the player list and/or initiative tracker. Green = connected, grey = disconnected. Optional: amber = connected but idle (no interaction for N minutes).
- **WebSocket lifecycle hooks** — on connect, broadcast a `presence_join` message to all clients; on disconnect (or WebSocket close), broadcast `presence_leave`. Clients maintain a local presence map and update the UI reactively.
- **Cursor / active-token highlight** (stretch) — show a faint coloured ring or name label on the token currently being hovered or dragged by another user, similar to Google Docs cursor presence.
- **GM view** — the GM's player list should show presence state for every campaign member, including those who haven't joined the current session yet (shown as offline).

Backend: presence state is ephemeral (in-memory in `realtime.py`, not persisted to the database) — it resets when the server restarts, which is acceptable.

### Player Notes
Per-player scratchpad (rich text or markdown) scoped to a campaign. Notes should be private to the player by default, with an optional "share with GM" toggle. Persisted server-side so they survive page refreshes.

---

## UI / Mobile

### Slide-Out Menu for Mobile
On small screens, replace the current sidebar with a proper slide-out drawer triggered by a hamburger button. The map should fill the full viewport and the drawer overlays it rather than pushing it. Needs gesture support (swipe to open/close).

### Darker Sepia Themes
Add a few darker sepia/warm-brown colour themes as alternatives to the existing dark theme. Candidates: a deep parchment (dark tan background, inked-brown text), a candlelit tavern (very dark brown with amber accents), and a burnt manuscript (near-black with faded sepia highlights). Should slot into the existing theme system with new CSS variable sets — no structural changes needed.

---

## Rules Reference

### SRD Rules in Full Text
Surface the complete D&D 5e Systems Reference Document (SRD 5.1, CC BY 4.0) as searchable in-app reference text. Players and GMs should be able to look up rules without leaving the VTT. Planned scope:
- Full SRD text indexed and searchable by keyword (conditions, actions, spells, equipment, etc.)
- Contextual links from the character sheet and encounter panels (e.g. clicking a condition name opens its SRD entry)
- Offline-capable: content bundled in the Docker image rather than fetched at runtime
- GM can pin a rule snippet to the tabletop panel for the whole table to see during play

Content source: the official SRD 5.1 PDF / markdown release from Wizards of the Coast, licensed CC BY 4.0. Attribution required in-app.

### Page Number References in Official Content
Where SimpleVTT surfaces content from official published sourcebooks (e.g. PHB, MM, DMG) — in spell descriptions, class features, item entries — investigate whether page numbers can be shown alongside the source citation (e.g. "PHB p.218").

**Licensing review required before implementing:** displaying page numbers from non-SRD sourcebooks may constitute a reference to copyrighted content even if the page number itself is a fact. Consult the D&D 5e SRD licence terms and any Fan Content Policy. If page numbers are only shown for SRD-sourced content (which is CC BY 4.0), no additional licensing concern applies — SRD content should be safe. Non-SRD sourcebook page numbers should be gated on legal sign-off.

---

## Legal & Compliance

### Full Audit for Licensed Material
Systematic review of all content bundled in or served by SimpleVTT to ensure nothing included exceeds its licence terms. Scope:

- **SRD content (spells, monsters, items, classes, races)** — confirm all data served via the Open5e mirror or shipped FS files is SRD 5.1 / CC BY 4.0 material only; flag any non-SRD entries (e.g. setting-specific content, post-SRD sourcebook expansions)
- **Images and art** — audit every image in `app/static/` (including any bundled token/map art) against its licence; ensure CC0 or CC BY assets have attribution in `CREDITS.md`
- **Fonts** — verify Google Fonts licences (currently all SIL OFL 1.1 — should be clean)
- **Third-party JS/CSS libraries** — list all vendored or CDN-loaded libraries and confirm licences are compatible with self-hosting
- **Any AI-generated art** — confirm the generation tool's output licence (some tools claim copyright on outputs; others release CC0); document the tool and settings used for each asset

Output: a `CREDITS.md` file at the repo root listing every third-party asset, its licence, and its source URL, plus a checklist of items that need further review or replacement.

---

## Test Infrastructure

> **Bugs moved to [`BUGS.md`](BUGS.md).** The skull-overlay CI emoji-font skip (B1) and the Garrik-not-tokenized encounter-sim skips (B2) now live in the bug tracker with their repro + fix paths. This section is kept for non-bug test-infra *features* if any are filed later.

---

## Integrations

### Philips Hue Integration
Allow GMs to sync Philips Hue smart lights with tabletop events — e.g. dim lights on combat start, flash red on a critical hit, restore brightness when combat ends. Should connect to the local Hue Bridge (mDNS or manual IP) and allow the GM to map VTT events to Hue scenes or brightness/colour changes in campaign settings.

---

## Visual

### Frosted-glass treatment across the whole tabletop interface
v2.49.139 applied the iOS-style frosted-glass look (semi-transparent background + `backdrop-filter: blur(10px) saturate(140%)`) to roll-log cards only. Extend to every drawer card on the tabletop so the canvas behind reads through everywhere — init-tracker cards (`.init-row` / `.init-entry`), GM panel cards (`.gm-panel`), the sound panel, the AoE picker hint, the ruler hint, the targeting chip, etc. Each surface needs:
- A theme-coherent `color-mix(in srgb, var(--bg) 78%, transparent)` background (or the appropriate variant for accent / panel-tinted surfaces)
- `backdrop-filter: blur(10px) saturate(140%)` + `-webkit-backdrop-filter` for Safari/iPad
- Verification that text remains readable on a busy map across all 9 themes (dark, midnight, dim, light, forest, bubblegum, oled, fire, sepia)

Performance note from v2.49.139: each `backdrop-filter` element triggers a compositor layer. Audit the total composite layer count once applied — if it gets heavy on long sessions, gate the blur behind a "low-detail" theme toggle.

---

## Class Features (next cycle)

### Paladin Aura of Courage (Lv 10)
Same shape as Aura of Protection (v2.53.0) and Aura of Devotion (v2.55.0) — `_ally_has_aura_of_courage(db, campaign_id, saving_char_id)` walks init for any Paladin Lv 10+ in any oath. RAW: "you and friendly creatures within 10 feet of you can't be frightened while you are conscious." This is a **condition-install immunity** gate matching the Aura of Devotion pattern, just with "frightened" as the blocked condition key (instead of "charmed"). Wire the same way: gate at `/roll_request/{id}/respond`'s PC-failed-save condition-install block, skip install + broadcast `feature_used(source=aura-of-courage)` when `cond.key == "frightened"` and a Paladin Lv 10+ is in init.

**Caelan bump**: 7 → 10. **Three levels** of cascading changes — prof bonus +3 → +4 (changes at Lv 9), HP +24, Lay on Hands pool 35 → 50, spell slots gain L3 (4/3/2 instead of 4/3/0). The prof bump breaks existing attack-bonus assertions in `test_attack.py::test_attack_divine_smite_spends_slot` (Longsword +6 → +7 because STR +3 + prof +4 = +7) — needs an audit-and-fix pass; this latent test-coupling hazard is tracked as **B9 in [`BUGS.md`](BUGS.md)**. **Recommended scope**: bundle Aura of Courage with the Caelan bump so the slot-pool / damage-die scaling lands once. Defer Aura of Devotion's Lv 18 30-ft radius expansion — same helper, larger gate, different commit.

Filed by v2.55.0 when the user picked Indomitable as the next implementation target. Pick this up after Indomitable ships.

### Fighter Indomitable (Lv 9+) — IN PROGRESS as v2.56.0 "Iron Will"
Garrik bump 7 → 9 (prof +3 → +4, HP +14, Second Wind 1d10+9). New `/use_indomitable` endpoint installs a single-use `indomitable-armed` self-buff; the save-roll construction hook reads the buff, swaps `1d20 → 2d20kh1`, and removes the buff from the combatant so the consumption is per-save (RAW: one specific reroll). RAW-bent v1: advantage on the next save rather than reroll-on-failure, since the post-roll reroll flow needs an undo-and-reapply path for installed conditions which is its own substantial commit. The accepted divergence + the precise post-roll reroll follow-up is tracked as **B10 in [`BUGS.md`](BUGS.md)**.

---

## Full Class-Feature Automation — remaining backlog

🔥 **IN PROGRESS** — plan: [`docs/plans/full-feature-automation.md`](docs/plans/full-feature-automation.md); live audit: [`docs/automation-coverage.md`](docs/automation-coverage.md). **Phases 0–7 ✅ done** + the entire v2.128.2–v2.149.1 retrofit batch landed (see CHANGELOG). Only Phase 8 (higher-level subclass features Lv 6/10/14/17/20) and a few Phase-1.5 / Phase-2 follow-ups on individual features remain.

**Status by archetype (re-evaluated 2026-06-08):**

Shipped archetypes (Phase 7 reactions, auras E, on-hit B, buff/temp-HP D/F, movement G) live in [`TODONE.md`](TODONE.md#full-class-feature-automation--archetype-bullets-shipped).

- 🟢 **P3 — Phase 8: higher-level subclass features (Lv 6/10/14/17/20).** Mostly composition on the now-built primitives; batch by class. The long tail. **Now the primary remaining work for the parent plan.**
- 🟢 **P3 — Per-feature Phase-2 finishers (deferred from this session):**
    - **Blade Flourish Phase 2** — Defensive AC self-buff + Mobile push + Slashing secondary-target routing.
    - **Fancy Footwork Phase 2** — OA-flow gate reads the `fancy-footwork-blocked` buff and skips OAs against the named char_id.
    - **Relentless Avenger Phase 2** — `/token/move` consumes `free_movement_remaining_ft` budget + skips OA prompts while `oa_immune_during_move` is set.
    - **Supreme Healing Phase 1.5** — `/apply_healing` chat-card path (legacy `_heal_claims` flow) also substitutes max dice.
    - **Combat Inspiration Phase 3** — Integrate the AC half into the reactions framework so the prompt fires automatically on `attack_targeted` for any combatant carrying a BI die buff.
    - **AP Phase 3 / UM Phase 1b** — Auto-install via `/attack` post-hit hook (currently both require player-driven trigger via the `target_surprised` / endpoint call).
- 🟢 **P3 — Classifier rerun for `docs/automation-coverage.md`.** Auto-generated row counts in the "Full classification" table still pin v2.99.460; rerun the classifier after the v2.128.2–v2.149.1 batch so the per-endpoint table reflects reality. Curated bullets + the "Recent retrofits" table are aligned per v2.142.1 + v2.149.1.

The remaining ~30 announce-only rows are **archetype J** (narration-only-by-design: passive senses, language grants, passive damage-boosters that already ride other paths) — leave as-is; see the audit doc's "Notable announce-only backlog" section for the full split.

---

## Design Plans Backlog

Every design doc under [`docs/plans/`](docs/plans/) + the two repo-root planning docs (`docs/encounters-plan.md` + `docs/multi-system-refactor.md`). Priorities reflect the post-v2.159.30 / 2026-06-11 SRD-audit refresh — **🔥 IN PROGRESS** = a plan with ongoing commits this session; **🔴 P1** = next-up substantial work that closes a real SRD-implementable gap; **🟡 P2** = substantial deferred phases or proposed work; **🟢 P3** = lower-priority or living-doc style.

> **v2.315.0 SRD-audit refresh (current).** Priorities re-shaped against the [SRD 5e Audit (v2.315.0 refresh)](#srd-5e-audit-v23150-refresh) at the top of this file — that section is now the authoritative re-prioritization. Since the 2026-06-11 list: legendary actions + lair actions + legendary resistance all ✅ shipped (v2.159.32–v2.167.0); the spell-validation suite is mostly ✅. The single biggest lever on overall SRD % is now the **magic-item content tail (116 of 239 items still GM-narrated)** — promoted to P1 below. Next is **spell upcast scaling** (~110 cast-and-broadcast-only spells), then the **class-feature ⚪ tail** (24 rows).
>
> **2026-06-11 SRD-audit refresh (superseded).** Priorities re-shaped against the [SRD 5e Audit (2026-06-11 refresh)](#srd-5e-audit-2026-06-11-refresh) above. The prior 2026-06-10 P1 list closed end-to-end: magic-items-automation framework ✅, Exhaustion-level tracking ✅, Pact Boon ✅, Battle Master 16/16 maneuvers ✅, non-Devotion Paladin Lv 15/20 capstones ✅. (That pass's P1 — legendary/lair actions + spell-validation — has since shipped; see the v2.315.0 note above.)

### 🔥 IN PROGRESS

- [`full-feature-automation.md`](docs/plans/full-feature-automation.md) — see the section above; Phase 8 is the next slice.

### ✅ Shipped end-to-end

Now lives in [`TODONE.md`](TODONE.md#design-plans-backlog--shipped-end-to-end) — 12 plans (auras, death-saves, demo-mode, feature-saves, movement-and-summons, movement-oa-flow, on-hit-riders, ruler-and-range, spell-upcasting, temp-hp-and-bonuses, test-harness, wild-magic). Plus the 2026-06-11 refresh: [`carrying-capacity.md`](docs/plans/carrying-capacity.md) ✅, [`exhaustion-levels.md`](docs/plans/exhaustion-levels.md) ✅, [`magic-items-automation.md`](docs/plans/magic-items-automation.md) ✅ (framework — Phase 9 content tail still open under P2), [`battle-master.md`](docs/plans/battle-master.md) ✅ (16/16 maneuvers), [`warlock-pact-boon.md`](docs/plans/warlock-pact-boon.md) ✅.

### 🔴 P1 — Next substantial work (v2.315.0 SRD-audit driven)

- **Magic-item content tail (the #1 SRD-automation lever).** 116 of 239 SRD magic items still have no code-side wiring and are GM-narrated. The engine substrate (`_MAGIC_ITEM_ACTIONS` / `_MAGIC_ITEM_PASSIVES` / `_MAGIC_ITEM_ATTACK_RIDERS` / ability-override / buff / boolean derived flags) is **complete** — every remaining item is a content drop-in fitting an existing template (on-hit rider, charge-with-spell, passive buff, nat-20 hook, ability-override, boolean flag). Ship in ~10–15-item batches; each batch is its own MINOR commit + 3 harness tests + a coverage-doc total bump. ~8–10 commits to close. Framework plan: [`magic-items-automation.md`](docs/plans/magic-items-automation.md) (Phase 9 — content tail).
- **Spell upcast scaling (~110 spells).** Add structured `upcast` / `damage_per_slot` scaling data to the cast-and-broadcast-only spells so higher-slot casts scale automatically. The resolver shipped in [`spell-upcasting.md`](docs/plans/spell-upcasting.md) Phase B (v2.110.0) — this is data-only content work that moves Spells from ~70% → ~90%+.
- [`reactions-automation.md`](docs/plans/reactions-automation.md) — **Phases 1–6 all ✅**; v3 backlog (pending-damage state machine for auto-resolution) is the substantial remaining slice. Adjusted up from "Phase 7" framing in the prior P2 list — Phase 7 already shipped per v2.118.0–v2.122.0.

### 🟡 P2 — Substantial deferred phases

- **Magic-item content tail — promoted to P1** (see the P1 list above; it's the single biggest SRD-automation lever). The stale "250 of 292 / Phase 9" framing is superseded by the v2.315.0 audit's corrected 116 / 239 count.
- **NEW: Carrying-capacity Phase 4 (Encumbered variant, PHB p.176).** Optional rule — currently skipped per the v1 plan; speed -10 ft + disadvantage on STR/DEX/CON checks when load > STR × 5 lb. Small lift over the existing `_carry_weight` helper.
- [`sorcery-points-and-metamagic.md`](docs/plans/sorcery-points-and-metamagic.md) — **7 of 8 PHB metamagics shipped end-to-end through the v2.99.x window** + Sorcerous Restoration ✅. Outstanding: Quickened Spell (action-economy override path) + AoE multi-target Empowered loop.
- [`paladin-oaths.md`](docs/plans/paladin-oaths.md) — header refreshed 2026-06-11; Lv 15/20 capstones for Ancients / Vengeance / Conquest / Redemption / Glory all ✅ (v2.99.283–.292). Outstanding small follow-ups: Vengeance Phase 2 OA-flow gate; Conquest Lv 3 (Conquering Presence) + Lv 7 (Aura of Conquest); Redemption Lv 3 (Rebuke the Violent); Glory Lv 3 (Inspiring Smite). Down-ranked from prior P2 position because most scope has shipped.
- [`eldritch-knight.md`](docs/plans/eldritch-knight.md) — Phase 1 ✅ + **Arcane Charge Phase 1 ✅** (v2.158.11) + **Improved War Magic Phase 1 ✅** (v2.158.12). Outstanding: Lv 7 War Magic (cantrip → bonus-action weapon attack) + Lv 10 Eldritch Strike (per-target save-dis install) + the Phase 2 read sites for Arcane Charge / Improved War Magic.
- [`unified-mini-sheet.md`](docs/plans/unified-mini-sheet.md) — 3 mockups landed; **Phase 1–3 unstarted**. Pairs naturally with Class Resource Tracking + Combat 2.0.
- [`encounter-sim-test-suite.md`](docs/plans/encounter-sim-test-suite.md) — **substantial progress** (Level 1 smoke + Level 2 encounter sim shipped through v2.49.x); Level 3 edge-case framework seeded; Phase 4 (Level 3 completion, ~40 tests) pending.
- [`docs/encounters-plan.md`](docs/encounters-plan.md) — **proposed, not started**. Save/load encounter state.
- [`docs/multi-system-refactor.md`](docs/multi-system-refactor.md) — **proposed, not started**. Big architectural lift; out of SRD-audit scope but tracked here for completeness.
- [`advantage-disadvantage.md`](docs/plans/advantage-disadvantage.md) — Phases 1, 2a–2f all ✅ (v2.2.0–v2.157.0); **only Phase 3 (positional / 5-ft prone-melee advantage) remains, blocked on Maps 2.0**. Down-ranked within P2 because the unblocker is itself a multi-session lift.

### 🟢 P3 — Lower-priority / living docs

- [`player-simulacrum.md`](docs/plans/player-simulacrum.md) — **design only, all phases unstarted**. Speculative.
- [`wiki-expansion.md`](docs/plans/wiki-expansion.md) — living roadmap of how-to guides + reference cards still to write. Doc-style work, lots of small slices.
- [`class-content-status.md`](docs/plans/class-content-status.md) — living inventory; updates as features ship.
