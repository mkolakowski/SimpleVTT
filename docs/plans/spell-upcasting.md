# Spell Up-casting — three ways to cast a spell with a higher-level slot

Up-casting is D&D 5e's rule that casting a spell with a slot **above its base
level** strengthens it — Magic Missile at 3rd level throws 4 darts instead of 3,
Fireball at 4th deals 9d6 instead of 8d6, Cure Wounds at 2nd heals 2d8 + mod.
This doc audits how SimpleVTT handles up-casting **today**, then proposes **three
distinct ways** to let users up-cast, with a recommended phased rollout.

> **Scope note.** This is a design doc (the [TODO](../../TODO.md) item asked to
> "plan three ways"). Nothing here is implemented yet beyond the pieces called
> out as already-shipped in the audit. Each approach below ends with concrete
> file touches so a future commit can pick one up.

## Status snapshot

| Phase | Subject | Status | Lands in |
|-------|---------|--------|----------|
| Audit | How up-casting works today | ✅ documented (this doc) | — |
| A | UI slot-picker over the existing `slot_level` plumbing | ✅ shipped (full sheet + mini-sheet) | v2.108.0 / v2.109.0 |
| B | Structured `upcast` scaling data + a generic resolver | ⚪ design only | TBD |
| C | GM-adjudicated free-text up-cast (always-available fallback) | ✅ shipped (rule text in picker + broadcast) | v2.108.0 |

## What already works today (the audit)

The server is **further along than the UI**. Grounding references:

- **`POST /api/campaign/{cid}/cast_spell` already accepts `slot_level`**
  ([`tabletop_routes.py:16030`](../../app/routes/tabletop_routes.py)). It
  validates `slot_level >= spell.level`, consumes a slot **at the chosen
  level**, and several per-spell endpoints (Hold Person, Hold Monster, Flesh to
  Stone, …) read it to scale (e.g. Hold Person max-targets = `slot_level - 1`).
- **Count-scaling is automated** via two structured spell fields the resolver
  reads today:
  - `extra_targets_per_slot_above_base` — Magic Missile-style (one more dart per
    slot above base). Wired in the cast resolver + the multi-target picker.
  - `extra_beams_per_slot_above_base` — Scorching Ray-style (one more beam per
    slot above base).
- **Cantrip scaling by *character* level** (Fire Bolt 1d10 → 2d10 → 3d10 → 4d10
  at L1/5/11/17) is handled by `_pick_damage_tier` reading `damage_scaling`.
  This is **independent of slots** and out of scope for up-casting (cantrips
  have no slot to up-cast), but it's the proof that tiered scaling data + a
  resolver hook already exist.

### What does NOT work today

- **No slot-picker in the UI.** The sheet cast button and the init-tracker
  mini-sheet always cast at the spell's **base** level — `slot_level` is never
  surfaced to the player ([`_tab_spells.html:130`](../../app/templates/_tab_spells.html)).
  So even the already-automated count-scaling (extra darts/beams) is
  unreachable from the client.
- **Dice up-scaling is not automated.** The `UpcastEntry` schema exists
  (`slot_level` / `damage` / `healing` / `extra_targets`,
  [`action_schema.py:56`](../../app/action_schema.py)) but the `upcast: []`
  array is **empty on every SRD spell**. Fireball (+1d6/slot), Cure Wounds
  (+1d8/slot), etc. carry their up-cast rule **only in the free-text
  `higher_level` string** — nothing parses it, so the dice never grow.

### Up-cast behavior taxonomy (representative audit)

Every up-castable spell falls into one of these buckets. The bucket decides
which approach can automate it:

| Bucket | Example spells | How it scales | Structured today? |
|--------|----------------|---------------|-------------------|
| **+N targets/projectiles** | Magic Missile, Scorching Ray, Eldritch Blast*, Hold Person/Monster | +1 dart / beam / target per slot above base | ✅ `extra_targets_per_slot_above_base` / `extra_beams_per_slot_above_base` |
| **+dice damage** | Fireball, Burning Hands, Shatter, Scorching Ray (dmg/beam) | +Nd_X per slot above base | ❌ free-text `higher_level` only |
| **+dice healing** | Cure Wounds, Healing Word, Mass Healing Word | +Nd8 per slot above base | ❌ free-text only |
| **+duration / area / level-cap** | Spiritual Weapon, Spirit Guardians (no scale), Sleep (+2d8 HP pool), Sleep/Command targets | varies — extra HP dice, bigger area, higher CR cap | ❌ mostly free-text |
| **No up-cast effect** | Bless, Bane, most utility | unchanged; the slot just buys a higher-level cast | n/a |

\* Eldritch Blast is a cantrip — scales by character level, not slot.

**The pivotal finding:** structured data exists for the *count* bucket and is
already wired; the *dice* buckets (the bulk of "feels broken" up-casts like
Fireball) need either new structured data (Approach B) or human adjudication
(Approach C). Approach A unlocks the count bucket immediately and is the
prerequisite UI for B and C.

## The three approaches

### Approach A — UI slot-picker over the existing plumbing

**Idea.** Add a slot-level chooser to the cast flow. When a spell has up-cast
potential and the caster has a higher slot available, show a small picker
(base level pre-selected, higher levels listed with remaining-slot counts).
The chosen `slot_level` is already honored by `/cast_spell` and the
count-scaling resolver, so this immediately makes Magic Missile-at-L3 (4 darts)
and Scorching Ray-at-L3 (4 beams) work end to end, and correctly **consumes the
higher slot** for every spell.

**Feasibility: ✅ high.** Server side is done; this is a client-only change plus
a tiny "what slots can this be cast at" computation.

**Limitations.** Dice spells (Fireball) consume the right slot but don't grow
their dice yet — that waits for B or C. Pairs naturally with C as the
stopgap (show the `higher_level` text next to the picker).

**File touches**

| File | Change |
|------|--------|
| `app/templates/_tab_spells.html` | Add a slot `<select>` (or +/- stepper) on the cast button for leveled spells; default = base level; options = base…highest available slot with counts. |
| `app/static/sheet.js` (+ `tabletop.js` mini-sheet) | Read the chosen level; pass `slot_level` to `/cast_spell`; refresh remaining-slot counts after the cast's `spell_slot_update` broadcast. |
| `app/routes/tabletop_routes.py` | (Optional) a tiny `/api/.../spell/{idx}/upcast_options` helper, or compute client-side from the sheet's `spell_slots`. |

**Acceptance criteria**
- Casting Magic Missile at L3 consumes an L3 slot and fires 4 darts.
- Casting any leveled spell at L_n consumes an L_n slot; the picker hides levels
  with 0 remaining slots and never offers below the spell's base level.
- The mini-sheet (GM NPC cast) path is unaffected (NPCs have no slots).

### Approach B — Structured up-cast scaling data + a generic resolver

**Idea.** Populate the existing `UpcastEntry`/scaling fields with a per-slot
formula (`damage_per_slot: "1d6"`, `healing_per_slot: "1d8"`,
`extra_targets_per_slot_above_base: 1`) on the SRD spells, and extend the cast
resolver to add `(slot_level - base) × per_slot` dice to the rolled damage /
healing. Reuses the dice roller + the chat-card breakdown already in place.

**Feasibility: ⚠️ medium.** The resolver hook is small (mirror the existing
count-scaling block at [`tabletop_routes.py:16967`](../../app/routes/tabletop_routes.py)),
but it requires a **data backfill** across the SRD spell JSON. Two ways to
source the formula:
1. **Curated** — hand-author `damage_per_slot` / `healing_per_slot` for the
   ~40 commonly up-cast spells (high accuracy, bounded effort).
2. **Parsed** — regex the `higher_level` text ("increases by 1d6 for each slot
   level above 3rd") into the structured field at import time
   ([`monster_action_parse.py`](../../app/content/monster_action_parse.py) is the
   precedent for desc-parsing). Lower effort, but fragile on phrasing variants.

**File touches**

| File | Change |
|------|--------|
| `app/action_schema.py` | Add `damage_per_slot` / `healing_per_slot` (or fully populate `UpcastEntry`); keep back-compat with the existing count fields. |
| `app/data/local/dnd5e/spells/*.json` | Backfill the per-slot formula for the +dice buckets (curated and/or parsed). |
| `app/content/spell_*` (importer) | If parsed: extract `higher_level` → structured field. |
| `app/routes/tabletop_routes.py` | In the cast damage/heal resolution, add `(slot_level - base) × per_slot` dice; surface the up-cast addition in the chat-card breakdown. |
| `tests/harness/test_*` | Fireball L4 = 9d6 (vs 8d6 at L3); Cure Wounds L2 heals 2d8 + mod. |

**Acceptance criteria**
- Fireball at L4 rolls 9d6; at L5 rolls 10d6; the chat card shows the up-cast dice.
- Cure Wounds at L2 heals 2d8 + spellcasting mod.
- Spells with no `*_per_slot` data fall through to Approach C (no false scaling).

### Approach C — GM-adjudicated free-text up-cast (the universal fallback)

**Idea.** For any spell (especially the long tail B doesn't cover), surface the
spell's `higher_level` text in the cast picker and on the resulting chat card,
consume the chosen slot, and let the GM/player apply the extra effect manually
(e.g. type the bonus damage into the target's HP, or roll the extra dice with
the dice roller). Zero per-spell data; universal coverage; never wrong because a
human decides.

**Feasibility: ✅ high, ⚙️ low automation.** Essentially "Approach A + show the
rule text." It's the safety net that makes up-casting *usable* for 100% of
spells the day A ships, with B incrementally replacing manual steps for the
common spells.

**File touches**

| File | Change |
|------|--------|
| `app/templates/_tab_spells.html` / `tabletop.html` | When a higher slot is picked, render the spell's `higher_level` text inline in the picker + pass it onto the cast chat card. |
| `app/routes/tabletop_routes.py` | Echo `higher_level` + the chosen `slot_level` on the `spell_cast` broadcast so the card can show "Cast at L4 — +1d6 damage per slot above 3rd (apply manually)." |
| `tests/harness/test_*` | The `spell_cast` broadcast carries `slot_level` + `higher_level` when up-cast. |

**Acceptance criteria**
- Up-casting any leveled spell consumes the chosen slot and shows its
  `higher_level` rule on the chat card.
- No spell is silently mis-scaled; the human applies what isn't automated.

## Recommended rollout

1. **Approach A first** — unlocks the slot-picker (the missing UI) + the
   already-automated count scaling, and consumes slots correctly for *every*
   spell. Highest leverage, lowest risk.
2. **Approach C alongside A** — show `higher_level` text so dice spells are
   immediately usable (GM applies the bonus). A + C together is a complete,
   honest up-cast experience with no per-spell data.
3. **Approach B incrementally** — backfill `*_per_slot` for the common +dice /
   +heal spells (Fireball, Cure Wounds, Burning Hands, Shatter, Healing Word…)
   so the manual step from C disappears for the spells players up-cast most.

This staging means up-casting is *useful from day one* (A + C) and gets *more
automated over time* (B), rather than blocking on a full SRD data backfill.

## Open questions

- **Per-slot formula source** (B): curated vs. parsed-from-`higher_level`? A
  hybrid (parse, then hand-correct the misses flagged by a validation pass —
  see the [spell-validation suite plan](spell-validation-suite.md)) is likely best.
- **Sorcery Points / Metamagic interplay**: Empowered/Heightened operate on the
  cast result; up-casting changes the dice count first. Order: pick slot →
  resolve up-cast dice → apply metamagic. See
  [Sorcery Points + Metamagic](sorcery-points-and-metamagic.md).
- **Warlock Pact Magic**: all slots are the same (highest) level — up-casting is
  automatic for warlocks; the picker should reflect that (only one slot level
  offered).
- **Healing word / bonus-action spells** + the action-economy gate: no special
  handling needed; the slot picker rides the existing cast flow.
