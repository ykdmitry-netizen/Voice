"""Микрофон: запись в 16 кГц моно и индикатор уровня.

Используется sounddevice (PortAudio). Recorder можно запускать и останавливать
много раз подряд — это делает push-to-talk дешёвым.
"""

from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd

TARGET_RATE = 16000


class Recorder:
    def __init__(self) -> None:
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._level = 0.0
        self._peak = 0.0
        self.device_name = ""
        self.error: str | None = None

    # --- служебное -------------------------------------------------------
    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    @property
    def level(self) -> float:
        """Текущий уровень 0..1 (сглаженный) — для индикатора."""
        return self._level

    @property
    def peak(self) -> float:
        return self._peak

    @staticmethod
    def list_input_devices() -> list[tuple[int, str, int]]:
        out: list[tuple[int, str, int]] = []
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0:
                out.append((idx, dev["name"], int(dev.get("default_samplerate") or 0)))
        return out

    def _resolve_device(self, name: str) -> int | None:
        if not name:
            return None
        for idx, dev_name, _ in self.list_input_devices():
            if dev_name == name:
                return idx
        return None

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            self.error = str(status)
        block = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
        with self._lock:
            self._chunks.append(block)
            peak = float(np.max(np.abs(block))) if block.size else 0.0
            self._peak = max(self._peak, peak)
            # сглаживание для плавного индикатора
            self._level = max(peak, self._level * 0.72)

    # --- запись ----------------------------------------------------------
    def start(self, device_name: str = "", sample_rate: int = TARGET_RATE) -> None:
        if self._stream is not None:
            return
        with self._lock:
            self._chunks = []
        self._level = 0.0
        self._peak = 0.0
        self.error = None
        self.device_name = device_name or "по умолчанию"
        device = self._resolve_device(device_name)
        stream = sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            blocksize=1024,
            device=device,
            callback=self._callback,
        )
        stream.start()
        self._stream = stream

    def stop(self) -> np.ndarray:
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:  # noqa: BLE001
                pass
        with self._lock:
            chunks = self._chunks
            self._chunks = []
        self._level = 0.0
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks).astype(np.float32)

    def cancel(self) -> None:
        self.stop()


def trim_silence(samples: np.ndarray, threshold: float = 0.012,
                 keep_ms: int = 120) -> np.ndarray:
    """Обрезает тишину по краям, чтобы не гнать в модель лишние секунды."""
    if samples.size == 0:
        return samples
    loud = np.abs(samples) > threshold
    if not loud.any():
        return samples
    keep = int(TARGET_RATE * keep_ms / 1000)
    first = max(0, int(np.argmax(loud)) - keep)
    last = min(len(samples), len(samples) - int(np.argmax(loud[::-1])) + keep)
    return samples[first:last]
