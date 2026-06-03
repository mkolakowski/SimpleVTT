"""v2.99.143 — /use_beguiling_influence endpoint tests.

Beguiling Influence is a Warlock Lv 2+ Eldritch Invocation: gain
proficiency in Deception + Persuasion (PHB p.110). A passive
invocation — the proficiencies are stamped on the sheet at seed
time. The endpoint is a chat-log declaration for social-scene
moments ("I use Beguiling Influence to charm the bartender")
where the GM wants the table to see the bonus claimed.

Magnus's seed (v2.99.143):
  - Adds `eldritch-invocation-beguiling-influence` to feats.
  - Stamps `Persuasion` proficiency on skills with
    `source: "beguiling-influence"` (Deception was already on
    his sheet via the Charlatan background).

Tests:
  - happy path (Magnus has the invocation) → 200 + WS feature_used
    broadcast with `source: beguiling-influence` and
    `skill_proficiencies: ["Deception", "Persuasion"]`
  - missing invocation (Krieger Barbarian) → 409 missing_invocation
  - missing character_id → 400
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def test_use_beguiling_influence_happy_path(gm_client, gm_ws, roster):
    """Magnus has the invocation. Endpoint returns 200 + emits the
    audit broadcast with the two skill proficiencies.
    """
    magnus = roster["Magnus Hexbinder"]
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_beguiling_influence",
        json={"character_id": magnus["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["character_id"] == magnus["id"]
    assert data["skill_proficiencies"] == ["Deception", "Persuasion"]
    msg = await gm_ws.wait_for("feature_used")
    bd = msg["data"]
    assert bd.get("source") == "beguiling-influence"
    assert bd.get("character_id") == magnus["id"]
    assert bd.get("skill_proficiencies") == ["Deception", "Persuasion"]


async def test_use_beguiling_influence_without_invocation_409(
    gm_client, roster,
):
    """Krieger (Barbarian) → 409 missing_invocation."""
    krieger = roster["Krieger Stonefist"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_beguiling_influence",
        json={"character_id": krieger["id"]},
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data.get("error") == "missing_invocation"
    assert data.get("invocation") == "beguiling-influence"


async def test_use_beguiling_influence_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_beguiling_influence",
        json={},
    )
    assert resp.status_code == 400, resp.text
