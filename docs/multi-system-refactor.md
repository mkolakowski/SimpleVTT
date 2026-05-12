# Multi-system refactor plan

> **Status:** Proposed — not started. Written 2026-05-12 by Claude for review.
> **Author intent:** support Vampire: The Masquerade v5 and Vaesen as
> first-class game systems alongside D&D 5e, without rewriting the tabletop.

This file is the primary input for the refactor. Re-read before starting
the work; push back on anything that doesn't survive a fresh look.

---

## 1 — Why

The codebase has a `GameSystem` registry (`app/game_systems.py`) plus
`generic` and `dnd5e` entries, but the D&D-specific logic is woven
through routes, templates, static JS, and Open5e integration. Adding a
new system today requires editing dozens of files in many places.

The author wants to add Vampire: The Masquerade v5 (V5) and Vaesen.
Both are simpler than D&D 5e in structure (no levels, no
multi-classing, no subclasses, no Open5e equivalent) but introduce
**dice pool resolution** instead of d20+modifier — which the current
roll engine can't express.

## 2 — Current coupling inventory

What's universal (stays central):
- Token movement, maps, grids, fog
- Roll log + chat panel + roll requests
- WebSocket hub + campaign sessions
- Audio / playlists
- Concentration tracker (conceptually universal, currently D&D-shaped)
- Generic sheet template
- `GameSystem` registry + `Character.template` column
- HP / conditions / chat (concept; current implementation is D&D-flavored)

What's D&D-specific (needs to move into `app/systems/dnd5e/`):
- `app/templates/sheet_dnd5e.html` (5800+ lines)
- `app/static/sheet.js` (mostly shared, but has D&D branches)
- `app/static/beast_picker.js`
- `app/static/dnd5e_subclass_spells.js`
- `app/static/dnd5e_class_resources.js`
- `app/static/dnd5e_innate_defenses.js`
- `app/static/open5e_coverage.js`
- `app/character_presets.py` (D&D presets)
- `app/open5e_local.py` (D&D SRD cache)
- All `/api/open5e/*` endpoints in `app/routes/tabletop_routes.py`
- D&D-specific endpoints in `app/routes/tabletop_routes.py`:
  - `cast_spell`, `apply_healing`, `rest_character`,
  - `transform_character`, `revert_character`, `use_resource`,
  - `concentration_*`, weapon attack helpers
- `normalize_dnd5e_sheet()` and all D&D template fields in `app/sheet_templates.py`
- Mini-sheet HP / hit dice / rest controls in `app/templates/tabletop.html`

## 3 — Target architecture

### 3.1 Folder layout

```
app/
  systems/
    __init__.py            # registry + SystemModule Protocol
    generic/
      __init__.py          # implements SystemModule
      routes.py            # FastAPI sub-router (mounted by main app)
      templates/
        sheet.html
      static/
        sheet.js           # system-specific extensions, if any
      presets.py
      normalize.py
    dnd5e/
      __init__.py
      routes.py            # cast_spell, transform, rest, resource, /api/open5e/*
      templates/
        sheet.html         # was sheet_dnd5e.html
        _beast_picker_modal.html
      static/
        sheet.js           # was the dnd5e branches of static/sheet.js
        beast_picker.js
        dnd5e_subclass_spells.js
        dnd5e_class_resources.js
        dnd5e_innate_defenses.js
        open5e_coverage.js
      presets.py           # was character_presets.py
      normalize.py         # was normalize_dnd5e_sheet
      open5e.py            # was open5e_local.py
      data/
        open5e/...         # was app/data/open5e/
    vaesen/                # Phase 3
      ...
    vampire5/              # Phase 4
      ...

  dice/                    # was dice.py
    __init__.py            # registry; resolves expr → engine
    d20.py                 # current XdY±Z, kh/kl, adv/dis
    pool.py                # Year Zero / V5 base: count successes on N-sided dice
    v5.py                  # extends pool with Hunger dice, messy/bestial
```

### 3.2 SystemModule protocol (sketch)

```python
# app/systems/__init__.py
from typing import Protocol, runtime_checkable
from fastapi import APIRouter

@runtime_checkable
class SystemModule(Protocol):
    key: str                          # matches GameSystem.key and Character.template
    label: str
    template_dir: str                 # for Jinja loader
    static_dir: str                   # for /static/<key>/ mount
    template_name: str = "sheet.html" # default

    def router(self) -> APIRouter: ...
    def normalize_sheet(self, sheet: dict) -> dict: ...
    def default_sheet(self) -> dict: ...
    def presets(self) -> list[dict]: ...   # for the New Character picker
    def quick_dice(self) -> list[QuickDie]: ...

    # Optional hooks (default to no-op):
    def mini_sheet_partial(self) -> str | None: ...    # Jinja path
    def feature_static_modules(self) -> list[str]: ...  # extra <script src> URLs
```

Boot sequence:
1. Main app scans `app/systems/*/__init__.py` for `SystemModule` exports.
2. For each, mount `module.router()` under `/`.
3. Add `module.static_dir` as a static mount at `/static/<key>/`.
4. Add `module.template_dir` to the Jinja loader search path.
5. Register the system in `SYSTEMS` dict.

The existing `Character.template` column already routes sheets to the
right system. No schema change needed.

### 3.3 Dice engine shape

The current `app/dice.py` returns `DiceRoll(total: int, breakdown: str)`.

Refactor `RollResult` into a discriminated dataclass:

```python
@dataclass
class RollResult:
    mode: str              # "total" | "pool" | "v5-pool"
    total: int = 0         # for d20-style
    breakdown: str = ""    # human-readable description
    # Pool fields
    successes: int = 0
    crits: int = 0
    # V5-only
    hunger_results: list[int] = field(default_factory=list)
    messy_critical: bool = False
    bestial_failure: bool = False
    # Raw dice for the UI
    dice: list[int] = field(default_factory=list)
```

Each engine module exposes `roll(expression: str, **kwargs) -> RollResult`.
The system module declares which engine its `quick_dice` use; ad-hoc
expressions in the dice tray are parsed by the active campaign's
system module.

**Backward compat:** the `total` field stays on every result. Existing
roll-log renderers that read `.total` keep working; pool roll cards
opt into the `successes` rendering when `mode != "total"`.

## 4 — Phase 1: File reorg (target ~1 day)

**Goal:** physically separate D&D files into `app/systems/dnd5e/` with
zero behavior change. PR should be a structural diff only — no new
features, no logic edits beyond changing import paths.

### Concrete moves

| From | To |
|---|---|
| `app/templates/sheet_dnd5e.html` | `app/systems/dnd5e/templates/sheet.html` |
| `app/templates/_beast_picker_modal.html` | `app/systems/dnd5e/templates/_beast_picker_modal.html` |
| `app/templates/sheet_generic.html` | `app/systems/generic/templates/sheet.html` |
| `app/static/sheet.js` | `app/systems/dnd5e/static/sheet.js`* |
| `app/static/beast_picker.js` | `app/systems/dnd5e/static/beast_picker.js` |
| `app/static/dnd5e_*.js` | `app/systems/dnd5e/static/...` |
| `app/static/open5e_coverage.js` | `app/systems/dnd5e/static/open5e_coverage.js` |
| `app/character_presets.py` | `app/systems/dnd5e/presets.py` |
| `app/open5e_local.py` | `app/systems/dnd5e/open5e.py` |
| `app/data/open5e/` | `app/systems/dnd5e/data/open5e/` |
| `normalize_dnd5e_sheet()` in `app/sheet_templates.py` | `app/systems/dnd5e/normalize.py` |
| D&D template fields in `app/sheet_templates.py` | `app/systems/dnd5e/default_sheet.py` |

*`sheet.js` will need a careful look — anything that's actually shared
between systems stays at `app/static/sheet.js` (form save, basic field
hydration, etc.); D&D-specific code (multiclass roster, subclass spells,
HP rolls, defenses chip logic, resources panel) moves.

### D&D routes to extract

Pull these out of `app/routes/tabletop_routes.py` into
`app/systems/dnd5e/routes.py`:

- `cast_spell` (~line 1280)
- `apply_healing` (~1440)
- `rest_character` (~1523)
- `use_resource` (~1727)
- `transform_character` (~1936)
- `revert_character` (~2153)
- `_open5e_to_dnd5e_sheet` and all helpers it uses
- All `/api/open5e/*` endpoints
- `import_open5e_monster`
- Weapon attack helper (`use_attack`) — uncertain, possibly stays universal

Leave in core `tabletop_routes.py`:
- Token CRUD + move
- Map endpoints
- Campaign create/settings/members
- Generic roll endpoint
- Roll request endpoints
- Concentration (move to D&D? probably yes — concept exists in V5 / Vaesen but not in the same shape)

### Acceptance criteria for Phase 1

- All existing tests / smoke flows pass unchanged.
- Open the D&D 5e sheet on a live campaign and confirm: Wild Shape works,
  Class Resources auto-fill works, Defenses chips work, beast picker
  works, HP rolls table works.
- File count in `app/routes/tabletop_routes.py` drops from ~6800 lines
  to under 2000 (everything not core).
- `app/systems/dnd5e/__init__.py` exposes a working `SystemModule`.

## 5 — Phase 2: Dice engine extensibility (target ~1 day)

**Goal:** make `app/dice/` polymorphic so a pool-based engine can return
success counts. No new system uses it yet; this just opens the seam.

### Concrete steps

1. Rename `app/dice.py` → `app/dice/__init__.py`. Move existing logic
   into `app/dice/d20.py`. Re-export public API from `__init__.py` so
   existing imports (`from .. import dice as dice_mod`) keep working.
2. Promote `DiceRoll` to `RollResult` (see §3.3). Existing callsites
   read `.total` / `.breakdown` — those fields stay.
3. Add `app/dice/pool.py` with `roll_pool(expression, dice_size=6) -> RollResult`.
   Expression grammar: `Nd6p` (push-able), `Nd10p`, etc. Successes =
   count of dice ≥ 6 (Year Zero) or ≥ 6 (V5, but 10s pair-double).
4. Roll log card: extend the roll-card renderer in `app/static/tabletop.js`
   (lines ~390-450, `appendRoll`) to render either a total OR a success
   count based on `r.mode`. Same for `app/templates/rolls_popout.html`.

### Things to leave alone in this phase

- Don't build the V5 Hunger logic yet — that's part of Phase 4 (or do
  it speculatively in `app/dice/v5.py` but don't wire it).
- Don't touch the D&D sheet's roll buttons.
- Don't add new endpoints.

### Acceptance criteria for Phase 2

- All existing D&D rolls render identically.
- Calling `app.dice.pool.roll_pool("5d6p")` returns `{mode: 'pool',
  successes: N, dice: [...], breakdown: "5d6 → 3 successes"}`.
- The roll-log card renders that pool result with a `3 successes` label
  instead of a total.

## 6 — Phase 3: Vaesen (target ~2 days)

Vaesen is the **smallest** of the three new systems and uses Year Zero
dice, which forces us to use the new pool engine end-to-end. It's the
test of whether the abstractions work.

### Sheet shape

```python
VAESEN_TEMPLATE = {
    "archetype": "",              # text — Academic / Doctor / Hunter / ...
    "age": "",                    # Young / Middle-aged / Old
    "motivation": "",
    "trauma": "",
    "dark_secret": "",
    "relationships": "",          # free text
    # 4 attributes
    "attributes": {
        "physique": 2,
        "precision": 2,
        "logic": 2,
        "empathy": 2,
    },
    # ~12 skills (each 0-5)
    "skills": {
        "agility": 0, "close_combat": 0, "force": 0,
        "medicine": 0, "stealth": 0, "vigilance": 0,
        "investigation": 0, "learning": 0, "observation": 0,
        "inspiration": 0, "manipulation": 0,
        "ranged_combat": 0,
    },
    # Conditions — 4 physical + 4 mental, each boolean
    "conditions_physical": {"exhausted": False, "battered": False, "wounded": False, "broken": False},
    "conditions_mental":   {"angry": False, "frightened": False, "hopeless": False, "broken": False},
    "talents": [],                # [{name, desc}]
    "resources": "",              # text — gear, money, contacts
    "notes": "",
}
```

### UI flow

- Sheet UI: 4 attribute boxes, 12 skill rows, 8 condition checkboxes,
  talents list, free-text Resources + Notes. ~500 lines of Jinja.
- Each skill row has a "Roll" button. Click → builds `1d6 × (attr+skill)`
  pool, fires through `app/dice/pool.py`, posts to roll log.
- **Push roll** UX: after a failed roll the roll-log card has a "Push"
  button. Click → re-roll non-6 dice, player picks one Condition to mark
  (chip-toggle popover).
- No multiclass, no subclass, no spells.

### Static files

- `app/systems/vaesen/static/sheet.js` ~150 lines: roll buttons, condition
  toggles, talents add/remove.
- No curated data tables. No Open5e integration.

### Acceptance criteria for Phase 3

- Create a Vaesen campaign → create a character with Archetype="Hunter"
  → roll Vigilance (attr Precision 3 + skill Vigilance 2 = 5d6 pool).
- Roll log shows "3 successes" not "12" or "1d6+5".
- Marking a Condition adds a `-1` modifier visible in subsequent rolls
  on the affected attribute.
- Push roll button re-rolls non-6s and forces a condition pick.
- The D&D 5e sheet on a different campaign is unaffected.

## 7 — Phase 4: V:tM v5 (target ~3–4 days)

The biggest of the three new systems but still simpler than D&D 5e.
Builds on the dice-pool foundation from Phase 3 with the Hunger
mechanic on top.

### Sheet shape

Bigger than Vaesen because of stat count. Highlights:

```python
V5_TEMPLATE = {
    # Identity
    "concept": "", "ambition": "", "desire": "",
    "predator_type": "",
    "clan": "",                          # Brujah / Gangrel / ... / Thin-Blood / Caitiff
    "sire": "", "generation": 13,
    "chronicle": "", "touchstones": [],
    # 9 Attributes (3 physical + 3 social + 3 mental)
    "attributes": {
        "strength": 1, "dexterity": 1, "stamina": 1,
        "charisma": 1, "manipulation": 1, "composure": 1,
        "intelligence": 1, "wits": 1, "resolve": 1,
    },
    # 27 Skills, each 0-5
    "skills": { ... },                   # full PHB-V5 list
    # Health: superficial + aggravated boxes
    "health": {"max": 5, "superficial": 0, "aggravated": 0},
    # Willpower: same shape
    "willpower": {"max": 4, "superficial": 0, "aggravated": 0},
    "hunger": 1,                         # 0-5
    "humanity": 7,                       # 0-10
    "stains": 0,
    # Disciplines — list of {discipline, level, powers: [...]}
    "disciplines": [],
    "advantages": [],                    # merits/flaws/loresheets
    "convictions": [],
    "notes": "",
}
```

### Dice engine: V5 pool

Extend `app/dice/pool.py` with V5 rules in `app/dice/v5.py`:

- Pool of N d10s, of which `hunger` of them are Hunger dice (red).
- Success = die showing 6+.
- Critical: pair of 10s → 4 successes (not 2). Pairs of 10s with at
  least one Hunger 10 → **Messy Critical** (success but with cost).
- Hunger 1 → **Bestial Failure** if the roll fails OR has a Hunger 1.
- Result shape:
  ```python
  {mode: 'v5-pool', successes: 5, crits: 1,
   hunger_results: [10, 8, 1, 3, 5],
   regular_results: [10, 6, 4, 7, 9],
   messy_critical: True, bestial_failure: False}
  ```

### Sheet ↔ dice tray coupling

The dice tray needs to know the active character's current Hunger value
when assembling a V5 pool. Simplest design: when the player clicks a
skill's Roll button on their V5 sheet, the click handler reads
`sheet.hunger` and passes it as a `hunger=` query param to the roll
endpoint. The roll endpoint forwards to `app/dice/v5.py`.

For ad-hoc rolls from the tabletop dice tray (not from a sheet), the
tray needs a "Hunger" input field that defaults to the controlling
character's current hunger.

### Acceptance criteria for Phase 4

- Create a V:tM campaign → create a Brujah character with Strength 3,
  Brawl 2, Hunger 2 → click Brawl roll → 5d10 pool with 2 red Hunger
  dice. Roll log shows successes, hunger dice values, and any
  Messy Critical / Bestial Failure flags.
- Health damage track works: clicking a Superficial box marks it; when
  Superficial fills, additional damage converts to Aggravated.
- Hunger 5 + Bestial Failure shows the appropriate warning in the
  roll-log card.
- Disciplines list can be added/edited (simple JSON-textarea fallback
  is fine for v1 — automation deferred).

## 8 — Cross-cutting concerns (don't forget)

These get harder the longer they're deferred. Plan to address each at
the phase where they first matter.

1. **Roll log polymorphism (Phase 2).** Every roll-card renderer (full
   tabletop, popped-out window, mini-sheet) currently reads `r.total`.
   When pool results land, that field is still present (= total dice
   count, not really useful), but the user-facing label changes to
   "N successes". The card renderer needs a small `_renderRollBody(r)`
   switch on `r.mode`.

2. **Mini-sheet flavoring (Phase 3+).** `app/templates/tabletop.html`'s
   player drawer currently shows D&D-shaped controls (HP bar, AC/Speed,
   Hit Dice, Short/Long Rest, Ability + Skill grid). For Vaesen the
   mini-sheet should show Conditions checkboxes; for V:tM it should
   show Health + Willpower tracks + Hunger. Plan: make the mini-sheet
   a per-system Jinja partial — `app/systems/<key>/templates/_mini_sheet.html`
   included from `tabletop.html` based on `campaign.game_system`.

3. **Concentration tracker.** Currently D&D-shaped (a single spell
   slot you concentrate on). V5 has its own "Activated Discipline"
   concept that's conceptually similar. Vaesen has nothing similar.
   Move into `app/systems/dnd5e/` for now; revisit if V5 wants it.

4. **Character preset system.** Currently `app/character_presets.py`
   serves D&D presets globally. Per-system: each system's `presets.py`
   returns its own list; the New Character form lists presets matching
   the chosen campaign's system.

5. **Open5e is D&D-only.** All `/api/open5e/*` endpoints, the local
   mirror, the curated tables (`dnd5e_subclass_spells.js`,
   `dnd5e_class_resources.js`, `dnd5e_innate_defenses.js`,
   `open5e_coverage.js`), and `_open5e_to_dnd5e_sheet` all move into
   `app/systems/dnd5e/`. Vaesen and V:tM have no equivalent external
   data source — both ship inline data (clans, archetypes, etc.) in
   their own `app/systems/<key>/data/`.

## 9 — Risks / things likely to bite

- **`tabletop_routes.py` extraction is the riskiest single edit.**
  6800 lines, lots of shared helpers (`_user_is_gm`, `_class_slug`,
  `_heal_claims`, etc.). Plan: keep shared helpers in
  `tabletop_routes.py`, import into each system's router. Use a
  `routes_dnd5e.py` intermediate file as a refactor checkpoint before
  the full move.
- **WebSocket message types are D&D-flavored.** Types like `spell_cast`,
  `spell_slot_update`, `transform_update`, `feature_used`,
  `resource_update`, `heal_applied`, `concentration_update` are all
  D&D-only. V5 will want different messages (`v5_pool_rolled`,
  `hunger_changed`, `health_damage_applied`). The WS hub is system-
  agnostic; only message *contents* differ. Each system's frontend
  module subscribes to its own message types — no central message-type
  registry needed.
- **`sheet.js` is mixed.** Some pieces are universal (form save,
  collapsible fieldsets, name/race fields), most are D&D-specific
  (multiclass roster, subclass picker, HP rolls, defenses chips,
  resources panel, feature grants). Splitting cleanly will be tedious;
  budget extra time in Phase 1 for this specifically.
- **Tabletop UI assumes a sheet template per character.** The map
  rendering, tokens, dice tray, drawer panels all work fine across
  systems. The thing that breaks per-system is the mini-sheet markup
  (covered in §8.2) and any GM-only tools that import monsters from
  Open5e (D&D-only).
- **Dice tray UI lives in `tabletop.html`.** The expression input is
  free-form. For V5 we'll want a "Hunger" companion input near the
  expression box. For Vaesen we'll want a "Push" affordance after a
  failed roll. Each system gets a partial in
  `app/systems/<key>/templates/_dice_tray.html` included by
  `tabletop.html` based on `campaign.game_system`.

## 10 — Open questions to resolve before starting

1. **Is the static-file mount tolerable as `/static/dnd5e/sheet.js`?**
   That breaks any existing `<script src="/static/sheet.js">` references.
   Two options: (a) bite the bullet and update every reference (clean);
   (b) keep a compatibility redirect at `/static/sheet.js` →
   `/static/dnd5e/sheet.js` for one release. Recommend (a) — the diff
   is mechanical.
2. **Does `Character.template` need to support per-system migrations?**
   Likely yes long-term, but for v1 the per-system normalize function
   handles JSON-shape changes idempotently. Defer migration story.
3. **Do we want a `/api/system/<key>/...` URL prefix** for system-
   specific endpoints? E.g. `/api/system/dnd5e/cast_spell` vs the
   current `/api/campaign/{id}/cast_spell`. Probably yes for clarity
   but it's a public-URL break. Recommend keeping current URLs and
   organizing only at the *code* level — i.e., D&D routes live in
   `app/systems/dnd5e/routes.py` but the route paths don't change.
4. **Does Vaesen / V:tM need a beast / NPC importer like Open5e?**
   Neither has a Pathbuilder-style external SRD. For now, each system
   ships a "create custom statblock" form. Re-evaluate after Phase 4.
5. **Plugin discovery: scan vs. explicit registration?** Recommend
   explicit registration in `app/systems/__init__.py` — `from .dnd5e
   import SystemModule as Dnd5eModule` etc. — no filesystem magic.
   Adding a new system means one import + one entry in `SYSTEMS`.

## 11 — Recommended order of work

```
Phase 1   (~1 day)  → File reorg, no behavior change            ▢ Ready to start
Phase 2   (~1 day)  → Dice engine refactor + RollResult         ▢
Phase 3   (~2 days) → Vaesen end-to-end                         ▢
Phase 4   (~3-4 days) → V:tM v5                                 ▢
```

Each phase ships as its own version bump. Phase 1 is a MAJOR or MINOR
bump depending on whether external code paths break (probably MINOR if
we keep public URLs stable). Phase 2 is MINOR. Phase 3 and 4 are each
MINOR (new feature: a new game system).

## 12 — What this plan deliberately doesn't do

- No third-party plugin system (`pip install simplevtt-system-pf2e`).
- No per-system DB tables — sheets stay in the JSON `Character.sheet`
  column.
- No live cross-system play (a single campaign is one system).
- No automation of V:tM disciplines or Vaesen talents — those are
  free-text for v1.
- No Open5e equivalent for V:tM or Vaesen — data ships inline.

These can come later. Don't pre-build for them.
