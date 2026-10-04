"""Индикатор диктовки на Qt: безрамочная «пилюля» поверх всех окон.

Красный кружок записи и волна уровня. Слов во время записи нет — говорит
анимация; текст появляется только в коротком сообщении с результатом.
"""

from __future__ import annotations

import math
from collections import deque

from PySide6 import QtCore, QtGui, QtWidgets

from . import qt_theme as th

PANEL = "#121214"
HEIGHT = 46
WIDTH_COMPACT = 214
WIDTH_MAX = 460
WAVE_POINTS = 15
PAD_LEFT = 36


class OverlayWidget(QtWidgets.QWidget):
    def __init__(self) -> None:
        flags = (QtCore.Qt.WindowType.FramelessWindowHint
                 | QtCore.Qt.WindowType.WindowStaysOnTopHint
                 | QtCore.Qt.WindowType.Tool
                 | QtCore.Qt.WindowType.WindowDoesNotAcceptFocus
                 | QtCore.Qt.WindowType.WindowTransparentForInput)
        super().__init__(None, flags)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowTitle("Индикатор диктовки")

        self.enabled = True
        self._state = "idle"
        self._message = ""
        self._note = ""
        self._color = th.GOLD
        self._levels: deque[float] = deque([0.0] * WAVE_POINTS, maxlen=WAVE_POINTS)
        self._phase = 0.0
        self._width = WIDTH_COMPACT
        self._hide_timer = QtCore.QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._tick)

        self._font = th.font(13)
        self._metrics = QtGui.QFontMetrics(self._font)
        self.setFixedSize(self._width, HEIGHT)
        self.hide()

    # --- геометрия --------------------------------------------------------
    def _place(self) -> None:
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = area.center().x() - self._width // 2
        y = area.bottom() - HEIGHT - 76
        self.setGeometry(x, y, self._width, HEIGHT)

    def _resize(self, width: int) -> None:
        width = max(WIDTH_COMPACT, min(WIDTH_MAX, int(width)))
        if width != self._width:
            self._width = width
            self.setFixedSize(width, HEIGHT)
            self._place()

    # --- внешний интерфейс ------------------------------------------------
    def set_level(self, level: float) -> None:
        self._levels.append(max(0.0, min(1.0, level)))

    def recording(self, level: float = 0.0) -> None:
        if not self.enabled:
            return
        self._hide_timer.stop()
        self._resize(WIDTH_COMPACT)
        self._state = "recording"
        self._message = ""
        self._note = ""
        self._levels.append(max(0.0, min(1.0, level)))
        self._show()
        self._timer.start()

    def working(self, subtitle: str = "") -> None:
        if not self.enabled:
            return
        self._hide_timer.stop()
        self._note = subtitle
        self._resize(WIDTH_COMPACT + (58 if subtitle else 0))
        self._state = "working"
        self._message = ""
        self._show()
        self._timer.start()

    def done(self, text: str, hide_after_ms: int = 1600) -> None:
        self._message_state("done", text, th.GREEN, hide_after_ms)

    def notice(self, title: str, subtitle: str = "", color: str = th.DIM,
               hide_after_ms: int = 2200) -> None:
        self._message_state("notice", title, color, hide_after_ms)

    def error(self, message: str, hide_after_ms: int = 4000) -> None:
        self._message_state("error", message, th.RED, hide_after_ms)

    def _message_state(self, state: str, text: str, color: str, hide_ms: int) -> None:
        if not self.enabled:
            return
        self._timer.stop()
        self._state = state
        self._message = self._fit(text)
        self._color = color
        self._resize(PAD_LEFT + 26 + self._metrics.horizontalAdvance(self._message))
        self._show()
        self._hide_timer.start(max(400, hide_ms))

    def _fit(self, text: str) -> str:
        limit = WIDTH_MAX - PAD_LEFT - 28
        if self._metrics.horizontalAdvance(text) <= limit:
            return text
        shortened = text
        while shortened and self._metrics.horizontalAdvance(shortened + "…") > limit:
            shortened = shortened[:-1]
        return shortened + "…"

    def _show(self) -> None:
        self._place()
        self.show()
        self.raise_()

    def stop(self) -> None:
        self._timer.stop()
        self._hide_timer.stop()
        self.hide()

    # --- отрисовка --------------------------------------------------------
    def _tick(self) -> None:
        if self._state not in ("recording", "working"):
            self._timer.stop()
            return
        self._phase += 0.12
        if self._state == "recording":
            self._levels.append(self._levels[-1] * 0.8)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(1, 1, self.width() - 2, self.height() - 2)
        painter.setBrush(QtGui.QColor(PANEL))
        painter.setPen(QtGui.QPen(QtGui.QColor(th.GOLD_DIM), 1))
        painter.drawRoundedRect(rect, 14, 14)

        cy = self.height() / 2
        if self._state == "recording":
            radius = 4.5 + 2.0 * self._levels[-1]
            painter.setBrush(QtGui.QColor(th.RED))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawEllipse(QtCore.QPointF(20, cy), radius, radius)
            self._paint_wave(painter, cy, list(self._levels), th.GOLD)
        elif self._state == "working":
            painter.setBrush(QtGui.QColor(th.GOLD))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.drawEllipse(QtCore.QPointF(20, cy), 4.5, 4.5)
            wave = [0.18 + 0.82 * abs(math.sin(self._phase * 1.5 + i * 0.5))
                    for i in range(WAVE_POINTS)]
            self._paint_wave(painter, cy, wave, th.GOLD)
            if self._note:
                painter.setFont(self._font)
                painter.setPen(QtGui.QColor(th.DIM))
                painter.drawText(
                    QtCore.QRectF(self.width() - 68, 0, 56, self.height()),
                    QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter,
                    self._note)
        else:
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            if self._state == "done":
                painter.setBrush(QtGui.QColor(th.GREEN))
                painter.drawEllipse(QtCore.QPointF(20, cy), 7, 7)
                pen = QtGui.QPen(QtGui.QColor(PANEL), 2)
                pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawPolyline([QtCore.QPointF(17, cy),
                                      QtCore.QPointF(20, cy + 3.5),
                                      QtCore.QPointF(24, cy - 3.5)])
            else:
                painter.setBrush(QtGui.QColor(self._color))
                painter.drawEllipse(QtCore.QPointF(21, cy), 6, 6)
            if self._message:
                painter.setFont(self._font)
                painter.setPen(QtGui.QColor(th.TEXT))
                painter.drawText(
                    QtCore.QRectF(PAD_LEFT + 4, 0, self.width() - PAD_LEFT - 12,
                                  self.height()),
                    QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
                    self._message)
        painter.end()

    def _paint_wave(self, painter: QtGui.QPainter, cy: float,
                    values: list[float], color: str) -> None:
        span = self.width() - PAD_LEFT - 16
        step = span / (WAVE_POINTS - 1)
        pen = QtGui.QPen(QtGui.QColor(color), 2)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        points = []
        for index, value in enumerate(values):
            level = max(0.0, min(1.0, value))
            offset = (2.5 + 13.0 * level) * (1 if index % 2 else -1)
            points.append(QtCore.QPointF(PAD_LEFT + index * step, cy + offset))
        painter.drawPolyline(points)
