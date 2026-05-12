/**
 * Class-resources editor for homebrew custom-class forms.
 *
 * Repeatable rows for "per-rest counter" recipes (Channel Divinity, Bardic
 * Inspiration, Ki, Action Surge, …). Each row carries a name, the level
 * the resource becomes available, the "max kind" + the supporting field
 * for that kind (a number, an ability letter, or a level→count table), a
 * reset cadence, and an optional description. Empty rows are dropped on
 * save. Auto-inits every [data-resources-editor] on DOMContentLoaded and
 * on <details> open, syncs to a hidden <input name="resources_json"> on
 * form submit.
 *
 * Max kinds:
 *   static       — fixed count (e.g. Action Surge = 1, then 2 at lv17 → use level_table instead)
 *   ability_mod  — equal to a chosen ability modifier (e.g. Bardic Inspiration = CHA mod)
 *   proficiency  — equal to the proficiency bonus
 *   level_table  — keyed by class level (e.g. Channel Divinity = 1 at lv2, 2 at lv6, 3 at lv18)
 *
 * The server-side parser tolerates the same JSON shape this widget emits,
 * including either a numeric or stringified level-table key.
 */
(function () {
    'use strict';

    const NS = 'SimpleVTTResourcesEditor';
    const ABILITY_OPTS = ['str', 'dex', 'con', 'int', 'wis', 'cha'];
    const RESET_OPTS = ['short', 'long', 'none'];

    function _closestForm(el) {
        while (el && el.tagName !== 'FORM') el = el.parentElement;
        return el;
    }

    function _findHiddenInput(root) {
        const form = _closestForm(root);
        return form ? form.querySelector('input[type="hidden"][name="resources_json"]') : null;
    }

    function _option(value, label, selected) {
        const o = document.createElement('option');
        o.value = value;
        o.textContent = label;
        if (selected) o.selected = true;
        return o;
    }

    function _renderConditional(row, kind, initial) {
        const cond = row.querySelector('.res-conditional');
        cond.innerHTML = '';
        if (kind === 'static') {
            const lbl = document.createElement('label');
            lbl.style.cssText = 'display:flex;flex-direction:column;gap:2px;font-size:11px;';
            lbl.innerHTML = '<span style="color:var(--fg-mute);">Max uses</span>';
            const inp = document.createElement('input');
            inp.type = 'number';
            inp.className = 'res-static';
            inp.min = '0';
            inp.max = '999';
            inp.value = (initial && initial.max_static != null) ? String(initial.max_static) : '1';
            lbl.appendChild(inp);
            cond.appendChild(lbl);
        } else if (kind === 'ability_mod') {
            const lbl = document.createElement('label');
            lbl.style.cssText = 'display:flex;flex-direction:column;gap:2px;font-size:11px;';
            lbl.innerHTML = '<span style="color:var(--fg-mute);">Ability</span>';
            const sel = document.createElement('select');
            sel.className = 'res-ability';
            ABILITY_OPTS.forEach(ab => sel.appendChild(_option(ab, ab.toUpperCase(),
                initial && initial.max_ability === ab)));
            lbl.appendChild(sel);
            cond.appendChild(lbl);
        } else if (kind === 'proficiency') {
            const note = document.createElement('span');
            note.style.cssText = 'font-size:11px;color:var(--fg-mute);font-style:italic;align-self:center;';
            note.textContent = '= proficiency bonus';
            cond.appendChild(note);
        } else if (kind === 'level_table') {
            const wrap = document.createElement('div');
            wrap.style.cssText = 'display:flex;flex-direction:column;gap:4px;';
            const label = document.createElement('span');
            label.style.cssText = 'font-size:11px;color:var(--fg-mute);';
            label.textContent = 'Level → count thresholds';
            wrap.appendChild(label);
            const rowsWrap = document.createElement('div');
            rowsWrap.className = 'res-levels';
            rowsWrap.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px;';
            wrap.appendChild(rowsWrap);

            const addPair = (lvl, cnt) => {
                const pair = document.createElement('div');
                pair.className = 'res-level-pair';
                pair.style.cssText = 'display:inline-flex;gap:2px;align-items:center;background:#1a1d24;border:1px solid #2e3140;border-radius:4px;padding:2px 4px;';
                const lvlInp = document.createElement('input');
                lvlInp.type = 'number';
                lvlInp.min = '1';
                lvlInp.max = '20';
                lvlInp.placeholder = 'lv';
                lvlInp.className = 'res-level-key';
                lvlInp.style.cssText = 'width:42px;font-size:11px;text-align:center;';
                if (lvl != null) lvlInp.value = String(lvl);
                const cntInp = document.createElement('input');
                cntInp.type = 'number';
                cntInp.min = '0';
                cntInp.max = '999';
                cntInp.placeholder = 'n';
                cntInp.className = 'res-level-val';
                cntInp.style.cssText = 'width:42px;font-size:11px;text-align:center;';
                if (cnt != null) cntInp.value = String(cnt);
                const rm = document.createElement('button');
                rm.type = 'button';
                rm.textContent = '✕';
                rm.style.cssText = 'background:none;border:none;color:#c66;font-size:10px;cursor:pointer;padding:0;';
                rm.addEventListener('click', () => pair.remove());
                pair.appendChild(lvlInp);
                pair.appendChild(document.createTextNode(' → '));
                pair.appendChild(cntInp);
                pair.appendChild(rm);
                rowsWrap.appendChild(pair);
            };

            const initialTable = (initial && initial.max_table) || {};
            const keys = Object.keys(initialTable).map(k => parseInt(k, 10)).sort((a, b) => a - b);
            if (keys.length === 0) {
                addPair(1, 1);
            } else {
                keys.forEach(k => addPair(k, initialTable[String(k)]));
            }
            const addBtn = document.createElement('button');
            addBtn.type = 'button';
            addBtn.textContent = '+ level';
            addBtn.style.cssText = 'background:#252c45;border:1px solid #3a4060;color:#c8cce8;font-size:11px;padding:2px 8px;border-radius:3px;cursor:pointer;';
            addBtn.addEventListener('click', () => addPair(null, null));
            wrap.appendChild(addBtn);

            cond.appendChild(wrap);
        }
    }

    function _createRow(initial) {
        const row = document.createElement('div');
        row.className = 'resources-editor-row';
        row.style.cssText =
            'display:grid;grid-template-columns:1fr 70px 130px 1fr 90px auto;gap:6px;align-items:start;' +
            'padding:8px;border:1px solid #2e3140;border-radius:6px;margin-bottom:8px;background:#1a1d24;';

        // Name
        const nameLbl = document.createElement('label');
        nameLbl.style.cssText = 'display:flex;flex-direction:column;gap:2px;font-size:11px;';
        nameLbl.innerHTML = '<span style="color:var(--fg-mute);">Name</span>';
        const nameInp = document.createElement('input');
        nameInp.type = 'text';
        nameInp.className = 'res-name';
        nameInp.placeholder = 'Channel Divinity';
        nameInp.maxLength = 120;
        nameInp.style.cssText = 'font-weight:600;';
        if (initial && initial.name) nameInp.value = initial.name;
        nameLbl.appendChild(nameInp);
        row.appendChild(nameLbl);

        // Min level
        const lvlLbl = document.createElement('label');
        lvlLbl.style.cssText = 'display:flex;flex-direction:column;gap:2px;font-size:11px;';
        lvlLbl.innerHTML = '<span style="color:var(--fg-mute);">Min level</span>';
        const lvlInp = document.createElement('input');
        lvlInp.type = 'number';
        lvlInp.className = 'res-min-level';
        lvlInp.min = '1';
        lvlInp.max = '20';
        lvlInp.value = (initial && initial.min_level != null) ? String(initial.min_level) : '1';
        lvlInp.style.cssText = 'text-align:center;';
        lvlLbl.appendChild(lvlInp);
        row.appendChild(lvlLbl);

        // Kind
        const kindLbl = document.createElement('label');
        kindLbl.style.cssText = 'display:flex;flex-direction:column;gap:2px;font-size:11px;';
        kindLbl.innerHTML = '<span style="color:var(--fg-mute);">Max kind</span>';
        const kindSel = document.createElement('select');
        kindSel.className = 'res-kind';
        const kindOpts = [
            ['static', 'Fixed value'],
            ['ability_mod', 'Ability modifier'],
            ['proficiency', 'Proficiency bonus'],
            ['level_table', 'Per-level table'],
        ];
        const startKind = (initial && initial.max_kind) || 'static';
        kindOpts.forEach(([v, l]) => kindSel.appendChild(_option(v, l, v === startKind)));
        kindLbl.appendChild(kindSel);
        row.appendChild(kindLbl);

        // Conditional (per-kind field)
        const cond = document.createElement('div');
        cond.className = 'res-conditional';
        cond.style.cssText = 'display:flex;align-items:flex-end;';
        row.appendChild(cond);

        // Reset
        const resetLbl = document.createElement('label');
        resetLbl.style.cssText = 'display:flex;flex-direction:column;gap:2px;font-size:11px;';
        resetLbl.innerHTML = '<span style="color:var(--fg-mute);">Reset</span>';
        const resetSel = document.createElement('select');
        resetSel.className = 'res-reset';
        const startReset = (initial && initial.reset) || 'long';
        RESET_OPTS.forEach(r => resetSel.appendChild(_option(r, r, r === startReset)));
        resetLbl.appendChild(resetSel);
        row.appendChild(resetLbl);

        // Delete
        const del = document.createElement('button');
        del.type = 'button';
        del.textContent = '✕';
        del.title = 'Remove this resource';
        del.style.cssText = 'padding:4px 10px;color:#c66;background:#2a1a1a;border:1px solid #4a2a2a;border-radius:4px;cursor:pointer;align-self:end;';
        del.addEventListener('click', () => row.remove());
        row.appendChild(del);

        // Desc (full-width row 2)
        const descTa = document.createElement('textarea');
        descTa.className = 'res-desc';
        descTa.placeholder = 'Description (short, shown on hover in the resource panel)';
        descTa.rows = 2;
        descTa.maxLength = 1000;
        descTa.style.cssText = 'grid-column:1 / span 6;font-family:inherit;font-size:12px;';
        if (initial && initial.desc) descTa.value = initial.desc;
        row.appendChild(descTa);

        _renderConditional(row, startKind, initial);
        kindSel.addEventListener('change', () => _renderConditional(row, kindSel.value, null));

        return row;
    }

    function _serializeRow(row) {
        const name = row.querySelector('.res-name').value.trim();
        if (!name) return null;
        const min_level = parseInt(row.querySelector('.res-min-level').value, 10) || 1;
        const max_kind = row.querySelector('.res-kind').value;
        const reset = row.querySelector('.res-reset').value;
        const desc = row.querySelector('.res-desc').value.trim();
        const rec = { name: name, min_level: min_level, max_kind: max_kind, reset: reset, desc: desc };
        if (max_kind === 'static') {
            const s = row.querySelector('.res-static');
            rec.max_static = s ? (parseInt(s.value, 10) || 0) : 0;
        } else if (max_kind === 'ability_mod') {
            const a = row.querySelector('.res-ability');
            rec.max_ability = a ? a.value : 'cha';
        } else if (max_kind === 'level_table') {
            const tbl = {};
            row.querySelectorAll('.res-level-pair').forEach(pair => {
                const k = pair.querySelector('.res-level-key').value.trim();
                const v = pair.querySelector('.res-level-val').value.trim();
                if (k === '' || v === '') return;
                const ki = parseInt(k, 10);
                const vi = parseInt(v, 10);
                if (Number.isFinite(ki) && Number.isFinite(vi) && ki >= 1 && ki <= 20) {
                    tbl[String(ki)] = vi;
                }
            });
            rec.max_table = tbl;
        }
        return rec;
    }

    function _serialize(root) {
        const rows = root.querySelectorAll('.resources-editor-row');
        const out = [];
        rows.forEach(r => {
            const rec = _serializeRow(r);
            if (rec) out.push(rec);
        });
        return JSON.stringify(out);
    }

    function init(root) {
        if (root.dataset.resourcesEditorInit === '1') return;
        root.dataset.resourcesEditorInit = '1';

        let initial = [];
        try { initial = JSON.parse(root.dataset.resources || '[]'); } catch (e) {}
        if (!Array.isArray(initial)) initial = [];

        const rowsContainer = document.createElement('div');
        rowsContainer.className = 'resources-editor-rows';
        root.appendChild(rowsContainer);
        initial.forEach(r => rowsContainer.appendChild(_createRow(r)));

        const addBtn = document.createElement('button');
        addBtn.type = 'button';
        addBtn.textContent = '+ Add resource';
        addBtn.style.cssText =
            'padding:6px 14px;background:#252c45;color:#c8cce8;border:1px solid #3a4060;' +
            'border-radius:4px;cursor:pointer;font-size:12px;';
        addBtn.addEventListener('click', () => {
            const row = _createRow();
            rowsContainer.appendChild(row);
            row.querySelector('.res-name').focus();
        });
        root.appendChild(addBtn);

        const form = _closestForm(root);
        if (form && !form.dataset.resourcesEditorSubmitBound) {
            form.dataset.resourcesEditorSubmitBound = '1';
            form.addEventListener('submit', () => {
                form.querySelectorAll('[data-resources-editor]').forEach(ed => {
                    const hidden = _findHiddenInput(ed);
                    if (hidden) hidden.value = _serialize(ed);
                });
            });
        }
    }

    function initAll(scope) {
        const root = scope || document;
        root.querySelectorAll('[data-resources-editor]').forEach(init);
    }

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
