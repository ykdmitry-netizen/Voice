"""Значок в трее — напрямую через Win32 (Shell_NotifyIcon), без сторонних библиотек.

Своя реализация даёт главное: `Shell_NotifyIconW` возвращает результат, поэтому
видно, действительно ли значок появился. Раньше это приходилось угадывать по
внутреннему флагу pystray, и приложение зря показывало резервное окно.

Значок и меню живут в своём потоке со своим циклом сообщений; пункты меню
только складывают события в очередь приложения.
"""

from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_APP = 0x8000
WM_DESTROY = 0x0002
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_QUIT = 0x0012

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_GRAYED = 0x00000001
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
WS_POPUP = 0x80000000

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_byte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


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
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
user32.LoadImageW.argtypes = [
    wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
user32.LoadImageW.restype = wintypes.HANDLE
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR]
user32.AppendMenuW.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, wintypes.HWND, wintypes.LPVOID,
]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.RegisterClassExW.restype = wintypes.ATOM
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]


def make_icon_file(path: str) -> bool:
    """Рисует значок микрофона и сохраняет его как .ico."""
    try:
        from PIL import Image, ImageDraw

        size = 64
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((2, 2, size - 2, size - 2), radius=15,
                               fill=(76, 141, 255, 255))
        draw.rounded_rectangle((26, 13, 38, 35), radius=6, fill=(255, 255, 255, 255))
        draw.arc((17, 20, 47, 46), start=0, end=180, fill=(255, 255, 255, 255), width=4)
        draw.line((32, 45, 32, 52), fill=(255, 255, 255, 255), width=4)
        image.save(path, sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (48, 48), (64, 64)])
        return True
    except Exception:  # noqa: BLE001 - значок не критичен для работы
        return False


class TrayIcon:
    """Значок в трее с контекстным меню.

    items_provider() -> список (подпись, callable) или ("-", None) для
    разделителя; вызывается при каждом открытии меню, поэтому подписи могут
    меняться.
    """

    def __init__(self, tooltip: str, items_provider, on_default=None,
                 icon_path: str = "", log=None) -> None:
        self.tooltip = tooltip[:127]
        self.items_provider = items_provider
        self.on_default = on_default
        self.icon_path = icon_path
        self.log = log or (lambda *_: None)

        self.callback_message = WM_APP + 1
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._hwnd = None
        self._hicon = None
        self._proc = WNDPROC(self._wndproc)   # держим ссылку от сборщика
        self._class_name = f"PantelaVoiceTray{os.getpid()}"
        self.available = False

    # --- окно и сообщения -------------------------------------------------
    def _wndproc(self, hwnd, msg, wparam, lparam):  # noqa: ANN001
        try:
            if msg == self.callback_message:
                event = lparam & 0xFFFF
                if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    if self.on_default:
                        self.on_default()
                elif event == WM_RBUTTONUP:
                    self._show_menu()
            elif msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
        except Exception as exc:  # noqa: BLE001 - оконная процедура не должна падать
            self.log(f"tray wndproc error: {exc!r}")
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _create_window(self) -> bool:
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = self._class_name
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            self.log(f"RegisterClassExW failed: {ctypes.get_last_error()}")
            return False
        self._hwnd = user32.CreateWindowExW(
            0, self._class_name, "PantelaVoice", WS_POPUP,
            0, 0, 0, 0, None, None, hinst, None,
        )
        return bool(self._hwnd)

    # --- значок -----------------------------------------------------------
    def _add_icon(self) -> bool:
        if self.icon_path and os.path.exists(self.icon_path):
            self._hicon = user32.LoadImageW(
                None, self.icon_path, IMAGE_ICON, 0, 0,
                LR_LOADFROMFILE | LR_DEFAULTSIZE,
            )
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = self.callback_message
        nid.hIcon = self._hicon
        nid.szTip = self.tooltip
        if shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            return True
        self.log(f"Shell_NotifyIcon(NIM_ADD) failed: {ctypes.get_last_error()}")
        return False

    def notify(self, title: str, text: str) -> None:
        """Всплывающее уведомление возле значка."""
        if not self.available:
            return
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_INFO
        nid.szInfoTitle = title[:63]
        nid.szInfo = text[:255]
        nid.dwInfoFlags = 0x00000001  # NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    # --- меню -------------------------------------------------------------
    def _show_menu(self) -> None:
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        actions: dict[int, object] = {}
        try:
            for index, (label, callback) in enumerate(self.items_provider(), start=1):
                if label == "-":
                    user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
                    continue
                flags = MF_STRING if callback else MF_STRING | MF_GRAYED
                user32.AppendMenuW(menu, flags, index, label)
                if callback:
                    actions[index] = callback

            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            # без SetForegroundWindow меню не закроется по клику мимо
            user32.SetForegroundWindow(self._hwnd)
            command = user32.TrackPopupMenu(
                menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                point.x, point.y, 0, self._hwnd, None,
            )
        finally:
            user32.DestroyMenu(menu)

        action = actions.get(command)
        if action is not None:
            try:
                action()
            except Exception as exc:  # noqa: BLE001
                self.log(f"tray action error: {exc!r}")

    # --- жизненный цикл ---------------------------------------------------
    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        if not self._create_window():
            return
        if not self._add_icon():
            user32.DestroyWindow(self._hwnd)
            return
        self.available = True
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        if self._hicon:
            user32.DestroyIcon(self._hicon)
            self._hicon = None
        self.available = False

    def start(self, timeout: float = 3.0) -> bool:
        self._thread = threading.Thread(target=self._run, name="tray", daemon=True)
        self._thread.start()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.available:
                return True
            if not self._thread.is_alive():
                return False
            time.sleep(0.05)
        return self.available

    def stop(self) -> None:
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None
        self._thread_id = 0
