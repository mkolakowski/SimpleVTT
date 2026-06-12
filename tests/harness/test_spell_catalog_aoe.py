"""Phase 2G — area-of-effect shape assertions across the spell catalog.

For every spell in ``app/data/local/dnd5e/spells/``: inspect each
action's ``area`` block (``{shape, size_ft, secondary_ft}``) and assert
that any non-empty ``shape`` is one of the RAW-recognized AoE shapes the
server's ``_AOE_SHAPE_SET`` accepts, paired with a positive ``size_ft``.
A content edit that corrupts a shape ("sphere" → "spheer") or zeroes a
size ("fireball" 20 ft → 0) would make the server's ``_extract_aoe_area``
silently stop treating the spell as an AoE — caught here as drift.

The server-side authority is ``app/routes/tabletop_routes.py``:

    _AOE_SHAPE_SET = frozenset(
        {"sphere", "cone", "line", "cube", "self_sphere", "self_cube"}
    )

    def _extract_aoe_area(spell):
        # first action whose area.shape in _AOE_SHAPE_SET and size_ft > 0

That module imports ``fastapi`` so it can't be imported by the harness
locally; we replicate the frozenset here (same approach the Phase 2E/2F
concentration/buff registries take) and assert the catalog stays in lock
step with it. If a new shape is added to the catalog, this test fails
until the shape is added to BOTH the server set and ``_RAW_SHAPES`` here —
that lock-step failure is the point.

Pure-Python: imports the catalog loader directly, no HTTP / WS fixtures
(same pattern as ``test_spell_catalog_range.py``). The HTTP
``/place_aoe`` geometry test (targets inside the shape get the broadcast,
targets outside don't) is a filed follow-up — it needs map + token
positioning, which is materially more setup than this content gate.
"""
from __future__ import annotations

from .spell_catalog import load_all_spells

# Mirror of ``tabletop_routes._AOE_SHAPE_SET``. Kept in lock step by the
# count assertion below — see module docstring.
_RAW_SHAPES = frozenset(
    {"sphere", "cone", "line", "cube", "self_sphere", "self_cube"}
)

# The 27 SRD spells that declare a real AoE shape today. A drop below
# this count means a shape or size was zeroed out; a rise means a new
# AoE spell landed without updating this gate. Either way: investigate.
_EXPECTED_AOE_COUNT = 27


def _first_aoe_area(spell: dict) -> tuple[str, float, float] | None:
    """Return ``(shape, size_ft, secondary_ft)`` for the first action
    whose ``area.shape`` is non-empty, else ``None``. Mirrors the
    server's ``_extract_aoe_area`` selection (first matching action),
    but DOES NOT pre-filter on the shape set — so a corrupted shape
    surfaces here as a failure instead of being silently skipped.
    """
    for action in spell.get("actions") or []:
        area = action.get("area") or {}
        shape = (area.get("shape") or "").strip()
        if shape:
            size = area.get("size_ft") or 0
            secondary = area.get("secondary_ft") or 0
            return (shape, float(size), float(secondary))
    return None


def test_every_aoe_spell_has_a_valid_raw_shape_and_size():
    """Every catalog spell that declares an AoE shape uses a RAW-valid
    shape with a positive size; an unknown shape or zeroed size fails."""
    spells = load_all_spells()
    failures: list[str] = []
    aoe_count = 0
    for spell in spells:
        slug = spell.get("slug") or spell.get("_slug") or "?"
        found = _first_aoe_area(spell)
        if found is None:
            continue
        shape, size, secondary = found
        aoe_count += 1

        if shape not in _RAW_SHAPES:
            failures.append(
                f"{slug}: shape {shape!r} not in RAW set {sorted(_RAW_SHAPES)} "
                f"(typo / drift, or a new shape that must be added to BOTH "
                f"tabletop_routes._AOE_SHAPE_SET and this test's _RAW_SHAPES)"
            )
            continue
        if size <= 0:
            failures.append(
                f"{slug}: shape {shape!r} has non-positive size_ft {size!r} — "
                f"_extract_aoe_area would silently skip this spell"
            )
        # A line declares its width in secondary_ft; the one RAW line
        # spell (lightning-bolt) carries a positive secondary width.
        if shape == "line" and secondary <= 0:
            failures.append(
                f"{slug}: line shape has non-positive secondary_ft {secondary!r} "
                f"(width) — a line with no width is malformed"
            )

    assert aoe_count == _EXPECTED_AOE_COUNT, (
        f"found {aoe_count} AoE-shaped spells; expected {_EXPECTED_AOE_COUNT}. "
        f"A drop means a shape/size was zeroed (drift); a rise means a new "
        f"AoE spell landed — update _EXPECTED_AOE_COUNT and confirm the new "
        f"shape is in _RAW_SHAPES + tabletop_routes._AOE_SHAPE_SET."
    )
    assert not failures, (
        f"{len(failures)} AoE-shape failures (content drift):\n  "
        + "\n  ".join(failures)
    )


def test_aoe_shape_set_covers_every_shape_in_use():
    """The catalog uses every shape in ``_RAW_SHAPES`` at least once
    (no dead entries) and no shape outside it — a two-way lock-step
    check between the catalog and the server's accepted shape set."""
    spells = load_all_spells()
    shapes_in_use: set[str] = set()
    for spell in spells:
        found = _first_aoe_area(spell)
        if found is not None:
            shapes_in_use.add(found[0])

    unknown = shapes_in_use - _RAW_SHAPES
    assert not unknown, (
        f"catalog uses shapes outside the RAW set: {sorted(unknown)} — "
        f"add to _RAW_SHAPES + tabletop_routes._AOE_SHAPE_SET or fix the typo."
    )
    missing = _RAW_SHAPES - shapes_in_use
    assert not missing, (
        f"_RAW_SHAPES declares shapes no catalog spell uses: {sorted(missing)} — "
        f"a spell that used them may have been removed or had its shape zeroed."
    )
