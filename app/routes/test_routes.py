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

from fastapi import APIRouter
from pydantic import BaseModel

from .. import dice as dice_mod

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
