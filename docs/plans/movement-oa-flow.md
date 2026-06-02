# Movement-OA Flow — pre-move confirmation, per-watcher resolution, team filter, token-management UI

A design plan for the user-requested overhaul of the Opportunity Attack experience. The current OA pipeline (v2.66.0 + v2.67.0) is **reactive**: the move is committed first, then watcher owners are pinged. The to-do is **preemptive + serialized**: pause the move, ask the mover whether to continue, then resolve every triggered OA in sequence before the move actually commits. Adds a team data model so same-team OAs don't fire, plus a Token Management UI refresh that surfaces the new fields.

This plan does NOT supersede `plan-reactions-automation`. That doc owns the generic reaction-prompt machinery (Shield, Counterspell, Uncanny Dodge, etc.); this doc owns the OA-specific movement flow built on top.

## Status snapshot

| Phase | Subject | Status | Lands in |
|-------|---------|--------|----------|
| 1 | Team data model + same-team filter | ✅ shipped | v2.99.52 |
| 2 | Token Management UI overhaul | ✅ shipped | v2.99.53 |
| 3 | "Would-this-trigger-OA?" preview endpoint | ✅ shipped | v2.99.54 |
| 4 | Pre-move "Continue or Stop?" modal | ✅ shipped | v2.99.55 |
| 5 | Per-watcher serial OA resolution + attack picker | ⚪ proposed | v2.99.5x |
| 6 | Multi-token-per-owner sequencing | ⚪ proposed | v2.99.5x |

The current ship contract (v2.99.49) — reactive popup with amber pulse + diagnostics — stays unchanged through Phase 1-3. Phase 4 onwards shifts the popup contract; v2.99.49's UX work flows through.

## End-state user flow (after all 6 phases)

1. **Player drags a token.** The client computes the proposed destination but does NOT commit the move yet.
2. **Client asks the server "would this trigger any OAs?"** via the new preview endpoint (Phase 3). Server walks the same `_check_opportunity_attack_triggers` logic with the new same-team filter (Phase 1).
3. **No OAs ⇒ proceed normally.** Existing `/token/move` flow ships the move.
4. **One or more OAs ⇒ pre-move modal opens** (Phase 4) showing the mover: "Continuing past this point will provoke OAs from: Tavik (5 ft reach), Krieger (5 ft reach)." with Continue / Stop buttons.
   - **Stop ⇒ token snaps back to origin.** End flow.
   - **Continue ⇒ server enters serial OA resolution.** Each watcher's owner gets a per-token prompt in order (Phase 5). The mover's token is *visually paused* at the just-out-of-reach point (the cell where the OA was triggered) until all watchers resolve.
5. **For each triggered watcher, in iteration order** (Phase 5):
   - The watcher's owner gets a popup with an **attack picker** — lists eligible melee attacks from the sheet, plus War Caster spell options if the feat is present. "Skip" is always available.
   - Click an attack ⇒ server executes the attack as the reaction (reusing `/use_attack` infrastructure); reaction slot flips True; chat-card surfaces the result.
   - Skip ⇒ reaction slot stays free; prompt closes.
   - If multiple OAs are queued AND one owner controls multiple watchers, they're surfaced one-at-a-time (Phase 6); the owner exhausts their queue before the next owner's prompts open.
6. **All OAs resolved ⇒ commit the move OR snap back.** If the mover survives (HP > 0 + not Unconscious / Paralyzed / etc.), the token continues to the destination. If the mover dropped to 0 HP / Unconscious from an OA, the token stays at the just-out-of-reach point and the death-save state machine fires.

## Phase 1 — Team data model + same-team filter

**Intent.** Add a `team` field (`"hero" | "villain" | "neutral"`) on tokens + init-tracker combatants so `_check_opportunity_attack_triggers` can skip same-team matches. RAW says OA fires from a "hostile creature"; today the helper has no faction concept and would fire OA from a paladin watching a wizard ally move out of reach.

**Default value** is `"neutral"` so existing campaigns don't get behavior changes until the GM opts into team tagging. Same-team filter only fires when BOTH the mover AND the watcher have a non-`"neutral"` team and they match.

**File touches**

| File | Change |
|------|--------|
| `app/models.py` | Add `team: Mapped[str]` column on `Token` (`String(16), default="neutral", server_default="neutral"`). |
| `app/database.py` | Add `_apply_inline_migrations()` block to ALTER TABLE on existing campaigns. `SCHEMA_VERSION` +1. |
| `app/version.py` | `SCHEMA_VERSION` increment. |
| `app/routes/tabletop_routes.py` | `_check_opportunity_attack_triggers` reads watcher's team from the combatant dict (mirrored from `Token.team`) + mover's team. Skip when both non-neutral and equal. Plumb `team` into the `_lookup_combatant` synthesizer + the `/api/campaign/{cid}/tokens` JSON projection. |
| `app/routes/tabletop_routes.py` | `PATCH /api/campaign/{cid}/token/{tid}` — accept `team` in body. (Already exists as the generic token PATCH endpoint per `patch_token` — just whitelist the field.) |
| `tests/harness/test_opportunity_attack.py` | New tests: (a) same-team filter skips OA, (b) opposite-team OA still fires, (c) neutral-vs-anything still fires (back-compat). |

**Acceptance criteria**

- A token defaults to `team="neutral"` on creation.
- `PATCH /token/{tid}` with `{team: "hero"}` persists + broadcasts `token_update`.
- `_check_opportunity_attack_triggers` skips watchers when both mover and watcher are `"hero"` (or both `"villain"`).
- `_check_opportunity_attack_triggers` still fires when one side is `"neutral"` (backwards-compatible with pre-Phase-1 campaigns).
- All existing OA tests still pass (they use the default `"neutral"` so the filter is a no-op).

## Phase 2 — Token Management UI overhaul

**Intent.** Surface the new `team` field + a cleaner ownership-change UX in the Token Management panel (`app/templates/tabletop.html` line 3864; `renderTokenTracker` in `app/static/tabletop.js` line 6310). Adds an Edit toggle next to Refresh: non-edit mode shows ownership + team as **pills** before the action buttons; edit mode swaps the pills for dropdowns. Removes the "🖼 Upload art" row button per the to-do — uploads can still happen via the character sheet or template editor, just not from the per-token row.

**File touches**

| File | Change |
|------|--------|
| `app/templates/tabletop.html` | Add Edit toggle button next to Refresh / Add Token (line 3871). |
| `app/static/tabletop.js` | `renderTokenTracker` (line 6310): track edit mode in a panel-local `_tmEditMode` flag. Non-edit: render `<span class="tm-pill">${owner}</span> <span class="tm-pill">${team}</span>` before action buttons. Edit: render `<select class="tt-ctrl">` (owner) + `<select class="tt-team">` (team — hero / villain / neutral). Remove the `<label class="tt-btn tt-art-label">` block (line 6377-6379). |
| `app/static/style.css` | Add `.tm-pill` styling (small rounded badge, color-coded by team — amber for hero, slate for villain, muted for neutral). |
| `tests/harness/test_token_management.py` | New file. Smoke test that PATCH-ing `team` persists; full UI render coverage is filed for the harness_ui suite. |

**Acceptance criteria**

- Token Management panel renders with an `Edit` button next to Refresh.
- Non-edit mode shows two pills per row: ownership ("👤 Alice" or "⚙ GM") + team ("🦸 Hero" / "👹 Villain" / muted "—").
- Edit mode swaps each pill for a select dropdown; selecting a new value PATCHes the token + the pill / next-render reflects the change.
- No "🖼 Upload art" file-input visible on any row.
- Existing `tt-vis` / `tt-target` / sheet-link / `tt-del` buttons all still work.
- `clean_pcs` fixture-based tests don't regress (token state is per-test, the field defaults to neutral).

## Phase 3 — "Would-this-trigger-OA?" preview endpoint

**Intent.** A pure read endpoint the client can call BEFORE committing a token move. Returns the same trigger list the actual `/token/move` would produce, without mutating the token. Lets Phase 4's modal know which OAs would fire so it can list them in the confirmation prompt.

**File touches**

| File | Change |
|------|--------|
| `app/routes/tabletop_routes.py` | New endpoint `POST /api/campaign/{cid}/token/{tid}/preview_move`. Body `{x, y}`. Validates same gates as `/token/move` (campaign membership, token ownership). Calls `_check_opportunity_attack_triggers(db, cid, tid, from_x, from_y, x, y)`. Returns `{would_trigger_oa: bool, triggers: [...]}` with the same trigger shape `/token/move` already returns. NO commit, NO broadcast. |
| `tests/harness/test_opportunity_attack.py` | New tests: (a) preview returns same triggers as a `/token/move` call would (run preview, then move, compare lists), (b) preview leaves token position unchanged. |

**Acceptance criteria**

- `POST /token/{tid}/preview_move` returns 200 + the trigger list.
- Token's `x`/`y` are unchanged after the call (verified via `GET /tokens`).
- Triggers list matches what a real `/token/move` would emit (same watcher_combatant_ids, same trigger_types).
- Phase 1 same-team filter applies here too (the preview uses the same helper).

## Phase 4 — Pre-move "Continue or Stop?" modal

**Intent.** Wire the client to use the preview endpoint before committing a move. When `would_trigger_oa: true`, open a modal listing the watchers and ask the mover whether to continue or stop.

**File touches**

| File | Change |
|------|--------|
| `app/static/tabletop.js` | `_commitTokenMove` (line 3397): instead of immediately POSTing `/token/move`, POST `/token/{tid}/preview_move` first. If response carries `would_trigger_oa: false`, fall through to the existing `/token/move` path. Otherwise open the new modal (see below). |
| `app/static/tabletop.js` | New helper `_showPreMoveOaModal(token, x, y, triggers, postMove, snapBack)`. Builds a modal listing each trigger with watcher name + reach. Continue button → `postMove()` (which calls `/token/move` with `{x, y, oa_confirmed: true}`). Stop button → `snapBack()`. |
| `app/routes/tabletop_routes.py` | `/token/move` accepts new `oa_confirmed: bool` body field. When True AND triggers fire, behavior is unchanged from today (move commits, reaction_prompts fire). When False AND triggers would fire, return 409 `oa_confirmation_required` with the triggers list (defense-in-depth in case a client races past the preview check). |
| `tests/harness/test_opportunity_attack.py` | New test: `/token/move` without `oa_confirmed` AND with triggers → 409 + position unchanged. |

**Acceptance criteria**

- Dragging a token that wouldn't trigger an OA still moves cleanly (preview returns false → direct commit).
- Dragging a token that would trigger an OA opens a modal listing the watchers' names + reaches with Continue / Stop buttons.
- Stop button: token snaps back; no `/token/move` call; no OA prompts fire.
- Continue button: `/token/move` posts with `oa_confirmed: true`; OA prompts fire to watchers' owners as today.
- Server returns 409 `oa_confirmation_required` if a malicious client tries to `/token/move` without `oa_confirmed` on a trigger-eligible move.

## Phase 5 — Per-watcher serial OA resolution + attack picker

**Intent.** Today every triggered watcher gets a popup in parallel and the popup only has a single "⚔ Take the Opportunity Attack" button (a verbal cue — the player still clicks Attack on their sheet to actually swing). Phase 5 (a) emits prompts one-at-a-time per the trigger list's iteration order, (b) extends the popup to a real attack picker that lists the watcher's eligible melee attacks + War Caster spell options, and (c) hooks the picker click into `/use_attack` so the OA actually resolves through the reaction prompt.

**File touches**

| File | Change |
|------|--------|
| `app/routes/tabletop_routes.py` | New `_oa_queue` per-campaign in `_active_reaction_prompts`'s siblings dict. When `/token/move` fires triggers, instead of emitting all `reaction_prompt`s at once, push them onto the queue + emit only the head. `_use_reaction` (and a new `skip_reaction` sibling) advances the queue: when the head resolves, emit the next. The mover's token visually pauses at the trigger point until the queue drains. |
| `app/routes/tabletop_routes.py` | `_eligible_reactions[creature_exits_reach]`: extend the option list to include one entry per melee weapon on the watcher's sheet (key=`take-the-oa:{attack_index}`, label=`"⚔ {attack_name}"`). War Caster cast-instead-of-OA already exists from v2.76.0 Phase 4c. |
| `app/routes/tabletop_routes.py` | `/use_reaction` handler for `take-the-oa:{idx}`: execute the attack via existing `/use_attack` infrastructure with the provoking mover as the target. Reaction slot flips True, attack resolves, damage applies. |
| `app/static/reaction_prompt.js` | Render multi-button option lists in priority order. Existing logic already supports `options[].label` / `options[].key`; just needs styling tweaks for longer lists. |
| `tests/harness/test_reaction_prompt.py` | New tests: (a) serial queue: 2 watchers, only 1 popup fires until first resolves, (b) attack picker: `take-the-oa:0` option key resolves through `/use_attack`, attacker rolls, target HP drops, (c) skip path: `skip-oa` option closes prompt without consuming reaction. |

**Acceptance criteria**

- Two watchers in reach, both triggered → only one prompt visible at a time; second prompt opens after the first resolves (either via attack or skip).
- The prompt's options include `⚔ {attack_name}` for each of the watcher's melee weapons (Greatsword, Handaxe, etc.).
- Click an attack option → `/use_attack` fires, swing resolves, chat-card shows hit/miss/damage.
- Click `Skip` → prompt closes, reaction slot stays unused.
- War Caster's `take-war-caster-cast` option still appears alongside (v2.76.0 wire intact).
- Mover's token position: stays at the just-out-of-reach point until the queue drains; if all OAs miss or skip, advances to the requested destination; if mover hits 0 HP, stays put + death-save fires.

## Phase 6 — Multi-token-per-owner sequencing

**Intent.** When the queue from Phase 5 contains multiple prompts for the same owner (one player controls Tavik AND Caelan, both watching), Phase 5's per-watcher queue would emit all of that owner's prompts at once. Phase 6 adds a per-owner sub-queue: emit one at a time per owner, in original queue order.

**File touches**

| File | Change |
|------|--------|
| `app/routes/tabletop_routes.py` | Group queue entries by `target_user_ids[0]` (the watcher's owner). Emit one entry per owner concurrently; subsequent entries for the same owner wait until that owner resolves their current prompt. |
| `tests/harness/test_reaction_prompt.py` | New test: one player owns 2 watchers, both triggered → exactly one prompt visible per the player's WS buffer at any time; second prompt opens after the first resolves. |

**Acceptance criteria**

- Player owns 2 watchers, both eligible OAs → first popup appears, second appears only after the first resolves.
- Two different players each own 1 watcher → both popups fire in parallel (no inter-player serialization).

## Open questions

- **Mover identification.** Phase 4 needs to know who the mover IS for the modal to render. `_user_can_move_token` already gates this; the mover is the authenticated user. But for the team filter (Phase 1), the mover's TEAM matters — and a mover can be the GM dragging an NPC token. Decision: GM-dragged NPC token uses the token's own team field (the team the GM has assigned to that NPC). PC-dragged token uses the token's team field too. The user identity matters only for routing the modal back to the mover, not for the filter.
- **OA-during-AoE.** `/place_aoe` doesn't trigger OAs today (no movement involved). Should it? Decision: no — AoE placement is a targeting picker, not a creature move. RAW: OA is for movement, not for "the spell hits a creature you didn't realize was nearby."
- **GM-as-mover popup routing.** When the GM drags an NPC, who sees the pre-move modal? The GM (the mover). The WATCHER's owner still gets the OA prompt. Two different popups, two different users.
- **Death-during-OA.** If the mover takes lethal damage from an OA, the mover's token stops at the just-out-of-reach point. Should the death-save state machine fire? Decision: yes, reuse the existing `_apply_hp_change` death-save plumbing.
- **Reaction reroute through `/use_attack`.** Phase 5 has the reaction handler call into the attack endpoint. The attack endpoint normally consumes the watcher's action slot — for an OA the reaction slot is the cost, not action. Decision: add an `is_reaction: True` flag to `/use_attack` that skips the action-slot consumption and the bonus-action gate.
- **Movement budget accounting.** When the mover stops at the just-out-of-reach point, does their `economy.movement` decrement by the partial distance? Decision: yes — the existing `/token/move` already does the math from `from_x,from_y → x,y`. Phase 4 just needs to pass the just-out-of-reach point as the actual move destination on Stop (not the original request).
- **AoE OA via teleport / Misty Step.** RAW: forced movement and teleportation do NOT provoke OA. The current `_check_opportunity_attack_triggers` doesn't know the difference between a walk and a teleport. Decision: filed for Phase 7. Add a `move_kind: "walk" | "teleport" | "forced"` field to the move payload and skip OA when not "walk".

## Decisions baked into the plan

- The pre-move modal is mover-side. The watcher-side popup (existing v2.67.0 + v2.99.49) stays per-watcher.
- Same-team filter is server-side; client doesn't need to know. The preview endpoint just won't return same-team triggers.
- The attack picker reuses sheet attack definitions; no new attack schema work.
- Phase 1's `team` field is on the Token, not on the Character. Reason: NPCs don't have Character rows, but they have Tokens. The same field works for both, and the GM toggles it per-token in the new UI (Phase 2). PCs default to "hero" once a GM tags them; NPCs default to "neutral" until tagged.

## Backlog (post-Phase-6)

- Reach-weapon awareness in the pre-move modal: show "⚠ entering Tavik's 10 ft polearm reach" for Polearm Master enter-OAs.
- Hostile-only filter independent of the team data model: a "creature you're afraid of" or "creature you can't see" wouldn't provoke OA from a Frightened/Blinded watcher. Reuses existing buff inspection.
- Auto-reaction toggle: a GM-side setting that auto-takes every OA with the watcher's first melee weapon. Useful for fast NPC-vs-NPC swing fights.
- Forced movement / teleport / pushed-out-of-reach distinction (see open question).

## Wiki surfacing

This plan lives at `docs/plans/movement-oa-flow.md` and is reachable via `/wiki/doc/plan-movement-oa-flow` per the v2.49.9 allowlist + landing-page surfacing rules in `CLAUDE.md`. Per-slug harness coverage: `tests/harness/test_wiki.py::test_wiki_doc_serves_movement_oa_flow_plan`.

## See also

- [Reactions automation plan](/wiki/doc/plan-reactions-automation) — the generic reaction-prompt machinery this plan builds on.
- [Reactions — GM Guide](/wiki/reactions) — operator-facing doc that gets updated each phase to reflect what's live.
- [The character sheet](/wiki/the-character-sheet) — where the watcher's melee attack list is defined.
