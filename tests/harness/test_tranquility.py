"""v2.1016.0 — Tranquility (Way of the Open Hand Monk Lv 11+, PHB p.79).

"At the end of a long rest, you gain the effect of a sanctuary spell
that lasts until the start of your next long rest. The saving throw DC
equals 8 + your Wisdom modifier + your proficiency bonus." Way of the
Open Hand is the SRD monk subclass, so Tranquility is SRD-valid. Kael
Brightleaf (Monk Open Hand Lv 5) is the demo fixture, PATCH'd to Lv 11.
`_install_buff` needs an active battle, so the happy path seeds one.

Because Tranquility installs the SAME `sanctuary` buff the Sanctuary
spell uses, the existing attacker-must-Wis-save gate enforces it for
free — the buff's `effects.dc` + `sanctuary_attacker_must_save` are the
contract this test pins.

Tests:
  - Happy path: Kael@Lv11 → a `sanctuary` buff with `effects.dc` =
    8 + WIS mod + prof and the enforcement flags.
  - Level gate: Kael@Lv5 → 409.
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


def _pc(cid, c, *, hp_max=90):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed(gm_client, kael):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={"combatants": [_pc(f"tok_tq_kael_{kael['id']}", kael)],
              "turn_index": 0, "round": 1, "active": True},
    )


async def _sanctuary_buff(gm_client, char_id):
    buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs"
    )).json().get("buffs", [])
    return next(
        (b for b in buffs if (b or {}).get("key") == "sanctuary"), None)


async def test_tranquility_installs_sanctuary(gm_client, roster):
    """Kael@Lv11 → a sanctuary buff with effects.dc = 8 + WIS mod + prof
    and the attacker-must-save enforcement flag."""
    kael = roster["Kael Brightleaf"]
    await _patch_sheet(gm_client, kael["id"], {"level": 11},
                       class_slug="monk")
    try:
        await _seed(gm_client, kael)
        # Read the monk's WIS + prof to compute the expected DC.
        sj = (await gm_client.get(
            f"/api/campaign/{CAMPAIGN_ID}/character/{kael['id']}/sheet-json"
        )).json().get("sheet") or {}
        wis = int((sj.get("abilities") or {}).get("WIS") or 10)
        prof = int(sj.get("proficiency_bonus") or 2)
        expected_dc = 8 + (wis - 10) // 2 + prof
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_tranquility",
            json={"character_id": kael["id"]},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["buff_installed"] is True
        assert data["save_dc"] == expected_dc
        await asyncio.sleep(0.2)
        buff = await _sanctuary_buff(gm_client, kael["id"])
        assert buff is not None, "sanctuary buff missing after Tranquility"
        eff = buff.get("effects") or {}
        assert eff.get("dc") == expected_dc
        assert eff.get("sanctuary_attacker_must_save") is True
    finally:
        await _patch_sheet(gm_client, kael["id"], {"level": 5},
                           class_slug="monk")


async def test_tranquility_level_gate(gm_client, roster):
    """Kael at Lv 5 → 409 (Tranquility needs Lv 11)."""
    kael = roster["Kael Brightleaf"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tranquility",
        json={"character_id": kael["id"]},
    )
    assert r.status_code == 409, r.text
    assert r.json().get("error") == "wrong_subclass_or_level"


async def test_tranquility_missing_character_id(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tranquility",
        json={},
    )
    assert r.status_code == 400, r.text


async def test_tranquility_unknown_character(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_tranquility",
        json={"character_id": 99999999},
    )
    assert r.status_code == 404, r.text
