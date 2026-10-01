@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem Запускатор окна генератора. Двойной щелчок открывает интерфейс.
rem Берёт pythonw из локального .venv, чтобы не всплывала консоль Python.
rem start с пустым заголовком закрывает это окно bat сразу после старта.

set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYW%" (
    echo Не найден интерпретатор:
    echo %PYW%
    echo.
    echo Сначала запустите Установить.bat — он создаст .venv и скачает библиотеки.
    pause
    exit /b 1
)

set "PYTHONPATH=%CD%"
start "" "%PYW%" -m bass_tube.ui
