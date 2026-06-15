# Ruler & Range Enforcement — Design Plan

**Status:** ✅ shipped (Phases 1, 2, 3A–E; ruler tool live in `app/static/tabletop.js`, distance enforcement in `token_move`, AoE templates in the canvas picker — git history from v2.49.77). This doc is retained as the design record.
**Filed across:** v2.49.55–v2.49.58 "20-ft radius enforcement" (Sleep), v2.49.57 "push_authorized cast-card UI" (Open Hand), v2.49.55 "Must follow a hit" (Stunning Strike — the related range check on melee Flurry hits).
**Related code surfaces:** `app/static/tabletop.js` (canvas, AoE picker, pointer handlers), `app/routes/tabletop_routes.py::token_move` (distance calc), spell JSON `range` fields.

---

## Goal

Give players and the GM a way to **measure distances on the tabletop** and have the system **enforce range** on attacks and spell casts so that "Magic Missile at the bandit 200 ft away" gets caught before it consumes a spell slot.

Two features, tightly coupled:

1. **Ruler tool** — a player- and GM-accessible measurement UI. Click two points on the map, see the distance in feet. Suspends normal map control while active so the click can't double as a token-move or AoE-commit.
2. **Range enforcement** — when a player invokes an attack or spell against a target, the server checks the source-token → target-token distance against the action's range. Out-of-range invocations are blocked with a 409 the cast card can render as "Out of range (60 ft; target is 90 ft away)."

The two features share the same underlying primitive: a **distance-between-two-canvas-points** function that already exists for token movement (`token_move` endpoint, line 4929 in `tabletop_routes.py`).

---

## Interface changes — at a glance

Every UI delta this plan introduces, gathered in one place so a reviewer can scan what's new without reading the per-phase detail. Per-feature mockups live in the phase sections below.

| # | Surface | Phase | Where | Change | State (default → active) |
|---|---|---|---|---|---|
| 1 | **📏 Ruler button** | 1 | New "canvas-tool" row above the existing drawer tab bar (`tabletop.html:~1216`) | Toggle button. Click → enter ruler mode. Shift-click → broadcast mode (GM demo). `R` hotkey duplicates the click. | Outlined ghost → filled `var(--accent)` + `aria-pressed="true"` |
| 2 | **Ruler hint banner** | 1 | Top-center of the canvas viewport, ~24 px below the top edge | Translucent pill: "Click two points. Esc to cancel." Updates to "Click second point — Esc to cancel" after the first click. | Hidden → visible (300 ms fade) while `_rulerPicker.active` |
| 3 | **Body cursor + click suspension** | 1 | `<body>` element via `.ruler-picker-active` CSS class | Crosshair cursor; map-drag + token-drag suppressed; AoE-picker mutex (only one mode active at a time). | None → crosshair |
| 4 | **Ruler measurement overlay** | 1 | Canvas (new draw pass in `render()` after AoE preview) | Dashed line A → B + filled circle at A + open circle at B (or cursor before second click) + "45 ft" chip at the midpoint. **Snaps to grid cell centers** — see "Snap to grid center" below. | Hidden → drawn during measurement + 3 s after commit |
| 5 | **Out-of-range cast-card banner** | 2 | Cast-card error pane (rendered when server returns 409 `out_of_range`) | Red banner: "Out of range. Counterspell reaches 60 ft. Bandit Captain is 95 ft away." with `[Cancel]` and `[⚠ Cast anyway (GM)]` buttons. The GM-override button is hidden for players in strict mode. | Hidden → visible only on 409 response |
| 6 | **Range ring around caster** | 2 (D) | Canvas — new draw pass during cast-card hover OR while a spell button is hovered on the spell list | Translucent ring at the spell's range (e.g., 120 ft Fire Bolt = 24 grid cells radius) anchored at the caster's token center. Targets inside ring keep normal opacity; targets outside dimmed to 50 %. | Hidden → drawn on hover; removed on hover-out |
| 7 | **Hover rangefinder line** | 3 (C, optional) | Canvas — only when a token is selected AND no other tool mode is active | Thin solid line from selected token to cursor + distance chip. Updates on every `mousemove`. | Hidden → drawn while a token is selected and cursor moves |
| 8 | **Multi-segment ruler waypoints** | 3 (B/extension, optional) | Same overlay as #4 | Shift + R activates a mode where each click adds a waypoint; total distance updates at the midpoint of the last segment. Enter commits; Esc cancels. | Hidden → drawn while in multi-segment ruler mode |
| 9 | **Broadcast-mode ruler ghost** | 3 (extension, optional) | Canvas (all clients) | Same overlay as #4 but rendered semi-transparent + tagged with the broadcaster's name. Lives until the broadcaster releases or 5 s after commit. | Hidden → drawn on every client when the broadcaster shift-clicks the button |

> **Touch / mobile.** Every new surface has a no-keyboard equivalent: button taps replace the `R` hotkey, two finger taps replace the two clicks, long-press cancels (replacing Esc). The hint banner doubles as the discoverability vector for users who don't see the cursor change.

---

## Constraints surfaced by the codebase survey

The plan has to fit the existing system, not invent new infrastructure:

- **Map canvas is 2D Canvas, ~3 K lines, event-driven render loop** (`app/static/tabletop.js`). All rendering goes through one `render()` function. Adding a ruler overlay is a new drawing pass at the end of the loop, after the AoE preview.
- **Grid + distance math already exist server-side.** `token_move` computes Chebyshev distance for square grids and Euclidean for hex, applying 5 ft per grid cell. The ruler reuses this verbatim; the range enforcer reuses the same helper (extracted into a shared function).
- **The AoE picker is the canonical "suspend map control, prompt for clicks, resume" pattern.** It uses a tool-mode flag (`_aoePicker.active`), a CSS class on `<body>` for visual feedback, and a Promise that resolves on confirm/cancel. The ruler tool should mirror its structure.
- **Spell range is plain-text in the JSON** (`"range": "60 feet"`). No numeric `range_ft` field today. The plan adds a server-side parser + a one-time content backfill pass.
- **Touch targets must be ≥ 44 × 44 px** (`CLAUDE.md`). Any new toolbar button must meet this.
- **Every endpoint commit lands harness tests** (`CLAUDE.md`). Any new endpoint or broadcast in this plan gets per-commit harness coverage.

---

## Approaches considered

### A) Modal ruler button (suspend map control + two left-clicks) — **RECOMMENDED**

Click the ruler button in the right-hand drawer (or via a hotkey, e.g. `R`). The cursor changes; map drag/click is suspended. Left-click point A, then left-click point B. A line is drawn between the two with the distance in feet rendered as a tooltip at the midpoint. Esc or right-click cancels. Confirming (a second click) freezes the measurement on-screen for ~3 s as a translucent ghost, then clears.

**Pros:**
- Mirrors the AoE picker pattern exactly — same `start() → Promise → cleanup()` shape (`tabletop.js:314–527`).
- Two discrete clicks are easy to undo (Esc cancels point A, second click commits).
- Works equally well with mouse + touch (touch device's "click" is a tap; no drag tracking required).
- The "suspend map control" semantics are already established + tested via the AoE picker.

**Cons:**
- Two clicks vs. one drag — slightly higher interaction cost.
- Requires the user to enter ruler mode explicitly. A drag-mode alternative (option B) requires no mode change.

### B) Drag-to-measure (no mode toggle)

Hold a modifier (e.g. Shift) and drag from a point — the distance updates live. Release ends the measurement. No button needed.

**Pros:** No mode change, no toolbar button, fewer clicks.
**Cons:**
- Modifier-drag conflicts with future pan/zoom-with-modifier patterns.
- Touch devices have no Shift key — they'd need a separate UX anyway.
- Live-update during drag is more rendering work + can flicker on slow devices.
- Less discoverable; a button + tooltip is easier to find than a hidden gesture.

**Verdict:** Discoverability + touch-device compatibility win. Defer drag-mode to a future enhancement; let the button be primary.

### C) Hover rangefinder on selected token

When a token is selected, hovering elsewhere on the map shows a distance line from the selected token to the cursor. No clicks needed.

**Pros:** Zero interaction cost for "how far is X from Y" when X is selected.
**Cons:**
- Only works for "from a token." Doesn't measure arbitrary points (e.g. "how wide is this room?").
- Hover-line is visual noise when the player just wants to look at the map.
- Doesn't generalize to the range-enforcement use case (the server doesn't need a "cursor" coordinate).

**Verdict:** Useful as an **additive** feature later, but it doesn't replace the ruler. The ruler is the primitive; hover-rangefinder is sugar on top once a token is selected.

### D) Attached-range overlays (range ring around selected token's current weapon / spell)

When a player selects a token and clicks "Fire Bolt" in the cast list, a 120-ft (Fire Bolt's range) ring renders around the token. Targets within the ring are valid; targets outside are dimmed.

**Pros:**
- Best UX for the "is this target in range?" check — completely visual, no clicks.
- Naturally extends to "show me all valid targets for this spell."

**Cons:**
- Requires every spell + attack to have a numeric `range_ft` field (a content backfill problem either way).
- Layered overlays clutter the map if multiple are active.
- Doesn't measure arbitrary distances (the room-width problem from option C).

**Verdict:** **Complement to the ruler, not replacement.** Ship the ruler first (small, isolated, useful on its own); add range rings in a follow-up commit gated on the spell-range-parsing work, since the parser is shared infrastructure.

### Recommended composition

| Feature | Phase | Built on |
|---|---|---|
| **A** Ruler tool (button + two-click) | 1 | AoE picker pattern |
| **D** Range rings on selected target | 2 | Phase 1's distance helper + spell-range parser |
| **Server range enforcement (409)** | 2 | Phase 1's helper + parser |
| **C** Hover rangefinder on selected token | 3 (optional) | Phase 1's helper |
| **B** Modifier-drag shortcut | 3 (optional) | Phase 1's overlay |

---

## Chosen approach — detailed design

### Phase 1: Ruler tool

#### Client state

In `app/static/tabletop.js`, add a `_rulerPicker` object next to the existing `_aoePicker` (~line 314). Same shape:

```javascript
const _rulerPicker = {
    active: false,
    points: [],          // [{x, y}, {x, y}] — accumulated clicks
    cursor: null,        // {x, y} — mouse-follow for live preview
    _resolve: null,
    start() {
        if (this.active) return;
        this.active = true;
        this.points = [];
        document.body.classList.add('ruler-picker-active');
        _showRulerHint();        // tooltip: "Click two points. Esc to cancel."
        try { render(); } catch (_) {}
        return new Promise((resolve) => { this._resolve = resolve; });
    },
    cancel() { this._cleanup(); if (this._resolve) this._resolve(null); },
    addPoint(x, y) {
        this.points.push({x, y});
        if (this.points.length >= 2) {
            const distance_ft = _computeDistanceFt(this.points[0], this.points[1]);
            this._resolve({points: this.points, distance_ft});
            // Freeze the line for 3 s then clear.
            setTimeout(() => this._cleanup(), 3000);
        }
    },
    _cleanup() { /* mirror _aoePicker._cleanup */ }
};
```

#### Mouse integration

Insert at the top of the existing `mousedown` handler (`tabletop.js:1477`) BEFORE the AoE-commit branch:

```javascript
if (_rulerPicker.active && e.button === 0) {
    const {x, y} = _canvasPoint(e);
    _rulerPicker.addPoint(x, y);
    e.preventDefault();
    return;
}
```

Same insertion point in `mousemove` (`tabletop.js:1600`) for cursor updates, and `contextmenu` (`tabletop.js:1405`) for right-click cancel.

#### Rendering

Add a new drawing pass in `render()` after the AoE preview (`tabletop.js:~905`):

```javascript
if (_rulerPicker.active || _rulerPicker.points.length === 2) {
    _drawRuler(ctx, _rulerPicker);
}
```

`_drawRuler` draws:
- A dashed line from point A to (point B or cursor).
- A circle at each established point.
- A label at the midpoint: `"45 ft"` (rounded to nearest 0.1 ft) in a chip with `var(--bg-2)` background.

#### Snap to grid center

Both committed points AND the live cursor preview snap to the **center of the grid cell** under the pointer. The user clicks anywhere inside a cell and the ruler treats it as if they clicked the cell's center. Rationale:

- **5e RAW measures by squares**, not by pixels. A ruler that returns "22.7 ft" because the user clicked slightly off-center is more confusing than helpful at a TTRPG table.
- **Clean integer-ft results on square grids.** With both endpoints snapped, the Chebyshev distance is always an integer number of cells × 5 ft. Players see "20 ft" instead of "22.7 ft."
- **Consistent with token placement.** Tokens already snap-to-grid via `snapToGrid` (in `tabletop.js:79`); the ruler reuses the same primitive so a measurement between two tokens equals the distance the tokens would actually be on the grid.
- **Hex is unchanged in spirit.** Hex centers ARE the only sensible positions in a hex layout; `snapToGrid` already returns the hex center for any pixel inside a hex.

Implementation: add a small `_snapPointToGridCenter(x, y) -> {x, y}` helper near `snapToGrid`. For square grids: `(Math.floor(x / gridSize) + 0.5) * gridSize`. For hex: delegate to `snapToGrid` (which already returns the hex center). Square `snapToGrid` returns the CORNER (top-left of the cell at the rounded grid intersection) — so the ruler can't reuse it directly; the `+ 0.5` offset is the bit that differs. Call the helper at THREE sites:

1. `mousedown` ruler intercept — snap the canvas point before `addPoint`.
2. `mousemove` ruler cursor update — snap the canvas point before storing as `cursor`.
3. The `points[]` array always holds snapped values (so the render-pass draws snapped lines without re-snapping).

**No "free-mode" override in Phase 1.** A future Shift-modifier could let the user pin a point off-center (for measuring along a non-grid-aligned wall), but every VTT we surveyed (Roll20, Foundry VTT) defaults to snap and the override is rarely used. Keep it simple; file the override if a user asks.

#### Toolbar button

The survey notes the GM Tools drawer (`tabletop.html:1216–1222`) is the right home for tool buttons. **But the ruler should be available to players too**, not just the GM — measuring range is a player concern. Two options:

1. Add a "📏 Ruler" button to a NEW row inserted at the top of the right-hand drawer, above the existing tab bar. Visible to GM + players.
2. Add it to the players' Battle drawer (already player-facing).

**Recommendation: option 1**, with a hotkey (`R`) registered in the canvas keydown handler so the button is supplementary.

#### Mockup — toolbar insertion

```
┌────────────────────────────────────────┐
│  📏 Ruler   🎯 Targets   ↩ Undo Move  │  ← NEW canvas-tool row, 44 px tall
├────────────────────────────────────────┤
│  Roll Log   Battle   ⚙ GM Tools       │  ← existing tab bar (unchanged)
├────────────────────────────────────────┤
│  (drawer contents based on active tab)│
└────────────────────────────────────────┘
```

Each button is `min-width: 44px; min-height: 44px` per the touch-target rule. The 📏 Ruler button is a toggle — active state has an `aria-pressed="true"` + a filled `var(--accent)` background.

#### Mockup — ruler active

```
                  ┌─ point A (filled circle)
                  ●
                   \                            ┌─ "45 ft" chip at midpoint
                    \   ╲─ ╲─ ╲                 │
                     \    ╲    ╲    ┌─────┐    │
                      ●─ ─ ─ ─ ─ ─ ─│45 ft│─ ─ ┘
                      │              └─────┘
                      └─ cursor (open circle, live preview before second click)

Body cursor: crosshair
Body class: .ruler-picker-active (overrides hover-token-cursor)
Hint banner: see mockup below
```

#### Mockup — hint banner

```
   Canvas top edge
   ╔════════════════════════════════════════════════════════════╗
   ║                                                            ║
   ║      ┌─────────────────────────────────────────────────┐  ║
   ║      │  📏 Click second point — Esc to cancel          │  ║  ← floating pill,
   ║      └─────────────────────────────────────────────────┘  ║     centered, ~24 px from top
   ║                                                            ║
   ║                                                            ║
   ║       (map content)                                        ║
   ║                                                            ║

   Background:   var(--bg-2) at 90 % alpha
   Border:       1 px solid var(--accent)
   Text:         var(--fg) — 14 px
   Padding:      8px 16px
   Border-radius: 999px (pill)
   Position:     fixed, top: 24px, left: 50% transform: translateX(-50%)
   Z-index:      2000 (above canvas overlays, below modals)
   Fade-in:      300 ms ease on activate; 200 ms fade-out on cleanup.

   Text variants by ruler state:
     - 0 points clicked: "📏 Click two points. Esc to cancel."
     - 1 point clicked:  "📏 Click second point — Esc to cancel."
     - 2 points (committed, 3 s ghost): hint hides early.

   Mobile: identical visual; long-press anywhere on the canvas to dismiss
   if the player wants to cancel without finding a keyboard.
```

#### Mockup — toolbar button states

```
   Default (inactive):
   ┌──────────────┐
   │  📏 Ruler    │   border: 1 px solid var(--border)
   └──────────────┘   bg: transparent, color: var(--fg)

   Hover:
   ┌──────────────┐
   │  📏 Ruler    │   bg: var(--bg-2), color: var(--fg)
   └──────────────┘

   Active (ruler mode on):
   ┌──────────────┐
   │  📏 Ruler ◉  │   bg: var(--accent), color: var(--accent-fg)
   └──────────────┘   aria-pressed="true"

   Broadcasting (Shift-click activated):
   ┌──────────────┐
   │  📏 Ruler 📡 │   bg: var(--accent), badge: 📡 (cyan)
   └──────────────┘   aria-pressed="true", title="Broadcasting to all clients"

   Disabled (e.g. no active map):
   ┌──────────────┐
   │  📏 Ruler    │   opacity: 0.5, cursor: not-allowed
   └──────────────┘   title="Ruler needs an active map"
```

#### Hotkeys

- `R` toggles the ruler tool.
- `Esc` cancels (matches the AoE picker's Esc behavior).
- `Shift + R` (future) — multi-segment ruler that keeps adding waypoints until you press Enter.

#### Visibility broadcast

**Decision:** the ruler is **local-only** by default. Other players don't see your measurements — they're an analog of "running a tape measure across the page." A `Shift + click` on the ruler button activates "broadcast mode" (sends the active ruler to everyone via a new `ruler_active` WS event) for GM-led range demos.

**Why local by default:** measuring shouldn't reveal the player's plan to the GM (and vice versa). The broadcast mode covers the "GM, can you show everyone how far my Fire Bolt reaches?" case explicitly.

---

### Phase 2: Range enforcement

#### Server-side distance helper

Extract the distance math from `token_move` (lines 4929–4946 in `tabletop_routes.py`) into a shared helper:

```python
# app/routes/tabletop_routes.py
def _distance_ft_between_tokens(map_id: int, token_a_id: int, token_b_id: int, db: Session) -> float | None:
    """Compute distance in feet between two tokens on the same map.
    Returns None if either token is missing or maps differ.
    """
    a = db.query(Token).filter(Token.id == token_a_id).first()
    b = db.query(Token).filter(Token.id == token_b_id).first()
    if not a or not b or a.map_id != b.map_id or a.map_id != map_id:
        return None
    m = a.map
    grid_size_px = m.grid_size_px or 70
    grid_type = (m.grid_type.value if m.grid_type else "square").lower()
    dx, dy = (b.x or 0) - (a.x or 0), (b.y or 0) - (a.y or 0)
    if grid_size_px <= 0:
        return None
    if grid_type == "square":
        cells = max(abs(dx), abs(dy)) / grid_size_px
    else:
        cells = (dx * dx + dy * dy) ** 0.5 / grid_size_px
    return round(cells * 5, 1)
```

#### Spell-range parser

Plain-text `range` strings → numeric feet. Cases to cover:
- `"Self"` → 0
- `"Touch"` → 5 (RAW: touch range = melee reach)
- `"5 feet"` / `"60 feet"` / `"150 feet"` → 5 / 60 / 150
- `"30/120 feet"` (thrown weapons — normal/long range) → returns a tuple `(30, 120)`
- `"Self (30-foot radius)"` → 0 for the cast range; the radius is irrelevant to the cast check (AoE selector handles it)
- Unknown / unparseable → `None` (no enforcement; logged for content cleanup)

Implementation: a small parser in `app/content/range_parser.py` with unit tests, called from a `_spell_range_ft(spell_dict) -> int | None | tuple[int, int]` helper that callers can apply.

#### Endpoint integration

Existing endpoints to extend:
- `/use_attack` — check melee weapon ranges (5 ft for melee, 20/60 for thrown darts, etc.).
- `/cast_spell`, `/cast_hex`, `/cast_sleep`, `/use_stunning_strike`, `/use_open_hand_technique` — check spell/feature ranges.

The check fires only if **both source and target have tokens on the same active map**. PCs without placed tokens get a free pass (so a PC casting from a campaign without an active map doesn't get blocked). If the source or target is "synthesized" (target_character_id with no live combatant), skip the check — covers the "off-map" GM-narrative case.

New body field on every check-able endpoint: `override_range: bool` (default False). When true + the requester is GM or strict mode is off, the range check is bypassed. Surfaces the same way as the existing Phase 4 action-economy `override` — the cast card's "Cast anyway" button sets it.

#### 409 response shape

```json
{
  "error": "out_of_range",
  "source_name": "Thalindra",
  "target_name": "Bandit Captain",
  "distance_ft": 95,
  "range_ft": 60,
  "spell_name": "Counterspell"
}
```

Client cast card renders this as a banner: `"Out of range (60 ft; target is 95 ft away)"` with an "Override" button that re-fires the cast with `override_range: true`.

#### Mockup — out-of-range cast card

```
┌─────────────────────────────────────────────┐
│ ⚠ Out of range                              │
│ Counterspell reaches 60 ft.                 │
│ Bandit Captain is 95 ft away.               │
│                                             │
│   [ Cancel ]    [ ⚠ Cast anyway (GM) ]     │
└─────────────────────────────────────────────┘
```

#### When NOT to enforce

- **Self-range spells** (`Self` / `Self (30 ft radius)`) — no target distance to check.
- **Off-map casts** — if either party has no token on the active map.
- **AoE placement** — `/place_aoe` already gets the placement coordinate from the user; range against the cast point is already implicit in the picker UI. (A future enhancement: warn if the placement is beyond the spell's `range`, but not block it.)
- **Synthesized targets** (target_character_id with no live combatant in battle) — common in GM-narrative casts (`/cast_hex` at "the shopkeeper" who isn't tokenized).

#### Harness tests for Phase 2

Per CLAUDE.md, each endpoint commit lands at least one harness test:

- **Happy path:** Thalindra at (100, 100), bandit at (200, 100), Fire Bolt (120 ft range) → 200 (1 cell = 5 ft, 100 px = ~7 ft) → in range, normal success.
- **Out of range:** same setup, but bandit at (1000, 100) → 409 `out_of_range`.
- **Override:** same as out-of-range case but body includes `override_range: true` → 200 (GM-only allowed if strict; bypass-otherwise).
- **Self-range no-check:** Bless on Thalindra herself → no range check fires regardless of distance.
- **Off-map no-check:** target_character_id present but no token → skip check.

These are per-endpoint, so one for `/cast_spell`, one for `/use_attack`, etc. Reuse a `test_range_enforcement.py` fixture that seeds map + tokens + caster pair.

---

### Phase 3

Originally framed as "optional follow-ups" — promoted to a load-bearing slot when **Phase 3A (AoE range enforcement)** was identified as closing a real correctness gap that Phase 2 deliberately deferred. The remaining items (3B–3E) stay optional.

#### Phase 3A — AoE range visualization + enforcement (LOAD-BEARING)

Phase 2 enforces range for single-target casts; AoE casts (Fireball, Sleep, Thunderwave, Shatter, etc.) deliberately skipped because the endpoint receives pre-resolved targets WITHOUT a cast-point coordinate. `/place_aoe` (the modern AoE flow's commit endpoint) DOES carry the picker's chosen center coordinate — so the server CAN enforce range there. Plus the picker UI should render a translucent range ring around the caster's token while the picker is active so the player gets pre-commit visual feedback.

**Server (5 minutes of edits, ~30 lines):**

Add a range check to `/place_aoe` that compares the body's `center: {x, y}` against the caster's token position on the active map. The cast context stashed in `_pending_aoe_casts` already carries the caster's character_id; pull the caster's Token row, compute distance via `_distance_ft_between_points`, parse the spell's range string via the v2.49.74 parser, and return 409 `out_of_range` if the placement exceeds the spell's range. Same three-tier override as Phase 2C (GM auto-bypass, player override + not strict, otherwise enforced).

For the legacy `/cast_spell`-with-`target_combatant_ids`-list flow (pre-v2.48.0 AoE), no `cast_point` is available — keep skipping per the existing convention. Future content / picker work could pass `cast_point` through but that's a separate refactor.

**Client (~80 LOC):**

When `_aoePicker.active` is true, render a translucent range ring around the caster's token at the spell's `range_ft` (parsed via a JS port of `parse_range_ft` or passed through from the spell-cast call site). When the cursor's distance to the caster exceeds `range_ft`, dim the AoE preview (e.g. desaturated stroke + faded fill) so the player sees the placement would be rejected.

#### Mockup — AoE picker with range ring (Phase 3A)

```
   Caster: Thalindra (Fireball, range 150 ft = 30 cells = 2100 px on the demo grid)

   ╲╲╲╲                                          ╱╱╱╱
   ╲ ╲ ╲╲                                       ╱╱ ╱ ╱           ← translucent range
   ╲    ╲╲   ┌─ caster token                  ╱╱   ╱             ring (alpha 0.08
   ╲     ●─ ╲                                ╱    ╱              fill, dashed accent
   ╲        ╲─ ╲                            ╱   ╱                stroke)
   ╲          ╲─ ╲                        ╱   ╱
   ╲    in-range zone (Fireball ≤ 150 ft)╲╱─ ╱       ← AoE picker preview
   ╲                                ┌────╲                       (sphere/cone/cube)
   ╲                              ┌─╲─ ─ ╲                       follows the cursor
   ╲                              │  ╲─ ─ ╲   AoE preview         normally; gets
   ╲                              │   ╲─ ─ ╲  rendered            dimmed when cursor
   ╲                              │    ╲─ ─ ╲ inside ring         goes outside the ring
   ╲                              └─────────╲
   ╲                                         ╲
   ╱                                                              ⚠ AoE preview outside
   ╱                                          ┌─ ─ ─ ─ ┐         ring renders desaturated
   ╱╱                                          │ ─ ─ ─ │  ← dimmed (red instead of orange,
   ╱ ╱╱                                       │  outside │     opacity 0.5)
   ╱   ╱╱                                      └─ ─ ─ ─ ┘
   ╱       ╱╱                                                     Click anyway: server
   ╱           ╱╱╱╱                                              returns 409 out_of_range
   ╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱           with the placement coord.

   Ring fill:   rgba(74, 222, 128, 0.08)   — soft green
   Ring stroke: 1.5 px dashed var(--accent) — visible at any zoom
   Dimmed AoE: stroke #555, fill rgba(220, 38, 38, 0.10), opacity 0.5
```

#### Phase 3B–3E (optional polish)

- **3B Hover rangefinder** when a token is selected (option C). Implementation is a single render-loop branch: if `selectedToken && cursor && !_rulerPicker.active && !_aoePicker.active`, draw a thin distance line from `selectedToken` to `cursor`.
- **3C Range rings on cast-button hover** (option D). When the player mouses over a spell button in the cast list (before they've clicked Cast), render a translucent ring around the caster's token at the spell's range. Phase 3A's ring shows DURING the AoE picker; this one shows BEFORE the cast even fires — a "where can this reach?" preview. Same rendering primitive.
- **3D Multi-segment ruler** (Shift + R). Same `_rulerPicker.addPoint()` but doesn't auto-commit after 2 points; commit on Enter. Useful for "what's the total path length around the corner?"
- **3E Broadcast mode toggle** for GM-led range demos (Shift-click the Ruler button).

#### Mockup — hover rangefinder

When a token is selected (highlighted blue) AND the cursor is anywhere else on the map AND no other tool mode is active, draw a thin distance line from the selected token's center to the cursor:

```
   ┌──────────────────────────────────────┐
   │                                      │
   │   ┌─ selected token (blue ring)      │
   │   ●                                  │
   │    \                                 │
   │     \─ ─ ─ ─ ┐                       │
   │              │  35 ft                │
   │              ●  ← cursor             │
   │                                      │
   └──────────────────────────────────────┘

   Stroke:    1 px solid var(--fg-mute)   (thinner than the ruler tool's dashed line — passive cue, not a measurement commit)
   Chip:      "35 ft" floating 12 px from cursor, anchored to mouse position
   Suspended: while _rulerPicker.active OR _aoePicker.active (don't double-draw distance lines)
   Suspended: while the player is dragging the token (movement breadcrumb already shows distance)
```

#### Mockup — range ring on cast-button hover

When the cast-card or the inline spell list is open AND the player hovers a spell button, render a translucent ring around the caster's token at the spell's range. Out-of-range tokens dim to 50 %:

```
  Spell list panel              Map canvas

  ┌─────────────────────┐       ┌────────────────────────────────────────┐
  │ Spells              │       │                                        │
  │                     │       │     ┌─ caster token                    │
  │ [Fire Bolt]  ▶ hov  │ ────► │     ●                                  │
  │   120 ft            │       │   ╱╱│╲╲                                │
  │                     │       │ ╱╱  │  ╲╲                              │
  │ [Magic Missile]     │       │╱    │    ╲                             │
  │   120 ft            │       │     │     │ ← translucent ring, 24-cell│
  │                     │       │     │     │   radius (= 120 ft / 5 ft) │
  │ [Healing Word]      │       │╲    │    ╱                             │
  │   60 ft             │       │ ╲╲  │  ╱╱                              │
  │                     │       │   ╲╲│╱╱                                │
  │                     │       │     ●           ●←dimmed (out of range)│
  │                     │       │  bandit-1                              │
  │                     │       │  (in range)         bandit-2           │
  └─────────────────────┘       └────────────────────────────────────────┘

  Ring fill:    rgba(74, 222, 128, 0.08)  (theme accent green @ 8 % alpha)
  Ring stroke:  1 px dashed var(--accent)
  Dimmed tokens: filter: brightness(0.5) opacity(0.5) — same effect as the
                 out-of-init token style; non-confusable from "selectable but currently invalid"
```

#### Mockup — multi-segment ruler (Shift + R)

```
   Shift+R → cursor: crosshair, hint: "Click waypoints — Enter to commit, Esc to cancel"

   ●─ ─ ─ ─ ●─ ─ ─ ─ ─ ─ ─ ●─ ─ ─ ─ ┐
   A        wp1             wp2     │  ← live cursor with running total "85 ft"
                                    ●

   Segments rendered as separate dashed lines.
   Each segment's length displayed at its midpoint.
   Total at the end-of-path cursor chip.
   Enter → freeze for 3 s then clear (matches single-segment behavior).
```

#### Mockup — broadcast mode (Shift-click the Ruler button)

```
   Toolbar:  [📏 Ruler ◉]   ← active + broadcasting (filled accent + 📡 satellite badge)

   All connected clients see:

   ●─ ─ ─ ─ ─ ─ ─ ─ ●  "45 ft (Demo GM)"
   A                B

   Same overlay as #4, but rendered semi-transparent (alpha 0.6) and tagged
   with the broadcaster's display name in the chip.
   Server emits a `ruler_active` WS broadcast on every addPoint() + a
   `ruler_cleared` on cleanup. Clients render via a new `_remoteRulers`
   map keyed by user_id; expired entries (5 s after the broadcaster's
   commit) auto-drop.
```

---

## Open questions

1. **Diagonal counting on square grids.** The current `token_move` uses Chebyshev (max(|dx|, |dy|)) which is 5e RAW "5-5-5" diagonals. Some tables play "5-10-5" (1.5x diagonal). Should the ruler match the grid's existing rule or expose a per-campaign setting? **Recommendation:** match `token_move` exactly. Don't add a new setting unless someone asks.
2. **Should the ruler measure to token edge or center?** Current `token_move` measures center-to-center. For range purposes 5e uses the "nearest squares" rule (often called token edge), but center-to-center is a common shortcut. **Recommendation:** center-to-center for consistency with `token_move`. Add an "edge" mode in Phase 3 if requested.
3. **What about cover / line-of-sight?** Out of scope. RAW range is "is the target within range AND visible" — visibility is a much bigger feature. The range enforcer answers only the first question.
4. **Should range check fire BEFORE or AFTER spell slot consumption?** Before. The 409 `out_of_range` returns BEFORE the `slot["used"] += 1` mutation — same pattern as the existing 409 `no_slot` gate. A blocked cast doesn't consume resources.
5. **Should the demo seed include a "range demo" encounter?** Probably yes — drop a couple bandits 200 ft from Thalindra so the harness range-enforcement test has a deterministic setup. Coupled to the Phase 2 implementation commit, not Phase 1.

---

## Implementation phases summary

| Phase | Scope | Estimated LOC | Harness tests | Notes |
|---|---|---|---|---|
| **1** | Ruler tool: `_rulerPicker` + toolbar button + render pass + hotkey | ~250 client, ~20 server (none — ruler is client-side) | 0 (no endpoints) | The harness rule applies to endpoints; ruler has none. CSS-only / interaction tests would need Playwright, which the project already uses. |
| **2** | Distance helper + spell-range parser + range enforcement on `/cast_spell` + `/use_attack` | ~150 server, ~50 client (cast-card 409 banner) | ≥1 per touched endpoint × ~6 endpoints | Each endpoint commit ships its own version bump per CLAUDE.md. |
| **3** | Hover rangefinder + range rings + multi-segment ruler + broadcast mode | optional / per-feature | per-commit | All optional; ship if user demand surfaces. |

Phase 1 is shippable alone — the ruler is useful even without enforcement. Phase 2 builds on Phase 1's distance helper but is otherwise independent.

---

## File-path index (for the implementation agent)

| File | Section to touch | Why |
|---|---|---|
| `app/static/tabletop.js:314–527` | `_aoePicker` — copy as template | Picker pattern + cleanup |
| `app/static/tabletop.js:770–903` | `render()` — add `_drawRuler` call | New draw pass |
| `app/static/tabletop.js:1477–1488` | `mousedown` — add ruler branch | Click → addPoint |
| `app/static/tabletop.js:1600–1624` | `mousemove` — add cursor update | Live preview |
| `app/static/tabletop.js:1405` | `contextmenu` — add ruler cancel | Right-click cancel |
| `app/templates/tabletop.html:1216` | Drawer tab bar — insert canvas-tool row above | Button placement |
| `app/static/style.css` | Add `.ruler-picker-active` body class styles | Cursor / hover overrides |
| `app/routes/tabletop_routes.py:4929–4946` | `token_move` distance math — extract helper | Phase 2 reuse |
| `app/content/range_parser.py` (NEW) | Spell-range parser | Phase 2 |
| `app/routes/tabletop_routes.py` — each cast / attack endpoint | Add range check + `override_range` gate | Phase 2 |
| `tests/harness/test_range_enforcement.py` (NEW) | Per-endpoint tests | Phase 2 |
| `docs/test-harness-coverage.md` | New section per harness file | Phase 2 |

---

## Decision log

- **Picker pattern over drag-mode** — discoverability + touch parity wins.
- **Local-only ruler by default** — measurements don't reveal strategy; Shift-click activates broadcast.
- **Center-to-center distance** — matches the existing `token_move` rule; new rule would be a separate decision.
- **Range check before slot consumption** — matches the existing `no_slot` gate ordering.
- **One ruler button, accessible to GM + players** — measuring is a player concern, not a GM-only tool.
- **`override_range` body field over a magic header or query string** — matches the existing `override` Phase-4 pattern.
- **Spell-range parser as separate file** — content concern; isolating it from `tabletop_routes.py` keeps the route file's surface area down.
