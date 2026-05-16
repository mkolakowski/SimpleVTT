/**
 * Reusable repeatable-rows editor for class / subclass feature lists.
 *
 * Replaces the raw JSON textarea on the campaign settings page with a friendlier
 * row-based widget. Each row has Name, Level (int or blank), Description, and a
 * delete button.  An "+ Add feature" button appends a new blank row. On form
 * submit, the editor serializes its current state into a hidden
 * <input name="features_json"> so the existing server-side validator sees the
 * same JSON list shape it already parses.
 *
 * Usage from a Jinja template:
 *
 *   <div data-features-editor data-features='{{ features | tojson }}'></div>
 *   <input type="hidden" name="features_json" />
 *   <script src="/static/features_editor.js"></script>
 *
 * The script auto-initialises every [data-features-editor] in the document
 * on DOMContentLoaded and on any subsequent <details> open (so the editor
 * inside the "+ New custom subclass" collapsible card initialises lazily).
 * Each editor finds its hidden input via (1) an optional ``data-target``
 * attribute naming the input, (2) its next-element sibling if that's a
 * hidden input (the convention every current template uses), or (3) a
 * legacy form-wide lookup for ``features_json``.
 *
 * No external dependencies, no globals beyond a single
 * window.SimpleVTTFeaturesEditor namespace with init() and serializeAll().
 */
(function () {
    'use strict';

    const NS = 'SimpleVTTFeaturesEditor';

    /** Find the nearest enclosing <form> ancestor. */
    function _closestForm(el) {
        while (el && el.tagName !== 'FORM') el = el.parentElement;
        return el;
    }

    /** Locate the hidden input this editor instance should sync to. Resolution
     *  order: (1) an explicit ``data-target`` on the editor root naming the
     *  hidden input, (2) the editor's next-sibling element when it's a hidden
     *  input — the convention every current template already uses (editor div
     *  followed immediately by ``<input type="hidden" name="..._json">``),
     *  (3) the legacy form-wide ``features_json`` lookup. (2) is what makes
     *  this work for the monster form's four parallel editor instances
     *  (actions_json / special_abilities_json / reactions_json /
     *  legendary_actions_json) and the race form's traits_json, which the
     *  legacy form-wide lookup silently dropped. */
    function _findHiddenInput(root) {
        const form = _closestForm(root);
        if (!form) return null;
        const targetName = root.dataset.target;
        if (targetName) {
            return form.querySelector(`input[type="hidden"][name="${targetName}"]`);
        }
        const sib = root.nextElementSibling;
        if (sib && sib.tagName === 'INPUT' && sib.type === 'hidden') {
            return sib;
        }
        return form.querySelector('input[type="hidden"][name="features_json"]');
    }

    // 5e damage and ability lists for the action-mode dropdowns. Kept inline
    // (not imported) so this script stays dependency-free.
    const DAMAGE_TYPES = [
        '', 'acid', 'bludgeoning', 'cold', 'fire', 'force', 'lightning',
        'necrotic', 'piercing', 'poison', 'psychic', 'radiant', 'slashing', 'thunder',
    ];
    const SAVE_ABILITIES = ['', 'STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA'];

    /** Build one editor row. ``mode`` is 'feature' (default) or 'action'. The
     *  action mode appends a secondary input strip with attack_roll / to-hit
     *  bonus / damage / damage_type / save_ability / save_dc — the structured
     *  fields the renderActionButtons helper inspects to emit Attack / Save /
     *  Damage buttons on the stat-block view. Inputs are stashed on
     *  ``row._inputs`` so ``_serialize`` can read them without DOM indexing. */
    function _createRow(initial, mode) {
        initial = initial || {};
        mode = mode || 'feature';

        const row = document.createElement('div');
        row.className = 'features-editor-row';
        row.dataset.rowMode = mode;
        row.style.cssText =
            'display:grid;grid-template-columns:1fr 80px auto;gap:8px;align-items:start;' +
            'padding:8px;border:1px solid #2e3140;border-radius:6px;margin-bottom:8px;background:#1a1d24;';

        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.placeholder = mode === 'action'
            ? 'Action name (e.g. Greatclub)'
            : 'Feature name (e.g. Combat Wild Shape)';
        nameInput.maxLength = 160;
        nameInput.value = initial.name || '';
        nameInput.style.cssText = 'font-weight:600;';

        const levelInput = document.createElement('input');
        levelInput.type = 'number';
        levelInput.min = '1';
        levelInput.max = '20';
        levelInput.placeholder = 'Lvl';
        levelInput.title = 'Level the feature is gained at (blank = no level requirement)';
        levelInput.value = (initial.level != null) ? String(initial.level) : '';

        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'features-editor-delete';
        deleteBtn.textContent = '✕';
        deleteBtn.title = 'Remove this entry';
        deleteBtn.style.cssText = 'padding:4px 10px;color:#c66;background:#2a1a1a;border:1px solid #4a2a2a;border-radius:4px;cursor:pointer;';
        deleteBtn.addEventListener('click', () => row.remove());

        const descTa = document.createElement('textarea');
        descTa.placeholder = 'Description (markdown allowed; rolls + level refs are auto-detected on display)';
        descTa.rows = 3;
        descTa.maxLength = 4000;
        descTa.value = initial.desc || '';
        descTa.style.cssText = 'grid-column:1 / span 3;font-family:inherit;font-size:13px;';

        row.appendChild(nameInput);
        row.appendChild(levelInput);
        row.appendChild(deleteBtn);
        row.appendChild(descTa);

        const inputs = { nameInput, levelInput, descTa };

        if (mode === 'action') {
            const atkRow = document.createElement('div');
            atkRow.className = 'features-editor-attack-row';
            atkRow.style.cssText =
                'grid-column:1 / span 3;display:grid;' +
                'grid-template-columns:auto 80px 110px 130px 90px 70px 80px;gap:6px;align-items:end;' +
                'padding:8px 0 0 0;margin-top:4px;border-top:1px dashed #2e3140;font-size:11px;';

            const attackWrap = document.createElement('label');
            attackWrap.style.cssText = 'display:flex;align-items:center;gap:4px;color:var(--fg-mute);';
            const attackRollCb = document.createElement('input');
            attackRollCb.type = 'checkbox';
            attackRollCb.checked = !!initial.attack_roll;
            attackRollCb.title = 'Render an 🎯 Attack Roll button on the stat block';
            attackWrap.appendChild(attackRollCb);
            attackWrap.appendChild(document.createTextNode('Attack'));

            const attackBonusInput = _mkLabeledInput('To-hit', '+5', initial.attack_bonus || '');
            attackBonusInput.input.maxLength = 6;
            attackBonusInput.input.title = 'Bonus added to the 1d20 attack roll. e.g. "+5", "-1". Leave blank for raw 1d20.';

            const damageInput = _mkLabeledInput('Damage', '1d8+3', initial.damage || '');
            damageInput.input.maxLength = 40;
            damageInput.input.title = 'Damage dice expression. e.g. "1d8+3", "2d6". Empty = no damage button.';

            const damageTypeSel = _mkLabeledSelect('Damage type', DAMAGE_TYPES, initial.damage_type || '');

            const saveAbilitySel = _mkLabeledSelect('Save', SAVE_ABILITIES, (initial.save_ability || '').toUpperCase());
            saveAbilitySel.select.title = 'If set, renders a "📋 Prompt save" button instead of (or alongside) an attack.';

            const saveDcInput = _mkLabeledInput('DC', '15', initial.save_dc ? String(initial.save_dc) : '');
            saveDcInput.input.type = 'number';
            saveDcInput.input.min = '1';
            saveDcInput.input.max = '40';

            // v2.3.41: Charges/use — surfaces the schema's ``charges_max``
            // field added in v2.3.40. A positive integer renders the
            // ``cur/max`` pill + ↻ recharge button in the GM init tracker
            // and disables the strike-button trio when spent. Blank/0
            // means unlimited (the default for non-limited actions).
            const chargesInput = _mkLabeledInput('Charges', '0', initial.charges_max ? String(initial.charges_max) : '');
            chargesInput.input.type = 'number';
            chargesInput.input.min = '0';
            chargesInput.input.max = '99';
            chargesInput.input.title = 'Uses per encounter (e.g. 1 for "Recharge 5-6" or "1/day"). Blank or 0 = unlimited.';

            atkRow.appendChild(attackWrap);
            atkRow.appendChild(attackBonusInput.wrap);
            atkRow.appendChild(damageInput.wrap);
            atkRow.appendChild(damageTypeSel.wrap);
            atkRow.appendChild(saveAbilitySel.wrap);
            atkRow.appendChild(saveDcInput.wrap);
            atkRow.appendChild(chargesInput.wrap);
            row.appendChild(atkRow);

            inputs.attackRollCb = attackRollCb;
            inputs.attackBonusInput = attackBonusInput.input;
            inputs.damageInput = damageInput.input;
            inputs.damageTypeSel = damageTypeSel.select;
            inputs.saveAbilitySel = saveAbilitySel.select;
            inputs.saveDcInput = saveDcInput.input;
            inputs.chargesInput = chargesInput.input;
        }

        row._inputs = inputs;
        return row;
    }

    /** Helper: text-input column with a small label above it. Returns the
     *  wrapper element and the inner ``<input>`` so callers can tweak attrs. */
    function _mkLabeledInput(label, placeholder, value) {
        const wrap = document.createElement('label');
        wrap.style.cssText = 'display:flex;flex-direction:column;gap:2px;color:var(--fg-mute);';
        const span = document.createElement('span');
        span.textContent = label;
        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = placeholder;
        input.value = value;
        input.style.cssText = 'min-height:32px;padding:4px 6px;font-size:12px;';
        wrap.appendChild(span);
        wrap.appendChild(input);
        return { wrap, input };
    }

    /** Helper: select column with a small label above it. ``options`` is a
     *  list of strings; empty string renders as a blank option. */
    function _mkLabeledSelect(label, options, value) {
        const wrap = document.createElement('label');
        wrap.style.cssText = 'display:flex;flex-direction:column;gap:2px;color:var(--fg-mute);';
        const span = document.createElement('span');
        span.textContent = label;
        const select = document.createElement('select');
        select.style.cssText = 'min-height:32px;padding:4px 6px;font-size:12px;';
        options.forEach(opt => {
            const o = document.createElement('option');
            o.value = opt;
            o.textContent = opt || '—';
            if (opt === value) o.selected = true;
            select.appendChild(o);
        });
        wrap.appendChild(span);
        wrap.appendChild(select);
        return { wrap, select };
    }

    /** Serialize the rows in ``root`` into a JSON string. Drops rows whose
     *  name AND desc are both empty. Returns "[]" for an editor with no
     *  meaningful rows so the server normalises to "no features". */
    function _serialize(root) {
        const rows = root.querySelectorAll('.features-editor-row');
        const out = [];
        rows.forEach(row => {
            const inputs = row._inputs;
            if (!inputs) return;
            const name = (inputs.nameInput.value || '').trim();
            const desc = (inputs.descTa.value || '').trim();
            if (!name && !desc) return;
            const rec = { name, desc };
            const lvlTrim = (inputs.levelInput.value || '').toString().trim();
            if (lvlTrim === '') {
                rec.level = null;
            } else {
                const n = parseInt(lvlTrim, 10);
                rec.level = Number.isFinite(n) ? n : null;
            }
            // Attack-mode extras. Only include fields the GM actually set, so
            // we don't bloat the JSON with empty defaults. The Pydantic model
            // applies the defaults on the server side.
            if (row.dataset.rowMode === 'action' && inputs.attackRollCb) {
                if (inputs.attackRollCb.checked) rec.attack_roll = true;
                const atkBonus = (inputs.attackBonusInput.value || '').trim();
                if (atkBonus) rec.attack_bonus = atkBonus;
                const dmg = (inputs.damageInput.value || '').trim();
                if (dmg) rec.damage = dmg;
                const dmgType = (inputs.damageTypeSel.value || '').trim();
                if (dmgType) rec.damage_type = dmgType;
                const saveAb = (inputs.saveAbilitySel.value || '').trim();
                if (saveAb) rec.save_ability = saveAb.toLowerCase();
                const saveDcRaw = (inputs.saveDcInput.value || '').toString().trim();
                if (saveDcRaw) {
                    const n = parseInt(saveDcRaw, 10);
                    if (Number.isFinite(n) && n > 0) rec.save_dc = n;
                }
                // v2.3.41: charges_max only emitted when > 0 so the JSON
                // stays terse for the (vast majority) unlimited-use case.
                const chargesRaw = (inputs.chargesInput.value || '').toString().trim();
                if (chargesRaw) {
                    const n = parseInt(chargesRaw, 10);
                    if (Number.isFinite(n) && n > 0) rec.charges_max = n;
                }
            }
            out.push(rec);
        });
        return JSON.stringify(out);
    }

    function init(root) {
        if (root.dataset.featuresEditorInit === '1') return;
        root.dataset.featuresEditorInit = '1';

        let initial = [];
        try {
            initial = JSON.parse(root.dataset.features || '[]');
        } catch (e) {
            initial = [];
        }
        if (!Array.isArray(initial)) initial = [];

        const mode = root.dataset.rowMode === 'action' ? 'action' : 'feature';

        const rowsContainer = document.createElement('div');
        rowsContainer.className = 'features-editor-rows';
        root.appendChild(rowsContainer);

        initial.forEach(f => rowsContainer.appendChild(_createRow(f, mode)));

        const addBtn = document.createElement('button');
        addBtn.type = 'button';
        addBtn.className = 'features-editor-add';
        addBtn.textContent = mode === 'action' ? '+ Add action' : '+ Add feature';
        addBtn.style.cssText =
            'padding:6px 14px;background:#252c45;color:#c8cce8;border:1px solid #3a4060;' +
            'border-radius:4px;cursor:pointer;font-size:12px;';
        addBtn.addEventListener('click', () => {
            const row = _createRow({}, mode);
            rowsContainer.appendChild(row);
            row.querySelector('input[type="text"]').focus();
        });
        root.appendChild(addBtn);

        // Hook the parent form's submit to sync the hidden input. Multiple
        // editors in the same form each install a sync handler — that's
        // fine, they target different hidden inputs (or the same one twice
        // with the same result; idempotent).
        const form = _closestForm(root);
        if (form && !form.dataset.featuresEditorSubmitBound) {
            form.dataset.featuresEditorSubmitBound = '1';
            form.addEventListener('submit', () => {
                form.querySelectorAll('[data-features-editor]').forEach(ed => {
                    const hidden = _findHiddenInput(ed);
                    if (hidden) hidden.value = _serialize(ed);
                });
            });
        }
    }

    function initAll(scope) {
        const root = scope || document;
        root.querySelectorAll('[data-features-editor]').forEach(init);
    }

    // Lazy init: when a <details> opens, initialise any editors inside it.
    // The campaign settings page wraps each subclass form in a <details>
    // that's closed by default, so we can't rely on a single DOMContentLoaded
    // pass for editors inside collapsed cards.
    document.addEventListener('toggle', e => {
        if (e.target.tagName === 'DETAILS' && e.target.open) {
            initAll(e.target);
        }
    }, true);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => initAll());
    } else {
        initAll();
    }

    window[NS] = { init, initAll };
})();
