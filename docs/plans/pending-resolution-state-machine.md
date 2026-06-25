# Pending-Resolution State Machine — Design Plan

**Status:** 🔥 IN PROGRESS — Phase 0 (plan) v2.610.1; Phase 1 (extract
`_resolve_save_failure`) v2.610.2; Phase 2 (Silvery Barbs re-resolves the
save-or-suck condition on a reroll pass→fail flip) v2.611.0; **Phase 3a
(Silvery Barbs applies the *withheld half* of a save-for-half AoE damage spell
on a reroll pass→fail flip, via `_resolve_save_for_half_flip`) shipped
v2.612.0.** The remaining Phase 3 work is attack hit↔miss re-resolution. A
v2.648.1 substrate analysis (see the Phase 3 section) splits it: the **damage
half is already done** (the Lucky / AC-bump hit→miss heal-back reverses Sneak
Attack / Hunter's Mark / Hex / Smite, since those fold into `damage_applied`),
and the **condition half is a dedicated arc** — weapon on-hit conditions ride a
deferred `weapon_hit_save` flow keyed on the save's cast_id (not the attack's
`attack_id`), so reverting them on a flip needs either logging that chain under
`attack_id` (Phase 3c, incremental) or the true held "pending" window (the
architectural lift). Not a quick slice — scope as its own arc.

This was the single biggest remaining item in the
[reactions-automation](reactions-automation.md) v3 backlog — **and the save
path is now closed.** The AC-bump auto-negation family (Shield / Defensive
Duelist / Form of the Beast Tail / Combat Inspiration / NPC Parry) and the
d20-reroll family (Lucky, Silvery Barbs) all ship, and the save **consequence**
is now re-resolved mechanically rather than GM-narrated:

- **Lucky** auto-heals the attacker's damage on a reroll-miss (self-contained
  — done).
- **Silvery Barbs** (v2.610.0 reroll display; **v2.611.0 + v2.612.0
  consequence**) auto-rolls the forced reroll AND, when it flips a save
  pass→fail, **applies the now-failed save's effect** — installs the spell's
  condition (`_resolve_save_failure`, Phase 2) or converts save-for-half to
  full damage (`_resolve_save_for_half_flip`, Phase 3a) — with every immunity
  gate intact.

The reason this needed a plan was structural: when a save is resolved through
`POST /api/campaign/{cid}/roll_request/{id}/respond`, the **save-or-suck
failure resolution** (install the matching condition + run every immunity
gate — Aura of Devotion, Mindless Rage, PFE&G, Heroism, legendary-resistance
deferral) *was* a ~200-line inline block with multiple early HTTP returns, not
a reusable function. Phase 1 (v2.610.2) **extracted it into the reusable
`_resolve_save_failure` coroutine** so a reaction that flips an outcome can
re-run it — which Phases 2 + 3a then did. **What remains is only the attack
hit↔miss re-resolution** (a reroll flipping an attack hit↔miss beyond the
Lucky heal-back) plus an optional true held "pending" window before the
outcome commits.

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

### Phase 3a — Save-for-half damage flips ✅ (v2.612.0)

A reroll-fail on an AoE save-for-half **damage** save now applies the withheld
half. On a *passed* AoE save the `/respond` handler stashes the rolled total +
applied half + `evasion_used` on `_save_request_context` (rather than popping
it); the `cast-silvery-barbs` dispatch calls `_resolve_save_for_half_flip`,
which applies the difference between the full-on-fail amount (rolled, or
rolled//2 with Evasion) and what already landed. Harness:
`test_silvery_barbs_applies_withheld_half_on_damage_flip`.

### Phase 3 — Attack hit↔miss re-resolution

**Substrate analysis (v2.648.1) — the work splits into a done half and a hard
half, so this is a dedicated arc, not a quick slice:**

- **Damage half — already done.** When a Lucky reroll (v2.609.0) or any
  AC-bump reaction (Shield / Defensive Duelist / Form of the Beast Tail /
  Combat Inspiration / NPC Parry, v2.600.0–v2.608.0) flips an attack
  **hit→miss**, the full `damage_applied` is healed back. Sneak Attack,
  Hunter's Mark, Hex, and Divine Smite are all folded into the attack's damage
  *total*, so healing `damage_applied` already reverses those riders — there's
  no separate "recompute the damage riders" work left. The `attack_targeted`
  prompt context already carries everything a downstream re-resolution needs:
  `attack_id`, `damage_applied`, `attack_natural`, `attack_bonus`, `target_ac`,
  `is_crit`.
- **Condition half — structurally harder (the real Phase 3 work).** Weapon
  **on-hit condition installs** don't ride the attack's `attack_id`: they go
  through the `weapon_hit_save` rider path (`_fire_weapon_hit_saves`,
  v2.99.408), which prompts the *target's* save via a RollRequest and installs
  the condition on a fail — a **deferred, separate flow keyed on the save's own
  cast_id**. By the time a defender's Lucky reroll flips the attack to a miss,
  that on-hit save may already have been prompted or resolved. The attack-undo
  infra (`_snapshot_target_buffs` / `_restore_target_buffs` +
  `/undo_attack_damage`, which reverts `buff_install` entries) *can* walk back
  condition installs, but the on-hit-save install isn't logged under the
  attack's `attack_id`, so the reaction can't currently find it.
- **miss→hit — no trigger today.** Every attack-flipping reaction is
  defender-side (it can only make an attacker's hit *worse*). A reroll turning
  a miss into a hit needs an attacker-side own-roll Lucky, which depends on the
  filed `attack_resolved` event.

**Recommended phasing:**

- **3b (small):** on a Lucky/AC-bump hit→miss flip, also restore any *direct*
  on-hit `buff_install` logged under `attack_id` (reuse `_restore_target_buffs`).
  Covers weapons that install a buff directly on hit with no save. Needs a
  direct-on-hit-buff demo fixture.
- **3c (the hard part):** revert weapon on-hit-*save* condition installs on a
  flip — either log the on-hit-save → install chain under the attack's
  `attack_id` so the reaction can walk it back, **or** build the true **pending
  window** (hold the on-hit save until the reaction window closes). The pending
  window is the cleaner model but is the architectural lift flagged below; the
  log-and-replay variant is incremental and fits the rest of this machine.

- **A true "pending" window** — hold the resolution un-committed for a short
  reaction window instead of resolve-then-replay. Only pursue if replay proves
  insufficient; replay (re-invoke the resolver with a new result) is simpler and
  covers every reaction case shipped so far. Phase 3c is the first case where
  replay strains (the deferred on-hit save), so the window becomes worth
  weighing there.

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
