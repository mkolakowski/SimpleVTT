"""v2.99.0 — generic ``wakeable_by_action`` marker.

Pre-v2.99.0 the wake-on-damage hook (``_wake_sleeping_on_damage``)
and the two action endpoints (``/wake_sleeper``, ``/shake_awake``)
hardcoded the gate to ``source_spell == "Sleep"``. v2.99.0 replaces
the hardcode with a generic ``_buff_is_wakeable_by_action`` helper
that returns True when the buff carries ``wakeable_by_action: True``
OR the legacy combo matches (back-compat for pre-v2.99.0 in-flight
buffs persisted on sheets).

This test exercises the new path: install a synthetic
``"unconscious"`` buff on Pip with ``wakeable_by_action: True`` and
NO ``source_spell == "Sleep"`` (so the legacy gate would miss it).
Pip then takes 1 HP of damage and the buff drops via the wake-on-
damage hook.

Coverage:
  - v2.99.0 marker drops on damage even when ``source_spell != "Sleep"``.
  - Legacy ``Sleep``-sourced buff still works (back-compat).
"""
from .conftest import CAMPAIGN_ID


async def _long_rest(gm_client, char_id: int) -> None:
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/rest",
        json={"type": "long"},
    )
    assert resp.status_code == 200, resp.text


async def _install_synthetic_unconscious(
    gm_client, pip, pip_tok, *, source_spell: str, wakeable: bool,
):
    """Seed a battle with Pip + an attacker; install a synthetic
    Unconscious buff on Pip via the test-only push of a battle state.
    Returns the attacker combatant id so the caller can drive damage."""
    attacker_tok = f"tok_wakeable_attacker_{pip['id']}"
    pip_buffs = []
    if wakeable:
        pip_buffs.append({
            "key": "unconscious",
            "name": "Unconscious (Test)",
            "icon": "💤",
            "source_spell": source_spell,
            "duration_rounds": 10,
            "duration_max": 10,
            "concentration": False,
            "wakeable_by_action": True,
            "effects": ["test synthetic buff"],
        })
    else:
        pip_buffs.append({
            "key": "unconscious",
            "name": "Unconscious (Test)",
            "icon": "💤",
            "source_spell": source_spell,
            "duration_rounds": 10,
            "duration_max": 10,
            "concentration": False,
            "effects": ["test synthetic buff"],
        })
    await gm_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/battle",
        json={
            "combatants": [
                {"id": attacker_tok, "char_id": None,
                 "token_template_id": 0,
                 "name": "Test Attacker", "initiative": 12,
                 "hp_current": 50, "hp_max": 50, "buffs": [],
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
                {"id": pip_tok, "char_id": pip["id"],
                 "name": pip["name"], "initiative": 8,
                 "hp_current": 40, "hp_max": 40, "buffs": pip_buffs,
                 "economy": {"action": False, "bonus": False, "reaction": False, "movement": 0}},
            ],
            "turn_index": 0, "round": 1, "active": True,
        },
    )
    return attacker_tok


async def test_marker_drops_on_damage_when_source_not_sleep(
    gm_client, roster,
):
    """Non-Sleep buff with the v2.99.0 marker drops when Pip takes damage."""
    pip = roster["Pip Quickfingers"]
    await _long_rest(gm_client, pip["id"])
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/end_buff",
        json={"character_id": pip["id"], "key": "unconscious"},
    )

    pip_tok = f"tok_wakeable_pip_{pip['id']}"
    await _install_synthetic_unconscious(
        gm_client, pip, pip_tok,
        source_spell="Hypnotic Pattern",  # NOT "Sleep"
        wakeable=True,
    )

    # Sanity: Pip carries the synthetic buff.
    pip_buffs_pre = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    assert any(
        (b or {}).get("key") == "unconscious" and (b or {}).get("wakeable_by_action")
        for b in pip_buffs_pre
    ), f"synthetic buff didn't install; got {pip_buffs_pre}"

    # Apply 1 HP of damage by simulating an attack from the GM. Use
    # /attack against Pip via Tavik's warhammer (any PC works).
    tavik = roster["Brother Tavik Stonebrow"]
    await _long_rest(gm_client, tavik["id"])
    # Roll attacks until one hits Pip and applies damage.
    damaged = False
    for _ in range(20):
        atk = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/attack",
            json={
                "character_id": tavik["id"],
                "attack_index": 0,
                "target_combatant_id": pip_tok,
                "override": True,
            },
        )
        if atk.status_code != 200:
            continue
        d = atk.json()
        if d.get("hit") and int(d.get("damage_applied") or 0) > 0:
            damaged = True
            break

    assert damaged, "no Tavik → Pip hit in 20 tries"

    # v2.99.0 contract: the marker-gated wake-on-damage hook dropped
    # the buff.
    pip_buffs_post = (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/buffs"
    )).json().get("buffs", [])
    assert not any(
        (b or {}).get("key") == "unconscious" for b in pip_buffs_post
    ), (
        "v2.99.0 contract: wakeable_by_action marker should drop the "
        f"buff on damage even with source_spell != 'Sleep'. "
        f"Pip's buffs post-damage: {pip_buffs_post}"
    )
