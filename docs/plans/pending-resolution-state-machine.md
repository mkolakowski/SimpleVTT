# Pending-Resolution State Machine — Design Plan

**Status:** ✅ **the attack-flip arc is complete** (Phases 0–3a + 3c-1/3c-2/3c-3 all shipped). The save path closed at v2.612.0; the attack hit→miss condition arc closed at v2.664.0 (3c-3). Phase 0 (plan) v2.610.1; Phase 1 (extract
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
architectural lift). **Phase 3c is now designed (v2.648.3) — see the
implementation arc in the Phase 3 section:** NPC-defender flips are synchronous
(log-and-replay, 3c-1/3c-2 — small, shippable now) and PC-defender flips are
async (the held pending window, 3c-3 — its own arc). **3c-1 (log NPC on-hit-save
installs under `attack_id`) shipped v2.658.0** and **3c-2 (auto-revert the
condition on a flip via `_revert_attack_buff_installs`) shipped v2.659.0** — an
NPC Parry that flips a hit to a miss now restores HP **and** removes the on-hit
condition. **3c-3 (the PC-defender negate-then-answer case) shipped v2.664.0**
— but **not** via the held "pending window" sketched below. Instead it ships
the simpler, equivalent **record-negated + skip-at-resolution** model:
`_revert_attack_buff_installs` (the single chokepoint all six flip-producers
call) records the negated `attack_id` in a TTL registry, and
`_resolve_save_failure` skips the install when the deferred on-hit save's
`cast_id` (== the attack id, per 3c-1) was negated. This achieves the same RAW
outcome (a PC who negates the hit doesn't suffer the on-hit condition) without
reordering the attack pipeline — the held-window lift proved unnecessary once
3c-2 already covered the answer-then-negate order via revert and only the
negate-then-answer order remained. **The attack-flip arc is now fully closed.**

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

- **3b (no producer today — verified v2.648.2):** the idea was "on a
  Lucky/AC-bump hit→miss flip, restore any *direct* on-hit `buff_install`
  logged under `attack_id`." A substrate check killed it as an independent
  slice: the weapon `/attack` + `/npc_attack` paths log **only** `kind: damage`
  and `kind: spell_slot_spend` entries under `attack_id` — **nothing logs a
  direct on-hit `buff_install`**, because no shipped weapon installs a buff
  directly on a hit. Every on-hit condition rides the deferred `weapon_hit_save`
  save flow (= 3c). So 3b has nothing to revert today; it only becomes real
  once a direct-on-hit-buff weapon exists (e.g. Sword of Wounding's recurring-
  damage marker), and then the revert is a one-liner (`_restore_target_buffs`
  over the `buff_install` entries). **Net: the entire genuine Phase 3 remainder
  is 3c.**
- **3c (the real remainder):** revert weapon on-hit-*save* condition installs
  on a hit→miss flip. See the implementation arc below — a v2.648.2 design pass
  found the work splits by whether the flipping defender is an NPC (synchronous,
  log-and-replay) or a PC (async, needs the pending window).

### Phase 3c — implementation arc (designed; unstarted)

**The decisive insight: the flip is always defender-side, and the on-hit-save
timing splits by defender type.**

- **NPC defender** (flips via NPC Parry): `_fire_weapon_hit_saves` resolved the
  on-hit save **synchronously** (`_resolve_feature_save` → `_install_buff_on_combatant_id`)
  *before* the Parry prompt fired, so the condition **is already installed** at
  flip time — but it was installed with **zero logging**, so there's nothing to
  walk back. Pure log-gap; **replay works perfectly once we log it.**
- **PC defender** (flips via Lucky / Shield / Defensive Duelist / Form-of-Beast
  / Combat Inspiration): the on-hit save was only **prompted** (a RollRequest
  the player answers later). The condition is **not installed yet** at flip
  time. Replay can't revert a buff that doesn't exist; the only correct model is
  to **hold the save** until the reaction window closes (the true pending
  window). The PC case *is* the pending-window case.

**Per-commit breakdown (NPC-first; each its own version bump + CHANGELOG + push):**

- **3c-1 (smallest shippable first commit) — log NPC on-hit-save installs under
  `attack_id`. ✅ SHIPPED v2.658.0.** Threaded an `attack_id` param through
  `_fire_weapon_hit_saves` → `_resolve_feature_save` from the `/attack` call
  site. **Correction:** there is only **one** `_fire_weapon_hit_saves` call site
  (`/attack`), not the `/npc_attack` pair this design pass assumed — `/npc_attack`
  doesn't fire weapon-hit-save riders today. In the NPC-target branch, the
  install now snapshots-before + `_log_damage_entry(attack_id, {"kind":
  "buff_install", target_combatant_id, buffs_before, buff_installed_key})`
  (mirroring the PC path's `/respond` log). The PC branch gets `cast_id =
  cast_id or attack_id` for free. The NPC on-hit condition is now undoable via
  the existing `/undo_attack_damage`. No flip logic. Test:
  `tests/harness/test_weapon_hit_save_undo.py` using the `garrik_battle_master`
  PATCH recipe (`test_menacing_attack.py`) — Garrik arms Menacing Attack, hits
  an NPC bandit until the WIS save fails (Frightened installs), then
  `/undo_attack_damage` reverts it (+ a 404 error path).
- **3c-2 — auto-revert the NPC condition on a flip. ✅ SHIPPED v2.659.0.** New
  shared helper `_revert_attack_buff_installs(db, campaign_id, attack_id)` walks
  `_attack_damage_log[attack_id]`, restores each `buff_install` via
  `_restore_target_buffs`, and prunes the reverted entries (double-undo guard).
  Called from all **six** flip-producer heal-back blocks (Shield, Lucky,
  Defensive Duelist, Form-of-Beast, Combat Inspiration, NPC Parry) right after
  the HP heal-back, with a `conditions_reverted` field added to each negate
  broadcast. Only **NPC Parry** fires for an NPC defender, so it's the only one
  3c-2's test exercises (the other five are PC-defender no-ops until 3c-3).
  Test: `test_npc_parry_flip_reverts_on_hit_condition` — Garrik (Battle Master,
  Frightened rider) hits a Bandit Captain in the Parry band until Frightened
  installs, the NPC Parries → HP healed **and** Frightened removed.
- **3c-3 — the async PC-defender case. ✅ SHIPPED v2.664.0 — but simpler than
  this bullet planned.** The original sketch was a true pending window: hold the
  on-hit save un-fired until the reaction window closes, then drain+discard on a
  flip or fire on decline/timeout — a real attack-pipeline reorder for PC
  targets. **That lift proved unnecessary.** Once 3c-2 covered the
  answer-then-negate order (the install logs under `attack_id`, so a flip
  reverts it), only the **negate-then-answer** order remained, and that's
  handled by a far smaller **record-negated + skip-at-resolution** change: the
  flip records the negated `attack_id` in a TTL registry (`_negated_attack_ids`,
  marked inside `_revert_attack_buff_installs` — the single chokepoint all six
  flip-producers already call), and `_resolve_save_failure` skips the install
  when the deferred on-hit save's `cast_id` (== the attack id, per 3c-1) is in
  it. Same RAW outcome, no pipeline reorder, no new held-save state. Precise:
  spell save-or-suck + Silvery-Barbs re-invokes carry unrelated cast_ids never
  in the registry. Harness:
  `test_pc_defender_negate_then_answer_skips_on_hit_condition` (Garrik Menacing
  → Thalindra Shields first, then fails the on-hit save → Frightened skipped).

**Risks (full analysis in the design pass):** double-revert (3c-2 prunes the log
entries it reverts); the PC-async ordering (quarantined to 3c-3's held window so
it never rides an under-tested commit); NPC-vs-PC restore branch (`_restore_target_buffs`
already forks on `target_char_id` presence); once-per-turn rider / superiority-die
refund on a flip is **out of scope** (file separately — don't couple the pending
window to resource accounting); avoid legendary-resistance NPCs in the 3c-2 test
(LR defers the install, making the assertion non-deterministic).

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
