"""Проверка горячей клавиши.

Две части:

1. Логика хука — ему скармливаются синтетические события клавиатуры, а
   состояние модификаторов подменяется. Проверяется press/release/cancel и
   перехват клавиши (хук не должен пропускать пробел в приложение).
2. Цепочка в приложении — событие клавиши доходит до старта записи,
   останавливается и приводит к решению (распознавание или сообщение о тишине).

Доставку реальных клавиш через SendInput проверить внутри песочницы агента
нельзя: синтезированный ввод доходит до системы только когда активно
собственное окно процесса, а хук должен ловить нажатия в любом окне. Это
проверяется живым нажатием на клавиатуре.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "pylibs"), ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ["PANTELA_NO_TRAY"] = "1"
os.environ.setdefault("PANTELA_HOME", os.path.join(ROOT, "testhome"))

from app import hotkey as hk  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import Application, setup_logging  # noqa: E402

VK_CONTROL = 0x11
VK_MENU = 0x12
VK_SPACE = 0x20
VK_ESCAPE = 0x1B

modifiers = {"ctrl": 0x8000, "alt": 0x8000, "space": 0x8000}


def fake_async_state(vk: int) -> int:
    if vk == VK_CONTROL:
        return modifiers["ctrl"]
    if vk == VK_MENU:
        return modifiers["alt"]
    if vk == VK_SPACE:
        return modifiers["space"]
    return 0


def feed(hook, vk: int, down: bool) -> int:  # noqa: ANN001
    info = hk.KBDLLHOOKSTRUCT(vkCode=vk, scanCode=0, flags=0, time=0, dwExtraInfo=None)
    msg = hk.WM_KEYDOWN if down else hk.WM_KEYUP
    return hook._hook_proc(0, msg, ctypes.addressof(info))


def part1_hook_logic() -> tuple[bool, list[str]]:
    hk.user32.GetAsyncKeyState = fake_async_state
    hk.user32.CallNextHookEx = lambda *args: 0

    log: list[str] = []
    hook = hk.GlobalHotkey(
        "ctrl+alt+space",
        on_press=lambda: log.append("press"),
        on_release=lambda: log.append("release"),
        on_cancel=lambda: log.append("cancel"),
    )

    swallowed_press = feed(hook, VK_SPACE, True)
    swallowed_release = feed(hook, VK_SPACE, False)
    print(f"1. нажатие: события={log}, перехвачено={bool(swallowed_press)}")
    print(f"   отпускание: события={log}, перехвачено={bool(swallowed_release)}")

    ok = log == ["press", "release"] and swallowed_press == 1 and swallowed_release == 1

    # Esc во время удержания — отмена
    log.clear()
    feed(hook, VK_SPACE, True)
    feed(hook, VK_ESCAPE, True)
    print(f"2. Esc во время диктовки: события={log}")
    ok = ok and "cancel" in log

    # отпустили Ctrl раньше пробела
    log.clear()
    modifiers["ctrl"] = 0x8000
    feed(hook, VK_SPACE, True)
    modifiers["ctrl"] = 0
    modifiers["space"] = 0
    feed(hook, VK_CONTROL, False)
    print(f"3. Ctrl отпущен раньше пробела: события={log}")
    ok = ok and log == ["press", "release"]

    # без модификаторов пробел не перехватывается
    log.clear()
    modifiers["ctrl"] = 0
    modifiers["alt"] = 0
    result = feed(hook, VK_SPACE, True)
    print(f"4. просто пробел: события={log}, перехвачено={bool(result)}")
    ok = ok and not log and result == 0

    modifiers.update({"ctrl": 0x8000, "alt": 0x8000, "space": 0x8000})
    return ok, log


def part2_app_chain() -> tuple[bool, list[str]]:
    setup_logging()
    settings = Settings(
        show_overlay=False, play_sound=False, auto_paste=False,
        copy_to_clipboard=False, mode="hold", min_seconds=0.35,
    )
    app = Application(settings)
    app.overlay.enabled = False

    calls: list[str] = []
    app.overlay.recording = lambda level=0.0: calls.append("recording")
    app.overlay.working = lambda subtitle="": calls.append("working")
    app.overlay.done = lambda text, hide_after_ms=0: calls.append(f"done:{text[:25]}")
    app.overlay.error = lambda message, hide_after_ms=0: calls.append(f"error:{message[:30]}")
    app.overlay.notice = lambda title, subtitle="", color=None, hide_after_ms=0: calls.append(
        f"notice:{title}"
    )
    app.overlay.set_level = lambda level, color=None: None
    app.overlay.set = lambda *a, **k: None

    app._pump()
    app.events.put(("press", None))          # имитируем нажатие
    started = False
    deadline = time.time() + 10
    while time.time() < deadline:
        app.root.update()
        if app._recording:
            started = True
            break
        time.sleep(0.03)

    time.sleep(1.2)                           # «держим» клавиши
    app.events.put(("release", None))         # имитируем отпускание
    deadline = time.time() + 10
    while time.time() < deadline:
        app.root.update()
        if not app._recording and calls:
            break
        time.sleep(0.03)
    for _ in range(20):
        app.root.update()
        time.sleep(0.05)
    app.quit()

    print(f"5. запись по событию: стартовала={started}, реакция={calls}")
    ok = started and bool(calls)
    return ok, calls


def part3_real_delivery() -> tuple[bool, str]:
    """Пытается проверить настоящую доставку нажатия через систему.

    Синтезированный ввод в этой песочнице доходит до системы, только когда
    активна собственная программа, поэтому сначала забираем фокус на своё окно.
    Если фокус забрать не удалось — тест пропускается, а не падает.
    """
    import tkinter as tk

    from app.inserter import _key, _send, user32

    KEYUP = 0x0002
    VK_MENU = 0x12

    user32.AllowSetForegroundWindow(-1)
    root = tk.Tk()
    root.title("Pantela Voice — проверка горячей клавиши")
    root.geometry("420x120+160+160")
    root.attributes("-topmost", True)
    label = tk.Label(root, text="Не закрывайте это окно несколько секунд", height=4)
    label.pack(fill="both", expand=True)
    root.update()

    for _ in range(8):
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.SetForegroundWindow(root.winfo_id())
        user32.BringWindowToTop(root.winfo_id())
        user32.keybd_event(VK_MENU, 0, KEYUP, 0)
        root.update()
        time.sleep(0.25)
        if user32.GetForegroundWindow() == root.winfo_id():
            break

    if user32.GetForegroundWindow() != root.winfo_id():
        root.destroy()
        return True, "пропущено: рабочий стол занят другим окном"

    log: list[str] = []
    hook = hk.GlobalHotkey(
        "ctrl+alt+space",
        on_press=lambda: log.append("press"),
        on_release=lambda: log.append("release"),
    )
    hook.start()
    if not hook.is_running:
        node = "ОШИБКА: хук не установился"
        root.destroy()
        return False, node

    time.sleep(0.3)
    _send([_key(VK_CONTROL), _key(VK_MENU), _key(VK_SPACE)])
    for _ in range(30):
        root.update()
        time.sleep(0.02)
    _send([_key(VK_SPACE, KEYUP), _key(VK_MENU, KEYUP), _key(VK_CONTROL, KEYUP)])
    for _ in range(30):
        root.update()
        time.sleep(0.02)

    hook.stop()
    root.destroy()
    ok = log == ["press", "release"]
    return ok, f"события от системы: {log}"


def main() -> int:
    ok1, _ = part1_hook_logic()
    print()
    ok2, _ = part2_app_chain()
    print()
    ok3, note3 = part3_real_delivery()
    print(f"6. доставка нажатия системой: {note3}")
    print(f"\nИТОГ: логика хука — {'ок' if ok1 else 'ОШИБКА'}, "
          f"цепочка в приложении — {'ок' if ok2 else 'ОШИБКА'}, "
          f"доставка системой — {note3}")
    return 0 if (ok1 and ok2 and ok3) else 1


if __name__ == "__main__":
    raise SystemExit(main())
