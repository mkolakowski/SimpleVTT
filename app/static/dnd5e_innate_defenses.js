/* Curated D&D 5e race / class / subclass defense table.
 *
 * Maps Open5e slugs to "innate" defenses that apply automatically — the
 * Defenses fieldset's chip toggles read this on render and lock any
 * chip whose label matches a grant from the player's current race or
 * class roster.
 *
 * Coverage is intentionally conservative: only ALWAYS-ON grants from
 * the PHB / official sources I'm confident about. Conditional defenses
 * (Rage's BPS resistance, Aura of Protection's save bonus, etc.) are
 * deliberately excluded because they're not really "auto-applied" in
 * the sheet-state sense — the player tracks them while active.
 *
 * Add entries by appending to the appropriate map; the picker reloads
 * on race / multiclass change so new entries apply immediately.
 *
 * Notable known gaps:
 *   - Dragonborn (resistance depends on ancestry, but the sheet has no
 *     separate ancestry field — skipped to avoid wrong-ancestry chips).
 *   - Sorcerer Draconic Bloodline Elemental Affinity (same reason as
 *     Dragonborn — depends on a Draconic Ancestry choice that isn't
 *     captured as structured data).
 *
 * Shape — each race entry is a single grant; each class/subclass entry
 * is either a single grant or an array of level-tiered grants:
 *
 *   {
 *     damage_resistances:     ['Fire'],
 *     damage_immunities:      ['Poison'],
 *     damage_vulnerabilities: [],
 *     condition_immunities:   ['Poisoned'],
 *     source: 'Tiefling',     // shown in the chip's hover tooltip
 *   }
 *
 * Or for class/subclass tiers:
 *   [ { minLevel: 10, source: 'Purity of Body (Monk 10)',
 *       grants: { damage_immunities: ['Poison'], condition_immunities: ['Poisoned'] } } ]
 */
;(function () {
    // Fey Ancestry note (applies to all Elf subraces below).
    // RAW: "You have advantage on saving throws against being charmed,
    // and magic can't put you to sleep." That's a save-side advantage,
    // not a flat Charmed condition immunity. We model it as a Charmed
    // condition-immunity chip because (a) the chip is a visible
    // reminder of the trait, and (b) many tables play Fey Ancestry as
    // effective charm immunity. The tooltip on the chip names the
    // trait so players whose tables play it stricter can read the chip
    // as "advantage" instead of full immunity. Sleep-magic immunity
    // isn't in the standard condition list and is omitted.
    const _FEY_ANCESTRY = {
        condition_immunities: ['Charmed'],
        source: 'Fey Ancestry (Elf) — advantage on charm saves, can\'t be magically slept',
    };

    const RACE = {
        // Tieflings — Infernal Legacy: fire resistance
        'tiefling':            { damage_resistances: ['Fire'], source: 'Tiefling — Infernal Legacy' },
        // Dwarves — Dwarven Resilience: resistance to poison damage + advantage on poison saves
        'dwarf':               { damage_resistances: ['Poison'], source: 'Dwarven Resilience' },
        'hill-dwarf':          { damage_resistances: ['Poison'], source: 'Dwarven Resilience' },
        'mountain-dwarf':      { damage_resistances: ['Poison'], source: 'Dwarven Resilience' },
        'duergar':             { damage_resistances: ['Poison'], source: 'Duergar Resilience' },
        // Aasimar — Celestial Resistance: necrotic + radiant
        'aasimar':             { damage_resistances: ['Necrotic', 'Radiant'], source: 'Celestial Resistance' },
        'protector-aasimar':   { damage_resistances: ['Necrotic', 'Radiant'], source: 'Celestial Resistance' },
        'scourge-aasimar':     { damage_resistances: ['Necrotic', 'Radiant'], source: 'Celestial Resistance' },
        'fallen-aasimar':      { damage_resistances: ['Necrotic', 'Radiant'], source: 'Celestial Resistance' },
        // Genasi
        'fire-genasi':         { damage_resistances: ['Fire'],      source: 'Fire Genasi — Fire Resistance' },
        'water-genasi':        { damage_resistances: ['Acid'],      source: 'Water Genasi — Acid Resistance' },
        // Triton
        'triton':              { damage_resistances: ['Cold'],      source: 'Triton — Guardians of the Depths' },
        // Yuan-ti — full poison immunity + Magic Resistance (advantage on spell saves, not a flat immunity)
        'yuan-ti-pureblood':   {
            damage_immunities:    ['Poison'],
            condition_immunities: ['Poisoned'],
            source: 'Yuan-ti Pureblood — Poison Immunity',
        },
        // Elves — all subraces share Fey Ancestry. Variants with extra
        // racial resistances (Shadar-kai, Sea Elf) combine both grants
        // under a single tooltip label.
        'elf':                 _FEY_ANCESTRY,
        'high-elf':            _FEY_ANCESTRY,
        'wood-elf':            _FEY_ANCESTRY,
        'drow':                _FEY_ANCESTRY,
        'eladrin':             _FEY_ANCESTRY,
        // Shadar-kai (Mordenkainen's Tome of Foes) — elf subrace, so
        // Fey Ancestry applies on top of Necrotic Resistance.
        'shadar-kai':          {
            damage_resistances:   ['Necrotic'],
            condition_immunities: ['Charmed'],
            source: 'Shadar-kai — Necrotic Resistance + Fey Ancestry',
        },
        // Sea Elf (MotM) — elf subrace; Cold Resistance + Fey Ancestry.
        'sea-elf':             {
            damage_resistances:   ['Cold'],
            condition_immunities: ['Charmed'],
            source: 'Sea Elf — Cold Resistance + Fey Ancestry',
        },
        // Halflings — Brave (RAW: advantage on saving throws against
        // being frightened). Same flexible-reading-as-immunity treatment
        // as Fey Ancestry above; the chip tooltip names the trait so
        // strict-RAW tables can read it as "advantage" not full immunity.
        // Stout subraces add Stout Resilience on top: a direct, RAW-
        // accurate analog of Dwarven Resilience (poison resistance +
        // advantage on poison saves).
        'halfling':            { condition_immunities: ['Frightened'], source: 'Brave (Halfling) — advantage on frightened saves' },
        'lightfoot-halfling':  { condition_immunities: ['Frightened'], source: 'Brave (Halfling) — advantage on frightened saves' },
        'ghostwise-halfling':  { condition_immunities: ['Frightened'], source: 'Brave (Halfling) — advantage on frightened saves' },
        'stout-halfling':      {
            damage_resistances:   ['Poison'],
            condition_immunities: ['Frightened'],
            source: 'Stout Halfling — Stout Resilience + Brave',
        },
        'strongheart-halfling': {
            damage_resistances:   ['Poison'],
            condition_immunities: ['Frightened'],
            source: 'Strongheart Halfling — Poison Resistance + Brave',
        },
    };

    // Class — array of level-gated grants (most classes have none; sparse on purpose).
    const CLS = {
        'monk': [
            {
                minLevel: 10,
                source: 'Purity of Body (Monk 10)',
                grants: {
                    damage_immunities:    ['Poison'],
                    condition_immunities: ['Poisoned'],
                },
            },
        ],
        // Barbarian's Rage gives BPS resistance, but only while raging —
        // deliberately not included here. The player tracks it via the
        // Rage resource counter, not as a sheet-state resistance.
    };

    // Subclass — same shape as CLS. Most PHB subclasses' defenses are
    // conditional (aura, while-raging, etc.) so this stays sparse.
    const SUB = {
        // example: 'storm-sorcery': [{ minLevel: 6, source: 'Heart of the Storm (Storm 6)',
        //   grants: { damage_resistances: ['Lightning', 'Thunder'] } }],
    };

    window._INNATE_DEFENSES = { race: RACE, class: CLS, subclass: SUB };

    /* Compute the active innate defenses from a sheet snapshot.
     * Input shape: ``{race: 'Tiefling', classes: [{class, subclass, level, _subclass_slug}, …]}``
     * Returns: ``{damage_resistances: [{label, source}, …], damage_immunities: […], …}``
     * Categories without grants come back as empty arrays so callers
     * can iterate the four keys uniformly.
     */
    function _slug(s) {
        return String(s || '').trim().toLowerCase().replace(/\s+/g, '-');
    }

    window._computeInnateDefenses = function (sheet) {
        const out = {
            damage_resistances: [],
            damage_immunities: [],
            damage_vulnerabilities: [],
            condition_immunities: [],
        };
        const seen = {
            damage_resistances: new Set(),
            damage_immunities: new Set(),
            damage_vulnerabilities: new Set(),
            condition_immunities: new Set(),
        };
        function _addGrant(grant, source) {
            for (const key of Object.keys(out)) {
                const labels = grant && Array.isArray(grant[key]) ? grant[key] : [];
                labels.forEach(label => {
                    const norm = String(label || '').trim();
                    if (!norm) return;
                    const lower = norm.toLowerCase();
                    if (seen[key].has(lower)) return;
                    seen[key].add(lower);
                    out[key].push({ label: norm, source: source || 'Innate' });
                });
            }
        }

        // Race grants
        const rslug = _slug(sheet && sheet.race);
        if (rslug && RACE[rslug]) {
            _addGrant(RACE[rslug], RACE[rslug].source);
        }

        // Class & subclass grants
        const roster = (sheet && Array.isArray(sheet.classes)) ? sheet.classes : [];
        roster.forEach(entry => {
            if (!entry || !entry.class) return;
            const cslug = _slug(entry.class);
            const lvl = parseInt(entry.level, 10) || 0;
            // Class tiers
            (CLS[cslug] || []).forEach(tier => {
                if (lvl >= (tier.minLevel || 1)) {
                    _addGrant(tier.grants || {}, tier.source);
                }
            });
            // Subclass tiers — prefer the cached _subclass_slug (Open5e
            // canonical) but fall back to slugifying the display name.
            const subSlug = entry._subclass_slug
                ? _slug(entry._subclass_slug)
                : _slug(entry.subclass);
            if (subSlug) {
                const subEntry = SUB[subSlug];
                if (Array.isArray(subEntry)) {
                    subEntry.forEach(tier => {
                        if (lvl >= (tier.minLevel || 1)) _addGrant(tier.grants || {}, tier.source);
                    });
                } else if (subEntry) {
                    _addGrant(subEntry, subEntry.source);
                }
            }
        });

        return out;
    };
})();
