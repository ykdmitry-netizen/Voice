@echo off
rem Запуск Pantela Voice без консольного окна.
setlocal
set "ROOT=%~dp0"
set "PYTHONPATH=%ROOT%pylibs"

where pyw >nul 2>&1
if %errorlevel%==0 (
  start "" pyw -3.12 "%ROOT%run_pantela.pyw" %*
  exit /b 0
)

for /f "delims=" %%i in ('py -3.12 -c "import sys;print(sys.executable)"') do set "PY=%%i"
if not defined PY (
  echo Не найден Python 3.12. Установите его или поправьте этот файл.
  pause
  exit /b 1
)
set "PYW=%PY:python.exe=pythonw.exe%"
start "" "%PYW%" "%ROOT%run_pantela.pyw" %*
