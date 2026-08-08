"""v2.1018.0 — Thief's Reflexes (Thief Rogue Lv 17+, PHB p.98).

"You can take two turns during the first round of any combat. You take
your first turn at your normal initiative and your second turn at your
initiative minus 10. You can't use this feature when you're surprised."
Thief is the SRD rogue subclass, so this is SRD-valid.

**Scoped v1 (announce + marker).** The full initiative-tracker second
turn is filed in docs/plans/thiefs-reflexes.md. This endpoint mechanizes
the contract: it validates Thief Rogue Lv 17+, an active round-1 battle,
not-surprised, and thief-in-initiative, then broadcasts the second-turn
initiative (base − 10). Pip Quickfingers (Rogue Thief Lv 7) is the demo
fixture, PATCH'd to Lv 17.

Tests:
  - Happy path: round 1 → second_turn_initiative = base − 10 + broadcast.
  - Round gate: round 2 → 409 not_first_round.
  - Surprised → 409.
  - Not in initiative → 409.
  - Level gate: Pip@Lv7 → 409.
  - Error paths: missing character_id → 400; unknown char → 404.
"""
import asyncio

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


def _pc(cid, c, *, initiative=18, hp_max=90):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": initiative, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed(gm_client, pip, *, round_no=1, include_pip=True, initiative=18):
    combatants = []
    if include_pip:
        combatants.append(_pc(f"tok_tr_pip_{pip['id']}", pip,
                              initiative=initiative))
    combatants.append({
        "id": f"tok_tr_bandit_{pip['id']}", "char_id": None, "name": "Bandit",
        "initiative": 12, "hp_current": 30, "hp_max": 30, "buffs": [],
        "economy": {"action": False, "bonus": False, "reaction": False,
                    "movement": 0}})
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": round_no, "active": True},
    )


async def test_thiefs_reflexes_second_turn_initiative(gm_client, gm_ws, roster):
    """Pip@Lv17 in round 1 → second_turn_initiative = base − 10 +
    a thiefs-reflexes broadcast."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(gm_client, pip["id"], {"level": 17},
                       class_slug="rogue")
    try:
        await _seed(gm_client, pip, round_no=1, initiative=18)
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_thiefs_reflexes",
            json={"character_id": pip["id"]},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["base_initiative"] == 18
        assert data["second_turn_initiative"] == 8
        assert data["round"] == 1
        await asyncio.sleep(0.3)
        cards = [
            m for m in gm_ws.buffered("feature_used")
            if (m.get("data") or {}).get("source") == "thiefs-reflexes"
            and (m.get("data") or {}).get("character_id") == pip["id"]
        ]
        assert cards
        assert cards[-1]["data"]["second_turn_initiative"] == 8
    finally:
        await _patch_sheet(gm_client, pip["id"], {"level": 7},
                           class_slug="rogue")


async def test_thiefs_reflexes_not_first_round(gm_client, roster):
    """Round 2 → 409 not_first_round."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(gm_client, pip["id"], {"level": 17},
                       class_slug="rogue")
    try:
        await _seed(gm_client, pip, round_no=2)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_thiefs_reflexes",
            json={"character_id": pip["id"]},
        )
        assert r.status_code == 409, r.text
        assert r.json().get("error") == "not_first_round"
    finally:
        await _patch_sheet(gm_client, pip["id"], {"level": 7},
                           class_slug="rogue")


async def test_thiefs_reflexes_surprised(gm_client, roster):
    """surprised=True → 409."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(gm_client, pip["id"], {"level": 17},
                       class_slug="rogue")
    try:
        await _seed(gm_client, pip, round_no=1)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_thiefs_reflexes",
            json={"character_id": pip["id"], "surprised": True},
        )
        assert r.status_code == 409, r.text
        assert r.json().get("error") == "surprised"
    finally:
        await _patch_sheet(gm_client, pip["id"], {"level": 7},
                           class_slug="rogue")


async def test_thiefs_reflexes_surprised_from_server_state(gm_client, roster):
    """v2.1058.0 — the surprise gate now reads the thief's server-side
    `surprised` combatant flag (set via /set_surprised), so no client
    `surprised` body flag is needed. 409 with `source: server_state`."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(gm_client, pip["id"], {"level": 17},
                       class_slug="rogue")
    try:
        await _seed(gm_client, pip, round_no=1)
        tok = f"tok_tr_pip_{pip['id']}"
        sr = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/set_surprised",
            json={"combatant_ids": [tok], "surprised": True})
        assert sr.status_code == 200, sr.text
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_thiefs_reflexes",
            json={"character_id": pip["id"]},  # no client `surprised`
        )
        assert r.status_code == 409, r.text
        d = r.json()
        assert d.get("error") == "surprised", d
        assert d.get("source") == "server_state", d
    finally:
        await _patch_sheet(gm_client, pip["id"], {"level": 7},
                           class_slug="rogue")


async def test_thiefs_reflexes_not_in_initiative(gm_client, roster):
    """Thief not in the initiative order → 409 not_in_initiative."""
    pip = roster["Pip Quickfingers"]
    await _patch_sheet(gm_client, pip["id"], {"level": 17},
                       class_slug="rogue")
    try:
        await _seed(gm_client, pip, round_no=1, include_pip=False)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_thiefs_reflexes",
            json={"character_id": pip["id"]},
        )
        assert r.status_code == 409, r.text
        assert r.json().get("error") == "not_in_initiative"
    finally:
        await _patch_sheet(gm_client, pip["id"], {"level": 7},
                           class_slug="rogue")


async def test_thiefs_reflexes_level_gate(gm_client, roster):
    """Pip at Lv 7 → 409 (Thief's Reflexes needs Lv 17)."""
    pip = roster["Pip Quickfingers"]
    await _seed(gm_client, pip, round_no=1)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_thiefs_reflexes",
        json={"character_id": pip["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json().get("error") == "wrong_subclass_or_level"


async def test_thiefs_reflexes_missing_character_id(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_thiefs_reflexes",
        json={},
    )
    assert r.status_code == 400, r.text


async def test_thiefs_reflexes_unknown_character(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_thiefs_reflexes",
        json={"character_id": 99999999},
    )
    assert r.status_code == 404, r.text
