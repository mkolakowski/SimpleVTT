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

## 5. Interactive mockups (before → after)

**These are live** — click them. They're toys (not the real editor), just enough to feel
each proposal. Each rounded panel is a collapsible **group**; vertical labels are **zone**
dividers.

<style>
.mde-wrap{margin-left:calc(50% - 50vw);margin-right:calc(50% - 50vw);box-sizing:border-box;background:#12141d;border:1px solid #2a2e40;border-radius:10px;padding:14px 28px;font-family:system-ui,sans-serif;}
.mde-row{display:flex;flex-wrap:wrap;gap:8px;align-items:flex-start;}
.mde-grp{background:#20232f;border:1px solid #333850;border-radius:8px;padding:6px 8px;}
.mde-t{font-size:10px;letter-spacing:.4px;text-transform:uppercase;color:#8f98bd;font-weight:700;margin-bottom:5px;}
.mde-t.clk{cursor:pointer;user-select:none;}
.mde-t.clk:hover{color:#c7cef0;}
.mde-chip{display:block;font-size:12px;color:#e7e9f3;background:#2b3040;border:1px solid #3a4058;border-radius:5px;padding:4px 8px;margin:3px 0;white-space:nowrap;}
.mde-chip.clk{cursor:pointer;}
.mde-chip.clk:hover{border-color:#5b6690;}
.mde-chip.armed{outline:2px solid #ffd24a;border-color:#ffd24a;}
.mde-chip.red{color:#f2d7cf;background:#3a2a26;border-color:#5a3b34;border-left:3px solid #e0674f;}
.mde-chip.green{color:#d7f2dc;background:#243a29;border-color:#34573b;border-left:3px solid #57b26a;}
.mde-zone{writing-mode:vertical-rl;transform:rotate(180deg);font-size:10px;font-weight:700;color:#7b84ab;align-self:stretch;display:flex;align-items:center;padding:0 1px;}
.mde-map{position:relative;height:200px;margin-top:12px;border:2px dashed #3a4058;border-radius:8px;background:repeating-linear-gradient(0deg,#171a26,#171a26 33px,#1b1e2c 33px,#1b1e2c 34px),repeating-linear-gradient(90deg,#171a26,#171a26 33px,#1b1e2c 33px,#1b1e2c 34px);cursor:crosshair;overflow:hidden;}
.mde-bar{display:flex;align-items:center;gap:12px;margin-top:10px;}
.mde-status{flex:1 1 auto;font-size:13px;color:#9fd3ab;background:#1b2430;border:1px solid #34573b;border-radius:6px;padding:7px 11px;}
.mde-btn{font-size:13px;color:#f2d7cf;background:#3a2a26;border:1px solid #5a3b34;border-radius:6px;padding:7px 14px;cursor:pointer;}
.mde-insp{background:#1b2430;border:1px solid #57b26a;border-radius:8px;padding:8px 9px;min-width:200px;}
.mde-insp .mde-chip{background:#243040;border-color:#3a4a5e;color:#e7e9f3;}
.mde-collapsed .mde-body{display:none;}
.mde-hint{font-size:12px;color:#9fd3ab;background:#1b2430;border:1px solid #34573b;border-radius:6px;padding:6px 10px;margin-top:8px;}
.mde-ctl{font-size:12px;color:#e7e9f3;background:#243040;border:1px solid #3a4a5e;border-radius:5px;padding:3px 6px;}
</style>

### 5.1 Today (v2.922.0) — click a group title to collapse; click a red control to see the problem

<div class="mde-wrap" id="mde-today">
<div class="mde-row">
<div class="mde-grp"><div class="mde-t clk">▾ File</div><div class="mde-body"><span class="mde-chip">↶ ↷ · 💾 Save</span><span class="mde-chip">⬇ Export · ⬆ Import</span></div></div>
<div class="mde-grp"><div class="mde-t clk">▾ Tools</div><div class="mde-body"><span class="mde-chip">🗑 · 🧲 · 📏</span><span class="mde-chip">⬚ Select · 🖱 Sel&amp;move</span></div></div>
<div class="mde-zone">Draw</div>
<div class="mde-grp"><div class="mde-t clk">▾ Walls</div><div class="mde-body"><span class="mde-chip">🧱 Wall · 🚪 Door</span><span class="mde-chip">material ▾ · opacity ▭</span></div></div>
<div class="mde-grp"><div class="mde-t clk">▾ Markers</div><div class="mde-body"><span class="mde-chip">📍 Hotspots</span><span class="mde-chip red clk" data-note="Problem: lighting lives HERE (the Lights tool + its 3 config rows) …">💡 Lights · light type ▾ · B D</span><span class="mde-chip">🔤 Label · 📌 Pin</span></div></div>
<div class="mde-grp"><div class="mde-t clk">▾ Environment</div><div class="mde-body"><span class="mde-chip red clk" data-note="… and ALSO here (ambient) — that's the split. A GM lighting a room looks in two groups.">ambient ▾</span><span class="mde-chip">🌫 Fog · ⛰ Terrain</span><span class="mde-chip">terrain ▾ · weather ▾</span></div></div>
<div class="mde-grp"><div class="mde-t clk">▾ Lair</div><div class="mde-body"><span class="mde-chip">🎯 Lair Zone</span><span class="mde-chip">action ▾</span></div></div>
<div class="mde-grp"><div class="mde-t clk">▾ Tokens</div><div class="mde-body"><span class="mde-chip">🔵 · 🟠</span></div></div>
<div class="mde-zone">Map</div>
<div class="mde-grp"><div class="mde-t clk">▾ Grid</div><div class="mde-body"><span class="mde-chip">grid ▾ · show ☑ · px</span><span class="mde-chip red clk" data-note="Problem: the token-SIZE dial is stranded under Grid — nothing to do with grid setup.">tokens × [1.0] · S M L XL</span></div></div>
<div class="mde-grp"><div class="mde-t clk">▾ Layers · View</div><div class="mde-body"><span class="mde-chip">👁 layers ✕8</span><span class="mde-chip">Fit · 🔍 −/+</span></div></div>
</div>
<div class="mde-bar"><div class="mde-status" data-status>Click a group title to collapse it. Click a red control to see why it's mis-placed today.</div></div>
</div>

### 5.2 Theme A — regrouped by concern (a working toy: arm a tool → click the map → click a piece to inspect)

<div class="mde-wrap" id="mde-a">
<div class="mde-row">
<div class="mde-grp"><div class="mde-t clk">▾ Actions</div><div class="mde-body"><span class="mde-chip">File · Tools</span></div></div>
<div class="mde-zone">Draw</div>
<div class="mde-grp"><div class="mde-t clk">▾ Walls &amp; Doors</div><div class="mde-body"><span class="mde-chip clk" data-tool="wall">🧱 Wall</span><span class="mde-chip clk" data-tool="door">🚪 Door</span><span class="mde-chip">material ▾ · opacity ▭</span></div></div>
<div class="mde-grp"><div class="mde-t clk">▾ Terrain</div><div class="mde-body"><span class="mde-chip clk" data-tool="terrain">⛰ Terrain</span><span class="mde-chip">terrain ▾</span></div></div>
<div class="mde-grp"><div class="mde-t clk">▾ Lighting</div><div class="mde-body"><span class="mde-chip green">ambient ▾</span><span class="mde-chip green clk" data-tool="light">💡 Lights · type ▾</span></div></div>
<div class="mde-grp"><div class="mde-t clk">▾ Fog &amp; Vision</div><div class="mde-body"><span class="mde-chip clk" data-tool="fog">🌫 Fog</span><span class="mde-chip">explore ☑ · ↺</span></div></div>
<div class="mde-grp"><div class="mde-t clk">▾ Annotations</div><div class="mde-body"><span class="mde-chip clk" data-tool="hotspot">📍 Hotspot</span><span class="mde-chip">🔤 Label · 📌 Pin</span></div></div>
<div class="mde-grp"><div class="mde-t clk">▾ Lair</div><div class="mde-body"><span class="mde-chip clk" data-tool="lair">🎯 Lair Zone</span></div></div>
<div class="mde-grp"><div class="mde-t clk">▾ Tokens</div><div class="mde-body"><span class="mde-chip clk" data-tool="token">🔵 Token</span><span class="mde-chip green">tokens × [1.0] · S M L XL</span></div></div>
<div class="mde-zone">Map</div>
<div class="mde-grp"><div class="mde-t clk">▾ Grid</div><div class="mde-body"><span class="mde-chip">grid ▾ · show ☑</span><span class="mde-chip">px · x/y</span></div></div>
</div>
<div class="mde-map" data-map></div>
<div class="mde-bar"><div class="mde-status" data-status>Green = moved/merged here. Click a tool above, then click the map to place it; click a placed piece to select it.</div><button class="mde-btn" type="button" data-reset>↺ Reset</button></div>
<div class="mde-insp" data-insp style="display:none;margin-top:10px;max-width:300px;"><div class="mde-t" data-insp-title>Selected · Wall</div><span class="mde-chip">material [ Stone ▾ ]</span><span class="mde-chip">opacity ▭▬▬▬▬▬▬ 70%</span><span class="mde-chip">↻ flip · 🔒 secret · 🗑 delete</span></div>
</div>

### 5.3 Theme B — the "Selected object" inspector (click **Select a wall** to summon it; the controls are live)

<div class="mde-wrap" id="mde-b">
<div class="mde-row" style="align-items:center;">
<div class="mde-grp" style="min-width:150px;"><div class="mde-t">Walls &amp; Doors · defaults</div><span class="mde-chip">🧱 Wall · 🚪 Door · ⬡</span><span class="mde-chip" style="color:#c9cee6;background:#252a39;">material [ Stone ▾ ]</span><span class="mde-chip" style="color:#c9cee6;background:#252a39;">opacity ▭▬▬▬▬▬▬</span><div style="font-size:11px;color:#6a7398;margin-top:4px;">makes NEW walls</div></div>
<button class="mde-btn" type="button" data-b-toggle style="background:#243040;border-color:#3a4a5e;color:#e7e9f3;">Select a wall ▸</button>
<div class="mde-insp" data-b-insp style="display:none;"><div class="mde-t" style="color:#9fd3ab;">Selected · Wall</div><div style="margin:4px 0;"><label style="font-size:11px;color:#9aa3c0;">material </label><select class="mde-ctl" data-b-mat><option>Stone</option><option>Wood</option><option>Brick</option><option>Metal</option><option>Cave</option><option>🪟 Window</option></select></div><div style="margin:4px 0;"><label style="font-size:11px;color:#9aa3c0;">opacity </label><input type="range" min="0" max="100" value="70" data-b-op style="vertical-align:middle;"></div><span class="mde-chip">↻ flip · 🔒 secret · 🗑 delete</span><div class="mde-hint" data-b-prev>preview: Stone wall @ 70% opacity</div></div>
</div>
<div style="font-size:12px;color:#8f98bd;margin-top:6px;">The tool group shows only <em>new-wall defaults</em>; the green inspector edits <em>the selected wall</em> — two visibly distinct surfaces (change the material / opacity above and watch the preview).</div>
</div>

### 5.4 Theme D — label the context + the Select→Grab rename (toggle them)

<div class="mde-wrap" id="mde-d">
<div class="mde-row" style="align-items:center;">
<div class="mde-grp" style="min-width:150px;" data-d-card><div class="mde-t" data-d-title>New wall</div><span class="mde-chip" data-d-c1 style="color:#c9cee6;background:#252a39;">material ▾</span><span class="mde-chip" data-d-c2 style="color:#c9cee6;background:#252a39;">opacity ▭▬▬</span></div>
<button class="mde-btn" type="button" data-d-sel style="background:#243040;border-color:#3a4a5e;color:#e7e9f3;">Select the wall ▸</button>
<div class="mde-grp"><div class="mde-t">Tools</div><span class="mde-chip clk" data-d-chip data-d-name="Select &amp; move">🖱 Select &amp; move</span><button class="mde-btn" type="button" data-d-rename style="margin-top:4px;font-size:11px;padding:4px 8px;">rename ↔</button></div>
</div>
<div class="mde-hint" data-d-hint style="display:none;">status: Editing <b>selected wall</b> — Esc to deselect</div>
</div>

<script>
(function(){
  // Generic collapse: any ".mde-t.clk" toggles its group + flips the arrow.
  document.querySelectorAll('.mde-wrap .mde-t.clk').forEach(function(t){
    t.addEventListener('click', function(e){
      e.stopPropagation();
      var grp = t.closest('.mde-grp'); if(!grp) return;
      var open = !grp.classList.toggle('mde-collapsed');
      t.textContent = (open ? '▾ ' : '▸ ') + t.textContent.replace(/^[▾▸]\s*/,'');
    });
  });
  // 5.1 — red controls explain the problem in the status line.
  (function(){
    var root = document.getElementById('mde-today'); if(!root) return;
    var st = root.querySelector('[data-status]');
    root.querySelectorAll('.mde-chip.red').forEach(function(c){
      c.addEventListener('click', function(e){ e.stopPropagation(); st.textContent = c.getAttribute('data-note'); });
    });
  })();
  // 5.2 — arm a tool, place on the map, click a piece to inspect.
  (function(){
    var root = document.getElementById('mde-a'); if(!root) return;
    var map = root.querySelector('[data-map]');
    var st = root.querySelector('[data-status]');
    var insp = root.querySelector('[data-insp]');
    var glyph = { wall:'🧱', door:'🚪', terrain:'⛰', light:'💡', fog:'🌫', hotspot:'📍', lair:'🎯', token:'🔵' };
    var tool = null;
    function clearArm(){ root.querySelectorAll('[data-tool]').forEach(function(c){ c.classList.remove('armed'); }); }
    root.querySelectorAll('[data-tool]').forEach(function(chip){
      chip.addEventListener('click', function(e){
        e.stopPropagation();
        if(tool === chip.dataset.tool){ tool=null; clearArm(); st.textContent='Tool cleared — pick a tool, or click a placed piece.'; return; }
        tool = chip.dataset.tool; clearArm(); chip.classList.add('armed');
        st.textContent = chip.textContent.trim()+' armed — click the map to place it.';
      });
    });
    map.addEventListener('click', function(e){
      insp.style.display='none';
      if(!tool){ st.textContent='No tool armed — pick one above first.'; return; }
      var r = map.getBoundingClientRect();
      var piece = document.createElement('span');
      var kind = tool;
      piece.textContent = glyph[kind] || '▪';
      piece.setAttribute('data-piece','1');
      piece.style.cssText='position:absolute;transform:translate(-50%,-50%);font-size:22px;cursor:pointer;filter:drop-shadow(0 1px 2px rgba(0,0,0,.6));';
      piece.style.left=(e.clientX-r.left)+'px'; piece.style.top=(e.clientY-r.top)+'px';
      piece.addEventListener('click', function(ev){
        ev.stopPropagation();
        insp.querySelector('[data-insp-title]').textContent='Selected · '+kind.charAt(0).toUpperCase()+kind.slice(1);
        insp.style.display='block';
        st.textContent='Selected a '+kind+' — the inspector shows just its properties (that’s Theme B).';
      });
      map.appendChild(piece);
      st.textContent='Placed a '+kind+'. Click it to select, or keep placing.';
    });
    root.querySelector('[data-reset]').addEventListener('click', function(){
      map.querySelectorAll('[data-piece]').forEach(function(p){ p.remove(); });
      tool=null; clearArm(); insp.style.display='none'; st.textContent='Reset — pick a tool to begin.';
    });
  })();
  // 5.3 — summon the inspector; material + opacity update a live preview.
  (function(){
    var root = document.getElementById('mde-b'); if(!root) return;
    var btn = root.querySelector('[data-b-toggle]');
    var insp = root.querySelector('[data-b-insp]');
    var mat = root.querySelector('[data-b-mat]');
    var op = root.querySelector('[data-b-op]');
    var prev = root.querySelector('[data-b-prev]');
    function refresh(){ prev.textContent = 'preview: '+mat.value+' wall @ '+op.value+'% opacity'; }
    btn.addEventListener('click', function(){
      var shown = insp.style.display!=='none';
      insp.style.display = shown ? 'none' : 'block';
      btn.textContent = shown ? 'Select a wall ▸' : 'Deselect ▾';
      if(!shown) refresh();
    });
    mat.addEventListener('change', refresh);
    op.addEventListener('input', refresh);
  })();
  // 5.4 — toggle the label context + the Select&move ↔ Grab rename.
  (function(){
    var root = document.getElementById('mde-d'); if(!root) return;
    var card = root.querySelector('[data-d-card]');
    var title = root.querySelector('[data-d-title]');
    var selBtn = root.querySelector('[data-d-sel]');
    var hint = root.querySelector('[data-d-hint]');
    var c1 = root.querySelector('[data-d-c1]');
    var c2 = root.querySelector('[data-d-c2]');
    var selected = false;
    selBtn.addEventListener('click', function(){
      selected = !selected;
      title.textContent = selected ? 'Selected wall' : 'New wall';
      title.style.color = selected ? '#9fd3ab' : '#8f98bd';
      card.style.borderColor = selected ? '#57b26a' : '#333850';
      [c1,c2].forEach(function(c){ c.style.color = selected?'#e7e9f3':'#c9cee6'; c.style.background = selected?'#243040':'#252a39'; });
      hint.style.display = selected ? 'block' : 'none';
      selBtn.textContent = selected ? 'Deselect ▾' : 'Select the wall ▸';
    });
    var chip = root.querySelector('[data-d-chip]');
    var grab = false;
    root.querySelector('[data-d-rename]').addEventListener('click', function(){
      grab = !grab;
      chip.textContent = grab ? '🖱 Grab' : '🖱 Select & move';
    });
  })();
})();
</script>

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
