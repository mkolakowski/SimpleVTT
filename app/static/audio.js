/* SimpleVTT audio client.
 *
 * Handles three things:
 *  1. Master volume + mute (localStorage; per-browser).
 *  2. Per-category volume override (server-side; loaded once on connect).
 *     Categories: music, sfx, environment.
 *     Effective playback volume = master * (categoryOverride ?? 1).
 *  3. Time-sync: every audio_play broadcast carries `started_at_ms` (UTC
 *     epoch from the server). On receipt, we compute elapsed seconds and
 *     seek the <audio> element to match so all clients hear the same
 *     position. A small drift correction kicks in if a client falls more
 *     than DRIFT_THRESHOLD_S out of sync (e.g., after tab throttling).
 *
 * Listens for `vtt:ws-message` CustomEvents dispatched by tabletop.js.
 */
(function () {
    'use strict';

    const root = document.getElementById('audio-panel');
    if (!root) return;

    const audioEl = document.createElement('audio');
    audioEl.id = 'vtt-audio';
    audioEl.preload = 'auto';
    audioEl.style.display = 'none';
    document.body.appendChild(audioEl);

    const nowPlayingEl  = document.getElementById('audio-now-playing');
    const volSlider     = document.getElementById('audio-volume');
    const muteBtn       = document.getElementById('audio-mute');
    const enableBtn     = document.getElementById('audio-enable');
    const catVolWrap    = document.getElementById('audio-cat-volume');
    const catVolSld     = document.getElementById('audio-cat-volume-slider');
    const catVolNum     = document.getElementById('audio-cat-volume-num');
    const catVolLabel   = document.getElementById('audio-cat-volume-label');

    const CATEGORY_LABELS = { music: 'Music', sfx: 'Sound Effects', environment: 'Environment' };

    // ---- master volume + mute (localStorage) ----
    const VOL_KEY  = 'simplevtt.audio.volume';
    const MUTE_KEY = 'simplevtt.audio.muted';
    function loadMasterVol() {
        const v = parseFloat(localStorage.getItem(VOL_KEY));
        return Number.isFinite(v) && v >= 0 && v <= 1 ? v : 0.6;
    }
    function loadMute() { return localStorage.getItem(MUTE_KEY) === '1'; }

    let masterVol = loadMasterVol();
    audioEl.muted = loadMute();
    if (volSlider) volSlider.value = String(masterVol);
    if (muteBtn) { muteBtn.textContent = audioEl.muted ? '🔇' : '🔊'; muteBtn.title = audioEl.muted ? 'Unmute' : 'Mute'; }

    // ---- per-category volume preferences (server-side) ----
    // Map of category -> volume (0..1). Loaded once on init.
    let categoryVol = {};
    fetch('/api/audio/category-preferences', { credentials: 'same-origin' })
        .then(r => r.ok ? r.json() : {})
        .then(json => { categoryVol = json || {}; applyEffectiveVolume(); })
        .catch(() => {});

    let currentTrackId = null;
    let currentCategory = 'music';
    let currentDuration = 0;
    let suppressSavingCatVol = false;

    function effectiveCategoryVol() {
        const v = categoryVol[currentCategory];
        return (typeof v === 'number') ? v : 1;
    }
    function applyEffectiveVolume() {
        audioEl.volume = Math.max(0, Math.min(1, masterVol * effectiveCategoryVol()));
    }

    if (volSlider) {
        volSlider.addEventListener('input', () => {
            masterVol = parseFloat(volSlider.value);
            localStorage.setItem(VOL_KEY, String(masterVol));
            if (masterVol === 0 && !audioEl.muted) {
                audioEl.muted = true;
                localStorage.setItem(MUTE_KEY, '1');
                if (muteBtn) { muteBtn.textContent = '🔇'; muteBtn.title = 'Unmute'; }
            } else if (masterVol > 0 && audioEl.muted) {
                audioEl.muted = false;
                localStorage.setItem(MUTE_KEY, '0');
                if (muteBtn) { muteBtn.textContent = '🔊'; muteBtn.title = 'Mute'; }
            }
            applyEffectiveVolume();
        });
    }
    if (muteBtn) {
        muteBtn.addEventListener('click', () => {
            audioEl.muted = !audioEl.muted;
            localStorage.setItem(MUTE_KEY, audioEl.muted ? '1' : '0');
            muteBtn.textContent = audioEl.muted ? '🔇' : '🔊';
            muteBtn.title = audioEl.muted ? 'Unmute' : 'Mute';
        });
    }

    // ---- per-category slider in the tabletop panel ----
    let saveCatTimer = null;
    function debouncedSaveCategoryVol(category, volume) {
        if (suppressSavingCatVol) return;
        clearTimeout(saveCatTimer);
        saveCatTimer = setTimeout(async () => {
            try {
                await fetch(`/api/audio/category-preferences/${category}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                    body: JSON.stringify({ volume }),
                });
            } catch (e) { console.warn('save category vol failed', e); }
        }, 350);
    }
    if (catVolSld) {
        catVolSld.addEventListener('input', () => {
            const v = parseFloat(catVolSld.value);
            categoryVol[currentCategory] = v;
            if (catVolNum) catVolNum.textContent = Math.round(v * 100) + '%';
            applyEffectiveVolume();
            debouncedSaveCategoryVol(currentCategory, v);
        });
    }
    function refreshCategoryVolUI() {
        if (!catVolWrap) return;
        if (currentTrackId == null) {
            catVolWrap.style.display = 'none';
            return;
        }
        catVolWrap.style.display = '';
        if (catVolLabel) catVolLabel.textContent = CATEGORY_LABELS[currentCategory] || currentCategory;
        const v = effectiveCategoryVol();
        suppressSavingCatVol = true;
        if (catVolSld) catVolSld.value = String(v);
        suppressSavingCatVol = false;
        if (catVolNum) catVolNum.textContent = Math.round(v * 100) + '%';
    }

    // ---- now-playing label ----
    function setNowPlaying(name) {
        if (!nowPlayingEl) return;
        nowPlayingEl.textContent = name || 'Nothing playing';
    }

    // ---- progress bars ----
    // Re-queried lazily on each call: the player drawer + GM tools each
    // render their own ``.audio-progress`` element, and the GM panel can
    // be lazily-rendered on first open in some flows.
    function _progressEls() {
        return document.querySelectorAll('.audio-progress');
    }
    function _fmtTime(seconds) {
        if (!isFinite(seconds) || seconds < 0) return '0:00';
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    }
    function _showProgress(visible) {
        _progressEls().forEach(el => {
            if (visible) el.removeAttribute('hidden');
            else el.setAttribute('hidden', '');
        });
    }
    function _setProgress(elapsed, total) {
        const safeTotal = isFinite(total) && total > 0 ? total : 0;
        const pct = safeTotal > 0 ? Math.min(100, Math.max(0, (elapsed / safeTotal) * 100)) : 0;
        _progressEls().forEach(el => {
            const eEl = el.querySelector('.audio-progress-elapsed');
            const tEl = el.querySelector('.audio-progress-total');
            const fEl = el.querySelector('.audio-progress-fill');
            if (eEl) eEl.textContent = _fmtTime(elapsed);
            if (tEl) tEl.textContent = _fmtTime(safeTotal);
            if (fEl) fEl.style.width = pct + '%';
        });
    }
    // <audio>.timeupdate fires every ~250 ms during playback — perfect
    // cadence for a smooth bar without any extra timer.
    audioEl.addEventListener('timeupdate', () => {
        if (!currentTrackId) return;
        _setProgress(audioEl.currentTime || 0, audioEl.duration || 0);
    });

    // ---- autoplay-blocked helper ----
    function tryPlay() {
        const p = audioEl.play();
        if (p && typeof p.then === 'function') {
            p.catch((err) => {
                if (enableBtn) enableBtn.style.display = '';
                console.warn('audio play blocked until user gesture:', err);
            });
        }
    }
    if (enableBtn) {
        enableBtn.style.display = 'none';
        enableBtn.addEventListener('click', () => {
            tryPlay();
            enableBtn.style.display = 'none';
        });
    }

    // ---- time sync ----
    const DRIFT_THRESHOLD_S = 0.75;
    let serverStartedAtMs = null;
    let currentPaused = false;
    let currentPausedOffset = 0;
    let currentTrackName = '';

    function expectedPositionSeconds() {
        if (serverStartedAtMs == null) return 0;
        return Math.max(0, (Date.now() - serverStartedAtMs) / 1000);
    }
    function seekToExpected() {
        const target = expectedPositionSeconds();
        if (currentDuration && target > currentDuration) {
            if (currentDuration > 0) audioEl.currentTime = target % currentDuration;
        } else {
            audioEl.currentTime = target;
        }
    }
    audioEl.addEventListener('loadedmetadata', () => {
        currentDuration = audioEl.duration || 0;
        if (currentPaused) {
            // Sync the freshly-loaded element to the pause offset so the
            // user sees the correct elapsed time on the progress bar; do
            // NOT auto-play.
            audioEl.currentTime = Math.min(currentPausedOffset, currentDuration || currentPausedOffset);
        } else {
            seekToExpected();
            tryPlay();
        }
        // First moment we know the total duration → paint the bar with
        // real values and reveal it.
        _setProgress(audioEl.currentTime || 0, currentDuration);
        _showProgress(true);
    });
    setInterval(() => {
        if (!currentTrackId || serverStartedAtMs == null) return;
        if (currentPaused) return;   // Don't fight the GM's pause.
        if (audioEl.paused || !audioEl.duration) return;
        const expected = expectedPositionSeconds() % audioEl.duration;
        const drift = Math.abs(expected - audioEl.currentTime);
        const wrappedDrift = Math.min(drift, Math.abs(drift - audioEl.duration));
        if (wrappedDrift > DRIFT_THRESHOLD_S) audioEl.currentTime = expected;
    }, 5000);

    // ---- WS event handling ----
    function _labelFor(name, paused) {
        return `${paused ? '⏸' : '▶'} ${name || ''}`;
    }

    function handleMessage(msg) {
        if (msg.type === 'audio_play') {
            const d = msg.data || {};
            const newPaused = !!d.paused;
            // Idempotency: server sends audio_play on every WS connect
            // (so reconnecting clients re-sync to the live position).
            // That means a fresh page load fires this handler twice — once
            // from the HTML data-initial-play, then again from the WS sync
            // with identical data. Skip the second call to avoid an
            // unnecessary <audio> reload glitch.
            if (currentTrackId === d.track_id
                && serverStartedAtMs === (d.started_at_ms || null)
                && currentPaused === newPaused
                && audioEl.src
                && audioEl.src.endsWith(d.file_url || '')) {
                return;
            }
            // Same-track update — pause toggle or resume with adjusted
            // started_at. Update timing/pause state without reloading
            // ``<audio>.src`` (which would force a refetch + reseek glitch).
            if (currentTrackId === d.track_id
                && audioEl.src
                && audioEl.src.endsWith(d.file_url || '')) {
                serverStartedAtMs   = d.started_at_ms || Date.now();
                currentPausedOffset = (typeof d.paused_offset_s === 'number') ? d.paused_offset_s : 0;
                currentPaused       = newPaused;
                currentTrackName    = d.name || currentTrackName;
                if (newPaused) {
                    audioEl.currentTime = currentPausedOffset;
                    audioEl.pause();
                } else {
                    seekToExpected();
                    tryPlay();
                }
                setNowPlaying(_labelFor(currentTrackName, newPaused));
                _setProgress(audioEl.currentTime || 0, audioEl.duration || 0);
                return;
            }
            // Different track (or first play) — full reset.
            currentTrackId      = d.track_id;
            currentCategory     = d.category || 'music';
            serverStartedAtMs   = d.started_at_ms || Date.now();
            currentPaused       = newPaused;
            currentPausedOffset = (typeof d.paused_offset_s === 'number') ? d.paused_offset_s : 0;
            currentTrackName    = d.name || '';
            currentDuration     = 0;
            audioEl.src = d.file_url;
            setNowPlaying(_labelFor(currentTrackName, currentPaused));
            refreshCategoryVolUI();
            applyEffectiveVolume();
            // Reset the bar to "—" while metadata loads; loadedmetadata
            // will populate real values + reveal it.
            _setProgress(0, 0);
        } else if (msg.type === 'audio_pause') {
            const d = msg.data || {};
            currentPaused = true;
            if (typeof d.paused_offset_s === 'number') {
                currentPausedOffset = d.paused_offset_s;
            } else if (audioEl.duration) {
                currentPausedOffset = audioEl.currentTime || 0;
            }
            audioEl.pause();
            setNowPlaying(_labelFor(currentTrackName, true));
        } else if (msg.type === 'audio_stop') {
            currentTrackId      = null;
            currentCategory     = 'music';
            serverStartedAtMs   = null;
            currentPaused       = false;
            currentPausedOffset = 0;
            currentTrackName    = '';
            audioEl.pause();
            audioEl.removeAttribute('src');
            audioEl.load();
            setNowPlaying('Nothing playing');
            refreshCategoryVolUI();
            _setProgress(0, 0);
            _showProgress(false);
        }
    }
    document.addEventListener('vtt:ws-message', (ev) => handleMessage(ev.detail));

    // ---- track-end: ask server to advance ----
    audioEl.addEventListener('ended', async () => {
        if (!currentTrackId || typeof CAMPAIGN_ID === 'undefined') return;
        try {
            await fetch(`/campaign/${CAMPAIGN_ID}/audio/next`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({ track_id: currentTrackId }),
            });
        } catch (e) { console.warn('audio_next failed', e); }
    });

    // ---- Initial state from the server-rendered "now playing" ----
    const initial = root.dataset.initialPlay;
    if (initial) {
        try {
            const d = JSON.parse(initial);
            if (d && d.file_url) handleMessage({ type: 'audio_play', data: d });
        } catch (e) { /* ignore */ }
    }

    // ---- GM helpers ----
    window.vttPlayTrack = async function (trackId) {
        if (typeof CAMPAIGN_ID === 'undefined') return;
        const resp = await fetch(`/campaign/${CAMPAIGN_ID}/audio/play`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin', body: JSON.stringify({ track_id: trackId }),
        });
        if (!resp.ok) alert('Could not start track: ' + (await resp.text()));
    };
    window.vttStopAudio = async function () {
        if (typeof CAMPAIGN_ID === 'undefined') return;
        await fetch(`/campaign/${CAMPAIGN_ID}/audio/stop`, { method: 'POST', credentials: 'same-origin' });
    };
    window.vttResyncAudio = async function () {
        if (typeof CAMPAIGN_ID === 'undefined') return;
        await fetch(`/campaign/${CAMPAIGN_ID}/audio/resync`, { method: 'POST', credentials: 'same-origin' });
    };

    // ---- Transport controls (GM-only) ----
    // Idempotent fetches; the buttons disable themselves while pending.
    async function _audioPost(path) {
        if (typeof CAMPAIGN_ID === 'undefined') return;
        try {
            const resp = await fetch(`/campaign/${CAMPAIGN_ID}/audio/${path}`, {
                method: 'POST', credentials: 'same-origin',
            });
            if (!resp.ok) console.warn(`audio/${path} failed: HTTP ${resp.status}`);
        } catch (e) { console.warn(`audio/${path} failed:`, e); }
    }
    window.vttSkipTrack     = () => _audioPost('skip');
    window.vttPreviousTrack = () => _audioPost('previous');
    window.vttPauseAudio    = () => _audioPost('pause');
    window.vttResumeAudio   = () => _audioPost('resume');
    // Convenience: one toggle button can call this and the server figures
    // out whether to pause or resume based on current state.
    window.vttTogglePause   = () => currentPaused ? _audioPost('resume') : _audioPost('pause');

    // Expose state read so the UI button can render the right glyph.
    window.vttAudioIsPaused = () => currentPaused;
    window.vttAudioHasTrack = () => currentTrackId != null;
})();
