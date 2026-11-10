"""Download the on-device voice dictation files into sandbox/static/speech/.

Siraugga serves these itself, so a user's browser never contacts Hugging Face,
jsDelivr or any other third party when they use the microphone button. The
audio itself never leaves the user's device at all (see speech-worker.js).

Run once per machine/deployment (the files are git-ignored, ~210 MB):

    python scripts/fetch_speech_assets.py
"""
import io
import os
import sys
import tarfile
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SPEECH_DIR = os.path.join(ROOT, "sandbox", "static", "speech")
VENDOR_DIR = os.path.join(SPEECH_DIR, "vendor")
MODEL_ID = "Xenova/whisper-tiny.en"
MODEL_DIR = os.path.join(SPEECH_DIR, "models", *MODEL_ID.split("/"))

TRANSFORMERS_VERSION = "3.7.5"
TRANSFORMERS_TGZ = (
    f"https://registry.npmjs.org/@huggingface/transformers/-/transformers-{TRANSFORMERS_VERSION}.tgz"
)
VENDOR_FILES = {
    # path inside the npm tarball -> local file name
    "package/dist/transformers.min.js": "transformers.min.js",
    "package/dist/ort-wasm-simd-threaded.jsep.mjs": "ort-wasm-simd-threaded.jsep.mjs",
    "package/dist/ort-wasm-simd-threaded.jsep.wasm": "ort-wasm-simd-threaded.jsep.wasm",
    "package/LICENSE": "LICENSE-transformers.js.txt",
}
ORT_LICENSE_URL = "https://raw.githubusercontent.com/microsoft/onnxruntime/main/LICENSE"
WHISPER_LICENSE_URL = "https://raw.githubusercontent.com/openai/whisper/main/LICENSE"

MODEL_FILES = [
    "config.json",
    "generation_config.json",
    "preprocessor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "onnx/encoder_model.onnx",                    # GPU (WebGPU) path
    "onnx/decoder_model_merged.onnx",
    "onnx/encoder_model_quantized.onnx",          # CPU (WebAssembly) path
    "onnx/decoder_model_merged_quantized.onnx",
]


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "siraugga-speech-fetch"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    print(f"  {os.path.relpath(path, ROOT)}  ({len(data) / 1e6:.1f} MB)")


def main():
    print(f"Transformers.js {TRANSFORMERS_VERSION} ...")
    with tarfile.open(fileobj=io.BytesIO(_get(TRANSFORMERS_TGZ)), mode="r:gz") as tar:
        for member, name in VENDOR_FILES.items():
            _write(os.path.join(VENDOR_DIR, name), tar.extractfile(member).read())
    _write(os.path.join(VENDOR_DIR, "LICENSE-onnxruntime.txt"), _get(ORT_LICENSE_URL))
    _write(os.path.join(VENDOR_DIR, "LICENSE-whisper.txt"), _get(WHISPER_LICENSE_URL))

    print(f"Model {MODEL_ID} ...")
    for rel in MODEL_FILES:
        url = f"https://huggingface.co/{MODEL_ID}/resolve/main/{rel}"
        _write(os.path.join(MODEL_DIR, *rel.split("/")), _get(url))
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"Failed: {e}", file=sys.stderr)
        sys.exit(1)
