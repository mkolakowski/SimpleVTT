# SimpleVTT — Planned Features

Backlog of features to implement.

> Completed items live in [`TODONE.md`](TODONE.md). When an item ships, move it there (preserving the version reference) rather than leaving a strikethrough or ✅ stub here.

**Priority legend (Manually Added section only; other sections are time-ordered by header):**

| Tag | Meaning |
|-----|---------|
| `🔥 IN PROGRESS` | Actively being shipped (a plan doc + ongoing commits exist). |
| `🔴 P1` | High priority — bugs, regressions, top-of-the-list features the user has explicitly asked for. |
| `🟡 P2` | Medium priority — substantial features that are planned but not blocking anyone. |
| `🟢 P3` | Low priority — polish / cosmetic / nice-to-have UX tweaks. |

When the assistant offers a single-option "what's next?" via `AskUserQuestion` after a commit, the **top-priority** item (highest P-level, or the IN PROGRESS phase) should be the **(Recommended)** option per the rule in [`CLAUDE.md`](CLAUDE.md#offer-whats-next-as-multiple-choice-questions).

**Quick map of where to look:**

- **SRD 5e (CC BY 4.0) audit findings** → see [SRD 5e Audit (v2.553.0 refresh)](#srd-5e-audit-v25530-refresh) for the current per-category coverage. **Functionally complete: ~98–99% mechanically automated, 100% supported** under the 2026-06-22 rubric (GM-narrated resolution counts as done — every SRD spell/condition/feature is mechanically automated or GM-adjudicated). The **cast-and-broadcast utility-spell tail** is complete through #67; the conjure-catalog override shipped alongside; the only remaining work is out-of-SRD-scope content + optional automation of the GM-narrated remainder. Prior passes: [v2.502.0](#srd-5e-audit-v25020-refresh), [v2.434.0](#srd-5e-audit-v24340-refresh), [v2.399.0](#srd-5e-audit-v23990-refresh), [v2.390.0](#srd-5e-audit-v23900-refresh), [v2.382.0](#srd-5e-audit-v23820-refresh), [v2.379.0](#srd-5e-audit-v23790-refresh), [v2.376.0](#srd-5e-audit-v23760-refresh), [v2.344.1](#srd-5e-audit-v23441-refresh), [v2.315.0](#srd-5e-audit-v23150-refresh), [2026-06-14](#srd-5e-audit-2026-06-14-refresh), [2026-06-13](#srd-5e-audit-2026-06-13-refresh), [2026-06-11](#srd-5e-audit-2026-06-11-refresh), [2026-06-10](#srd-5e-audit-2026-06-10). The v2.315.0 refresh **corrects two denominators** that all prior passes got wrong: magic items now sit at **239/239 wired (100%)** post-v2.404.0 — the old "292" figure counted total equipment (239 magic + 37 mundane weapons + 18 mundane armor); class features are **222 per-row entries (strictly-✅ 100%)**, not the stale "133".
- **Active class-feature automation backlog** → see [Full Class-Feature Automation — remaining backlog](#full-class-feature-automation--remaining-backlog) (just Phase 8 + a few per-feature Phase-2 finishers remain after v2.149.1).
- **Design plans with deferred phases** → see [Design Plans Backlog](#design-plans-backlog) (every `docs/plans/*.md` indexed with a priority tag).
- **One-off bugs + UI polish that don't have a design plan** → see [Manually Added](#manually-added).
- **Big feature buckets that aren't tracked by a plan** → see the topic sections below (Character Sheet, GM Tools, Combat, Maps, Media, Player Features, UI/Mobile, Rules Reference, Legal & Compliance, Security, Test Infrastructure, Integrations, Visual, Class Features (next cycle)). The priority legend doesn't apply to these — they're topic-grouped, not P-tagged. Topic sections may contain entries that *do* have a design plan (e.g. Combat's Advantage & Disadvantage; Security's three v2.423.3–v2.423.5 plans) — the topic split is about audience navigation, not plan-vs.-no-plan status.

---

## SRD 5e Audit (v2.553.0 refresh)

> **Re-verified + re-scored 2026-06-22 (v2.565.1).** Denominators confirmed directly against `app/data/local/dnd5e/`: **319 spells, 322 monsters, 14 races, 15 conditions, 294 equipment (239 magic items), 12 class-feature + 13 subclass-feature files (222 per-row entries)**. A `git diff` of `app/data/local/dnd5e/` **and** `app/routes/tabletop_routes.py` from the v2.553.1 audit (78ea2cc3) to HEAD is **empty** — the entire interim (v2.554.0–v2.565.1) was the Notes & Handouts feature, which touches no SRD content or spell engine.
>
> **Scoring rubric change (2026-06-22): GM-narrated resolution counts as completed.** In a VTT the GM is the rules authority, so a spell/condition/feature whose resolution is *adjudicated at the table* is **supported**, not a gap — the cast endpoint spends the slot + broadcasts, and the GM narrates the spatial/scrying/object outcome. Under this "supported (automated **or** GM-narrated)" rubric the SRD ruleset is **functionally complete: every category sits at 100%, overall 100%.** The per-category table below uses the older *mechanically-automated-only* scoring (Spells ~93%, Conditions ~92%); the difference between those numbers and 100% is exactly the GM-narrated remainder — the 40,000-sq-ft zone geometry (Forbiddance / Antilife Shell / Globe), remote scrying views (Clairvoyance / Arcane Eye / Project Image), object triggers (Magic Mouth / Illusory Script), and the permanently-narrated condition clauses (Charmed / Grappled / Deafened). All of those are now considered **done** (GM-narrated). Mechanically automating the spatial/scrying remainder (Maps 2.0 geometry, a remote-sensor surface) is an **optional future enhancement**, not missing SRD coverage. What genuinely remains un-built is only **out-of-SRD-scope** content (Tasha's / Xanathar's-beyond-SRD / 2024 rules / Mythic Actions — future-3.x).
>
> **Correction 2026-06-22 (verify-substrate):** earlier refreshes (carried forward since v2.404.10/v2.434.0) listed a "**PC save-or-suck install hook**" as a filed gap "needing the v2.32.0 PC-save roll-response hook." **That hook was built at v2.37.0 (Phase T.3d) and is mature** — `/cast_spell` (and NPC-cast saves) prompt the targeted PC's save via a RollRequest, and `/roll_request/{id}/respond` auto-installs the matching condition on a fail, applies save-for-half for damage spells (v2.47.0 T.5d/T.5e AoE orchestration), and layers immunity gates (Aura of Devotion, Mindless Rage, PFE&G, Heroism) + legendary-resistance deferral. Harness-tested (`test_npc_archmage_hold_person`, `test_npc_cast_npc_target_install`, `test_cast_confusion_npc`, `test_menacing_attack`, …). So PC save-or-suck is **mechanically automated, not GM-narrated** — the stale gap is struck below.
>
> **Verify pass 2026-06-22 (the other "GM-narrated" items).** Ran the same substrate check over the rest of the remainder; several pieces are also **already mechanical**, so "zone geometry = GM-narrated" was too coarse:
> - **Globe of Invulnerability — spell-block is mechanical.** `_target_globe_blocks_spell` is wired into `/cast_spell` (line ~22374): a spell cast from outside the 10-ft barrier at a lower-or-equal level is **blocked**, geometry-aware via `_distance_ft_between_chars`.
> - **Antilife Shell — movement-barrier is mechanical.** `_move_crosses_antilife_shell` + `_antilife_shell_emitter_forces_creature_through` are wired into the token-move path (lines ~16038/16120): a move that would carry an affected creature across the shell is blocked/swept.
> - **Emanation start-of-turn damage is mechanical** via the `_tick_auras` engine (Spirit Guardians, Holy Aura, the aura family) — geometry-aware per-turn damage to creatures in radius.
> - **Genuinely still GM-narrated** (confirmed no substrate): the *enter-the-area-mid-move* re-trigger (the `_concentration_aoes` "future re-trigger-on-enter follow-up" — filed, unbuilt), Forbiddance's 5d10 ward damage + 40,000-sq-ft geometry (flag-buff), the remote scrying **views** (Clairvoyance / Arcane Eye / Project Image — no camera surface), and the object **triggers** (Magic Mouth / Illusory Script — no trigger engine). These remain counted done under the rubric; mechanizing them needs Maps-2.0 geometry / a remote-sensor surface.

**Audit scope.** Recomputed against the codebase as of v2.553.0, capturing the **continuation of the cast-and-broadcast utility-spell tail arc** ([`docs/plans/cast-and-broadcast-tail.md`](plans/cast-and-broadcast-tail.md)) from **#36 → #67** (v2.503.0 → v2.553.0), plus the **conjure-catalog summon override** (v2.539.0 → v2.541.0). The v2.502.0 refresh below stopped at tail #35; this pass captures ~32 more wired spell endpoints. The headline: **every substrate-blocked cluster the v2.502.0 audit filed as gap #1 now has a wired cast endpoint** — either riding a real substrate (a mechanical effect) or installing a GM-narrated marker buff where SimpleVTT deliberately models no engine (geometry / objects / scrying views).

- **Invisibility-detection — shipped.** See Invisibility (#42) + True Seeing (#56) ride the `sees_invisible` attack-edge substrate (v2.510.0/.514.0): a creature that sees invisible negates an invisible attacker's advantage AND the disadvantage of attacking an invisible target. True Seeing also rides `darkvision_ft`.
- **Illusion-duplicates — shipped.** Mirror Image (#57) added a genuinely **new attack-pipeline deflection mechanic** (`_resolve_mirror_image_deflection` in `/attack` + `/npc_attack` — a hitting swing rolls a d20 to strike a duplicate, which is destroyed if the swing meets its AC). Mislead (#60) rides the `invisible` substrate; Project Image (#61) is a GM-narrated concentration projection.
- **Scrying-sensors — shipped.** Clairvoyance (#62) + Arcane Eye (#63) on the shared `_do_cast_scry_sensor` helper (concentration flag-buffs; views GM-narrated).
- **AoE-shape zones — shipped (GM-narrated markers).** Antilife Shell (#45), Globe of Invulnerability (#44), and Forbiddance (#67) install marker buffs; Forbiddance bakes a 5d10 damage marker, Globe a spell-level block, Antilife a barrier flag — geometry GM-narrated.
- **Summon-catalog depth — shipped.** All six Conjure spells (Animals / Woodland Beings / Minor Elementals / Elemental / Fey / Celestial) accept an optional catalog creature slug, validated by type + CR (count-tier or CR-cap), via `_monster_summon_template` + `_summon_companion(template=…)`.
- **Other tail #36–#67 utility spells** ride existing substrates: concentration cascade (Locate Object/Creature #58/#59, Detect Thoughts #64, the scrying pair), DC-bake (Zone of Truth #52, Detect Thoughts #64, Forbiddance #67), flag-buffs (Darkvision #51, Water Walk/Breathing, Fire Shield, Nondetection), and GM-narrated inscriptions (Magic Mouth #65, Illusory Script #66 on `_do_cast_inscribed_illusion`).

**Substrate take-aways for the next contributor:** the tail is effectively **complete** for the simple flag-buff / DC-bake / concentration-marker / GM-narrated-zone shapes. What remains genuinely un-modelable in 2.x is the spatial/object/scrying *resolution* (40,000-sq-ft zones, remote camera views, object trigger engines) — those ship as GM-narrated markers by design. The one new mechanical substrate this continuation added is the Mirror Image deflection; everything else rode a pre-existing read-site (verify-substrate, prefer-zero-code).

### v2.502.0 → v2.553.0 audit scope (prior section retained below)

The v2.437.0 → v2.502.0 arc (tail #1–#35) is documented in the [v2.502.0 refresh](#srd-5e-audit-v25020-refresh) immediately below, retained verbatim. The rest of *this* section's headline numbers supersede it.

### Per-category coverage (the headline numbers)

| Category | SRD count | Automated | Notes |
|---|---|---|---|
| Races | 14 | **✅ ~100%** | v2.654.0: added the 5 SRD 5.1 subraces missing from the shipped tier (Mountain Dwarf, Wood Elf, Forest Gnome, Stout Halfling, Drow). The prior "9 = 100%" counted the 9 shipped races' traits as fully automated, but the SRD subrace roster was incomplete — only one subrace per base race shipped. Completeness floor bumped 9→14. |
| Monsters | 322 | **✅ ~100%** | Unchanged. |
| Conditions | 15 | **~92%** automated · **100% supported** | The ~8% is the permanently-GM-narrated clauses (Charmed / Grappled / Deafened) — **counted done** under the 2026-06-22 rubric. |
| Class features | **222 rows** | **✅ 100%** | Unchanged. |
| Spells | 319 | **~93%** automated · **100% supported** | The residual ~7% is GM-narrated spatial/object/scrying resolution — **counted done** under the 2026-06-22 rubric (every spell has a wired cast endpoint; the GM adjudicates the remainder). *(PC save-or-suck condition install is mechanically automated since v2.37.0 — see the correction note above; it is NOT part of this residual.)* **+3 pts vs. v2.502.0 (~90% → ~93%).** The tail #36–#67 continuation + conjure-catalog work wired a cast endpoint for **every substrate-blocked cluster** the v2.502.0 audit filed as open — invisibility-detection, illusion-duplicates, scrying-sensors, AoE-shape zones, summon-catalog depth. Where SimpleVTT models the mechanic it's a real effect (Mirror Image deflection; See Invisibility / True Seeing / Mislead attack-edge; catalog summons; baked save-DCs / damage markers; concentration cascade). Where it deliberately models no engine (zone geometry, remote scrying views, object triggers) the cast is wired + slot-spent + a marker buff installed, with the spatial/object resolution **GM-narrated**. The residual ~7% is that GM-narrated spatial/object/scrying resolution + the filed PC-save-or-suck install hook. |
| Magic items | **239 / 239 wired** | **✅ 100%** | Unchanged. |

**Overall ~98–99% mechanically automated · 100% supported** across the SRD ruleset. Four of six categories are strictly-✅ 100% automated (Races, Monsters, Class features, Magic items); Conditions ~92% and Spells ~93% by the automated-only count, **both 100% under the 2026-06-22 "GM-narrated counts as done" rubric** — every SRD spell, condition, and feature is either mechanically automated or GM-narrated, so the SRD ruleset is functionally complete. The only un-built remainder is out-of-SRD-scope future content.

### Status (2026-06-22 rubric: GM-narrated = done → SRD functionally complete)

1. ✅ **DONE — spatial/object/scrying resolution** (mechanical where SimpleVTT models it, GM-narrated otherwise; see the verify-pass note above). Already **mechanical**: Globe of Invulnerability spell-block (`_target_globe_blocks_spell`, geometry-aware), Antilife Shell movement-barrier (`_move_crosses_antilife_shell`), and emanation start-of-turn damage (`_tick_auras` — Spirit Guardians / Holy Aura / aura family). Still **GM-narrated** (no substrate): the enter-mid-move damage re-trigger (filed `_concentration_aoes` follow-up — now has a design plan: [`aoe-enter-trigger.md`](plans/aoe-enter-trigger.md), the one buildable-on-existing-substrate item), Forbiddance's ward damage + 40k-sq-ft geometry, the remote scrying views (Clairvoyance / Arcane Eye / Project Image), and object triggers (Magic Mouth / Illusory Script). **Counted complete.** Mechanizing the GM-narrated slice (Maps 2.0 geometry + a remote-sensor surface) is an **optional future enhancement**, not missing SRD coverage.
2. ✅ **DONE (mechanically automated, v2.37.0 Phase T.3d) — PC save-or-suck condition install.** The PC-save roll-response hook is **built**, not filed: a PC-targeted save spell (PC- or NPC-cast) prompts the PC's save via a RollRequest, and `/roll_request/{id}/respond` auto-installs the matching condition on a fail (+ save-for-half for damage spells via v2.47.0 T.5d/T.5e, immunity gates, legendary-resistance deferral). Harness-tested. The long-standing "needs the v2.32.0 hook" filing was stale — see the correction note at the top of this section.
3. ✅ **DONE (GM-narrated) — permanently-narrated condition clauses.** Charmed clause 2 (social-check advantage), Grappled clause 3 (out-of-reach), Deafened (hearing-narrative) — adjudicated at the table per the v2.384.0 audit doc. **Counted complete.**
4. 🟠 **Optional enhancements (not gaps).** Bucket D announce-only magic items; race-features Phases 1b/1c + 4b/5b + 7. These already work as GM-narrated; mechanizing them is optional polish.
5. ✅ **DONE — Cast-and-broadcast utility-spell tail (v2.437.0–v2.553.0).** Phase 1 (5) + Phase 2 (#1–#67). Every substrate-blocked cluster wired. See [`docs/plans/cast-and-broadcast-tail.md`](plans/cast-and-broadcast-tail.md).
6. ✅ **DONE — Conjure-catalog summon override (v2.539.0–v2.541.0).** All six Conjure spells accept arbitrary catalog creatures (type + CR validated).
7. ✅ **DONE — Spell utility-upcast + target-scaling arcs; Magic-items closure; Security spine.** Unchanged.

**Net: the SRD ruleset is functionally complete** — every spell, condition, feature, monster, race, and magic item is mechanically automated or GM-narrated. The only remaining work is out-of-SRD-scope content (below) + optional automation of the GM-narrated remainder.

### Out-of-scope (unchanged)

Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte, 2024 rules + Mythic Actions stay future-3.x scope. (The permanently-GM-narrated condition clauses — Charmed / Grappled / Deafened — are now **counted done**, not a gap; see status #3 above.)

### What's left to ship in SimpleVTT 2.x?

The SRD ruleset is **functionally complete** — ~98–99% mechanically automated, **100% supported** once GM-narrated resolution is counted as done (2026-06-22 rubric). The cast-and-broadcast tail is complete; there is no un-wired spell cluster, and no SRD spell/condition/feature is unsupported. The remaining inflection points are **enhancements + scope expansion, not coverage gaps**:

- **3.0 scope expansion** — post-SRD content (Tasha's, Xanathar's, 2024-PHB rules, Mythic Actions) + the Bucket D announce-only mechanization arc.
- **Maps 2.0 geometry + remote-sensor substrates** — would upgrade the GM-narrated spatial/object/scrying markers (gap #1) to fully-resolved effects, and unlock race-features Phases 4b + 5b + the positional advantage-disadvantage Phase 3.
- **Polish + UX** — Manually Added P3 items + Combat / GM Tools sections.

---

## SRD 5e Audit (v2.502.0 refresh)

**Audit scope.** Recomputed against the codebase as of v2.502.0, capturing the **v2.437.0 → v2.502.0 cast-and-broadcast utility-spell tail arc** ([`docs/plans/cast-and-broadcast-tail.md`](plans/cast-and-broadcast-tail.md)) — the single biggest Spells mover since the v2.434.0 audit, which predates the *entire* arc. The arc took utility spells that previously only "cast + broadcast" (spent the slot + showed a roll-log card) and gave them **mechanized server-side effects**, all riding existing substrates where possible (the "verify-substrate, prefer zero-code" recipe):

- **Phase 1 — 5 demonstrators (v2.437.0 → v2.441.0):** True Strike, Speak with Animals, Spider Climb, Pass without Trace, Find Steed.
- **Phase 2 — #1 → #35 (v2.442.0 → v2.502.0):** ~30 more utility spells. The latest cluster (this session): Protection from Poison (#25), Enlarge/Reduce (#26), Freedom of Movement (#27), Warding Bond (#28), **Death Ward (#29 — first to add new HP-path code)**, Protection from Energy (#30), Stoneskin (#31), Greater Invisibility (#32), **Blur (#33 — new generic `attackers_have_disadvantage` read-site)**, Mind Blank (#34), **Foresight (#35 — new generic blanket-`foresight` advantage substrate)**.
- **v2.496.1 fix:** Protection from Poison's resistance buff wasn't mirrored to the target sheet (so `_resistance_halve` never read it) — patched; the resistance/condition/invisible buffs all need a `_mirror_buffs_to_sheet` call because those readers consult the DB sheet, not hub state.

**Substrate take-aways for the next contributor:** the tail is now deep enough that the remaining candidates need genuinely new substrates, not buff-layer rides. Three reusable read-sites were added this arc — the Death-Ward HP-floor (alongside Relentless Endurance), the generic `attackers_have_disadvantage` (Blur + Foresight), and the generic `foresight` blanket-advantage (wired into all three advantage choke-points). The mirror-vs-hub-state distinction is the main footgun: condition-immunity / resistance / invisible buffs are **sheet-read** (need the mirror); AC / attack adv/dis / blanket-advantage buffs are **hub-read** (no mirror).

### Per-category coverage (the headline numbers)

| Category | SRD count | Automated | Notes |
|---|---|---|---|
| Races | 9 | **✅ ~100%** | Unchanged. |
| Monsters | 322 | **✅ ~100%** | Unchanged. |
| Conditions | 15 | **~92%** | Unchanged. |
| Class features | **222 rows** | **✅ 100%** | Unchanged. |
| Spells | 319 | **~90%** | **+5 pts vs. v2.434.0 (~85% → ~90%).** The v2.437.0–v2.502.0 tail arc mechanized ~35 utility spells that were cast-and-broadcast-only at the v2.434.0 audit — buffs (Longstrider, Mage Armor, Enlarge/Reduce, Stoneskin, Greater Invisibility, Blur, Foresight), condition-immunities (Freedom of Movement, Mind Blank), resistances (Protection from Poison/Energy, Warding Bond), and HP-floors (Death Ward). Remaining ~10% is the spells that need substrates SimpleVTT doesn't model: invisibility-detection (See Invisibility), AoE-shape effects (Antilife Shell, Globe of Invulnerability), illusion-duplicates (Mirror Image, Mislead, Project Image), summon-catalog depth (the Conjure family — filed separately), and the permanently-GM-narrated divination/scry/surprise clauses. |
| Magic items | **239 / 239 wired** | **✅ 100%** | Unchanged. |

**Overall ~98%** automated across the SRD ruleset (up from ~97% at v2.434.0 — the Spells bump from ~85% → ~90% is the mover). Four of six categories stay strictly-✅ 100% (Races, Monsters, Class features, Magic items); Conditions ~92% (permanently-GM-narrated clauses); Spells ~90% with the remaining gap now dominated by substrate-blocked spells rather than the cast-and-broadcast tail (which is largely closed).

### Remaining gaps (priority order — toward full SRD automation)

1. 🟡 **P2 — Substrate-blocked utility spells.** The cast-and-broadcast tail is largely closed; what's left needs new engine substrates: invisibility-detection (See Invisibility / True Seeing), AoE-shape persistent effects (Antilife Shell, Globe of Invulnerability, Forbiddance), illusion-duplicate state (Mirror Image, Mislead, Project Image), and summon-catalog depth (the Conjure family — has its own filed follow-up). Each is a substrate ship, not a content drop. Pick by leverage if a contributor wants to drive it.
2. 🟠 **Filed follow-up — PC save-or-suck install for condition-shape spells.** Unchanged from v2.434.0 — the per-target condition install on a failed PC save still needs the v2.32.0 PC-save roll-response hook.
3. 🟠 **Filed follow-ups — Bucket D announce-only magic items; race-features Phases 1b/1c + 4b/5b + 7.** Unchanged.
4. ✅ **DONE — Cast-and-broadcast utility-spell tail (v2.437.0–v2.502.0).** Phase 1 (5) + Phase 2 (#1–#35). See [`docs/plans/cast-and-broadcast-tail.md`](plans/cast-and-broadcast-tail.md).
5. ✅ **DONE — Spell utility-upcast Phase 1 (duration) + Phase 4 (rider/bonus).** Closed v2.405.0–v2.434.0.
6. ✅ **DONE — Spell target-scaling cap+upcast arc (v2.404.1–v2.404.10); Magic-items closure (v2.403.0–v2.404.0); Security spine (v2.424.0–v2.431.0).** Unchanged.

### Out-of-scope (unchanged)

Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte, 2024 rules + Mythic Actions stay future-3.x scope. Charmed clause 2 (social-check advantage), Grappled clause 3 (out-of-reach), Deafened (hearing-narrative): permanently GM-narrated per the v2.384.0 audit doc.

### What's left to ship in SimpleVTT 2.x?

The SRD ruleset sits at ~98% automated end-to-end. With the cast-and-broadcast tail largely closed, the remaining ~2% is dominated by the substrate-blocked spells (gap #1) + the filed PC-save-or-suck hook (gap #2). The natural next-arc inflection points:

- **3.0 scope expansion** — post-SRD content (Tasha's, Xanathar's, 2024-PHB rules, Mythic Actions) + the Bucket D announce-only mechanization arc.
- **v2.5x substrate arcs** — invisibility-detection, AoE-shape persistent effects, illusion-duplicates, summon-catalog depth (each unlocks a cluster of the remaining ~10% Spells gap).
- **Polish + UX** — Manually Added P3 items + Combat / GM Tools sections.
- **Maps 2.0 / Stealth-cover substrates** — would unlock race-features Phases 4b + 5b + the positional advantage-disadvantage Phase 3.

---

## SRD 5e Audit (v2.434.0 refresh)

**Audit scope.** Recomputed against the codebase as of v2.434.0, capturing the **v2.405.0 → v2.434.0 ship train** that closed two more spell-utility-upcast phases end-to-end:

- **v2.405.0 → v2.408.0 — Phase 1 (duration scaling) closed.** 6 spells substrate-wired across the `_SPELL_DURATION_MAP` + `_spell_duration_rounds_for_slot()` helper. Hunter's Mark / Hex got one-line retrofits onto the new substrate; Bestow Curse + Geas + Mass Suggestion + Modify Memory got new endpoint-builds (catalog-only before). The substrate's `"permanent"` / `"30d"` / `"1y"` markers handle non-numeric durations.
- **v2.421.0 → v2.423.0 — Phase 4 (rider/bonus scaling) opens.** 3 consumers across two sub-shapes — Magic Weapon (tier-walk, opens Phase 4), Elemental Weapon (tier-walk, two riders off one tier), False Life (linear-additive, opens the additive shape).
- **v2.424.0 → v2.431.0 — Security spine end-to-end (8 commits).** Not an SRD shift but worth noting because it consumed most of the v2.434.0 session: `app/audit_log.py` canonical-line emission + demo magic-link URL-login + `api.unauthorized` / `api.forbidden` + Cloudflare edge-banning + CrowdSec configs + admin_audit_log destructive-action audit. 15 canonical event tags + 97 new harness tests + SCHEMA_VERSION 69 → 71.
- **v2.432.0 → v2.434.0 — Phase 4 close.** Aid refactor (4th consumer), Spiritual Weapon + `step_size` substrate generalization (5th consumer, opens step-N additive sub-shape), Phase 4 closure audit confirming no remaining SRD candidates fit. Phase 4 ✅ CLOSED.

### Per-category coverage (the headline numbers)

| Category | SRD count | Automated | Notes |
|---|---|---|---|
| Races | 9 | **✅ ~100%** | Unchanged from v2.404.10. |
| Monsters | 322 | **✅ ~100%** | Unchanged. |
| Conditions | 15 | **~92%** | Unchanged. |
| Class features | **222 rows** | **✅ 100%** | Unchanged. |
| Spells | 319 | **~85%** | **+2 pts vs. v2.404.10 (~83% → ~85%).** Phase 1 (duration scaling) added 3 net-new mechanized utility spells via endpoint-builds (Geas / Mass Suggestion / Modify Memory — catalog-only before v2.406.0–v2.408.0). Phase 4 added 3 net-new mechanized utility spells via endpoint-builds (Magic Weapon / Elemental Weapon / False Life — catalog-only before v2.421.0–v2.423.0). Aid + Spiritual Weapon were already wired but moved onto the Phase 4 substrate for symmetry. Hunter's Mark + Hex got duration-substrate retrofits (no behavior change). Remaining ~15% is the cast-and-broadcast utility tail with no per-slot scaling RAW (Detect Magic, Identify, Counterspell, Comprehend Languages, etc.) + the permanently-GM-narrated spell mechanics. |
| Magic items | **239 / 239 wired** | **✅ 100%** | Unchanged. |

**Overall ~97%** automated across the SRD ruleset (unchanged headline; Spells nudged from ~83% to ~85% but the per-category roll-up rounds to the same overall). Four of six categories are strictly-✅ 100% (Races, Monsters, Class features, Magic items); Conditions sits at ~92% with the permanently-GM-narrated clauses noted v2.384.0 (Charmed social-check advantage, Grappled out-of-reach, Deafened hearing-narrative); Spells sits at ~85% with the cast-and-broadcast tail accounting for nearly all of the remaining gap.

### Remaining gaps (priority order — toward full SRD automation)

After Phase 1 + Phase 4 closure, the engine-shaped gaps are narrower still:

1. 🟡 **P2 — Cast-and-broadcast utility-spell mechanical depth.** Unchanged framing from v2.404.10 but with a smaller scope after the Phase 1 + Phase 4 closures. The remaining ~250 SRD utility spells either don't scale RAW (True Strike / Identify / Heroes' Feast / Detect Magic) or scale via mechanisms that don't fit the existing substrates (true polymorph form-pool depth, glyph trigger-state, conjure family summon catalog — see filed Phase 3 follow-ups). Pick the next 3–5 highest-leverage spells per commit if a contributor wants to drive this surface.
2. 🟠 **Filed follow-up — PC save-or-suck install for condition-shape spells.** Unchanged from v2.404.10. The condition-install path at `tabletop_routes.py:~22165` is NPC-only in v1; PC save-or-suck spells (Charm Person / Hold Person / Command / Animal Friendship / Blindness-Deafness etc.) ride the cap substrate for the target-count gate but the per-target condition install on a failed save still requires the v2.32.0 PC-save roll-response hook. Filed for a future v2.5x.x arc.
3. 🟠 **Filed follow-up — Bucket D announce-only mechanization (Path C from v2.403.x).** Unchanged. ~60 SRD magic items have catalog rows + charge counters wired but mechanical effects stay GM-narrated by design. Filed for v3.x scope expansion.
4. 🟠 **Filed follow-up — race-features Phases 1b/1c + 4b/5b + 7.** Unchanged.
5. ✅ **DONE — Spell utility-upcast Phase 1 (duration scaling).** Closed v2.405.0–v2.408.0. 6 spells substrate-wired.
6. ✅ **DONE — Spell utility-upcast Phase 4 (rider/bonus scaling).** Closed v2.421.0–v2.434.0. 5 consumers across 3 sub-shapes. Closure audit at v2.434.0 confirms no remaining SRD candidates.
7. ✅ **DONE — Spell target-scaling cap+upcast arc (v2.404.1–v2.404.10).** Unchanged.
8. ✅ **DONE — Magic-items closure arc (v2.403.0–v2.404.0).** Unchanged.
9. ✅ **DONE — Security spine end-to-end (v2.424.0–v2.431.0).** Not an SRD shift, but the operational closure of the three-piece security spine (audit-log + demo magic-link + fail2ban/CrowdSec configs + Cloudflare edge banning + admin destructive-action audit) is the headline non-SRD ship since v2.404.10. See [`docs/plans/demo-magic-link.md`](plans/demo-magic-link.md) / [`docs/plans/fail2ban-crowdsec-integration.md`](plans/fail2ban-crowdsec-integration.md) / [`docs/plans/cloudflare-edge-banning.md`](plans/cloudflare-edge-banning.md).
10. ✅ **DONE — Charmed-gate mirror onto `/cast_spell` + `/use_feature` (v2.399.2).** Unchanged.
11. ✅ **DONE — Race tail (v2.392.0–v2.399.0).** Unchanged.
12. ✅ **DONE — Condition-enforcement audit clauses #1–#4.** Closed v2.385.0–v2.390.0.
13. ✅ **DONE — Class-feature ⚪ tail.** Closed v2.368.0–v2.370.1.
14. ✅ **DONE — Spell area-effect automation.** Closed v2.373.0–v2.376.0.
15. ✅ **DONE — Spell upcast dice/heal scaling.** Effectively complete (v2.344.2).
16. ✅ **DONE — Magic-item content tail.** Closed v2.316.0–v2.344.0.
17. ✅ **DONE — Legendary + Lair Actions arc.** Closed v2.159.32–v2.382.0.

### Out-of-scope (unchanged)

Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte stay future-3.x scope. **2024 rules + Mythic Actions** likewise stay future-3.x scope. **Charmed clause 2** (social-check advantage), **Grappled clause 3** (out-of-reach), **Deafened** (mostly hearing-narrative): permanently GM-narrated per the v2.384.0 audit doc.

### What's left to ship in SimpleVTT 2.x?

The SRD ruleset stays at ~97% automated end-to-end. With Phase 1 + Phase 4 closed, the remaining ~3% gap is dominated by:

- **Cast-and-broadcast utility-spell mechanical depth** — the ~250 spells with no per-slot scaling RAW (filed gap #1). Substrate-extension work, not engine.
- **PC save-or-suck install hook** (filed gap #2) — affects ~10 condition-shape spells.
- **Bucket D announce-only mechanization** (filed gap #3) — magic-item mechanical depth.
- **race-features substrate-dependent phases** (filed gap #4) — Halfling Nimbleness / Naturally Stealthy full enforcement.

Each of these is filed in its own plan doc. The natural next-arc inflection points are unchanged from v2.404.10:

- **3.0 scope expansion** — post-SRD content (Tasha's, Xanathar's, 2024-PHB rule changes, Mythic Actions). Plus the Bucket D announce-only mechanization arc.
- **v2.5x utility-spell mechanical-depth arcs** — opens after the cast-and-broadcast tail gets a substrate.
- **Polish + UX** — Manually Added P3 polish items + Combat / GM Tools sections.
- **Test-infrastructure hardening** — spell-validation suite Phase 5 + pytest-xdist parallelization.
- **Maps 2.0 / Stealth-cover substrates** — would unlock Phases 4b + 5b of race-features.

---

## SRD 5e Audit (v2.404.10 refresh)

**Audit scope.** Recomputed against the codebase as of v2.404.10, after the **v2.404.1 → v2.404.10 spell utility-upcast arc** that closed the target-scaling cap+upcast substrate for 9 utility spells across both substrate dicts:

- **v2.404.1 "The Hidden Hand"** — Invisibility cap (`_SPELL_BUFF_MAP`, L2 + 1/slot).
- **v2.404.2 "The Borrowed Sky"** — Fly cap (`_SPELL_BUFF_MAP`, L3 + 1/slot).
- **v2.404.3 "The Menagerie's Touch"** — Enhance Ability cap (`_SPELL_BUFF_MAP`, L2 + 1/slot).
- **v2.404.4 "The Hour's Stride"** — Longstrider cap (`_SPELL_BUFF_MAP`, L1 + 1/slot; existing entry extended).
- **v2.404.5 "The Whispered Bond"** — Charm Person cap (`_SPELL_TARGET_CAPS` data drop, L1 + 1/slot — first condition-shape consumer of the generalized substrate).
- **v2.404.6 "The Shared Cap"** — Bane substrate consolidation (moved inline math to registry; new `_spell_target_cap_for_slot` helper for bespoke endpoints).
- **v2.404.7 "The Single Word"** — Command full condition-install + cap (`_SPELL_CONDITION_MAP` + `_SPELL_TARGET_CAPS`, L1 + 1/slot).
- **v2.404.8 "The Beast's Trust"** — Animal Friendship full condition-install + cap (L1 + 1/slot).
- **v2.404.9 "The Stolen Sense"** — Blindness/Deafness arc-closer (first L2-base condition-install ship).
- **v2.404.10 "The Arc Recorded"** — Closure-retrospective plan doc at [`docs/plans/spell-utility-upcast.md`](plans/spell-utility-upcast.md) + wiki surfacing (allowlist + landing-page row + on-disk index row + per-slug harness test).

The session shipped **10 commits** end-to-end. Spells moves slightly closer to its strictly-✅ ceiling (cap arithmetic substrate is now a closed surface across both dicts; the remaining ~17% gap is mechanical depth on the cast-and-broadcast utility tail — see filed gap #1 below).

### Per-category coverage (the headline numbers)

| Category | SRD count | Automated | Notes |
|---|---|---|---|
| Races | 9 | **✅ ~100%** | Unchanged. |
| Monsters | 322 | **✅ ~100%** | Unchanged. |
| Conditions | 15 | **~92%** | Unchanged. |
| Class features | **222 rows** | **✅ 100%** | Unchanged. |
| Spells | 319 | **~83%** | **+4 pts vs. v2.404.0 (~79% → ~83%).** Nine target-scaling utility spells (Invisibility / Fly / Enhance Ability / Longstrider / Charm Person / Bane / Command / Animal Friendship / Blindness-Deafness) now ride the v2.380.0 / v2.381.0 cap-extension substrate. **All 9 in-scope target-scaling utility spells are now wired** — the cap-arithmetic surface is closed across both `_SPELL_BUFF_MAP` and `_SPELL_TARGET_CAPS`. The remaining ~17% gap is mechanical depth on cast-and-broadcast utility spells (no damage/heal base) — filed below. |
| Magic items | **239 / 239 wired** | **✅ 100%** | Unchanged from v2.404.0. |

**Overall ~97%** automated across the SRD ruleset (headline unchanged — Spells was already in the ~79% range; the meaningful change is that the target-scaling cap+upcast substrate is now a closed surface). The remaining ~3% is dominated by the cast-and-broadcast utility-spell mechanical-depth tail + the permanently-GM-narrated condition clauses.

### Remaining gaps (priority order — toward full SRD automation)

After the v2.404.x spell utility-upcast arc, the per-category gaps are narrower still:

1. 🟡 **P2 — Cast-and-broadcast utility-spell mechanical depth (narrower scope).** Reframed. The v2.404.x arc closed the **target-scaling** cap+upcast surface for the 9 in-scope spells. The remaining ~250 SRD utility spells either don't scale RAW (True Strike / Identify / Heroes' Feast / Detect Magic / etc.) or scale via mechanisms outside the target-cap substrate: duration-only (Mass Suggestion / Hunter's Mark / Bestow Curse / Geas / Modify Memory — 11 spells), radius/AoE-area (Confusion / Fog Cloud / Major Image / Globe of Invulnerability — 9 spells), summon-level (the Conjure family — 6 spells), counter/effect riders (Counterspell / Dispel Magic / Heal / Animate Dead / Magic Weapon — 14 spells). Each sub-bucket needs its own substrate ship (duration-scaling first, since it has the most spells). Filed for a v2.5x.x arc.
2. 🟠 **Filed follow-up — PC save-or-suck install for condition-shape spells.** The condition-install path at line ~22165 of `tabletop_routes.py` is NPC-only in v1 (per the v2.32.0 filed comment). The v2.404.x arc shipped Command / Animal Friendship / Blindness-Deafness with the cap enforcement working for PC targets, but the per-target condition install on a failed save still requires the v2.32.0 PC-save roll-response hook. Affects 5+ spells in this arc + Charm Person + Hold Person + every save-or-suck spell. Filed for the same v2.5x.x arc.
3. 🟠 **Filed follow-up — Bucket D announce-only mechanization (Path C from the v2.403.x arc).** Unchanged. ~60 SRD magic items have catalog rows + charge counters wired but mechanical effects stay GM-narrated by design. Filed for v3.x scope expansion.
4. 🟠 **Filed follow-up — race-features Phases 1b/1c + 4b/5b + 7.** Unchanged.
5. ✅ **DONE — Spell target-scaling cap+upcast arc (v2.404.1–v2.404.10).** All 9 in-scope target-scaling utility spells now use the v2.380.0 / v2.381.0 substrate. Both buff-shape and condition-shape paths exercised.
6. ✅ **DONE — Magic-items closure arc (v2.403.0–v2.404.0).** Unchanged.
7. ✅ **DONE — Charmed-gate mirror onto `/cast_spell` + `/use_feature` (v2.399.2 reconciliation).** Unchanged.
8. ✅ **DONE — Race tail (v2.392.0–v2.399.0).** Unchanged.
9. ✅ **DONE — Condition-enforcement audit clauses #1–#4.** Closed v2.385.0–v2.390.0.
10. ✅ **DONE — Class-feature ⚪ tail.** Closed v2.368.0–v2.370.1.
11. ✅ **DONE — Spell area-effect automation.** Closed v2.373.0–v2.376.0.
12. ✅ **DONE — Spell upcast dice/heal scaling.** Effectively complete (v2.344.2 reconciliation).
13. ✅ **DONE — Magic-item content tail.** Closed v2.316.0–v2.344.0.
14. ✅ **DONE — Legendary + Lair Actions arc.** Closed end-to-end v2.159.32–v2.382.0.

### Out-of-scope (unchanged)

Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte stay future-3.x scope. **2024 rules + Mythic Actions** likewise stay future-3.x scope. **Charmed clause 2** (social-check advantage), **Grappled clause 3** (out-of-reach), **Deafened** (mostly hearing-narrative): permanently GM-narrated per the v2.384.0 audit doc.

### What's left to ship in SimpleVTT 2.x?

The SRD ruleset stays at ~97% automated end-to-end. The remaining ~3% is dominated by the cast-and-broadcast utility-spell mechanical-depth tail (filed gap #1, narrower scope after v2.404.x) + the PC-side save-or-suck install hook (filed gap #2) + the substrate-dependent filed follow-ups. The natural next-arc inflection is unchanged:

- **3.0 scope expansion** — post-SRD content (Tasha's, Xanathar's, 2024-PHB rule changes, Mythic Actions). **Plus the Bucket D announce-only mechanization arc** (filed gap #3 above).
- **v2.5x.x utility-spell mechanical-depth arcs** — duration-scaling substrate (Hunter's Mark / Bestow Curse / Geas / Modify Memory / Mass Suggestion) is the highest-leverage next ship; AoE-radius scaling (Confusion / Fog Cloud / Globe of Invulnerability) next.
- **v2.5x.x PC save-or-suck install hook** — closes the condition-install gap for PC targets across Charm Person / Hold Person / Command / Animal Friendship / Blindness-Deafness + every existing save-or-suck spell.
- **Polish + UX** — Manually Added P3 polish items + Combat / GM Tools sections.
- **Test-infrastructure hardening** — spell-validation suite Phase 5 + pytest-xdist parallelization.
- **Maps 2.0 / Stealth-cover substrates** — would unlock Phases 4b + 5b of race-features.

---

## SRD 5e Audit (v2.404.0 refresh)

**Audit scope.** Recomputed against the codebase as of v2.404.0, after the **v2.403.0 → v2.404.0 magic-items closure arc** that took the magic-items category from 235/239 (~98%) to 239/239 (100%):

- **v2.403.0 "The Elemental Counter"** — substrate ship: new `_use_item_action_announce_only` handler + 4 elemental-summoning items (bowl/brazier/censer/stone).
- **v2.403.1 "The Trickster's Counter"** — 4 more announce-only items (cape-of-the-mountebank, iron-bands-of-binding, efreeti-bottle, bag-of-tricks 3/dawn).
- **v2.403.2 "The Recharging Cube"** — 3 multi-charge per-day items with dice-recharge (pipes-of-the-sewers, helm-of-teleportation, cube-of-force).
- **v2.403.3 "The Patient Hourglass"** — 3 multi-day cooldown items (horn-of-valhalla, ring-of-djinni-summoning, rod-of-security).
- **v2.403.4 "The Spent Chime"** — 2 lifetime-charge items (chime-of-opening, ring-of-three-wishes).
- **v2.403.5 "The Apothecary's Jar"** — 4 multi-dose consumable containers (restorative-ointment, dust-of-dryness, sovereign-glue, bag-of-beans).
- **v2.403.6 "The Tearing Fan"** — Bucket A holdout #1: Wind Fan with cumulative-20% tear-on-overuse mechanic (dedicated handler).
- **v2.403.7 "The Quiet Probe"** — Bucket A holdout #2: Medallion of Thoughts closes the Phase 9.2 arc.
- **v2.404.0 "The Last Four Rows"** — Phase 9.3 umbrella-slug closure. 4 umbrella catalog slugs wired (potion-of-healing real heal handler with tier picker, spell-scroll real cast handler, weapon-1-2-or-3 + wand-of-the-war-mage-1-2-or-3 passive catalog stubs). Magic-items denominator from 235/239 → **239/239 = 100%**.

The session shipped **9 commits** end-to-end. Magic items joins Monsters + Class features + Races as a strictly-✅ surface.

### Per-category coverage (the headline numbers)

| Category | SRD count | Automated | Notes |
|---|---|---|---|
| Races | 9 | **✅ ~100%** | Unchanged. |
| Monsters | 322 | **✅ ~100%** | Unchanged. |
| Conditions | 15 | **~92%** | Unchanged. |
| Class features | **222 rows** | **✅ 100%** | Unchanged. |
| Spells | 319 | **~79%** | Unchanged. |
| Magic items | **239 / 239 wired** | **✅ 100%** | **+2 pts vs. v2.399.0 (~98% → 100%).** The v2.403.0–v2.403.7 Phase 9.2 arc wired charge tracking for 22 Bucket D + 2 Bucket A holdout items; v2.404.0 Phase 9.3 closed the 4 umbrella catalog slugs (potion-of-healing + spell-scroll real handlers; weapon-1-2-or-3 + wand-of-the-war-mage-1-2-or-3 passive stubs). Every SRD magic-item slug now resolves to a wiring entry. |

**Overall ~97%** automated across the SRD ruleset (unchanged headline % — Magic items was already in the 98% range; the meaningful change is that another category joins the strictly-✅ club, narrowing the remaining gap to just the utility-spell upcast tail + the permanently-GM-narrated condition clauses).

### Remaining gaps (priority order — toward full SRD automation)

After the v2.404.0 magic-items closure, the per-category gaps are genuinely small and substrate-shaped.

1. 🟡 **P2 — Cast-and-broadcast utility-spell upcast.** Unchanged. ~250 SRD utility spells with no damage/healing base — a subset could gain richer per-slot modeling. Substrate work, not engine.
2. 🟠 **Filed follow-up — Bucket D announce-only mechanization (Path C from the v2.403.x arc).** Roughly 60 SRD magic items have their catalog row + charge counter wired but their *effect* stays GM-narrated by design ("archetype J" per the v2.367.0 closure note). These need substrates SimpleVTT doesn't model: extradimensional storage math (bag-of-holding, handy-haversack, portable-hole, bag-of-devouring), item-summoned creatures (figurines, staff-of-the-python, dancing-sword, animated-shield), planar travel (amulet-of-the-planes, cubic-gate, well-of-many-worlds, cape teleport, plate-armor-of-etherealness, rod-of-security), capture-creature state (iron-flask, mirror-of-life-trapping), random-table dispatch (deck-of-many-things, deck-of-illusions, bag-of-beans rolls), multi-mode catalog entries (rod-of-lordly-might 6-button, candle-of-invocation, crystal-ball variants, necklace-of-prayer-beads), and reaction-charge items (rod-of-absorption, ring-of-evasion). Filed for the v3.x scope expansion. The audit row stays at 100% because catalog wiring is complete; what's left is mechanical *depth* of inherently-narrative items.
3. 🟠 **Filed follow-up — race-features Phases 1b/1c + 4b/5b + 7.** Unchanged. All filed in [`docs/plans/race-features.md`](plans/race-features.md).
4. ✅ **DONE — Magic-items closure arc (v2.403.0–v2.404.0).** All 239 SRD magic-item slugs now resolve to a wiring entry.
5. ✅ **DONE — Charmed-gate mirror onto `/cast_spell` + `/use_feature` (v2.399.2 reconciliation).** Unchanged.
6. ✅ **DONE — Race tail (v2.392.0–v2.399.0).** Unchanged.
7. ✅ **DONE — Condition-enforcement audit clauses #1–#4.** Closed v2.385.0–v2.390.0.
8. ✅ **DONE — Class-feature ⚪ tail.** Closed v2.368.0–v2.370.1.
9. ✅ **DONE — Spell area-effect automation.** Closed v2.373.0–v2.376.0.
10. ✅ **DONE — Spell upcast dice/heal scaling.** Effectively complete (v2.344.2 reconciliation).
11. ✅ **DONE — Magic-item content tail.** Closed v2.316.0–v2.344.0.
12. ✅ **DONE — Legendary + Lair Actions arc.** Closed end-to-end v2.159.32–v2.382.0.

### Out-of-scope (unchanged)

Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte stay future-3.x scope. **2024 rules + Mythic Actions** likewise stay future-3.x scope. **Charmed clause 2** (social-check advantage), **Grappled clause 3** (out-of-reach), **Deafened** (mostly hearing-narrative): permanently GM-narrated per the v2.384.0 audit doc — need substrates that don't exist.

### What's left to ship in SimpleVTT 2.x?

The SRD ruleset is now ~97% automated end-to-end. Four of six categories are strictly-✅ 100% (Races, Monsters, Class features, **Magic items** new in v2.404.0). The remaining ~3% is dominated by content-layer utility-spell richness + the substrate-dependent filed follow-ups. After those the SRD is essentially closed; the natural next-arc inflection is unchanged:

- **3.0 scope expansion** — post-SRD content (Tasha's, Xanathar's, 2024-PHB rule changes, Mythic Actions). **Plus the Bucket D announce-only mechanization arc** (filed gap #2 above) — extradimensional storage substrate, planar travel, sentient items, random-table dispatch, multi-mode catalog entries, reaction-charge items.
- **Polish + UX** — Manually Added P3 polish items + Combat / GM Tools sections.
- **Test-infrastructure hardening** — spell-validation suite Phase 5 + pytest-xdist parallelization.
- **Maps 2.0 / Stealth-cover substrates** — would unlock Phases 4b + 5b of race-features.

---

## SRD 5e Audit (v2.399.0 refresh)

**Audit scope.** Recomputed against the codebase as of v2.399.0, after the **v2.392.0 → v2.399.0 race-features arc** that closed the per-race trait tail end-to-end:

- **v2.392.0 "The Exhaled Storm"** — Dragonborn Breath Weapon endpoint.
- **v2.393.0 "The Bloodline Ledger"** — `docs/plans/race-features.md` plan + wiki surfacing.
- **v2.394.0 "The Second Look"** — 5th stale-audit reconciliation (Half-Orc Savage Attacks was already shipped v2.99.23; caught before duplicate code committed).
- **v2.395.0 "The Free Rebuke"** — Phase 1: Tiefling Infernal Legacy racial Hellish Rebuke (consumes the `hellish-rebuke` racial resource, not a spell slot).
- **v2.395.1 "The Calibrated Test"** — test-assertion fixes.
- **v2.396.0 "The Hewn Memory"** — Phase 2: Hill Dwarf Stonecunning (`POST /check_stonecunning` rolls `1d20 + INT + 2×PB`).
- **v2.396.1 "The Plain Halfling"** — test-assertion fix.
- **v2.397.0 "The Unburdened Stride"** — Phase 3: Hill Dwarf heavy-armor speed bypass (`_pc_heavy_armor_speed_penalty` + `_apply_heavy_armor_speed_penalty` folded into `_speed_walk_from_sheet`; installs the underlying PHB p.144 -10 substrate alongside the PHB p.20 Dwarf exemption in one ship).
- **v2.398.0 "The Tinker's Memory"** — Phase 6: Rock Gnome Artificer's Lore (`POST /check_artificers_lore` — twin of Stonecunning).
- **v2.399.0 "The Quiet Steps"** — Phases 4a + 5a: Halfling Nimbleness + Lightfoot Naturally Stealthy recognition flags on `/sheet-json`. Phases 4b + 5b (full enforcement) filed for the future Maps 2.0 / Stealth-cover substrate arcs.

The session shipped **9 commits** end-to-end, lifting Races from a long-standing ~90% to essentially closed for v2.x.

### Per-category coverage (the headline numbers)

| Category | SRD count | Automated | Notes |
|---|---|---|---|
| Races | 9 | **✅ ~100%** | **+10 pts vs. v2.390.0 (~90% → ~100%).** All 7 engine-shaped race traits now ship with at least a recognition flag (Phases 4a + 5a) or full enforcement (Phases 1 + 2 + 3 + 6 + Savage Attacks + Breath Weapon). Phase 4b/5b enforcement filed for the future Maps 2.0 / Stealth-cover arcs; out-of-scope-by-design traits (Rock Gnome Tinker, Elf Trance) intentionally not shipped per the [plan](plans/race-features.md). |
| Monsters | 322 | **✅ ~100%** | Unchanged. |
| Conditions | 15 | **~92%** | Unchanged. |
| Class features | **222 rows** | **✅ 100%** | Unchanged. |
| Spells | 319 | **~79%** | Unchanged. |
| Magic items | **235 / 239 wired** | **~98%** | Unchanged. |

**Overall ~97%** automated across the SRD ruleset (up from ~96% at v2.390.0 — the Races bump from ~90% → ~100% is the mover). Races joins Monsters + Class features as a strictly-✅ surface; the remaining ~3% is the long-known cast-and-broadcast utility-spell tail (P2) + the permanently-GM-narrated Charmed-social/Grappled-reach/Deafened-hearing clauses.

### Remaining gaps (priority order — toward full SRD automation)

After the v2.392.0–v2.399.0 race-features arc, the per-category gaps are genuinely small and substrate-shaped.

1. 🟡 **P2 — Cast-and-broadcast utility-spell upcast.** Unchanged from v2.390.0. ~250 SRD utility spells with no damage/healing base — a subset could gain richer per-slot modeling. Substrate work, not engine.
2. 🟠 **Filed follow-up — race-features Phases 1b/1c + 4b/5b + 7.** All filed in [`docs/plans/race-features.md`](plans/race-features.md): Tiefling Darkness 1/long racial cast (Phase 1b — needs `/cast_spell` racial-resource branch); auto-grant projection of Tiefling Infernal Legacy spells on `/sheet-json` (Phase 1c — architectural); Halfling Nimbleness full move-through-creature enforcement (Phase 4b — needs Maps 2.0 substrate); Naturally Stealthy full Stealth-cover gate (Phase 5b — needs Stealth-cover substrate); Elf Trance long-rest UI flavor (Phase 7 — pure polish).
3. ✅ **DONE — Charmed-gate mirror onto `/cast_spell` + `/use_feature` (v2.399.2 reconciliation).** Sixth stale-audit reconciliation in the v2.376.2 → v2.399.2 stretch. Per-site verification: `/cast_spell` was already mirrored in **v2.391.0** at `tabletop_routes.py:19706` (visible via `grep "charmed_cannot_target_charmer"`); `/use_feature` doesn't accept a `target_combatant_id` body field — it's structurally self-targeted (Action Surge, Channel Divinity buffs, Lay on Hands pool), so the Charmed-cannot-target-charmer rule is moot. The v2.391.0 changelog explicitly filed `/use_feature` as "not-applicable rather than not-done" with this exact rationale; the audit row never picked it up across the v2.391.0/v2.392.0/v2.399.0 refreshes. Closing now.
4. ✅ **DONE — Race tail (v2.392.0–v2.399.0).** Engine-shaped Races row at ~100% per the per-race plan table.
5. ✅ **DONE — Condition-enforcement audit clauses #1–#4.** Closed v2.385.0–v2.390.0.
6. ✅ **DONE — Class-feature ⚪ tail.** Closed v2.368.0–v2.370.1.
7. ✅ **DONE — Spell area-effect automation.** Closed v2.373.0–v2.376.0.
8. ✅ **DONE — Spell upcast dice/heal scaling.** Effectively complete (v2.344.2 reconciliation).
9. ✅ **DONE — Magic-item content tail.** Closed v2.316.0–v2.344.0.
10. ✅ **DONE — Legendary + Lair Actions arc.** Closed end-to-end v2.159.32–v2.382.0.

### Out-of-scope (unchanged)

Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte stay future-3.x scope. **2024 rules + Mythic Actions** likewise stay future-3.x scope. **Charmed clause 2** (social-check advantage), **Grappled clause 3** (out-of-reach), **Deafened** (mostly hearing-narrative): permanently GM-narrated per the v2.384.0 audit doc — need substrates that don't exist.

**Out-of-scope by design (race-features):** Rock Gnome Tinker (needs a crafting substrate — 1-hour craft, GP cost, clockwork-creature catalog). Race-trait Darkvision (already correctly seeded as `darkvision_ft: 60`; actual gameplay consequence lives in Maps 2.0).

### What's left to ship in SimpleVTT 2.x?

The SRD ruleset is now ~97% automated end-to-end. The remaining ~3% is dominated by content-layer utility-spell richness + the substrate-dependent filed follow-ups in (2) and (3). After those the SRD is essentially closed; the natural next-arc inflection is unchanged:

- **3.0 scope expansion** — post-SRD content (Tasha's, Xanathar's, 2024-PHB rule changes, Mythic Actions).
- **Polish + UX** — Manually Added P3 polish items + Combat / GM Tools sections.
- **Test-infrastructure hardening** — spell-validation suite Phase 5 + pytest-xdist parallelization.
- **Maps 2.0 / Stealth-cover substrates** — would unlock Phases 4b + 5b of race-features.

---

## SRD 5e Audit (v2.390.0 refresh)

**Audit scope.** Recomputed against the codebase as of v2.390.0, after the **v2.385.0 → v2.390.0 condition-enforcement sweep** that closed all six clauses surfaced by the v2.384.0 `docs/condition-enforcement-audit.md`:

- **v2.385.0 "The Conscious Ally"** — Sneak Attack ally-adjacency skips incapacitated allies (clause #1).
- **v2.386.0 "The Still Hand"** — `/attack` rejects 409 incapacitated (clause #2a).
- **v2.387.0 "The Quiet Tongue"** — `/cast_spell` rejects 409 incapacitated (clause #2b).
- **v2.388.0 "The Held Trick"** — `/use_feature` rejects 409 incapacitated (clause #2c). Completes the general action gate.
- **v2.389.0 "The Broken Hold"** — Grappled auto-ends when grappler becomes incapacitated (clause #3).
- **v2.390.0 "The Charmer's Shield"** — `/attack` rejects 409 when attacker is charmed by target (clause #4). The audit's per-clause shipping list is now **fully closed end-to-end**.

The shared `_combatant_is_incapacitated` predicate landed in v2.385.0 and was reused unchanged across 5 sites (Sneak Attack ally-skip + 3 action gates + Grappled-end sweep). The shared `_caster_is_incapacitated` helper landed in v2.386.0 and was reused unchanged across the 3 action gates. The audit doc's prediction held: a single predicate served every site without modification — the substrate-first design paid off.

### Per-category coverage (the headline numbers)

| Category | SRD count | Automated | Notes |
|---|---|---|---|
| Races | 9 | **~90%** | Unchanged. |
| Monsters | 322 | **✅ ~100%** | Unchanged from v2.382.0 — lair-action arc end-to-end complete. |
| Conditions | 15 | **~92%** | **+7 pts vs. v2.382.0 (~85% → ~92%).** All six clauses from the v2.384.0 audit doc closed across v2.385.0–v2.390.0. Specifically: Incapacitated → action gate enforced at `/attack` + `/cast_spell` + `/use_feature` + Sneak Attack ally-skip; Grappled clause 2 auto-fires; Charmed clause 1 enforced at `/attack`. **Remaining ~8% is permanently GM-narrated by design** (Charmed clause 2 social-check advantage + Grappled clause 3 out-of-reach movement + Deafened "auto-fail hearing checks") — these need substrates that don't exist (social-check engine, Reach-aware movement) and aren't planned for v2.x. |
| Class features | **222 rows** | **✅ 100%** | Unchanged. |
| Spells | 319 | **~79%** | Unchanged from v2.382.0. The remaining gap is cast-and-broadcast utility-spell richness; substrate-extensions only (Bless / Mass Healing Word / Bane caps all shipped v2.380.0–v2.383.0). |
| Magic items | **235 / 239 wired** | **~98%** | Unchanged. |

**Overall ~96%** automated across the SRD ruleset (up from ~95% at v2.382.0 — the Conditions bump from ~85% → ~92% is the mover). The remaining ~4% is dominated by **cast-and-broadcast utility-spell richness** (P2 below) + the permanently-GM-narrated Charmed-social/Grappled-reach/Deafened-hearing clauses (out-of-scope by design).

### Remaining gaps (priority order — toward full SRD automation)

After the v2.385.0–v2.390.0 sweep, the audit's per-clause shipping list is empty. The remaining engine-shaped gap is content-layer.

1. 🟡 **P2 — Cast-and-broadcast utility-spell upcast.** Unchanged from prior audits. ~250 SRD utility spells with no damage/healing base — a subset could gain richer per-slot modeling (Mass Suggestion / Heroes' Feast / etc.). Substrate work, not engine.
2. ✅ **DONE — `source_char_id` on charmed-buff install sites (v2.390.2 verification).** Verified after a per-install-site audit: the v2.32.0 save-resolution branch at `tabletop_routes.py:19048` already sets `source_char_id` from `ctx["caster_char_id"]` for all spell-cast charms (charm-person, suggestion). The item-action save handler at line 2187 already sets `source_char_id: int(char.id)` for item charms (Rod of Rulership, etc.). Lair-action installs fundamentally can't carry a `source_char_id` — the charmer is a monster (no char_id), so the gate is RAW-correctly silent for monster-source charms (GM-narrated by design). The v2.390.0 gate fires correctly for every realistic charm source out of the box.
3. 🟠 **Filed follow-up — mirror v2.390.0 onto `/cast_spell` + `/use_feature`.** The Charmed-can't-target-charmer gate is currently `/attack`-only. Mirror to the other two PC action endpoints (~10 lines each, mirrors the v2.387.0/v2.388.0 incapacitated-gate sweep).
4. ✅ **DONE — Condition-enforcement audit clauses #1–#4.** Closed v2.385.0–v2.390.0.
5. ✅ **DONE — Class-feature ⚪ tail.** Closed v2.368.0–v2.370.1.
6. ✅ **DONE — Spell area-effect automation.** Closed v2.373.0–v2.376.0.
7. ✅ **DONE — Spell upcast dice/heal scaling.** Effectively complete (v2.344.2 reconciliation).
8. ✅ **DONE — Magic-item content tail.** Closed v2.316.0–v2.344.0.
9. ✅ **DONE — Legendary + Lair Actions arc.** Closed end-to-end v2.159.32–v2.382.0.
10. ✅ **DONE — Hold Person / Hold Monster / Sleep refactor.** Reconciled v2.382.1; already uses shared `upcast_target_count` helper.

### Out-of-scope (unchanged)

Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte stay future-3.x scope. **2024 rules + Mythic Actions** likewise stay future-3.x scope. **Charmed clause 2** (social-check advantage), **Grappled clause 3** (out-of-reach), **Deafened** (mostly hearing-narrative): permanently GM-narrated per the v2.384.0 audit doc — need substrates that don't exist.

### What's left to ship in SimpleVTT 2.x?

The SRD ruleset is now ~96% automated end-to-end. The remaining ~4% is dominated by **content-layer utility-spell richness** + two small filed-follow-up gaps from the v2.390.0 ship (`source_char_id` backfill, /cast_spell+/use_feature charmed-gate mirror). After that the SRD is essentially closed; the natural next-arc inflection is:

- **3.0 scope expansion** — post-SRD content (Tasha's, Xanathar's, 2024-PHB rule changes, Mythic Actions).
- **Polish + UX** — Manually Added P3 polish items + Combat / GM Tools sections.
- **Test-infrastructure hardening** — spell-validation suite Phase 5 + pytest-xdist parallelization.

---

## SRD 5e Audit (v2.382.0 refresh)

**Audit scope.** Recomputed against the codebase as of v2.382.0, after the **v2.380.0 → v2.382.0 utility-spell + regional-effects close-out** sweep:
- **v2.380.0 "The Wider Bless"** — new `extra_targets_per_slot_above_base` / `base_level` fields on `_SPELL_BUFF_MAP` so per-slot target scaling can ride the existing v2.372.1 cap gate. Bless first consumer (3 base @ L1, +1/slot).
- **v2.381.0 "The Wider Heal"** — parallel `_SPELL_TARGET_CAPS` dict for heal-loop spells. Mass Healing Word + Mass Cure Wounds wired (both 6 base, fixed across upcast).
- **v2.381.1 "The Second Witness"** — Mass Cure Wounds dedicated harness coverage (PATCH sheet + L5 slot pattern).
- **v2.382.0 "The Living Map"** — 7 metallic + Lich + Kraken regional effects backfilled; `REGIONAL_EFFECTS_BY_SLUG` grows 10 → 22 slugs matching `LAIR_ACTIONS_BY_SLUG`'s coverage.

**Headline:** the **lair-action arc is fully closed end-to-end** — 22 lair-action slugs + 22 regional-effect slugs + 8 mapped condition-buff keys + every endpoint / UI / cadence guard / roll-log card / regional panel / fade tracker shipped v2.169.0–v2.382.0. The legendary-actions plan's filed-follow-ups list is **genuinely empty**.

**v2.382.1 reconciliation.** Verifying audit text before promoting — the **P3 Sleep / Hold Person / Hold Monster bespoke-constant refactor** carried forward from v2.379.0 is **already done**. Both endpoints (lines 82597, 83250 in `app/routes/tabletop_routes.py`) use the shared `upcast_target_count` helper from `app/content/spell_upcast_parse.py` (per the v2.127.0 extraction); the Sleep endpoint uses a separate but similarly-shared helper. Same stale-audit pattern that hit Aura of Courage (v2.376.2) and Legendary + Lair Actions (v2.376.2) — corrected here. The P3 row is dropped.

### Per-category coverage (the headline numbers)

| Category | SRD count | Automated | Notes |
|---|---|---|---|
| Races | 9 | **~90%** | Unchanged. |
| Monsters | 322 | **✅ ~100%** | **+1 pt vs. v2.379.0 (~99% → effectively 100%).** Lair-action arc end-to-end complete: 22 lair-action slugs + 22 regional-effect slugs + every condition auto-installs + every endpoint / UI / cadence guard / roll-log / regional panel / fade tracker shipped. The remaining ~0% is non-SRD post-2024 mythic actions + custom AoE shapes for homebrew lairs (out-of-scope per the legendary-actions plan's non-goals). |
| Conditions | 15 | **~85%** | Unchanged. |
| Class features | **222 rows** | **✅ 100%** | Unchanged. Strictly-✅ across every per-row entry. |
| Spells | 319 | **~79%** | **+1 pt vs. v2.379.0 (~78% → ~79%).** The v2.380.0/v2.381.0 cap substrates added per-slot target scaling to Bless + Mass Healing Word + Mass Cure Wounds (3 spells gained mechanically-enforced caps). Dice/heal upcast scaling remains effectively complete. Remaining: per-slot extras on a handful more utility spells (Bane needs the buff-vs-condition install-path refactor; True Strike / Identify / etc. could gain richer per-slot effect modeling). |
| Magic items | **235 / 239 wired** | **~98%** | Unchanged. The 4 unwired remain generic/meta slugs intentionally out-of-scope. |

**Overall ~95%** automated across the SRD ruleset (up from ~94% at v2.379.0 — the Monsters bump from ~99% → effectively 100% via the regional-effects close-out + the small Spells nudge from the cap substrates are the movers).

### Remaining gaps (priority order — toward full SRD automation)

After the v2.380.0–v2.382.0 close-out + the v2.382.1 P3 reconciliation, the remaining gaps are genuinely small and content-shaped.

1. 🟡 **P2 — Cast-and-broadcast utility-spell upcast (substrate-extended).** The v2.380.0/v2.381.0 substrates now exist; remaining work is wiring more spells onto them. Next-up candidates: Bane (target scaling + condition install — needs the install-path refactor that lets the buff-cap gate fire on condition spells), Telekinesis (no scaling RAW — skip), True Strike (cantrip — no upcast), Identify (no upcast RAW). The high-leverage targets are Mass Suggestion / Mass Polymorph / Heroes' Feast which have rich per-slot effects; their install pipelines are also more substantial.
2. ✅ **DONE — Hold Person / Hold Monster / Sleep bespoke-constant refactor (v2.382.1 reconciliation).** Verified — both endpoints already use the shared `upcast_target_count` helper (extracted in v2.127.0). The audit row was stale.
3. ✅ **DONE — Class-feature ⚪ tail.** Closed v2.368.0–v2.370.1.
4. ✅ **DONE — Spell area-effect automation.** Closed v2.373.0–v2.376.0.
5. ✅ **DONE — Spell upcast dice/heal scaling.** Effectively complete (v2.344.2 reconciliation).
6. ✅ **DONE — Magic-item content tail.** Closed v2.316.0–v2.344.0.
7. ✅ **DONE — Legendary + Lair Actions arc.** Closed end-to-end v2.159.32–v2.382.0.

### Out-of-scope (unchanged)

Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte stay future-3.x scope. **2024 rules + Mythic Actions** likewise stay future-3.x scope.

### What's left to ship in SimpleVTT 2.x?

The SRD ruleset is now ~95% automated end-to-end. The remaining ~5% is dominated by **content-layer utility-spell upcast extension** to a handful more spells (P2 above), which is incremental per-spell work on the substrates that already exist. The "what's the SRD missing?" question is essentially closed; the natural next-arc inflection is:

- **3.0 scope expansion** — post-SRD content (Tasha's class features, Xanathar's tools / racial feats, 2024-PHB rule changes, Mythic Actions, custom AoE shapes for homebrew lairs).
- **Polish + UX** — see the [Manually Added](#manually-added) section + the Combat / GM Tools sections below.
- **Test-infrastructure hardening** — see the [Test Infrastructure](#test-infrastructure) section.

---

## SRD 5e Audit (v2.379.0 refresh)

**Audit scope.** Recomputed against the codebase as of v2.379.0, after the **v2.377.0 → v2.379.0 lair-action arc closure** that landed (a) the 5 metallic dragon lairs (v2.377.0 "The Metallic Five"), (b) Lich + Kraken lairs (v2.378.0 "The Phylactery and the Deep" — every SRD legendary lair-bearing creature now has authored data), and (c) the condition-map closure mapping `unconscious` / `silenced` / `frightened` so the engine auto-installs the buff on failed lair-action saves (v2.379.0 "The Closed Condition Map"). After this sweep **the lair-action arc is end-to-end complete** — data + engine dispatch + UI + cadence guards (once-per-round + no-repeat + init-20 broadcast) + roll-log card + regional effects + fade tracker + condition closure. **Filed-follow-ups list on `legendary-actions.md` is empty.**

### Per-category coverage (the headline numbers)

| Category | SRD count | Automated | Notes |
|---|---|---|---|
| Races | 9 | **~90%** | Unchanged. |
| Monsters | 322 | **~99%** | **+1 pt vs. v2.376.0 (~98% → ~99%).** Lair-action data backfill arc closed (v2.377.0–v2.378.0 = +12 slugs to `LAIR_ACTIONS_BY_SLUG` for 22 total) + condition map closure (v2.379.0 maps the last 3 unmapped condition keys). The remaining ~1% is non-SRD post-2024 mythic actions + per-monster custom AoE shapes (half-cylinder, donut) for homebrew lair actions — out of scope per the legendary-actions plan's non-goals. |
| Conditions | 15 | **~85%** | Unchanged. The lair-action condition map closure (v2.379.0) is independent of the broader condition substrate — it shipped new lair-specific condition templates, not new core conditions. |
| Class features | **222 rows** | **✅ 100%** | Unchanged from v2.376.0 refresh. Strictly-✅ across every per-row entry. |
| Spells | 319 | **~78%** | Unchanged from v2.376.0 refresh. AoE auto-targeting arc closed; dice/heal upcast scaling effectively complete. Remaining: cast-and-broadcast utility spells (the long tail of spells with no damage/healing base to scale). |
| Magic items | **235 / 239 wired** | **~98%** | Unchanged. The 4 unwired remain generic/meta slugs intentionally out-of-scope. |

**Overall ~94%** automated across the SRD ruleset (up from ~93% at v2.376.2 — the Monsters bump from ~98% → ~99% via the lair-action arc closure is the mover).

### Remaining gaps (priority order — toward full SRD automation)

The SRD ruleset is now mature enough that the next substantive surfaces are either cleanup (no behavior change) or scope expansion (post-SRD).

1. 🟡 **P2 — Cast-and-broadcast utility-spell upcast.** Unchanged from v2.376.0. ~250 SRD spells (Detect Magic, Divination, Counterspell, Comprehend Languages, etc.) have no damage/healing base — but a subset (True Strike / Identify / Magic Weapon / etc.) could gain richer per-slot effect modeling (extra targets / longer durations / wider AoE). Pick 3–5 highest-leverage spells per commit. The single largest *engine-shaped* remaining surface.
2. 🟢 **P3 — Sleep / Hold Person / Hold Monster bespoke-constant refactor.** Unchanged. Migrate the three off per-endpoint constants (Hold Person uses a hardcoded `slot_level - 1` for max targets) onto a shared structured `upcast` param field per [`spell-upcasting.md`](plans/spell-upcasting.md). Pure cleanup; no behavior change.
3. ✅ **DONE — Class-feature ⚪ tail.** Closed v2.368.0–v2.370.1.
4. ✅ **DONE — Spell area-effect automation.** Closed v2.373.0–v2.376.0.
5. ✅ **DONE — Spell upcast dice/heal scaling.** Effectively complete (v2.344.2 reconciliation).
6. ✅ **DONE — Magic-item content tail.** Closed v2.316.0–v2.344.0.
7. ✅ **DONE — Legendary + Lair Actions (v2.376.2 reconciliation).** Phases 1+2+3 shipped end-to-end across v2.159.32 → v2.181.0. The v2.377.0–v2.378.0 lair-action data backfills extended `LAIR_ACTIONS_BY_SLUG` from 10 to 22 slugs (all SRD legendary lair-bearing creatures). The v2.379.0 condition-map closure auto-installs the last 3 unmapped condition keys. **Arc fully closed; filed-follow-ups list empty.**

### Out-of-scope (unchanged)

Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte stay future-3.x scope. **2024 rules + Mythic Actions** likewise stay future-3.x scope.

### What's left to ship in SimpleVTT 2.x?

The SRD ruleset is now ~94% automated end-to-end. The remaining ~6% is dominated by **content-layer utility-spell upcast** (P2 above) and one **engine-cleanup refactor** (P3). Neither is user-visible work — the game runs strictly-RAW for every shipped category. The natural next-arc inflection is:

- **3.0 scope expansion** — post-SRD content (Tasha's class features, Xanathar's tools / racial feats, 2024-PHB rule changes, Mythic Actions, custom AoE shapes for homebrew lairs).
- **Polish + UX** — see the [Manually Added](#manually-added) section for `🟢 P3` UI nits + the Combat / GM Tools sections below for big-feature buckets that don't have a plan doc yet.
- **Test-infrastructure hardening** — see the [Test Infrastructure](#test-infrastructure) section for the harness-suite stability + the spell-validation suite Phase 5 + the pytest-xdist parallelization filed work.

The "what's the SRD missing?" question is now a small list. The "what's next for the project?" question is now a scope decision, not a backlog drain.

---

## SRD 5e Audit (v2.376.0 refresh)

**Audit scope.** Recomputed against the codebase as of v2.376.0, after the **v2.345.0 → v2.376.0 sweep** that landed (a) Aura of Courage + Unarmored Defense + Deflect Missiles + Cleansing Touch (closing the class-feature ⚪ tail to **strictly-✅ 100%**), (b) Aid upcast + Dispel Magic + Aid 3-target cap (closing the named-spell P2 gap), and (c) the **AoE auto-targeting arc** (v2.373.0 sphere-targets faction filter → v2.373.1 cone+line picker parity → v2.374.0/.375.0/.376.0 `/cast_spell target_set` sphere+cone+line — server-side AoE target id resolution for every SRD AoE damage spell).

**v2.376.2 correction.** The v2.376.1 first cut of this refresh promoted "Legendary + Lair Actions" to P1 on the strength of the older 2026-06-11 audit text — but `docs/plans/legendary-actions.md` shows **Phases 1+2+3 are ALL shipped end-to-end (v2.159.32 → v2.181.0, closed 2026-06-12)** with the full lair-action arc (data + engine + GM UI + chromatic backfill + no-repeat guard + once-per-round counter + init-20 server broadcast + roll-log card + regional effects + player visibility + fade tracker). Same stale-doc pattern that hit the magic-item tail and the class-feature ⚪ tail in v2.344.2/.3. The single largest un-planned SRD surface is now genuinely small — see the corrected gap list below.

### Per-category coverage (the headline numbers)

| Category | SRD count | Automated | Notes |
|---|---|---|---|
| Races | 9 | **~90%** | Unchanged. |
| Monsters | 322 | **~98%** | **+13 pts vs. v2.376.1 first cut (corrected).** Stat blocks + attacks + legendary actions (Phase 1 v2.159.32–v2.164.0) + legendary resistance pool with auto-prompt (Phase 2 v2.165.0–v2.167.0) + lair actions full arc (Phase 3 v2.168.0–v2.181.0 including chromatic backfill + no-repeat / once-per-round guards + init-20 server broadcast + roll-log card + regional effects + fade tracker) all shipped. Remaining ~2% is the metallic-dragon lair-action / Lich / Kraken data backfill (filed follow-up; engine-supported, drop-in JSON). |
| Conditions | 15 | **~85%** | Unchanged. |
| Class features | **222 rows** | **✅ 100%** | **Aura of Courage flipped v2.368.0**, closing the last genuine ⚪ row noted in the v2.344.3 reconciliation. Auto-AC engine for Unarmored Defense v2.369.0; Deflect Missiles v2.370.0; Cleansing Touch picker v2.370.1. Class-feature SRD coverage is now strictly-✅ across every per-row entry. |
| Spells | 319 | **~78%** | **+6 pts vs. v2.344.1 (~72% → ~78%):** server-side AoE auto-targeting closed the "area-effect automation" lever (was the P2 spell gap). `/cast_spell` now resolves AoE target ids for sphere (v2.374.0), cone (v2.375.0), and line (v2.376.0) shapes with optional faction filtering. Dice/heal upcast scaling remains effectively complete (39/73 modeled-base leveled spells dice-scale via the v2.125.0 parser + structured fields; rest are RAW non-scalers). Remaining: 3 utility spells with non-dice upcast (Bestow Curse / Geas duration; Chain Lightning extra-beams — already wired) + ~250 cast-and-broadcast utility spells (no damage/healing base = nothing TO upcast). |
| Magic items | **235 / 239 wired** | **~98%** | Unchanged from v2.344.1. The 4 unwired remain generic/meta slugs intentionally out-of-scope. |

**Overall ~93%** automated across the SRD ruleset (up from ~88% at v2.344.1 — the Monsters jump from ~85% → ~98% via the now-recognised Legendary + Lair shipped state, the Spells jump from ~72% → ~78% via AoE auto-targeting, and the class-feature flip from ~99% → strictly-✅ 100% are the movers). The remaining ~7% is dominated by cast-and-broadcast utility spells (the ~250 base-less spells that have nothing to mechanize beyond broadcast) + the metallic-dragon / Lich / Kraken lair-action data backfill (drop-in, no engine change).

### Remaining gaps (priority order — toward full SRD automation)

The engine substrate is complete for every shipped category; the remaining items below are content/data backfill, not engine code.

1. 🟡 **P2 — Cast-and-broadcast utility-spell upcast.** ~250 SRD spells (Detect Magic, Divination, Counterspell, Comprehend Languages, etc.) have no damage/healing base, so they have nothing to upcast-scale in the dice/heal sense — but a subset (Bless / Bane already wired; Aid already wired v2.372.0; True Strike; Identify) could gain richer per-slot effect modeling (extra targets / longer durations / wider AoE). Pick the next 3–5 highest-leverage spells and ship per-spell substrates.
2. 🟡 **P2 — Lair-action data backfill (metallic dragons + Lich + Kraken).** Engine + UI + roll-log card + regional effects already ship (the Phase 3 arc closed at v2.181.0 with regional-effects fade tracker). The remaining work is **JSON-only** — fold the metallic dragon lairs, Lich phylactery effects, and Kraken submerged lair into `app/content/lair_actions.py` `LAIR_ACTIONS_BY_SLUG`, mirroring the v2.171.0 chromatic backfill pattern. No code change.
3. 🟢 **P3 — Sleep / Hold Person / Hold Monster bespoke-constant refactor.** Migrate the three off per-endpoint constants (Hold Person uses a hardcoded `slot_level - 1` for max targets) onto a shared structured `upcast` param field per [`spell-upcasting.md`](plans/spell-upcasting.md). Pure cleanup; no behavior change.
4. ✅ **DONE — Class-feature ⚪ tail.** Closed v2.368.0–v2.370.1 (Aura of Courage / Unarmored Defense / Deflect Missiles / Cleansing Touch). Strictly-✅ 100%.
5. ✅ **DONE — Spell area-effect automation.** Closed v2.373.0–v2.376.0 (sphere + cone + line picker faction filter + `/cast_spell target_set` parity).
6. ✅ **DONE — Spell upcast dice/heal scaling.** Effectively complete (v2.344.2 reconciliation).
7. ✅ **DONE — Magic-item content tail.** Closed v2.316.0–v2.344.0. 235/239 wired; 4 generic/meta slugs intentionally out-of-scope.
8. ✅ **DONE — Legendary + Lair Actions (v2.376.2 reconciliation).** Phases 1+2+3 shipped end-to-end across v2.159.32 → v2.181.0, including the entire lair-action arc (regional effects + fade tracker). See [`legendary-actions.md`](plans/legendary-actions.md). The 2026-06-11 audit's "P1 — no plan doc today" line was stale through every subsequent refresh; corrected here.

### Out-of-scope (unchanged)

Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte stay future-3.x scope.

---

## SRD 5e Audit (v2.344.1 refresh)

**Audit scope.** Recomputed directly from the content JSON (`app/data/local/dnd5e/items/`, 294 equipment files) + the three magic-item registry dicts in `app/routes/tabletop_routes.py` as of v2.344.1, after the v2.316.0→v2.344.0 magic-item content sprint (Sword of Life Stealing through "The Armory's Remainder"). This pass records that **the magic-item content tail is now closed**. A follow-up correction in **v2.344.2** found the spell upcast dice/heal scaling is *also* effectively complete (the prose parser covers it — see the Spells row). A further reconciliation in **v2.344.3** found the **class-feature ⚪ tail was likewise stale** — 22 of 24 rows were already shipped (v2.99.197–.221) and just never flipped. After all three corrections the SRD ruleset is **~88% automated**, and the single remaining genuine gap is **Aura of Courage** (Paladin Lv 10/18).

### Per-category coverage (the headline numbers)

| Category | SRD count | Automated | Notes |
|---|---|---|---|
| Races | 9 | **~90%** | Unchanged from v2.315.0. |
| Monsters | 322 | **~85%** | Unchanged. |
| Conditions | 15 | **~85%** | Unchanged. |
| Class features | **222 rows** | **~99%** | **Reconciliation correction (v2.344.3):** the prior ~81% / "24 ⚪ rows" was stale doc-status, not missing code. 22 of those 24 rows were already shipped end-to-end (v2.99.197–.221, each with a dedicated harness test) but never flipped from ⚪ in [`class-content-status.md`](plans/class-content-status.md). All flipped to ✅ (Deflect Missiles → 🟢). **The lone genuine ⚪ is Aura of Courage** (Paladin Lv 10/18) — no code/test. |

| Spells | 319 | **~72%** | **Upcast scaling correction (v2.344.2):** the prior "~110 lack upcast scaling" figure counted spells lacking the *structured field*, not spells lacking *scaling* — the v2.125.0 prose parser derives per-slot dice from `higher_level` at cast time. Of 73 leveled spells with a modeled base, **39 dice-scale automatically** (32 structured + 7 parser); the other 34 carry no per-slot dice clause because RAW they don't dice-scale (Finger of Death, Meteor Swarm, Sunburst) or scale by count/duration/area handled elsewhere. **Dice/heal upcast scaling is effectively complete.** The remaining spell gap is area-effect automation + cast-and-broadcast utility spells, not upcast. |
| Magic items | **235 / 239 wired** | **~98%** | **Up from 123/239 (~51%) at v2.315.0.** The v2.316–v2.344 content sprint wired the entire tail. The only 4 unwired are the generic/meta slugs (`potion-of-healing`, `spell-scroll`, `weapon-1-2-or-3`, `wand-of-the-war-mage-1-2-or-3`) — intentionally **not** discrete collectibles. Effectively **100% of discrete SRD magic items** are now wired. |

**Overall ~88%** automated across the SRD ruleset (up from ~75% at v2.315.0 — the magic-item jump from ~51% → ~98% and the class-feature correction from ~81% → ~99% are the movers).

### How the count was computed

294 equipment files = 239 magic items + 37 mundane weapons + 18 mundane armor (the mundane rows need no magic wiring). Distinct wired slugs across `_MAGIC_ITEM_PASSIVES` (176) + `_MAGIC_ITEM_ACTIONS` (51) + `_MAGIC_ITEM_ATTACK_RIDERS` (17) = 241, of which 235 map onto SRD item files. 239 − 235 = 4 unwired, all generic/meta. Most are catalog-stub passives (mechanics GM-narrated in v1); ~70 have full mechanical handlers (on-hit riders, charge-with-spell, nat-20 hooks, ability-overrides, action dispatchers).

### Remaining gaps (priority order — toward full SRD automation)

The engine substrate is complete; everything below is content/scaling-data, not engine code.

1. 🔴 **P1 — Aura of Courage (Paladin Lv 10/18).** The single remaining genuine ⚪ class feature after the v2.344.3 reconciliation. RAW: the paladin + friendly creatures within 10 ft (30 ft at Lv 18) can't be frightened while the paladin is conscious. Build it on the `_aura_of_protection_bonus` init-walk pattern as a frightened-immunity aura + a `feature_used(source=aura-of-courage)` broadcast. One real code commit + harness test.
2. 🟡 **P2 — Spell area-effect + utility automation.** With dice/heal upcast scaling complete (below), the remaining spell lever is automating area-of-effect targeting and the cast-and-broadcast-only utility spells.
3. 🟢 **P3 — Class-feature test-hygiene + bespoke upcast refactor.** (a) ✅ **Capstone seed-drift fixed v2.368.1** — `test_persistent_rage` long-rests Krieger first; `test_select_spell_mastery` + `test_select_signature_spells` level-gate tests PATCH Thalindra to seed Lv 7 first. (b) Migrate Sleep / Hold Person / Hold Monster off per-endpoint constants onto a shared structured `upcast` param field. See [`spell-upcasting.md`](plans/spell-upcasting.md).
4. ✅ **DONE — Class-feature ⚪ tail.** Reconciled v2.344.3 — 22 of 24 "⚪" rows were already shipped (v2.99.197–.221); flipped to ✅ in [`class-content-status.md`](plans/class-content-status.md). Only Aura of Courage remains (now P1 above).
5. ✅ **DONE — Spell upcast dice/heal scaling.** Effectively complete via structured fields + the v2.125.0 prose parser (39/73 modeled-base leveled spells dice-scale; the rest are RAW non-scalers or count/duration scalers). Corrected v2.344.2 — see the Spells row above.
6. ✅ **DONE — Magic-item content tail.** Closed across v2.316.0–v2.344.0. Only the 4 generic/meta slugs remain, which are intentionally out of scope.

### Out-of-scope (unchanged)

Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte stay future-3.x scope.

---

## SRD 5e Audit (v2.315.0 refresh)

**Audit scope.** Fifth pass against `app/data/local/dnd5e/`, recomputed directly from the content JSON + the three magic-item registry dicts in `app/routes/tabletop_routes.py` as of v2.315.0. This pass exists to answer one question — *what percentage of the SRD does SimpleVTT mechanically automate, per category* — and to **correct two denominators** that every prior audit carried forward incorrectly. Excludes setting-specific / post-SRD content (Tasha's, Xanathar's-beyond-SRD, Strixhaven) and homebrew, same as prior passes.

### Per-category coverage (the headline numbers)

| Category | SRD count | Automated | Notes |
|---|---|---|---|
| Races | 9 | **~90%** | Racial passives + speed + darkvision derived; a few flavor traits GM-narrated. |
| Monsters | 322 | **~85%** | Stat blocks + attacks + legendary/lair actions + legendary resistance all engine-driven. |
| Conditions | 15 | **~85%** | Mechanical conditions enforce; exhaustion ladder shipped. |
| Class features | **222 rows** (179 ✅ / 19 🟡 / 24 ⚪) | **~81%** | Denominator corrected from the stale "133". Tail is Barbarian Lv 9–20, Monk capstones, Ranger Lv 10–20, Rogue Reliable Talent / Stroke of Luck. |
| Spells | 319 | **~70%** | Catalog 319/319; 116 have save dispatch, 76 damage, 27 area, 29 upcast scaling. ~110 cast-and-broadcast-only spells still lack upcast scaling. |
| Magic items | **123 / 239 wired** | **~51%** | Denominator corrected: 294 equipment rows = 239 magic + 37 mundane weapons + 18 mundane armor. Wiring across `_MAGIC_ITEM_ACTIONS` (47) + `_MAGIC_ITEM_PASSIVES` (71) + `_MAGIC_ITEM_ATTACK_RIDERS` (8); 123 distinct slugs (3 span two layers). |

**Overall ~75%** automated across the SRD ruleset.

### Denominator corrections (why the numbers moved up)

- **Magic items: 292 → 239 denominator.** Prior passes divided the wired count by 292, which was the *total equipment* row count (it bundled 37 mundane weapons and 18 mundane armor that are not "magic items" and need no passive wiring). The honest denominator is the 239 magic-item rows. With 123 distinct slugs wired, coverage is **~51%**, not the ~34% the v2.314-era TODO reported.
- **Class features: 133 → 222 denominator.** The "133" was a stale count from an early class-content snapshot. The living inventory in [`class-content-status.md`](docs/plans/class-content-status.md) now enumerates **222 per-row entries** (179 ✅ shipped / 19 🟡 partial / 24 ⚪ unstarted) = **~81%**.

### Remaining gaps (priority order — toward full SRD automation)

The engine substrate (actions / passives / attack-riders / ability-override / buff / save-dispatch / upcast) is complete. Every remaining item below is **content drop-in or scaling-data**, not new engine code.

1. 🔴 **P1 — Magic-item content tail (116 items).** The single biggest lever on the overall %. 116 of 239 SRD magic items remain GM-narrated. Each fits an existing template (on-hit rider, charge-with-spell, passive buff, nat-20 hook, ability-override, boolean derived flag). Ship in ~10–15-item batches, each its own MINOR commit + 3 harness tests.
2. 🟡 **P2 — Spell upcast scaling (~110 spells).** Add `damage_per_slot` / scaling data to the cast-and-broadcast-only spells so higher-slot casts scale automatically. Moves Spells from ~70% → ~90%+.
3. 🟢 **P3 — Class-feature ⚪ tail (24 rows).** Barbarian Lv 9–20, Monk Deflect Missiles / Diamond Soul / Empty Body / Perfect Self, Ranger Lv 10–20 (minus Vanish), Rogue Reliable Talent / Slippery Mind / Elusive / Stroke of Luck.

### Out-of-scope (unchanged)

Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte stay future-3.x scope.

---

## SRD 5e Audit (2026-06-14 refresh)

**Audit scope.** Fourth pass against `app/data/local/dnd5e/`, capturing the window from v2.222.0 → v2.284.0. The defining event is the **charged-items plan closing all phases (0–5)** — the magic-item wiring count was re-counted directly by AST-parsing the three registry dicts in `app/routes/tabletop_routes.py`. The tail of the window (v2.280.0–v2.284.0) closed the **SRD movement/levitation item family** on the passive substrate. Excludes setting-specific / post-SRD content (Tasha's, Xanathar's-beyond-SRD, Strixhaven) and homebrew, same as prior passes.

### Headline state (delta vs 2026-06-13)

| Layer | SRD count | 2026-06-13 | 2026-06-14 | % | Movement |
|---|---|---|---|---|---|
| Magic items | 292 | ~49 wired | **100 distinct wired** | **~34%** | **47 `_MAGIC_ITEM_ACTIONS` + 48 `_MAGIC_ITEM_PASSIVES` + 8 `_MAGIC_ITEM_ATTACK_RIDERS`** (3 slugs span two layers). Charged-items plan ✅ closed all phases; the v2.280.0–v2.284.0 tail closed the movement/levitation family — Helm of Brilliance (fire resistance), Wings of Flying, Broom of Flying, Carpet of Flying (all on the `flying_speed` flag), and Boots of Levitation (NEW `levitate_at_will` flag). |
| Spells | 319 | ~70% | ~70% | ~70% | No movement this window. Catalog 319/319; ~18 validation suites CI-gated. |
| Monsters | 322 | ~85% | ~85% | ~85% | No movement. Legendary actions / resistance / lair actions all ✅. |
| Conditions | 15 | ~85% | ~85% | ~85% | No movement. |
| Class features | 133 | ~82% | ~82% | ~82% | No movement this window. |
| Races | 9 | ~90% | ~90% | ~90% | No movement. |
| Ability-score override engine | — | ✅ shipped | ✅ shipped | — | Stable. |

### What closed since 2026-06-13

✅ **Charged-items plan — all phases (0–5)** ([plan ✅](docs/plans/charged-items.md)) — every named item on the plan shipped on the mature charge engine (`_MAGIC_ITEM_ACTIONS` + `/use_item_action` + per-slug dispatch + the generalized `action_kind: "buff"` substrate). Final commits: Staff of Power (v2.274.0), Wand of Wonder (v2.273.0), Staff of Thunder & Lightning, Wand of the War Mage +3 (v2.276.0, completing the +1/+2/+3 tier set), Wand of Enemy Detection (v2.277.0). Zero new engine code required for the last items — pure content drop-ins.

✅ **SRD movement/levitation item family** (v2.280.0–v2.284.0) — closed the passive-flag movement items on the shipped `flying_speed` substrate (v2.238.0 Winged Boots) plus one new flag. Helm of Brilliance (fire resistance via the resistance substrate, v2.280.0); Wings of Flying (attunement), Broom of Flying (no attunement), Carpet of Flying (no attunement) — all on `flying_speed` with zero new engine code (v2.281.0–v2.283.0); Boots of Levitation (v2.284.0) landed the **NEW `levitate_at_will` boolean derived flag** (init / walker boolean-OR / `/sheet-json` projection), the reusable surface for future "cast X at will" items. Each shipped as inert spare loot on a thematically-fit demo PC + 3 harness tests.

### Remaining gaps (re-prioritized)

The substrate (actions / passives / attack-riders / ability-override / buff) is complete. All remaining magic-item work is content drop-ins with no new engine code.

🟡 **P2 — Magic-item action backfill long tail.** ~197 of 292 SRD items still have no code-side wiring (down from ~245). Most are weightless/flavor or one-off mechanics. Pick the next ~10–15-item batch that fits an existing template (on-hit riders, charge-with-spell, passive buff, nat-20 hook, ability-override).

🟡 **P2 — Ability-score engine drop-in tail (small).** Still trivially absorbed: giant-tier Belts (Stone/Frost STR 23, Fire 25, Cloud 27, Storm 29) and the Ioun Stone ability variants. Each ~1 commit on the shipped engine.

🟡 **P2 — Spell-validation suite finishers.** Upcast scaling on the ~110 cast-and-broadcast-only spells.

🟡 **P2 — Wizard capstone Spell Mastery / Signature Spells, Aura of Courage, Reactions v3 pending-damage state machine, Sorcerer Quickened Spell.** Unchanged.

🟢 **P3 — Eldritch Knight Phase 2 read sites; class-feature ⚪ tail** (Barbarian Lv 9–20, Monk Deflect Missiles / Diamond Soul / Empty Body / Perfect Self, Ranger Lv 10–20 minus Vanish, Rogue Reliable Talent / Slippery Mind / Elusive / Stroke of Luck). Unchanged.

### Out-of-scope (unchanged)

Same as prior passes: Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte stay future-3.x scope.

---

## SRD 5e Audit (2026-06-13 refresh)

**Audit scope.** Third pass against `app/data/local/dnd5e/` capturing the delta over ~63 MINOR/PATCH releases between v2.159.30 → v2.222.0 (the largest single window so far). Re-shapes the [Design Plans Backlog](#design-plans-backlog) priorities. Excludes setting-specific / post-SRD content (Tasha's, Xanathar's-beyond-SRD, Strixhaven, etc.) and homebrew, same as the prior passes.

### Headline state (delta vs 2026-06-11)

| Layer | 2026-06-11 coverage | 2026-06-13 coverage | Movement |
|---|---|---|---|
| Spells (319 SRD) | ~66% mechanical | ~70% mechanical | Spell-validation suite went from 1 catalog test (Fire Bolt) to **~18 catalog suites** (loader, smoke, damage, exact-damage, save, save-damage, attack, heal, conditions, concentration, range, aoe, aoe-placement, autohit, multibeam, buff-install, buff-effects, upcast) — CI-gated catalog drift is now broad. |
| Monsters (322 SRD) | ~75% mechanical | ~85% mechanical | **Legendary actions, legendary resistance, AND lair actions all ✅** — the 2026-06-11 audit's NEW #1 P1 surface, closed end-to-end v2.159.32–v2.167.0. |
| Conditions (15/15) | ~85% | ~85% | No movement. |
| Items (292 SRD) | ~50% framework + 42 wired | framework ✅ + **~49 items wired in code** (35 `_MAGIC_ITEM_ACTIONS` + 10 `_MAGIC_ITEM_PASSIVES` + 6 `_MAGIC_ITEM_ATTACK_RIDERS`) | Content tail still the long pole, but the **NEW ability-score override engine** (below) added a whole item class. |
| Ability-score override engine (NEW) | not audited | ✅ shipped | RAW `max(base, set)` runtime engine + 6 drop-ins: Belt of Giant Strength (Hill), Amulet of Health, Headband of Intellect, Gauntlets of Ogre Power, Potion of Giant Strength (tiered), Manuals & Tomes (permanent +2). v2.211.0–v2.222.0. |
| Class features (133) | ~82% | ~82% | No movement this window. |

### What closed since 2026-06-11

✅ **Legendary actions + legendary resistance + lair actions** ([plan ⚪→✅](docs/plans/legendary-actions.md)) — the prior audit's NEW #1 P1, shipped v2.159.32–v2.167.0: per-round action-point budget, `/use_legendary_action` dispatch (attack + AoE-save shapes + chat card), a 3/day legendary-resistance pool with deferred failed-save interception (`/spend_legendary_resistance` + `/decline_legendary_resistance` + GM prompt banner), and curated `lair_actions` data + `/trigger_lair_action` (initiative-20 trigger, AoE dispatch, GM banner). The single biggest un-planned SRD surface from the prior audit is now closed.

✅ **Ability-score override engine + 6 drop-in items** ([plan ⚪→✅](docs/plans/str-override.md)) — a surface that wasn't on any prior audit. RAW `max(base, set)` runtime semantics via `effective_ability_score`, routed through every read site (saves, checks, sheet card, carry capacity, `/sheet-json`). Drop-ins: Belt of Giant Strength (Hill, STR 21), Amulet of Health (CON 19, with boosted-max-HP threading into combat + all rest/heal paths), Headband of Intellect (INT 19), Gauntlets of Ogre Power (STR 19), Potion of Giant Strength (tiered timed buff), and the six Manuals & Tomes (DMG pp.180/208) as a permanent base-score `permanent_boost` archetype. v2.211.0–v2.222.0.

✅ **Spell-validation suite — most of it** ([plan 🟠](docs/plans/spell-validation-suite.md)) — the 2026-06-11 audit's carry-over P1. From a single Fire Bolt slice to ~18 catalog suites covering loader/damage/save/attack/heal/conditions/concentration/range/aoe/upcast and more. The CI-gated drift net the prior audits kept asking for is now largely in place.

✅ **Magic-item action backfill — continued** (Phase 9 of [magic-items-automation](docs/plans/magic-items-automation.md)) — ~49 items now wired in code (vs 42). New since the prior audit: Potion of Heroism / Resistance / Mind Reading / Diminution, Wand of Lightning Bolts / Paralysis, Eyes of Charming, Stone of Good Luck, Staff of Fire, plus the ability-score passives above.

### Remaining gaps (re-prioritized)

With magic-item framework, legendary/lair actions, and the ability-score engine all closed, there is **no single headline P1 surface left** — the remaining work is breadth (content tails) and a handful of mid-size class/spell features.

🟡 **P2 — Magic-item action backfill long tail.** ~245 of 294 SRD items still have no code-side wiring. The framework + templates are all in place; each remaining item is a content commit. Bag of Devouring is shipped; pick the next ~10–15-item batch from the Phase 1–8 templates (on-hit riders, charge-with-spell, passive buff, nat-20 hook).

🟡 **P2 — Ability-score engine drop-in tail (NEW, small).** The override substrate now trivially absorbs: the **giant-tier Belts** (Stone/Frost STR 23, Fire 25, Cloud 27, Storm 29 — one passive row + demo seed each) and the **Ioun Stone ability variants** (Strength/Dexterity/Constitution/Intelligence/Wisdom/Charisma — +2-to-max-20 equipped boost). Each is a ~1-commit slice on the shipped engine.

🟡 **P2 — Spell-validation suite finishers.** The catalog suites are broad now; remaining work is closing the specific cast paths still flagged partial (upcast scaling on the ~110 cast-and-broadcast-only spells).

🟡 **P2 — Wizard capstone Spell Mastery / Signature Spells, Aura of Courage, Reactions v3 pending-damage state machine, Sorcerer Quickened Spell.** Unchanged from 2026-06-11.

🟢 **P3 — Eldritch Knight Phase 2 read sites; class-feature ⚪ tail** (Barbarian Lv 9–20, Monk Deflect Missiles / Diamond Soul / Empty Body / Perfect Self, Ranger Lv 10–20 minus Vanish, Rogue Reliable Talent / Slippery Mind / Elusive / Stroke of Luck). Unchanged.

### Removed from gap list (since shipped)

- ~~Legendary actions + lair actions~~ — closed (the prior audit's NEW #1 P1).
- ~~Legendary resistance~~ — closed.
- ~~Spell-validation suite Phase 1+~~ — mostly closed (broad catalog coverage; only cast-path finishers remain).

### Out-of-scope (unchanged)

Same as the prior passes: Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats, backgrounds beyond Acolyte stay future-3.x scope. Out-of-scope-by-design RAW-narrative features unchanged.

---

## SRD 5e Audit (2026-06-11 refresh)

**Audit scope.** Follow-up pass against `app/data/local/dnd5e/` after the [2026-06-10 audit](#srd-5e-audit-2026-06-10). Captures the delta over ~60 commits between v2.158.69 → v2.159.30 and re-shapes the [Design Plans Backlog](#design-plans-backlog) priorities. Excludes setting-specific / post-SRD content (Tasha's, Xanathar's-beyond-SRD, Strixhaven, etc.) and homebrew, same as the prior pass.

### Headline state (delta vs 2026-06-10)

| Layer | 2026-06-10 coverage | 2026-06-11 coverage | Movement |
|---|---|---|---|
| Spells (319 SRD) | ~66% mechanical | ~66% mechanical | No movement (spell-validation suite Phase 1+ still pending). |
| Monsters (322 SRD) | ~75% mechanical | ~75% mechanical | Legendary actions still ⚪ (15 monsters carry data; engine has no dispatch). **NEW P1 surface this audit.** |
| Conditions (15/15) | ~70% (Exhaustion single-flag) | ~85% (Exhaustion ✅ 6-level) | Exhaustion levels closed v2.159.17–.22. |
| Items (292 SRD) | <25% (every `actions: []`) | ~50%+ (framework ✅ + 42 of 292 items wired) | Phases 1–8 ✅ v2.158.74–v2.159.25. Content tail (~250 items) now P2. |
| Class features (133) | ~80% | ~82% | Berserker Frenzy + non-Devotion Lv 15/20 + Battle Master 16/16 + Pact Boon all ✅. |
| Carrying capacity (NEW) | not audited | ✅ shipped | RAW STR × 15 engine + Bag of Holding ✅ v2.159.26–.30. |

### What closed since 2026-06-10

✅ **Magic-items-automation Phases 1–8** ([plan ⚪→✅](docs/plans/magic-items-automation.md)) — shipped end-to-end across v2.158.74 → v2.159.25 (32 PATCH commits) + v2.159.0 MINOR milestone. Framework closed: passives → attunement → actions → on-hit riders → AoE shapes → ammunition. The content tail (~250 of 292 items still have `actions: []`) is the new P2 below.

✅ **Exhaustion-levels Phases 1–4** ([plan ⚪→✅](docs/plans/exhaustion-levels.md)) — shipped v2.159.17 → v2.159.22: `set_exhaustion` endpoint, 6-level integer field, disadvantage wiring (Lv 1/3), speed wiring (Lv 2/5), HP-max halving (Lv 4), Berserker Frenzy rage-end hook, JS-side speed mirror.

✅ **Carrying-capacity Phases 0–3** ([plan ⚪→✅](docs/plans/carrying-capacity.md)) — not surfaced in the 2026-06-10 audit; surfaced + shipped during the magic-items wave. STR × 15 capacity engine, `/sheet-json` exposure, 12-PC weight backfill, carry meter UI, Bag of Holding.

✅ **Battle Master 16/16 maneuvers** ([plan 🟠→✅](docs/plans/battle-master.md)) — 2026-06-10 audit kept this in P2 but 16/16 maneuvers had actually shipped at v2.99.266 (v-numbers pre-dated the audit; header missed). Refreshed in this audit.

✅ **Warlock Pact Boon** ([plan ⚪→✅](docs/plans/warlock-pact-boon.md)) — same story. Tome v2.99.200 + Blade v2.99.212 + Chain v2.99.213 all shipped pre-audit; header missed. Refreshed.

✅ **Non-Devotion Paladin Lv 15/20 capstones** ([plan refresh](docs/plans/paladin-oaths.md)) — 2026-06-10 audit kept these as P3 outstanding; actually shipped v2.99.283 → v2.99.292 (Undying Sentinel, Soul of Vengeance, Scornful Rebuke, Glorious Defense, Protective Spirit, Elder Champion, Avenging Angel, Invincible Conqueror, Living Legend, Emissary of Redemption — 10 capstones in one batch). Header refreshed. Outstanding scope shrinks to Conquest Lv 3/7 + Redemption Lv 3 + Glory Lv 3 + Vengeance Phase 2 OA-flow.

### NEW headline gap (RAW-implementable, no system blocker)

🔴 **P1 — Legendary actions + lair actions (NEW — no plan doc today).** 15 SRD monsters carry `legendary_actions` data arrays (ancient red/silver/gold/bronze/copper/green/white dragons, lich, vampire, tarrasque, kraken, mummy lord, solar, androsphinx, unicorn) but the engine has no `/use_legendary_action` dispatch, no legendary-resistance pool (RAW: 3/day auto-pass on a failed save), and no per-round legendary-action point budget (RAW: 3 action points / round, refresh at end of each non-legendary turn). Zero monsters carry `lair_actions` data despite RAW SRD specifying them on the same roster (initiative count 20 trigger; thematic environmental effect each round in lair). Today a GM running an ancient dragon adjudicates these by hand. **Suggested approach:** write `docs/plans/legendary-actions.md`; first slice plumbs the action-point budget + a `/use_legendary_action` dispatch reusing the `/npc_attack` pipeline for the attack-shape actions (Tail / Wing / Claw); defer save-shape actions (Frightful Presence, Detect) until on-monster reactions land. Lair actions ship as a separate Phase 2 once the data layer carries them. This is the single biggest un-planned SRD surface left, now that magic items + exhaustion are closed.

### Carry-over P1/P2/P3 (unchanged from 2026-06-10)

🔴 **P1 — Spell-validation suite Phase 1+** ([`docs/plans/spell-validation-suite.md`](docs/plans/spell-validation-suite.md)). 4 spell-specific harness tests for 319 spells (`test_spell_catalog_damage`, `test_spell_catalog_loader`, `test_spell_condition_catalog_confusion_banishment`, `test_spell_upcast_parser`). CI-gated catalog drift remains the cheapest way to lock spell mechanics. No movement since 2026-06-10.

🟡 **P2 — Magic-item action backfill (NEW — Phase 9 of magic-items-automation).** 250 of 292 SRD items still carry `actions: []`. The framework is in place; each remaining item is a content commit picking from the existing Phase 1–8 templates (Potion of Heroism → passive buff; Potion of Healing → spell-effect dispatch; Wand of Polymorph / Lightning Bolts → charges-with-spell; Frost Brand / Flame Tongue → on-hit rider; Vorpal Sword / Hammer of Thunderbolts → nat-20 hook). Estimate: ~10–15 items per commit; ~20 commits to close the long tail. Bag of Devouring (paired counterpart to Bag of Holding) is the natural first slice.

🟡 **P2 — Wizard capstone Spell Mastery / Signature Spells (Lv 18/20).** Unchanged.

🟡 **P2 — Aura of Courage (Paladin Lv 10/18).** Unchanged.

🟡 **P2 — Reactions v3 pending-damage state machine** ([`docs/plans/reactions-automation.md`](docs/plans/reactions-automation.md) v3 backlog). Unchanged.

🟡 **P2 — Sorcerer Quickened Spell.** Unchanged.

🟢 **P3 — Eldritch Knight Phase 2 read sites** ([`docs/plans/eldritch-knight.md`](docs/plans/eldritch-knight.md)). Unchanged.

🟢 **P3 — Class-feature ⚪ tail.** Unchanged (Barbarian Lv 9–20, Monk Deflect Missiles / Diamond Soul / Empty Body / Perfect Self, Ranger Lv 10–20 minus Vanish, Rogue Reliable Talent / Slippery Mind / Elusive / Stroke of Luck).

### Removed from gap list (since shipped)

- ~~Magic-items-automation~~ — closed (framework; content tail moved to P2).
- ~~Exhaustion-level tracking~~ — closed.
- ~~Pact Boon~~ — closed.
- ~~Battle Master 15 maneuvers~~ — closed.
- ~~Non-Devotion Paladin Lv 15/20 capstones~~ — closed (10 of 11 capstones shipped; Conquest Lv 3/7 + Redemption Lv 3 + Glory Lv 3 + Vengeance Phase 2 remain as small follow-ups under the paladin-oaths plan).

### Out-of-scope (unchanged)

Same as the 2026-06-10 audit: Tasha's, Xanathar's-beyond-SRD, Strixhaven, post-SRD feats (Tough, Resilient, etc.), backgrounds beyond Acolyte stay future-3.x scope. Out-of-scope-by-design RAW-narrative features (Beast Speech, Mask of Many Faces, Druid Land's Stride, Monk Slow Fall, Cleric/Paladin Divine Health) also unchanged.

---

## SRD 5e Audit (2026-06-10)

**Audit scope.** Walk every piece of SRD 5.1 (CC BY 4.0 — the "free" 5e release from Wizards of the Coast) content shipped under `app/data/local/dnd5e/` and confirm whether the mechanical wiring is in place to automate it. The audit excludes setting-specific / post-SRD content (Tasha's, Xanathar's beyond the bits already in SRD, Strixhaven, etc.) and homebrew. Findings below feed directly into the [Design Plans Backlog](#design-plans-backlog) re-priorities.

### Headline state

| Layer | Shipped count | Automated count | Coverage |
|---|---|---|---|
| Spells (319 SRD entries) | 319 ✅ data | ~210 cast endpoints route through the engine; ~110 still cast-and-broadcast-only or partial scaling | ~66% mechanical |
| Monsters (322 SRD) | 322 ✅ data + structured actions | `/npc_attack` + `/npc_cast_spell` route most actions through the damage pipeline; legendary / lair actions still ⚪ | ~75% mechanical |
| Conditions (15/15 SRD) | 15 ✅ data | 10 fully wired; **Exhaustion levels ⚪** (single-flag today, RAW has 6 stacking levels with cumulative penalties); Deafened/Petrified-detail/Restrained-grapple-source partial | ~70% mechanical |
| Items (292 SRD equipment + magic items) | 292 ✅ data | **0% magic-item automation** — every magic item's `actions` array is empty; no attunement gate, no charges, no spell effects, no on-hit riders | <25% mechanical (weapons + armor only) |
| Class features (133 per-row entries) | 107 ✅ / 5 🟢 / 1 🟡 / 20 ⚪ | ~80% ✅ across the 12 classes (per `docs/plans/class-content-status.md`) | ~80% mechanical |
| SRD feats (1 in SRD 5.1 — Grappler) | 1 ✅ data (`grappler.json`) | Grappler 🟡 announce-only; 6 PHB-not-SRD feats (Lucky, Defensive Duelist, War Caster, Mage Slayer, Sentinel, Polearm Master) wired via the reactions framework but data layer doesn't list them | N/A — SRD 5.1 only ships 1 feat |
| SRD backgrounds (1 in SRD 5.1 — Acolyte) | 1 ✅ data (`acolyte.json`) | Pure descriptive, RAW-correct | 100% (RAW backgrounds carry no mechanical effect server-side) |
| SRD races (9/9) | 9 ✅ data + traits curated | 8 wired through `_RACE_SAVE_ADVANTAGES` + damage-resistance + sleep-immunity + Relentless Endurance + Halfling Lucky (all 5 surfaces) | ~90% mechanical |

### Headline gaps (RAW-implementable, no system blocker)

🔴 **P1 — Magic-item automation (NEW — no plan doc today).** 292 SRD magic items shipped as data but `actions: []` on every entry. RAW shape is identical to spell endpoints: attunement gate, charges-per-day, spell-effect dispatch, on-hit rider buffs (Flame Tongue, Frost Brand), passive AC/save bonuses (Cloak of Protection — partially shipped as Cloak of Displacement reaction in v2.78.0 but item-walk doesn't read `sheet.inventory[*]._reactions[]` yet). **Suggested first slice:** Pearl of Power (recover one spell slot — already a primitive); Wand of Magic Missiles (auto-cast with charges); Cloak of Protection (+1 AC + saves passive); Bracers of Defense (+2 AC unarmored). Write `docs/plans/magic-items-automation.md` before starting; this is the largest single un-planned SRD surface.

🔴 **P1 — Exhaustion-level tracking (NEW — no plan doc today).** RAW: 6 cumulative levels with disadvantage on ability checks (Lv 1), speed halved (Lv 2), disadvantage on attacks + saves (Lv 3), HP max halved (Lv 4), speed → 0 (Lv 5), death (Lv 6). Today's engine treats Exhaustion as a single-flag buff. Unlocks: Barbarian Frenzy (Lv 3 Berserker — gain exhaustion on rage end), Wizard Spell Mastery overuse, environmental-hazard hooks. **Suggested approach:** `sheet.conditions.exhaustion.level` int field + a `_exhaustion_disadvantage` helper that composes with the v2.152.0–v2.155.0 condition-disadvantage stack at the same construction sites.

🔴 **P1 — Spell-validation suite Phase 1+** ([`docs/plans/spell-validation-suite.md`](docs/plans/spell-validation-suite.md)). 319 spells shipped, only ~25 have explicit harness tests. Phase 2A v1 (Fire Bolt) is the only shipped slice. CI-gated catalog iteration is the cheapest way to catch SRD-content drift; closes the audit's "spell mechanics ~66% mechanical" gap one batch at a time.

🟡 **P2 — Pact Boon (Warlock Lv 3)** ([`docs/plans/warlock-pact-boon.md`](docs/plans/warlock-pact-boon.md)). Plan exists ⚪ proposed. RAW SRD content; Tome is the cheapest first ship (+3 cantrips picker); Chain unlocks the familiar-summon primitive (extends v2.99.443 summon-companion); Blade adds a CHA-based summoned weapon. Unblocks ~8 Pact-gated invocations downstream.

🟡 **P2 — Battle Master 15 maneuvers** ([`docs/plans/battle-master.md`](docs/plans/battle-master.md)). All 16 maneuvers are SRD RAW; Phase 1 shipped Trip Attack. Remaining 15 compose on the v2.99.405–.414 feature-save resolver + the v2.99.395–.401 on-hit rider primitive — each maneuver is mostly a thin endpoint over those primitives. ~15 commits at one-per-day cadence.

🟡 **P2 — Wizard capstone Spell Mastery / Signature Spells (Lv 18/20).** Both are SRD; both need a spell-picker (pattern: v2.16.1 Arcane Recovery) + a per-rest counter. Two small endpoints unblock Thalindra's Lv 18+ capstones.

🟡 **P2 — Aura of Courage (Paladin Lv 10/18).** Same gate shape as Aura of Devotion (v2.55.0). One commit when a Paladin Lv 10+ fixture lands. Filed in Class Features (next cycle) below.

🟡 **P2 — Reactions v3 pending-damage state machine** ([`docs/plans/reactions-automation.md`](docs/plans/reactions-automation.md) v3 backlog). Closes auto-resolution for Shield AC negation, HR damage-to-attacker, Lucky / SB d20 reroll, Counterspell undo. The framework is shipped (Phases 1–6); v3 replaces the advisory chat-card with state-machine auto-resolution.

🟡 **P2 — Sorcerer Quickened Spell.** The one of 8 SRD metamagics still announce-only. Bonus-action cast routing needs a `/cast_spell` action-economy override path; small lift.

🟢 **P3 — Eldritch Knight Phase 2 read sites** ([`docs/plans/eldritch-knight.md`](docs/plans/eldritch-knight.md)). The Lv 15/18 Phase 1 flag buffs shipped v2.158.11/.12; the Lv 7/10 War Magic + Eldritch Strike are the next slice.

🟢 **P3 — Non-Devotion Paladin Lv 15/20 capstones** ([`docs/plans/paladin-oaths.md`](docs/plans/paladin-oaths.md)). Ancients Undying Sentinel / Elder Champion; Vengeance Soul of Vengeance / Avenging Angel; Conquest Invincible Conqueror; Redemption Protective Spirit / Emissary of Redemption; full Glory oath. Phase 1 plumbing for each landed in v2.99.245–v2.158.x.

🟢 **P3 — Class-feature ⚪ tail** (~20 rows per the [class-content-status](docs/plans/class-content-status.md) re-audit): Barbarian Lv 9–20, Monk Deflect Missiles + Diamond Soul + Empty Body + Perfect Self, Ranger Lv 10–20 (Hide in Plain Sight, Vanish, Feral Senses, Foe Slayer — Vanish Phase 1 shipped v2.158.21), Rogue Reliable Talent / Slippery Mind / Elusive / Stroke of Luck. Most are RAW-implementable but blocked on a Lv 10+ demo fixture for the relevant class. Group by demo-PC bump rather than by class.

### Out-of-scope-by-design (RAW intentionally narrative)

These show up as ⚪ / 🟡 in the per-class tables but RAW is "narrative description, no mechanical effect server-side": Beast Speech, Devil's Sight (Phase 1 install ✅ v2.158.14; engine read site filed), Mask of Many Faces, Pact of the Tome cantrip selection (data-only — counted under Pact Boon plan), Druid Land's Stride (blocked on difficult terrain F11), Monk Slow Fall (blocked on fall-damage F4), Cleric Divine Health / Paladin Divine Health (blocked on disease F5). These stay descriptive until the framework lands — not part of the SRD audit's "should automate" list.

### Out-of-scope (not in SRD 5.1)

Setting-specific subclasses (Tasha's: Beast Barbarian Phase 1 shipped v2.158.20 but the rest of the subclass is Tasha's-only and stays gated on user choice); post-SRD feats (Tough, Resilient, Skilled, Magic Initiate — the data layer correctly carries only Grappler); backgrounds beyond Acolyte. None of these belong in this audit; they're the future-3.x scope per the long-standing user direction.

---

## Manually Added

- 🟢 **P3** — Feature: More pills in the roll log for spells
    - Move spell type, range, action type and details to pills
        - details should be an expanding pill
        - pills should be different color than damage pills
- 🟢 **P3** — Allow the map and roll log (when on the left) to move over the tt-topbar but not over the title of the campaign or the ruler, roll log, battle, characters, tools buttons
- 🟢 **P3** — Change the logout button under tools > quick links to reverse how its animated (better for backgrounds)
- 🟢 **P3** — Update all of roll log to look like spells

---

## Character Sheet

### Ability Score Generation
Two methods for players to generate ability scores during character creation:
- **Point buy** — players spend a fixed pool of points (standard D&D 5e: 27 points, scores 8–15 before racial bonuses) with an interactive cost table shown in the sheet UI. Should enforce the budget in real time and show remaining points.
- **Dice rolling** — roll 4d6 drop lowest for each attribute, with an in-sheet button per score and a "Re-roll all" option. Should show the individual dice results before committing. Optionally allow the GM to lock or unlock rerolls per campaign.

### Class Resource Tracking in Mini-Sheet
Review every D&D 5e class and subclass resource and surface the most commonly used ones in the mini-sheet panel. Current mini-sheet only shows HP and basic rolls. Resources to audit and add:
- **Rage** (Barbarian) — uses per long rest; toggle button to mark active (grants resistance, damage bonus) with a use counter
- **Ki points** (Monk), **Sorcery points** (Sorcerer), **Superiority dice** (Battle Master Fighter), **Bardic Inspiration** — numeric trackers with per-rest reset
- **Channel Divinity**, **Second Wind**, **Action Surge**, **Lay on Hands** pool — binary or pool trackers
- **Wild Shape** uses (Druid), **Arcane Recovery** (Wizard) — per-rest binary toggles

Goal: a compact resource row below HP in the mini-sheet that auto-populates based on the character's class(es). Resources should persist server-side (stored in the character JSON) and broadcast updates via WebSocket so the GM can see resource consumption in real time.

### Dynamic Character Art Updates
When a player updates their character portrait on their sheet, the change should propagate in real time to the tabletop — updating the token image, the player list, and any other places the portrait is displayed — without requiring a page reload. Should use the existing WebSocket broadcast infrastructure so all connected clients (GM and other players) see the new art immediately.

---

## GM Tools

### GM Access to All Character Sheets
GMs should be able to open and read any player's character sheet in the campaign directly from the tabletop or campaign settings, without needing to be assigned as the character's owner. Read-only access is the minimum; optionally allow the GM to make edits (e.g. to update HP after a session or correct a mistake). Needs a clear UI entry point — likely a "View Sheet" button next to each character in the GM's player list.

### Reporting Page
Admin/GM dashboard showing campaign activity: session count, token move history, roll statistics, active players over time. Useful for GMs who want a post-session summary.

### Initiative Tracker Roll Prompt
When a combatant is added to the initiative order without a roll (e.g. added mid-combat from the token sheet or manually), show the GM a "Prompt Roll" button next to that entry. Clicking it sends a WebSocket message to the relevant player's client asking them to roll initiative. The button disappears automatically once the player's initiative is recorded (either via self-roll or GM entry).

### Homebrew Clone
Add a "Clone" button on every homebrew entry in the campaign settings homebrew menu — feats, backgrounds, races, subclasses, monsters, and classes (the six file-based homebrew types as of v2.0.0). Clicking it duplicates the source record as a new homebrew JSON file with a name pre-populated to "Copy of \<original\>" and a fresh auto-generated slug, then opens the new entry in the editor for the GM to tweak. Makes it trivial to spin off variants (e.g. clone "Bandit" → tweak HP / abilities → save as "Veteran Bandit") without retyping every field. Behaviour: server-side endpoint reads the source JSON, mutates the `slug`/`name` fields, writes a new file in the same campaign scope, redirects to the edit form. Existing-slug guard already applies (the existing `_existing_*` check in `homebrew/import` rejects duplicates). No clone for shipped SRD content — that lives in `app/data/local/dnd5e/` and is read-only; cloning shipped → homebrew would be a separate feature.

### Homebrew Monster Attack Fields → Rollable Attack Buttons
Expand the homebrew-monster Actions editor (`app/templates/campaign_settings.html` ~line 2188-2192, currently a generic `data-features-editor` exposing only `name` + `desc`) so each action carries the same structured fields the shipped SRD stat blocks already use — `attack_roll: bool`, `attack_bonus: int` (or derived "+to_hit"), `damage: "1d8"`, `damage_type`, optional `save_ability` / save DC for save-based attacks. With those fields populated, the stat-block view can render each attack as a clickable button that pipes through the existing `/roll` endpoint (mirroring the character sheet's weapon attack flow at `app/static/sheet.js`) so GMs running a homebrew "Veteran Bandit" don't have to manually retype `1d20+5` and `1d8+3 slashing` into chat for every swing. Scope: (1) extend the features-editor JS to render the extra attack fields when the parent fieldset is the Actions list (Special Abilities / Reactions / Legendary can stay name+desc-only — those are mostly narrative), (2) update the homebrew monster POST handler to persist the structured fields into the JSON file, (3) extend the monster stat-block read-view to render attack buttons when `attack_roll: true` is set, with hover/click semantics matching the character-sheet attack buttons. Bonus follow-up: a "Parse from description" button that regex-extracts `+N to hit` / `NdM damage type` from a pasted SRD-style description so importing a homebrew monster doesn't require filling every field manually.

### Unified Monster Sheet in Initiative Tracker (reuse character sheet UI)
Today the initiative tracker opens a read-only stat-block popover for monster entries, while character entries open the full interactive D&D 5e sheet (`app/templates/sheet_dnd5e.html`) with clickable ability checks, skill checks, saves, and weapon-attack buttons that pipe through `/roll`. Goal: replace the monster popover with the same sheet shell so the GM can click an attack on "Bandit Captain" the same way a player clicks an attack on their PC — one-click roll, auto-applied advantage/disadvantage from `roll_state`, breakdown lands in the shared roll log. Pairs naturally with the "Homebrew Monster Attack Fields" TODO above (the structured `attack_roll` / `damage` fields are the data the buttons bind to). Scope sketch: (1) backend — extend the sheet route or add a "monster sheet" sibling that reads a stat block (SRD JSON or homebrew JSON) and projects it into the same context shape `sheet_dnd5e.html` expects (abilities, modifiers, skills, attacks, spells). Most fields map cleanly; HP/AC/speed/CR have direct equivalents, skills need to be derived from the monster's `skills` list + ability modifiers, attacks come from the Actions list. (2) frontend — reuse `sheet.js`'s `wireDnd5eRollButtons` against the monster sheet so ability/skill/save/attack clicks all hit `/roll` and respect roll-state. (3) initiative tracker — open the new sheet (full-screen or large modal) instead of the popover, keyed by token's stat-block reference (slug or homebrew slug). (4) ownership/scope — monsters are GM-only; the sheet should hide the "edit" affordances available to a PC owner (or route them to the homebrew editor for homebrew monsters). Open question: do legendary actions and lair actions get first-class buttons too, or stay as narrative text? Probably first-class buttons since they're the rolling-heavy content. Builds on the structured-attack-fields TODO above; can ship the read-mostly version first and incrementally add roll wiring per field category.

---

## Combat

### Advantage & Disadvantage Tracking
Per-character roll-state toggle (adv / normal / dis) that the server applies to d20 rolls automatically, with the existing manual `adv` / `dis` dice buttons preserved as one-shot overrides. Three phases: manual toggle, condition automation, context-aware rolls. See [`docs/plans/advantage-disadvantage.md`](docs/plans/advantage-disadvantage.md) for the full design.

### Death Saving Throws
Triggered automatically when a character hits 0 HP. Mini-sheet + full sheet show success/failure pips; "Roll Death Save" button rolls a 1d20 through the regular roll pipeline (so it honors the adv/dis roll-state toggle). Healing wakes the character up; damage at 0 HP ticks failures (with crit and massive-damage rules per 5e RAW). GM gets override + stabilize controls. See [`docs/plans/death-saves.md`](docs/plans/death-saves.md) for the full design.

### Combat 2.0 — Action Economy Tracking
Full per-turn action economy tracker surfaced in the initiative tracker and each player's mini-sheet. Tracks the four action types defined by D&D 5e:

- **Action** — one per turn; used for attacks, casting most spells, Dash/Disengage/Dodge/Help/Hide/Ready
- **Bonus action** — one per turn; class features, certain spells, off-hand attacks
- **Movement** — up to the character's speed (in feet); partially consumed by moving between tokens (requires Maps 2.0 grid distance awareness)
- **Free action / Reaction** — one reaction per round; tracked separately, auto-resets at the start of the character's next turn

UI: a compact row of four icons in the initiative tracker entry and mini-sheet. Clicking an icon marks it spent (greyed out). At the start of a character's turn the GM can click "New Turn" to reset all four. The GM can also manually mark/unmark any action for any combatant. State is broadcast over WebSocket so all clients stay in sync.

### Summon Spells — Creature Picker + Auto-Control + Init Placement

Unify the **cast-flow UX** for every spell that summons a creature onto the battle field. Today each summon endpoint (`/cast_conjure_animals`, `/cast_conjure_woodland_beings`, `/cast_conjure_minor_elementals`, `/cast_animate_dead`, `/cast_conjure_elemental`, `/cast_conjure_fey`, `/cast_conjure_celestial`, `/find_familiar`, plus any future summon ship) takes the chosen creature as an opaque server-side default (Conjure Animals always spawns wolves; Find Familiar always spawns a generic familiar) or as a free-form body field with no UI affordance. The player has no in-game picker for the RAW choices and the GM has to manually assign control + reorder initiative.

**Three changes wrapped into one feature:**

1. **Per-spell creature picker.** When a player casts a summon spell with RAW choice, surface a picker UI (modal or sheet-side popover) showing the valid summoning options for the chosen slot level. Examples:
    - **Conjure Animals** — picker shows wolf / boar / brown bear / giant eagle / etc. filtered by CR matching the `count` summoning option (8×CR¼, 4×CR½, 2×CR1, 1×CR2).
    - **Conjure Woodland Beings** — same shape: pixie / sprite / satyr / dryad scaled by CR.
    - **Conjure Minor Elementals** — magmin / mephit / azer / etc.
    - **Animate Dead** — zombie / skeleton (RAW two choices).
    - **Conjure Elemental** — fire / water / earth / air elemental (caster picks element).
    - **Conjure Fey / Celestial** — RAW caster picks; surface known creature options.
    - **Find Familiar** — bat / cat / crab / frog / hawk / lizard / octopus / owl / poisonous snake / fish (quipper) / rat / raven / sea horse / spider / weasel (RAW PHB p.240 list).
    - **Bag of Tricks** (magic item) — colored bag rolls a random animal per RAW DMG p.154; picker collapses to "Pull a creature" with the random-table dispatch happening server-side.

   Backend: extend each summon endpoint with a `creature_key` body field (defaulting to the current opaque choice if missing); the player UI surfaces a picker before the cast goes through. The catalog of valid options per spell lives next to the existing `_SPELL_SUMMON_MAP` substrate or in a sibling `_SPELL_SUMMON_OPTIONS_MAP`. Each option carries the matching `companion_key` for `_summon_companion` (or a new template if needed).

2. **Auto-assign control to the casting player.** Today summons spawn with `is_summon: True, summoned_by: <caster_id>` but the owning player isn't automatically granted move/attack control over the new token. Wire the existing per-token ownership/control hook so the casting player's user_id is stamped on the summon's combatant entry (similar to how PC tokens carry `owner_user_id`). The GM retains override (any combatant is GM-controllable), but the casting player no longer has to ask the GM to move the wolf pack.

3. **Auto-insert summons behind caster in initiative.** Per RAW PHB p.193 (and several DMG calls), summoned creatures "act on the caster's turn" — i.e. the caster decides when they act, and they typically act immediately after the caster's turn. Today summon endpoints take an `initiative: int` body field that has to be set manually. Change the default behavior: when the body omits `initiative`, compute it as `caster_initiative - 0.001 × N` where N is the summon index in the cast, placing every summon **immediately after** the caster in the turn order without disturbing other combatants' positions. The GM can still manually reorder via the existing initiative tracker.

   Edge case: if the caster isn't in the initiative tracker (out-of-combat summon, e.g. Find Familiar during a rest), skip the auto-placement and add the summon at the end of any active battle, or omit from initiative entirely.

**Why this matters.** The v2.404.x–v2.420.0 Phase 3 work shipped 7 summon endpoints + the cap-extension substrate, but each cast still requires GM-side hand-holding (assigning control, reordering initiative, picking the creature for the player). This feature closes the cast-flow UX gap so summoning is one-click-per-cast for the player and zero-GM-effort to set up.

**Includes familiars.** Find Familiar (Wizard L1 ritual) is the lightest summon mechanically (it's not even a real combatant in v1) but it's the most common one at low levels — and the RAW creature list is the longest. Bringing familiars into the same picker+control+init flow means a player Find Familiar cast spawns the actual chosen creature (owl vs cat vs raven) under player control, in the turn order behind the wizard, with one cast. Same shape for Pact of the Chain (Warlock) and any other familiar-style summon.

Scope sketch: (1) a single `_SPELL_SUMMON_OPTIONS_MAP` covering all 8+ summon endpoints with RAW creature lists; (2) sheet-side picker JS that lights up when a summon-spell button is clicked; (3) endpoint extensions to read `creature_key` + auto-stamp `owner_user_id` + auto-compute initiative; (4) harness coverage for all three behaviors (picker choice persists, owner stamp matches caster, initiative places summon immediately after caster). Likely a v2.5x arc — substantial enough to merit its own `docs/plans/summon-cast-flow.md`.

---

## Maps & Map Editor

### Bulk Map Upload
Allow GMs and admins to upload multiple map images at once (e.g. a zip or multi-file picker) rather than one at a time. Should probably show a progress indicator and let the user assign names/grid settings to each before committing.

### Map Generator
Procedural in-browser map generation — produce a playable battle map without any external upload. Minimum viable output: a dungeon room layout (walls, corridors, door placements) rendered to a canvas the GM can place tokens on immediately. Stretch goals: biome presets (dungeon, wilderness, tavern interior), adjustable density/size parameters, and one-click export as a PNG that feeds into the existing map upload flow.

### Bundled Art Assets (Maps, Player Tokens, Monster Tokens)
Source and bundle a starter set of free-to-use art so new campaigns have something to work with out of the box. Three separate asset packs:
- **Battle maps** — a handful of generic scenes (dungeon room, tavern, forest clearing, city street) usable as starting maps
- **Player tokens** — a set of generic adventurer portraits (warrior, rogue, mage, cleric, ranger, etc.)
- **Monster tokens** — common encounter creatures (goblin, skeleton, orc, wolf, spider, etc.)

Licensing requirements: CC0 or CC BY with attribution in a bundled `CREDITS.md`. Consider AI-generated art (e.g. Stable Diffusion with a permissive licence) as a practical source for a consistent style across all three packs. Assets should ship inside the Docker image under `app/static/bundled/` so they are available without any upload step.

### Maps 2.0 — Advanced Map Features
Extends the existing battle map canvas with GM-controlled environmental features. Builds on the Map Editor Framework groundwork below; these items represent the prioritised feature set for a Maps 2.0 milestone.

- **Combat movement locking** — when a combat encounter is active, token movement is capped at the character's speed (in feet). Each move broadcasts the distance consumed; the token becomes unmovable once the movement budget is exhausted for that turn. Requires grid scale (ft per square/hex) to be set on the map. Integrates with Combat 2.0 action economy tracking.
- **Fog of war** — GM-controlled per-cell reveal overlay. Players see black/obscured cells until the GM reveals them. Two modes: manual brush reveal (GM paints explored areas) and auto-reveal based on token line-of-sight. GM always sees the full map.
- **Walls & doors** — the GM places wall segments (line tools) directly on the battle map. Wall data is saved at the map level (not per-encounter) so the same map always loads with its walls intact. Doors are interactive wall segments: players and GMs can toggle them open/closed, which updates the fog-of-war LOS calculation in real time.
- **Dedicated wall editor** — a separate editing mode (toggle in the GM toolbar) for placing, moving, and deleting wall segments. Should be distinct from normal token-interaction mode to prevent accidental edits during play. Wall data stored as a JSON array of line segments on the `BattleMap` record.
- **Clickable map items** — hotspots placed by the GM that trigger a description popup or roll prompt when a token moves onto or a player clicks them.

### Map Editor Framework
Groundwork for in-browser map authoring tools. Planned capabilities:
- **Fog of war** — GM-controlled reveal of map regions; players see only explored areas
- **Walls** — line segments that block token line-of-sight
- **Doors** — interactive wall segments that players/GMs can open or close
- **Clickable items** — hotspots on the map that trigger a description popup or roll prompt
- **Multi-map encounters** — link multiple maps into a single encounter (e.g. interior/exterior transitions) without switching the active map for the whole campaign

### Lighting
GM can place different kinds of light sources on the map — torches, lanterns, campfires, magical lights — each with their own radius, colour, and behaviour. Flicker animation for fire-based sources (gentle brightness/radius oscillation), steady glow for magical lights, etc. Integrates with fog of war and player vision: tokens illuminate the area around them based on attached lights, and players only see what their token's light source(s) cover (plus any GM-revealed fog area). The GM has full visibility regardless. Stretch goals: ambient map-wide lighting (day/night/dim), per-token vision types (darkvision out to N ft as dim light, blindsight ignoring lighting entirely), and "extinguish" interaction on placed lights. Builds on the Maps 2.0 / Map Editor Framework groundwork above — both fog-of-war LOS and wall segments need to land first so lighting can compute shadows correctly.

---

## Media & Content

### Resources
A dedicated section for GMs and admins to upload documents (PDFs, images, handouts) that players can view directly in the browser — inline PDF rendering, no download required. Needs access control so GMs can choose whether a resource is visible to all players or GM-only.

### Playlist Builder with Existing Songs
Allow GMs to create playlists from tracks already uploaded to the campaign rather than re-uploading. UI: a picker listing existing campaign audio tracks, drag-to-reorder, save as a named playlist. Backend: new playlist model + endpoints; guard file deletion to prevent removing audio that is still referenced by a playlist.

---

## Player Features

### User Presence on the Tabletop
Show who is currently connected to the session in real time. All connected users (GM and players) should be able to see at a glance which other players are online, idle, or have disconnected. Planned scope:

- **Presence indicators** — a small online/offline dot (or avatar badge) next to each player's name in the player list and/or initiative tracker. Green = connected, grey = disconnected. Optional: amber = connected but idle (no interaction for N minutes).
- **WebSocket lifecycle hooks** — on connect, broadcast a `presence_join` message to all clients; on disconnect (or WebSocket close), broadcast `presence_leave`. Clients maintain a local presence map and update the UI reactively.
- **Cursor / active-token highlight** (stretch) — show a faint coloured ring or name label on the token currently being hovered or dragged by another user, similar to Google Docs cursor presence.
- **GM view** — the GM's player list should show presence state for every campaign member, including those who haven't joined the current session yet (shown as offline).

Backend: presence state is ephemeral (in-memory in `realtime.py`, not persisted to the database) — it resets when the server restarts, which is acceptable.

---

## UI / Mobile

### Slide-Out Menu for Mobile
On small screens, replace the current sidebar with a proper slide-out drawer triggered by a hamburger button. The map should fill the full viewport and the drawer overlays it rather than pushing it. Needs gesture support (swipe to open/close).

### Darker Sepia Themes
Add a few darker sepia/warm-brown colour themes as alternatives to the existing dark theme. Candidates: a deep parchment (dark tan background, inked-brown text), a candlelit tavern (very dark brown with amber accents), and a burnt manuscript (near-black with faded sepia highlights). Should slot into the existing theme system with new CSS variable sets — no structural changes needed.

---

## Rules Reference

### SRD Rules in Full Text
Surface the complete D&D 5e Systems Reference Document (SRD 5.1, CC BY 4.0) as searchable in-app reference text. Players and GMs should be able to look up rules without leaving the VTT. Planned scope:
- Full SRD text indexed and searchable by keyword (conditions, actions, spells, equipment, etc.)
- Contextual links from the character sheet and encounter panels (e.g. clicking a condition name opens its SRD entry)
- Offline-capable: content bundled in the Docker image rather than fetched at runtime
- GM can pin a rule snippet to the tabletop panel for the whole table to see during play

Content source: the official SRD 5.1 PDF / markdown release from Wizards of the Coast, licensed CC BY 4.0. Attribution required in-app.

### Page Number References in Official Content
Where SimpleVTT surfaces content from official published sourcebooks (e.g. PHB, MM, DMG) — in spell descriptions, class features, item entries — investigate whether page numbers can be shown alongside the source citation (e.g. "PHB p.218").

**Licensing review required before implementing:** displaying page numbers from non-SRD sourcebooks may constitute a reference to copyrighted content even if the page number itself is a fact. Consult the D&D 5e SRD licence terms and any Fan Content Policy. If page numbers are only shown for SRD-sourced content (which is CC BY 4.0), no additional licensing concern applies — SRD content should be safe. Non-SRD sourcebook page numbers should be gated on legal sign-off.

---

## Legal & Compliance

### Full Audit for Licensed Material
Systematic review of all content bundled in or served by SimpleVTT to ensure nothing included exceeds its licence terms. Scope:

- **SRD content (spells, monsters, items, classes, races)** — confirm all data served via the Open5e mirror or shipped FS files is SRD 5.1 / CC BY 4.0 material only; flag any non-SRD entries (e.g. setting-specific content, post-SRD sourcebook expansions)
- **Images and art** — audit every image in `app/static/` (including any bundled token/map art) against its licence; ensure CC0 or CC BY assets have attribution in `CREDITS.md`
- **Fonts** — verify Google Fonts licences (currently all SIL OFL 1.1 — should be clean)
- **Third-party JS/CSS libraries** — list all vendored or CDN-loaded libraries and confirm licences are compatible with self-hosting
- **Any AI-generated art** — confirm the generation tool's output licence (some tools claim copyright on outputs; others release CC0); document the tool and settings used for each asset

Output: a `CREDITS.md` file at the repo root listing every third-party asset, its licence, and its source URL, plus a checklist of items that need further review or replacement.

---

## Test Infrastructure

> **Bugs moved to [`BUGS.md`](BUGS.md).** The skull-overlay CI emoji-font skip (B1) and the Garrik-not-tokenized encounter-sim skips (B2) now live in the bug tracker with their repro + fix paths. This section is kept for non-bug test-infra *features* if any are filed later.

---

## Integrations

### Philips Hue Integration
Allow GMs to sync Philips Hue smart lights with tabletop events — e.g. dim lights on combat start, flash red on a critical hit, restore brightness when combat ends. Should connect to the local Hue Bridge (mDNS or manual IP) and allow the GM to map VTT events to Hue scenes or brightness/colour changes in campaign settings.

---

## Visual

### Frosted-glass treatment across the whole tabletop interface
v2.49.139 applied the iOS-style frosted-glass look (semi-transparent background + `backdrop-filter: blur(10px) saturate(140%)`) to roll-log cards only. Extend to every drawer card on the tabletop so the canvas behind reads through everywhere — init-tracker cards (`.init-row` / `.init-entry`), GM panel cards (`.gm-panel`), the sound panel, the AoE picker hint, the ruler hint, the targeting chip, etc. Each surface needs:
- A theme-coherent `color-mix(in srgb, var(--bg) 78%, transparent)` background (or the appropriate variant for accent / panel-tinted surfaces)
- `backdrop-filter: blur(10px) saturate(140%)` + `-webkit-backdrop-filter` for Safari/iPad
- Verification that text remains readable on a busy map across all 9 themes (dark, midnight, dim, light, forest, bubblegum, oled, fire, sepia)

Performance note from v2.49.139: each `backdrop-filter` element triggers a compositor layer. Audit the total composite layer count once applied — if it gets heavy on long sessions, gate the blur behind a "low-detail" theme toggle.

---

## Class Features (next cycle)

### Paladin Aura of Courage (Lv 10)
Same shape as Aura of Protection (v2.53.0) and Aura of Devotion (v2.55.0) — `_ally_has_aura_of_courage(db, campaign_id, saving_char_id)` walks init for any Paladin Lv 10+ in any oath. RAW: "you and friendly creatures within 10 feet of you can't be frightened while you are conscious." This is a **condition-install immunity** gate matching the Aura of Devotion pattern, just with "frightened" as the blocked condition key (instead of "charmed"). Wire the same way: gate at `/roll_request/{id}/respond`'s PC-failed-save condition-install block, skip install + broadcast `feature_used(source=aura-of-courage)` when `cond.key == "frightened"` and a Paladin Lv 10+ is in init.

**Caelan bump**: 7 → 10. **Three levels** of cascading changes — prof bonus +3 → +4 (changes at Lv 9), HP +24, Lay on Hands pool 35 → 50, spell slots gain L3 (4/3/2 instead of 4/3/0). The prof bump breaks existing attack-bonus assertions in `test_attack.py::test_attack_divine_smite_spends_slot` (Longsword +6 → +7 because STR +3 + prof +4 = +7) — needs an audit-and-fix pass; this latent test-coupling hazard is tracked as **B9 in [`BUGS.md`](BUGS.md)**. **Recommended scope**: bundle Aura of Courage with the Caelan bump so the slot-pool / damage-die scaling lands once. Defer Aura of Devotion's Lv 18 30-ft radius expansion — same helper, larger gate, different commit.

Filed by v2.55.0 when the user picked Indomitable as the next implementation target. Pick this up after Indomitable ships.

### Fighter Indomitable (Lv 9+) — IN PROGRESS as v2.56.0 "Iron Will"
Garrik bump 7 → 9 (prof +3 → +4, HP +14, Second Wind 1d10+9). New `/use_indomitable` endpoint installs a single-use `indomitable-armed` self-buff; the save-roll construction hook reads the buff, swaps `1d20 → 2d20kh1`, and removes the buff from the combatant so the consumption is per-save (RAW: one specific reroll). RAW-bent v1: advantage on the next save rather than reroll-on-failure, since the post-roll reroll flow needs an undo-and-reapply path for installed conditions which is its own substantial commit. The accepted divergence + the precise post-roll reroll follow-up is tracked as **B10 in [`BUGS.md`](BUGS.md)**.

---

## Full Class-Feature Automation — remaining backlog

🔥 **IN PROGRESS** — plan: [`docs/plans/full-feature-automation.md`](docs/plans/full-feature-automation.md); live audit: [`docs/automation-coverage.md`](docs/automation-coverage.md). **Phases 0–7 ✅ done** + the entire v2.128.2–v2.149.1 retrofit batch landed (see CHANGELOG). Only Phase 8 (higher-level subclass features Lv 6/10/14/17/20) and a few Phase-1.5 / Phase-2 follow-ups on individual features remain.

**Status by archetype (re-evaluated 2026-06-08):**

Shipped archetypes (Phase 7 reactions, auras E, on-hit B, buff/temp-HP D/F, movement G) live in [`TODONE.md`](TODONE.md#full-class-feature-automation--archetype-bullets-shipped).

- 🟢 **P3 — Phase 8: higher-level subclass features (Lv 6/10/14/17/20).** Mostly composition on the now-built primitives; batch by class. The long tail. **Now the primary remaining work for the parent plan.**
- 🟢 **P3 — Per-feature Phase-2 finishers (deferred from this session):**
    - **Blade Flourish Phase 2** — Defensive AC self-buff + Mobile push + Slashing secondary-target routing.
    - **Fancy Footwork Phase 2** — OA-flow gate reads the `fancy-footwork-blocked` buff and skips OAs against the named char_id.
    - **Relentless Avenger Phase 2** — `/token/move` consumes `free_movement_remaining_ft` budget + skips OA prompts while `oa_immune_during_move` is set.
    - **Supreme Healing Phase 1.5** — `/apply_healing` chat-card path (legacy `_heal_claims` flow) also substitutes max dice.
    - **Combat Inspiration Phase 3** — Integrate the AC half into the reactions framework so the prompt fires automatically on `attack_targeted` for any combatant carrying a BI die buff.
    - **AP Phase 3 / UM Phase 1b** — Auto-install via `/attack` post-hit hook (currently both require player-driven trigger via the `target_surprised` / endpoint call).
- 🟢 **P3 — Classifier rerun for `docs/automation-coverage.md`.** Auto-generated row counts in the "Full classification" table still pin v2.99.460; rerun the classifier after the v2.128.2–v2.149.1 batch so the per-endpoint table reflects reality. Curated bullets + the "Recent retrofits" table are aligned per v2.142.1 + v2.149.1.

The remaining ~30 announce-only rows are **archetype J** (narration-only-by-design: passive senses, language grants, passive damage-boosters that already ride other paths) — leave as-is; see the audit doc's "Notable announce-only backlog" section for the full split.

---

## Design Plans Backlog

Every design doc under [`docs/plans/`](docs/plans/) + the two repo-root planning docs (`docs/encounters-plan.md` + `docs/multi-system-refactor.md`). Priorities reflect the post-v2.159.30 / 2026-06-11 SRD-audit refresh — **🔥 IN PROGRESS** = a plan with ongoing commits this session; **🔴 P1** = next-up substantial work that closes a real SRD-implementable gap; **🟡 P2** = substantial deferred phases or proposed work; **🟢 P3** = lower-priority or living-doc style.

> **v2.315.0 SRD-audit refresh (current).** Priorities re-shaped against the [SRD 5e Audit (v2.315.0 refresh)](#srd-5e-audit-v23150-refresh) at the top of this file — that section is now the authoritative re-prioritization. Since the 2026-06-11 list: legendary actions + lair actions + legendary resistance all ✅ shipped (v2.159.32–v2.167.0); the spell-validation suite is mostly ✅. The magic-item content tail this note once flagged as "the single biggest lever (116 of 239 GM-narrated)" **closed at 239/239 = 100% (v2.404.0)** — see the SRD audit at the top of this file. The remaining levers were **spell upcast scaling** (~110 cast-and-broadcast-only spells) and the **class-feature ⚪ tail** (24 rows) — the upcast lever has since been **reconciled as ✅ DONE** (the "~110" figure was stale audit text; see the P1 note below).
>
> **2026-06-11 SRD-audit refresh (superseded).** Priorities re-shaped against the [SRD 5e Audit (2026-06-11 refresh)](#srd-5e-audit-2026-06-11-refresh) above. The prior 2026-06-10 P1 list closed end-to-end: magic-items-automation framework ✅, Exhaustion-level tracking ✅, Pact Boon ✅, Battle Master 16/16 maneuvers ✅, non-Devotion Paladin Lv 15/20 capstones ✅. (That pass's P1 — legendary/lair actions + spell-validation — has since shipped; see the v2.315.0 note above.)

### 🔥 IN PROGRESS

- [`campaign-pc-archive.md`](docs/plans/campaign-pc-archive.md) — ✅ **shipped end-to-end** (v2.602.1–v2.605.0): plan doc → campaign archive (v2.603.0, schema v78) → PC retirement (v2.604.0, schema v79) → demo reseed (v2.605.0: Sundered Vault archived, fresh `Demo L5: The Tide-Wracked Catacombs` added). Reversible soft-state alongside delete, dogfooded in the demo.
- [`full-feature-automation.md`](docs/plans/full-feature-automation.md) — see the section above; Phase 8 is the next slice. **(The only remaining IN-PROGRESS plan — pending-resolution + reactions-automation both closed end-to-end as of v2.664.0; see TODONE.md.)**

### ✅ Shipped end-to-end

Now lives in [`TODONE.md`](TODONE.md#design-plans-backlog--shipped-end-to-end) — 12 plans (auras, death-saves, demo-mode, feature-saves, movement-and-summons, movement-oa-flow, on-hit-riders, ruler-and-range, spell-upcasting, temp-hp-and-bonuses, test-harness, wild-magic). Plus the 2026-06-11 refresh: [`carrying-capacity.md`](docs/plans/carrying-capacity.md) ✅, [`exhaustion-levels.md`](docs/plans/exhaustion-levels.md) ✅, [`magic-items-automation.md`](docs/plans/magic-items-automation.md) ✅ (framework + Phase 9 content tail both closed at 239/239 = 100%, v2.404.0), [`battle-master.md`](docs/plans/battle-master.md) ✅ (16/16 maneuvers), [`warlock-pact-boon.md`](docs/plans/warlock-pact-boon.md) ✅.

### 🔴 P1 — Next substantial work (v2.315.0 SRD-audit driven)

- _(The reactions-v3 auto-resolution arc — pending-resolution-state-machine + reactions-automation — closed end-to-end at v2.664.0; both plans moved to [`TODONE.md`](TODONE.md). No P1 plan-driven work is currently open; the next substantial slices are the P2 entries below + full-feature-automation Phase 8.)_

> **~~Spell upcast scaling (~110 spells)~~ — ✅ DONE (reconciled v2.599.13).** This long-standing P1 was **stale audit text**, not open work. Verified directly against the corpus: of 295 leveled spells, **39 dice-scale automatically** (32 structured `damage_per_slot`/`healing_per_slot` + 7 prose-parser-derived via [`spell_upcast_parse.py`](../app/content/spell_upcast_parse.py)); the **34** with a damage/heal base that don't scale **genuinely don't dice-scale in RAW** (Finger of Death, Meteor Swarm, Harm, Sunburst — empty `higher_level`) or scale by count handled by separate fields (Magic Missile, Scorching Ray, Chain Lightning); the remaining **222 are utility spells with no damage/heal base**. All three approaches shipped (A picker / B dice resolver / C free-text, v2.108.0–v2.110.0), and the bespoke +targets/HP-pool math (Hold Person `upcast_target_count`, Sleep `upcast_pool_dice`) already rides shared helpers. End-to-end harness coverage in [`test_cast_spell.py`](../tests/harness/test_cast_spell.py) (Burning Hands 3d6→4d6, Heat Metal 2d8→3d8, Thunderwave via parser, Cure Wounds healing) + unit coverage in [`test_spell_upcast_parser.py`](../tests/harness/test_spell_upcast_parser.py). **There is no clean dice/heal backfill batch left** — see the [spell-upcasting plan](docs/plans/spell-upcasting.md) v2.344.2 note. The only optional remainder is migrating the few per-endpoint constants onto data fields (a refactor, not content).

### 🟡 P2 — Substantial deferred phases

- [`unified-mini-sheet.md`](docs/plans/unified-mini-sheet.md) — 3 mockups landed; **Phase 1–3 unstarted**. Pairs naturally with Class Resource Tracking + Combat 2.0.
- [`encounter-sim-test-suite.md`](docs/plans/encounter-sim-test-suite.md) — **substantial progress** (Level 1 smoke + Level 2 encounter sim shipped through v2.49.x); Level 3 edge-case framework seeded; Phase 4 (Level 3 completion, ~40 tests) pending.
- [`docs/encounters-plan.md`](docs/encounters-plan.md) — **proposed, not started**. Save/load encounter state.
- [`docs/multi-system-refactor.md`](docs/multi-system-refactor.md) — **proposed, not started**. Big architectural lift; out of SRD-audit scope but tracked here for completeness.
- [`advantage-disadvantage.md`](docs/plans/advantage-disadvantage.md) — Phases 1, 2a–2f all ✅ (v2.2.0–v2.157.0); **only Phase 3 (positional / 5-ft prone-melee advantage) remains, blocked on Maps 2.0**. Down-ranked within P2 because the unblocker is itself a multi-session lift.

### 🟢 P3 — Lower-priority / living docs

- [`player-simulacrum.md`](docs/plans/player-simulacrum.md) — **design only, all phases unstarted**. Speculative.
- [`wiki-expansion.md`](docs/plans/wiki-expansion.md) — living roadmap of how-to guides + reference cards still to write. Doc-style work, lots of small slices.
- [`class-content-status.md`](docs/plans/class-content-status.md) — living inventory; updates as features ship.
