"""Сквозная проверка: «нажал — отпустил» -> распознавание -> буфер обмена.

Микрофон и вставка Ctrl+V не задействуются: вместо записи подставляется
готовый wav, а вставка отключена, чтобы тест не отправлял нажатия в чужие окна.
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (os.path.join(ROOT, "pylibs"), ROOT, os.path.join(ROOT, "bench")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

os.environ["PANTELA_NO_TRAY"] = "1"
os.environ.setdefault("PANTELA_HOME", os.path.join(ROOT, "testhome"))

from audio_io import load  # noqa: E402
from app.config import Settings  # noqa: E402
from app.inserter import get_clipboard_text, set_clipboard_text  # noqa: E402
from app.main import Application, setup_logging  # noqa: E402


def main() -> int:
    setup_logging()
    samples = load(os.path.join(ROOT, "audio", "ru_real.wav"), 16000)
    print(f"тестовое аудио: {len(samples) / 16000:.2f} с")

    settings = Settings(
        show_overlay=False,
        auto_paste=False,
        copy_to_clipboard=True,
        play_sound=False,
        dictionary=[["Ничьих", "НИЧЬИХ"]],
    )
    settings.save()

    original_clipboard = get_clipboard_text()
    set_clipboard_text("")
    app = Application([sys.argv[0]])
    app.overlay.enabled = False

    # подменяем работу с железом: запись отдаёт заранее загруженный wav
    app.recorder.start = lambda *a, **k: None       # type: ignore[method-assign]
    app.recorder.stop = lambda: samples             # type: ignore[method-assign]
    app.recorder.cancel = lambda: None              # type: ignore[method-assign]

    print("нажимаем горячую клавишу (имитация)…")
    app.events.put(("press", None))
    deadline = time.time() + 8
    while time.time() < deadline and not app._recording:
        app.qapp.processEvents()
        time.sleep(0.03)
    assert app._recording, "запись не началась"

    time.sleep(1.0)
    app.events.put(("release", None))
    assert True

    deadline = time.time() + 90
    text = ""
    while time.time() < deadline:
        app.qapp.processEvents()
        text = get_clipboard_text()
        if text:
            break
        time.sleep(0.05)

    app.quit()

    ok = True
    if not text:
        print("ОШИБКА: буфер обмена пуст — результат не дошёл")
        ok = False
    else:
        print(f"в буфере: {text[:90]}")
        if "НИЧЬИХ" not in text:
            print("ОШИБКА: словарь замен не применился")
            ok = False
        if len(text) < 40:
            print("ОШИБКА: текст подозрительно короткий")
            ok = False

    if original_clipboard:
        set_clipboard_text(original_clipboard)
    print("\nИТОГ:", "сквозной путь работает" if ok else "есть проблемы")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
