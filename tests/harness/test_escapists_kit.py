"""v2.336.0 — "The Escapist's Kit" bundle (ninth stub bundle). Three SRD
escape / evasion wondrous items shipped together as catalog-stub passives.
Each has a 1/day-cast or one-shot mechanic (GM-narrated in v1). Seeded on
thematic carriers:

  - Wind Fan (RAW DMG p.213, uncommon, no attunement) → Kael Brightleaf
    (Wood Elf Open Hand Monk — a disengage gust for an acrobat).
  - Cape of the Mountebank (RAW DMG p.157, rare, no attunement) → Lyra
    Sunstrider (College of Lore Bard — a showman's vanish-and-reappear).
  - Dust of Disappearance (RAW DMG p.166, uncommon, no attunement,
    consumable) → Quan Reelstep (Drunken Master Monk — a vanishing
    bolthole).

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


async def test_kael_carries_wind_fan(gm_client, roster):
    """Wind Fan is seeded on Kael Brightleaf (Monk) — equipped, no
    attunement."""
    kael = roster["Kael Brightleaf"]
    inv = await _carrier_inv(gm_client, kael["id"])
    fan = _find_by_slug(inv, "wind-fan")
    assert fan is not None, (
        f"Kael should carry a Wind Fan; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert fan.get("name") == "Wind Fan"
    assert fan.get("equipped") is True
    assert not fan.get("attuned"), f"Wind Fan is no-attunement (RAW); got: {fan!r}"


async def test_lyra_carries_cape_of_the_mountebank(gm_client, roster):
    """Cape of the Mountebank is seeded on Lyra Sunstrider (Bard) —
    equipped, no attunement."""
    lyra = roster["Lyra Sunstrider"]
    inv = await _carrier_inv(gm_client, lyra["id"])
    cape = _find_by_slug(inv, "cape-of-the-mountebank")
    assert cape is not None, (
        f"Lyra should carry a Cape of the Mountebank; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert cape.get("name") == "Cape of the Mountebank"
    assert cape.get("equipped") is True
    assert not cape.get("attuned"), f"Cape is no-attunement (RAW); got: {cape!r}"


async def test_quan_carries_dust_of_disappearance(gm_client, roster):
    """Dust of Disappearance is seeded on Quan Reelstep (Drunken Master
    Monk) — equipped, no attunement, consumable=True (used up on a throw)."""
    quan = roster["Quan Reelstep"]
    inv = await _carrier_inv(gm_client, quan["id"])
    dust = _find_by_slug(inv, "dust-of-disappearance")
    assert dust is not None, (
        f"Quan should carry Dust of Disappearance; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert dust.get("name") == "Dust of Disappearance"
    assert dust.get("equipped") is True
    assert not dust.get("attuned"), f"Dust is no-attunement (RAW); got: {dust!r}"
    assert dust.get("consumable") is True, (
        f"Dust of Disappearance is consumable (RAW one-shot); got: {dust!r}"
    )
