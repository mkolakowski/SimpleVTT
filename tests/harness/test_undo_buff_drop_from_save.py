"""v2.97.77 — ``/undo_attack_damage`` restores a buff dropped by a
passed repeated save.

Before v2.97.77, when an end-of-turn save (v2.97.62/69) or
damage-triggered save (v2.97.65/66) passed, the condition buff was
silently dropped — no log entry, no undo handle. If the GM realized
the save shouldn't have been allowed (wrong DC, wrong target, etc.)
the only recovery was to manually re-install the buff.

v2.97.77 makes ``_resolve_repeated_save_for_buff`` (the shared helper
all four save-pass paths route through, per v2.97.70) snapshot the
target's buffs pre-drop, mint a fresh cast_id, and stamp a
``buff_drop_from_save`` entry into the per-cast undo log. The cast_id
is surfaced on the helper's return + the ``feature_used`` broadcast.
``/undo_attack_damage`` then has a matching reverse branch that calls
``_restore_target_buffs`` with the snapshot.

The test: Lyra (test creature_type="fiend" override) Fears Pip, then
Pip POSTs /use_repeated_save in a loop until a pass drops the
Frightened buff. The response carries a non-empty ``undo_cast_id``.
The test then POSTs /undo_attack_damage with that cast_id and
verifies Pip's Frightened buff is back on the character (via the
/buffs GET).
"""
from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def _install_frightened_from_lyra(gm_client, lyra, pip):
    """Seed battle + walk Lyra's Fear cast loop until Pip fails the
    Wis save and Frightened lands. Returns nothing; the caller reads
    Pip's buffs to confirm the install."""
    lyra_tok = f"tok_undo_lyra_{lyra['id']}"
    pip_tok = f"tok_undo_pip_{pip['id']}"

    landed = False
    for _ in range(30):
        await _long_rest(gm_client, lyra["id"])
        await _long_rest(gm_client, pip["id"])
        for _stale in (
            "frightened", "paralyzed", "charmed", "baned", "faerie-fired",
            "protection-from-evil-and-good", "heroism", "bless",
        ):
            await gm_client.post(
                f"/api/campaign/{CAMPAIGN_ID}/end_buff",
                json={"character_id": pip["id"], "key": _stale},
            )

        combatants = [
            {
                "id": lyra_tok, "char_id": lyra["id"],
                "name": lyra["name"], "initiative": 12,
                "hp_current": 35, "hp_max": 35, "buffs": [],
                "creature_type": "fiend",
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            },
            {
                "id": pip_tok, "char_id": pip["id"],
                "name": pip["name"], "initiative": 8,
                "hp_current": 40, "hp_max": 40, "buffs": [],
                "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0},
            },
        ]
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/battle",
            json={
                "combatants": combatants,
                "turn_index": 0, "round": 1, "active": True,
            },
        )

        fear_cast = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/cast_spell",
            json={
                "character_id": lyra["id"],
                "spell_index": 19,
                "slot_level": 3,
                "class_slug": "bard",
                "target_character_id": pip["id"],
                "target_combatant_id": pip_tok,
                "target_name": pip["name"],
                "override": True,
                "override_range": True,
            },
        )
        assert fear_cast.status_code == 200, fear_cast.text
        prompt_id = fear_cast.json().get("auto_save_prompt_id")
        if not prompt_id:
            continue
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/roll_request/{prompt_id}/respond",
            json={"character_id": pip["id"]},
        )
        data = resp.json()
        if data.get("auto_buff_installed") == "Frightened":
            landed = True
            break

    assert landed, "no failed Wis save in 30 tries; couldn't install Frightened"


async def test_passing_repeated_save_can_be_undone(gm_client, roster):
    """Frighten Pip via Lyra; loop /use_repeated_save until a pass
    drops the Frightened buff; assert the response carries a non-empty
    ``undo_cast_id``; POST /undo_attack_damage with that cast_id;
    verify Pip's Frightened buff is restored."""
    lyra = roster["Lyra Sunstrider"]
    pip = roster["Pip Quickfingers"]

    await _install_frightened_from_lyra(gm_client, lyra, pip)

    # Sanity: Pip carries Frightened pre-undo loop.
    pip_buffs = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    assert any(
        (b or {}).get("key") == "frightened" for b in pip_buffs
    ), f"Frightened didn't land; Pip's buffs: {pip_buffs}"

    # Loop /use_repeated_save until a pass returns non-empty
    # undo_cast_id. Pip's Wis save mod is low so the 30-iteration
    # cap is comfortable.
    undo_cast_id = ""
    for _ in range(30):
        rs = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_repeated_save",
            json={"character_id": pip["id"], "buff_key": "frightened"},
        )
        if rs.status_code == 409:
            # The buff dropped on a prior iteration; refetch the
            # cast_id from the last successful pass response (loop
            # invariant: we only break on a pass, so on 409 the loop
            # has already captured the cast_id).
            break
        assert rs.status_code == 200, rs.text
        data = rs.json()
        if data.get("passed") and data.get("buff_dropped"):
            undo_cast_id = data.get("undo_cast_id") or ""
            break

    assert undo_cast_id, (
        "no save-pass dropped Frightened in 30 tries; "
        "v2.97.77 undo_cast_id was never surfaced"
    )

    # Confirm Pip's Frightened actually dropped before the undo runs.
    pip_buffs_post_drop = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    assert not any(
        (b or {}).get("key") == "frightened" for b in pip_buffs_post_drop
    ), (
        "Frightened didn't actually drop on the save-pass; "
        f"Pip's buffs: {pip_buffs_post_drop}"
    )

    # Undo: POST /undo_attack_damage with the cast_id.
    undo = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/undo_attack_damage",
        json={"attack_id": undo_cast_id},
    )
    assert undo.status_code == 200, undo.text
    undo_data = undo.json()
    assert undo_data["ok"] is True

    # Verify Pip's Frightened is back on the character.
    pip_buffs_post_undo = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    assert any(
        (b or {}).get("key") == "frightened" for b in pip_buffs_post_undo
    ), (
        "Frightened wasn't restored by /undo_attack_damage; "
        f"Pip's buffs post-undo: {pip_buffs_post_undo}"
    )


async def test_failed_repeated_save_returns_empty_undo_cast_id(
    gm_client, roster,
):
    """When the save fails, the buff doesn't drop → undo_cast_id
    should be the empty string (no undo handle surfaced since there's
    nothing to undo)."""
    lyra = roster["Lyra Sunstrider"]
    pip = roster["Pip Quickfingers"]

    await _install_frightened_from_lyra(gm_client, lyra, pip)

    # Roll the repeated save once. Pass-or-fail is random; on a fail
    # we expect undo_cast_id == "". On a pass we expect it non-empty
    # (already covered by the happy-path test above). Either branch
    # is a valid assertion of the contract.
    rs = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_repeated_save",
        json={"character_id": pip["id"], "buff_key": "frightened"},
    )
    assert rs.status_code == 200, rs.text
    data = rs.json()
    assert "undo_cast_id" in data, (
        "v2.97.77 contract: undo_cast_id field must be present on "
        "every /use_repeated_save 200 response (empty when no drop)"
    )
    if data.get("passed") and data.get("buff_dropped"):
        assert data["undo_cast_id"], (
            "save passed + buff dropped → undo_cast_id must be non-empty"
        )
    else:
        assert data["undo_cast_id"] == "", (
            f"save didn't drop the buff → undo_cast_id should be empty, "
            f"got {data['undo_cast_id']!r}"
        )
