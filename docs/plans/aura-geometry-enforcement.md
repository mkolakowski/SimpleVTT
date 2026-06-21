# Aura & Barrier Geometry Enforcement — Design Plan

**Status:** ✅ CLOSED — all phases shipped (P1 v2.516.0, P2 v2.517.0, P3 v2.518.0)
**Parent / foundation:** [auras.md](auras.md) (the shipped `_tick_auras` per-turn radius engine) + [ruler-and-range.md](ruler-and-range.md) (distance primitives + AoE templates).
**Motivating ships:** the cast-and-broadcast tail's geometry-bound spells — Holy Aura (#41, v2.508.0), Globe of Invulnerability (#44, v2.511.0 + the `/cast_spell` block v2.513.0), and Antilife Shell (#45, v2.512.0). Each shipped as a **flag-buff with the spatial half GM-narrated**; this plan replaces the GM-narration with real engine enforcement.
**Related code:** `app/routes/tabletop_routes.py` — `_tick_auras`, `_distance_ft_between_chars`, `_aura_of_protection_bonus`, `_resolve_sphere_aoe_combatant_ids`, `_concentration_aoes`, the `token_move` endpoint, `_target_globe_blocks_spell`.

---

## Goal

Three spells shipped this arc carry a real area effect that the engine
currently leaves to the GM because there is no substrate for **"who is
inside this moving radius right now"** and **"can this creature cross
this barrier."** This plan builds those two substrates on top of the
already-shipped per-turn aura tick and distance helpers, then retro-wires
the three spells (and any future area spell) to enforce mechanically.

| Spell | Shipped (flag-buff) | GM-narrated half this plan closes |
|---|---|---|
| **Holy Aura** (#41) | `save_advantage: True` + `attackers_have_disadvantage: True` placed on caller-chosen targets | **Membership**: the 30-ft aura moves with the caster; creatures entering/leaving should gain/lose the benefit automatically. |
| **Globe of Invulnerability** (#44) | `globe_of_invulnerability` + `spell_immunity_max_level` + the `/cast_spell` block (v2.513.0) | **Inside/outside**: the block currently fires regardless of the offending caster's position (GM `override` is the escape hatch). RAW only blocks spells cast *from outside* the 10-ft barrier. |
| **Antilife Shell** (#45) | `antilife_shell: True` flag | **Movement barrier**: the moving 10-ft shell should hedge living creatures out — they can't pass or reach through. |

---

## 1. What already works (verified v2.515.0)

All in `app/routes/tabletop_routes.py`.

### A. Per-turn aura tick — `_tick_auras`
The [auras.md](auras.md) P5 ship built a per-turn aura tick fired from the
`update_battle` turn-advance hook. It walks combatants, gates on
radius via `_distance_ft_between_chars`, and applies damage / temp-HP /
heal / save-or-condition to creatures in an emitter's radius. **This is
the membership engine Phase 1 extends** — instead of applying a tick
effect, Phase 1 installs/removes a derived buff based on radius
membership.

### B. Distance / radius
- `_distance_ft_between_chars(db, campaign_id, a_id, b_id)` → feet
  between two combatants' tokens (Chebyshev "5-5-5" on square grids via
  `_distance_ft_between_points`). Returns `None` off-grid; `0.0` for self.
- `_aura_of_protection_bonus` is the canonical **walk-combatants +
  gate-on-radius** precedent, including the **"None distance → assume in
  range"** fallback for off-grid narrative scenes. Both new substrates
  reuse this pattern so off-grid tables keep working (GM-narrated when no
  map is laid out).

### C. AoE shape resolution
- `_resolve_sphere_aoe_combatant_ids` / `_resolve_cone_aoe_combatant_ids`
  / `_resolve_line_aoe_combatant_ids` resolve a shape + origin into the
  combatant-id list inside it (one-shot snapshot, used by `/cast_spell`'s
  `target_set`). Phase 1's membership read is the **persistent,
  re-evaluated** sibling of the sphere resolver.

### D. Persistent AoE markers + concentration teardown
- `_concentration_aoes` holds map markers (Spirit Guardians, Hypnotic
  Pattern); `_clear_caster_concentration_aoes` drops them when the
  caster's concentration ends. A moving aura/barrier marker rides this
  registry so it vanishes RAW-correctly on concentration break, and the
  client can already render `concentration_aoe_update`.

### E. Movement endpoint
- `token_move` (the range-enforcement gate from ruler-and-range.md) is
  where Phase 3's barrier gate lives — it already computes source→dest
  distance and returns a 409 the client renders.

### F. The choke-point reads shipped this arc
- `_target_globe_blocks_spell` (v2.513.0) already gates `/cast_spell`;
  Phase 2 only swaps its "assume outside" default for a real distance
  check.

---

## 2. Phases

### Phase 1 — Aura membership auto-apply / auto-remove (Holy Aura) — ✅ shipped v2.516.0

**Shipped simpler than designed below:** the v2.99.449 `buff` aura
payload (Aura of Alacrity / Warding) already does install-on-enter +
lapse-on-leave via `_tick_auras` + a short refresh duration. So
`cast_holy_aura` just registers `effects.aura = {radius_ft: 30, affects:
"allies", buff: {key: "holy-aura-radiance", effects: {save_advantage,
attackers_have_disadvantage}, duration_rounds: 2}}` on the caster's
anchor buff — zero new engine code. The tick grants a distinct
`holy-aura-radiance` key (the reads are key-agnostic) so it never
clobbers the cast-time `holy-aura` buffs on chosen targets. The
"creatures of your choice" subset stays the cast-time selection
(generalized to in-range allies); the design below (a chosen-set ∩
in-range registry) is retained as the fuller model if needed later.



A registry of **active auras** keyed by emitter combatant: `{emitter_char_id,
radius_ft, buff_template, faction}`. On the per-turn `_tick_auras` pass
(and on emitter movement), for every combatant:

- inside the radius + matches the faction filter → ensure the derived
  buff is installed (idempotent; tagged `_aura_derived: True` +
  `source_char_id`);
- outside → remove any `_aura_derived` buff from this emitter.

Holy Aura registers `{radius: 30, buff: {save_advantage, attackers_have_disadvantage}, faction: chosen}`.
The "creatures of your choice" clause stays a cast-time selection (the
emitter records the chosen char-ids; membership is the intersection of
*chosen* ∩ *in-radius*). Generalizes to any "allies within N ft get X"
effect (Aura of Vitality, Paladin auras already partly modeled, etc.).

**Test:** a chosen ally inside 30 ft has the buff after a turn tick;
move them out (or the emitter away) → buff removed on the next tick;
concentration break → all derived buffs dropped via the existing cascade.

### Phase 2 — Inside/outside enforcement (Globe of Invulnerability) — ✅ shipped v2.517.0

Replace the v2.513.0 globe gate's "assume the caster is outside" default
with a real check: the offending caster is "outside the barrier" when
`_distance_ft_between_chars(caster, globe_holder) > globe_radius_ft`
(10 ft). When the caster is **inside** (≤ radius), the block does **not**
fire (RAW — a creature inside the barrier can cast freely). Off-grid
(`None` distance) keeps the v2.513.0 behavior (assume outside) so
narrative scenes are unchanged; GM `override` still bypasses.

**Test:** an enemy ≥ 15 ft away casting a ≤5 spell at the globe holder →
409 (as today); the same enemy moved to within 10 ft → not blocked;
off-grid → blocked (unchanged).

### Phase 3 — Movement-barrier substrate (Antilife Shell) — ✅ shipped v2.518.0

The genuinely new piece. A registry of **barriers** keyed by emitter:
`{emitter_char_id, radius_ft, predicate}`. In `token_move`, after the
range gate, reject (409 `barrier_blocks_move`) a move whose destination
would bring an *affected* creature inside (or across) a barrier it isn't
already inside. Antilife Shell's predicate: the mover is a living
creature (not undead/construct — read the mover's type tag). The
"affected creature can still attack with reach/ranged through the
barrier" clause needs no code (only movement is gated). The "spell ends
if the emitter forces an affected creature through" clause fires when the
emitter's *own* move would overlap an affected creature → drop the
emitter's concentration via the existing cascade.

**Test:** a living NPC's `token_move` into the shell → 409
`barrier_blocks_move`; an undead NPC's move in → allowed; GM `override`
bypasses; emitter moving onto a living creature → shell ends.

---

## 3. Non-goals

- **Non-square grids / hex** — the distance helper is square-grid
  Chebyshev; hex is filed against the broader Maps 2.0 work.
- **Line-of-effect / cover** — these substrates are pure radius; walls
  and cover stay GM-narrated.
- **Re-deriving "creatures of your choice"** — Phase 1 keeps the
  cast-time selection; it does not auto-add newly-entering creatures the
  caster didn't originally choose (RAW Holy Aura fixes the set at cast).

---

## 4. Test contract

Each phase lands harness tests asserting the membership/enforcement
state after the relevant trigger (turn tick, cast, or move), plus an
off-grid control proving the `None`-distance fallback preserves the
pre-existing GM-narrated behavior. Each phase is one or more commits on
the standard per-commit recipe (code + tests + plan-doc status flip).

---

## 5. Closure criteria

The plan closes when all three motivating spells enforce their geometry
mechanically (or a phase is explicitly deferred with a filed reason).
The substrates (`_tick_auras` membership extension + the barrier
registry) remain open for future area spells.
