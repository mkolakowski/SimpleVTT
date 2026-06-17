# Condition enforcement audit — Charmed / Grappled / Incapacitated

**Status:** Reference audit, written for v2.384.0 (2026-06-16). **Reconciliation refresh v2.400.2 (2026-06-17):** all four per-clause items on the suggested shipping order **shipped end-to-end v2.385.0 → v2.391.0**. The TODO.md Conditions row moved ~85% → ~92% on the strength of this sweep, and the only remaining ~8% is the three permanently-GM-narrated clauses listed under [Out-of-scope](#out-of-scope). This doc is now a historical record of how the gaps closed, not a punch list of open work.
**Audience:** Contributors looking up *how* a particular Charmed/Grappled/Incapacitated clause is enforced today, or referencing the per-clause shipping order as a template for future condition arcs.

## Why this doc exists

The v2.383.0 ground-truth SRD audit found that the TODO.md "Conditions ~85%" headline papered over a more nuanced state: all 15 SRD conditions had **data + buff templates + at least one read site**, but **per-clause RAW enforcement varied in completeness**. This doc walked the three most-cited partially-enforced conditions (Charmed, Grappled, Incapacitated) clause-by-clause, citing the existing enforcement points and the filed gaps. The v2.385.0–v2.391.0 sweep picked the four clauses off this list one commit at a time and closed each one with a narrow per-clause ship. The clause sections below mark each one ✅ shipped with the version reference.

Not in scope: Deafened (mostly narrative-only RAW), Exhaustion (separately tracked via `/set_exhaustion` and exhaustion-levels plan, already ~95% enforced). Out-of-scope per the v2.383.0 audit: charmed/frightened (immunity reads at lines 1054/1067/1551 are correct — Aura of Devotion).

---

## Charmed (RAW PHB p.290)

**Clause 1: "A charmed creature can't attack the charmer or target the charmer with harmful abilities or magical effects."**

- **State:** ✅ **shipped v2.390.0 + v2.391.0.** The gate reads the charmed buff's `source_char_id` (which `_install_buff` was already populating) and rejects the action with 409 `charmed_cannot_target_charmer` when the attacker is charmed by the target.
  - `v2.390.0 "The Charmer's Shield"` — `/attack` gate via `_attacker_is_charmed_by_target` helper at `tabletop_routes.py`.
  - `v2.391.0 "The Charmer's Wider Shield"` — mirrored onto `/cast_spell` (single-target harmful spells) at `tabletop_routes.py:19706`.
  - `/use_feature` is **not applicable** — the endpoint is structurally self-targeted (Action Surge, Channel Divinity buffs, Lay on Hands pool), so there's no `target_combatant_id` to gate against. The v2.399.2 audit-row reconciliation confirms this. The v2.390.2 install-site verification confirmed `source_char_id` is set on every realistic charm source (`tabletop_routes.py:19048` for spell-cast charms, `:2187` for item-action charms); lair-action installs from monster sources fundamentally can't carry a `source_char_id` and are GM-narrated by design.

**Clause 2: "The charmer has advantage on any ability check to interact socially with the creature."**

- **State:** ⚪ **GM-narrated.** SimpleVTT has no social-check engine site (Persuasion / Deception / etc. are descriptive only — the dice are rolled but the engine doesn't compute social outcomes). This clause is filed as out-of-scope until a social-check substrate lands.

---

## Grappled (RAW PHB p.290)

**Clause 1: "A grappled creature's speed becomes 0, and it can't benefit from any bonus to speed."**

- **State:** ✅ **enforced** via `effects.speed_reduction_ft = base_speed` in `_make_grappled_buff` at `tabletop_routes.py:33484–33493`. The `effective_speed_walk` helper at `app/content/effective_speed.py:98` reads this reduction and clamps to 0. A Longstrider +10 bonus would still apply, but the reduction (equal to base + 10 with bonus) keeps the net at 0. **Functionally correct.**
- **Note:** The "can't benefit from any bonus" RAW clause is honored mechanically (the clamp to 0 makes any positive bonus irrelevant), even though the architecture doesn't explicitly suppress the bonus. Filed as "enforced by side-effect" rather than literal clause check; no follow-up needed unless a future bonus type bypasses the additive model.

**Clause 2: "The condition ends if the grappler is incapacitated."**

- **State:** ✅ **shipped v2.389.0 "The Broken Hold".** Buff-install side-effect: whenever a buff with `incapacitated` semantics is installed on a creature, the engine sweeps every combatant for `grappled` buffs whose `source_char_id` matches the newly-incapacitated combatant and auto-ends them. Uses the canonical `_INCAPACITATED_KEYS` set (`hideous-laughter`, `stunned`, `paralyzed`, `unconscious`, `petrified`, the generic `incapacitated`) and the shared `_combatant_is_incapacitated` predicate that landed in v2.385.0. The grappled buff's `source_char_id` field (already populated by `_install_buff` from v2.99.112) was the existing scaffolding the sweep keyed off.

**Clause 3: "The condition also ends if an effect removes the grappled creature from the reach of the grappler."**

- **State:** ⚪ **GM-narrated.** Movement-based clauses are filed — the engine doesn't track "the grappler's reach" as a moving quantity. Future Reach-aware movement substrate would close this; not a priority.

---

## Incapacitated (RAW PHB p.290)

**Clause 1: "An incapacitated creature can't take actions or reactions."**

- **State:** ✅ **shipped v2.385.0 → v2.388.0.** All action/reaction sites now reject 409 `incapacitated` when the actor carries an incapacitating buff.
  - ✅ Concentration drops when incapacitated: `tabletop_routes.py:965, 989, 2343` (pre-audit).
  - ✅ Cleansing Touch (Paladin Lv 14) can end charmed/frightened/etc.: `tabletop_routes.py:274–279` (pre-audit).
  - ✅ **Sneak Attack ally-adjacency skips incapacitated allies** — `v2.385.0 "The Conscious Ally"`. Introduces the shared `_combatant_is_incapacitated` predicate that the rest of the sweep reuses unchanged.
  - ✅ **`/attack` action gate** — `v2.386.0 "The Still Hand"`. The opportunity-attack reaction branch shares the same `/attack` endpoint, so this commit closes the filed note that previously sat at `tabletop_routes.py:3259–3260`.
  - ✅ **`/cast_spell` action gate** — `v2.387.0 "The Quiet Tongue"`.
  - ✅ **`/use_feature` action gate** — `v2.388.0 "The Held Trick"`. Completes the general action gate.
  - **`/next_turn` deliberately has no gate** — incapacitated combatants still consume the turn slot RAW; their turn just has no actions.

The shared `_combatant_is_incapacitated` helper reads the combatant's buff list against `_INCAPACITATED_KEYS` (line 1906). The substrate-first design held: a single predicate served all five sites (Sneak Attack ally-skip + 3 action gates + Grappled-end sweep) without modification.

---

## Per-clause shipping order — closed end-to-end

The original v2.384.0 list (ordered by leverage × scope) closed in order across v2.385.0 → v2.391.0. Recorded here for posterity + as a template future condition arcs can reuse.

1. ✅ **Incapacitated → opportunity-attack + general action gate** — shipped as a four-commit sweep:
   - `v2.385.0 "The Conscious Ally"` — Sneak Attack ally-adjacency skips incapacitated allies; introduces the shared `_combatant_is_incapacitated` predicate.
   - `v2.386.0 "The Still Hand"` — `/attack` gate (covers both the action and the opportunity-attack reaction branch via the same endpoint, closing the long-standing `tabletop_routes.py:3259–3260` filed comment).
   - `v2.387.0 "The Quiet Tongue"` — `/cast_spell` gate.
   - `v2.388.0 "The Held Trick"` — `/use_feature` gate.
2. ✅ **Grappled → ends on grappler incapacitated** — `v2.389.0 "The Broken Hold"`. Install-side-effect that sweeps for `grappled` buffs whose `source_char_id` matches the newly-incapacitated combatant.
3. ✅ **Charmed → can't target charmer** — `v2.390.0 "The Charmer's Shield"` (`/attack`) + `v2.391.0 "The Charmer's Wider Shield"` (`/cast_spell` mirror). `/use_feature` is structurally self-targeted; not applicable.

**Total shipped:** 6 commits across v2.385.0 → v2.391.0. The Conditions TODO row moved ~85% → ~92% on the strength of this sweep. The `_combatant_is_incapacitated` helper landed in v2.385.0 and was reused unchanged across 5 sites — substrate-first design paid off.

---

## Out-of-scope

- **Charmed clause 2** (advantage on social checks) — no social-check substrate exists.
- **Grappled clause 3** (ends on out-of-reach movement) — no Reach-aware movement substrate; blocked on the Maps 2.0 arc.
- **Deafened** — RAW is mostly "can't hear" narrative; the only mechanical clause is "auto-fail any ability check requiring hearing" which is GM-narrated by design.

These three clauses remain the ~8% gap between the post-v2.391.0 Conditions row (~92%) and 100%. They're filed as future-3.x or out-of-scope per the v2.383.0 audit's "polish + UX" + "3.0 scope expansion" tracks, and account for **every** condition-side gap left in the SRD ruleset as of v2.400.x.

## Related docs

- [SRD 5e Audit (v2.382.0 refresh)](../TODO.md#srd-5e-audit-v23820-refresh) — the audit that surfaced the partial-enforcement question.
- [`condition_impacts.py`](../app/content/condition_impacts.py) — the descriptive condition-effect strings (the data layer this doc audits enforcement of).
- [`exhaustion-levels.md`](plans/exhaustion-levels.md) — the parallel condition Exhaustion already has a dedicated tracker.
