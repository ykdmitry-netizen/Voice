@echo off
rem Установка окружения «Гласографа» с нуля на новой машине.
rem Требуется Python 3.12 x64 (проверьте: py -3.12 --version).
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"

echo === Шаг 1/3: библиотеки ===
py -3.12 "%ROOT%bench\fetch_deps.py" faster-whisper sherpa-onnx sounddevice pillow PySide6-Essentials || goto :fail
py -3.12 "%ROOT%bench\unpack_wheels.py" || goto :fail

echo.
echo === Шаг 2/3: модель распознавания (Parakeet TDT 0.6B v3, около 670 МБ) ===
py -3.12 "%ROOT%bench\download_models.py" parakeet || goto :fail

echo.
echo === Шаг 3/3: проверка ===
set "PYTHONPATH=%ROOT%pylibs"
py -3.12 "%ROOT%bench\selftest.py" || goto :fail

echo.
echo Готово. Запускайте Glasograf.bat
pause
exit /b 0

:fail
echo.
echo Установка прервана из-за ошибки выше.
pause
exit /b 1
