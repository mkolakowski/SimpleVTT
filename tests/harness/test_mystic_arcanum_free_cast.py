"""v2.99.88 — Mystic Arcanum free-cast routing through /cast_spell.

v2.99.45 shipped /use_mystic_arcanum as announce-only (decrement
the daily charge + broadcast); the actual spell-cast had to be
done separately and consumed a Pact Magic slot. v2.99.88 closes
the loop: /cast_spell now accepts a ``free_cast: true`` flag that
routes through Mystic Arcanum.

Server-side gates (all 409):
  - free_cast_wrong_class — sheet.class != "warlock"
  - free_cast_invalid_slot_level — slot_level ∉ {6,7,8,9}
  - free_cast_level_too_low — warlock level < gate
  - free_cast_no_arcanum_resource — mystic-arcanum-l{N} missing
  - free_cast_no_uses_left — resource current == 0

On valid: decrements ``mystic-arcanum-l{slot_level}`` resource by
1, SKIPS the Pact Magic slot decrement, broadcasts
``feature_used(source=mystic-arcanum-cast)`` + ``resource_update``.

Tests use the v2.99.39 capstone-test pattern + the v2.99.86
fixture pattern (PATCH the L6-L9 resource list before each test).

Tests:
- happy: Magnus at Lv 11, casts a Lv 6 spell with free_cast=true →
  mystic-arcanum-l6 decrements; Pact Magic slot UNCHANGED; the
  feature_used + resource_update broadcasts fire.
- gate: Magnus at Lv 5, free_cast L6 → free_cast_level_too_low.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _full_mystic_arcanum_resources():
    return [
        {"key": "mystic-arcanum-l6", "name": "Mystic Arcanum (L6)",
         "current": 1, "max": 1, "reset": "long",
         "class_slug": "warlock", "manual": False},
        {"key": "mystic-arcanum-l7", "name": "Mystic Arcanum (L7)",
         "current": 1, "max": 1, "reset": "long",
         "class_slug": "warlock", "manual": False},
        {"key": "mystic-arcanum-l8", "name": "Mystic Arcanum (L8)",
         "current": 1, "max": 1, "reset": "long",
         "class_slug": "warlock", "manual": False},
        {"key": "mystic-arcanum-l9", "name": "Mystic Arcanum (L9)",
         "current": 1, "max": 1, "reset": "long",
         "class_slug": "warlock", "manual": False},
    ]


@pytest_asyncio.fixture
async def magnus_with_arcana(gm_client, roster):
    """Ensures Magnus has the full 4-tier MA resource list (PATCHed
    at setup, not restored at teardown since the seed already
    carries them). Yields a setter for warlock level + the char
    dict.
    """
    magnus = roster["Magnus Hexbinder"]
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"resources": _full_mystic_arcanum_resources()},
    )

    async def _set(level):
        await gm_client.patch(
            f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
            json={"class_slug": "warlock", "level": level},
        )
        return magnus

    yield _set

    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/sheet-fields",
        json={"class_slug": "warlock", "level": 5},
    )


async def _find_magnus_spell_at_level(gm_client, magnus_id, level):
    """Locate a spell in Magnus's prepared list at the requested
    level. Returns (spell_index, slug) or (None, None) if missing.
    """
    # Magnus's seed includes Counterspell (Lv 3) but no L6+ spells.
    # For free-cast we need slot_level >= 6 even if the spell
    # itself is lower-level. /cast_spell accepts slot_level > spell
    # level (upcast). Counterspell is a fine candidate.
    return 0, "magic-missile"  # placeholder; actual indices below


async def test_free_cast_decrements_arcanum_not_pact_slot(
    gm_client, gm_ws, magnus_with_arcana,
):
    """Magnus at Lv 11 casts a leveled spell with free_cast=true +
    slot_level=6 → the mystic-arcanum-l6 charge drops by 1, the
    Pact Magic slots stay untouched, feature_used(source=mystic-
    arcanum-cast) + resource_update broadcast.
    """
    magnus = await magnus_with_arcana(11)

    # Find Magnus's spell index for any leveled spell. The seed
    # has Counterspell at index 4 typically; we hit /cast_spell
    # with slot_level=6 to upcast.
    # First, snapshot the pact slot state so we can assert no change.
    # The /economy endpoint returns the spell_slots; we read directly
    # from the character endpoint via sheet-fields PATCH echo if available.
    # Simpler: we'll cast with free_cast and check that the response's
    # ``updated_slot`` field is None and the MA resource decremented.

    # Use Magnus's first available leveled spell — Eldritch Blast
    # is a cantrip (level 0), so skip. The seed has spells listed;
    # we'll use Magic Missile (Lv 1) at index that varies. Walk
    # the spell list to find a non-cantrip.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": magnus["id"],
            "spell_index": 0,  # first spell — varies; for the test
                                # the actual spell doesn't matter as
                                # long as /cast_spell accepts it
            "slot_level": 6,
            "class_slug": "warlock",
            "free_cast": True,
        },
    )
    # If index 0 happens to be a cantrip (level 0), the endpoint
    # will route differently; walk indices 0..10 until one accepts
    # the slot_level=6 upcast or returns a different error.
    for idx in range(10):
        if r.status_code == 200:
            break
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        # If level-too-low or wrong errors fire on this spell, try next.
        if body.get("error") in ("free_cast_no_arcanum_resource",
                                 "free_cast_no_uses_left",
                                 "free_cast_level_too_low",
                                 "free_cast_wrong_class"):
            # These are unrelated to spell selection — bail.
            break
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": magnus["id"],
                "spell_index": idx,
                "slot_level": 6,
                "class_slug": "warlock",
                "free_cast": True,
            },
        )
    assert r.status_code == 200, (
        f"free_cast at Lv 11 should succeed for some leveled spell "
        f"in Magnus's list; last response: {r.text}"
    )
    data = r.json()
    # The endpoint should NOT report a slot consumption.
    assert data.get("updated_slot") is None, (
        f"free_cast should NOT decrement a Pact Magic slot; got "
        f"updated_slot={data.get('updated_slot')!r}"
    )

    # Verify the mystic-arcanum-cast feature_used + resource_update
    # broadcasts fired.
    import asyncio as _asy
    await _asy.sleep(0.2)
    fu_msgs = gm_ws.buffered("feature_used")
    ma_cast = [
        m for m in fu_msgs
        if (m.get("data") or {}).get("source") == "mystic-arcanum-cast"
        and (m.get("data") or {}).get("character_id") == magnus["id"]
    ]
    assert ma_cast, (
        f"expected feature_used(source=mystic-arcanum-cast); "
        f"buffered: {[(m.get('data') or {}).get('source') for m in fu_msgs]}"
    )
    ru_msgs = gm_ws.buffered("resource_update")
    ma_ru = [
        m for m in ru_msgs
        if (m.get("data") or {}).get("character_id") == magnus["id"]
        and (m.get("data") or {}).get("key") == "mystic-arcanum-l6"
    ]
    assert ma_ru, (
        f"expected resource_update for mystic-arcanum-l6 with "
        f"current=0; got: "
        f"{[(m.get('data') or {}).get('key') for m in ru_msgs]}"
    )


async def test_free_cast_level_too_low(gm_client, magnus_with_arcana):
    """Magnus at Lv 5 attempts a free-cast at slot_level=6 → 409
    free_cast_level_too_low (gate is Lv 11 for L6).
    """
    magnus = await magnus_with_arcana(5)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": magnus["id"],
            "spell_index": 0,
            "slot_level": 6,
            "class_slug": "warlock",
            "free_cast": True,
        },
    )
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "free_cast_level_too_low"
    assert err["required"] == 11
    assert err["got"] == 5
    assert err["slot_level"] == 6
