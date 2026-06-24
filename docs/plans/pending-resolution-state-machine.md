# Pending-Resolution State Machine — Design Plan

**Status:** 🔥 IN PROGRESS — Phase 0 (plan) v2.610.1; Phase 1 (extract
`_resolve_save_failure`) v2.610.2; **Phase 2 (Silvery Barbs re-resolves the
save-or-suck condition on a reroll pass→fail flip) shipped v2.611.0.** Phase 3
(save-for-half damage flips + attack re-resolution) is the remaining future
work.

This is the single biggest remaining item in the
[reactions-automation](reactions-automation.md) v3 backlog. The AC-bump
auto-negation family (Shield / Defensive Duelist / Form of the Beast Tail /
Combat Inspiration / NPC Parry) and the d20-reroll *display* family (Lucky,
Silvery Barbs) all ship — but two of them still **GM-narrate the
consequence**:

- **Lucky** auto-heals the attacker's damage on a reroll-miss (self-contained
  — done).
- **Silvery Barbs** (v2.610.0) auto-rolls the forced reroll and reports a
  pass→fail flip, but **applying** the now-failed save's effect (install the
  spell's condition, or convert save-for-half to full damage) is GM-narrated.

The reason is structural: when a save is resolved through
`POST /api/campaign/{cid}/roll_request/{id}/respond`, the **save-or-suck
failure resolution** (install the matching condition + run every immunity
gate — Aura of Devotion, Mindless Rage, PFE&G, Heroism, legendary-resistance
deferral) is a **~200-line inline block with multiple early HTTP returns**, not
a reusable function. Nothing else can re-invoke it. The pending-resolution
machine makes that resolution **callable and replayable** so a reaction that
flips an outcome can re-run it.

## Goal

A reaction that retroactively changes a committed d20 outcome (Silvery Barbs
flipping a save pass→fail; later: a reroll flipping an attack hit↔miss) should
**re-resolve the downstream effect**, not just announce the flip. The first
concrete payoff is Silvery Barbs **actually installing the spell's condition**
when its reroll makes the target fail.

## Substrate (verified)

- **`_save_request_context: dict[int, dict]`** (`tabletop_routes.py`) — keyed by
  `roll_request.id`, stashed by `/cast_spell` (and feature saves) at
  prompt-creation time. Holds `spell_slug` / `condition_buff` /
  `target_character_id` / `caster_char_id` / `campaign_id` / `ts`. TTL-purged,
  **not** popped on a normal resolve, so it's still present for a reaction that
  fires immediately after.
- **The failure block** (`/respond`, ~`tabletop_routes.py:22106+`) — reads that
  ctx, and on `not _save_passed_final` resolves the condition via
  `_SPELL_CONDITION_MAP` / `ctx["condition_buff"]`, gated by the immunity
  checks, then `_install_buff` + broadcast + `_log_damage_entry` (for Undo).
  Multiple `return {...}` HTTP responses are interleaved with the gates.
- **The `save_resolved` reaction context** (v2.610.0) already carries the
  save's `save_natural` + `save_bonus`; it does **not** yet carry the
  `roll_request.id` — Phase 2 needs that to find the ctx.

## Phases (one commit each)

### Phase 0 — Plan doc ✅ (this commit)

This document, surfaced through `/wiki`.

### Phase 1 — Extract `_resolve_save_failure(...)` (pure refactor)

Lift the save-or-suck failure block out of `/respond` into a reusable
coroutine:

```
async def _resolve_save_failure(db, campaign_id, roll_req, ctx, *, saver_total)
    -> dict   # {"auto_buff_installed": str, "immunity": str | None, ...}
```

- Move the condition-resolution + every immunity gate + `_install_buff` +
  logging into the helper; it returns an **outcome dict** (never an HTTP
  response). `/respond` calls it and adapts the outcome into its existing
  response shape — **no behavior change**.
- Safety net: the existing harness suite already covers this path heavily
  (`test_npc_archmage_hold_person`, `test_npc_cast_npc_target_install`,
  `test_cast_confusion_npc`, `test_menacing_attack`, the immunity tests:
  `test_buff_save_advantage`, `test_heroism_frightened_immunity`,
  `test_pfeag_condition_immunity`, …). Phase 1 ships **green against all of
  them with zero new behavior** — the refactor is done when they pass
  unchanged.

### Phase 2 — Silvery Barbs re-resolves the save

- Plumb `roll_request.id` (`req_id`) into the `save_resolved` reaction context.
- In the `cast-silvery-barbs` dispatch, when the auto-rolled reroll flips the
  verdict **pass→fail** (`new_save_total < dc`), look up
  `_save_request_context[req_id]` and call `_resolve_save_failure(...)` with the
  new (failed) total. The spell's condition now installs (subject to the same
  immunity gates) — Silvery Barbs becomes a real save-or-suck enabler instead
  of a GM-narrated prompt.
- Harness: extend the SB test so a deterministic pass→fail flip (high DC, a
  forced-low reroll fixture) installs the condition on the target.

### Phase 3 — Generalize (future)

- **Save-for-half damage flips** — a reroll-fail on a damage save applies the
  withheld half (needs the cast's damage stashed alongside the condition ctx).
- **Attack hit↔miss re-resolution beyond the heal-back** — recompute riders /
  on-hit effects, not just restore HP.
- **A true "pending" window** — hold the resolution un-committed for a short
  reaction window instead of resolve-then-replay. Only pursue if replay proves
  insufficient; replay is simpler and covers the reaction cases we have.

## Out of scope

- Rewriting the whole attack/save pipeline around an event-sourced pending
  log. The replay approach (re-invoke the resolver with a new result) covers
  every reaction in the current backlog without that.
- Multi-reaction ordering (two reactions on one roll) — single-reaction replay
  first.

## Cross-references

- [`reactions-automation.md`](reactions-automation.md) — the parent arc.
- `tabletop_routes.py` — `_save_request_context`, the `/respond` failure block,
  the `cast-silvery-barbs` dispatch, the `save_resolved` emit.
