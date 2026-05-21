# Encounter-simulation test suite — plan

**Status:** v2.49.17 — Phase 1 complete (commits A v2.49.12, B v2.49.15, C v2.49.16, D v2.49.17). Phase 2 pending — task #94.
**Authors:** rolling
**Last updated:** 2026-05-21

A test suite that simulates a complete D&D encounter end-to-end and
validates every observable side effect: roll log entries, toast
messages, HP changes, init tracker state, buffs installed, slot
decrements, action-economy chips, picker placements, persistent
markers, presence dots. The aim is to catch UI / WS / contract
regressions that the existing `tests/harness/` Python suite misses
because it only drives endpoints + asserts on JSON / WS frames —
without ever rendering a pill, popping a toast, or drawing a token.

The session that triggered this plan: v2.49.4 added a 💀 skull overlay
on 0-HP tokens. The skull never fired in real play. The Python harness
suite passed all 212 tests because the broadcast was correct — but the
canvas IIFE couldn't see `window.battle` (closure-scoped). A UI-layer
test that placed Fireball + asserted "skull is visible at (x, y) on
the canvas after damage applied" would have caught it.

---

## Why this layer is needed

The existing layers cover the contract surface but not the
**experience**:

| Layer | What it tests | Coverage gap |
|---|---|---|
| `tests/harness/` (Python httpx + ws) | HTTP request/response shapes + WS broadcast payloads. 212 tests as of v2.49.6 | Doesn't render the broadcast. A regression in `_spellResultPillsHtml` that drops every pill still passes. v2.49.4 skull missed because `window.battle` lookup was wrong on the client. |
| `tests/harness_ui/` (Playwright smoke) | "Page renders, sheet loads, no console errors, attack-toast appears" | 5 tests total. Smoke-level only — doesn't validate exact damage numbers, pill contents, buff durations, the full chain. |
| Manual GM testing | Everything | Slow, ad-hoc, doesn't catch regressions consistently. The user reports a regression, then we add a test. |

The encounter-sim layer fills the gap: **drive the UI end-to-end like
a player would, assert every visible outcome at every layer**, with
deterministic dice so failures are reproducible.

---

## Design principles

1. **Demo mode is the only fixture.** All tests run against demo
   campaign 1 with its 12 PCs + Tavern Brawl encounter. The lifespan
   auto-reset means each *session* starts clean; individual tests use
   `/long_rest` + explicit cleanup hooks to avoid cross-test
   contamination.
2. **Deterministic dice.** A `DICE_SEED` env var seeds Python's
   `random.Random` instance used by the server's roll resolver.
   Without this, every test asserting "Fireball hit Bandit Alpha for
   24 fire damage" would flake whenever the dice rolled a different
   total.
3. **Multi-layer assertions.** Every test asserts at 3+ layers (HTTP +
   WS + DOM + canvas). One layer alone is the gap that motivated this
   suite.
4. **Page object pattern.** Selectors live in `pages/*.py` shared
   helpers, not scattered through test files. When the DOM changes,
   one file updates, not 40.
5. **Levels are cumulative.** Level 2 imports Level 1's helpers + adds
   new scenarios. No copy-paste between levels.
6. **Headless by default.** CI runs headless. Local dev can set
   `HARNESS_UI_HEADED=1` to watch tests run.

---

## Levels

The suite runs in **progressively deeper levels**, each adding
coverage at the cost of runtime. Default CI uses Level 1; release
branches run Level 3.

### Level 1 — Smoke (≈30s, ~12 tests)
The golden path for each demo PC. Each class fires its signature
ability **once** and the test asserts on the full chain of effects.

| PC | Action(s) | Asserts |
|---|---|---|
| Garrik (Fighter) | Strike longsword on Bandit Alpha | weapon_attack WS frame, toast "🗡️ Strike — 7 dmg", attack card with hit pill + damage pill, Bandit Alpha HP drops |
| Tavik (Cleric) | Sacred Flame on Bandit Bravo | cast_spell WS, save pill (DC 13 DEX), damage pill if failed, 1d8 radiant rolled |
| Thalindra (Wizard) | Fireball over bandits, Shield as reaction (separate test) | place_aoe WS, 3 per-target save pills, 8d6 fire damage rolled once, all 3 bandits' HP drops, persistent marker drawn |
| Lyra (Bard) | Vicious Mockery on Bandit, Bardic Inspiration on Garrik | cast_spell WS for VM, use_feature WS for BI, BI buff installed on Garrik |
| Magnus (Warlock) | Eldritch Blast (single target), Hex install | cast_spell WS, concentration buff installed on Magnus, target_combatant_id resolved |
| Pip (Rogue) | Strike with Sneak Attack via uplift | weapon_attack WS with uplift, +3d6 sneak attack pill renders |
| Mira (Druid) | Produce Flame ranged, Spike Growth AoE | cast_spell WS + place_aoe WS, persistent marker for Spike Growth |
| Sir Caelan (Paladin) | Strike + Divine Smite uplift | weapon_attack WS with smite uplift, +2d8 radiant pill, smite slot consumed |
| Krieger (Barbarian) | Rage on, then Strike | use_feature WS for rage, buff installed with auto-expire, next Strike rolls +rage damage |
| Echo (Monk) | Strike + Stunning Strike uplift | weapon_attack WS, save pill DC 13, stunned condition installed on failed save |
| Cassia (Sorcerer) | Fire Bolt + Misty Step | cast_spell WS, sorcery point not consumed for FB, slot consumed for MS |
| Vex (Ranger) | Hunter's Mark install, then Strike | use_feature + concentration buff + weapon_attack with HM uplift, +1d6 damage pill |

**Per-test assertion chain:**
1. POST endpoint → status 200, response shape matches harness
2. WS frame captured → expected `type` + key fields
3. Roll log card appears in `#roll-log-drawer` within 2s
4. At least one pill in the card matches `.result-pill.chip-{X}`
5. Toast appears in `#toast-stack` within 1s, text contains expected emoji + total
6. Target's HP bar in `#init-tracker` reflects damage
7. If applicable: buff list under target's combatant shows new buff with correct duration

**Runtime budget:** 12 tests × ~2.5s each + 5s setup = ≈35s.

### Level 2 — Encounter sim (≈3-5 min, ~6 tests)
Runs a **scripted multi-round encounter** using Tavern Brawl. Each PC
takes a real turn including movement, action, bonus action, and
sometimes reaction. The encounter ends when bandits are dead or PCs
flee. Tests assert on full-encounter invariants, not single actions.

**Scripted rounds (one test per scenario):**
1. `test_tavern_brawl_3_rounds_baseline.py` — vanilla resolution, no
   edge cases. 3 PCs + 3 NPCs. Asserts: initiative order correct,
   turn chips flip, action-economy chips reset between rounds,
   movement breadcrumb tracks, all damage applied correctly, no NPCs
   left standing.
2. `test_concentration_lifecycle.py` — Magnus casts Hex on Bandit
   Alpha, takes damage that triggers a concentration save, fails, Hex
   drops, buff removed from buff list. Re-casts Hex on Bandit Bravo,
   that bandit dies, marker auto-clears.
3. `test_aoe_persistent_marker.py` — Mira casts Spike Growth on round
   1, marker visible on canvas. Bandit moves through it (server-side
   move endpoint), v2.49.0 marker re-trigger fires (when implemented),
   damage pill appears. Mira's concentration drops on round 4, marker
   auto-clears.
4. `test_buff_install_decrement.py` — Krieger Rages turn 1, Strike
   hits with +2 rage damage. Turn 2 still raged. Turn 3 still raged.
   Turn 4: Rage expires after 10 rounds (or breaks earlier on no-hit
   condition). Buff list reflects each state.
5. `test_roll_log_replay_survives_refresh.py` — run 5 actions, refresh
   the page, assert all 5 cards still appear from localStorage replay.
   Click each card to expand, assert detail text matches what was
   rendered live.
6. `test_action_economy_strict_mode.py` — toggle strict_action_economy
   on, PC tries to take 2nd action, gated. GM override flag bypasses.
   Audit badge appears on the over-budget turn.

**Test data:** fixed `DICE_SEED=42`. Initiative order set explicitly
via test helper rather than dice (so PC X is always first).

**Runtime budget:** 6 tests × ~30s each = ≈3 min.

### Level 3 — Edge cases (≈15-30 min, ~40 tests)
Branch coverage for unusual interactions. Grouped by subsystem.

**AoE picker variants (10 tests):**
- Every shape × every position type: sphere over empty area, sphere
  over single target, sphere over crowded area, sphere over hidden
  tokens; same for cone (with rotation), line, cube, self_sphere,
  self_cube.
- Cone rotation: cast, rotate via wheel, place — assert the rotation
  angle is in the broadcast.
- Cancel mid-pick via Escape + via right-click. Assert pending stash
  cleared. Assert slot not consumed (refund).

**Save resolution matrix (12 tests):**
- Every combination of (PC vs NPC) × (passed vs failed) × (auto-damage
  on vs off) × (resistance vs not) × (concentration vs not).
- Save pill renders correctly in each: chip-success for passed,
  chip-fail for failed, half damage applied on success when spell has
  "half on save".

**Action-economy edge cases (8 tests):**
- Over-budget retry, strict mode block, GM override.
- Action Surge: Garrik's chip refund after using.
- Cunning Action: Pip's bonus-action Dash/Disengage/Hide.
- Reaction-only chips (Shield, Hellish Rebuke).

**Concentration cleanup (6 tests):**
- Cast new conc spell while concentrating → old marker drops.
- Failed con save → marker drops.
- PC at 0 HP → concentration drops + AoE marker drops.
- PC dies (3 death save failures) → marker drops.
- Buff with paired concentration (Hex + Hexblade's Curse) → both drop
  together.

**Death saves (4 tests):**
- Enter dying, roll 3 successes via /death_save endpoint, stabilize.
- Enter dying, roll 3 failures, die. Token gets 💀 (v2.49.4).
- Massive damage instakill (damage ≥ HP max).
- Healing word on a dying PC restores them above 0 + clears death
  save tracker.

**Multi-user (4 tests):**
- 2 players + 1 GM, each in own browser context. Each takes actions
  in turn. Assert all 3 clients see the same state after each action
  (HP bars match, roll log mirrored, presence dots visible).
- One player goes offline → presence dot dims. Reconnects → dot
  brightens.

**Runtime budget:** ~30 min worst case, sharded 4-way for CI to fit
in ≈8 min wall time.

### Level 4 — Fuzz (manual, not CI)
Random action sequences over hundreds of turns. Used by maintainers
to find rare interaction bugs (e.g. "what happens if rage drops
mid-cast of a concentration spell?"). Not CI; run on release branch
manually before a MAJOR bump.

---

## Architecture

### Directory layout

```
tests/encounter_sim/
├── __init__.py
├── conftest.py            # shared fixtures (extends harness_ui conftest)
├── pages/
│   ├── __init__.py
│   ├── tabletop.py        # TabletopPage: drag, click token, open sheet, read init tracker
│   ├── sheet.py           # SheetPage: click attack/spell row, click .sp-cast, click .atk-roll
│   ├── roll_log.py        # RollLogPage: cards list, find by data-cast-id, expand pill
│   ├── toast.py           # ToastWatcher: catch every toast for the test duration
│   └── canvas.py          # CanvasReader: pixel-sample for skull / marker / breadcrumb checks
├── helpers/
│   ├── __init__.py
│   ├── dice.py            # set/clear DICE_SEED at test start
│   ├── ws.py              # subscribe to WS for the campaign + filter frames
│   ├── reset.py           # demo reset hook + long-rest helper
│   └── assert_pill.py     # assert_pill(card, class_, header, detail)
├── level_1_smoke/
│   ├── test_garrik_strike.py
│   ├── test_tavik_sacred_flame.py
│   ├── test_thalindra_fireball.py
│   └── ... one per PC
├── level_2_encounter/
│   ├── test_tavern_brawl_baseline.py
│   ├── test_concentration_lifecycle.py
│   └── ...
└── level_3_edge_cases/
    ├── aoe/
    ├── saves/
    ├── action_economy/
    ├── concentration/
    ├── death_saves/
    └── multiuser/
```

### Test runner

Playwright (already wired in `tests/harness_ui/`). Each level is its
own subdirectory. CI selects by directory:

```yaml
- name: Level 1 smoke
  run: python3 -m pytest tests/encounter_sim/level_1_smoke -q
- name: Level 2 encounter sim
  if: github.ref == 'refs/heads/main'
  run: python3 -m pytest tests/encounter_sim/level_2_encounter -q
- name: Level 3 edge cases
  if: contains(github.event.pull_request.labels.*.name, 'run-level-3')
  run: python3 -m pytest tests/encounter_sim/level_3_edge_cases -q
```

### Demo mode dependency

All levels run against demo mode (4 env vars in
`docs/plans/demo-mode.md`). The lifespan auto-reset means each test
*session* starts from a clean seed; per-test isolation uses an
explicit `reset_demo_state` fixture.

**Reset strategy:**
- Per-test: call `helpers.reset.long_rest_everyone()` to restore HP,
  slots, charges, expire all buffs. Cheap (~200ms).
- Per-file: call `helpers.reset.clear_battle()` to wipe init + AoE
  markers + pending casts. Used when a test loads a fresh encounter.
- Per-session: rely on lifespan auto-reset.

### Deterministic dice

**Server side:** add `DICE_SEED` env var. When set, the dice resolver
(`app/services/dice.py` or wherever `random.randint` calls live)
seeds a per-process `random.Random(int(DICE_SEED))` instance and uses
it instead of the module-level `random`. Required because module-level
`random` would leak between requests.

**Client side:** none — the only client-side dice is the optional
local dice animation, which doesn't affect game state.

**Test usage:**
```python
def test_thalindra_fireball(gm_page, set_dice_seed):
    set_dice_seed(42)
    # Now every dice roll on the server is deterministic
    # 8d6 with seed 42 rolls a known total — assert on that exact value
```

**Caveat:** when test order matters (sequential dice draws within
a test), tests must call `set_dice_seed` at the start of each
discrete action.

### Output validation strata

Each test asserts at multiple layers. Tests pick which layers apply
to their scenario but should always include at least 3.

1. **HTTP response** (existing harness layer — `httpx` post + assert
   on status + body shape).
2. **WS broadcast** (subscribe + capture frames into a queue, assert
   first matching frame's `type` + key fields).
3. **Toast** (`ToastWatcher` mounts a `page.locator(".toast")` listener
   on `mutationobserver` events, captures every toast text + class
   for the test duration).
4. **Roll log card** (`RollLogPage.find_card_by_cast_id(cast_id)`
   returns a Playwright Locator; assert pill text + class +
   breakdown detail when expanded via click).
5. **Init tracker** (`TabletopPage.get_combatant_row(name)` returns
   the row; assert HP bar reads expected value).
6. **Mini sheet** (open via init tracker → sheet button; assert HP +
   buff list).
7. **Full sheet** (drawer iframe; assert `#hp-current-input` value
   matches).
8. **Canvas** (pixel sample at known coordinates: e.g. skull pixel
   at center of dead bandit token). Heavy — only used for purely-
   canvas assertions like skull / marker presence.

---

## Open questions

| Question | Proposed answer |
|---|---|
| Visual regression tests (screenshot diffs)? | **No** for V1. High maintenance, high flake. Reconsider if we get repeated theme-break regressions. |
| Non-deterministic init order? | Test helper sets initiative explicitly via existing `/initiative/set` endpoint after rolling, OR uses a fixed `DICE_SEED` that produces known init order for the demo PCs. |
| Multi-user Level 3 — multi-context vs multi-process? | **Multi-context in one test.** Playwright supports N browser contexts in one test; cheaper than multi-process and shares the WS subscription helper. |
| What happens if demo state drifts between tests in the same file? | Each test calls `reset_demo_state` fixture (autouse=True on the level_2_encounter package, opt-in elsewhere). |
| Where do server-side dice get seeded? | Add `_get_dice_random()` in `app/services/dice.py` (create file) that returns either a seeded instance (DICE_SEED set) or the module-level random. Call sites: every existing `random.randint` in roll routes. Audit during Phase 1. |
| What if a test wants to assert a roll value but doesn't care which? | `assert_pill(card, chip_class="chip-damage")` with no `detail` — just asserts the pill exists with the right class. |
| Does the suite need to test with strict_action_economy on AND off? | Level 1 = off (default). Level 3 = both, via a per-test fixture that flips the campaign setting. |

---

## Phasing

Each phase ships as one commit with version bump + CHANGELOG entry,
following the per-commit rule. Tests added must keep the harness
passing.

### Phase 1 — Level 1 PoC ✅ COMPLETE (v2.49.12 → v2.49.17)
**Goal:** prove the architecture works. Pick Garrik, Thalindra,
Tavik (the broadest coverage: weapon attack, AoE save spell, single-
target save spell).

Tasks (all complete):
1. ✅ Add seedable dice RNG to `app/dice.py` (NOT `app/services/dice.py`
   — extended the existing module instead) + audit all `random.randint`
   call sites to use it. Shipped v2.49.12.
2. ✅ Add `DICE_SEED` env var (read at module level, optional).
   Shipped v2.49.12.
3. ✅ Create `tests/encounter_sim/conftest.py`, `pages/`, `helpers/`
   directory structure. Shipped v2.49.15.
4. ✅ Implement `TabletopPage`, `SheetPage`, `RollLogPage`,
   `ToastWatcher`, `CanvasReader` skeletons + concrete helpers
   (`set_dice_seed`, `long_rest`, `assert_pill`, `WSCollector`).
   Shipped v2.49.15.
5. ✅ Write `test_garrik_strike.py`, `test_tavik_sacred_flame.py`,
   `test_thalindra_fireball.py` to spec. Shipped v2.49.16 and
   v2.49.17.
6. ✅ Wire into CI as a new step `encounter-sim`
   (`continue-on-error: true` initially while we shake out flake).
   Shipped v2.49.17.

**Exit criteria:** ✅ 3 tests pass locally on 5 consecutive runs at
~6.2 s/run with no flake. CI corroboration pending (`continue-on-
error: true`); flip to `false` once 5 green CI runs land.

**Findings worth carrying forward** (from commits C / D):

- **GM clients ignore `battle_update` broadcasts** without
  `force_gm_sync` (tabletop.html:5543, v2.5.5 echo-loop guard). Any
  UI assertion on init-tracker DOM HP updates from server-pushed
  state MUST be driven by a non-GM. Phase 1 worked around this by
  asserting against the response body's `auto_save_damage_applied`
  / `target_hp_after` (the source of truth that drives card text).
  A player-driver variant of each PoC test is filed for Phase 2.
- **`/attack` and `/cast_spell` don't broadcast `force_gm_sync`**.
  Mirror the `/place_aoe` pattern (line ~7986 of tabletop_routes.py)
  to fix; separate from the suite but surfaced by it.
- **Sync Playwright + `time.sleep()`** blocks event-loop processing
  so WS listeners can't fire. `WSCollector.wait_for` uses
  `page.wait_for_timeout` between polls.
- **Sync Playwright + pytest-asyncio cross-suite** can't share a
  process (`Cannot run the event loop while another loop is
  running`). CI runs `harness` / `harness-ui` / `encounter-sim` as
  separate jobs; locally, run each suite independently.
- **`set_dice_seed` MUST clean up to `None` on teardown**, otherwise
  the shared process-global RNG stays deterministic and the next
  test (encounter-sim, harness, or harness-ui) flakes against
  expected randomness. Handled in the conftest fixture.
- **GM page localStorage is the source of truth** for init tracker
  state. The `seed_battle_into_page(context, combatants)` helper
  pre-populates localStorage via `add_init_script` so the IIFE picks
  up the seeded state on load — pairs with `seed_battle(combatants)`
  which PUTs the same state to the server for endpoint targeting.

### Phase 2 — Level 1 full coverage (target v2.51.0)
Expand to all 12 demo PCs. Mostly mechanical — copy the Phase 1
patterns. Catches: any PC who can't be driven by the page-object
helpers gets the helper extended.

**Exit criteria:** 12 tests pass; runtime ≤45s.

### Phase 3 — Level 2 encounter sim (target v2.52.0)
Implement the 6 multi-round scenarios. This is where the
encounter-level invariants get exercised (initiative, buff lifecycle,
concentration, AoE persistence).

**Prerequisite work that may surface:**
- Phase B re-trigger on AoE enter (filed v2.49.0) — needed for the
  Spike Growth marker test.
- Demo reset hook may need a server-side endpoint to wipe
  battle state without a full lifespan reset, to keep test runtime
  low.

**Exit criteria:** 6 tests pass; runtime ≤4 min.

### Phase 4 — Level 3 edge cases (target v2.53.0)
Implement the 40-test edge case grid. Sharded 4-way in CI.

**Exit criteria:** 40 tests pass; sharded runtime ≤10 min per shard.

### Phase 5 — CI integration + docs (target v2.54.0)
- Default CI runs Level 1 on every PR.
- Level 2 runs on push to `main`.
- Level 3 runs on `run-level-3` PR label or release branches.
- Update `docs/test-harness-coverage.md` to include the encounter-sim
  layer.
- Add a `CONTRIBUTING.md` paragraph: "when adding a new spell /
  feature, add a Level 1 smoke test in the same commit."
- Update CLAUDE.md's "every new endpoint commit lands a harness
  test" rule to clarify endpoint-shape vs experience tests.

**Exit criteria:** plan complete, suite stable, contributor doc lands.

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Flake — UI tests are notoriously flaky | Multi-layer assertions short-circuit on WS frame before DOM, so timing waits are bounded. Use Playwright's `expect(...).to_be_visible()` with explicit timeouts, never `sleep`. |
| Runtime balloons past CI budget | Sharding in Level 3. Level 1 budget is hard-capped at 45s. |
| Server-side dice seeding leaks between tests | `helpers.dice.set_dice_seed` always re-seeds at the start of the test, never mid-test. Tests that need mid-test determinism set the seed before each action. |
| Demo reset is slow | Per-test long_rest is ~200ms; per-file battle clear is ~500ms; per-session lifespan is ~3s. Profile in Phase 1, optimize if needed. |
| Page-object selectors drift | The pages/ helpers are the single source of selectors. When the DOM changes, the test diff shows up in one file. Periodic audit during Phase 5. |
| `DICE_SEED` env var leaks into production | Only read inside `_get_dice_random()`, defaults to unseeded `random` when unset. Add a runtime check that warns if set + not in test mode. |

---

## Related

- `docs/plans/test-harness.md` — the existing endpoint-contract harness.
- `tests/harness/` — current Python test suite (212 tests as of v2.49.6).
- `tests/harness_ui/` — current Playwright smoke harness (5 tests, the
  Phase 4 work from `test-harness.md`).
- `docs/plans/demo-mode.md` — demo mode prerequisites for the suite.
- `docs/test-harness-coverage.md` — coverage catalog (will gain a new
  section in Phase 5).
- Task #93 — Phase 1 PoC, tracked in the project task list.
