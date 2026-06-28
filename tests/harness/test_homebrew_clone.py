"""Homebrew clone (TODO reconciliation).

Filed as unbuilt but already shipped (v2.3.37): every file-based homebrew type
(feats / backgrounds / races / subclasses / monsters / classes) has a
`POST /campaign/{cid}/custom-<type>/{slug}/clone` endpoint + a 📋 Clone button
in the campaign-settings homebrew menu. `_clone_homebrew_record` writes a
fresh `copy-of-<slug>` record with a "Copy of …" name via `_unique_clone_slug`.

This test locks the clone contract in end-to-end on the monster type: create a
homebrew monster with an attack action → clone it → the `copy-of-…` record
exists with a "Copy of" name and the source's action preserved.
"""
import json

from .conftest import CAMPAIGN_ID

_SRC = "zzclonesrc"
_CLONE = "copy-of-zzclonesrc"


async def _del(gm_client, slug):
    await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/custom-monsters/{slug}/delete")


async def test_homebrew_monster_clone_creates_copy(gm_client):
    # Clean any leftovers from a prior run.
    for s in (_CLONE, f"{_CLONE}-2", _SRC):
        await _del(gm_client, s)

    actions = [{"name": "Slam", "desc": "Melee", "attack_roll": True,
                "attack_bonus": "+5", "damage": "2d6+3",
                "damage_type": "bludgeoning"}]
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/custom-monsters",
        data={"name": "Zzclonesrc", "hit_points": "40",
              "challenge_rating": "2", "actions_json": json.dumps(actions)})
    assert r.status_code in (200, 303), r.text
    try:
        clone = await gm_client.post(
            f"/campaign/{CAMPAIGN_ID}/custom-monsters/{_SRC}/clone")
        assert clone.status_code in (200, 303), clone.text

        # The clone exists with a "Copy of" name + the source's action.
        c = await gm_client.get(
            f"/api/content/monsters/{_CLONE}?campaign_id={CAMPAIGN_ID}")
        assert c.status_code == 200, c.text
        rec = c.json()["record"]
        assert (rec.get("name") or "").lower().startswith("copy of"), rec.get("name")
        atk = next((a for a in (rec.get("actions") or [])
                    if a.get("name") == "Slam"), None)
        assert atk is not None and atk.get("attack_roll") is True, rec.get("actions")
        assert atk.get("damage") == "2d6+3"
    finally:
        for s in (_CLONE, f"{_CLONE}-2", _SRC):
            await _del(gm_client, s)


async def test_clone_unknown_source_404(gm_client):
    r = await gm_client.post(
        f"/campaign/{CAMPAIGN_ID}/custom-monsters/zznosuchmonster/clone")
    assert r.status_code == 404, r.text
