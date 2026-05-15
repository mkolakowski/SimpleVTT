# Death Saving Throws — Design Plan

**Status:** Planned. Not yet implemented.
**Target version:** v2.x.0 — next available MINOR (sequencing TBD against other planned MINOR features).
**Tracked in:** [`TODO.md`](../../TODO.md) → Combat → Death Saving Throws.

---

## Goal

When a character drops to 0 HP, they enter the 5e "dying" state and start rolling death saving throws. The system tracks successes/failures, auto-resolves to *stable* on 3 successes or *dead* on 3 failures, applies damage-while-dying penalties per RAW, and reactivates cleanly when the character is healed. Visible to player and GM in the mini-sheet, full sheet, and (Phase 3) initiative tracker.

---

## Architectural decisions

### 1. State lives on `Character.sheet.death_saves`

Add a nested field to the character sheet JSON:

```json
"death_saves": {
  "status": "alive" | "dying" | "stable" | "dead",
  "successes": 0,
  "failures": 0
}
```

**Why:** matches the `roll_state` pattern from the adv/dis plan — no schema migration, broadcasts via the existing character-update WebSocket. Death save state is per-character, never per-token (the same character appearing on two maps shouldn't have divergent death save counts).

**Tradeoff:** NPC tokens have no character row, so Phase 1 doesn't track death saves for them. Most monsters drop dead at 0 HP per RAW anyway. Phase 4 covers the "boss NPCs should roll saves too" case.

### 2. Server-driven state transitions, not client-driven

Every endpoint that mutates `hp_current` (`/apply_healing`, `/apply_damage`, weapon attack damage application, manual HP edit on the sheet) routes through a single helper `_apply_hp_change(char, new_hp, *, is_crit=False, damage_amount=0)`. The helper handles the death-save state machine atomically:

- `alive` → `hp = 0` → `dying`, reset saves to `{0, 0}`
- `dying` → `hp > 0` (healing) → `alive`, clear saves
- `dying` → damage applied → `failures += 1` (or `+2` on crit; per RAW)
- `dying` → damage ≥ max_hp at 0 HP → `dead` (massive damage rule, applied in Phase 1)
- `stable` → `hp > 0` (healing) → `alive`, clear saves
- `stable` → damage → back to `dying` with the appropriate failure tick

**Why:** server-side state machine means stale clients can't desync the dying state, and the behavior is identical across all damage sources (weapon attacks, action-button damage, GM HP edits). Single source of truth.

### 3. Any HP > 0 clears non-alive states (incl. dead)

Any positive HP change sets `status = alive` and zeros out the save counters, regardless of prior status. **v2.1.1 update:** this now includes `dead` — the original "dead stays dead, GM override required" rule proved confusing in practice (the user healing a character is usually the GM, so requiring a second action to clear the dead flag was unhelpful). If a table wants strict revivify-spell semantics, they keep the character at 0 HP and use the override to set them `alive` at 1 HP rather than healing them through it.

### 4. Death save rolls go through the existing `/roll` endpoint

A new endpoint `POST /api/campaign/{id}/character/{char_id}/death-save` posts a `1d20` through the existing roll pipeline (so it respects the adv/dis plan's `roll_state` interception, hits the roll log like any other roll, and broadcasts over WebSocket). Then it applies the result to the death save state:

- 10+ → `successes += 1`
- <10 → `failures += 1`
- Nat 20 → `hp = 1`, status → `alive`, clear saves (regain consciousness)
- Nat 1 → `failures += 2`
- After update: if `successes >= 3` → status → `stable`, reset counters; if `failures >= 3` → status → `dead`

**Why:** rolls already have a working pipeline (visibility, breakdown, roll log, WebSocket fanout, auto-applied roll_state from adv/dis). Death saves are one more d20 with special interpretation of the result.

### 5. Massive damage instant-kill is in Phase 1

5e RAW: damage at 0 HP that exceeds the character's max HP = instant death (skip remaining death saves). Implemented in Phase 1 so the system is RAW-correct from day one. Adds a single conditional in `_apply_hp_change`.

### 6. GM-only stabilize button

The full character sheet exposes a "Stabilize" button that sets status to `stable` and clears save counters. **GM-only** — stabilize is something done *to* you, not by you. Player-side features that grant self-stabilize (Withers' Hold, certain class abilities) are out of scope for Phase 1 and would be wired in alongside the conditions/feats systems.

### 7. UI surfaces

**Three touchpoints** (Phase 1):

1. **Mini-sheet tracker** — three green dots (successes) and three red dots (failures), filled as they accumulate. Prominent "Roll Death Save" button when status is `dying`. Status badge in the appropriate color ("ALIVE" / "DYING" / "STABLE" / "DEAD").
2. **Full character sheet header** — same tracker, expanded with the GM-only "Stabilize" button.
3. **GM token context menu** — "Set status: alive / dying / stable / dead" override, in case the GM needs to fix a misclick or apply a story beat.

**v2.1.1 update:** the tracker is now **permanently visible** on both the full and mini sheet, regardless of status. The earlier "hide when alive" behavior made it unclear whether the feature was even present until a character actually started dying. Always-on visibility lets players see "I am ALIVE with 0 successes / 0 failures" as a baseline.

**Color coding** matches the rest of the app's danger/success palette: red status fields when dying or dead, amber when stable, normal otherwise. Dying tracker gets a subtle pulse animation to draw the player's eye.

---

## Phase scope

### Phase 1 — Manual rolls + auto state on HP changes (ships now)

- HP hits 0 → auto-transition to `dying`, save counters initialized
- "Roll Death Save" button rolls `1d20`, applies result per RAW
- 3 successes → stable; 3 failures → dead
- Any healing → clear dying/stable state, back to `alive`
- **Damage at 0 HP automatic failure** (Phase 1, RAW from day one): any damage source applied to a `dying` character ticks `failures += 1` (or `+2` if crit)
- **Massive damage instant-kill** (Phase 1, RAW from day one): damage ≥ max_hp at 0 HP → instant `dead`
- GM override via token context menu
- GM-only "Stabilize" button on the full sheet
- Nat 20 and nat 1 special cases handled

### Phase 2 — (reserved)

Phase 2 was originally "damage at 0 = auto failures" but that's been pulled into Phase 1. Reserved slot for whatever else turns out to matter (e.g., richer status broadcast for the initiative tracker, exhaustion-on-revive variant rule support).

### Phase 3 — Initiative & stabilize automation (later, after combat improvements)

- Initiative tracker auto-prompts the dying character's player on their turn ("Your character is dying. Roll a death save.")
- Medicine check button auto-resolves stabilize for an adjacent ally (Medicine DC 10 = success → status `stable`)
- Track stable-countdown (RAW: 1d4 hours until 1 HP) — gated on a session-time concept the project doesn't yet have

### Phase 4 — NPC death saves (much later, optional GM toggle)

- Per-token "use death saves" flag the GM enables on bosses or major NPCs
- Stores death save state on the Token row instead of the Character.sheet
- All other behavior identical

---

## Files to add (Phase 1)

- **`app/templates/_death_saves_tracker.html`** — reusable Jinja partial. Three success dots, three failure dots, status badge, conditional "Roll Death Save" button, conditional GM-only "Stabilize" button.

---

## Files to modify (Phase 1)

### `app/routes/tabletop_routes.py`
- New helper `_apply_hp_change(char, new_hp, *, is_crit=False, damage_amount=0) -> dict` — single source of truth for HP transitions + death save state machine. Returns a dict the caller can echo back to the client (e.g. `{new_hp, status_changed, status, successes, failures}`).
- All current HP-mutation paths (`/apply_healing`, `/apply_damage`, weapon attack damage commit, manual HP edit on the sheet) refactored to call the helper.
- New endpoint `POST /api/campaign/{id}/character/{char_id}/death-save` — rolls a 1d20 via the existing roll pipeline (respects `roll_state` from the adv/dis plan), applies the result, broadcasts a `character_death_save` WebSocket message.
- New endpoint `POST /api/campaign/{id}/character/{char_id}/death-save/override` — GM-only manual override (used by the token context menu). Accepts `{status, successes, failures}`.
- New endpoint `POST /api/campaign/{id}/character/{char_id}/stabilize` — GM-only. Sets status to `stable`, clears counters.

### `app/static/sheet.js` / `app/static/sheet_dnd5e.html`
- Render the tracker partial in the sheet header. Click handler on "Roll Death Save" posts to the new endpoint.
- Roll-log renderer recognizes death-save rolls (carry a `kind: "death_save"` field) and shows the result with the special interpretation: `"Death save: 18 → SUCCESS (2/3)"` / `"Death save: 1 → CRIT FAIL (2 failures)"` / `"Death save: 20 → REGAIN CONSCIOUSNESS"`.
- "Stabilize" button only renders for users with GM role on this campaign.

### `app/static/tabletop.js`
- Mini-sheet renders the tracker.
- WebSocket handler for `character_death_save` updates open mini-sheets and refreshes the initiative tracker entry.
- Token context menu (GM) gets a "Death save status" submenu (alive / dying / stable / dead).

### `app/static/style.css`
- `.death-save-tracker` family — pip styling, status badge colors, dying-state highlight pulse.

### `app/version.py` + `CHANGELOG.md`
MINOR bump (additive, no schema change).

---

## Verification (Phase 1)

1. **HP drops to 0 → dying** — apply damage that brings Alice from 12 HP to 0. Mini-sheet pill flips to "DYING" with `(0/3, 0/3)`. WebSocket broadcasts; GM's view updates.
2. **Successful death save** — click "Roll Death Save", roll a 14. Successes → 1/3. Log: `"Death save: 14 → SUCCESS (1/3)"`.
3. **Failed death save** — manipulate the roll to a 7. Failures → 1/3.
4. **Nat 20 wakes up** — roll a 20. HP → 1, status → `alive`, saves cleared. Log notes the regain.
5. **Nat 1 double failure** — roll a 1. Failures → 2/3 in one click.
6. **Three successes → stable** — accumulate to 3 successes. Status → `stable`. Counters reset to 0.
7. **Three failures → dead** — accumulate to 3 failures. Status → `dead`. "Roll Death Save" button no longer shown.
8. **Healing clears state** — apply 5 HP healing to a dying character. Status → `alive`, saves cleared, HP = 5.
9. **Damage at 0 = auto failure** — Alice is dying with `(1/3, 1/3)`. Apply 4 HP damage from a weapon attack. Failures → 2/3 automatically (no save roll). Log notes the auto failure.
9a. **Crit damage at 0 = double failure** — Alice is dying with `(0/3, 0/3)`. Apply a critical hit. Failures → 2/3 in one event.
9b. **Massive damage at 0 = instant dead** — Alice (max HP 12) is dying. Apply 15 damage. Status → `dead` immediately, regardless of save count.
10. **Adv/dis interaction** — set `roll_state=advantage` on Alice while dying. Roll a death save. Server rolls `2d20kh1`, applies highest as the death save result. Log notes `(auto advantage)`.
11. **GM override** — as GM, right-click Alice's token → "Set status: dead". Alice immediately shows `dead`; no rolls possible.
12. **GM Stabilize button** — Alice is dying with `(1/3, 2/3)`. GM clicks Stabilize on her sheet. Status → `stable`, counters → `(0, 0)`. Button is not rendered when the same user views the page as a non-GM.
13. **Permission guard — roll** — Bob tries to roll Alice's death save via the API. Server returns 403.
14. **Permission guard — override** — Bob tries to call the override endpoint as a non-GM. Server returns 403.

---

## Out of scope (Phase 1)

- **Auto-prompt on initiative turn** — Phase 3.
- **Medicine check auto-stabilize** — Phase 3 (Phase 1's "Stabilize" button is a manual GM action).
- **Stable countdown** (RAW: 1d4 hours → regain 1 HP) — Phase 3, gated on session-time concept.
- **NPC death saves** — Phase 4.
- **Revivify / resurrection spells** — out of scope. Healing a `dead` character requires the GM override.
- **Self-stabilize features** (Withers' Hold, certain class abilities) — gated on conditions / feats systems.
- **Long-rest reset of death save counters** — not needed; counters reset on stable/heal/dead transitions, so a long rest in `alive` state has nothing to reset.

---

## Commit strategy

Single MINOR commit. Roughly: 1 helper + state machine, 3 new endpoints, 1 partial, ~80 LoC of UI wiring, ~40 LoC of styling, ~30 LoC of WebSocket handlers. Total ~300 LoC + tests.

The plan touches every HP-mutating endpoint; the refactor to route them through `_apply_hp_change` is the riskiest part. Suggest a careful pre-implementation grep for direct `hp_current = X` assignments so none get missed.
