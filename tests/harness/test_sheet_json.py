"""v2.117.0 — GET /api/campaign/{cid}/character/{id}/sheet-json.

Read-only JSON view of a character's sheet (the other character GETs
render HTML). Gated to the GM or the character's owner. Enables
restore-safe test fixtures (snapshot a field before patching) + clients
that want the raw sheet.

Tests:
  - happy: GM reads Garrik → 200, sheet carries his class + resources.
  - 404 unknown character.
  - 403 when a non-owner non-GM (alice) reads a GM-owned character.
"""
from .conftest import CAMPAIGN_ID


async def test_sheet_json_returns_sheet(gm_client, roster):
    garrik = roster["Garrik Ironside"]
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-json",
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["character_id"] == garrik["id"]
    assert body["name"] == "Garrik Ironside"
    sheet = body["sheet"]
    assert (sheet.get("class") or "").lower() == "fighter"
    # Resources (lucky / second-wind / action-surge / indomitable) ride
    # the sheet — the data restore-safe fixtures need to snapshot.
    res_keys = {(x or {}).get("key") for x in (sheet.get("resources") or [])}
    assert "lucky" in res_keys, f"expected Garrik's resources; got {res_keys}"


async def test_sheet_json_unknown_character(gm_client):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/999999/sheet-json",
    )
    assert r.status_code == 404, r.text


async def test_sheet_json_forbidden_for_non_owner(alice_client, roster):
    """Alice (not GM) reading a GM-owned character → 403."""
    garrik = roster["Garrik Ironside"]  # GM-owned in the demo
    r = await alice_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-json",
    )
    assert r.status_code == 403, r.text
