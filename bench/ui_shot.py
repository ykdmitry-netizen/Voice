"""Снимки интерфейса «Гласографа»: индикатор диктовки и четыре раздела окна.

Окна настоящие, поэтому снимаем область экрана: так видно то же, что видит
пользователь, включая скругления и прозрачность.
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "pylibs"), ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("PANTELA_HOME", os.path.join(ROOT, "testhome"))
os.environ["PANTELA_NO_TRAY"] = "1"

from PySide6 import QtCore, QtGui  # noqa: E402

from app.main import Application  # noqa: E402

SHOTS = os.path.join(ROOT, "bench", "shots")

DEMO = [
    ("Так, теперь пошла настоящая проверка. Смотри, зашёл.", 39.0),
    ("Смотри, вот сейчас я зашёл на страницу статусы ящика и всё проверил.", 69.0),
    ("Не работает твоя фишка. Всё равно доступ запрещён, проверь права.", 63.0),
    ("Смотри, ещё по сертификату. Там и добавил сертификат приложения.", 39.0),
    ("Давай, набирай. Всё, что есть, я сейчас посмотрю, что тут не так.", 24.0),
    ("Смотри, заходил только что, уже, наверное, раз пятый. Так нужно.", 44.0),
]


def pump(app, seconds: float = 0.5) -> None:  # noqa: ANN001
    end = time.time() + seconds
    while time.time() < end:
        app.qapp.processEvents()
        time.sleep(0.03)


def grab_widget(app, widget, name: str, background: str | None = None) -> None:  # noqa: ANN001
    """Снимаем сам виджет: так на картинку не попадут чужие окна поверх."""
    pump(app, 0.5)
    pixmap = widget.grab()
    if background:
        canvas = QtGui.QPixmap(pixmap.size())
        canvas.fill(QtGui.QColor(background))
        painter = QtGui.QPainter(canvas)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        pixmap = canvas
    path = os.path.join(SHOTS, name)
    pixmap.save(path)
    print(f"{name}: {pixmap.width()}x{pixmap.height()}")


def main() -> int:
    os.makedirs(SHOTS, exist_ok=True)
    app = Application([sys.argv[0]])
    app.overlay.enabled = True

    app.history.clear()
    now = time.time()
    for index, (text, seconds) in enumerate(DEMO):
        app.history.add(text, seconds, "parakeet")
        app.history._entries[-1].ts = now - index * 3600 - 1800
    app.history.rewrite()
    app.window.refresh_all()

    overlay = app.overlay
    overlay.recording(0.35)
    for level in (0.25, 0.6, 0.85, 0.4, 0.7, 0.3, 0.65, 0.45):
        overlay.set_level(level)
        pump(app, 0.06)
    grab_widget(app, overlay, background="#33333a", name="overlay_recording.png")

    overlay.set_level(0.9)
    overlay.working("1.4 с")
    grab_widget(app, overlay, background="#33333a", name="overlay_working.png")

    overlay.done("Так, теперь пошла настоящая проверка")
    grab_widget(app, overlay, background="#33333a", name="overlay_done.png")
    overlay.stop()

    window = app.window
    window.show_window()
    window.set_status("Текст вставлен в активное окно · 9 сл.", "#7cc47f")
    for key, name in (("home", "window_home.png"), ("summary", "window_summary.png"),
                      ("settings", "window_settings.png"), ("help", "window_help.png")):
        window.show_page(key)
        pump(app, 0.4)
        grab_widget(app, window, name)

    app.quit()
    print("готово:", SHOTS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
