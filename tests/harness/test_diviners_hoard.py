"""v2.334.0 — "The Diviner's Hoard" bundle (eighth stub bundle). Three SRD
high-power divination / planar-travel wondrous items shipped together as
catalog-stub passives. Two require attunement (Crystal Ball, Candle of
Invocation); Cubic Gate doesn't. Their RAW mechanics (scry-through-orb,
six-face planar gate, alignment-keyed invocation candle) are GM-narrated
in v1. Seeded on thematic carriers:

  - Crystal Ball (RAW DMG p.159, very rare, attunement by a spellcaster)
    → Lyra Sunstrider (College of Lore Bard — scrying lore).
  - Cubic Gate (RAW DMG p.165, legendary, no attunement) → Thalindra
    Moonwhisper (Wizard Evoker — six-plane gate fits a research scholar).
  - Candle of Invocation (RAW DMG p.157, very rare, attunement) →
    Brother Tavik Stonebrow (Life Cleric — consecrated invocation candle
    for a divine-ritual altar kit).

Smoke tests verify each item is reachable via `/sheet-json` by `_slug`.
The two attunement items additionally assert `attuned: True` to confirm
the contract loads through the seed.
"""
from .conftest import CAMPAIGN_ID


async def _carrier_inv(gm_client, char_id):
    resp = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    assert resp.status_code == 200, resp.text
    return list((resp.json().get("sheet") or {}).get("inventory") or [])


def _find_by_slug(inv, slug):
    for it in inv:
        if isinstance(it, dict) and it.get("_slug") == slug:
            return it
    return None


async def test_lyra_carries_crystal_ball(gm_client, roster):
    """Crystal Ball is seeded on Lyra Sunstrider (Bard) — equipped=True,
    attuned=True (RAW: attunement by a spellcaster)."""
    lyra = roster["Lyra Sunstrider"]
    inv = await _carrier_inv(gm_client, lyra["id"])
    orb = _find_by_slug(inv, "crystal-ball")
    assert orb is not None, (
        f"Lyra should carry a Crystal Ball; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert orb.get("name") == "Crystal Ball"
    assert orb.get("equipped") is True
    assert orb.get("attuned") is True, (
        f"Crystal Ball requires attunement (RAW); got: {orb!r}"
    )


async def test_thalindra_carries_cubic_gate(gm_client, roster):
    """Cubic Gate is seeded on Thalindra Moonwhisper (Wizard) —
    equipped=True, no attunement."""
    thalindra = roster["Thalindra Moonwhisper"]
    inv = await _carrier_inv(gm_client, thalindra["id"])
    gate = _find_by_slug(inv, "cubic-gate")
    assert gate is not None, (
        f"Thalindra should carry a Cubic Gate; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert gate.get("name") == "Cubic Gate"
    assert gate.get("equipped") is True
    assert not gate.get("attuned"), (
        f"Cubic Gate is no-attunement (RAW); got: {gate!r}"
    )


async def test_tavik_carries_candle_of_invocation(gm_client, roster):
    """Candle of Invocation is seeded on Brother Tavik Stonebrow (Cleric) —
    equipped=True, attuned=True (RAW: attunement)."""
    tavik = roster["Brother Tavik Stonebrow"]
    inv = await _carrier_inv(gm_client, tavik["id"])
    candle = _find_by_slug(inv, "candle-of-invocation")
    assert candle is not None, (
        f"Tavik should carry a Candle of Invocation; got slugs="
        f"{[(it.get('_slug') if isinstance(it, dict) else None) for it in inv]}"
    )
    assert candle.get("name") == "Candle of Invocation"
    assert candle.get("equipped") is True
    assert candle.get("attuned") is True, (
        f"Candle of Invocation requires attunement (RAW); got: {candle!r}"
    )
