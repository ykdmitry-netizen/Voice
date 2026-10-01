"""Снимки интерфейса: индикатор диктовки, окно управления, настройки.

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
from app.overlay import ControlWindow  # noqa: E402
from app.settings_ui import SettingsWindow  # noqa: E402

SHOTS = os.path.join(ROOT, "bench", "shots")


def pump(root, seconds: float = 0.4) -> None:  # noqa: ANN001
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.03)


def grab(root, widget, name: str, pad: int = 10) -> None:  # noqa: ANN001
    pump(root, 0.35)
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
    overlay = app.overlay
    overlay.enabled = True

    overlay.recording(0.35)
    for level in (0.2, 0.55, 0.8, 0.45, 0.7, 0.3, 0.6):
        overlay.set_level(level)
        pump(root, 0.06)
    grab(root, overlay.win, "overlay_recording.png")

    overlay.set_level(0.9)
    overlay.working("1.4 с")
    grab(root, overlay.win, "overlay_working.png")

    overlay.done("Сегодня я тестирую локальную диктовку")
    grab(root, overlay.win, "overlay_done.png")

    overlay.notice("Слишком коротко", hide_after_ms=6000)
    grab(root, overlay.win, "overlay_notice.png")
    overlay.hide()

    control = ControlWindow(root, lambda: None, lambda: None, lambda: None)
    grab(root, control.win, "control_window.png")
    control.destroy()

    window = SettingsWindow(app)
    pump(root, 0.8)
    for index, name in enumerate(
        ["settings_recognition.png", "settings_control.png", "settings_dictionary.png"]
    ):
        window.notebook.select(index)
        grab(root, window.win, name, pad=0)
    window.close()

    app.quit()
    print("готово:", SHOTS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
