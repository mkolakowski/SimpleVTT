# Cast-and-broadcast utility-spell tail — Design Plan

> **Status:** ⚪ proposed · Phase 1 unstarted. Opens at v2.436.0
> after the v2.434.0 SRD audit refresh identified this as the
> remaining ~15% of the Spells category.
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

### 1. True Strike (Cantrip)

RAW PHB p.284: "You point a finger at a target in range. Your next
attack roll against the target has advantage if you make it before
the end of your next turn. The spell ends if you attack a target
other than the one you pointed at."

**Implementation sketch:**

- New `_SPELL_BUFF_MAP["true-strike"]` entry. Effects carry
  `next_attack_advantage: true` + a `target_combatant_id` field
  that the install endpoint stamps from the cast payload.
- Concentration, 1-round duration (`duration_rounds: 1`).
- Hook in `/attack` endpoint's roll-construction branch: if the
  attacker carries a True Strike buff AND `target_combatant_id`
  matches the attack's target, override the d20 expression to
  `2d20kh1` and remove the buff.
- If the attacker hits a different target while concentrating,
  the buff drops naturally on concentration sweep (no new code).

**Harness:** 3 tests — buff installs on cast, the next attack against
the marked target rolls 2d20kh1 (assert via the breakdown), the
buff is gone after the attack.

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

### 3. Speak with Animals (L1 ritual)

RAW PHB p.277: "You gain the ability to comprehend and verbally
communicate with beasts for the duration."

**Implementation sketch:**

- Self-buff install with `speaks_with_animals: true` flag.
- 10-minute duration, non-concentration.
- No mechanical hook needed (the buff is the proof — GMs can let
  PCs converse with beasts when the buff is active).

**Harness:** 2 tests — buff installs on cast, buff times out after
100 rounds.

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
