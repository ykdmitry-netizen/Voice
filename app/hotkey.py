"""Глобальная горячая клавиша через низкоуровневый хук клавиатуры (WH_KEYBOARD_LL).

Хук живёт в отдельном потоке со своим циклом сообщений. Колбэки вызываются из
этого потока, поэтому они должны быть мгновенными: приложение в них только
складывает события в очередь.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C

MODIFIER_VKS = {VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN}

NAMED_KEYS = {
    "space": 0x20,
    "пробел": 0x20,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "insert": 0x2D,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "`": 0xC0,
    "-": 0xBD,
    "=": 0xBB,
    "[": 0xDB,
    "]": 0xDD,
    "\\": 0xDC,
    ";": 0xBA,
    "'": 0xDE,
    ",": 0xBC,
    ".": 0xBE,
    "/": 0xBF,
}
for _i in range(1, 13):
    NAMED_KEYS[f"f{_i}"] = 0x6F + _i


def key_to_vk(name: str) -> int:
    key = name.strip().lower()
    if key in NAMED_KEYS:
        return NAMED_KEYS[key]
    if len(key) == 1 and key.isalpha():
        return ord(key.upper())
    if len(key) == 1 and key.isdigit():
        return ord(key)
    if key.startswith("0x"):
        return int(key, 16)
    raise ValueError(f"неизвестная клавиша: {name}")


MODIFIER_VK_BY_NAME = {"ctrl": VK_CONTROL, "alt": VK_MENU, "shift": VK_SHIFT, "win": VK_LWIN}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


class GlobalHotkey:
    """Удержание или переключение по комбинации вида 'ctrl+alt+space'."""

    def __init__(
        self,
        spec: str,
        on_press,
        on_release,
        on_cancel=None,
        log=None,
    ) -> None:
        from .config import parse_hotkey

        self.mods, key_name = parse_hotkey(spec)
        self.vk = key_to_vk(key_name)
        self.on_press = on_press
        self.on_release = on_release
        self.on_cancel = on_cancel
        self.log = log or (lambda *_: None)

        self._thread: threading.Thread | None = None
        self._thread_id: int = 0
        self._hook = None
        self._proc = HOOKPROC(self._hook_proc)  # держим ссылку, иначе сборщик убьёт
        self._down = False
        self._swallow = False
        self.started_at = 0.0

    # --- состояние модификаторов ----------------------------------------
    def _mods_down(self) -> bool:
        for name in self.mods:
            vk = MODIFIER_VK_BY_NAME[name]
            if name == "win":
                if not (user32.GetAsyncKeyState(VK_LWIN) & 0x8000
                        or user32.GetAsyncKeyState(VK_RWIN) & 0x8000):
                    return False
            elif not user32.GetAsyncKeyState(vk) & 0x8000:
                return False
        return True

    # --- сам хук ---------------------------------------------------------
    def _hook_proc(self, n_code, w_param, l_param):  # noqa: ANN001
        if n_code < 0:
            return user32.CallNextHookEx(None, n_code, w_param, l_param)
        info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        vk = int(info.vkCode)
        is_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
        is_up = w_param in (WM_KEYUP, WM_SYSKEYUP)

        try:
            if vk == 0x1B and self._down and is_down and self.on_cancel:
                # Esc во время диктовки — отмена
                self._down = False
                self._swallow = False
                self.on_cancel()
            elif vk == self.vk:
                if is_down and not self._down and self._mods_down():
                    self._down = True
                    self._swallow = True
                    self.started_at = time.time()
                    self.on_press()
                    return 1  # не пропускаем клавишу в приложение
                if is_down and self._down:
                    return 1
                if is_up and self._down:
                    self._down = False
                    was_swallowed = self._swallow
                    self._swallow = False
                    self.on_release()
                    if was_swallowed:
                        return 1
            elif vk in MODIFIER_VKS and is_up and self._down:
                # отпустили Ctrl/Alt раньше основной клавиши
                if not user32.GetAsyncKeyState(self.vk) & 0x8000:
                    self._down = False
                    self._swallow = False
                    self.on_release()
        except Exception as exc:  # noqa: BLE001 - хук не должен падать
            self.log(f"hotkey callback error: {exc!r}")

        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    # --- жизненный цикл --------------------------------------------------
    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not self._hook:
            self.log(f"SetWindowsHookExW failed: {ctypes.get_last_error()}")
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(self._hook)
        self._hook = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="hotkey", daemon=True)
        self._thread.start()
        for _ in range(100):
            if self._hook:
                break
            time.sleep(0.01)

    def stop(self) -> None:
        if self._thread is None:
            return
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self._thread.join(timeout=1.0)
        self._thread = None
        self._thread_id = 0

    @property
    def is_running(self) -> bool:
        return bool(self._hook)
