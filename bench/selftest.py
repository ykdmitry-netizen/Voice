"""Автопроверка узлов приложения: то, что можно проверить без пользователя.

Запуск:  py -3.12 bench/selftest.py
"""

from __future__ import annotations

import ctypes
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (os.path.join(ROOT, "pylibs"), ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

os.environ.setdefault("PANTELA_NO_TRAY", "1")
os.environ.setdefault("PANTELA_HOME", os.path.join(ROOT, "testhome"))

results: list[tuple[str, bool, str]] = []


def check(name: str, fn) -> None:  # noqa: ANN001
    started = time.perf_counter()
    try:
        detail = fn()
        if detail is None:
            detail = ""
        results.append((name, True, f"{detail}  [{time.perf_counter() - started:.2f} с]"))
    except Exception as exc:  # noqa: BLE001
        results.append((name, False, f"{type(exc).__name__}: {exc}"))


def t_config() -> str:
    from app.config import Settings, format_hotkey, home_dir, parse_hotkey

    s = Settings()
    s.dictionary = [["паракейт", "Parakeet"]]
    s.save()
    back = Settings.load()
    assert back.dictionary == s.dictionary, "словарь не сохранился"
    assert format_hotkey("ctrl+alt+space") == "Ctrl + Alt + Пробел"
    mods, key = parse_hotkey("ctrl+shift+f9")
    assert mods == frozenset({"ctrl", "shift"}) and key == "f9", (mods, key)
    return f"{home_dir()}"


def t_dictionary() -> str:
    from app.config import Settings

    s = Settings(dictionary=[["паракейт", "Parakeet"], ["харнесс", "Harness"]])
    out = s.apply_dictionary("локальный паракейт и харнесс")
    assert out == "локальный Parakeet и Harness", out
    return out


def t_sendinput_layout() -> str:
    from app.inserter import INPUT

    size = ctypes.sizeof(INPUT)
    expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    assert size == expected, f"sizeof(INPUT)={size}, ожидалось {expected}"
    return f"sizeof(INPUT)={size}"


def t_clipboard() -> str:
    from app.inserter import get_clipboard_text, set_clipboard_text

    original = get_clipboard_text()
    marker = f"pantela-selftest-{time.time():.0f}"
    assert set_clipboard_text(marker), "set_clipboard_text вернул False"
    time.sleep(0.05)
    got = get_clipboard_text()
    assert got == marker, f"прочитано {got!r}"
    if original:
        set_clipboard_text(original)
    return f"обмен «{marker}» прошёл"


def t_devices() -> str:
    from app.audio import Recorder

    devices = Recorder.list_input_devices()
    assert devices, "не найдено ни одного микрофона"
    return f"{len(devices)} устройств ввода, первое: {devices[0][1]}"


def t_engine() -> str:
    from app import asr
    from app.config import Settings

    s = Settings.load()
    engine = asr.build_engine(s.engine, s.models_dir, s.whisper_model)
    engine.load()
    sys.path.insert(0, os.path.join(ROOT, "bench"))
    from audio_io import load  # noqa: PLC0415

    samples = load(os.path.join(ROOT, "audio", "ru_real.wav"), 16000)
    started = time.perf_counter()
    text = engine.transcribe(samples, "ru")
    elapsed = time.perf_counter() - started
    duration = len(samples) / 16000
    assert text, "пустой результат распознавания"
    return (f"{engine.name}: загрузка {engine.load_seconds:.1f} с, "
            f"{duration:.1f} с речи за {elapsed:.2f} с ({duration / elapsed:.1f}x) -> {text[:60]}")


def t_hotkey_hook() -> str:
    from app.hotkey import GlobalHotkey, key_to_vk

    assert key_to_vk("space") == 0x20
    hook = GlobalHotkey("ctrl+alt+space", lambda: None, lambda: None)
    hook.start()
    assert hook.is_running, "хук не встал"
    time.sleep(0.2)
    hook.stop()
    return "хук клавиатуры поставлен и снят"


def t_ui() -> str:
    import tkinter as tk

    from app.overlay import ControlWindow, Overlay

    root = tk.Tk()
    root.withdraw()
    overlay = Overlay(root, show=True)

    overlay.recording(0.4)
    root.update()
    width_recording = overlay._width

    overlay.set_level(0.9)
    overlay.working("1.2 с")
    root.update()

    overlay.done("готово: проверка панели")
    root.update()
    width_message = overlay._width

    overlay.notice("Проверка", hide_after_ms=100)
    root.update()
    overlay.hide()

    control = ControlWindow(root, lambda: None, lambda: None, lambda: None)
    control.set_recording(True)
    root.update()
    control.destroy()

    overlay.destroy()
    root.destroy()
    assert width_message > width_recording, "сообщение должно быть шире компактного индикатора"
    return f"индикатор компактный ({width_recording}px), сообщение {width_message}px"


def t_tray_icon() -> str:
    import os

    from app.config import Settings, home_dir
    from app.main import Application
    from app.tray import TrayIcon, make_icon_file

    class FakeApp(Application):  # noqa: D101
        def __init__(self) -> None:  # noqa: D107
            self.settings = Settings()
            self._recording = False
            self.events = type("Q", (), {"put": staticmethod(lambda _x: None)})()

    icon = FakeApp()._build_tray()
    assert isinstance(icon, TrayIcon), "ожидался нативный значок"

    icon_path = os.path.join(home_dir(), "tray.ico")
    assert make_icon_file(icon_path), "не удалось нарисовать значок"
    assert os.path.getsize(icon_path) > 500, "файл значка подозрительно мал"

    started = icon.start(timeout=2.0)
    icon.notify("Проверка", "значок в трее")
    icon.stop()
    state = "значок появился" if started else "значок не появился (нет доступа к панели задач)"
    return f"файл значка {os.path.getsize(icon_path)} байт, {state}"


def t_models_present() -> str:
    from app import models
    from app.config import Settings

    s = Settings.load()
    missing = models.missing(s.models_dir, "parakeet")
    assert not missing, f"не хватает файлов Parakeet: {missing}"
    gigaam = models.missing(s.models_dir, "gigaam")
    state = "на месте" if not gigaam else "нет: " + ", ".join(gigaam)
    return f"parakeet на месте ({models.total_size('parakeet') / 1e6:.0f} МБ), gigaam {state}"


def t_settings_window() -> str:
    from app.config import Settings
    from app.main import Application
    from app.settings_ui import SettingsWindow

    app = Application(Settings(show_overlay=False, play_sound=False))
    app.overlay.enabled = False
    window = SettingsWindow(app)
    app.root.update()
    tabs = window.win.winfo_children()
    assert tabs, "окно настроек пустое"
    window.close()
    app.root.update()
    app.quit()
    return "окно настроек открывается и закрывается"


def t_import_main() -> str:
    from app import main as main_module

    assert hasattr(main_module, "Application")
    return "модуль приложения импортируется"


def main() -> int:
    check("настройки и горячая клавиша", t_config)
    check("словарь замен", t_dictionary)
    check("раскладка SendInput", t_sendinput_layout)
    check("буфер обмена", t_clipboard)
    check("микрофоны", t_devices)
    check("движок распознавания", t_engine)
    check("файлы моделей", t_models_present)
    check("хук клавиатуры", t_hotkey_hook)
    check("панель состояния", t_ui)
    check("значок в трее", t_tray_icon)
    check("окно настроек", t_settings_window)
    check("импорт приложения", t_import_main)

    width = max(len(name) for name, _ok, _d in results)
    print("\n=== Самопроверка Pantela Voice ===\n")
    failed = 0
    for name, ok, detail in results:
        mark = "OK  " if ok else "ОШИБКА"
        if not ok:
            failed += 1
        print(f"{mark} {name.ljust(width)}  {detail}")
    print(f"\nвсего {len(results)}, успешно {len(results) - failed}, ошибок {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
