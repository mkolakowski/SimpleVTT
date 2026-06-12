"""v2.178.0 — legendary-actions regional-effects pure-Python unit tests.

Tests against the leaf module `app.content.regional_effects`. Pure-Python;
no HTTP / WS harness fixtures. RAW MM p.11 / each chromatic dragon's
"Regional Effects" sidebar. See `docs/plans/legendary-actions.md`.
"""
from app.content.regional_effects import (
    REGIONAL_EFFECTS_BY_SLUG,
    regional_effects_for_slug,
)


# ── regional_effects_for_slug ────────────────────────────────────────────────


def test_adult_red_dragon_has_three_regional_effects():
    re_ = regional_effects_for_slug("adult-red-dragon")
    assert len(re_) == 3
    ids = {e["id"] for e in re_}
    assert ids == {"minor-earthquakes", "fouled-water", "fire-portals"}


def test_every_effect_has_id_name_desc():
    re_ = regional_effects_for_slug("adult-red-dragon")
    for e in re_:
        assert e["id"]
        assert e["name"]
        assert e["desc"]


def test_ancient_red_dragon_shares_the_volcanic_region():
    """Dragons of every age share the same regional effects (RAW: the
    effects are tied to the lair's region, not the creature's age)."""
    adult = regional_effects_for_slug("adult-red-dragon")
    ancient = regional_effects_for_slug("ancient-red-dragon")
    assert [e["id"] for e in adult] == [e["id"] for e in ancient]
    assert adult == ancient


def test_unknown_slug_returns_empty_list():
    assert regional_effects_for_slug("bandit") == []
    assert regional_effects_for_slug("adult-red-dragon-nope") == []


def test_blank_or_non_string_slug_returns_empty_list():
    assert regional_effects_for_slug("") == []
    assert regional_effects_for_slug(None) == []
    assert regional_effects_for_slug(123) == []


def test_slug_lookup_is_case_and_whitespace_insensitive():
    assert len(regional_effects_for_slug("  Adult-Red-Dragon  ")) == 3


def test_returned_list_is_a_deep_copy():
    """Mutating the returned list / dicts must not corrupt the module
    source."""
    re_ = regional_effects_for_slug("adult-red-dragon")
    re_[0]["desc"] = "MUTATED"
    re_.append({"id": "bogus"})
    fresh = regional_effects_for_slug("adult-red-dragon")
    assert len(fresh) == 3
    assert all(e["id"] != "bogus" for e in fresh)
    assert all(e["desc"] != "MUTATED" for e in fresh)
    assert REGIONAL_EFFECTS_BY_SLUG["adult-red-dragon"][0]["desc"] != "MUTATED"


# ── chromatic coverage ───────────────────────────────────────────────────────


def test_all_ten_chromatic_slugs_are_keyed():
    """Adult + ancient × black/blue/green/red/white = 10 lair slugs."""
    for color in ("black", "blue", "green", "red", "white"):
        for age in ("adult", "ancient"):
            slug = f"{age}-{color}-dragon"
            assert slug in REGIONAL_EFFECTS_BY_SLUG, slug
            assert len(regional_effects_for_slug(slug)) == 3


def test_each_chromatic_color_shares_adult_and_ancient():
    for color in ("black", "blue", "green", "white"):
        adult = regional_effects_for_slug(f"adult-{color}-dragon")
        ancient = regional_effects_for_slug(f"ancient-{color}-dragon")
        assert adult == ancient
        assert [e["id"] for e in adult] == [e["id"] for e in ancient]


def test_black_swamp_region_shape():
    re_ = regional_effects_for_slug("adult-black-dragon")
    ids = {e["id"] for e in re_}
    assert ids == {"obscuring-fog", "twisted-plants", "tainted-water"}


def test_blue_desert_region_shape():
    re_ = regional_effects_for_slug("adult-blue-dragon")
    ids = {e["id"] for e in re_}
    assert ids == {"thunderstorms", "treacherous-sand", "sand-spouts"}


def test_green_forest_region_shape():
    re_ = regional_effects_for_slug("adult-green-dragon")
    ids = {e["id"] for e in re_}
    assert ids == {"labyrinth-thickets", "cunning-predators", "whispering-glades"}


def test_white_arctic_region_shape():
    re_ = regional_effects_for_slug("adult-white-dragon")
    ids = {e["id"] for e in re_}
    assert ids == {"chill-fog", "freezing-precipitation", "frozen-sculptures"}
