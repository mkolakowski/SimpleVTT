"""v2.728.0 — dynamic character art updates.

Uploading a new portrait (`POST /campaign/{cid}/character/{id}/portrait`) now
propagates live (no reload): tokens linked to the character get their
`image_url` updated + re-broadcast (`token_update`), and a
`character_portrait_update` event fires so roll-card / spell-card avatars and
the in-memory char map pick up the new art.

(The demo reseeds hourly, so the portrait change here is transient.)
"""
import asyncio

from .conftest import CAMPAIGN_ID

# A minimal 1×1 PNG — the endpoint validates extension + size, not content.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000100ffff03000006000557bfabd4"
    "0000000049454e44ae426082"
)


async def test_portrait_upload_updates_token_and_broadcasts(gm_client, gm_ws, roster):
    pip = roster["Pip Quickfingers"]
    # Ensure the character has a token on the active map.
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/place-token",
        json={"x": 300.0, "y": 300.0})

    gm_ws.mark()
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/character/{pip['id']}/portrait",
        files={"portrait": ("p.png", _PNG, "image/png")})
    assert r.status_code == 200, r.text
    purl = r.json()["portrait_url"]
    assert purl.startswith("/static/uploads/portraits/")

    # The linked token's image_url now points at the new portrait.
    body = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/tokens")).json()
    tok = next((t for t in body["tokens"]
                if t.get("character_id") == pip["id"]), None)
    assert tok is not None, "Pip token missing"
    assert tok["image_url"] == purl, tok

    # The live-propagation broadcasts fired.
    await asyncio.sleep(0.3)
    cp = [m for m in gm_ws.buffered("character_portrait_update")
          if (m.get("data") or {}).get("char_id") == pip["id"]]
    assert cp and cp[-1]["data"]["portrait_url"] == purl, cp
    assert (cp[-1]["data"].get("owner_user_id") is not None
            or "owner_user_id" in cp[-1]["data"])
    tu = [m for m in gm_ws.buffered("token_update")
          if (m.get("data") or {}).get("id") == tok["id"]]
    assert tu and tu[-1]["data"]["image_url"] == purl, tu


async def test_portrait_upload_bad_extension_400(gm_client, roster):
    pip = roster["Pip Quickfingers"]
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/character/{pip['id']}/portrait",
        files={"portrait": ("p.txt", b"not an image", "text/plain")})
    assert r.status_code == 400, r.text
