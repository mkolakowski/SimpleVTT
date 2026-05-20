# Endpoint catalog

**Audience:** contributors integrating with the SimpleVTT API or grepping for "where does X happen."
**Version stamp:** v2.43.15.

Hand-curated index of every gameplay-relevant HTTP endpoint. The full set is grep-able with `grep -nE "^@router\.(get|post|put|patch|delete)" app/routes/*.py` (139+ in `tabletop_routes.py` alone as of v2.43.14); this catalog focuses on the **core gameplay surface** — table actions, battle state, character + sheet, encounters, maps, tokens. Outside scope: the open5e proxy routes (`/api/open5e/…`), the homebrew CRUD (`/campaign/.../custom-classes`, `…/custom-feats`, etc.), and the Jinja page routes (`/`, `/login`, `/campaign/{id}`).

Pair this doc with the [realtime broadcasts catalog](realtime-broadcasts-catalog.md) — endpoint mutations broadcast WS messages, and the catalog cross-references both directions.

## Conventions

| Symbol / column | Meaning |
|-----------------|---------|
| **Auth** | `gm` = GM only, `member` = any campaign member, `owner` = character owner OR GM, `none` = public |
| **Body** | JSON keys the endpoint reads from `request.body`. `?` suffix = optional |
| **Broadcasts** | WS message types fired on success. See [realtime broadcasts catalog](realtime-broadcasts-catalog.md). |
| **Override** | endpoints that respect the `override: true` body field to bypass the Phase 4 action-economy gate |
| **Harness** | the `tests/harness/test_*.py` file where the happy-path coverage lives |

Per-endpoint URLs in this doc omit the `/api/campaign/{cid}` prefix where it's universal — the right-hand "Path" column carries the suffix only. Read full URL = `/api/campaign/{cid}` + `Path`.

## Table actions

These endpoints drive the roll-log cards + dice toasts + auto-resolution flows.

### `/roll`
- **Method:** `POST`
- **Body:** `expression`, `label?`, `note?`, `visibility?` (`public` / `gm_and_roller` / `gm_only`)
- **Auth:** member
- **Broadcasts:** `roll`
- **Behavior:** rolls the dice expression via `dice.py`, broadcasts a `roll` event with `total` / `expression` / `breakdown` / `note` / `visibility`. Optional `label` is rendered into the `note` line. The visibility field gates both the WS broadcast (server-side filter) and the client-side render (defense-in-depth).
- **Harness:** `test_roll.py` + `test_broadcast_payload_shapes.py::test_roll_*`.

### `/attack`
- **Method:** `POST`
- **Body:** `character_id`, `attack_index`, `target_combatant_id?`, `target_name?`, `target_character_id?`, `uplifts?` (Smite / Sneak Attack list), `override?`
- **Auth:** owner
- **Broadcasts:** `weapon_attack` (+ `character_hp_update` + `economy_update` when auto-apply lands), possibly `character_death_save`
- **Behavior:** rolls the d20 attack + the damage dice + (optionally) bonus damage uplifts. When `Campaign.auto_apply_damage` is on AND a target is set, hit determination runs server-side; on a hit, damage applies via `_apply_damage_to_combatant` and the broadcast carries `hit` / `is_crit` / `target_hp_before` / `target_hp_after` / `damage_applied`. Records the application in `_attack_damage_log` for the Undo button.
- **Harness:** `test_attack.py`, `test_attack_auto_damage.py`, `test_attack_buff_intercepts.py`, `test_broadcast_payload_shapes.py::test_weapon_attack_*`.

### `/cast_spell`
- **Method:** `POST`
- **Body:** `character_id`, `spell_index`, `slot_level`, `class_slug`, `target_combatant_id?`, `target_character_id?`, `target_name?`, `override?`
- **Auth:** owner
- **Broadcasts:** `spell_cast`, plus `character_hp_update` / `heal_applied` / `buff_update` / `character_death_save` / `roll_request` / `roll` (concentration log) depending on the auto-resolution path that fires.
- **Behavior:** the richest endpoint. Resolves the spell's action schema, picks a damage tier for cantrips by character level, auto-applies heals (T.4), rolls auto-attacks (T.4b/c — including multi-beam for Eldritch Blast), rolls auto-saves (T.3 — NPC server-side, T.3d — PC via roll_request), installs save-or-suck conditions (T.3c) + paired caster-side concentration buffs (T.3e). Strips manual buttons that the auto-resolution path already covered (v2.42.3).
- **Harness:** `test_cast_spell*.py` (several files), `test_cast_spell_target.py`, `test_concentration_cleanup.py`, `test_save_spell_pc_buff.py`, `test_broadcast_payload_shapes.py::test_spell_cast_*`.

### `/use_feature`
- **Method:** `POST`
- **Body:** `character_id`, `feature_key`, `option_key?`, `label?`, `desc?`, `override?`
- **Auth:** owner
- **Broadcasts:** `feature_used`
- **Behavior:** generic class-feature announce. Slot is re-derived server-side from `_FEATURE_ECONOMY` (no client claims trusted). The body's `desc` field falls back to the server's `_feature_economy_desc` lookup when empty (v2.43.11) so the roll-log card always carries the inline description tail.
- **Harness:** `test_use_feature.py`, `test_broadcast_payload_shapes.py::test_feature_used_*`.

### Dedicated class-feature endpoints

These bypass `/use_feature` because they need extra side effects (roll a die, decrement a pool, refund a chip, install a buff). Each fires `feature_used` plus its own follow-ups.

| Path | Side effects | Broadcasts | Harness |
|------|--------------|-----------|---------|
| `/use_second_wind` | Roll 1d10+lv, apply HP, decrement counter, mark bonus chip. v2.43.0+ broadcasts heal-pill fields; v2.43.12 restores rolled-dice info in `feature_desc`. | `feature_used`, `resource_update`, `character_hp_update`, possibly `character_death_save` | `test_use_second_wind.py` |
| `/use_action_surge` | Decrement counter, REFUND the action chip (clears it in the hub). | `feature_used`, `resource_update`, `economy_update` | `test_use_action_surge.py` |
| `/use_rage` | Install rage buff, decrement counter, mark bonus chip. | `feature_used`, `buff_update`, `resource_update` | `test_use_rage.py` |
| `/use_lay_on_hands` | Spend from pool, apply HP to target. v2.43.0+ heal-pill fields on broadcast. | `feature_used`, `resource_update`, `heal_applied`, `character_hp_update` | `test_use_lay_on_hands.py` |
| `/use_bardic_inspiration` | Decrement BI uses. Target picker lives client-side. | `feature_used`, `resource_update` | `test_use_bardic_inspiration.py` |
| `/use_cutting_words` | Roll BI die server-side, decrement BI, mark reaction chip. Target picker upstream. | `feature_used`, `resource_update` | `test_use_cutting_words.py` |
| `/use_arcane_recovery` | Restore spell slots up to `⌈wizard_lv/2⌉`. Out-of-combat only. | `feature_used`, `resource_update`, `spell_slot_update` (per restored slot) | `test_use_arcane_recovery.py` |
| `/use_item` | Use a consumable. Potions trigger `heal_applied` (house rule: bonus action). | `feature_used`, possibly `heal_applied` + `character_hp_update` | (covered indirectly) |

### Concentration helpers

| Path | Purpose | Broadcasts |
|------|---------|-----------|
| `/cast_hunters_mark` | Install Hunter's Mark on target + caster-side concentration anchor. | `spell_cast`, `buff_update`, `concentration_update` |
| `/cast_hex` | Install Hex on target + caster-side concentration anchor. | `spell_cast`, `buff_update`, `concentration_update` |
| `/end_buff` | Manually remove a buff. Triggers paired-buff cleanup if the buff was a concentration anchor (v2.38.0 T.3e). | `buff_update` |

### Heal flow + Undo

| Path | Purpose | Broadcasts |
|------|---------|-----------|
| `/apply_healing` | Legacy heal-claim apply (player clicks the manual "Apply Healing" button). Returns `already_auto_applied: true` when T.4 had already auto-applied the heal. | `heal_applied`, `character_hp_update` |
| `/undo_attack_damage` | Reverts a `weapon_attack` or `spell_cast` damage / heal application. Looks up the entry in `_attack_damage_log` (8h TTL). | `character_hp_update`, possibly `character_death_save` |

### Roll requests

| Path | Purpose | Broadcasts |
|------|---------|-----------|
| `/roll_request` (POST) | GM panel "Request roll" — broadcasts a `roll_request` event with optional per-player targeting (`target_user_ids`). | `roll_request` |
| `/roll_request/{req_id}/respond` (POST) | Player rolls in response. Broadcasts a `roll` follow-up. Used by T.3d (save-or-suck PC prompts) to correlate the save outcome back to the spell-cast card. | `roll` |

## Battle state

### `/battle`
- **Method:** `PUT`
- **Body:** `combatants` (array), `turn_index`, `round`, `active`
- **Auth:** gm
- **Broadcasts:** `battle_update`
- **Behavior:** writes the full battle snapshot to the in-memory hub. Used by Start Initiative, init advance, and the test harness's `_seed_battle` setup pattern.

### `/character/{cid}/economy` (GET)
- Returns the character's current chip state. Used by the sheet's chip strip + the over-budget audit.

## Character + sheet

### `/character/{cid}` (POST / PUT)
- Updates the full character row. Broadcasts `character_update` (big — clients re-render the sheet). Prefer the patch endpoint below for narrow edits.

### `/character/{cid}/sheet-fields` (PATCH)
- **Body:** any subset of sheet fields, plus optional `hp_change_reason` for HP edits.
- Broadcasts `character_hp_update` (HP-only delta — lightweight). Also fires `character_death_save` when the HP edit crosses the death-save state machine threshold (drops to 0, comes back from dying, instant-kill via massive damage, etc.).

### `/character/{cid}/death-save` (POST)
- **Body:** `result?` ("success" / "failure"), `nat20?`, `nat1?`
- Increments the death-save tally; on 3 successes the character stabilizes, on 3 failures they die. Broadcasts `character_death_save`. The override variant at `/death-save/override` lets the GM force-set the state.

### `/character/{cid}/stabilize` (POST)
- GM action — sets the dying character to 0 HP, stable, death-save counters reset.

### `/character/{cid}/roll-state` (POST)
- **Body:** `state` ("normal" / "advantage" / "disadvantage")
- Sets the next-roll advantage flag. Broadcasts `character_roll_state`. Drives the d20 toast's "2d20 keep highest/lowest" rendering.

### `/character/{cid}/rest` (POST)
- **Body:** `type` ("short" / "long")
- Resets HP, hit dice, spell slots, short-rest features (or long-rest on `type: long`). Broadcasts `short` / `long` + multiple `resource_update` + `spell_slot_update` follow-ups.

### `/character/{cid}/resource` (POST)
- **Body:** `key` (resource slug), `delta` (-1 to decrement, +N to refund)
- Used by the class-feature ⚡ Use button + Channel Divinity picker + every endpoint that decrements a counter. Broadcasts `resource_update`.

### `/character/{cid}/transform` (POST)
- **Body:** `beast_slug`
- Wild Shape transformation. Returns + broadcasts `transform_update` with the resolved `economy_slot` (Moon Druid → bonus, default → action).

### `/character/{cid}/revert` (POST)
- Reverts a Wild Shape transformation back to the original character form.

### `/character/{cid}/color` + `/character/{cid}/ring-style` (POST)
- Update per-token color + ring style. Broadcast `character_color_update` / `character_ring_update`. Drives the canvas token outline + the sheet header accent.

### `/character/{cid}/buffs` (GET)
- Snapshot of active buffs on the character. Used by the sheet's buff descriptive layer.

### `/character/{cid}/place-token` (POST)
- Drops a token for this character on the active map. Broadcasts `token_add`.

### `/character/{cid}/token` (DELETE)
- Removes the character's token from the map.

## Tokens

### `/tokens` (GET / POST)
- GET: list all tokens on the active map.
- POST: create a token (often called for monster tokens). Broadcasts `token_add`.

### `/tokens/{token_id}` (DELETE)
- Broadcasts `token_delete`.

### `/token/{token_id}` (PATCH)
- Update a token (image, name, scale). Broadcasts `token_update`.

### `/token/{token_id}/move` (POST)
- Drag-move endpoint. Throttled — broadcasts `token_move` ~every 50 ms during a drag.

### `/token/{token_id}/image` (POST)
- Upload a new token image.

## Encounters

| Path | Method | Purpose |
|------|--------|---------|
| `/encounters` | GET | List campaign encounters. |
| `/encounters` | POST | Build a new encounter from the current battle + tokens. |
| `/encounters/{id}` | PATCH | Rename / update metadata. |
| `/encounters/{id}/spawn` | POST | Spawn the encounter's tokens onto the active map (without overwriting the battle state). |
| `/encounters/{id}/duplicate` | POST | Clone the encounter. |
| `/encounters/{id}/update` | POST | Overwrite the encounter from the current battle state. |
| `/encounters/{id}/load` | POST | Destructive load — wipes the active map's tokens + battle, then writes the encounter's snapshot. |
| `/encounters/{id}/delete` | POST | Delete the encounter row. |

Harness coverage: `test_encounters.py`.

## Maps (campaign settings)

These live under `/campaign/{cid}/settings/maps/{map_id}/...` (no `/api/` prefix — they're form-post endpoints called from the settings page).

| Path | Method | Purpose |
|------|--------|---------|
| `/settings/maps` | POST | Upload a new map. |
| `/settings/maps/{id}/rename` | POST | Rename. |
| `/settings/maps/{id}/grid_size` | POST | Set the per-map grid size (overrides campaign default). |
| `/settings/maps/{id}/show_grid` | POST | Toggle the grid overlay (v2.4.0). |
| `/settings/maps/{id}/tags` | POST | Update the map's tag list. |
| `/settings/maps/{id}/folder` | POST | Move the map into a folder. |
| `/settings/maps/{id}/activate` | POST | Make this map the active one. Broadcasts `map_change`. |
| `/settings/maps/{id}/delete` | POST | Delete. |

## Session lifecycle

| Path | Method | Purpose |
|------|--------|---------|
| `/campaign/{cid}/session/start` | POST | GM starts a session. Broadcasts `session_started`. |
| `/campaign/{cid}/session/end` | POST | GM ends a session. Broadcasts `session_ended` — non-GM clients are bounced off the tabletop. |

## Templates (token templates)

Token templates are the monster archetypes that spawn tokens via the GM's Add Token modal.

| Path | Method | Purpose |
|------|--------|---------|
| `/templates` | GET | List. |
| `/templates` | POST | Create. |
| `/templates/{id}` | PATCH / DELETE | Update / remove. |
| `/templates/{id}/image` | POST | Upload portrait. |
| `/templates/{id}/sheet` | GET | Render the monster sheet (for the mini-sheet expand). |
| `/templates/export` (GET) + `/templates/import` (POST) | Export / import. |
| `/templates/import-monster` | POST | Pull a monster from the SRD bestiary (`local_content`) into a custom template. |

## Settings

### `/campaign/{cid}/settings` (POST)
- The big multi-field form. Updates `auto_apply_damage`, `strict_action_economy`, `gm_tab_color`, audio settings, HP threshold colors, default encounter wiring, etc. No granular endpoints — one form post.

### `/campaign/{cid}/settings/members/...`
- Add / remove members. Broadcasts `member_color_update` if the member's color changes.

### `/api/campaign/{cid}/member_color` (POST)
- Per-player tab color. Broadcasts `member_color_update`.

## Roster + utilities

### `/api/campaign/{cid}/roster` (GET)
- Skinny character list keyed by ID + name + owner. Used by harness fixtures + sheet picker dropdowns.

### `/api/character/{cid}/multiclass-check` (GET)
- Pre-flight check for adding a multiclass level — validates ability-score prerequisites against the SRD rules.

## Auth + user (cross-campaign)

These live in `app/routes/auth_routes.py` and `app/routes/user_routes.py`. No campaign scope.

| Path | Method | Purpose |
|------|--------|---------|
| `/login`, `/logout`, `/register` | GET / POST | Auth flow. `APP_ALLOW_LOCAL_REGISTRATION` env toggles register. |
| `/auth/google/login`, `/auth/google/callback` | GET | Google SSO. |
| `/characters` (GET) + `/characters/new` (POST) | | Cross-campaign character list + create. |
| `/character/{cid}/sheet` (GET) | | Full-page sheet view (Jinja). |
| `/settings` (GET) + `/api/settings/{theme,font,scale,zoom_speed,animate_gifs,tab_color}` (POST) | | Per-user prefs. |

## Health + metadata

| Path | Method | Purpose |
|------|--------|---------|
| `/healthz` | GET | Liveness probe — returns `{ok, app_version, schema_version}`. |
| `/version` | GET | Same payload minus the `ok` field. Used by deploy scripts + the harness. |

## Where the code lives

- **Routes:** `app/routes/tabletop_routes.py` (the bulk — 139+ endpoints), `app/routes/auth_routes.py`, `app/routes/user_routes.py`, `app/routes/audio_routes.py`, `app/routes/admin_routes.py`, `app/routes/homebrew_routes.py`, `app/routes/wiki_routes.py`.
- **Realtime hub:** `app/realtime.py` (`CampaignHub.broadcast`).
- **Per-endpoint behavior tests:** `tests/harness/test_<endpoint>.py`.
- **Payload-shape tests:** `tests/harness/test_broadcast_payload_shapes.py`.

## Adding a new endpoint

The CLAUDE.md harness rule applies — every commit that adds an HTTP endpoint or changes a WebSocket broadcast shape MUST land at least one harness test. The pattern:

1. **Decide the URL.** Tabletop actions go under `/api/campaign/{cid}/...`. Form-post settings go under `/campaign/{cid}/settings/...`.
2. **Define the body shape.** Keep it small + flat. Use `override: bool` for endpoints that respect the action-economy gate.
3. **Resolve the slot server-side.** Don't trust client claims — re-derive via `_feature_economy_slot` or the equivalent.
4. **Broadcast on success.** `await hub.broadcast(cid, {"type": "...", "data": {...}})`. Pick a slug (see [broadcasts catalog](realtime-broadcasts-catalog.md)).
5. **Add a behavior test.** Happy-path + at least one error path. See `tests/harness/test_attack.py` for the canonical shape.
6. **Add a payload-shape test** if the broadcast carries new fields.
7. **Add a row to this catalog.**
