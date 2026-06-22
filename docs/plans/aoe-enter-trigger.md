# Persistent-AoE enter-trigger

**Status:** 🟠 partial · **Phase 1 shipped v2.567.0** (radius shapes: sphere / self_sphere — Spirit Guardians et al.). Ships **both** RAW halves — enter-mid-move (`_trigger_persistent_aoe_on_move` in `move_token`) **and** start-of-turn (`_tick_persistent_aoe_start_of_turn` in `update_battle`'s turn-advance) — sharing one per-turn dedupe, with caster filter + save-for-half. Phases 2 (cube/cone/line) and 3 (forced-movement entry) unstarted.

> **Substrate note (v2.567.0).** An early read of this plan claimed "start-of-turn is already automated via `_tick_auras`." That was wrong: `_tick_auras` only ticks aura *buffs* (Holy Aura etc.), not `_concentration_aoes` markers. Spirit Guardians *does* create a `self_sphere` marker at cast (via `/place_aoe`), but neither the start-of-turn nor the enter damage was resolved off it — only the placement sweep. Phase 1 wired **both**. Phase 1 simplification: a plain save (the target's own modifier); ally/cast-time save-advantage layers (Aura of Protection, Danger Sense, …) are a documented follow-up — they live duplicated at the single-target + cast-time AoE save sites and want a shared extractor rather than a third copy.

Automate the **"enters the area for the first time on a turn"** half of
persistent damaging area spells — Spirit Guardians, Spike Growth, Sleet
Storm, Moonbeam, Cloud of Daggers, etc. RAW each deals its save +
damage *"when a creature enters the area for the first time on a turn or
starts its turn there."* The **start-of-turn** half is already automated
(`_tick_auras` for emanations + the persistent-AoE markers); the
**enter-mid-move** half is currently GM-narrated. This is the one
SRD mechanic that is both genuinely un-automated **and** buildable on
existing substrate without a new geometry engine (per the v2.565.5 audit
verify-pass).

---

## Why this is buildable now (substrate, verified v2.566.x)

Everything the trigger needs already exists; the gap is only *invoking*
the save+damage on a move that enters a zone.

- **Persistent AoE markers** — `_concentration_aoes[campaign_id]` is a
  list of marker dicts placed by `/place_aoe` and cleared when the
  caster's concentration ends (`_clear_caster_concentration_aoes`). Each
  marker carries `shape` (`sphere` / `self_sphere` / `cube` / `self_cube`
  / `cone` / `line`), `size_ft`, `secondary_ft`, `center` (x/y px),
  `caster_char_id`, and the damage/save payload **`dc` / `damage_expr` /
  `damage_type` / `save_ability`** — the comment at the marker site even
  flags these as *"everything the future re-trigger-on-enter follow-up
  will need."*
- **The move endpoint already has the hook point.** The token-move
  handler computes `from_x/from_y → x/y` + `distance_ft` and runs the
  Antilife-Shell barrier check (`_move_crosses_antilife_shell`) *before*
  mutating, then applies the move + broadcasts `token_move`. The
  enter-trigger runs *after* the move is applied, on the same
  from→dest pair.
- **The save+damage resolution already exists.** `/cast_spell`'s per-PC
  AoE orchestration (Phase T.5d/T.5e) fires a `roll_request` for a
  targeted PC and stashes the cast context in `_save_request_context`
  (`damage_expr` / `dc` / `save_ability` / `auto_apply_damage`); on the
  player's roll, `/roll_request/{id}/respond` applies **save-for-half**
  damage. NPC targets auto-roll + apply inline. Condition-only AoEs go
  through `_resolve_feature_save`. The enter-trigger reuses this — it's
  the *same* per-target resolution, fired from the move instead of the
  cast.
- **Radius geometry exists** — `_distance_ft_between_points` (and the
  70px = 5ft demo grid). Globe (spell-block) and Antilife (barrier)
  already do center-distance gating with it.
- **No server-side cone/line/cube point-in-shape test** — AoE shape
  sweeping at cast time is **client-side** (the placement picker sweeps
  targets and POSTs their ids). So Phase 1 scopes to **radius shapes**
  (`sphere` / `self_sphere`), which the server *can* test; cube/cone/line
  are deferred to Phase 2 (they need new geometry or a client report).

---

## Design

### The trigger (in the token-move handler, after the move applies)

For each persistent marker in `_concentration_aoes[campaign_id]` that
carries a damage payload (`damage_expr` + `dc` + `save_ability`):

1. **Shape gate (Phase 1):** only `sphere` / `self_sphere`. Radius =
   `size_ft`. (Skip cube/cone/line → Phase 2.)
2. **Entry test:** the move *enters* the zone when the **destination is
   inside** (`_distance_ft_between_points(center, dest) ≤ radius`) and it
   counts as a "first time on a turn" entry (see dedupe). A move that
   starts inside and stays inside does not re-trigger; start-of-turn is
   `_tick_auras`'s job, not this one.
3. **Affects filter:** skip the marker's own `caster_char_id` (a caster
   isn't hit by their own Spirit Guardians), and honor any
   `affects` filter the marker carries (mirrors the `_tick_auras` aura
   filter: `all` / `enemies` / `allies`).
4. **Resolve:** fire the AoE's save+damage against the moved combatant
   via the existing orchestration — PC → `roll_request` + stash
   `_save_request_context` (save-for-half on respond); NPC → auto-roll +
   `_apply_damage_to_combatant`. Broadcast the same per-target result
   event the cast path uses so chat cards render it.

### "First time on a turn" dedupe

A per-turn set `_aoe_enter_triggered[campaign_id] = {(combatant_id,
marker_id), …}`, **cleared on turn advance** (the same place
`_tick_auras` runs). A creature that moves in → out → in within one turn
triggers once; next turn it can trigger again. Markers get a stable
`id` (uuid at placement) if they don't already have one.

### Escape hatches

- `override_barrier: true` (the existing GM move-escape) also skips the
  enter-trigger, for GM adjudication.
- A campaign toggle is **not** added in Phase 1 — the trigger only fires
  when a damaging persistent AoE is actually on the map, which is rare
  and always GM-placed, so it's self-gating. (Revisit if a table wants
  it off.)

---

## Phases

1. **Phase 1 — radius-shaped damage AoEs.** Spirit Guardians, Spike
   Growth, Sleet Storm, Moonbeam (cylinder ≈ radius), etc. Enter-trigger
   in the move handler + per-turn dedupe + save-for-half via the existing
   per-target orchestration + the affects/caster filter. Harness tests
   (below).
2. **Phase 2 — cube / cone / line shapes.** Needs either server-side
   point-in-shape helpers (`_point_in_cube` / `_point_in_cone` /
   `_point_in_line`, with the shape's stored orientation) **or** a
   client-reported "entered AoE `<id>`" signal piggy-backed on the move
   POST (the client already renders the marker shapes). Decide at Phase 2
   time; radius covers the most common damage-on-enter spells first.
3. **Phase 3 (optional) — forced-movement entry.** Wire the same check
   into `_force_move` so a push/pull/Thorn-Whip that drags a creature
   into a zone also triggers it (RAW: forced movement counts as entering).

---

## Test contract (Phase 1, `tests/harness/test_aoe_enter_trigger.py`)

- **Enters → triggers:** place a radius damage-AoE marker; move a PC
  token from outside to inside → a `roll_request` fires for the PC and,
  on a failed save, save-for-half damage is applied (assert the WS
  result + HP). Model on the existing AoE-save harness tests.
- **No re-trigger same turn:** a second move while already inside (or
  out-and-back-in) within the same turn does **not** fire a second
  save; advancing the turn re-arms it.
- **NPC entry:** an NPC moved into the zone auto-rolls + takes damage
  inline (no prompt).
- **Caster immunity:** the marker's `caster_char_id` moving inside is
  **not** damaged; the `affects` filter excludes the wrong side.
- **No entry, no trigger:** a move that stays outside the radius fires
  nothing.
- **Override:** `override_barrier: true` skips the trigger.

---

## Non-goals

- **Cube / cone / line shapes** — Phase 2 (no server geometry yet).
- **Non-damage AoE riders** — Spike Growth's difficult-terrain speed
  cost, Web's restrain, Hypnotic Pattern's incapacitate-on-enter. Those
  are condition/terrain effects with their own resolution; this plan is
  the *damage*-on-enter half. (Condition-on-enter could reuse
  `_resolve_feature_save` in a follow-up.)
- **Replacing the GM-narrated fallback** for un-modeled shapes — the
  marker + GM narration stays the fallback until Phase 2.
- **A geometry/line-of-effect engine** — out of scope; that's the
  Maps-2.0-class work the other GM-narrated items (Forbiddance ward,
  scrying views) are waiting on.

This doc is surfaced through the wiki at `/wiki/doc/plan-aoe-enter-trigger`.
