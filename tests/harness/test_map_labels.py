"""v2.802.0 — Maps 2.0 public text labels.

  - `GET  /api/campaign/{cid}/map/{map_id}/labels`  — read (any member).
  - `PUT  /api/campaign/{cid}/map/{map_id}/labels`  — replace (GM-only) +
    broadcast `labels_update`.
  - `GET  /api/campaign/{cid}/active-map`           — surfaces labels too.

Labels are `{id, x, y, text, size, color}` public annotations in map-pixel
coords; `text` is capped/required, `size` clamped 8..200, `color` a #rrggbb.
"""
from .conftest import CAMPAIGN_ID


async def _active_map_id(gm_client) -> int:
    return int((await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()["map_id"])


async def test_set_and_get_labels(gm_client, gm_ws):
    mid = await _active_map_id(gm_client)
    labels = [
        {"x": 100, "y": 120, "text": "The Vault", "size": 300, "color": "#ffcc00"},
        {"x": 5, "y": 5, "text": "   ", "color": "#fff"},   # dropped — empty text
        {"y": 10, "text": "no x"},                          # dropped — no x
    ]
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/labels",
            json={"labels": labels})
        assert r.status_code == 200, r.text
        ls = r.json()["labels"]
        assert len(ls) == 1, ls
        assert ls[0]["text"] == "The Vault"
        assert ls[0]["size"] == 200.0          # clamped down from 300
        assert ls[0]["color"] == "#ffcc00" and ls[0]["id"]

        msg = await gm_ws.wait_for("labels_update")
        assert msg["data"]["map_id"] == mid
        assert len(msg["data"]["labels"]) == 1

        am = (await gm_client.get(f"/api/campaign/{CAMPAIGN_ID}/active-map")).json()
        assert len(am["labels"]) == 1
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/labels", json={"labels": []})


async def test_label_defaults(gm_client):
    mid = await _active_map_id(gm_client)
    try:
        r = await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/labels",
            json={"labels": [{"x": 0, "y": 0, "text": "Hi", "color": "bogus"}]})
        lb = r.json()["labels"][0]
        assert lb["size"] == 24.0        # default size
        assert lb["color"] == "#ffffff"  # invalid → default white
    finally:
        await gm_client.put(
            f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/labels", json={"labels": []})


async def test_set_labels_requires_gm(gm_client, alice_client):
    mid = await _active_map_id(gm_client)
    assert (await alice_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/labels")).status_code == 200
    r = await alice_client.put(
        f"/api/campaign/{CAMPAIGN_ID}/map/{mid}/labels",
        json={"labels": [{"x": 0, "y": 0, "text": "nope"}]})
    assert r.status_code == 403, r.text


async def test_labels_unknown_map_404(gm_client):
    assert (await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/map/99999999/labels")).status_code == 404
