"""Проверка доставки текста в настоящее поле ввода Windows.

Создаём обычное окно с многострочным EDIT, ставим фокус, прогоняем оба режима
вставки (Ctrl+V и посимвольную печать) и читаем результат через WM_GETTEXT.

Виджет Tk для этой проверки не годится: он игнорирует синтезированный Ctrl+V,
хотя реальные приложения его принимают.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "pylibs"), ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app import inserter  # noqa: E402

user32 = inserter.user32
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_VISIBLE = 0x10000000
WS_CHILD = 0x40000000
WS_BORDER = 0x00800000
WS_VSCROLL = 0x00200000
ES_MULTILINE = 0x0004
ES_AUTOVSCROLL = 0x0040
WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
PM_REMOVE = 0x0001

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetFocus.argtypes = [wintypes.HWND]
user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.SetActiveWindow.argtypes = [wintypes.HWND]
user32.PeekMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT
]

ASFW_ANY = -1
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x0002


def force_foreground(hwnd) -> None:  # noqa: ANN001
    """Windows не даёт просто так забрать фокус: нужно право на это. Самое
    надёжное — «нажать» Alt, после чего SetForegroundWindow разрешён."""
    user32.AllowSetForegroundWindow(ASFW_ANY)
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    user32.SetActiveWindow(hwnd)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)


def edit_text(edit) -> str:  # noqa: ANN001
    length = user32.SendMessageW(edit, WM_GETTEXTLENGTH, 0, 0)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.SendMessageW(edit, WM_GETTEXT, length + 1, ctypes.addressof(buf))
    return buf.value


def main() -> int:
    hinst = kernel32.GetModuleHandleW(None)
    wndproc = WNDPROC(lambda hwnd, msg, wp, lp: user32.DefWindowProcW(hwnd, msg, wp, lp))

    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.lpfnWndProc = wndproc
    wc.hInstance = hinst
    wc.lpszClassName = "PantelaPasteTest"
    user32.RegisterClassExW(ctypes.byref(wc))

    main_hwnd = user32.CreateWindowExW(
        0, "PantelaPasteTest", "Pantela Voice — проверка вставки",
        WS_OVERLAPPEDWINDOW | WS_VISIBLE, 120, 120, 640, 260,
        None, None, hinst, None,
    )
    edit = user32.CreateWindowExW(
        0, "EDIT", "",
        WS_CHILD | WS_VISIBLE | WS_BORDER | WS_VSCROLL | ES_MULTILINE | ES_AUTOVSCROLL,
        10, 10, 610, 200, main_hwnd, None, hinst, None,
    )
    user32.SetForegroundWindow(main_hwnd)
    user32.SetFocus(edit)

    msg = wintypes.MSG()

    def pump(seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.01)

    for _ in range(10):
        force_foreground(main_hwnd)
        user32.SetFocus(edit)
        pump(0.3)
        if user32.GetForegroundWindow() == main_hwnd:
            break

    if user32.GetForegroundWindow() != main_hwnd:
        title = ctypes.create_unicode_buffer(256)
        fg = user32.GetForegroundWindow()
        user32.GetWindowTextW(fg, title, 256)
        print(f"БЕЗОПАСНОСТЬ: фокус в чужом окне {title.value!r} — ничего не отправляем.")
        user32.DestroyWindow(main_hwnd)
        return 2

    print("окно и поле в фокусе:", user32.GetFocus() == edit)

    results = []
    for mode, sample in (
        ("paste", "Режим Ctrl+V: Pantela Voice, 123."),
        ("type", "Режим печати: Pantela Voice, 123."),
    ):
        user32.SendMessageW(edit, WM_SETTEXT, 0, 0)
        pump(0.2)
        if user32.GetForegroundWindow() != main_hwnd:
            print(f"фокус потерян перед режимом {mode} — ничего не отправляем")
            results.append((mode, False))
            continue
        delivered, _ = inserter.insert_text(
            sample, auto_paste=True, restore_clipboard=False,
            paste_delay_ms=80, mode=mode,
        )
        pump(0.9)
        got = edit_text(edit)
        ok = delivered and got.strip() == sample
        results.append((mode, ok))
        print(f"{'OK ' if ok else 'НЕТ'} режим {mode}: {got!r}")

    user32.DestroyWindow(main_hwnd)
    failed = [mode for mode, ok in results if not ok]
    print("\nИТОГ:", "оба режима доставляют текст" if not failed
          else f"не сработали: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
