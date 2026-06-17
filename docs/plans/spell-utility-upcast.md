# Spell utility-upcast

> **Status:** ✅ **CLOSED** as of v2.404.9 (2026-06-17). All 9 in-scope spells shipped across 9 sequential PATCH commits (v2.404.1 → v2.404.9). Two related substrate facts proven; one helper introduced.

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

## References

- v2.380.0 commit (Bless cap+upcast substrate)
- v2.381.0 commit (generalized `_SPELL_TARGET_CAPS`)
- v2.97.31 (no-save buff install via `_SPELL_BUFF_MAP`)
- v2.32.0 (save-or-suck condition install via `_SPELL_CONDITION_MAP`)
- v2.404.1 → v2.404.9 commits (this arc)
- [`docs/plans/spell-validation-suite.md`](spell-validation-suite.md) (the broader spell-test umbrella; Phase 5 complete)
- [`docs/plans/spell-upcasting.md`](spell-upcasting.md) (the upcasting plan; dice scaling shipped, target scaling closed by this arc)
