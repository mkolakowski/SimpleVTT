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
