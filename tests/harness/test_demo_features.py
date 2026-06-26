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
    s = _apply("Fighter", "Battle Master", "Mountain Dwarf")  # neither SRD
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
