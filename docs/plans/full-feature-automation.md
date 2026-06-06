# Full Class-Feature Automation — design plan

**Status:** 🟠 in progress — Phase 1 ✅ + Phase 2 ✅ (sub-plan [on-hit-riders.md](on-hit-riders.md), shipped v2.99.395–.403); Phase 3 next.
**Author:** drafted v2.99.386
**Scope:** Turn every shipped class/subclass feature from "v1 announce-only"
into a **server-applied, state-changing, harness-verified** mechanic — and
fill in the higher-level subclass features that aren't shipped yet.

---

## 1. Goal & definition of "automated"

A class feature is **automated** when the server applies its full mechanical
effect end-to-end, with **no GM bookkeeping required**, and a harness test
asserts the resulting **state change** (not merely that a `feature_used` card
was broadcast).

Concretely, "automated" means the feature does the appropriate subset of:

- **decrements its resource** (use-counter, dice pool, ki, spell slot) and is
  **refilled on the correct rest**;
- **applies damage / healing / temp HP** to the right combatant through the
  damage pipeline (so resistance, immunity, concentration saves, death saves
  all fire);
- **installs a buff / condition** through the buff engine (so duration,
  concentration, immunity gates, and roll-time intercepts all fire);
- **modifies a roll** (advantage/disadvantage, +Xd_, save DC) at the
  construction site, not after the fact;
- **moves a token** (teleport, forced move, speed change) through the movement
  layer;
- **spawns a token** (companion, echo, tentacle, spirit) as a real combatant;
- **fires as a reaction** through the reactions framework when triggered.

### The verification bar

Today a typical test asserts `data["bonus_damage"] in [1,8]` and that a
broadcast fired. An **automated** feature's test must assert the *consequence*:
the target's HP dropped, the buff is present on the combatant, the condition
installed, the counter decremented, the token exists, the next roll used
advantage. **Upgrading the test contract is part of the definition of done.**

---

## 2. Current state (v2.99.385)

### Breadth — done

Every in-print subclass across all 12 classes has **one** Lv 1–3 first-feature
endpoint, gated on subclass + level, with happy- + error-path tests.

### Depth & automation — the gap

- **~156 of ~216 `feature_used` endpoints are announce-only.** They validate,
  spend a chip, roll display values, and broadcast — but leave the actual
  effect to the GM.
- **Only ~60 are genuinely tracked** (resource spend and/or buff install):
  e.g. `rage`, `patient_defense`, `lay_on_hands`, `second_wind`,
  `bardic_inspiration`, `holy_nimbus`, `turn_the_unholy`, `tides_of_chaos`,
  `restore_balance`, `favored_by_the_gods`, `strength_of_the_grave`,
  `healing_light`, `shadow_arts`, the metamagic suite, and the reactions
  (Shield / Counterspell / Uncanny Dodge / Lucky / …).
- **Higher-level subclass features (Lv 6/10/14/17/20) are mostly unshipped**
  for the newer subclasses — only the first feature exists.

### The good news: the engine is already strong

The hard infrastructure exists and is battle-tested. This plan is mostly about
**routing announce-only endpoints into primitives that already work**, plus a
small number of new primitives. Key existing pieces (file = `app/routes/tabletop_routes.py`):

| Primitive | Entry points |
|---|---|
| Buff install / refresh / concentration swap | `_install_buff`, `_install_buff_on_combatant_id`, `_get_buffs`, `_mirror_buffs_to_sheet` |
| Effect keys read by the engine | `effects.advantage_on`, `incoming_attacks_have_advantage`, `dodging`, `melee_str_damage_bonus`, `weapon_hit_bonus_dice` / `_target_combatant_id` / `_damage_type`, `resistance_to`, `immunity_to`, `vulnerability_to`, `condition_immunity_to`, `ac_bonus`, `bless_attack_bonus`, `bless_save_bonus`, `speed_reduction_ft`, … |
| Condition install + immunity gate | `_SPELL_CONDITION_MAP`, `_target_condition_immune`, `_INCAPACITATING_BUFF_KEYS` |
| Damage pipeline (resist/immune/vuln, concentration, death saves) | `_apply_damage_to_combatant`, `_apply_hp_change`, `_resistance_halve`, `_immunity_zero`, `_vulnerability_double` |
| On-hit damage uplift | `_compute_attack_auto_uplifts` (Rage, Hex, Hunter's Mark already ride this) |
| Roll-time advantage intercepts | `_attacker_has_str_attack_advantage`, `_target_grants_advantage_to_attackers`, `_target_has_dodging`, `_pc_has_danger_sense_on_dex_save`, `_race_grants_save_advantage` |
| Action economy | `_mark_battle_economy`, `_is_slot_used` (+ `override` / `strict_action_economy` gate) |
| Resource pools + bare counters | `sheet.resources[]` (`key/label/current/max/reset`); bare `*_uses` fields; `resource_update` broadcast |
| Rest refills | `rest_character` generic loop (`reset="short"|"long"`) + bespoke per-feature long-rest hooks |
| Reactions framework | `_eligible_reactions`, `_emit_reaction_prompt`, `reaction_prompt` WS, per-reaction availability helpers |
| Token disguise / summon groundwork | `Token.disguise` (Schema v66), `_apply_token_disguise` / `_revert_token_disguise`, `/place_token` |
| Level / ability / DC helpers | `_<class>_level_from_sheet`, `_caster_spellcasting_mod`, `sheet.proficiency_bonus` |

---

## 3. Strategy: patterns, not 156 bespoke endpoints

The 156 announce-only endpoints collapse into **~10 automation archetypes**.
The win is to build **one reusable primitive per archetype** and route every
feature of that shape through it, rather than hand-coding each. Each archetype
below names the canonical recipe and the new primitive (if any) it needs.

| # | Archetype | Count (approx) | Canonical recipe | New primitive? |
|---|---|---|---|---|
| A | **use-per-rest counter** | ~50 (cross-cutting) | bare counter + rest-refill | **Registry** (replace bespoke hooks) |
| B | **on-hit damage rider** (once/turn +Xd_) | ~40 | feed `_compute_attack_auto_uplifts` | **Rider registry** read by the uplift fn |
| C | **save-or-condition** | ~15 | reuse `_SPELL_CONDITION_MAP` + save resolver | **Feature-callable save resolver** |
| D | **self-buff** (adv / resist / AC / stance) | ~20 | `_install_buff` with existing `effects.*` | Wire `ac_bonus` read at `/attack` |
| E | **ally-buff / aura** (radius) | ~15 | `_install_buff` on each target in radius | **Aura tick** + radius target picker |
| F | **temp-HP grant** | ~10 | apply temp HP to target | **Temp-HP primitive** |
| G | **forced movement / teleport / speed** | ~10 | movement layer + `speed_reduction_ft` | **Forced-move primitive** |
| H | **summon / token** (companion/echo/spirit) | ~6 | extend `/place_token` + `Token.disguise` | **Summon-token primitive** |
| I | **reaction** (reduce dmg, reroll, riposte) | ~10 | register in `_eligible_reactions` | New reaction kinds |
| J | **announce-only-OK** (pure narration) | ~50 | leave as-is; tag in audit | — |

> Note the totals overlap: many features are e.g. *use-per-rest* **and**
> *save-or-condition* (Champion Challenge = A+C), or *use-per-rest* **and**
> *on-hit rider* (Slayer's Prey = A+B). Building the primitives once lets each
> feature compose them.

---

## 4. New primitives to build (the engine gaps)

### P1 — Feature-use registry (`_FEATURE_USES`) ✅ shipped
A data table mapping `feature_slug → {counter_field, max_fn(sheet), reset}`.
Replaces the ~6 hand-written long-rest hooks in `rest_character` with one loop,
and gives every use-per-rest feature decrement + 409 `out_of_uses` + refill for
free. Bare counter for ≤PB uses; promote to `sheet.resources[]` when the UI
should show a pip strip.

### P2 — On-hit rider registry (`_ATTACK_RIDERS`) ✅ shipped
A table of active "next/each hit deals +Xd_ [type], once per turn" riders,
keyed by attacker + (optional) target, consumed inside
`_compute_attack_auto_uplifts`. Today Hex/Hunter's Mark ride a bespoke branch;
generalize it so Colossus Slayer, Divine Fury, Slayer's Prey, Dreadful Strike,
Kensei's Shot, Gathered Swarm, Hexblade's Curse, Planar Warrior, the Battle
Master maneuvers, etc. all register a rider and let the attack flow apply it —
including the **once-per-turn** bookkeeping (per-turn flag on `combatant.economy`).

### P3 — Feature save resolver (`_resolve_feature_save`)
Extract the save-construction + condition-install path out of `/cast_spell` so a
feature endpoint can say "target makes a {ability} save vs DC {n}; on fail
install {condition} / take {damage}". Reuses `_SPELL_CONDITION_MAP`,
`_target_condition_immune`, the advantage intercepts, and the damage pipeline.
Unlocks Champion Challenge, Conquering Presence, Draconic Presence, Fey
Presence, Menacing Attack, Trip Attack, Hypnotic Gaze, Control Undead, etc.

### P4 — Temp-HP primitive (`_grant_temp_hp`)
Apply temporary HP to a combatant (RAW: doesn't stack — take the higher),
broadcast an HP/temp update. Unlocks Dark One's Blessing, Fighting Spirit,
Touch of Death, Heroism's per-turn grant, Inspiring Smite, Bear totem-less, etc.

### P5 — Aura tick (`_tick_auras`)
A per-turn hook (on turn start / combatant entering radius) that applies an
aura buff's effect to creatures in range: damage (Storm Aura desert, Spirit
Totem), heal/temp-HP (tundra, Aura of the Sentinel), or buff (Wolf totem,
Aura of Protection already does save bonus). Needs the radius target picker
(reuse range math from the ruler/range work).

### P6 — Forced-move / speed primitive (`_force_move`, speed buffs)
Move a token N ft (Gathered Swarm, Repelling Blast already partial), apply a
speed delta buff (Tempestuous Magic fly, Longstrider, Eagle totem dash),
teleport (Misty Step, Shadow Step, Ascendant Step, Planar Warrior is damage not
move). Mostly server-authoritative token-position update + a `speed_bonus_ft`
effect read by `effective_speed`.

### P7 — Summon-token primitive (`_summon_companion`)
Create a real combatant token bonded to the summoner: Ranger's Companion,
Manifest Echo, Tentacle of the Deeps, Spirit Totem, Summon Wildfire Spirit
(partial), Drake/Steel Defender. Extends `/place_token` with an `owner_char_id`,
synthetic stat block (AC = 14+PB etc.), and turn-on-owner-initiative behavior.

### P8 — Roll-bonus engine completion
Finish the **filed** read sites so existing effect keys actually fire:
`ac_bonus` at `/attack` hit/miss adjudication (Shield of Faith, Defensive
Duelist, Giant's Might-while-large), `bless_attack_bonus` / `bless_save_bonus`
d-dice at attack/save construction, buff-level **save advantage** (parallel to
`_pc_has_danger_sense_on_dex_save`).

---

## 5. Phased roadmap (leverage-weighted)

Each phase is independently shippable and unlocks a whole archetype. Earlier
phases unlock the most downstream features.

### Phase 0 — Automation audit doc (S, 1 commit)
Generate `docs/automation-coverage.md`: every `use_*` feature endpoint tagged
`tracked` / `announce-only` + its archetype(s) + target primitive. This is the
backlog the rest of the plan burns down; keep it in sync like the harness
coverage catalog. *(This plan + that audit are the two living docs.)*

### Phase 1 — P1 feature-use registry + retrofit (M, ~5 commits) ✅ shipped
Build `_FEATURE_USES`; migrate the existing bespoke hooks; retrofit every
announce-only use-per-rest feature (Fighting Spirit 3/long, Hexblade's Curse
1/rest, Watcher's Will & Champion Challenge & Control Undead via Channel
Divinity pool, etc.) to decrement + 409 + refill. **Biggest breadth win.**

### Phase 2 — P2 on-hit rider registry (M-L, ~6 commits, own sub-plan) ✅ shipped (v2.99.395–.403)
Generalize `_compute_attack_auto_uplifts`; add once-per-turn flagging; retrofit
the damage-rider features. Shipped via the [on-hit-riders.md](on-hit-riders.md)
sub-plan (P2.1 substrate → P2.5 `_ATTACK_RIDERS` registry), plus the
activated-rider retrofits (Slayer's Prey, Dreadful Strike, Gathered Swarm,
Hexblade's Curse, Planar Warrior, Divine Fury, Kensei's Shot). The remaining
announce-only riders (Genie's Wrath, Battle Master maneuvers, …) follow the same
install-a-buff shape as a long tail.

### Phase 3 — P3 feature save resolver (M-L, ~6 commits) ← next
Extract `_resolve_feature_save`; retrofit the save-or-condition features. Pairs
with the existing repeated-save / save-on-damage auto-fire so installed
conditions tick correctly.

### Phase 4 — P4 temp-HP + P8 roll-bonus completion (M, ~5 commits)
Temp-HP primitive + wire the filed `ac_bonus` / `bless_*` / save-advantage read
sites. Closes a cluster of "+temp HP", "+AC", "+d4 to save" features at once.

### Phase 5 — P5 auras (L, ~6 commits, own sub-plan)
Aura tick + radius picker; retrofit Storm Aura, Spirit Totem, the Paladin Lv 7
auras (Protection already done — fold the rest in), Aura of the Sentinel, etc.

### Phase 6 — P6 movement / P7 summons (L, ~8 commits, own sub-plan)
Forced-move + speed buffs, then the summon-token primitive (the heaviest — real
companion combatants with their own turns).

### Phase 7 — P9 reactions breadth (M, ~5 commits)
New reaction kinds for Protective Field (reduce damage), Riposte (attack after
miss), Chronal Shift (reroll), Restore Balance (cancel adv/disadv — buff exists,
make it a real reaction), etc. Reuses the framework.

### Phase 8 — Higher-level subclass features (L, ongoing)
With the primitives in place, the Lv 6/10/14/17/20 features become mostly
composition. Batch by class, same cadence as the breadth sweep.

### Phase 9 — Test-contract upgrade (cross-cutting, every phase)
Each retrofit converts its test from "asserts broadcast" to "asserts state":
HP delta, buff present (`GET /battle` → combatant.buffs), condition installed,
counter decremented (`GET …/sheet` or re-invoke → `out_of_uses`), token created,
next roll used advantage. **No phase is done until its tests assert state.**

---

## 6. Estimated scope

- Primitives P1–P8: ~10–15 commits of infrastructure.
- Retrofits: ~150 announce-only endpoints, but in archetype batches of 5–15 →
  ~20–30 commits.
- Higher-level features (Phase 8): ~100+ features → many sessions, but
  cheap-per-feature once primitives exist.
- **Order of magnitude: a multi-session effort (think 150–250 commits).** The
  primitive phases (1–7) are the high-value core; Phase 8 is a long tail.

---

## 7. Risks & non-goals

- **Hot-path risk:** P2 (on-hit riders) and P5 (auras) touch the attack/turn
  loop. Land them behind the existing per-feature gates and lean on the harness
  to catch regressions; each is its own sub-plan.
- **Once-per-turn / per-rest bookkeeping** is where bugs hide — centralize it in
  P1/P2 rather than re-deriving per feature.
- **Positional features** (auras, forced move, summons) depend on token
  positions being authoritative server-side; verify the range/ruler math is
  reusable before Phase 5/6.
- **Non-goals:** fog-of-war, difficult terrain, disease, fall damage, component
  tracking — these are *system frameworks* (Phase G in
  [class-content-status.md](class-content-status.md)), out of scope here unless
  a feature is blocked on one.
- **Non-goal:** rewriting already-tracked features. If it decrements and applies
  today, it stays.

---

## 8. Definition of done (per feature)

1. Resource decremented + refilled on the right rest (or N/A).
2. Mechanical effect applied through the engine (damage/heal/temp-HP/buff/
   condition/move/summon/roll-mod).
3. Once-per-turn / once-per-rest limit enforced server-side.
4. Harness test asserts the **state change**, not just the broadcast.
5. Coverage docs updated: `docs/automation-coverage.md` flips the row to
   `tracked`, `docs/test-harness-coverage.md` count bumped.

---

## Related docs

- [class-content-status.md](class-content-status.md) — the breadth roadmap (what
  subclass features exist and their ship status).
- [reactions-automation.md](reactions-automation.md) — the reactions framework
  this plan extends (Phase 7).
- [wild-magic.md](wild-magic.md), [sorcery-points-and-metamagic.md](sorcery-points-and-metamagic.md),
  [battle-master.md](battle-master.md) — examples of features already automated
  end-to-end; use as reference implementations.
- `docs/test-harness-coverage.md` — the test catalog that grows with each
  retrofit.
