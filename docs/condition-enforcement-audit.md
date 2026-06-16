# Condition enforcement audit — Charmed / Grappled / Incapacitated

**Status:** Reference audit, written for v2.384.0 (2026-06-16).
**Audience:** Contributors planning to close the partial-enforcement gaps the v2.383.0 SRD audit surfaced.

## Why this doc exists

The v2.383.0 ground-truth SRD audit found that the TODO.md "Conditions ~85%" headline papers over a more nuanced state: all 15 SRD conditions have **data + buff templates + at least one read site**, but **per-clause RAW enforcement varies in completeness**. This doc walks the three most-cited partially-enforced conditions (Charmed, Grappled, Incapacitated) clause-by-clause, citing the existing enforcement points and the filed gaps. Subsequent commits can pick individual clauses off this list and ship narrow per-clause fixes.

Not in scope: Deafened (mostly narrative-only RAW), Exhaustion (separately tracked via `/set_exhaustion` and exhaustion-levels plan, already ~95% enforced). Out-of-scope per the v2.383.0 audit: charmed/frightened (immunity reads at lines 1054/1067/1551 are correct — Aura of Devotion).

---

## Charmed (RAW PHB p.290)

**Clause 1: "A charmed creature can't attack the charmer or target the charmer with harmful abilities or magical effects."**

- **State:** ⚪ **filed.** The buff template's `effects` field at `tabletop_routes.py:25387–25397` is a descriptive list of strings (lair-action shape) — not a structured dict the engine reads. No grep match for "charmer" being checked at `/attack` or `/cast_spell` time. A GM playing strict RAW today has to remember + reject the player's attack.
- **Read site needed:** `/attack` + `/use_attack` + `/cast_spell` (when targeting an attack/harmful spell). Pattern: check the attacker's buffs for `key == "charmed"`, look up the buff's `source_char_id`, return 409 `charmed_cannot_target_charmer` when the target_char_id matches.
- **Existing scaffolding:** `_install_buff` already records `source_char_id` on the buff. The charmed buff would just need the structured `effects.charmer_char_id` field + the gate check at the three sites.

**Clause 2: "The charmer has advantage on any ability check to interact socially with the creature."**

- **State:** ⚪ **GM-narrated.** SimpleVTT has no social-check engine site (Persuasion / Deception / etc. are descriptive only — the dice are rolled but the engine doesn't compute social outcomes). This clause is filed as out-of-scope until a social-check substrate lands.

---

## Grappled (RAW PHB p.290)

**Clause 1: "A grappled creature's speed becomes 0, and it can't benefit from any bonus to speed."**

- **State:** ✅ **enforced** via `effects.speed_reduction_ft = base_speed` in `_make_grappled_buff` at `tabletop_routes.py:33484–33493`. The `effective_speed_walk` helper at `app/content/effective_speed.py:98` reads this reduction and clamps to 0. A Longstrider +10 bonus would still apply, but the reduction (equal to base + 10 with bonus) keeps the net at 0. **Functionally correct.**
- **Note:** The "can't benefit from any bonus" RAW clause is honored mechanically (the clamp to 0 makes any positive bonus irrelevant), even though the architecture doesn't explicitly suppress the bonus. Filed as "enforced by side-effect" rather than literal clause check; no follow-up needed unless a future bonus type bypasses the additive model.

**Clause 2: "The condition ends if the grappler is incapacitated."**

- **State:** ⚪ **filed.** The `raw_effects[]` array at `tabletop_routes.py:33401` documents this RAW clause, but no engine hook auto-ends the grappled buff when the grappler becomes incapacitated. Today the GM `/end_buff`s the grappled buff manually when the grappler drops to 0 HP, is paralyzed, etc.
- **Hook needed:** A buff-install side-effect: whenever a buff with `incapacitated` semantics is installed on a creature (lookup against `_INCAPACITATED_KEYS` at line 1906), scan all combatants for `grappled` buffs whose `source_char_id` matches the newly-incapacitated combatant and auto-`/end_buff` them. The set of incapacitating buff keys is already canonical (`hideous-laughter`, `stunned`, `paralyzed`, `unconscious`, `petrified`, the generic `incapacitated`).

**Clause 3: "The condition also ends if an effect removes the grappled creature from the reach of the grappler."**

- **State:** ⚪ **GM-narrated.** Movement-based clauses are filed — the engine doesn't track "the grappler's reach" as a moving quantity. Future Reach-aware movement substrate would close this; not a priority.

---

## Incapacitated (RAW PHB p.290)

**Clause 1: "An incapacitated creature can't take actions or reactions."**

- **State:** 🟡 **partial.**
  - ✅ Concentration drops when incapacitated: `tabletop_routes.py:965, 989, 2343`.
  - ✅ Cleansing Touch (Paladin Lv 14) can end charmed/frightened/etc.: `tabletop_routes.py:274–279`.
  - ⚪ **Opportunity attacks specifically don't check incapacitated.** Comment at `tabletop_routes.py:3259–3260`: *"v1 doesn't check the incapacitated buff; filed."* So an incapacitated creature whose space a hostile creature exits *can* still trigger an opportunity attack — wrong RAW.
  - ⚪ **General action / reaction gate.** The action-economy gate (`_mark_battle_economy`) tracks whether an action/bonus/reaction has been spent but doesn't reject the attempt outright when the actor is incapacitated. Today an incapacitated character can `/use_attack` and the engine fires the attack normally. The gate would need an early `is_incapacitated(combatant)` check that returns 409 `incapacitated`.

**Hook needed for the opportunity-attack + action-gate clauses:** A shared `_combatant_is_incapacitated(c: dict) -> bool` helper that checks the combatant's buff list against `_INCAPACITATED_KEYS` (line 1906). Three call sites:

1. `/use_attack` + `/cast_spell` + `/use_feature` — pre-action-economy gate: if incapacitated, 409 with `error: "incapacitated"`.
2. `/use_attack` reaction branch (opportunity attacks) — same gate per the `tabletop_routes.py:3259–3260` filed note.
3. `/next_turn` — no gate (incapacitated still consumes the turn slot RAW; their turn just has no actions).

---

## Suggested per-clause shipping order

Ordered by leverage × scope:

1. **Incapacitated → opportunity-attack gate (small):** closes the explicit filed comment at line 3260. One helper + one site. Probably 30-line PR + 2 harness tests.
2. **Incapacitated → general action gate (medium):** the helper from #1 + checks at `/use_attack`, `/cast_spell`, `/use_feature`. ~50-line PR + 3-4 tests. Affects normal play (incapacitated PCs can't attack).
3. **Grappled → ends on grappler incapacitated (medium):** install-side-effect on the incapacitating buffs. Uses the same `_INCAPACITATED_KEYS` set as #1/#2 + a sweep over the campaign's combatants. ~40-line PR + 2 tests.
4. **Charmed → can't target charmer (medium):** new structured `effects.charmer_char_id` field on the charmed buff + 3-site gate. ~60-line PR + 3 tests. Requires updating existing charmed-buff installs to populate the new field.

**Total estimated:** 4 commits, ~180 lines net, ~11 harness tests. Closes the per-clause Charmed/Grappled/Incapacitated gaps.

---

## Out-of-scope

- **Charmed clause 2** (advantage on social checks) — no social-check substrate exists.
- **Grappled clause 3** (ends on out-of-reach movement) — no Reach-aware movement substrate.
- **Deafened** — RAW is mostly "can't hear" narrative; the only mechanical clause is "auto-fail any ability check requiring hearing" which is GM-narrated by design.

These three clauses are filed as future-3.x or out-of-scope per the v2.383.0 audit's "polish + UX" + "3.0 scope expansion" tracks.

## Related docs

- [SRD 5e Audit (v2.382.0 refresh)](../TODO.md#srd-5e-audit-v23820-refresh) — the audit that surfaced the partial-enforcement question.
- [`condition_impacts.py`](../app/content/condition_impacts.py) — the descriptive condition-effect strings (the data layer this doc audits enforcement of).
- [`exhaustion-levels.md`](plans/exhaustion-levels.md) — the parallel condition Exhaustion already has a dedicated tracker.
