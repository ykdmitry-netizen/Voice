"""Автопроверка «Гласографа»: то, что можно проверить без пользователя.

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
_app = None  # QApplication создаётся один раз: второй в процессе недопустим


def qt_app():
    """Лениво поднимает приложение Qt для проверок интерфейса."""
    global _app
    if _app is None:
        from app.main import Application

        _app = Application([sys.argv[0]])
    return _app


def check(name: str, fn) -> None:  # noqa: ANN001
    started = time.perf_counter()
    try:
        detail = fn()
        results.append((name, True, f"{detail or ''}  [{time.perf_counter() - started:.2f} с]"))
    except Exception as exc:  # noqa: BLE001
        results.append((name, False, f"{type(exc).__name__}: {exc}"))


# --- обычные узлы ---------------------------------------------------------
def t_config() -> str:
    from app.config import APP_TITLE, Settings, format_hotkey, home_dir, parse_hotkey

    s = Settings()
    s.dictionary = [["паракейт", "Parakeet"]]
    s.save()
    back = Settings.load()
    assert back.dictionary == s.dictionary, "словарь не сохранился"
    assert format_hotkey("ctrl+alt+space") == "Ctrl + Alt + Пробел"
    mods, key = parse_hotkey("ctrl+shift+f9")
    assert mods == frozenset({"ctrl", "shift"}) and key == "f9", (mods, key)
    assert APP_TITLE == "Гласограф"
    return f"{APP_TITLE}, {home_dir()}"


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
    marker = f"glasograf-selftest-{time.time():.0f}"
    assert set_clipboard_text(marker), "set_clipboard_text вернул False"
    time.sleep(0.05)
    assert get_clipboard_text() == marker
    if original:
        set_clipboard_text(original)
    return f"обмен «{marker}» прошёл"


def t_devices() -> str:
    from app.audio import Recorder

    devices = Recorder.list_input_devices()
    first = devices[0][1] if devices else "нет устройств ввода"
    return f"{len(devices)} устройств ввода, первое: {first}"


def t_engine() -> str:
    from app import asr
    from app.config import Settings

    sample_path = os.path.join(ROOT, "audio", "ru_real.wav")
    if not os.path.exists(sample_path):
        return "пропущено: нет тестового аудио — запустите bench/download_demo_audio.py"

    s = Settings()
    engine = asr.build_engine(s.engine, s.models_dir, s.whisper_model)
    engine.load()
    sys.path.insert(0, os.path.join(ROOT, "bench"))
    from audio_io import load  # noqa: PLC0415

    samples = load(sample_path, 16000)
    started = time.perf_counter()
    text = engine.transcribe(samples, "ru")
    elapsed = time.perf_counter() - started
    duration = len(samples) / 16000
    assert text, "пустой результат распознавания"
    return (f"{engine.name}: загрузка {engine.load_seconds:.1f} с, "
            f"{duration:.1f} с речи за {elapsed:.2f} с ({duration / elapsed:.1f}x)")


def t_models_present() -> str:
    from app import models
    from app.config import Settings

    s = Settings()
    missing = models.missing(s.models_dir, "parakeet")
    if missing:
        return ("пропущено: модели нет — запустите setup_env.bat или "
                "bench/download_models.py parakeet")
    gigaam = models.missing(s.models_dir, "gigaam")
    state = "на месте" if not gigaam else "нет: " + ", ".join(gigaam)
    return f"parakeet на месте ({models.total_size('parakeet') / 1e6:.0f} МБ), gigaam {state}"


def t_hotkey_hook() -> str:
    from app.hotkey import GlobalHotkey, key_to_vk

    assert key_to_vk("space") == 0x20
    hook = GlobalHotkey("ctrl+alt+space", lambda: None, lambda: None)
    hook.start()
    assert hook.is_running, "хук не встал"
    time.sleep(0.2)
    hook.stop()
    return "хук клавиатуры поставлен и снят"


def t_history_roundtrip() -> str:
    from app.history import History

    path = os.path.join(os.environ["PANTELA_HOME"], "roundtrip.jsonl")
    if os.path.exists(path):
        os.remove(path)
    first = History(path)
    first.add("Первая строка", 1.0)
    first.add("Вторая строка", 2.0)
    second = History(path)
    assert len(second.entries()) == 2, second.entries()
    assert second.entries()[0].text == "Вторая строка"
    second.remove(second.entries()[0])
    assert len(History(path).entries()) == 1
    os.remove(path)
    return "запись, чтение и удаление истории работают"


def t_history_stats() -> str:
    import tempfile

    from app import stats
    from app.history import History

    path = os.path.join(tempfile.gettempdir(), "glasograf_test_history.jsonl")
    if os.path.exists(path):
        os.remove(path)
    history = History(path)
    history.add("Нужно проверить документ и отправить отчёт", 5.0)
    history.add("Идея: сделать заметку про проект", 4.0)
    history.add("Обычная фраза без ключевых слов", 3.0)
    summary = stats.summarize(history.entries())
    names = [name for name, _c, _p in summary.categories]
    assert summary.words > 10 and summary.days == 1
    assert "Документы" in names or "Задачи" in names, names
    assert len(summary.activity) == 28
    history.clear()
    return f"слов {summary.words}, категорий {len(summary.categories)}, топ: {names[0]}"


# --- интерфейс на Qt ------------------------------------------------------
def t_overlay() -> str:
    app = qt_app()
    overlay = app.overlay
    overlay.enabled = True
    overlay.recording(0.4)
    app.qapp.processEvents()
    compact = overlay.width()
    for level in (0.2, 0.6, 0.9, 0.3):
        overlay.set_level(level)
    overlay.working("1.2 с")
    app.qapp.processEvents()
    overlay.done("проверка индикатора диктовки")
    app.qapp.processEvents()
    message = overlay.width()
    overlay.stop()
    assert message > compact, "сообщение должно быть шире индикатора записи"
    return f"индикатор {compact}px, сообщение {message}px"


def t_main_window() -> str:
    app = qt_app()
    app.history.clear()
    app.history.add("Проверка словаря и статистики приложения", 4.0, "parakeet")
    app.history.add("Вторая фраза для проверки истории", 6.0, "parakeet")
    window = app.window
    for key in ("home", "summary", "settings", "help"):
        window.show_page(key)
        app.qapp.processEvents()
    window.refresh_all()
    app.qapp.processEvents()
    words = window.pages["home"].words_card.value.text()
    assert words.strip() not in ("", "0"), "статистика не посчиталась"
    assert window.pages["summary"].activity._cells, "лента активности пуста"
    return f"4 раздела, слов в статистике: {words}"


def t_settings_collect() -> str:
    app = qt_app()
    page = app.window.pages["settings"]
    values = page.collect()
    required = {"engine", "hotkey", "insert_mode", "input_device", "weekly_goal_words",
                "dictionary", "auto_paste"}
    assert required.issubset(values), sorted(required - set(values))
    assert isinstance(values["weekly_goal_words"], int)
    return f"собирается: движок {values['engine']}, цель {values['weekly_goal_words']}"


def t_tray() -> str:
    from PySide6 import QtWidgets

    app = qt_app()
    available = QtWidgets.QSystemTrayIcon.isSystemTrayAvailable()
    if not available:
        return "пропущено: панель задач недоступна в этой сессии"
    shown = app.tray.show()
    return f"панель задач доступна, значок показан: {shown}"


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
    check("история: запись и удаление", t_history_roundtrip)
    check("история: статистика", t_history_stats)
    check("индикатор диктовки", t_overlay)
    check("главное окно", t_main_window)
    check("сбор настроек из окна", t_settings_collect)
    check("значок в трее", t_tray)
    check("импорт приложения", t_import_main)

    if _app is not None:
        _app.quit()

    width = max(len(name) for name, _ok, _d in results)
    print("\n=== Самопроверка «Гласографа» ===\n")
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
