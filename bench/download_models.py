"""Download sherpa-onnx model files (Parakeet TDT v3 int8, GigaAM Russian CTC int8)."""

import os
import sys
import time
import urllib.request

# корень проекта — по расположению файла, чтобы репозиторий работал из любого места
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, "models")

PARAKEET = (
    "parakeet-tdt-0.6b-v3-int8",
    "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/resolve/main/",
    ["encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"],
)

GIGAAM = (
    "gigaam-ctc-ru-int8",
    "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-ctc-giga-am-russian-2024-10-24/resolve/main/",
    ["model.int8.onnx", "tokens.txt"],
)

ALL = {"parakeet": PARAKEET, "gigaam": GIGAAM}


def fetch(url: str, dest: str) -> None:
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "bench/1.0"})
    start = time.time()
    with urllib.request.urlopen(req, timeout=600) as resp, open(tmp, "wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if total:
                pct = 100.0 * done / total
                print(
                    f"\r  {os.path.basename(dest)}: {done / 1e6:7.1f}/{total / 1e6:.1f} MB "
                    f"({pct:5.1f}%)",
                    end="",
                    flush=True,
                )
    os.replace(tmp, dest)
    dt = time.time() - start
    print(f"\r  {os.path.basename(dest)}: {os.path.getsize(dest) / 1e6:.1f} MB in {dt:.0f}s")


def main() -> None:
    which = sys.argv[1:] or list(ALL)
    for key in which:
        name, base, files = ALL[key]
        target = os.path.join(MODELS, name)
        os.makedirs(target, exist_ok=True)
        print(f"=== {name} ===")
        for f in files:
            dest = os.path.join(target, f)
            if os.path.exists(dest) and os.path.getsize(dest) > 1000:
                print(f"  {f}: present ({os.path.getsize(dest) / 1e6:.1f} MB)")
                continue
            fetch(base + f + "?download=true", dest)


if __name__ == "__main__":
    main()
