/* Shared action-button renderer.
 *
 * Loaded on both tabletop.html (so the spell-cast roll-log card can use it)
 * and sheet_dnd5e.html (so character-sheet panels can mount slots populated
 * from each content record's `actions: list[Action]` field).
 *
 * Field-presence gates which buttons each Action emits — see
 * app/action_schema.py for the canonical field list. Consumers wire behavior
 * via the `handlers` callbacks in ctx:
 *
 *   const frag = renderActionButtons(actions, {
 *       characterLevel: 5,
 *       handlers: {
 *           damage: (action, expr, btn) => { ... },
 *           save:   (action, btn) => { ... },
 *           heal:   (action, btn) => { ... },
 *           attack: (action, btn) => { ... },
 *           toggle: (action, btn) => { ... },
 *       },
 *   });
 *   slotEl.appendChild(frag);
 *
 * Auto-init: on DOMContentLoaded, every `[data-actions]` element on the page
 * is scanned. Its `data-actions` attribute is parsed as JSON, and the
 * resulting array is rendered into the element. The optional
 * `data-character-level` attribute drives `damage_scaling` tier resolution.
 * Auto-init wires no handlers; if you want clickable buttons, attach a
 * `[data-renderer-callback]` JS function name on the element (looked up on
 * window) — that function receives `(actions, slotEl)` and is expected to
 * call renderActionButtons itself with appropriate handlers.
 */
(function () {
    'use strict';

    function _mkActionBtn(label, className) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'spell-cast-btn ' + (className || '');
        btn.textContent = label;
        return btn;
    }

    // ── Transient toast notifications (1.10.0) ──
    // Same .vtt-toast / #vtt-toast-stack styling the tabletop already uses
    // (CSS lives in style.css so both pages get it). tabletop.js also defines
    // window.showToast for its own toasts; we only register ours if no such
    // function already exists so we never clobber the page that loads
    // tabletop.js first.
    function _showToast(msg, kind) {
        let stack = document.getElementById('vtt-toast-stack');
        if (!stack) {
            stack = document.createElement('div');
            stack.id = 'vtt-toast-stack';
            document.body.appendChild(stack);
        }
        const t = document.createElement('div');
        t.className = 'vtt-toast' + (kind ? ' vtt-toast-' + kind : '');
        t.textContent = msg;
        stack.appendChild(t);
        // Force a reflow so the fade-in transition runs.
        // eslint-disable-next-line no-unused-expressions
        t.offsetHeight;
        t.classList.add('vtt-toast-show');
        setTimeout(() => {
            t.classList.remove('vtt-toast-show');
            setTimeout(() => t.remove(), 260);
        }, 4200);
    }
    if (typeof window.showToast !== 'function') {
        window.showToast = _showToast;
    }

    function _pickDamageTier(scaling, level) {
        if (!scaling || !scaling.length) return null;
        const eligible = scaling.filter(t => (t.level || 1) <= level);
        if (!eligible.length) return null;
        eligible.sort((a, b) => (b.level || 0) - (a.level || 0));
        return eligible[0];
    }

    function renderActionButtons(actions, ctx) {
        const frag = document.createDocumentFragment();
        const characterLevel = (ctx && ctx.characterLevel) || 1;
        const handlers = (ctx && ctx.handlers) || {};

        (actions || []).forEach(action => {
            // Damage: scaling tier wins over the static field.
            let damageExpr = '';
            const tier = _pickDamageTier(action.damage_scaling, characterLevel);
            if (tier && tier.damage) damageExpr = tier.damage;
            else if (action.damage) damageExpr = action.damage;
            const damageType = action.damage_type || '';

            if (action.attack_roll && handlers.attack) {
                const btn = _mkActionBtn('🎯 Attack Roll', 'spell-cast-attack-btn');
                btn.addEventListener('click', () => handlers.attack(action, btn));
                frag.appendChild(btn);
            }
            if (damageExpr && handlers.damage) {
                const label = damageType
                    ? `🎲 Roll ${damageExpr} ${damageType}`
                    : `🎲 Roll damage (${damageExpr})`;
                const btn = _mkActionBtn(label, 'spell-cast-dmg-btn');
                btn.addEventListener('click', () => handlers.damage(action, damageExpr, btn));
                frag.appendChild(btn);
            }
            if (action.save_ability && handlers.save) {
                const sa = String(action.save_ability).toUpperCase();
                const btn = _mkActionBtn(`📋 Prompt ${sa} save`, 'spell-cast-save-btn');
                btn.addEventListener('click', () => handlers.save(action, btn));
                frag.appendChild(btn);
            }
            if (action.healing && handlers.heal) {
                const isAoe = (action.aoe_targets || 1) > 1;
                const chargeLabel = isAoe ? ` (0/${action.aoe_targets})` : '';
                const btn = _mkActionBtn(
                    `🩹 Apply Healing (${action.healing})${chargeLabel}`,
                    'spell-cast-heal-btn'
                );
                btn.dataset.aoe = isAoe ? '1' : '0';
                if (isAoe) {
                    btn.dataset.claimed = '0';
                    btn.dataset.max = String(action.aoe_targets);
                }
                btn.addEventListener('click', () => handlers.heal(action, btn));
                frag.appendChild(btn);
            }
            if (action.active_toggle && handlers.toggle) {
                const btn = _mkActionBtn(`⚡ ${action.name}`, 'feature-toggle-btn');
                if (action.resource_key) btn.dataset.resourceKey = action.resource_key;
                btn.addEventListener('click', () => handlers.toggle(action, btn));
                frag.appendChild(btn);
            }
            // reroll_trigger and transform_picker are surfaced elsewhere:
            //   - Lucky-style reroll on the roll log when a d20 lands on 1
            //   - Wildshape via the existing beast_picker.js modal
        });

        return frag;
    }

    // Build a description-only card for an action that has no handler-bound
    // buttons (passive racial traits, condition effects, etc.). Used by the
    // auto-init hook so authors get *something* visible even when no callback
    // is attached.
    function renderActionCards(actions) {
        const wrap = document.createElement('div');
        wrap.className = 'action-cards';
        (actions || []).forEach(a => {
            const card = document.createElement('div');
            card.className = 'action-card';
            card.style.cssText = 'padding:6px 10px;margin:4px 0;border-left:3px solid var(--accent,#7aa);background:#1e2230;font-size:13px';
            const title = document.createElement('div');
            title.style.cssText = 'font-weight:600;font-size:13px';
            title.textContent = a.name + (a.category && a.category !== 'action' ? ` (${a.category.replace('_', ' ')})` : '');
            card.appendChild(title);
            if (a.desc) {
                const desc = document.createElement('div');
                desc.style.cssText = 'color:#aaa;font-size:12px;line-height:1.35;margin-top:2px';
                desc.textContent = a.desc;
                card.appendChild(desc);
            }
            wrap.appendChild(card);
        });
        return wrap;
    }

    function _autoInitOne(el) {
        const raw = el.getAttribute('data-actions');
        if (!raw) return;
        let actions;
        try {
            actions = JSON.parse(raw);
        } catch (e) {
            console.warn('action-buttons: invalid data-actions JSON on', el, e);
            return;
        }
        const level = parseInt(el.getAttribute('data-character-level') || '1', 10) || 1;
        const cbName = el.getAttribute('data-renderer-callback');
        if (cbName && typeof window[cbName] === 'function') {
            // Delegate to a page-supplied renderer that knows how to wire handlers.
            window[cbName](actions, el, { characterLevel: level });
        } else {
            // No callback: render passive description cards so the actions are
            // at least visible. Pages that want clickable buttons should
            // provide a callback.
            el.appendChild(renderActionCards(actions));
        }
        el.setAttribute('data-actions-rendered', '1');
    }

    function autoInit() {
        document.querySelectorAll('[data-actions]:not([data-actions-rendered])').forEach(_autoInitOne);
    }

    // Expose so pages can call it explicitly after injecting new slots.
    window.renderActionButtons = renderActionButtons;
    window.renderActionCards = renderActionCards;
    window.autoInitActionSlots = autoInit;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', autoInit);
    } else {
        autoInit();
    }
})();
