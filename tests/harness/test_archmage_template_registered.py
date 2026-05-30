"""v2.97.74 — Archmage TokenTemplate registered in the demo.

The SRD Archmage (CR 12, Lv 18 spellcaster) ships at
``app/data/local/dnd5e/monsters/archmage.json`` and lists Banishment
among its 4th-level spells. v2.97.74 registers it as a demo
TokenTemplate so it's available to drag-spawn for set-piece
encounters and to demonstrate the Banishment cast-loop on the
caster side (the spell list now has both a player-side known entry
on Caelan and a server-side caster with the L4 slots to actually
cast it).

Test:
- Fetch the campaign's templates list.
- Assert the Archmage template exists with the expected name.
- The minimal sheet structure points at the ``archmage`` slug for
  SRD resolution.
"""
from .conftest import CAMPAIGN_ID


async def test_archmage_template_is_registered(gm_client):
    """The demo seed should register an Archmage TokenTemplate."""
    r = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/templates")
    assert r.status_code == 200, r.text
    templates = r.json()
    archmage = next(
        (t for t in templates
         if (t.get("name") or "").lower() == "archmage"),
        None,
    )
    assert archmage is not None, (
        f"Archmage template not found in campaign templates; "
        f"got names={[t.get('name') for t in templates]}"
    )
    # Sheet should point at the archmage slug for SRD resolution.
    sheet = archmage.get("sheet") or {}
    assert (sheet.get("monster_slug") or "").lower() == "archmage", (
        f"expected sheet.monster_slug='archmage'; got {sheet}"
    )
    assert archmage.get("template") == "dnd5e"
