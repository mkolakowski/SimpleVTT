# Cast-and-broadcast utility-spell tail — Design Plan

> **Status:** ✅ **Phase 1 CLOSED v2.441.0.** Plan opens at v2.436.0; True Strike (#1) ✅ shipped v2.437.0; Speak with Animals (#3) ✅ shipped v2.438.0; Spider Climb (#5) ✅ shipped v2.439.0; Pass without Trace (#4) ✅ shipped v2.440.0; Find Steed (#2) ✅ shipped v2.441.0. Phase 2+ now opens against Bucket A (Shield of Faith, Feather Fall, Mage Armor, Hellish Rebuke spell variant, Tongues, …).
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
