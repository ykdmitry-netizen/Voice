"""Экранный индикатор диктовки: маленькая панель поверх всех окон.

Панель безрамочная, всегда сверху, живёт в главном потоке Tk. Показывает
состояние («Запись…», «Распознаю…», «Готово») и уровень микрофона.
"""

from __future__ import annotations

import tkinter as tk

BG = "#14161a"
FG = "#e8eaed"
DIM = "#8b929c"
ACCENT = "#4c8dff"
REC = "#ff4d4f"
OK = "#31c48d"

WIDTH = 340
HEIGHT = 68


class Overlay:
    def __init__(self, root: tk.Tk, show: bool = True) -> None:
        self.root = root
        self.enabled = show
        self._hide_job: str | None = None

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-alpha", 0.96)
        except tk.TclError:
            pass
        self.win.configure(bg=BG)

        self.canvas = tk.Canvas(
            self.win, width=WIDTH, height=HEIGHT, bg=BG, highlightthickness=0
        )
        self.canvas.pack()

        self.dot = self.canvas.create_oval(18, 22, 34, 38, fill=ACCENT, outline="")
        self.title = self.canvas.create_text(
            46, 24, text="Готово", anchor="w", fill=FG, font=("Segoe UI", 11, "bold")
        )
        self.subtitle = self.canvas.create_text(
            46, 44, text="", anchor="w", fill=DIM, font=("Segoe UI", 9)
        )
        self.bar_bg = self.canvas.create_rectangle(
            18, 54, WIDTH - 18, 60, fill="#242833", outline=""
        )
        self.bar = self.canvas.create_rectangle(18, 54, 18, 60, fill=ACCENT, outline="")

        self._place()

    # --- расположение ----------------------------------------------------
    def _place(self) -> None:
        self.win.update_idletasks()
        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        x = (screen_w - WIDTH) // 2
        y = screen_h - HEIGHT - 72
        self.win.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

    # --- показ -----------------------------------------------------------
    def _show_window(self) -> None:
        if not self.enabled:
            return
        if self._hide_job is not None:
            self.root.after_cancel(self._hide_job)
            self._hide_job = None
        self._place()
        self.win.deiconify()
        self.win.lift()
        self.win.attributes("-topmost", True)

    def set(self, title: str, subtitle: str = "", color: str = ACCENT,
            level: float = 0.0) -> None:
        if not self.enabled:
            return
        self._show_window()
        self.canvas.itemconfigure(self.dot, fill=color)
        self.canvas.itemconfigure(self.title, text=title)
        self.canvas.itemconfigure(self.subtitle, text=subtitle)
        self.set_level(level, color)

    def set_level(self, level: float, color: str = ACCENT) -> None:
        if not self.enabled:
            return
        level = max(0.0, min(1.0, level))
        width = 18 + (WIDTH - 36) * level
        self.canvas.coords(self.bar, 18, 54, width, 60)
        self.canvas.itemconfigure(self.bar, fill=color)

    def recording(self, level: float = 0.0) -> None:
        self.set("Запись…", "Отпустите клавиши, чтобы распознать", REC, level)

    def working(self, subtitle: str = "") -> None:
        self.set("Распознаю…", subtitle, ACCENT, 1.0)

    def done(self, text: str, hide_after_ms: int = 1400) -> None:
        preview = text if len(text) <= 46 else text[:45] + "…"
        self.set("Готово", preview, OK, 1.0)
        self._schedule_hide(hide_after_ms)

    def notice(self, title: str, subtitle: str = "", color: str = DIM,
               hide_after_ms: int = 2200) -> None:
        self.set(title, subtitle, color, 0.0)
        self._schedule_hide(hide_after_ms)

    def error(self, message: str, hide_after_ms: int = 4000) -> None:
        self.notice("Ошибка", message, REC, hide_after_ms)

    def _schedule_hide(self, ms: int) -> None:
        if self._hide_job is not None:
            self.root.after_cancel(self._hide_job)
        self._hide_job = self.root.after(ms, self.hide)

    def hide(self) -> None:
        self._hide_job = None
        try:
            self.win.withdraw()
        except tk.TclError:
            pass

    def destroy(self) -> None:
        if self._hide_job is not None:
            try:
                self.root.after_cancel(self._hide_job)
            except tk.TclError:
                pass
            self._hide_job = None
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class ControlWindow:
    """Резервное окно управления: показывается, если значок в трее недоступен
    (например, из-за ограничений безопасности Windows)."""

    def __init__(self, root: tk.Tk, on_toggle, on_settings, on_quit) -> None:
        self.win = tk.Toplevel(root)
        self.win.title("Pantela Voice")
        self.win.attributes("-topmost", True)
        self.win.resizable(False, False)
        self.win.geometry("+60+60")

        frame = tk.Frame(self.win, padx=14, pady=12)
        frame.pack()

        tk.Label(
            frame,
            text="Значок в трее недоступен.\nУправление — этими кнопками.",
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        self.toggle_btn = tk.Button(frame, text="Начать диктовку", width=24, command=on_toggle)
        self.toggle_btn.pack(fill="x", pady=2)
        tk.Button(frame, text="Настройки…", width=24, command=on_settings).pack(fill="x", pady=2)
        tk.Button(frame, text="Выход", width=24, command=on_quit).pack(fill="x", pady=(10, 0))

    def set_recording(self, recording: bool) -> None:
        try:
            self.toggle_btn.configure(
                text="Остановить диктовку" if recording else "Начать диктовку"
            )
        except tk.TclError:
            pass

    def destroy(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass
