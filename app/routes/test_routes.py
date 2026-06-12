"""Test-mode-only endpoints.

Mounted from ``app/main.py`` ONLY when the ``TEST_MODE`` env var is
true (parsed via ``_env_bool``). Production deployments leave it off,
so none of these routes exist on the live API surface — they 404
before any handler runs because the router was never included.

v2.49.12 adds the first endpoint: ``POST /api/test/dice/seed``. The
encounter-simulation harness (docs/plans/encounter-sim-test-suite.md)
calls this at test setup to make the shared dice RNG deterministic
so assertions like "Fireball 8d6 = 24 fire damage" don't flake.

Future test-only endpoints (clear-battle, force-init-order, etc.)
land here too. Keep the router scoped to genuinely test-only surfaces
— anything an actual operator might use belongs in ``admin_routes``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import dice as dice_mod
from ..database import get_db
from ..models import Campaign

router = APIRouter()


class _SeedRequest(BaseModel):
    seed: int | None = None  # None = re-seed from OS entropy


@router.post("/api/test/dice/seed")
def seed_dice(body: _SeedRequest) -> dict:
    """Set the seed of the shared dice RNG. With a fixed seed every
    subsequent ``XdY`` roll is reproducible. Passing ``seed: null``
    returns the RNG to non-deterministic mode (OS entropy).

    No auth — this endpoint only exists when TEST_MODE is true, which
    is gated at the env var level. The test stack is the only place
    that boots with that env var set.
    """
    dice_mod.set_seed(body.seed)
    return {"ok": True, "seed": body.seed}


class _CampaignFlagsRequest(BaseModel):
    # Only the flags a test needs to flip. ``None`` leaves the flag
    # untouched so a caller can set one without clobbering the others.
    auto_apply_damage: bool | None = None


@router.post("/api/test/campaign/{campaign_id}/flags")
def set_campaign_flags(
    campaign_id: int,
    body: _CampaignFlagsRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Flip campaign-level boolean settings the harness needs without
    driving the full GM settings form (which is multipart and resets
    every other field). Only the flags listed on ``_CampaignFlagsRequest``
    are mutable here; a ``None`` field is left as-is so a test can set
    one flag and restore it in a ``finally`` without disturbing others.

    No auth — TEST_MODE-only, same as ``/api/test/dice/seed``.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(404, "campaign not found")
    if body.auto_apply_damage is not None:
        campaign.auto_apply_damage = body.auto_apply_damage
    db.commit()
    return {"ok": True, "auto_apply_damage": bool(campaign.auto_apply_damage)}
