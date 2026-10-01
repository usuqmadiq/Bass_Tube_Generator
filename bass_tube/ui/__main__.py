"""Запуск окна командой python -m bass_tube.ui."""

from __future__ import annotations

import sys
import traceback


def main() -> None:
    """Открывает окно генератора.

    Ничего не принимает. Крутит цикл событий, пока окно не закроют.
    Если модуль окна не импортировался или окно упало при старте,
    при запуске без консоли (pythonw, двойной щелчок) показывает
    диалог с причиной, иначе пишет traceback в stderr.
    Возвращает None.
    """
    try:
        from bass_tube.ui.app import TubeApp

        TubeApp().run()
    except Exception as exc:
        _report_launch_error(exc)
        raise SystemExit(1) from exc


def _report_launch_error(exc: BaseException) -> None:
    """Сообщает, почему окно не открылось.

    Принимает исключение. Если stderr есть (запуск из консоли), пишет
    полный traceback туда. Если консоли нет (pythonw), открывает диалог
    tkinter с текстом ошибки. Ничего не возвращает.
    """
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    if sys.stderr is not None:
        sys.stderr.write(text)
        return
    try:
        import tkinter as tk
        from tkinter import messagebox

        from bass_tube.ui.i18n import load_saved_language, set_current_language, t

        set_current_language(load_saved_language())
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showerror(t("app.title"), f"{t('error.launch')}\n\n{exc}")
        root.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    main()
