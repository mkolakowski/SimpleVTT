"""v2.328.0 — "The Inventor's Trio" bundle (sequel to v2.327.0's Wayfarer's
Trio): three utility-themed SRD wondrous items shipped together as catalog-
stub passives in `_MAGIC_ITEM_PASSIVES`. Each has GM-narrated mechanics (no
save, damage, or buff to wire); the catalog row exists so the slug counts
in the SRD audit. Seeded on thematic carriers:

  - Decanter of Endless Water (RAW DMG p.161, uncommon, no attunement) →
    Tavik (Cleric — sacred-water vessel symbolism for a Life Domain
    healer).
  - Sovereign Glue (RAW DMG p.200, legendary, no attunement) → Garrik
    (Fighter, Soldier — improvised field-repair adhesive).
  - Universal Solvent (RAW DMG p.209, legendary, no attunement) →
    Thalindra (Wizard — alchemy / lab-experiment fits an Evoker scholar).

Smoke tests verify each item is reachable via `/sheet-json` by `_slug`.
Any future mechanical extension lands its own dedicated test file.
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


async def test_tavik_carries_decanter_of_endless_water(gm_client, roster):
    """Decanter of Endless Water is seeded on Brother Tavik Stonebrow
    (Cleric) — equipped=True, no attunement."""
    tavik = roster["Brother Tavik Stonebrow"]
    inv = await _carrier_inv(gm_client, tavik["id"])
    decanter = _find_by_slug(inv, "decanter-of-endless-water")
    assert decanter is not None, (
        f"Tavik should carry a Decanter of Endless Water; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert decanter.get("name") == "Decanter of Endless Water"
    assert decanter.get("type") == "magic"
    assert decanter.get("equipped") is True
    assert not decanter.get("attuned"), (
        f"Decanter is no-attunement (RAW); got: {decanter!r}"
    )


async def test_garrik_carries_sovereign_glue(gm_client, roster):
    """Sovereign Glue is seeded on Garrik Ironside (Fighter) — equipped=True,
    no attunement."""
    garrik = roster["Garrik Ironside"]
    inv = await _carrier_inv(gm_client, garrik["id"])
    glue = _find_by_slug(inv, "sovereign-glue")
    assert glue is not None, (
        f"Garrik should carry a Sovereign Glue; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert glue.get("name") == "Sovereign Glue"
    assert glue.get("type") == "magic"
    assert glue.get("equipped") is True
    assert not glue.get("attuned"), (
        f"Sovereign Glue is no-attunement (RAW); got: {glue!r}"
    )


async def test_thalindra_carries_universal_solvent(gm_client, roster):
    """Universal Solvent is seeded on Thalindra Moonwhisper (Wizard) —
    equipped=True, no attunement."""
    thalindra = roster["Thalindra Moonwhisper"]
    inv = await _carrier_inv(gm_client, thalindra["id"])
    solvent = _find_by_slug(inv, "universal-solvent")
    assert solvent is not None, (
        f"Thalindra should carry a Universal Solvent; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert solvent.get("name") == "Universal Solvent"
    assert solvent.get("type") == "magic"
    assert solvent.get("equipped") is True
    assert not solvent.get("attuned"), (
        f"Universal Solvent is no-attunement (RAW); got: {solvent!r}"
    )
