"""Pantela Voice для Windows — локальная диктовка.

Точка входа: главный поток отдан Tk (индикатор состояния + окно настроек),
горячая клавиша и значок в трее живут в своих потоках с циклами сообщений
Windows, распознавание — в рабочем потоке.
"""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk

from . import asr, audio, inserter, models, theme
from .config import Settings, format_hotkey, home_dir, log_path
from .history import History
from .hotkey import GlobalHotkey
from .main_window import MainWindow
from .overlay import ControlWindow, Overlay
from .tray import TrayIcon, make_icon_file

APP_TITLE = "Pantela Voice"
MUTEX_NAME = "Global\\PantelaVoiceWin_SingleInstance"


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
    # библиотека изображений слишком болтлива в режиме отладки
    logging.getLogger("PIL").setLevel(logging.INFO)


log = logging.getLogger("pantela")


def single_instance() -> bool:
    """True, если это первый запуск. Второй экземпляр нужен только чтобы
    показать сообщение, поэтому мутируем и отпускаем."""
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    already = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    return not already, handle


def set_autostart(enabled: bool) -> None:
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
    ) as key:
        if enabled:
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.exists(pythonw):
                pythonw = sys.executable
            entry = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run_pantela.pyw")
            winreg.SetValueEx(key, APP_TITLE, 0, winreg.REG_SZ, f'"{pythonw}" "{entry}"')
        else:
            try:
                winreg.DeleteValue(key, APP_TITLE)
            except FileNotFoundError:
                pass


class Application:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.load()
        log.info("настройки: %s", self.settings)

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_TITLE)

        self.overlay = Overlay(self.root, self.settings.show_overlay)
        self.recorder = audio.Recorder()
        self.history = History()
        self.events: queue.Queue = queue.Queue()
        self.jobs: queue.Queue = queue.Queue()

        self.engine = None
        self.engine_error: str | None = None
        self._engine_lock = threading.Lock()
        self._recording = False
        self._toggled_on = False
        self._busy = False
        self._tray = None
        self._control = None
        self._pump_job: str | None = None
        self._stopping = False
        self._worker = threading.Thread(target=self._worker_loop, name="asr", daemon=True)
        self._worker.start()

        self.window = MainWindow(self)

        self.hotkey = GlobalHotkey(
            self.settings.hotkey,
            on_press=lambda: self.events.put(("press", None)),
            on_release=lambda: self.events.put(("release", None)),
            on_cancel=lambda: self.events.put(("cancel", None)),
            log=log.warning,
        )

    # --- движок ----------------------------------------------------------
    def _ensure_engine(self):
        with self._engine_lock:
            if self.engine is None:
                self.engine = asr.build_engine(
                    self.settings.engine, self.settings.models_dir, self.settings.whisper_model
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
                log.info(
                    "распознано %.2f с речи за %.2f с (%.1fx): %s",
                    duration, elapsed, duration / elapsed if elapsed else 0, text[:120],
                )
                self.events.put(("result", (text, duration)))
            except Exception as exc:  # noqa: BLE001
                self.engine_error = str(exc)
                log.exception("ошибка распознавания")
                self.events.put(("error", str(exc)))

    # --- сценарий диктовки -----------------------------------------------
    def _start_recording(self) -> None:
        if self._recording:
            return
        try:
            self.recorder.start(self.settings.input_device, self.settings.sample_rate)
        except Exception as exc:  # noqa: BLE001
            log.exception("микрофон недоступен")
            self._beep(error=True)
            self.overlay.error(f"микрофон недоступен: {exc}")
            return
        self._recording = True
        if self._control is not None:
            self._control.set_recording(True)
        self.window.set_recording(True)
        log.info("запись начата (микрофон: %s)", self.recorder.device_name)
        self._beep()
        self.overlay.recording(0.0)

    def _stop_recording(self, cancel: bool = False) -> None:
        if not self._recording:
            return
        self._recording = False
        if self._control is not None:
            self._control.set_recording(False)
        self.window.set_recording(False)
        samples = self.recorder.stop()
        if cancel:
            self.overlay.notice("Отменено", "", hide_after_ms=900)
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
            self.overlay.notice("Тишина в микрофоне", "проверьте устройство ввода", hide_after_ms=2500)
            return

        self._busy = True
        self.overlay.working(f"{duration:.1f} с речи")
        self.jobs.put((samples, self.settings.language))

    def _deliver(self, text: str, seconds: float = 0.0) -> None:
        self._busy = False
        if not text:
            self.overlay.notice("Ничего не распознано", "", hide_after_ms=1600)
            self.window.set_status("Ничего не распознано", theme.MUTE)
            return
        text = text.strip()
        if not text:
            self.overlay.notice("Ничего не распознано", "", hide_after_ms=1600)
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
                threading.Thread(
                    target=lambda: winsound.Beep(1200, 45), daemon=True
                ).start()
        except Exception:  # noqa: BLE001
            pass

    # --- очередь событий в главном потоке --------------------------------
    def _handle_event(self, kind: str, payload) -> bool:  # noqa: ANN001
        """Обрабатывает одно событие. True — приложение должно завершиться."""
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
            self.open_settings()
        elif kind == "window":
            self.window.toggle()
        elif kind == "tray_failed":
            log.warning("переходим на резервное окно управления: %s", payload)
            self._show_control_window()
        elif kind == "quit":
            self.quit()
            return True
        else:
            log.debug("неизвестное событие: %r", kind)
        return False

    def _pump(self) -> None:
        if self._stopping:
            return
        try:
            while True:
                item = self.events.get_nowait()
                # событие может прийти как ("kind", payload) или просто "kind"
                if isinstance(item, tuple):
                    kind = item[0]
                    payload = item[1] if len(item) > 1 else None
                else:
                    kind, payload = item, None
                try:
                    if self._handle_event(kind, payload):
                        return
                except Exception:  # noqa: BLE001 - одно плохое событие не должно
                    log.exception("ошибка обработки события %r", kind)  # ронять цикл
        except queue.Empty:
            pass

        if self._recording:
            level = self.recorder.level * 3.2
            self.overlay.set_level(level)
            self.window.push_level(min(1.0, level))

        self._pump_job = self.root.after(40, self._pump)

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
        self.window.show("settings")

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
        """Применяет настройки из окна: сохраняет и перезапускает то, что нужно."""
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

        self.window.refresh_all()
        log.info("настройки сохранены")
        return "Сохранено"

    # --- трей -------------------------------------------------------------
    def _build_tray(self) -> TrayIcon:
        icon_path = os.path.join(home_dir(), "tray.ico")
        if not os.path.exists(icon_path):
            if not make_icon_file(icon_path):
                icon_path = ""

        def items() -> list[tuple[str, object]]:
            return [
                ("Открыть окно", lambda: self.events.put(("window", None))),
                ("Остановить диктовку" if self._recording else "Начать диктовку",
                 lambda: self.events.put(("toggle", None))),
                ("-", None),
                ("Настройки", lambda: self.events.put(("settings", None))),
                ("Открыть журнал", self._open_log),
                ("Открыть папку моделей", self._open_models),
                ("-", None),
                ("Выход", lambda: self.events.put(("quit", None))),
            ]

        return TrayIcon(
            APP_TITLE,
            items,
            on_default=lambda: self.events.put(("toggle", None)),
            icon_path=icon_path,
            log=log.warning,
        )

    def _open_log(self, *_args) -> None:
        try:
            os.startfile(log_path())  # noqa: S606
        except OSError:
            log.warning("не удалось открыть журнал")

    def _open_models(self, *_args) -> None:
        try:
            os.startfile(self.settings.models_dir)  # noqa: S606
        except OSError:
            log.warning("не удалось открыть папку моделей")

    def _show_control_window(self) -> None:
        if self._control is not None:
            return
        try:
            self._control = ControlWindow(
                self.root,
                on_toggle=lambda: self.events.put(("toggle", None)),
                on_settings=lambda: self.events.put(("settings", None)),
                on_quit=lambda: self.events.put(("quit", None)),
            )
            self.root.lift()
        except Exception:  # noqa: BLE001
            log.exception("не удалось показать резервное окно")

    # --- жизненный цикл ---------------------------------------------------
    def run(self) -> None:
        self.hotkey.start()
        if not self.hotkey.is_running:
            log.error("не удалось поставить хук клавиатуры")
            self.overlay.error("не удалось перехватить горячую клавишу")
        else:
            log.info("горячая клавиша: %s (%s)", format_hotkey(self.settings.hotkey),
                     self.settings.mode)

        threading.Thread(target=self._warmup, name="warmup", daemon=True).start()

        if os.environ.get("PANTELA_NO_TRAY") != "1":
            try:
                self._tray = self._build_tray()
                if self._tray.start():
                    log.info("значок в трее установлен")
                else:
                    log.warning("значок в трее не установился — включаю резервное окно")
                    self._show_control_window()
            except Exception:  # noqa: BLE001
                log.exception("трей недоступен")
                self._show_control_window()
        else:
            log.info("трей отключён переменной PANTELA_NO_TRAY")

        self.window.show()
        self._pump_job = self.root.after(40, self._pump)
        self.root.mainloop()

    def quit(self) -> None:
        log.info("выход")
        self._stopping = True
        if self._pump_job is not None:
            try:
                self.root.after_cancel(self._pump_job)
            except tk.TclError:
                pass
            self._pump_job = None
        try:
            self.recorder.cancel()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.hotkey.stop()
        except Exception:  # noqa: BLE001
            pass
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:  # noqa: BLE001
                pass
        try:
            self.overlay.destroy()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.window.destroy()
        except Exception:  # noqa: BLE001
            pass
        if self._control is not None:
            self._control.destroy()
        self.root.quit()
        self.root.destroy()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
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
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None, "Pantela Voice уже запущен — ищите значок в трее.", APP_TITLE, 0x40
            )
        except Exception:  # noqa: BLE001
            pass
        return 0

    log.info("запуск, домашний каталог: %s", home_dir())
    app = Application()
    if quit_after > 0:
        app.root.after(int(quit_after * 1000), app.quit)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
