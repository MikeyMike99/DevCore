// On-device speech-to-text for the chat mic button.
//
// Privacy: the audio arrives here as raw samples from the page, is transcribed
// in this worker with a Whisper model running in the user's own browser, and is
// then discarded. Nothing is uploaded. The library, its WebAssembly runtime and
// the model files are all served by Siraugga itself (scripts/fetch_speech_assets.py),
// so the browser never contacts Hugging Face, jsDelivr or any other third party.
// The ?v=2 is on purpose: while the engine files were missing from mikeytech.dev, browsers cached the 404 for this
// exact address (static files are cached for an hour), so the worker could not start even after the files were fixed.
import { env, pipeline, AutoProcessor, AutoModel } from '/static/speech/vendor/transformers.min.js?v=2';

const MODEL_ID = 'Xenova/whisper-tiny.en';
const SV_MODEL_ID = 'Xenova/wavlm-base-plus-sv';   // voice matching (voice.js)

var _isStaticPages = (self.location && (self.location.hostname === 'mikeytech.dev' || self.location.hostname === 'www.mikeytech.dev'));
env.allowRemoteModels = false;               // never fall back to huggingface.co
env.allowLocalModels = true;
env.localModelPath = _isStaticPages ? 'https://siraugga.mikeytech.dev/static/speech/models/' : '/static/speech/models/';
env.useBrowserCache = true;                  // cache model after the first download
env.backends.onnx.wasm.wasmPaths = '/static/speech/vendor/'; // never fall back to jsDelivr
env.backends.onnx.wasm.numThreads = 1;       // multi-threading needs cross-origin isolation
env.backends.onnx.wasm.proxy = false;

// Measured on an i5-13420H laptop, 5 s of speech:
//   GPU (WebGPU) + full-precision model: ~2.4 s, 145 MB one-time download
//   CPU (WebAssembly) + quantized model: ~7.6 s,  39 MB one-time download
// (Mixed fp32/q8 on WebGPU produced garbage text, so the GPU path is all-fp32.)
// voice.js starts the worker with ?cpu=1 after a crash on the GPU path, so a machine whose graphics driver
// kills the worker keeps working on the slower, safer CPU path.
var FORCE_CPU = false;
try { FORCE_CPU = new URL(self.location.href).searchParams.get('cpu') === '1'; } catch (_) {}
function stage(name) { try { self.postMessage({ type: 'stage', stage: name }); } catch (_) {} }

async function hasWebGPU() {
    try {
        if (FORCE_CPU) return false;
        // Phones: the 145 MB GPU model often runs out of memory or gives bad text, use the small CPU one.
        if (/Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || '')) return false;
        return !!(navigator.gpu && await navigator.gpu.requestAdapter());
    } catch (_) {
        return false;
    }
}

function progress(p) {
    if (p.status === 'progress' && p.total) {
        self.postMessage({ type: 'progress', file: p.file, loaded: p.loaded, total: p.total });
    }
}

let transcriberPromise = null;

function getTranscriber() {
    if (!transcriberPromise) {
        transcriberPromise = (async () => {
            if (await hasWebGPU()) {
                try {
                    stage('speech model: loading on the graphics card');
                    const gpu = await pipeline('automatic-speech-recognition', MODEL_ID, {
                        device: 'webgpu', dtype: 'fp32', progress_callback: progress,
                    });
                    stage('speech model: ready (graphics card)');
                    return gpu;
                } catch (err) {
                    console.warn('[dictation] WebGPU unavailable, using CPU:', err);
                }
            }
            stage('speech model: loading on the processor');
            const cpu = await pipeline('automatic-speech-recognition', MODEL_ID, {
                device: 'wasm', dtype: 'q8', progress_callback: progress,
            });
            stage('speech model: ready (processor)');
            return cpu;
        })().catch((err) => {
            transcriberPromise = null;               // allow a retry later
            throw err;
        });
    }
    return transcriberPromise;
}

// Voice matching: turns a clip into a 512-number "voice print". voice.js compares prints.
// CPU only on purpose; the GPU path gave unreliable numbers for this model.
let speakerPromise = null;
function getSpeakerModel() {
    if (!speakerPromise) {
        speakerPromise = (async () => {
            const processor = await AutoProcessor.from_pretrained(SV_MODEL_ID);
            const model = await AutoModel.from_pretrained(SV_MODEL_ID, {
                device: 'wasm', dtype: 'q8', progress_callback: progress,
            });
            return { processor, model };
        })().catch((err) => {
            speakerPromise = null;
            throw err;
        });
    }
    return speakerPromise;
}

async function embedVoice(audio) {
    const { processor, model } = await getSpeakerModel();
    const MAX = 8 * 16000;                           // 8 s from the middle is plenty and keeps it quick
    if (audio.length > MAX) {
        const start = Math.floor((audio.length - MAX) / 2);
        audio = audio.slice(start, start + MAX);
    }
    const inputs = await processor(audio);
    const out = await model(inputs);
    const vec = Array.from(out.embeddings.data);
    let norm = 0;
    for (const v of vec) norm += v * v;
    norm = Math.sqrt(norm) || 1;
    return vec.map((v) => v / norm);
}

self.onmessage = async (e) => {
    const msg = e.data || {};
    try {
        if (msg.type === 'embed') {
            const embedding = await embedVoice(msg.audio);
            self.postMessage({ type: 'embedding', id: msg.id, embedding });
        } else if (msg.type === 'load') {
            await getTranscriber();
            self.postMessage({ type: 'ready' });
        } else if (msg.type === 'transcribe') {
            const transcriber = await getTranscriber();
            self.postMessage({ type: 'ready' });
            const opts = msg.audio.length > 30 * 16000 ? { chunk_length_s: 30, stride_length_s: 5 } : {};
            stage('transcribing');
            const out = await transcriber(msg.audio, opts);
            stage('transcribed');
            self.postMessage({ type: 'result', id: msg.id, text: (out && out.text ? out.text : '').trim() });
        }
    } catch (err) {
        self.postMessage({ type: 'error', id: msg.id, message: String((err && err.message) || err) });
    }
};
