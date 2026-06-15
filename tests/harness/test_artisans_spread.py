"""v2.333.0 — "The Artisan's Spread" bundle (seventh stub bundle). Three
SRD craft/utility wondrous items shipped together as catalog-stub
passives. Each has distinct GM-narrated mechanics (10-charge sonic
unlocker, paint-becomes-real pots, multi-item embroidered robe).
Seeded on thematic carriers:

  - Chime of Opening (RAW DMG p.158, rare, no attunement) → Pip
    Quickfingers (Halfling Rogue scout — silent unlock chimes fit her
    Wand of Secrets + Slippers toolkit).
  - Marvelous Pigments (RAW DMG p.183, very rare, no attunement) →
    Thalindra Moonwhisper (Wizard Evoker — Pigments + Universal Solvent
    pair for a "create then dissolve" alchemy demo).
  - Robe of Useful Items (RAW DMG p.195, uncommon, no attunement) →
    Magnus Hexbinder (Fiend-pact Warlock — embroidered patches fit his
    arcane scholar aesthetic).

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


async def test_pip_carries_chime_of_opening(gm_client, roster):
    """Chime of Opening is seeded on Pip Quickfingers (Rogue) —
    equipped=True, no attunement."""
    pip = roster["Pip Quickfingers"]
    inv = await _carrier_inv(gm_client, pip["id"])
    chime = _find_by_slug(inv, "chime-of-opening")
    assert chime is not None, (
        f"Pip should carry a Chime of Opening; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert chime.get("name") == "Chime of Opening"
    assert chime.get("equipped") is True
    assert not chime.get("attuned"), (
        f"Chime is no-attunement (RAW); got: {chime!r}"
    )


async def test_thalindra_carries_marvelous_pigments(gm_client, roster):
    """Marvelous Pigments are seeded on Thalindra Moonwhisper (Wizard) —
    equipped=True, no attunement."""
    thalindra = roster["Thalindra Moonwhisper"]
    inv = await _carrier_inv(gm_client, thalindra["id"])
    pigments = _find_by_slug(inv, "marvelous-pigments")
    assert pigments is not None, (
        f"Thalindra should carry Marvelous Pigments; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert pigments.get("name") == "Marvelous Pigments"
    assert pigments.get("equipped") is True
    assert not pigments.get("attuned"), (
        f"Marvelous Pigments are no-attunement (RAW); got: {pigments!r}"
    )


async def test_magnus_carries_robe_of_useful_items(gm_client, roster):
    """Robe of Useful Items is seeded on Magnus Hexbinder (Warlock) —
    equipped=True, no attunement."""
    magnus = roster["Magnus Hexbinder"]
    inv = await _carrier_inv(gm_client, magnus["id"])
    robe = _find_by_slug(inv, "robe-of-useful-items")
    assert robe is not None, (
        f"Magnus should carry a Robe of Useful Items; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert robe.get("name") == "Robe of Useful Items"
    assert robe.get("equipped") is True
    assert not robe.get("attuned"), (
        f"Robe of Useful Items is no-attunement (RAW); got: {robe!r}"
    )
