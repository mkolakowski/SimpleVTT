# Class / Subclass / Feat / Race content — implementation status

Inventory of every D&D 5e SRD entity shipped under `app/data/local/dnd5e/`,
annotated with current implementation status. This is the **starting
list** — detailed per-feature plans go below their respective sections as
work begins. Add follow-up plans for items in 🟠 / ⚪ status as they
become priorities; do **not** start a feature without first writing
its plan section here.

> **Recent shipped work (through v2.15.10):** Phase A demo content
> (A.1-A.3: Caelan Paladin v2.14.0 / Lyra Bard v2.14.1 / Mira Druid
> v2.14.2 — demo party now 6 PCs covering Rogue/Wizard/Cleric/Paladin/
> Bard/Druid). Phase B per-feature work: B.1 Channel Divinity Devotion
> options for Paladin (v2.14.3, Sacred Weapon + Turn the Unholy);
> B.2-B.2.2 Wild Shape harness + chip integration + over-budget gate
> (v2.14.4-v2.14.6); B.3-B.3.1 Magical Secrets toggle + Lyra Lv 6 demo
> picks (v2.15.0-v2.15.1); B.4 Jack of All Trades (v2.15.2); B.5-B.5.2
> Song of Rest server bonus + Short/Long Rest UI routing through
> `/rest` (v2.15.3-v2.15.5); B.6 Divine Sense announce + Cleansing
> Touch curated (v2.15.6); B.7-B.7.1 Cutting Words endpoint + target
> picker (v2.15.7, v2.15.10). Doc-only commits: v2.15.8 filed the Wild
> Shape token-swap TODO; v2.15.9 generalised it into a reusable
> `Token.disguise` primitive design for Polymorph / Disguise Self /
> Alter Self / True Polymorph. Action-economy infrastructure (E) is
> complete through Phase 5 + strict-mode gate (v2.8.0). Test harness
> grew from the v2.12.0 vertical slice to **72 tests** at v2.15.10
> covering /attack, /cast_spell, /rest, /roll, /transform, /use_*,
> concurrency, smoke, plus Playwright UI tests. Status markers in
> this file's per-class tables update only when a feature is fully
> shipped (✅) or genuinely progresses (🟢 → 🟢 with note, 🟡 → 🟢,
> ⚪ → 🟠/🟢/✅). When a feature ships, the row's Notes column
> documents the specific commit(s) so future readers can trace the
> work back to the changelog.

> **Recent shipped work (v2.15.11 → v2.49.109):** Spans 34 patch
> versions of incremental class-feature + system work. Highlights
> material to this doc's status markers:
> **Monk** — Stunning Strike endpoint + Lv5+ harness coverage
> (v2.49.55: `/api/campaign/{cid}/use_stunning_strike`, paired CON
> save broadcast, applies "stunned" condition buff via the Phase C
> condition slot); Way of the Open Hand — Open Hand Technique
> endpoint (v2.49.57: three picker modes — prone / disengage / lose
> reaction — driven by a per-Flurry-of-Blows action button). Both
> ship with harness tests + are mechanically wired end-to-end.
> **Concentration system** — auto-save on damage (v2.49.48 corrected
> the timing so concentration drops BEFORE the save when HP hits 0,
> preventing lingering Hex / Hunter's Mark on unconscious casters);
> incapacitating-buff caster drops their own concentration (v2.49.51);
> GM audit-log entries for voluntary end-buff + swap-conc (v2.49.52,
> v2.49.53, v2.49.54). **Sleep spell** — full mechanical
> implementation (v2.49.58 HP-pool targeting + 20-ft radius sweep;
> v2.49.61 wake-on-damage; v2.49.62 `/shake_awake` voluntary wake
> action; v2.49.63 added to Bard/Sorcerer/Warlock spell lists;
> v2.49.64 undead + charm-immune exclusion). Not a class feature but
> material to the Wizard / Bard / Sorcerer / Warlock spell catalogs.
> **Ruler / range enforcement** — Phases 1-3E all shipped (v2.49.71
> through v2.49.84): client-side ruler tool, server-side range parser
> + enforcement on `/cast_spell` and `/place_aoe`, hover rangefinder,
> cast-button hover rings, multi-segment measuring, broadcast mode.
> **Multi-target attacks** — `/attack` accepts `target_combatant_ids`
> with per-target fresh rolls (v2.49.85-86); chat card fans out one
> attack+damage toast chain per target (v2.49.93). Per-target uplift
> detection (Hex / Hunter's Mark only on primary) is filed — needs
> the v2.49.85 multi-target loop to call `_compute_attack_auto_uplifts`
> per-target instead of once. **NPC resistance halving** — closed the
> v2.49.107 damage-review finding that template `damage_resistances`
> + combatant `buffs` were silently no-op'd (v2.49.109).
> **Spell-validation suite** — plan landed v2.49.103 at
> `docs/plans/spell-validation-suite.md`; Phase 2A v1 v2.49.108 with
> `spell_catalog.py` loader + `spell_assert.py` damage range
> assertion + Fire Bolt as the seed row. Save / multi-beam /
> auto-hit follow-up commits will iterate the catalog.
> **Player simulacrum** — plan landed v2.49.68 at
> `docs/plans/player-simulacrum.md` (private per-player testing
> tabletop); no code yet.
> The test harness grew from 72 tests at v2.15.10 to **351 tests** in
> `tests/harness/` + 7 in `tests/harness_ui/` at v2.49.109 — see
> `docs/test-harness-coverage.md`.
>
> **Comprehensive audit (v2.49.111, 2026-05-22):** walked all 105
> commits in the v2.15.11 → v2.49.109 range. The audit confirmed that
> only TWO entries needed a status flip — Monk Stunning Strike (Lv 5,
> ⚪ → ✅, v2.49.55) and Way of the Open Hand subclass (🟡 → 🟢,
> Open Hand Technique wired v2.49.57). Both were updated in v2.49.110.
> The remaining ~50 ⚪ / 🟡 / 🟢 rows across the 12 classes stayed at
> the v2.15.10 baseline: the v2.16 → v2.49 work was dominated by
> SPELL ENGINE INFRASTRUCTURE (Phase T.3 save-spell auto-resolution
> in v2.30.0; T.3b auto-damage on save-for-half v2.31.0; T.3c NPC
> condition auto-install v2.32.0; T.3d PC save-or-suck v2.37.0; T.3e
> concentration cleanup v2.38.0; T.4 heal flows v2.26.0; T.4b spell
> attack rolls v2.34.0; T.4c cantrip scaling v2.36.0; T.4c-follow-up
> Eldritch Blast multi-beam v2.40.0; T.5 / T.5b / T.5d / T.5e AoE
> placement v2.44.x → v2.48.x) — none of which add new class-feature
> rows but ALL of which materially improve every spellcasting class's
> in-play experience. These spell-engine improvements should be read
> as "the existing 🟢 / 🟡 spell-related rows now work better"
> rather than triggering row-by-row status flips.

**Audit conclusion.** The doc as of v2.49.111 accurately reflects
shipped class-feature work. New row flips will happen when concrete
class features ship — e.g. the next Monk picker (Patient Defense /
Step of the Wind), Sorcerer Metamagic, Warlock Pact Boon, etc.

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | **Implemented** — appears on the character sheet AND mechanically functional (clickable, decrements / restores correctly, integrated with rest / roll-log / WS broadcast where relevant) |
| 🟢 | **Half-implemented** — UI primitive present (e.g. counter pill), but the side-effect mechanics (e.g. the option-picker that drives "Channel Divinity → Turn Undead") aren't wired |
| 🟡 | **Data only** — description text visible on sheet via the SRD JSON; no mechanical wiring |
| 🟠 | **Planned** — design / plan exists in this file or in `docs/plans/*.md`, no code yet |
| ⚪ | **No plan** — neither implemented nor designed; would need a fresh planning pass before work starts |

Where a feature exists in multiple flavors (counter ✅ + option-picker 🟠
e.g. Channel Divinity) the highest applicable symbol wins, with a note in
the comment column.

---

## Classes — features

The 12 PHB SRD classes are shipped under `app/data/local/dnd5e/class_features/`.
The `### Header` names below come from the `features` field of each JSON.

### Barbarian

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Rage | 🟢 | Resource counter exists (`key: 'rage'`); damage bonus + advantage / resistance side effects not auto-applied |
| 1 | Unarmored Defense | 🟡 | Description visible; AC engine doesn't auto-detect this fighting style — player sets `base_ac` manually |
| 2 | Reckless Attack | ✅ | v2.49.238 — `/use_reckless_attack` endpoint installs a 1-round self-buff with `effects.advantage_on=['str_attack']` + `effects.incoming_attacks_have_advantage=True`. Phase-B helper `_attacker_has_str_attack_advantage` (generalized from rage-only check) picks up the upside; new `_target_grants_advantage_to_attackers` picks up the downside. Krieger (Lv 5 Berserker) is the demo fixture; harness in `test_use_reckless_attack.py`. |
| 2 | Danger Sense | ✅ | v2.52.0 — first save-roll advantage intercept. `_pc_has_danger_sense_on_dex_save(char, save_ability)` returns True for Barbarian Lv 2+ PCs on DEX saves; callers swap the d20 expression `1d20 → 2d20kh1` (same kh1 idiom the attack flow uses for Reckless Attack / Rage str-attack). Wired into `/place_aoe` PC branch (server-rolled save expr) + `/cast_spell` single + AoE PC save roll_request creation (`base_expression` is set to `2d20kh1` so the PC's own /respond roll uses advantage). Broadcasts `feature_used` with `source: "danger-sense"` when triggered. Krieger (Lv 5 Berserker) is the demo fixture; harness in `test_danger_sense.py`. RAW caveats ("can see" + "not blinded/deafened/incapacitated") not enforced — same simplification convention as Uncanny Dodge / Evasion. |
| 3 | Primal Path | ✅ | Subclass system shipped — see Subclasses table for per-path status. Path of the Berserker has features JSON; other paths fall back to descriptive. |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | Standard ASI flow handles every class |
| 5 | Extra Attack | ✅ | RAW supported — click the attack button twice within your action; the action-economy chip is per-action (not per-attack) so it doesn't double-mark. UI polish (auto-suggest, "attacks remaining" badge) is filed as a future nice-to-have. |
| 5 | Fast Movement | ✅ | v2.54.1 — pure-descriptive. +10 ft speed while not in heavy armor. Already baked into Krieger's listed sheet speed (40 ft = 30 base + 10 Fast Movement). Added a descriptive `class_features` row on `_barbarian_sheet`. No mechanic required RAW — sheet speed is GM-set / sheet-authoritative; the bonus is already reflected. |
| 7 | Feral Instinct | ⚪ | |
| 9 / 13 / 17 | Brutal Critical | ⚪ | |
| 11 | Relentless Rage | ⚪ | |
| 15 | Persistent Rage | ⚪ | |
| 18 | Indomitable Might | ⚪ | |
| 20 | Primal Champion | ⚪ | |

### Bard

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Spellcasting | ✅ | Spells panel renders + casts via `/api/.../roll` |
| 1 | Bardic Inspiration | ✅ | v2.11.0 — target picker (`showTargetPicker`) excludes self per RAW; `/use_bardic_inspiration` endpoint decrements counter + marks bonus slot + scales die by Bard level (d6/d8/d10/d12). Harness coverage v2.14.1. |
| 2 | Jack of All Trades | ✅ | v2.15.2 — `_hasJackOfAllTrades(form)` JS helper + Jinja `_bard_lv_ns` mirror in the skill card render. Adds `floor(PB/2)` to non-proficient ability checks (raw ability rolls + non-proficient skill rolls; saves intentionally untouched per RAW). Roll note carries `(Jack +N)` for attribution. |
| 2 | Song of Rest | ✅ | v2.15.3 — `_song_of_rest_for_campaign` helper picks highest-level Bard in campaign; `/rest` short-rest folds `+1dN` (d6/d8/d10/d12 by Bard level) into the recovery dice expression. UI Short Rest button routed through `/rest` in v2.15.4; Long Rest in v2.15.5. Harness coverage in `tests/harness/test_rest.py`. |
| 3 | Bard College | ✅ | Subclass system shipped — see Subclasses table. College of Lore has features JSON + Cutting Words + Additional Magical Secrets wired (v2.15.7-v2.15.10). |
| 3 / 10 | Expertise | ✅ | Skills schema has `expertise: true` flag handled by skill-roll engine |
| 5 | Font of Inspiration | ✅ | Bardic Inspiration counter resets on short rest from Lv 5 — handled implicitly by the `reset: 'short'` flag on the resource (already wired via `/rest`'s `refilled_resources` walk). Demo Lyra's counter is tagged `reset: "short"` per v2.14.1. |
| 6 | Countercharm | ✅ | v2.54.0 — first **condition-gated** save aura. `/use_countercharm` installs a 1-round `countercharm-active` self-buff on the bard. The cast_spell save-roll construction hook reads the buff via `_ally_has_countercharm_active` AND gates on the spell's `_SPELL_CONDITION_MAP` entry — if the spell installs charmed or frightened, the saving PC's d20 swaps `1d20 → 2d20kh1`. Same commit also adds `suggestion` to `_SPELL_CONDITION_MAP` (Wis save → Charmed, concentration 8h) so there's a demo-coverable spell to gate against. Wired into both cast_spell single-target + AoE PC save roll_request paths. Broadcasts `feature_used(source="countercharm")` naming the bard. Lyra (Lv 6 College of Lore) is the demo fixture; harness in `test_use_countercharm.py`. v1 simplifications: no 30 ft radius check (any PC in init counts as in range); RAW "re-perform each turn" handled by 1-round buff auto-expire — player re-casts to maintain. |
| 10 / 14 / 18 | Magical Secrets | ✅ | v2.15.0 — "🪄 Any class list" toggle in the Browse Spells modal omits the `spell_list=` filter when an eligible PC is editing (Lore Bard Lv 6+ OR Bard Lv 10+). Added spells carry `_via: "magical-secrets"` so `spellRowHtml()` renders a purple badge. v2.15.1 bumped demo Lyra to Lv 6 + added her 2 picks (Fireball + Counterspell). |
| 20 | Superior Inspiration | ⚪ | |

### Cleric

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Spellcasting | ✅ | Demo Tavik (Lv 5) prepares cantrips + L1-L3 spells correctly post-v2.4.12 |
| 1 | Divine Domain | ✅ | Subclass system shipped — see Subclasses table. All 12 domains have spell-grants curated; Life Domain has features JSON + Channel Divinity options end-to-end (Tavik demo PC since v2.3.25). |
| 2 | Channel Divinity | 🟢 | Resource counter (`key: 'channel-divinity'`) + v2.9.0 option-picker (`showResourceOptionPicker`). Life Domain ✅ end-to-end (Turn Undead + Preserve Life); v2.14.3 added Light's Radiance of the Dawn + War's Guided Strike option entries. **v2.56.1** added the Lv 2 CD options for the remaining 8 Cleric domains (Knowledge: Knowledge of the Ages; Tempest: Destructive Wrath; Trickery: Invoke Duplicity; Forge: Artisan's Blessing; Grave: Path to the Grave; Order: Order's Demand; Nature: Charm Animals and Plants; Twilight: Twilight Sanctuary). Every Lv 2+ Cleric of any domain now sees a curated CD option in the picker. Each is announce-only — the GM applies the mechanical effect manually after the chip flip + broadcast (matches Turn Undead's existing UX). Lv 6 CD options (Knowledge: Read Thoughts; Trickery: Cloak of Shadows) + a picker level-gate filed for follow-up. Curated table also serves Paladin Oath of Devotion (Sacred Weapon + Turn the Unholy). |
| 5 / 8 / 11 / 14 / 17 | Destroy Undead | ⚪ | Tied to Turn Undead option above; would surface as a damage uplift when Turn Undead is implemented |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 10 | Divine Intervention | ⚪ | |

### Druid

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Druidic | ✅ | Pure-descriptive language feature. No mechanic required RAW — description text on the sheet is sufficient. |
| 1 | Spellcasting | ✅ | |
| 2 | Wild Shape | ✅ | Sheet swap via `/transform` endpoint + `BeastPicker` JS (pre-2.0.0). v2.14.4 added harness coverage (`tests/harness/test_transform.py`). v2.14.5 added action-economy chip integration (`_wild_shape_economy_slot` returns "bonus" for Moon Druid, "action" otherwise; `_mark_battle_economy` called on success). v2.14.6 added the Phase 4 over-budget gate (409 `error: "over_budget"` for non-GMs; BeastPicker's `_confirm` handles the modal-and-retry). Demo Mira (Lv 5 Moon Druid) is the test bed. Token swap on transform is filed as the Token-disguise primitive TODO (v2.15.9) for future implementation. |
| 2 | Druid Circle | ✅ | Subclass system shipped — see Subclasses table. Circle of the Moon has full Wild Shape integration (Combat Wild Shape v2.14.5; Circle Forms CR cap raised to 1 at Lv 2); Circle of the Land has Natural Recovery counter. |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 18 | Timeless Body | ✅ | Druid Lv 18: pure-descriptive (you age more slowly). No mechanic required RAW — description text on the sheet is sufficient. |
| 18 | Beast Spells | ✅ | v2.55.1 — pure-descriptive. RAW: cast spells while in Wild Shape (verbal/somatic components flow through the beast form). The existing v2.14.4 `/transform` Wild Shape flow doesn't gate spellcasting on form anyway — a Wild-Shaped Druid CAN already cast their spells through SimpleVTT today — so Beast Spells lands as a no-op behavioral default. Descriptive only; no demo Lv 18+ Druid fixture. |
| 20 | Archdruid | ✅ | v2.55.1 — pure-descriptive. RAW: unlimited Wild Shape per day + ignore verbal/somatic/material components on Druid spells + age cap. Wild Shape uses are already not enforced as a strict resource in the demo (Mira's Wild Shape counter is descriptive — `/transform` allows the swap without decrementing); Archdruid's "unlimited" property is the default. Component-cost ignoring isn't modeled (no component-tracking system). Descriptive; no Lv 20 Druid fixture. |

### Fighter

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Fighting Style | 🟡 | Description visible; bonuses not auto-applied to attack rolls |
| 1 | Second Wind | ✅ | v2.17.1 — dedicated `/use_second_wind` endpoint rolls 1d10 + fighter_level + applies HP via `_apply_hp_change` + decrements counter + marks bonus slot + over-budget gate. Garrik (Lv 5 Champion Fighter, v2.17.0) is the demo test bed (1d10+5 → 6-15 HP). cf-use handler routes class_features 'second-wind' to the new endpoint with HP form-input sync. Harness coverage in `test_use_second_wind.py`. |
| 2 / 17 | Action Surge | ✅ | v2.17.2 — dedicated `/use_action_surge` endpoint decrements the counter + REFUNDS the action chip via `_mark_battle_economy(..., used=False)` (new keyword arg added in v2.17.2). cf-use handler routes class_features 'action-surge' to the new endpoint. After Action Surge fires, the fighter can click another weapon/spell on the same turn and Act auto-marks again. Garrik (Lv 5 Champion) is the demo test bed. Harness coverage in `test_use_action_surge.py` including a chip-refund test that injects battle state via PUT /battle. |
| 3 | Martial Archetype | ✅ | Subclass system shipped — see Subclasses table. Champion: Improved Critical ✅ (v2.49.231) + Remarkable Athlete ✅ (v2.49.237). Battle Master has Superiority Dice counter. |
| 4 / 6 / 8 / 12 / 14 / 16 / 19 | Ability Score Improvement | ✅ | |
| 5 / 11 / 20 | Extra Attack | ✅ | RAW supported — click the attack button N times within your action (2 at Lv 5, 3 at Lv 11, 4 at Lv 20); the action-economy chip is per-action so it doesn't double-mark. UI polish (auto-suggest, "attacks remaining" badge) is filed for the future. |
| 9 / 13 / 17 | Indomitable | ✅ | v2.56.0 — `/use_indomitable` arms a single-use `indomitable-armed` self-buff on Garrik (bumped Lv 7 → 9 in this commit). The save-roll construction hook reads the buff, swaps `1d20 → 2d20kh1`, and removes it via `_remove_buff` so the arm is per-save (not per-turn). Wired into both cast_spell single + AoE PC save roll_request paths. Counter decrements on arm; 1/long rest at Lv 9-12, 2 at Lv 13, 3 at Lv 17 (counter scaling handled on the sheet's `resources` entry — Garrik starts with max=1). **v1 simplification**: ships advantage-on-the-next-save instead of RAW reroll-on-failure, since the post-roll reroll-with-consequence-undo flow needs an undo-and-reapply path for installed conditions (Charmed, Paralyzed, etc.). Filed in TODO.md::Fighter Indomitable. Harness in `test_use_indomitable.py` (5 tests). |

### Monk

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Unarmored Defense | 🟡 | |
| 1 | Martial Arts | 🟡 | |
| 2 | Ki | ✅ | All three Lv 2 Ki spend-options now wired: Patient Defense + Step of the Wind (v2.49.112) and Flurry of Blows (v2.49.114). Endpoints `/use_patient_defense`, `/use_step_of_the_wind`, `/use_flurry_of_blows` — each installs a 1-round self-buff via `_install_buff`, marks the bonus slot, decrements the Ki counter, and broadcasts feature_used + resource_update + buff_update. Phase B effect integration (attack-roll path consuming `effects.dodging` / `flurry-of-blows-active.unarmed_strikes_available`) is filed. |
| 2 | Unarmored Movement | ✅ | v2.54.1 — pure-descriptive. +10 ft speed while not wearing armor or carrying a shield (scales to +30 ft at Lv 18+). Already baked into Kael's listed sheet speed (40 ft = 30 base + 10 Unarmored Movement at Lv 2-5; would be 45 at Lv 6-9, etc.). Added a descriptive `class_features` row on `_monk_sheet`. No mechanic required RAW — sheet speed is GM-set / sheet-authoritative. |
| 3 | Monastic Tradition | ✅ | Subclass system shipped — see Subclasses table. Way of the Open Hand: Open Hand Technique mechanically wired (v2.49.57); Wholeness of Body ✅ (v2.49.227). |
| 3 | Deflect Missiles | ⚪ | |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 4 | Slow Fall | ✅ | v2.54.1 — pure-descriptive. Reaction to reduce fall damage by 5 × monk level (35 at Lv 7). SimpleVTT doesn't model fall damage today (no `_apply_fall_damage` helper, no terrain-height tracking), so the descriptive entry on the sheet is sufficient. Re-evaluate if a fall-damage system ships — would then become a real reaction endpoint like Uncanny Dodge. |
| 5 | Extra Attack | ✅ | RAW supported — click the attack button twice within your action; the action-economy chip is per-action so it doesn't double-mark. UI polish (auto-suggest, "attacks remaining" badge) is filed for the future. |
| 5 | Stunning Strike | ✅ | v2.49.55 — `/api/campaign/{cid}/use_stunning_strike` endpoint. After a hit with a melee weapon attack, spend 1 ki → target makes CON save against the monk's spell save DC (`8 + prof + WIS mod`); on fail, "stunned" condition applied via the Phase C condition slot until end of monk's next turn. First non-concentration incapacitating-condition buff. Harness coverage in `test_use_stunning_strike.py` including a PC integration case. |
| 6 | Ki-Empowered Strikes | ✅ | v2.54.1 — pure-descriptive. Unarmed strikes count as magical for the purpose of bypassing resistance / immunity to nonmagical attacks. SimpleVTT doesn't gate resistance on the magical-vs-mundane axis today (`_resistance_halve` only checks damage type, not source-magicality), so the descriptive entry is sufficient. Re-evaluate if a magical-source resistance gate ships. |
| 7 | Evasion | ✅ | v2.51.5 — server-side intercept of save-for-half Dex-save damage. `_target_uses_evasion` (Monk Lv 7+ via `_monk_level_from_sheet`, OR Rogue Lv 7+ via `_rogue_level_from_sheet`) gates `_apply_evasion_to_dex_save_damage`, which replaces the standard "half on save, full on fail" math with "0 on save, half on fail". Wired into all 7 save-damage call sites (`/cast_spell` single-target NPC, AoE NPC extras, AoE PC reroll via `/roll_request/respond`, `/place_aoe` PC + NPC, `/npc_cast_spell` single + AoE). Broadcasts `feature_used` with `source: "evasion"`. Kael (Lv 7 Open-Hand Monk) is the demo fixture; harness in `test_use_save_evasion.py`. Rogue side (Pip needs Lv 7 bump) filed for the next class-work cycle. |
| 7 | Stillness of Mind | ✅ | v2.49.229 — `/api/campaign/{cid}/use_stillness_of_mind` endpoint. Action, unlimited uses. Takes `buff_key`; validates it's in `_STILLNESS_OF_MIND_ALLOWED_BUFF_KEYS = {charmed, frightened}` (refuses paralyzed/stunned/etc.); reuses `_remove_buff` to clear the matching buff. Sheet picker pops when monk has BOTH charmed and frightened simultaneously. Demo Kael bumped Lv 6 → 7 to land the fixture. Harness: `test_use_stillness_of_mind.py`. |
| 10 | Purity of Body | ✅ | Monk Lv 10: pure-descriptive (immunity to disease + poison). RAW: would gate the disease / poisoned conditions but SimpleVTT doesn't model those conditions today, so the description text is sufficient. Re-evaluate if a disease engine ships. |
| 13 | Tongue of the Sun and Moon | ✅ | Monk Lv 13: pure-descriptive language feature (understand all spoken languages). No mechanic required RAW. |
| 14 | Diamond Soul | ⚪ | |
| 15 | Timeless Body | ✅ | Monk Lv 15: pure-descriptive (you age more slowly + need less food/water). No mechanic required RAW. |
| 18 | Empty Body | ⚪ | |
| 20 | Perfect Self | ⚪ | |

### Paladin

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Divine Sense | ✅ | v2.15.6 — resource ⚡ Use special-case decrements the counter + POSTs `/use_feature` for the roll-log card + chip flip + over-budget gate. Caelan (Lv 5 Oath of Devotion Paladin) is the demo test bed (counter 4/4 = 1 + CHA mod). Curated `_FEATURE_ECONOMY['divine-sense'].slot = "action"`. Harness: `test_divine_sense_announces` in `test_use_feature.py`. |
| 1 | Lay on Hands | ✅ | v2.10.0 — amount + target picker chain (`showAmountPicker` → `showTargetPicker`). Dedicated `/use_lay_on_hands` endpoint is authoritative: applies HP via `_apply_hp_change` to the target AND decrements the pool atomically. Broadcasts `heal_applied` + `resource_update` + `feature_used`. Demo Caelan added v2.14.0 with pool 25 HP (5 × Lv 5). Harness coverage in `test_use_lay_on_hands.py`. |
| 2 | Fighting Style | 🟡 | |
| 2 | Spellcasting | ✅ | |
| 2 | Divine Smite | ✅ | v2.16.0 — per-attack uplift modal on Strike click. Player picks a spell slot level (L1-L4 visible from sheet's spell_slots inputs); endpoint atomically decrements the slot + rolls (level+1)d8 radiant capped at 5d8. Caelan (Lv 5 Oath of Devotion Paladin) is the demo test bed. v1 deviations: (a) modal fires BEFORE the d20 result (RAW: declare on hit), (b) +1d8 vs undead/fiends toggle isn't in the modal yet, (c) Rogue/Paladin multiclass can't stack with Sneak Attack on the same swing (endpoint accepts one bonus_damage). |
| 3 | Divine Health | ✅ | Paladin Lv 3: pure-descriptive (immunity to disease). RAW: would gate the disease condition but SimpleVTT doesn't model that condition today. Re-evaluate if a disease engine ships. |
| 3 | Sacred Oath | ✅ | Subclass system shipped — see Subclasses table. Oath of Devotion has features JSON + Channel Divinity options end-to-end (Sacred Weapon + Turn the Unholy v2.14.3; Caelan demo PC since v2.14.0). |
| 3 | Channel Divinity | 🟢 | Same counter + v2.9.0 picker shape as Cleric. **Oath of Devotion ✅ end-to-end** (Sacred Weapon + Turn the Unholy via v2.14.3 — options live under `channel-divinity.options` in the curated table with `class: "paladin", subclass: "devotion"` tags; the sheet picker filters by class+subclass via the v2.14.3 `classEntries` walker). Oath of the Ancients (Nature's Wrath / Turn the Faithless), Oath of Vengeance (Abjure Enemy / Vow of Enmity), Oathbreaker, Conquest, Crown, Redemption, Treachery still need their option entries. |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 5 | Extra Attack | ✅ | RAW supported — click the attack button twice within your action; the action-economy chip is per-action so it doesn't double-mark. UI polish (auto-suggest, "attacks remaining" badge) is filed for the future. |
| 6 / 18 | Aura of Protection | ✅ | v2.53.0 — first ally-conferred save-bonus mechanic. `_aura_of_protection_bonus(db, campaign_id, saving_char_id)` walks the active battle's init tracker for any Paladin Lv 6+ (via `_paladin_level_from_sheet`); returns the highest CHA mod (min +1 per RAW) + the paladin's Character row. Appended to `base_expression` at roll_request creation time (same construction-time hook as Danger Sense), so the PC's save shape becomes e.g. `1d20+3+5` (d20 + aura + stat). Wired into all 3 save-roll sites: `/place_aoe` PC branch, `/cast_spell` single + AoE PC save roll_request. Broadcasts `feature_used(source="aura-of-protection")` naming the paladin. Caelan (Lv 6 Oath of Devotion, bumped Lv 5 → 6 in this commit) is the demo fixture; harness in `test_aura_of_protection.py`. v1 simplifications: no 10 ft radius check (any paladin in init grants the aura to every saver — filed for follow-up via `_distance_ft_between_points`); multi-paladin doesn't stack (max wins per RAW). Lv 18 expansion to 30 ft is a future content tweak — same helper, larger radius. |
| 10 / 18 | Aura of Courage | ⚪ | |
| 11 | Improved Divine Smite | ⚪ | |
| 14 | Cleansing Touch | 🟢 | Resource counter. v2.15.6 added the curated `_FEATURE_ECONOMY['cleansing-touch']` entry so `/use_feature` accepts the slug (server-side announce works). No demo PC at Lv 14+ yet (Caelan is Lv 5), so the resource ⚡ Use branch + target picker UI for "end one spell on yourself or one willing creature you touch" is deferred to a future Lv 14+ Paladin fixture. Harness contract pin: `test_cleansing_touch_curated` in `test_use_feature.py`. |

### Ranger

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Favored Enemy | ✅ | v2.55.1 — pure-descriptive. RAW: "advantage on Wisdom (Survival) checks to track favored enemies, as well as on Intelligence checks to recall information about them." SimpleVTT doesn't model tracking-check workflows or recall checks (no `_creature_type` taxonomy on monster templates either), so the descriptive `favored-enemy` class_features row on Rowan's sheet (already shipped v2.18.3) is sufficient. Re-evaluate if a tracking/lore-check system ships. |
| 1 | Natural Explorer | ✅ | v2.55.1 — pure-descriptive. RAW: terrain-expertise bonuses on Int/Wis checks involving the chosen terrain + party travel speed + foraging perks. SimpleVTT doesn't model terrain type, party travel time, or foraging today. Descriptive `natural-explorer` row on Rowan's sheet (v2.18.3). |
| 2 | Fighting Style | 🟡 | |
| 2 | Spellcasting | ✅ | |
| 3 | Ranger Archetype | ✅ | Subclass system shipped — see Subclasses table. Hunter has features JSON (Hunter's Prey / Defensive Tactics / Multiattack still descriptive). |
| 3 | Primeval Awareness | ⚪ | |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 5 | Extra Attack | ✅ | RAW supported — click the attack button twice within your action; the action-economy chip is per-action so it doesn't double-mark. UI polish (auto-suggest, "attacks remaining" badge) is filed for the future. |
| 8 | Land's Stride | ✅ | v2.55.1 — pure-descriptive. RAW: ignore difficult terrain, advantage on saves vs plant-based magical impediments. SimpleVTT doesn't model difficult terrain on the canvas (no `terrain_difficulty` field on map cells, no movement-cost gating), so the descriptive entry is sufficient. Re-evaluate if a difficult-terrain system ships. No demo Lv 8+ Ranger fixture today. |
| 10 | Hide in Plain Sight | ⚪ | |
| 14 | Vanish | ⚪ | |
| 18 | Feral Senses | ⚪ | |
| 20 | Foe Slayer | ⚪ | |

### Rogue

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 / 6 | Expertise | ✅ | Same Skills.expertise plumbing as Bard |
| 1 | Sneak Attack | ✅ | v2.16.0 — per-attack uplift modal on Strike click. Die scales by Rogue level via `_sneakAttackDie(lv)` = `ceil(lv/2)d6` cap 10d6; Pip at Lv 5 gets 3d6. Player asserts eligibility (RAW: advantage OR ally within 5 ft of target — not validated server-side, trust-based). v1 deviations: (a) "once per turn" gating not enforced; (b) can't stack with Divine Smite on a Rogue/Paladin multiclass (endpoint accepts one bonus_damage); (c) the "ally adjacent" detection waits on a positional / token-adjacency check that doesn't exist yet. |
| 1 | Thieves' Cant | ✅ | Pure-descriptive language feature. No mechanic required RAW — description text on the sheet is sufficient. |
| 2 | Cunning Action | ✅ | v2.6.0 — class-features panel renders Dash/Disengage/Hide buttons that POST `/use_feature` and auto-mark Bns chip |
| 3 | Roguish Archetype | ✅ | Subclass system shipped — see Subclasses table. Thief has features JSON (Fast Hands / Use Magic Device still descriptive); Pip is the demo Thief since v2.3.25. |
| 4 / 8 / 10 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 5 | Uncanny Dodge | ✅ | v2.49.243 — server-side reaction halving in the damage pipeline. `_target_uses_uncanny_dodge` (Rogue Lv 5+, reaction available) fires inside `_apply_damage_to_combatant` when the new `is_attack=True` kwarg is set by an attack-roll caller. Halves damage, flips reaction chip, broadcasts `feature_used`. RAW save-spell paths intentionally skip the halving (only triggers on attacker-hits-you-with-an-attack). Auto-fires on the first incoming attack each round; "decline reaction" toggle filed for follow-up. |
| 7 | Evasion | ✅ | v2.51.6 — shares the v2.51.5 `_apply_evasion_to_dex_save_damage` plumbing with Monk Evasion; `_target_uses_evasion` recognizes BOTH `_monk_level_from_sheet(sheet) >= 7` AND `_rogue_level_from_sheet(sheet) >= 7`. This commit bumped demo Pip Lv 5 → 7 (HP 33 → 47, hit_dice 5 → 7, Sneak Attack die 3d6 → 4d6 via the JS `_sneakAttackDie(lv)` helper) and added the `evasion` `class_features` row. Harness coverage: new `test_evasion_rogue_save_success_zero_damage` test in `test_use_save_evasion.py` proves Fireball at Pip → save success → 0 damage + Evasion broadcast. |
| 11 | Reliable Talent | ⚪ | Floor-of-10 on proficient skill checks — would need an option on skill roll |
| 14 | Blindsense | ✅ | Rogue Lv 14: pure-descriptive (sense unseen creatures within 10 ft). RAW: would interact with a fog-of-war / hidden-token engine, but SimpleVTT doesn't model token hiding at that granularity. Re-evaluate if a hidden/seen state ships. |
| 15 | Slippery Mind | ⚪ | |
| 18 | Elusive | ⚪ | |
| 20 | Stroke of Luck | 🟢 | Resource counter. Curated `_FEATURE_ECONOMY` entry shipped v2.16.2 (slot:'free'). Full miss-to-hit / fail-to-20 UX waits on (B) roll-time intercept + a Lv 20 Rogue fixture. |

### Sorcerer

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Spellcasting | ✅ | |
| 1 | Sorcerous Origin | ✅ | Subclass system shipped — see Subclasses table. Draconic Bloodline has features JSON; Wild Magic has Tides of Chaos counter. |
| 2 | Font of Magic | 🟢 | Sorcery Points counter (`key: 'sorcery-points'`); curated `_FEATURE_ECONOMY` entry shipped v2.16.2 (slot:'free'). Full SP↔slot conversion picker waits on a Sorcerer fixture (Phase A.4+). Slot-conversion endpoint would follow the Arcane Recovery (`/use_arcane_recovery`) pattern — atomic mutation of spell_slots + the Sorcery Points counter. |
| 3 | Metamagic | ⚪ | Per-cast modifier; needs spell-cast intercept |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 20 | Sorcerous Restoration | ⚪ | Auto-refill 4 sorcery points on short rest — could just be a special-case in the rest endpoint |

### Warlock

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Otherworldly Patron | ✅ | Subclass system shipped — see Subclasses table. The Fiend has features JSON (Dark One's Blessing / Own Luck / Fiendish Resilience still descriptive). |
| 1 | Pact Magic | 🟡 | Uses spell-slot UI but slots refresh on short rest; partial — slot reset path needs the patch |
| 2 | Eldritch Invocations | 🟡 | Picker UI not wired; invocations are stat boosts / new options |
| 3 | Pact Boon | ⚪ | |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 11 / 13 / 15 / 17 | Mystic Arcanum | ⚪ | One-per-day single-slot spells, fresh tracking needed |
| 20 | Eldritch Master | ⚪ | |

### Wizard

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Spellcasting | ✅ | Demo Thalindra (Lv 5) prepares cantrips + L1-L3 spells correctly post-v2.4.12 |
| 1 | Arcane Recovery | ✅ | v2.16.1 — counter (1/1 long-rest) added to Thalindra's demo sheet; dedicated `/use_arcane_recovery` endpoint validates allowance (⌈wizard_lv/2⌉, L1-L5 only) + atomically decrements counter + restores selected slots + broadcasts spell_slot_update per slot + resource_update + feature_used. Resource ⚡ Use opens a +/− stepper modal with running spent/allowance display. Harness coverage in `test_use_arcane_recovery.py`. |
| 2 | Arcane Tradition | ✅ | Subclass system shipped — see Subclasses table. School of Evocation has features JSON; Divination has Portent Dice counter. Thalindra is the demo Evocation Wizard. |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 18 | Spell Mastery | ⚪ | |
| 20 | Signature Spells | ⚪ | |

---

## Subclasses

13 PHB SRD subclasses shipped under `app/data/local/dnd5e/subclass_features/`.
The curated subclass-spell tables in `app/static/dnd5e_subclass_spells.js`
also cover **non-SRD subclasses** (Tasha's, Xanathar's etc.) that don't yet
have features JSON.

| Class | Subclass | Features JSON | Spell-grants curated | Status | Notes |
|---|---|---|---|---|---|
| Barbarian | Path of the Berserker | ✅ | n/a | 🟡 | Frenzy / Mindless Rage / Intimidating Presence / Retaliation — all descriptive |
| Bard | College of Lore | ✅ | n/a | 🟢 | **Cutting Words ✅** (v2.15.7 endpoint + v2.15.10 target picker — Lyra at Lv 6 is the test bed). **Additional Magical Secrets ✅** (v2.15.0 spell-browser toggle + v2.15.1 Lyra's 2 picks). Peerless Skill (Lv 14) still descriptive — needs a Lv 14+ Bard fixture. |
| Cleric | Knowledge Domain | ❌ | ✅ | 🟡 | Spell grants work via picker; no features JSON |
| Cleric | **Life Domain** | ✅ | ✅ | 🟢 | Domain spells auto-grant (demo Tavik post-v2.4.15); Channel Divinity: Preserve Life is data only |
| Cleric | Light Domain | ❌ | ✅ | 🟡 | Curated spells; Warding Flare / Radiance of the Dawn descriptive |
| Cleric | Nature Domain | ❌ | ✅ | 🟡 | |
| Cleric | Tempest Domain | ❌ | ✅ | 🟢 | Wrath of the Storm counter exists |
| Cleric | Trickery Domain | ❌ | ✅ | 🟡 | |
| Cleric | War Domain | ❌ | ✅ | 🟢 | War Priest counter exists |
| Cleric | Forge / Grave / Order / Peace / Twilight | ❌ | ✅ | 🟡 | Spell grants only |
| Druid | **Circle of the Land** | ✅ | ✅ | 🟢 | Natural Recovery counter exists; Land's Stride / Nature's Ward descriptive |
| Druid | **Circle of the Moon** | ✅ | n/a | 🟢 | **Combat Wild Shape ✅** (v2.14.5 — `_wild_shape_economy_slot` returns "bonus" for Moon Druid subclass, "action" otherwise; `/transform` marks the right chip). **Circle Forms ✅** (CR cap raised to 1 at Lv 2 via `_ws_cr_cap` for Moon; Mira at Lv 5 can pick Dire Wolf CR 1 in the demo). Primal Strike (Lv 6) + Thousand Forms (Lv 14) still descriptive. |
| Druid | Circle of Spores / Wildfire / Stars | ❌ | ✅ | 🟡 | Spell grants only |
| Fighter | **Champion** | ✅ | n/a | 🟢 | **Improved Critical ✅** (v2.49.231). **Remarkable Athlete ✅** (v2.49.237 — `_hasRemarkableAthlete(form)` client-side helper in `sheet.js`; adds `ceil(PB/2)` to STR/DEX/CON ability checks + non-proficient skill checks on those abilities. Garrik bumped Lv 5 → 7 as the fixture; harness in `test_remarkable_athlete.py`). Survivor (Lv 18) still descriptive — waits on a Lv 18+ fixture. |
| Fighter | Battle Master | ❌ | n/a | 🟢 | Superiority Dice counter exists |
| Fighter | Eldritch Knight | ❌ | n/a | ⚪ | |
| Monk | **Way of the Open Hand** | ✅ | n/a | 🟢 | Open Hand Technique shipped (v2.49.57). **Wholeness of Body ✅** (v2.49.227: dedicated `/use_wholeness_of_body` endpoint — Lv 6 monk, action, 1/long rest, deterministic 3 × monk-level heal via `_apply_hp_change`. Krieger bumped to Lv 6 as the demo fixture; harness in `test_use_wholeness_of_body.py`). |
| Paladin | **Oath of Devotion** | ✅ | ✅ | 🟢 | **Sacred Weapon ✅** + **Turn the Unholy ✅** (v2.14.3 — both Channel Divinity options live under `channel-divinity.options` with `class:"paladin", subclass:"devotion"` tags; Caelan at Lv 5 is the demo test bed). **Aura of Devotion ✅** (v2.55.0 — first condition-install immunity gate; allies in init can't be Charmed by failed Wis saves while Caelan is in init; `_ally_has_aura_of_devotion` gates on Paladin Lv 7+ + subclass slug `devotion`; harness in `test_aura_of_devotion.py`). Purity of Spirit (Lv 15) + Holy Nimbus (Lv 20) still descriptive. |
| Paladin | Ancients / Vengeance / Conquest / Redemption / Glory / Watchers / Oathbreaker | ❌ | ✅ | 🟡 | Spell grants only |
| Ranger | **Hunter** | ✅ | n/a | 🟡 | Hunter's Prey / Defensive Tactics / Multiattack descriptive |
| Rogue | **Thief** | ✅ | n/a | 🟡 | Fast Hands / Use Magic Device descriptive |
| Sorcerer | **Draconic Bloodline** | ✅ | n/a | 🟡 | Dragon Ancestor / Draconic Resilience / Dragon Wings descriptive |
| Sorcerer | Wild Magic | ❌ | n/a | 🟢 | Tides of Chaos counter exists |
| Sorcerer | Aberrant Mind / Divine Soul | ❌ | ✅ (Aberrant) | 🟡 | Spell grants only |
| Warlock | **The Fiend** | ✅ | n/a | 🟡 | Dark One's Blessing / Dark One's Own Luck / Fiendish Resilience descriptive |
| Wizard | **School of Evocation** | ✅ | n/a | 🟡 | Evocation Savant / Sculpt Spells / Empowered Evocation descriptive |
| Wizard | Divination | ❌ | n/a | 🟢 | Portent Dice counter exists |

---

## Feats

Only one SRD feat shipped (Grappler is the only one in the OGL SRD 5.1).
Homebrew feats live alongside the SRD via the campaign-scoped homebrew
tier (e.g. the demo's `lucky-strike` feat in
`app/data/homebrew/campaign-X/feats/`).

| Feat | Source | Status | Notes |
|---|---|---|---|
| Grappler | SRD 5.1 (`app/data/local/dnd5e/feats/grappler.json`) | 🟡 | Description renders on sheet; no mechanical wiring (Grappler's "advantage on grapple checks" would need a per-skill-roll context) |
| Lucky Strike (demo homebrew) | `seed_homebrew_files` → `feats/lucky-strike.json` | 🟡 | Description renders; no automatic reroll-on-miss intercept |

Adding new feats means dropping a JSON file in the matching tier; the
homebrew editor (campaign settings → Homebrew → Feats) can author them
via UI. **Mechanical feat effects are uniformly ⚪** — none have automated
intercepts; they're all reference-text-on-the-sheet for now.

---

## Races

9 SRD races. Each ships a `traits` JSON array; the sheet renders each
trait as a row with description.

| Race | Traits | Status | Notes |
|---|---|---|---|
| Dragonborn | Draconic Ancestry, Breath Weapon, Damage Resistance | 🟡 | Breath weapon needs a "click to fire" + save-DC challenge — same pattern as Channel Divinity options |
| Half-Elf | ASI, Darkvision, Fey Ancestry, Skill Versatility, Extra Language | 🟡 | ASI ✅ via sheet; passives (Fey Ancestry = charm immunity, Darkvision) descriptive only |
| Half-Orc | Darkvision, Menacing, Relentless Endurance, Savage Attacks | 🟡 | Relentless Endurance has "once per long rest" semantics — could be a 1/1 resource counter |
| High Elf | Darkvision, Keen Senses, Fey Ancestry, Trance, Elf Weapon Training, Cantrip, Extra Language | 🟢 | Cantrip choice + Elf Weapon Training proficiency wire through existing systems; the rest descriptive |
| Hill Dwarf | Darkvision, Dwarven Resilience (poison adv/resistance), Dwarven Combat Training, Tool Proficiency, Stonecunning, Speed Not Reduced by Heavy Armor, Dwarven Toughness | 🟢 | Demo Tavik benefits from Dwarven Toughness (+5 HP at Lv 5) — already in the cleric sheet's `hp.max=43` |
| Human | ASI ×6, Extra Language | ✅ | The all-+1-stats flow is supported via standard ASI; Variant Human's free feat would need the feat-picker UI work |
| Lightfoot Halfling | Lucky, Brave, Halfling Nimbleness, Naturally Stealthy | 🟡 | Lucky (reroll 1 on attack/check/save) would need a roll-time intercept — same shape as the Lucky feat in some homebrew sources |
| Rock Gnome | Darkvision, Gnome Cunning (adv vs INT/WIS/CHA magic saves), Artificer's Lore (+2 ×PB on history of magic items), Tinker | 🟡 | |
| Tiefling | Darkvision, Hellish Resistance (fire resist), Infernal Legacy (Thaumaturgy + Hellish Rebuke 1/day + Darkness 1/day) | 🟢 | Infernal Legacy spells could attach to a per-day resource counter; spell-cast hook exists for cantrips |

---

## Cross-cutting infrastructure plans

These are NOT class/race/feat-specific but block any deeper mechanical
work above. Filed here so the order-of-operations is clear.

### A. Resource option-picker UI

**Affects:** Channel Divinity (Cleric, Paladin), Ki (Monk), Sorcery
Points (Sorcerer), Bardic Inspiration (Bard), Superiority Dice (Battle
Master), Lay on Hands (Paladin), Cleansing Touch, Stroke of Luck.

Today the class-resources panel renders `Name X/Y` and a single "Use"
button that decrements `current` by 1. The next level of richness is an
overlay that opens on click and lets the player pick **which option** the
resource is being spent on (Turn Undead vs Preserve Life, Flurry of
Blows vs Patient Defense vs Step of the Wind, etc.).

**Plan:** see the Channel Divinity 3-phase plan in conversation /
2.4.15 commit message. The plan generalizes — the picker is keyed on
`resource.key` and reads from a per-feature curated table
(`dnd5e_channel_divinity.js`, `dnd5e_ki_options.js`, etc.) that lists the
options unlocked at the character's level.

### B. Roll-time intercepts

**Affects:** Lucky (Halfling + feat), Reliable Talent (Rogue), Indomitable
(Fighter), Stroke of Luck (Rogue), Portent (Divination), Bardic
Inspiration (recipient side), Sneak Attack (uplift), Divine Smite
(uplift), Improved Critical (Champion).

These all want to fire **at the moment a d20 is rolled** — either to
modify the result (reroll, replace, add) or to trigger a follow-on
roll (smite damage). Today `/api/.../roll` is a fire-and-forget endpoint;
adding intercepts means a confirmation-style modal that pauses between
roll-result-known and result-applied, with affordances for each
applicable feature.

**No plan yet.** Big architectural change — would touch every roll path.

### C. Combat condition / buff slot

**Affects:** Rage (resistance + adv on STR), Reckless Attack (adv +
disadvantage incoming), Guided Strike (next attack +10), Bless (+1d4
on attack/save), Bardic Inspiration (recipient), almost every concentration
spell.

Today the only "buff" surface is the manual conditions list. A
character would benefit from a structured buff slot: name, duration,
mod, expiration trigger. Big design surface.

**No plan yet.**

### D. Passive trait engine

**Affects:** every race's Darkvision / damage resistance / saving-throw
advantage, Sneak Attack reqs, Dwarven Toughness, Fey Ancestry.

Most racial traits are passive — they apply automatically when a
specific roll happens (e.g. "Dwarves have advantage on saves against
poison"). Today they're descriptive only; players manually flip
advantage / disadvantage at roll time.

**No plan yet.** Tied to (B) — same intercept point.

### E. Action-economy tracker

**Affects:** Every ability button across the GM init tracker, mini-sheet
attacks / spells / monster-actions, and the full character sheet's
attacks + spells panels. Specifically: Cunning Action (Rogue Lv 2),
Second Wind / Action Surge (Fighter), Rage (Barbarian), Bardic
Inspiration (Bard), Healing Word / Misty Step / Counterspell / Shield /
Hellish Rebuke / Spiritual Weapon (any caster), Opportunity Attack +
Uncanny Dodge + Shield reactions, and every Channel Divinity / Ki /
Sorcery-point option that resolves to an action or bonus action.

**Why foundational:** Most per-feature plans above need to know "is
this clicking an action, bonus action, or reaction?" so they can both
consume the right per-turn slot and gate alternatives ("you've already
used your bonus action; Healing Word is unavailable until next turn").
Implementing the economy tracker first means (A) resource-picker, (B)
roll-time intercepts, and (C) buff slot can each read the economy
state instead of re-inventing per-turn tracking ad-hoc per feature.
This is the **biggest single source of leverage** for the whole class-
features roadmap — every Phase-3 work item under A becomes simpler
once the economy framework exists.

**Data model:**

Per combatant, on `battle.combatants[i].economy`:

```js
economy: {
    action: false,    // used this turn; cleared on nextTurn()
    bonus:  false,    // used this turn; cleared on nextTurn()
    reaction: false,  // used since the combatant's last start-of-turn;
                      // clears at the START of their next turn (so it
                      // persists across other combatants' turns within
                      // the same round)
    movement: 0,      // feet used this turn (informational; the GM may
                      // or may not enforce; for now just an integer
                      // that scales with token-drag distance)
}
```

Persists with the rest of battle state via the existing `saveBattle()`
localStorage path + the WS broadcast in `pushBattle()`. Resets driven
by the existing `nextTurn()` / `prevTurn()` / `startInitiative()`
control flow in `tabletop.html`.

**Ability metadata — where the action-cost tag lives:**

Each ability button carries `data-economy="action"|"bonus"|"reaction"|"free"|"none"`.
Sources:

- **Weapon attacks** (PC `.mini-strike-btn`, monster `.monster-strike-btn`,
  full-sheet `.atk-strike`) — default `action`. Off-hand
  Two-Weapon-Fighting attacks tag as `bonus`. Auto-tag at render time
  from the attack's `properties` field (presence of `"light"` +
  off-hand context → bonus).
- **Spells** (`mini-cast-btn`, `.sp-cast`) — parse `spell.casting_time`
  at render time. Map "1 action" → `action`, "1 bonus action" → `bonus`,
  "1 reaction" → `reaction`, anything longer (10 min, 1 hour) → `none`
  (out-of-combat — doesn't consume an in-combat slot). For SRD spells
  this field is already populated; for homebrew it's whatever the
  homebrew editor put there.
- **Channel Divinity options** — curated per the Channel Divinity 3-phase
  plan in `dnd5e_channel_divinity.js`. Each option has an
  `economy: "action"|"bonus"` field. Turn Undead is `action`; Preserve
  Life is `action`; War Domain's Guided Strike is `reaction`; etc.
- **Class features** — new curated table `dnd5e_feature_economy.js`
  mapping `(class_slug, feature_key)` → economy tag for non-spell,
  non-attack abilities (Cunning Action: bonus, Second Wind: bonus,
  Action Surge: free, Rage entry: bonus, Lay on Hands single use:
  action, etc.). Same shape as the existing `dnd5e_class_resources.js`
  recipe table.

**UI surface:**

Three chips inside the v2.4.21-streamlined init-card status row,
right-aligned after Tmp:

```
HP 33/33 · AC 18 · Spd 25 · Tmp 0   [Act ●] [Bns ○] [Rxn ○]
```

- Filled circle ● = used; empty ○ = available
- Color: green when available, amber when used
- Click a chip to manually toggle (GM override — clearing a slot mid-turn
  if a feature returned a use, marking a slot used for off-screen
  effects)
- Tooltip on hover/long-press explaining what consumed the slot ("Used
  for: Healing Word at 14:32")

When a slot is used, ability buttons tagged with the same economy class
get a `disabled-style` (50% opacity, cursor:not-allowed, but still
clickable for GM override). The disabled state signals "you've already
spent your bonus action" without preventing the click — the GM is
trusted to know when to override (e.g. Action Surge granted a second
action).

**Implementation phases:**

1. **Phase 1 — State model + manual toggle UI.** Add the `economy`
   object to combatants in `combatantFromToken` and the manual-add
   paths. Render the 3-chip strip in `renderBattle`. Hook click-to-toggle
   on each chip. Reset on `nextTurn` / `prevTurn` (action+bonus clear
   immediately; reaction clears when the *same* combatant's turn comes
   around again — track via a `_reactionResetOnNextTurn` flag). Ship as
   one commit; UI is immediately useful for manual tracking even without
   the auto-advance.

   **What to test in the VTT (after shipping Phase 1, currently v2.4.31):**
   1. Log in as the demo GM (`demo-gm@example.com` / `demopass`) at
      `/login` (use the v2.4.4 Fill button).
   2. Navigate to `/campaign/1` (the demo campaign auto-loads).
   3. Open the **Battle** drawer (the v2.4.5-renamed tab in the topbar).
      The init tracker is auto-populated from the v2.4.3 fix — 9
      combatants visible.
   4. Each combatant row should show three small chips under the
      Init/HP subline: `○ Act` · `○ Bns` · `○ Rxn` — all empty green
      circles (available).
   5. Click any chip → it flips to filled amber (●) and the tooltip
      changes to "used this turn". Click again → flips back. Repeat
      across all three chips on one combatant.
   6. Click **Next turn** (or the Next button if you've started
      initiative) → advance to the next combatant. The chips on the
      *new* active combatant reset to empty green; chips on the
      previous combatant stay where they were.
   7. Click **Start Initiative** → every combatant's chips reset to
      empty. Re-test the toggle on combatant 1, advance turns through
      the full round → chips reset correctly each time `turn_index`
      lands on a combatant.
   8. Reload the page → chips state persists for combatants whose
      slots were "used" (localStorage round-trip via `saveBattle`).
   9. Open the same campaign in a second browser tab as the GM →
      toggling a chip in tab A updates tab B within a second (via the
      WS `battle_update` broadcast from `pushBattle`). Players in the
      same campaign see read-only chip state (they can't toggle).

   **Demo updates required for Phase 1:** None. Chips render for any
   combatant whose `economy` field is initialized (which `combatantFromToken`
   handles at construction time + `_ensureEconomy` heals stale localStorage
   entries). The existing 9-combatant Tavern Brawl from v2.4.3+ exercises
   every code path: PCs (Pip / Thalindra / Tavik) with full mini-bodies,
   monsters with `buildMonsterInitSheet`, mixed initiative order. **Already
   shipped in v2.4.31; no demo seed change needed.**

2. **Phase 2 — Auto-advance from action / strike / cast buttons.** Each
   click on `.mini-strike-btn` / `.monster-strike-btn` / `.atk-strike`
   / `.mini-cast-btn` / `.sp-cast` reads its `data-economy` and marks
   the corresponding slot on the combatant's `economy` object. Spell
   `casting_time` parsing happens at template-render time for the full
   sheet, at `combatantFromToken` time for the mini-sheet monster
   actions, at the spell-row render in `_mini_sheet_card.html` for PCs.

   **What to test in the VTT after shipping Phase 2:**
   1. As the demo GM in `/campaign/1`, open the Battle drawer + start
      initiative. Verify Pip Quickfingers' (or any PC's) Act/Bns/Rxn
      chips begin empty.
   2. Expand Pip's init-card → click 🗡 Strike on the Shortsword
      attack. Expected: the roll fires in the roll log AND Pip's
      Act chip flips to filled amber. The Bns and Rxn chips stay
      empty.
   3. Click 🗡 Strike on the Dagger (also an action). Expected: roll
      fires; Act chip stays amber (already used); no Bns/Rxn change.
      The chip's "tooltip" should say "used this turn" but the click
      isn't blocked yet (gating is Phase 4).
   4. Open Thalindra Moonwhisper's init card → click 🪄 Cast on
      Healing Word (a 1-bonus-action spell). Expected: roll fires AND
      her Bns chip flips amber. Act stays empty.
   5. Click 🪄 Cast on Fireball (a 1-action spell). Expected: roll
      fires AND Act chip flips amber.
   6. Click 🪄 Cast on Shield (a 1-reaction spell). Expected: roll
      fires AND Rxn chip flips amber.
   7. Expand Vex (Bandit Captain) → click 🎯 Attack on Scimitar.
      Expected: monster action roll fires AND Vex's Act chip flips
      amber.
   8. Click **Next turn** until it cycles to Pip → all three chips
      reset to empty. Re-trigger steps 2-6 to confirm the cycle.

   **Demo updates required for Phase 2:**
   - Add `casting_time` field to every spell entry in `_wizard_sheet`
     and `_cleric_sheet` in `app/demo_seed.py`. The Phase 2 renderer
     reads `s.casting_time` directly to emit `data-economy` on the
     cast button; without it, every spell falls back to "action".
     Values per SRD: Fire Bolt / Mage Hand / Prestidigitation / Sacred
     Flame / Guidance / Light = "1 action"; Magic Missile / Shield /
     Cure Wounds / Healing Word / Bless = "1 action" except Shield
     ("1 reaction") and Healing Word ("1 bonus action"); Misty Step
     "1 bonus action"; Spiritual Weapon "1 bonus action"; Scorching
     Ray / Fireball / Counterspell = "1 action" except Counterspell
     ("1 reaction"); Hold Person / Lesser Restoration "1 action";
     Beacon of Hope / Revivify "1 action"; Spirit Guardians "1 action";
     Mass Healing Word "1 bonus action".
   - Verify Vex (Bandit Captain) has at least one attack with explicit
     `attack_roll: True` so the monster-strike branch exercises the
     auto-advance. (Already true in v2.3.31 — no change needed.)
   - **Heads-up:** the v2.4.19 lazy-loader (`/api/content/spells/<slug>`)
     can serve as a fallback for spells without inline `casting_time` —
     Phase 2 should read the SRD record on first click if `s.casting_time`
     is missing. Adding the field to the seed is the cleaner / faster
     path for the demo specifically.

3. **Phase 3 — Class-feature economy table.** Author
   `app/static/dnd5e_feature_economy.js` with the canonical per-feature
   action tag table. Used by the resource option-picker (Channel
   Divinity, Bardic Inspiration, Ki spend, etc.) to mark the right slot
   when the option is fired. The Channel Divinity 3-phase plan can drop
   its per-feature action-cost tracking and read from this table.

   **What to test in the VTT after shipping Phase 3:**
   1. (Requires Channel Divinity option-picker, prerequisite item #2
      on the priority list.) As the demo GM with Brother Tavik (Life
      Domain Cleric Lv 5), open the Battle drawer → expand Tavik's
      init-card.
   2. Click the Channel Divinity counter chip → option overlay opens
      with `Turn Undead` and `Preserve Life`. Click Turn Undead.
      Expected: CD counter decrements (1/1 → 0/1), the slot-DC roll
      fires to the log, AND Tavik's Act chip flips amber (Turn Undead
      is an action per `_CHANNEL_DIVINITY_OPTIONS.life`).
   3. Click Next turn through one full round so Tavik's slots reset.
      Click CD chip again → pick Preserve Life. Expected: same flow,
      Act flips amber (Preserve Life is also an action).
   4. If/when Pip's Cunning Action lands (Rogue Lv 2 feature, also
      Phase 3-tagged): click Cunning Action → Bns flips, Act stays
      empty. Click Action Surge (Fighter Lv 2 if a Fighter PC is
      added): no chip changes — Action Surge is `free` (it grants an
      extra action, doesn't consume one).

   **Demo updates required for Phase 3:**
   - Pip's `_rogue_sheet` in `app/demo_seed.py` needs an entry in a
     new `features` or `class_abilities` array on the sheet so the
     sheet renderer + curated feature_economy table can emit a
     clickable "Cunning Action" button (with a sub-picker for Dash /
     Disengage / Hide). The feature is unlocked at Rogue Lv 2; Pip
     is Lv 5, so it applies. Without this, the most visible Phase 3
     test (Pip clicks Cunning Action → Bns flips) has no UI to click.
   - Tavik's Channel Divinity counter from v2.4.15 already exists; the
     CD option-picker (priority item #2) ships it as a clickable.
     Phase 3 just needs `_CHANNEL_DIVINITY_OPTIONS.life` entries to
     carry `economy: "action"` per the Channel Divinity 3-phase plan.
     No new seed data; just the curated JS table needs the `economy:`
     field added to each option.
   - Optionally: add a Fighter PC to the demo party (Vex's bandits are
     fighter-shaped but treated as monsters; a real Fighter Lv 1+ PC
     would let Phase 3 exercise Action Surge + Second Wind). Out of
     scope for Phase 3 itself; filed as a separate demo-data follow-up.

4. **Phase 4 — Gating + over-budget messaging.** Disable buttons whose
   economy slot is used (50% opacity + cursor:not-allowed). The player-
   facing warning lives in **three layers** of escalating commitment so
   nothing gets through silently but the GM isn't pinged for every
   legitimate retry:

   - **Layer A — tooltip on hover.** Passive. Shows on any mouse-over
     of a dimmed button:
     > "Action already used this turn — your Act slot is spent. Click
     > to override."
     Copy varies per slot ("Bonus action already used", "Reaction
     already used since your last turn"). Tooltip uses the standard
     `title=""` attribute so it works on desktop hover + iPad
     long-press without any new infrastructure.
   - **Layer B — confirm modal on click.** Active, blocking. When a
     player clicks a dimmed button, a small modal interrupts:
     > "You've already used your action this turn. Roll the [attack
     > name / spell name] anyway?"
     "Cancel" closes the modal without firing the roll. "Confirm"
     fires the roll AND records an over-budget marker (see Layer C).
     The modal copy includes the action name + the player's
     character name so it's obvious what's about to happen at a
     shared screen.
   - **Layer C — roll-log audit entry.** Whenever a player confirms an
     over-budget action, the roll-log entry that gets posted carries
     an over-budget badge:
     > 🗡 **Pip Quickfingers** rolls Dagger → 18 hit
     > ⚠ *Manual override: 2nd action this turn*
     The badge is visible to every participant (GM + all players),
     not just the rolling player. This serves as the audit trail
     the GM needs without requiring a separate WS push — the GM is
     already watching the roll log during play, so flagging the
     entry inline makes the violation obvious without spam.

   **GM bypass:** the GM (and admins) skip Layer B entirely — a dimmed
   button still fires on click without a modal interrupt, since the GM
   is the rules authority and doesn't need a confirmation prompt. The
   Layer C audit entry still fires (so a GM rolling a creature's
   second action this turn still gets the ⚠ marker). The GM can also
   shift+click a player's combatant chip to clear the slot mid-turn
   (e.g. "Action Surge granted Pip a second action — clearing Act so
   the player can roll their second attack normally").

   **House-rule-aware messaging.** When `campaign.potions_as_bonus_action`
   (v2.5.0) is on AND the over-budget click is on a Healing Potion's
   "Use Item" button, the Layer B modal copy adapts:
     > "You've already used your bonus action this turn (house rule:
     > potions consume bonus action). Drink the potion anyway?"
   Same Layer C entry, just different modal copy. Future house rules
   that affect specific buttons should follow the same per-rule copy
   override pattern; the framework reads from a small `_economyCopy`
   lookup keyed on `(slot, source)`.

   **What to test in the VTT after shipping Phase 4:**
   1. As Pip the player (`demo-alice@example.com`), click 🗡 Strike on
      Shortsword. Act flips amber.
   2. Hover over the dimmed 🗡 Strike on the Dagger. **Layer A:**
      tooltip shows "Action already used this turn — your Act slot is
      spent. Click to override." Cursor is `not-allowed`.
   3. Click the dimmed Dagger button. **Layer B:** confirm modal:
      "You've already used your action this turn. Roll the Dagger
      attack anyway?". Click **Cancel** → modal closes, no roll fires,
      no log entry.
   4. Click Dagger again, then **Confirm** on the modal. Expected:
      roll fires AND the roll log entry includes an over-budget
      badge: "⚠ Manual override: 2nd action this turn" below the
      attack roll. **Layer C** confirmed.
   5. Other players (open `demo-bob@example.com` in a second browser)
      see the same Layer C audit entry in their roll log — the badge
      is visible to everyone, not just the rolling player.
   6. As the GM (`demo-gm@example.com`), click a dimmed button on any
      combatant → no Layer B modal; roll fires immediately. Layer C
      audit entry still posts (so the violation is logged even when
      the GM initiates it).
   7. As the GM, **shift+click** a player's chip to clear the slot
      mid-turn — chip flips back to empty green. Then click the
      dimmed button → it's no longer dimmed (slot was cleared), no
      modal, no audit badge. Models the "Action Surge granted an
      extra action" override case.
   8. Enable the v2.5.0 `potions_as_bonus_action` house rule in
      campaign settings. As Tavik the player, drink a Potion of
      Healing once → Bns flips amber. Try to drink a second potion →
      Layer B modal copy now reads: "You've already used your bonus
      action this turn (house rule: potions consume bonus action).
      Drink the potion anyway?". The Layer C badge below the heal
      roll: "⚠ Manual override: 2nd bonus action this turn (potion)".
   9. Click Next turn. The chips reset to empty; buttons return to
      full opacity. Any tooltips clear.

   **Demo updates required for Phase 4:** None directly. Phase 4 is
   pure UI/UX layered on Phase 2's auto-advance — any combatant whose
   slot gets flipped by Phase 2 also gets buttons dimmed by Phase 4.
   The demo's existing spell + attack rosters from Phase 2's data
   updates exercise every code path. Optional: a one-line tooltip
   string update in the explainer for the v2.5.0 settings
   `potions_as_bonus_action` toggle, dropping the "currently
   informational" hedge once Phase 4 actually gates the slot.

5. **Phase 5 — Movement tracker (optional).** Add a `Mov 30/30 ft`
   chip; auto-decrement when the GM drags a token (the existing
   `/api/.../token/.../move` endpoint already broadcasts moves with
   from/to coordinates — tie into that to compute distance moved and
   subtract from the budget).

   **What to test in the VTT after shipping Phase 5:**
   1. As the demo GM on `/campaign/1`, start initiative on the Tavern
      Brawl. The active combatant's init-card should show a fourth
      chip: `Mov 30/30 ft` (Pip's speed) or whatever each combatant's
      `sheet.speed` is.
   2. Drag Pip's token on the canvas by 2 grid cells (140 px at 70
      px/cell = 2 squares = 10 ft). Expected: the chip updates to
      `Mov 20/30 ft`.
   3. Drag again by 3 grid cells (15 ft). Expected: chip updates to
      `Mov 5/30 ft`.
   4. Drag past the budget — drag another 2 cells (10 ft). Expected:
      chip shows `Mov 0/30 ft` in red or amber (overrun indicator) —
      the drag isn't blocked (the GM can always override), just
      flagged visually.
   5. Click Next turn → Pip's movement resets to `Mov 30/30 ft`.
   6. (Optional) Click the Mov chip → manually edit the value, e.g.
      to reflect a Dash bonus action that doubled the budget for
      this turn.

   **Demo updates required for Phase 5:**
   - Every demo combatant already has a `speed` field. Tavik's
     `_cleric_sheet` has `speed: 25` (Hill Dwarf); Pip has `speed: 25`
     (Halfling); Thalindra has `speed: 30` (Elf); the NPC templates
     ship per the SRD. **No seed change needed for PCs.**
   - For monsters whose template `sheet.speed` is a structured dict
     (e.g. Grixxa's `{"walk": 30}` from `seed_homebrew_files`),
     Phase 5 needs to read `sheet.speed.walk` rather than `sheet.speed`
     directly. The homebrew speed shape is already a dict for every
     demo monster; Phase 5's chip-render code should handle both
     scalar (PC sheets: `speed: 25`) and dict (monster sheets:
     `speed: {walk: 30}`) shapes. **Code change in Phase 5, not seed
     data.**
   - The grid scale is per-map: `map.grid_size_px = 70` on the demo
     tavern with `grid_type = "square"`. 5 ft / square is the 5e
     default; Phase 5 should hardcode `5 ft per grid cell` initially
     and read it from a per-campaign setting only if/when a non-5-ft
     grid case appears.

**Dependencies:**

- Sits between (B) roll-time intercepts and (C) buff slot in the
  cross-cutting graph. (B) wants to know "what kind of action is this
  roll" — the economy tag answers it. (C) wants to know "what activated
  this buff" — same.
- Phase 1+2 are independent and shippable on their own.
- Phase 3 depends on the Channel Divinity option-picker existing
  (cross-cutting A's Phase 1).

**What unblocks after each phase:**

- After Phase 1 (manual): GMs can manually track action economy during
  play. No mechanical gating, but it's immediately useful.
- After Phase 2 (auto-advance from buttons): Attacks / spells auto-mark
  their slot. Players see Healing Word's "bonus" tag illuminate when
  they cast it. Heuristics for Sneak Attack / Two-Weapon Fighting still
  need tuning.
- After Phase 3 (feature table): Cunning Action / Second Wind / Action
  Surge / Bardic Inspiration / etc. all have correct slot tagging
  without per-feature code changes — just adding an entry to the
  table.
- After Phase 4 (gating): The action economy becomes UI-enforced
  rather than just visible. Mistakes get flagged before they happen.
- After Phase 5 (movement): The fifth column closes the "what can my
  character still do this turn" UX gap.

**Related: house-rule toggles (shipped piecemeal alongside the
economy phases).** Per-campaign Boolean preferences on the `Campaign`
model affect how the economy framework interprets specific button
clicks. First example landed in v2.5.0: `potions_as_bonus_action`.

**What to test in the VTT for the `potions_as_bonus_action` toggle
(v2.5.0):**

1. As the demo GM (`demo-gm@example.com`), navigate to
   `/campaign/1/settings`.
2. Scroll to the **📜 House rules** fieldset (between the
   GM-font-override section and the 🎵 Audio fieldset).
3. The checkbox "Potions are a bonus action" should render unchecked
   by default (RAW). Below it: explainer text flagging the rule as a
   Xanathar's / Tasha's variant + a note that the toggle is currently
   informational until action-economy Phase 2 ships the "Use Item"
   button on consumable inventory items.
4. Tick the checkbox → click the form's **Save** button at the bottom
   of the page. Expected: redirect / re-render with the checkbox now
   ticked. Reload the page → still ticked (persisted via the v54
   schema column `campaigns.potions_as_bonus_action`).
5. Untick + Save → checkbox unticks, persists.
6. Verify the DB column directly (operator sanity check):
   `docker exec simplevtt-db psql -U simplevtt -d simplevtt -c
   "SELECT id, name, potions_as_bonus_action FROM campaigns;"` →
   shows the toggle value matching the UI.
7. (After action-economy Phase 2 + the "Use Item" potion button
   land): with the checkbox on, click the Use button on a Healing
   Potion item on Tavik's sheet. Expected: HP increases, qty
   decrements, AND Tavik's Bns chip flips amber. With the checkbox
   off, the same click flips Act chip amber instead. This step is
   filed for the Phase 2 follow-up.

**Demo updates required for the house-rule toggle to be testable
end-to-end:**

- v2.5.0 ships the column + the settings checkbox. Steps 1-6 above
  are runnable today.
- Step 7 (the actual mechanical effect) is gated on **two** future
  pieces:
  1. The action-economy Phase 2 work that adds `data-economy` tags
     + auto-advance to inventory item buttons.
  2. A **"Use Item" button on consumable inventory rows** in
     `sheet_dnd5e.html`. The row's existing equip toggle / qty input
     / × delete cluster doesn't include a "Use" action; v2.4.13's
     rich-item shape supports `type: "consumable"` but the sheet
     renders consumables identically to gear today. Adding the Use
     button is a small follow-up (~30 LOC: a button in the row,
     a click handler that decrements qty + posts to the HP endpoint
     + marks the economy slot per `campaign.potions_as_bonus_action`).
- **Seed updates required to test end-to-end:** add a
  `{name: "Potion of Healing", type: "consumable", qty: 1, _slug:
  "potion-of-healing", desc: "..."}` entry to each PC's inventory
  in `app/demo_seed.py`. The SRD ships
  `app/data/local/dnd5e/items/potion-of-healing.json` so the v2.4.13
  `_loadItemActions` lazy-loader fills in the description on first
  row-expand. Suggested per-PC counts: Pip 2 (rogue stash), Tavik 3
  (cleric's emergency reserve), Thalindra 1 (wizard backup).

---

## Order of priority (rough)

Updated for v2.9.3. ~~Strikethrough~~ items are shipped.

1. ~~**(E) Action-economy tracker — Phase 1+2** — manual chip strip + auto-advance from existing strike / cast buttons.~~ ✅ shipped v2.4.31 (Phase 1) + v2.5.3 (Phase 2) + v2.5.5 (Phase 2b full-sheet sync).
2. ~~**Channel Divinity option-picker.**~~ ✅ shipped v2.9.0 with the reusable `showResourceOptionPicker` helper. Life Domain end-to-end; other domains need their `_FEATURE_ECONOMY` option entries (see per-class plans below — short follow-up per domain).
3. **Lay on Hands target-picker.** Needs a numeric amount picker (HP to spend, max = pool) layered on top of `showResourceOptionPicker`. Plus a target-picker overlay (click a token / pick from init roster). Now mostly a UX assembly job since the resource picker exists. See per-class plan.
4. **Wild Shape transformation UI.** `_doMiniTransform` is half-wired (beast picker exists for Druids). Finishing the form-picker dropdown closes Druid Lv 2 functionality. See per-class plan.
5. **Bardic Inspiration target-picker.** Same target-picker primitive as #3 (just no amount picker — pick target → "Bardic Inspiration to X" log entry + give X a d6/d8/d10/d12 die). Completes Bard core loop. See per-class plan.
6. ~~**(E) Action-economy — Phase 3+4** — class-feature table + gating with GM override.~~ ✅ shipped v2.6.0 (Phase 3 curated table) + v2.6.1 (Phase 4 gating) + v2.7.2 (Phase 4a dimming) + v2.8.0 (strict mode).
7. **Cross-cutting (A) generalized.** Refactor LoH / Wild Shape / Bardic Inspiration / Ki / Sorcery Points onto a single `resource → option → target → effect` framework. Now post-shipping #3-5 since the abstraction emerges from the concrete cases.
8. **Sneak Attack / Divine Smite per-attack uplift toggle.** Pair of adjacent damage-uplift features; each is a per-attack toggle that fires extra damage dice on the resulting damage roll. Depends on (B) for the post-attack damage-up intercept. See per-class plans (Rogue Sneak Attack, Paladin Divine Smite).
9. **(B) Roll-time intercepts.** Big architectural work; unblocks Lucky / Indomitable / Reliable Talent / Portent / Champion Improved Critical. The roll-toast popup (`/static/roll_toast.js`) is the most natural insertion point: pause the toast animation, surface intercept buttons under the dice, fire follow-up rolls / replace value before the toast lands. Filed as a separate plan doc when work begins.
10. **(C) Buff slot.** Even bigger; unblocks every concentration spell + Bless / Reckless Attack / Guided Strike / etc. Buff entries should carry name + duration + mods + expiration trigger + source. The existing concentration-tracker UI from v2.1.x is the closest precedent. Filed as a separate plan doc when work begins.
11. **(D) Passive trait engine.** Likely subsumed by (B) once the intercept exists. Each race trait registers a callback on a specific roll type (e.g. "STR save against poison" → advantage) that the intercept evaluates.
12. ~~**(E) Action-economy — Phase 5** — movement tracker.~~ ✅ shipped v2.6.2 (chip) + v2.8.1-2 (breadcrumb) + v2.8.3 (Dash modal).

Items 3-5 are the next-up user-visible wins. 7-11 are infrastructure
that pays for itself across many features once shipped.

---

## Per-feature implementation plans (⚪ → 🟠)

This section catalogues every ⚪ class feature with at least a one-
paragraph plan so the contributor picking it up doesn't have to start
from scratch. Plans are tight by design — they identify the
implementation hook (which infrastructure piece A/B/C/D/E the feature
leans on), an estimated complexity (S = small, ~50-150 LOC; M =
medium, ~150-400 LOC; L = large, may need its own design doc), and
dependencies. Once a feature ships, its row in the per-class table
above flips to ✅ and the plan paragraph here can be deleted (or kept
as historical context — your call).

### Barbarian

- **Reckless Attack (Lv 2)** — S. Toggle on the attack panel. When on, the
  next melee STR attack rolls with advantage and incoming attacks until
  the barbarian's next turn have advantage against them. Implementation:
  per-attack toggle alongside Sneak Attack uplift (#8 in priority list);
  the "incoming attacks have advantage" half is a buff slot entry (C).
  Without (C), ship the outgoing-advantage half first; the incoming
  passive sticks to a manual note in the conditions list.
- **Danger Sense (Lv 2)** — S. Passive advantage on DEX saves against
  effects you can see. Pure (D) passive trait engine territory. Deps:
  (D). Until (D) lands, players manually click advantage on the DEX save
  roll-state pill.
- **Rage damage / resistance / advantage side effects (Lv 1, augments existing 🟢 counter)** —
  M. The counter works (v?.x). Missing: +2/+3/+4 damage on STR melee
  attacks (scales with level), resistance to bludgeoning/piercing/slashing,
  advantage on STR checks + saves. All three pieces want (C) buff slot
  to attach the modifiers. Deps: (C). When Rage is active, the buff slot
  feeds modifiers into the attack/damage/check intercepts.
- **Fast Movement (Lv 5)** — S. +10 ft speed when not wearing heavy
  armor. Implementation: extend `_speedWalkFromSheet` (or a sibling
  `_effectiveSpeed`) to add 10 ft when class === Barbarian, level ≥ 5,
  AND no equipped heavy armor. No deps.
- **Feral Instinct (Lv 7)** — M. Advantage on initiative + can act on
  surprise round if raging. Advantage part = (D) passive on init rolls;
  surprise-act needs a new "surprise" state on the init tracker (which
  doesn't exist today — surprise is hand-waved by the GM). Deps: (D).
  Surprise state is its own minor plan; deferred.
- **Brutal Critical (Lv 9 / 13 / 17)** — M. Extra damage dice on melee
  crits (1/2/3 extras). Implementation: damage-roll uplift triggered by
  crit detection — same surface as Divine Smite / Sneak Attack (priority
  #8). Deps: (B) for crit intercept. Ship after #8.
- **Relentless Rage (Lv 11)** — M. When dropped to 0 HP while raging,
  make a DC 10 CON save (escalates by 5 per use this short-rest) to drop
  to 1 HP instead. Implementation: hook into `_apply_hp_change`'s
  dying-transition (already exists for the v2.1.x death-save state
  machine). If the character is raging, prompt the CON save before
  applying the 0-HP transition; on success, clamp HP at 1. DC tracking
  needs a per-short-rest counter. Deps: (C) for the rage-is-active
  check (or a manual conditions check until (C) lands).
- **Persistent Rage (Lv 15)** — S. Rage no longer ends early from "no
  attack / no damage taken" — only from incapacitation or being knocked
  out. Implementation: just a flag on the Rage buff entry. Deps: (C).
- **Indomitable Might (Lv 18)** — S. Floor on STR checks = STR score.
  Implementation: clamp the d20 result before adding mods on STR ability
  checks — needs a roll-time intercept hook. Deps: (B).
- **Primal Champion (Lv 20)** — S. STR/CON +4 (cap 24). Implementation:
  a one-line tweak in the level-20 ASI ceiling check + the cap. No
  intercept needed; the ability scores just go up to 24. No deps.
- **Unarmored Defense (Barbarian, Lv 1)** — S. AC = 10 + DEX + CON when
  no armor (shield OK). Implementation: extend `computeEffectiveAC` in
  `sheet_dnd5e.html` to detect class === Barbarian + no armor and apply
  the formula. Already a similar branch exists for Mage Armor / etc. No
  deps.
- **Extra Attack (Lv 5)** — M. (Shared with every martial class.) The
  Attack action grants 2 (or more) attack rolls. Implementation: the
  attack panel could mark each weapon's Strike as "Attack 1/2" with a
  combined button, or just leave the current per-attack behaviour and
  add a tooltip "Lv ≥ 5 — you can make a 2nd attack as part of this
  Attack action". Action-economy stays correct either way because the
  Attack action is a single Act slot. Deps: none, but UX-wise it ties
  to action-economy.

### Bard

- **Bardic Inspiration (Lv 1, augments 🟢 counter)** — M, **priority #5**.
  Click Use on the counter → target picker overlay (list of allies +
  self exclusion). Pick a target → roll-log entry "✨ Pip Quickfingers
  gains a Bardic Inspiration d8 from Tavik (10 min duration)". Until
  (C) buff slot exists, the recipient tracks the die manually — but the
  log entry is the audit trail. Target picker primitive is also #3 (LoH)
  and shares between them. Deps: target picker (new shared helper); (C)
  for proper buff tracking, optional.
- **Jack of All Trades (Lv 2)** — S. Add half PB (round down) to
  non-proficient ability checks. Implementation: ability-check roll
  engine adds `+floor(PB/2)` when proficient flag is off AND class
  includes Bard ≥ 2. Deps: (B).
- **Song of Rest (Lv 2, augments 🟢 counter)** — S. During a short rest,
  each ally that spends a Hit Die regains +1d6 (1d8 at Lv 9, 1d10 at
  Lv 13, 1d12 at Lv 17) extra HP. Implementation: when the short-rest
  endpoint processes Hit Die spending, look for any party member with
  Bard ≥ 2 and add the bonus die per HD spent. Trivial wiring; the
  bonus dice apply once per rest regardless of how many bards are
  resting. Deps: short-rest endpoint surface (already exists).
- **Countercharm (Lv 6)** — M. Action; allies within 30 ft get advantage
  on saves vs fear/charm until your next turn. Implementation: buff slot
  entry granting advantage on those specific save types within range.
  Deps: (C). Action button on sheet decrements Act slot.
- **Magical Secrets (Lv 10/14/18)** — S. Pick 2 spells from any class
  list every 4 levels. Implementation: the existing spell picker is
  class-filtered; just remove the filter for these picks (add a "From
  any class list" checkbox in the picker UI that bypasses the filter).
  Per-bard tracking: store the picked spells with a `_via: "magical-
  secrets"` marker so they're flagged. No deps.
- **Font of Inspiration (Lv 5)** — already 🟡 with implicit short-rest
  refill via the resource counter's `reset: "short"`. No code change
  needed; the description is accurate. Mark ✅ once the Bardic
  Inspiration target-picker ships (the counter behaves as expected
  today; only the picker is missing).
- **Superior Inspiration (Lv 20)** — S. On rolling initiative, regain
  1 BI use if at 0. Implementation: hook into the init-roll flow
  (the v?.x roll-init-btn) — for every PC at Bard ≥ 20, if BI counter
  is at 0, set it to 1 and announce. Trivial. No deps.

### Cleric

- **Channel Divinity — Knowledge / Light / Nature / Tempest / Trickery /
  War / Forge / Grave / Order / Peace / Twilight (Lv 2)** — S per
  domain. Each domain has 1-2 options on top of Turn Undead. The v2.9.0
  picker already filters by subclass; just add the option entries to
  `_FEATURE_ECONOMY['channel-divinity'].options` with the correct
  `subclass` tag. SRD options to wire (one entry per option per domain):
  Knowledge → `knowledge-of-the-ages` (action — proficiency in a skill
  for 10 min), `read-thoughts` (action). Light → already has
  `radiance-of-the-dawn` from v2.6.0. Nature → `charm-animals-and-
  plants` (action). Tempest → `destructive-wrath` (free — maximises
  lightning/thunder damage on next roll). Trickery → `invoke-
  duplicity` (action — illusionary duplicate, 1 minute). War → already
  has `guided-strike` from v2.6.0. Forge → `artisans-blessing` (10 min
  ritual — out-of-combat, slot: "none"). Grave → `path-to-the-grave`
  (action — vulnerability for next attack). Order → `order's-demand`
  (action — Wis save or charm). Peace → `balm-of-peace` (action — heal
  on allies you pass by). Twilight → `twilight-sanctuary` (action —
  1-minute aura). Deps: none — purely data entries on the existing
  curated table.
- **Destroy Undead (Lv 5+)** — S. Tied to Turn Undead — when undead
  within a CR threshold fail the Wisdom save, they're destroyed instead
  of fleeing. Implementation: side effect on the Turn Undead
  announcement — after the save prompt resolves, low-CR undead that
  failed get a "destroyed" flag and lose their HP. Deps: Turn Undead's
  save-prompt flow (currently just the feature_used roll-log entry
  from v2.9.0 — no actual save mechanic yet). Filed as part of the
  broader save-prompt-on-feature plan.
- **Divine Intervention (Lv 10)** — M. Roll d100 — if ≤ cleric level
  (or any value at Lv 20), divine aid arrives. Implementation: special-
  purpose 1-per-week resource (so the existing rest system doesn't
  auto-refill it). New `/divine-intervention` endpoint rolls the d100,
  announces in the log, and updates the counter. Long-rest doesn't
  refill it; the GM manually refills on a successful invocation (per
  RAW the next 7 days are the cooldown). Deps: a new "weekly" reset
  kind in the resource recipe table (or just `manual` with the GM
  refilling on a long rest).

### Druid

- **Druidic (Lv 1)** — Pure descriptive language. No mechanic. Skip
  permanently unless a "private message / secret language" system is
  ever added (filed as nice-to-have but not on any roadmap).
- **Wild Shape (Lv 2, augments 🟢 counter)** — M, **priority #4**. Click
  Use on the counter → `BeastPicker.open` (already exists). Pick a
  beast → POST `/api/.../character/.../transform` which swaps the
  active sheet for the beast's stat block AND decrements the wild-
  shape counter.
  - **Sheet swap:** ✅ shipped (pre-2.0.0 endpoint + BeastPicker JS;
    harness coverage v2.14.4; action-economy chip integration v2.14.5;
    over-budget gate v2.14.6).
  - **Token swap on transform — TODO (design: token-disguise primitive).**
    When a druid Wild Shapes, the map token should reflect the new
    form. Today `/transform` mutates `sheet["active_form"]` but doesn't
    touch the character's Token rows — the mini-sheet shows the beast
    but the canvas still renders Mira's portrait + colour ring. **Design
    as a reusable mechanism** so the same primitive powers Wild Shape
    AND every other appearance-changing ability (Polymorph spell,
    Disguise Self, Alter Self, True Polymorph, future homebrew). The
    primitive is per-TOKEN (not per-character) because Polymorph can
    target an enemy whose token isn't tied to the caster's sheet.

    **Storage shape — new `Token.disguise` JSON column.** Schema bump
    when this ships. NULL when no disguise active. When set:
    ```json
    {
      "source": "wild-shape" | "polymorph" | "disguise-self" | "alter-self" | "true-polymorph",
      "caster_character_id": 42,           // who initiated the disguise
      "caster_user_id": 7,                  // for permission checks on revert
      "form_name": "Dire Wolf",             // display label for the badge
      "form_slug": "srd_dire-wolf",         // beast/creature key when applicable (null for Disguise Self illusions)
      "started_at": "2026-05-18T12:00:00Z",
      "concentration_caster_id": 7,         // null for non-concentration (Wild Shape, Disguise Self)
      "prior": {                            // snapshot for revert
        "label": "Mira Greenleaf",
        "image_url": "/static/uploads/portraits/mira.png",
        "size": "M",
        "color": "#4d9d6d"
      }
    }
    ```
    Storing on the Token (not on the caster's sheet) lets a
    Polymorph that targets an NPC bandit store the disguise on that
    bandit's token, independent of the bandit's Character row (which
    may not even exist for monster tokens). Stacking policy: a token
    can carry AT MOST ONE active disguise — the helper rejects with
    409 if `disguise` is already set (caller passes `force=True` to
    overwrite, which destroys the original `prior` snapshot — used
    only by Dispel Magic / GM force-revert flows).

    **Helper API (in `app/routes/tabletop_routes.py`):**
    ```python
    async def _apply_token_disguise(
        db, token, *,
        source: str,                  # required: "wild-shape" / "polymorph" / ...
        caster_character_id: int,
        caster_user_id: int,
        form_name: str,               # display label
        form_slug: str | None = None, # Open5e key when applicable
        new_label: str | None = None, # overrides token.label; default = form_name
        new_image_url: str | None = None,
        new_size: str | None = None,  # "T" / "S" / "M" / "L" / "H" / "G"
        new_color: str | None = None,
        concentration: bool = False,  # True for Polymorph/True Polymorph
        force: bool = False,          # overwrite existing disguise
    ) -> dict:
        """Snapshot the token's current visual fields into
        ``token.disguise["prior"]`` + apply the new values + broadcast
        ``token_update``. Returns the disguise dict.
        Raises HTTPException(409) if ``token.disguise`` is already
        set and ``force`` is False.
        """

    async def _revert_token_disguise(
        db, token, *,
        expected_source: str | None = None,  # safety: only revert if source matches
        actor_user_id: int,                    # for permission check
        actor_is_gm: bool = False,
    ) -> dict | None:
        """Restore token fields from ``token.disguise["prior"]`` and
        clear ``token.disguise``. Broadcasts ``token_update``.
        Returns the prior snapshot (or None if no disguise was set).
        Raises HTTPException(403) if actor_user_id is neither the
        original caster nor the GM. Raises HTTPException(409) if
        ``expected_source`` is provided and doesn't match the
        disguise's actual source (prevents accidental cross-source
        reverts — e.g. /revert on the druid sheet shouldn't accidentally
        end an unrelated Polymorph on the same token).
        """
    ```

    **Consumers:**
    - `/transform` (Wild Shape source): finds tokens where
      `token.character_id == char.id` and `token.disguise is None`,
      calls `_apply_token_disguise` for each. Image comes from the
      Open5e creature's `illustration` field when present;
      otherwise the token keeps its existing image (RAW Wild Shape
      doesn't enforce a visual swap — the token-image change is a
      UX nicety, not a rule). Size comes from `monster["size"]`.
    - `/transform` (Polymorph source) — same flow but `caster_user_id`
      is the spell caster (not necessarily the token's owner), and
      `concentration: True`. RAW Polymorph targets one creature;
      typically that's a target token the caster selected via a
      future target picker (extends the lay-on-hands picker to
      include enemy tokens).
    - `/revert`: calls `_revert_token_disguise` with
      `expected_source="wild-shape"` (or "polymorph") so the right
      disguise is ended.
    - Future Disguise Self endpoint: calls `_apply_token_disguise`
      with `source="disguise-self"`, `concentration: False`, and
      only `new_label` / `new_image_url` set (no size change — RAW
      Disguise Self is illusion-only, target's actual size is
      unchanged). Reverts via a Use-button click or a 1-hour timer.
    - Future Alter Self endpoint: similar to Disguise Self but the
      visual change is real (target genuinely becomes the new
      form). Concentration: True.
    - Future True Polymorph: same as Polymorph but
      `concentration: True` for 1 hour, then becomes permanent if
      sustained. The "becomes permanent" transition would clear the
      `concentration_caster_id` field (without reverting the
      disguise) so the disguise persists past concentration drop.

    **Edge cases:**
    - GM spawned multiple tokens of the same character (rare).
      Wild Shape applies to all of them by default; a future
      enhancement could let the caster pick which token to
      transform. Polymorph targets one specific token always.
    - NPC tokens that share `character_id` (e.g. a Mirror Image
      clone, a summoned beast). Wild Shape should NOT touch those
      — RAW is single-target. Gate via `token.is_summon` or a new
      `token.is_clone` flag if Mirror Image ever ships.
    - Token has a custom player-uploaded portrait. The snapshot
      pattern captures it, so revert restores correctly. The
      disguise replaces it for the duration.
    - Concentration coupling: Polymorph / True Polymorph drop when
      the caster loses concentration. Implementation: when a
      character takes damage, the WS broadcast that fires
      `concentration_check` (if/when that ships) also walks Token
      rows where `disguise.concentration_caster_id == char.id`
      and reverts each. Without concentration infrastructure, the
      caster manually reverts via the existing `/revert` flow.
    - Mass effects (a future homebrew "Mass Polymorph"): the
      primitive supports it — just loop over multiple tokens and
      apply individually. No new API needed.
    - Death of a Polymorphed creature: per RAW, the target reverts
      when it drops to 0 HP. Implementation: `_apply_hp_change`
      checks the disguise field; if HP hits 0 AND source is
      "polymorph", auto-revert before applying the dying state.
      Filed as a sub-piece for whoever ships Polymorph.

    **WS broadcast shape (existing `token_update`):**
    The full token payload already carries every field a client
    cares about, including the new `disguise` field once it exists.
    A client renders a small badge on disguised tokens
    (e.g. 🎭 for polymorph, 🐺 for wild-shape, 👤 for disguise-self)
    by reading `token.disguise.source`. No new broadcast type
    needed.

    **Implementation order (when this work is picked up):**
    1. Schema migration: add `Token.disguise` JSON column. Bump
       SCHEMA_VERSION. Backfill existing rows with NULL.
    2. Build `_apply_token_disguise` + `_revert_token_disguise`
       helpers. Unit-style tests via the harness (no UI yet).
    3. Wire `/transform` to call the helpers for Wild Shape source.
       Add Wild Shape size-swap (Mira → Dire Wolf changes size from
       M → L on the token). Harness assertion: after /transform,
       the token's label contains the form name AND its `size` reflects
       the beast.
    4. Wire `/revert` to revert the disguise alongside the sheet
       revert. Harness assertion: after /revert, the token's label
       + size restore.
    5. Polymorph: add a `/cast_spell` branch that detects
       `spell_slug == "polymorph"`, opens a target picker, calls
       `/transform` with `source="polymorph"` and the target's
       token. Filed for when Polymorph ships as a real interactive
       spell (currently it's a generic spell-cast announce).
    6. Disguise Self / Alter Self / True Polymorph: each new
       spell endpoint reuses the same helper.

    Filed for a future commit. Not blocking any other Phase B work.
    The design is intentionally bigger than a single Wild Shape
    feature so subsequent shape-changing abilities can plug in
    without re-litigating the storage shape.
- **Timeless Body (Lv 18)** — Pure descriptive. No mechanic.
- **Beast Spells (Lv 18)** — S. While Wild Shaped, can cast Druid spells
  (with verbal-only components allowed). Implementation: the
  transform endpoint currently swaps the spells panel out for beast
  abilities. For Druid Lv 18, keep the spells panel accessible alongside
  the beast actions. One-line conditional in the transform handler.
- **Archdruid (Lv 20)** — S. Wild Shape unlimited + spells without
  material components. Implementation: set the wild-shape resource max
  to a large sentinel (999), and for Lv 20 druids, the spell-cast
  endpoint skips any material-component check (which isn't enforced
  today anyway — Archdruid is a no-op until that check exists).

### Fighter

- **Fighting Style (Lv 1)** — M. Player picks one of 6 styles. Each is a
  small modifier. Implementation: dropdown on sheet → stored as
  `sheet.fighting_style: "archery"|"defense"|"dueling"|"great-weapon"|
  "protection"|"two-weapon"`. Archery (+2 ranged attack), Defense (+1
  AC in armor), Dueling (+2 damage on one-handed melee), Great Weapon
  Fighting (reroll 1s/2s on two-handed melee damage), Protection
  (reaction — impose disadvantage on attack vs ally), Two-Weapon
  Fighting (off-hand adds ability mod to damage). Most need (B) for
  the modifier intercepts; Defense is computed at sheet-render time
  (extend `computeEffectiveAC`). Deps: (B) for the attack/damage
  modifiers; (C) optional for Protection's reaction handling.
- **Second Wind (Lv 1, augments 🟢 counter)** — S. Click → bonus action,
  heal 1d10 + fighter level HP. Already tagged `bonus` in
  `_FEATURE_ECONOMY` from v2.6.0. Implementation: dedicated Use button
  on the resource row that opens a "Heal: 1d10 + N HP" roll-toast,
  applies via `_apply_hp_change`, decrements counter. Mirrors the
  v2.7.0 Potion-of-Healing Use button shape closely. Small follow-up.
- **Action Surge (Lv 2, augments 🟢 counter)** — S. Click → roll-log
  entry "Tavik Action Surges", decrements counter, and the GM clears
  the Act chip on the init tracker so the player can roll a second
  action. Already tagged `free` in `_FEATURE_ECONOMY`. The chip-clear
  is what the existing Phase 4 plan calls out as a "GM grants extra
  action" override. Small.
- **Extra Attack (Lv 5/11/20)** — see Barbarian Extra Attack above
  (shared). Lv 11 adds a 3rd attack; Lv 20 (Fighter only) adds a 4th.
- **Indomitable (Lv 9, augments 🟢 counter)** — M. Click → reroll a
  failed save. Implementation: needs a save-roll intercept that
  offers the reroll AFTER the save fails. Best as part of (B). Deps:
  (B). Until (B), the Use button can manually re-fire the same save
  roll on click + announce "Indomitable: rerolled X save → new total
  Y" in the log.

### Monk

- **Martial Arts (Lv 1)** — M. (1) Use DEX or STR (whichever is higher)
  for monk weapons + unarmed strikes. (2) Unarmed strike damage scales:
  d4 → d6 → d8 → d10 over levels 1/5/11/17. (3) Bonus-action unarmed
  strike after taking the Attack action. Implementation: (1) is a
  sheet-render-time decision in the auto-attack generator (which weapons
  are "monk weapons" — quarterstaff, shortsword, simple melee, etc.).
  (2) is a level-table lookup in the unarmed-strike damage. (3) is an
  action-economy hook — after firing the Attack action, suggest a bonus-
  action unarmed strike on the same panel. Deps: (B) for the damage
  scaling, action-economy already shipped.
- **Ki (Lv 2, augments 🟢 counter)** — M. Use button → option picker
  (same v2.9.0 helper) with: Flurry of Blows (1 ki, bonus), Patient
  Defense (1 ki, bonus, dodge), Step of the Wind (1 ki, bonus,
  dash/disengage + jump x2). All three already in `_FEATURE_ECONOMY`
  from v2.6.0. Implementation: extend the `.res-use` handler in
  `sheet_dnd5e.html` with a `k === 'ki'` branch mirroring the
  channel-divinity branch from v2.9.0. Per-option key gates the slot
  + posts feature_used. Small (~100 LOC).
- **Unarmored Defense (Monk, Lv 1)** — S. AC = 10 + DEX + WIS when no
  armor / no shield. Same pattern as Barbarian Unarmored Defense
  above. Extend `computeEffectiveAC`. No deps.
- **Unarmored Movement (Lv 2 +)** — S. +10 ft / +15 ft / +20 ft /
  +25 ft / +30 ft at Lv 2/6/10/14/18 when no armor / no shield.
  Implementation: speed normaliser extension (same hook as Barbarian
  Fast Movement above).
- **Deflect Missiles (Lv 3)** — L. Reaction; reduce ranged damage by
  1d10 + DEX + monk level; if reduced to 0, can spend 1 ki to throw it
  back. Needs an incoming-damage intercept (the damage-take side —
  doesn't exist yet) + a follow-up attack-roll surface for the throw-
  back. Filed under (B). Deps: (B), and a "damage taken" hook that
  doesn't exist today (today damage is computed by the GM and applied
  manually via HP edit — no client-side intercept).
- **Slow Fall (Lv 4)** — S. Reaction; reduce falling damage by 5 ×
  monk level. Same shape as Deflect Missiles' damage-intake intercept.
  Deps: (B), damage-take hook.
- **Stunning Strike (Lv 5)** — ✅ **shipped v2.49.55**. After a hit
  with a melee weapon attack, spend 1 ki; target makes CON save
  against the monk's spell-save DC (`8 + prof + WIS mod`); on fail,
  stunned until end of monk's next turn. Endpoint:
  `/api/campaign/{cid}/use_stunning_strike`. Stunned condition applied
  via the Phase C condition slot — the first non-concentration
  incapacitating-condition buff to land. Harness:
  `tests/harness/test_use_stunning_strike.py` including a PC
  integration case.
- **Ki-Empowered Strikes (Lv 6)** — S. Unarmed strikes count as magical
  for the purposes of bypassing resistance. Pure damage-type tag —
  attach `magical: true` to monk unarmed strikes at level 6. Deps: a
  damage-resistance check exists in the damage application path
  (currently the GM applies damage manually so this is informational
  only).
- **Evasion (Lv 7)** — M. On a DEX save vs an effect that deals half
  damage on success, take 0 on success and half on failure. Same
  damage-take intercept as Deflect Missiles. Deps: (B), damage-take
  hook.
- **Stillness of Mind (Lv 7)** — S. Action: end one effect on yourself
  causing charm or fright. Implementation: action button → consult the
  conditions list, prompt the GM to remove the matching one. Trivial
  once buff slot (C) tracks conditions structurally.
- **Purity of Body (Lv 10)** — Pure descriptive (immunity to disease /
  poison). Deps: (D) passive trait engine for the immunities to
  auto-apply on saves; until then, descriptive only.
- **Tongue of the Sun and Moon (Lv 13)** — Pure descriptive.
- **Diamond Soul (Lv 14)** — Proficiency in all saves; spend 1 ki to
  reroll a save. Implementation: the proficiency part is a sheet-side
  flag (set all save proficiencies); the ki-reroll is same as Fighter
  Indomitable's reroll path. Deps: (B) for the reroll intercept.
- **Timeless Body (Lv 15)** — Pure descriptive.
- **Empty Body (Lv 18)** — Action; spend 4 ki for invisibility + damage
  resistance (1 minute, concentration). Or 8 ki to cast Astral
  Projection. Implementation: action button decrements ki + adds a
  buff slot entry. Deps: (C).
- **Perfect Self (Lv 20)** — S. Regain 4 ki if at 0 on initiative roll.
  Same shape as Bard Superior Inspiration above. No deps.

### Paladin

- **Lay on Hands (Lv 1, augments 🟢 counter)** — M, **priority #3**.
  Pool of HP (max = 5 × paladin level). Use button → amount picker
  (slider or input, max = pool) + target picker (list of allies + self).
  Pick → apply HP via `_apply_hp_change` to the target; subtract from
  pool. RAW also lets a single use cure poison or disease (no HP cost
  for one of those, fixed-cost 5 HP for the other — TBD on exact
  semantics). Implementation: amount picker is a new helper
  `showAmountPicker({min: 1, max: pool, onPick})`; target picker is
  shared with Bardic Inspiration. Deps: target picker primitive (new
  shared helper); amount picker primitive (new).
- **Divine Sense (Lv 1, augments 🟢 counter)** — S. Action; know if any
  celestial / fiend / undead is within 60 ft until end of next turn.
  Implementation: action button → roll-log entry, decrement counter,
  no other side effects (the GM tells the player what they sense).
  Small.
- **Fighting Style (Lv 2)** — see Fighter Fighting Style above (shared).
- **Divine Smite (Lv 2)** — M, **priority #8**. After hitting with a
  melee weapon attack, spend a spell slot to add 2d8 radiant (+1d8 per
  slot level above 1st, +1d8 vs undead/fiends, max 5d8). Implementation:
  per-attack toggle alongside Sneak Attack — when on, after a hit the
  damage panel offers "🌟 Smite with Lv N slot?" which fires the extra
  dice + decrements the slot. Deps: (B) post-attack hook. Already
  tagged `free` in `_FEATURE_ECONOMY` (smite doesn't consume action;
  the attack already did). Pair-ship with Sneak Attack.
- **Divine Health (Lv 3)** — Pure passive (disease immunity). Deps:
  (D) passive trait engine; descriptive only until.
- **Channel Divinity (Lv 3)** — S per Oath. Devotion (Sacred Weapon
  + Turn the Unholy), Ancients (Nature's Wrath + Turn the Faithless),
  Vengeance (Abjure Enemy + Vow of Enmity), etc. Same shape as Cleric
  CD — extend `_FEATURE_ECONOMY` with `channel-divinity-paladin` entry
  (separate from cleric since options differ entirely) and wire the
  picker on the resource Use. Deps: none beyond v2.9.0's primitive.
- **Aura of Protection (Lv 6 + 18)** — M. Allies within 10 ft (30 ft
  at Lv 18) add the paladin's CHA mod to saves. Implementation: pure
  passive — every save roll by an ally checks proximity to a paladin
  and adds the bonus. Needs (D) passive trait engine + proximity
  detection (the canvas knows token positions; the save-roll context
  doesn't). Deps: (D); medium architectural lift.
- **Aura of Courage (Lv 10 + 18)** — M. Allies within 10 ft / 30 ft
  immune to fear while paladin is conscious. Same shape as Aura of
  Protection — passive + proximity. Deps: (D).
- **Improved Divine Smite (Lv 11)** — S. Melee weapon damage adds 1d8
  radiant. Auto-applied to every melee hit (no slot cost). Damage-roll
  uplift triggered by hit detection. Deps: (B) post-attack hook
  (same as Divine Smite proper).
- **Cleansing Touch (Lv 14, augments 🟢 counter)** — S. Action; end one
  spell on a willing creature you touch. Implementation: action button
  → target picker → posts a "Cleansing Touch on X" entry; the GM
  manually removes the matching condition (until (C) ships structurally).

### Ranger

- **Favored Enemy (Lv 1)** — S. Advantage on Wisdom (Survival) checks
  to track favored enemies + INT checks to recall info about them.
  Implementation: ranger picks a creature-type at level-up
  (`sheet.favored_enemy: "humanoid:orc"` etc.); the skill-roll engine
  applies advantage when the roll context matches. Deps: (B) skill-
  roll-context intercept.
- **Natural Explorer (Lv 1)** — S. Pick a terrain type; double
  proficiency bonus on INT and WIS checks related to that terrain
  while in it. Implementation: ranger picks
  `sheet.natural_explorer: "forest"|"swamp"|...`; environment is a
  GM-controlled map state. Until (B) and a per-map "terrain" attribute
  exist, descriptive. Deps: (B) + new map terrain field.
- **Primeval Awareness (Lv 3)** — S. Action; spend a spell slot to
  sense favored enemies within 1 mile (6 miles in favored terrain).
  Implementation: action button + slot consumer + roll-log entry. The
  GM tells the player what they sense. Trivial.
- **Land's Stride (Lv 8)** — Pure passive (move through difficult
  terrain without penalty + advantage on saves vs plant-based
  hindrance). Deps: (D).
- **Hide in Plain Sight (Lv 10)** — S. Spend 1 minute camouflaging
  yourself; +10 to Stealth while motionless. Implementation: action
  + buff slot entry granting the bonus while the buff is active.
  Deps: (C).
- **Vanish (Lv 14)** — S. Hide as a bonus action; can't be tracked
  except by magical means. Implementation: bonus-action Hide button
  + descriptive flag. Already tagged via Cunning Action-style entry
  in `_FEATURE_ECONOMY` if added.
- **Feral Senses (Lv 18)** — Pure passive (no disadvantage attacking
  invisible creatures, blindsense 30 ft). Deps: (D).
- **Foe Slayer (Lv 20)** — S. Once per turn, add Wis mod to attack or
  damage roll vs a favored enemy. Implementation: per-attack toggle
  + favored-enemy check. Deps: (B) post-attack hook.

### Rogue

- **Sneak Attack (Lv 1)** — M, **priority #8**. When you hit a creature
  with a finesse / ranged weapon AND either (a) have advantage or
  (b) have an ally within 5 ft of the target, add extra damage scaling
  with level (1d6 at Lv 1, +1d6 per 2 levels, max 10d6 at Lv 19).
  Implementation: per-attack toggle on the attack panel — the player
  marks the attack as "sneak attack" before firing, and the resulting
  damage roll includes the extra dice. Pair-ship with Divine Smite
  (same surface). Deps: (B) post-attack hook; advantage detection
  (already in the roll engine via `roll_state`).
- **Thieves' Cant (Lv 1)** — Pure descriptive language. No mechanic.
- **Uncanny Dodge (Lv 5)** — M. Reaction; halve damage from one
  attack you can see. Implementation: damage-take intercept (same as
  Monk Deflect Missiles). Deps: (B) + damage-take hook.
- **Evasion (Rogue, Lv 7)** — M. Same as Monk Evasion above (shared
  pattern).
- **Reliable Talent (Lv 11)** — S. Treat any d20 < 10 as 10 for
  proficient skill checks. Implementation: clamp the d20 to ≥10 in
  the skill-roll engine when proficient + Rogue ≥ 11. Deps: (B)
  skill-roll intercept.
- **Blindsense (Lv 14)** — Pure descriptive (sense hidden / invisible
  within 10 ft). Deps: (D).
- **Slippery Mind (Lv 15)** — S. Proficiency in Wisdom saves.
  Implementation: set `saving_throws.WIS = {proficient: true}` at level-
  up. Trivial.
- **Elusive (Lv 18)** — S. No attack roll has advantage against you
  unless you're incapacitated. Implementation: passive disable of
  advantage on incoming attacks. Deps: (D) + (B) for the attack
  intercept.
- **Stroke of Luck (Lv 20, augments 🟢 counter)** — M. Once per short
  rest: turn a missed attack into a hit OR a failed ability check
  into a 20. Implementation: roll-time intercept post-result, offer
  the conversion. Deps: (B).

### Sorcerer

- **Font of Magic — Sorcery Points (Lv 2, augments 🟢 counter)** — M.
  Use button → option picker with: "Convert N sorcery points to a
  Lv X spell slot" + "Convert a Lv X spell slot to (X×2) sorcery
  points". Implementation: option picker (v2.9.0 primitive) opens →
  pick conversion direction + level → POST a new
  `/api/.../font-of-magic` endpoint that updates both the SP counter
  AND the spell-slots row. Conversion rates per RAW: 1 SP ↔ Lv 1 slot,
  2 SP ↔ Lv 2 slot, 3 SP ↔ Lv 3 slot, 5 SP ↔ Lv 4 slot, 6 SP ↔ Lv 5
  slot, 7 SP ↔ Lv 6 slot, 8 SP ↔ Lv 7 slot, 9 SP ↔ Lv 8 slot. No
  deps — both sides are sheet-state mutations.
- **Metamagic (Lv 3)** — L. Per-cast modifiers (Quickened Spell:
  action → bonus, Twinned Spell: target 2 creatures, Subtle Spell:
  no V/S components, Distant Spell: 2× range, Heightened Spell:
  disadvantage on save, Empowered Spell: reroll damage dice). Each
  costs SP. Implementation: pre-cast intercept on the .sp-cast button
  — picker overlay listing the player's known metamagic options with
  SP costs. Pick metamagic → fire the cast with the modifier applied
  (e.g. Quickened changes the broadcast's casting_time to "1 bonus
  action" so the action-economy chip flips bonus instead of action).
  Deps: pre-cast intercept (new), action-economy already shipped.
  Medium-large lift since metamagic is complex per-option.
- **Sorcerous Restoration (Lv 20)** — S. Regain 4 SP on short rest.
  Implementation: special-case in the short-rest endpoint that adds
  the bonus refill alongside the regular per-rest-key refill. Trivial.

### Warlock

- **Pact Magic (Lv 1)** — augments 🟡 today. Uses spell-slot UI but
  slots refresh on **short** rest, not long. Implementation: the
  short-rest endpoint should refill warlock spell slots to max. Check
  whether the existing short-rest path refills `spell_slots[warlock]`
  — if not, special-case it. Small.
- **Eldritch Invocations (Lv 2)** — M. Picker UI for invocations
  (descriptive boosts: Agonizing Blast, Devil's Sight, etc.). Some are
  stat boosts, some are new spells at will, some are once-per-rest.
  Implementation: a per-warlock `invocations: []` array on the sheet
  + a picker that lists eligible invocations by level/pact-boon
  prerequisites. Most invocations are descriptive (set flags the
  sheet reads); a few (Agonizing Blast → +CHA mod to Eldritch Blast
  damage) need (B) attack-damage intercepts.
- **Pact Boon (Lv 3)** — M. Pick: Pact of the Chain (familiar) /
  Pact of the Blade (summonable pact weapon) / Pact of the Tome
  (3 free cantrips). Each is its own sub-system. Tome is easiest
  (just an extra-spells flag). Blade needs an attack-panel addition.
  Chain is a familiar with its own stat block — major new surface.
  Deps: vary; ship Tome first.
- **Mystic Arcanum (Lv 11 / 13 / 15 / 17)** — S. Pick a high-level
  spell (Lv 6/7/8/9) that can be cast once per long rest WITHOUT a
  spell slot. Implementation: separate `mystic_arcanum: [{name,
  level, used: bool}]` array on the sheet. Each entry renders as a
  spell-cast button + a 1-per-long-rest flag (resets on long rest).
  No spell slot consumed. Deps: long-rest endpoint extension for the
  reset.
- **Eldritch Master (Lv 20)** — S. 1-minute prayer to regain all Pact
  Magic slots. Implementation: action button + slot reset; the
  existing short-rest path already restores all slots, so this is
  effectively a "force short-rest for spell slots" action. Trivial.

### Wizard

- **Arcane Recovery (Lv 1, augments 🟢 counter)** — M. Once per long
  rest after a short rest, recover spell slots whose combined level
  ≤ half wizard level (round up). Implementation: Use button → custom
  picker (lists each spell slot level + a count input, total ≤ budget).
  Pick → restore the chosen slots. Trivial UX-wise; the picker is
  custom enough that the existing `showResourceOptionPicker` doesn't
  fit cleanly. Small-medium. No deps.
- **Spell Mastery (Lv 18)** — S. Pick a Lv 1 and a Lv 2 spell that
  can be cast at their lowest level without expending a slot.
  Implementation: flag specific spells with `_master: true` on the
  sheet → cast button skips the slot decrement when active. Small.
- **Signature Spells (Lv 20)** — S. Pick 2 Lv 3 spells that can each
  be cast once per short rest without a slot. Implementation: same
  shape as Mystic Arcanum (per-spell rest counter). Small.

### Cross-class shared

- **Extra Attack (Barbarian/Fighter/Paladin/Ranger Lv 5; Fighter Lv 11
  +20)** — M. (One section since the implementation is shared.) When
  you take the Attack action, you can make additional attack rolls
  (1 extra at Lv 5; Fighter gets +1 at Lv 11 and Lv 20). Implementation:
  the attack panel could render a single "Attack action (×2)" button
  that fires both rolls back-to-back with a small delay between dice
  toasts, OR keep the existing per-attack buttons and add a tooltip /
  badge "You can attack ×2 as part of this Attack action". Action-
  economy stays correct (the Attack action burns 1 Act slot regardless
  of how many strikes are inside it; subsequent same-turn Strikes
  shouldn't re-burn Act). The current behavior re-burns Act on each
  Strike — this needs to change for Extra Attack to feel right. Deps:
  action-economy already shipped, but `use_attack` endpoint needs to
  skip the slot mark when the slot is already used AND the same
  combatant's first attack this turn was logged within the last 6
  seconds (rough heuristic). Or: introduce an explicit "attack action
  in progress" marker that the Extra Attack feature toggles. Medium
  design — needs its own follow-up plan when work begins.

---

## Subclass-feature plans (⚪ → 🟠)

The subclass table above lists each subclass's overall status (✅ for
shipped features JSON, 🟡 / 🟢 for partial mechanics). Below: brief
implementation hooks for the descriptive 🟡 / 🟢 entries that are
*specific to the subclass*. Spell-grant-only subclasses (Forge / Grave
/ Order etc.) need no further work beyond the curated spell tables
already shipped.

- **Path of the Berserker (Frenzy / Mindless Rage / Intimidating
  Presence / Retaliation)** — M total. Frenzy: extend Rage to grant
  a bonus-action melee attack at the cost of exhaustion at Rage end.
  Mindless Rage: passive immunity to charmed/frightened while raging
  (D). Intimidating Presence: action target picker + Wis-save broadcast
  (uses CD picker primitive). Retaliation: reaction-on-damage (B +
  damage-take hook).
- **College of Lore (Cutting Words / Additional Magical Secrets / Peerless
  Skill)** — M. Cutting Words: reaction; spend a Bardic Inspiration die
  to subtract from an enemy's attack/check/save. Needs roll-time
  intercept (B). Additional Magical Secrets: extend the Magical
  Secrets picker count. Peerless Skill: spend BI die on own ability
  check (B intercept).
- **Channel Divinity options for non-Life domains** — see Cleric CD
  section above. Each non-Life domain needs its option entries in
  `_FEATURE_ECONOMY` (~10 LOC per domain) + a demo cleric per domain
  to exercise it (optional).
- **Circle of the Moon (Combat Wild Shape / Circle Forms)** — M.
  Combat Wild Shape: lets you Wild Shape as a bonus action and spend
  HD-equivalent ki to heal in beast form. Circle Forms: better CR cap
  + access to specific elemental forms. Implementation: extend the
  Wild Shape transform UI (priority #4) with the moon-specific
  bonus-action variant + CR-cap-aware beast picker. Deps: priority
  #4 Wild Shape transform.
- **Champion (Improved Critical / Remarkable Athlete / Additional
  Fighting Style / Superior Critical / Survivor)** — M. Improved
  Critical: crit on 19-20. Remarkable Athlete: +floor(PB/2) on certain
  ability checks (extension of Jack of All Trades pattern). Survivor:
  regen at start of turn if ≤ half HP. Implementation: each is a small
  roll-time tweak in the appropriate engine. Deps: (B).
- **Battle Master (Combat Maneuvers / Know Your Enemy / Improved Combat
  Superiority / Relentless)** — L. Combat Maneuvers are a list of
  ~16 options each spending a Superiority Die for a tactical effect.
  Picker-shaped (use v2.9.0 primitive). Each maneuver needs its own
  side effect (Riposte: reaction-attack after enemy misses; Trip
  Attack: prone on hit; Disarm: save vs disarm; etc.). Largest single
  subclass effort. Deps: (B), (C).
- **Way of the Open Hand (Open Hand Technique / Wholeness of Body /
  Tranquility / Quivering Palm)** — Open Hand Technique ✅ **shipped
  v2.49.57** with three picker modes (prone / disengage / lose
  reaction) driven by a per-Flurry-of-Blows action button at the
  `/api/campaign/{cid}/use_open_hand_technique` endpoint. Wholeness
  of Body / Tranquility / Quivering Palm still pending — Wholeness
  of Body needs the Ki spend-picker (filed); Tranquility is a
  long-rest aura buff; Quivering Palm is a high-level action with
  delayed damage trigger.
- **Oath of Devotion (Sacred Weapon / Turn the Unholy)** — S. Both are
  Channel Divinity options; add them to `_FEATURE_ECONOMY` under a
  `channel-divinity-paladin` key. Sacred Weapon adds CHA mod to attack
  rolls + magical-damage tag for 1 min. Turn the Unholy: variant Turn
  Undead targeting fiends/undead.
- **Hunter (Hunter's Prey / Defensive Tactics / Multiattack /
  Superior Hunter's Defense)** — M. Hunter's Prey: pick one of 3
  damage uplift variants. Defensive Tactics: pick one of 3 passive
  defense variants. Multiattack: Extra Attack ×2 (extends Extra
  Attack). Superior Hunter's Defense: reaction-based defense. Deps:
  (B) + (D).
- **Thief (Fast Hands / Use Magic Device / Supreme Sneak / Thief's
  Reflexes)** — M. Fast Hands: bonus-action Cunning Action variants
  (use object, Sleight of Hand, use thieves' tools). Use Magic Device:
  ignore class-based item-use restrictions. Supreme Sneak: advantage
  on Stealth at half speed. Thief's Reflexes: second turn at -10 init.
  Mostly descriptive + small toggles; Fast Hands extends the existing
  Cunning Action picker.
- **Draconic Bloodline (Dragon Ancestor / Draconic Resilience / Dragon
  Wings)** — M. Dragon Ancestor: pick draconic ancestor (descriptive +
  damage-type for elemental affinity). Draconic Resilience: +1 HP per
  sorcerer level + unarmored AC 13+DEX. Dragon Wings: action; sprout
  wings for fly speed. Wings: action-economy + buff slot for the
  duration.
- **Wild Magic (Tides of Chaos / Wild Magic Surge / Bend Luck /
  Controlled Chaos / Spell Bombardment)** — M. Tides of Chaos:
  advantage on attack/check/save 1/long rest (counter exists). Wild
  Magic Surge: d100 chaos roll on cantrip cast. Bend Luck: reaction
  +/-1d4 on a roll for a sorcery point. Controlled Chaos: re-roll the
  surge. Bombardment: extra damage die on max rolls.
- **Aberrant Mind / Divine Soul** — Spell grants only.
- **The Fiend (Dark One's Blessing / Dark One's Own Luck / Fiendish
  Resilience / Hurl Through Hell)** — M. Dark One's Blessing: temp HP
  on kill (passive on damage application). Dark One's Own Luck:
  reroll one ability check or save per short rest. Fiendish
  Resilience: pick a damage type for resistance (1/long rest).
  Hurl Through Hell: action on hit; target takes 10d10 psychic if
  fails Cha save.
- **School of Evocation (Evocation Savant / Sculpt Spells / Potent
  Cantrip / Empowered Evocation / Overchannel)** — M. Sculpt Spells:
  passive ally-exclusion from your own evocation AoEs (descriptive
  until target-picker exists for damage spells). Potent Cantrip:
  half-damage on cantrip saves. Empowered Evocation: +INT mod to one
  damage roll per evocation. Overchannel: max damage on a Lv 5+
  evocation, take damage on subsequent uses.
- **Divination (Portent / Expert Divination / The Third Eye / Greater
  Portent)** — M. Portent (counter exists, 🟢): pre-rolled d20s at the
  start of long rest; player replaces an attack/save/check d20 with
  one of these dice. Implementation: action button per portent die
  → roll-time intercept that swaps the active d20 result. Deps:
  (B). Expert Divination: refund slots when casting divination spells.
  Greater Portent: 3 dice instead of 2.

---

## Feat plans (⚪ → 🟠)

Only one SRD feat ships (Grappler); homebrew feats live alongside.
Mechanical feat effects are uniformly ⚪ today. Each filed feat needs:

- **Grappler (SRD)** — S. Advantage on attack rolls vs creatures you're
  grappling + you can use an action to try to pin them. Both pieces
  need (B) attack-time intercepts. Today the feat description renders
  on the sheet via the existing feats panel; mechanical wiring is
  deferred until (B) lands.
- **Lucky Strike (demo homebrew)** — S. Reroll a missed attack 1/long
  rest. Same shape as Halfling Lucky / Fighter Indomitable. Needs
  (B) roll-time intercept.

Future feat additions: drop a JSON in the matching tier and the sheet
will render the description automatically. Mechanical wiring follows
the per-feat plan once (B) ships.

---

## Race trait plans (⚪ → 🟠)

Most race traits are passive — they apply automatically when a specific
roll happens. (D) passive trait engine is the natural fit; until (D)
lands, players manually flip advantage/disadvantage at roll time.

- **Dragonborn (Breath Weapon)** — M. Action; pick area (line/cone per
  ancestry); save-DC challenge for half damage. Same shape as a
  Channel Divinity save-prompt option. Use the v2.9.0 option picker
  for area selection (line vs cone) + the existing save-prompt
  infrastructure. Deps: save-prompt-on-feature plan (not yet shipped
  beyond the feature_used roll-log entry).
- **Dragonborn (Damage Resistance)** — Pure passive. Deps: (D).
- **Half-Orc (Relentless Endurance)** — S. Once per long rest, drop to
  1 HP instead of 0. Same shape as Barbarian Relentless Rage. Hook
  into `_apply_hp_change`'s dying transition. Deps: per-long-rest
  counter ✅ (already supported via resource recipe), `_apply_hp_change`
  hook ✅ (exists). Could ship today as a 1/1 resource + hook.
- **Half-Orc (Savage Attacks)** — S. On a melee crit, roll one extra
  damage die. Damage-roll uplift on crit. Deps: (B) crit intercept.
- **Half-Elf (Fey Ancestry)** — Pure passive (advantage on charm saves,
  can't be put to sleep magically). Deps: (D).
- **High Elf (Cantrip + Elf Weapon Training)** — S. Cantrip pick adds
  one wizard cantrip to the sheet's spell list. Weapon Training:
  proficiency in longsword / shortsword / shortbow / longbow. Both
  wire through existing systems (spell picker + proficiency flags).
  Trivial; no deps.
- **High Elf (Keen Senses / Trance / Fey Ancestry)** — Mix of passive
  (Keen Senses: skill proficiency in Perception ✅; Fey Ancestry: see
  Half-Elf above; Trance: 4-hour sleep equivalent — descriptive).
- **Hill Dwarf (Dwarven Resilience / Dwarven Combat Training /
  Stonecunning / Speed Not Reduced by Heavy Armor / Dwarven Toughness)**
  — Dwarven Toughness ✅ already in Tavik's HP via sheet `hp.max=43`.
  Dwarven Resilience: advantage vs poison + resistance to poison
  damage — pure (D). Dwarven Combat Training: proficiencies (battleaxe
  / handaxe / light hammer / warhammer) — trivial sheet flag. Speed
  reduction: edit `_speedWalkFromSheet` to skip the heavy-armor
  speed penalty for dwarves. Stonecunning: +2 × PB on history checks
  about stonework — (B) skill-context intercept.
- **Lightfoot Halfling (Lucky / Brave / Halfling Nimbleness /
  Naturally Stealthy)** — Lucky: reroll natural 1s on attack/check/
  save. Same shape as Stroke of Luck / Lucky feat — (B) intercept.
  Brave: advantage vs fear — (D). Nimbleness: move through larger
  creatures' spaces — descriptive. Naturally Stealthy: hide behind
  Medium+ creatures — descriptive.
- **Rock Gnome (Gnome Cunning / Artificer's Lore / Tinker)** — Gnome
  Cunning: advantage on INT/WIS/CHA saves vs magic — (D). Artificer's
  Lore: +2 × PB on History checks about magic items — (B) skill-
  context intercept. Tinker: descriptive 1-hour clockwork creation.
- **Tiefling (Hellish Resistance / Infernal Legacy)** — Hellish
  Resistance: fire resistance — (D). Infernal Legacy: Thaumaturgy
  cantrip + Hellish Rebuke 1/long rest at Lv 3 + Darkness 1/long
  rest at Lv 5. Each spell tracks against a per-day resource counter.
  Trivial wiring; per-day counters already exist in the resource
  recipe system.

---

## What this section does NOT plan

Each plan paragraph is a starting point, not a finished design.
Several features (Battle Master maneuvers, Metamagic, Wild Magic
Surge) will need their own dedicated plan files when work begins —
they're complex enough that a single paragraph isn't enough scaffold.
Filed for follow-up; do **not** start coding them without writing a
fuller plan in `docs/plans/<feature>.md` first.

Anything tagged "pure descriptive" or "no mechanic" is intentionally
deferred forever (or until a system big enough to absorb it lands).
The character sheet shows the description text via the SRD JSON tier;
that's the final state for these features unless someone proposes a
mechanic.
