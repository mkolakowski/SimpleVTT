# Encounter-simulation test suite — plan

**Status:** filed v2.49.1 · not yet started

A test suite that simulates a complete D&D encounter end-to-end and
validates every observable side effect: roll log entries, toast
messages, HP changes, init tracker state, buffs installed, slot
decrements, action-economy chips, picker placements. The aim is to
catch UI / WS / contract regressions that the existing
`tests/harness/` suite misses because it only drives endpoints +
asserts on JSON / WS frames.

## Why this layer is needed

The existing test layers cover the contract surface but not the
**experience**:

| Layer | What it tests | Coverage gap |
|---|---|---|
| `tests/harness/` (Python) | HTTP request/response shapes + WS broadcast payloads | Doesn't verify the client renders the broadcast correctly. A regression in `_spellResultPillsHtml` that drops every pill would still pass these tests. |
| Playwright smoke (`tests/playwright/`) | "Can I open the page, see a sheet, fire a spell, get a roll" | Smoke-level only. Doesn't validate damage numbers, toast contents, buff durations, or the full chain of effects from one action. |
| Manual GM testing | Everything | Slow, ad-hoc, doesn't catch regressions consistently. |

The encounter-sim layer fills the gap: drive the UI end-to-end like
a player would, assert every visible outcome.

## Levels

The suite runs in **progressively deeper levels**, each adding
coverage at the cost of runtime. Default CI uses Level 1; release
branches run Level 3.

### Level 1 — Smoke (≈30s)
The golden path for the 12 demo PCs. Each class fires their
signature ability once:
- Garrik (Fighter): Strike with longsword, Second Wind, Action Surge
- Tavik (Cleric): Sacred Flame, Cure Wounds, Spirit Guardians
- Thalindra (Wizard): Fire Bolt, Magic Missile, Fireball, Shield
- Lyra (Bard): Vicious Mockery, Bardic Inspiration, Cutting Words, Shatter
- Magnus (Warlock): Eldritch Blast, Hex, Hellish Rebuke, Burning Hands
- Pip (Rogue): Strike + Sneak Attack, Cunning Action
- Mira (Druid): Produce Flame, Wild Shape, Spike Growth
- Sir Caelan (Paladin): Strike, Divine Smite, Lay on Hands, Channel Divinity
- Krieger (Barbarian): Rage, Strike with rage
- Echo (Monk): Stunning Strike, Patient Defense
- Cassia (Sorcerer): Fire Bolt, Misty Step, Counterspell
- Vex (Ranger): Hunter's Mark, Strike (multi-attack)

For each:
- Assert the cast/use endpoint returns 200
- Assert the WS broadcast fires with the expected shape
- Assert the roll log card renders (DOM check)
- Assert at least one pill renders with the expected class + label
- Assert any HP change is reflected on the targeted token / character

### Level 2 — Encounter sim (≈3-5 min)
Runs a scripted multi-round encounter using the demo's Tavern
Brawl. Each PC takes a real turn including movement, action, bonus
action, possibly reaction. Asserts:
- Initiative tracker advances correctly
- Each turn's action-economy chips flip (action used, bonus used)
- Movement breadcrumb tracks correctly
- Buffs install + decrement per round
- Concentration breaks on damage (run a save against DC = damage/2)
- Persistent AoE markers (v2.49.0) appear + persist + clear
- All cast cards / pills / toasts match expected
- Roll log replay survives a page refresh mid-encounter

Test data: a fixed RNG seed so dice rolls are deterministic.

### Level 3 — Edge cases (≈15-30 min)
Branch coverage for unusual interactions:
- AoE picker variants: every shape (sphere / cone / line / cube / self_sphere / self_cube) placed at every position type (over empty area, over single target, over crowded area, over hidden tokens)
- Save outcomes: every combination of (PC vs NPC) × (passed vs failed) × (auto-damage on vs off) × (resistance vs not) × (concentration vs not)
- Action-economy edge cases: over-budget retry, strict mode, GM override
- Multi-class interactions: a Lv 5 Paladin/Cleric multi-class using both spell lists
- Concentration cleanup: cast new conc spell → old marker drops; failed con save → marker drops; PC dies → marker drops
- Death saves: enter dying, roll 3 successes, stabilize; enter dying, roll 3 failures, die; massive damage instakill
- Replay: every entry in the roll log survives `Cmd+R`
- Multi-user: 2 players + 1 GM, each takes actions, every client sees the same state

### Level 4 — Fuzz (manual, not CI)
Random action sequences over hundreds of turns. Used by maintainers
to find rare interaction bugs (e.g. "what happens if rage drops
mid-cast of a concentration spell?").

## Architecture

### Test runner
Playwright (already wired in `tests/playwright/`). Each level is a
separate Playwright test file with a `playwright.config.ts` profile
selecting the level via env var (`SIMPLEVTT_TEST_LEVEL=1`).

### Demo mode dependency
All levels run against demo mode (4 env vars in
`docs/plans/demo-mode.md`). The lifespan auto-reset means each test
starts from a clean seed. The demo includes the right PCs, monster
templates, the Tavern Brawl encounter, and pre-seeded sample rolls.

### Deterministic dice
Server-side: a `DICE_SEED` env var (or fixture) seeds Python's
`random` module so dice rolls reproduce. Tests would set this seed
at the start of each test and assert on exact rolled values.

### Output validation
Each test asserts at multiple layers:
1. **HTTP response** (existing harness layer)
2. **WS broadcast** (subscribe + capture frames)
3. **Toast message** (Playwright finds the toast container, reads text, asserts on emoji + total + breakdown)
4. **Roll log card** (Playwright queries the cast card by `data-cast-id`, asserts pill text + class + breakdown detail when expanded)
5. **Init tracker** (HP bar reads expected value)
6. **Token sheet** (open mini-sheet, assert HP fields)
7. **Map state** (concentration markers, persistent overlays)

## Open questions

- Do we want visual regression tests (screenshot diffs)? Useful for catching theme breaks but high maintenance.
- How do we handle non-deterministic init order when multiple PCs roll the same initiative? Tie-break by character_id alphabetical, or set explicit initiative in the test fixture.
- For multi-user Level 3 tests: do we spin up multiple Playwright browser contexts in one test, or run multiple processes?

## Phasing

1. **Phase 1**: Level 1 smoke runner + 3 PCs (Garrik, Thalindra, Tavik) as proof of concept.
2. **Phase 2**: Expand to all 12 demo PCs.
3. **Phase 3**: Level 2 encounter sim. Pick one encounter (Tavern Brawl), script 3 rounds.
4. **Phase 4**: Level 3 edge cases. Group by subsystem (AoE, save resolution, action economy, etc.).
5. **Phase 5**: CI integration. Default to Level 1; release branches run Level 3.

## Related

- `docs/plans/test-harness.md` — the existing endpoint-contract harness.
- `tests/harness/` — current Python test suite (212 tests as of v2.49.0).
- `tests/playwright/` — current smoke harness (limited coverage).
- `docs/plans/demo-mode.md` — demo mode prerequisites for the suite.
