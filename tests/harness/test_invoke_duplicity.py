"""v2.158.52 — Trickery Domain Cleric: Invoke Duplicity (Lv 2 CD)
+ Phase 2 read of the v2.158.3 `improved-duplicity` upgrade buff.

`/use_invoke_duplicity` is the base Channel Divinity feature
(Trickery Domain Cleric Lv 2+, PHB p.62): as an action, spend 1
Channel Divinity use to create an illusory duplicate of yourself
for 1 minute (concentration). Installs a 10-round
`invoke-duplicity-active` concentration buff.

This is also the **Phase 2 read site** for the v2.158.3
`improved-duplicity` buff (Trickery Cleric Lv 17+). RAW the Lv-17
upgrade raises the duplicate count from 1 to 4 (the 30-ft bonus
move + 120-ft range are identical at both tiers). The endpoint
walks the caster's combatant buffs for `improved-duplicity` and,
when present, reads `effects.invoke_duplicity_max_duplicates` (4)
instead of the Lv-2 baseline of 1 — flipping that install-only
buff to consumed.

Tests:
  - Happy Lv 2 → duplicates 1, improved False, CD 2 → 1,
    feature_used broadcast (source "invoke-duplicity").
  - Happy Lv 17 → install improved-duplicity first, then invoke
    → duplicates 4, improved True (the Phase 2 read).
  - Out of CD → 409 out_of_uses.
  - Wrong subclass (default Life Domain) → 409.
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


async def _read_sheet(gm_client, char_id):
    r = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert r.status_code == 200, r.text
    return r.json()["sheet"]


def _cd_resource(current: int, maximum: int) -> dict:
    return {
        "key": "channel-divinity",
        "name": "Channel Divinity",
        "current": current, "max": maximum, "reset": "short",
        "source": "cleric Lv 2",
        "class_slug": "cleric",
        "subclass_slug": "trickery",
        "desc": "Channel Divinity (Invoke Duplicity, Cloak of Shadows).",
        "manual": False,
    }


def _id_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "invoke-duplicity"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


def _pc(cid, c, *, hp_max=80):
    return {"id": cid, "char_id": c["id"], "name": c["name"],
            "initiative": 10, "hp_current": hp_max, "hp_max": hp_max,
            "buffs": [],
            "economy": {"action": False, "bonus": False,
                        "reaction": False, "movement": 0}}


async def _seed_tavik_in_battle(gm_client, tavik):
    """`_install_buff` requires an active battle. Seed a minimal
    one with Tavik so the endpoint can lay down its buff."""
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [_pc(f"tok_id_tavik_{tavik['id']}", tavik)],
            "turn_index": 0, "round": 1, "active": True,
        },
    )


async def _make_trickery_tavik(gm_client, roster, level, cd_current=2):
    """PATCH Tavik to Trickery Domain at `level` with a fresh CD
    pool. Returns (tavik, original_state) so the caller can restore."""
    tavik = roster["Brother Tavik Stonebrow"]
    original = await _read_sheet(gm_client, tavik["id"])
    orig_state = {
        "subclass": original.get("subclass"),
        "level": original.get("level"),
        "resources": original.get("resources") or [],
    }
    await _patch_sheet(
        gm_client, tavik["id"],
        {
            "subclass": "Trickery Domain",
            "level": level,
            "resources": [_cd_resource(cd_current, 2)],
        },
        class_slug="cleric",
    )
    return tavik, orig_state


async def _restore_tavik(gm_client, tavik, orig_state):
    await _patch_sheet(
        gm_client, tavik["id"],
        {
            "subclass": orig_state["subclass"] or "Life Domain",
            "level": orig_state["level"] or 8,
            "resources": orig_state["resources"],
        },
        class_slug="cleric",
    )


@pytest_asyncio.fixture
async def tavik_trickery_lv2(gm_client, roster):
    tavik, orig = await _make_trickery_tavik(gm_client, roster, 2)
    try:
        yield tavik
    finally:
        await _restore_tavik(gm_client, tavik, orig)


@pytest_asyncio.fixture
async def tavik_trickery_lv17(gm_client, roster):
    tavik, orig = await _make_trickery_tavik(gm_client, roster, 17)
    try:
        yield tavik
    finally:
        await _restore_tavik(gm_client, tavik, orig)


async def test_use_invoke_duplicity_happy_lv2(
    gm_client, gm_ws, tavik_trickery_lv2,
):
    """Lv 2 Trickery → 1 duplicate, improved False, CD 2 → 1,
    30 ft move, 120 ft range, action consumed, feature_used."""
    tavik = tavik_trickery_lv2
    await _seed_tavik_in_battle(gm_client, tavik)
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_invoke_duplicity",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["feature"] == "invoke-duplicity"
    assert data["duplicates"] == 1
    assert data["improved"] is False
    assert data["bonus_move_per_duplicate_ft"] == 30
    assert data["max_range_ft"] == 120
    assert data["cleric_level"] == 2
    assert data["channel_divinity_remaining"] == 1
    assert data["buff_installed"] is True
    await asyncio.sleep(0.3)
    feats = _id_broadcasts(gm_ws, tavik["id"])
    assert feats, "expected a feature_used broadcast for invoke-duplicity"
    assert feats[-1]["data"]["duplicates"] == 1
    assert feats[-1]["data"]["improved"] is False


async def test_use_invoke_duplicity_reads_improved_buff_lv17(
    gm_client, gm_ws, tavik_trickery_lv17,
):
    """Phase 2 read site: at Lv 17, installing the
    `improved-duplicity` upgrade buff first and then invoking
    Channel Divinity yields 4 duplicates (improved True) instead
    of the Lv-2 baseline of 1."""
    tavik = tavik_trickery_lv17
    await _seed_tavik_in_battle(gm_client, tavik)
    # Phase 1: install the upgrade buff via its own endpoint.
    r_up = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_improved_duplicity",
        json={"character_id": tavik["id"]},
    )
    assert r_up.status_code == 200, r_up.text
    assert r_up.json()["buff_installed"] is True
    # Phase 2: invoke and read the upgraded duplicate count.
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_invoke_duplicity",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["duplicates"] == 4, (
        f"expected 4 duplicates from improved-duplicity read; got {data}"
    )
    assert data["improved"] is True
    assert data["bonus_move_per_duplicate_ft"] == 30
    assert data["max_range_ft"] == 120
    assert data["cleric_level"] == 17
    await asyncio.sleep(0.3)
    feats = _id_broadcasts(gm_ws, tavik["id"])
    assert feats
    assert feats[-1]["data"]["duplicates"] == 4
    assert feats[-1]["data"]["improved"] is True


async def test_use_invoke_duplicity_out_of_cd(
    gm_client, roster,
):
    """No Channel Divinity uses left → 409 out_of_uses."""
    tavik, orig = await _make_trickery_tavik(gm_client, roster, 2, cd_current=0)
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_invoke_duplicity",
            json={"character_id": tavik["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        assert r.json().get("error") == "out_of_uses"
    finally:
        await _restore_tavik(gm_client, tavik, orig)


async def test_use_invoke_duplicity_wrong_subclass(
    gm_client, roster,
):
    """Default Tavik (Life Domain) → 409 wrong_subclass_or_level."""
    tavik = roster["Brother Tavik Stonebrow"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_invoke_duplicity",
        json={"character_id": tavik["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    assert r.json().get("error") == "wrong_subclass_or_level"
