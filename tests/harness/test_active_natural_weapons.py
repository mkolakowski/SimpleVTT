"""v2.158.25 — Phase 2 read site for the v2.158.20 Form of the
Beast buff.

GET /api/campaign/{cid}/active_natural_weapons?character_id=N
returns a list of attack-dict-shaped entries derived from active
natural-weapon-grant buffs (today: form-of-the-beast-active; future:
shape-change buffs reading the same effect-key contract).

Tests:
  - Krieger Barbarian (no buff) → empty list.
  - Krieger Path of the Beast + claws form installed via
    /use_form_of_the_beast → one entry: name contains "Claws",
    damage_type "slashing", range "5 ft", form="claws",
    source_buff_key "form-of-the-beast-active", attack_bonus carries
    "+" sign, damage expression contains the buff die "1d6".
  - Krieger + tail form → reach 10 ft, damage_type "piercing".
  - Unknown character_id → 404.
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


def _pc(cid, c, *, hp_max=75):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_krieger_in_battle(gm_client, krieger):
    """`_install_buff` requires an active battle."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_anw_kr_{krieger['id']}", krieger)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def _clear_battle(gm_client):
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [], "turn_index": 0, "round": 1, "active": False,
        },
    )


@pytest_asyncio.fixture
async def krieger_beast(gm_client, roster):
    """PATCH Krieger to Path of the Beast; restore to Berserker."""
    krieger = roster["Krieger Stonefist"]
    await _patch_sheet(
        gm_client, krieger["id"],
        {"subclass": "Path of the Beast"},
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


async def test_no_buff_returns_empty_list(
    gm_client, roster,
):
    """Krieger (any subclass), no Form-of-the-Beast buff → []."""
    krieger = roster["Krieger Stonefist"]
    await _clear_battle(gm_client)
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active_natural_weapons",
        params={"character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["character_id"] == krieger["id"]
    assert data["natural_weapons"] == []


async def test_claws_form_buff_returns_claws_entry(
    gm_client, krieger_beast,
):
    """Path of the Beast + claws → one entry: 1d6 slashing, reach 5."""
    krieger = krieger_beast
    await _seed_krieger_in_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_form_of_the_beast",
        json={"character_id": krieger["id"], "form": "claws"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["buff_installed"] is True
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active_natural_weapons",
        params={"character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    weapons = r.json()["natural_weapons"]
    assert len(weapons) == 1, (
        f"expected 1 natural weapon; got {weapons!r}"
    )
    w = weapons[0]
    assert "Claws" in w["name"]
    assert w["damage_type"] == "slashing"
    assert w["range"] == "5 ft"
    assert w["form"] == "claws"
    assert w["source_buff_key"] == "form-of-the-beast-active"
    assert "1d6" in w["damage"]
    assert w["attack_bonus"].startswith(("+", "-")), (
        f"attack_bonus should be a signed string; got {w['attack_bonus']!r}"
    )
    await _clear_battle(gm_client)


async def test_tail_form_buff_returns_tail_with_reach_10(
    gm_client, krieger_beast,
):
    """Tail form → reach 10 ft, piercing."""
    krieger = krieger_beast
    await _seed_krieger_in_battle(gm_client, krieger)
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_form_of_the_beast",
        json={"character_id": krieger["id"], "form": "tail"},
    )
    assert r.status_code == 200, r.text
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active_natural_weapons",
        params={"character_id": krieger["id"]},
    )
    assert r.status_code == 200, r.text
    weapons = r.json()["natural_weapons"]
    assert len(weapons) == 1
    w = weapons[0]
    assert w["form"] == "tail"
    assert w["range"] == "10 ft"
    assert w["damage_type"] == "piercing"
    assert "1d8" in w["damage"]
    await _clear_battle(gm_client)


async def test_active_natural_weapons_unknown_character_returns_404(
    gm_client,
):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active_natural_weapons",
        params={"character_id": 99999999},
    )
    assert r.status_code == 404, r.text
