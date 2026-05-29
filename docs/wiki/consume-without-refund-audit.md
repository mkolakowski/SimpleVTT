# Consume-without-refund audit (v2.97.0 – v2.97.8)

> **Status:** ✅ shipped (v2.97.8 closes the audit). Filed follow-ups documented at the bottom.

## Why this audit existed

Pre-v2.97.0, the `↶ Undo` button on roll-log cards reverted **HP changes** (so you could un-do damage / un-do a heal) and **buff installs** (so an accidental Bless / Hex came back off). But it did **not** revert anything the cast had **consumed** — spell slots, feature resource pools, item charges. A `/cast_spell` that consumed an L1 slot and an `/use_lay_on_hands` that drained 5 HP off the Paladin's pool stayed consumed after Undo.

That made spam-cast → spam-undo a free-cast exploit (cast a level-1 spell, undo to refund the HP delta but keep the spell effect's broadcast in the log — except the slot was now gone, so the player just lost the slot and got nothing). More mundanely, "I clicked the wrong feature, please give me my use back" was unsupported.

The v2.97.0 – v2.97.8 audit pass closed every endpoint that consumes a resource.

## How a refund works

The per-cast undo log (`_attack_damage_log[cast_id]`, 8-hour TTL, in-memory) is the central machinery. Every endpoint that consumes something now stamps an entry into this log under the cast's `cast_id`, and `POST /undo_attack_damage` walks the entries in reverse and dispatches by `kind`.

There are five refund-relevant entry kinds:

| Kind | Stamped by | What undo does | Broadcasts on refund |
|---|---|---|---|
| `spell_slot_spend` | `/cast_spell`, `/use_font_of_magic_to_points` (slot sacrifice leg) | Decrement `sheet["spell_slots"][cslug][lvl]["used"]` by 1 (clamped ≥ 0) | `spell_slot_update` |
| `resource_spend` | All `/use_*` feature endpoints with a counter; `/use_feature` for catalog-resolved keys; `/use_font_of_magic_to_slot` (SP cost leg) | Add `amount` back to `sheet["resources"][i]["current"]` (clamped ≤ `max`) | `resource_update` |
| `slot_restore` | `/use_arcane_recovery` (per-level leg) | Bump `slot.used` **up** by `count` (clamped ≤ `total`) — the inverse of `spell_slot_spend` | `spell_slot_update` |
| `resource_gain` | `/use_font_of_magic_to_points` (SP gain leg) | Subtract `amount` from `current` (clamped ≥ 0) — the inverse of `resource_spend` | `resource_update` |
| `slot_gain` | `/use_font_of_magic_to_slot` (slot gain leg) | If `ephemeral=True`: decrement `total` by 1 and `font_of_magic_extra`. If `ephemeral=False`: increment `used` by 1. | `spell_slot_update` |
| `inventory_consume` | `/use_item` | Find item by `_slug` or `name`; bump qty by 1, OR re-insert the stored item dict at `inv_idx` | `inventory_update` |
| `buff_install` (pre-existing) | `/cast_spell`, `/use_reaction` reaction-cast branches, `/use_rage`, etc. | Restore `target.buffs` to pre-install snapshot | `buff_update` |
| `damage` / `heal` (pre-existing) | `/use_attack`, `/cast_spell`, `/apply_healing`, etc. | Reverse `applied` HP on `target_char_id` | `character_hp_update` |

A single cast can stamp **multiple legs** under one `cast_id`. Examples:

- `/use_arcane_recovery` (Wizard L1): 1 × `resource_spend` (arcane-recovery counter) + N × `slot_restore` (one per restored level). One Undo replays both.
- `/use_font_of_magic_to_points`: 1 × `spell_slot_spend` (the sacrificed slot) + 1 × `resource_gain` (the gained SP, capped at actually-gained delta so an overflow cast doesn't drive SP negative on undo).
- `/use_font_of_magic_to_slot`: 1 × `resource_spend` (SP cost) + 1 × `slot_gain` (with `ephemeral` flag to drive the right inverse).
- `/use_item` heal: 1 × `inventory_consume`. (HP gain is **not** stamped — see "Filed for follow-up" below.)

## How the UI knows a card is refundable

The `feature_used` WS broadcast carries a `cast_id` only when the endpoint stamped a refundable leg. The client's `_appendFeatureUsed` renderer checks `d.cast_id && _REFUNDABLE_FEATURE_SOURCES.has(d.source)` and renders the `↶ Undo` pill on the roll-log card if both hold. The Set lives in `app/static/tabletop.js`:

```js
const _REFUNDABLE_FEATURE_SOURCES = new Set([
    'counterspell-cast', 'shield-cast', 'hellish-rebuke-cast',
    'absorb-elements-cast', 'silvery-barbs-cast',
    'lay-on-hands', 'second-wind',
    'bardic-inspiration', 'cutting-words', 'action-surge',
    'indomitable', 'rage',
    'patient-defense', 'flurry-of-blows', 'wholeness-of-body',
    'step-of-the-wind', 'metamagic-empowered-spell',
    'arcane-recovery', 'font-of-magic',
    'class-feature',  // catch-all for /use_feature-routed features (Channel Divinity)
    'item-use',
]);
```

Spell-cast cards use the existing `spell_cast` source + the v2.92.0 `spell_slot_spend` plumbing — they render their own `↶ Undo` pill via a separate JS path, so they're not in this Set.

## Endpoints covered

### Spell slots

- `/cast_spell` — all leveled spells (cantrips never log; `slot_level >= 1` is the gate)

### Reaction casts (5 endpoints, all share the `/use_reaction` dispatcher)

- `cast-counterspell` — Counterspell at L3+
- `cast-shield` — Shield
- `cast-hellish-rebuke` — Hellish Rebuke
- `cast-absorb-elements` — Absorb Elements
- `cast-silvery-barbs` — Silvery Barbs

### Dedicated `/use_*` endpoints (single-resource spend)

- `/use_lay_on_hands` — Paladin HP pool (variable amount)
- `/use_second_wind` — Fighter Second Wind counter
- `/use_bardic_inspiration` — Bard BI counter
- `/use_cutting_words` — College of Lore reaction; shares the BI counter
- `/use_action_surge` — Fighter action-surge counter
- `/use_indomitable` — Fighter indomitable counter
- `/use_rage` — Barbarian rage counter
- `/use_patient_defense` — Monk ki
- `/use_flurry_of_blows` — Monk ki
- `/use_wholeness_of_body` — Way of the Open Hand 1/long-rest
- `/use_step_of_the_wind` — Monk ki (Disengage / Dash variants)
- `/use_metamagic_empowered_spell` — Sorcerer SP (1)

### Cross-resource conversions (multi-leg)

- `/use_arcane_recovery` — Wizard arcane-recovery counter + per-level slot restore
- `/use_font_of_magic_to_points` — Sacrifice slot → gain SP (with cap-aware actually-gained logging)
- `/use_font_of_magic_to_slot` — Spend SP → gain slot (ephemeral OR restored)

### Catalog-driven (`/use_feature` with `resource_key` in `_FEATURE_ECONOMY`)

- Channel Divinity — all 8 variants (Cleric Turn Undead / Preserve Life / Radiance of the Dawn / Guided Strike; Paladin Sacred Weapon / Turn the Unholy; Death / Arcana / Peace domain options). Single catalog entry with `resource_key: "channel-divinity"` covers all variants because they share the 1-use cost.

### Inventory

- `/use_item` — any consumable (Potion of Healing, scrolls, etc.) via the new `inventory_consume` log kind

## Filed for follow-up

- ~~**HP / death-save effect refund.**~~ ✅ Shipped in **v2.97.16** for the four dedicated HP-applying endpoints (`/use_lay_on_hands`, `/use_second_wind`, `/use_wholeness_of_body`, `/use_item` heal kind). Each stamps a `kind: "heal"` log entry alongside the existing resource / inventory leg; the existing pre-v2.97.0 damage/heal-undo branch reverses the HP delta. Healing spells cast via `/cast_spell` (Cure Wounds, Mass Cure, Healing Word) still have their HP gain unreverted — that path's multi-target save-for-half / claim-based flow is more complex and is filed for a separate audit commit.
- **Stunning Strike.** `/use_stunning_strike` doesn't currently broadcast `feature_used`; it broadcasts `roll` + `roll_request` + `resource_update` instead. The v2.96.0 ↶ Undo pill has nowhere to attach, so plumbing `resource_spend` without a UI surface would be half-done. Filed: switch the endpoint to a feature_used broadcast (or add a roll-card Undo path).
- **Buff persistence after refund.** Endpoints like `/use_rage`, `/use_shield`, `/use_indomitable`, `/use_metamagic_empowered_spell`, and Monk Ki spend-options all install a buff alongside the resource decrement. The refund only restores the resource — the buff stays installed. Players/GMs can manually pop the buff via the buff tracker. A future pass could add the buff to the per-cast `buff_install` snapshot so the v2.65.0 buff-restore branch handles it automatically.
- **Channel Divinity buff teardown.** Sacred Weapon installs a 1-minute buff with `+CHA mod to attack rolls`. Refunding the CD use today leaves the buff active — a future pass should snapshot + restore.
- **`/use_feature` other counters.** Divine Sense (1 + CHA/day), Cleansing Touch (CHA/day), Stroke of Luck (1/short-rest), Cunning Action if a future class adds a counter to it. All can opt in by adding `resource_key + amount` to their `_FEATURE_ECONOMY` entry (one-line change per feature — the v2.97.7 plumbing reads it).
- **Metamagic variants beyond Empowered.** Twinned / Quickened / Heightened / Subtle / Distant / Extended Spell don't have endpoints yet (only Empowered ships in v2.97.x). When they ship, each gets the same 3-line resource_spend patch as `/use_metamagic_empowered_spell`.

## Adding a refundable endpoint

The pattern is small enough to inline:

```python
# After the existing decrement + db.commit():
cast_id = uuid.uuid4().hex[:12]
_log_damage_entry(cast_id, {
    "kind": "resource_spend",                 # or "spell_slot_spend" / "inventory_consume" / etc.
    "campaign_id": campaign_id,
    "character_id": char.id,
    "resource_key": "<your-resource-key>",
    "amount": <int>,
    "source_label": "<human-readable>",
})

# Add cast_id to the existing feature_used broadcast payload.
await hub.broadcast(campaign_id, {
    "type": "feature_used",
    "data": {
        ...,
        "source": "<your-slug>",
        "cast_id": cast_id,
        ...,
    },
})
```

Then add `'<your-slug>'` to `_REFUNDABLE_FEATURE_SOURCES` in `app/static/tabletop.js`. The existing `↶ Undo` click handler POSTs to `/undo_attack_damage` with the `cast_id` — no other JS changes needed.

For a harness test, model on `tests/harness/test_undo_refunds_resource.py::test_undo_refunds_lay_on_hands_pool`: cast, capture `cast_id` off the `feature_used` broadcast, mark the WS, undo, assert the matching `resource_update` (or `spell_slot_update` / `inventory_update`) refund broadcast lands.

## Cross-references

- [Realtime broadcasts catalog](realtime-broadcasts-catalog.md) — full payload shapes for `feature_used`, `resource_update`, `spell_slot_update`, `inventory_update`, etc.
- [Endpoint catalog](endpoint-catalog.md) — full request/response shapes for every endpoint covered by the audit.
- CHANGELOG entries v2.92.0 (initial spell-slot refund), v2.97.0 ("Pool Refund"), v2.97.5 ("Recover the Recovery"), v2.97.6 ("Trading Posts"), v2.97.7 ("Tithe and Refund"), v2.97.8 ("Pocket the Potion").
