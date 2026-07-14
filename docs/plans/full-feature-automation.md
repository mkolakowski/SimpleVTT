# Full Class-Feature Automation — design plan

**Status:** 🟠 in progress — Phase 0 ✅ ([automation-coverage.md](../automation-coverage.md), v2.99.447), Phase 1 ✅, Phase 2 ✅ ([on-hit-riders.md](on-hit-riders.md), v2.99.395–.403), Phase 3 ✅ ([feature-saves.md](feature-saves.md), v2.99.405–.414), Phase 4 ✅ ([temp-hp-and-bonuses.md](temp-hp-and-bonuses.md), v2.99.415–.423), Phase 5 ✅ ([auras.md](auras.md), v2.99.424–.429), Phase 6 ✅ ([movement-and-summons.md](movement-and-summons.md), v2.99.431–.446); Phase 7 (reactions breadth) 🟠 started — Riposte counter-attack (v2.99.455) + Protective Field damage-reduction (v2.99.456) resolve server-side; **new on-damage-taken primitive shipped v2.142.0** (Scornful Rebuke); **new heal-pipeline max-dice helper shipped v2.143.0** (Supreme Healing — generic `_max_dice_total`); **Phase 8 (higher-level subclass features) 🟠 started v2.158.0** — **Twelve-class diversification arc CLOSED — full PHB class coverage:** cleric (Lv-17 batch 6/6) + paladin (v2.158.10) + fighter (EK 2/2: v2.158.11+12) + druid (v2.158.13) + warlock (v2.158.14) + sorcerer (v2.158.15) + bard (v2.158.16) + rogue (v2.158.17) + monk (v2.158.18) + wizard (v2.158.19) + barbarian (v2.158.20) + ranger (v2.158.21). Plus PC `_resistance_halve` F6 hotfix (v2.158.1) + monster_slug HD resolve hotfix (v2.158.7). **Current coverage: 211+ tracked / 26- announce-only of 239 feature endpoints** (was ~60/156 at baseline; see [automation-coverage.md](../automation-coverage.md); auto-counts pin v2.99.460 — rerun the classifier after the next batch).

**v2.128.2–v2.149.0 retrofit summary** (curated; see [automation-coverage.md §Recent retrofits](../automation-coverage.md)):

- **Up-cast spell tail** — per-two-slot (v2.129.0) + flat-bonus (v2.130.0) up-cast prose parsing; closes Aid / Heal / False Life / Flame Blade / Spiritual Weapon shapes.
- **Assassinate** (Assassin Rogue Lv 3+) — auto-crit vs surprised (v2.131.0) + advantage vs not-yet-acted (v2.132.0). Adds the `has_acted: bool` combatant field (flipped on turn-advance in PUT `/battle`).
- **Aura of Warding** (Ancients Paladin Lv 7+) — full RAW chain across 5 commits (v2.133.0 plumbing + v2.134.0 endpoint + v2.135.0 tick test + v2.135.1 deferred-site coverage). New `is_spell: bool` kwarg threaded through `_apply_damage_to_combatant` + both `_resistance_halve` helpers; the aura emitter buff also carries `resistance_spell_damage` for the caster's "you and …" half.
- **Ancestral Protectors** (Ancestral Guardian Barbarian Lv 3+) — full RAW chain (install v2.136.0 + disadvantage gate v2.137.0/.1 + damage halving v2.138.0). Helper shared between adv/dis layering and damage-halve path.
- **Unwavering Mark** (Cavalier Fighter Lv 3+) — full RAW chain (install v2.139.0 + 5-ft disadvantage gate v2.140.0 + bonus-action punish endpoint v2.141.0). `_distance_ft_between_chars` 5-ft gate distinguishes UM from AP.
- **Scornful Rebuke** (Conquest Paladin Lv 15+) — first **on-damage-taken hook** in the codebase (v2.142.0). Inside `_apply_damage_to_combatant` PC branch after `_maybe_concentration_save`: when `is_attack and applied > 0 and attacker_char_id and _pc_has_conquest_oath(sheet, 15)`, recursively apply CHA-mod psychic to the attacker (with `is_attack=False` to break ping-pong). Sets the pattern for future on-being-hit retaliation features.
- **Supreme Healing** (Life Domain Cleric Lv 17+) — heal-pipeline max-dice substitution (v2.143.0). New `_max_dice_total` helper parses any dice expression and returns max(N*M) per term; `/cast_spell` heal block branches on `_pc_has_life_domain(sheet, 17)` and substitutes the max value. Generic helper — candidate for future Brutal Critical / Reliable Talent.
- **Combat Inspiration** (Valor Bard Lv 3+) — damage half (v2.144.0/.1) + AC half (v2.145.0). Damage path applies the BI bonus through `_apply_damage_to_combatant`. AC path is a pure calculator returning `ac_new_ac` + `ac_would_miss` for the GM/player to reconcile after the attack roll.
- **Blade Flourish** (Swords Bard Lv 3+) — shared damage half (v2.146.0). Same shape as CI damage half. Per-flourish riders (Defensive AC buff, Mobile push, Slashing secondary-target routing) deferred to Phase 2.
- **Ascendant Step** (Warlock Lv 9 invocation) — levitate buff install (v2.147.0). Mirrors v2.99.459 Stormborn with `fly_speed_ft: 10` + concentration. Vertical-only per RAW; SimpleVTT's 2D map keeps altitude narrative-only.
- **Fancy Footwork** (Swashbuckler Rogue Lv 3+) — Phase 1 install of the OA-block mark on the target (v2.148.0). Phase 2 (deferred): OA flow reads the buff and skips OAs against the named char_id.
- **Relentless Avenger** (Vengeance Paladin Lv 7+) — Phase 1 install of a free-move budget + OA-immune flag (v2.149.0). Phase 2 (deferred): `/token/move` consumes the budget + skips OA prompts while immune. Effect shape is generic enough to serve Mobile feat / Charger feat in the future.
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

### P3 — Feature save resolver (`_resolve_feature_save`) ✅ shipped
Extract the save-construction + condition-install path out of `/cast_spell` so a
feature endpoint can say "target makes a {ability} save vs DC {n}; on fail
install {condition} / take {damage}". Reuses `_SPELL_CONDITION_MAP`,
`_target_condition_immune`, the advantage intercepts, and the damage pipeline.
Unlocks Champion Challenge, Conquering Presence, Draconic Presence, Fey
Presence, Menacing Attack, Trip Attack, Hypnotic Gaze, Control Undead, etc.

### P4 — Temp-HP primitive (`_grant_temp_hp`) ✅ shipped
Apply temporary HP to a combatant (RAW: doesn't stack — take the higher),
broadcast an HP/temp update. Unlocks Dark One's Blessing, Fighting Spirit,
Touch of Death, Heroism's per-turn grant, Inspiring Smite, Bear totem-less, etc.

### P5 — Aura tick (`_tick_auras`) ✅ shipped
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

### Phase 0 — Automation audit doc (S, 1 commit) ✅ shipped v2.99.447
Generated [`docs/automation-coverage.md`](../automation-coverage.md): every
`use_*` / `cast_*` feature endpoint tagged `tracked` / `announce-only` + its
detected archetype, machine-classified from the endpoint body's state-mutation
markers so it can be regenerated. Current split: **177 tracked / 60
announce-only / 2 mechanical of 239**. This is the backlog the rest of the plan
burns down; keep it in sync like the harness coverage catalog. *(This plan +
that audit are the two living docs.)*

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

### Phase 3 — P3 feature save resolver (M-L, ~6 commits) ✅ shipped (v2.99.405–.414)
Extract `_resolve_feature_save`; retrofit the save-or-condition features. Pairs
with the existing repeated-save / save-on-damage auto-fire so installed
conditions tick correctly.

### Phase 4 — P4 temp-HP + P8 roll-bonus completion (M, ~5 commits) ✅ shipped (v2.99.415–.423)
Temp-HP primitive + wire the filed `ac_bonus` / `bless_*` / save-advantage read
sites. Closes a cluster of "+temp HP", "+AC", "+d4 to save" features at once.
Shipped via the [temp-hp-and-bonuses.md](temp-hp-and-bonuses.md) sub-plan
(`_grant_temp_hp` + damage absorption → 6 temp-HP retrofits → +AC spells →
buff-level save advantage).

### Phase 5 — P5 auras (L, ~6 commits, own sub-plan) ✅ shipped (v2.99.424–.429)
Aura tick + radius picker; retrofit Storm Aura, Spirit Totem, the Paladin Lv 7
auras (Protection already done — fold the rest in), Aura of the Sentinel, etc.
Shipped via the [auras.md](auras.md) sub-plan (`_tick_auras` owner- +
subject-turn-start passes → Storm Aura Desert, Spirit Totem Bear re-grant,
Elder Champion self-heal, Avenging Angel frightful aura).

### Phase 6 — P6 movement / P7 summons (L, ~8 commits, own sub-plan)
Forced-move + speed buffs, then the summon-token primitive (the heaviest — real
companion combatants with their own turns).

### Phase 7 — P9 reactions breadth (M, ~5 commits)
New reaction kinds for Protective Field (reduce damage), Riposte (attack after
miss), Chronal Shift (reroll), Restore Balance (cancel adv/disadv — buff exists,
make it a real reaction), etc. Reuses the framework.

### Phase 8 — Higher-level subclass features (L, ongoing) 🟠 started v2.158.0
With the primitives in place, the Lv 6/10/14/17/20 features become mostly
composition. Batch by class, same cadence as the breadth sweep.

**Shipped so far:**

- **v2.158.0 ("Iron Skin") — Avatar of Battle** (War Cleric Lv 17): permanent
  buff with `effects.resistance_to = ["nonmagical-bludgeoning",
  "nonmagical-piercing","nonmagical-slashing"]`; the v2.63.0 F6
  `_resistance_matches_damage` matcher halves nonmagical BPS damage through
  `_apply_damage_to_combatant`.
- **v2.158.1 ("Closing the F6 Gap") — PC `_resistance_halve` F6-aware**:
  hotfix that threads `is_magical` through and uses
  `_resistance_matches_damage` for the per-entry compare, closing the gap
  where the PC side trailed the NPC side on SRD "X from nonmagical attacks"
  phrasing. Required for v2.158.0's end-to-end test to pass.
- **v2.158.2 ("Saint of the Anvil") — Saint of Forge and Fire** (Forge
  Cleric Lv 17): permanent buff with BOTH `effects.immunity_to=["fire"]`
  AND `effects.resistance_to=["nonmagical-bludgeoning",
  "nonmagical-piercing","nonmagical-slashing"]`. Sibling of Avatar of
  Battle; v1 simplification on the heavy-armor RAW gate (always-on
  pending a PC armor-detection helper).
- **v2.158.3 ("Four-Faced Trick") — Improved Duplicity** (Trickery Cleric
  Lv 17): permanent buff carrying the upgraded Invoke Duplicity
  parameters (`effects.invoke_duplicity_max_duplicates=4`,
  `effects.invoke_duplicity_bonus_move_per_duplicate_ft=30`,
  `effects.invoke_duplicity_max_range_ft=120`). Phase 1 of the standard
  install-then-deferred-read split (same shape as v2.148.0 Fancy Footwork
  + v2.149.0 Relentless Avenger). Phase 2 (deferred): when the Invoke
  Duplicity endpoint ships, it reads the flags off `_buffs_active`.
- **v2.158.4 ("Soul Watcher") — Keeper of Souls** (Grave Cleric Lv 17):
  permanent buff carrying `effects.keeper_of_souls_watcher: True` +
  `effects.keeper_of_souls_radius_ft: 60`. Phase 1 of install-then-
  deferred-read. Phase 2 (deferred): on-death hook in
  `_apply_damage_to_combatant`'s NPC branch detects the 0-HP transition,
  walks PC combatants for the buff, range-gates at 60 ft, and auto-heals
  the watcher for the dying NPC's Hit Dice count. The Phase 2 hook is the
  most-interesting follow-up — a new pipeline event that will also unlock
  auto-firing for Touch of Death (Death Cleric Lv 1).
- **v2.158.5 ("Marked for Order") — Order's Wrath** (Order Cleric Lv 17):
  first Phase 8 commit to install a buff on the TARGET combatant via
  `_install_buff_on_combatant_id`. When `target_combatant_id` supplied,
  installs an `orders-wrath-curse` buff carrying
  `effects.orders_wrath_psychic_damage_expression="2d8"` +
  `effects.orders_wrath_caster_char_id=<cleric.id>` +
  `effects.orders_wrath_active=True`, duration 2 rounds. Phase 2
  (deferred): `/attack` hit by an ally against a cursed target deals
  2d8 psychic + drops the curse. Falls back to historical announce-only
  when no target supplied.
- **v2.158.6 ("Parting Vitality") — Keeper of Souls Phase 2 / new
  on-death pipeline primitive**: closes the deferred Phase 2 of
  v2.158.4. New helper `_fire_keeper_of_souls_on_npc_death` wires
  into the NPC branch of `_apply_damage_to_combatant` after the
  0-HP transition — walks PC combatants for the watcher buff,
  range-gates at 60 ft via `_combatant_token` +
  `_distance_ft_between_points`, parses dying NPC's HD count from
  the token template's `hit_dice` field, auto-heals each in-range
  watcher via `_apply_heal_to_combatant`. First new pipeline event
  since v2.142.0's on-damage-taken Scornful Rebuke. Future on-death
  features (Touch of Death auto-fire, on-kill triggers) reuse this
  hook point. v1 simplifications filed: self-heal only (no "or one
  creature of your choice" picker), no once-per-turn enforcement,
  no line-of-sight gate.
- **v2.158.7 ("Routed via Slug") — Keeper of Souls HD parse
  fallback**: hotfix on v2.158.6 — the HD parse was reading
  `tmpl.sheet["hit_dice"]` directly but the demo's NPCs use the
  `monster_slug` pointer pattern. Added a `local_content.resolve`
  fallback to re-read `hit_dice` off the raw monster JSON for
  pointer-style templates.
- **v2.158.8 ("Ally's Reprisal") — Order's Wrath Phase 2 /
  on-attack-hit trigger**: closes the deferred Phase 2 of v2.158.5.
  New helper `_fire_orders_wrath_on_attack_hit` wires into BOTH PC
  + NPC branches of `_apply_damage_to_combatant` after damage
  applies — checks `orders-wrath-curse` buff on target, validates
  attacker isn't the curse caster, rolls 2d8 psychic, applies via
  the damage pipeline (recursive with `is_attack=False`), drops
  the curse in place. Broadcasts `feature_used` source
  `orders-wrath-trigger`. Order in NPC branch: damage applies →
  break-on-damage → Order's Wrath trigger → Keeper of Souls on
  0-HP. A psychic-damage kill chains naturally into Keeper of
  Souls via the recursive call.
- **v2.158.9 ("Double Reaping") — Improved Reaper / Phase 1
  flag-install** (Death Cleric Lv 17): closes the Lv-17 cleric
  subclass capstone batch 6/6. Permanent buff carrying the six
  `improved_reaper_*` necromancy dual-target parameters. Phase 2
  (deferred): `/cast_spell` reads the flags + accepts a second
  `target_combatant_id` when the spell qualifies (necromancy
  school, levels 1-5, single-target).
- **v2.158.10 ("Ward Made Permanent") — Purity of Spirit**
  (Devotion Paladin Lv 15+): Phase 8 step-out to the Lv-15
  tier. Permanent buff carrying the same `pfeag_*` effects
  payload as the cast Protection from Evil and Good spell. The
  two existing engine read sites accept either `key="purity-of-
  spirit"` or `key="protection-from-evil-and-good"` so the
  class feature reuses the spell-buff engine wholesale. Sets
  the engine-reuse pattern for future PFE&G-shape features.
- **v2.158.11 ("Charged Step") — Arcane Charge** (Eldritch
  Knight Fighter Lv 15+): sibling Lv-15 commit to Purity of
  Spirit, but a martial subclass capstone. Phase 1 install of a
  permanent `arcane-charge-active` buff carrying two
  `arcane_charge_*` effect keys (`teleport_max_ft=30`,
  `requires_action_surge=True`). Phase 2 (deferred):
  `/use_action_surge` reads the buff + surfaces the teleport
  budget; actual server move via existing `_force_move`
  primitives.
- **v2.158.12 ("Bonus Bolt") — Improved War Magic** (Eldritch
  Knight Fighter Lv 18+): closes the EK 2/2 Phase 8 tracked
  features. Endpoint was already chip-marked pre-Phase-8; the
  Phase 8 enhancement adds the `improved-war-magic-active`
  flag buff with `improved_war_magic_*` effect keys (active=True,
  min_spell_level=1). Phase 2 (deferred): War Magic /
  `/cast_spell` flow reads the buff and allows the bonus-action
  weapon attack rider when the cast spell's level >= 1 (vs the
  Lv-7 War Magic cantrip-only limit).
- **v2.158.13 ("Chart the Heavens") — Star Map** (Stars Druid
  Lv 2+): Phase 8 diversifies into Druid — first Druid subclass
  feature flipped from announce-only to tracked this session.
  Two-part Phase 1: install `star-map-active` buff with three
  `star_map_*` parameter flags AND auto-bootstrap a
  `guiding-bolt-charges` resource on the sheet (delivers on the
  original v2.99.316 docstring promise). The existing
  rest-character flow now refills Guiding Bolt charges on long
  rest automatically. Phase 2 (deferred): `/cast_spell` lets
  Guiding Bolt route through the resource decrement instead of
  consuming a slot. New reusable pattern (capture parameter in
  buff + auto-create sheet resource if missing) for similar
  Lv-2-3 subclass focus-style features.
- **v2.158.14 ("Through the Dark") — Devil's Sight** (Warlock
  Lv 2+ Eldritch Invocation): Phase 8 diversifies into Warlock
  — first Warlock invocation flipped from announce-only to
  tracked this session. Permanent buff with two `devils_sight_*`
  effect keys (`range_ft: 120` + `through_magical_darkness:
  True`). Phase 2 (deferred): vision/darkness resolver short-
  circuits the in-darkness disadvantage adjudication at
  attack-roll time when the warlock is within 120 ft through
  magical darkness. Closes the v2.99.131 filed item. Pattern
  reusable for Eldritch Sight (at-will Detect Magic), Mask of
  Many Faces (at-will Disguise Self), other Warlock invocations
  with real parameters.
- **v2.158.15 ("Critical Cascade") — Spell Bombardment** (Wild
  Magic Sorcerer Lv 18+): closes the six-class diversification
  arc (cleric + paladin + fighter + druid + warlock + sorcerer).
  Endpoint was already chip-tracked pre-Phase-8 via
  `_is_spell_bombardment_used` / `_mark_spell_bombardment_used`;
  the Phase 8 enhancement adds the `spell-bombardment-active`
  flag buff with three `spell_bombardment_*` effect keys
  (active=True, die_sizes=[4,6,8,10,12], uses_per_turn=1).
  Phase 2 (deferred): `/cast_spell` damage-roll path auto-
  detects max-rolled dice in the per-die breakdown + surfaces
  the reroll option. Pre-Phase-8 the feature was player-invoked
  after seeing a max die in the roll log.
- **v2.158.16 ("Honeyed Lies") — Silver Tongue** (Eloquence
  College Bard Lv 3+): pushes the diversification arc to 7/12
  classes — Bard joins. Permanent buff with three
  `silver_tongue_*` effect keys (min_d20=10,
  skills=["persuasion","deception"], ability="CHA"). Phase 2
  (deferred): ability-check roll resolver reads the buff and
  applies the min-10 floor to the d20 result on CHA
  Persuasion/Deception checks. Pattern reusable for Reliable
  Talent (Rogue Lv 11) and similar floor-the-d20 features.
- **v2.158.17 ("Sleight of Spell") — Mage Hand Legerdemain**
  (Arcane Trickster Rogue Lv 3+): pushes the diversification
  arc to 8/12 classes — Rogue joins. Permanent buff with four
  `mage_hand_legerdemain_*` effect keys (range_ft=30,
  invisible=True, bonus_action_control=True,
  unnoticed_check="sleight_of_hand_vs_passive_perception").
  Phase 2 (deferred): Mage Hand cast flow reads the buff +
  surfaces the Legerdemain task picker (stow/retrieve from
  another's container, pick locks/disarm traps at range).
- **v2.158.18 ("Stagger and Sway") — Drunken Technique** (Way
  of the Drunken Master Monk Lv 3+): pushes the diversification
  arc to 9/12 classes — Monk joins. 1-turn buff carrying
  `effects.disengage: True` (reuses the engine flag from Step
  of the Wind, so the existing OA-prompting flow already half-
  consumes it) + `effects.drunken_technique_speed_bonus_ft: 10`
  + `effects.drunken_technique_rider_of: "flurry-of-blows"`.
  Different shape from the permanent-passive Phase 8 commits —
  a 1-turn rider that expires at next turn-start tick. Half-
  implements Phase 2 already via engine-flag reuse.
- **v2.158.19 ("Sharpened Bolt") — Empowered Evocation**
  (Evocation School Wizard Lv 10+): pushes the diversification
  arc to 10/12 classes — Wizard joins. Permanent
  `empowered-evocation-active` buff with three
  `empowered_evocation_*` effect keys (active=True, int_mod,
  school="evocation"). Phase 2 (deferred): `/cast_spell` reads
  the buff and lets the player apply +INT to one damage roll
  per evocation cast.
- **v2.158.20 ("Bestial Aspect") — Form of the Beast** (Path
  of the Beast Barbarian Lv 3+ TCE): pushes the diversification
  arc to 11/12 classes — Barbarian joins. 10-round rage-
  duration `form-of-the-beast-active` buff with six
  `form_of_the_beast_*` effect keys (active=True, form,
  damage_die, damage_type, reach_ft, special). Phase 2
  (deferred): `/attack` reads the buff and renders Bite/Claws/
  Tail as a built-in attack option while the buff is active.
- **v2.158.21 ("Faded Footprints") — Vanish** (Ranger Lv 14+
  PHB): **CLOSES the twelve-class diversification arc — full
  PHB class coverage.** Endpoint was already chip-marked pre-
  Phase-8 (bonus-action slot); the Phase 8 enhancement adds
  the permanent passive `vanish-active` buff with three
  `vanish_*` effect keys (active=True, hide_as_bonus_action=
  True, untrackable_nonmagical=True). Phase 2 (deferred): (a)
  action-UI surfaces Hide as a bonus-action option when the
  buff is present + ranger_lv >= 14; (b) any future non-
  magical tracking-check resolver short-circuits when the
  target carries `vanish_untrackable_nonmagical`. Same install-
  then-deferred-read shape as Devil's Sight (v2.158.14) and
  Mage Hand Legerdemain (v2.158.17). Every PHB class now has
  at least one Phase-8 buff-payload feature.
- **v2.612.1 ("The Lit Cantrip") — Potent Spellcasting** (Light/
  Knowledge/Grave/Peace Domain Cleric Lv 8+): the cleric/cantrip
  twin of v2.158.19 Empowered Evocation. `use_potent_spellcasting`
  was announce-only; the Phase 8 enhancement installs a permanent
  `potent-spellcasting-active` buff with three `potent_spellcasting_*`
  effect keys (active=True, wis_mod=<computed>, class="cleric"),
  sheet-mirrored + idempotent. Phase 2 (deferred): `/cast_spell`
  reads the buff and auto-adds the WIS mod to cleric-cantrip damage
  — the same cantrip-detection read-site Empowered Evocation's
  Phase 2 needs for evocation spells. Same install-then-deferred-read
  shape; reuses the "+ability-mod to spell damage" flag substrate.
- **v2.612.2 ("The Three Totems") — Totem Spirit** (Path of the
  Totem Warrior Barbarian Lv 3+): `use_totem_spirit` was
  announce-only; the Phase 8 enhancement installs a permanent
  `totem-spirit-active` buff carrying the chosen totem's parameter
  payload (new `_TOTEM_SPIRIT_EFFECTS` map), all gated on
  `totem_spirit_requires_rage`: Bear → `resistance_except: ["psychic"]`,
  Eagle → OA-disadvantage + bonus-action Dash + no-heavy-armor, Wolf →
  ally-melee-advantage-within-5ft. A re-press with a different totem
  overwrites the params (`_install_buff` refresh semantics — a barbarian
  has one totem). Phase 2 (deferred): the rage read sites apply each
  benefit (Bear needs a new "all except" matcher in `_resistance_halve`).
  First multi-variant Phase-8 flag-buff (three parameter payloads behind
  one endpoint).
- **v2.665.0 ("The Drop on Them") — Assassinate — REVERTED v2.670.1.** This
  commit added an `assassinate-active` flag-buff believing the feature was
  announce-only. **It wasn't:** Assassinate was already mechanized in `/attack`
  (v2.131.0–v2.132.0) — auto-crit vs `target_surprised` + advantage vs a target
  whose `has_acted` is False, gated directly on `_pc_has_assassin_subclass`.
  The flag-buff's keys were never read (dead flags), so v2.670.1 reverted the
  install + its test and corrected the docs. **Lesson (verify-substrate):**
  checking the endpoint body for `_install_buff` is NOT enough — a feature can
  be mechanized in a *different* path (here `/attack`, keyed on the subclass,
  not the endpoint). Grep the read path (`/attack`, `/cast_spell`, the tick
  engines) before declaring a feature announce-only.
  **Verify-substrate note (still valid):** picking this feature surfaced that the
  `automation-coverage.md` classifier is stale for several rows (Aura of
  Warding, Fancy Footwork, Relentless Avenger, Unwavering Mark, Order's
  Wrath, Improved Duplicity all already mechanized) — re-run the classifier
  before trusting the announce-only counts.
- **v2.667.0 ("The Quickened Blade") — Blade Flourish speed bonus** (Swords
  College Bard Lv 3+): `use_blade_flourish` already installed the Defensive
  Flourish AC self-buff (v2.158.66); the +10 ft walking-speed bonus was still
  announce-only. Now installs a 1-round `blade-flourish-speed-active` buff with
  `effects.speed_bonus_ft: 10` that the `effective_speed_walk` engine adds to
  the move cap (reuses the Longstrider/Eagle-Totem substrate — zero new engine
  code). Flourish-agnostic (rides the Attack action). Harness:
  `test_blade_flourish.py::test_bf_installs_speed_bonus_buff`.
- **v2.668.0 ("The Whispered Wound") — Psychic Blades** (Whispers College
  Bard Lv 3+): `use_whispers_psychic_blades` computed the level-scaled NdN
  psychic (2d6→8d6) but was announce-only; it now rolls + applies the damage
  server-side via `_apply_damage_to_combatant` when a `target_combatant_id` is
  supplied (the v2.146.0 Blade Flourish damage-half pattern), surfacing
  `damage_rolled`/`damage_applied`/`damage_breakdown`. Announce-only without a
  target. Harness: `test_whispers_psychic_blades.py` (+2).
- **v2.669.0 ("The Sheltered Blast") — Sculpt Spells** (Evocation Wizard Lv
  2+): RAW-identical to Careful Spell metamagic, so it rides that substrate.
  `use_sculpt_spells` installs a `sculpt-spells-active` buff carrying
  `effects.protected_combatant_ids`; `_caster_has_careful_pending_buff` was
  extended to match the key (so all six AoE-save read sites honor it for free)
  and `_broadcast_careful_protected` reads `effects.protection_label` so the
  auto-pass card says "Sculpt Spells" not "Careful Spell". Consumed per-cast at
  the AoE cleanup. Announce-only without `protected_combatant_ids`. First
  substrate **shared across two features under distinct keys**. Harness:
  `test_sculpt_spells.py` (+3, incl. an end-to-end Fireball auto-pass).
- **v2.670.0 ("The Mote Made Real") — Mote of Potential** (Creation College
  Bard Lv 3+): `use_mote_of_potential` had three modes but was announce-only.
  Two now apply server-side: **attack** → `1d{die}` force damage via
  `_apply_damage_to_combatant` (Psychic Blades shape); **save** → `1d{die}+CHA`
  temp HP via `_grant_temp_hp` (Inspiring Smite shape). **check** mode stays
  GM-narrated (no ability-check substrate) but the die is rolled + surfaced.
  Harness: `test_mote_of_potential.py` (+2).
- **v2.671.0 ("The Fey-Woven Shield") — Mantle of Inspiration** (Glamour
  College Bard Lv 3+): `use_mantle_of_inspiration` computed `5 + bard_level`
  temp HP but applied it by hand. It now accepts `target_combatant_ids` (a
  list — the feature buffs up to CHA-mod allies) and grants the temp HP to
  each named combatant via `_grant_temp_hp` (the Mote save-mode / Inspiring
  Smite substrate), honoring the CHA-mod cap. The free reaction-move-without-
  OAs half stays GM-narrated. Surfaces `targets_buffed`/`applied_targets`.
  Announce-only without target ids. Harness: `test_mantle_of_inspiration.py`
  (+3).
- **v2.672.0 ("The Turned Blow") — Rebuke the Violent** (Redemption Paladin
  Lv 3+): `use_rebuke_the_violent` computed the save DC + on-fail/on-success
  psychic but was announce-only. It now rolls the attacker's Wisdom save
  server-side (NPC save mod via `_monster_template_to_sheet` +
  `_resolve_stat_modifier`, the Polymorph pattern; PC via sheet WIS + prof)
  and applies the reflected psychic — full `damage_dealt` on a fail, half on
  a success — via `_apply_damage_to_combatant` (`is_magical=True`, Channel
  Divinity is magical/save-based, not an attack). Surfaces `save_total`/
  `save_passed`/`psychic_damage_applied`; announce-only when the attacker has
  no resolvable sheet. Harness: `test_rebuke_the_violent.py` (+1).
- **v2.673.0 ("The Answering Thunder") — Wrath of the Storm** (Tempest Domain
  Cleric Lv 1+): `use_wrath_of_the_storm` rolled the 2d8 + DC but was
  announce-only. It now accepts an optional `attacker_combatant_id`; when it
  resolves to a sheet, the attacker's Dexterity save is rolled server-side
  (same NPC/PC resolution as Rebuke the Violent, but a DEX save) and the
  elemental damage applied — full 2d8 on a fail, half on a success — via
  `_apply_damage_to_combatant` (`is_magical=True`). Surfaces `save_total`/
  `save_passed`/`damage_applied`; the free-form `attacker_name` path stays
  announce-only. Harness: `test_wrath_of_the_storm.py` (+2).
- **v2.674.0 ("The Mending Touch") — Hands of Healing** (Way of Mercy Monk
  Lv 3+): `use_hands_of_healing` rolled the heal but was announce-only. It
  now accepts an optional `target_combatant_id` and applies the rolled HP
  via `_apply_heal_to_combatant` — the heal-pipeline twin of
  `_apply_damage_to_combatant` (caps at max HP, revives a dying PC). First
  **heal-application** wire of this session's tail (the prior three rode
  damage / temp-HP substrates). Surfaces `target_combatant_id`/`heal_applied`/
  `revived`; announce-only without a target. Harness:
  `test_hands_of_healing.py` (+2).
- **v2.675.0 ("The Celestial Mend") — Healing Light** (The Celestial Warlock
  Lv 1+): `use_healing_light` rolled the pooled-d6 heal + tracked the
  `healing-light-dice` resource but was announce-only. It now accepts an
  optional `target_combatant_id` and applies the rolled HP via
  `_apply_heal_to_combatant` — the same heal-pipeline wire as Hands of
  Healing (v2.674.0). Surfaces `target_combatant_id`/`heal_applied`/`revived`;
  announce-only without a target. Harness: `test_healing_light.py` (+2).
- **v2.676.0 ("The Necrotic Bloom") — Halo of Spores** (Spores Druid Lv 2+):
  `use_halo_of_spores` computed the level-scaled necrotic die + CON save DC
  but was announce-only. With a `target_combatant_id` it now rolls the
  target's CON save server-side (same NPC/PC resolution as Wrath of the
  Storm, but a CON save) and applies the necrotic — **save-OR-NOTHING** (RAW:
  full on a fail, ZERO on a success, NOT save-for-half) — via
  `_apply_damage_to_combatant` (`is_magical=True`). Surfaces `save_total`/
  `save_passed`/`damage_rolled`/`damage_applied`; announce-only without a
  resolvable target. Harness: `test_halo_of_spores.py` (+2).
- **v2.677.0 ("The Roaming Tempest") — Storm Aura (Sea + Tundra)** (Storm
  Herald Barbarian Lv 3+): the Desert environment already auto-ticks as an
  aura (v2.99.426); the two single-target choices were announce-only. With a
  `target_combatant_id` they now resolve server-side — **Sea** rolls the
  target's DEX save (same NPC/PC resolution as Wrath of the Storm; DC = 8 +
  prof + CON mod) + applies the lightning save-for-half via
  `_apply_damage_to_combatant`; **Tundra** grants the flat `2 + tiers` temp
  HP via `_grant_temp_hp`. Surfaces `save_total`/`save_passed`/
  `damage_applied`/`temp_hp_applied`; announce-only without a target. Harness:
  `test_storm_aura.py` (+3).
- **v2.678.0 ("The Grasping Deep") — Tentacle of the Deeps** (Fathomless
  Warlock Lv 1+): first **attack-roll** wire of this session's tail (the
  prior seven rode save / heal / temp-HP substrates). With a
  `target_combatant_id`, `use_tentacle_of_the_deeps` rolls the melee spell
  attack server-side vs the target's AC (`_read_target_ac`; nat 20 crits +
  doubles the dice, nat 1 misses) and applies the cold on a hit via
  `_apply_damage_to_combatant` (`is_attack=True, is_magical=True`). Surfaces
  `target_ac`/`attack_nat`/`attack_total`/`is_crit`/`hit`/`damage_applied`;
  speed reduction stays GM-narrated; announce-only without a target. Harness:
  `test_tentacle_of_the_deeps.py` (+2).
- **v2.679.0 ("The Summer Balm") — Balm of the Summer Court** (Dreams Druid
  Lv 2+): `use_balm_of_the_summer_court` rolled the pooled-d6 heal + computed
  the per-die temp HP but was announce-only. With a `target_combatant_id` it
  now applies **both halves to the same ally** — the HP via
  `_apply_heal_to_combatant` (Hands of Healing wire) AND the temp HP via
  `_grant_temp_hp` (Mantle of Inspiration wire). First endpoint this session
  to compose two apply-substrates on one target. Surfaces `heal_applied`/
  `temp_hp_applied`/`revived`; announce-only without a target. Harness:
  `test_balm_of_the_summer_court.py` (+2).
- **v2.680.0 ("The Ensnaring Vines") — Nature's Wrath** (Ancients Paladin Lv
  3+ CD): first **save → condition-install** wire of this session's tail (the
  prior nine applied damage / heal / temp-HP). `use_natures_wrath` now
  resolves the target's STR/DEX save via `_resolve_feature_save` (the Champion
  Challenge / feature-saves substrate — NPC saves inline, PC via RollRequest)
  and installs Restrained (`_make_restrained_buff`, key `restrained`, with the
  end-of-turn repeated-save stamps) on a fail. Surfaces `feature_save`.
  Harness: `test_natures_wrath.py` (+1).
- **v2.681.0 ("The Holy Symbol") — Abjure Enemy** (Vengeance Paladin Lv 3+
  CD): the Nature's Wrath sibling — `use_abjure_enemy` now resolves the
  target's WIS save via `_resolve_feature_save` (NPC inline, PC via
  RollRequest) and installs Frightened (key `frightened`, the Conquering
  Presence shape, with the end-of-turn repeated save) on a fail. The
  fiends/undead disadvantage + speed-0/halved mutation stay GM-narrated.
  Surfaces `feature_save`. Harness: `test_abjure_enemy.py` (+1).
- **v2.682.0 ("The Faithless Routed") — Turn the Faithless** (Ancients Paladin
  Lv 3+ AoE CD): the multi-target sibling of Nature's Wrath —
  `use_turn_the_faithless` now resolves each target's WIS save via
  `_resolve_feature_save` in the Champion Challenge AoE-loop pattern (NPC
  inline, PC via RollRequest) and installs Turned (key `turned`, the Turn the
  Unholy shape, ends on damage so `repeated_save=False`) on a fail. The
  fey/fiend creature-type filter stays GM-tracked. Surfaces `feature_saves`
  (one per target). Harness: `test_turn_the_faithless.py` (+1).
- **v2.683.0 ("The Menacing Glare") — Intimidating Presence** (Berserker
  Barbarian Lv 10+): `use_intimidating_presence` now accepts an optional
  `target_combatant_id` and resolves the target's WIS save via
  `_resolve_feature_save` (NPC inline, PC via RollRequest), installing
  Frightened on a fail (short fixed duration — RAW "until the end of your next
  turn" — so `repeated_save=False`). The free-form `target_name` label still
  drives the announce-only path. Surfaces `feature_save`. Harness:
  `test_berserker_path.py` (+1).
- **v2.690.0 ("The Sweeping Leg") — Trip Attack** (Battle Master Fighter Lv
  3+): the first Battle Master **maneuver** mechanized on-target. With a
  `target_combatant_id` (trust-the-caller — the hit already landed),
  `use_trip_attack` applies the superiority die as bonus damage via
  `_apply_damage_to_combatant` (`is_attack=True`) and resolves the STR save →
  Prone via `_resolve_feature_save` (NPC inline, PC via RollRequest; `prone`
  engine condition, no re-save). The Large-or-smaller size gate stays
  GM-tracked. Delivers the rules automation the "/attack maneuver field" was
  filed for, without core-path surgery (the one-click `/attack` `maneuver:`
  UX wiring remains a deferred follow-up). Surfaces `damage_applied` +
  `feature_save`. Harness: `test_trip_attack.py` (+2).
- **v2.691.0 ("The Driving Blow") — Pushing Attack** (Battle Master Fighter Lv
  3+): the STR save → 15-ft push was already wired (v2.99.433 via
  `_force_move`); this closes the last GM-tracked half by applying the
  superiority die as bonus weapon damage via `_apply_damage_to_combatant`
  (`is_attack=True`, trust-the-caller). With both halves server-side, Pushing
  Attack is fully mechanized but for the GM-tracked size gate. Surfaces
  `damage_applied`. Harness: `test_pushing_attack.py` (+1).
- **v2.692.0 ("The Wrested Blade") — Disarming Attack** (Battle Master Fighter
  Lv 3+): closes the targeted-maneuver tail. With a `target_combatant_id`
  (trust-the-caller), `use_disarming_attack` applies the superiority die as
  bonus damage via `_apply_damage_to_combatant` and rolls the STR save via
  `_resolve_feature_save` with `condition_buff=None` (no engine condition for
  "drop object" → resolved-but-GM-narrated). Surfaces `damage_applied` +
  `feature_save`. Harness: `test_disarming_attack.py` (+2). **All four targeted
  Battle Master maneuvers (Trip / Pushing / Disarming / Menacing) now
  mechanize damage + save server-side.**
- **v2.693.0 ("The Refused Fall") — Undying Sentinel** (Ancients Paladin Lv
  15+): `use_undying_sentinel` now applies the "drop to 1 HP instead of 0"
  HP-mutation — brings the caster to exactly 1 HP via
  `_apply_heal_to_combatant` (heal `1 - current`; flips the death-save state
  dying → alive), the Protective Spirit self-apply shape. Deliberately rides
  the heal pipeline on the caster's own combatant rather than threading a
  fourth branch into the high-traffic `_apply_hp_change` HP-floor chain
  (Relentless Endurance / Death Ward / Relentless Rage), avoiding a
  manual-decrement-vs-auto-fire conflict. Surfaces `hp_after`/`revived`.
  Harness: `test_undying_sentinel.py` (+1).
- **v2.694.0 ("The Shared Wound") — Aura of the Guardian** (Redemption Paladin
  Lv 7+): the first **two-target redirection** shape of the arc. With an
  `ally_combatant_id` + `damage_amount` (trust-the-caller — the ally already
  took the damage), the ally is healed back via `_apply_heal_to_combatant` and
  the Paladin takes that damage via `_apply_damage_to_combatant` as untyped /
  unreducible (RAW: "can't be reduced in any way"; other effects not
  transferred). Surfaces `redirected`/`ally_healed`/`paladin_damage_applied`/
  `paladin_hp_after`. Harness: `test_aura_of_the_guardian.py` (+2).
- **v2.695.0 ("The Spirit's Tale") — Tales from Beyond** (Spirits College Bard
  Lv 3+): a branchy d6-table feature. With a `target_combatant_id`, the four
  mechanizable tales resolve server-side keyed off the rolled tale — 3 Beloved
  Friends / 6 Traveler grant `2d6+bard_lv` temp HP (`_grant_temp_hp`); 4 Brute
  is a STR save → Prone + 2d10 force on a fail (`_resolve_feature_save` +
  `_apply_damage_to_combatant`); 5 Tragic Romance is a WIS save → Charmed.
  Tales 1 (Clever Animal) + 2 (Renowned Duelist) stay GM-narrated. Surfaces
  `applied`. Harness: `test_tales_from_beyond.py` (+4, the force_tale apply
  tests skip when TEST_MODE is off).
- **v2.696.0 ("The Open Field") — Skirmisher + free-move substrate
  generalization** (Scout Rogue Lv 3+): generalized the Relentless Avenger
  `/token/move` read site (v2.158.51) from a hardcoded `relentless-avenger-
  bonus-move` key into an **effect-keyed free-move substrate** — any buff with
  `effects.oa_immune_during_move` (+ optional `free_movement_remaining_ft`)
  now exempts the next move from the over-speed cap + suppresses OAs, then is
  consumed. `use_skirmisher` mechanizes onto it: installs a 1-round
  `skirmisher-bonus-move` buff (half-speed budget + OA-immune). Relentless
  Avenger rides the same generalized path unchanged. Harness:
  `test_skirmisher.py` (+1, end-to-end over-cap move proof).
- **v2.697.0 ("The Riding Storm") — Tempestuous Magic** (Storm Sorcery Lv 1+):
  second feature to ride the v2.696.0 free-move substrate. `use_tempestuous_
  magic` installs a 1-round `tempestuous-magic-fly` buff
  (`free_movement_remaining_ft: 10` + `oa_immune_during_move`), so the
  Sorcerer's next ≤10-ft move is cap-exempt + OA-free, then consumed. The
  on-ground / recent-cast prereq + fly-vs-walk stay GM-narrated. Surfaces
  `buff_installed`. Harness: `test_tempestuous_magic.py` (+1, end-to-end
  over-cap move proof).
- **v2.698.0 ("The Nimble Exit") — Disengage OA-read** (Monk Step of the Wind
  / Drunken Technique, + any Cunning Action source): wired `/token/move`'s OA
  check to honor a mover's `effects.disengage: True` buff — a disengaged mover
  provokes no opportunity attacks for the turn (triggers dropped, no 409).
  Effect-keyed (not class-specific); **not consumed** (persists for the turn,
  unlike the single-use free-move budget). Makes the long-installed-but-unread
  disengage flag mechanical. Surfaces `disengage_applied`. Harness:
  `test_disengage_oa.py` (+3).
- **v2.699.0 ("The Vanishing Mist") — Misty Escape** (The Archfey Warlock Lv
  6+): new `/use_misty_escape` endpoint (the feature previously had only a
  reactions-menu label). Once/short-rest reaction that **composes two
  substrates** — installs an `invisible` buff (the attack-edge substrate) +
  a `disengage` buff (so the 60-ft teleport rides the v2.698.0 OA-free move
  read). Teleport destination is player-dragged; attack/cast-cancel of
  invisibility GM-narrated. First reaction to compose invisible + disengage.
  Harness: `test_misty_escape.py` (+4, incl. error paths).
- **v2.700.0 ("The Avatar of Peace") — Emissary of Redemption** (Redemption
  Paladin Lv 20 capstone): both halves mechanized. The endpoint installs a
  permanent `resistance_to: ["all"]` buff (the resistance half — the damage
  pipeline halves every type against the wildcard), and a new on-damage-taken
  hook in `_apply_damage_to_combatant` (after Scornful Rebuke) reflects half
  the applied damage as radiant to the attacker (the reflect half, Redemption
  Lv 20 gate, recursive `is_attack=False`). The per-target "ends if you attack
  them" caveat stays GM-narrated. Surfaces `resistance_installed`. Harness:
  `test_emissary_of_redemption.py` (+1, end-to-end reflect-on-hit).
- **v2.701.0 ("The Tactician's Nod") — Master of Tactics** (Mastermind Rogue
  Lv 3+): RAW combat Help is target-specific, so it rides the existing
  target-keyed advantage substrate — no new read site. With
  `ally_combatant_id` + `target_combatant_id`, installs a 1-round buff on the
  ally (`attack_advantage_vs_target_combatant_id` + `consume_on_attack`); the
  ally's next attack vs that target rolls `2d20kh1` (the True Strike / Vow of
  Enmity read) then drops. Surfaces `help_installed`; announce-only without
  both ids. Harness: `test_master_of_tactics.py` (+1, end-to-end advantage).
- **v2.702.0 ("The Searing Sun") — Corona of Light** (Light Domain Cleric Lv
  17+): a genuinely new save-disadvantage substrate. The endpoint installs a
  `corona-of-light` buff; `_caster_corona_disadvantages_save` is wired into
  the single-target + AoE NPC save sites in `/cast_spell` — a corona-active
  cleric casting a fire/radiant spell swaps the enemy NPC saver's d20 →
  2d20kl1 (mirrors the Heightened Spell swap). v1 trust-the-caller scope (the
  caster's own fire/radiant spells); the 60-ft distance gate + non-caster
  spells + light emission stay GM-narrated. Surfaces `aura_installed`.
  Harness: `test_corona_of_light.py` (+1, Sacred Flame disadvantage end-to-end).

- **v2.1002.0 ("The Wild Mend") — Combat Wild Shape heal apply** (Moon Druid
  Lv 2+): the heal mode rolled `<slot_level>d8` since v2.99.348 but left the
  HP application GM-tracked — a fresh announce-only survey (2026-07-12)
  ranked it the cleanest remaining candidate. It now applies the rolled HP
  to the druid's own combatant via `_apply_heal_to_combatant` (the Undying
  Sentinel v2.693.0 self-apply shape; caps at max HP, revives a dying druid,
  works in or out of battle), surfacing `heal_applied`/`hp_after`/`revived`.
  Still GM-tracked: the transform, the slot spend, the "while transformed"
  prereq (trust-the-caller). The same survey confirmed the two remaining
  deferred read-sites are **Supreme Healing in `/apply_healing`** (the
  `_heal_claims` chat-card path never calls `_max_dice_total` — only the
  `/cast_spell` inline path does) and **Potent Spellcasting in
  `/cast_spell`** (no read helper exists; Empowered Evocation's
  `_empowered_evocation_bonus` is the template), plus one clean summon
  candidate (`use_summon_wildfire_spirit` → `_summon_companion`). Harness:
  `test_combat_wild_shape.py` (+1 state-asserting heal test per the Phase 9
  contract).

- **v2.1003.0 ("The Full Measure") — Supreme Healing heal-claim parity**
  (Life Domain Cleric Lv 17+): closes the filed Phase-1.5 finisher the
  v2.1002.0 survey re-confirmed. `/cast_spell`'s target-bound auto-heal has
  maxed every healing die since v2.143.0, but the legacy `/apply_healing`
  heal-claim (chat-card 🩹 button) path still rolled bare dice. The caster
  sheet is now loaded before the roll (it was already fetched for the
  v2.59.2 spellcasting-mod/Disciple-of-Life parity, just after the dice),
  and a Lv 17+ Life cleric caster routes through `_max_dice_total` with the
  same `💗 Supreme Healing` breakdown prefix; `supreme_healing_applied`
  surfaces on the response + `heal_applied` broadcast. Harness:
  `test_supreme_healing.py` (+1 end-to-end claim-path test). Remaining from
  the survey: the Potent Spellcasting `/cast_spell` read-site + the
  Wildfire Spirit summon.
- **v2.1004.0 ("The Cantrip's Edge") — Potent Spellcasting Phase 2 read
  site** (Light/Knowledge/Grave/Peace Cleric Lv 8+): closes the deferred
  read the v2.612.1 install filed. New `_potent_spellcasting_bonus`
  (campaign_id, character_id, spell_level) — gate: cantrip (level 0) +
  the `potent-spellcasting-active` buff — clones the
  `_empowered_evocation_bonus` "+N to one damage roll" contract and
  threads through the SAME four sites: the `/cast_spell` spell-attack
  aggregate, the single-target NPC-save expression, the `/cast_spell`
  AoE-NPC first-target fallback, and the `/place_aoe` NPC loop (the
  pending-AoE ctx now stashes `spell_level`; a pre-deploy ctx without the
  key defaults to -1 so it can't read as a cantrip). Companion
  `feature_used(source=potent-spellcasting-bonus)` broadcast. Covers
  Sacred Flame / Toll the Dead (single-target) + Word of Radiance
  (place_aoe). Harness: `test_potent_spellcasting.py` (+1 end-to-end
  Sacred Flame test). **The survey remainder is now just the Wildfire
  Spirit summon** (`use_summon_wildfire_spirit` → `_summon_companion`).
- **v2.1005.0 ("The Kindled Ally") — Summon Wildfire Spirit stands up a
  real combatant** (Wildfire Druid Lv 2+, TCE p.38): closes the LAST item
  of the 2026-07-12 announce-only survey. New `wildfire-spirit` registry
  entry in `_COMPANION_TEMPLATES` (AC 13, fly-30-as-speed-30, Small); the
  endpoint calls `_summon_companion` with a level-scaled `hp=5 + 5 ×
  druid_lv` override and `_summon_initiative_for_body` (caster's init
  slot per RAW "acts on your turn"), so the spirit gets a controllable
  token + `is_summon`/`summoned_by` battle entry and rides the damage /
  HP / move / dismiss pipelines for free. Surfaces `summon_combatant_id`
  / `summon_token_id`. Still GM-narrated: Wild Shape / slot consumption
  + the 1-hour expiry. Harness: `test_summon_wildfire_spirit.py` (+1
  state-asserting battle_update test; the happy-path tests now dismiss
  their summons). **With this, every announce-only endpoint the survey
  flagged as cleanly mechanizable is wired** — what remains in the
  survey's lower-confidence bucket is the flag-buff-with-no-read-site
  family (Giant's Might / Bladesong / Arcane Ward / Invincible
  Conqueror / …), each of which needs its own read-site design, not a
  substrate ride.

- **v2.1008.0 ("The Widened Edge") — Superior Critical** (Champion
  Fighter Lv 17+): a passive read-site enhancement (no `use_*`
  endpoint) closing the crit-floor TODO the `_attacker_crit_threshold`
  docstring filed at v2.49.231. Improved Critical (Lv 3+) already
  dropped the natural-crit threshold 20 → 19; Superior Critical now
  drops it 19 → 18 at Lv 17+, in both the single-class fast path and
  the multiclass `classes[]` walk. The `/attack` crit-detection block
  already reads the helper (min'd with the on-hit-rider crit-range
  buff), so the wider range propagates with no call-site change.
  Champion is the SRD fighter subclass → SRD-valid. No Lv-17 PC exists
  in the demo (Garrik is Lv 7), so it's covered by in-process unit
  tests of the pure helper rather than a roll-batch harness test.
  Harness: `test_superior_critical_threshold.py` (+12).

- **v2.1009.0 ("The Last Breath") — Survivor** (Champion Fighter Lv
  18+): the Champion-subclass companion to Superior Critical. New
  `_pc_champion_survivor_regen(sheet)` returns `5 + CON mod` for a Lv
  18+ Champion (single-class + multiclass), `None` otherwise. The
  turn-advance start-of-turn hook (right after `_tick_auras`, so an
  aura heal that lifts the Champion above half suppresses Survivor
  that turn) applies the regen via `_apply_heal_to_combatant` when the
  active combatant is at `0 < current ≤ max // 2` HP, and broadcasts a
  `💚 Survivor` feature_used card. RAW's "no benefit at 0 HP" rides
  the `current > 0` gate. Fully automatic — nothing GM-tracked.
  SRD-valid (Champion). No Lv-18 PC in the demo, so unit-tested on the
  helper. Harness: `test_champion_survivor_regen.py` (+12).

- **v2.1010.0 ("The Overload") — Overchannel** (Evocation Wizard Lv
  14+): the marquee Evocation capstone, and the first Phase 8 ship to
  add a genuinely new spell-damage read-site (not just a passive gate).
  `POST /use_overchannel` arms a one-shot `overchannel-armed` buff
  (carrying the per-long-rest use number); when the armed caster casts
  a damaging 1st-5th level spell, the two `/cast_spell` NPC-auto-damage
  sites (single-target save + AoE loop) max every roll via the existing
  `_max_dice_total` (the Supreme Healing maximiser), drop the buff, and
  apply the escalating necrotic self-damage (`use_number × spell_level`
  d12, untyped so resistance can't reduce it) on the 2nd+ use since a
  long rest. Every read is gated behind the armed buff → a complete
  no-op for unarmed casts, so the hot damage path is unchanged for
  everyone else. The demo Evocation Wizard (Thalindra) PATCHes to Lv 14
  so this is happy-path harness-tested end-to-end (unlike the Champion
  Lv 17/18 features). Phase 2 (filed): the attack-roll spell-damage
  path + `/place_aoe` aren't maxed yet; PC client-rolled damage stays
  GM-narrated. Harness: `test_overchannel.py` (+7) +
  `test_overchannel_self_damage.py` (+9).

- **v2.1011.0 ("The Lower Planes") — Hurl Through Hell** (The Fiend
  Warlock Lv 14+): `POST /use_hurl_through_hell` validates a Fiend
  Warlock Lv 14+, auto-bootstraps a 1/long-rest `hurl-through-hell`
  resource (reset by the long-rest flow), and applies 10d10 psychic to
  the target via `_apply_damage_to_combatant` — unless the target's
  creature type is `fiend` (RAW exemption, `_attacker_creature_type`).
  Rides an attack you already made, so no economy chip is marked. The
  end-of-next-turn timing + planar banishment stay GM-narrated. The
  demo Fiend Warlock (Magnus) PATCHes to Lv 14 so it's happy-path
  harness-tested end-to-end. Harness: `test_hurl_through_hell.py` (+7).

The Lv-17 cleric subclass capstone batch is **6/6 shipped** — Improved
Reaper closed at v2.158.9 (install) + v2.158.41 (the `_pc_improved_reaper_params`
`/cast_spell` read site); the earlier "5/6, Improved Reaper is the last" note
was stale. Then the
Lv-15 / Lv-18 / Lv-20 capstones (Arcane Charge / Purity of Spirit /
Arcane Mastery / Emissary of Redemption / Improved War Magic / …) and
the Phase-2 read sites for the deferred Phase-1 commits (Keeper of
Souls on-death hook, Order's Wrath ally-hit trigger, Improved Duplicity
parameter read site).

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
