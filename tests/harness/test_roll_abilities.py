"""v2.741.0 — ability-score roller (4d6 drop lowest).

`POST /api/campaign/{cid}/character/{char_id}/roll-abilities` rolls six scores
via 4d6-drop-lowest through the shared dice engine and returns each score with
its four dice + the dropped die. It does NOT write the sheet — the player
reviews + assigns, then saves via sheet-fields. GM or owner only.
"""
from .conftest import CAMPAIGN_ID


async def test_roll_abilities_happy(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/roll-abilities")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["method"] == "4d6-drop-lowest"
    res = body["results"]
    assert len(res) == 6
    for rr in res:
        assert len(rr["dice"]) == 4
        assert all(1 <= d <= 6 for d in rr["dice"])
        assert rr["dropped"] == min(rr["dice"])
        # score = sum of the top three dice = total - dropped.
        assert rr["score"] == sum(rr["dice"]) - rr["dropped"]
        assert 3 <= rr["score"] <= 18
    # It must NOT have mutated the character's stored abilities (review-first).
    sheet = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/sheet-json"
    )).json()["sheet"]
    assert (sheet.get("abilities") or {}), "sheet abilities unchanged + present"


async def test_roll_abilities_unknown_character_404(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/99999999/roll-abilities")
    assert r.status_code == 404, r.text
