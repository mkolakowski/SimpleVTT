# Maps, grids & tokens

**Audience:** GMs running encounters on a battle map.
**Version stamp:** v2.637.0.
**Screenshots refreshed:** v2.637.0 (regenerate with `python3 tests/harness_ui/capture_maps_tokens.py`).

The battle map is the GM's stage: you upload a map image, choose a grid, make it the active map, then place player and monster tokens on it. This guide walks the whole loop. Screenshots are from the demo campaign **The Sundered Vault**, which ships a tavern map with a grid and a dozen tokens already placed.

## Uploading & managing maps

Maps live under **Campaign settings → World → Maps**. The table lists every map in the campaign with its grid, size, and status; the active map is flagged, and **Activate** switches which one the table sees. The **+ Upload map** form adds a new one.

![The Maps management table in campaign settings](/static/docs/maps-tokens/01-maps-settings.png)

When you upload, you set:

| Field | What it does |
|---|---|
| **Name** *(+ optional Folder / Tags)* | Label and organize the map in the list. |
| **Grid type** | `Square`, `Hex`, or `None` — controls how tokens snap. |
| **Grid size (px)** | The spacing of one grid cell (20–300 px), matched to your image's tile size. |
| **Width / Height (px)** | The map's pixel dimensions (auto-detected from the image when you upload one). |
| **Image** | PNG / JPG / WebP / GIF, or a looping `MP4` / `WebM` for an animated map. |

The first map you add to a campaign **auto-activates**; after that, use **Activate** to switch.

## The grid overlay

Each map has a **show-grid** toggle (the overlay checkbox in the Maps table). It controls whether the grid lines are *drawn* on top of the map — turn it off for a map whose art already has its own grid baked in.

> **Important:** hiding the overlay only hides the *lines*. Token **snapping still follows the map's grid type** (square/hex/none) either way — so a square-grid map keeps snapping tokens to the grid even with the overlay off. Choose `Grid type: None` if you want truly free token placement.

## The tabletop board

The active map renders on the tabletop at **`/campaign/<id>`**. You pan and zoom the board, and a row of canvas tools sits above it:

- **📏 Ruler** (hotkey `R`) — measure distance in grid squares / feet.
- **🔒 Movement lock** (GM-only) — freeze token dragging so a stray click can't move a token mid-scene.

![The tabletop: the tavern map with its grid and placed tokens, GM Tools drawer at right](/static/docs/maps-tokens/02-tabletop-grid.png)

**Tokens are the top layer.** Tokens draw **above** all map decoration — terrain regions, walls, light hotspots, and weather — so they're never tinted or hidden by the scenery under them. The only thing that still renders **over** a token is the **fog-of-war and darkness veil**: an unexplored or unlit token stays hidden/dimmed, exactly as vision intends. Tokens also have a **minimum on-screen size**, so a lone figure stays legible even when you've zoomed the board out or you're on a large, high-resolution map.

## Placing tokens

Open the **GM Tools** drawer (right side) → **Token Management** → **+ Add Token**. The modal has four ways to get a token onto the map:

| Tab | Places |
|---|---|
| **Library** | A monster/NPC from the campaign's **token templates** (e.g. Adult Red Dragon, Bandit Captain) — the SRD bestiary + your homebrew. |
| **Players** | One or more **player-character** tokens from the roster (multi-select, then *Place Selected*). |
| **Blank Token** | A quick **label + color** marker — great for hazards, objectives, or "mystery" tokens. |
| **Open5e** | Search the wider **Open5e** bestiary and drop the result in. |

![The Add Token modal on the Library tab, listing campaign token templates](/static/docs/maps-tokens/04-add-token.png)

After you pick a token, click the map to place it; it **snaps to the grid**. Placed tokens immediately appear in the token tracker below.

## The token tracker

**Token Management** lists every token on the board, split into **Players** and **GM / NPCs**. Each row shows the token's color ring, label, **owner** (which player controls it), **team** (Hero / Villain — used for target filtering and initiative), and HP for character-backed tokens.

![The token tracker listing player tokens and GM/NPC tokens with owner + team](/static/docs/maps-tokens/03-token-tracker.png)

- **✎ Edit** swaps the owner/team pills for dropdowns so you can reassign who controls a token or flip its team.
- **⟳ Refresh** re-syncs the list.
- Tokens can be hidden from players (a GM-only token the table can't see until you reveal it).

## Tips

- **Lock movement** before a scene starts so players can't accidentally drag tokens; unlock on their turn.
- **Team** matters beyond color — Hero/Villain drives target pickers and the initiative tracker, so set it when you place NPCs.
- **`Grid type: None`** gives free placement; square/hex keep things tidy and make the ruler's distances meaningful.

## Where to go next

- **[Running a session as GM](running-a-session-as-gm.md)** — initiative, the target picker, the GM tools drawer in depth.
- **[Inviting players](inviting-players.md)** — get the players (and their tokens' owners) into the campaign first.
- **[Player onboarding](player-onboarding.md)** — what your players see on the same board.
