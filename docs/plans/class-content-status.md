# Class / Subclass / Feat / Race content — implementation status

Inventory of every D&D 5e SRD entity shipped under `app/data/local/dnd5e/`,
annotated with current implementation status. This is the **starting
list** — detailed per-feature plans go below their respective sections as
work begins. Add follow-up plans for items in 🟠 / ⚪ status as they
become priorities; do **not** start a feature without first writing
its plan section here.

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | **Implemented** — appears on the character sheet AND mechanically functional (clickable, decrements / restores correctly, integrated with rest / roll-log / WS broadcast where relevant) |
| 🟢 | **Half-implemented** — UI primitive present (e.g. counter pill), but the side-effect mechanics (e.g. the option-picker that drives "Channel Divinity → Turn Undead") aren't wired |
| 🟡 | **Data only** — description text visible on sheet via the SRD JSON; no mechanical wiring |
| 🟠 | **Planned** — design / plan exists in this file or in `docs/plans/*.md`, no code yet |
| ⚪ | **No plan** — neither implemented nor designed; would need a fresh planning pass before work starts |

Where a feature exists in multiple flavors (counter ✅ + option-picker 🟠
e.g. Channel Divinity) the highest applicable symbol wins, with a note in
the comment column.

---

## Classes — features

The 12 PHB SRD classes are shipped under `app/data/local/dnd5e/class_features/`.
The `### Header` names below come from the `features` field of each JSON.

### Barbarian

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Rage | 🟢 | Resource counter exists (`key: 'rage'`); damage bonus + advantage / resistance side effects not auto-applied |
| 1 | Unarmored Defense | 🟡 | Description visible; AC engine doesn't auto-detect this fighting style — player sets `base_ac` manually |
| 2 | Reckless Attack | ⚪ | |
| 2 | Danger Sense | ⚪ | |
| 3 | Primal Path | 🟡 | Subclass slot rendered; specific paths see Subclasses below |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | Standard ASI flow handles every class |
| 5 | Extra Attack | 🟡 | Description visible; attack panel doesn't auto-suggest a second attack roll |
| 5 | Fast Movement | ⚪ | |
| 7 | Feral Instinct | ⚪ | |
| 9 / 13 / 17 | Brutal Critical | ⚪ | |
| 11 | Relentless Rage | ⚪ | |
| 15 | Persistent Rage | ⚪ | |
| 18 | Indomitable Might | ⚪ | |
| 20 | Primal Champion | ⚪ | |

### Bard

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Spellcasting | ✅ | Spells panel renders + casts via `/api/.../roll` |
| 1 | Bardic Inspiration | 🟢 | Resource counter (`key: 'bardic-inspiration'`); no "give die to ally" target-picker UI |
| 2 | Jack of All Trades | ⚪ | |
| 2 | Song of Rest | 🟢 | Resource counter (`key: 'song-of-rest'`); no "apply during short rest" hook |
| 3 | Bard College | 🟡 | Subclass slot only |
| 3 / 10 | Expertise | ✅ | Skills schema has `expertise: true` flag handled by skill-roll engine |
| 5 | Font of Inspiration | 🟡 | Description; reset → short rest already implicit via counter |
| 6 | Countercharm | ⚪ | |
| 10 / 14 / 18 | Magical Secrets | ⚪ | |
| 20 | Superior Inspiration | ⚪ | |

### Cleric

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Spellcasting | ✅ | Demo Tavik (Lv 5) prepares cantrips + L1-L3 spells correctly post-v2.4.12 |
| 1 | Divine Domain | 🟡 | Subclass slot; domain-spells curated table covers all 12 domains |
| 2 | Channel Divinity | 🟢 | Resource counter (`key: 'channel-divinity'`) shows correctly in mini + full sheet; **see plan section below** for option-picker UI work |
| 5 / 8 / 11 / 14 / 17 | Destroy Undead | ⚪ | Tied to Turn Undead option above; would surface as a damage uplift when Turn Undead is implemented |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 10 | Divine Intervention | ⚪ | |

### Druid

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Druidic | ⚪ | Language only — no mechanic |
| 1 | Spellcasting | ✅ | |
| 2 | Wild Shape | 🟢 | Resource counter (`key: 'wild-shape'`); the `/api/.../character/.../transform` route exists (per `_doMiniTransform` JS) and the mini-sheet has a Wild Shape dropdown |
| 2 | Druid Circle | 🟡 | Subclass slot |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 18 | Timeless Body | ⚪ | |
| 18 | Beast Spells | ⚪ | |
| 20 | Archdruid | ⚪ | |

### Fighter

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Fighting Style | 🟡 | Description visible; bonuses not auto-applied to attack rolls |
| 1 | Second Wind | 🟢 | Resource counter (`key: 'second-wind'`); no "click to spend + roll 1d10 + lv HP" button |
| 2 / 17 | Action Surge | 🟢 | Resource counter (`key: 'action-surge'`); no in-combat affordance |
| 3 | Martial Archetype | 🟡 | Subclass slot |
| 4 / 6 / 8 / 12 / 14 / 16 / 19 | Ability Score Improvement | ✅ | |
| 5 / 11 / 20 | Extra Attack | 🟡 | |
| 9 / 13 / 17 | Indomitable | 🟢 | Resource counter (`key: 'indomitable'`); no save-reroll button |

### Monk

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Unarmored Defense | 🟡 | |
| 1 | Martial Arts | 🟡 | |
| 2 | Ki | 🟢 | Resource counter (`key: 'ki'`); spend-Ki options (Flurry / Patient / Step) not wired |
| 2 | Unarmored Movement | ⚪ | |
| 3 | Monastic Tradition | 🟡 | Subclass slot |
| 3 | Deflect Missiles | ⚪ | |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 4 | Slow Fall | ⚪ | |
| 5 | Extra Attack | 🟡 | |
| 5 | Stunning Strike | ⚪ | (Tied to Ki) |
| 6 | Ki-Empowered Strikes | ⚪ | |
| 7 | Evasion | ⚪ | |
| 7 | Stillness of Mind | ⚪ | |
| 10 | Purity of Body | ⚪ | |
| 13 | Tongue of the Sun and Moon | ⚪ | |
| 14 | Diamond Soul | ⚪ | |
| 15 | Timeless Body | ⚪ | |
| 18 | Empty Body | ⚪ | |
| 20 | Perfect Self | ⚪ | |

### Paladin

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Divine Sense | 🟢 | Resource counter |
| 1 | Lay on Hands | 🟢 | Resource counter — "HP pool" variant (max ≠ uses, `max = 5 × lvl`); no target-picker |
| 2 | Fighting Style | 🟡 | |
| 2 | Spellcasting | ✅ | |
| 2 | Divine Smite | ⚪ | Should be a per-attack damage-uplift toggle |
| 3 | Divine Health | ⚪ | Passive — disease immunity |
| 3 | Sacred Oath | 🟡 | Subclass slot |
| 3 | Channel Divinity | 🟢 | Same counter / picker situation as Cleric — see plan section |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 5 | Extra Attack | 🟡 | |
| 6 / 18 | Aura of Protection | ⚪ | |
| 10 / 18 | Aura of Courage | ⚪ | |
| 11 | Improved Divine Smite | ⚪ | |
| 14 | Cleansing Touch | 🟢 | Resource counter |

### Ranger

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Favored Enemy | ⚪ | |
| 1 | Natural Explorer | ⚪ | |
| 2 | Fighting Style | 🟡 | |
| 2 | Spellcasting | ✅ | |
| 3 | Ranger Archetype | 🟡 | Subclass slot |
| 3 | Primeval Awareness | ⚪ | |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 5 | Extra Attack | 🟡 | |
| 8 | Land's Stride | ⚪ | |
| 10 | Hide in Plain Sight | ⚪ | |
| 14 | Vanish | ⚪ | |
| 18 | Feral Senses | ⚪ | |
| 20 | Foe Slayer | ⚪ | |

### Rogue

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 / 6 | Expertise | ✅ | Same Skills.expertise plumbing as Bard |
| 1 | Sneak Attack | ⚪ | Per-attack damage uplift; needs a toggle on the attack panel |
| 1 | Thieves' Cant | ⚪ | Language only |
| 2 | Cunning Action | ⚪ | Bonus-action utility |
| 3 | Roguish Archetype | 🟡 | Subclass slot |
| 4 / 8 / 10 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 5 | Uncanny Dodge | ⚪ | |
| 7 | Evasion | ⚪ | |
| 11 | Reliable Talent | ⚪ | Floor-of-10 on proficient skill checks — would need an option on skill roll |
| 14 | Blindsense | ⚪ | |
| 15 | Slippery Mind | ⚪ | |
| 18 | Elusive | ⚪ | |
| 20 | Stroke of Luck | 🟢 | Resource counter |

### Sorcerer

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Spellcasting | ✅ | |
| 1 | Sorcerous Origin | 🟡 | Subclass slot |
| 2 | Font of Magic | 🟢 | Sorcery Points counter (`key: 'sorcery-points'`); no slot-conversion picker |
| 3 | Metamagic | ⚪ | Per-cast modifier; needs spell-cast intercept |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 20 | Sorcerous Restoration | ⚪ | Auto-refill 4 sorcery points on short rest — could just be a special-case in the rest endpoint |

### Warlock

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Otherworldly Patron | 🟡 | Subclass slot |
| 1 | Pact Magic | 🟡 | Uses spell-slot UI but slots refresh on short rest; partial — slot reset path needs the patch |
| 2 | Eldritch Invocations | 🟡 | Picker UI not wired; invocations are stat boosts / new options |
| 3 | Pact Boon | ⚪ | |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 11 / 13 / 15 / 17 | Mystic Arcanum | ⚪ | One-per-day single-slot spells, fresh tracking needed |
| 20 | Eldritch Master | ⚪ | |

### Wizard

| Lv | Feature | Status | Notes |
|---|---|---|---|
| 1 | Spellcasting | ✅ | Demo Thalindra (Lv 5) prepares cantrips + L1-L3 spells correctly post-v2.4.12 |
| 1 | Arcane Recovery | 🟢 | Resource counter (`key: 'arcane-recovery'`); no spell-slot-restore picker |
| 2 | Arcane Tradition | 🟡 | Subclass slot |
| 4 / 8 / 12 / 16 / 19 | Ability Score Improvement | ✅ | |
| 18 | Spell Mastery | ⚪ | |
| 20 | Signature Spells | ⚪ | |

---

## Subclasses

13 PHB SRD subclasses shipped under `app/data/local/dnd5e/subclass_features/`.
The curated subclass-spell tables in `app/static/dnd5e_subclass_spells.js`
also cover **non-SRD subclasses** (Tasha's, Xanathar's etc.) that don't yet
have features JSON.

| Class | Subclass | Features JSON | Spell-grants curated | Status | Notes |
|---|---|---|---|---|---|
| Barbarian | Path of the Berserker | ✅ | n/a | 🟡 | Frenzy / Mindless Rage / Intimidating Presence / Retaliation — all descriptive |
| Bard | College of Lore | ✅ | n/a | 🟡 | Cutting Words / Additional Magical Secrets / Peerless Skill descriptive |
| Cleric | Knowledge Domain | ❌ | ✅ | 🟡 | Spell grants work via picker; no features JSON |
| Cleric | **Life Domain** | ✅ | ✅ | 🟢 | Domain spells auto-grant (demo Tavik post-v2.4.15); Channel Divinity: Preserve Life is data only |
| Cleric | Light Domain | ❌ | ✅ | 🟡 | Curated spells; Warding Flare / Radiance of the Dawn descriptive |
| Cleric | Nature Domain | ❌ | ✅ | 🟡 | |
| Cleric | Tempest Domain | ❌ | ✅ | 🟢 | Wrath of the Storm counter exists |
| Cleric | Trickery Domain | ❌ | ✅ | 🟡 | |
| Cleric | War Domain | ❌ | ✅ | 🟢 | War Priest counter exists |
| Cleric | Forge / Grave / Order / Peace / Twilight | ❌ | ✅ | 🟡 | Spell grants only |
| Druid | **Circle of the Land** | ✅ | ✅ | 🟢 | Natural Recovery counter exists; Land's Stride / Nature's Ward descriptive |
| Druid | **Circle of the Moon** | ✅ | n/a | 🟡 | Combat Wild Shape / Circle Forms — relies on Wild Shape infrastructure |
| Druid | Circle of Spores / Wildfire / Stars | ❌ | ✅ | 🟡 | Spell grants only |
| Fighter | **Champion** | ✅ | n/a | 🟡 | Improved Critical / Remarkable Athlete — needs attack-roll intercept |
| Fighter | Battle Master | ❌ | n/a | 🟢 | Superiority Dice counter exists |
| Fighter | Eldritch Knight | ❌ | n/a | ⚪ | |
| Monk | **Way of the Open Hand** | ✅ | n/a | 🟡 | Open Hand Technique / Wholeness of Body — needs Ki integration |
| Paladin | **Oath of Devotion** | ✅ | ✅ | 🟡 | Sacred Weapon / Turn the Unholy descriptive (both Channel options) |
| Paladin | Ancients / Vengeance / Conquest / Redemption / Glory / Watchers / Oathbreaker | ❌ | ✅ | 🟡 | Spell grants only |
| Ranger | **Hunter** | ✅ | n/a | 🟡 | Hunter's Prey / Defensive Tactics / Multiattack descriptive |
| Rogue | **Thief** | ✅ | n/a | 🟡 | Fast Hands / Use Magic Device descriptive |
| Sorcerer | **Draconic Bloodline** | ✅ | n/a | 🟡 | Dragon Ancestor / Draconic Resilience / Dragon Wings descriptive |
| Sorcerer | Wild Magic | ❌ | n/a | 🟢 | Tides of Chaos counter exists |
| Sorcerer | Aberrant Mind / Divine Soul | ❌ | ✅ (Aberrant) | 🟡 | Spell grants only |
| Warlock | **The Fiend** | ✅ | n/a | 🟡 | Dark One's Blessing / Dark One's Own Luck / Fiendish Resilience descriptive |
| Wizard | **School of Evocation** | ✅ | n/a | 🟡 | Evocation Savant / Sculpt Spells / Empowered Evocation descriptive |
| Wizard | Divination | ❌ | n/a | 🟢 | Portent Dice counter exists |

---

## Feats

Only one SRD feat shipped (Grappler is the only one in the OGL SRD 5.1).
Homebrew feats live alongside the SRD via the campaign-scoped homebrew
tier (e.g. the demo's `lucky-strike` feat in
`app/data/homebrew/campaign-X/feats/`).

| Feat | Source | Status | Notes |
|---|---|---|---|
| Grappler | SRD 5.1 (`app/data/local/dnd5e/feats/grappler.json`) | 🟡 | Description renders on sheet; no mechanical wiring (Grappler's "advantage on grapple checks" would need a per-skill-roll context) |
| Lucky Strike (demo homebrew) | `seed_homebrew_files` → `feats/lucky-strike.json` | 🟡 | Description renders; no automatic reroll-on-miss intercept |

Adding new feats means dropping a JSON file in the matching tier; the
homebrew editor (campaign settings → Homebrew → Feats) can author them
via UI. **Mechanical feat effects are uniformly ⚪** — none have automated
intercepts; they're all reference-text-on-the-sheet for now.

---

## Races

9 SRD races. Each ships a `traits` JSON array; the sheet renders each
trait as a row with description.

| Race | Traits | Status | Notes |
|---|---|---|---|
| Dragonborn | Draconic Ancestry, Breath Weapon, Damage Resistance | 🟡 | Breath weapon needs a "click to fire" + save-DC challenge — same pattern as Channel Divinity options |
| Half-Elf | ASI, Darkvision, Fey Ancestry, Skill Versatility, Extra Language | 🟡 | ASI ✅ via sheet; passives (Fey Ancestry = charm immunity, Darkvision) descriptive only |
| Half-Orc | Darkvision, Menacing, Relentless Endurance, Savage Attacks | 🟡 | Relentless Endurance has "once per long rest" semantics — could be a 1/1 resource counter |
| High Elf | Darkvision, Keen Senses, Fey Ancestry, Trance, Elf Weapon Training, Cantrip, Extra Language | 🟢 | Cantrip choice + Elf Weapon Training proficiency wire through existing systems; the rest descriptive |
| Hill Dwarf | Darkvision, Dwarven Resilience (poison adv/resistance), Dwarven Combat Training, Tool Proficiency, Stonecunning, Speed Not Reduced by Heavy Armor, Dwarven Toughness | 🟢 | Demo Tavik benefits from Dwarven Toughness (+5 HP at Lv 5) — already in the cleric sheet's `hp.max=43` |
| Human | ASI ×6, Extra Language | ✅ | The all-+1-stats flow is supported via standard ASI; Variant Human's free feat would need the feat-picker UI work |
| Lightfoot Halfling | Lucky, Brave, Halfling Nimbleness, Naturally Stealthy | 🟡 | Lucky (reroll 1 on attack/check/save) would need a roll-time intercept — same shape as the Lucky feat in some homebrew sources |
| Rock Gnome | Darkvision, Gnome Cunning (adv vs INT/WIS/CHA magic saves), Artificer's Lore (+2 ×PB on history of magic items), Tinker | 🟡 | |
| Tiefling | Darkvision, Hellish Resistance (fire resist), Infernal Legacy (Thaumaturgy + Hellish Rebuke 1/day + Darkness 1/day) | 🟢 | Infernal Legacy spells could attach to a per-day resource counter; spell-cast hook exists for cantrips |

---

## Cross-cutting infrastructure plans

These are NOT class/race/feat-specific but block any deeper mechanical
work above. Filed here so the order-of-operations is clear.

### A. Resource option-picker UI

**Affects:** Channel Divinity (Cleric, Paladin), Ki (Monk), Sorcery
Points (Sorcerer), Bardic Inspiration (Bard), Superiority Dice (Battle
Master), Lay on Hands (Paladin), Cleansing Touch, Stroke of Luck.

Today the class-resources panel renders `Name X/Y` and a single "Use"
button that decrements `current` by 1. The next level of richness is an
overlay that opens on click and lets the player pick **which option** the
resource is being spent on (Turn Undead vs Preserve Life, Flurry of
Blows vs Patient Defense vs Step of the Wind, etc.).

**Plan:** see the Channel Divinity 3-phase plan in conversation /
2.4.15 commit message. The plan generalizes — the picker is keyed on
`resource.key` and reads from a per-feature curated table
(`dnd5e_channel_divinity.js`, `dnd5e_ki_options.js`, etc.) that lists the
options unlocked at the character's level.

### B. Roll-time intercepts

**Affects:** Lucky (Halfling + feat), Reliable Talent (Rogue), Indomitable
(Fighter), Stroke of Luck (Rogue), Portent (Divination), Bardic
Inspiration (recipient side), Sneak Attack (uplift), Divine Smite
(uplift), Improved Critical (Champion).

These all want to fire **at the moment a d20 is rolled** — either to
modify the result (reroll, replace, add) or to trigger a follow-on
roll (smite damage). Today `/api/.../roll` is a fire-and-forget endpoint;
adding intercepts means a confirmation-style modal that pauses between
roll-result-known and result-applied, with affordances for each
applicable feature.

**No plan yet.** Big architectural change — would touch every roll path.

### C. Combat condition / buff slot

**Affects:** Rage (resistance + adv on STR), Reckless Attack (adv +
disadvantage incoming), Guided Strike (next attack +10), Bless (+1d4
on attack/save), Bardic Inspiration (recipient), almost every concentration
spell.

Today the only "buff" surface is the manual conditions list. A
character would benefit from a structured buff slot: name, duration,
mod, expiration trigger. Big design surface.

**No plan yet.**

### D. Passive trait engine

**Affects:** every race's Darkvision / damage resistance / saving-throw
advantage, Sneak Attack reqs, Dwarven Toughness, Fey Ancestry.

Most racial traits are passive — they apply automatically when a
specific roll happens (e.g. "Dwarves have advantage on saves against
poison"). Today they're descriptive only; players manually flip
advantage / disadvantage at roll time.

**No plan yet.** Tied to (B) — same intercept point.

### E. Action-economy tracker

**Affects:** Every ability button across the GM init tracker, mini-sheet
attacks / spells / monster-actions, and the full character sheet's
attacks + spells panels. Specifically: Cunning Action (Rogue Lv 2),
Second Wind / Action Surge (Fighter), Rage (Barbarian), Bardic
Inspiration (Bard), Healing Word / Misty Step / Counterspell / Shield /
Hellish Rebuke / Spiritual Weapon (any caster), Opportunity Attack +
Uncanny Dodge + Shield reactions, and every Channel Divinity / Ki /
Sorcery-point option that resolves to an action or bonus action.

**Why foundational:** Most per-feature plans above need to know "is
this clicking an action, bonus action, or reaction?" so they can both
consume the right per-turn slot and gate alternatives ("you've already
used your bonus action; Healing Word is unavailable until next turn").
Implementing the economy tracker first means (A) resource-picker, (B)
roll-time intercepts, and (C) buff slot can each read the economy
state instead of re-inventing per-turn tracking ad-hoc per feature.
This is the **biggest single source of leverage** for the whole class-
features roadmap — every Phase-3 work item under A becomes simpler
once the economy framework exists.

**Data model:**

Per combatant, on `battle.combatants[i].economy`:

```js
economy: {
    action: false,    // used this turn; cleared on nextTurn()
    bonus:  false,    // used this turn; cleared on nextTurn()
    reaction: false,  // used since the combatant's last start-of-turn;
                      // clears at the START of their next turn (so it
                      // persists across other combatants' turns within
                      // the same round)
    movement: 0,      // feet used this turn (informational; the GM may
                      // or may not enforce; for now just an integer
                      // that scales with token-drag distance)
}
```

Persists with the rest of battle state via the existing `saveBattle()`
localStorage path + the WS broadcast in `pushBattle()`. Resets driven
by the existing `nextTurn()` / `prevTurn()` / `startInitiative()`
control flow in `tabletop.html`.

**Ability metadata — where the action-cost tag lives:**

Each ability button carries `data-economy="action"|"bonus"|"reaction"|"free"|"none"`.
Sources:

- **Weapon attacks** (PC `.mini-strike-btn`, monster `.monster-strike-btn`,
  full-sheet `.atk-strike`) — default `action`. Off-hand
  Two-Weapon-Fighting attacks tag as `bonus`. Auto-tag at render time
  from the attack's `properties` field (presence of `"light"` +
  off-hand context → bonus).
- **Spells** (`mini-cast-btn`, `.sp-cast`) — parse `spell.casting_time`
  at render time. Map "1 action" → `action`, "1 bonus action" → `bonus`,
  "1 reaction" → `reaction`, anything longer (10 min, 1 hour) → `none`
  (out-of-combat — doesn't consume an in-combat slot). For SRD spells
  this field is already populated; for homebrew it's whatever the
  homebrew editor put there.
- **Channel Divinity options** — curated per the Channel Divinity 3-phase
  plan in `dnd5e_channel_divinity.js`. Each option has an
  `economy: "action"|"bonus"` field. Turn Undead is `action`; Preserve
  Life is `action`; War Domain's Guided Strike is `reaction`; etc.
- **Class features** — new curated table `dnd5e_feature_economy.js`
  mapping `(class_slug, feature_key)` → economy tag for non-spell,
  non-attack abilities (Cunning Action: bonus, Second Wind: bonus,
  Action Surge: free, Rage entry: bonus, Lay on Hands single use:
  action, etc.). Same shape as the existing `dnd5e_class_resources.js`
  recipe table.

**UI surface:**

Three chips inside the v2.4.21-streamlined init-card status row,
right-aligned after Tmp:

```
HP 33/33 · AC 18 · Spd 25 · Tmp 0   [Act ●] [Bns ○] [Rxn ○]
```

- Filled circle ● = used; empty ○ = available
- Color: green when available, amber when used
- Click a chip to manually toggle (GM override — clearing a slot mid-turn
  if a feature returned a use, marking a slot used for off-screen
  effects)
- Tooltip on hover/long-press explaining what consumed the slot ("Used
  for: Healing Word at 14:32")

When a slot is used, ability buttons tagged with the same economy class
get a `disabled-style` (50% opacity, cursor:not-allowed, but still
clickable for GM override). The disabled state signals "you've already
spent your bonus action" without preventing the click — the GM is
trusted to know when to override (e.g. Action Surge granted a second
action).

**Implementation phases:**

1. **Phase 1 — State model + manual toggle UI.** Add the `economy`
   object to combatants in `combatantFromToken` and the manual-add
   paths. Render the 3-chip strip in `renderBattle`. Hook click-to-toggle
   on each chip. Reset on `nextTurn` / `prevTurn` (action+bonus clear
   immediately; reaction clears when the *same* combatant's turn comes
   around again — track via a `_reactionResetOnNextTurn` flag). Ship as
   one commit; UI is immediately useful for manual tracking even without
   the auto-advance.

   **What to test in the VTT (after shipping Phase 1, currently v2.4.31):**
   1. Log in as the demo GM (`demo-gm@example.com` / `demopass`) at
      `/login` (use the v2.4.4 Fill button).
   2. Navigate to `/campaign/1` (the demo campaign auto-loads).
   3. Open the **Battle** drawer (the v2.4.5-renamed tab in the topbar).
      The init tracker is auto-populated from the v2.4.3 fix — 9
      combatants visible.
   4. Each combatant row should show three small chips under the
      Init/HP subline: `○ Act` · `○ Bns` · `○ Rxn` — all empty green
      circles (available).
   5. Click any chip → it flips to filled amber (●) and the tooltip
      changes to "used this turn". Click again → flips back. Repeat
      across all three chips on one combatant.
   6. Click **Next turn** (or the Next button if you've started
      initiative) → advance to the next combatant. The chips on the
      *new* active combatant reset to empty green; chips on the
      previous combatant stay where they were.
   7. Click **Start Initiative** → every combatant's chips reset to
      empty. Re-test the toggle on combatant 1, advance turns through
      the full round → chips reset correctly each time `turn_index`
      lands on a combatant.
   8. Reload the page → chips state persists for combatants whose
      slots were "used" (localStorage round-trip via `saveBattle`).
   9. Open the same campaign in a second browser tab as the GM →
      toggling a chip in tab A updates tab B within a second (via the
      WS `battle_update` broadcast from `pushBattle`). Players in the
      same campaign see read-only chip state (they can't toggle).

   **Demo updates required for Phase 1:** None. Chips render for any
   combatant whose `economy` field is initialized (which `combatantFromToken`
   handles at construction time + `_ensureEconomy` heals stale localStorage
   entries). The existing 9-combatant Tavern Brawl from v2.4.3+ exercises
   every code path: PCs (Pip / Thalindra / Tavik) with full mini-bodies,
   monsters with `buildMonsterInitSheet`, mixed initiative order. **Already
   shipped in v2.4.31; no demo seed change needed.**

2. **Phase 2 — Auto-advance from action / strike / cast buttons.** Each
   click on `.mini-strike-btn` / `.monster-strike-btn` / `.atk-strike`
   / `.mini-cast-btn` / `.sp-cast` reads its `data-economy` and marks
   the corresponding slot on the combatant's `economy` object. Spell
   `casting_time` parsing happens at template-render time for the full
   sheet, at `combatantFromToken` time for the mini-sheet monster
   actions, at the spell-row render in `_mini_sheet_card.html` for PCs.

   **What to test in the VTT after shipping Phase 2:**
   1. As the demo GM in `/campaign/1`, open the Battle drawer + start
      initiative. Verify Pip Quickfingers' (or any PC's) Act/Bns/Rxn
      chips begin empty.
   2. Expand Pip's init-card → click 🗡 Strike on the Shortsword
      attack. Expected: the roll fires in the roll log AND Pip's
      Act chip flips to filled amber. The Bns and Rxn chips stay
      empty.
   3. Click 🗡 Strike on the Dagger (also an action). Expected: roll
      fires; Act chip stays amber (already used); no Bns/Rxn change.
      The chip's "tooltip" should say "used this turn" but the click
      isn't blocked yet (gating is Phase 4).
   4. Open Thalindra Moonwhisper's init card → click 🪄 Cast on
      Healing Word (a 1-bonus-action spell). Expected: roll fires AND
      her Bns chip flips amber. Act stays empty.
   5. Click 🪄 Cast on Fireball (a 1-action spell). Expected: roll
      fires AND Act chip flips amber.
   6. Click 🪄 Cast on Shield (a 1-reaction spell). Expected: roll
      fires AND Rxn chip flips amber.
   7. Expand Vex (Bandit Captain) → click 🎯 Attack on Scimitar.
      Expected: monster action roll fires AND Vex's Act chip flips
      amber.
   8. Click **Next turn** until it cycles to Pip → all three chips
      reset to empty. Re-trigger steps 2-6 to confirm the cycle.

   **Demo updates required for Phase 2:**
   - Add `casting_time` field to every spell entry in `_wizard_sheet`
     and `_cleric_sheet` in `app/demo_seed.py`. The Phase 2 renderer
     reads `s.casting_time` directly to emit `data-economy` on the
     cast button; without it, every spell falls back to "action".
     Values per SRD: Fire Bolt / Mage Hand / Prestidigitation / Sacred
     Flame / Guidance / Light = "1 action"; Magic Missile / Shield /
     Cure Wounds / Healing Word / Bless = "1 action" except Shield
     ("1 reaction") and Healing Word ("1 bonus action"); Misty Step
     "1 bonus action"; Spiritual Weapon "1 bonus action"; Scorching
     Ray / Fireball / Counterspell = "1 action" except Counterspell
     ("1 reaction"); Hold Person / Lesser Restoration "1 action";
     Beacon of Hope / Revivify "1 action"; Spirit Guardians "1 action";
     Mass Healing Word "1 bonus action".
   - Verify Vex (Bandit Captain) has at least one attack with explicit
     `attack_roll: True` so the monster-strike branch exercises the
     auto-advance. (Already true in v2.3.31 — no change needed.)
   - **Heads-up:** the v2.4.19 lazy-loader (`/api/content/spells/<slug>`)
     can serve as a fallback for spells without inline `casting_time` —
     Phase 2 should read the SRD record on first click if `s.casting_time`
     is missing. Adding the field to the seed is the cleaner / faster
     path for the demo specifically.

3. **Phase 3 — Class-feature economy table.** Author
   `app/static/dnd5e_feature_economy.js` with the canonical per-feature
   action tag table. Used by the resource option-picker (Channel
   Divinity, Bardic Inspiration, Ki spend, etc.) to mark the right slot
   when the option is fired. The Channel Divinity 3-phase plan can drop
   its per-feature action-cost tracking and read from this table.

   **What to test in the VTT after shipping Phase 3:**
   1. (Requires Channel Divinity option-picker, prerequisite item #2
      on the priority list.) As the demo GM with Brother Tavik (Life
      Domain Cleric Lv 5), open the Battle drawer → expand Tavik's
      init-card.
   2. Click the Channel Divinity counter chip → option overlay opens
      with `Turn Undead` and `Preserve Life`. Click Turn Undead.
      Expected: CD counter decrements (1/1 → 0/1), the slot-DC roll
      fires to the log, AND Tavik's Act chip flips amber (Turn Undead
      is an action per `_CHANNEL_DIVINITY_OPTIONS.life`).
   3. Click Next turn through one full round so Tavik's slots reset.
      Click CD chip again → pick Preserve Life. Expected: same flow,
      Act flips amber (Preserve Life is also an action).
   4. If/when Pip's Cunning Action lands (Rogue Lv 2 feature, also
      Phase 3-tagged): click Cunning Action → Bns flips, Act stays
      empty. Click Action Surge (Fighter Lv 2 if a Fighter PC is
      added): no chip changes — Action Surge is `free` (it grants an
      extra action, doesn't consume one).

   **Demo updates required for Phase 3:**
   - Pip's `_rogue_sheet` in `app/demo_seed.py` needs an entry in a
     new `features` or `class_abilities` array on the sheet so the
     sheet renderer + curated feature_economy table can emit a
     clickable "Cunning Action" button (with a sub-picker for Dash /
     Disengage / Hide). The feature is unlocked at Rogue Lv 2; Pip
     is Lv 5, so it applies. Without this, the most visible Phase 3
     test (Pip clicks Cunning Action → Bns flips) has no UI to click.
   - Tavik's Channel Divinity counter from v2.4.15 already exists; the
     CD option-picker (priority item #2) ships it as a clickable.
     Phase 3 just needs `_CHANNEL_DIVINITY_OPTIONS.life` entries to
     carry `economy: "action"` per the Channel Divinity 3-phase plan.
     No new seed data; just the curated JS table needs the `economy:`
     field added to each option.
   - Optionally: add a Fighter PC to the demo party (Vex's bandits are
     fighter-shaped but treated as monsters; a real Fighter Lv 1+ PC
     would let Phase 3 exercise Action Surge + Second Wind). Out of
     scope for Phase 3 itself; filed as a separate demo-data follow-up.

4. **Phase 4 — Gating + GM override.** Disable buttons whose economy
   slot is used (50% opacity + cursor:not-allowed). GM can shift+click
   or right-click to override. Players see a tooltip explaining why.
   Players who try to click anyway get a confirm: "You've already used
   your bonus action this turn. Use it anyway?" — yes path manually
   advances state, no path closes the modal.

   **What to test in the VTT after shipping Phase 4:**
   1. As Pip the player (`demo-alice@example.com`), click 🗡 Strike on
      Shortsword. Act flips amber.
   2. Try to click 🗡 Strike on the Dagger again. Expected: the button
      visually dims to ~50% opacity, cursor shows
      `not-allowed` on hover. Tooltip: "Action already used this
      turn — your Act slot is spent".
   3. Click anyway. Expected: a small confirm modal appears: "You've
      already used your action this turn. Roll the Dagger attack
      anyway?". Click Cancel → modal closes, roll doesn't fire.
   4. Repeat step 3, click Confirm. Expected: roll fires; Act chip
      stays amber (already amber). The roll log records the dagger
      attack.
   5. As the GM (`demo-gm@example.com`), perform the same dimmed-button
      click → no confirm modal; the roll just fires. Phase 4 includes
      a GM-bypass for the modal.
   6. Click Next turn. The chips reset to empty; buttons return to
      full opacity.

   **Demo updates required for Phase 4:** None directly. Phase 4 is
   pure UI/UX layered on Phase 2's auto-advance — any combatant whose
   slot gets flipped by Phase 2 also gets buttons dimmed by Phase 4.
   The demo's existing spell + attack rosters from Phase 2's data
   updates exercise every code path. Optional: a one-line tooltip
   string update in the explainer for the v2.5.0 settings
   `potions_as_bonus_action` toggle, dropping the "currently
   informational" hedge once Phase 4 actually gates the slot.

5. **Phase 5 — Movement tracker (optional).** Add a `Mov 30/30 ft`
   chip; auto-decrement when the GM drags a token (the existing
   `/api/.../token/.../move` endpoint already broadcasts moves with
   from/to coordinates — tie into that to compute distance moved and
   subtract from the budget).

   **What to test in the VTT after shipping Phase 5:**
   1. As the demo GM on `/campaign/1`, start initiative on the Tavern
      Brawl. The active combatant's init-card should show a fourth
      chip: `Mov 30/30 ft` (Pip's speed) or whatever each combatant's
      `sheet.speed` is.
   2. Drag Pip's token on the canvas by 2 grid cells (140 px at 70
      px/cell = 2 squares = 10 ft). Expected: the chip updates to
      `Mov 20/30 ft`.
   3. Drag again by 3 grid cells (15 ft). Expected: chip updates to
      `Mov 5/30 ft`.
   4. Drag past the budget — drag another 2 cells (10 ft). Expected:
      chip shows `Mov 0/30 ft` in red or amber (overrun indicator) —
      the drag isn't blocked (the GM can always override), just
      flagged visually.
   5. Click Next turn → Pip's movement resets to `Mov 30/30 ft`.
   6. (Optional) Click the Mov chip → manually edit the value, e.g.
      to reflect a Dash bonus action that doubled the budget for
      this turn.

   **Demo updates required for Phase 5:**
   - Every demo combatant already has a `speed` field. Tavik's
     `_cleric_sheet` has `speed: 25` (Hill Dwarf); Pip has `speed: 25`
     (Halfling); Thalindra has `speed: 30` (Elf); the NPC templates
     ship per the SRD. **No seed change needed for PCs.**
   - For monsters whose template `sheet.speed` is a structured dict
     (e.g. Grixxa's `{"walk": 30}` from `seed_homebrew_files`),
     Phase 5 needs to read `sheet.speed.walk` rather than `sheet.speed`
     directly. The homebrew speed shape is already a dict for every
     demo monster; Phase 5's chip-render code should handle both
     scalar (PC sheets: `speed: 25`) and dict (monster sheets:
     `speed: {walk: 30}`) shapes. **Code change in Phase 5, not seed
     data.**
   - The grid scale is per-map: `map.grid_size_px = 70` on the demo
     tavern with `grid_type = "square"`. 5 ft / square is the 5e
     default; Phase 5 should hardcode `5 ft per grid cell` initially
     and read it from a per-campaign setting only if/when a non-5-ft
     grid case appears.

**Dependencies:**

- Sits between (B) roll-time intercepts and (C) buff slot in the
  cross-cutting graph. (B) wants to know "what kind of action is this
  roll" — the economy tag answers it. (C) wants to know "what activated
  this buff" — same.
- Phase 1+2 are independent and shippable on their own.
- Phase 3 depends on the Channel Divinity option-picker existing
  (cross-cutting A's Phase 1).

**What unblocks after each phase:**

- After Phase 1 (manual): GMs can manually track action economy during
  play. No mechanical gating, but it's immediately useful.
- After Phase 2 (auto-advance from buttons): Attacks / spells auto-mark
  their slot. Players see Healing Word's "bonus" tag illuminate when
  they cast it. Heuristics for Sneak Attack / Two-Weapon Fighting still
  need tuning.
- After Phase 3 (feature table): Cunning Action / Second Wind / Action
  Surge / Bardic Inspiration / etc. all have correct slot tagging
  without per-feature code changes — just adding an entry to the
  table.
- After Phase 4 (gating): The action economy becomes UI-enforced
  rather than just visible. Mistakes get flagged before they happen.
- After Phase 5 (movement): The fifth column closes the "what can my
  character still do this turn" UX gap.

**Related: house-rule toggles (shipped piecemeal alongside the
economy phases).** Per-campaign Boolean preferences on the `Campaign`
model affect how the economy framework interprets specific button
clicks. First example landed in v2.5.0: `potions_as_bonus_action`.

**What to test in the VTT for the `potions_as_bonus_action` toggle
(v2.5.0):**

1. As the demo GM (`demo-gm@example.com`), navigate to
   `/campaign/1/settings`.
2. Scroll to the **📜 House rules** fieldset (between the
   GM-font-override section and the 🎵 Audio fieldset).
3. The checkbox "Potions are a bonus action" should render unchecked
   by default (RAW). Below it: explainer text flagging the rule as a
   Xanathar's / Tasha's variant + a note that the toggle is currently
   informational until action-economy Phase 2 ships the "Use Item"
   button on consumable inventory items.
4. Tick the checkbox → click the form's **Save** button at the bottom
   of the page. Expected: redirect / re-render with the checkbox now
   ticked. Reload the page → still ticked (persisted via the v54
   schema column `campaigns.potions_as_bonus_action`).
5. Untick + Save → checkbox unticks, persists.
6. Verify the DB column directly (operator sanity check):
   `docker exec simplevtt-db psql -U simplevtt -d simplevtt -c
   "SELECT id, name, potions_as_bonus_action FROM campaigns;"` →
   shows the toggle value matching the UI.
7. (After action-economy Phase 2 + the "Use Item" potion button
   land): with the checkbox on, click the Use button on a Healing
   Potion item on Tavik's sheet. Expected: HP increases, qty
   decrements, AND Tavik's Bns chip flips amber. With the checkbox
   off, the same click flips Act chip amber instead. This step is
   filed for the Phase 2 follow-up.

**Demo updates required for the house-rule toggle to be testable
end-to-end:**

- v2.5.0 ships the column + the settings checkbox. Steps 1-6 above
  are runnable today.
- Step 7 (the actual mechanical effect) is gated on **two** future
  pieces:
  1. The action-economy Phase 2 work that adds `data-economy` tags
     + auto-advance to inventory item buttons.
  2. A **"Use Item" button on consumable inventory rows** in
     `sheet_dnd5e.html`. The row's existing equip toggle / qty input
     / × delete cluster doesn't include a "Use" action; v2.4.13's
     rich-item shape supports `type: "consumable"` but the sheet
     renders consumables identically to gear today. Adding the Use
     button is a small follow-up (~30 LOC: a button in the row,
     a click handler that decrements qty + posts to the HP endpoint
     + marks the economy slot per `campaign.potions_as_bonus_action`).
- **Seed updates required to test end-to-end:** add a
  `{name: "Potion of Healing", type: "consumable", qty: 1, _slug:
  "potion-of-healing", desc: "..."}` entry to each PC's inventory
  in `app/demo_seed.py`. The SRD ships
  `app/data/local/dnd5e/items/potion-of-healing.json` so the v2.4.13
  `_loadItemActions` lazy-loader fills in the description on first
  row-expand. Suggested per-PC counts: Pip 2 (rogue stash), Tavik 3
  (cleric's emergency reserve), Thalindra 1 (wizard backup).

---

## Order of priority (rough)

1. **(E) Action-economy tracker — Phase 1+2** — manual chip strip +
   auto-advance from existing strike / cast buttons. Most leverage of
   any single piece of infrastructure: every subsequent per-feature
   item below benefits from being able to ask "what action class is
   this?". Phase 1 ships standalone; Phase 2 follows immediately.
2. **Channel Divinity option-picker** (Phase 1-3 plan in 2.4.15 commit) —
   Tavik's most visible missing feature in the demo. Now reads economy
   state from (E) so Turn Undead's "action" cost is auto-tracked.
3. **Lay on Hands target-picker** — pairs with Channel Divinity work;
   same UI shape (resource → option overlay → target → effect).
4. **Wild Shape transformation UI** — already half-wired
   (`_doMiniTransform`); finishing the form-picker dropdown closes
   Druid Lv 2 functionality.
5. **Bardic Inspiration target-picker** — completes Bard core loop.
6. **(E) Action-economy — Phase 3+4** — class-feature table + gating
   with GM override. By this point items 2-5 have populated enough
   features that the table needs the curated entries; piggybacks on
   their work.
7. **Cross-cutting (A) generalized** — refactor 2-5 onto a single
   `resource → option → target` framework.
8. **Sneak Attack / Divine Smite per-attack uplift toggle** — pairs of
   adjacent damage-uplift features.
9. **(B) Roll-time intercepts** — big architectural work; unblock Lucky
   / Indomitable / Reliable Talent / Portent / Champion Improved
   Critical.
10. **(C) Buff slot** — even bigger; unblock everything concentration
    / duration-based.
11. **(D) Passive trait engine** — likely subsumed by (B) once the
    intercept exists.
12. **(E) Action-economy — Phase 5** — movement tracker. Lowest-priority
    polish; useful for table-mat-style play but optional for digital.

Items 1-5 are user-visible per-feature wins (or in #1's case, an
immediately-useful UI primitive that the wins build on); 6+ are
infrastructure changes that pay for themselves across many features.
