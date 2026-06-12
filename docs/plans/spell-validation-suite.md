# Spell-validation test suite — plan

**Status:** 🟠 in progress (v2.182.4, 2026-06-12) — Phase 2D heal assertions landed: `test_spell_catalog_heal.py` casts every healing spell (7) at the caster and range-checks the `spell_cast` broadcast's `auto_heal_rolled` against the declared healing dice shifted by the caster's spellcasting mod; zero skips. Phase 2C attack assertions landed (v2.182.3): `test_spell_catalog_attack.py` casts every spell-attack-roll spell (15) at an NPC and asserts the derived attack bonus = `prof + spellcasting mod` (uniform across one caster) + the hit/miss verdict follows the d20 rules vs target AC; a seeded test proves crit-doubling (Fire Bolt 2d10 → 4d10); zero skips. Phase 2B save assertions landed (v2.182.2): `test_spell_catalog_save.py` casts every save-bearing spell (~116) at an NPC and asserts the response's save ability matches the JSON + the DC matches the caster's spell-save-DC formula (uniform across one caster's spells); zero skips. Phase 1 smoke catalog landed (v2.182.1): `test_spell_catalog_smoke.py` patches one scratch caster with the whole 319-spell catalog + abundant slots and casts every spell by index, asserting the floor contract (no 500, `spell_cast` broadcast emitted); all 319 pass with zero skips. Earlier (v2.49.108): Phase 2A v1 — `spell_catalog.py` loader + `spell_assert.py` damage range assertion + `test_spell_catalog_damage.py` parameterized over `(caster, spell, slot)` rows, covering single-target attack-roll spells (Fire Bolt). Filed: 2A save spells, multi-beam (Scorching Ray / Eldritch Blast), auto-hit (Magic Missile) — each needs a different response-shape adapter.
**Authors:** rolling
**Last updated:** 2026-06-12 (Phase 3b complete — exact save-side buff uplifts: Bless +1d4 / Bane −1d4 on saving throws)

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
**Status 🟠 partial.** v1 (v2.49.108) covers single-target attack-roll
spells with one clean `auto_attack_damage_rolled` (Fire Bolt). The
**multi-beam** backfill shipped v2.182.8 in
`test_spell_catalog_multibeam.py` — Scorching Ray (3×2d6) + Eldritch
Blast (2×1d10) assert beam count, per-beam damage range (crit-widened),
the `auto_attack_damage_rolled == sum(beams)` aggregation contract, and
damage type. The **save-for-half** backfill shipped v2.183.0 in
`test_spell_catalog_save_damage.py` — 8 spells (Fireball, Lightning
Bolt, Burning Hands, Thunderwave, Shatter, Cone of Cold + Sacred Flame /
Poison Spray cantrips) range-check `auto_save_damage_rolled` + type with
`auto_apply_damage` flipped on via a new TEST_MODE-only
`POST /api/test/campaign/{id}/flags` endpoint (so the flag flip doesn't
clobber the campaign's other settings). The **auto-hit** backfill
shipped v2.183.1 in `test_spell_catalog_autohit.py` — Magic Missile's
3 darts (`auto_hit_targets`) range-checked against `1d4+1` force, one
roll per target id sent (dart count is client-side). **All four Phase 2A
damage shapes — attack-roll, multi-beam, save-for-half, auto-hit — are
now covered.** The exact-value (TEST_MODE dice-seed) follow-up
shipped v2.183.4 in `test_spell_catalog_exact_damage.py` (Phase 2A.2 ✅) —
one test seeds the RNG via `POST /api/test/dice/seed` and parses the
engine's breakdown string for arithmetic self-consistency (dice count,
roll bounds, subtotals → grand total → reported `rolled`) across all
four shapes (Fire Bolt 2d10 attack-roll, Scorching Ray 2d6/beam,
Fireball 8d6 save-for-half, Magic Missile 1d4+1/dart auto-hit). **Phase
2A is now complete at both band and exact-value granularity.**

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

### 2E — `test_spell_catalog_concentration.py` ✅ (v2.182.5)
**Shipped:** iterates the 5 `_SPELL_BUFF_MAP` entries flagged
`concentration: True` (Bless, Heroism, Shield of Faith, Protection
from Evil and Good, Haste). Each is **self-cast** (so the buff lands
on the caster's own combatant, which is where `_install_buff`'s
one-at-a-time swap loop fires). Asserts: (1) the install carries
`concentration: True` (read off live battle state, not the JSON
catalog whose `concentration` field is a known SRD-build bug); and
(2) the prior anchor is dropped on the next cast — verified in both
the post-cast battle state and the `buff_update` broadcast's
`replaced_concentration` list.

Filed follow-ups (not in v2.182.5): damage-to-caster concentration
save broadcasts, and failing the save dropping the spell's installed
buff(s).

### 2F — `test_spell_catalog_buff_install.py` ✅ (v2.182.6)
**Shipped:** iterates the 9 `_SPELL_BUFF_MAP` entries (Bless, Heroism,
Shield of Faith, Aid, Sanctuary, Protection from Evil and Good, Mage
Armor, Haste, Longstrider). Each is cast on a **separate** PC target
(the cross-combatant `_install_buff` path, distinct from 2E's self-
cast swap path). Asserts the installed buff's `key`, `name`,
`duration_rounds`, and `concentration` flag match an expected table
mirroring the registry; `effects` is asserted non-empty. These install
unconditionally (no save gate), so the test is deterministic.

Phase 2F-2 follow-up ✅ (v2.183.5) — the save-gated condition installs
(`_SPELL_CONDITION_MAP` — Hold Person → Paralyzed, Bane → Baned,
Fear → Frightened, …) shipped in `test_spell_catalog_conditions.py`.
One test bulk-injects the catalog and, for each of the 8 genuine
single-target save-or-suck spells, seeds the RNG via
`/api/test/dice/seed` and loops seeds until the NPC bandit *fails* its
save, then asserts the response's buff key/name/duration match the
registry AND the condition buff lands on the bandit combatant in the
persisted battle state. A guard test pins the catalog preconditions
(save ability present, no damage, no AoE area). `hold-monster` (no save
in its catalog action), `faerie-fire` (cube AoE → `/place_aoe`), and the
two Monk class-feature entries are excluded with documented reasons.

### 2G — `test_spell_catalog_aoe.py` ✅ (v2.183.2 shape gate + v2.183.3 HTTP placement)
**Shipped (v2.183.2):** a pure-Python content-drift gate (no HTTP/WS,
same shape as the 2H range gate). The server treats a spell as an AoE
only when an action's `area.shape` is in
`tabletop_routes._AOE_SHAPE_SET = {sphere, cone, line, cube,
self_sphere, self_cube}` AND `size_ft > 0` (`_extract_aoe_area`). That
module imports fastapi so it can't be imported by the harness — the
test replicates the frozenset locally (same approach Phase 2E/2F take)
and keeps it in lock step via count + two-way coverage assertions. It
iterates the catalog and asserts every spell declaring a non-empty
`area.shape` (note: the catalog uses `actions[*].area.shape`, not the
`aoe_shape` this plan originally sketched) uses a RAW-valid shape with
positive `size_ft`; the one `line` spell (Lightning Bolt) carries a
positive `secondary_ft` width; the AoE count is exactly 27 (sphere ×15,
cone ×4, cube ×5, line ×1, self_sphere ×1, self_cube ×1) so a zeroed
shape can't pass vacuously; and no catalog shape falls outside the set
/ no replicated entry is dead. Catches a corrupted shape ("sphere" →
"spheer") or zeroed size that would make the server silently stop
painting the template.

**Shipped (v2.183.3) — `test_spell_catalog_aoe_placement.py`:** the HTTP
`/place_aoe` geometry test. For a spell cast without targets, `/place_aoe`
accepts the `cast_id` + `center` + `target_combatant_ids`; the swept-up
targets get a `spell_cast_aoe_resolved` broadcast + save/damage
resolution, a battle combatant left outside the placement is untouched
(absent from `auto_save_targets`, HP unchanged), and the `aoe_pulse`
broadcast carries the catalog shape + size. Covers sphere (Fireball),
cone (Burning Hands), and line (Lightning Bolt) — the three
non-concentration damage AoE shapes — through the live endpoint;
`test_cast_spell_aoe.py` already covered sphere + the cube concentration
marker path. The inside/outside *geometry* itself is computed
client-side, so the server contract tested is "resolve exactly the id
set handed in" rather than a server-side point-in-shape check.

### 2H — `test_spell_catalog_range.py` ✅ (v2.182.7)
**Shipped:** a pure-Python gate (no HTTP/WS) that parses all 319
catalog spells' `range` strings through `app/content/range_parser.py`
and asserts the projection matches the string's RAW category:
Self / Self (N-foot radius) → 0, Touch → 5, "N feet" → N, "N mile(s)"
→ N × 5280, and Special / Unlimited / Sight → None (deliberately
skipped). A string that parses to None while *not* being a recognized
skip token fails (catches typos / drift); numeric bands also assert the
reach equals the embedded number.

Filed follow-up (not in v2.182.7): the HTTP cast-from-position range
gate — cast from inside range succeeds, outside → 409 with a `range`
body field; Touch requires 5 ft adjacency; Self only targets the
caster. Needs the generic `/cast_spell` to enforce a position-based
range check, which isn't wired today.

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

**Status:** 🟠 partial — Phases 3a + 3b shipped (v2.183.6 / v2.183.7). The
auto-applied Bless +1d4 / Bane −1d4 d4 uplifts are validated *exactly* in
`tests/harness/test_spell_catalog_buff_effects.py` on both the **attack**
side (3a — `/attack`) and the **save** side (3b — NPC save in
`/cast_spell`): a same-seed with/without-buff pair isolates the buff die
and asserts the rolled-total delta equals the printed d4 value × the
registry sign, so a `1d4`→`1d6` content edit, a dropped uplift, or a sign
flip fails the gate. Filed for later 3c+ slices: Shield of Faith (+2 AC),
Mage Armor (13+DEX), Haste / Slow (AC + speed), Hex / Hunter's Mark (+1d6
on hits). The per-spell spot tests in `test_buff_attack_hooks.py` already
cover several of these at "token appears" granularity; the next slices
promote them to exact-contribution gates.

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
- [✅] Phase 2A — Damage assertions (v1 v2.49.108: Fire Bolt attack-roll; v2.182.8: multi-beam backfill (`test_spell_catalog_multibeam.py`) — Scorching Ray 3×2d6 + Eldritch Blast 2×1d10; v2.183.0: save-for-half backfill (`test_spell_catalog_save_damage.py`) — 8 spells' `auto_save_damage_rolled` + new TEST_MODE `/api/test/campaign/{id}/flags` toggle; v2.183.1: auto-hit backfill (`test_spell_catalog_autohit.py`) — Magic Missile 3-dart `auto_hit_targets`; **v2.183.4: exact-value Phase 2A.2 (`test_spell_catalog_exact_damage.py`)** — seeded RNG + breakdown self-consistency across all four shapes; Phase 2A complete at both band and exact granularity)
- [✅] Phase 2B — Save assertions (`test_spell_catalog_save.py`) — v2.182.2: all ~116 save spells assert ability + uniform DC, zero skips.
- [✅] Phase 2C — Attack assertions (`test_spell_catalog_attack.py`) — v2.182.3: all 15 spell-attack-roll spells assert bonus = prof + spell mod + hit/miss vs AC; seeded crit-doubling test (2d10 → 4d10), zero skips.
- [✅] Phase 2D — Heal assertions (`test_spell_catalog_heal.py`) — v2.182.4: all 7 healers' `auto_heal_rolled` (read off the `spell_cast` WS) range-checked against dice + spellcasting mod, zero skips.
- [✅] Phase 2E — Concentration assertions (`test_spell_catalog_concentration.py`) — v2.182.5: all 5 concentration buff-spells (Bless, Heroism, Shield of Faith, Protection from Evil and Good, Haste) self-cast; install carries the concentration flag + the prior anchor is dropped via the one-at-a-time swap (asserted in battle state + `replaced_concentration` broadcast), zero skips.
- [✅] Phase 2F — Buff install assertions (`test_spell_catalog_buff_install.py`) — v2.182.6: all 9 `_SPELL_BUFF_MAP` spells cast on a separate target; installed key/name/duration_rounds/concentration asserted against the expected payload table, zero skips. **v2.183.5: Phase 2F-2 (`test_spell_catalog_conditions.py`)** — the save-gated `_SPELL_CONDITION_MAP` installs (8 spells) land their condition on a seed-forced failed NPC save, asserted in both response + battle state, with a catalog-precondition guard.
- [x] Phase 2G — AoE assertions (v2.183.2 shape drift gate + v2.183.3 HTTP /place_aoe geometry)
- [✅] Phase 2H — Range assertions (`test_spell_catalog_range.py`) — v2.182.7: all 319 spell ranges parsed via `range_parser` and asserted against their RAW category (Self→0, Touch→5, N feet→N, N miles→N×5280, Special/Unlimited/Sight→None) + numeric value; pure-Python, zero drift. (HTTP cast-from-position gate filed as follow-up.)
- [ ] Phase 3 — Buff effect validation
- [ ] Phase 4 — Bespoke complex-spell tests
- [ ] Phase 5 — CI integration + coverage gating

Each checkbox flips green as the corresponding commit lands; the
status line at the top of this doc is updated in the same commit.
