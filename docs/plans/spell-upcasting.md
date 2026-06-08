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
| B | Structured `upcast` scaling data + a generic resolver | ✅ shipped (common +dice/+heal spells) | v2.110.0 |
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

### What's sparse today (the real gap — measured 2026-06-08)

The earlier draft of this section claimed "no slot-picker" and "dice
up-scaling is not automated." **Both shipped since** (A in v2.108.0/.109.0,
B in v2.110.0) — see the status snapshot above. The picker is live on the
full sheet ([`sheet_dnd5e.html:2653`](../../app/templates/sheet_dnd5e.html))
and the dice resolver runs in `/cast_spell`
([`tabletop_routes.py:16999`](../../app/routes/tabletop_routes.py)) via
`_scale_dice_for_upcast` reading `damage_per_slot` / `healing_per_slot`.

The remaining gap is **not mechanism — it's data coverage.** All three
scaling kinds work the moment a spell carries the structured field, but
almost no spells do:

| Structured up-cast field | Spells carrying it | of 319 |
|--------------------------|--------------------|--------|
| `damage_per_slot` / `healing_per_slot` (dice) | 14 | 4% |
| `extra_targets_per_slot_above_base` (instances) | 1 (Magic Missile) | <1% |
| `extra_beams_per_slot_above_base` (beams) | 1 (Scorching Ray) | <1% |

So **Magic Missile at L3 already fires 4 darts** (its action carries
`extra_targets_per_slot_above_base: 1`, wired at
[`tabletop_routes.py:17461`](../../app/routes/tabletop_routes.py)) — the
TODO's headline example is *already closed*. But Fireball, Cure Wounds,
Burning Hands, Shatter, etc. only scale if/when their per-slot field is
populated; the other ~300 spells carry their up-cast rule **only in the
free-text `higher_level` string**, which nothing parses, so the dice /
targets don't grow. The work that remains is the **backfill** (Approach
B's data half) — optionally driven by a `higher_level`-prose parser.

### Up-cast behavior taxonomy (representative audit)

Every up-castable spell falls into one of these buckets. The bucket decides
which approach can automate it:

| Bucket | Example spells | How it scales | Mechanism wired? | Data populated? |
|--------|----------------|---------------|------------------|-----------------|
| **+N targets/projectiles** | Magic Missile, Scorching Ray, Eldritch Blast*, Hold Person/Monster | +1 dart / beam / target per slot above base | ✅ `extra_targets_/extra_beams_per_slot_above_base` | ⚠️ 2 spells (Magic Missile, Scorching Ray) |
| **+dice damage** | Fireball, Burning Hands, Shatter | +Nd_X per slot above base | ✅ `damage_per_slot` + `_scale_dice_for_upcast` | ⚠️ ~10 of the 14 annotated |
| **+dice healing** | Cure Wounds, Healing Word, Mass Healing Word | +Nd8 per slot above base | ✅ `healing_per_slot` | ⚠️ ~4 of the 14 annotated |
| **+duration / area / level-cap** | Sleep (+2d8 HP pool), Hold Person/Monster (targets), Polymorph (CR cap) | varies — extra HP dice, bigger area, higher CR cap | 🟠 per-endpoint bespoke math; no generic field | n/a |
| **No up-cast effect** | Bless, Bane, most utility | unchanged; the slot just buys a higher-level cast | n/a | n/a |

\* Eldritch Blast is a cantrip — scales by character level, not slot.

**The pivotal finding:** every scaling *mechanism* now ships — the picker
(A), the dice resolver (B), the count/beam resolver, and the free-text
fallback (C). What's missing is **data**: only 16 of 319 spells carry any
structured up-cast field, so ~300 spells consume the higher slot correctly
but don't grow. The remaining work is therefore a **data backfill** (curated
+ a `higher_level` prose parser), not new engine code — plus generalizing the
bespoke per-endpoint "+targets/HP-pool" math (Sleep, Hold Monster) onto a
shared structured field so it stops being copy-pasted.

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

## Recommended rollout (revised 2026-06-08)

Approaches A (picker), B (dice resolver), and C (free-text fallback) **all
shipped** (v2.108.0–v2.110.0). What remains is closing the data gap so the
shipped mechanisms actually fire on more than 16 spells:

1. **Backfill the common +dice / +heal spells** — hand-author
   `damage_per_slot` / `healing_per_slot` on the ~40 most-up-cast spells
   (Fireball, Burning Hands, Shatter, Cure Wounds, Healing Word, Mass
   Healing Word, …). Each is a one-line JSON edit + a harness assertion
   (e.g. Fireball at L5 → `10d6`). Highest leverage, lowest risk.
2. **`higher_level`-prose parser** — `app/content/spell_upcast_parse.py`
   (sibling to `monster_action_parse.py`) extracts `"+Nd M"` and
   `"one more <thing> for each slot"` patterns into the structured fields
   at resolve time, with manual JSON winning over the parser. Closes the
   long tail without 300 hand edits. Gate low-confidence parses for review
   (see the [spell-validation suite](spell-validation-suite.md)).
3. **Generalize the bespoke +targets/HP-pool math** — migrate Sleep / Hold
   Person / Hold Monster off their per-endpoint constants onto a shared
   `upcast` param field so the rule lives in data, not code.

C (the `higher_level` text shown in the picker) already makes every spell
*honestly* up-castable today — the player applies what isn't yet automated.
This staging just shrinks that manual step spell-by-spell.

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
