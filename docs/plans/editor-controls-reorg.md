# Map-editor control reorganization — review & proposals

**Status:** ⚪ proposed (design only — no code yet)
**Audience:** contributors / the maintainer
**Scope:** the floating toolbar of the map editor (`app/templates/map_editor.html`), not the tabletop.

This doc reviews the *current* organization of the map-editor controls and offers a
few concrete reorganizations to consider. It's deliberately a menu of options with a
recommendation, not a single mandate — pick what fits.

---

## 1. Current layout (as shipped, v2.922.0)

The toolbar is a single horizontal, transparent strip floating over an edge-to-edge
map. Groups collapse individually (click the group label) and by **zone** (click the
`Draw` / `Map` divider). Left → right:

**Actions zone (no divider label)**
- **File** *(stacked)* — Undo · Redo · **Save** · Delete all · **Export / Import** · Tags input + Save tags
- **Tools** *(stacked)* — Erase · Snap · Measure · Select (box) · Select & move

**`Draw` zone**
- **Walls** — Wall · Door · FreeForm · `material` select (Stone…Cave, 🪟 Window, 👻 Invisible) · `opacity` slider
- **Markers** — Hotspots · Lights · `light type` + Bright + Dim · flicker colour ×2 · Label · Pin
- **Environment** — `ambient` select · Fog · Terrain · FreeForm terrain · *(fog on / dynamic / reset — hidden until Fog armed)* · `terrain` type · `weather` select
- **Lair zones** — Lair Zone · FreeForm · colour + `Lair Actions` select · action description
- **Tokens** — 🔵 sample token · 🟠 sample token

**`Map` zone**
- **Grid** — `grid type` · show + px · offset x/y · **tokens × dial** · **S/M/L/XL token presets**
- **Layers** — All/None + 9 reorderable visibility rows
- **View** — Fit · zoom −/+ · resolution readout

---

## 2. What works well (keep it)

- **Tool button sits next to its properties.** Each draw group keeps its mode button
  adjacent to the knobs that configure it (material by Wall, light type by Lights).
  That locality is good — don't scatter it.
- **Zone + group collapsing** already lets a GM shrink the strip to just what they need.
- **Layers** (visibility + z-order in one column) and **View** are coherent and self-contained.
- **Dual-purpose controls** (a dropdown edits *either* the new-object default *or* the
  double-click-selected object) are powerful and space-efficient.

## 3. Pain points (the "why")

1. **Lighting is split across two groups.** Ambient light lives in **Environment**;
   placed **Lights** (with three rows of config: type, Bright/Dim radii, two flicker
   colours) live in **Markers**. A GM "setting up lighting" has to look in two places,
   and *Markers* is a poor label for light sources.
2. **"Markers" is overloaded and mis-named.** It holds Hotspots, Lights, Labels, and
   GM Pins — four unrelated things, with Lights alone taking three rows.
3. **Token controls are scattered across three groups.** The sample-token drops are in
   **Tokens** (Draw zone); the **token-scale dial + S/M/L/XL presets** are in **Grid**
   (Map zone); token visibility is a **Layers** row. "tokens ×" living under *Grid* is
   the most surprising placement in the editor.
4. **Environment is a grab-bag.** Ambient light (lighting) + Fog (vision) + Terrain
   (a *draw* concern like walls) + Weather (presentation) — four distinct concerns fused
   into one group, plus conditionally-shown fog sub-controls that shift the layout.
5. **The dual-purpose controls are invisible.** Nothing tells the GM whether a dropdown
   is currently editing "new walls" or "the wall I just selected." The behaviour is great;
   its discoverability is nil.
6. **"Select" vs "Select & move" read as the same thing.** Box-select and
   double-click-select-into-move are two different modes with near-identical names.
7. **"⬡ FreeForm" is duplicated three times** (Walls, Terrain, Lair) — contextual, but
   visually repetitive.

---

## 4. Proposals

Four independent themes. **A** is the headline; **B** is the highest-leverage UX fix;
**C** and **D** are smaller polish. They compose — you can take A+B and skip C.

### Theme A — Regroup the `Draw` zone by *concern* (recommended)

Re-slot the existing controls (no behaviour change, pure regrouping) into coherent groups:

| New group | Contains | Moved from |
|---|---|---|
| **Walls & Doors** | Wall · Door · FreeForm · material · opacity | *(unchanged — was Walls)* |
| **Terrain** | Terrain · FreeForm · terrain type | split out of *Environment* |
| **Lighting** | ambient select · Lights · light type · Bright/Dim · flicker ×2 | **merges** Environment's ambient + Markers' Lights |
| **Fog & Vision** | Fog · fog on / dynamic / reset | split out of *Environment* |
| **Annotations** | Hotspots · Labels · GM Pins | *Markers* minus Lights, renamed |
| **Weather** *(or fold into Lighting/Env)* | weather select | split out of *Environment* |
| **Lair zones** | *(unchanged)* | — |
| **Tokens** | 🔵/🟠 sample tokens · **token-scale dial + S/M/L/XL presets** | scale **moved out of Grid** |

Net effect: every group answers one question ("how do I light this room?" → **Lighting**;
"how big are tokens here?" → **Tokens**). **Grid** shrinks to grid-only. Slightly more
groups, but each is smaller and collapsible, and the zone-collapse already tames width.

*Cost:* mechanical — move `<div class="me-group">` blocks + their JS wiring reads the same
element IDs, so most handlers are untouched. Watch the conditionally-shown fog controls and
the shared `styleSel`/`terrainTypeSel` "edit the selection" hooks.

### Theme B — A "Selected object" inspector (highest-leverage UX)

Introduce a small **contextual inspector** that appears (in the toolbar or as a floating
panel near the selection) **only when an object is selected**, showing *just that object's*
editable properties: material · opacity · type · colour · size · flip · secret · delete.
The tool groups then advertise only **new-object defaults**.

This resolves pain point #5 (the invisible dual role) directly: "these knobs make new
things" vs "this panel edits the thing you clicked" become two visibly different surfaces.
It also shortens the always-on toolbar, since per-object knobs move into the on-demand
inspector.

*Cost:* larger — a new panel + selection-change plumbing. But it's the change most likely
to reduce day-to-day confusion. Could ship incrementally (walls first).

### Theme C — One shared "shape mode" control

Replace the three per-group **⬡ FreeForm** toggles with a single global
`shape: line · rect · freeform` segmented control that applies to whichever draw tool is
active (walls / terrain / lair). Removes duplication (#7) and teaches the concept once.

*Cost:* small-medium — unify three independent `*PolyMode` flags behind one state var; each
draw tool already branches on its own flag, so this is mostly consolidation.

### Theme D — Label defaults vs. selection (cheap polish)

Without building the full inspector (B), just **relabel** the dual-purpose captions based
on context: `material` → "New wall" normally, "Selected wall" when a wall is selected; same
for light/terrain/lair. A one-line status hint ("Editing selected door") does most of the
work. Rename **Select & move** → "Grab" or "Move" to disambiguate from box **Select** (#6).

*Cost:* tiny — caption text + a class toggle on selection.

---

## 5. Visual mockups (before → after)

Wireframes (not pixel-exact) of the floating toolbar strip. Each `[ … ]` is a
collapsible group; `║ Draw ║` / `║ Map ║` are the zone dividers.

### 5.1 Today (v2.922.0)

```
 Actions                       ║Draw║                                                                              ║Map║
┌File────┐┌Tools────┐ ┌Walls──────┐┌Markers──────────┐┌Environment────────┐┌Lair────┐┌Tokens┐ ┌Grid──────────┐┌Layers─┐┌View─┐
│↶  ↷    ││🗑 Erase  │ │🧱 Wall     ││📍Hotspot 💡Light ││ ambient ▾         ││🎯 Lair  ││🔵 🟠 │ │grid type ▾   ││👁 All ││ Fit │
│💾 Save ││🧲 Snap   │ │🚪 Door     ││light type ▾      ││🌫Fog   ⛰Terrain  ││⬡ Free  ││      │ │show☑ px[70]  ││🧱Walls││🔍-+ │
│🗑 Del  ││📏 Measure│ │⬡ FreeForm  ││ B[  ] D[  ]      ││⬡ FreeForm terrain ││🎨act ▾ ││      │ │x[0]  y[0]    ││⛰Terr ││     │
│⬇ ⬆ i/o ││⬚ Select  │ │material ▾  ││🎨 🎨 flicker     ││terrain ▾ weather ▾││(desc…) ││      │ │tokens×[1.0]  ││💡… ✕8 ││     │
│Tags…   ││🖱 Sel&mv │ │opacity ▭▬▬ ││🔤Label  📌Pin    ││                   ││        ││      │ │[S][M][L][XL] ││       ││     │
└────────┘└─────────┘ └───────────┘└─────────────────┘└───────────────────┘└────────┘└──────┘ └──────────────┘└───────┘└─────┘
                        ▲ lighting is here (ambient) …and here (Lights)      token size is stranded under “Grid” ▲
```

Two things to notice: **lighting** is split between *Environment* (ambient) and
*Markers* (the Lights tool + its 3 config rows), and the **token-size** dial +
presets sit under **Grid**, unrelated to grid setup.

### 5.2 Theme A — regrouped by concern

```
 Actions               ║Draw║                                                                          ║Map║
┌File┐┌Tools┐ ┌Walls &──┐┌Terrain─┐┌Lighting────┐┌Fog &───┐┌Annotations┐┌Lair┐┌Tokens──────┐ ┌Grid────┐┌Layers┐┌View┐
│ …  ││  …  │ │  Doors  ││⛰ Terrain││ ambient ▾  ││ Vision ││📍 Hotspots ││ …  ││🔵 🟠 Token  │ │grid ▾  ││ …    ││ …  │
│    ││     │ │🧱 Wall   ││⬡ Free  ││💡 Lights   ││🌫 Fog  ││🔤 Label    ││    ││tokens×[1.0]│ │show☑   ││      ││    │
│    ││     │ │🚪 Door   ││terrain▾││light type▾ ││ on ☑   ││📌 Pin      ││    ││[S][M][L][X]│ │px[70]  ││      ││    │
│    ││     │ │⬡ Free   ││        ││ B[ ] D[ ]  ││explore☑││            ││    ││            │ │x[0]y[0]││      ││    │
│    ││     │ │material▾ ││        ││🎨 🎨       ││↺ reset ││            ││    ││            │ │        ││      ││    │
│    ││     │ │opacity ▭ ││        ││            ││        ││            ││    ││            │ │        ││      ││    │
└────┘└─────┘ └─────────┘└────────┘└────────────┘└────────┘└───────────┘└────┘└────────────┘ └────────┘└──────┘└────┘
                                    ▲ ambient + Lights, together   ▲ fog split out   token size lives with Tokens ▲
```

Every group now answers one question. `Grid` is grid-only; `Lighting` owns both
ambient level and placed lights; `Tokens` owns the size dial; `Fog & Vision` and
`Terrain` are their own concerns instead of a shared *Environment* bin.
(`Weather` folds into `Lighting`/atmosphere or becomes its own tiny group.)

### 5.3 Theme B — a "Selected object" inspector

The tool group advertises only **new-object defaults**; the moment you
double-click an object, a compact inspector floats next to it with *that
object's* live properties:

```
   Nothing selected                     A wall selected
 ┌ Walls & Doors ─────┐          ┌ Selected · Wall ───────────┐
 │ 🧱 Wall  🚪 Door   │          │ material  [ Stone       ▾] │
 │ ⬡ FreeForm         │          │ opacity   ▭▭▭▭▭▭▭──  70 %  │
 │ material  [Stone ▾]│  ◄─────► │ type      (Wall)Door Window│
 │ opacity   ▭▬▬▬▬▬▬  │          │ ↻ flip    🔒 secret        │
 └────────────────────┘          │ 🗑 Delete                  │
   “make NEW walls”               └────────────────────────────┘
                                   floats by the selection · Esc closes
```

This makes the current dual role (a knob edits *either* the default *or* the
selection) two visibly distinct surfaces.

### 5.4 Theme D — label the context (cheap version of B)

Without the full inspector, just relabel the shared caption + add a status hint:

```
  nothing selected          wall selected
 ┌──────────────┐          ┌──────────────────┐
 │ New wall     │    →     │ Selected wall     │
 │ material  ▾  │          │ material  ▾       │
 │ opacity ▭▬▬  │          │ opacity ▭▬▬       │
 └──────────────┘          └──────────────────┘
   status: “Editing selected door — Esc to deselect”
```

And rename **🖱 Select & move** → **🖱 Grab** so it stops colliding with the
box-**⬚ Select** tool.

## 6. Suggested phasing

1. **Phase 1 (mechanical, low-risk):** Theme A regrouping + move token-scale into Tokens
   (Theme A's token row). Pure DOM reshuffle; existing handlers keep their element IDs.
   Ship behind the existing harness (`test_map_editor_*`) which asserts by element ID, so a
   regroup that preserves IDs stays green.
2. **Phase 2 (cheap polish):** Theme D labels + the Select/Grab rename.
3. **Phase 3 (opt-in, higher effort):** Theme B inspector, walls first, then terrain/lights.
4. **Phase 4 (optional):** Theme C unified shape mode.

## 7. Risks & test impact

- The `harness_ui` editor tests locate controls by **element ID** (`#me-wall-btn`,
  `#me-token-scale`, …), not by group. **Theme A keeps every ID**, so those tests should
  pass unchanged — but the group-collapse tests (`test_editor_group_collapse.py`,
  `ZONE_MEMBERS`) reference group `aria-label`s and **must be updated** when groups are
  renamed/added.
- Moving the token-scale dial out of **Grid** means updating any test/coverage note that
  says it lives there, plus the `ZONE_MEMBERS.Map`/`Draw` membership if Tokens changes zones.
- Theme B (inspector) is the only proposal that adds real new UI/JS and would need its own
  harness coverage (selection → inspector fields → edit round-trips).
- None of these touch the server or schema — the wall/terrain/light/token payloads are
  unchanged; this is toolbar layout only.

---

## 8. Recommendation

Ship **Theme A (regroup by concern)** + **Theme D (labels/rename)** first — together they
remove the two worst papercuts (scattered lighting/token controls; the invisible
default-vs-selection role) for modest, low-risk effort. Treat **Theme B (inspector)** as the
next substantial investment if the dual-role confusion persists, and **Theme C** as
optional cleanup.
