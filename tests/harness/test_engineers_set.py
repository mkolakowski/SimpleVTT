"""v2.330.0 — "The Engineer's Set" bundle (fourth stub bundle after the
v2.327.0 Wayfarer's Trio + v2.328.0 Inventor's Trio + v2.329.0 Captor's
Cache): three mechanical-contraption SRD wondrous items shipped together as
catalog-stub passives in `_MAGIC_ITEM_PASSIVES`. Each has GM-narrated
mechanics; the catalog row exists so the slug counts in the audit. Cube
of Force is the first stub item to declare `requires_attunement: True`
(legal — the gate is descriptive in v1 since the stub has no other
payload). Seeded on thematic carriers:

  - Apparatus of the Crab (RAW DMG p.151, legendary, no attunement) →
    Kael (Wood Elf Monk — mechanical-tinker contraption for a
    contemplative hermit explorer).
  - Cube of Force (RAW DMG p.165, rare, attunement) → Zara (Tiefling
    Sorcerer — defensive arcane field for a frail-frame blaster).
  - Portable Hole (RAW DMG p.185, rare, no attunement) → Lyra (College
    of Lore Bard — hidden stash for performance gear + secret
    manuscripts).

Smoke tests verify each item is reachable via `/sheet-json` by `_slug`.
The Cube of Force test additionally asserts `attuned: True` to confirm
the attunement contract loads correctly through the seed.
"""
from .conftest import CAMPAIGN_ID


async def _carrier_inv(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return list((resp.json().get("sheet") or {}).get("inventory") or [])


def _find_by_slug(inv, slug):
    for it in inv:
        if isinstance(it, dict) and it.get("_slug") == slug:
            return it
    return None


async def test_kael_carries_apparatus_of_the_crab(gm_client, roster):
    """Apparatus of the Crab is seeded on Kael Brightleaf (Monk) —
    equipped=True, no attunement."""
    kael = roster["Kael Brightleaf"]
    inv = await _carrier_inv(gm_client, kael["id"])
    apparatus = _find_by_slug(inv, "apparatus-of-the-crab")
    assert apparatus is not None, (
        f"Kael should carry Apparatus of the Crab; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert apparatus.get("name") == "Apparatus of the Crab"
    assert apparatus.get("type") == "magic"
    assert apparatus.get("equipped") is True
    assert not apparatus.get("attuned"), (
        f"Apparatus is no-attunement (RAW); got: {apparatus!r}"
    )


async def test_zara_carries_cube_of_force(gm_client, roster):
    """Cube of Force is seeded on Zara Emberfire (Sorcerer) — equipped=True,
    attuned=True (the first stub bundle item to require attunement)."""
    zara = roster["Zara Emberfire"]
    inv = await _carrier_inv(gm_client, zara["id"])
    cube = _find_by_slug(inv, "cube-of-force")
    assert cube is not None, (
        f"Zara should carry a Cube of Force; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert cube.get("name") == "Cube of Force"
    assert cube.get("type") == "magic"
    assert cube.get("equipped") is True
    # Cube of Force REQUIRES attunement (RAW); seed declares attuned=True.
    assert cube.get("attuned") is True, (
        f"Cube of Force requires attunement (RAW); got: {cube!r}"
    )


async def test_lyra_carries_portable_hole(gm_client, roster):
    """Portable Hole is seeded on Lyra Sunstrider (Bard) — equipped=True,
    no attunement."""
    lyra = roster["Lyra Sunstrider"]
    inv = await _carrier_inv(gm_client, lyra["id"])
    hole = _find_by_slug(inv, "portable-hole")
    assert hole is not None, (
        f"Lyra should carry a Portable Hole; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert hole.get("name") == "Portable Hole"
    assert hole.get("type") == "magic"
    assert hole.get("equipped") is True
    assert not hole.get("attuned"), (
        f"Portable Hole is no-attunement (RAW); got: {hole!r}"
    )
