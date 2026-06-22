"""Phase 1 of docs/plans/homebrew-fork-srd.md — fork SRD mechanics as homebrew.

`POST /api/campaign/{id}/homebrew/fork` lets a GM copy a shipped SRD record
into their campaign's homebrew scope so they can tweak it (the tweaking UI is
Phase 2). Two modes:

  - variant  — fresh "copy-of-<slug>" slug, " (Homebrew)" name (a distinct
    new mechanic).
  - override — same slug at campaign scope; shadows the SRD record for THIS
    campaign via the loader's campaign→global→shipped priority.

`DELETE /api/campaign/{id}/homebrew/{type}/{slug}` reverts (un-forks) a
campaign-scoped record.

The fork copies the SRD record verbatim (no mechanical change here), and
always lands in the homebrew tier (`source:"custom"`), never the shipped
tree — so `test_srd_provenance` stays green. Tests revert in `finally` for
hygiene; a leaked override is mechanically identical to SRD anyway.
"""
import pytest

from .conftest import CAMPAIGN_ID


async def _fork(client, ctype, src_slug, mode):
    return await client.post(
        f"/api/campaign/{CAMPAIGN_ID}/homebrew/fork",
        json={"type": ctype, "src_slug": src_slug, "mode": mode},
    )


async def _revert(client, ctype, slug):
    return await client.delete(
        f"/api/campaign/{CAMPAIGN_ID}/homebrew/{ctype}/{slug}",
    )


async def _edit(client, ctype, slug, record):
    return await client.post(
        f"/api/campaign/{CAMPAIGN_ID}/homebrew/{ctype}/{slug}/edit",
        json=record,
    )


async def _lookup(client, ctype, slug, campaign_id=None):
    url = f"/api/content/{ctype}/{slug}"
    if campaign_id is not None:
        url += f"?campaign_id={campaign_id}"
    return await client.get(url)


async def test_fork_srd_spell_variant(gm_client):
    """Fork the SRD Fireball in variant mode → a fresh campaign-homebrew
    record (source 'custom', '(Homebrew)' name) resolvable for the campaign."""
    r = await _fork(gm_client, "spells", "fireball", "variant")
    assert r.status_code == 200, r.text
    data = r.json()
    new_slug = data["slug"]
    try:
        assert new_slug.startswith("copy-of-fireball"), data
        assert data["mode"] == "variant"
        assert data["forked_from"] == "fireball"
        look = await _lookup(gm_client, "spells", new_slug, CAMPAIGN_ID)
        assert look.status_code == 200, look.text
        body = look.json()
        assert body["source"] == "local-homebrew", body
        rec = body["record"]
        assert rec["source"] == "custom", rec
        assert "(Homebrew)" in rec["name"]
        # Verbatim copy: the headline mechanic carried over.
        assert any(a.get("damage") == "8d6" for a in rec.get("actions", [])), rec
    finally:
        await _revert(gm_client, "spells", new_slug)


async def test_fork_srd_spell_override_shadows_only_this_campaign(gm_client):
    """Override mode writes the SRD slug at campaign scope: the campaign now
    resolves the homebrew copy, while a no-campaign lookup still returns the
    pristine shipped SRD record (other campaigns unaffected)."""
    await _revert(gm_client, "spells", "fireball")  # best-effort pre-clean
    r = await _fork(gm_client, "spells", "fireball", "override")
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == "fireball"
    try:
        # Campaign sees the homebrew override...
        camp = await _lookup(gm_client, "spells", "fireball", CAMPAIGN_ID)
        assert camp.status_code == 200, camp.text
        assert camp.json()["source"] == "local-homebrew", camp.json()
        assert camp.json()["record"]["source"] == "custom"
        # ...but the shipped SRD record is untouched (no campaign scope).
        srd = await _lookup(gm_client, "spells", "fireball")
        assert srd.status_code == 200, srd.text
        assert srd.json()["source"] == "local-srd", srd.json()
        assert srd.json()["record"]["source"] == "srd"
    finally:
        await _revert(gm_client, "spells", "fireball")


async def test_override_twice_conflicts(gm_client):
    """A second override of an already-overridden slug → 409 (don't clobber
    the GM's tweaks)."""
    await _revert(gm_client, "spells", "bless")  # best-effort pre-clean
    first = await _fork(gm_client, "spells", "bless", "override")
    assert first.status_code == 200, first.text
    try:
        again = await _fork(gm_client, "spells", "bless", "override")
        assert again.status_code == 409, again.text
    finally:
        await _revert(gm_client, "spells", "bless")


async def test_fork_srd_monster_variant(gm_client):
    """Type-generality: fork a non-spell SRD record (a monster)."""
    r = await _fork(gm_client, "monsters", "commoner", "variant")
    assert r.status_code == 200, r.text
    new_slug = r.json()["slug"]
    try:
        look = await _lookup(gm_client, "monsters", new_slug, CAMPAIGN_ID)
        assert look.status_code == 200, look.text
        assert look.json()["record"]["source"] == "custom"
    finally:
        await _revert(gm_client, "monsters", new_slug)


async def test_fork_requires_gm(bob_client):
    """A non-GM campaign member cannot fork — 403."""
    r = await _fork(bob_client, "spells", "fireball", "variant")
    assert r.status_code == 403, r.text


async def test_fork_unknown_slug_404(gm_client):
    r = await _fork(gm_client, "spells", "not-a-real-spell-xyz", "variant")
    assert r.status_code == 404, r.text


async def test_fork_unknown_type_404(gm_client):
    r = await _fork(gm_client, "widgets", "fireball", "variant")
    assert r.status_code == 404, r.text


async def test_fork_bad_mode_400(gm_client):
    r = await _fork(gm_client, "spells", "fireball", "sideways")
    assert r.status_code == 400, r.text


async def test_revert_unknown_404(gm_client):
    """Reverting a campaign homebrew record that doesn't exist → 404."""
    r = await _revert(gm_client, "spells", "definitely-not-forked-abc")
    assert r.status_code == 404, r.text


# ── Phase 2: GM editor write path ────────────────────────────────────────────
async def test_edit_forked_record_tweaks_mechanics(gm_client):
    """Fork an SRD spell, then edit its mechanics (damage 8d6 → 10d6) via the
    GM editor endpoint — the tweak persists for the campaign."""
    r = await _fork(gm_client, "spells", "fireball", "variant")
    assert r.status_code == 200, r.text
    slug = r.json()["slug"]
    try:
        rec = (await _lookup(gm_client, "spells", slug, CAMPAIGN_ID)).json()["record"]
        # Tweak the headline mechanic + the name.
        for a in rec.get("actions", []):
            if a.get("damage") == "8d6":
                a["damage"] = "10d6"
        rec["name"] = "Bigger Fireball"
        ed = await _edit(gm_client, "spells", slug, rec)
        assert ed.status_code == 200, ed.text
        after = (await _lookup(gm_client, "spells", slug, CAMPAIGN_ID)).json()["record"]
        assert after["name"] == "Bigger Fireball", after
        assert any(a.get("damage") == "10d6" for a in after.get("actions", [])), after
        assert after["source"] == "custom"
    finally:
        await _revert(gm_client, "spells", slug)


async def test_edit_forces_campaign_scope(gm_client):
    """Even if the payload claims scope:'global', the edit is written at
    campaign scope — a GM can't escalate to global / shipped content."""
    r = await _fork(gm_client, "spells", "fireball", "variant")
    assert r.status_code == 200, r.text
    slug = r.json()["slug"]
    try:
        rec = (await _lookup(gm_client, "spells", slug, CAMPAIGN_ID)).json()["record"]
        rec["scope"] = "global"  # attempt to escalate
        ed = await _edit(gm_client, "spells", slug, rec)
        assert ed.status_code == 200, ed.text
        assert ed.json()["scope"] == f"campaign-{CAMPAIGN_ID}"
        # The variant slug must NOT be visible globally (no campaign id).
        glob = await _lookup(gm_client, "spells", slug)
        assert glob.status_code == 404, glob.text
    finally:
        await _revert(gm_client, "spells", slug)


async def test_edit_slug_mismatch_400(gm_client):
    r = await _fork(gm_client, "spells", "fireball", "variant")
    assert r.status_code == 200, r.text
    slug = r.json()["slug"]
    try:
        rec = (await _lookup(gm_client, "spells", slug, CAMPAIGN_ID)).json()["record"]
        rec["slug"] = "some-other-slug"
        ed = await _edit(gm_client, "spells", slug, rec)
        assert ed.status_code == 400, ed.text
    finally:
        await _revert(gm_client, "spells", slug)


async def test_edit_requires_gm(gm_client, bob_client):
    """A non-GM cannot edit campaign homebrew — 403 (set up the fork as GM)."""
    r = await _fork(gm_client, "spells", "fireball", "variant")
    assert r.status_code == 200, r.text
    slug = r.json()["slug"]
    try:
        rec = (await _lookup(gm_client, "spells", slug, CAMPAIGN_ID)).json()["record"]
        ed = await _edit(bob_client, "spells", slug, rec)
        assert ed.status_code == 403, ed.text
    finally:
        await _revert(gm_client, "spells", slug)


async def test_edit_unknown_type_404(gm_client):
    r = await _edit(gm_client, "widgets", "whatever", {"slug": "whatever"})
    assert r.status_code == 404, r.text
