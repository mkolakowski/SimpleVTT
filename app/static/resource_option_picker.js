/* resource_option_picker.js — overlay that opens when the player
 * clicks Use on a multi-option class resource (Channel Divinity in
 * v2.9.0; future: Ki / Bardic Inspiration / Sorcery Points / Lay on
 * Hands). Cross-cutting infrastructure piece (A) in
 * docs/plans/class-content-status.md.
 *
 * Usage:
 *   window.showResourceOptionPicker({
 *     title: 'Channel Divinity',
 *     subtitle: '1 / 1 use remaining — pick what to channel:',
 *     options: [
 *       { key: 'turn-undead',  label: 'Turn Undead',  desc: '...' },
 *       { key: 'preserve-life', label: 'Preserve Life', desc: '...' },
 *     ],
 *     onPick: (option) => { ... },     // option = the picked entry
 *     onCancel: () => { ... },          // optional
 *   });
 *
 * Cancel-by-overlay-click and Esc both behave as Cancel. The picker
 * removes itself before calling either callback so a follow-up
 * picker / modal can stack safely. Single-fire callbacks — clicking
 * twice fast on the same option only runs onPick once.
 */
(function () {
    if (window.showResourceOptionPicker) return;

    function _removeExisting() {
        const prev = document.getElementById('resource-option-picker');
        if (prev) prev.remove();
    }

    function _esc(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    window.showResourceOptionPicker = function (opts) {
        const o = opts || {};
        const options = Array.isArray(o.options) ? o.options : [];
        if (!options.length) {
            // Nothing to pick — best to no-op rather than show an empty
            // overlay. Callers should pre-filter so this path stays
            // unused; logging here helps catch the misuse during dev.
            console.warn('showResourceOptionPicker: empty options list');
            if (typeof o.onCancel === 'function') o.onCancel();
            return;
        }

        _removeExisting();
        const overlay = document.createElement('div');
        overlay.id = 'resource-option-picker';
        overlay.style.cssText = (
            'position:fixed;inset:0;z-index:10000;' +
            'background:rgba(6,8,16,.78);' +
            'display:flex;align-items:center;justify-content:center;padding:18px;'
        );
        const card = document.createElement('div');
        card.style.cssText = (
            'background:var(--s-card,#1a1f2c);' +
            'border:1px solid var(--s-border,#2c3344);' +
            'border-radius:8px;padding:18px 18px 14px;max-width:520px;width:100%;' +
            'max-height:calc(100vh - 80px);overflow-y:auto;' +
            'color:var(--s-fg,#e8e8e8);font-size:14px;line-height:1.45;' +
            'box-shadow:0 20px 60px rgba(0,0,0,0.6);'
        );

        const optsHtml = options.map((opt, i) => {
            const label = _esc(opt.label || opt.key || 'Option');
            const desc = _esc(opt.desc || '');
            // 44 px min height for touch targets per CLAUDE.md.
            return (
                `<button type="button" class="rop-opt" data-idx="${i}"
                    style="display:block;width:100%;text-align:left;background:rgba(255,255,255,0.04);` +
                    `border:1px solid var(--s-border,#2c3344);border-radius:6px;` +
                    `padding:10px 12px;margin-bottom:8px;cursor:pointer;` +
                    `min-height:44px;color:var(--s-fg,#e8e8e8);font:inherit;">` +
                    `<div style="font-weight:700;font-size:14px;margin-bottom:${desc ? '3px' : '0'};">${label}</div>` +
                    (desc ? `<div style="font-size:12px;color:var(--s-mute,#888);line-height:1.4;">${desc}</div>` : '') +
                `</button>`
            );
        }).join('');

        card.innerHTML = (
            `<div style="font-size:16px;font-weight:700;color:var(--s-accent,#ffa54a);margin-bottom:6px;">${_esc(o.title || 'Pick an option')}</div>` +
            (o.subtitle ? `<div style="font-size:12px;color:var(--s-mute,#888);margin-bottom:12px;">${_esc(o.subtitle)}</div>` : '<div style="margin-bottom:10px;"></div>') +
            optsHtml +
            '<div style="display:flex;justify-content:flex-end;margin-top:4px;">' +
            '<button type="button" id="rop-cancel" style="padding:8px 14px;min-height:44px;background:transparent;border:1px solid var(--s-border,#2c3344);color:var(--s-fg,#e8e8e8);border-radius:5px;cursor:pointer;">Cancel</button>' +
            '</div>'
        );
        overlay.appendChild(card);
        document.body.appendChild(overlay);

        const fired = { value: false };
        const fire = (cb, arg) => {
            if (fired.value) return;
            fired.value = true;
            overlay.remove();
            document.removeEventListener('keydown', escHandler);
            if (typeof cb === 'function') {
                try { cb(arg); } catch (e) { console.error('resource picker handler threw:', e); }
            }
        };

        card.querySelectorAll('.rop-opt').forEach(btn => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.dataset.idx, 10);
                const opt = options[idx];
                if (!opt) return;
                fire(o.onPick, opt);
            });
        });
        card.querySelector('#rop-cancel').addEventListener('click', () => fire(o.onCancel));
        overlay.addEventListener('click', (ev) => { if (ev.target === overlay) fire(o.onCancel); });
        const escHandler = (ev) => {
            if (ev.key === 'Escape') fire(o.onCancel);
        };
        document.addEventListener('keydown', escHandler);
        // Focus the first option for keyboard-friendly access.
        setTimeout(() => card.querySelector('.rop-opt')?.focus(), 30);
    };
})();
