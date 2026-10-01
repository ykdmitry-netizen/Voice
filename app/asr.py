"""Движки распознавания речи: Parakeet TDT v3, GigaAM (русский), Whisper.

Все работают полностью локально, на CPU. Модели — ONNX (sherpa-onnx) или
CTranslate2 (faster-whisper) и лежат в каталоге models.
"""

from __future__ import annotations

import os
import threading

import numpy as np

SAMPLE_RATE = 16000


class EngineError(RuntimeError):
    pass


class Engine:
    name = "engine"
    label = "движок"
    dir_name = ""          # имя каталога с моделью внутри models/
    files: dict[str, str] = {}
    needs_hf_download = False

    def __init__(self, models_dir: str) -> None:
        self.models_dir = models_dir
        self._lock = threading.Lock()
        self._model = None
        self.load_seconds = 0.0

    # --- доступность -----------------------------------------------------
    @property
    def dir(self) -> str:
        return os.path.join(self.models_dir, self.dir_name or self.name)

    def missing_files(self) -> list[str]:
        return [f for f in self.files if not os.path.exists(os.path.join(self.dir, f))]

    def is_ready(self) -> bool:
        return not self.missing_files()

    # --- API -------------------------------------------------------------
    def load(self) -> None:
        raise NotImplementedError

    def transcribe(self, samples: np.ndarray, language: str = "ru") -> str:
        raise NotImplementedError

    def close(self) -> None:
        self._model = None


class ParakeetEngine(Engine):
    """NVIDIA Parakeet TDT 0.6B v3 (int8, ONNX) — мультиязычная, 25 языков ЕС,
    включая русский и английский. Язык выбирать не нужно, модель сама решает."""

    name = "parakeet"
    label = "Parakeet TDT 0.6B v3 (быстро, мультиязычно)"
    dir_name = "parakeet-tdt-0.6b-v3-int8"
    files = {
        "encoder.int8.onnx": "encoder.int8.onnx",
        "decoder.int8.onnx": "decoder.int8.onnx",
        "joiner.int8.onnx": "joiner.int8.onnx",
        "tokens.txt": "tokens.txt",
    }

    def load(self) -> None:
        if self._model is not None:
            return
        import time

        import sherpa_onnx

        missing = self.missing_files()
        if missing:
            raise EngineError(
                "нет файлов модели: " + ", ".join(missing) + f"\nожидались в {self.dir}"
            )
        start = time.perf_counter()
        self._model = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=os.path.join(self.dir, "encoder.int8.onnx"),
            decoder=os.path.join(self.dir, "decoder.int8.onnx"),
            joiner=os.path.join(self.dir, "joiner.int8.onnx"),
            tokens=os.path.join(self.dir, "tokens.txt"),
            num_threads=os.cpu_count() or 4,
            sample_rate=SAMPLE_RATE,
            feature_dim=80,
            decoding_method="greedy_search",
            model_type="nemo_transducer",
            provider="cpu",
        )
        self.load_seconds = time.perf_counter() - start

    def transcribe(self, samples: np.ndarray, language: str = "ru") -> str:
        if self._model is None:
            self.load()
        with self._lock:
            stream = self._model.create_stream()
            stream.accept_waveform(SAMPLE_RATE, samples)
            self._model.decode_stream(stream)
            return stream.result.text.strip()


class GigaamEngine(Engine):
    """GigaAM v2 CTC — русская модель, точная, но без пунктуации."""

    name = "gigaam"
    label = "GigaAM v2 (только русский, без пунктуации)"
    dir_name = "gigaam-ctc-ru-int8"
    files = {"model.int8.onnx": "model.int8.onnx", "tokens.txt": "tokens.txt"}

    def load(self) -> None:
        if self._model is not None:
            return
        import time

        import sherpa_onnx

        missing = self.missing_files()
        if missing:
            raise EngineError("нет файлов модели: " + ", ".join(missing))
        start = time.perf_counter()
        self._model = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
            model=os.path.join(self.dir, "model.int8.onnx"),
            tokens=os.path.join(self.dir, "tokens.txt"),
            num_threads=os.cpu_count() or 4,
            sample_rate=SAMPLE_RATE,
            feature_dim=80,
            provider="cpu",
        )
        self.load_seconds = time.perf_counter() - start

    def transcribe(self, samples: np.ndarray, language: str = "ru") -> str:
        if self._model is None:
            self.load()
        with self._lock:
            stream = self._model.create_stream()
            stream.accept_waveform(SAMPLE_RATE, samples)
            self._model.decode_stream(stream)
            return stream.result.text.strip()


class WhisperEngine(Engine):
    """Whisper через faster-whisper/CTranslate2. На этом CPU пригодны только
    base и small; large-v3-turbo даёт ~0.5x реального времени."""

    name = "whisper"
    label = "Whisper (faster-whisper, CPU int8)"

    def __init__(self, models_dir: str, model_size: str = "small") -> None:
        super().__init__(models_dir)
        self.model_size = model_size
        self.cache_dir = os.path.join(models_dir, "..", "cache", "fw")
        self.cache_dir = os.path.abspath(self.cache_dir)

    def missing_files(self) -> list[str]:
        # модель качает сама библиотека с Hugging Face, проверяем только импорт
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return ["faster-whisper (не установлен)"]
        return []

    def load(self) -> None:
        if self._model is not None:
            return
        import time

        from faster_whisper import WhisperModel

        start = time.perf_counter()
        self._model = WhisperModel(
            self.model_size,
            device="cpu",
            compute_type="int8",
            cpu_threads=os.cpu_count() or 4,
            download_root=self.cache_dir,
        )
        self.load_seconds = time.perf_counter() - start

    def transcribe(self, samples: np.ndarray, language: str = "ru") -> str:
        if self._model is None:
            self.load()
        lang = None if language in ("", "auto") else language
        with self._lock:
            segments, _info = self._model.transcribe(
                samples, language=lang, beam_size=1, vad_filter=False
            )
            return "".join(s.text for s in segments).strip()


BUILDERS = {
    "parakeet": ParakeetEngine,
    "gigaam": GigaamEngine,
    "whisper": WhisperEngine,
}


def build_engine(name: str, models_dir: str, whisper_model: str = "small") -> Engine:
    if name == "whisper":
        return WhisperEngine(models_dir, whisper_model)
    try:
        return BUILDERS[name](models_dir)
    except KeyError as exc:
        raise EngineError(f"неизвестный движок: {name}") from exc


def available_engines() -> list[tuple[str, str]]:
    return [(name, cls.label) for name, cls in BUILDERS.items()]
