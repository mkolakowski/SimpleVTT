# Reactions Automation — Design Plan

**Status:** 🟠 Phases 1a (v2.67.0) + 1b (v2.67.1) + 2a-partial (v2.67.2) + 2b-partial (v2.68.5) + 2 catalog (v2.68.6–v2.68.11) + 3a-partial (v2.69.0) shipped. Phase 1a: server-side foundation — `reaction_prompt` broadcast + `/use_reaction` endpoint + `_eligible_reactions` + `_emit_reaction_prompt` + schema v60 `users.reaction_prompt_mode` + OA exit-reach retrofit. Phase 1b: client popup UI (`reaction_prompt.js`) + `/api/settings/reaction_prompt_mode` endpoint + radio-group toggle on `/settings`. Phase 2a-partial: Uncanny Dodge surfaces through the prompt pipeline (ack-only — auto-fire preserved). v2.67.3: NPC watchers consume their reaction slot via `_mark_battle_economy_by_combatant_id`. **v2.68.0 ("The GM's Console") ships the GM Reactions Panel** — manual-spend bypass for any reaction. v2.68.1: Polearm Master + Sentinel emit `reaction_prompt` alongside their legacy `feature_used` advisories. **v2.68.5 ("Bards and Bulwarks") — Phase 2b partial:** Cutting Words + Indomitable endpoints now emit `reaction_prompt(reaction_used)` acks. **v2.68.6 ("Stance and Sting") — Phase 2b continuation:** Battle Master maneuvers (Riposte / Parry / Brace) + Deflect Missiles added to the GM Reactions Panel catalog. **v2.68.7 ("Stand and Shield") — Phase 2c:** Protection + Interception fighting styles added to the catalog. **v2.68.8 ("Faith and Fey") — Phase 2d:** Warding Flare (Cleric Light) + Wrath of the Storm (Cleric Tempest) + Misty Escape (Warlock Archfey Lv 6+) added to the catalog with a shared subclass-slug normalization pipeline. **v2.68.9 ("Crown and Chorus") — Phase 2e:** Mantle of Inspiration (Bard Valor Lv 3+) + Rebuke the Violent (Paladin Crown Lv 7+ Channel Divinity) added to the catalog. **Phase 2 is now ✅ shipped on the catalog side** — every class-feature reaction in the plan doc's category A is surfaced (or filed with explicit per-mechanic notes). **v2.69.0 ("The Arcane Aegis") — Phase 3a partial:** Shield spell is the first reaction *spell* wired to a runtime trigger event (`attack_targeted`). `/attack` against a PC target now emits `reaction_prompt` with a `cast-shield` option (AC math preview in label, lowest available 1st+ slot); `/use_reaction` consumes the slot, marks the reaction, and installs a `shield-active` buff (`ac_bonus=5` + `immune_magic_missile` + `duration_rounds=1`). Retroactive negation of the triggering hit is filed as v1 limitation — popup tells the player whether the new AC would have made the hit miss; the v3 pending-damage state machine is the long-term fix. **v2.70.0 ("The Silence") — Phase 3b partial:** Counterspell is the second reaction spell wired to a runtime trigger. New `spell_cast_near` event fires from `/cast_spell` + `/npc_cast_spell` for every PC watcher within 60 ft of the caster who has Counterspell prepared + a 3rd+ slot available. `/use_reaction` consumes the slot, marks reaction, broadcasts `feature_used(source=counterspell-cast)` with `outcome_hint` (`auto` when slot ≥ incoming level, `check` with `arcana_check_dc` otherwise). RAW arcana-check roll + auto-undo of the original cast filed for v3 alongside the pending-damage state machine. **v2.71.0 ("The Devil's Bargain") — Phase 3c partial:** Hellish Rebuke + Absorb Elements wired to the existing `damage_taken` event. Second `_emit_reaction_prompt(damage_taken)` site in `_apply_damage_to_combatant`'s PC branch (after `_log_damage_entry`) gated on `applied > 0 AND not uncanny_dodge_used AND not reaction_used`; `_eligible_reactions[damage_taken]` now returns a LIST so UD ack + HR + AE can coexist. Hellish Rebuke dispatch consumes lowest 1st+ slot, marks reaction, broadcasts `feature_used(source=hellish-rebuke-cast)` with `damage_expr` + `damage_type=fire` + `rebuke_target_*` fields. Absorb Elements dispatch installs `absorb-elements-active` buff with `effects.resistance_damage_type`, `effects.next_melee_bonus_dice`, `effects.next_melee_bonus_type`. v1 limitations filed: auto-damage to rebuked attacker, resistance pipeline reading buff effects, next-melee bonus damage pipeline reading buff effects, demo PC fixture for Absorb Elements. Phase 3d (Silvery Barbs + `save_failed`) / 3e (Feather Fall + `falling`) still ⚪.
**Companion to:** [`docs/plans/class-content-status.md`](class-content-status.md) (the content catalog) and the v2.66.0+ OA/Sentinel trigger work.

---

## Goal

When a player has a reaction available (their `combatant.economy.reaction === false`) AND a trigger event fires for which one of their reaction-bearing features, spells, or items is eligible, **prompt them to spend it**. The prompt should:

1. Surface every eligible reaction for that trigger, with the **resource cost** + **expected effect** + a **one-click spend button**.
2. Render in both the **roll log** (durable, scrollable, audit-friendly) and a **transient popup toast** (immediate, dismissible) so the player can't miss it mid-combat.
3. Auto-dismiss when the trigger resolves (e.g. the damage applies, the spell resolves) and the reaction was either spent or explicitly declined.
4. Never silently consume the reaction — the player has to click. Auto-fire is a footgun (Uncanny Dodge today auto-spends and players occasionally complain that they wanted to save it for a bigger hit).

The goal is to close the gap between *"this trigger happened"* (v2.66.x advisories) and *"the player actually used the reaction"* (still manual chip-clicking today).

---

## Existing surfaces

What's already shipped that this plan builds on:

| Surface | Version | What it does | What's missing |
|---------|---------|--------------|----------------|
| `economy.reaction: bool` on every combatant | v2.4.31 | Per-combatant slot, flipped by `_mark_battle_economy` (server) or chip click (client). | No "consumed by what" attribution. |
| Reaction-chip click in init tracker (`tabletop.html:4576`) | v2.4.31 | Manual toggle. | Player has to know WHICH reaction they spent — no menu of options. |
| Turn-start reset (`tabletop.html:6471-6474`) | v2.4.31 | Resets all 4 economy slots when `turn_index` advances. | Client-only — non-GM clients can't authoritatively reset. |
| Auto-consume — Uncanny Dodge | v2.49.243 | Server auto-flips reaction + halves damage in `_apply_damage_to_combatant`. | No "decline" path; fires every hit while available. |
| Auto-consume — Cutting Words | v2.54.0 | `/use_cutting_words` endpoint marks the reaction. | Player has to know to call the endpoint — no proactive prompt. |
| OA exit-reach advisory | v2.66.0 | Move endpoint broadcasts `feature_used(source="opportunity-attack-trigger")` per provoked watcher. | Pure advisory — player must click Attack manually. |
| Polearm Master enter-reach advisory | v2.66.4 | Same broadcast shape with `trigger_type="enter"`. | Same — advisory only. |
| Sentinel ally-attacked-near-you advisory | v2.66.5 / v2.66.6 | `/attack` + `/npc_attack` broadcast `feature_used(source="sentinel-attack-trigger")`. | Same — advisory only. |

**Common gap:** there's no central **reaction prompt** that says *"these are the reactions you could spend right now"*. Each existing surface is bespoke. This plan unifies them.

---

## Architecture

### 1. A new `reaction_prompt` WS broadcast type

Triggers a client-side popup AND a roll-log entry. Payload shape:

```json
{
  "type": "reaction_prompt",
  "data": {
    "prompt_id": "rxn_<uuid>",
    "campaign_id": 1,
    "watcher_combatant_id": "tok_oa_3",
    "watcher_char_id": 4,
    "watcher_name": "Sir Caelan Lightbringer",
    "watcher_user_id": 7,
    "trigger_event": "damage_taken",
    "trigger_summary": "Krieger took 14 slashing damage from Bandit Captain.",
    "expires_at": "2026-05-26T18:42:10Z",
    "options": [
      {
        "key": "shield",
        "label": "✨ Shield (+5 AC)",
        "kind": "spell",
        "slot_level": 1,
        "resource_cost": "1st-level spell slot",
        "endpoint": "/api/campaign/1/use_reaction",
        "endpoint_body": {
          "watcher_char_id": 4,
          "reaction_key": "shield",
          "prompt_id": "rxn_<uuid>"
        },
        "available": true,
        "unavailable_reason": null
      },
      {
        "key": "uncanny-dodge",
        "label": "🛡️ Uncanny Dodge (halve damage)",
        ...
      }
    ]
  }
}
```

**Per-user routing.** Today's broadcasts fan out to every WS client in the campaign. The popup should only appear for the **watcher's owning user** (or the GM if the watcher is an NPC). Add a `target_user_ids: list[int]` field to the broadcast payload; the client renders the popup ONLY if its `ME.id` is in the list. Roll-log entry still shows for everyone (auditable history) but the spend buttons render disabled for non-watchers.

### 2. A new `/use_reaction` endpoint

Single entry point for spending ANY reaction. Routes to per-reaction handlers (analogous to how `/use_<feature>` endpoints already work, but consolidated). Body:

```json
{
  "watcher_char_id": 4,
  "reaction_key": "shield",  // matches the option.key from the prompt
  "prompt_id": "rxn_<uuid>",  // for replay-attack guard + telemetry
  "params": { "slot_level": 1 }  // per-reaction extras
}
```

Server: validate `economy.reaction === False` (over-budget gate), validate the reaction is in the prompt's option list (replay guard), dispatch to the handler, mark the reaction slot, broadcast the effect (`shield_buff_installed`, `attack_damage_halved`, etc.), broadcast a `reaction_prompt_resolved` event to clear the popup.

### 3. Trigger-event taxonomy

Every reaction has one of N trigger events. Define them once:

| Trigger event | Fires on | Reactions that listen |
|---------------|---------|----------------------|
| `damage_taken` | `_apply_damage_to_combatant` (PC branch) | Uncanny Dodge, Shield (if pre-damage), Hellish Rebuke, Absorb Elements, Heroic Sacrifice, Wrathful Smite spell, Cloak of Displacement (item) |
| `attack_targeted` | `/attack`, `/npc_attack` — fires BEFORE the d20 roll | Shield, Cutting Words, Lucky (feat), Cloak of Displacement |
| `spell_cast_near` | `/cast_spell`, `/npc_cast_spell` (within range) | Counterspell, Silvery Barbs (post-save) |
| `save_failed` | `/roll_request/{id}/respond` with `total < dc` | Indomitable (v2.56.0), Silvery Barbs, Lucky, Bardic Inspiration (Cutting Words sister-use) |
| `ally_attacked_near` | `/attack`, `/npc_attack` with attacker ≤ 5 ft of watcher, target ≠ watcher | **Sentinel (v2.66.5+)**, Protection fighting style |
| `creature_exits_reach` | `/move` when a watcher's reach is exited | **OA exit (v2.66.0)** |
| `creature_enters_reach` | `/move` when a watcher's reach is entered (Polearm Master only) | **OA enter (v2.66.4)** |
| `falling` | Fall damage (not yet modeled — file) | Feather Fall, Slow Fall |
| `crit_against_you` | When the attack roll is a crit | Lucky, possibly Shield (RAW Shield doesn't help vs a confirmed crit but the prompt should still fire so the player decides) |
| `ally_drops_to_zero` | `_apply_hp_change` with `new_hp <= 0` for an ally | Healing Word (if cast as bonus action — not strictly a reaction but the prompt shape is the same; reserve for future) |

The trigger event becomes the **filter key** the server uses to find matching reactions in each watcher's catalog.

### 4. Per-character reaction catalog

Each character's sheet gets a derived **reaction inventory** computed on-the-fly from:
- `sheet.feats` — slug matches against `_REACTION_FEATS` (Sentinel, Polearm Master, Lucky, War Caster, Mage Slayer, Shield Master).
- `sheet.class_features` — slug matches against `_REACTION_CLASS_FEATURES` (Uncanny Dodge, Cutting Words, Riposte, Protection, etc.).
- `sheet.spells` — filter by `casting_time` containing "reaction" (Shield, Counterspell, Hellish Rebuke, Absorb Elements, Feather Fall, Silvery Barbs, Wrathful Smite-as-reaction).
- `sheet.inventory` — filter by item slug being in `_REACTION_ITEMS` (Cloak of Displacement, Ring of Spell Turning).

Computed once per trigger event via a new helper `_eligible_reactions(db, campaign_id, watcher_char_id, trigger_event, context) -> list[dict]`. Returns the option list directly usable in the `reaction_prompt` payload.

### 5. Client-side popup

New component: `app/static/reaction_prompt.js` (or extend `economy_messaging.js`). Listens for `reaction_prompt` broadcasts; if `ME.id ∈ target_user_ids`, renders a glass-card modal in the corner:

```
┌─────────────────────────────────────┐
│ ⚡ Reaction available — Sir Caelan  │
│                                     │
│ Krieger took 14 slashing damage    │
│ from Bandit Captain.                │
│                                     │
│ [ ✨ Shield (+5 AC, 1st slot)    ]  │
│ [ 🛡️ Uncanny Dodge (halve dmg)   ]  │
│ [ 💚 Cure Wounds (heal ally)*    ]  │
│ [ Dismiss ]                         │
│                                     │
│ * not available — requires bonus    │
│   action, not reaction              │
└─────────────────────────────────────┘
```

Same options simultaneously appear as a `roll_log` card (using the existing `feature_used` card variant) so the roll log captures *which* reactions were offered, *which* was picked, and the resulting effect.

**Timeout.** Popup stays on screen for 20 s by default (configurable per-user). After timeout: auto-dismiss + roll-log entry annotated with "no reaction taken". Player can still click the chip manually later to spend the reaction on something off-menu.

---

## Reaction catalog by category

Status legend:
- ✅ **Shipped** — reaction is auto-detected/consumed today
- 🟡 **Partial** — manually triggered via dedicated endpoint, no prompt
- ⚪ **Filed** — no automation; player tracks manually

### A. Class features

| Reaction | Class | Lv | Trigger | Cost | Effect | Current |
|----------|-------|----|---------|------|--------|---------|
| **Uncanny Dodge** | Rogue | 5 | `damage_taken` (single attacker) | Reaction | Halve attack damage | ✅ v2.49.243 (auto-fire — needs prompt opt-in) |
| **Cutting Words** | Bard Lore | 3 | `attack_targeted`, `damage_taken`, `save_failed` against an ally within 60 ft | Reaction + BI die | Subtract BI die from attack/check/damage | 🟡 v2.54.x (endpoint only — needs prompt) |
| **Mantle of Inspiration** | Bard Valor | 3 | `ally_drops_to_zero` or seen ally falling | Reaction + BI die | Grant temp HP + reaction-cost move | ⚪ |
| **Mage Hand Legerdemain** | Rogue Arcane Trickster | 3 | Various (passive) | Bonus action, not reaction | n/a (catalog completeness) | ⚪ |
| **Riposte** | Fighter Battle Master | 3 | `attack_targeted` if attacker missed you | Reaction + 1 superiority die | Attack the attacker | ⚪ |
| **Parry (Battle Master)** | Fighter Battle Master | 3 | `damage_taken` from a melee attacker you can see | Reaction + 1 superiority die | Reduce damage by 1d8 + DEX mod | ⚪ |
| **Brace (Battle Master)** | Fighter Battle Master | 3 | `creature_enters_reach` | Reaction + 1 superiority die | Attack the enterer | ⚪ |
| **Goading Strike react** | Battle Master | varies | covered in initial attack, not separate reaction | n/a | n/a | n/a |
| **Indomitable** | Fighter | 9 | `save_failed` | Reaction-adjacent (separate use slot) | Reroll the save | 🟡 v2.56.0 (advantage v1 approximation; Phase C reroll filed) |
| **Deflect Missiles** | Monk | 3 | `damage_taken` from a ranged attack | Reaction | Reduce damage by 1d10 + DEX + Monk Lv; catch if 0 | ⚪ |
| **Slow Fall** | Monk | 4 | `falling` | Reaction | Reduce fall damage by 5×Monk Lv | ⚪ |
| **Stunning Strike on reaction** | Monk | n/a (not RAW reaction) | n/a | n/a | n/a | n/a |
| **Protection fighting style** | Paladin / Fighter | 1 (style) | `ally_attacked_near` within 5 ft | Reaction (need shield) | Impose disadvantage on attack | ⚪ |
| **Interception fighting style** | Paladin / Fighter / Warrior | 1 (style XGE) | `damage_taken` by ally within 5 ft | Reaction (need shield/weapon) | Reduce damage by 1d10 + prof | ⚪ |
| **Cleric Domain reactions** | Cleric | varies | per-domain | varies | varies | ⚪ (none yet) |
| **Hellish Rebuke (Warlock prep)** | Warlock | 1 | `damage_taken` | Reaction + 1st spell slot (or higher) | 2d10 fire to attacker | ⚪ |
| **Counterspell prep (Warlock 3rd)** | Warlock | 3 | `spell_cast_near` | Reaction + 3rd spell slot | Counter spell ≤ 3rd | ⚪ |
| **Misty Escape** | Warlock Archfey | 6 | `damage_taken` | Reaction | Teleport 60 ft + invis | ⚪ |
| **Wrath of the Storm** | Cleric Tempest | 1 | `damage_taken` from creature within 5 ft | Reaction (limited uses) | 2d8 lightning/thunder save half | ⚪ |
| **Warding Flare** | Cleric Light | 1 | `attack_targeted` by creature you can see within 30 ft | Reaction (limited uses) | Impose disadvantage | ⚪ |
| **Shield of Faith reaction** | n/a | n/a | bonus action, not reaction | n/a | n/a | n/a |
| **Vow of Enmity reaction** | Paladin Vengeance | 3 (CD) | n/a (bonus action) | n/a | n/a | n/a |
| **Channel Divinity: Rebuke the Violent** | Paladin Crown | 7 | `damage_taken` by ally within 30 ft | Reaction + CD | Force CON save, half damage to attacker | ⚪ |
| **Master Duelist** | Fighter Battle Master | 18 | `attack_targeted` and missed | n/a (no reaction; reroll attack) | n/a | n/a |
| **Mantle of Faithful (Champion)** | Fighter Champion | various | passive | n/a | n/a | n/a |
| **Druidic Warrior reaction** | Druid | n/a | n/a | n/a | n/a | n/a |

### B. Feats (PHB + XGE common picks)

| Reaction | Trigger | Cost | Effect | Current |
|----------|---------|------|--------|---------|
| **Sentinel — effect 3** | `ally_attacked_near` | Reaction | Melee attack vs attacker | ✅ v2.66.5/6 (advisory; needs prompt) |
| **Polearm Master — enter-reach OA** | `creature_enters_reach` | Reaction | OA against the enterer | ✅ v2.66.4 (advisory; needs prompt) |
| **Lucky** | `attack_targeted`, `save_failed`, `attacker_rolls_d20_against_you` | Free (no reaction) + 1 luck point | Reroll the d20 | ⚪ |
| **War Caster — OA spell** | `creature_exits_reach` | Reaction | OA as a single-target spell | ⚪ (extends existing OA) |
| **Mage Slayer — reaction strike on cast** | `spell_cast_near` (within 5 ft) | Reaction | Melee attack vs caster | ⚪ |
| **Shield Master — reactive shove** | n/a (action/bonus action) | n/a | n/a | n/a |
| **Defensive Duelist** | `attack_targeted` (melee, wielding finesse) | Reaction | +PB to AC for that attack | ⚪ |
| **Heavy Armor Master reaction** | n/a (passive damage reduction) | n/a | n/a | n/a |
| **Inspiring Leader** | n/a | n/a | n/a | n/a |
| **Tough** | n/a (passive HP) | n/a | n/a | n/a |
| **Resilient** | n/a (save proficiency) | n/a | n/a | n/a |

### C. Reaction spells (PHB + XGE + TCoE)

| Spell | Lv | Trigger | Cost | Effect | Current |
|-------|----|---------|------|--------|---------|
| **Shield** | 1 | `attack_targeted` (incl. magic missile) | Reaction + 1st slot | +5 AC vs that attack + immune to magic missile until next turn | ⚪ |
| **Hellish Rebuke** | 1 | `damage_taken` from a creature you can see within 60 ft | Reaction + 1st (or higher) | 2d10 fire (DEX save half), +1d10 per slot level above 1st | ⚪ |
| **Absorb Elements** | 1 (XGE) | `damage_taken` from acid/cold/fire/lightning/thunder | Reaction + 1st (or higher) | Resistance to triggering damage + first melee attack next turn adds 1d6 of that type | ⚪ |
| **Feather Fall** | 1 | `falling` (self or creature within 60 ft) | Reaction + 1st slot | Fall slowed to 60 ft/round, no damage on landing | ⚪ |
| **Counterspell** | 3 | `spell_cast_near` (within 60 ft) | Reaction + 3rd (or higher) slot | Counter ≤ 3rd auto, higher levels need DC 10+spell_lv ability check | ⚪ |
| **Silvery Barbs** | 1 (SCAG/XGE) | `save_failed`, `attack_hit_against_ally`, `ability_check_success_enemy` | Reaction + 1st slot | Force reroll, ally gets advantage on next attack/check/save | ⚪ |
| **Wrathful Smite (reaction half)** | 1 | n/a — Wrathful Smite is concentration bonus action; doesn't have a reaction half | n/a | n/a | n/a |
| **Warding Wind reaction half** | n/a | n/a | n/a | n/a | n/a |
| **Counterspell from item** | varies | `spell_cast_near` | Reaction + charge | counter | ⚪ (covered under items) |
| **Steel Wind Strike** | n/a (action) | n/a | n/a | n/a | n/a |
| **Healing Spirit reaction half** | n/a | n/a | n/a | n/a | n/a |

### D. Reaction items

| Item | Trigger | Cost | Effect | Current |
|------|---------|------|--------|---------|
| **Cloak of Displacement** | `attack_targeted` (passive — first attack always has disadvantage, but if hit, breaks until start of next turn) | Passive (not a reaction per se) | Attacker disadvantage | ⚪ (passive — file under buffs, not reactions) |
| **Ring of Spell Turning** | `spell_cast_near` (targets you) | Reaction + ring charge | Reflect spell on percentile roll | ⚪ |
| **Cloak of the Bat / Wings of Flying** | Falling-adjacent (toggle, not reaction) | Action | Flight | n/a |
| **Periapt of Wound Closure** | `damage_taken` | Passive | Stabilize on dying, double natural healing | ⚪ (passive) |
| **Brooch of Shielding** | `damage_taken` from force damage | Passive | Resistance + immune to magic missile | ⚪ (passive) |
| **Eldritch Cannon (Artificer Artillerist)** | n/a — bonus action | n/a | n/a | n/a |
| **Spell Storing Ring with reaction spells** | varies (whatever stored spell triggers on) | Reaction + 1 stored spell | Cast as the spell would | ⚪ |
| **Defender weapon mode shift** | n/a | n/a | n/a | n/a |
| **Mantle of Spell Resistance** | `save_failed` against spell | Passive (advantage on save, not reaction) | n/a | n/a |

### E. Monster reactions (representative)

Monsters are GM-controlled — the prompt routing should land on the GM client only.

| Reaction | Monster | Trigger | Effect |
|----------|---------|---------|--------|
| **Parry** | Bandit Captain, Knight, Veteran, Hobgoblin Captain | `attack_targeted` (melee) | +2 to AC vs that attack |
| **Uncanny Dodge** | Spy, Assassin | `damage_taken` | Halve damage |
| **Snake Form (Yuan-Ti)** | `spell_cast_near` (targets you) | Reflect spell | varies |
| **Tentacle Slap (Aboleth)** | `attack_targeted` (creature attacks the aboleth) | Whip-attack the attacker | melee 9 (2d4+4) bludgeoning |
| **Sting (various dragons)** | n/a — usually legendary action, not reaction | n/a | n/a |
| **Vampire Spider Climb** | n/a — passive | n/a | n/a |
| **Spectator Eye Ray reaction** | n/a — passive | n/a | n/a |
| **Wyvern Tail Sting** | n/a — multi-attack action | n/a | n/a |
| **Banshee Wail** | n/a — recharge action | n/a | n/a |
| **Pit Fiend Fear Aura** | n/a — passive | n/a | n/a |

Monster reactions are stored in the projected sheet's `actions` list with `category: "reaction"` (already populated by `_monster_template_to_sheet`). The eligible-reactions helper reads `sheet.actions` for NPCs.

---

## UX details

### Roll-log entry

Reuse the `feature_used` card variant. Append a chip row at the bottom listing the option labels as clickable buttons. The card stays in the log forever (audit history).

```
[12:42]  ⚡ Reaction available — Sir Caelan
         Krieger took 14 slashing damage from Bandit Captain.
         [ Shield ][ Uncanny Dodge ][ Dismiss ]
```

After resolution: the chip row replaces with the chosen option + the effect.

```
[12:42]  ⚡ Reaction taken — Sir Caelan: Shield (1st slot)
         → +5 AC vs Bandit Captain's Scimitar; attack now misses.
```

### Popup toast

Position: top-right corner (next to the existing dice toasts). Glass-card style matching the v2.62.0 transparency aesthetic. Auto-fades to roll-log-only after 20 s if untouched.

Per-user setting: `User.reaction_prompt_mode = "popup" | "roll_log_only" | "off"`. Default "popup".

### Cross-client coordination

Two clients for the same user could see the prompt simultaneously (laptop + phone). The first to click wins; the second sees a `reaction_prompt_resolved` event and removes the popup. Server-side replay guard: `prompt_id` is single-use; second `/use_reaction` with same `prompt_id` returns `409 already_resolved`.

### Out-of-band reactions

Players sometimes want to spend a reaction on something the system DOESN'T prompt (e.g. narrative reactions). Keep the manual chip-click path intact — clicking the reaction chip flips it without consuming any specific reaction, and the roll-log entry reads "Sir Caelan spent his reaction (manual)."

---

## Implementation phases

### Phase 1 — Foundation (1 commit, MINOR)

- `reaction_prompt` WS broadcast type + handler in `economy_messaging.js`.
- `target_user_ids` per-user routing field on the broadcast.
- New `/use_reaction` endpoint with prompt_id replay guard + dispatch table.
- Helper `_eligible_reactions(db, campaign_id, watcher_char_id, trigger_event, context)`.
- Helper `_emit_reaction_prompt(campaign_id, watcher_combatant, trigger_event, summary, options)` that builds + broadcasts the payload.
- One trigger wired end-to-end as a proof: **OA exit-reach** (v2.66.0 advisory upgraded into a real prompt with an "Take the OA" button that triggers a follow-up `/attack` call).
- Per-user `User.reaction_prompt_mode` field + schema migration.
- Settings UI toggle.
- Harness test: `tests/harness/test_reaction_prompt.py` covering the prompt → click → resolve → broadcast cycle.

### Phase 2 — Class-feature reactions (1 commit per ~3 reactions)

Wire each via the Phase 1 prompt framework. Auto-fire features (Uncanny Dodge) get retrofitted to FIRE A PROMPT instead — keeps the player in the driver's seat.

- **Phase 2a:** Uncanny Dodge (retrofit), Cutting Words (retrofit), Indomitable.
- **Phase 2b:** Riposte, Parry, Brace, Deflect Missiles.
- **Phase 2c:** Protection style, Interception style.
- **Phase 2d:** Misty Escape, Warding Flare, Wrath of the Storm.
- **Phase 2e:** Mantle of Inspiration, Rebuke the Violent.

### Phase 3 — Reaction spells (1 commit per spell)

Each is a small commit using the prompt framework + the existing `/cast_spell` machinery:

- **Phase 3a:** Shield (highest gameplay impact). ✅ partial — v2.69.0 wires prompt + slot consumption + buff install; retroactive AC negation of the triggering hit filed for v3 pending-damage state machine.
- **Phase 3b:** Counterspell (needs `spell_cast_near` event). ✅ partial — v2.70.0 wires prompt + slot consumption + outcome-hint advisory; arcana-check roll + auto-undo of countered cast filed for v3.
- **Phase 3c:** Hellish Rebuke + Absorb Elements (both `damage_taken` listeners). ✅ partial — v2.71.0 wires both helpers + dispatch + HR live tests; auto-damage to rebuked attacker, AE resistance pipeline + next-melee bonus damage pipeline, and AE demo fixture all filed.
- **Phase 3d:** Silvery Barbs (needs `save_failed` event).
- **Phase 3e:** Feather Fall (needs `falling` event — depends on a fall-damage model which is filed separately).

### Phase 4 — Feats (1 commit)

- Lucky (multi-trigger), War Caster (extends OA framework), Mage Slayer (adds `spell_cast_near` listener), Defensive Duelist.

### Phase 5 — Items (1 commit)

- Ring of Spell Turning (extends Counterspell pipeline), Spell-Storing Ring with reaction spells, Periapt of Wound Closure (passive — file under buffs).

### Phase 6 — Monster reactions (1 commit)

- Parry (Bandit Captain et al.) — wire `attack_targeted` for NPC watchers + dispatch to `/use_npc_reaction`.
- Yuan-Ti Snake Form, Aboleth Tentacle Slap.
- The eligible-reactions helper already reads `sheet.actions[].category == "reaction"` for NPCs; this phase wires the GM-side popup routing.

### Phase 7 — Triggers not yet modeled

These don't exist in the codebase today; each gets its own design pass:

- **`falling` event** — needs fall-distance tracking on tokens (vertical map dim?) — depends on a fall-damage model. File.
- **`spell_cast_near` event** — needs to fire on every `/cast_spell` + `/npc_cast_spell` with the spell's effective origin point + a `spell_level`. Trivial but every spell endpoint emits.
- **`save_failed` extension** — fire on EVERY save (not just condition-installs). Currently only condition-install paths emit; for Silvery Barbs etc. we need a save resolution broadcast on every save.

---

## Out of scope

- **Auto-fire policy**. Today's Uncanny Dodge auto-spends without asking. The plan flips this to *always-prompt* by default, with an optional per-user setting "auto-spend Uncanny Dodge" for players who prefer it. This is a UX preference, not a code path — both code paths exist (the existing auto-fire + the new prompt), the user picks.
- **AI suggestions** ("Should I spend Shield here?"). The prompt shows raw options; deciding is the player's job.
- **Reaction-on-roll-log-replay**. If a player joins mid-session, they don't get retroactive prompts for past triggers — only new ones.
- **Server-authoritative turn advance**. Resetting reactions is still client-driven. A future plan should consider a server-side `/battle/next_turn` endpoint that runs reset + buff TTL ticks; out of scope here.
- **Reaction-shaped resources that aren't reactions** (e.g. Bonus Action Lay on Hands). The prompt framework could extend to bonus actions but RAW reactions are a tighter scope and the gameplay value is higher.

---

## Open questions

1. **Prompt timeout**. 20 s seems right for most groups, but slow tables might want 60 s. Make it user-configurable.
2. **Popup placement**. Top-right matches dice toast; bottom-center is more visible. Test with users.
3. **Sound cue**. A subtle audio chime when a prompt fires (configurable per-user, off by default)? Audio routes already exist (`app/routes/audio_routes.py`).
4. **NPC reactions**. GM gets bombarded if every bandit captain attacks — should the GM client batch reactions into a single "GM reactions queue" panel? Probably yes, but ship per-prompt first and iterate.
5. **Multi-trigger reactions**. Lucky has 3 triggers; should we show ONE prompt with all eligible Lucky uses, or fire 3 separate prompts? One unified prompt is cleaner.
6. **Indomitable reroll path**. v2.65.0 Phase C is filed for the snapshot-pipeline reroll. Indomitable in this plan assumes Phase C lands first OR we ship the v1 advantage approximation.

---

## Notes on the prompt-event vs auto-consume tradeoff

Some reactions auto-consume today (v2.49.243 Uncanny Dodge). The plan flips this to always-prompt by default. Why:

- **Player agency**. RAW says reactions are *opt-in*. Auto-fire removes choice.
- **Resource conservation**. A Rogue may want to save Uncanny Dodge for a bigger hit later in the round.
- **Auditability**. The roll-log entry shows "Sir Caelan declined Shield, took 14 damage" — a record of the player's choice. Auto-fire hides this.

But auto-fire has fans (faster combat, less interruption). The compromise: a per-user setting that turns on auto-spend for specific reactions ("don't ask, just halve my damage with Uncanny Dodge").

---

## Cross-references

- [`docs/plans/class-content-status.md`](class-content-status.md) — content catalog this plan extends.
- v2.66.0 → v2.66.6 — pre-plan reaction-trigger work this plan unifies.
- `tabletop_routes.py:_mark_battle_economy` — the slot-flip primitive.
- `tabletop_routes.py:_check_opportunity_attack_triggers` — pattern template for trigger helpers.
- `tabletop_routes.py:_check_sentinel_attack_triggers` — pattern template for attack-listener triggers.
