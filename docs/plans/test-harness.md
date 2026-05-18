# Autonomous click-through test harness — plan

A regression-test framework that exercises every clickable surface on
SimpleVTT character sheets + the tabletop mini-sheets, asserts on the
resulting WebSocket broadcasts + HTTP responses, and surfaces failures
as a structured report. The motivating bug class: backend state +
broadcast-shape regressions that were only caught by manual play (e.g.
the v2.7.3 weapon-attack-toast miss, the v2.4.12 spell-level field
typo, the v2.6.0 action-economy gating that needed end-to-end coverage).

This plan is the **starting design**. Phases are sequenced for
incremental usefulness — Phase 1 ships as soon as it covers the
existing endpoints; Phases 2-3 extend coverage and CI integration;
Phase 4 (Playwright) lands later if UI-layer bugs warrant it.

---

## Goal

Run a single command (e.g. `make test-harness`) and get a pass/fail
report covering every interactive endpoint on the d&d5e sheet and the
tabletop mini-sheet. Each test fires a real HTTP request against a
running stack, listens for the WebSocket broadcast, and asserts both
the HTTP response shape AND the resulting WS message type + payload.
Tests run in seconds, fit in CI, and the per-button mapping doubles as
living documentation of "what each endpoint should produce".

**Non-goals** (filed as Phase 4 follow-up):

- Visual regression testing (canvas breadcrumb appearance, modal
  layout, color tokens).
- True end-user click simulation through a real browser. The
  HTTP+WS layer skips the JS click-handler path entirely — it talks
  directly to the endpoints the handlers eventually POST to. That's
  a deliberate scope cut: ~90% of recent regressions live in the
  endpoint or the WS protocol, not the click handler glue.
- Multi-user concurrency tests (e.g. two players clicking simultaneously).
  Filed as Phase 5 stretch goal.

---

## Why now

Five recent bugs that the harness would have caught at HEAD-of-branch
time, not at user-report time:

1. **v2.7.3** — `weapon_attack` WS broadcasts didn't fire a roll toast.
   The `roll_toast.js` WS listener filtered for `type === 'roll'`
   only; `weapon_attack` slipped through. A harness assertion of "click
   strike → expect toast within 2 s on the WS bus" would have caught
   this the moment v2.6.x introduced the `weapon_attack` payload.
2. **v2.4.12** — spell sheet bucketed every spell under cantrips
   because the seed used `level_int: N` but the renderer read `s.level`.
   A harness check "Magic Missile is level 1 in the spell-cast broadcast"
   would have failed loudly.
3. **v2.6.1** — Phase 4 over-budget gate's `override` flag flow was
   spread across 4 endpoints. A harness assertion of "double-fire
   attack → second one returns 409 over_budget without override" gives
   each endpoint a contract test.
4. **v2.10.0** — Lay on Hands pool decrement vs. actual-healed
   semantics (pool ticks by spend amount, not by healed amount). A
   single test "drink-cap target → pool decremented by spend amount,
   healed = 0" pins the RAW intent in code.
5. **v2.5.3 → v2.6.0** — Cunning Action, Channel Divinity, and other
   feature endpoints were rolled out across 3 commits. A "fire every
   feature_used endpoint → expect feature_used broadcast" sweep
   catches the contract break the moment a new endpoint forgets to
   broadcast or to mark the economy slot.

The pattern is the same: a small, declarative "click this button →
expect this broadcast" map captures the API contract per surface, and
any regression that breaks the contract fails the harness immediately.

---

## Architecture (Phase 1 — HTTP + WS)

### Tech choices

- **pytest** as the runner. Already an industry standard for Python
  HTTP+WS test suites; integrates cleanly with `pytest-asyncio` for
  the WS subscription side. New dev dependency.
- **httpx** for HTTP. Already in `requirements.txt` (v0.27.2). Async-
  capable, modern API, supports session cookie persistence out of the
  box.
- **websockets** library for WS. Already in `requirements.txt` (v13.1).
  Async, supports `recv` with a timeout. Used the same way the FastAPI
  websocket endpoint serves it.
- **Demo stack as the test bed.** The existing demo docker-compose
  (`demo-gm@example.com` / `demo-alice@example.com` / `demo-bob@example.com`,
  campaign 1, the seeded encounter) is a known-good fixture. Tests
  log in as one of these accounts and exercise the demo PCs.

### Connection flow

1. **Login.** POST to `/auth/login` with form credentials → save the
   `session` cookie. The session is the only auth surface (no
   API tokens today); cookies persist across HTTP requests AND
   the subsequent WS upgrade.
2. **Open WS.** Connect to `wss://localhost:8013/ws/campaign/1` with
   the session cookie. The hub fires an initial `battle_update` (if
   init is active) + a `presence_update` (v2.9.1).
3. **Per test.** Fire the HTTP POST, then `await ws.recv()` with a
   timeout until the expected broadcast type arrives or the timeout
   expires. Multiple `recv` calls may be needed — endpoints often
   fire 2-3 messages in sequence (e.g. `feature_used` +
   `heal_applied` + `resource_update` for /use_lay_on_hands).

### Test contract shape

Each test declares:

```python
@pytest.mark.parametrize("scenario", LAY_ON_HANDS_SCENARIOS)
async def test_lay_on_hands(scenario, client, ws):
    # Setup: ensure paladin has the resource + slot is fresh
    await reset_paladin_state(client, scenario.char_id)

    # Act: fire the endpoint
    resp = await client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_lay_on_hands",
        json=scenario.body,
    )
    assert resp.status_code == scenario.expected_status

    # Assert: WS broadcasts in expected order
    msgs = await collect_ws_messages(ws, timeout=2.0)
    assert {m["type"] for m in msgs} >= scenario.expected_ws_types
    # Per-broadcast shape checks
    for m in msgs:
        if m["type"] == "heal_applied":
            assert m["data"]["rolled"] == scenario.expected_healed
```

Scenarios are dataclass-shaped:

```python
@dataclass
class Scenario:
    name: str
    body: dict
    expected_status: int                # 200 / 409 / 404
    expected_ws_types: set[str]         # {"feature_used", "heal_applied"}
    expected_healed: int | None = None  # per-test extra assertions
```

### Fixture characters

Phase 1 covers what the demo already ships:

| Demo PC | Class | Click-through coverage |
|---|---|---|
| Pip Quickfingers | Rogue 5 | `/attack` (Shortsword, Dagger), `/use_feature` (Cunning Action × Dash/Disengage/Hide), `/use_item` (Potion of Healing — when potions-as-bonus is on AND off) |
| Thalindra Moonwhisper | Wizard 5 | `/cast_spell` (Magic Missile L1, Fireball L3, Shield reaction, Misty Step bonus), `/attack` (Quarterstaff) |
| Brother Tavik | Cleric 5 / Life Domain | `/use_resource` decrement, `/use_feature` (Channel Divinity × Turn Undead / Preserve Life via the v2.9.0 picker → POST /use_feature endpoint), `/use_item` (Potion of Healing), `/cast_spell` (Healing Word bonus, Spirit Guardians action), `/attack` (Warhammer) |

For surfaces the demo doesn't cover (Lay on Hands, Bardic Inspiration,
Wild Shape, Ki, Action Surge, Second Wind, etc.), Phase 1 ships a
**separate test fixture seeder** that creates additional characters in
a sidecar test campaign (campaign 2 in the test DB). The seeder is
its own module under `tests/fixtures/`, runs once per test session,
and the characters are wiped + re-seeded between runs.

Test-fixture PCs to author (Phase 1):

- **Sir Caelan (Paladin 5, Oath of Devotion)** — for Lay on Hands,
  Channel Divinity (Paladin variant), Divine Smite (Phase 3 below).
- **Lyra (Bard 5, College of Lore)** — for Bardic Inspiration,
  Song of Rest, Cutting Words (Phase 3).
- **Bram (Fighter 5, Champion)** — for Second Wind, Action Surge,
  Fighting Style.
- **Sister Mirabel (Druid 5, Circle of the Moon)** — for Wild Shape
  via the BeastPicker.
- **Kael (Monk 5, Way of the Open Hand)** — for Ki + Flurry / Patient
  Defense / Step of the Wind.

Each fixture character lives in `tests/fixtures/<class>.py` mirroring
the demo seed shape. Total fixture LOC ≈ ~600 across 5 PCs.

### Action-economy state management

Many endpoints check `_is_slot_used(...)` against the realtime hub's
battle state. Tests need predictable starting state. Three strategies:

1. **Fresh-init-per-test** — before each test, POST to a hypothetical
   `/test/reset_battle` admin endpoint that wipes the hub's battle
   state for the test campaign. New, sidecar-only endpoint guarded by
   `ENV=test`.
2. **Override every call** — pass `override: true` on every test
   POST. Bypasses the Phase 4 gate. Works for "happy path" tests but
   prevents testing the gate itself.
3. **Explicit setup per scenario** — each test declares `setup:
   "clear_action" | "spent_action" | None` and the runner calls a
   helper to put the chip in the right state.

Phase 1 ships strategy 3 (explicit setup) — gives the most expressive
testing surface, including coverage of the over-budget gate itself.

### Strict mode coverage

The v2.8.0 `Campaign.strict_action_economy` flag is its own dimension.
Phase 1 parameterizes the relevant tests with `[strict_off, strict_on]`
and asserts the appropriate response shape per:

| State | strict_off | strict_on |
|---|---|---|
| slot free | 200 (proceeds) | 200 (proceeds) |
| slot used, no override | 409 over_budget | 409 over_budget + `strict: true` |
| slot used, override:true | 200 (proceeds) | 409 over_budget + `strict: true` (override ignored) |
| GM clicks slot used | 200 (proceeds) | 200 (proceeds — GM bypass) |

### Reporting

Pytest's default text output is fine for local dev. CI gets:

- **JUnit XML** via `--junitxml=reports/harness.xml` for GitHub
  Actions test-result annotations.
- **HTML report** via `pytest-html` for human-readable per-test
  detail. Failing tests show the request body, response body, and
  the full WS message stream collected during the test.
- **Failure log** persisted under `reports/<timestamp>/` with the
  full pytest output + a per-test JSON dump of `{request, response,
  ws_messages}` so failures can be triaged after the fact.

---

## Phases

### Phase 1 — HTTP+WS smoke test (MVP)

Coverage targets all currently-shipped endpoints that fire a WS
broadcast on success. One test per (endpoint, expected_status_code)
pair, plus a parametrized over-budget gate test per affected endpoint.

**Endpoint coverage matrix:**

| Endpoint | Tests | WS broadcasts asserted |
|---|---|---|
| `POST /attack` | happy + over_budget gate | `weapon_attack`, `economy_update` |
| `POST /cast_spell` | happy + over_budget + 409 no_slot | `spell_cast`, `spell_slot_update`, `economy_update` |
| `POST /use_feature` | one per feature key in `_FEATURE_ECONOMY` (~14 entries) + over_budget | `feature_used`, `economy_update` |
| `POST /use_item` | happy + house-rule on/off (potions_as_bonus_action) + 409 out_of_stock | `feature_used`, `heal_applied`, `economy_update` |
| `POST /use_lay_on_hands` | happy + 409 insufficient_pool + over_budget gate + target-cap clamp | `feature_used`, `heal_applied`, `resource_update`, `economy_update` |
| `POST /use_bardic_inspiration` | happy + 409 out_of_uses + over_budget + die-scaling (Lv 4/5/10/15) | `feature_used`, `resource_update`, `economy_update` |
| `POST /character/{cid}/resource` | happy + announce flag | `resource_update`, optional `feature_used` |
| `POST /token/{tid}/move` | happy + distance-calc + strict-mode movement overrun | `token_move`, optional `feature_used` (audit) |
| `POST /roll` | happy + visibility filtering | `roll` (with visibility checks) |

**Exit criteria for Phase 1:**

- One pytest invocation runs all tests in <30 s against a live demo
  stack.
- Every endpoint above has at least the happy-path + one error-path
  test.
- Strict-mode and over-budget paths covered for the four
  action-bearing endpoints.
- README updated with a `Testing` section + a `make test-harness`
  target.
- Tests run in CI on every PR (Phase 2 below) — but CI integration
  can ship as a separate commit.

Estimated LOC: ~1500-2000 (test code) + ~600 (fixture seeders) + ~100
(harness helpers) ≈ ~2300 total.

### Phase 2 — CI integration

GitHub Actions workflow `.github/workflows/test-harness.yml`:

1. Checkout repo
2. `docker compose -f docker-compose.test.yml up -d --build` (new
   compose file that spins up the app + db + a sidecar test campaign
   seeder + the test runner)
3. Wait for `/healthz` to return 200
4. Run `pytest tests/harness/ --junitxml=reports/harness.xml --html=reports/harness.html`
5. Upload `reports/` as artifacts on failure
6. Fail the workflow if any test failed

Triggers: on every PR + on every push to main. Smoke-test mode (subset
of fast tests, <10 s) runs on every PR; full sweep runs on main pushes.

### Phase 3 — Contract tests for new features

Every new feature commit that adds an endpoint + broadcast pair is
expected to land with at least one harness test. The CLAUDE.md
contributor guide grows a line about this.

Phase 3 also widens coverage to per-feature flows that span multiple
endpoints, e.g.:

- **Channel Divinity full flow** — start session, advance init,
  expand Tavik's init card, click ⚡ Use, pick "Preserve Life", assert
  feature_used + economy_update + counter decrement.
- **Lay on Hands full flow** — pick amount, pick target, assert
  pool decrement, target HP increment.
- **Bardic Inspiration full flow** — pick target (excludes self),
  assert die size scales with level, counter decrement.

Each "full flow" test exercises 2-4 endpoints in sequence and
validates the end-to-end state transition.

### Phase 4 — Playwright UI layer (follow-up)

Lands separately once Phase 1-3 are stable AND a UI-layer regression
slips through (the v2.7.3 toast miss being the canonical case). Tests
drive the actual browser:

- Click `.atk-strike` on Pip's sheet (running headless Chromium).
- Wait for the roll-toast div to appear in the DOM.
- Assert the toast text matches the attack name.
- Take a screenshot on failure for the failure log.

Test count would mirror the Phase 1 endpoint sweep but at ~10× the
runtime (browser overhead). Run only on main pushes, not per-PR.

Dependencies: `playwright` Python package + the browser binary
(~250 MB), best installed in a separate docker image
(`docker-compose.playwright.yml`) so the regular dev compose stays
slim.

### Phase 5 — Multi-user concurrency (stretch)

Two test clients, both connected to the same campaign WS. Test that
e.g. Alice and Bob clicking attack simultaneously doesn't break the
hub's battle state. Filed as stretch — current evidence suggests
single-user races are the dominant bug surface, but multi-user shows
up at scale.

---

## Invocation

Phase 1 ships a `Makefile` target:

```bash
make test-harness         # runs against a live demo stack at localhost:8013
make test-harness-fresh   # docker compose up -d, wait for healthz, run tests, leave stack up
```

Plus a pytest invocation:

```bash
pytest tests/harness/                                # all tests
pytest tests/harness/ -k "lay_on_hands"              # one feature
pytest tests/harness/ --junitxml=reports/h.xml       # CI report
```

Environment variables:

| Var | Default | Purpose |
|---|---|---|
| `HARNESS_BASE_URL` | `http://localhost:8013` | App URL |
| `HARNESS_TEST_USER` | `demo-gm@example.com` | Default test login |
| `HARNESS_TEST_PASS` | `demopass` | Default test pass |
| `HARNESS_TEST_CAMPAIGN` | `1` | Default campaign ID for demo PCs |
| `HARNESS_FIXTURE_CAMPAIGN` | `2` | Where the test-fixture PCs (Paladin / Bard / Druid / Fighter / Monk) live |
| `HARNESS_LOG_DIR` | `reports/` | Where JSON dumps + HTML reports land |
| `HARNESS_WS_TIMEOUT` | `2.0` | Per-test WS receive timeout in seconds |

---

## Open questions / risks

- **WS race conditions.** A POST returns 200; the WS broadcast may
  arrive on the WS connection *before* the HTTP response completes
  (the broadcast fires inside the route handler). The harness must
  buffer WS messages from the moment the test starts, not from after
  the HTTP response. Pattern: spawn a `recv_loop` task that
  accumulates messages into a per-test queue, then drain on assert.
- **Race between fixture seeding and the demo's 60-min reset.** The
  test campaign 2 lives outside the demo's wipe scope (the wipe is
  keyed on the demo emails + the demo campaign), so this is fine —
  but the plan should explicitly carve out that the test fixtures
  use a separate campaign + non-demo emails.
- **Persistence of test state between runs.** Pytest fixtures are
  per-test, but the database persists. If a test mutates a character
  sheet (e.g. decrements a resource), the next test starts from the
  mutated state. Three options: (a) wipe the test campaign before
  every test (slow but deterministic), (b) restore the relevant
  resource before each test (fast but needs per-test setup code),
  (c) make tests order-independent by always asserting on relative
  state, not absolute (e.g. "counter decreased by 1" not "counter
  is now 4/5"). Phase 1 ships (b); if it gets brittle, drop to (a).
- **WS subscription leak.** If a test crashes between opening the WS
  and tearing it down, the WS stays open until the GC reaps it. The
  hub will accumulate stale connections in the `_channels` set. Use
  pytest's `autouse=True, scope="function"` fixture with an explicit
  `finalizer` that closes the WS.
- **Demo data drift.** The harness assumes Pip has a Shortsword +
  Dagger, Thalindra knows Magic Missile + Fireball, etc. If the
  demo seed changes, the harness breaks. Counter-measures: (a) keep
  the demo PC tests minimal (1-2 attacks, 1-2 spells per PC); (b)
  for full coverage rely on the test-fixture PCs which the harness
  owns end-to-end. The hand-off boundary is clear.
- **Action-economy state isolation.** As discussed under "Action-
  economy state management" — Phase 1 ships strategy 3 (explicit
  per-scenario setup). If maintenance burden gets high, fall back
  to a `/test/reset_battle` admin endpoint guarded by `ENV=test`.
- **CI flakiness.** WS-based assertions in CI are notoriously flaky
  due to network timing. Mitigations: bump `HARNESS_WS_TIMEOUT` to
  5.0 in CI, retry-once on flake, log full WS message stream on
  failure for triage.

---

## What this does NOT do

- **Visual regression.** Modal layout, color tokens, breadcrumb arrow
  geometry, dimming opacity — all live above the HTTP+WS layer. The
  Phase 4 Playwright layer covers some of this; pixel-perfect
  comparison is out of scope entirely (too brittle).
- **Performance / load testing.** "Can the hub handle 50 concurrent
  players?" is a different tool (locust, k6). Not in scope.
- **Security testing.** SQL injection, XSS, CSRF — those are their
  own pass via static analysis + manual review, not the click-through
  harness.
- **Test the test harness.** The harness's own correctness is
  validated by manual review + by catching a real bug the first time
  it's run. No meta-tests.
- **Replace manual play-testing.** The harness catches *contract*
  regressions (endpoint shape, broadcast type, state transitions).
  UX regressions (the breadcrumb labels look weird; the modal is too
  wide on mobile; the chip strip ordering is unintuitive) still
  require eyes. The harness gives the human playtester more headroom
  by handling the mechanical-correctness layer.

---

## Estimated timeline

- **Phase 1 MVP** — ~1-2 dedicated commits. The first commit ships
  the harness scaffold + ~3 endpoints (a vertical slice: `/attack`,
  `/cast_spell`, `/use_feature`). The second commit fills out
  coverage to every shipped endpoint.
- **Phase 2 CI** — 1 commit. The GitHub Actions workflow + the
  `docker-compose.test.yml` + the make targets.
- **Phase 3 contract tests** — incremental: every new endpoint commit
  also adds a harness test. No single big commit.
- **Phase 4 Playwright** — 1-2 dedicated commits. Lands when a UI-layer
  regression motivates it.
- **Phase 5 concurrency** — stretch. Skip until evidence motivates.

Total upfront investment: ~3 commits + ongoing per-endpoint test
additions in every subsequent feature commit. Recurring cost: ~5-10
minutes of test-writing per new feature endpoint. Recurring savings:
1-2 manual play-test cycles per release, plus the bugs that don't
ship.
