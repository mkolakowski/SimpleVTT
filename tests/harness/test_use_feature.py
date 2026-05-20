"""/api/campaign/{cid}/use_feature — class-feature use endpoint tests.

Coverage in the Phase 1 vertical slice:
  - Pip's Cunning Action: Dash (bonus slot)
  - Pip's Cunning Action: Disengage (bonus slot)
  - Pip's Cunning Action: Hide (bonus slot)
  - Tavik's Channel Divinity: Turn Undead (action slot — uses
    /use_feature directly, not the resource counter; the v2.9.0
    picker chains both endpoints but this test just hits use_feature)
  - 404 on unknown feature_key
  - 400 on missing fields

The use_feature endpoint doesn't decrement any counter on its own —
it only announces the feature use + marks the action-economy slot.
The CD counter decrement happens via /character/{cid}/resource which
the picker calls separately; tests for that path are filed for
Phase 1.5.
"""
from .conftest import CAMPAIGN_ID


async def test_cunning_action_dash(gm_client, gm_ws, roster):
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": pip["id"],
            "feature_key": "cunning-action",
            "option_key": "dash",
            "label": "Cunning Action",
            "desc": "Move up to your speed again this turn.",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["slot"] == "bonus"
    assert "Cunning Action" in data["feature_label"]
    assert "Dash" in data["feature_label"]

    msg = await gm_ws.wait_for("feature_used")
    assert msg["data"]["source"] == "class-feature"
    assert "Cunning Action" in msg["data"]["feature_name"]
    assert "Dash" in msg["data"]["feature_name"]


async def test_cunning_action_disengage(gm_client, gm_ws, roster):
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": pip["id"],
            "feature_key": "cunning-action",
            "option_key": "disengage",
            "label": "Cunning Action",
            "override": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["slot"] == "bonus"
    msg = await gm_ws.wait_for("feature_used")
    assert "Disengage" in msg["data"]["feature_name"]


async def test_cunning_action_hide(gm_client, gm_ws, roster):
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": pip["id"],
            "feature_key": "cunning-action",
            "option_key": "hide",
            "label": "Cunning Action",
            "override": True,
        },
    )
    assert resp.status_code == 200
    msg = await gm_ws.wait_for("feature_used")
    assert "Hide" in msg["data"]["feature_name"]


async def test_channel_divinity_turn_undead(gm_client, gm_ws, roster):
    """Channel Divinity → Turn Undead is an action (not bonus).
    Tests that the slot resolution per the curated table is correct."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": tavik["id"],
            "feature_key": "channel-divinity",
            "option_key": "turn-undead",
            "label": "Channel Divinity",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["slot"] == "action"

    msg = await gm_ws.wait_for("feature_used")
    assert "Channel Divinity" in msg["data"]["feature_name"]
    assert "Turn Undead" in msg["data"]["feature_name"]


async def test_channel_divinity_sacred_weapon(gm_client, gm_ws, roster):
    """v2.14.3: Paladin Devotion options join the curated table.
    Sacred Weapon resolves to slot=action (same as the Cleric CD
    options); /use_feature accepts it without subclass filtering
    (filter is client-side in the picker)."""
    caelan = roster["Sir Caelan Lightbringer"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": caelan["id"],
            "feature_key": "channel-divinity",
            "option_key": "sacred-weapon",
            "label": "Channel Divinity",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["slot"] == "action"
    msg = await gm_ws.wait_for("feature_used")
    assert "Sacred Weapon" in msg["data"]["feature_name"]


async def test_channel_divinity_turn_the_unholy(gm_client, gm_ws, roster):
    """The other Devotion option. Same shape as Sacred Weapon."""
    caelan = roster["Sir Caelan Lightbringer"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": caelan["id"],
            "feature_key": "channel-divinity",
            "option_key": "turn-the-unholy",
            "label": "Channel Divinity",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["slot"] == "action"
    msg = await gm_ws.wait_for("feature_used")
    assert "Turn The Unholy" in msg["data"]["feature_name"] or "Turn the Unholy" in msg["data"]["feature_name"]


async def test_channel_divinity_preserve_life(gm_client, gm_ws, roster):
    """Preserve Life is Life-Domain-specific. /use_feature itself
    doesn't filter by subclass — the v2.9.0 picker does — so the
    server accepts the option regardless. Subclass filtering is the
    client's responsibility."""
    tavik = roster["Brother Tavik Stonebrow"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": tavik["id"],
            "feature_key": "channel-divinity",
            "option_key": "preserve-life",
            "label": "Channel Divinity",
            "override": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["slot"] == "action"


async def test_divine_sense_announces(gm_client, gm_ws, roster):
    """v2.15.6: Divine Sense is the Paladin Lv 1 announce-only feature.
    /use_feature accepts the curated key and broadcasts feature_used
    with slot=action. Caelan (Lv 5 Oath of Devotion Paladin) is the
    demo's eligible PC.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": caelan["id"],
            "feature_key": "divine-sense",
            "label": "Divine Sense",
            "desc": "Detect celestial / fiend / undead within 60 ft.",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["slot"] == "action"
    assert "Divine Sense" in data["feature_label"]

    msg = await gm_ws.wait_for("feature_used")
    assert msg["data"]["source"] == "class-feature"
    assert "Divine Sense" in msg["data"]["feature_name"]


async def test_cleansing_touch_curated(gm_client, gm_ws, roster):
    """v2.15.6: Cleansing Touch (Paladin Lv 14) is in the curated
    table for forward compat — the server accepts the slug even
    though Caelan is only Lv 5 (RAW eligibility is client-side; the
    server doesn't enforce class level on /use_feature). When a
    future Lv 14+ Paladin fixture lands, this test confirms the
    table entry is wired correctly.
    """
    caelan = roster["Sir Caelan Lightbringer"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": caelan["id"],
            "feature_key": "cleansing-touch",
            "label": "Cleansing Touch",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["slot"] == "action"
    msg = await gm_ws.wait_for("feature_used")
    assert "Cleansing Touch" in msg["data"]["feature_name"]


async def test_indomitable_curated(gm_client, gm_ws, roster):
    """v2.16.2: Indomitable (Fighter Lv 9+) is in the curated table for
    forward compat — the server accepts the slug even though Pip is a
    Rogue (no enforcement of class eligibility on /use_feature; client
    filters via class_features rendering). slot:'free' because the
    save-reroll doesn't consume an action/bonus/reaction.
    """
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": pip["id"],
            "feature_key": "indomitable",
            "label": "Indomitable",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["slot"] == "free"
    msg = await gm_ws.wait_for("feature_used")
    assert "Indomitable" in msg["data"]["feature_name"]


async def test_stroke_of_luck_curated(gm_client, gm_ws, roster):
    """v2.16.2: Stroke of Luck (Rogue Lv 20) curated table entry.
    Future Lv 20 Rogue fixture + (B) roll-time intercept needed for
    the proper miss-to-hit / fail-to-20 UX; today the slug is
    accepted and the chat card announces it generically.
    """
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": pip["id"],
            "feature_key": "stroke-of-luck",
            "label": "Stroke of Luck",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["slot"] == "free"
    msg = await gm_ws.wait_for("feature_used")
    assert "Stroke of Luck" in msg["data"]["feature_name"]


async def test_font_of_magic_curated(gm_client, gm_ws, roster):
    """v2.16.2: Font of Magic (Sorcerer Lv 2) curated table entry.
    Demo has no Sorcerer; the slug is server-accepted for forward
    compat. Full SP↔slot conversion picker ships when a Sorcerer
    fixture lands (Phase A.4+).
    """
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": pip["id"],
            "feature_key": "font-of-magic",
            "label": "Font of Magic",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["slot"] == "free"
    msg = await gm_ws.wait_for("feature_used")
    assert "Font of Magic" in msg["data"]["feature_name"]


async def test_action_surge_is_free(gm_client, gm_ws, roster):
    """Action Surge doesn't consume an economy slot (slot='free').
    The chip should NOT flip when this fires."""
    # No Fighter PC in the demo, so we use Pip just to exercise the
    # 'free' slot resolution path. Slot validation is by feature_key,
    # not by character class.
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": pip["id"],
            "feature_key": "action-surge",
            "label": "Action Surge",
            "override": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["slot"] == "free"


async def test_unknown_feature_key(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": pip["id"],
            "feature_key": "nonexistent-feature",
            "override": True,
        },
    )
    assert resp.status_code == 404


async def test_missing_required_fields(gm_client):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={},
    )
    assert resp.status_code == 400


async def test_feature_desc_falls_back_when_client_omits(gm_client, gm_ws, roster):
    """v2.43.11: /use_feature looks up a curated description from
    _FEATURE_ECONOMY when the client request didn't include a ``desc``.
    Asserts the broadcast's ``feature_desc`` is non-empty for a known
    feature even when no desc was sent, AND that the option-specific
    desc takes precedence over the parent feature's desc.
    """
    pip = roster["Pip Quickfingers"]
    # No ``desc`` in the body. Server should fall back to the disengage
    # option's curated desc.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": pip["id"],
            "feature_key": "cunning-action",
            "option_key": "disengage",
            "label": "Cunning Action",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("feature_used")
    desc = msg["data"]["feature_desc"]
    assert desc, "expected feature_desc to be populated by server-side fallback"
    assert "opportunity" in desc.lower() or "movement" in desc.lower(), (
        f"expected disengage-specific desc, got: {desc!r}"
    )


async def test_feature_desc_client_override_wins(gm_client, gm_ws, roster):
    """When the client DOES send a desc, it overrides the server table."""
    pip = roster["Pip Quickfingers"]
    custom_desc = "Pip nimbly disengages, leaving no opening."
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_feature",
        json={
            "character_id": pip["id"],
            "feature_key": "cunning-action",
            "option_key": "disengage",
            "label": "Cunning Action",
            "desc": custom_desc,
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("feature_used")
    assert msg["data"]["feature_desc"] == custom_desc
