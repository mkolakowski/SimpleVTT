# Running a session as GM

**Audience:** the GM at the table — opens this in a tab next to the tabletop.
**Version stamp:** v2.43.18.

The densest GM-facing guide in the wiki. Walks through the full session loop: pre-session setup, starting initiative, running combat (chips, targeting, auto-resolution, undo, buffs, death saves), managing concentration, cycling turns, mid-session housekeeping (HP edits, save prompts, audio cues, encounter snapshots), and ending the session. Cross-references the existing guides for surfaces that have their own docs.

If you haven't yet brought a fresh instance up, read [first-run setup](first-run-setup.md) first.

## Pre-session checklist

Before players arrive (or before you click **▶ Start Session**):

1. **Activate the right map.** Campaign settings → Maps tab → click the radio next to the map you want. Players see the active map; old maps remain available for swap.
2. **Load or build the encounter.** Two paths:
   - **Load a saved encounter** (GM Tools drawer → Encounters panel → click an entry → **Load**). This wipes any current tokens + writes the saved snapshot back. Destructive — confirm before clicking.
   - **Build live** (Token Tracker → **Add Token**). Pick from your roster (PCs) or token templates (monsters). Set initiative as you go.
3. **Check the campaign settings you care about** (`/campaign/{cid}/settings`):
   - **Auto-apply damage** — when on, `/attack` and `/cast_spell` apply HP server-side and broadcast the result. When off, the damage roll fires but doesn't touch HP — players see the roll, you apply manually. Default is off; turn on if you want fast play.
   - **Strict action economy** — when on, the over-budget gate refuses player actions instead of opening the Layer B confirmation modal. Use this for hardcore-mode tables; default off.
   - **HP threshold colors** — visual tints on the HP bar at the 1/2/3/4 thresholds you set.
   - **Default encounter** — automatically loads on every page hit. Optional.
4. **Cue audio** if you use it. GM Tools drawer → Music panel → pick a playlist → ▶ Play. Players hear it (per their per-category volume preferences) unless they've muted that category.

When ready, click **▶ Start Session** in the GM Tools drawer. The button broadcasts `session_started` — players who load the campaign URL now land on the tabletop instead of getting bounced.

## Starting initiative

1. Each player rolls **Initiative** from their character sheet's combat tab (or you roll for them — sheet → Combat → click the d20 next to Initiative).
2. The roll-log card lands in the right drawer with the d20 toast.
3. Type their result into the **Initiative Tracker** drawer (left side of the screen) for each combatant. Or hit **Auto-Roll Initiative** on each NPC token from the Token Tracker.
4. Click **Start Initiative** at the top of the tracker. The first row highlights — that's whose turn it is.

The tracker now drives the session. Per-row you see:

- Portrait + name
- HP bar (with threshold tint colors when configured)
- AC chip
- Initiative number
- **Action-economy chips:** ⚔ Act / 💨 Bns / 🛡 Rxn / 👣 Mov — see below.
- **Buff chips:** 🔥 Marked / 🥶 Paralyzed / 😤 Rage / etc. — see [buffs section](#buffs--concentration).
- ✕ End-turn / advance button (the GM clicks; players' chips reset on advance).

For the per-row anatomy + the buff-chip mechanics, the dedicated "Initiative tracker drawer" wiki guide is filed in `docs/plans/wiki-expansion.md` — until it ships, this section is your reference.

## The action-economy chip strip

Each combatant has four chips: **⚔ Act** (action), **💨 Bns** (bonus action), **🛡 Rxn** (reaction), **👣 Mov** (movement counter, separate from the HP / AC display). When a player clicks a spell / attack / feature, the chip for that slot flips on automatically (server-side `_mark_battle_economy`).

GM controls:

- **Shift-click a chip** to manually toggle. Use this when a player declares "I'm using my bonus action for Healing Word" but the sheet didn't auto-flip because they cast it from a script.
- **End turn** advances initiative + resets the chips on the row whose turn just ended. Buffs with `duration_rounds` set decrement by 1.
- **Over-budget warnings.** When a player clicks an action whose chip is already burnt:
   - Without strict mode: a Layer B confirmation modal opens ("Krieger has already used their action this turn. Confirm to override."). Player clicks **Confirm** → action proceeds, the resulting card carries the ⚠ "Manual override" badge.
   - With strict mode: the action 409s; the player sees a status toast ("Already used their action this turn — ask the GM"). They cannot self-override.

The action-economy system has its own deep-dive wiki guide planned in the TODO list. The design rationale lives at `docs/plans/action-economy.md`.

## Targeting

Two interaction patterns to know:

1. **Single-target spells / attacks**: the player double-clicks a token to **target** it (target ring appears). Then they click the spell or weapon strike — the cast carries `target_combatant_id` so server-side auto-resolution can hit / damage / buff the right creature.
2. **The target picker modal** opens when the player clicks a heal / buff that needs a friendly target without one preset. Lay on Hands, Bardic Inspiration, Cutting Words — all use this. Cancel closes the cast without burning a chip.

Mobile / iPad players who can't double-tap reliably have a 🎯 button on each Token Tracker row (added v2.38.0 T.9).

3. **AoE spells (Fireball, Burning Hands, Lightning Bolt, etc.)**: the cast button does NOT open the picker. Instead the cast lands a "pending placement" card in the roll log with a `📍 Place sphere` / `📍 Place cone` / etc button. Only the caster (or the GM) can press it — other players see `⏳ Awaiting placement…`. Pressing the button opens the canvas placement picker; click to drop the sphere over the desired tokens. The server auto-rolls every swept-up target's save (NPCs AND PCs, server-side, using their save modifier) and applies save-for-half damage. The card mutates in place to show one pill per target plus a Σ aggregate. v2.48.0–v2.48.6.
4. **AoE shape badges on spell rows**: spells with a populated `area` block show a flame-orange badge in the spell list (`💥 20ft sphere`, `💥 15ft cone (you)`, `💥 100×5ft line`) so the GM knows at a glance which spells use the placement flow. v2.48.1.
5. **No active battle? The picker still works.** If init isn't started, the picker passes token IDs to `/place_aoe` which auto-adds swept-up NPC tokens to the battle state with HP from their template — they appear in the init tracker post-Fireball. v2.48.5.

Design notes at `docs/plans/targeting.md`.

## Auto-resolution outcomes

When **auto-apply damage** is on and a target is set, server-side resolution fires and the roll-log card carries the outcome pills:

| Outcome | Pill | Source |
|---------|------|--------|
| Heal | `chip-heal` (green) | T.4 — auto-applied on Healing Word + Cure Wounds + Mass Healing Word + heal-class features |
| Spell attack | `chip-hit` / `chip-miss` / `chip-crit` | T.4b — Fire Bolt + Eldritch Blast + Inflict Wounds + Guiding Bolt + Scorching Ray + Ray of Frost + Vampiric Touch |
| Save (PC) | `chip-prompt` (accent) | T.3d — roll-request sent to player; T.5d AoE saves auto-roll server-side instead |
| Save (NPC) | `chip-hit` / `chip-miss` | T.3 — server rolls 1d20+ability_mod against DC |
| Damage applied | `chip-damage` (orange) | T.2 attack / T.4b spell attack / T.3b save-for-half |
| Condition installed | `chip-buff` (cyan) | T.3c — Paralyzed / Charmed / Frightened / etc. with duration in rounds |
| Σ AoE total | `chip-damage` | T.5c — sum across per-target AoE entries |
| 💨 No targets | `chip-miss` | T.5e — AoE placed in empty patch of map |
| ↶ Undo | `chip-undo` button | Reverses HP changes within 8 hours of the cast |

**Click any pill** to expand it and see the dice breakdown (save roll, damage roll, attack roll). The pill grows slightly + reveals a `· Save: 1d20+2[15+2]=17 · Damage: 8d6[3,5,4,6,2,1,5,2]=28` detail row. Click again to collapse. Applies to single-target attack / save / damage / heal pills AND per-target AoE pills (v2.48.6 / v2.48.7).

Full anatomy + the verbose vs. compact mode design is in the [roll-log guide](roll-log-guide.html). The cast card's ▾ details element separately holds the spell description + higher-level upcast text.

## Cycling turns

The Initiative Tracker's top bar shows: **Round N · Turn M of K · ✕ End Turn**.

- **End Turn** (or hitting the next row's avatar) advances initiative. The previous row's chips reset; buffs decrement.
- **End Round** is implicit — when the last row in initiative ends, the tracker rolls back to row 0, increments the round counter, and decrements every buff with `duration_rounds`.
- **Buffs that reach 0 rounds** auto-drop on the next turn advance. The `buff_update` broadcast tells every client.

GM keyboard shortcuts (filed): future enhancement adds keybinds for End Turn + Set Target. Today everything is click-driven.

## Buffs + concentration

Per-combatant buff chips render under the HP bar. Click ✕ on any chip to manually remove (broadcasts `buff_update`).

**Concentration anchors.** When a caster maintains concentration on a spell (Hold Person, Hunter's Mark, Hex, Bless, etc.), a `concentration-<slug>` buff installs on the caster + the spell's effect buff installs on the target(s). The two are paired by `source_char_id`:

- **End the caster's concentration** (click ✕ on `Concentrating: Hold Person`) → every paired target-side condition drops at the same time. The `_drop_paired_concentration_buffs` helper handles this (v2.38.0 T.3e).
- **Caster takes damage** → server rolls a CON concentration save automatically (`_maybe_concentration_save`). On failure, the buff and its paired effects all drop. A GM-only `roll` event narrates what was lost (v2.39.0).
- **New concentration cast replaces the old one** → same cleanup helper fires for the old concentration's paired effects.

The buff slot system + concentration rules are a deep subsystem with their own future wiki guide.

## HP edits + the Undo button

Two ways to change HP outside the auto-apply flow:

1. **The character sheet's HP input** — type a new value. Broadcasts `character_hp_update` + may fire `character_death_save` if the change crosses the dying/stable/dead threshold (instant-kill via massive damage is checked here).
2. **The Undo button** on a recent weapon-attack or spell-cast card — reverts the HP change for that one cast. The server stores the original delta in `_attack_damage_log` for 8 hours; after that the Undo is gone. Returns a status toast on success ("↶ Reverted 9 damage to Bandit").

The **death-save state machine** runs from `_apply_hp_change`:

- HP drops to 0 → status `dying`, death-save tracker overlay appears on the sheet + tracker row.
- Each turn: the player (or the GM via the override endpoint) rolls a death save. 1–9 = failure, 10–19 = success, nat 1 = 2 failures, nat 20 = revive at 1 HP.
- 3 failures → status `dead`.
- 3 successes → status `stable` (no more rolls; still 0 HP).
- Any heal from `dying` resets the tracker and status returns to `alive`.

The full state machine has a planned "Death saves + dying" wiki guide. Design at `docs/plans/death-saves.md`.

## Visibility filter on rolls

The Dice Roller card (right drawer, top of the roll log) has a visibility dropdown:

- **Public** (default) — every connected client sees the roll-log card + dice toast.
- **GM + you** — visible to the GM + the rolling user. Card carries an amber "GM + you" badge.
- **GM only** — visible to the GM alone. Card carries a danger-colored "GM only" badge.

Used for: secret stealth checks, monster perception, behind-the-screen damage adjustments. Server-side and client-side filters both apply (defense-in-depth).

The v2.39.0 GM-only concentration-loss narrative entry uses the same `gm_only` visibility.

## Roll requests

When you want everyone to roll the same thing (perception check, surprise round, group athletics):

1. **GM Tools drawer → Request roll**. Fill the expression (`1d20+wisdom`), DC, optional label.
2. Click **Send**. A `roll_request` card appears in everyone's roll log.
3. Each player clicks the **Roll** button on their card; the response posts to `/roll_request/{id}/respond` and broadcasts a `roll` follow-up.
4. The GM sees one card per response, with the d20 result + pass/fail vs the DC.

**Per-player targeting** (v1.7.1): the request form has per-player checkboxes. Tick only the players you want to roll — others don't see the prompt. The GM always sees the button regardless.

This is the path the v2.37.0 T.3d PC save-or-suck flow uses too — Hold Person on a PC prompts that player via a `roll_request` event.

## Mid-session housekeeping

### Save a snapshot of the current battle

**Encounters panel → Save current state**. Name it, add tags / notes / a bound map / an auto-play playlist. The snapshot captures:
- Every token on the map (position, scale, color, image)
- The initiative tracker (combatants, turn_index, round)
- Any active buffs (with remaining durations)

Reload it later with **Load** to restore the exact state. Useful for: pausing a multi-session encounter, prepping the same combat for two different parties, recovering from a TPK.

The full Encounters CRUD has a planned dedicated wiki guide; until then see the [endpoint catalog](endpoint-catalog.md#encounters).

### Switch maps mid-session

Campaign settings → Maps tab → **Activate** another map. Broadcasts `map_change`; players see the new background. Tokens stay where they were (you may want to clear + drop new ones — Token Tracker → **Clear all** if your players agree).

### Adjust a player's HP / class resources

Click the player's token → mini-sheet → edit the HP input directly, or click ⚡ Use on a resource counter to decrement / refund. Resource updates broadcast `resource_update` so the player's full sheet syncs in real time.

### Spawn a wandering monster

GM Tools → Token Tracker → **Add Token**. Pick a token template (or import from the SRD bestiary via Token Templates → **Import**). The new token drops; auto-roll initiative + drag to position.

### Quick rolls behind the screen

Use the **Dice Roller** at the top of the roll-log drawer with **Visibility: GM only**. The roll lands in your log but never broadcasts to players.

## Ending the session

When the table is done:

1. **⏹ End Session** in the GM Tools drawer. Broadcasts `session_ended`; non-GM clients bounce off the tabletop (router redirect via the global fetch interceptor in `base.html`).
2. **Save the current state** as an encounter snapshot if you want to pick up where you left off.
3. **Long rest** if the fiction has the party resting. GM Tools → click each character's **Long Rest** button (or each player does their own from the sheet). HP + spell slots + hit dice + long-rest features all reset.

After end-session, the campaign page is GM-only until you click **▶ Start Session** again.

## Troubleshooting

**Player's chip didn't flip.** They cast a spell from outside the standard sheet flow (e.g. typed a /roll directly), or `auto_apply_damage` is off. Shift-click the chip manually.

**Auto-attack rolled a hit but no damage applied.** Auto-apply damage is off in campaign settings. Either turn it on or click the manual damage button on the roll-log card.

**Undo button is gone from an old card.** 8-hour TTL on `_attack_damage_log`. Past that window, edit HP directly on the sheet.

**Player can't see the target ring.** Targeting state is per-tab (localStorage). If they have two tabs open + targeted in one, they need to target again in the active tab.

**Roll request isn't reaching a specific player.** The request form's per-player checkboxes are exclusive — if any are ticked, only those players get the button. Untick all to broadcast to everyone.

**Concentration didn't drop when the spell should have ended.** The paired-buff cleanup only fires on the four documented paths (failed CON save, explicit `/end_buff`, new concentration cast replacing the old, target-side condition `/end_buff`). Manual edits via the sheet won't trigger the cleanup — you need to use the ✕ on the concentration anchor chip in the tracker.

## Where the code lives

- **Initiative tracker drawer:** `app/templates/tabletop.html` left-drawer block + `renderTokenTracker` in `app/static/tabletop.js`.
- **Action-economy chips:** `_mark_battle_economy` (server) + the chip-strip render in `tabletop.js` + the over-budget Layer B modal handler.
- **GM Tools drawer:** `app/templates/tabletop.html` `#gm-tools-drawer` block. Encounters, audio, session controls, request-roll all live here.
- **Visibility filter:** `app/static/roll_toast.js` + `appendRoll` re-check + server-side filter in `/roll`.
- **Death-save state machine:** `_apply_hp_change` in `app/routes/tabletop_routes.py`.

## Related guides

- **[First-run setup](first-run-setup.md)** — for the stand-up that precedes this guide.
- **[Architecture overview](architecture-overview.md)** — for the system map underneath.
- **[Endpoint catalog](endpoint-catalog.md)** — what the buttons in the UI POST to.
- **[Realtime broadcasts catalog](realtime-broadcasts-catalog.md)** — what each GM action broadcasts.
- **[Roll-log guide](roll-log-guide.html)** + **[Toast notifications guide](toast-notifications-guide.html)** — for the in-session feedback surfaces.
