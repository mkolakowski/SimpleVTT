# Spell-validation test suite — plan

**Status:** 🟠 in progress (v2.182.1, 2026-06-12) — Phase 1 smoke catalog landed: `test_spell_catalog_smoke.py` patches one scratch caster with the whole 319-spell catalog + abundant slots and casts every spell by index, asserting the floor contract (no 500, `spell_cast` broadcast emitted). All 319 pass with zero skips. Earlier (v2.49.108): Phase 2A v1 — `spell_catalog.py` loader + `spell_assert.py` damage range assertion + `test_spell_catalog_damage.py` parameterized over `(caster, spell, slot)` rows, covering single-target attack-roll spells (Fire Bolt). Filed: 2A save spells, multi-beam (Scorching Ray / Eldritch Blast), auto-hit (Magic Missile) — each needs a different response-shape adapter.
**Authors:** rolling
**Last updated:** 2026-06-12

A plan to expand `tests/harness/` so every spell in
`app/data/local/dnd5e/spells/` (319 SRD entries as of v2.49.102, plus
any homebrew the GM imports) is exercised against an explicit
behavioural contract — slot consumed at the right level, save DC
matches the caster's spell save DC, damage dice match the spell's
declared expression, applied buffs install with the right duration
and effect, etc. The aim is to catch content/route drift the way the
existing class-feature suite does: any future change to
`/api/campaign/{cid}/cast_spell`, the spell-content schema, or a
specific spell's mechanical attributes either keeps the contract or
fails CI before merge.

---

## Why this layer is needed

`tests/harness/test_cast_spell.py` + the per-feature siblings
(`test_cast_spell_attack.py`, `test_cast_spell_heal.py`,
`test_cast_spell_save.py`, `test_cast_spell_aoe.py`,
`test_cast_spell_target.py`, `test_cast_spell_range.py`) cover the
**endpoint contract** — they call `/cast_spell` with hand-picked
spells (Fireball, Cure Wounds, Hold Person, etc.) and assert the
broadcast shape. They do NOT cover the **catalog**: 319 entries are
shipped, only ~25 have explicit tests, and a content edit to any of
the other ~294 can ship a broken spell that doesn't 500 the endpoint
but rolls the wrong dice, applies the wrong save, or installs a buff
with the wrong duration. Today that's caught by manual GM play; the
plan makes it CI-gated.

The existing layers cover what we already know to test:

| Layer | What it tests | Gap this plan fills |
|---|---|---|
| `tests/harness/test_cast_spell*.py` | A dozen specific spells across the major mechanics — happy paths, error paths. | Doesn't iterate the catalog. Add a new spell to `app/data/local/dnd5e/spells/`; nothing reads it as a test fixture. |
| `tests/harness/test_cast_sleep*.py` | One spell's full edge-case story (HP pool, wake-on-damage, immunity). | Sleep is the only spell with this depth. Comparable depth needed for ~30 other spells with quirky rules (Bless, Bane, Hex, Hunter's Mark, Faerie Fire, Counterspell, Wish, …). |
| `tests/encounter_sim/` | End-to-end UI scenarios using a fixed set of spells. | Validates the player experience but doesn't enumerate the catalog. |
| Manual GM testing | Whatever the GM happens to cast that session. | Slow + ad-hoc; regressions surface in actual play, not before merge. |

This plan does **not** replace the existing per-spell deep-dive tests
— it complements them with a generated catalog-iterating layer that
catches mechanical drift cheaply.

---

## Design principles

1. **Catalog is the source of truth.** The spell JSON files at
   `app/data/local/dnd5e/spells/<slug>.json` are the input fixture.
   The test framework iterates them; the test code shouldn't list
   spells by name. New JSON files automatically get covered; deleted
   spells fall out of the suite without a test edit.
2. **Per-mechanic test groups, not per-spell test files.** A spell
   that does damage gets the damage assertions; a spell that does a
   save gets the save assertions; concentration spells get
   concentration assertions. Mechanics are independent, so the matrix
   is `mechanics × spells` filtered to applicable rows — not 319
   bespoke test files.
3. **Deterministic dice via `TEST_MODE=true`.** The `/api/test/dice/seed`
   endpoint from v2.49.12 is the foundation. Damage / save / attack
   tests seed the RNG so "Magic Missile 3 darts → 12 damage" is
   reproducible across runs.
4. **Run-time budget under 90 s.** The existing `tests/harness/` suite
   runs in ~30 s. Catalog iteration at 319 spells × N mechanics could
   blow that out fast. Mitigations: parameterize aggressively to share
   fixtures, skip uncategorized spells in early phases, and split the
   catalog suite into its own pytest mark / CI job that can be run
   independently from the smoke harness.
5. **Skip + xfail before delete.** Spells with not-yet-implemented
   mechanics (Wish, Polymorph, Plane Shift, etc.) should `pytest.mark.skip`
   with a reason citing the open issue — never silently fall out of
   the catalog. Spells with known content bugs get `pytest.mark.xfail`
   so a fix flips them green without needing test edits.

---

## Phase 0 — Inventory & contract

**Goal:** decide what "validate" means per mechanic + what the spell
JSON needs to expose.

**Tasks:**
- A. Catalog every spell's mechanical attributes from the JSON:
     `level_int`, `school`, `casting_time`, `range`, `duration`,
     `concentration`, `ritual`, `actions[].damage`,
     `actions[].damage_type`, `actions[].damage_scaling`,
     `actions[].attack_roll`, `actions[].save_ability`,
     `actions[].save_dc_attribute` (?), `actions[].healing`,
     `actions[].aoe_shape`, `actions[].aoe_size`, `actions[].buff_key` (?).
     Spot-check: are these fields populated for all 319? Are there
     missing fields the renderer relies on?
- B. Cross-reference against the SRD's mechanical effects: for each
     spell, the JSON's mechanical attributes should match the SRD
     text. (e.g. Bless says "+1d4 to attacks and saves for 1 minute";
     does the JSON encode that as a buff with the right duration?)
- C. List spells whose mechanical attributes aren't fully encoded —
     these are the "complex" spells (Wish, Polymorph, Counterspell,
     Mirror Image, Mage Armor, ...) that need bespoke handling.
- D. Decide the smoke contract: at minimum, every spell can be cast
     against a target/AoE without 500, consumes a slot, emits a
     `spell_cast` WS broadcast. This is the floor for Phase 1.

**Output:** `docs/plans/spell-validation-suite-inventory.md` (a sister
doc) tabulating each spell × mechanic flag. Plus a list of "complex"
spells that escape the matrix.

**Exit criterion:** the inventory doc lists every spell + flags +
"complex" group is bounded.

---

## Phase 1 — Smoke catalog (every spell castable)

**Goal:** one parameterized test that calls `/cast_spell` for each
spell in the catalog and asserts the floor contract — no 500, slot
consumed, broadcast emitted.

**Test:** `tests/harness/test_spell_catalog_smoke.py`. Pattern:

```python
SPELL_FILES = sorted(Path("app/data/local/dnd5e/spells").glob("*.json"))

@pytest.mark.parametrize("spell_path", SPELL_FILES, ids=lambda p: p.stem)
async def test_spell_casts_without_500(spell_path, gm_client, gm_ws, roster):
    spell = json.loads(spell_path.read_text())
    caster = _find_caster_for_spell(spell, roster)  # pick a PC who can cast it
    if caster is None:
        pytest.skip(f"No demo PC can cast {spell['name']}")
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json=_minimal_cast_body(caster, spell),
    )
    assert resp.status_code in (200, 201), resp.text
    # ... slot decrement, broadcast emitted
```

**Mechanics needed:**
- `_find_caster_for_spell` helper — pick the lowest-level demo PC
  whose class is in `spell_lists` AND who has an available slot of
  the right level.
- `_minimal_cast_body` helper — build the minimal body for a
  successful cast: slot_level, target_combatant_id if needed,
  caster_x/y if AoE, etc. Reads the spell's mechanical attributes
  to know what shape of body to build.
- A long_rest fixture that resets the caster's slots between tests
  (or just `override: true` to skip slot consumption — depends on
  scope).
- Skip if no demo PC can cast (skipping is fine for Phase 1 floor;
  Phase 2 will add test-fixture casters for the missing classes).

**Exit criterion:** ~300 of 319 spells pass smoke (the remaining
handful are skipped with a known reason, e.g. requires a class no
demo PC has, or needs material components not yet modelled).

**Risks:** runtime — 300 cast calls at ~50 ms each = ~15 s. Plus WS
overhead. Probably under the budget, but if not, parallelise via
pytest-xdist.

---

## Phase 2 — Mechanical assertions per-group

**Goal:** for each spell with a given mechanic, assert the
mechanic's outcome shape is correct.

**Test groups** (each one its own test file, parameterized over the
applicable subset of the catalog):

### 2A — `test_spell_catalog_damage.py`
For every spell with `actions[*].damage` non-empty:
- Damage breakdown matches the declared dice expression
  (`damage` string in JSON, e.g. `"8d6"`, parsed and rolled).
- Damage type matches `damage_type`.
- Higher-level scaling: cast at slot 2 → damage matches
  `damage_scaling` rule (e.g. Fireball adds 1d6 per level above 3rd).
- Seed the RNG before each cast so the assertion is exact.

### 2B — `test_spell_catalog_save.py`
For every spell with `actions[*].save_ability`:
- Broadcast carries `save_dc` matching `8 + caster_prof + caster_spell_mod`.
- Save ability matches the JSON.
- Half-on-save behavior: if `actions[*].half_on_save` is set, the
  applied damage should drop ~50 % when the target's save succeeds.

### 2C — `test_spell_catalog_attack.py`
For every spell with `actions[*].attack_roll = true`:
- Attack bonus matches `caster_prof + caster_spell_mod`.
- Hit/miss determined against target AC + applied damage on hit.
- Crit on natural 20 doubles damage dice.

### 2D — `test_spell_catalog_heal.py`
For every spell with `actions[*].healing`:
- Heal amount matches the dice expression + scaling per slot level.
- `damage_applied` is negative (or the broadcast has `heal_applied`).
- Target's `hp_current` increases by the heal amount (capped at hp_max).

### 2E — `test_spell_catalog_concentration.py`
For every spell with `concentration: true`:
- Casting installs concentration on the caster (`/concentration/{cid}` GET returns the spell).
- Casting a second concentration spell drops the first
  (already tested for some spells; expand catalog coverage).
- Damage to the caster triggers a concentration save broadcast.
- Failing the save drops the buff(s) installed by the spell.

### 2F — `test_spell_catalog_buff_install.py`
For every spell with a known buff side effect (Bless, Bane, Hex,
Hunter's Mark, Faerie Fire, Hold Person, Sleep, etc.):
- Casting installs the buff on the target combatant.
- Buff has correct `key`, `name`, `duration_rounds`, `effects`.
- Buff key matches the canonical name used by the auto-uplift /
  intercept paths in `_attack_dice_uplifts` (`app/routes/tabletop_routes.py`).

### 2G — `test_spell_catalog_aoe.py`
For every spell with `actions[*].aoe_shape`:
- `/place_aoe` accepts the spell + shape + size + caster pos.
- Targets inside the AoE get the broadcast.
- Targets outside don't.
- Shape coverage matches RAW (sphere = circle from center, cube =
  square from corner, cone = wedge, line = rectangle).

### 2H — `test_spell_catalog_range.py`
For every spell with a parseable `range`:
- Cast from a position inside the spell's range succeeds.
- Cast from outside fails with 409 + a `range` field in the body.
- Touch spells (range "Touch") require adjacency (5 ft).
- Self spells (range "Self") only target the caster.

**Mechanics needed:**
- Test-fixture casters for every class (PHB-12) at every relevant
  level. The demo has all 12 classes but at varying levels — Phase
  1.5 of the harness plan covers test-fixture characters.
- An assertion helper library (`tests/harness/spell_assert.py`) with
  helpers like `assert_damage_matches_expression`, `assert_buff_installed`,
  `assert_concentration_set`, etc.
- A spell-catalog loader (`tests/harness/spell_catalog.py`) that
  reads the JSON files once at session scope and exposes a filtered
  iterator for each mechanic.

**Exit criterion:** each of 2A–2H has > 90 % of its applicable
spells passing. Spells with not-yet-implemented mechanics are
`pytest.mark.skip(reason="...")` with a tracked issue.

**Risks:** runtime explosion. Mitigation: split each 2X file into
its own pytest job in CI, run them in parallel.

---

## Phase 3 — Buff effect validation

**Goal:** for every spell that installs a buff, validate the buff's
**mechanical effect** during play — not just that it was installed.

The most common slip: a content edit changes Bless from `+1d4 to
attacks/saves` to `+1d6 to attacks/saves` but the `_attack_dice_uplifts`
helper in `app/routes/tabletop_routes.py` still hard-codes `+1d4`.
The buff installs correctly, the chip shows correctly, but the
auto-uplift on attack rolls is wrong.

**Test:** `tests/harness/test_spell_catalog_buff_effects.py`. Pattern:
for each buff-installing spell, cast it, then perform a downstream
action that the buff modifies (attack, save, damage, AC, speed) and
assert the modifier matches the spell's RAW.

**Buffs to cover:**
- Bless / Bane: +1d4 / -1d4 on attacks + saves
- Hex: +1d6 necrotic on hits, disadvantage on chosen ability checks
- Hunter's Mark: +1d6 on hits
- Hold Person: incapacitated, paralyzed (auto-fail STR/DEX saves, attacks have advantage, melee crit auto)
- Sleep: unconscious (already covered; in-catalog smoke + buff-effect)
- Faerie Fire: advantage on attacks against, can't benefit from invisible
- Shield of Faith: +2 AC
- Mage Armor: AC becomes 13 + DEX mod
- Haste: +2 AC, advantage on DEX saves, +1 action, double speed
- Slow: -2 AC + WIS save, half speed, can't use reactions
- Bless of Bahamut / Curse of Strahd / homebrew: per-buff-key assertion

**Mechanics needed:**
- For each buff-installing spell, a "downstream action" recipe:
  attack from the buffed combatant, or against the buffed combatant.
- Deterministic dice so the uplift's contribution is observable
  (e.g. seed RNG so the buff's +1d4 always rolls 3 — verifies
  3 was added to the attack total).
- Per-buff golden expected output: the broadcast should carry a
  `dmg_uplift_breakdown` chip / similar.

**Exit criterion:** every buff-installing spell has at least one
buff-effect test, OR an explicit skip with reason.

**Risks:** requires the engine to actually implement the buff's
effect. Some buffs aren't auto-applied today (e.g. Bane's -1d4 on
saves is filed as a TODO from v2.31.0). For those, the test asserts
the buff installs + the auto-uplift / intercept stays manual; a
future commit implementing the auto-effect can flip the test to
assert the auto-effect lands.

---

## Phase 4 — Bespoke complex-spell tests

**Goal:** the dozen-ish spells that don't fit the catalog matrix get
their own deep-dive tests, modelled on `tests/harness/test_cast_sleep*.py`.

**Candidates** (from Phase 0 inventory):
- Counterspell — needs reaction trigger + caster identification
- Polymorph / Wild Shape — needs alternate stat-block swap
- Wish — open-ended, mostly narrative; assert it doesn't 500
- Mage Armor — AC override, needs equipment slot logic
- Mirror Image — duplicate tokens, attack redirection
- Bless of Bahamut (homebrew) — homebrew handling
- Eldritch Blast — multi-beam scaling
- Magic Missile — multi-dart scaling (already partial coverage)
- Spiritual Weapon — persistent attacker
- Spirit Guardians — concentration aura
- Conjure X / Summon X — token creation
- Hold Person + Stunning Strike interaction — incapacitation stack
- Sleep wake-on-damage — already tested; this is the model

**Test:** one file per complex spell, named
`tests/harness/test_cast_<spell-slug>.py`. Each file owns the spell's
full edge-case story. The smoke + mechanic catalog tests stay
lightweight; the deep-dive tests cover everything else.

**Exit criterion:** every spell on the Phase 0 "complex" list has its
own test file.

---

## Phase 5 — CI integration + coverage gating

**Goal:** the new catalog suite runs on every push + PR, fails
loudly, and is tracked in `docs/test-harness-coverage.md`.

**Tasks:**
- Add a `spell-catalog` job to `.github/workflows/test-harness.yml`
  that runs the Phase 1 + Phase 2 + Phase 3 + Phase 4 files in
  parallel (pytest-xdist). Cache the spell catalog load.
- Update `docs/test-harness-coverage.md` with a new section for the
  spell catalog tests + per-mechanic counts.
- Add a coverage badge to the catalog page that reads "X / 319 spells
  smoke-tested, Y / Z damage-validated, ...".
- Failure reporting: when a test fails, include the spell's slug +
  the JSON path + the expected vs. actual mechanic. The output
  should make "Magic Missile damage broken" diagnosable from CI logs
  without re-running locally.

**Exit criterion:** the spell-catalog job is green on `main`, has
< 90 s wall-clock, and a regression that breaks any spell's contract
fails the workflow before merge.

---

## Mechanics & infrastructure

A summary of the non-test helpers this plan asks for:

### `tests/harness/spell_catalog.py` (NEW)
- `load_all_spells()` — read every JSON in `app/data/local/dnd5e/spells/`,
  return a list of dicts.
- `filter_by_mechanic(spells, mechanic)` — yield spells matching a
  predicate (e.g. `lambda s: any(a.get("damage") for a in s["actions"])`).
- `find_caster_for_spell(spell, roster)` — pick a demo PC who can
  cast it; prefer the lowest-level qualified caster so the test
  doesn't burn high-level slots.

### `tests/harness/spell_assert.py` (NEW)
- `assert_damage_matches_expression(broadcast, expected_expr)` —
  parse the rolled total against the dice expression range, assert
  it's in bounds (or exact with seeded RNG).
- `assert_buff_installed(combatant, buff_key, *, duration_rounds=None)`.
- `assert_concentration_set(client, caster_id, spell_name)`.
- `assert_save_dc(broadcast, expected_dc)`.
- `assert_aoe_targets(broadcast, expected_combatant_ids)`.

### `tests/harness/conftest.py` extensions
- `spell_catalog` fixture (session-scoped) — calls `load_all_spells()`
  once.
- `seeded_dice_client` fixture — wraps `gm_client` with auto-seed
  before each cast for deterministic damage tests.

### CI workflow
- New `spell-catalog` job in `.github/workflows/test-harness.yml`
  with its own caching (the catalog rarely changes, so the JSON
  parse result can be cached across jobs).
- `pytest-xdist` for parallel test execution within the job.

### Documentation
- `docs/plans/spell-validation-suite-inventory.md` — Phase 0
  output: catalog × mechanic table.
- `docs/test-harness-coverage.md` — new "Spell catalog" section
  with per-mechanic counts.
- Wiki entries (this plan + the inventory doc).

---

## Open questions

- **Homebrew spells.** Should the suite also iterate
  `app/data/campaign-{cid}/dnd5e/spells/*.json` (GM-imported homebrew)?
  Pro: catches GM-uploaded broken content. Con: tests become per-
  campaign which doesn't fit the demo-mode-only harness model.
  Probably defer until Phase 5; smoke a single demo-imported spell to
  prove the path.
- **Multi-system support.** Spells today live under `dnd5e/`. If a
  future commit adds a 5.5e or PF2e content tree, the catalog
  iterator should glob the system directory. Make
  `load_all_spells(system="dnd5e")` parameterized.
- **Speed vs. comprehensiveness.** 319 spells × 8 mechanic groups
  = potentially 2552 tests. Even at 30 ms each that's 76 s. Tight
  but achievable with pytest-xdist. If runtime blows out, split into
  a "fast" catalog suite (Phase 1 + 2) that runs on every PR + a
  "slow" suite (Phase 3 + 4) that runs nightly.
- **Content-vs-engine bugs.** A failing test could mean the JSON is
  wrong OR the route is wrong. The error message should make this
  distinguishable — print the JSON's declared expression next to the
  observed broadcast value.

---

## Risks

| Risk | Mitigation |
|---|---|
| Suite becomes flaky due to non-deterministic dice. | Mandate `/api/test/dice/seed` before every damage/save/heal test; assert exact values, not ranges. |
| Runtime blows out > 90 s. | pytest-xdist, split fast + slow tiers, cache catalog parse. |
| Content edits break a lot of tests at once (legitimate breakage). | Tests should report the slug + JSON line that doesn't match the assertion, so a content fix is targeted. |
| Spells with not-yet-implemented mechanics get noisy skips. | `pytest.mark.skip(reason="<linked issue>")` instead of silently passing; review skip list quarterly. |
| The "complex" list grows over time. | Cap at Phase 4's initial dozen; new complex spells get an open issue + skip until their bespoke test lands. |
| Demo PC roster doesn't cover every class × level. | Phase 1.5 of the existing test-harness plan adds test-fixture characters; coordinate timing. |

---

## Status tracking

- [ ] Phase 0 — Inventory + sister doc
- [✅] Phase 1 — Smoke catalog (`test_spell_catalog_smoke.py`) — v2.182.1: all 319 spells cast without 500, zero skips.
- [🟠] Phase 2A — Damage assertions (v1 v2.49.108: Fire Bolt attack-roll; filed save / multi-beam / auto-hit follow-ups)
- [ ] Phase 2B — Save assertions
- [ ] Phase 2C — Attack assertions
- [ ] Phase 2D — Heal assertions
- [ ] Phase 2E — Concentration assertions
- [ ] Phase 2F — Buff install assertions
- [ ] Phase 2G — AoE assertions
- [ ] Phase 2H — Range assertions
- [ ] Phase 3 — Buff effect validation
- [ ] Phase 4 — Bespoke complex-spell tests
- [ ] Phase 5 — CI integration + coverage gating

Each checkbox flips green as the corresponding commit lands; the
status line at the top of this doc is updated in the same commit.
