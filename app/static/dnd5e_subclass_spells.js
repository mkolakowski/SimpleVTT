/* Curated subclass-granted spell tables for D&D 5e (PHB).
 *
 * Each top-level key is the Open5e subclass slug (lowercased + hyphenated).
 * Entries describe spells that the subclass *grants* on top of the class's
 * normal spellcasting — these are "always prepared" and do NOT count
 * against the player's prepared/known limits.
 *
 * Shape:
 *   {
 *     class:    'cleric'                   // class slug this subclass belongs to
 *     feature:  'Domain Spells'            // feature name shown in the UI heading
 *     grants:   [ {classLvl, spellLvl, name}, … ]   // unconditional grants, OR…
 *     variants: { Arctic: [ … ], Coast: […] }       // … one set per choice (e.g. Druid land type)
 *     chooseLabel: 'Land Type'             // dropdown label when variants is used
 *
 *     // Optional: bonus-cantrip / bonus-spell *features* (e.g. Circle of the
 *     // Land's "Bonus Cantrip"). These render in the Feature Grants panel
 *     // immediately — they don't need Open5e subclass features to be cached
 *     // first, unlike the heuristic parser fallback.
 *     bonusFeatures: [
 *       { feature: 'Bonus Cantrip', classLvl: 2,
 *         grant: { type: 'choose', fromClass: 'druid', count: 1, spellLevel: 0 } },
 *       { feature: 'Bonus Cantrip', classLvl: 1,
 *         grant: { type: 'fixed', names: ['Light'], spellLevel: 0 } },
 *     ]
 *   }
 *
 * The renderer (window._renderSubclassSpellPanel in sheet_dnd5e.html) reads
 * window._SUBCLASS_SPELLS and builds the per-class panel that shows the +/−
 * buttons. Subclasses without a curated entry fall back to a hint nudging
 * the player to add granted spells manually via the Spell Browser.
 */
;(function () {
    // Helper: build a {classLvl, spellLvl, name} record. Stored explicitly so
    // the renderer doesn't have to derive spell-level from class-level (which
    // is irregular for paladin oaths and would break for half-/third-casters).
    const _ = (classLvl, spellLvl, name) => ({ classLvl, spellLvl, name });

    window._SUBCLASS_SPELLS = {
        // ── Cleric Domains (PHB) ─────────────────────────────────────────
        'knowledge': { class: 'cleric', feature: 'Domain Spells', grants: [
            _(1,1,'Command'),         _(1,1,'Identify'),
            _(3,2,'Augury'),          _(3,2,'Suggestion'),
            _(5,3,'Nondetection'),    _(5,3,'Speak with Dead'),
            _(7,4,'Arcane Eye'),      _(7,4,'Confusion'),
            _(9,5,'Legend Lore'),     _(9,5,'Scrying'),
        ] },
        'life': { class: 'cleric', feature: 'Domain Spells', grants: [
            _(1,1,'Bless'),               _(1,1,'Cure Wounds'),
            _(3,2,'Lesser Restoration'),  _(3,2,'Spiritual Weapon'),
            _(5,3,'Beacon of Hope'),      _(5,3,'Revivify'),
            _(7,4,'Death Ward'),          _(7,4,'Guardian of Faith'),
            _(9,5,'Mass Cure Wounds'),    _(9,5,'Raise Dead'),
        ] },
        'light': { class: 'cleric', feature: 'Domain Spells', grants: [
            _(1,1,'Burning Hands'),      _(1,1,'Faerie Fire'),
            _(3,2,'Flaming Sphere'),     _(3,2,'Scorching Ray'),
            _(5,3,'Daylight'),           _(5,3,'Fireball'),
            _(7,4,'Guardian of Faith'),  _(7,4,'Wall of Fire'),
            _(9,5,'Flame Strike'),       _(9,5,'Scrying'),
        ], bonusFeatures: [
            { feature: 'Bonus Cantrip', classLvl: 1,
              grant: { type: 'fixed', names: ['Light'], spellLevel: 0 } },
        ] },
        'nature': { class: 'cleric', feature: 'Domain Spells', grants: [
            _(1,1,'Animal Friendship'),  _(1,1,'Speak with Animals'),
            _(3,2,'Barkskin'),           _(3,2,'Spike Growth'),
            _(5,3,'Plant Growth'),       _(5,3,'Wind Wall'),
            _(7,4,'Dominate Beast'),     _(7,4,'Grasping Vine'),
            _(9,5,'Insect Plague'),      _(9,5,'Tree Stride'),
        ], bonusFeatures: [
            { feature: 'Acolyte of Nature', classLvl: 1,
              grant: { type: 'choose', fromClass: 'druid', count: 1, spellLevel: 0 } },
        ] },
        'tempest': { class: 'cleric', feature: 'Domain Spells', grants: [
            _(1,1,'Fog Cloud'),         _(1,1,'Thunderwave'),
            _(3,2,'Gust of Wind'),      _(3,2,'Shatter'),
            _(5,3,'Call Lightning'),    _(5,3,'Sleet Storm'),
            _(7,4,'Control Water'),     _(7,4,'Ice Storm'),
            _(9,5,'Destructive Wave'),  _(9,5,'Insect Plague'),
        ] },
        'trickery': { class: 'cleric', feature: 'Domain Spells', grants: [
            _(1,1,'Charm Person'),     _(1,1,'Disguise Self'),
            _(3,2,'Mirror Image'),     _(3,2,'Pass without Trace'),
            _(5,3,'Blink'),            _(5,3,'Dispel Magic'),
            _(7,4,'Dimension Door'),   _(7,4,'Polymorph'),
            _(9,5,'Dominate Person'),  _(9,5,'Modify Memory'),
        ] },
        'war': { class: 'cleric', feature: 'Domain Spells', grants: [
            _(1,1,'Divine Favor'),         _(1,1,'Shield of Faith'),
            _(3,2,'Magic Weapon'),         _(3,2,'Spiritual Weapon'),
            _(5,3,"Crusader's Mantle"),    _(5,3,'Spirit Guardians'),
            _(7,4,'Freedom of Movement'),  _(7,4,'Stoneskin'),
            _(9,5,'Flame Strike'),         _(9,5,'Hold Monster'),
        ] },

        // ── Cleric Domains (XGtE) ────────────────────────────────────────
        'forge': { class: 'cleric', feature: 'Domain Spells', grants: [
            _(1,1,'Identify'),             _(1,1,'Searing Smite'),
            _(3,2,'Heat Metal'),           _(3,2,'Magic Weapon'),
            _(5,3,'Elemental Weapon'),     _(5,3,'Protection from Energy'),
            _(7,4,'Fabricate'),            _(7,4,'Wall of Fire'),
            _(9,5,'Animate Objects'),      _(9,5,'Creation'),
        ] },
        'grave': { class: 'cleric', feature: 'Domain Spells', grants: [
            _(1,1,'Bane'),                 _(1,1,'False Life'),
            _(3,2,'Gentle Repose'),        _(3,2,'Ray of Enfeeblement'),
            _(5,3,'Revivify'),             _(5,3,'Vampiric Touch'),
            _(7,4,'Blight'),               _(7,4,'Death Ward'),
            _(9,5,'Antilife Shell'),       _(9,5,'Raise Dead'),
        ] },

        // ── Cleric Domains (TCoE) ────────────────────────────────────────
        'order': { class: 'cleric', feature: 'Domain Spells', grants: [
            _(1,1,'Command'),              _(1,1,'Heroism'),
            _(3,2,'Hold Person'),          _(3,2,'Zone of Truth'),
            _(5,3,'Mass Healing Word'),    _(5,3,'Slow'),
            _(7,4,'Compulsion'),           _(7,4,'Locate Creature'),
            _(9,5,'Commune'),              _(9,5,'Dominate Person'),
        ] },
        'peace': { class: 'cleric', feature: 'Domain Spells', grants: [
            _(1,1,'Heroism'),              _(1,1,'Sanctuary'),
            _(3,2,'Aid'),                  _(3,2,'Warding Bond'),
            _(5,3,'Beacon of Hope'),       _(5,3,'Sending'),
            _(7,4,'Aura of Purity'),       _(7,4,"Otiluke's Resilient Sphere"),
            _(9,5,'Greater Restoration'),  _(9,5,"Rary's Telepathic Bond"),
        ] },
        'twilight': { class: 'cleric', feature: 'Domain Spells', grants: [
            _(1,1,'Faerie Fire'),          _(1,1,'Sleep'),
            _(3,2,'Moonbeam'),             _(3,2,'See Invisibility'),
            _(5,3,'Aura of Vitality'),     _(5,3,"Leomund's Tiny Hut"),
            _(7,4,'Aura of Life'),         _(7,4,'Greater Invisibility'),
            _(9,5,'Circle of Power'),      _(9,5,'Mislead'),
        ] },

        // ── Druid Circles (PHB) ──────────────────────────────────────────
        // Circle of the Land has terrain variants — pick one Land Type and
        // the corresponding spell list is granted on top of the normal druid
        // spell list. Spell levels here use the *class level* the spell is
        // unlocked at; the spell's own level is encoded explicitly.
        'circle-of-the-land': {
            class: 'druid', feature: 'Circle Spells', chooseLabel: 'Land Type',
            bonusFeatures: [
                { feature: 'Bonus Cantrip', classLvl: 2,
                  grant: { type: 'choose', fromClass: 'druid', count: 1, spellLevel: 0 } },
            ],
            variants: {
                'Arctic':    [_(3,2,'Hold Person'),         _(3,2,'Spike Growth'),
                              _(5,3,'Sleet Storm'),         _(5,3,'Slow'),
                              _(7,4,'Freedom of Movement'), _(7,4,'Ice Storm'),
                              _(9,5,'Commune with Nature'), _(9,5,'Cone of Cold')],
                'Coast':     [_(3,2,'Mirror Image'),        _(3,2,'Misty Step'),
                              _(5,3,'Water Breathing'),     _(5,3,'Water Walk'),
                              _(7,4,'Control Water'),       _(7,4,'Freedom of Movement'),
                              _(9,5,'Conjure Elemental'),   _(9,5,'Scrying')],
                'Desert':    [_(3,2,'Blur'),                _(3,2,'Silence'),
                              _(5,3,'Create Food and Water'), _(5,3,'Protection from Energy'),
                              _(7,4,'Blight'),              _(7,4,'Hallucinatory Terrain'),
                              _(9,5,'Insect Plague'),       _(9,5,'Wall of Stone')],
                'Forest':    [_(3,2,'Barkskin'),            _(3,2,'Spider Climb'),
                              _(5,3,'Call Lightning'),      _(5,3,'Plant Growth'),
                              _(7,4,'Divination'),          _(7,4,'Freedom of Movement'),
                              _(9,5,'Commune with Nature'), _(9,5,'Tree Stride')],
                'Grassland': [_(3,2,'Invisibility'),        _(3,2,'Pass without Trace'),
                              _(5,3,'Daylight'),            _(5,3,'Haste'),
                              _(7,4,'Divination'),          _(7,4,'Freedom of Movement'),
                              _(9,5,'Dream'),               _(9,5,'Insect Plague')],
                'Mountain':  [_(3,2,'Spider Climb'),        _(3,2,'Spike Growth'),
                              _(5,3,'Lightning Bolt'),      _(5,3,'Meld into Stone'),
                              _(7,4,'Stone Shape'),         _(7,4,'Stoneskin'),
                              _(9,5,'Passwall'),            _(9,5,'Wall of Stone')],
                'Swamp':     [_(3,2,'Darkness'),            _(3,2,"Melf's Acid Arrow"),
                              _(5,3,'Water Walk'),          _(5,3,'Stinking Cloud'),
                              _(7,4,'Freedom of Movement'), _(7,4,'Locate Creature'),
                              _(9,5,'Insect Plague'),       _(9,5,'Scrying')],
                'Underdark': [_(3,2,'Spider Climb'),        _(3,2,'Web'),
                              _(5,3,'Gaseous Form'),        _(5,3,'Stinking Cloud'),
                              _(7,4,'Greater Invisibility'),_(7,4,'Stone Shape'),
                              _(9,5,'Cloudkill'),           _(9,5,'Insect Plague')],
            },
        },

        // ── Druid Circles (TCoE) ─────────────────────────────────────────
        'circle-of-spores': { class: 'druid', feature: 'Circle Spells', grants: [
            _(3,2,'Blindness/Deafness'),   _(3,2,'Gentle Repose'),
            _(5,3,'Animate Dead'),         _(5,3,'Gaseous Form'),
            _(7,4,'Blight'),               _(7,4,'Confusion'),
            _(9,5,'Cloudkill'),            _(9,5,'Contagion'),
        ] },
        'circle-of-wildfire': { class: 'druid', feature: 'Circle Spells', grants: [
            _(3,2,'Burning Hands'),        _(3,2,'Cure Wounds'),
            _(5,3,'Flaming Sphere'),       _(5,3,'Scorching Ray'),
            _(7,4,'Plant Growth'),         _(7,4,'Revivify'),
            _(9,5,'Aura of Life'),         _(9,5,'Flame Strike'),
        ] },
        // Circle of Stars' "Star Map" feature hands you Guidance + Guiding
        // Bolt at druid level 2, both always known.
        'circle-of-stars': { class: 'druid', feature: 'Star Map', grants: [
            _(2,0,'Guidance'),
            _(2,1,'Guiding Bolt'),
        ] },

        // ── Paladin Oaths (PHB) ──────────────────────────────────────────
        'oath-of-devotion': { class: 'paladin', feature: 'Oath Spells', grants: [
            _(3,1,'Protection from Evil and Good'), _(3,1,'Sanctuary'),
            _(5,2,'Lesser Restoration'),            _(5,2,'Zone of Truth'),
            _(9,3,'Beacon of Hope'),                _(9,3,'Dispel Magic'),
            _(13,4,'Freedom of Movement'),          _(13,4,'Guardian of Faith'),
            _(17,5,'Commune'),                      _(17,5,'Flame Strike'),
        ] },
        'oath-of-the-ancients': { class: 'paladin', feature: 'Oath Spells', grants: [
            _(3,1,'Ensnaring Strike'),     _(3,1,'Speak with Animals'),
            _(5,2,'Moonbeam'),             _(5,2,'Misty Step'),
            _(9,3,'Plant Growth'),         _(9,3,'Protection from Energy'),
            _(13,4,'Ice Storm'),           _(13,4,'Stoneskin'),
            _(17,5,'Commune with Nature'), _(17,5,'Tree Stride'),
        ] },
        'oath-of-vengeance': { class: 'paladin', feature: 'Oath Spells', grants: [
            _(3,1,'Bane'),               _(3,1,"Hunter's Mark"),
            _(5,2,'Hold Person'),        _(5,2,'Misty Step'),
            _(9,3,'Haste'),              _(9,3,'Protection from Energy'),
            _(13,4,'Banishment'),        _(13,4,'Dimension Door'),
            _(17,5,'Hold Monster'),      _(17,5,'Scrying'),
        ] },

        // ── Paladin Oaths (DMG) ──────────────────────────────────────────
        'oathbreaker': { class: 'paladin', feature: 'Oathbreaker Spells', grants: [
            _(3,1,'Hellish Rebuke'),     _(3,1,'Inflict Wounds'),
            _(5,2,'Crown of Madness'),   _(5,2,'Darkness'),
            _(9,3,'Animate Dead'),       _(9,3,'Bestow Curse'),
            _(13,4,'Blight'),            _(13,4,'Confusion'),
            _(17,5,'Contagion'),         _(17,5,'Dominate Person'),
        ] },

        // ── Paladin Oaths (XGtE) ─────────────────────────────────────────
        'oath-of-conquest': { class: 'paladin', feature: 'Oath Spells', grants: [
            _(3,1,'Armor of Agathys'),   _(3,1,'Command'),
            _(5,2,'Hold Person'),        _(5,2,'Spiritual Weapon'),
            _(9,3,'Bestow Curse'),       _(9,3,'Fear'),
            _(13,4,'Dominate Beast'),    _(13,4,'Stoneskin'),
            _(17,5,'Cloudkill'),         _(17,5,'Dominate Person'),
        ] },
        'oath-of-redemption': { class: 'paladin', feature: 'Oath Spells', grants: [
            _(3,1,'Sanctuary'),                  _(3,1,'Sleep'),
            _(5,2,'Hold Person'),                _(5,2,'Ray of Enfeeblement'),
            _(9,3,'Counterspell'),               _(9,3,'Hypnotic Pattern'),
            _(13,4,"Otiluke's Resilient Sphere"),_(13,4,'Stoneskin'),
            _(17,5,'Hold Monster'),              _(17,5,'Wall of Force'),
        ] },

        // ── Paladin Oaths (TCoE) ─────────────────────────────────────────
        'oath-of-glory': { class: 'paladin', feature: 'Oath Spells', grants: [
            _(3,1,'Guiding Bolt'),       _(3,1,'Heroism'),
            _(5,2,'Enhance Ability'),    _(5,2,'Magic Weapon'),
            _(9,3,'Haste'),              _(9,3,'Protection from Energy'),
            _(13,4,'Compulsion'),        _(13,4,'Freedom of Movement'),
            _(17,5,'Flame Strike'),      _(17,5,'Greater Restoration'),
        ] },
        'oath-of-the-watchers': { class: 'paladin', feature: 'Oath Spells', grants: [
            _(3,1,'Alarm'),              _(3,1,'Detect Magic'),
            _(5,2,'Moonbeam'),           _(5,2,'See Invisibility'),
            _(9,3,'Counterspell'),       _(9,3,'Nondetection'),
            _(13,4,'Aura of Purity'),    _(13,4,'Banishment'),
            _(17,5,'Hold Monster'),      _(17,5,'Scrying'),
        ] },

        // ── Sorcerer Subclasses (TCoE) ───────────────────────────────────
        // Tasha's introduced an "always known, doesn't count against your
        // sorcerer spells known" mechanic. These are the curated grants for
        // the two Tasha's origins that have them. Mind Sliver is the cantrip
        // half of Aberrant Mind's level-1 grant.
        'aberrant-mind': { class: 'sorcerer', feature: 'Psionic Spells', grants: [
            _(1,0,'Mind Sliver'),
            _(1,1,'Arms of Hadar'),                  _(1,1,'Dissonant Whispers'),
            _(3,2,'Calm Emotions'),                  _(3,2,'Detect Thoughts'),
            _(5,3,'Hunger of Hadar'),                _(5,3,'Sending'),
            _(7,4,"Evard's Black Tentacles"),        _(7,4,'Summon Aberration'),
            _(9,5,"Rary's Telepathic Bond"),         _(9,5,'Telekinesis'),
        ] },
        'clockwork-soul': { class: 'sorcerer', feature: 'Clockwork Magic', grants: [
            _(1,1,'Alarm'),                          _(1,1,'Protection from Evil and Good'),
            _(3,2,'Aid'),                            _(3,2,'Lesser Restoration'),
            _(5,3,'Dispel Magic'),                   _(5,3,'Protection from Energy'),
            _(7,4,'Freedom of Movement'),            _(7,4,'Summon Construct'),
            _(9,5,'Greater Restoration'),            _(9,5,'Wall of Force'),
        ] },
    };
})();
