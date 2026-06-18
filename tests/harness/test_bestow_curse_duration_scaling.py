"""v2.405.2 — spell-utility-mechanical-depth Phase 1: duration-scaling
substrate, third consumer + first ``"permanent"`` marker. The v2.405.0
`_SPELL_DURATION_MAP` + `_spell_duration_rounds_for_slot()` helper now
backs `/cast_bestow_curse`, which pre-v2.405.2 stamped a flat 10-round
(1 min) duration regardless of slot level. RAW PHB p.218:

  - L3    → 1 minute   (10 rounds)   → label "1min"
  - L4    → 10 minutes (100 rounds)  → label "10min"
  - L5-L6 → 8 hours    (4800 rounds) → label "8h"
  - L7-L8 → 24 hours   (14400 rounds)→ label "24h"
  - L9    → until dispelled          → marker "permanent" → label "permanent"

The endpoint now surfaces `duration_label` + the substrate-computed
`duration_rounds` on the response body. These tests cast at L3 / L4 /
L5 / L7 / L9 and assert the label routes through every tier — including
the new `"permanent"` marker at L9.

Bestow Curse isn't on any demo PC's native spell list (Magnus casts it
only via the 1/long-rest Sign of Ill Omen invocation at L3). Thalindra
Moonwhisper (Wizard Lv 7) gets it for these tests: the fixture snapshots
her spells + wizard slot table, appends Bestow Curse + a full L1-L9 slot
table, and restores both on teardown so other Thalindra tests are
unaffected.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    return r.json()["sheet"]


async def _patch(gm_client, char_id, fields):
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=fields,
    )
    assert r.status_code == 200, r.text


@pytest_asyncio.fixture
async def thalindra_cursed(gm_client, roster):
    """Thalindra armed with Bestow Curse on her spell list + an L1-L9
    wizard slot table so every duration tier is reachable. Snapshots
    + restores her spells + wizard slots so other tests are untouched."""
    thal = roster["Thalindra Moonwhisper"]
    sheet = await _sheet(gm_client, thal["id"])
    orig_spells = list(sheet.get("spells") or [])
    orig_slots = dict((sheet.get("spell_slots") or {}).get("wizard") or {})

    spells = list(orig_spells)
    has_bc = any(
        (s.get("_slug") == "bestow-curse")
        or (str(s.get("name", "")).lower() == "bestow curse")
        for s in spells
    )
    if not has_bc:
        spells.append({
            "name": "Bestow Curse",
            "_slug": "bestow-curse",
            "level": 3,
            "class": "wizard",
        })
    slot_table = {
        str(lv): {"total": 2, "used": 0} for lv in range(1, 10)
    }
    await _patch(gm_client, thal["id"], {
        "spells": spells,
        "spell_slots": {"wizard": slot_table},
    })
    yield thal
    # Restore so other Thalindra tests see the untouched sheet.
    await _patch(gm_client, thal["id"], {
        "spells": orig_spells,
        "spell_slots": {"wizard": orig_slots},
    })


async def _cast(gm_client, thal, slot_level):
    return await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_bestow_curse",
        json={
            "character_id": thal["id"],
            "class_slug": "wizard",
            "slot_level": slot_level,
            "override": True,
        },
    )


async def test_bestow_curse_l3_routes_1min(gm_client, thalindra_cursed):
    """L3 → 10 rounds (1 min); `duration_label == "1min"`. Base tier."""
    resp = await _cast(gm_client, thalindra_cursed, slot_level=3)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["duration_label"] == "1min", data
    assert data["duration_rounds"] == 10, data


async def test_bestow_curse_l4_routes_10min(gm_client, thalindra_cursed):
    """L4 → 100 rounds (10 min); `duration_label == "10min"`."""
    resp = await _cast(gm_client, thalindra_cursed, slot_level=4)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["duration_label"] == "10min", data
    assert data["duration_rounds"] == 100, data


async def test_bestow_curse_l5_routes_8h(gm_client, thalindra_cursed):
    """L5 → 4800 rounds (8 hours); `duration_label == "8h"`."""
    resp = await _cast(gm_client, thalindra_cursed, slot_level=5)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["duration_label"] == "8h", data
    assert data["duration_rounds"] == 4800, data


async def test_bestow_curse_l7_routes_24h(gm_client, thalindra_cursed):
    """L7 → 14400 rounds (24 hours); `duration_label == "24h"`."""
    resp = await _cast(gm_client, thalindra_cursed, slot_level=7)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["duration_label"] == "24h", data
    assert data["duration_rounds"] == 14400, data


async def test_bestow_curse_l9_routes_permanent(gm_client, thalindra_cursed):
    """L9 → "permanent" marker (until dispelled); `duration_label ==
    "permanent"`. First consumer of the substrate's marker-string path."""
    resp = await _cast(gm_client, thalindra_cursed, slot_level=9)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["duration_label"] == "permanent", data
