"""v2.1013.0 — Peerless Skill (College of Lore Bard Lv 14+, PHB p.55).

"When you make an ability check, you can expend one use of Bardic
Inspiration. Roll a Bardic Inspiration die and add the number rolled to
your ability check." College of Lore is the SRD bard college, so
Peerless Skill is SRD-valid. Lyra Sunstrider (Bard College of Lore
Lv 6) is the demo fixture, PATCH'd to Lv 14 for the happy path. No
action/reaction cost — the only cost is one Bardic Inspiration use.

Tests:
  - Happy path: Lyra@Lv14 spends a BI use → +1d10 bonus returned,
    resource decremented, feature_used broadcast.
  - Out of uses: with 0 Bardic Inspiration → 409.
  - Level gate: Lyra@Lv6 → 409.
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


async def _bi_current(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    for res in (r.json().get("sheet") or {}).get("resources") or []:
        if (res.get("key") or "").lower() == "bardic-inspiration":
            return int(res.get("current") or 0)
    return None


async def _set_bi_current(gm_client, char_id, value):
    """Directly set the Bardic Inspiration current via sheet-fields
    (the resources list is a sheet field)."""
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    resources = (r.json().get("sheet") or {}).get("resources") or []
    for res in resources:
        if (res.get("key") or "").lower() == "bardic-inspiration":
            res["current"] = value
    await _patch_sheet(gm_client, char_id, {"resources": resources})


async def test_peerless_skill_adds_bonus(gm_client, gm_ws, roster):
    """Lyra@Lv14 spends one Bardic Inspiration → +1d10 bonus returned,
    the resource drops by one, and a feature_used(source=peerless-skill)
    broadcast carries the rolled bonus."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(gm_client, lyra["id"], {"level": 14},
                       class_slug="bard")
    try:
        await _set_bi_current(gm_client, lyra["id"], 3)
        before = await _bi_current(gm_client, lyra["id"])
        gm_ws.mark()
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_peerless_skill",
            json={"character_id": lyra["id"]},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["die_size"] == 10  # Lv 14 → d10
        assert 1 <= data["bonus"] <= 10
        assert data["remaining"] == before - 1
        after = await _bi_current(gm_client, lyra["id"])
        assert after == before - 1
        await asyncio.sleep(0.3)
        cards = [
            m for m in gm_ws.buffered("feature_used")
            if (m.get("data") or {}).get("source") == "peerless-skill"
            and (m.get("data") or {}).get("character_id") == lyra["id"]
        ]
        assert cards, "expected a peerless-skill feature_used broadcast"
        assert cards[-1]["data"]["dice_total"] == data["bonus"]
    finally:
        await _patch_sheet(gm_client, lyra["id"], {"level": 6},
                           class_slug="bard")


async def test_peerless_skill_out_of_uses(gm_client, roster):
    """Lyra@Lv14 with 0 Bardic Inspiration → 409 out_of_uses."""
    lyra = roster["Lyra Sunstrider"]
    await _patch_sheet(gm_client, lyra["id"], {"level": 14},
                       class_slug="bard")
    try:
        await _set_bi_current(gm_client, lyra["id"], 0)
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_peerless_skill",
            json={"character_id": lyra["id"]},
        )
        assert r.status_code == 409, r.text
        assert r.json().get("error") == "out_of_uses"
    finally:
        await _set_bi_current(gm_client, lyra["id"], 3)
        await _patch_sheet(gm_client, lyra["id"], {"level": 6},
                           class_slug="bard")


async def test_peerless_skill_level_gate(gm_client, roster):
    """Lyra at Lv 6 → 409 (Peerless Skill needs Lv 14)."""
    lyra = roster["Lyra Sunstrider"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_peerless_skill",
        json={"character_id": lyra["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json().get("error") == "wrong_subclass_or_level"


async def test_peerless_skill_missing_character_id(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_peerless_skill",
        json={},
    )
    assert r.status_code == 400, r.text


async def test_peerless_skill_unknown_character(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_peerless_skill",
        json={"character_id": 99999999},
    )
    assert r.status_code == 404, r.text
