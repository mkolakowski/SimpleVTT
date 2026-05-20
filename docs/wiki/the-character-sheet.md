# The character sheet

**Audience:** players + GMs needing to navigate the most-touched UI surface in the app.
**Version stamp:** v2.43.19.

The character sheet is where players spend most of their time. SimpleVTT renders it in two surfaces with the same data underneath: the **full sheet** (own-page view, accessed via the topnav or `/character/{id}/sheet`) and the **mini-sheet** (modal-style panel that opens when you click a token on the tabletop). Both share the same sections, the same edit gestures, and the same WebSocket sync — changes in one show up in the other immediately.

This guide walks the D&D 5e sheet (`sheet_dnd5e.html`). The generic system sheet (`sheet_generic.html`) is simpler — same anatomy, fewer sections.

## Two surfaces, one data model

| Surface | URL / trigger | When to use |
|---------|---------------|-------------|
| **Full sheet** | `/character/{id}/sheet` (linked from `/characters` and the topnav user menu) | Long-form work — editing your character, planning a level-up, reviewing class features. |
| **Mini-sheet** | Tabletop view → click your token | In-session quick actions — clicking Strike, casting a spell, applying healing. |

Both render the same Jinja template (`app/templates/sheet_dnd5e.html`) with slightly different scaffolding around it. Any field edit broadcasts `character_update` or `character_hp_update` (the lightweight delta) so the other surface re-renders without a refresh.

## Section anatomy (top to bottom)

The full sheet is a single scrollable column. Sections from top to bottom:

### 1. Header / identity

Portrait + name + class + level + race + background. Right side: HP bar, AC, Initiative, action-economy chip strip.

| Field | Edit gesture | What happens |
|-------|--------------|--------------|
| **Portrait** | Click → upload image | Persists to the `uploads_data` volume; reflected on the token + the init tracker. |
| **Color** | Color picker swatch | Broadcasts `character_color_update` → token ring + sheet header re-tint. |
| **Ring style** | Style picker | Broadcasts `character_ring_update` → token outline (solid / dashed / glow / double / spiked). |
| **Name / class / level / race / background** | ✏ Edit button (top-right of the header) | Opens an editable form; ✓ Done commits. Multi-class supported via the **+ Add Class** button. |

### 2. HP block

HP current / max / temp inputs. Death-save tracker overlay appears here when the character is dying. The HP bar at the top of the sheet reflects this block in real time.

| Field | Edit gesture | What happens |
|-------|--------------|--------------|
| **HP current** | Type a number, blur the input | Broadcasts `character_hp_update`. Crosses the death-save state machine if the change passes 0 (dying), comes back from 0 (resets dying), or is "massive damage" (instant kill check). |
| **HP max** | Type a number | Updates the max. The bar re-scales. Apply-sum-to-max button below derives the max from your hit dice if you've been recording them. |
| **HP temp** | Type a number | Damage absorbs temp HP first, then current. Cleared on long rest. |
| **Death-save checkboxes** | Click | Manually adjust the tracker. Each click broadcasts `character_death_save`. |
| **Long Rest / Short Rest buttons** | Click | Reset HP + hit dice + spell slots + class-feature counters per rest type. Broadcasts `long` or `short`. |

### 3. Action-economy chip strip

Always visible at the top of the sheet. Four chips: **⚔ Act / 💨 Bns / 🛡 Rxn / 👣 Mov** (movement counter to the right).

- **Lit** = used this turn. **Dim** = unused.
- **GM Shift-click** = manual toggle.
- **Players** can't toggle directly — chips flip server-side when they click a spell / weapon / feature.

For the design rationale + the over-budget gate, see `docs/plans/action-economy.md` (the dedicated wiki guide is on the TODO list).

### 4. Ability scores + saving throws

Six rows: STR / DEX / CON / INT / WIS / CHA. Each row has the score, the modifier (computed), the saving throw modifier, and a d20 button to roll the save.

| Field | Edit gesture | What happens |
|-------|--------------|--------------|
| **Score** | ✏ Edit → number input → ✓ Done | Updates the score; modifier recomputes; downstream skill bonuses + spell DCs all re-derive. |
| **Save proficiency** | Edit mode → checkbox | Adds proficiency bonus to the save mod. Class-derived proficiencies are pre-set. |
| **d20 button** | Click | Posts `/roll` with `1d20 + save_mod`, label `<ability> save`. Broadcasts `roll`. |

The "Advantage / Disadvantage" buttons next to the dice roller pre-set the next roll's state (broadcasts `character_roll_state`). The dice toast renders both d20s with the kept one highlighted.

### 5. Skills

All 18 skills in a table: skill name, ability, proficiency checkboxes (None / Proficient / Expertise), the computed total, and the d20 roll button. Edit mode lets you check / uncheck proficiency + expertise; the bonus auto-derives.

Skills are clickable from the **monster mini-sheet** too (v2.4.10) — the GM picks a skill on a monster and the bonus is rolled instantly.

### 6. Combat

Attacks list: weapons + custom attacks. Each row shows:

- **Name** (clickable to expand the dice breakdown)
- **Attack bonus** (auto-derived from ability + proficiency, or hand-set on custom attacks)
- **Damage expression** (e.g. `1d8+3 slashing`)
- **Range**
- **🗡 Strike** button — POSTs `/attack`, broadcasts `weapon_attack`, fires the attack + damage dice toasts, lands the roll-log card

The **Browse Items** button opens the SRD weapon list to drop a new weapon onto the sheet. **+ Custom** lets you hand-roll a custom attack (NPC abilities, homebrew weapons).

For the auto-resolution flow when a target is set, see the [running a session as GM guide](running-a-session-as-gm.md#auto-resolution-outcomes).

### 7. Spells

Spell-slot tracker at the top — current / max per level. Spell list below, grouped by level. Each spell row:

- **Name** (clickable to expand description + actions)
- **Level / school** (`Lv 1 · Evocation`)
- **Casting time / range / components**
- **Damage / save DC** if applicable
- **🪄 Cast** button + a spell-slot-level picker (so you can upcast)

Clicking **Cast** POSTs `/cast_spell` which fires the full auto-resolution pipeline (heal, attack, save — see [endpoint catalog](endpoint-catalog.md#cast_spell)).

Cantrips don't consume slots; their damage tier auto-scales at L5 / L11 / L17 (v2.36.0).

### 8. Class features

The big section. Per-class features grouped by level. Each feature is a collapsible row:

- **Name + level chip** (e.g. `Second Wind · Lv 1 Fighter`)
- **Description** (RAW text from the SRD)
- **⚡ Use** button (for features that announce / trigger a side effect)
- **Counter** if the feature has limited uses (`(1/1 left)`)

Some features open a picker before firing — Channel Divinity options, Wild Shape beast picker, Cunning Action (Dash / Disengage / Hide). The picker collects the option, then POSTs `/use_feature` (or a dedicated endpoint like `/use_second_wind`).

Features with `desc` populated render the inline description on the roll-log card (v2.43.11 server-side fallback for the curated feature table).

### 9. Inventory

Items list with quantity, weight, description. **+ Add** opens the SRD item browser or a custom-item form. **🧪 Use** on a potion / wand / scroll triggers `/use_item` — which auto-applies the heal for potions of healing (v2.5.0 house rule: potions are a bonus action).

### 10. Description / notes

Free-form text fields for backstory, personality traits, ideals, bonds, flaws. Save on blur. Not broadcast (private to the character).

## Mini-sheet specifics

The mini-sheet (token click on the tabletop) renders the same sections in a stacked modal panel. Differences:

- **Collapsible section headers.** The mini-sheet folds the long page into expandable headers; click each to expand. Tap-friendly for iPad / touch.
- **No "Edit" gestures.** The mini-sheet is read-only for editing — use the full sheet for those.
- **Spell + Action rows are always expanded.** Faster click-to-Cast / click-to-Strike during play.
- **GM sees mini-sheets for every token.** Players see their own + any NPCs the GM has marked visible.

The mini-sheet is what the GM uses to drive monster turns — click the bandit's token, the bandit's mini-sheet opens, click **Strike** on its weapon.

### Sample mini-sheet

Here's how Krieger's mini-sheet looks during a session. Theme-aware — the markup uses the same CSS custom properties as the live mini-sheet, so it re-tints when you switch themes.

<div style="max-width:340px;margin:14px auto;border:1px solid var(--border);border-radius:8px;background:var(--bg-2);overflow:hidden;box-shadow:0 6px 18px rgba(0,0,0,0.25);font-size:12px;line-height:1.4;">
  <!-- ── Mini-header (always visible) ── -->
  <div style="display:flex;align-items:flex-start;gap:8px;padding:8px 10px 7px;background:linear-gradient(135deg,rgba(167,139,250,.15),rgba(108,180,255,.10));border-bottom:2px solid var(--accent);">
    <div style="width:38px;height:38px;border-radius:50%;background:color-mix(in srgb,var(--accent) 20%,transparent);display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;border:2px solid var(--accent);">🪓</div>
    <div style="flex:1;min-width:0;">
      <div style="font-size:13px;font-weight:700;color:var(--fg);">Krieger Stonefist</div>
      <div style="font-size:10px;color:var(--accent);margin-top:2px;opacity:.85;">Lv 5 Barbarian (Berserker) · Half-Orc</div>
    </div>
    <div style="font-size:10px;color:var(--fg-mute);text-align:right;flex-shrink:0;">
      <div style="font-weight:700;color:var(--fg);">AC 14</div>
      <div>Init +2</div>
    </div>
  </div>

  <!-- ── HP block ── -->
  <div style="padding:8px 10px;border-bottom:1px solid var(--border);">
    <div style="display:flex;align-items:center;justify-content:space-between;font-size:11px;color:var(--fg-mute);margin-bottom:4px;">
      <span style="color:var(--fg);font-weight:600;">HP</span>
      <span><strong style="color:var(--c-heal);font-size:14px;">38</strong> / 49</span>
    </div>
    <div style="height:8px;background:var(--bg);border-radius:4px;overflow:hidden;border:1px solid var(--border);">
      <div style="width:78%;height:100%;background:var(--c-heal);"></div>
    </div>
  </div>

  <!-- ── Action-economy chip strip ── -->
  <div style="padding:6px 10px;display:flex;gap:5px;border-bottom:1px solid var(--border);">
    <span style="flex:1;text-align:center;padding:4px 6px;border:1.5px solid var(--c-damage);background:color-mix(in srgb,var(--c-damage) 18%,transparent);border-radius:4px;font-size:10px;font-weight:600;color:var(--c-damage);">⚔ Act</span>
    <span style="flex:1;text-align:center;padding:4px 6px;border:1.5px solid var(--border);background:var(--bg);border-radius:4px;font-size:10px;color:var(--fg-mute);">💨 Bns</span>
    <span style="flex:1;text-align:center;padding:4px 6px;border:1.5px solid var(--border);background:var(--bg);border-radius:4px;font-size:10px;color:var(--fg-mute);">🛡 Rxn</span>
    <span style="flex:1;text-align:center;padding:4px 6px;border:1.5px solid var(--border);background:var(--bg);border-radius:4px;font-size:10px;color:var(--fg-mute);">👣 0/30</span>
  </div>

  <!-- ── Buff chips (active conditions) ── -->
  <div style="padding:6px 10px;border-bottom:1px solid var(--border);display:flex;gap:4px;flex-wrap:wrap;">
    <span style="display:inline-flex;align-items:center;gap:3px;padding:3px 8px;border:1.5px solid var(--c-buff);color:var(--c-buff);background:color-mix(in srgb,var(--c-buff) 12%,transparent);border-radius:12px;font-size:11px;font-weight:600;">😤 Rage <span style="color:var(--fg-mute);font-weight:400;">9 rounds</span></span>
  </div>

  <!-- ── ⚔ Attacks (always expanded) ── -->
  <div>
    <div style="display:flex;align-items:center;gap:6px;padding:6px 10px;background:color-mix(in srgb,var(--accent) 8%,transparent);border-bottom:1px solid var(--border);font-size:11px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:0.4px;">
      <span>⚔ Attacks</span>
    </div>
    <div style="padding:6px 10px;">
      <div style="display:flex;align-items:center;justify-content:space-between;padding:5px 0;border-bottom:1px dashed var(--border);">
        <div style="flex:1;min-width:0;">
          <div style="font-weight:600;font-size:12px;color:var(--fg);">🪓 Greataxe</div>
          <div style="font-size:10px;color:var(--fg-mute);">+7 to hit · 1d12+5 slashing · 5 ft.</div>
        </div>
        <button style="background:transparent;border:1.5px solid var(--c-damage);color:var(--c-damage);border-radius:14px;padding:4px 10px;font-size:11px;font-weight:600;font-family:inherit;cursor:pointer;">🗡 Strike</button>
      </div>
      <div style="display:flex;align-items:center;justify-content:space-between;padding:5px 0;">
        <div style="flex:1;min-width:0;">
          <div style="font-weight:600;font-size:12px;color:var(--fg);">🗡 Handaxe (thrown)</div>
          <div style="font-size:10px;color:var(--fg-mute);">+5 to hit · 1d6+3 slashing · 20/60</div>
        </div>
        <button style="background:transparent;border:1.5px solid var(--c-damage);color:var(--c-damage);border-radius:14px;padding:4px 10px;font-size:11px;font-weight:600;font-family:inherit;cursor:pointer;">🗡 Strike</button>
      </div>
    </div>
  </div>

  <!-- ── ✨ Class features (collapsible) ── -->
  <details style="border-top:1px solid var(--border);">
    <summary style="list-style:none;display:flex;align-items:center;gap:6px;padding:6px 10px;background:color-mix(in srgb,var(--accent) 8%,transparent);font-size:11px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:0.4px;cursor:pointer;">
      <span style="font-size:9px;">▶</span>
      <span>✨ Class Features</span>
      <span style="margin-left:auto;font-size:10px;color:var(--fg-mute);text-transform:none;font-weight:400;letter-spacing:0;">3 features</span>
    </summary>
    <div style="padding:6px 10px;font-size:11px;color:var(--fg-mute);">
      <div style="padding:5px 0;border-bottom:1px dashed var(--border);">
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <strong style="color:var(--fg);font-size:12px;">😤 Rage</strong>
          <span style="font-size:10px;color:var(--fg-mute);">(2/3 left)</span>
        </div>
        <div style="font-size:10px;font-style:italic;margin-top:2px;">+damage on STR melee, advantage on STR checks/saves, resistance to bludgeoning/piercing/slashing.</div>
      </div>
      <div style="padding:5px 0;border-bottom:1px dashed var(--border);">
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <strong style="color:var(--fg);font-size:12px;">⚡ Reckless Attack</strong>
        </div>
        <div style="font-size:10px;font-style:italic;margin-top:2px;">Gain advantage on STR melee attacks this turn — but attacks against you have advantage until next turn.</div>
      </div>
      <div style="padding:5px 0;">
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <strong style="color:var(--fg);font-size:12px;">💢 Frenzy</strong>
        </div>
        <div style="font-size:10px;font-style:italic;margin-top:2px;">While raging, make a single melee weapon attack as a bonus action each turn. Exhaustion when rage ends.</div>
      </div>
    </div>
  </details>

  <!-- ── 🧪 Inventory (collapsible) ── -->
  <details style="border-top:1px solid var(--border);">
    <summary style="list-style:none;display:flex;align-items:center;gap:6px;padding:6px 10px;background:color-mix(in srgb,var(--accent) 8%,transparent);font-size:11px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:0.4px;cursor:pointer;">
      <span style="font-size:9px;">▶</span>
      <span>🧪 Inventory</span>
      <span style="margin-left:auto;font-size:10px;color:var(--fg-mute);text-transform:none;font-weight:400;letter-spacing:0;">8 items</span>
    </summary>
  </details>

  <!-- ── 🎯 Abilities + skills (collapsible) ── -->
  <details style="border-top:1px solid var(--border);">
    <summary style="list-style:none;display:flex;align-items:center;gap:6px;padding:6px 10px;background:color-mix(in srgb,var(--accent) 8%,transparent);font-size:11px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:0.4px;cursor:pointer;">
      <span style="font-size:9px;">▶</span>
      <span>🎯 Abilities &amp; Skills</span>
    </summary>
  </details>
</div>

<p style="text-align:center;font-size:11px;color:var(--fg-mute);margin-top:-8px;font-style:italic;">A live mini-sheet for a Lv 5 Barbarian, mid-fight (action spent, raging). Click a section header to fold / unfold — the mock above uses native <code style="font-style:normal;">&lt;details&gt;</code> so the chevrons work right here in your browser.</p>

Key things to notice:

- **Header chrome** uses the same accent-gradient + 2 px accent border-bottom as every other card in the app.
- **HP bar** colors track the threshold tints (green at 78% — the HP threshold tints in campaign settings can flip this to amber / orange / red at lower percentages).
- **Chip strip** lights up the spent action chip (Act burned, Bns / Rxn unspent, Mov shows remaining out of total).
- **Buff chips** carry an icon + name + the rounds-remaining tail (v2.43.7 — "rounds" spelled out instead of the cryptic "r" suffix).
- **Attacks section is always expanded** — Strike buttons are one tap away. Other sections (features, inventory, abilities) collapse so the modal stays compact.
- **The whole panel is one CSS column** — on mobile / iPad it scrolls naturally; on desktop it fits in a side modal.

## Realtime sync

Every edit on the sheet broadcasts a WS message so other clients re-render without a refresh:

| Edit | Broadcast | Re-render scope |
|------|-----------|----------------|
| HP input | `character_hp_update` | HP bar on the token + tracker + open sheets. Lightweight delta. |
| Death-save click | `character_death_save` | Death-save overlay on the sheet + tracker. May change `status` to `dying` / `dead` / `stable`. |
| Color / ring style | `character_color_update` / `character_ring_update` | Token ring + sheet header. |
| Resource counter (class feature) | `resource_update` | Counter chip on the sheet + tracker. |
| Spell slot spend | `spell_slot_update` | Slot tracker. |
| Buff install / remove | `buff_update` | Buff chips on the sheet + tracker. |
| Big edit (name, class, ability score) | `character_update` | Full sheet refresh on other clients. |
| Roll state (adv/dis) | `character_roll_state` | The next-roll banner above the dice roller. |
| Wild Shape | `transform_update` | Mini-sheet swaps to the beast form. |

Two important notes:

1. **Optimistic update + server reconcile.** The sheet updates its own state immediately on edit (so the player sees the change instantly), THEN waits for the server's confirmation broadcast. If the server reconciles to a different value (rare — only happens with concurrent edits), the broadcast wins.
2. **Page Visibility API throttling.** When the sheet tab is backgrounded, periodic refetches (resource counters, buff timers) pause. They resume + fire one catch-up fetch when the tab becomes visible again. Avoids burning network on a tab the player isn't looking at.

## Editing flow

The sheet has two states: **read** (numbers, dice buttons, chip strip — interactive but values are display-only) and **edit** (✏ buttons turn into editable inputs / dropdowns / pickers).

Convention: every section that supports edit has an ✏ Edit button in its header. Click it to enter edit mode; click ✓ Done to exit. Some sections (HP, death saves, resource counters) are always editable since they change frequently in-session.

The header has a special **✏ Edit** button that opens the **character editor** — name / class / level / race / background / feats / multi-class controls in one modal. Use this for level-ups and big identity changes.

## Sheet for GMs

GMs see every character's sheet, both via the topnav (`/characters`) and via clicking any token on the tabletop. The GM-side editing has no extra controls today — same gestures as the player. Two-tab edit etiquette: if the player is on the sheet, the GM should avoid simultaneous edits (race-condition surface; see the optimistic-update note above).

## Mobile / iPad

The sheet is touch-responsive. v2.4.24–v2.4.29 shipped a series of debounce + double-fire fixes for iPad Safari + trackpad gestures — these keep the mini-sheet's expandable row headers from double-firing when you tap them. If you see double-cast / double-strike on your iPad, file an issue with the device model — there are still corner cases.

The full sheet is also touch-friendly but works better on desktop / laptop because of the column width.

## Where the code lives

- **Sheet templates:** `app/templates/sheet_dnd5e.html` (D&D 5e — main one; 7000+ lines), `app/templates/sheet_generic.html` (system-agnostic).
- **Sheet-side JS** (most lives inline in the template; some helpers are in `/static/`):
  - `app/static/action_buttons.js` — the shared action-button renderer used by every spell / feature row.
  - `app/static/dnd5e_class_resources.js` — per-class resource registry.
  - `app/static/dnd5e_feature_economy.js` — per-feature slot table.
- **Sheet-fields PATCH endpoint:** `/api/campaign/{cid}/character/{cid}/sheet-fields` — accepts any subset of sheet fields + optional `hp_change_reason`. Broadcasts `character_hp_update`.
- **HP edits + death save:** `_apply_hp_change` in `app/routes/tabletop_routes.py`.
- **Mini-sheet modal:** `app/templates/tabletop.html` `#mini-sheet-modal` block + `openMiniSheet` in `app/static/tabletop.js`.

## Related guides

- **[Running a session as GM](running-a-session-as-gm.md)** — for the in-session context where the sheet is most used.
- **[Endpoint catalog](endpoint-catalog.md#character--sheet)** — what each sheet edit POSTs.
- **[Realtime broadcasts catalog](realtime-broadcasts-catalog.md)** — what each edit broadcasts.
- **[Roll-log guide](roll-log-guide.html)** + **[Toast notifications guide](toast-notifications-guide.html)** — for the feedback when sheet actions fire.
