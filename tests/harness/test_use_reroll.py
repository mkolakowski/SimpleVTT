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

v2.107.0 — Phase 3 folds the save-only reroll features into the same
registry/endpoint:
  - a SAVE roll for a Lv 9 Fighter offers both `lucky` (any) and
    `indomitable` (save-only); `/use_reroll {feature_key:"indomitable"}`
    takes the new d20 (keep="new") and decrements the resource.
  - a non-save d20 offers `lucky` but NOT `indomitable` (applies-gating).
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


async def test_reroll_button_on_server_rendered_history(gm_client, roster):
    """v2.115.0 — a d20 rolled as a Lucky-feat character persists its
    character_id, so the server-rendered roll history (page reload, not
    just live WS) renders the reroll button."""
    garrik = roster["Garrik Ironside"]
    rr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={"expression": "1d20", "character_id": garrik["id"],
              "note": "ssr-reroll-test"},
    )
    assert rr.status_code == 200, rr.text
    page = await gm_client.get(f"/campaign/{CAMPAIGN_ID}")
    assert page.status_code == 200, page.status_code
    html = page.text
    assert "reroll-btn" in html, (
        "server-rendered roll history should carry reroll buttons"
    )
    assert "Lucky reroll" in html, (
        "Garrik's d20 should offer a Lucky reroll in the SSR history"
    )


async def test_reroll_button_on_rolls_popout(gm_client, roster):
    """v2.116.0 — the rolls popout (/campaign/{id}/rolls) also renders
    the reroll button for a Lucky-feat character's past d20 roll."""
    garrik = roster["Garrik Ironside"]
    rr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={"expression": "1d20", "character_id": garrik["id"],
              "note": "popout-reroll-test"},
    )
    assert rr.status_code == 200, rr.text
    page = await gm_client.get(f"/campaign/{CAMPAIGN_ID}/rolls")
    assert page.status_code == 200, page.status_code
    html = page.text
    assert "rr-btn" in html, "popout roll history should carry reroll buttons"
    assert "Lucky reroll" in html


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


@pytest_asyncio.fixture
async def garrik_lv9_indomitable(gm_client, roster):
    """Garrik at Lv 9 with a full Indomitable resource. v2.117.0 —
    restore-safe: snapshots his original level + resources via the
    sheet-json endpoint and restores them in teardown (was wiping
    resources to [], destroying his Lucky etc. for downstream tests)."""
    garrik = roster["Garrik Ironside"]
    _snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{garrik['id']}/sheet-json",
    )
    _orig = (_snap.json() or {}).get("sheet") or {}
    _orig_level = _orig.get("level")
    _orig_resources = _orig.get("resources") or []
    await _patch_sheet(gm_client, garrik["id"], {"level": 9}, class_slug="fighter")
    await _patch_sheet(gm_client, garrik["id"], {"resources": [
        {"key": "indomitable", "label": "Indomitable",
         "current": 1, "max": 1, "reset": "long"},
    ]})
    try:
        yield garrik
    finally:
        if _orig_level is not None:
            await _patch_sheet(
                gm_client, garrik["id"], {"level": _orig_level},
                class_slug="fighter",
            )
        await _patch_sheet(gm_client, garrik["id"], {"resources": _orig_resources})


async def test_save_offers_lucky_and_indomitable_and_indomitable_takes_new(
    gm_client, gm_ws, garrik_lv9_indomitable,
):
    """A Lv 9 Fighter's SAVE roll offers both lucky (any) and
    indomitable (save-only); the indomitable reroll keeps the new d20
    (keep="new") and decrements the resource 1 → 0."""
    garrik = garrik_lv9_indomitable
    data = await _roll(
        gm_client, gm_ws, "1d20+2", garrik["id"],
    )
    # Re-roll the save with an explicit stat_key so it reads as a save.
    gm_ws.mark()
    rr = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/roll",
        json={"expression": "1d20+2", "character_id": garrik["id"],
              "stat_key": "wis_save", "note": "WIS saving throw"},
    )
    assert rr.status_code == 200, rr.text
    msg = await gm_ws.wait_for("roll")
    keys = {o["key"] for o in (msg["data"].get("reroll_options") or [])}
    assert "lucky" in keys, f"save should still offer Lucky; got {keys}"
    assert "indomitable" in keys, (
        f"a Lv 9 Fighter's save should offer Indomitable; got {keys}"
    )
    roll_id = msg["data"]["id"]

    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_reroll",
        json={"character_id": garrik["id"], "roll_id": roll_id,
              "feature_key": "indomitable"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["feature_key"] == "indomitable"
    assert body["took_new"] is True, "Indomitable must use the new roll"
    assert body["remaining"] == 0, "indomitable should decrement 1 → 0"


async def test_indomitable_hidden_on_non_save(
    gm_client, gm_ws, garrik_lv9_indomitable,
):
    """A non-save d20 for the same Fighter offers Lucky but NOT the
    save-only Indomitable (applies-gating)."""
    garrik = garrik_lv9_indomitable
    data = await _roll(gm_client, gm_ws, "1d20", garrik["id"], note="attack")
    keys = {o["key"] for o in (data.get("reroll_options") or [])}
    assert "lucky" in keys, f"expected Lucky on a plain d20; got {keys}"
    assert "indomitable" not in keys, (
        f"Indomitable is save-only and must not appear on a non-save "
        f"roll; got {keys}"
    )
