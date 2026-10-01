"""Главное окно: Главная, Сводка, Настройки, Как пользоваться.

Тёмная тема с золотым акцентом. Окно фиксированного размера — так вся
раскладка предсказуема, а рисованные карточки и кнопки не «плывут».
"""

from __future__ import annotations

import datetime as dt
import os
import threading
import tkinter as tk
from tkinter import font as tkfont

from . import asr, audio, history as history_mod, models, stats, theme
from .config import format_hotkey
from .theme import BG, BORDER, BORDER_HI, DIM, GOLD, GOLD_DIM, GOLD_SOFT
from .theme import GREEN, MUTE, PANEL, PANEL_HI, PANEL_SOFT, RED, TEAL, TEXT, BLUE

WINDOW_W = 1280
WINDOW_H = 820
NAV_H = 64
PAD = 24
CONTENT_Y = NAV_H + 8
CONTENT_W = WINDOW_W - 2 * PAD
CONTENT_H = WINDOW_H - CONTENT_Y - 16

MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря")

PRESET_KEYS = [("Right Ctrl", "right ctrl"), ("CapsLock", "capslock"),
               ("Ctrl + Пробел", "ctrl+space")]


def bind_wheel(widget: tk.Misc, canvas: tk.Canvas) -> None:
    """Колесо мыши должно прокручивать список, даже когда курсор над элементом."""
    def scroll(event) -> None:  # noqa: ANN001
        canvas.yview_scroll(-1 * (event.delta // 120), "units")

    widget.bind("<MouseWheel>", scroll, add="+")
    for child in widget.winfo_children():
        bind_wheel(child, canvas)


class DarkSelect(tk.Canvas):
    """Выпадающий список в тёмной теме: ttk-комбобокс сюда не вписывается."""

    def __init__(self, master: tk.Misc, values: list[str], value: str,
                 command=None, width: int = 240, height: int = 36,  # noqa: ANN001
                 bg: str = PANEL) -> None:
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0)
        self.values = values
        self.value = value
        self.command = command
        self._cw, self._ch = width, height
        self._open = False
        self._popup: tk.Toplevel | None = None
        self.bind("<Button-1>", lambda _e: self.toggle())
        self.configure(cursor="hand2")
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        theme.round_rect(self, 1, 1, self._cw - 1, self._ch - 1, 10,
                         fill=PANEL_SOFT, outline=BORDER_HI if self._open else BORDER)
        self.create_text(14, self._ch / 2, text=self.value, anchor="w",
                         fill=TEXT, font=theme.font(10))
        self.create_text(self._cw - 16, self._ch / 2, text=theme.ICONS["chevron"],
                         anchor="e", fill=DIM, font=theme.icon_font(9))

    def set_values(self, values: list[str], value: str | None = None) -> None:
        self.values = values
        if value is not None and value in values:
            self.value = value
        elif self.value not in values and values:
            self.value = values[0]
        self._draw()

    def set(self, value: str) -> None:
        self.value = value
        self._draw()

    def toggle(self) -> None:
        if self._popup is not None:
            self._close()
        else:
            self._open_menu()

    def _open_menu(self) -> None:
        self._open = True
        self._draw()
        top = tk.Toplevel(self)
        self._popup = top
        top.overrideredirect(True)
        top.configure(bg=BORDER)
        top.attributes("-topmost", True)
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self._ch + 2
        height = min(len(self.values) * 30 + 8, 260)
        top.geometry(f"{self._cw}x{height}+{x}+{y}")
        inner = tk.Frame(top, bg=PANEL_HI)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        for item in self.values:
            row = tk.Label(inner, text=item, anchor="w", padx=12, pady=5,
                           bg=PANEL_HI, fg=GOLD if item == self.value else TEXT,
                           font=theme.font(10))
            row.pack(fill="x")
            row.configure(cursor="hand2")
            row.bind("<Button-1>", lambda _e, value=item: self._choose(value))
        top.bind("<FocusOut>", lambda _e: self._close())
        top.focus_set()

    def _choose(self, value: str) -> None:
        self.value = value
        self._close()
        if self.command:
            self.command(value)

    def _close(self) -> None:
        self._open = False
        if self._popup is not None:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass
            self._popup = None
        self._draw()


class Tab:
    key = ""
    title = ""

    def __init__(self, window: "MainWindow") -> None:
        self.window = window
        self.app = window.app
        self.settings = window.app.settings
        self.history = window.history
        self.frame = tk.Frame(window.win, bg=BG)
        self.frame.place(x=PAD, y=CONTENT_Y, width=CONTENT_W, height=CONTENT_H)
        self.build()

    def build(self) -> None:
        raise NotImplementedError

    def refresh(self) -> None:
        pass

    def on_show(self) -> None:
        pass


class MainWindow:
    def __init__(self, app) -> None:  # noqa: ANN001
        self.app = app
        self.history = app.history

        self.win = tk.Toplevel(app.root)
        self.win.title("Pantela Voice")
        self.win.configure(bg=BG)
        self.win.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.win.minsize(WINDOW_W, WINDOW_H)
        self.win.protocol("WM_DELETE_WINDOW", self.hide)

        self.nav = theme.NavBar(
            self.win,
            [("home", theme.ICONS["home"], "Главная"),
             ("summary", theme.ICONS["chart"], "Сводка"),
             ("settings", theme.ICONS["settings"], "Настройки"),
             ("help", theme.ICONS["help"], "Как пользоваться")],
            on_select=self.show_tab,
            active="home",
            width=WINDOW_W, height=NAV_H,
        )
        self.nav.place(x=0, y=0)

        theme.label(self.win, "Pantela Voice", size=13, weight="bold", bg=BG
                    ).place(x=PAD, y=20)
        theme.icon_label(self.win, theme.ICONS["mic"], size=15, bg=BG
                         ).place(x=PAD + 122, y=19)

        self.tabs: dict[str, Tab] = {
            "home": HomeTab(self),
            "summary": SummaryTab(self),
            "settings": SettingsTab(self),
            "help": HelpTab(self),
        }
        self.current = "home"
        self.show_tab("home")

    # --- управление окном -------------------------------------------------
    @property
    def alive(self) -> bool:
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def show(self, tab: str | None = None) -> None:
        if tab:
            self.nav.select(tab)
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        self.refresh_all()

    def hide(self) -> None:
        self.win.withdraw()

    def toggle(self) -> None:
        if self.win.state() == "withdrawn":
            self.show()
        else:
            self.hide()

    def show_tab(self, key: str) -> None:
        if key not in self.tabs:
            return
        self.current = key
        self.tabs[key].frame.tkraise()
        self.tabs[key].on_show()
        self.nav.active = key
        self.nav._draw()

    # --- обновление данных ------------------------------------------------
    def refresh_all(self) -> None:
        for tab in self.tabs.values():
            tab.refresh()

    def set_status(self, text: str, color: str = DIM) -> None:
        tab = self.tabs.get("home")
        if isinstance(tab, HomeTab):
            tab.set_status(text, color)

    def set_recording(self, recording: bool) -> None:
        tab = self.tabs.get("home")
        if isinstance(tab, HomeTab):
            tab.set_recording(recording)

    def push_level(self, level: float) -> None:
        tab = self.tabs.get("settings")
        if isinstance(tab, SettingsTab):
            tab.push_level(level)

    def destroy(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass


# --------------------------------------------------------------------------
#  Вспомогательные блоки
# --------------------------------------------------------------------------
def stat_card(parent: tk.Misc, x: int, y: int, width: int, height: int,
              glyph: str, glyph_color: str, title: str, subtitle: str) -> tuple:
    card = theme.Card(parent, width, height, radius=14, padding=16, bg=BG)
    card.place(x=x, y=y)
    body = card.body

    head = tk.Frame(body, bg=PANEL)
    head.pack(fill="x")
    theme.label(head, title, fg=DIM, size=9, bg=PANEL).pack(side="left")
    badge = tk.Canvas(head, width=30, height=30, bg=PANEL, highlightthickness=0, bd=0)
    badge.pack(side="right")
    theme.round_rect(badge, 0, 0, 29, 29, 9, fill=PANEL_HI, outline="")
    badge.create_text(15, 15, text=glyph, fill=glyph_color, font=theme.icon_font(12))

    value = theme.label(body, "0", size=25, weight="bold", bg=PANEL)
    value.pack(anchor="w", pady=(4, 0))
    theme.label(body, subtitle, fg=MUTE, size=8, bg=PANEL).pack(anchor="w")
    return card, value


# --------------------------------------------------------------------------
#  Главная
# --------------------------------------------------------------------------
class HomeTab(Tab):
    key = "home"
    title = "Главная"

    def build(self) -> None:
        f = self.frame
        self._current = None

        # --- история слева ------------------------------------------------
        theme.label(f, "ИСТОРИЯ", fg=MUTE, size=8, weight="bold", bg=BG
                    ).place(x=2, y=0)
        self.refresh_btn = theme.RoundButton(
            f, glyph=theme.ICONS["refresh"], command=self._reload_history,
            width=32, height=26, radius=8, size=9,
        )
        self.refresh_btn.place(x=268, y=-4)

        self.history_card = theme.Card(f, 300, 626, radius=14, padding=10, bg=BG)
        self.history_card.place(x=0, y=30)
        self.list_canvas = tk.Canvas(self.history_card.body, bg=PANEL,
                                     highlightthickness=0, bd=0, width=278, height=604)
        self.list_canvas.pack(side="left", fill="both", expand=True)
        self.list_inner = tk.Frame(self.list_canvas, bg=PANEL)
        self.list_window = self.list_canvas.create_window(
            (0, 0), window=self.list_inner, anchor="nw", width=276
        )
        self.list_inner.bind(
            "<Configure>",
            lambda _e: self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all")),
        )
        self.list_canvas.bind("<MouseWheel>", self._wheel)

        # --- цель недели --------------------------------------------------
        self.goal_label = theme.label(f, "", fg=DIM, size=9, bg=BG)
        self.goal_label.place(x=2, y=676)
        self.goal_bar = theme.ProgressBar(f, 300, 6, bg=BG)
        self.goal_bar.place(x=0, y=700)

        # --- карточки статистики справа -----------------------------------
        right = 316
        card_w, gap = 217, 16
        self.stat_values: dict[str, tk.Label] = {}
        definitions = [
            ("words", theme.ICONS["list"], BLUE, "Слов всего", "распознано голосом"),
            ("minutes", theme.ICONS["clock"], BLUE, "Минут наговорено", "вместо печати"),
            ("days", theme.ICONS["calendar"], GOLD, "Дней с приложением", "по истории"),
            ("saved", theme.ICONS["bolt"], TEAL, "Сэкономлено", "времени на печати"),
        ]
        for index, (key, glyph, color, title, subtitle) in enumerate(definitions):
            _card, value = stat_card(f, right + index * (card_w + gap), 0,
                                     card_w, 108, glyph, color, title, subtitle)
            self.stat_values[key] = value

        # --- распознанный текст -------------------------------------------
        self.text_card = theme.Card(f, 916, 470, radius=14, padding=20, bg=BG)
        self.text_card.place(x=right, y=124)
        body = self.text_card.body

        head = tk.Frame(body, bg=PANEL)
        head.pack(fill="x")
        theme.label(head, "Распознанный текст", size=12, weight="bold",
                    bg=PANEL).pack(side="left")
        self.delete_btn = theme.RoundButton(
            head, "Удалить", glyph=theme.ICONS["delete"], command=self._delete_current,
            width=112, height=32, size=9, bg=PANEL,
        )
        self.delete_btn.pack(side="right")
        self.copy_btn = theme.RoundButton(
            head, "Копировать", glyph=theme.ICONS["copy"], command=self._copy_current,
            width=132, height=32, size=9, bg=PANEL,
        )
        self.copy_btn.pack(side="right", padx=8)

        self.text_area = tk.Text(
            body, bg=PANEL_SOFT, fg=TEXT, insertbackground=GOLD, relief="flat",
            font=theme.font(11), wrap="word", padx=14, pady=12,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER,
            selectbackground=GOLD_DIM, selectforeground=TEXT,
        )
        self.scroll = tk.Scrollbar(body, command=self.text_area.yview, width=10,
                                   troughcolor=PANEL, bg=PANEL_HI, bd=0,
                                   relief="flat", activebackground=GOLD_DIM)
        self.text_area.configure(yscrollcommand=self.scroll.set)

        self.empty = tk.Frame(body, bg=PANEL)
        icon = tk.Canvas(self.empty, width=64, height=64, bg=PANEL,
                         highlightthickness=0, bd=0)
        icon.pack(pady=(70, 12))
        theme.round_rect(icon, 2, 2, 61, 61, 18, fill=PANEL_HI, outline=BORDER_HI)
        icon.create_text(32, 32, text=theme.ICONS["mic"], fill=GOLD,
                         font=theme.icon_font(26))
        theme.label(self.empty, "Наговори — и текст появится здесь", size=13,
                    weight="bold", bg=PANEL).pack()
        theme.label(self.empty,
                    "Зажми клавишу — говори — отпусти.\nТекст можно скопировать или удалить.",
                    fg=DIM, size=9, bg=PANEL, justify="center").pack(pady=(8, 0))

        # --- кнопка микрофона и статус ------------------------------------
        self.mic_btn = tk.Canvas(f, width=84, height=84, bg=BG,
                                 highlightthickness=0, bd=0)
        self.mic_btn.place(x=right + (916 - 84) // 2, y=604)
        self.mic_btn.configure(cursor="hand2")
        self.mic_btn.bind("<Button-1>", lambda _e: self.app.toggle_dictation())
        self._mic_recording = False
        self._draw_mic()

        self.status = theme.label(f, "Готово к диктовке", fg=MUTE, size=9, bg=BG)
        self.status.place(x=right, y=698, width=916, anchor="nw")

        self.refresh()

    # --- отрисовка кнопки микрофона ---------------------------------------
    def _draw_mic(self) -> None:
        c = self.mic_btn
        c.delete("all")
        recording = self._mic_recording
        outer = RED if recording else GOLD
        c.create_oval(4, 4, 80, 80, fill=PANEL_HI, outline=GOLD_DIM)
        c.create_oval(12, 12, 72, 72, fill=outer, outline="")
        c.create_text(42, 42, text=theme.ICONS["mic"], fill="#141005",
                      font=theme.icon_font(24))

    def set_recording(self, recording: bool) -> None:
        self._mic_recording = recording
        self._draw_mic()

    def set_status(self, text: str, color: str = DIM) -> None:
        self.status.configure(text=text, fg=color)

    # --- данные -----------------------------------------------------------
    def current_entry(self):
        return getattr(self, "_current", None)

    def refresh(self) -> None:
        summary = stats.summarize(self.history.entries())
        self.stat_values["words"].configure(text=f"{summary.words:,}".replace(",", " "))
        self.stat_values["minutes"].configure(text=f"{summary.seconds / 60:.0f}")
        self.stat_values["days"].configure(text=f"{summary.days}")
        self.stat_values["saved"].configure(text=stats.human_minutes(summary.saved_minutes))

        goal = max(1, int(self.settings.weekly_goal_words or 2000))
        left = max(0, goal - summary.week_words)
        self.goal_label.configure(
            text=f"Осталось {left:,} слов до цели недели".replace(",", " ")
        )
        self.goal_bar.set(summary.week_words / goal)

        # список истории перестраивается только когда окно видно: при диктовке
        # в другое приложение окно скрыто, и тратить на это время незачем
        if self.window.win.state() != "withdrawn":
            self._rebuild_history()
            self._show_current()

    def on_show(self) -> None:
        self.refresh()

    def _reload_history(self) -> None:
        self.history.load()
        self.refresh()

    def _wheel(self, event) -> None:  # noqa: ANN001
        self.list_canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def _rebuild_history(self) -> None:
        for child in self.list_inner.winfo_children():
            child.destroy()

        entries = self.history.entries()
        if not entries:
            theme.label(self.list_inner, "Пока пусто.\nНаговорите первую фразу.",
                        fg=MUTE, size=9, bg=PANEL, justify="left"
                        ).pack(anchor="w", padx=12, pady=16)
            bind_wheel(self.list_inner, self.list_canvas)
            return

        last_date = None
        for entry in entries[:120]:
            when = dt.datetime.fromtimestamp(entry.ts)
            day = when.date()
            if day != last_date:
                last_date = day
                today = dt.date.today()
                if day == today:
                    header = "СЕГОДНЯ"
                elif day == today - dt.timedelta(days=1):
                    header = "ВЧЕРА"
                else:
                    header = f"{day.day} {MONTHS[day.month - 1].upper()}"
                theme.label(self.list_inner, header, fg=MUTE, size=8, weight="bold",
                            bg=PANEL).pack(anchor="w", padx=10, pady=(12, 4))

            row = tk.Frame(self.list_inner, bg=PANEL_HI)
            row.pack(fill="x", padx=4, pady=2)
            inner = tk.Frame(row, bg=PANEL_HI)
            inner.pack(fill="x", padx=10, pady=8)

            top = tk.Frame(inner, bg=PANEL_HI)
            top.pack(fill="x")
            theme.icon_label(top, theme.ICONS["page"], fg=DIM, size=11,
                             bg=PANEL_HI).pack(side="left")
            theme.label(top, f"{when:%H:%M}", fg=MUTE, size=8, bg=PANEL_HI
                        ).pack(side="left", padx=(8, 0))
            theme.label(top, f"{entry.words} сл.", fg=GOLD, size=8,
                        bg=PANEL_HI).pack(side="right")

            preview = entry.text.strip().replace("\n", " ")
            if len(preview) > 90:
                preview = preview[:89] + "…"
            theme.label(inner, preview, fg=TEXT, size=9, bg=PANEL_HI,
                        wraplength=236, justify="left").pack(anchor="w", pady=(4, 0))

            for widget in (row, inner, top):
                widget.bind("<Button-1>", lambda _e, e=entry: self._select(e))
            for widget in row.winfo_children() + inner.winfo_children() + top.winfo_children():
                widget.bind("<Button-1>", lambda _e, e=entry: self._select(e))

        bind_wheel(self.list_inner, self.list_canvas)

    def _select(self, entry) -> None:  # noqa: ANN001
        self._current = entry
        self._show_current()

    def _show_current(self) -> None:
        # запись могла быть удалена или история очищена — не показываем призрак
        if self._current is not None and not self.history.contains(self._current):
            self._current = None
        entry = self.current_entry() or self.history.last
        self._current = entry
        if entry is None:
            self.text_area.pack_forget()
            self.scroll.pack_forget()
            self.empty.pack(fill="both", expand=True)
            return
        self.empty.pack_forget()
        self.text_area.pack(side="left", fill="both", expand=True, pady=(12, 0))
        self.scroll.pack(side="right", fill="y", pady=(12, 0))
        self.text_area.configure(state="normal")
        self.text_area.delete("1.0", "end")
        self.text_area.insert("1.0", entry.text)
        self.text_area.configure(state="disabled")

    # --- действия ---------------------------------------------------------
    def _copy_current(self) -> None:
        entry = self.current_entry()
        if entry is None:
            self.set_status("Нечего копировать", MUTE)
            return
        ok = self.app.copy_to_clipboard(entry.text)
        self.set_status("Текст скопирован" if ok else "Не удалось скопировать",
                        GREEN if ok else RED)

    def _delete_current(self) -> None:
        entry = self.current_entry()
        if entry is None:
            return
        self.history.remove(entry)
        self._current = None
        self.set_status("Запись удалена", MUTE)
        self.refresh()


# --------------------------------------------------------------------------
#  Сводка
# --------------------------------------------------------------------------
class SummaryTab(Tab):
    key = "summary"
    title = "Сводка"

    def build(self) -> None:
        f = self.frame
        card_w, gap = 217, 16
        self.stat_values: dict[str, tk.Label] = {}
        definitions = [
            ("words", theme.ICONS["list"], BLUE, "Слов всего", "распознано голосом"),
            ("minutes", theme.ICONS["clock"], BLUE, "Минут наговорено", "вместо печати"),
            ("days", theme.ICONS["calendar"], GOLD, "Дней с приложением", "по истории"),
            ("saved", theme.ICONS["bolt"], TEAL, "Сэкономлено", "времени на печати"),
        ]
        for index, (key, glyph, color, title, subtitle) in enumerate(definitions):
            _card, value = stat_card(f, index * (card_w + gap), 0, card_w, 108,
                                     glyph, color, title, subtitle)
            self.stat_values[key] = value

        self.cat_card = theme.Card(f, 560, 250, radius=14, padding=18, bg=BG)
        self.cat_card.place(x=0, y=124)
        theme.label(self.cat_card.body, "Категории", size=12, weight="bold",
                    bg=PANEL).pack(anchor="w", pady=(0, 10))
        self.cat_canvas = tk.Canvas(self.cat_card.body, bg=PANEL, width=524,
                                    height=180, highlightthickness=0, bd=0)
        self.cat_canvas.pack(anchor="w")

        self.tag_card = theme.Card(f, 340, 250, radius=14, padding=18, bg=BG)
        self.tag_card.place(x=576, y=124)
        theme.label(self.tag_card.body, "Частые слова", size=12, weight="bold",
                    bg=PANEL).pack(anchor="w", pady=(0, 10))
        self.tag_canvas = tk.Canvas(self.tag_card.body, bg=PANEL, width=304,
                                    height=180, highlightthickness=0, bd=0)
        self.tag_canvas.pack(anchor="w")

        self.act_card = theme.Card(f, 916, 358, radius=14, padding=18, bg=BG)
        self.act_card.place(x=0, y=390)
        head = tk.Frame(self.act_card.body, bg=PANEL)
        head.pack(fill="x")
        theme.label(head, "Активность за 28 дней", size=12, weight="bold",
                    bg=PANEL).pack(side="left")
        legend = tk.Frame(head, bg=PANEL)
        legend.pack(side="right")
        theme.label(legend, "меньше", fg=MUTE, size=8, bg=PANEL).pack(side="left")
        for color in ("#1e1e24", "#4a3a16", "#8a6a25", GOLD):
            box = tk.Canvas(legend, width=12, height=12, bg=PANEL,
                            highlightthickness=0, bd=0)
            box.pack(side="left", padx=3)
            theme.round_rect(box, 0, 0, 11, 11, 3, fill=color, outline="")
        theme.label(legend, "больше", fg=MUTE, size=8, bg=PANEL).pack(side="left", padx=(3, 0))
        theme.label(self.act_card.body, "Чем ярче клетка — тем больше наговорено в этот день",
                    fg=MUTE, size=8, bg=PANEL).pack(anchor="w", pady=(2, 12))
        self.act_canvas = tk.Canvas(self.act_card.body, bg=PANEL, width=880,
                                    height=210, highlightthickness=0, bd=0)
        self.act_canvas.pack(anchor="w")

        self.refresh()

    def refresh(self) -> None:
        summary = stats.summarize(self.history.entries())
        self.stat_values["words"].configure(text=f"{summary.words:,}".replace(",", " "))
        self.stat_values["minutes"].configure(text=f"{summary.seconds / 60:.0f}")
        self.stat_values["days"].configure(text=f"{summary.days}")
        self.stat_values["saved"].configure(text=stats.human_minutes(summary.saved_minutes))

        # категории
        c = self.cat_canvas
        c.delete("all")
        if not summary.categories:
            c.create_text(0, 12, text="Пока нет данных", anchor="nw", fill=MUTE,
                          font=theme.font(9))
        else:
            y = 0
            for name, _count, percent in summary.categories[:5]:
                color = stats.CATEGORY_COLORS.get(name, MUTE)
                theme.icon_label_canvas = None  # noqa: F841 (для читаемости)
                c.create_text(0, y + 8, text="●", anchor="w", fill=color,
                              font=theme.font(12))
                c.create_text(18, y + 8, text=name, anchor="w", fill=TEXT,
                              font=theme.font(10))
                c.create_text(500, y + 8, text=f"{percent:.0f}%", anchor="e",
                              fill=DIM, font=theme.font(9))
                theme.round_rect(c, 18, y + 24, 500, y + 30, 3,
                                 fill="#22222a", outline="")
                theme.round_rect(c, 18, y + 24, 18 + 482 * percent / 100, y + 30, 3,
                                 fill=color, outline="")
                y += 44

        # частые слова
        t = self.tag_canvas
        t.delete("all")
        if not summary.frequent:
            t.create_text(0, 12, text="Пока нет данных", anchor="nw", fill=MUTE,
                          font=theme.font(9))
        else:
            x, y, row_h = 0, 0, 30
            measure_font = tkfont.Font(root=t, family=theme.FAMILY, size=9)
            for word, _count in summary.frequent:
                w = measure_font.measure(word) + 26
                if x + w > 304:
                    x, y = 0, y + row_h
                if y > 150:
                    break
                theme.round_rect(t, x, y, x + w, y + 24, 12, fill=PANEL_HI,
                                 outline=BORDER)
                t.create_text(x + w / 2, y + 12, text=word, fill=TEXT,
                              font=theme.font(9))
                x += w + 8

        # активность: 28 дней одной лентой слева (раньше) направо (сегодня)
        a = self.act_canvas
        a.delete("all")
        cells = summary.activity
        if cells:
            size, gap = 28, 3
            total = len(cells) * size + (len(cells) - 1) * gap
            x0 = (880 - total) / 2
            max_words = max((w for _d, w in cells), default=0) or 1
            for index, (day, words) in enumerate(cells):
                x = x0 + index * (size + gap)
                ratio = words / max_words
                if words == 0:
                    color = "#17171c"
                elif ratio < 0.34:
                    color = "#4a3a16"
                elif ratio < 0.67:
                    color = "#8a6a25"
                else:
                    color = GOLD
                theme.round_rect(a, x, 10, x + size, 10 + size, 7, fill=color,
                                 outline=BORDER if words == 0 else "")
            a.create_text(x0, 10 + size + 10, text=f"{cells[0][0]:%d.%m}",
                          anchor="nw", fill=MUTE, font=theme.font(8))
            a.create_text(x0 + total, 10 + size + 10, text="сегодня",
                          anchor="ne", fill=MUTE, font=theme.font(8))
            a.create_text(x0, 10 + size + 34,
                          text="лента: каждый столбик — один день, ярче — больше наговорено",
                          anchor="nw", fill="#4b4b53", font=theme.font(8))


# --------------------------------------------------------------------------
#  Настройки
# --------------------------------------------------------------------------
class SettingsTab(Tab):
    key = "settings"
    title = "Настройки"

    def build(self) -> None:
        f = self.frame
        self._engine_choice = [self.settings.engine]
        self._mode_choice = [self.settings.insert_mode]
        self._lang_choice = [self.settings.language]

        # --- распознавание ------------------------------------------------
        card = theme.Card(f, 440, 250, radius=14, padding=18, bg=BG)
        card.place(x=0, y=0)
        body = card.body
        head = tk.Frame(body, bg=PANEL)
        head.pack(fill="x")
        theme.icon_label(head, theme.ICONS["spark"], bg=PANEL).pack(side="left")
        theme.label(head, "Распознавание", size=12, weight="bold",
                    bg=PANEL).pack(side="left", padx=(8, 0))
        theme.label(body, "Локально — полная приватность, офлайн. Облака в приложении нет.",
                    fg=MUTE, size=8, bg=PANEL, wraplength=390, justify="left"
                    ).pack(anchor="w", pady=(4, 10))

        self.engine_radios = []
        for name, label_text in asr.available_engines():
            radio = theme.DarkRadio(body, label_text, name, self._engine_choice,
                                    command=self._engine_changed, bg=PANEL)
            radio.pack(anchor="w", pady=3)
            self.engine_radios.append(radio)
        body.bind("<<RadioChanged>>", lambda _e: self._refresh_radios(self.engine_radios))

        row = tk.Frame(body, bg=PANEL)
        row.pack(fill="x", pady=(10, 0))
        theme.label(row, "Whisper, размер", fg=DIM, size=9, bg=PANEL).pack(side="left")
        self.whisper_select = DarkSelect(
            row, ["tiny", "base", "small", "medium", "large-v3-turbo"],
            self.settings.whisper_model, command=lambda _v: self._engine_changed(),
            width=150, height=30, bg=PANEL,
        )
        self.whisper_select.pack(side="right")

        self.model_label = theme.label(body, "", fg=MUTE, size=8, bg=PANEL,
                                       wraplength=390, justify="left")
        self.model_label.pack(anchor="w", pady=(8, 0))

        # --- микрофон -----------------------------------------------------
        card = theme.Card(f, 460, 250, radius=14, padding=18, bg=BG)
        card.place(x=456, y=0)
        body = card.body
        head = tk.Frame(body, bg=PANEL)
        head.pack(fill="x")
        theme.icon_label(head, theme.ICONS["mic"], bg=PANEL).pack(side="left")
        theme.label(head, "Микрофон", size=12, weight="bold",
                    bg=PANEL).pack(side="left", padx=(8, 0))
        theme.label(body, "Выберите устройство. Ниже — уровень звука: говорите, "
                          "полоска должна двигаться.",
                    fg=MUTE, size=8, bg=PANEL, wraplength=410, justify="left"
                    ).pack(anchor="w", pady=(4, 10))

        self.device_select = DarkSelect(body, ["по умолчанию"], 
                                        self.settings.input_device or "по умолчанию",
                                        width=410, height=34, bg=PANEL)
        self.device_select.pack(anchor="w")
        self.level = theme.LevelMeter(body, 410, 34, bars=32, bg=PANEL)
        self.level.pack(anchor="w", pady=(12, 10))
        theme.RoundButton(body, "Проверить микрофон и модель", glyph=theme.ICONS["play"],
                          command=self._test, width=250, height=32, size=9,
                          bg=PANEL).pack(anchor="w")
        self.test_label = theme.label(body, "", fg=DIM, size=8, bg=PANEL,
                                      wraplength=410, justify="left")
        self.test_label.pack(anchor="w", pady=(6, 0))

        # --- горячая клавиша ----------------------------------------------
        card = theme.Card(f, 440, 232, radius=14, padding=18, bg=BG)
        card.place(x=0, y=266)
        body = card.body
        head = tk.Frame(body, bg=PANEL)
        head.pack(fill="x")
        theme.icon_label(head, theme.ICONS["keyboard"], bg=PANEL).pack(side="left")
        theme.label(head, "Горячая клавиша", size=12, weight="bold",
                    bg=PANEL).pack(side="left", padx=(8, 0))

        self.hotkey_entry = tk.Entry(
            body, bg=PANEL_SOFT, fg=TEXT, insertbackground=GOLD, relief="flat",
            font=theme.font(11), justify="center", highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=GOLD_DIM,
        )
        self.hotkey_entry.insert(0, self.settings.hotkey)
        self.hotkey_entry.pack(fill="x", pady=(12, 8), ipady=6)

        presets = tk.Frame(body, bg=PANEL)
        presets.pack(fill="x")
        for label_text, value in PRESET_KEYS:
            theme.RoundButton(presets, label_text,
                              command=lambda v=value: self._set_hotkey(v),
                              width=118, height=30, size=9, bg=PANEL
                              ).pack(side="left", padx=(0, 8))
        theme.RoundButton(body, "Записать своё сочетание…", glyph=theme.ICONS["edit"],
                          command=self._capture_hotkey, width=250, height=30, size=9,
                          bg=PANEL).pack(anchor="w", pady=(8, 0))
        theme.label(body, "Зажмите клавишу и говорите — текст вставится в активное поле.",
                    fg=MUTE, size=8, bg=PANEL, wraplength=390, justify="left"
                    ).pack(anchor="w", pady=(8, 0))

        # --- вставка ------------------------------------------------------
        card = theme.Card(f, 460, 232, radius=14, padding=18, bg=BG)
        card.place(x=456, y=266)
        body = card.body
        head = tk.Frame(body, bg=PANEL)
        head.pack(fill="x")
        theme.icon_label(head, theme.ICONS["doc"], bg=PANEL).pack(side="left")
        theme.label(head, "Вставка", size=12, weight="bold",
                    bg=PANEL).pack(side="left", padx=(8, 0))

        self.paste_check = theme.DarkCheck(body, "Вставлять текст в активное окно",
                                           self.settings.auto_paste, bg=PANEL)
        self.paste_check.pack(anchor="w", pady=(12, 4))
        self.copy_check = theme.DarkCheck(body, "Копировать в буфер обмена",
                                          self.settings.copy_to_clipboard, bg=PANEL)
        self.copy_check.pack(anchor="w", pady=2)
        self.restore_check = theme.DarkCheck(body, "Возвращать прежнее содержимое буфера",
                                             self.settings.restore_clipboard, bg=PANEL)
        self.restore_check.pack(anchor="w", pady=2)

        theme.label(body, "Способ доставки", fg=DIM, size=9, bg=PANEL
                    ).pack(anchor="w", pady=(8, 0))
        self.mode_radios = []
        for value, label_text in (("paste", "Ctrl+V — быстро"),
                                  ("type", "печатать посимвольно — совместимо")):
            radio = theme.DarkRadio(body, label_text, value, self._mode_choice,
                                    bg=PANEL)
            radio.pack(anchor="w", pady=1)
            self.mode_radios.append(radio)
        body.bind("<<RadioChanged>>", lambda _e: self._refresh_radios(self.mode_radios))

        # --- словарь ------------------------------------------------------
        card = theme.Card(f, 616, 232, radius=14, padding=18, bg=BG)
        card.place(x=0, y=508)
        body = card.body
        theme.label(body, "Словарь замен", size=12, weight="bold",
                    bg=PANEL).pack(anchor="w")
        theme.label(body, "По одной замене в строке: что_распознано=на_что_заменить",
                    fg=MUTE, size=8, bg=PANEL).pack(anchor="w", pady=(2, 8))
        self.dict_text = tk.Text(
            body, bg=PANEL_SOFT, fg=TEXT, insertbackground=GOLD, relief="flat",
            font=theme.font(10), wrap="none", height=6, padx=10, pady=8,
            highlightthickness=1, highlightbackground=BORDER,
        )
        self.dict_text.pack(fill="both", expand=True)
        self.dict_text.insert("1.0", "\n".join(f"{a}={b}" for a, b in self.settings.dictionary))

        # --- прочее -------------------------------------------------------
        card = theme.Card(f, 284, 232, radius=14, padding=18, bg=BG)
        card.place(x=632, y=508)
        body = card.body
        theme.label(body, "Прочее", size=12, weight="bold", bg=PANEL).pack(anchor="w")
        self.overlay_check = theme.DarkCheck(body, "Показывать индикатор диктовки",
                                             self.settings.show_overlay, bg=PANEL)
        self.overlay_check.pack(anchor="w", pady=(10, 4))
        self.sound_check = theme.DarkCheck(body, "Звуковой сигнал", self.settings.play_sound,
                                           bg=PANEL)
        self.sound_check.pack(anchor="w", pady=4)
        self.autostart_check = theme.DarkCheck(body, "Запускать при входе в Windows",
                                               self.settings.autostart, bg=PANEL)
        self.autostart_check.pack(anchor="w", pady=4)

        theme.label(body, "Цель недели, слов", fg=DIM, size=9, bg=PANEL
                    ).pack(anchor="w", pady=(8, 2))
        self.goal_entry = tk.Entry(body, bg=PANEL_SOFT, fg=TEXT, insertbackground=GOLD,
                                   relief="flat", font=theme.font(10), justify="center",
                                   highlightthickness=1, highlightbackground=BORDER)
        self.goal_entry.insert(0, str(self.settings.weekly_goal_words))
        self.goal_entry.pack(fill="x", ipady=3)

        self._build_actions()
        self.refresh()

    # --- правая колонка: сохранение и служебные действия ------------------
    def _build_actions(self) -> None:
        f = self.frame
        theme.RoundButton(f, "Сохранить настройки", glyph=theme.ICONS["check"],
                          command=self.save, width=276, height=42, accent=True,
                          bg=BG).place(x=956, y=0)
        theme.label(f, "Изменения применяются после сохранения.",
                    fg=MUTE, size=8, bg=BG, wraplength=276, justify="left"
                    ).place(x=956, y=54)
        self.saved_label = theme.label(f, "", fg=GREEN, size=9, bg=BG,
                                       wraplength=276, justify="left")
        self.saved_label.place(x=956, y=78)

        theme.RoundButton(f, "Открыть папку моделей", glyph=theme.ICONS["folder"],
                          command=self.app.open_models, width=276, height=36,
                          bg=BG).place(x=956, y=130)
        theme.RoundButton(f, "Открыть журнал", glyph=theme.ICONS["page"],
                          command=self.app.open_log, width=276, height=36,
                          bg=BG).place(x=956, y=176)
        theme.label(f, "Журнал помогает разобраться, если текст не вставляется.",
                    fg=MUTE, size=8, bg=BG, wraplength=276, justify="left"
                    ).place(x=956, y=222)

    def save(self) -> None:
        message = self.app.apply_settings(self.collect())
        color = GREEN if message.startswith("Сохранено") else RED
        self.saved_label.configure(text=message, fg=color)

    # --- вспомогательное --------------------------------------------------
    def _refresh_radios(self, radios: list) -> None:
        for radio in radios:
            radio.refresh()

    def _engine_changed(self) -> None:
        self.refresh_model_status()

    def _set_hotkey(self, value: str) -> None:
        self.hotkey_entry.delete(0, "end")
        self.hotkey_entry.insert(0, value)

    def _capture_hotkey(self) -> None:
        grab = tk.Toplevel(self.window.win)
        grab.overrideredirect(True)
        grab.geometry("1x1+0+0")
        grab.attributes("-topmost", True)
        grab.focus_force()
        self.test_label.configure(text="Нажмите сочетание клавиш…", fg=GOLD)

        def on_key(event) -> None:  # noqa: ANN001
            mods = []
            if event.state & 0x0004:
                mods.append("ctrl")
            if event.state & 0x0008:
                mods.append("alt")
            if event.state & 0x0001:
                mods.append("shift")
            key = event.keysym.lower()
            if key in ("control_l", "control_r", "alt_l", "alt_r", "shift_l",
                       "shift_r", "win_l", "win_r", "super_l"):
                return
            key = {"space": "space", "escape": "esc"}.get(key, key)
            spec = "+".join(mods + [key])
            self._set_hotkey(spec)
            self.test_label.configure(text=f"Будет: {format_hotkey(spec)}", fg=GREEN)
            grab.destroy()

        grab.bind("<KeyPress>", on_key)
        grab.after(6000, lambda: grab.destroy() if grab.winfo_exists() else None)

    def push_level(self, level: float) -> None:
        self.level.push(level)

    def refresh_model_status(self) -> None:
        engine = self._engine_choice[0]
        if engine == "whisper":
            self.model_label.configure(
                text=f"Whisper скачает модель «{self.whisper_select.value}» "
                     "сам при первом использовании."
            )
            return
        missing = models.missing(self.settings.models_dir, engine)
        folder = os.path.basename(models.engine_dir(self.settings.models_dir, engine))
        if missing:
            self.model_label.configure(
                text=f"Не хватает файлов модели: {', '.join(missing)}. "
                     "Запустите setup_env.bat или скачайте заново."
            )
        else:
            self.model_label.configure(text=f"Модель на месте: {folder}")

    def refresh(self) -> None:
        # опрос звуковых устройств занимает доли секунды, поэтому список
        # микрофонов обновляем только при показе вкладки (on_show)
        self.refresh_model_status()

    def on_show(self) -> None:
        names = ["по умолчанию"] + [name for _i, name, _r
                                    in audio.Recorder.list_input_devices()]
        self.device_select.set_values(names, self.settings.input_device or "по умолчанию")
        self.refresh_model_status()

    # --- проверка микрофона -----------------------------------------------
    def _test(self) -> None:
        self.test_label.configure(text="Запись 3 секунды — говорите…", fg=DIM)
        threading.Thread(target=self._test_worker, daemon=True).start()

    def _test_worker(self) -> None:
        import numpy as np
        import sounddevice as sd

        device = self.device_select.value
        index = None
        for idx, name, _rate in audio.Recorder.list_input_devices():
            if name == device:
                index = idx
                break
        try:
            recording = sd.rec(int(3 * audio.TARGET_RATE), samplerate=audio.TARGET_RATE,
                               channels=1, dtype="float32", device=index)
            sd.wait()
            samples = np.asarray(recording, dtype=np.float32).reshape(-1)
            peak = float(abs(samples).max()) if samples.size else 0.0
            if peak < 0.01:
                self._set_test("Микрофон молчит: уровень почти нулевой.", RED)
                return
            self._set_test("Распознаю…", DIM)
            engine = asr.build_engine(self._engine_choice[0], self.settings.models_dir,
                                      self.whisper_select.value)
            engine.load()
            text = engine.transcribe(samples, self._lang_choice[0])
            self._set_test(f"Уровень {peak:.2f}. Распознано: {text or '(пусто)'}", GREEN)
        except Exception as exc:  # noqa: BLE001
            self._set_test(f"Ошибка: {exc}", RED)

    def _set_test(self, text: str, color: str) -> None:
        self.window.win.after(0, lambda: self.test_label.configure(text=text, fg=color))

    # --- сохранение -------------------------------------------------------
    def _read_dictionary(self) -> list[list[str]]:
        pairs: list[list[str]] = []
        for line in self.dict_text.get("1.0", "end").splitlines():
            if "=" not in line:
                continue
            src, _sep, dst = line.partition("=")
            src, dst = src.strip(), dst.strip()
            if src:
                pairs.append([src, dst])
        return pairs

    def collect(self) -> dict:
        device = self.device_select.value
        if device == "по умолчанию":
            device = ""
        try:
            goal = max(100, min(100000, int(self.goal_entry.get())))
        except ValueError:
            goal = self.settings.weekly_goal_words
        return {
            "engine": self._engine_choice[0],
            "whisper_model": self.whisper_select.value,
            "language": self._lang_choice[0],
            "hotkey": self.hotkey_entry.get().strip().lower() or self.settings.hotkey,
            "insert_mode": self._mode_choice[0],
            "auto_paste": bool(self.paste_check.value),
            "copy_to_clipboard": bool(self.copy_check.value),
            "restore_clipboard": bool(self.restore_check.value),
            "show_overlay": bool(self.overlay_check.value),
            "play_sound": bool(self.sound_check.value),
            "autostart": bool(self.autostart_check.value),
            "input_device": device,
            "dictionary": self._read_dictionary(),
            "weekly_goal_words": goal,
        }


# --------------------------------------------------------------------------
#  Как пользоваться
# --------------------------------------------------------------------------
class HelpTab(Tab):
    key = "help"
    title = "Как пользоваться"

    def build(self) -> None:
        f = self.frame
        left = (CONTENT_W - 780) // 2

        theme.label(f, "Как пользоваться", size=17, weight="bold", bg=BG
                    ).place(x=left, y=0)
        theme.label(f, "Диктуйте голосом в любое приложение — это занимает пару секунд.",
                    fg=DIM, size=10, bg=BG).place(x=left, y=34)

        # демонстрация
        card = theme.Card(f, 780, 150, radius=14, padding=18, bg=BG)
        card.place(x=left, y=70)
        body = card.body
        key_box = tk.Canvas(body, width=184, height=64, bg=PANEL,
                            highlightthickness=0, bd=0)
        key_box.pack(side="left", padx=(0, 18))
        theme.round_rect(key_box, 1, 1, 183, 63, 12, fill=PANEL_HI, outline=GOLD_DIM)
        key_box.create_text(92, 24, text="ВАША КЛАВИША", fill=MUTE,
                            font=theme.font(7, "bold"))
        key_box.create_text(92, 44, text=format_hotkey(self.settings.hotkey),
                            fill=GOLD, font=theme.font(10, "bold"))

        right = tk.Frame(body, bg=PANEL)
        right.pack(side="left", fill="both", expand=True)
        wave = tk.Canvas(right, width=380, height=34, bg=PANEL,
                         highlightthickness=0, bd=0)
        wave.pack(anchor="w")
        coords: list[float] = []
        for index in range(24):
            import math as _math
            level = 0.25 + 0.75 * abs(_math.sin(index * 0.7))
            offset = (2 + 12 * level) * (1 if index % 2 else -1)
            coords.extend((index * 16, 17 + offset))
        wave.create_line(*coords, fill=GOLD, width=2, smooth=True,
                         capstyle="round", joinstyle="round")
        theme.label(right, "запись…", fg=MUTE, size=8, bg=PANEL).place(x=300, y=4)

        example = tk.Frame(right, bg=PANEL_SOFT, highlightthickness=1,
                           highlightbackground=BORDER)
        example.pack(fill="x", pady=(10, 0))
        theme.label(example, "Привет! Это пример текста, который я продиктовал.",
                    fg=TEXT, size=10, bg=PANEL_SOFT).pack(anchor="w", padx=12, pady=10)

        # подсказка
        hint = theme.Card(f, 780, 84, radius=14, padding=18, fill=GOLD_SOFT,
                          border=GOLD_DIM, bg=BG)
        hint.place(x=left, y=236)
        theme.label(hint.body, "Держите, не тапайте", size=11, weight="bold",
                    fg=GOLD, bg=GOLD_SOFT).pack(anchor="w")
        theme.label(hint.body,
                    f"Короткое нажатие запись не запускает. Держите "
                    f"{format_hotkey(self.settings.hotkey)} всё время, пока говорите, "
                    "и отпустите, когда закончили.",
                    fg=TEXT, size=9, bg=GOLD_SOFT, wraplength=730,
                    justify="left").pack(anchor="w", pady=(4, 0))

        # три шага
        steps = [
            ("1", "Зажмите клавишу",
             "В любом текстовом поле — браузер, чат, заметки, почта."),
            ("2", "Говорите",
             "Своими словами, как удобно. Можно вперемешку по-русски и по-английски."),
            ("3", "Отпустите",
             "Текст распознаётся и сам вставится туда, где стоит курсор."),
        ]
        for index, (number, title, text) in enumerate(steps):
            card = theme.Card(f, 244, 150, radius=14, padding=18, bg=BG)
            card.place(x=left + index * 268, y=336)
            body = card.body
            theme.label(body, number, fg=GOLD, size=10, weight="bold",
                        bg=PANEL).pack(anchor="e")
            theme.label(body, title, size=11, weight="bold", bg=PANEL
                        ).pack(anchor="w", pady=(6, 6))
            theme.label(body, text, fg=DIM, size=9, bg=PANEL, wraplength=206,
                        justify="left").pack(anchor="w")

        # если не получается
        card = theme.Card(f, 780, 96, radius=14, padding=18, bg=BG)
        card.place(x=left, y=502)
        theme.label(card.body, "Не получается?", size=11, weight="bold",
                    fg=GOLD, bg=PANEL).pack(anchor="w")
        theme.label(card.body,
                    "Нажали — и ничего не произошло? Скорее всего, отпустили слишком "
                    "быстро. Зажмите клавишу и не отпускайте, пока говорите. Если "
                    "текст не появился в поле — он всё равно в буфере обмена, "
                    "вставьте его вручную.",
                    fg=DIM, size=9, bg=PANEL, wraplength=730,
                    justify="left").pack(anchor="w", pady=(4, 0))
