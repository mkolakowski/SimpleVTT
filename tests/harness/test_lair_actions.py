"""v2.168.0 — legendary-actions Phase 3a pure-Python unit tests.

Tests against the leaf module `app.content.lair_actions`. Pure-Python;
no HTTP / WS harness fixtures. RAW MM — Red Dragon volcanic "Lair
Actions" sidebar. See `docs/plans/legendary-actions.md` Phase 3a.
"""
from app.content.lair_actions import (
    LAIR_ACTIONS_BY_SLUG,
    lair_action_by_id,
    lair_actions_for_slug,
)


# ── lair_actions_for_slug ────────────────────────────────────────────────────


def test_adult_red_dragon_has_three_lair_actions():
    la = lair_actions_for_slug("adult-red-dragon")
    assert len(la) == 3
    ids = {a["id"] for a in la}
    assert ids == {"magma-erupts", "tremor", "volcanic-gases"}


def test_magma_erupts_is_a_dex_save_aoe():
    la = lair_actions_for_slug("adult-red-dragon")
    magma = next(a for a in la if a["id"] == "magma-erupts")
    assert magma["save_ability"] == "DEX"
    assert magma["save_dc"] == 15
    assert magma["damage"] == "6d6"
    assert magma["damage_type"] == "fire"
    assert magma["half_on_save"] is True
    assert magma["area"] == {"shape": "sphere", "size_ft": 20}


def test_tremor_is_a_non_damage_prone_effect():
    la = lair_actions_for_slug("adult-red-dragon")
    tremor = next(a for a in la if a["id"] == "tremor")
    assert tremor["save_ability"] == "DEX"
    assert tremor["save_dc"] == 15
    assert tremor["damage"] == ""
    assert tremor["effect"] == "prone"
    assert tremor["area"]["size_ft"] == 60


def test_volcanic_gases_is_a_con_save_poison():
    la = lair_actions_for_slug("adult-red-dragon")
    gas = next(a for a in la if a["id"] == "volcanic-gases")
    assert gas["save_ability"] == "CON"
    assert gas["save_dc"] == 13
    assert gas["effect"] == "poisoned"
    assert gas["damage"] == ""


def test_ancient_red_dragon_shares_the_volcanic_lair():
    """Red dragons of every age share the same volcanic lair (RAW: lair
    actions are tied to the lair, not the creature's age)."""
    adult = lair_actions_for_slug("adult-red-dragon")
    ancient = lair_actions_for_slug("ancient-red-dragon")
    assert [a["id"] for a in adult] == [a["id"] for a in ancient]
    assert adult == ancient


def test_unknown_slug_returns_empty_list():
    assert lair_actions_for_slug("bandit") == []
    assert lair_actions_for_slug("adult-red-dragon-nope") == []


def test_blank_or_non_string_slug_returns_empty_list():
    assert lair_actions_for_slug("") == []
    assert lair_actions_for_slug(None) == []
    assert lair_actions_for_slug(123) == []


def test_slug_lookup_is_case_and_whitespace_insensitive():
    assert len(lair_actions_for_slug("  Adult-Red-Dragon  ")) == 3


def test_returned_list_is_a_deep_copy():
    """Mutating the returned list / dicts must not corrupt the module
    source — the projection overlays fields onto these copies."""
    la = lair_actions_for_slug("adult-red-dragon")
    la[0]["save_dc"] = 999
    la.append({"id": "bogus"})
    fresh = lair_actions_for_slug("adult-red-dragon")
    assert len(fresh) == 3
    assert all(a["id"] != "bogus" for a in fresh)
    magma = next(a for a in fresh if a["id"] == "magma-erupts")
    assert magma["save_dc"] == 15
    # The module-level source is also untouched.
    assert LAIR_ACTIONS_BY_SLUG["adult-red-dragon"][0]["save_dc"] != 999


# ── chromatic backfill (v2.171.0) ────────────────────────────────────────────


def test_all_ten_chromatic_slugs_are_keyed():
    """Adult + ancient × black/blue/green/red/white = 10 lair slugs."""
    colors = ("black", "blue", "green", "red", "white")
    for color in colors:
        for age in ("adult", "ancient"):
            slug = f"{age}-{color}-dragon"
            assert slug in LAIR_ACTIONS_BY_SLUG, slug
            assert len(lair_actions_for_slug(slug)) == 3


def test_each_chromatic_color_shares_adult_and_ancient():
    for color in ("black", "blue", "green", "white"):
        adult = lair_actions_for_slug(f"adult-{color}-dragon")
        ancient = lair_actions_for_slug(f"ancient-{color}-dragon")
        assert adult == ancient
        assert [a["id"] for a in adult] == [a["id"] for a in ancient]


def test_black_swamp_lair_shape():
    la = lair_actions_for_slug("adult-black-dragon")
    ids = {a["id"] for a in la}
    assert ids == {"grasping-tide", "swarming-insects", "magical-darkness"}
    tide = next(a for a in la if a["id"] == "grasping-tide")
    assert tide["save_ability"] == "STR"
    assert tide["effect"] == "prone"
    assert tide["damage"] == ""
    insects = next(a for a in la if a["id"] == "swarming-insects")
    assert insects["save_ability"] == "CON"
    assert insects["damage"] == "3d6"
    assert insects["damage_type"] == "piercing"
    assert insects["half_on_save"] is True
    # Magical darkness has no engine effect — a descriptive entry.
    dark = next(a for a in la if a["id"] == "magical-darkness")
    assert dark["save_ability"] == ""
    assert dark["save_dc"] == 0
    assert dark["damage"] == ""
    assert dark["effect"] == ""


def test_blue_desert_lair_shape():
    la = lair_actions_for_slug("adult-blue-dragon")
    ids = {a["id"] for a in la}
    assert ids == {"ceiling-collapse", "sand-cloud", "lightning-arc"}
    sand = next(a for a in la if a["id"] == "sand-cloud")
    assert sand["save_ability"] == "CON"
    assert sand["effect"] == "blinded"
    assert sand["damage"] == ""
    arc = next(a for a in la if a["id"] == "lightning-arc")
    assert arc["damage"] == "3d6"
    assert arc["damage_type"] == "lightning"
    # Lightning arc deals full or nothing — no half on a success.
    assert arc["half_on_save"] is False


def test_green_forest_lair_shape():
    la = lair_actions_for_slug("adult-green-dragon")
    ids = {a["id"] for a in la}
    assert ids == {"grasping-roots", "wall-of-tangled-brush", "magical-fog"}
    roots = next(a for a in la if a["id"] == "grasping-roots")
    assert roots["save_ability"] == "STR"
    assert roots["effect"] == "restrained"
    fog = next(a for a in la if a["id"] == "magical-fog")
    assert fog["save_ability"] == "WIS"
    assert fog["effect"] == "charmed"
    wall = next(a for a in la if a["id"] == "wall-of-tangled-brush")
    assert wall["damage"] == "4d8"
    assert wall["half_on_save"] is True


def test_white_arctic_lair_shape():
    la = lair_actions_for_slug("adult-white-dragon")
    ids = {a["id"] for a in la}
    assert ids == {"freezing-fog", "jagged-ice", "ice-wall"}
    fog = next(a for a in la if a["id"] == "freezing-fog")
    assert fog["save_ability"] == "CON"
    assert fog["save_dc"] == 10
    assert fog["damage"] == "3d6"
    assert fog["damage_type"] == "cold"
    # The ranged ice-shard attack + opaque ice wall are descriptive.
    for did in ("jagged-ice", "ice-wall"):
        d = next(a for a in la if a["id"] == did)
        assert d["save_ability"] == ""
        assert d["damage"] == ""
        assert d["effect"] == ""


# ── lair_action_by_id ────────────────────────────────────────────────────────


def test_lair_action_by_id_resolves_known_action():
    a = lair_action_by_id("adult-red-dragon", "magma-erupts")
    assert a is not None
    assert a["name"] == "Magma Erupts"
    assert a["damage"] == "6d6"


def test_lair_action_by_id_unknown_id_returns_none():
    assert lair_action_by_id("adult-red-dragon", "no-such-action") is None


def test_lair_action_by_id_unknown_slug_returns_none():
    assert lair_action_by_id("bandit", "magma-erupts") is None


def test_lair_action_by_id_blank_id_returns_none():
    assert lair_action_by_id("adult-red-dragon", "") is None
    assert lair_action_by_id("adult-red-dragon", None) is None
