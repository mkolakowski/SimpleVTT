# Vision & Light — server-side sight/obscurement engine

**Status:** ✅ All phases shipped (v2.704.0–v2.710.0). The full engine is live: data model (v2.704.0), `_visibility_between` resolver (v2.705.0), PC `/attack` (v2.706.0), NPC `/npc_attack` (v2.707.0), Darkness/Daylight/Fog emitters (v2.708.0), Hide/Stealth (v2.709.0), and the client dynamic-lighting canvas overlay (v2.710.0). Plan authored v2.703.0; completed in one arc.

The one combat mechanic that is still **entirely GM-narrated** and is *not*
buildable on an existing substrate: whether an attacker can **see** its
target. RAW PHB p.194–195, attacking a target you can't see is at
**disadvantage** (and you miss-guess its location); attacking *from*
unseen (an attacker the target can't see) is at **advantage**. Today the
engine has all the *consequence* plumbing but none of the *determination*
— a GM sets a manual `attacker_cant_see_target` body flag by eye. This
plan builds the missing half: a server-side model of **light on the map**
+ **each token's vision senses**, and a resolver that answers *"can A see
B?"* so the attack pipeline (and Corona of Light, Hide, etc.) can read it
instead of asking the GM.

This is **Maps-2.0-class** work — it introduces the first map/token
*lighting* state. It is deliberately phased so each phase ships a usable
slice and the engine can stop at any phase with value banked.

---

## What already exists (reuse, don't rebuild)

The **consequences** of sight are wired; only the **determination** is missing.

- **Vision senses are modelled as flags** — `darkvision_ft`, `truesight_ft`
  (`_SPELL_BUFF_MAP["truesight"]`), `blindsight` (descriptive), `sees_invisible`
  (See Invisibility / Detect Evil & Good / Tongues), and Devil's Sight via
  `_pc_sees_in_darkness(sheet)` (reads the `devils-sight-active` buff). These
  are surfaced on `/sheet-json` derived data and ride buff/sheet effects.
- **The attack site already applies the edges.** `/attack` (both the
  single-target and second-attack paths) folds:
  - `attacker_cant_see_target` (a **manual** body flag) → **disadvantage**,
    suppressed by Feral Senses (`_pc_has_feral_senses`);
  - the invisible-attacker **advantage**, negated when the target
    `_target_sees_invisible`.
  So once a resolver can *decide* "the attacker can't see the target," the
  disadvantage already flows — Phase 2 is mostly **replacing the manual flag
  with a computed one**.
- **Corona of Light (v2.702.0)** already emits a 60-ft "bright light" marker
  conceptually (the `corona-of-light` buff carries `corona_bright_radius_ft`)
  but the light itself is GM-narrated — a natural **first light source** for
  the model.
- **Distance geometry** — `_distance_ft_between_points` + the 70px=5ft grid
  (used by Globe, Antilife, the AoE-enter trigger) gives token-to-token
  ranges for sense/light radii.
- **Token positions** live on `Token.x/y` per map; the battle hub tracks
  combatants. No token or map carries **light** state yet — that is the
  net-new model.

### The gap

There is **no model of illumination**: maps have no ambient light level, and
tokens emit no light. So nothing can compute whether a given square is in
bright / dim / darkness, and therefore nothing can compute whether attacker A
(with senses S, at range R) can see target B. That determination is the whole
plan.

---

## Data model (Phase 0)

Additive, backward-compatible. Default = "bright everywhere" so existing
campaigns behave exactly as today until a GM opts in.

- **Map ambient light** — `Map.ambient_light` enum: `bright` (default) /
  `dim` / `dark`. A bright map needs no vision rules (status quo); dim/dark
  maps engage the resolver.
- **Token light sources** — `Token.light_bright_ft` + `Token.light_dim_ft`
  (default 0/0 = emits no light). A torch is 20/20, a Light cantrip 20/20,
  Corona of Light 60/30, etc. The token carrying the source lights its own
  square + the radii.
- **Token vision senses** — normalized at resolve time from the existing
  sheet/buff flags into `{darkvision_ft, blindsight_ft, truesight_ft,
  sees_in_darkness, sees_invisible}` (no schema change — derived).
- **Spell-emitted light/darkness** — Darkness (magical darkness sphere),
  Daylight, Fog Cloud (heavy obscurement). Modeled as **token-anchored or
  placed light/darkness emitters** reusing the `_concentration_aoes` marker
  list shape (Phase 3).

No DB migration is forced in Phase 0 beyond the two nullable Map/Token
columns (one `SCHEMA_VERSION` bump + an inline migration).

---

## The resolver (Phase 1) — `_visibility_between(db, campaign_id, attacker, target)`

A pure-ish function returning one of `seen` / `obscured` / `unseen`:

1. **Illumination at the target's square** = the max of the map ambient and
   any light source within range (token light radii + placed light emitters),
   yielding `bright` / `dim` / `dark`.
2. **Apply the attacker's senses**: truesight / blindsight (within range) →
   always `seen`; darkvision treats `dark` within range as `dim`;
   `sees_in_darkness` (Devil's Sight) treats magical `dark` as `bright`.
3. **Map illumination → visibility**: `bright` → `seen`; `dim` →
   `obscured` (lightly obscured = Perception disadvantage, **not** an attack
   edge RAW, so this alone does not impose attack disadvantage); `dark` /
   heavily obscured → `unseen`.
4. **Invisibility** composes (already handled): an invisible target is
   `unseen` unless the attacker `sees_invisible`.

Phase 1 ships the resolver + unit-style harness coverage with **no caller
changes** — it can be validated in isolation before touching `/attack`.

---

## Phases

0. **Phase 0 — data model + migration (S). ✅ shipped v2.704.0.**
   `Map.ambient_light` (`bright`/`dim`/`dark`), `Token.light_bright_ft/light_dim_ft`
   (defaults preserve current behavior). Schema v82 inline migration. GM
   set-endpoints (`/settings/maps/{id}/ambient_light`; `PATCH /token/{id}`
   light radii) + surfaced on `GET /tokens` + `_token_dict`. No combat
   behavior change yet. Harness: `test_vision_light_phase0.py`.
1. **Phase 1 — `_visibility_between` resolver (M). ✅ shipped v2.705.0.**
   The resolver + `_combatant_vision_senses` extractor (folds darkvision/
   truesight/blindsight/devils-sight across buffs + sheet) + `_illumination_
   at_point` (ambient ∪ token light sources). Exposed read-only at
   `GET /visibility` for validation. Harness: `test_vision_light_phase1.py`
   (the ambient × senses × range matrix). No `/attack` change yet.
2. **Phase 2 — wire into `/attack` (M). ✅ shipped v2.706.0.** The
   `_attack_vision_edges` helper feeds both PC `/attack` branches: target
   `unseen` → **disadvantage** (`disadvantage_cant_see`); attacker `unseen`
   by the target → **advantage** (`advantage_unseen_attacker`); mutual →
   cancel. The manual `attacker_cant_see_target` flag stays a GM override;
   bright maps short-circuit (hot path untouched). Harness:
   `test_vision_light_phase2.py`. **NPC `/npc_attack` mirror ✅ shipped
   v2.707.0** (`_compute_vision_edges` core + `_npc_attack_vision_edges`
   wrapper; harness `test_vision_light_npc_attack.py`).
3. **Phase 3 — spell light/darkness emitters (M). ✅ shipped v2.708.0.**
   `_light_emitters` store + `POST`/`DELETE /light_emitter` GM endpoints.
   `darkness` → `magical_dark` (only Devil's Sight/truesight pierces, NOT
   darkvision); `daylight` → bright (dispels darkness); `fog` → heavy
   obscurement (only truesight/blindsight). `_illumination_at_point` reads
   them (precedence fog > daylight > darkness); composes with the Phase-2
   attack wiring. Harness: `test_vision_light_phase3.py`.
4. **Phase 4 — Hide / Stealth & unseen-attacker advantage (M). ✅ shipped
   v2.709.0.** `POST /hide` installs a `hidden` buff with a Stealth score;
   `_visibility_between` treats the hider as `unseen` to observers whose
   passive Perception (`_passive_perception`) is lower (truesight/blindsight
   defeat it). Rides the Phase-2 wiring → hidden attacker gets advantage;
   both `/attack` + `/npc_attack` reveal the attacker after the swing.
   Harness: `test_vision_light_phase4.py`.
5. **Phase 5 — client dynamic lighting (L). ✅ shipped v2.710.0.** A
   `drawLighting()` canvas overlay renders the ambient veil + light-source
   punches + darkness/fog emitters (offscreen-composited so the light punch
   erases only the veil). State bootstrapped from `GET /tokens` + kept live
   by the `map_ambient_light` / `light_emitter_*` WS events. Presentation
   only; covered by `tests/harness_ui/test_tabletop_canvas.py` (no-console-
   errors load). Per-player fog-of-war secrecy remains an optional non-goal.

Each phase is independently shippable. Phases 1–2 deliver the core
"attacking what you can't see" automation; Phase 5 is the visual polish that
can lag.

**Auto-place-on-cast follow-up (post-Phase-5).** The Phase-3 emitters were
GM-placed via `/light_emitter`; the follow-up wires spell casting to drop the
emitter automatically (concentration-bound, cleared on concentration end):
- **Fog Cloud** ✅ v2.711.0 — `/cast_fog_cloud` accepts a `center` and places
  a `fog` emitter at the slot-scaled radius (shared `_add_light_emitter`).
- **Darkness** ✅ v2.712.0 — new `/cast_darkness` endpoint places a fixed
  15-ft `darkness` (magical) emitter on a `center`.
- **Daylight** — pending a cast endpoint.

---

## Test contract (per phase)

- **Phase 0:** the new columns default such that an existing bright map +
  no light sources behaves identically (a regression sweep of the attack
  tests stays green); the settings endpoints round-trip the values.
- **Phase 1:** a matrix test of `_visibility_between` — bright→seen,
  dark→unseen, dark+darkvision-in-range→obscured (no attack edge),
  dark+devils-sight→seen, beyond-darkvision-range→unseen, invisible target
  vs `sees_invisible`.
- **Phase 2:** an attacker in a dark map attacking an unlit target →
  `/attack` rolls `2d20kl1` (disadvantage) **without** the manual flag; a
  torch-lit target → straight `1d20`; the manual override still forces
  disadvantage.
- **Phase 3:** a target inside a Darkness sphere → `unseen` to a normal
  attacker, `seen` to a Devil's Sight attacker.

---

## Non-goals

- **Line-of-sight / walls blocking vision** — Phase 5+ (needs a wall/occluder
  model, the heaviest geometry). Phases 0–4 assume open sight lines (range +
  illumination only), matching how the table already adjudicates cover.
- **Per-player fog-of-war secrecy** — optional in Phase 5; the server stays
  authoritative regardless.
- **Replacing GM judgment** — every computed verdict keeps a GM override (the
  existing manual flag), exactly like the rest of the engine.

This doc is surfaced through the wiki at `/wiki/doc/plan-vision-and-light`.
