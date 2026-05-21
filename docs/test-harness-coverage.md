# Test Harness Coverage

Living catalog of the click-through harness suite at `tests/harness/`.

> **Update rule.** Whenever a test is added, removed, renamed, or has its assertion shape materially changed, update this file in the same commit. The CLAUDE.md harness-discipline rule already requires harness coverage for every endpoint commit; this file makes the coverage navigable.

**Total tests:** 243 (as of v2.49.53, 2026-05-21).
**Runner:** `python3 -m pytest tests/harness/ -q` from the repo root. The harness expects the demo app to be reachable at `http://localhost:8013` (Docker Compose).
**Fixtures:** `gm_client`, `alice_client`, `bob_client` (httpx async clients), `roster` (skinny char list), `gm_ws` / `alice_ws` / `bob_ws` (WebSocket collectors). Per-test character fixtures (e.g. `krieger_full`, `tavik_rested`, `garrik_fresh`) long-rest + reset state so each test starts from a known baseline.

---

## Categories

- [Smoke & infrastructure](#smoke--infrastructure)
- [Generic rolls + roll requests](#generic-rolls--roll-requests)
- [Weapon attacks](#weapon-attacks)
- [Spell casting](#spell-casting)
- [Class features](#class-features)
- [Items](#items)
- [HP & death-save state machine](#hp--death-save-state-machine)
- [Buffs & concentration](#buffs--concentration)
- [Tabletop operations](#tabletop-operations)

---

## Smoke & infrastructure

### `test_smoke.py`
Sanity checks that the harness can even talk to the demo app.

| Test | What it asserts |
|------|-----------------|
| `test_healthz` | `GET /healthz` → 200, JSON `{ok, app_version, schema_version}`. |
| `test_version` | `GET /version` → 200, matches `app/version.py`. |
| `test_roster_fixture` | The `roster` fixture loads and contains all 12 demo PCs by name. |
| `test_gm_can_open_ws` | `WS /ws/campaign/1` as GM accepts connection + emits an opening `state` message. |

### `test_concurrency.py`
Multi-client races and late-joiner behavior. Guards the per-campaign `CampaignHub` + WS broadcast pipeline.

| Test | What it asserts |
|------|-----------------|
| `test_concurrent_attacks_both_broadcasts_arrive` | Two simultaneous `/attack` POSTs (GM + Alice) both produce `weapon_attack` WS events to every client. |
| `test_concurrent_rolls_all_arrive` | Burst of 10 `/roll` POSTs arrives in order on the GM's WS. |
| `test_late_joiner_does_not_get_replay` | A client connecting AFTER a roll fires doesn't see the past event (intended — WS doesn't replay history). |
| `test_late_joiner_does_get_subsequent_broadcasts` | Same client sees broadcasts that fire AFTER they connected. |
| `test_multi_tab_same_user_both_receive` | Alice with two WS connections receives each broadcast on both. |

### `test_dice_seeding.py`
v2.49.12 — TEST_MODE-only `/api/test/dice/seed` endpoint that re-seeds the shared dice RNG. Foundation for the encounter-simulation suite (docs/plans/encounter-sim-test-suite.md) — reproducible dice unlock assertions like "Fireball 8d6 = 24 fire damage" without flake.

| Test | What it asserts |
|------|-----------------|
| `test_seed_endpoint_accepts_int_seed` | `POST /api/test/dice/seed {seed:42}` → 200, body echoes the seed. |
| `test_seed_endpoint_accepts_null_seed` | `seed:null` re-seeds from OS entropy, endpoint still 200. |
| `test_seeded_rolls_are_reproducible` | After re-seeding with the same value, two sequences of `4d6` rolls match index-for-index. |
| `test_different_seeds_produce_different_rolls` | Different seeds diverge — guards against a no-op seed handler. |
| `test_seeded_d20_total_in_range` | Seeded `1d20` total still lands in `[1, 20]` — regression catch for a broken seeded resolver. |

---

## Generic rolls + roll requests

### `test_roll.py`
The `/roll` endpoint + WS broadcast shape + visibility filter.

| Test | What it asserts |
|------|-----------------|
| `test_roll_d20` | `1d20` returns `{total, breakdown, expression}`; WS `roll` event matches. |
| `test_roll_4d6` | Multi-die expression rolls correctly; breakdown contains 4 brackets. |
| `test_roll_invalid_visibility` | `visibility: "garbage"` → 400. |
| `test_roll_gm_only_hidden_from_player` | `gm_only` roll's WS event doesn't reach Alice's WS but does reach the GM's. |
| `test_roll_gm_and_roller_hidden_from_non_roller` | `gm_and_roller` roll from Alice reaches Alice + GM but not Bob. |

### `test_roll_request.py`
GM-driven roll-prompt flow used by T.3 PC save spells.

| Test | What it asserts |
|------|-----------------|
| `test_gm_creates_roll_request` | `POST /roll_request` as GM → 200 + numeric `id`. |
| `test_non_gm_cannot_create_roll_request` | Alice → 403. |
| `test_roll_request_missing_label_400` | Empty `label` → 400. |
| `test_respond_to_roll_request` | GM responds on Pip's behalf; server resolves WIS-save mod + rolls `1d20+mod`; response carries `total` + `breakdown`. |
| `test_respond_invalid_req_id_404` | Bogus `req_id` → 404. |
| `test_respond_for_someone_elses_character_403` | Alice responds for Krieger (not hers) → 403 (or 404 fallback). |

---

## Weapon attacks

### `test_attack.py`
Basic `/attack` happy paths + error paths + bonus-damage uplifts.

| Test | What it asserts |
|------|-----------------|
| `test_attack_pip_shortsword` | Pip's L1 attack (`index=0`) rolls a d20 + slashing dmg; broadcast matches. |
| `test_attack_pip_dagger` | Same flow at `index=1`. |
| `test_attack_tavik_warhammer` | Tavik's L1 attack works; carries `damage_type=bludgeoning`. |
| `test_attack_invalid_index` | `attack_index=999` → 404. |
| `test_attack_missing_character_id` | Empty body → 400. |
| `test_attack_sneak_attack_uplift` | Pip with `uplifts=["sneak-attack"]` rolls extra `1d6` damage; broadcast carries the uplift in `auto_uplifts`. |
| `test_attack_divine_smite_spends_slot` | Sir Caelan's Smite consumes a L1 paladin slot + adds radiant dice. |
| `test_attack_divine_smite_no_slot` | Smite without an available slot → 409. |
| `test_attack_spend_slot_missing_class` | `spend_spell_slot` without `class_slug` → 400. |

### `test_attack_auto_damage.py`
T.2 hit determination + auto-applied damage + Undo. Gated by `Campaign.auto_apply_damage` toggle.

| Test | What it asserts |
|------|-----------------|
| `test_attack_hit_determination_without_auto_apply` | Toggle off: response carries `hit` / `target_ac` but no HP change. |
| `test_attack_auto_apply_on_hit` | Toggle on: hits apply damage; `damage_applied > 0`, target HP drops. |
| `test_attack_crit_doubles_damage` | Forced crit doubles the damage dice (via `_double_dice_for_crit`). |
| `test_undo_attack_damage` | `POST /undo_attack_damage` reverses the HP change for the cast id. |
| `test_undo_unknown_attack_id` | Unknown id → 404. |
| `test_undo_missing_attack_id_field` | Empty body → 400. |

### `test_attack_force_gm_sync.py`
v2.49.40 — `/attack` against an NPC broadcasts `battle_update` with `force_gm_sync: True` so the GM client (whose `battle_update` handler ignores broadcasts without the flag per the v2.5.5 echo-loop guard) actually applies the HP change. Pre-fix the GM's local state stayed at pre-attack HP until something else triggered `pushBattle`, then the GM's stale local state overwrote the server's new HP — the bandit visually "came back to life."

| Test | What it asserts |
|------|-----------------|
| `test_npc_damage_broadcast_carries_force_gm_sync` | Krieger attacks Bandit Alpha; `battle_update` broadcast carries `force_gm_sync=True`; broadcasted state contains the updated combatant HP. Skips assertion gracefully on miss (no broadcast in that case). |

### `test_sheet_patch_hp_broadcast.py`
v2.49.42 — `PATCH /sheet-fields` broadcasts `character_hp_update` on HP change (not just `character_death_save` on status crossings). Pre-fix, vanilla HP edits within "alive" went silent on the WS, so non-GM clients couldn't observe HP-bar movement from GM sheet edits or test damage applications.

| Test | What it asserts |
|------|-----------------|
| `test_hp_drop_within_alive_broadcasts` | PATCH HP down (35 → 25) without crossing status fires `character_hp_update` with negative delta + `source: "sheet_patch"`. |
| `test_hp_heal_broadcasts_positive_delta` | PATCH HP up fires `character_hp_update` with positive delta. |
| `test_hp_unchanged_does_not_broadcast` | PATCH with `current == current` (no-op) suppresses the broadcast — prevents settings-form spam. |

### `test_attack_buff_intercepts.py`
Phase B damage-flow intercepts — Rage / Hunter's Mark / Colossus Slayer / resistance.

| Test | What it asserts |
|------|-----------------|
| `test_rage_adds_damage_bonus` | Krieger with Rage buff adds +2 damage to a melee strength attack. |
| `test_rage_advantage_on_attack` | Reckless attack flag rolls 2d20 keep-highest. |
| `test_hunters_mark_rider_on_marked_target` | Rowan's strike vs marked target adds 1d6 bonus dice. |
| `test_hunters_mark_does_not_fire_on_other_target` | Strike vs unmarked target → no bonus dice. |
| `test_colossus_slayer_fires_vs_below_max_hp` | Hunter Ranger's bonus 1d8 fires when target HP < max. |
| `test_colossus_slayer_skips_full_hp_target` | Same archer vs full-HP target → no bonus. |
| `test_colossus_slayer_once_per_turn` | Second attack in the same turn skips the bonus (1/turn limit). |
| `test_resistance_halves_damage` | Krieger's slashing attack on a slashing-resistant NPC → halved. |
| `test_resistance_does_not_halve_unrelated_type` | Different damage type → no halving. |
| `test_attack_broadcast_includes_target_name` | Broadcast `target_name` populated when init-tracker combatant resolves. |

---

## Spell casting

### `test_cast_spell.py`
Basic `/cast_spell` happy paths + slot-consumption errors.

| Test | What it asserts |
|------|-----------------|
| `test_cast_magic_missile` | Thalindra's Magic Missile (L1) decrements a wizard slot; broadcast names the spell. |
| `test_cast_misty_step_bonus_action` | Misty Step at L2 marks the bonus chip. |
| `test_cast_tavik_healing_word` | Tavik's bonus-action heal cast (long-rest pre-fixture). |
| `test_cast_invalid_spell_index` | `spell_index=999` → 404. |
| `test_cast_missing_fields` | Empty body → 400. |

### `test_cast_spell_target.py`
Phase T.1 target descriptors plumbed into `/cast_spell` body + WS broadcast.

| Test | What it asserts |
|------|-----------------|
| `test_cast_spell_with_target_character_id` | `target_character_id` resolves to `target_combatant_id` server-side; broadcast carries all 3 fields. |
| `test_cast_spell_target_combatant_id_wins` | When both descriptors are present, explicit combatant_id wins. |
| `test_cast_spell_no_target` | No descriptor → broadcast fields empty. |
| `test_cast_spell_target_npc_by_name` | NPC target via `target_name` only resolves to its combatant id. |

### `test_cast_spell_attack.py`
Phase T.4b auto-rolled spell attacks (Fire Bolt etc.) — hit vs AC, crit doubling, damage apply.

| Test | What it asserts |
|------|-----------------|
| `test_fire_bolt_resolves_hit_vs_npc` | Fire Bolt vs bandit: `auto_attack_hit`/`total`/`target_ac` populated; damage rolls when hit + toggle on. |
| `test_spell_attack_no_damage_when_toggle_off` | Toggle off: attack rolls but `damage_applied == 0`. |
| `test_spell_attack_no_target_skips_block` | No target → `auto_attack_hit is None`. |
| `test_fire_bolt_scales_at_l5` | v2.36.0 cantrip scaling: Thalindra (L5) Fire Bolt rolls 2d10 (range 2..20), not 1d10. |
| `test_eldritch_blast_multibeam_at_l5` | v2.40.0 multi-beam: Magnus (L5) Eldritch Blast → 2 beams, each rolling 1d10 (range 1..10 per beam). |
| `test_non_attack_spell_skips_attack_block` | Healing Word (no `attack_roll`) → block skipped. |

### `test_cast_spell_heal.py`
Phase T.4 auto-healing — target-aware HP apply, revive, undo, max-HP cap.

| Test | What it asserts |
|------|-----------------|
| `test_heal_auto_applies_on_target` | Tavik → Pip (HP=10): `auto_heal_applied > 0`, Pip's HP rises. |
| `test_cast_without_target_no_auto_heal` | No target → `auto_heal_applied == 0`, heal_claim registered. |
| `test_heal_revives_dying_target` | Dying Pip → Healing Word brings him back; `auto_heal_revived: True`. |
| `test_undo_heal_reverses_hp` | `/undo_attack_damage` reverses the heal via the `is_heal` flag. |
| `test_heal_auto_applies_with_only_character_id` | Target PC not in init: synthesized-combatant fallback still applies heal. |
| `test_heal_caps_at_max_hp` | Pip at max-1 → only 1 HP applied even if dice rolled higher. |

### `test_cast_spell_save.py`
Phase T.3 save-spell auto-resolution + T.3b save-for-half damage + T.3c condition install.

| Test | What it asserts |
|------|-----------------|
| `test_save_spell_prompts_pc_target` | Hold Person → Pip (PC): `auto_save_prompted=True`, RollRequest created for Pip's owner. |
| `test_save_spell_auto_rolls_npc` | Hold Person → bandit (NPC): server rolls save, `auto_save_rolled`/`passed` populated. |
| `test_cast_without_target_no_auto_save` | No target → save fields empty. |
| `test_save_for_half_applies_half_on_success` | Sacred Flame: full damage on fail, half on success. |
| `test_save_spell_no_auto_damage_when_toggle_off` | Toggle off: save rolls but no damage applied. |
| `test_save_or_suck_installs_buff_on_fail` | Hold Person on bandit failure: Paralyzed buff installed on combatant. |
| `test_save_or_suck_skips_unknown_spell` | Sacred Flame (has damage, not save-or-suck) → no buff installed. |
| `test_non_save_spell_no_auto_save` | Healing Word (no `save_ability`) → save block skipped. |

### `test_save_spell_pc_buff.py`
Phase T.3d — PC save-or-suck via roll-response correlation. When the PC fails their save, the condition buff installs on them through `/roll_request/{id}/respond`.

| Test | What it asserts |
|------|-----------------|
| `test_cast_hold_person_at_pc_creates_prompt` | Cast carries `auto_save_prompt_id` (numeric RollRequest id) when target is a PC. |
| `test_pc_save_fail_installs_paralyzed_buff` | PC fails the save → respond response carries `auto_buff_installed: "Paralyzed"` and `/buffs` GET lists the paralyzed entry. Loops up to 15 attempts to land a failure (Krieger Wis +1 vs DC 14). |
| `test_pc_save_pass_skips_buff` | Manual (non-cast-stashed) `/roll_request` → `/respond` returns `auto_buff_installed: ""` even when forced to fail. |

### `test_cast_spell_aoe.py`
Phase T.5a — AoE multi-target dispatch on `/cast_spell`. New `target_combatant_ids` (list) body field; loops save + save-for-half damage per target; `auto_save_targets` per-target outcome list on response.

| Test | What it asserts |
|------|-----------------|
| `test_fireball_hits_three_bandits` | Thalindra Fireball at 3 bandits → `auto_save_targets` has 3 entries with rolled/passed/damage_applied/damage_type. Each bandit took non-zero fire damage. |
| `test_single_target_fallback_unchanged` | Old single-target `target_combatant_id` (no list) still populates the headline `auto_save_*` fields AND `auto_save_targets` with 1 entry. |
| `test_aoe_list_with_pc_target_marks_pc_skipped` | AoE list with a PC token → PC entry has `pc_skipped: True`, `rolled: None`, `damage_applied: 0`, AND (v2.47.0) `pending_request_id` set so the cast card can correlate the eventual update broadcast. |
| `test_aoe_pc_response_applies_damage_and_broadcasts_update` | v2.47.0 Phase T.5d end-to-end: AoE cast at NPC+PC → PC submits the save → server applies save-for-half damage AND broadcasts `spell_cast_target_updated` with `cast_id`, `combatant_id`, `target_name`, `rolled`, `passed`, `damage_applied`, `damage_type`. PC's HP drops by the broadcast's `damage_applied`. |
| `test_aoe_cast_without_targets_lands_pending_then_place_aoe_resolves` | v2.48.0 Phase T.5e caster-gated placement. `/cast_spell` without `target_combatant_ids` returns `pending_aoe_placement: True` + the spell's `area_shape`/`area_size_ft`. Then POST `/place_aoe` with the cast_id + target list resolves NPC saves + damage and broadcasts `spell_cast_aoe_resolved` with the resolved targets. |
| `test_place_aoe_auto_rolls_pc_save_and_applies_damage` | v2.48.3 — `/place_aoe` auto-rolls PC saves alongside NPCs (no more roll_request prompt for the new flow). PC entry has `rolled`/`passed`/`damage_applied` populated, `pc_skipped` and `pending_request_id` absent. PC's HP drops server-side. |
| `test_place_aoe_rejects_non_caster_non_gm` | v2.48.0 Phase T.5e auth gate. `/place_aoe` with a bogus cast_id returns 404 (stash-not-found). |

---

## Class features

### `test_use_rage.py`
Barbarian Rage install + end_buff (Phase C primitive sanity).

| Test | What it asserts |
|------|-----------------|
| `test_rage_happy_path` | `/use_rage` installs Rage buff; broadcast carries `feature_used`. |
| `test_rage_out_of_uses` | Calling beyond counter → 409. |
| `test_rage_wrong_class` | Non-Barbarian → 409. |
| `test_rage_missing_character_id` | Empty body → 400. |
| `test_end_buff_happy_path` | `/end_buff` removes Rage. |
| `test_end_buff_not_found` | Removing a buff that isn't installed → 404. |
| `test_end_buff_missing_fields` | Empty body → 400. |

### `test_use_second_wind.py`
Fighter Second Wind heal-roll (v2.34.x `dice_*` envelope).

| Test | What it asserts |
|------|-----------------|
| `test_second_wind_happy_path` | Rolls 1d10+lv, applies HP, decrements counter; `feature_used` includes `Second Wind` substring; broadcast carries v2.43.0 `heal_amount` + `heal_target_name` (== caster). |
| `test_second_wind_out_of_uses` | Counter exhausted → 409. |
| `test_second_wind_wrong_class` | Non-Fighter → 409. |
| `test_second_wind_missing_character_id` | Empty body → 400. |

### `test_use_action_surge.py`
Fighter Action Surge: refunds the action chip.

| Test | What it asserts |
|------|-----------------|
| `test_action_surge_happy_path` | Decrement counter + broadcast `feature_used`. |
| `test_action_surge_refunds_action_chip` | The `action` economy chip flips back to unused. |
| `test_action_surge_out_of_uses` | 409 when counter is empty. |
| `test_action_surge_wrong_class` | Non-Fighter → 409. |
| `test_action_surge_missing_character_id` | 400. |

### `test_use_arcane_recovery.py`
Wizard Arcane Recovery: half-level slot refund.

| Test | What it asserts |
|------|-----------------|
| `test_arcane_recovery_happy_path` | Refunds requested slots up to the level/2 allowance. |
| `test_arcane_recovery_allowance` | Allowance maxes at `ceil(wiz_level/2)`. |
| `test_arcane_recovery_l6_rejected` | L6 slot rejected (RAW). |
| `test_arcane_recovery_missing_slots` | Empty body → 400. |
| `test_arcane_recovery_invalid_slot_entry` | Non-int level → 400. |
| `test_arcane_recovery_wrong_class` | Non-Wizard → 409. |
| `test_arcane_recovery_missing_character_id` | 400. |

### `test_use_bardic_inspiration.py`
Bard grants a Bardic Inspiration die to a target (Phase C resource).

| Test | What it asserts |
|------|-----------------|
| `test_bi_happy_path` | Adds BI die to target; decrements bard's counter. |
| `test_bi_missing_fields` | Missing target → 400. |
| `test_bi_self_target` | Bard grants to themselves → succeeds (RAW edge case). |
| `test_bi_no_bard_resource` | Non-Bard caller → 409. |
| `test_bi_unknown_target` | Unknown target id → 404. |

### `test_use_cutting_words.py`
Bardic Inspiration die used as a reaction debuff (College of Lore).

| Test | What it asserts |
|------|-----------------|
| `test_cutting_words_happy_path` | Rolls a BI die, broadcasts a `feature_used` describing the subtraction. |
| `test_cutting_words_no_target` | Generic broadcast text when no target was passed. |
| `test_cutting_words_target_name_fallback` | `target_name` alone is acceptable. |
| `test_cutting_words_target_character_id_wins` | Explicit char_id beats name. |
| `test_cutting_words_missing_character_id` | 400. |
| `test_cutting_words_unknown_character` | 404. |
| `test_cutting_words_wrong_class` | Non-Bard caller → 409. |
| `test_cutting_words_out_of_uses` | BI counter exhausted → 409. |

### `test_use_lay_on_hands.py`
Paladin Lay on Hands: heal from a per-day pool.

| Test | What it asserts |
|------|-----------------|
| `test_loh_happy_path` | Heals targeted PC; decrements pool; broadcast carries v2.43.0 `heal_amount` + `heal_target_name` (== target). |
| `test_loh_missing_fields` | 400. |
| `test_loh_zero_amount` | Amount ≤ 0 → 400. |
| `test_loh_no_paladin_resource` | Non-Paladin caller → 409. |
| `test_loh_unknown_target` | Unknown target id → 404. |

### `test_use_feature.py`
Generic `/use_feature` endpoint — Rogue Cunning Action, Channel Divinity options, Paladin Divine Sense, plus several curated single-shot features.

| Test | What it asserts |
|------|-----------------|
| `test_cunning_action_dash` | Pip's Dash flips the bonus chip. |
| `test_cunning_action_disengage` | Same flow for Disengage. |
| `test_cunning_action_hide` | Same flow for Hide. |
| `test_channel_divinity_turn_undead` | Tavik's Turn Undead consumes CD charge. |
| `test_channel_divinity_sacred_weapon` | Sacred Weapon variant works. |
| `test_channel_divinity_turn_the_unholy` | Turn the Unholy CD variant. |
| `test_channel_divinity_preserve_life` | Preserve Life CD variant. |
| `test_divine_sense_announces` | Paladin announces aura sense; no resource cost. |
| `test_cleansing_touch_curated` | Curated feature label fires. |
| `test_indomitable_curated` | Fighter Indomitable variant. |
| `test_stroke_of_luck_curated` | Rogue Stroke of Luck. |
| `test_font_of_magic_curated` | Sorcerer Font of Magic announce. |
| `test_action_surge_is_free` | Action Surge via the generic endpoint is action-economy-free (refunds the action chip). |
| `test_unknown_feature_key` | Unknown key → 404. |
| `test_missing_required_fields` | 400. |
| `test_feature_desc_falls_back_when_client_omits` | v2.43.11: when the client doesn't send `desc`, the server falls back to the curated `_FEATURE_ECONOMY` desc and the option-specific entry (disengage) wins over the parent feature's. |
| `test_feature_desc_client_override_wins` | Client-supplied `desc` overrides the server table. |

---

## Items

### `test_use_item.py`
`/use_item` consumable + non-consumable paths (heal potions, story items).

| Test | What it asserts |
|------|-----------------|
| `test_use_item_missing_fields` | Empty body → 400. |
| `test_use_item_unknown_index` | Out-of-range item index → 404. |
| `test_use_item_non_consumable` | Story item (qty 1, non-consumable) → fires feature_used but doesn't decrement. |

> Heal-potion happy path is covered indirectly via `heal_applied` broadcasts in `test_cast_spell_heal.py` and the v2.27.1 routing logic. A dedicated potion-heal test is **filed**.

---

## HP & death-save state machine

### `test_death_save.py`
The dying / stable / dead state machine. Core HP transitions through 0.

| Test | What it asserts |
|------|-----------------|
| `test_drop_to_zero_sets_dying` | Damaging Pip to 0 (with safe magnitude) → death-save POST returns 200 (state is dying). |
| `test_death_save_roll_updates_counters` | POST returns flat `{ok, raw, outcome, status, successes, failures, hp}`; one roll advances either counter. |
| `test_death_save_409_when_alive` | POST on a long-rested alive PC → 409. |
| `test_death_save_override_sets_status` | GM `/death-save/override` force-sets `{status, successes, failures}`. |
| `test_stabilize_endpoint` | `/stabilize` sets status=stable, counters=0. |
| `test_stabilize_forbidden_for_non_gm` | Alice → 403. |
| `test_override_to_alive_bumps_hp_to_1` | Override `status="alive"` from 0-HP-dying → HP bumps to 1 automatically. |

---

## Buffs & concentration

### `test_end_buff.py`
Manual buff removal via `/end_buff`.

| Test | What it asserts |
|------|-----------------|
| `test_end_buff_removes_rage` | Install Rage via `/use_rage`, then `/end_buff` drops it; `/character/{id}/buffs` no longer lists it. |
| `test_end_buff_missing_character_id_400` | 400. |
| `test_end_buff_missing_key_400` | 400. |
| `test_end_buff_unknown_key_404` | Buff not present → 404. |
| `test_end_buff_non_owner_403` | Alice tries to drop Krieger's buff → 403/404. |

### `test_concentration_buffs.py`
Phase C concentration handling — Hunter's Mark, Hex, swap, concentration-save trigger.

| Test | What it asserts |
|------|-----------------|
| `test_hunters_mark_happy_path` | Ranger Rowan installs HM on target; `cast_hunters_mark` broadcasts a `buff_update`. |
| `test_hunters_mark_wrong_class` | Non-Ranger → 409. |
| `test_hunters_mark_missing_target` | No target → 400. |
| `test_hunters_mark_missing_character_id` | 400. |
| `test_hex_happy_path` | Warlock Magnus installs Hex; same buff-update shape. |
| `test_hex_wrong_class` | Non-Warlock → 409. |
| `test_concentration_swap` | Casting a second concentration spell drops the first (RAW one-at-a-time). |
| `test_concentration_save_on_damage` | Damage event triggers a concentration CON save; failure drops the buff. |

### `test_concentration_drops_on_zero_hp.py`
v2.49.48 — RAW PHB p.203: concentration ends automatically when the caster's HP drops to 0, regardless of CON save outcome. Pre-fix the save could pass at 0 HP and leave a dying/dead PC concentrating on Hex / Hunter's Mark.

| Test | What it asserts |
|------|-----------------|
| `test_concentration_force_drops_at_zero_hp` | Damage that drops Magnus to 0 HP force-drops Hex regardless of d20 outcome. `concentration_save` broadcast carries `forced_drop_on_zero_hp=True` + `passed=False` + `dropped_key="hex"`. |
| `test_concentration_normal_save_when_not_at_zero` | Damage that doesn't drop to 0 still uses the normal save path. `forced_drop_on_zero_hp=False`, `passed` follows the d20 roll. |

### `test_swap_concentration_log.py`
v2.49.53 — closes the four-emoji concentration audit set with 🔁 for swap-replaced-by-new-cast. The RAW one-concentration-at-a-time rule already silently dropped the old anchor; this commit adds the GM log breadcrumb naming `old → new`. Filtered by `source_char_id` so paired buffs (concentration=True but sourced by another caster) don't generate spurious 🔁 logs even when the (pre-existing, separately-filed) swap-loop bug drops them.

| Test | What it asserts |
|------|-----------------|
| `test_swap_own_anchor_emits_swap_log` | Pre-seed Magnus with `concentration-bless` (own-anchor); cast Hex → `🔁 Magnus swapped concentration: Bless → Hex` with breakdown naming the swap. Uses `/battle` PUT to seed because the demo lacks two separate concentration endpoints for any single PC. |
| `test_swap_paired_buff_does_not_emit_log` | Pre-seed Magnus with `paralyzed` sourced by enemy_id=99999 (mimics Hold Person victim). Cast Hex → swap loop drops the paired buff (pre-existing bug) but 🔁 log MUST NOT fire. |
| `test_no_prior_concentration_no_swap_log` | Cast Hex on Magnus with no prior concentration → fresh install, no 🔁 log (nothing was replaced). |

### `test_voluntary_end_concentration_log.py`
v2.49.52 — closes the third concentration-log cause: voluntary `/end_buff` on a caster's own concentration anchor emits a ✋ GM-only roll-log entry. Completes the three-emoji audit set (💔 failed save / 💀 incapacitated / ✋ voluntary).

| Test | What it asserts |
|------|-----------------|
| `test_voluntary_end_concentration_emits_palm_log` | Magnus casts Hex; `/end_buff` on hex → broadcast type=roll with note `✋ Magnus lost concentration on Hex` and breakdown `Concentration ends — voluntary`. |
| `test_voluntary_end_non_concentration_buff_no_log` | Krieger has Rage (concentration=False); `/end_buff` on rage emits NO ✋ log. The audit is scoped to concentration anchors only. |
| `test_voluntary_end_paired_condition_no_log` | Tavik Hold-Persons Magnus → Magnus has Paralyzed (concentration=True, source=Tavik). Magnus `/end_buff` on paralyzed → NO ✋ log because the victim isn't the one concentrating; Tavik still is. |

### `test_incapacitation_drops_concentration.py`
v2.49.51 — RAW PHB p.203 "you also lose concentration on a spell if you are incapacitated." Closes the non-damage incapacitation gap filed in v2.49.49. `_install_buff` now detects when the incoming buff is in `_INCAPACITATING_BUFF_KEYS` (paralyzed / incapacitated / stunned / petrified / unconscious / asleep) and drops the target's OWN concentration anchors + emits a 💀 GM log naming the incapacitating buff as the cause. `_drop_caster_concentration` now filters by `source_char_id` so paired condition buffs (sustained by another caster) aren't swept.

| Test | What it asserts |
|------|-----------------|
| `test_paralyzed_pc_drops_own_concentration` | Magnus has Hex; Tavik casts Hold Person → save fails → Paralyzed lands on Magnus → Hex drops + 💀 log fires naming "Paralyzed" + "incapacitated" in breakdown. Paralyzed buff itself is preserved. |
| `test_charmed_pc_keeps_own_concentration` | Regression guard: non-incapacitating Charmed via Charm Person does NOT drop Hex. Gracefully skips if the seed doesn't expose Charm Person at the expected spell index. |
| `test_source_caster_concentration_still_cascades` | v2.49.51's `source_char_id` filter doesn't regress the v2.38.0 paired cleanup: ending Tavik's `concentration-hold-person` still cascade-removes Magnus's Paralyzed buff. |

### `test_concentration_skull_log.py`
v2.49.50 — distinguishes 💀 incapacitation drops from 💔 failed-save drops in the GM-only roll-log. The broadcast shape is unchanged (still `type=roll` with `visibility=gm_only`); the note text + breakdown carry the cause. Closes the v2.49.48 Filed item.

| Test | What it asserts |
|------|-----------------|
| `test_zero_hp_forced_drop_emits_skull_log` | Damage drops Magnus to 0 HP → note starts with 💀, breakdown contains "incapacitated" + "0 HP" + "would have been" (rolled save preserved for telemetry). |
| `test_failed_con_save_still_emits_heart_log` | Damage above 0 HP + failed CON save → note still starts with 💔. Regression guard against over-broadening the fix. Retry loop because the d20 is random. |
| `test_override_to_dead_emits_skull_log` | GM overrides Magnus → dead while Hex'd → 💀 log with breakdown naming "GM override → dead". Caster name from combatant name (not "PC {id}"). |
| `test_roll_3_failures_emits_skull_log` | `roll_death_save` 3rd-failure branch → 💀 log with breakdown naming "death saves". Distinct reason string from override path. Retry loop on the d20. |

### `test_death_save_drops_concentration.py`
v2.49.49 — RAW PHB p.203: concentration ends when the caster is incapacitated or killed. The v2.49.48 0-HP rule covered damage-induced drops, but the death-save endpoints (`POST /death-save` rolling, `POST /death-save/override` GM force) didn't go through `_maybe_concentration_save`. Both branches now call `_drop_caster_concentration` so 3 failed saves → dead, or a GM override to dying/stable/dead, also drops concentration.

| Test | What it asserts |
|------|-----------------|
| `test_override_to_dead_drops_concentration` | GM overrides Magnus to status=dead via `POST /death-save/override` → `buff_update` broadcasts a new buff list with `hex` removed; live `/buffs` re-fetch confirms. |
| `test_roll_3_failures_drops_concentration` | Dying Magnus reaches 3 failures → status transitions to dead → `buff_update` fires with `hex` absent. Uses override(failures=3, status=dead) which exercises the same `_drop_caster_concentration` codepath. |
| `test_override_to_alive_does_not_drop_concentration` | Guard against over-broad fix: override(alive) on an alive PC does not emit a hex-dropping `buff_update`; the buff stays installed. |

### `test_concentration_cleanup.py`
Phase T.3e — concentration drop cascades to paired condition buffs.

| Test | What it asserts |
|------|-----------------|
| `test_save_or_suck_installs_caster_concentration` | Cast Hold Person at a bandit who fails the save → caster gains `concentration-hold-person` anchor buff (loops up to 20 attempts). |
| `test_end_concentration_drops_caster_buff` | `/end_buff` on the caster's concentration removes it; paired NPC buff drop happens server-side via the cleanup helper. |
| `test_concentration_break_emits_gm_only_log` | v2.39.0: failed CON save on damage emits a `roll`-type event with `visibility: "gm_only"` narrating "💔 NAME lost concentration on SPELL — dropped: …". |
| `test_non_concentration_buff_removal_unaffected` | Removing Rage on Krieger (non-concentration) still works post-T.3e change. |

### `test_buff_sheet_mirror.py`
Phase C.3 — buffs persist to `sheet["_buffs_active"]` for cross-page visibility.

| Test | What it asserts |
|------|-----------------|
| `test_use_rage_mirrors_to_sheet` | After `/use_rage`, the sheet mirror contains the Rage entry. |
| `test_end_buff_clears_sheet_mirror` | After `/end_buff`, the mirror is empty. |
| `test_hunters_mark_mirrors_to_sheet` | Hunter's Mark also mirrors. |
| `test_put_battle_mirrors_to_sheet` | A raw `PUT /battle` with buffs in the combatants array updates the sheet mirror. |
| `test_put_battle_clears_sheet_on_buff_drop` | Removing the buff via PUT clears the mirror. |

---

## Tabletop operations

### `test_move.py`
Token-list GET + token-move POST.

| Test | What it asserts |
|------|-----------------|
| `test_tokens_list` | `GET /tokens` returns all live tokens. |
| `test_move_pip_one_cell` | Single-cell move broadcasts `token_update` with the new x/y. |
| `test_move_chebyshev_diagonal` | Diagonal move counts as one cell (chebyshev distance). |
| `test_move_unknown_token` | Unknown token id → 404. |

### `test_rest.py`
Short rest (Song of Rest) + long rest.

| Test | What it asserts |
|------|-----------------|
| `test_short_rest_song_of_rest_happy_path` | Short rest with hit dice → broadcasts hp restore. |
| `test_long_rest_happy_path` | Long rest refills HP + spell slots + class features. |
| `test_short_rest_invalid_type` | `type: "bogus"` → 400. |
| `test_short_rest_no_hit_dice` | No HD left → cannot short rest. |

### `test_encounters.py`
Encounters CRUD — `GET /encounters`, `POST /encounters`, `PATCH /encounters/{id}`, duplicate / update / delete. v2.40.0 closed the v2.35.1 audit gap.

| Test | What it asserts |
|------|-----------------|
| `test_list_encounters_returns_array` | `GET /encounters` returns a JSON list. |
| `test_non_gm_cannot_list` | 403 for non-GM. |
| `test_create_blank_encounter` | `POST /encounters` with `payload` creates a build-from-blank draft; shows up in subsequent list. |
| `test_create_encounter_missing_name_400` | Empty `name` → 400. |
| `test_patch_encounter_updates_name` | `PATCH /encounters/{id}` rewrites name + description. |
| `test_duplicate_encounter` | `POST /encounters/{id}/duplicate` creates a sibling row with a new id. |
| `test_delete_encounter` | `POST /encounters/{id}/delete` removes the row from the list. |
| `test_non_gm_cannot_create_403` | 403 for non-GM POST. |
| `test_update_encounter_overwrites_payload` | `POST /encounters/{id}/update` snapshots live state into the saved payload (doesn't touch live state). |

> `POST /encounters/{id}/load` happy-path test is **filed** — loading replaces live tokens + battle state which is destructive for the standing demo seed and breaks downstream tests. Needs a save-restore harness pattern.

### `test_transform.py`
Druid Wild Shape / Polymorph form transitions.

| Test | What it asserts |
|------|-----------------|
| `test_wild_shape_happy_path` | Mira → beast form; `transform` broadcast carries new sheet. |
| `test_transform_missing_slug` | 400. |
| `test_transform_invalid_source` | `source: "garbage"` → 400. |
| `test_transform_cr_cap_enforced` | Druid CR cap rejects high-CR beasts. |
| `test_transform_already_transformed` | Cannot transform while transformed (409). |
| `test_revert_when_not_transformed` | Reverting a base-form character → 409. |
| `test_transform_over_budget_flag` | Carries `over_budget: true` when action chip already used. |

---

## Wiki

Read-only doc-hub routes added in v2.43.3, expanded in v2.49.9 with the `/wiki/doc/<slug>` route + shared nav menu injection. Tests live in `tests/harness/test_wiki.py`.

| Test | What it asserts |
|------|-----------------|
| `test_wiki_home_renders` | `GET /wiki` → 200, HTML body contains "SimpleVTT wiki", a link to `/wiki/roll-log-guide`, the `wiki-nav` menu, and links into the Plans / References / Repo Docs tables (v2.49.9). |
| `test_wiki_guide_serves_roll_log` | `GET /wiki/roll-log-guide` → 200, body contains "roll-log" + the injected `wiki-nav` menu (v2.49.9). |
| `test_wiki_unknown_slug_404` | `GET /wiki/no-such-page` → 404. |
| `test_wiki_traversal_blocked` | URL-encoded `../` in the slug → 404 / 400 (path-traversal blocked). |
| `test_wiki_markdown_guide_renders` | v2.43.14: `/wiki/realtime-broadcasts-catalog` (a `.md` source) renders through the markdown package + wraps in `wiki_md.html`. Asserts `<h1`, `<table`, the catalog's title, and the `wiki-nav` menu (v2.49.9). |
| `test_wiki_doc_serves_plan` | v2.49.9: `GET /wiki/doc/plan-test-harness` → 200, body contains the plan's H1 + the nav menu. Resolves through the `_DOC_ALLOWLIST` mapping to `docs/plans/test-harness.md`. |
| `test_wiki_doc_serves_root_doc` | v2.49.9: `GET /wiki/doc/claude` → 200, body contains CLAUDE.md's H1 ("Claude Code guidelines") + the nav menu. Resolves through the allowlist to the repo-root `CLAUDE.md`. |
| `test_wiki_doc_unknown_slug_404` | v2.49.9: a slug that isn't in `_DOC_ALLOWLIST` → 404. Important security guarantee — the allowlist is the only way to reach a file outside `docs/wiki/`. |
| `test_wiki_doc_traversal_blocked` | v2.49.9: directory-traversal characters in the doc slug → 404 / 400, rejected by the slug guard before the allowlist lookup. |

---

## Broadcast payload shapes

Field-presence assertions on the WS broadcasts that drive the roll-log cards + the dice / status toasts. Tests live in `tests/harness/test_broadcast_payload_shapes.py` (added v2.43.12). Behavior tests stay in per-endpoint files; these focus purely on what fields the client reads.

| Test | What it asserts |
|------|-----------------|
| `test_roll_broadcast_carries_all_required_fields` | `/roll` broadcast has `total`, `expression`, `breakdown`, `user_id`, `user_name`, `visibility`, `note`. |
| `test_roll_broadcast_carries_visibility_field` | `visibility: "gm_only"` round-trips correctly. |
| `test_weapon_attack_broadcast_carries_all_required_fields` | `/attack` broadcast has `attack_total`, `attack_breakdown`, `attack_name`, `damage_total`, `damage_breakdown`, `damage_type`, `caster_*`, `id`, `hit`, `is_crit`, `is_save`, `over_budget`. |
| `test_spell_cast_heal_broadcast_carries_all_required_fields` | Tavik Healing Word → Pip; broadcast has spell-cast header fields + `auto_heal_*` heal pill fields. |
| `test_spell_cast_attack_broadcast_carries_all_required_fields` | Thalindra Fire Bolt → bandit; broadcast has `auto_attack_*` fields. |
| `test_spell_cast_save_broadcast_carries_all_required_fields` | Tavik Hold Person → bandit; broadcast has `auto_save_*` fields. |
| `test_feature_used_simple_broadcast_carries_all_required_fields` | Cunning Action: Dash; broadcast has header + `feature_desc` (server-side fallback). |
| `test_second_wind_broadcast_carries_dice_and_heal_fields` | `/use_second_wind` broadcast has both the v2.35.0 `dice_*` fields (for the dice toast) AND the v2.43.0 `heal_*` fields (for the card's heal pill), and v2.43.12's `feature_desc` contains "rolled". |
| `test_lay_on_hands_broadcast_carries_heal_fields` | `/use_lay_on_hands` broadcast has the heal pill fields. |

---

## Filed (not yet implemented)

The following endpoint surfaces are exercised indirectly by other tests but lack a dedicated test file. Tracked for future expansion; low regression risk today.

- `/api/campaign/{cid}/encounters/{id}/load` happy-path (destructive — wipes live tokens). The rest of the CRUD surface is now covered in `test_encounters.py`.
- `/api/campaign/{cid}/encounters/{id}/spawn` — not yet covered.
- `/api/campaign/{cid}/character/{id}/economy` GET — the action-chip JSON view.
- Token CRUD beyond `/move` — create, image upload, delete.
- Template CRUD — `/templates`, `/templates/{id}`, image upload, monster import.
- `/character/{id}/sheet-fields` PATCH edge cases — massive-damage instant-kill, temp HP absorption, `hp_change_reason: "heal"` death-save reset.
- `/character/{id}/resource` POST — used by class-feature charge counters.
- `/character/{id}/place-token` POST.
- `/use_item` heal happy path — covered indirectly via the `heal_applied` broadcast in `test_cast_spell_heal.py`.

---

## Updating this doc

When you change tests, update the corresponding section in the same commit. Conventions:

- **Added test** → new row in the file's table.
- **Removed test** → strike the row out (`~~test_name~~`) and leave the file's total-test-count number in the header in sync.
- **Renamed test** → rename the row.
- **Behavior change** → update the "What it asserts" cell.

When a whole new test file lands, add a new H3 (`###`) section under the appropriate category. If the category doesn't fit, add a new H2 (`##`) and link it from the [Categories](#categories) list.

The total-test-count line at the top is updated each time the file changes. Run `python3 -m pytest tests/harness/ -q` to confirm the number.
