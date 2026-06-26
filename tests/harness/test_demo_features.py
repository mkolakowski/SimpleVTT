"""v2.653.0 — demo PCs backfill subclass features + race traits from the
shipped SRD content at seed time, via app/demo_features.apply_srd_features
(wired into demo_seed.build_dnd5e_sheet + the Vault PC seed loop).

Tests the helper directly (it only needs the offline `local_features`
SRD layer — no DB), so it runs host-side AND in CI. SRD-covered
class/subclass/race combos get their structured `[{name,level,desc}]`
lists; non-SRD combos are left empty (those backfill from live Open5e
when a sheet is opened, per the design).
"""
from app.demo_features import apply_srd_features


def _apply(klass, subclass, race):
    s = {"class": klass, "subclass": subclass, "race": race,
         "subclass_features": [], "race_trait_items": [], "class_features": []}
    return apply_srd_features(s)


def _apply_lvl(klass, subclass, race, level):
    s = {"class": klass, "subclass": subclass, "race": race, "level": level,
         "subclass_features": [], "race_trait_items": [], "class_features": []}
    return apply_srd_features(s)


def test_srd_pc_gets_subclass_and_race_features():
    s = _apply("Fighter", "Champion", "Human")  # both SRD 5.1
    assert s.get("subclass_features"), "expected SRD subclass features"
    assert all(f.get("name") for f in s["subclass_features"])
    assert s.get("subclass_name"), "subclass_name backfilled"
    assert s.get("race_trait_items"), "expected SRD race traits"


def test_variant_human_alias_resolves_to_human():
    s = _apply("Fighter", "Champion", "Variant Human")
    assert s.get("race_trait_items"), "variant-human should alias to human"


def test_per_field_partial_coverage():
    # Thief (SRD subclass) + base Halfling (NOT shipped — only lightfoot).
    s = _apply("Rogue", "Thief", "Halfling")
    assert s.get("subclass_features"), "Thief is SRD → subclass fills"
    assert not (s.get("race_trait_items") or []), "base Halfling not in SRD"


def test_non_srd_combo_left_empty():
    # Firbolg is genuinely non-SRD (homebrew tier only); Battle Master too.
    # (Mountain Dwarf moved into the SRD tier in v2.654.0, so it no longer
    # works as a "non-SRD race" example.)
    s = _apply("Fighter", "Battle Master", "Firbolg")
    assert not (s.get("subclass_features") or [])
    assert not (s.get("race_trait_items") or [])


def test_does_not_overwrite_existing_features():
    s = {"class": "Fighter", "subclass": "Champion", "race": "Human",
         "subclass_features": [{"name": "Curated", "desc": "x"}],
         "race_trait_items": []}
    apply_srd_features(s)
    assert s["subclass_features"] == [{"name": "Curated", "desc": "x"}], \
        "must not overwrite a pre-set subclass_features list"
    assert s.get("race_trait_items"), "but still fills the empty race field"


def test_class_features_parsed_and_level_filtered():
    # Every SRD class gets class features parsed from the markdown blob,
    # filtered to the PC's level.
    s = _apply_lvl("Fighter", "Champion", "Human", 9)
    names = [(f["name"], f["level"]) for f in s.get("class_features") or []]
    assert names, "expected parsed class features"
    assert ("Indomitable", 9) in names, "Lv 9 feature should appear at L9"
    s3 = _apply_lvl("Fighter", "Battle Master", "Mountain Dwarf", 3)
    # Even a non-SRD subclass/race PC gets class features (Fighter is SRD).
    cf3 = [f["name"] for f in s3.get("class_features") or []]
    assert "Martial Archetype" in cf3
    assert "Indomitable" not in cf3, "Lv 9 feature must be filtered out at L3"


def test_class_features_not_overwritten():
    s = {"class": "Rogue", "subclass": "Thief", "race": "Human", "level": 5,
         "class_features": [{"key": "cunning-action", "name": "Cunning Action",
                             "desc": "curated"}]}
    apply_srd_features(s)
    assert s["class_features"] == [{"key": "cunning-action",
                                    "name": "Cunning Action", "desc": "curated"}], \
        "must not overwrite a curated class_features list"


def test_newly_shipped_srd_subraces_resolve():
    # v2.654.0 — the 5 SRD 5.1 subraces missing from the shipped tier
    # (Mountain Dwarf, Wood Elf, Forest Gnome, Stout Halfling, Drow) now
    # ship, so demo PCs on them seed race traits offline.
    from app import local_features as lf
    expected = {
        "mountain-dwarf": "Dwarven Armor Training",
        "wood-elf": "Mask of the Wild",
        "forest-gnome": "Natural Illusionist",
        "stout-halfling": "Stout Resilience",
        "drow": "Drow Magic",
    }
    for slug, signature in expected.items():
        rec, src = lf.resolve_race(slug, scopes=["global"])
        assert rec, f"{slug} should ship in the SRD tier"
        assert src == "local-srd", f"{slug} must resolve from shipped SRD, got {src}"
        names = [t.get("name") for t in rec.get("traits") or []]
        assert signature in names, f"{slug} missing subrace trait {signature!r}: {names}"


def test_wood_elf_demo_pc_now_seeds_race_traits():
    # Mira / Kael / Nyx / Vesh are Wood Elf — previously empty, now filled.
    s = _apply("Druid", "Circle of the Moon", "Wood Elf")
    names = [t.get("name") for t in s.get("race_trait_items") or []]
    assert "Fleet of Foot" in names and "Mask of the Wild" in names, names


def test_srd_5_2_species_resolve():
    # v2.655.0 — Goliath + Aasimar ship from SRD 5.2 (2024 rules, CC BY 4.0),
    # the two demo non-SRD races that became freely distributable.
    from app import local_features as lf
    expected = {
        "goliath": "Giant Ancestry",
        "aasimar": "Celestial Revelation",
    }
    for slug, signature in expected.items():
        rec, src = lf.resolve_race(slug, scopes=["global"])
        assert rec, f"{slug} should ship in the SRD tier"
        assert src == "local-srd"
        assert "5.2" in (rec.get("_attribution") or ""), \
            f"{slug} must cite SRD 5.2"
        names = [t.get("name") for t in rec.get("traits") or []]
        assert signature in names, f"{slug} missing {signature!r}: {names}"


def test_goliath_demo_pc_now_seeds_race_traits():
    # Bryn / High Cleric Doran are Goliath; Aurelia is Aasimar.
    s = _apply("Fighter", "Champion", "Goliath")
    names = [t.get("name") for t in s.get("race_trait_items") or []]
    assert "Giant Ancestry" in names and "Powerful Build" in names, names
