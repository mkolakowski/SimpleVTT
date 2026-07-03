"""Capture the live demo maps' editor state back into paste-ready seed snippets.

The five leveled demo campaigns (L3/L5/L9/L13/L18) are seeded from the ``map``
dicts + ``party_pos``/``npc_pos`` lists in ``app/demo_campaigns.py``. When you
tweak those maps in the in-app editor (move lights, redraw walls, reshape
terrain, reposition tokens, change ambient/fog), the changes live only in the
database and are wiped on the next demo reset. This script reads the current DB
state of each leveled campaign's active map and prints a **paste-ready block**
of Python literals — the element keys for the spec's ``map`` dict plus the
``party_pos``/``npc_pos`` token lists — so you (or the assistant) can drop them
into ``app/demo_campaigns.py`` and make the layout permanent.

It reads only the DB (no mutations) and emits to stdout.

Run it inside the app container (which has the app package + DB access) by
piping this file into its Python — the wrapper does exactly that:

    scripts/capture_demo_maps.sh

or directly:

    docker compose exec -T app python - < scripts/capture_demo_maps.py

The flagship "Sundered Tavern" (campaign 1) is intentionally skipped — it's the
harness playground (tests mutate it) and it's seeded separately in
``app/demo_seed.py``.
"""
from app.database import SessionLocal
from app.models import Campaign, Map, Token

# (spec var in app/demo_campaigns.py, campaign name) for the five leveled demos.
LEVELED = [
    ("_GOBLIN_WARRENS", "Demo L3: The Goblin Warrens"),
    ("_TIDEWRACKED_CATACOMBS", "Demo L5: The Tide-Wracked Catacombs"),
    ("_STORM_SALTMARSH", "Demo L9: Storm Over Saltmarsh"),
    ("_SHADOWFELL_SPIRE", "Demo L13: The Shadowfell Spire"),
    ("_DRAGONS_APOTHEOSIS", "Demo L18: The Dragon's Apotheosis"),
]

# Element JSON columns emitted in the spec's map dict (order = readable output).
_ELEMENT_COLS = ["walls", "lights", "terrain", "hotspots", "gm_pins", "labels"]


def _num(v):
    """Whole floats → ints (coords/radii read back as e.g. 293.0); keep the rest."""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _py(v):
    """Format a JSON value as a Python literal (double-quoted strings,
    True/False/None) matching the seed file's style."""
    if isinstance(v, bool):
        return "True" if v else "False"
    if v is None:
        return "None"
    v = _num(v)
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_py(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join('"%s": %s' % (k, _py(x)) for k, x in v.items()) + "}"
    return repr(v)


def _emit_list(key, items, indent="            "):
    """One record per line, so a wall/light list stays diff-friendly."""
    if not items:
        return
    print(f'{indent}"{key}": [')
    for it in items:
        print(f"{indent}    {_py(it)},")
    print(f"{indent}],")


def main():
    db = SessionLocal()
    try:
        for var, name in LEVELED:
            camp = db.query(Campaign).filter(Campaign.name == name).first()
            if not camp:
                print(f"# !! campaign not found: {name}")
                continue
            m = (db.query(Map).filter(Map.id == camp.active_map_id).first()
                 if camp.active_map_id else None)
            if not m:
                print(f"# !! no active map for {name}")
                continue
            print("    # " + "=" * 66)
            print(f"    # {name}  (spec {var}, campaign {camp.id}, map {m.id})")
            print("    # Paste the keys below into this spec's \"map\" dict, and the")
            print("    # party_pos / npc_pos lists at the spec's top level.")
            print("    # " + "=" * 66)
            # Map-level settings the editor can change.
            gt = getattr(m.grid_type, "value", m.grid_type) or "square"
            if gt == "none":
                print('            "gridless": True,')
            if (m.ambient_light or "bright") != "bright":
                print(f'            "ambient_light": {_py(m.ambient_light)},')
            if bool(getattr(m, "fog_enabled", False)):
                dyn = bool(getattr(m, "fog_dynamic", False))
                print('            "fog_enabled": True,'
                      + (' "fog_dynamic": True,' if dyn else ""))
            _emit_list("fog_revealed", list(getattr(m, "fog_revealed", None) or []))
            for col in _ELEMENT_COLS:
                _emit_list(col, list(getattr(m, col, None) or []))
            # Token positions, split by team + ordered by id (= party / npc
            # creation order in _seed_one), emitted as (x, y) tuples.
            toks = (db.query(Token).filter(Token.map_id == m.id)
                    .order_by(Token.team, Token.id).all())
            party = [(int(_num(t.x)), int(_num(t.y))) for t in toks if t.team == "hero"]
            npc = [(int(_num(t.x)), int(_num(t.y))) for t in toks if t.team == "villain"]
            if party:
                print('    "party_pos": [' + ", ".join(f"({x}, {y})" for x, y in party) + "],")
            if npc:
                print('    "npc_pos": [' + ", ".join(f"({x}, {y})" for x, y in npc) + "],")
            print()
    finally:
        db.close()


if __name__ == "__main__":
    main()
