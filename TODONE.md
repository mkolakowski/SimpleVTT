# SimpleVTT — Completed To-Dos

Archive of items moved out of [`TODO.md`](TODO.md) once they shipped. The active backlog lives in `TODO.md`; this file is the historical companion so the live backlog stays scannable.

Items are grouped by the section they originally lived under in `TODO.md`. Each entry preserves its original wording and the version reference that shipped it. The changelog (`CHANGELOG.md` + `CHANGELOG_v1.md`) is still the source of truth for what each version actually contained — this file is a navigation index from "feature ask" to "ship version."

> **Why this file exists.** `TODO.md` had accumulated ~30 ✅ DONE entries by v2.151.2 (the v2.149.2 "Triage" pass), and scanning it for the next thing to work on meant skipping over a lot of already-shipped noise. Moving them here keeps the active backlog terse without losing the history.

---

## Touch Target Remediation

Apple's HIG minimum of 44×44 px was applied globally in v1.2.7 via the base `button`, `input`, and `select` CSS rules. The follow-up phases below covered the inline-styled elements that the global pass didn't reach.

### ~~Phase 1 — Campaign Settings~~ ✓ Done (v1.2.8)

`app/templates/campaign_settings.html`

| Line | Element | Current style | Fix |
|------|---------|---------------|-----|
| ~83 | `.track-actions button` (rename / save / cancel / play / delete audio track) | `padding:2px 7px; font-size:12px` | Add CSS class `.track-action-btn` with `min-height:44px` and replace inline style |
| ~624 | `select.pl-category-select` (playlist category dropdown) | `font-size:11px; padding:2px 4px` | Increase to `padding:6px 8px` or remove inline style and rely on global `select` rule |
| ~1071 | `select#enc-lib-sort` (encounter library sort) | `font-size:12px; padding:2px 6px` | Same — remove inline padding override so global rule applies |

**Approach:** Remove the inline `padding` overrides from the two selects (they will then inherit the global `min-height:44px` rule). For `.track-actions button`, add a named CSS class at the top of the template so it can be shared across all track action buttons.

### ~~Phase 2 — Tabletop JS-created buttons~~ ✓ Done (v1.2.9)

`app/templates/tabletop.html` · `app/static/tabletop.js`

Defined `.enc-action-btn` (32 px), `.enc-modal-btn` (44 px), and `.enc-spawn-btn` (32 px) CSS classes. Replaced `style.cssText` assignments on encounter action buttons, save/cancel, and spawn set/clear with `className` assignments. Removed padding overrides from encounter edit form inputs/selects, roll-request panel controls, audio-enable button, and Import & Place button.

### ~~Phase 3 — D&D 5e Character Sheet~~ ✓ Done (v1.2.10)

`app/templates/sheet_dnd5e.html`

Nearly all 24 buttons share the same inline style (`font-size:11px; padding:2px 8px`). The fix was to introduce a single shared CSS class (`.sheet-section-btn`) and replace every occurrence.

---

## Manually Added — shipped

- ✅ **DONE** — GM and player do not get popup notification that opportunity attack can be used. **Design doc: [`docs/plans/movement-oa-flow.md`](docs/plans/movement-oa-flow.md)** (added v2.99.50). All 6 phases shipped v2.99.52–v2.99.57:
    - Phase 1 ✅ v2.99.52 — Team data model + same-team filter
    - Phase 2 ✅ v2.99.53 — Token Management UI overhaul (edit button, pills, remove upload art)
    - Phase 3 ✅ v2.99.54 — "would-this-trigger-OA?" preview endpoint
    - Phase 4 ✅ v2.99.55 — Pre-move "Continue or Stop?" modal (the headline)
    - Phase 5 ✅ v2.99.56 — Per-watcher serial resolution + attack picker + skip
    - Phase 6 ✅ v2.99.57 — Multi-token-per-owner sub-queue (parallel across owners)
    - Notification flow (covered by Phase 4 + 5):
        - Pause movement and popup notification
        - User moving token gets popup asking if they want to continue movement as they will trigger an attack of opportunity
            - player chooses to stop → token stops + doesn't move out of the spot that leaving would trigger the OA + end flow
            - player chooses to move → owner of the token(s) receives a notification per token, if they have a reaction, to either roll the attack or skip
                - Attacking choice lists eligible attacks (some feats will let spells be used) and if the player chooses an attack, executes it as the OA
                    - if player survives → allow movement until next OA contest, as range allows
                - If skip chosen → allow movement until next OA contest, as range allows
    - if multiple tokens would get OAs they will need to all be resolved before the player can continue movement (Phase 5)
    - if one owner has multiple tokens that would need to make OAs, finish one flow before showing the next (Phase 6)
    - Do not prompt for OAs for tokens on the same "team" (Phase 1)
        - GM to specify using a toggle inside token management to assign "hero" or "villain" team groups vs the existing players and GM/NPC (Phase 1 + 2)
        - add edit button next to refresh and expose dropdown to change ownership and team per line item (Phase 2)
            - when not editing, show these new fields as pills before the buttons (Phase 2)
            - when not editing do not show player assignment dropdown (Phase 2)
        - remove upload art from token management (Phase 2)
- ✅ **DONE (spell slots) — v2.99.462–.464** — Bug: Un-do button does not refund spell slot
    - ✅ All spell-slot consumers now refund on Undo: the 10 dedicated `cast_*` endpoints (cast_sleep / cast_slow / cast_polymorph / cast_compulsion / cast_bestow_curse / cast_bane / cast_hold_person / cast_flesh_to_stone / cast_hold_monster / cast_web) via the new `_log_spell_slot_spend` helper (v2.99.462–.463), plus `/attack` Divine Smite + `/use_primeval_awareness` (v2.99.464).
    - **Remaining (lower-priority audit follow-up):** a coverage pass over feature/item resource consumes — the `/undo_attack_damage` machinery already handles `resource_spend` / `inventory_consume` kinds; audit which `use_*` endpoints actually log them on consume (most do, e.g. lay_on_hands / second_wind). Not a spell-slot issue.
- 🟢 **DONE (root cause) — v2.99.465** — Bug: NPCs unable to use action buttons, IE strike button on Dagger for Vex
    - Root cause: every `attack_roll: true` action in the 322 SRD monster JSONs shipped with `attack_bonus` null, so the client strike gate (`hasAttackRoll = bonus && damage`) fell through to legacy `/roll` instead of `/npc_attack` → no hit/damage. Backfilled `attack_bonus` (parsed from each action's `desc` "+N to hit") across all 536 attack actions; the stat block resolves live from `local_content`, so the fix reaches the client immediately. The attack-roll → `/npc_attack` routing was already wired (v2.49.164 / v2.94.0) — only the data was missing.
    - ✅ Save-only NPC actions (breath weapons) — fixed v2.99.466 (backfilled `save_dc` from desc) + v2.99.467 (init-tracker strike handler routes save-DC actions to `/npc_cast_spell`, which rolls the save + applies save-for-half damage). Single-target via the picker for v1.
    - ✅ AoE breath weapons (v2.99.468 — strike button passes `aoe_target_combatant_ids`); ✅ Open5e-import normalization (v2.99.469 — `app/content/monster_action_parse.py` parses combat fields from `desc`, applied in `_creature_full`).
    - **Remaining (low-priority):** the unified mini-sheet `.mini-strike-btn` NPC path could get the same save routing the init-tracker handler got (v2.99.467) if it surfaces save actions — the init-tracker path is the primary GM NPC-strike surface, so this is a nice-to-have.
- ✅ **DONE — v2.108.0–v2.110.0 (mechanisms) + v2.125.0 (parser)** — Feature: plan three ways that we can allow users to up-cast spells
    - Plan doc: [`docs/plans/spell-upcasting.md`](docs/plans/spell-upcasting.md) — audits today's surface and proposes three approaches (A: UI slot-picker; B: structured per-slot scaling data + generic resolver; C: GM-adjudicated `higher_level` text fallback).
    - All three approaches shipped: A (full sheet + mini-sheet picker, v2.108.0/.109.0), B (`damage_per_slot` / `healing_per_slot` + `_scale_dice_for_upcast` resolver, v2.110.0), C (rule text in the picker + `spell_cast` broadcast, v2.108.0).
    - v2.125.0 "Read the Footnote" added a `higher_level`-prose fallback (`app/content/spell_upcast_parse.py`) so ~285 prose-only spells auto-scale without a per-spell JSON edit.
    - Shared upcast math now lives in one module: `parse_upcast_dice` (v2.125.0), `upcast_target_count` (v2.127.0), `upcast_pool_dice` (v2.128.0).
    - **Remaining (lower-priority follow-up):** continue the spell-by-spell `damage_per_slot` / `healing_per_slot` backfill on the +dice/+heal tail the parser doesn't cover (per-two-level scaling, instance scaling, missing-base spells). Tracked inline in the plan doc's "Recommended rollout" section, not a top-priority backlog item.
- ✅ **DONE — v2.105.0–v2.107.0** — Feature: Framework that will allow then to use features like luck by clicking a button inside the roll log card they want to re-roll
    - Phase 1 ✅ v2.105.0 ("Push Your Luck") — `_REROLL_FEATURES` registry + generic `POST /use_reroll` + `reroll_options` on the `/roll` broadcast; Lucky feat (any d20, keep-better).
    - Phase 2 ✅ v2.106.0 ("One More Roll") — reroll button(s) on roll-log cards.
    - Phase 3 ✅ v2.107.0 ("Three of a Kind") — folded Fighter Indomitable (Lv 9+) + Monk Diamond Soul (Lv 14+) into the registry (save-only, keep-new).
    - ~~button to only be visible to GM and PC owner~~ ✓ (gated `ME.isGm || r.user_id === ME.id`)
    - ~~Add confirmation to confirm usage~~ ✓ (native confirm on click)
    - ~~grey out if no uses; hidden if no features available~~ ✓ (`remaining:0` → disabled/greyed; empty `reroll_options` → no button)
    - Follow-up (filed): surface the button on server-rendered roll history (only live WS rolls carry it today) + on the `/roll_request/respond` save path; a `keep-better` "decline after seeing the reroll" variant (v1 commits the use, then keeps the better).
- ✅ **LIKELY FIXED (v2.99.71) — verify in browser** — when roll log is on left, do not make disappear when gm requests roll and gm rolls for player
    - example: GM uses gm roller to push a INT Save with the DC of 20 for both demo characters, GM rolls as Pip, roll log collapses after the roll animation completes
    - **Investigation (v2.99.470):** traced end-to-end and found no remaining collapse path. When the GM rolls as Pip, `/roll_request/{id}/respond` broadcasts the `roll` with `user_id = GM` (the actor), so the client's `_focusRollLogIfLocal(GM)` calls `openPanel('roll-log-drawer', {auto: true})` → the `_auto && already-open` branch returns early (no-op). The only code that removes `.open` from a left panel is `openPanel`'s toggle-close branch, gated by `!_auto`; `roll_toast.js` does nothing to the drawer. This is exactly the class of bug v2.99.71 fixed (the pre-v2.99.71 non-`auto` `openPanel` collapsed an already-open left log on auto-focus). The reported repro predates that fix. **Action:** confirm in a live browser; reopen with a precise repro if it still collapses.
- ✅ **DONE — v2.100.0** — GM does not get movement popup when moving tokens past range
    - `preview_move` now returns `token_speed_ft` + `over_range`; the GM client shows an advisory `_showGmOverRangeModal` ("Move anyway / Cancel") when repositioning a **non-active** token further than its base walking speed in a single drag **during an active battle**. Advisory only (GM is the arbiter). The active combatant's per-turn budget is still handled by the stricter v2.99.99 overrun gate, so the two never double-prompt.
- ✅ **DONE — v2.111.0–v2.112.0** — AoE updates
    - ~~Concentration/duration AoEs place a persistent visual indicator~~ ✓ (the `_concentration_aoes` marker render — translucent dashed shape + label)
    - ~~Spirit Guardians bound to the caster's token~~ ✓ (self-anchored markers resolve the caster's current token position each frame, so the shape follows them)
    - ~~Moonbeam movable while concentration holds~~ ✓ v2.112.0 ("Walk the Beam") — `POST /move_aoe` + GM-only "↔ Move" control re-opens the picker to reposition; re-broadcasts to all clients
    - ~~Fireball-style instantaneous AoEs leave a pulse for a few seconds~~ ✓ v2.111.0 ("Flash Point") — `aoe_pulse` broadcast + a warm shape that expands + fades over ~2.2 s
    - Follow-ups (filed): Spirit Guardians "don't target same-team" is a targeting-exclusion concern (separate from the visual); RAW once-per-turn + 60-ft-range gate on the Moonbeam move (v1 is GM-adjudicated); a player-facing (non-GM) Move trigger (the `/move_aoe` endpoint already permits the caster).
- ✅ **DONE — v2.102.0–v2.104.0** — Add feature to lock player and NPC movement
    - Phase 1 ✅ v2.102.0 ("Hold Still") — server core: `Campaign.movement_locked` (live) + `movement_lock_default` (House Rules setting, seeds the live flag on each encounter load); `POST /movement_lock` GM toggle broadcasting `movement_lock_update`; `/token/move` gate (non-GM → 409 `movement_locked`, GM passes); one-shot `_movement_grants` store.
    - Phase 2 ✅ v2.103.0 ("The Velvet Rope") — GM-only 🔒/🔓 toggle button in the canvas-tools cluster; `_commitTokenMove` lock gate (player snap-back + "movement is locked" notice / GM advisory "move anyway?" confirm).
    - Phase 3 ✅ v2.104.0 ("Mother May I") — player "🙋 Request to move" → `POST /movement_request` → GM approve/deny popup → `POST /movement_request/{id}/respond` issues a one-shot grant + broadcasts `movement_request_resolved` so the player gets a single move while the table stays locked.
    - ~~add toggle in encounter~~ ✓ (the live GM toggle on the tabletop, defaulted per encounter load from the campaign setting)
    - ~~add option in campaign settings to make the toggle default on or off~~ ✓ (`movement_lock_default` House Rules checkbox)
    - ~~player and GM get popup notifying that movement is locked~~ ✓ (player notice + GM advisory confirm)
    - ~~Player can request from GM to allow movement; GM can approve or deny~~ ✓ (Phase 3)
- ✅ **DONE — v2.91.0** — Move the Title of the campaign, to the center of the window and please place it in a "pill" that has the "glass effects" (the `.tt-title-pill` centered glass pill in the topbar).
- ✅ **DONE — v2.91.0** — Remove badge system tt-topbar-badge and "muted tt-topbar-gm" from the tt-topbar (both removed in the v2.91.0 topbar rework; no longer present in the template).
- ✅ **DONE — v2.97.10** — Update the Dice roller to have the same glass effects (the Dice Roller card now uses the shared glass recipe: `color-mix` translucent `--bg` + `backdrop-filter: blur(16px) saturate(160%)`).

---

## Combat — shipped

### ~~Targeting Button on the Attack Flow~~ ✓ Done (v2.49.85 → v2.49.87)

Shipped in three commits: v2.49.85 (server) added `target_combatant_ids` list support on `/attack` with per-target fresh attack + damage rolls and a new `auto_attack_targets` response/broadcast array. v2.49.86 (client wiring) extended `_targetBodyFields` on the sheet to emit the list when the canvas has 2+ targets currently selected. v2.49.87 (mobile picker) added multi-select via checkbox rows + a Confirm button to `_promptTargetPicker`, opt-out via `{allowMulti: false}` — the same modal handles desktop multi-target without canvas-double-clicks. Filed follow-ups: chat-card multi-target rendering, per-target uplift detection (Hex / Hunter's Mark / Colossus Slayer), per-target range check.

---

## Full Class-Feature Automation — archetype bullets shipped

The parent plan ([`docs/plans/full-feature-automation.md`](docs/plans/full-feature-automation.md)) is still IN PROGRESS — Phase 8 (higher-level subclass features Lv 6/10/14/17/20) and a few Phase-1.5 / Phase-2 follow-ups on individual features remain. The bullets below are the archetypes that closed out across the v2.118.0–v2.149.1 push.

- ✅ **DONE — Phase 7: reactions breadth (v2.118.0–v2.122.0).** Protective Field, Riposte, Chronal Shift, Restore Balance. Filed follow-ups: NPC-damaged-ally Protective Field walker; intercepting one-off manual `2d20kh1` for Restore Balance; proactive prompt for Restore Balance; auto-application of Chronal Shift / Silvery Barbs rerolls.
- ✅ **DONE — Auras backlog (E) all four shipped this session:**
    - `aura_of_warding` ✅ v2.133.0–v2.135.1 — full RAW chain (`is_spell` plumbing + `resistance_spell_damage` buff + `_tick_auras` aura-installs-buff payload).
    - `ancestral_protectors` ✅ v2.136.0–v2.138.0 — install + disadvantage gate + damage halving (3-pass RAW chain).
    - `unwavering_mark` ✅ v2.139.0–v2.141.0 — install + 5-ft disadvantage + bonus-action punish endpoint (full RAW chain).
    - `scornful_rebuke` ✅ v2.142.0 — first on-damage-taken hook in the codebase.
- ✅ **DONE — On-hit / attack-roll backlog (B):** `assassinate` ✅ v2.131.0–v2.132.0 (auto-crit + advantage halves, full RAW chain).
- ✅ **DONE — Buff / temp-HP tail (D/F) all six shipped:**
    - `supreme_healing` ✅ v2.143.0 — heal-pipeline max-dice substitution.
    - `combat_inspiration` ✅ v2.144.0–v2.145.0 — damage half + AC half.
    - `blade_flourish` ✅ v2.146.0 — shared damage half (per-flourish riders deferred to Phase 2).
    - `rallying_cry` ✅ v2.99.454, `grim_harvest` ✅ v2.99.457, `protective_spirit` ✅ v2.99.458.
- ✅ **DONE — Movement tail (G) all four shipped:**
    - `stormborn` ✅ v2.99.459 (fly buff).
    - `ascendant_step` ✅ v2.147.0 (levitate buff with vertical fly_speed).
    - `fancy_footwork` ✅ v2.148.0 (OA-block mark install; Phase 2 OA-flow read deferred).
    - `relentless_avenger` ✅ v2.149.0 (free-move budget + OA-immune flag; Phase 2 `/token/move` read deferred).

---

## Design Plans Backlog — shipped end-to-end

Plans whose phases closed out completely. Each entry preserves the per-phase ship references so the trail back to the changelog is intact. The active backlog (P1/P2/P3) lives in [`TODO.md`](TODO.md).

- [`auras.md`](docs/plans/auras.md) — Phase 5 ✅ v2.99.424–.429.
- [`death-saves.md`](docs/plans/death-saves.md) — Phase 1 ✅ v2.1.0; Phase 3a ✅ v2.150.0; Phase 3b ✅ v2.151.0. (Phase 3c needs a session-time concept the project doesn't have; Phase 4 NPC death-saves deferred.)
- [`demo-mode.md`](docs/plans/demo-mode.md) — ✅ v2.3.0.
- [`feature-saves.md`](docs/plans/feature-saves.md) — Phase 3 ✅ v2.99.405–.414.
- [`movement-and-summons.md`](docs/plans/movement-and-summons.md) — Phase 6 ✅ v2.99.431–.446.
- [`movement-oa-flow.md`](docs/plans/movement-oa-flow.md) — ✅ all 6 phases v2.99.52–.57.
- [`on-hit-riders.md`](docs/plans/on-hit-riders.md) — Phase 2 ✅ v2.99.395–.403.
- [`ruler-and-range.md`](docs/plans/ruler-and-range.md) — ✅ all phases (1, 2, 3A–E).
- [`spell-upcasting.md`](docs/plans/spell-upcasting.md) — ✅ A+B+C v2.108.0–v2.110.0; prose parser v2.125.0; per-two-slot v2.129.0; flat-bonus v2.130.0.
- [`temp-hp-and-bonuses.md`](docs/plans/temp-hp-and-bonuses.md) — Phase 4 ✅ v2.99.415–.423.
- [`test-harness.md`](docs/plans/test-harness.md) — ✅ Phases 1–5 (2045 tests).
- [`wild-magic.md`](docs/plans/wild-magic.md) — ✅ all 5 phases v2.99.227–231.
