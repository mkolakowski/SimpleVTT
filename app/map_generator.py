"""Procedural battle-map generation (v2.1048.0 "The Cartwright's Compass").

Produces a playable dungeon battle map as PNG bytes entirely server-side —
no external upload, no network call. The output feeds the exact same Map
flow as an uploaded image (see ``settings_generate_map`` in
``app/routes/tabletop_routes.py``): the PNG is written under
``static/uploads/maps/`` and a ``Map`` row is created with matching
``grid_size_px`` so the in-app grid overlay lines up with the drawn cells.

The algorithm is a classic random-room dungeon:

1. Scatter non-overlapping rectangular rooms on a cell grid.
2. Connect consecutive room centres with L-shaped 1-wide corridors.
3. Place doors where a corridor meets a room edge.
4. Render rock / floor / wall-edges / doors to a PNG.

Everything is driven by a seeded ``random.Random`` so a given ``seed``
reproduces the same map — that determinism is what the harness test pins.
Grid overlay lines are deliberately NOT baked into the image; the tabletop
draws its own overlay from ``show_grid`` + ``grid_size_px``, and baking a
second grid would double it.
"""

from __future__ import annotations

import io
import random
from typing import Optional

from PIL import Image, ImageDraw

# --- Sizing presets (in grid cells). Kept small enough that even "large"
# stays well under the 8000 px Map dimension clamp at 70 px/cell. ---
_SIZE_PRESETS: dict[str, tuple[int, int]] = {
    "small": (24, 18),
    "medium": (32, 24),
    "large": (44, 32),
}
_DEFAULT_SIZE = "medium"

# --- Biome registry. Each biome pairs a generation style with a render
# palette (RGB). ``rock`` is the non-floor fill (dungeon stone / cave
# earth / tree canopy / tavern void), ``floor_a``/``floor_b`` the
# alternating floor tint (a faint flagstone/grass texture), ``wall`` the
# boundary stroke, and ``door``/``door_edge`` the doorway plank. ``gen``
# names the layout function; ``label`` is the human name for the UI. ---
_BIOMES: dict[str, dict] = {
    "dungeon": {
        "label": "Dungeon",
        "gen": "dungeon",
        "rock": (24, 26, 32), "floor_a": (58, 64, 76), "floor_b": (52, 58, 70),
        "wall": (14, 15, 19), "door": (138, 94, 52), "door_edge": (92, 60, 30),
    },
    "cave": {
        "label": "Cave",
        "gen": "cave",
        "rock": (30, 24, 20), "floor_a": (74, 62, 48), "floor_b": (66, 55, 42),
        "wall": (18, 14, 10), "door": (138, 94, 52), "door_edge": (92, 60, 30),
    },
    "wilderness": {
        "label": "Wilderness",
        "gen": "wilderness",
        "rock": (40, 54, 34), "floor_a": (86, 112, 64), "floor_b": (78, 104, 58),
        "wall": (24, 34, 20), "door": (138, 94, 52), "door_edge": (92, 60, 30),
    },
    "tavern": {
        "label": "Tavern",
        "gen": "tavern",
        "rock": (26, 20, 14), "floor_a": (120, 86, 54), "floor_b": (108, 76, 46),
        "wall": (58, 38, 22), "door": (156, 116, 70), "door_edge": (104, 72, 38),
    },
}
_DEFAULT_BIOME = "dungeon"


def size_presets() -> list[str]:
    """The valid ``size`` keys, in ascending order — for UI + validation."""
    return list(_SIZE_PRESETS.keys())


def biomes() -> list[dict]:
    """The available biomes as ``{"key", "label"}`` dicts — for the UI +
    validation."""
    return [{"key": k, "label": v["label"]} for k, v in _BIOMES.items()]


def _carve_room(grid: list[list[bool]], x: int, y: int, w: int, h: int) -> None:
    for cy in range(y, y + h):
        for cx in range(x, x + w):
            grid[cy][cx] = True


def _overlaps(rooms: list[tuple[int, int, int, int]], x: int, y: int, w: int, h: int) -> bool:
    """True if (x,y,w,h) touches any existing room with a 1-cell gap."""
    for (rx, ry, rw, rh) in rooms:
        if (x - 1 < rx + rw and x + w + 1 > rx
                and y - 1 < ry + rh and y + h + 1 > ry):
            return True
    return False


def _carve_h_corridor(grid: list[list[bool]], x1: int, x2: int, y: int) -> None:
    for cx in range(min(x1, x2), max(x1, x2) + 1):
        grid[y][cx] = True


def _carve_v_corridor(grid: list[list[bool]], y1: int, y2: int, x: int) -> None:
    for cy in range(min(y1, y2), max(y1, y2) + 1):
        grid[cy][x] = True


def _gen_dungeon(cols: int, rows: int, rng: random.Random):
    """Return ``(grid, doors)`` — ``grid[y][x]`` True = floor; ``doors`` a
    list of door dicts. Classic random-room-and-corridor dungeon."""
    grid = [[False] * cols for _ in range(rows)]
    rooms: list[tuple[int, int, int, int]] = []

    # Attempt a room count that scales with area; the overlap rejection
    # naturally caps how many actually land on a crowded grid.
    attempts = max(8, (cols * rows) // 40)
    for _ in range(attempts):
        w = rng.randint(4, 8)
        h = rng.randint(3, 6)
        x = rng.randint(1, max(1, cols - w - 1))
        y = rng.randint(1, max(1, rows - h - 1))
        if _overlaps(rooms, x, y, w, h):
            continue
        _carve_room(grid, x, y, w, h)
        rooms.append((x, y, w, h))

    # Guarantee at least one room even on a pathologically small grid.
    if not rooms:
        w, h = min(4, cols - 2), min(3, rows - 2)
        _carve_room(grid, 1, 1, w, h)
        rooms.append((1, 1, w, h))

    # Connect consecutive room centres with an L-shaped corridor. Randomise
    # which leg (horizontal-first vs vertical-first) so junctions vary.
    centres = [(rx + rw // 2, ry + rh // 2) for (rx, ry, rw, rh) in rooms]
    for (x1, y1), (x2, y2) in zip(centres, centres[1:]):
        if rng.random() < 0.5:
            _carve_h_corridor(grid, x1, x2, y1)
            _carve_v_corridor(grid, y1, y2, x2)
        else:
            _carve_v_corridor(grid, y1, y2, x1)
            _carve_h_corridor(grid, x1, x2, y2)

    doors = _place_doors(grid, rooms, rng)
    return grid, doors


def _largest_region(grid) -> None:
    """In-place: keep only the largest 4-connected floor region, filling
    every smaller pocket back to rock. Guarantees a single traversable
    area (used by the cave biome)."""
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    seen = [[False] * cols for _ in range(rows)]
    best: list[tuple[int, int]] = []
    for sy in range(rows):
        for sx in range(cols):
            if not grid[sy][sx] or seen[sy][sx]:
                continue
            stack = [(sx, sy)]
            seen[sy][sx] = True
            region = []
            while stack:
                x, y = stack.pop()
                region.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < cols and 0 <= ny < rows and grid[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if len(region) > len(best):
                best = region
    keep = set(best)
    for y in range(rows):
        for x in range(cols):
            if grid[y][x] and (x, y) not in keep:
                grid[y][x] = False


def _gen_cave(cols: int, rows: int, rng: random.Random):
    """Organic caverns via cellular automata, then prune to the largest
    connected region. Caves have no doors."""
    # Random fill (~55% floor), with a solid rock border.
    grid = [[(0 < x < cols - 1 and 0 < y < rows - 1 and rng.random() > 0.45)
             for x in range(cols)] for y in range(rows)]
    for _ in range(5):
        nxt = [[False] * cols for _ in range(rows)]
        for y in range(rows):
            for x in range(cols):
                walls = 0
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = x + dx, y + dy
                        if not (0 <= nx < cols and 0 <= ny < rows) or not grid[ny][nx]:
                            walls += 1
                nxt[y][x] = walls < 5  # floor unless hemmed in by rock
        grid = nxt
    _largest_region(grid)
    return grid, []


def _gen_wilderness(cols: int, rows: int, rng: random.Random):
    """Open field scattered with obstacle clumps (boulders / thickets)
    that block sight. No doors."""
    grid = [[True] * cols for _ in range(rows)]
    clumps = max(4, (cols * rows) // 45)
    for _ in range(clumps):
        x = rng.randint(1, cols - 2)
        y = rng.randint(1, rows - 2)
        for _ in range(rng.randint(3, 8)):
            if 0 < x < cols - 1 and 0 < y < rows - 1:
                grid[y][x] = False
            x += rng.randint(-1, 1)
            y += rng.randint(-1, 1)
    return grid, []


def _gen_tavern(cols: int, rows: int, rng: random.Random):
    """A single walled building subdivided by one partition wall with a
    door gap — a main hall + a back room."""
    grid = [[False] * cols for _ in range(rows)]
    rx, ry, rw, rh = 1, 1, cols - 2, rows - 2
    _carve_room(grid, rx, ry, rw, rh)
    doors: list[dict] = []

    if rng.random() < 0.5 and rw >= 8:
        # Vertical partition: passage crosses it horizontally, so the door
        # is a vertical threshold segment at the gap cell's left edge.
        px = rng.randint(rx + 3, rx + rw - 4)
        gap = rng.randint(ry + 1, ry + rh - 2)
        for y in range(ry, ry + rh):
            if y != gap:
                grid[y][px] = False
        doors.append({"cx": px, "cy": gap, "edge": ("v", px, gap)})
    elif rh >= 8:
        # Horizontal partition: door is a horizontal threshold at the gap.
        py = rng.randint(ry + 3, ry + rh - 4)
        gap = rng.randint(rx + 1, rx + rw - 2)
        for x in range(rx, rx + rw):
            if x != gap:
                grid[py][x] = False
        doors.append({"cx": gap, "cy": py, "edge": ("h", py, gap)})
    return grid, doors


def _place_doors(grid, rooms, rng) -> list[dict]:
    """Mark up to two doorways per room: a corridor cell orthogonally
    adjacent to the room's perimeter (an entrance).

    Each door records the corridor cell (``cx``/``cy``, used for the PNG
    fill) *and* its threshold ``edge`` — the room-wall boundary the
    doorway sits in — so a functional wall segment can be emitted there.
    ``edge`` is ``("h", y_boundary, x_cell)`` or ``("v", x_boundary,
    y_cell)`` in cell units."""
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    doors: list[dict] = []
    seen: set[tuple[int, int]] = set()
    for (rx, ry, rw, rh) in rooms:
        candidates: list[dict] = []
        for cx in range(rx, rx + rw):
            if ry - 1 >= 0 and grid[ry - 1][cx] and (cx, ry - 1) not in seen:
                candidates.append({"cx": cx, "cy": ry - 1, "edge": ("h", ry, cx)})
            if ry + rh < rows and grid[ry + rh][cx] and (cx, ry + rh) not in seen:
                candidates.append({"cx": cx, "cy": ry + rh, "edge": ("h", ry + rh, cx)})
        for cy in range(ry, ry + rh):
            if rx - 1 >= 0 and grid[cy][rx - 1] and (rx - 1, cy) not in seen:
                candidates.append({"cx": rx - 1, "cy": cy, "edge": ("v", rx, cy)})
            if rx + rw < cols and grid[cy][rx + rw] and (rx + rw, cy) not in seen:
                candidates.append({"cx": rx + rw, "cy": cy, "edge": ("v", rx + rw, cy)})
        rng.shuffle(candidates)
        for d in candidates[:2]:
            doors.append(d)
            seen.add((d["cx"], d["cy"]))
    return doors


def _wall_segments(grid, doors, cell: int) -> list[dict]:
    """Emit the map's ``walls`` list (Maps 2.0 line-of-sight format) in
    map-image pixel coords. Solid wall runs trace every floor/non-floor
    boundary (merged into long segments); each door threshold becomes a
    toggleable whole-segment door (``door=True, open=False``)."""
    from collections import defaultdict

    rows = len(grid)
    cols = len(grid[0]) if rows else 0

    door_h = {(a, b) for d in doors if d["edge"][0] == "h" for _, a, b in [d["edge"]]}
    door_v = {(a, b) for d in doors if d["edge"][0] == "v" for _, a, b in [d["edge"]]}

    h_edges: set[tuple[int, int]] = set()  # (y_boundary, x_cell)
    v_edges: set[tuple[int, int]] = set()  # (x_boundary, y_cell)
    for y in range(rows):
        for x in range(cols):
            if not grid[y][x]:
                continue
            if y == 0 or not grid[y - 1][x]:
                h_edges.add((y, x))
            if y == rows - 1 or not grid[y + 1][x]:
                h_edges.add((y + 1, x))
            if x == 0 or not grid[y][x - 1]:
                v_edges.add((x, y))
            if x == cols - 1 or not grid[y][x + 1]:
                v_edges.add((x + 1, y))
    # Doorway openings are floor/floor edges so never land in the solid
    # sets, but subtract defensively in case a room abuts the map edge.
    h_edges -= door_h
    v_edges -= door_v

    walls: list[dict] = []

    def _emit(kind, fixed, a, b, wid):
        if kind == "h":
            coords = (a * cell, fixed * cell, b * cell, fixed * cell)
        else:
            coords = (fixed * cell, a * cell, fixed * cell, b * cell)
        x1, y1, x2, y2 = (float(v) for v in coords)
        return {"id": wid, "x1": x1, "y1": y1, "x2": x2, "y2": y2, "style": "stone"}

    idx = 0
    by_row: dict[int, list[int]] = defaultdict(list)
    for (yb, xc) in h_edges:
        by_row[yb].append(xc)
    for yb, xs in by_row.items():
        xs.sort()
        start = prev = xs[0]
        for xc in xs[1:]:
            if xc == prev + 1:
                prev = xc
            else:
                walls.append(_emit("h", yb, start, prev + 1, f"w{idx}")); idx += 1
                start = prev = xc
        walls.append(_emit("h", yb, start, prev + 1, f"w{idx}")); idx += 1

    by_col: dict[int, list[int]] = defaultdict(list)
    for (xb, yc) in v_edges:
        by_col[xb].append(yc)
    for xb, ys in by_col.items():
        ys.sort()
        start = prev = ys[0]
        for yc in ys[1:]:
            if yc == prev + 1:
                prev = yc
            else:
                walls.append(_emit("v", xb, start, prev + 1, f"w{idx}")); idx += 1
                start = prev = yc
        walls.append(_emit("v", xb, start, prev + 1, f"w{idx}")); idx += 1

    for j, d in enumerate(doors):
        kind, fixed, cidx = d["edge"]
        seg = _emit(kind, fixed, cidx, cidx + 1, f"door{j}")
        seg.update({"door": True, "open": False, "style": "wood"})
        walls.append(seg)

    return walls


def _render(grid, doors, cell: int, palette: dict) -> bytes:
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    img = Image.new("RGB", (cols * cell, rows * cell), palette["rock"])
    draw = ImageDraw.Draw(img)

    # Floor cells with a faint checker so the surface texture reads.
    floor_a, floor_b = palette["floor_a"], palette["floor_b"]
    for y in range(rows):
        for x in range(cols):
            if not grid[y][x]:
                continue
            px, py = x * cell, y * cell
            tint = floor_a if (x + y) % 2 == 0 else floor_b
            draw.rectangle([px, py, px + cell - 1, py + cell - 1], fill=tint)

    # Wall edges: any floor/non-floor boundary gets a thick dark stroke.
    wall_col = palette["wall"]
    wall_w = max(3, cell // 16)
    for y in range(rows):
        for x in range(cols):
            if not grid[y][x]:
                continue
            px, py = x * cell, y * cell
            if y == 0 or not grid[y - 1][x]:
                draw.line([px, py, px + cell, py], fill=wall_col, width=wall_w)
            if y == rows - 1 or not grid[y + 1][x]:
                draw.line([px, py + cell, px + cell, py + cell], fill=wall_col, width=wall_w)
            if x == 0 or not grid[y][x - 1]:
                draw.line([px, py, px, py + cell], fill=wall_col, width=wall_w)
            if x == cols - 1 or not grid[y][x + 1]:
                draw.line([px + cell, py, px + cell, py + cell], fill=wall_col, width=wall_w)

    # Doors: a warm plank set into the doorway cell.
    inset = cell // 4
    door_col, door_edge = palette["door"], palette["door_edge"]
    for d in doors:
        px, py = d["cx"] * cell, d["cy"] * cell
        draw.rectangle(
            [px + inset, py + inset, px + cell - inset, py + cell - inset],
            fill=door_col, outline=door_edge, width=max(2, cell // 24),
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


_GENERATORS = {
    "dungeon": _gen_dungeon,
    "cave": _gen_cave,
    "wilderness": _gen_wilderness,
    "tavern": _gen_tavern,
}


def generate_map(
    *,
    size: str = _DEFAULT_SIZE,
    biome: str = _DEFAULT_BIOME,
    cell_px: int = 70,
    seed: Optional[int] = None,
) -> dict:
    """Generate a battle map with functional walls.

    Returns ``{"png": bytes, "width_px": int, "height_px": int,
    "walls": list}`` — the ``walls`` list is the Maps 2.0 line-of-sight
    format (pixel-coord solid segments + toggleable door segments), ready
    to store on ``Map.walls``. ``size`` is one of :func:`size_presets`
    and ``biome`` one of :func:`biomes`; unknown values fall back to the
    defaults. ``seed`` makes the output deterministic (same seed + biome →
    same map + same walls).
    """
    cols, rows = _SIZE_PRESETS.get(size, _SIZE_PRESETS[_DEFAULT_SIZE])
    cfg = _BIOMES.get(biome, _BIOMES[_DEFAULT_BIOME])
    cell = max(20, min(int(cell_px), 200))
    rng = random.Random(seed)
    grid, doors = _GENERATORS[cfg["gen"]](cols, rows, rng)
    return {
        "png": _render(grid, doors, cell, cfg),
        "width_px": cols * cell,
        "height_px": rows * cell,
        "walls": _wall_segments(grid, doors, cell),
    }


def generate_dungeon(
    *, size: str = _DEFAULT_SIZE, cell_px: int = 70, seed: Optional[int] = None,
) -> dict:
    """Back-compat alias for :func:`generate_map` with the dungeon biome."""
    return generate_map(size=size, biome="dungeon", cell_px=cell_px, seed=seed)


def generate_dungeon_png(
    *, size: str = _DEFAULT_SIZE, cell_px: int = 70, seed: Optional[int] = None,
) -> tuple[bytes, int, int]:
    """Back-compat thin wrapper returning just ``(png, width, height)``."""
    d = generate_dungeon(size=size, cell_px=cell_px, seed=seed)
    return d["png"], d["width_px"], d["height_px"]
