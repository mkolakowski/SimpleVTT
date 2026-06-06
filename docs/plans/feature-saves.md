# Feature saving throws — Phase 3 sub-plan

**Status:** ✅ shipped (P3.1 → P3.5 complete, v2.99.405–.414)
**Parent:** [full-feature-automation.md](full-feature-automation.md) Phase 3.
**Goal:** Extract the save-construction + condition-install + save-for-half
path out of `/cast_spell` into a reusable **`_resolve_feature_save`**
helper, so the ~10 announce-only "target makes a {ability} save vs DC
{N}; on a fail install {condition} / take {damage}" subclass features
**auto-resolve the save and apply the result through the engine** — and
verify each with a harness test that asserts the installed condition (or
HP delta), not just the broadcast.

---

## 1. What already works (the spell save path)

All in `app/routes/tabletop_routes.py`. `/cast_spell` (≈ line 14736)
already builds a save, rolls/prompts it, and on a fail installs a
condition or applies save-for-half damage. The machinery Phase 3 reuses:

### A. Save DC
`_compute_spell_save_dc_from_sheet` (line 23871) → `8 + proficiency +
spellcasting-ability mod`. Class features use the same shape but key off
a chosen ability (e.g. Battle Master maneuvers: `8 + prof + max(STR,
DEX) mod`; Paladin auras: `8 + prof + CHA mod`). The helper needs an
**ability-override** parameter (or a thin feature-DC wrapper).

### B. Rolling the save — two target paths
- **PC target → roll-request.** `/cast_spell` builds a `RollRequest`,
  stamps `_save_request_context[req.id]` (line 5801) with `spell_slug`,
  `dc`, `save_ability`, `caster_char_id`, `cast_id`, broadcasts
  `roll_request`, and resolves on `/roll_request/{id}/respond` (line
  ≈ 14116). That respond-handler is where the condition installs on a
  failed PC save.
- **NPC target → server-side roll.** `/cast_spell` rolls `1d20 + mod`
  inline, applies Bless/Bane + metamagic, broadcasts `roll`, and
  installs the condition / applies half damage immediately.

### C. The advantage/disadvantage stack
A dozen intercepts already adjust the save d20 (Danger Sense, Indomitable,
Aura of Protection, Countercharm, race traits, Rage STR-save, Heightened
/ Careful metamagic, Bless/Bane, Halfling Lucky). These are **caller-side
today** (inline in `/cast_spell`). Whatever `_resolve_feature_save` does
must run through the same stack so a feature save isn't "dumber" than a
spell save.

### D. Condition install + immunity + repeated-save metadata
- `_SPELL_CONDITION_MAP` (line 805) maps a slug → condition buff template
  (`key/name/icon/duration_rounds/concentration/effects` + optional
  `save_on_damage`).
- `_install_buff` (line 524) installs it and consults
  `_target_condition_immune` (line 29663) / `_target_condition_immune_npc`
  before applying. Immunity gates (Aura of Devotion, Mindless Rage,
  PFE&G) live in the respond-handler.
- `_make_paralyzed_buff` (line 23895) & siblings stamp
  `repeated_save_ability` + `repeated_save_dc` so the end-of-turn /
  damage-triggered re-save (`_resolve_repeated_save_for_buff`, line
  22755; `_fire_damage_triggered_saves`) can drop the condition on a
  later success.

### E. Save-for-half damage
`_apply_damage_to_combatant` (line 5955) applies a rolled amount with
resistance/vulnerability/immunity; "half on success" is expressed by
halving the rolled total before the call on a passed save.

**Takeaway:** the spell path is the reference implementation, but the
logic is **inlined in `/cast_spell` + `/respond`**, not callable. Phase 3
is mostly an *extraction* — lift the construct-save / roll-or-prompt /
on-fail-install-or-damage flow into one helper that a feature endpoint
can call with `{targets, save_ability, dc, on_fail}`.

---

## 2. Target features (the retrofit backlog)

All compute a DC correctly today but are **announce-only** (the save +
condition are GM-tracked). Verified endpoints + line numbers:

| Feature | Endpoint (line) | Class / Lv | Save | On fail |
|---|---|---|---|---|
| Menacing Attack | `use_menacing_attack` (42474) | BM Fighter 3+ | WIS | Frightened to end of your next turn |
| Trip Attack | `use_trip_attack` (42787) | BM Fighter 3+ | STR | Prone |
| Fey Presence | `use_fey_presence` (50510) | Archfey Warlock 1+ | WIS | Charmed **or** Frightened (caster's choice) to end of next turn |
| Champion Challenge | `use_champion_challenge` (55194) | Crown Paladin 3+ | WIS | Can't willingly move >30 ft from you |
| Control Undead | `use_control_undead` (55351) | Oathbreaker Paladin 3+ | CHA | Obeys your commands (24h) |
| Hypnotic Gaze | `use_hypnotic_gaze` (56732) | Enchant. Wizard 2+ | WIS | Charmed + Incapacitated + speed 0 |
| Conquering Presence | `use_conquering_presence` (58529) | Conquest Paladin 3+ | WIS | Frightened 1 min (repeat save end of turn) |
| Draconic Presence | `use_draconic_presence` (33575) | Draconic Sorc 18+ | CHA | Charmed **or** Frightened (choice), 1 min, concentration |

Shape clusters:
- **Single-target, on-hit save** (Menacing / Trip): rider on a confirmed
  weapon hit; the save fires after the attack lands.
- **AoE / multi-target presence** (Fey / Conquering / Draconic /
  Champion Challenge): every creature in range/the supplied target list
  saves independently.
- **Targeted gaze** (Hypnotic Gaze / Control Undead): one creature, often
  with a use-budget already tracked from Phase 1.

Several need condition-map entries that don't exist yet (a generic
"frightened" / "charmed" / "prone" install not keyed to a specific
spell). Add feature-condition templates or generalize the map.

---

## 3. Design: `_resolve_feature_save`

A single coroutine the feature endpoints call per target:

```
_resolve_feature_save(
    db, campaign_id, *,
    caster_char_id, caster_sheet,
    target_combatant_id,
    save_ability,                 # "WIS" / "STR" / "CHA" / …
    dc,                           # precomputed (8 + prof + ability mod)
    on_fail,                      # {"condition": <template|slug>} and/or
                                  #   {"damage": "{expr}", "type": "{t}",
                                  #    "half_on_success": bool}
    source,                       # feature slug for cards + flags
    repeated_save=False,          # stamp repeated_save_* on the condition
) -> dict   # {target_id, save_total, passed, condition_installed,
            #  damage_applied, prompted}  (prompted=True for PC roll-req)
```

Internally it must:
1. Resolve the target → PC (roll-request, deferred resolution) vs NPC
   (server-side roll, immediate resolution). **Reuse the same
   `_save_request_context` plumbing** so PC saves resolve on
   `/respond` exactly like spell saves — including the advantage stack
   (§1C) and the on-fail immunity gates (§1D).
2. On an NPC fail (or a PC fail at respond time): install the condition
   via `_install_buff` (immunity-checked) and/or apply
   `_apply_damage_to_combatant` (halved first on a save-for-half pass).
3. Stamp `repeated_save_ability/_dc` when `repeated_save=True` so the
   existing end-of-turn / damage-triggered re-save drops it correctly.

**Key constraint — don't fork the advantage stack.** The cleanest
extraction lifts the `/cast_spell` save-build block (the d20-shape +
suffix assembly) into a helper both `/cast_spell` and
`_resolve_feature_save` call, rather than copy-pasting. If that lift is
too invasive for one commit, P3.1 can *wrap* the existing path for NPCs
first and tackle the PC roll-request extraction in P3.2.

---

## 4. Phased implementation

1. **P3.1 — extract the resolver (M). ✅ shipped v2.99.406.** Built
   `_resolve_feature_save` (NPC server-side path: roll → on-fail install)
   + `_feature_save_dc`, proven by retrofitting Menacing Attack (WIS save
   vs an NPC auto-installs Frightened on a fail). Save-for-half damage
   and the PC roll-request path are still pending (P3.2).
2. **P3.2 — PC roll-request path (M). ✅ shipped v2.99.407.** The
   resolver now prompts PC targets via a `RollRequest` + stamps
   `_save_request_context["condition_buff"]`; `/respond` installs that
   template (preferring it over the spell-slug map), inheriting the
   immunity gates + undo plumbing. Menacing Attack resolves vs PCs too.
   (The full advantage stack — Aura of Protection, race traits,
   metamagic — is not yet shared; PC feature saves use the plain
   `base_expression="1d20"` + stat-mod path, same as Stunning Strike
   today. Sharing that stack with `/cast_spell` is a follow-up.)
3. **P3.3 — on-hit save riders (S-M). ✅ shipped v2.99.408 (Menacing
   Attack).** New `weapon_hit_save` rider key + `_fire_weapon_hit_saves`
   (called in the `/attack` hit branch) fire a feature save on a
   confirmed hit. Menacing Attack armed without a target installs a rider
   that adds the superiority die AND triggers the WIS save on the next
   hit. Trip Attack (→ Prone) is the natural follow-up using the same key.
4. **P3.4 — presence AoE saves (M). ✅ shipped v2.99.409–.412.** All
   four resolve via the per-target `_resolve_feature_save` loop:
   Conquering Presence (Frightened, repeated save), Fey Presence (charm
   /fear choice, fixed), Draconic Presence (CHA, charm/fear, repeated),
   Champion Challenge (`challenged` marker, GM-enforced tether).
5. **P3.5 — targeted gaze (S). ✅ shipped v2.99.413–.414.** Hypnotic Gaze
   (WIS → Charmed) + Control Undead (CHA → `controlled-undead` marker)
   resolve their single-target saves through the resolver. **Completes
   Phase 3.**

---

## 5. Test contract (the bar that makes a feature save "automated")

Each retrofit's test must: put caster + target(s) in a battle
(`PUT /battle`), invoke the feature endpoint against an **NPC** target
(deterministic server-side roll), then assert via `GET /battle` /
`buff_update` that **the condition buff installed on a failed save**
(force a fail by setting the target's save mod low / DC high) **and did
NOT install on a pass** (and, for save-for-half, that HP dropped by the
right amount). PC-target prompting is asserted by the roll-request being
emitted (the respond-side install is covered by the existing spell-save
respond tests). Immunity: a condition-immune target takes no buff.

---

## 6. Risks & guards

- **Extraction risk:** the `/cast_spell` save path is large and
  battle-tested. Lift in small steps (NPC first, then PC), and lean on
  the existing spell-save harness tests to prove no regression in
  `/cast_spell` after the shared helper lands.
- **Advantage-stack drift:** a feature save that skips Aura of
  Protection / race traits / metamagic would silently diverge from spell
  saves. The shared d20-build helper (§3) is the guard — don't duplicate.
- **Double resolution:** a PC save must resolve exactly once (on
  `/respond`), never also server-side. Mirror the `/cast_spell` PC/NPC
  branch precisely.
- **Concentration:** presence features that are concentration (Draconic)
  must register concentration so existing breaks drop them.

---

## Related

- [full-feature-automation.md](full-feature-automation.md) — parent plan.
- [on-hit-riders.md](on-hit-riders.md) — Phase 2 sub-plan; P3.3 composes
  with its rider substrate.
- `_compute_spell_save_dc_from_sheet`, `_SPELL_CONDITION_MAP`,
  `_install_buff`, `_target_condition_immune`,
  `_resolve_repeated_save_for_buff`, `_apply_damage_to_combatant`,
  `/cast_spell`, `/roll_request/{id}/respond` — the reference
  implementations.
- `docs/test-harness-coverage.md` — grows with each retrofit.
