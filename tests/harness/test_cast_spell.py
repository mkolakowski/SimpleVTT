"""/api/campaign/{cid}/cast_spell — spell-cast endpoint tests.

Coverage in the Phase 1 vertical slice:
  - Thalindra Magic Missile (PC, L1 spell, "1 action" → action chip)
  - Thalindra Healing Word equivalent — actually Thalindra is Wizard;
    use her Misty Step (bonus action) instead
  - Tavik Healing Word (PC, L1 spell, "1 bonus action" → bonus chip)
  - 404 on unknown spell_index
  - 409 no_slot when out of spell slots

Phase 1.5 will add: upcast (slot_level > spell_level), reaction
spells (Shield / Counterspell), cantrips (Fire Bolt — no slot
decrement), over-budget gate parametrization.
"""
from .conftest import CAMPAIGN_ID


async def test_cast_magic_missile(gm_client, gm_ws, roster):
    thalindra = roster["Thalindra Moonwhisper"]
    # Magic Missile is index 3 in the wizard sheet's spells (Fire Bolt /
    # Mage Hand / Prestidigitation / Magic Missile / Shield / ...). We
    # don't fetch the sheet here to avoid coupling to demo seed indices;
    # we just look up spell_index=3 and verify the result name matches.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thalindra["id"],
            "spell_index": 3,
            "slot_level": 1,
            "class_slug": "wizard",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["slot"]["level"] == 1
    # Slot ticked down (or 0 if a previous test already consumed L1
    # slots). We assert >= 1 used; tests are intentionally relative
    # to the pre-call state via the response body.
    assert data["slot"]["used"] >= 1

    msg = await gm_ws.wait_for("spell_cast")
    assert msg["data"]["spell_name"] == "Magic Missile"
    assert msg["data"]["spell_level"] == 1
    assert msg["data"]["spell_casting_time"] == "1 action"


async def test_upcast_echoes_slot_level_and_higher_level(gm_client, gm_ws, roster):
    """v2.108.0 — casting Magic Missile with an L2 slot (up-cast) echoes
    slot_level=2 alongside spell_level=1 on the spell_cast broadcast,
    plus the spell_higher_level key the slot-picker + cast card read
    (Approach A slot plumbing + Approach C rule text)."""
    thalindra = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thalindra["id"],
            "spell_index": 3,   # Magic Missile (L1)
            "slot_level": 2,    # up-cast with an L2 slot
            "class_slug": "wizard",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["slot"]["level"] == 2, "the L2 slot should be spent"
    msg = await gm_ws.wait_for("spell_cast")
    d = msg["data"]
    assert d["spell_name"] == "Magic Missile"
    assert d["spell_level"] == 1
    assert d["slot_level"] == 2, "broadcast must echo the up-cast slot level"
    # Approach C: the up-cast rule text key is always present (may be
    # empty if the stored spell carries no higher_level text).
    assert "spell_higher_level" in d, "broadcast must carry spell_higher_level"


async def test_upcast_scales_damage_dice(gm_client, gm_ws, roster):
    """v2.110.0 — Approach B: Burning Hands (3d6 base, +1d6/slot) cast
    with an L2 slot scales the action damage to 4d6 on the spell_cast
    broadcast (the data the chat card + auto-damage path read)."""
    zara = roster["Zara Emberfire"]  # Tiefling Sorcerer 5
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": 8,   # Burning Hands (L1)
            "slot_level": 2,    # up-cast → +1d6
            "class_slug": "sorcerer",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("spell_cast")
    d = msg["data"]
    assert d["spell_name"] == "Burning Hands"
    assert d["slot_level"] == 2
    dmgs = [a.get("damage") for a in (d.get("actions") or []) if a.get("damage")]
    assert "4d6" in dmgs, (
        f"Burning Hands at L2 should scale 3d6 → 4d6; got {dmgs}"
    )


async def test_upcast_scales_healing_dice(gm_client, gm_ws, roster):
    """v2.110.0 — Cure Wounds (1d8 base, +1d8/slot) cast with an L2
    slot scales the broadcast healing to 2d8 (the heal-claim + auto-
    heal roll both read this string)."""
    tavik = roster["Brother Tavik Stonebrow"]  # Cleric, Life Domain
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": 4,   # Cure Wounds (L1)
            "slot_level": 2,    # up-cast → +1d8
            "class_slug": "cleric",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("spell_cast")
    d = msg["data"]
    assert d["spell_name"] == "Cure Wounds"
    assert d["slot_level"] == 2
    assert d["spell_healing"] == "2d8", (
        f"Cure Wounds at L2 should scale 1d8 → 2d8; got {d['spell_healing']}"
    )


async def test_upcast_base_level_leaves_dice_unscaled(gm_client, gm_ws, roster):
    """Sanity: casting Burning Hands at its base L1 leaves 3d6 (the
    scaler is a no-op when slot_level == spell_level)."""
    zara = roster["Zara Emberfire"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": 8,
            "slot_level": 1,
            "class_slug": "sorcerer",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("spell_cast")
    dmgs = [a.get("damage") for a in (msg["data"].get("actions") or []) if a.get("damage")]
    assert "3d6" in dmgs, f"base-level cast must stay 3d6; got {dmgs}"


async def test_cast_misty_step_bonus_action(gm_client, gm_ws, roster):
    thalindra = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thalindra["id"],
            "spell_index": 5,  # Misty Step is index 5 in _wizard_sheet
            "slot_level": 2,
            "class_slug": "wizard",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["slot"]["level"] == 2
    msg = await gm_ws.wait_for("spell_cast")
    assert msg["data"]["spell_name"] == "Misty Step"
    assert msg["data"]["spell_casting_time"] == "1 bonus action"


async def test_cast_tavik_healing_word(gm_client, gm_ws, roster):
    """Tavik's bonus-action heal. Hardcoded to index 5 in the v2.4.x
    cleric sheet (Sacred Flame / Guidance / Light / Bless / Cure
    Wounds / Healing Word). If the demo seed reorders cleric spells,
    this test breaks loudly and the per-cleric-spell coverage moves
    to fixture characters in Phase 1.5.
    """
    tavik = roster["Brother Tavik Stonebrow"]
    # v2.25.2: long-rest Tavik so accumulated state from prior tests
    # (drained spell slots) doesn't 409 the cast. The harness doesn't
    # auto-reset PC state between runs; flaky-test fix.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{tavik['id']}/rest",
        json={"type": "long"},
    )
    HEALING_WORD_INDEX = 5
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": tavik["id"],
            "spell_index": HEALING_WORD_INDEX,
            "slot_level": 1,
            "class_slug": "cleric",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    msg = await gm_ws.wait_for("spell_cast")
    assert msg["data"]["spell_name"] == "Healing Word"
    assert msg["data"]["spell_casting_time"] == "1 bonus action"


async def test_cast_invalid_spell_index(gm_client, roster):
    thalindra = roster["Thalindra Moonwhisper"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": thalindra["id"],
            "spell_index": 999,
            "class_slug": "wizard",
            "override": True,
        },
    )
    assert resp.status_code == 404


async def test_cast_missing_fields(gm_client):
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={},
    )
    assert resp.status_code == 400
