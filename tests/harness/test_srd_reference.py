"""v2.1020.0 — In-app SRD 5.1 rules reference.

A searchable browser over the shipped player-safe SRD content
(conditions, spells, equipment, feats, races, backgrounds) so players +
GMs can look up rules without leaving the VTT. SRD content is CC-BY, so
the page + API are public (like the wiki).

  - GET /reference — the HTML page (search box + type filter).
  - GET /api/reference/search?type=&q= — JSON: full-text records from the
    shipped SRD tier only (no homebrew, no monsters).

Tests:
  - Page renders with the search UI + nav.
  - Search all types (empty query) returns SRD records with desc text.
  - Type filter (conditions) returns only conditions; a known condition
    (Grappled) is findable by name.
  - Spell search (Fireball) returns the spell with a description.
  - Monsters are NOT searchable (GM-visibility data excluded).
  - Unknown type → 404.
"""
import httpx

from .helpers import BASE_URL


async def test_reference_page_renders():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.get("/reference")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    body = r.text.lower()
    assert "srd 5.1 reference" in body
    assert 'id="ref-q"' in r.text          # the search input
    assert 'class="wiki-nav"' in r.text     # nav injected


async def test_reference_search_all_returns_records():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.get("/api/reference/search", params={"type": "all"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] >= 1
    assert data["results"], "expected some SRD records"
    first = data["results"][0]
    for key in ("slug", "name", "type", "type_label", "desc", "source"):
        assert key in first
    assert first["source"] == "local-srd"
    # Every returned record is one of the player-safe types (never monster).
    safe = {"conditions", "spells", "items", "feats", "races", "backgrounds"}
    assert all(rec["type"] in safe for rec in data["results"])


async def test_reference_search_conditions_finds_grappled():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.get(
            "/api/reference/search",
            params={"type": "conditions", "q": "grappled"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    grappled = next(
        (rec for rec in data["results"] if rec["slug"] == "grappled"), None)
    assert grappled is not None, "Grappled condition not found in SRD reference"
    assert grappled["type"] == "conditions"
    assert grappled["type_label"] == "Condition"
    assert grappled["desc"], "Grappled should have description text"


async def test_reference_search_spell_fireball():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.get(
            "/api/reference/search",
            params={"type": "spells", "q": "fireball"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    fb = next((rec for rec in data["results"] if rec["slug"] == "fireball"), None)
    assert fb is not None, "Fireball not found in SRD reference"
    assert fb["type"] == "spells"
    assert fb["desc"]


async def test_reference_search_excludes_monsters():
    """Monsters are GM-visibility data — never a valid reference type."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.get(
            "/api/reference/search", params={"type": "monsters"})
    assert r.status_code == 404, r.text


async def test_reference_search_unknown_type():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.get(
            "/api/reference/search", params={"type": "bogus"})
    assert r.status_code == 404, r.text
