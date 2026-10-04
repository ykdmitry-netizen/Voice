"""Четыре страницы главного окна: Главная, Сводка, Настройки, Как пользоваться."""

from __future__ import annotations

import os
import threading

from PySide6 import QtCore, QtGui, QtWidgets

from . import asr, audio, models, qt_theme as th, stats
from .config import format_hotkey
from .qt_widgets import ActivityStrip, Card, HistoryList, LevelMeter, MicButton, StatCard

PRESET_KEYS = [("Right Ctrl", "right ctrl"), ("CapsLock", "capslock"),
               ("Ctrl + Пробел", "ctrl+space")]


class BasePage(QtWidgets.QWidget):
    def __init__(self, app) -> None:  # noqa: ANN001
        super().__init__()
        self.app = app
        self.settings = app.settings
        self.history = app.history

    def refresh(self) -> None:
        pass

    def on_show(self) -> None:
        """Вызывается, когда страница становится видимой."""
        pass


# --------------------------------------------------------------------------
class HomePage(BasePage):
    def __init__(self, app) -> None:  # noqa: ANN001
        super().__init__(app)
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(22)

        # --- левая колонка: история и две карточки ------------------------
        left_wrap = QtWidgets.QWidget()
        left_wrap.setFixedWidth(330)
        left = QtWidgets.QVBoxLayout(left_wrap)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(10)
        root.addWidget(left_wrap)

        head = QtWidgets.QHBoxLayout()
        title = th.text_label("ИСТОРИЯ", th.MUTE, 11, 600)
        head.addWidget(title)
        head.addStretch(1)
        refresh_btn = QtWidgets.QPushButton()
        refresh_btn.setObjectName("Ghost")
        refresh_btn.setIcon(th.glyph_icon(th.ICONS["refresh"], th.DIM, 15))
        refresh_btn.setFixedSize(34, 28)
        refresh_btn.setToolTip("Обновить историю")
        refresh_btn.clicked.connect(self._reload)
        head.addWidget(refresh_btn)
        left.addLayout(head)

        self.list = HistoryList()
        self.list.selected.connect(self._select)
        left.addWidget(self.list, 1)

        self.words_card = StatCard("Слов всего", th.ICONS["list"], th.BLUE, "распознано голосом")
        self.words_card.setFixedHeight(112)
        left.addWidget(self.words_card)
        self.minutes_card = StatCard("Минут наговорено", th.ICONS["clock"], th.BLUE, "вместо печати")
        self.minutes_card.setFixedHeight(112)
        left.addWidget(self.minutes_card)

        # --- правая колонка: текст и кнопка микрофона ---------------------
        right = QtWidgets.QVBoxLayout()
        right.setSpacing(14)
        root.addLayout(right, 1)

        card = Card(margins=20)
        header = QtWidgets.QHBoxLayout()
        header.addWidget(th.text_label("Распознанный текст", th.TEXT, 15, 600))
        header.addStretch(1)
        self.copy_btn = QtWidgets.QPushButton("  Копировать")
        self.copy_btn.setIcon(th.glyph_icon(th.ICONS["copy"], th.TEXT, 15))
        self.copy_btn.clicked.connect(self._copy)
        header.addWidget(self.copy_btn)
        self.delete_btn = QtWidgets.QPushButton("  Удалить")
        self.delete_btn.setIcon(th.glyph_icon(th.ICONS["delete"], th.TEXT, 15))
        self.delete_btn.clicked.connect(self._delete)
        header.addWidget(self.delete_btn)
        card.body.addLayout(header)

        self.stack = QtWidgets.QStackedWidget()
        self.empty_page = self._build_empty()
        self.stack.addWidget(self.empty_page)
        self.text = QtWidgets.QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(th.font(14))
        self.stack.addWidget(self.text)
        card.body.addWidget(self.stack, 1)
        right.addWidget(card, 1)

        bottom = QtWidgets.QVBoxLayout()
        bottom.setSpacing(8)
        self.mic = MicButton()
        self.mic.clicked.connect(self.app.toggle_dictation)
        bottom.addWidget(self.mic, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.status = th.text_label("Готово к диктовке", th.MUTE, 12)
        self.status.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        bottom.addWidget(self.status)
        right.addLayout(bottom)

        self._current = None
        self.refresh()

    def _build_empty(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.addStretch(1)
        badge = QtWidgets.QLabel()
        badge.setPixmap(th.glyph_pixmap(th.ICONS["mic"], th.GOLD, 56))
        badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(badge)
        title = th.text_label("Наговори — и текст появится здесь", th.TEXT, 15, 600)
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        hint = th.text_label("Зажмите клавишу, скажите фразу и отпустите.\n"
                             "Текст можно скопировать или удалить.", th.DIM, 12)
        hint.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    # --- данные -----------------------------------------------------------
    def current_entry(self):
        return self._current

    def refresh(self) -> None:
        summary = stats.summarize(self.history.entries())
        self.words_card.set_value(f"{summary.words:,}".replace(",", " "))
        self.minutes_card.set_value(f"{summary.seconds / 60:.0f}")

        if self.isVisible():
            self._sync_list()

    def on_show(self) -> None:
        self._sync_list()

    def _sync_list(self) -> None:
        self.list.set_entries(self.history.entries())
        if self._current is not None and not self.history.contains(self._current):
            self._current = None
        if self._current is None:
            self._current = self.history.last
        if self._current is not None:
            self.list.select(self._current)
        self._show(self._current)

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_list()

    def _reload(self) -> None:
        self.history.load()
        self.refresh()

    def _select(self, entry) -> None:
        self._current = entry
        self._show(entry)

    def _show(self, entry) -> None:  # noqa: ANN001
        if entry is None:
            self.stack.setCurrentWidget(self.empty_page)
            return
        self.stack.setCurrentWidget(self.text)
        self.text.setPlainText(entry.text)

    def set_status(self, text: str, color: str = th.DIM) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color}; background: transparent;")

    def set_recording(self, recording: bool) -> None:
        self.mic.set_recording(recording)

    # --- действия ---------------------------------------------------------
    def _copy(self) -> None:
        entry = self.current_entry()
        if entry is None:
            self.set_status("Нечего копировать", th.MUTE)
            return
        ok = self.app.copy_to_clipboard(entry.text)
        self.set_status("Текст скопирован" if ok else "Не удалось скопировать",
                        th.GREEN if ok else th.RED)

    def _delete(self) -> None:
        entry = self.current_entry()
        if entry is None:
            return
        self.history.remove(entry)
        self._current = None
        self.set_status("Запись удалена", th.MUTE)
        self.refresh()


# --------------------------------------------------------------------------
class SummaryPage(BasePage):
    def __init__(self, app) -> None:  # noqa: ANN001
        super().__init__(app)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        cards = QtWidgets.QHBoxLayout()
        cards.setSpacing(18)
        self.words_card = StatCard("Слов всего", th.ICONS["list"], th.BLUE, "распознано голосом")
        self.minutes_card = StatCard("Минут наговорено", th.ICONS["clock"], th.BLUE, "вместо печати")
        cards.addWidget(self.words_card, 1)
        cards.addWidget(self.minutes_card, 1)
        root.addLayout(cards)

        card = Card(margins=20)
        header = QtWidgets.QHBoxLayout()
        header.addWidget(th.text_label("Активность за 28 дней", th.TEXT, 15, 600))
        header.addStretch(1)
        header.addWidget(th.text_label("меньше", th.MUTE, 11))
        for color in ("#1e1e24", "#4a3a16", "#8a6a25", th.GOLD):
            box = QtWidgets.QLabel()
            box.setFixedSize(12, 12)
            box.setStyleSheet(f"background: {color}; border-radius: 3px;")
            header.addWidget(box)
        header.addWidget(th.text_label("больше", th.MUTE, 11))
        card.body.addLayout(header)
        card.body.addWidget(th.text_label(
            "Чем ярче клетка — тем больше наговорено в этот день", th.MUTE, 11))
        self.activity = ActivityStrip()
        card.body.addWidget(self.activity, 1)
        root.addWidget(card, 1)
        self.refresh()

    def refresh(self) -> None:
        summary = stats.summarize(self.history.entries())
        self.words_card.set_value(f"{summary.words:,}".replace(",", " "))
        self.minutes_card.set_value(f"{summary.seconds / 60:.0f}")
        self.activity.set_data(summary.activity)


# --------------------------------------------------------------------------
class SettingsPage(BasePage):
    def __init__(self, app) -> None:  # noqa: ANN001
        super().__init__(app)
        root = QtWidgets.QGridLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        root.addWidget(self._build_recognition(), 0, 0)
        root.addWidget(self._build_microphone(), 0, 1)
        root.addWidget(self._build_hotkey(), 1, 0)
        root.addWidget(self._build_insert(), 1, 1)
        root.addWidget(self._build_dictionary(), 2, 0)
        root.addWidget(self._build_other(), 2, 1)
        root.addWidget(self._build_actions(), 0, 2, 3, 1)
        root.setColumnStretch(0, 1)
        root.setColumnStretch(1, 1)
        root.setRowStretch(1, 1)
        root.setRowStretch(2, 1)

    # --- карточки ---------------------------------------------------------
    def _build_recognition(self) -> Card:
        card = Card()
        head = QtWidgets.QHBoxLayout()
        head.addWidget(th.glyph_label(th.ICONS["spark"], th.GOLD, 15))
        head.addWidget(th.text_label("Распознавание", th.TEXT, 15, 600))
        head.addStretch(1)
        card.body.addLayout(head)
        card.body.addWidget(th.text_label(
            "Локально — полная приватность, офлайн. Облака в приложении нет.",
            th.MUTE, 11))

        self.engine_group = QtWidgets.QButtonGroup(self)
        for index, (name, label_text) in enumerate(asr.available_engines()):
            radio = QtWidgets.QRadioButton(label_text)
            radio.setProperty("engine", name)
            if name == self.settings.engine:
                radio.setChecked(True)
            radio.toggled.connect(self._engine_changed)
            self.engine_group.addButton(radio, index)
            card.body.addWidget(radio)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(th.text_label("Whisper, размер", th.DIM, 12))
        row.addStretch(1)
        self.whisper_box = QtWidgets.QComboBox()
        self.whisper_box.addItems(["tiny", "base", "small", "medium", "large-v3-turbo"])
        self.whisper_box.setCurrentText(self.settings.whisper_model)
        self.whisper_box.currentTextChanged.connect(lambda _v: self._engine_changed())
        row.addWidget(self.whisper_box)
        card.body.addLayout(row)
        self.model_label = th.text_label("", th.MUTE, 11)
        self.model_label.setWordWrap(True)
        card.body.addWidget(self.model_label)
        card.body.addStretch(1)
        return card

    def _build_microphone(self) -> Card:
        card = Card()
        head = QtWidgets.QHBoxLayout()
        head.addWidget(th.glyph_label(th.ICONS["mic"], th.GOLD, 15))
        head.addWidget(th.text_label("Микрофон", th.TEXT, 15, 600))
        head.addStretch(1)
        card.body.addLayout(head)
        card.body.addWidget(th.text_label(
            "Выберите устройство. Ниже — уровень звука: говорите, полоска должна двигаться.",
            th.MUTE, 11, wrap=True))

        self.device_box = QtWidgets.QComboBox()
        self.refresh_devices()
        card.body.addWidget(self.device_box)

        self.level = LevelMeter()
        card.body.addWidget(self.level)
        test_btn = QtWidgets.QPushButton("  Проверить микрофон и модель")
        test_btn.setIcon(th.glyph_icon(th.ICONS["play"], th.TEXT, 15))
        test_btn.clicked.connect(self._test)
        card.body.addWidget(test_btn)
        self.test_label = th.text_label("", th.MUTE, 11)
        self.test_label.setWordWrap(True)
        card.body.addWidget(self.test_label)
        card.body.addStretch(1)
        return card

    def _build_hotkey(self) -> Card:
        card = Card()
        head = QtWidgets.QHBoxLayout()
        head.addWidget(th.glyph_label(th.ICONS["keyboard"], th.GOLD, 15))
        head.addWidget(th.text_label("Горячая клавиша", th.TEXT, 15, 600))
        head.addStretch(1)
        card.body.addLayout(head)

        self.hotkey_edit = QtWidgets.QLineEdit(self.settings.hotkey)
        self.hotkey_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.hotkey_edit.setFont(th.font(14))
        card.body.addWidget(self.hotkey_edit)

        presets = QtWidgets.QHBoxLayout()
        presets.setSpacing(8)
        for label_text, value in PRESET_KEYS:
            button = QtWidgets.QPushButton(label_text)
            button.clicked.connect(lambda _c=False, v=value: self.hotkey_edit.setText(v))
            presets.addWidget(button)
        card.body.addLayout(presets)

        capture = QtWidgets.QPushButton("  Записать своё сочетание…")
        capture.setIcon(th.glyph_icon(th.ICONS["edit"], th.TEXT, 15))
        capture.clicked.connect(self._capture)
        card.body.addWidget(capture)
        card.body.addWidget(th.text_label(
            "Зажмите клавишу и говорите — текст вставится в активное поле.", th.MUTE, 11))
        card.body.addStretch(1)
        return card

    def _build_insert(self) -> Card:
        card = Card()
        head = QtWidgets.QHBoxLayout()
        head.addWidget(th.glyph_label(th.ICONS["doc"], th.GOLD, 15))
        head.addWidget(th.text_label("Вставка", th.TEXT, 15, 600))
        head.addStretch(1)
        card.body.addLayout(head)

        self.paste_check = QtWidgets.QCheckBox("Вставлять текст в активное окно")
        self.paste_check.setChecked(self.settings.auto_paste)
        card.body.addWidget(self.paste_check)
        self.copy_check = QtWidgets.QCheckBox("Копировать в буфер обмена")
        self.copy_check.setChecked(self.settings.copy_to_clipboard)
        card.body.addWidget(self.copy_check)
        self.restore_check = QtWidgets.QCheckBox("Возвращать прежнее содержимое буфера")
        self.restore_check.setChecked(self.settings.restore_clipboard)
        card.body.addWidget(self.restore_check)

        card.body.addWidget(th.text_label("Способ доставки", th.DIM, 12))
        self.mode_group = QtWidgets.QButtonGroup(self)
        for index, (value, label_text) in enumerate((
            ("paste", "Ctrl+V — быстро"),
            ("type", "печатать посимвольно — совместимо"),
        )):
            radio = QtWidgets.QRadioButton(label_text)
            radio.setProperty("mode", value)
            if value == self.settings.insert_mode:
                radio.setChecked(True)
            self.mode_group.addButton(radio, index)
            card.body.addWidget(radio)
        card.body.addStretch(1)
        return card

    def _build_dictionary(self) -> Card:
        card = Card()
        card.body.addWidget(th.text_label("Словарь замен", th.TEXT, 15, 600))
        card.body.addWidget(th.text_label(
            "По одной замене в строке: что_распознано=на_что_заменить", th.MUTE, 11))
        self.dict_edit = QtWidgets.QPlainTextEdit()
        self.dict_edit.setPlainText("\n".join(f"{a}={b}" for a, b in self.settings.dictionary))
        card.body.addWidget(self.dict_edit, 1)
        return card

    def _build_other(self) -> Card:
        card = Card()
        card.body.addWidget(th.text_label("Прочее", th.TEXT, 15, 600))
        self.overlay_check = QtWidgets.QCheckBox("Показывать индикатор диктовки")
        self.overlay_check.setChecked(self.settings.show_overlay)
        card.body.addWidget(self.overlay_check)
        self.sound_check = QtWidgets.QCheckBox("Звуковой сигнал")
        self.sound_check.setChecked(self.settings.play_sound)
        card.body.addWidget(self.sound_check)
        self.autostart_check = QtWidgets.QCheckBox("Запускать при входе в Windows")
        self.autostart_check.setChecked(self.settings.autostart)
        card.body.addWidget(self.autostart_check)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(th.text_label("Цель недели, слов", th.DIM, 12))
        row.addStretch(1)
        self.goal_edit = QtWidgets.QLineEdit(str(self.settings.weekly_goal_words))
        self.goal_edit.setFixedWidth(110)
        self.goal_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.goal_edit)
        card.body.addLayout(row)
        card.body.addWidget(th.text_label(
            "От цели считается полоса прогресса на «Главной».", th.MUTE, 11,
            wrap=True))
        card.body.addStretch(1)
        return card

    def _build_actions(self) -> QtWidgets.QWidget:
        wrap = QtWidgets.QWidget()
        wrap.setFixedWidth(300)
        layout = QtWidgets.QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        save = QtWidgets.QPushButton("  Сохранить настройки")
        save.setObjectName("Accent")
        save.setIcon(th.glyph_icon(th.ICONS["check"], th.GOLD, 16))
        save.setMinimumHeight(44)
        save.clicked.connect(self.save)
        layout.addWidget(save)

        self.saved_label = th.text_label("", th.GREEN, 12)
        self.saved_label.setWordWrap(True)
        layout.addWidget(self.saved_label)
        layout.addWidget(th.text_label("Изменения применяются после сохранения.", th.MUTE, 11))

        models_btn = QtWidgets.QPushButton("  Открыть папку моделей")
        models_btn.setIcon(th.glyph_icon(th.ICONS["folder"], th.TEXT, 15))
        models_btn.clicked.connect(self.app.open_models)
        layout.addWidget(models_btn)

        log_btn = QtWidgets.QPushButton("  Открыть журнал")
        log_btn.setIcon(th.glyph_icon(th.ICONS["page"], th.TEXT, 15))
        log_btn.clicked.connect(self.app.open_log)
        layout.addWidget(log_btn)

        layout.addWidget(th.text_label(
            "Журнал помогает разобраться, если текст не вставляется.", th.MUTE, 11,
            wrap=True))
        layout.addStretch(1)
        return wrap

    # --- логика -----------------------------------------------------------
    def selected_engine(self) -> str:
        button = self.engine_group.checkedButton()
        return button.property("engine") if button else self.settings.engine

    def selected_mode(self) -> str:
        button = self.mode_group.checkedButton()
        return button.property("mode") if button else self.settings.insert_mode

    def refresh_devices(self) -> None:
        current = self.settings.input_device or "по умолчанию"
        names = ["по умолчанию"] + [name for _i, name, _r
                                    in audio.Recorder.list_input_devices()]
        self.device_box.clear()
        self.device_box.addItems(names)
        self.device_box.setCurrentText(current if current in names else "по умолчанию")

    def _engine_changed(self) -> None:
        engine = self.selected_engine()
        if engine == "whisper":
            self.model_label.setText(
                f"Whisper скачает модель «{self.whisper_box.currentText()}» "
                "сам при первом использовании.")
            return
        missing = models.missing(self.settings.models_dir, engine)
        folder = os.path.basename(models.engine_dir(self.settings.models_dir, engine))
        if missing:
            self.model_label.setText(
                f"Не хватает файлов модели: {', '.join(missing)}. "
                "Запустите setup_env.bat или скачайте заново.")
        else:
            self.model_label.setText(f"Модель на месте: {folder}")

    def refresh(self) -> None:
        self._engine_changed()

    def on_show(self) -> None:
        # опрос звуковых устройств занимает доли секунды — только при показе
        self.refresh_devices()
        self._engine_changed()

    def push_level(self, level: float) -> None:
        self.level.push(level)

    def _capture(self) -> None:
        self.saved_label.setText("Нажмите сочетание клавиш…")
        self.saved_label.setStyleSheet(f"color: {th.GOLD}; background: transparent;")
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Запись сочетания")
        dialog.setFixedSize(360, 120)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(th.text_label("Нажмите нужное сочетание клавиш", th.TEXT, 13))
        hint = th.text_label("Например: Ctrl + Shift + Пробел", th.MUTE, 11)
        layout.addWidget(hint)

        def on_key(event: QtGui.QKeyEvent) -> None:
            key = event.key()
            if key in (QtCore.Qt.Key.Key_Control, QtCore.Qt.Key.Key_Shift,
                       QtCore.Qt.Key.Key_Alt, QtCore.Qt.Key.Key_Meta):
                return
            mods = []
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
                mods.append("ctrl")
            if event.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier:
                mods.append("alt")
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                mods.append("shift")
            name = QtGui.QKeySequence(key).toString().lower() or "space"
            name = {" ": "space", "esc": "esc"}.get(name, name)
            spec = "+".join(mods + [name])
            self.hotkey_edit.setText(spec)
            dialog.accept()

        dialog.keyPressEvent = on_key  # type: ignore[method-assign]
        dialog.exec()
        self.saved_label.setText("")

    def _test(self) -> None:
        self.test_label.setText("Запись 3 секунды — говорите…")
        threading.Thread(target=self._test_worker, daemon=True).start()

    def _test_worker(self) -> None:
        import numpy as np
        import sounddevice as sd

        device = self.device_box.currentText()
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
                self._set_test("Микрофон молчит: уровень почти нулевой.", th.RED)
                return
            self._set_test("Распознаю…", th.DIM)
            engine = asr.build_engine(self.selected_engine(), self.settings.models_dir,
                                      self.whisper_box.currentText())
            engine.load()
            text = engine.transcribe(samples, self.settings.language)
            self._set_test(f"Уровень {peak:.2f}. Распознано: {text or '(пусто)'}", th.GREEN)
        except Exception as exc:  # noqa: BLE001
            self._set_test(f"Ошибка: {exc}", th.RED)

    def _set_test(self, text: str, color: str) -> None:
        def apply() -> None:
            self.test_label.setText(text)
            self.test_label.setStyleSheet(f"color: {color}; background: transparent;")
        QtCore.QTimer.singleShot(0, apply)

    def collect(self) -> dict:
        device = self.device_box.currentText()
        if device == "по умолчанию":
            device = ""
        try:
            goal = max(100, min(100000, int(self.goal_edit.text())))
        except ValueError:
            goal = self.settings.weekly_goal_words
        pairs: list[list[str]] = []
        for line in self.dict_edit.toPlainText().splitlines():
            if "=" not in line:
                continue
            src, _sep, dst = line.partition("=")
            if src.strip():
                pairs.append([src.strip(), dst.strip()])
        return {
            "engine": self.selected_engine(),
            "whisper_model": self.whisper_box.currentText(),
            "hotkey": self.hotkey_edit.text().strip().lower() or self.settings.hotkey,
            "insert_mode": self.selected_mode(),
            "auto_paste": self.paste_check.isChecked(),
            "copy_to_clipboard": self.copy_check.isChecked(),
            "restore_clipboard": self.restore_check.isChecked(),
            "show_overlay": self.overlay_check.isChecked(),
            "play_sound": self.sound_check.isChecked(),
            "autostart": self.autostart_check.isChecked(),
            "input_device": device,
            "dictionary": pairs,
            "weekly_goal_words": goal,
        }

    def auto_paste_check(self) -> bool:
        return self.paste_check.isChecked()

    def save(self) -> None:
        message = self.app.apply_settings(self.collect())
        color = th.GREEN if message.startswith("Сохранено") else th.RED
        self.saved_label.setText(message)
        self.saved_label.setStyleSheet(f"color: {color}; background: transparent;")


# --------------------------------------------------------------------------
class HelpPage(BasePage):
    def __init__(self, app) -> None:  # noqa: ANN001
        super().__init__(app)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        root.addStretch(1)

        wrap = QtWidgets.QWidget()
        wrap.setMaximumWidth(880)
        layout = QtWidgets.QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(th.text_label("Как пользоваться", th.TEXT, 26, 600))
        layout.addWidget(th.text_label(
            "Диктуйте голосом в любое приложение — это занимает пару секунд.", th.DIM, 13))

        demo = Card(margins=18)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(18)

        key_box = QtWidgets.QFrame()
        key_box.setObjectName("Soft")
        key_box.setFixedSize(190, 74)
        key_layout = QtWidgets.QVBoxLayout(key_box)
        key_layout.setSpacing(2)
        key_layout.addWidget(th.text_label("ВАША КЛАВИША", th.MUTE, 10, 600))
        key_layout.addWidget(th.text_label(format_hotkey(self.settings.hotkey),
                                           th.GOLD, 15, 600))
        row.addWidget(key_box)

        right = QtWidgets.QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(WaveformHolder(self))
        example = QtWidgets.QFrame()
        example.setObjectName("Soft")
        example_layout = QtWidgets.QVBoxLayout(example)
        example_layout.setContentsMargins(12, 10, 12, 10)
        example_layout.addWidget(th.text_label(
            "Привет! Это пример текста, который я продиктовал.", th.TEXT, 13))
        right.addWidget(example)
        row.addLayout(right, 1)
        demo.body.addLayout(row)
        layout.addWidget(demo)

        hint = Card(margins=18, variant="Hint")
        hint.body.addWidget(th.text_label("Держите, не тапайте", th.GOLD, 15, 600))
        hint.body.addWidget(th.text_label(
            f"Короткое нажатие запись не запускает. Держите "
            f"{format_hotkey(self.settings.hotkey)} всё время, пока говорите, "
            "и отпустите, когда закончили.", th.TEXT, 12))
        layout.addWidget(hint)

        steps = QtWidgets.QHBoxLayout()
        steps.setSpacing(16)
        for number, title, text in (
            ("1", "Зажмите клавишу",
             "В любом текстовом поле — браузер, чат, заметки, почта."),
            ("2", "Говорите",
             "Своими словами, как удобно. Можно вперемешку по-русски и по-английски."),
            ("3", "Отпустите",
             "Текст распознаётся и сам вставится туда, где стоит курсор."),
        ):
            card = Card(margins=16)
            head = QtWidgets.QHBoxLayout()
            head.addStretch(1)
            head.addWidget(th.text_label(number, th.GOLD, 12, 600))
            card.body.addLayout(head)
            card.body.addWidget(th.text_label(title, th.TEXT, 14, 600))
            body = th.text_label(text, th.DIM, 12)
            body.setWordWrap(True)
            card.body.addWidget(body)
            card.body.addStretch(1)
            steps.addWidget(card, 1)
        layout.addLayout(steps)

        fail = Card(margins=18)
        fail.body.addWidget(th.text_label("Не получается?", th.GOLD, 15, 600))
        note = th.text_label(
            "Нажали — и ничего не произошло? Скорее всего, отпустили слишком быстро. "
            "Зажмите клавишу и не отпускайте, пока говорите. Если текст не появился "
            "в поле — он всё равно в буфере обмена, вставьте его вручную.", th.DIM, 12)
        note.setWordWrap(True)
        fail.body.addWidget(note)
        layout.addWidget(fail)

        root.addWidget(wrap, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
        root.addStretch(1)


class WaveformHolder(QtWidgets.QWidget):
    """Волна с подписью «запись…» для примера на вкладке помощи."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        from .qt_widgets import Waveform

        self.setFixedHeight(34)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(Waveform(self), 1)
        layout.addWidget(th.text_label("запись…", th.MUTE, 11), 0,
                         QtCore.Qt.AlignmentFlag.AlignTop)
