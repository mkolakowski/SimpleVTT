# PC vs NPC combat systems — divergence map

A catalog of every place in SimpleVTT where Player Characters (PCs) and Non-Player Characters (NPCs / monsters) are handled by **separate code paths, schemas, endpoints, or systems**. The point of this doc is to make the divergence visible: a future contributor adding a feature should be able to see at a glance "PCs have X, NPCs have Y (or nothing)" without spelunking the source.

> **Audit date:** v2.49.166 (2026-05-23). Re-walk the codebase periodically — divergences shift as the NPC surface area expands.

## Why two systems exist

SimpleVTT treats PCs and NPCs as conceptually different things:

- **PCs** are persistent, player-owned, with full sheets (HP, ability scores, skills, spell slots, resources, class features, death saves). They survive across sessions and rest cycles. The player drives most of their own mechanics; the GM has override authority.
- **NPCs** are GM-controlled stat blocks instantiated into a battle as combatants. They live in the hub's in-memory battle state, not in the ORM. They have static templates and ephemeral HP; when they drop, they drop. The GM drives 100% of their mechanics.

This split is **deliberate** for most of the divergences below. A few are accidental tech debt — those are flagged explicitly.

---

## Data model

### Character vs TokenTemplate vs combatant dict

| Concept | PC | NPC |
|---|---|---|
| ORM model | `Character` (`app/models.py:267`) | `TokenTemplate` (`app/models.py:491`) |
| Mechanics blob | `Character.sheet` (JSON) | `TokenTemplate.sheet` (JSON) |
| Battle entry | combatant dict in `hub.battle.combatants[]` keyed by `char_id` | combatant dict keyed by `token_template_id` |
| Per-instance state | sheet mutations commit to DB; HP changes broadcast as `character_hp_update` | hub-state mutations only; HP changes broadcast as `battle_update` with `force_gm_sync: True` (v2.49.40) |
| Token position | `Token.character_id == char.id` | `Token.id == combatant.source_token_id` (preferred) or `Token.token_template_id == ... && Token.label == name` (fallback for multi-instance templates) |

### Sheet structure

**PC sheet** (`Character.sheet`):
- `abilities` (STR/DEX/CON/INT/WIS/CHA scores)
- `proficiency_bonus`
- `attacks[]` (weapons + cantrips; indexed by `attack_index`)
- `spell_slots[class_slug][level] = {total, used}`
- `hit_dice[class_slug] = {total, used}`
- `saving_throws[]` (proficiency markers)
- `death_saves = {status, successes, failures}` (state machine: alive / dying / stable / dead)
- `resources[]` (Bardic Inspiration, Lay on Hands pool, etc.)
- `_buffs_active[]` (mirror of hub-state buffs for client-side conditional rendering)
- `roll_state.value` ("advantage" / "disadvantage" — manual override)
- `class_features[]` (Colossus Slayer, Sneak Attack, etc.)

**NPC sheet** (`TokenTemplate.sheet`):
- `armor_class` (static integer)
- `hit_points` (static max)
- `damage_resistances[]` (string list: `["fire", "cold"]`)
- `damage_immunities`, `damage_vulnerabilities`, `condition_immunities` (strings)
- `actions[]` (each: `{id, name, attack_roll, attack_bonus, damage, damage_type, save_dc, save_ability, range, desc, charges_max}`)
- `special_abilities[]`, `legendary_actions[]`, `reactions[]` (stored but not mechanically enforced)
- **No spell slots, no death saves, no class features, no roll state.**

### Combatant dict (hub state)

PC and NPC combatants live in the same `battle.combatants[]` array but carry different keys:

| Field | PC | NPC |
|---|---|---|
| `id` | `tok_<char_id>` or `<char_id>` | `tok_<random>_<demo_seed>` or per-template UUID |
| `char_id` | int (PK to `Character`) | omitted/null |
| `token_template_id` | omitted | int (PK to `TokenTemplate`) |
| `source_token_id` | optional (only set when GM placed a token) | required for position lookup |
| `hp_current`, `hp_max` | mirrored from sheet, authoritative on sheet | authoritative in hub; sheet has static max only |
| `economy` | `{action, bonus, reaction, movement}` (v2.6.1+) | usually absent / null |
| `buffs[]` | yes | yes (uniform storage) |
| `action_charges[action_id]` | n/a | yes (recharge tracker for limited-use actions) |

---

## HTTP endpoints

### Attack

| Action | PC | NPC |
|---|---|---|
| Endpoint | `POST /api/campaign/{cid}/attack` (`tabletop_routes.py:15793`) | `POST /api/campaign/{cid}/npc_attack` (`tabletop_routes.py:16482`, v2.49.164+) |
| Auth | character owner OR GM | GM only |
| Action-economy gate | yes (409 over_budget) | no — NPCs don't track economy |
| Range enforcement | `_check_cast_range` (`tabletop_routes.py:1261`) — three-tier (GM bypass / player override / strict) | `_check_npc_attack_range` (`tabletop_routes.py:1327`, v2.49.166+) — **no GM bypass**, explicit `override_range` flag only |
| Auto-uplifts | Rage / Hunter's Mark / Hex / Colossus Slayer | none |
| Per-attack uplift | `bonus_damage` body field for Sneak Attack / Divine Smite | none |
| Slot spending | `spend_spell_slot: {class_slug, level}` for Divine Smite | none |
| Roll state | applied via `_apply_roll_state` from `sheet.roll_state` | not read — only buff-driven adv/dis (e.g., target Dodging) |
| Broadcast | `weapon_attack` with `caster_char_id: int, caster_char_name: str` | `weapon_attack` with `caster_char_id: None, caster_char_name: <NPC name>, caster_combatant_id: str, is_npc_attack: True` |
| Multi-target | `target_combatant_ids[]` list (RAW per-target attack rolls) | single target only |

### Spell casting

| Action | PC | NPC |
|---|---|---|
| Endpoint | `POST /api/campaign/{cid}/cast_spell` (`tabletop_routes.py:7526`) | **none** |
| Workaround for NPC spells | n/a | GM uses `/npc_attack` to resolve spell-like abilities as weapon attacks; AoE spells flow through `/place_aoe` |
| Spell slot consumption | `_spend_spell_slot` decrements `sheet.spell_slots[class][level].used` | n/a |
| Metamagic | `/use_metamagic_empowered_spell` (`tabletop_routes.py:11348`) + others | n/a |

### Healing

| Action | PC | NPC |
|---|---|---|
| Endpoint | `POST /api/campaign/{cid}/apply_healing` (`tabletop_routes.py:14797`) | **none** |
| HP up path | `_apply_hp_change` (runs death-save state machine for dying-to-stable transitions) | no dedicated path — must edit HP manually via `/battle` PUT or trigger negative-damage via `_apply_damage_to_combatant` |

### Death saves

| Action | PC | NPC |
|---|---|---|
| Endpoints | `POST /character/{id}/death-save` (roll), `POST /override_death_save` (GM patch) | **none** |
| Storage | `sheet.death_saves = {status, successes, failures}` | n/a |
| State machine | alive → (HP=0) → dying → (3 successes) stable / (3 failures) dead; massive-damage rule (damage ≥ max_hp = instant death) | n/a — NPC at HP=0 = dead instantly |
| Wake on damage | when stable PC takes damage, → dying again | n/a |

### Rest

| Action | PC | NPC |
|---|---|---|
| Endpoint | `POST /character/{id}/rest` (`tabletop_routes.py:14931`) — short or long | **none** |
| Long rest effects | HP→max, temp HP cleared, hit dice refill, spell slots reset, resources refill | n/a |

### Resources

| Action | PC | NPC |
|---|---|---|
| Endpoint | `POST /character/{id}/resource` (`tabletop_routes.py:15204`) | **none** |
| Storage | `sheet.resources[] = [{key, name, current, max, reset}]` | NPCs use `combatant.action_charges[action_id]` (recharge tracker, NPC-only) |

### Class features

| Endpoint | Used by | NPC equivalent |
|---|---|---|
| `/use_feature` (generic) | various PC features | none |
| `/use_rage` | Barbarian | none |
| `/use_stunning_strike` | Monk | none |
| `/use_lay_on_hands` | Paladin | none |
| `/use_bardic_inspiration` | Bard | none |
| `/use_cutting_words` | Bard | none |
| `/use_arcane_recovery` | Wizard | none |
| `/use_metamagic_empowered_spell` | Sorcerer | none |
| `/use_font_of_magic_*` | Sorcerer | none |
| `/use_open_hand_technique` | Monk | none |
| `/use_patient_defense`, `/use_step_of_the_wind` | Monk | none |
| `/use_flurry_of_blows` | Monk | none |
| `/cast_hunters_mark` | Ranger | none |

NPCs execute their "feature-like" abilities through `/npc_attack` (weapon/spell-like single-target) or `/place_aoe` (AoE / save-DC).

### HP changes from the sheet

| Action | PC | NPC |
|---|---|---|
| Endpoint | `PATCH /character/{id}/sheet-fields` with HP fields (`tabletop_routes.py`) | `PUT /battle` (entire battle state replacement) |
| Broadcast | `character_hp_update` (v2.49.42) | `battle_update` with `force_gm_sync: True` (v2.49.40) |

### Concentration

| Action | PC | NPC |
|---|---|---|
| Storage | `ConcentrationEffect` ORM table, unique on `(campaign_id, character_id)` (`models.py:634`) | **none** |
| Endpoints | `POST /concentration`, `DELETE /concentration/{buff_key}` | none |
| Auto-save on damage | `_maybe_concentration_save` (`tabletop_routes.py:752`) fires on attack/save/sheet-patch damage | none |

---

## Server-side helpers (the unified-but-branching layer)

These helpers handle both PC and NPC inputs but internally branch on the caller's identity. They're the "good citizens" of the codebase — most of the unified behavior lives here.

### `_apply_damage_to_combatant` (`tabletop_routes.py:1876`)

Single entry point for all damage. Branches on `combatant.char_id` (PC) vs `combatant.token_template_id` (NPC):

- **PC branch:** `_resistance_halve` (sheet's `_buffs_active`) → `_apply_hp_change` (death-save state machine) → `character_hp_update` broadcast → `_maybe_concentration_save` → `_wake_sleeping_on_damage` → log to `_attack_damage_log` for undo.
- **NPC branch:** `_resistance_halve_npc` (template's `damage_resistances[]` + `combatant.buffs[]`) → direct `hp_current` mutation in hub → `battle_update` broadcast with `force_gm_sync: True` → `_wake_sleeping_on_damage` → log to `_attack_damage_log`.

### `_read_target_ac` (`tabletop_routes.py:1383`)

Unified AC lookup. Branches:
- PC: `character.sheet["ac"]`.
- NPC: `token_template.sheet["armor_class"]` or `token_template.sheet["ac"]`.
- Fallback: 10.

### `_resistance_halve` vs `_resistance_halve_npc`

| Helper | Source | What it reads |
|---|---|---|
| `_resistance_halve` (`tabletop_routes.py:10675`) | PC damage path | `sheet["_buffs_active"]` (buff list mirror) |
| `_resistance_halve_npc` (`tabletop_routes.py:10704`) | NPC damage path | template's static `damage_resistances[]` **AND** `combatant.buffs[]` |

> **History note:** Pre-v2.49.109, NPC resistance was silently ignored ("NPCs don't have resistance buffs yet"). v2.49.107 was the bug fix.

### `_check_cast_range` vs `_check_npc_attack_range`

Parallel range gates. The PC version supports three tiers (GM bypass / player override / strict enforcement); the NPC version is enforcement-only with an explicit `override_range` flag escape hatch. See [Range Enforcement](#range-enforcement) above for the rationale.

### `_target_has_dodging` (`tabletop_routes.py:10541`)

**Unified.** Scans the target combatant's `buffs[]` for `effects.dodging == True`, regardless of PC or NPC target. Both `/attack` and `/npc_attack` honor it as disadvantage on the d20.

### `_wake_sleeping_on_damage` (`tabletop_routes.py:1046`)

**Unified** (v2.49.61+). Resolves PC via `char_id` or NPC via `combatant_id` to find the affected combatant and clear the Sleep-derived Unconscious condition. Called from both damage application branches.

### Buff installation / lookup

| Helper | Scope | Works for NPCs? |
|---|---|---|
| `_install_buff(campaign_id, character_id, buff)` | PC by character_id | **No** — searches hub for `c.char_id == character_id`. NPCs have no char_id. |
| `_get_buffs(campaign_id, character_id)` | PC by character_id | **No** — same limitation. |
| `_remove_buff(campaign_id, character_id, key)` | PC by character_id | **No** — same. |

> **Tech debt flag:** NPCs DO carry buffs in `combatant.buffs[]` (installed directly by `/place_aoe` for AoE spells like Stoneskin / Bless / Spirit Guardians on NPCs), but there's no `_install_buff_for_combatant_id` / `_get_buffs_for_combatant_id` helper to manage them by id. New NPC-buff features must mutate the hub state directly. Filed as latent debt — a follow-up should add the helpers and migrate `/place_aoe` to use them.

### `_mark_battle_economy` / `_is_slot_used` (`tabletop_routes.py:282`)

**PC only.** NPCs aren't gated on action-economy; the GM is the rules authority and can chain attacks freely.

### Auto-uplifts (Rage / Hunter's Mark / Hex / Colossus Slayer)

**PC only.** `_compute_attack_auto_uplifts` (`tabletop_routes.py:11800`+) reads the attacker's buffs + class features and rolls bonus damage dice. NPCs have no auto-uplift computation.

---

## Client-side

### Mini-sheet rendering

| Element | PC | NPC |
|---|---|---|
| Strike button | `.mini-strike-btn` (`_mini_sheet_card.html`) — single 🗡 Strike per attack | `.monster-strike-btn` (init tracker, `tabletop.html:5139`) — 🗡 Strike (attack actions) + 📋 Save (save-DC actions) + 🎲 Dmg (rare damage-only) (v2.49.165+) |
| Cast button | `.mini-cast-btn` (PC spell list) | none (NPCs have no spell list UI) |
| Resources tracker | `.mc-resource-row` (multi-charge resources) | none |
| Death-save tracker | rendered when status == "dying" | n/a |
| Action-economy chips | rendered from `combatant.economy` | typically empty (no NPC economy data) |

### Target picker integration

**Unified module, different caster resolution:**

```js
// PC
vttOpenMultiTargetPicker({ required, spellName, casterCharId, rangeStr })

// NPC (v2.49.163+)
vttOpenMultiTargetPicker({ required, spellName, casterCombatantId, rangeStr })
```

The picker walks tokens to find the caster's center for the ruler line: PC via `t.character_id`, NPC via the combatant's `source_token_id` / `token_template_id+name` three-tier resolution.

### Roll-log card

**Unified shape** (`appendWeaponAttack`, `tabletop.js:5093`). NPC casts arrive on the same `weapon_attack` WS broadcast; the client falls back gracefully:

```js
const dispName = d.caster_char_name || USER_CHAR_NAMES[d.caster_user_id] || d.caster_user_name;
```

The card carries `is_npc_attack: True` and `caster_combatant_id` so future client code can branch on caster type without breaking existing renderers.

### HP bar rendering

| Surface | PC | NPC |
|---|---|---|
| Init tracker | HP bar from `combatant.hp_current/max` | same |
| Mini-sheet body | HP from `sheet.hp.current/max` | HP from `combatant.hp_current/max` (template max is static) |
| Token health pip | derived from combatant HP | same |

### Buff badges

**Unified.** Both PC and NPC buffs render as colored badges in the init tracker and mini-sheet.

---

## What NPCs don't support (the unsupported list)

These features exist for PCs but have **no NPC equivalent** at all:

1. **Spell casting** — no `/cast_spell` for NPC casters.
2. **Spell slots + tracked usage** — no slot system.
3. **Class resources** — no `/resource` endpoint.
4. **Death saves** — no state machine; NPCs die at 0 HP.
5. **Rests** — no `/rest` endpoint.
6. **Class features** — no `/use_<feature>` endpoints (Rage, Lay on Hands, Bardic Inspiration, Stunning Strike, Flurry of Blows, etc.).
7. **Concentration** — no `ConcentrationEffect` tracking, no `_maybe_concentration_save` on damage.
8. **Roll state override** — no `sheet.roll_state` equivalent (only buff-driven adv/dis like Dodging applies).
9. **Action economy** — no slot gating; GM can chain NPC attacks freely.
10. **Legendary actions** — stored in template but not mechanically enforced (no daily counter, no recharge tracking).
11. **Reactions** — no dedicated reaction tracking; opportunity attacks happen via manual `/npc_attack`.
12. **Buff installation by id** — `_install_buff` requires `character_id`; NPCs get buffs via `/place_aoe` direct hub mutation only.
13. **Auto-uplifts** — no Hunter's Mark / Hex / Colossus Slayer / Rage equivalent on NPC attacks.
14. **Multi-target attacks** — `/npc_attack` accepts a single target; PC `/attack` accepts `target_combatant_ids[]`.
15. **Multiattack chains** — a single NPC `Multiattack` action that fans out to N attacks isn't modeled; the GM clicks Strike N times manually.
16. **Cantrip scaling** — `_pick_damage_tier` (cantrip damage by level) is PC-only.
17. **Per-attack uplift dice** — `bonus_damage` body field is PC-only (Sneak Attack / Divine Smite have no NPC analog).

---

## Assessment — deliberate design vs accidental tech debt

### Deliberate (scope-limited by design)

- Spell casting, resources, death saves, class features, rests, action economy, cantrip scaling, per-attack uplifts — NPCs have no player-facing sheet UI, no persistent state between sessions, and no class identity. These are intentionally omitted (scope reduction).
- Spell-slot tracking — NPCs use stat-block actions; spell-slot accounting is a PC mechanic.
- Range enforcement difference (no GM bypass for NPCs) — deliberate v2.49.166 choice: the GM is *acting as* the NPC, not bending its rules. Explicit override flag is the escape hatch.

### Accidental tech debt

- **Concentration on NPCs** — mid-v2.19.0 buildout missed NPC support; concentration buffs (Hold Person, Hunter's Mark) installed *by* a PC on an NPC target work, but an NPC casting a concentration spell has no automatic concentration tracking. GM must manually `/end_buff`.
- **Lack of `_get_buffs_for_combatant_id` / `_install_buff_for_combatant_id` helpers** — the buff helpers all key on `character_id`, forcing AoE spells and similar features to mutate hub state directly when targeting NPCs.
- **Legendary-action daily counter** — `legendary_actions[]` stored in template but no `legendary_actions_per_round` enforcement.
- **NPC reactions** — stored in template, not enforced.
- **Multiattack** — a known gap; would need either a chain-of-attacks endpoint or a server-side fan-out from a single `Multiattack` action.

---

## When extending NPC support

If you're adding an NPC-facing feature, check this list first:

1. Does it need a new endpoint, or can it ride on `/npc_attack` / `/place_aoe`?
2. Does it need to install buffs? If yes — add the missing `_install_buff_for_combatant_id` helper first; don't bake combatant-id awareness into your new feature.
3. Does it need concentration tracking? If yes — flag it; NPC concentration is a larger lift.
4. Does it need spell slots / resources? If yes — likely better modeled as `action_charges` (NPC's per-action recharge tracker) than a port of the PC slot system.
5. Does it need to enforce range? Use `_check_npc_attack_range` (no GM bypass).
6. Should the broadcast reuse `weapon_attack` or invent a new type? Default to reusing — client renderers already fall back gracefully on missing `caster_char_id`.
7. Does it need a harness test? Yes — `tests/harness/test_npc_attack.py` is the canonical pattern.

---

## Related docs

- [`endpoint-catalog.md`](endpoint-catalog.md) — full endpoint inventory (PC + NPC + tabletop ops).
- [`realtime-broadcasts-catalog.md`](realtime-broadcasts-catalog.md) — WS message shapes including `weapon_attack` payload.
- [`architecture-overview.md`](architecture-overview.md) — the hub state, ORM models, broadcast pipeline.
- [`../plans/ruler-and-range.md`](../plans/ruler-and-range.md) — range enforcement design rationale.
- [`../plans/death-saves.md`](../plans/death-saves.md) — PC death-save state machine.
