# Exhaustion levels — design plan

**Status:** ✅ shipped end-to-end (re-audited 2026-06-11, v2.159.31 — SRD audit refresh). Phases 1–4 all closed across v2.159.17 → v2.159.22:
- **Phase 1** ✅ v2.159.17 (`set_exhaustion` endpoint + 6-level integer field on sheet).
- **Phase 2** ✅ v2.159.18 (disadvantage wiring — Lv 1 ability checks, Lv 3 attacks + saves).
- **Phase 3a** ✅ v2.159.19 (speed wiring — Lv 2 halve, Lv 5 → 0; server-side).
- **Phase 3b** ✅ v2.159.20 (HP-max halving at Lv 4).
- **Phase 4** ✅ v2.159.21 (Berserker Frenzy rage-end exhaustion +1 hook — closes the Phase E.8 Berserker blocker).
- **JS speed mirror** ✅ v2.159.22 (client-side move-preview ring consistency).

Closed the second-largest un-planned RAW gap from the 2026-06-10 audit.

**Authors:** rolling
**Last updated:** 2026-06-11

A plan to replace the engine's single-flag Exhaustion treatment with
RAW SRD 5.1 six-level tracking. Today `exhaustion` is just another
condition buff key — install it and nothing mechanical fires; the six
cumulative levels live in the GM's head.

## RAW (SRD 5.1 / PHB Appendix A)

| Level | Effect (cumulative — a creature suffers its level's effect **and all lower levels'**) |
|---|---|
| 1 | Disadvantage on ability checks |
| 2 | Speed halved |
| 3 | Disadvantage on attack rolls and saving throws |
| 4 | Hit point maximum halved |
| 5 | Speed reduced to 0 |
| 6 | Death |

- Finishing a **long rest** with food/water reduces exhaustion by 1
  (v1 simplification: always reduce by 1 on long rest; the
  food/water gate is narrative).
- Effects that remove exhaustion (Greater Restoration) reduce by 1
  per cast unless stated otherwise.
- Multiple exhaustion-causers **add levels**, they don't refresh.

## Why this matters

Unlocks (currently blocked or hand-waved):

- **Berserker Frenzy** (Barbarian Lv 3 subclass — the headline
  blocked feature; `class-content-status.md` Phase E.8 notes Frenzy
  "needs the exhaustion-tracking framework").
- Future environmental hooks (forced march, extreme heat) and any
  homebrew that says "gain one level of exhaustion."
- RAW-correct death spiral visibility for players (the level badge
  is genuinely useful at the table).

## Design

### Data shape

`sheet.exhaustion_level: int` (0–6, default 0 / absent) on the PC
sheet; `combatant.exhaustion_level` for NPCs. **Not** a buff — it has
no duration, never expires on its own, and stacks; the buff engine's
expiry machinery is the wrong home. A thin condition-buff mirror
(`exhaustion` key with `effects.exhaustion_level`) can ride along so
existing condition-badge UI shows it, but the integer field is the
source of truth.

### New helpers + endpoint

- `_exhaustion_level(sheet_or_combatant) -> int` — single read
  helper used everywhere.
- `POST /api/campaign/{cid}/set_exhaustion`
  `{character_id | combatant_id, delta | level, override?}` —
  GM- or feature-driven mutation; clamps 0–6; broadcasts
  `exhaustion_update` (and `feature_used(source=exhaustion)` card).
  At 6: sets death state via the existing death-saves machinery
  (`death_saves.status = "dead"` for PCs; 0-HP removal for NPCs).

### Read-site wiring (composition with what already exists)

| Level effect | Read site | Existing mechanism it composes with |
|---|---|---|
| 1 — checks disadvantage | `/roll` ability/skill classification | `_roll_condition_disadvantage` (v2.153.0) — add `exhaustion>=1` to the check-dis composition; NPC mirror via `_npc_roll_condition_disadvantage` (v2.157.0) |
| 2 — speed halved | `effective_speed` | same place `speed_reduction_ft` buffs already apply |
| 3 — attack disadvantage | `/attack` + `/npc_attack` adv/dis source sets | `_attacker_has_condition_disadvantage` (v2.152.0) + NPC twin (v2.154.0) |
| 3 — save disadvantage | save-construction sites | the Phase 2b/2d/2f save-dis helpers (all six NPC sites + PC resolver) |
| 4 — HP max halved | `_apply_hp_change` / heal paths + sheet HP display | clamp `hp` to `floor(max_hp/2)`; mirrors the Aid `+5 max HP` plumbing in reverse |
| 5 — speed 0 | `effective_speed` | hard floor after the level-2 halving |
| 6 — death | `set_exhaustion` endpoint itself | death-saves state machine (v2.1.0) |

### Rest interaction

`rest_character` long-rest branch decrements `exhaustion_level` by 1
(min 0) and broadcasts. Short rest: no effect (RAW).

## Phasing

### Phase 0 — Plan (this doc) ✅ v2.158.72

### Phase 1 — Data + endpoint + badge (S-M, ~2 commits)
The int field, `set_exhaustion` endpoint (PC + NPC), long-rest
decrement, mini-sheet/init-tracker level badge, `exhaustion_update`
broadcast. Harness: set → read back; clamp at 0/6; long rest
decrements; level 6 kills via death-saves state.

### Phase 2 — Roll read sites (M, ~2 commits)
Levels 1 + 3 wiring into the four existing condition-disadvantage
helpers (PC checks, PC attacks/saves, NPC attacks, NPC checks/saves).
Harness: level-1 PC check carries `auto_disadvantage_exhaustion`;
level-3 attack + save disadvantage; level-2 character at level 1 does
NOT get attack disadvantage (cumulative-floor check).

### Phase 3 — Speed + HP-max (M, ~2 commits)
Levels 2/4/5: `effective_speed` halve + zero floor; HP-max halving
with re-clamp on level change (dropping to level 4 halves current HP
ceiling; recovering past it restores). Harness: speed math at levels
2 and 5; HP clamp + heal-above-clamp rejection at level 4.

### Phase 4 — Berserker Frenzy retrofit (S, 1 commit)
`/use_frenzy` (or the existing rage-end hook) adds
`set_exhaustion(delta=+1)` on rage end after a frenzied rage —
closes the Phase E.8 blocker in `class-content-status.md`.

### Non-goals (v1)
- Food/water/forced-march environmental automation (no clock).
- The 2024-rules variant (−2 per level flat penalty) — SRD 5.1 only.
- Greater Restoration auto-hook (the spell can call the endpoint
  when its buff-teardown work lands; filed).

## Definition of done (per phase)

1. Mutation only via the endpoint/helper (no ad-hoc writes).
2. Effects fire through the existing condition/speed/HP read sites.
3. Harness tests assert the **state change** (roll label, speed
   value, HP clamp, death state), not just the broadcast.
4. `docs/automation-coverage.md` + `docs/test-harness-coverage.md`
   updated in the same commit.

## Related docs

- [advantage-disadvantage.md](advantage-disadvantage.md) — Phases
  2a–2f built the condition-disadvantage helpers this plan composes
  with.
- [death-saves.md](death-saves.md) — level 6 routes through its
  state machine.
- [class-content-status.md](class-content-status.md) — Phase E.8
  Berserker Frenzy is the blocked consumer.
- [`TODO.md` SRD 5e Audit](../../TODO.md#srd-5e-audit-2026-06-10) —
  the audit finding that filed this plan.
