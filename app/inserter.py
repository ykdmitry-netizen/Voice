"""Вставка текста в активное окно: буфер обмена + Ctrl+V через SendInput.

Работает в любом приложении, которое умеет вставлять из буфера (аналог Cmd+V в
оригинальном macOS-приложении). Дополнительно есть режим прямой печати
Unicode-символами — на случай, если приложение блокирует Ctrl+V.

Важно: все Win32-функции получают явные argtypes/restype. Без этого ctypes
обрезает 64-битные HANDLE до int, и буфер обмена молча перестаёт работать.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_V = 0x56
VK_RETURN = 0x0D

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL


def _send(inputs: list[INPUT]) -> None:
    if not inputs:
        return
    arr = (INPUT * len(inputs))(*inputs)
    sent = user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        raise ctypes.WinError(ctypes.get_last_error())


def _key(vk: int, flags: int = 0, scan: int = 0) -> INPUT:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
    return inp


# --- буфер обмена --------------------------------------------------------
def _open_clipboard(retries: int = 10, delay: float = 0.03) -> bool:
    """Открывает буфер обмена с повторами.

    Буфер — общий ресурс: его может держать другое приложение (проводник,
    браузер, мессенджер). Без повторов вставка иногда молча не срабатывает.
    """
    for attempt in range(retries):
        if user32.OpenClipboard(None):
            return True
        if attempt < retries - 1:
            time.sleep(delay)
    return False


def get_clipboard_text() -> str:
    if not _open_clipboard():
        return ""
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.c_wchar_p(ptr).value or ""
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def set_clipboard_text(text: str) -> bool:
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    if not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            kernel32.GlobalFree(handle)
            return False
        try:
            ctypes.memmove(ptr, data, size)
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        return True
    finally:
        user32.CloseClipboard()


# --- отправка нажатий ----------------------------------------------------
def send_ctrl_v(delay_ms: int = 0) -> None:
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)
    _send(
        [
            _key(VK_CONTROL),
            _key(VK_V),
            _key(VK_V, KEYEVENTF_KEYUP),
            _key(VK_CONTROL, KEYEVENTF_KEYUP),
        ]
    )


def type_text_unicode(text: str, per_char_pause: float = 0.002) -> None:
    """Печатает текст «как клавиатура», не трогая буфер обмена."""
    for ch in text:
        if ch == "\n":
            _send([_key(VK_RETURN), _key(VK_RETURN, KEYEVENTF_KEYUP)])
        else:
            _send([_key(0, KEYEVENTF_UNICODE, ord(ch)), _key(0, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, ord(ch))])
        if per_char_pause:
            time.sleep(per_char_pause)


def get_foreground_title() -> str:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def insert_text(
    text: str,
    auto_paste: bool = True,
    restore_clipboard: bool = True,
    paste_delay_ms: int = 60,
    mode: str = "paste",
) -> tuple[bool, str]:
    """Кладёт текст в буфер и (если нужно) доставляет его в активное окно.

    mode="paste" — Ctrl+V (быстро, так же как в оригинале на macOS);
    mode="type"  — посимвольная печать Unicode (медленнее, но работает в
    приложениях, которые игнорируют Ctrl+V).

    Возвращает (доставили ли, текст или описание ошибки).
    """
    if not text:
        return False, ""

    previous = get_clipboard_text() if restore_clipboard else ""
    if not set_clipboard_text(text):
        return False, "не удалось записать в буфер обмена"

    if not auto_paste:
        return False, text

    if mode == "type":
        type_text_unicode(text)
        return True, text

    if restore_clipboard:
        # Буфер возвращаем уже после того, как Ctrl+V доехал до приложения.
        def _restore() -> None:
            time.sleep(max(0.3, paste_delay_ms / 1000.0 + 0.25))
            set_clipboard_text(previous)

        threading.Thread(target=_restore, daemon=True).start()

    send_ctrl_v(paste_delay_ms)
    return True, text
