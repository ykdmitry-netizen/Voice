"""Audio loading helper shared by the benchmark scripts.

faster_whisper.audio.decode_audio is broken with the PyAV version we installed
(`av.open(..., metadata_errors=...)` no longer exists), so we decode ourselves:
first through PyAV's AudioResampler, and if that API also differs, through the
stdlib `wave` module with a linear resampler.
"""

from __future__ import annotations

import wave

import numpy as np


def _load_pyav(path: str, sr: int) -> np.ndarray:
    import av

    chunks = []
    with av.open(path) as container:
        stream = container.streams.audio[0]
        resampler = av.audio.resampler.AudioResampler(
            format="fltp", layout="mono", rate=sr
        )
        for frame in container.decode(stream):
            out = resampler.resample(frame)
            for item in out if isinstance(out, list) else [out]:
                if item is not None:
                    chunks.append(item.to_ndarray().reshape(-1))
        tail = resampler.resample(None)
        for item in tail if isinstance(tail, list) else [tail]:
            if item is not None:
                chunks.append(item.to_ndarray().reshape(-1))
    if not chunks:
        raise RuntimeError("no audio decoded")
    return np.concatenate(chunks).astype(np.float32)


def _load_wave(path: str, sr: int) -> np.ndarray:
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2:
            raise RuntimeError(f"unsupported sample width {w.getsampwidth()}")
        n_ch = w.getnchannels()
        rate = w.getframerate()
        raw = w.readframes(w.getnframes())
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if n_ch > 1:
        data = data.reshape(-1, n_ch).mean(axis=1)
    if rate != sr:
        n_out = int(round(len(data) * sr / rate))
        idx = np.linspace(0, len(data) - 1, n_out)
        data = np.interp(idx, np.arange(len(data)), data).astype(np.float32)
    return data


def load(path: str, sr: int = 16000) -> np.ndarray:
    try:
        return _load_pyav(path, sr)
    except Exception:  # noqa: BLE001 - fall back to the stdlib decoder
        return _load_wave(path, sr)
