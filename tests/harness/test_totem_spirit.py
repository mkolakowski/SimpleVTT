"""v2.99.364 — Path of the Totem Warrior Barbarian: Totem Spirit (G Barbarian batch OPEN, Lv 3+, PHB).

Phase G Barbarian Paths subclass batch OPEN — Path of the Totem
Warrior is the first new path beyond the already-shipped Path of
the Berserker.
RAW PHB p.50: at 3rd level choose a totem — Bear (resistance to
all damage except psychic while raging), Eagle (OA disadvantage +
Dash as bonus action while raging), or Wolf (allies get advantage
on melee vs enemies within 5 ft while raging).

v1 announce-only — the chosen totem's passive rage effect is
GM-tracked. No action cost.

Krieger Stonefist (Barbarian, PATCHed to Path of the Totem Warrior
Lv 7) is the demo fixture.

Tests:
  - Lv 7 happy (default bear): totem bear, benefit text present.
  - Lv 7 happy (wolf): totem echoes "wolf".
  - Wrong subclass (default Berserker) → 409.
  - Invalid totem → 400.
"""
import asyncio
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


def _ts_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "totem-spirit"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def krieger_totem(gm_client, roster):
    """PATCH Krieger to Path of the Totem Warrior; restore to Berserker."""
    krieger = roster["Krieger Stonefist"]
    await _patch_sheet(
        gm_client, krieger["id"],
        {"subclass": "Path of the Totem Warrior"},
        class_slug="barbarian",
    )
    try:
        yield krieger
    finally:
        await _patch_sheet(
            gm_client, krieger["id"],
            {"subclass": "Path of the Berserker"},
            class_slug="barbarian",
        )


async def test_use_ts_happy_bear(
    gm_client, gm_ws, krieger_totem,
):
    """Lv 7 Totem Warrior, default → bear totem benefit."""
    krieger = krieger_totem
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_totem_spirit",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["feature"] == "totem-spirit"
    assert data["totem"] == "bear"
    assert "psychic" in data["benefit"].lower()
    assert data["barbarian_level"] == 7
    await asyncio.sleep(0.3)
    feats = _ts_broadcasts(gm_ws, krieger["id"])
    assert feats
    assert feats[-1]["data"]["totem"] == "bear"


async def test_use_ts_happy_wolf(
    gm_client, krieger_totem,
):
    """totem=wolf echoes through."""
    krieger = krieger_totem
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_totem_spirit",
        json={"character_id": krieger["id"], "totem": "wolf"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["totem"] == "wolf"


async def test_use_ts_wrong_subclass(
    gm_client, roster,
):
    """Default Krieger (Berserker) → 409."""
    krieger = roster["Krieger Stonefist"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_totem_spirit",
        json={"character_id": krieger["id"]},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_ts_invalid_totem(
    gm_client, krieger_totem,
):
    """Invalid totem → 400."""
    krieger = krieger_totem
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_totem_spirit",
        json={"character_id": krieger["id"], "totem": "tiger"},
    )
    assert r.status_code == 400, r.text


async def _seed_krieger_in_battle(gm_client, krieger):
    """v2.612.2 — `_install_buff` requires an active battle."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [{
                "id": f"tok_ts_kr_{krieger['id']}", "char_id": krieger["id"],
                "name": krieger["name"], "initiative": 12,
                "hp_current": 80, "hp_max": 80, "buffs": [],
                "economy": {"action": False, "bonus": False,
                            "reaction": False, "movement": 0},
            }],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def _krieger_buff(gm_client, char_id, key):
    buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/buffs"
    )).json().get("buffs", [])
    return next((b for b in buffs if b.get("key") == key), None)


async def test_ts_buff_payload_carries_totem_params(
    gm_client, krieger_totem,
):
    """v2.612.2 — Phase 8 state contract: using Totem Spirit installs a
    permanent `totem-spirit-active` buff carrying the chosen totem's
    parameter payload, all rage-gated (`totem_spirit_requires_rage`).
    Bear carries the resistance-except-psychic shape; a re-press with a
    different totem (eagle) overwrites the params (`_install_buff` refresh
    semantics) since a barbarian has exactly one Totem Spirit. Phase 2
    (deferred) reads these flags at the rage read sites. Seeds a battle
    because `_install_buff` requires one."""
    krieger = krieger_totem
    await _seed_krieger_in_battle(gm_client, krieger)

    # Bear → resistance-to-all-except-psychic while raging.
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_totem_spirit",
        json={"character_id": krieger["id"], "totem": "bear"},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("buff_installed") is True
    buff = await _krieger_buff(gm_client, krieger["id"], "totem-spirit-active")
    assert buff is not None, "totem-spirit-active buff missing after bear install"
    effects = buff.get("effects") or {}
    assert effects.get("totem_spirit_active") is True
    assert effects.get("totem_spirit_totem") == "bear"
    assert effects.get("totem_spirit_requires_rage") is True
    assert effects.get("totem_spirit_resistance_except") == ["psychic"]
    # Permanent passive — no concentration, very long duration.
    assert buff.get("concentration") in (False, None)
    assert int(buff.get("duration_rounds") or 0) >= 1000

    # Switch to Eagle → the buff's params must overwrite (one totem only).
    r2 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_totem_spirit",
        json={"character_id": krieger["id"], "totem": "eagle"},
    )
    assert r2.status_code == 200, r2.text
    buff2 = await _krieger_buff(gm_client, krieger["id"], "totem-spirit-active")
    assert buff2 is not None
    effects2 = buff2.get("effects") or {}
    assert effects2.get("totem_spirit_totem") == "eagle"
    assert effects2.get("totem_spirit_oa_disadvantage") is True
    assert effects2.get("totem_spirit_dash_bonus_action") is True
    # Bear-only flag must be gone after the overwrite.
    assert "totem_spirit_resistance_except" not in effects2, (
        f"eagle install should overwrite bear params; got {effects2}"
    )
