"""Phase 4 complex-spell deep-dive — the Conjure X family (narration-only).

Conjure Animals (L3) is the one summon-spell with a real engine: it has a
dedicated ``/cast_conjure_animals`` endpoint that stands up `count` beast
combatants on the grid (see test_cast_conjure_animals.py). Its five higher
siblings — Conjure Celestial (L7), Conjure Elemental (L5), Conjure Fey
(L6), Conjure Minor Elementals (L4), Conjure Woodland Beings (L4) — have
NO bespoke endpoint and NO ``_SPELL_BUFF_MAP`` entry. They ride the generic
``/cast_spell`` path: it spends a slot and broadcasts ``spell_cast``, and
the GM stands up the conjured stat block by hand. The engine creates no
combatant and no token for them — that's the narration-only contract.

This file pins two things so a future "wire the rest of the family into
the summon engine" change is a conscious one, not silent drift:

  1. Catalog shape for all five siblings — Conjuration, the right level,
     no auto-resolved save/attack/damage action, and the catalog-vs-runtime
     concentration divergence: every sibling's duration starts with "Up to"
     (the Open5e concentration convention the generic cast path keys on)
     even though the catalog ``concentration`` flag is False.

  2. Generic-cast narration contract for one representative (Conjure Minor
     Elementals): casting it spends the slot and broadcasts, but — unlike
     /cast_conjure_animals — the response carries NO ``combatants`` /
     ``token_ids`` keys, creates no summon combatant, and installs no buff
     or concentration anchor.

No demo PC owns these high-level conjures, so the cast fixture patches
Conjure Minor Elementals + a druid L4 slot onto Mira Greenleaf (demo
Druid) and restores both in finally.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

# slug -> (level, {required spell-list members})
_FAMILY = {
    "conjure-celestial": (7, {"cleric"}),
    "conjure-elemental": (5, {"druid", "wizard"}),
    "conjure-fey": (6, {"druid", "warlock"}),
    "conjure-minor-elementals": (4, {"druid", "wizard"}),
    "conjure-woodland-beings": (4, {"druid", "ranger"}),
}

_CAST_SLUG = "conjure-minor-elementals"


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
async def mira_conjure(gm_client, roster):
    """Patch Conjure Minor Elementals + a druid L4 slot onto Mira; restore."""
    mira = roster["Mira Greenleaf"]
    sheet = await _sheet(gm_client, mira["id"])
    orig_spells = list(sheet.get("spells") or [])
    orig_slots = dict(sheet.get("spell_slots") or {})

    new_spells = orig_spells + [{
        "name": "Conjure Minor Elementals", "_slug": _CAST_SLUG, "level": 4,
        "class": "druid", "prepared": True, "casting_time": "1 minute",
    }]
    cast_index = len(orig_spells)

    new_slots = {k: dict(v) for k, v in orig_slots.items()}
    dru = dict(new_slots.get("druid") or {})
    dru["4"] = {"total": 1, "used": 0}
    new_slots["druid"] = dru

    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
        json={"spells": new_spells, "spell_slots": new_slots},
    )
    assert r.status_code == 200, r.text
    try:
        yield {"char": mira, "cast_index": cast_index}
    finally:
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/sheet-fields",
            json={"spells": orig_spells, "spell_slots": orig_slots},
        )


def test_conjure_family_present_in_catalog():
    """All five higher conjures are present, Conjuration, at the right
    level, with a single no-save / no-attack / no-damage cast action, the
    right spell-list membership, and the concentration divergence: catalog
    ``concentration`` is False yet the duration starts with "Up to" (the
    runtime concentration convention)."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    for slug, (level, lists) in _FAMILY.items():
        sp = by_slug.get(slug)
        assert sp is not None, f"{slug} must be in the spell catalog"
        assert sp.get("level_int") == level, slug
        assert (sp.get("school") or "").lower() == "conjuration", slug
        assert lists <= set(sp.get("spell_lists") or []), slug
        # Narration-only: the cast action auto-resolves nothing.
        for a in sp.get("actions") or []:
            assert not a.get("save_ability"), (slug, a)
            assert not a.get("attack_roll"), (slug, a)
            assert not a.get("damage"), (slug, a)
        # Catalog-vs-runtime concentration divergence.
        assert sp.get("concentration") is False, slug
        assert (sp.get("duration") or "").strip().lower().startswith("up to"), (
            slug, sp.get("duration"),
        )


async def test_cast_conjure_minor_elementals_narration_only(
    gm_client, gm_ws, mira_conjure,
):
    """The siblings ride the generic /cast_spell path: casting Conjure Minor
    Elementals spends the L4 slot and broadcasts spell_cast — but, unlike
    /cast_conjure_animals, the response stands up no combatant. The contract
    is "spends the slot, names the spell, creates no token; the GM places
    the conjured stat block by hand"."""
    mira = mira_conjure["char"]
    idx = mira_conjure["cast_index"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": mira["id"],
            "spell_index": idx,
            "slot_level": 4,
            "class_slug": "druid",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["slot"]["level"] == 4
    assert data["slot"]["used"] >= 1
    # The narration contract: no summon-engine payload (contrast
    # /cast_conjure_animals, which returns combatants + token_ids).
    assert "combatants" not in data, data
    assert "token_ids" not in data, data

    msg = await gm_ws.wait_for("spell_cast")
    d = msg["data"]
    assert d["spell_name"] == "Conjure Minor Elementals"
    assert d["spell_level"] == 4
    assert d["spell_casting_time"] == "1 minute"


async def test_cast_conjure_installs_no_buff_or_anchor(gm_client, mira_conjure):
    """No ``_SPELL_BUFF_MAP`` entry and no AoE template, so the generic cast
    installs neither a spell buff nor a ``concentration-conjure-*`` anchor on
    the caster — the GM tracks the conjured creatures' duration by hand."""
    mira = mira_conjure["char"]
    idx = mira_conjure["cast_index"]
    before = await _get_buff_keys(gm_client, mira["id"])
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": mira["id"],
            "spell_index": idx,
            "slot_level": 4,
            "class_slug": "druid",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert not resp.json().get("concentration"), resp.text
    after = await _get_buff_keys(gm_client, mira["id"])
    assert not any("conjure" in (k or "") for k in after - before), after
    assert not any("concentration" in (k or "") for k in after - before), after
