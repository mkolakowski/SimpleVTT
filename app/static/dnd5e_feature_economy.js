/* dnd5e_feature_economy.js — canonical per-feature action-cost table.
 *
 * Phase 3 of the action-economy tracker (see docs/plans/class-content-status.md
 * section E). Maps class / subclass features to the economy slot they
 * consume. Lookup is keyed by a stable feature slug, plus an optional
 * sub-option slug (e.g. Cunning Action's three modes, Channel Divinity's
 * per-domain options).
 *
 * Consumed by:
 *   • app/templates/sheet_dnd5e.html — the Class abilities panel reads
 *     this table to decide which chip to flip when a feature button is
 *     clicked, and what description to show in the roll-log entry.
 *   • app/routes/tabletop_routes.py — a small Python mirror of this
 *     table powers the /api/campaign/{id}/use_feature endpoint so the
 *     server can derive the slot without trusting the client.
 *
 * Slots: "action" / "bonus" / "reaction" / "free". The "free" slot
 * means the feature does NOT consume any economy slot (e.g. Action
 * Surge grants an extra action, doesn't consume one). The chip code
 * treats "free" as a no-op.
 *
 * Keys: lowercase kebab-case feature slug. When a feature has sub-
 * options (Cunning Action: dash / disengage / hide; Channel Divinity:
 * turn-undead / preserve-life) the table nests `options` keyed by
 * option slug. Each option can override the slot if needed (most
 * inherit the parent feature's slot).
 *
 * Adding a new entry: append to the right class block alphabetically.
 * Mirror it in app/routes/tabletop_routes.py's _FEATURE_ECONOMY dict
 * so the server-side validator agrees.
 */

window._FEATURE_ECONOMY = {
    /* ── Rogue ───────────────────────────────────────────────────── */
    'cunning-action': {
        slot: 'bonus',
        class: 'rogue',
        unlock_level: 2,
        label: 'Cunning Action',
        desc: 'Take Dash, Disengage, or Hide as a bonus action.',
        options: {
            'dash': { label: 'Dash', desc: 'Move up to your speed again this turn.' },
            'disengage': { label: 'Disengage', desc: "Your movement doesn't provoke opportunity attacks this turn." },
            'hide': { label: 'Hide', desc: 'Make a Dexterity (Stealth) check to hide.' },
        },
    },

    /* ── Fighter ─────────────────────────────────────────────────── */
    'second-wind': {
        slot: 'bonus',
        class: 'fighter',
        unlock_level: 1,
        label: 'Second Wind',
        desc: 'Regain 1d10 + your fighter level HP. Recharges on a short or long rest.',
    },
    'action-surge': {
        slot: 'free',
        class: 'fighter',
        unlock_level: 2,
        label: 'Action Surge',
        desc: 'Take one additional action on this turn. Recharges on a short or long rest.',
        // Action Surge GRANTS an extra action — doesn't consume one. The
        // chip code treats slot:"free" as a no-op so clicking the button
        // doesn't flip any chip (the player will then click their actual
        // second action which marks Act for the round; the previously-
        // used Act stays burnt). Phase 4's GM shift+click chip-clear is
        // the proper way to model "I just got a second action."
    },

    /* ── Cleric ──────────────────────────────────────────────────── */
    'channel-divinity': {
        slot: 'action',
        class: 'cleric',
        unlock_level: 2,
        label: 'Channel Divinity',
        desc: 'Channel divine energy to fuel a domain-specific effect.',
        options: {
            'turn-undead': { label: 'Turn Undead', desc: 'Each undead within 30 ft makes a Wisdom save or flees for 1 minute.' },
            'preserve-life': { label: 'Preserve Life (Life)', desc: 'Distribute 5 × cleric level HP among creatures within 30 ft, none raised above half max HP.' },
            'radiance-of-the-dawn': { label: 'Radiance of the Dawn (Light)', desc: 'Dispel magical darkness, deal 2d10 + cleric level radiant damage on a failed Con save (each enemy within 30 ft).' },
            'guided-strike': { label: 'Guided Strike (War)', desc: '+10 bonus to one attack roll, declared after seeing the d20.' },
        },
    },

    /* ── Paladin ─────────────────────────────────────────────────── */
    'lay-on-hands': {
        slot: 'action',
        class: 'paladin',
        unlock_level: 1,
        label: 'Lay on Hands',
        desc: 'Spend from your pool (5 × paladin level) to heal a touched creature or cure poison/disease.',
    },
    'divine-smite': {
        slot: 'free',
        class: 'paladin',
        unlock_level: 2,
        label: 'Divine Smite',
        desc: 'After hitting with a melee weapon attack, expend a spell slot for +2d8 radiant (+1d8 per slot level above 1st; +1d8 vs undead/fiends).',
        // "Free" because Divine Smite augments an attack you already made
        // — the attack itself consumed action; the smite doesn't add a
        // second economy cost.
    },

    /* ── Bard ────────────────────────────────────────────────────── */
    'bardic-inspiration': {
        slot: 'bonus',
        class: 'bard',
        unlock_level: 1,
        label: 'Bardic Inspiration',
        desc: 'Pick one creature within 60 ft (other than yourself). They gain a bonus die to add to one ability check, attack roll, or save in the next 10 minutes.',
    },

    /* ── Monk ────────────────────────────────────────────────────── */
    'flurry-of-blows': {
        slot: 'bonus',
        class: 'monk',
        unlock_level: 2,
        label: 'Flurry of Blows',
        desc: 'Immediately after taking the Attack action, spend 1 ki to make two unarmed strikes as a bonus action.',
    },
    'patient-defense': {
        slot: 'bonus',
        class: 'monk',
        unlock_level: 2,
        label: 'Patient Defense',
        desc: 'Spend 1 ki to take the Dodge action as a bonus action.',
    },
    'step-of-the-wind': {
        slot: 'bonus',
        class: 'monk',
        unlock_level: 2,
        label: 'Step of the Wind',
        desc: 'Spend 1 ki to take the Disengage or Dash action as a bonus action; your jump distance doubles for the turn.',
    },

    /* ── Druid ───────────────────────────────────────────────────── */
    'wild-shape': {
        slot: 'action',
        class: 'druid',
        unlock_level: 2,
        label: 'Wild Shape',
        desc: 'Transform into a beast you have seen before.',
    },

    /* ── Barbarian ───────────────────────────────────────────────── */
    'rage': {
        slot: 'bonus',
        class: 'barbarian',
        unlock_level: 1,
        label: 'Rage',
        desc: '+damage on STR melee attacks, advantage on STR checks/saves, resistance to bludgeoning/piercing/slashing.',
    },
    'reckless-attack': {
        slot: 'free',
        class: 'barbarian',
        unlock_level: 2,
        label: 'Reckless Attack',
        desc: 'On your first attack this turn, gain advantage on melee STR attacks but attacks against you have advantage until your next turn.',
        // Modifies your existing attack action; doesn't consume a new slot.
    },

    /* ── Sorcerer ────────────────────────────────────────────────── */
    'quickened-spell': {
        slot: 'bonus',
        class: 'sorcerer',
        unlock_level: 3,
        label: 'Quickened Spell',
        desc: 'Spend 2 sorcery points to change the casting time of a 1-action spell to 1 bonus action this turn.',
        // Note: this metamagic effectively swaps action → bonus for the
        // spell it modifies, not adds an extra cost. UI should let the
        // player flip the cast slot manually; we tag it bonus here
        // because clicking the Quickened button itself is the slot
        // selector for the spell that follows.
    },
};

/* Lookup helper. Returns the merged feature + option entry or null
 * when the key isn't recognised. The `slot` on the returned object is
 * the option's slot if specified, else the parent feature's slot.
 *
 * Example:
 *   getFeatureEconomy('cunning-action', 'disengage')
 *   → { slot: 'bonus', label: 'Disengage', desc: '...', parent_label: 'Cunning Action' }
 *
 *   getFeatureEconomy('second-wind')
 *   → { slot: 'bonus', label: 'Second Wind', desc: '...' }
 */
window.getFeatureEconomy = function (featureKey, optionKey) {
    const fkey = String(featureKey || '').toLowerCase();
    const feat = window._FEATURE_ECONOMY[fkey];
    if (!feat) return null;
    if (!optionKey) {
        return {
            slot: feat.slot,
            label: feat.label,
            desc: feat.desc,
            class: feat.class,
            unlock_level: feat.unlock_level,
        };
    }
    const okey = String(optionKey).toLowerCase();
    const opt = (feat.options || {})[okey];
    if (!opt) return null;
    return {
        slot: opt.slot || feat.slot,
        label: opt.label,
        desc: opt.desc,
        parent_label: feat.label,
        class: feat.class,
        unlock_level: feat.unlock_level,
    };
};
