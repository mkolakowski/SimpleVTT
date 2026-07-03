# Exploration-tracking fog of war

**Status:** 🟠 partial · Phase 1 (engine + persistence) shipped v2.843.0.
**Extends:** [vision-and-light.md](vision-and-light.md) — reuses that engine's wall model and the client lighting overlay's shadow-casting.

## Problem

The original fog of war (v2.766.0) is a **static, GM-painted, shared rectangle layer**:
`Map.fog_enabled` + `Map.fog_revealed` (`[{x,y,w,h}]`). The GM hand-paints the holes and every
player sees the same reveal. It has no concept of what the party has *explored* — walk a token
into a new room and nothing happens.

This plan adds **exploration-tracking fog**: as player tokens move, the area they can see is
revealed and stays revealed; never-seen areas stay hidden; and areas seen-but-no-longer-in-view
render as a dimmed "memory."

## Design decisions

- **Vision radius:** `max(BASE_SIGHT_FT, token dim-light ft)`, occluded by walls. Even an unlit
  token sees its immediate surroundings; light extends the reveal. Predictable and simple.
- **Rendering (three states):** currently-visible = clear · explored-but-out-of-view = dimmed ·
  never-seen = hidden.
- **Scope:** **shared party memory** — one explored set per map, the union of the party's (hero)
  tokens. Matches "what the *players* have collectively seen."
- **Backward compatible:** `fog_dynamic` opts a map into exploration mode; off = the original
  static-rect behavior, unchanged. GM-painted `fog_revealed` rects coexist as always-clear.

## Persistence (`Map`)

- `fog_dynamic: bool` (default false) — exploration mode on/off.
- `fog_explored: list[[col,row]]` (default `[]`) — accumulated seen grid cells (map-grid units).
  Vision shapes can't be expressed as axis-aligned rects, so we store the seen **grid cells**;
  at a 70 px grid a map is only a few hundred cells. Schema **v97** (additive `ALTER TABLE`).

## Server (`app/routes/tabletop_routes.py`)

- `_sanitize_fog_cells(raw)` — `[[c,r], …]` → non-negative int pairs, deduped, capped
  (`_FOG_EXPLORED_CELL_CAP = 20000`).
- `_fog_payload(m)` — the shared fog shape (`map_id, fog_enabled, fog_dynamic, fog_revealed,
  fog_explored`) used by every read + the `fog_update` broadcast.
- **`POST …/fog/explore`** — any campaign member. Body `{cells: [[c,r], …]}`; **unions**
  (add-only) into `fog_explored`; broadcasts `fog_update` only when the set changed. The
  incremental, non-GM reveal path (the mover's client posts what its party tokens now see).
- **`POST …/fog/reset`** — GM-only. Clears `fog_explored`; broadcasts `fog_update`.
- Extended: `PUT …/fog` accepts `dynamic`; the fog GET, `get_active_map`, the map-editor page
  context, and every `fog_update` broadcast now carry `fog_dynamic` + `fog_explored`.

## Client (`app/static/tabletop.js`) — Phase 2

- Refactor the `drawLighting` closure `_eraseWallShadows(sctx, sx, sy)` into a reusable helper.
- `computeVisibleCells()` — per party token (`team === 'hero'` or `controller_user_id`, not
  hidden): rasterize a `max(BASE_SIGHT_FT, dim_ft)` vision disc on an offscreen canvas, erase
  wall shadows, sample grid-cell centers → currently-visible cells.
- On `token_move` + load, when `fog_dynamic`: drive live rendering from the visible set, union
  new cells into `mapFogExplored`, and POST the newly-added cells to `…/fog/explore` (throttled,
  deduped).
- Three-state `drawFog()`: base veil → partial `destination-out` over explored cells (dim
  memory) + GM rects → full `destination-out` over currently-visible cells.

## Editor + demo — Phase 3

- Map editor: "Dynamic fog (explore)" toggle + "Reset explored" button, wired to the fog PUT
  (`dynamic`) and `…/fog/reset`.
- Demo seed: `fog_dynamic: true` on the maps that already ship fog (Goblin Warrens, Catacombs,
  Drowned Reef, Shadowfell Spire) so exploration fog is live in the demo.

## Tests

- `tests/harness/test_fog_explore.py` — explore unions monotonically; a repeat of the same
  cells is a no-op (`added: 0`, no broadcast); `/fog/reset` is GM-only (player → 403) and clears;
  the `fog_update` broadcast + reads carry `fog_dynamic` + `fog_explored`.
- `tests/harness/test_map_fog.py` — the `dynamic` flag round-trips through PUT.
- Phase 2: a `harness_ui` render test samples the fog canvas (unexplored opaque vs explored dim
  vs visible clear).
