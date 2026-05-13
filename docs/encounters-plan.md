# Combat encounters — design + phasing

> **Status:** Proposed — not started. Written 2026-05-12 by Claude for review.
> **Author intent:** let the GM save the current tabletop state as a named
> "encounter" and reload it later in one click. Bundles map + tokens +
> initiative + optional ambient audio.

Re-read before starting; push back on anything that doesn't survive a
fresh look.

---

## 1 — Why

Today, prepping a combat takes ~5 GM clicks per minute:

1. Switch the active map.
2. For each NPC: open the Add Token modal, pick a template, click on the map.
3. Hide tokens individually if doing a stealth reveal.
4. Add each combatant to the initiative tracker (or roll all).
5. Optionally cue ambient audio.

Multiply by 4–10 NPCs and most groups end up doing this work mid-session
while everyone waits. The fix: prep once, save, then `▶ Load` at the
table. **Encounter** = a snapshot of {map, tokens, initiative seed,
optional playlist} that can be replayed any number of times.

## 2 — What's there today

The pieces already exist; they just aren't bundled:

| Concept | Table | Lifetime |
|---|---|---|
| Map | `maps` | Permanent (campaign-scoped) |
| Token templates (NPCs / monsters) | `token_templates` | Permanent |
| Live tokens on the map | `tokens` | Survives until GM removes them |
| Initiative state | `hub._battle[campaign_id]` | **In-memory only** — lost on restart |
| Playlists | `playlists` / `playlist_tracks` | Permanent |
| Active map flag | `Map.is_active` (one per campaign) | Permanent |

The encounter system introduces one new table to bundle references to
these existing rows + the live state (positions, hidden flags) at the
moment of saving.

## 3 — Target data model

### 3.1 Schema

```python
class Encounter(Base):
    __tablename__ = "encounters"
    id: int (PK)
    campaign_id: int (FK → campaigns, ON DELETE CASCADE, indexed)
    name: str            # GM-chosen
    description: str     # optional GM notes
    map_id: Optional[int] (FK → maps, ON DELETE SET NULL)
    auto_play_playlist_id: Optional[int] (FK → playlists, ON DELETE SET NULL)
    auto_play_mode: str  # "order" / "shuffle" — same vocab as Campaign
    created_at, updated_at

    # The actual bundle. Shape:
    # {
    #   "tokens": [
    #     {
    #       "template_id": 7,            # OR null for free-floating
    #       "character_id": null,        # OR a Character.id for PC slots
    #       "label_override": "Goblin 1",
    #       "color_override": "#cc3333",
    #       "size": 1,
    #       "x": 240, "y": 380,
    #       "is_hidden": true,
    #     },
    #     ...
    #   ],
    #   "initiative": [
    #     {"name": "Goblin 1", "init": 12, "hp_max": 7, "hp_current": 7,
    #      "color": "#cc3333", "token_idx": 0},  # index into ``tokens`` for linking
    #     ...
    #   ],
    # }
    payload: dict (JSON column)
```

**Why JSON for the bundle?** Tokens and initiative entries are
per-encounter (not reusable across encounters), have nullable / optional
fields that vary by token type (PC vs NPC vs manual), and we want the
shape to evolve without N migrations. JSON column matches the existing
pattern (`Character.sheet`, `Map.grid_settings`, etc.).

### 3.2 Encounter token rules

| Source | Resolved at load to |
|---|---|
| `template_id` set | new `Token` row whose template ref + name come from the template; `controller_user_id = null` |
| `character_id` set | **Skipped** — players keep their own tokens across loads (see §6) |
| Both null (manual) | new `Token` row with `label_override` as name, no template/character link |

Player-controlled tokens (`controller_user_id != null`) are **never**
serialized into an encounter — they're not the GM's to capture.

## 4 — Server endpoints

| Method | Path | Auth | Action |
|---|---|---|---|
| `GET` | `/campaign/{id}/encounters` | GM | List encounters for the GM library UI |
| `POST` | `/campaign/{id}/encounters` | GM | Save the current state as a new encounter. Body: `{name, description?}`. |
| `PATCH` | `/campaign/{id}/encounters/{eid}` | GM | Rename / re-describe. Body: `{name?, description?}`. |
| `POST` | `/campaign/{id}/encounters/{eid}/update` | GM | Re-capture the current state into this encounter (overwrite). |
| `POST` | `/campaign/{id}/encounters/{eid}/load` | GM | Load. Body: `{preserve_player_tokens?: bool = true, start_audio?: bool = true}`. |
| `POST` | `/campaign/{id}/encounters/{eid}/delete` | GM | Delete. |

The two interesting ones (save + load) are detailed in §5–6.

## 5 — Save flow

Triggered by `POST /encounters` (new) or `/encounters/{eid}/update`
(overwrite). Server:

1. Read all current `Token` rows for the campaign where
   `controller_user_id IS NULL` (GM-owned NPCs / monsters / manual
   tokens). Snapshot their position + size + color + label + template
   + hidden state into `payload["tokens"]`.
2. Read the current in-memory initiative state from
   `hub.get_battle(campaign_id)`. Snapshot each combatant into
   `payload["initiative"]`. Link to the snapshotted tokens by index
   when the initiative row references a live token.
3. Capture `Campaign.now_playing_track_id`'s playlist → store as
   `auto_play_playlist_id` if a track is currently playing.
4. Capture the active `Map.id` → store as `map_id`.
5. Insert the `Encounter` row.

Save is a pure snapshot — never mutates live state. Safe to spam.

## 6 — Load flow + edge cases

Triggered by `POST /encounters/{eid}/load`. Two-pass server logic:

### Pass 1 — Clear GM-owned state

- Delete all `Token` rows where `controller_user_id IS NULL` AND the
  campaign matches. **Player tokens are kept** unless
  `preserve_player_tokens=false` is passed (escape hatch for "fully
  reset the map"). Broadcasts a `token_delete` per removed token.
- Clear initiative state via existing battle hub helpers; broadcast a
  fresh `battle_update` with the empty state.

### Pass 2 — Apply the encounter

- If `encounter.map_id` is set, switch active map (existing
  `map_activate` flow + `token_position_clear` broadcasts? — TBD: when
  the active map changes today, do tokens move with it? Need to
  re-check during implementation).
- For each `payload["tokens"]` entry:
  - If `character_id` is set, skip (player will reconnect their own token).
  - Otherwise create a new `Token` row resolving template / overrides.
  - Broadcast `token_add` per token.
- For each `payload["initiative"]` entry: insert into the battle hub
  state, optionally relinking `token_idx` to the freshly-created Token
  ids. Broadcast a single `battle_update`.
- If `auto_play_playlist_id` is set AND `start_audio=true`:
  - Pick the first / random track per `auto_play_mode` (reuse the
    helper landed in v0.58.0).
  - Call `_start_track_for_campaign(..., source="auto_start",
    prev_reason="skipped")` (same path session-start uses).

### Edge cases

- **Map missing / deleted**: `encounter.map_id` is now NULL (FK ON DELETE
  SET NULL). Skip the map switch with a non-fatal warning.
- **Playlist missing**: same — skip audio with a warning, continue load.
- **Token template missing**: a referenced `token_templates` row has been
  deleted. Fall back to a manual token using `label_override` + a default
  color. Logged so the GM can clean up the encounter later.
- **Concurrent loads**: idempotent on the data; broadcasts may multiply
  but clients dedupe on `token_id`. No locking needed for v1.
- **Encounter loaded twice in a row** (no changes between): pass 1
  removes the tokens it just created, pass 2 recreates them with new ids.
  Visually flickers but state ends correct. Optimize later if it bites.
- **Players mid-action**: loading mid-combat is jarring but allowed.
  GMs are expected to use the existing pause/end-session flows before
  swapping encounters. Document, don't enforce.

## 7 — UI surfaces

Two places:

### 7.1 Tabletop — Battle drawer (live use)

A new collapsible `<details>` section under **Token Management** (which
just moved to the Battle drawer in v0.62.0) labeled **Encounters**.
GM-only, with the same gold "GM only" pill pattern.

Content:
```
▼ Encounters                        [GM only]
   ┌──────────────────────────┐
   │ Goblin Ambush            │ [▶ Load] [✎] [🗑]
   │ map: Forest Path · 6 NPCs │
   │ — Notes: stealth start... │
   ├──────────────────────────┤
   │ Cave Boss Fight          │ [▶ Load] [✎] [🗑]
   │ ...                      │
   └──────────────────────────┘
   [💾 Save current state as encounter]
```

Hitting **Save current** opens a small inline form (name + description),
posts to `/encounters`, and the new entry slides into the list. **Load**
fires the two-pass server flow.

### 7.2 Campaign settings — full library

Per the existing pattern (custom subclasses, audio history, etc.), the
campaign settings page gets an "⚔ Encounters" section with the full
library — same list shape but with more space, plus inline edit for
description + a "Duplicate" affordance for variants ("Goblin Ambush —
Dawn", "Goblin Ambush — Night").

The tabletop section is the "use" UI; the settings section is the
"manage" UI.

## 8 — Phasing

Each phase ships as its own MINOR. Estimates assume an undisturbed day
of focused work, not real-world calendar time.

**Phase 1 — Schema + read-only listing (~1 day).**
- Add `Encounter` model + migration (`Schema vNEXT`).
- `GET /encounters` endpoint.
- Campaign settings page renders an empty "Encounters" section ("None
  yet — save your first one from the tabletop").
- Battle drawer Encounters section: render the (empty) list.

**Phase 2 — Save current state (~1 day).**
- `POST /encounters` capture flow.
- "💾 Save current state as encounter" form in the Battle drawer.
- Manual testing: GM sets up tokens + map + initiative, hits save,
  reloads the page → encounter appears in the list with the right name +
  description.

**Phase 3 — Load (~2 days, the hardest one).**
- `POST /encounters/{eid}/load` two-pass flow.
- "▶ Load" button on each encounter row.
- Edge-case handling: missing map / playlist / template (warn + degrade).
- Player-token preservation (`controller_user_id` filter).
- Audio auto-start integration with the existing helpers.

**Phase 4 — Edit / overwrite / delete (~1 day).**
- `PATCH /encounters/{eid}` for name + description.
- `POST /encounters/{eid}/update` to re-snapshot current state into an
  existing encounter (so "Goblin Ambush" can evolve without making a
  new entry every time).
- `POST /encounters/{eid}/delete`.
- Inline edit UI on the campaign settings library section.

**Phase 5 — Quality of life (~1 day).**
- Duplicate-encounter shortcut (POST copies the row with a new name).
- "Preview" tooltip on hover that lists the token names + map name.
- Sort options (recent, alphabetical).
- Optional: tag column for grouping (boss fights / random encounters /
  set pieces).

Total ~6 days of focused work for all five phases. Phases 1–3 are the
MVP — after Phase 3 the feature is usable; Phases 4–5 are polish.

## 9 — Risks

- **Battle hub state is in-memory only.** Initiative entries don't
  survive a process restart today. The encounter snapshot captures the
  in-memory state at save time; loading restores it into memory. After
  Phase 3 this is the same as today: a server restart still loses the
  *current* initiative, but the *saved encounter* survives. If we want
  persistent initiative across restarts, that's a separate feature
  (move `hub._battle` into a DB column on Campaign).
- **Token deletion is loud.** Pass 1 of load broadcasts one
  `token_delete` per removed token, then Pass 2 broadcasts one
  `token_add` per new token. For a 10-NPC encounter that's 20 WS
  messages. Clients handle this fine today, but the visual flicker is
  noticeable. Two mitigations:
  1. Add a `battle_load_begin` / `battle_load_end` WS pair so clients
     can suppress repaint between them.
  2. Add a bulk `tokens_replace` WS message that ships the new token
     list in one go. Bigger refactor, defer to Phase 5.
- **Player-token edge case.** If a player has placed their character
  token on map A, and the GM loads an encounter that switches to map B,
  the player's token's coordinates are now meaningless. Need to
  either (a) preserve the player token but reset its position to a
  sensible default (origin? a "player start" marker?), or (b) move it
  off-canvas until the player picks a new position. **Decision needed
  before Phase 3 starts.**
- **Encounter library hygiene.** Without limits, a busy GM ends up with
  100+ encounters. Phase 5's tag / sort options handle the common case;
  a hard cap isn't necessary.
- **The `tokens` JSON payload can diverge from reality.** Token templates
  evolve (renamed, deleted); a saved encounter pointing at template id
  42 might find that template gone on load. Acceptable — the "missing
  template" edge case in §6 handles it gracefully (manual token +
  warning).

## 10 — Open questions

1. **Player token positions on map switch.** §9 question. Recommend
   option (a): preserve, reset to origin / map-defined start.
2. **Encounter scope: campaign-only, or shareable across campaigns?**
   Recommend campaign-only for v1. The shareable case (an SRD bestiary
   of pre-built encounters) is a different feature.
3. **Audio behavior on load: always start, never start, or per-load
   choice?** Recommend an `start_audio` query param defaulting to true
   on the Load button, with a checkbox in the campaign settings library
   to set the default per encounter.
4. **Naming.** "Encounter" is D&D-flavored. PbtA games might call them
   "scenes". Vaesen calls them "mysteries". Either:
   - Lock the term to "Encounter" and accept the D&D bias, OR
   - Defer this work behind the multi-system refactor (see
     [`multi-system-refactor.md`](multi-system-refactor.md)) so each
     system module can name them locally. **Recommend the former** for
     this feature — `app/systems/*/encounters.py` is a fine future home,
     but a single shared `Encounter` table is fine today.
5. **Encounter creation from outside the tabletop.** Should the GM be
   able to build an encounter from scratch in campaign settings without
   first wiring up tokens on the tabletop? Useful for prep work but
   doubles the UI scope. **Defer to Phase 5 or later.**

## 11 — What this plan deliberately doesn't do

- No "encounter import" from external sources (Pathbuilder, Roll20, etc.).
- No XP / loot tracking per encounter.
- No automated CR balancing.
- No dynamic spawning ("wave 2 of goblins arrives after turn 3").
- No fog-of-war or dynamic lighting tied to encounters.
- No per-player NPC visibility flags beyond the existing global
  `is_hidden` per token.

These can come later; don't pre-build for them.

## 12 — Recommended order of work

```
Phase 1 (~1 day)  → Schema + read-only listing                    ▢ Ready to start
Phase 2 (~1 day)  → Save current state                            ▢
Phase 3 (~2 days) → Load (player-token edge case decided first)   ▢
Phase 4 (~1 day)  → Edit / overwrite / delete                     ▢
Phase 5 (~1 day)  → Duplicate / preview / sort / tags             ▢
```

Resolve **Open question 1** (player-token position on load) before
Phase 3 starts. Everything else can be decided as the implementation
makes the choice concrete.
