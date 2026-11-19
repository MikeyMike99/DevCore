// Talk button: a hands-free voice conversation with the chat.
//
//   listen -> (is it my voice?) -> speech to text -> send to the chat -> speak the reply -> listen again
//
// Privacy: audio is handled on this device only. Speech-to-text and voice matching run in
// speech-worker.js (models served by Siraugga itself), and the reply is read out with a voice
// that is installed on this device (cloud voices are never used). Only the text you say goes
// to the chat, exactly like typing it.
//
// The chat keeps its own memory per conversation, so talking continues the current
// conversation until you start a new one (say "new conversation" or use the normal button).
(function () {
    'use strict';

    var btn = document.getElementById('talk-btn');
    var label = document.getElementById('talk-btn-label');
    var status = document.getElementById('mic-status');
    var notice = document.getElementById('mic-notice');
    var promptEl = document.getElementById('prompt');
    var form = document.getElementById('chat-form');
    var enrollBtn = document.getElementById('voice-enroll-btn');
    var forgetBtn = document.getElementById('voice-forget-btn');
    var enrollInfo = document.getElementById('voice-enroll-status');
    var thresholdEl = document.getElementById('voice-threshold');
    if (!btn || !promptEl || !form) return;

    var supported = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia &&
        window.Worker && window.WebAssembly && window.speechSynthesis);
    if (!supported) {
        btn.disabled = true;
        btn.title = 'Voice conversation is not supported in this browser';
        return;
    }

    var PRINT_KEY = 'siraugga.voice.print';          // the enrolled voice print (never leaves this device)
    var THRESH_KEY = 'siraugga.voice.threshold';
    var DEFAULT_THRESHOLD = 0.85;
    var MAX_CLIP_SECONDS = 40;
    var END_SILENCE_MS = 1400;                        // pause that ends your turn (you can also tap the button when you are done)
    var END_SILENCE_EARLY_MS = 2200;                  // ...while you have spoken for less than 2 s (people pause early to think)
    var roomNoise = null;                             // remembered between turns AND sessions (see recordTurn, loadNoise)
    var NOISE_KEY = 'siraugga.voice.roomNoise';
    function loadNoise() {                            // start low: a high first guess hides faint speech that begins right away
        var v = NaN;
        try { v = parseFloat(localStorage.getItem(NOISE_KEY)); } catch (_) {}
        return isFinite(v) && v > 0.0003 && v < 0.02 ? v : 0.0008;
    }
    function saveNoise() { try { localStorage.setItem(NOISE_KEY, String(roomNoise)); } catch (_) {} }
    // A turn that produced no words, or only noise, means the level was set too low for this room: raise it.
    function raiseNoise() { roomNoise = Math.min(0.01, Math.max(roomNoise || 0.0008, 0.001) * 1.8); saveNoise(); }
    var MIC_KEY = 'siraugga.voice.micId';             // chosen microphone ('' = the system default)
    var IDLE_TIMEOUT_MS = 3 * 60 * 1000;              // mic switches itself off after 3 quiet minutes
    var MAX_SPOKEN_CHARS = 700;

    var state = 'off';                                // off | listening | thinking | speaking | enrolling
    var worker = null;
    var nextId = 1;
    var pending = {};                                 // worker request id -> {resolve, reject}
    var noticeTimer = null;
    var savedModel = null;                            // model the user had before voice mode
    var watchdog = null;
    var memoryStore = {};

    // ---- small storage helpers -----------------------------------------------
    function store(key, value) {
        if (value === undefined) { try { return localStorage.getItem(key); } catch (_) { return memoryStore[key] || null; } }
        memoryStore[key] = value;
        try { if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value); } catch (_) {}
    }
    function getPrint() {
        try { var p = JSON.parse(store(PRINT_KEY) || 'null'); return Array.isArray(p) && p.length ? p : null; } catch (_) { return null; }
    }
    function getThreshold() {
        var t = parseFloat(store(THRESH_KEY));
        return isFinite(t) && t > 0.5 && t < 0.99 ? t : DEFAULT_THRESHOLD;
    }

    // ---- UI helpers ----------------------------------------------------------
    // A visible status box above the message box. It shows every step while voice is on, and
    // problems stay on screen until the next step (they used to vanish after a few seconds).
    var panel = document.createElement('div');
    panel.id = 'voice-live';
    panel.setAttribute('aria-hidden', 'true');        // for people who can see it; screen readers get #mic-status instead (no double reading)
    panel.className = 'hidden text-sm rounded-lg px-3 py-2 mb-2 border';
    form.parentNode.insertBefore(panel, form);

    // A level bar for people who can see it: shows how loud the microphone hears you while it is listening.
    var meter = document.createElement('div');
    meter.id = 'voice-meter';
    meter.setAttribute('aria-hidden', 'true');
    meter.className = 'hidden h-2 rounded bg-slate-800 border border-slate-700 mb-2 overflow-hidden';
    var meterBar = document.createElement('div');
    meterBar.className = 'h-full bg-teal-500';
    meterBar.style.width = '0%';
    meter.appendChild(meterBar);
    form.parentNode.insertBefore(meter, form);
    function showLevel(level) {
        var db = 20 * Math.log10(Math.max(level, 1e-5));              // -60 dB (silence) ... -10 dB (loud)
        meterBar.style.width = Math.max(0, Math.min(100, (db + 60) / 50 * 100)) + '%';
    }

    // Which microphone to use. Names only appear once the browser has given permission.
    var micSelect = document.getElementById('voice-mic-select');
    async function refreshMics() {
        if (!micSelect || !navigator.mediaDevices.enumerateDevices) return;
        try {
            var devs = await navigator.mediaDevices.enumerateDevices();
            var ins = devs.filter(function (d) { return d.kind === 'audioinput' && d.deviceId !== 'default' && d.deviceId !== 'communications'; });
            var cur = store(MIC_KEY) || '';
            micSelect.innerHTML = '';
            var first = document.createElement('option'); first.value = ''; first.textContent = 'System default'; micSelect.appendChild(first);
            ins.forEach(function (d, i) {
                var o = document.createElement('option'); o.value = d.deviceId; o.textContent = d.label || ('Microphone ' + (i + 1)); micSelect.appendChild(o);
            });
            micSelect.value = ins.some(function (d) { return d.deviceId === cur; }) ? cur : '';
        } catch (_) {}
    }

    // Replies are announced through this region so the user's own screen reader reads them (ARIA),
    // instead of a second computer voice talking over it.
    var ariaEl = document.createElement('div');
    ariaEl.id = 'voice-aria';
    ariaEl.className = 'sr-only';
    ariaEl.setAttribute('aria-live', 'assertive');
    ariaEl.setAttribute('aria-atomic', 'true');
    document.body.appendChild(ariaEl);
    function announce(text) {
        ariaEl.textContent = '';                       // clear first so the same words are announced again
        setTimeout(function () { ariaEl.textContent = text; }, 80);
    }
    var TTS_KEY = 'siraugga.voice.deviceVoice';       // '1' = read replies with a device voice instead of ARIA
    function getUseTts() { return store(TTS_KEY) === '1'; }
    function paint(text, kind) {
        panel.textContent = text;
        panel.className = 'text-sm rounded-lg px-3 py-2 mb-2 border ' + (kind === 'error'
            ? 'text-red-200 bg-red-950/60 border-red-700/60'
            : kind === 'ok' ? 'text-emerald-200 bg-emerald-950/50 border-emerald-700/60'
            : 'text-teal-200 bg-slate-900 border-teal-700/60');
    }
    function liveQuiet(text, kind) {                   // visible only; NOT announced. Used while the microphone is open, so a
        paint(text, kind || 'ok');                     // screen reader does not speak into it (it would be heard as your voice)
    }
    function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
    function readTimeMs(text) { return Math.max(1500, Math.round((String(text).match(/\S+/g) || []).length / 3.2 * 1000) + 1500); }
    // Say something (screen reader), wait long enough for it to be read, and only then open the microphone again.
    async function noteThenListen(text, kind) {
        live(text, kind);
        await sleep(readTimeMs(text));
        if (state !== 'off') return listen();
    }
    function say(text) { if (status) status.textContent = text; }
    function live(text, kind) {                       // kind: 'info' (default) | 'error' | 'ok'
        say(text);
        try { console.log('[voice]', text); } catch (_) {}
        kind = kind || 'info';
        panel.textContent = text;
        panel.className = 'text-sm rounded-lg px-3 py-2 mb-2 border ' + (kind === 'error'
            ? 'text-red-200 bg-red-950/60 border-red-700/60'
            : kind === 'ok' ? 'text-emerald-200 bg-emerald-950/50 border-emerald-700/60'
            : 'text-teal-200 bg-slate-900 border-teal-700/60');
        if (noticeTimer) clearTimeout(noticeTimer);
        if (state === 'off') noticeTimer = setTimeout(function () { if (state === 'off' && kind !== 'error') panel.classList.add('hidden'); }, 15000);
    }
    function show(text) { live(text, 'info'); }
    function problem(text) { live(text, 'error'); }
    function setState(s, text) {
        state = s;
        var on = s !== 'off';
        btn.setAttribute('aria-pressed', on ? 'true' : 'false');
        btn.classList.toggle('mic-recording', s === 'listening');
        meter.classList.toggle('hidden', s !== 'listening');
        if (label) label.textContent = text || (on ? 'Stop talking' : 'Talk');
    }
    function refreshEnrollUi() {
        var has = !!getPrint();
        if (enrollInfo) enrollInfo.textContent = has
            ? 'Your voice is saved on this device. Other voices are ignored.'
            : 'No voice saved yet, so it will answer to any voice.';
        if (forgetBtn) forgetBtn.disabled = !has;
        if (thresholdEl) thresholdEl.value = String(getThreshold());
    }

    // ---- cues (same idea as dictation.js: sounds instead of speech) ----------
    var cueCtx = null;
    function cue(freqs) {
        try {
            var Ctx = window.AudioContext || window.webkitAudioContext;
            if (!cueCtx || cueCtx.state === 'closed') cueCtx = new Ctx();
            if (cueCtx.state === 'suspended') cueCtx.resume();
            var t = cueCtx.currentTime;
            freqs.forEach(function (f, i) {
                var o = cueCtx.createOscillator(), g = cueCtx.createGain();
                o.type = 'sine'; o.frequency.value = f;
                o.connect(g); g.connect(cueCtx.destination);
                var a = t + i * 0.1;
                g.gain.setValueAtTime(0.0001, a);
                g.gain.exponentialRampToValueAtTime(0.18, a + 0.015);
                g.gain.exponentialRampToValueAtTime(0.0001, a + 0.09);
                o.start(a); o.stop(a + 0.1);
            });
        } catch (_) {}
    }
    function cueHeard() { cue([880]); }               // "got it, working on it"

    // ---- worker --------------------------------------------------------------
    async function diagnoseEngine() {
        var files = [
            ['worker', '/static/speech/speech-worker.js?v=10'],
            ['engine', '/static/speech/vendor/transformers.min.js?v=2'],
            ['runtime', '/static/speech/vendor/ort-wasm-simd-threaded.jsep.mjs'],
            ['wasm', '/static/speech/vendor/ort-wasm-simd-threaded.jsep.wasm'],
            ['speech model', '/static/speech/models/Xenova/whisper-tiny.en/config.json'],
        ];
        var parts = [];
        for (var i = 0; i < files.length; i++) {
            try {
                var r = await fetch(files[i][1], { method: 'HEAD', cache: 'no-store' });
                parts.push(files[i][0] + ' ' + r.status);
            } catch (err) {
                parts.push(files[i][0] + ' unreachable');
            }
        }
        var script = document.querySelector('script[src*="speech/voice.js"]');
        var ver = script && (script.getAttribute('src').match(/v=(\d+)/) || [])[1];
        return 'Checked on ' + location.host + ' (page version ' + (ver || '?') + ', ' + (cpuMode() ? 'processor mode' : 'graphics-card mode') +
            ', last step: ' + (lastStage || 'none') + '): ' + parts.join(', ') + '.';
    }

    // Model download progress: always shown on screen, and announced only at 25% steps (not on every tick).
    var loadFiles = {}, loadAnnounced = 0;
    function onLoadProgress(m) {
        if (state === 'off' || state === 'listening') return;
        loadFiles[m.file] = [m.loaded, m.total];
        var L = 0, T = 0;
        Object.keys(loadFiles).forEach(function (k) { L += loadFiles[k][0]; T += loadFiles[k][1]; });
        if (!T) return;
        // Files are discovered one at a time, so count against the whole expected download (not just what is known so
        // far); otherwise the percentage jumps backwards when the next, bigger file starts.
        var expected = Math.max(T, cpuMode() ? 41e6 : 147e6);
        var pct = Math.min(99, Math.round(L / expected * 100));
        var text = 'Loading the speech model: ' + pct + '% (' + Math.round(L / 1e6) + ' of about ' + Math.round(expected / 1e6) + ' MB). First time only; it is saved on this device afterwards.';
        var step = Math.floor(pct / 25) * 25;
        if (step > loadAnnounced) { loadAnnounced = step; live(text); } else { liveQuiet(text, 'info'); }
    }

    // If the worker dies while it is running (some graphics drivers do that), run it on the processor from then on.
    var CPU_KEY = 'siraugga.speech.cpu';
    var lastStage = '';
    function cpuMode() { return store(CPU_KEY) === '1'; }

    function getWorker() {
        if (worker) return worker;
        worker = new Worker('/static/speech/speech-worker.js?v=10' + (cpuMode() ? '&cpu=1' : ''), { type: 'module' });
        worker.onmessage = function (e) {
            var m = e.data || {};
            if (m.type === 'stage') { lastStage = m.stage || ''; return; }
            if (m.type === 'progress') { onLoadProgress(m); return; }
            var p = pending[m.id];
            if (!p) return;
            delete pending[m.id];
            if (m.type === 'error') p.reject(new Error(m.message));
            else p.resolve(m);
        };
        worker.onerror = function (e) {
            worker = null;
            var detail = e && e.message ? ' (' + e.message + ')' : '';
            // A worker that fails to start gives the browser nothing to report, so check each file it needs and say which one is wrong.
            diagnoseEngine().then(function (report) {
                Object.keys(pending).forEach(function (k) {
                    var err = new Error('The voice worker stopped' + detail + '. ' + report);
                    err.crashed = true;
                    pending[k].reject(err);
                    delete pending[k];
                });
            });
        };
        return worker;
    }
    function askOnce(type, audio) {
        return new Promise(function (resolve, reject) {
            var id = nextId++;
            pending[id] = { resolve: resolve, reject: reject };
            getWorker().postMessage({ type: type, id: id, audio: audio });
        });
    }
    function ask(type, audio) {
        return askOnce(type, audio).catch(function (err) {
            if (err && err.crashed && !cpuMode()) {         // first crash: switch to the safe mode and try once more
                store(CPU_KEY, '1');
                worker = null;
                live('The speech engine stopped, so I am switching to the slower, safer mode and trying again.');
                return askOnce(type, audio);
            }
            throw err;
        });
    }

    // ---- voice matching ------------------------------------------------------
    function cosine(a, b) {
        var n = Math.min(a.length, b.length), s = 0;
        for (var i = 0; i < n; i++) s += a[i] * b[i];
        return s;                                      // both are unit length
    }
    function average(vectors) {
        var out = new Array(vectors[0].length).fill(0);
        vectors.forEach(function (v) { for (var i = 0; i < out.length; i++) out[i] += v[i] / vectors.length; });
        var norm = Math.sqrt(out.reduce(function (s, v) { return s + v * v; }, 0)) || 1;
        return out.map(function (v) { return v / norm; });
    }

    // ---- microphone capture with simple silence detection --------------------
    function rms(buf) {
        var s = 0;
        for (var i = 0; i < buf.length; i++) s += buf[i] * buf[i];
        return Math.sqrt(s / (buf.length || 1));
    }
    // Averages groups of samples down to 16 kHz (Whisper and the voice model both expect it).
    function to16k(float32, rate) {
        if (rate === 16000) return float32;
        var ratio = rate / 16000, len = Math.floor(float32.length / ratio), out = new Float32Array(len);
        for (var i = 0; i < len; i++) {
            var a = Math.floor(i * ratio), b = Math.max(a + 1, Math.floor((i + 1) * ratio)), s = 0;
            for (var j = a; j < b && j < float32.length; j++) s += float32[j];
            out[i] = s / (b - a);
        }
        return out;
    }

    // Records one spoken turn. Resolves with {audio} (16 kHz mono), or {audio:null} on timeout / stop.
    // opts.fixedSeconds records exactly that long (used for enrolment) instead of waiting for silence.
    // Noise suppression and echo cancellation are OFF on purpose: they are meant for calls, and they remove quiet or distant
    // voices (you had to be right next to the microphone). Automatic gain is ON, so quiet speech is boosted instead.
    function openMic() {
        var base = { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: true };
        var id = store(MIC_KEY);
        if (id) {
            var withId = Object.assign({ deviceId: { exact: id } }, base);
            return navigator.mediaDevices.getUserMedia({ audio: withId }).catch(function (err) {
                if (err && err.name === 'NotAllowedError') throw err;
                return navigator.mediaDevices.getUserMedia({ audio: base });      // the chosen microphone is gone: use the default
            });
        }
        return navigator.mediaDevices.getUserMedia({ audio: base });
    }

    // Quiet speech is made louder before the speech model hears it (a small model does much worse on quiet audio).
    // Returns the audio and how loud it originally was (its 99.5th-percentile level).
    function boost(a) {
        var n = a.length;
        if (!n) return { audio: a, peak: 0 };
        var step = Math.max(1, Math.floor(n / 4000)), vals = [];
        for (var i = 0; i < n; i += step) vals.push(Math.abs(a[i]));
        vals.sort(function (x, y) { return x - y; });
        var peak = vals[Math.floor(vals.length * 0.995)] || 0;
        if (peak < 1e-4) return { audio: a, peak: peak };
        var gain = Math.min(30, 0.5 / peak);
        if (gain <= 1.05) return { audio: a, peak: peak };
        var out = new Float32Array(n);
        for (var j = 0; j < n; j++) { var v = a[j] * gain; out[j] = v > 1 ? 1 : v < -1 ? -1 : v; }
        return { audio: out, peak: peak };
    }

    // Microphone sensitivity (Settings): 1 = needs a clear, close voice ... 5 = picks up faint, distant voices (and more noise).
    var SENS_KEY = 'siraugga.voice.sensitivity';
    function getSens() { var s = parseInt(store(SENS_KEY), 10); return s >= 1 && s <= 5 ? s : 3; }
    function sensitivityScale() { return [1.6, 1.25, 1.0, 0.75, 0.55][getSens() - 1]; }

    var dbg = { level: 0, threshold: 0, roomNoise: 0, speaking: false, frames: 0 };     // read through window.sirauggaVoice.stats()
    var lastMicName = '';
    var heardSomething = false;                       // anything at all picked up during this voice session
    // Nothing heard for 12 s at the start of a session: say so, because from the outside "nothing happens" looks like "broken".
    // It is read by the screen reader while the microphone is open, so it is remembered like a reply and ignored if the mic hears it.
    function quietHint() {
        if (state !== 'listening') return;
        var note = 'I cannot hear you yet. Move closer to the microphone, or choose a different microphone in Settings.';
        rememberReply(note);
        live(note, 'error');
    }
    function recordTurn(opts) {
        opts = opts || {};
        if (roomNoise === null) roomNoise = loadNoise();
        return new Promise(function (resolve, reject) {
            var Ctx = window.AudioContext || window.webkitAudioContext;
            openMic().then(function (stream) {
                try { lastMicName = (stream.getAudioTracks()[0] || {}).label || ''; } catch (_) {}
                refreshMics();                                  // labels of the microphones are only available once permission is given
                var ctx = new Ctx();
                var src = ctx.createMediaStreamSource(stream);
                var proc = ctx.createScriptProcessor(4096, 1, 1);
                var mute = ctx.createGain(); mute.gain.value = 0;    // keep the node alive without echoing the mic
                src.connect(proc); proc.connect(mute); mute.connect(ctx.destination);

                var frameMs = 4096 / ctx.sampleRate * 1000;
                var preRoll = [], frames = [], speaking = false, loud = 0, silentMs = 0, heardMs = 0, voicedMs = 0;
                var finished = false, started = Date.now(), recentLoud = [], hinted = false;
                var session = {
                    cancel: function () { finish(null); },
                    hasSpeech: function () { return speaking && voicedMs > 250; },     // something real has been said
                    finishNow: function () { if (speaking) finish(concat(frames)); },   // "I am done": send what was said now
                };
                currentSession = session;

                function finish(audio) {
                    if (finished) return;
                    finished = true;
                    currentSession = null;
                    try { proc.disconnect(); src.disconnect(); mute.disconnect(); } catch (_) {}
                    stream.getTracks().forEach(function (t) { t.stop(); });
                    var rate = ctx.sampleRate;
                    try { ctx.close(); } catch (_) {}
                    saveNoise();
                    var boosted = audio ? boost(to16k(audio, rate)) : null;
                    resolve({ audio: boosted ? boosted.audio : null, peak: boosted ? boosted.peak : 0, voicedMs: voicedMs });
                }

                proc.onaudioprocess = function (ev) {
                    if (finished) return;
                    var data = new Float32Array(ev.inputBuffer.getChannelData(0));
                    var level = rms(data);

                    if (opts.fixedSeconds) {
                        frames.push(data);
                        if ((Date.now() - started) / 1000 >= opts.fixedSeconds) finish(concat(frames));
                        return;
                    }

                    // No "measuring" delay: the room noise level is remembered from earlier turns and adapts slowly from quiet
                    // moments. (It used to spend the first half second measuring and throw that audio away, so a sentence that
                    // began right after the beep lost its start, or was taken for background noise and never heard at all.)
                    // The "you are speaking" level follows the room noise (at least 3.5x louder), with a low floor so quiet or
                    // distant speech still counts. It used to have to be at least 0.01 (about -40 dB), too loud for many voices.
                    var threshold = Math.max(0.0012, Math.min(0.03, Math.max(0.0025, roomNoise * 3)) * sensitivityScale());
                    showLevel(level);
                    dbg.level = level; dbg.threshold = threshold; dbg.roomNoise = roomNoise; dbg.speaking = speaking; dbg.frames++;
                    if (!speaking) {
                        preRoll.push(data); if (preRoll.length > 6) preRoll.shift();     // keep ~0.5 s from before the first loud moment
                        recentLoud.push(level > threshold ? 1 : 0); if (recentLoud.length > 4) recentLoud.shift();
                        // The room-noise estimate falls quickly but rises only very slowly, and has a ceiling. Otherwise the quiet
                        // moments of faint speech teach it that "speech is noise" and the level creeps up until nothing is heard.
                        if (level < roomNoise) roomNoise = Math.max(0.0003, 0.85 * roomNoise + 0.15 * level);   // floor: digital silence must not drag it to zero
                        else if (level <= threshold) roomNoise = Math.min(0.006, 0.998 * roomNoise + 0.002 * level);
                        // Speech starts when at least 2 of the last 4 moments were above the level (not necessarily in a row:
                        // quiet or distant speech rises and falls around the level).
                        if (recentLoud.reduce(function (a, b) { return a + b; }, 0) >= 2) {
                            speaking = true; frames = preRoll.slice(); silentMs = 0; heardMs = 0; voicedMs = 0;
                            if (label) label.textContent = 'Listening… (tap when done)';
                        }
                        else if (Date.now() - started > IDLE_TIMEOUT_MS) finish(null);
                        else if (!hinted && !heardSomething && Date.now() - started > 12000) { hinted = true; quietHint(); }
                    } else {
                        frames.push(data);
                        heardMs += frameMs;
                        heardSomething = true;
                        if (level > threshold * 0.7) { silentMs = 0; voicedMs += frameMs; } else { silentMs += frameMs; }   // a bit easier to keep going than to start
                        // People pause to think, most of all near the start of a sentence, so wait longer until you have
                        // actually spoken for a few seconds (time spent in silence does not count towards that).
                        var allowedSilence = voicedMs < 2000 ? END_SILENCE_EARLY_MS : END_SILENCE_MS;
                        if (silentMs >= allowedSilence || heardMs >= MAX_CLIP_SECONDS * 1000) finish(concat(frames));
                    }
                };
            }).catch(reject);
        });
    }
    var currentSession = null;
    function concat(chunks) {
        var n = 0; chunks.forEach(function (c) { n += c.length; });
        var out = new Float32Array(n), o = 0;
        chunks.forEach(function (c) { out.set(c, o); o += c.length; });
        return out;
    }

    // ---- speaking ------------------------------------------------------------
    var voices = [];
    function loadVoices() { voices = window.speechSynthesis.getVoices() || []; }
    loadVoices();
    if (window.speechSynthesis.addEventListener) window.speechSynthesis.addEventListener('voiceschanged', loadVoices);

    // Only voices installed on this device: browser "online"/cloud voices would send the reply text away.
    function pickVoice() {
        var local = voices.filter(function (v) { return v.localService; });
        var lang = (navigator.language || 'en').toLowerCase();
        return local.filter(function (v) { return v.lang && v.lang.toLowerCase() === lang; })[0] ||
            local.filter(function (v) { return v.lang && v.lang.toLowerCase().indexOf(lang.slice(0, 2)) === 0; })[0] ||
            local[0] || null;
    }

    // Markdown to something that sounds right when read out.
    function spokenVersion(md, cap) {
        cap = cap || MAX_SPOKEN_CHARS;
        var t = String(md || '');
        t = t.replace(/```[\s\S]*?```/g, ' (code on screen) ');
        t = t.replace(/<[^>]+>/g, ' ');
        t = t.replace(/!\[[^\]]*\]\([^)]*\)/g, ' ');
        t = t.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');
        t = t.replace(/https?:\/\/\S+/g, ' a link ');
        t = t.replace(/`([^`]*)`/g, '$1');
        t = t.replace(/^[#>\-*+\d.\s]+(?=\S)/gm, function (m) { return /\d/.test(m) ? m.replace(/[^\d.]/g, '') + ' ' : ''; });
        t = t.replace(/[*_~|#]+/g, '');
        t = t.replace(/\s+/g, ' ').trim();
        if (t.length > cap) {
            var cut = t.slice(0, cap);
            var end = Math.max(cut.lastIndexOf('. '), cut.lastIndexOf('? '), cut.lastIndexOf('! '));
            t = (end > 200 ? cut.slice(0, end + 1) : cut) + ' The rest is on screen.';
        }
        return t;
    }

    function speak(text) {
        return new Promise(function (resolve) {
            var voice = pickVoice();
            if (!voice) { show('No voice is installed on this device, so replies are shown but not spoken.'); resolve(); return; }
            if (!text) { resolve(); return; }
            var parts = text.match(/[^.!?]+[.!?]*\s*/g) || [text];
            var i = 0;
            function next() {
                if (state !== 'speaking' || i >= parts.length) { resolve(); return; }
                var u = new SpeechSynthesisUtterance(parts[i++]);
                u.voice = voice; u.lang = voice.lang;
                u.onend = next; u.onerror = next;
                window.speechSynthesis.speak(u);
            }
            window.speechSynthesis.cancel();
            next();
        });
    }
    function stopSpeaking() { try { window.speechSynthesis.cancel(); } catch (_) {} }

    // ---- the conversation loop ----------------------------------------------
    // A result that is the same few words over and over (or mostly one repeated phrase) is the speech model making things up
    // on noise, not something you said.
    function looksLikeLoop(text) {
        var w = wordsOf(text);
        if (w.length < 10) return false;
        var counts = {}, top = 0;
        for (var i = 0; i + 2 < w.length; i++) {
            var g = w[i] + ' ' + w[i + 1] + ' ' + w[i + 2];
            counts[g] = (counts[g] || 0) + 1;
            if (counts[g] > top) top = counts[g];
        }
        var unique = new Set(w).size;
        return top >= 4 || (w.length >= 16 && unique / w.length < 0.3);
    }

    function normalise(t) { return String(t || '').toLowerCase().replace(/[^a-z ]/g, ' ').replace(/\s+/g, ' ').trim(); }
    function cleanup(text) { return (text || '').replace(/\[[^\]]*\]|\([^)]*\)/g, ' ').replace(/\s+/g, ' ').trim(); }

    function agentCount() { return document.querySelectorAll('article[data-sender="agent"]').length; }
    function lastReply() {
        var all = document.querySelectorAll('article[data-sender="agent"]');
        var el = all[all.length - 1];
        if (!el) return '';
        return (el.dataset.rawMarkdown || '').trim() || (el.innerText || '').slice(0, 2000);
    }

    var waitingForReply = false;
    function onTaskFinished() {
        if (!waitingForReply || state !== 'thinking') return;
        waitingForReply = false;
        if (watchdog) { clearTimeout(watchdog); watchdog = null; }
        var useVoice = getUseTts();
        var reply = spokenVersion(lastReply(), useVoice ? MAX_SPOKEN_CHARS : 1500);
        rememberReply(reply);
        if (useVoice) {
            setState('speaking', 'Speaking (tap to talk now)');
            live('Reply received. Reading it out…', 'ok');
            speak(reply).then(function () {
                if (state === 'speaking') listen();
            });
            return;
        }
        // Default: the screen reader reads the reply (ARIA). It gives no "finished" signal, so wait about as
        // long as reading takes before the microphone opens again, so the mic does not hear the screen reader.
        setState('speaking', 'Reading reply… (tap to talk now)');
        liveQuiet('Reply: ' + reply);
        announce(reply || 'The reply is on screen.');
        var words = (reply.match(/\S+/g) || []).length;
        ariaTimer = setTimeout(function () {
            ariaTimer = null;
            if (state === 'speaking') listen();
        }, Math.max(2500, Math.round(words / 4.5 * 1000) + 1500));      // ~270 words a minute plus a pause; tap the button to skip the wait
    }
    var ariaTimer = null;
    var lastReplyWords = null, lastReplyAt = 0;
    function wordsOf(t) { return (String(t || '').toLowerCase().match(/[a-z']+/g) || []); }
    function rememberReply(reply) { lastReplyWords = new Set(wordsOf(reply)); lastReplyAt = Date.now(); }
    // The microphone can pick up the reply being read out loud; if what it heard is mostly the reply's own words, ignore it.
    function looksLikeEcho(text) {
        if (!lastReplyWords || Date.now() - lastReplyAt > 120000) return false;
        var w = wordsOf(text);
        if (w.length < 3) return false;
        var hit = w.filter(function (x) { return lastReplyWords.has(x); }).length;
        return hit / w.length >= 0.6;
    }
    // The page calls finishTaskUI() when a task ends; wrap it so the reply can be read out.
    function hookFinish() {
        var orig = window.finishTaskUI;
        if (typeof orig !== 'function' || orig.__voiceHooked) return !!orig;
        var wrapped = function () {
            var r = orig.apply(this, arguments);
            try { onTaskFinished(); } catch (err) { console.error('[voice]', err); }
            return r;
        };
        wrapped.__voiceHooked = true;
        window.finishTaskUI = wrapped;
        return true;
    }

    async function listen() {
        if (state === 'off') return;
        setState('listening', 'Listening… (tap to stop)');
        // A beep (not speech) says "the microphone is open, talk now": speech from a screen reader would be picked up by it.
        liveQuiet('Listening… speak now, then pause when you are done.' + (lastMicName ? ' Microphone: ' + lastMicName : ''), 'info');
        cue([660, 990]);
        await sleep(350);                              // let the beep end before the microphone starts measuring the room
        if (state === 'off') return;
        var turn;
        try {
            turn = await recordTurn();
        } catch (err) {
            var msg = err && err.name === 'NotAllowedError'
                ? 'Microphone access was blocked. Allow it in your browser to talk.'
                : 'No microphone could be opened (' + ((err && (err.name || err.message)) || 'error') + ').';
            stopVoice();
            return problem(msg);
        }
        if (state === 'off') return;
        var injected = injectedText; injectedText = null;
        if (!turn.audio && !injected) { stopVoice(); return show('Stopped listening after a quiet while.'); }
        if (!injected) {
            if (turn.voicedMs < 350) return listen();                       // a click or a cough, not speech: just keep listening
            if (turn.peak < 0.006) {                                        // even the loudest part was very faint
                return noteThenListen('I could hardly hear you. Move closer to the microphone, or raise its volume in Windows sound settings.', 'error');
            }
        }

        setState('thinking', 'Working…');
        try {
            if (injected) {                               // typed through window.sirauggaVoice.say() (testing without a microphone)
                live('Using typed text: “' + injected + '”');
                return await handleText(injected);
            }
            var print = getPrint();
            if (print) {
                live('Heard you. Checking that it is your voice… (the first time loads the voice model, about 100 MB)');
                var emb = (await ask('embed', turn.audio)).embedding;
                if (state === 'off') return;
                var score = cosine(print, emb);
                if (score < getThreshold()) {
                    return noteThenListen('That did not sound like you, so it was ignored. Match ' + score.toFixed(2) + ', needs ' + getThreshold().toFixed(2) + '. Lower the strictness in Settings if this is wrong.', 'error');
                }
            }
            live('Turning your speech into text… (the first time loads the speech model)');
            var text = cleanup((await ask('transcribe', turn.audio)).text);
            if (state === 'off') return;
            if (!text) { raiseNoise(); return noteThenListen('I did not catch any words.'); }
            if (looksLikeLoop(text)) { raiseNoise(); return noteThenListen('That was mostly noise, so it was ignored. Check that nothing else is playing sound near the microphone.'); }
            if (looksLikeEcho(text)) return noteThenListen('That sounded like the reply being read out, so it was ignored.');
            await handleText(text);
        } catch (err) {
            console.error('[voice]', err);
            stopVoice();
            problem('Voice conversation hit a problem: ' + ((err && err.message) || err));
        }
    }

    async function handleText(text) {
        var cmd = normalise(text);
        if (/^(stop|stop it|stop listening|stop talking|stop voice|turn off|turn it off|voice off|cancel|goodbye|good bye|bye|that is all|thats all|that s all)$/.test(cmd)) {
            show('Stopped listening.');
            return stopVoice();
        }
        if (/^(new conversation|new chat|start a new conversation|start over)$/.test(cmd) && typeof window.newConversation === 'function') {
            say('Starting a new conversation');
            await window.newConversation();
            return listen();
        }
        if (window.isTaskRunning) {                     // Send would "steer" a running task; don't do that by voice
            show('A task is still running, so that was not sent. Say it again when it finishes.');
            return listen();
        }
        cueHeard();
        live('You said: “' + text + '”. Sending… waiting for the reply.', 'ok');
        promptEl.value = text;
        promptEl.dispatchEvent(new Event('input', { bubbles: true }));
        var before = agentCount();
        waitingForReply = true;
        // Tell the page this is a spoken message: no card shortcuts, plain conversation (read by sendPrompt synchronously).
        window.__sirauggaVoiceTurn = true;
        try {
            if (typeof form.requestSubmit === 'function') form.requestSubmit(); else form.dispatchEvent(new Event('submit', { cancelable: true }));
        } finally {
            window.__sirauggaVoiceTurn = false;
        }
        // If nothing started (a slash command, a closed connection...) go back to listening.
        watchdog = setTimeout(function () {
            watchdog = null;
            if (waitingForReply && state === 'thinking' && agentCount() === before && !window.isTaskRunning) {
                waitingForReply = false;
                noteThenListen('The message did not start a reply. Is the connection open?', 'error');
            }
        }, 10000);
    }

    function useHaiku(on) {
        var sel = window.modelSelector || document.getElementById('model-selector');
        if (!sel) return;
        if (on) {
            var opt = Array.prototype.filter.call(sel.options, function (o) { return /haiku/i.test(o.value); })[0];
            if (opt && sel.value !== opt.value) {
                savedModel = sel.value;
                sel.value = opt.value;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
            }
        } else if (savedModel) {
            sel.value = savedModel;
            sel.dispatchEvent(new Event('change', { bubbles: true }));
            savedModel = null;
        }
    }

    // The speech engine is a set of files this site has to be able to serve. If they are missing (for example on a
    // static copy of the site built without them) say so plainly, instead of a worker that dies with no explanation.
    async function enginePresent() {
        try {
            var r = await fetch('/static/speech/vendor/transformers.min.js?v=2', { method: 'HEAD', cache: 'no-store' });
            return r.ok;
        } catch (_) { return false; }
    }

    async function startVoice() {
        if (state !== 'off') return;
        heardSomething = false;
        setState('thinking', 'Starting…');
        if (!(await enginePresent())) {
            setState('off');
            return problem('The speech files are not available at ' + location.host + '. Open https://siraugga.mikeytech.dev to use voice.');
        }
        hookFinish();
        useHaiku(true);
        // Load the speech model BEFORE opening the microphone, and say so: the first time it is a download of about
        // 150 MB, and talking to something that is not ready yet looks exactly like "nothing happens".
        loadFiles = {}; loadAnnounced = 0;
        live('Getting ready. Loading the speech model. The first time takes about a minute; after that it is quick.');
        try {
            await ask('load');
        } catch (err) {
            console.error('[voice]', err);
            stopVoice();
            return problem('The speech model could not be loaded: ' + ((err && err.message) || err));
        }
        if (state === 'off') return;                       // you pressed the button again while it was loading
        cue([660, 990, 1320]);                             // three rising notes: ready
        liveQuiet('Ready (' + (/processor/.test(lastStage) ? 'processor mode, a little slower' : 'graphics card, fastest') + ').', 'ok');
        setState('listening', 'Starting…');                // listen() does nothing while the state is 'off'
        listen();
    }
    function stopVoice() {
        waitingForReply = false;
        if (watchdog) { clearTimeout(watchdog); watchdog = null; }
        if (ariaTimer) { clearTimeout(ariaTimer); ariaTimer = null; }
        stopSpeaking();
        if (currentSession) currentSession.cancel();
        useHaiku(false);
        setState('off');
        say('Voice conversation off');
        live('Voice conversation off.');
    }

    btn.addEventListener('click', function () {
        if (state === 'off') startVoice();
        else if (state === 'enrolling') return;
        else if (state === 'listening' && currentSession && currentSession.hasSpeech()) currentSession.finishNow();   // tap when done: send now
        else if (state === 'speaking') skipReading();                                                               // tap while the reply is read: talk now
        else stopVoice();                                                                                           // otherwise tap = stop
    });
    // Skip the wait for the screen reader (or the device voice) and open the microphone straight away.
    function skipReading() {
        if (ariaTimer) { clearTimeout(ariaTimer); ariaTimer = null; }
        setState('listening', 'Listening…');               // set first so a finishing device voice does not also start listening
        stopSpeaking();
        listen();
    }
    // Escape switches voice off completely, from anywhere on the page.
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && state !== 'off' && state !== 'enrolling') { e.preventDefault(); stopVoice(); }
    });

    // ---- teach it my voice ---------------------------------------------------
    var ENROL_LINES = [
        'The quick brown fox jumps over the lazy dog.',
        'Please open the plan and read me the next step.',
        'I am setting up my voice so that only I can start the conversation.',
    ];
    async function enrol() {
        if (state !== 'off') { show('Stop the voice conversation first.'); return; }
        setState('enrolling', 'Teaching…');
        enrollBtn.disabled = true;
        try {
            var prints = [];
            for (var i = 0; i < ENROL_LINES.length; i++) {
                show('Sentence ' + (i + 1) + ' of ' + ENROL_LINES.length + '. After the beep, say: ' + ENROL_LINES[i]);
                await new Promise(function (r) { setTimeout(r, 1500); });
                cue([660, 990]);
                await new Promise(function (r) { setTimeout(r, 400); });
                var turn = await recordTurn({ fixedSeconds: 6 });
                cue([990, 660]);
                if (!turn.audio || rms(turn.audio) < 0.004) throw new Error('I could not hear you. Check the microphone and try again.');
                show('Working on sentence ' + (i + 1) + '…');
                prints.push((await ask('embed', turn.audio)).embedding);
            }
            store(PRINT_KEY, JSON.stringify(average(prints).map(function (v) { return Math.round(v * 1e5) / 1e5; })));
            live('Done. Your voice is saved on this device.', 'ok');
        } catch (err) {
            console.error('[voice]', err);
            problem('Voice setup failed: ' + ((err && err.message) || err));
        } finally {
            setState('off');
            enrollBtn.disabled = false;
            refreshEnrollUi();
        }
    }
    if (enrollBtn) enrollBtn.addEventListener('click', enrol);
    if (forgetBtn) forgetBtn.addEventListener('click', function () {
        store(PRINT_KEY, null);
        refreshEnrollUi();
        show('Your saved voice was removed. It will answer to any voice again.');
    });
    if (thresholdEl) thresholdEl.addEventListener('input', function () { store(THRESH_KEY, thresholdEl.value); });
    var sensEl = document.getElementById('voice-sens');
    if (sensEl) {
        sensEl.value = String(getSens());
        sensEl.addEventListener('input', function () { store(SENS_KEY, sensEl.value); });
    }
    if (micSelect) {
        micSelect.addEventListener('change', function () { store(MIC_KEY, micSelect.value); });
        if (navigator.mediaDevices.addEventListener) navigator.mediaDevices.addEventListener('devicechange', refreshMics);
        refreshMics();
    }
    var useTtsEl = document.getElementById('voice-use-tts');
    if (useTtsEl) {
        useTtsEl.checked = getUseTts();
        useTtsEl.addEventListener('change', function () { store(TTS_KEY, useTtsEl.checked ? '1' : '0'); });
    }

    // Lets you test the whole loop without a microphone: while voice is listening,
    // window.sirauggaVoice.say('hello') behaves as if you had said it.
    var injectedText = null;
    window.sirauggaVoice = {
        say: function (text) {
            if (state !== 'listening' || !currentSession) return false;
            injectedText = String(text || '');
            currentSession.cancel();
            return true;
        },
        state: function () { return state; },
        stats: function () { return JSON.parse(JSON.stringify(dbg)); },
    };

    window.addEventListener('pagehide', function () { if (state !== 'off') stopVoice(); });
    setState('off');
    refreshEnrollUi();
})();
