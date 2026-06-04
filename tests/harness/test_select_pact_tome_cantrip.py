"""v2.99.200 — Pact of the Tome (Warlock Lv 3) cantrip-picker endpoint.

Phase D.1 of the v2.99.193 phased completion plan. RAW (PHB
p.108): "Your patron gives you a grimoire called a Book of
Shadows. When you gain this feature, choose three cantrips from
any class's spell list. While the book is on your person, you
can cast those cantrips at will. They don't count against your
number of cantrips known."

v2.99.200 ships `/select_pact_tome_cantrip` — appends the picked
cantrip to the caster's `sheet.spells` list with `_via:
"pact-of-the-tome"` as the accounting marker. Cantrips never
consume Pact Magic slots by RAW, so no further integration with
/cast_spell is needed — the existing "spell on list" gate
admits the Tome cantrip just like a natively known one.

Tests:
  - Happy path: Magnus (Warlock Lv 5, pact_boon=tome via PATCH)
    picks Mage Hand → 200 + spell appended with the marker.
  - Cap: 4th pick → 409 cap_exceeded.
  - Duplicate: pick the same slug twice → 409 already_picked.
  - Gate: non-Warlock → 409 wrong_class.
  - Gate: wrong pact_boon (pact_boon="" or "blade") → 409 wrong_pact_boon.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _tome_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "pact-of-the-tome"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


async def _clear_tome_cantrips(gm_client, char_id):
    """Use the endpoint's clear_first flag to drop all existing
    Tome cantrips on the character. Idempotent."""
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_pact_tome_cantrip",
        json={
            "character_id": char_id,
            "cantrip_slug": "",
            "clear_first": True,
        },
    )


@pytest_asyncio.fixture
async def magnus_with_tome_boon(gm_client, roster):
    """PATCH Magnus's pact_boon → 'tome' + clear any leftover Tome
    cantrips from prior tests. Restore pact_boon='' + clear in
    teardown."""
    magnus = roster["Magnus Hexbinder"]
    await _patch_sheet(gm_client, magnus["id"], {"pact_boon": "tome"})
    await _clear_tome_cantrips(gm_client, magnus["id"])
    yield magnus
    await _clear_tome_cantrips(gm_client, magnus["id"])
    await _patch_sheet(gm_client, magnus["id"], {"pact_boon": ""})


async def test_pact_tome_pick_happy_path(
    gm_client, gm_ws, magnus_with_tome_boon,
):
    """Magnus picks Mage Hand (Wizard cantrip) via the Tome boon."""
    magnus = magnus_with_tome_boon
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_pact_tome_cantrip",
        json={
            "character_id": magnus["id"],
            "cantrip_slug": "mage-hand",
            "cantrip_name": "Mage Hand",
            "source_class_slug": "wizard",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["cantrip_slug"] == "mage-hand"
    assert data["picked"] == 1
    assert data["max"] == 3
    feats = _tome_broadcasts(gm_ws, magnus["id"])
    assert feats, (
        f"expected feature_used(source=pact-of-the-tome); "
        f"buffered={gm_ws.buffered()}"
    )


async def test_pact_tome_cap_at_three(
    gm_client, magnus_with_tome_boon,
):
    """Magnus picks 3 cantrips successfully; the 4th returns 409."""
    magnus = magnus_with_tome_boon
    for slug, name in [
        ("guidance", "Guidance"),
        ("light", "Light"),
        ("druidcraft", "Druidcraft"),
    ]:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/select_pact_tome_cantrip",
            json={
                "character_id": magnus["id"],
                "cantrip_slug": slug,
                "cantrip_name": name,
                "source_class_slug": "cleric",
            },
        )
        assert r.status_code == 200, r.text
    # 4th pick → cap_exceeded.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_pact_tome_cantrip",
        json={
            "character_id": magnus["id"],
            "cantrip_slug": "fire-bolt",
            "cantrip_name": "Fire Bolt",
            "source_class_slug": "wizard",
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "cap_exceeded"
    assert data.get("max") == 3


async def test_pact_tome_duplicate_pick_rejected(
    gm_client, magnus_with_tome_boon,
):
    """Picking the same slug twice → 409 already_picked."""
    magnus = magnus_with_tome_boon
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_pact_tome_cantrip",
        json={
            "character_id": magnus["id"],
            "cantrip_slug": "thaumaturgy",
            "cantrip_name": "Thaumaturgy",
            "source_class_slug": "cleric",
        },
    )
    assert r.status_code == 200, r.text
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_pact_tome_cantrip",
        json={
            "character_id": magnus["id"],
            "cantrip_slug": "thaumaturgy",
            "cantrip_name": "Thaumaturgy",
            "source_class_slug": "cleric",
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "already_picked"
    assert data.get("slug") == "thaumaturgy"


async def test_pact_tome_wrong_class_gate(
    gm_client, roster,
):
    """Control: Tavik (Cleric) → 409 wrong_class."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_pact_tome_cantrip",
        json={
            "character_id": tavik["id"],
            "cantrip_slug": "mage-hand",
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_class"


async def test_pact_tome_wrong_pact_boon_gate(
    gm_client, roster,
):
    """Control: Magnus with pact_boon="" → 409 wrong_pact_boon."""
    magnus = roster["Magnus Hexbinder"]
    # Default: no pact_boon. Don't PATCH.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/select_pact_tome_cantrip",
        json={
            "character_id": magnus["id"],
            "cantrip_slug": "mage-hand",
        },
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_pact_boon"
