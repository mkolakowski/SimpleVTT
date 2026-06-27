# Automation coverage — feature-endpoint audit

**Status:** ✅ shipped (Phase 0 of [full-feature-automation.md](plans/full-feature-automation.md)) · generated v2.99.447, counts regenerated v2.158.35 by [`scripts/classify_feature_endpoints.py`](../scripts/classify_feature_endpoints.py)
**What this is:** the living tally of every `use_*` / `cast_*` class-feature
endpoint in `app/routes/tabletop_routes.py`, tagged **tracked** (server-applies
its mechanical effect and/or spends its resource) vs **announce-only** (validates
+ broadcasts a `feature_used` card but leaves the effect to the GM), with the
automation **archetype** each one matches. This is the backlog the rest of the
parent plan burns down.

## How to regenerate

This table is **heuristic + machine-generated** — an endpoint is tagged
`tracked` when its body calls a state-mutating primitive (`_install_buff`,
`_apply_damage_to_combatant`, `_grant_temp_hp`, `_force_move`,
`_summon_companion`, `_resolve_feature_save`, `_tick_auras`, …) or a
resource/economy decrement (`_mark_battle_economy`, `resource_update`,
`flag_modified(char…)`, a spell-slot `used` bump). `announce-only` = only a
`feature_used` broadcast with no state mutation detected. Re-run the classifier
after a batch of retrofits and update the counts below — the heuristic lives in
[`scripts/classify_feature_endpoints.py`](../scripts/classify_feature_endpoints.py)
(`python3 scripts/classify_feature_endpoints.py`). Treat the split as
**±a few**: a few `announce-only`-tagged features are *narration-only by design*
(archetype J — passive senses, language grants), a few are retrofitted but apply
their effect in a *different* code path (e.g. `scornful_rebuke`, `supreme_healing`,
`ancestral_protectors`, `assassinate` fire inside `_apply_damage_to_combatant` or
via a Phase-1 install + deferred read, so the endpoint body itself reads
announce-only to the classifier), and a few `tracked`-tagged ones only spend a
resource without a downstream effect.

## Summary (counts regenerated v2.612.2)

| Status | Count | Meaning |
|---|---|---|
| ✅ **tracked** | **289** | server-applies effect and/or spends resource |
| ⚪ **announce-only** | **35** | validates + broadcasts; effect left to the GM |
| 🔧 mechanical | **8** | helper endpoints (not `feature_used` features) |
| **Total** | **332** | `use_*` / `cast_*` endpoints |

> The per-slug table further down still pins the v2.158.35 snapshot in
> places — it drifts behind the classifier between full reconciliations.
> The summary row above is the freshly-regenerated truth
> (`python3 scripts/classify_feature_endpoints.py`). Recent Phase-8
> flag-buff flips: `potent_spellcasting` (v2.612.1), `totem_spirit`
> (v2.612.2) — both announce-only → tracked.

At the plan's baseline (v2.99.385) the split was **~60 tracked / ~156
announce-only**. Phases 1–6 (feature-use registry, on-hit riders, feature
saves, temp-HP + roll bonuses, auras, movement + summons) flipped **~118**
endpoints to tracked — the engine-gap work is done; what's left is the
announce-only tail below (much of it archetype J, narration-only-OK).

## Phase status (parent plan)

| Phase | Primitive | Status |
|---|---|---|
| P0 — automation audit | this doc | ✅ shipped v2.99.447 |
| P1 — feature-use registry (`_FEATURE_USES`) | use-per-rest counters | ✅ |
| P2 — on-hit rider registry (`_ATTACK_RIDERS`) | +Xd riders | ✅ v2.99.395–.403 |
| P3 — feature save resolver (`_resolve_feature_save`) | save-or-condition | ✅ v2.99.405–.414 |
| P4 — temp-HP + roll-bonus (`_grant_temp_hp`) | +tempHP/+AC/+save | ✅ v2.99.415–.423 |
| P5 — auras (`_tick_auras`) | radius effects | ✅ v2.99.424–.429 (+ Aura of Conquest v2.99.448) |
| P6 — movement + summons (`_force_move`, `_summon_companion`) | push/pull + companions | ✅ v2.99.431–.446 |
| P7 — reactions breadth | new reaction kinds | ⚪ not started |
| P8 — higher-level subclass features | composition on primitives | 🟠 started v2.158.0 — **Twelve-class diversification arc CLOSED — full PHB class coverage:** cleric (Lv-17 batch 6/6) + paladin + fighter (EK 2/2) + druid + warlock + sorcerer + bard + rogue + monk + wizard + barbarian + ranger (Vanish v2.158.21). Plus engine improvements: v2.158.1 PC `_resistance_halve` F6 hotfix + v2.158.7 monster_slug HD resolve hotfix |
| P9 — test-contract upgrade | assert state not broadcast | 🟢 ongoing |

## Archetype legend

`A` use-per-rest counter · `B` on-hit damage rider · `C` save-or-condition ·
`D` self-buff · `E` ally-buff / aura · `F` temp-HP grant · `G` forced
movement / speed · `H` summon / token · `I` reaction · `J` announce-only-OK
(pure narration). See [full-feature-automation.md §3](plans/full-feature-automation.md)
for the archetype → primitive mapping.

## Notable announce-only backlog (candidates for automation)

> **⚠ Classifier drift (noted v2.665.0).** The ⚪ announce-only tags in the
> per-endpoint table below are pinned to an old classifier run and are **stale
> for several rows** — Aura of Warding, Fancy Footwork, Relentless Avenger,
> Unwavering Mark, Order's Wrath, and Improved Duplicity were all found
> already-mechanized when spot-checked. **Verify in code (grep the endpoint
> body for `_install_buff` / a mechanical read site) before picking a row to
> automate** — don't trust the tag alone. Re-running the classifier would
> correct the counts; until then this table over-states the announce-only set.

Most of the 59 announce-only rows are **archetype J** (narration /
passive senses: `beast_speech`, `devils_sight`, `eldritch_sight`,
`mask_of_many_faces`, `eyes_of_the_rune_keeper`, `improved_minor_illusion`, …)
or passive damage-boosters that already ride other code paths
(`potent_spellcasting`, `empowered_evocation`, `sculpt_spells`, `foe_slayer`,
`spell_bombardment`). The genuinely-automatable tail:

- **Auras (E):** `aura_of_warding` ✅ v2.133.0–v2.135.1 (full RAW chain — `is_spell` plumbing through `_apply_damage_to_combatant` + `resistance_spell_damage` buff payload via `_tick_auras`); `ancestral_protectors` ✅ v2.136.0–v2.138.0 (install on raging melee hit → attacker-side disadvantage gate + attacker-side damage halving); `unwavering_mark` ✅ v2.139.0–v2.141.0 (install on melee hit + 5-ft disadvantage gate + `/use_unwavering_punish` bonus-action endpoint). `aura_of_conquest` ✅ v2.99.448 condition gate; `aura_of_alacrity` ✅ v2.99.449 buff-payload.
- **On-being-hit retaliation (new primitive):** `scornful_rebuke` ✅ v2.142.0 — first on-damage-taken hook in `_apply_damage_to_combatant`; Conquest Paladin Lv 15+ auto-deals `max(1, CHA mod)` psychic to the attacker. Sibling to the on-hit-rider, aura-tick, and condition-install paths.
- **On-hit / extra-attack:** `assassinate` ✅ v2.131.0–v2.132.0 (auto-crit on surprised + advantage vs not-yet-acted; uses `target_surprised: bool` body flag + the new combatant `has_acted` field). `genies_wrath` ✅ v2.99.450 flat rider; `horde_breaker` ✅ v2.99.451 + `dread_ambusher` ✅ v2.99.452 server-resolved extra attacks.
- **Buff / temp-HP (D/F):** `supreme_healing` ✅ v2.143.0 (heal pipeline max-dice substitution via the new `_max_dice_total` helper); `combat_inspiration` ✅ v2.144.0–v2.145.0 (damage half — roll BI die + apply to target; AC half — calculator returning the boosted-AC outcome); `blade_flourish` ✅ v2.146.0 (shared damage half — Defensive/Slashing/Mobile riders deferred). `rallying_cry` ✅ v2.99.454 heals allies; `grim_harvest` ✅ v2.99.457 + `protective_spirit` ✅ v2.99.458 self-heals.
- **Movement (G):** `ascendant_step` ✅ v2.147.0 (levitate buff carrying `fly_speed_ft: 10` + concentration); `fancy_footwork` ✅ v2.148.0 (Phase 1 install of the OA-block mark on the target — OA-flow read deferred to Phase 2); `relentless_avenger` ✅ v2.149.0 (Phase 1 install of the free-move budget + OA-immune flag — `/token/move` read deferred to Phase 2). `stormborn` ✅ v2.99.459 fly buff.

## Recent retrofits (v2.128.2 – v2.158.21)

| Feature | Phases shipped | Notes |
|---|---|---|
| Up-cast tail | per-two-slot parser (v2.129.0), flat-bonus parser + scaler (v2.130.0) | Closes Aid / Heal / False Life / Flame Blade / Spiritual Weapon classes of up-cast prose; `parse_upcast_dice` now handles 3 RAW shapes (per-1 dice, per-2 dice, flat-N) |
| Assassinate | auto-crit (v2.131.0) + advantage (v2.132.0) | `target_surprised: bool` body field; new combatant `has_acted` field flipped on turn-advance |
| Aura of Warding | engine plumbing (v2.133.0) + endpoint install (v2.134.0) + Phase 4 tick test (v2.135.0) + Phase 1.5 deferred-site threading (v2.135.1) | `is_spell` plumbed through `_apply_damage_to_combatant` + `_resistance_halve` + `_resistance_halve_npc`; aura emitter buff installs `resistance_spell_damage` on allies + the emitter buff itself carries the flag for the caster's "you and …" half |
| Ancestral Protectors | install (v2.136.0) + disadvantage gate (v2.137.0/.1) + damage halving (v2.138.0) | Three-pass RAW chain; the helper `_attacker_marked_by_ancestral_protectors_vs_other` is shared between the adv/dis and damage halving paths |
| Unwavering Mark | install (v2.139.0) + 5-ft disadvantage gate (v2.140.0) + bonus-action punish endpoint (v2.141.0) | `_distance_ft_between_chars` 5-ft gate distinguishes UM from AP; `/use_unwavering_punish` rolls 2d20kh1 + weapon damage + flat half-fighter-level bonus |
| Scornful Rebuke | on-damage-taken hook (v2.142.0) | New primitive — fires inside `_apply_damage_to_combatant` PC branch after `_maybe_concentration_save`; recursive psychic damage to attacker (with `is_attack=False` to break ping-pong) |
| Supreme Healing | heal-pipeline max-dice substitution (v2.143.0) | New `_max_dice_total` helper parses any dice expression and returns max(N*M) per term; `/cast_spell` heal block branches on `_pc_has_life_domain(sheet, 17)` and substitutes the max value. `auto_heal_breakdown` surfaces `💗 Supreme Healing` prefix + `[max:8]` markers |
| Combat Inspiration | damage half (v2.144.0/.1) + AC half (v2.145.0) | Damage: `mode=damage` + `target_combatant_id` rolls the BI die and applies bonus damage through `_apply_damage_to_combatant`. AC: `mode=ac` + `attack_total` + `target_ac` returns a pure calculator response with `ac_new_ac` + `ac_would_miss` |
| Blade Flourish | shared damage half (v2.146.0) | Same shape as CI damage half — when `target_combatant_id` + `damage_type` are provided, rolls the BI die and applies bonus damage. Defensive AC buff + Mobile push + Slashing secondary-target routing deferred to Phase 2 |
| Ascendant Step | levitate buff install (v2.147.0) | Mirrors v2.99.459 Stormborn — installs `ascendant-step-levitate` with `effects.fly_speed_ft: 10` (vertical-only per RAW) + `concentration: True`. SimpleVTT's 2D map keeps altitude narrative-only |
| Fancy Footwork | OA-block mark on target (v2.148.0) | Phase 1 — install `fancy-footwork-blocked` buff on target with `effects.fancy_footwork_blocked_against_char_id`. Phase 2 (deferred): OA flow reads the buff and skips OAs against the named char_id |
| Relentless Avenger | free-move budget buff (v2.149.0) | Phase 1 — install `relentless-avenger-bonus-move` with `effects.free_movement_remaining_ft: base_speed // 2` + `effects.oa_immune_during_move: True`. Phase 2 (deferred): `/token/move` consumes the budget + skips OA prompts while immune. Generic shape can serve Mobile feat / Charger feat in the future |
| Avatar of Battle | permanent `nonmagical-X` resistance buff (v2.158.0 — Phase 8 kick-off) | War Domain Cleric Lv 17+. Endpoint installs the `avatar-of-battle` buff with `effects.resistance_to = ["nonmagical-bludgeoning","nonmagical-piercing","nonmagical-slashing"]` + `permanent: True` + `duration_rounds: 100000`. The v2.63.0 F6 `_resistance_matches_damage` matcher halves nonmagical BPS damage through `_apply_damage_to_combatant` + skips magical attacks per RAW. Idempotent on re-install via key dedupe. Pure composition on shipped primitives — sets the recipe for the Lv-17 cleric subclass capstone batch (Saint of Forge and Fire, Improved Reaper, Improved Duplicity, Keeper of Souls, Order's Wrath) |
| PC `_resistance_halve` F6 plumbing | hotfix shipped with Phase 8 kick-off (v2.158.1) | Threads `_apply_damage_to_combatant`'s existing `is_magical` flag down into `_resistance_halve` + swaps the per-entry literal `in` compare for the F6-aware `_resistance_matches_damage` matcher. Sheet-level `damage_resistances` + per-buff `effects.resistance_to` both route through it. Closes the gap where PC-side resistance ignored the SRD "X from nonmagical attacks" phrasing variants — the NPC side has had this matcher since v2.63.0 |
| Saint of Forge and Fire | permanent fire-immunity + nonmagical-BPS resistance buff (v2.158.2 — Phase 8 follow-up) | Forge Domain Cleric Lv 17+. Endpoint installs the `saint-of-forge-and-fire` buff with BOTH `effects.immunity_to=["fire"]` (read by `_immunity_zero`) AND `effects.resistance_to=["nonmagical-bludgeoning","nonmagical-piercing","nonmagical-slashing"]` (read by the v2.158.1-upgraded `_resistance_halve`). v1 simplification: BPS halving installs unconditionally pending a PC-armor-detection helper (Lv 17 Forge canonically wears heavy armor; the RAW conditional is treated as always-on for now). Pure composition — no new primitive |
| Improved Duplicity | permanent Invoke-Duplicity-parameter buff (v2.158.3 — Phase 8 third commit; Phase 1 of install-then-deferred-read split) | Trickery Domain Cleric Lv 17+. Endpoint installs the `improved-duplicity` buff with `effects.invoke_duplicity_max_duplicates=4` + `effects.invoke_duplicity_bonus_move_per_duplicate_ft=30` + `effects.invoke_duplicity_max_range_ft=120`. Invoke Duplicity itself isn't yet a server-side endpoint, so this captures the upgraded params for the future `/use_invoke_duplicity` read site (Phase 2 deferred). Same shape as v2.148.0 Fancy Footwork + v2.149.0 Relentless Avenger |
| Keeper of Souls | permanent watcher-flag buff (v2.158.4 — Phase 8 fourth commit; Phase 1 of install-then-deferred-read split) | Grave Domain Cleric Lv 17+. Endpoint installs the `keeper-of-souls-watcher` buff with `effects.keeper_of_souls_watcher: True` + `effects.keeper_of_souls_radius_ft: 60`. Phase 2 (deferred): on-death hook in `_apply_damage_to_combatant`'s NPC branch reads the buff, range-gates at 60 ft from the dying NPC, and auto-heals the watcher for the NPC's Hit Dice count. Manual announce path stays as the player-driven GM override. New pipeline event (on-death) is the natural Phase 8 follow-up; will also unlock auto-firing for Touch of Death (Death Cleric Lv 1 — already has v1 manual install) |
| Order's Wrath | target-side curse buff (v2.158.5 — Phase 8 fifth commit; Phase 1 of install-then-deferred-read split) | Order Domain Cleric Lv 17+. First Phase 8 commit to install on a target combatant (not the caster) via `_install_buff_on_combatant_id`. When `target_combatant_id` supplied, installs the `orders-wrath-curse` buff with `effects.orders_wrath_psychic_damage_expression="2d8"` + `effects.orders_wrath_caster_char_id=<cleric.id>` + `effects.orders_wrath_active=True`, duration 2 rounds. Phase 2 (deferred): `/attack` hit by an ally against a cursed target deals 2d8 psychic + drops the curse. When no target supplied, falls back to historical announce-only behavior |
| Keeper of Souls Phase 2 (on-death hook) | new pipeline primitive (v2.158.6) | Closes the Phase 2 of v2.158.4's install-then-deferred-read split. New helper `_fire_keeper_of_souls_on_npc_death` walks PC combatants for the v2.158.4 watcher buff, range-gates at 60 ft via `_combatant_token` + `_distance_ft_between_points`, parses dying NPC's HD count from token template's `hit_dice` field (regex `(\d+)d`), auto-heals each in-range watcher via `_apply_heal_to_combatant`, broadcasts `feature_used` with source `keeper-of-souls-trigger`. Wired into the NPC branch of `_apply_damage_to_combatant` after the 0-HP transition. Defensive try/except so a feature-hook failure can never break the damage pipeline. Sibling primitive shape to v2.142.0 Scornful Rebuke (on-damage-taken) — first new pipeline event since that commit. Future on-death features reuse this hook point |
| Order's Wrath Phase 2 (ally-hit trigger) | on-attack-hit hook (v2.158.8) | Closes the Phase 2 of v2.158.5's install-then-deferred-read split. New helper `_fire_orders_wrath_on_attack_hit` wires into BOTH PC + NPC branches of `_apply_damage_to_combatant` after damage applies. Checks `orders-wrath-curse` buff on target + verifies attacker isn't the curse caster, rolls 2d8 psychic, applies via the damage pipeline (recursive with `is_attack=False` to prevent loop), drops the curse in place. Broadcasts `feature_used` source `orders-wrath-trigger`. Order in NPC branch: damage applies → break-on-damage → Order's Wrath trigger → Keeper of Souls on 0-HP (so a psychic-damage kill chains correctly into Keeper of Souls) |
| Improved Reaper | permanent necromancy-dual-target flag buff (v2.158.9 — Phase 8 final cleric-capstone commit) | Death Domain Cleric Lv 17+. Phase 1 of install-then-deferred-read split. Installs `improved-reaper-active` buff with six `improved_reaper_*` effect keys (active, min_spell_level=1, max_spell_level=5, school="necromancy", max_targets=2, max_target_separation_ft=5). Phase 2 (deferred): `/cast_spell` reads the buff and accepts a second `target_combatant_id` when the spell qualifies (necromancy school, levels 1-5, default single-target shape). **CLOSES the Lv-17 cleric subclass capstone batch 6/6 in v2.158.x** |
| Purity of Spirit | permanent PFE&G class-feature buff (v2.158.10 — Phase 8 step-out to Lv-15 tier) | Devotion Paladin Lv 15+. Installs `purity-of-spirit` buff carrying the same `pfeag_*` effects payload as the cast Protection from Evil and Good spell (six protected creature types + attackers-disadvantage flag + charm/frighten/possess-immunity flag + save-advantage flag). The two existing engine read sites (`_target_attackers_have_pfeag_disadvantage_against_type` + `_pc_has_pfeag_against_type`) were extended to accept either `key="purity-of-spirit"` or `key="protection-from-evil-and-good"` so the class-feature buff reuses the spell-buff engine wholesale. Distinct key so a cast PfE&G spell on top doesn't collide. Sets the engine-reuse pattern for future PFE&G-shape features |
| Arcane Charge | permanent teleport-budget flag buff (v2.158.11 — Phase 8 Lv-15 tier) | Eldritch Knight Fighter Lv 15+. Phase 1 of install-then-deferred-read split. Installs `arcane-charge-active` buff with two `arcane_charge_*` effect keys (`teleport_max_ft=30`, `requires_action_surge=True`). Phase 2 (deferred): `/use_action_surge` reads the buff + surfaces the teleport budget (before/after the additional action per RAW); the actual move uses existing `_force_move` / movement primitives. Sibling commit to v2.158.10 Purity of Spirit — both step Phase 8 out into the Lv-15 tier |
| Improved War Magic | permanent Lv-1+ spell-threshold flag buff (v2.158.12 — Phase 8 Lv-18 tier; EK 2/2 close) | Eldritch Knight Fighter Lv 18+. Endpoint was already chip-marked pre-Phase-8 (so it was tracked); the Phase 8 enhancement adds the `improved-war-magic-active` flag buff with two `improved_war_magic_*` effect keys (active=True, min_spell_level=1). Phase 2 (deferred): War Magic / `/cast_spell` flow reads the buff and allows the bonus-action weapon attack rider when the cast spell's level >= 1 (vs the Lv-7 War Magic cantrip-only limit). Closes EK 2/2 Phase 8 tracked features |
| Star Map | permanent buff + auto-bootstrap resource (v2.158.13 — Phase 8 Druid diversification) | Stars Druid Lv 2+ (Tasha's). Two-part Phase 1: install `star-map-active` buff with three `star_map_*` effect keys (active=True, free_guiding_bolt_uses_max=WIS_mod min 1, always_prepared=["Guidance","Guiding Bolt"]) + auto-bootstrap a `guiding-bolt-charges` resource on the sheet (max=WIS_mod min 1, reset=long) if missing — delivers on the original v2.99.316 docstring promise. The existing rest-character flow now refills Guiding Bolt charges on long rest automatically. Phase 2 (deferred): `/cast_spell` reads the buff + lets Guiding Bolt route through the resource decrement instead of consuming a slot. **First Druid subclass feature flipped from announce-only to tracked.** |
| Devil's Sight | permanent vision-parameter flag buff (v2.158.14 — Phase 8 Warlock diversification) | Warlock Lv 2+ Eldritch Invocation. Installs `devils-sight-active` buff with two `devils_sight_*` effect keys (`range_ft: 120` + `through_magical_darkness: True`). Phase 2 (deferred): a `_pc_sees_in_darkness(sheet)` helper + darkness-modifier resolver short-circuit the "attacker/target in darkness" disadvantage adjudication at attack-roll time when the warlock is within 120 ft of the target through magical darkness + skip the install of a `blinded` condition from a darkness-trigger source. Closes the v2.99.131 filed item. **First Warlock invocation flipped from announce-only to tracked.** |
| Spell Bombardment | permanent max-die-reroll parameter flag buff (v2.158.15 — Phase 8 Sorcerer diversification; closes the six-class arc) | Wild Magic Sorcerer Lv 18+. Already chip-tracked pre-Phase-8 via `_is_spell_bombardment_used` / `_mark_spell_bombardment_used`; the Phase 8 enhancement adds the `spell-bombardment-active` flag buff with three `spell_bombardment_*` effect keys (active=True, die_sizes=[4,6,8,10,12], uses_per_turn=1). Phase 2 (deferred): `/cast_spell` damage-roll path auto-detects max-rolled dice in the per-die breakdown, checks the buff + once-per-turn flag, and surfaces a one-click "reroll this max die" option. **First Sorcerer subclass feature flipped to tracked this session; closes the cleric/paladin/fighter/druid/warlock/sorcerer six-class diversification arc.** |
| Silver Tongue | permanent d20-floor parameter flag buff (v2.158.16 — Phase 8 Bard diversification; pushes the arc to 7/12 classes) | Eloquence College Bard Lv 3+. Installs `silver-tongue-active` buff with three `silver_tongue_*` effect keys (min_d20=10, skills=["persuasion","deception"], ability="CHA"). Phase 2 (deferred): ability-check roll resolver reads the buff and applies the min-10 floor to the d20 result on CHA Persuasion/Deception checks. Pattern reusable for Reliable Talent (Rogue Lv 11 — d20 floor 10 on prof skills) and similar floor-the-d20 features. **First Bard subclass feature flipped to tracked this session; pushes the diversification arc to 7/12 classes.** |
| Mage Hand Legerdemain | permanent spell-task parameter flag buff (v2.158.17 — Phase 8 Rogue diversification; pushes the arc to 8/12 classes) | Arcane Trickster Rogue Lv 3+. Installs `mage-hand-legerdemain-active` buff with four `mage_hand_legerdemain_*` effect keys (range_ft=30, invisible=True, bonus_action_control=True, unnoticed_check="sleight_of_hand_vs_passive_perception"). Phase 2 (deferred): Mage Hand cast flow reads the buff and surfaces the Legerdemain task picker (stow/retrieve from another's container, pick locks/disarm traps at range). **First Rogue subclass feature flipped to tracked this session; pushes the diversification arc to 8/12 classes.** |
| Drunken Technique | 1-turn Flurry-of-Blows rider buff (v2.158.18 — Phase 8 Monk diversification; pushes the arc to 9/12 classes) | Way of the Drunken Master Monk Lv 3+. Installs a 1-turn `drunken-technique-active` buff with `effects.disengage: True` (reuses the engine flag from Step of the Wind so the OA-prompting flow already half-consumes it) + two Drunken-Technique-specific flags (`speed_bonus_ft: 10`, `rider_of: "flurry-of-blows"`). Different shape from the permanent-passive Phase 8 commits — a 1-turn rider that expires at next turn-start tick per RAW. Engine-flag reuse pattern half-implements Phase 2 already via the existing OA-prompting flow. **First Monk subclass feature flipped to tracked this session; pushes the diversification arc to 9/12 classes.** |
| Empowered Evocation | permanent +INT-damage parameter flag buff (v2.158.19 — Phase 8 Wizard diversification; pushes the arc to 10/12 classes) | Evocation School Wizard Lv 10+. Installs `empowered-evocation-active` buff with three `empowered_evocation_*` effect keys (active=True, int_mod=<computed at install time>, school="evocation"). Phase 2 (deferred): `/cast_spell` reads the buff for evocation spells + lets the player apply +INT to one damage roll per cast. **First Wizard subclass feature flipped to tracked this session; pushes the diversification arc to 10/12 classes.** |
| Form of the Beast | 10-round natural-weapon parameter buff (v2.158.20 — Phase 8 Barbarian diversification; pushes the arc to 11/12 classes) | Path of the Beast Barbarian Lv 3+ (TCE). 10-round rage-duration `form-of-the-beast-active` buff with six `form_of_the_beast_*` effect keys (active=True, form, damage_die, damage_type, reach_ft, special) capturing the chosen natural weapon's parameters. Phase 2 (deferred): `/attack` reads the buff and renders Bite/Claws/Tail as a built-in attack option while the buff is active. **First Barbarian subclass feature flipped to tracked this session; pushes the diversification arc to 11/12 classes.** |
| Vanish | permanent passive parameter flag buff (v2.158.21 — Phase 8 Ranger diversification; **CLOSES the 12/12 arc — full PHB class coverage**) | Ranger Lv 14+ (PHB). Endpoint was already chip-tracked pre-Phase-8 (bonus-action slot); the Phase 8 enhancement adds the permanent passive `vanish-active` buff with three `vanish_*` effect keys (active=True, hide_as_bonus_action=True, untrackable_nonmagical=True). Phase 2 (deferred): (a) action-UI surfaces Hide as a bonus-action option when the buff is present + ranger_lv >= 14; (b) any future non-magical tracking-check resolver short-circuits when the target carries `vanish_untrackable_nonmagical`. **First Ranger subclass feature given a Phase-8 buff payload this session; closes the twelve-class diversification arc at 12/12 — every PHB class now has at least one Phase-8 buff-payload feature.** |

## Full classification

| Endpoint | Status | Detected mechanic / archetype |
|---|---|---|
| `cast_bane` | ✅ tracked | A use/resource |
| `cast_bestow_curse` | ✅ tracked | A use/resource |
| `cast_compulsion` | ✅ tracked | A use/resource |
| `cast_conjure_animals` | ✅ tracked | H summon |
| `cast_find_familiar` | ✅ tracked | H summon |
| `cast_flesh_to_stone` | ✅ tracked | D buff-install, D/E buff-install |
| `cast_gust` | ✅ tracked | G forced-move |
| `cast_hex` | ✅ tracked | D buff-install |
| `cast_hold_monster` | ✅ tracked | D buff-install, D/E buff-install |
| `cast_hold_person` | ✅ tracked | D buff-install, D/E buff-install |
| `cast_hunters_mark` | ✅ tracked | D buff-install |
| `cast_polymorph` | ✅ tracked | A use/resource |
| `cast_sleep` | ✅ tracked | D buff-install, D/E buff-install |
| `cast_slow` | ✅ tracked | D buff-install, D/E buff-install |
| `cast_spell` | ✅ tracked | D buff-install, D/E buff-install, damage, heal, heal/damage |
| `cast_web` | ✅ tracked | D buff-install, D/E buff-install |
| `use_abjure_enemy` | ✅ tracked | v2.681.0 — resolves the target's WIS save via `_resolve_feature_save` (NPC inline, PC via RollRequest) + installs Frightened (repeated save) on a fail; speed-0/halved mutation GM-narrated |
| `use_action_surge` | ✅ tracked | A use/resource |
| `use_adjust_density` | ✅ tracked | A use/resource |
| `use_animal_companion` | ✅ tracked | H summon, damage |
| `use_arcane_charge` | ✅ tracked | D buff-install (Action-Surge teleport-budget flags) |
| `use_arcane_deflection` | ✅ tracked | A use/resource |
| `use_arcane_recovery` | ✅ tracked | A use/resource |
| `use_arcane_shot` | ✅ tracked | A use/resource |
| `use_arcane_ward` | ✅ tracked | A use/resource |
| `use_arms_of_the_astral_self` | ✅ tracked | A use/resource |
| `use_aura_of_alacrity` | ✅ tracked | D buff-install |
| `use_aura_of_conquest` | ✅ tracked | D buff-install, E aura |
| `use_aura_of_the_guardian` | ✅ tracked | v2.694.0 — with `ally_combatant_id` + `damage_amount`, redirects the damage server-side: heals the ally back (`_apply_heal_to_combatant`) + applies it to the Paladin as untyped/unreducible (`_apply_damage_to_combatant`); announce-only without redirect args |
| `use_avatar_of_battle` | ✅ tracked | D buff-install |
| `use_avenging_angel` | ✅ tracked | D buff-install |
| `use_balm_of_the_summer_court` | ✅ tracked | v2.679.0 — with `target_combatant_id`, applies the rolled heal (`_apply_heal_to_combatant`) AND the per-die temp HP (`_grant_temp_hp`) to the same ally; announce-only without a target |
| `use_bardic_inspiration` | ✅ tracked | D buff-install |
| `use_bend_luck` | ✅ tracked | A use/resource |
| `use_bladesong` | ✅ tracked | A use/resource |
| `use_blessing_of_the_forge` | ✅ tracked | A use/resource |
| `use_blessing_of_the_trickster` | ✅ tracked | D buff-install |
| `use_champion_challenge` | ✅ tracked | C save-or-condition |
| `use_chronal_shift` | ✅ tracked | A use/resource |
| `use_cleansing_touch` | ✅ tracked | A use/resource |
| `use_combat_wild_shape` | ✅ tracked | A use/resource |
| `use_commanders_strike` | ✅ tracked | A use/resource |
| `use_conquering_presence` | ✅ tracked | C save-or-condition |
| `use_control_undead` | ✅ tracked | C save-or-condition |
| `use_corona_of_light` | ✅ tracked | A use/resource |
| `use_countercharm` | ✅ tracked | D buff-install |
| `use_cutting_words` | ✅ tracked | B on-hit-rider, C save-or-condition, D buff-install, D/E buff-install, G forced-move, damage, heal, heal/damage |
| `use_dark_ones_blessing` | ✅ tracked | F temp-HP |
| `use_devils_sight` | ✅ tracked | D buff-install (vision-parameter flags) |
| `use_diamond_soul_reroll` | ✅ tracked | A use/resource |
| `use_disarming_attack` | ✅ tracked | v2.692.0 — with `target_combatant_id` (trust-the-caller), applies the superiority die as bonus damage (`_apply_damage_to_combatant`) + rolls the STR save (`_resolve_feature_save`, `condition_buff=None`); drop-object outcome GM-narrated |
| `use_distracting_strike` | ✅ tracked | A use/resource |
| `use_drunken_technique` | ✅ tracked | D buff-install (1-turn Disengage rider + speed bonus) |
| `use_divine_fury` | ✅ tracked | D buff-install |
| `use_divine_intervention` | ✅ tracked | A use/resource |
| `use_draconic_presence` | ✅ tracked | C save-or-condition |
| `use_draconic_wings` | ✅ tracked | D buff-install |
| `use_dread_ambusher` | ✅ tracked | damage |
| `use_dreadful_strike` | ✅ tracked | D buff-install |
| `use_elder_champion` | ✅ tracked | D buff-install |
| `use_eldritch_master` | ✅ tracked | A use/resource |
| `use_eldritch_strike` | ✅ tracked | D buff-install |
| `use_elemental_affinity` | ✅ tracked | D buff-install |
| `use_emboldening_bond` | ✅ tracked | D buff-install |
| `use_emissary_of_peace` | ✅ tracked | A use/resource |
| `use_empowered_evocation` | ✅ tracked | D buff-install (+INT-damage parameter flags) |
| `use_empty_body` | ✅ tracked | D buff-install |
| `use_evasive_footwork` | ✅ tracked | A use/resource |
| `use_eyes_of_the_grave` | ✅ tracked | A use/resource |
| `use_fangs_of_the_fire_snake` | ✅ tracked | A use/resource |
| `use_fast_hands` | ✅ tracked | A use/resource |
| `use_favored_by_the_gods` | ✅ tracked | A use/resource |
| `use_feature` | ✅ tracked | D buff-install |
| `use_feinting_attack` | ✅ tracked | A use/resource |
| `use_fey_presence` | ✅ tracked | C save-or-condition |
| `use_fighting_spirit` | ✅ tracked | F temp-HP |
| `use_flurry_of_blows` | ✅ tracked | D buff-install |
| `use_foe_slayer` | ✅ tracked | D buff-install |
| `use_form_of_the_beast` | ✅ tracked | D buff-install (10-round rage natural-weapon parameter flags) |
| `use_font_of_magic_to_points` | ✅ tracked | A use/resource |
| `use_font_of_magic_to_slot` | ✅ tracked | A use/resource |
| `use_frenzy` | ✅ tracked | A use/resource |
| `use_gathered_swarm` | ✅ tracked | D buff-install |
| `use_genies_wrath` | ✅ tracked | D buff-install |
| `use_giant_killer` | ✅ tracked | A use/resource |
| `use_giants_might` | ✅ tracked | A use/resource |
| `use_glorious_defense` | ✅ tracked | A use/resource |
| `use_goading_attack` | ✅ tracked | A use/resource |
| `use_grapple` | ✅ tracked | D buff-install, D/E buff-install |
| `use_grim_harvest` | ✅ tracked | heal |
| `use_halo_of_spores` | ✅ tracked | v2.676.0 — with `target_combatant_id`, rolls the target's CON save server-side (NPC via template, PC via sheet) + applies the necrotic via `_apply_damage_to_combatant` (save-OR-NOTHING: full on fail, 0 on success); announce-only without a resolvable target |
| `use_hands_of_healing` | ✅ tracked | v2.674.0 — applies the rolled heal (Martial Arts die + WIS) to `target_combatant_id` via `_apply_heal_to_combatant` (caps at max HP, revives a dying PC); announce-only without a target |
| `use_healing_light` | ✅ tracked | v2.675.0 — applies the rolled pooled-d6 heal to `target_combatant_id` via `_apply_heal_to_combatant` (caps at max HP, revives a dying PC); announce-only without a target |
| `use_hexblades_curse` | ✅ tracked | D buff-install |
| `use_hide_in_plain_sight` | ✅ tracked | D buff-install |
| `use_holy_nimbus` | ✅ tracked | D buff-install |
| `use_horde_breaker` | ✅ tracked | damage |
| `use_hypnotic_gaze` | ✅ tracked | C save-or-condition |
| `use_improved_duplicity` | ✅ tracked | D buff-install (Invoke Duplicity parameter flags) |
| `use_improved_reaper` | ✅ tracked | D buff-install (necromancy dual-target flags) |
| `use_improved_war_magic` | ✅ tracked | A use/resource + D buff-install (Lv-1+ spell-threshold flag) |
| `use_indomitable` | ✅ tracked | D buff-install |
| `use_indomitable_reroll` | ✅ tracked | A use/resource |
| `use_insightful_fighting` | ✅ tracked | A use/resource |
| `use_inspiring_smite` | ✅ tracked | F temp-HP |
| `use_intimidating_presence` | ✅ tracked | v2.683.0 — with `target_combatant_id`, resolves the target's WIS save via `_resolve_feature_save` (NPC inline, PC via RollRequest) + installs Frightened (short fixed duration, no re-save) on a fail; announce-only without a target |
| `use_invincible_conqueror` | ✅ tracked | A use/resource |
| `use_item` | ✅ tracked | heal/damage |
| `use_keeper_of_souls` | ✅ tracked | D buff-install (watcher flag, Phase 1) |
| `use_kensei_shot` | ✅ tracked | D buff-install |
| `use_lay_on_hands` | ✅ tracked | heal/damage |
| `use_living_legend` | ✅ tracked | A use/resource |
| `use_lunging_attack` | ✅ tracked | A use/resource |
| `use_mage_hand_legerdemain` | ✅ tracked | D buff-install (Mage Hand spell-task parameter flags) |
| `use_maneuvering_attack` | ✅ tracked | A use/resource |
| `use_manifest_echo` | ✅ tracked | A use/resource |
| `use_mantle_of_inspiration` | ✅ tracked | v2.671.0 — applies `5 + bard_level` temp HP to each named ally (`target_combatant_ids`, capped at CHA-mod) via `_grant_temp_hp`; free reaction-move stays GM-narrated |
| `use_master_of_nature` | ✅ tracked | A use/resource |
| `use_master_of_tactics` | ✅ tracked | A use/resource |
| `use_menacing_attack` | ✅ tracked | C save-or-condition, D buff-install |
| `use_metamagic_careful_spell` | ✅ tracked | D buff-install |
| `use_metamagic_distant_spell` | ✅ tracked | D buff-install |
| `use_metamagic_empowered_spell` | ✅ tracked | D buff-install |
| `use_metamagic_extended_spell` | ✅ tracked | D buff-install |
| `use_metamagic_heightened_spell` | ✅ tracked | D buff-install |
| `use_metamagic_subtle_spell` | ✅ tracked | D buff-install |
| `use_metamagic_twinned_spell` | ✅ tracked | D buff-install |
| `use_minor_conjuration` | ✅ tracked | A use/resource |
| `use_mystic_arcanum` | ✅ tracked | A use/resource |
| `use_natural_recovery` | ✅ tracked | A use/resource |
| `use_natures_wrath` | ✅ tracked | v2.680.0 — resolves the target's STR/DEX save via `_resolve_feature_save` (NPC inline, PC via RollRequest) + installs Restrained (`_make_restrained_buff`, repeated save) on a fail |
| `use_open_hand_technique` | ✅ tracked | D buff-install, D/E buff-install, G forced-move |
| `use_orders_wrath` | ✅ tracked | D buff-install (target-side curse, Phase 1) |
| `use_parry` | ✅ tracked | A use/resource |
| `use_patient_defense` | ✅ tracked | D buff-install |
| `use_peerless_athlete` | ✅ tracked | A use/resource |
| `use_planar_warrior` | ✅ tracked | D buff-install |
| `use_portent` | ✅ tracked | A use/resource |
| `use_precision_attack` | ✅ tracked | A use/resource |
| `use_primeval_awareness` | ✅ tracked | A use/resource |
| `use_protective_field` | ✅ tracked | heal |
| `use_protective_spirit` | ✅ tracked | heal |
| `use_psychic_blades` | ✅ tracked | A use/resource |
| `use_purity_of_spirit` | ✅ tracked | D buff-install (permanent PFE&G effects) |
| `use_pushing_attack` | ✅ tracked | G forced-move (save→15-ft push via `_force_move`, v2.99.433). v2.691.0 — the superiority die also lands as bonus damage via `_apply_damage_to_combatant`; size gate GM-tracked |
| `use_radiant_sun_bolt` | ✅ tracked | A use/resource |
| `use_rage` | ✅ tracked | D buff-install |
| `use_rally` | ✅ tracked | F temp-HP |
| `use_rallying_cry` | ✅ tracked | heal |
| `use_rangers_companion` | ✅ tracked | A use/resource |
| `use_reaction` | ✅ tracked | D buff-install, damage, heal/damage |
| `use_rebuke_the_violent` | ✅ tracked | v2.672.0 — rolls the attacker's WIS save server-side (NPC via template, PC via sheet) + applies the reflected psychic via `_apply_damage_to_combatant` (full on fail, half on success); announce-only when the attacker has no resolvable sheet |
| `use_reckless_attack` | ✅ tracked | D buff-install |
| `use_restore_balance` | ✅ tracked | A use/resource |
| `use_riposte` | ✅ tracked | damage |
| `use_saint_of_forge_and_fire` | ✅ tracked | D buff-install (fire immunity + nonmagical-BPS resist) |
| `use_second_wind` | ✅ tracked | heal/damage |
| `use_shadow_arts` | ✅ tracked | A use/resource |
| `use_silver_tongue` | ✅ tracked | D buff-install (d20-floor parameter flags) |
| `use_skirmisher` | ✅ tracked | A use/resource |
| `use_slayers_prey` | ✅ tracked | D buff-install |
| `use_soul_of_vengeance` | ✅ tracked | A use/resource |
| `use_spirit_totem` | ✅ tracked | D buff-install, F temp-HP |
| `use_spell_bombardment` | ✅ tracked | A use/resource + D buff-install (max-die-reroll parameter flags) |
| `use_spiritual_weapon` | ✅ tracked | H summon, damage |
| `use_star_map` | ✅ tracked | D buff-install + auto-bootstrap guiding-bolt-charges resource |
| `use_steel_defender` | ✅ tracked | H summon, damage |
| `use_step_of_the_wind` | ✅ tracked | D buff-install |
| `use_stillness_of_mind` | ✅ tracked | A use/resource |
| `use_storm_aura` | ✅ tracked | Desert = auto-tick aura buff (v2.99.426). v2.677.0 — with `target_combatant_id`, Sea rolls the target's DEX save + applies the lightning save-for-half (`_apply_damage_to_combatant`) and Tundra grants temp HP (`_grant_temp_hp`); announce-only without a target |
| `use_stormborn` | ✅ tracked | D buff-install |
| `use_strength_of_the_grave` | ✅ tracked | A use/resource |
| `use_stroke_of_luck` | ✅ tracked | A use/resource |
| `use_stunning_strike` | ✅ tracked | D buff-install, D/E buff-install |
| `use_summon_wildfire_spirit` | ✅ tracked | A use/resource |
| `use_supreme_sneak` | ✅ tracked | D buff-install |
| `use_sweeping_attack` | ✅ tracked | A use/resource |
| `use_tales_from_beyond` | ✅ tracked | A use/resource |
| `use_telepathic_speech` | ✅ tracked | A use/resource |
| `use_tempestuous_magic` | ✅ tracked | A use/resource |
| `use_tentacle_of_the_deeps` | ✅ tracked | v2.678.0 — with `target_combatant_id`, rolls the melee spell attack vs the target's AC (`_read_target_ac`; nat 20 crits + doubles dice, nat 1 misses) + applies the cold on a hit via `_apply_damage_to_combatant`; speed reduction GM-narrated; announce-only without a target |
| `use_third_eye` | ✅ tracked | A use/resource |
| `use_thorn_whip` | ✅ tracked | G forced-move, damage |
| `use_thunderwave` | ✅ tracked | G forced-move, damage |
| `use_tides_of_chaos` | ✅ tracked | D buff-install |
| `use_touch_of_death` | ✅ tracked | F temp-HP |
| `use_trip_attack` | ✅ tracked | v2.690.0 — with `target_combatant_id` (trust-the-caller), applies the superiority die as bonus damage (`_apply_damage_to_combatant`) + resolves the STR save → Prone (`_resolve_feature_save`; NPC inline, PC via RollRequest); size gate GM-tracked |
| `use_turn_the_faithless` | ✅ tracked | v2.682.0 — resolves each target's WIS save via `_resolve_feature_save` (AoE loop; NPC inline, PC via RollRequest) + installs Turned (ends on damage) on a fail; fey/fiend filter GM-tracked |
| `use_turn_the_unholy` | ✅ tracked | D buff-install, D/E buff-install |
| `use_undying_sentinel` | ✅ tracked | v2.693.0 — brings the caster to exactly 1 HP via `_apply_heal_to_combatant` (heal `1 - current`; flips dying → alive), the Protective Spirit self-apply shape; surfaces `hp_after`/`revived` |
| `use_vanish` | ✅ tracked | A use/resource + D buff-install (Lv-14 passive parameter flags) |
| `use_vigilant_blessing` | ✅ tracked | D buff-install |
| `use_visions_of_the_past` | ✅ tracked | A use/resource |
| `use_voice_of_authority` | ✅ tracked | A use/resource |
| `use_vow_of_enmity` | ✅ tracked | D buff-install |
| `use_war_magic` | ✅ tracked | A use/resource |
| `use_war_priest` | ✅ tracked | A use/resource |
| `use_warding_flare` | ✅ tracked | A use/resource |
| `use_watchers_will` | ✅ tracked | A use/resource |
| `use_weapon_bond` | ✅ tracked | A use/resource |
| `use_wholeness_of_body` | ✅ tracked | heal/damage |
| `use_wizardly_quill` | ✅ tracked | A use/resource |
| `use_wrath_of_the_storm` | ✅ tracked | v2.673.0 — with `attacker_combatant_id`, rolls the attacker's DEX save server-side (NPC via template, PC via sheet) + applies the 2d8 via `_apply_damage_to_combatant` (full on fail, half on success); free-form `attacker_name` stays announce-only |
| `use_ancestral_protectors` | ⚪ announce-only | — |
| `use_arcane_mastery` | ⚪ announce-only | — |
| `use_ascendant_step` | ⚪ announce-only | — |
| `use_assassinate` | ✅ tracked | mechanized in `/attack` (v2.131.0–v2.132.0): auto-crit vs `target_surprised` + advantage vs a target whose `has_acted` is False, gated on `_pc_has_assassin_subclass`. The `use_assassinate` endpoint is the chat-log declaration (a v2.665.0 flag-buff attempt was reverted v2.670.1 as redundant — its flags were never read) |
| `use_aura_of_warding` | ⚪ announce-only | — |
| `use_awakened_mind` | ⚪ announce-only | — |
| `use_beast_speech` | ⚪ announce-only | — |
| `use_beguiling_influence` | ⚪ announce-only | — |
| `use_blade_flourish` | ✅ tracked | Defensive Flourish AC self-buff v2.158.66; +10 ft walking-speed `speed_bonus_ft` buff v2.667.0 (rides `effective_speed_walk`) |
| `use_bonus_cantrip` | ⚪ announce-only | — |
| `use_combat_inspiration` | ⚪ announce-only | — |
| `use_dash` | ⚪ announce-only | — |
| `use_eldritch_sight` | ⚪ announce-only | — |
| `use_emissary_of_redemption` | ⚪ announce-only | — |
| `use_expansive_bond` | ⚪ announce-only | — |
| `use_eyes_of_the_rune_keeper` | ⚪ announce-only | — |
| `use_fancy_footwork` | ⚪ announce-only | — |
| `use_flesh_to_stone_make_permanent` | ⚪ announce-only | — |
| `use_improved_minor_illusion` | ⚪ announce-only | — |
| `use_invocation` | ⚪ announce-only | — |
| `use_mask_of_many_faces` | ⚪ announce-only | — |
| `use_minor_alchemy` | ⚪ announce-only | — |
| `use_mote_of_potential` | ✅ tracked | v2.670.0 — attack mode applies 1d{die} force damage (`_apply_damage_to_combatant`) + save mode grants 1d{die}+CHA temp HP (`_grant_temp_hp`); check mode stays GM-narrated |
| `use_potent_spellcasting` | ✅ tracked | v2.612.1 — installs permanent `potent-spellcasting-active` flag-buff (`potent_spellcasting_*`: active/wis_mod/class); Phase 8 cleric/cantrip twin of Empowered Evocation |
| `use_relentless_avenger` | ⚪ announce-only | — |
| `use_scornful_rebuke` | ⚪ announce-only | — |
| `use_sculpt_spells` | ✅ tracked | v2.669.0 — installs a `sculpt-spells-active` protection buff riding the Careful Spell auto-pass substrate (`_caster_has_careful_pending_buff` matches the key); protected creatures auto-succeed + take no damage from the evocation AoE |
| `use_supreme_healing` | ⚪ announce-only | — |
| `use_totem_spirit` | ✅ tracked | v2.612.2 — installs permanent `totem-spirit-active` flag-buff (per-totem `totem_spirit_*` rage-gated params: Bear resistance-except-psychic / Eagle OA-dis + Dash / Wolf ally-advantage); Phase 8 |
| `use_unwavering_mark` | ⚪ announce-only | — |
| `use_visions_of_distant_realms` | ⚪ announce-only | — |
| `use_whispers_of_the_dead` | ⚪ announce-only | — |
| `use_whispers_of_the_grave` | ⚪ announce-only | — |
| `use_whispers_psychic_blades` | ✅ tracked | v2.668.0 — rolls + applies the level-scaled NdN psychic damage server-side via `_apply_damage_to_combatant` when targeted (Blade-Flourish damage-half pattern); announce-only without a target |
| `use_bardic_inspiration_die` | 🔧 mechanical | mechanical |
| `use_repeated_save` | 🔧 mechanical | mechanical |
