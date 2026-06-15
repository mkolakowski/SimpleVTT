"""v2.329.0 — "The Captor's Cache" bundle (third stub bundle after the
v2.327.0 Wayfarer's Trio + v2.328.0 Inventor's Trio): three SRD capture /
trap wondrous items shipped together as catalog-stub passives in
`_MAGIC_ITEM_PASSIVES`. Each has GM-narrated mechanics; the catalog row
exists so the slug counts in the audit. Seeded on thematic carriers:

  - Iron Bands of Binding (RAW DMG p.176, rare, no attunement) → Krieger
    (Half-Orc Barbarian — brutal restraining throw).
  - Iron Flask (RAW DMG p.178, legendary, no attunement) → Magnus
    Hexbinder (Fiend-pact Warlock — dark-magic creature capture).
  - Mirror of Life Trapping (RAW DMG p.181, very rare, no attunement) →
    Mira Greenleaf (Wood Elf Druid — cataloguing wild beasts and spirits).

Smoke tests verify each item is reachable via `/sheet-json` by `_slug`.
Future mechanical extensions land in their own dedicated test files.
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


async def test_krieger_carries_iron_bands_of_binding(gm_client, roster):
    """Iron Bands of Binding is seeded on Krieger Stonefist (Barbarian) —
    equipped=True, no attunement."""
    krieger = roster["Krieger Stonefist"]
    inv = await _carrier_inv(gm_client, krieger["id"])
    bands = _find_by_slug(inv, "iron-bands-of-binding")
    assert bands is not None, (
        f"Krieger should carry Iron Bands of Binding; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert bands.get("name") == "Iron Bands of Binding"
    assert bands.get("type") == "magic"
    assert bands.get("equipped") is True
    assert not bands.get("attuned"), (
        f"Iron Bands are no-attunement (RAW); got: {bands!r}"
    )


async def test_magnus_carries_iron_flask(gm_client, roster):
    """Iron Flask is seeded on Magnus Hexbinder (Warlock) — equipped=True,
    no attunement."""
    magnus = roster["Magnus Hexbinder"]
    inv = await _carrier_inv(gm_client, magnus["id"])
    flask = _find_by_slug(inv, "iron-flask")
    assert flask is not None, (
        f"Magnus should carry an Iron Flask; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert flask.get("name") == "Iron Flask"
    assert flask.get("type") == "magic"
    assert flask.get("equipped") is True
    assert not flask.get("attuned"), (
        f"Iron Flask is no-attunement (RAW); got: {flask!r}"
    )


async def test_mira_carries_mirror_of_life_trapping(gm_client, roster):
    """Mirror of Life Trapping is seeded on Mira Greenleaf (Druid) —
    equipped=True, no attunement."""
    mira = roster["Mira Greenleaf"]
    inv = await _carrier_inv(gm_client, mira["id"])
    mirror = _find_by_slug(inv, "mirror-of-life-trapping")
    assert mirror is not None, (
        f"Mira should carry a Mirror of Life Trapping; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert mirror.get("name") == "Mirror of Life Trapping"
    assert mirror.get("type") == "magic"
    assert mirror.get("equipped") is True
    assert not mirror.get("attuned"), (
        f"Mirror of Life Trapping is no-attunement (RAW); got: {mirror!r}"
    )
