# Realtime broadcasts catalog

**Audience:** contributors adding or debugging WebSocket-driven UI.
**Version stamp:** v2.43.14.

Every realtime update in SimpleVTT flows through a per-campaign WebSocket hub (`app/realtime.py`'s `CampaignHub`). Each server-side state change broadcasts a typed JSON message; client subscribers dispatch off `msg.type` to update the canvas, sheet, roll log, dice toast, etc.

This page is the **complete catalog**: every broadcast type, what fires it, what the payload carries, and which client handler reads it. Pair this doc with the harness payload-shape tests at `tests/harness/test_broadcast_payload_shapes.py` — that suite asserts the contract; this catalog narrates it.

## How the hub works

```
client GET  /campaign/{id}                  ← Jinja page load
client UPGRADE  /ws/campaign/{id}            ← WebSocket subscribe
   ↓
CampaignHub (app/realtime.py)
   ↓ on every change, server calls:
hub.broadcast(campaign_id, {"type": "...", "data": {...}})
   ↓ hub fans out to every connected socket for that campaign
client onmessage:
   document.dispatchEvent(new CustomEvent('vtt:ws-message', { detail: msg }))
   ↓ AND a big if/else if dispatch on msg.type inside tabletop.js
```

Three notes worth absorbing:

- **Per-campaign isolation.** The hub keys on `campaign_id`. Two campaigns running concurrently never see each other's broadcasts.
- **In-memory state.** The hub also caches the current `battle_state` + `tokens` snapshots in memory, separate from the DB. Restart loses ephemeral state (chip flips, in-progress targeting); persistent state (HP, sheet edits) survives because it's DB-backed.
- **Two dispatch paths.** Most handlers are wired inline in the `tabletop.js` `onmessage` block (a big if/else if on `msg.type`). The dice toast (`roll_toast.js`) listens off a `vtt:ws-message` `CustomEvent` that the same block re-dispatches — gives the toast subscriber a decoupled path so character-sheet pages can listen too.

## Quick index

| Broadcast type | Fired by | Client handler (`tabletop.js`) | Notes |
|----------------|---------|--------------------------------|-------|
| `roll` | `/roll`, every dice-rolling endpoint internally | `appendRoll`, `roll_toast.js` | Has `visibility` field; filter applies. |
| `roll_request` | GM panel "Request roll" button | `appendRollRequest` | Per-player targeting via `target_user_ids`. |
| `weapon_attack` | `/attack` | `appendWeaponAttack`, `roll_toast.js` | Two-toast sequence (attack → 1600 ms → damage). |
| `spell_cast` | `/cast_spell` (+ heal_claim flow) | `appendSpellCast`, `roll_toast.js` | Richest payload — `auto_*` sub-trees for heal/attack/save. |
| `feature_used` | `/use_feature`, `/use_second_wind`, `/use_lay_on_hands`, `/use_rage`, `/use_cutting_words`, `/use_action_surge`, `/use_arcane_recovery`, `/use_bardic_inspiration` | `_appendFeatureUsed`, `roll_toast.js` (when `dice_*` set) | Header + inline desc; optional heal pill + dice toast. |
| `heal_applied` | `/apply_healing`, `/use_lay_on_hands`, `/use_second_wind`, `/cast_spell` (T.4 auto-heal) | `_onHealApplied` | Updates token HP bar + sheet HP. |
| `battle_update` | `/battle` PUT, init advance, chip flip | `_onBattleUpdate` | Full snapshot of combatants + turn_index + round. |
| `economy_update` | `_mark_battle_economy`, GM chip click | (inside battle_update broadcast cycle) | Lightweight chip-state delta. |
| `character_update` | `/character/{id}` PATCH/PUT | `_onCharacterUpdate` | Full sheet refresh — broad. |
| `character_hp_update` | `_apply_hp_change` + HP-edit endpoints | `_onCharacterHpUpdate` | HP-only delta; faster path than `character_update`. |
| `character_death_save` | `_apply_hp_change` when crossing 0 / 3-success / 3-fail | `_onCharacterDeathSave` | Drives the death-save tracker overlay. |
| `character_roll_state` | `/character/{id}/roll_state` POST | `_onCharacterRollState` | Sets advantage/disadvantage flag on next roll. |
| `character_color_update` | Character color picker on sheet | inline | Recolors the token ring + sheet header. |
| `character_ring_update` | Character ring-style picker | inline | Token outline style (solid / dashed / glow / etc.). |
| `member_color_update` | GM tab color in campaign settings | inline | Recolors per-player UI bits. |
| `resource_update` | `/character/{id}/resource` POST | `_onResourceUpdate` | Class-feature counters (Channel Divinity uses, Bardic Inspiration, Lay on Hands pool). |
| `spell_slot_update` | Spell-slot tracker edits | `_onSpellSlotUpdate` | Per-slot-level remaining counters. |
| `buff_update` | `_install_buff`, `_remove_buff`, `_drop_paired_concentration_buffs` | inline | Per-combatant buff list change. |
| `concentration_save` | `_maybe_concentration_save` after damage | inline + GM-only `roll` follow-up | Includes pass/fail + dropped paired buffs. |
| `concentration_update` | Concentration toggle on sheet | inline | Concentration anchor on/off. |
| `transform_update` | `/transform` (wild shape) | `_onTransformUpdate` | Beast form swap on a Druid token. |
| `map_change` | `/maps/{id}/set_active` | inline | Repaints the canvas with the new map background. |
| `token_add` / `token_delete` / `token_update` / `token_move` | Token CRUD + drag | inline | Canvas state — see `app/realtime.py` for the throttled `token_move` debounce. |
| `presence_update` | WS connect / disconnect / heartbeat | `_onPresenceUpdate` | Online/offline indicator at the bottom-left of the canvas. |
| `session_started` / `session_ended` | GM Tools "Start session" / "End session" | inline | Bounces non-GM clients off the tabletop on `session_ended`. |
| `long` / `short` | Long/short rest endpoints | inline | Rest indicator; refreshes HP + resource counters. |
| `audio_play` | Audio routes | `roll_toast.js`-adjacent audio listener | Triggers playlist playback. |
| `beast` | Wild Shape beast picker | inline | Modal callback. |

## Per-broadcast details

### `roll`

**Fired by:** `/roll` and every dice-rolling endpoint that wants the standard breakdown UI (e.g. `/roll_request/{id}/respond`, the v2.39.0 GM concentration log, save spells via `auto_save_breakdown`).

**Payload:** see `tests/harness/test_broadcast_payload_shapes.py::test_roll_broadcast_carries_all_required_fields` for the field-presence contract. Required keys: `total`, `expression`, `breakdown`, `user_id`, `user_name`, `visibility`, `note`. Optional: `char_name`, `portrait_url`, `user_color` (display only).

**Visibility:** `public` / `gm_and_roller` / `gm_only`. Server-side `/roll` only broadcasts to eligible sockets; client also re-checks before rendering — defense-in-depth.

**Handlers:**
- `appendRoll` in `tabletop.js` — renders the roll-log card (big number + note + breakdown pill).
- `vtt:ws-message` listener in `roll_toast.js` — fires the animated dice popup.

### `roll_request`

**Fired by:** GM panel "Request roll" button (or programmatically by endpoints that want to prompt a player).

**Payload:** `id`, `dc`, `expression`, `label`, `target_user_ids` (per-player gating; empty = everyone sees the prompt), `creator_user_id`, plus character-select metadata for the Roll button.

**Handler:** `appendRollRequest` in `tabletop.js`. Renders a roll-request card with a "Roll" button; the click POSTs `/roll_request/{id}/respond`, which broadcasts a `roll` follow-up.

### `weapon_attack`

**Fired by:** `/attack` (weapon strikes via the sheet + monster attacks via mini-sheet).

**Payload:** 13+ keys. See `tests/harness/test_broadcast_payload_shapes.py::test_weapon_attack_broadcast_carries_all_required_fields`. Required: `attack_total`, `attack_breakdown`, `attack_name`, `damage_total`, `damage_breakdown`, `damage_type`, `caster_user_id`, `caster_user_name`, `caster_char_name`, `id`, `hit`, `is_crit`, `is_save`, `over_budget`. Optional: `bonus_damage_*` (Sneak Attack / Divine Smite), `target_*` (resistance, HP delta, dying/dead status), `range`, `desc`.

**Visibility:** always public.

**Handlers:**
- `appendWeaponAttack` in `tabletop.js` — renders the attack card with the oversized pill row.
- `roll_toast.js` listener — fires two toasts in sequence: attack-d20 immediately, damage roll 1600 ms later.

### `spell_cast`

**Fired by:** `/cast_spell`.

**Payload:** the richest broadcast in the system. Header fields (`spell_name`, `slot_level`, `spell_level`, `spell_school`, `spell_casting_time`, `spell_range`, `spell_concentration`, `spell_ritual`, `spell_desc`), caster fields (`caster_*`), target fields (`target_*`), and three auto-resolution sub-trees:

- **`auto_heal_*`** — fires when T.4 auto-applied the heal. Fields: `auto_heal_applied` (HP delta), `auto_heal_target_name`, `auto_heal_hp_before`, `auto_heal_hp_after`, `auto_heal_revived`.
- **`auto_attack_*`** — fires when T.4b/c spell attack resolved. Fields: `auto_attack_hit`, `auto_attack_total`, `auto_attack_breakdown`, `auto_attack_target_name`, `auto_attack_target_ac`, `auto_attack_damage_applied`, `auto_attack_damage_breakdown`, `auto_attack_damage_type`, `auto_attack_crit`. Plus `auto_attack_beams` (list) for multi-beam casts (Eldritch Blast at L5+).
- **`auto_save_*`** — fires when T.3/T.3b/T.3c save spell resolved. Fields: `auto_save_target_kind` (pc/npc), `auto_save_target_name`, `auto_save_ability`, `auto_save_dc`, `auto_save_rolled`, `auto_save_breakdown`, `auto_save_passed`, `auto_save_prompted` (PC path), `auto_save_damage_applied`, `auto_save_damage_breakdown`, `auto_save_damage_type`, `auto_save_buff_name`, `auto_save_buff_duration`, `auto_save_buff_icon`.

Plus `actions` (the cast's action button schema) + `character_level` (for damage-scaling tier resolution).

**Visibility:** always public.

**Handlers:**
- `appendSpellCast` in `tabletop.js` — renders the spell-cast card with target tag in the header + inline meta row + oversized result pills + manual action buttons (when auto-resolution didn't already cover them).
- `roll_toast.js` listener — fires dice toasts off the `auto_attack_*` and `auto_save_damage_*` fields.

### `feature_used`

**Fired by:** `/use_feature` (generic), `/use_second_wind`, `/use_lay_on_hands`, `/use_rage`, `/use_cutting_words`, `/use_action_surge`, `/use_arcane_recovery`, `/use_bardic_inspiration`. Class-feature uses always announce.

**Payload:**
- Header: `character_id`, `character_name`, `user_color`, `source` (slug — drives the header chip label via `_featureSourceLabel`), `over_budget`, `over_budget_slot`.
- Body row: `feature_name`, `feature_desc` (server-side fallback from `_FEATURE_ECONOMY` table when client didn't send one — v2.43.11), `remaining`, `max`.
- Optional dice fields: `dice_expression`, `dice_total`, `dice_breakdown`, `dice_note` — when present, `roll_toast.js` fires a dice popup for the rolled die (Second Wind heal die, Bardic Inspiration grant die, Cutting Words BI die).
- Optional heal pill fields (v2.43.0+): `heal_amount`, `heal_target_name`, `heal_hp_before`, `heal_hp_after` — when `heal_amount > 0` the card renders an oversized heal pill.

**Visibility:** always public.

**Handlers:**
- `_appendFeatureUsed` in `tabletop.js` — renders the feature-used card with header chip + inline desc + optional heal pill.
- `roll_toast.js` listener — fires a dice popup when `dice_*` fields are set.

### `heal_applied`

**Fired by:** `/apply_healing`, `/use_lay_on_hands`, `/use_second_wind`, `/cast_spell` (T.4 auto-heal path).

**Payload:** `char_id`, `hp_current`, `hp_max`, optionally `rolled`, `breakdown`, `target_name`, `caster_name`, `caster_char_name`.

**Handler:** `_onHealApplied` in `tabletop.js` — updates the target's HP bar on the canvas + the open sheet's HP block. Adds a "+N HP" indicator over the token briefly.

### Combat state broadcasts

**`battle_update`** carries the full battle snapshot: `combatants` (array, each with `id`, `char_id`, `name`, `initiative`, `hp_current`, `hp_max`, `buffs`, `economy`), `turn_index`, `round`, `active`. Fired on `PUT /battle`, init advance, every chip flip, every buff change. Heavy — replaces full client-side battle state each time.

**`economy_update`** is a lightweight chip-flip delta: `character_id`, `slot`, `value`. Fired separately for incremental updates that don't need a full battle snapshot.

**`buff_update`** fires when `_install_buff` or `_remove_buff` mutates a combatant's buff list. Payload: `combatant_id`, `buffs` (full new list).

**`concentration_save`** fires when `_maybe_concentration_save` rolls a CON save after damage. Payload: `character_id`, `dc`, `rolled`, `breakdown`, `passed`, optionally `dropped_buffs` (list of names). When `passed: false`, a follow-up GM-only `roll` event with `visibility: "gm_only"` narrates the dropped concentration buffs (v2.39.0).

**`concentration_update`** fires when concentration is toggled on/off on the sheet directly (not via a save).

### Character / sheet broadcasts

**`character_update`** is the big sync — full sheet refresh. Fires on `/character/{id}` PATCH / PUT. Other clients viewing the sheet re-render entirely.

**`character_hp_update`** is the lightweight HP-only delta. Fires on every HP edit (sheet input change, `_apply_hp_change` calls, the v2.5.0 potion auto-heal). Payload: `char_id`, `hp_current`, `hp_max`, `hp_temp`.

**`character_death_save`** fires when `_apply_hp_change` crosses the death-save state machine boundary. Payload: `character_id`, `status` (`alive` / `dying` / `dead` / `stable`), `successes` (0–3), `failures` (0–3), `hp`, `source` (e.g. `second_wind`).

**`character_roll_state`** carries the next-roll advantage flag from `/character/{id}/roll_state`. Payload: `character_id`, `state` (`normal` / `advantage` / `disadvantage`).

**`resource_update`** is the class-feature counter delta. Fires on `/character/{id}/resource` POST + every endpoint that decrements a counter (Second Wind, Channel Divinity uses, Bardic Inspiration, Lay on Hands pool). Payload: `character_id`, `key` (resource slug), `current`, `max`.

**`spell_slot_update`** fires when a spell slot is spent or restored. Payload: `character_id`, `level`, `current`, `max`.

**`transform_update`** fires on `/transform` (Wild Shape). Payload: `character_id`, `beast_slug`, `economy_slot`.

### Color / appearance broadcasts

`character_color_update`, `character_ring_update`, `member_color_update` — all carry `character_id` (or `user_id` for member) + the new value. Used to drive per-token color + per-player UI accents in real-time.

### Token / map broadcasts

`token_add` / `token_delete` / `token_update` / `token_move` — canvas state. The `token_move` broadcast is throttled (~50 ms debounce) for dragged tokens so the WS doesn't flood.

`map_change` carries `map_id` + a snapshot of the new map state. Triggers a full canvas repaint.

### Session lifecycle

`session_started` / `session_ended` — GM-controlled session state. Non-GM clients bounce off the tabletop on `session_ended` (router redirect via the global fetch interceptor).

`presence_update` — connect / disconnect / heartbeat. Drives the online-presence indicator at the bottom-left of the canvas.

`long` / `short` — rest broadcasts. Reset short-rest features on `short`; reset everything on `long`. Refresh HP, hit dice, slots, class-feature counters.

### Misc

`audio_play` — playlist trigger from the audio routes.

`beast` — Wild Shape beast picker selection.

## Visibility filter

`roll` events carry a `visibility` field:

| Visibility | Reaches |
|------------|---------|
| `public` (default) | Every connected socket. |
| `gm_and_roller` | GM + the rolling user only. |
| `gm_only` | GM only. |

Filter is enforced **both** server-side (`/roll` only broadcasts to eligible sockets) and client-side (`appendRoll` re-checks before rendering). The dice toast in `roll_toast.js` independently re-checks too.

Other broadcast types (`weapon_attack`, `spell_cast`, `feature_used`) are **always public** — they represent public table actions. The GM-only concentration follow-up (v2.39.0) is the one exception: it's a `roll` event with `visibility: "gm_only"`.

## Where the code lives

- **Hub:** `app/realtime.py` — `CampaignHub` class, `hub.broadcast(campaign_id, msg)` entry point, the in-memory `battle_state` + `tokens` snapshots.
- **Server-side broadcast sites:** `app/routes/tabletop_routes.py` — search for `"type": "<broadcast_name>"` to find every fire site. 33 broadcast types as of v2.43.14.
- **Client-side dispatch:** `app/static/tabletop.js` — search for `if (msg.type === '...')` in the WS `onmessage` block.
- **Decoupled dice-toast subscriber:** `app/static/roll_toast.js` — listens off `vtt:ws-message` CustomEvent.
- **Payload contract tests:** `tests/harness/test_broadcast_payload_shapes.py` — asserts every field the client reads is present on the corresponding broadcast.
- **Design docs:** `docs/plans/test-harness.md`, `docs/roll-log-card-layout.md`.

## Adding a new broadcast type

Convention checklist when wiring a new one:

1. **Decide a slug.** Use snake_case, present-tense verb (`token_move`, `heal_applied`, `concentration_save`). Avoid generic names (`update`, `event`).
2. **Server:** `await hub.broadcast(campaign_id, {"type": "<slug>", "data": {...}})` at the mutation site.
3. **Client dispatch:** add a branch in the `tabletop.js` `onmessage` if/else if block.
4. **Handler:** name it `_on<Slug>` (e.g. `_onCharacterHpUpdate`).
5. **Payload-shape test:** add to `tests/harness/test_broadcast_payload_shapes.py`. Use the `_assert_keys` helper.
6. **Visibility:** decide if it needs a filter. If yes, mirror the `roll` event's pattern (server-side filter + client-side re-check).
7. **Add a row** to the "Quick index" table in this file.

When the new broadcast lives behind a new endpoint, the harness rule from `CLAUDE.md` also requires a behavior test for the endpoint. The shape test is separate.
