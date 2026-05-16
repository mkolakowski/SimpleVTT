# Advantage & Disadvantage Tracking — Design Plan

**Status:** Phase 1 shipped in **v2.2.0**, refined in **v2.2.2** (full-sheet skill-click cross-character rollover fix) and **v2.2.3** (pill promoted from cramped HP card to a full-width row). Cross-character rollover regression caught + re-fixed at **v2.3.18** when the mini-sheet handlers moved to document-level delegation.
**Phases 2 + 3 still deferred** — see [Implementation status](#implementation-status) below for the per-phase breakdown.
**Tracked in:** [`TODO.md`](../../TODO.md) → Combat → Advantage & Disadvantage Tracking.

---

## Implementation status

(Annotation pass v2.3.26 — audited against CHANGELOG / code.)

- ✅ **Phase 1 — Manual toggle** — done in v2.2.0. `Character.sheet.roll_state`, `_apply_roll_state()` server helper with the regex contract, `POST /character/{id}/roll-state` endpoint, `_roll_state_pill.html` partial on mini-sheet + full sheet, GM token-context "Roll state" submenu (v2.3.17), roll-log `(auto …)` / `(manual …)` indicators, initiative exempt via `skip_roll_state`, damage rolls unaffected.
- 🔄 **Cross-character rollover** — initial bug where the GM's pill bled into other characters' rolls fixed in v2.2.2 (full sheet path) and again in v2.3.18 (mini-sheet handlers moved to document-level delegation; monster mini-sheets always set `skip_roll_state: true`).
- ⏸ **Phase 2 — Condition automation** — deferred. The `adv_sources` / `dis_sources` list + auto-cancel logic depends on a conditions system the project doesn't have yet.
- ⏸ **Phase 3 — Context-aware rolls** — deferred. 5-ft-melee advantage / prone disadvantage depends on Maps 2.0 grid-distance awareness, also not yet shipped.
- ❌ **Elven Accuracy / 3d20kh1** — explicitly out of scope from day one; deferred to a feats-action follow-up.
- ❌ **NPC / monster token adv/dis** — out of scope from day one. Partially addressed in v2.3.18: monster mini-sheet rolls pass `skip_roll_state: true` so the GM's own char's pill never bleeds into monster checks, but monsters themselves still don't have a settable pill.

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
