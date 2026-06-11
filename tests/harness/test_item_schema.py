"""Harness tests for the v2.158.73 magic-items-automation Phase 0
schema additions to the SRD item content layer.

Phase 0 added three top-level keys to the ``Item`` Pydantic model in
``app/content_schemas.py`` and to every shipped item JSON under
``app/data/local/dnd5e/items/``:

    charges           — int | None   (RAW charge count for wand / staff
                                      / ring-of-spell-storing items)
    charge_recovery   — str | None   (recharge expression, e.g. "1d6+1"
                                      for Wand of Magic Missiles)
    passives          — list[dict]   (always-on bonuses merged at read
                                      time by Phase 1's
                                      _equipped_item_effects walker)

All three default to "no mechanical wiring" so the 292 SRD items ship
a uniform shape without behavior change. Phase 1 populates the values
for the first-slice roster (Cloak of Protection / Bracers of Defense
/ Ring of Protection / Pearl of Power) — this commit's tests just
assert the shape is present and the public read endpoint returns it.

Endpoint surface (already shipped, see ``app/routes/homebrew_routes.py``):
  GET /api/content/items/{slug}  →  {"source": "local-srd", "record": {...}}
"""
import httpx

from .helpers import BASE_URL


async def test_item_schema_cloak_of_protection_has_phase1a_passives():
    """v2.158.73 originally: assert Phase 0's "no wiring" defaults
    on Cloak of Protection. v2.158.75: Phase 1a (v2.158.74) populated
    the Cloak's passives with the +1 AC / +1 save payload, so the
    assertion now reflects the wired shape instead. Charges remain
    null (Phase 4 won't touch the Cloak — it's a passive, not a
    charge-tracked item)."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/api/content/items/cloak-of-protection")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "local-srd"
    record = body["record"]
    assert record["slug"] == "cloak-of-protection"
    # Charges fields stay null — Cloak is a passive item, not charge-tracked.
    assert "charges" in record and record["charges"] is None
    assert "charge_recovery" in record and record["charge_recovery"] is None
    # Phase 1a payload: +1 AC, +1 saves, requires attunement.
    assert "passives" in record
    passives = record["passives"]
    assert isinstance(passives, list) and len(passives) == 1, (
        f"expected exactly one passive entry, got {passives!r}"
    )
    p = passives[0]
    assert p.get("ac_bonus") == 1
    assert p.get("save_bonus") == 1
    assert p.get("requires_attunement") is True


async def test_item_schema_ring_of_protection_has_phase1b_passives():
    """v2.158.76: Phase 1b wired Ring of Protection with the same +1
    AC / +1 saves payload as Cloak. Empty-passives canary moves on
    to Bracers of Defense (Phase 1c target — different shape because
    of the no-armor + no-shield gate)."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/api/content/items/ring-of-protection")
    assert resp.status_code == 200
    record = resp.json()["record"]
    assert record["slug"] == "ring-of-protection"
    assert record["charges"] is None
    assert record["charge_recovery"] is None
    passives = record["passives"]
    assert isinstance(passives, list) and len(passives) == 1
    p = passives[0]
    assert p.get("ac_bonus") == 1
    assert p.get("save_bonus") == 1
    assert p.get("requires_attunement") is True


async def test_item_schema_bracers_of_defense_has_empty_passives():
    """v2.158.76: empty-passives canary moves from Ring of Protection
    (now Phase 1b wired) to Bracers of Defense (Phase 1c target —
    +2 AC with the RAW no-armor + no-shield gate, which needs a
    new ``requires_no_armor`` walker primitive). When Phase 1c ships,
    this assertion flips and the canary rolls forward again."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/api/content/items/bracers-of-defense")
    assert resp.status_code == 200
    record = resp.json()["record"]
    assert record["slug"] == "bracers-of-defense"
    assert record["charges"] is None
    assert record["charge_recovery"] is None
    assert record["passives"] == []


async def test_item_schema_wand_of_magic_missiles_has_phase0_keys():
    """v2.158.73: same shape assertion on a charge-tracked item so
    both archetypes (passive wearable / charge-tracked caster) prove
    the schema landed uniformly across all 292 items, not just the
    wearables."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/api/content/items/wand-of-magic-missiles")
    assert resp.status_code == 200
    record = resp.json()["record"]
    assert record["slug"] == "wand-of-magic-missiles"
    # Phase 0 ships the keys with null defaults; Phase 4 will populate
    # charges=7 + charge_recovery="1d6+1" on this exact item.
    assert record["charges"] is None
    assert record["charge_recovery"] is None
    assert record["passives"] == []


async def test_item_schema_unknown_slug_404():
    """v2.158.73: GET /api/content/items/<not-real> — 404. The Phase 0
    additions don't change the error contract; this asserts the
    read endpoint still 404s an unknown item slug."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        resp = await client.get("/api/content/items/no-such-srd-item")
    assert resp.status_code == 404
