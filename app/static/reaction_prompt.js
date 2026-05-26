/* reaction_prompt.js — Phase 1b of docs/plans/reactions-automation.md.
 *
 * Listens for the v2.67.0 ``reaction_prompt`` WS broadcast (via the
 * ``vtt:ws-message`` CustomEvent dispatched by tabletop.js's
 * ``ws.onmessage`` handler) and renders a popup toast in the
 * top-right corner with the reaction options as one-click buttons.
 *
 * Render rules:
 *   - If ``ME.id`` is NOT in ``data.target_user_ids``, suppress.
 *   - If ``ME.reactionPromptMode === "off"``, suppress entirely.
 *   - If ``ME.reactionPromptMode === "roll_log_only"``, suppress
 *     popup (roll-log card render happens server-side via the
 *     existing ``feature_used`` advisory + the new ``reaction_prompt``
 *     broadcast; this script only handles the popup).
 *   - Default (``"popup"``) renders the toast.
 *
 * Auto-dismiss:
 *   - 20-second timeout — the toast fades + removes itself.
 *   - ``reaction_prompt_resolved`` broadcast — removes any popup
 *     matching the ``prompt_id`` (cross-client coordination: another
 *     tab resolved it).
 *
 * Click handlers:
 *   - Option button → POST /api/campaign/{cid}/use_reaction.
 *     Disables all buttons while in flight; on 200, removes the
 *     popup (the ``reaction_prompt_resolved`` broadcast will also
 *     arrive but the local removal is faster).
 *   - Dismiss button → just removes the popup; the reaction
 *     remains unspent server-side.
 */
(function () {
    if (window.__reactionPromptInstalled) return;
    window.__reactionPromptInstalled = true;

    const POPUP_TTL_MS = 20_000;

    // Map of prompt_id → DOM node so resolved/timeout handlers can
    // find the right popup to remove.
    const _popups = new Map();

    function _hostContainer() {
        // Lazily create a top-right container that stacks popups
        // vertically. Reused across all prompts; persists after
        // the last popup is removed (harmless empty div).
        let host = document.getElementById('reaction-prompt-host');
        if (!host) {
            host = document.createElement('div');
            host.id = 'reaction-prompt-host';
            host.style.cssText = [
                'position:fixed', 'top:80px', 'right:16px',
                'display:flex', 'flex-direction:column', 'gap:8px',
                'z-index:2147483600', 'max-width:360px',
                'pointer-events:none',
            ].join(';');
            document.body.appendChild(host);
        }
        return host;
    }

    function _glassCardStyle() {
        // Match the v2.62.0 frosted-glass card aesthetic. The
        // glass-alpha CSS var is set by the body element when the
        // user has tuned it via /settings; falls back to 42%.
        return [
            'background:color-mix(in srgb, var(--bg) var(--glass-alpha, 42%), transparent)',
            'backdrop-filter:blur(6px)',
            '-webkit-backdrop-filter:blur(6px)',
            'border:1px solid var(--border, rgba(255,255,255,0.18))',
            'border-radius:8px',
            'padding:12px',
            'color:var(--fg, #fff)',
            'font-size:13px',
            'box-shadow:0 6px 24px rgba(0,0,0,0.45)',
            'pointer-events:auto',
            'animation:reactionPopIn 180ms ease-out',
        ].join(';');
    }

    // Inject keyframes + button styles once.
    function _ensureStyleSheet() {
        if (document.getElementById('reaction-prompt-styles')) return;
        const style = document.createElement('style');
        style.id = 'reaction-prompt-styles';
        style.textContent = `
            @keyframes reactionPopIn {
                from { transform: translateY(-8px); opacity: 0; }
                to   { transform: translateY(0);    opacity: 1; }
            }
            #reaction-prompt-host .rp-opt-btn {
                display: block;
                width: 100%;
                min-height: 36px;
                margin-top: 6px;
                padding: 8px 12px;
                border-radius: 6px;
                border: 1px solid var(--border, rgba(255,255,255,0.22));
                background: rgba(255,255,255,0.04);
                color: var(--fg, #fff);
                font-size: 13px;
                text-align: left;
                cursor: pointer;
            }
            #reaction-prompt-host .rp-opt-btn:hover:not(:disabled) {
                background: rgba(255,255,255,0.08);
            }
            #reaction-prompt-host .rp-opt-btn:disabled {
                opacity: 0.5; cursor: not-allowed;
            }
            #reaction-prompt-host .rp-dismiss {
                display: inline-block;
                margin-top: 10px;
                padding: 4px 10px;
                font-size: 11px;
                opacity: 0.7;
                background: none;
                border: none;
                color: inherit;
                cursor: pointer;
            }
            #reaction-prompt-host .rp-dismiss:hover { opacity: 1; }
            #reaction-prompt-host .rp-header {
                font-weight: 600; font-size: 13px;
                display: flex; align-items: center; justify-content: space-between;
                gap: 8px; margin-bottom: 4px;
            }
            #reaction-prompt-host .rp-summary {
                font-size: 12px; opacity: 0.85; line-height: 1.35;
                margin: 0 0 6px 0;
            }
            #reaction-prompt-host .rp-watcher {
                font-size: 11px; opacity: 0.7;
            }
        `;
        document.head.appendChild(style);
    }

    function _campaignId() {
        if (typeof window.CAMPAIGN_ID === 'number') return window.CAMPAIGN_ID;
        if (typeof window.CAMPAIGN_ID === 'string') {
            const n = parseInt(window.CAMPAIGN_ID, 10);
            if (!isNaN(n)) return n;
        }
        return null;
    }

    function _removePopup(promptId) {
        const node = _popups.get(promptId);
        if (!node) return;
        node.remove();
        _popups.delete(promptId);
    }

    async function _spendReaction(promptId, reactionKey, watcherCharId, node) {
        const cid = _campaignId();
        if (cid == null) return;
        // Disable all buttons during the fetch to prevent double-clicks.
        node.querySelectorAll('button').forEach(b => { b.disabled = true; });
        try {
            const resp = await fetch(`/api/campaign/${cid}/use_reaction`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({
                    prompt_id: promptId,
                    reaction_key: reactionKey,
                    watcher_char_id: watcherCharId,
                }),
            });
            if (!resp.ok) {
                // 409 already_resolved (cross-tab race) or 400 (bad
                // input) — either way, the popup is stale. Remove
                // it locally; the resolved broadcast will arrive
                // imminently from the winning client.
                _removePopup(promptId);
                if (resp.status !== 409) {
                    console.warn('use_reaction failed', resp.status, await resp.text());
                }
                return;
            }
            // Server will broadcast reaction_prompt_resolved which
            // removes our popup; remove locally too for snappy UX.
            _removePopup(promptId);
        } catch (err) {
            console.error('use_reaction request errored', err);
            // Re-enable so the user can retry; but only if popup
            // wasn't auto-dismissed.
            node.querySelectorAll('button').forEach(b => { b.disabled = false; });
        }
    }

    function _renderPopup(data) {
        // Build the DOM. data shape per v2.67.0 reactions plan:
        //   prompt_id, watcher_combatant_id, watcher_char_id,
        //   watcher_name, watcher_color, trigger_event,
        //   trigger_summary, target_user_ids, options[]
        _ensureStyleSheet();
        const host = _hostContainer();
        const card = document.createElement('div');
        card.setAttribute('style', _glassCardStyle());
        card.setAttribute('data-prompt-id', data.prompt_id);
        card.setAttribute('role', 'dialog');
        card.setAttribute('aria-label', 'Reaction available');

        const header = document.createElement('div');
        header.className = 'rp-header';
        const nameSpan = document.createElement('span');
        nameSpan.textContent = `⚡ Reaction available`;
        const watcherEl = document.createElement('span');
        watcherEl.className = 'rp-watcher';
        watcherEl.textContent = data.watcher_name || '';
        if (data.watcher_color) watcherEl.style.color = data.watcher_color;
        header.appendChild(nameSpan);
        header.appendChild(watcherEl);
        card.appendChild(header);

        const summary = document.createElement('p');
        summary.className = 'rp-summary';
        summary.textContent = data.trigger_summary || '';
        card.appendChild(summary);

        (data.options || []).forEach(opt => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'rp-opt-btn';
            btn.textContent = opt.label || opt.key;
            if (opt.available === false) {
                btn.disabled = true;
                if (opt.unavailable_reason) {
                    btn.title = opt.unavailable_reason;
                }
            } else {
                btn.addEventListener('click', () => {
                    _spendReaction(
                        data.prompt_id, opt.key, data.watcher_char_id, card,
                    );
                });
            }
            card.appendChild(btn);
        });

        const dismiss = document.createElement('button');
        dismiss.type = 'button';
        dismiss.className = 'rp-dismiss';
        dismiss.textContent = 'Dismiss';
        dismiss.addEventListener('click', () => _removePopup(data.prompt_id));
        card.appendChild(dismiss);

        host.appendChild(card);
        _popups.set(data.prompt_id, card);

        // Auto-dismiss after the popup TTL.
        setTimeout(() => _removePopup(data.prompt_id), POPUP_TTL_MS);
    }

    function _onMessage(ev) {
        const msg = ev && ev.detail;
        if (!msg || typeof msg !== 'object') return;
        const data = msg.data || {};
        if (msg.type === 'reaction_prompt') {
            // Per-user routing — only render if THIS user is a
            // listed target.
            const meId = (window.ME && window.ME.id) ? Number(window.ME.id) : null;
            const targets = Array.isArray(data.target_user_ids)
                ? data.target_user_ids.map(Number) : [];
            if (meId == null || !targets.includes(meId)) return;
            const mode = (window.ME && window.ME.reactionPromptMode) || 'popup';
            if (mode === 'off') return;
            if (mode === 'roll_log_only') return;
            // mode === 'popup' (default) — render.
            _renderPopup(data);
        } else if (msg.type === 'reaction_prompt_resolved') {
            if (data.prompt_id) _removePopup(data.prompt_id);
        }
    }

    document.addEventListener('vtt:ws-message', _onMessage);
})();
