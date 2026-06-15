"""v2.344.0 — "The Armory's Remainder" bulk-stub push. The last 12
mechanically-rich SRD magic items shipped as catalog-stub passives (one
`_MAGIC_ITEM_PASSIVES` row each, registered by the remainder `setdefault`
loop in tabletop_routes.py), seeded as inert spare loot on thematic
carriers (the v2.344.0 block appended to `_vault_loot` in demo_seed.py).
Each item is flagged for future dedicated wiring; mechanics are
GM-narrated in v1. This layer guards the catalog rows + seeds against
regression and closes the magic-item content tail.

Parametrized by carrier: each test fetches the carrier's `/sheet-json`
inventory once and asserts every expected remainder slug is present. The
full (carrier → slugs) map mirrors the seed; a missing slug names itself
in the failure message.
"""
import pytest

from .conftest import CAMPAIGN_ID


# carrier display-name → list of remainder stub slugs seeded on them
# (mirrors the v2.344.0 block in demo_seed.py `_vault_loot`).
_REMAINDER_BY_CARRIER = {
    "Thalindra Moonwhisper": ["bead-of-force", "staff-of-the-magi"],
    "Krieger Stonefist": ["berserker-axe"],
    "Garrik Ironside": ["hammer-of-thunderbolts"],
    "Rowan Quickbow": ["oathbow"],
    "Lyra Sunstrider": ["pipes-of-haunting"],
    "Sir Caelan Lightbringer": ["sword-of-wounding"],
    "Mira Greenleaf": [
        "trident-of-fish-command", "staff-of-the-python",
        "staff-of-the-woodlands",
    ],
    "Magnus Hexbinder": ["staff-of-striking", "staff-of-withering"],
}


@pytest.mark.parametrize("carrier_name", sorted(_REMAINDER_BY_CARRIER))
async def test_armorys_remainder_seeded(gm_client, roster, carrier_name):
    """Each carrier's `/sheet-json` inventory contains every remainder stub
    slug seeded on them — proves the remainder catalog rows + seeds loaded."""
    pc = roster[carrier_name]
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pc['id']}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    inv = (resp.json().get("sheet") or {}).get("inventory") or []
    present = {
        it.get("_slug") for it in inv if isinstance(it, dict)
    }
    expected = _REMAINDER_BY_CARRIER[carrier_name]
    missing = [s for s in expected if s not in present]
    assert not missing, (
        f"{carrier_name} is missing remainder stub slugs {missing}; "
        f"present slugs: {sorted(s for s in present if s)}"
    )
