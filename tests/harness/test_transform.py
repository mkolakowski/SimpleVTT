"""/api/campaign/{cid}/character/{cid}/transform + /revert — Wild Shape tests.

v2.14.4: Mira Greenleaf (demo Druid, added v2.14.2) is now in the
roster so the happy-path test below can run end-to-end. Pre-v2.14.4
no harness coverage existed for these endpoints — they were shipped
pre-v2.0.0 along with the BeastPicker JS but the demo had no Druid
to test against.

The /transform endpoint hits api.open5e.com from the app container
to fetch the beast stat block. CI has internet so this works in the
GitHub Actions runner; local air-gapped runs skip via the
``_open5e_reachable`` gate below.

Coverage:
  - happy path: Mira → Wolf (CR 1/4, within Moon Druid Lv 5 cap of 1)
    + revert in the same test to leave state clean for the next test
  - 400 missing slug
  - 400 invalid source value
  - 409 CR cap exceeded (Mira → Giant Scorpion CR 3)
  - 409 already transformed (transform Mira twice without reverting)
  - 409 revert when not transformed (Pip is a Rogue)

The transform endpoint doesn't bypass action-economy validation
(neither /transform nor /revert pass through _is_slot_used), so
these tests don't need ``override: true``.
"""
import urllib.request

import pytest
import pytest_asyncio

from .conftest import CAMPAIGN_ID


def _open5e_reachable() -> bool:
    """Skip-gate for tests that need a live Open5e v2 API. CI has
    internet so this returns True there; local air-gapped runs skip.

    Open5e blocks the default urllib user-agent with a 403; the app's
    helper passes ``User-Agent: SimpleVTT/1.0`` and works. Mirror that
    here. Pings the search endpoint (rather than a specific slug)
    since slug shapes vary between API revisions.
    """
    try:
        req = urllib.request.Request(
            "https://api.open5e.com/v2/creatures/?limit=1&type__key=beast",
            headers={"User-Agent": "SimpleVTT/1.0"},
        )
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False


_skip_no_open5e = pytest.mark.skipif(
    not _open5e_reachable(), reason="Open5e API not reachable from this host"
)


@pytest_asyncio.fixture
async def mira_in_base_form(gm_client, roster):
    """Ensure Mira is in her true form at test start. A prior failed
    test could have left her transformed; this fixture idempotently
    reverts so each test has a clean baseline. Revert returns 409
    when she's already in base form, which we ignore.
    """
    mira = roster["Mira Greenleaf"]
    await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/revert",
        json={},
    )
    return mira


@_skip_no_open5e
async def test_wild_shape_happy_path(gm_client, gm_ws, mira_in_base_form):
    """Mira (Lv 5 Moon Druid) transforms into a Wolf (CR 1/4). Asserts:
      - 200 + ok:true with active_form populated
      - active_form.slug == 'wolf' and source == 'wild-shape'
      - transform_update WS broadcast fires for Mira with the new form
      - feature_used WS broadcast announces 'Transformed into Wolf'
      - resource_update WS broadcast decrements wild-shape 2 → 1
    Then reverts so the next test starts with Mira in base form.
    """
    mira = mira_in_base_form
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/transform",
        json={"slug": "wolf", "source": "wild-shape"},
    )
    # If Open5e is reachable but the response format drifted, surface
    # the body so the test failure is actionable.
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is True
    af = data["active_form"]
    assert af["slug"] == "wolf"
    assert af["source"] == "wild-shape"
    assert af["creature_type"] == "beast"
    # Wolf's name might be "Wolf" or "wolf" depending on Open5e's
    # case; just verify a non-empty string came back.
    assert isinstance(af.get("name"), str) and af["name"]
    # v2.14.5: Mira is Circle of the Moon → bonus-action shift.
    # The endpoint computes the slot and returns it so tests can
    # verify the resolution without needing a loaded battle state.
    assert data["economy_slot"] == "bonus"

    tu_msg = await gm_ws.wait_for("transform_update")
    assert tu_msg["data"]["character_id"] == mira["id"]
    assert tu_msg["data"]["active_form"] is not None
    assert tu_msg["data"]["active_form"]["slug"] == "wolf"

    fu_msg = await gm_ws.wait_for("feature_used")
    assert fu_msg["data"]["source"] == "Wild Shape"
    # The announce reads "🐺 Transformed into Wolf" or similar.
    assert "ransform" in fu_msg["data"]["feature_name"]

    ru_msg = await gm_ws.wait_for("resource_update")
    assert ru_msg["data"]["character_id"] == mira["id"]
    assert ru_msg["data"]["key"] == "wild-shape"
    # Mira starts the demo with wild-shape 2/2 (short-rest refresh).
    # First transform takes her to 1/2. If a prior test session left
    # the counter at 1/2 and the demo didn't reset between, the value
    # could be 0; assert it's strictly less than max instead.
    assert ru_msg["data"]["max"] == 2
    assert ru_msg["data"]["current"] < ru_msg["data"]["max"]

    # Advance the WSCollector cursor past the transform's broadcasts so
    # the next wait_for only sees the revert's transform_update (both
    # the transform and the revert fire transform_update messages).
    gm_ws.mark()

    # Revert to leave Mira in base form for subsequent tests.
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/revert",
        json={},
    )
    assert resp.status_code == 200, resp.text
    rev_msg = await gm_ws.wait_for("transform_update")
    assert rev_msg["data"]["character_id"] == mira["id"]
    assert rev_msg["data"]["active_form"] is None


async def test_transform_missing_slug(gm_client, mira_in_base_form):
    """Missing 'slug' returns 400."""
    mira = mira_in_base_form
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/transform",
        json={"source": "wild-shape"},
    )
    assert resp.status_code == 400


async def test_transform_invalid_source(gm_client, mira_in_base_form):
    """Source must be 'wild-shape' or 'polymorph' — anything else 400."""
    mira = mira_in_base_form
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/transform",
        json={"slug": "wolf", "source": "polyform-typo"},
    )
    assert resp.status_code == 400


@_skip_no_open5e
async def test_transform_cr_cap_enforced(gm_client, mira_in_base_form):
    """Giant Scorpion is CR 3 — exceeds Mira's Moon Druid Lv 5 cap of 1.
    Endpoint returns 409 with a message about the CR cap.
    """
    mira = mira_in_base_form
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/transform",
        json={"slug": "giant-scorpion", "source": "wild-shape"},
    )
    assert resp.status_code == 409
    detail = resp.json().get("detail", "").lower()
    assert "cr" in detail or "cap" in detail


@_skip_no_open5e
async def test_transform_already_transformed(gm_client, mira_in_base_form):
    """Transforming twice without reverting returns 409.
    Always reverts at the end (or via the mira_in_base_form fixture
    on the next test) so state stays clean.
    """
    mira = mira_in_base_form
    try:
        # First transform — succeeds
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/transform",
            json={"slug": "wolf", "source": "wild-shape"},
        )
        assert resp.status_code == 200, resp.text

        # Second transform — 409 because active_form is set
        resp = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/transform",
            json={"slug": "cat", "source": "wild-shape"},
        )
        assert resp.status_code == 409
        detail = resp.json().get("detail", "").lower()
        assert "already" in detail or "revert" in detail
    finally:
        # Revert to leave Mira in base form. If the first transform
        # also failed, the revert returns 409 which we ignore.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/character/{mira['id']}/revert",
            json={},
        )


async def test_revert_when_not_transformed(gm_client, roster):
    """Reverting a character that isn't transformed returns 409.
    Pip is a Rogue and never transforms — guaranteed clean baseline.
    """
    pip = roster["Pip Quickfingers"]
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/character/{pip['id']}/revert",
        json={},
    )
    assert resp.status_code == 409
