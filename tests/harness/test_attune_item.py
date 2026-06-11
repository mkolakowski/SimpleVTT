"""v2.158.79 — magic-items-automation Phase 2: ``/attune`` endpoint
that toggles the ``attuned`` flag on a PC's inventory item, with
server-side enforcement of the RAW DMG p.138 3-item attunement cap.

The Phase 1 catalog walker (``_equipped_item_effects``) already gates
passive payloads on the ``attuned`` flag — this endpoint is the
player/GM-facing surface that flips it. Today the flag is set in the
demo seed for Pip (Cloak + Ring), Thalindra (Cloak), Tavik (Ring),
and Kael (Bracers); Phase 2 lets the gate be flipped at runtime.

Tests:
  - happy: toggle Pip's Cloak off → AC drops; toggle back on → AC
    restores.
  - cap: Pip starts with 2 attuned items (Cloak + Ring). Attune a 3rd
    item (her Shortsword — non-magic but attunement is a per-item
    flag independent of item type, so the cap test exercises it
    cleanly). Attune a 4th → 409.
  - error paths: missing fields → 400, unknown char_id → 404,
    out-of-range inventory_index → 400.

Teardown: every test restores Pip's seed state (Shortsword/Dagger
unattuned, Cloak + Ring re-attuned).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


# Pip's seed inventory indices (as of v2.158.78):
#   0  Shortsword
#   1  Dagger (×2)
#   2  Studded leather
#   3  Thieves' tools
#   4  Burglar's pack
#   5  Hooded lantern
#   6  Potion of Healing (×2)
#   7  Cloak of Protection (attuned: True)
#   8  Ring of Protection  (attuned: True)
PIP_CLOAK_IDX = 7
PIP_RING_IDX = 8
PIP_SHORTSWORD_IDX = 0
PIP_DAGGER_IDX = 1
PIP_STUDDED_LEATHER_IDX = 2


async def _seed_battle_with(gm_client, char_specs: list[dict]) -> None:
    combatants = []
    for spec in char_specs:
        combatants.append({
            "id": spec["tok_id"],
            "char_id": spec["id"],
            "name": spec["name"],
            "initiative": spec.get("initiative", 10),
            "hp_current": spec.get("hp_max", 40),
            "hp_max": spec.get("hp_max", 40),
            "buffs": [],
            "economy": {
                "action": False, "bonus": False, "reaction": False,
                "movement": 0,
            },
        })
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": combatants, "turn_index": 0, "round": 1,
            "active": True,
        },
    )


@pytest_asyncio.fixture
async def restore_pip_attunement(gm_client, roster):
    """Restore Pip's seed attunement state (Cloak + Ring attuned;
    everything else unattuned) after a test that mutates it."""
    pip = roster["Pip Quickfingers"]
    yield pip
    # Best-effort teardown — restore Cloak + Ring to attuned, and
    # un-attune any other item the test may have flipped.
    for idx in (
        PIP_SHORTSWORD_IDX, PIP_DAGGER_IDX, PIP_STUDDED_LEATHER_IDX,
    ):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/attune",
            json={"inventory_index": idx, "attuned": False},
        )
    for idx in (PIP_CLOAK_IDX, PIP_RING_IDX):
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/attune",
            json={"inventory_index": idx, "attuned": True},
        )


async def test_attune_toggle_off_drops_ac(
    gm_client, roster, restore_pip_attunement,
):
    """v2.158.79 happy-path: toggling Pip's Cloak attunement off
    drops her effective AC from 16 → 15 (Ring still gives +1). Then
    toggling back to attuned restores it."""
    pip = restore_pip_attunement
    krieger = roster["Krieger Stonefist"]

    # Toggle Cloak attunement → off.
    resp_off = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/attune",
        json={"inventory_index": PIP_CLOAK_IDX, "attuned": False},
    )
    assert resp_off.status_code == 200, resp_off.text
    body = resp_off.json()
    assert body["ok"] is True
    assert body["attuned"] is False
    assert body["item_name"] == "Cloak of Protection"

    pip_tok = f"tok_attune_off_pip_{pip['id']}"
    await _seed_battle_with(gm_client, [
        {"id": krieger["id"], "name": krieger["name"],
         "tok_id": f"tok_attune_off_krieger_{krieger['id']}",
         "hp_max": 55, "initiative": 14},
        {"id": pip["id"], "name": pip["name"],
         "tok_id": pip_tok, "hp_max": 47, "initiative": 8},
    ])
    atk = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/attack",
        json={
            "character_id": krieger["id"],
            "attack_index": 0,
            "target_combatant_id": pip_tok,
            "target_character_id": pip["id"],
            "target_name": pip["name"],
            "override": True,
        },
    )
    assert atk.status_code == 200, atk.text
    target_ac = atk.json().get("target_ac")
    # Pip base AC 14 + Ring +1 (still attuned) = 15. Cloak suppressed.
    assert target_ac == 15, (
        f"expected target_ac=15 (14 base + Ring +1; Cloak unattuned), "
        f"got {target_ac}; response={atk.json()}"
    )


async def test_attune_cap_blocks_fourth(
    gm_client, roster, restore_pip_attunement,
):
    """v2.158.79 cap path: Pip starts with 2 attuned items (Cloak +
    Ring). Attune a 3rd item (Shortsword) → 200. Attune a 4th
    (Dagger) → 409 ``attunement_cap``. RAW DMG p.138."""
    pip = restore_pip_attunement

    # 3rd attunement (Shortsword) → 200, total 3.
    resp_3 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/attune",
        json={"inventory_index": PIP_SHORTSWORD_IDX, "attuned": True},
    )
    assert resp_3.status_code == 200, resp_3.text

    # 4th attunement (Dagger) → 409.
    resp_4 = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/attune",
        json={"inventory_index": PIP_DAGGER_IDX, "attuned": True},
    )
    assert resp_4.status_code == 409, resp_4.text
    body = resp_4.json()
    assert body.get("error") == "attunement_cap"
    assert body.get("max_attuned") == 3
    assert body.get("current_attuned") == 3


async def test_attune_toggle_existing_no_spurious_409(
    gm_client, roster, restore_pip_attunement,
):
    """v2.158.79 cap guard: setting attuned=True on an item that's
    ALREADY attuned must not 409 even if the PC has 3 attuned items.
    The cap counts OTHER attuned items so the target is excluded.
    Otherwise re-saving a sheet would spuriously fail."""
    pip = restore_pip_attunement

    # Push Pip to exactly 3 attuned (Cloak + Ring + Shortsword).
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/attune",
        json={"inventory_index": PIP_SHORTSWORD_IDX, "attuned": True},
    )

    # Re-set Cloak attuned=True → must still 200 (no-op effectively).
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/attune",
        json={"inventory_index": PIP_CLOAK_IDX, "attuned": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["attuned"] is True


async def test_attune_missing_fields_400(gm_client, roster):
    """v2.158.79 error path: empty body → 400."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/attune",
        json={},
    )
    assert resp.status_code == 400


async def test_attune_unknown_char_404(gm_client):
    """v2.158.79 error path: unknown char_id → 404."""
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/99999999/attune",
        json={"inventory_index": 0, "attuned": True},
    )
    assert resp.status_code == 404


async def test_attune_index_out_of_range_400(gm_client, roster):
    """v2.158.79 error path: inventory_index past end of inventory
    → 400."""
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/attune",
        json={"inventory_index": 999, "attuned": True},
    )
    assert resp.status_code == 400
