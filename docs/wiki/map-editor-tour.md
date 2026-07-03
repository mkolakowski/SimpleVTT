# Map editor tour

**Audience:** GMs building out a battle map's interactive layers.
**Version stamp:** v2.842.0.

The [Maps, grids & tokens](maps-grids-tokens.md) guide covers uploading a map, its grid, and placing tokens on the tabletop. This guide is about the layer *underneath* that — the **map editor**, where you draw the walls, lights, terrain, fog, and annotations that make a map interactive. As of **v2.840.0 ("The Furnished Board")** every demo campaign ships a map pre-furnished with these elements, so the fastest way to learn the editor is to open a demo map and poke at what's already there.

## Opening the editor

The editor lives at **`/campaign/<id>/map/<map_id>/edit`** — reach it from **Campaign settings → World → Maps → Edit** on any map you own. The map fills the screen edge-to-edge, with a floating, frosted-glass **toolbar** over the top. One-finger drag (or left-drag) pans; scroll-wheel or two-finger pinch zooms; **Fit** re-centres the whole map below the toolbar.

Everything you place is stored per-map and broadcast live to the tabletop the instant you **Save** — players see the walls occlude, the lights glow, and the labels appear without a reload.

## The element families

The toolbar groups the editor's tools by what they place. Each family is one persisted layer you can toggle in the **Layers** group.

| Group | Tool | What it places | Demo map to see it on |
|---|---|---|---|
| **Walls** | Wall / Door / Room | Sight-blocking line segments. A **door** is a wall you can toggle open; a **secret** door is hidden from players until opened; a **window** passes sight but reads solid. A **material** (stone / wood / brick / metal / cave) sets the look. | Sundered Tavern (walled common room + a hidden cellar door); Goblin Warrens (cave walls + secret door) |
| **Markers → Lights** | Light | A light source with a **bright** and **dim** radius (in feet) and a **two-colour flicker pair** — the live tabletop's glow wavers torch-like between them. Pick a preset (candle / torch / lantern / lamp / bullseye / daylight; each defines its pair) or set your own colours with the two pickers — non-preset values make the light **custom**. **Double-click a placed light to select it**: the toolbar then mirrors and live-edits its radii + colours (a right-click **🎨 Flicker colours** pop-out edits them in place too). | Every demo map ships flickering lights — e.g. Shadowfell Spire (violet braziers in the dark); Caldera Throne (ember-red fire-glow); Goblin Warrens & Catacombs (torches + lanterns carving pools out of the black) |
| **Markers → Hotspots** | Hotspot | A clickable point with a title, description, and an optional dice expression — players get a 🎲 **Roll** button in the popup. Great for traps and points of interest. | Goblin Warrens (a pit-trap that rolls `1d20`); Caldera Throne (erupting vent) |
| **Markers → Label** | Label | Public on-map text (room names, callouts) with a size and colour. | Sundered Tavern ("The Bar", "Hearth", "Cellar"); Drowned Reef ("Deep channel", "Kelp forest") |
| **Markers → GM Pin** | GM Pin | A **GM-only** note pinned to the map — never sent to players. Use it for ambush triggers and secret staging. | Goblin Warrens ("Ambush"); Shadowfell Spire ("Shadow gate") |
| **Environment → Terrain** | Terrain | A region tagged difficult / water / lava / ice / swamp / rubble — the tabletop shades it so players see the hazard. Drag a rectangle; on a **gridless** map you can instead **click four dots** for a quad. Or turn on **⬡ Free polygon** and click as many vertices as you like on **any** map, closing the shape by clicking the first dot — Resize then drags each vertex independently. | Tide-Wracked Catacombs (standing water); Caldera Throne (lava); Drowned Reef (the kelp forest is a free-form quad) |
| **Environment → Fog** | Fog | Fog of war. Two modes: **static** — paint **revealed** rectangles by hand; or **explore (dynamic)** — tick the toggle and the party's tokens auto-reveal what they can see as they move (base 60 ft sight + their light, occluded by walls). Explored ground stays revealed as **dimmed memory**; never-seen ground stays hidden. **Reset explored** clears the memory. On the tabletop the **GM sees no fog by default** (the whole map) — but **targeting a token** (double-click it) renders the fog from *that* entity's viewpoint, so you can check exactly what a player or monster can see. | All four fogged demo maps (Goblin Warrens, Tide-Wracked Catacombs, Drowned Reef, Shadowfell Spire) ship in **dynamic** mode — walk a token in and watch the veil peel back |
| **Environment → Ambient / Weather** | *(selects)* | Map-wide **ambient light** (bright / dim / dark — governs how much the light sources matter) and a **weather** overlay (rain / snow / fog particles). | The demo fleet spans all three levels: **dim** (Sundered Tavern, Drowned Reef, Caldera Throne) and **dark** (Goblin Warrens, Catacombs, Shadowfell Spire) |

> **Props** are intentionally absent from the toolbar right now — the decorative-stamp tool is parked (v2.835.0), so this tour skips it.

## A worked example: the Sundered Tavern

Open the flagship demo map's editor and you'll find the pattern most interior maps use:

1. **Room** walls trace the tavern's outer shape in the `wood` material.
2. A **door** sits on the south wall (players can open/close it from the tabletop).
3. A **secret** door hides the cellar on the east wall — invisible to players until you reveal it.
4. **Dim** ambient light (dusk), so the three **lights** — a `torch` by the hearth, a `candle` on the bar, and a central `lamp` chandelier — read warmly against the gloom.
5. Three **labels** name the spaces: *The Bar*, *Hearth*, *Cellar*.

Toggle the **Layers** checkboxes to isolate each family, then **Erase** + redraw to feel out the tools. Because it's a demo map, the hourly reseed restores the original set — experiment freely.

## Select to edit

**Double-click** any placed light, wall, or terrain region to **select** it (dashed white
highlight): the matching toolbar control then mirrors its values and edits it live — the light
type/radii/colour pickers for lights, the **material** select for walls, the **terrain type**
select for terrain. Double-click again, press **Esc**, or switch tools to deselect; with nothing
selected the same controls set the defaults for *new* placements, exactly as before.

## Tips

- **Snap** (in the Tools group) locks new wall endpoints to the grid, so rooms come out square.
- Walls only block sight if the map's tokens have a vision range — see the vision/lighting behaviour on a **dark**-ambient map like the Shadowfell Spire.
- Keep **fog** reveals generous over wherever the tokens stand; a too-tight reveal blacks out the live view for players.
- Everything here is **GM-only to edit** but the walls / lights / terrain / labels / hotspots are **player-visible** on the tabletop once saved. GM pins are the one family players never receive.

## See also

- [Maps, grids & tokens](maps-grids-tokens.md) — uploading maps, grids, and placing tokens.
- [Building an encounter](building-an-encounter.md) — encounter library, token templates, spawn points.
- [Demo content — campaigns, PCs & NPCs](demo-content.md) — the six demo campaigns whose maps this tour references.
