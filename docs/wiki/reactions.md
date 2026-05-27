# Reactions Automation — GM Guide

SimpleVTT surfaces reactions (Opportunity Attack, Shield, Counterspell, Uncanny Dodge, Parry, etc.) through a popup + roll-log prompt when their trigger event fires at the table. This guide covers what the system surfaces, what each prompt looks like, and how it interacts with manual GM adjudication.

## Quick start

When a trigger event fires (a creature exits a watcher's reach, an attack hits a PC, a spell is cast within 60 ft of a Counterspell-prepared caster, etc.), every eligible watcher's owning user — plus the GM — gets a popup with one or more reaction options.

Each option shows:
- The reaction name + the resource it costs (Reaction slot, spell slot level, charge count, etc.)
- A preview of the mechanical effect (e.g. "+5 AC (15 → 20) would make d20 18 MISS")
- A click button to spend the reaction

The popup also appears as a roll-log entry so it's auditable after the fact. The popup auto-dismisses when the reaction is spent or declined; the roll-log entry persists.

You can change your popup behavior in `/settings` — three modes:
- **Popup + roll log** (default): popup toast + roll log entry
- **Roll log only**: skip the popup; the roll-log entry still appears
- **Off**: no surface at all (you'll only see reactions through the GM Reactions Panel)

## Trigger events

The framework currently fires on these events. Each event maps to one or more reactions; the table below shows which.

| Trigger event | When it fires | Reactions surfaced |
|---|---|---|
| `creature_exits_reach` | A creature moves out of a watcher's melee reach | Opportunity Attack, War Caster (cast-instead-of-OA) |
| `creature_enters_reach` | A creature enters a Polearm Master's reach | Polearm Master OA, War Caster (cast-instead-of-OA) |
| `ally_attacked_near` | A creature attacks someone within 5 ft of a Sentinel | Sentinel reaction (melee attack on the attacker) |
| `attack_targeted` | An attack roll lands as a hit on any combatant | Shield, Defensive Duelist, Lucky, Uncanny Dodge (when other reactions exist), NPC stat-block reactions (Parry, etc.), item reactions (Cloak of Displacement) |
| `damage_taken` | A PC takes nonzero damage | Uncanny Dodge ack (when UD auto-fired), Hellish Rebuke, Absorb Elements (elemental damage only) |
| `spell_cast_near` | A creature within 60 ft casts a leveled spell | Counterspell, Mage Slayer (5 ft gate) |
| `save_resolved` | A creature succeeds on a saving throw (via `/roll_request` resolution) | Silvery Barbs |
| `reaction_used` | A class-feature reaction was already spent (Cutting Words, Indomitable) | Informational ack only |

## Reactions catalog

The full set of reactions wired into the prompt pipeline, grouped by source.

### Class features (auto-surfaced based on PC class/subclass)

- **Opportunity Attack** — Any combatant. Fires when a hostile creature exits their melee reach.
- **Polearm Master** (feat) — When wielding a glaive/halberd/pike/quarterstaff/spear, creatures entering reach provoke an OA.
- **Sentinel** (feat) — Allies attacked within 5 ft of you let you OA the attacker.
- **Uncanny Dodge** (Rogue 5+) — Halve damage from one attack per round. Auto-fires unless other attack_targeted reactions are eligible (Shield / Defensive Duelist / Lucky / item reactions) — in that case, the player picks from the prompt.
- **Cutting Words** (Bard College of Lore 3+) — Reduce a creature's d20 attack/check/damage. Surfaced as a dedicated `/use_cutting_words` endpoint + roll-log ack.
- **Indomitable** (Fighter 9+) — Reroll a failed saving throw. Surfaced as a dedicated `/use_indomitable` endpoint + roll-log ack.
- **Battle Master maneuvers** (Fighter 3+ Battle Master): Riposte, Parry, Brace, Deflect Missiles. Listed in the GM Reactions Panel catalog.
- **Protection** / **Interception** fighting styles. Listed in the GM Reactions Panel catalog.
- **Warding Flare** (Cleric Light), **Wrath of the Storm** (Cleric Tempest), **Misty Escape** (Warlock Archfey 6+), **Mantle of Inspiration** (Bard Valor 3+), **Rebuke the Violent** (Paladin Crown 7+). All listed in the GM Reactions Panel.

### Reaction spells

- **Shield** (Wizard / Sorcerer cantrip-tier 1st-level slot) — +5 AC. Fires on `attack_targeted`; surfaces with AC-math preview showing whether the new AC would have missed.
- **Counterspell** (Sorcerer / Wizard / Warlock 3rd-level slot) — Reflect / cancel an incoming spell within 60 ft. Fires on `spell_cast_near`; surfaces with the level-vs-slot outcome (auto-counter or arcana check DC).
- **Hellish Rebuke** (Warlock / Tiefling 1st-level slot) — Damaging creature takes 2d10 (+1d10/slot) fire. Fires on `damage_taken`.
- **Absorb Elements** (Wizard / Sorcerer / Druid / Ranger / Artificer 1st-level slot) — Resistance to elemental damage + +1d6 elemental damage on next melee hit. Fires on `damage_taken` with damage_type ∈ {acid, cold, fire, lightning, thunder}.
- **Silvery Barbs** (Sorcerer / Wizard / Bard 1st-level slot) — Force a creature that succeeded on a d20 to reroll, take the lower. Fires on `save_resolved` with `context.passed=True`.

### PC feats

- **Defensive Duelist** (Lyra in demo) — +PB AC against one melee hit when wielding a finesse weapon. Fires on `attack_targeted`.
- **Mage Slayer** (Krieger in demo) — Melee attack against a creature within 5 ft that casts a spell. Fires on `spell_cast_near` with 5-ft gate.
- **War Caster** (Tavik in demo) — Cast a 1-action spell instead of an OA. Extends both OA branches with a second option per prompt.
- **Lucky** (Garrik in demo) — 3 luck points / long rest. Force a d20 reroll. Fires on `attack_targeted` (own attack/check/save surfaces filed for v3).

### Items

Equipped inventory items with a `_reactions: [...]` array surface generically — no per-item code needed. The framework reads each entry's `trigger`, `label`, `desc`, `cost` and builds a prompt option keyed `item-{slug}-{descriptor}`.

Demo: **Cloak of Displacement** on Lyra (binds to `attack_targeted`).

### Monster reactions (NPCs)

The same `attack_targeted` event fires for NPC targets too. The framework walks the monster's projected stat-block actions for `category == "reaction"` entries (Parry on Bandit Captain / Knight / Gladiator / Erinyes / Marilith / Noble, etc.) and surfaces them as `monster-{action_id}` options. Walker auto-scales — new monsters with reactions in the SRD catalog get the prompt surface without code changes.

## GM Reactions Panel

For reactions that don't yet have a trigger event wired (or for narrative use cases like "the lich casts Counterspell from a bookshelf you didn't roll for"), the GM Reactions Panel surfaces every combatant's reaction catalog with one-click manual spend. Open it from the GM Tools tab; it shows each combatant's reactions + flips the reaction chip when you click.

The panel is GM-only.

## v1 limitations

- **No auto-resolution of advisory reactions.** Shield's AC bump tells you whether the new AC would have missed, but doesn't auto-undo the damage. Hellish Rebuke surfaces the formula (`4d10 fire`) but doesn't auto-roll. Mage Slayer / Sentinel / OA surface the "click your Attack button" instruction; the player rolls the actual swing. Same for War Caster ("click Cast Spell"). Auto-resolution is filed for the v3 pending-damage state machine.
- **No retroactive damage undo on Shield / Defensive Duelist.** When the new AC would have missed, the chat-card surfaces the outcome but the damage isn't undone server-side. Use the v2.65.0 chat-card Undo to manually walk it back.
- **Own-roll Lucky / Silvery Barbs not surfaced.** Lucky's "your attack/check/save" triggers and SB's attack-roll triggers need new `attack_resolved` + `check_resolved` events that don't exist yet.
- **Some NPC reactions don't fire on non-`attack_targeted` triggers.** Phase 6 catalog wires monster reactions to `attack_targeted` only; `damage_taken` / `spell_cast_near` / `ally_attacked_near` NPC walkers are filed.
- **Passive feat effects not surfaced.** Mage Slayer's save advantage vs nearby casters + concentration disadvantage on damage dealt; War Caster's concentration-save advantage on damage. All filed.

## See also

- [Reactions automation plan](/wiki/doc/plan-reactions-automation) — the per-phase design doc with status table and v3 backlog.
- [GM Reactions Panel](/wiki/running-a-session-as-gm#reactions-panel) — operational guide for the manual-spend bypass.
- [The character sheet](/wiki/the-character-sheet) — where feats, spells, and items get configured per PC.
