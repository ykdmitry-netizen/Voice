"""Оформление на Qt: цвета, шрифты, иконки и таблица стилей.

Qt рисует скругления, тени и состояния сам, поэтому тема здесь — это набор
констант и один QSS. Иконки берём из системного шрифта Segoe MDL2 Assets:
он есть в Windows 10/11 и не требует картинок.
"""

from __future__ import annotations

import os

from PySide6 import QtCore, QtGui, QtWidgets

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
ICON_FAMILY = "Segoe MDL2 Assets"

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


def font(size: int = 10, weight: int = 400) -> QtGui.QFont:
    f = QtGui.QFont(FAMILY)
    f.setPixelSize(size)
    f.setWeight(QtGui.QFont.Weight(weight))
    return f


def icon_font(size: int = 14) -> QtGui.QFont:
    f = QtGui.QFont(ICON_FAMILY)
    f.setPixelSize(size)
    return f


def glyph_pixmap(char: str, color: str = GOLD, size: int = 16) -> QtGui.QPixmap:
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pix)
    painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)
    painter.setFont(icon_font(int(size * 0.84)))
    painter.setPen(QtGui.QColor(color))
    painter.drawText(pix.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, char)
    painter.end()
    return pix


def glyph_icon(char: str, color: str = GOLD, size: int = 16) -> QtGui.QIcon:
    return QtGui.QIcon(glyph_pixmap(char, color, size))


def glyph_label(char: str, color: str = GOLD, size: int = 14,
                parent: QtWidgets.QWidget | None = None) -> QtWidgets.QLabel:
    """Иконка-глиф отдельным виджетом.

    Рисуем картинку, а не полагаемся на шрифт: общий QSS задаёт семейство
    шрифта всем виджетам и затёр бы Segoe MDL2 Assets.
    """
    label = QtWidgets.QLabel(parent)
    label.setPixmap(glyph_pixmap(char, color, size))
    label.setStyleSheet("background: transparent;")
    label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    return label


def text_label(text: str, color: str = TEXT, size: int = 13, weight: int = 400,
               parent: QtWidgets.QWidget | None = None, wrap: bool = False
               ) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text, parent)
    label.setFont(font(size, weight))
    label.setStyleSheet(f"color: {color}; background: transparent;")
    if wrap:
        label.setWordWrap(True)
    return label


def app_icon(size: int = 64) -> QtGui.QIcon:
    """Значок приложения: золотой кружок с микрофоном."""
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setBrush(QtGui.QColor(GOLD))
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, size - 4, size - 4)
    p.setFont(icon_font(int(size * 0.56)))
    p.setPen(QtGui.QColor("#141005"))
    p.drawText(pix.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, ICONS["mic"])
    p.end()
    return QtGui.QIcon(pix)


QSS = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "{FAMILY}";
    font-size: 13px;
}}
QToolTip {{
    background: {PANEL_HI};
    color: {TEXT};
    border: 1px solid {BORDER_HI};
    padding: 6px;
}}
QFrame#Card {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#Soft {{
    background: {PANEL_SOFT};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#Hint {{
    background: {GOLD_SOFT};
    border: 1px solid {GOLD_DIM};
    border-radius: 14px;
}}
QFrame#Entry {{
    background: {PANEL_HI};
    border: 1px solid transparent;
    border-radius: 12px;
}}
QFrame#Entry:hover {{
    border-color: {BORDER_HI};
}}
QLabel#H1 {{ font-size: 26px; font-weight: 600; }}
QLabel#H2 {{ font-size: 17px; font-weight: 600; }}
QLabel#CardTitle {{ font-size: 15px; font-weight: 600; }}
QLabel#Big {{ font-size: 30px; font-weight: 600; }}
QLabel#Muted {{ color: {DIM}; font-size: 12px; }}
QLabel#Faint {{ color: {MUTE}; font-size: 11px; }}
QLabel#Gold {{ color: {GOLD}; }}
QPushButton {{
    background: {PANEL_HI};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 14px;
    font-size: 13px;
}}
QPushButton:hover {{ background: #232329; border-color: {BORDER_HI}; }}
QPushButton:pressed {{ background: #2a2a31; }}
QPushButton:disabled {{ color: {MUTE}; border-color: {BORDER}; }}
QPushButton#Nav {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 12px;
    padding: 9px 18px;
    color: {DIM};
    font-size: 13px;
    text-align: left;
}}
QPushButton#Nav:hover {{ background: {PANEL_HI}; color: {TEXT}; }}
QPushButton#Nav:checked {{
    background: {GOLD_SOFT};
    border-color: {GOLD_DIM};
    color: {GOLD};
}}
QPushButton#Accent {{
    background: {GOLD_SOFT};
    border-color: {GOLD_DIM};
    color: {GOLD};
}}
QPushButton#Accent:hover {{ background: #2c2410; border-color: {GOLD}; }}
QPushButton#Ghost {{ background: transparent; border-color: transparent; color: {DIM}; }}
QPushButton#Ghost:hover {{ background: {PANEL_HI}; color: {TEXT}; }}
QPushButton#Mic {{
    border-radius: 38px;
    background: {GOLD};
    border: 4px solid {GOLD_SOFT};
    color: #141005;
}}
QPushButton#Mic:hover {{ background: {GOLD_BRIGHT}; }}
QPushButton#MicRec {{
    border-radius: 38px;
    background: {RED};
    border: 4px solid #2a1110;
    color: #1a0806;
}}
QLineEdit, QTextEdit, QPlainTextEdit {{
    background: {PANEL_SOFT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px 10px;
    selection-background-color: {GOLD_DIM};
    selection-color: {TEXT};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {GOLD_DIM}; }}
QComboBox {{
    background: {PANEL_SOFT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 7px 12px;
}}
QComboBox:hover {{ border-color: {BORDER_HI}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {DIM};
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {PANEL_HI};
    border: 1px solid {BORDER_HI};
    border-radius: 8px;
    selection-background-color: {GOLD_SOFT};
    selection-color: {GOLD};
    outline: none;
    padding: 4px;
}}
QCheckBox, QRadioButton {{ spacing: 9px; color: {DIM}; }}
QCheckBox:hover, QRadioButton:hover {{ color: {TEXT}; }}
QCheckBox::indicator {{
    width: 18px; height: 18px;
    border-radius: 5px;
    border: 1px solid #4a4a52;
    background: {PANEL_SOFT};
}}
QCheckBox::indicator:hover {{ border-color: {GOLD_DIM}; }}
QCheckBox::indicator:checked {{
    background: {GOLD};
    border-color: {GOLD};
    image: url("@CHECK@");
}}
QRadioButton::indicator {{
    width: 18px; height: 18px;
    border-radius: 9px;
    border: 2px solid #4a4a52;
    background: {PANEL_SOFT};
}}
QRadioButton::indicator:hover {{ border-color: {GOLD_DIM}; }}
QRadioButton::indicator:checked {{ border-color: {GOLD}; background: {GOLD}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2c2c33; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {GOLD_DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #2c2c33; border-radius: 4px; min-width: 30px; }}
QMenu {{
    background: {PANEL_HI};
    border: 1px solid {BORDER_HI};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{ padding: 7px 26px 7px 14px; border-radius: 7px; }}
QMenu::item:selected {{ background: {GOLD_SOFT}; color: {GOLD}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}
QProgressBar {{
    background: #1e1e24;
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background: {GOLD}; border-radius: 3px; }}
QStackedWidget {{ background: transparent; }}
QSplitter::handle {{ background: transparent; }}
"""

_check_icon_path: str | None = None


def check_icon() -> str:
    """Рисует галочку для флажков: в QSS картинку без файла не подставить."""
    global _check_icon_path
    if _check_icon_path and os.path.exists(_check_icon_path):
        return _check_icon_path

    from .config import home_dir

    path = os.path.join(home_dir(), "check.png")
    pix = QtGui.QPixmap(18, 18)
    pix.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pix)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pen = QtGui.QPen(QtGui.QColor("#1a1406"), 2.6)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline([QtCore.QPointF(4.5, 9.5), QtCore.QPointF(7.5, 13),
                          QtCore.QPointF(13.5, 5.5)])
    painter.end()
    try:
        pix.save(path)
        _check_icon_path = path
    except Exception:  # noqa: BLE001 - без галочки флажки всё равно работают
        _check_icon_path = ""
    return _check_icon_path or ""


def stylesheet() -> str:
    """QSS с подставленной картинкой галочки."""
    path = check_icon().replace("\\", "/")
    return QSS.replace("@CHECK@", path)
