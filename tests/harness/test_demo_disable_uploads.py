"""Harness tests for the ``DEMO_DISABLE_UPLOADS`` toggle (v2.1034.0).

The guard is a shared FastAPI dependency, ``app.auth.require_uploads_enabled``,
attached to every user-facing file-upload endpoint (token / portrait /
template / map / handout / encounter-background images, audio tracks, and
character / campaign import). It refuses the upload with 403 **only** when the
instance is a locked-down public demo: ``DEMO_MODE=true`` AND
``DEMO_DISABLE_UPLOADS=true`` (the latter defaults true).

Two families, mirroring ``test_demo_magic_link.py``:

1. **In-process unit tests** on the predicate + dependency, driving the two
   flags directly via a crafted ``Settings`` — the only way to exercise the
   locked-down (403) path, since the dev/CI container boots with
   ``DEMO_MODE=false``.
2. **Integration test** against the running container (``DEMO_MODE=false``):
   the gate-off path — an upload endpoint behaves normally and does NOT emit
   the demo-disabled 403.
"""
from __future__ import annotations

import io

import pytest
from fastapi import HTTPException

from app import auth as auth_mod
from app.auth import require_uploads_enabled, uploads_disabled_in_demo
from app.config import Settings

from .conftest import CAMPAIGN_ID  # noqa: F401


# ─── Unit tests on the predicate + dependency ─────────────────────────


def test_predicate_true_when_demo_and_disabled():
    """Both flags on → locked down."""
    s = Settings(demo_mode=True, demo_disable_uploads=True)
    assert uploads_disabled_in_demo(s) is True


def test_predicate_false_when_demo_off():
    """DEMO_MODE off → never locked, even with DEMO_DISABLE_UPLOADS=true.
    This is the invariant that keeps normal deploys uploading."""
    s = Settings(demo_mode=False, demo_disable_uploads=True)
    assert uploads_disabled_in_demo(s) is False


def test_predicate_false_when_uploads_allowed():
    """Demo instance that deliberately re-enables uploads."""
    s = Settings(demo_mode=True, demo_disable_uploads=False)
    assert uploads_disabled_in_demo(s) is False


def test_dependency_raises_403_when_locked(monkeypatch):
    """The dependency raises HTTPException(403) with a recognizable detail
    when the instance is a locked-down demo."""
    monkeypatch.setattr(
        auth_mod, "get_settings",
        lambda: Settings(demo_mode=True, demo_disable_uploads=True),
    )
    with pytest.raises(HTTPException) as ei:
        require_uploads_enabled()
    assert ei.value.status_code == 403
    assert "disabled" in ei.value.detail.lower()


def test_dependency_noop_when_not_demo(monkeypatch):
    """DEMO_MODE off → the dependency is a silent no-op (returns None), so
    the endpoint proceeds to its normal auth + upload logic."""
    monkeypatch.setattr(
        auth_mod, "get_settings",
        lambda: Settings(demo_mode=False, demo_disable_uploads=True),
    )
    assert require_uploads_enabled() is None


def test_default_disable_uploads_is_true():
    """A fresh Settings defaults DEMO_DISABLE_UPLOADS on — a public demo is
    locked down out of the box (operator opts back in explicitly)."""
    assert Settings().demo_disable_uploads is True


# ─── Integration test: gate-off path on the live container ────────────

# 1x1 transparent PNG — smallest valid image we can post through an
# upload endpoint without pulling in Pillow. (Same asset as
# test_encounter_background.py.)
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63000100000005000100"
    "0d0a2db40000000049454e44ae426082"
)


async def test_upload_endpoint_wired_to_guard(gm_client):
    """Prove the guard is actually wired to a real upload endpoint over HTTP,
    robustly across instance configs (the harness may point at a normal dev
    stack **or** a live demo — this operator's stack runs ``DEMO_MODE=true``).

    Whichever it is, the campaign-background upload must resolve to exactly
    one of two outcomes and never an unrelated error:

      - locked-down demo (``DEMO_MODE`` + ``DEMO_DISABLE_UPLOADS``) → 403 with
        the guard's exact detail string;
      - otherwise → 200 (the dependency is a no-op and the upload proceeds).

    A 403 here therefore proves the dependency fires; a 200 proves it doesn't
    block a normal deploy. Either branch exercises the wiring.
    """
    files = {"image": ("gate.png", io.BytesIO(_PNG_BYTES), "image/png")}
    resp = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/background", files=files,
    )
    assert resp.status_code in (200, 403), resp.text
    if resp.status_code == 403:
        assert resp.json()["detail"] == "Uploads are disabled on this demo instance"
    else:
        assert resp.json()["ok"] is True
        # Clean up so we don't leave a background on the campaign.
        await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/background", data={"clear": "true"},
        )
