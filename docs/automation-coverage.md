# Automation coverage — feature-endpoint audit

**Status:** ✅ shipped (Phase 0 of [full-feature-automation.md](plans/full-feature-automation.md)) · generated v2.99.447, last refreshed v2.99.460
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
after a batch of retrofits and update the counts below. Treat the split as
**±a few**: a few `announce-only`-tagged features are *narration-only by design*
(archetype J — passive senses, language grants), and a few `tracked`-tagged ones
only spend a resource without a downstream effect.

## Summary (as of v2.99.460)

| Status | Count | Meaning |
|---|---|---|
| ✅ **tracked** | **187** | server-applies effect and/or spends resource |
| ⚪ **announce-only** | **50** | validates + broadcasts; effect left to the GM |
| 🔧 mechanical | **2** | helper endpoints (not `feature_used` features) |
| **Total** | **239** | `use_*` / `cast_*` endpoints |

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
| P8 — higher-level subclass features | composition on primitives | ⚪ mostly unshipped |
| P9 — test-contract upgrade | assert state not broadcast | 🟢 ongoing |

## Archetype legend

`A` use-per-rest counter · `B` on-hit damage rider · `C` save-or-condition ·
`D` self-buff · `E` ally-buff / aura · `F` temp-HP grant · `G` forced
movement / speed · `H` summon / token · `I` reaction · `J` announce-only-OK
(pure narration). See [full-feature-automation.md §3](plans/full-feature-automation.md)
for the archetype → primitive mapping.

## Notable announce-only backlog (candidates for automation)

Most of the 59 announce-only rows are **archetype J** (narration /
passive senses: `beast_speech`, `devils_sight`, `eldritch_sight`,
`mask_of_many_faces`, `eyes_of_the_rune_keeper`, `improved_minor_illusion`, …)
or passive damage-boosters that already ride other code paths
(`potent_spellcasting`, `empowered_evocation`, `sculpt_spells`, `foe_slayer`,
`spell_bombardment`). The genuinely-automatable tail:

- **Auras (E):** `aura_of_warding`, `ancestral_protectors`,
  `unwavering_mark`, `scornful_rebuke` — fold into `_tick_auras`
  (`aura_of_conquest` ✅ v2.99.448 condition gate; `aura_of_alacrity` ✅ v2.99.449 buff-payload).
- **On-hit / extra-attack:**
  `assassinate` (auto-crit rider). (`genies_wrath` ✅ v2.99.450 flat rider; `horde_breaker` ✅ v2.99.451 + `dread_ambusher` ✅ v2.99.452 server-resolved extra attacks.)
- **Buff / temp-HP (D/F):** `combat_inspiration`,
  `blade_flourish`, `supreme_healing` (`rallying_cry` ✅ v2.99.454 heals allies; `grim_harvest` ✅ v2.99.457 + `protective_spirit` ✅ v2.99.458 self-heals).
- **Movement (G):** `ascendant_step` (fly),
  `relentless_avenger`, `fancy_footwork` (`stormborn` ✅ v2.99.459 fly buff).

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
| `use_abjure_enemy` | ✅ tracked | A use/resource |
| `use_action_surge` | ✅ tracked | A use/resource |
| `use_adjust_density` | ✅ tracked | A use/resource |
| `use_animal_companion` | ✅ tracked | H summon, damage |
| `use_arcane_deflection` | ✅ tracked | A use/resource |
| `use_arcane_recovery` | ✅ tracked | A use/resource |
| `use_arcane_shot` | ✅ tracked | A use/resource |
| `use_arcane_ward` | ✅ tracked | A use/resource |
| `use_arms_of_the_astral_self` | ✅ tracked | A use/resource |
| `use_aura_of_alacrity` | ✅ tracked | D buff-install |
| `use_aura_of_conquest` | ✅ tracked | D buff-install, E aura |
| `use_aura_of_the_guardian` | ✅ tracked | A use/resource |
| `use_avenging_angel` | ✅ tracked | D buff-install |
| `use_balm_of_the_summer_court` | ✅ tracked | A use/resource |
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
| `use_diamond_soul_reroll` | ✅ tracked | A use/resource |
| `use_disarming_attack` | ✅ tracked | A use/resource |
| `use_distracting_strike` | ✅ tracked | A use/resource |
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
| `use_halo_of_spores` | ✅ tracked | A use/resource |
| `use_hands_of_healing` | ✅ tracked | A use/resource |
| `use_healing_light` | ✅ tracked | A use/resource |
| `use_hexblades_curse` | ✅ tracked | D buff-install |
| `use_hide_in_plain_sight` | ✅ tracked | D buff-install |
| `use_holy_nimbus` | ✅ tracked | D buff-install |
| `use_horde_breaker` | ✅ tracked | damage |
| `use_hypnotic_gaze` | ✅ tracked | C save-or-condition |
| `use_improved_war_magic` | ✅ tracked | A use/resource |
| `use_indomitable` | ✅ tracked | D buff-install |
| `use_indomitable_reroll` | ✅ tracked | A use/resource |
| `use_insightful_fighting` | ✅ tracked | A use/resource |
| `use_inspiring_smite` | ✅ tracked | F temp-HP |
| `use_intimidating_presence` | ✅ tracked | A use/resource |
| `use_invincible_conqueror` | ✅ tracked | A use/resource |
| `use_item` | ✅ tracked | heal/damage |
| `use_kensei_shot` | ✅ tracked | D buff-install |
| `use_lay_on_hands` | ✅ tracked | heal/damage |
| `use_living_legend` | ✅ tracked | A use/resource |
| `use_lunging_attack` | ✅ tracked | A use/resource |
| `use_maneuvering_attack` | ✅ tracked | A use/resource |
| `use_manifest_echo` | ✅ tracked | A use/resource |
| `use_mantle_of_inspiration` | ✅ tracked | A use/resource |
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
| `use_natures_wrath` | ✅ tracked | A use/resource |
| `use_open_hand_technique` | ✅ tracked | D buff-install, D/E buff-install, G forced-move |
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
| `use_pushing_attack` | ✅ tracked | G forced-move |
| `use_radiant_sun_bolt` | ✅ tracked | A use/resource |
| `use_rage` | ✅ tracked | D buff-install |
| `use_rally` | ✅ tracked | F temp-HP |
| `use_rallying_cry` | ✅ tracked | heal |
| `use_rangers_companion` | ✅ tracked | A use/resource |
| `use_reaction` | ✅ tracked | D buff-install, damage, heal/damage |
| `use_rebuke_the_violent` | ✅ tracked | A use/resource |
| `use_reckless_attack` | ✅ tracked | D buff-install |
| `use_restore_balance` | ✅ tracked | A use/resource |
| `use_riposte` | ✅ tracked | damage |
| `use_second_wind` | ✅ tracked | heal/damage |
| `use_shadow_arts` | ✅ tracked | A use/resource |
| `use_skirmisher` | ✅ tracked | A use/resource |
| `use_slayers_prey` | ✅ tracked | D buff-install |
| `use_soul_of_vengeance` | ✅ tracked | A use/resource |
| `use_spirit_totem` | ✅ tracked | D buff-install, F temp-HP |
| `use_spiritual_weapon` | ✅ tracked | H summon, damage |
| `use_steel_defender` | ✅ tracked | H summon, damage |
| `use_step_of_the_wind` | ✅ tracked | D buff-install |
| `use_stillness_of_mind` | ✅ tracked | A use/resource |
| `use_storm_aura` | ✅ tracked | D buff-install |
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
| `use_tentacle_of_the_deeps` | ✅ tracked | A use/resource |
| `use_third_eye` | ✅ tracked | A use/resource |
| `use_thorn_whip` | ✅ tracked | G forced-move, damage |
| `use_thunderwave` | ✅ tracked | G forced-move, damage |
| `use_tides_of_chaos` | ✅ tracked | D buff-install |
| `use_touch_of_death` | ✅ tracked | F temp-HP |
| `use_trip_attack` | ✅ tracked | A use/resource |
| `use_turn_the_faithless` | ✅ tracked | A use/resource |
| `use_turn_the_unholy` | ✅ tracked | D buff-install, D/E buff-install |
| `use_undying_sentinel` | ✅ tracked | A use/resource |
| `use_vanish` | ✅ tracked | A use/resource |
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
| `use_wrath_of_the_storm` | ✅ tracked | A use/resource |
| `use_ancestral_protectors` | ⚪ announce-only | — |
| `use_arcane_charge` | ⚪ announce-only | — |
| `use_arcane_mastery` | ⚪ announce-only | — |
| `use_ascendant_step` | ⚪ announce-only | — |
| `use_assassinate` | ⚪ announce-only | — |
| `use_aura_of_warding` | ⚪ announce-only | — |
| `use_avatar_of_battle` | ⚪ announce-only | — |
| `use_awakened_mind` | ⚪ announce-only | — |
| `use_beast_speech` | ⚪ announce-only | — |
| `use_beguiling_influence` | ⚪ announce-only | — |
| `use_blade_flourish` | ⚪ announce-only | — |
| `use_bonus_cantrip` | ⚪ announce-only | — |
| `use_combat_inspiration` | ⚪ announce-only | — |
| `use_dash` | ⚪ announce-only | — |
| `use_devils_sight` | ⚪ announce-only | — |
| `use_drunken_technique` | ⚪ announce-only | — |
| `use_eldritch_sight` | ⚪ announce-only | — |
| `use_emissary_of_redemption` | ⚪ announce-only | — |
| `use_empowered_evocation` | ⚪ announce-only | — |
| `use_expansive_bond` | ⚪ announce-only | — |
| `use_eyes_of_the_rune_keeper` | ⚪ announce-only | — |
| `use_fancy_footwork` | ⚪ announce-only | — |
| `use_flesh_to_stone_make_permanent` | ⚪ announce-only | — |
| `use_form_of_the_beast` | ⚪ announce-only | — |
| `use_improved_duplicity` | ⚪ announce-only | — |
| `use_improved_minor_illusion` | ⚪ announce-only | — |
| `use_improved_reaper` | ⚪ announce-only | — |
| `use_invocation` | ⚪ announce-only | — |
| `use_keeper_of_souls` | ⚪ announce-only | — |
| `use_mage_hand_legerdemain` | ⚪ announce-only | — |
| `use_mask_of_many_faces` | ⚪ announce-only | — |
| `use_minor_alchemy` | ⚪ announce-only | — |
| `use_mote_of_potential` | ⚪ announce-only | — |
| `use_orders_wrath` | ⚪ announce-only | — |
| `use_potent_spellcasting` | ⚪ announce-only | — |
| `use_purity_of_spirit` | ⚪ announce-only | — |
| `use_relentless_avenger` | ⚪ announce-only | — |
| `use_saint_of_forge_and_fire` | ⚪ announce-only | — |
| `use_scornful_rebuke` | ⚪ announce-only | — |
| `use_sculpt_spells` | ⚪ announce-only | — |
| `use_silver_tongue` | ⚪ announce-only | — |
| `use_spell_bombardment` | ⚪ announce-only | — |
| `use_star_map` | ⚪ announce-only | — |
| `use_supreme_healing` | ⚪ announce-only | — |
| `use_totem_spirit` | ⚪ announce-only | — |
| `use_unwavering_mark` | ⚪ announce-only | — |
| `use_visions_of_distant_realms` | ⚪ announce-only | — |
| `use_whispers_of_the_dead` | ⚪ announce-only | — |
| `use_whispers_of_the_grave` | ⚪ announce-only | — |
| `use_whispers_psychic_blades` | ⚪ announce-only | — |
| `use_bardic_inspiration_die` | 🔧 mechanical | mechanical |
| `use_repeated_save` | 🔧 mechanical | mechanical |
