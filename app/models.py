"""Загрузка моделей распознавания с Hugging Face.

Скачиваем сами, без huggingface_hub: нужен прогресс в интерфейсе и предсказуемое
поведение (файлы кладутся прямо в models/<движок>).
"""

from __future__ import annotations

import os
import socket
import urllib.error
import urllib.request

SOURCES = {
    "parakeet": {
        "label": "Parakeet TDT 0.6B v3 int8 (~670 МБ)",
        "dir": "parakeet-tdt-0.6b-v3-int8",
        "base": "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/resolve/main/",
        "files": ["encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"],
        "sizes": {
            "encoder.int8.onnx": 652184281,
            "decoder.int8.onnx": 11845275,
            "joiner.int8.onnx": 6355277,
            "tokens.txt": 93939,
        },
    },
    "gigaam": {
        "label": "GigaAM v2 CTC русский int8 (~275 МБ)",
        "dir": "gigaam-ctc-ru-int8",
        "base": "https://huggingface.co/csukuangfj/sherpa-onnx-nemo-ctc-giga-am-russian-2024-10-24/resolve/main/",
        "files": ["model.int8.onnx", "tokens.txt"],
        "sizes": {"model.int8.onnx": 274808098, "tokens.txt": 196},
    },
}


class DownloadError(RuntimeError):
    pass


def engine_dir(models_dir: str, engine: str) -> str:
    spec = SOURCES.get(engine)
    return os.path.join(models_dir, (spec or {}).get("dir", engine))


def total_size(engine: str) -> int:
    return sum(SOURCES[engine]["sizes"].values())


def missing(models_dir: str, engine: str) -> list[str]:
    spec = SOURCES.get(engine)
    if spec is None:
        return []
    out = []
    for name in spec["files"]:
        path = os.path.join(engine_dir(models_dir, engine), name)
        expected = spec["sizes"].get(name, 0)
        if not os.path.exists(path) or os.path.getsize(path) < expected:
            out.append(name)
    return out


def download(models_dir: str, engine: str, progress=None, cancelled=None) -> None:
    """progress(файл, скачано_байт, всего_байт); cancelled() -> bool."""
    spec = SOURCES.get(engine)
    if spec is None:
        raise DownloadError(f"для движка {engine} нет источника загрузки")

    target = engine_dir(models_dir, engine)
    os.makedirs(target, exist_ok=True)
    socket.setdefaulttimeout(30)

    for name in spec["files"]:
        dest = os.path.join(target, name)
        expected = spec["sizes"].get(name, 0)
        if os.path.exists(dest) and os.path.getsize(dest) >= expected > 0:
            continue

        url = spec["base"] + name + "?download=true"
        tmp = dest + ".part"
        request = urllib.request.Request(url, headers={"User-Agent": "PantelaVoice/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response, open(tmp, "wb") as fh:
                total = int(response.headers.get("Content-Length") or expected or 0)
                done = 0
                while True:
                    if cancelled is not None and cancelled():
                        raise DownloadError("загрузка отменена")
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(name, done, total)
            os.replace(tmp, dest)
        except (urllib.error.URLError, OSError, socket.timeout) as exc:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            raise DownloadError(f"не удалось скачать {name}: {exc}") from exc
    if progress:
        progress("", 0, 0)
