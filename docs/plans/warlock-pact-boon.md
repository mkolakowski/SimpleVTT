# Warlock Pact Boon — design plan

**Status:** ⚪ proposed (v2.49.119, 2026-05-22) — no code yet.
**Authors:** rolling
**Last updated:** 2026-05-22

A plan to ship the **Pact Boon** feature (Warlock Lv 3) — a
subclass-shaping pick where the warlock chooses one of three gifts
from their patron: Pact of the Chain (familiar), Pact of the Blade
(summoned weapon), or Pact of the Tome (3 extra cantrips). Each
boon has distinct mechanics; the plan covers all three in a
phased rollout.

Demo subject: **Magnus Hexbinder** (Warlock Lv 3, The Fiend
patron) — already in the demo seed since v2.18.4 with placeholder
Pact features waiting on the picker. Pact Boon is gated at Lv 3
RAW, so Magnus is exactly the level the rule unlocks.

---

## Why this matters

Pre-plan state in `class-content-status.md`:

| Lv | Feature | Status |
|---|---|---|
| 1 | Otherworldly Patron | ✅ subclass shipped; The Fiend features 🟡 |
| 1 | Pact Magic | 🟡 |
| 2 | Eldritch Invocations | 🟡 picker not wired |
| 3 | **Pact Boon** | **⚪ no plan, no code** |
| 11 / 13 / 15 / 17 | Mystic Arcanum | ⚪ |
| 20 | Eldritch Master | ⚪ |

Pact Boon is the most player-facing pick at low Warlock levels —
it shapes the Warlock's identity (familiar-toting / blade-wielding
/ tome-studying) before the higher-level features layer on. Without
it, the demo Warlock is a one-trick Eldritch Blast caster.

---

## Design principles

1. **One picker, three boons, three Phase commits.** The picker
   itself is small (3 radio buttons + Confirm). Each boon has its
   own implementation phase — Tome is the simplest (sheet-side
   cantrip list mutation), Chain is medium (familiar combatant +
   action proxy), Blade is the most complex (summoned weapon as
   an attack row + magical-damage tagging).
2. **Pick is permanent until long rest.** RAW says Pact Boon is
   a once-per-level choice — the warlock picks at Lv 3, can't
   change without a class feature reshuffle. The plan's picker is
   a one-time pick stored on the sheet (`warlock_pact_boon: "chain"
   | "blade" | "tome"`). A GM-only edit lets the GM unstick a
   bad pick.
3. **Pact-Boon-driven downstream features.** Several Eldritch
   Invocations gate on the chosen Pact Boon (e.g. "Improved Pact
   Weapon" needs Blade). The Eldritch Invocations picker (Phase 5
   of THIS plan, or its own commit later) reads
   `sheet["warlock_pact_boon"]` to filter the available rows.
4. **Sheet-side picker + endpoint pattern.** Same shape as the
   v2.49.112 Patient Defense pattern: a sheet click handler pops
   a picker modal, the chosen boon POSTs to a dedicated endpoint
   that validates Warlock Lv 3+ + persists the pick.

---

## Phase 0 — Picker + boon-storage infrastructure

**Goal:** Pact Boon picker + persisted choice on the sheet. No
boon mechanics yet — just the data.

### Endpoint

`POST /api/campaign/{cid}/use_pact_boon_pick`
- Body: `{character_id, boon: "chain" | "blade" | "tome"}`
- Validates Warlock Lv 3+, `boon` in the allowed set.
- Stores the choice on the sheet: `sheet["warlock_pact_boon"] = boon`.
- Adds a class-feature row to the sheet's `class_features` list
  for the chosen boon's mechanics (placeholder for Phase 1+).
- Broadcasts `feature_used` (announces the pick), `sheet_patch`
  (updates open sheet drawers across the campaign).

### Picker UI

A modal on the Warlock's sheet, opened by an "Active your Pact
Boon" button in the class-features block. Three radio rows + a
description tooltip per row + Confirm. Once the boon is set, the
button is replaced with a static badge ("Pact of the Blade") on
the sheet.

### Tests

`tests/harness/test_use_pact_boon_pick.py`:
- Happy path each boon (3 tests): Magnus picks Chain / Blade /
  Tome; verify `sheet["warlock_pact_boon"]` is set + the right
  class-feature row appears.
- 409 `wrong_class`: a Wizard tries to pick.
- 409 `level_too_low`: a Lv 1 Warlock tries (need a fixture).
- 409 `already_picked`: re-picking without GM-side override is
  rejected.

**Exit criterion:** Magnus can pick a Pact Boon end-to-end. The
sheet shows the chosen boon. The next phase implements its
mechanics.

---

## Phase 1 — Pact of the Tome (simplest)

**Goal:** Tome boon mechanics — three cantrips from any class's
spell list, learned permanently.

RAW PHB p.108: "Your patron gives you a grimoire called a Book of
Shadows. When you gain this feature, choose three cantrips from
any class's spell list. While the book is on your person, you can
cast those cantrips at will."

### Endpoint

`POST /api/campaign/{cid}/use_pact_tome_pick_cantrips`
- Body: `{character_id, cantrip_slugs: [str, str, str]}`
- Validates Warlock Lv 3+ with `pact_boon == "tome"`, three slugs
  passed, each slug resolves to a level-0 spell in
  `app/data/local/dnd5e/spells/`.
- Appends the three cantrips to the warlock's `spells` list on
  the sheet (marked as `tome_grant: true` so future cleanup can
  recognize them).
- Broadcasts `sheet_patch` + `feature_used`.

### Picker UI

A second-stage modal AFTER the Phase 0 picker — when the player
picks "Tome", the modal swaps to a 3-cantrip-selector with a
spell-catalog filter. Reuses the spell-catalog loader from the
v2.49.108 spell-validation suite.

### Tests

- Happy path: pick Tome → pick (Light, Vicious Mockery, Toll the
  Dead) → all three appear in Magnus's spell list with the
  `tome_grant: true` flag.
- 400 wrong-number-of-cantrips (not exactly 3).
- 400 invalid slug.
- 400 picked a leveled spell, not a cantrip.

**Exit criterion:** Magnus has three extra cantrips on his sheet
he can cast via the existing `/cast_spell` endpoint without any
extra wiring.

---

## Phase 2 — Pact of the Chain

**Goal:** Familiar combatant exists; warlock can attack via the
familiar's action proxy.

RAW PHB p.107: "You learn the find familiar spell and can cast it
as a ritual. The spell doesn't count against your number of
spells known. When you cast the spell, you can choose one of the
normal forms for your familiar or one of the following special
forms: imp, pseudodragon, quasit, or sprite."

### Familiar template

Add four monster templates to the SRD content under
`app/data/local/dnd5e/monsters/` (or campaign-scoped fixtures):
imp, pseudodragon, quasit, sprite. Each gets the standard stat
block + a `pact_familiar: true` flag.

### Endpoint

`POST /api/campaign/{cid}/use_pact_chain_summon`
- Body: `{character_id, familiar_form: "imp"|"pseudodragon"|"quasit"|"sprite"}`
- Validates Warlock Lv 3+ with `pact_boon == "chain"`, no
  existing familiar in init for this caster.
- Creates a combatant entry from the chosen template, marks
  `source_caster_id = char.id` + `pact_familiar = True`, places
  next to the warlock's token.
- Broadcasts `battle_update` + `feature_used`.

### Action proxy

When a familiar is in init AND owned by the warlock, the warlock
can use their action to command the familiar to take the Attack
action via a dedicated `POST /use_pact_chain_command_attack`
endpoint. The familiar's attack rolls with the warlock's spell
attack bonus + familiar's damage dice + appropriate damage type.

### Tests

- Happy path: pick Chain → summon imp → imp appears in init →
  command attack → imp's stinger attack lands on a bandit.
- 409 if no Pact Boon picked yet.
- 409 if a familiar already exists for this warlock.

**Exit criterion:** Magnus can summon an imp + use it to attack.

---

## Phase 3 — Pact of the Blade (most complex)

**Goal:** Summon a magical melee weapon as an action; weapon
attacks use CHA instead of STR/DEX; weapon counts as magical
for resistance bypass.

RAW PHB p.107-108: "You can use your action to create a pact
weapon in your empty hand. You can choose the form that this
melee weapon takes each time you create it. You are proficient
with it while you wield it. This weapon counts as magical for
the purpose of overcoming resistance and immunity to nonmagical
attacks and damage."

### Endpoint

`POST /api/campaign/{cid}/use_pact_blade_summon`
- Body: `{character_id, weapon_kind: "longsword"|"battleaxe"|"glaive"|... }`
- Validates Warlock Lv 3+ with `pact_boon == "blade"`.
- Adds the weapon to the warlock's `attacks` list with the
  `pact_blade: true` flag + CHA-mod attack bonus + appropriate
  damage dice.
- Marks the action chip.
- Broadcasts `sheet_patch` + `feature_used` + `economy_update`.

### Attack-flow integration

When a `/attack` call uses an `attack_index` that points to a
`pact_blade: true` row, the to-hit bonus is computed from CHA
(not STR/DEX), and the damage type tag includes `magical: true`
so the v2.49.107 / v2.49.109 resistance halving correctly
distinguishes magical vs nonmagical (filed in the damage review
follow-ups as the "nonmagical-only resistance" expansion).

### Dismiss + re-summon

A `POST /use_pact_blade_dismiss` endpoint removes the weapon
from the attacks list. Re-summoning is just another
`/use_pact_blade_summon` call.

### Tests

- Happy path: pick Blade → summon longsword → weapon appears
  in attack list → strike with CHA-mod bonus + magical tag.
- 409 if no Pact Boon picked.
- 409 if Pact Boon ≠ Blade.
- Dismiss + re-summon cycle clean.

**Exit criterion:** Magnus can summon a pact weapon + strike
with it using his CHA stat.

---

## Phase 4 — Class table updates + class-content-status doc

**Goal:** flip the Pact Boon row from ⚪ to ✅ in
`class-content-status.md`; update the per-feature plan section
with shipped status + commit refs.

---

## Phase 5 — Pact-eligible Eldritch Invocations

**Goal:** unlock the Invocations that gate on a specific Pact
Boon. Examples:

- **Improved Pact Weapon** (needs Blade): summoned weapon gets
  +1 to attack/damage; can be a ranged weapon.
- **Thirsting Blade** (needs Blade, Lv 5+): make two attacks
  instead of one when taking Attack action with a pact weapon.
- **Voice of the Chain Master** (needs Chain): communicate
  telepathically with familiar; perceive through familiar's
  senses.
- **Book of Ancient Secrets** (needs Tome): three extra ritual
  spells from any class list.

Each invocation that gates on a Pact Boon gets its own row in
the Eldritch Invocations picker (filed separately under the
existing 🟡 Eldritch Invocations row in the Warlock class table).

---

## Open questions

- **Pact Boon respec.** RAW doesn't allow re-picking the Pact
  Boon. A GM-edit path (sheet-edit clears the `warlock_pact_boon`
  field) should be the only way to change it. Document in the
  picker modal's footer.
- **Pact of the Chain familiar HP.** RAW the familiar has the
  same HP as its stat block; if killed, the warlock can re-summon
  by casting Find Familiar (1-hour ritual). For v1, the re-
  summon endpoint requires a long rest. Filed.
- **Pact of the Blade + non-warlock multiclass.** A Warlock/Fighter
  multiclass with both Extra Attack + Thirsting Blade could
  theoretically attack 4 times. Out of scope for v1; the v2.49.117
  Flurry chip refund pattern can be extended once the Blade attack
  flow exists.

---

## Risks

| Risk | Mitigation |
|---|---|
| Pact Boon picker conflicts with the existing Otherworldly Patron picker. | Otherworldly Patron is a Lv 1 pick (subclass system shipped); Pact Boon is Lv 3 (separate picker, separate `warlock_pact_boon` field on the sheet). No collision. |
| Familiar combatant pollutes init tracker. | Mark familiar combatants with `pact_familiar: True` so the GM can filter / hide; add a "Dismiss Familiar" button on the warlock's sheet. |
| Pact Blade attack rolls compete with the existing attack-row schema. | Add a `pact_blade: True` flag; the attack-flow reads it for the CHA-mod bonus + magical-damage tag. Same pattern Hex Warrior uses (filed separately for Hexblade subclass). |

---

## Status tracking

- [ ] Phase 0 — Picker + boon-storage infrastructure
- [ ] Phase 1 — Pact of the Tome
- [ ] Phase 2 — Pact of the Chain
- [ ] Phase 3 — Pact of the Blade
- [ ] Phase 4 — Class table updates
- [ ] Phase 5 — Pact-eligible Eldritch Invocations

Each checkbox flips green as the corresponding commit lands; the
status line at the top of this doc is updated in the same commit.
