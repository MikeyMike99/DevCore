// Chat mic button: click to start talking, click again to stop. The recording is
// turned into text on this device by speech-worker.js and typed into the chat box.
// Audio is never uploaded; only the text the user sends leaves the device.
//
// Auto-send: asked once before the first dictation (#dictation-choice-modal) and
// changeable in Settings (#dictation-autosend). It only ever fires when the user
// pressed Stop. A recording that hit the time limit, an empty or failed
// transcription, or a task that is still running (Send would "Steer" it) is
// never sent automatically; the text is left in the box instead.
(function () {
    'use strict';

    var MAX_SECONDS = 120;
    var PREF_KEY = 'siraugga.dictation.autoSend';    // '1' | '0' | absent = not asked yet
    var btn = document.getElementById('mic-btn');
    var label = document.getElementById('mic-btn-label');
    var status = document.getElementById('mic-status');
    var notice = document.getElementById('mic-notice');
    var prompt = document.getElementById('prompt');
    var form = document.getElementById('chat-form');
    var sendBtn = document.getElementById('send-btn');
    var sendSpinner = document.getElementById('send-btn-spinner');
    var choiceModal = document.getElementById('dictation-choice-modal');
    var settingsToggle = document.getElementById('dictation-autosend');
    if (!btn || !prompt) return;

    var supported = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia &&
        window.MediaRecorder && window.Worker && window.WebAssembly);
    if (!supported) {
        btn.disabled = true;
        btn.title = 'Voice dictation is not supported in this browser';
        return;
    }

    var worker = null;
    var state = 'idle';          // idle | recording | working
    var recorder = null;
    var chunks = [];
    var stream = null;
    var stopTimer = null;
    var stoppedBy = null;        // 'user' | 'timeout'
    var nextId = 1;
    var progress = {};
    var noticeTimer = null;
    var memoryPref = null;       // used when browser storage is unavailable
    var caretTouched = false;    // until the user places the cursor, dictation appends at the end
    prompt.addEventListener('focus', function () { caretTouched = true; });

    // ---- auto-send preference ------------------------------------------------
    function getPref() {          // true | false | null (never asked)
        var v = memoryPref;
        try { v = localStorage.getItem(PREF_KEY); } catch (_) {}
        return v === '1' ? true : v === '0' ? false : null;
    }
    function setPref(on) {
        memoryPref = on ? '1' : '0';
        try { localStorage.setItem(PREF_KEY, memoryPref); } catch (_) {}
        if (settingsToggle) settingsToggle.checked = on;
    }
    if (settingsToggle) {
        settingsToggle.checked = getPref() === true;
        settingsToggle.addEventListener('change', function () { setPref(settingsToggle.checked); });
    }

    // Resolves true/false once the user picks, or null if they dismiss the dialog.
    function askPref() {
        return new Promise(function (resolve) {
            if (!choiceModal || typeof choiceModal.showModal !== 'function') { resolve(false); return; }
            var auto = document.getElementById('dictation-choice-auto');
            var review = document.getElementById('dictation-choice-review');
            function done(value) {
                auto.removeEventListener('click', onAuto);
                review.removeEventListener('click', onReview);
                choiceModal.removeEventListener('cancel', onCancel);
                if (choiceModal.open) choiceModal.close();
                btn.focus();
                resolve(value);
            }
            function onAuto() { done(true); }
            function onReview() { done(false); }
            function onCancel(e) { e.preventDefault(); done(null); }
            auto.addEventListener('click', onAuto);
            review.addEventListener('click', onReview);
            choiceModal.addEventListener('cancel', onCancel);
            choiceModal.showModal();
            review.focus();       // the safer choice gets focus
        });
    }

    // ---- UI helpers ----------------------------------------------------------
    function say(text, isError) {
        if (status) status.textContent = text;
        if (isError) {
            showVisible(text);
            if (label) {
                label.textContent = 'Mic error';
                setTimeout(function () { if (state === 'idle') label.textContent = 'Speak'; }, 4000);
            }
        }
    }

    // A short visible note above the message box (also announced to screen readers).
    function showNotice(text) {
        if (status) status.textContent = text;
        showVisible(text);
    }
    function showVisible(text) {
        if (!notice) return;
        notice.textContent = text;
        notice.classList.remove('hidden');
        if (noticeTimer) clearTimeout(noticeTimer);
        noticeTimer = setTimeout(function () { notice.classList.add('hidden'); }, 8000);
    }

    function setState(s, text) {
        state = s;
        btn.setAttribute('aria-pressed', s === 'recording' ? 'true' : 'false');
        btn.classList.toggle('mic-recording', s === 'recording');
        btn.disabled = s === 'working';
        // Accessible name stays "Speak" (set in index.html); only aria-pressed changes.
        if (label) label.textContent = text || (s === 'recording' ? 'Stop' : 'Speak');
    }

    // ---- transcription -------------------------------------------------------
    function getWorker() {
        if (worker) return worker;
        worker = new Worker('/static/speech/speech-worker.js?v=5', { type: 'module' });
        worker.onmessage = function (e) {
            var m = e.data || {};
            if (m.type === 'progress') {
                progress[m.file] = [m.loaded, m.total];
                var loaded = 0, total = 0;
                Object.keys(progress).forEach(function (k) { loaded += progress[k][0]; total += progress[k][1]; });
                if (state === 'working' && total) {
                    var pct = Math.round(loaded / total * 100);
                    if (label) label.textContent = 'Loading ' + pct + '%';
                }
            } else if (m.type === 'ready') {
                if (state === 'working' && label) label.textContent = 'Transcribing';
            } else if (m.type === 'result') {
                setState('idle');
                var inserted = insertText(cleanup(m.text));
                if (inserted) afterInsert();
            } else if (m.type === 'error') {
                console.error('[dictation]', m.message);
                setState('idle');
                say('Voice dictation failed: ' + m.message, true);
            }
        };
        worker.onerror = function (e) {
            console.error('[dictation] worker error', e);
            worker = null;
            setState('idle');
            say('Voice dictation could not start.', true);
        };
        return worker;
    }

    // Whisper marks silence/noise like "[BLANK_AUDIO]" or "(music)"; drop those.
    function cleanup(text) {
        return (text || '').replace(/\[[^\]]*\]|\([^)]*\)/g, ' ').replace(/\s+/g, ' ').trim();
    }

    // True when this recording will be sent without the user touching Send (same rules as afterInsert).
    function willAutoSend() {
        return getPref() === true && stoppedBy === 'user' && !taskRunning() &&
            !!form && !!sendBtn && !sendBtn.disabled;
    }

    function insertText(text) {
        if (!text) { say('No speech was detected.', true); return false; }
        var start = caretTouched && prompt.selectionStart != null ? prompt.selectionStart : prompt.value.length;
        var end = caretTouched && prompt.selectionEnd != null ? prompt.selectionEnd : prompt.value.length;
        var before = prompt.value.slice(0, start);
        var after = prompt.value.slice(end);
        if (before && !/\s$/.test(before)) text = ' ' + text;
        if (after && !/^\s/.test(after)) text = text + ' ';
        prompt.value = before + text + after;
        var caret = before.length + text.length;
        if (!willAutoSend()) {                    // auto-send: leave focus (and the keyboard) alone
            prompt.focus();
            prompt.setSelectionRange(caret, caret);
        }
        prompt.dispatchEvent(new Event('input', { bubbles: true }));
        say('Inserted: ' + text.trim());
        return true;
    }

    function taskRunning() {
        // While a task runs, Send becomes "Steer" and shows its spinner.
        return !!(sendSpinner && !sendSpinner.classList.contains('hidden'));
    }

    function afterInsert() {
        if (stoppedBy === 'timeout') {
            showNotice('Recording stopped at the ' + (MAX_SECONDS / 60) + '-minute limit, so it was not sent. Check the text and press Send.');
            return;
        }
        if (!getPref() || stoppedBy !== 'user') return;
        if (taskRunning()) {
            showNotice('Not sent automatically because a task is still running. Press Send (Steer) when you are ready.');
            return;
        }
        if (!form || !sendBtn || sendBtn.disabled) {
            showNotice('Not sent automatically because sending is unavailable right now. Press Send when it is.');
            return;
        }
        if (typeof form.requestSubmit === 'function') form.requestSubmit(sendBtn);
        else sendBtn.click();
    }

    // ---- recording -----------------------------------------------------------
    function releaseMic() {
        if (stopTimer) { clearTimeout(stopTimer); stopTimer = null; }
        if (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; }
    }

    // Sound cues instead of speech. A screen reader says "Stop, button..." when the button is
    // pressed, so recording starts after a short wait, then a rising two-note beep means "the mic
    // is live, talk now". A falling two-note beep means "recording stopped". Made with the browser's
    // own audio, so there is no file to load; the beep ends before recording starts, so it is
    // never part of the dictation.
    var START_DELAY_MS = 700;
    var BEEP_MS = 220;
    var startTimer = null;
    var cueCtx = null;
    function cue(freqs) {
        try {
            var Ctx = window.AudioContext || window.webkitAudioContext;
            if (!cueCtx || cueCtx.state === 'closed') cueCtx = new Ctx();
            if (cueCtx.state === 'suspended') cueCtx.resume();
            var t = cueCtx.currentTime;
            freqs.forEach(function (f, i) {
                var o = cueCtx.createOscillator(), g = cueCtx.createGain();
                o.type = 'sine';
                o.frequency.value = f;
                o.connect(g); g.connect(cueCtx.destination);
                var a = t + i * 0.1;
                g.gain.setValueAtTime(0.0001, a);
                g.gain.exponentialRampToValueAtTime(0.18, a + 0.015);
                g.gain.exponentialRampToValueAtTime(0.0001, a + 0.09);
                o.start(a); o.stop(a + 0.1);
            });
        } catch (_) {}
    }
    var cueStart = function () { cue([660, 990]); };    // rising
    var cueStop = function () { cue([990, 660]); };     // falling

    async function startRecording() {
        try {
            getWorker().postMessage({ type: 'load' });   // warm the model while the user talks
        } catch (err) {
            console.error('[dictation] worker', err);
            say('Voice dictation could not start in this browser (' + ((err && err.message) || err) + ').', true);
            return;
        }
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
            });
        } catch (err) {
            say(err && err.name === 'NotAllowedError'
                ? 'Microphone access was blocked. Allow it in your browser to use dictation.'
                : 'No microphone could be opened (' + ((err && err.name) || 'error') + ').', true);
            return;
        }
        chunks = [];
        stoppedBy = null;
        try {
            recorder = new MediaRecorder(stream);
        } catch (err) {
            releaseMic();
            say('This browser could not start recording (' + ((err && err.message) || err) + ').', true);
            return;
        }
        recorder.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
        recorder.onstop = onRecordingStopped;
        setState('recording');
        startTimer = setTimeout(function () {
            cueStart();
            startTimer = setTimeout(function () {
                startTimer = null;
                recorder.start();
                stopTimer = setTimeout(function () { stopRecording('timeout'); }, MAX_SECONDS * 1000);
            }, BEEP_MS);
        }, START_DELAY_MS);
    }

    function stopRecording(reason) {
        if (startTimer) {                         // pressed again before recording began: just cancel
            clearTimeout(startTimer); startTimer = null;
            releaseMic(); recorder = null; chunks = [];
            setState('idle');
            return;
        }
        if (!stoppedBy) stoppedBy = reason;
        if (recorder && recorder.state !== 'inactive') recorder.stop();
        releaseMic();
    }

    async function onRecordingStopped() {
        cueStop();
        setState('working', 'Transcribing');
        try {
            var blob = new Blob(chunks, { type: (recorder && recorder.mimeType) || 'audio/webm' });
            chunks = [];
            var audio = await toMono16k(await blob.arrayBuffer());
            // Whisper invents words (often "you") for silence, so skip near-silent recordings.
            var sum = 0;
            for (var i = 0; i < audio.length; i++) sum += audio[i] * audio[i];
            if (!audio.length || Math.sqrt(sum / audio.length) < 0.004) { setState('idle'); say('No speech was detected.', true); return; }
            getWorker().postMessage({ type: 'transcribe', id: nextId++, audio: audio }, [audio.buffer]);
        } catch (err) {
            console.error('[dictation]', err);
            setState('idle');
            say('The recording could not be processed: ' + ((err && err.message) || err), true);
        }
    }

    // Whisper expects 16 kHz mono float samples. Some phone browsers refuse an
    // AudioContext at 16 kHz, so fall back to the default rate and resample.
    async function toMono16k(arrayBuffer) {
        var Ctx = window.AudioContext || window.webkitAudioContext;
        var ctx;
        try { ctx = new Ctx({ sampleRate: 16000 }); } catch (_) { ctx = new Ctx(); }
        try {
            // Safari's older decodeAudioData only takes callbacks.
            var decoded = await new Promise(function (resolve, reject) {
                var p = ctx.decodeAudioData(arrayBuffer, resolve, reject);
                if (p && p.then) p.then(resolve, reject);
            });
            if (decoded.sampleRate !== 16000 && window.OfflineAudioContext) {
                var len = Math.max(1, Math.ceil(decoded.duration * 16000));
                var off = new OfflineAudioContext(1, len, 16000);   // mixes down to mono too
                var src = off.createBufferSource();
                src.buffer = decoded;
                src.connect(off.destination);
                src.start();
                var rendered = await new Promise(function (resolve, reject) {
                    var p = off.startRendering();
                    off.oncomplete = function (ev) { resolve(ev.renderedBuffer); };
                    if (p && p.then) p.then(resolve, reject);
                });
                return new Float32Array(rendered.getChannelData(0));
            }
            if (decoded.numberOfChannels === 1) return new Float32Array(decoded.getChannelData(0));
            var out = new Float32Array(decoded.length);
            for (var c = 0; c < decoded.numberOfChannels; c++) {
                var ch = decoded.getChannelData(c);
                for (var i = 0; i < ch.length; i++) out[i] += ch[i] / decoded.numberOfChannels;
            }
            return out;
        } finally {
            if (ctx.close) ctx.close();
        }
    }

    btn.addEventListener('click', async function () {
        if (state === 'recording') { stopRecording('user'); return; }
        if (state !== 'idle') return;
        if (getPref() === null) {
            var choice = await askPref();
            if (choice === null) return;              // dismissed: ask again next time
            setPref(choice);
        }
        startRecording();
    });

    setState('idle');
})();
