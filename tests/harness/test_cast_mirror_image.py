"""Mirror Image (L2 Illusion) — Phase 4 deep-dive + the v2.543.0
mechanical cast endpoint (#57 of cast-and-broadcast-tail.md).

Originally Mirror Image was the suite's reference case for a
GM-narration-only spell (no endpoint, no buff, generic /cast_spell).
**v2.543.0 changes that:** a dedicated ``/cast_mirror_image`` endpoint
installs a ``mirror-image`` buff carrying ``mirror_image_duplicates``
(3) + ``mirror_image_ac`` (10 + DEX mod), and the ``/attack`` +
``/npc_attack`` hit path rolls the RAW deflection (3 dupes → 6+, 2 → 8+,
1 → 11+; a deflected hit that meets the duplicate AC pops one).

This file pins BOTH surfaces:
  - the catalog shape (unchanged);
  - the generic ``/cast_spell`` path, which still spends a slot +
    broadcasts but is **narration-only** (installs no buff) — the
    mechanical buff is the dedicated endpoint's job;
  - the new ``/cast_mirror_image`` endpoint: installs 3 duplicates,
    non-concentration, and the deflection mechanic spares the caster
    while destroying duplicates.

Caster: Zara Emberfire (Tiefling Sorcerer 5) owns Mirror Image
natively at spell_index 9 and has L2 slots.
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


async def _get_buffs(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs",
    )
    assert resp.status_code == 200, resp.text
    return resp.json().get("buffs") or []


def _tok(char, tid=None, buffs=None, init=10, hp=40):
    return {
        "id": tid or f"tok_mi_{char['id']}",
        "char_id": char["id"],
        "name": char["name"],
        "initiative": init,
        "hp_current": hp, "hp_max": hp,
        "buffs": buffs or [],
        "economy": {"action": False, "bonus": False,
                    "reaction": False, "movement": 0},
    }


async def _set_battle(gm_client, combatants):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": combatants, "turn_index": 0,
              "round": 1, "active": True},
    )


@pytest_asyncio.fixture
async def zara_rested(gm_client, roster):
    """Long-rest Zara so L2 slots are full before each cast."""
    zara = roster["Zara Emberfire"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{zara['id']}/rest",
        json={"type": "long"},
    )
    return zara


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(gm_client, roster):
    yield
    zara = roster.get("Zara Emberfire")
    if zara:
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/end_buff",
            json={"character_id": zara["id"], "key": "mirror-image"},
        )
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [], "turn_index": 0, "round": 1, "active": False},
    )


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
    """Zara casts Mirror Image at its base L2 via the generic path: a
    slot ticks down and the spell_cast broadcast carries the name /
    level / action timing the chat card reads."""
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
    dmgs = [a.get("damage") for a in (d.get("actions") or []) if a.get("damage")]
    assert not dmgs, f"Mirror Image carries no damage; got {dmgs}"


async def test_cast_is_non_concentration(gm_client, zara_rested):
    """RAW: Mirror Image is NOT concentration. The cast must not flag
    concentration on the response and must not install a
    ``concentration-mirror-image`` anchor on the caster."""
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


async def test_generic_cast_spell_path_installs_no_buff(gm_client, zara_rested):
    """Contract pin: the *generic* /cast_spell path stays
    narration-only — it spends the slot + broadcasts but installs no
    ``mirror-image`` buff. The mechanical duplicates live behind the
    dedicated ``/cast_mirror_image`` endpoint (asserted below), so a
    spell-grid cast and the dedicated cast stay distinguishable."""
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
        f"the generic /cast_spell path installs no engine buff; got {keys}"
    )


async def test_cast_mirror_image_installs_three_duplicates(gm_client, roster):
    """The dedicated endpoint installs a buff with 3 duplicates + AC =
    10 + DEX mod, non-concentration, 10 rounds."""
    zara = roster["Zara Emberfire"]
    await _set_battle(gm_client, [_tok(zara)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mirror_image",
        json={"character_id": zara["id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["feature"] == "mirror-image"
    assert body["duplicates"] == 3
    assert body["duplicate_ac"] >= 10
    assert body["duration_rounds"] == 10

    buffs = await _get_buffs(gm_client, zara["id"])
    mi = next((b for b in buffs if b.get("key") == "mirror-image"), None)
    assert mi is not None, f"buff missing: {buffs}"
    eff = mi.get("effects") or {}
    assert int(eff.get("mirror_image_duplicates") or 0) == 3
    assert int(eff.get("mirror_image_ac") or 0) == body["duplicate_ac"]
    assert mi.get("concentration") is False


async def test_mirror_image_deflects_attacks_and_destroys_duplicates(
    gm_client, roster,
):
    """Attacks against the Mirror-Image caster deflect onto a duplicate:
    a deflected swing met the caster's AC yet leaves ``hit`` False +
    ``damage_applied`` 0, and duplicates are destroyed (count
    decrements toward 0)."""
    zara = roster["Zara Emberfire"]
    pip = roster["Pip Quickfingers"]
    zara_tok = "tok_mi_caster"
    await _set_battle(gm_client, [
        # Generous HP so non-deflected hits don't drop her mid-loop.
        _tok(zara, zara_tok, init=5, hp=500),
        _tok(pip, "tok_mi_pip", init=20),
    ])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mirror_image",
        json={"character_id": zara["id"]},
    )
    assert r.status_code == 200, r.text

    deflected_once = False
    saw_decrement = False
    # 3 duplicates deflect ~75% of hits; 40 swings makes a flake
    # vanishingly unlikely.
    for _ in range(40):
        a = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={"character_id": pip["id"], "attack_index": 0,
                  "target_combatant_id": zara_tok, "override": True},
        )
        assert a.status_code == 200, a.text
        j = a.json()
        mi = j.get("mirror_image")
        if not mi:
            continue
        if mi.get("deflected"):
            deflected_once = True
            # The caster is spared despite the swing meeting her AC.
            assert j["hit"] is False, j
            assert j["damage_applied"] == 0, j
            if int(mi.get("remaining", 3)) < 3:
                saw_decrement = True
            if int(mi.get("remaining", 3)) <= 0:
                break  # all duplicates spent — buff is gone
    assert deflected_once, "expected ≥1 Mirror Image deflection over 40 swings"
    assert saw_decrement, "expected ≥1 duplicate to be destroyed"


async def test_cast_mirror_image_non_caster_rejected(gm_client, roster):
    """Krieger (Barbarian) → 409 cannot_cast."""
    krieger = roster["Krieger Stonefist"]
    await _set_battle(gm_client, [_tok(krieger)])
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mirror_image",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "cannot_cast"
    assert "mirror image" in r.json()["expected"].lower()


async def test_cast_mirror_image_missing_character_id_400(gm_client):
    """Missing character_id → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/cast_mirror_image",
        json={},
    )
    assert r.status_code == 400, r.text
