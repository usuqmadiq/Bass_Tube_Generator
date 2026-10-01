@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

rem Ставит локальное окружение .venv и библиотеки из pyproject.toml.
rem Нужен Python 3.11 или новее. CadQuery качает OpenCASCADE — это долго и тяжело.

echo Генератор басовой трубы: установка библиотек
echo.

set "PY="
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo Не найден Python 3.11 или новее.
    echo Поставьте его с https://www.python.org/downloads/ и отметьте "Add python.exe to PATH".
    pause
    exit /b 1
)

echo Интерпретатор:
%PY% -c "import sys; print(sys.executable); print(sys.version)"
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Создаю виртуальное окружение .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo Не удалось создать .venv
        pause
        exit /b 1
    )
) else (
    echo Окружение .venv уже есть, ставлю пакеты в него.
)

set "VENV=%~dp0.venv\Scripts\python.exe"
"%VENV%" -m pip install --upgrade pip
if errorlevel 1 (
    echo Не удалось обновить pip.
    pause
    exit /b 1
)

echo.
echo Ставлю cadquery, numpy, pillow и сам пакет. Это может занять несколько минут.
"%VENV%" -m pip install -e ".[dev]"
if errorlevel 1 (
    echo Установка не закончилась. Смотрите сообщения pip выше.
    pause
    exit /b 1
)

echo.
echo Готово. Дальше двойной щелчок по Запустить.vbs
pause
