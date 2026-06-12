"""Phase 4 complex-spell deep-dive — homebrew handling ("Bless of Bahamut").

Every other Phase 4 deep-dive exercises an SRD spell that ships in the
catalog. This one proves the cast path works for a spell the GM *invents* —
content that has no JSON file and no catalog entry at all. The contract
lives at tabletop_routes.py:18164-18177: `/cast_spell` reads the inline
spell dict off the caster's sheet, and only *enriches* it from the SRD
catalog when the spell's ``_slug`` resolves — using ``setdefault`` so any
field already on the sheet wins. Two consequences this file pins:

  1. A fully homebrew spell — one whose ``_slug`` is not in the catalog —
     casts entirely from its inline sheet definition. The ``spell_cast``
     broadcast echoes the homebrew name / level / school / casting time /
     save ability / damage and the inline ``actions`` array verbatim, with
     no catalog lookup needed. (This is the headline "homebrew handling"
     case the spell-validation plan filed.)

  2. Sheet-side override precedence: when a homebrew entry borrows a real
     catalog ``_slug`` but overrides a field (renaming an SRD spell for
     flavor), the sheet value wins while the un-overridden catalog fields
     still bleed through.

"Bless of Bahamut" is a fictional homebrew spell (deliberately absent from
the catalog). The fixtures patch it + a cleric slot onto Brother Tavik
Stonebrow (demo Cleric — a thematic fit for a draconic blessing) and
restore the sheet in finally.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

_HOMEBREW_SLUG = "bless-of-bahamut"


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


@pytest_asyncio.fixture
async def tavik_homebrew(gm_client, roster):
    """Patch a fully-homebrew 'Bless of Bahamut' + a cleric L2 slot onto
    Brother Tavik Stonebrow; restore both in finally."""
    tavik = roster["Brother Tavik Stonebrow"]
    sheet = await _sheet(gm_client, tavik["id"])
    orig_spells = list(sheet.get("spells") or [])
    orig_slots = dict(sheet.get("spell_slots") or {})

    homebrew = {
        "name": "Bless of Bahamut",
        "_slug": _HOMEBREW_SLUG,
        "level": 2,
        "class": "cleric",
        "prepared": True,
        "school": "Evocation",
        "casting_time": "1 action",
        "range": "30 feet",
        "duration": "Instantaneous",
        "save_ability": "DEX",
        "damage": "2d8",
        "actions": [{
            "name": "Radiant Smite",
            "save_ability": "DEX",
            "attack_roll": False,
            "damage": "2d8",
            "damage_type": "radiant",
        }],
    }
    new_spells = orig_spells + [homebrew]
    homebrew_index = len(orig_spells)

    new_slots = {k: dict(v) for k, v in orig_slots.items()}
    cle = dict(new_slots.get("cleric") or {})
    cle["2"] = {"total": 1, "used": 0}
    new_slots["cleric"] = cle

    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"spells": new_spells, "spell_slots": new_slots},
    )
    assert r.status_code == 200, r.text
    try:
        yield {"char": tavik, "index": homebrew_index}
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )


@pytest_asyncio.fixture
async def tavik_renamed_bless(gm_client, roster):
    """Patch a homebrew entry that BORROWS the real ``bless`` slug but
    renames it ('Bahamut's Greater Blessing') + a cleric L1 slot; restore."""
    tavik = roster["Brother Tavik Stonebrow"]
    sheet = await _sheet(gm_client, tavik["id"])
    orig_spells = list(sheet.get("spells") or [])
    orig_slots = dict(sheet.get("spell_slots") or {})

    renamed = {
        "name": "Bahamut's Greater Blessing",
        "_slug": "bless",  # real catalog slug — enrichment fires
        "level": 1,
        "class": "cleric",
        "prepared": True,
        "casting_time": "1 action",
    }
    new_spells = orig_spells + [renamed]
    idx = len(orig_spells)

    new_slots = {k: dict(v) for k, v in orig_slots.items()}
    cle = dict(new_slots.get("cleric") or {})
    cle["1"] = {"total": max(1, int((cle.get("1") or {}).get("total") or 1)),
                "used": 0}
    new_slots["cleric"] = cle

    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
        json={"spells": new_spells, "spell_slots": new_slots},
    )
    assert r.status_code == 200, r.text
    try:
        yield {"char": tavik, "index": idx}
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )


def test_bless_of_bahamut_absent_from_catalog():
    """The homebrew spell is genuinely non-SRD: no ``bless-of-bahamut``
    slug ships in the catalog, so the cast path can't be leaning on a
    hidden JSON file."""
    slugs = {(s.get("slug") or "") for s in load_all_spells()}
    assert _HOMEBREW_SLUG not in slugs, (
        "Bless of Bahamut must NOT be in the catalog — it's homebrew"
    )


async def test_cast_homebrew_spell_rides_inline_definition(
    gm_client, gm_ws, tavik_homebrew,
):
    """A fully-homebrew spell (slug absent from the catalog) casts entirely
    from its inline sheet definition: the cast spends the L2 slot and the
    ``spell_cast`` broadcast echoes the homebrew name / level / school /
    casting time / save ability / damage and the inline ``actions`` array
    verbatim — no catalog enrichment required."""
    tavik = tavik_homebrew["char"]
    idx = tavik_homebrew["index"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": idx,
            "slot_level": 2,
            "class_slug": "cleric",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["slot"]["level"] == 2
    assert data["slot"]["used"] >= 1

    msg = await gm_ws.wait_for("spell_cast")
    d = msg["data"]
    assert d["spell_name"] == "Bless of Bahamut"
    assert d["spell_level"] == 2
    assert d["spell_school"] == "Evocation"
    assert d["spell_casting_time"] == "1 action"
    assert d["spell_save_ability"] == "DEX"
    assert d["spell_damage"] == "2d8"
    # The inline action array rides through untouched.
    actions = d["actions"]
    assert actions, "homebrew actions must survive to the broadcast"
    smite = actions[0]
    assert smite["name"] == "Radiant Smite"
    assert smite["save_ability"] == "DEX"
    assert smite["damage"] == "2d8"
    assert (smite["damage_type"] or "").lower() == "radiant"


async def test_homebrew_sheet_override_beats_catalog(
    gm_client, gm_ws, tavik_renamed_bless,
):
    """Sheet-side override precedence: a homebrew entry borrowing the real
    ``bless`` slug but renaming it broadcasts the SHEET name (sheet wins via
    ``setdefault``), while un-overridden catalog fields (the spell's
    Enchantment school) still bleed through from the SRD record."""
    tavik = tavik_renamed_bless["char"]
    idx = tavik_renamed_bless["index"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": idx,
            "slot_level": 1,
            "class_slug": "cleric",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text

    msg = await gm_ws.wait_for("spell_cast")
    d = msg["data"]
    # Sheet override wins.
    assert d["spell_name"] == "Bahamut's Greater Blessing"
    # Catalog field bleeds through (Bless is Enchantment in the SRD).
    assert d["spell_school"] == "Enchantment"
