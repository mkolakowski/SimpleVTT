"""v2.1032.0 — SRD Reference Phase 3 close-out: the 📖 rules chip.

The initiative tracker's action-economy strip (Act / Bns / Rxn / Mov)
gains a 📖 chip that opens the SRD "actions in combat" rules in the
same popover the ⚠ Conditions pill uses. This is the contextual-rules-
link slice that closes Phase 3.

The chip itself is rendered client-side inside ``renderBattle``'s
template literal, so an HTTP harness can't click it. What it *can*
pin down is the two things that actually regress:

  1. The chip markup + its ``data-ref-type`` / ``data-ref-slugs``
     contract survive in the served page (a rename of either attribute
     silently breaks the popover, since the JS reads them by name).
  2. **Every slug the chip lists resolves via ``/api/reference/entry``.**
     This is the real regression net: a typo in the slug list, or a
     deleted/renamed rule JSON, would leave the popover rendering
     "No SRD rule text available" with no server-side error anywhere.

Test 2 parses the slug list out of the page rather than hardcoding a
copy, so the assertion tracks the chip instead of drifting from it.
"""
from .conftest import CAMPAIGN_ID


def _chip_tag(html: str) -> str:
    """Return the ``<button class="rule-ref-chip" …>`` tag source."""
    # Anchor on the class *attribute*, not the bare name — the first
    # "rule-ref-chip" in the document is the CSS rule in <head>, which
    # has no enclosing <button>.
    idx = html.find('class="rule-ref-chip"')
    assert idx >= 0, "The 📖 .rule-ref-chip was not found in the page source"
    start = html.rfind("<button", 0, idx)
    assert start >= 0
    end = html.find(">", idx)
    assert end > start
    return html[start:end + 1]


def _chip_slugs(html: str) -> list[str]:
    """Parse the chip's ``data-ref-slugs`` list out of the page."""
    tag = _chip_tag(html)
    marker = 'data-ref-slugs="'
    i = tag.find(marker)
    assert i >= 0, f"chip tag carries no data-ref-slugs: {tag!r}"
    raw = tag[i + len(marker):tag.find('"', i + len(marker))]
    slugs = [s.strip() for s in raw.split(",") if s.strip()]
    assert slugs, "data-ref-slugs parsed empty"
    return slugs


async def test_econ_strip_carries_rules_reference_chip(gm_client):
    """The tabletop page ships the 📖 chip with the attribute pair the
    popover JS reads (`data-ref-type="rules"` + `data-ref-slugs`)."""
    resp = await gm_client.get(f"/campaign/{CAMPAIGN_ID}")
    assert resp.status_code == 200, resp.text
    tag = _chip_tag(resp.text)
    assert 'data-ref-type="rules"' in tag, (
        f"chip must declare the rules reference tier; got: {tag!r}"
    )
    assert "data-ref-slugs=" in tag, (
        f"chip must carry a slug list for the popover; got: {tag!r}"
    )
    # A real <button> (not a role="button" span) — Enter/Space fire click
    # natively, which is why the chip is deliberately absent from the
    # keydown handler that serves the ⚠ pill.
    assert tag.startswith("<button"), (
        f"chip should be a real button for native keyboard activation: {tag!r}"
    )


async def test_econ_rule_chip_slugs_all_resolve(gm_client):
    """Every slug the chip lists resolves against the shipped SRD tier.

    This is the assertion that catches a typo or a deleted rule file —
    both of which would degrade the popover silently.
    """
    resp = await gm_client.get(f"/campaign/{CAMPAIGN_ID}")
    assert resp.status_code == 200, resp.text
    slugs = _chip_slugs(resp.text)
    # Sanity: the chip should cover the core action-economy verbs.
    assert "actions-in-combat" in slugs
    assert "dash" in slugs
    for slug in slugs:
        r = await gm_client.get(
            "/api/reference/entry", params={"type": "rules", "slug": slug})
        assert r.status_code == 200, (
            f"chip lists rules slug {slug!r} but /api/reference/entry "
            f"returned {r.status_code} — the popover would render empty "
            f"for this entry. Body: {r.text}"
        )
        body = r.json()
        assert body["slug"] == slug
        assert body["type"] == "rules"
        assert (body.get("desc") or "").strip(), (
            f"rules entry {slug!r} resolved but has empty desc — the "
            f"popover would show a blank block."
        )


async def test_reference_entry_rules_unknown_slug_404s(gm_client):
    """Error path: a slug that isn't in the shipped rules tier 404s
    rather than returning an empty record the popover would render."""
    r = await gm_client.get(
        "/api/reference/entry",
        params={"type": "rules", "slug": "no-such-rule-xyz"})
    assert r.status_code == 404, r.text
