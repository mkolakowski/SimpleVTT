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
 * Each editor finds its sibling hidden input by name "features_json".
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

    /** Find the hidden features_json input inside the same form as ``root``. */
    function _findHiddenInput(root) {
        const form = _closestForm(root);
        return form ? form.querySelector('input[type="hidden"][name="features_json"]') : null;
    }

    /** Coerce a raw row reading to a clean object suitable for the server. */
    function _normalizeRow(name, level, desc) {
        const out = { name: (name || '').trim() };
        const lvlTrim = (level || '').toString().trim();
        if (lvlTrim === '') {
            out.level = null;
        } else {
            const n = parseInt(lvlTrim, 10);
            out.level = Number.isFinite(n) ? n : null;
        }
        out.desc = (desc || '').trim();
        return out;
    }

    function _createRow(initial) {
        const row = document.createElement('div');
        row.className = 'features-editor-row';
        row.style.cssText =
            'display:grid;grid-template-columns:1fr 80px auto;gap:8px;align-items:start;' +
            'padding:8px;border:1px solid #2e3140;border-radius:6px;margin-bottom:8px;background:#1a1d24;';

        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.placeholder = 'Feature name (e.g. Combat Wild Shape)';
        nameInput.maxLength = 160;
        nameInput.value = (initial && initial.name) || '';
        nameInput.style.cssText = 'font-weight:600;';

        const levelInput = document.createElement('input');
        levelInput.type = 'number';
        levelInput.min = '1';
        levelInput.max = '20';
        levelInput.placeholder = 'Lvl';
        levelInput.title = 'Level the feature is gained at (blank = no level requirement)';
        levelInput.value = (initial && initial.level != null) ? String(initial.level) : '';

        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'features-editor-delete';
        deleteBtn.textContent = '✕';
        deleteBtn.title = 'Remove this feature';
        deleteBtn.style.cssText = 'padding:4px 10px;color:#c66;background:#2a1a1a;border:1px solid #4a2a2a;border-radius:4px;cursor:pointer;';
        deleteBtn.addEventListener('click', () => {
            row.remove();
        });

        const descTa = document.createElement('textarea');
        descTa.placeholder = 'Description (markdown allowed; rolls + level refs are auto-detected on display)';
        descTa.rows = 3;
        descTa.maxLength = 4000;
        descTa.value = (initial && initial.desc) || '';
        descTa.style.cssText = 'grid-column:1 / span 3;font-family:inherit;font-size:13px;';

        row.appendChild(nameInput);
        row.appendChild(levelInput);
        row.appendChild(deleteBtn);
        row.appendChild(descTa);

        return row;
    }

    /** Serialize the rows in ``root`` into a JSON string. Drops rows whose
     *  name AND desc are both empty. Returns "[]" for an editor with no
     *  meaningful rows so the server normalises to "no features". */
    function _serialize(root) {
        const rows = root.querySelectorAll('.features-editor-row');
        const out = [];
        rows.forEach(row => {
            const [nameInput, levelInput, , descTa] = row.children;
            const rec = _normalizeRow(nameInput.value, levelInput.value, descTa.value);
            // Drop rows the GM started filling out then abandoned.
            if (!rec.name && !rec.desc) return;
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

        const rowsContainer = document.createElement('div');
        rowsContainer.className = 'features-editor-rows';
        root.appendChild(rowsContainer);

        initial.forEach(f => rowsContainer.appendChild(_createRow(f)));

        const addBtn = document.createElement('button');
        addBtn.type = 'button';
        addBtn.className = 'features-editor-add';
        addBtn.textContent = '+ Add feature';
        addBtn.style.cssText =
            'padding:6px 14px;background:#252c45;color:#c8cce8;border:1px solid #3a4060;' +
            'border-radius:4px;cursor:pointer;font-size:12px;';
        addBtn.addEventListener('click', () => {
            const row = _createRow();
            rowsContainer.appendChild(row);
            // Focus the new row's name input so the GM can start typing immediately.
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
