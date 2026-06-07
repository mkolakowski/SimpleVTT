"""v2.105.0 — generic reroll framework (Phase 1: Lucky feat).

`POST /use_reroll {character_id, roll_id, feature_key}` spends a reroll
feature (registry `_REROLL_FEATURES`) to reroll a roll-log card's d20.
Phase 1 registers the Lucky feat (any d20, keep the better of old/new).
The `/roll` broadcast now carries `reroll_options` so the client knows
which reroll button(s) to show.

Demo fixture: Garrik Ironside (Fighter Lv 9) ships the Lucky feat +
3 luck points. The autouse `clean_pcs` long-rest resets the resource
to 3 before each test, so every test starts from a known 3 uses.

Tests:
  - happy: roll a d20 as Garrik → broadcast carries a `lucky`
    reroll_option (remaining 3, keep="better"); `/use_reroll` keeps the
    better d20, decrements 3 → 2, and broadcasts roll(reroll_feature) +
    feature_used(lucky-reroll) + resource_update.
  - error: unknown feature_key → 404; a character without the feature →
    409 out_of_uses; a non-d20 roll → 409 no_d20 (and no reroll_options).
"""
from .conftest import CAMPAIGN_ID


async def _roll(gm_client, gm_ws, expression, char_id, note="reroll test"):
    """Roll `expression` attributed to a character; return the `roll`
    broadcast data (carrying id + reroll_options)."""
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={"expression": expression, "character_id": char_id, "note": note},
    )
    assert r.status_code == 200, r.text
    msg = await gm_ws.wait_for("roll")
    return msg["data"]


async def test_lucky_reroll_keeps_better_and_decrements(
    gm_client, gm_ws, roster,
):
    garrik = roster["Garrik Ironside"]  # Fighter Lv 9 — has Lucky
    data = await _roll(gm_client, gm_ws, "1d20", garrik["id"])
    roll_id = data["id"]
    opts = data.get("reroll_options") or []
    lucky = next((o for o in opts if o["key"] == "lucky"), None)
    assert lucky is not None, (
        f"Garrik's d20 roll should offer a Lucky reroll option; got {opts}"
    )
    assert lucky["remaining"] == 3
    assert lucky["keep"] == "better"

    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reroll",
        json={"character_id": garrik["id"], "roll_id": roll_id,
              "feature_key": "lucky"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["feature_key"] == "lucky"
    assert body["remaining"] == 2, "Lucky should decrement 3 → 2"
    # keep-better guarantees the kept d20 is at least the original.
    assert body["kept_d20"] >= body["old_d20"]
    if body["took_new"]:
        # Only swaps in when the new d20 strictly beats the old.
        assert body["new_d20"] > body["old_d20"]
        assert body["kept_d20"] == body["new_d20"]
    else:
        assert body["new_total"] == body["old_total"]
        assert body["kept_d20"] == body["old_d20"]

    # Broadcasts: mutated roll + feature_used + resource_update.
    rmsg = await gm_ws.wait_for("roll")
    assert rmsg["data"]["reroll_feature"] == "lucky"
    assert rmsg["data"]["id"] == roll_id
    fu = await gm_ws.wait_for("feature_used")
    assert fu["data"]["source"] == "lucky-reroll"
    assert fu["data"]["roll_id"] == roll_id
    ru = await gm_ws.wait_for("resource_update")
    assert ru["data"]["key"] == "lucky"
    assert ru["data"]["current"] == 2


async def test_reroll_unknown_feature(gm_client, roster):
    """An unrecognized feature_key → 404 (checked before roll lookup)."""
    garrik = roster["Garrik Ironside"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reroll",
        json={"character_id": garrik["id"], "roll_id": 1,
              "feature_key": "definitely-not-a-feature"},
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"] == "unknown_feature"


async def test_reroll_feature_not_available(gm_client, roster):
    """A character without the feature → 409 out_of_uses (eligibility
    is checked before the roll lookup, so the roll_id is irrelevant)."""
    pip = roster["Pip Quickfingers"]  # Rogue — no Lucky feat
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reroll",
        json={"character_id": pip["id"], "roll_id": 1, "feature_key": "lucky"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "out_of_uses"


async def test_reroll_no_d20(gm_client, gm_ws, roster):
    """A roll with no d20 offers no reroll option and 409s no_d20."""
    garrik = roster["Garrik Ironside"]
    data = await _roll(gm_client, gm_ws, "2d6", garrik["id"], note="dmg")
    assert not (data.get("reroll_options") or []), (
        "a non-d20 roll must not offer a reroll option"
    )
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reroll",
        json={"character_id": garrik["id"], "roll_id": data["id"],
              "feature_key": "lucky"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "no_d20"
