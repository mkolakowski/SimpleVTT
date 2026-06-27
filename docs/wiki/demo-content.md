# Demo content — campaigns, PCs & NPCs

The `DEMO_MODE` deployment ships **five leveled sample campaigns** so you can
see how the VTT and D&D 5e characters feel across the whole level curve. The
dataset **resets on a fixed interval** (default 60 min) — anything you change
is wiped on the next reset.

Every PC is chosen so its class + subclass **showcases a feature gained around
that campaign's level** — the demo doubles as a "what does this class get at
level N?" tour. Each PC's sheet **Notes** carry three blocks: a one-line
**Description**, a **Roleplay** hook, and **How to play** (tactics that lean on
the showcase feature).

> **Art status:** every leveled demo now ships **full art** — a painterly
> battle map plus PC portraits and NPC tokens — generated from the prompts in
> the collapsed **Generation prompts** section below (the same prompts live in
> the demo image-prompts checklist). Art is dropped under
> `app/static/demo/...` and wired in `app/demo_campaigns.py`. The only
> remaining placeholder is the **archived Sundered Vault**'s `tavern.png` map.

## Accounts

All accounts share the password **`demopass`**.

| Email | Role | Campaigns |
|---|---|---|
| `demo-gm@example.com` | Admin + GM | GM of L3, L5, L13, L18 |
| `demo-gm2@example.com` | GM (not admin) | GM of L9 (Saltmarsh) |
| `demo-alice@example.com` | Player | L3, L5 |
| `demo-bob@example.com` | Player | L5, L9, L13 |
| `demo-carol@example.com` | Player | L3, L5, L18 |
| `demo-dave@example.com` | Player | L9, L13 |
| `demo-erin@example.com` | Player | L9, L18 |

## The five campaigns

The active leveled lineup is **L3 / L5 / L9 / L13 / L18**. The original
hand-built L5 ("The Sundered Vault") is kept as an **archived** showcase
(see the Level 5 section) — six campaigns seed in total, five active.

### Level 3 — The Goblin Warrens (Tier 1) · GM: demo-gm
A goblin warband raids the trade road from a tunnel warren. *Art: ✅ battle map.*

| PC | Class / subclass · race | Owner | Level-3 showcase |
|---|---|---|---|
| Thorin Battlehammer | Fighter / Battle Master · Mountain Dwarf | demo-gm | **Maneuvers** (4 superiority dice) — Trip / Riposte / Menacing |
| Nyx Shadowstep | Rogue / Assassin · Wood Elf | alice | **Assassinate** (adv vs. un-acted, auto-crit vs. surprised) + Sneak Attack 2d6 |
| Sister Elsbeth | Cleric / Light · Human | carol | **Channel Divinity: Radiance of the Dawn** + first 2nd-level spells |
| Aldric the Sudden | Wizard / Evocation · Forest Gnome | demo-gm | **Sculpt Spells** (carve allies out of his AoEs) |
| Brisa Quickarrow | Ranger / Hunter · Lightfoot Halfling | demo-gm | **Colossus Slayer** (+1d6 vs. damaged) |

NPCs: Goblin, Wolf, Bandit, Bandit-Captain "warlord" (SRD). *Art: ✅ token art.*

### Level 5 — The Tide-Wracked Catacombs (Tier 2) · GM: demo-gm
The remade Level-5 demo — a drowned crypt beneath a ruined lighthouse spills
undead onto the coast at every high tide. Each PC shows off a feature their
class gains at the level-5 power spike. *Art: ✅ battle map.*

| PC | Class / subclass · race | Owner | Level-5 showcase |
|---|---|---|---|
| Sir Gareth Tidebreaker | Fighter / Champion · Human | demo-gm | **Extra Attack** (two swings) + Improved Critical |
| Maelis Stormcaller | Wizard / Evocation · High Elf | demo-gm | **3rd-level: Fireball** (8d6) + Sculpt Spells |
| Mother Coralind | Cleric / Tempest · Half-Elf | carol | **3rd-level: Spirit Guardians** (15-ft radiant aura) |
| Vesh Quillon | Rogue / Assassin · Wood Elf | alice | **Uncanny Dodge** (halve a hit) + Sneak Attack 3d6 |
| Hrudd Saltmane | Barbarian / Berserker · Half-Orc | demo-gm | **Extra Attack** + Fast Movement + Frenzy |

NPCs: Skeleton, Zombie, Ghoul, Wight "Captain of the Drowned" (SRD undead). *Art: ✅ token art.*

> **Archived original — The Sundered Vault.** The flagship hand-built demo (a
> full one-of-every-class party of 15 PCs in the **Tavern Brawl** — Pip
> Quickfingers, Thalindra Moonwhisper, Brother Tavik Stonebrow, Sir Caelan
> Lightbringer, Garrik Ironside, …) is still seeded as campaign **id 1** (the
> harness anchor) but is now **archived** (v2.605.0) — it lives in the lobby's
> **Archived** section as a live showcase of the archive feature, fully
> reachable by URL and via the API. *Art: ✅ map `tavern.png` + some PC/NPC tokens.*

### Level 9 — Storm Over Saltmarsh (Tier 2→3) · GM: demo-gm2 *(the second GM)*
Sahuagin raiders boil up from a storm-wracked reef. *Art: ✅ battle map.*

| PC | Class / subclass · race | Owner | Level-9 showcase |
|---|---|---|---|
| Vaelith Stormscale | Sorcerer / Draconic · Tiefling | dave | **5th-level spells: Cone of Cold** |
| Lirael Songhaven | Bard / Lore · Half-Elf | bob | **Hold Monster** (5th) + Countercharm |
| Oakheart Mossbrook | Druid / Moon · Firbolg | erin | **Conjure Elemental** (5th) + high-CR Wild Shape |
| Ser Kadvan Tideward | Paladin / Vengeance · Human | demo-gm2 | **Aura of Courage** + Divine Smite |
| Brother Tym | Monk / Open Hand · Water Genasi | demo-gm2 | **Unarmored Movement over water/walls** + Stunning Strike |

NPCs: Sahuagin, Reef Shark, Water Elemental, a drag-spawn young dragon (SRD). *Art: ✅ token art.*

### Level 13 — The Shadowfell Spire (Tier 3) · GM: demo-gm
A spire of black glass bleeds the Shadowfell into the world. *Art: ✅ battle map.*

| PC | Class / subclass · race | Owner | Level-13 showcase |
|---|---|---|---|
| Maelen Farsight | Wizard / Divination · High Elf | bob | **7th-level: Forcecage** + Portent |
| Cassius Emberbinder | Warlock / Fiend · Tiefling | dave | **Mystic Arcanum 6th + 7th** (Circle of Death, Finger of Death) |
| High Cleric Doran | Cleric / War · Goliath | demo-gm | **7th-level: Divine Word** + Divine Strike |
| Hruld Skullcleaver | Barbarian / Totem · Half-Orc | demo-gm | **Brutal Critical (2)** + Relentless Rage |
| Wisp Underbough | Rogue / Arcane Trickster · Forest Gnome | demo-gm | **Magical Ambush** + Sneak Attack 7d6 |

NPCs: Wraith, Vampire Spawn, Mind Flayer, Specter (SRD). *Art: ✅ token art.*

### Level 18 — The Dragon's Apotheosis (Tier 4) · GM: demo-gm
An ancient red wyrm ascends to godhood atop a volcano. *Art: ✅ battle map.*

| PC | Class / subclass · race | Owner | Level-18 showcase |
|---|---|---|---|
| Archmagus Selene | Wizard / Evocation · High Elf | demo-gm | **9th-level: Meteor Swarm / Wish** + Overchannel |
| Ignar Flamesoul | Sorcerer / Draconic · Dragonborn | demo-gm | **Draconic Presence** + Time Stop (9th) |
| Dame Aurelia Dawnward | Paladin / Devotion · Aasimar | carol | **30-ft auras** + Holy Nimbus + Holy Avenger |
| Bryn Ironwall | Fighter / Champion · Goliath | demo-gm | **Survivor** + 3 attacks + crit 18–20 |
| Thornroot Elder | Druid / Moon · Firbolg | erin | **9th-level: Storm of Vengeance** + Archdruid |

NPCs: Adult Red Dragon (Pyraxis), Fire Giants, Cult Archmage, Salamander (SRD). *Art: ✅ token art.*

---

<details>
<summary><strong>Generation prompts</strong> (the prompts behind the now-shipped art — kept for reference & regeneration)</summary>

All prompts target a consistent look: **painterly digital fantasy art, dramatic
lighting, no text/watermark**. Battle maps are **top-down, grid-aligned,
seamless edges**; portraits/tokens are **bust framing on a transparent or plain
background, centred**.

### Battle maps (top-down, 70px-per-square grid friendly)

- **The Goblin Warrens (entrance)** — top-down cave-mouth into a goblin tunnel warren: muddy entrance, crude wooden palisade, scattered bones and cookfires, tunnel openings, torchlight. ~20×14 squares.
- **The Tide-Wracked Catacombs** — top-down flooded crypt beneath a ruined lighthouse: ankle-deep seawater pooling between barnacle-crusted sarcophagi, broken burial niches, kelp and bone debris, a collapsed lighthouse stair descending into the dark, faint phosphorescent glow at the water's edge. ~20×14 squares.
- **The Sundered Tavern** *(placeholder `tavern.png` — the lone un-regenerated map)* — top-down two-storey roadside tavern interior: bar to the east, door to the west, overturned tables, a brawl in progress.
- **The Drowned Reef** — top-down storm-lashed coral reef at low tide: tide pools, jagged coral, a half-sunken shipwreck, sahuagin lair openings, churning surf at the edges. ~23×16 squares.
- **The Shadowfell Spire (threshold)** — top-down obsidian plaza before a spire of black glass: cracked flagstones, drifting shadow-mist, guttering violet braziers, grasping dead hands at the margins. ~23×17 squares.
- **The Caldera Throne** — top-down volcanic caldera rim: rivers of lava, basalt causeways, a central obsidian throne-dais, ember haze, a dragon-sized landing ledge. ~26×19 squares.

### PC portraits (bust, fantasy character art)

- *Level 3:* Mountain-dwarf Battle Master with a warhammer; wood-elf assassin in dark leathers; human Light-domain cleric haloed in dawn-light; forest-gnome evoker mid-spark; halfling Hunter ranger with a longbow.
- *Level 5 (Catacombs):* storm-cloaked human Champion knight with a longsword; high-elf evoker cradling a forming fireball; half-elf Tempest cleric ringed in spectral wrath; wood-elf assassin rogue half in shadow; half-orc berserker mid-roar with a greataxe.
- *Level 9:* tiefling storm-sorcerer wreathed in frost; half-elf lore bard with a rapier and lute; towering firbolg moon-druid; grim human Vengeance paladin in plate; serene water-genasi monk.
- *Level 13:* ice-calm high-elf diviner; charismatic tiefling fiend-warlock with infernal sigils; mountainous goliath war-priest with a maul; scarred half-orc totem barbarian mid-roar; impish forest-gnome arcane trickster.
- *Level 18:* poised high-elf archmage with meteor-light; proud dragonborn sorcerer breathing fire; radiant aasimar paladin with glowing wings and a holy sword; stoic goliath champion with a greatsword; ancient firbolg archdruid wreathed in storm.

### NPC tokens (top-down or bust ring tokens)

- *Tier 1:* goblin skirmisher, dire wolf/warg, human bandit, a brutish goblin warlord.
- *Tier 2 (Catacombs):* a brine-crusted skeleton, a bloated drowned zombie, a gaunt tide ghoul, a barnacled wight "Captain of the Drowned" in rusted mail.
- *Tier 2 (Saltmarsh):* sahuagin raider, sahuagin priestess, reef shark, a translucent water/tide elemental.
- *Tier 3 (Spire):* a tattered wraith, a feral vampire spawn, an illithid mind flayer, a wispy specter.
- *Tier 4 (Caldera):* a colossal ancient red dragon (Pyraxis), fire-giant honor guard, a robed cult archmage, a coiling salamander.

</details>

This guide is surfaced at `/wiki/demo-content`.
