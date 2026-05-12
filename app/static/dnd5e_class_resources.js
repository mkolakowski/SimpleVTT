/* Curated D&D 5e class / subclass *resource* table.
 *
 * "Resources" are limited-use features that the player needs to track
 * across short / long rests: Rage, Channel Divinity, Ki, Action Surge,
 * Bardic Inspiration, Superiority Dice, Lay on Hands, Portent, …
 *
 * Each recipe describes ONE feature. The Class Resources panel
 * (in sheet_dnd5e.html) reads this table, looks up which recipes apply
 * to each entry on sheet["classes"], and seeds sheet["resources"]
 * accordingly. Players can also add purely manual resources from the UI;
 * those carry ``manual: true`` and are never overwritten by this table.
 *
 * Recipe shape:
 *   {
 *     key:       'action-surge',          // stable id, unique per character
 *     name:      'Action Surge',          // shown in the UI
 *     class:     'fighter',               // class slug it belongs to
 *     subclass:  'battle-master' | null,  // null for class-wide features
 *     minLevel:  2,                       // class level required
 *     // max uses, as a function of (classLevel, abilityMods, profBonus)
 *     // abilityMods is {STR, DEX, CON, INT, WIS, CHA} (integer modifiers)
 *     max:       (lvl, mods, prof) => lvl >= 17 ? 2 : 1,
 *     // when uses refill: 'short' / 'long' / 'none', or a function
 *     // of classLevel returning one of those strings.
 *     reset:     'short',
 *     desc:      'Take an additional action on your turn.',
 *   }
 *
 * Notes:
 * - We deliberately don't model spell slots here — they have their own
 *   pip framework in sheet_dnd5e.html / sheet.js.
 * - Subclass-specific Channel Divinity *options* (Turn Undead, Sacred
 *   Weapon, …) share the class-wide Channel Divinity counter. We expose
 *   ONE recipe for the counter; the options live in the feature
 *   description so players know what to spend it on.
 */
;(function () {
    const _max = (fn) => (typeof fn === 'function' ? fn : () => fn);

    window._CLASS_RESOURCES = [

        // ── Barbarian ────────────────────────────────────────────────
        {
            key: 'rage', name: 'Rage', class: 'barbarian', subclass: null,
            minLevel: 1,
            max: (lvl) => lvl >= 20 ? 99 : lvl >= 17 ? 6 : lvl >= 12 ? 5 : lvl >= 6 ? 4 : lvl >= 3 ? 3 : 2,
            reset: 'long',
            desc: 'Enter a rage for damage resistance, advantage on STR checks/saves, and +rage damage on STR melee attacks. Lasts 1 minute; 3 rounds without attacking/being hit ends it.',
        },

        // ── Bard ─────────────────────────────────────────────────────
        {
            key: 'bardic-inspiration', name: 'Bardic Inspiration', class: 'bard', subclass: null,
            minLevel: 1,
            max: (lvl, mods) => Math.max(1, mods.CHA || 0),
            reset: (lvl) => lvl >= 5 ? 'short' : 'long',
            desc: 'Bonus action: give an ally a Bardic Inspiration die (d6/d8/d10/d12 at lv1/5/10/15). They roll & add it to one ability check, attack, or save in the next 10 min.',
        },
        {
            key: 'song-of-rest', name: 'Song of Rest', class: 'bard', subclass: null,
            minLevel: 2, max: 0, reset: 'none',
            desc: 'During a short rest, allies who spend hit dice get extra healing (1d6 / 1d8 / 1d10 / 1d12 at lv2/9/13/17).',
        },

        // ── Cleric ───────────────────────────────────────────────────
        {
            key: 'channel-divinity', name: 'Channel Divinity', class: 'cleric', subclass: null,
            minLevel: 2,
            max: (lvl) => lvl >= 18 ? 3 : lvl >= 6 ? 2 : 1,
            reset: 'short',
            desc: 'Use a domain-granted effect (Turn Undead, Preserve Life, Sacred Weapon, etc.).',
        },

        // ── Druid ────────────────────────────────────────────────────
        {
            key: 'wild-shape', name: 'Wild Shape', class: 'druid', subclass: null,
            minLevel: 2, max: () => 2, reset: 'short',
            desc: 'Transform into a beast you have seen, with CR limits by level. Moon druids start at CR 1 at lv2.',
        },

        // ── Fighter ──────────────────────────────────────────────────
        {
            key: 'second-wind', name: 'Second Wind', class: 'fighter', subclass: null,
            minLevel: 1, max: () => 1, reset: 'short',
            desc: 'Bonus action: regain 1d10 + fighter level HP.',
        },
        {
            key: 'action-surge', name: 'Action Surge', class: 'fighter', subclass: null,
            minLevel: 2,
            max: (lvl) => lvl >= 17 ? 2 : 1,
            reset: 'short',
            desc: 'Take one additional action on your turn.',
        },
        {
            key: 'indomitable', name: 'Indomitable', class: 'fighter', subclass: null,
            minLevel: 9,
            max: (lvl) => lvl >= 17 ? 3 : lvl >= 13 ? 2 : 1,
            reset: 'long',
            desc: 'Reroll a failed saving throw; must use the new roll.',
        },

        // ── Monk ─────────────────────────────────────────────────────
        {
            key: 'ki', name: 'Ki Points', class: 'monk', subclass: null,
            minLevel: 2,
            max: (lvl) => lvl,
            reset: 'short',
            desc: 'Spend to fuel Flurry of Blows, Patient Defense, Step of the Wind, and subclass abilities.',
        },

        // ── Paladin ──────────────────────────────────────────────────
        {
            key: 'lay-on-hands', name: 'Lay on Hands (HP pool)', class: 'paladin', subclass: null,
            minLevel: 1,
            max: (lvl) => lvl * 5,
            reset: 'long',
            desc: 'Touch a creature to restore HP from the pool, or spend 5 to cure disease/poison.',
        },
        {
            key: 'divine-sense', name: 'Divine Sense', class: 'paladin', subclass: null,
            minLevel: 1,
            max: (lvl, mods) => 1 + Math.max(0, mods.CHA || 0),
            reset: 'long',
            desc: 'Action: detect celestials, fiends, and undead within 60 ft until the end of your next turn.',
        },
        {
            key: 'channel-divinity', name: 'Channel Divinity', class: 'paladin', subclass: null,
            minLevel: 3, max: () => 1, reset: 'short',
            desc: 'Use an oath-granted effect (Sacred Weapon, Turn the Unholy, Nature\'s Wrath, …).',
        },

        // ── Ranger ───────────────────────────────────────────────────
        // Core PHB ranger has no countable class resource. Subclass / Tasha
        // optional class features add some — left to the manual-add flow.

        // ── Sorcerer ─────────────────────────────────────────────────
        {
            key: 'sorcery-points', name: 'Sorcery Points', class: 'sorcerer', subclass: null,
            minLevel: 2,
            max: (lvl) => lvl,
            reset: 'long',
            desc: 'Spend on Metamagic, or convert to/from spell slots via Font of Magic.',
        },

        // ── Warlock — pact magic uses the spell-slot framework already ──

        // ── Wizard ───────────────────────────────────────────────────
        {
            key: 'arcane-recovery', name: 'Arcane Recovery', class: 'wizard', subclass: null,
            minLevel: 1, max: () => 1, reset: 'long',
            desc: 'Once per long rest, on a short rest, recover spell slots totalling ⌈wizard level / 2⌉.',
        },

        // ── Subclass-specific ────────────────────────────────────────

        // Fighter — Battle Master Superiority Dice
        {
            key: 'superiority-dice', name: 'Superiority Dice',
            class: 'fighter', subclass: 'battle-master',
            minLevel: 3,
            max: (lvl) => lvl >= 15 ? 6 : lvl >= 7 ? 5 : 4,
            reset: 'short',
            desc: 'Die size: d8 (lv3) → d10 (lv10) → d12 (lv18). Spend on maneuvers like Riposte, Trip, Disarming Attack.',
        },

        // Wizard — Divination School Portent
        {
            key: 'portent', name: 'Portent Dice',
            class: 'wizard', subclass: 'divination',
            minLevel: 2,
            max: (lvl) => lvl >= 14 ? 3 : 2,
            reset: 'long',
            desc: 'Roll two d20s after a long rest; record them. Replace any attack roll, save, or ability check you can see with one of those rolls.',
        },

        // Sorcerer — Wild Magic Tides of Chaos
        {
            key: 'tides-of-chaos', name: 'Tides of Chaos',
            class: 'sorcerer', subclass: 'wild-magic',
            minLevel: 1, max: () => 1, reset: 'long',
            desc: 'Gain advantage on one attack roll, ability check, or save. GM may cause a Wild Magic Surge before your next rest to recharge it early.',
        },

        // Cleric — Tempest Wrath of the Storm  (PHB; superseded in updated SRD,
        // kept here because most groups still use the PHB version)
        {
            key: 'wrath-of-the-storm', name: 'Wrath of the Storm',
            class: 'cleric', subclass: 'tempest',
            minLevel: 1,
            max: (lvl, mods) => Math.max(1, mods.WIS || 0),
            reset: 'long',
            desc: 'Reaction when hit in melee: target makes a DEX save or takes 2d8 lightning/thunder (half on success). Damage scales at lv6/14/18.',
        },

        // Cleric — War Priest
        {
            key: 'war-priest', name: 'War Priest',
            class: 'cleric', subclass: 'war',
            minLevel: 1,
            max: (lvl, mods) => Math.max(1, mods.WIS || 0),
            reset: 'long',
            desc: 'Bonus action: make one weapon attack after using the Attack action.',
        },

        // Druid — Circle of the Land Natural Recovery
        {
            key: 'natural-recovery', name: 'Natural Recovery',
            class: 'druid', subclass: 'land',
            minLevel: 2, max: () => 1, reset: 'long',
            desc: 'On a short rest, recover spell slots totalling up to ⌈druid level / 2⌉ (no slot above 5th).',
        },

        // Paladin — Cleansing Touch (all oaths)
        {
            key: 'cleansing-touch', name: 'Cleansing Touch', class: 'paladin', subclass: null,
            minLevel: 14,
            max: (lvl, mods) => Math.max(1, mods.CHA || 0),
            reset: 'long',
            desc: 'Action: end one spell on yourself or a willing creature you touch.',
        },

        // Rogue — Stroke of Luck (capstone)
        {
            key: 'stroke-of-luck', name: 'Stroke of Luck', class: 'rogue', subclass: null,
            minLevel: 20, max: () => 1, reset: 'short',
            desc: 'Turn a missed attack into a hit, or a failed ability check into a 20.',
        },
    ];

    // Helper: recipe → resource object ready for sheet["resources"].
    // entry is one element of sheet["classes"] (has .class, .subclass, .level).
    // mods is a {STR, DEX, CON, INT, WIS, CHA} integer-modifier map.
    // prof is the proficiency bonus.
    window._buildResourceFromRecipe = function (recipe, entry, mods, prof) {
        const lvl = Math.max(1, parseInt(entry.level, 10) || 1);
        const mxFn = _max(recipe.max);
        const max = Math.max(0, parseInt(mxFn(lvl, mods || {}, prof || 2), 10) || 0);
        const reset = typeof recipe.reset === 'function'
            ? recipe.reset(lvl)
            : (recipe.reset || 'long');
        const subLabel = (entry.subclass || '').trim();
        const source = subLabel
            ? `${entry.class} (${subLabel}) Lv ${lvl}`
            : `${entry.class} Lv ${lvl}`;
        return {
            key: recipe.key,
            name: recipe.name,
            current: max,           // start full
            max: max,
            reset: reset,
            source: source,
            class_slug: (entry.class || '').trim().toLowerCase(),
            subclass_slug: recipe.subclass || '',
            desc: recipe.desc || '',
            manual: false,
        };
    };

    // Find every recipe that applies to a given class-roster entry.
    //
    // Subclass matching is forgiving — Open5e uses slugs like ``tempest``
    // (without the "-domain" suffix) for clerics but ``battle-master``,
    // ``wild-magic`` for fighter/sorcerer, while the display name on the
    // sheet may be "Tempest Domain", "Tempest", or just "Tempest". We
    // accept a match if the recipe's subclass slug is contained in any
    // of: the explicit ``_subclass_slug`` cache, the slugified display
    // name, or the slugified display name with "-domain"/"-school" etc.
    // stripped off.
    window._findRecipesForEntry = function (entry) {
        if (!entry || !entry.class) return [];
        const cslug = String(entry.class || '').trim().toLowerCase();
        const lvl = Math.max(1, parseInt(entry.level, 10) || 1);
        const slugify = (s) => String(s || '')
            .trim().toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
        const candidates = new Set();
        if (entry._subclass_slug) candidates.add(slugify(entry._subclass_slug));
        if (entry.subclass) {
            const s = slugify(entry.subclass);
            candidates.add(s);
            // Strip common trailing nouns so "tempest-domain" matches "tempest"
            candidates.add(s.replace(/-(?:domain|school|circle|college|oath|of-the-?|way-of-the-?|path-of-the-?)$/i, ''));
            candidates.add(s.replace(/^(?:circle-of-the-?|college-of-?|oath-of-?|path-of-the-?|way-of-the-?|school-of-?)/i, ''));
        }
        return (window._CLASS_RESOURCES || []).filter(r => {
            if (r.class !== cslug) return false;
            if ((r.minLevel || 1) > lvl) return false;
            if (r.subclass) return candidates.has(r.subclass);
            return true;
        });
    };
})();
