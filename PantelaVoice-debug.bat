@echo off
rem Запуск с консолью — видно журнал и ошибки. Для отладки.
setlocal
set "ROOT=%~dp0"
set "PYTHONPATH=%ROOT%pylibs"
py -3.12 "%ROOT%run_pantela.pyw" --verbose %*
pause
