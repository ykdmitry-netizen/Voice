"""Проверка горячей клавиши.

Две части:

1. Логика хука — ему скармливаются синтетические события клавиатуры, а
   состояние модификаторов подменяется. Проверяется press/release/cancel и
   перехват клавиши.
2. Цепочка в приложении — событие клавиши доходит до старта записи,
   останавливается и приводит к решению (распознавание или сообщение о тишине).

Доставку реальных клавиш через SendInput проверить внутри песочницы агента
нельзя: синтезированный ввод доходит до системы только когда активно
собственное окно процесса. Это проверяется живым нажатием на клавиатуре.
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


def part1_hook_logic() -> bool:
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
    print(f"1. нажатие и отпускание: события={log}, перехвачено={bool(swallowed_press)}")
    ok = log == ["press", "release"] and swallowed_press == 1 and swallowed_release == 1

    log.clear()
    feed(hook, VK_SPACE, True)
    feed(hook, VK_ESCAPE, True)
    print(f"2. Esc во время диктовки: события={log}")
    ok = ok and "cancel" in log

    log.clear()
    modifiers["ctrl"] = 0x8000
    feed(hook, VK_SPACE, True)
    modifiers["ctrl"] = 0
    modifiers["space"] = 0
    feed(hook, VK_CONTROL, False)
    print(f"3. Ctrl отпущен раньше пробела: события={log}")
    ok = ok and log == ["press", "release"]

    log.clear()
    modifiers["ctrl"] = 0
    modifiers["alt"] = 0
    result = feed(hook, VK_SPACE, True)
    print(f"4. просто пробел: события={log}, перехвачено={bool(result)}")
    ok = ok and not log and result == 0

    modifiers.update({"ctrl": 0x8000, "alt": 0x8000, "space": 0x8000})
    return ok


def part2_app_chain() -> bool:
    setup_logging()
    app = Application([sys.argv[0]])
    app.overlay.enabled = False

    calls: list[str] = []
    app.overlay.recording = lambda level=0.0: calls.append("recording")
    app.overlay.working = lambda subtitle="": calls.append("working")
    app.overlay.done = lambda text, hide_after_ms=0: calls.append(f"done:{text[:25]}")
    app.overlay.error = lambda message, hide_after_ms=0: calls.append(f"error:{message[:40]}")
    app.overlay.notice = lambda title, subtitle="", color=None, hide_after_ms=0: calls.append(
        f"notice:{title}")
    app.overlay.set_level = lambda level: None

    app.events.put(("press", None))          # имитируем нажатие
    started = False
    deadline = time.time() + 8
    while time.time() < deadline:
        app.qapp.processEvents()
        if app._recording:
            started = True
            break
        time.sleep(0.03)

    time.sleep(1.2)                           # «держим» клавиши
    app.events.put(("release", None))         # имитируем отпускание
    deadline = time.time() + 8
    while time.time() < deadline:
        app.qapp.processEvents()
        if not app._recording and calls:
            break
        time.sleep(0.03)
    for _ in range(20):
        app.qapp.processEvents()
        time.sleep(0.05)

    print(f"5. запись по событию: стартовала={started}, реакция={calls}")
    app.quit()
    # микрофона может не быть в системе — это не ошибка приложения
    if not started and any(str(c).startswith("error:микрофон") for c in calls):
        print("   (микрофон недоступен — проверка цепочки пропущена)")
        return True
    return started and bool(calls)


def main() -> int:
    ok1 = part1_hook_logic()
    print()
    ok2 = part2_app_chain()
    print(f"\nИТОГ: логика хука — {'ок' if ok1 else 'ОШИБКА'}, "
          f"цепочка в приложении — {'ок' if ok2 else 'ОШИБКА'}")
    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    raise SystemExit(main())
