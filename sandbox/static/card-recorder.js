(function () {
    'use strict';

    const STATE = {
        isolatedCard: null,
        hiddenNodes: new Map(),
        recorders: new WeakMap(),
        activeCards: new Set(),
        logs: [],
        seq: 0,
        latestCourseSnapshot: null,
        secureConnection: null,
        autoHookInstalled: false,
        exitHooksInstalled: false,
        dbPromise: null,
    };

    const IDB_NAME = 'siraugga_card_recordings';
    const IDB_VERSION = 1;

    function openRecorderDb() {
        if (STATE.dbPromise) return STATE.dbPromise;
        if (typeof indexedDB === 'undefined') {
            STATE.dbPromise = Promise.resolve(null);
            return STATE.dbPromise;
        }
        STATE.dbPromise = new Promise(function (resolve) {
            try {
                const req = indexedDB.open(IDB_NAME, IDB_VERSION);
                req.onupgradeneeded = function () {
                    const db = req.result;
                    if (!db.objectStoreNames.contains('sessions')) {
                        const sStore = db.createObjectStore('sessions', { keyPath: 'sessionId' });
                        sStore.createIndex('by_updated', 'updatedAt', { unique: false });
                    }
                    if (!db.objectStoreNames.contains('chunks')) {
                        const cStore = db.createObjectStore('chunks', { keyPath: 'id', autoIncrement: true });
                        cStore.createIndex('by_session', 'sessionId', { unique: false });
                    }
                };
                req.onsuccess = function () { resolve(req.result); };
                req.onerror = function () { resolve(null); };
            } catch (e) {
                resolve(null);
            }
        });
        return STATE.dbPromise;
    }

    function idbPutSession(sessionObj) {
        return openRecorderDb().then(function (db) {
            if (!db) return false;
            return new Promise(function (resolve) {
                try {
                    const tx = db.transaction('sessions', 'readwrite');
                    tx.objectStore('sessions').put(sessionObj);
                    tx.oncomplete = function () { resolve(true); };
                    tx.onerror = function () { resolve(false); };
                } catch (e) { resolve(false); }
            });
        });
    }

    function idbAddChunk(sessionId, seq, blob) {
        return openRecorderDb().then(function (db) {
            if (!db) return false;
            return new Promise(function (resolve) {
                try {
                    const tx = db.transaction('chunks', 'readwrite');
                    tx.objectStore('chunks').add({ sessionId: sessionId, seq: seq, blob: blob, ts: Date.now() });
                    tx.oncomplete = function () { resolve(true); };
                    tx.onerror = function () { resolve(false); };
                } catch (e) { resolve(false); }
            });
        });
    }

    function idbDeleteSession(sessionId) {
        if (!sessionId) return Promise.resolve(false);
        return openRecorderDb().then(function (db) {
            if (!db) return false;
            return new Promise(function (resolve) {
                try {
                    const tx = db.transaction(['sessions', 'chunks'], 'readwrite');
                    tx.objectStore('sessions').delete(sessionId);
                    const idx = tx.objectStore('chunks').index('by_session');
                    const cur = idx.openCursor(IDBKeyRange.only(sessionId));
                    cur.onsuccess = function () {
                        const c = cur.result;
                        if (c) { c.delete(); c.continue(); }
                    };
                    tx.oncomplete = function () { resolve(true); };
                    tx.onerror = function () { resolve(false); };
                } catch (e) { resolve(false); }
            });
        });
    }

    function idbFindLatestRecoverable(courseId, cardId) {
        return openRecorderDb().then(function (db) {
            if (!db) return null;
            return new Promise(function (resolve) {
                try {
                    const tx = db.transaction(['sessions', 'chunks'], 'readonly');
                    const req = tx.objectStore('sessions').getAll();
                    req.onsuccess = function () {
                        const rows = (req.result || []).filter(function (s) {
                            if (!s || (s.status !== 'recording' && s.status !== 'interrupted' && s.status !== 'ready')) return false;
                            if (courseId && s.courseId && s.courseId !== courseId) return false;
                            if (cardId && s.cardId && s.cardId !== cardId) return false;
                            return (s.byteCount || 0) > 0 || (s.chunkCount || 0) > 0;
                        });
                        if (!rows.length) { resolve(null); return; }
                        rows.sort(function (a, b) { return (b.updatedAt || 0) - (a.updatedAt || 0); });
                        const best = rows[0];
                        const idx = tx.objectStore('chunks').index('by_session');
                        const cReq = idx.getAll(IDBKeyRange.only(best.sessionId));
                        cReq.onsuccess = function () {
                            const chunks = (cReq.result || []).slice().sort(function (a, b) { return (a.seq || 0) - (b.seq || 0); });
                            if (!chunks.length) { resolve(null); return; }
                            resolve({ session: best, blobs: chunks.map(function (c) { return c.blob; }).filter(Boolean) });
                        };
                        cReq.onerror = function () { resolve(null); };
                    };
                    req.onerror = function () { resolve(null); };
                } catch (e) { resolve(null); }
            });
        });
    }

    function sendBeaconJson(path, obj) {
        const url = apiUrl(path);
        const json = JSON.stringify(obj);
        try {
            if (navigator.sendBeacon && json.length < 60000) {
                const blob = new Blob([json], { type: 'application/json' });
                if (navigator.sendBeacon(url, blob)) return true;
            }
        } catch (e) {}
        try {
            fetch(url, {
                method: 'POST',
                credentials: 'include',
                keepalive: true,
                headers: { 'Content-Type': 'application/json' },
                body: json,
            }).catch(function () {});
            return true;
        } catch (e) { return false; }
    }

    function queueServerChunkUpload(ctx, seq, blob) {
        if (!ctx || !ctx.sessionId || !blob || !blob.size) return;
        const qs = new URLSearchParams({
            session_id: ctx.sessionId,
            seq: String(seq),
            mime_type: ctx.mimeType || 'video/webm',
            card_id: ctx.cardId || 'card',
            course_id: ctx.courseId || '',
        }).toString();
        ctx.uploadChain = (ctx.uploadChain || Promise.resolve()).then(function () {
            return fetch(apiUrl('/api/course/recorder-chunk?' + qs), {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/octet-stream' },
                body: blob,
            }).catch(function () {});
        });
    }

    function buildSessionMetaPayload(cardEl, ctx, statusVal) {
        const snap = cardEl ? extractIsolatedCardSnapshot(cardEl) : { title: 'Siraugga Isolated Card Recording', transcript: '' };
        const regName = (typeof window.progressState === 'object' && window.progressState && window.progressState.registration && window.progressState.registration.full_name)
            || (typeof window.progressState === 'object' && window.progressState && window.progressState.learner_name)
            || 'Siraugga User';
        return {
            session_id: ctx.sessionId,
            status: statusVal,
            card_id: ctx.cardId || getCardId(cardEl),
            course_id: ctx.courseId || getCourseIdContext(),
            title: snap.title,
            learner: regName,
            mime_type: ctx.mimeType || 'video/webm',
            transcript: (ctx.c2d && ctx.c2d._lastTranscript) || snap.transcript || '',
            logs: (ctx.logs || STATE.logs).slice(-60),
        };
    }

    function flushActiveRecordingsForExit(isClosing) {
        STATE.activeCards.forEach(function (cardEl) {
            const ctx = STATE.recorders.get(cardEl);
            if (!ctx || !ctx.mediaRecorder) return;
            const st = ctx.mediaRecorder.state;
            if (st !== 'recording' && st !== 'paused') return;
            try { ctx.mediaRecorder.requestData(); } catch (e) {}
            const payload = buildSessionMetaPayload(cardEl, ctx, isClosing ? 'interrupted' : 'recording');
            idbPutSession({
                sessionId: ctx.sessionId,
                cardId: payload.card_id,
                courseId: payload.course_id,
                title: payload.title,
                learner: payload.learner,
                mimeType: payload.mime_type,
                startedAt: ctx.startedAtIso || new Date().toISOString(),
                updatedAt: Date.now(),
                status: isClosing ? 'interrupted' : 'recording',
                logs: payload.logs,
                transcript: payload.transcript,
                byteCount: ctx.byteCount || 0,
                chunkCount: ctx.chunkSeq || 0,
            });
            if (isClosing) {
                sendBeaconJson('/api/course/recorder-log', {
                    seq: ++STATE.seq,
                    ts: new Date().toISOString(),
                    state: 'interrupted',
                    native_state: st,
                    card_id: payload.card_id,
                    resolution: '1920x1080',
                    fps: 30,
                    mime_type: payload.mime_type,
                    bytes: ctx.byteCount || 0,
                    detail: 'Browser closing or page unloading; recording chunks preserved for recovery',
                    course_id: payload.course_id,
                });
                sendBeaconJson('/api/course/recorder-finalize', payload);
            }
        });
    }

    function installExitPersistenceHooks() {
        if (STATE.exitHooksInstalled) return;
        STATE.exitHooksInstalled = true;
        window.addEventListener('beforeunload', function (e) {
            let hasActive = false;
            STATE.activeCards.forEach(function (cardEl) {
                const ctx = STATE.recorders.get(cardEl);
                if (ctx && ctx.mediaRecorder && (ctx.mediaRecorder.state === 'recording' || ctx.mediaRecorder.state === 'paused')) {
                    hasActive = true;
                }
            });
            if (!hasActive) return;
            flushActiveRecordingsForExit(true);
            e.preventDefault();
            e.returnValue = '';
        });
        window.addEventListener('pagehide', function () {
            flushActiveRecordingsForExit(true);
        });
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'hidden') {
                flushActiveRecordingsForExit(false);
            }
        });
    }

    window.__sirauggaRecorderLogs = STATE.logs;

    function apiUrl(path) {
        const base = (typeof window.API_BASE === 'string' && window.API_BASE) ? window.API_BASE.replace(/\/+$/, '') : '';
        return base + path;
    }

    function announceText(msg) {
        if (typeof window.announce === 'function') {
            window.announce(msg);
            return;
        }
        const el = document.getElementById('announcer') || document.getElementById('exam-announcer');
        if (el) {
            el.textContent = '';
            setTimeout(function () { el.textContent = msg; }, 30);
        }
    }

    function escapeHtml(str) {
        return String(str == null ? '' : str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function isLocalLoopbackHost(host) {
        const h = String(host || '').toLowerCase();
        return h === 'localhost' || h === '127.0.0.1' || h === '::1' || h === '[::1]';
    }

    async function verifySecureConnection() {
        const host = window.location.hostname || '';
        const isLocal = isLocalLoopbackHost(host);
        if (window.location.protocol === 'http:' && !isLocal && (host === 'mikeytech.dev' || host === 'www.mikeytech.dev' || host === 'siraugga.mikeytech.dev')) {
            try {
                window.location.replace('https://' + window.location.host + window.location.pathname + window.location.search + window.location.hash);
                return { ok: false, upgrading: true };
            } catch (e) {}
        }

        const browserSecure = Boolean(window.isSecureContext);
        let serverInfo = null;
        try {
            const res = await fetch(apiUrl('/api/course/connection-status'), {
                method: 'GET',
                credentials: 'include',
                cache: 'no-store',
            });
            if (res.ok) serverInfo = await res.json();
        } catch (e) {}

        const verified = browserSecure && (!serverInfo || Boolean(serverInfo.secure_context));
        const label = serverInfo && serverInfo.tls_label
            ? serverInfo.tls_label
            : (browserSecure ? ('Secure Context Verified (' + (host || 'local') + ')') : 'Insecure Context — HTTPS Required');

        STATE.secureConnection = {
            verified: verified,
            browserSecure: browserSecure,
            protocol: window.location.protocol,
            host: host,
            server: serverInfo,
            label: label,
        };
        window.__sirauggaSecureConnection = STATE.secureConnection;
        updateConnectionBadges();
        return STATE.secureConnection;
    }

    function updateConnectionBadges() {
        const info = STATE.secureConnection;
        if (!info) return;
        document.querySelectorAll('[data-secure-conn-badge]').forEach(function (el) {
            el.textContent = info.verified ? ('🔒 ' + info.label) : ('⚠ ' + info.label);
            el.setAttribute('data-secure-verified', info.verified ? 'true' : 'false');
            el.className = info.verified
                ? 'text-[11px] font-mono px-2.5 py-1 rounded bg-emerald-950/90 text-emerald-300 border border-emerald-700/70'
                : 'text-[11px] font-mono px-2.5 py-1 rounded bg-rose-950/90 text-rose-300 border border-rose-700/70';
        });
    }

    function getCardId(cardEl) {
        if (!cardEl) return 'card';
        if (cardEl.id) return cardEl.id;
        if (cardEl.dataset && cardEl.dataset.recorderCardId) return cardEl.dataset.recorderCardId;
        const gen = 'card-' + (STATE.seq + 1) + '-' + Math.random().toString(36).slice(2, 7);
        cardEl.dataset.recorderCardId = gen;
        return gen;
    }

    function getCourseIdContext() {
        if (typeof window.courseId === 'string' && window.courseId) return window.courseId;
        return '';
    }

    function logRecorderState(cardEl, stateName, detail) {
        const ctx = cardEl ? (STATE.recorders.get(cardEl) || {}) : {};
        const nativeState = ctx.mediaRecorder ? ctx.mediaRecorder.state : 'inactive';
        const entry = {
            seq: ++STATE.seq,
            ts: new Date().toISOString(),
            state: String(stateName || 'idle'),
            native_state: nativeState,
            card_id: getCardId(cardEl),
            resolution: '1920x1080',
            fps: 30,
            mime_type: ctx.mimeType || '',
            bytes: (detail && detail.bytes) || (ctx.videoBlob ? ctx.videoBlob.size : 0),
            detail: (detail && detail.message) || '',
            course_id: getCourseIdContext(),
        };
        STATE.logs.push(entry);
        if (ctx.logs) ctx.logs.push(entry);

        if (cardEl) {
            cardEl.setAttribute('data-recorder-state', entry.state);
            const badge = cardEl.querySelector('[data-recorder-state-badge]');
            if (badge) {
                const labels = {
                    idle: 'Recorder Idle',
                    isolated: 'Isolated (Ready to Record)',
                    unisolated: 'Isolation Exited',
                    recording: 'Recording 1080p @ 30fps',
                    paused: 'Paused',
                    resumed: 'Recording 1080p @ 30fps',
                    rendering: 'Rendering 1080p Recording...',
                    preview_ready: 'Preview Ready (Click Preview)',
                    previewing: 'Playing In-Card Preview',
                    saving: 'Saving Standalone HTML...',
                    saved: 'Standalone HTML Saved ✓',
                    interrupted: 'Saved on Exit (Recoverable)',
                    recovered: 'Recovered Previous Recording ✓',
                    error: 'Recorder Error',
                };
                badge.textContent = labels[entry.state] || entry.state;
                badge.setAttribute('data-state', entry.state);
            }
            const logList = cardEl.querySelector('[data-recorder-log-list]');
            if (logList) {
                const li = document.createElement('li');
                li.textContent = '[' + entry.ts + '] state=' + entry.state + ' (MediaRecorder=' + entry.native_state + ') ' + entry.resolution + ' ' + entry.fps + 'fps' + (entry.detail ? ' — ' + entry.detail : '');
                logList.appendChild(li);
            }
        }

        try {
            fetch(apiUrl('/api/course/recorder-log'), {
                method: 'POST',
                credentials: 'include',
                keepalive: true,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(entry),
            }).catch(function () {});
        } catch (e) {}

        return entry;
    }

    function ensureIsolationStyles() {
        if (document.getElementById('siraugga-card-recorder-styles')) return;
        const st = document.createElement('style');
        st.id = 'siraugga-card-recorder-styles';
        st.textContent = [
            '.siraugga-hidden-isolated { display: none !important; }',
            'body.siraugga-isolation-active { background: #020617 !important; overflow: auto !important; }',
            '.siraugga-isolated-card { max-width: 1120px !important; margin: 18px auto !important; border: 2px solid #2dd4bf !important; box-shadow: 0 0 0 4px rgba(45, 212, 191, 0.18), 0 24px 60px rgba(0, 0, 0, 0.85) !important; position: relative !important; z-index: 40 !important; }',
        ].join('\n');
        document.head.appendChild(st);
    }

    function hideNodeForIsolation(node) {
        if (!node || STATE.hiddenNodes.has(node)) return;
        STATE.hiddenNodes.set(node, {
            ariaHidden: node.getAttribute('aria-hidden'),
            inert: Boolean(node.inert),
        });
        node.setAttribute('aria-hidden', 'true');
        node.inert = true;
        node.classList.add('siraugga-hidden-isolated');
    }

    function isolateCard(cardEl) {
        if (!cardEl) return false;
        ensureIsolationStyles();
        if (STATE.isolatedCard && STATE.isolatedCard !== cardEl) {
            unisolateCard(true);
        }
        if (STATE.isolatedCard === cardEl && cardEl.getAttribute('data-card-isolated') === 'true') {
            return true;
        }

        let cur = cardEl;
        while (cur && cur !== document.body && cur.parentElement) {
            const parent = cur.parentElement;
            Array.from(parent.children).forEach(function (sib) {
                if (sib === cur) return;
                const tag = sib.tagName;
                if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'LINK') return;
                if (sib.id === 'announcer' || sib.id === 'exam-announcer' || sib.hasAttribute('data-recorder-keep-live')) return;
                if (sib.getAttribute('aria-live') && sib.classList.contains('sr-only')) return;
                hideNodeForIsolation(sib);
            });
            cur = parent;
        }

        document.body.classList.add('siraugga-isolation-active');
        document.body.setAttribute('data-isolation-active', 'true');
        cardEl.setAttribute('data-card-isolated', 'true');
        cardEl.classList.add('siraugga-isolated-card');
        STATE.isolatedCard = cardEl;

        const isoBtn = cardEl.querySelector('[data-recorder-action="isolate"]');
        if (isoBtn) {
            isoBtn.setAttribute('aria-pressed', 'true');
            isoBtn.textContent = 'Exit Isolation';
        }

        logRecorderState(cardEl, 'isolated', { message: 'Single active visual response card isolated in UI' });
        announceText('Response card isolated. Only this active visual response card is visible.');
        const focusTarget = cardEl.querySelector('h1, h2, h3, [data-recorder-action="record"]') || cardEl;
        if (focusTarget && typeof focusTarget.focus === 'function') {
            if (!focusTarget.hasAttribute('tabindex') && /^H[1-6]|ARTICLE|SECTION$/.test(focusTarget.tagName)) {
                focusTarget.setAttribute('tabindex', '-1');
            }
            try { focusTarget.focus({ preventScroll: false }); } catch (e) {}
        }
        return true;
    }

    function unisolateCard(silent) {
        const cardEl = STATE.isolatedCard;
        STATE.hiddenNodes.forEach(function (prev, node) {
            node.classList.remove('siraugga-hidden-isolated');
            node.inert = prev.inert;
            if (prev.ariaHidden == null) node.removeAttribute('aria-hidden');
            else node.setAttribute('aria-hidden', prev.ariaHidden);
        });
        STATE.hiddenNodes.clear();
        document.body.classList.remove('siraugga-isolation-active');
        document.body.removeAttribute('data-isolation-active');

        if (cardEl) {
            cardEl.removeAttribute('data-card-isolated');
            cardEl.classList.remove('siraugga-isolated-card');
            const isoBtn = cardEl.querySelector('[data-recorder-action="isolate"]');
            if (isoBtn) {
                isoBtn.setAttribute('aria-pressed', 'false');
                isoBtn.textContent = 'Isolate Card';
            }
            if (!silent) {
                logRecorderState(cardEl, 'unisolated', { message: 'Restored full workspace UI' });
                announceText('Card isolation exited. Full UI restored.');
            }
        }
        STATE.isolatedCard = null;
    }

    function extractIframeCourseInfo(cardEl) {
        const iframe = cardEl.querySelector('iframe');
        if (iframe) {
            try {
                const doc = iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
                if (doc && doc.body) {
                    const heading = doc.getElementById('main-heading');
                    const secHead = doc.getElementById('section-heading');
                    const prog = doc.getElementById('progress-label');
                    const concept = doc.getElementById('concept-summary');
                    const codeBox = doc.getElementById('code-snippet-box');
                    const termPre = doc.getElementById('terminal-output-pre');
                    const termsGate = doc.getElementById('course-terms-gate');
                    const regGate = doc.getElementById('course-registration-gate');
                    const surveySec = doc.getElementById('course-survey-section');
                    const certPanel = doc.getElementById('certificate-issued-panel');
                    let activeStage = 'Curriculum Workspace';
                    if (termsGate && !termsGate.classList.contains('hidden')) activeStage = 'Mandatory Terms & Privacy Agreement';
                    else if (regGate && !regGate.classList.contains('hidden')) activeStage = 'User Registration';
                    else if (certPanel && !certPanel.classList.contains('hidden')) activeStage = 'Signed Certificate Issued';
                    else if (surveySec && !surveySec.classList.contains('hidden')) activeStage = 'End-of-Course Survey';
                    return {
                        title: heading ? heading.innerText.trim() : 'Interactive Course',
                        stage: activeStage,
                        progress: prog ? prog.innerText.trim() : '',
                        section: secHead ? secHead.innerText.trim() : '',
                        summary: concept ? concept.innerText.trim() : '',
                        code: codeBox ? codeBox.innerText.trim() : '',
                        output: termPre ? termPre.innerText.trim() : '',
                    };
                }
            } catch (e) {}
        }
        return STATE.latestCourseSnapshot || null;
    }

    function extractIsolatedCardSnapshot(cardEl) {
        const lines = [];
        const h = cardEl.querySelector('h1, h2, h3');
        const title = h ? h.innerText.trim() : 'Siraugga Active Response Card';
        const badgeEl = cardEl.querySelector('.status-badge, #step-status-badge');
        const statusText = badgeEl ? badgeEl.innerText.trim() : 'Active';

        const courseSnap = extractIframeCourseInfo(cardEl);
        if (courseSnap) {
            if (courseSnap.stage) lines.push('ACTIVE STAGE: ' + courseSnap.stage);
            if (courseSnap.progress) lines.push(courseSnap.progress);
            if (courseSnap.section) lines.push(courseSnap.section);
            if (courseSnap.summary) lines.push(courseSnap.summary);
            if (courseSnap.code) {
                lines.push('--- CODE / COMMAND ---');
                courseSnap.code.split('\n').slice(0, 12).forEach(function (l) { lines.push(l); });
            }
            if (courseSnap.output) {
                lines.push('--- SANDBOX OUTPUT ---');
                courseSnap.output.split('\n').slice(0, 8).forEach(function (l) { lines.push(l); });
            }
        } else {
            const visibleWalk = cardEl.querySelectorAll('h1, h2, h3, h4, p, li, pre code, label, button[aria-checked="true"], [role="status"]');
            visibleWalk.forEach(function (el) {
                if (el.closest('[data-recorder-chrome="true"]')) return;
                if (el.offsetParent === null) return;
                const txt = (el.innerText || '').trim();
                if (txt && txt.length > 1) lines.push(txt);
            });
            cardEl.querySelectorAll('input, textarea, select').forEach(function (inp) {
                if (inp.closest('[data-recorder-chrome="true"]')) return;
                if (inp.offsetParent === null) return;
                if (inp.type === 'password') return;
                const lbl = inp.getAttribute('aria-label') || inp.id || 'field';
                if (inp.type === 'checkbox' || inp.type === 'radio') {
                    lines.push(lbl + ': ' + (inp.checked ? '[Checked]' : '[Unchecked]'));
                } else if (inp.value) {
                    lines.push(lbl + ': ' + String(inp.value).slice(0, 140));
                }
            });
        }

        const deduped = [];
        lines.forEach(function (l) {
            if (!deduped.length || deduped[deduped.length - 1] !== l) deduped.push(l);
        });

        return {
            title: title,
            status: statusText,
            lines: deduped.slice(0, 48),
            transcript: deduped.join('\n'),
        };
    }

    function wrapCanvasLines(ctx, text, maxWidth) {
        const out = [];
        String(text || '').split('\n').forEach(function (para) {
            const words = para.split(/\s+/).filter(Boolean);
            if (!words.length) {
                out.push('');
                return;
            }
            let cur = words[0];
            for (let i = 1; i < words.length; i++) {
                const candidate = cur + ' ' + words[i];
                if (ctx.measureText(candidate).width <= maxWidth) {
                    cur = candidate;
                } else {
                    out.push(cur);
                    cur = words[i];
                }
            }
            out.push(cur);
        });
        return out;
    }

    function drawCardFrame(ctx, cardEl, frameNum, elapsedMs) {
        const W = 1920;
        const H = 1080;
        const snap = extractIsolatedCardSnapshot(cardEl);
        ctx._lastTranscript = snap.transcript;

        ctx.fillStyle = '#020617';
        ctx.fillRect(0, 0, W, H);

        ctx.fillStyle = '#0f172a';
        ctx.strokeStyle = '#2dd4bf';
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.roundRect(48, 40, W - 96, H - 80, 20);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = '#0b1220';
        ctx.fillRect(52, 44, W - 104, 112);

        const recPulse = (Math.floor(frameNum / 15) % 2) === 0;
        ctx.fillStyle = recPulse ? '#ef4444' : '#991b1b';
        ctx.beginPath();
        ctx.arc(100, 100, 14, 0, Math.PI * 2);
        ctx.fill();

        const sec = (elapsedMs / 1000).toFixed(1);
        ctx.fillStyle = '#f8fafc';
        ctx.font = 'bold 34px system-ui, -apple-system, sans-serif';
        ctx.fillText(snap.title.slice(0, 72), 134, 96);

        ctx.fillStyle = '#2dd4bf';
        ctx.font = '600 22px monospace';
        ctx.fillText('ISOLATED RESPONSE CARD  |  1920x1080 @ 30fps  |  REC ' + sec + 's  |  FRAME #' + frameNum, 134, 134);

        ctx.fillStyle = '#134e4a';
        ctx.beginPath();
        ctx.roundRect(W - 360, 74, 272, 48, 10);
        ctx.fill();
        ctx.fillStyle = '#99f6e4';
        ctx.font = 'bold 20px monospace';
        ctx.fillText(snap.status.slice(0, 22), W - 340, 105);

        ctx.strokeStyle = '#1e293b';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(68, 160);
        ctx.lineTo(W - 68, 160);
        ctx.stroke();

        let y = 212;
        const maxY = H - 120;
        const maxW = W - 180;
        ctx.font = '24px system-ui, -apple-system, sans-serif';
        for (let i = 0; i < snap.lines.length; i++) {
            const rawLine = snap.lines[i];
            const isCode = rawLine.startsWith('---') || rawLine.startsWith('$ ') || rawLine.includes('{') || rawLine.includes('param ') || rawLine.includes('resource ');
            ctx.font = isCode ? '21px monospace' : (i === 0 ? 'bold 26px system-ui, -apple-system, sans-serif' : '24px system-ui, -apple-system, sans-serif');
            ctx.fillStyle = isCode ? '#6ee7b7' : (i === 0 ? '#67e8f9' : '#e2e8f0');
            const wrapped = wrapCanvasLines(ctx, rawLine, maxW);
            for (let j = 0; j < wrapped.length; j++) {
                if (y > maxY) break;
                ctx.fillText(wrapped[j], 90, y);
                y += 34;
            }
            y += 6;
            if (y > maxY) break;
        }

        ctx.fillStyle = '#090d16';
        ctx.fillRect(52, H - 96, W - 104, 52);
        ctx.fillStyle = '#94a3b8';
        ctx.font = '18px monospace';
        const secLabel = (STATE.secureConnection && STATE.secureConnection.label) ? STATE.secureConnection.label : 'Secure Context Verified';
        ctx.fillText(secLabel + '  |  Strictly Isolated Card Capture  |  Standalone Offline Export Ready', 90, H - 64);
    }

    function pickSupportedMimeType() {
        const candidates = [
            'video/webm;codecs=vp9',
            'video/webm;codecs=vp8',
            'video/webm',
            'video/mp4',
        ];
        if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') {
            return '';
        }
        for (let i = 0; i < candidates.length; i++) {
            if (MediaRecorder.isTypeSupported(candidates[i])) return candidates[i];
        }
        return '';
    }

    function blobToBase64(blob) {
        return new Promise(function (resolve, reject) {
            const reader = new FileReader();
            reader.onloadend = function () {
                const res = String(reader.result || '');
                const idx = res.indexOf(',');
                resolve(idx >= 0 ? res.slice(idx + 1) : res);
            };
            reader.onerror = function () { reject(new Error('Failed to encode recorded video blob')); };
            reader.readAsDataURL(blob);
        });
    }

    function buildStandaloneOfflineHtml(meta, videoBase64, mimeType, logs, transcriptText) {
        const safeTitle = escapeHtml(meta.title || 'Siraugga Isolated Card Recording');
        const safeLearner = escapeHtml(meta.learner || 'Learner');
        const safeDate = escapeHtml(meta.recordedAt || new Date().toISOString());
        const safeMime = escapeHtml(mimeType || 'video/webm');
        const safeLogsJson = JSON.stringify(logs || [], null, 2).replace(/<\//g, '<\\/');
        const safeTranscript = escapeHtml(transcriptText || '');

        return [
            '<!DOCTYPE html>',
            '<html lang="en">',
            '<head>',
            '<meta charset="UTF-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
            '<title>' + safeTitle + ' — Standalone Offline Playback</title>',
            '<style>',
            'body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background: #020617; color: #e2e8f0; padding: 24px; line-height: 1.5; }',
            'main { max-width: 1100px; margin: 0 auto; background: #0f172a; border: 2px solid #2dd4bf; border-radius: 14px; padding: 24px; box-shadow: 0 20px 50px rgba(0,0,0,.6); }',
            'h1 { margin: 0 0 8px; color: #5eead4; font-size: 1.5rem; }',
            '.meta { font-family: monospace; font-size: 0.85rem; color: #94a3b8; margin-bottom: 16px; display: flex; flex-wrap: wrap; gap: 12px; }',
            '.pill { background: #042f2e; color: #99f6e4; border: 1px solid #0f766e; padding: 4px 10px; border-radius: 6px; }',
            'video { width: 100%; max-height: 70vh; background: #000; border-radius: 10px; border: 1px solid #334155; display: block; }',
            '.controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 14px 0; }',
            'button, select { background: #0f766e; color: #fff; border: 1px solid #2dd4bf; padding: 8px 14px; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 0.9rem; }',
            'button:focus, select:focus { outline: 3px solid #99f6e4; outline-offset: 2px; }',
            'pre { background: #020617; color: #cbd5e1; border: 1px solid #1e293b; border-radius: 8px; padding: 14px; overflow-x: auto; font-size: 0.8rem; max-height: 260px; white-space: pre-wrap; }',
            '.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; }',
            '</style>',
            '</head>',
            '<body>',
            '<main role="main" aria-labelledby="offline-title">',
            '<h1 id="offline-title">' + safeTitle + '</h1>',
            '<div class="meta">',
            '<span class="pill">Standalone Offline Recording (Zero Network Required)</span>',
            '<span class="pill">Resolution: 1920x1080 (1080p) @ 30fps</span>',
            '<span class="pill">Learner: ' + safeLearner + '</span>',
            '<span class="pill">Recorded: ' + safeDate + '</span>',
            '</div>',
            '<video id="offline-video" controls playsinline preload="auto" aria-label="Recorded Isolated Response Card Video Playback (1080p 30fps)"></video>',
            '<div class="controls" role="group" aria-label="Offline Video Controls">',
            '<button type="button" id="btn-play">Play / Pause</button>',
            '<button type="button" id="btn-restart">Restart</button>',
            '<label for="rate-sel">Speed:</label>',
            '<select id="rate-sel"><option value="0.5">0.5x</option><option value="1" selected>1x</option><option value="1.5">1.5x</option><option value="2">2x</option></select>',
            '<span id="video-dims" role="status" style="font-family:monospace;font-size:0.85rem;color:#67e8f9;">Loading offline stream...</span>',
            '</div>',
            '<details open><summary style="cursor:pointer;font-weight:700;color:#fbbf24;margin:12px 0 6px;">MediaRecorder State Transition Log (recording, rendering, saving)</summary>',
            '<pre id="state-log-pre">' + escapeHtml(safeLogsJson) + '</pre></details>',
            '<details><summary style="cursor:pointer;font-weight:700;color:#67e8f9;margin:12px 0 6px;">Captured Response Card Text Transcript</summary>',
            '<pre id="transcript-pre">' + safeTranscript + '</pre></details>',
            '<div id="offline-announcer" class="sr-only" aria-live="polite"></div>',
            '</main>',
            '<script id="embedded-video-b64" type="text/plain">' + videoBase64 + '</script>',
            '<script>',
            '(function () {',
            '  var b64 = (document.getElementById("embedded-video-b64").textContent || "").trim();',
            '  var mime = ' + JSON.stringify(safeMime) + ';',
            '  var video = document.getElementById("offline-video");',
            '  var dims = document.getElementById("video-dims");',
            '  var bin = atob(b64);',
            '  var bytes = new Uint8Array(bin.length);',
            '  for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);',
            '  var blob = new Blob([bytes], { type: mime });',
            '  video.src = URL.createObjectURL(blob);',
            '  video.addEventListener("loadedmetadata", function () {',
            '    dims.textContent = "Ready offline: " + (video.videoWidth || 1920) + "x" + (video.videoHeight || 1080) + " (" + (isFinite(video.duration) ? video.duration.toFixed(1) + "s" : "stream") + ")";',
            '  });',
            '  document.getElementById("btn-play").onclick = function () { if (video.paused) video.play(); else video.pause(); };',
            '  document.getElementById("btn-restart").onclick = function () { video.currentTime = 0; video.play(); };',
            '  document.getElementById("rate-sel").onchange = function (e) { video.playbackRate = parseFloat(e.target.value) || 1; };',
            '})();',
            '</script>',
            '</body>',
            '</html>',
        ].join('\n');
    }

    function setRecorderButtons(cardEl, mode) {
        const recBtn = cardEl.querySelector('[data-recorder-action="record"]');
        const stopBtn = cardEl.querySelector('[data-recorder-action="stop"]');
        const prevBtn = cardEl.querySelector('[data-recorder-action="preview"]');
        const dlBtn = cardEl.querySelector('[data-recorder-action="download"]');
        const dlWebmBtn = cardEl.querySelector('[data-recorder-action="download-webm"]');

        if (mode === 'recording') {
            if (recBtn) recBtn.disabled = true;
            if (stopBtn) stopBtn.disabled = false;
            if (prevBtn) prevBtn.disabled = true;
            if (dlBtn) dlBtn.disabled = true;
            if (dlWebmBtn) dlWebmBtn.disabled = true;
        } else if (mode === 'rendering') {
            if (recBtn) recBtn.disabled = true;
            if (stopBtn) stopBtn.disabled = true;
            if (prevBtn) prevBtn.disabled = true;
            if (dlBtn) dlBtn.disabled = true;
            if (dlWebmBtn) dlWebmBtn.disabled = true;
        } else if (mode === 'ready') {
            if (recBtn) recBtn.disabled = false;
            if (stopBtn) stopBtn.disabled = true;
            if (prevBtn) prevBtn.disabled = false;
            if (dlBtn) dlBtn.disabled = false;
            if (dlWebmBtn) dlWebmBtn.disabled = false;
        } else {
            if (recBtn) recBtn.disabled = false;
            if (stopBtn) stopBtn.disabled = true;
            if (prevBtn) prevBtn.disabled = true;
            if (dlBtn) dlBtn.disabled = true;
            if (dlWebmBtn) dlWebmBtn.disabled = true;
        }
    }

    async function startRecording(cardEl) {
        if (!cardEl) return false;
        if (cardEl.getAttribute('data-preview-mode') === 'true') {
            announceText('Recording is disabled while previewing the course.');
            return false;
        }
        if (!window.isSecureContext) {
            logRecorderState(cardEl, 'error', { message: 'MediaRecorder requires a secure HTTPS or loopback context.' });
            announceText('Cannot start recording: secure HTTPS domain connection required.');
            return false;
        }
        if (typeof MediaRecorder === 'undefined') {
            logRecorderState(cardEl, 'error', { message: 'MediaRecorder API is unavailable in this browser.' });
            announceText('MediaRecorder API is not supported in this browser.');
            return false;
        }

        let ctx = STATE.recorders.get(cardEl);
        if (!ctx) {
            ctx = { logs: [] };
            STATE.recorders.set(cardEl, ctx);
        }
        if (ctx.mediaRecorder && ctx.mediaRecorder.state === 'recording') {
            return true;
        }

        installExitPersistenceHooks();
        isolateCard(cardEl);
        hideRecoveryBanner(cardEl);

        const canvas = document.createElement('canvas');
        canvas.width = 1920;
        canvas.height = 1080;
        const c2d = canvas.getContext('2d');
        const startTs = performance.now();
        let frameNum = 0;

        drawCardFrame(c2d, cardEl, ++frameNum, 0);

        const stream = canvas.captureStream(30);
        const tracks = stream.getVideoTracks();
        if (tracks.length && typeof tracks[0].applyConstraints === 'function') {
            try {
                await tracks[0].applyConstraints({ width: 1920, height: 1080, frameRate: 30 });
            } catch (e) {}
        }

        const mimeType = pickSupportedMimeType();
        const opts = mimeType ? { mimeType: mimeType, videoBitsPerSecond: 4000000 } : { videoBitsPerSecond: 4000000 };
        let recorder;
        try {
            recorder = new MediaRecorder(stream, opts);
        } catch (e) {
            recorder = mimeType ? new MediaRecorder(stream, { mimeType: mimeType }) : new MediaRecorder(stream);
        }

        const sessionId = 'rec_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
        const cardId = getCardId(cardEl);
        const courseIdCtx = getCourseIdContext();
        const snapInit = extractIsolatedCardSnapshot(cardEl);
        const regNameInit = (typeof window.progressState === 'object' && window.progressState && window.progressState.registration && window.progressState.registration.full_name)
            || (typeof window.progressState === 'object' && window.progressState && window.progressState.learner_name)
            || 'Siraugga User';

        const chunks = [];
        ctx.sessionId = sessionId;
        ctx.cardId = cardId;
        ctx.courseId = courseIdCtx;
        ctx.startedAtIso = new Date().toISOString();
        ctx.chunkSeq = 0;
        ctx.byteCount = 0;
        ctx.uploadChain = Promise.resolve();
        ctx.canvas = canvas;
        ctx.c2d = c2d;
        ctx.stream = stream;
        ctx.mediaRecorder = recorder;
        ctx.chunks = chunks;
        ctx.mimeType = recorder.mimeType || mimeType || 'video/webm';
        ctx.startTs = startTs;
        ctx.videoBlob = null;
        ctx.standaloneHtmlBlob = null;
        if (ctx.blobUrl) {
            try { URL.revokeObjectURL(ctx.blobUrl); } catch (e) {}
            ctx.blobUrl = '';
        }
        STATE.activeCards.add(cardEl);

        idbPutSession({
            sessionId: sessionId,
            cardId: cardId,
            courseId: courseIdCtx,
            title: snapInit.title,
            learner: regNameInit,
            mimeType: ctx.mimeType,
            startedAt: ctx.startedAtIso,
            updatedAt: Date.now(),
            status: 'recording',
            logs: (ctx.logs || []).slice(-60),
            transcript: snapInit.transcript || '',
            byteCount: 0,
            chunkCount: 0,
        });

        recorder.ondataavailable = function (ev) {
            if (ev && ev.data && ev.data.size > 0) {
                const seqNum = ctx.chunkSeq++;
                chunks.push(ev.data);
                ctx.byteCount += ev.data.size;
                idbAddChunk(sessionId, seqNum, ev.data);
                idbPutSession({
                    sessionId: sessionId,
                    cardId: cardId,
                    courseId: courseIdCtx,
                    title: snapInit.title,
                    learner: regNameInit,
                    mimeType: ctx.mimeType,
                    startedAt: ctx.startedAtIso,
                    updatedAt: Date.now(),
                    status: (recorder.state === 'inactive') ? 'finalizing' : 'recording',
                    logs: (ctx.logs || []).slice(-60),
                    transcript: (ctx.c2d && ctx.c2d._lastTranscript) || snapInit.transcript || '',
                    byteCount: ctx.byteCount,
                    chunkCount: ctx.chunkSeq,
                });
                queueServerChunkUpload(ctx, seqNum, ev.data);
            }
        };

        ctx.timerId = setInterval(function () {
            if (!ctx.mediaRecorder || ctx.mediaRecorder.state !== 'recording') return;
            drawCardFrame(c2d, cardEl, ++frameNum, performance.now() - startTs);
        }, 33);

        recorder.start(250);
        setRecorderButtons(cardEl, 'recording');
        logRecorderState(cardEl, 'recording', { message: 'MediaRecorder started strictly on isolated card at 1920x1080 30fps (durable backup active)' });
        announceText('Recording isolated response card at 1080p and 30 frames per second.');
        return true;
    }

    function stopRecording(cardEl, options) {
        const opts = options || {};
        const ctx = cardEl ? STATE.recorders.get(cardEl) : null;
        if (!ctx || !ctx.mediaRecorder || ctx.mediaRecorder.state === 'inactive') {
            return Promise.resolve(null);
        }

        setRecorderButtons(cardEl, 'rendering');
        logRecorderState(cardEl, 'rendering', { message: 'Stopping MediaRecorder and rendering 1080p video + standalone offline HTML' });
        announceText('Stopping recording and rendering standalone offline playback package...');

        return new Promise(function (resolve) {
            const recorder = ctx.mediaRecorder;
            recorder.onstop = async function () {
                if (ctx.timerId) {
                    clearInterval(ctx.timerId);
                    ctx.timerId = null;
                }
                if (ctx.stream) {
                    ctx.stream.getTracks().forEach(function (t) { try { t.stop(); } catch (e) {} });
                }

                const blob = new Blob(ctx.chunks || [], { type: ctx.mimeType || 'video/webm' });
                ctx.videoBlob = blob;
                ctx.blobUrl = URL.createObjectURL(blob);

                let b64 = '';
                try {
                    b64 = await blobToBase64(blob);
                } catch (e) {
                    logRecorderState(cardEl, 'error', { message: e.message });
                }

                const snap = extractIsolatedCardSnapshot(cardEl);
                const regName = (typeof window.progressState === 'object' && window.progressState && window.progressState.registration && window.progressState.registration.full_name)
                    || (typeof window.progressState === 'object' && window.progressState && window.progressState.learner_name)
                    || 'Siraugga User';

                const meta = {
                    title: snap.title,
                    learner: regName,
                    recordedAt: new Date().toISOString(),
                };
                const transcriptText = ctx.c2d ? ctx.c2d._lastTranscript : snap.transcript;
                const htmlStr = buildStandaloneOfflineHtml(meta, b64, ctx.mimeType, ctx.logs || STATE.logs, transcriptText);
                ctx.standaloneHtmlBlob = new Blob([htmlStr], { type: 'text/html;charset=utf-8' });
                const tsSlug = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
                ctx.standaloneFilename = 'siraugga-recording-' + tsSlug + '.html';
                ctx.webmFilename = 'siraugga-recording-' + tsSlug + '.webm';

                if (ctx.sessionId) {
                    await idbPutSession({
                        sessionId: ctx.sessionId,
                        cardId: ctx.cardId || getCardId(cardEl),
                        courseId: ctx.courseId || getCourseIdContext(),
                        title: meta.title,
                        learner: meta.learner,
                        mimeType: ctx.mimeType || 'video/webm',
                        startedAt: ctx.startedAtIso || meta.recordedAt,
                        updatedAt: Date.now(),
                        status: 'ready',
                        logs: (ctx.logs || STATE.logs).slice(-60),
                        transcript: transcriptText || '',
                        byteCount: blob.size,
                        chunkCount: (ctx.chunks || []).length,
                    });
                    const finPayload = buildSessionMetaPayload(cardEl, ctx, 'ready');
                    Promise.resolve(ctx.uploadChain).then(function () {
                        fetch(apiUrl('/api/course/recorder-finalize'), {
                            method: 'POST',
                            credentials: 'include',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(finPayload),
                        }).catch(function () {});
                    });
                }

                setRecorderButtons(cardEl, 'ready');
                logRecorderState(cardEl, 'preview_ready', {
                    bytes: blob.size,
                    message: 'In-card preview ready (' + Math.round(blob.size / 1024) + ' KB WebM, standalone HTML ' + Math.round(ctx.standaloneHtmlBlob.size / 1024) + ' KB)',
                });
                announceText('Recording rendered. Use Preview Recording on the card to inspect playback before downloading.');

                if (opts.autoDownload) {
                    downloadStandalone(cardEl);
                }
                resolve(ctx);
            };
            try {
                recorder.stop();
            } catch (e) {
                resolve(null);
            }
        });
    }

    function togglePreview(cardEl) {
        const ctx = cardEl ? STATE.recorders.get(cardEl) : null;
        const wrap = cardEl ? cardEl.querySelector('[data-recorder-preview-wrap]') : null;
        const video = cardEl ? cardEl.querySelector('[data-recorder-preview-video]') : null;
        const btn = cardEl ? cardEl.querySelector('[data-recorder-action="preview"]') : null;
        const infoEl = cardEl ? cardEl.querySelector('[data-recorder-preview-meta]') : null;
        if (!ctx || !ctx.blobUrl || !wrap || !video) return;

        const willShow = wrap.classList.contains('hidden');
        if (willShow) {
            wrap.classList.remove('hidden');
            if (btn) btn.setAttribute('aria-expanded', 'true');
            if (video.src !== ctx.blobUrl) {
                video.src = ctx.blobUrl;
                try { video.load(); } catch (e) {}
            }
            video.onloadedmetadata = function () {
                if (infoEl) {
                    const w = video.videoWidth || 1920;
                    const h = video.videoHeight || 1080;
                    const dur = isFinite(video.duration) ? video.duration.toFixed(1) + 's' : 'recorded';
                    infoEl.textContent = 'Preview Ready: ' + w + 'x' + h + ' @ 30fps (' + dur + ', ' + Math.round(ctx.videoBlob.size / 1024) + ' KB)';
                }
            };
            if (infoEl) {
                infoEl.textContent = '1920x1080 @ 30fps (' + Math.round(ctx.videoBlob.size / 1024) + ' KB) — Previewing inside response card';
            }
            video.play().catch(function () {});
            logRecorderState(cardEl, 'previewing', { bytes: ctx.videoBlob.size, message: 'Playing embedded in-card recording preview' });
            announceText('Embedded recording preview opened in response card.');
            video.focus();
        } else {
            try { video.pause(); } catch (e) {}
            wrap.classList.add('hidden');
            if (btn) btn.setAttribute('aria-expanded', 'false');
        }
    }

    function triggerBlobDownload(blob, filename) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () { try { URL.revokeObjectURL(url); } catch (e) {} }, 2500);
    }

    function markSessionDownloaded(cardEl, ctx) {
        if (!ctx || !ctx.sessionId) return;
        idbPutSession({
            sessionId: ctx.sessionId,
            cardId: ctx.cardId || getCardId(cardEl),
            courseId: ctx.courseId || getCourseIdContext(),
            title: (ctx.recoveredMeta && ctx.recoveredMeta.title) || 'Siraugga Isolated Card Recording',
            learner: (ctx.recoveredMeta && ctx.recoveredMeta.learner) || 'Siraugga User',
            mimeType: ctx.mimeType || 'video/webm',
            startedAt: ctx.startedAtIso || new Date().toISOString(),
            updatedAt: Date.now(),
            status: 'downloaded',
            logs: (ctx.logs || []).slice(-60),
            transcript: '',
            byteCount: ctx.videoBlob ? ctx.videoBlob.size : 0,
            chunkCount: (ctx.chunks || []).length,
        });
        fetch(apiUrl('/api/course/recorder-discard'), {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: ctx.sessionId, remove: false }),
        }).catch(function () {});
        hideRecoveryBanner(cardEl);
    }

    function hideRecoveryBanner(cardEl) {
        const banner = cardEl ? cardEl.querySelector('[data-recorder-recovery-banner]') : null;
        if (banner) banner.classList.add('hidden');
    }

    function showRecoveryBanner(cardEl, info) {
        if (!cardEl || !info) return;
        const banner = cardEl.querySelector('[data-recorder-recovery-banner]');
        const msg = cardEl.querySelector('[data-recorder-recovery-text]');
        const dlServerHtml = cardEl.querySelector('[data-recorder-action="recover-server-html"]');
        const dlServerWebm = cardEl.querySelector('[data-recorder-action="recover-server-webm"]');
        if (!banner || !msg) return;
        const kb = Math.max(1, Math.round((info.byteCount || 0) / 1024));
        msg.textContent = 'Recovered recording from your previous session (' + kb + ' KB). Preview, download offline HTML, or discard it.';
        if (dlServerHtml && dlServerWebm) {
            if (info.serverHtmlUrl) {
                dlServerHtml.href = info.serverHtmlUrl;
                dlServerHtml.classList.remove('hidden');
            } else {
                dlServerHtml.classList.add('hidden');
            }
            if (info.serverWebmUrl) {
                dlServerWebm.href = info.serverWebmUrl;
                dlServerWebm.classList.remove('hidden');
            } else {
                dlServerWebm.classList.add('hidden');
            }
        }
        banner.classList.remove('hidden');
    }

    async function discardRecoveredSession(cardEl) {
        const ctx = cardEl ? STATE.recorders.get(cardEl) : null;
        const sid = (ctx && (ctx.recoveredSessionId || ctx.sessionId)) || '';
        if (sid) {
            await idbDeleteSession(sid);
            fetch(apiUrl('/api/course/recorder-discard'), {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sid, remove: true }),
            }).catch(function () {});
        }
        if (ctx) {
            ctx.recoveredSessionId = '';
            if (!ctx.mediaRecorder || ctx.mediaRecorder.state === 'inactive') {
                ctx.videoBlob = null;
                ctx.standaloneHtmlBlob = null;
                if (ctx.blobUrl) {
                    try { URL.revokeObjectURL(ctx.blobUrl); } catch (e) {}
                    ctx.blobUrl = '';
                }
                setRecorderButtons(cardEl, 'idle');
                logRecorderState(cardEl, 'idle', { message: 'Discarded recovered recording' });
            }
        }
        hideRecoveryBanner(cardEl);
        announceText('Recovered recording discarded.');
    }

    async function recoverSessionForCard(cardEl) {
        if (!cardEl) return false;
        if (cardEl.getAttribute('data-preview-mode') === 'true') return false;
        const ctx = STATE.recorders.get(cardEl);
        if (ctx && ctx.mediaRecorder && ctx.mediaRecorder.state !== 'inactive') return false;
        if (ctx && ctx.videoBlob) return false;

        const courseIdCtx = getCourseIdContext();
        const cardId = getCardId(cardEl);
        const found = await idbFindLatestRecoverable(courseIdCtx, cardId);
        if (found && found.blobs && found.blobs.length) {
            const sess = found.session;
            const blob = new Blob(found.blobs, { type: sess.mimeType || 'video/webm' });
            if (blob.size > 0) {
                let b64 = '';
                try { b64 = await blobToBase64(blob); } catch (e) {}
                const meta = {
                    title: sess.title || 'Recovered Siraugga Card Recording',
                    learner: sess.learner || 'Siraugga User',
                    recordedAt: sess.startedAt || new Date(sess.updatedAt || Date.now()).toISOString(),
                };
                const logs = Array.isArray(sess.logs) ? sess.logs : [];
                const htmlStr = buildStandaloneOfflineHtml(meta, b64, sess.mimeType || 'video/webm', logs, sess.transcript || '');
                const tsSlug = (meta.recordedAt || new Date().toISOString()).replace(/[:.]/g, '-').slice(0, 19);
                const targetCtx = ctx || { logs: [] };
                targetCtx.sessionId = sess.sessionId;
                targetCtx.recoveredSessionId = sess.sessionId;
                targetCtx.recoveredMeta = meta;
                targetCtx.cardId = sess.cardId || cardId;
                targetCtx.courseId = sess.courseId || courseIdCtx;
                targetCtx.mimeType = sess.mimeType || 'video/webm';
                targetCtx.startedAtIso = sess.startedAt || meta.recordedAt;
                targetCtx.chunks = found.blobs;
                targetCtx.videoBlob = blob;
                targetCtx.blobUrl = URL.createObjectURL(blob);
                targetCtx.standaloneHtmlBlob = new Blob([htmlStr], { type: 'text/html;charset=utf-8' });
                targetCtx.standaloneFilename = 'siraugga-recording-' + tsSlug + '.html';
                targetCtx.webmFilename = 'siraugga-recording-' + tsSlug + '.webm';
                STATE.recorders.set(cardEl, targetCtx);
                setRecorderButtons(cardEl, 'ready');
                logRecorderState(cardEl, 'recovered', {
                    bytes: blob.size,
                    message: 'Recovered interrupted recording from local browser storage (' + Math.round(blob.size / 1024) + ' KB)',
                });
                showRecoveryBanner(cardEl, { byteCount: blob.size });
                announceText('Recovered a recording from your previous session. Preview or download it from the recorder bar.');
                return true;
            }
        }

        try {
            const qs = new URLSearchParams({ course_id: courseIdCtx || '', card_id: cardId || '' }).toString();
            const res = await fetch(apiUrl('/api/course/recorder-recover?' + qs), {
                method: 'GET',
                credentials: 'include',
                cache: 'no-store',
            });
            if (!res.ok) return false;
            const data = await res.json();
            if (data && data.ok && data.session && data.session.session_id) {
                const s = data.session;
                const targetCtx = ctx || { logs: [] };
                targetCtx.sessionId = s.session_id;
                targetCtx.recoveredSessionId = s.session_id;
                STATE.recorders.set(cardEl, targetCtx);
                logRecorderState(cardEl, 'recovered', {
                    bytes: s.byte_count || 0,
                    message: 'Recovered interrupted recording from server sandbox (' + Math.round((s.byte_count || 0) / 1024) + ' KB)',
                });
                showRecoveryBanner(cardEl, {
                    byteCount: s.byte_count || 0,
                    serverHtmlUrl: apiUrl(s.download_html_url),
                    serverWebmUrl: apiUrl(s.download_webm_url),
                });
                announceText('Recovered a recording from your previous session. Download links are ready in the recorder bar.');
                return true;
            }
        } catch (e) {}
        return false;
    }

    function downloadStandalone(cardEl) {
        const ctx = cardEl ? STATE.recorders.get(cardEl) : null;
        if (!ctx || !ctx.standaloneHtmlBlob) return false;
        logRecorderState(cardEl, 'saving', { bytes: ctx.standaloneHtmlBlob.size, message: 'Triggering standalone offline HTML recording download: ' + ctx.standaloneFilename });
        triggerBlobDownload(ctx.standaloneHtmlBlob, ctx.standaloneFilename);
        logRecorderState(cardEl, 'saved', { bytes: ctx.standaloneHtmlBlob.size, message: 'Standalone offline HTML download complete' });
        markSessionDownloaded(cardEl, ctx);
        announceText('Standalone offline HTML recording downloaded: ' + ctx.standaloneFilename);
        return true;
    }

    function downloadWebm(cardEl) {
        const ctx = cardEl ? STATE.recorders.get(cardEl) : null;
        if (!ctx || !ctx.videoBlob) return false;
        logRecorderState(cardEl, 'saving', { bytes: ctx.videoBlob.size, message: 'Triggering WebM download: ' + ctx.webmFilename });
        triggerBlobDownload(ctx.videoBlob, ctx.webmFilename);
        logRecorderState(cardEl, 'saved', { bytes: ctx.videoBlob.size, message: 'WebM video download complete' });
        markSessionDownloaded(cardEl, ctx);
        return true;
    }

    function attachRecorderToolbar(cardEl, insertTarget) {
        if (!cardEl || cardEl.querySelector('[data-recorder-chrome="true"]')) return;
        installExitPersistenceHooks();
        const bar = document.createElement('div');
        bar.setAttribute('data-recorder-chrome', 'true');
        bar.setAttribute('role', 'region');
        bar.setAttribute('aria-label', 'Response Card Isolation and 1080p Recording Controls');
        bar.className = 'mt-3 pt-3 border-t border-slate-800 space-y-2.5';

        const connText = STATE.secureConnection ? (STATE.secureConnection.verified ? '🔒 ' + STATE.secureConnection.label : '⚠ ' + STATE.secureConnection.label) : '🔒 Checking Secure Connection...';
        const connClass = (STATE.secureConnection && !STATE.secureConnection.verified)
            ? 'text-[11px] font-mono px-2.5 py-1 rounded bg-rose-950/90 text-rose-300 border border-rose-700/70'
            : 'text-[11px] font-mono px-2.5 py-1 rounded bg-emerald-950/90 text-emerald-300 border border-emerald-700/70';

        bar.innerHTML = [
            '<div class="flex flex-wrap items-center justify-between gap-2">',
            '  <div class="flex flex-wrap items-center gap-2">',
            '    <span data-secure-conn-badge class="' + connClass + '">' + escapeHtml(connText) + '</span>',
            '    <span data-recorder-state-badge data-state="idle" role="status" class="text-[11px] font-mono px-2.5 py-1 rounded bg-slate-950 text-cyan-300 border border-slate-700">Recorder Idle</span>',
            '  </div>',
            '  <div class="flex flex-wrap items-center gap-2">',
            '    <button type="button" data-recorder-action="isolate" aria-pressed="false" class="text-xs font-semibold px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-teal-300 border border-teal-700/70 focus:outline-none focus:ring-2 focus:ring-teal-400">Isolate Card</button>',
            '    <button type="button" data-recorder-action="record" class="text-xs font-bold px-3 py-1.5 rounded bg-rose-700 hover:bg-rose-600 disabled:opacity-40 text-white focus:outline-none focus:ring-2 focus:ring-rose-400">Record 1080p (30fps)</button>',
            '    <button type="button" data-recorder-action="stop" disabled class="text-xs font-bold px-3 py-1.5 rounded bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-black focus:outline-none focus:ring-2 focus:ring-amber-300">Stop</button>',
            '    <button type="button" data-recorder-action="preview" disabled aria-expanded="false" class="text-xs font-bold px-3 py-1.5 rounded bg-cyan-700 hover:bg-cyan-600 disabled:opacity-40 text-white focus:outline-none focus:ring-2 focus:ring-cyan-300">Preview Recording</button>',
            '    <button type="button" data-recorder-action="download" disabled class="text-xs font-bold px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 text-white focus:outline-none focus:ring-2 focus:ring-emerald-300">Download Standalone (.html)</button>',
            '    <button type="button" data-recorder-action="download-webm" disabled class="text-xs font-semibold px-2.5 py-1.5 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200 border border-slate-600 focus:outline-none focus:ring-2 focus:ring-teal-400">.webm</button>',
            '  </div>',
            '</div>',
            '<div data-recorder-recovery-banner role="status" class="hidden flex flex-wrap items-center justify-between gap-2 bg-amber-950/60 border border-amber-600/80 rounded-lg px-3 py-2 text-xs text-amber-100">',
            '  <span data-recorder-recovery-text class="font-semibold"></span>',
            '  <div class="flex flex-wrap items-center gap-2">',
            '    <a data-recorder-action="recover-server-html" href="#" class="hidden text-xs font-bold px-2.5 py-1 rounded bg-emerald-700 hover:bg-emerald-600 text-white focus:outline-none focus:ring-2 focus:ring-emerald-300">Download Recovered (.html)</a>',
            '    <a data-recorder-action="recover-server-webm" href="#" class="hidden text-xs font-semibold px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-100 border border-slate-600 focus:outline-none focus:ring-2 focus:ring-teal-400">Download .webm</a>',
            '    <button type="button" data-recorder-action="discard-recovery" class="text-xs font-semibold px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-amber-200 border border-amber-700 focus:outline-none focus:ring-2 focus:ring-amber-400">Discard</button>',
            '  </div>',
            '</div>',
            '<div data-recorder-preview-wrap class="hidden bg-slate-950 border border-cyan-700/60 rounded-lg p-3 space-y-2">',
            '  <div class="flex flex-wrap items-center justify-between gap-2">',
            '    <span data-recorder-preview-meta class="text-xs font-mono text-cyan-300">In-Card Recording Preview (1920x1080 @ 30fps)</span>',
            '    <span class="text-[11px] font-mono text-slate-400">Preview locally before saving offline HTML</span>',
            '  </div>',
            '  <video data-recorder-preview-video controls playsinline preload="auto" tabindex="0" aria-label="In-card recorded video preview (1920x1080 at 30fps)" class="w-full max-h-[360px] rounded border border-slate-800 bg-black"></video>',
            '</div>',
            '<details class="text-xs text-slate-400">',
            '  <summary class="cursor-pointer font-mono hover:text-cyan-300 select-none">MediaRecorder State Log (recording / rendering / saving)</summary>',
            '  <ol data-recorder-log-list role="log" aria-live="polite" aria-label="MediaRecorder State Change Log" class="mt-2 bg-black/80 border border-slate-800 rounded p-2.5 font-mono text-[11px] text-slate-300 space-y-1 max-h-36 overflow-y-auto list-decimal list-inside"></ol>',
            '</details>',
        ].join('\n');

        bar.querySelector('[data-recorder-action="isolate"]').addEventListener('click', function () {
            if (cardEl.getAttribute('data-card-isolated') === 'true') {
                unisolateCard(false);
            } else {
                isolateCard(cardEl);
            }
        });
        bar.querySelector('[data-recorder-action="record"]').addEventListener('click', function () {
            startRecording(cardEl);
        });
        bar.querySelector('[data-recorder-action="stop"]').addEventListener('click', function () {
            stopRecording(cardEl, { autoDownload: false });
        });
        bar.querySelector('[data-recorder-action="preview"]').addEventListener('click', function () {
            togglePreview(cardEl);
        });
        bar.querySelector('[data-recorder-action="download"]').addEventListener('click', function () {
            downloadStandalone(cardEl);
        });
        bar.querySelector('[data-recorder-action="download-webm"]').addEventListener('click', function () {
            downloadWebm(cardEl);
        });
        bar.querySelector('[data-recorder-action="discard-recovery"]').addEventListener('click', function () {
            discardRecoveredSession(cardEl);
        });

        const host = insertTarget || cardEl.querySelector('.flip-front > div:last-child') || cardEl;
        host.appendChild(bar);
        if (!STATE.recorders.has(cardEl)) {
            STATE.recorders.set(cardEl, { logs: [] });
        }
        cardEl.setAttribute('data-recorder-state', 'idle');
        if (cardEl.querySelector('iframe[src*="preview=1"], iframe[src*="mode=preview"]')) {
            syncPreviewRecordingLock(cardEl, true);
        } else {
            recoverSessionForCard(cardEl);
        }
    }

    function syncPreviewRecordingLock(cardEl, isPreview) {
        if (!cardEl) return;
        cardEl.setAttribute('data-preview-mode', isPreview ? 'true' : 'false');
        const recBtn = cardEl.querySelector('[data-recorder-action="record"]');
        const badge = cardEl.querySelector('[data-recorder-state-badge]');
        if (isPreview) {
            if (recBtn) {
                recBtn.disabled = true;
                recBtn.textContent = 'Recording Off (Preview)';
            }
            if (badge) {
                badge.textContent = 'Preview Mode (No Recording)';
            }
        } else {
            const ctx = STATE.recorders.get(cardEl);
            const active = ctx && ctx.mediaRecorder && ctx.mediaRecorder.state === 'recording';
            if (recBtn && !active) {
                recBtn.disabled = false;
                recBtn.textContent = 'Record 1080p (30fps)';
            }
            if (badge && !active && badge.textContent === 'Preview Mode (No Recording)') {
                badge.textContent = 'Recorder Idle';
            }
        }
    }

    function attachToFeed(feedEl) {
        if (!feedEl) return;
        const attachExisting = function () {
            feedEl.querySelectorAll('article.message-card.agent-message').forEach(function (art) {
                attachRecorderToolbar(art);
            });
        };
        attachExisting();
        const obs = new MutationObserver(function () { attachExisting(); });
        obs.observe(feedEl, { childList: true });
    }

    window.addEventListener('message', function (ev) {
        if (!ev || !ev.data || typeof ev.data !== 'object') return;
        const allowedOrigins = [
            window.location.origin,
            'https://mikeytech.dev',
            'https://www.mikeytech.dev',
            'https://siraugga.mikeytech.dev',
        ];
        if (ev.origin && allowedOrigins.indexOf(ev.origin) === -1) return;

        if (ev.data.type === 'siraugga_course_snapshot') {
            STATE.latestCourseSnapshot = ev.data.snapshot || null;
            if (ev.data.snapshot && typeof ev.data.snapshot.previewMode === 'boolean') {
                document.querySelectorAll('article.message-card').forEach(function (art) {
                    const fr = art.querySelector('iframe');
                    if (fr && fr.contentWindow === ev.source) {
                        syncPreviewRecordingLock(art, ev.data.snapshot.previewMode);
                    }
                });
            }
        } else if (ev.data.type === 'siraugga_course_interaction_complete') {
            const target = STATE.isolatedCard || document.querySelector('article.message-card[data-backend-card="course"]') || document.querySelector('article.message-card.agent-message:last-of-type');
            const ctx = target ? STATE.recorders.get(target) : null;
            if (ctx && ctx.mediaRecorder && ctx.mediaRecorder.state === 'recording') {
                stopRecording(target, { autoDownload: true });
            }
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && STATE.isolatedCard) {
            const ctx = STATE.recorders.get(STATE.isolatedCard);
            if (!ctx || !ctx.mediaRecorder || ctx.mediaRecorder.state !== 'recording') {
                unisolateCard(false);
            }
        }
    });

    window.SirauggaCardRecorder = {
        verifySecureConnection: verifySecureConnection,
        isolateCard: isolateCard,
        unisolateCard: unisolateCard,
        startRecording: startRecording,
        stopRecording: stopRecording,
        togglePreview: togglePreview,
        downloadStandalone: downloadStandalone,
        downloadWebm: downloadWebm,
        attachRecorderToolbar: attachRecorderToolbar,
        attachToFeed: attachToFeed,
        recoverSessionForCard: recoverSessionForCard,
        discardRecoveredSession: discardRecoveredSession,
        flushActiveRecordingsForExit: flushActiveRecordingsForExit,
        getLogs: function () { return STATE.logs.slice(); },
        buildStandaloneOfflineHtml: buildStandaloneOfflineHtml,
    };

    verifySecureConnection();
})();
