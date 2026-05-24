# Unified mini-sheet — design plan

**Status:** ⚪ Proposed — for review. No code shipped beyond the v2.49.183 partial alignment that this doc supersedes / extends.
**Filed across:** the v2.49.183 alignment work (NPC gained PC-style header + HP bar) hit the limit of what we can do without picking a unified architecture. The user's question — "can we create a new mini-sheet and only display properties that are relevant to the entity displayed?" — is what this plan answers.
**Related code surfaces:** `app/templates/_mini_sheet_card.html` (PC partial), `app/templates/tabletop.html::buildMonsterInitSheet` (NPC JS renderer), `app/routes/tabletop_routes.py::_monster_template_to_sheet` (server-side monster projection).
**Related docs:** [Battle & Characters tab sheets](/wiki/battle-character-sheets-guide), [PC vs NPC combat systems](/wiki/pc-vs-npc-systems).

---

## Goal

Eliminate the two-renderer split in the init-tracker mini-sheet. Today, **PCs** render through the Jinja partial `_mini_sheet_card.html` (rich tabbed sheet with 6 tabs: Actions / Spells / Abilities / Skills / Resources / Feats) and **NPCs** render through `buildMonsterInitSheet` (JS-built inline stat block with 2–3 tabs). The two paths have drifted across v2.49.x feature work despite multiple alignment passes (v2.49.175 Spells tab parity, v2.49.183 header + HP bar). Every new mini-sheet feature has to be implemented twice or accept the divergence.

**The goal: one renderer, one source of truth, conditional sections per entity type.** Different fields show or hide based on what the entity actually has, but the chrome + visual conventions are identical.

---

## History — why we're back here

v2.3.17 (released ~mid-2024) attempted the unified approach: a `monster_templates` context pool that synthesized PC-style mini-sheets for monsters. Reverted in **v2.3.34** because users preferred the "older 2.3.9 inline stat-block view that `buildMonsterInitSheet` produces directly from the resolved `tmpl.sheet`" — quote from the `tabletop.html:1862-1869` Jinja comment block.

So the precedent for "unify" is documented, and the precedent for "users like the compact NPC view" is also documented. **Any new attempt has to satisfy both constraints** — unified chrome AND density-appropriate body.

---

## Mockups

Three approaches presented for review. Each shows the same combatant (Soren the Cult Acolyte) so the differences are about the **renderer**, not the data.

> **🎨 Visual mockups** — the three options are also rendered as
> live-styled HTML at [/wiki/unified-mini-sheet-mockups](/wiki/unified-mini-sheet-mockups)
> (side-by-side NPC + PC for each approach, plus a 3-up summary
> comparison at the bottom). The ASCII below is the same content
> in text-form for review-in-diff.

---

### Mockup A — "Conservative: PC-shape, NPC fits in"

Reuse `_mini_sheet_card.html` verbatim. Server projects NPCs into PC-shaped dicts (`_monster_template_to_sheet` already does most of this); empty PC-only fields (spell_slots, death_saves, resources, class_features) hide their sections via the existing `{% if %}` gates. The partial becomes the single source of truth.

```
┌────────────────────────────────────────────────────────┐
│ ●  Soren (Cult Acolyte)                             ▶ │  ← .mini-header (PC partial)
│    Medium Humanoid · evil                              │     class → "Cult Acolyte"
├────────────────────────────────────────────────────────┤     race  → size + type
│ HP 18 / 18    AC 12    Spd 30                          │
│ ████████████████████████████████████████              │  ← .mini-hp-bar gradient
│                                                         │
│  ⚔ Act   💨 Bns   🛡 Rxn   👣 30                       │  ← Economy chips (HIDDEN for
│                                                         │     NPCs via {% if economy %})
│  [ Actions ] [ Spells ] [ Skills ]                     │  ← Tab strip — Abilities /
│ ──────────────                                          │     Resources / Feats hide
│  🗡 Dagger    +4   1d4+2 piercing            🗡 Strike │     when empty (existing gate)
└────────────────────────────────────────────────────────┘
```

**Pros**
- Single source of truth for the entire mini-sheet — every future feature lands in one place.
- Existing PC tests + harness coverage protect the unified path automatically.
- Zero JS-vs-Jinja mental cost — the Jinja partial wins.
- Matches the v2.3.17 architecture that worked; just needs the v2.3.34 density complaint addressed via tighter spacing in NPC mode.

**Cons**
- High refactor risk — `_mini_sheet_card.html` is ~480 lines and references PC-shaped fields throughout (`sh.spell_slots`, `sh.death_saves`, `sh.class_features`, `sh.hit_dice`, `sh.classes`). Each section needs a null-safe `{% if %}` audit.
- Loses the per-NPC charge counter + ↻ recharge button unless we promote that to the unified partial.
- Density: PC partial has more breathing room (padding/gap) than the JS-built NPC view; NPCs would render visually "loose" unless we add a `{% if is_monster %}` density-tightening block (which is the v2.3.34 user complaint resurfacing).

---

### Mockup B — "Symmetric: shared chrome, adaptive tabs" ⭐ RECOMMENDED

A new partial (`_combatant_sheet_card.html`) that both PCs and NPCs feed into via a normalized dict. The chrome (header + HP bar + tab strip) is identical for both. The tab strip **adapts** to the entity's data — PCs get 6 tabs, NPCs get 3 — but each tab renders through the same Jinja blocks regardless of source.

```
┌────────────────────────────────────────────────────────┐
│ ●  Soren (Cult Acolyte)                             ▶ │  ← Shared header (new partial)
│    Medium Humanoid · evil                              │
├────────────────────────────────────────────────────────┤
│ HP 18 / 18    AC 12    Spd 30                          │
│ ████████████████████████████████████████              │  ← Shared HP bar
│                                                         │
│  [ Actions ] [ Spells ] [ Skills ]                     │  ← Adaptive tab strip:
│ ──────────────                                          │     server provides tabs=[...]
│  🗡 Dagger    +4   1d4+2 piercing            🗡 Strike │     PC: [actions, spells,
│                                                         │      abilities, skills,
│                                                         │      resources, feats]
└────────────────────────────────────────────────────────┘     NPC: [actions, spells,
                                                                skills]

┌────────────────────────────────────────────────────────┐
│ ●  Zara Emberfire 🧿                                ▶ │
│    Sorcerer 5 · Tiefling                               │
├────────────────────────────────────────────────────────┤
│ HP 37 / 37    AC 12    Spd 30                          │
│ ████████████████████████████████████████              │
│  ⚔ Act   💨 Bns   🛡 Rxn   👣 30                       │  ← Economy chips when present
│                                                         │
│ [Actions] [Spells] [Abilities] [Skills] [Res] [Feats] │  ← 6-tab PC strip
│                                                         │
│  CANTRIPS                                              │
│  ✨ Fire Bolt   120 feet   +7   2d10 fire     ✨ Cast │
└────────────────────────────────────────────────────────┘
```

**Pros**
- True unification — one partial, one set of tests, one place to add features.
- Server-driven `tabs=[...]` list keeps the partial dumb: don't try to detect "is this an NPC", just iterate the tabs the server says exist.
- Each tab can be its own sub-partial (`_tab_actions.html`, `_tab_spells.html`, `_tab_skills.html`) — easier to refactor, easier to test.
- Naturally extensible: when v2.50 adds a Spells tab to bandits (because someone homebrews a magical bandit), the server includes 'spells' in the tabs list and it Just Works.

**Cons**
- Largest up-front refactor of the three: requires extracting per-tab partials AND building the normalized dict on the server.
- The action-economy chips are PC-only today (NPCs have no economy field) — placing them between HP bar and tabs is fine for PCs, but for NPCs the row would be absent, leaving a visual "gap" unless we conditionally remove the row entirely.
- Charge counter + ↻ recharge button (NPC-only Frightful Howl / Inflict Wounds limit) needs a home in the shared Actions tab — either always render the slot or gate on `action.charges_max > 0`.

> **Aesthetic exploration — pillified variants (v2.49.194).** Two
> rounded-corner variants of Mockup B (`pillified-soft` at 12 px,
> `pillified` at 999 px) are rendered side-by-side at
> [/wiki/unified-mini-sheet-mockups#pillified](/wiki/unified-mini-sheet-mockups#pillified)
> for design review. Pillification is a CSS-only modifier class on
> the `.mock-mini` wrapper — no markup change, no functional impact,
> applies orthogonally to whichever structural mockup wins. The
> active-tab styling does change in both variants (underline-bottom
> → filled-pill background) because underlines read poorly when
> everything around them is round. See open question #5 below.

---

### Mockup C — "Hybrid Density: stat-block body for NPCs, full sheet for PCs"

Shared chrome (header + HP bar). Body **density** branches on entity type:
- **NPC body**: compact 6-cell ability mod grid + flat action list (current `buildMonsterInitSheet` look).
- **PC body**: full tabbed layout (current `_mini_sheet_card.html` look).

This is **the path v2.49.183 already started us down** — we have the shared header + HP bar; the body density diverges. Mockup C is "continue what we have, do it properly with one partial that branches."

```
┌────────────────────────────────────────────────────────┐
│ ●  Soren (Cult Acolyte)                             ▶ │  ← Shared header
│    Medium Humanoid · evil                              │
├────────────────────────────────────────────────────────┤
│ HP 18 / 18    AC 12    Spd 30                          │
│ ████████████████████████████████████████              │  ← Shared HP bar
│                                                         │
│  STR DEX CON INT WIS CHA                               │  ← NPC body: compact ability
│   +0  +2  +0  +0  +2  +0                               │     grid (6 cells) — keeps
│   10  14  10  10  14  11                               │     the v2.3.34 density users
│                                                         │     preferred
│  [ Actions ] [ Spells ] [ Skills ]                     │
│ ──────────────                                          │
│  🗡 Dagger    +4   1d4+2 piercing            🗡 Strike │
└────────────────────────────────────────────────────────┘
                                                                    ⇣ DIFFERENT BODY ⇣
┌────────────────────────────────────────────────────────┐
│ ●  Zara Emberfire 🧿                                ▶ │  ← Same shared header
│    Sorcerer 5 · Tiefling                               │
├────────────────────────────────────────────────────────┤
│ HP 37 / 37    AC 12    Spd 30                          │  ← Same shared HP bar
│ ████████████████████████████████████████              │
│  ⚔ Act   💨 Bns   🛡 Rxn   👣 30                       │
│                                                         │
│ [Actions] [Spells] [Abilities] [Skills] [Res] [Feats] │  ← PC body: full tabbed view
│                                                         │     with spell-slot pips,
│  CANTRIPS                                              │     ability scores, resource
│  ✨ Fire Bolt   120 feet   +7   2d10 fire     ✨ Cast │     counters, rest buttons
│  ✨ Mage Hand   30 feet                       ✨ Cast │
│  LEVEL 1 SPELLS                                        │
│  Slots ● ● ○ ○  2/4                                    │
│  ✨ Magic Missile   120 feet   1d4+1 force    ✨ Cast │
└────────────────────────────────────────────────────────┘
```

**Pros**
- Honors both historical constraints: shared chrome (unification) + NPC density (v2.3.34 preference).
- Smallest refactor — we're 60% of the way there with v2.49.183.
- No risk of accidentally bloating the NPC view (the body branch isolates concerns).
- GM scanning 6 NPC cards stays fast — they don't have to skim past blank Spells / Resources / Feats panels per monster.

**Cons**
- Two body paths to maintain (still less than today's two ENTIRE renderers — header + HP bar are shared at minimum).
- "Unified chrome, divergent body" is a half-measure — future features that touch the body have to be implemented twice.
- NPCs can never gain the tabbed view organically — adding a Spells tab to a homebrew caster monster would feel like a special case.

---

## Comparison matrix

| Dimension | A: Conservative | B: Symmetric ⭐ | C: Hybrid Density |
|---|---|---|---|
| Source-of-truth files | 1 (existing partial) | 1 (new partial + per-tab partials) | 1 (with internal branch) |
| Refactor scope | Audit + null-safety every section of the existing partial | Extract per-tab partials, build server projection, then rewrite | Extract body branch, share chrome |
| Risk of breaking PC sheet | Medium — touch existing partial | Low — net-new partial; PC migrates last | Low |
| Density match for NPCs | Requires CSS tightening for "is_monster" | Same density as PC (could feel loose) | Preserves compact NPC view |
| Extensibility (future features) | High (one place) | Highest (per-tab partials) | Medium (two body paths) |
| Test coverage transfer | All PC tests cover both | Need new harness tests | Most existing coverage still works |
| Honors v2.3.34 rollback | No (re-creates the loose look) | Partial (depends on CSS) | Yes (NPC stays compact) |
| Time-to-ship estimate | 4–6 commits | 8–12 commits | 3–5 commits |

---

## Recommendation

**Mockup B (Symmetric) — for the long term. Mockup C (Hybrid Density) — as the Phase 1 step toward B.**

Rationale: B is the right architectural endpoint (one partial, per-tab sub-partials, server-driven `tabs=[...]`) but the refactor scope is significant. C is what v2.49.183 already started. **Ship C as Phase 1** — extract `buildMonsterInitSheet`'s body into a Jinja partial that shares the header + HP bar with `_mini_sheet_card.html`. This locks in the chrome unification we already have without further density risk. **Then ship B as Phase 2** — once the chrome is shared, extract per-tab partials one by one, replace the NPC body branch with the unified tabbed layout when the per-tab partials are ready. The per-tab extraction is the gnarly part; doing it incrementally on a shared chrome is much safer than doing it big-bang.

---

## Phased plan

### Phase 1 — Hybrid Density (Mockup C)

| # | Step | Files touched | Notes |
|---|---|---|---|
| 1.1 | Extract shared chrome (header + HP bar + footer) into `_mini_sheet_chrome.html` | `app/templates/_mini_sheet_chrome.html` (new), `_mini_sheet_card.html` (use the include), `buildMonsterInitSheet` (port to call `_mini_sheet_chrome.html` server-side) | Server side needs to render the chrome partial for NPCs and inject it into the JS-built body. Best approach: GM-page server-side renders the chrome shell + leaves a `data-body-slot` div; JS body renders into the slot. |
| 1.2 | Move v2.49.183 header + HP-bar code from `buildMonsterInitSheet` into `_mini_sheet_chrome.html` | `app/templates/tabletop.html`, new partial | Delete the JS duplicate. |
| 1.3 | Add per-Combatant chrome render endpoint or pre-bake chrome into the GM init render | `app/routes/tabletop_routes.py` | If pre-baked, no new endpoint needed. |
| 1.4 | Harness test: smoke test that a `_mini_sheet_chrome.html` render emits the portrait + HP bar markup for both PC and NPC sheet projections | `tests/harness/test_mini_sheet_chrome.py` (new) | Renders the partial directly via TestClient. |

### Phase 2 — Symmetric (Mockup B)

| # | Step | Files touched | Notes |
|---|---|---|---|
| 2.1 | ✅ **Done v2.49.193.** Extract `_tab_actions.html` from `_mini_sheet_card.html` Actions panel. (JS Actions panel swap deferred to 2.5.) | `app/templates/_tab_actions.html` (new), `_mini_sheet_card.html` (uses include) | Pure refactor; PC behaviour byte-identical. NPC still rendered client-side via `buildMonsterInitSheet`. |
| 2.2 | ✅ **Done v2.49.195.** Extract `_tab_spells.html` (the v2.49.177+ chip layout) | `app/templates/_tab_spells.html` (new), `_mini_sheet_card.html` (uses include) | Pure refactor; PC behaviour byte-identical. Partial owns the `{% if _is_caster and _spell_vis.any %}` gate so the parent include line is unconditional. Multiclass loop, slot-pip rendering, prepared-caster gating all moved verbatim into the partial via Jinja's parent-scope inheritance (no `{% with %}` needed). |
| 2.3 | ✅ **Done v2.49.196.** Extract `_tab_skills.html` | `app/templates/_tab_skills.html` (new), `_mini_sheet_card.html` (uses include) | Pure refactor; PC behaviour byte-identical. Simplest extraction of the three — 18-skill grid in a single loop, no class-awareness, no `_is_caster` gate (every character gets a Skills tab). `SKILLS_LIST` constant moved inside the partial. |
| 2.3b | ✅ **Done v2.49.197.** Extract `_tab_features.html` (follow-on; not in original Phase 2 plan) | `app/templates/_tab_features.html` (new), `_mini_sheet_card.html` (uses include) | Pure refactor; PC behaviour byte-identical. Added for consistency so all four PC tab panels (Actions / Spells / Skills / Features) are includes before Phase 2.4's server-`tabs[]` work. Partial owns the `{% if _features_list %}` gate. |
| 2.4 | ✅ **Done v2.49.198.** `tabs=[...]` list drives both the strip and the panel render | `_mini_sheet_card.html` | Pure refactor; PC behaviour byte-identical. The partial now computes a single `_tabs_present` list of `{file, panel, label}` dicts and iterates it twice (strip + content). Caller override: pass `tabs=[...]` via `{% with %}` to replace the default computation — this is the integration point Phase 2.5 NPC code will use to inject a per-combatant tab list. Server-side projection of `tabs` to `tabletop_routes.py` deferred to Phase 2.5 (where NPCs need it). |
| 2.5 | Swap NPC body to the per-tab partials; delete `buildMonsterInitSheet` body section | `tabletop.html`, `tabletop_routes.py` | **Open question for this step:** the NPC mini-sheet is rendered entirely client-side today (`buildMonsterInitSheet` returns an HTML string at `renderBattle()` time). To consume Jinja partials it needs either (a) per-TokenTemplate server pre-render at page-load, hoisted into the init-card slot, with client-side HP / charge patching per combatant after hoist — same pattern as the PC `#char-detail-{id}` hoist; or (b) a new per-combatant render endpoint (`GET /api/combatant/{id}/card`) hit on-demand by `renderBattle()`. Path (a) is simpler — no new endpoint, same pattern as PCs — but requires the per-combatant patch step. This decision lands with the 2.5 commit; until then 2.1-2.4 work as pure refactors on the PC side. |
| 2.6 | ✅ **Done v2.49.200 (PC-only; NPC coverage waits for 2.5).** Harness test: every demo PC renders all four per-tab partials without throwing | `tests/harness/test_mini_sheet_partials.py` (new — 6 tests) | Loads `GET /campaign/1` + asserts all 12 PCs' `.mini-sheet` blocks present; spot-checks Zara (full caster) renders all four tab buttons in the documented order, Pip (Rogue) renders Actions + 18-skill Skills grid, Zara renders Spells with slot pips, ≥1 PC renders Features. NPC coverage deferred — `buildMonsterInitSheet` is still the NPC render path; Phase 2.5's body swap will replace the JS renderer with the partial + this test expands to include the 6 demo NPCs at that time. |

### Phase 3 — Cleanup (post-B)

- Delete `buildMonsterInitSheet` entirely.
- Move `.mini-spell-tag` CSS from `tabletop.html` inline `<style>` to `style.css` for shared use.
- Update the [PC vs NPC combat systems audit](/wiki/pc-vs-npc-systems) to remove the "two renderers" entry from the data-model section.
- Update the [Battle & Characters tab sheets visual guide](/wiki/battle-character-sheets-guide) PC-vs-NPC table to reflect single-renderer reality.

---

## Risks + mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| User reverts to v2.3.34 stance: "NPC view feels loose now" | Medium (we already learned this lesson) | Density-tightening CSS class `.mini-sheet--monster` applied to the partial when `is_monster` is true; tightens padding / gap. Tested visually with the GM on the demo before locking in. |
| Per-combatant tab state in localStorage (`vtt_minitab_<id>`) breaks during the refactor | Low | Validation allowlist already pattern (v2.49.175 added `'spells'`); just keep updating. |
| Existing PC harness tests pass but visual regressions slip | Medium | Add a Playwright-style smoke (Phase 1.4 / 2.6) that snapshots the chrome output. |
| Removing `buildMonsterInitSheet` breaks GM-only features (e.g., the action-charge ↻ recharge button) | Medium | Phase 1.3 explicitly inventories every JS-only NPC affordance and ports each to the partial before deletion. |
| The "GM seeds NPC HP via the init-card admin row" pattern conflicts with the new in-mini-sheet HP bar | Low | The admin row above the mini-sheet (init / HP / × inputs) stays — the in-mini-sheet HP bar is read-only display. Already the v2.49.183 behavior. |

---

## Out of scope

- **Full character sheet** (`sheet_dnd5e.html`) is unaffected. This plan only touches the init-tracker mini-sheet.
- **The `/character/<id>/sheet` page** keeps its own rendering — that's the long-form view, not the at-a-glance view.
- **PC vs NPC server divergence** (no `/cast_spell` for NPCs, no spell slots for NPCs, etc.) is documented in the [PC vs NPC audit](/wiki/pc-vs-npc-systems) and out of scope for this UI plan.

---

## Open questions

1. **Density class for NPC mode in Mockup B** — do we apply a `.mini-sheet--monster` modifier class for tighter padding, or trust the partial to compose well without?
2. **Charge tracker location** — Phase 2 needs to decide whether `action.charges_max` rendering belongs in `_tab_actions.html` (every action checks for it) or in a separate `_action_row.html` sub-partial.
3. **NPC concentration sigil** — PCs get the 🧿 sigil in the header when concentrating. Should NPCs get the same (per the v2.49.167 audit, NPC concentration tracking is filed as tech debt)?
4. **GM-only affordances** — the ↻ recharge button and the `×` remove button are GM-only. Should they live on the chrome (visible to GMs only) or on the per-action row?
5. **Pillification (aesthetic only)** — adopt rounder corners + filled-pill active tab? Two variants explored in [the mockups page Pillified section](/wiki/unified-mini-sheet-mockups#pillified): `pillified-soft` (12 px) and `pillified` (999 px). Pillification is orthogonal to the structural choice (A/B/C) — pick whichever structural mockup wins, then apply or skip the pill modifier class. Trade-off: pillification reads as friendlier / chip-stack-like; the squared corners read as denser / more spreadsheet-like. Active-tab pattern also changes (underline → filled background) in both pill variants because underlines look awkward next to round chips.

---

## Definition of done

- One mini-sheet renderer for both PC and NPC combatants in both Battle and Characters tabs.
- `buildMonsterInitSheet` deleted.
- Density of the NPC mini-sheet matches the current v2.49.183+ stat-block compactness — no looser.
- Header + HP bar + tab strip + chips render identically across PC and NPC.
- All existing harness tests (35+ in attack + npc_attack + wiki suites) pass without modification.
- New harness test (Phase 1.4) snapshots the chrome markup for both surfaces.
- Visual guide ([battle-character-sheets-guide.html](/wiki/battle-character-sheets-guide)) PC-vs-NPC table reduced to a single "rendered through the unified partial" line.
