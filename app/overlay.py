"""Экранный индикатор диктовки и резервное окно управления.

Индикатор — компактная тёмная «пилюля» с золотой рамкой внизу экрана: красный
кружок записи и волна уровня микрофона. Слов во время записи нет — говорит
анимация; текст появляется только в коротком сообщении с результатом.
"""

from __future__ import annotations

import math
import tkinter as tk
from collections import deque
from tkinter import font as tkfont

from . import theme
from .theme import DIM, GOLD, GOLD_DIM, GREEN, RED, TEXT

PANEL = "#121214"
HEIGHT = 44
WIDTH_COMPACT = 208
WIDTH_MAX = 420
WAVE_POINTS = 15
PAD_LEFT = 34


class Overlay:
    def __init__(self, root: tk.Tk, show: bool = True) -> None:
        self.root = root
        self.enabled = show

        self._hide_job: str | None = None
        self._tick_job: str | None = None
        self._state = "idle"
        self._message = ""
        self._note = ""
        self._color = GOLD
        self._levels: deque[float] = deque([0.0] * WAVE_POINTS, maxlen=WAVE_POINTS)
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
        self.win.configure(bg=PANEL)

        self.font = tkfont.Font(family=theme.FAMILY, size=10)
        self.canvas = tk.Canvas(
            self.win, width=self._width, height=HEIGHT, bg=PANEL,
            highlightthickness=0, bd=0,
        )
        self.canvas.pack()

    # --- геометрия --------------------------------------------------------
    def _place(self) -> None:
        self.win.update_idletasks()
        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        x = (screen_w - self._width) // 2
        y = screen_h - HEIGHT - 76
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
        theme.round_rect(c, 1, 1, w - 1, HEIGHT - 1, 13,
                         fill=PANEL, outline=GOLD_DIM)

        if self._state == "recording":
            pulse = 4.5 + 2.0 * self._levels[-1]
            c.create_oval(19 - pulse, cy - pulse, 19 + pulse, cy + pulse,
                          fill=RED, outline="")
            self._draw_wave(c, cy, list(self._levels), GOLD)
        elif self._state == "working":
            c.create_oval(15, cy - 4.5, 24, cy + 4.5, fill=GOLD, outline="")
            wave = [0.18 + 0.82 * abs(math.sin(self._phase * 1.5 + i * 0.5))
                    for i in range(WAVE_POINTS)]
            self._draw_wave(c, cy, wave, GOLD)
            if self._note:
                c.create_text(w - 14, cy, text=self._note, anchor="e",
                              fill=DIM, font=self.font)
        else:
            if self._state == "done":
                c.create_oval(13, cy - 7, 27, cy + 7, fill=GREEN, outline="")
                c.create_line(17, cy, 20, cy + 3.5, 24, cy - 3.5,
                              fill=PANEL, width=2, capstyle="round", joinstyle="round")
            else:
                c.create_oval(15, cy - 6, 27, cy + 6, fill=self._color, outline="")
            if self._message:
                c.create_text(PAD_LEFT + 4, cy, text=self._message, anchor="w",
                              fill=TEXT, font=self.font)

    def _draw_wave(self, c: tk.Canvas, cy: float, values: list[float],
                   color: str) -> None:
        span = self._width - PAD_LEFT - 16
        step = span / (WAVE_POINTS - 1)
        coords: list[float] = []
        for index, value in enumerate(values):
            level = max(0.0, min(1.0, value))
            offset = (2.0 + 13.0 * level) * (1 if index % 2 else -1)
            coords.extend((PAD_LEFT + index * step, cy + offset))
        c.create_line(*coords, fill=color, width=2, smooth=True,
                      capstyle="round", joinstyle="round")

    # --- анимация ---------------------------------------------------------
    def _tick(self) -> None:
        self._tick_job = None
        if not self.enabled or self._state not in ("recording", "working"):
            return
        self._phase += 0.12
        if self._state == "recording":
            # волна опадает, если уровень не поднимается
            self._levels.append(self._levels[-1] * 0.8)
        self._draw()
        self._tick_job = self.root.after(60, self._tick)

    def _ensure_animation(self) -> None:
        if self._tick_job is None and self.enabled:
            self._tick_job = self.root.after(60, self._tick)

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
        """Уровень 0..1 — попадает в волну индикатора."""
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
        self._message_state("done", text, GREEN, hide_after_ms)

    def notice(self, title: str, subtitle: str = "", color: str = DIM,
               hide_after_ms: int = 2200) -> None:
        self._message_state("notice", title, color, hide_after_ms)

    def error(self, message: str, hide_after_ms: int = 4000) -> None:
        self._message_state("error", message, RED, hide_after_ms)

    def _message_state(self, state: str, text: str, color: str,
                       hide_after_ms: int) -> None:
        if not self.enabled:
            return
        self._stop_animation()
        self._state = state
        self._message = self._fit(text)
        self._color = color
        self._resize(PAD_LEFT + 22 + int(self.font.measure(self._message)))
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
    """Резервное окно управления — если значок в трее не появился."""

    def __init__(self, root: tk.Tk, on_toggle, on_settings, on_quit) -> None:
        self.win = tk.Toplevel(root)
        self.win.title("Pantela Voice")
        self.win.attributes("-topmost", True)
        self.win.resizable(False, False)
        self.win.configure(bg=theme.BG)

        card = theme.Card(self.win, 320, 258, radius=16, padding=20, bg=theme.BG)
        card.pack(padx=12, pady=12)
        body = card.body

        head = tk.Frame(body, bg=theme.PANEL)
        head.pack(fill="x", pady=(0, 4))
        theme.icon_label(head, theme.ICONS["mic"], bg=theme.PANEL).pack(side="left")
        theme.label(head, "Pantela Voice", size=13, weight="bold",
                    bg=theme.PANEL).pack(side="left", padx=(8, 0))

        theme.label(body, "Значок в трее не появился.\nУправление — этими кнопками.",
                    fg=theme.DIM, size=9, bg=theme.PANEL,
                    justify="left").pack(anchor="w", pady=(0, 14))

        self.toggle_btn = theme.RoundButton(
            body, "Начать диктовку", glyph=theme.ICONS["mic"], command=on_toggle,
            width=278, height=38, accent=True,
        )
        self.toggle_btn.pack(pady=3)
        theme.RoundButton(body, "Настройки", glyph=theme.ICONS["settings"],
                          command=on_settings, width=278, height=36).pack(pady=3)
        theme.RoundButton(body, "Выход", glyph=theme.ICONS["power"], command=on_quit,
                          width=278, height=36).pack(pady=3)

    def set_recording(self, recording: bool) -> None:
        try:
            self.toggle_btn.set_text(
                "Остановить диктовку" if recording else "Начать диктовку"
            )
        except tk.TclError:
            pass

    def destroy(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass
