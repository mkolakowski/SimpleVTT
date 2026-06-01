"""v2.99.25 — Warlock Pact Magic short-rest slot refresh.

RAW (PHB p.107): Warlock spell slots refresh on a **short** rest
(every other class refreshes on long rest). v2.99.25 closes the
gap: each Pact Magic slot row on the sheet carries `reset: "short"`;
the /rest short-rest branch walks `sheet.spell_slots[cslug][lvl]`
and resets `used = 0` on any slot row with that marker. The
slot-level marker (rather than a blanket warlock-class gate)
generalizes to multiclass Warlocks + future homebrew short-rest
casters.

Test strategy:
- Long rest Magnus to start at full slots (used=0).
- Deplete his L3 Pact slot via sheet-fields PATCH (set used=2).
- Short rest.
- Verify the spell_slot_update broadcast for class_slug="warlock",
  level=3 fires with used=0.

Magnus Hexbinder is the demo Warlock (Lv 5, "The Fiend" patron).
Pact slot pool at Lv 5: 2 slots at L3.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def magnus_rested(gm_client, roster):
    magnus = roster["Magnus Hexbinder"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    return magnus


async def _patch_slot_used(gm_client, char_id, class_slug, level, used, total=2):
    """Set Magnus's Pact Magic slot used count via sheet-fields PATCH.
    Avoids needing a spell cast that consumes the slot — keeps the
    test focused on the rest-refresh behaviour itself. Preserves
    the `reset: "short"` marker so the rest walker still sees it.
    """
    return await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={
            "spell_slots": {
                class_slug: {
                    str(level): {"total": total, "used": used, "reset": "short"},
                },
            },
        },
    )


def _slot_updates(gm_ws, character_id, class_slug, level):
    return [
        m for m in gm_ws.buffered("spell_slot_update")
        if (m.get("data") or {}).get("character_id") == character_id
        and (m.get("data") or {}).get("class_slug") == class_slug
        and (m.get("data") or {}).get("level") == level
    ]


async def test_warlock_pact_magic_refreshes_on_short_rest(
    gm_client, gm_ws, magnus_rested,
):
    """Magnus depletes both L3 Pact slots; a short rest restores
    both via a `spell_slot_update` broadcast carrying used=0.
    """
    magnus = magnus_rested
    # Consume both Pact slots.
    r = await _patch_slot_used(gm_client, magnus["id"], "warlock", 3, used=2)
    assert r.status_code == 200, r.text

    gm_ws.mark()
    # Short rest.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "short"},
    )
    assert r.status_code == 200, r.text
    import asyncio as _asy
    await _asy.sleep(0.2)

    # Assert spell_slot_update fired for warlock L3 with used=0.
    msgs = _slot_updates(gm_ws, magnus["id"], "warlock", 3)
    assert msgs, (
        f"expected spell_slot_update broadcast for warlock L3 after short rest; "
        f"buffered: {[(m.get('type'), (m.get('data') or {})) for m in gm_ws.buffered()]}"
    )
    last = msgs[-1].get("data") or {}
    assert last.get("used") == 0, (
        f"expected used=0 after short rest; got {last}"
    )
    assert int(last.get("total") or -1) == 2, (
        f"expected total=2 (slot count unchanged); got {last}"
    )


async def test_warlock_pact_magic_refreshes_on_long_rest(
    gm_client, gm_ws, roster,
):
    """Sanity: a long rest ALSO refreshes Pact slots (the existing
    long-rest path resets every slot regardless of `reset` field).
    Regression guard against the v2.99.25 short-rest change
    over-touching the long-rest path.
    """
    magnus = roster["Magnus Hexbinder"]
    # Force-deplete pact slots.
    r = await _patch_slot_used(gm_client, magnus["id"], "warlock", 3, used=2)
    assert r.status_code == 200, r.text
    gm_ws.mark()
    # Long rest.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{magnus['id']}/rest",
        json={"type": "long"},
    )
    assert r.status_code == 200, r.text
    import asyncio as _asy
    await _asy.sleep(0.2)

    msgs = _slot_updates(gm_ws, magnus["id"], "warlock", 3)
    assert msgs, "expected spell_slot_update broadcast for warlock L3 after long rest"
    last = msgs[-1].get("data") or {}
    assert last.get("used") == 0, (
        f"expected used=0 after long rest; got {last}"
    )


async def test_short_rest_does_not_touch_non_warlock_slots(
    gm_client, gm_ws, roster,
):
    """Regression guard: Thalindra (Wizard) takes a short rest with
    L1 slots used; her slots should NOT be refreshed because Wizard
    slots don't carry `reset: "short"`. Only Warlock Pact slots do.
    """
    thalindra = roster["Thalindra Moonwhisper"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "long"},
    )
    # Burn 2 L1 slots.
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/sheet-fields",
        json={
            "spell_slots": {
                "wizard": {"1": {"total": 4, "used": 2}},
            },
        },
    )
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{thalindra['id']}/rest",
        json={"type": "short"},
    )
    assert r.status_code == 200, r.text
    import asyncio as _asy
    await _asy.sleep(0.2)
    # No spell_slot_update for wizard L1 — short rest leaves Wizard slots alone.
    msgs = _slot_updates(gm_ws, thalindra["id"], "wizard", 1)
    assert not msgs, (
        f"short rest should NOT refresh Wizard slots; got broadcasts: {msgs}"
    )
