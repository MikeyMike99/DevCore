// Course Voice: on-device dictation (predict, reflect, agent message) and hands-free
// voice conversation (no wake-up word yet) for course_application.html.
// Shares voice preferences (siraugga.voice.*) with chat's voice.js.
(function () {
    'use strict';

    var supported = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia &&
        window.Worker && window.WebAssembly && window.speechSynthesis);

    var TTS_KEY = 'siraugga.voice.deviceVoice';       // '1' = TTS, '0' = ARIA, null = not chosen yet
    var TTS_VOICE_KEY = 'siraugga.voice.ttsVoice';
    var TTS_RATE_KEY = 'siraugga.voice.ttsRate';
    var TTS_PITCH_KEY = 'siraugga.voice.ttsPitch';
    var TTS_SAPI_KEY = 'siraugga.voice.includeSapi';
    var MIC_KEY = 'siraugga.voice.micId';
    var SENS_KEY = 'siraugga.voice.sens';
    var NOISE_KEY = 'siraugga.voice.roomNoise';
    var PRINT_KEY = 'siraugga.voice.print';
    var THRESH_KEY = 'siraugga.voice.threshold';
    var CPU_KEY = 'siraugga.voice.cpu';

    var DEFAULT_THRESHOLD = 0.85;
    var MAX_CLIP_SECONDS = 40;
    var END_SILENCE_MS = 1400;
    var END_SILENCE_EARLY_MS = 2200;
    var IDLE_TIMEOUT_MS = 3 * 60 * 1000;
    var MAX_SPOKEN_CHARS = 700;

    var memoryStore = {};
    function store(key, value) {
        if (value === undefined) {
            try { return localStorage.getItem(key); } catch (_) { return memoryStore[key] || null; }
        }
        memoryStore[key] = value;
        try {
            if (value === null) localStorage.removeItem(key);
            else localStorage.setItem(key, value);
        } catch (_) {}
    }

    function hasReplyModeChoice() {
        var v = store(TTS_KEY);
        return v === '0' || v === '1';
    }
    function getUseTts() { return store(TTS_KEY) === '1'; }
    function getIncludeSapi() { return store(TTS_SAPI_KEY) === '1'; }
    function getTtsRate() {
        var n = parseFloat(store(TTS_RATE_KEY));
        return (isFinite(n) && n >= 0.5 && n <= 2.5) ? n : 1.0;
    }
    function getTtsPitch() {
        var n = parseFloat(store(TTS_PITCH_KEY));
        return (isFinite(n) && n >= 0.5 && n <= 2.0) ? n : 1.0;
    }
    function getSens() {
        var n = parseInt(store(SENS_KEY), 10);
        return (n >= 1 && n <= 5) ? n : 3;
    }
    function getPrint() {
        try {
            var p = JSON.parse(store(PRINT_KEY) || 'null');
            return Array.isArray(p) && p.length ? p : null;
        } catch (_) { return null; }
    }
    function getThreshold() {
        var t = parseFloat(store(THRESH_KEY));
        return isFinite(t) && t > 0.5 && t < 0.99 ? t : DEFAULT_THRESHOLD;
    }
    function cpuMode() { return store(CPU_KEY) === '1'; }

    var roomNoise = null;
    function loadNoise() {
        var v = NaN;
        try { v = parseFloat(localStorage.getItem(NOISE_KEY)); } catch (_) {}
        return isFinite(v) && v > 0.0003 && v < 0.02 ? v : 0.0008;
    }
    function saveNoise() { try { localStorage.setItem(NOISE_KEY, String(roomNoise)); } catch (_) {} }
    function raiseNoise() { roomNoise = Math.min(0.01, Math.max(roomNoise || 0.0008, 0.001) * 1.8); saveNoise(); }

    // ---- DOM references ------------------------------------------------------
    var talkBtn = document.getElementById('course-talk-btn');
    var talkLabel = document.getElementById('course-talk-label');
    var liveBox = document.getElementById('course-voice-live');
    var meterWrap = document.getElementById('course-voice-meter');
    var meterBar = document.getElementById('course-voice-meter-bar');
    var replyBox = document.getElementById('course-voice-reply-box');
    var replyTextEl = document.getElementById('course-voice-reply-text');

    var modeDialog = document.getElementById('voice-mode-dialog');
    var modeAriaBtn = document.getElementById('voice-mode-aria-btn');
    var modeTtsBtn = document.getElementById('voice-mode-tts-btn');
    var modeCancelBtn = document.getElementById('voice-mode-cancel-btn');

    var replyModeEl = document.getElementById('course-voice-reply-mode');
    var ttsOptionsEl = document.getElementById('course-voice-tts-options');
    var ttsSelectEl = document.getElementById('course-voice-tts-select');
    var ttsSapiEl = document.getElementById('course-voice-tts-sapi');
    var ttsRateEl = document.getElementById('course-voice-tts-rate');
    var ttsRateValEl = document.getElementById('course-voice-tts-rate-val');
    var ttsPitchEl = document.getElementById('course-voice-tts-pitch');
    var ttsPitchValEl = document.getElementById('course-voice-tts-pitch-val');
    var ttsTestEl = document.getElementById('course-voice-tts-test');
    var ttsResetEl = document.getElementById('course-voice-tts-reset');
    var micSelectEl = document.getElementById('course-voice-mic-select');
    var sensEl = document.getElementById('course-voice-sens');

    var ariaEl = document.createElement('div');
    ariaEl.id = 'course-voice-aria';
    ariaEl.className = 'sr-only';
    ariaEl.setAttribute('aria-live', 'assertive');
    ariaEl.setAttribute('aria-atomic', 'true');
    document.body.appendChild(ariaEl);
    function announce(text) {
        ariaEl.textContent = '';
        setTimeout(function () { ariaEl.textContent = text; }, 80);
    }

    function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

    // ---- Status / Live UI ----------------------------------------------------
    var state = 'off'; // off | listening | thinking | speaking
    var noticeTimer = null;
    function paint(text, kind) {
        if (!liveBox) return;
        liveBox.textContent = text;
        liveBox.className = 'text-xs md:text-sm rounded-lg px-3 py-2 border mt-2 ' + (kind === 'error'
            ? 'text-red-200 bg-red-950/60 border-red-700/60'
            : kind === 'ok' ? 'text-emerald-200 bg-emerald-950/50 border-emerald-700/60'
            : 'text-teal-200 bg-slate-950 border-teal-700/60');
    }
    function live(text, kind) {
        if (noticeTimer) { clearTimeout(noticeTimer); noticeTimer = null; }
        paint(text, kind || 'info');
        announce(text);
        if (state === 'off') {
            noticeTimer = setTimeout(function () {
                if (state === 'off' && kind !== 'error' && liveBox) liveBox.classList.add('hidden');
            }, 12000);
        }
    }
    function liveQuiet(text, kind) {
        if (noticeTimer) { clearTimeout(noticeTimer); noticeTimer = null; }
        paint(text, kind || 'ok');
    }
    function problem(text) { live(text, 'error'); }

    function setState(s, labelText) {
        state = s;
        if (talkBtn) {
            talkBtn.setAttribute('aria-pressed', s !== 'off' ? 'true' : 'false');
            talkBtn.classList.toggle('bg-rose-700', s !== 'off');
            talkBtn.classList.toggle('hover:bg-rose-600', s !== 'off');
            talkBtn.classList.toggle('bg-teal-700', s === 'off');
            talkBtn.classList.toggle('hover:bg-teal-600', s === 'off');
        }
        if (talkLabel) {
            talkLabel.textContent = labelText || (s === 'off' ? 'Hands-Free Talk (Alt+V)' : 'Listening…');
        }
        if (meterWrap) meterWrap.classList.toggle('hidden', s !== 'listening');
        if (s !== 'listening' && meterBar) meterBar.style.width = '0%';
    }

    function showLevel(level) {
        if (!meterBar) return;
        var db = 20 * Math.log10(Math.max(level, 1e-5));
        meterBar.style.width = Math.max(0, Math.min(100, (db + 60) / 50 * 100)) + '%';
    }

    // ---- Audio cues ----------------------------------------------------------
    var cueCtx = null;
    function cue(freqs) {
        try {
            var Ctx = window.AudioContext || window.webkitAudioContext;
            if (!Ctx) return;
            if (!cueCtx || cueCtx.state === 'closed') cueCtx = new Ctx();
            if (cueCtx.state === 'suspended') cueCtx.resume();
            var t = cueCtx.currentTime;
            freqs.forEach(function (f, i) {
                var o = cueCtx.createOscillator(), g = cueCtx.createGain();
                o.type = 'sine'; o.frequency.value = f;
                g.gain.setValueAtTime(0.0001, t + i * 0.08);
                g.gain.exponentialRampToValueAtTime(0.07, t + i * 0.08 + 0.015);
                g.gain.exponentialRampToValueAtTime(0.0001, t + i * 0.08 + 0.09);
                o.connect(g); g.connect(cueCtx.destination);
                o.start(t + i * 0.08); o.stop(t + i * 0.08 + 0.1);
            });
        } catch (_) {}
    }
    function cueHeard() { cue([880]); }

    function releaseAudioSession() {
        try { if (cueCtx && cueCtx.state !== 'closed') cueCtx.close(); } catch (_) {}
        cueCtx = null;
        try {
            if (navigator.audioSession && 'type' in navigator.audioSession) navigator.audioSession.type = 'auto';
        } catch (_) {}
    }

    // ---- Speech Worker -------------------------------------------------------
    var worker = null;
    var nextId = 1;
    var pending = {};
    var engineReady = false;
    var engineWarming = false;
    var loadPromise = null;
    var enginePresentPromise = null;
    var lastStage = '';

    function enginePresent() {
        if (!enginePresentPromise) {
            enginePresentPromise = fetch('/static/speech/vendor/transformers.min.js?v=2', { method: 'HEAD' })
                .then(function (r) { return r.ok; })
                .catch(function () { return false; });
        }
        return enginePresentPromise;
    }

    function getWorker() {
        if (worker) return worker;
        worker = new Worker('/static/speech/speech-worker.js?v=16', { type: 'module' });
        worker.onmessage = function (e) {
            var m = e.data;
            if (!m) return;
            if (m.type === 'stage' && m.text) { lastStage = m.text; return; }
            if (m.type === 'progress') return;
            var p = pending[m.id];
            if (!p) return;
            delete pending[m.id];
            if (m.type === 'error') p.reject(new Error(m.message));
            else p.resolve(m);
        };
        worker.onerror = function (e) {
            Object.keys(pending).forEach(function (k) {
                pending[k].reject(new Error((e && e.message) || 'speech worker failed'));
                delete pending[k];
            });
            worker = null;
            engineReady = false;
            loadPromise = null;
        };
        return worker;
    }

    function askOnce(type, audio, extra) {
        return new Promise(function (resolve, reject) {
            var id = nextId++;
            pending[id] = { resolve: resolve, reject: reject };
            var msg = Object.assign({ type: type, id: id, cpu: cpuMode() }, extra || {});
            if (audio) { msg.audio = audio; getWorker().postMessage(msg, [audio.buffer]); }
            else { getWorker().postMessage(msg); }
        });
    }

    function ask(type, audio, extra) {
        var copy = audio ? new Float32Array(audio) : null;
        return askOnce(type, copy, extra).catch(function (err) {
            if (!cpuMode() && /WebGPU|createBuffer|adapter|shader|device|session/i.test(String(err && err.message))) {
                store(CPU_KEY, '1');
                if (worker) { worker.terminate(); worker = null; }
                engineReady = false; loadPromise = null;
                return askOnce(type, audio ? new Float32Array(audio) : null, extra);
            }
            throw err;
        });
    }

    function ensureEngineLoaded(extra) {
        if (engineReady) return Promise.resolve({ type: 'ready' });
        if (loadPromise) return loadPromise;
        loadPromise = ask('load', null, extra || {}).then(function (res) {
            engineReady = true;
            return res;
        }).catch(function (err) {
            loadPromise = null;
            throw err;
        });
        return loadPromise;
    }

    function warmVoiceEngine(immediate) {
        if (engineReady || engineWarming || !supported) return;
        engineWarming = true;
        var doWarm = function () {
            enginePresent().then(function (ok) {
                if (!ok) { engineWarming = false; return; }
                ensureEngineLoaded({ warmup_pass: true, warm_speaker: !!getPrint() })
                    .then(function () { engineReady = true; engineWarming = false; })
                    .catch(function () { engineWarming = false; });
            });
        };
        if (immediate) doWarm();
        else if (typeof window.requestIdleCallback === 'function') window.requestIdleCallback(doWarm, { timeout: 3000 });
        else setTimeout(doWarm, 1200);
    }

    // ---- TTS Voice Selection & Speaking (Non-SAPI by default) ----------------
    var tts = window.speechSynthesis;
    var cachedVoices = [];
    if (tts) {
        var refreshVoices = function () {
            cachedVoices = tts.getVoices();
            refreshTtsVoicesUi();
        };
        refreshVoices();
        if (tts.addEventListener) tts.addEventListener('voiceschanged', refreshVoices);
    }

    function isNaturalVoice(v) {
        if (!v) return false;
        if (!v.localService) return true;
        return /Natural|Neural|Online|Google|Wavenet|Studio/i.test(v.name || '');
    }

    function availableVoices() {
        var all = (tts && tts.getVoices().length) ? tts.getVoices() : cachedVoices;
        if (!all || !all.length) return [];
        var list = getIncludeSapi() ? all.slice() : all.filter(isNaturalVoice);
        if (!list.length) list = all.slice();
        list.sort(function (a, b) {
            var aNat = isNaturalVoice(a) ? 0 : 1;
            var bNat = isNaturalVoice(b) ? 0 : 1;
            if (aNat !== bNat) return aNat - bNat;
            var aEn = /^en/i.test(a.lang) ? 0 : 1;
            var bEn = /^en/i.test(b.lang) ? 0 : 1;
            if (aEn !== bEn) return aEn - bEn;
            return String(a.name || '').localeCompare(String(b.name || ''));
        });
        return list;
    }

    function pickVoice() {
        var list = availableVoices();
        if (!list.length) return null;
        var saved = store(TTS_VOICE_KEY);
        if (saved) {
            var exact = list.filter(function (v) { return (v.voiceURI || v.name) === saved; })[0];
            if (exact) return exact;
        }
        var enNat = list.filter(function (v) { return /^en/i.test(v.lang) && isNaturalVoice(v); })[0];
        if (enNat) return enNat;
        var enAny = list.filter(function (v) { return /^en/i.test(v.lang); })[0];
        return enAny || list[0];
    }

    function speak(text, opts) {
        opts = opts || {};
        return new Promise(function (resolve) {
            if (!tts || !text) return resolve();
            var done = false;
            var finish = function () {
                if (done) return;
                done = true;
                clearTimeout(guard);
                resolve();
            };
            var u = new SpeechSynthesisUtterance(text);
            var v = pickVoice();
            if (v) { u.voice = v; if (v.lang) u.lang = v.lang; }
            u.rate = getTtsRate();
            u.pitch = getTtsPitch();
            u.onend = finish;
            u.onerror = finish;
            var guard = setTimeout(finish, Math.max(12000, Math.round(text.length * 140 / Math.max(0.5, u.rate))));
            try {
                if (opts.preview) tts.cancel();
                tts.speak(u);
            } catch (_) { finish(); }
        });
    }

    function stopSpeaking() {
        try { if (tts) tts.cancel(); } catch (_) {}
    }

    function spokenVersion(raw, limit) {
        var t = String(raw || '')
            .replace(/```[\s\S]*?```/g, ' Code block on screen. ')
            .replace(/`([^`]+)`/g, '$1')
            .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
            .replace(/[#*_>~|]/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
        limit = limit || MAX_SPOKEN_CHARS;
        if (t.length <= limit) return t;
        var cut = t.slice(0, limit).replace(/\s+\S*$/, '');
        return cut + '. The full reply is on screen.';
    }

    // ---- Microphone & VAD recording ------------------------------------------
    var lastMicName = '';
    async function refreshMics() {
        if (!micSelectEl || !navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
        try {
            var devs = await navigator.mediaDevices.enumerateDevices();
            var ins = devs.filter(function (d) { return d.kind === 'audioinput' && d.deviceId !== 'default' && d.deviceId !== 'communications'; });
            var cur = store(MIC_KEY) || '';
            micSelectEl.innerHTML = '';
            var first = document.createElement('option'); first.value = ''; first.textContent = 'System default'; micSelectEl.appendChild(first);
            ins.forEach(function (d, i) {
                var o = document.createElement('option'); o.value = d.deviceId; o.textContent = d.label || ('Microphone ' + (i + 1)); micSelectEl.appendChild(o);
            });
            micSelectEl.value = ins.some(function (d) { return d.deviceId === cur; }) ? cur : '';
        } catch (_) {}
    }

    async function openMic() {
        var dev = store(MIC_KEY);
        var audio = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };
        if (dev) audio.deviceId = { ideal: dev };
        var stream = await navigator.mediaDevices.getUserMedia({ audio: audio });
        var track = stream.getAudioTracks()[0];
        if (track && track.label) lastMicName = track.label;
        refreshMics();
        return stream;
    }

    function resampleTo16k(chunks, fromRate) {
        var total = 0; chunks.forEach(function (c) { total += c.length; });
        var out = new Float32Array(Math.round(total * 16000 / fromRate));
        var ratio = fromRate / 16000;
        var chunkIdx = 0, chunkOff = 0;
        for (var i = 0; i < out.length; i++) {
            var src = Math.min(total - 1, Math.floor(i * ratio));
            while (chunkIdx < chunks.length - 1 && src >= chunkOff + chunks[chunkIdx].length) {
                chunkOff += chunks[chunkIdx].length;
                chunkIdx++;
            }
            out[i] = chunks[chunkIdx][src - chunkOff];
        }
        return out;
    }

    function rms(arr) {
        var s = 0;
        for (var i = 0; i < arr.length; i++) s += arr[i] * arr[i];
        return Math.sqrt(s / Math.max(1, arr.length));
    }

    var currentSession = null;
    async function recordTurn(preStreamPromise) {
        var stream = preStreamPromise ? await preStreamPromise : await openMic();
        var Ctx = window.AudioContext || window.webkitAudioContext;
        var ctx = new Ctx();
        if (ctx.state === 'suspended') await ctx.resume();
        var rate = ctx.sampleRate;
        var src = ctx.createMediaStreamSource(stream);
        var proc = ctx.createScriptProcessor(4096, 1, 1);
        var mute = ctx.createGain(); mute.gain.value = 0;
        src.connect(proc); proc.connect(mute); mute.connect(ctx.destination);

        if (roomNoise === null) roomNoise = loadNoise();
        var chunks = [], pre = [];
        var preMax = Math.ceil(rate * 0.4 / 4096);
        var speaking = false, speechStart = 0, lastVoice = 0, startAt = Date.now(), peak = 0;
        var sensMul = [2.6, 1.9, 1.35, 1.0, 0.72][getSens() - 1];
        var finished = false;

        return new Promise(function (resolve) {
            function stop(keep) {
                if (finished) return;
                finished = true;
                currentSession = null;
                try { proc.disconnect(); src.disconnect(); mute.disconnect(); } catch (_) {}
                stream.getTracks().forEach(function (t) { t.stop(); });
                try { ctx.close(); } catch (_) {}
                if (!keep || !chunks.length) return resolve({ audio: null, voicedMs: 0, peak: 0 });
                resolve({ audio: resampleTo16k(chunks, rate), voicedMs: lastVoice - speechStart, peak: peak });
            }
            currentSession = {
                cancel: function () { stop(false); },
                finishNow: function () { stop(speaking); },
                hasSpeech: function () { return speaking; }
            };
            proc.onaudioprocess = function (e) {
                if (finished) return;
                var buf = new Float32Array(e.inputBuffer.getChannelData(0));
                var level = rms(buf);
                showLevel(level);
                var now = Date.now();
                if (!speaking) {
                    roomNoise = roomNoise * 0.96 + Math.min(level, roomNoise * 3) * 0.04;
                    var thresh = Math.max(0.0025, roomNoise * 2.2) * sensMul;
                    pre.push(buf); if (pre.length > preMax) pre.shift();
                    if (level > thresh) {
                        speaking = true;
                        speechStart = now;
                        lastVoice = now;
                        peak = level;
                        chunks = pre.slice();
                        liveQuiet('Hearing you…', 'ok');
                    } else if (now - startAt > IDLE_TIMEOUT_MS) {
                        saveNoise();
                        stop(false);
                    }
                } else {
                    chunks.push(buf);
                    if (level > peak) peak = level;
                    var keepThresh = Math.max(0.002, roomNoise * 1.6) * sensMul;
                    if (level > keepThresh) lastVoice = now;
                    var silenceNeed = (now - speechStart < 2000) ? END_SILENCE_EARLY_MS : END_SILENCE_MS;
                    if (now - lastVoice > silenceNeed || now - speechStart > MAX_CLIP_SECONDS * 1000) {
                        saveNoise();
                        stop(true);
                    }
                }
            };
        });
    }

    // ---- Echo / Hallucination filters ----------------------------------------
    var lastReplyWords = null, lastReplyAt = 0;
    function wordsOf(t) { return (String(t || '').toLowerCase().match(/[a-z']+/g) || []); }
    function rememberReply(reply) { lastReplyWords = new Set(wordsOf(reply)); lastReplyAt = Date.now(); }
    function looksLikeEcho(text) {
        if (!lastReplyWords || Date.now() - lastReplyAt > 120000) return false;
        var w = wordsOf(text);
        if (w.length < 3) return false;
        var hit = w.filter(function (x) { return lastReplyWords.has(x); }).length;
        return hit / w.length >= 0.6;
    }
    function looksLikeLoop(text) {
        var w = (text || '').toLowerCase().match(/[a-z']+/g) || [];
        if (w.length < 8) return false;
        var counts = {}, top = 0;
        for (var i = 0; i <= w.length - 3; i++) {
            var g = w[i] + ' ' + w[i + 1] + ' ' + w[i + 2];
            counts[g] = (counts[g] || 0) + 1;
            if (counts[g] > top) top = counts[g];
        }
        return top >= 4 || (w.length >= 16 && new Set(w).size / w.length < 0.3);
    }
    function normalise(t) { return String(t || '').toLowerCase().replace(/[^a-z ]/g, ' ').replace(/\s+/g, ' ').trim(); }
    function cleanup(t) { return (t || '').replace(/\[[^\]]*\]|\([^)]*\)/g, ' ').replace(/\s+/g, ' ').trim(); }
    function cosine(a, b) {
        var d = 0, na = 0, nb = 0;
        for (var i = 0; i < a.length; i++) { d += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; }
        return d / (Math.sqrt(na) * Math.sqrt(nb) + 1e-9);
    }

    // ---- Speak (Dictation) buttons for Predict / Reflect / Agent fields ------
    var dictActive = null; // { btn, labelEl, recorder, chunks, stream, timer }
    async function blobTo16k(blob) {
        var arr = await blob.arrayBuffer();
        var Ctx = window.AudioContext || window.webkitAudioContext;
        var ctx = new Ctx();
        try {
            var decoded = await ctx.decodeAudioData(arr);
            var ch = decoded.getChannelData(0);
            if (decoded.sampleRate === 16000) return new Float32Array(ch);
            if (window.OfflineAudioContext) {
                var len = Math.ceil(decoded.duration * 16000);
                var off = new window.OfflineAudioContext(1, len, 16000);
                var buf = off.createBuffer(1, decoded.length, decoded.sampleRate);
                buf.copyToChannel(ch, 0);
                var s = off.createBufferSource(); s.buffer = buf; s.connect(off.destination); s.start();
                var rendered = await off.startRendering();
                return new Float32Array(rendered.getChannelData(0));
            }
            return resampleTo16k([ch], decoded.sampleRate);
        } finally {
            try { ctx.close(); } catch (_) {}
        }
    }

    function insertIntoField(ta, text) {
        if (!ta || !text) return;
        var cur = ta.value || '';
        var sep = (cur && !/\s$/.test(cur)) ? ' ' : '';
        ta.value = cur + sep + text;
        ta.dispatchEvent(new Event('input', { bubbles: true }));
    }

    async function stopDictation(d) {
        if (!d || d.stopping) return;
        d.stopping = true;
        clearTimeout(d.timer);
        if (d.labelEl) d.labelEl.textContent = 'Transcribing…';
        d.btn.disabled = true;
        try {
            await new Promise(function (res) {
                d.recorder.onstop = res;
                d.recorder.stop();
            });
            d.stream.getTracks().forEach(function (t) { t.stop(); });
            var blob = new Blob(d.chunks, { type: d.recorder.mimeType || 'audio/webm' });
            await ensureEngineLoaded({ warmup_pass: true });
            var audio = await blobTo16k(blob);
            var res = await ask('transcribe', audio);
            var text = cleanup(res.text);
            if (text) {
                insertIntoField(d.ta, text);
                announce('Dictated: ' + text);
            } else {
                announce('No speech detected.');
            }
        } catch (err) {
            announce('Dictation failed: ' + ((err && err.message) || err));
        } finally {
            d.btn.disabled = false;
            d.btn.setAttribute('aria-pressed', 'false');
            if (d.labelEl) d.labelEl.textContent = d.baseLabel;
            dictActive = null;
        }
    }

    function attachDictation(ta, opts) {
        opts = opts || {};
        if (!ta || !supported || ta.dataset.voiceDictationAttached) return;
        ta.dataset.voiceDictationAttached = '1';
        var baseLabel = opts.label || 'Speak';
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-teal-300 border border-teal-700/60 focus:outline-none focus:ring-2 focus:ring-teal-400';
        btn.setAttribute('aria-pressed', 'false');
        btn.setAttribute('aria-label', baseLabel + ' into ' + (opts.fieldName || 'text box'));
        var lbl = document.createElement('span');
        lbl.textContent = baseLabel;
        btn.appendChild(lbl);

        btn.addEventListener('pointerenter', function () { warmVoiceEngine(true); }, { once: true });
        btn.addEventListener('click', async function () {
            if (dictActive && dictActive.btn === btn) {
                return stopDictation(dictActive);
            }
            if (dictActive) {
                await stopDictation(dictActive);
            }
            if (state !== 'off') stopVoice();
            if (!(await enginePresent())) {
                announce('Speech engine is not available on this host.');
                return;
            }
            try {
                var stream = await openMic();
                var recorder = new MediaRecorder(stream);
                var chunks = [];
                recorder.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
                recorder.start();
                btn.setAttribute('aria-pressed', 'true');
                lbl.textContent = 'Stop speaking';
                announce('Recording. Speak now, then press Stop speaking.');
                var d = {
                    btn: btn, labelEl: lbl, ta: ta, baseLabel: baseLabel,
                    recorder: recorder, chunks: chunks, stream: stream, stopping: false,
                    timer: null
                };
                d.timer = setTimeout(function () { stopDictation(d); }, 120000);
                dictActive = d;
            } catch (err) {
                announce('Could not open microphone.');
            }
        });

        var row = document.createElement('div');
        row.className = 'flex items-center justify-end mt-1';
        row.appendChild(btn);
        ta.insertAdjacentElement('afterend', row);
    }

    // ---- Reply delivery (ARIA or TTS) & Hands-Free loop ----------------------
    var ariaTimer = null;
    async function deliverReplyAndContinue(replyText, opts) {
        opts = opts || {};
        if (state === 'off') return;
        var useVoice = getUseTts();
        var spoken = spokenVersion(replyText, useVoice ? MAX_SPOKEN_CHARS : 1500);
        rememberReply(spoken);
        if (replyBox && replyTextEl && opts.showInBox !== false) {
            replyTextEl.textContent = replyText;
            replyBox.classList.remove('hidden');
        }
        if (useVoice) {
            setState('speaking', 'Speaking (tap to talk)');
            liveQuiet('Reply received. Speaking…', 'ok');
            await speak(spoken);
            if (state === 'speaking') listen();
            return;
        }
        setState('speaking', 'Reading reply… (tap to talk)');
        liveQuiet('Reply: ' + spoken);
        announce(spoken || 'Reply ready on screen.');
        var words = (spoken.match(/\S+/g) || []).length;
        ariaTimer = setTimeout(function () {
            ariaTimer = null;
            if (state === 'speaking') listen();
        }, Math.max(2500, Math.round(words / 4.5 * 1000) + 1500));
    }

    var assistHistory = [];
    var lastAssistStep = null;

    async function askCourseAssistant(text) {
        var bridge = window.SirauggaCourseBridge;
        if (!bridge || !bridge.getContext) {
            return deliverReplyAndContinue('The course is still loading. Try again in a moment.');
        }
        var ctx = bridge.getContext();
        if (!ctx || !ctx.stepId) {
            return deliverReplyAndContinue('Open a course section first, then ask me anything about it.');
        }
        if (lastAssistStep !== ctx.stepId) {
            assistHistory = [];
            lastAssistStep = ctx.stepId;
        }

        // If the learner is on an agent_card step, route directly through the card's agent box
        var agentMsg = document.getElementById('agent-msg');
        var agentSend = document.getElementById('agent-send-btn');
        if (ctx.taskType === 'agent_card' && agentMsg && agentSend && !agentSend.disabled) {
            agentMsg.value = text;
            agentMsg.dispatchEvent(new Event('input', { bubbles: true }));
            var beforeTurns = document.querySelectorAll('#agent-log > div').length;
            agentSend.click();
            liveQuiet('Asked the card agent. Waiting for reply…', 'info');
            var waited = 0;
            while (waited < 65000 && state !== 'off') {
                await sleep(350);
                waited += 350;
                if (!agentSend.disabled) break;
            }
            if (state === 'off') return;
            var boxes = document.querySelectorAll('#agent-log > div');
            if (boxes.length > beforeTurns) {
                var lastBox = boxes[boxes.length - 1];
                var replyP = lastBox.querySelectorAll('p')[1];
                return deliverReplyAndContinue(replyP ? replyP.textContent : 'The agent updated the card.', { showInBox: false });
            }
            var st = document.getElementById('agent-status');
            return deliverReplyAndContinue((st && st.textContent) || 'The agent finished.');
        }

        if (ctx.previewMode) {
            return deliverReplyAndContinue('Preview mode is on, so the live course agent is switched off. You can still dictate predictions and reflections.');
        }

        liveQuiet('Asking the course assistant…', 'info');
        try {
            var res = await fetch('/api/course/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action: 'course_assist',
                    course_id: ctx.courseId,
                    step_id: ctx.stepId,
                    message: text,
                    history: assistHistory.slice(-6)
                })
            });
            var data = {};
            try { data = await res.json(); } catch (_) {}
            if (!res.ok || !data.ok) {
                return deliverReplyAndContinue(data.error || 'The course assistant could not answer right now.');
            }
            assistHistory.push({ role: 'learner', text: text });
            assistHistory.push({ role: 'agent', text: data.reply });
            return deliverReplyAndContinue(data.reply);
        } catch (err) {
            return deliverReplyAndContinue('Connection error reaching the course assistant.');
        }
    }

    async function handleVoiceText(text) {
        var cmd = normalise(text);
        if (/^(stop|stop it|stop listening|stop talking|stop voice|turn off|turn it off|voice off|cancel|goodbye|good bye|bye|that is all|thats all|that s all)$/.test(cmd)) {
            return stopVoice();
        }
        cueHeard();
        liveQuiet('You said: “' + text + '”', 'ok');

        // 1. Predict by voice: "predict ..." or "my prediction is ..."
        var predMatch = text.match(/^(?:my\s+prediction\s+is|prediction|predict(?:\s+that)?)\s*[:,-]?\s+(.+)$/i);
        if (predMatch) {
            var predEl = document.getElementById('predict-field');
            if (!predEl) {
                return deliverReplyAndContinue('There is no prediction box on this step.');
            }
            insertIntoField(predEl, predMatch[1].trim());
            var plen = predEl.value.trim().length;
            var msg = plen >= 20
                ? 'Prediction saved, ' + plen + ' characters. That is long enough to run.'
                : 'Prediction updated, ' + plen + ' of 20 characters needed. Say predict followed by more detail.';
            return deliverReplyAndContinue(msg, { showInBox: false });
        }

        // 2. Error reflection by voice: "error reflection ..." or "common error ..."
        var errMatch = text.match(/^(?:error\s+reflection|common\s+error(?:\s+is)?)\s*[:,-]?\s+(.+)$/i);
        if (errMatch) {
            var errEl = document.getElementById('reflect-error');
            if (!errEl) {
                return deliverReplyAndContinue('There is no error reflection box on this step.');
            }
            insertIntoField(errEl, errMatch[1].trim());
            var elen = errEl.value.trim().length;
            return deliverReplyAndContinue('Error reflection updated, ' + elen + ' characters.', { showInBox: false });
        }

        // 3. Reflection by voice: "reflect ..." or "my reflection is ..."
        var refMatch = text.match(/^(?:my\s+reflection\s+is|reflection|reflect(?:\s+that)?)\s*[:,-]?\s+(.+)$/i);
        if (refMatch) {
            var refEl = document.getElementById('reflect-explain');
            if (!refEl) {
                return deliverReplyAndContinue('Run the step first to open the reflection box, or ask me a question.');
            }
            insertIntoField(refEl, refMatch[1].trim());
            var rlen = refEl.value.trim().length;
            var rmsg = rlen >= 30
                ? 'Reflection saved, ' + rlen + ' characters. Say save reflection when ready.'
                : 'Reflection updated, ' + rlen + ' of 30 characters needed.';
            return deliverReplyAndContinue(rmsg, { showInBox: false });
        }

        // 4. Save reflection
        if (/^save\s+(?:my\s+)?reflection$/.test(cmd)) {
            var saveBtn = document.getElementById('save-reflection-btn');
            if (!saveBtn) return deliverReplyAndContinue('The reflection save button is not visible yet.');
            saveBtn.click();
            await sleep(250);
            var st = document.getElementById('reflection-status');
            return deliverReplyAndContinue((st && st.textContent) || 'Reflection saved.', { showInBox: false });
        }

        // 5. Run current step
        if (/^(run|run command|run step|execute|check and save)$/.test(cmd)) {
            var runBtn = document.getElementById('run-step-btn');
            if (!runBtn) return deliverReplyAndContinue('There is no Run button on this step.');
            runBtn.click();
            return deliverReplyAndContinue('Running the step now.', { showInBox: false });
        }

        // 6. Navigate sections
        var bridge = window.SirauggaCourseBridge;
        if (/^(next|next section|continue|next step)$/.test(cmd) && bridge && bridge.nextStep) {
            bridge.nextStep();
            await sleep(150);
            var cNext = bridge.getContext();
            return deliverReplyAndContinue('Moved to ' + ((cNext && cNext.title) || 'the next section') + '.', { showInBox: false });
        }
        if (/^(previous|previous section|go back|last step)$/.test(cmd) && bridge && bridge.prevStep) {
            bridge.prevStep();
            await sleep(150);
            var cPrev = bridge.getContext();
            return deliverReplyAndContinue('Moved back to ' + ((cPrev && cPrev.title) || 'the previous section') + '.', { showInBox: false });
        }

        // 7. Read current section
        if (/^(read section|read step|what is this step|read the task|where am i)$/.test(cmd) && bridge && bridge.getContext) {
            var cRead = bridge.getContext();
            var summary = [cRead.title, cRead.conceptSummary, cRead.taskPrompt].filter(Boolean).join('. ');
            return deliverReplyAndContinue(summary || 'Open a section to read it.', { showInBox: false });
        }

        // 8. Default: communicate with the course agent
        return askCourseAssistant(text);
    }

    async function noteThenListen(text, kind) {
        live(text, kind);
        await sleep(getUseTts() ? 600 : Math.max(1500, Math.round((String(text).match(/\S+/g) || []).length / 3.2 * 1000) + 1500));
        if (state !== 'off') listen();
    }

    async function listen(preStreamPromise, skipBeep) {
        if (state === 'off') {
            if (preStreamPromise) preStreamPromise.then(function (s) { s.getTracks().forEach(function (t) { t.stop(); }); }).catch(function () {});
            return;
        }
        setState('listening', 'Listening… (tap to stop)');
        liveQuiet('Hands-Free listening… speak now, then pause.' + (lastMicName ? ' Mic: ' + lastMicName : ''), 'info');
        if (!skipBeep) {
            cue([660, 990]);
            await sleep(250);
        }
        if (state === 'off') {
            if (preStreamPromise) preStreamPromise.then(function (s) { s.getTracks().forEach(function (t) { t.stop(); }); }).catch(function () {});
            return;
        }
        var turn;
        try {
            turn = await recordTurn(preStreamPromise);
        } catch (err) {
            var msg = err && err.name === 'NotAllowedError'
                ? 'Microphone access was blocked. Allow it in your browser to use Hands-Free Talk.'
                : 'No microphone could be opened (' + ((err && (err.name || err.message)) || 'error') + ').';
            stopVoice();
            return problem(msg);
        }
        if (state === 'off') return;
        if (!turn.audio) { stopVoice(); return live('Stopped listening after a quiet while.'); }
        if (turn.voicedMs < 350) return listen();
        if (turn.peak < 0.006) {
            return noteThenListen('I could hardly hear you. Move closer to the microphone.', 'error');
        }
        setState('thinking', 'Working…');
        try {
            var print = getPrint();
            if (print) {
                var emb = (await ask('embed', turn.audio)).embedding;
                if (state === 'off') return;
                var score = cosine(print, emb);
                if (score < getThreshold()) {
                    return noteThenListen('That did not sound like you, so it was ignored.', 'error');
                }
            }
            var text = cleanup((await ask('transcribe', turn.audio)).text);
            if (state === 'off') return;
            if (!text) { raiseNoise(); return noteThenListen('I did not catch any words.'); }
            if (looksLikeLoop(text)) { raiseNoise(); return noteThenListen('That sounded like background noise, so it was ignored.'); }
            if (looksLikeEcho(text)) return noteThenListen('That sounded like the reply being read out, so it was ignored.');
            await handleVoiceText(text);
        } catch (err) {
            stopVoice();
            problem('Hands-Free Talk hit a problem: ' + ((err && err.message) || err));
        }
    }

    async function startVoice() {
        if (state !== 'off') return;
        if (dictActive) await stopDictation(dictActive);
        var micEarlyPromise = null;
        try { micEarlyPromise = openMic(); } catch (_) {}
        setState('thinking', 'Starting…');
        if (!(await enginePresent())) {
            setState('off');
            if (micEarlyPromise) micEarlyPromise.then(function (s) { s.getTracks().forEach(function (t) { t.stop(); }); }).catch(function () {});
            return problem('The speech files are not available at ' + location.host + '.');
        }
        if (!engineReady) {
            live('Loading the on-device speech model. The first time takes a moment…');
            try {
                await ensureEngineLoaded({ warmup_pass: true, warm_speaker: !!getPrint() });
            } catch (err) {
                if (micEarlyPromise) micEarlyPromise.then(function (s) { s.getTracks().forEach(function (t) { t.stop(); }); }).catch(function () {});
                stopVoice();
                return problem('The speech model could not be loaded: ' + ((err && err.message) || err));
            }
        }
        if (state === 'off') {
            if (micEarlyPromise) micEarlyPromise.then(function (s) { s.getTracks().forEach(function (t) { t.stop(); }); }).catch(function () {});
            return;
        }
        cue([660, 990, 1320]);
        liveQuiet('Hands-Free Talk ready. Ask a question, or say "predict ..." or "reflect ...".', 'ok');
        setState('listening', 'Listening…');
        listen(micEarlyPromise, true);
    }

    function stopVoice() {
        if (ariaTimer) { clearTimeout(ariaTimer); ariaTimer = null; }
        stopSpeaking();
        if (currentSession) currentSession.cancel();
        releaseAudioSession();
        ariaEl.textContent = '';
        setState('off');
        live('Hands-Free Talk off.');
    }

    function skipReading() {
        if (ariaTimer) { clearTimeout(ariaTimer); ariaTimer = null; }
        setState('listening', 'Listening…');
        stopSpeaking();
        listen();
    }

    // ---- First-time reply mode choice dialog --------------------------------
    var modeDialogReturnFocus = null;
    function closeReplyModeDialog(restoreFocus) {
        if (!modeDialog) return;
        modeDialog.classList.add('hidden');
        if (restoreFocus && modeDialogReturnFocus && typeof modeDialogReturnFocus.focus === 'function') {
            modeDialogReturnFocus.focus();
        }
        modeDialogReturnFocus = null;
    }
    function openReplyModeDialog() {
        if (!modeDialog) { store(TTS_KEY, '0'); startVoice(); return; }
        warmVoiceEngine(true);
        modeDialogReturnFocus = document.activeElement || talkBtn;
        modeDialog.classList.remove('hidden');
        setTimeout(function () { if (modeAriaBtn) modeAriaBtn.focus(); }, 10);
    }
    function chooseReplyMode(mode) {
        store(TTS_KEY, mode === 'tts' ? '1' : '0');
        syncReplyModeUi();
        closeReplyModeDialog(true);
        startVoice();
    }
    if (modeAriaBtn) modeAriaBtn.addEventListener('click', function () { chooseReplyMode('aria'); });
    if (modeTtsBtn) modeTtsBtn.addEventListener('click', function () { chooseReplyMode('tts'); });
    if (modeCancelBtn) modeCancelBtn.addEventListener('click', function () { closeReplyModeDialog(true); });
    if (modeDialog) {
        modeDialog.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                e.preventDefault(); e.stopPropagation(); closeReplyModeDialog(true); return;
            }
            if (e.key === 'Tab') {
                var focusables = [modeAriaBtn, modeTtsBtn, modeCancelBtn].filter(Boolean);
                if (!focusables.length) return;
                var first = focusables[0], last = focusables[focusables.length - 1];
                if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
                else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
            }
        });
    }

    // ---- Course Voice Settings UI --------------------------------------------
    function refreshTtsVoicesUi() {
        if (!ttsSelectEl) return;
        var list = availableVoices();
        var cur = store(TTS_VOICE_KEY) || '';
        ttsSelectEl.innerHTML = '';
        var autoOpt = document.createElement('option');
        autoOpt.value = '';
        autoOpt.textContent = list.length ? 'Automatic (best natural voice)' : 'No voices available';
        ttsSelectEl.appendChild(autoOpt);
        list.forEach(function (v) {
            var opt = document.createElement('option');
            opt.value = v.voiceURI || v.name;
            opt.textContent = v.name + ' (' + v.lang + ' — ' + (isNaturalVoice(v) ? 'Natural' : 'Local SAPI') + ')';
            ttsSelectEl.appendChild(opt);
        });
        ttsSelectEl.value = list.some(function (v) { return (v.voiceURI || v.name) === cur; }) ? cur : '';
    }

    function syncReplyModeUi() {
        var chosen = hasReplyModeChoice();
        var useTts = getUseTts();
        if (replyModeEl) replyModeEl.value = chosen ? (useTts ? 'tts' : 'aria') : '';
        if (ttsOptionsEl) ttsOptionsEl.classList.toggle('hidden', !useTts);
        if (ttsSapiEl) ttsSapiEl.checked = getIncludeSapi();
        if (ttsRateEl) ttsRateEl.value = String(getTtsRate());
        if (ttsRateValEl) ttsRateValEl.textContent = getTtsRate().toFixed(2) + 'x';
        if (ttsPitchEl) ttsPitchEl.value = String(getTtsPitch());
        if (ttsPitchValEl) ttsPitchValEl.textContent = getTtsPitch().toFixed(2);
        refreshTtsVoicesUi();
    }

    if (replyModeEl) {
        replyModeEl.addEventListener('change', function () {
            if (replyModeEl.value === 'tts' || replyModeEl.value === 'aria') {
                store(TTS_KEY, replyModeEl.value === 'tts' ? '1' : '0');
                syncReplyModeUi();
            }
        });
    }
    if (ttsSelectEl) ttsSelectEl.addEventListener('change', function () { store(TTS_VOICE_KEY, ttsSelectEl.value || null); });
    if (ttsSapiEl) ttsSapiEl.addEventListener('change', function () { store(TTS_SAPI_KEY, ttsSapiEl.checked ? '1' : '0'); refreshTtsVoicesUi(); });
    if (ttsRateEl) {
        ttsRateEl.addEventListener('input', function () {
            store(TTS_RATE_KEY, ttsRateEl.value);
            if (ttsRateValEl) ttsRateValEl.textContent = parseFloat(ttsRateEl.value).toFixed(2) + 'x';
        });
    }
    if (ttsPitchEl) {
        ttsPitchEl.addEventListener('input', function () {
            store(TTS_PITCH_KEY, ttsPitchEl.value);
            if (ttsPitchValEl) ttsPitchValEl.textContent = parseFloat(ttsPitchEl.value).toFixed(2);
        });
    }
    if (ttsTestEl) ttsTestEl.addEventListener('click', function () { speak('This is how I will sound when replying during your course.', { preview: true }); });
    if (ttsResetEl) ttsResetEl.addEventListener('click', function () { store(TTS_RATE_KEY, '1.0'); store(TTS_PITCH_KEY, '1.0'); syncReplyModeUi(); });
    if (sensEl) {
        sensEl.value = String(getSens());
        sensEl.addEventListener('input', function () { store(SENS_KEY, sensEl.value); });
    }
    if (micSelectEl) {
        micSelectEl.addEventListener('change', function () { store(MIC_KEY, micSelectEl.value); });
        if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) navigator.mediaDevices.addEventListener('devicechange', refreshMics);
        refreshMics();
    }
    syncReplyModeUi();

    if (talkBtn) {
        if (!supported) {
            talkBtn.disabled = true;
            talkBtn.title = 'Hands-Free Talk is not supported in this browser';
        } else {
            talkBtn.addEventListener('pointerenter', function () { warmVoiceEngine(true); }, { once: true });
            talkBtn.addEventListener('focus', function () { warmVoiceEngine(true); }, { once: true });
            talkBtn.addEventListener('click', function () {
                if (state === 'off') {
                    if (!hasReplyModeChoice()) openReplyModeDialog();
                    else startVoice();
                } else if (state === 'listening' && currentSession && currentSession.hasSpeech()) {
                    currentSession.finishNow();
                } else if (state === 'speaking') {
                    skipReading();
                } else {
                    stopVoice();
                }
            });
        }
    }

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && state !== 'off') {
            e.preventDefault();
            stopVoice();
        } else if (e.altKey && (e.key === 'v' || e.key === 'V') && talkBtn && !talkBtn.disabled) {
            e.preventDefault();
            talkBtn.click();
        }
    });
    window.addEventListener('pagehide', function () { if (state !== 'off') stopVoice(); });

    window.SirauggaCourseVoice = {
        attachDictation: attachDictation,
        state: function () { return state; },
        stop: stopVoice
    };
})();
