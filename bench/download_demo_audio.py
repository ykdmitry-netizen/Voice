"""Download real human speech samples for the ASR benchmark (stdlib only)."""

import os
import urllib.request
import wave

# корень проекта — по расположению файла, чтобы репозиторий работал из любого места
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO = os.path.join(ROOT, "audio")
os.makedirs(AUDIO, exist_ok=True)

SOURCES = [
    (
        "ru_real.wav",
        "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-ctc-giga-am-russian-2024-10-24/resolve/main/test_wavs/example.wav",
    ),
    (
        "ru_long_real.wav",
        "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-ctc-giga-am-russian-2024-10-24/resolve/main/test_wavs/long_example.wav",
    ),
    (
        "en_real.wav",
        "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/resolve/main/test_wavs/en.wav",
    ),
]

for name, url in SOURCES:
    dest = os.path.join(AUDIO, name)
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        print(f"{name}: already present")
    else:
        req = urllib.request.Request(url, headers={"User-Agent": "bench/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as fh:
            fh.write(resp.read())
        print(f"{name}: downloaded {os.path.getsize(dest)} bytes")

    try:
        with wave.open(dest, "rb") as w:
            dur = w.getnframes() / float(w.getframerate())
            print(
                f"   -> {w.getnchannels()}ch {w.getframerate()} Hz "
                f"{w.getsampwidth() * 8}-bit  {dur:.2f} s"
            )
    except Exception as exc:  # noqa: BLE001
        print(f"   -> not a plain PCM wav ({exc}); will be decoded by PyAV")
