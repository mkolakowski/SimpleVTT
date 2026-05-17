/* economy_messaging.js — shared Layer B confirm modal for the
 * action-economy over-budget flow (Phase 4 in
 * docs/plans/class-content-status.md section E).
 *
 * Used by:
 *   • app/templates/sheet_dnd5e.html — .atk-strike / .sp-cast / .cf-use
 *     click handlers wrap their fetch call; on a 409 over_budget response
 *     they call window.showOverBudgetModal({...}) and re-fire with
 *     override:true on Confirm.
 *   • app/templates/tabletop.html — .mini-strike-btn / .mini-cast-btn
 *     handlers do the same for the GM init tracker's mini-sheet panel.
 *
 * The modal is intentionally lightweight: one centered card, two
 * buttons, no CSS framework dependency. Cancel = close, Confirm =
 * call the onConfirm callback. Multiple opens replace the existing
 * modal (no stacking — there's only ever one over-budget question on
 * screen at a time).
 *
 * GM bypass: the server skips the 409 entirely for GM clicks, so the
 * modal never appears for them. This helper has no GM-awareness on
 * its own; that lives in the gating logic upstream.
 */

(function () {
    if (window.showOverBudgetModal) return;  // load-once guard

    const SLOT_LABEL = {
        action: 'action',
        bonus: 'bonus action',
        reaction: 'reaction',
    };

    // Per-(slot, source) copy override table. Each entry is a function
    // ``(opts) → copy`` so the wording can interpolate ``label`` and
    // ``characterName`` from the call site. Keys are ``${slot}|${source}``;
    // ``source`` matches the value the server stamps onto the 409 body
    // (currently one of "attack" / "spell" / "feature" / "potion"). Add
    // entries here whenever a house rule changes the wording of a slot
    // for a specific source.
    const _economyCopy = {
        // v2.7.1: when a campaign has potions_as_bonus_action turned on
        // AND the over-budget click is on a Healing Potion's 🧪 Use
        // button, the modal calls out the house rule + uses
        // potion-flavoured verbs ("Drink anyway?" instead of "Roll
        // anyway?"). Cancel/Confirm labels match — confirming a second
        // drink in one turn is closer to "commit" than "fire".
        'bonus|potion': (opts) => {
            const who = opts.characterName || 'You';
            const subject = opts.label ? `the ${opts.label}` : 'the potion';
            return {
                title: 'Over the action budget',
                body: `${who}'ve already used your bonus action this turn. Drink ${subject} anyway?`,
                hint: 'House rule: potions consume your bonus action.',
                confirm: 'Confirm — drink anyway',
                cancel: 'Cancel',
            };
        },
    };

    function _modalCopy(opts) {
        const slot = opts.slot;
        const source = opts.source || '';
        const override = _economyCopy[`${slot}|${source}`];
        if (typeof override === 'function') return override(opts);
        if (override) return override;
        const slotPhrase = SLOT_LABEL[slot] || slot;
        const subject = opts.label ? `the ${opts.label}` : 'this';
        return {
            title: 'Over the action budget',
            body: `${opts.characterName || 'You'}'ve already used your ${slotPhrase} this turn. Roll ${subject} anyway?`,
            hint: '',
            confirm: 'Confirm — fire anyway',
            cancel: 'Cancel',
        };
    }

    function _removeExisting() {
        const prev = document.getElementById('over-budget-modal');
        if (prev) prev.remove();
    }

    /* showOverBudgetModal({ slot, source, label, characterName, onConfirm })
     *
     *   slot          - "action" / "bonus" / "reaction" (from the 409 body)
     *   source        - "attack" / "spell" / "feature" / "potion" (for
     *                   future per-source copy overrides; safe to omit)
     *   label         - the action name shown in the modal body
     *                   (e.g. "Dagger", "Magic Missile", "Cunning Action: Hide")
     *   characterName - the rolling PC's name (so a shared screen makes
     *                   the intent obvious)
     *   onConfirm     - callback invoked when the player clicks Confirm.
     *                   The caller is responsible for re-firing the
     *                   original fetch with override:true.
     *
     * Cancel always closes the modal without calling onConfirm. Click
     * outside the card AND clicking the close button both behave like
     * Cancel.
     */
    window.showOverBudgetModal = function (opts) {
        const o = opts || {};
        const copy = _modalCopy(o);

        _removeExisting();
        const overlay = document.createElement('div');
        overlay.id = 'over-budget-modal';
        overlay.style.cssText = (
            'position:fixed;inset:0;z-index:10000;' +
            'background:rgba(6,8,16,.78);' +
            'display:flex;align-items:center;justify-content:center;padding:18px;'
        );
        const card = document.createElement('div');
        card.style.cssText = (
            'background:var(--s-card,#1a1f2c);' +
            'border:1px solid var(--s-border,#2c3344);' +
            'border-radius:8px;padding:20px;max-width:420px;width:100%;' +
            'color:var(--s-fg,#e8e8e8);font-size:14px;line-height:1.45;' +
            'box-shadow:0 20px 60px rgba(0,0,0,0.6);'
        );
        const _esc = s => String(s ?? '')
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
        card.innerHTML = (
            `<div style="font-size:16px;font-weight:700;color:var(--s-accent,#ffa54a);margin-bottom:12px;">⚠ ${_esc(copy.title)}</div>` +
            `<div style="margin-bottom:${copy.hint ? '8px' : '20px'};">${_esc(copy.body)}</div>` +
            (copy.hint ? `<div style="font-size:12px;color:var(--s-mute,#888);margin-bottom:20px;font-style:italic;">${_esc(copy.hint)}</div>` : '') +
            '<div style="display:flex;gap:8px;justify-content:flex-end;">' +
            `<button type="button" id="obm-cancel" style="padding:8px 14px;min-height:44px;background:transparent;border:1px solid var(--s-border,#2c3344);color:var(--s-fg,#e8e8e8);border-radius:5px;cursor:pointer;">${_esc(copy.cancel)}</button>` +
            `<button type="button" id="obm-confirm" style="padding:8px 14px;min-height:44px;background:var(--s-accent,#ffa54a);border:1px solid var(--s-accent,#ffa54a);color:#1a1f2c;font-weight:700;border-radius:5px;cursor:pointer;">${_esc(copy.confirm)}</button>` +
            '</div>'
        );
        overlay.appendChild(card);
        document.body.appendChild(overlay);

        const close = () => overlay.remove();
        card.querySelector('#obm-cancel').addEventListener('click', close);
        overlay.addEventListener('click', (ev) => { if (ev.target === overlay) close(); });
        card.querySelector('#obm-confirm').addEventListener('click', () => {
            close();
            if (typeof o.onConfirm === 'function') {
                try { o.onConfirm(); } catch (e) { console.error('over-budget onConfirm threw:', e); }
            }
        });
        // Focus the confirm button so keyboard Enter fires it.
        setTimeout(() => card.querySelector('#obm-confirm')?.focus(), 30);
    };

    /* Convenience wrapper: takes a Response object from a 409
     * over_budget reply + the fetch callback to re-fire on Confirm.
     * The fetch body is mutated to add { override: true } before the
     * second call. Returns the second Response on Confirm or null
     * on Cancel.
     *
     * Usage:
     *   const data = await window.handleOverBudget(resp, async () => {
     *       return fetch(url, { ...opts, body: JSON.stringify({ ...origBody, override: true }) });
     *   });
     *   if (!data) return; // user cancelled
     */
    window.handleOverBudget = async function (resp, refetch, characterName) {
        let body; try { body = await resp.json(); } catch { body = null; }
        if (!body || body.error !== 'over_budget') return null;
        return new Promise((resolve) => {
            window.showOverBudgetModal({
                slot: body.slot || 'action',
                source: body.source || '',
                label: body.label || '',
                characterName: characterName || body.char_name || '',
                onConfirm: async () => {
                    try {
                        const r2 = await refetch();
                        resolve(r2);
                    } catch (e) {
                        console.error('over-budget refetch failed:', e);
                        resolve(null);
                    }
                },
            });
            // If the user cancels, the modal closes without firing
            // onConfirm. We need to resolve the promise so callers
            // don't hang — wire that via overlay removal.
            const observer = new MutationObserver(() => {
                if (!document.getElementById('over-budget-modal')) {
                    observer.disconnect();
                    // resolve(null) only if not already resolved (Confirm
                    // path resolves first and removes the overlay).
                    // The double-resolve is harmless — Promise resolution
                    // is idempotent — but we skip it for cleanliness.
                    resolve(null);
                }
            });
            observer.observe(document.body, { childList: true, subtree: false });
        });
    };
})();
