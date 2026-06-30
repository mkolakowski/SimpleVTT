"""v2.761.0 — Maps 2.0 multi-map encounters.

`PATCH /api/campaign/{cid}/encounters/{id}` accepts `linked_map_ids` — a list
of additional campaign map ids the encounter groups for quick active-map
switching. Invalid ids, non-ints, dupes, and the encounter's own primary
`map_id` are filtered out; the value surfaces in the encounter dict.

The demo has a single map, so this drives the positive case by temporarily
unbinding the encounter's primary map (making that map a valid "extra").
"""
from .conftest import CAMPAIGN_ID


async def _encounters(client):
    r = await client.get(f"/api/campaign/{CAMPAIGN_ID}/encounters")
    d = r.json()
    return d if isinstance(d, list) else d.get("encounters", [])


async def _enc_with_map(gm_client):
    for e in await _encounters(gm_client):
        if e.get("map_id"):
            return e
    return (await _encounters(gm_client))[0]


async def _patch(client, enc_id, body):
    return await client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/encounters/{enc_id}", json=body)


async def _get_enc(gm_client, enc_id):
    for e in await _encounters(gm_client):
        if e["id"] == enc_id:
            return e
    return None


async def test_linked_map_ids_filter_and_persist(gm_client):
    enc = await _enc_with_map(gm_client)
    enc_id, map_a = enc["id"], enc["map_id"]
    assert map_a, "need an encounter with a bound map"
    try:
        # Unbind the primary so map_a can be a valid "extra".
        assert (await _patch(gm_client, enc_id, {"map_id": None})).status_code == 200
        # Link map_a + an invalid id + a non-int + a dupe → only map_a survives.
        r = await _patch(gm_client, enc_id,
                         {"linked_map_ids": [map_a, 99999999, "x", map_a]})
        assert r.status_code == 200, r.text
        got = await _get_enc(gm_client, enc_id)
        assert got["linked_map_ids"] == [map_a], got["linked_map_ids"]

        # Clearing works.
        await _patch(gm_client, enc_id, {"linked_map_ids": []})
        assert (await _get_enc(gm_client, enc_id))["linked_map_ids"] == []

        # With the primary re-bound, linking it is dropped (it's the base map).
        await _patch(gm_client, enc_id, {"map_id": map_a})
        await _patch(gm_client, enc_id, {"linked_map_ids": [map_a]})
        assert (await _get_enc(gm_client, enc_id))["linked_map_ids"] == []
    finally:
        await _patch(gm_client, enc_id, {"map_id": map_a, "linked_map_ids": []})


async def test_linked_map_ids_requires_gm(gm_client, alice_client):
    enc = await _enc_with_map(gm_client)
    r = await _patch(alice_client, enc["id"], {"linked_map_ids": []})
    assert r.status_code == 403, r.text
