"""v2.331.0 — "The Trickster's Pouch" bundle (fifth stub bundle after the
Wayfarer's / Inventor's / Captor's / Engineer's collections): three SRD
random-effect wondrous items shipped together as catalog-stub passives in
`_MAGIC_ITEM_PASSIVES`. Each has GM-narrated random-table mechanics; the
catalog row exists so the slug counts in the audit. Seeded on thematic
carriers:

  - Bag of Beans (RAW DMG p.152, rare, no attunement) → Mira Greenleaf
    (Wood Elf Druid — experimenting with strange seeds fits her
    naturalist aesthetic).
  - Bag of Tricks (RAW DMG p.154, uncommon, no attunement) → Brakka
    Wildmane (Goliath Beast Barbarian — summoning animal allies fits
    Path of the Beast).
  - Feather Token (RAW DMG p.188, rare, no attunement) → Quan Reelstep
    (Drunken Master Monk — featherweight trick token fits acrobatic /
    improvised aesthetic).

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


async def test_mira_carries_bag_of_beans(gm_client, roster):
    """Bag of Beans is seeded on Mira Greenleaf (Druid) — equipped=True,
    no attunement."""
    mira = roster["Mira Greenleaf"]
    inv = await _carrier_inv(gm_client, mira["id"])
    beans = _find_by_slug(inv, "bag-of-beans")
    assert beans is not None, (
        f"Mira should carry a Bag of Beans; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert beans.get("name") == "Bag of Beans"
    assert beans.get("type") == "magic"
    assert beans.get("equipped") is True
    assert not beans.get("attuned"), (
        f"Bag of Beans is no-attunement (RAW); got: {beans!r}"
    )


async def test_brakka_carries_bag_of_tricks(gm_client, roster):
    """Bag of Tricks is seeded on Brakka Wildmane (Goliath Beast Barbarian) —
    equipped=True, no attunement."""
    brakka = roster["Brakka Wildmane"]
    inv = await _carrier_inv(gm_client, brakka["id"])
    tricks = _find_by_slug(inv, "bag-of-tricks")
    assert tricks is not None, (
        f"Brakka should carry a Bag of Tricks; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert tricks.get("name") == "Bag of Tricks"
    assert tricks.get("type") == "magic"
    assert tricks.get("equipped") is True
    assert not tricks.get("attuned"), (
        f"Bag of Tricks is no-attunement (RAW); got: {tricks!r}"
    )


async def test_quan_carries_feather_token(gm_client, roster):
    """Feather Token is seeded on Quan Reelstep (Drunken Master Monk) —
    equipped=True, no attunement, consumable=True (it vanishes on use)."""
    quan = roster["Quan Reelstep"]
    inv = await _carrier_inv(gm_client, quan["id"])
    token = _find_by_slug(inv, "feather-token")
    assert token is not None, (
        f"Quan should carry a Feather Token; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert token.get("name") == "Feather Token"
    assert token.get("type") == "magic"
    assert token.get("equipped") is True
    assert not token.get("attuned"), (
        f"Feather Token is no-attunement (RAW); got: {token!r}"
    )
    # Feather Token is consumed after use per RAW.
    assert token.get("consumable") is True, (
        f"Feather Token should be consumable (RAW); got: {token!r}"
    )
