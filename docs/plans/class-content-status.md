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
2. **Phase 2 — Auto-advance from action / strike / cast buttons.** Each
   click on `.mini-strike-btn` / `.monster-strike-btn` / `.atk-strike`
   / `.mini-cast-btn` / `.sp-cast` reads its `data-economy` and marks
   the corresponding slot on the combatant's `economy` object. Spell
   `casting_time` parsing happens at template-render time for the full
   sheet, at `combatantFromToken` time for the mini-sheet monster
   actions, at the spell-row render in `_mini_sheet_card.html` for PCs.
3. **Phase 3 — Class-feature economy table.** Author
   `app/static/dnd5e_feature_economy.js` with the canonical per-feature
   action tag table. Used by the resource option-picker (Channel
   Divinity, Bardic Inspiration, Ki spend, etc.) to mark the right slot
   when the option is fired. The Channel Divinity 3-phase plan can drop
   its per-feature action-cost tracking and read from this table.
4. **Phase 4 — Gating + GM override.** Disable buttons whose economy
   slot is used (50% opacity + cursor:not-allowed). GM can shift+click
   or right-click to override. Players see a tooltip explaining why.
   Players who try to click anyway get a confirm: "You've already used
   your bonus action this turn. Use it anyway?" — yes path manually
   advances state, no path closes the modal.
5. **Phase 5 — Movement tracker (optional).** Add a `Mov 30/30 ft`
   chip; auto-decrement when the GM drags a token (the existing
   `/api/.../token/.../move` endpoint already broadcasts moves with
   from/to coordinates — tie into that to compute distance moved and
   subtract from the budget).

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
