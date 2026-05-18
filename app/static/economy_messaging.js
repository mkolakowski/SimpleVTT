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
        // v2.14.6: Wild Shape over-budget. Moon Druid spends a bonus
        // action (Lv 2 RAW feature); the default Druid spends an action.
        // The endpoint stamps source:"wild-shape" on the 409 body so
        // both slot variants can route here. Verb is "shift" — the
        // table reads as Wild-Shape-flavoured, not generic.
        'bonus|wild-shape': (opts) => {
            const who = opts.characterName || 'You';
            return {
                title: 'Over the action budget',
                body: `${who}'ve already used your bonus action this turn. Wild Shape anyway?`,
                hint: 'Circle of the Moon: Wild Shape consumes your bonus action.',
                confirm: 'Confirm — shift anyway',
                cancel: 'Cancel',
            };
        },
        'action|wild-shape': (opts) => {
            const who = opts.characterName || 'You';
            return {
                title: 'Over the action budget',
                body: `${who}'ve already used your action this turn. Wild Shape anyway?`,
                hint: '',
                confirm: 'Confirm — shift anyway',
                cancel: 'Cancel',
            };
        },
        // Polymorph the spell is always an action regardless of caster
        // class. The 🦌 Polymorph button on the resources panel goes
        // through /transform directly without /cast_spell so this is
        // its over-budget path.
        'action|polymorph': (opts) => {
            const who = opts.characterName || 'You';
            return {
                title: 'Over the action budget',
                body: `${who}'ve already used your action this turn. Cast Polymorph anyway?`,
                hint: '',
                confirm: 'Confirm — cast anyway',
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

    /* showOverBudgetModal({ slot, source, label, characterName, strict, onConfirm })
     *
     *   slot          - "action" / "bonus" / "reaction" (from the 409 body)
     *   source        - "attack" / "spell" / "feature" / "potion" (for
     *                   future per-source copy overrides; safe to omit)
     *   label         - the action name shown in the modal body
     *                   (e.g. "Dagger", "Magic Missile", "Cunning Action: Hide")
     *   characterName - the rolling PC's name (so a shared screen makes
     *                   the intent obvious)
     *   strict        - v2.8.0: when true, the Confirm button is replaced
     *                   with a "Close" + "Ask the GM to clear your chip"
     *                   hint. Players can't bypass; only the GM clicking
     *                   the chip on the init tracker can refund the slot.
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
        const isStrict = !!o.strict;

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

        // In strict mode the Confirm button is replaced with an explanatory
        // hint line — players can't override a spent chip from the modal.
        // The hint text overwrites copy.hint so the strict-mode reason is
        // the bottom-line message regardless of any house-rule copy.
        const strictHint = isStrict
            ? "Strict mode: players can't override. Ask the GM to clear your chip on the init tracker (shift+click)."
            : '';
        const hintLine = strictHint || copy.hint;
        const buttonsHtml = isStrict
            ? `<button type="button" id="obm-cancel" style="padding:8px 14px;min-height:44px;background:var(--s-accent,#ffa54a);border:1px solid var(--s-accent,#ffa54a);color:#1a1f2c;font-weight:700;border-radius:5px;cursor:pointer;">Close</button>`
            : `<button type="button" id="obm-cancel" style="padding:8px 14px;min-height:44px;background:transparent;border:1px solid var(--s-border,#2c3344);color:var(--s-fg,#e8e8e8);border-radius:5px;cursor:pointer;">${_esc(copy.cancel)}</button>` +
              `<button type="button" id="obm-confirm" style="padding:8px 14px;min-height:44px;background:var(--s-accent,#ffa54a);border:1px solid var(--s-accent,#ffa54a);color:#1a1f2c;font-weight:700;border-radius:5px;cursor:pointer;">${_esc(copy.confirm)}</button>`;

        card.innerHTML = (
            `<div style="font-size:16px;font-weight:700;color:var(--s-accent,#ffa54a);margin-bottom:12px;">⚠ ${_esc(copy.title)}</div>` +
            `<div style="margin-bottom:${hintLine ? '8px' : '20px'};">${_esc(copy.body)}</div>` +
            (hintLine ? `<div style="font-size:12px;color:var(--s-mute,#888);margin-bottom:20px;font-style:italic;">${_esc(hintLine)}</div>` : '') +
            `<div style="display:flex;gap:8px;justify-content:flex-end;">${buttonsHtml}</div>`
        );
        overlay.appendChild(card);
        document.body.appendChild(overlay);

        const close = () => overlay.remove();
        card.querySelector('#obm-cancel').addEventListener('click', close);
        overlay.addEventListener('click', (ev) => { if (ev.target === overlay) close(); });
        if (!isStrict) {
            card.querySelector('#obm-confirm').addEventListener('click', () => {
                close();
                if (typeof o.onConfirm === 'function') {
                    try { o.onConfirm(); } catch (e) { console.error('over-budget onConfirm threw:', e); }
                }
            });
            // Focus the confirm button so keyboard Enter fires it.
            setTimeout(() => card.querySelector('#obm-confirm')?.focus(), 30);
        } else {
            // Strict mode — focus the close button so Enter dismisses.
            setTimeout(() => card.querySelector('#obm-cancel')?.focus(), 30);
        }
    };

    /* v2.8.3: showMovementOverrunModal({characterName, currentUsed,
     *   distanceFt, speedCap, dashed, onCancel, onMove, onDash})
     *
     * Pre-commit gate on a token drag that would push the active
     * combatant past their walking speed for the turn. Three buttons:
     *
     *   Cancel       — snap the token back; nothing committed.
     *   Move anyway  — accept the overrun, fire the regular /move POST.
     *                  The Mov chip + breadcrumb render red for the
     *                  segment, and v2.8.0 strict mode (if on) also
     *                  posts the ⚠ Movement overrun audit entry.
     *   Take Dash    — Disabled when ``dashed`` is true (already Dashed
     *                  this turn). Otherwise: mark the action slot
     *                  (Dash IS the action), bump the player's effective
     *                  cap by +speedCap so the next speedCap feet are
     *                  green again, and fire /move.
     *
     * Cancel-by-overlay-click and Cancel-by-Escape both behave as the
     * Cancel button. Each onX callback fires once; the modal removes
     * itself before calling the callback so handlers can show further
     * modals safely.
     */
    window.showMovementOverrunModal = function (opts) {
        const o = opts || {};
        const who = o.characterName || 'Your character';
        const current = Math.round(((o.currentUsed || 0)) * 10) / 10;
        const dist = Math.round(((o.distanceFt || 0)) * 10) / 10;
        const cap = Math.round(o.speedCap || 30);
        const newTotal = Math.round((current + dist) * 10) / 10;
        const overBy = Math.round((newTotal - cap) * 10) / 10;
        const dashed = !!o.dashed;
        const dashBonus = cap;

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
            'border-radius:8px;padding:20px;max-width:460px;width:100%;' +
            'color:var(--s-fg,#e8e8e8);font-size:14px;line-height:1.45;' +
            'box-shadow:0 20px 60px rgba(0,0,0,0.6);'
        );
        const _esc = s => String(s ?? '')
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');

        const dashBtnHtml = dashed
            ? `<button type="button" id="obm-dash" disabled
                style="padding:8px 14px;min-height:44px;background:rgba(76,217,100,0.18);border:1px solid rgba(76,217,100,0.35);color:#7ed17b;font-weight:700;border-radius:5px;cursor:not-allowed;opacity:.6;"
                title="Already Dashed this turn">🏃 Already Dashed</button>`
            : `<button type="button" id="obm-dash"
                style="padding:8px 14px;min-height:44px;background:rgba(76,217,100,0.18);border:1px solid #4cd964;color:#7ed17b;font-weight:700;border-radius:5px;cursor:pointer;"
                title="Use your action to Dash (+${_esc(dashBonus)} ft this turn)">🏃 Dash (+${_esc(dashBonus)} ft, uses action)</button>`;

        card.innerHTML = (
            `<div style="font-size:16px;font-weight:700;color:var(--s-accent,#ffa54a);margin-bottom:12px;">⚠ Over your walking speed</div>` +
            `<div style="margin-bottom:8px;">${_esc(who)}, this move would put you at <strong>${_esc(newTotal)} ft</strong> this turn — ${_esc(overBy)} ft past your ${_esc(cap)} ft walking speed.</div>` +
            `<div style="margin-bottom:18px;font-size:12px;color:var(--s-mute,#888);font-style:italic;">${dashed
                ? "You've already Dashed this turn. Take the overrun or cancel."
                : "Dash (action) lets you move an extra " + _esc(dashBonus) + " ft this turn."}</div>` +
            '<div style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;">' +
            `<button type="button" id="obm-cancel" style="padding:8px 14px;min-height:44px;background:transparent;border:1px solid var(--s-border,#2c3344);color:var(--s-fg,#e8e8e8);border-radius:5px;cursor:pointer;">Cancel</button>` +
            `<button type="button" id="obm-move" style="padding:8px 14px;min-height:44px;background:rgba(255,96,96,0.18);border:1px solid #ff7070;color:#ff8080;font-weight:700;border-radius:5px;cursor:pointer;">Move anyway</button>` +
            dashBtnHtml +
            '</div>'
        );
        overlay.appendChild(card);
        document.body.appendChild(overlay);

        const fired = { value: false };
        const fire = (cb) => {
            if (fired.value) return;
            fired.value = true;
            overlay.remove();
            if (typeof cb === 'function') {
                try { cb(); } catch (e) { console.error('movement modal handler threw:', e); }
            }
        };
        card.querySelector('#obm-cancel').addEventListener('click', () => fire(o.onCancel));
        card.querySelector('#obm-move').addEventListener('click', () => fire(o.onMove));
        if (!dashed) {
            card.querySelector('#obm-dash').addEventListener('click', () => fire(o.onDash));
        }
        overlay.addEventListener('click', (ev) => { if (ev.target === overlay) fire(o.onCancel); });
        const escHandler = (ev) => {
            if (ev.key === 'Escape') {
                document.removeEventListener('keydown', escHandler);
                fire(o.onCancel);
            }
        };
        document.addEventListener('keydown', escHandler);
        // Focus the Cancel button so Enter doesn't accidentally trigger
        // the overrun-accepting Move button. Mirrors the strict-mode
        // over-budget modal's defensive focus.
        setTimeout(() => card.querySelector('#obm-cancel')?.focus(), 30);
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
                // v2.8.0: when the campaign has strict_action_economy on,
                // the 409 body carries ``strict: true``. The modal swaps
                // its Confirm button for a Close-only flow; the refetch
                // path below never fires because the strict modal has no
                // onConfirm handler (resolve(null) lands via the modal
                // removal observer below, same as a Cancel).
                strict: !!body.strict,
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
