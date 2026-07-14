# Thief's Reflexes — design plan

**Status:** 🟠 partial — scoped v1 (announce + marker) shipped v2.1018.0; the full initiative-engine second-turn slot is filed below.

**Feature:** Thief's Reflexes (Thief Rogue Lv 17+, PHB p.98): "You can
take two turns during the first round of any combat. You take your first
turn at your normal initiative and your second turn at your initiative
minus 10. You can't use this feature when you're surprised." Thief is the
SRD rogue subclass, so this is SRD-valid.

## Why this one is different

Every other Phase 8 subclass feature (see
[`full-feature-automation.md`](full-feature-automation.md)) is a clean
HTTP-endpoint mechanization: install a buff, roll a save, apply damage —
all server-side state the click-through harness at `tests/harness/` can
assert on. Thief's Reflexes is not. It's fundamentally an **initiative-
tracker behavior**:

- The battle's `turn_index` / `round` / initiative order is **client-
  managed** and pushed to the server via `PUT /battle`. The server hooks
  fire *reactively* on a detected turn change; it doesn't own the turn
  cursor.
- "A second turn at initiative − 10 during round 1" means inserting an
  extra **turn slot** into the tracker that the thief acts on, then
  pruning it when round 2 begins.
- A phantom combatant entry risks colliding with (a) the init-tracker's
  **orphan-cleanup** (which drops combatants whose `char_id` isn't
  tokenized — see BUGS.md B2), and (b) every system that iterates
  `state["combatants"]` (auras, start-of-turn ticks, repeated saves),
  which could double-process the thief.
- The HTTP harness asserts endpoint contracts, **not** rendered tracker
  DOM or turn advancement — so a phantom-turn implementation would land
  with weak automated verification (the same gap BUGS.md B4 flags for
  client-side initiative regressions).

## Phase 1 — scoped v1 (shipped v2.1018.0 "The Second Wind of Shadows")

`POST /use_thiefs_reflexes` mechanizes the **contract** without touching
the turn engine:

- Validates Thief Rogue Lv 17+ (`_pc_has_thief_features(sheet, 17)`).
- Requires an **active battle in round 1** (409 `not_first_round`
  otherwise), the caller **not surprised** (409 `surprised`), and the
  thief **in the initiative order** (409 `not_in_initiative`).
- Computes the second-turn initiative (the thief's `initiative − 10`) and
  broadcasts a `feature_used(source=thiefs-reflexes)` card carrying
  `base_initiative` + `second_turn_initiative` so the GM drops the extra
  turn into the tracker.

Harness: `tests/harness/test_thiefs_reflexes.py` — happy path (round 1 →
second_turn_initiative = init − 10 + broadcast), round-gate (round 2 →
409), surprised (409), not-in-initiative (409), level gate (Lv 7 → 409),
and error paths (400 missing id / 404 unknown).

## Phase 2 — full initiative-engine second turn (filed)

The mechanized version needs, in order:

1. **A phantom turn slot** distinct from the PC's real combatant — a
   tracker entry (`is_thiefs_reflexes: True`, `reflexes_of_char_id`,
   name "<Thief> (Reflexes)", initiative = base − 10) that the aura /
   save / start-of-turn iterators **skip** (so the thief isn't
   double-ticked) but the turn cursor **stops on**.
2. **Orphan-cleanup exemption** so the tracker doesn't drop it (it has
   no token / `char_id`).
3. **Round-2 pruning** — a turn-advance hook that removes the phantom
   when `round` increments past 1 (RAW: round 1 only).
4. **Surprise integration** — a surprised thief can't use it; ties into
   whatever surprise model the tracker grows.
5. **Encounter-sim (Playwright) coverage** — because the HTTP harness
   can't see the tracker, the Level-3 encounter-sim layer
   ([`encounter-sim-test-suite.md`](encounter-sim-test-suite.md)) is the
   right net for "the second turn renders + advances + prunes."

Phase 2 is gated on the encounter-sim Level-3 framework maturing (so the
behavior has a real test net) and a small tracker refactor to make the
combatant iterators phantom-aware.
