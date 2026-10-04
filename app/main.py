"""Гласограф — локальная голосовая диктовка для Windows.

Интерфейс на Qt (PySide6): главное окно с четырьмя разделами, индикатор
диктовки поверх всех окон и значок в трее. Распознавание — в отдельном потоке,
глобальная горячая клавиша — в своём потоке с хуком клавиатуры Windows.
"""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time

from PySide6 import QtCore, QtGui, QtWidgets

from . import asr, audio, inserter, qt_theme as theme
from .config import APP_TITLE, Settings, format_hotkey, home_dir, log_path
from .history import History
from .hotkey import GlobalHotkey
from .qt_overlay import OverlayWidget
from .qt_window import ControlWindow, MainWindow, Tray

MUTEX_NAME = "Global\\Glasograf_SingleInstance"


def setup_logging(verbose: bool = False) -> None:
    handlers: list[logging.Handler] = []
    try:
        handlers.append(logging.FileHandler(log_path(), encoding="utf-8"))
    except OSError:
        pass  # каталог журнала недоступен — не повод не запускаться
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    if not handlers:
        handlers.append(logging.NullHandler())
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


log = logging.getLogger("glasograf")


def single_instance() -> tuple[bool, object]:
    """True, если это первый запуск."""
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    already = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    return not already, handle


def set_autostart(enabled: bool) -> None:
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.exists(pythonw):
                pythonw = sys.executable
            entry = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "run_glasograf.pyw",
            )
            winreg.SetValueEx(key, APP_TITLE, 0, winreg.REG_SZ, f'"{pythonw}" "{entry}"')
        else:
            try:
                winreg.DeleteValue(key, APP_TITLE)
            except FileNotFoundError:
                pass


class Application(QtCore.QObject):
    def __init__(self, argv: list[str]) -> None:
        super().__init__()
        self.settings = Settings.load()
        log.info("настройки: %s", self.settings)

        self.qapp = QtWidgets.QApplication(argv)
        self.qapp.setApplicationName(APP_TITLE)
        self.qapp.setApplicationDisplayName(APP_TITLE)
        self.qapp.setQuitOnLastWindowClosed(False)
        self.qapp.setStyleSheet(theme.stylesheet())
        self.qapp.setWindowIcon(theme.app_icon())

        self.quitting = False
        self.history = History()
        self.recorder = audio.Recorder()
        self.events: queue.Queue = queue.Queue()
        self.jobs: queue.Queue = queue.Queue()

        self.engine = None
        self.engine_error: str | None = None
        self._engine_lock = threading.Lock()
        self._recording = False
        self._busy = False
        self._control = None

        self.overlay = OverlayWidget()
        self.overlay.enabled = self.settings.show_overlay

        self.window = MainWindow(self)
        self.tray = Tray(self, self.window)

        self._worker = threading.Thread(target=self._worker_loop, name="asr", daemon=True)
        self._worker.start()

        self.hotkey = GlobalHotkey(
            self.settings.hotkey,
            on_press=lambda: self.events.put(("press", None)),
            on_release=lambda: self.events.put(("release", None)),
            on_cancel=lambda: self.events.put(("cancel", None)),
            log=log.warning,
        )

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._pump)
        self._timer.start()

    # --- движок ----------------------------------------------------------
    def _ensure_engine(self):
        with self._engine_lock:
            if self.engine is None:
                self.engine = asr.build_engine(
                    self.settings.engine, self.settings.models_dir,
                    self.settings.whisper_model,
                )
            self.engine.load()
            return self.engine

    def reload_engine(self) -> None:
        with self._engine_lock:
            if self.engine is not None:
                self.engine.close()
            self.engine = None
            self.engine_error = None

    def _warmup(self) -> None:
        try:
            started = time.perf_counter()
            self._ensure_engine()
            log.info("модель загружена за %.1f с", time.perf_counter() - started)
            self.events.put(("warm", None))
        except Exception as exc:  # noqa: BLE001
            self.engine_error = str(exc)
            log.exception("не удалось загрузить модель")
            self.events.put(("warm_error", str(exc)))

    # --- рабочий поток распознавания -------------------------------------
    def _worker_loop(self) -> None:
        while True:
            item = self.jobs.get()
            if item is None:
                return
            samples, language = item
            try:
                started = time.perf_counter()
                engine = self._ensure_engine()
                raw = engine.transcribe(samples, language)
                text = self.settings.apply_dictionary(raw)
                elapsed = time.perf_counter() - started
                duration = len(samples) / audio.TARGET_RATE
                log.info("распознано %.2f с речи за %.2f с (%.1fx): %s",
                         duration, elapsed, duration / elapsed if elapsed else 0,
                         text[:120])
                self.events.put(("result", (text, duration)))
            except Exception as exc:  # noqa: BLE001
                self.engine_error = str(exc)
                log.exception("ошибка распознавания")
                self.events.put(("error", str(exc)))

    # --- сценарий диктовки -----------------------------------------------
    @property
    def is_recording(self) -> bool:
        return self._recording

    def _start_recording(self) -> None:
        if self._recording:
            return
        try:
            self.recorder.start(self.settings.input_device, self.settings.sample_rate)
        except Exception as exc:  # noqa: BLE001
            log.exception("микрофон недоступен")
            self._beep(error=True)
            self.overlay.error(f"микрофон недоступен: {exc}")
            self.window.set_status("Микрофон недоступен", theme.RED)
            return
        self._recording = True
        self.window.set_recording(True)
        if self._control is not None:
            self._control.set_recording(True)
        log.info("запись начата (микрофон: %s)", self.recorder.device_name)
        self._beep()
        self.overlay.recording(0.0)

    def _stop_recording(self, cancel: bool = False) -> None:
        if not self._recording:
            return
        self._recording = False
        self.window.set_recording(False)
        if self._control is not None:
            self._control.set_recording(False)
        samples = self.recorder.stop()
        if cancel:
            self.overlay.notice("Отменено", hide_after_ms=900)
            self.window.set_status("Отменено", theme.MUTE)
            return

        duration = len(samples) / audio.TARGET_RATE
        log.info("запись остановлена: %.2f с, пик %.4f", duration,
                 float(abs(samples).max()) if samples.size else 0.0)
        if duration < self.settings.min_seconds:
            self.overlay.notice("Слишком коротко", f"{duration:.2f} с", hide_after_ms=1200)
            return

        samples = audio.trim_silence(samples)
        peak = float(abs(samples).max()) if samples.size else 0.0
        if peak < 0.01:
            self.overlay.notice("Тишина в микрофоне", "проверьте устройство ввода",
                                hide_after_ms=2500)
            self.window.set_status("Тишина в микрофоне", theme.MUTE)
            return

        self._busy = True
        self.overlay.working(f"{duration:.1f} с речи")
        self.window.set_status("Распознаю…", theme.DIM)
        self.jobs.put((samples, self.settings.language))

    def _deliver(self, text: str, seconds: float = 0.0) -> None:
        self._busy = False
        text = (text or "").strip()
        if not text:
            self.overlay.notice("Ничего не распознано", hide_after_ms=1600)
            self.window.set_status("Ничего не распознано", theme.MUTE)
            return

        pasted = False
        copied = False
        if self.settings.auto_paste:
            try:
                pasted, _ = inserter.insert_text(
                    text,
                    auto_paste=True,
                    restore_clipboard=self.settings.restore_clipboard,
                    paste_delay_ms=self.settings.paste_delay_ms,
                    mode=self.settings.insert_mode,
                )
                copied = True
            except Exception as exc:  # noqa: BLE001
                log.exception("вставка не удалась")
                self.overlay.error(f"вставка не удалась: {exc}")
                self.window.set_status(f"Вставка не удалась: {exc}", theme.RED)
                return
        elif self.settings.copy_to_clipboard:
            copied = inserter.set_clipboard_text(text)

        self.history.add(text, seconds, self.settings.engine)
        self.window.refresh_all()

        if pasted:
            title, status = "Вставлено", "Текст вставлен в активное окно"
        elif copied:
            title, status = "Скопировано", "Текст скопирован в буфер обмена"
        else:
            title, status = "Распознано", "Текст распознан"
        log.info("%s: %s", title, text[:120])
        self.window.set_status(f"{status} · {len(text.split())} сл.", theme.GREEN)
        self.overlay.done(text)

    def _beep(self, error: bool = False) -> None:
        if not self.settings.play_sound:
            return
        try:
            import winsound

            if error:
                winsound.MessageBeep(winsound.MB_ICONHAND)
            else:
                threading.Thread(target=lambda: winsound.Beep(1200, 45),
                                 daemon=True).start()
        except Exception:  # noqa: BLE001
            pass

    # --- очередь событий в главном потоке --------------------------------
    def _handle_event(self, kind: str, payload) -> bool:  # noqa: ANN001
        if kind == "press":
            if self.settings.mode == "hold":
                self._start_recording()
            elif self._recording:
                self._stop_recording()
            else:
                self._start_recording()
        elif kind == "release":
            if self.settings.mode == "hold":
                self._stop_recording()
        elif kind == "cancel":
            self._stop_recording(cancel=True)
        elif kind == "toggle":
            if self._recording:
                self._stop_recording()
            else:
                self._start_recording()
        elif kind == "result":
            if isinstance(payload, tuple):
                self._deliver(payload[0], payload[1] if len(payload) > 1 else 0.0)
            else:
                self._deliver(payload or "")
        elif kind == "error":
            self._busy = False
            self.overlay.error(str(payload)[:80])
        elif kind == "warm":
            log.info("движок готов")
        elif kind == "warm_error":
            self.overlay.notice("Модель не готова", str(payload)[:60], hide_after_ms=4000)
        elif kind == "settings":
            self.show_window("settings")
        elif kind == "window":
            self.toggle_window()
        elif kind == "quit":
            self.quit()
            return True
        else:
            log.debug("неизвестное событие: %r", kind)
        return False

    def _pump(self) -> None:
        if self.quitting:
            return
        try:
            while True:
                item = self.events.get_nowait()
                if isinstance(item, tuple):
                    kind = item[0]
                    payload = item[1] if len(item) > 1 else None
                else:
                    kind, payload = item, None
                try:
                    if self._handle_event(kind, payload):
                        return
                except Exception:  # noqa: BLE001
                    log.exception("ошибка обработки события %r", kind)
        except queue.Empty:
            pass

        if self._recording:
            level = self.recorder.level * 3.2
            self.overlay.set_level(level)
            self.window.push_level(min(1.0, level))

    # --- команды из интерфейса --------------------------------------------
    def toggle_dictation(self) -> None:
        self.events.put(("toggle", None))

    def copy_to_clipboard(self, text: str) -> bool:
        try:
            return inserter.set_clipboard_text(text)
        except Exception:  # noqa: BLE001
            log.exception("не удалось скопировать")
            return False

    def open_settings(self) -> None:
        self.show_window("settings")

    def open_models(self) -> None:
        try:
            os.startfile(self.settings.models_dir)  # noqa: S606
        except OSError:
            log.warning("не удалось открыть папку моделей")

    def open_log(self) -> None:
        try:
            os.startfile(log_path())  # noqa: S606
        except OSError:
            log.warning("не удалось открыть журнал")

    def apply_settings(self, values: dict) -> str:
        old = self.settings
        known = {f for f in Settings.__dataclass_fields__}
        merged = {**old.__dict__, **{k: v for k, v in values.items() if k in known}}
        new = Settings(**{k: v for k, v in merged.items() if k in known})
        try:
            new.save()
        except OSError as exc:
            return f"Не удалось сохранить: {exc}"

        self.settings = new
        self.overlay.enabled = new.show_overlay
        if not new.show_overlay:
            self.overlay.stop()

        if new.hotkey != old.hotkey or new.mode != old.mode:
            try:
                self.hotkey.stop()
                self.hotkey = GlobalHotkey(
                    new.hotkey,
                    on_press=lambda: self.events.put(("press", None)),
                    on_release=lambda: self.events.put(("release", None)),
                    on_cancel=lambda: self.events.put(("cancel", None)),
                    log=log.warning,
                )
                self.hotkey.start()
                log.info("горячая клавиша: %s", format_hotkey(new.hotkey))
            except Exception:  # noqa: BLE001
                log.exception("не удалось перезапустить горячую клавишу")
                return "Сохранено, но горячая клавиша не перезапустилась"

        if (new.engine != old.engine or new.whisper_model != old.whisper_model
                or new.models_dir != old.models_dir):
            self.reload_engine()
            threading.Thread(target=self._warmup, name="warmup", daemon=True).start()

        if new.autostart != old.autostart:
            try:
                set_autostart(new.autostart)
            except Exception as exc:  # noqa: BLE001
                log.warning("автозапуск не настроен: %s", exc)
                return f"Сохранено, автозапуск не настроен: {exc}"

        log.info("настройки сохранены")
        return "Сохранено"

    # --- окно и трей -------------------------------------------------------
    def show_window(self, page: str | None = None) -> None:
        self.window.show_window(page)

    def toggle_window(self) -> None:
        if self.window.isVisible() and not self.window.isMinimized():
            self.window.hide()
        else:
            self.window.show_window()

    # --- жизненный цикл ---------------------------------------------------
    def run(self) -> int:
        self.hotkey.start()
        if self.hotkey.is_running:
            log.info("горячая клавиша: %s (%s)", format_hotkey(self.settings.hotkey),
                     self.settings.mode)
        else:
            log.error("не удалось поставить хук клавиатуры")
            self.overlay.error("не удалось перехватить горячую клавишу")

        threading.Thread(target=self._warmup, name="warmup", daemon=True).start()

        if self.settings.autostart:
            # путь к запускаемому файлу мог измениться — запись в реестре обновляем
            try:
                set_autostart(True)
            except Exception as exc:  # noqa: BLE001
                log.warning("автозапуск не обновлён: %s", exc)

        if os.environ.get("PANTELA_NO_TRAY") != "1":
            try:
                if self.tray.show():
                    log.info("значок в трее установлен")
                else:
                    log.warning("трей недоступен — включаю резервное окно")
                    self._show_control_window()
            except Exception:  # noqa: BLE001
                log.exception("трей недоступен")
                self._show_control_window()
        else:
            log.info("трей отключён переменной PANTELA_NO_TRAY")

        self.window.show_window()
        return self.qapp.exec()

    def _show_control_window(self) -> None:
        if self._control is not None:
            return
        try:
            self._control = ControlWindow(self)
            self._control.show()
        except Exception:  # noqa: BLE001
            log.exception("не удалось показать резервное окно")

    def quit(self) -> None:
        log.info("выход")
        self.quitting = True
        self._timer.stop()
        try:
            self.recorder.cancel()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.hotkey.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.overlay.stop()
            self.overlay.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.tray.icon.hide()
        except Exception:  # noqa: BLE001
            pass
        if self._control is not None:
            self._control.close()
        try:
            self.window.close()
        except Exception:  # noqa: BLE001
            pass
        self.qapp.quit()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    verbose = "--verbose" in argv
    setup_logging(verbose)

    quit_after = 0.0
    if "--quit-after" in argv:
        try:
            quit_after = float(argv[argv.index("--quit-after") + 1])
        except (IndexError, ValueError):
            quit_after = 5.0

    first, _handle = single_instance()
    if not first:
        log.info("приложение уже запущено")
        app = QtWidgets.QApplication(argv)
        QtWidgets.QMessageBox.information(
            None, APP_TITLE, "Гласограф уже запущен — ищите значок в трее.")
        return 0

    log.info("запуск, домашний каталог: %s", home_dir())
    app = Application(argv)
    if quit_after > 0:
        QtCore.QTimer.singleShot(int(quit_after * 1000), app.quit)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
