# Building an encounter

**Audience:** GMs prepping combats ahead of (or during) a session.
**Version stamp:** v2.639.0.
**Screenshots refreshed:** v2.639.0 (regenerate with `python3 tests/harness_ui/capture_encounters.py`).

An **encounter** in SimpleVTT is a saved bundle — a map, the GM-owned tokens, the initiative seed, optional per-player spawn points, and an optional ambient playlist — that you can drop onto the table with a single click. Prep your fights in advance, then load them mid-session without scrambling. Screenshots are from the demo campaign **The Sundered Vault** and its seeded **Tavern Brawl** encounter.

You manage encounters in two places:

- **The encounter library** (*Settings → World → Encounters*) — draft and organize encounters before play.
- **The Battle drawer** on the tabletop (`/campaign/<id>`) — save the current board as an encounter, and load encounters live.

## The encounter library

*Settings → World → Encounters* lists every saved encounter, grouped into folders with search, sort, and tag filters. Each card shows its map, token count, spawn-point count, and tags, with **Duplicate / Edit / Delete** controls. **+ New Encounter** drafts a fresh one.

![The encounter library with the Tavern Brawl encounter expanded](/static/docs/encounters/01-encounter-library.png)

## The monster roster: token templates

An encounter's NPC tokens come from **token templates** — reusable monster/NPC definitions you build once and drop in repeatedly. The roster lives at *Settings → World → Token templates*; each template carries a name, art, tags, type (D&D 5e / Generic), and a full stat-block sheet you can edit.

![The token-template roster of monsters and NPCs](/static/docs/encounters/02-token-templates.png)

## Adding monsters from the SRD bestiary

Don't build common monsters by hand — import them. The **🔍 Open5e** search in the Token templates section searches the **5e bestiary** (plus your campaign's homebrew). Find a creature and **Import** drops it in as a new token template with its stat block pre-filled.

![Searching the bestiary for "goblin" with Import buttons](/static/docs/encounters/03-bestiary-search.png)

> Homebrew monsters you've authored show up in the same search, ahead of the SRD results — so your custom creatures and the SRD bestiary share one "add a monster" flow.

## Building the encounter

The fastest way to build an encounter is to **stage it on the board, then snapshot it**:

1. **Activate the map** the fight happens on (see **[Maps, grids & tokens](maps-grids-tokens.md)**).
2. **Place the tokens** — monsters from your templates (Add Token → Library) and the player characters.
3. **Roll initiative** in the Battle drawer's initiative tracker.
4. In the tabletop **Battle drawer**, open **💾 Save current state** and either **Update** an existing encounter or save a new one. This snapshots the token positions + initiative + map binding into the encounter.

After that, loading the encounter restores exactly that board.

## Spawn points (optional)

Instead of dropping players at their snapshot positions, an encounter can use **spawn points** — per-player coordinates you mark on the bound map. Expand an encounter in the library, tick **Use spawn points for players**, and **Set** each character's spot (click the map to place it). When the encounter loads, each PC drops onto their marked square — handy for "you enter from the south door" framing.

## Auto-load on session start

Wire an encounter to fire automatically when you start the session: *Settings → Basic info → ⚔ Encounter on session start*. Pick a default encounter and it loads the moment you hit **Start session** — same flow as the manual Load.

![The Encounter-on-session-start default-encounter picker](/static/docs/encounters/04-default-encounter.png)

## Loading an encounter

Loading (the **▶ Load** button on a card, the live list in the Battle drawer, or auto-load on session start) does a clean reset:

- **Clears** the target map's existing tokens.
- **Switches** to the encounter's bound map if it differs.
- **Re-creates** the GM/monster tokens from the snapshot, and the player tokens — at their **spawn points** if set, otherwise their snapshot positions.
- Optionally **starts the bound playlist** for instant ambience.

So a prepped encounter takes you from "between scenes" to "roll initiative" in one click.

## Where to go next

- **[Maps, grids & tokens](maps-grids-tokens.md)** — set up the board and place the tokens an encounter snapshots.
- **[Running a session as GM](running-a-session-as-gm.md)** — initiative, the target picker, and the GM tools once the fight is live.
- **[Inviting players](inviting-players.md)** — make sure the party's characters exist before you build around them.
