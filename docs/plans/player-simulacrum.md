# Player Simulacrum — Design Plan

**Status:** Not started. Design document — no code has shipped.
**Filed in:** v2.49.68 (this plan).
**Related code surfaces:** `app/models.py` (Campaign / Character / CampaignMembership / TokenTemplate / Map), `app/demo_seed.py` (the cloning pattern used by demo reseed), `app/routes/campaign_routes.py` (campaign CRUD + auth), `app/realtime.py` (per-campaign WS hub channels).

---

## Goal

Give a player a **private testing sandbox** — a personal "simulacrum" of the demo tabletop where they can take their character, place demo NPCs as enemies, and exercise abilities (attacks, spells, class features, items) without affecting the main campaign or notifying the GM.

The motivation is teaching + experimentation:

- A new player wants to know what their level-3 Fireball actually does before committing to it in a real combat round. Today the only way is to either (a) ask the GM to set up a side game, or (b) burn a slot in the real session and apologize.
- A veteran player wants to test a homebrew item interaction or a multi-feat combo without confusing the table.
- A returning player who hasn't played their Paladin in months wants to refresh themselves on the Smite + Hex + Divine Smite damage stack.

The simulacrum solves all three with a **per-player, per-character private campaign** that mirrors the demo map + offers the demo NPC templates as placable enemies, fully isolated from the source campaign via the existing campaign-membership auth model.

---

## Interface changes — at a glance

Every UI delta this plan introduces, gathered for a reviewer who wants to scan visually. Per-feature mockups live in the implementation-phases sections below.

| # | Surface | Phase | Where | Change | Visibility |
|---|---|---|---|---|---|
| 1 | **"🧪 Enter Simulacrum" button** | 1 | Character sheet header — next to the existing portrait + name row | Click → POST `/api/character/{cid}/simulacrum/enter`, server creates / finds the per-character sandbox campaign, returns `redirect_url`. | Owning player only (button hidden for other players + GM). |
| 2 | **Simulacrum banner** | 1 | Persistent strip at the top of the tabletop view when inside a simulacrum campaign | "🧪 Simulacrum — your testing sandbox. Nothing here affects the main campaign. [↩ Exit] [🔄 Refresh] [🗑 Reset]" | All viewers of the simulacrum (= only the owning player). |
| 3 | **NPC palette panel** | 2 | New right-drawer tab "🐺 Enemies" alongside the existing Roll Log / Battle / GM Tools tabs (the player is the GM of their sandbox) | List of cloned demo token templates (Bandit, Bandit Captain, Goblin, Thug, Skeleton, Doppelganger). Drag onto the map to place; click → Add to initiative. | Owning player only. |
| 4 | **"Refresh character" button** | 3 | Inside the simulacrum banner | Click → re-clone the source character (latest sheet, full slots, full HP) into the sandbox. Existing sandbox tokens / map state preserved. | Owning player only. |
| 5 | **"Reset map" button** | 3 | Inside the simulacrum banner | Wipe placed NPC tokens + initiative + roll log; map terrain preserved. Useful for "start a fresh fight from the same map." | Owning player only. |
| 6 | **Campaign list affordance** | 3 | The user's campaign list (`/campaigns` page) | Simulacrum campaigns grouped under a collapsed "🧪 Simulacrums" heading at the bottom so the player's main-campaign list isn't cluttered. | Owning player only. |
| 7 | **Sheet exit confirmation** | 1 | When the player clicks "Enter Simulacrum" while another sim is open elsewhere | Modal: "You already have a simulacrum open for [Char Name]. [Switch to it] [Cancel]." | Owning player only. |

> **Privacy by default.** The GM and other players have **no visibility** into the simulacrum — not in the WS fan-out (the simulacrum campaign's hub channel only fans out to its single member), not in the roll log (rolls fired in the sim never broadcast to the source campaign), not in the campaign list (other users can't see the sim because they aren't members). The auth model is the same `CampaignMembership` check that every other endpoint already uses; no new permission system needed.

---

## Constraints surfaced by the codebase

- **Auth model is membership-based.** Every campaign-scoped endpoint already filters by `CampaignMembership.user_id == requester` (or `Campaign.gm_user_id`). A new campaign owned solely by the player automatically inherits this isolation — zero new auth code.
- **Demo data is clone-able.** `app/demo_seed.py` already demonstrates the pattern: `_npc_sheet(slug, label)` for token templates, `_wizard_sheet(name)` etc. for characters, full Map / Token / Campaign rows. The simulacrum clone reuses these helpers.
- **WS hub fans out per-campaign.** `app/realtime.py` keeps a `dict[campaign_id, set[WebSocket]]` so broadcasts in the simulacrum can't leak to the source campaign's channel. Zero new infrastructure.
- **Inline migrations only.** Any schema additions (a `Campaign.is_simulacrum: bool` flag, say) go through `_apply_inline_migrations()` in `app/database.py` + bump `SCHEMA_VERSION`.
- **Every endpoint commit lands harness tests** (`CLAUDE.md`). The simulacrum endpoints get per-commit coverage.
- **44 × 44 px touch targets** (`CLAUDE.md`). The new buttons meet the minimum.

---

## Approaches considered

### A) In-memory shadow state (per-player) — **REJECTED**

A new realtime-hub keyed `dict[user_id, SimulacrumState]` with a parallel set of endpoints (`/sim_attack`, `/sim_cast_spell`, …) that mutate the shadow state instead of the DB.

**Pros:** No DB writes; trivially isolated.
**Cons:**
- Doubles every endpoint (every attack / cast / use_feature has a `/sim_*` twin).
- State lost on container restart.
- Roll log + WS broadcasts need a parallel "sim channel" model.
- Code duplication multiplies the surface area for bugs.

**Verdict:** rejected. Too invasive for too little gain over option B.

### B) Forked campaign on demand — **RECOMMENDED**

The first time a player clicks "Enter Simulacrum" for a given character, the server creates a NEW Campaign row whose `gm_user_id = player.id` + the player as the only member. Clones: their character into the new campaign (`Character.campaign_id` set to the sim), the demo map, the demo token templates. The player is then redirected to the new campaign — every existing endpoint works unchanged. Subsequent entries find the existing sim campaign by `(source_character_id, owner_user_id)` and reuse it.

**Pros:**
- **Zero endpoint changes.** Every cast / attack / move / use_feature / use_item endpoint works because the simulacrum is a real campaign with a real character.
- **State persists** across container restarts.
- **Auth is automatic** — the existing membership check enforces isolation.
- **Reset is cheap** — a single SQL DELETE on the sim campaign + a re-clone.

**Cons:**
- DB bloat: O(N × M) where N = players and M = characters they care about. Each sim is ~1 Campaign + 1 Character + 1 Map + (Token + TokenTemplate count). Mitigated by the "one sim per (character, user)" cap.
- The cloned character's state drifts from the source if the source levels up. Addressed by the explicit "Refresh character" button (#4).
- A user can spawn unlimited simulacrums by creating new characters. Mitigated by the per-character uniqueness constraint (the entry endpoint returns the existing sim instead of creating a duplicate).

**Verdict:** **CHOSEN.** Best leverage on existing infrastructure; no endpoint surface duplicated.

### C) "Sandbox mode" toggle on the character sheet — **REJECTED**

A per-character `sandbox_mode: bool` flag; when set, every endpoint that mutates state (HP, slots, buffs) instead writes to a parallel `sandbox_*` field and broadcasts go to a sim WS channel.

**Pros:** No new campaign rows; state stays on the character.
**Cons:**
- Every endpoint needs a sandbox-mode branch (12+ endpoints).
- Roll log + broadcasts need a separate visibility layer.
- The "Enemies palette" feature (place NPCs) requires sandbox-only tokens that don't exist in the schema.

**Verdict:** rejected — same code-duplication trap as option A.

### D) Replay-style "what-if" preview — **REJECTED**

The player picks an attack / spell, the server simulates the roll + damage + buff install, returns a preview WITHOUT mutating anything.

**Pros:** No new state at all.
**Cons:** Only handles single-action previews. Can't test multi-turn ability stacks (Hex + Smite + Divine Smite on round 2). Doesn't let the player place enemies or test movement.

**Verdict:** rejected — too narrow for the use case.

---

## Chosen approach — detailed design

### Data model

One new boolean column on `Campaign`:

```python
# app/models.py::Campaign
is_simulacrum: Mapped[bool] = mapped_column(
    Boolean, default=False, server_default="false",
    index=True,
)
# Provenance pointers (NULL for non-simulacrum campaigns).
simulacrum_source_campaign_id: Mapped[Optional[int]] = mapped_column(
    ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True,
)
simulacrum_source_character_id: Mapped[Optional[int]] = mapped_column(
    ForeignKey("characters.id", ondelete="SET NULL"), nullable=True,
)
```

`is_simulacrum` gates:

- `/campaigns` list affordance (#6) — sims are visually grouped under a separate heading.
- The simulacrum banner (#2) renders only when `is_simulacrum=True`.
- The "Enemies palette" tab (#3) is shown only when `is_simulacrum=True`.

The source pointers let the "Refresh character" endpoint find the source character even if the player renames their PC mid-sim.

Schema migration: adds the three columns + a unique partial index on `(simulacrum_source_character_id, gm_user_id)` where `is_simulacrum=true` to enforce the "one sim per character per user" rule at the DB level. Goes through `_apply_inline_migrations()` + bumps `SCHEMA_VERSION`.

### Lifecycle

```
                           Player clicks "🧪 Enter Simulacrum"
                                          │
                                          ▼
                         POST /api/character/{cid}/simulacrum/enter
                                          │
                            ┌─────────────┴──────────────┐
                            │                            │
                  ┌─────────▼─────────┐         ┌────────▼────────┐
                  │ existing sim?     │         │   no sim yet?   │
                  │ (source_char_id   │         │   create new    │
                  │  + owner match)   │         │                 │
                  └─────────┬─────────┘         └────────┬────────┘
                            │                            │
                            │                            ▼
                            │             ┌───────────────────────────┐
                            │             │ 1. Create Campaign row    │
                            │             │    is_simulacrum=True     │
                            │             │    gm_user_id=player.id   │
                            │             │ 2. Clone Map (terrain     │
                            │             │    only; no tokens)       │
                            │             │ 3. Clone TokenTemplates   │
                            │             │    (one row per demo NPC) │
                            │             │ 4. Clone Character (full  │
                            │             │    sheet, fresh slots,    │
                            │             │    full HP)               │
                            │             │ 5. Place caster token on  │
                            │             │    the map                │
                            │             └───────────┬───────────────┘
                            │                         │
                            └─────────────┬───────────┘
                                          ▼
                              { redirect_url: "/campaign/{sim_id}" }
                                          │
                                          ▼
                                  Player is in the sim.
                                  Every existing endpoint works.
                                          │
                              ┌───────────┼───────────┐
                              ▼           ▼           ▼
                         🔄 Refresh   🗑 Reset    ↩ Exit
                         char         map         (just redirect)
                         (re-clone    (wipe
                         from source) NPC tokens
                                      + roll log)
```

### Cloning details

- **Map.** New `Map` row with the same `image_url`, `grid_size_px`, `grid_type`. **No tokens** copied from the source. (The player places their own tokens for the sim.)
- **TokenTemplates.** Each demo template (bandit, bandit-captain, thug, goblin-captain, skeleton, doppelganger) gets a new row keyed to the sim campaign. Same `monster_slug` so the SRD overlay resolves identically.
- **Character.** Full sheet copy + reset state: HP at max, all slots at total, resources at full, buffs empty, death_saves cleared. The clone's `owner_user_id = source.owner_user_id`. `campaign_id = sim.id`. Source character pointer stashed on the new Campaign row (not on the Character — characters are 1:1 with campaigns in the model).
- **Caster token.** One `Token` row placed at the map's center pointing at the cloned character.

### Endpoints

```
POST /api/character/{cid}/simulacrum/enter
  Auth: character owner.
  Returns: { sim_campaign_id, redirect_url, was_created: bool }
  Idempotent: re-entering returns the existing sim.

POST /api/campaign/{sim_id}/simulacrum/refresh_character
  Auth: sim owner.
  Re-clones the source character into the sim (preserves token position).
  Returns: { ok, hp_max, slot_totals }
  409 if `campaign.is_simulacrum is False`.

POST /api/campaign/{sim_id}/simulacrum/reset_map
  Auth: sim owner.
  Wipes all NPC tokens from the sim's map + clears its battle state + truncates its roll log.
  Caster token + map terrain preserved.
  Returns: { ok, tokens_removed }

DELETE /api/campaign/{sim_id}/simulacrum
  Auth: sim owner OR admin.
  Cascade-deletes the sim Campaign + Map + Characters + Tokens + TokenTemplates.
  Returns: { ok, deleted_campaign_id }

GET /api/campaign/{sim_id}/simulacrum/enemies
  Auth: sim member.
  Returns the sim's cloned TokenTemplates as a flat list, for the Enemies-palette tab.
  Returns: { templates: [{id, name, slug, ...}, ...] }
```

Existing endpoints (`/attack`, `/cast_spell`, `/use_feature`, `/move`, `/battle`, `/end_buff`, …) work without modification — the simulacrum is a real campaign and the auth check is the existing membership filter.

---

## Mockups

### Mockup — "🧪 Enter Simulacrum" button on the character sheet

```
   Character sheet header (top of /character/{id})

   ┌────────────────────────────────────────────────────────────────────────┐
   │  ┌──────┐                                                              │
   │  │ 🧙   │   Thalindra Moonwhisper                  ┌──────────────────┐│
   │  │      │   Wizard 5 · School of Evocation         │ 🧪 Enter         ││
   │  └──────┘   HP 27/27 · AC 12                       │    Simulacrum    ││
   │                                                    └──────────────────┘│
   └────────────────────────────────────────────────────────────────────────┘

   Visibility:    owning player only.
   Button style:  `min-height: 44px`, `var(--bg-2)` background, `var(--accent)` text,
                  hover/active states identical to the existing "View Sheet" button.
   Tooltip:       "Open a private testing sandbox for this character. The GM and other players
                  won't see what you do here. Nothing here affects the main campaign."
```

### Mockup — Simulacrum banner

```
   Top of the tabletop view in a simulacrum campaign:

   ╔══════════════════════════════════════════════════════════════════════════╗
   ║  🧪  Simulacrum — your testing sandbox. Nothing here affects the          ║
   ║      main campaign.        [↩ Exit] [🔄 Refresh character] [🗑 Reset map] ║
   ╚══════════════════════════════════════════════════════════════════════════╝

   Background:    repeating-linear-gradient(45deg, var(--bg-2), var(--bg-3) 10px)
                  — subtle diagonal tint so it can't be confused with the
                  normal campaign chrome.
   Border-bottom: 1 px dashed var(--accent)
   Height:        44 px (touch-target rule)
   Sticky:        top: 0, z-index 100 — always visible, scrolls with the page.
   Mobile:        the three action buttons collapse into a kebab menu (⋮) on
                  viewports < 600 px.
```

### Mockup — Enemies palette tab

```
   Right drawer in a simulacrum campaign:

   ┌─────────────────────────────────────────┐
   │ Roll Log │ Battle │ 🐺 Enemies │ ⚙ Tools │  ← tab bar (NEW: 🐺 Enemies)
   ├─────────────────────────────────────────┤
   │                                         │
   │  Place enemies on the map               │
   │  ───────────────────────────             │
   │                                         │
   │  ┌──────────────────────────────┐       │
   │  │ 🗡  Bandit            (CR 1/8)│       │
   │  │     d8 HP · AC 12             │ ⊕    │
   │  └──────────────────────────────┘       │
   │  ┌──────────────────────────────┐       │
   │  │ 🗡  Bandit Captain    (CR 2) │       │
   │  │     65 HP · AC 15             │ ⊕    │
   │  └──────────────────────────────┘       │
   │  ┌──────────────────────────────┐       │
   │  │ 🗡  Thug               (CR 1/2)│       │
   │  │     32 HP · AC 11             │ ⊕    │
   │  └──────────────────────────────┘       │
   │  ┌──────────────────────────────┐       │
   │  │ 🏹  Goblin Captain    (CR 1) │       │
   │  │     21 HP · AC 15             │ ⊕    │
   │  └──────────────────────────────┘       │
   │  ┌──────────────────────────────┐       │
   │  │ 💀  Skeleton          (CR 1/4)│       │
   │  │     13 HP · AC 13 · Undead    │ ⊕    │
   │  └──────────────────────────────┘       │
   │  ┌──────────────────────────────┐       │
   │  │ 🎭  Doppelganger      (CR 3) │       │
   │  │     52 HP · AC 14 · charm-imm │ ⊕    │
   │  └──────────────────────────────┘       │
   │                                         │
   │  Drag a row onto the map OR click ⊕     │
   │  to drop in the center.                 │
   │                                         │
   └─────────────────────────────────────────┘

   Each row: 60 px tall, 44 px touch target on the ⊕ button.
   Drag handle: the entire row is draggable; cursor: grab.
   On drop: POST /api/campaign/{sim_id}/token (existing endpoint) with the
            picked template_id + drop coordinates.
```

### Mockup — Enter / switch / refresh / reset flow

```
   Player clicks "🧪 Enter Simulacrum" on the character sheet.

   ┌──────────────────────────────────────┐
   │ POST /character/2/simulacrum/enter   │
   └──────────────────┬───────────────────┘
                      │
            ┌─────────┴──────────┐
            │ was_created=True   │  ─→  Banner: "🧪 Simulacrum created — Thalindra's fresh sandbox."
            │ was_created=False  │  ─→  Banner: "🧪 Welcome back. Last visited 3 hours ago."
            └─────────┬──────────┘
                      │
                      ▼
                  Redirect to /campaign/{sim_id}
```

```
   Player clicks "🔄 Refresh character" in the banner.

   ┌────────────────────────────────────────┐
   │ Modal:                                 │
   │   "Refresh Thalindra from her main     │
   │    campaign sheet?                     │
   │                                        │
   │    HP → 27/27                          │
   │    Slots → L1 4/4, L2 3/3, L3 2/2     │
   │    Buffs cleared                       │
   │                                        │
   │    Map tokens + battle state stay.    │
   │                                        │
   │    [Cancel]  [⚠ Refresh]              │
   │ ────────────────────────────────────── │
```

```
   Player clicks "🗑 Reset map" in the banner.

   ┌────────────────────────────────────────┐
   │ Modal:                                 │
   │   "Clear all enemy tokens from the    │
   │    sandbox map?                        │
   │                                        │
   │    3 tokens will be removed.           │
   │    Initiative cleared.                 │
   │    Roll log cleared.                   │
   │                                        │
   │    Your character + character sheet   │
   │    are untouched.                     │
   │                                        │
   │    [Cancel]  [⚠ Reset]                │
   └────────────────────────────────────────┘
```

---

## Implementation phases

| Phase | Scope | Estimated LOC | Harness tests |
|---|---|---|---|
| **1** | Schema migration + 2 endpoints (`/enter` + `/refresh_character`) + character/map/template cloning helpers + "Enter Simulacrum" button on the sheet + Simulacrum banner | ~600 server, ~150 client | 4–6 (enter creates sim, enter idempotent on re-entry, refresh re-clones sheet state, isolation guarantee — rolls in sim don't broadcast to source) |
| **2** | Enemies palette tab + drag-to-place wiring + `GET /simulacrum/enemies` endpoint | ~200 server, ~300 client (drawer tab + drag logic) | 2–3 (enemies list returns the cloned templates, dropped token uses sim's TokenTemplate IDs not source IDs) |
| **3** | `/reset_map` endpoint + `DELETE` cleanup + the "🧪 Simulacrums" group in `/campaigns` list + the "switch to existing sim" modal | ~150 server, ~100 client | 3–4 (reset clears tokens + battle + roll log but preserves character, delete cascades, campaign-list grouping, switch-existing-sim modal correctness) |

Phase 1 is shippable alone — the player can enter their sim, mess around with attacks against their own token, refresh state. Phase 2 unlocks the "place enemies" workflow. Phase 3 polishes.

---

## Open questions

1. **Should levels-up auto-refresh the sim?** When the source character gains a level (the GM clicks "Award XP" in the main campaign), should the sim re-clone automatically, or require the player to click "Refresh"? **Recommendation:** require explicit refresh. Auto-clobbering an in-progress test would be hostile. The banner's "Last refreshed: X" timestamp helps the player notice drift.
2. **Should sims be deletable on character delete?** If the source character is deleted, what happens to the sim? **Recommendation:** ON DELETE SET NULL on `simulacrum_source_character_id` (the schema spec above). The sim stays alive as a "snapshot" — the player can still play in it, just can't refresh from source any more. Add a banner warning when source_character_id is NULL.
3. **Should the GM be able to peek?** RAW spirit of the feature: no. But there could be a flag a campaign admin sets to allow "GM may view player sims for debugging." **Recommendation:** no GM peek in v1. If a player wants help, they invite the GM as a member (existing flow) — that's the explicit consent path.
4. **How many sims per user?** Hard cap or soft? **Recommendation:** one sim per (character, user) pair, enforced at the unique-partial-index level. A user with 4 characters can have 4 sims, but not 8. Prevents spam.
5. **Roll-log isolation.** RollRecord rows are scoped to a campaign already. Confirm that no shared global table leaks rolls across campaigns. **Recommendation:** verified during Phase 1 via a harness test (`test_simulacrum_rolls_dont_leak`).
6. **Demo dependency.** The plan clones the demo map + demo TokenTemplates. What if demo mode is off (production deployment without demo seeding)? **Recommendation:** the entry endpoint 409s with `"error": "no_demo_assets"` if the user's home campaign has no map / templates. A future version could let the user pick which campaign's map to clone from (e.g., their main campaign's map).
7. **Token sprites / portraits.** Cloning a TokenTemplate copies the `image_url` field but the actual blob lives on disk under `uploads/`. **Recommendation:** for v1, share the blob (both rows point at the same file). On delete-cascade, only the sim's TokenTemplate row goes; the file stays for the source.

---

## Filed (out of scope here)

- **Multi-character sims.** Today: one sim per character. Future: a sim with multiple cloned characters so the player can test party-vs-party scenarios.
- **Save / load encounter snapshots.** Future: the player can save a fight setup ("3 bandits + a captain") and reload it.
- **Share simulacrum with another player.** Future: a player invites a friend to their sim to test ability interactions (e.g., Hexblade's Curse + Divine Smite stack). The membership model already supports this trivially; just needs a UI affordance.
- **GM "view player sim" tool.** Filed in Open Question #3.
- **Per-action "what-if" preview** (rejected approach D) — could resurface as a quick-test feature INSIDE the sim banner: "Try this action without committing." Lower priority since the sim itself solves the use case.
- **Rate-limit on `/enter`.** A user could thrash the create-sim path. Filed if it surfaces as abuse; for v1, the per-character uniqueness constraint is the practical limit.

---

## File-path index (for the implementation agent)

| File | Section to touch | Why |
|---|---|---|
| `app/models.py::Campaign` | Add `is_simulacrum`, `simulacrum_source_campaign_id`, `simulacrum_source_character_id` | Phase 1 schema |
| `app/database.py::_apply_inline_migrations` | New migration block; bump `SCHEMA_VERSION` | Phase 1 schema |
| `app/routes/campaign_routes.py` (or new `app/routes/simulacrum_routes.py`) | 5 new endpoints | Phase 1–3 |
| `app/demo_seed.py` | Reuse `_npc_sheet`, character-sheet helpers via a new shared cloning helper | Phase 1 |
| `app/templates/character_sheet.html` (or wherever the sheet header lives) | "🧪 Enter Simulacrum" button | Phase 1 |
| `app/templates/tabletop.html` | Simulacrum banner partial (gated on `campaign.is_simulacrum`) + new Enemies tab | Phase 1–2 |
| `app/static/tabletop.js` | Enemies palette drag-to-place wiring | Phase 2 |
| `tests/harness/test_simulacrum_*.py` (NEW files) | Per-endpoint + isolation tests | Phase 1–3 |
| `docs/wiki/README.md` + `app/templates/wiki.html` + `app/routes/wiki_routes.py::_DOC_ALLOWLIST` | Surface this plan via the wiki | This commit |

---

## Decision log

- **Forked campaign per (character, user)** — chosen over in-memory shadow + sandbox-mode toggle because it inherits the existing auth + WS + endpoint surface with zero duplication.
- **`is_simulacrum` boolean + source pointers** — minimal schema change; everything else is regular Campaign / Character / Map / Token / TokenTemplate.
- **Player is the GM of their own sim** — they get the existing GM Tools tab + the new Enemies palette. No new permission tier needed.
- **No GM peek in v1** — privacy by default; the player can invite the GM as a member if they want help.
- **One sim per (character, user)** — enforced at the unique-partial-index level; prevents row spam.
- **Explicit "Refresh" rather than auto-sync** — protects the player's in-progress experiments from being clobbered by upstream character changes.
- **Persistent banner with three actions** (Exit, Refresh, Reset) — keeps the privacy story visible and the recovery actions one tap away.
