"""Оформление интерфейса: цвета, шрифты, иконки и рисованные элементы.

Тёмная тема с тёплым золотым акцентом. Скруглённые углы, карточки и кнопки
рисуются на Canvas: ttk такого не умеет, а сторонние темы тянуть не хочется.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

# --- цвета ---------------------------------------------------------------
BG = "#0b0b0d"
PANEL = "#141417"
PANEL_HI = "#1b1b1f"
PANEL_SOFT = "#101013"
BORDER = "#26262c"
BORDER_HI = "#34343c"

TEXT = "#f2f2f4"
DIM = "#9b9ba4"
MUTE = "#6d6d76"

GOLD = "#e5aa3d"
GOLD_BRIGHT = "#f5c45c"
GOLD_DIM = "#7a5f21"
GOLD_SOFT = "#221b0d"

GREEN = "#7cc47f"
BLUE = "#6f9dfb"
TEAL = "#3aa8a0"
RED = "#e5544b"

FAMILY = "Segoe UI"
FAMILY_SEMI = "Segoe UI Semibold"
ICON_FAMILY = "Segoe MDL2 Assets"

# --- иконки (Segoe MDL2 Assets) -----------------------------------------
ICONS = {
    "home": "\uE80F",
    "chart": "\uE9D9",
    "settings": "\uE713",
    "help": "\uE897",
    "mic": "\uE720",
    "copy": "\uE8C8",
    "delete": "\uE74D",
    "refresh": "\uE72C",
    "clock": "\uE823",
    "calendar": "\uE787",
    "bolt": "\uE945",
    "list": "\uE8FD",
    "words": "\uE8D2",
    "doc": "\uE8A5",
    "note": "\uE70B",
    "folder": "\uE8B7",
    "keyboard": "\uE765",
    "check": "\uE73E",
    "target": "\uE8BD",
    "star": "\uE734",
    "page": "\uE7C3",
    "search": "\uE721",
    "power": "\uE7E8",
    "chevron": "\uE76C",
    "info": "\uE946",
    "edit": "\uE70F",
    "spark": "\uE9A9",
    "lock": "\uE72E",
    "volume": "\uE767",
    "play": "\uE768",
}


def font(size: int = 10, weight: str = "normal") -> tuple:
    return (FAMILY, size, weight)


def semi(size: int = 10) -> tuple:
    return (FAMILY_SEMI, size)


def icon_font(size: int = 12) -> tuple:
    return (ICON_FAMILY, size)


_icon_cache: dict[tuple, tkfont.Font] = {}


def measure(root: tk.Misc, text: str, f: tuple) -> int:
    key = (f, root)
    if key not in _icon_cache:
        _icon_cache[key] = tkfont.Font(root=root, family=f[0], size=f[1],
                                       weight=f[2] if len(f) > 2 else "normal")
    return _icon_cache[key].measure(text)


# --- рисование -----------------------------------------------------------
def round_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
               r: float, **kwargs) -> int:
    """Скруглённый прямоугольник (canvas не умеет их из коробки)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class Card(tk.Frame):
    """Карточка со скруглёнными углами и внутренней областью для содержимого."""

    def __init__(self, master: tk.Misc, width: int, height: int, *,
                 radius: int = 14, padding: int = 16, fill: str = PANEL,
                 border: str = BORDER, bg: str = BG) -> None:
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0)
        self.pack_propagate(False)
        self.grid_propagate(False)
        self.canvas = tk.Canvas(self, width=width, height=height, bg=bg,
                                highlightthickness=0, bd=0)
        self.canvas.place(x=0, y=0)
        round_rect(self.canvas, 1, 1, width - 1, height - 1, radius,
                   fill=fill, outline=border)
        self.body = tk.Frame(self, bg=fill)
        self.body.place(x=padding, y=padding,
                        width=width - 2 * padding, height=height - 2 * padding)


class RoundButton(tk.Canvas):
    """Кнопка со скруглёнными углами, иконкой и подписью."""

    def __init__(self, master: tk.Misc, text: str = "", glyph: str = "",
                 command=None, width: int = 120, height: int = 36,  # noqa: ANN001
                 fill: str = PANEL_HI, hover: str = BORDER_HI, fg: str = TEXT,
                 border: str = BORDER, radius: int = 10, size: int = 10,
                 icon_color: str | None = None, bg: str = BG,
                 accent: bool = False) -> None:
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0)
        self.command = command
        self._cw, self._ch = width, height
        self._fill, self._hover = fill, hover
        self._fg = GOLD if accent else fg
        self._border = GOLD_DIM if accent else border
        self._radius = radius
        self._text = text
        self._glyph = glyph
        self._size = size
        self._icon_color = icon_color or self._fg
        self._state = "normal"
        self._draw()
        self.bind("<Enter>", lambda _e: self._set_state("hover"))
        self.bind("<Leave>", lambda _e: self._set_state("normal"))
        self.bind("<Button-1>", lambda _e: self._set_state("press"))
        self.bind("<ButtonRelease-1>", self._release)

    def _set_state(self, state: str) -> None:
        self._state = state
        self._draw()

    def _release(self, event) -> None:  # noqa: ANN001
        inside = 0 <= event.x <= self._cw and 0 <= event.y <= self._ch
        self._set_state("hover" if inside else "normal")
        if inside and self.command is not None:
            self.command()

    def _draw(self) -> None:
        self.delete("all")
        fill = {"normal": self._fill, "hover": self._hover, "press": self._hover}[self._state]
        round_rect(self, 1, 1, self._cw - 1, self._ch - 1, self._radius,
                   fill=fill, outline=self._border)
        text_font = font(self._size)
        glyph_w = 0
        if self._glyph:
            glyph_font = icon_font(self._size + 3)
            glyph_w = tkfont.Font(root=self, family=ICON_FAMILY,
                                  size=self._size + 3).measure(self._glyph)
        label_w = tkfont.Font(root=self, family=FAMILY, size=self._size).measure(self._text)
        gap = 7 if (self._glyph and self._text) else 0
        total = glyph_w + gap + label_w
        x = (self._cw - total) / 2
        if self._glyph:
            self.create_text(x, self._ch / 2, text=self._glyph, anchor="w",
                             fill=self._icon_color, font=glyph_font)
            x += glyph_w + gap
        if self._text:
            self.create_text(x, self._ch / 2, text=self._text, anchor="w",
                             fill=self._fg, font=text_font)

    def set_text(self, text: str) -> None:
        self._text = text
        self._draw()


class NavBar(tk.Canvas):
    """Верхнее меню: скруглённые вкладки, активная подсвечена золотом."""

    def __init__(self, master: tk.Misc, items: list[tuple[str, str, str]],
                 on_select, active: str, width: int = 1280, height: int = 64,  # noqa: ANN001
                 bg: str = BG) -> None:
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0)
        self.items = items
        self.on_select = on_select
        self.active = active
        self._cw, self._ch = width, height
        self._boxes: list[tuple[float, float, str]] = []
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._motion)
        self._hover: str | None = None
        self._draw()

    def _metrics(self) -> list[tuple[float, float, str, int]]:
        result = []
        gap = 8
        pad_x = 18
        widths = []
        for key, glyph, label in self.items:
            text_w = tkfont.Font(root=self, family=FAMILY, size=10).measure(label)
            widths.append(pad_x * 2 + 22 + 8 + text_w)
        total = sum(widths) + gap * (len(widths) - 1)
        x = (self._cw - total) / 2
        for (key, _glyph, _label), w in zip(self.items, widths):
            result.append((x, w, key, 0))
            x += w + gap
        return result

    def _draw(self) -> None:
        self.delete("all")
        self._boxes = []
        top = (self._ch - 40) / 2
        for x, w, key, _ in self._metrics():
            active = key == self.active
            hover = key == self._hover and not active
            fill = GOLD_SOFT if active else (PANEL_HI if hover else PANEL)
            border = GOLD_DIM if active else BORDER
            round_rect(self, x, top, x + w, top + 40, 12, fill=fill, outline=border)
            glyph = next(g for k, g, _ in self.items if k == key)
            label = next(t for k, _, t in self.items if k == key)
            color = GOLD if active else (TEXT if hover else DIM)
            self.create_text(x + 18, self._ch / 2, text=glyph, anchor="w",
                             fill=color, font=icon_font(12))
            self.create_text(x + 40, self._ch / 2, text=label, anchor="w",
                             fill=color, font=font(10))
            self._boxes.append((x, x + w, key))

    def _motion(self, event) -> None:  # noqa: ANN001
        found = None
        for x1, x2, key in self._boxes:
            if x1 <= event.x <= x2:
                found = key
                break
        if found != self._hover:
            self._hover = found
            self.configure(cursor="hand2" if found else "")
            self._draw()

    def _click(self, event) -> None:  # noqa: ANN001
        for x1, x2, key in self._boxes:
            if x1 <= event.x <= x2:
                self.select(key)
                return

    def select(self, key: str) -> None:
        if key == self.active:
            return
        self.active = key
        self._draw()
        self.on_select(key)


class ProgressBar(tk.Canvas):
    def __init__(self, master: tk.Misc, width: int, height: int = 6,
                 fill: str = GOLD, track: str = "#22222a", bg: str = BG) -> None:
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0)
        self._cw, self._ch = width, height
        self._fill, self._track = fill, track
        self._value = 0.0
        self._draw()

    def set(self, value: float) -> None:
        self._value = max(0.0, min(1.0, value))
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        round_rect(self, 0, 0, self._cw, self._ch, self._ch / 2, fill=self._track, outline="")
        if self._value > 0:
            round_rect(self, 0, 0, max(self._ch, self._cw * self._value), self._ch,
                       self._ch / 2, fill=self._fill, outline="")


class LevelMeter(tk.Canvas):
    """Полоска уровня микрофона: столбики, как на индикаторе диктовки."""

    def __init__(self, master: tk.Misc, width: int = 380, height: int = 34,
                 bars: int = 28, bg: str = PANEL) -> None:
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0)
        self._cw, self._ch, self._bars = width, height, bars
        self._values = [0.0] * bars
        self._draw()

    def push(self, value: float) -> None:
        self._values.append(max(0.0, min(1.0, value)))
        self._values.pop(0)
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        step = self._cw / self._bars
        for index, value in enumerate(self._values):
            half = 2 + (self._ch / 2 - 3) * value
            x = index * step + step / 2
            color = GOLD if value > 0.45 else (GOLD_DIM if value > 0.12 else BORDER_HI)
            self.create_line(x, self._ch / 2 - half, x, self._ch / 2 + half,
                             width=3, capstyle="round", fill=color)


def label(master: tk.Misc, text: str, *, fg: str = TEXT, size: int = 10,
          weight: str = "normal", bg: str = PANEL, **kwargs) -> tk.Label:
    return tk.Label(master, text=text, fg=fg, bg=bg,
                    font=(FAMILY_SEMI if weight == "bold" else FAMILY, size),
                    **kwargs)


def icon_label(master: tk.Misc, glyph: str, *, fg: str = GOLD, size: int = 14,
               bg: str = PANEL, **kwargs) -> tk.Label:
    return tk.Label(master, text=glyph, fg=fg, bg=bg, font=icon_font(size), **kwargs)


class DarkCheck(tk.Frame):
    """Флажок в тёмной теме: ttk-чекбоксы выбиваются из оформления."""

    def __init__(self, master: tk.Misc, text: str, value: bool = False,
                 command=None, bg: str = PANEL, width: int = 0) -> None:  # noqa: ANN001
        super().__init__(master, bg=bg)
        self.command = command
        self.value = value
        self.canvas = tk.Canvas(self, width=18, height=18, bg=bg,
                                highlightthickness=0, bd=0)
        self.canvas.pack(side="left")
        self.label = tk.Label(self, text=text, fg=DIM, bg=bg, font=font(9),
                              anchor="w", justify="left")
        self.label.pack(side="left", padx=(8, 0))
        for widget in (self.canvas, self.label):
            widget.bind("<Button-1>", self._toggle)
            widget.configure(cursor="hand2")
        self._draw()

    def _toggle(self, _event=None) -> None:
        self.value = not self.value
        self._draw()
        if self.command:
            self.command()

    def set(self, value: bool) -> None:
        self.value = value
        self._draw()

    def _draw(self) -> None:
        self.canvas.delete("all")
        if self.value:
            round_rect(self.canvas, 0, 0, 17, 17, 5, fill=GOLD, outline="")
            self.canvas.create_text(9, 9, text=ICONS["check"], fill="#1a1406",
                                    font=icon_font(8))
            self.label.configure(fg=TEXT)
        else:
            round_rect(self.canvas, 0, 0, 17, 17, 5, fill=PANEL_SOFT, outline=BORDER_HI)
            self.label.configure(fg=DIM)


class DarkRadio(tk.Frame):
    """Переключатель в тёмной теме."""

    def __init__(self, master: tk.Misc, text: str, value: str, variable: list,
                 command=None, bg: str = PANEL) -> None:  # noqa: ANN001
        super().__init__(master, bg=bg)
        self.text = text
        self.value = value
        self.variable = variable
        self.command = command
        self.canvas = tk.Canvas(self, width=18, height=18, bg=bg,
                                highlightthickness=0, bd=0)
        self.canvas.pack(side="left")
        self.label = tk.Label(self, text=text, fg=DIM, bg=bg, font=font(9), anchor="w")
        self.label.pack(side="left", padx=(8, 0))
        for widget in (self.canvas, self.label):
            widget.bind("<Button-1>", self._select)
            widget.configure(cursor="hand2")
        self._draw()

    @property
    def selected(self) -> bool:
        return self.variable[0] == self.value

    def _select(self, _event=None) -> None:
        self.variable[0] = self.value
        if self.command:
            self.command()
        self.master.event_generate("<<RadioChanged>>")

    def refresh(self) -> None:
        self._draw()

    def _draw(self) -> None:
        self.canvas.delete("all")
        if self.selected:
            self.canvas.create_oval(1, 1, 17, 17, outline=GOLD, width=2)
            self.canvas.create_oval(6, 6, 12, 12, fill=GOLD, outline="")
            self.label.configure(fg=TEXT)
        else:
            self.canvas.create_oval(1, 1, 17, 17, outline=BORDER_HI, width=2)
            self.label.configure(fg=DIM)
