# SRD Conditions — Implementation Guide

How SimpleVTT implements the 15 SRD 5.1 conditions (CC BY 4.0). For each condition, this guide lists every RAW clause, what fires automatically vs. what the GM applies vs. what the engine deliberately leaves narrative, and the underlying mechanism (buff key, helper, endpoint) so you know exactly what to expect at the table.

Verified against the codebase at **v2.401.0** (2026-06-17 audit). Status legend:

| Symbol | Meaning |
|---|---|
| ✅ | Engine enforces the clause automatically when the trigger fires (attack roll, save, action attempt, install side-effect). |
| 🟢 | Engine recognizes the condition for one purpose (warning pill, immunity read, dispel target) but the clause itself is narrative. |
| ⚪ | Genuinely unwired — flagged where it appears. (Empty in v2.401.0.) |
| OOS | Out-of-scope by design. The substrate the clause needs (social-check engine, reach-aware movement, hearing-narrative) doesn't exist server-side and isn't planned for v2.x. See [the v2.384.0 condition-enforcement audit](/wiki/doc/condition-enforcement-audit) for the per-clause rationale. |
| N/A | RAW clause is pure flavor (e.g. "The creature can't speak") with no engine analog. |

**Headline:** Conditions are at **~92% mechanical coverage** as of v2.401.0. All 15 SRD conditions have data + a buff template + at least one read site. Ten conditions are fully wired d20-side; the three previously-partial conditions (Charmed, Grappled, Incapacitated) closed their per-clause sweep across v2.385.0–v2.391.0; Exhaustion runs on a separate 6-level ladder; the remaining ~8% is three clauses that are permanently GM-narrated by design (Charmed clause 2 social-check, Grappled clause 3 out-of-reach, Deafened hearing). See [Out-of-scope by design](#out-of-scope-by-design) for the full rationale.

---

## TL;DR — what fires when

If you're a GM running a session and just want to know what to expect at the table:

| The engine fires automatically | The engine reads + warns | GM-narrated by design |
|---|---|---|
| **Attack roll adv/dis** — Poisoned, Frightened, Restrained, Blinded, Prone, Paralyzed, Stunned, Unconscious, Invisible all fire their own attack adv/dis + attacks-against adv/dis through `_attacker_has_condition_disadvantage` / `_target_has_condition_advantage` | **Mini-sheet warning pill** — `⚠ Conditions` chip on the abilities header lists every active condition with its mechanical impact (v2.401.0 broadened to charmed/grappled/incapacitated alongside the d20-adv/dis set) | **Charmed clause 2** — advantage on social checks against the charmed creature (no social-check engine) |
| **Save auto-fail** — Paralyzed, Stunned, Unconscious, Petrified auto-fail STR + DEX saves via `_saver_auto_fails_strdex_save` | **Condition immunity** — Paladin Aura of Devotion (Charmed/Frightened), Aasimar/Tiefling/Fiend ancestry immunities all read through `_buff_blocks_install` at install time | **Grappled clause 3** — condition ends when an effect removes the grappled creature from the grappler's reach (no reach-aware movement substrate) |
| **Melee auto-crit** — Paralyzed and Unconscious targets eat melee auto-crits inside 5 ft via the v2.99.107 critical-hit pipeline | **Concentration drop** — incapacitating buffs (stunned/paralyzed/unconscious/petrified/hideous-laughter/incapacitated) drop the carrier's concentration through the v1 concentration handler | **Deafened** — auto-fail on ability checks requiring hearing (no hearing-check substrate; RAW is mostly narrative anyway) |
| **Action gate** — incapacitated combatants get a 409 `incapacitated` at `/attack` (v2.386.0), `/cast_spell` (v2.387.0), and `/use_feature` (v2.388.0) | **Sneak Attack ally-skip** — Rogue ally-adjacency advantage trigger ignores incapacitated allies (v2.385.0) | |
| **Grappled auto-end** — when a creature carrying a grappled buff has its grappler become incapacitated, the engine auto-ends the grappled buff (v2.389.0) | | |
| **Charmed action block** — a charmed creature attempting to attack or harmful-cast against its charmer gets a 409 `charmed_cannot_target_charmer` (v2.390.0 `/attack` + v2.391.0 `/cast_spell`) | | |
| **Exhaustion ladder** — `/set_exhaustion` levels 1–6 fire cumulative penalties (ability-check disadvantage Lv 1+, speed halved Lv 2+, attack & save disadvantage Lv 3+, max-HP halved Lv 4+, speed=0 Lv 5, death Lv 6) | | |
| **Grappled speed=0** — `effective_speed_walk` clamps to 0 via the buff's `speed_reduction_ft` effect (v2.99.112) | | |

---

## Blinded

**RAW:** Auto-fail any ability check requiring sight. Attack rolls have disadvantage; attack rolls against the blinded creature have advantage.

| Clause | Status | How it works |
|---|---|---|
| Disadvantage on own attacks | ✅ | `_attacker_has_condition_disadvantage` reads the `blinded` buff key at every `/attack` + spell-attack site and downgrades the roll to 2d20kl1. |
| Advantage on attacks against | ✅ | `_target_has_condition_advantage` upgrades incoming attacks to 2d20kh1. |
| Auto-fail sight-based ability checks | OOS | RAW is mostly narrative; SimpleVTT has no engine for "this check requires sight" — GM applies as needed. |

**Test coverage:** `test_attack_condition_adv_dis.py` covers both adv/dis halves; `test_npc_attack_condition_adv_dis.py` covers the NPC-attacker side.

---

## Charmed

**RAW:** Can't attack the charmer or target the charmer with harmful abilities or magical effects. The charmer has advantage on social ability checks to interact with the creature.

| Clause | Status | How it works |
|---|---|---|
| Cannot attack the charmer | ✅ | `_attacker_is_charmed_by_target` (v2.390.0) reads the charmed buff's `source_char_id` (populated by `_install_buff` at spell-cast time at `tabletop_routes.py:19048` and item-action time at `:2187`). `/attack` returns 409 `charmed_cannot_target_charmer` when the attacker carries a `charmed` buff whose source matches the target. |
| Cannot harmful-cast at the charmer | ✅ | Mirrored onto `/cast_spell` at `tabletop_routes.py:19706` in v2.391.0. Note: `/use_feature` is **not applicable** — it's structurally self-targeted (Action Surge, Channel Divinity buffs, Lay on Hands pool), so there's no `target_combatant_id` to gate against. |
| Social-check advantage for the charmer | OOS | No social-check engine exists. The dice for Persuasion / Deception / Insight are rolled but the engine doesn't compute social outcomes. Filed permanently — see [audit doc](/wiki/doc/condition-enforcement-audit#out-of-scope). |

**Install paths:** spell-cast (Charm Person, Suggestion, Hypnotic Pattern), item-action (Rod of Rulership, Potion of Animal Friendship), lair-action (monster-source). Lair-action installs deliberately can't carry `source_char_id` — the charmer is a monster (no char_id), so the v2.390.0 gate is silent for monster-source charms (GM-narrated by design).

**Immunity reads:** Aura of Devotion (Paladin Lv 7+ Devotion) at `tabletop_routes.py:1054/1067/1551`, Aasimar / Fey ancestry race-immunity at `_buff_blocks_install`. Pact of the Fiend's `frightened`/`charmed` immunity covered by `test_pfeag_condition_immunity.py`.

**Test coverage:** `test_attack_condition_adv_dis.py` (charmed-attack 409 path), `test_condition_immunity.py` (Devotion aura blocks install), `test_pfeag_condition_immunity.py` (Pact of Fiend).

---

## Deafened

**RAW:** Can't hear. Auto-fail any ability check requiring hearing.

| Clause | Status | How it works |
|---|---|---|
| All clauses | OOS | RAW is mostly "can't hear" narrative; the only mechanical clause is the auto-fail on hearing-based checks, which has no engine site to gate against. Buff is installable for GM tracking but no automation fires. |

**Why no automation:** SimpleVTT doesn't tag ability checks with sense requirements — a Perception check could be sight, hearing, smell, or several at once. Gating "this Perception is a hearing check" is GM-narrated by design. Deafened deliberately not in `CONDITION_IMPACTS` (no warning-pill entry).

---

## Exhaustion

**RAW:** Six cumulative levels. Lv 1: disadvantage on ability checks. Lv 2: speed halved. Lv 3: disadvantage on attack rolls + saving throws. Lv 4: hit-point maximum halved. Lv 5: speed reduced to 0. Lv 6: death.

| Level | Status | How it works |
|---|---|---|
| Lv 1: disadvantage on ability checks | ✅ | `_roll_condition_disadvantage` reads `sheet.exhaustion_level >= 1` and downgrades ability-check d20s to 2d20kl1. |
| Lv 2: speed halved | ✅ | `effective_speed_walk` halves the walk speed once `exhaustion_level >= 2`. |
| Lv 3: disadvantage on attacks + saves | ✅ | Attack + save sites read the same exhaustion_level field via `_attacker_has_condition_disadvantage` / `_saver_has_condition_disadvantage`. |
| Lv 4: hit-point maximum halved | ✅ | `_effective_hp_max` halves the cap; HP clamp at the next damage/heal fires through. |
| Lv 5: speed reduced to 0 | ✅ | `effective_speed_walk` clamps to 0 at exhaustion_level >= 5. |
| Lv 6: death | ✅ | `/set_exhaustion?level=6` immediately drops the combatant to 0 HP + dead via the v2.159.22 death path. |

**Tracked separately** — Exhaustion is a sheet integer field (`exhaustion_level`), not a buff entry, so it doesn't surface in the mini-sheet `CONDITION_IMPACTS` warning pill. The dedicated exhaustion UI lives on the character sheet's death-saves area.

**Plan doc:** [exhaustion-levels](/wiki/doc/plan-exhaustion-levels) — shipped v2.159.17–.22.

**Test coverage:** `test_npc_roll_condition_adv_dis.py` covers the Lv 3 attack-disadvantage path; the speed + max-HP clamps surface through the generic combat tests.

---

## Frightened

**RAW:** Disadvantage on ability checks and attack rolls while the source of fear is within line of sight. Can't willingly move closer to the source.

| Clause | Status | How it works |
|---|---|---|
| Disadvantage on attacks | ✅ | `_attacker_has_condition_disadvantage` reads the `frightened` buff key. |
| Disadvantage on ability checks | ✅ | `_roll_condition_disadvantage` reads the same key for d20 ability checks. |
| "Within line of sight" qualifier | OOS | The engine doesn't track LoS as a per-tick predicate. RAW correctness is GM-narrated: if the source is around a corner, the GM manually `/end_buff`s. |
| "Can't willingly move closer to the source" | OOS | No movement-vector gating today. Maps 2.0 territory. |

**Immunity reads:** Devotion-Paladin Aura of Devotion (Charmed/Frightened); Bear Totem Barbarian (Frightened); Pact of the Fiend (Frightened). All flow through `_buff_blocks_install`.

**Test coverage:** Multiple harness files including `test_attack_condition_adv_dis.py`, `test_roll_condition_adv_dis.py`, `test_npc_roll_condition_adv_dis.py`, `test_pfeag_condition_immunity.py`.

---

## Grappled

**RAW:** Speed = 0; can't benefit from any bonus to speed. Condition ends if the grappler is incapacitated. Also ends if an effect removes the grappled creature from the reach of the grappler.

| Clause | Status | How it works |
|---|---|---|
| Speed = 0 | ✅ | `_make_grappled_buff` (v2.99.112) installs `effects.speed_reduction_ft = base_speed`. `effective_speed_walk` clamps to 0. Any positive bonus (e.g. Longstrider +10) is functionally irrelevant — the clamp wins. |
| Can't benefit from speed bonuses | ✅ | Enforced by side-effect of the speed=0 clamp above. RAW-correct without an explicit "suppress bonus" check; filed as "enforced by side-effect" rather than literal clause. |
| Ends if grappler incapacitated | ✅ | v2.389.0 "The Broken Hold". Install-side-effect: whenever any incapacitating buff (`stunned`/`paralyzed`/`unconscious`/`petrified`/`hideous-laughter`/`incapacitated`) is installed on a creature, the engine sweeps every combatant for `grappled` buffs whose `source_char_id` matches the newly-incapacitated combatant and auto-ends them. Uses the shared `_combatant_is_incapacitated` predicate that landed in v2.385.0. |
| Ends if out-of-reach movement | OOS | No reach-aware movement substrate exists. Blocked on Maps 2.0. |

**Test coverage:** Grappled adv/dis covered through `test_attack_condition_adv_dis.py` (note: Grappled doesn't itself fire attack adv/dis RAW — but the buff is read for speed-clamp tests).

---

## Incapacitated

**RAW:** Can't take actions or reactions.

| Clause | Status | How it works |
|---|---|---|
| Can't take actions | ✅ | v2.386.0–v2.388.0 — `/attack`, `/cast_spell`, `/use_feature` all reject 409 `incapacitated` when the actor carries any buff with incapacitating semantics (`stunned`/`paralyzed`/`unconscious`/`petrified`/`hideous-laughter`/`incapacitated`). Shared `_combatant_is_incapacitated` predicate. |
| Can't take reactions | ✅ | The `/attack` opportunity-attack reaction branch shares the same endpoint as the action gate, so the v2.386.0 ship closes both the action and the reaction clause at the same site. Previously a filed comment at `tabletop_routes.py:3259–3260` ("v1 doesn't check the incapacitated buff; filed") — now resolved. |
| Sneak Attack ally-adjacency skip | ✅ | v2.385.0 "The Conscious Ally" — Sneak Attack's RAW "another enemy of the target is within 5 ft of it" check skips incapacitated allies. First consumer of `_combatant_is_incapacitated`. |
| Concentration drops | ✅ | v1 concentration handler reads the incapacitated keys at `tabletop_routes.py:965, 989, 2343` and drops concentration whenever an incapacitating buff installs. |
| Cleansing Touch can lift incapacitated-source conditions | ✅ | Paladin Lv 14 Cleansing Touch at `tabletop_routes.py:274–279` ends charmed/frightened on touch — works against incapacitated PCs as a heal. |
| `/next_turn` deliberately has no gate | N/A | Incapacitated still consumes the turn slot RAW; their turn just has no actions. |

**Substrate-first design paid off:** The shared `_combatant_is_incapacitated` helper landed in v2.385.0 and was reused unchanged across 5 sites (Sneak Attack ally-skip + 3 PC action gates + Grappled-end sweep). Single predicate, five callers, zero modifications.

**Test coverage:** `test_attack_condition_adv_dis.py`, `test_npc_attack_condition_adv_dis.py`, the Sneak Attack ally-adjacency tests, and the v2.401.0 mini-sheet warning-pill assertion at `test_mini_sheet_cond_warn.py::test_incapacitated_pc_mini_sheet_shows_action_gate_warning`.

---

## Invisible

**RAW:** Impossible to see without magic or a special sense. Counts as heavily obscured. Attack rolls against have disadvantage; the invisible creature's attack rolls have advantage.

| Clause | Status | How it works |
|---|---|---|
| Advantage on own attacks | ✅ | `_attacker_has_condition_advantage` reads the `invisible` buff key. |
| Disadvantage on attacks against | ✅ | `_target_has_condition_disadvantage` does the inverse read on the target's buff list. |
| "Heavily obscured" qualifier | OOS | The engine doesn't model obscurement as a separate substrate; the visibility consequence is the adv/dis above. Maps 2.0 territory for fog-of-war + obscurement. |

**Install paths:** Invisibility spell (v2.99.x catalog), Greater Invisibility, Cloak of Invisibility, Potion of Invisibility, Ring of Invisibility. All install the `invisible` buff key uniformly.

**Test coverage:** `test_attack_condition_adv_dis.py` covers both halves.

---

## Paralyzed

**RAW:** Incapacitated; can't move or speak. Auto-fail STR + DEX saves. Attack rolls against have advantage. Melee attacks within 5 ft auto-crit.

| Clause | Status | How it works |
|---|---|---|
| Incapacitated (action gate) | ✅ | The `paralyzed` key is in `_INCAPACITATED_KEYS`; the v2.386.0–v2.388.0 gates fire for paralyzed combatants too. |
| Auto-fail STR + DEX saves | ✅ | `_saver_auto_fails_strdex_save` returns True when the saver carries `paralyzed`. The save resolver auto-fails before the d20 is even rolled. |
| Advantage on attacks against | ✅ | `_target_has_condition_advantage` reads paralyzed → 2d20kh1. |
| Melee auto-crit within 5 ft | ✅ | The v2.99.107 critical-hit pipeline reads paralyzed + adjacency to convert any hit to a critical. |
| Can't move or speak | N/A | Speed-0 is enforced via the buff's effect dict; speech is narrative. |

**Install paths:** Hold Person, Hold Monster, Cone of Cold (alt save-or-paralyze for certain monsters), monster-spec attacks (Ghoul claw). Save-resolver branch at `tabletop_routes.py:19048` populates `source_char_id` correctly for spell-cast paralysis.

**Test coverage:** `test_attack_condition_adv_dis.py`, `test_spell_catalog_conditions.py` (Hold Person + Hold Monster save-or-paralyze install gates).

---

## Petrified

**RAW:** Incapacitated; transformed into solid mineral. Weight × 10. Auto-fail STR + DEX saves. Resistance to all damage. Immunity to poison + disease.

| Clause | Status | How it works |
|---|---|---|
| Incapacitated | ✅ | `petrified` is in `_INCAPACITATED_KEYS`. |
| Auto-fail STR + DEX saves | ✅ | `_saver_auto_fails_strdex_save` reads petrified. |
| Resistance to all damage | ✅ | `_make_petrified_buff` sets `effects.damage_resistances = ["all"]`. The resistance-halve damage pipeline reads it. |
| Advantage on attacks against | ✅ | `_target_has_condition_advantage` reads petrified. |
| Poison + disease immunity | ✅ | Petrified buff seeds `damage_immunities += ["poison"]` + a poisoned-buff-install block. |
| Weight × 10 | N/A | No carrying-capacity engine; pure narrative. |

**Install paths:** Flesh to Stone, Basilisk gaze, Medusa gaze, Cockatrice peck (save-or-petrify). All flow through the spell/monster catalog.

**Test coverage:** `test_attack_condition_adv_dis.py` covers the adv-on-attacks-against + auto-fail halves; resistance reads tested through the universal resistance pipeline.

---

## Poisoned

**RAW:** Disadvantage on attack rolls and ability checks.

| Clause | Status | How it works |
|---|---|---|
| Disadvantage on attacks | ✅ | `_attacker_has_condition_disadvantage` reads the `poisoned` buff key. |
| Disadvantage on ability checks | ✅ | `_roll_condition_disadvantage` reads poisoned for d20 ability checks. |

**Save advantages:** Dwarven Resilience grants advantage on saves vs. Poisoned + halves poison damage (`_RACE_SAVE_ADVANTAGES["dwarf"]`).

**Test coverage:** `test_attack_condition_adv_dis.py`, `test_roll_condition_adv_dis.py`, `test_npc_attack_condition_adv_dis.py`, `test_mini_sheet_cond_warn.py::test_poisoned_pc_mini_sheet_shows_warning_pill`.

---

## Prone

**RAW:** Crawl-only movement (half speed). Disadvantage on own attacks. Melee attacks against have advantage; ranged attacks against have disadvantage.

| Clause | Status | How it works |
|---|---|---|
| Disadvantage on own attacks | ✅ | `_attacker_has_condition_disadvantage` reads `prone`. |
| Melee attacks against have advantage | ✅ | `_target_has_condition_advantage` reads prone + checks attacker melee-range adjacency. |
| Ranged attacks against have disadvantage | ✅ | The same helper inverts the read for ranged attackers. |
| Crawl movement (half speed) | OOS | No movement-cost substrate today. GM applies. |

**Install paths:** Earth Tremor, knock-prone tactical effect, monster melee shove. Stand-up costs half the combatant's speed RAW; GM-narrated for now.

**Test coverage:** Part of `test_attack_condition_adv_dis.py` (the melee-vs-ranged branch is explicitly covered).

---

## Restrained

**RAW:** Speed = 0; can't benefit from speed bonuses. Disadvantage on own attacks. Attack rolls against have advantage. Disadvantage on DEX saves.

| Clause | Status | How it works |
|---|---|---|
| Speed = 0 | ✅ | `_make_restrained_buff` (v2.99.106) seeds `effects.speed_reduction_ft = base_speed`. Same enforcement-by-side-effect as Grappled. |
| Disadvantage on own attacks | ✅ | `_attacker_has_condition_disadvantage` reads `restrained`. |
| Advantage on attacks against | ✅ | `_target_has_condition_advantage`. |
| Disadvantage on DEX saves | ✅ | `_saver_has_condition_disadvantage` reads `restrained` for DEX-save d20s. |

**Install paths:** Web spell, Entangle spell, Hold Person (combined paralyzed+restrained on certain monsters), monster Restrain attacks (Roper, Black Pudding).

**Test coverage:** `test_attack_condition_adv_dis.py`, `test_npc_save_condition_adv_dis.py` (the DEX-save half).

---

## Stunned

**RAW:** Incapacitated; can't move; can speak only falteringly. Auto-fail STR + DEX saves. Attack rolls against have advantage.

| Clause | Status | How it works |
|---|---|---|
| Incapacitated | ✅ | `stunned` is in `_INCAPACITATED_KEYS`. |
| Auto-fail STR + DEX saves | ✅ | `_saver_auto_fails_strdex_save` reads stunned. |
| Advantage on attacks against | ✅ | `_target_has_condition_advantage` reads stunned. |
| Falter-speak qualifier | N/A | Narrative. |

**Install paths:** Stunning Strike (Monk Lv 5), Hold Monster save-fail variants, monster gaze attacks.

**Test coverage:** Spell-catalog tests for Stunning Strike + Hold Monster save-or-stun branches; `test_attack_condition_adv_dis.py` covers the adv-on-attacks-against half.

---

## Unconscious

**RAW:** Incapacitated + Prone. Auto-fail STR + DEX saves. Attack rolls against have advantage. Melee attacks within 5 ft auto-crit.

| Clause | Status | How it works |
|---|---|---|
| Incapacitated | ✅ | `unconscious` is in `_INCAPACITATED_KEYS`. |
| Prone | ✅ | `_make_unconscious_buff` co-installs the `prone` semantics (same target gates fire). |
| Auto-fail STR + DEX saves | ✅ | `_saver_auto_fails_strdex_save` reads unconscious. |
| Advantage on attacks against | ✅ | `_target_has_condition_advantage`. |
| Melee auto-crit within 5 ft | ✅ | v2.99.107 crit pipeline reads unconscious + adjacency. |
| Drops items, falls prone visually | N/A | Visual / narrative. |

**Install paths:** PHB *Sleep*, Power Word Stun (at sufficient HP), 0-HP collapse, Holy Word (alt unconscious branch). The 0-HP path is the dominant trigger — handled by the death-save state machine.

**Test coverage:** `test_attack_condition_adv_dis.py`, plus the broader death-save / HP state-machine harness suite.

---

## Out-of-scope by design

The [v2.384.0 condition-enforcement audit](/wiki/doc/condition-enforcement-audit#out-of-scope) explicitly carves these out:

- **Charmed clause 2** (advantage on social checks against the charmed creature) — no social-check engine exists. Persuasion / Deception / Insight rolls fire dice but the engine doesn't compute social outcomes. Filed permanently.
- **Grappled clause 3** (condition ends if an effect removes the grappled creature from the grappler's reach) — no reach-aware movement substrate exists. Blocked on the Maps 2.0 arc.
- **Deafened** (auto-fail any ability check requiring hearing) — RAW is mostly narrative and SimpleVTT doesn't tag ability checks with sense requirements. GM-narrated by design; not in `CONDITION_IMPACTS` (no warning-pill entry).

These three clauses are the entire remaining ~8% gap between the post-v2.391.0 Conditions row (~92%) and 100%. They're filed as future-3.x-or-later scope and require substrate work that isn't planned for v2.x.

---

## How the mini-sheet warning pill works

When a PC carries any condition listed in `CONDITION_IMPACTS` (13 of the 15 SRD conditions as of v2.401.0 — Exhaustion is tracked separately and Deafened is OOS), the mini-sheet's abilities-header renders a `⚠ Conditions` chip whose tooltip lists every active condition with its impact:

> Active conditions affecting actions or d20 rolls:
>
> Poisoned: disadvantage on attacks + ability checks
> Charmed: cannot attack charmer or target charmer with harmful spells

Single source of truth lives in [`app/content/condition_impacts.py`](https://github.com/mkolakowski/SimpleVTT/blob/main/app/content/condition_impacts.py) and is exposed two ways:

- Server-rendered via the `CONDITION_IMPACTS` Jinja global (initial page load).
- Client-rendered via `window._COND_IMPACT_MAP` (runtime hydration after WS battle updates).

Both surfaces read the same dict, so a new entry surfaces in both render paths without further wiring.

---

## What to read next

- [Condition-enforcement audit (v2.384.0 reference)](/wiki/doc/condition-enforcement-audit) — the per-clause walk-through of Charmed / Grappled / Incapacitated + the closing record of the v2.385.0–v2.391.0 sweep.
- [Exhaustion levels plan](/wiki/doc/plan-exhaustion-levels) — the dedicated 6-level ladder design doc.
- [Reactions automation guide](/wiki/reactions) — the reaction-side of the action gate (opportunity attacks, Hellish Rebuke, etc.).
- [SRD race rules implementation guide](/wiki/srd-races-implementation) — companion guide covering race traits, including the Dwarven Resilience / Fey Ancestry save-vs-condition advantages that compose with this surface.
- [Test harness coverage](/wiki/doc/test-harness-coverage) — per-test catalog including every `test_*condition*` file.
