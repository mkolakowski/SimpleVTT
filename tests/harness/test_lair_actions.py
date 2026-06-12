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
