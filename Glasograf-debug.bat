@echo off
rem Запуск «Гласографа» с консолью — видно журнал и ошибки. Для отладки.
setlocal
set "ROOT=%~dp0"
set "PYTHONPATH=%ROOT%pylibs"
py -3.12 "%ROOT%run_glasograf.pyw" --verbose %*
pause
