/* Beast Picker — shared module for Wild Shape / Polymorph beast selection.
 *
 * Surfaces a modal overlay (see app/templates/_beast_picker_modal.html)
 * that searches Open5e creatures, filters by type=Beast + CR cap, and
 * POSTs the chosen beast to the backend transform endpoint.
 *
 * Used from:
 *   - The standalone D&D 5e sheet (sheet_dnd5e.html — Wild Shape /
 *     Polymorph buttons in the Class Resources fieldset)
 *   - The tabletop mini-sheet (tabletop.html — Wild Shape / Polymorph
 *     mini buttons in the player drawer)
 *
 * API:
 *   window.BeastPicker.open({
 *       campaignId:         123,
 *       characterId:        456,
 *       source:             'wild-shape' | 'polymorph',
 *       druidLevel:         5,             // 0 if not a druid
 *       isMoonDruid:        false,
 *       characterLevel:     5,             // total class levels (caps Polymorph)
 *       onSuccess:          () => location.reload(),   // optional, default = reload
 *       favorites:          [                          // optional
 *           {slug:'wolf', name:'Wolf', cr:'1/4', type:'Beast',
 *            size:'Medium', hp:11, ac:13, source:'SRD'},
 *           // legacy v0.38.0 bare slug strings also accepted; they
 *           // get backfilled on first open and re-persisted.
 *       ],
 *       onFavoritesChange:  (newList) => {},           // optional, called after persist
 *   });
 *
 * Favorites carry their full lite stat block so the "★ Favorites"
 * section renders WITHOUT any Open5e call when every entry is cached.
 * Bare-slug entries (legacy) trigger a single backfill fetch on open,
 * after which the resolved data is persisted via /sheet-fields so
 * subsequent opens are cache-hits even if Open5e is unreachable.
 * The ★ button on each row toggles favorite state — the picker
 * PATCHes the new list back and calls onFavoritesChange if supplied
 * so the caller can refresh any cached copy.
 *
 * The overlay is a singleton — only one instance per page. Both
 * sheet_dnd5e.html and tabletop.html `{% include %}` the modal partial
 * exactly once.
 */
;(function () {
    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({
            '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
        }[c]));
    }
    function _crStr(cr) {
        if (cr <= 0) return '0';
        if (cr < 1) return cr === 0.125 ? '1/8' : cr === 0.25 ? '1/4' : cr === 0.5 ? '1/2' : String(cr);
        return String(cr);
    }
    function _parseCr(raw) {
        if (raw == null) return 0;
        const s = String(raw).trim();
        if (!s) return 0;
        if (s.includes('/')) {
            const [a, b] = s.split('/');
            return (parseFloat(b) > 0) ? parseFloat(a) / parseFloat(b) : 0;
        }
        return parseFloat(s) || 0;
    }
    function _wsCrCap(lv, moon) {
        const table = moon
            ? [[2,1],[4,2],[6,3],[8,4],[10,5],[12,6]]
            : [[2,0.25],[4,0.5],[8,1]];
        let cap = 0;
        for (const [reqLv, cr] of table) if (lv >= reqLv) cap = cr;
        return cap;
    }
    // Curated SRD beasts shown as "Quick Picks". Full stat blocks are
    // embedded so ability scores, attacks, and traits display without
    // any Open5e API call.
    const _PRESETS = [
      { slug:'cat', name:'Cat', cr:'0', type:'Beast', size:'Tiny', hp:2, ac:12, source:'SRD',
        desc:'A small domestic animal valued for its silence and keen senses. Excellent for low-profile scouting.',
        abilities:{STR:3,DEX:15,CON:10,INT:3,WIS:12,CHA:7}, speed:{walk:40,climb:30},
        traits:['Keen Smell — advantage on Perception checks relying on smell.'],
        actions:[{name:'Claws',desc:'Melee weapon attack: +0 to hit, reach 5 ft. Hit: 1 slashing damage.'}] },
      { slug:'rat', name:'Rat', cr:'0', type:'Beast', size:'Tiny', hp:1, ac:10, source:'SRD',
        desc:'A tiny rodent able to squeeze through tight spaces. Useful for infiltration and eavesdropping.',
        abilities:{STR:2,DEX:11,CON:9,INT:2,WIS:10,CHA:4}, speed:{walk:20},
        traits:['Keen Smell — advantage on Perception checks relying on smell.'],
        actions:[{name:'Bite',desc:'Melee weapon attack: +0 to hit, reach 5 ft. Hit: 1 piercing damage.'}] },
      { slug:'raven', name:'Raven', cr:'0', type:'Beast', size:'Tiny', hp:1, ac:12, source:'SRD',
        desc:'An intelligent corvid capable of mimicking sounds. Ideal for aerial scouting and carrying messages.',
        abilities:{STR:2,DEX:14,CON:8,INT:2,WIS:12,CHA:6}, speed:{walk:10,fly:50},
        traits:['Mimicry — can mimic simple sounds; DC 10 Insight check to recognise as imitation.'],
        actions:[{name:'Beak',desc:'Melee weapon attack: +4 to hit, reach 5 ft. Hit: 1 piercing damage.'}] },
      { slug:'poisonous-snake', name:'Poisonous Snake', cr:'1/8', type:'Beast', size:'Tiny', hp:2, ac:13, source:'SRD',
        desc:'A small venomous serpent. Useful for hiding in confined spaces and delivering a dangerous bite.',
        abilities:{STR:2,DEX:15,CON:11,INT:1,WIS:10,CHA:3}, speed:{walk:30,swim:30},
        traits:[],
        actions:[{name:'Bite',desc:'Melee weapon attack: +4 to hit, reach 5 ft. Hit: 1 piercing damage, and the target must make a DC 10 Constitution saving throw or take 5 (2d4) poison damage.'}] },
      { slug:'giant-rat', name:'Giant Rat', cr:'1/8', type:'Beast', size:'Small', hp:7, ac:12, source:'SRD',
        desc:'An oversized rodent that hunts in packs. Better in a fight than a normal rat.',
        abilities:{STR:7,DEX:15,CON:11,INT:2,WIS:10,CHA:4}, speed:{walk:30},
        traits:['Keen Smell.','Pack Tactics — advantage on attacks when an ally is adjacent to the target.'],
        actions:[{name:'Bite',desc:'Melee weapon attack: +4 to hit, reach 5 ft. Hit: 4 (1d4+2) piercing damage.'}] },
      { slug:'wolf', name:'Wolf', cr:'1/4', type:'Beast', size:'Medium', hp:11, ac:13, source:'SRD',
        desc:'A swift pack predator. Excellent for scouting, flanking, and knocking enemies prone.',
        abilities:{STR:12,DEX:15,CON:12,INT:3,WIS:12,CHA:6}, speed:{walk:40},
        traits:['Keen Hearing and Smell.','Pack Tactics — advantage on attacks when an ally is adjacent to the target.'],
        actions:[{name:'Bite',desc:'Melee weapon attack: +4 to hit, reach 5 ft. Hit: 7 (2d4+2) piercing damage. The target must succeed on a DC 11 Strength saving throw or be knocked prone.'}] },
      { slug:'panther', name:'Panther', cr:'1/4', type:'Beast', size:'Medium', hp:13, ac:12, source:'SRD',
        desc:'A fast, agile ambush predator. Pounce can knock an enemy prone and allow a bonus-action bite.',
        abilities:{STR:14,DEX:15,CON:10,INT:3,WIS:14,CHA:7}, speed:{walk:50,climb:40},
        traits:['Keen Smell.','Pounce — if the panther moves 20 ft. toward a target and hits with a claw, the target must make a DC 12 Strength save or be knocked prone; the panther can then bite as a bonus action.'],
        actions:[
          {name:'Bite',desc:'Melee weapon attack: +4 to hit, reach 5 ft. Hit: 5 (1d6+2) piercing damage.'},
          {name:'Claw',desc:'Melee weapon attack: +4 to hit, reach 5 ft. Hit: 4 (1d4+2) slashing damage.'} ] },
      { slug:'giant-badger', name:'Giant Badger', cr:'1/4', type:'Beast', size:'Medium', hp:13, ac:10, source:'SRD',
        desc:'A tenacious digger with a ferocious bite and strong claws. Can burrow through soft earth.',
        abilities:{STR:13,DEX:10,CON:15,INT:2,WIS:12,CHA:5}, speed:{walk:30,burrow:10},
        traits:['Keen Smell.'],
        actions:[
          {name:'Multiattack',desc:'The badger makes two attacks: one with its bite and one with its claws.'},
          {name:'Bite',desc:'Melee weapon attack: +3 to hit, reach 5 ft. Hit: 4 (1d6+1) piercing damage.'},
          {name:'Claws',desc:'Melee weapon attack: +3 to hit, reach 5 ft. Hit: 6 (2d4+1) slashing damage.'} ] },
      { slug:'constrictor-snake', name:'Constrictor Snake', cr:'1/4', type:'Beast', size:'Large', hp:13, ac:12, source:'SRD',
        desc:'A powerful serpent that grapples and crushes its prey. Good for locking down a single target.',
        abilities:{STR:15,DEX:14,CON:12,INT:1,WIS:10,CHA:3}, speed:{walk:30,swim:30},
        traits:[],
        actions:[
          {name:'Bite',desc:'Melee weapon attack: +4 to hit, reach 5 ft. Hit: 5 (1d6+2) piercing damage.'},
          {name:'Constrict',desc:'Melee weapon attack: +4 to hit, reach 5 ft., one creature. Hit: 6 (1d8+2) bludgeoning damage, and the target is grappled (escape DC 14). Until this grapple ends, the creature is restrained.'} ] },
      { slug:'black-bear', name:'Black Bear', cr:'1/2', type:'Beast', size:'Medium', hp:19, ac:11, source:'SRD',
        desc:'A sturdy forest bear. A solid choice for early-level combat with reliable multi-attack.',
        abilities:{STR:15,DEX:10,CON:14,INT:2,WIS:12,CHA:7}, speed:{walk:40,climb:30},
        traits:['Keen Smell.'],
        actions:[
          {name:'Multiattack',desc:'The bear makes two attacks: one with its bite and one with its claws.'},
          {name:'Bite',desc:'Melee weapon attack: +4 to hit, reach 5 ft. Hit: 5 (1d6+2) piercing damage.'},
          {name:'Claws',desc:'Melee weapon attack: +4 to hit, reach 5 ft. Hit: 7 (2d4+2) slashing damage.'} ] },
      { slug:'ape', name:'Ape', cr:'1/2', type:'Beast', size:'Medium', hp:19, ac:12, source:'SRD',
        desc:'A strong primate with notable Intelligence for a beast. Can hurl rocks as a ranged attack.',
        abilities:{STR:16,DEX:14,CON:14,INT:6,WIS:12,CHA:7}, speed:{walk:30,climb:30},
        traits:[],
        actions:[
          {name:'Multiattack',desc:'The ape makes two fist attacks.'},
          {name:'Fist',desc:'Melee weapon attack: +5 to hit, reach 5 ft. Hit: 6 (1d6+3) bludgeoning damage.'},
          {name:'Rock',desc:'Ranged weapon attack: +5 to hit, range 25/50 ft. Hit: 6 (1d6+3) bludgeoning damage.'} ] },
      { slug:'giant-wasp', name:'Giant Wasp', cr:'1/2', type:'Beast', size:'Medium', hp:13, ac:12, source:'SRD',
        desc:'A flying insect with a potent venomous sting. Good for aerial harassment and poisoning targets.',
        abilities:{STR:10,DEX:14,CON:10,INT:1,WIS:10,CHA:3}, speed:{walk:10,fly:50},
        traits:[],
        actions:[{name:'Sting',desc:'Melee weapon attack: +4 to hit, reach 5 ft. Hit: 5 (1d6+2) piercing damage, and the target must make a DC 11 Constitution saving throw, taking 10 (3d6) poison damage on a failed save, or half as much on a success. A failed save also poisons the target for 1 minute; it may repeat the save at end of each of its turns.'}] },
      { slug:'brown-bear', name:'Brown Bear', cr:'1', type:'Beast', size:'Large', hp:34, ac:11, source:'SRD',
        desc:'A large, powerful bear with impressive HP and multiattack. A druid staple at level 2.',
        abilities:{STR:19,DEX:10,CON:16,INT:2,WIS:13,CHA:7}, speed:{walk:40,climb:30},
        traits:['Keen Smell.'],
        actions:[
          {name:'Multiattack',desc:'The bear makes two attacks: one with its bite and one with its claws.'},
          {name:'Bite',desc:'Melee weapon attack: +6 to hit, reach 5 ft. Hit: 8 (1d8+4) piercing damage.'},
          {name:'Claws',desc:'Melee weapon attack: +6 to hit, reach 5 ft. Hit: 11 (2d6+4) slashing damage.'} ] },
      { slug:'dire-wolf', name:'Dire Wolf', cr:'1', type:'Beast', size:'Large', hp:37, ac:14, source:'SRD',
        desc:'A massive wolf with high AC and pack tactics. Outstanding for groups that can flank.',
        abilities:{STR:17,DEX:15,CON:15,INT:3,WIS:12,CHA:7}, speed:{walk:50},
        traits:['Keen Hearing and Smell.','Pack Tactics — advantage on attacks when an ally is adjacent to the target.'],
        actions:[{name:'Bite',desc:'Melee weapon attack: +5 to hit, reach 5 ft. Hit: 10 (2d6+3) piercing damage. The target must succeed on a DC 13 Strength saving throw or be knocked prone.'}] },
      { slug:'giant-spider', name:'Giant Spider', cr:'1', type:'Beast', size:'Medium', hp:26, ac:14, source:'SRD',
        desc:'A web-spinning predator that can restrain targets from range and climb any surface.',
        abilities:{STR:14,DEX:16,CON:12,INT:2,WIS:11,CHA:4}, speed:{walk:30,climb:30},
        traits:['Spider Climb — can climb difficult surfaces including ceilings.','Web Sense — knows the location of any creature in contact with its webs.','Web Walker — ignores movement restrictions from webbing.'],
        actions:[
          {name:'Bite',desc:'Melee weapon attack: +5 to hit, reach 5 ft. Hit: 7 (1d8+3) piercing damage, and the target must make a DC 11 Constitution saving throw, taking 9 (2d8) poison damage on failure (half on success). If poison damage drops the target to 0 hp, it is stable but poisoned for 1 hour and paralyzed while poisoned.'},
          {name:'Web (Recharge 5–6)',desc:'Ranged weapon attack: +5 to hit, range 30/60 ft. Hit: The target is restrained by webbing. As an action, the restrained target can make a DC 12 Strength check, bursting the webbing on a success.'} ] },
      { slug:'tiger', name:'Tiger', cr:'1', type:'Beast', size:'Large', hp:37, ac:12, source:'SRD',
        desc:'A stealthy ambush hunter. High STR and Pounce let it control the battlefield.',
        abilities:{STR:17,DEX:15,CON:14,INT:3,WIS:12,CHA:8}, speed:{walk:40},
        traits:['Keen Smell.','Pounce — if the tiger moves 20 ft. toward a target and hits with a claw, the target must make a DC 13 Strength save or be knocked prone; the tiger can then bite as a bonus action.'],
        actions:[
          {name:'Bite',desc:'Melee weapon attack: +5 to hit, reach 5 ft. Hit: 8 (1d10+3) piercing damage.'},
          {name:'Claw',desc:'Melee weapon attack: +5 to hit, reach 5 ft. Hit: 7 (1d8+3) slashing damage.'} ] },
      { slug:'giant-constrictor-snake', name:'Giant Constrictor Snake', cr:'2', type:'Beast', size:'Huge', hp:60, ac:12, source:'SRD',
        desc:'A massive serpent that can restrain Large or smaller creatures indefinitely. Devastating grappler.',
        abilities:{STR:19,DEX:14,CON:12,INT:1,WIS:10,CHA:3}, speed:{walk:30,swim:30},
        traits:[],
        actions:[
          {name:'Bite',desc:'Melee weapon attack: +6 to hit, reach 10 ft. Hit: 11 (2d6+4) piercing damage.'},
          {name:'Constrict',desc:'Melee weapon attack: +6 to hit, reach 5 ft. Hit: 13 (2d8+4) bludgeoning damage, and the target is grappled (escape DC 16). Until this grapple ends, the creature is restrained and the snake can\'t constrict another target.'} ] },
      { slug:'polar-bear', name:'Polar Bear', cr:'2', type:'Beast', size:'Large', hp:42, ac:12, source:'SRD',
        desc:'A powerful bear with exceptional STR and swim speed. Ideal for aquatic or arctic encounters.',
        abilities:{STR:20,DEX:10,CON:16,INT:2,WIS:13,CHA:7}, speed:{walk:40,swim:30},
        traits:['Keen Smell.'],
        actions:[
          {name:'Multiattack',desc:'The bear makes two attacks: one with its bite and one with its claws.'},
          {name:'Bite',desc:'Melee weapon attack: +7 to hit, reach 5 ft. Hit: 9 (1d8+5) piercing damage.'},
          {name:'Claws',desc:'Melee weapon attack: +7 to hit, reach 5 ft. Hit: 12 (2d6+5) slashing damage.'} ] },
      { slug:'allosaurus', name:'Allosaurus', cr:'2', type:'Beast', size:'Large', hp:51, ac:13, source:'SRD',
        desc:'A fast, aggressive theropod. Exceptional speed (60 ft.) and Pounce make it a fearsome charger.',
        abilities:{STR:19,DEX:13,CON:17,INT:2,WIS:12,CHA:5}, speed:{walk:60},
        traits:['Pounce — if the allosaurus moves 30 ft. toward a target and hits with a claw, the target must make a DC 13 Strength save or be knocked prone; the allosaurus can then bite as a bonus action.'],
        actions:[
          {name:'Bite',desc:'Melee weapon attack: +6 to hit, reach 5 ft. Hit: 15 (2d10+4) piercing damage.'},
          {name:'Claw',desc:'Melee weapon attack: +6 to hit, reach 5 ft. Hit: 8 (1d8+4) slashing damage.'} ] },
      { slug:'ankylosaurus', name:'Ankylosaurus', cr:'3', type:'Beast', size:'Huge', hp:68, ac:15, source:'SRD',
        desc:'A heavily armoured dinosaur with a bone-crushing tail. Exceptional AC for its CR.',
        abilities:{STR:19,DEX:11,CON:15,INT:2,WIS:12,CHA:5}, speed:{walk:30},
        traits:[],
        actions:[{name:'Tail',desc:'Melee weapon attack: +7 to hit, reach 10 ft. Hit: 18 (4d6+4) bludgeoning damage. If the target is a creature, it must succeed on a DC 14 Strength saving throw or be knocked prone.'}] },
      { slug:'killer-whale', name:'Killer Whale', cr:'3', type:'Beast', size:'Huge', hp:90, ac:12, source:'SRD',
        desc:'A massive apex predator built for the sea. Highest HP of any CR 3 beast; requires water to swim.',
        abilities:{STR:19,DEX:10,CON:13,INT:3,WIS:12,CHA:7}, speed:{swim:60},
        traits:['Echolocation — can\'t use blindsight while deafened.','Hold Breath — can hold its breath for 30 minutes.','Keen Hearing.'],
        actions:[{name:'Bite',desc:'Melee weapon attack: +6 to hit, reach 5 ft. Hit: 21 (5d6+4) piercing damage.'}] },
      { slug:'giant-scorpion', name:'Giant Scorpion', cr:'3', type:'Beast', size:'Large', hp:52, ac:15, source:'SRD',
        desc:'A multi-limbed predator with grappling claws and a deadly poisonous sting.',
        abilities:{STR:15,DEX:13,CON:15,INT:1,WIS:9,CHA:3}, speed:{walk:40},
        traits:[],
        actions:[
          {name:'Multiattack',desc:'The scorpion makes three attacks: two with its claws and one with its sting.'},
          {name:'Claw',desc:'Melee weapon attack: +4 to hit, reach 5 ft. Hit: 6 (1d8+2) bludgeoning damage, and the target is grappled (escape DC 12). The scorpion has two claws, each of which can grapple one target.'},
          {name:'Sting',desc:'Melee weapon attack: +4 to hit, reach 5 ft. Hit: 7 (1d10+2) piercing damage, and the target must make a DC 12 Constitution saving throw, taking 22 (4d10) poison damage on a failed save, or half as much on a success.'} ] },
      { slug:'elephant', name:'Elephant', cr:'4', type:'Beast', size:'Huge', hp:76, ac:12, source:'SRD',
        desc:'A massive beast with a trampling charge that can knock down and stomp targets.',
        abilities:{STR:22,DEX:9,CON:17,INT:3,WIS:11,CHA:6}, speed:{walk:40},
        traits:['Trampling Charge — if the elephant moves 20 ft. toward a target and hits with a gore, the target must make a DC 12 Strength save or be knocked prone; the elephant can then stomp as a bonus action.'],
        actions:[
          {name:'Gore',desc:'Melee weapon attack: +8 to hit, reach 5 ft. Hit: 19 (3d6+6) piercing damage.'},
          {name:'Stomp',desc:'Melee weapon attack: +8 to hit, reach 5 ft., one prone creature. Hit: 22 (3d8+6) bludgeoning damage.'} ] },
      { slug:'triceratops', name:'Triceratops', cr:'5', type:'Beast', size:'Huge', hp:114, ac:13, source:'SRD',
        desc:'A horned dinosaur with high HP and a devastating trampling charge. Solid frontliner.',
        abilities:{STR:22,DEX:9,CON:17,INT:2,WIS:11,CHA:5}, speed:{walk:50},
        traits:['Trampling Charge — if the triceratops moves 20 ft. toward a target and hits with a gore, the target must make a DC 13 Strength save or be knocked prone; the triceratops can then stomp as a bonus action.'],
        actions:[
          {name:'Gore',desc:'Melee weapon attack: +9 to hit, reach 5 ft. Hit: 24 (4d8+6) piercing damage.'},
          {name:'Stomp',desc:'Melee weapon attack: +9 to hit, reach 5 ft., one prone creature. Hit: 22 (3d10+6) bludgeoning damage.'} ] },
      { slug:'giant-crocodile', name:'Giant Crocodile', cr:'5', type:'Beast', size:'Huge', hp:114, ac:14, source:'SRD',
        desc:'A heavily armoured aquatic ambush predator that grapples with its bite and can knock targets prone with its tail.',
        abilities:{STR:21,DEX:9,CON:17,INT:2,WIS:10,CHA:7}, speed:{walk:30,swim:50},
        traits:['Hold Breath — can hold its breath for 30 minutes.'],
        actions:[
          {name:'Multiattack',desc:'The crocodile makes two attacks: one with its bite and one with its tail.'},
          {name:'Bite',desc:'Melee weapon attack: +8 to hit, reach 5 ft. Hit: 21 (3d10+5) piercing damage, and the target is grappled (escape DC 16). Until this grapple ends, the target is restrained and the crocodile can\'t bite another target.'},
          {name:'Tail',desc:'Melee weapon attack: +8 to hit, reach 10 ft., one target not grappled by the crocodile. Hit: 14 (2d8+5) bludgeoning damage. If the target is a creature, it must succeed on a DC 16 Strength saving throw or be knocked prone.'} ] },
      { slug:'mammoth', name:'Mammoth', cr:'6', type:'Beast', size:'Huge', hp:126, ac:13, source:'SRD',
        desc:'A colossal prehistoric elephant with outstanding STR and CON. The most powerful non-Moon-Druid form at level 8.',
        abilities:{STR:24,DEX:9,CON:21,INT:3,WIS:11,CHA:6}, speed:{walk:40},
        traits:['Trampling Charge — if the mammoth moves 20 ft. toward a target and hits with a gore, the target must make a DC 18 Strength save or be knocked prone; the mammoth can then stomp as a bonus action.'],
        actions:[
          {name:'Gore',desc:'Melee weapon attack: +10 to hit, reach 10 ft. Hit: 25 (4d8+7) piercing damage.'},
          {name:'Stomp',desc:'Melee weapon attack: +10 to hit, reach 5 ft., one prone creature. Hit: 29 (4d10+7) bludgeoning damage.'} ] },
      { slug:'tyrannosaurus-rex', name:'Tyrannosaurus Rex', cr:'8', type:'Beast', size:'Huge', hp:136, ac:13, source:'SRD',
        desc:'The apex predator of the preset list. Enormous bite damage and grapple on a hit; Moon Druids only (level 12+).',
        abilities:{STR:25,DEX:10,CON:19,INT:2,WIS:12,CHA:9}, speed:{walk:50},
        traits:[],
        actions:[
          {name:'Multiattack',desc:'The T. rex makes two attacks: one with its bite and one with its tail. It can\'t make both attacks against the same target.'},
          {name:'Bite',desc:'Melee weapon attack: +10 to hit, reach 10 ft. Hit: 33 (4d12+7) piercing damage. If the target is Medium or smaller, it is grappled (escape DC 17). Until this grapple ends, the target is restrained and the T. rex can\'t bite another target.'},
          {name:'Tail',desc:'Melee weapon attack: +10 to hit, reach 10 ft. Hit: 20 (3d8+7) bludgeoning damage.'} ] },
    ];

    function _toast(msg, kind) {
        if (typeof window._toast === 'function') return window._toast(msg, kind);
        if (typeof window.showToast === 'function') return window.showToast(msg, kind);
        console.log('[BeastPicker]', msg);
    }

    // Lazy DOM lookups so the picker can be invoked before any inline
    // <script>s run (e.g. from sheet.js inside a stripped-script modal).
    function $(id) { return document.getElementById(id); }

    let _state = null;   // { opts, cap, results, selected }

    function _close() {
        const overlay = $('beast-picker-overlay');
        if (overlay) overlay.style.display = 'none';
        _state = null;
    }

    // Defensive coercion: Open5e v2 occasionally returns ``type``/``size``
    // as ``{key, name}`` dicts instead of strings (the server normalizes
    // these, but belt-and-braces here keeps the picker working if a
    // proxy mid-stream slips a raw v2 response through).
    function _str(v) {
        if (v == null) return '';
        if (typeof v === 'string') return v;
        if (typeof v === 'object') return String(v.name || v.key || '');
        return String(v);
    }

    function _rowHtml(r, isFavorite) {
        // Single row used by both the Favorites section at the top and
        // the live search results below it. The ★ button toggles
        // favorite state; ev.stopPropagation in the click handler keeps
        // it from also selecting the row.
        const starColor = isFavorite ? '#f7c948' : 'var(--s-mute)';
        const starGlyph = isFavorite ? '★' : '☆';
        const starTitle = isFavorite ? 'Unfavorite' : 'Favorite';
        // Campaign-authored homebrew rows carry ``is_custom: true`` from the
        // server. Render a tiny gold pill so GMs can tell at a glance which
        // entries came from their settings page vs. Open5e.
        const customBadge = r.is_custom
            ? `<span title="Campaign-authored homebrew" style="font-size:9px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:#d4a84a;background:#3a2f15;border:1px solid #6e5828;border-radius:3px;padding:0 4px;margin-left:5px;vertical-align:1px;">Custom</span>`
            : '';
        return `
            <div class="bp-row" data-slug="${_esc(r.slug)}"
                 style="padding:7px 14px;cursor:pointer;border-bottom:1px solid var(--s-border);display:flex;align-items:flex-start;gap:8px;">
                <button type="button" class="bp-fav" data-slug="${_esc(r.slug)}"
                        title="${starTitle}"
                        style="background:none;border:none;font-size:16px;color:${starColor};cursor:pointer;padding:0 2px;line-height:1;flex-shrink:0;margin-top:1px;">${starGlyph}</button>
                <div style="flex:1;min-width:0;">
                    <div style="font-size:12px;font-weight:700;color:var(--s-fg);">${_esc(r.name)}${customBadge}</div>
                    <div style="font-size:10px;color:var(--s-mute);">CR ${_esc(r.cr || '0')} · ${_esc(_str(r.size))} ${_esc(_str(r.type))}</div>
                </div>
            </div>
        `;
    }

    function _sectionHeader(label) {
        return `<div style="padding:5px 14px;font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--s-mute);background:var(--s-input);border-bottom:1px solid var(--s-border);text-transform:uppercase;">${_esc(label)}</div>`;
    }

    function _renderList() {
        const listPanel = $('bp-list-panel');
        if (!listPanel || !_state) return;
        const free = $('bp-free-pick').checked;
        const all = _state.results || [];
        const favSet = _state.favorites || new Set();
        // Client-side name filter as a safety net — the server already
        // forwards ``name__icontains`` to Open5e v2, but if the upstream
        // API ever drops or renames that filter we still want the picker
        // to narrow results to what the user typed. Also handy when Free
        // pick is on (we want the search term to still narrow the type-
        // unfiltered list).
        const qLower = String(_state.lastQuery || '').toLowerCase();
        const filtered = all.filter(r => {
            if (qLower && !String(r.name || '').toLowerCase().includes(qLower)) return false;
            if (free) return true;
            if (_str(r.type).toLowerCase() !== 'beast') return false;
            if (_parseCr(r.cr) > _state.cap) return false;
            return true;
        });

        // Favorites that also match the current search term — keeps the
        // top section relevant when the user has many favorites and is
        // typing to narrow.
        const favResults = (_state.favoriteResults || []).filter(r => {
            if (!qLower) return true;
            return String(r.name || '').toLowerCase().includes(qLower);
        });

        // Always surface a count so users understand whether the API is
        // returning data (and how aggressively the type/CR filter is
        // chopping). The total reported by the API can be far larger
        // than what we fetched; show the page size honestly.
        const statusEl = $('bp-status');
        if (statusEl) {
            const total = _state.totalCount || all.length;
            const shown = filtered.length;
            const favCount = favResults.length;
            const favPart = favCount ? `★ ${favCount} favorite${favCount === 1 ? '' : 's'} · ` : '';
            statusEl.textContent = free
                ? `${favPart}${shown} of ${all.length} on this page (${total} total) — free pick`
                : `${favPart}${shown} of ${all.length} on this page match the beast / CR filter`;
        }

        // Presets filtered by CR cap and name query; skip any already shown
        // in the Favorites section to avoid duplicate rows.
        const favSlugSet = new Set(favResults.map(r => r.slug));
        const presetMatches = _PRESETS.filter(r => {
            if (qLower && !String(r.name || '').toLowerCase().includes(qLower)) return false;
            if (!free && _parseCr(r.cr) > _state.cap) return false;
            if (favSlugSet.has(r.slug)) return false;
            return true;
        });

        const sections = [];
        if (favResults.length) {
            sections.push(_sectionHeader('★ Favorites'));
            sections.push(favResults.map(r => _rowHtml(r, true)).join(''));
        }
        if (presetMatches.length) {
            sections.push(_sectionHeader('⚡ Quick Picks'));
            sections.push(presetMatches.map(r => _rowHtml(r, favSet.has(r.slug))).join(''));
        }
        if (filtered.length) {
            const hasAbove = favResults.length || presetMatches.length;
            if (hasAbove) sections.push(_sectionHeader(qLower ? 'Other matches' : 'All beasts'));
            sections.push(filtered.map(r => _rowHtml(r, favSet.has(r.slug))).join(''));
        }
        if (!sections.length) {
            const hint = free
                ? 'API returned an empty page — try a different search term.'
                : `No beasts within your CR cap on this page. Try a search term, or enable Free pick to bypass the filter.`;
            listPanel.innerHTML = `<div style="padding:14px;color:var(--s-mute);font-size:12px;">${hint}</div>`;
            return;
        }
        listPanel.innerHTML = sections.join('');
    }

    function _abilityMod(score) {
        const mod = Math.floor((parseInt(score, 10) - 10) / 2);
        return mod >= 0 ? `+${mod}` : `${mod}`;
    }

    function _findInState(slug) {
        const inResults = (_state?.results || []).find(r => r.slug === slug);
        if (inResults) return inResults;
        const inFavs = (_state?.favoriteResults || []).find(r => r.slug === slug);
        if (inFavs) return inFavs;
        return _PRESETS.find(r => r.slug === slug) || null;
    }

    function _buildDetailHtml(m, full) {
        const free = $('bp-free-pick').checked;
        const typeOk = _str(m.type).toLowerCase() === 'beast';
        const crOk   = _parseCr(m.cr) <= (_state?.cap ?? 0);
        let warn = '';
        if (!free) {
            if (!typeOk) warn = `<div style="padding:8px 10px;margin-top:8px;background:var(--s-err-bg);border:1px solid var(--s-danger);color:var(--s-err-fg);border-radius:5px;font-size:11px;">⚠ Not a beast — enable Free pick to override.</div>`;
            else if (!crOk) warn = `<div style="padding:8px 10px;margin-top:8px;background:var(--s-err-bg);border:1px solid var(--s-danger);color:var(--s-err-fg);border-radius:5px;font-size:11px;">⚠ CR ${m.cr} exceeds your cap of ${_crStr(_state.cap)} — enable Free pick to override.</div>`;
        }
        const isPoly = _state?.opts?.source === 'polymorph';
        const abils = full?.abilities;
        const abilBlock = abils ? `
            <div style="margin-top:10px;">
                <table style="width:100%;border-collapse:collapse;font-size:11px;text-align:center;">
                    <thead><tr>${['STR','DEX','CON','INT','WIS','CHA'].map(a =>
                        `<th style="color:var(--s-mute);font-weight:600;padding:2px 0;width:16.6%;">${a}</th>`).join('')}</tr></thead>
                    <tbody><tr>${['STR','DEX','CON','INT','WIS','CHA'].map(a => {
                        const v = abils[a] ?? 10;
                        return `<td style="color:var(--s-fg);padding:2px 0;">${v}<br><span style="color:var(--s-mute);font-size:10px;">${_abilityMod(v)}</span></td>`;
                    }).join('')}</tr></tbody>
                </table>
            </div>` : '';

        const speedParts = [];
        if (full?.speed && typeof full.speed === 'object') {
            for (const [k, v] of Object.entries(full.speed)) {
                if (v) speedParts.push(`${k} ${v} ft`);
            }
        }
        const speedStr = speedParts.length
            ? ` · <strong>Speed</strong> ${speedParts.join(', ')}`
            : (m.speed ? ` · <strong>Speed</strong> ${_esc(String(m.speed))} ft` : '');

        let traitsHtml = '';
        if (full?.traits?.length) {
            traitsHtml = `<div style="margin-top:10px;">
                <div style="font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--s-mute);text-transform:uppercase;margin-bottom:4px;">Traits</div>
                ${full.traits.map(t => `<div style="font-size:11px;color:var(--s-mute);margin-bottom:3px;">• ${_esc(t)}</div>`).join('')}
            </div>`;
        }

        let actionsHtml = '';
        if (full?.actions?.length) {
            actionsHtml = `<div style="margin-top:10px;">
                <div style="font-size:10px;font-weight:700;letter-spacing:.06em;color:var(--s-mute);text-transform:uppercase;margin-bottom:4px;">Actions</div>
                ${full.actions.map(a => `
                    <div style="margin-bottom:6px;">
                        <span style="font-size:11px;font-weight:700;color:var(--s-fg);">${_esc(a.name)}.</span>
                        <span style="font-size:11px;color:var(--s-mute);"> ${_esc(a.desc)}</span>
                    </div>`).join('')}
            </div>`;
        }

        const descHtml = full?.desc
            ? `<p style="font-size:11px;color:var(--s-mute);margin-top:8px;margin-bottom:0;line-height:1.45;font-style:italic;">${_esc(full.desc)}</p>`
            : '';

        return `
            <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;">
                <h3 style="margin:0;font-size:18px;color:var(--s-fg);">${_esc(m.name)}</h3>
                <span style="font-size:12px;color:var(--s-mute);">CR ${_esc(m.cr || '0')}</span>
            </div>
            <div style="font-size:11px;color:var(--s-mute);margin-top:2px;">${_esc(_str(m.size))} ${_esc(_str(m.type))}</div>
            ${descHtml}
            <div style="display:flex;gap:14px;margin-top:8px;flex-wrap:wrap;font-size:12px;color:var(--s-fg);">
                <span><strong>HP</strong> ${_esc(m.hp ?? '?')}</span>
                <span><strong>AC</strong> ${_esc(m.ac ?? '?')}</span>${speedStr}
            </div>
            ${abilBlock}
            ${traitsHtml}
            ${actionsHtml}
            ${warn}
            <p style="font-size:11px;color:var(--s-mute);margin-top:10px;line-height:1.45;">
                Transforms replace your HP, AC, speed,
                ${isPoly ? '<strong>all ability scores</strong>' : 'STR / DEX / CON (keeps your INT / WIS / CHA)'},
                skills, saves, and attacks. Class features, spells, and inventory are preserved.
                Click <strong>Revert</strong> on the active-form banner to switch back.
            </p>
        `;
    }

    async function _renderDetail(slug) {
        const detail = $('bp-detail-panel');
        if (!detail || !_state) return;
        const base = _findInState(slug);
        if (!base) return;

        _state.selected = base;
        $('bp-confirm-btn').disabled = false;
        // Presets carry embedded stat blocks — use them immediately so the
        // panel is complete without any API call.
        const localFull = base.abilities ? base : null;
        detail.innerHTML = _buildDetailHtml(base, localFull);
        // Still try to enrich from Open5e (resolves canonical v2 slug,
        // may add extra data). Failures are silently ignored.
        _renderDetailFull(base, detail).catch(() => {});
    }

    async function _renderDetailFull(m, detail) {
        if (!_state) return;
        try {
            const cid = _state.opts?.campaignId ? `&campaign_id=${_state.opts.campaignId}` : '';
            const resp = await fetch(`/api/open5e/creature/${encodeURIComponent(m.slug)}?full=1${cid}`);
            if (resp.ok) {
                const full = await resp.json();
                // Use the slug from the server response as the canonical v2 slug
                const resolved = { ...m, slug: full.slug || m.slug };
                _state.selected = resolved;
                $('bp-confirm-btn').disabled = false;
                detail.innerHTML = _buildDetailHtml(resolved, full);
            } else {
                // Full fetch failed — already showing basic detail, leave it.
                _state.selected = m;
                $('bp-confirm-btn').disabled = false;
            }
        } catch {
            _state.selected = m;
            $('bp-confirm-btn').disabled = false;
        }
    }

    async function _runSearch() {
        if (!_state) return;
        const q = ($('bp-search').value || '').trim();
        _state.lastQuery = q;   // remembered so _renderList can name-filter locally
        const listPanel = $('bp-list-panel');
        listPanel.innerHTML = '<div style="padding:14px;color:var(--s-mute);font-size:12px;">Searching…</div>';

        // Push the type + CR filter to the server when Free pick is off,
        // so v2 returns a page of relevant matches instead of 50 random
        // creatures most of which would fail our client-side filter.
        const free = $('bp-free-pick')?.checked;
        const params = new URLSearchParams();
        params.set('search', q);
        params.set('limit', '50');
        if (!free) {
            params.set('type_filter', 'beast');
            if (_state.cap && _state.cap > 0) {
                params.set('cr_max', _crStr(_state.cap));
            }
        }

        try {
            // Thread campaign id through so homebrew monsters merge into
            // the response (server-side dedupes any slug collision).
            if (_state.opts && _state.opts.campaignId) {
                params.set('campaign_id', _state.opts.campaignId);
            }
            const resp = await fetch(`/api/open5e/monsters?${params.toString()}`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            _state.results = data.results || [];
            _state.totalCount = data.count || 0;
            _renderList();
        } catch (e) {
            // Search failed (e.g. Open5e unreachable). Clear results and
            // re-render so Quick Picks and Favorites still appear.
            _state.results = [];
            _state.totalCount = 0;
            _renderList();
            const statusEl = $('bp-status');
            if (statusEl) statusEl.textContent = `Search unavailable: ${e.message}`;
        }
    }

    async function _confirm() {
        if (!_state || !_state.selected) return;
        const { opts, selected } = _state;
        $('bp-confirm-btn').disabled = true;
        $('bp-status').textContent = 'Transforming…';
        try {
            const resp = await fetch(`/api/campaign/${opts.campaignId}/character/${opts.characterId}/transform`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    slug: selected.slug,
                    source: opts.source,
                    free_pick: $('bp-free-pick').checked,
                }),
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: 'Transform failed' }));
                throw new Error(err.detail || err.error || `HTTP ${resp.status}`);
            }
            // Default behaviour: reload the page so all stats re-render.
            // Callers can override via onSuccess (e.g. mini-sheet partial refresh).
            if (typeof opts.onSuccess === 'function') {
                opts.onSuccess();
            } else {
                window.location.reload();
            }
            _close();
        } catch (e) {
            $('bp-status').textContent = '';
            _toast('Transform failed: ' + e.message, 'error');
            $('bp-confirm-btn').disabled = false;
        }
    }

    // True when a favorite entry has enough fields cached locally that
    // the picker can render its row without an Open5e call.
    function _favHasCache(fav) {
        return !!(fav && fav.slug && fav.name && fav.cr != null);
    }

    async function _persistFavorites() {
        if (!_state) return;
        const url = _state.opts.campaignId
            ? `/api/campaign/${_state.opts.campaignId}/character/${_state.opts.characterId}/sheet-fields`
            : `/api/character/${_state.opts.characterId}/sheet-fields`;
        const payload = _state.favoritesArray.map(fav => ({ ...fav }));
        try {
            await fetch(url, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ favorite_beasts: payload }),
            });
        } catch { /* keep local state; next open will repopulate from server */ }
        if (typeof _state.opts.onFavoritesChange === 'function') {
            try { _state.opts.onFavoritesChange(payload); }
            catch { /* swallow listener errors */ }
        }
    }

    async function _toggleFavorite(slug) {
        if (!slug || !_state) return;
        const isFav = _state.favorites.has(slug);
        if (isFav) {
            // Remove from the slug-set, the order-preserving array, AND
            // the render cache so the ★ Favorites section refreshes.
            _state.favorites.delete(slug);
            _state.favoritesArray = _state.favoritesArray.filter(f => f.slug !== slug);
            _state.favoriteResults = (_state.favoriteResults || []).filter(r => r.slug !== slug);
            _renderList();
            await _persistFavorites();
            return;
        }
        // Add. Snapshot the lite shape from whichever source already has
        // it: the row the user just starred (in the current search
        // results), or the matching detail panel data. Falling back to
        // a fetch is a last resort — every starred creature SHOULD be
        // cached so we never re-fetch on subsequent opens.
        const fromResults = (_state.results || []).find(r => r.slug === slug);
        let liteShape = fromResults
            ? { slug: fromResults.slug, name: fromResults.name, cr: fromResults.cr,
                type: fromResults.type, size: fromResults.size,
                hp: fromResults.hp, ac: fromResults.ac, source: fromResults.source }
            : { slug };

        _state.favorites.add(slug);
        _state.favoritesArray = [..._state.favoritesArray, liteShape];
        if (_favHasCache(liteShape)) {
            _state.favoriteResults = [...(_state.favoriteResults || []), liteShape];
            _renderList();
        } else {
            // Don't have cache yet (e.g. user starred while Free pick was
            // on and the row's data was minimal). Render immediately for
            // visual feedback, then try to backfill.
            _renderList();
            try {
                const _cid = (_state.opts && _state.opts.campaignId) ? _state.opts.campaignId : '';
                const _cQ = _cid ? `?campaign_id=${_cid}` : '';
                const resp = await fetch(`/api/open5e/creature/${encodeURIComponent(slug)}${_cQ}`);
                if (resp.ok) {
                    const lite = await resp.json();
                    // Replace the placeholder entry in the saved array
                    // and the render cache with the fully-cached version.
                    _state.favoritesArray = _state.favoritesArray.map(f =>
                        f.slug === slug ? { ...f, ...lite } : f);
                    _state.favoriteResults = [...(_state.favoriteResults || []), lite];
                    _renderList();
                }
            } catch { /* offline — slug is recorded; render shows just the slug name */ }
        }
        await _persistFavorites();
    }

    async function _fetchFavorites() {
        if (!_state) return;
        const favs = _state.favoritesArray || [];
        // First pass: anything with a complete cache renders immediately
        // from local data — zero Open5e calls for the common case.
        _state.favoriteResults = favs.filter(_favHasCache).map(f => ({ ...f }));
        _renderList();

        // Second pass: backfill any cache-misses (legacy slug-only
        // entries from before v0.39.0). Each missing entry triggers one
        // /api/open5e/creature/{slug} call. Failures (Open5e down,
        // creature removed upstream) are tolerated — those entries just
        // render with their slug as the label.
        const misses = favs.filter(f => !_favHasCache(f));
        if (!misses.length) return;
        const _cid = (_state.opts && _state.opts.campaignId) ? _state.opts.campaignId : '';
        const _cQ = _cid ? `?campaign_id=${_cid}` : '';
        const fetched = await Promise.all(misses.map(f =>
            fetch(`/api/open5e/creature/${encodeURIComponent(f.slug)}${_cQ}`)
                .then(r => r.ok ? r.json() : null)
                .catch(() => null)
        ));
        let anyBackfilled = false;
        misses.forEach((f, idx) => {
            const lite = fetched[idx];
            if (!lite) return;
            // Merge fetched data into the slugs entry inside favoritesArray
            _state.favoritesArray = _state.favoritesArray.map(orig =>
                orig.slug === f.slug ? { ...orig, ...lite } : orig);
            anyBackfilled = true;
        });
        if (anyBackfilled) {
            _state.favoriteResults = _state.favoritesArray
                .filter(_favHasCache)
                .map(f => ({ ...f }));
            _renderList();
            // Persist so the next open is cache-hit even if Open5e is
            // unavailable later.
            await _persistFavorites();
        } else {
            // No backfill possible but still render any slug-only rows
            // so the user sees their favorites (with slug as label).
            _state.favoriteResults = _state.favoritesArray.map(f => ({
                slug: f.slug,
                name: f.name || f.slug,
                cr: f.cr ?? '?',
                type: f.type || '',
                size: f.size || '',
                hp: f.hp, ac: f.ac, source: f.source,
            }));
            _renderList();
        }
    }

    function _bindOnce() {
        const overlay = $('beast-picker-overlay');
        if (!overlay || overlay._bpBound) return;
        overlay._bpBound = true;

        overlay.addEventListener('click', (ev) => {
            // ★ Favorite toggle — must intercept before the row-select
            // handler so a star click doesn't also pick the beast.
            const favBtn = ev.target.closest('.bp-fav');
            if (favBtn) {
                ev.stopPropagation();
                _toggleFavorite(favBtn.dataset.slug);
                return;
            }
            const row = ev.target.closest('.bp-row');
            if (row) {
                overlay.querySelectorAll('.bp-row').forEach(r => r.style.background = '');
                row.style.background = 'var(--accent-bg2, rgba(99,102,241,.12))';
                _renderDetail(row.dataset.slug);
            }
        });
        $('bp-close-btn')?.addEventListener('click', _close);
        $('bp-search-btn')?.addEventListener('click', _runSearch);
        $('bp-search')?.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter') { ev.preventDefault(); _runSearch(); }
        });
        $('bp-free-pick')?.addEventListener('change', () => {
            // Re-query the server when the filter mode changes — with
            // Free pick OFF we want only beasts within the CR cap, and
            // when it's ON we want everything (Open5e ignores the
            // ``type__key`` / ``cr__lte`` params we drop). Re-rendering
            // the existing local list wouldn't broaden the set since the
            // server already trimmed it.
            _runSearch();
            if (_state?.selected) _renderDetail(_state.selected.slug);
        });
        $('bp-confirm-btn')?.addEventListener('click', _confirm);

        // Dismiss on backdrop click
        overlay.addEventListener('click', (ev) => {
            if (ev.target === overlay) _close();
        });
    }

    window.BeastPicker = {
        open(opts) {
            opts = opts || {};
            if (!opts.campaignId || !opts.characterId) {
                console.warn('BeastPicker.open: campaignId + characterId required');
                return;
            }
            const overlay = $('beast-picker-overlay');
            if (!overlay) {
                console.warn('BeastPicker: modal partial not present on this page');
                return;
            }
            _bindOnce();

            const source = opts.source === 'polymorph' ? 'polymorph' : 'wild-shape';
            const druidLv = parseInt(opts.druidLevel, 10) || 0;
            const isMoon = !!opts.isMoonDruid;
            const charLv = parseInt(opts.characterLevel, 10) || 1;
            const cap = source === 'wild-shape'
                ? _wsCrCap(druidLv, isMoon)
                : Math.max(0, charLv / 4);

            // Coerce favorites: caller can pass an array of slug strings
            // (legacy v0.38.0 shape) or objects ``{slug, name, cr, …}``
            // (v0.39.0+). Both normalize to objects so the rest of the
            // picker only deals with one shape. Entries without a usable
            // slug are dropped silently.
            const favArr = Array.isArray(opts.favorites)
                ? opts.favorites.map(f => {
                    if (typeof f === 'string') {
                        const s = f.trim();
                        return s ? { slug: s } : null;
                    }
                    if (f && typeof f === 'object' && typeof f.slug === 'string' && f.slug.trim()) {
                        return { ...f, slug: f.slug.trim() };
                    }
                    return null;
                }).filter(Boolean)
                : [];
            _state = {
                opts: { ...opts, source },
                cap,
                results: [],
                selected: null,
                lastQuery: '',
                favorites: new Set(favArr.map(f => f.slug)),
                favoritesArray: favArr,
                favoriteResults: [],
            };

            const titleEl = $('bp-title');
            if (titleEl) titleEl.textContent = source === 'polymorph'
                ? '🦌 Choose a Beast (Polymorph)'
                : '🐺 Choose a Beast (Wild Shape)';
            const capEl = $('bp-cap-text');
            if (capEl) {
                if (source === 'wild-shape') {
                    capEl.innerHTML = druidLv >= 2
                        ? `Druid Lv ${druidLv}${isMoon ? ' (Moon)' : ''} — max CR <strong>${_crStr(cap)}</strong>. Type must be Beast.`
                        : `Druid level 2+ required. Enable <strong>Free pick</strong> to override.`;
                } else {
                    capEl.innerHTML = `Polymorph: target CR ≤ <strong>${_crStr(cap)}</strong> (your level ${charLv} ÷ 4). Type must be Beast.`;
                }
            }

            $('bp-search').value = '';
            // Placeholder shown briefly until the auto-search below resolves.
            $('bp-list-panel').innerHTML = '<div style="padding:14px;color:var(--s-mute);font-size:12px;">Loading beasts…</div>';
            $('bp-detail-panel').innerHTML = '<p style="color:var(--s-mute);font-size:13px;">Select a beast to see its stats.</p>';
            $('bp-free-pick').checked = false;
            $('bp-confirm-btn').disabled = true;
            $('bp-status').textContent = '';

            overlay.style.display = '';
            setTimeout(() => $('bp-search').focus(), 50);

            // Auto-populate the list with the first page of results so the
            // player can scroll immediately without typing — mirrors the
            // Spell Browser UX. An empty search returns the API's default
            // ordering; the type/CR cap filter narrows it to beasts the
            // character can actually transform into. Favorites are
            // fetched in parallel so the ★ section appears as soon as
            // possible — independent of the search response.
            _runSearch();
            _fetchFavorites();
        },
        close: _close,
    };
})();
