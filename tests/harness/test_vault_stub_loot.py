"""v2.342.0 — "The Vault" bulk-stub push. 60 remaining pure-narrative SRD
magic items shipped as catalog-stub passives (one `_MAGIC_ITEM_PASSIVES`
row each, registered by the bulk-stub loop in tabletop_routes.py), seeded
as inert spare loot on thematic carriers (the `_VAULT_STUB_LOOT` block in
demo_seed.py). Mechanics are GM-narrated in v1; this layer just guards the
catalog rows + seeds against regression.

Parametrized by carrier (15 PCs): each test fetches the carrier's
`/sheet-json` inventory once and asserts every expected Vault slug is
present. The full (carrier → slugs) map mirrors the seed; a missing slug
names itself in the failure message.
"""
import pytest

from .conftest import CAMPAIGN_ID


# carrier display-name → list of Vault stub slugs seeded on them (mirrors
# demo_seed.py `_VAULT_STUB_LOOT`).
_VAULT_BY_CARRIER = {
    "Pip Quickfingers": [
        "dust-of-sneezing-and-choking", "lantern-of-revealing",
        "oil-of-slipperiness", "potion-of-poison", "ring-of-invisibility",
    ],
    "Thalindra Moonwhisper": [
        "amulet-of-the-planes", "helm-of-teleportation", "manual-of-golems",
        "ring-of-spell-storing",
    ],
    "Brother Tavik Stonebrow": [
        "helm-of-comprehending-languages", "necklace-of-prayer-beads",
        "restorative-ointment",
    ],
    "Sir Caelan Lightbringer": [
        "arrow-catching-shield", "defender", "instant-fortress",
        "plate-armor-of-etherealness", "talisman-of-pure-good",
    ],
    "Lyra Sunstrider": [
        "dancing-sword", "deck-of-illusions", "philter-of-love",
        "robe-of-scintillating-colors",
    ],
    "Mira Greenleaf": [
        "figurine-of-wondrous-power", "horseshoes-of-a-zephyr",
        "oil-of-etherealness", "ring-of-animal-influence",
    ],
    "Garrik Ironside": [
        "adamantine-armor", "handy-haversack", "immovable-rod",
        "mithral-armor", "oil-of-sharpness",
    ],
    "Kael Brightleaf": [
        "dust-of-dryness", "gloves-of-missile-snaring", "ring-of-evasion",
        "rope-of-entanglement",
    ],
    "Zara Emberfire": [
        "circlet-of-blasting", "orb-of-dragonkind",
        "ring-of-djinni-summoning", "ring-of-shooting-stars",
    ],
    "Krieger Stonefist": [
        "horn-of-valhalla", "ring-of-regeneration", "rod-of-lordly-might",
        "sphere-of-annihilation",
    ],
    "Rowan Quickbow": [
        "animated-shield", "arrow-of-slaying", "efficient-quiver",
        "horseshoes-of-speed",
    ],
    "Magnus Hexbinder": [
        "deck-of-many-things", "medallion-of-thoughts", "ring-of-telekinesis",
        "rod-of-absorption", "talisman-of-ultimate-evil",
    ],
    "Dame Seraphine Vael": [
        "ring-of-three-wishes", "rod-of-rulership",
        "shield-of-missile-attraction",
    ],
    "Brakka Wildmane": [
        "dimensional-shackles", "pipes-of-the-sewers",
    ],
    "Quan Reelstep": [
        "luck-blade", "rod-of-security", "talisman-of-the-sphere",
        "well-of-many-worlds",
    ],
}


@pytest.mark.parametrize("carrier_name", sorted(_VAULT_BY_CARRIER))
async def test_vault_stub_loot_seeded(gm_client, roster, carrier_name):
    """Each carrier's `/sheet-json` inventory contains every Vault stub slug
    seeded on them — proves the bulk-stub catalog rows + seeds loaded."""
    pc = roster[carrier_name]
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pc['id']}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    inv = (resp.json().get("sheet") or {}).get("inventory") or []
    present = {
        it.get("_slug") for it in inv if isinstance(it, dict)
    }
    expected = _VAULT_BY_CARRIER[carrier_name]
    missing = [s for s in expected if s not in present]
    assert not missing, (
        f"{carrier_name} is missing Vault stub slugs {missing}; "
        f"present slugs: {sorted(s for s in present if s)}"
    )
