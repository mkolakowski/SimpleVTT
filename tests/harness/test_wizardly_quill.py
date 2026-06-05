"""v2.99.335 — Order of Scribes Wizard: Wizardly Quill (G.1 batch, Lv 2+, TCE).

G.1 Wizard subclass batch ship #10. RAW TCE p.75: bonus
action to conjure a magical quill. No ink; writes in any
language/script in any color; 4× normal speed; self-erases
as a free action. Vanishes after a long rest.

v1 announce-only — writing/erasing/scribing GM-tracked.
Costs bonus chip.

Tests:
  - Lv 7 happy → 4× speed, multi-lang/color, self-erase.
  - Wrong subclass → 409.
  - Scribes Lv 1 → 409.
"""
import asyncio
import pytest_asyncio

from .conftest import CAMPAIGN_ID


async def _patch_sheet(gm_client, char_id, fields, class_slug=None):
    body = dict(fields)
    if class_slug:
        body["class_slug"] = class_slug
    r = await gm_client.patch(
        f"/api/campaign/{CAMPAIGN_ID}/character/{char_id}/sheet-fields",
        json=body,
    )
    assert r.status_code == 200, r.text


def _wq_broadcasts(gm_ws, character_id):
    return [
        m for m in gm_ws.buffered("feature_used")
        if (m.get("data") or {}).get("source") == "wizardly-quill"
        and (m.get("data") or {}).get("character_id") == character_id
    ]


@pytest_asyncio.fixture
async def thalindra_scribes(gm_client, roster):
    """PATCH Thalindra to Order of Scribes."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "Order of Scribes"},
        class_slug="wizard",
    )
    try:
        yield thal
    finally:
        await _patch_sheet(
            gm_client, thal["id"],
            {"subclass": "School of Evocation", "level": 7},
            class_slug="wizard",
        )


async def test_use_wq_happy_lv7(
    gm_client, gm_ws, thalindra_scribes,
):
    """Lv 7 Scribes → 4× speed, multi-lang/color, self-erase."""
    thal = thalindra_scribes
    gm_ws.mark()
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_wizardly_quill",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["speed_multiplier"] == 4
    assert data["writes_in_any_language"] is True
    assert data["writes_in_any_color"] is True
    assert data["self_erase"] is True
    assert data["duration"] == "until_long_rest"
    assert data["wizard_level"] == 7
    await asyncio.sleep(0.3)
    feats = _wq_broadcasts(gm_ws, thal["id"])
    assert feats


async def test_use_wq_wrong_subclass(
    gm_client, roster,
):
    """Default Thalindra (Evocation) → 409."""
    thal = roster["Thalindra Moonwhisper"]
    r = await gm_client.post(
        f"/api/campaign/{CAMPAIGN_ID}/use_wizardly_quill",
        json={"character_id": thal["id"], "override": True},
    )
    assert r.status_code == 409, r.text
    data = r.json()
    assert data.get("error") == "wrong_subclass_or_level"


async def test_use_wq_level_gate(
    gm_client, roster,
):
    """Scribes Thalindra at Lv 1 → 409."""
    thal = roster["Thalindra Moonwhisper"]
    await _patch_sheet(
        gm_client, thal["id"],
        {"subclass": "Order of Scribes", "level": 1},
        class_slug="wizard",
    )
    try:
        r = await gm_client.post(
            f"/api/campaign/{CAMPAIGN_ID}/use_wizardly_quill",
            json={"character_id": thal["id"], "override": True},
        )
        assert r.status_code == 409, r.text
        data = r.json()
        assert data.get("error") == "wrong_subclass_or_level"
    finally:
        await _patch_sheet(
            gm_client, thal["id"],
            {"subclass": "School of Evocation", "level": 7},
            class_slug="wizard",
        )
