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

Rendered HTML mockups of the floating toolbar strip (indicative, not
pixel-exact). Each rounded panel is a collapsible **group**; the vertical
labels are the **zone** dividers.

<div style="font-size:12px;color:#8f98bd;margin:2px 0 12px;">Legend: <span style="border-left:3px solid #e0674f;padding-left:6px;margin-right:16px;color:#e0a99c;">red&nbsp;=&nbsp;a control in the wrong / duplicated place today</span><span style="border-left:3px solid #57b26a;padding-left:6px;color:#9fd3ab;">green&nbsp;=&nbsp;where it moves to</span></div>

### 5.1 Today (v2.922.0)

<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:flex-start;margin-left:calc(50% - 50vw);margin-right:calc(50% - 50vw);box-sizing:border-box;background:#12141d;border:1px solid #2a2e40;border-radius:10px;padding:12px 28px;font-family:system-ui,sans-serif;">
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">File</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">↶ ↷ · 💾 Save</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">⬇ Export · ⬆ Import</span></div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Tools</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">🗑 · 🧲 · 📏</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">⬚ Select · 🖱 Sel&amp;move</span></div>
<div style="writing-mode:vertical-rl;transform:rotate(180deg);font-size:10px;font-weight:700;color:#7b84ab;align-self:stretch;display:flex;align-items:center;padding:0 1px;">Draw</div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Walls</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">🧱 Wall · 🚪 Door</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">material ▾ · opacity ▭</span></div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Markers</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">📍 Hotspots</span><span style="display:block;font-size:11.5px;color:#f2d7cf;background:#33262330;background:#3a2a26;border:1px solid #5a3b34;border-left:3px solid #e0674f;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">💡 Lights · light type ▾ · B D</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">🔤 Label · 📌 Pin</span></div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Environment</div><span style="display:block;font-size:11.5px;color:#f2d7cf;background:#3a2a26;border:1px solid #5a3b34;border-left:3px solid #e0674f;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">ambient ▾</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">🌫 Fog · ⛰ Terrain</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">terrain ▾ · weather ▾</span></div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Lair</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">🎯 Lair Zone</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">action ▾</span></div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Tokens</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">🔵 · 🟠</span></div>
<div style="writing-mode:vertical-rl;transform:rotate(180deg);font-size:10px;font-weight:700;color:#7b84ab;align-self:stretch;display:flex;align-items:center;padding:0 1px;">Map</div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Grid</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">grid ▾ · show ☑ · px</span><span style="display:block;font-size:11.5px;color:#f2d7cf;background:#3a2a26;border:1px solid #5a3b34;border-left:3px solid #e0674f;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">tokens × [1.0] · S M L XL</span></div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Layers · View</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">👁 layers ✕8</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">Fit · 🔍 −/+</span></div>
</div>

Two things to notice (red above): **lighting** is split between *Environment*
(ambient) and *Markers* (the Lights tool + its config rows), and the
**token-size** dial + presets sit under **Grid**, unrelated to grid setup.

### 5.2 Theme A — regrouped by concern

<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:flex-start;margin-left:calc(50% - 50vw);margin-right:calc(50% - 50vw);box-sizing:border-box;background:#12141d;border:1px solid #2a2e40;border-radius:10px;padding:12px 28px;font-family:system-ui,sans-serif;">
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Actions</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">File · Tools</span></div>
<div style="writing-mode:vertical-rl;transform:rotate(180deg);font-size:10px;font-weight:700;color:#7b84ab;align-self:stretch;display:flex;align-items:center;padding:0 1px;">Draw</div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Walls &amp; Doors</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">🧱 Wall · 🚪 Door</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">material ▾ · opacity ▭</span></div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Terrain</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">⛰ Terrain · ⬡</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">terrain ▾</span></div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Lighting</div><span style="display:block;font-size:11.5px;color:#d7f2dc;background:#26361f;background:#243a29;border:1px solid #34573b;border-left:3px solid #57b26a;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">ambient ▾</span><span style="display:block;font-size:11.5px;color:#d7f2dc;background:#243a29;border:1px solid #34573b;border-left:3px solid #57b26a;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">💡 Lights · type ▾ · B D · 🎨</span></div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Fog &amp; Vision</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">🌫 Fog · on ☑</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">explore ☑ · ↺ reset</span></div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Annotations</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">📍 Hotspots</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">🔤 Label · 📌 Pin</span></div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Lair</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">🎯 Lair Zone</span></div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Tokens</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">🔵 · 🟠 Token</span><span style="display:block;font-size:11.5px;color:#d7f2dc;background:#243a29;border:1px solid #34573b;border-left:3px solid #57b26a;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">tokens × [1.0] · S M L XL</span></div>
<div style="writing-mode:vertical-rl;transform:rotate(180deg);font-size:10px;font-weight:700;color:#7b84ab;align-self:stretch;display:flex;align-items:center;padding:0 1px;">Map</div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Grid</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">grid ▾ · show ☑</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">px · x/y offset</span></div>
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 7px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;">Layers · View</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">👁 layers ✕8</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:3px 7px;margin:3px 0;white-space:nowrap;">Fit · 🔍 −/+</span></div>
</div>

Every group now answers one question: **Lighting** owns ambient level *and*
placed lights (green — merged from two groups); **Tokens** owns the size dial
(green — moved out of Grid); **Grid** is grid-only; **Fog & Vision** and
**Terrain** split out of the old *Environment* bin. (Weather folds into an
atmosphere group or its own tiny one.)

### 5.3 Theme B — a "Selected object" inspector

The tool group advertises only **new-object defaults**; the moment you
double-click an object, a compact inspector floats next to it with *that
object's* live properties.

<div style="display:flex;flex-wrap:wrap;gap:18px;align-items:flex-start;margin-left:calc(50% - 50vw);margin-right:calc(50% - 50vw);box-sizing:border-box;background:#12141d;border:1px solid #2a2e40;border-radius:10px;padding:16px 28px;font-family:system-ui,sans-serif;">
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:8px 9px;min-width:150px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:6px;">Walls &amp; Doors <span style="color:#6a7398;">· defaults</span></div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:4px 8px;margin:4px 0;white-space:nowrap;">🧱 Wall · 🚪 Door · ⬡</span><span style="display:block;font-size:11.5px;color:#c9cee6;background:#252a39;border:1px solid #3a4058;border-radius:5px;padding:4px 8px;margin:4px 0;white-space:nowrap;">material [ Stone ▾ ]</span><span style="display:block;font-size:11.5px;color:#c9cee6;background:#252a39;border:1px solid #3a4058;border-radius:5px;padding:4px 8px;margin:4px 0;white-space:nowrap;">opacity ▭▬▬▬▬▬▬</span><div style="font-size:11px;color:#6a7398;margin-top:4px;">makes NEW walls</div></div>
<div style="align-self:center;color:#57b26a;font-size:20px;font-weight:700;">⇄</div>
<div style="background:#1b2430;border:1px solid #57b26a;box-shadow:0 4px 18px rgba(0,0,0,.4);border-radius:8px;padding:8px 9px;min-width:190px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#9fd3ab;font-weight:700;margin-bottom:6px;">Selected · Wall</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#243040;border:1px solid #3a4a5e;border-radius:5px;padding:4px 8px;margin:4px 0;white-space:nowrap;">material [ Stone ▾ ]</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#243040;border:1px solid #3a4a5e;border-radius:5px;padding:4px 8px;margin:4px 0;white-space:nowrap;">opacity ▭▬▬▬▬▬▬ 70%</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#243040;border:1px solid #3a4a5e;border-radius:5px;padding:4px 8px;margin:4px 0;white-space:nowrap;">type ( Wall ) Door · Window</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#243040;border:1px solid #3a4a5e;border-radius:5px;padding:4px 8px;margin:4px 0;white-space:nowrap;">↻ flip · 🔒 secret · 🗑 delete</span><div style="font-size:11px;color:#6a7398;margin-top:4px;">floats by the selection · Esc closes</div></div>
</div>

This makes the current dual role (a knob edits *either* the default *or* the
selection) two visibly distinct surfaces.

### 5.4 Theme D — label the context (cheap version of B)

Without the full inspector, just relabel the shared caption + add a status hint.

<div style="display:flex;flex-wrap:wrap;gap:16px;align-items:center;margin-left:calc(50% - 50vw);margin-right:calc(50% - 50vw);box-sizing:border-box;background:#12141d;border:1px solid #2a2e40;border-radius:10px;padding:16px 28px;font-family:system-ui,sans-serif;">
<div style="background:#20232f;border:1px solid #333850;border-radius:8px;padding:8px 9px;min-width:120px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:6px;">New wall</div><span style="display:block;font-size:11.5px;color:#c9cee6;background:#252a39;border:1px solid #3a4058;border-radius:5px;padding:4px 8px;margin:4px 0;">material ▾</span><span style="display:block;font-size:11.5px;color:#c9cee6;background:#252a39;border:1px solid #3a4058;border-radius:5px;padding:4px 8px;margin:4px 0;">opacity ▭▬▬</span></div>
<div style="color:#57b26a;font-size:20px;font-weight:700;">→</div>
<div style="background:#1b2430;border:1px solid #57b26a;border-radius:8px;padding:8px 9px;min-width:140px;"><div style="font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#9fd3ab;font-weight:700;margin-bottom:6px;">Selected wall</div><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#243040;border:1px solid #3a4a5e;border-radius:5px;padding:4px 8px;margin:4px 0;">material ▾</span><span style="display:block;font-size:11.5px;color:#e7e9f3;background:#243040;border:1px solid #3a4a5e;border-radius:5px;padding:4px 8px;margin:4px 0;">opacity ▭▬▬ 70%</span></div>
</div>

<div style="font-size:12px;color:#9fd3ab;background:#1b2430;border:1px solid #34573b;border-radius:6px;padding:6px 10px;margin:8px 0;font-family:system-ui,sans-serif;">status: Editing <b>selected door</b> — Esc to deselect</div>

And rename **🖱 Select &amp; move** → **🖱 Grab** so it stops colliding with the
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
