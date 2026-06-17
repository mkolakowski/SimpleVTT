"""v2.399.0 — Halfling Nimbleness + Naturally Stealthy recognition
flags (race-features plan Phases 4a + 5a).

RAW PHB p.28:
- **Halfling Nimbleness:** "You can move through the space of any
  creature that is of a size larger than yours." Race-gated to any
  Halfling.
- **Naturally Stealthy:** "You can attempt to hide even when you
  are obscured only by a creature that is at least one size larger
  than you." Lightfoot-subrace-gated.

Neither underlying substrate exists server-side today:
- /token/move doesn't enforce the RAW PHB p.190 "moving through
  other creatures" restriction (any token can cross any other).
- /roll with stat_key="Stealth" doesn't enforce LOS / cover gates
  (Stealth always rolls).

So both Halfling exemptions are vacuously satisfied. v2.399.0 ships
the **recognition** half of both: `derived.halfling_nimbleness` and
`derived.naturally_stealthy` blocks on `/sheet-json` so chat-card /
UI / harness can attribute the traits. Phases 4b + 5b (full
enforcement) are filed for the future movement / Stealth-cover arcs.

Test strategy (3 tests):
1. Pip (Halfling) → both `derived.halfling_nimbleness.applies` and
   `derived.naturally_stealthy.applies` are True; sources cite PHB
   p.28; enforcement_status contains "filed for Phase 4b/5b".
2. Krieger (Half-Orc) control → neither flag present in `derived`.
3. The recognition blocks carry the verbatim RAW clauses (a future
   refactor that drops them should fail this guard).
"""
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _get_derived(gm_client, char_id: int) -> dict:
    snap = await gm_client.get(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-json",
    )
    body = snap.json() or {}
    return body.get("derived") or {}


async def test_halfling_recognition_flags_for_pip(gm_client, roster):
    """Pip (Lightfoot Halfling) gets BOTH recognition flags on
    /sheet-json's derived block: halfling_nimbleness (Phase 4a) and
    naturally_stealthy (Phase 5a). Both are informational —
    server-side enforcement of the RAW move-through-larger and
    Stealth-cover rules is filed for Phases 4b + 5b."""
    pip = roster["Pip Quickfingers"]
    derived = await _get_derived(gm_client, pip["id"])

    nim = derived.get("halfling_nimbleness")
    assert nim is not None, (
        f"Pip (Halfling) should have derived.halfling_nimbleness; "
        f"got derived = {derived}"
    )
    assert nim.get("applies") is True
    assert "halfling" in (nim.get("source") or "").lower()
    assert "phase 4b" in (nim.get("enforcement_status") or "").lower()
    assert "larger" in (nim.get("raw_clause") or "").lower()

    stealthy = derived.get("naturally_stealthy")
    assert stealthy is not None, (
        f"Pip (Lightfoot Halfling) should have derived.naturally_stealthy; "
        f"got derived = {derived}"
    )
    assert stealthy.get("applies") is True
    assert "lightfoot" in (stealthy.get("source") or "").lower()
    assert "phase 5b" in (stealthy.get("enforcement_status") or "").lower()
    assert "hide" in (stealthy.get("raw_clause") or "").lower()
    assert "larger" in (stealthy.get("raw_clause") or "").lower()


async def test_halfling_recognition_flags_not_for_non_halfling(
    gm_client, roster,
):
    """Control: Krieger (Half-Orc) does NOT get either flag.
    Race-gate regression guard."""
    krieger = roster["Krieger Stonefist"]
    derived = await _get_derived(gm_client, krieger["id"])
    assert "halfling_nimbleness" not in derived, (
        f"non-Halfling Krieger should NOT have derived.halfling_nimbleness; "
        f"got {derived.get('halfling_nimbleness')}"
    )
    assert "naturally_stealthy" not in derived, (
        f"non-Halfling Krieger should NOT have derived.naturally_stealthy; "
        f"got {derived.get('naturally_stealthy')}"
    )


async def test_halfling_recognition_carries_raw_clauses(gm_client, roster):
    """The recognition blocks carry the verbatim RAW PHB p.28 clauses
    so future refactors that drop them fail this guard. The clauses
    are also the chat-card / UI surface text — losing them would
    silently degrade the player-facing description."""
    pip = roster["Pip Quickfingers"]
    derived = await _get_derived(gm_client, pip["id"])
    nim_clause = (derived.get("halfling_nimbleness") or {}).get("raw_clause") or ""
    stealthy_clause = (derived.get("naturally_stealthy") or {}).get("raw_clause") or ""
    assert "move through the space of any creature" in nim_clause.lower(), (
        f"halfling_nimbleness raw_clause missing the RAW PHB p.28 text; "
        f"got {nim_clause!r}"
    )
    assert "obscured only by a creature" in stealthy_clause.lower(), (
        f"naturally_stealthy raw_clause missing the RAW PHB p.28 text; "
        f"got {stealthy_clause!r}"
    )
