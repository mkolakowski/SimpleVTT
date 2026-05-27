"""v2.86.0 — encounter backgrounds.

A fullscreen fixed-position image/video layer that renders BEHIND the
battle map. Extends past the visible viewport, stays still while the
map pans/zooms, and is bindable to individual encounters so the
backdrop swaps with the scene. See models.Campaign.active_background_url
and models.Encounter.background_url for the data-model contract.

Endpoints under test:
  - POST /api/campaign/{cid}/background  (campaign-level set/clear)
  - POST /api/campaign/{cid}/encounters/{eid}/background
    (per-encounter set/clear; doesn't broadcast until the encounter
    loads)

Tests:
  - error path: missing payload (no file, no clear=true) → 400
  - happy path: campaign-level upload → 200 + URL persisted + WS
    ``background_change`` broadcast carries the new URL
  - clear path: clear=true → 200 + URL nulled + WS broadcast carries
    null
  - per-encounter upload persists the URL but does NOT broadcast (the
    encounter-load flow is what propagates it to the campaign)

Asset payload: 1x1 transparent PNG (smallest valid PNG, ~70 bytes).
Kept inline so the test is hermetic — no fixture file needed.
"""
from __future__ import annotations

import io

from .conftest import CAMPAIGN_ID  # noqa: F401


# 1x1 transparent PNG. Smallest valid image we can post through the
# upload endpoint without bringing in Pillow as a test dependency.
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63000100000005000100"
    "0d0a2db40000000049454e44ae426082"
)


async def test_campaign_background_missing_payload_400(gm_client):
    """No file + clear=false → 400. Guards against silent no-op calls."""
    resp = await gm_client.post(f"/api/campaign/{CAMPAIGN_ID}/background")
    assert resp.status_code == 400, resp.text


async def test_campaign_background_upload_then_clear(gm_client, gm_ws):
    """Set the campaign background via upload, verify the URL persists
    and a ``background_change`` broadcast carries the new URL; then
    clear it and verify the broadcast carries null.
    """
    gm_ws.mark()
    files = {"image": ("bg.png", io.BytesIO(_PNG_BYTES), "image/png")}
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/background", files=files,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    new_url = data["active_background_url"]
    assert isinstance(new_url, str) and new_url.startswith("/static/uploads/encounter_bg/")

    msg = await gm_ws.wait_for("background_change")
    assert msg["data"]["url"] == new_url

    # Clear: form data, ``clear=true``.
    gm_ws.mark()
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/background", data={"clear": "true"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["active_background_url"] is None

    msg = await gm_ws.wait_for("background_change")
    assert msg["data"]["url"] is None


async def test_encounter_background_upload_does_not_broadcast(gm_client, gm_ws):
    """Setting a background on a saved encounter persists the URL on
    that encounter but doesn't fire a campaign-level broadcast —
    propagation only happens when the encounter is loaded.

    We create a throwaway encounter, attach a background, assert the
    PATCH/list projection includes ``background_url``, then verify no
    ``background_change`` shows up on the WS in the meantime.
    """
    # Create a fresh encounter so we don't mutate the demo seed. Pass
    # an explicit empty payload (the build-from-blank path) so the
    # endpoint doesn't snapshot the live tabletop state — keeps the
    # test side-effect free w.r.t. other concurrent harness runs.
    create = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/encounters",
        json={
            "name": "Background test encounter",
            "payload": {"tokens": [], "battle_state": {}},
        },
    )
    assert create.status_code == 200, create.text
    enc_id = create.json()["id"]

    try:
        gm_ws.mark()
        files = {"image": ("bg2.png", io.BytesIO(_PNG_BYTES), "image/png")}
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/encounters/{enc_id}/background",
            files=files,
        )
        assert resp.status_code == 200, resp.text
        bg_url = resp.json()["background_url"]
        assert isinstance(bg_url, str) and bg_url.endswith(".png")

        # Verify the encounter projection now carries the URL — the
        # encounter-editor UI reads this field to render the "Set: …"
        # status line.
        listing = await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/encounters")
        assert listing.status_code == 200, listing.text
        encounters = listing.json()
        target = next((e for e in encounters if e["id"] == enc_id), None)
        assert target is not None
        assert target["background_url"] == bg_url

        # Per-encounter upload should NOT broadcast. Buffered slice
        # after the mark must contain zero background_change messages.
        bg_msgs = gm_ws.buffered("background_change")
        assert not bg_msgs, (
            "Per-encounter upload should not broadcast; got: "
            f"{[m['data'] for m in bg_msgs]}"
        )

        # Clear path on the encounter endpoint.
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/encounters/{enc_id}/background",
            data={"clear": "true"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["background_url"] is None
    finally:
        # Clean up the throwaway encounter so subsequent tests don't
        # see it in the demo library.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/encounters/{enc_id}/delete",
        )
