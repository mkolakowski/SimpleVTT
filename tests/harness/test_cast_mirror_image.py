"""Phase 4 complex-spell deep-dive — Mirror Image (L2 Illusion).

Mirror Image is the spell-validation suite's reference case for a
spell whose RAW mechanic is *deliberately* GM-narration-only. Unlike
Hold Person (paralyzed buff + repeated WIS save) or Polymorph (full
stat-block swap + concentration anchor), Mirror Image has:

  - NO dedicated cast endpoint (no /cast_mirror_image),
  - NO ``_SPELL_BUFF_MAP`` entry, and
  - a single catalog "cast" action with no save / attack / damage.

So it rides the generic ``/cast_spell`` path: it spends a slot and
broadcasts ``spell_cast``, but installs no engine buff. The RAW
3-duplicate misdirection (roll 1d20: 6+ with three dupes, 8+ with two,
11+ with one; duplicate AC = 10 + Dex mod; a hit pops one) is narrated
at the table, not modeled.

Two RAW facts make Mirror Image worth pinning:

  1. It is **non-concentration** (PHB) — a sorcerer can hold Mirror
     Image *and* a concentration spell at once. We assert the cast
     installs no ``concentration-mirror-image`` anchor and the
     response doesn't flag concentration, the inverse of the
     Polymorph deep-dive's ``concentration-polymorph`` assertion.
  2. It installs **no duplicate/AC buff** today. The narration-only
     contract is pinned so a future commit that adds real duplicate
     modeling is a conscious change to this test, not a silent drift.

Caster: Zara Emberfire (Tiefling Sorcerer 5) owns Mirror Image
natively at spell_index 9 (Fire Bolt/Mage Hand/Minor Illusion/
Prestidigitation/Shocking Grasp/Thaumaturgy/Shield/Magic Missile/
Burning Hands/**Mirror Image**/...). She has L2 slots.
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID
from .spell_catalog import load_all_spells

_SLUG = "mirror-image"
_MIRROR_INDEX = 9  # Zara's spell list, see module docstring.


async def _get_buff_keys(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    body = resp.json()
    keys = {(b or {}).get("key") for b in body.get("buffs") or []}
    keys |= {(b or {}).get("key") for b in body.get("sheet_buffs") or []}
    return keys


@pytest_asyncio.fixture
async def zara_rested(gm_client, roster):
    """Long-rest Zara so L2 slots are full before each cast."""
    zara = roster["Zara Emberfire"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "long"},
    )
    return zara


def test_mirror_image_present_in_catalog():
    """Catalog shape: L2 Illusion, Self range, 1-minute duration,
    non-concentration, and a single no-save/no-attack/no-damage
    action (the misdirection lives in prose, not the action grid)."""
    by_slug = {(s.get("slug") or ""): s for s in load_all_spells()}
    mi = by_slug.get(_SLUG)
    assert mi is not None, "mirror-image must be in the spell catalog"
    assert mi.get("level_int") == 2
    assert (mi.get("school") or "").lower() == "illusion"
    assert "self" in (mi.get("range") or "").lower()
    assert "minute" in (mi.get("duration") or "").lower()
    assert mi.get("concentration") is False
    actions = mi.get("actions") or []
    assert actions, "mirror-image must carry at least the cast action"
    for a in actions:
        assert not a.get("save_ability"), a
        assert not a.get("attack_roll"), a
        assert not a.get("damage"), a


async def test_cast_consumes_l2_slot_and_broadcasts(gm_client, gm_ws, zara_rested):
    """Zara casts Mirror Image at its base L2: a slot ticks down and
    the spell_cast broadcast carries the name / level / action timing
    the chat card reads."""
    zara = zara_rested
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": _MIRROR_INDEX,
            "slot_level": 2,
            "class_slug": "sorcerer",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["slot"]["level"] == 2
    assert data["slot"]["used"] >= 1

    msg = await gm_ws.wait_for("spell_cast")
    d = msg["data"]
    assert d["spell_name"] == "Mirror Image"
    assert d["spell_level"] == 2
    assert d["spell_casting_time"] == "1 action"
    # No engine-rolled damage/save action surfaces on the broadcast.
    dmgs = [a.get("damage") for a in (d.get("actions") or []) if a.get("damage")]
    assert not dmgs, f"Mirror Image carries no damage; got {dmgs}"


async def test_cast_is_non_concentration(gm_client, zara_rested):
    """RAW: Mirror Image is NOT concentration. The cast must not flag
    concentration on the response and must not install a
    ``concentration-mirror-image`` anchor on the caster — the inverse
    of the Polymorph deep-dive, and what lets a sorcerer hold it
    alongside a real concentration spell."""
    zara = zara_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": _MIRROR_INDEX,
            "slot_level": 2,
            "class_slug": "sorcerer",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert not resp.json().get("concentration"), (
        "Mirror Image must not flag concentration on the cast response"
    )
    keys = await _get_buff_keys(gm_client, zara["id"])
    assert "concentration-mirror-image" not in keys, keys
    assert not any("concentration" in (k or "") and "mirror" in (k or "")
                   for k in keys), keys


async def test_cast_installs_no_duplicate_or_ac_buff(gm_client, zara_rested):
    """Contract pin: the 3-duplicate misdirection mechanic is
    GM-narration-only — no ``mirror-image`` buff, no duplicate-count
    or AC-by-count effect is installed on the caster today. A future
    commit that models duplicates as a real buff updates this test on
    purpose rather than drifting silently."""
    zara = zara_rested
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
        json={
            "character_id": zara["id"],
            "spell_index": _MIRROR_INDEX,
            "slot_level": 2,
            "class_slug": "sorcerer",
            "override": True,
        },
    )
    assert resp.status_code == 200, resp.text
    keys = await _get_buff_keys(gm_client, zara["id"])
    assert not any("mirror" in (k or "") for k in keys), (
        f"Mirror Image installs no engine buff today; got {keys}"
    )
