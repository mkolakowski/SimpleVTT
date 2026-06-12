"""Phase 4 complex-spell deep-dive — Wish (L9 Conjuration).

Wish (PHB p.288-289) is the catalog's open-ended capstone: "you can
alter the very foundations of reality." Its basic use duplicates any
8th-level-or-lower spell; its bespoke effects (object creation, mass
healing, reroll-the-last-round, the stress backlash) are pure DM
adjudication. The engine models *none* of that — Wish has no dedicated
endpoint and no ``_SPELL_BUFF_MAP`` entry, so it rides the generic
``/cast_spell`` path: it spends an L9 slot and broadcasts ``spell_cast``,
and the wish itself is narrated at the table.

This deep-dive is the L9 sibling of the Mirror Image one — a
*narration-only contract pin* plus one catalog quirk worth documenting:
the SRD build mis-folded Wish's stress clause ("1d10 necrotic per spell
level") into the cast action's ``damage`` field, so the action carries
``damage: "1d10"`` necrotic even though Wish has no attack roll and no
save. That damage is narration-grade (the GM applies the backlash by
hand), not an auto-resolved hit — the test pins that shape so a future
"resolve Wish's damage automatically" change is a conscious one.

No demo PC is high enough level to own Wish (no L17 casters), so the
fixture patches Wish + a single wizard L9 slot onto Thalindra
Moonwhisper (demo Wizard), then restores both in finally.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

_SLUG = "wish"


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    return (r.json() or {}).get("sheet") or {}


async def _get_buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    body = resp.json()
    keys = {(b or {}).get("key") for b in body.get("buffs") or []}
    keys |= {(b or {}).get("key") for b in body.get("sheet_buffs") or []}
    return keys


@pytest_asyncio.fixture
async def thalindra_wish(gm_client, roster):
    """Patch Wish + a wizard L9 slot onto Thalindra; restore both."""
    thal = roster["Thalindra Moonwhisper"]
    sheet = await _sheet(gm_client, thal["id"])
    orig_spells = list(sheet.get("spells") or [])
    orig_slots = dict(sheet.get("spell_slots") or {})

    new_spells = orig_spells + [{
        "name": "Wish", "_slug": "wish", "level": 9,
        "class": "wizard", "prepared": True, "casting_time": "1 action",
    }]
    wish_index = len(orig_spells)

    new_slots = {k: dict(v) for k, v in orig_slots.items()}
    wiz = dict(new_slots.get("wizard") or {})
    wiz["9"] = {"total": 1, "used": 0}
    new_slots["wizard"] = wiz

    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/sheet-fields",
        json={"spells": new_spells, "spell_slots": new_slots},
    )
    assert r.status_code == 200, r.text
    try:
        yield {"char": thal, "wish_index": wish_index}
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{thal['id']}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )


def test_wish_present_in_catalog():
    """Catalog shape: L9 Conjuration, Self range, Instantaneous,
    non-concentration, Sorcerer + Wizard lists. Plus the SRD quirk —
    the cast action carries ``damage: "1d10"`` necrotic (the stress
    clause folded into the action) but NO attack roll and NO save, so
    the backlash is narration-grade, not an auto-resolved hit."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    w = by_slug.get(_SLUG)
    assert w is not None, "wish must be in the spell catalog"
    assert w.get("level_int") == 9
    assert (w.get("school") or "").lower() == "conjuration"
    assert "self" in (w.get("range") or "").lower()
    assert "instantaneous" in (w.get("duration") or "").lower()
    assert w.get("concentration") is False
    assert {"sorcerer", "wizard"} <= set(w.get("spell_lists") or [])
    actions = w.get("actions") or []
    assert actions, "wish must carry the cast action"
    cast = actions[0]
    # SRD-build quirk: stress damage on the action, but no hit/save —
    # narration-grade, not auto-resolved.
    assert cast.get("damage") == "1d10", cast
    assert (cast.get("damage_type") or "").lower() == "necrotic", cast
    assert not cast.get("attack_roll"), cast
    assert not cast.get("save_ability"), cast


async def test_cast_wish_spends_l9_slot_and_broadcasts(
    gm_client, gm_ws, thalindra_wish,
):
    """Wish rides the generic /cast_spell path: casting it spends the
    L9 slot and broadcasts spell_cast with the name / level / timing.
    The wish's effect is GM-narrated — the contract is "doesn't 500,
    spends the slot, names the spell."""
    thal = thalindra_wish["char"]
    idx = thalindra_wish["wish_index"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": idx,
            "slot_level": 9,
            "class_slug": "wizard",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["slot"]["level"] == 9
    assert data["slot"]["used"] >= 1

    msg = await gm_ws.wait_for("spell_cast")
    d = msg["data"]
    assert d["spell_name"] == "Wish"
    assert d["spell_level"] == 9
    assert d["spell_casting_time"] == "1 action"


async def test_cast_wish_is_non_concentration(gm_client, thalindra_wish):
    """Wish is Instantaneous + non-concentration: the cast must not
    flag concentration on the response and must not install a
    ``concentration-wish`` anchor on the caster."""
    thal = thalindra_wish["char"]
    idx = thalindra_wish["wish_index"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thal["id"],
            "spell_index": idx,
            "slot_level": 9,
            "class_slug": "wizard",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert not resp.json().get("concentration"), (
        "Wish is non-concentration; the cast must not flag it"
    )
    keys = await _get_buff_keys(gm_client, thal["id"])
    assert not any("concentration" in (k or "") and "wish" in (k or "")
                   for k in keys), keys
