# Test Harness Coverage

Living catalog of the click-through harness suite at `tests/harness/`.

> **Update rule.** Whenever a test is added, removed, renamed, or has its assertion shape materially changed, update this file in the same commit. The CLAUDE.md harness-discipline rule already requires harness coverage for every endpoint commit; this file makes the coverage navigable.

**Total tests:** 2020 in `tests/harness/` + 19 in `tests/harness_ui/` (as of v2.135.0, 2026-06-08).
**Runner:** `python3 -m pytest tests/harness/ -q` from the repo root. The harness expects the demo app to be reachable at `http://localhost:8013` (Docker Compose).

> **⚠️ Run against a FRESH DB — not a long-lived shared container.** The harness talks to one shared Docker app + Postgres over HTTP/WS. Many tests PATCH demo character sheets (subclass / level / abilities / resources / HP) and seed in-memory battle state; fixtures restore on teardown, but a long *serial* run of the **whole** suite accumulates residual state in the shared DB (a stripped resource here, a leftover battle there). Running all ~1900 tests as a single serial batch against a stale container can therefore surface **~150+ false failures from cross-test contention, not code regressions** — verified when those same tests pass after `docker compose restart app` (which re-runs `reset_and_reseed`) or in smaller batches. **CI is the authoritative full-suite gate** (`.github/workflows/test-harness.yml` runs against a fresh container per push). Locally: run per-file / per-feature batches, and `docker compose restart app` to reseed before a clean run. If a full-suite run shows a wall of failures, reseed and re-check a sample in isolation before assuming a regression.
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
| `test_attack_assassinate_auto_crit_vs_surprised` | v2.131.0 — PATCH-swaps Pip's subclass to Assassin, attacks with `target_surprised: true`, asserts `is_crit: true` on the broadcast + crit-doubled damage range. Restores subclass on teardown. Gated to Assassin Rogue Lv 3+ so a non-Assassin `target_surprised` is silently ignored. |

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

### `test_npc_attack.py`
v2.49.164 — parallel `/api/campaign/{cid}/npc_attack` endpoint for NPC monster combatants. GM-only. Mirrors PC `/attack` (d20 + damage + hit-vs-AC + auto-apply on hit) but reads attacker context from `combatant_id` instead of `character_id` + `attack_index`. Reuses the existing `weapon_attack` broadcast type with NPC-shaped caster fields (`caster_char_id: None`, `caster_char_name: <NPC name>`, `caster_combatant_id`, `is_npc_attack: True`).

| Test | What it asserts |
|------|-----------------|
| `test_npc_attack_happy_path` | Bandit `+3 to hit / 1d6+1 slashing` vs Pip: response carries `attack_total`, `damage_total`, `target_ac`, `hit`; broadcast carries `is_npc_attack=True`, `caster_combatant_id`, `caster_char_id=None`. Auto-apply off — no HP change. |
| `test_npc_attack_auto_apply_on_hit` | With `campaign.auto_apply_damage=on`, probe-fires up to 12 attacks until one lands; verifies `target_hp_after` shifts + `auto_applied=True`. |
| `test_npc_attack_no_target_still_rolls` | Endpoint called without `target_combatant_id` still rolls + broadcasts; `hit=None`, `damage_applied=0`. GM uses this for "I want the rolls in the log without committing." |
| `test_npc_attack_missing_combatant_id` | Empty body → 400. |
| `test_npc_attack_unknown_combatant_id` | Attacker not in battle → 404. |
| `test_npc_attack_unknown_target_combatant_id` | Target not in battle → 404. |
| `test_npc_attack_out_of_range_returns_409` | v2.49.166: `range` body field is parsed; endpoint accepts `override_range: true` body param without 400-ing. Fail-open semantics documented — out-of-range only fires when both attacker + target tokens are on the active map. |
| `test_npc_attack_override_range_bypasses_check` | v2.49.166: explicit `override_range: true` short-circuits the range check unconditionally. |
| `test_npc_attack_player_forbidden` | Non-GM caller → 403 (NPCs are GM-authorised). |

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
| `test_assassinate_advantage_vs_target_who_hasnt_acted` | v2.132.0 — PATCH-swaps Pip's subclass to Assassin, seeds a battle with Tavik (default `has_acted: False`), attacks with `target_combatant_id=tavik_cid`; asserts `2d20kh1` in the breakdown + `roll_state_applied == "advantage_assassinate_hasnt_acted"`. |
| `test_assassinate_advantage_gate_drops_after_target_acts` | v2.132.0 — Companion: after Tavik's turn starts (`turn_index=1`), his `has_acted` flips True via the turn-advance hook in PUT `/battle`; Pip's next attack does NOT get the Assassinate advantage. |

### `test_npc_resistance.py`
v2.49.109 — closes the v2.49.107 damage-review finding that the NPC branch of `_apply_damage_to_combatant` silently no-op'd resistance. The new `_resistance_halve_npc` helper resolves resistances from (1) the combatant's TokenTemplate's `sheet.damage_resistances` list and (2) the combatant's own `buffs` list.

| Test | What it asserts |
|------|-----------------|
| `test_npc_template_fire_resistance_halves_fireball` | NPC with `damage_resistances: ["fire"]` on its template takes ≤ 24 HP from Fireball (resistance halved from max 48). |
| `test_npc_no_resistance_takes_full_fireball` | Control: NPC with empty `damage_resistances` takes normal damage — confirms the halving is conditional, not unconditional. |

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
| `test_upcast_echoes_slot_level_and_higher_level` | Up-cast echoes `slot_level` + `higher_level` on the broadcast. |
| `test_upcast_scales_damage_dice` | Burning Hands at L2 → 4d6 (v2.110.0 resolver). |
| `test_upcast_scales_moonbeam_damage` | Moonbeam at L3 → 3d10. |
| `test_upcast_scales_heat_metal_damage` | v2.123.0 — Mira casts Heat Metal at L3 → 3d8 (backfilled `damage_per_slot`). |
| `test_upcast_scales_hellish_rebuke_damage` | v2.123.0 — Magnus casts Hellish Rebuke at L3 → 4d10. |
| `test_upcast_scales_acid_arrow_multitype` | v2.124.0 — restore-safe spell-list patch → Acid Arrow at L3 → 5d4 (resolver reads the field from content by `_slug`). |
| `test_upcast_scales_from_higher_level_prose` | v2.125.0 — Thunderwave (2d8, NO structured field) at L2 → 3d8 via the `parse_upcast_dice` fallback. Restore-safe spell-list patch. |
| `test_modeled_base_healing_then_parser_scales` | v2.126.0 — Prayer of Healing (base 2d8 now modeled) cast at L3 → `spell_healing == "3d8"` (base + parser +1d8). Restore-safe spell-list patch on Tavik. |
| `test_upcast_scales_per_two_slot_spiritual_weapon` | v2.129.0 — Tavik (Cleric) casts Spiritual Weapon at L4 → 2d8 (base 1d8 just-modeled + 1d8 from `upcast_step=2`, eff_extra=1). Restore-safe spell-list patch. Flame Blade's per-two phrasing is covered by the parser-unit tests; an end-to-end cast test would need a higher-level Druid PC (Mira is Lv 2 with no L4 slot). |
| `test_upcast_scales_healing_dice` | Cure Wounds at L2 → 2d8 healing. |
| `test_upcast_base_level_leaves_dice_unscaled` | Burning Hands at base L1 stays 3d6 (no-op). |

### `test_spell_upcast_parser.py`
v2.125.0 — pure-Python unit tests for `app/content/spell_upcast_parse.py::parse_upcast_dice`, the conservative `higher_level`-prose → per-slot-dice parser the `/cast_spell` resolver uses as a fallback below manual `damage_per_slot` / `healing_per_slot` fields.

| Test | What it asserts |
|------|-----------------|
| `test_parses_per_slot_damage` | "+1d6 for each slot level above 3rd" → `{damage_per_slot: 1d6}`. |
| `test_parses_per_slot_healing` | "the healing increases by 1d8 for each slot level above 1st" → `{healing_per_slot: 1d8}`. |
| `test_parses_multi_die_term` | "+2d6 for each slot level above 7th" → `{damage_per_slot: 2d6}`. |
| `test_ignores_cantrip_character_level_scaling` | "when you reach 5th level" → `{}` (no slot). |
| `test_parses_per_two_level_damage` | v2.129.0 — "+1d6 for every two slot levels above 2nd" → `{damage_per_slot: 1d6, upcast_step: 2}`. |
| `test_parses_per_two_level_damage_spiritual_weapon` | v2.129.0 — "above the 2nd" prose variant matches the same shape. |
| `test_parses_per_two_level_healing` | v2.129.0 — heal/damage classifier still routes per-two clauses correctly. |
| `test_ignores_instance_scaling` | "one more dart for each slot level" → `{}` (no dice term). |
| `test_ignores_flat_bonus` | "increases by 5 for each slot level" → `{}`. |
| `test_empty_or_missing` | `""` / `None` → `{}`. |
| `test_target_count_hold_person` | v2.127.0 — `upcast_target_count(slot, base_level=2)` → L2/L3/L4 = 1/2/3. |
| `test_target_count_hold_monster` | v2.127.0 — `upcast_target_count(slot, base_level=5)` → L5/L6/L9 = 1/2/5. |
| `test_target_count_clamps_and_params` | v2.127.0 — clamps below base level; custom `base_targets`/`per_slot` (Bless-style 3 +1/slot). |
| `test_pool_dice_sleep` | v2.128.0 — `upcast_pool_dice(slot, base_level=1, base_dice=5, per_slot_dice=2)` → L1/L2/L3 = 5/7/9 (Sleep HP pool). |
| `test_pool_dice_clamps_below_base` | v2.128.0 — slot below base never under-rolls the base dice count. |
| `test_parses_flat_healing_aid` | v2.130.0 — Aid's "+5 hit points for each slot level above 2nd" → `{flat_healing_per_slot: 5}`. |
| `test_parses_flat_healing_heal` | v2.130.0 — Heal's "+10 healing per slot above 6th" → `{flat_healing_per_slot: 10}`. |
| `test_parses_flat_healing_false_life` | v2.130.0 — False Life's "5 additional temporary hit points" (keyword AFTER the number) → `{flat_healing_per_slot: 5}` via the broadened classifier. |
| `test_flat_does_not_match_dice_clause` | v2.130.0 — regression guard: a dice clause must not surface the dice-internal digit as a flat per-slot value. |
| `test_flat_scaler_pure_flat_base` | v2.130.0 — `scale_flat_for_upcast("70", 10, 1)` → "80" (Heal at L7). |
| `test_flat_scaler_dice_plus_flat_base` | v2.130.0 — `scale_flat_for_upcast("1d4+4", 5, 1)` → "1d4+9" (merges into the +N suffix; False Life at L2). |
| `test_flat_scaler_pure_dice_base` | v2.130.0 — `scale_flat_for_upcast("1d8", 5, 1)` → "1d8+5" (appends +N to a pure dice base). |
| `test_flat_scaler_base_unchanged_on_no_op` | v2.130.0 — extra_levels=0 / per_slot=0 / unparseable base each return the base unchanged. |

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

### `test_shake_awake.py`
v2.49.62 — `POST /shake_awake`. Closes the v2.49.61 filed "wake-via-shake" item. RAW Sleep's third wake branch: another creature uses an action to shake the sleeper awake. Any class can shake (RAW "someone"); costs 1 action. Scoped to Sleep-sourced Unconscious buffs only — shaking a dying-at-0-HP creature isn't a wake.

| Test | What it asserts |
|------|-----------------|
| `test_shake_awake_npc` | Pip shakes a Sleep'd bandit; assert `buffs_removed==1`, latest battle_update shows bandit without Unconscious, 🤚 log names both shaker + bandit. |
| `test_shake_awake_pc` | Pip shakes a Sleep'd Magnus; assert Unconscious dropped from both hub AND sheet mirror; 🤚 log names Pip + Magnus. |
| `test_shake_awake_not_asleep_no_buff` | Target has no Unconscious buff → 409 `not_asleep`. |
| `test_shake_awake_not_asleep_non_sleep_unconscious` | Target has generic Unconscious (no `source_spell==Sleep`) → 409 `not_asleep`. Regression guard: shaking a dying/knocked-out creature isn't a Sleep-wake. |

### `test_sleep_wake_on_damage.py`
v2.49.61 — closes the "wake-on-damage" filed item from v2.49.58. RAW Sleep wakes the sleeper on damage. The new `_wake_sleeping_on_damage` hook fires from both branches of `_apply_damage_to_combatant` after damage applies; scoped to buffs with `source_spell == "Sleep"` so other Unconscious sources (future knockout features etc.) aren't accidentally cleared. Same commit also fixes a pre-existing latent bug in `_resistance_halve` (crashed on condition buffs with `effects: list`; now skips non-dict effects).

| Test | What it asserts |
|------|-----------------|
| `test_wake_on_damage_npc` | Bandit pre-seeded with Sleep-Unconscious buff; Krieger attacks (auto_apply_damage on) → latest `battle_update` shows bandit's Unconscious dropped + 🌅 wake log fires. |
| `test_wake_on_damage_pc` | Magnus pre-seeded with Sleep-Unconscious buff; Krieger attacks → Unconscious dropped from BOTH hub and sheet mirror + 🌅 wake log names Magnus. |
| `test_non_sleep_unconscious_preserved` | Bandit pre-seeded with a generic Unconscious buff (no `source_spell == "Sleep"`); Krieger attacks → buff preserved (regression guard against over-broad clearing). |

### `test_attack_uplift_vs_label.py`
v2.99.190 — attack `damage_breakdown` suffix labels rider uplifts with "(vs NAME)" when the uplift dict carries `vs_combatant_id` (v2.99.188). The user-visible rendering path is the server-baked breakdown string; `tabletop.js` doesn't consume `auto_uplifts` directly. Closes the v2.99.188 UI follow-up.

| Test | What it asserts |
|------|-----------------|
| `test_attack_breakdown_labels_rider_vs_target` | Rowan marks Pip → attacks Pip → `damage_breakdown` contains "(vs Pip Quickfingers)" + the uplift's `vs_combatant_id` matches Pip's combatant ID. |
| `test_attack_breakdown_no_rider_no_vs_label` | Control: no Hunter's Mark in play → no "(vs ...)" suffix in `damage_breakdown` (non-rider uplifts like Rage / Colossus Slayer don't gain spurious labels). |

### `test_attack_multi_target.py`
v2.49.85 — `/attack` accepts `target_combatant_ids: list` in addition to `target_combatant_id`. Each list entry gets its own fresh attack + damage roll (RAW weapon attacks per-target). Per-target outcomes return in `auto_attack_targets`. Closes the v2.49.79 TODO's server side.

| Test | What it asserts |
|------|-----------------|
| `test_attack_legacy_single_target_emits_one_entry` | Legacy `target_combatant_id` still works; `auto_attack_targets` has 1 entry mirroring the legacy fields. |
| `test_attack_multi_target_fresh_rolls` | 3-entry list → 3 fresh per-target attack rolls + damage rolls. |
| `test_attack_multi_target_auto_apply_damage` | With `auto_apply_damage` on, each hit target's HP drops by its per-target damage_applied. |
| `test_attack_no_target_yields_empty_list` | Untargeted attack → `auto_attack_targets: []`. |

### `test_ruler_broadcast.py`
v2.49.84 — Phase 3E of the ruler/range plan. `POST /api/campaign/{cid}/ruler_broadcast` fans out the requester's ruler measurement to every connected campaign client. Auth: any campaign member. Server does no persistence; broadcast-only.

| Test | What it asserts |
|------|-----------------|
| `test_ruler_broadcast_show` | `{action: "show", points: [...], multi_segment: false}` → 200 + WS `ruler_broadcast` with `user_id`, `user_name`, `action="show"`, `points`, `multi_segment=false`. |
| `test_ruler_broadcast_show_multi_segment` | 4-point path + `multi_segment: true` → WS broadcast carries all 4 points + flag. |
| `test_ruler_broadcast_hide` | `{action: "hide"}` → 200 + WS broadcast with `action="hide"` and no points/multi_segment fields. |
| `test_ruler_broadcast_invalid_action` | Action other than `show` / `hide` → 400. |
| `test_ruler_broadcast_invalid_points_type` | Non-list `points` → 400. |
| `test_ruler_broadcast_non_member_403` | Non-existent campaign id → 403 (membership check fails). |

### `test_place_aoe_range.py`
v2.49.77 — Phase 3A of the ruler/range plan: server-side range enforcement on AoE casts via `/place_aoe`. The picker's chosen `center: {x, y}` is compared to the caster's token position vs the parsed spell range. Same three-tier override as Phase 2C (GM auto-bypass, player override + not strict, otherwise enforced). Tests use Bob (Thalindra's owner, non-GM) so the non-GM enforcement fires.

| Test | What it asserts |
|------|-----------------|
| `test_place_aoe_in_range_succeeds` | Thalindra at (100,100); Fireball center 50 ft away → 200 (well within 150 ft range). |
| `test_place_aoe_out_of_range_409` | Center 350 ft away → 409 `out_of_range` with `range_ft=150`, `distance_ft=350.0`, `spell_name="Fireball"`, `target_name="(AoE cast point)"`. |
| `test_place_aoe_override_bypasses_409` | Same out-of-range setup + `override_range=True` → 200. |
| `test_place_aoe_gm_bypasses_range_check` | gm_client places out-of-range AoE without `override_range` → 200 (auto-bypass). |

### `test_cast_attack_range.py`
v2.49.76 — Phase 2D of the ruler/range plan. Extends `_check_cast_range` to `/attack`, `/cast_hex`, `/use_stunning_strike`, `/use_open_hand_technique`. `/cast_sleep` is intentionally skipped (AoE multi-target — see endpoint comment + Phase 2C "When NOT to enforce"). Ownership limitation: only Pip (Alice's) and Thalindra (Bob's) are non-GM-owned in the demo, so the 409 path is directly testable only via `/attack`; the other three endpoints get integration-call-site happy-path coverage to confirm they don't break.

| Test | What it asserts |
|------|-----------------|
| `test_attack_in_range_succeeds` | Alice's Pip swings shortsword (5 ft) at a bandit 5 ft away → 200. |
| `test_attack_out_of_range_409` | Same setup, bandit 50 ft away → 409 `out_of_range` with `range_ft=5`, `distance_ft=50.0`, `spell_name="Shortsword"`. |
| `test_attack_thrown_long_range_uses_long_band` | Pip's Dagger (20/60 ft thrown) at a bandit ~50 ft away → 200. Pins `max_range_ft` collapsing the (20, 60) tuple to the long band. |
| `test_cast_hex_in_range_succeeds` | Magnus Hexes a bandit 5 ft away → 200. Hex range = 90 ft RAW; GM-owned caster so range auto-bypasses but the call site invocation is verified. |
| `test_stunning_strike_in_range_succeeds` | Kael's Stunning Strike on a bandit 5 ft away → 200. Melee 5 ft RAW. |
| `test_open_hand_technique_in_range_succeeds` | Kael's Open Hand Technique (no_reactions mode) on a bandit 5 ft away → 200. Melee 5 ft RAW. |

### `test_cast_spell_range.py`
v2.49.75 — Phase 2C of the ruler/range plan. New `_check_cast_range` helper + `override_range` body field on `/cast_spell` + 409 `out_of_range` response. Tests use Bob (Thalindra's owner, non-GM) so the non-GM enforcement paths fire; the GM-bypass test uses gm_client.

| Test | What it asserts |
|------|-----------------|
| `test_in_range_succeeds` | Thalindra at (100,100), bandit at +10 ft via test-NPC token; Bob casts Fire Bolt (120 ft) → 200. |
| `test_out_of_range_409` | Bandit at +350 ft; Bob casts Fire Bolt → 409 `out_of_range`. Response shape: `error`, `range_ft=120`, `distance_ft=350.0`, `spell_name="Fire Bolt"`, `source_name`, `target_name`. |
| `test_override_range_bypasses_409` | Same out-of-range setup + `override_range=True` → 200. Strict mode is off in the demo. |
| `test_gm_bypasses_range_check` | gm_client casts same out-of-range setup WITHOUT `override_range` → 200 (GM auto-bypass). |
| `test_self_range_skips_check` | Cast Shield (range=Self) → 200 regardless of any target position (parser returns 0 → check skips). |
| `test_off_map_target_skips_check` | Cast Fire Bolt at a synthesized target_name (no Token row on the active map) → 200 (helper returns None → check skips). |

### `test_cast_sleep_immunity.py`
v2.49.64 — closes the v2.49.58 "undead / charm-immune exclusion" filed item. RAW Sleep: "Undead and creatures immune to being charmed aren't affected by this spell." New `_is_sleep_immune` helper checks the target's monster template (NPCs) or character sheet (PCs) for `race contains "undead"` or `condition_immunities contains "charmed"`. Immune targets land in `unaffected` with `reason="undead"` or `reason="charm_immune"`. Same commit adds Skeleton (Undead) + Doppelganger (Monstrosity + charm-immune) templates to the demo seed + DB.

| Test | What it asserts |
|------|-----------------|
| `test_undead_excluded` | Skeleton + bandit targeted at L3. Skeleton lands in `unaffected` with `reason="undead"`; bandit still affected. |
| `test_charm_immune_excluded` | Doppelganger (non-undead but charm-immune) lands in `unaffected` with `reason="charm_immune"`. Regression guard that the two branches are distinct. |
| `test_regular_humanoid_still_affected` | Plain bandit (humanoid, no charm immunity) → affected, NOT in unaffected with an immunity reason. Regression guard against over-broad immunity filtering. |

### `test_cast_sleep_fey_ancestry.py`
v2.99.15 — (D) Phase 3 first-ship: Fey Ancestry magical sleep immunity. Extends `_is_sleep_immune._check_sheet` to read the race slug via `_race_slug_from_sheet` and return `(True, "fey-ancestry")` for `elf` / `half-elf` normalized slugs. Elf / Half-Elf / Wood Elf / High Elf / Dark Elf targets silently filter into `unaffected[]` with `reason: "fey-ancestry"` — RAW (PHB p.23): "magic can't put you to sleep."

| Test | What it asserts |
|------|-----------------|
| `test_elf_target_immune_via_fey_ancestry` | Lyra casts Sleep at Thalindra (Elf Wizard) at 5 HP under a 7d8 pool → Thalindra lands in `unaffected` with `reason="fey-ancestry"` (never counts against HP pool). |
| `test_half_elf_target_immune_via_fey_ancestry` | Lyra (Half-Elf Bard) targets herself with Sleep → same immunity gate. |
| `test_wood_elf_target_immune_via_fey_ancestry` | Mira (Wood Elf Druid) → confirms slug normalizer folds Wood Elf → elf. |
| `test_halfling_target_NOT_immune` | Control: Pip (Halfling) → affected, regression guard against over-broad immunity. |

### `test_relentless_endurance.py`
v2.99.17 — (D) Phase 3 second-ship: Half-Orc Relentless Endurance auto-clamp. `_apply_hp_change` reads the `relentless-endurance` resource (1/long-rest counter on Krieger's sheet); when damage drops the PC from alive → 0 HP AND the massive-damage rule didn't fire AND the resource is available, the function clamps `new_current = 1`, decrements the resource, and stays at `status="alive"`. Result dict carries `relentless_endurance_fired` / `relentless_endurance_damage` flags so `_apply_damage_to_combatant` can emit the `feature_used(source=relentless-endurance)` + `resource_update` broadcasts.

| Test | What it asserts |
|------|-----------------|
| `test_relentless_endurance_clamps_zero_to_one` | Krieger at 3 HP; Pip attacks; after a hit dealing ≥3 damage, the `character_hp_update` broadcast carries `current=1`, `resource_update` for `relentless-endurance` carries `current=0`, AND `feature_used(source=relentless-endurance)` broadcast fires for Krieger. |
| `test_relentless_endurance_skips_non_half_orc` | Control: Lyra at 3 HP; same attack setup; HP-update broadcast carries `current=0` (no clamp); no Relentless Endurance broadcast. Regression guard. |

### `test_savage_attacks.py`
v2.99.23 — Half-Orc Savage Attacks. `_compute_attack_auto_uplifts` extended with `is_crit` + `weapon_damage_expr` kwargs. When the attacker is Half-Orc + the hit is a crit + the damage type is physical (melee proxy via `_PHYSICAL_DAMAGE_TYPES`), the helper adds one extra die roll to the uplift list with `source="savage-attacks"`. Krieger's Greataxe (1d12) is the demo fixture.

| Test | What it asserts |
|------|-----------------|
| `test_savage_attacks_fires_on_half_orc_crit` | Krieger crits a Bandit (seeded d20=20) → `auto_uplifts` includes `{source="savage-attacks", expression="1d12"}` (the weapon's first die). |
| `test_savage_attacks_skips_non_half_orc` | Control: Garrik (Variant Human Champion Fighter) crits (d20 ∈ {19, 20}) → no Savage Attacks uplift. Regression guard. |

### `test_hellish_resistance.py`
v2.99.18 — (D) Phase 3 third-ship: Tiefling Hellish Resistance (sheet-level `damage_resistances` field on PCs). `_resistance_halve` extended to read the sheet root's `damage_resistances` list before walking buffs. Same field shape NPC templates already use. Zara Emberfire's demo sheet ships `damage_resistances: ["fire"]`.

| Test | What it asserts |
|------|-----------------|
| `test_tiefling_halves_fire_damage` | Thalindra casts Fire Bolt at Zara (Tiefling); deterministic seed lands a hit; `damage_applied == damage_total // 2` (resistance halving). |
| `test_no_resistance_for_non_tiefling` | Control: Fire Bolt at Pip (Halfling) → `damage_applied == damage_total` (no halving). Regression guard against over-broad resistance match. |

### `test_cast_sleep_multi_class.py`
v2.49.63 — closes the "add Sleep to Bard / Sorcerer / Warlock lists" filed item. Seed-list backfill verified via one happy-path cast per class. Sleep is RAW on bard / sorcerer / warlock / wizard lists; pre-v2.49.63 only Thalindra (wizard) had it.

| Test | What it asserts |
|------|-----------------|
| `test_cast_sleep_bard` | Lyra (Bard) casts Sleep at L1 → `class_slug=bard`, `pool_expr=5d8`, single 5-HP bandit affected. |
| `test_cast_sleep_sorcerer` | Zara (Sorcerer) casts Sleep at L1 → `class_slug=sorcerer`, 5d8 pool, bandit affected. |
| `test_cast_sleep_warlock_l3` | Magnus (Warlock Lv 5, L3-only Pact Magic) casts at L3 → `pool_expr=9d8` (5 + 2*2), 9–72 pool range. |

### `test_cast_sleep.py`
v2.49.58 — `POST /cast_sleep`. RAW Sleep (1st-level enchantment, bard/sorcerer/warlock/wizard). Rolls 5d8 + 2d8 per slot level above 1st as an HP pool; affects creatures in ascending order of current HP, subtracting each affected creature's HP from the pool. No save, no concentration. Unconscious key is in `_INCAPACITATING_BUFF_KEYS`, so a PC sleeper drops their own concentration via the v2.49.51 hook. Dedicated endpoint (not `/cast_spell`) because the HP-pool targeting doesn't fit save-or-suck or save-for-half.

| Test | What it asserts |
|------|-----------------|
| `test_sleep_happy_path_npc` | Single 5-HP bandit at L1; 5d8 min=5 → always affected. Response shape: `pool_expr`, `pool_total`, `affected`, `unaffected`. |
| `test_sleep_ordering_invariant` | 3 bandits at 1/2/3 HP; affected list is non-decreasing by HP; sum(affected.hp) <= pool_total; first unaffected (if any) has hp > pool_remaining. Dice-independent. |
| `test_sleep_high_hp_skipped` | Bandit HP=50; 5d8 max=40 < 50 → always unaffected. |
| `test_sleep_already_unconscious_skipped` | Bandit pre-seeded with Unconscious buff is omitted from both `affected` and `unaffected` lists (RAW: ignored when ordering). |
| `test_sleep_drops_pc_concentration` | Magnus has Hex up (concentration); Magnus HP=5; Thalindra Sleeps Magnus. Asserts Unconscious lands on Magnus + Hex drops via v2.49.51 hook + 💀 GM log fires. |
| `test_sleep_upcast_scales_pool` | L3 slot → `pool_expr == "9d8"` (5 + 2 * 2). |
| `test_sleep_no_slot` | Drain Thalindra's 4 L1 slots; next call → 409 `no_slot`. Restores via long-rest at end to keep `test_cast_magic_missile` happy. |
| `test_sleep_wrong_class` | Krieger (Barbarian) → 409 `wrong_class` with `expected=wizard`. |

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

### `test_use_dash.py`
v2.100.3 — `/use_dash` propagates the Dash movement-cap bonus to the authoritative hub state + broadcasts `economy_update` (carrying `dash_bonus_ft`) so the bonus survives a player's wholesale `battle_update` replace. Pip Quickfingers is the seeded fixture.

| Test | What it asserts |
|------|-----------------|
| `test_use_dash_propagates_dash_bonus` | Dash a seeded combatant → `economy_update` carries `slot=action`, `used=True`, `dash_bonus_ft=30`; `feature_used(source=dash-action)` fires; response echoes `dash_bonus_ft=30`. |
| `test_use_dash_stacks_additively` | A second Dash stacks the absolute bonus (30 → 60) rather than overwriting. |
| `test_use_dash_not_in_battle_no_economy_update` | Error path: dashing a character absent from init still fires `feature_used` but broadcasts NO `economy_update` and returns `dash_bonus_ft: null`. |

### `test_h3_invocations.py`
v2.99.250 — Phase H.3 batched 5-invocation breadth ship. Single `/use_invocation` endpoint backed by a 5-entry registry: Devil's Sight, Mask of Many Faces, Hex Warrior, Lifedrinker, Lance of Lethargy. Magnus Hexbinder (Warlock The Fiend Lv 5) is the fixture.

| Test | What it asserts |
|------|-----------------|
| `test_use_inv_devils_sight_happy` | Magnus Lv 5 → Devil's Sight (min Lv 2) succeeds; broadcast (source `eldritch-invocation`). |
| `test_use_inv_bad_slug` | Unknown slug → 400. |
| `test_use_inv_wrong_class` | Pip (Rogue) → 409 `wrong_class`. |
| `test_use_inv_lifedrinker_no_pact` | Magnus PATCH'd to Lv 12 (level prereq satisfied) but no `pact_boon == "blade"` → 409 `pact_prereq_unmet`. |
| `test_use_inv_lifedrinker_level_too_low` | Lifedrinker at Lv 5 (needs 12) → 409 `level_too_low`. |
| `test_use_inv_hex_warrior_wrong_subclass` | Magnus default subclass "The Fiend" → 409 `subclass_prereq_unmet` (Hex Warrior needs Hexblade). |

### `test_emissary_of_peace.py`
v2.99.275 — Redemption Paladin (XGE p.39) Emissary of Peace CD (H.2 depth). Bonus action self-buff: +5 Persuasion 10 min.

| Test | What it asserts |
|------|-----------------|
| `test_use_eop_happy` | Redemption Caelan → `persuasion_bonus == 5`, `duration_minutes == 10`, CD 1 → 0. |
| `test_use_eop_out_of_cd` | CD 0 → 409. |
| `test_use_eop_wrong_subclass` | Default Caelan (Devotion) → 409. |

### `test_rebuke_the_violent.py`
v2.99.249 — Oath of Redemption (Paladin subclass, XGE p.39) Rebuke the Violent reaction CD (Phase H.2 FIFTH + FINAL oath). Caelan PATCH'd to Redemption + CD 1/1 + Bandit attacker in battle. DC 14.

| Test | What it asserts |
|------|-----------------|
| `test_use_rtv_happy` | Rebuke a Bandit who dealt 15 dmg → `save_dc == 14`, `psychic_damage_on_fail == 15`, `psychic_damage_on_success == 7`, broadcast (source `rebuke-the-violent`). |
| `test_use_rtv_missing_damage` | No `damage_dealt` body → 400. |
| `test_use_rtv_zero_damage` | `damage_dealt: 0` → 400 (must be >= 1). |
| `test_use_rtv_attacker_not_in_battle` | Unknown attacker_combatant_id → 404. |
| `test_use_rtv_out_of_cd` | `channel-divinity.current = 0` → 409 `out_of_uses`. |
| `test_use_rtv_wrong_subclass` | Default Caelan (Devotion) → 409 `wrong_subclass_or_level`. |

### `test_peerless_athlete.py`
v2.99.276 — Glory Paladin (TCE p.55) Peerless Athlete CD (H.2 depth). Bonus action: 10 min advantage on Athletics + Acrobatics + +10 ft jump distance.

| Test | What it asserts |
|------|-----------------|
| `test_use_pa_happy` | Glory Caelan → `jump_bonus_ft == 10`, `duration_minutes == 10`, CD 1 → 0. |
| `test_use_pa_out_of_cd` | CD 0 → 409. |
| `test_use_pa_wrong_subclass` | Default Caelan (Devotion) → 409. |

### `test_inspiring_smite.py`
v2.99.248 — Oath of Glory (Paladin subclass, TCE p.55) Inspiring Smite bonus-action CD (Phase H.2 fourth oath). Rolls 2d8 + paladin level temp HP, divides evenly (remainder to first targets).

| Test | What it asserts |
|------|-----------------|
| `test_use_is_happy_two_targets` | 2 targets → `paladin_level == 7`, `total_temp_hp` in [9, 23], allocations sum equals total, broadcast. |
| `test_use_is_three_targets_remainder` | 3 targets → sum of allocations == total, first allocation >= last (remainder skew). |
| `test_use_is_empty_list` | Empty target list → 400. |
| `test_use_is_out_of_cd` | `channel-divinity.current = 0` → 409 `out_of_uses`. |
| `test_use_is_wrong_subclass` | Default Caelan (Devotion) → 409 `wrong_subclass_or_level`. |

### `test_aura_of_conquest.py`
v2.99.273 — Conquest Paladin (XGE p.37) Aura of Conquest passive (H.2 depth). Lv 7+ aura that reduces frightened creatures' speed to 0 + deals half-paladin-level psychic at turn start. Lv 18+ radius bumps 10 → 30 ft. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_aoc_happy_lv7` | Lv 7 Caelan → `radius_ft == 10`, `psychic_damage == 3`, broadcast (source `aura-of-conquest`). |
| `test_use_aoc_lv18_radius_upgrade` | Lv 18 Caelan → `radius_ft == 30`, `psychic_damage == 9`. |
| `test_use_aoc_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_aoc_level_gate` | Conquest at Lv 6 → 409. |

### `test_aura_of_warding.py`
v2.99.279 — Ancients Paladin (PHB p.87) Aura of Warding passive (H.2 depth). Lv 7+ aura: you + friendly creatures within have resistance to damage from spells. Lv 18+ radius bumps 10 → 30 ft. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_aow_happy_lv7` | Lv 7 Caelan → `radius_ft == 10`, broadcast (source `aura-of-warding`). |
| `test_use_aow_lv18_radius_upgrade` | Lv 18 Caelan → `radius_ft == 30`. |
| `test_use_aow_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_aow_level_gate` | Ancients at Lv 6 → 409. |

### `test_relentless_avenger.py`
v2.99.280 — Vengeance Paladin (PHB p.88) Relentless Avenger OA-rider (H.2 depth). Lv 7+: on OA hit, you can move up to half your speed as part of the same reaction without provoking OAs. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ra_happy_lv7` | Lv 7 Caelan (speed 30) → `bonus_move_ft == 15`, `base_speed == 30`, broadcast (source `relentless-avenger`). |
| `test_use_ra_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_ra_level_gate` | Vengeance at Lv 6 → 409. |

### `test_aura_of_the_guardian.py`
v2.99.281 — Redemption Paladin (XGE p.39) Aura of the Guardian reactive shield (H.2 depth). Lv 7+: when an ally within 10 ft (30 ft at Lv 18+) takes damage, you reaction-redirect the damage to yourself. Damage can't be reduced. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_aotg_happy_lv7` | Lv 7 Caelan → `radius_ft == 10`, broadcast (source `aura-of-the-guardian`). |
| `test_use_aotg_lv18_radius_upgrade` | Lv 18 Caelan → `radius_ft == 30`. |
| `test_use_aotg_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_aotg_level_gate` | Redemption at Lv 6 → 409. |

### `test_aura_of_alacrity.py`
v2.99.282 — Glory Paladin (XGE p.37) Aura of Alacrity speed aura (H.2 depth — CLOSES the H.2 Lv 7 batch). Lv 7+: your walking speed +10 ft permanently; allies starting their turn within 5 ft (10 ft at Lv 18+) get +10 ft walking speed until end of turn. Note: 5/10 radius is distinct from the 10/30 ft pattern of the other oath auras. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_aoa_happy_lv7` | Lv 7 Caelan → `radius_ft == 5`, `speed_bonus_ft == 10`, broadcast (source `aura-of-alacrity`). |
| `test_use_aoa_lv18_radius_upgrade` | Lv 18 Caelan → `radius_ft == 10` (RAW upgrade). |
| `test_use_aoa_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_aoa_level_gate` | Glory at Lv 6 → 409. |

### `test_undying_sentinel.py`
v2.99.283 — Ancients Paladin (PHB p.87) Undying Sentinel "drop to 1 HP, not 0" (H.2 deeper, Lv 15). Once-per-long-rest. Auto-bootstraps an `undying-sentinel` resource if missing; refilled by the generic long-rest resource hook. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_us_happy_lv15` | Lv 15 Caelan → `uses_remaining == 0`, broadcast (source `undying-sentinel`). |
| `test_use_us_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_us_level_gate` | Ancients at Lv 14 → 409. |
| `test_use_us_out_of_uses` | Second back-to-back call → 409 `no_uses_left`. |
| `test_use_us_long_rest_refills` | Use → long rest → use again → 200 (resource refilled). |

### `test_soul_of_vengeance.py`
v2.99.284 — Vengeance Paladin (PHB p.88) Soul of Vengeance reactive melee (H.2 deeper, Lv 15). When a Vow of Enmity target attacks, reaction → melee weapon attack against them. Costs a reaction chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_sov_happy_lv15` | Lv 15 Caelan → 200, broadcast (source `soul-of-vengeance`). |
| `test_use_sov_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_sov_level_gate` | Vengeance at Lv 14 → 409. |

### `test_scornful_rebuke.py`
v2.99.285 — Conquest Paladin (XGE p.37) Scornful Rebuke passive psychic counter (H.2 deeper, Lv 15). When a creature hits you with an attack, they take psychic damage = max(1, CHA mod). No chip — passive auto-trigger. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_sr_happy_lv15` | Lv 15 Caelan (CHA 16) → `psychic_damage == 3`, broadcast (source `scornful-rebuke`). |
| `test_use_sr_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_sr_level_gate` | Conquest at Lv 14 → 409. |

### `test_glorious_defense.py`
v2.99.286 — Glory Paladin (XGE p.38) Glorious Defense reactive AC bonus (H.2 deeper, Lv 15). When you or an ally within 10 ft is hit, reaction → +CHA mod (min +1) AC; if hit becomes miss, follow-up weapon attack on attacker. Costs a reaction chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_gd_happy_lv15` | Lv 15 Caelan (CHA 16) → `ac_bonus == 3`, broadcast (source `glorious-defense`). |
| `test_use_gd_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_gd_level_gate` | Glory at Lv 14 → 409. |

### `test_protective_spirit.py`
v2.99.287 — Redemption Paladin (XGE p.39) Protective Spirit self-heal (H.2 deeper, Lv 15 — CLOSES the H.2 Lv 15 batch). End of turn, if at half HP or less and not incapacitated: regain 1d6 + half-paladin-level HP. v1 announce-only — actual HP application is GM-tracked.

| Test | What it asserts |
|------|-----------------|
| `test_use_ps_happy_lv15` | Lv 15 Caelan → `die_rolled` in [1,6], `half_paladin_level == 7`, `heal_amount` in [8,13], broadcast (source `protective-spirit`). |
| `test_use_ps_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_ps_level_gate` | Redemption at Lv 14 → 409. |

### `test_elder_champion.py`
v2.99.288 — Ancients Paladin (PHB p.87) Elder Champion Lv 20 capstone transform (H.2 deeper). Once-per-long-rest. Auto-bootstraps an `elder-champion` resource if missing; refilled by long rest. Action chip + transform broadcast. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ec_happy_lv20` | Lv 20 Caelan → `uses_remaining == 0`, `turn_start_heal == 10`, `aura_radius_ft == 10`, `duration_minutes == 1`, broadcast (source `elder-champion`). |
| `test_use_ec_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_ec_level_gate` | Ancients at Lv 19 → 409. |
| `test_use_ec_out_of_uses` | Second back-to-back call → 409 `no_uses_left`. |
| `test_use_ec_long_rest_refills` | Use → long rest → use again → 200 (resource refilled). |

### `test_avenging_angel.py`
v2.99.289 — Vengeance Paladin (PHB p.88) Avenging Angel Lv 20 capstone transform (H.2 deeper). 1 hour: wings + fly 60 ft; 30 ft frightful aura (Wis save DC 8 + prof + CHA). Auto-bootstraps an `avenging-angel` resource if missing; refilled by long rest. Action chip + transform broadcast. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_aa_happy_lv20` | Lv 20 Caelan (stale prof 3, CHA 16) → `save_dc == 14`, `fly_speed_ft == 60`, `aura_radius_ft == 30`, `duration_minutes == 60`, broadcast (source `avenging-angel`). |
| `test_use_aa_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_aa_level_gate` | Vengeance at Lv 19 → 409. |
| `test_use_aa_long_rest_refills` | Use → long rest → use again → 200 (resource refilled). |

### `test_invincible_conqueror.py`
v2.99.290 — Conquest Paladin (XGE p.37) Invincible Conqueror Lv 20 capstone (H.2 deeper). 1 min: resistance to all damage, +1 extra attack on Attack action, melee weapon crits on 19-20. Auto-bootstraps `invincible-conqueror` resource if missing; refilled by long rest. Action chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ic_happy_lv20` | Lv 20 Caelan → `resistance_all_damage == True`, `extra_attack == 1`, `crit_range_min == 19`, `duration_minutes == 1`, broadcast (source `invincible-conqueror`). |
| `test_use_ic_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_ic_level_gate` | Conquest at Lv 19 → 409. |
| `test_use_ic_long_rest_refills` | Use → long rest → use again → 200 (resource refilled). |

### `test_living_legend.py`
v2.99.291 — Glory Paladin (XGE p.38) Living Legend Lv 20 capstone (H.2 deeper). Bonus action transform 1 min: advantage on CHA checks; 1/turn (up to 4 total) turn missed weapon attack into hit; once, reroll a failed save as reaction. Auto-bootstraps `living-legend` resource; refilled by long rest. Bonus chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ll_happy_lv20` | Lv 20 Caelan → `miss_to_hit_uses == 4`, `save_reroll_uses == 1`, `duration_minutes == 1`, broadcast (source `living-legend`). |
| `test_use_ll_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_ll_level_gate` | Glory at Lv 19 → 409. |
| `test_use_ll_long_rest_refills` | Use → long rest → use again → 200 (resource refilled). |

### `test_emissary_of_redemption.py`
v2.99.292 — Redemption Paladin (XGE p.39) Emissary of Redemption Lv 20 passive capstone (H.2 deeper — CLOSES the H.2 Lv 20 batch). Resistance to all damage from creatures + half-damage radiant counter on hit. Both negated against a creature you attack/spell/damage until next long rest. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_er_happy_lv20` | Lv 20 Caelan → `resistance_all_creature_damage == True`, `radiant_back_fraction == 0.5`, broadcast (source `emissary-of-redemption`). |
| `test_use_er_wrong_subclass` | Default Caelan (Devotion) → 409. |
| `test_use_er_level_gate` | Redemption at Lv 19 → 409. |

### `test_corona_of_light.py`
v2.99.293 — Light Domain Cleric (PHB p.61) Corona of Light Lv 17 capstone (H.1 deeper — opens H.1 Lv 17 batch). Action: bright sunlight 60 ft + dim 30 ft beyond, 1 min, enemies in bright light have disadvantage on saves vs your fire/radiant spells. Action chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_col_happy_lv17` | Lv 17 Tavik → `bright_light_radius_ft == 60`, `dim_light_radius_ft == 90`, `duration_minutes == 1`, disadvantage types fire+radiant, broadcast (source `corona-of-light`). |
| `test_use_col_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_col_level_gate` | Light at Lv 16 → 409. |

### `test_stormborn.py`
v2.99.294 — Tempest Domain Cleric (PHB p.63) Stormborn Lv 17 passive (H.1 deeper). Fly speed = walking speed when not underground or indoors. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_sb_happy_lv17` | Lv 17 Tavik (dwarf speed 25) → `fly_speed_ft == 25`, `outdoor_only == True`, broadcast (source `stormborn`). |
| `test_use_sb_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_sb_level_gate` | Tempest at Lv 16 → 409. |

### `test_supreme_healing.py`
v2.99.295 — Life Domain Cleric (PHB p.61) Supreme Healing Lv 17 passive (H.1 deeper). When you would roll dice to restore HP with a spell, use max on each die instead. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_sh_happy_lv17` | Lv 17 Tavik → `max_dice_substitution == True`, broadcast (source `supreme-healing`). |
| `test_use_sh_wrong_subclass` | Light Domain Tavik at Lv 17 → 409. |
| `test_use_sh_level_gate` | Life at Lv 16 → 409. |

### `test_avatar_of_battle.py`
v2.99.296 — War Domain Cleric (PHB p.63) Avatar of Battle Lv 17 passive (H.1 deeper). Resistance to bludgeoning, piercing, slashing from nonmagical attacks. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_aob_happy_lv17` | Lv 17 Tavik → resistance_types BPS, `nonmagical_only == True`, broadcast (source `avatar-of-battle`). |
| `test_use_aob_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_aob_level_gate` | War at Lv 16 → 409. |

### `test_improved_reaper.py`
v2.99.297 — Death Domain Cleric (DMG p.97) Improved Reaper Lv 17 passive (H.1 deeper). 1st-5th level necromancy spells targeting one creature can target two creatures within range + within 5 ft of each other. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ir_happy_lv17` | Lv 17 Tavik → `max_targets == 2`, `max_target_separation_ft == 5`, school necromancy, levels 1-5, broadcast (source `improved-reaper`). |
| `test_use_ir_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_ir_level_gate` | Death at Lv 16 → 409. |

### `test_improved_duplicity.py`
v2.99.298 — Trickery Domain Cleric (PHB p.62) Improved Duplicity Lv 17 passive (H.1 deeper). Invoke Duplicity now creates up to 4 duplicates (was 1). Bonus action moves any number up to 30 ft each, max 120 ft range. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_id_happy_lv17` | Lv 17 Tavik → `max_duplicates == 4`, `bonus_move_per_duplicate_ft == 30`, `max_range_ft == 120`, broadcast (source `improved-duplicity`). |
| `test_use_id_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_id_level_gate` | Trickery at Lv 16 → 409. |

### `test_saint_of_forge_and_fire.py`
v2.99.299 — Forge Domain Cleric (XGE p.18) Saint of Forge and Fire Lv 17 passive (H.1 deeper). Fire immunity + (while wearing heavy armor) resistance to BPS from nonmagical attacks. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_sff_happy_lv17` | Lv 17 Tavik → `fire_immunity == True`, `heavy_armor_bps_resistance == True`, BPS in `resistance_types`, broadcast (source `saint-of-forge-and-fire`). |
| `test_use_sff_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_sff_level_gate` | Forge at Lv 16 → 409. |

### `test_keeper_of_souls.py`
v2.99.300 — Grave Domain Cleric (XGE p.19) Keeper of Souls Lv 17 (H.1 deeper). When enemy within 60 ft dies, you or one creature within 60 ft heals HP = enemy's HD. 1/turn. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ks_happy_lv17` | Lv 17 Tavik, enemy HD 5 → `heal_amount == 5`, `max_range_ft == 60`, broadcast (source `keeper-of-souls`). |
| `test_use_ks_default_hd_clamp` | Missing `enemy_hit_dice` → `heal_amount == 1` (clamp). |
| `test_use_ks_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_ks_level_gate` | Grave at Lv 16 → 409. |

### `test_visions_of_the_past.py`
v2.99.301 — Knowledge Domain Cleric (PHB p.60) Visions of the Past Lv 17 (H.1 deeper). 1 min meditation → dream-like glimpses of recent events. Concentration up to WIS-score minutes. Modes: object (24h held-object history) or area (50-ft cube 24h history). Auto-bootstraps `visions-of-the-past` resource (max=1, reset=short). v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_vp_object_mode` | Lv 17 Tavik (WIS 16), object mode → `mode == "object"`, `max_duration_minutes == 16`, broadcast (source `visions-of-the-past`). |
| `test_use_vp_area_mode` | Area mode → `mode == "area"`. |
| `test_use_vp_default_mode` | Missing mode → defaults to "object". |
| `test_use_vp_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_vp_level_gate` | Knowledge at Lv 16 → 409. |
| `test_use_vp_out_of_uses` | Back-to-back → 409 `no_uses_left`. |

### `test_master_of_nature.py`
v2.99.302 — Nature Domain Cleric (PHB p.62) Master of Nature Lv 17 (H.1 deeper). Bonus action to verbally command beasts/plants charmed by your Charm Animals and Plants CD. Costs bonus chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_mon_happy_lv17` | Lv 17 Tavik → 200, broadcast (source `master-of-nature`). |
| `test_use_mon_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_mon_level_gate` | Nature at Lv 16 → 409. |

### `test_expansive_bond.py`
v2.99.303 — Peace Domain Cleric (TCE p.39) Expansive Bond Lv 17 (H.1 deeper — CLOSES the H.1 Lv 17 batch). Emboldening Bond now works within 60 ft between bonded creatures (was 30); d4 bonus becomes d6. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_eb_happy_lv17` | Lv 17 Tavik → `bond_radius_ft == 60`, `bonus_die == "d6"`, broadcast (source `expansive-bond`). |
| `test_use_eb_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_eb_level_gate` | Peace at Lv 16 → 409. |

### `test_arcane_mastery.py`
v2.99.304 — Arcana Domain Cleric (SCAG p.125) Arcane Mastery Lv 17 (H.1 deeper extension to 12/13 domains). Add 4 spells (one each of Lv 6/7/8/9) from any class as domain spells — always prepared, count as cleric spells. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_am_happy_lv17` | Lv 17 Tavik → `added_spell_count == 4`, `added_spell_levels == [6, 7, 8, 9]`, `source_class == "any"`, broadcast (source `arcane-mastery`). |
| `test_use_am_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_am_level_gate` | Arcana at Lv 16 → 409. |

### `test_orders_wrath.py`
v2.99.305 — Order Domain Cleric (TCE p.40) Order's Wrath Lv 17 (H.1 deeper — CLOSES H.1 Lv 17 FULL BATCH 13/13). When you Divine Strike, curse target until start of next turn; next ally-hit triggers 2d8 psychic and ends curse. Once per turn. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ow_happy_lv17` | Lv 17 Tavik → `psychic_damage_expression == "2d8"`, `expires_on == "next_turn_start"`, broadcast (source `orders-wrath`). |
| `test_use_ow_with_target` | Optional `target_combatant_id` passed through in response. |
| `test_use_ow_wrong_subclass` | Default Tavik (Life Domain) → 409. |
| `test_use_ow_level_gate` | Order at Lv 16 → 409. |

### `test_assassinate.py`
v2.99.306 — Assassin Rogue (PHB p.97) Assassinate Lv 3+ (E.3 Rogue subclass batch opener — pivoted after Thief Fast Hands was found already wired in v2.99.224). Advantage vs creatures that haven't taken a turn; auto-crit vs surprised. No chip — passive declaration. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ass_happy_lv7` | PATCH Pip → Assassin Lv 7 → `advantage_vs_pre_turn == True`, `auto_crit_vs_surprised == True`, broadcast (source `assassinate`). |
| `test_use_ass_wrong_subclass` | Default Pip (Thief) → 409. |
| `test_use_ass_level_gate` | Assassin at Lv 2 → 409. |

### `test_fancy_footwork.py`
v2.99.307 — Swashbuckler Rogue (XGE p.47) Fancy Footwork Lv 3+ (E.3 Rogue batch). On a melee attack against a creature, that creature can't make OAs against you for the rest of your turn. No chip — passive on melee attack. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ff_happy_lv7` | PATCH Pip → Swashbuckler Lv 7 → `oa_suppressed_until == "end_of_turn"`, broadcast (source `fancy-footwork`). |
| `test_use_ff_with_target` | Optional `target_combatant_id` passes through. |
| `test_use_ff_wrong_subclass` | Default Pip (Thief) → 409. |
| `test_use_ff_level_gate` | Swashbuckler at Lv 2 → 409. |

### `test_master_of_tactics.py`
v2.99.308 — Mastermind Rogue (XGE p.46) Master of Tactics Lv 3+ (E.3 Rogue batch). Bonus action Help; when helping an ally attack, target can be within 30 ft of you (not 5 ft) if it can see/hear you. Costs bonus chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_mt_happy_lv7` | PATCH Pip → Mastermind Lv 7 → `help_action_economy == "bonus"`, `help_target_range_ft == 30`, broadcast (source `master-of-tactics`). |
| `test_use_mt_wrong_subclass` | Default Pip (Thief) → 409. |
| `test_use_mt_level_gate` | Mastermind at Lv 2 → 409. |

### `test_skirmisher.py`
v2.99.309 — Scout Rogue (XGE p.46) Skirmisher Lv 3+ (E.3 Rogue batch). Reaction to move up to half speed when enemy ends turn within 5 ft; no OA. Costs reaction chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_sk_happy_lv7` | PATCH Pip → Scout Lv 7 (halfling speed 25) → `bonus_move_ft == 12`, `no_oa == True`, broadcast (source `skirmisher`). |
| `test_use_sk_wrong_subclass` | Default Pip (Thief) → 409. |
| `test_use_sk_level_gate` | Scout at Lv 2 → 409. |

### `test_insightful_fighting.py`
v2.99.310 — Inquisitive Rogue (XGE p.45) Insightful Fighting Lv 3+ (E.3 Rogue batch). Bonus action Wis (Insight) vs target Cha (Deception). On win, Sneak Attack without advantage (still blocked by disadvantage) for 1 min or until used vs different target. Costs bonus chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_if_happy_lv7` | PATCH Pip → Inquisitive Lv 7 → `duration_minutes == 1`, broadcast (source `insightful-fighting`). |
| `test_use_if_with_target` | Optional `target_combatant_id` passes through. |
| `test_use_if_wrong_subclass` | Default Pip (Thief) → 409. |
| `test_use_if_level_gate` | Inquisitive at Lv 2 → 409. |

### `test_psychic_blades.py`
v2.99.311 — Soulknife Rogue (TCE p.62) Psychic Blades Lv 3+ (E.3 Rogue batch). Bonus action to manifest Psychic Blades in each free hand. Simple melee + thrown (60/120 ft), 1d6 psychic, finesse + light. Counts as monk weapon. Usable with Sneak Attack. Costs bonus chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_pb_happy_lv7` | PATCH Pip → Soulknife Lv 7 → `damage_expression == "1d6"`, `damage_type == "psychic"`, `thrown_range_ft == [60, 120]`, properties include finesse/light/thrown, `counts_as_monk_weapon == True`, broadcast (source `psychic-blades`). |
| `test_use_pb_wrong_subclass` | Default Pip (Thief) → 409. |
| `test_use_pb_level_gate` | Soulknife at Lv 2 → 409. |

### `test_whispers_of_the_dead.py`
v2.99.312 — Phantom Rogue (TCE p.61) Whispers of the Dead Lv 3+ (E.3 Rogue batch — CLOSES the batch 8/8). On each rest, choose one skill or tool proficiency; you have that prof until next rest. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_wd_happy_lv7` | PATCH Pip → Phantom Lv 7 with explicit "Arcana" prof → `proficiency_name == "Arcana"`, `expires_on == "next_rest"`, broadcast (source `whispers-of-the-dead`). |
| `test_use_wd_default_prof` | Missing `proficiency_name` → fallback string with "unspecified". |
| `test_use_wd_wrong_subclass` | Default Pip (Thief) → 409. |
| `test_use_wd_level_gate` | Phantom at Lv 2 → 409. |

### `test_bonus_cantrip.py`
v2.99.313 — Land Druid (PHB p.68) Bonus Cantrip Lv 2+ (E.4 Druid subclass batch opener). +1 druid cantrip of your choice. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_bc_happy_lv5` | PATCH Mira → Land Lv 5 with "Shillelagh" → `cantrip_name == "Shillelagh"`, `added_cantrip_count == 1`, broadcast (source `bonus-cantrip`). |
| `test_use_bc_default_name` | Missing `cantrip_name` → fallback string with "unspecified". |
| `test_use_bc_wrong_subclass` | Default Mira (Moon) → 409. |
| `test_use_bc_level_gate` | Land at Lv 1 → 409. |

### `test_natural_recovery.py`
v2.99.314 — Land Druid (PHB p.68) Natural Recovery Lv 2+ (E.4 Druid batch). During short rest, recover spell slots totaling ceil(druid level / 2) levels (max Lv 5). Once per long rest. Auto-bootstraps `natural-recovery` resource. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_nr_happy_lv5` | PATCH Mira → Land Lv 5 → `recoverable_level_pool == 3`, `max_slot_level == 5`, broadcast (source `natural-recovery`). |
| `test_use_nr_wrong_subclass` | Default Mira (Moon) → 409. |
| `test_use_nr_level_gate` | Land at Lv 1 → 409. |
| `test_use_nr_out_of_uses` | Back-to-back → 409 `no_uses_left`. |
| `test_use_nr_long_rest_refills` | Use → long rest → use again → 200. |

### `test_spirit_totem.py`
v2.99.315 — Shepherd Druid (XGE p.24) Spirit Totem Lv 2+ (E.4 Druid batch). Bonus action to summon Bear/Hawk/Unicorn spirit at point within 60 ft. 30-ft aura, 1 min. Bear = 5+druid_lv temp HP to allies in aura; Hawk = reaction ally-attack advantage; Unicorn = heal-spell rider HP = druid level. Once per short or long rest. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_st_happy_lv5_bear` | PATCH Mira → Shepherd Lv 5 default Bear → `bear_temp_hp == 10`, `aura_radius_ft == 30`, broadcast (source `spirit-totem`). |
| `test_use_st_hawk` | spirit="hawk" passes through. |
| `test_use_st_unicorn` | spirit="unicorn" → `unicorn_heal_bonus == 5`. |
| `test_use_st_wrong_subclass` | Default Mira (Moon) → 409. |
| `test_use_st_level_gate` | Shepherd at Lv 1 → 409. |
| `test_use_st_out_of_uses` | Back-to-back → 409 `no_uses_left`. |

### `test_star_map.py`
v2.99.316 — Stars Druid (TCE p.37) Star Map Lv 2+ (E.4 Druid batch). Star chart focus + Guidance & Guiding Bolt always prepared. Guiding Bolt castable WIS_mod times (min 1) per long rest without slot. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_sm_happy_lv5` | PATCH Mira → Stars Lv 5 (WIS 17 mod 3) → `free_guiding_bolt_uses == 3`, always_prepared includes Guidance + Guiding Bolt, broadcast (source `star-map`). |
| `test_use_sm_wrong_subclass` | Default Mira (Moon) → 409. |
| `test_use_sm_level_gate` | Stars at Lv 1 → 409. |

### `test_halo_of_spores.py`
v2.99.317 — Spores Druid (TCE p.36) Halo of Spores Lv 2+ (E.4 Druid batch). Reaction when creature moves into or starts turn within 10 ft → necrotic damage on failed CON save. Die scales 1d4/1d6/1d8/1d10 at Lv 2/6/10/14. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_hs_happy_lv5` | PATCH Mira → Spores Lv 5 (WIS 17 prof 3) → `damage_expression == "1d4"`, `save_dc == 14`, `save_ability == "CON"`, `aura_radius_ft == 10`, broadcast (source `halo-of-spores`). |
| `test_use_hs_lv6` | Lv 6 → `damage_expression == "1d6"`. |
| `test_use_hs_lv14` | Lv 14 → `damage_expression == "1d10"`. |
| `test_use_hs_wrong_subclass` | Default Mira (Moon) → 409. |
| `test_use_hs_level_gate` | Spores at Lv 1 → 409. |

### `test_summon_wildfire_spirit.py`
v2.99.318 — Wildfire Druid (TCE p.38) Summon Wildfire Spirit Lv 2+ (E.4 Druid batch). Action + Wild Shape (default) or Lv 2+ spell slot to summon Wildfire Spirit for 1 hour. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ws_happy_lv5_default` | PATCH Mira → Wildfire Lv 5 default → `resource_used == "wild-shape"`, `duration_minutes == 60`, broadcast (source `summon-wildfire-spirit`). |
| `test_use_ws_slot_variant` | slot_level 3 → `resource_used == "spell-slot"`, `slot_level == 3`. |
| `test_use_ws_wrong_subclass` | Default Mira (Moon) → 409. |
| `test_use_ws_level_gate` | Wildfire at Lv 1 → 409. |

### `test_balm_of_the_summer_court.py`
v2.99.319 — Dreams Druid (XGE p.23) Balm of the Summer Court Lv 2+ (E.4 Druid batch). Pool of d6 fey energy = druid_lv dice. Bonus action: spend up to half-druid-lv dice → ally within 120 ft heals total + 1 temp HP per die. Pool refills on long rest. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_bsc_happy_lv5_one_die` | PATCH Mira → Dreams Lv 5 default 1 die → `heal_amount` in [1, 6], `temp_hp == 1`, `max_range_ft == 120`, `dice_remaining == 4`, broadcast (source `balm-of-the-summer-court`). |
| `test_use_bsc_two_dice` | dice_spent 2 → `heal_amount` in [2, 12], `temp_hp == 2`. |
| `test_use_bsc_dice_clamp` | dice_spent 99 → clamped to half-druid-level 2. |
| `test_use_bsc_wrong_subclass` | Default Mira (Moon) → 409. |
| `test_use_bsc_level_gate` | Dreams at Lv 1 → 409. |

### `test_combat_inspiration.py`
v2.99.320 — Valor College Bard (PHB p.55) Combat Inspiration Lv 3+ (F.1 Bard subclass batch opener — pivoted after Lore Cutting Words was found already wired). A creature with a BI die from you can roll it and add to weapon damage OR (reaction) AC. Die scales d6/d8/d10/d12 at Lv 3/5/10/15. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ci_happy_lv6` | PATCH Lyra → Valor Lv 6 default damage → `die_size == 8`, `die_expression == "1d8"`, broadcast (source `combat-inspiration`). |
| `test_use_ci_mode_ac` | Mode "ac" passes through. |
| `test_use_ci_default_mode` | Missing mode → "damage". |
| `test_use_ci_wrong_subclass` | Default Lyra (Lore) → 409. |
| `test_use_ci_level_gate` | Valor at Lv 2 → 409. |

### `test_mantle_of_inspiration.py`
v2.99.321 — Glamour College Bard (XGE p.16) Mantle of Inspiration Lv 3+ (F.1 Bard batch). Bonus action + 1 BI use → up to CHA-mod (min 1) allies within 60 ft each gain 5+bard_lv temp HP + immediate reaction-move at full speed without provoking OAs. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_mi_happy_lv6` | PATCH Lyra → Glamour Lv 6 (CHA 17 mod 3) → `max_targets == 3`, `temp_hp_per_target == 11`, `max_range_ft == 60`, `free_move_no_oa == True`, broadcast (source `mantle-of-inspiration`). |
| `test_use_mi_wrong_subclass` | Default Lyra (Lore) → 409. |
| `test_use_mi_level_gate` | Glamour at Lv 2 → 409. |

### `test_whispers_psychic_blades.py`
v2.99.322 — Whispers College Bard (XGE p.17) Psychic Blades Lv 3+ (F.1 Bard batch). On weapon hit, expend 1 BI use to deal extra psychic damage. Dice scale 2d6/3d6/5d6/8d6 at Lv 3/5/10/15. Endpoint slug `/use_whispers_psychic_blades` to avoid collision with Soulknife Rogue's `/use_psychic_blades` (v2.99.311). v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_wpb_happy_lv6` | PATCH Lyra → Whispers Lv 6 → `damage_expression == "3d6"`, `damage_type == "psychic"`, `consumed_bardic_inspiration == True`, broadcast (source `whispers-psychic-blades`). |
| `test_use_wpb_lv10` | Lv 10 → `damage_expression == "5d6"`. |
| `test_use_wpb_lv15` | Lv 15 → `damage_expression == "8d6"`. |
| `test_use_wpb_wrong_subclass` | Default Lyra (Lore) → 409. |
| `test_use_wpb_level_gate` | Whispers at Lv 2 → 409. |

### `test_blade_flourish.py`
v2.99.323 — Swords College Bard (XGE p.16) Blade Flourish Lv 3+ (F.1 Bard batch). On Attack action walking speed +10 ft until end of turn; on weapon hit, expend 1 BI use → one Flourish (Defensive / Slashing / Mobile). Once per turn. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_bf_happy_lv6_defensive` | PATCH Lyra → Swords Lv 6 default Defensive → `flourish == "defensive"`, `walking_speed_bonus_ft == 10`, `consumed_bardic_inspiration == True`, broadcast (source `blade-flourish`). |
| `test_use_bf_slashing` | flourish="slashing" passes through. |
| `test_use_bf_mobile` | flourish="mobile" passes through. |
| `test_use_bf_wrong_subclass` | Default Lyra (Lore) → 409. |
| `test_use_bf_level_gate` | Swords at Lv 2 → 409. |

### `test_silver_tongue.py`
v2.99.324 — Eloquence College Bard (TCE p.28) Silver Tongue Lv 3+ (F.1 Bard batch). Cha (Persuasion) and Cha (Deception) checks treat a d20 roll of 9 or lower as a 10. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_st_happy_lv6` | PATCH Lyra → Eloquence Lv 6 → `minimum_d20_value == 10`, applies_to includes persuasion + deception, `ability == "CHA"`, broadcast (source `silver-tongue`). |
| `test_use_st_wrong_subclass` | Default Lyra (Lore) → 409. |
| `test_use_st_level_gate` | Eloquence at Lv 2 → 409. |

### `test_tales_from_beyond.py`
v2.99.325 — Spirits College Bard (TCE p.30) Tales from Beyond Lv 3+ (F.1 Bard batch). Bonus action to roll 1d6 on Spirit Tales table; action to apply tale (6 tales: Clever Animal/Duelist/Beloved Friends/Brute/Tragic Romance/Traveler). `force_tale` body param (1-6) is a TEST_MODE escape hatch. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_tb_happy_lv6` | PATCH Lyra → Spirits Lv 6 → `tale_roll` in [1,6], `tale_name` non-empty, broadcast (source `tales-from-beyond`). |
| `test_use_tb_force_tale_4_brute` | `force_tale=4` → roll 4, name contains "Brute". |
| `test_use_tb_force_tale_2_duelist` | `force_tale=2` → roll 2, name contains "Duelist". |
| `test_use_tb_wrong_subclass` | Default Lyra (Lore) → 409. |
| `test_use_tb_level_gate` | Spirits at Lv 2 → 409. |

### `test_mote_of_potential.py`
v2.99.326 — Creation College Bard (TCE p.31) Mote of Potential Lv 3+ (F.1 Bard batch — CLOSES the batch 8/8). When a creature uses a BI die from you, the Mote attaches + triggers an effect by mode: check (re-roll BI die, add to check), attack (BI die in force damage to nearby creature), save (temp HP = BI roll + CHA mod). v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_mp_happy_lv6_check` | PATCH Lyra → Creation Lv 6 (CHA 17 mod 3) default check → `die_size == 8`, `die_expression == "1d8"`, `cha_mod == 3`, broadcast (source `mote-of-potential`). |
| `test_use_mp_mode_attack` | mode="attack" passes through. |
| `test_use_mp_mode_save` | mode="save" passes through. |
| `test_use_mp_wrong_subclass` | Default Lyra (Lore) → 409. |
| `test_use_mp_level_gate` | Creation at Lv 2 → 409. |

### `test_arcane_ward.py`
v2.99.327 — Abjuration School Wizard (PHB p.115) Arcane Ward Lv 2+ (G.1 Wizard subclass batch opener). On abjuration cast Lv 1+, create magical ward HP = 2 × wizard_lv + INT mod. Refills 2 × spell-level HP per abjuration cast. Lasts until long rest. Once-per-long-rest creation. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_aw_happy_lv7` | PATCH Thalindra → Abjuration Lv 7 (INT 16 mod 3) → `ward_hp_max == 17`, broadcast (source `arcane-ward`). |
| `test_use_aw_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_aw_level_gate` | Abjuration at Lv 1 → 409. |

### `test_third_eye.py`
v2.99.328 — Divination School Wizard (PHB p.116) The Third Eye Lv 10+ (G.1 Wizard batch — pivot after Portent was found already wired in v2.99.219). Action to gain one of 4 magical senses until dismissed or short/long rest: Darkvision / Ethereal Sight / Greater Comprehension / See Invisibility. Costs action chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_te_happy_lv10_darkvision` | PATCH Thalindra → Divination Lv 10 default → `sense == "darkvision"`, broadcast (source `third-eye`). |
| `test_use_te_see_invisibility` | sense="see-invisibility" passes through. |
| `test_use_te_ethereal_sight` | sense="ethereal-sight" passes through. |
| `test_use_te_greater_comprehension` | sense="greater-comprehension" passes through. |
| `test_use_te_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_te_level_gate` | Divination at Lv 9 → 409. |

### `test_minor_conjuration.py`
v2.99.329 — Conjuration School Wizard (PHB p.116) Minor Conjuration Lv 2+ (G.1 Wizard batch). Action to conjure a nonmagical inanimate object ≤3 ft any dim, ≤10 lb, in hand or unoccupied space within 10 ft. Persists 1 hr or until re-conjured/damaged. Costs action chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_mc_happy_lv7` | PATCH Thalindra → Conjuration Lv 7 with "torch" → `object_name == "torch"`, `duration_minutes == 60`, `max_dim_ft == 3`, `max_weight_lb == 10`, `dim_light_radius_ft == 5`, broadcast (source `minor-conjuration`). |
| `test_use_mc_default_name` | Missing `object_name` → fallback string with "unspecified". |
| `test_use_mc_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_mc_level_gate` | Conjuration at Lv 1 → 409. |

### `test_hypnotic_gaze.py`
v2.99.330 — Enchantment School Wizard (PHB p.117) Hypnotic Gaze Lv 2+ (G.1 Wizard batch). Action, target within 5 ft → WIS save DC 8 + prof + INT mod; on fail, charmed + incapacitated + speed 0 until end of next turn. Extendable. Costs action chip. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_hg_happy_lv7` | PATCH Thalindra → Enchantment Lv 7 (prof 3 INT 16 mod 3) → `save_dc == 14`, `save_ability == "WIS"`, `range_ft == 5`, broadcast (source `hypnotic-gaze`). |
| `test_use_hg_with_target` | `target_combatant_id` passes through. |
| `test_use_hg_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_hg_level_gate` | Enchantment at Lv 1 → 409. |

### `test_improved_minor_illusion.py`
v2.99.331 — Illusion School Wizard (PHB p.118) Improved Minor Illusion Lv 2+ (G.1 Wizard batch). Free Minor Illusion cantrip + dual-mode sound + image in single cast. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_imi_happy_lv7` | PATCH Thalindra → Illusion Lv 7 → `dual_mode == True`, free_cantrip mentions Minor Illusion, broadcast (source `improved-minor-illusion`). |
| `test_use_imi_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_imi_level_gate` | Illusion at Lv 1 → 409. |

### `test_grim_harvest.py`
v2.99.332 — Necromancy School Wizard (PHB p.118) Grim Harvest Lv 2+ (G.1 Wizard batch). Once per turn, kill with Lv 1+ spell → regain HP = 2 × spell level (3 × if necromancy). v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_gh_happy_lv7_lv3_spell` | PATCH Thalindra → Necromancy Lv 7, spell_level 3 non-necro → `heal_amount == 6`, broadcast (source `grim-harvest`). |
| `test_use_gh_necromancy_spell` | spell_level 3 + is_necromancy=true → `heal_amount == 9`. |
| `test_use_gh_default_spell_level` | Missing spell_level → default 1 → `heal_amount == 2`. |
| `test_use_gh_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_gh_level_gate` | Necromancy at Lv 1 → 409. |

### `test_minor_alchemy.py`
v2.99.333 — Transmutation School Wizard (PHB p.119) Minor Alchemy Lv 2+ (G.1 Wizard batch). 10 min / cubic foot transmute one nonmagical object (wood/stone/iron/copper/silver) into another. Reverts after 1 hour or on losing concentration. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ma_happy_lv7_default` | PATCH Thalindra → Transmutation Lv 7 default → wood → stone, `time_per_cubic_foot_minutes == 10`, `duration_minutes == 60`, `concentration == True`, broadcast (source `minor-alchemy`). |
| `test_use_ma_iron_to_copper` | source/target=iron/copper passes through. |
| `test_use_ma_invalid_material_clamps` | "gold"/"diamond" → clamped to wood/stone defaults. |
| `test_use_ma_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_ma_level_gate` | Transmutation at Lv 1 → 409. |

### `test_bladesong.py`
v2.99.334 — Bladesinging Wizard (TCE p.74) Bladesong Lv 2+ (G.1 Wizard batch — pivot after Sculpt Spells found already wired in v2.99.225). Bonus action 1 min: +CHA mod AC, +10 ft speed, advantage on Acrobatics, +INT mod concentration/weapon damage. Twice per short or long rest. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_bs_happy_lv7` | PATCH Thalindra → Bladesinging Lv 7 (CHA 10 mod 0, INT 16 mod 3) → `ac_bonus == 1` (max(1, CHA)), `speed_bonus_ft == 10`, `concentration_bonus == 3`, `weapon_damage_bonus_per_turn == 3`, `duration_minutes == 1`, `uses_remaining == 1`, broadcast (source `bladesong`). |
| `test_use_bs_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_bs_level_gate` | Bladesinging at Lv 1 → 409. |
| `test_use_bs_two_uses_then_out` | 1st → uses_remaining 1; 2nd → 0; 3rd → 409 `no_uses_left`. |

### `test_wizardly_quill.py`
v2.99.335 — Order of Scribes Wizard (TCE p.75) Wizardly Quill Lv 2+ (G.1 Wizard batch). Bonus action to conjure magical quill — no ink, any language/color, 4× speed, self-erase. Vanishes after long rest. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_wq_happy_lv7` | PATCH Thalindra → Scribes Lv 7 → `speed_multiplier == 4`, all property flags True, `duration == "until_long_rest"`, broadcast (source `wizardly-quill`). |
| `test_use_wq_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_wq_level_gate` | Scribes at Lv 1 → 409. |

### `test_arcane_deflection.py`
v2.99.336 — War Magic Wizard (XGE p.59) Arcane Deflection Lv 2+ (G.1 Wizard batch). Reaction on hit by attack or failed save → +2 AC vs the triggering attack OR +4 to the failed save. Can't cast leveled spells (cantrips only) until end of next turn. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ad_happy_lv7_ac` | PATCH Thalindra → War Magic Lv 7 → `mode == "ac"`, `bonus == 2`, `leveled_spell_lockout == True`, `wizard_level == 7`, broadcast (source `arcane-deflection`). |
| `test_use_ad_save_mode` | `mode="save"` → `bonus == 4`. |
| `test_use_ad_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_ad_level_gate` | War Magic at Lv 1 → 409. |

### `test_chronal_shift.py`
v2.99.337 — Chronurgy Magic Wizard (EGtW p.184) Chronal Shift Lv 2+ (G.1 Wizard batch). Reaction: self or a seen creature within 30 ft making an attack roll, check, or save must reroll and use the new roll. Twice per long rest. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_cs_happy_lv7` | PATCH Thalindra → Chronurgy Lv 7 → `uses_remaining == 1`, `uses_max == 2`, `wizard_level == 7`, broadcast (source `chronal-shift`). |
| `test_use_cs_two_uses_then_out` | 1st → 1; 2nd → 0; 3rd → 409 `no_uses_left`. |
| `test_use_cs_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_cs_level_gate` | Chronurgy at Lv 1 → 409. |

### `test_restore_balance.py`
v2.99.342 — Clockwork Soul Sorcerer (TCE p.69) Restore Balance Lv 1+ (G.2 Sorcerer batch). Reaction: a seen creature within 60 ft about to roll a d20 with adv/disadv rolls without it. Uses = proficiency bonus per long rest (server-tracked on `sheet.restore_balance_uses`). v2.122.0 — the cancel is now REAL: clears the target's active `roll_state` + broadcasts `character_roll_state(value=None)`.

| Test | What it asserts |
|------|-----------------|
| `test_use_rb_happy_lv5` | PATCH Zara → Clockwork Soul → `range_ft == 60`, `cancels_adv_disadv == True`, uses 3 → 2, `sorcerer_level == 5`, broadcast (source `restore-balance`). |
| `test_use_rb_out_of_uses` | `restore_balance_uses == 0` → 409 `out_of_uses`. |
| `test_use_rb_wrong_subclass` | Default Zara (Draconic Bloodline) → 409. |
| `test_use_rb_wrong_class` | Caelan (Paladin) → 409. |
| `test_rb_cancels_target_advantage` | v2.122.0 — set Krieger to `advantage`, Zara Restore-Balances him with `target_character_id` → `cancelled=True`, `previous_roll_state="advantage"`, `character_roll_state(value=None)` broadcast, `feature_used(cancelled=True)`. Restores Krieger's roll_state in finally. |
| `test_rb_no_op_when_target_neutral` | v2.122.0 — target with no active adv/disadv → 200 but `cancelled=False`, `previous_roll_state=None` (the use is still spent). |
| `test_rb_rest_refill_long_only` | Exhausted → 409; SHORT rest does NOT refill; LONG rest refills to PB. |

### `test_adjust_density.py`
v2.99.338 — Graviturgy Magic Wizard (EGtW p.185) Adjust Density Lv 2+ (G.1 Wizard batch CLOSE 13/13). Action + concentration up to 1 min: double or halve a willing creature's weight. Doubled → -10 ft speed + advantage on STR. Halved → +10 ft speed + disadvantage on STR. v1 announce-only.

| Test | What it asserts |
|------|-----------------|
| `test_use_ad_happy_lv7_double` | PATCH Thalindra → Graviturgy Lv 7 → `mode == "double"`, `speed_delta == -10`, `str_effect == "advantage"`, `wizard_level == 7`, broadcast (source `adjust-density`). |
| `test_use_ad_halve_mode` | `mode="halve"` → `speed_delta == 10`, `str_effect == "disadvantage"`. |
| `test_use_ad_with_target` | `target_character_id` → response carries `target_character_name == "Sir Caelan Lightbringer"`. |
| `test_use_ad_wrong_subclass` | Default Thalindra (Evocation) → 409. |
| `test_use_ad_level_gate` | Graviturgy at Lv 1 → 409. |

### `test_conquering_presence.py`
v2.99.247 — Oath of Conquest (Paladin subclass, XGE p.37) Conquering Presence CD (Phase H.2 third oath). Caelan PATCH'd to Conquest + CD 1/1 + 2 Bandits in battle. DC 14.

| Test | What it asserts |
|------|-----------------|
| `test_use_cp_happy` | Conquest Caelan targets 2 bandits → `save_dc == 14`, `uses_remaining == 0`, list of 2 ids returned, broadcast (source `conquering-presence`). |
| `test_use_cp_empty_target_list` | Empty target list → 400. |
| `test_use_cp_unknown_target` | One unknown target in list → 404 `target_not_in_battle`. |
| `test_use_cp_out_of_cd` | `channel-divinity.current = 0` → 409 `out_of_uses`. |
| `test_use_cp_wrong_subclass` | Default Caelan (Devotion) → 409 `wrong_subclass_or_level`. |

### `test_abjure_enemy.py`
v2.99.274 — Vengeance Paladin (PHB p.87) Abjure Enemy CD (H.2 depth). Sibling CD to Vow of Enmity (v2.99.246). Single target Wis save DC 8 + prof + CHA; fail Frightened + speed 0 or success speed halved (both end on damage).

| Test | What it asserts |
|------|-----------------|
| `test_use_ae_happy` | Vengeance Caelan adjures Bandit → `save_dc == 14`, `uses_remaining == 0`, broadcast. |
| `test_use_ae_target_not_in_battle` | Unknown target → 404. |
| `test_use_ae_out_of_cd` | CD 0 → 409. |
| `test_use_ae_wrong_subclass` | Default Caelan (Devotion) → 409. |

### `test_vow_of_enmity.py`
v2.99.246 — Oath of Vengeance (Paladin subclass, PHB p.87) Vow of Enmity bonus-action CD (Phase H.2 second oath). Caelan PATCH'd to Vengeance + CD 1/1 + Bandit in battle.

| Test | What it asserts |
|------|-----------------|
| `test_use_voe_happy` | Vengeance Caelan vs Bandit → CD 1 → 0, `buff_installed: True`, `target_name == "Bandit Alpha"`, broadcast (source `vow-of-enmity`). |
| `test_use_voe_target_not_in_battle` | Unknown target_combatant_id → 404 `target_not_in_battle`. |
| `test_use_voe_out_of_cd` | `channel-divinity.current = 0` → 409 `out_of_uses`. |
| `test_use_voe_wrong_subclass` | Default Caelan (Devotion) → 409 `wrong_subclass_or_level`. |

### `test_turn_the_faithless.py`
v2.99.272 — Ancients Paladin (PHB p.87) Turn the Faithless CD (H.2 Phase 2). Sibling CD to Nature's Wrath (v2.99.245). 30-ft AOE Wis save vs fey/fiend or Turned 1 minute.

| Test | What it asserts |
|------|-----------------|
| `test_use_ttf_happy` | Ancients Caelan vs Imp + Sprite → `save_dc == 14`, `uses_remaining == 0`, broadcast (source `turn-the-faithless`). |
| `test_use_ttf_empty_target_list` | Empty list → 400. |
| `test_use_ttf_unknown_target` | One unknown target → 404. |
| `test_use_ttf_out_of_cd` | CD 0 → 409 `out_of_uses`. |
| `test_use_ttf_wrong_subclass` | Default Caelan (Devotion) → 409. |

### `test_natures_wrath.py`
v2.99.245 — Oath of the Ancients (Paladin subclass, PHB p.86) Nature's Wrath Channel Divinity (Phase H.2 Phase 1 of [docs/plans/paladin-oaths.md](../plans/paladin-oaths.md)). Sir Caelan Lightbringer is the demo fixture; tests PATCH his subclass to "Oath of the Ancients" and seed Bandit in battle. Caelan Lv 8 CHA 16: DC = 8 + prof 3 + CHA +3 = 14.

| Test | What it asserts |
|------|-----------------|
| `test_use_nw_str_happy` | Ancients Caelan vs Bandit with `save_ability: "STR"` → `save_dc == 14`, `uses_remaining == 0`, broadcast (source `natures-wrath`). |
| `test_use_nw_dex_mode` | `save_ability: "DEX"` → mirrored in response. |
| `test_use_nw_bad_save_ability` | CON isn't in `{STR, DEX}` → 400. |
| `test_use_nw_out_of_cd` | `channel-divinity.current = 0` → 409 `out_of_uses`. |
| `test_use_nw_wrong_subclass` | Default Caelan (Devotion) → 409 `wrong_subclass_or_level`. |

### `test_voice_of_authority.py`
v2.99.244 — Order Domain Cleric (TCE p.39) Voice of Authority manual trigger (Phase H.1 final domain). Authorizes an ally to take a reaction weapon attack after the cleric casts a Lv 1+ spell. Marks the ALLY's reaction chip.

| Test | What it asserts |
|------|-----------------|
| `test_use_voa_ally_happy` | Tavik authorizes Caelan vs Bandit Alpha → ally reaction marked, broadcast (source `voice-of-authority`). |
| `test_use_voa_self_target` | Targeting self → 409 `self_targeting_not_allowed` (RAW: ally only). |
| `test_use_voa_unknown_ally` | Unknown ally_combatant_id → 404 `ally_not_in_battle`. |
| `test_use_voa_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_emboldening_bond.py`
v2.99.243 — Peace Domain Cleric (TCE p.40) Emboldening Bond multi-target buff (Phase H.1 tenth domain). Up to prof-bonus creatures get +1d4 to attack/check/save while within 30 ft of one another.

| Test | What it asserts |
|------|-----------------|
| `test_use_eb_two_targets_happy` | Tavik bonds Pip + Caelan → 2 buffs installed, `max_allowed == 3` (prof +3), broadcast. |
| `test_use_eb_too_many_targets` | 4 targets with prof 3 → 409 `too_many_targets`, `max == 3`, `got == 4`. |
| `test_use_eb_unknown_target` | One unknown target in list → 404 `target_not_in_battle`. |
| `test_use_eb_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_vigilant_blessing.py`
v2.99.242 — Twilight Domain Cleric (TCE p.41) Vigilant Blessing action (Phase H.1 ninth domain). Touch-an-ally (or self) buff installer: advantage on next init roll. No daily cap.

| Test | What it asserts |
|------|-----------------|
| `test_use_vb_target_ally` | Tavik blesses Pip → `target_char_id == pip.id`, `is_self == False`, `buff_installed: True`, broadcast (source `vigilant-blessing`). |
| `test_use_vb_target_self` | Tavik targets himself → `is_self: True`, buff installed (RAW allows self). |
| `test_use_vb_target_not_in_battle` | Unknown target_combatant_id → 404 `target_not_in_battle`. |
| `test_use_vb_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_eyes_of_the_grave.py`
v2.99.241 — Grave Domain Cleric (XGE p.19) Eyes of the Grave (Phase H.1 eighth domain). Action to detect undead within 60 ft for 1 round. WIS mod uses per long rest.

| Test | What it asserts |
|------|-----------------|
| `test_use_eotg_happy` | Grave Tavik → `uses_remaining == 2`, broadcast (source `eyes-of-the-grave`). |
| `test_use_eotg_out_of_uses` | `eyes-of-the-grave.current = 0` → 409 `out_of_uses`. |
| `test_use_eotg_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_blessing_of_the_forge.py`
v2.99.240 — Forge Domain Cleric (XGE p.18) Blessing of the Forge (Phase H.1 seventh domain). Long-rest blessing picks 1 non-magical weapon or armor; persists `sheet.blessed_object`.

| Test | What it asserts |
|------|-----------------|
| `test_use_bof_weapon_happy` | Tavik blesses Warhammer (index 0) → `kind: "weapon"`, `slug: "warhammer"`, broadcast (source `blessing-of-the-forge`). |
| `test_use_bof_armor_happy` | Tavik blesses Chain mail (index 2) → `kind: "armor"`. |
| `test_use_bof_shield_rejected` | Shield (index 1, `type: "shield"`) → 400 (RAW only weapon or armor). |
| `test_use_bof_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |
| `test_use_bof_missing_item_index` | No item_index body → 400. |

### `test_acolyte_of_nature.py`
v2.99.239 — Nature Domain Cleric (PHB p.61) Acolyte of Nature one-time picker (Phase H.1 sixth domain). Picks 1 druid cantrip + 1 skill from {Animal Handling, Nature, Survival}.

| Test | What it asserts |
|------|-----------------|
| `test_select_aon_happy` | Tavik picks Druidcraft + Survival → persisted, broadcast (source `acolyte-of-nature`). |
| `test_select_aon_bad_skill` | Arcana isn't in valid set → 400. |
| `test_select_aon_missing_cantrip` | Empty cantrip → 400. |
| `test_select_aon_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_blessings_of_knowledge.py`
v2.99.238 — Knowledge Domain Cleric (PHB p.59) Blessings of Knowledge one-time picker (Phase H.1 fifth domain). Picks 2 skills from {Arcana, History, Nature, Religion} + 2 languages.

| Test | What it asserts |
|------|-----------------|
| `test_select_bok_happy` | Tavik picks Arcana + Religion + Celestial + Draconic → 200, persisted, broadcast (source `blessings-of-knowledge`). |
| `test_select_bok_bad_skill` | Skill not in PHB list (Athletics) → 400. |
| `test_select_bok_wrong_count` | 1 skill instead of 2 → 400. |
| `test_select_bok_duplicate_skills` | Arcana + Arcana → 400. |
| `test_select_bok_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_blessing_of_the_trickster.py`
v2.99.237 — Trickery Domain Cleric (PHB p.62) Blessing of the Trickster (Phase H.1 fourth domain). Touch-an-ally buff installer (no daily cap RAW). Brother Tavik Stonebrow is the fixture; tests PATCH his subclass to "Trickery Domain" and seed Tavik + Pip in a battle.

| Test | What it asserts |
|------|-----------------|
| `test_use_botrickster_happy` | Tavik blesses Pip → `target_char_id == pip.id`, `buff_installed: True`, broadcast (source `blessing-of-the-trickster`). |
| `test_use_botrickster_self_target` | Target is Tavik himself → 409 `self_targeting_not_allowed`. |
| `test_use_botrickster_target_not_in_battle` | Unknown `target_combatant_id` → 404 `target_not_in_battle`. |
| `test_use_botrickster_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_war_priest.py`
v2.99.236 — War Domain Cleric (PHB p.63) War Priest bonus-action attack (Phase H.1 third domain). Brother Tavik Stonebrow is the demo fixture; tests PATCH his subclass to "War Domain" + seed a `war-priest` resource.

| Test | What it asserts |
|------|-----------------|
| `test_use_war_priest_happy` | War Cleric Tavik → `uses_remaining == 2`, bonus chip marked + broadcast (source `war-priest`). |
| `test_use_war_priest_out_of_uses` | `war-priest.current = 0` → 409 `out_of_uses`. |
| `test_use_war_priest_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_wrath_of_the_storm.py`
v2.99.235 — Tempest Domain Cleric (PHB p.62) Wrath of the Storm reaction (Phase H.1 second domain). Brother Tavik Stonebrow is the demo fixture; tests PATCH his subclass to "Tempest Domain" + seed a `wrath-of-the-storm` resource.

| Test | What it asserts |
|------|-----------------|
| `test_use_wots_lightning_happy` | Lightning damage_type → `damage` in 2..16, `save_dc == 14` (Tavik Lv 8: prof +3 + WIS +3), `uses_remaining == 2` + broadcast. |
| `test_use_wots_thunder` | `damage_type: "thunder"` mirrored in response. |
| `test_use_wots_bad_damage_type` | `damage_type: "fire"` → 400. |
| `test_use_wots_out_of_uses` | `wrath-of-the-storm.current = 0` → 409 `out_of_uses`. |
| `test_use_wots_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |

### `test_potent_spellcasting.py`
v2.99.270 — Light Domain Cleric Lv 8 (PHB p.60) Potent Spellcasting announce (H.1 depth — first Lv 6/8/17 feature for an already-shipped Cleric domain). Tavik Lv 8 WIS 16 → +3 mod.

| Test | What it asserts |
|------|-----------------|
| `test_use_ps_happy` | Light Tavik Lv 8 → `wis_mod == 3`, cantrip_name mirrored, broadcast (source `potent-spellcasting`). |
| `test_use_ps_wrong_subclass` | Default Tavik (Life) → 409 `wrong_subclass_or_level`. |
| `test_use_ps_level_gate` | Light Tavik at Lv 7 → 409. |
| `test_use_ps_knowledge_lv8` | v2.99.271: Knowledge Domain Tavik Lv 8 also works (RAW identical for Light + Knowledge). |
| `test_use_ps_grave_lv8` | v2.99.277: Grave Domain Tavik Lv 8 also works (XGE p.19). |
| `test_use_ps_peace_lv8` | v2.99.277: Peace Domain Tavik Lv 8 also works (TCE p.40). |

### `test_warding_flare.py`
v2.99.234 — Light Domain Cleric (PHB p.60) Warding Flare reaction (Phase H.1 first ship). Brother Tavik Stonebrow is the demo fixture; tests PATCH his subclass to "Light Domain" + seed a `warding-flare` resource with 3 uses (WIS 16 → +3 mod).

| Test | What it asserts |
|------|-----------------|
| `test_use_warding_flare_happy` | Light Cleric Tavik (in battle) → `uses_remaining == 2`, broadcast (source `warding-flare`) carries `attacker_name == "Bandit Alpha"`. |
| `test_use_warding_flare_out_of_uses` | `warding-flare.current = 0` → 409 `out_of_uses`. |
| `test_use_warding_flare_wrong_subclass` | Default Tavik (Life Domain) → 409 `wrong_subclass_or_level`. |
| `test_use_warding_flare_no_resource` | Light Cleric without the `warding-flare` resource entry → 404. |

### `test_eldritch_knight_capstones.py`
v2.99.269 — Eldritch Knight Fighter (PHB p.74) Arcane Charge + Improved War Magic announces (Phase E.2 Phase 4, **closes E.2**). Lv 15 Arcane Charge (teleport 30 ft with Action Surge); Lv 18 Improved War Magic (Lv 1+ spell variant of War Magic).

| Test | What it asserts |
|------|-----------------|
| `test_use_ac_happy_lv15` | Lv 15 EK Garrik → `teleport_max_ft == 30`, broadcast (source `arcane-charge`). |
| `test_use_ac_level_gate` | Lv 14 → 409. |
| `test_use_iwm_happy_lv18` | Lv 18 EK Garrik → broadcast (source `improved-war-magic`), bonus chip marked. |
| `test_use_iwm_level_gate` | Lv 17 → 409. |

### `test_eldritch_strike.py`
v2.99.268 — Eldritch Knight Fighter (PHB p.74) Eldritch Strike buff install (Phase E.2 Phase 3). Lv 10+; on hit, target has disadvantage on next save vs an EK spell before end of next turn.

| Test | What it asserts |
|------|-----------------|
| `test_use_es_happy` | Lv 10 EK Garrik marks Pip → `target_char_id == pip.id`, `buff_installed: True`, broadcast (source `eldritch-strike`). |
| `test_use_es_wrong_subclass` | Default Garrik (Champion) → 409 `wrong_subclass_or_level`. |
| `test_use_es_level_gate` | EK at Lv 9 → 409. |
| `test_use_es_target_not_in_battle` | Unknown target → 404 `target_not_in_battle`. |

### `test_war_magic.py`
v2.99.267 — Eldritch Knight Fighter (PHB p.74) War Magic announce (Phase E.2 Phase 2). Lv 7+; after casting a cantrip with action, make one weapon attack as a bonus action.

| Test | What it asserts |
|------|-----------------|
| `test_use_wm_happy` | Lv 9 Eldritch Knight Garrik → 200, broadcast (source `war-magic`), bonus chip marked. |
| `test_use_wm_wrong_subclass` | Default Garrik (Champion) → 409 `wrong_subclass_or_level`. |
| `test_use_wm_level_gate` | Eldritch Knight at Lv 6 (not 7+) → 409. |

### `test_commanders_strike.py`
v2.99.266 — Battle Master maneuver 16 of 16 — Commander's Strike (PHB p.74). **Closes the 16-maneuver batch.** Bonus action: ally takes free weapon attack as reaction + die added to damage.

| Test | What it asserts |
|------|-----------------|
| `test_use_cs_happy` | Lv 9 Garrik d8 → `extra_damage` 1..8, `ally_name == "Pip"`. |
| `test_use_cs_out_of_dice` | Dice 0 → 409. |
| `test_use_cs_wrong_subclass` | Default Champion → 409. |

### `test_maneuvering_attack.py`
v2.99.265 — Battle Master maneuver 15 of 16 — Maneuvering Attack (PHB p.74). On hit, +die damage; chosen ally can use reaction to move half speed without provoking OAs from the target.

| Test | What it asserts |
|------|-----------------|
| `test_use_ma_happy` | Lv 9 Garrik d8 → `extra_damage` 1..8, `ally_name == "Pip"`, `target_name == "Bandit Alpha"`. |
| `test_use_ma_out_of_dice` | Dice 0 → 409. |
| `test_use_ma_wrong_subclass` | Default Champion → 409. |

### `test_distracting_strike.py`
v2.99.264 — Battle Master maneuver 14 of 16 — Distracting Strike (PHB p.74). On hit, +die damage; allies have advantage on next attack vs target.

| Test | What it asserts |
|------|-----------------|
| `test_use_ds_happy` | Lv 9 Garrik d8 → `extra_damage` 1..8, `target_name` mirrored, dice 4 → 3. |
| `test_use_ds_out_of_dice` | Dice 0 → 409. |
| `test_use_ds_wrong_subclass` | Default Champion → 409. |

### `test_evasive_footwork.py`
v2.99.263 — Battle Master maneuver 13 of 16 — Evasive Footwork (PHB p.74). Movement-tied; +die AC until movement stops.

| Test | What it asserts |
|------|-----------------|
| `test_use_ef_happy` | Lv 9 Garrik d8 → `ac_bonus` 1..8, dice 4 → 3. |
| `test_use_ef_out_of_dice` | Dice 0 → 409. |
| `test_use_ef_wrong_subclass` | Default Champion → 409. |

### `test_riposte.py`
v2.99.262 — Battle Master maneuver 12 of 16 — Riposte (PHB p.74). Reaction when missed by melee: counter-attack + die added to damage on hit.

| Test | What it asserts |
|------|-----------------|
| `test_use_ri_happy` | Lv 9 Garrik d8 → `extra_damage_on_hit` 1..8, dice 4 → 3. |
| `test_use_ri_out_of_dice` | Dice 0 → 409. |
| `test_use_ri_wrong_subclass` | Default Champion → 409. |

### `test_parry.py`
v2.99.261 — Battle Master maneuver 11 of 16 — Parry (PHB p.74). First defensive maneuver: reaction; reduce melee damage by die + DEX mod.

| Test | What it asserts |
|------|-----------------|
| `test_use_pa_happy` | Lv 9 Garrik d8 → `dex_mod == 2`, `die_roll` 1..8, `damage_reduction == die_roll + 2`, dice 4 → 3. |
| `test_use_pa_out_of_dice` | Dice 0 → 409. |
| `test_use_pa_wrong_subclass` | Default Champion → 409. |

### `test_rally.py`
v2.99.260 — Battle Master maneuver 10 of 16 — Rally (PHB p.74). Bonus action: ally gets temp HP = die + CHA mod.

| Test | What it asserts |
|------|-----------------|
| `test_use_ra_happy` | Lv 9 Garrik d8 → `cha_mod == 0` (CHA 10), `die_roll` 1..8, `temp_hp == die_roll`, ally name mirrored, dice 4 → 3. |
| `test_use_ra_out_of_dice` | Dice 0 → 409. |
| `test_use_ra_wrong_subclass` | Default Champion → 409. |

### `test_feinting_attack.py`
v2.99.259 — Battle Master maneuver 9 of 16 — Feinting Attack (PHB p.74). First per-maneuver endpoint to gate on a Phase 4 BONUS chip (bonus action; advantage + damage bump on next attack).

| Test | What it asserts |
|------|-----------------|
| `test_use_fa_happy` | Lv 9 Garrik d8 → `next_attack_advantage: True`, `extra_damage_on_hit` 1..8, `target_name == "Bandit Alpha"`, dice 4 → 3, broadcast. |
| `test_use_fa_out_of_dice` | Dice 0 → 409. |
| `test_use_fa_wrong_subclass` | Default Champion → 409. |

### `test_sweeping_attack.py`
v2.99.258 — Battle Master maneuver 8 of 16 — Sweeping Attack (PHB p.74). Die becomes damage on a *second* target within 5 ft of the original if the same attack roll hits both.

| Test | What it asserts |
|------|-----------------|
| `test_use_sa_happy` | Lv 9 Garrik d8 → `second_target_damage` 1..8, `second_target_name == "Bandit Beta"`, dice 4 → 3. |
| `test_use_sa_out_of_dice` | Dice 0 → 409. |
| `test_use_sa_wrong_subclass` | Default Champion → 409. |

### `test_lunging_attack.py`
v2.99.257 — Battle Master maneuver 7 of 16 — Lunging Attack (PHB p.74). Melee attack only: +5 ft reach + die added to damage on hit. No save.

| Test | What it asserts |
|------|-----------------|
| `test_use_la_happy` | Lv 9 Garrik d8 → `extra_reach_ft == 5`, `extra_damage_on_hit` 1..8, dice 4 → 3, broadcast. |
| `test_use_la_out_of_dice` | Dice 0 → 409. |
| `test_use_la_wrong_subclass` | Default Champion → 409. |

### `test_precision_attack.py`
v2.99.256 — Battle Master maneuver 6 of 16 — Precision Attack (PHB p.74). First non-save maneuver: die adds to ATTACK roll (not damage).

| Test | What it asserts |
|------|-----------------|
| `test_use_pra_happy` | Lv 9 Garrik d8 → `attack_bonus` 1..8, no save fields, dice 4 → 3, broadcast (source `precision-attack`). |
| `test_use_pra_out_of_dice` | Dice 0 → 409. |
| `test_use_pra_wrong_subclass` | Default Champion → 409. |

### `test_goading_attack.py`
v2.99.255 — Battle Master maneuver 5 of 16 — Goading Attack (PHB p.74). Same shape as Menacing; on-fail effect is "disadvantage on attacks vs others than attacker."

| Test | What it asserts |
|------|-----------------|
| `test_use_ga_happy` | Lv 9 Garrik d8 → `extra_damage` 1..8, `save_dc == 16`, `save_ability == "WIS"`, dice 4 → 3, broadcast. |
| `test_use_ga_out_of_dice` | Dice 0 → 409 `out_of_uses`. |
| `test_use_ga_wrong_subclass` | Default Champion → 409. |

### `test_pushing_attack.py`
v2.99.254 — Battle Master maneuver 4 of 16 — Pushing Attack (PHB p.74). Save ability STR; on-fail effect "pushed up to 15 ft."

| Test | What it asserts |
|------|-----------------|
| `test_use_pa_happy` | Lv 9 Garrik (d8) → `extra_damage` 1..8, `save_dc == 16`, `save_ability == "STR"`, `push_max_ft == 15`, dice 4 → 3, broadcast. |
| `test_use_pa_out_of_dice` | `superiority-dice.current = 0` → 409 `out_of_uses`. |
| `test_use_pa_wrong_subclass` | Default Garrik (Champion) → 409. |

### `test_use_thorn_whip.py`
v2.99.435 — Phase 6.3 of `docs/plans/movement-and-summons.md`. Thorn Whip (Druid/Artificer cantrip, PHB p.282): melee spell attack → on a hit, piercing damage (1d6 scaling to 2d6/3d6/4d6) + **pull the target 10 ft toward the caster** via `_force_move(pull=True)`. Third forced-move retrofit and the first to exercise the `pull` path. Caster fixture: Mira Greenleaf (demo Druid Lv 5, WIS caster, +6 to hit).

| Test | What it asserts |
|------|-----------------|
| `test_thorn_whip_pulls_target_on_hit` | Mira (placed above the bandit) loops until she hits; on the hit asserts `pull_applied` True, `pull_distance_ft == 10`, 2d6 piercing applied, and the bandit's NPC token moved −140 px (2 cells / 10 ft toward Mira). A miss applies no damage + moves nothing. NPC token created via `POST /tokens` (linked as `source_token_id`) + torn down. |
| `test_thorn_whip_wrong_class` | Krieger (Barbarian) → 409 `wrong_class`. |
| `test_thorn_whip_missing_target_400` | Missing `target_combatant_id` → 400. |
| `test_thorn_whip_target_not_in_battle_404` | Unknown target combatant → 404. |

### `test_use_thunderwave.py`
v2.99.436 — Phase 6.3 of `docs/plans/movement-and-summons.md`. Thunderwave (Bard/Druid/Sorcerer/Wizard L1, PHB p.282): each creature in the cube makes a CON save vs the caster's spell save DC; a fail takes 2d8 thunder (rolled once for the area) + is **pushed 10 ft away** from the caster via `_force_move`, a success takes half + isn't pushed. First *multi-target* forced-move retrofit. Caster fixture: Lyra Sunstrider (demo Bard, knows Thunderwave, CHA 17 / prof +3 → DC 14).

| Test | What it asserts |
|------|-----------------|
| `test_thunderwave_pushes_failed_targets` | Two bandits flank Lyra (one 10 ft above, one 10 ft below); loop until ≥1 fails its CON save, asserting per-target that a failed save → `pushed` True + token moved ±140 px (10 ft away from Lyra) and a passed save → not pushed + token unmoved. `save_dc == 14`, `any_pushed` set. Two NPC tokens created + torn down. |
| `test_thunderwave_unknown_target_per_result_error` | Unknown combatant id → 200 with a per-result `error: not_in_battle` (not a top-level 404). |
| `test_thunderwave_spell_not_known` | Krieger (Barbarian) → 409 `spell_not_known`. |
| `test_thunderwave_missing_targets_400` | Empty `target_combatant_ids` → 400. |

### `test_summon_companion.py`
v2.99.437 — Phase 7.1 of `docs/plans/movement-and-summons.md`. The summon primitive: `_summon_companion` stands up a summoned companion as a REAL combatant (NPC token + init slot + HP/AC on the combatant dict, no TokenTemplate row) so it reuses the existing damage/HP pipeline; `POST /summon_companion` wraps it and `POST /dismiss_companion` tears it down. `_read_target_ac` now honors a combatant-dict `ac`. Owner fixture: Lyra Sunstrider (demo Bard, knows Thunderwave for the deterministic damage proof).

| Test | What it asserts |
|------|-----------------|
| `test_summon_creates_combatant_and_token` | Lyra summons a Wolf → 200 with `is_summon`, `hp_max == 11`, `ac == 13`, `summoned_by == Lyra`, `source_token_id == token_id`, `initiative == 12`; a `token_add` + `battle_update` broadcast fire; the token (label "Wolf") is on the map. |
| `test_summon_is_real_combatant_takes_damage` | Lyra casts Thunderwave at her own Wolf → the per-target result shows `damage_applied > 0` (≥ half on any save → deterministic), proving the summon flows through `_apply_damage_to_combatant`. |
| `test_dismiss_removes_combatant_and_token` | Dismiss → 200 `removed`, the `token_delete` broadcast fires, the token is gone from the map, and a second dismiss → 404. |
| `test_summon_unknown_companion_400` | Unknown `companion_key` → 400 `unknown_companion`. |
| `test_dismiss_unknown_404` | Dismiss an unknown combatant id → 404. |

### `test_use_spiritual_weapon.py`
v2.99.438 — Phase 7.1 of `docs/plans/movement-and-summons.md`. The first summon retrofit: `/use_spiritual_weapon` (Cleric L2) stands up the floating spectral-weapon combatant via `_summon_companion` (`spiritual-weapon` entry) and, when a `target_combatant_id` is supplied, makes the melee spell attack server-side (1d20 + prof + spellcasting mod vs AC) + applies 1d8 + mod force damage on a hit. Caster fixture: Brother Tavik Stonebrow (demo Cleric Lv 6, WIS 16 / prof +3 → +6 to hit).

| Test | What it asserts |
|------|-----------------|
| `test_spiritual_weapon_summon_only` | No target → `attacked` False; the `spiritual-weapon` summon combatant appears (`is_summon`, 1 HP, `summoned_by` Tavik) with a token + `token_add` broadcast. Dismissed after. |
| `test_spiritual_weapon_attacks_target` | Loop a fresh weapon each cast until Tavik hits a bandit → `damage_type == "force"`, `damage_rolled`/`damage_applied > 0`. Each cast's weapon is dismissed to avoid board accumulation. |
| `test_spiritual_weapon_spell_not_known` | Krieger (Barbarian) → 409 `spell_not_known`. |

### `test_summon_rest_teardown.py`
v2.99.439 — Phase 7.1 of `docs/plans/movement-and-summons.md`. Closes the companion-lifecycle-leak risk: a long rest drops the resting character's summons (`_teardown_summons_for_owner` — combatant + token), a short rest leaves them. Owner fixture: Lyra Sunstrider.

| Test | What it asserts |
|------|-----------------|
| `test_long_rest_drops_summons` | Lyra summons a Wolf, then long-rests → the combatant id is in `dismissed_summons`, the token is deleted from the map, and a follow-up manual dismiss → 404. |
| `test_short_rest_keeps_summons` | After a refill long rest, Lyra summons a Wolf + short-rests → no `dismissed_summons` field and the token is still on the map (summon survives). |

### `test_cast_find_familiar.py`
v2.99.440 — Phase 7.2 of `docs/plans/movement-and-summons.md`. The second summon retrofit: `/cast_find_familiar` (Wizard L1 ritual) stands up the tiny non-combat `familiar` companion in a chosen animal form via `_summon_companion`. Gates on knowing Find Familiar OR being a Wizard / Artificer. Caster fixture: Thalindra Moonwhisper (demo Wizard).

| Test | What it asserts |
|------|-----------------|
| `test_find_familiar_summons_companion` | Thalindra conjures an owl familiar → `is_summon`, `companion_key == "familiar"`, `name == "Familiar (owl)"`, `ac == 11`, 1 HP, `summoned_by` Thalindra; a `token_add` broadcast + the token (matching label) on the map. Dismissed after. |
| `test_find_familiar_cannot_cast` | Krieger (Barbarian) → 409 `cannot_cast`. |

### `test_use_animal_companion.py`
v2.99.441 — Phase 7.2 of `docs/plans/movement-and-summons.md`. The third summon retrofit: `/use_animal_companion` (Beast Master Ranger Lv 3+) stands up the beast companion (HP = max(beast HP, 4 × ranger level), AC = 13 + prof) via `_summon_companion` and, when a `target_combatant_id` is supplied, makes the beast's bite (2d4 + STR-mod piercing on a hit). The demo Ranger (Rowan Quickbow) is a Hunter, so the happy paths PATCH his subclass to Beast Master then restore.

| Test | What it asserts |
|------|-----------------|
| `test_animal_companion_summon_only` | No target → `attacked` False; the beast combatant has `companion_hp == 20` (max(11, 4×5)), `companion_ac == 16` (13 + prof 3), `is_summon`, `companion_key == "beast-companion"`, `summoned_by` Rowan. Dismissed after. |
| `test_animal_companion_bites_target` | Loop a fresh companion each cast until the bite hits a bandit → `damage_type == "piercing"`, `damage_rolled`/`damage_applied > 0`. Each companion dismissed. |
| `test_animal_companion_wrong_subclass` | Default Rowan (Hunter) → 409 `wrong_subclass_or_level`. |

### `test_use_steel_defender.py`
v2.99.442 — Phase 7.2 of `docs/plans/movement-and-summons.md`. The fourth summon retrofit: `/use_steel_defender` (Battle Smith Artificer Lv 3+) stands up the construct companion (HP = 2 + INT mod + 5 × level, AC 15) via `_summon_companion` and, when a `target_combatant_id` is supplied, makes its Force-Empowered Rend (1d8 + prof force on a hit). No demo Artificer, so the happy paths PATCH Thalindra's subclass to Battle Smith then restore (her Lv 5 / INT 16 stand in → defender HP 30).

| Test | What it asserts |
|------|-----------------|
| `test_steel_defender_summon_only` | No target → `attacked` False; the construct has `defender_hp == 30`, `defender_ac == 15`, `is_summon`, `companion_key == "steel-defender"`, `summoned_by` the artificer. Dismissed after. |
| `test_steel_defender_rends_target` | Loop a fresh defender each cast until the Rend hits a bandit → `damage_type == "force"`, `damage_rolled`/`damage_applied > 0`. Each defender dismissed. |
| `test_steel_defender_wrong_subclass` | Default Thalindra (Evocation) → 409 `wrong_subclass_or_level`. |

### `test_cast_conjure_animals.py`
v2.99.443 — Phase 7.2 of `docs/plans/movement-and-summons.md`. The first *multi*-summon: `/cast_conjure_animals` (Druid/Ranger L3) stands up `count` (1–8) wolf combatants on their own grid cells via repeated `_summon_companion` calls. Gates on knowing Conjure Animals OR being a Druid / Ranger. Caster fixture: Mira Greenleaf (demo Druid).

| Test | What it asserts |
|------|-----------------|
| `test_conjure_animals_eight_wolves` | The default → `count == 8`, 8 distinct summon combatants (all `is_summon`, `companion_key == "wolf"`, `summoned_by` Mira) + 8 tokens at x positions spaced 70 px apart from 700. All dismissed after. |
| `test_conjure_animals_count_clamp` | `count=2` → exactly two wolves. |
| `test_conjure_animals_cannot_cast` | Krieger (Barbarian) → 409 `cannot_cast`. |

### `test_cast_gust.py`
v2.99.445 — Phase 6.3 of `docs/plans/movement-and-summons.md`. Gust (Druid/Sorcerer/Wizard cantrip, Tasha's p.106): the target makes a STR save vs the spell save DC or is pushed 5 ft away via `_force_move`. The last forced-mover. Caster fixture: Thalindra Moonwhisper (demo Wizard).

| Test | What it asserts |
|------|-----------------|
| `test_gust_pushes_target_on_failed_save` | Thalindra (above the bandit) loops until it fails its STR save → `push_applied` True + the bandit's NPC token moved +70 px (5 ft / 1 cell away); a passed save moves nothing. NPC token created + torn down. |
| `test_gust_cannot_cast` | Krieger (Barbarian) → 409 `cannot_cast`. |
| `test_gust_missing_target_400` | Missing `target_combatant_id` → 400. |

### `test_menacing_attack.py`
v2.99.253 — Battle Master maneuver 3 of 16 — Menacing Attack (PHB p.74). Mirrors Trip/Disarming but save ability is WIS and on-fail is Frightened.

| Test | What it asserts |
|------|-----------------|
| `test_use_ma_happy` | Lv 9 Garrik (Battle Master, d8) → `extra_damage` in 1..8, `save_dc == 16`, `save_ability == "WIS"`, dice 4 → 3, broadcast (source `menacing-attack`). |
| `test_use_ma_out_of_dice` | `superiority-dice.current = 0` → 409 `out_of_uses`. |
| `test_use_ma_wrong_subclass` | Default Garrik (Champion) → 409 `wrong_subclass_or_level`. |

### `test_disarming_attack.py`
v2.99.252 — Battle Master maneuver 2 of 16 — Disarming Attack (PHB p.74). Mirrors Trip Attack's shape; on-fail effect is "drop one held object" vs Prone.

| Test | What it asserts |
|------|-----------------|
| `test_use_da_happy` | Lv 9 Garrik (Battle Master, d8) → `extra_damage` in 1..8, `save_dc == 16` (prof +4 + max(STR +4, DEX +2)), dice 4 → 3, broadcast (source `disarming-attack`). |
| `test_use_da_out_of_dice` | `superiority-dice.current = 0` → 409 `out_of_uses`. |
| `test_use_da_wrong_subclass` | Default Garrik (Champion) → 409 `wrong_subclass_or_level`. |
| `test_use_da_level_gate` | Battle Master at Lv 2 → 409. |

### `test_trip_attack.py`
v2.99.233 — Battle Master Fighter (PHB p.74) Combat Superiority pool + Trip Attack maneuver (Phase 1 of [docs/plans/battle-master.md](../plans/battle-master.md)). Garrik Ironside is the demo fixture; tests PATCH his subclass to "Battle Master" + seed a `superiority-dice` resource.

| Test | What it asserts |
|------|-----------------|
| `test_use_trip_attack_happy` | Lv 9 Garrik (Battle Master, d8 die) → `extra_damage` in 1..8, `save_dc == 16` (prof +4 + max(STR +4, DEX +2)), dice 4 → 3 + broadcast (source `trip-attack`). |
| `test_use_trip_attack_out_of_dice` | `superiority-dice.current = 0` → 409 `out_of_uses`. |
| `test_use_trip_attack_wrong_subclass` | Default Garrik (Champion) → 409 `wrong_subclass_or_level`. |
| `test_use_trip_attack_level_gate` | Battle Master at Lv 2 (not 3+) → 409. |

### `test_weapon_bond.py`
v2.99.232 — Eldritch Knight Fighter (PHB p.74) Weapon Bond (Phase 1 of [docs/plans/eldritch-knight.md](../plans/eldritch-knight.md)). Garrik Ironside is the demo fixture; tests PATCH his subclass to "Eldritch Knight".

| Test | What it asserts |
|------|-----------------|
| `test_use_weapon_bond_happy` | Bond Greatsword (index 0) → `bonded_weapons == ["greatsword"]` + broadcast (source `weapon-bond`). |
| `test_use_weapon_bond_second_weapon` | Greatsword then Glaive → `bonded_weapons` length 2. |
| `test_use_weapon_bond_cap_reached` | Two already bonded → third attempt → 409 `cap_reached` (RAW max 2). |
| `test_use_weapon_bond_wrong_subclass` | Default Garrik (Champion) → 409 `wrong_subclass_or_level`. |
| `test_use_weapon_bond_level_gate` | Eldritch Knight at Lv 2 (not 3+) → 409. |
| `test_use_weapon_bond_non_weapon` | `weapon_index` pointing at Chain mail (armor) → 400. |

### `test_wild_magic_spell_bombardment.py`
v2.99.231 — Wild Magic Sorcerer (PHB p.103) Spell Bombardment (Phase 5 of [docs/plans/wild-magic.md](../plans/wild-magic.md), final phase). Once-per-turn flag tracked via `combatant.economy.spell_bombardment_used` (mirror of Colossus Slayer's v2.60.0 flag).

| Test | What it asserts |
|------|-----------------|
| `test_use_spell_bombardment_happy` | Lv 18 Wild Magic Zara, `die_size: 8` → `extra_damage` in 1..8 + broadcast (source `spell-bombardment`). |
| `test_use_spell_bombardment_once_per_turn` | First call succeeds; second call same turn → 409 `once_per_turn`. |
| `test_use_spell_bombardment_bad_die_size` | `die_size: 5` → 400 (only 4/6/8/10/12 allowed). |
| `test_use_spell_bombardment_wrong_subclass` | Default Draconic Bloodline → 409 `wrong_subclass_or_level`. |
| `test_use_spell_bombardment_level_gate` | Wild Magic at Lv 17 (not 18+) → 409. |

### `test_wild_magic_controlled_chaos.py`
v2.99.230 — Wild Magic Sorcerer (PHB p.103) Controlled Chaos (Phase 4 of [docs/plans/wild-magic.md](../plans/wild-magic.md)). Lv 14+ Wild Magic Sorcerers roll the surge table twice and pick. Uses TEST_MODE `_force_surge_d20: 1` on `/cast_spell` for determinism.

| Test | What it asserts |
|------|-----------------|
| `test_controlled_chaos_rolls_twice_at_lv14` | Lv 14 Wild Magic Zara casts Magic Missile with forced d20=1 → `wild_magic_surge` broadcast carries `controlled_chaos: true` + `alternatives` length 2 (each with slug/name/d100). |
| `test_controlled_chaos_single_entry_at_lv5` | Lv 5 Wild Magic Zara → broadcast `controlled_chaos: false` + `alternatives` length 1 (regression for the v2.99.230 backward-compat shape). |

### `test_wild_magic_bend_luck.py`
v2.99.229 — Wild Magic Sorcerer (PHB p.103) Bend Luck reaction (Phase 3 of [docs/plans/wild-magic.md](../plans/wild-magic.md)). Zara Emberfire is the demo fixture; tests PATCH her subclass to "Wild Magic" + level to 6.

| Test | What it asserts |
|------|-----------------|
| `test_use_bend_luck_bonus` | Bonus mode → SP 5 → 3, `d4` in 1..4, `signed > 0`, broadcast fired. |
| `test_use_bend_luck_penalty` | Penalty mode → `signed < 0` and equals `-d4`. |
| `test_use_bend_luck_out_of_sp` | SP at 1 → 409 `out_of_uses` (RAW: costs 2 SP). |
| `test_use_bend_luck_wrong_subclass` | Default Draconic Bloodline → 409 `wrong_subclass_or_level`. |
| `test_use_bend_luck_level_gate` | Wild Magic at Lv 5 (not 6+) → 409. |
| `test_use_bend_luck_bad_mode` | `mode: "sideways"` → 400. |

### `test_wild_magic_surge.py`
v2.99.228 — Wild Magic Sorcerer (PHB p.103) Wild Magic Surge auto-roll (Phase 2 of [docs/plans/wild-magic.md](../plans/wild-magic.md)). Zara Emberfire is the demo fixture; tests PATCH her subclass to "Wild Magic". Uses the TEST_MODE-only `_force_surge_d20` body param on /cast_spell for deterministic outcomes.

| Test | What it asserts |
|------|-----------------|
| `test_wild_magic_surge_fires_on_d20_one` | Wild Magic Zara casts Magic Missile (Lv 1) with `_force_surge_d20: 1` → `wild_magic_surge` broadcast with table entry (slug, name, desc, d100, tides_refilled). |
| `test_wild_magic_surge_refills_tides_of_chaos` | After surge fires with `tides_of_chaos_uses` at 0 pre-cast, a follow-up `/use_tides_of_chaos` succeeds (RAW refill on DM-triggered surge). |
| `test_wild_magic_no_surge_on_d20_high` | `_force_surge_d20: 20` → no surge broadcast (only natural 1 triggers). |
| `test_wild_magic_cantrip_no_surge` | Cantrip cast with `_force_surge_d20: 1` → no surge (RAW gates on Lv 1+ spell). |
| `test_wild_magic_non_subclass_no_surge` | Default Draconic Bloodline Zara with `_force_surge_d20: 1` → no surge (subclass gate). |

### `test_wild_magic_tides.py`
v2.99.227 — Wild Magic Sorcerer (PHB p.103) Tides of Chaos (Phase 1 of [docs/plans/wild-magic.md](../plans/wild-magic.md)). Zara Emberfire is the demo fixture; tests PATCH her subclass to "Wild Magic" + counter to 1.

| Test | What it asserts |
|------|-----------------|
| `test_use_tides_of_chaos_happy_path` | Wild Magic Zara counter 1 → 200, `uses_remaining == 0`, buff installed, broadcast. |
| `test_use_tides_of_chaos_out_of_uses` | Second invocation on the same turn → 409 `out_of_uses`. |
| `test_use_tides_of_chaos_wrong_class` | Krieger (Barbarian) → 409 `wrong_subclass_or_level`. |
| `test_use_tides_of_chaos_wrong_subclass` | Zara default (Draconic Bloodline) → 409 `wrong_subclass_or_level`. |
| `test_tides_of_chaos_long_rest_refill` | Consume → /rest long → second use succeeds (counter refilled to 1). Exercises the v2.99.227 `subclass` class-scope fix that keeps the PATCH'd subclass through normalize_dnd5e_sheet. |

### `test_berserker_path.py`
v2.99.226 — Path of the Berserker (PHB p.49) Frenzy (Lv 3) + Intimidating Presence (Lv 10). Krieger Stonefist is the demo fixture; IP test PATCHes him Lv 7 → 10.

| Test | What it asserts |
|------|-----------------|
| `test_use_frenzy_after_rage` | `/use_rage` to install the rage buff, then `/use_frenzy` → 200 + `feature_used` broadcast (source `frenzy`). |
| `test_use_frenzy_without_rage` | No rage buff → 409 `not_raging`. |
| `test_use_frenzy_wrong_class` | Pip (Rogue) → 409 `wrong_subclass_or_level`. |
| `test_use_intimidating_presence_at_lv10` | Krieger PATCH'd to Lv 10 → `dc == 10` (sheet prof +3 unchanged on level PATCH; CHA 8 → -1; 8 + 3 + (-1) = 10) + `target_name == "Bandit"` + broadcast. |
| `test_use_intimidating_presence_level_gate` | Control: Krieger at Lv 7 → 409 `wrong_subclass_or_level`. |

### `test_evocation_school.py`
v2.99.225 — Evocation Wizard (PHB p.117) Sculpt Spells (Lv 2) + Empowered Evocation (Lv 10). Thalindra Moonwhisper is the demo fixture; Empowered Evocation test PATCHes her Lv 7 → 10.

| Test | What it asserts |
|------|-----------------|
| `test_use_sculpt_spells_lv3_fireball` | Thalindra at Lv 7 with `spell_level=3` → `protected_count == 4` + sculpt-spells broadcast. |
| `test_use_sculpt_spells_bad_level` | `spell_level=0` → 400. |
| `test_use_sculpt_spells_wrong_class` | Krieger (Barbarian) → 409 `wrong_subclass_or_level`. |
| `test_use_empowered_evocation_at_lv10` | Thalindra PATCH'd to Lv 10 → `int_mod == 3` (INT 16) + empowered-evocation broadcast. |
| `test_use_empowered_evocation_level_gate` | Control: Thalindra at Lv 7 → 409 `wrong_subclass_or_level`. |

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

### `test_use_stunning_strike.py`
v2.49.55 — Monk class feature `POST /use_stunning_strike`. Lv 5+ + ki >= 1 + a target. Server rolls a CON save for NPC targets (or creates a roll_request for PCs); on fail, installs Stunned (concentration=False, 1-turn duration) via the existing save-or-suck pipeline. First endpoint to install a `concentration: False` incapacitating buff — validates the v2.49.51 hook's non-concentration branch (for PC targets via the roll_request path; NPC validation here verifies the install + buff shape).

| Test | What it asserts |
|------|-----------------|
| `test_stunning_strike_happy_path_npc` | Kael (Monk Lv 5) hits a bandit until the save fails; assert `auto_save_buff_installed=Stunned`, `concentration=False` on the broadcast buff, `source_char_id=Kael`. Retry loop because the d20 is random. |
| `test_stunning_strike_wrong_class` | Krieger (Barbarian) → 409 `wrong_class` with `expected=monk`. |
| `test_stunning_strike_no_ki` | Drain Kael's ki via repeated calls (response carries `ki_remaining`); when 0, next call → 409 `no_ki` with `available=0`. |
| `test_stunning_strike_pc_drops_own_concentration` | v2.49.56 — closes the v2.49.55 filed item. Magnus casts Hex (concentration); Kael uses Stunning Strike on Magnus → roll_request; GM-as-Magnus /responds; on save fail assert (a) Stunned lands on Magnus, (b) Magnus's Hex drops via the v2.49.51 hook's `concentration: False` branch, (c) 💀 GM log naming "stunned" + "incapacitated" fires. Retry loop because the CON save is random. |

### `test_use_metamagic_empowered.py`
v2.49.124-125 — Sorcerer Lv 3+ Empowered Spell metamagic (Phase 1 of the Sorcery Points + Metamagic plan). New endpoint `/use_metamagic_empowered_spell` spends 1 sorcery point + installs a one-cast `metamagic-empowered-pending` buff on the caster carrying `effects.rerolls_available = max(1, CHA-mod)`. The next `/cast_spell` damage roll consumes the buff and rerolls up to that many lowest dice. v2.49.124 wires the save-for-half single-target NPC path; v2.49.125 wires the multi-beam attack-roll path (Scorching Ray, Eldritch Blast, Fire Bolt) with a pool reroll across all beams. Cast payload gains an `empowered_spell` block (`rerolled_count`, `original_total`, `final_total`, `rerolls` list of `{sides, old, new}`). Demo subject: Zara (CHA 17 → +3 mod, 5 SP, knows Fire Bolt / Scorching Ray / Fireball at spell indices 0 / 10 / 11).

| Test | What it asserts |
|------|-----------------|
| `test_empowered_arms_pending_buff` | 1 SP → 200, buff installed on Zara's combatant with `effects.rerolls_available=3` + `effects.metamagic_option="empowered-spell"`. SP decremented to 4. |
| `test_empowered_409_when_no_sorcery_points` | Drain 5 SP via 5 arm calls → 6th returns 409 `not_enough_points` (`required=1`, `have=0`). |
| `test_empowered_wrong_class` | Thalindra (Wizard) → 409 `wrong_class` with `expected="sorcerer"`. |
| `test_empowered_buff_consumed_on_cast_fireball` | Arm Empowered → cast Fireball at a bandit → response `empowered_spell` block present, `rerolled_count==3`, each reroll entry has `sides==6` + `old/new` in 1-6. Buff removed after the cast. |
| `test_empowered_pool_reroll_scorching_ray` | v2.49.126 — true cross-beam Empowered. Arm Empowered → cast Scorching Ray L2 (3 beams of 2d6 = 6-die pool); retry until ≥ 2 beams hit + budget fully fires; assert `rerolled_count==3` (CHA-mod budget fully spent across the pool) + each cast fires 3 beams + at least one beam's `damage_breakdown` carries the `→` annotation. Proves the pool reroll spans beams, not just the first one. |
| `test_scorching_ray_l3_slot_fires_four_beams` | v2.49.127 — RAW upcast: cast Scorching Ray at L3 slot → assert 4 beams (3 base + 1 upcast). Exercises the new `extra_beams_per_slot_above_base` action-schema field. |
| `test_scorching_ray_l2_slot_fires_three_beams` | v2.49.127 control — cast at base L2 slot → assert 3 beams (no upcast bonus). Off-by-one regression guard for the slot-delta math. |
| `test_empowered_single_beam_fire_bolt` | v2.49.125 — attack-roll path. Arm Empowered → cast Fire Bolt (2d10 cantrip); assert `rerolled_count==2` (CHA-mod budget 3 clipped to pool size 2) + all reroll log entries are d10. |
| `test_no_empowered_block_when_buff_absent` | Control: cast Fireball without arming → `empowered_spell` key NOT present in payload (no spurious fire). |

### `test_use_font_of_magic.py`
v2.49.120 — Sorcerer Lv 2+ Font of Magic feature (Phase 0 of the Sorcery Points + Metamagic plan). Two endpoints: `/use_font_of_magic_to_points` (spell slot → sorcery points, gain = slot level) + `/use_font_of_magic_to_slot` (sorcery points → spell slot, cost table L1=2/L2=3/L3=5/L4=6/L5=7). Both bonus actions; L6+ slots not recoverable per RAW. Demo subject: Zara Emberfire (Sorcerer L5).

| Test | What it asserts |
|------|-----------------|
| `test_font_of_magic_l1_slot_to_1_sp` | Sacrifice L1 slot → +1 SP. From a full pool (5/5), the +1 overflow caps; response carries `sp_overflow_lost: 1`. |
| `test_font_of_magic_l3_slot_to_3_sp` | Sacrifice L3 slot → +3 SP (with overflow when starting full). |
| `test_font_of_magic_no_slot_to_sacrifice` | Zara has no L4 slots (Lv 5) → 409 `no_slot`. |
| `test_font_of_magic_2_sp_to_l1_slot` | After sacrificing an L1 slot, spend 2 SP to recover it. |
| `test_font_of_magic_5_sp_to_l3_slot` | After sacrificing an L3 slot, spend the full pool (5 SP) to recover it. |
| `test_font_of_magic_slot_too_high` | L6+ slots → 409 `slot_too_high` with `max_recoverable: 5`. |
| `test_font_of_magic_not_enough_points` | Drain SP to 1, try to recover an L1 slot (cost 2) → 409 `not_enough_points`. |
| `test_font_of_magic_no_used_slot_to_restore` | All L1 slots full → 409 `no_used_slot_to_restore` (the RAW "ephemeral slot creation" edge case is filed). |
| `test_font_of_magic_wrong_class` | Thalindra the Wizard → 409 `wrong_class`. |

### `test_flurry_chip_refund.py`
v2.49.117 — Phase B v2. While `flurry-of-blows-active` is on the attacker, the next two unarmed-strike attacks DON'T burn the action chip; `effects.unarmed_strikes_available` decrements per strike. When it hits 0, the buff drops. Non-unarmed attacks while Flurry active still mark the chip — RAW Flurry grants unarmed strikes only.

| Test | What it asserts |
|------|-----------------|
| `test_unarmed_strike_with_flurry_active_refunds_chip` | Activate Flurry → unarmed strike → action chip stays clear; buff counter ticks 2 → 1. |
| `test_second_unarmed_strike_consumes_flurry` | Two unarmed strikes in succession → buff DROPS after the second (counter hit 0). |
| `test_non_unarmed_attack_with_flurry_active_still_marks_chip` | Quarterstaff attack with Flurry active → chip marked normally; buff counter unchanged. |
| `test_unarmed_strike_without_flurry_marks_chip` | Control / regression guard: unarmed strike WITHOUT Flurry → action chip marked normally. |

### `test_dodging_disadvantage.py`
v2.49.115 — first Phase B effect integration. When a weapon attack targets a combatant with the `patient-defense` buff (`effects.dodging: True`), the d20 attack roll uses disadvantage (`2d20kl1`). Handles the Rage-attacker-vs-Dodging-target cancellation per RAW PHB p.173 (advantage + disadvantage = neither = straight 1d20).

| Test | What it asserts |
|------|-----------------|
| `test_attack_without_dodging_uses_straight_d20` | Control case — no buff, no `2d20kl1` in `attack_breakdown`. Regression guard. |
| `test_attack_against_dodging_target_has_disadvantage` | Kael uses Patient Defense → Krieger's attack against Kael shows `2d20kl1` in the breakdown. |
| `test_rage_attacker_vs_dodging_target_cancels` | Krieger Rages + Kael dodges → straight `1d20` (neither `2d20kh1` nor `2d20kl1` in the breakdown). |

### `test_use_flurry_of_blows.py`
v2.49.114 — Monk class feature `POST /use_flurry_of_blows` (Lv 2+). Spend 1 ki as a bonus action to install the `flurry-of-blows-active` buff (1 round, `effects.unarmed_strikes_available: 2` + `effects.is_flurry: True`). Signals "two unarmed strikes available" for a future Phase B attack-flow integration and the v2.49.57 Open Hand Technique trigger.

| Test | What it asserts |
|------|-----------------|
| `test_flurry_of_blows_happy_path` | Kael → 200, `remaining=4` (was 5), `unarmed_strikes_available=2`. `buff_update` broadcast carries `flurry-of-blows-active` key, `effects.unarmed_strikes_available=2`, `effects.is_flurry=True`, `concentration=False`, `duration_rounds=1`. |
| `test_flurry_of_blows_wrong_class` | Krieger (Barbarian) → 409 `wrong_class` with `expected=monk`. |
| `test_flurry_of_blows_no_ki` | Drain ki via 5 override calls; 6th → 409 `no_ki`. |

### `test_use_patient_defense.py`
v2.49.112 — Monk class feature `POST /use_patient_defense` (Lv 2+). Spend 1 ki as a bonus action to install Dodging (advantage on DEX saves; attackers have disadvantage). Self-buff, no target. Duration 1 round (until start of next turn).

| Test | What it asserts |
|------|-----------------|
| `test_patient_defense_happy_path` | Kael at full ki → POST → 200, `remaining=4` (was 5), `buff_installed=True`. `buff_update` broadcast carries the `patient-defense` key with `concentration=False`, `effects.dodging=True`, `dex_save` in `advantage_on`. |
| `test_patient_defense_wrong_class` | Krieger (Barbarian) → 409 `wrong_class` with `expected=monk`. |
| `test_patient_defense_no_ki` | Drain Kael's ki to 0 via 5 successive override-bypassed calls; 6th call → 409 `no_ki` with `available=0`. |

### `test_use_step_of_the_wind.py`
v2.49.112 — Monk class feature `POST /use_step_of_the_wind` (Lv 2+). Spend 1 ki as a bonus action; takes `mode: "disengage" | "dash"`. Both install a 1-round self-buff with `jump_distance_doubled`; the disengage variant adds `effects.disengage=True`, the dash variant adds `effects.dash=True`.

| Test | What it asserts |
|------|-----------------|
| `test_step_of_the_wind_disengage_mode` | Kael, mode=disengage → 200, `remaining=4`, `buff_installed=True`. `buff_update` broadcast has `step-of-the-wind-disengage` key with `effects.disengage=True` + `effects.jump_distance_doubled=True`, `concentration=False`. |
| `test_step_of_the_wind_dash_mode` | Kael, mode=dash → 200, `mode=dash` in response. `buff_update` broadcast has `step-of-the-wind-dash` key with `effects.dash=True` + `effects.jump_distance_doubled=True`. |
| `test_step_of_the_wind_wrong_class` | Krieger → 409 `wrong_class`. |
| `test_step_of_the_wind_invalid_mode` | mode="fly" → 400 with "mode" in the error body. |

### `test_use_attack_improved_critical.py`
v2.49.231 — Champion Fighter Lv 3+ subclass feature. Server-side crit threshold drops from 20 to 19 for Champion attackers; `_attacker_crit_threshold(sheet)` reads class/subclass/level. Tests use `/api/test/dice/seed` for deterministic dice + 200-roll batches per attacker, parse the `attack_breakdown` for the kept d20 value, then group-assert `is_crit` matches the expected threshold.

| Test | What it asserts |
|------|-----------------|
| `test_champion_crits_on_19` | Garrik (Lv 5 Champion) — every d20=19 in the batch crits (Improved Critical fires); every d20=20 crits (baseline); every d20<19 does NOT crit (regression guard). |
| `test_rogue_does_not_crit_on_19` | Pip (Rogue) control — d20=19 must NOT crit (Improved Critical is Champion-only); d20=20 still crits per baseline. |

### `test_use_stillness_of_mind.py`
v2.49.229 — Monk class feature `POST /use_stillness_of_mind` (Lv 7). Action, unlimited uses. Takes `{character_id, buff_key}`; validates buff_key is in `{charmed, frightened}` (refuses paralyzed/stunned/etc. per RAW). Removes the matching buff via `_remove_buff` (same helper /end_buff uses), syncs the sheet mirror, marks the action slot, broadcasts buff_update + feature_used.

| Test | What it asserts |
|------|-----------------|
| `test_stillness_of_mind_clears_charmed` | Seed Kael with a Charmed buff → 200; `removed_key=charmed`, `removed_name=Charmed`. `buff_update` shows the buff gone; `feature_used` source=stillness-of-mind. |
| `test_stillness_of_mind_clears_frightened` | Same path, Frightened buff variant → 200; `removed_key=frightened`. |
| `test_stillness_of_mind_wrong_class` | Pip (Rogue) → 409 `error=wrong_class`, `expected=monk`, `got=rogue`. |
| `test_stillness_of_mind_wrong_condition` | buff_key="stunned" → 409 `error=wrong_condition`, `got=stunned`, `allowed=[charmed,frightened]`. |
| `test_stillness_of_mind_buff_not_present` | Kael with no Charmed/Frightened buff → 404 `error=buff_not_present`. |
| `test_stillness_of_mind_missing_buff_key` | Missing buff_key → 400. |
| `test_stillness_of_mind_missing_character_id` | Missing character_id → 400. |

### `test_use_wholeness_of_body.py`
v2.49.227 — Monk subclass feature `POST /use_wholeness_of_body` (Way of the Open Hand, Lv 6). Action, 1/long rest, deterministic heal = 3 × monk level (no roll). Atomically decrements the `wholeness-of-body` counter, applies HP via `_apply_hp_change`, marks the action slot, broadcasts `feature_used` + `resource_update` + `character_death_save` (when applicable). Kael Brightleaf (bumped from Lv 5 to Lv 6 in the same release) is the demo fixture.

| Test | What it asserts |
|------|-----------------|
| `test_wholeness_of_body_happy_path` | Kael spends WoB → 200, `rolled=18` (3 × Lv 6), `actual_healed=0` (at full HP), `remaining=0`, `max=1`. `feature_used` broadcast carries `source=wholeness-of-body`, heal_target_name=Kael, `feature_desc` includes "18" and "Lv 6". `resource_update` broadcast confirms `current=0`, `max=1`. |
| `test_wholeness_of_body_out_of_uses` | Drain the one use; second call → 409 `error=out_of_uses` with `label="Wholeness of Body"`. |
| `test_wholeness_of_body_wrong_class` | Pip (Rogue) → 409 `error=wrong_class`, `expected=monk`, `got=rogue`. |
| `test_wholeness_of_body_missing_character_id` | Empty body → 400. |

### `test_use_reckless_attack.py`
v2.49.238 — Barbarian class feature `POST /use_reckless_attack` (Lv 2+). No counter cost; installs a 1-round self-buff with `effects.advantage_on=['str_attack']` + `effects.incoming_attacks_have_advantage=True`. Phase-B integration: the new `_target_grants_advantage_to_attackers` helper exposes the downside to `use_attack` so attacks AGAINST a reckless barbarian roll `2d20kh1`. The upside (advantage on the barbarian's own STR melee attacks) folds into the generalized `_attacker_has_str_attack_advantage` (formerly `_has_rage_str_advantage`).

| Test | What it asserts |
|------|-----------------|
| `test_reckless_attack_happy_path` | Krieger → 200, `buff_installed=True`, `duration_rounds=1`. `buff_update` broadcast carries `reckless-attack` key with both effect flags; `feature_used` source=reckless-attack. |
| `test_reckless_attack_wrong_class` | Pip (Rogue) → 409 `error=wrong_class`, `expected=barbarian`. |
| `test_reckless_attack_missing_character_id` | Empty body → 400. |
| `test_attack_against_reckless_target_gets_advantage` | Seeds Krieger with the reckless-attack buff pre-installed; Pip's Shortsword attack against him rolls `2d20kh1` (breakdown match) and `roll_state_applied` mentions reckless. |

### `test_settings_roll_log_position.py`
v2.49.244 — per-user UI preference. `POST /api/settings/roll_log_position` flips the Roll Log drawer between the shared right sidebar (default) and an independent left-side sidebar.

| Test | What it asserts |
|------|-----------------|
| `test_roll_log_position_left_then_right` | GM POSTs `{"position": "left"}` → 200 + `roll_log_position == "left"`; subsequent POST `{"position": "right"}` flips back, both persist. |
| `test_roll_log_position_rejects_invalid_value` | `{"position": "middle"}` → 400 with the invalid value surfaced in the response body. |
| `test_roll_log_position_persists_for_player` | Per-user isolation — Alice sets `left` independently of the GM; cleanup resets her to `right`. |

### `test_encounter_background.py`
v2.86.0 — encounter backgrounds. Fullscreen fixed-position image/video layer behind the battle map; `POST /api/campaign/{cid}/background` writes `campaign.active_background_url` + broadcasts `background_change`; `POST /api/campaign/{cid}/encounters/{eid}/background` writes `enc.background_url` without broadcasting (the encounter load flow propagates).

| Test | What it asserts |
|------|-----------------|
| `test_campaign_background_missing_payload_400` | No file + `clear=false` on the campaign endpoint → 400. Guards against silent no-op calls. |
| `test_campaign_background_upload_then_clear` | Multipart PNG upload → 200 + `active_background_url` starts with `/static/uploads/encounter_bg/` + `background_change` WS broadcast carries the new URL. Subsequent `clear=true` → 200 + URL nulled + broadcast carries `null`. |
| `test_campaign_default_falls_back_for_encounter_without_bg` | v2.87.0 — campaign endpoint sets both `default_background_url` and `active_background_url`; a no-bg encounter creates with `background_url=null`. Proves the contract that powers the fallback in `_perform_encounter_load` (enc bg → campaign default → null). |
| `test_encounter_background_upload_does_not_broadcast` | Creates a throwaway encounter, attaches a background to it via the per-encounter endpoint, asserts the encounter projection now carries `background_url`, asserts NO `background_change` broadcast fires (propagation only happens on encounter load), cleans up via the delete endpoint. |

### `test_use_indomitable.py`
v2.56.0 — Fighter Lv 9+ Indomitable. Arm-then-consume single-use save-advantage buff (`indomitable-armed`). Save-roll hook reads + consumes the buff per-save. RAW-bent v1 (advantage on next save instead of post-roll reroll-on-failure); see TODO.md.

| Test | What it asserts |
|------|-----------------|
| `test_use_indomitable_arms_buff` | `/use_indomitable` → 200, `remaining=0`, buff `indomitable-armed` lands on Garrik's combatant, arm-side `feature_used(source=indomitable)` broadcast. |
| `test_use_indomitable_wrong_class` | Pip (Rogue) → 409 `wrong_class` with `expected=fighter`. |
| `test_use_indomitable_out_of_uses` | First call burns the only use; second call → 409 `out_of_uses` with `label=Indomitable`. |
| `test_indomitable_consumes_on_save` | Arm + cast Suggestion at Garrik → save `base_expression="2d20kh1"`, buff removed from Garrik's combatant, consume-side `feature_used(source=indomitable)` broadcast. |
| `test_indomitable_one_save_only` | After consume, a second save in the same round has `base_expression="1d20"` (no kh1; buff already consumed). |

### `test_aura_of_devotion.py`
v2.55.0 — Paladin Oath of Devotion Lv 7+ Aura of Devotion. First **condition-install immunity gate** — when a failed Wis save would install Charmed on a PC ally, and any Paladin Lv 7+ with subclass `devotion` is in init, the install is BLOCKED and a `feature_used(source=aura-of-devotion)` broadcast surfaces the immunity. Distinct from Aura of Protection (save modifier): AoD acts AFTER the save resolves to bypass the consequence.

| Test | What it asserts |
|------|-----------------|
| `test_aura_of_devotion_blocks_charmed_install` | Caelan + Krieger in init; Lyra casts Suggestion at Krieger; loop until save fails → response `auto_buff_installed=""`, Krieger's buff list has no `charmed` entry, broadcast names Caelan. |
| `test_charmed_installs_when_paladin_absent` | Control: Caelan NOT in init → failed save installs Charmed normally; no AoD broadcast. |
| `test_aod_skips_non_charm_conditions` | Caelan in init + Tavik casts Hold Person → failed save installs Paralyzed (AoD is charm-only). |

### `test_mindless_rage.py`
v2.57.0 — Path of the Berserker Lv 6+ Mindless Rage. **Self-targeted** condition-install immunity gate (sibling of AoD but keyed off the saver's own active rage buff instead of an ally aura). When a failed Wis/Cha save would install Charmed or Frightened on a Barbarian and the saver has a rage buff active, the install is BLOCKED and a `feature_used(source=mindless-rage)` broadcast surfaces the immunity. Helper `_pc_has_rage_active_buff` reads the active battle combatant's buff list; gate sits next to the v2.55.0 AoD branch in `/roll_request/{id}/respond`.

| Test | What it asserts |
|------|-----------------|
| `test_mindless_rage_blocks_charmed_install` | Krieger rages (`/use_rage`); Lyra casts Suggestion at Krieger; loop until save fails → response `auto_buff_installed=""`, Krieger's buff list has no `charmed` entry, broadcast names Krieger. |
| `test_charmed_installs_when_not_raging` | Control: Krieger does NOT rage → failed save installs Charmed normally; no Mindless Rage broadcast. |
| `test_mindless_rage_skips_non_charm_fright` | Krieger rages + Tavik casts Hold Person → failed save installs Paralyzed (Mindless Rage is charm/fright-only). |

### `test_life_domain_heal_uplift.py`
v2.58.0 — Life Domain Cleric heal-uplift hook. Two stacked features fire on outgoing Lv 1+ heals: **Disciple of Life** (Lv 1+) adds 2 + slot_level HP to the target heal; **Blessed Healer** (Lv 6+) ALSO self-heals the caster for 2 + slot_level when target ≠ caster. Helper `_life_domain_heal_uplift(caster_sheet, slot_level, target_is_self)` returns `(target_uplift, self_uplift)`. Wired in the /cast_spell heal-resolution branch — target gets `heal_rolled + target_uplift` via the existing single `_apply_heal_to_combatant`; caster gets a second `_apply_heal_to_combatant` call when `self_uplift > 0`. Two `feature_used` broadcasts (`source=disciple-of-life`, `source=blessed-healer`) credit the chat card.

| Test | What it asserts |
|------|-----------------|
| `test_disciple_and_blessed_healer_on_other_target` | Tavik casts Cure Wounds (L1) at Krieger → both `disciple-of-life` (+3) and `blessed-healer` (+3) broadcasts fire. |
| `test_blessed_healer_skips_self_target` | Tavik casts Healing Word at himself → only `disciple-of-life` fires (Blessed Healer RAW requires target ≠ caster). |
| `test_no_uplift_for_non_life_domain_caster` | Control: Lyra (College of Lore Bard) casts Cure Wounds at Krieger → neither broadcast fires. |

### `test_mass_healing_word_aoe.py`
v2.59.0 — Multi-target heal loop in `/cast_spell`. Extends the v2.58.0 Life Domain hook to Mass Healing Word / Mass Cure Wounds. Single-target block handles `target_combatant_ids[0]`; new extras loop walks `[1:]` applying per-target Disciple of Life uplift and one late Blessed Healer self-heal (if not already fired). Blessed Healer is per-cast, not per-target (RAW). Extras use `cast_id=None` so undo reverts the first target only.

| Test | What it asserts |
|------|-----------------|
| `test_mass_healing_word_per_target_disciple_uplift` | Tavik casts MHW (slot 3) at Krieger + Pip → 2 `disciple-of-life` broadcasts (+5 each) + 1 `blessed-healer` broadcast. |
| `test_aoe_heal_skips_uplift_for_non_life_domain` | Single-target MHW (one target via `target_combatant_ids`) → extras loop skipped (len == 1); 1 Disciple + 1 Blessed Healer from single-target block only. |
| `test_mass_healing_word_blessed_healer_skips_self_first_target` | Tavik MHW at himself + Krieger → 2 Disciple broadcasts (self + Krieger), 1 late Blessed Healer fired from extras loop (single-target block skipped it because first target was caster). |

### `test_heal_spellcasting_mod.py`
v2.59.1 — Heal expressions bake the caster's spellcasting modifier. Pre-v2.59.1, /cast_spell rolled SRD JSON heal dice bare (e.g. Cure Wounds `1d8`). RAW: heal = dice + spellcasting modifier. `_caster_spellcasting_mod(caster_sheet)` reads the ability slug + score from the sheet; the heal-resolution branch adds the modifier to `heal_rolled` before the v2.58.0 Disciple of Life uplift. Modifier > 0 gate keeps negative-mod behavior at RAW heal floor.

| Test | What it asserts |
|------|-----------------|
| `test_cure_wounds_adds_wis_modifier_to_heal` | Tavik (WIS 16 = +3) casts Cure Wounds (L1) at Krieger 5 times. Every `auto_heal_rolled` is in [4, 11] (= 1d8 + 3). Pre-fix min was 1. |

### `test_heal_claim_uplift.py`
v2.59.2 — Legacy `/apply_healing` (chat-card "🩹 Apply Healing" button) path honors caster spellcasting modifier + Life Domain uplift. Pre-v2.59.2 the claim flow rolled bare dice — bypassed the v2.58.0 + v2.59.1 corrections. Fix: `_heal_claims[cast_id]` captures `caster_char_id` + `slot_level` at registration; /apply_healing reads them, runs the same uplift composition + broadcasts as the target-bound path.

| Test | What it asserts |
|------|-----------------|
| `test_apply_healing_runs_life_domain_uplift` | Tavik casts Cure Wounds with no target → /apply_healing routes to Tavik himself (calling user's first PC fallback) → Disciple of Life broadcast fires; Blessed Healer does NOT (RAW: only when target ≠ caster). |
| `test_apply_healing_routes_to_stored_target_and_fires_blessed_healer` | Sanity check on the target-bound path still works after the heal-claim edits: Tavik casts Cure Wounds at Krieger via target_combatant_id → Disciple + Blessed Healer both fire (v2.58.0 path unchanged). |

### `test_divine_strike.py`
v2.60.0 — Divine Strike (Life Domain Cleric Lv 8+). +1d8 radiant on first weapon hit per turn, wired into `_compute_attack_auto_uplifts`. Once-per-turn lock via `combatant.economy.divine_strike_used` (mirror of v2.20.0 Colossus Slayer flag). Companion helper `_mark_divine_strike_used` flips the flag. Client-side turn-advance handlers in tabletop.html reset the flag alongside `colossus_slayer_used`.

| Test | What it asserts |
|------|-----------------|
| `test_divine_strike_fires_on_first_weapon_hit` | Tavik (Lv 8 Life Domain) attacks Krieger with Warhammer → /attack `auto_uplifts` carries a divine-strike entry with `1d8` expression + `radiant` damage_type. |
| `test_divine_strike_locks_after_first_hit` | Same turn, second attack → divine-strike NOT in auto_uplifts (once-per-turn lock). |
| `test_divine_strike_skips_non_cleric` | Pip (Rogue) attacks Krieger → no divine-strike uplift fires (subclass gate). |

### `test_aura_range_gate.py`
v2.61.0 — F1 framework lands. New helper `_distance_ft_between_chars(db, campaign_id, char_a_id, char_b_id) → float | None` wraps the existing `_distance_ft_between_points` with Token-position lookup. Wired into AoP / AoD / Countercharm as a range gate (10/30 ft / 10/30 ft / 30 ft). Fall-back-to-no-position when token data is unavailable preserves the pre-v2.61.0 "any in init" behavior, so existing aura tests continue to pass.

| Test | What it asserts |
|------|-----------------|
| `test_aura_of_devotion_blocks_when_paladin_within_10_ft` | Caelan + Krieger 5 ft apart (1 cell on demo 70 px / 5 ft grid) → AoD range gate passes → Suggestion save-fail does NOT install Charmed, broadcast fires. |
| `test_aura_of_devotion_skips_when_paladin_outside_10_ft` | Caelan + Krieger 25 ft apart (5 cells) → AoD range gate skips → Charmed install proceeds, no broadcast. |

### `test_opportunity_attack.py`
v2.66.0 — F1 follow-ups: Aura conscious-check + Opportunity Attack trigger. `_paladin_is_conscious(char)` gates both `_aura_of_protection_bonus` and `_ally_has_aura_of_devotion` on `hp > 0 AND death_saves.status ∈ {alive, stable}`. `_check_opportunity_attack_triggers(...)` walks combatants on token move, detects from ≤ 5 ft → to > 5 ft transitions, and emits `feature_used(source="opportunity-attack-trigger")` for each provoked watcher whose reaction is available.

| Test | What it asserts |
|------|-----------------|
| `test_aura_of_protection_skips_when_paladin_unconscious` | Override Caelan to `dying` via `/death-save/override` → Thalindra Fireball at Pip → `base_expression="1d20"` (no +CHA from Caelan), no aura broadcast. |
| `test_oa_fires_when_mover_leaves_watcher_reach` | Krieger token 5 ft from Tavik (350,350 vs 420,350 on 70 px / 5 ft grid) moves to 25 ft (700,350) → move response carries `opportunity_attack_triggers` naming Tavik; `feature_used(source=opportunity-attack-trigger)` broadcast fires. |
| `test_oa_skips_when_watcher_reaction_used` | Tavik combatant seeded with `economy.reaction=True` → Krieger leaves reach → no OA trigger (RAW: needs reaction). |
| `test_oa_skips_when_move_starts_out_of_reach` | Krieger starts 25 ft from Tavik → moves further away → no OA trigger (no in-reach → out-of-reach transition). |
| `test_oa_honors_explicit_melee_reach_ft_override` | v2.66.1 — Tavik seeded with `melee_reach_ft=10` (glaive/halberd) → Krieger at 10 ft moves to 15 ft → OA fires past the 10 ft threshold; trigger carries `watcher_reach_ft=10.0`; broadcast `feature_desc` references "10 ft". |
| `test_oa_5ft_reach_still_skips_at_10ft_start` | Control for the reach override — same geometry without `melee_reach_ft` set → default 5 ft → no OA at 10 ft start. |
| `test_oa_npc_reach_parses_from_monster_action_desc` | v2.66.2 — Hill Giant TokenTemplate via SRD slug `hill-giant` (Greatclub desc contains "reach 10 ft.") → spawn token + seed battle with the giant 10 ft from Krieger → Krieger moves to 15 ft → OA fires with `watcher_reach_ft=10.0` parsed from action desc (no explicit override). |
| `test_oa_polearm_master_fires_on_enter_reach` | v2.66.4 — Tavik seeded with `polearm_master=True` + `melee_reach_ft=10` → Krieger moves from 15 ft to 10 ft → enter-reach OA fires with `trigger_type="enter"` + broadcast desc references "Polearm Master". |
| `test_oa_enter_reach_skips_without_polearm_master` | Control — same geometry, but Tavik has reach 10 ft without the Polearm Master flag → no enter-reach OA (only exit-reach fires for standard combatants). |
| `test_sentinel_fires_when_ally_attacks_target_near_watcher` | v2.66.5 — Tavik flagged with `sentinel=True`; placed 5 ft from Krieger. Krieger attacks Pip → `sentinel_triggers` lists Tavik + broadcast `feature_used(source=sentinel-attack-trigger)` desc references "Sentinel". |
| `test_sentinel_skips_when_watcher_is_the_target` | Control — Krieger attacks Tavik (the sentinel) directly → no trigger (RAW: watcher must not be the target). |
| `test_sentinel_skips_without_feat_flag` | Control — same geometry without the `sentinel` flag → no trigger. |
| `test_sentinel_fires_on_npc_attack` | v2.66.6 — Bandit NPC (SRD slug) spawned via TokenTemplate + `/npc_attack` against Pip, Tavik (sentinel) 5 ft from the bandit → response carries `sentinel_triggers` + broadcast desc names the bandit. |
| `test_oa_fires_for_npc_watcher_without_source_token_id` | v2.99.62 — bandit token + combatant with ONLY `token_template_id` + `name` (demo's `seed_encounter` shape — no `source_token_id`, no `char_id`) → Krieger moves out of reach → OA fires via the template+label Token-lookup fallback. Closes the demo "OA doesn't fire" regression. |
| `test_oa_chain_multi_npc_watchers_all_get_to_attack` | v2.99.64 — two bandit NPCs (Goon-A 5 ft east, Goon-B 5 ft south of Krieger) in the demo's exact combatant shape → drag Krieger out of both reaches in one move → 2 triggers, 1 head reaction_prompt, resolve head with `skip-oa` → 1 chained next prompt for the OTHER NPC. Regression-locks the v2.99.57 per-owner sub-queue chain for multi-NPC. |
| `test_oa_chain_multi_npc_take_the_oa_path` | v2.99.64 — parallel test that resolves the head by taking the OA → chain pop fires regardless of which reaction_key resolved the head. (v2.101.1: derives the resolve key from the prompt options — a picker `take-the-oa:{idx}` when the multi-attack NPC has one, else the generic key — per v2.99.68 fallback semantics.) |
| `test_preview_move_reports_over_range_beyond_speed` | v2.100.0 — GM over-range advisory. `preview_move` of a ~78.6 ft single drag returns `over_range: true` + `token_speed_ft > 0` + `distance_ft > token_speed_ft`, and leaves the token unmoved (read-only). |
| `test_preview_move_within_speed_not_over_range` | v2.100.0 — control: a ~7 ft drag returns `over_range: false` + `distance_ft <= token_speed_ft` so the GM client suppresses the popup. |

### `test_reaction_prompt.py`
v2.67.0 — Phase 1a of the reactions-automation plan (see [`docs/plans/reactions-automation.md`](plans/reactions-automation.md)). New `reaction_prompt` WS broadcast + `/api/campaign/{cid}/use_reaction` endpoint + in-memory `_active_reaction_prompts` registry with `prompt_id` replay guard. OA exit-reach (v2.66.0) retrofits to emit both the legacy `feature_used` advisory AND the new `reaction_prompt`. Schema v60 adds `users.reaction_prompt_mode`.

| Test | What it asserts |
|------|-----------------|
| `test_oa_exit_reach_emits_reaction_prompt` | Krieger leaves Tavik's 5 ft reach → `reaction_prompt` broadcast with `take-the-oa` option + the legacy `feature_used(source=opportunity-attack-trigger)` still fires (backward compat). |
| `test_use_reaction_marks_economy_and_resolves_prompt` | POST `/use_reaction` with the prompt_id + `reaction_key=take-the-oa` → 200, `reaction_prompt_resolved` broadcast fires, Tavik's `economy.reaction` flips to True. |
| `test_use_reaction_replay_guard` | Second POST with the same prompt_id → 409 `prompt_already_resolved`. |
| `test_use_reaction_unknown_prompt_id` | POST with a fake prompt_id → 409 `prompt_expired_or_unknown`. |
| `test_use_reaction_missing_prompt_id` | POST with no prompt_id → 400. |
| `test_reaction_prompt_mode_setting_valid` | v2.67.1 — POST `/api/settings/reaction_prompt_mode` with each of `popup` / `roll_log_only` / `off` → 200 + persisted. |
| `test_reaction_prompt_mode_setting_invalid` | Invalid mode → 400. |
| `test_uncanny_dodge_emits_reaction_prompt` | v2.67.2 — Phase 2a. NPC attacks Pip (Rogue Lv 5) for flat 6 → UD auto-halves to 3 AND emits `reaction_prompt(damage_taken)` with `uncanny-dodge-ack` option; ack POSTs cleanly resolve the prompt. |
| `test_use_reaction_marks_npc_economy_via_combatant_id` | v2.67.3 — spawn bandit NPC + Krieger 5 ft adjacent + move Krieger out of reach → OA prompt fires for the bandit → POST `/use_reaction` (no `watcher_char_id`) → bandit's `economy.reaction` flips True via `economy_update` carrying `combatant_id`. |
| `test_shield_prompt_fires_on_pc_hit` | v2.69.0 — Phase 3a. Bandit NPC swings at Thalindra (Wizard with Shield prepared + Lv 1 slot) until a hit lands → `reaction_prompt(attack_targeted)` fires with `cast-shield` option carrying class_slug + slot_level + AC preview in the label. |
| `test_cast_shield_consumes_slot_and_installs_buff` | v2.69.0 — POST `/use_reaction` with `reaction_key=cast-shield` after the prompt → 200, `economy_update` for Thalindra's reaction = True, `spell_slot_update` decrements the Lv 1 wizard slot, `feature_used(source=shield-cast)` broadcast, `buff_update` installs `shield-active` with `effects.ac_bonus=5` + `immune_magic_missile=True` + `duration_rounds=1`. |
| `test_counterspell_prompt_fires_on_pc_cast` | v2.70.0 — Phase 3b. Lyra (Bard 6 with Counterspell via Magical Secrets) casts Suggestion (L2) at Krieger while Thalindra (Wizard 5 with Counterspell + L3 slot) is positioned 5 ft from her on the active map → `reaction_prompt(spell_cast_near)` fires for Thalindra with `cast-counterspell` option whose `params.slot_level=3`, `params.spell_name="suggestion"`, `params.incoming_spell_level=2`. |
| `test_cast_counterspell_consumes_slot` | v2.70.0 — POST `/use_reaction` with `reaction_key=cast-counterspell` after the prompt → 200, `economy_update` for Thalindra's reaction = True, `spell_slot_update` decrements the L3 wizard slot, `feature_used(source=counterspell-cast)` broadcast with `outcome_hint="auto"` (L3 slot ≥ L2 incoming), `slot_level=3`, `countered_spell_name="suggestion"`. |
| `test_hellish_rebuke_prompt_fires_on_pc_damage` | v2.71.0 — Phase 3c. Krieger swings on Magnus (Warlock 5 w/ Hellish Rebuke + Pact L3 slot) until a hit lands; force `auto_apply_damage=on` via the campaign-settings form-post so `_apply_damage_to_combatant` runs (restored in finally) → `reaction_prompt(damage_taken)` fires for Magnus with `cast-hellish-rebuke` option. |
| `test_cast_hellish_rebuke_consumes_slot` | v2.71.0 — POST `/use_reaction` with `reaction_key=cast-hellish-rebuke` after the prompt → 200, `economy_update` for Magnus's reaction = True, `spell_slot_update` decrements his L3 Pact slot, `feature_used(source=hellish-rebuke-cast, damage_type=fire, damage_expr=4d10, slot_level=3)`. |
| `test_silvery_barbs_prompt_fires_on_save_pass` | v2.72.0 — Phase 3d. Krieger (Barbarian +7 STR save) rolls a DC 5 STR save via `/roll_request/{id}/respond` and trivially passes; Thalindra (Wizard 5 w/ Silvery Barbs from v2.72.0 demo seed + L1 slot) in the battle → `reaction_prompt(save_resolved)` fires for Thalindra with `cast-silvery-barbs` option whose `params.slot_level=1`, `params.target_name="Krieger Stonefist"`. The rolling character is excluded from being their own watcher. |
| `test_cast_silvery_barbs_consumes_slot` | v2.72.0 — POST `/use_reaction` with `reaction_key=cast-silvery-barbs` after the prompt → 200, `economy_update` for Thalindra's reaction = True, `spell_slot_update` decrements her L1 wizard slot, `feature_used(source=silvery-barbs-cast, slot_level=1, rerolled_target_name="Krieger Stonefist")`. |
| `test_npc_parry_prompt_fires_on_hit` | v2.73.0 — Phase 6. Krieger swings on a spawned Bandit Captain (forces `auto_apply_damage=on`) until a hit lands → `reaction_prompt(attack_targeted)` fires for the captain's combatant_id with `monster-parry` option built from `_monster_template_to_sheet(tmpl).actions[].category=="reaction"`. |
| `test_use_npc_parry_marks_reaction` | v2.73.0 — POST `/use_reaction` with `reaction_key=monster-parry` (no `watcher_char_id` for NPC) → 200, `economy_update` for the captain's reaction = True (via `combatant_id` key, not `character_id`), `feature_used(source=monster-reaction, action_name="Parry", monster_name~="Bandit Captain*")`. |
| `test_defensive_duelist_prompt_fires_on_pc_hit` | v2.74.0 — Phase 4a. Krieger swings on Lyra (Bard 6 with Defensive Duelist feat from v2.74.0 demo seed + Rapier equipped/finesse) until a hit lands → `reaction_prompt(attack_targeted)` fires for Lyra with `use-defensive-duelist` option whose `params.pb == 3` (Lyra's PB at Lv 6). |
| `test_use_defensive_duelist_marks_reaction` | v2.74.0 — POST `/use_reaction` with `reaction_key=use-defensive-duelist` after the prompt → 200, `economy_update` for Lyra's reaction = True, `feature_used(source=defensive-duelist, pb_bonus=3)`. |
| `test_mage_slayer_prompt_fires_on_spell_within_5ft` | v2.75.0 — Phase 4d. Magnus and Krieger placed 5 ft apart on the active map; Magnus casts Burning Hands at L3 → `reaction_prompt(spell_cast_near)` fires for Krieger (Mage Slayer feat from v2.75.0 demo seed + Greataxe equipped) with `take-mage-slayer-strike` option. |
| `test_use_mage_slayer_strike_marks_reaction` | v2.75.0 — POST `/use_reaction` with `reaction_key=take-mage-slayer-strike` after the prompt → 200, `economy_update` for Krieger's reaction = True, `feature_used(source=mage-slayer, caster_name="Magnus Hexbinder", spell_name="Burning Hands")`. |
| `test_war_caster_prompt_offers_cast_alongside_oa` | v2.76.0 — Phase 4c. Krieger leaves Tavik's reach (Tavik has War Caster feat from v2.76.0 demo seed + Cleric spells with `casting_time="1 action"`) → existing v2.66.0 `creature_exits_reach` prompt now includes BOTH `take-the-oa` AND `take-war-caster-cast` keys. |
| `test_use_war_caster_cast_marks_reaction` | v2.76.0 — POST `/use_reaction` with `reaction_key=take-war-caster-cast` after the prompt → 200, `economy_update` for Tavik's reaction = True, `feature_used(source=war-caster, provoker_name="Krieger Stonefist")`. |
| `test_lucky_prompt_fires_on_pc_hit` | v2.77.0 — Phase 4b. Krieger swings on Garrik (Fighter w/ Lucky feat + 3/3 Luck Points resource from v2.77.0 demo seed; long-rested in setup to ensure 3/3) until a hit lands → `reaction_prompt(attack_targeted)` fires for Garrik with `use-lucky` option whose `params.charges_before == 3`. |
| `test_use_lucky_decrements_charge` | v2.77.0 — POST `/use_reaction` with `reaction_key=use-lucky` after the prompt → 200, `economy_update` for Garrik's reaction = True, `feature_used(source=lucky, charges_after=2)` (resource decremented from 3 → 2 via in-place mutation of `sheet.resources[*].current`). |
| `test_item_reaction_prompt_includes_cloak_of_displacement` | v2.78.0 — Phase 5. Krieger swings on Lyra (Cloak of Displacement equipped from v2.78.0 demo seed + DD feat from v2.74.0) until a hit lands → `attack_targeted` prompt now includes BOTH `use-defensive-duelist` AND `item-cloak-displacement-advantage` keys. Generic `_pc_item_reactions_for_trigger` walker reads `sheet.inventory[*]._reactions[]`. |
| `test_use_item_reaction_marks_reaction` | v2.78.0 — POST `/use_reaction` with `reaction_key=item-cloak-displacement-advantage` after the prompt → 200, `economy_update` for Lyra's reaction = True, `feature_used(source=item-reaction, item_slug="cloak-of-displacement", item_name="Cloak of Displacement")`. Generic `item-*` dispatch — no per-item code required. |
| `test_uncanny_dodge_suppressed_when_dd_eligible` | v2.80.0 — PATCH Defensive Duelist onto Pip's feats; Krieger swings until a hit lands → assert NO `feature_used(source=uncanny-dodge)` auto-fire broadcast AND the `attack_targeted` prompt surfaces BOTH `cast-uncanny-dodge` AND `use-defensive-duelist`. Restores Pip's empty feats in finally. Closes the v2.74.0 filing for the Pip-vs-UD interaction. |
| `test_cast_uncanny_dodge_via_prompt_heals_back_half` | v2.80.0 — same PATCH-and-restore; POST `/use_reaction` with `cast-uncanny-dodge` → 200, `economy_update` for Pip's reaction = True, `character_hp_update(source=uncanny-dodge, delta=heal_back)` restores HP by `ceil(damage_applied / 2)`, `feature_used(source=uncanny-dodge, damage_applied, heal_back)`. |
| `test_protective_field_prompt_fires_on_pc_damage` | v2.118.0 — Phase 7. `garrik_psi_warrior` restore-safe fixture PATCHes Garrik into the Psi Warrior archetype (snapshots subclass + level via `sheet-json`, restores in finally). Krieger swings until a hit lands → `reaction_prompt(damage_taken)` fires for Garrik with `use-protective-field` option whose `params.die_size == 8` (Lv 9 → d8) + `params.target_combatant_id` matches the seeded combatant. |
| `test_use_protective_field_reduces_damage` | v2.118.0 — POST `/use_reaction` with `reaction_key=use-protective-field` after the prompt → 200, `economy_update` for Garrik's reaction = True, `feature_used(source=protective-field)` with `reduction>=1`, `psionic_die="1d8"`, `applied>=1` (the damaged combatant heals back by the reduction). |
| `test_riposte_prompt_fires_on_missed_attack` | v2.119.0 — Phase 7. `garrik_riposte_bm` restore-safe fixture PATCHes Garrik into Battle Master Lv 9 + a 4/4 Superiority Dice pool. Krieger swings on Garrik until a MISS lands → `reaction_prompt(attack_missed)` fires for Garrik with a `use-riposte:{idx}` option (one per melee weapon) whose `params.target_combatant_id` == Krieger's combatant + `params.die_size=="d8"`. |
| `test_use_riposte_resolves_counter_attack` | v2.119.0 — POST `/use_reaction` with the `use-riposte:{idx}` key after the prompt → 200, `economy_update` for Garrik's reaction = True, `resource_update(key=superiority-dice, current=3)` (die spent 4→3), `feature_used(source=riposte, attacked=True, extra_damage_on_hit>=1, dice_remaining=3)`. |
| `test_chronal_shift_prompt_fires_on_failed_save` | v2.120.0 — Phase 7. `thalindra_chronurgy` restore-safe fixture PATCHes Thalindra to Chronurgy Magic + a 2/2 Chronal Shift pool. Krieger FAILS a DC 30 STR save → `save_resolved` prompt fires for Thalindra with a `use-chronal-shift` option (works on any outcome) but NO `cast-silvery-barbs` (passed-gated, save failed). Option `params.target_combatant_id` == Krieger + `uses_before==2`. |
| `test_use_chronal_shift_decrements_uses` | v2.120.0 — POST `/use_reaction` with `reaction_key=use-chronal-shift` after the prompt → 200, `economy_update` for Thalindra's reaction = True, `resource_update(key=chronal-shift, current=1)` (use spent 2→1), `feature_used(source=chronal-shift, uses_remaining=1)`. |
| `test_protective_field_ally_prompt_fires_for_nearby_psi_warrior` | v2.121.0 — Phase 7. Garrik (patched Psi Warrior, `garrik_psi_warrior` fixture) placed one cell from Tavik on the active map; Krieger hits Tavik → `_emit_protective_field_ally_prompts` walker fires `reaction_prompt(ally_damaged_near)` for Garrik with a `use-protective-field` option whose `params.target_combatant_id` is **Tavik's** combatant (the damaged ally) + `die_size==8`. |
| `test_use_protective_field_heals_damaged_ally` | v2.121.0 — POST `/use_reaction` with `use-protective-field` after the ally prompt → 200, `economy_update` for Garrik's reaction = True, `feature_used(source=protective-field, reduction>=1, applied>=1)` (Garrik shields, Tavik heals back). |

### `test_gm_reactions_panel.py`
v2.68.0 — GM Reactions Panel (see [`docs/plans/reactions-automation.md`](plans/reactions-automation.md)). New `GET /available_reactions` + `POST /spend_reaction_manual` endpoints surface every combatant's reaction catalog to the GM and let the GM flip any reaction chip with one click. PC class features (Uncanny Dodge / Cutting Words / Indomitable), PC feats (Sentinel / Polearm Master / etc.), PC reaction spells (Shield / Counterspell / etc. via `casting_time` scan), NPC monster reactions (Parry / etc. via `category == "reaction"` walk).

| Test | What it asserts |
|------|-----------------|
| `test_available_reactions_lists_pc_class_features` | Pip (Rogue Lv 7) catalog contains `uncanny-dodge` + `reaction_used: false`. |
| `test_available_reactions_lists_npc_monster_reaction` | Bandit Captain TokenTemplate spawned + added to init → catalog includes at least one `monster-*` keyed reaction (Parry). |
| `test_spend_reaction_manual_pc` | POST `/spend_reaction_manual` for Pip's uncanny-dodge → 200, `economy_update` for Pip's reaction = True, `feature_used(source=manual-reaction)` broadcast. |
| `test_spend_reaction_manual_already_used` | Pip with `economy.reaction=True` seeded → 409 `reaction_already_used`. |
| `test_spend_reaction_manual_unknown_key` | POST with a bogus reaction_key → 400 `unknown_reaction_key`. |
| `test_available_reactions_gm_only` | alice_client (non-GM) GET → 403. |
| `test_spend_reaction_manual_gm_only` | alice_client (non-GM) POST → 403. |

### `test_use_countercharm.py`
v2.54.0 — Bard Lv 6+ Countercharm. First condition-gated save aura (only fires on spells installing charmed/frightened, not all saves). `/use_countercharm` installs a 1-round self-buff; `_ally_has_countercharm_active` reads it on save-roll construction; gate on `_SPELL_CONDITION_MAP[slug].key ∈ {charmed, frightened}` via `_spell_installs_countercharmed_condition`. Same commit adds `suggestion → Charmed` to the map.

| Test | What it asserts |
|------|-----------------|
| `test_use_countercharm_installs_buff` | POST `/use_countercharm` → 200, `buff_installed=True`, `duration_rounds=1`, `feature_used(source=countercharm)` broadcast. |
| `test_countercharm_grants_advantage_on_charm_save` | Lyra activates Countercharm then casts Suggestion at Krieger → `roll_request.base_expression="2d20kh1"` + Countercharm broadcast for Lyra. |
| `test_countercharm_skips_without_active_buff` | Control: no buff → Suggestion at Krieger → `base_expression="1d20"`; no broadcast. |
| `test_countercharm_skips_wrong_condition_spell` | Lyra DOES activate, but casts Hold Person (Paralyzed, not Charmed/Frightened) → `base_expression="1d20"`; gate is condition-keyed not save-ability-keyed. |
| `test_use_countercharm_wrong_class` | Pip (Rogue) → 409 `wrong_class` with `expected=bard`. |

### `test_aura_of_protection.py`
v2.53.0 — Paladin Lv 6+ Aura of Protection. First ally-conferred save-bonus mechanic. `_aura_of_protection_bonus(db, campaign_id, saving_char_id)` returns the CHA mod of the highest-CHA Paladin Lv 6+ in init (min +1 per RAW); 0 when no paladin qualifies or saver isn't in battle. Bonus appended to `base_expression` at roll_request creation time; same hook as Danger Sense.

| Test | What it asserts |
|------|-----------------|
| `test_aura_of_protection_grants_bonus_to_ally_save` | Caelan + Pip both in init; Thalindra casts Fireball at Pip → roll_request `base_expression == "1d20+3"` (Caelan CHA 16 → +3 mod) and feature_used(source=aura-of-protection) broadcast names Caelan. |
| `test_aura_skips_when_paladin_absent` | Control: Caelan NOT in init → `base_expression == "1d20"` (no bonus); no Aura broadcast. |
| `test_paladin_own_aura_applies_to_self` | Fireball at Caelan himself → his own aura applies (`base_expression == "1d20+3"`); broadcast still names Caelan. |

### `test_danger_sense.py`
v2.52.0 — Barbarian Lv 2+ Danger Sense. First save-roll advantage intercept; `_pc_has_danger_sense_on_dex_save(char, save_ability)` flips the d20 expression to `2d20kh1` on Dex saves. Wired into `/place_aoe` PC branch + `/cast_spell` single + AoE PC save roll_request creation. Broadcasts `feature_used` with `source: "danger-sense"`.

| Test | What it asserts |
|------|-----------------|
| `test_danger_sense_advantage_on_dex_save` | Thalindra casts Fireball at Krieger (Barbarian 5) → the roll_request broadcast carries `base_expression="2d20kh1"` AND a `feature_used(source=danger-sense)` broadcast fires for Krieger. |
| `test_danger_sense_skips_non_barbarian` | Control: Thalindra casts Fireball at Pip (Rogue 7) → `base_expression="1d20"` (no kh1); no Danger Sense broadcast. |
| `test_danger_sense_skips_non_dex_save` | Tavik casts Hold Person (WIS save) at Krieger → `base_expression="1d20"`; Danger Sense is Dex-only. |

### `test_race_save_advantage.py`
v2.99.11–v2.99.12 — (D) Phase 2 race-keyed save advantage. `_race_grants_save_advantage(sheet, save_ability, spell_slug, damage_type, is_spell_save)` returns `(applies, trait_slug, trait_name)` based on the curated `_RACE_SAVE_ADVANTAGES` table. Entries: Fey Ancestry (Elf / Half-Elf) advantage on saves vs charm install; Gnome Cunning (Rock / Forest Gnome) advantage on INT/WIS/CHA saves from spells; Dwarven Resilience (Hill / Mountain Dwarf) advantage on saves vs poison damage OR poisoned-condition install (v2.99.12 — adds `damage_types` field + `_save_damage_type_from_spell` helper + OR semantics between condition_keys and damage_types). Wired into all 3 save-roll construction sites (single-target PC save, AoE PC save, `/place_aoe` server-rolled save). Broadcasts `feature_used` with `source: <trait_slug>`.

| Test | What it asserts |
|------|-----------------|
| `test_fey_ancestry_advantage_on_charm_save` | Lyra (Half-Elf Bard) casts Suggestion at Thalindra (Elf Wizard) → Wis save, Suggestion installs Charmed → `base_expression="2d20kh1"` AND `feature_used(source=fey-ancestry)` broadcast fires for Thalindra. |
| `test_fey_ancestry_skips_non_charm_save` | Control: Lyra casts Hold Person at Thalindra → Wis save, Paralyzed install (not Charmed) → `base_expression="1d20"`; no Fey Ancestry broadcast. |
| `test_fey_ancestry_skips_non_fey_race` | Control: Lyra casts Suggestion at Tavik (Hill Dwarf Cleric) → Wis save vs Charmed but Tavik isn't Elf/Half-Elf → `base_expression="1d20"`; no Fey Ancestry broadcast. |
| `test_dwarven_resilience_advantage_on_poison_save` | Thalindra (Elf Wizard) casts Poison Spray (CON save, poison damage) at Tavik (Hill Dwarf Cleric) → Dwarven Resilience fires → `base_expression="2d20kh1"` AND `feature_used(source=dwarven-resilience)` broadcast fires for Tavik. |
| `test_dwarven_resilience_skips_non_poison_save` | Control: Fireball (Dex save, fire damage) at Tavik → Dwarven Resilience doesn't fire (poison-only) → `base_expression="1d20"`; no broadcast. |
| `test_dwarven_resilience_skips_non_dwarf_race` | Control: Poison Spray at Thalindra herself (Elf) → Dwarven Resilience doesn't fire (Elf, not Dwarf) → `base_expression="1d20"`; no broadcast. |
| `test_halfling_brave_advantage_on_fright_save` | Lyra casts Fear at Pip (Halfling Rogue) → Wis save vs Frightened install → Halfling Brave fires → `base_expression="2d20kh1"` AND `feature_used(source=halfling-brave)` broadcast for Pip. |
| `test_halfling_brave_skips_non_fright_save` | Control: Lyra casts Suggestion (Charmed install) at Pip → Halfling Brave doesn't fire (gates on Frightened only); `base_expression="1d20"`. |
| `test_halfling_brave_skips_non_halfling` | Control: Lyra casts Fear at Thalindra (Elf) → no Halfling Brave broadcast (race gate). |

### `test_halfling_lucky.py`
v2.99.13 — Halfling Lucky race-trait reroll-on-natural-1 (save-roll surface). Distinct from the v2.77.0 Lucky FEAT — Halfling Lucky is unlimited, auto-fire, only triggers on natural 1. Post-result intercept in `respond_roll_request`: after `dice_mod.roll`, if `_extract_kept_d20_from_breakdown(result.breakdown) == 1` AND the rolling PC is a Halfling, reroll the full expression once. Broadcasts `feature_used` with `source: "halfling-lucky"`. Roll note carries "🍀 Lucky reroll d20 1 → N". Uses `/api/test/dice/seed` TEST_MODE endpoint for deterministic d20=1 forcing.

| Test | What it asserts |
|------|-----------------|
| `test_halfling_lucky_rerolls_on_natural_one` | Pip (Halfling Rogue) saves vs Suggestion; seed forces d20=1 → server rerolls → roll note contains "Lucky reroll d20 1 →" AND `feature_used(source=halfling-lucky)` broadcast fires for Pip. |
| `test_halfling_lucky_skips_non_halfling` | Control: Thalindra (Elf Wizard) with seeded d20=1 → no reroll, no Lucky note, no broadcast (race trait gates on Halfling slug). |
| `test_halfling_lucky_skips_non_natural_one` | Control: Pip with d20 ≥ 10 → no reroll, no broadcast (trait only fires on natural 1). |
| `test_halfling_lucky_rerolls_on_attack_natural_one` | v2.99.21 attack-roll surface. Pip attacks a Bandit with seeded d20=1 → server rerolls + `feature_used(source=halfling-lucky)` broadcast fires for Pip. |
| `test_halfling_lucky_attack_skips_non_halfling` | Control: Garrik (Variant Human) attacks with seeded d20=1 → no reroll, no broadcast. |
| `test_halfling_lucky_rerolls_on_check_natural_one` | v2.99.22 check-roll surface. Pip rolls `1d20+4` (Stealth-shaped) with seeded d20=1 → server rerolls; `feature_used(source=halfling-lucky)` broadcast + Lucky note in the roll log. |
| `test_halfling_lucky_check_skips_non_halfling` | Control: Garrik rolls `1d20+4` with seeded d20=1 → no reroll, no broadcast. |

### `test_use_save_evasion.py`
v2.51.5 — Monk Lv 7+ (and Rogue Lv 7+) Evasion. Server-side intercept of save-for-half Dex-save damage via `_apply_evasion_to_dex_save_damage` (wired into all 7 save-damage call sites). With Evasion: save → 0, fail → half. Without: standard save → half, fail → full. Broadcasts `feature_used` with `source: "evasion"` on every fire (both branches).

| Test | What it asserts |
|------|-----------------|
| `test_evasion_save_success_zero_damage` | Thalindra casts Fireball at [bandit, Kael (Monk 7)] via AoE; loop until Kael's Dex save passes → `damage_applied == 0` and feature_used(source=evasion) broadcast fires. |
| `test_evasion_save_fail_half_damage` | Same setup; loop until Kael's save fails → `damage_applied` in 8d6's half range (4-24) and the Evasion broadcast still fires on the fail branch. |
| `test_evasion_rogue_save_success_zero_damage` | v2.51.6: Pip (Rogue Lv 7 post-bump) — Fireball at [bandit, Pip], loop until save passes → `damage_applied == 0` + feature_used(source=evasion) for Pip. Proves the helper recognizes Rogue Lv 7+ alongside Monk Lv 7+. |
| `test_non_monk7_target_standard_save_for_half` | Control: Tavik (Cleric 5, no Evasion) on save success → standard half damage (not zero); no Evasion broadcast. |

### `test_use_attack_uncanny_dodge.py`
v2.49.243 — Rogue Lv 5+ passive reaction. Server-side halving wired into `_apply_damage_to_combatant` via the new `is_attack=True` kwarg + `_target_uses_uncanny_dodge` helper. Auto-fires on the first incoming attack each round; reaction-gated (a second swing in the same round takes full damage); RAW save-spell paths intentionally don't trigger.

| Test | What it asserts |
|------|-----------------|
| `test_uncanny_dodge_halves_first_attack` | `/npc_attack` Bandit hits Pip (Rogue 5) for flat 6 damage → `damage_applied == 3`, Pip's reaction chip flips on, `feature_used` broadcast carries `source=uncanny-dodge` and Pip's name. |
| `test_uncanny_dodge_only_once_per_round` | Second swing in the same round → `damage_applied == 6` (reaction already used; no halving). |
| `test_non_rogue_target_no_halving` | Control: Bandit hits Garrik (Fighter) for flat 6 → `damage_applied == 6`, Garrik's reaction chip stays unflipped. |
| `test_save_spell_does_not_trigger_uncanny_dodge` | `/npc_cast_spell` Sacred Flame DEX save against Pip → Pip's reaction chip stays unflipped (RAW: UD only fires on attack rolls, not on save spells). |

### `test_use_open_hand_technique.py`
v2.49.57 — Monk subclass feature `POST /use_open_hand_technique` (Way of the Open Hand, Lv 3+). Three modes: `prone` (DEX save → Prone via new `open-hand-prone` map entry), `push` (STR save → response carries `push_authorized` for the GM to drag the token; no buff), `no_reactions` (no save → inline install of `reaction-denied` buff). No ki cost — RAW the Flurry of Blows already paid. Same trust-the-caller convention as Stunning Strike for the "must follow a Flurry hit" gate.

| Test | What it asserts |
|------|-----------------|
| `test_open_hand_prone_happy_path_npc` | Kael uses prone on a bandit; retry until DEX save fails; assert `auto_save_buff_installed=Prone`, `concentration=False` on the broadcast buff, `source_char_id=Kael`. |
| `test_open_hand_push_npc` | Kael uses push on a bandit; assert `push_authorized` is the boolean inverse of `auto_save_passed`. No buff installed either way. |
| `test_open_hand_push_moves_target_on_failed_save` | v2.99.434 — Phase 6.3. Kael (placed above the bandit) loops until the bandit fails its STR save, then asserts `push_applied` is True + the bandit's real NPC token moved +210 px (3 cells / 15 ft) via `_force_move`; a passed save moves nothing. NPC token created via `POST /tokens` (linked as `source_token_id`) + torn down at the end. |
| `test_open_hand_no_reactions_npc` | Kael uses no_reactions on a bandit; assert `buff_installed=No Reactions (Open Hand)`, `reaction-denied` key on the bandit's buff list, `duration_rounds=1`, no `auto_save_prompted`. |
| `test_open_hand_wrong_class` | Krieger (Barbarian) → 409 `wrong_class` with `expected=monk`. |
| `test_open_hand_bad_mode` | Invalid `mode` string → 400. |
| `test_open_hand_prone_pc_installs_prone` | v2.49.65 — closes the v2.49.57 filed item. Magnus pre-cast Hex (concentrating); Kael uses Open Hand prone on Magnus → roll_request; GM-as-Magnus /responds; on save fail assert (a) Prone lands, (b) Magnus's Hex SURVIVES (Prone isn't in `_INCAPACITATING_BUFF_KEYS` — regression guard that the v2.49.51 hook does NOT fire for non-incapacitating condition buffs). Retry loop on DEX save. |
| `test_open_hand_push_pc_no_buff` | v2.49.65 — push PC path. Kael shoves Magnus → roll_request; GM responds → assert `auto_buff_installed=""` (no `_SPELL_CONDITION_MAP` entry for `open-hand-push`); Magnus's buff list carries no prone / no reaction-denied. Both deterministic (no save-outcome dependency). |
| `test_open_hand_no_reactions_pc` | v2.49.65 — no_reactions PC path. Inline `_install_buff` of `reaction-denied`; verify it lands in BOTH hub and sheet mirror; 🫷 public log names Kael + Magnus. |

### `test_swap_preserves_paired_buffs.py`
v2.49.54 — closes the bug filed in v2.49.53. The swap loop in `_install_buff` no longer drops `concentration: True` buffs sourced by another caster. RAW: the one-concentration-at-a-time rule applies only to the combatant's OWN concentration spells; a paired condition (e.g. Paralyzed on a Hold Person victim) is sustained by the SOURCE caster and must persist independently.

| Test | What it asserts |
|------|-----------------|
| `test_paired_buff_preserved_when_caster_swaps` | Magnus pre-seeded with Paralyzed (source=99999 enemy). Cast Hex → Paralyzed PRESERVED + Hex installed. Pre-fix the swap loop wrongly dropped Paralyzed. |
| `test_own_anchor_swap_still_works` | Regression guard: own anchor (concentration-bless, source=Magnus) is STILL replaced by Hex. The source filter must not over-broaden. |

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

### `test_battle.py`
v2.101.0 — battle hub persistence + the new `GET /api/campaign/{id}/battle` endpoint. The hub is now a write-through cache over the `battles` table; the GET reads the persisted row from the DB.

| Test | What it asserts |
|------|-----------------|
| `test_battle_put_persists_and_get_round_trips` | PUT a battle (Pip combatant, active, round 1) → 200 `{"ok": True}`; GET returns `{"battle": {...}}` from the DB with `active=True`, `round=1`, and the seeded combatant; a fresh WS connect replays the state as a `battle_update`. |
| `test_battle_put_requires_gm` | A non-GM player's `PUT /battle` → 403 (the write gate the viewer-readable GET deliberately doesn't share). |

### `test_movement_lock.py`
v2.102.0 — campaign movement lock (Phase 1 server core) + v2.104.0 Phase 3 request/approve flow. GM toggles `campaign.movement_locked` via `POST /movement_lock`; non-GM `/token/move` drags are gated 409 while locked; players request a one-token unlock via `POST /movement_request`, the GM approves/denies via `/movement_request/{id}/respond`.

| Test | What it asserts |
|------|-----------------|
| `test_movement_lock_blocks_player_gm_passes` | GM `POST /movement_lock {locked:true}` → 200 `{ok, locked:true}` + a `movement_lock_update(locked=true)` broadcast; alice's drag of Pip → 409 `movement_locked` (with `token_id`); the GM's drag of the same token → 200 (arbiter); unlocking restores alice's move to 200. Unlocks in a `finally` so a failure doesn't strand the campaign locked. |
| `test_movement_lock_requires_gm` | A non-GM player's `POST /movement_lock` → 403. |
| `test_movement_request_approve_grants_one_move` | While locked, alice `POST /movement_request {token_id}` → 200 `{ok, request_id}` + GM `movement_request` broadcast (request_id / token_id / character_id); GM `respond {approved:true}` → 200 + alice `movement_request_resolved(approved, requester_user_id)`; the one-shot grant lets her FIRST locked drag 200, the SECOND 409 `movement_locked`. |
| `test_movement_request_deny_keeps_player_blocked` | GM `respond {approved:false}` → 200; alice's drag stays 409 (no grant issued). |
| `test_movement_request_unknown_token` | `movement_request` for a token not in this campaign → 404. |
| `test_respond_movement_request_requires_gm` | Non-GM `respond` → 403 (GM gate fires before the request lookup). |
| `test_respond_unknown_movement_request` | GM `respond` on an unknown/expired request id → 404. |

### `test_use_reroll.py`
v2.105.0 — generic reroll framework (Phase 1: Lucky feat). `POST /use_reroll` spends a reroll feature to reroll a roll-log card's d20; the `/roll` broadcast carries `reroll_options`. Uses demo Fighter Garrik Ironside (Lucky feat + 3 luck points).

| Test | What it asserts |
|------|-----------------|
| `test_lucky_reroll_keeps_better_and_decrements` | A d20 rolled as Garrik broadcasts a `lucky` reroll_option (`remaining=3`, `keep="better"`); `POST /use_reroll {feature_key:"lucky"}` → 200, decrements 3→2, kept d20 ≥ original (swaps in only when the new d20 strictly beats it), and fires `roll(reroll_feature="lucky")` + `feature_used(source="lucky-reroll")` + `resource_update(key="lucky", current=2)`. |
| `test_reroll_unknown_feature` | An unknown `feature_key` → 404 `unknown_feature` (checked before the roll lookup). |
| `test_reroll_feature_not_available` | A character without the feature (Pip) → 409 `out_of_uses`. |
| `test_reroll_no_d20` | A non-d20 roll (`2d6`) offers no reroll_option and `/use_reroll` → 409 `no_d20`. |
| `test_save_offers_lucky_and_indomitable_and_indomitable_takes_new` | v2.107.0 — a Lv 9 Fighter's SAVE roll (`stat_key="wis_save"`) offers both `lucky` (any) and `indomitable` (save-only); `/use_reroll {feature_key:"indomitable"}` → `took_new=True` (keep="new") + resource decrements 1→0. |
| `test_indomitable_hidden_on_non_save` | v2.107.0 — a non-save d20 for the same Fighter offers `lucky` but NOT the save-only `indomitable` (applies-gating). |

### `test_battle_put_npc_concentration_cascade.py`
v2.99.185 — `/battle PUT` auto-fires `_drop_paired_concentration_buffs_npc` when an NPC's concentration buff is removed via the canonical battle-edit path. Closes the v2.99.179 filed item; completes the Polymorph mechanical chain for NPC casters via the routine UI path.

| Test | What it asserts |
|------|-----------------|
| `test_battle_put_drops_npc_concentration_buffs` | Seed NPC with `concentration-polymorph` buff + Krieger with a `polymorph-active` marker sourced from the NPC. `/battle PUT` with the NPC's concentration buff removed → the NPC-mirror cascade fires + the v2.99.172 revert hook drops Krieger's polymorph-active marker. |

### `test_battle_put_pc_concentration_cascade.py`
v2.99.191 — PC mirror of v2.99.185. `/battle PUT` auto-fires `_drop_paired_concentration_buffs` when a PC's concentration buff is removed via the canonical battle-edit path. Closes the `/battle PUT` parallel for PC casters (PC `/end_buff` was already covered by `_remove_buff`'s cascade hook).

| Test | What it asserts |
|------|-----------------|
| `test_battle_put_drops_pc_paired_buffs` | Seed Magnus with `concentration-hold-person` + Krieger with paired Paralyzed (`source_char_id=Magnus`, `_dependent_on_caster_concentration=True`). `/battle PUT` with Magnus's concentration removed → PC cascade fires → Krieger's Paralyzed is dropped from his sheet mirror. |

### `test_npc_cast_subtle_immune.py`
v2.99.186 — `/npc_cast_spell` mirrors the PC Subtle gate. Closes a v2.99.173 filed item; an NPC carrying `metamagic-subtle-pending` on its combatant suppresses the Counterspell prompt the same way a PC caster does.

| Test | What it asserts |
|------|-----------------|
| `test_npc_cast_subtle_suppresses_counterspell_prompt` | Seed a synthetic NPC with `metamagic-subtle-pending` on its combatant + Thalindra (Counterspell on sheet) as a PC watcher. `/npc_cast_spell` → cast payload carries `was_subtle: True`, the 🤫 `metamagic-subtle-spell-consumed` `feature_used` fires, and no `reaction_prompt(spell_cast_near)` is emitted for the cast. |

### `test_hunters_mark_twinned_install.py`
v2.99.187 — `/cast_hunters_mark` folds the Twinned second target into the installed buff's rider field (`effects.weapon_hit_bonus_target_combatant_id`), not just the response. The weapon-hit rider consumer at line ~21498 accepts list-or-string.

| Test | What it asserts |
|------|-----------------|
| `test_hunters_mark_twinned_installs_list_rider` | Rowan casts Hunter's Mark with Twinned armed + a second target seeded. Response carries `twinned_target_combatant_id_2`; Rowan's installed `hunters-mark` buff carries a list-shape `effects.weapon_hit_bonus_target_combatant_id` containing both targets + a top-level `target_combatant_ids` list mirroring both. |
| `test_hunters_mark_no_twinned_keeps_single_rider` | Control: cast Hunter's Mark with no Twinned pending. The buff's `effects.weapon_hit_bonus_target_combatant_id` remains a single string (backward compat with pre-v2.99.187 serialized buffs + `/cast_hex`'s still-singular field). |

### `test_hunters_mark_twinned_broadcast.py`
v2.99.188 — `/cast_hunters_mark` install broadcast names both targets when Twinned fires + stamps the weapon-hit rider with `vs_combatant_id` for downstream attack-chat-card labeling.

| Test | What it asserts |
|------|-----------------|
| `test_twinned_install_broadcast_names_both_targets` | Rowan casts Hunter's Mark with Twinned armed. The `feature_used` install broadcast's `feature_name` + `feature_desc` mention both targets, and the new metadata fields fire: `target_names` is a 2-element list, `twinned_target_combatant_id_2` matches the second target ID, `twinned_target_name` resolves to the second target's display name. |
| `test_no_twinned_broadcast_keeps_single_target` | Control: cast without Twinned pending. The install broadcast keeps the single-target shape — `target_names` is a singleton, `twinned_target_combatant_id_2` + `twinned_target_name` are falsy. |

### `test_hex_twinned_install.py`
v2.99.189 — `/cast_hex` adopts the v2.99.187/.188 Hunter's Mark pattern: per-target install when Twinned fires + chat-card naming both targets.

| Test | What it asserts |
|------|-----------------|
| `test_hex_twinned_install_list_rider_and_broadcast` | Magnus Hexbinder casts Hex with Twinned armed + a synthetic "Cursed Cultist" as the second target. The installed Hex buff carries a list-shape `effects.weapon_hit_bonus_target_combatant_id` containing both targets + a `target_combatant_ids` list mirroring both. The install `feature_used` broadcast's `feature_name` + `feature_desc` mention both targets; `target_names` lists both; `twinned_target_combatant_id_2` + `twinned_target_name` are populated. |
| `test_hex_no_twinned_keeps_single_target` | Control: Magnus casts Hex without Twinned pending. The buff's rider remains a single string; the install broadcast keeps single-target shape (`target_names` is a singleton, `twinned_target_*` fields are falsy). |

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

## Content parsers (unit tests)

Pure-Python unit tests that don't need the docker stack or any HTTP / WS fixture. Hosted under `tests/harness/` so the CI workflow picks them up alongside the harness tests; the parser modules live under `app/content/`.

### `test_range_parser.py`
v2.49.74 — Phase 2B of the ruler/range plan. Tests `app/content/range_parser.py`'s `parse_range_ft` + `max_range_ft`.

| Test | What it asserts |
|------|-----------------|
| `test_self_returns_zero` | `"Self"` (in any casing / whitespace) → 0. Self-range spells skip the range check. |
| `test_self_with_radius_returns_zero` | `"Self (30-foot radius)"` etc. → 0 (radius is an AoE concern, not the cast-range gate). |
| `test_touch_returns_five` | `"Touch"` → 5 (RAW melee reach). |
| `test_single_feet_band` | `"5 feet"` / `"30 feet"` … `"500 feet"` → int. |
| `test_feet_abbreviation` | `"5 ft"` / `"60 ft"` / `"120 ft"` → int (weapons use the abbreviation). |
| `test_feet_alt_spellings` | `"5 foot"` / `"5 feet."` / `"60 ft."` → int. |
| `test_thrown_weapon_range` | `"20/60 feet"` → `(20, 60)` etc. |
| `test_thrown_abbreviated` | `"30/120 ft"` → `(30, 120)` (the demo's javelin / hand-crossbow shape). |
| `test_mile_scale` | `"1 mile"` → 5280, `"5 miles"` → 26400, `"500 miles"` → 2640000. |
| `test_skip_strings_return_none` | `"Special"` / `"Unlimited"` / `"Sight"` → None — caller skips the range check. |
| `test_empty_inputs_return_none` | `""` / `"   "` / `None` → None. |
| `test_garbage_returns_none` | `"not a range"` / `"60"` (no unit) / `"60 leagues"` → None. Robust to unparseable content. |
| `test_max_range_passthrough_int` | `max_range_ft(60)` → 60. |
| `test_max_range_collapses_thrown` | `max_range_ft((20, 60))` → 60 (uses long range for "is target reachable at all"). |
| `test_max_range_none_passthrough` | `max_range_ft(None)` → None. |
| `test_combined_pipeline` | End-to-end: parse a string then collapse to a single int. |
| `test_srd_spell_ranges` (parametrized, 17 cases) | Pins every unique range string surveyed from `app/data/local/dnd5e/spells/*.json` against its expected ft. SRD content drift fails this test rather than silently breaking range enforcement. |

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
| `test_wiki_doc_serves_ruler_plan` | v2.49.66: `GET /wiki/doc/plan-ruler-and-range` → 200, body contains "ruler" + "range" + the nav menu. Resolves through the allowlist to `docs/plans/ruler-and-range.md`. |
| `test_wiki_doc_serves_simulacrum_plan` | v2.49.68: `GET /wiki/doc/plan-player-simulacrum` → 200, body contains "simulacrum" + the nav menu. Resolves through the allowlist to `docs/plans/player-simulacrum.md`. |
| `test_wiki_doc_serves_root_doc` | v2.49.9: `GET /wiki/doc/claude` → 200, body contains CLAUDE.md's H1 ("Claude Code guidelines") + the nav menu. Resolves through the allowlist to the repo-root `CLAUDE.md`. |
| `test_wiki_doc_serves_automation_coverage` | v2.99.447: `GET /wiki/doc/automation-coverage` → 200, body contains "automation coverage" + the nav menu. Resolves through the allowlist to `docs/automation-coverage.md` (the Phase 0 audit doc). |
| `test_wiki_doc_unknown_slug_404` | v2.49.9: a slug that isn't in `_DOC_ALLOWLIST` → 404. Important security guarantee — the allowlist is the only way to reach a file outside `docs/wiki/`. |
| `test_wiki_doc_traversal_blocked` | v2.49.9: directory-traversal characters in the doc slug → 404 / 400, rejected by the slug guard before the allowlist lookup. |

---

## Mini-sheet partials (Phase 2.6 — v2.49.200)

Regression net for the v2.49.193–.198 per-tab partial extractions from `_mini_sheet_card.html` (Mockup B Phase 2 of [`docs/plans/unified-mini-sheet.md`](../plans/unified-mini-sheet.md)). Loads the demo campaign tabletop page (`GET /campaign/1`) and asserts that the four per-tab partials (`_tab_actions.html`, `_tab_spells.html`, `_tab_skills.html`, `_tab_features.html`) still produce their expected markup when iterated from the unified `_tabs_present` list. Tests live in `tests/harness/test_mini_sheet_partials.py`. NPC mini-sheets are still rendered client-side via `buildMonsterInitSheet` — Phase 2.5's NPC body swap will add matching coverage.

| Test | What it asserts |
|------|-----------------|
| `test_tabletop_renders_all_demo_pc_mini_sheets` | `GET /campaign/1` → 200; all 12 demo PCs' `.mini-header-name` blocks present in the response. A single Jinja error in any sub-partial would 500 the page; this test fails fast. |
| `test_tab_strip_renders_per_tabs_present_list` | Phase 2.4: Zara Emberfire (Sorcerer 5) renders all four tab buttons (`data-tab="attacks"` "Actions" / `"spells"` "Spells" / `"features"` "Features" / `"skills"` "Skills") in the documented order. Validates the `_tabs_present` iteration emits the right `{panel, label}` pairs for a full caster. |
| `test_actions_panel_renders_when_attacks_present` | Phase 2.1: Pip Quickfingers (Rogue) renders the `data-panel="attacks"` panel with at least one `.mini-attack-row` + a `🗡 Strike` button — the partial's tell-tale markup. |
| `test_spells_panel_renders_for_caster_with_slots` | Phase 2.2: Zara renders the `data-panel="spells"` panel with at least one `.mini-spell-row` + `✨ Cast` button + a `.mini-slot-row` slot-pip bar (level ≥ 1 spell present). Validates the multiclass loop + slot-pip rendering in `_tab_spells.html`. |
| `test_skills_panel_renders_all_18_skills` | Phase 2.3: Pip's `data-panel="skills"` contains exactly 18 `.mini-sk-btn` buttons — the `SKILLS_LIST` constant inside `_tab_skills.html` produces the full standard 5e skill grid for every PC. |
| `test_features_panel_renders_for_pc_with_class_features` | Phase 2.3b: at least one PC in the demo roster renders the `data-panel="features"` panel with `.mini-feature-row` + `🪄 Use` button. `_features_list` is the per-character gate; the assertion doesn't hardcode which PC since the demo seed gives every PHB class some class-feature entries. |
| `test_monster_card_pool_renders_for_gm` | Phase 2.5a (v2.49.202): GM sees a hidden `#monster-card-pool` div with at least one `#char-detail-monster-template-{tid}` child per dnd5e TokenTemplate. Canary asserts the `-template-` infix is preserved — the existing `hasCharDetail` lookup matches `char-detail-monster-{tid}` (no infix), so any commit that accidentally drops the infix would activate the legacy `buildMonsterInitSheet` hoist for the first combatant of each template + break multi-combatant cases. |
| `test_monster_card_pool_hidden_from_players` | Phase 2.5a: non-GM users (alice) don't see the pool div in their page DOM at all. NPC sheet data is GM-only. |
| `test_monster_card_pool_partial_renders_for_dnd5e_monster` | Phase 2.5a: the partial doesn't crash on `is_monster=True` against a monster sheet shape (no `classes` / `hit_dice` / etc.). Anchors on the first monster-template card, asserts the 100 KB window contains a `.mini-tabs` block + Skills tab + at least one `.mini-sk-btn` — i.e., the unified `_tabs_present` iteration produced output, `_tab_skills.html` ran against the monster's abilities dict + 18-skill grid emitted buttons. |
| `test_renderbattle_wires_hydration_helper_for_monsters` | Phase 2.5b (v2.49.203): the tabletop page source carries the `_hydrateMonsterCard` JS helper, the slotId computation prefers `c.id` over `'monster-{tid}'` for monsters, and `renderBattle()` actually calls the helper. If a future commit removes any of the three, monster mini-sheets silently regress to `buildMonsterInitSheet` for all combatants and Phase 2.5b's user-visible benefit (unified renderer, per-tab partial parity) is lost. |
| `test_spell_slug_npc_renders_spells_tab` | Bug 3 fix (v2.49.206): Soren the Cult Acolyte's mini-sheet in the monster pool contains a `data-tab="spells"` button + `data-panel="spells"` panel + at least one `✨ Inflict Wounds` or `✨ Sacred Flame` row. Validates that `_monster_template_to_sheet` projects spell_slug actions into `sh['spells']` AND the partial's empty-`_iter_classes` fallback fires for monsters (which have no class hierarchy). |

---

## NPC cast spell (Phase 2.5b finale — v2.49.215)

`/api/campaign/{cid}/npc_cast_spell` — NPC-caster spell endpoint that emits a `spell_cast` WS event so the chat card renders with PC-style spell-card chrome instead of multiple plain dice cards. Mirrors `/npc_attack`'s GM-only stance; rolls attack + damage server-side; on attack hit + `auto_apply_damage` applies damage via `_apply_damage_to_combatant`; for save spells emits the DC + ability chip (save resolution stays GM-manual for v1). Tests live in `tests/harness/test_npc_cast_spell.py`.

| Test | What it asserts |
|------|-----------------|
| `test_npc_cast_spell_requires_combatant_id` | POST without `combatant_id` → 400. |
| `test_npc_cast_spell_gm_only` | Non-GM POST → 403 (alice client). |
| `test_npc_cast_spell_bad_combatant_404` | GM POST with an unknown combatant_id → 404. |
| `test_npc_cast_spell_happy_path_save_spell` | GM POST for Soren (Cult Acolyte) casting Sacred Flame → 200 + `spell_cast` WS broadcast with the right shape (`spell_name=Sacred Flame`, `save_ability=DEX`, `save_dc=13`, `is_save=True`, `caster_char_name=<nickname>`, `caster_combatant_id=tok_…`, `caster_char_id=None`, `is_npc_cast=True`). Skips gracefully when the demo's battle.combatants doesn't currently include the Acolyte. |
| `test_npc_cast_spell_aoe_multi_target_save_loop` | v2.49.217: GM POST for Burning Hands with `aoe_target_combatant_ids=[tok_a, tok_b]` + `area_shape=cone` + `area_size_ft=15` → broadcast contains `area_shape="cone"` + `auto_save_targets` array with ≥1 entry. NPC target entries carry a rolled save value (PC entries pc_skipped=true). Skips when the demo doesn't have the Acolyte. |

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

## Spell catalog (Phase 2A — v2.49.108)

First slice of the spell-validation suite proposed at [`plan-spell-validation-suite`](../plans/spell-validation-suite.md). Loads every SRD spell JSON under `app/data/local/dnd5e/spells/` (319 entries) and asserts mechanical contracts per spell. v1 covers single-target attack-roll spells (damage range-check only); save / multi-beam / auto-hit variants are filed for follow-up commits.

### `spell_catalog.py` (helper, not a test file)
The session-scope catalog loader + dice-expression parser. `load_all_spells()` reads every JSON file; `dice_range("8d6")` returns `(8, 48)`; `damage_actions(spell)` filters a spell's actions list to those with non-empty `damage`.

### `spell_assert.py` (helper, not a test file)
Assertion helpers — `assert_damage_in_range(damage_total, expression, *, spell_name, slot_level, upcast_dice)` checks the rolled total is inside the dice expression's [min, max] bounds. Failure messages lead with the spell slug + expression so a CI log points at the broken row.

### `test_spell_catalog_loader.py`
Unit tests for the loader + parser. Pure Python; doesn't need the harness server.

| Test | What it asserts |
|------|-----------------|
| `test_load_all_spells_returns_non_empty` | The SRD catalog loads ≥ 200 spells; each has a slug + name. |
| `test_dice_range_single_die` | `1d10` → (1, 10); `1d4` → (1, 4); `1d20` → (1, 20). |
| `test_dice_range_multi_die` | `8d6` → (8, 48); `3d4` → (3, 12); `4d8` → (4, 32). |
| `test_dice_range_flat_bonus` | `1d10+3` → (4, 13); `2d6+5` → (7, 17). |
| `test_dice_range_negative_modifier` | `1d6-1` → (0, 5); `2d8-1` → (1, 15). |
| `test_dice_range_mixed_dice_terms` | `1d8+1d6` → (2, 14); `1d4+1d6+1d8` → (3, 18). |
| `test_dice_range_empty_string` | `""` and whitespace → (0, 0). |
| `test_dice_range_whitespace_tolerated` | ` 1d10 + 3 ` and `8 d 6` parse the same as their compact forms. |
| `test_damage_actions_finds_damage_only` | Filters action lists to entries with non-empty `damage`. |

### `test_spell_catalog_damage.py`
Parameterized over `(caster_name, spell_slug, spell_index, slot_level, base_dmg_expr, upcast_dice)` rows in the `DAMAGE_SPELL_CASES` table. v1 has one row (Fire Bolt at Wizard L5 → 2d10). Each case long-rests the caster, seeds a target combatant, casts the spell, and asserts `response.auto_attack_damage_rolled` is inside the dice expression's [min, max]. Damage type is verified against the catalog JSON.

| Test | What it asserts |
|------|-----------------|
| `test_spell_damage_in_declared_range[Thalindra Moonwhisper-fire-bolt-L0]` | Fire Bolt cast by Thalindra (Wizard L5) → response rolls 2d10 fire damage; range-check 2-20. |

**Filed for follow-up** (each is a separate response-shape adapter):
- Save spells (Fireball, Sacred Flame, …) — read `auto_save_damage_rolled` / per-target `auto_save_targets[*].damage_applied`; requires `auto_apply_damage` toggled on for the cast.
- Multi-beam spells (Scorching Ray, Eldritch Blast) — read `auto_attack_beams[*]`; expected expression is per-beam, not summed.
- Auto-hit damage spells (Magic Missile) — read whichever field carries the auto-hit dart sum; no attack roll, no save.

---

## Browser-level UI harness (`tests/harness_ui/`)

The HTTP+WS suite at `tests/harness/` can't reach canvas event handlers, modal dialogs, or other DOM-level behavior. The Playwright suite at `tests/harness_ui/` covers those — it boots a real Chromium, navigates the demo as a logged-in user, and asserts on observable DOM / network state. Runs in CI under the `harness-ui` job.

### `test_smoke.py`
| Test | What it asserts |
|------|-----------------|
| `test_sheet_loads_for_pip` | Pip's standalone character sheet renders without console errors; `#attacks-fieldset` is visible. |
| `test_sheet_loads_for_tavik` | Same smoke check for Tavik; `#resources-fieldset` also visible. |

### `test_attack_toast.py`
v2.7.3 regression catcher — the broadcast was correct but the toast never appeared in the DOM. See file for exact assertions. **NOTE (v2.49.93):** these two tests have been silently failing since v2.16.0 added the Sneak Attack uplift modal — the click handler now opens `#uplift-modal` for Pip (Rogue Lv 1+) before reaching the fetch, and the test never dismisses it. Tracked for follow-up; not introduced by v2.49.93.

### `test_attack_toast_multi_target.py`
v2.49.93 — chat-card multi-target rendering. When `/attack` fires with `target_combatant_ids: [a, b, c]`, the server's `weapon_attack` broadcast carries `auto_attack_targets` with one entry per target (v2.49.85). Pre-v2.49.93, the client's chat card only rendered the primary target's outcome — the secondary + tertiary names were silently dropped. v2.49.93 fans the chain out: one attack + one damage toast per per-target outcome, staggered 700 ms apart so they don't pile on each other.

| Test | What it asserts |
|------|-----------------|
| `test_multi_target_attack_renders_one_toast_chain_per_target` | Seeds a 3-bandit battle, POSTs `/attack` with `target_combatant_ids` of 3, asserts 6 `.roll-toast` elements appear (3 attack + 3 damage), and every bandit's name shows up in at least one toast label. |
| `test_single_target_attack_still_renders_one_chain` | Backward-compat smoke. Same setup, but POSTs with the legacy singular `target_combatant_id`, asserts exactly 2 toasts (one chain only) and only the primary target's name appears. Catches an accidental double-render on the single-target path. |

### `test_tabletop_canvas.py`
v2.49.92 — canvas pan + drag regression suite. Built when the v2.49.81 `_hoverCursor` TDZ bug silently broke every canvas listener for 11 versions and no existing test could detect it. The suite is the gate for any future change that touches canvas event handlers, CSS on `.map-pane` / `#vtt-canvas`, or the tabletop's IIFE structure.

| Test | What it asserts |
|------|-----------------|
| `test_tabletop_loads_without_js_errors` | `page.on("pageerror", ...)` collects exceptions during navigation to `/campaign/1`; assert list is empty after `window.vttGetCharacters` is defined. Would catch a TDZ / undeclared-variable / syntax error in tabletop.js. |
| `test_right_click_drag_pans_canvas` | Drives a right-mouse drag inside the visible `.map-pane`; asserts `#vtt-canvas`'s `style.transform`'s translate(...) component shifted by > 20 px horizontally + > 10 px vertically. Would catch v2.49.88-class CSS regressions, v2.49.90-class JS event-pipeline regressions, OR the v2.49.81 IIFE-crash regression that broke pan silently. |
| `test_left_click_drag_moves_token` | Resets a known token (Pip) to a fixed on-screen position via the `/token/{id}/move?override=true` REST API; drives a left-mouse drag on the canvas; asserts the token's persisted x/y mutated by at least one grid cell in the dragged direction. Would catch any regression that prevents the mousedown → POST `/token/{id}/move` chain from firing end-to-end. |

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

## Known flakes (test-isolation pollution)

The following tests pass in isolation (running the file alone or the test alone) but fail when run as part of the full `pytest tests/harness/` suite due to state pollution from earlier-running tests. Tracked here because the bisection cost per flake is non-trivial (each requires running subsets of the 568-test suite to find the polluter) and the failures are not regressions from any specific commit — they accumulated across the reactions push (v2.69 → v2.80) as more tests share the demo campaign without resetting state between them.

Bisection-find pattern (when you decide to chase one):
1. Confirm the test passes in isolation: `python3 -m pytest tests/harness/<test_file>::<test_name> -v`
2. Run the failing test after each alphabetical group: `python3 -m pytest tests/harness/test_a*.py tests/harness/<file>::<name> -q`, then `test_b*.py`, etc.
3. The group that fails contains the polluter. Bisect down to a single test.
4. Read that test's `finally` block. The pattern is almost always "removes a campaign-setting form key" (interpreted server-side as resetting to OFF) instead of "restores to the demo seed default." v2.79.0 fixed one instance (auto_apply_damage in the v2.67.2 UD test); the same playbook applies here.

| Flake | Failure | First-noticed |
|-------|---------|---------------|
| ~~`test_attack_auto_damage.py::test_attack_auto_apply_on_hit`~~ | ~~Asserts `target_hp_after < pip_hp_before` after a hit. Fails when run after some other test in the suite (depends on `auto_apply_damage` campaign setting + Pip's sheet HP state). The fixture-level `auto_apply_on` cleanup at line 73-76 removes the form key (= OFF) on teardown, matching the v2.79.0-fixed pattern. Likely the source.~~ **Fixed in v2.80.2** — `auto_apply_on` fixture teardown now restores the demo default (ON) instead of removing the key. Full 568-test suite passes. | v2.51.6 (fixed in v2.80.2) |
| `test_aura_of_devotion.py::test_aura_of_devotion_blocks_charmed_install` | Fails when test_aura_of_devotion runs after some other test that polluted Caelan's sheet (lost his aura-of-devotion class feature, or his action economy is in the wrong state). | reactions push era |
| `test_heal_claim_uplift.py::test_apply_healing_runs_life_domain_uplift` | Asserts a `disciple-of-life` broadcast on heal-claim resolution but the buffered broadcasts show only `spell_cast` + `spell_slot_update`. Tavik's action economy or Life Domain feature state is polluted. | reactions push era |
| `test_aura_of_protection.py` (various) | Caelan's level / aura-of-protection state polluted by tests that touched his sheet. | reactions push era |
| `test_danger_sense.py` (various) | Krieger's class_features / level / sheet state polluted. | reactions push era |
| `test_spell_catalog_damage.py` (various) | Demo spell-list state assertions affected by tests that touched sheet.spells (e.g. v2.72.0 Silvery Barbs test patches Thalindra). | reactions push era |

When a flake is fixed at the source, remove its row.

---

## Updating this doc

When you change tests, update the corresponding section in the same commit. Conventions:

- **Added test** → new row in the file's table.
- **Removed test** → strike the row out (`~~test_name~~`) and leave the file's total-test-count number in the header in sync.
- **Renamed test** → rename the row.
- **Behavior change** → update the "What it asserts" cell.

When a whole new test file lands, add a new H3 (`###`) section under the appropriate category. If the category doesn't fit, add a new H2 (`##`) and link it from the [Categories](#categories) list.

The total-test-count line at the top is updated each time the file changes. Run `python3 -m pytest tests/harness/ -q` to confirm the number.
