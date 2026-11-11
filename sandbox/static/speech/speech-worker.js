// On-device speech-to-text for the chat mic button.
//
// Privacy: the audio arrives here as raw samples from the page, is transcribed
// in this worker with a Whisper model running in the user's own browser, and is
// then discarded. Nothing is uploaded. The library, its WebAssembly runtime and
// the model files are all served by Siraugga itself (scripts/fetch_speech_assets.py),
// so the browser never contacts Hugging Face, jsDelivr or any other third party.
import { env, pipeline } from '/static/speech/vendor/transformers.min.js';

const MODEL_ID = 'Xenova/whisper-tiny.en';

env.allowRemoteModels = false;               // never fall back to huggingface.co
env.allowLocalModels = true;
env.localModelPath = '/static/speech/models/';
env.useBrowserCache = true;                  // cache model after the first download
env.backends.onnx.wasm.wasmPaths = '/static/speech/vendor/'; // never fall back to jsDelivr
env.backends.onnx.wasm.numThreads = 1;       // multi-threading needs cross-origin isolation
env.backends.onnx.wasm.proxy = false;

// Measured on an i5-13420H laptop, 5 s of speech:
//   GPU (WebGPU) + full-precision model: ~2.4 s, 145 MB one-time download
//   CPU (WebAssembly) + quantized model: ~7.6 s,  39 MB one-time download
// (Mixed fp32/q8 on WebGPU produced garbage text, so the GPU path is all-fp32.)
async function hasWebGPU() {
    try {
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
                    return await pipeline('automatic-speech-recognition', MODEL_ID, {
                        device: 'webgpu', dtype: 'fp32', progress_callback: progress,
                    });
                } catch (err) {
                    console.warn('[dictation] WebGPU unavailable, using CPU:', err);
                }
            }
            return pipeline('automatic-speech-recognition', MODEL_ID, {
                device: 'wasm', dtype: 'q8', progress_callback: progress,
            });
        })().catch((err) => {
            transcriberPromise = null;               // allow a retry later
            throw err;
        });
    }
    return transcriberPromise;
}

self.onmessage = async (e) => {
    const msg = e.data || {};
    try {
        if (msg.type === 'load') {
            await getTranscriber();
            self.postMessage({ type: 'ready' });
        } else if (msg.type === 'transcribe') {
            const transcriber = await getTranscriber();
            self.postMessage({ type: 'ready' });
            const opts = msg.audio.length > 30 * 16000 ? { chunk_length_s: 30, stride_length_s: 5 } : {};
            const out = await transcriber(msg.audio, opts);
            self.postMessage({ type: 'result', id: msg.id, text: (out && out.text ? out.text : '').trim() });
        }
    } catch (err) {
        self.postMessage({ type: 'error', id: msg.id, message: String((err && err.message) || err) });
    }
};
