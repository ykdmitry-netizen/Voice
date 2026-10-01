"""Окно настроек (tkinter): движок, микрофон, горячая клавиша, словарь замен."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import ttk

from . import asr, audio, models
from .config import Settings, format_hotkey

LANGUAGES = [("Русский", "ru"), ("English", "en"), ("Определять самому (Whisper)", "auto")]
WHISPER_SIZES = ["tiny", "base", "small", "medium", "large-v3-turbo"]
MODES = [("Удерживать клавиши", "hold"), ("Нажать — начать, нажать — стоп", "toggle")]


class SettingsWindow:
    def __init__(self, app) -> None:  # noqa: ANN001
        self.app = app
        self.settings: Settings = app.settings
        self._downloading = False
        self._cancel_download = False
        self._test_running = False

        self.win = tk.Toplevel(app.root)
        self.win.title("Pantela Voice — настройки")
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        notebook = ttk.Notebook(self.win)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self._build_recognition(notebook)
        self._build_control(notebook)
        self._build_dictionary(notebook)

        footer = ttk.Frame(self.win)
        footer.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(footer, text="Сохранить", command=self.save).pack(side="right")
        ttk.Button(footer, text="Закрыть", command=self.close).pack(side="right", padx=6)

        self.status = ttk.Label(self.win, text="", foreground="#555")
        self.status.pack(fill="x", padx=12, pady=(0, 8))

        self.refresh_model_status()
        self.win.deiconify()
        self.win.lift()

    # --- вкладки ---------------------------------------------------------
    def _build_recognition(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        notebook.add(frame, text="Распознавание")

        ttk.Label(frame, text="Движок").grid(row=0, column=0, sticky="w", pady=4)
        engines = asr.available_engines()
        self.engine_var = tk.StringVar(value=self.settings.engine)
        combo = ttk.Combobox(
            frame,
            state="readonly",
            width=42,
            values=[f"{name} — {label}" for name, label in engines],
        )
        combo.grid(row=0, column=1, sticky="w", pady=4)
        for idx, (name, _label) in enumerate(engines):
            if name == self.settings.engine:
                combo.current(idx)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._on_engine_change())
        self.engine_combo = combo
        self.engine_names = [name for name, _ in engines]

        ttk.Label(frame, text="Whisper, размер").grid(row=1, column=0, sticky="w", pady=4)
        self.whisper_var = tk.StringVar(value=self.settings.whisper_model)
        ttk.Combobox(
            frame, state="readonly", width=42, values=WHISPER_SIZES, textvariable=self.whisper_var
        ).grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(frame, text="Язык диктовки").grid(row=2, column=0, sticky="w", pady=4)
        self.lang_combo = ttk.Combobox(
            frame, state="readonly", width=42, values=[label for label, _ in LANGUAGES]
        )
        self.lang_combo.grid(row=2, column=1, sticky="w", pady=4)
        for idx, (_label, code) in enumerate(LANGUAGES):
            if code == self.settings.language:
                self.lang_combo.current(idx)

        self.model_status = ttk.Label(frame, text="", foreground="#555", wraplength=380)
        self.model_status.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 2))

        self.download_btn = ttk.Button(frame, text="Скачать модель", command=self.toggle_download)
        self.download_btn.grid(row=4, column=0, sticky="w", pady=4)

        ttk.Label(
            frame,
            text="Parakeet TDT 0.6B v3 — рекомендованный движок: на этом ПК\n"
                 "~1 с задержки на короткую фразу, русский и английский, 670 МБ.",
            foreground="#666",
            justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _build_control(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        notebook.add(frame, text="Управление")

        ttk.Label(frame, text="Горячая клавиша").grid(row=0, column=0, sticky="w", pady=4)
        self.hotkey_var = tk.StringVar(value=self.settings.hotkey)
        entry = ttk.Entry(frame, textvariable=self.hotkey_var, width=28)
        entry.grid(row=0, column=1, sticky="w", pady=4)
        ttk.Button(frame, text="Записать", width=10, command=self.capture_hotkey).grid(
            row=0, column=2, padx=6
        )
        self.hotkey_hint = ttk.Label(frame, text="", foreground="#666")
        self.hotkey_hint.grid(row=1, column=1, columnspan=2, sticky="w")

        ttk.Label(frame, text="Режим").grid(row=2, column=0, sticky="nw", pady=(10, 4))
        self.mode_var = tk.StringVar(value=self.settings.mode)
        modes = ttk.Frame(frame)
        modes.grid(row=2, column=1, columnspan=2, sticky="w", pady=(10, 4))
        for idx, (label, value) in enumerate(MODES):
            ttk.Radiobutton(modes, text=label, value=value, variable=self.mode_var).grid(
                row=idx, column=0, sticky="w"
            )

        ttk.Label(frame, text="Микрофон").grid(row=3, column=0, sticky="w", pady=(10, 4))
        self.device_var = tk.StringVar(value=self.settings.input_device or "по умолчанию")
        self.device_combo = ttk.Combobox(frame, state="readonly", width=40,
                                         textvariable=self.device_var)
        self.device_combo.grid(row=3, column=1, sticky="w", pady=(10, 4))
        ttk.Button(frame, text="Обновить", width=10, command=self.refresh_devices).grid(
            row=3, column=2, padx=6
        )
        self.refresh_devices()

        self.overlay_var = tk.BooleanVar(value=self.settings.show_overlay)
        ttk.Checkbutton(frame, text="Показывать панель состояния", variable=self.overlay_var).grid(
            row=4, column=1, sticky="w", pady=(10, 2)
        )
        self.sound_var = tk.BooleanVar(value=self.settings.play_sound)
        ttk.Checkbutton(frame, text="Звуковой сигнал при записи", variable=self.sound_var).grid(
            row=5, column=1, sticky="w", pady=2
        )
        self.autostart_var = tk.BooleanVar(value=self.settings.autostart)
        ttk.Checkbutton(frame, text="Запускать при входе в Windows", variable=self.autostart_var).grid(
            row=6, column=1, sticky="w", pady=2
        )

        ttk.Label(frame, text="Вставка").grid(row=7, column=0, sticky="nw", pady=(12, 4))
        box = ttk.Frame(frame)
        box.grid(row=7, column=1, columnspan=2, sticky="w", pady=(12, 4))
        self.paste_var = tk.BooleanVar(value=self.settings.auto_paste)
        ttk.Checkbutton(box, text="Вставлять текст в активное окно (Ctrl+V)",
                        variable=self.paste_var).grid(row=0, column=0, sticky="w")
        self.copy_var = tk.BooleanVar(value=self.settings.copy_to_clipboard)
        ttk.Checkbutton(box, text="Копировать в буфер обмена",
                        variable=self.copy_var).grid(row=1, column=0, sticky="w")
        self.restore_var = tk.BooleanVar(value=self.settings.restore_clipboard)
        ttk.Checkbutton(box, text="Возвращать прежнее содержимое буфера",
                        variable=self.restore_var).grid(row=2, column=0, sticky="w")

        self.insert_mode_var = tk.StringVar(value=self.settings.insert_mode)
        mode_box = ttk.Frame(box)
        mode_box.grid(row=3, column=0, sticky="w", pady=(6, 0))
        ttk.Label(mode_box, text="Способ:").grid(row=0, column=0, sticky="nw")
        ttk.Radiobutton(mode_box, text="Ctrl+V — быстро", value="paste",
                        variable=self.insert_mode_var).grid(row=0, column=1, padx=(6, 0), sticky="w")
        ttk.Radiobutton(mode_box, text="печатать посимвольно — совместимо",
                        value="type", variable=self.insert_mode_var).grid(
            row=1, column=1, padx=(6, 0), sticky="w")

        ttk.Label(frame, text="Минимум речи, с").grid(row=8, column=0, sticky="w", pady=(10, 4))
        self.min_var = tk.StringVar(value=str(self.settings.min_seconds))
        ttk.Spinbox(frame, from_=0.1, to=3.0, increment=0.05, width=8,
                    textvariable=self.min_var).grid(row=8, column=1, sticky="w", pady=(10, 4))

        ttk.Button(frame, text="Проверить микрофон и модель", command=self.run_test).grid(
            row=9, column=1, sticky="w", pady=(14, 0)
        )
        self.test_label = ttk.Label(frame, text="", foreground="#333", wraplength=380,
                                    justify="left")
        self.test_label.grid(row=10, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def _build_dictionary(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        notebook.add(frame, text="Словарь замен")

        ttk.Label(
            frame,
            text="По одной замене в строке: что_распознано=на_что_заменить\n"
                 "Например: паракейт=Parakeet   или   харнесс=Harness",
            justify="left",
        ).pack(anchor="w")

        self.dict_text = tk.Text(frame, width=58, height=14, wrap="none")
        self.dict_text.pack(fill="both", expand=True, pady=8)
        self.dict_text.insert(
            "1.0", "\n".join(f"{a}={b}" for a, b in self.settings.dictionary)
        )

    # --- вспомогательное -------------------------------------------------
    @property
    def alive(self) -> bool:
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def focus(self) -> None:
        self.win.lift()
        self.win.focus_force()

    def refresh_devices(self) -> None:
        names = ["по умолчанию"] + [name for _idx, name, _rate in audio.Recorder.list_input_devices()]
        self.device_combo.configure(values=names)
        if self.device_var.get() not in names:
            self.device_var.set("по умолчанию")

    def _selected_engine(self) -> str:
        return self.engine_names[self.engine_combo.current()] \
            if self.engine_combo.current() >= 0 else self.settings.engine

    def _on_engine_change(self) -> None:
        self.refresh_model_status()

    def refresh_model_status(self) -> None:
        engine = self._selected_engine()
        if engine == "whisper":
            self.model_status.configure(
                text="Whisper скачает модель сам при первом использовании "
                     f"({self.whisper_var.get()})."
            )
            self.download_btn.state(["disabled"])
            return
        self.download_btn.state(["!disabled"])
        missing = models.missing(self.settings.models_dir, engine)
        if not missing:
            self.model_status.configure(
                text=f"Модель на месте: {models.engine_dir(self.settings.models_dir, engine)}"
            )
            self.download_btn.configure(text="Проверить целостность")
        else:
            size = models.total_size(engine) / 1e6
            self.model_status.configure(
                text=f"Не хватает файлов: {', '.join(missing)} (около {size:.0f} МБ)"
            )
            self.download_btn.configure(text="Скачать модель")

    # --- скачивание модели ------------------------------------------------
    def toggle_download(self) -> None:
        if self._downloading:
            self._cancel_download = True
            return
        engine = self._selected_engine()
        if engine == "whisper":
            return
        self._downloading = True
        self._cancel_download = False
        self.download_btn.configure(text="Отменить")
        threading.Thread(target=self._download_worker, args=(engine,), daemon=True).start()

    def _download_worker(self, engine: str) -> None:
        def progress(name: str, done: int, total: int) -> None:
            if not name:
                return
            pct = (done / total * 100) if total else 0
            self.win.after(0, lambda: self.status.configure(
                text=f"{name}: {done / 1e6:.0f} / {total / 1e6:.0f} МБ ({pct:.0f}%)"
            ))

        try:
            models.download(
                self.settings.models_dir,
                engine,
                progress=progress,
                cancelled=lambda: self._cancel_download,
            )
            message = "Модель загружена"
        except Exception as exc:  # noqa: BLE001
            message = f"Загрузка не удалась: {exc}"
        finally:
            self._downloading = False
            def finish() -> None:
                self.status.configure(text=message)
                self.download_btn.configure(text="Скачать модель")
                self.refresh_model_status()
            self.win.after(0, finish)

    # --- горячая клавиша --------------------------------------------------
    def capture_hotkey(self) -> None:
        self.hotkey_hint.configure(text="Нажмите комбинацию…")
        grab = tk.Toplevel(self.win)
        grab.overrideredirect(True)
        grab.geometry("1x1+0+0")
        grab.attributes("-topmost", True)
        grab.focus_force()

        def on_key(event: tk.Event) -> None:
            mods = []
            state = event.state
            if state & 0x0004:
                mods.append("ctrl")
            if state & 0x0008:
                mods.append("alt")
            if state & 0x0001:
                mods.append("shift")
            key = event.keysym.lower()
            if key in ("control_l", "control_r", "alt_l", "alt_r", "shift_l", "shift_r",
                       "win_l", "win_r", "super_l"):
                return
            key = {"space": "space", "escape": "esc"}.get(key, key)
            spec = "+".join(mods + [key])
            self.hotkey_var.set(spec)
            self.hotkey_hint.configure(text=f"Будет: {format_hotkey(spec)}")
            grab.destroy()

        grab.bind("<KeyPress>", on_key)
        grab.after(5000, lambda: grab.destroy() if grab.winfo_exists() else None)

    # --- проверка ---------------------------------------------------------
    def run_test(self) -> None:
        if self._test_running:
            return
        self._test_running = True
        self.test_label.configure(text="Запись 3 секунды — говорите…")
        threading.Thread(target=self._test_worker, daemon=True).start()

    def _test_worker(self) -> None:
        import numpy as np

        import sounddevice as sd

        device = self.device_var.get()
        device_index = None
        for idx, name, _rate in audio.Recorder.list_input_devices():
            if name == device:
                device_index = idx
                break
        try:
            recording = sd.rec(int(3 * audio.TARGET_RATE), samplerate=audio.TARGET_RATE,
                               channels=1, dtype="float32", device=device_index)
            sd.wait()
            samples = np.asarray(recording, dtype=np.float32).reshape(-1)
            peak = float(abs(samples).max()) if samples.size else 0.0
            if peak < 0.01:
                self._set_test("Микрофон молчит: уровень почти нулевой. "
                               "Проверьте устройство ввода в Windows.")
                return
            engine_name = self._selected_engine()
            self._set_test("Распознаю…")
            engine = asr.build_engine(engine_name, self.settings.models_dir,
                                      self.whisper_var.get())
            engine.load()
            text = engine.transcribe(samples, self.settings.language)
            self._set_test(f"Уровень {peak:.2f}. Распознано: {text or '(пусто)'}")
        except Exception as exc:  # noqa: BLE001
            self._set_test(f"Ошибка: {exc}")
        finally:
            self._test_running = False

    def _set_test(self, text: str) -> None:
        self.win.after(0, lambda: self.test_label.configure(text=text))

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

    def save(self) -> None:
        old = self.settings
        engine = self._selected_engine()
        language = LANGUAGES[self.lang_combo.current()][1] if self.lang_combo.current() >= 0 \
            else old.language
        device = self.device_var.get()
        if device == "по умолчанию":
            device = ""
        try:
            min_seconds = max(0.1, min(3.0, float(self.min_var.get().replace(",", "."))))
        except ValueError:
            min_seconds = old.min_seconds

        new = Settings(
            engine=engine,
            whisper_model=self.whisper_var.get() or old.whisper_model,
            language=language,
            hotkey=self.hotkey_var.get().strip().lower() or old.hotkey,
            mode=self.mode_var.get(),
            min_seconds=min_seconds,
            max_seconds=old.max_seconds,
            auto_paste=bool(self.paste_var.get()),
            insert_mode=self.insert_mode_var.get(),
            copy_to_clipboard=bool(self.copy_var.get()),
            restore_clipboard=bool(self.restore_var.get()),
            paste_delay_ms=old.paste_delay_ms,
            show_overlay=bool(self.overlay_var.get()),
            play_sound=bool(self.sound_var.get()),
            autostart=bool(self.autostart_var.get()),
            input_device=device,
            sample_rate=old.sample_rate,
            dictionary=self._read_dictionary(),
            models_dir=old.models_dir,
            notify_on_error=old.notify_on_error,
        )
        try:
            new.save()
        except OSError as exc:
            self.status.configure(text=f"Не удалось сохранить настройки: {exc}")
            return
        self.app.settings = new

        # применяем на ходу
        engine_changed = (new.engine != old.engine
                          or new.whisper_model != old.whisper_model
                          or new.models_dir != old.models_dir)
        hotkey_changed = (new.hotkey != old.hotkey or new.mode != old.mode)
        self.app.overlay.enabled = new.show_overlay

        if hotkey_changed:
            from .hotkey import GlobalHotkey

            self.app.hotkey.stop()
            self.app.hotkey = GlobalHotkey(
                new.hotkey,
                on_press=lambda: self.app.events.put(("press", None)),
                on_release=lambda: self.app.events.put(("release", None)),
                on_cancel=lambda: self.app.events.put(("cancel", None)),
                log=lambda *a: None,
            )
            self.app.hotkey.start()
        if engine_changed:
            self.app.reload_engine()
            threading.Thread(target=self.app._warmup, daemon=True).start()
        try:
            from .main import set_autostart

            set_autostart(new.autostart)
        except Exception as exc:  # noqa: BLE001
            self.status.configure(text=f"Автозапуск не настроен: {exc}")

        self.status.configure(text="Сохранено")
        self.app.overlay.notice("Настройки сохранены", "", hide_after_ms=1200)

    def close(self) -> None:
        self._cancel_download = True
        self.app._settings_window = None
        self.win.destroy()
