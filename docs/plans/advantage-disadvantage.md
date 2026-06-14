# Advantage & Disadvantage Tracking — Design Plan

**Status:** Phase 1 shipped in **v2.2.0**, refined in **v2.2.2** (full-sheet skill-click cross-character rollover fix) and **v2.2.3** (pill promoted from cramped HP card to a full-width row). Cross-character rollover regression caught + re-fixed at **v2.3.18** when the mini-sheet handlers moved to document-level delegation.
**Phase 2a shipped in v2.152.0** — attacker-side condition automation (Blinded / Poisoned / Restrained / Frightened / Prone → disadvantage; Invisible → advantage) and target-side condition automation (Blinded / Paralyzed / Petrified / Restrained / Stunned / Unconscious → advantage) auto-layer into `/attack`'s adv/dis source set via three new helpers reading existing `_buffs_active` (PC) / combatant.buffs (NPC) condition keys.
**Phase 2b shipped in v2.153.0** — `/api/campaign/{id}/roll` parity. Conditions now also gate disadvantage on saves + ability checks via a new `_roll_condition_disadvantage(sheet, stat_key, stat_ability)` helper that reads the same `_buffs_active` mirror, classifies the roll by `stat_key` / `stat_ability`, and composes with the existing `_apply_roll_state` output per PHB p.173 cancel logic. Conditions covered: Poisoned + Frightened → disadvantage on ability checks; Restrained → disadvantage on DEX saves.
**Phase 2c shipped in v2.154.0** — `/npc_attack` parity. The NPC-attack adv/dis source set is now symmetric with PC `/attack`: NPC attacker condition disadvantage (Blinded / Poisoned / Restrained / Frightened / Prone), NPC attacker Invisible advantage, and target condition advantage (Blinded / Paralyzed / Petrified / Restrained / Stunned / Unconscious) all fold in. Two new hub-state helpers — `_npc_attacker_has_condition_disadvantage` + `_npc_attacker_has_invisible_advantage` — read the attacker's combatant.buffs (no sheet mirror needed for NPCs). RAW PHB p.173 cancel logic.
**Phase 2d shipped in v2.155.0** — NPC saves parity. PC casters auto-rolling NPC-target saves (single-target `/cast_spell`, AoE `/place_aoe`, the shared resolution helper, `/use_open_hand_technique`, NPC-caster `/npc_cast_spell`) now read `target_combatant.buffs` via a new `_npc_save_condition_disadvantage(target_combatant, stat_key)` helper. RAW Restrained → DEX-save disadvantage. Six NPC-save construction sites wired uniformly.
**Phase 2e shipped in v2.156.0** — auto-fail STR/DEX saves from Paralyzed / Stunned / Unconscious / Petrified per RAW PHB Appendix A. Separate mechanic from adv/dis — the d20 still rolls (broadcast remains transparent) but the outcome is forced FAIL regardless of total. One shared helper `_saver_auto_fails_strdex_save(buffs_iter, stat_key_lc)` works on both PC `_buffs_active` and NPC `combatant.buffs`. Wired into the PC-save resolver (`respond_roll_request`) + all six NPC-save construction sites.
**Phase 2f shipped in v2.157.0** — NPC `/roll` parity for ability checks + saves. The unified mini-sheet's NPC stat-block buttons now pass `combatant_id` into the `/roll` body when the click originated from an init-tracker entry; the server's `/roll` handler reads it as an NPC fallback that mirrors Phase 2b's PC composition (Poisoned/Frightened → check dis; Restrained → DEX-save dis) via a new hub-state helper `_npc_roll_condition_disadvantage`.
**Phase 3 still deferred** — needs Maps 2.0 positional awareness for 5-ft prone-melee advantage / prone-ranged disadvantage. See [Implementation status](#implementation-status) below for the per-phase breakdown.
**Phase 4a shipped in v2.252.0** — **item-granted adv/dis (Cloak of Displacement)**. The first target-side item disadvantage: an equipped + attuned Cloak of Displacement (RAW DMG p.158) sets `incoming_attacks_have_disadvantage` in `_equipped_item_effects`, and the `/attack` + `/npc_attack` pipelines read it at attack time via `_target_wearer_imposes_attack_disadvantage` (target combatant → character → sheet), folding it into the existing disadvantage source set. Attacks against the wearer roll `2d20kl1`; the PHB p.173 cancel logic handles adv+dis for free. Phase 4b+ (suppress-after-damage, Elvenkind stealth-advantage via `/roll`, Eyes of the Eagle) remain filed. See [Phase 4 — Item-granted adv/dis](#phase-4--item-granted-advdis) below.
**Tracked in:** [`TODO.md`](../../TODO.md) → Combat → Advantage & Disadvantage Tracking.

---

## Implementation status

(Annotation pass v2.3.26 — audited against CHANGELOG / code.)

- ✅ **Phase 1 — Manual toggle** — done in v2.2.0. `Character.sheet.roll_state`, `_apply_roll_state()` server helper with the regex contract, `POST /character/{id}/roll-state` endpoint, `_roll_state_pill.html` partial on mini-sheet + full sheet, GM token-context "Roll state" submenu (v2.3.17), roll-log `(auto …)` / `(manual …)` indicators, initiative exempt via `skip_roll_state`, damage rolls unaffected.
- 🔄 **Cross-character rollover** — initial bug where the GM's pill bled into other characters' rolls fixed in v2.2.2 (full sheet path) and again in v2.3.18 (mini-sheet handlers moved to document-level delegation; monster mini-sheets always set `skip_roll_state: true`).
- ✅ **Phase 2a — Condition automation (attacker- and target-side, ex-Prone)** — shipped in **v2.152.0**. Three new helpers near the existing AP/UM Phase 1b helpers — `_attacker_has_condition_disadvantage(sheet)` / `_attacker_has_invisible_advantage(sheet)` / `_target_has_condition_advantage(campaign_id, target_combatant_id)` — fold into both `/attack` adv/dis branches (bonused + bonusless) as additive source-set entries alongside Rage / Dodge / Reckless / Assassinate / AP / UM. The original "depends on a conditions system" deferral was outdated: the v2.97.30 `_buffs_active` mirror + the combatant.buffs hub state already serve as the conditions system. Standard 5e attacker-disadvantage condition keys: `{blinded, poisoned, restrained, frightened, prone}`. Standard 5e target-advantage condition keys: `{blinded, paralyzed, petrified, restrained, stunned, unconscious}`. Prone is intentionally excluded from the TARGET set — RAW it only grants advantage on MELEE attacks within 5 ft, which needs Phase 3 positional awareness. Cancel logic unchanged: `has_adv and has_dis` → `canceled_<adv_label>_vs_<dis_label>` straight roll per PHB p.173.
- ✅ **Phase 2b — `/api/campaign/{id}/roll` parity** — shipped in **v2.153.0**. New `_roll_condition_disadvantage(sheet, stat_key_lc, stat_ability)` helper (sits next to the Phase 2a helpers) returns a condition key matched to the roll classification: Poisoned + Frightened on ability checks (RAW PHB Appendix A); Restrained on DEX saves only (RAW). Wired into `/roll` after the existing `_apply_roll_state` call with full RAW PHB p.173 cancel logic — manual `1d20a` / `2d20kh1` (advantage) + condition-driven disadvantage reverts to a straight 1d20 with a `canceled_*_vs_disadvantage_*` label; manual disadvantage stacks as a no-op; no prior roll_state + condition fires → `auto_disadvantage_<key>`. Generic untyped `/roll` calls (no `stat_key`) don't fire — the conservative default is "don't auto-disadvantage rolls we can't classify."
- ✅ **Phase 2f — NPC `/roll` parity (ability checks + saves)** — shipped in **v2.157.0**. New hub-state helper `_npc_roll_condition_disadvantage(campaign_id, combatant_id, stat_key_lc, stat_ability)` mirrors the Phase 2b PC version (same `_CHECK_DIS_CONDITION_KEYS` / `_DEX_SAVE_DIS_CONDITION_KEYS` frozensets). Client change in `app/templates/tabletop.html`'s `.mini-roll-btn` handler: when the click originates from an init-tracker entry (isMonster + `charIdRaw` NOT prefixed with `monster-`), stamp `combatant_id: charIdRaw` into the POST body. Server change in `/roll` handler: after the existing PC condition-dis composition, fall back to the NPC helper when `cond_dis_key` is still None AND the body carries `combatant_id`. PC and NPC paths are mutually exclusive — PC has `_char`, NPC has `skip_roll_state` + `combatant_id`. Template-browser monster clicks (`charIdRaw` = `monster-<tid>`) deliberately don't pass `combatant_id` — they have no associated combatant.
- ✅ **Phase 2e — Auto-fail STR/DEX saves from Paralyzed / Stunned / Unconscious / Petrified** — shipped in **v2.156.0**. Separate mechanic from adv/dis: the d20 still rolls (broadcast transparency), but the outcome is forced FAIL. One shared helper `_saver_auto_fails_strdex_save(buffs_iter, stat_key_lc)` works for both PC `_buffs_active` and NPC `combatant.buffs`. PC path refactor: `respond_roll_request` now derives a single `_save_passed_final` flag that gates the note outcome, the Silvery-Barbs / Chronal-Shift watcher prompt, the condition-install path, AND the AoE-PC damage-applied math — so a Paralyzed PC failing a DEX save against Banishment still installs Banished even on a natural 20. NPC path: each of the six NPC-save construction sites (same as Phase 2d) overrides `auto_save_passed = False` after the comparison. Filed follow-ups: NPC ability checks via `/roll` (the unified mini-sheet's stat-block click path) still don't pass a combatant_id — a client-side change is needed before the helper can read NPC buffs there; concentration-save auto-fail when a paralyzed/stunned creature takes damage (RAW: concentration saves are CON saves so not auto-fail per the four conditions, but the implicit "Incapacitated → can't take actions" means concentration drops via the v2.49.51 hook on Stun/Paralysis/Unconscious — likely already handled).
- ✅ **Phase 2d — NPC-save parity** — shipped in **v2.155.0**. New `_npc_save_condition_disadvantage(target_combatant, stat_key_lc)` helper reads the NPC target's `combatant.buffs` directly + classifies by stat_key. RAW Restrained → DEX-save disadvantage (the only adv/dis condition that lands on saves per PHB Appendix A — Paralyzed/Stunned/Unconscious/Petrified auto-fail STR/DEX saves, a separate mechanic filed for follow-up). Wired into all six NPC-save construction sites: `/cast_spell` single-target PC→NPC (~line 18287), `/place_aoe` NPC save (~line 19920), shared save-resolution helper (~line 26995), two additional PC-caster spell sites (~lines 40005, 40426), and `/npc_cast_spell` NPC→NPC (~line 75836). Composes cleanly with the v2.97.35 Bless/Bane suffix (the `replace("1d20", "2d20kl1", 1)` only touches the leading d20 so the +1d4/-1d4 suffix is preserved).
- ✅ **Phase 2c — NPC-attack parity** — shipped in **v2.154.0**. Two new hub-state helpers next to the Phase 2a/2b helpers: `_npc_attacker_has_condition_disadvantage(campaign_id, attacker_combatant_id)` (reuses `_ATTACKER_DIS_CONDITION_KEYS`) and `_npc_attacker_has_invisible_advantage(campaign_id, attacker_combatant_id)`. Both walk hub state for the attacker's combatant.buffs (no sheet mirror needed). The `/npc_attack` adv/dis composition now layers all three Phase 2 source-set sides (attacker dis, attacker invisible adv, target condition adv) and replaces the pre-existing v2.49.238 reckless-only branch with the full PC-symmetric composition. `roll_state_applied` is now echoed in the `/npc_attack` response too (matching PC `/attack`), so clients + tests can read which condition or combination drove the roll. Cancel logic matches PHB p.173.
- ⏸ **Phase 3 — Context-aware rolls** — deferred. 5-ft-melee advantage on prone targets / prone-ranged disadvantage depends on Maps 2.0 grid-distance awareness, also not yet shipped. The prone-attacker disadvantage half DID ship in Phase 2a (PHB p.292 — prone melee + ranged are both disadvantaged from the attacker's side).
- ❌ **Elven Accuracy / 3d20kh1** — explicitly out of scope from day one; deferred to a feats-action follow-up.
- ❌ **NPC / monster token adv/dis** — out of scope from day one. Partially addressed in v2.3.18: monster mini-sheet rolls pass `skip_roll_state: true` so the GM's own char's pill never bleeds into monster checks, but monsters themselves still don't have a settable pill.
- 🟠 **Phase 4 — Item-granted adv/dis** — Phase 4a shipped v2.252.0 (Cloak of Displacement: attacks against the wearer have disadvantage, wired through a target-side equipped-item read). Phase 4b+ (suppress-after-damage, Elvenkind stealth-advantage via `/roll`, Eyes of the Eagle) still filed. See [Phase 4 — Item-granted adv/dis](#phase-4--item-granted-advdis).

---

---

## Goal

Eliminate the repetitive manual `adv` / `dis` dice-button picking for d20 rolls. A character has an explicit "roll state" (advantage / normal / disadvantage); any d20 ability check, save, attack, or skill check that character rolls is automatically upgraded server-side. Manual buttons remain for one-shot overrides.

The hourly grind of "click the dis button, then click the dis button, then click the dis button" for a Restrained character goes away. One toggle, all subsequent d20 rolls honor it.

---

## Design principle: manual buttons preserved as override

The auto-state is a **convenience layer on top of** the existing dice picker, not a replacement. The manual `adv` / `dis` buttons keep working unchanged. The auto-state only upgrades single-d20 expressions; anything the player or GM rolls manually as `2d20kh1` or `2d20kl1` is left alone.

Edge cases that need manual buttons:

- **One-shot effects** — Bless grants advantage on the next save only; easier to click `adv` once than toggle the state and clear it
- **Feature-granted adv on a specific roll** — Reckless Attack, Help action, Pack Tactics; these grant adv on a single roll, not a state
- **GM override** — GM decides "you've got a good angle on this one" without modifying the character's tracked state
- **Conflict resolution by player choice** — character has `dis` set from being prone, but the player wants to manually pick `adv` because a feature grants it; the manual click wins

This split also makes 5e RAW conflict handling tractable for v1: we don't need to compute "auto says adv + manual says dis → normal"; we respect whatever the player clicks. If they manually picked `2d20kh1`, that's what rolls.

---

## Architectural decisions

### 1. Server-side interception, not client-side

The advantage/disadvantage upgrade happens inside `/api/campaign/{id}/roll` and `/api/campaign/{id}/attack`, before the dice are rolled, by inspecting the rolling character's roll state.

**Why:** all roll surfaces (mini-sheet, full sheet ability/save/skill clicks, action buttons, attack rolls, roll-request responses) already funnel through these two endpoints. Intercepting server-side means a stale client or a player editing their browser can't bypass the toggle, and we avoid wiring the logic into 6 separate UI handlers.

**Tradeoff:** quick-roll buttons on the tabletop dice picker that aren't tied to a character (raw `1d20` by the GM with no character context) won't auto-apply. Acceptable — those are usually deliberate.

### 2. State lives in `Character.sheet.roll_state`

Add one nested field to the character sheet JSON:

```json
"roll_state": { "value": "advantage" | "disadvantage" | null }
```

**Why over a new table:** zero schema migration, ships under existing edit-character plumbing, broadcasts over the existing character-update WebSocket. Adv/dis state is per-character anyway; a sidecar table would just duplicate `character_id`.

**Tradeoff:** the state persists until manually cleared (no auto-reset between sessions). Mitigated by surfacing a 🔄 "Clear" affordance prominently in the UI. Phase 2 will auto-clear based on condition expiry; until then it's manual.

### 3. Regex contract — only single-d20 expressions are upgraded

Server-side regex match. Only single-d20 expressions are eligible:

- ✅ `1d20`, `1d20+5`, `1d20-2`, `1d20+stat`, `1d20+prof+stat`
- ❌ `2d20kh1` / `2d20kl1` (already advantage/disadvantage — left alone; this is also the line between auto-state and manual choice)
- ❌ `3d20*` / multi-d20
- ❌ `4d6kh3`, `3d8+5`, `8d6` (damage / generation rolls)
- ❌ Any expression with two or more dice terms

**Why:** keeps behavior predictable and matches 5e semantics — adv/dis applies to d20 tests, not damage. Damage rolls keep working as-is.

### 4. Initiative is exempt

Initiative rolls (`1d20+dex`) match the regex and would auto-upgrade by default. **The initiative endpoint sets a `skip_roll_state` flag** to bypass the upgrade.

**Why:** 5e RAW has no general rule that initiative honors advantage/disadvantage from conditions. Specific features (e.g. Alert) grant adv on initiative; players can use the manual `adv` button for those. Auto-applying every condition's adv/dis to initiative would surprise tables.

If you want initiative to honor the toggle, flip one constant. Easy to revisit.

### 5. UI surfaces

**Three touchpoints** (Phase 1):

1. **Mini-sheet** — a compact tri-state pill: `[Adv | Normal | Dis]`. Single click swaps state. Color-coded (green / neutral / red) so the player and GM can see at a glance.
2. **Full character sheet** — same pill in the header, next to HP.
3. **Token context menu** (GM-side) — "Grant advantage / disadvantage / clear" — lets the GM set state for any character without opening their sheet.

**Visibility:** the rolling player sees the upgrade reflected in the roll-log card. The log distinguishes auto vs manual:

- `1d20+5` rolled by a char with `roll_state=adv` → `"Stealth check (auto advantage): 2d20kh1+5..."`
- `2d20kh1+5` rolled manually (any roll_state) → `"Stealth check (manual advantage): ..."`
- `1d20+5` rolled by a char with `roll_state=null` → `"Stealth check: ..."`

Players see clearly *why* the dice doubled.

---

## Phase scope

### Phase 1 — Manual toggle (ships now) — ✅ shipped v2.2.0

Manual set/clear via UI; server intercepts single-d20 expressions; WebSocket broadcasts state change so other clients refresh. Manual buttons preserved as override. Self-contained.

### Phase 2 — Condition automation (later, after conditions system lands) — ⏸ deferred

Conditions like Blinded / Prone / Restrained / Invisible / Poisoned push entries onto `adv_sources` or `dis_sources` lists. Effective state is computed (any adv + any dis → cancels to normal; per 5e RAW, multiple advs don't stack). Removing a condition pops its entry. Manual toggle becomes one source on the list (`source: "manual"`) so it composes cleanly.

Backward-compatible — Phase 1 manual state migrates to `adv_sources: ["manual"]`.

### Phase 3 — Context-aware rolls (later, after Maps 2.0) — ⏸ deferred

Attack rolls against a token within 5 ft of a prone target → auto-advantage. Ranged attacks against a prone target → auto-disadvantage. Needs the combat system to know token positions and target identity, which Maps 2.0 brings.

---

## Files to add (Phase 1)

- **`app/templates/_roll_state_pill.html`** — reusable Jinja partial rendering the tri-state pill. Used by both the mini-sheet and full sheet.

---

## Files to modify (Phase 1)

### `app/routes/tabletop_routes.py`
- Add `_apply_roll_state(expression: str, roll_state: dict | None) -> tuple[str, str]` helper that returns `(modified_expression, note)`. Pure function, easy to unit-test. Implements the regex contract from decision #3.
- `/api/campaign/{id}/roll` — if `character_id` is in the payload and the request doesn't carry `skip_roll_state`, look up the character's `roll_state` and run the expression through the helper before rolling. Result includes `roll_state_applied: "advantage" | "disadvantage" | null` so the client log renders the indicator.
- `/api/campaign/{id}/attack` — same upgrade path for the attack-roll d20.
- Initiative endpoint passes `skip_roll_state=True` (decision #4).
- New `POST /api/campaign/{id}/character/{char_id}/roll-state` — sets/clears state for a character. Body: `{value: "advantage" | "disadvantage" | null}`. GM or character owner only. Broadcasts a `character_roll_state` WebSocket message.

### `app/static/sheet.js` / `app/static/sheet_dnd5e.html`
- Render the pill in the sheet header. Click handlers POST to the new endpoint.
- Roll-log renderer recognizes `roll_state_applied` and prepends `(auto advantage)` / `(auto disadvantage)` to the note. Manual `2d20kh1` / `2d20kl1` rolls get `(manual ...)` instead.

### `app/static/tabletop.js`
- Mini-sheet renders the pill.
- WebSocket handler for `character_roll_state` updates any open mini-sheet pills.
- Token context menu (GM) gets a "Roll state" submenu.

### `app/static/style.css`
- `.roll-state-pill` family — tri-state styling. Green tint for adv, red for dis, neutral for normal.

### `app/version.py` + `CHANGELOG.md`
MINOR bump (additive feature, no schema change).

---

## Verification

1. **Set advantage from mini-sheet** — toggle pill on Alice's mini-sheet to "Adv". Roll a Stealth check from her sheet. Log shows `(auto advantage)`, dice resolve as `2d20kh1`.
2. **Persistence across reload** — refresh the page; the pill is still on "Adv".
3. **GM-side toggle** — as GM, right-click Bob's token → "Grant disadvantage". Bob's mini-sheet pill updates over WebSocket without a refresh.
4. **Damage roll unaffected** — with adv set, fire a weapon attack. The attack d20 upgrades; the damage `1d8+3` does not.
5. **Already-modified expression left alone** — set adv, then manually roll a `2d20kl1` (disadvantage). Server does NOT add a third d20 — original expression rolls verbatim.
5a. **Manual button overrides auto-state** — set `roll_state=disadvantage` on Alice. Click manual `adv` dice button + roll. Log shows `(manual advantage)`, dice resolve as `2d20kh1`. Auto-disadvantage bypassed.
5b. **Manual `dis` with auto-`dis`** — set `roll_state=disadvantage`. Click manual `dis` button + roll. Resolves as `2d20kl1` exactly once (no triple-d20). Log says `(manual disadvantage)`.
5c. **No state + manual buttons** — clear roll state. Manual `adv` button works as it does today.
6. **Non-d20 expressions ignored** — set adv, roll a `4d6kh3` (ability score gen). Server doesn't touch it.
7. **Clear state** — click "Normal" or 🔄 Clear. Next d20 rolls normally.
8. **Permission guard** — Alice tries to set Bob's roll state via the API. Server returns 403.
9. **Roll log indicator** — every adv/dis-affected roll in the log carries the `(auto ...)` or `(manual ...)` parenthetical.
10. **Initiative exempt** — set adv on Alice. Roll initiative for her. Server resolves a single `1d20+dex` with no upgrade. Log carries no roll-state indicator for initiative.

---

## Out of scope (Phase 1)

- **Elven Accuracy / similar features** — turning adv into 3d20kh1. Defer to a feats-action follow-up.
- **Roll-request prompts honoring per-target state** — the GM-issued roll request fires `1d20+stat` for every targeted player; Phase 1 lets each player's own roll state upgrade their individual roll, but the prompt itself doesn't pre-mark "this is an advantage roll." Acceptable — the upgrade is transparent in the result.
- **Auto-clear after a single roll** — covered by the manual buttons for one-shot effects like Bless. No need for a separate "next-roll-only" auto-state.
- **Auto-clear on long rest** — kept out of Phase 1 to ship cleanly. Could be added later as a small follow-up: `roll_state.reset_on_long_rest: bool`.
- **NPC / monster tokens** — Phase 1 only applies state to player characters (`character_id` required). Adding adv/dis to monster stat blocks means storing it on the Token row; deferred to Phase 2 or its own follow-up.

---

## Commit strategy

Single MINOR commit. Roughly: 1 helper function, 1 new endpoint, 1 new partial, ~50 LoC of UI wiring, ~30 LoC of styling, ~30 LoC of WebSocket handlers. Total ~250 LoC + tests.

---

## Phase 4 — Item-granted adv/dis

**Status:** 🟠 Phase 4a shipped v2.252.0 (Cloak of Displacement). Phase 4b+ filed.

The Phase 2 work automated adv/dis from **conditions** (Blinded, Restrained, …) and **features** (Rage, Reckless, Vow of Enmity, …). Both read from the combatant `buffs` list (hub state) / `_buffs_active` (PC sheet mirror). **Magic items** that grant adv/dis are not yet wired into those source sets — the seeded Cloak of Displacement (`app/demo_seed.py`, on Lyra Sunstrider) carries only an *informational* `_reactions` entry the GM clicks to declare disadvantage retroactively; nothing is auto-applied.

### Why the substrate is mostly already there

The attacker side is fully built. `/attack` (`app/routes/tabletop_routes.py`) collects adv from a half-dozen sources and dis from another half-dozen, then applies PHB p.173 cancel logic and swaps the leading `1d20 → 2d20kh1` (adv) / `2d20kl1` (dis) before rolling. `/npc_attack` is symmetric. The dice engine (`app/dice.py`) keep-highest/keep-lowest is native. So a new adv/dis *source* only needs to add itself to the existing source set; no new roll plumbing.

The one genuinely new thing: existing **target-side** reads (e.g. `_target_grants_advantage_to_attackers`, `_target_has_condition_advantage`) read the **target combatant's** hub `buffs`. A Cloak of Displacement is a **passive on the wearer's character sheet** (an equipped + attuned inventory item), not a combatant buff. So Phase 4a needs to resolve *target combatant → character → sheet → `_equipped_item_effects`* at attack time and read a new item-effect flag.

### Phase 4a — Cloak of Displacement (incoming attacks have disadvantage)

**RAW (DMG p.158, rare, attunement):** "While you wear this cloak, it projects an illusion that makes you appear to be standing in a place near your actual location, causing any creature to have disadvantage on attack rolls against you. If you take damage, this property ceases to function until the start of your next turn. This property is suppressed while you are incapacitated, restrained, or otherwise unable to move." (v1 models the always-on disadvantage; the "suppressed after damage / while incapacitated" clauses are GM-narrated follow-ups — filed for Phase 4b.)

**Engine changes (one coherent commit):**

1. **`_equipped_item_effects`** — add a boolean-OR field `incoming_attacks_have_disadvantage` (out-dict default `False` + `_sources` list, walker accumulator folding any catalogued slug's `incoming_attacks_have_disadvantage` payload, attunement-gated like the other riders). Mirror the existing `magic_missile_immune` / `swim_speed` shape.
2. **`_MAGIC_ITEM_PASSIVES`** — add `"cloak-of-displacement": [{"incoming_attacks_have_disadvantage": True, "requires_attunement": True}]`.
3. **Target-side read helper** — add `_target_wearer_imposes_attack_disadvantage(campaign_id, target_combatant_id)` that resolves the target combatant to its `char_id`, loads the character sheet, runs `_equipped_item_effects(sheet)`, and returns the source name if `incoming_attacks_have_disadvantage` is truthy (else None). Reuse the combatant→character resolution the attack damage path already uses.
4. **Wire into both attack endpoints** — fold the helper's result into the **disadvantage** source set in `/attack` and `/npc_attack`, alongside the existing target-side reads. Cancel logic + label tracking come for free (`roll_state_applied: "disadvantage_cloak_of_displacement"` or the canceled-pair label).
5. **`/sheet-json derived`** — surface `derived.incoming_attacks_have_disadvantage = {sources}` when truthy (display-only mirror, matching the `magic_missile_immune` precedent).
6. **Demo seed** — Lyra's Cloak of Displacement is already seeded with `_slug: "cloak-of-displacement"` + `attunement: True`; flip it to a true attuned passive (`attuned: True` so the gate fires) and keep the informational reaction. Lyra is at 3/3 (Demon Slayer Rapier + Staff of Charming + Ring of Mind Shielding) — homing the Cloak as a 4th attuned item is fine at seed-load (the 3/3 cap is enforced only on the `/attune` runtime endpoint, as established by the Frost Brand / Garrik precedent in v2.251.0), or displace Ring of Mind Shielding if a strict 3/3 demo is preferred.

**Tests (`tests/harness/test_item_cloak_of_displacement.py`):**
- A PC attacking Lyra (Cloak attuned) rolls at disadvantage — `roll_state_applied` carries the cloak label, the attack expression resolves `2d20kl1`.
- An NPC attacking Lyra is symmetric (`/npc_attack`).
- Detuning the Cloak via `/attune` drops the disadvantage (straight `1d20`).
- Cancel logic: an attacker who ALSO has advantage (e.g. attacking a Lyra who is also Reckless-marked, or an invisible attacker) rolls straight per PHB p.173.
- `/sheet-json` exposes `derived.incoming_attacks_have_disadvantage` naming the cloak.

### Phase 4b+ — follow-ups (filed, not scheduled)

- **Suppress-after-damage / while-incapacitated** clauses for Cloak of Displacement (needs a per-turn "took damage since start of turn" flag — the legendary-resistance/damage hooks are candidate read sites).
- **Stealth-advantage items** (Cloak of Elvenkind, Boots of Elvenkind) — these grant advantage on Stealth (DEX) *ability checks*, which is the `/roll` path (Phase 2b machinery), not the attack path. A `check_advantage_on: ["stealth"]` item-effect feeding `/roll`'s adv source set.
- **Eyes of the Eagle / similar** — advantage on Perception (WIS) checks; same `/roll` substrate.
- **Elven Accuracy** (3d20kh1) — still out of scope (a feat, and needs a triple-d20 dice extension).
