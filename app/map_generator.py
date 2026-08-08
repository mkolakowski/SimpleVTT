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

# Render palette (RGB). A dark dungeon read: near-black rock, cool stone
# floor, black wall edges, and a warm door.
_ROCK = (24, 26, 32)
_FLOOR_A = (58, 64, 76)
_FLOOR_B = (52, 58, 70)  # alternating cell tint for a faint flagstone texture
_WALL = (14, 15, 19)
_DOOR = (138, 94, 52)
_DOOR_EDGE = (92, 60, 30)


def size_presets() -> list[str]:
    """The valid ``size`` keys, in ascending order — for UI + validation."""
    return list(_SIZE_PRESETS.keys())


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


def _generate_layout(cols: int, rows: int, rng: random.Random):
    """Return ``(grid, doors)`` — ``grid[y][x]`` True = floor; ``doors`` a
    list of ``(x, y)`` cells drawn as doorways."""
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


def _render(grid, doors, cell: int) -> bytes:
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    img = Image.new("RGB", (cols * cell, rows * cell), _ROCK)
    draw = ImageDraw.Draw(img)

    # Floor cells with a faint checker so flagstones read at a glance.
    for y in range(rows):
        for x in range(cols):
            if not grid[y][x]:
                continue
            px, py = x * cell, y * cell
            tint = _FLOOR_A if (x + y) % 2 == 0 else _FLOOR_B
            draw.rectangle([px, py, px + cell - 1, py + cell - 1], fill=tint)

    # Wall edges: any floor/non-floor boundary gets a thick dark stroke.
    wall_w = max(3, cell // 16)
    for y in range(rows):
        for x in range(cols):
            if not grid[y][x]:
                continue
            px, py = x * cell, y * cell
            if y == 0 or not grid[y - 1][x]:
                draw.line([px, py, px + cell, py], fill=_WALL, width=wall_w)
            if y == rows - 1 or not grid[y + 1][x]:
                draw.line([px, py + cell, px + cell, py + cell], fill=_WALL, width=wall_w)
            if x == 0 or not grid[y][x - 1]:
                draw.line([px, py, px, py + cell], fill=_WALL, width=wall_w)
            if x == cols - 1 or not grid[y][x + 1]:
                draw.line([px + cell, py, px + cell, py + cell], fill=_WALL, width=wall_w)

    # Doors: a warm plank set into the doorway cell.
    inset = cell // 4
    for d in doors:
        px, py = d["cx"] * cell, d["cy"] * cell
        draw.rectangle(
            [px + inset, py + inset, px + cell - inset, py + cell - inset],
            fill=_DOOR, outline=_DOOR_EDGE, width=max(2, cell // 24),
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def generate_dungeon(
    *,
    size: str = _DEFAULT_SIZE,
    cell_px: int = 70,
    seed: Optional[int] = None,
) -> dict:
    """Generate a dungeon battle map with functional walls.

    Returns ``{"png": bytes, "width_px": int, "height_px": int,
    "walls": list}`` — the ``walls`` list is the Maps 2.0 line-of-sight
    format (pixel-coord solid segments + toggleable door segments), ready
    to store on ``Map.walls``. ``size`` is one of :func:`size_presets`;
    an unknown value falls back to ``medium``. ``seed`` makes the output
    deterministic (same seed → same map + same walls).
    """
    cols, rows = _SIZE_PRESETS.get(size, _SIZE_PRESETS[_DEFAULT_SIZE])
    cell = max(20, min(int(cell_px), 200))
    rng = random.Random(seed)
    grid, doors = _generate_layout(cols, rows, rng)
    return {
        "png": _render(grid, doors, cell),
        "width_px": cols * cell,
        "height_px": rows * cell,
        "walls": _wall_segments(grid, doors, cell),
    }


def generate_dungeon_png(
    *,
    size: str = _DEFAULT_SIZE,
    cell_px: int = 70,
    seed: Optional[int] = None,
) -> tuple[bytes, int, int]:
    """Back-compat thin wrapper over :func:`generate_dungeon` returning
    just ``(png_bytes, width_px, height_px)``."""
    d = generate_dungeon(size=size, cell_px=cell_px, seed=seed)
    return d["png"], d["width_px"], d["height_px"]
