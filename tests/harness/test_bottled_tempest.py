"""v2.337.0 — "The Bottled Tempest" bundle (tenth stub bundle). Three SRD
sealed-vessel summon/release wondrous items shipped together as catalog-stub
passives. Each releases something (a genie, a smoke cloud, an elemental)
GM-narrated in v1. Seeded on thematic carriers:

  - Efreeti Bottle (RAW DMG p.167, very rare, no attunement) → Zara
    Emberfire (Tiefling Draconic Sorcerer — a fire-genie bottle).
  - Eversmoking Bottle (RAW DMG p.168, uncommon, no attunement) → Pip
    Quickfingers (Halfling Rogue — instant smoke-screen escape).
  - Elemental Gem (RAW DMG p.167, uncommon, no attunement, consumable) →
    Brakka Wildmane (Goliath Beast Barbarian — an elemental ally).

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


async def test_zara_carries_efreeti_bottle(gm_client, roster):
    """Efreeti Bottle is seeded on Zara Emberfire (Sorcerer) — equipped, no
    attunement."""
    zara = roster["Zara Emberfire"]
    inv = await _carrier_inv(gm_client, zara["id"])
    bottle = _find_by_slug(inv, "efreeti-bottle")
    assert bottle is not None, (
        f"Zara should carry an Efreeti Bottle; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert bottle.get("name") == "Efreeti Bottle"
    assert bottle.get("equipped") is True
    assert not bottle.get("attuned"), f"Efreeti Bottle is no-attunement; got: {bottle!r}"


async def test_pip_carries_eversmoking_bottle(gm_client, roster):
    """Eversmoking Bottle is seeded on Pip Quickfingers (Rogue) — equipped,
    no attunement."""
    pip = roster["Pip Quickfingers"]
    inv = await _carrier_inv(gm_client, pip["id"])
    bottle = _find_by_slug(inv, "eversmoking-bottle")
    assert bottle is not None, (
        f"Pip should carry an Eversmoking Bottle; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert bottle.get("name") == "Eversmoking Bottle"
    assert bottle.get("equipped") is True
    assert not bottle.get("attuned"), f"Eversmoking Bottle is no-attunement; got: {bottle!r}"


async def test_brakka_carries_elemental_gem(gm_client, roster):
    """Elemental Gem is seeded on Brakka Wildmane (Beast Barbarian) —
    equipped, no attunement, consumable=True (crushed on use)."""
    brakka = roster["Brakka Wildmane"]
    inv = await _carrier_inv(gm_client, brakka["id"])
    gem = _find_by_slug(inv, "elemental-gem")
    assert gem is not None, (
        f"Brakka should carry an Elemental Gem; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert gem.get("name") == "Elemental Gem"
    assert gem.get("equipped") is True
    assert not gem.get("attuned"), f"Elemental Gem is no-attunement; got: {gem!r}"
    assert gem.get("consumable") is True, (
        f"Elemental Gem is consumable (RAW: destroyed on use); got: {gem!r}"
    )
