"""Снимки интерфейса: индикатор диктовки и четыре вкладки главного окна.

Важно: используется единственный `Tk()` — тот, что создаёт само приложение.
Второй экземпляр Tk в одном процессе уводит StringVar в другой интерпретатор
Tcl, и поля выглядят пустыми (это ломает только тесты, не приложение).

Результат — PNG в bench/shots.
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

from PIL import ImageGrab  # noqa: E402

from app.config import Settings  # noqa: E402
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


def pump(root, seconds: float = 0.4) -> None:  # noqa: ANN001
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.03)


def grab(root, widget, name: str, pad: int = 10) -> None:  # noqa: ANN001
    pump(root, 0.4)
    widget.update_idletasks()
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    image = ImageGrab.grab((x - pad, y - pad, x + widget.winfo_width() + pad,
                            y + widget.winfo_height() + pad))
    image.save(os.path.join(SHOTS, name))
    print(f"{name}: {image.size[0]}x{image.size[1]}")


def main() -> int:
    os.makedirs(SHOTS, exist_ok=True)

    app = Application(Settings(show_overlay=True, play_sound=False))
    root = app.root
    app.overlay.enabled = True

    app.history.clear()
    now = time.time()
    for index, (text, seconds) in enumerate(DEMO):
        app.history.add(text, seconds, "parakeet")
        app.history._entries[-1].ts = now - index * 3600 - 1800
    app.history.rewrite()

    overlay = app.overlay
    overlay.recording(0.35)
    for level in (0.25, 0.6, 0.85, 0.4, 0.7, 0.3, 0.65, 0.45):
        overlay.set_level(level)
        pump(root, 0.05)
    grab(root, overlay.win, "overlay_recording.png")

    overlay.set_level(0.9)
    overlay.working("1.4 с")
    grab(root, overlay.win, "overlay_working.png")

    overlay.done("Так, теперь пошла настоящая проверка")
    grab(root, overlay.win, "overlay_done.png")
    overlay.hide()

    window = app.window
    window.show()
    window.set_status("Текст вставлен в активное окно · 9 сл.", "#7cc47f")
    for tab in ("home", "summary", "settings", "help"):
        window.show_tab(tab)
        window.refresh_all()
        grab(root, window.win, f"window_{tab}.png", pad=0)

    app.quit()
    print("готово:", SHOTS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
