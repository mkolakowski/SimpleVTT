# Undo refund audit (v2.97.0 – v2.97.34)

> **Status:** ✅ shipped. Two stacked audits closed: **consume-without-refund** (resources + slots + inventory + HP, v2.97.0 – v2.97.18) and **buff teardown** (buffs from feature use + reaction casts + spell save-or-suck + catalog-driven /use_feature + Bardic Inspiration target buff + no-save spell buffs via `_SPELL_BUFF_MAP` + dedicated concentration-spell endpoints (Hunter's Mark + Hex) + Cha-save / Dex-save debuff spells (Bane + Faerie Fire), v2.97.20 – v2.97.33). **v2.97.34** then closes the attack-roll mechanical hooks for four of the marker buffs: Sacred Weapon +CHA, Bless +1d4, Bane -1d4, Faerie Fire advantage — every buff that installs now actually does its thing on attack rolls. Filed follow-ups documented at the bottom.

## Why these audits existed

Pre-v2.97.0, the `↶ Undo` button on roll-log cards reverted **HP changes** (so you could un-do damage / un-do a heal) and **buff installs from spell casts** (so an accidental Bless / Hex came back off). But it did **not** revert anything the cast had **consumed** — spell slots, feature resource pools, item charges. A `/cast_spell` that consumed an L1 slot stayed consumed after Undo. An `/use_lay_on_hands` that drained 5 HP off the Paladin's pool stayed drained.

The **consume-without-refund audit** (v2.97.0 – v2.97.18) closed every endpoint that consumes a resource, plus the downstream HP-application paths.

The **buff-teardown audit** (v2.97.20 – v2.97.27) then closed the secondary gap: even after the resource refund landed, buffs installed by `/use_rage`, `/use_indomitable`, the three Monk ki spend-options, `/use_metamagic_empowered_spell`, the Shield / Absorb Elements reaction casts, Stunning Strike's target Stunned, and any `/cast_spell` save-or-suck condition would stay installed. The resource was back but the effect lingered — a Barbarian could rage indefinitely by spam Use → Undo without the rage buff ever clearing. Same shape for every other endpoint that paired a resource with a buff.

## How a refund works

The per-cast undo log (`_attack_damage_log[cast_id]`, 8-hour TTL, in-memory) is the central machinery. Every endpoint that consumes something or installs a buff stamps an entry into this log under the cast's `cast_id`, and `POST /undo_attack_damage` walks the entries in reverse and dispatches by `kind`.

There are eight refund-relevant entry kinds:

| Kind | Stamped by | What undo does | Broadcasts on refund |
|---|---|---|---|
| `spell_slot_spend` | `/cast_spell`, reaction casts (Shield / Counterspell / etc.), `/use_font_of_magic_to_points` | Decrement `sheet["spell_slots"][cslug][lvl]["used"]` by 1 (clamped ≥ 0) | `spell_slot_update` |
| `resource_spend` | All `/use_*` feature endpoints; `/use_feature` for catalog-resolved keys; `/use_stunning_strike`; `/use_font_of_magic_to_slot` | Add `amount` back to `sheet["resources"][i]["current"]` (clamped ≤ `max`) | `resource_update` |
| `slot_restore` | `/use_arcane_recovery` (per-level leg) | Bump `slot.used` **up** by `count` (clamped ≤ `total`) — the inverse of `spell_slot_spend` | `spell_slot_update` |
| `resource_gain` | `/use_font_of_magic_to_points` (SP gain leg) | Subtract `amount` from `current` (clamped ≥ 0) — the inverse of `resource_spend` | `resource_update` |
| `slot_gain` | `/use_font_of_magic_to_slot` (slot gain leg) | If `ephemeral=True`: decrement `total` by 1 and `font_of_magic_extra`. If `ephemeral=False`: increment `used` by 1. | `spell_slot_update` |
| `inventory_consume` | `/use_item` | Find item by `_slug` or `name`; bump qty by 1, OR re-insert the stored item dict at `inv_idx` | `inventory_update` |
| `buff_install` (pre-existing v2.65.0; opted into by v2.97.20+) | `/cast_spell` non-cantrip save-or-suck, `/use_reaction` Shield + Absorb Elements, `/use_rage`, `/use_indomitable`, the 3 Monk ki spends, `/use_metamagic_empowered_spell`, `/use_stunning_strike` (NPC target + PC target via `/respond`), `/use_feature` catalog-driven (Sacred Weapon, v2.97.29), `/use_bardic_inspiration` target buff (v2.97.30), `/cast_spell` no-save buff via `_SPELL_BUFF_MAP` (Bless, v2.97.31), `/cast_hunters_mark` + `/cast_hex` (dedicated concentration-spell endpoints, v2.97.32) | Restore `target.buffs` to pre-install snapshot via `_restore_target_buffs(db, campaign_id, target_char_id, target_combatant_id, buffs_before)` | `buff_update` |
| `damage` / `heal` (pre-existing) | `/use_attack`, `/cast_spell`, `/apply_healing`, `/use_lay_on_hands`, `/use_second_wind`, `/use_wholeness_of_body`, `/use_item` heal kind, Blessed Healer (Disciple of Life subclass) | Reverse `applied` HP on `target_char_id` | `character_hp_update` |

A single cast can stamp **multiple legs** under one `cast_id`. Examples:

- `/use_rage`: 1 × `resource_spend` (rage counter) + 1 × `buff_install` (caster's rage buff snapshot). Undo refunds the counter AND drops the buff in one POST.
- `/use_arcane_recovery` (Wizard L1): 1 × `resource_spend` (arcane-recovery counter) + N × `slot_restore` (one per restored level).
- `/use_font_of_magic_to_points`: 1 × `spell_slot_spend` (the sacrificed slot) + 1 × `resource_gain` (the gained SP, capped at actually-gained delta so an overflow cast doesn't drive SP negative on undo).
- `/use_font_of_magic_to_slot`: 1 × `resource_spend` (SP cost) + 1 × `slot_gain` (with `ephemeral` flag to drive the right inverse).
- `/use_lay_on_hands`: 1 × `resource_spend` (pool) + 1 × `heal` (target HP, post-cap).
- `/use_item` heal: 1 × `inventory_consume` + 1 × `heal` (self HP, post-cap).
- `/use_stunning_strike` (NPC target who fails save): 1 × `resource_spend` (ki) + 1 × `buff_install` (target's Stunned, keyed by `target_combatant_id`).
- `/cast_spell` Hold Person on a PC who fails: 1 × `spell_slot_spend` (slot) + 1 × `buff_install` (target's Paralyzed). The buff_install is stamped by `/respond` under the spell's cast_id via `_save_request_context[req.id]["cast_id"]`.

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
    'stunning-strike',
]);
```

Spell-cast cards use the existing `spell_cast` source + the v2.92.0 `spell_slot_spend` plumbing — they render their own `↶ Undo` pill via a separate JS path, so they're not in this Set.

## Endpoints covered

### Spell slots

- `/cast_spell` — all leveled spells (cantrips never log; `slot_level >= 1` is the gate). PC-target save-or-suck spells (Hold Person, Sleep, Suggestion, Tasha's Hideous Laughter, Bane — Cha save, Faerie Fire — Dex save, …) pair a `buff_install` leg via `/respond` from the `_SPELL_CONDITION_MAP` catalog (v2.97.27 plumbing; Bane + Faerie Fire added v2.97.33). No-save buff spells with a `_SPELL_BUFF_MAP` entry (Bless today; Heroism / Aid next) install + log inline after the `spell_cast` broadcast (v2.97.31).
- `/cast_hunters_mark` — Ranger 1st-level dedicated endpoint. Pre-v2.97.32 the slot consume + caster concentration buff install lived outside the v2.92.0 + v2.97.20 undo paths; v2.97.32 mints a `cast_id`, logs `spell_slot_spend` + `buff_install` under it, and surfaces the cast_id on the `feature_used` broadcast. Single Undo refunds the Ranger slot AND drops the `hunters-mark` buff.
- `/cast_hex` — Warlock 1st-level dedicated endpoint, same plumbing as `/cast_hunters_mark` (v2.97.32). Refunds Pact slot + drops the `hex` caster buff in one undo.

### Reaction casts (5 endpoints, all share the `/use_reaction` dispatcher)

- `cast-counterspell` — Counterspell at L3+
- `cast-shield` — Shield, with caster `buff_install` (shield-active, v2.97.24)
- `cast-hellish-rebuke` — Hellish Rebuke
- `cast-absorb-elements` — Absorb Elements, with caster `buff_install` (absorb-elements buff, v2.97.24)
- `cast-silvery-barbs` — Silvery Barbs

### Dedicated `/use_*` endpoints (single-resource spend)

- `/use_lay_on_hands` — Paladin HP pool (variable amount) + target `heal` (v2.97.16)
- `/use_second_wind` — Fighter Second Wind counter + self `heal` (v2.97.16)
- `/use_bardic_inspiration` — Bard BI counter + target `buff_install` (`bardic-inspiration-die`, carries die size in `effects.bardic_inspiration_die`, v2.97.30)
- `/use_cutting_words` — College of Lore reaction; shares the BI counter
- `/use_action_surge` — Fighter action-surge counter
- `/use_indomitable` — Fighter indomitable counter + caster `buff_install` (indomitable-armed, v2.97.21)
- `/use_rage` — Barbarian rage counter + caster `buff_install` (rage, v2.97.20)
- `/use_patient_defense` — Monk ki + caster `buff_install` (patient-defense, v2.97.22)
- `/use_flurry_of_blows` — Monk ki + caster `buff_install` (flurry-of-blows-active, v2.97.22)
- `/use_wholeness_of_body` — Way of the Open Hand 1/long-rest + self `heal` (v2.97.16)
- `/use_step_of_the_wind` — Monk ki (Disengage / Dash variants) + caster `buff_install` (v2.97.22)
- `/use_metamagic_empowered_spell` — Sorcerer SP (1) + caster `buff_install` (metamagic-empowered-pending, v2.97.23)
- `/use_stunning_strike` — Monk ki + target `buff_install` (Stunned; NPC inline at v2.97.25, PC via `/respond` at v2.97.26)

### Cross-resource conversions (multi-leg)

- `/use_arcane_recovery` — Wizard arcane-recovery counter + per-level slot restore
- `/use_font_of_magic_to_points` — Sacrifice slot → gain SP (with cap-aware actually-gained logging)
- `/use_font_of_magic_to_slot` — Spend SP → gain slot (ephemeral OR restored)

### Catalog-driven (`/use_feature` with `resource_key` in `_FEATURE_ECONOMY`)

- Channel Divinity — all 8 variants (Cleric Turn Undead / Preserve Life / Radiance of the Dawn / Guided Strike; Paladin Sacred Weapon / Turn the Unholy; Death / Arcana / Peace domain options). Single catalog entry with `resource_key: "channel-divinity"` covers all variants because they share the 1-use cost. **Sacred Weapon** additionally installs the `sacred-weapon` caster buff via the v2.97.29 catalog-driven buff path; `_FEATURE_ECONOMY` option entries can opt in by adding a `"buff": {...}` dict and `/use_feature` snapshots → installs → logs `buff_install` under the same `cast_id` as the resource_spend. Other CD options + future class features can drop the same buff dict in and get teardown for free.

### Inventory

- `/use_item` — any consumable (Potion of Healing, scrolls, etc.) via the `inventory_consume` log kind; heal items also stamp a self-`heal` leg (v2.97.16).

### Healing surface

- `/apply_healing` — the heal-claim path. Refund stamps a `heal` entry against whoever Alice/the GM healed (v2.97.17). Blessed Healer self-heal also refundable (v2.97.18).

## Adding a refundable endpoint

The pattern for a new resource refund is small enough to inline:

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

Then add `'<your-slug>'` to `_REFUNDABLE_FEATURE_SOURCES` in `app/static/tabletop.js`.

If the endpoint also installs a buff (caster-side or target-side), pair it with a buff_install snapshot:

```python
# Caster-side (most common):
_caster_buffs_before = _snapshot_target_buffs(
    db, campaign_id, {"char_id": char.id},
)
await _install_buff(campaign_id, char.id, buff)
_log_damage_entry(cast_id, {
    "kind": "buff_install",
    "campaign_id": campaign_id,
    "target_char_id": char.id,
    "buffs_before": _caster_buffs_before,
    "buff_installed_key": buff["key"],
})

# Target-side (NPC):
_target_buffs_before = _snapshot_target_buffs(
    db, campaign_id, target_combatant,
)
await _install_buff_on_combatant_id(campaign_id, target_combatant.get("id"), buff)
_log_damage_entry(cast_id, {
    "kind": "buff_install",
    "campaign_id": campaign_id,
    "target_combatant_id": target_combatant.get("id"),
    "buffs_before": _target_buffs_before,
    "buff_installed_key": buff["key"],
})
```

For a save-or-suck endpoint whose buff installs via `/respond` (after the player rolls), thread the cast_id through `_save_request_context[req.id]["cast_id"]`. `/respond` already prefers `ctx["cast_id"]` when stamping (v2.97.26+).

For a harness test, model on `tests/harness/test_undo_refunds_resource.py::test_undo_refunds_lay_on_hands_pool` (single-leg) or `test_undo_refunds_rage_counter_and_buff` (multi-leg with buff teardown).

## Filed for follow-up

- ~~**HP / death-save effect refund.**~~ ✅ **Audit complete across v2.97.16 + v2.97.17 + v2.97.18.** Every documented heal path now leaves an undo log entry the existing v2.65.0 heal-undo branch can reverse.
- ~~**Stunning Strike.**~~ ✅ Shipped in **v2.97.19** (ki refund) and **v2.97.25 + v2.97.26** (NPC + PC target Stunned teardown).
- ~~**Buff persistence after refund.**~~ ✅ **Audit complete across v2.97.20 – v2.97.27.** 11 sites across 9 endpoints now drop their buff alongside refunding the resource. Endpoint-specific notes in the table above.
- ~~**Channel Divinity buff teardown.**~~ ✅ Shipped in **v2.97.29**. `/use_feature` now reads a `buff` dict from the catalog entry (parent feature OR option override), snapshots caster buffs, installs via `_install_buff`, mirrors to sheet, and stamps `buff_install` under the resource_spend's `cast_id`. Sacred Weapon is the first opt-in (its buff carries `effects: {"sacred_weapon": True}` as a marker for a future +CHA attack-roll hook — today the icon + duration are real, the attack bonus is GM-adjudicated). Other CD options that install buffs (Sentinel of Faith, Path of the Grave, Order's Demand, …) and any future `/use_feature`-routed buff installer can opt in with the same one-key catalog edit.
- **`/use_feature` other counters.** Divine Sense (1 + CHA/day), Cleansing Touch (CHA/day), Stroke of Luck (1/short-rest), Cunning Action if a future class adds a counter to it. All can opt in by adding `resource_key + amount` to their `_FEATURE_ECONOMY` entry (one-line change per feature — the v2.97.7 plumbing reads it).
- **Metamagic variants beyond Empowered.** Twinned / Quickened / Heightened / Subtle / Distant / Extended Spell don't have endpoints yet (only Empowered ships in v2.97.x). When they ship, each gets the same resource_spend + (optional) buff_install patches.
- ~~**Bardic Inspiration target buff teardown.**~~ ✅ Shipped in **v2.97.30**. `/use_bardic_inspiration` now installs a `bardic-inspiration-die` buff on the recipient (carrying the die size in `effects.bardic_inspiration_die` for a future attack/save hook), snapshots the target's pre-install buffs, and logs `buff_install` under the existing `bi_cast_id`. Undo refunds the BI counter on the bard AND drops the buff on the recipient in one POST. Install is best-effort: outside combat (no active battle / recipient not in init) it stays announce-only and skips the log entry so undo doesn't try to restore an install that never happened.
- **Other `/cast_spell` buff-installing spells beyond save-or-suck.** ✅ Bless shipped in v2.97.31 via `_SPELL_BUFF_MAP`; Hex + Hunter's Mark shipped in v2.97.32 (direct endpoint edits); **Bane + Faerie Fire shipped in v2.97.33** via `_SPELL_CONDITION_MAP` (save-or-debuff; the existing /respond install path stamps the buff_install under cast_spell's cast_id via v2.97.27 plumbing). Remaining filed: Haste / Aid / Heroism / Protection from Evil and Good / Shield of Faith / Sanctuary — all one-line additions to `_SPELL_BUFF_MAP` (no save) or `_SPELL_CONDITION_MAP` (save-or-debuff/buff). The catalog + the patch pattern both exist; this is a content-population follow-up, not an architecture task.

## Cross-references

- [Realtime broadcasts catalog](realtime-broadcasts-catalog.md) — full payload shapes for `feature_used`, `resource_update`, `spell_slot_update`, `inventory_update`, `buff_update`, etc.
- [Endpoint catalog](endpoint-catalog.md) — full request/response shapes for every endpoint covered by the audit.
- CHANGELOG entries v2.92.0 (initial spell-slot refund), v2.97.0 ("Pool Refund"), v2.97.5 ("Recover the Recovery"), v2.97.6 ("Trading Posts"), v2.97.7 ("Tithe and Refund"), v2.97.8 ("Pocket the Potion"), v2.97.16 ("The Effect Rewind"), v2.97.17 ("Claim the Refund"), v2.97.18 ("Heal the Healer"), v2.97.19 ("Strike the Refund"), v2.97.20 ("Calm the Rage"), v2.97.21 ("Disarm the Shield"), v2.97.22 ("Three Stances Down"), v2.97.23 ("Empowered No More"), v2.97.24 ("Lower the Shield"), v2.97.25 ("Wake the Stunned"), v2.97.26 ("Wake the Other Stunned"), v2.97.27 ("Hold the Cleric"), v2.97.28 ("The Updated Ledger"), v2.97.29 ("Sheathe the Sacred Weapon"), v2.97.30 ("Reclaim the Inspiration"), v2.97.31 ("Lift the Blessing"), v2.97.32 ("Untrack the Mark"), v2.97.33 ("Snuff the Curse"), v2.97.34 ("Roll the Reckoning"), v2.97.35 ("Save Your Breath"), v2.97.36 ("Touch the Bonfire"), v2.97.37 ("Borrow the Bravery"), v2.97.38 ("Faithward"), v2.97.39 ("The Sheen Holds"), v2.97.40 ("Stout Hearts"), v2.97.41 ("Quick Salve"), v2.97.42 ("Above the Mark"), v2.97.43 ("Resolute Heart"), v2.97.44 ("Steady Breath"), v2.97.45 ("Don't Look Here"), v2.97.46 ("The Six Wards"), v2.97.47 ("Three Stout Hearts"), v2.97.48 ("The Sacred Veil"), v2.97.49 ("Unbreakable Will"), v2.97.50 ("Tools for the Vigil"), v2.97.51 ("Open Hands, Open Books"), v2.97.52 ("The Inviolate Ward"), v2.97.53 ("Vow Broken"), v2.97.54 ("The Caster Steps Up"), v2.97.55 ("The Spell Breaks the Vow"), v2.97.56 ("The Whisper Lands"), v2.97.57 ("Tap the Verse"), v2.97.58 ("The Daybreak Tally"), v2.97.59 ("Verse in the Right Slot"), v2.97.60 ("The Second Bell"), v2.97.61 ("Tolling Loose the Chain"), v2.97.62 ("The Bell Rings Itself"), v2.97.63 ("Shake the Sleeper"), v2.97.64 ("Rise and Shine"), v2.97.65 ("The Blood Wakes"), v2.97.66 ("The Bandit Stirs").
