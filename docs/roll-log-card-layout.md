# Roll-log card layout

The roll log (right-side drawer on the tabletop) collects four kinds of cards. Every card has the same anatomy: a **headline** that's always visible + an optional **`▾ details`** section that's collapsed by default and tucks the narrative / breakdown out of the way.

## Why collapsible

A long fight at the table generates a lot of cards — saves, attacks, spell descriptions, feature uses. If every card unfurls its full description by default, the log becomes a wall of text and the actionable info (HP delta, hit/miss, ↶ Undo button) gets buried. v2.41.0 introduced a `<details>` block so the narrative content (spell description, feature flavor text, dice breakdown) is one tap away rather than always-on.

## Display modes (v2.42.0)

A user-toggleable setting at the top of the roll-log drawer switches between two display modes for spell-cast cards' auto-effect consequences. The state lives in `localStorage["simplevtt:rolllog_mode"]` and applies to newly-rendered cards (existing cards in the DOM keep the mode they were rendered with).

| Mode | Label | What it does |
|------|-------|--------------|
| **`verbose`** (default) | "Compact: OFF" | Auto-effect lines (heal / attack / save / damage / buff) live inside a `▼ Result` collapsible block, open by default. Folded state shows a one-liner summary chip. |
| **`simple`** | "Compact: ON" | Auto-effect lines collapse into a horizontal pill row — one chip per consequence, always visible. The `▼ Result` block is replaced entirely. |

Both modes:
- Fire the **dice toast** (v2.33.0+) for every server roll.
- Keep the `▾ Spell details` toggle for the spell's RAW flavor text.
- Surface the `↶ Undo` button identically (server endpoint unchanged).

The toggle button is in the toolbar at the top of the roll log; click to flip.

## Common anatomy

```
┌────────────────────────────────────────────────┐
│  ⭕ avatar    Caster Name    [badge]    HH:MM │  ← header (always)
│                                                │
│  🎯 note line — "What just happened"           │  ← short narrative
│                                                │
│  [auto-effect lines: 🎯 vs AC, 🎲 damage,      │  ← consequences
│   ✚ healed, 📋 save, 🥶 paralyzed, ↶ Undo]   │     (always)
│                                                │
│  ▾ details                                     │  ← collapsible toggle
│  ┌─────────────────────────────────────────┐  │
│  │ Long-form description / dice breakdown  │  │  ← only when open
│  │ 1d20[14]+5 = 19                         │  │
│  │ Spell flavor text…                      │  │
│  └─────────────────────────────────────────┘  │
└────────────────────────────────────────────────┘
```

The four card variants below differ in **what goes in the headline** and **what goes inside `details`**, but the structure is identical.

---

## 1. `roll` — plain dice roll

Emitted by the `/roll` endpoint and by every dice-rolling endpoint internally (`/roll_request/{id}/respond`, the v2.39.0 GM concentration log, save spells, etc.). The headline is the **total** in the big number column; the details holds the **dice expression and breakdown**.

### Headline (always visible)

| Field | Purpose | Example |
|-------|---------|---------|
| `total` | Big number on the left, the only number the table needs to act on | `19` |
| `note` | One-line narrative ("what was rolled / why") | `🎯 Greataxe → Bandit · vs AC 12 · ✅ HIT` |
| `user_name` / `char_name` / `portrait_url` | Who rolled | Krieger Stonefist + 🪓 |
| `visibility` badge | `GM only` / `GM + you` chip when the roll isn't public | `GM only` |
| `time` | Local clock | `03:15 PM` |

### `▾ details` (collapsed by default)

| Field | Purpose | Example |
|-------|---------|---------|
| `expression` | The submitted dice formula | `1d20+5` |
| `breakdown` | dice.py's expanded form with bracketed die faces | `1d20[14]+5 = 19` |

---

## 2. `weapon_attack` — `/attack` endpoint result

Emitted on every weapon strike. The headline carries the attack roll + damage + applied-HP delta + crit / hit / miss verdict. Most info is **always visible** because each line is actionable (the ↶ Undo button needs to be one click, not two).

### Headline (always visible)

```
🎯 Greataxe — attack       17     ✅ HIT vs AC 12      [1d20[12]+5]
💥 Damage                  9      −9 HP · 11 → 2 HP    ↶ Undo
✨ Sneak Attack            +6     [1d6[6]]
```

| Block | Purpose |
|-------|---------|
| **Attack line** | d20 result · hit/miss/crit verdict · target AC |
| **Damage line** | damage total · type · `damage_applied` HP delta · ↶ Undo button (T.2 auto-apply) |
| **Bonus damage line** | Sneak Attack / Divine Smite / etc. — separate so attribution is clear |
| **Prompt-save button** | For save-DC weapons (Breath Weapon, etc.) |

### `▾ details` (currently not yet wrapped here — filed)

The breakdown spans live inline today because the dice IS the at-a-glance point of an attack card. Future commit can move the per-line `1d20[12]+5` breakdown into a collapsible section if the card becomes too dense.

---

## 3. `spell_cast` — `/cast_spell` endpoint result

The richest card type. The headline holds the spell name + target + slot + every auto-resolution outcome (heal, attack roll, save, condition install, save-for-half damage). The collapsible details holds the spell's **flavor / mechanical description text**.

### Headline (always visible)

```
🪄 Healing Word → Krieger     Lv 1 slot     03:15 PM
1 bonus action

✚ Healed Krieger Stonefist +4 HP  (50 → 54 HP)  ↶ Undo
[Cast] [Damage] [Save] action buttons via renderActionButtons
```

Same pattern for spell attacks (Fire Bolt → "🎯 Spell attack Bandit: 18 vs AC 12 — ✅ HIT" + 🎲 Applied line), save spells (Hold Person → "📋 WIS save Bandit: 8 vs DC 14 — ❌ failed" + "🥶 Paralyzed Bandit · 10 rounds"), and multi-beam Eldritch Blast (one row per beam in `auto_attack_beams`).

| Auto-line | Fires when |
|-----------|------------|
| `_autoHealLineHtml` | `auto_heal_applied > 0` (T.4) |
| `_autoSaveLineHtml` | `auto_save_target_kind` set (T.3 / T.3b / T.3c) |
| `_autoAttackLineHtml` | `auto_attack_hit != null` (T.4b / T.4c multi-beam) |

### `▾ details` (collapsed by default)

| Field | Purpose | Example |
|-------|---------|---------|
| `spell_desc` | RAW spell text from the SRD JSON | "A creature of your choice that you can see within range regains hit points equal to 1d4 + your spellcasting ability modifier…" |

The auto-resolution lines stay outside the toggle because they're the **outcome** of the cast — players need to see the HP delta or the save verdict immediately. The spell description is reference reading, not action information.

---

## 4. `feature_used` — class-feature use

Emitted by `/use_feature`, `/use_rage`, `/use_second_wind`, `/use_cutting_words`, `/use_lay_on_hands`, etc.

### Headline (always visible)

```
✨ Garrik Ironside                       03:15 PM
💨 Second Wind   (0/1 left)  second-wind
```

| Field | Purpose | Example |
|-------|---------|---------|
| `feature_name` | Title (always one short line) | `💨 Second Wind` |
| `remaining`/`max` | Counter chip if the feature has uses | `(0/1 left)` |
| `source` | Slug tag | `second-wind` |
| `over_budget_badge` | If the action chip was already spent | `⚠ Manual override` |
| `dice_*` toast | Heal die / BI die pops as a separate **roll toast** (v2.35.0) — not on the card | Sequenced toast popup |

### `▾ details` (collapsed by default)

| Field | Purpose | Example |
|-------|---------|---------|
| `feature_desc` | Narrative description of what happened | `"Bonus action: rolled 1d10+5 = 9."` |

The dice value lives in the toast (v2.35.0) AND in `feature_desc`. The HP bar shows the consequence. The card stays clean.

---

## 5. Persistence

All four card types **survive page refreshes** (v2.28.0 — `simplevtt:rolllog:${CAMPAIGN_ID}` localStorage). Plus the legacy heal-apply result rows (v2.29.1). Open state on the `<details>` toggle does **not** persist — refreshing a card reverts it to collapsed. Acceptable: the headline alone is enough for the table to read the log; the details are reference-only.

The roll log is capped at the most recent 100 WS-only entries (FIFO trim). Server-rendered `roll` rows from the DB (the Jinja `{% for r in rolls %}` block) are not in the localStorage buffer — they come down on every page load fresh.

---

## 6. Visibility filter

`roll` events carry a `visibility` field with three legal values:

| Visibility | Reaches |
|------------|---------|
| `public` (default) | Everyone in the campaign |
| `gm_and_roller` | Just the GM + the rolling user |
| `gm_only` | Just the GM |

The filter is enforced both server-side (`/roll` broadcasts only to eligible sockets) and client-side (`appendRoll` re-checks before rendering — defense-in-depth). The new v2.39.0 GM-only concentration log entry uses `gm_only`.

`weapon_attack` / `spell_cast` / `feature_used` are always public — they reflect public table actions.

---

## 7. Where the code lives

- **Card rendering**: `app/static/tabletop.js` — `appendRoll`, `appendSpellCast`, `_appendFeatureUsed`, `appendWeaponAttack`, `appendRollRequest`.
- **Persistence**: `app/static/tabletop.js` — `_persistRollEntry` + `_hydrateRollLog`. localStorage key `simplevtt:rolllog:${CAMPAIGN_ID}`.
- **Toggle CSS**: `app/templates/tabletop.html` — `.roll-card-details` rules at the top of the inline `<style>` block.
- **Dice toast (separate from the log card)**: `app/static/roll_toast.js`. Fires for every server roll; respects the visibility filter.

---

## Changing this layout

If you add a new card type or move a field between the headline and the details section, update this file in the same commit. Convention:

- New card type → new H2 section here with the headline / details table.
- Moved field → update the corresponding table row.
- Visibility / persistence changes → update sections 5 + 6 at the bottom.
