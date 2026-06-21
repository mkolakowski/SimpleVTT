# Cast-and-broadcast utility-spell tail — Design Plan

> **Status:** 🟢 **Phase 2 IN PROGRESS — #25 shipped v2.490.0.** Phase 1 CLOSED v2.441.0 (True Strike #1 v2.437.0; Speak with Animals #3 v2.438.0; Spider Climb #5 v2.439.0; Pass without Trace #4 v2.440.0; Find Steed #2 v2.441.0). **Phase 2 has shipped #1–#25:** the Bucket A spells originally listed below as "next" (Shield of Faith v2.442.0, Mage Armor, Feather Fall, Tongues, Comprehend Languages, Longstrider #9 v2.452.0, Jump #10 v2.453.0, … through Mass Healing Word #24 v2.467.0) are all done. Recent: Protection from Poison (#25) ✅ v2.490.0 (poison-damage resistance via `resistance_to`); Enlarge/Reduce (#26) ✅ v2.491.0 (STR-check/save adv/dis via the Potion-of-Growth/Diminution marker substrate); Freedom of Movement (#27) ✅ v2.492.0 (paralyzed/restrained immunity via the condition-immunity substrate the Ring of Free Action uses); Warding Bond (#28) ✅ v2.493.0 (+1 AC + resistance-to-all-damage via the `ac_bonus` + `resistance_to` substrates; +1 saves + damage-share GM-narrated); **Death Ward (#29) ✅ v2.496.0** — first drop-to-0-from-damage becomes drop-to-1, via a new HP-floor hook in `_apply_hp_change` alongside the Half-Orc Relentless Endurance branch (the first tail spell needing genuinely new mechanical code, not a zero-code substrate ride). The instant-death-negation clause stays GM-narrated. **Protection from Energy (#30) ✅ v2.497.0** — resistance to a caller-chosen energy type (acid/cold/fire/lightning/thunder), the concentration sibling of #25, riding the same `resistance_to` substrate. (v2.496.1 fixed a latent #25 gap: resistance buffs must be mirrored to the target sheet or `_resistance_halve` never reads them.) Stoneskin (#31) ✅ v2.498.0 (resistance to nonmagical b/p/s via the `nonmagical-<type>` substrate); **Greater Invisibility (#32) ✅ v2.499.0** — rides the existing `effects.invisible` marker (advantage for the invisible attacker; disadvantage for attackers vs the target); the "persists through attacks" distinction from L2 is already the engine default, so zero-code. **Blur (#33) ✅ v2.500.0** — attackers roll at disadvantage vs the caster, via a new generic `attackers_have_disadvantage` read-site (`_target_blur_imposes_disadvantage`) folded into the /attack + /npc_attack disadvantage logic (the first tail spell since Death Ward to add a new read-site). The marker is generic so Foresight's attacker-disadvantage half can reuse it. **Mind Blank (#34) ✅ v2.501.0** — charmed-condition immunity via the existing `condition_immunity_to` gate; psychic-damage immunity + divination/scry/wish clauses GM-narrated (the damage path models resistance, not full immunity). **Foresight (#35) ✅ v2.502.0** — advantage on all attacks/checks/saves (via the new generic `foresight` marker wired into the three advantage choke-points) + attacker disadvantage (reusing the v2.500.0 Blur read-site); can't-be-surprised GM-narrated. The `foresight` blanket-advantage marker is reusable by any future "advantage on everything" effect. **Barkskin (#36) ✅ v2.503.0** — AC floor of 16 via a new reusable `effects.ac_floor` read in `_read_target_ac` (`max(total, 16)`). **Guidance (#37) ✅ v2.504.0** — +1d4 to the next ability check (consumed after one check) via a new check-bonus-die read at `/roll`. **Resistance (#38) ✅ v2.505.0** — +1d4 to the next save (consumed after one save) via a save-bonus-die append on the `/roll` save path, mirroring Guidance. (Both cantrips: spell-prompted saves via `roll_request`/`/respond` are a filed follow-up; the `/roll` manual path is wired.) **Heroes' Feast (#39) ✅ v2.506.0** — poison/frightened immunity + WIS-save advantage + 2d10 max-HP boost, all riding existing substrates (`condition_immunity_to`, `_buff_grants_save_advantage`, `aid_hp_bonus`); cure-disease + multi-creature feast GM-narrated. **Beacon of Hope (#40) ✅ v2.507.0** — WIS-save advantage (`save_advantage`) + death-save advantage (new `_pc_has_death_save_advantage` read at `/death-save`, 2d20-keep-highest); max-healing GM-narrated. **Holy Aura (#41) ✅ v2.508.0** — the **first tail spell to fan the buff out across an arbitrary number of chosen creatures** (the 30-ft aura): all-saves advantage (`save_advantage: True`) + attacker-disadvantage (the v2.500.0 Blur read-site), both zero-code substrate rides; concentration anchors on the caster's buff and companion buffs carry `_dependent_on_caster_concentration` so the whole aura drops in lock-step. Dim-light radius + fiend/undead-melee blinding flash GM-narrated. **See Invisibility (#42) ✅ v2.509.0** — a 1-hour `sees_invisible` flag-buff (Bard/Sorcerer/Wizard) so the table can see who can pierce invisibility; the flag IS the mechanic. Negating the v2.499.0 `effects.invisible` attack-edge when the See-Invisibility caster sits on the other side of the roll was filed as a follow-up; detection + Ethereal-Plane sight stay GM-narrated. **See Invisibility attack-edge (#43) ✅ v2.510.0** — closes that follow-up: new `_target_sees_invisible` hub-read folded into the v2.152.0 invisible-attacker advantage across all three attack branches (PC `/attack` bonused + bonusless, NPC `/npc_attack`), so an invisible attacker (PC or NPC) loses its advantage against a target carrying `effects.sees_invisible`. The target-side invisibility disadvantage is driven by the manual `attacker_cant_see_target` field (which also covers darkness) and is left untouched — See Invisibility grants no darkvision. **Globe of Invulnerability (#44) ✅ v2.511.0** — a 1-minute concentration flag-buff (Sorcerer/Wizard) carrying `globe_of_invulnerability: True` + an explicit `spell_immunity_max_level: 5` threshold the table can read; the response echoes it. The barrier geometry (who's inside the 10-ft radius; inside-vs-outside caster) is a filed follow-up — the spatial AoE-shape work sits against Maps 2.0, the same boundary the Holy Aura aura sits behind. **The `/cast_spell` block shipped v2.513.0** — `_target_globe_blocks_spell` compares the spell's BASE level (RAW "even if cast using a higher level spell slot") against `spell_immunity_max_level` and rejects a single-target ≤-threshold spell at a globe'd target with 409 `globe_blocks_spell` (self-casts skipped; GM `override` bypasses; AoE per-target exclusion stays GM-narrated). **Antilife Shell (#45) ✅ v2.512.0** — a 1-hour concentration flag-buff (Druid-only) carrying `antilife_shell: True`. The moving 10-ft radius, hedging out living creatures, the can't-pass-or-reach-through enforcement, and the "spell ends if a creature is forced through" clause are a brand-new movement-barrier substrate with no existing ride, filed against Maps 2.0 alongside the Globe + Holy Aura geometry; the undead/construct exception is GM-narrated. Remaining candidates: the heavy-substrate ones — See Invisibility (poison/frightened condition-immunity rides the substrate; max-HP + WIS-save halves need more), Holy Aura (all-saves advantage + attacker-disadvantage ride the new substrates but it's a 30-ft aura), See Invisibility (invisibility-detection model — likely GM-narrated), Antilife Shell / Globe of Invulnerability (AoE-shape), the Conjure family (summon-catalog depth, filed separately). **The per-spell list below is a historical Phase 1 record — Phase 2 ships are tracked in CHANGELOG by their `Phase 2 #N` tag, not here.**
> **Tracked in:** [`TODO.md`](../../TODO.md) → SRD 5e Audit
> (v2.434.0 refresh) → "P2: Cast-and-broadcast utility-spell
> mechanical depth."

---

## Goal

Close the long tail of SRD utility spells where SimpleVTT currently
casts (consumes the slot, broadcasts the `feature_used` card to the
roll log) but doesn't *mechanize the effect*. After Phase 1 of
spell-utility-upcast.md closed duration scaling and Phase 4 closed
rider/bonus scaling, the remaining ~250 SRD utility spells fall
into one of two buckets:

- **Bucket A — mechanically simple but unwired.** Spells with a
  clear server-side effect that the engine could enforce, but
  nobody's written the handler yet. True Strike (self-buff with
  next-attack-advantage), Find Steed (summon a horse-shaped
  companion via the existing `_summon_companion` path), Bless
  Water (turn a flask into holy water for the demo's potion
  catalog), etc. **Phase 1 ships these.**

- **Bucket B — RAW-narrative by design.** Spells whose effect is
  inherently narrative or session-context-dependent (Detect
  Magic's sensory output, Prestidigitation's GM-improvised
  effects, Identify's item-property reveal, Comprehend
  Languages' translation). Filed permanently as GM-narrated.

The arc consumes Bucket A spell by spell. Each ship adds one
spell's mechanical effect + harness test + (where relevant) a new
substrate entry on an existing buff/condition/summon map.

---

## Phase 1 — first five demonstrators

The following spells are the highest-leverage Bucket A candidates.
Each becomes one or two commits.

### 1. True Strike (Cantrip) — ✅ shipped v2.437.0

RAW PHB p.284: "You extend your hand and point a finger at a
target in range. Your magic grants you a brief insight into the
target's defenses. On your next turn, you gain advantage on your
first attack roll against the target, provided that this spell
hasn't ended."

**Implementation (v2.437.0):**

- New `/cast_true_strike` endpoint. Body: `{character_id, target_combatant_id}`.
- Installs a 1-round concentration buff on the caster carrying `effects.attack_advantage_vs_target_combatant_id` bound to the chosen target's combatant id.
- **No new attack-pipeline hook needed.** Rides the existing v2.158.53 `_attacker_has_vow_of_enmity_vs_target` helper that the `/attack` endpoint already calls — that helper is generic across all buff keys and picks up the effect regardless of who installed it.
- Caster gate: knows True Strike OR is in `{bard, sorcerer, warlock, wizard}` per RAW.
- Concentration replaces any existing concentration buff on the caster (Hunter's Mark / Hex semantics).

**RAW-bent v1:** RAW says "*first* attack roll." This v1 grants advantage on *every* attack against the marked target while the buff is active. Bounded by the 1-round duration — a multi-attack character at high level gets advantage on every attack against the marked target in that one turn. Filed for Phase 1.5: a generic buff-consume-on-hit contract (the existing Feinting Attack broadcast already names `next_attack_advantage: true` and would benefit from the same hook).

**Harness:** 4 tests (`tests/harness/test_cast_true_strike.py`):

- Buff installs with the right target-binding effect (`attack_advantage_vs_target_combatant_id`).
- Buff carries `concentration: true` + `duration_rounds: 1`.
- Non-caster (Krieger Stonefist, Barbarian) → 409 cannot_cast.
- Missing `target_combatant_id` → 400.

### 2. Find Steed (L2 paladin) — ✅ shipped v2.441.0 (Phase 1 closer)

RAW PHB p.240: "You summon a spirit that assumes the form of an
unusually intelligent, strong, and loyal steed... the steed takes
on a form that you choose: a warhorse, a pony, a camel, an elk, or
a mastiff."

**Implementation (v2.441.0):**

- Five new `_COMPANION_TEMPLATES` entries — `find-steed-warhorse`
  / `find-steed-pony` / `find-steed-camel` / `find-steed-elk` /
  `find-steed-mastiff`. Stats sourced from the SRD monster JSON
  files at `app/data/local/dnd5e/monsters/`. Large steeds
  (warhorse / camel / elk) use `size=2`; Medium (pony / mastiff)
  use `size=1`.
- New `/cast_find_steed` endpoint. Body: `{character_id,
  steed_type, x?, y?, initiative?}`. Caster gate: knows Find
  Steed OR is a paladin. 400 if `steed_type` is missing or not
  one of the five RAW choices.
- Spawned via the v2.99.437 `_summon_companion` path with
  `concentration_bound=True` — plugs into the v2.113.0
  `_drop_paired_concentration_buffs` cascade so future
  concentration breaks (incapacitated paladin, hit-save fails,
  etc.) dismiss the steed RAW-correctly.
- The summon is a real combatant: own token + init slot + HP /
  AC dict + the existing damage / HP pipeline + `_force_move`
  movement. The caster can dismiss it manually via
  `/dismiss_companion`.

**Harness:** 4 tests (`tests/harness/test_cast_find_steed.py`):

- Warhorse happy path: summon spawns + tagged
  `is_summon` + `summoned_by` = caster +
  `concentration_bound: true`; HP/AC/speed match the SRD warhorse.
- Mastiff variant: a second steed type uses the smaller stat
  block (HP 5, AC 12, 40-ft speed).
- Krieger (Barbarian) → 409 cannot_cast.
- Missing or unknown `steed_type` → 400.

### 3. Speak with Animals (L1 ritual) — ✅ shipped v2.438.0

RAW PHB p.277: "You gain the ability to comprehend and verbally
communicate with beasts for the duration." Action, V/S, Self, 10
minutes, non-concentration. Bard/Druid/Ranger.

**Implementation (v2.438.0):**

- New `/cast_speak_with_animals` endpoint. Body: `{character_id}`.
- Installs a self-buff with `effects.speaks_with_animals: true`. Duration 100 rounds (10 min @ 6 s/round); non-concentration.
- Caster gate: knows Speak with Animals OR is in `{bard, druid, ranger}`.
- **No mechanical hook needed.** The buff's presence IS the mechanic — GMs / players read the flag directly. Proves the pattern for the long tail of "buff with a flag" utility spells.

**Harness:** 3 tests (`tests/harness/test_cast_speak_with_animals.py`):

- Buff installs with `speaks_with_animals: true` effect.
- Buff carries `duration_rounds: 100` + `concentration: false`.
- Krieger Stonefist (Barbarian) → 409 cannot_cast.

### 4. Pass Without Trace (L2) — ✅ shipped v2.440.0

RAW PHB p.264: "A veil of shadows and silence radiates from you,
masking you and your companions from detection. For the duration,
each creature you choose within 30 feet of you (including you) has
a +10 bonus to Dexterity (Stealth) checks and can't be tracked
except by magical means."

**Implementation (v2.440.0):**

- New `_SPELL_BUFF_MAP["pass-without-trace"]` substrate entry —
  concentration, 600 rounds, `effects.stealth_bonus: 10`.
- New persistent (non-consuming) Stealth-roll read site in the
  `/roll` handler (right after Supreme Sneak's consume read).
  Same shape as the v2.158.47 Emboldening Bond read site — fires
  on every Stealth check while the buff is active, doesn't drop
  the buff after a single use.
- New `/cast_pass_without_trace` endpoint. Body: `{character_id,
  target_character_ids?}`. The caster is always added to the list
  (RAW "including you"); companion targets each get their own
  buff install. Concentration is on the caster's buff only (RAW —
  ending concentration drops the bonus for everyone).
- Caster gate: knows Pass without Trace OR is in `{druid, ranger}`.
- 30-ft companion radius + "can't be tracked except by magical
  means" rider stay GM-tracked.

**Harness:** 4 tests (`tests/harness/test_cast_pass_without_trace.py`):

- Buff installs with `stealth_bonus: 10` effect (self-target).
- Buff carries `concentration: true` + `duration_rounds: 600`.
- A Stealth `/roll` while the buff is active gets `+10 (Pass without
  Trace)` in the breakdown; a second Stealth roll still gets the
  bonus (persistent, vs. consume-on-use Hide in Plain Sight).
- Krieger Stonefist (Barbarian) → 409 cannot_cast.

### 5. Spider Climb (L2) — ✅ shipped v2.439.0

RAW PHB p.277: "Until the spell ends, one willing creature you
touch gains the ability to move up, down, and across vertical
surfaces and upside down along ceilings, while leaving its hands
free. The target also gains a climbing speed equal to its walking
speed."

**Implementation (v2.439.0):**

- New `_SPELL_BUFF_MAP["spider-climb"]` substrate entry —
  distinct from the v2.195.0 `climbing` (Potion of Climbing)
  substrate, which carries an `advantage_on: ["str_check"]` extra
  that's RAW-specific to the potion. Spider Climb has no such
  advantage; reusing the climbing entry would have leaked the
  potion's effect onto the spell. The spider-climb entry stands
  alone with the right flag.
- New `/cast_spider_climb` endpoint. Body: `{character_id,
  target_character_id?}`. If `target_character_id` is omitted
  the caster targets themself (the caster counts as a willing
  creature per RAW).
- Caster gate: knows Spider Climb OR is in `{druid, sorcerer,
  warlock, wizard}`.
- Buff carries `effects.climb_speed_equals_walk: true`,
  concentration, 600 rounds (1 hour). The flag IS the mechanic
  — same shape as Speak with Animals' `speaks_with_animals`
  flag (v2.438.0).

**Why GM-narrated for the climb speed itself:** the engine
tracks no climb-speed attribute on PC sheets and the
"stick to walls" affordance interacts with map terrain that
v2.x doesn't model. Closing the climb-speed numeric is filed
against Maps 2.0.

**Harness:** 3 tests (`tests/harness/test_cast_spider_climb.py`):

- Buff installs with `climb_speed_equals_walk: true` effect.
- Buff carries `concentration: true` + `duration_rounds: 600`.
- Krieger Stonefist (Barbarian) → 409 cannot_cast.

---

## Phase 2 — Bucket A continuation

Opened v2.442.0 after Phase 1 closed at v2.441.0. Each ship adds
one more Bucket A spell on the same per-commit recipe (substrate
or endpoint + 2-4 harness tests + plan-doc flip). No phase
closure — runs indefinitely until Bucket A is exhausted.

### Shipped

- **Shield of Faith (L1)** — ✅ shipped v2.442.0. The
  `_SPELL_BUFF_MAP["shield-of-faith"]` substrate + the
  `_read_target_ac` ac_bonus walker were already wired
  (v2.97.38 / v2.97.39); this ship just added the
  `/cast_shield_of_faith` endpoint so the substrate is reachable.
  Body: `{character_id, target_character_id?}`. Gates
  cleric/paladin. 4 harness tests including a target_ac round-trip
  via /attack that verifies the +2 lands.

- **Mage Armor (L1)** — ✅ shipped v2.443.0. Same shape as Shield
  of Faith — the `_SPELL_BUFF_MAP["mage-armor"]` substrate was
  wired v2.99.422 (`ac_bonus: 3`, 4800 rounds = 8 h, non-
  concentration); this ship just added the `/cast_mage_armor`
  endpoint. Body: `{character_id, target_character_id?}`. Gates
  sorcerer/wizard. 4 harness tests including a target_ac
  round-trip via /attack that verifies the +3 lands. The "while
  unarmored" RAW rider stays GM-tracked.

- **Feather Fall (L1 reaction)** — ✅ shipped v2.444.0. New
  `_SPELL_BUFF_MAP["feather-fall"]` substrate (10 rounds = 1 min,
  non-concentration, `effects.feather_fall: True` flag) + new
  `/cast_feather_fall` endpoint. Multi-target up to 5 per RAW;
  the caster is always added automatically. Same flag-buff shape
  as Speak with Animals (v2.438.0) and Spider Climb (v2.439.0)
  — the engine doesn't model falling damage at all (no
  elevation tracking) so the flag IS the mechanic; the GM
  narrates the "no falling damage" rider. 5 harness tests.

- **Tongues (L3)** — ✅ shipped v2.445.0. New
  `_SPELL_BUFF_MAP["tongues"]` substrate (600 rounds = 1 hour,
  non-concentration, `effects.tongues: True` flag) + new
  `/cast_tongues` endpoint. Single-target touch (caster or
  another willing creature). Same flag-buff shape as Speak with
  Animals (v2.438.0) but for any spoken language, not just
  beast-speech. The "understands and is understood" rider is
  permanently GM-narrated; the engine surfaces the flag so the
  table can see Tongues is active. 3 harness tests.

- **Mass Healing Word (L3)** — ✅ shipped v2.467.0. **First
  multi-target heal on the cast-and-broadcast arc.** Same
  mechanical-mutation engine path as Cure Wounds (v2.463.0) and
  Healing Word (v2.464.0) but wrapped in a per-target loop.
  Rolls `1d4 + spellcasting_mod` ONCE, applies to up to 6
  targets, broadcasts one `character_hp_update` per healed
  target plus a single `feature_used` summarizing the cast.
  Body: `{character_id, target_character_ids: [...]}`. Class
  gate: bard/cleric (narrower than Healing Word's bard/cleric/
  druid — RAW excludes Druid). Atomic guarantee: if any target
  id is unknown the endpoint returns 404 BEFORE mutating any
  state. Opens the per-target loop pattern that future multi-
  target heals (Mass Cure Wounds, Aid v2, Beacon of Hope) can
  mirror. 5 harness tests including the atomicity guarantee.

- **`/eat_goodberry` consume endpoint** — ✅ shipped v2.466.0.
  Closes the loop on the v2.465.0 Goodberry buff. New consume
  endpoint decrements `goodberry_charges` in the holder's buff
  state, removes the buff entirely when the counter hits 0, and
  heals the eater for 1 HP via the same `_apply_hp_change` path
  Cure Wounds / Healing Word use. Body:
  `{character_id, target_character_id?}` — caster holds the
  berries, eater (defaulting to caster) consumes one. **First
  paired-endpoint ship on the arc** — v2.465.0 installed the
  substrate; v2.466.0 drives it. Unlocks future install+consume
  pairs (Aganazzar's Scorcher pearls, alchemical-token cantrips,
  etc.). 5 harness tests including cross-character feeding
  (Mira casts, Krieger eats) and counter exhaustion (eat 10
  times → buff removed).

- **Goodberry (L1)** — ✅ shipped v2.465.0. New
  `_SPELL_BUFF_MAP["goodberry"]` substrate (14400 rounds = 24h,
  non-concentration, `effects.goodberry_charges: 10` counter) +
  new `/cast_goodberry` endpoint. Charge-counter buff shape —
  same pattern as Bless Water's v2.447.0 `holy-water-flask`
  buff, but with a multi-charge counter (10 berries vs. 1
  flask). Self-cast only per RAW. Gates druid/ranger only —
  narrowest two-class gate on the arc alongside Identify's
  bard/wizard. v1 leaves berry consumption GM-narrated; a
  future commit can add `/eat_goodberry` to decrement the
  counter + heal via `_apply_hp_change`. Generalizes the
  charge-counter buff pattern from single-use to multi-charge,
  opening a fourth shape bucket: **carry-forward consumable
  counter**. 4 harness tests including a Ranger happy path and
  a Cleric narrow-gate.

- **Healing Word (L1)** — ✅ shipped v2.464.0. Companion ship
  to Cure Wounds v2.463.0 — same mechanical-mutation shape but
  with a smaller die (`1d4` vs `1d8`), a narrower class gate
  (Bard/Cleric/Druid only — no Paladin/Ranger per RAW), and 60-ft
  range rather than touch. New `/cast_healing_word` endpoint
  mirrors the Cure Wounds structure end-to-end. v1 skips both the
  bonus-action chip gate and upcast scaling. 5 harness tests
  including a Paladin → 409 that asserts the narrow gate vs.
  Cure Wounds' broader Bard/Cleric/Druid/Paladin/Ranger list.
  Proves the mechanical-non-buff bucket scales across die size +
  class list + range without needing per-spell substrate.

- **Cure Wounds (L1)** — ✅ shipped v2.463.0. **Third
  mechanical non-buff cast on the arc.** New `/cast_cure_wounds`
  endpoint rolls `1d8 + spellcasting_mod`, mutates the target's
  HP through the canonical `_apply_hp_change` helper, and
  broadcasts `character_hp_update`. A heal at 0 HP automatically
  flips `death_saves.status` from dying/stable/dead back to
  alive — RAW revival semantics for free. Body:
  `{character_id, target_character_id}`. Class gate: bard/cleric/
  druid/paladin/ranger. v1 skips upcast scaling (each slot above
  L1 adds another d8 per RAW); a future commit can layer in a
  `slot_level` body param. 5 harness tests including a 0-HP
  revival path (uses Caelan rather than Krieger because Krieger's
  Half-Orc Relentless Endurance interferes with the dying-state
  setup). The mechanical-non-buff bucket now has three exemplars:
  death-save flip (v2.461.0), buff-strip (v2.462.0), HP-write
  (v2.463.0) — fully tooling the pattern.

- **Lesser Restoration (L2)** — ✅ shipped v2.462.0. **Second
  mechanical non-buff cast on the arc** (after Spare the Dying
  v2.461.0). New `/cast_lesser_restoration` endpoint takes a
  `condition_key` body param, validates the target carries that
  condition as a buff, calls the existing `_remove_buff` helper
  to strip it, and broadcasts a `feature_used` card. Body:
  `{character_id, target_character_id, condition_key}`. Class
  gate: bard/cleric/druid/paladin/ranger. `condition_key`
  allowlist: `{blinded, deafened, paralyzed, poisoned,
  diseased}`. 409 `condition_not_present` if no matching buff
  on the target (RAW: must have something to cure). The
  "mechanical non-buff" bucket now has two exemplars — death-
  save-state mutation (v2.461.0) + buff-strip mutation
  (v2.462.0) — both wiring into existing engine paths without
  inventing new substrate. 5 harness tests.

- **Spare the Dying (Cantrip)** — ✅ shipped v2.461.0. **First
  mechanical non-buff cast on the arc** — unlike Identify
  (v2.459.0) and Purify Food and Drink (v2.460.0), Spare the
  Dying actually mutates engine state. New `/cast_spare_the_dying`
  endpoint validates the target is at 0 HP, flips
  `death_saves.status` → `stable` via the existing
  `_set_death_save_state` helper, and broadcasts the canonical
  `character_death_save` event the death-save UI already listens
  for. Body: `{character_id, target_character_id}` (both
  required). Class gate: cleric only. Error gates: 409
  `target_not_at_zero_hp` (RAW requires 0 HP) + 400 missing
  target + 409 non-cleric. Opens the "mechanical non-buff"
  pattern bucket for future ships that need surgical state
  mutation (Lesser Restoration, Mass Healing Word, etc.). 4
  harness tests including a sheet round-trip after the cast.

- **Purify Food and Drink (L1 ritual)** — ✅ shipped v2.460.0.
  **Second non-buff cast on the arc** (after Identify v2.459.0).
  No substrate entry, no buff install — RAW-instantaneous,
  affects environmental food/drink the engine doesn't model.
  New `/cast_purify_food_and_drink` endpoint broadcasts a
  `feature_used` card; the GM narrates which rations/wineskins
  were purified. Body: `{character_id}` — no target, since the
  5-ft sphere is GM-placed. Gates cleric/druid/paladin (the
  three RAW casters). 4 harness tests covering all three caster
  classes + Barbarian → 409. Two non-buff casts in a row proves
  the cast-and-broadcast arc can ship spells where the engine
  has nothing to track — the broadcast IS the ship.

- **Identify (L1 ritual)** — ✅ shipped v2.459.0. **First
  non-buff cast on the arc.** No substrate entry, no buff
  install — Identify is RAW-instantaneous, so the new
  `/cast_identify` endpoint broadcasts a `feature_used` card
  naming what's being identified without any on-going effect to
  track. The GM types the learned properties in chat. Body:
  `{character_id, target_character_id?, target_item_name?}` —
  both targets optional, four feature-card sentence shapes
  based on which targets are provided. Gates bard/wizard only
  per RAW. 4 harness tests including an explicit "no buff
  installed" assertion. Proves the cast-and-broadcast arc
  generalizes beyond buff-shaped spells; future instantaneous
  spells (Purify Food and Drink, Spare the Dying, Cure Wounds,
  etc.) can mirror this shape.

- **Detect Poison and Disease (L1 ritual)** — ✅ shipped
  v2.458.0. New
  `_SPELL_BUFF_MAP["detect-poison-and-disease"]` substrate (100
  rounds = 10 min, concentration,
  `effects.senses_poison_and_disease_within_30ft: True` flag) +
  new `/cast_detect_poison_and_disease` endpoint. Flag-buff
  shape (same as Detect Evil and Good v2.456.0 / Detect Magic
  v2.457.0). Self-cast only per RAW. Gates cleric/druid/paladin/
  ranger — divine + primal only (no arcane casters per RAW).
  Completes the L1-ritual detection trio on the cast-and-
  broadcast arc; the three spells share the same flag-buff
  structure and together cover every L1 divination ritual in
  the SRD. 4 harness tests including Wizard → 409.

- **Detect Magic (L1 ritual)** — ✅ shipped v2.457.0. New
  `_SPELL_BUFF_MAP["detect-magic"]` substrate (100 rounds = 10
  min, concentration, `effects.senses_magic_within_30ft: True`
  flag) + new `/cast_detect_magic` endpoint. Flag-buff shape
  (same as Detect Evil and Good v2.456.0). Self-cast only per
  RAW. Gates bard/cleric/druid/paladin/ranger/sorcerer/wizard —
  the widest class gate on the cast-and-broadcast arc (7 of 11
  SRD caster classes, all except Barbarian/Fighter/Monk/Rogue).
  4 harness tests including Wizard + Cleric happy paths to
  exercise both arcane and divine sides of the wide gate.

- **Detect Evil and Good (L1)** — ✅ shipped v2.456.0. New
  `_SPELL_BUFF_MAP["detect-evil-and-good"]` substrate (100 rounds
  = 10 min, concentration,
  `effects.senses_evil_and_good_within_30ft: True` flag) + new
  `/cast_detect_evil_and_good` endpoint. Flag-buff shape — same
  as Tongues (v2.445.0) / Comprehend Languages (v2.450.0) / Jump
  (v2.453.0): the flag IS the mechanic, the GM narrates what the
  caster senses. Self-cast only per RAW. Gates cleric/paladin
  (narrowest class gate on the cast-and-broadcast arc so far).
  4 harness tests including Wizard → 409 (Wizards are NOT on
  this spell's RAW class list).

- **Protection from Evil and Good (L1)** — ✅ shipped v2.455.0.
  Rides the existing
  `_SPELL_BUFF_MAP["protection-from-evil-and-good"]` substrate +
  the pre-existing /use_attack attacker-disadvantage gate + the
  condition-install gate + the save-roll suffix. New
  `/cast_protection_from_evil_and_good` endpoint exposes the
  substrate. Body: `{character_id, target_character_id?}`. Self-
  or-touch. Gates cleric/paladin/warlock/wizard. All four RAW
  benefits (disadvantage on attacks from 6 creature types,
  immunity to their charm/frighten/possess, advantage on new
  saves vs ongoing effects from them, the protected-types list)
  are pre-wired into the engine — zero new mechanical code. 4
  harness tests including a protected_types round-trip vs the
  RAW 6-type list.

- **Sanctuary (L1)** — ✅ shipped v2.454.0. Rides the existing
  `_SPELL_BUFF_MAP["sanctuary"]` substrate + the v2.97.52 install-
  time DC bake-in + the pre-existing /use_attack attacker-Wis-save
  gate. New `/cast_sanctuary` endpoint adds a one-click cleric
  cast path. Body: `{character_id, target_character_id?}`. Self-
  or-touch. Gates cleric only (RAW). Response + broadcast surface
  `dc = 8 + prof + spellcasting_mod` so any chat/sheet card can
  render it without recomputing. First Phase 2 ship to install a
  save-DC effect — the pattern future save-or-suck spells will
  follow. 5 harness tests including a DC round-trip vs the
  caster's sheet.

- **Jump (L1)** — ✅ shipped v2.453.0. New
  `_SPELL_BUFF_MAP["jump"]` substrate (10 rounds = 1 min,
  non-concentration, `effects.jump_distance_tripled: True` flag)
  + new `/cast_jump` endpoint. Flag-buff shape (same as Tongues
  v2.445.0 / Comprehend Languages v2.450.0): the flag IS the
  mechanic, the GM narrates the tripled distance. Mirrors the
  v2.99.x Monk Step of the Wind precedent that uses
  `jump_distance_doubled: True` for its own jump rider. Single-
  target self-or-touch. Gates druid/ranger/sorcerer/wizard. 4
  harness tests.

- **Longstrider (L1)** — ✅ shipped v2.452.0. Same shape as
  Shield of Faith / Mage Armor — the
  `_SPELL_BUFF_MAP["longstrider"]` substrate was wired
  pre-v2.452.0 (`speed_bonus_ft: 10`, 600 rounds = 1 h,
  non-concentration); this ship just adds the
  `/cast_longstrider` endpoint. Body: `{character_id,
  target_character_id?}`. Gates bard/druid/ranger/wizard. The
  pre-existing `effective_speed_walk` reader (lit by the v2.368.0
  Aura of Glory ship) sums `effects.speed_bonus_ft` across active
  buffs, so the move-endpoint speed cap rises automatically — no
  new mechanical code. 4 harness tests including a self-vs-ally
  routing split.

- **Comprehend Languages (L1 ritual)** — ✅ shipped v2.450.0.
  New `_SPELL_BUFF_MAP["comprehend-languages"]` substrate (600
  rounds = 1 hour, non-concentration,
  `effects.comprehends_languages: True` flag) + new
  `/cast_comprehend_languages` endpoint. Same flag-buff shape as
  Tongues (v2.445.0) but understand-only (not speak-also) and
  self-targeted. Gates bard/sorcerer/warlock/wizard. 3 harness
  tests.

- **Phase 1.5 — buff-consume-on-attack contract** — ✅ shipped
  v2.449.0; **Feinting Attack opt-in** ✅ shipped v2.451.0. Closes
  the v2.437.0 True Strike RAW-bend. New contract in the
  `/attack` endpoint walks the attacker's buffs after the attack
  resolves and drops any buff with `effects.consume_on_attack:
  True`. True Strike's buff entry (v2.437.0) updated to opt into
  the contract via the new flag. RAW "your *first* attack roll"
  now matches engine behavior: the advantage drops after the
  first /attack. The contract is generic — any future "next
  attack" effect (Vow of Enmity, etc.) can opt in by setting the
  same flag. **v2.451.0** wired Feinting Attack as the second
  consumer: optional `target_combatant_id` body param on
  `/use_feinting_attack` installs a `feinting-attack` buff
  carrying both `attack_advantage_vs_target_combatant_id` (lit by
  the v2.158.53 helper) AND `consume_on_attack: True`. Zero new
  attack-pipeline code — same lesson as True Strike. Legacy
  `target_name`-only path stays GM-narrated. **2 v2.449.0 tests**
  (consumer path + no-op control) + **3 v2.451.0 tests** (legacy
  path, opt-in install, /attack consumes).

- **Hellish Rebuke DEX save-for-half** — ✅ shipped v2.448.0.
  Phase 2 #7. Builds on v2.446.0: adds the attacker's DEX save
  vs the caster's spell save DC. Halves damage on success per
  RAW. v1 supports PC attackers only (the attacker_char_id
  lookup yields a Character row); NPC attackers fall through to
  the v2.446.0 full-damage behavior (filed for a future NPC-save
  ship). Broadcast now carries `save_dc`, `save_total`,
  `save_breakdown`, `save_passed` alongside the v2.446.0 damage
  fields. The existing v2.446.0 test got extra assertions to
  verify the save half-damages correctly (damage_total ∈ [2, 20]
  when save passes vs [4, 40] when save fails).

- **Bless Water (L1)** — ✅ shipped v2.447.0. New
  `_SPELL_BUFF_MAP["holy-water-flask"]` substrate (14400 rounds
  = 24 h, non-concentration, `effects.holy_water_charges: 1`) +
  new `/cast_bless_water` endpoint. Self-targeted — the caster
  consumes a flask of water and gains a marker buff representing
  the new flask of holy water. The 2d6 radiant splash damage on
  undead/fiends per RAW stays GM-narrated. Gates cleric/paladin.
  3 harness tests.

- **Hellish Rebuke auto-damage-roll** — ✅ shipped v2.446.0.
  Phase 2 #5. Closes the v2.71.0 filed "Auto-roll +
  auto-damage-to-attacker" gap on the existing slot-based
  Hellish Rebuke reaction-cast flow. The v2.71.0 ship wired the
  reaction-watcher branch but left the damage roll + apply as
  GM-narrated; this commit rolls server-side and applies via
  `_apply_damage_to_combatant` when the attacker's combatant_id
  is in the reaction params. v1 applies FULL damage; the RAW DEX
  save-for-half stays GM-narrated (GM can `/undo_attack_damage`
  with the cast_id to halve). Broadcast now carries
  `damage_total`, `damage_applied`, and `damage_breakdown`
  alongside the legacy `damage_expr`. 1 new harness test
  exercising the end-to-end Krieger-hits-Magnus → Hellish Rebuke
  → damage-applied-to-Krieger flow.

### Remaining candidates (filed)

Next 4 highest-leverage spells from Bucket A:

- **Feather Fall (L1 reaction)** — slow-fall buff that triggers on
  the next falling-damage event.
- **Mage Armor (L1)** — set AC to 13 + DEX modifier; persists 8 h.
- **Hellish Rebuke (L1 reaction)** — fire damage in response to
  taking damage. Already wired for the Tiefling racial variant
  (v2.395.0); needs the spell variant exposed.
- **Tongues (L3)** — universal speech buff; same shape as Speak
  with Animals.

---

## Non-goals

- **Bucket B spells** — Detect Magic, Identify, Prestidigitation,
  etc. stay permanently GM-narrated. The plan does NOT ship them.
- **Combat spells with existing wiring** — Magic Missile, Cure
  Wounds, etc. are already mechanized through the standard
  `/cast_spell` damage/healing path.
- **Spells with substrate-blocking dependencies** — light spells
  (Light, Dancing Lights, etc.) wait on Maps 2.0's dynamic
  lighting substrate. Sound-based spells (Silence, Thunderwave)
  wait on the area-sound substrate. Filed in the respective
  Maps 2.0 + audio substrate plans.

---

## Test contract

Each Phase 1 ship lands:

- 1 new substrate entry (buff map / summon map / etc.) OR 1 new
  bespoke endpoint, depending on the spell's shape.
- 2–3 new harness tests covering install + the mechanical effect
  + (where applicable) duration end.
- Plan-doc status line flipped to ✅ shipped with the version
  number.

---

## Closure criteria

Phase 1 closes when all 5 demonstrators are shipped. Phase 2+ runs
indefinitely against Bucket A; the arc closes when Bucket A is
empty or the remaining candidates are too small to justify the
substrate work (e.g. one-off spells with bespoke mechanics).
