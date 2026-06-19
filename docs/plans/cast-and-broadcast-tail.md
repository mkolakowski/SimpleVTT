# Cast-and-broadcast utility-spell tail — Design Plan

> **Status:** 🟠 Phase 1 in progress. Plan opens at v2.436.0; True Strike (#1) ✅ shipped v2.437.0; Speak with Animals (#3) ✅ shipped v2.438.0. Find Steed (#2) / Pass Without Trace (#4) / Spider Climb (#5) pending.
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

### 2. Find Steed (L2 paladin)

RAW PHB p.240: "You summon a spirit that assumes the form of an
unusually intelligent, strong, and loyal steed."

**Implementation sketch:**

- Reuses the existing `_summon_companion` path (the Phase 3
  Conjure/Animate Dead machinery).
- New `/cast_find_steed` endpoint that takes the chosen steed
  type (warhorse, pony, camel, elk, mastiff per RAW), spawns it
  via `_summon_companion` with the appropriate stat block from
  the SRD monster catalog, binds to the caster's concentration
  via the `concentration_bound` path.

**Harness:** 3 tests — cast spawns the steed, the steed is
controllable by the caster, dismissing the steed (concentration
drop) removes it.

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

### 4. Pass Without Trace (L2)

RAW PHB p.264: "A veil of shadows and silence radiates from you,
masking you and your companions from detection. For the duration,
each creature you choose within 30 feet of you (including you) has
a +10 bonus to Dexterity (Stealth) checks and can't be tracked
except by magical means."

**Implementation sketch:**

- New `_SPELL_BUFF_MAP["pass-without-trace"]` with
  `stealth_bonus: 10`. Multi-target (caster + companions in 30
  ft); reuses the existing buff multi-target install path.
- Concentration, 1-hour duration (600 rounds).
- Hook on Stealth-check rolls: if buff is present, add +10.
- 30-ft radius gate stays GM-tracked (Maps 2.0 / range substrate
  is filed elsewhere).

**Harness:** 3 tests — buff installs, Stealth check rolls +10,
buff drops on concentration end.

### 5. Spider Climb (L2)

RAW PHB p.277: "Until the spell ends, one willing creature you
touch gains the ability to move up, down, and across vertical
surfaces and upside down along ceilings, while leaving its hands
free. The target also gains a climbing speed equal to its walking
speed."

**Implementation sketch:**

- The existing `_SPELL_BUFF_MAP["climbing"]` entry (already
  wired) is the substrate. This phase repurposes / extends it
  for Spider Climb specifically with the right name/icon.
- Single target, concentration, 1-hour duration.
- No new mechanical hook needed beyond the existing climb-speed
  effect.

**Harness:** 2 tests — buff installs on cast, target's climbing
speed = walking speed.

---

## Phase 2+ candidates (filed)

After Phase 1 ships, the next 5 highest-leverage spells from
Bucket A:

- **Shield of Faith (L1)** — +2 AC buff, concentration, 10 minutes.
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
