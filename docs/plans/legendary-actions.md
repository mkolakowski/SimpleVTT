# Legendary actions + lair actions — design plan

**Status:** 🟠 Phases 1a + 1b + 1c (UI) shipped (re-audited 2026-06-11,
v2.160.0) — the budget surface + GM control are live:
- **Phase 1a ✅ v2.159.33** — cost-integer backfill across 30 monsters
  (39 actions).
- **Phase 1b ✅ v2.159.34** — combatant `legendary_actions = {max, current}`
  field + turn-start refresh hook in the `/battle` PUT handler +
  `POST /api/campaign/{cid}/use_legendary_action` endpoint (GM-only,
  own-turn gate, pool-cost gate, decrement, broadcasts
  `legendary_action_pool_update` + `feature_used`).
- **Phase 1c (UI) ✅ v2.160.0** — GM init-tracker legendary-action strip:
  pool meter (👑 ●●● 3/3) + a click-to-spend button per option (cost
  pill, own-turn + insufficient-points disable), wired to the
  /use_legendary_action endpoint, with a `legendary_action_pool_update`
  WS handler driving the meter live. 3 Playwright UI tests.
- **Phase 1c demo fixture ✅ v2.160.1** — the Adult Red Dragon (CR 17,
  legendary) is now a drag-spawnable demo template, so the v2.160.0
  strip has a real legendary creature to render on (the demo's existing
  Young Red Dragon is non-legendary RAW). 2 HTTP harness tests guard
  the seed wiring.

- **Phase 1c (server save-AoE) ✅ v2.161.0** — `/use_legendary_action`
  now resolves the spent action's definition from the monster template
  (`_resolve_legendary_action_def`) and, when it carries a `save_ability`
  + `damage` and the caller passes `aoe_target_combatant_ids`, rolls each
  target's save server-side (`_resolve_feature_save`) and applies
  save-or-take damage (`_apply_damage_to_combatant`), broadcasting
  `legendary_action_aoe_resolved`. Validated against the Adult Red
  Dragon's Wing Attack (cost 2, DEX DC 22, 2d6+8 bludgeoning). 2 HTTP
  harness tests.

- **Phase 1c (UI target-pick) ✅ v2.162.0** — the strip's spend button
  for a save-AoE legendary action (Wing Attack — carries `save_ability`
  + `damage`) now opens `vttOpenMultiTargetPicker` so the GM clicks the
  caught creatures, then folds the picked ids into the
  `/use_legendary_action` POST as `aoe_target_combatant_ids`. Cancel
  aborts the spend. Non-AoE options spend straight through. 2 Playwright
  tests.

- **Phase 1c (chat card) ✅ v2.163.0** — the `legendary_action_aoe_resolved`
  broadcast now renders a 👑 roll-log card
  (`_appendLegendaryAoeResolved` in `tabletop.js`) naming the creature +
  action + save line, with one pill per target (✅ saved / ❌
  failed-with-damage / ⏳ pending PC save). Persists + hydrates like the
  other WS-only cards. 1 Playwright test.

- **Phase 1c (server reference-attack) ✅ v2.164.0** — `/use_legendary_action`
  now resolves a reference-attack legendary action (Tail Attack → base
  "Tail" action, +14 / 2d8+8) via `_resolve_reference_attack_base_action`,
  rolls 2d20kh1+attack_bonus vs the target's AC, applies (crit-doubled)
  damage on a hit, and broadcasts `feature_used(source=legendary-action-attack)`.
  The response gains an `attack_result` field. 2 harness tests. **Phase 1c
  is now complete.**

The data shapes turned out more varied than the original "attack_roll +
damage" assumption: the demo dragon's legendary options are a save-AoE
(Wing Attack), a reference-attack (Tail Attack → base "Tail" action), and
a no-damage utility (Detect). v2.161.0–v2.164.0 cover all of them: the
save-AoE slice end-to-end (server dispatch + UI target-pick + chat card)
and the reference-attack dispatch. Phase 1c is closed.
**Authors:** rolling
**Last updated:** 2026-06-11

A plan to wire the legendary-action + legendary-resistance + lair-action
mechanics for the **30** SRD monsters that ship with the relevant data.
(The original Phase 0 filing cited "15 monsters" — that count was for
the un-suffixed legendary creature roster; including the 10 Adult
dragons, Aboleth, Gynosphinx, and the original 17 unique creatures
the real count is 30 monsters and 39 multi-cost actions. The Phase 1a
data backfill in v2.159.33 surfaced the larger roster.)
Today a GM running an ancient dragon, lich, vampire, tarrasque, kraken,
mummy lord, solar, sphinx, or unicorn has to track all three of those
mechanics by hand — the engine surfaces the data via `/templates` but
has no dispatch endpoint, no per-round action-point budget, and no
legendary-resistance pool that auto-applies to failed saves.

This is the single largest un-planned SRD surface left after the
2026-06-11 audit closed magic-items-automation + exhaustion-levels.

---

## RAW (SRD 5.1 / DMG p.11 + per-monster stat blocks)

### Legendary actions

- A legendary creature has a pool of **legendary action points** —
  default 3 per round; some monsters have 1 or 2.
- The pool **refreshes at the start of the legendary creature's
  turn** (i.e. they're spent over the round between the creature's
  own turns, on other creatures' turns).
- Spent **only at the end of another creature's turn**, never on the
  creature's own turn, and never if the creature is incapacitated.
- Each option in the legendary-action list has a **cost** (1, 2, or
  3 points). Cost is encoded in the action name as "(Costs N Actions)"
  in the SRD text; the data layer normalises everything to `cost: 1`
  today (see [Open question 1](#open-questions) below).

**Per-monster pools (SRD 5.1):**

| Monster | Pool | Options (cost) |
|---|---|---|
| Ancient Red/Silver/Gold/Bronze/Copper/Green/White Dragon | 3 | Detect (1) / Tail Attack (1) / Wing Attack (2) |
| Lich | 3 | Cantrip (1) / Paralyzing Touch (2) / Frightening Gaze (2) / Disrupt Life (3) |
| Vampire | 3 | Move (1) / Unarmed Strike (1) / Bite (2) |
| Tarrasque | 3 | Move (1) / Chomp (1) / Tail Attack (2) / Frightful Presence (2) |
| Kraken | 3 | Tentacle Attack or Fling (1) / Lightning Storm (2) / Ink Cloud (3) |
| Mummy Lord | 3 | Attack (1) / Blinding Dust (2) / Blasphemous Word (2) / Channel Negative Energy (2) / Whirlwind of Sand (2) |
| Solar | 3 | Teleport (1) / Searing Burst (2) / Blinding Gaze (3) |
| Androsphinx | 3 | Claw Attack (1) / Teleport (2) / Cast a Spell (3) |
| Unicorn | 3 | Hooves (1) / Shimmering Shield (2) / Heal Self (3) |

### Legendary resistance

- A pool of **N uses per day** (default 3; SRD-correct for every
  monster on the roster above except Solar = 3 and Unicorn = 0).
- On a **failed save** the creature may choose to succeed instead;
  decrement the pool by 1.
- Today's data shape: `category: "special_ability"` entry named
  e.g. `Legendary Resistance (3/Day)` — the count lives in the name
  string. The endpoint that triggers on save-fail needs to parse
  that to seed the per-monster pool (or the data layer grows a
  structured `legendary_resistance_per_day` integer; filed Phase 0).

### Lair actions

- A legendary creature in its **lair** acts on **initiative count
  20** (losing initiative ties) — a separate slot in the round.
- Picks one of 2-3 thematic effects (typically a save-required AoE
  or environment manipulation).
- **Cannot be used in the round the creature enters initiative.**
- Today's data shape: ⚪ **no lair_actions data ships on any monster
  JSON** — neither as a top-level array nor as `category: "lair_action"`
  inside the unified `actions` array. Phase 2 lands the data first.

---

## Why this matters

A GM running the climactic ancient-red-dragon fight today:

1. Manually checks "wait, can the dragon legendary-action right now?
   It's the rogue's turn ending..."
2. Spends one of three points tracked on a napkin.
3. Decides the wing attack costs 2 by reading the parenthetical in
   the action name.
4. When the party Wizard lands Hold Monster on the dragon, GM looks
   at the stat-block special-ability list, sees "Legendary
   Resistance (3/Day)," asks "do I want to burn one?" and
   decrements another napkin counter.
5. If the fight is in the dragon's volcanic lair, GM checks
   initiative-count-20 trigger for the "magma erupts" lair-action
   AoE, decides which of three options to fire, has every PC roll
   a DEX save by hand.

All five of those are RAW-implementable on existing engine
primitives:

| Need | Existing primitive |
|---|---|
| Action dispatch | `/npc_attack` + `/npc_cast_spell` + the `_apply_damage_to_combatant` pipeline |
| Per-round budget | `combatant.economy` action/bonus/reaction pattern (v2.49.x) — add `legendary_actions: int` field |
| Refresh timing | turn-start hook in the initiative-advance flow (`/next_turn` already broadcasts `turn_changed`) |
| Resistance pool | `combatant.resources` pattern (mirror of PC class resource trackers) |
| Save-fail interception | the save-resolution sites already exist (`_resolve_npc_save` etc.) — branch on pool > 0 |
| Lair-action initiative slot | the existing initiative-tracker UI's "count" sort — add a synthetic "Lair" entry pinned to 20 |
| Lair-action AoE | the v2.158.x AoE dispatch templates (line/sphere/cone) the magic-items-Phase-8 work shipped |

This plan is **routing + a small data backfill**, not new
infrastructure.

---

## Design

### Data shape

**Legendary actions** (already in the data layer per the unified
`actions` array — `category: "legendary_action"`):
- The cost field today is uniformly `cost: 1`. Phase 0 backfills
  the cost integer (1/2/3) by parsing the "(Costs N Actions)"
  suffix in the SRD action names. ~7 actions across the 15 monsters
  carry a "Costs 2" or "Costs 3" suffix.

**Legendary resistance** (currently `special_ability` with the count
in the name string):
- Phase 0 also adds a structured `legendary_resistance_per_day: int`
  field at the monster top level so the endpoint doesn't need to
  parse the action name.

**Lair actions** (NEW):
- Add `lair_actions: list[Action]` at the monster top level (or
  unified as `category: "lair_action"` inside `actions`). Either
  shape is fine — `category` is slightly more uniform but the
  top-level array gives a cleaner allowlist for the initiative-20
  scheduler. Decision filed under [Open question 2](#open-questions).
- Backfill data for the 15-monster legendary roster from SRD 5.1.

### Per-combatant state

```python
combatant.legendary_actions = {
    "max": 3,
    "current": 3,           # decremented per spend; refreshed at turn start
}
combatant.legendary_resistance = {
    "max": 3,               # parsed from special_ability name or new field
    "current": 3,           # decremented per save-fail spend; per-day
}
```

### New endpoints

| Endpoint | Body | Behavior |
|---|---|---|
| `POST /api/campaign/{cid}/use_legendary_action` | `combatant_id, action_id, target_combatant_id?, save_dc?` | Verify `current >= cost`; verify it's NOT the legendary creature's turn; decrement; dispatch through `_apply_damage_to_combatant` (for attacks) or save-resolver (for AoE); broadcast `feature_used(source=legendary-action)` + `economy_update`. |
| `POST /api/campaign/{cid}/spend_legendary_resistance` | `combatant_id` | Verify pool > 0; decrement; convert the pending failed save to a success (or just return the pool decrement for the GM to apply when the auto-save plumbing lands); broadcast `feature_used(source=legendary-resistance)`. |
| `POST /api/campaign/{cid}/trigger_lair_action` | `combatant_id, action_id, target_combatant_ids?[]` | Verify the legendary creature is in combat + in its lair (GM toggle on the encounter); dispatch as AoE save through the v2.158.x AoE templates; broadcast `lair_action_used`. |

### Refresh wiring

- `/next_turn` (already exists) — on turn change, find the
  legendary creature(s) whose turn is just *starting* and reset
  their `legendary_actions.current = max`. Mirror the per-PC
  reaction-refresh pattern (v2.49.x).
- `rest_*` endpoints — long rest refills `legendary_resistance.current`
  to max.

### Initiative-count-20 lair scheduler

- The initiative-tracker UI already sorts by initiative count.
- Add a synthetic `{combatant_type: "lair", monster_id: <legendary>,
  initiative: 20}` entry when a legendary creature is in combat
  and the encounter is flagged "in lair."
- Skip the slot in the round the creature was first added (RAW).
- When the slot's turn fires, broadcast `lair_action_prompt` to the
  GM with the available `lair_actions` list; GM picks one (or
  randomises); `trigger_lair_action` dispatches it.

---

## Phasing

### Phase 0 — Plan (this doc) ✅ v2.159.32

- This commit. Files the plan, wires it through the wiki (allowlist
  + landing-page row + per-slug harness test + `test_wiki_home_renders`
  update).
- No engine work; no schema change; no new endpoint.

### Phase 1 — Legendary action point budget + dispatch (M, ~3 commits)

- **Phase 1a ✅ v2.159.33** — data backfill. Parsed "(Costs N Actions)"
  suffix from 39 multi-cost legendary actions across 30 monsters and
  updated the `cost` integer (1/2/3) in each monster JSON. New harness
  `test_monster_legendary_action_cost.py` (4 tests) guards the
  invariant against future SRD-rebuild drift. Breakdown:
  - 20 dragons (Adult + Ancient × 10 colors) — Wing Attack cost 2.
  - Aboleth — Psychic Drain (2).
  - Solar — Searing Burst (2) / Blinding Gaze (3).
  - Kraken — Lightning Storm (2) / Ink Cloud (3).
  - Lich — Paralyzing Touch (2) / Frightening Gaze (2) / Disrupt Life (3).
  - Sphinx (Andro + Gyno) — Teleport (2) / Cast a Spell (3).
  - Vampire — Bite (2). Tarrasque — Chomp (2).
  - Mummy Lord — Blasphemous Word (2) / Channel Negative Energy (2) / Whirlwind of Sand (2).
  - Unicorn — Shimmering Shield (2) / Heal Self (3).
- **Phase 1b ✅ v2.159.34** — `combatant.legendary_actions = {max, current}`
  field + turn-start refresh hook in the `/battle` PUT handler +
  `POST /api/campaign/{cid}/use_legendary_action` endpoint (GM-only,
  own-turn gate, pool-cost gate, decrement). 7 harness tests
  (`test_use_legendary_action.py`) — cost-1 spend / cost-2 spend /
  own-turn 409 / insufficient-pool 409 / turn-start refresh / 400
  missing-id / 403 non-GM. Broadcasts `legendary_action_pool_update`
  (data: combatant_id + max + current + reason ∈ {spent,
  turn_start_refresh} + cost?) + `feature_used(source=legendary-action)`.
  Damage dispatch deferred to Phase 1c — Phase 1b is a budget gate
  only; the client (or a future commit) follows up with a regular
  `/npc_attack` call for attack-shape actions.
- Phase 1c (UI) ✅ v2.160.0: initiative-tracker legendary-action strip
  (pool meter + per-option spend buttons) in `app/templates/tabletop.html`
  — `_ensureLegendaryActions` seed helper, `.legendary-strip` render,
  click → `/use_legendary_action`, `legendary_action_pool_update` WS
  handler, 3 Playwright UI tests (`test_legendary_action_buttons.py`).
- Phase 1c (server save-AoE) ✅ v2.161.0: `/use_legendary_action`
  resolves the spent action def from the monster template
  (`_resolve_legendary_action_def`); when it has `save_ability`+`damage`
  and the caller passes `aoe_target_combatant_ids`, loops the targets
  (spender excluded), rolls each save via `_resolve_feature_save`
  (caster_char_id=0, source=legendary-action-save), applies save-or-take
  damage via `_apply_damage_to_combatant` (is_attack=False), and
  broadcasts `legendary_action_aoe_resolved` (data: combatant_id +
  combatant_name + action_id + action_name + save_ability + save_dc +
  damage_type + results[]). 2 HTTP tests
  (`test_wing_attack_aoe_resolves_saves_and_damage`,
  `test_wing_attack_without_targets_skips_dispatch`).
- Phase 1c (UI target-pick) ✅ v2.162.0: the strip's save-AoE spend
  button (`data-is-save-aoe`, set when the option has `save_ability` +
  `damage`) opens `vttOpenMultiTargetPicker` before POSTing, folding the
  picked combatant ids into `aoe_target_combatant_ids`; cancel aborts the
  spend. `_ensureLegendaryActions` now carries `save_ability` + `damage`
  onto each option. 2 Playwright tests
  (`test_wing_attack_save_aoe_opens_picker_and_posts_targets`,
  `test_wing_attack_save_aoe_picker_cancel_aborts_spend`).
- Phase 1c (chat card) ✅ v2.163.0: `_appendLegendaryAoeResolved` in
  `tabletop.js` renders the `legendary_action_aoe_resolved` broadcast as
  a 👑 `.feature-used-card` roll-log entry with per-target pills
  (`chip-hit` saved / `chip-miss` failed-with-damage / `chip-buff`
  pending PC save); wired into the WS dispatch + hydration replay +
  `_persistRollEntry`; exposed as `window._appendLegendaryAoeResolved`
  for the harness. 1 Playwright test
  (`test_legendary_aoe_resolved_card_renders_per_target_pills`).
- Phase 1c (server reference-attack) ✅ v2.164.0: `use_legendary_action`
  resolves a reference-attack legendary action via
  `_resolve_reference_attack_base_action` (Tail Attack → base "Tail",
  +14 / 2d8+8 bludgeoning), rolls 2d20kh1+attack_bonus vs the target's
  AC, applies crit-doubled damage on a hit, broadcasts
  `feature_used(source=legendary-action-attack)`, and returns an
  `attack_result` field. 2 harness tests
  (`test_tail_attack_reference_resolves_attack_and_damage`,
  `test_tail_attack_without_target_skips_attack_dispatch`). **Phase 1c
  complete.**

### Phase 2 — Legendary resistance pool (S, ~2 commits)

- Phase 2a ✅ v2.165.0: derivation + spend endpoint. `_monster_dict_to_sheet`
  derives `legendary_resistance_per_day` from the "Legendary Resistance
  (N/Day)" special ability (Adult Red Dragon → 3); `_resolve_legendary_resistance_max`
  + `_ensure_legendary_resistance_pool` seed a per-combatant `{max, current}`
  pool; `POST /spend_legendary_resistance` (GM-only) decrements it and
  broadcasts `legendary_resistance_spent`. 6 harness tests in
  `test_spend_legendary_resistance.py` (happy + drain-to-409 + non-legendary
  409 + 404 + 400 + 403).
- Phase 2b (pending): GM auto-prompt on failed-save broadcasts when the
  target's pool > 0 (intercept in the save-resolver hot path) + long-rest
  pool refill. Harness: creature fails a save → prompt fires; spend → save
  flips to success; long rest refills the pool.

### Phase 3 — Lair actions (M, ~3 commits)

- Phase 3a: data shape decision (Open question 2) + backfill
  `lair_actions` for the 15-monster legendary roster from SRD 5.1.
  Ancient Red Dragon (volcanic): "magma erupts" / "tremor"
  / "volcanic gas." Lich: "necrotic surge" / "shadowy tendrils"
  / "memory-shred."
- Phase 3b: `in_lair` toggle on the encounter; initiative-20
  scheduler entry; `lair_action_prompt` + `trigger_lair_action`
  endpoint; AoE dispatch via existing geometry templates.
- Phase 3c: harness — ancient-red-dragon in lair, turn count
  reaches 20, lair-action prompt fires; GM picks "magma erupts";
  DEX-save AoE applies to all combatants in the AoE.

### Non-goals (v1)

- **Non-SRD legendary monsters** (Strahd, Acererak, Mordenkainen,
  custom homebrew). Out of scope per long-standing user direction.
- **Mythic actions** (post-SRD; Theros / Mythic Odysseys content).
- **Per-monster custom lair-action AoEs that need new geometry
  shapes** (e.g. half-cylinder, donut). The existing line/sphere/cone
  templates from v2.158.x cover RAW SRD lair actions in v1.
- **Auto-firing legendary resistance** without a GM prompt — the v1
  flow surfaces the choice to the GM (pool > 0 → "Spend Legendary
  Resistance?" prompt on failed save broadcast). Auto-fire is filed
  as a v2 polish once the reactions-v3 state machine lands.
- **PC-side legendary actions** (e.g. higher-tier homebrew or 2024
  rules). SRD 5.1 has no PC-legendary; out of scope.

---

## Risks

1. **Data shape decision (lair_actions top-level vs unified
   category).** Either works. Default to top-level array because
   the initiative-20 scheduler needs a clean allowlist read; the
   `category` unification can be added later if other call sites
   want a single iteration shape.
2. **The legendary-resistance auto-prompt-on-failed-save needs an
   intercept point in the save-resolver flow.** Both PC-side
   (`_resolve_pc_save`) and NPC-side (`_resolve_npc_save`) need to
   check the relevant target combatant for `legendary_resistance.current
   > 0` and emit the prompt. The save resolver is a hot path —
   the check should be cheap (single dict read).
3. **Multi-legendary-creature encounters.** If two ancient dragons
   share a fight, each has its own pool — straightforward. The
   initiative-20 lair-action slot only fires once per round
   regardless of how many lair creatures are in combat (RAW: lair
   actions are tied to the LAIR, not the creature).
4. **`/next_turn` refresh timing edge case** — the pool refreshes
   at the start of the legendary creature's turn, not at the end
   of the prior creature's turn. The current `/next_turn` flow
   advances `current_combatant_id` atomically; the refresh hook
   fires after the advance, which is correct.

---

## Definition of done (per phase)

1. Mutation only via the endpoints (no ad-hoc writes to
   `combatant.legendary_actions.current` from other sites).
2. Effects fire through the existing `/npc_attack` + AoE dispatch
   pipelines (no parallel damage path).
3. Harness tests assert the **state change** (HP delta, save
   verdict flip, pool decrement, economy_update payload), not
   just the broadcast.
4. `docs/automation-coverage.md` + `docs/test-harness-coverage.md`
   updated in the same commit.

---

## Open questions

1. **Cost-suffix parsing vs data-layer cost field.** The SRD text
   carries the cost in the action name ("Wing Attack (Costs 2
   Actions)"). The data layer today uniformly sets `cost: 1`. Two
   options: (a) keep the name-parse in the endpoint; (b) backfill
   the integer in Phase 1a so the endpoint is name-agnostic.
   **Default: b.** Cleaner, future-proofs against name-string
   changes, and the boot-time validator can gate on the integer.
2. **`lair_actions` top-level array vs `category: "lair_action"`
   in the unified `actions` array.** **Default: top-level array.**
   The initiative-20 scheduler reads the array directly; mixing it
   into `actions` would require a filter on every read site that
   doesn't want lair actions surfaced (which is most of them).
3. **PC-side legendary-resistance prompt.** RAW: only the
   legendary creature uses it. But a PC casting a save-required
   spell on the dragon would trigger the prompt. The flow:
   `_resolve_npc_save` sees the dragon failed → checks pool →
   emits prompt to the GM running the dragon → GM picks "spend" →
   save flips to success. The PC sees the result through the
   regular save broadcast (no PC-side prompt). **Default: NPC-only
   prompt; PC sees the auto-flip in the broadcast.**

---

## Related docs

- [`magic-items-automation.md`](magic-items-automation.md) —
  Phase 1–8 shipped the AoE save dispatch templates the lair-action
  Phase 3 composes with.
- [`reactions-automation.md`](reactions-automation.md) — the v3
  pending-damage state machine is the natural home for the
  auto-resolution polish of the legendary-resistance prompt.
- [`exhaustion-levels.md`](exhaustion-levels.md) — the per-creature
  state-field pattern (integer on the combatant + endpoint mutation
  + read sites compose) is the template this plan follows.
- [`class-content-status.md`](class-content-status.md) — the per-class
  resource-tracking pattern (`combatant.resources` shape) is the
  template for `legendary_resistance.current` / `.max`.
- [`TODO.md` SRD 5e Audit (2026-06-11 refresh)](../../TODO.md#srd-5e-audit-2026-06-11-refresh) —
  the audit finding that filed this plan.
