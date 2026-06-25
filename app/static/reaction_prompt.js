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

    // v2.99.49 — bumped from 20s to 30s. Users reported missing OA
    // popups because they were mid-action when the popup faded;
    // 30s gives a more forgiving window without permanently
    // cluttering the corner.
    const POPUP_TTL_MS = 30_000;

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
        //
        // v2.99.49 — added a solid background fallback BEHIND the
        // color-mix() backdrop so the popup is readable on browsers
        // that don't support color-mix yet (some older Safari /
        // Chrome). Also added a bright 4px accent stripe on the
        // left edge + a 1.2s attention pulse so the popup is
        // unmistakably visible in the corner of the eye.
        return [
            // Solid fallback color first (older browsers ignore the
            // color-mix line below and fall back to this).
            'background:#1f2433',
            // Modern browsers override with the translucent variant.
            'background:color-mix(in srgb, var(--bg, #1f2433) var(--glass-alpha, 42%), transparent)',
            'backdrop-filter:blur(6px)',
            '-webkit-backdrop-filter:blur(6px)',
            'border:1px solid var(--border, rgba(255,255,255,0.18))',
            'border-left:4px solid #ffb74d',  // bright amber accent
            'border-radius:8px',
            'padding:12px',
            'color:var(--fg, #fff)',
            'font-size:13px',
            'box-shadow:0 6px 24px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,183,77,0.18)',
            'pointer-events:auto',
            'animation:reactionPopIn 180ms ease-out, reactionPulse 1.2s ease-in-out 2',
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
            /* v2.99.49 — short amber pulse to draw the eye. Repeats
               twice (set in _glassCardStyle as the animation count)
               so the popup says "look here" without nagging. */
            @keyframes reactionPulse {
                0%   { box-shadow: 0 6px 24px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,183,77,0.18); }
                50%  { box-shadow: 0 6px 24px rgba(0,0,0,0.45), 0 0 0 8px rgba(255,183,77,0.35); }
                100% { box-shadow: 0 6px 24px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,183,77,0.18); }
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

    async function _spendReaction(
        promptId, reactionKey, watcherCharId, node, extraParams,
    ) {
        const cid = _campaignId();
        if (cid == null) return false;
        // Disable all buttons during the fetch to prevent double-clicks.
        node.querySelectorAll('button').forEach(b => { b.disabled = true; });
        try {
            // v2.646.0 — optional `params` carry a per-reaction choice
            // (War Caster's spell_index, Mage Slayer's attack_index) so
            // the server runs the real cast/attack pipeline instead of
            // the click-to-resolve advisory.
            const reqBody = {
                prompt_id: promptId,
                reaction_key: reactionKey,
                watcher_char_id: watcherCharId,
            };
            if (extraParams && typeof extraParams === 'object') {
                reqBody.params = extraParams;
            }
            const resp = await fetch(`/api/campaign/${cid}/use_reaction`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify(reqBody),
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
                return false;
            }
            // Server will broadcast reaction_prompt_resolved which
            // removes our popup; remove locally too for snappy UX.
            _removePopup(promptId);
            return true;
        } catch (err) {
            console.error('use_reaction request errored', err);
            // Re-enable so the user can retry; but only if popup
            // wasn't auto-dismissed.
            node.querySelectorAll('button').forEach(b => { b.disabled = false; });
            return false;
        }
    }

    // v2.99.68 — after the OA reaction slot is marked, automatically
    // roll the chosen attack against the provoker so the user gets a
    // weapon-attack chat card instead of having to manually fire
    // /attack from the watcher's sheet. PC: /attack with attack_index.
    // NPC: /npc_attack with inline action params. Both need
    // target_combatant_id = the provoker (from data.mover_combatant_id).
    async function _chainOaAttack(data, opt) {
        const cid = _campaignId();
        if (cid == null) return;
        const params = (opt && opt.params) || {};
        const target = data && data.mover_combatant_id;
        // v2.99.78 — entry-point log so the user can confirm the
        // chain fired at all. Pairs with the failure logs below.
        console.log(
            '[oa-chain] firing',
            'key=' + (opt && opt.key),
            'watcher_char=' + (data && data.watcher_char_id),
            'target=' + target,
            'attack_index=' + params.attack_index,
        );
        if (!target) {
            const msg = (
                '[oa-chain] no mover_combatant_id on the prompt — '
                + 'skipping auto-roll. Server-side mover lookup in '
                + '/token/move may have failed.'
            );
            console.warn(msg, data);
            if (typeof window.showToast === 'function') {
                window.showToast(
                    'OA: could not target the mover (missing combatant_id). '
                    + 'Roll the attack manually from the watcher\'s sheet.',
                    'warning',
                );
            }
            return;
        }
        const isNpc = !!params.npc || !data.watcher_char_id;
        const url = isNpc
            ? `/api/campaign/${cid}/npc_attack`
            : `/api/campaign/${cid}/attack`;
        const body = isNpc ? {
            combatant_id: data.watcher_combatant_id,
            action_id: params.action_id || '',
            action_name: params.action_name || '',
            attack_bonus: params.attack_bonus || '',
            damage: params.damage || '',
            damage_type: params.damage_type || '',
            range: params.range || '',
            target_combatant_id: target,
            // v2.99.75 — mark the chained attack as an OA so the
            // weapon_attack chat card chrome renders "OA — {weapon}".
            is_opportunity_attack: true,
        } : {
            character_id: data.watcher_char_id,
            attack_index: params.attack_index,
            target_combatant_id: target,
            is_opportunity_attack: true,
        };
        try {
            const resp = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify(body),
            });
            // v2.99.73 — surface non-2xx so silent /attack failures
            // (auth, missing field, out-of-range) don't masquerade
            // as the popup-side "OA roll didn't come through" bug.
            if (!resp.ok) {
                let errBody = '';
                try { errBody = await resp.text(); } catch (_) {}
                console.error(
                    '[oa-chain] auto-roll POST failed',
                    'url=' + url,
                    'status=' + resp.status,
                    'body=' + errBody,
                    'request=', body,
                );
                // v2.99.78 — surface the failure as a toast so the
                // user knows the OA roll didn't fire silently. The
                // browser-console log above carries the diagnostic
                // detail; the toast is a "go look in DevTools"
                // breadcrumb.
                if (typeof window.showToast === 'function') {
                    window.showToast(
                        'OA roll failed (' + resp.status + '). '
                        + 'Check DevTools Console for [oa-chain] details.',
                        'error',
                    );
                }
            }
        } catch (err) {
            console.error('[oa-chain] auto-roll fetch errored', err, body);
            if (typeof window.showToast === 'function') {
                window.showToast(
                    'OA roll request errored. '
                    + 'Check DevTools Console for [oa-chain] details.',
                    'error',
                );
            }
        }
    }

    // v2.646.0 — fetch the watcher's sheet so the War Caster / Mage
    // Slayer reaction options can offer a real spell / weapon picker.
    // The popup only renders for the watcher's owner (or the GM for
    // NPCs), both of whom are authorized to read the sheet-json.
    async function _fetchWatcherSheet(watcherCharId) {
        const cid = _campaignId();
        if (cid == null || !watcherCharId) return null;
        try {
            const resp = await fetch(
                `/api/campaign/${cid}/character/${watcherCharId}/sheet-json`,
                { credentials: 'same-origin' },
            );
            if (!resp.ok) return null;
            const data = await resp.json();
            return (data && data.sheet) || null;
        } catch (err) {
            console.warn('[reaction] sheet fetch failed', err);
            return null;
        }
    }

    // v2.646.0 — replace the card's option buttons with a back-able
    // sub-picker: one button per `items` entry (calls onPick(item)),
    // plus a "Cast/Strike manually instead" fallback (resolves the
    // reaction with no choice → the server's advisory path) and a Back
    // button that restores the original options. `items` entries are
    // {label, index}.
    function _showSubPicker(card, data, opt, items, manualLabel, title) {
        const optBtns = Array.from(card.querySelectorAll('.rp-opt-btn'));
        const dismissBtn = card.querySelector('.rp-dismiss');
        optBtns.forEach(b => { b.style.display = 'none'; });
        if (dismissBtn) dismissBtn.style.display = 'none';

        const panel = document.createElement('div');
        panel.className = 'rp-subpicker';

        const titleEl = document.createElement('p');
        titleEl.className = 'rp-summary';
        titleEl.textContent = title || 'Choose:';
        panel.appendChild(titleEl);

        const restore = () => {
            panel.remove();
            optBtns.forEach(b => { b.style.display = ''; });
            if (dismissBtn) dismissBtn.style.display = '';
        };

        items.forEach(item => {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'rp-opt-btn';
            b.textContent = item.label;
            b.addEventListener('click', async () => {
                const extra = {};
                extra[opt.paramKey] = item.index;
                await _spendReaction(
                    data.prompt_id, opt.key, data.watcher_char_id, card, extra,
                );
            });
            panel.appendChild(b);
        });

        const manual = document.createElement('button');
        manual.type = 'button';
        manual.className = 'rp-opt-btn';
        manual.textContent = manualLabel;
        manual.addEventListener('click', async () => {
            // No choice → server falls back to the advisory broadcast.
            await _spendReaction(
                data.prompt_id, opt.key, data.watcher_char_id, card,
            );
        });
        panel.appendChild(manual);

        const back = document.createElement('button');
        back.type = 'button';
        back.className = 'rp-dismiss';
        back.textContent = '← Back';
        back.addEventListener('click', restore);
        panel.appendChild(back);

        card.appendChild(panel);
    }

    // War Caster: pick a 1-action spell to cast at the provoker.
    async function _showWarCasterPicker(data, card, opt) {
        const sheet = await _fetchWatcherSheet(data.watcher_char_id);
        const spells = (sheet && sheet.spells) || [];
        const items = [];
        spells.forEach((sp, i) => {
            const ct = String((sp && sp.casting_time) || '').toLowerCase();
            // RAW: 1-action casting time only (mirror the server gate).
            if (ct.indexOf('action') === -1
                || ct.indexOf('bonus') !== -1
                || ct.indexOf('reaction') !== -1) return;
            const lvl = (sp && sp.level) || 0;
            items.push({
                label: '✨ ' + ((sp && sp.name) || 'Spell')
                    + (lvl ? ' (L' + lvl + ')' : ' (cantrip)'),
                index: i,
            });
        });
        const o = Object.assign({ paramKey: 'spell_index' }, opt);
        const title = items.length
            ? 'Cast which 1-action spell at the provoker?'
            : 'No 1-action spell found on your sheet — cast manually.';
        _showSubPicker(card, data, o, items, 'Cast manually instead', title);
    }

    // Mage Slayer: pick a melee weapon to strike the caster.
    async function _showMageSlayerPicker(data, card, opt) {
        const sheet = await _fetchWatcherSheet(data.watcher_char_id);
        const attacks = (sheet && sheet.attacks) || [];
        const items = attacks.map((atk, i) => ({
            label: '⚔ ' + ((atk && atk.name) || 'Weapon'),
            index: i,
        }));
        const o = Object.assign({ paramKey: 'attack_index' }, opt);
        const title = items.length
            ? 'Strike the caster with which weapon?'
            : 'No weapon found on your sheet — strike manually.';
        _showSubPicker(card, data, o, items, 'Strike manually instead', title);
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
                btn.addEventListener('click', async () => {
                    // v2.646.0 — War Caster / Mage Slayer open a real
                    // spell / weapon sub-picker; the choice rides
                    // /use_reaction's `params` so the server runs the
                    // cast/attack pipeline (v2.643.0 / v2.644.0) instead
                    // of the click-to-resolve advisory.
                    if (opt.key === 'take-war-caster-cast') {
                        await _showWarCasterPicker(data, card, opt);
                        return;
                    }
                    if (opt.key === 'take-mage-slayer-strike') {
                        await _showMageSlayerPicker(data, card, opt);
                        return;
                    }
                    const ok = await _spendReaction(
                        data.prompt_id, opt.key, data.watcher_char_id, card,
                    );
                    // v2.99.68 — chain the chosen OA attack roll on
                    // success so the user gets a weapon-attack chat
                    // card immediately. Generic take-the-oa (no
                    // attack_index in params) falls through to the
                    // old manual-roll behavior. War Caster / Skip /
                    // other reaction keys are unaffected.
                    if (ok && typeof opt.key === 'string'
                            && opt.key.startsWith('take-the-oa:')) {
                        await _chainOaAttack(data, opt);
                    }
                });
            }
            card.appendChild(btn);
        });

        const dismiss = document.createElement('button');
        dismiss.type = 'button';
        dismiss.className = 'rp-dismiss';
        dismiss.textContent = 'Dismiss';
        // v2.99.78 — Dismiss on an OA prompt now resolves the prompt
        // with skip-oa server-side (was: local _removePopup only).
        // Per the user's request: "remove the Opportunity Attack
        // triggered message if the OA is not taken." Dismiss is the
        // "I'm not taking it" gesture; calling /use_reaction fires
        // reaction_prompt_resolved which clears the chat-card row
        // on every connected client via _markOaCardResolved. For
        // non-OA prompts we keep the legacy behavior (just hide
        // the popup locally).
        dismiss.addEventListener('click', async () => {
            const isOa = (data.trigger_event === 'creature_exits_reach'
                || data.trigger_event === 'creature_enters_reach');
            if (isOa) {
                // Reuse _spendReaction so the 409-cross-tab-race
                // handling + button-disable logic is unified. The
                // chain check below only fires for take-the-oa keys,
                // so skip-oa naturally bypasses _chainOaAttack.
                await _spendReaction(
                    data.prompt_id, 'skip-oa', data.watcher_char_id, card,
                );
            } else {
                _removePopup(data.prompt_id);
            }
        });
        card.appendChild(dismiss);

        host.appendChild(card);
        _popups.set(data.prompt_id, card);

        // Auto-dismiss after the popup TTL. v2.99.78 — for OA prompts,
        // fire skip-oa on TTL expiry too so the chat-card clears across
        // every tab when nobody acts. Mirrors the Dismiss-button gesture.
        setTimeout(async () => {
            // Re-check existence (the user may have clicked already).
            if (!_popups.has(data.prompt_id)) return;
            const isOa = (data.trigger_event === 'creature_exits_reach'
                || data.trigger_event === 'creature_enters_reach');
            if (isOa) {
                await _spendReaction(
                    data.prompt_id, 'skip-oa', data.watcher_char_id, card,
                );
            } else {
                _removePopup(data.prompt_id);
            }
        }, POPUP_TTL_MS);
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
            const mode = (window.ME && window.ME.reactionPromptMode) || 'popup';
            // v2.99.49 — diagnostic log so users reporting "popup
            // doesn't appear" can open devtools and see what filter
            // (if any) suppressed the render. v2.99.63: bumped from
            // console.debug → console.log so the line shows at the
            // default DevTools Verbose-off level (debug entries are
            // hidden unless the user explicitly enables Verbose).
            try {
                console.log(
                    '[reaction_prompt]',
                    'prompt_id=' + (data.prompt_id || '?'),
                    'trigger=' + (data.trigger_event || '?'),
                    'me=' + meId,
                    'targets=[' + targets.join(',') + ']',
                    'mode=' + mode,
                    'will_render=' + (
                        meId != null && targets.includes(meId)
                        && mode === 'popup'
                    ),
                );
            } catch (_) {}
            if (meId == null || !targets.includes(meId)) return;
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
