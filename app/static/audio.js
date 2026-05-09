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
    if (muteBtn) muteBtn.textContent = audioEl.muted ? '🔇 Unmute' : '🔈 Mute';

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
                if (muteBtn) muteBtn.textContent = '🔇 Unmute';
            } else if (masterVol > 0 && audioEl.muted) {
                audioEl.muted = false;
                localStorage.setItem(MUTE_KEY, '0');
                if (muteBtn) muteBtn.textContent = '🔈 Mute';
            }
            applyEffectiveVolume();
        });
    }
    if (muteBtn) {
        muteBtn.addEventListener('click', () => {
            audioEl.muted = !audioEl.muted;
            localStorage.setItem(MUTE_KEY, audioEl.muted ? '1' : '0');
            muteBtn.textContent = audioEl.muted ? '🔇 Unmute' : '🔈 Mute';
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
        seekToExpected();
        tryPlay();
    });
    setInterval(() => {
        if (!currentTrackId || serverStartedAtMs == null) return;
        if (audioEl.paused || !audioEl.duration) return;
        const expected = expectedPositionSeconds() % audioEl.duration;
        const drift = Math.abs(expected - audioEl.currentTime);
        const wrappedDrift = Math.min(drift, Math.abs(drift - audioEl.duration));
        if (wrappedDrift > DRIFT_THRESHOLD_S) audioEl.currentTime = expected;
    }, 5000);

    // ---- WS event handling ----
    function handleMessage(msg) {
        if (msg.type === 'audio_play') {
            const d = msg.data || {};
            currentTrackId    = d.track_id;
            currentCategory   = d.category || 'music';
            serverStartedAtMs = d.started_at_ms || Date.now();
            currentDuration   = 0;
            audioEl.src = d.file_url;
            setNowPlaying(`▶ ${d.name || ''}`);
            refreshCategoryVolUI();
            applyEffectiveVolume();
        } else if (msg.type === 'audio_stop') {
            currentTrackId    = null;
            currentCategory   = 'music';
            serverStartedAtMs = null;
            audioEl.pause();
            audioEl.removeAttribute('src');
            audioEl.load();
            setNowPlaying('Nothing playing');
            refreshCategoryVolUI();
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
})();
