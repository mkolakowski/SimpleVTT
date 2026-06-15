"""v2.332.0 — "The Elemental Conclave" bundle (sixth stub bundle, expanded
to FOUR items for thematic completeness — one per element). Four SRD
elemental-control wondrous items shipped together as catalog-stub passives
in `_MAGIC_ITEM_PASSIVES`. Each has the same RAW shape: rare, no
attunement, action to summon + CHA-check-to-command the matching
elemental for 1 hour. Pure GM-narrated mechanics in v1.

Carriers — one per element:
  - Brazier of Commanding Fire Elementals (RAW DMG p.156) → Caelan
    (Devotion Paladin — sacred fire / divine wrath).
  - Bowl of Commanding Water Elementals (RAW DMG p.156) → Rowan (Hunter
    Ranger — outdoorsman commanding nature's flowing forces).
  - Censer of Controlling Air Elementals (RAW DMG p.157) → Seraphine
    (Vengeance Paladin — wind / wrath chasing evil through the heavens).
  - Stone of Controlling Earth Elementals (RAW DMG p.207) → Krieger
    (Half-Orc Barbarian — earthy raw strength completes the four corners).

Smoke tests verify each item is reachable via `/sheet-json` by `_slug`.
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


async def test_caelan_carries_brazier(gm_client, roster):
    """Brazier of Commanding Fire Elementals is seeded on Sir Caelan
    Lightbringer (Devotion Paladin) — equipped=True, no attunement."""
    caelan = roster["Sir Caelan Lightbringer"]
    inv = await _carrier_inv(gm_client, caelan["id"])
    brazier = _find_by_slug(inv, "brazier-of-commanding-fire-elementals")
    assert brazier is not None, (
        f"Caelan should carry the Brazier; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert brazier.get("name") == "Brazier of Commanding Fire Elementals"
    assert brazier.get("equipped") is True
    assert not brazier.get("attuned"), (
        f"Brazier is no-attunement (RAW); got: {brazier!r}"
    )


async def test_rowan_carries_bowl(gm_client, roster):
    """Bowl of Commanding Water Elementals is seeded on Rowan Quickbow
    (Hunter Ranger) — equipped=True, no attunement."""
    rowan = roster["Rowan Quickbow"]
    inv = await _carrier_inv(gm_client, rowan["id"])
    bowl = _find_by_slug(inv, "bowl-of-commanding-water-elementals")
    assert bowl is not None, (
        f"Rowan should carry the Bowl; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert bowl.get("name") == "Bowl of Commanding Water Elementals"
    assert bowl.get("equipped") is True
    assert not bowl.get("attuned"), (
        f"Bowl is no-attunement (RAW); got: {bowl!r}"
    )


async def test_seraphine_carries_censer(gm_client, roster):
    """Censer of Controlling Air Elementals is seeded on Dame Seraphine
    Vael (Vengeance Paladin) — equipped=True, no attunement."""
    seraphine = roster["Dame Seraphine Vael"]
    inv = await _carrier_inv(gm_client, seraphine["id"])
    censer = _find_by_slug(inv, "censer-of-controlling-air-elementals")
    assert censer is not None, (
        f"Seraphine should carry the Censer; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert censer.get("name") == "Censer of Controlling Air Elementals"
    assert censer.get("equipped") is True
    assert not censer.get("attuned"), (
        f"Censer is no-attunement (RAW); got: {censer!r}"
    )


async def test_krieger_carries_stone(gm_client, roster):
    """Stone of Controlling Earth Elementals is seeded on Krieger Stonefist
    (Half-Orc Barbarian) — equipped=True, no attunement."""
    krieger = roster["Krieger Stonefist"]
    inv = await _carrier_inv(gm_client, krieger["id"])
    stone = _find_by_slug(inv, "stone-of-controlling-earth-elementals")
    assert stone is not None, (
        f"Krieger should carry the Stone; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert stone.get("name") == "Stone of Controlling Earth Elementals"
    assert stone.get("equipped") is True
    assert not stone.get("attuned"), (
        f"Stone is no-attunement (RAW); got: {stone!r}"
    )
