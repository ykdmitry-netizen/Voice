# Лицензии моделей и сторонних компонентов

Код проекта распространяется по [MIT](LICENSE). Модели распознавания речи
распространяются под своими лицензиями и **в этот репозиторий не входят** —
`setup_env.bat` скачивает их с Hugging Face.

## Модели

| Модель | Источник | Лицензия |
|---|---|---|
| NVIDIA Parakeet TDT 0.6B v3 (int8, ONNX) | `csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8` | CC-BY-4.0 (NVIDIA) |
| GigaAM v2 CTC (русский, int8, ONNX) | `csukuangfj/sherpa-onnx-nemo-ctc-giga-am-russian-2024-10-24` | MIT (SberDevices) |
| OpenAI Whisper (через faster-whisper) | `Systran/faster-whisper-*` | MIT (OpenAI) |

Указание имён NVIDIA, SberDevices и OpenAI не означает их поддержки или
одобрения этого проекта.

## Библиотеки

| Компонент | Лицензия |
|---|---|
| Qt 6 (через PySide6) | LGPL-3.0 |
| sherpa-onnx | Apache-2.0 |
| onnxruntime | MIT |
| CTranslate2 | MIT |
| faster-whisper | MIT |
| sounddevice (PortAudio) | MIT |
| Pillow | MIT-CMU |

Qt используется как динамически подключаемая библиотека (PySide6), исходный код
Qt доступен на [code.qt.io](https://code.qt.io/cgit/qt/qtbase.git/) и
[github.com/qt/qtbase](https://github.com/qt/qtbase).

## Происхождение

Проект вдохновлён [PantelaVoice](https://github.com/EvgenyPantela/PantelaVoice) —
приложением локальной диктовки для macOS на SwiftUI (лицензия MIT). Код для
Windows написан заново: SwiftUI, AppKit, CoreML, FluidAudio и WhisperKit на
Windows не существуют, поэтому общего кода у проектов нет — совпадают идея и
пользовательский сценарий.
