"""Настройки приложения и пути.

По умолчанию всё личное хозяйство лежит в %APPDATA%\\PantelaVoice.
Переменная окружения PANTELA_HOME переопределяет каталог (нужна для тестов
внутри песочницы).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field

APP_NAME = "PantelaVoice"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MODELS_DIR = os.path.join(PROJECT_ROOT, "models")


def home_dir() -> str:
    """Каталог для настроек и журнала.

    Пробуем по очереди: PANTELA_HOME, %APPDATA%\\PantelaVoice, папку рядом с
    программой, системный временный каталог. Первый доступный и выигрывает —
    приложение не должно падать из-за прав на запись.
    """
    candidates: list[str] = []
    env = os.environ.get("PANTELA_HOME")
    if env:
        candidates.append(env)
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    candidates.append(os.path.join(base, APP_NAME))
    candidates.append(os.path.join(PROJECT_ROOT, "data"))
    candidates.append(os.path.join(tempfile.gettempdir(), APP_NAME))

    for path in candidates:
        try:
            os.makedirs(path, exist_ok=True)
            probe = os.path.join(path, ".write-test")
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write("ok")
            os.remove(probe)
            return path
        except OSError:
            continue
    return tempfile.gettempdir()


def settings_path() -> str:
    return os.path.join(home_dir(), "settings.json")


def log_path() -> str:
    return os.path.join(home_dir(), "pantela.log")


@dataclass
class Settings:
    # движок распознавания
    engine: str = "parakeet"          # parakeet | gigaam | whisper
    whisper_model: str = "small"
    language: str = "ru"              # ru | en | auto (auto — только для whisper)

    # управление
    hotkey: str = "ctrl+alt+space"
    mode: str = "hold"                # hold — держать, toggle — нажать/отпустить
    min_seconds: float = 0.35         # короче — считаем случайным нажатием
    max_seconds: int = 120

    # вставка результата
    auto_paste: bool = True           # доставлять текст в активное окно
    insert_mode: str = "paste"        # paste — Ctrl+V, type — печатать посимвольно
    copy_to_clipboard: bool = True
    restore_clipboard: bool = True    # вернуть прежнее содержимое буфера
    paste_delay_ms: int = 60

    # интерфейс
    show_overlay: bool = True
    play_sound: bool = True
    autostart: bool = False
    weekly_goal_words: int = 2000     # цель недели для полосы прогресса на «Главной»

    # звук
    input_device: str = ""            # пусто — устройство по умолчанию
    sample_rate: int = 16000

    # словарь замен: список пар [что, на что]
    dictionary: list[list[str]] = field(default_factory=list)

    # служебное
    models_dir: str = DEFAULT_MODELS_DIR
    notify_on_error: bool = True

    @classmethod
    def load(cls, path: str | None = None) -> "Settings":
        path = path or settings_path()
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:  # noqa: BLE001 - битый файл не должен ломать запуск
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self, path: str | None = None) -> None:
        path = path or settings_path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def apply_dictionary(self, text: str) -> str:
        out = text
        for pair in self.dictionary:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            src, dst = str(pair[0]), str(pair[1])
            if src:
                out = out.replace(src, dst)
        return out


def parse_hotkey(spec: str) -> tuple[frozenset[str], str]:
    """'ctrl+alt+space' -> ({'ctrl','alt'}, 'space')."""
    parts = [p.strip().lower() for p in spec.replace(" ", "").split("+") if p.strip()]
    mods = frozenset(p for p in parts if p in {"ctrl", "alt", "shift", "win"})
    keys = [p for p in parts if p not in mods]
    return mods, (keys[0] if keys else "space")


def format_hotkey(spec: str) -> str:
    names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win", "space": "Пробел"}
    mods, key = parse_hotkey(spec)
    order = ["ctrl", "alt", "shift", "win"]
    shown = [names[m] for m in order if m in mods]
    shown.append(names.get(key, key.upper()))
    return " + ".join(shown)
