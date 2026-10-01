#!/bin/sh
# Ставит локальное окружение .venv и библиотеки из pyproject.toml.
# Нужен Python 3.11 или новее. CadQuery качает OpenCASCADE — это долго и тяжело.

set -e
cd "$(dirname "$0")"

echo "Генератор басовой трубы: установка библиотек"
echo

if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "Не найден Python. Поставьте 3.11 или новее."
    exit 1
fi

"$PY" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" || {
    echo "Нужен Python 3.11 или новее. Сейчас: $($PY -c 'import sys; print(sys.version)')"
    exit 1
}

echo "Интерпретатор:"
"$PY" -c "import sys; print(sys.executable); print(sys.version)"
echo

if [ ! -x .venv/bin/python ]; then
    echo "Создаю виртуальное окружение .venv ..."
    "$PY" -m venv .venv
else
    echo "Окружение .venv уже есть, ставлю пакеты в него."
fi

.venv/bin/python -m pip install --upgrade pip
echo
echo "Ставлю cadquery, numpy, pillow и сам пакет. Это может занять несколько минут."
.venv/bin/python -m pip install -e ".[dev]"

echo
echo "Готово. Запуск: .venv/bin/python -m bass_tube.ui"
