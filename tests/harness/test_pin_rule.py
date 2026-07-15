"""v2.1023.0 — SRD Reference Phase 2b: pin a rule to the tabletop.

A GM pins an SRD reference entry from `/campaign/{cid}/reference` → its
name + description broadcast (`rule_pinned`) to every tabletop client as
a card the whole table sees; unpin clears it (`rule_unpinned`). The pin
is held in-memory per campaign so a reloading / late-joining client can
re-fetch it via `GET /pinned_rule`.

Tests (API contract — the client card render is Playwright territory):
  - GM `POST /pin_rule {grappled, conditions}` → 200 + `rule_pinned`
    broadcast carrying name/desc; `GET /pinned_rule` echoes it.
  - GM `POST /unpin_rule` → 200 + `rule_unpinned`; `GET /pinned_rule`
    returns null.
  - A player pinning → 403 (GM only).
  - Unknown slug → 404; bad type → 400.
  - `GET /campaign/{cid}/reference` (GM) renders the page with pin UI.
"""
import asyncio

from .conftest import CAMPAIGN_ID


async def test_pin_rule_broadcasts_and_persists(gm_client, gm_ws):
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/pin_rule",
        json={"slug": "grappled", "type": "conditions"},
    )
    assert r.status_code == 200, r.text
    pinned = r.json()["pinned"]
    assert pinned["slug"] == "grappled"
    assert pinned["type_label"] == "Condition"
    assert pinned["desc"]
    await asyncio.sleep(0.3)
    msgs = gm_ws.buffered("rule_pinned")
    assert msgs, "expected a rule_pinned broadcast"
    assert msgs[-1]["data"]["slug"] == "grappled"
    assert msgs[-1]["data"]["desc"]
    # Late-joiner fetch.
    g = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/pinned_rule")
    assert g.status_code == 200, g.text
    assert (g.json()["pinned"] or {}).get("slug") == "grappled"
    # Cleanup.
    await gm_client.post(f"/api/campaign/{CAMPAIGN_ID}/unpin_rule")


async def test_unpin_rule_clears(gm_client, gm_ws):
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/pin_rule",
        json={"slug": "prone", "type": "conditions"},
    )
    gm_ws.mark()
    r = await gm_client.post(f"/api/campaign/{CAMPAIGN_ID}/unpin_rule")
    assert r.status_code == 200, r.text
    await asyncio.sleep(0.3)
    assert gm_ws.buffered("rule_unpinned"), "expected a rule_unpinned broadcast"
    g = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/pinned_rule")
    assert g.json()["pinned"] is None


async def test_pin_rule_gm_only(alice_client):
    """A player can't pin a rule → 403."""
    r = await alice_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/pin_rule",
        json={"slug": "grappled", "type": "conditions"},
    )
    assert r.status_code == 403, r.text


async def test_pin_rule_unknown_slug(gm_client):
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/pin_rule",
        json={"slug": "definitely-not-a-real-condition", "type": "conditions"},
    )
    assert r.status_code == 404, r.text


async def test_pin_rule_bad_type(gm_client):
    """Monsters aren't a player-safe reference type → 400."""
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/pin_rule",
        json={"slug": "goblin", "type": "monsters"},
    )
    assert r.status_code == 400, r.text


async def test_campaign_reference_page_renders(gm_client):
    r = await gm_client.get(f"/campaign/{CAMPAIGN_ID}/reference")
    assert r.status_code == 200, r.text
    body = r.text
    assert "SRD 5.1 Reference" in body
    # GM in a campaign → the pin path is enabled in the page JS.
    assert "CAN_PIN = true" in body
    assert f"CAMPAIGN_ID = {CAMPAIGN_ID}" in body
