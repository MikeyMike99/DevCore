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
            if (label) {
                label.textContent = 'Mic error';
                setTimeout(function () { if (state === 'idle') label.textContent = 'Speak'; }, 4000);
            }
        }
    }

    // A short visible note above the message box (also announced to screen readers).
    function showNotice(text) {
        say(text);
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
        worker = new Worker('/static/speech/speech-worker.js?v=4', { type: 'module' });
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
        prompt.focus();
        prompt.setSelectionRange(caret, caret);
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

    async function startRecording() {
        getWorker().postMessage({ type: 'load' });   // warm the model while the user talks
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
            });
        } catch (err) {
            say(err && err.name === 'NotAllowedError'
                ? 'Microphone access was blocked. Allow it in your browser to use dictation.'
                : 'No microphone could be opened.', true);
            return;
        }
        chunks = [];
        stoppedBy = null;
        recorder = new MediaRecorder(stream);
        recorder.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
        recorder.onstop = onRecordingStopped;
        recorder.start();
        stopTimer = setTimeout(function () { stopRecording('timeout'); }, MAX_SECONDS * 1000);
        setState('recording');
        say('Listening. Press the button again to stop.');
    }

    function stopRecording(reason) {
        if (!stoppedBy) stoppedBy = reason;
        if (recorder && recorder.state !== 'inactive') recorder.stop();
        releaseMic();
    }

    async function onRecordingStopped() {
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
            say('The recording could not be processed.', true);
        }
    }

    // Whisper expects 16 kHz mono float samples.
    async function toMono16k(arrayBuffer) {
        var Ctx = window.AudioContext || window.webkitAudioContext;
        var ctx = new Ctx({ sampleRate: 16000 });
        try {
            var decoded = await ctx.decodeAudioData(arrayBuffer);
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
