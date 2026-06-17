"""v2.398.0 — Rock Gnome Artificer's Lore History check
(race-features plan Phase 6).

RAW PHB p.37: "Whenever you make an Intelligence (History) check
related to magic items, alchemical objects, or technological
devices, you can add twice your proficiency bonus, instead of any
proficiency bonus you normally apply." Race-gated to Gnome (any
subrace via `_race_slug_from_sheet`).

New endpoint `POST /api/campaign/{cid}/check_artificers_lore` rolls
``1d20 + INT mod + 2 × PB`` and broadcasts a `feature_used` event
with `source: "artificers-lore"` so chat-card / harness can
attribute the bonus. Optional free-text `note` echoes back as
"(topic: <note>)" in the feature description.

Test strategy (4 tests):
1. Happy path — Tavik (Hill Dwarf Cleric Lv 8) PATCHed to race
   "Rock Gnome" temporarily; the endpoint rolls 1d20 + INT mod
   (+0) + 2× PB (+3 → +6) = total in [7, 26]; feature_used
   broadcast carries source="artificers-lore" + the right math
   fields. Race restored at the end.
2. Non-Gnome 409 — Tavik (real Hill Dwarf seed, no PATCH) → 409
   `race_not_gnome`. Race-gate regression guard.
3. Missing character_id 400 — body without character_id is rejected
   at the input gate.
4. Note echo — Tavik PATCHed to "Rock Gnome" + note "Wand of Magic
   Detection" → response carries note verbatim + the feature_desc
   broadcast contains the note text.

Why Tavik as the fixture: no demo PC ships as a Rock Gnome today
(Mira is a Wood Elf, all other PCs are non-Gnome). PATCHing Tavik's
race for test scope avoids adding a new demo PC for one
trait; the restore-on-finally guarantees no cross-test
contamination of the shared dev container.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


@pytest_asyncio.fixture
async def tavik_rested(gm_client, roster):
    tavik = roster["Brother Tavik Stonebrow"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    return tavik


async def _patch_race(gm_client, char_id: int, race: str) -> None:
    await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json={"race": race},
    )


async def test_artificers_lore_rolls_with_double_pb_for_gnome(
    gm_client, gm_ws, tavik_rested,
):
    """Tavik PATCHed to race "Rock Gnome" (Lv 8, INT 10 → +0 mod, PB
    +3): the endpoint rolls 1d20 + 0 + (2 × 3) = 1d20 + 6. Total
    should be in [7, 26]; feature_used broadcast carries
    source=artificers-lore."""
    tavik = tavik_rested
    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-json",
    )
    orig_race = (snap.json().get("sheet") or {}).get("race") or "Hill Dwarf"
    try:
        await _patch_race(gm_client, tavik["id"], "Rock Gnome")
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/check_artificers_lore",
            json={"character_id": tavik["id"]},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["ok"] is True
        assert data["int_mod"] == 0
        assert data["proficiency_bonus"] == 3
        assert data["double_pb"] == 6
        assert 7 <= data["total"] <= 26, (
            f"total out of expected [7, 26] range; got {data['total']}"
        )
        assert "+6" in data["expression"]

        await asyncio.sleep(0.2)
        fu = [
            m for m in gm_ws.buffered("feature_used")
            if (m.get("data") or {}).get("source") == "artificers-lore"
            and (m.get("data") or {}).get("character_id") == tavik["id"]
        ]
        assert fu, (
            f"expected feature_used(source=artificers-lore); buffered: "
            f"{[(m.get('data') or {}).get('source') for m in gm_ws.buffered('feature_used')]}"
        )
        fu_data = fu[-1]["data"]
        assert fu_data["stat_key"] == "history"
        assert fu_data["stat_ability"] == "INT"
        assert fu_data["double_pb"] == 6
        assert fu_data["int_mod"] == 0
        assert fu_data["proficiency_bonus"] == 3
    finally:
        await _patch_race(gm_client, tavik["id"], orig_race)


async def test_artificers_lore_rejects_non_gnome(gm_client, tavik_rested):
    """Control: Tavik (real seed = Hill Dwarf) → 409 `race_not_gnome`
    with `got_race` echo. Race-gate regression guard against the trait
    firing for non-Gnomes."""
    tavik = tavik_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/check_artificers_lore",
        json={"character_id": tavik["id"]},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["error"] == "race_not_gnome"
    assert body["char_name"] == tavik["name"]
    assert "dwarf" in (body["got_race"] or "").lower()


async def test_artificers_lore_missing_character_id_400(gm_client):
    """Body without character_id is rejected at the input gate."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/check_artificers_lore",
        json={},
    )
    assert resp.status_code == 400


async def test_artificers_lore_echoes_note(gm_client, gm_ws, tavik_rested):
    """Tavik PATCHed to "Rock Gnome" + note "Wand of Magic Detection"
    → response carries note verbatim; feature_desc broadcast
    contains the note text."""
    tavik = tavik_rested
    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/sheet-json",
    )
    orig_race = (snap.json().get("sheet") or {}).get("race") or "Hill Dwarf"
    note = "Wand of Magic Detection"
    try:
        await _patch_race(gm_client, tavik["id"], "Rock Gnome")
        gm_ws.mark()
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/check_artificers_lore",
            json={"character_id": tavik["id"], "note": note},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["note"] == note

        await asyncio.sleep(0.2)
        fu = [
            m for m in gm_ws.buffered("feature_used")
            if (m.get("data") or {}).get("source") == "artificers-lore"
            and (m.get("data") or {}).get("character_id") == tavik["id"]
        ]
        assert fu
        fu_data = fu[-1]["data"]
        assert fu_data["note"] == note
        assert note in (fu_data.get("feature_desc") or "")
    finally:
        await _patch_race(gm_client, tavik["id"], orig_race)
