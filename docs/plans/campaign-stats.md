# Per-Campaign Statistics Logging — Design Plan

**Status:** ✅ shipped end-to-end (v2.650.0–v2.652.0). Phase 1 (v2.650.0): the
`campaign_stat_events` table (schema v81) + the damage capture Hook A + reseed
wiring. Phase 2 (v2.651.0): the read API `GET /api/campaign/{id}/stats`
(own-vs-GM gated) + `stats_service.py` + the heal/cast/attack capture hooks
(B/C/D). Phase 3 (v2.652.0): the `/campaign/{id}/stats` page + the `📊 Stats`
nav pill. Lay on Hands heal capture added v2.652.1. Optional follow-ups (filed
below): other heal-endpoint capture (Healing Word, etc.), NPC-cast tracking,
charts/leaderboard, and a retention rollup. A
player-facing stats page
showing damage dealt/taken, healing, attacks + hit-rate, crits, KOs, biggest
hit, and most-used spells — per campaign, with a per-session breakdown.

## Product decisions (locked)

- **Scope:** per-campaign. "In *this* campaign, your character has dealt X
  damage." Not cross-campaign.
- **Visibility:** each player sees their **own** character's stats; the **GM
  sees everyone's**. Rides the existing campaign-membership / GM gating
  (`_user_can_view_campaign`, `_user_is_gm`, `char.owner_user_id`).
- **Depth:** an **event log** (a new table), so the feature gives both lifetime
  totals AND a per-session / over-time breakdown. Requires a schema migration.
- **Surface:** its own page, `GET /campaign/{id}/stats`.

## Substrate (verified in code, 2026-06-25)

| Thing | Where |
|---|---|
| Damage funnel (the single capture point) | `_apply_damage_to_combatant(db, campaign_id, combatant, damage_amount, damage_type, *, is_crit, is_attack, attack_id, is_magical, is_spell, attacker_char_id, is_ranged_weapon_attack)` — async, `tabletop_routes.py`. Returns `{applied, hp_before, hp_after, is_dying, is_dead, …}`. PC branch → `_apply_hp_change`; NPC branch mutates hub `hp_current`. |
| PC vs NPC discriminator | `combatant.get("char_id")` truthy = PC (has a `Character` row); falsy = NPC. |
| HP/heal choke | `_apply_hp_change(char, new_current, *, is_damage=False, …)` (sync). Heal = `is_damage=False` and `new_current > old_current`. NPC heals: `_apply_heal_to_combatant`. |
| Attack endpoint | `POST .../attack` → `use_attack`; broadcasts `weapon_attack` with `caster_char_id`, `hit`, `is_crit`, `damage_applied`. |
| Cast endpoint | `POST .../cast_spell`; payload carries `caster_char_id`, `spell_name`, `spell_level`; slug via `spell.get("_slug")`. `npc_cast_spell` sibling. |
| Event-log model precedent | `AudioPlayEvent` (`models.py:583`) — one-row-per-event: indexed `campaign_id` FK CASCADE, nullable FKs `SET NULL` + snapshot name columns, indexed timestamp. **Mirror this.** |
| Migration mechanism | `_apply_inline_migrations()` in `database.py` (latest block **v80**). New table → block **v81**, bumping `SCHEMA_VERSION` 80→81. Use `Model.__table__.create(bind=engine, checkfirst=True)` + a belt-and-suspenders `CREATE TABLE IF NOT EXISTS`. |
| Reseed wipe | `wipe_campaign_children(db, campaign_ids)` (`campaign_wipe.py`) deletes child rows by `campaign_id`. **The new table must be added here** so demo reseed purges stats. |
| Session boundary | `Campaign.session_started_at` (`models.py:246`, schema v6) — set when the GM hits Start Session. Use it as the per-session bucket key (no new schema). |
| Permission helpers | `_user_can_view_campaign(db, user, campaign)`, `_user_is_gm(user, campaign, db)`, ownership via `char.owner_user_id == user.id`. |

## Data model — `campaign_stat_events`

New model `CampaignStatEvent` in `app/models.py`, mirroring `AudioPlayEvent`:

- `id` PK.
- `campaign_id` — FK `campaigns.id` CASCADE, **indexed**.
- `actor_char_id` — FK `characters.id` SET NULL, **nullable, indexed** (the PC who dealt/cast/healed; NULL for NPC actors).
- `actor_name` — `String(120)` snapshot (survives rename/delete; identifies NPC actors).
- `target_char_id` — FK `characters.id` SET NULL, **nullable, indexed**.
- `target_name` — `String(120)` nullable snapshot.
- `event_type` — `String(24)`, **indexed**. v1 values: `damage_dealt`, `damage_taken`, `heal_done`, `heal_received`, `spell_cast`, `attack`, `ko`. Plain lowercase string (not a DB enum — matches the codebase + avoids ALTER-TYPE on later additions).
- `amount` — `Integer` nullable (HP for damage/heal; NULL for cast/attack).
- `damage_type` — `String(24)` nullable.
- `spell_slug` — `String(80)` nullable (stable grouping key).
- `spell_name` — `String(120)` nullable (display snapshot).
- `is_crit` — `Boolean` default False.
- `is_hit` — `Boolean` nullable (only `attack` events set it → hit-rate).
- `session_key` — `String(40)`, **indexed** (the `session_started_at` ISO stamp at capture time; fallback = `created_at` UTC date when NULL).
- `created_at` — `DateTime` `server_default=func.now()`, **indexed**.

Indexes (`__table_args__`): `(campaign_id, actor_char_id)`, `(campaign_id, session_key)`, `(campaign_id, event_type)`.

**Event-log only for v1** (no redundant aggregate table). Aggregates derive from the log; the reverse doesn't. A materialized `campaign_stat_totals` rollup is a *filed* optimization, only if a long campaign's page query gets slow.

**Storage growth.** Low-thousands of events per combat-heavy session; tens-of-thousands per campaign — trivially indexed in Postgres. Unbounded over a campaign's life (esp. damage events); a `session_key`-based rollup-and-prune job is **filed**, not v1.

## Capture hooks

Principle: **log inline in the transaction the caller already commits, best-effort.** Each hook calls a `_log_stat_event(db, campaign_id, …)` helper that swallows-and-logs exceptions so a stats bug can never 500 combat. One extra INSERT on an already-committing path — cheaper + transactionally consistent vs a deferred queue.

- **Hook A — `_apply_damage_to_combatant` (the funnel).** The *only* damage capture point (so `use_attack`/`npc_attack`/`attack_spell`/cast-attack-branch/riders never double-count). When `applied > 0`: log `damage_dealt` (actor = `attacker_char_id`) and, if the target is a PC, `damage_taken` (actor = target). On `became_dead`/`is_dead`: log `ko`. (`damage_dealt` + `damage_taken` are two rows for one hit **by design** — different stats, filtered by `event_type`; a code comment must say so to stop a future "dedupe".)
- **Hook B — heal sites.** Capture at the **call sites** where caster identity is known (cast-spell auto-heal, `use_lay_on_hands`, etc.) — not inside `_apply_hp_change` (no campaign/caster there). Shared `_log_heal_event(...)` logs `heal_done` (caster) + `heal_received` (target).
- **Hook C — `cast_spell` / `npc_cast_spell`.** After the payload, one `spell_cast` (actor, `spell_slug`, `spell_name`). Damage/heal riders are Hooks A/B — so a damage cantrip = `spell_cast` + `damage_dealt` (correct).
- **Hook D — `use_attack`.** After the `weapon_attack` broadcast, one `attack` event (`is_hit`, `is_crit`). Damage is **not** logged here (Hook A owns it).

**NPC actor policy:** only store PC-anchored events. PC→NPC logs `damage_dealt` (PC actor); NPC→PC logs `damage_taken` (PC target, `actor_name` = monster). NPC `damage_dealt` and NPC casts are **not** stored in v1 (no PC-facing home; would bloat with monster HP). Filed.

## Read layer

New `app/stats_service.py` (keeps `tabletop_routes.py` lean, unit-testable):
`character_totals`, `character_top_spells(limit=5)`, `character_by_session`, `campaign_totals` (per-character roll-up for the GM). SQL `SUM/COUNT … FILTER (WHERE event_type=…)` + `GROUP BY spell_slug` / `session_key`.

**API:** `GET /api/campaign/{id}/stats?character_id=` — 404 unknown campaign, 403 non-member. **Visibility gate:** GM may pass any `character_id` (or omit → campaign roll-up); a non-GM is resolved server-side to *their own* characters and a request for another player's `character_id` returns their own data (never another's numbers), mirroring `_filter_roll_for_user`. Response: `{scope, characters:[{id, name, totals, top_spells, by_session}]}`.

## The page

`GET /campaign/{id}/stats` → `campaign_stats.html` (modeled on `campaign_settings`, gated by `_user_can_view_campaign`). Fetches the API client-side (vanilla JS).
- **v1 cards:** damage dealt / taken, healing done / received, attacks + hit-rate %, crits, KOs, biggest single hit, top-5 spells.
- **Per-session table:** one row per `session_key`.
- **Player view:** own character(s) only. **GM view:** a roster `<select>` switcher + a campaign-wide totals table.
- **Nav:** a `📊 Stats` quick-link pill in `tabletop.html` (all members); a back-link in `campaign_stats.html`.
- **Filed (v2):** charts/sparklines, an MVP leaderboard, a damage-type pie.

## Phasing (one bump = one commit = one push = one rebuild)

1. **Schema + model + Hook A + reseed wiring** (MINOR, `SCHEMA_VERSION` 80→81). `CampaignStatEvent`, migration v81, `wipe_campaign_children` add, `_log_stat_event` + Hook A. No endpoint/page yet — ships persistence + the hardest hook with nothing user-facing to break. Harness: `test_stats_capture.py` (assert the attack still succeeds; positive aggregate deferred to #2's API).
2. **Read API + Hooks B/C/D** (MINOR). `stats_service.py`, `GET /api/campaign/{id}/stats` with the visibility gate. Harness: `test_stats_api.py` (happy: damage/cast reflected; error: a player can't read another's stats; 403 non-member, 404 unknown campaign).
3. **Page + nav** (MINOR). `campaign_stats.html` + route + nav pill. Harness: renders 200 for GM + member, 403 for non-member.
4. **(this doc)** — surfaced through the wiki on creation.

## Risks

- **Hot-path latency** — one INSERT on the already-committing damage/attack/cast paths; best-effort try/except. A deferred queue is filed if profiling later shows cost.
- **Double-counting** — damage captured *only* in the funnel; attacks log the attack only; casts log the cast only. The two-rows-per-hit (`damage_dealt` + `damage_taken`) is intentional and must be code-commented.
- **NPC actors** — no `Character` row → NULL `actor_char_id`, snapshot `actor_name`; only PC-anchored events stored.
- **Session boundary** — `Campaign.session_started_at` is the bucket key; date-bucket fallback when NULL. (A `Battle` proxy was rejected — battles are one-per-campaign and reload, so they don't delimit sessions.)
- **Backfill** — none; stats start empty at ship (no historical events). Expected.
- **Reseed idempotency** — the new table is in `wipe_campaign_children`, so each 60-min demo reseed starts clean (else harness assertions drift).
- **Storage growth** — unbounded over a campaign's life; rollup/retention filed.

## Cross-references

- `app/models.py` — `AudioPlayEvent` (the event-log precedent) + `Campaign.session_started_at`.
- `app/routes/tabletop_routes.py` — `_apply_damage_to_combatant` (Hook A), `cast_spell` (Hook C), `use_attack` (Hook D), the permission helpers.
- `app/campaign_wipe.py` — `wipe_campaign_children` (reseed idempotency).
- `app/database.py` — `_apply_inline_migrations` (migration v81).
