"""Benchmark sherpa-onnx models (Parakeet TDT v3 int8, GigaAM Russian CTC int8) on CPU.

Usage: python bench_sherpa.py [parakeet] [gigaam]
Env:   BENCH_THREADS (default 4)
"""

import glob
import json
import os
import sys
import time

# корень проекта — по расположению файла, чтобы репозиторий работал из любого места
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO = os.path.join(ROOT, "audio")
MODELS = os.path.join(ROOT, "models")
OUT = os.path.join(ROOT, "bench")
THREADS = int(os.environ.get("BENCH_THREADS", "4"))

os.environ.setdefault("HF_HOME", os.path.join(ROOT, "cache", "hf"))

import numpy as np  # noqa: E402
from audio_io import load  # noqa: E402
import sherpa_onnx  # noqa: E402


def make_parakeet(num_threads: int):
    d = os.path.join(MODELS, "parakeet-tdt-0.6b-v3-int8")
    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=os.path.join(d, "encoder.int8.onnx"),
        decoder=os.path.join(d, "decoder.int8.onnx"),
        joiner=os.path.join(d, "joiner.int8.onnx"),
        tokens=os.path.join(d, "tokens.txt"),
        num_threads=num_threads,
        sample_rate=16000,
        feature_dim=80,
        decoding_method="greedy_search",
        model_type="nemo_transducer",
        provider="cpu",
    )


def make_gigaam(num_threads: int):
    d = os.path.join(MODELS, "gigaam-ctc-ru-int8")
    return sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
        model=os.path.join(d, "model.int8.onnx"),
        tokens=os.path.join(d, "tokens.txt"),
        num_threads=num_threads,
        sample_rate=16000,
        feature_dim=80,
        provider="cpu",
    )


BUILDERS = {"parakeet": make_parakeet, "gigaam": make_gigaam}


def lang_of(path: str) -> str:
    name = os.path.basename(path).lower()
    if name.startswith("ru"):
        return "ru"
    if name.startswith("de"):
        return "de"
    return "en"


def main() -> None:
    wanted = sys.argv[1:] or list(BUILDERS)
    files = sorted(glob.glob(os.path.join(AUDIO, "*.wav")))
    if not files:
        raise SystemExit(f"no wav files in {AUDIO}")

    decoded = {}
    for f in files:
        samples = load(f, 16000)
        decoded[f] = (samples, len(samples) / 16000.0)
    print("Audio files:")
    for f, (_, dur) in decoded.items():
        print(f"  {os.path.basename(f):18s} {dur:6.2f} s")
    print(f"\nthreads={THREADS} provider=cpu\n")

    rows = []
    for name in wanted:
        print(f"=== {name} ===", flush=True)
        try:
            t0 = time.perf_counter()
            recognizer = BUILDERS[name](THREADS)
            load_s = time.perf_counter() - t0
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED to load: {type(exc).__name__}: {exc}", flush=True)
            rows.append({"model": name, "error": f"{type(exc).__name__}: {exc}"})
            continue
        print(f"  (load {load_s:.1f}s)", flush=True)

        # warm-up on 3 s of the first file
        warm = decoded[files[0]][0][: 16000 * 3]
        s = recognizer.create_stream()
        s.accept_waveform(16000, warm)
        recognizer.decode_stream(s)

        for f in files:
            samples, dur = decoded[f]
            t0 = time.perf_counter()
            stream = recognizer.create_stream()
            stream.accept_waveform(16000, samples)
            recognizer.decode_stream(stream)
            text = stream.result.text.strip()
            dt = time.perf_counter() - t0
            rtf = dur / dt if dt > 0 else 0.0
            print(
                f"  {os.path.basename(f):18s} {dur:6.2f}s audio -> {dt:6.2f}s  "
                f"RTF {rtf:5.2f}x  | {text[:70]}",
                flush=True,
            )
            rows.append(
                {
                    "model": name,
                    "file": os.path.basename(f),
                    "lang": lang_of(f),
                    "audio_s": round(dur, 2),
                    "time_s": round(dt, 2),
                    "rtf": round(rtf, 2),
                    "text": text,
                }
            )
        del recognizer
        print()

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, os.environ.get("BENCH_OUT", "sherpa_results.json"))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)
    print("saved:", path)


if __name__ == "__main__":
    main()
