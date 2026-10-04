"""Повторно используемые элементы интерфейса на Qt."""

from __future__ import annotations

import datetime as dt
from collections import deque

from PySide6 import QtCore, QtGui, QtWidgets

from . import qt_theme as th

MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря")


class Card(QtWidgets.QFrame):
    """Панель со скруглёнными углами и отступами."""

    def __init__(self, parent: QtWidgets.QWidget | None = None, *, margins: int = 18,
                 spacing: int = 10, variant: str = "Card") -> None:
        super().__init__(parent)
        self.setObjectName(variant)
        self.body = QtWidgets.QVBoxLayout(self)
        self.body.setContentsMargins(margins, margins, margins, margins)
        self.body.setSpacing(spacing)


class StatCard(Card):
    """Карточка со значением: подпись, крупное число, пояснение."""

    def __init__(self, title: str, glyph: str, color: str = th.GOLD,
                 subtitle: str = "", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent, margins=16)
        self.setMinimumHeight(112)
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(th.text_label(title, th.DIM, 12))
        head.addStretch(1)
        head.addWidget(th.glyph_label(glyph, color, 15))
        self.body.addLayout(head)

        self.value = th.text_label("0", th.TEXT, 30, 600)
        self.value.setObjectName("Big")
        self.body.addWidget(self.value)
        self.body.addWidget(th.text_label(subtitle, th.MUTE, 11))
        self.body.addStretch(1)

    def set_value(self, text: str) -> None:
        self.value.setText(text)


class MicButton(QtWidgets.QPushButton):
    """Круглая кнопка микрофона."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Mic")
        self.setFixedSize(76, 76)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QtCore.QSize(28, 28))
        self.set_recording(False)

    def set_recording(self, recording: bool) -> None:
        self.setObjectName("MicRec" if recording else "Mic")
        self.setIcon(th.glyph_icon(th.ICONS["mic"], "#141005" if not recording else "#1a0806", 28))
        self.style().unpolish(self)
        self.style().polish(self)


class HistoryEntry(QtWidgets.QFrame):
    """Одна запись в истории."""

    clicked = QtCore.Signal(object)

    def __init__(self, entry, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.setObjectName("Entry")
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.selected = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        top = QtWidgets.QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(th.glyph_label(th.ICONS["page"], th.DIM, 13))
        when = dt.datetime.fromtimestamp(entry.ts)
        top.addWidget(th.text_label(f"{when:%H:%M}", th.MUTE, 11))
        top.addStretch(1)
        top.addWidget(th.text_label(f"{entry.words} сл.", th.GOLD, 11))
        layout.addLayout(top)

        preview = entry.text.strip().replace("\n", " ")
        if len(preview) > 120:
            preview = preview[:119] + "…"
        label = th.text_label(preview, th.TEXT, 12)
        label.setWordWrap(True)
        layout.addWidget(label)

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.setStyleSheet(
            f"QFrame#Entry {{ border: 1px solid {th.GOLD_DIM};"
            f" background: {th.GOLD_SOFT}; border-radius: 12px; }}"
            if selected else ""
        )

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        self.clicked.emit(self.entry)
        super().mousePressEvent(event)


class HistoryList(QtWidgets.QScrollArea):
    """Прокручиваемый список истории с заголовками по дням."""

    selected = QtCore.Signal(object)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._container = QtWidgets.QWidget()
        self._layout = QtWidgets.QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 0, 4, 0)
        self._layout.setSpacing(4)
        self._layout.addStretch(1)
        self.setWidget(self._container)
        self._rows: list[HistoryEntry] = []

    def set_entries(self, entries: list) -> None:
        """Пересобирает список целиком.

        Просто удалять старые виджеты нельзя: пока Qt их не удалил, раскладка
        держит их геометрию и строки наезжают друг на друга.
        """
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(4)
        self._rows = []

        if not entries:
            empty = th.text_label("Пока пусто.\nНаговорите первую фразу.", th.MUTE, 12)
            empty.setContentsMargins(8, 16, 8, 16)
            layout.addWidget(empty)
            layout.addStretch(1)
            self.setWidget(container)
            return

        today = dt.date.today()
        last_header = None
        for entry in entries[:150]:
            day = dt.datetime.fromtimestamp(entry.ts).date()
            if day != last_header:
                last_header = day
                if day == today:
                    header = "СЕГОДНЯ"
                elif day == today - dt.timedelta(days=1):
                    header = "ВЧЕРА"
                else:
                    header = f"{day.day} {MONTHS[day.month - 1].upper()}"
                label = th.text_label(header, th.MUTE, 10, 600)
                label.setContentsMargins(8, 10, 0, 2)
                layout.addWidget(label)

            row = HistoryEntry(entry)
            row.clicked.connect(self._on_click)
            layout.addWidget(row)
            self._rows.append(row)

        layout.addStretch(1)
        self.setWidget(container)

    def _on_click(self, entry) -> None:
        self.select(entry)
        self.selected.emit(entry)

    def select(self, entry) -> None:
        for row in self._rows:
            row.set_selected(row.entry is entry)

    def clear_selection(self) -> None:
        for row in self._rows:
            row.set_selected(False)


class ActivityStrip(QtWidgets.QWidget):
    """Лента активности: 28 столбиков, ярче — больше слов."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(96)
        self._cells: list[tuple[dt.date, int]] = []
        self.setMouseTracking(True)

    def set_data(self, cells: list[tuple[dt.date, int]]) -> None:
        self._cells = cells
        self.update()

    def _cell_rect(self, index: int) -> QtCore.QRectF:
        count = max(1, len(self._cells))
        gap = 5
        size = min(40.0, (self.width() - (count - 1) * gap) / count)
        total = count * size + (count - 1) * gap
        x0 = (self.width() - total) / 2
        y0 = max(16.0, (self.height() - size) / 2 - 10)
        return QtCore.QRectF(x0 + index * (size + gap), y0, size, size)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        if not self._cells:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        max_words = max((words for _day, words in self._cells), default=0) or 1

        for index, (_day, words) in enumerate(self._cells):
            rect = self._cell_rect(index)
            ratio = words / max_words
            if words == 0:
                color = QtGui.QColor("#17171c")
            elif ratio < 0.34:
                color = QtGui.QColor("#4a3a16")
            elif ratio < 0.67:
                color = QtGui.QColor("#8a6a25")
            else:
                color = QtGui.QColor(th.GOLD)
            painter.setBrush(color)
            painter.setPen(QtGui.QPen(QtGui.QColor(th.BORDER)) if words == 0
                           else QtCore.Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 7, 7)

        painter.setFont(th.font(11))
        painter.setPen(QtGui.QColor(th.MUTE))
        first = self._cell_rect(0)
        last = self._cell_rect(len(self._cells) - 1)
        painter.drawText(QtCore.QPointF(first.left(), first.bottom() + 18),
                         f"{self._cells[0][0]:%d.%m}")
        painter.drawText(QtCore.QRectF(last.right() - 80, last.bottom() + 6, 80, 18),
                         QtCore.Qt.AlignmentFlag.AlignRight, "сегодня")
        painter.end()

    def event(self, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.ToolTip:
            pos = event.pos()
            for index, (day, words) in enumerate(self._cells):
                if self._cell_rect(index).contains(QtCore.QPointF(pos)):
                    self.setToolTip(f"{day:%d.%m.%Y}: {words} слов")
                    break
        return super().event(event)


class LevelMeter(QtWidgets.QWidget):
    """Полоска уровня микрофона."""

    def __init__(self, parent: QtWidgets.QWidget | None = None, bars: int = 40) -> None:
        super().__init__(parent)
        self.setFixedHeight(34)
        self._values: deque[float] = deque([0.0] * bars, maxlen=bars)

    def push(self, value: float) -> None:
        self._values.append(max(0.0, min(1.0, value)))
        self.update()

    def clear(self) -> None:
        self._values = deque([0.0] * self._values.maxlen, maxlen=self._values.maxlen)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        count = len(self._values)
        step = self.width() / count
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        cy = self.height() / 2
        for index, value in enumerate(self._values):
            half = 2 + (cy - 3) * value
            if value > 0.45:
                color = QtGui.QColor(th.GOLD)
            elif value > 0.12:
                color = QtGui.QColor(th.GOLD_DIM)
            else:
                color = QtGui.QColor(th.BORDER_HI)
            painter.setBrush(color)
            painter.drawRoundedRect(
                QtCore.QRectF(index * step + step / 2 - 1.5, cy - half, 3, half * 2), 1.5, 1.5
            )
        painter.end()


class Waveform(QtWidgets.QWidget):
    """Небольшая декоративная волна для вкладки «Как пользоваться»."""

    def __init__(self, parent: QtWidgets.QWidget | None = None,
                 color: str = th.GOLD) -> None:
        super().__init__(parent)
        self.setFixedHeight(34)
        self._color = color

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        import math

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor(self._color), 2)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        points = []
        count = 34
        for index in range(count):
            level = 0.2 + 0.8 * abs(math.sin(index * 0.55))
            offset = (3 + 11 * level) * (1 if index % 2 else -1)
            points.append(QtCore.QPointF(index * (self.width() / count),
                                         self.height() / 2 + offset))
        painter.drawPolyline(points)
        painter.end()
