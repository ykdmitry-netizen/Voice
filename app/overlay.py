"""Экранный индикатор диктовки и резервное окно управления.

Индикатор — компактная «пилюля» внизу экрана: цветная точка состояния и
столбики уровня микрофона. Никаких надписей вроде «Запись…»: во время записи
говорит сама анимация, а текст появляется только в коротком сообщении с
результатом.
"""

from __future__ import annotations

import math
import tkinter as tk
from collections import deque
from tkinter import font as tkfont
from tkinter import ttk

BG = "#12141a"
BORDER = "#272c38"
TEXT = "#e9ecf1"
DIM = "#8b93a1"
ACCENT = "#4c8dff"
REC = "#ff4b4b"
OK = "#35d07f"
BAR_IDLE = "#333a49"

HEIGHT = 44
WIDTH_COMPACT = 186
WIDTH_MAX = 400
BAR_COUNT = 14
PAD_LEFT = 30


def round_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
               r: float, **kwargs) -> int:
    """Скруглённый прямоугольник: canvas не умеет их из коробки."""
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class Overlay:
    def __init__(self, root: tk.Tk, show: bool = True) -> None:
        self.root = root
        self.enabled = show

        self._hide_job: str | None = None
        self._tick_job: str | None = None
        self._state = "idle"
        self._message = ""
        self._note = ""
        self._color = ACCENT
        self._levels: deque[float] = deque([0.0] * BAR_COUNT, maxlen=BAR_COUNT)
        self._phase = 0.0
        self._width = WIDTH_COMPACT

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-alpha", 0.97)
        except tk.TclError:
            pass
        self.win.configure(bg=BG)

        self.font = tkfont.Font(family="Segoe UI", size=10)
        self.canvas = tk.Canvas(
            self.win, width=self._width, height=HEIGHT, bg=BG, highlightthickness=0
        )
        self.canvas.pack()

    # --- геометрия --------------------------------------------------------
    def _place(self) -> None:
        self.win.update_idletasks()
        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        x = (screen_w - self._width) // 2
        y = screen_h - HEIGHT - 72
        self.win.geometry(f"{self._width}x{HEIGHT}+{x}+{y}")

    def _resize(self, width: int) -> None:
        width = max(WIDTH_COMPACT, min(WIDTH_MAX, width))
        if width != self._width:
            self._width = width
            self.canvas.configure(width=width)
            self._place()

    # --- отрисовка --------------------------------------------------------
    def _draw(self) -> None:
        c = self.canvas
        c.delete("all")
        w = self._width
        cy = HEIGHT / 2
        round_rect(c, 1, 1, w - 1, HEIGHT - 1, 13, fill=BG, outline=BORDER)

        if self._state == "recording":
            pulse = 5.0 + 2.0 * self._levels[-1]
            c.create_oval(20 - pulse, cy - pulse, 20 + pulse, cy + pulse,
                          fill=REC, outline="")
            self._draw_bars(c, cy, lambda i: self._levels[i])
        elif self._state == "working":
            c.create_oval(15, cy - 5, 25, cy + 5, fill=ACCENT, outline="")
            self._draw_bars(
                c, cy,
                lambda i: 0.15 + 0.85 * abs(math.sin(self._phase * 1.6 + i * 0.55)),
            )
            if self._note:
                c.create_text(w - 14, cy, text=self._note, anchor="e",
                              fill=DIM, font=self.font)
        else:
            if self._state == "done":
                c.create_oval(14, cy - 7, 28, cy + 7, fill=OK, outline="")
                c.create_line(18, cy, 21, cy + 3.5, 25, cy - 3.5,
                              fill=BG, width=2, capstyle="round", joinstyle="round")
            else:
                c.create_oval(16, cy - 6, 28, cy + 6, fill=self._color, outline="")
            if self._message:
                c.create_text(PAD_LEFT + 6, cy, text=self._message, anchor="w",
                              fill=TEXT, font=self.font)
            elif self._state == "working":
                pass

    def _draw_bars(self, c: tk.Canvas, cy: float, value) -> None:  # noqa: ANN001
        span = self._width - PAD_LEFT - 16
        step = span / (BAR_COUNT - 1)
        for i in range(BAR_COUNT):
            level = max(0.0, min(1.0, value(i)))
            half = 2.5 + 13.0 * level
            x = PAD_LEFT + i * step
            c.create_line(x, cy - half, x, cy + half, width=3.0,
                          capstyle="round",
                          fill=ACCENT if level > 0.12 else BAR_IDLE)

    # --- анимация ---------------------------------------------------------
    def _tick(self) -> None:
        self._tick_job = None
        if not self.enabled or self._state not in ("recording", "working"):
            return
        self._phase += 0.12
        if self._state == "recording":
            # столбики плавно опадают, если уровень не поднимается
            self._levels.append(self._levels[-1] * 0.82)
        self._draw()
        self._tick_job = self.root.after(50, self._tick)

    def _ensure_animation(self) -> None:
        if self._tick_job is None and self.enabled:
            self._tick_job = self.root.after(50, self._tick)

    def _stop_animation(self) -> None:
        if self._tick_job is not None:
            try:
                self.root.after_cancel(self._tick_job)
            except tk.TclError:
                pass
            self._tick_job = None

    # --- показ ------------------------------------------------------------
    def _show_window(self) -> None:
        if not self.enabled:
            return
        if self._hide_job is not None:
            try:
                self.root.after_cancel(self._hide_job)
            except tk.TclError:
                pass
            self._hide_job = None
        self._place()
        self.win.deiconify()
        self.win.lift()
        self.win.attributes("-topmost", True)

    def _fit(self, text: str) -> str:
        limit = WIDTH_MAX - PAD_LEFT - 24
        if self.font.measure(text) <= limit:
            return text
        while text and self.font.measure(text + "…") > limit:
            text = text[:-1]
        return text + "…"

    def set_level(self, level: float) -> None:
        """Уровень 0..1 — попадает в столбики индикатора."""
        self._levels.append(max(0.0, min(1.0, level)))

    def recording(self, level: float = 0.0) -> None:
        if not self.enabled:
            return
        self._resize(WIDTH_COMPACT)
        self._state = "recording"
        self._message = ""
        self._note = ""
        self._levels.append(max(0.0, min(1.0, level)))
        self._show_window()
        self._draw()
        self._ensure_animation()

    def working(self, subtitle: str = "") -> None:
        if not self.enabled:
            return
        self._note = subtitle
        self._resize(WIDTH_COMPACT + (56 if subtitle else 0))
        self._state = "working"
        self._message = ""
        self._show_window()
        self._draw()
        self._ensure_animation()

    def done(self, text: str, hide_after_ms: int = 1600) -> None:
        self._message_state("done", text, OK, hide_after_ms)

    def notice(self, title: str, subtitle: str = "", color: str = DIM,
               hide_after_ms: int = 2200) -> None:
        self._message_state("notice", title, color, hide_after_ms)

    def error(self, message: str, hide_after_ms: int = 4000) -> None:
        self._message_state("error", message, REC, hide_after_ms)

    def _message_state(self, state: str, text: str, color: str,
                       hide_after_ms: int) -> None:
        if not self.enabled:
            return
        self._stop_animation()
        self._state = state
        self._message = self._fit(text)
        self._color = color
        self._resize(PAD_LEFT + 24 + int(self.font.measure(self._message)))
        self._show_window()
        self._draw()
        self._schedule_hide(hide_after_ms)

    def _schedule_hide(self, ms: int) -> None:
        if self._hide_job is not None:
            try:
                self.root.after_cancel(self._hide_job)
            except tk.TclError:
                pass
        self._hide_job = self.root.after(ms, self.hide)

    def hide(self) -> None:
        self._hide_job = None
        self._stop_animation()
        self._state = "idle"
        try:
            self.win.withdraw()
        except tk.TclError:
            pass

    def destroy(self) -> None:
        self._stop_animation()
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
    """Резервное окно управления — на случай, если значок в трее не появился."""

    def __init__(self, root: tk.Tk, on_toggle, on_settings, on_quit) -> None:
        self.win = tk.Toplevel(root)
        self.win.title("Pantela Voice")
        self.win.attributes("-topmost", True)
        self.win.resizable(False, False)
        self.win.configure(bg="#f4f6fa")

        outer = ttk.Frame(self.win, padding=(18, 16, 18, 16))
        outer.pack(fill="both", expand=True)

        head = ttk.Frame(outer)
        head.pack(fill="x", pady=(0, 10))
        ttk.Label(head, text="Pantela Voice",
                  font=("Segoe UI Semibold", 13)).pack(side="left")
        ttk.Label(head, text="диктовка", foreground="#6b7280").pack(side="left", padx=(8, 0))

        ttk.Label(
            outer,
            text="Значок в трее не появился — управление этими кнопками.",
            foreground="#4b5563",
            wraplength=250,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))

        self.toggle_btn = ttk.Button(outer, text="Начать диктовку", width=26, command=on_toggle)
        self.toggle_btn.pack(fill="x", pady=3)
        ttk.Button(outer, text="Настройки…", width=26, command=on_settings).pack(fill="x", pady=3)
        ttk.Separator(outer).pack(fill="x", pady=(12, 10))
        ttk.Button(outer, text="Выход", width=26, command=on_quit).pack(fill="x")

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
