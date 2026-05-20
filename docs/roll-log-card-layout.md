# Roll-log card layout

The roll log (right-side drawer on the tabletop) collects four kinds of cards. Every card has the same anatomy: a **header strip** (avatar, name, target tag, classification chip, time) + a **body row** (what was rolled / cast / used) + an **outcome pill row** (the result of auto-resolution, when applicable) + a collapsible **`▾ details`** section for long flavor / dice breakdown.

## Why pills?

A long fight at the table generates a lot of cards. v2.41.0 added a `<details>` toggle for the narrative tail. v2.42.0 added a `▼ Result` collapsible + a "Compact" mode toggle for the auto-effect outcomes. v2.43.0 simplified to **one display**: outcomes always render as a horizontal row of **oversized pills**, color-coded by consequence type (heal=green, hit=green, miss=red, crit=amber, damage=orange, buff=cyan, prompt=accent, undo=accent). One pill per outcome; the row is the eye's at-a-glance scan target. The ▼ Result drop-down and the Compact toggle are gone — the simpler layout serves both casual scrollback and live-play readability without a mode setting.

## Common anatomy (v2.43.0)

```
┌────────────────────────────────────────────────────────┐
│  ⭕ avatar  Caster Name  [→ Target] [Chip]    HH:MM   │  ← header (always)
│                                                        │
│  🪄 Spell / Feature Name · meta · meta · meta          │  ← name + inline meta
│                                                        │
│  [✚ +5 HP Pip (8→13)] [↶ Undo]                         │  ← outcome pills
│                                                        │
│  ▾ details                                             │  ← collapsible toggle
│  ┌─────────────────────────────────────────────┐      │
│  │ Long-form description / dice breakdown       │      │  ← only when open
│  └─────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────┘
```

Three structural changes from earlier versions:

- **Target tag in the header** (not in the body next to the spell name). Same row as the avatar / name / slot chip, so the target is the first thing the eye lands on.
- **Meta inlined with the name.** School, casting time, range, Concentration, Ritual all live on the same line as the spell name — separated by `·` dots.
- **Outcome row is always pills.** No more ▼ Result drop-down, no mode toggle. Pills are bigger than the v2.42.0 chips (~30 px tall, 13 px font, semibold border) so they read across the table at a glance.

The four card variants below differ in **what goes in the body row** and **what pills the outcome row carries**, but the structure is identical.

---

## 1. `roll` — plain dice roll

Emitted by `/roll`. Headline is the total (big number in the left column) + a short note line. No outcome pills (a plain roll has no auto-resolution outcome). The dice expression + per-die breakdown live in `▾ details`.

### Header (always visible)

| Field | Purpose | Example |
|-------|---------|---------|
| `total` | Big number in the left column | `19` |
| `note` | One-line narrative | `🎯 Greataxe → Bandit · vs AC 12 · ✅ HIT` |
| `user_name` / `char_name` / `portrait_url` | Who rolled | Krieger Stonefist + 🪓 |
| `visibility` badge | `GM only` / `GM + you` chip when not public | `GM only` |
| `time` | Local clock | `03:15 PM` |

### `▾ details` (collapsed by default)

| Field | Purpose | Example |
|-------|---------|---------|
| `expression` | The submitted dice formula | `1d20+5` |
| `breakdown` | dice.py's expanded form with bracketed die faces | `1d20[14]+5 = 19` |

---

## 2. `weapon_attack` — `/attack` endpoint result

Emitted on every weapon strike. Carries the attack roll + damage + applied-HP delta + crit / hit / miss verdict. Lines are inline (always visible) because each line is actionable.

### Lines (always visible)

```
🎯 To hit         17     ✅ HIT vs AC 12      1d20[12]+5
💥 Damage         9      −9 HP · 11 → 2 HP    ↶ Undo
✨ Sneak Attack   +6                          1d6[6]
```

| Block | Purpose |
|-------|---------|
| **Attack line** | d20 result · hit/miss/crit verdict · target AC |
| **Damage line** | damage total · type · `damage_applied` HP delta · ↶ Undo button (T.2 auto-apply) |
| **Bonus damage line** | Sneak Attack / Divine Smite / etc. — separate so attribution is clear |
| **Prompt-save button** | For save-DC weapons (Breath Weapon, etc.) |

Weapon-attack cards do **not** use the oversized pill row — their inline attack/damage lines already carry the same information in a denser format and the dice expression is the at-a-glance content of the card.

---

## 3. `spell_cast` — `/cast_spell` endpoint result

The richest card type. Target tag lives in the header (v2.43.0). Spell metadata (school / casting time / range / Concentration / Ritual) is **inlined** with the spell name on a single body row. The outcome of auto-resolution (heal, attack-roll verdict, save prompt or rolled save, condition install, save-for-half damage) renders as **oversized pills** in a horizontal row.

### Header (always visible)

| Field | Purpose | Example |
|-------|---------|---------|
| `caster_char_name` | Who cast | `Brother Tavik Stonebrow` |
| target tag (v2.43.0) | Target combatant chip (`→ Pip Quickfingers`) | `→ Pip` |
| `slot_label` | `Cantrip` / `Lv 1 slot` / `Lv 2 slot (upcast)` | `Lv 1 slot` |
| `time` | Local clock | `03:15 PM` |

### Body row (always visible)

```
🪄 Healing Word · Evocation · 1 bonus action · 60 feet · Concentration
```

One row — spell name plus the metadata bits joined with `·` dots.

### Outcome pill row (when auto-resolution fired)

Each consequence is its own pill:

| Pill | Class | When it fires |
|------|-------|---------------|
| `✚ Pip +5 HP (8 → 13)` | `chip-heal` | `auto_heal_applied > 0` |
| `🎯 Bandit: 19/12 ✅ HIT` | `chip-hit` / `chip-miss` / `chip-crit` | `auto_attack_hit != null` |
| `🎲 −7 fire` | `chip-damage` | `auto_attack_damage_applied > 0` |
| `📋 Pip WIS save · DC 14` | `chip-prompt` | `auto_save_target_kind == "pc"` |
| `📋 Bandit: 8/14 ❌ failed` | `chip-hit` / `chip-miss` | `auto_save_target_kind == "npc"` |
| `🎲 −12 fire (half)` | `chip-damage` | `auto_save_damage_applied > 0` |
| `🥶 Paralyzed · 10r` | `chip-buff` | `auto_save_buff_name` set |
| `↶ Undo` | `chip-undo` button | any HP was actually applied |

Utility-only casts (Mage Armor, Misty Step) have no auto-resolution outcomes — the pill row is omitted entirely.

### `▾ details` (collapsed by default)

| Field | Purpose | Example |
|-------|---------|---------|
| `spell_desc` | RAW spell text from the SRD JSON | "A creature of your choice…" |

The body row + the pill row carry the actionable info. The spell description is reference reading; it stays tucked behind the toggle.

### Auto-resolution suppresses redundant buttons

When the server resolved the spell's attack / save / damage / heal, the manual "🎲 Roll {damage}" / "📋 Prompt save" / "🩹 Apply Healing" buttons on the card are **not rendered** (introduced v2.42.3). The outcome is in the pill row + the ↶ Undo pill. Spells with no auto path (Magic Missile, utility spells) keep their manual buttons.

---

## 4. `feature_used` — class features, racial traits, items

Emitted by `/use_feature`, `/use_rage`, `/use_second_wind`, `/use_cutting_words`, `/use_lay_on_hands`, etc. v2.43.0 inlined the description tail with the feature name (it used to live in a `▾ details` block); the source chip moved into the header.

### Header (always visible)

```
✨  Garrik Ironside  [→ Target?]  [Class Feature]   03:15 PM
```

| Field | Purpose | Example |
|-------|---------|---------|
| `character_name` | Who used it | `Garrik Ironside` |
| target tag (when set) | For features that target a character | `→ Pip` |
| source chip (v2.42.3) | `Class Feature` / `Item` / `Racial Trait` / `Feat` | `Class Feature` |
| `time` | Local clock | `03:15 PM` |

### Body row (always visible)

```
💨 Second Wind · Bonus action · (0/1 left)
```

Feature name + an inline `feature_desc` tail + an optional remaining-uses counter — all on the same line. Long descs wrap; short ones stay inline.

### Outcome pill row (when the feature healed someone)

Features that broadcast `heal_amount > 0` render an oversized heal pill, parallel to the spell-cast pill row:

| Pill | When it fires |
|------|---------------|
| `✚ Garrik +9 HP (25 → 34)` | Second Wind, when `actual_healed > 0` |
| `✚ Pip +5 HP (12 → 17)` | Lay on Hands, when `actual_healed > 0` |

Features that don't heal (Cunning Action, Rage, Channel Divinity, Action Surge, Cutting Words, Bardic Inspiration, Arcane Recovery) have no pill row.

### `▾ details` (collapsed by default — only when the desc is too long for the inline tail)

If `feature_desc` is short, it's inline. If a feature emits a longer description (paragraph of rules text), the same `▾ details` pattern can still wrap it (today only `feature_desc` strings have an inline path).

---

## 5. Persistence

All four card types **survive page refreshes** (v2.28.0 — `simplevtt:rolllog:${CAMPAIGN_ID}` localStorage). Plus the legacy heal-apply result rows (v2.29.1). Open state on `<details>` toggles does **not** persist — refreshing a card reverts it to collapsed. Acceptable: the header + pill row carry the at-a-glance info; details are reference-only.

The roll log is capped at the most recent 100 WS-only entries (FIFO trim). Server-rendered `roll` rows from the DB (the Jinja `{% for r in rolls %}` block) are not in the localStorage buffer — they come down on every page load fresh.

---

## 6. Visibility filter

`roll` events carry a `visibility` field with three legal values:

| Visibility | Reaches |
|------------|---------|
| `public` (default) | Everyone in the campaign |
| `gm_and_roller` | Just the GM + the rolling user |
| `gm_only` | Just the GM |

The filter is enforced both server-side (`/roll` broadcasts only to eligible sockets) and client-side (`appendRoll` re-checks before rendering — defense-in-depth). The v2.39.0 GM-only concentration log entry uses `gm_only`.

`weapon_attack` / `spell_cast` / `feature_used` are always public — they reflect public table actions.

---

## 7. Where the code lives

- **Card rendering:** `app/static/tabletop.js` — `appendRoll`, `appendSpellCast`, `_appendFeatureUsed`, `appendWeaponAttack`, `appendRollRequest`.
- **Outcome pill row:** same file — `_spellResultPillsHtml(d)` (v2.43.0). Emits the row of pills based on `auto_*` payload fields.
- **Persistence:** same file — `_persistRollEntry` + `_hydrateRollLog`. localStorage key `simplevtt:rolllog:${CAMPAIGN_ID}`.
- **Pill CSS + inline-meta styles:** `app/templates/tabletop.html` — `.result-pill`, `.result-pills`, `.spell-cast-name-row`, `.spell-cast-meta-inline`, `.feature-used-name-row`, `.feature-used-desc`, `.feature-used-counter` rules at the top of the inline `<style>` block.
- **Semantic colors (`--c-heal` / `--c-crit` / `--c-damage` / `--c-buff`):** `app/static/style.css`, with light-theme overrides for legibility on `[data-theme="light"]` + `[data-theme="bubblegum"]`.
- **Dice toast (separate transient surface):** `app/static/roll_toast.js`. Fires for every server roll; respects the visibility filter.

---

## Changing this layout

If you add a new card type or move a field between the header / body / pill row / details section, update this file in the same commit. Convention:

- New card type → new H2 section here with the field tables.
- New pill type → new row in the table under "Outcome pill row" in section 3 (spells) or 4 (features).
- Visibility / persistence changes → update sections 5 + 6.
