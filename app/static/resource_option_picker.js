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

    /* v2.10.0: showAmountPicker({title, subtitle, min, max, default, onPick, onCancel})
     *
     * Numeric pick gate — used by Lay on Hands ("how much of your pool
     * to spend") and any future feature that needs a 1..N number from
     * the player (e.g. Bardic Inspiration with multiple die sizes, Ki
     * spend variants). Renders a slider + linked numeric input;
     * Confirm fires onPick(value); Cancel fires onCancel.
     */
    window.showAmountPicker = function (opts) {
        const o = opts || {};
        const min = Math.max(0, Number(o.min) || 1);
        const max = Math.max(min, Number(o.max) || min);
        const initial = Math.min(max, Math.max(min, Number(o.default) || min));

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
            'border-radius:8px;padding:18px;max-width:420px;width:100%;' +
            'color:var(--s-fg,#e8e8e8);font-size:14px;line-height:1.45;' +
            'box-shadow:0 20px 60px rgba(0,0,0,0.6);'
        );

        card.innerHTML = (
            `<div style="font-size:16px;font-weight:700;color:var(--s-accent,#ffa54a);margin-bottom:6px;">${_esc(o.title || 'Pick an amount')}</div>` +
            (o.subtitle ? `<div style="font-size:12px;color:var(--s-mute,#888);margin-bottom:14px;">${_esc(o.subtitle)}</div>` : '<div style="margin-bottom:10px;"></div>') +
            '<div style="display:flex;align-items:center;gap:12px;margin-bottom:18px;">' +
            `<input type="range" id="amt-slider" min="${min}" max="${max}" value="${initial}" style="flex:1;">` +
            `<input type="number" id="amt-input" min="${min}" max="${max}" value="${initial}" ` +
            `style="width:72px;font-size:14px;text-align:center;min-height:44px;padding:4px 6px;background:var(--s-input,#0e1119);border:1px solid var(--s-border,#2c3344);color:var(--s-fg,#e8e8e8);border-radius:5px;">` +
            `<span style="font-size:11px;color:var(--s-mute,#888);">/ ${max}</span>` +
            '</div>' +
            '<div style="display:flex;gap:8px;justify-content:flex-end;">' +
            '<button type="button" id="amt-cancel" style="padding:8px 14px;min-height:44px;background:transparent;border:1px solid var(--s-border,#2c3344);color:var(--s-fg,#e8e8e8);border-radius:5px;cursor:pointer;">Cancel</button>' +
            '<button type="button" id="amt-confirm" style="padding:8px 14px;min-height:44px;background:var(--s-accent,#ffa54a);border:1px solid var(--s-accent,#ffa54a);color:#1a1f2c;font-weight:700;border-radius:5px;cursor:pointer;">Continue →</button>' +
            '</div>'
        );
        overlay.appendChild(card);
        document.body.appendChild(overlay);

        const slider = card.querySelector('#amt-slider');
        const input = card.querySelector('#amt-input');
        const sync = (src) => {
            let v = parseInt((src === slider ? slider.value : input.value), 10);
            if (!Number.isFinite(v)) v = min;
            v = Math.max(min, Math.min(max, v));
            slider.value = String(v);
            input.value = String(v);
        };
        slider.addEventListener('input', () => sync(slider));
        input.addEventListener('input', () => sync(input));

        const fired = { value: false };
        const fire = (cb, arg) => {
            if (fired.value) return;
            fired.value = true;
            overlay.remove();
            document.removeEventListener('keydown', escHandler);
            if (typeof cb === 'function') {
                try { cb(arg); } catch (e) { console.error('amount picker handler threw:', e); }
            }
        };
        card.querySelector('#amt-cancel').addEventListener('click', () => fire(o.onCancel));
        card.querySelector('#amt-confirm').addEventListener('click', () => {
            sync(input);
            fire(o.onPick, parseInt(input.value, 10));
        });
        input.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter') {
                sync(input);
                fire(o.onPick, parseInt(input.value, 10));
            }
        });
        overlay.addEventListener('click', (ev) => { if (ev.target === overlay) fire(o.onCancel); });
        const escHandler = (ev) => { if (ev.key === 'Escape') fire(o.onCancel); };
        document.addEventListener('keydown', escHandler);

        setTimeout(() => input?.focus(), 30);
    };

    /* v2.10.0: showTargetPicker({title, subtitle, candidates, onPick, onCancel})
     *
     * Pick one creature from a list. Each ``candidates`` entry:
     *   { id, name, color?, hp_current?, hp_max?, portrait_url?, badge? }
     *
     * Used by Lay on Hands (party + self), planned for Bardic
     * Inspiration (party - self), and any future "pick a target"
     * feature. Visual treatment: a row per candidate showing portrait
     * (or color-dot fallback) + name + HP bar. Click → onPick(entry).
     */
    window.showTargetPicker = function (opts) {
        const o = opts || {};
        const candidates = Array.isArray(o.candidates) ? o.candidates : [];
        if (!candidates.length) {
            console.warn('showTargetPicker: empty candidates list');
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
            'border-radius:8px;padding:18px;max-width:480px;width:100%;' +
            'max-height:calc(100vh - 80px);overflow-y:auto;' +
            'color:var(--s-fg,#e8e8e8);font-size:14px;line-height:1.45;' +
            'box-shadow:0 20px 60px rgba(0,0,0,0.6);'
        );

        const rowsHtml = candidates.map((c, i) => {
            const name = _esc(c.name || 'Target');
            const color = c.color || '#6cb4ff';
            const badge = c.badge ? `<span style="font-size:10px;color:var(--s-mute,#888);margin-left:6px;">${_esc(c.badge)}</span>` : '';
            const hpFrag = (typeof c.hp_current === 'number' && typeof c.hp_max === 'number' && c.hp_max > 0)
                ? `<span style="font-size:11px;color:var(--s-mute,#888);margin-left:auto;">${c.hp_current} / ${c.hp_max} HP</span>`
                : '';
            const avatar = c.portrait_url
                ? `<img src="${_esc(c.portrait_url)}" alt="" style="width:32px;height:32px;border-radius:50%;object-fit:cover;flex-shrink:0;border:2px solid ${_esc(color)};">`
                : `<span style="width:32px;height:32px;border-radius:50%;background:${_esc(color)};flex-shrink:0;display:inline-block;"></span>`;
            return (
                `<button type="button" class="tgt-opt" data-idx="${i}"
                    style="display:flex;align-items:center;gap:10px;width:100%;text-align:left;background:rgba(255,255,255,0.04);
                    border:1px solid var(--s-border,#2c3344);border-radius:6px;
                    padding:8px 12px;margin-bottom:6px;cursor:pointer;
                    min-height:44px;color:var(--s-fg,#e8e8e8);font:inherit;">` +
                    avatar +
                    `<span style="font-weight:700;font-size:14px;">${name}</span>${badge}${hpFrag}` +
                '</button>'
            );
        }).join('');

        card.innerHTML = (
            `<div style="font-size:16px;font-weight:700;color:var(--s-accent,#ffa54a);margin-bottom:6px;">${_esc(o.title || 'Pick a target')}</div>` +
            (o.subtitle ? `<div style="font-size:12px;color:var(--s-mute,#888);margin-bottom:12px;">${_esc(o.subtitle)}</div>` : '<div style="margin-bottom:10px;"></div>') +
            rowsHtml +
            '<div style="display:flex;justify-content:flex-end;margin-top:6px;">' +
            '<button type="button" id="tgt-cancel" style="padding:8px 14px;min-height:44px;background:transparent;border:1px solid var(--s-border,#2c3344);color:var(--s-fg,#e8e8e8);border-radius:5px;cursor:pointer;">Cancel</button>' +
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
                try { cb(arg); } catch (e) { console.error('target picker handler threw:', e); }
            }
        };
        card.querySelectorAll('.tgt-opt').forEach(btn => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.dataset.idx, 10);
                const c = candidates[idx];
                if (!c) return;
                fire(o.onPick, c);
            });
        });
        card.querySelector('#tgt-cancel').addEventListener('click', () => fire(o.onCancel));
        overlay.addEventListener('click', (ev) => { if (ev.target === overlay) fire(o.onCancel); });
        const escHandler = (ev) => { if (ev.key === 'Escape') fire(o.onCancel); };
        document.addEventListener('keydown', escHandler);

        setTimeout(() => card.querySelector('.tgt-opt')?.focus(), 30);
    };
})();
