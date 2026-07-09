# Self-test SRD coverage — audit & demo evaluation

This is the coverage map for the Admin-Center demo [self-test](self-test.md): what
D&D 5e SRD mechanics it exercises, what it *doesn't* yet, and — because
applicability depends on each demo's party/monsters/map — **what each demo can
test**. It backs the **🎓 Rules deep-dive** testing tier (a second level of
checks layered on top of the original "Core" smoke test).

## The two tiers

- **Core** (`movement, combat, doors, spells, gates`) — the original smoke test:
  token movement, doors, initiative, a bare weapon attack, an NPC strike, a
  first-spell cast, and the off-turn (403) / over-budget (409) gates.
- **Rules deep-dive** (added incrementally) — deeper SRD mechanics that need an
  active battle + a target combatant, each **applicability-skipped per demo**
  (a check records `skip`, never `fail`, when the demo lacks the required
  class/feature/target). Phases: `rest`, `heal`, `death_saves`, `concentration`, `reactions` (shipped), then
  `death_saves`, `reactions`, `saves`, `features`.

Every deep check is a smoke test — endpoint 200 + the expected state delta + the
broadcast a client reads — not exhaustive rules validation (the per-mechanic
harness tests in `tests/harness/` own that). Mutations restore via the existing
teardown (token snapshot + battle snapshot + a long rest for any PC whose sheet
or slots were touched); the **♻ Reseed** button is the guaranteed-clean baseline.

## Audit — implemented, harness-proven, but historically NOT in the self-test

Each family below has passing endpoint tests in `tests/harness/` (endpoints work)
yet was invisible to the self-test. Endpoints live in
`app/routes/tabletop_routes.py`.

| Family | Drive with | Tier phase |
|---|---|---|
| Short rest / hit dice | `/character/{id}/rest {"type":"short"}` | `rest` ✅ shipped |
| Healing | `/cast_healing_word`; `/cast_spell`(Cure Wounds); `/apply_healing {cast_id}` | `heal` ✅ shipped |
| Concentration + damage cascade | `/concentration {character_id,spell_name,rounds}`; damage the caster; `DELETE /concentration/{id}` | `concentration` ✅ shipped |
| Death saves / stabilize | `/character/{id}/death-save`; `/death-save/override`; `/stabilize`; `/medicine_stabilize` | `death_saves` ✅ shipped |
| Reactions / opportunity attacks | `/attack {is_opportunity_attack:true}`; `/use_reaction` | `reactions` ✅ shipped |
| Saving-throw → condition | `/cast_spell` a save spell, then `/roll_request/{id}/respond`; `/use_repeated_save` | `saves` |
| Class features | `/use_rage` `/use_second_wind` `/use_action_surge` `/use_lay_on_hands` `/use_stunning_strike` `/use_bardic_inspiration` `/use_font_of_magic_to_slot`; Divine Smite = `/attack {spend_spell_slot,bonus_damage,...}` | `features` |
| Buff lifecycle | `/character/{id}/buffs`; `/end_buff {character_id,key}` | (within `saves`/`features`) |
| Damage undo | `/undo_attack_damage {attack_id}` | deferred |
| Resistance / immunity / vuln / temp-HP | `/attack` vs a typed/buffed target; assert reduced/doubled/absorbed HP | deferred |
| Legendary / lair | `/use_legendary_action`; `/spend_legendary_resistance`; `/trigger_lair_action` | deferred (L18) |
| Exhaustion, grapple/dash/hide, generic feature/item | `/use_feature` `/use_item` `/use_grapple` `/use_dash` … | deferred |

## Evaluation — demos vs SRD (what each demo can test)

Applicability is decided from the seeded sheets/monsters/map, so a check the demo
can't support records a **skip**. Class list per demo (leveled campaigns are
gridless; the flagship is the only square-grid demo and carries one of every
class):

| Demo (campaign) | Party classes | Casters (heal/conc/saves) | Class features | Notable monsters | Map |
|---|---|---|---|---|---|
| **L3 Goblin Warrens** | Fighter(BM), Rogue, Cleric(Life), Wizard, Ranger | Cleric, Wizard, Ranger | Second Wind, Action Surge, Sneak Attack, BM maneuvers | goblins, warg, bandit-captain(Parry reaction) | closed **gate door**, dark + dynamic fog |
| **L5 Tide-Wracked** | Fighter(Champ), Wizard, Cleric(Life), Rogue, Barbarian | Cleric(Revivify), Wizard(Fireball) | **Extra Attack**, **Rage**, Uncanny Dodge, Second Wind | ghoul **paralyze**, wight **drain** | **water terrain**, dark fog |
| **L9 Saltmarsh** (gm2) | Sorcerer, Bard, Druid, Paladin, Monk | Sorcerer(**Metamagic**), Bard(**Inspiration**), Druid | **Divine Smite**, **Lay on Hands**, **Ki/Stunning Strike**, Cutting Words | dragon **breath**, Frightful Presence | water + **difficult polygon**, hotspot |
| **L13 Shadowfell** | Wizard, Warlock, Cleric(Life), Barbarian, Rogue(AT) | Wizard, Warlock(**pact/Mystic Arcanum**), Cleric | Rage, Arcane Trickster spells | mind flayer **Mind Blast stun**, wraith drain | colored/typed lights, GM pin |
| **L18 Caldera** | Wizard, Sorcerer, Paladin, Fighter, Druid | Wizard(9th), Sorcerer(9th), Druid(Archdruid) | Divine Smite, Lay on Hands, **Indomitable/Action Surge** | Adult Red Dragon **legendary + lair**, breath | **lava hazard terrain** |
| **Sundered Vault** (id 1, archived) | one of EVERY class (15 PCs) | Wizard, Cleric, Bard, Sorcerer, Warlock, Druid, Ranger, Paladin | **all** features + variant subclasses (Vow of Enmity / Form of the Beast / Drunken Technique); NPC caster Soren (attack-roll + save-DC) | square grid, wood + **secret** door, breath/legendary fixtures | dim, walls |

**Takeaways.** `heal / rest / concentration / death_saves / reactions / saves`
are exercisable in essentially every demo (they ride spell slots + battle/HP +
death-save state). **Class-feature** coverage is broadest at L9 (Paladin, Monk,
Bard, Sorcerer) + L5/L13 (Barbarian, Fighter) and total in the flagship.
**Legendary/lair** is L18 (+ the flagship's drag-spawn Adult Red Dragon).

### Demo-provisioning note (class-feature resources)

The resource-based feature endpoints (`/use_rage`, `/use_second_wind`,
`/use_action_surge`, `/use_lay_on_hands`, `/use_stunning_strike`,
`/use_bardic_inspiration`, `/use_font_of_magic_to_slot`) read a matching row in
`sheet["resources"]` and 404 (`"No X resource on this sheet"`) when it's absent.
The **leveled demo sheets** (`app/demo_campaigns.py`) historically shipped the
`class_features` text but **not** those resource counters — so those buttons 404
for players too. The `features` phase's arrival is paired with enriching those
sheets (`extra={"resources":[…]}`, keys `rage / second-wind / action-surge /
indomitable / lay-on-hands / ki / bardic-inspiration / sorcery-points`, values by
class+level) so the features actually work; the flagship (`app/demo_seed.py`)
already carries them.

## Status

- **Core tier:** shipped (see the [self-test guide](self-test.md)).
- **Rules deep-dive:** `rest`, `heal`, `death_saves`, `concentration`, `reactions` shipped; `
  reactions / saves / features` land incrementally as same-shape additions.
- **Deferred:** damage-undo, resistance/temp-HP deltas, legendary/lair,
  exhaustion, grapple/dash/hide, generic feature/item.
