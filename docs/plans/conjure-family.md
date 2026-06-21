# Conjure family — summon-catalog Design Plan

**Status:** ⚪ design only · Phase 1 unstarted (filed v2.538.0)
**Parent / foundation:** [movement-and-summons.md](movement-and-summons.md) (the shipped `_summon_companion` substrate) + the cast-and-broadcast tail ([cast-and-broadcast-tail.md](cast-and-broadcast-tail.md), Find Steed #2 v2.441.0 is the single-summon precedent).
**Motivating spells:** the six SRD `conjure-*` spells the tail filed as "summon-catalog depth, separate work" — Conjure Animals, Conjure Woodland Beings, Conjure Minor Elementals, Conjure Elemental, Conjure Fey, Conjure Celestial.
**Related code:** `app/routes/tabletop_routes.py` — `_summon_companion`, `_COMPANION_TEMPLATES`, `_drop_paired_concentration_buffs` (concentration teardown cascade), `cast_find_steed`; `app/data/local/dnd5e/monsters/*.json` (322 records) via `local_content.resolve(slug, type="monsters")`.

---

## Goal

Wire the SRD Conjure spells, which summon **one or more catalog
creatures of a chosen type within a CR tier**. Unlike Find Steed (#2 —
five hardcoded `_COMPANION_TEMPLATES` steeds), the Conjure family draws
from the whole monster catalog, so the substrate gap is a
**catalog-backed summon**: build a companion stat block from a monster's
SRD JSON (HP / AC / speed / size / type / CR) at cast time, validate it
against the spell's type + CR-tier + count table, and spawn N
concentration-bound summons through the existing `_summon_companion`
path.

---

## 1. What already works (verified v2.538.0)

All in `app/routes/tabletop_routes.py` unless noted.

- **`_summon_companion(...)`** stands up a summoned creature as a REAL
  combatant: NPC `Token` on the active map (`token_add`), a combatant
  dict (HP/AC/speed/size ride on the dict — no `TokenTemplate` row),
  appended to the battle (`battle_update` + `force_gm_sync`), tagged
  `is_summon` + `summoned_by` + `concentration_bound`. Reuses the damage
  / HP pipeline + `_force_move` for free. Off-grid → combatant with no
  token. **Today it reads the stat block from `_COMPANION_TEMPLATES` by
  key** — the one extension Phase 1 needs (an inline-template override).
- **Concentration teardown** — `_drop_paired_concentration_buffs` drops
  every `is_summon` + `concentration_bound` combatant the caster summoned
  when their concentration ends (line ~4549). So a concentration-bound
  conjure is dismissed RAW-correctly on break / death / re-cast for free.
- **`cast_find_steed`** is the single-summon precedent: gate → resolve a
  template → `_summon_companion(concentration_bound=True)` → broadcast.
  The Conjure endpoints mirror it but loop N times over a catalog slug.
- **Monster catalog** — `local_content.resolve(slug, type="monsters")`
  returns the SRD record: `name`, `size` ("Medium"), `type` ("Beast"),
  `challenge_rating` ("1/4"), `armor_class`, `hit_points`, `speed`
  ({walk: 40}). 322 records cover the beast / fey / elemental / celestial
  pools the Conjure spells draw from.

---

## 2. The new substrate (Phase 1)

Two small additions:

1. **CR parser** — `_parse_cr("1/4") → 0.25`, `_parse_cr("2") → 2.0`
   (handles `"1/8"`, `"1/2"`, integers). Used to gate the chosen
   creature against the spell's tier.
2. **Inline-template summon** — extend `_summon_companion` (or add a thin
   `_summon_from_monster_slug` wrapper) to accept a stat block built from
   a catalog record instead of `_COMPANION_TEMPLATES`. The wrapper:
   resolves the slug, projects `{name, hp, ac, speed_walk, size}` from the
   record, and calls the spawn path. Returns None for an unknown /
   wrong-type / over-CR slug so the endpoint can 400/409.

---

## 3. Phases

### Phase 1 — Conjure Animals (the demonstrator)

`POST /cast_conjure_animals`. Body: `{character_id, beast_slug,
count, x?, y?}`. Druid/Ranger gate. RAW count↔CR table (PHB p.225):

| count | max CR |
|---|---|
| 1 | 2 |
| 2 | 1 |
| 4 | 1/2 |
| 8 | 1/4 |

Validates: the slug resolves to a **Beast** whose CR ≤ the tier for the
chosen `count`; rejects (400) a non-beast / over-CR / unknown slug or a
`count` not in {1,2,4,8}. Spawns `count` concentration-bound summons of
the beast via the catalog-backed path; broadcasts one `feature_used`
summarizing the conjuration. Concentration, up to 1 hour. The "GM/DM
chooses the creatures" RAW nuance is satisfied by the caller passing the
slug (the table's house rule decides who picks).

**Test:** valid (4 × CR-½ wolves spawn as `is_summon` + `concentration_bound`
combatants); count/CR mismatch → 400; non-beast slug → 400; non-caster
→ 409; dismissal via concentration break drops them.

### Phase 2 — the rest of the family

One endpoint each, same shape, differing in the allowed creature **type**
+ CR table + class gate:

- **Conjure Woodland Beings** (Druid/Ranger) — fey, same count table as
  Animals.
- **Conjure Minor Elementals** (Druid/Wizard) — elementals, same table.
- **Conjure Elemental** (Druid/Wizard) — one elemental of CR ≤ spell
  level; concentration up to 1 hour.
- **Conjure Fey** (Druid/Warlock) — one fey of CR ≤ spell level.
- **Conjure Celestial** (Cleric) — one celestial of CR ≤ 4 (5 upcast).

A shared `_cast_conjure_pool(...)` helper parameterizes type + table so
each endpoint is a thin wrapper.

### Phase 3 — polish (filed)

Upcast scaling (more/higher-CR creatures per slot above base), the
random-creature RAW variant (roll the pool), and a per-summon name suffix
(`Wolf 1`, `Wolf 2`) for the init tracker. Dismissal already works via
the concentration cascade + `/dismiss_companion`.

---

## 4. Non-goals

- **Full monster action automation for summons** — summoned creatures
  ride the existing combatant damage/HP/move pipeline + `/npc_attack`
  for their attacks; bespoke monster-action wiring is out of scope (the
  GM drives their turns, as with any NPC combatant).
- **The summon's own spellcasting** (Conjure Fey's higher-CR options) —
  GM-narrated.

---

## 5. Test contract

Each phase ships harness tests asserting: a valid conjuration spawns the
right count of `is_summon` + `concentration_bound` combatants with
catalog-correct HP/AC; the count/CR/type validation rejects bad input
(400); the class gate rejects non-casters (409). Phase 1 also asserts the
concentration-break dismissal.

---

## 6. Closure criteria

Closes when all six Conjure spells have cast endpoints riding the
catalog-backed summon. Phase 3 polish items are filed follow-ups, not
closure blockers.
