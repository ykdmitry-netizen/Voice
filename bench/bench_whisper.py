"""Benchmark faster-whisper (CTranslate2, CPU int8) on local audio files.

Usage:  python bench_whisper.py tiny base small
Env:    BENCH_THREADS (default 4), BENCH_BEAM (default 1), BENCH_LANG_MAP
"""
import glob
import json
import os
import sys
import time

# корень проекта — по расположению файла, чтобы репозиторий работал из любого места
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO = os.path.join(ROOT, "audio")
OUT = os.path.join(ROOT, "bench")
CACHE = os.path.join(ROOT, "cache", "fw")
THREADS = int(os.environ.get("BENCH_THREADS", "4"))
BEAM = int(os.environ.get("BENCH_BEAM", "1"))

os.environ.setdefault("HF_HOME", os.path.join(ROOT, "cache", "hf"))

import numpy as np  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402
from audio_io import load  # noqa: E402


def lang_of(path: str) -> str:
    name = os.path.basename(path).lower()
    for tag in ("ru", "de", "en", "jfk"):
        if name.startswith(tag):
            return "de" if tag == "de" else ("en" if tag in ("en", "jfk") else "ru")
    return "ru"


def main() -> None:
    models = sys.argv[1:] or ["tiny", "base", "small"]
    files = sorted(glob.glob(os.path.join(AUDIO, "*.wav")))
    if os.environ.get("BENCH_SKIP_LONG"):
        files = [f for f in files if os.path.getsize(f) < 2000000]
    if not files:
        raise SystemExit(f"no wav files in {AUDIO}")

    # decode once, reuse for every model
    decoded = {}
    for f in files:
        t0 = time.perf_counter()
        samples = load(f, 16000)
        dt = time.perf_counter() - t0
        decoded[f] = (samples, len(samples) / 16000.0, dt)
    print("Audio files:")
    for f, (_, dur, dt) in decoded.items():
        print(f"  {os.path.basename(f):16s} {dur:6.2f} s   (decode {dt:.2f} s)")
    print(f"\nthreads={THREADS} beam_size={BEAM} compute=int8 device=cpu\n")

    rows = []
    for name in models:
        print(f"=== {name} ===", flush=True)
        try:
            t0 = time.perf_counter()
            model = WhisperModel(
                name,
                device="cpu",
                compute_type="int8",
                cpu_threads=THREADS,
                download_root=CACHE,
            )
            load_s = time.perf_counter() - t0
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED to load: {exc}", flush=True)
            rows.append({"model": name, "error": str(exc)})
            continue

        # warm up on the first 3 s of the first file
        samples, _, _ = decoded[files[0]]
        warm = samples[: 16000 * 3]
        try:
            segs, _ = model.transcribe(warm, language="ru", beam_size=BEAM)
            list(segs)
        except Exception as exc:  # noqa: BLE001
            print(f"  warmup failed: {exc}", flush=True)

        for f in files:
            samples, dur, _ = decoded[f]
            lang = lang_of(f)
            t0 = time.perf_counter()
            segs, info = model.transcribe(samples, language=lang, beam_size=BEAM)
            text = "".join(s.text for s in segs).strip()
            dt = time.perf_counter() - t0
            rtf = dur / dt if dt > 0 else 0.0
            print(
                f"  {os.path.basename(f):16s} {dur:6.2f}s audio -> {dt:6.2f}s  "
                f"RTF {rtf:5.2f}x  lang={lang}  | {text[:70]}",
                flush=True,
            )
            rows.append(
                {
                    "model": name,
                    "file": os.path.basename(f),
                    "lang": lang,
                    "audio_s": round(dur, 2),
                    "time_s": round(dt, 2),
                    "rtf": round(rtf, 2),
                    "text": text,
                }
            )
        del model
        print(f"  (load {load_s:.1f}s)\n", flush=True)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, os.environ.get("BENCH_OUT", "whisper_results.json"))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)
    print("saved:", path)


if __name__ == "__main__":
    main()
