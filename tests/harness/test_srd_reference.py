"""v2.1020.0 — In-app SRD 5.1 rules reference.

A searchable browser over the shipped player-safe SRD content
(conditions, spells, equipment, feats, races, backgrounds) so players +
GMs can look up rules without leaving the VTT. SRD content is CC-BY, so
the page + API are public (like the wiki).

  - GET /reference — the HTML page (search box + type filter).
  - GET /api/reference/search?type=&q= — JSON: full-text records from the
    shipped SRD tier only (no homebrew, no monsters).
  - GET /api/reference/entry?type=&slug= — JSON: a SINGLE shipped-SRD
    record (Phase 3 substrate for inline contextual rule popovers).

Tests:
  - Page renders with the search UI + nav.
  - Search all types (empty query) returns SRD records with desc text.
  - Type filter (conditions) returns only conditions; a known condition
    (Grappled) is findable by name.
  - Spell search (Fireball) returns the spell with a description.
  - Monsters are NOT searchable (GM-visibility data excluded).
  - Unknown type → 404.
  - Entry lookup (conditions/blinded) returns one record with desc text.
  - Entry lookup rejects an unknown slug (404), an unknown type (404),
    and a monster type (404 — GM-visibility perimeter).
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
    safe = {"conditions", "rules", "spells", "items", "feats",
            "races", "backgrounds"}
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


async def test_reference_search_is_full_text():
    """v2.1022.0 Phase 2a — the query matches description text, not just
    names. "prone" appears in the Prone condition's name AND in many
    spell/condition descriptions; a full-text search returns entries
    whose NAME doesn't contain "prone" but whose DESC does (name_match
    False), proving description matching works."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.get(
            "/api/reference/search", params={"type": "all", "q": "prone"})
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert results, "expected full-text matches for 'prone'"
    # At least one desc-only match (name doesn't contain the needle).
    desc_only = [x for x in results
                 if not x["name_match"] and "prone" not in x["name"].lower()]
    assert desc_only, (
        "full-text search should surface entries matching only in the "
        "description"
    )
    # Every result genuinely contains the needle in name or desc.
    for x in results:
        assert ("prone" in x["name"].lower()) or ("prone" in x["desc"].lower())
    # Name matches rank ahead of description-only matches.
    first_desc_only = next(
        (i for i, x in enumerate(results) if not x["name_match"]), None)
    last_name_match = max(
        (i for i, x in enumerate(results) if x["name_match"]), default=-1)
    if first_desc_only is not None and last_name_match >= 0:
        assert last_name_match < first_desc_only, (
            "name matches should sort before description-only matches")


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


async def test_reference_entry_returns_single_record():
    """v2.1025.0 Phase 3 — single-entry lookup returns one shipped-SRD
    record by type + slug, shaped like a search result so consumers can
    reuse the search-card rendering."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.get(
            "/api/reference/entry",
            params={"type": "conditions", "slug": "blinded"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    for key in ("slug", "name", "type", "type_label", "desc", "source"):
        assert key in data
    assert data["slug"] == "blinded"
    assert data["type"] == "conditions"
    assert data["type_label"] == "Condition"
    assert data["source"] == "local-srd"
    assert data["desc"], "Blinded should carry SRD rule text"


async def test_reference_entry_unknown_slug():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.get(
            "/api/reference/entry",
            params={"type": "conditions", "slug": "no-such-condition"},
        )
    assert r.status_code == 404, r.text


async def test_reference_entry_unknown_type():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.get(
            "/api/reference/entry",
            params={"type": "bogus", "slug": "blinded"},
        )
    assert r.status_code == 404, r.text


async def test_reference_search_rules_finds_cover():
    """v2.1029.0 Phase 3 — the new ``rules`` type surfaces the non-content
    SRD rules sections (actions in combat, cover, resting, …) that live in
    no other per-type JSON. Cover is findable by name and carries its
    rephrased rule text."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.get(
            "/api/reference/search", params={"type": "rules", "q": "cover"})
    assert r.status_code == 200, r.text
    data = r.json()
    cover = next((rec for rec in data["results"] if rec["slug"] == "cover"), None)
    assert cover is not None, "Cover rule not found in SRD reference"
    assert cover["type"] == "rules"
    assert cover["type_label"] == "Rule"
    assert "three-quarters cover" in cover["desc"].lower(), (
        "Cover rule should describe the degrees of cover")


async def test_reference_entry_returns_rule():
    """The single-entry lookup resolves a rules-type slug (Grappling)."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.get(
            "/api/reference/entry",
            params={"type": "rules", "slug": "grappling"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["slug"] == "grappling"
    assert data["type"] == "rules"
    assert data["source"] == "local-srd"
    assert "athletics" in data["desc"].lower()


async def test_reference_rules_adventuring_environment_batch():
    """v2.1030.0 Phase 3 — the second rules batch adds Adventuring +
    Environment sections. Long Rest is findable by name, and the Falling
    rule resolves via the single-entry lookup with its 1d6-per-10-feet
    text."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        s = await client.get(
            "/api/reference/search", params={"type": "rules", "q": "long rest"})
        e = await client.get(
            "/api/reference/entry", params={"type": "rules", "slug": "falling"})
    assert s.status_code == 200, s.text
    long_rest = next(
        (r for r in s.json()["results"] if r["slug"] == "long-rest"), None)
    assert long_rest is not None, "Long Rest rule not found"
    assert long_rest["type_label"] == "Rule"
    assert e.status_code == 200, e.text
    falling = e.json()
    assert falling["slug"] == "falling"
    assert "1d6" in falling["desc"], "Falling rule should cite 1d6 per 10 feet"


async def test_reference_rules_objects_and_situational_batch():
    """v2.1031.0 Phase 3 — the third rules batch closes the sections the
    plan filed as remaining: Objects & interaction, underwater combat,
    mounted combat, and madness. Underwater Combat is findable by name,
    and the Objects rule resolves via the single-entry lookup with its
    material-AC table text."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        s = await client.get(
            "/api/reference/search",
            params={"type": "rules", "q": "underwater"})
        e = await client.get(
            "/api/reference/entry", params={"type": "rules", "slug": "objects"})
    assert s.status_code == 200, s.text
    underwater = next(
        (r for r in s.json()["results"] if r["slug"] == "underwater-combat"),
        None)
    assert underwater is not None, "Underwater Combat rule not found"
    assert underwater["type_label"] == "Rule"
    assert e.status_code == 200, e.text
    objects = e.json()
    assert objects["slug"] == "objects"
    assert objects["type"] == "rules"
    # The material-AC table is the mechanical payload GMs look this up for.
    assert "AC 15" in objects["desc"], "Objects rule should cite material ACs"


async def test_reference_rules_full_text_finds_madness():
    """The Phase 2a full-text path reaches the new batch too: searching a
    phrase that appears only in Madness's body (not its name) returns it."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.get(
            "/api/reference/search",
            params={"type": "rules", "q": "indefinite madness"})
    assert r.status_code == 200, r.text
    slugs = {x["slug"] for x in r.json()["results"]}
    assert "madness" in slugs, f"full-text miss for Madness: {slugs}"


async def test_reference_entry_excludes_monsters():
    """Monsters are GM-visibility data — never a valid reference type,
    same perimeter as the search endpoint."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        r = await client.get(
            "/api/reference/entry",
            params={"type": "monsters", "slug": "goblin"},
        )
    assert r.status_code == 404, r.text
