# Conjure family — summon-catalog (status: ✅ SHIPPED)

**Status:** ✅ **SHIPPED — all six SRD `conjure-*` spells have cast endpoints.** Filed v2.538.0 as a "design plan" under the mistaken premise that the family was unwired; **corrected v2.538.1** to this status/reference doc after discovering the work was already done via [movement-and-summons.md](movement-and-summons.md) Phase 7 + the v2.414.0–v2.420.0 multiplier-family arc.
**Foundation:** [movement-and-summons.md](movement-and-summons.md) (the `_summon_companion` substrate) + the v2.414.0 slot-multiplier helper.

> **Lesson (for future-me):** the cast-and-broadcast-tail plan listed "the Conjure family (summon-catalog depth, filed separately)" as if pending. It was already shipped. **Grep `async def cast_<spell>` before writing a new cast endpoint** — `_verify-substrate-before-proposing_` applies to whole arcs, not just single substrates.

---

## What shipped (and where)

All six endpoints live in `app/routes/tabletop_routes.py` and stand up
`count` real summon combatants (token + init slot + HP/AC + the
damage/HP/move pipeline) via `_summon_companion`, tagged `is_summon` +
`concentration_bound` so the v2.113.0 `_drop_paired_concentration_buffs`
cascade dismisses the pack when the caster's concentration breaks.

| Spell | Endpoint | Shipped |
|---|---|---|
| Conjure Animals | `POST /cast_conjure_animals` | v2.99.443 (Phase 7.2); upcast v2.414.0 |
| Conjure Woodland Beings | `POST /cast_conjure_woodland_beings` | v2.415.0 |
| Conjure Minor Elementals | `POST /cast_conjure_minor_elementals` | v2.416.0 |
| Conjure Elemental | `POST /cast_conjure_elemental` | v2.418.0 |
| Conjure Fey | `POST /cast_conjure_fey` | v2.419.0 |
| Conjure Celestial | `POST /cast_conjure_celestial` | v2.420.0 |

**Upcast scaling** rides the shared `_spell_summon_multiplier_for_slot(spell_slug, slot_level, default_multiplier=N)`
helper — a higher slot multiplies the summon count (e.g. Conjure
Animals' base 2 → 4 at L5, 6 at L7, 8 at L9).

**Stat blocks** come from the hardcoded `_COMPANION_TEMPLATES` registry
(e.g. the `wolf` entry — AC 13 / HP 11 / 40-ft speed). The summoned
creatures' turns are GM-driven through the standard NPC-combatant path
(`/npc_attack` etc.), per the movement-and-summons non-goals.

**Tests:** `tests/harness/test_cast_conjure_*.py` (7 files, 38 tests) —
spawn counts, upcast multipliers, the class gate, and dismissal.

---

## Remaining follow-ups (filed, not blockers)

- **Catalog-backed summon** — today the conjure endpoints summon from
  `_COMPANION_TEMPLATES` (a curated set), not the full 322-record monster
  catalog. A `_summon_companion(template=…)` override built from a
  monster's SRD JSON (HP/AC/speed/size/type/CR) by slug would let a
  caster pick *any* catalog creature within the spell's type + CR tier.
  **Conjure Animals shipped it v2.539.0** — `/cast_conjure_animals`
  takes an optional `beast_slug` to summon any catalog beast within the
  count's CR tier, via `_monster_summon_template` + a
  `_summon_companion(template=…)` override + the shared
  `_conjure_catalog_summon_template` validator. **Woodland Beings + Minor Elementals shipped it v2.540.0** (fey /
  elemental pools via `creature_slug`). The single-summon conjures
  (Elemental / Fey / Celestial — one creature of CR ≤ spell level) are a
  different validation shape, still a filed follow-up.
- **Random-creature RAW variant** (roll the pool) — GM-narrated today.
