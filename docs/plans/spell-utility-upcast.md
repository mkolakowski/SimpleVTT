# Spell utility-upcast

> **Status (target-scaling):** ✅ **CLOSED** as of v2.404.9 (2026-06-17). All 9 in-scope target-scaling spells shipped across 9 sequential PATCH commits (v2.404.1 → v2.404.9). Two related substrate facts proven; one helper introduced.
>
> **Status (duration-scaling):** ✅ **PHASE 1 CLOSED** as of v2.408.0 (2026-06-17). Substrate (`_SPELL_DURATION_MAP` + `_spell_duration_rounds_for_slot()` helper) + Hunter's Mark retrofit (v2.405.0) + Hex retrofit (v2.405.1) + Bestow Curse retrofit (v2.405.2, first `"permanent"` marker) + Geas (v2.406.0, first NEW endpoint + day/year markers) + Mass Suggestion (v2.407.0, endpoint-build) + Modify Memory (v2.408.0, final endpoint-build) shipped. **All six in-scope duration-scaling spells are live on the substrate.** See the [Phase 1 section](#phase-1--duration-scaling-substrate-v24050) below.
>
> **Status (AoE-radius scaling):** ✅ **PHASE 2 CLOSED** as of v2.413.0 (2026-06-17). Substrate (`_SPELL_AOE_MAP` + `_spell_aoe_for_slot()` helper) + Fog Cloud (v2.409.0, `/cast_fog_cloud`) + Confusion (v2.410.0, `/cast_confusion`) + Create or Destroy Water (v2.411.0, first cube-edge, `/cast_create_or_destroy_water`) + Creation (v2.412.0, second cube-edge, `/cast_creation`) + Private Sanctum (v2.413.0, third cube-edge, largest increment, `/cast_private_sanctum`) shipped. **All five in-scope AoE-radius scalers are live on the substrate.** See the [Phase 2 section](#phase-2--aoe-radius-scaling-substrate-v24090) below.
>
> **Status (rider/bonus scaling):** 🟠 **PHASE 4 OPEN** as of v2.421.0 (2026-06-17). New family — scales a flat numeric *rider* a spell grants its target (an attack/damage bonus, a temp-HP bump) as the cast slot climbs. Tier-walk substrate (`_SPELL_BONUS_MAP` + `_spell_bonus_for_slot()`): **Magic Weapon** (v2.421.0) + **Elemental Weapon** (v2.422.0). Linear-additive sibling substrate (`_SPELL_BONUS_ADDITIVE_MAP` + `_spell_bonus_additive_for_slot()`): **False Life** (v2.423.0, `step_size: 1` implicit) + **Aid** (v2.432.0 — refactor of the bespoke v2.371.0 inline scaling) + **Spiritual Weapon** (v2.433.0 — opens the **step-N additive** sub-shape via the new `step_size: 2` field; refactor of the v2.99.438 inline scaling). 5 consumers shipped end-to-end across the three sub-shapes (tier-walk / step-1 additive / step-N additive). See the [Phase 4 section](#phase-4--riderbonus-scaling-substrate-v24210) below.
>
> **Status (summon-count scaling):** ✅ **PHASE 3 COMPLETE** as of v2.420.0 (2026-06-17). Multiplier substrate (`_SPELL_SUMMON_MAP` + `_spell_summon_multiplier_for_slot()`): Conjure Animals retrofit (v2.414.0, ×1/×2/×3/×4) + Conjure Woodland Beings (v2.415.0, `/cast_conjure_woodland_beings` + `fey-spirit` template) + Conjure Minor Elementals (v2.416.0, `/cast_conjure_minor_elementals` + `elemental-spirit` template; Druid/Wizard gate) — **count-multiplier family complete**. Additive substrate (`_SPELL_SUMMON_ADDITIVE_MAP` + `_spell_summon_additive_for_slot()`): Animate Dead (v2.417.0, `/cast_animate_dead` + `undead-servant` template; 1 + 2/slot above 3rd) — **count-additive family complete**. CR-increase substrate — linear (`_SPELL_SUMMON_CR_MAP` + `_spell_summon_cr_for_slot()`): Conjure Elemental (v2.418.0, `/cast_conjure_elemental`; CR 5 base +1/slot above 5th) + Conjure Fey (v2.419.0, `/cast_conjure_fey`; CR 6 base +1/slot above 6th, Druid/Warlock gate, reuses `fey-spirit`) — and tier-walk (`_SPELL_SUMMON_CR_TIER_MAP` + `_spell_summon_cr_tier_for_slot()`): Conjure Celestial (v2.420.0, `/cast_conjure_celestial` + `celestial-spirit` template; CR 4 at L7–8, CR 5 at L9, Cleric gate) — **CR-increase family complete**. All three summon-scaling families are shipped. See the [Phase 3 section](#phase-3--summon-count-scaling-substrate-v24140) below.

## What this plan covered

The **v2.404.x spell utility-upcast arc** closed the multi-target cap + per-slot upcast scaling for 9 target-scaling utility spells across the SRD. These are RAW spells that follow the pattern *"You target one creature. At higher levels, target one additional creature per slot above N."* — Bless / Aid / Mass Healing Word / Mass Cure Wounds were already wired; this arc extended the substrate to the remaining 9 in scope.

The arc was framed after closing the v2.403.x magic-items-automation Phase 9.2 / 9.3 work and explicitly **not** to introduce new substrate — every commit reused existing v2.380.0 / v2.381.0 dispatch paths.

## The 9 commits

| # | Version | Spell | Substrate dict | Shape |
|---|---------|-------|----------------|-------|
| 1 | v2.404.1 "The Hidden Hand" | Invisibility | `_SPELL_BUFF_MAP` | new entry (L2 + 1/slot) |
| 2 | v2.404.2 "The Borrowed Sky" | Fly | `_SPELL_BUFF_MAP` | new entry (L3 + 1/slot) |
| 3 | v2.404.3 "The Menagerie's Touch" | Enhance Ability | `_SPELL_BUFF_MAP` | new entry (L2 + 1/slot) |
| 4 | v2.404.4 "The Hour's Stride" | Longstrider | `_SPELL_BUFF_MAP` | extended existing entry (L1 + 1/slot) |
| 5 | v2.404.5 "The Whispered Bond" | Charm Person | `_SPELL_TARGET_CAPS` | pure data drop (L1 + 1/slot) |
| 6 | v2.404.6 "The Shared Cap" | Bane | `_SPELL_TARGET_CAPS` + helper | substrate-consolidation refactor |
| 7 | v2.404.7 "The Single Word" | Command | `_SPELL_CONDITION_MAP` + caps | first condition-install ship (L1 + 1/slot) |
| 8 | v2.404.8 "The Beast's Trust" | Animal Friendship | both | condition-install ship (L1 + 1/slot) |
| 9 | v2.404.9 "The Stolen Sense" | Blindness/Deafness | both | arc-closer (L2 + 1/slot) |

**Tests:** 32 new harness tests across 8 new files. The Bane refactor was behavior-preserving (no new test) — verified by the existing 8 `test_cast_bane.py` tests passing unchanged.

## Substrate facts proven

The arc proved three substrate facts that were known-in-theory but not exercised at this breadth:

### 1. `_SPELL_BUFF_MAP` is sufficient for any no-save buff-install spell

The v2.380.0 Bless work added `max_targets` / `base_level` / `extra_targets_per_slot_above_base` to entries. The cap reader at `app/routes/tabletop_routes.py:22460` enforces the cap before the buff-install loop runs. Any new entry with these three fields gets cap enforcement for free.

**Proven across:** Invisibility (L2 base), Fly (L3 base), Enhance Ability (L2 base), Longstrider (L1 base + no concentration).

### 2. `_SPELL_TARGET_CAPS` is the generalized substrate for non-buff-install caps

The v2.381.0 comment described `_SPELL_TARGET_CAPS` as "the parallel path for spells that don't go through the buff-install branch." The reader at `app/routes/tabletop_routes.py:19877` is dispatch-agnostic — it fires regardless of whether the spell installs a buff, deals damage, or routes through a save-or-suck condition map. **Mass Healing Word + Mass Cure Wounds were the only consumers before this arc.**

**Proven across:** Charm Person (data-only opt-in), Bane (consolidation from inline math via a new helper), Command / Animal Friendship / Blindness/Deafness (new condition-install ships).

### 3. The save-or-suck dispatch at `/cast_spell` is auto-wired by `_SPELL_CONDITION_MAP`

Adding a new entry to `_SPELL_CONDITION_MAP` is **all the engine code needed** to make a save-or-suck spell install a condition on a failed save. The per-target dispatch loop at `app/routes/tabletop_routes.py:22181` reads `_SPELL_CONDITION_MAP.get(spell_slug)` and installs the templated buff. No new endpoint code is required for Command / Animal Friendship / Blindness/Deafness — their SRD JSONs already carry `save_ability`, and the existing dispatch picks them up the moment the condition map gains an entry.

Caveat: **NPC-only in v1.** The PC save-or-suck path is filed (the comment at line 22168 says: *"NPC-only for v1; PC save-or-suck is filed (the PC's owner rolls the save in their UI — we'd need a roll-response hook to know whether they passed and install accordingly)"*). The cap enforcement fires before saves regardless, so cap-rejection tests work with PC targets.

## The v2.404.6 helper

The Bane refactor introduced **one new helper function**:

```python
def _spell_target_cap_for_slot(
    spell_slug: str, slot_level: int, default_base: int = 1,
) -> int:
    """Reads `_SPELL_TARGET_CAPS[spell_slug]` and returns
    max_targets + max(0, slot_level - base_level) * extras, or 0 if
    no entry exists."""
```

This helper lets bespoke endpoints (`/cast_bane`, `/cast_hold_monster`, etc.) read the same source of truth as the `/cast_spell` cap reader without buying into the generic JSONResponse shape. Bespoke endpoints often carry extra response fields (Bane's `slot_level` in the 400 body) that don't generalize to the shared reader.

**Filed for future commits:**

- The `/cast_spell` reader (line ~19877) still has the cap-arithmetic inlined. Refactoring it to call the helper would complete the consolidation but touches the dispatch hot path — a careful no-op refactor with broader test coverage than this arc's scope.
- Other bespoke endpoints (`/cast_hold_monster`, `/cast_polymorph`, `/cast_compulsion`, etc.) could adopt the helper to share the same single source of truth. Filed as future polish.

## Filed follow-ups

Recorded so future spell-utility work doesn't have to re-derive the gaps:

- **PC save-or-suck for condition-install spells.** v1 only installs the condition on NPC failed saves. PCs need a roll-response hook (filed since v2.32.0). Affects Command / Animal Friendship / Blindness/Deafness / Charm Person / Hold Person — all of them, not just the v2.404.x arc.
- **Blindness/Deafness deafened-variant install.** v1 defaults to installing Blinded. Caster-picker UI would thread a per-cast `body.condition_choice` field through `/cast_spell` to the install branch.
- **Command word picker.** v1 narrates the 6 RAW commands via the buff effects list. Future work could thread `effects.command_word` through as a per-cast field.
- **Suggestion target scaling.** RAW Suggestion doesn't scale targets (single-target only). No engine work needed; documented here so a future contributor doesn't try to wire it.
- **Mass Suggestion duration scaling.** RAW: 24 h / 10 d / 30 d / year+day at L6 / L7 / L8 / L9. Duration substrate doesn't yet exist — the `duration_rounds` field is static at install time. Filed as a separate substrate ship.
- **Bane substrate consolidation.** The v2.404.6 commit moved Bane's cap to `_SPELL_TARGET_CAPS` and added the helper. The same shape could be applied to `/cast_hold_monster` (currently hardcodes its own cap math), `/cast_polymorph`, etc.

## Why the arc closed cleanly

Three reasons the arc shipped 9 commits in one session without architectural surprises:

1. **Substrate already existed.** v2.380.0 + v2.381.0 + v2.97.x had built the cap-enforcement readers, the buff-install dispatch, and the save-or-suck condition-install path. The arc was data + small refactors, not engine work.
2. **The audit was loose.** The pre-arc estimate was "~70 utility spells need upcast fields." Auditing the actual SRD revealed ~16 target-scaling spells; 7 were already wired bespokely; 9 were in scope. Re-scoping early prevented over-committing.
3. **Every commit was the same shape.** New entry in 1-2 dicts + spell-list demo seed + 4-test harness file + bump + CHANGELOG. The repeated shape kept commits at ~250-300 lines and avoided context drift.

---

## Phase 1 — duration-scaling substrate (v2.405.0)

After the target-scaling arc closed, the next substrate gap on the engine-shaped utility-spell tail is **duration scaling** — RAW spells whose duration grows per slot rather than (or in addition to) target count. Pre-v2.405.0 every such spell hardcoded its per-slot duration ladder at the cast endpoint; the cleanest example was Hunter's Mark with three tiers inlined as an `if/elif` block at `app/routes/tabletop_routes.py:81517-81525`.

### Substrate ship (v2.405.0)

Two pieces added near `_SPELL_TARGET_CAPS` to mirror the v2.404.6 cap-substrate shape:

- **`_SPELL_DURATION_MAP`** — keyed by spell slug; values carry `{base_level, tiers: [(max_slot_inclusive, rounds_or_marker), ...]}`. The first tier whose `max_slot_inclusive` ≥ the cast's slot wins. Marker strings (`"permanent"`, `"until_long_rest"`, etc.) flag non-numeric durations.
- **`_spell_duration_rounds_for_slot(spell_slug, slot_level, default_rounds=0)`** — pure-function lookup. Returns the matching tier's value or the default. Used by both `/cast_spell` (generic dispatcher) and bespoke endpoints.

Hunter's Mark is the first consumer:

```python
"hunters-mark": {
    "base_level": 1,
    "tiers": [
        (2, 600),     # L1-L2: 1 hour concentration
        (4, 4800),    # L3-L4: 8 hours
        (9, 14400),   # L5+:   24 hours
    ],
},
```

The `/cast_hunters_mark` endpoint reads the substrate via the helper and derives the display `duration_label` ("1h" / "8h" / "24h") from the substrate-returned round count. Engine behavior is preserved end-to-end (same display cap, same RAW duration tiers).

### Tests (v2.405.0)

`tests/harness/test_hunters_mark_duration_scaling.py` ships 3 tests — L1 / L3 / L5 casts each assert the installed buff's `duration_label` lands the right tier. Substrate routing proven across all three RAW tiers.

### Backlog (Phase 1 follow-on spells, ~11 spells)

Each ships as a registry drop-in + retrofit + harness. Same shape across all of them.

| Spell | Base level | RAW tier ladder | Notes |
|---|---|---|---|
| Hex | L1 | L1-L2 → 1h, L3-L4 → 8h, L5+ → 24h | ✅ shipped v2.405.1 ("The Second Curse"). Second consumer of the substrate — identical ladder to Hunter's Mark, retrofitted by adding one `"hex"` registry entry + a `_spell_duration_rounds_for_slot()` call at the cast endpoint. Harness: `tests/harness/test_hex_duration_scaling.py`. |
| Bestow Curse | L3 | L3 → 1 min, L4 → 10 min, L5 → 8h, L7 → 24h, L9 → permanent (RAW PHB p.218) | ✅ shipped v2.405.2 ("The Lasting Curse"). First consumer of the `"permanent"` marker. `/cast_bestow_curse` reads the substrate + branches on the marker to derive a `duration_label`. Harness: `tests/harness/test_bestow_curse_duration_scaling.py` (5 tests, one per tier). |
| Geas | L5 | L5 → 30 days, L7 → 1 year, L9 → permanent | ✅ shipped v2.406.0 ("The Binding Word"). **NOT a retrofit** — Geas had no cast endpoint (catalog-only), so this was a new `/cast_geas` MINOR endpoint built on the substrate from the start. First consumer of the day/year markers (`"30d"`, `"1y"`); reuses `"permanent"`. Harness: `tests/harness/test_cast_geas.py` (7 tests). |
| Mass Suggestion | L6 | L6 → 24h, L7 → 10d, L8 → 30d, L9 → 1y+1d | ✅ shipped v2.407.0 ("The Crowd's Whisper"). New `/cast_mass_suggestion` endpoint-build (catalog-only before). Four calendar markers, one per slot level. Harness: `tests/harness/test_cast_mass_suggestion.py` (8 tests). |
| Modify Memory | L5 | L5 → 10 min, L6 → 1h, L7 → 24h, L8 → 7d, L9 → permanent | ✅ shipped v2.408.0 ("The Rewritten Page"). New `/cast_modify_memory` endpoint-build (catalog-only before). Final Phase 1 spell — five markers, one per slot level, reusing `"permanent"` at L9. Concentration, single target, 30 ft. Harness: `tests/harness/test_cast_modify_memory.py` (9 tests). |
| Magic Weapon | L2 | L2-L3 → 1h, L4+ → 1h with attack-bonus increase (bonus scales, duration fixed) | ✅ shipped v2.421.0 ("The Tempered Edge") as the **first Phase 4 rider/bonus-scaling consumer** — see the [Phase 4 section](#phase-4--riderbonus-scaling-substrate-v24210). The bonus (+1 @L2–3, +2 @L4–5, +3 @L6+) scales via `_SPELL_BONUS_MAP`, not duration. |
| Heroes' Feast | L6 | Fixed 24h RAW; no per-slot scaling | Filed: no substrate consumer needed; documented to prevent rework. |
| Otiluke's Resilient Sphere | L4 | Fixed 1 min RAW (concentration); no per-slot scaling | Filed: AoE-radius scaling lands in Phase 2 instead. |
| Tiny Hut | L3 (ritual) | Fixed 8h RAW; no per-slot scaling | Filed: no substrate consumer. |
| Drawmij's Instant Summons | L6 | Fixed (instantaneous summon) | Filed: not a duration spell — moved out of scope. |
| Glyph of Warding | L3 | Fixed (until triggered) | Filed: trigger-state substrate (out of Phase 1 scope). |

**Real Phase 1 scope (revised):** Hunter's Mark ✅ + Hex ✅ + Bestow Curse ✅ + Geas ✅ + Mass Suggestion ✅ + Modify Memory ✅ = **6 spells** with genuine duration scaling, all shipped. The others get filed out of scope (no per-slot duration ladder) or moved to Phase 2/4. **Scope note:** only the first three were true one-line retrofits (they had endpoints with inline ladders). Geas, Mass Suggestion, and Modify Memory were catalog-only — making them substrate consumers meant *building* a `/cast_<spell>` endpoint (MINOR), as Geas demonstrated in v2.406.0. **Phase 1 closed at v2.408.0** with the Modify Memory endpoint-build.

### Markers (sentinel strings the helper returns)

- `"permanent"` — duration-until-dispelled. Engine clamps `duration_rounds` to the display cap; the buff's `duration_label` flips to a "perm" tag.
- `"30d"`, `"1y+1d"` — long durations the engine doesn't track minute-by-minute. Same display-cap behavior; the GM resolves expiry at the table.

The helper returns the raw marker string; the caller decides how to render it. Hunter's Mark retrofit demonstrates the numeric path (integer rounds → `duration_label` mapping); marker-string callers will add their own branches.

---

## Phase 2 — AoE-radius scaling substrate (v2.409.0)

A small set of SRD spells scale their **area** on upcast rather than their duration or target count. The growth is always linear: a fixed step per slot level above the spell's base level. Phase 2 introduces a dedicated substrate for that math, structurally parallel to the Phase 1 duration substrate.

### Substrate

- **`_SPELL_AOE_MAP`** — keyed by spell slug; values carry `{base_level, base_ft, increment_ft, shape}`. `shape` is descriptive (`"sphere-radius"` / `"cube-edge"`) so a caller can render the right template; the scaling math is identical regardless of shape.
- **`_spell_aoe_for_slot(spell_slug, slot_level, default_ft=0)`** — pure-function lookup. Returns `base_ft + max(0, slot_level − base_level) × increment_ft`, or `default_ft` when the slug has no entry. Single source of truth for per-slot area math.

Fog Cloud is the first consumer:

```python
"fog-cloud": {
    "base_level": 1,
    "base_ft": 20,         # 20-ft-radius sphere at L1
    "increment_ft": 20,    # +20 ft per slot above L1
    "shape": "sphere-radius",
},
```

`/cast_fog_cloud` (a new endpoint-build, since Fog Cloud was catalog-only) reads the substrate via the helper and surfaces the scaled `radius_ft` on the response + the `feature_used` broadcast. v1 ships the spell-side audit; placing the actual fog template on the battle map is filed.

### Tests (v2.409.0)

`tests/harness/test_cast_fog_cloud.py` ships 8 tests — L1/L2/L5/L9 casts assert the right `radius_ft` (20/40/100/180) + 4 error paths (missing character_id, slot < 1, wrong class, spell not known).

### Backlog (Phase 2 follow-on spells)

Each ships as a substrate drop-in + endpoint-build + harness, same shape across all of them (all five candidates are catalog-only).

| Spell | Base level | RAW area ladder | Notes |
|---|---|---|---|
| Fog Cloud | L1 | 20-ft radius, +20 ft per slot above 1st | ✅ shipped v2.409.0 ("The Rolling Bank"). First consumer of `_SPELL_AOE_MAP`; sphere-radius shape. Harness: `tests/harness/test_cast_fog_cloud.py` (8 tests). |
| Confusion | L4 | 10-ft radius, +5 ft per slot above 4th | ✅ shipped v2.410.0 ("The Widening Daze"). Second sphere-radius consumer (new `/cast_confusion` endpoint). Also a WIS-save condition spell; the AoE substrate covers the radius only (per-target save + behavior table filed). Harness: `tests/harness/test_cast_confusion.py` (8 tests). |
| Create or Destroy Water | L1 | 30-ft cube, +5 ft per slot above 1st (or +10 gal water) | ✅ shipped v2.411.0 ("The Rising Tide"). Third consumer + **first cube-edge shape** (new `/cast_create_or_destroy_water` endpoint, surfaces `cube_ft`). RAW base cube is 30 ft (the +10-gallon branch is a separate non-area scale, filed). Harness: `tests/harness/test_cast_create_or_destroy_water.py` (8 tests). |
| Creation | L5 | 5-ft cube, +5 ft per slot above 5th | ✅ shipped v2.412.0 ("The Shadow Forge"). Second cube-edge consumer (new `/cast_creation` endpoint, surfaces `cube_ft`). Harness: `tests/harness/test_cast_creation.py` (8 tests). |
| Private Sanctum | L4 | 100-ft cube, +100 ft per slot above 4th | ✅ shipped v2.413.0 ("The Warded Hold"). Fifth and final consumer + **third cube-edge shape** (new `/cast_private_sanctum` endpoint, surfaces `cube_ft`); largest increment in the substrate. v1 ships the cube audit; per-property security riders filed. Harness: `tests/harness/test_cast_private_sanctum.py` (8 tests). **Closes Phase 2.** |

---

## Phase 3 — summon-count scaling substrate (v2.414.0)

A family of SRD conjure spells scale the **number** (or **CR**) of summoned creatures on upcast rather than duration, area, or target count. Phase 3 introduces a dedicated substrate for the count math, structurally parallel to Phases 1 and 2. The family splits three ways:

- **Count-multiplier** — the chosen summoning option's base count is multiplied by a slot-dependent factor (Conjure Animals ×2/×3/×4; Conjure Woodland Beings + Conjure Minor Elementals ×2/×3).
- **Count-additive** — a fixed number of extra creatures per slot above base (Animate Dead, +2 undead per slot above 3rd).
- **CR-increase** — the count stays fixed at 1 but the summoned creature's challenge rating climbs with slot level (Conjure Elemental +1 CR/slot above 5th; Conjure Fey +1 CR/slot above 6th; Conjure Celestial CR 4 base → CR 5 @9th).

### Substrate

- **`_SPELL_SUMMON_MAP`** — keyed by spell slug; the count-multiplier entries carry `{base_level, tiers}` where `tiers` is a list of `(max_slot_inclusive, multiplier)` walked low→high (the same tier shape as `_SPELL_DURATION_MAP`). The additive and CR-increase families each got their own sibling map + helper rather than overloading this one (keeping each helper single-purpose).
- **`_spell_summon_multiplier_for_slot(spell_slug, slot_level, default_multiplier=1)`** — pure-function lookup. Returns the first tier's multiplier whose ceiling ≥ the cast's slot level (last-tier fallback above the table), or `default_multiplier` when the slug has no entry. Single source of truth for per-slot summon-count math.
- **`_SPELL_SUMMON_ADDITIVE_MAP`** + **`_spell_summon_additive_for_slot(spell_slug, slot_level, default_count=1)`** (v2.417.0) — sibling map for the count-additive family. Entries carry `{base_level, base_count, per_slot}`; the helper returns `base_count + per_slot × max(0, slot − base_level)` (linear, mirrors `_spell_aoe_for_slot`). First consumer: Animate Dead.
- **`_SPELL_SUMMON_CR_MAP`** + **`_spell_summon_cr_for_slot(spell_slug, slot_level, default_cr=0)`** (v2.418.0) — sibling map for the *linear* CR-increase family. Entries carry `{base_level, base_cr, per_slot}`; the helper returns `base_cr + per_slot × max(0, slot − base_level)`. Count stays fixed at 1; only the summoned creature's CR scales. Consumers: Conjure Elemental, Conjure Fey.
- **`_SPELL_SUMMON_CR_TIER_MAP`** + **`_spell_summon_cr_tier_for_slot(spell_slug, slot_level, default_cr=0)`** (v2.420.0) — sibling map for the *non-linear* CR-increase family (the linear `per_slot` can't express a CR that holds flat then jumps). Entries carry `{base_level, tiers}` where `tiers` is a list of `(max_slot_inclusive, cr)` walked low→high (last-tier fallback), the same shape as `_SPELL_SUMMON_MAP`. Consumer: Conjure Celestial (CR 4 at L7–8, CR 5 at L9).

Conjure Animals is the first consumer:

```python
"conjure-animals": {
    "base_level": 3,
    "tiers": [
        (4, 1),     # L3–L4: ×1 (base option count)
        (6, 2),     # L5–L6: twice as many
        (8, 3),     # L7–L8: three times as many
        (9, 4),     # L9: four times as many
    ],
},
```

`/cast_conjure_animals` already existed (v2.99.443, the first multi-summon); the v2.414.0 retrofit makes `count` the *base* summoning option and multiplies it by the slot-derived factor. A base-slot cast keeps the ×1 multiplier, so the retrofit is backward-compatible.

### Tests (v2.414.0)

`tests/harness/test_cast_conjure_animals.py` gains four tests — base-slot ×1 (L3), L5 doubles (base 2 → 4), L7 triples (base 2 → 6), L9 quadruples (base 1 → 4) — asserting `base_count`, `multiplier`, `slot_level`, `count`, and the summoned-combatant tally.

### Backlog (Phase 3 follow-on spells)

| Spell | Base level | RAW summon ladder | Family | Notes |
|---|---|---|---|---|
| Conjure Animals | L3 | ×2 @5th, ×3 @7th, ×4 @9th | count-multiplier | ✅ shipped v2.414.0 ("The Doubling Pack"). First consumer of `_SPELL_SUMMON_MAP`. Harness: `tests/harness/test_cast_conjure_animals.py`. |
| Conjure Woodland Beings | L4 | ×2 @6th, ×3 @8th | count-multiplier | ✅ shipped v2.415.0 ("The Sylvan Throng"). Second consumer of `_SPELL_SUMMON_MAP`; new `/cast_conjure_woodland_beings` endpoint + new `fey-spirit` companion template. Harness: `tests/harness/test_cast_conjure_woodland_beings.py`. |
| Conjure Minor Elementals | L4 | ×2 @6th, ×3 @8th | count-multiplier | ✅ shipped v2.416.0 ("The Elemental Host"). Third consumer + new `/cast_conjure_minor_elementals` endpoint + new `elemental-spirit` companion template. Druid **or Wizard** gate (the difference from Woodland Beings). Harness: `tests/harness/test_cast_conjure_minor_elementals.py` (7 tests). **Closes the count-multiplier family.** |
| Animate Dead | L3 | +2 undead per slot above 3rd | count-additive | ✅ shipped v2.417.0 ("The Risen Few"). First additive-family consumer: new sibling `_SPELL_SUMMON_ADDITIVE_MAP` + `_spell_summon_additive_for_slot()` helper + new `/cast_animate_dead` endpoint + new `undead-servant` companion template. Count fully slot-determined (no base-option `count`). Cleric / Wizard gate. Harness: `tests/harness/test_cast_animate_dead.py` (6 tests). **Opens the count-additive family.** |
| Conjure Elemental | L5 | CR +1 per slot above 5th | CR-increase | ✅ shipped v2.418.0 ("The Summoned Tempest"). First CR-increase consumer: new sibling `_SPELL_SUMMON_CR_MAP` + `_spell_summon_cr_for_slot()` helper + new `/cast_conjure_elemental` endpoint (reuses the `elemental-spirit` template). Count fixed at 1; CR slot-determined (CR 5 base, +1/slot). Druid / Wizard gate. Harness: `tests/harness/test_cast_conjure_elemental.py` (5 tests). **Opens the CR-increase family.** |
| Conjure Fey | L6 | CR +1 per slot above 6th | CR-increase | ✅ shipped v2.419.0 ("The Sixth-Circle Court"). Second CR-increase consumer: new `_SPELL_SUMMON_CR_MAP["conjure-fey"]` entry + new `/cast_conjure_fey` endpoint (reuses the `_spell_summon_cr_for_slot()` helper + `fey-spirit` template). Count fixed at 1; CR slot-determined (CR 6 base, +1/slot). Druid / Warlock gate. Harness: `tests/harness/test_cast_conjure_fey.py` (5 tests). |
| Conjure Celestial | L7 | CR 4 base → CR 5 @9th | CR-increase (tier-walk) | ✅ shipped v2.420.0 ("The Empyrean Summons"). Final Phase 3 consumer + the non-linear shape: new sibling `_SPELL_SUMMON_CR_TIER_MAP` + `_spell_summon_cr_tier_for_slot()` tier-walk helper + new `/cast_conjure_celestial` endpoint + new `celestial-spirit` companion template. CR 4 at L7–8, CR 5 at L9. Cleric gate. Harness: `tests/harness/test_cast_conjure_celestial.py` (4 tests). **Closes Phase 3.** |

---

## Phase 4 — rider/bonus scaling substrate (v2.421.0)

Where Phase 3 scaled *summons* (count or CR), Phase 4 scales a flat numeric **rider** a spell grants its target — an attack/damage bonus, a temp-HP bump — as the cast slot climbs. Two shapes have shipped, mirroring the two Phase 3 sub-families: a **tier-walk** bonus (plateaus at breakpoints) and a **linear-additive** bonus (a flat amount per slot, no plateau).

### Substrate

```python
# Tier-walk shape — plateaus at breakpoints (Magic Weapon, Elemental Weapon).
_SPELL_BONUS_MAP: dict[str, dict] = {
    "magic-weapon": {
        "base_level": 2,
        "tiers": [(3, 1), (5, 2), (9, 3)],   # +1 @L2-3, +2 @L4-5, +3 @L6+
    },
}


def _spell_bonus_for_slot(spell_slug, slot_level, default_bonus=0) -> int:
    """Walk the (max_slot_inclusive, bonus) tiers low→high; last-tier
    fallback above the table. Mirrors _spell_summon_cr_tier_for_slot."""


# Linear-additive shape — flat per-slot climb, no plateau (False Life).
_SPELL_BONUS_ADDITIVE_MAP: dict[str, dict] = {
    "false-life": {
        "base_level": 1,
        "base_bonus": 0,    # the 1d4+4 base is rolled separately
        "per_slot": 5,      # +5 temp HP per slot above 1st
    },
}


def _spell_bonus_additive_for_slot(spell_slug, slot_level, default_bonus=0):
    """base_bonus + max(0, slot − base_level) × per_slot. Mirrors
    _spell_summon_additive_for_slot."""
```

A weapon-buff consumer reads `_spell_bonus_for_slot(slug, slot_level)` and installs a buff carrying the scaled bonus as informational `effects` (the display-only convention from Bless's `bless_attack_bonus` — the buff records the number; the player adds it to their rolls). The buff install requires an active battle. A temp-HP consumer (False Life) reads `_spell_bonus_additive_for_slot()`, adds the per-slot bonus to a rolled base, and grants the total via `_grant_temp_hp` (RAW non-stacking) — no battle needed, the temp HP persists on the PC sheet.

### Tests (v2.421.0)

`tests/harness/test_cast_magic_weapon.py` (5 tests): L2 → +1, L4 → +2, L6 → +3 (each verified against the persisted buff `effects`), the Wizard-caster gate (Thalindra), and the 409 cannot_cast on Krieger (Barbarian).

### Backlog (Phase 4 follow-on spells)

| Spell | Base level | RAW rider ladder | Notes |
|---|---|---|---|
| Magic Weapon | L2 | +1 @L2–3, +2 @L4–5, +3 @L6+ (attack & damage) | ✅ shipped v2.421.0 ("The Tempered Edge"). First consumer: new `_SPELL_BONUS_MAP` + `_spell_bonus_for_slot()` tier-walk helper + new `/cast_magic_weapon` endpoint (Cleric/Wizard gate). Installs a 1-hour non-concentration buff with `weapon_attack_bonus` / `weapon_damage_bonus` effects. **Opens Phase 4.** |
| Elemental Weapon | L3 | +1/1d4 @L3–4, +2/2d4 @L5–6, +3/3d4 @L7+ (attack bonus + elemental damage die) | ✅ shipped v2.422.0 ("The Kindled Blade"). Second consumer — first to scale **two** riders off one tier value N (`+N` attack and `Nd4` damage). New `_SPELL_BONUS_MAP["elemental-weapon"]` entry + new `/cast_elemental_weapon` endpoint (Ranger/Paladin gate). **Concentration** (Magic Weapon isn't); carries a player-chosen element (acid/cold/fire/lightning/thunder). Buff effects: `weapon_attack_bonus` / `weapon_bonus_damage_dice` / `weapon_bonus_damage_type`. |
| False Life | L1 | +5 temp HP per slot above 1st (linear, no plateau) on top of a 1d4+4 base | ✅ shipped v2.423.0 ("The Borrowed Breath"). Third consumer — first **linear-additive** shape: new sibling `_SPELL_BONUS_ADDITIVE_MAP` + `_spell_bonus_additive_for_slot()` helper + new `/cast_false_life` endpoint (Sorcerer/Wizard gate). Grants **temp HP** directly via `_grant_temp_hp` (RAW non-stacking) rather than a buff effect; self-only, non-concentration, no battle needed. **Opens the linear-additive sub-shape.** |
| Aid | L2 | +5 HP at base L2, +5 HP per slot above 2nd (linear, no plateau) | ✅ refactored onto the substrate v2.432.0 ("The Aligned Boon"). Fourth Phase 4 consumer; first **refactor-style** ship — Aid's HP scaling shipped in v2.371.0 with a bespoke inline `max(5, 5 + 5 * max(0, slot - 2))` calculation at `/cast_spell`'s buff-install branch. v2.432.0 promotes Aid onto `_SPELL_BONUS_ADDITIVE_MAP` + `_spell_bonus_additive_for_slot()`, shrinking the inline branch from 6 lines to 1 helper call. No behavior change — the `base + (slot - base) * per` formula reproduces the v2.371.0 expression exactly. The 3 existing Aid harness tests (`test_cast_aid_upcast.py`) still pass without modification. |
| Spiritual Weapon | L2 | 1d8 at base L2, +1d8 per **two** slot levels above 2nd (step-2 additive, no plateau) | ✅ refactored + substrate generalization v2.433.0 ("The Floating Strike"). Fifth Phase 4 consumer; **opens the step-N additive sub-shape**. Adds a new `step_size` field to `_SPELL_BONUS_ADDITIVE_MAP` entries (default 1, preserving False Life / Aid behavior) so `_spell_bonus_additive_for_slot()` can compute `floor((slot - base) / step_size)` steps. Spiritual Weapon uses `step_size: 2` for the every-2-levels rhythm. Spiritual Weapon's damage scaling was wired in v2.99.438 with a bespoke inline `extra_dice = max(0, (slot - 2) // 2); n_dice = 1 + extra_dice` calculation at `/use_spiritual_weapon`; v2.433.0 replaces it with `_spell_bonus_additive_for_slot("spiritual-weapon", slot_level, default_bonus=1)`. The existing 2 dice-scaling tests (L2 = 1d8, L4 = 2d8) pass unchanged; a new L6 test (3d8 ceiling > 16+mod) exercises the third tier through the substrate. |

---

## References

- v2.380.0 commit (Bless cap+upcast substrate)
- v2.381.0 commit (generalized `_SPELL_TARGET_CAPS`)
- v2.97.31 (no-save buff install via `_SPELL_BUFF_MAP`)
- v2.32.0 (save-or-suck condition install via `_SPELL_CONDITION_MAP`)
- v2.404.1 → v2.404.9 commits (this arc)
- [`docs/plans/spell-validation-suite.md`](spell-validation-suite.md) (the broader spell-test umbrella; Phase 5 complete)
- [`docs/plans/spell-upcasting.md`](spell-upcasting.md) (the upcasting plan; dice scaling shipped, target scaling closed by this arc)
