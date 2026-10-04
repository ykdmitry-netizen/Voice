"""Главное окно «Гласографа»: четыре раздела, значок в трее, меню."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from . import qt_theme as th
from .config import APP_TITLE, log_path
from .qt_pages import HelpPage, HomePage, SettingsPage, SummaryPage

NAV_ITEMS = [
    ("home", th.ICONS["home"], "Главная"),
    ("summary", th.ICONS["chart"], "Сводка"),
    ("settings", th.ICONS["settings"], "Настройки"),
    ("help", th.ICONS["help"], "Как пользоваться"),
]


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, app) -> None:  # noqa: ANN001
        super().__init__()
        self.app = app
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(th.app_icon())
        self.resize(1320, 860)
        self.setMinimumSize(1160, 720)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(26, 18, 26, 20)
        root.setSpacing(16)

        # --- верхняя панель -----------------------------------------------
        nav = QtWidgets.QHBoxLayout()
        nav.setSpacing(8)
        logo = QtWidgets.QHBoxLayout()
        logo.setSpacing(8)
        logo.addWidget(th.text_label(APP_TITLE, th.TEXT, 20, 600))
        logo.addWidget(th.glyph_label(th.ICONS["mic"], th.GOLD, 18))
        logo_wrap = QtWidgets.QWidget()
        logo_wrap.setLayout(logo)
        nav.addWidget(logo_wrap)
        nav.addStretch(1)

        self.nav_group = QtWidgets.QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QtWidgets.QPushButton] = {}
        for index, (key, glyph, label) in enumerate(NAV_ITEMS):
            button = QtWidgets.QPushButton(f"  {label}")
            button.setObjectName("Nav")
            button.setCheckable(True)
            button.setIcon(th.glyph_icon(glyph, th.GOLD, 16))
            button.setIconSize(QtCore.QSize(16, 16))
            button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _c=False, k=key: self.show_page(k))
            self.nav_group.addButton(button, index)
            self.nav_buttons[key] = button
            nav.addWidget(button)

        nav.addStretch(1)
        root.addLayout(nav)

        # --- страницы ------------------------------------------------------
        self.stack = QtWidgets.QStackedWidget()
        self.pages = {
            "home": HomePage(app),
            "summary": SummaryPage(app),
            "settings": SettingsPage(app),
            "help": HelpPage(app),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)
        root.addWidget(self.stack, 1)

        self.nav_buttons["home"].setChecked(True)
        self.show_page("home")

    # --- страницы ---------------------------------------------------------
    def page(self, key: str):
        return self.pages.get(key)

    def show_page(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        button = self.nav_buttons.get(key)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        page.refresh()
        page.on_show()

    def refresh_all(self) -> None:
        for page in self.pages.values():
            page.refresh()

    # --- удобные обращения к «Главной» ------------------------------------
    def set_status(self, text: str, color: str = th.DIM) -> None:
        self.pages["home"].set_status(text, color)

    def set_recording(self, recording: bool) -> None:
        self.pages["home"].set_recording(recording)

    def push_level(self, level: float) -> None:
        self.pages["settings"].push_level(level)

    def show_window(self, page: str | None = None) -> None:
        if page:
            self.show_page(page)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.refresh_all()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        if self.app.quitting:
            event.accept()
            return
        event.ignore()
        self.hide()


class Tray:
    """Значок в трее со своим меню (штатный QSystemTrayIcon)."""

    def __init__(self, app, window: MainWindow) -> None:  # noqa: ANN001
        self.app = app
        self.window = window
        self.icon = QtWidgets.QSystemTrayIcon(th.app_icon(), window)
        self.icon.setToolTip(APP_TITLE)
        self.menu = QtWidgets.QMenu()
        self.menu.aboutToShow.connect(self._rebuild)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        self._rebuild()

    def _rebuild(self) -> None:
        self.menu.clear()
        open_action = self.menu.addAction("Открыть окно")
        open_action.triggered.connect(lambda: self.app.show_window())
        toggle = self.menu.addAction(
            "Остановить диктовку" if self.app.is_recording else "Начать диктовку")
        toggle.triggered.connect(self.app.toggle_dictation)
        self.menu.addSeparator()
        settings = self.menu.addAction("Настройки")
        settings.triggered.connect(lambda: self.app.show_window("settings"))
        log_action = self.menu.addAction("Открыть журнал")
        log_action.triggered.connect(self.app.open_log)
        models_action = self.menu.addAction("Открыть папку моделей")
        models_action.triggered.connect(self.app.open_models)
        self.menu.addSeparator()
        quit_action = self.menu.addAction("Выход")
        quit_action.triggered.connect(self.app.quit)

    def _activated(self, reason) -> None:  # noqa: ANN001
        if reason in (QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick,
                      QtWidgets.QSystemTrayIcon.ActivationReason.Trigger):
            self.app.toggle_window()

    def show(self) -> bool:
        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            return False
        self.icon.show()
        return self.icon.isVisible()


class ControlWindow(QtWidgets.QWidget):
    """Резервное окно управления, если значка в трее нет."""

    def __init__(self, app) -> None:  # noqa: ANN001
        super().__init__(None, QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.app = app
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(th.app_icon())
        self.setFixedWidth(360)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        head = QtWidgets.QHBoxLayout()
        head.addWidget(th.glyph_label(th.ICONS["mic"], th.GOLD, 18))
        head.addWidget(th.text_label(APP_TITLE, th.TEXT, 17, 600))
        head.addStretch(1)
        layout.addLayout(head)
        layout.addWidget(th.text_label(
            "Значок в трее не появился. Управление — этими кнопками.", th.DIM, 12))

        self.toggle_btn = QtWidgets.QPushButton("  Начать диктовку")
        self.toggle_btn.setObjectName("Accent")
        self.toggle_btn.setIcon(th.glyph_icon(th.ICONS["mic"], th.GOLD, 16))
        self.toggle_btn.setMinimumHeight(40)
        self.toggle_btn.clicked.connect(app.toggle_dictation)
        layout.addWidget(self.toggle_btn)

        settings_btn = QtWidgets.QPushButton("  Настройки")
        settings_btn.setIcon(th.glyph_icon(th.ICONS["settings"], th.TEXT, 16))
        settings_btn.clicked.connect(lambda: app.show_window("settings"))
        layout.addWidget(settings_btn)

        window_btn = QtWidgets.QPushButton("  Открыть окно")
        window_btn.setIcon(th.glyph_icon(th.ICONS["home"], th.TEXT, 16))
        window_btn.clicked.connect(lambda: app.show_window())
        layout.addWidget(window_btn)

        layout.addStretch(1)
        quit_btn = QtWidgets.QPushButton("  Выход")
        quit_btn.setIcon(th.glyph_icon(th.ICONS["power"], th.TEXT, 16))
        quit_btn.clicked.connect(app.quit)
        layout.addWidget(quit_btn)

    def set_recording(self, recording: bool) -> None:
        self.toggle_btn.setText("  Остановить диктовку" if recording else "  Начать диктовку")
